# moodle-sync

Personal automation tool that mirrors University of Nottingham Moodle modules to local storage, then builds a local citation-first search index over downloaded lecture PDFs.

Built because I got tired of manually checking five module pages every day to see what was new — and because finding the exact slide that taught a concept should not require spelunking through Moodle.

## What it does

### Sync

- Authenticates via `login/token.php` (Moodle Mobile App service)
- Pulls the full enrolled-course list via `core_enrol_get_users_courses`
- Walks each course's content tree via `core_course_get_contents`
- Downloads new resources into a structured local folder per module
- Tracks deadlines from `mod_assign_get_assignments`

### Search

- Extracts PDF text with PyMuPDF
- Stores document/page/chunk provenance in SQLite
- Detects pages that probably need OCR without running OCR in M1
- Indexes chunks with SQLite FTS5 BM25
- Adds local vector search with a MiniLM provider when `sentence-transformers` is installed
- Falls back to deterministic local hashing embeddings when MiniLM is unavailable
- Fuses BM25 and vector ranks with reciprocal rank fusion
- Returns exact module / lecture / filename / page citations
- Supports Rich terminal output and `--json` for future Discord / Notion / Q&A layers

## Setup

```bash
git clone https://github.com/benedict-anokye-davies/moodle-sync.git
cd moodle-sync
pip install -e .
```

For the stronger local embedding model:

```bash
pip install -e '.[embeddings]'
```

First sync still uses the original credential flow:

```bash
python moodle_sync_legacy.py
```

Subsequent syncs can use the CLI wrapper around the cached token:

```bash
moodle sync
```

## Index downloaded PDFs

By default the indexer reads:

```text
~/Desktop/moodle-sync/courses
```

and writes:

```text
~/Desktop/moodle-sync/moodle_search.sqlite3
```

Run:

```bash
moodle index
```

Override paths when needed:

```bash
moodle --courses-dir ./courses --db ./moodle_search.sqlite3 index
```

Example output:

```text
Indexed 1/1 documents, 1 pages, 1 chunks
DB: /tmp/search.sqlite3
Embeddings: hashing-fallback
```

If extraction quality is weak, M1 reports coverage gaps instead of pretending OCR happened:

```text
12 pages need OCR; search coverage incomplete
```

## Search

```bash
moodle search "semantic search"
```

Terminal output shows top citations, score breakdown, and highlighted snippets:

```text
Query: semantic search
╭─ #1 ─────────────────────────────────────────────────────────────╮
│ COMP1008 · Lecture 03 · retrieval.pdf · p. 1                    │
│ score=0.0328 bm25_rank=1 vector_rank=1 vector=0.408             │
│ Vector databases and semantic search help retrieve lecture ...   │
╰──────────────────────────────────────────────────────────────────╯
```

Machine-readable output for later Discord / Notion / Q&A work:

```bash
moodle search "semantic search" --json
```

```json
{
  "query": "semantic search",
  "results": [
    {
      "citation": "COMP1008 · Lecture 03 · retrieval.pdf · p. 1",
      "module": "COMP1008",
      "lecture": "Lecture 03",
      "filename": "retrieval.pdf",
      "page": 1,
      "scores": {
        "fused": 0.03278688524590164,
        "bm25_rank": 1,
        "vector_rank": 1
      }
    }
  ]
}
```

## Configuration

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `MOODLE_COURSES_DIR` | `~/Desktop/moodle-sync/courses` | Downloaded course files |
| `MOODLE_SEARCH_DB` | `~/Desktop/moodle-sync/moodle_search.sqlite3` | SQLite search index |
| `MOODLE_EMBEDDING_PROVIDER` | `local` | M1 supports local only |
| `MOODLE_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local MiniLM model name |

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```

## Notes

- Built for the Nottingham Moodle instance (`moodle.nottingham.ac.uk`).
- Credentials are never written to disk in plaintext. Only the issued Moodle token is cached.
- Courses, sync state, local DBs, and downloaded lecture files are git-ignored.
- OCR execution, LLM Q&A, FSRS, Discord delivery, Notion sync, calendar work, past-paper ingestion, reranking, and hosted UI are deliberately out of M1.

## License

MIT
