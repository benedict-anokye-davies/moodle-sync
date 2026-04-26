from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

TOKEN_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    page: int
    chunk_index: int
    text: str
    chunk_hash: str


def _chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_page(text: str, page: int, target_tokens: int = 500) -> list[Chunk]:
    tokens = TOKEN_RE.findall(text)
    if not tokens:
        return []
    chunks: list[Chunk] = []
    for start in range(0, len(tokens), target_tokens):
        chunk_text = " ".join(tokens[start : start + target_tokens]).strip()
        chunks.append(Chunk(page, len(chunks), chunk_text, _chunk_hash(chunk_text)))
    return chunks
