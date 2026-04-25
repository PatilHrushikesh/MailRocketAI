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


SORT_OPTIONS: dict[str, str] = {
    "latest":     "lp.post_date DESC, lp.uid DESC",
    "oldest":     "lp.post_date ASC, lp.uid ASC",
    # NULL match_percentage (unanalyzed posts) bubble to the bottom
    # regardless of direction.
    "match_desc": "(pa.match_percentage IS NULL), pa.match_percentage DESC, lp.uid DESC",
    "match_asc":  "(pa.match_percentage IS NULL), pa.match_percentage ASC, lp.uid DESC",
}


def list_posts_for_ui(
    *,
    status: str = "all",
    query: str | None = None,
    min_match: int = 0,
    company: str | None = None,
    sort: str = "latest",
    limit: int = 500,
    db_path: Path | None = None,
) -> list[dict]:
    """List posts joined with their *latest* analysis summary, for the UI grid.

    `status` is one of:
        all        -> every post
        unanalyzed -> analysed = 0 (no analysis yet)
        pending    -> latest analysis has mail_sent = -1 (drafts to review)
        sent       -> latest analysis has mail_sent = 1
        rejected   -> latest analysis has mail_sent = 0 (skipped/failed)

    The four non-`all` statuses form a partition: every post falls in
    exactly one of them, so their counts sum to `all`.

    Additional filters:
        `query`     case-insensitive substring across post_text, author_name,
                    LinkedIn search query, and company_name.
        `min_match` keep only posts whose latest match_percentage >= min_match
                    (0 disables; unanalyzed posts are excluded when > 0).
        `company`   case-insensitive substring on company_name.
        `sort`      one of `latest`, `oldest`, `match_desc`, `match_asc`.
    """
    sql = """
        SELECT
            lp.uid,
            lp.query,
            lp.author_name,
            lp.profile_url,
            lp.post_link,
            lp.post_text,
            lp.post_date,
            lp.analysed,
            lp.inserted_at,
            pa.analysis_id,
            pa.match_percentage,
            pa.experience_gap,
            pa.company_name,
            pa.should_apply,
            pa.mail_sent,
            pa.final_decision
        FROM linkedin_posts lp
        LEFT JOIN post_analysis pa ON pa.analysis_id = (
            SELECT analysis_id FROM post_analysis
            WHERE post_uid = lp.uid
            ORDER BY analysis_id DESC LIMIT 1
        )
    """
    where: list[str] = []
    params: list[Any] = []

    if status == "unanalyzed":
        where.append("lp.analysed = 0")
    elif status == "pending":
        where.append("pa.mail_sent = -1")
    elif status == "sent":
        where.append("pa.mail_sent = 1")
    elif status == "rejected":
        where.append("pa.mail_sent = 0")

    if query:
        where.append(
            "(LOWER(lp.post_text) LIKE ? OR LOWER(lp.author_name) LIKE ? "
            "OR LOWER(lp.query) LIKE ? OR LOWER(COALESCE(pa.company_name, '')) LIKE ?)"
        )
        like = f"%{query.lower()}%"
        params.extend([like, like, like, like])

    if min_match and int(min_match) > 0:
        where.append("pa.match_percentage >= ?")
        params.append(int(min_match))

    if company:
        where.append("LOWER(COALESCE(pa.company_name, '')) LIKE ?")
        params.append(f"%{company.lower().strip()}%")

    if where:
        sql += " WHERE " + " AND ".join(where)

    order_by = SORT_OPTIONS.get(sort, SORT_OPTIONS["latest"])
    sql += f" ORDER BY {order_by} LIMIT ?;"
    params.append(int(limit))

    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return rows


def list_distinct_companies(db_path: Path | None = None) -> list[str]:
    """Distinct, non-empty company names — used for the company autocomplete."""
    sql = """
        SELECT DISTINCT TRIM(company_name) AS name
        FROM post_analysis
        WHERE company_name IS NOT NULL AND TRIM(company_name) != ''
        ORDER BY LOWER(name);
    """
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        names = [r[0] for r in cur.fetchall()]
        cur.close()
    return names


def fetch_post_with_analyses(uid: int, db_path: Path | None = None) -> dict | None:
    """Return one post (with parsed `other_data`) plus all its analyses (newest first).

    Shape: {"post": {...}, "analyses": [{...}, ...]}
    Returns None if the post doesn't exist.
    """
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM linkedin_posts WHERE uid = ?;", (uid,))
        row = cur.fetchone()
        if row is None:
            cur.close()
            return None
        post = dict(row)
        if post.get("other_data"):
            try:
                post["other_data"] = json.loads(post["other_data"])
            except json.JSONDecodeError:
                pass

        cur.execute(
            "SELECT * FROM post_analysis WHERE post_uid = ? ORDER BY analysis_id DESC;",
            (uid,),
        )
        analyses = [dict(r) for r in cur.fetchall()]
        cur.close()

    for a in analyses:
        for key in ("contact_email", "contact_number", "application_link"):
            raw = a.get(key)
            if isinstance(raw, str):
                try:
                    a[key] = json.loads(raw)
                except json.JSONDecodeError:
                    a[key] = [raw] if raw else []
            elif raw is None:
                a[key] = []
        full = a.get("full_analysis_json")
        if isinstance(full, str):
            try:
                a["full_analysis_json"] = json.loads(full)
            except json.JSONDecodeError:
                pass

    return {"post": post, "analyses": analyses}
