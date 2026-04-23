import requests, os, sys, json, html, re
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
MOODLE_URL = "https://moodle.nottingham.ac.uk"
token = Path(os.path.expanduser("~/Desktop/moodle-sync/.moodle_token")).read_text().strip()

def api_call(function, **params):
    payload = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json", **params}
    return requests.post(MOODLE_URL + "/webservice/rest/server.php", data=payload, timeout=60).json()

site = api_call("core_webservice_get_site_info")
courses = api_call("core_enrol_get_users_courses", userid=site["userid"])
cid = None
for c in courses:
    if c.get("shortname", "").startswith("COMP1008"):
        cid = c["id"]
        break

result = api_call("mod_assign_get_assignments", **{"courseids[0]": cid})
for course_data in result.get("courses", []):
    for a in course_data.get("assignments", []):
        name = a.get("name", "")
        if "Coursework" in name or "coursework" in name:
            due = a.get("duedate", 0)
            due_str = datetime.fromtimestamp(due, tz=timezone.utc).strftime("%a %d %b %Y %H:%M UTC") if due else "No date"
            grade = a.get("grade", 0)
            intro = a.get("intro", "")

            print(f"=== {name} ===")
            print(f"Due: {due_str}")
            print(f"Max grade: {grade}")
            print()

            clean = re.sub(r"<[^>]+>", " ", html.unescape(intro))
            clean = re.sub(r"\s+", " ", clean).strip()
            print("DESCRIPTION:")
            print(clean[:3000])
            print()

            print("RAW HTML:")
            print(intro[:5000])
            print()

            intfiles = a.get("introfiles", [])
            attfiles = a.get("introattachments", [])
            if intfiles:
                print(f"Intro files: {json.dumps(intfiles, indent=2)}")
            if attfiles:
                print(f"Attachments: {json.dumps(attfiles, indent=2)}")

# Also check course contents for coursework-related modules
contents = api_call("core_course_get_contents", courseid=cid)
print("\n\n=== COURSE SECTIONS WITH CW-RELATED CONTENT ===")
for section in contents:
    for mod in section.get("modules", []):
        mod_name = mod.get("name", "")
        mod_type = mod.get("modname", "")
        desc = mod.get("description", "")
        if any(kw in mod_name.lower() for kw in ["coursework", "cw", "project", "assignment"]):
            print(f"\n[{mod_type}] {mod_name}")
            if desc:
                clean_desc = re.sub(r"<[^>]+>", " ", html.unescape(desc))
                clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
                print(f"  {clean_desc[:500]}")
