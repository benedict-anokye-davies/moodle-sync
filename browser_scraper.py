"""
Moodle Browser Scraper -- COMP1008 (and any course with linked content)
Uses Playwright to log in via SSO and download all linked resources.
"""

import asyncio
import re
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[!] Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

MOODLE_URL = "https://moodle.nottingham.ac.uk"
OUTPUT_BASE = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / "courses" / "Semester 2 (Spring)"

DOWNLOAD_EXTENSIONS = {
    ".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".ipynb", ".py", ".java", ".c", ".cpp", ".h",
    ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".mp4", ".mp3", ".wav",
    ".csv", ".json", ".xml", ".txt", ".md",
}


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip('. ')[:200] or "untitled"


async def scrape_course(course_id: int, course_name: str):
    course_url = f"{MOODLE_URL}/course/view.php?id={course_id}"
    output_dir = OUTPUT_BASE / sanitize(course_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Target: {course_url}")
    print(f"[*] Output: {output_dir}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # Navigate to course page (will redirect to SSO login)
        print("[*] Opening Moodle course page (you'll need to log in)...")
        await page.goto(course_url, wait_until="networkidle", timeout=120000)

        # Check if we're on a login page
        current_url = page.url
        if "login" in current_url.lower() or "sso" in current_url.lower() or "idp" in current_url.lower():
            print("[*] SSO login page detected. Please log in manually in the browser window.")
            print("[*] Waiting for you to complete login (up to 2 minutes)...")

            # Wait until we're back on the course page
            try:
                await page.wait_for_url(f"**/course/view.php**", timeout=120000)
                print("[*] Login successful!")
            except Exception:
                # Check if we're on the Moodle dashboard at least
                if "moodle.nottingham.ac.uk" in page.url:
                    print("[*] Logged in. Navigating to course...")
                    await page.goto(course_url, wait_until="networkidle", timeout=60000)
                else:
                    print("[!] Login timed out. Exiting.")
                    await browser.close()
                    return

        await asyncio.sleep(2)

        # Expand all sections if collapsed
        try:
            await page.evaluate("""
                document.querySelectorAll('.collapsed, [aria-expanded="false"]').forEach(el => {
                    try { el.click(); } catch(e) {}
                });
                // Also try Moodle 4.x toggle buttons
                document.querySelectorAll('[data-toggle="collapse"]').forEach(el => {
                    try { el.click(); } catch(e) {}
                });
            """)
            await asyncio.sleep(2)
        except Exception:
            pass

        # Collect all links on the course page
        print("[*] Scanning course page for resources...")
        links = await page.query_selector_all("a[href]")

        resource_links = []
        seen_urls = set()

        for link in links:
            try:
                href = await link.get_attribute("href")
                text = (await link.inner_text()).strip()
                if not href:
                    continue

                # Filter for Moodle resource/file links and external content
                is_resource = any(x in href for x in [
                    "/mod/resource/view.php",
                    "/mod/folder/view.php",
                    "/mod/url/view.php",
                    "/pluginfile.php",
                    "/mod/page/view.php",
                ])

                # Also grab direct file links
                parsed = urlparse(href)
                ext = Path(parsed.path).suffix.lower()
                is_direct_file = ext in DOWNLOAD_EXTENSIONS

                if (is_resource or is_direct_file) and href not in seen_urls:
                    seen_urls.add(href)
                    resource_links.append({"url": href, "text": text or "unnamed"})
            except Exception:
                continue

        print(f"[*] Found {len(resource_links)} resource links\n")

        downloaded = 0
        skipped = 0

        for i, res in enumerate(resource_links, 1):
            url = res["url"]
            name = res["text"]
            print(f"  [{i}/{len(resource_links)}] {name[:60]}")

            try:
                # Navigate to the resource link
                resource_page = await context.new_page()

                # Set up download handler
                download_started = False

                async def handle_download(download):
                    nonlocal download_started, downloaded
                    download_started = True
                    suggested = download.suggested_filename
                    dest = output_dir / sanitize(suggested)

                    if dest.exists():
                        print(f"    [skip] Already exists: {dest.name}")
                        return

                    await download.save_as(str(dest))
                    downloaded += 1
                    print(f"    [+] Downloaded: {dest.name}")

                resource_page.on("download", handle_download)

                response = await resource_page.goto(url, wait_until="load", timeout=30000)
                await asyncio.sleep(2)

                if not download_started:
                    # Check if the page itself contains downloadable links
                    content_type = ""
                    if response:
                        headers = response.headers
                        content_type = headers.get("content-type", "")

                    if "application/" in content_type or "octet-stream" in content_type:
                        # Direct download via response
                        pass
                    else:
                        # Look for download links within the resource page
                        inner_links = await resource_page.query_selector_all("a[href*='pluginfile'], a[href*='forcedownload']")
                        for inner_link in inner_links:
                            try:
                                inner_href = await inner_link.get_attribute("href")
                                if inner_href and inner_href not in seen_urls:
                                    seen_urls.add(inner_href)
                                    async with resource_page.expect_download(timeout=10000) as dl_info:
                                        await inner_link.click()
                                    dl = await dl_info.value
                                    dest = output_dir / sanitize(dl.suggested_filename)
                                    if not dest.exists():
                                        await dl.save_as(str(dest))
                                        downloaded += 1
                                        print(f"    [+] Downloaded: {dest.name}")
                            except Exception:
                                continue

                await resource_page.close()

            except Exception as e:
                err = str(e)[:80]
                print(f"    [!] Error: {err}")
                skipped += 1
                try:
                    await resource_page.close()
                except Exception:
                    pass

        print(f"\n{'='*50}")
        print(f"  Scrape complete!")
        print(f"  Resources scanned: {len(resource_links)}")
        print(f"  Files downloaded: {downloaded}")
        print(f"  Errors/skipped: {skipped}")
        print(f"  Output: {output_dir}")
        print(f"{'='*50}")

        await browser.close()


async def main():
    course_id = 158535
    course_name = "COMP1008 - Fundamentals of Artificial Intelligence"

    if len(sys.argv) > 1:
        course_id = int(sys.argv[1])
    if len(sys.argv) > 2:
        course_name = sys.argv[2]

    await scrape_course(course_id, course_name)


if __name__ == "__main__":
    asyncio.run(main())
