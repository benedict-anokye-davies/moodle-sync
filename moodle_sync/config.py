from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_COURSES_DIR = Path.home() / "Desktop" / "moodle-sync" / "courses"
DEFAULT_DB_PATH = Path.home() / "Desktop" / "moodle-sync" / "moodle_search.sqlite3"


@dataclass(frozen=True)
class Config:
    courses_dir: Path = DEFAULT_COURSES_DIR
    db_path: Path = DEFAULT_DB_PATH
    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


def load_config(courses_dir: str | None = None, db_path: str | None = None) -> Config:
    return Config(
        courses_dir=Path(courses_dir or os.getenv("MOODLE_COURSES_DIR", DEFAULT_COURSES_DIR)).expanduser(),
        db_path=Path(db_path or os.getenv("MOODLE_SEARCH_DB", DEFAULT_DB_PATH)).expanduser(),
        embedding_provider=os.getenv("MOODLE_EMBEDDING_PROVIDER", "local"),
        embedding_model=os.getenv("MOODLE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
    )
