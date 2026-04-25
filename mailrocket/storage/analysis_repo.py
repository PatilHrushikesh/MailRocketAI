"""CRUD for the `post_analysis` table."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mailrocket.storage.connection import get_conn

logger = logging.getLogger(__name__)


def insert_analysis(
    post_uid: int,
    analysis_list: list[dict],
    model_used: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert analysis rows for a given post and mark the post analysed.

    Returns the number of rows inserted.
    """
    if not isinstance(analysis_list, list):
        raise TypeError("analysis_list must be a list of dicts")

    inserted = 0
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        for a in analysis_list:
            resolved_model = model_used or a.get("model_name", "unknown")
            cur.execute(
                """
                INSERT INTO post_analysis (
                    post_uid, match_percentage, experience_gap,
                    contact_email, contact_number, application_link,
                    company_name, should_apply, subject, body,
                    mail_sent, full_analysis_json, model_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    post_uid,
                    a.get("match_percentage"),
                    a.get("experience_gap"),
                    json.dumps(a.get("contact_email")),
                    json.dumps(a.get("contact_number")),
                    json.dumps(a.get("application_link")),
                    a.get("company_name"),
                    a.get("should_apply"),
                    a.get("message_content", {}).get("subject"),
                    a.get("message_content", {}).get("body"),
                    -1,
                    json.dumps(a, default=str),
                    resolved_model,
                ),
            )
            inserted += 1

        cur.execute("UPDATE linkedin_posts SET analysed = 1 WHERE uid = ?;", (post_uid,))
        cur.close()

    logger.info("Inserted %d analysis row(s) for post_uid=%d", inserted, post_uid)
    return inserted


def fetch_pending_emails(db_path: Path | None = None) -> list[dict]:
    """Return joined rows for analyses where mail_sent = -1 (i.e. not yet attempted)."""
    sql = """
        SELECT pa.*, lp.post_link
        FROM post_analysis pa
        JOIN linkedin_posts lp ON pa.post_uid = lp.uid
        WHERE pa.mail_sent = -1;
    """
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return rows


def mark_mail_sent(analysis_id: int, sent: bool, db_path: Path | None = None) -> None:
    """Set `mail_sent` to 1 (sent) or 0 (rejected/failed)."""
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE post_analysis SET mail_sent = ? WHERE analysis_id = ?;",
            (1 if sent else 0, analysis_id),
        )
        cur.close()


def count_unsent(db_path: Path | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM post_analysis WHERE mail_sent = -1;")
        count = cur.fetchone()[0]
        cur.close()
    return count


def count_unsent_by_date(db_path: Path | None = None) -> list[dict]:
    sql = """
    WITH RECURSIVE last_20_days(day) AS (
        SELECT DATE('now', '-19 days')
        UNION ALL
        SELECT DATE(day, '+1 day') FROM last_20_days WHERE day < DATE('now')
    )
    SELECT
        last_20_days.day AS insertion_date,
        COUNT(DISTINCT linkedin_posts.uid) AS unsent_mail_post_count
    FROM last_20_days
    LEFT JOIN linkedin_posts
        ON DATE(linkedin_posts.inserted_at) = last_20_days.day
    LEFT JOIN post_analysis
        ON post_analysis.post_uid = linkedin_posts.uid AND post_analysis.mail_sent = -1
    GROUP BY last_20_days.day
    ORDER BY last_20_days.day DESC;
    """
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return rows
