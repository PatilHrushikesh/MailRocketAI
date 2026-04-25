"""Resume vs. job-post analyzer.

Public surface: `analyze_job_match(jobs_text)` — returns
`(list_of_analysis_dicts, model_info_used)`.
"""
from __future__ import annotations

import logging
import time
import traceback
from typing import Tuple

from langchain_core.output_parsers import JsonOutputParser

from mailrocket.analyzer.llm import get_llm, model_cycle
from mailrocket.analyzer.prompts import (
    build_prompt,
    load_email_tailoring_instructions,
    load_message_content,
    load_resume_text,
)
from mailrocket.settings import settings

logger = logging.getLogger(__name__)


_MODEL_ITER = None


def _get_iter():
    global _MODEL_ITER
    if _MODEL_ITER is None:
        _MODEL_ITER = model_cycle()
    return _MODEL_ITER


def _invoke(prompt, params: dict) -> Tuple[list, dict]:
    """Try models in order; return the first successful (parsed_result, model_info)."""
    models = list(settings.llm.models)
    if not models:
        raise RuntimeError("No LLM models configured")

    iterator = _get_iter()
    last_model = models[0]

    for attempt in range(len(models)):
        current = next(iterator)
        last_model = current
        logger.info("Invoking %s/%s (attempt %d)", current["provider"], current["name"], attempt + 1)
        try:
            llm = get_llm(current)
            chain = prompt | llm | JsonOutputParser()
            result = chain.invoke(params)
            return ([result] if isinstance(result, dict) else result), current
        except Exception as e:
            logger.warning("Model %s failed: %s", current["name"], e)
            logger.debug("Traceback: %s", traceback.format_exc())
            continue

    error_result = [{
        "model_name": last_model["name"],
        "original_job_text": params.get("jobs", ""),
        "error": "All models failed",
        "status": "failed",
        "timestamp": time.time(),
    }]
    return error_result, last_model


def analyze_job_match(jobs_text: str) -> Tuple[list, dict]:
    """Analyze how well the configured resume matches a job-posting blob."""
    logger.info("Starting job match analysis")

    prompt, full_template = build_prompt()
    params = {
        "response_template": full_template,
        "resume": load_resume_text(),
        "jobs": jobs_text,
        "messege_content": load_message_content(),
        "messege_content_tailoring_instructions": load_email_tailoring_instructions(),
        "resume_url": settings.candidate.resume_url,
        "linkedin_profile_url": settings.candidate.linkedin_profile_url,
    }

    result, model_info = _invoke(prompt, params)
    logger.info("Analysis complete using %s/%s", model_info["provider"], model_info["name"])
    return result, model_info
