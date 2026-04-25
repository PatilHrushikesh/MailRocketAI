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
        raise TypeError(
            f"analysis_list must be a list of dicts, got {type(analysis_list).__name__}"
        )
    if not all(isinstance(a, dict) for a in analysis_list):
        bad_types = sorted({type(a).__name__ for a in analysis_list if not isinstance(a, dict)})
        raise TypeError(
            f"analysis_list must contain only dicts; found {bad_types}"
        )

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


_EDITABLE_FIELDS: dict[str, str] = {
    "subject": "scalar",
    "body": "scalar",
    "company_name": "scalar",
    "match_percentage": "int",
    "experience_gap": "int",
    "should_apply": "bool",
    "final_decision": "bool",
    "mail_sent": "mail_sent",
    "contact_email": "json_list",
    "contact_number": "json_list",
    "application_link": "json_list",
}


def _coerce(field: str, kind: str, value: Any) -> Any:
    if kind == "scalar":
        return value if value is not None else None
    if kind == "int":
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{field} must be an integer") from e
    if kind == "bool":
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            return 1 if value else 0
        s = str(value).strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return 1
        if s in ("0", "false", "no", "n", "off", ""):
            return 0
        raise ValueError(f"{field} must be a boolean")
    if kind == "mail_sent":
        try:
            iv = int(value)
        except (TypeError, ValueError) as e:
            raise ValueError("mail_sent must be -1, 0 or 1") from e
        if iv not in (-1, 0, 1):
            raise ValueError("mail_sent must be -1, 0 or 1")
        return iv
    if kind == "json_list":
        if value is None:
            return json.dumps([])
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return json.dumps([])
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return json.dumps([str(x).strip() for x in parsed if str(x).strip()])
            except json.JSONDecodeError:
                pass
            items = [p.strip() for p in stripped.replace("\n", ",").split(",")]
            return json.dumps([p for p in items if p])
        if isinstance(value, list):
            return json.dumps([str(x).strip() for x in value if str(x).strip()])
        raise ValueError(f"{field} must be a list or comma-separated string")
    raise ValueError(f"Unknown coercion kind: {kind}")


def update_analysis(
    analysis_id: int,
    fields: dict[str, Any],
    db_path: Path | None = None,
) -> int:
    """Update a whitelisted set of fields on a `post_analysis` row.

    Returns the number of rows updated (0 or 1). Raises ValueError if the
    payload contains an unknown field or a value that fails coercion.
    """
    if not isinstance(fields, dict):
        raise TypeError("fields must be a dict")

    unknown = [k for k in fields if k not in _EDITABLE_FIELDS]
    if unknown:
        raise ValueError(f"Unknown field(s): {unknown}")

    if not fields:
        return 0

    set_clauses: list[str] = []
    params: list[Any] = []
    for name, raw in fields.items():
        coerced = _coerce(name, _EDITABLE_FIELDS[name], raw)
        set_clauses.append(f"{name} = ?")
        params.append(coerced)
    params.append(int(analysis_id))

    sql = f"UPDATE post_analysis SET {', '.join(set_clauses)} WHERE analysis_id = ?;"

    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rowcount = cur.rowcount
        cur.close()
    logger.info("Updated analysis_id=%d (%d row[s])", analysis_id, rowcount)
    return rowcount


def status_counts(db_path: Path | None = None) -> dict[str, int]:
    """Counts used by the UI sidebar (all, unanalyzed, pending, sent, rejected).

    The four non-`all` buckets are mutually exclusive and exhaustive, so:

        all == unanalyzed + pending + sent + rejected

    `pending`/`sent`/`rejected` look at each post's *latest* analysis only,
    so the pill numbers always equal the number of rows the corresponding
    filter renders.
    """
    sql = """
        WITH latest AS (
            SELECT pa.* FROM post_analysis pa
            WHERE pa.analysis_id = (
                SELECT MAX(analysis_id) FROM post_analysis pa2
                WHERE pa2.post_uid = pa.post_uid
            )
        )
        SELECT
            (SELECT COUNT(*) FROM linkedin_posts) AS all_posts,
            (SELECT COUNT(*) FROM linkedin_posts WHERE analysed = 0) AS unanalyzed,
            (SELECT COUNT(*) FROM latest WHERE mail_sent = -1) AS pending,
            (SELECT COUNT(*) FROM latest WHERE mail_sent = 1) AS sent,
            (SELECT COUNT(*) FROM latest WHERE mail_sent = 0) AS rejected;
    """
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        cur.close()
    return {
        "all": row["all_posts"] or 0,
        "unanalyzed": row["unanalyzed"] or 0,
        "pending": row["pending"] or 0,
        "sent": row["sent"] or 0,
        "rejected": row["rejected"] or 0,
    }


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
