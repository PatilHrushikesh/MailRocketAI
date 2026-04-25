"""Pure decision rules: should this LLM-produced draft actually be sent?

No I/O here. Returns (ok, reason).
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

from mailrocket.settings import settings

logger = logging.getLogger(__name__)


_EMAIL_RE = re.compile(
    r"""(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"""
    r"""|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]"""
    r"""|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")"""
    r"""@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"""
    r"""[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"""
    r"""|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"""
    r"""(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]"""
    r""":(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]"""
    r"""|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)])""",
    re.IGNORECASE,
)


def is_valid_email(email: str) -> bool:
    return _EMAIL_RE.fullmatch(email) is not None


def filter_valid_emails(emails: Iterable) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for e in emails:
        e = str(e)
        (valid if is_valid_email(e) else invalid).append(e)
    return valid, invalid


def should_send_email(job_data: dict) -> tuple[bool, str]:
    """Apply the configured filters to a single analysis dict."""
    if not isinstance(job_data, dict):
        raise TypeError("job_data must be a dict")

    email_list = job_data.get("contact_email") or []
    if not email_list:
        return False, "No contact email"

    valid, invalid = filter_valid_emails(email_list)
    if invalid:
        logger.info("Dropping %d invalid emails: %s", len(invalid), invalid)
    if not valid:
        return False, f"All emails invalid: {email_list}"

    try:
        match = float(job_data.get("match_percentage", 0))
    except (ValueError, TypeError) as e:
        raise TypeError("match_percentage must be numeric") from e

    if match <= settings.filters.match_threshold:
        return False, f"match {match}% <= {settings.filters.match_threshold}%"

    try:
        gap = float(job_data.get("experience_gap", 0))
    except (ValueError, TypeError) as e:
        raise TypeError("experience_gap must be numeric") from e

    if gap >= settings.filters.max_experience_gap:
        return False, f"experience_gap {gap}y >= {settings.filters.max_experience_gap}y"

    employment_type = str(job_data.get("additional_data", {}).get("employment_type", "")).lower()
    if employment_type in settings.filters.reject_employment_types:
        return False, f"employment_type rejected: {employment_type}"

    return True, "OK"
