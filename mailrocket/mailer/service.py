"""Mailer orchestration: decide -> send -> log -> bookkeeping."""
from __future__ import annotations

import logging
import time
from typing import Callable

from mailrocket.mailer.decisions import should_send_email
from mailrocket.mailer.gmail import send_email_via_gmail_api
from mailrocket.settings import settings

logger = logging.getLogger(__name__)


SendFunc = Callable[..., dict]


def decide_and_send_email(
    job_data: dict,
    job_post: dict,
    *,
    send_func: SendFunc | None = None,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Decide whether to send the prepared draft for `job_data`, then send it.

    Returns (sent, reason). `sent` is True only if at least one email actually
    went out (or would have gone out, in dry-run mode).
    """
    send_func = send_func or send_email_via_gmail_api

    ok, reason = should_send_email(job_data)
    if not ok:
        logger.info("Skip post=%s reason=%s", job_post.get("post_link"), reason)
        return False, reason

    subject = job_data["message_content"]["subject"]
    body = job_data["message_content"]["body"]
    contact_emails = job_data["contact_email"]
    from_mail = settings.email.from_mail
    pdf_path = settings.paths.resume_pdf if settings.paths.resume_pdf and settings.paths.resume_pdf.exists() else None

    logger.info(
        "Drafted email subject=%r recipients=%d post=%s",
        subject, len(contact_emails), job_post.get("post_link"),
    )

    if dry_run:
        logger.info("[dry-run] Would send to %s from %s", contact_emails, from_mail)
        return True, f"dry-run: would send to {len(contact_emails)} recipients"

    sent_count = 0
    for email in contact_emails:
        try:
            send_func(subject, body, email, from_mail, pdf_file_path=pdf_path)
            sent_count += 1
            logger.info("Sent to %s", email)
        except Exception:
            logger.exception("Failed to send to %s", email)

    if sent_count == 0:
        return False, "All recipients failed"

    if settings.email.self_review_mail:
        review_body = (
            body
            + "\n\nMail Sent to "
            + ", ".join(contact_emails)
            + f".\nJob Post URL: {job_post.get('post_link', '')}\n"
            f"AI Model Used: {job_data.get('model_name', 'N/A')}\n"
        )
        try:
            send_func(subject, review_body, settings.email.self_review_mail, from_mail, pdf_file_path=pdf_path)
            logger.info("Self-review copy sent to %s", settings.email.self_review_mail)
        except Exception:
            logger.exception("Failed to send self-review copy")

    time.sleep(2)
    return True, f"Sent to {sent_count}/{len(contact_emails)} recipients"
