"""SQLite connection helper used by every repo function.

Always go through `get_conn()` so we get consistent foreign-key enforcement,
row-as-dict access, and proper commit/rollback semantics.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from mailrocket.settings import settings


@contextmanager
def get_conn(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path) if db_path else settings.paths.db
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
