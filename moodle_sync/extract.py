from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import fitz

_TEXT_RE = re.compile(r"[A-Za-z0-9]")
_MODULE_RE = re.compile(r"\b(COMP\d{4})\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    needs_ocr: bool
    ocr_reason: str | None


@dataclass(frozen=True)
class DocumentInfo:
    path: Path
    file_hash: str
    module: str
    lecture: str
    filename: str
    pages: list[ExtractedPage]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def infer_module(path: Path) -> str:
    for part in path.parts:
        match = _MODULE_RE.search(part)
        if match:
            return match.group(1).upper()
    return "UNKNOWN"


def infer_lecture(path: Path, courses_dir: Path) -> str:
    try:
        rel = path.relative_to(courses_dir)
    except ValueError:
        rel = path
    if len(rel.parts) >= 2:
        return rel.parts[-2]
    return "General"


def detect_needs_ocr(page: fitz.Page, text: str) -> tuple[bool, str | None]:
    stripped = text.strip()
    alnum_count = len(_TEXT_RE.findall(stripped))
    if alnum_count < 25:
        images = page.get_images(full=True)
        if images:
            return True, "low_text_with_images"
        return True, "low_text"
    if stripped and len(set(stripped)) <= 4 and len(stripped) > 50:
        return True, "repeated_garbage"
    blocks = page.get_text("blocks") or []
    text_blocks = [block for block in blocks if len(block) > 4 and str(block[4]).strip()]
    if not text_blocks and page.get_images(full=True):
        return True, "image_only"
    return False, None


def extract_pdf(path: Path, courses_dir: Path) -> DocumentInfo:
    file_hash = sha256_file(path)
    pages: list[ExtractedPage] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text").replace("\x00", "").strip()
            needs_ocr, reason = detect_needs_ocr(page, text)
            pages.append(ExtractedPage(index, text, needs_ocr, reason))
    return DocumentInfo(
        path=path,
        file_hash=file_hash,
        module=infer_module(path),
        lecture=infer_lecture(path, courses_dir),
        filename=path.name,
        pages=pages,
    )
