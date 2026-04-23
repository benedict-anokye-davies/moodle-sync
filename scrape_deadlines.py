"""
Moodle Deadline Scraper -- University of Nottingham
Pulls assignment due dates, quiz dates, and calendar events via mobile API.
"""

import requests
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

MOODLE_URL = "https://moodle.nottingham.ac.uk"
TOKEN_FILE = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / ".moodle_token"


def get_token() -> str:
    if not TOKEN_FILE.exists():
        print("[!] No saved token. Run moodle_sync.py first to authenticate.")
        sys.exit(1)
    return TOKEN_FILE.read_text().strip()


def api_call(token: str, function: str, **params):
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    payload = {
        "wstoken": token,
        "wsfunction": function,
        "moodlewsrestformat": "json",
        **params,
    }
    resp = requests.post(url, data=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "exception" in data:
        return None
    return data


def ts_to_str(ts):
    if not ts:
        return "No date set"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%a %d %b %Y, %H:%M")


def main():
    token = get_token()

    print("=" * 60)
    print("  Moodle Deadline Scraper -- University of Nottingham")
    print("=" * 60)

    # Get user info
    site_info = api_call(token, "core_webservice_get_site_info")
    if not site_info:
        print("[!] Token expired. Run moodle_sync.py again to re-authenticate.")
        sys.exit(1)

    user_id = site_info["userid"]
    print(f"\n  Logged in as: {site_info.get('fullname', 'Unknown')}\n")

    # Get enrolled courses
    courses = api_call(token, "core_enrol_get_users_courses", userid=user_id)
    if not courses:
        print("[!] Could not get courses.")
        return

    # Filter to actual modules (COMP codes)
    modules = [c for c in courses if c.get("shortname", "").startswith("COMP")]
    course_map = {c["id"]: c for c in modules}

    all_deadlines = []

    # Method 1: Get assignments via mod_assign_get_assignments
    print("[*] Fetching assignments...")
    course_ids_str = ",".join(str(c["id"]) for c in modules)

    for course in modules:
        assigns = api_call(token, "mod_assign_get_assignments",
                          courseids=f"[{course['id']}]")
        if not assigns:
            continue

        for course_data in assigns.get("courses", []):
            for assignment in course_data.get("assignments", []):
                name = assignment.get("name", "Unknown")
                due = assignment.get("duedate", 0)
                cutoff = assignment.get("cutoffdate", 0)
                course_name = course.get("shortname", "Unknown")

                all_deadlines.append({
                    "type": "Assignment",
                    "module": course_name,
                    "name": name,
                    "due": due,
                    "due_str": ts_to_str(due),
                    "cutoff": cutoff,
                    "cutoff_str": ts_to_str(cutoff) if cutoff else None,
                    "course_id": course["id"],
                })

    # Method 2: Get calendar events (catches exams, quizzes, etc.)
    print("[*] Fetching calendar events...")
    events = api_call(token, "core_calendar_get_calendar_upcoming_view")
    if events and "events" in events:
        for event in events["events"]:
            event_type = event.get("eventtype", "")
            course_id = event.get("courseid", 0)
            module_name = event.get("course", {}).get("shortname", "")

            if not module_name and course_id in course_map:
                module_name = course_map[course_id].get("shortname", "Unknown")

            all_deadlines.append({
                "type": event.get("modulename", event_type).capitalize(),
                "module": module_name or "General",
                "name": event.get("name", "Unknown"),
                "due": event.get("timestart", 0),
                "due_str": ts_to_str(event.get("timestart", 0)),
                "cutoff": None,
                "cutoff_str": None,
                "course_id": course_id,
            })

    # Method 3: Check course contents for quiz/exam modules
    print("[*] Scanning course contents for quizzes and exams...")
    for course in modules:
        contents = api_call(token, "core_course_get_contents", courseid=course["id"])
        if not contents:
            continue

        for section in contents:
            for module in section.get("modules", []):
                mod_type = module.get("modname", "")
                mod_name = module.get("name", "")

                # Look for quizzes, exams, tests
                if mod_type in ("quiz", "exam") or any(
                    kw in mod_name.lower()
                    for kw in ["exam", "test", "quiz", "assessment", "deadline", "submission"]
                ):
                    dates = module.get("dates", [])
                    due_ts = 0
                    for d in dates:
                        if d.get("label", "").lower() in ("opens", "closes", "due"):
                            due_ts = d.get("timestamp", 0)

                    if not due_ts and module.get("completiondata"):
                        comp = module["completiondata"]
                        due_ts = comp.get("timemodified", 0)

                    all_deadlines.append({
                        "type": mod_type.capitalize() if mod_type else "Activity",
                        "module": course.get("shortname", "Unknown"),
                        "name": mod_name,
                        "due": due_ts,
                        "due_str": ts_to_str(due_ts) if due_ts else "Date TBC",
                        "cutoff": None,
                        "cutoff_str": None,
                        "course_id": course["id"],
                    })

    # Deduplicate by name + module
    seen = set()
    unique_deadlines = []
    for d in all_deadlines:
        key = (d["module"], d["name"])
        if key not in seen:
            seen.add(key)
            unique_deadlines.append(d)

    # Sort by due date
    unique_deadlines.sort(key=lambda x: x["due"] if x["due"] else float("inf"))

    # Display
    print(f"\n{'=' * 60}")
    print(f"  Found {len(unique_deadlines)} deadlines/events")
    print(f"{'=' * 60}\n")

    for d in unique_deadlines:
        icon = {
            "Assignment": "[ASSGN]",
            "Quiz": "[QUIZ]",
            "Exam": "[EXAM]",
        }.get(d["type"], "[EVENT]")

        print(f"  {icon} [{d['module']}] {d['name']}")
        print(f"     Type: {d['type']}")
        print(f"     Due:  {d['due_str']}")
        if d.get("cutoff_str"):
            print(f"     Cutoff: {d['cutoff_str']}")
        print()

    # Save to JSON
    output = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / "deadlines.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(unique_deadlines, f, indent=2, ensure_ascii=False)
    print(f"  Saved to: {output}")

    # Also save a markdown summary
    md_output = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / "deadlines.md"
    with open(md_output, "w", encoding="utf-8") as f:
        f.write("# Moodle Deadlines\n\n")
        f.write(f"*Last scraped: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("| Module | Type | Name | Due Date |\n")
        f.write("|--------|------|------|----------|\n")
        for d in unique_deadlines:
            f.write(f"| {d['module']} | {d['type']} | {d['name']} | {d['due_str']} |\n")
    print(f"  Saved to: {md_output}")


if __name__ == "__main__":
    main()
