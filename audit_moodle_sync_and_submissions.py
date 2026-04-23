import os
import re
import json
from pathlib import Path
from datetime import datetime, timezone
import requests

MOODLE_URL = "https://moodle.nottingham.ac.uk"
TOKEN_FILE = Path(os.path.expanduser("~/Desktop/moodle-sync/.moodle_token"))
OUTPUT_BASE = Path(os.path.expanduser("~/Desktop/moodle-sync/courses/Semester 2 (Spring)"))

TARGET_MODULES = ["COMP1003", "COMP1004", "COMP1008", "COMP1009", "COMP1043"]
MODULE_FOLDERS = {
    "COMP1003": "COMP1003-1-UNUK-SPR-2526 - Introduction to Software Engineering (COMP1003 UNUK) (SPR1 25-26)",
    "COMP1004": "COMP1004-1-UNUK-SPR-2526 - Databases and Interfaces (COMP1004 UNUK) (SPR1 25-26)",
    "COMP1008": "COMP1008 - Fundamentals of Artificial Intelligence",
    "COMP1009": "COMP1009-1-UNUK-SPR-2526 - Programming Paradigms (COMP1009 UNUK) (SPR1 25-26)",
    "COMP1043": "COMP1043-1-UNUK-SPR-2526 - Mathematics for Computer Scientists 2 (COMP1043 UNUK) (SPR1 25-26)",
}


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip('. ')[:200] or "untitled"


def ts_str(ts: int | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def api_call(token: str, function: str, **params):
    payload = {
        "wstoken": token,
        "wsfunction": function,
        "moodlewsrestformat": "json",
        **params,
    }
    r = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=payload, timeout=90)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("exception"):
        raise RuntimeError(f"{function}: {data.get('errorcode')} - {data.get('message')}")
    return data


def download_file(token: str, file_url: str, dest: Path) -> bool:
    if dest.exists():
        return False
    sep = "&" if "?" in file_url else "?"
    url = f"{file_url}{sep}token={token}"
    r = requests.get(url, timeout=120, stream=True)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return True


def get_submission_summary(status_data: dict):
    last = status_data.get("lastattempt", {})
    sub = last.get("submission")
    if sub:
        status = sub.get("status", "unknown")
        tmod = sub.get("timemodified")
        return status, tmod
    return "not submitted", None


def main():
    if not TOKEN_FILE.exists():
        print(json.dumps({"error": "TOKEN_FILE_MISSING", "path": str(TOKEN_FILE)}))
        return

    token = TOKEN_FILE.read_text().strip()

    try:
        site = api_call(token, "core_webservice_get_site_info")
    except Exception as e:
        print(json.dumps({"error": "TOKEN_INVALID", "detail": str(e)}))
        return

    user_id = site["userid"]
    now = datetime.now(timezone.utc)

    courses = api_call(token, "core_enrol_get_users_courses", userid=user_id)

    target_courses = []
    for c in courses:
        sn = c.get("shortname", "")
        mod = sn.split("-")[0] if "-" in sn else sn
        if any(sn.startswith(m) for m in TARGET_MODULES):
            target_courses.append((mod, c))

    sync_report = {
        "checked_modules": [],
        "remote_files_total": 0,
        "already_present": 0,
        "missing_before": 0,
        "downloaded_now": 0,
        "download_failures": [],
    }

    assignment_rows = []

    for module_code, course in sorted(target_courses, key=lambda x: x[0]):
        course_id = course["id"]
        folder = MODULE_FOLDERS.get(module_code, sanitize(course.get("shortname", module_code)))
        module_summary = {
            "module": module_code,
            "course": course.get("fullname", ""),
            "remote_files": 0,
            "already_present": 0,
            "missing_before": 0,
            "downloaded_now": 0,
        }

        # --- File comparison + incremental download ---
        contents = api_call(token, "core_course_get_contents", courseid=course_id)
        for section in contents:
            section_name = sanitize(section.get("name", "General"))
            for mod in section.get("modules", []):
                for content in mod.get("contents", []):
                    file_url = content.get("fileurl", "")
                    file_type = content.get("type", "")
                    filename = content.get("filename", "unknown")
                    if not file_url or file_type not in ("file", "content"):
                        continue

                    sync_report["remote_files_total"] += 1
                    module_summary["remote_files"] += 1

                    dest = OUTPUT_BASE / folder / section_name / sanitize(filename)
                    if dest.exists():
                        sync_report["already_present"] += 1
                        module_summary["already_present"] += 1
                    else:
                        sync_report["missing_before"] += 1
                        module_summary["missing_before"] += 1
                        try:
                            if download_file(token, file_url, dest):
                                sync_report["downloaded_now"] += 1
                                module_summary["downloaded_now"] += 1
                        except Exception as e:
                            sync_report["download_failures"].append({
                                "module": module_code,
                                "section": section_name,
                                "filename": filename,
                                "error": str(e)[:200],
                            })

        sync_report["checked_modules"].append(module_summary)

        # --- Assignments: due dates + submission status ---
        try:
            assigns = api_call(token, "mod_assign_get_assignments", **{"courseids[0]": course_id})
        except Exception:
            continue

        for course_data in assigns.get("courses", []):
            for a in course_data.get("assignments", []):
                assign_id = a.get("id")
                due = a.get("duedate", 0)
                name = a.get("name", "Unknown")
                grade_max = a.get("grade", 0)

                status = "unknown"
                submitted_at = None
                grade_display = None
                try:
                    st = api_call(token, "mod_assign_get_submission_status", assignid=assign_id)
                    status, submitted_at = get_submission_summary(st)
                    grade_display = st.get("feedback", {}).get("gradefordisplay")
                except Exception:
                    pass

                days_until = None
                if due:
                    due_dt = datetime.fromtimestamp(due, tz=timezone.utc)
                    days_until = (due_dt - now).days

                assignment_rows.append({
                    "module": module_code,
                    "assignment": name,
                    "due_ts": due,
                    "due": ts_str(due),
                    "days_until": days_until,
                    "max_grade": grade_max,
                    "submission_status": status,
                    "submitted_at": ts_str(submitted_at),
                    "grade": grade_display,
                })

    # Sort assignments by due date then module/name
    assignment_rows.sort(key=lambda x: (x["due_ts"] or 9999999999, x["module"], x["assignment"]))

    upcoming = [a for a in assignment_rows if a["due_ts"] and (a["days_until"] is not None and a["days_until"] >= 0)]
    submitted = [a for a in assignment_rows if str(a.get("submission_status", "")).lower() == "submitted"]

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sync": sync_report,
        "upcoming_assignments": upcoming,
        "submitted_assignments": submitted,
        "all_assignments": assignment_rows,
    }

    out_path = Path(os.path.expanduser("~/Desktop/moodle-sync/last_audit_report.json"))
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "report_file": str(out_path),
        "sync_summary": {
            "remote_files_total": sync_report["remote_files_total"],
            "already_present": sync_report["already_present"],
            "missing_before": sync_report["missing_before"],
            "downloaded_now": sync_report["downloaded_now"],
            "download_failures": len(sync_report["download_failures"]),
        },
        "upcoming_count": len(upcoming),
        "submitted_count": len(submitted),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
