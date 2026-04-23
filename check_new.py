import requests, json, os, sys
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

MOODLE_URL = "https://moodle.nottingham.ac.uk"
token = Path(os.path.expanduser("~/Desktop/moodle-sync/.moodle_token")).read_text().strip()

def api_call(function, **params):
    payload = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json", **params}
    resp = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=payload, timeout=60)
    return resp.json()

site = api_call("core_webservice_get_site_info")
courses = api_call("core_enrol_get_users_courses", userid=site["userid"])

targets = {}
for c in courses:
    sn = c.get("shortname", "")
    if sn.startswith("COMP1009"):
        targets["COMP1009"] = c["id"]
    elif sn.startswith("COMP1003"):
        targets["COMP1003"] = c["id"]

today = datetime(2026, 3, 2, tzinfo=timezone.utc)
today_ts = int(today.timestamp())
yesterday_ts = today_ts - 86400

for code, cid in targets.items():
    print(f"\n=== {code} ===")
    contents = api_call("core_course_get_contents", courseid=cid)
    for section in contents:
        sec_name = section.get("name", "")
        for mod in section.get("modules", []):
            for content in mod.get("contents", []):
                fname = content.get("filename", "")
                tmod = content.get("timemodified", 0)
                ftype = content.get("type", "")
                exts = (".pdf", ".pptx", ".ppt", ".zip", ".java")
                if ftype in ("file", "content") and fname.lower().endswith(exts):
                    mod_dt = datetime.fromtimestamp(tmod, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                    tag = " *** NEW ***" if tmod >= yesterday_ts else ""
                    print(f"  [{sec_name}] {fname} ({mod_dt}){tag}")
