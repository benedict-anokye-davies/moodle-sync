from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .chunking import chunk_page
from .db import connect, delete_document, get_document_by_path, insert_index_run, set_metadata, vector_to_blob
from .embeddings import Embedder
from .extract import extract_pdf


@dataclass(frozen=True)
class IndexReport:
    documents_seen: int
    documents_indexed: int
    pages_indexed: int
    chunks_indexed: int
    ocr_pages: int


def iter_pdfs(courses_dir: Path) -> list[Path]:
    return sorted(path for path in courses_dir.rglob("*.pdf") if path.is_file())


def index_courses(courses_dir: Path, db_path: Path, embedder: Embedder) -> IndexReport:
    conn = connect(db_path)
    pdfs = iter_pdfs(courses_dir)
    stats = {
        "documents_seen": len(pdfs),
        "documents_indexed": 0,
        "pages_indexed": 0,
        "chunks_indexed": 0,
        "ocr_pages": 0,
    }
    with conn:
        set_metadata(conn, embedding_provider="local", embedding_model=embedder.model_name, embedding_dimensions=str(embedder.dimensions))
        for pdf in pdfs:
            info = extract_pdf(pdf, courses_dir)
            existing = get_document_by_path(conn, pdf)
            if existing and existing["file_hash"] == info.file_hash:
                continue
            if existing:
                delete_document(conn, int(existing["id"]))

            cursor = conn.execute(
                """
                INSERT INTO documents(path, file_hash, module, lecture, filename)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(info.path), info.file_hash, info.module, info.lecture, info.filename),
            )
            document_id = int(cursor.lastrowid)
            stats["documents_indexed"] += 1

            pending_embeddings: list[tuple[int, str]] = []
            for page in info.pages:
                conn.execute(
                    """
                    INSERT INTO pages(document_id, page_number, text, needs_ocr, ocr_reason)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (document_id, page.page_number, page.text, int(page.needs_ocr), page.ocr_reason),
                )
                stats["pages_indexed"] += 1
                stats["ocr_pages"] += int(page.needs_ocr)
                for chunk in chunk_page(page.text, page.page_number):
                    cursor = conn.execute(
                        """
                        INSERT INTO chunks(document_id, page_number, chunk_index, chunk_hash, text, module, lecture, filename)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (document_id, chunk.page, chunk.chunk_index, chunk.chunk_hash, chunk.text, info.module, info.lecture, info.filename),
                    )
                    chunk_id = int(cursor.lastrowid)
                    pending_embeddings.append((chunk_id, chunk.text))
                    stats["chunks_indexed"] += 1

            if pending_embeddings:
                vectors = embedder.embed([text for _, text in pending_embeddings])
                conn.executemany(
                    """
                    INSERT INTO embeddings(chunk_id, provider, model, dimensions, vector)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (chunk_id, "local", embedder.model_name, embedder.dimensions, vector_to_blob(vector))
                        for (chunk_id, _), vector in zip(pending_embeddings, vectors)
                    ],
                )
        insert_index_run(conn, stats)
    conn.close()
    return IndexReport(**stats)
