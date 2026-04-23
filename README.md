# moodle-sync

Personal automation tool that mirrors University of Nottingham Moodle modules to local storage. Authenticates via the Moodle Mobile App token endpoint, walks every enrolled course, downloads slides and resources, and tracks coursework deadlines. Designed to be run nightly as a cron job with incremental sync state so only new content is fetched.

Built because I got tired of manually checking five module pages every day to see what was new.

## What it does

- Authenticates via `login/token.php` (Moodle Mobile App service)
- Pulls the full enrolled-course list via `core_enrol_get_users_courses`
- Walks each course's content tree via `core_course_get_contents`
- Downloads new resources (slides, PDFs, links) into a structured local folder per module
- Tracks deadlines from `mod_assign_get_assignments`
- Maintains a `sync_state.json` so re-runs skip already-fetched files

## Layout

| File | What |
|---|---|
| `moodle_sync.py` | One-shot full sync. Prompts for credentials, saves a token, downloads everything. |
| `daily_sync.py` | Cron entry point. Reads cached token, syncs only the active semester modules. |
| `scrape_deadlines.py` | Pulls assignment deadlines and writes a structured list. |
| `check_new.py` | Quick CLI to list the most recent additions across modules. |
| `audit_moodle_sync_and_submissions.py` | Sanity-check that local state matches what's actually live on Moodle. |
| `notion_helper.py` | Optional. Mirrors lecture metadata into a Notion database (off by default). |

## Setup

```bash
git clone https://github.com/benedict-anokye-davies/moodle-sync.git
cd moodle-sync
pip install requests
python moodle_sync.py
```

First run prompts for your Moodle username and password, exchanges them for a long-lived mobile API token, and caches it at `.moodle_token`. Subsequent runs reuse the token.

For nightly automation:

```cron
0 22 * * * cd /path/to/moodle-sync && python daily_sync.py >> sync.log 2>&1
```

## Why mobile token endpoint instead of scraping HTML

Moodle's web pages are JavaScript-heavy and brittle. The mobile app uses a stable JSON Web Services API exposed at `/webservice/rest/server.php` — it's faster, more reliable, and gives structured data directly. Same surface every other Moodle mobile app uses.

## Notes

- Built for the Nottingham Moodle instance (`moodle.nottingham.ac.uk`). The token endpoint and Web Services API are standard Moodle features so it should work on any Moodle install with mobile services enabled, but folder names and module codes are Nottingham-specific and would need adapting.
- Credentials are never written to disk in plaintext. Only the issued token is cached.
- Courses, sync state, and cached lecture files are git-ignored.

## License

MIT
