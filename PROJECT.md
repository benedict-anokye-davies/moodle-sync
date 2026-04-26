# PROJECT.md — M1 Hybrid Retrieval

## M1 scope

M1 turns the V1 Moodle downloader into a local citation-first search tool. The shippable loop is:

```text
moodle sync -> moodle index -> moodle search "query"
```

The success condition is narrow: return the exact module, lecture, PDF filename, and page where a concept appears.

## Included

- Installable Python package via `pip install -e .`
- `moodle` CLI with `sync`, `index`, and `search`
- SQLite document manifest and search index
- Hash-based incremental indexing by PDF SHA-256
- PyMuPDF text extraction
- OCR-needed detection without OCR execution
- Page-bounded chunks that never cross citation boundaries
- SQLite FTS5 BM25
- Local vector search
- Reciprocal-rank fusion across BM25 and vector results
- Rich terminal output
- `--json` search output for later automation
- Tests for extraction metadata, OCR detection, idempotent indexing, JSON output, and embedding fallback

## Deferred

- OCR execution
- LLM Q&A
- FSRS scheduling
- Discord delivery
- Notion sync
- Calendar integration
- Past-paper ingestion
- Cross-module concept graph
- Reranker
- Web UI
- Hosted deployment

## Embeddings

Default config targets `sentence-transformers/all-MiniLM-L6-v2` through the local provider. If `sentence-transformers` is unavailable, M1 falls back to a deterministic hashing embedder so indexing and search remain usable without API keys or heavyweight installs.

This is intentional. M1 proves ingestion, citation fidelity, and retrieval plumbing before adding paid hosted embeddings or rerankers.

## sqlite-vec spike

`sqlite-vec` is available on PyPI for the Linux environment (`0.1.9` observed). M1 still uses a SQLite BLOB + NumPy cosine fallback rather than making sqlite-vec a hard dependency.

Reason: the corpus is small enough for brute-force cosine, and the milestone should not hinge on extension loading or Windows packaging behavior. The schema keeps embeddings isolated so sqlite-vec can be introduced later without rewriting extraction or search callers.

## OCR policy

M1 detects pages likely to need OCR by checking low extracted text, image-only pages, and repeated garbage text. It records `needs_ocr` and `ocr_reason` per page and reports coverage gaps after indexing.

M1 does not run OCR. That belongs in M2 after the core search loop is stable.

## Operational runbook

Install:

```bash
pip install -e '.[dev]'
```

Sync with cached Moodle token:

```bash
moodle sync
```

Index default course directory:

```bash
moodle index
```

Index explicit paths:

```bash
moodle --courses-dir ~/Desktop/moodle-sync/courses --db ~/Desktop/moodle-sync/moodle_search.sqlite3 index
```

Search:

```bash
moodle search "normalisation database keys"
```

JSON:

```bash
moodle search "normalisation database keys" --json
```

## Verification run

Local verification on generated fixture corpus:

```text
$ pytest -q
.....                                                                    [100%]
5 passed in 0.29s
```

CLI smoke test:

```text
$ moodle --courses-dir /tmp/.../courses --db /tmp/.../search.sqlite3 index
Indexed 1/1 documents, 1 pages, 1 chunks
DB: /tmp/.../search.sqlite3
Embeddings: hashing-fallback

$ moodle --courses-dir /tmp/.../courses --db /tmp/.../search.sqlite3 search "semantic search" --json
{
  "query": "semantic search",
  "results": [
    {
      "citation": "COMP1008 · Lecture 03 · retrieval.pdf · p. 1",
      "module": "COMP1008",
      "lecture": "Lecture 03",
      "filename": "retrieval.pdf",
      "page": 1
    }
  ]
}
```

## Real corpus eval status

Blocked in this environment: Ben's actual synced Moodle corpus is not present under `/root/helios-workspace/moodle-sync/` and credentials are not available. The PR includes the eval-ready CLI path; run the five real queries after pulling on Ben's machine with his local `~/Desktop/moodle-sync/courses` directory.
