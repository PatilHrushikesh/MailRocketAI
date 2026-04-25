"""CLI entry point. Run with `python -m mailrocket <command>`."""
from __future__ import annotations

import argparse
import logging
import sys

from mailrocket.logging_setup import configure_logging
from mailrocket.settings import settings

logger = logging.getLogger("mailrocket")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mailrocket",
        description="LinkedIn job-post -> resume-tailored email pipeline",
    )
    p.add_argument(
        "--log-level",
        default=None,
        help="Override config logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create the SQLite schema if missing")
    sub.add_parser("scrape", help="Scrape LinkedIn and insert new posts (no analysis, no send)")
    sub.add_parser("analyze", help="Run LLM on posts pending analysis (no send)")

    send = sub.add_parser(
        "send",
        help="Send pending emails (those with mail_sent = -1). Run this when you want visibility.",
    )
    send.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without contacting Gmail or updating mail_sent",
    )

    sub.add_parser(
        "pipeline",
        help="scrape + analyze (no send). Use during the day; review and send next morning.",
    )

    runall = sub.add_parser(
        "run-all",
        help="scrape + analyze + send in one shot",
    )
    runall.add_argument("--dry-run", action="store_true")

    ui = sub.add_parser(
        "ui",
        help="Launch the web review UI (read-only posts, editable analyses)",
    )
    ui.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    ui.add_argument("--port", type=int, default=8765, help="Port (default 8765)")
    ui.add_argument("--reload", action="store_true", help="Enable auto-reload (dev)")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    level = args.log_level or settings.logging.level
    configure_logging(level=level, log_file=settings.paths.log_file)

    logger.info("Command: %s", args.command)

    try:
        if args.command == "init-db":
            from mailrocket.storage.schema import init_db

            init_db()
            print(f"Initialised DB at {settings.paths.db}")
            return 0

        if args.command == "scrape":
            from mailrocket.pipeline import run_scrape

            n = run_scrape()
            print(f"Scraped and inserted {n} new posts.")
            return 0

        if args.command == "analyze":
            from mailrocket.pipeline import run_analyze

            n = run_analyze()
            print(f"Analyzed {n} posts.")
            return 0

        if args.command == "send":
            from mailrocket.pipeline import run_send

            sent, rejected = run_send(dry_run=args.dry_run)
            label = "[dry-run] " if args.dry_run else ""
            print(f"{label}Sent: {sent}, rejected: {rejected}")
            return 0

        if args.command == "pipeline":
            from mailrocket.pipeline import run_pipeline

            new_posts, analyzed = run_pipeline()
            print(f"Scraped {new_posts} posts; analyzed {analyzed}.")
            print("Run `mailrocket send` (or `make send`) when you're ready to mail.")
            return 0

        if args.command == "run-all":
            from mailrocket.pipeline import run_all

            n, a, s, r = run_all(dry_run=args.dry_run)
            label = "[dry-run] " if args.dry_run else ""
            print(f"{label}Scraped {n}, analyzed {a}, sent {s}, rejected {r}.")
            return 0

        if args.command == "ui":
            from mailrocket.ui import run as run_ui

            print(f"Serving review UI at http://{args.host}:{args.port}")
            run_ui(host=args.host, port=args.port, reload=args.reload)
            return 0

        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 130
    except Exception:
        logger.exception("Command failed: %s", args.command)
        return 1


if __name__ == "__main__":
    sys.exit(main())
