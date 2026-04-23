"""
Moodle Course Sync -- University of Nottingham
Authenticates via mobile token endpoint, pulls all course content.
"""

import requests
import json
import os
import sys
import getpass
import re
from pathlib import Path
from urllib.parse import urlencode

MOODLE_URL = "https://moodle.nottingham.ac.uk"
SERVICE = "moodle_mobile_app"
OUTPUT_DIR = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / "courses"


def get_token(username: str, password: str) -> str:
    """Authenticate via mobile token endpoint."""
    url = f"{MOODLE_URL}/login/token.php"
    payload = {
        "username": username,
        "password": password,
        "service": SERVICE,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "token" in data:
        return data["token"]

    error = data.get("error", "Unknown error")
    error_code = data.get("errorcode", "")

    if "enablewsdescription" in error.lower() or error_code == "enablewsdescription":
        print("\n[!] Mobile web services are DISABLED on this Moodle instance.")
        print("    The university has locked down the mobile API endpoint.")
        print("    Falling back to Option A (browser scraper) is needed.")
        sys.exit(1)
    elif "invalidlogin" in error_code:
        print("\n[!] Invalid credentials. Check your username and password.")
        sys.exit(1)
    else:
        print(f"\n[!] Auth failed: {error} ({error_code})")
        sys.exit(1)


def api_call(token: str, function: str, **params) -> dict:
    """Call a Moodle Web Service function."""
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
        print(f"  [!] API error in {function}: {data.get('message', 'Unknown')}")
        return None
    return data


def sanitize_filename(name: str) -> str:
    """Remove invalid filename characters."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:200] if name else "untitled"


def download_file(token: str, file_url: str, dest: Path):
    """Download a file using the Moodle token."""
    if dest.exists():
        return False

    separator = "&" if "?" in file_url else "?"
    url = f"{file_url}{separator}token={token}"

    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    [!] Failed to download {dest.name}: {e}")
        return False


def sync_courses(token: str):
    """Pull all enrolled courses and their content."""
    print("\n[*] Getting site info...")
    site_info = api_call(token, "core_webservice_get_site_info")
    if not site_info:
        print("[!] Could not get site info. Token may be invalid.")
        return

    user_id = site_info.get("userid")
    fullname = site_info.get("fullname", "Unknown")
    site_name = site_info.get("sitename", "Moodle")
    print(f"    Logged in as: {fullname} (ID: {user_id})")
    print(f"    Site: {site_name}")

    functions = [f["name"] for f in site_info.get("functions", [])]
    print(f"    Available API functions: {len(functions)}")

    print("\n[*] Getting enrolled courses...")
    courses = api_call(token, "core_enrol_get_users_courses", userid=user_id)
    if not courses:
        print("[!] Could not retrieve courses.")
        return

    print(f"    Found {len(courses)} courses\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    course_index = []

    total_files = 0
    downloaded_files = 0

    for course in courses:
        course_id = course["id"]
        course_name = course.get("fullname", f"Course_{course_id}")
        short_name = course.get("shortname", "")
        safe_name = sanitize_filename(
            f"{short_name} - {course_name}" if short_name else course_name
        )

        print(f"  [{short_name}] {course_name}")
        course_dir = OUTPUT_DIR / safe_name

        course_index.append({
            "id": course_id,
            "name": course_name,
            "shortname": short_name,
            "folder": safe_name,
        })

        contents = api_call(token, "core_course_get_contents", courseid=course_id)
        if not contents:
            print(f"    [!] Could not get contents for {short_name}")
            continue

        for section in contents:
            section_name = sanitize_filename(section.get("name", "General"))
            section_dir = course_dir / section_name

            modules = section.get("modules", [])
            for module in modules:
                mod_contents = module.get("contents", [])
                for content in mod_contents:
                    file_url = content.get("fileurl", "")
                    filename = content.get("filename", "unknown")
                    file_type = content.get("type", "")

                    if not file_url or file_type not in ("file", "content"):
                        continue

                    total_files += 1
                    safe_filename = sanitize_filename(filename)
                    dest = section_dir / safe_filename

                    if download_file(token, file_url, dest):
                        downloaded_files += 1
                        print(f"    + {section_name}/{safe_filename}")

        print()

    with open(OUTPUT_DIR / "course_index.json", "w", encoding="utf-8") as f:
        json.dump(course_index, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"  Sync complete!")
    print(f"  Courses: {len(courses)}")
    print(f"  Files found: {total_files}")
    print(f"  New downloads: {downloaded_files}")
    print(f"  Skipped (already exists): {total_files - downloaded_files}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'='*50}")


def main():
    print("=" * 50)
    print("  Moodle Sync -- University of Nottingham")
    print("=" * 50)
    print()
    print("Your credentials are used ONLY to get a session token.")
    print("Nothing is stored or transmitted anywhere else.\n")

    username = input("Username (e.g. abcyz3): ").strip()
    if not username:
        print("[!] Username required.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    if not password:
        print("[!] Password required.")
        sys.exit(1)

    print("\n[*] Authenticating via mobile token endpoint...")
    token = get_token(username, password)
    print("    Token acquired (expires in ~3 months)")

    token_file = Path(__file__).parent / ".moodle_token"
    token_file.write_text(token)
    print(f"    Token saved to {token_file} (re-run without login next time)")

    sync_courses(token)


def main_with_token():
    """Re-run using saved token."""
    token_file = Path(__file__).parent / ".moodle_token"
    if not token_file.exists():
        print("[!] No saved token found. Run normally first.")
        sys.exit(1)

    token = token_file.read_text().strip()
    print("[*] Using saved token...")
    sync_courses(token)


def sync_single_course(course_id: int):
    """Force-sync a specific course by ID, including linked resources."""
    token_file = Path(__file__).parent / ".moodle_token"
    if not token_file.exists():
        print("[!] No saved token found. Run normally first.")
        sys.exit(1)

    token = token_file.read_text().strip()
    print(f"[*] Force-syncing course {course_id}...")

    site_info = api_call(token, "core_webservice_get_site_info")
    if not site_info:
        print("[!] Token invalid.")
        return

    # Get course info
    contents = api_call(token, "core_course_get_contents", courseid=course_id)
    if not contents:
        print("[!] Could not get course contents.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    downloaded = 0

    for section in contents:
        section_name = sanitize_filename(section.get("name", "General"))
        print(f"\n  Section: {section_name}")

        modules = section.get("modules", [])
        for module in modules:
            mod_name = module.get("name", "unnamed")
            mod_type = module.get("modname", "unknown")
            mod_url = module.get("url", "")

            # Handle direct file contents
            mod_contents = module.get("contents", [])
            for content in mod_contents:
                file_url = content.get("fileurl", "")
                filename = content.get("filename", "unknown")
                file_type = content.get("type", "")

                if not file_url:
                    continue

                total += 1
                safe_section = sanitize_filename(section_name)
                safe_filename = sanitize_filename(filename)
                course_dir = OUTPUT_DIR / f"COMP1008 - Fundamentals of AI (force-synced)"
                dest = course_dir / safe_section / safe_filename

                if download_file(token, file_url, dest):
                    downloaded += 1
                    print(f"    + {safe_section}/{safe_filename}")

            # Log linked resources that need browser access
            if mod_type == "url" and mod_url:
                print(f"    [link] {mod_name}: {mod_url}")
            elif mod_type == "resource" and not mod_contents:
                print(f"    [empty resource] {mod_name}")

    print(f"\n{'='*50}")
    print(f"  Force sync complete for course {course_id}")
    print(f"  Files found: {total}")
    print(f"  Downloaded: {downloaded}")
    print(f"{'='*50}")


if __name__ == "__main__":
    if "--resync" in sys.argv:
        main_with_token()
    elif "--course" in sys.argv:
        idx = sys.argv.index("--course")
        if idx + 1 < len(sys.argv):
            sync_single_course(int(sys.argv[idx + 1]))
        else:
            print("[!] Usage: --course <course_id>")
    else:
        main()
