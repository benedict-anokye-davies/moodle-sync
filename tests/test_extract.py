from __future__ import annotations

from moodle_sync.extract import extract_pdf
from tests.conftest import make_pdf


def test_extract_pdf_preserves_module_lecture_page_metadata(tmp_path):
    courses = tmp_path / "courses"
    pdf = courses / "COMP1008 - Fundamentals of AI" / "Lecture 03" / "search.pdf"
    pdf.parent.mkdir(parents=True)
    make_pdf(pdf, ["Neural search uses embeddings for semantic retrieval."])

    document = extract_pdf(pdf, courses)

    assert document.module == "COMP1008"
    assert document.lecture == "Lecture 03"
    assert document.filename == "search.pdf"
    assert document.pages[0].page_number == 1
    assert "semantic retrieval" in document.pages[0].text
    assert document.pages[0].needs_ocr is False


def test_extract_pdf_marks_blank_page_as_ocr_needed(tmp_path):
    courses = tmp_path / "courses"
    pdf = courses / "COMP1008" / "Lecture 04" / "blank.pdf"
    pdf.parent.mkdir(parents=True)
    make_pdf(pdf, [""])

    document = extract_pdf(pdf, courses)

    assert document.pages[0].needs_ocr is True
    assert document.pages[0].ocr_reason == "low_text"
