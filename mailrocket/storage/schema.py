"""DDL: create / migrate the SQLite schema.

`init_db()` is idempotent (`CREATE TABLE IF NOT EXISTS`) and is invoked
explicitly by the `init-db` CLI subcommand or implicitly by the storage
layer when the DB file is missing.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from mailrocket.storage.connection import get_conn

logger = logging.getLogger(__name__)


_LINKEDIN_POSTS_DDL = """
CREATE TABLE IF NOT EXISTS linkedin_posts (
    uid INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT,
    author_name TEXT,
    profile_url TEXT,
    post_link TEXT NOT NULL UNIQUE,
    post_text TEXT,
    post_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    analysed BOOLEAN NOT NULL DEFAULT 0,
    other_data JSON,
    inserted_at TEXT DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%f', 'NOW', '+5 hours', '30 minutes'))
);
"""

_POST_ANALYSIS_DDL = """
CREATE TABLE IF NOT EXISTS post_analysis (
    analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_uid INTEGER NOT NULL,
    experience_gap INTEGER,
    match_percentage INTEGER,
    contact_email TEXT,
    contact_number TEXT,
    application_link TEXT,
    company_name TEXT,
    should_apply BOOLEAN,
    subject TEXT,
    body TEXT,
    mail_sent INTEGER NOT NULL DEFAULT -1 CHECK (mail_sent IN (-1, 0, 1)),
    final_decision BOOLEAN NOT NULL DEFAULT 0,
    full_analysis_json JSON,
    model_used TEXT,
    inserted_at TEXT DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%f', 'NOW', '+5 hours', '30 minutes')),
    FOREIGN KEY (post_uid) REFERENCES linkedin_posts(uid) ON DELETE CASCADE
);
"""


def init_db(db_path: Path | None = None) -> None:
    """Create tables if they don't exist."""
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(_LINKEDIN_POSTS_DDL)
        cur.execute(_POST_ANALYSIS_DDL)
        cur.close()
    logger.info("DB initialised at %s", db_path or "(default)")


def migrate_post_analysis_schema(db_path: Path | None = None) -> None:
    """One-shot migration that flips legacy mail_sent==0 to mail_sent==-1.

    Kept for compatibility with older DBs. Safe to skip on fresh installs.
    """
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF;")
        try:
            cur.execute("BEGIN TRANSACTION;")
            cur.execute("ALTER TABLE post_analysis RENAME TO post_analysis_old;")
            cur.execute(_POST_ANALYSIS_DDL)
            cur.execute(
                """
                INSERT INTO post_analysis (
                    analysis_id, post_uid, experience_gap, match_percentage,
                    contact_email, contact_number, application_link, company_name,
                    should_apply, subject, body, mail_sent,
                    full_analysis_json, model_used, inserted_at
                )
                SELECT
                    analysis_id, post_uid, experience_gap, match_percentage,
                    contact_email, contact_number, application_link, company_name,
                    should_apply, subject, body,
                    CASE mail_sent WHEN 0 THEN -1 ELSE mail_sent END,
                    full_analysis_json, model_used, inserted_at
                FROM post_analysis_old;
                """
            )
            cur.execute("DROP TABLE post_analysis_old;")
            cur.execute("COMMIT;")
            logger.info("Schema migration completed.")
        except sqlite3.Error:
            cur.execute("ROLLBACK;")
            raise
        finally:
            cur.execute("PRAGMA foreign_keys = ON;")
            cur.close()
