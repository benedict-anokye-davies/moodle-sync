from __future__ import annotations

from moodle_sync.embeddings import HashingEmbedder
from moodle_sync.indexer import index_courses
from moodle_sync.search import search
from tests.conftest import make_pdf


def test_indexing_is_idempotent_and_search_returns_citations(tmp_path):
    courses = tmp_path / "courses"
    db = tmp_path / "search.sqlite3"
    pdf = courses / "COMP1008 - Fundamentals of AI" / "Lecture 03" / "retrieval.pdf"
    pdf.parent.mkdir(parents=True)
    make_pdf(pdf, ["Vector databases and semantic search help retrieve lecture evidence."])
    embedder = HashingEmbedder()

    first = index_courses(courses, db, embedder)
    second = index_courses(courses, db, embedder)
    results = search(db, "semantic search", embedder)

    assert first.documents_indexed == 1
    assert first.chunks_indexed == 1
    assert second.documents_indexed == 0
    assert second.chunks_indexed == 0
    assert results
    assert results[0].module == "COMP1008"
    assert results[0].lecture == "Lecture 03"
    assert results[0].page == 1
    assert "COMP1008 · Lecture 03 · retrieval.pdf · p. 1" == results[0].citation
