"""Build the chat messages used by the analyzer service.

This module used to depend on langchain's `ChatPromptTemplate`. Since
LiteLLM accepts the OpenAI-shaped `messages=[{role, content}, ...]`
list directly, we just produce that list with plain `str.format()` —
no template engine needed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mailrocket.settings import settings

logger = logging.getLogger(__name__)


SYSTEM_TEMPLATE = """RESUME ANALYSIS TASK
{response_template}

MESSEGE_CONTENT_TAILORING_INSTRUCTIONS:
{messege_content_tailoring_instructions}

RESUME_URL:
{resume_url}

LINKEDIN_PROFILE_URL:
{linkedin_profile_url}

STRICT JSON OUTPUT:"""


USER_TEMPLATE = """RESUME CONTENT:
{resume}

JOB POSTINGS:
{jobs}

MESSEGE_CONTENT:
{messege_content}"""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_response_template() -> str:
    """The schema-bearing part of the system prompt.

    Reads from `prompts/` on every call; cheap, and keeps things stateless.
    Returns the concatenation of `resume_analysis.txt` + `output_schema.json`.
    """
    prompts_dir = settings.paths.prompts_dir
    response_template = _read_text(prompts_dir / "resume_analysis.txt")
    json_structure = _read_text(prompts_dir / "output_schema.json")
    return response_template + json_structure


def build_messages(params: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    """Return (messages, full_response_template).

    `messages` is a chat-completions-shaped list ready to pass to LiteLLM.
    `full_response_template` is exposed separately because the service layer
    historically returned it for debugging; preserved for compatibility.
    """
    full_template = _load_response_template()
    fill = {**params, "response_template": full_template}

    messages = [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**fill)},
        {"role": "user", "content": USER_TEMPLATE.format(**fill)},
    ]
    return messages, full_template


def load_resume_text() -> str:
    return _read_text(settings.paths.resume_text)


def load_message_content() -> str:
    """The base email scaffold used when the LLM tailors the message.

    Historically this lived in a separate `messege_content.txt` file; with
    YAML config it's assembled from candidate + email defaults.
    """
    sig_lines = []
    if settings.candidate.full_name:
        sig_lines.append(f"Name: {settings.candidate.full_name}")
    if settings.candidate.phone_number:
        sig_lines.append(f"Phone: {settings.candidate.phone_number}")
    if settings.candidate.resume_url:
        sig_lines.append(f"Resume: {settings.candidate.resume_url}")
    if settings.candidate.linkedin_profile_url:
        sig_lines.append(f"LinkedIn: {settings.candidate.linkedin_profile_url}")
    return "\n".join(sig_lines)


def load_email_tailoring_instructions() -> str:
    return _read_text(settings.paths.prompts_dir / "email_tailoring.txt")
