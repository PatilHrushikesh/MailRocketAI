"""Three-stage pipeline. Each stage uses the DB as its queue:

    scrape  : new posts -> linkedin_posts (analysed=0)
    analyze : analysed=0 posts -> post_analysis (mail_sent=-1) + analysed=1
    send    : mail_sent=-1 analyses -> Gmail; mail_sent=1 (sent) or 0 (rejected)

The stages are deliberately independent so they can be run on different
schedules, e.g. `pipeline` (scrape+analyze) during the day and `send` once
in the morning for visibility.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time

from mailrocket.settings import settings
from mailrocket.storage import init_db
from mailrocket.storage.analysis_repo import (
    fetch_pending_emails,
    insert_analysis,
    mark_mail_sent,
)
from mailrocket.storage.posts_repo import (
    insert_post,
    mark_analyzed,
    read_unanalyzed,
)

logger = logging.getLogger(__name__)


def _ensure_db() -> None:
    if not settings.paths.db.exists():
        logger.info("DB not found at %s; initialising", settings.paths.db)
        init_db()


def run_scrape() -> int:
    """Stage 1: scrape LinkedIn and insert posts. Returns count of new posts."""
    from mailrocket.scraper.linkedin import scrape_linkedin_feed

    _ensure_db()
    inserted = 0
    for post in scrape_linkedin_feed():
        try:
            insert_post(post)
            inserted += 1
        except sqlite3.IntegrityError:
            logger.info("Duplicate post skipped: %s", post.get("post_link"))
        except Exception:
            logger.exception("Failed to insert post: %s", post.get("post_link"))
        time.sleep(settings.scraper.per_query_delay_seconds)
    logger.info("Scrape stage finished. New posts: %d", inserted)
    return inserted


def run_analyze() -> int:
    """Stage 2: pick `analysed=0` posts, run LLM, persist analyses. Returns count analyzed."""
    from mailrocket.analyzer.service import analyze_job_match

    _ensure_db()
    pending = read_unanalyzed()
    logger.info("Found %d posts pending analysis", len(pending))

    analyzed = 0
    for post in pending:
        try:
            jobs_text = post.get("post_text") or ""
            if not jobs_text:
                logger.info("Skipping post uid=%s with empty post_text", post["uid"])
                mark_analyzed(post["uid"])
                continue

            results, model_info = analyze_job_match(jobs_text)
            insert_analysis(post["uid"], results, model_used=model_info.get("name"))
            analyzed += 1
        except Exception:
            logger.exception("Analysis failed for post uid=%s", post.get("uid"))

    logger.info("Analyze stage finished. Posts analyzed: %d", analyzed)
    return analyzed


def _decorate_with_postfix_and_closer(analysis: dict) -> dict:
    """Apply the configured subject postfix and body closer if not already present."""
    msg = analysis.get("message_content") or {}
    subject = msg.get("subject") or ""
    body = msg.get("body") or ""

    if subject and settings.email.subject_postfix and settings.email.subject_postfix not in subject:
        subject = subject + settings.email.subject_postfix

    if body and settings.email.body_closer and settings.candidate.phone_number not in body:
        body = body + "\n" + settings.email.body_closer

    analysis["message_content"] = {"subject": subject, "body": body}
    return analysis


def run_send(dry_run: bool = False) -> tuple[int, int]:
    """Stage 3: send pending analyses. Returns (sent_count, rejected_count)."""
    from mailrocket.mailer.service import decide_and_send_email

    _ensure_db()
    rows = fetch_pending_emails()
    if not rows:
        logger.info("No pending emails to send")
        return (0, 0)

    logger.info("Found %d pending analyses; %s", len(rows), "dry-run" if dry_run else "sending")

    sent_count = 0
    rejected_count = 0

    for row in rows:
        try:
            analysis = json.loads(row["full_analysis_json"]) if row["full_analysis_json"] else {}
            analysis["model_name"] = row["model_used"] or "N/A"

            contact_email_raw = row["contact_email"]
            try:
                analysis["contact_email"] = json.loads(contact_email_raw) if contact_email_raw else []
            except (TypeError, json.JSONDecodeError):
                analysis["contact_email"] = []

            analysis["message_content"] = {
                "subject": row["subject"] or analysis.get("message_content", {}).get("subject"),
                "body": row["body"] or analysis.get("message_content", {}).get("body"),
            }

            if not analysis["message_content"]["subject"] or not analysis["message_content"]["body"]:
                logger.info("Skipping analysis_id=%s: empty subject/body", row["analysis_id"])
                if not dry_run:
                    mark_mail_sent(row["analysis_id"], False)
                rejected_count += 1
                continue

            analysis = _decorate_with_postfix_and_closer(analysis)
            job_post = {"post_link": row["post_link"]}

            sent, reason = decide_and_send_email(analysis, job_post, dry_run=dry_run)
            logger.info("[%s] %s", row["analysis_id"], reason)

            if not dry_run:
                mark_mail_sent(row["analysis_id"], sent)
            if sent:
                sent_count += 1
            else:
                rejected_count += 1

            time.sleep(2)
        except Exception:
            logger.exception("Error processing analysis_id=%s", row.get("analysis_id"))

    logger.info("Send stage finished. sent=%d rejected=%d", sent_count, rejected_count)
    return sent_count, rejected_count


def run_pipeline() -> tuple[int, int]:
    """Daily-use combo: scrape + analyze (no send). Returns (new_posts, analyzed)."""
    new_posts = run_scrape()
    analyzed = run_analyze()
    return new_posts, analyzed


def run_all(dry_run: bool = False) -> tuple[int, int, int, int]:
    """Full pipeline. Returns (new_posts, analyzed, sent, rejected)."""
    new_posts = run_scrape()
    analyzed = run_analyze()
    sent, rejected = run_send(dry_run=dry_run)
    return new_posts, analyzed, sent, rejected
