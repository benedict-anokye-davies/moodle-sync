from __future__ import annotations

import argparse
import json
import re
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config
from .embeddings import get_embedder
from .indexer import index_courses
from .search import SearchResult, search

console = Console()


def _snippet(text: str, query: str, max_chars: int = 420) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    terms = re.findall(r"[A-Za-z0-9_]+", query)
    first = min([compact.lower().find(term.lower()) for term in terms if term.lower() in compact.lower()] or [0])
    start = max(0, first - 120)
    snippet = compact[start : start + max_chars]
    for term in terms:
        snippet = re.sub(f"({re.escape(term)})", r"[bold yellow]\1[/bold yellow]", snippet, flags=re.IGNORECASE)
    return snippet


def _result_to_dict(result: SearchResult) -> dict[str, object]:
    return {
        "chunk_id": result.chunk_id,
        "citation": result.citation,
        "module": result.module,
        "lecture": result.lecture,
        "filename": result.filename,
        "page": result.page,
        "text": result.text,
        "scores": {
            "fused": result.fused_score,
            "bm25": result.bm25_score,
            "vector": result.vector_score,
            "bm25_rank": result.bm25_rank,
            "vector_rank": result.vector_rank,
        },
    }


def cmd_sync(_: argparse.Namespace) -> int:
    from moodle_sync_legacy import main_with_token

    main_with_token()
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    config = load_config(args.courses_dir, args.db)
    embedder = get_embedder(config.embedding_provider, config.embedding_model)
    report = index_courses(config.courses_dir, config.db_path, embedder)
    console.print(f"Indexed {report.documents_indexed}/{report.documents_seen} documents, {report.pages_indexed} pages, {report.chunks_indexed} chunks")
    if report.ocr_pages:
        console.print(f"[yellow]{report.ocr_pages} pages need OCR; search coverage incomplete[/yellow]")
    console.print(f"DB: {config.db_path}")
    console.print(f"Embeddings: {embedder.model_name}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    config = load_config(args.courses_dir, args.db)
    embedder = get_embedder(config.embedding_provider, config.embedding_model)
    results = search(config.db_path, args.query, embedder, limit=args.limit)
    if args.json:
        print(json.dumps({"query": args.query, "results": [_result_to_dict(result) for result in results]}, indent=2, ensure_ascii=False))
        return 0

    console.print(f"[bold]Query:[/bold] {args.query}")
    if not results:
        console.print("No results. Run `moodle index` or try a different query.")
        return 1
    for index, result in enumerate(results, start=1):
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_row(f"[bold cyan]{result.citation}[/bold cyan]")
        table.add_row(f"score={result.fused_score:.4f} bm25_rank={result.bm25_rank} vector_rank={result.vector_rank} vector={result.vector_score:.3f}")
        table.add_row(_snippet(result.text, args.query))
        console.print(Panel(table, title=f"#{index}", border_style="blue"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moodle")
    parser.add_argument("--courses-dir", help="Downloaded Moodle courses directory")
    parser.add_argument("--db", help="SQLite search index path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Run the existing Moodle downloader with a cached token")
    sync_parser.set_defaults(func=cmd_sync)

    index_parser = subparsers.add_parser("index", help="Index downloaded PDF files for citation-first search")
    index_parser.set_defaults(func=cmd_index)

    search_parser = subparsers.add_parser("search", help="Search indexed lecture content")
    search_parser.add_argument("query")
    search_parser.add_argument("--json", action="store_true", help="Print machine-readable results")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.set_defaults(func=cmd_search)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
