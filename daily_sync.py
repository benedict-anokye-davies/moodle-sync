"""
Daily Moodle Sync -- University of Nottingham
Syncs new lecture slides and checks deadlines.
Run by cron every evening.
"""

import requests
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

MOODLE_URL = "https://moodle.nottingham.ac.uk"
TOKEN_FILE = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / ".moodle_token"
OUTPUT_DIR = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / "courses" / "Semester 2 (Spring)"
STATE_FILE = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / "sync_state.json"

SEMESTER_2_MODULES = [
    "COMP1003", "COMP1004", "COMP1008", "COMP1009", "COMP1043"
]

MODULE_FOLDERS = {
    "COMP1003": "COMP1003-1-UNUK-SPR-2526 - Introduction to Software Engineering (COMP1003 UNUK) (SPR1 25-26)",
    "COMP1004": "COMP1004-1-UNUK-SPR-2526 - Databases and Interfaces (COMP1004 UNUK) (SPR1 25-26)",
    "COMP1008": "COMP1008 - Fundamentals of Artificial Intelligence",
    "COMP1009": "COMP1009-1-UNUK-SPR-2526 - Programming Paradigms (COMP1009 UNUK) (SPR1 25-26)",
    "COMP1043": "COMP1043-1-UNUK-SPR-2526 - Mathematics for Computer Scientists 2 (COMP1043 UNUK) (SPR1 25-26)",
}


def get_token():
    if not TOKEN_FILE.exists():
        return None
    return TOKEN_FILE.read_text().strip()


def api_call(token, function, **params):
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    payload = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json", **params}
    resp = requests.post(url, data=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "exception" in data:
        return None
    return data


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip('. ')[:200] or "untitled"


def download_file(token, file_url, dest):
    if dest.exists():
        return False
    sep = "&" if "?" in file_url else "?"
    url = f"{file_url}{sep}token={token}"
    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception:
        return False


def ts_to_str(ts):
    if not ts:
        return "No date"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%a %d %b %Y, %H:%M")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_sync": 0, "known_files": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    token = get_token()
    if not token:
        print("NO_TOKEN")
        return

    site_info = api_call(token, "core_webservice_get_site_info")
    if not site_info:
        print("TOKEN_EXPIRED")
        return

    user_id = site_info["userid"]
    state = load_state()
    now = datetime.now(timezone.utc)

    courses = api_call(token, "core_enrol_get_users_courses", userid=user_id)
    if not courses:
        print("NO_COURSES")
        return

    sem2_courses = [c for c in courses if any(
        c.get("shortname", "").startswith(m) for m in SEMESTER_2_MODULES
    )]

    new_files = []
    upcoming_deadlines = []
    new_assignments = []

    for course in sem2_courses:
        course_id = course["id"]
        shortname = course.get("shortname", "")
        module_code = shortname.split("-")[0] if "-" in shortname else shortname

        # Sync new files
        contents = api_call(token, "core_course_get_contents", courseid=course_id)
        if contents:
            folder_name = MODULE_FOLDERS.get(module_code, sanitize(shortname))
            for section in contents:
                section_name = sanitize(section.get("name", "General"))
                for module in section.get("modules", []):
                    for content in module.get("contents", []):
                        file_url = content.get("fileurl", "")
                        filename = content.get("filename", "unknown")
                        file_type = content.get("type", "")
                        time_modified = content.get("timemodified", 0)

                        if not file_url or file_type not in ("file", "content"):
                            continue

                        dest = OUTPUT_DIR / folder_name / section_name / sanitize(filename)
                        file_key = f"{module_code}/{section_name}/{filename}"

                        if file_key not in state.get("known_files", []):
                            if download_file(token, file_url, dest):
                                new_files.append({
                                    "module": module_code,
                                    "section": section_name,
                                    "filename": filename,
                                })
                            state.setdefault("known_files", []).append(file_key)

        # Check assignments
        assigns = api_call(token, "mod_assign_get_assignments", courseids=f"[{course_id}]")
        if assigns:
            for course_data in assigns.get("courses", []):
                for assignment in course_data.get("assignments", []):
                    due = assignment.get("duedate", 0)
                    name = assignment.get("name", "Unknown")

                    if due:
                        due_dt = datetime.fromtimestamp(due, tz=timezone.utc)
                        days_until = (due_dt - now).days

                        if 0 <= days_until <= 14:
                            upcoming_deadlines.append({
                                "module": module_code,
                                "name": name,
                                "due": due,
                                "due_str": ts_to_str(due),
                                "days_until": days_until,
                            })

                        if 0 <= days_until <= 7:
                            intro_date = assignment.get("allowsubmissionsfromdate", 0)
                            if intro_date:
                                intro_dt = datetime.fromtimestamp(intro_date, tz=timezone.utc)
                                if (now - intro_dt).days <= 7:
                                    new_assignments.append({
                                        "module": module_code,
                                        "name": name,
                                        "due_str": ts_to_str(due),
                                    })

    # Check calendar for upcoming events
    events = api_call(token, "core_calendar_get_calendar_upcoming_view")
    if events and "events" in events:
        for event in events["events"]:
            ts = event.get("timestart", 0)
            if ts:
                event_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                days_until = (event_dt - now).days
                if 0 <= days_until <= 14:
                    course_short = event.get("course", {}).get("shortname", "")
                    module_code = course_short.split("-")[0] if "-" in course_short else course_short
                    if any(module_code.startswith(m) for m in SEMESTER_2_MODULES):
                        upcoming_deadlines.append({
                            "module": module_code,
                            "name": event.get("name", "Unknown"),
                            "due": ts,
                            "due_str": ts_to_str(ts),
                            "days_until": days_until,
                        })

    # Deduplicate deadlines
    seen = set()
    unique_deadlines = []
    for d in upcoming_deadlines:
        key = (d["module"], d["name"])
        if key not in seen:
            seen.add(key)
            unique_deadlines.append(d)
    unique_deadlines.sort(key=lambda x: x["due"])

    # Build report
    report = {"date": now.strftime("%Y-%m-%d"), "new_files": new_files,
              "deadlines": unique_deadlines, "new_assignments": new_assignments}

    # Save state
    state["last_sync"] = int(now.timestamp())
    save_state(state)

    # Output as JSON for the cron job to parse
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
