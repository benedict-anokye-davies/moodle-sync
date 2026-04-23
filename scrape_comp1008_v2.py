"""
COMP1008 content scraper - uses Moodle web services to grab all content
including linked resources that don't show up in normal file listings.
"""
import requests, os, sys, re, json
from pathlib import Path

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

def download(url, dest):
    if dest.exists():
        return False
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}token={token}"
    try:
        resp = requests.get(full_url, timeout=120, stream=True, allow_redirects=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        size = dest.stat().st_size
        if size < 500:
            content = dest.read_text(errors="ignore")
            if "error" in content.lower() or "exception" in content.lower():
                dest.unlink()
                return False
        return True
    except Exception as e:
        print(f"    FAIL: {e}")
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
all_content = []

for section in contents:
    sec_name = section.get("name", "General")
    print(f"\n=== {sec_name} ===")

    for mod in section.get("modules", []):
        mod_name = mod.get("name", "")
        mod_type = mod.get("modname", "")
        mod_url = mod.get("url", "")

        # Collect content info
        all_content.append({
            "section": sec_name,
            "name": mod_name,
            "type": mod_type,
            "url": mod_url,
        })

        # Download any direct files
        for f in mod.get("contents", []):
            fname = f.get("filename", "")
            furl = f.get("fileurl", "")
            ftype = f.get("type", "")

            if furl and ftype in ("file", "content"):
                dest = OUTPUT_DIR / sanitize(sec_name) / sanitize(fname)
                if download(furl, dest):
                    print(f"  + {fname}")
                    new_files.append(fname)

        # For resource/page/url modules, try to get content via web service
        if mod_type == "resource":
            mod_id = mod.get("id", 0)
            if mod_id:
                try:
                    res = api_call("mod_resource_get_resources_by_courses", courseids=f"[{cid}]")
                    if res and "resources" in res:
                        for r in res["resources"]:
                            if r.get("coursemodule") == mod_id:
                                for cf in r.get("contentfiles", []):
                                    furl = cf.get("fileurl", "")
                                    fname = cf.get("filename", "")
                                    if furl:
                                        dest = OUTPUT_DIR / sanitize(sec_name) / sanitize(fname)
                                        if download(furl, dest):
                                            print(f"  + {fname}")
                                            new_files.append(fname)
                except Exception:
                    pass

        # For page modules, get the HTML content
        if mod_type == "page":
            mod_id = mod.get("id", 0)
            mod_instance = mod.get("instance", 0)
            if mod_instance:
                try:
                    res = api_call("mod_page_get_pages_by_courses", courseids=f"[{cid}]")
                    if res and "pages" in res:
                        for pg in res["pages"]:
                            if pg.get("coursemodule") == mod_id:
                                content_html = pg.get("content", "")
                                pg_name = pg.get("name", mod_name)
                                if content_html:
                                    dest = OUTPUT_DIR / sanitize(sec_name) / sanitize(f"{pg_name}.html")
                                    if not dest.exists():
                                        dest.parent.mkdir(parents=True, exist_ok=True)
                                        dest.write_text(content_html, encoding="utf-8")
                                        print(f"  + {pg_name}.html (page content)")
                                        new_files.append(f"{pg_name}.html")

                                # Extract any file URLs from the HTML
                                urls_in_html = re.findall(r'href="([^"]*pluginfile[^"]*)"', content_html)
                                urls_in_html += re.findall(r'src="([^"]*pluginfile[^"]*)"', content_html)
                                for u in urls_in_html:
                                    u = u.replace("&amp;", "&")
                                    fname_match = re.search(r'/([^/?]+)(?:\?|$)', u)
                                    if fname_match:
                                        fname = fname_match.group(1)
                                        dest = OUTPUT_DIR / sanitize(sec_name) / sanitize(fname)
                                        if download(u, dest):
                                            print(f"  + {fname} (from page)")
                                            new_files.append(fname)
                except Exception as e:
                    print(f"    page error: {e}")

        # For URL modules, just log the URL
        if mod_type == "url":
            print(f"  [link] {mod_name}: {mod_url}")

        # For label modules with descriptions, check for embedded files
        if mod_type == "label":
            desc = mod.get("description", "")
            if desc:
                urls_in_desc = re.findall(r'href="([^"]*pluginfile[^"]*)"', desc)
                urls_in_desc += re.findall(r'src="([^"]*pluginfile[^"]*)"', desc)
                for u in urls_in_desc:
                    u = u.replace("&amp;", "&")
                    fname_match = re.search(r'/([^/?]+)(?:\?|$)', u)
                    if fname_match:
                        fname = fname_match.group(1)
                        dest = OUTPUT_DIR / sanitize(sec_name) / sanitize(fname)
                        if download(u, dest):
                            print(f"  + {fname} (from label)")
                            new_files.append(fname)

# Save course structure
structure_file = OUTPUT_DIR / "course_structure.json"
with open(structure_file, "w", encoding="utf-8") as f:
    json.dump(all_content, f, indent=2, ensure_ascii=False)

print(f"\n{'='*50}")
print(f"New files: {len(new_files)}")
for f in new_files:
    print(f"  + {f}")
print(f"Course structure saved to: {structure_file}")
print(f"Total files in folder:")
total = list(OUTPUT_DIR.rglob("*"))
total_files = [f for f in total if f.is_file()]
print(f"  {len(total_files)} files")
