import requests, os, sys, json, re, time
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
MOODLE_URL = "https://moodle.nottingham.ac.uk"
token = Path(os.path.expanduser("~/Desktop/moodle-sync/.moodle_token")).read_text().strip()
OUTPUT_DIR = Path(os.path.expanduser("~/Desktop/moodle-sync/courses/Semester 2 (Spring)/COMP1008 - Fundamentals of Artificial Intelligence"))

def api_call(function, **params):
    payload = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json", **params}
    return requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=payload, timeout=60).json()

def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip('. ')[:200] or "untitled"

def download_file(file_url, dest):
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
    except Exception as e:
        print(f"  FAILED: {e}")
        return False

site = api_call("core_webservice_get_site_info")
courses = api_call("core_enrol_get_users_courses", userid=site["userid"])

cid = None
for c in courses:
    if c.get("shortname", "").startswith("COMP1008"):
        cid = c["id"]
        print(f"Course: {c['shortname']} (id={cid})")
        break

contents = api_call("core_course_get_contents", courseid=cid)
new_files = []

for section in contents:
    sec_name = section.get("name", "")
    mods = section.get("modules", [])
    if mods:
        print(f"\n=== {sec_name} ===")
        for mod in mods:
            mod_name = mod.get("name", "")
            mod_type = mod.get("modname", "")
            files = mod.get("contents", [])
            url = mod.get("url", "")

            print(f"  [{mod_type}] {mod_name}")

            if files:
                for f in files:
                    fname = f.get("filename", "")
                    furl = f.get("fileurl", "")
                    ftype = f.get("type", "")
                    if furl and ftype in ("file", "content"):
                        dest = OUTPUT_DIR / sanitize(sec_name) / sanitize(fname)
                        if download_file(furl, dest):
                            print(f"    DOWNLOADED: {fname}")
                            new_files.append(fname)
                        else:
                            if dest.exists():
                                pass  # already had it
                            # else download failed

            if url and mod_type in ("url",):
                print(f"    URL: {url}")

print(f"\n{'='*50}")
print(f"New files downloaded: {len(new_files)}")
for f in new_files:
    print(f"  + {f}")
