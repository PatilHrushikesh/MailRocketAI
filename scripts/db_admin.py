"""One-off DB administration commands kept out of the library proper.

Usage:
    python scripts/db_admin.py raw "SELECT count(*) FROM linkedin_posts;"
    python scripts/db_admin.py remove --no-backup
    python scripts/db_admin.py mark-sent --from urls.txt
    python scripts/db_admin.py count-by-date
    python scripts/db_admin.py migrate
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mailrocket.logging_setup import configure_logging  # noqa: E402
from mailrocket.settings import settings  # noqa: E402
from mailrocket.storage.connection import get_conn  # noqa: E402
from mailrocket.storage.schema import migrate_post_analysis_schema  # noqa: E402


def run_raw_sql_query(query: str) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    print(json.dumps(rows, indent=2, sort_keys=True, default=str))
    return rows


def remove_db(backup: bool = True) -> None:
    db_path = settings.paths.db
    if not db_path.exists():
        print(f"Database file {db_path} does not exist.")
        return

    if backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.with_name(f"{db_path.name}.backup_{timestamp}")
        shutil.copy2(db_path, backup_path)
        print(f"Backup created at: {backup_path}")

    os.remove(db_path)
    print(f"Removed database: {db_path}")


def mark_mail_sent_if_url_matches(url_file: Path) -> None:
    """Mark mail_sent=1 for analyses whose linkedin_posts.post_link is in the file."""
    if not url_file.exists():
        print(f"File {url_file} not found.")
        return

    urls = {line.strip() for line in url_file.read_text(encoding="utf-8").splitlines() if line.strip()}
    if not urls:
        print("No URLs to process.")
        return

    placeholders = ",".join(["?"] * len(urls))
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT pa.post_uid FROM post_analysis pa
            JOIN linkedin_posts lp ON pa.post_uid = lp.uid
            WHERE lp.post_link IN ({placeholders}) AND pa.mail_sent = 0;
            """,
            list(urls),
        )
        post_uids = [r[0] for r in cur.fetchall()]
        if not post_uids:
            print("No matching post_uids.")
            cur.close()
            return

        cur.execute(
            f"UPDATE post_analysis SET mail_sent = 1 WHERE post_uid IN ({','.join(['?'] * len(post_uids))});",
            post_uids,
        )
        print(f"Updated {cur.rowcount} rows to mail_sent = 1.")
        cur.close()


def count_unsent_by_date() -> None:
    from mailrocket.storage.analysis_repo import count_unsent_by_date as _impl

    rows = _impl()
    print(json.dumps(rows, indent=2, sort_keys=True))


def main() -> None:
    configure_logging(settings.logging.level, settings.logging.file)

    p = argparse.ArgumentParser(description="MailRocket DB admin")
    sub = p.add_subparsers(dest="cmd", required=True)

    raw = sub.add_parser("raw", help="Run a raw SELECT")
    raw.add_argument("sql")

    rm = sub.add_parser("remove", help="Remove the DB file")
    rm.add_argument("--no-backup", action="store_true")

    ms = sub.add_parser("mark-sent", help="Mark mail_sent=1 for URLs in a file")
    ms.add_argument("--from", dest="url_file", required=True, type=Path)

    sub.add_parser("count-by-date", help="Print unsent counts grouped by day")
    sub.add_parser("migrate", help="One-shot mail_sent legacy migration")

    args = p.parse_args()

    if args.cmd == "raw":
        run_raw_sql_query(args.sql)
    elif args.cmd == "remove":
        remove_db(backup=not args.no_backup)
    elif args.cmd == "mark-sent":
        mark_mail_sent_if_url_matches(args.url_file)
    elif args.cmd == "count-by-date":
        count_unsent_by_date()
    elif args.cmd == "migrate":
        migrate_post_analysis_schema()


if __name__ == "__main__":
    main()
