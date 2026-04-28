"""Safe prompt interpolation that never crashes on user content.

Uses ``{{variable}}`` placeholders instead of Python's ``str.format()``
so that stray ``{`` / ``}`` characters in resumes, job posts, or any
other user-supplied text are left untouched.

Also provides utilities to strip XML-style closing tags from user blocks
(injection hardening) and to extract version headers from prompt files.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

_DANGEROUS_TAGS = re.compile(
    r"</?(RESUME|JOB_POSTINGS|CANDIDATE)>",
    re.IGNORECASE,
)


def render(template: str, variables: dict[str, Any]) -> str:
    """Replace ``{{name}}`` placeholders with values from *variables*.

    Unknown placeholders are left as-is (a warning is logged). Values are
    stringified via ``str()``.  Unlike ``str.format()``, literal braces in
    the template or in values never cause errors.
    """
    missing: set[str] = set()

    def _sub(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        missing.add(key)
        return match.group(0)

    result = _PLACEHOLDER_RE.sub(_sub, template)
    if missing:
        logger.warning("Unresolved prompt placeholders: %s", sorted(missing))
    return result


def strip_data_tags(text: str) -> str:
    """Remove XML-style data-block tags from user-supplied text.

    Prevents a malicious job post from injecting ``</JOB_POSTINGS>`` to
    break out of its data block.
    """
    return _DANGEROUS_TAGS.sub("", text)


_VERSION_RE = re.compile(r"<!--\s*version:\s*([\w.\-]+)\s*-->")


def extract_version(text: str) -> str:
    """Return the version string from an ``<!-- version: x.y.z -->`` header.

    Falls back to ``"unknown"`` if no header is found.
    """
    m = _VERSION_RE.search(text[:200])
    return m.group(1) if m else "unknown"
