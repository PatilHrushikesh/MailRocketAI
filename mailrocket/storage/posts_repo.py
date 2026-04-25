"""CRUD for the `linkedin_posts` table."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from mailrocket.storage.connection import get_conn

logger = logging.getLogger(__name__)


def insert_post(post_data: dict[str, Any], db_path: Path | None = None) -> int:
    """Insert a scraped post; raises sqlite3.IntegrityError on duplicate post_link."""
    data = dict(post_data)
    if isinstance(data.get("post_date"), datetime):
        data["post_date"] = data["post_date"].isoformat()

    other_data_json = json.dumps(data, default=str)

    with get_conn(db_path) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO linkedin_posts
                    (query, post_link, post_text, post_date, author_name, profile_url, other_data)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data.get("query"),
                    data.get("post_link"),
                    data.get("post_text"),
                    data.get("post_date"),
                    data.get("author_name"),
                    data.get("profile_url"),
                    other_data_json,
                ),
            )
            uid = cur.lastrowid
            logger.info("Inserted post uid=%d", uid)
            return uid
        except sqlite3.IntegrityError as e:
            raise sqlite3.IntegrityError(
                f"Duplicate post_link '{data.get('post_link')}'"
            ) from e
        finally:
            cur.close()


def check_post_exists(post_link: str, db_path: Path | None = None) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM linkedin_posts WHERE post_link = ? LIMIT 1;", (post_link,))
        found = cur.fetchone() is not None
        cur.close()
    return found


def read_posts(filters: dict[str, Any] | None = None, db_path: Path | None = None) -> list[dict]:
    """Generic read with whitelisted equality filters."""
    allowed = {"uid", "query", "post_link", "post_text", "analysed", "post_date"}
    filters = filters or {}
    for k in filters:
        if k not in allowed:
            raise ValueError(f"Invalid filter key: {k}")

    sql = "SELECT * FROM linkedin_posts"
    params: list[Any] = []
    if filters:
        sql += " WHERE " + " AND ".join(f"{k} = ?" for k in filters)
        params.extend(filters.values())

    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()

    for r in rows:
        if r.get("other_data"):
            try:
                r["other_data"] = json.loads(r["other_data"])
            except json.JSONDecodeError:
                pass
    return rows


def read_unanalyzed(db_path: Path | None = None) -> list[dict]:
    return read_posts(filters={"analysed": 0}, db_path=db_path)


def mark_analyzed(uid: int, db_path: Path | None = None) -> None:
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE linkedin_posts SET analysed = 1 WHERE uid = ?;", (uid,))
        cur.close()
