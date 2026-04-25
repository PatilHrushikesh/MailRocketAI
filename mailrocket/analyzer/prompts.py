"""Build the langchain prompt used by the analyzer service."""
from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)

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


def build_prompt() -> tuple[ChatPromptTemplate, str]:
    """Return (chat prompt template, full response template string).

    Reads from `prompts/` on every call; cheap, and keeps things stateless.
    """
    prompts_dir = settings.paths.prompts_dir
    response_template = _read_text(prompts_dir / "resume_analysis.txt")
    json_structure = _read_text(prompts_dir / "output_schema.json")
    full_template = response_template + json_structure

    system = SystemMessagePromptTemplate.from_template(SYSTEM_TEMPLATE)
    human = HumanMessagePromptTemplate.from_template(USER_TEMPLATE)
    chat = ChatPromptTemplate.from_messages([system, human])
    return chat, full_template


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
