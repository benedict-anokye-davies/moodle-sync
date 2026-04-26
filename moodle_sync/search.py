from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .db import blob_to_vector, connect
from .embeddings import Embedder, cosine_scores


@dataclass(frozen=True)
class SearchResult:
    chunk_id: int
    citation: str
    module: str
    lecture: str
    filename: str
    page: int
    text: str
    bm25_rank: int | None
    vector_rank: int | None
    bm25_score: float
    vector_score: float
    fused_score: float


def _escape_fts(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+", query)
    return " OR ".join(terms) if terms else query


def _rrf(rank: int | None, k: int = 60) -> float:
    return 0.0 if rank is None else 1.0 / (k + rank)


def search(db_path: Path, query: str, embedder: Embedder, limit: int = 5, candidates: int = 50) -> list[SearchResult]:
    conn = connect(db_path)
    fts_query = _escape_fts(query)
    bm25_rows = conn.execute(
        """
        SELECT c.*, bm25(chunks_fts) AS bm25_score
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        WHERE chunks_fts MATCH ?
        ORDER BY bm25_score
        LIMIT ?
        """,
        (fts_query, candidates),
    ).fetchall() if fts_query else []

    all_rows = conn.execute(
        """
        SELECT c.*, e.vector
        FROM chunks c
        JOIN embeddings e ON e.chunk_id = c.id
        """
    ).fetchall()
    query_vector = embedder.embed([query])[0]
    vector_scores = cosine_scores(query_vector, [blob_to_vector(row["vector"]) for row in all_rows])
    vector_ranked = sorted(zip(all_rows, vector_scores), key=lambda item: item[1], reverse=True)[:candidates]

    combined: dict[int, dict[str, object]] = {}
    for rank, row in enumerate(bm25_rows, start=1):
        combined[int(row["id"])] = {"row": row, "bm25_rank": rank, "bm25_score": float(row["bm25_score"]), "vector_rank": None, "vector_score": 0.0}
    for rank, (row, score) in enumerate(vector_ranked, start=1):
        data = combined.setdefault(int(row["id"]), {"row": row, "bm25_rank": None, "bm25_score": 0.0, "vector_rank": None, "vector_score": 0.0})
        data["vector_rank"] = rank
        data["vector_score"] = float(score)

    results: list[SearchResult] = []
    for data in combined.values():
        row = data["row"]
        bm25_rank = data["bm25_rank"]
        vector_rank = data["vector_rank"]
        fused = _rrf(bm25_rank if isinstance(bm25_rank, int) else None) + _rrf(vector_rank if isinstance(vector_rank, int) else None)
        citation = f"{row['module']} · {row['lecture']} · {row['filename']} · p. {row['page_number']}"
        results.append(SearchResult(
            chunk_id=int(row["id"]),
            citation=citation,
            module=str(row["module"]),
            lecture=str(row["lecture"]),
            filename=str(row["filename"]),
            page=int(row["page_number"]),
            text=str(row["text"]),
            bm25_rank=bm25_rank if isinstance(bm25_rank, int) else None,
            vector_rank=vector_rank if isinstance(vector_rank, int) else None,
            bm25_score=float(data["bm25_score"]),
            vector_score=float(data["vector_score"]),
            fused_score=fused,
        ))
    conn.close()
    return sorted(results, key=lambda result: result.fused_score, reverse=True)[:limit]
