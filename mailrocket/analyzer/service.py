"""Resume vs. job-post analyzer.

Public surface: `analyze_job_match(jobs_text, *, trace_metadata=None)` —
returns `(list_of_analysis_dicts, model_info_used)`.

Trace metadata: when Langfuse keys are configured, each LLM call is traced.
The optional `trace_metadata` dict is merged into the per-call metadata so
the resulting Langfuse trace knows which post we were analysing (post_uid,
post_link, etc.). When Langfuse keys are absent the metadata is simply
ignored by the no-op callback path.
"""
from __future__ import annotations

import logging
import time
import traceback
import uuid
from typing import Any

from mailrocket.analyzer.llm import complete_json, model_cycle
from mailrocket.analyzer.prompts import build_messages, load_resume_text
from mailrocket.settings import settings

logger = logging.getLogger(__name__)


# One Langfuse session per Python process. Lets us see, in the Langfuse UI,
# every post processed during a single `make pipeline` / `make analyze` run
# grouped together.
_RUN_ID = f"mailrocket-{uuid.uuid4().hex[:12]}"

_MODEL_ITER = None


def _get_iter():
    global _MODEL_ITER
    if _MODEL_ITER is None:
        _MODEL_ITER = model_cycle()
    return _MODEL_ITER


def _normalize_result(result) -> list[dict] | None:
    """Coerce the parsed LLM output into a list-of-dicts.

    Returns None if the shape isn't recognisable (caller should treat as a
    model failure and try the next one).
    """
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        dicts = [r for r in result if isinstance(r, dict)]
        return dicts or None
    return None


def _build_trace_metadata(
    attempt: int,
    model_info: dict,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compose the metadata dict LiteLLM forwards to Langfuse.

    Recognised keys (per LiteLLM docs): generation_name, trace_id,
    trace_user_id, session_id, tags. Everything else is preserved as
    free-form metadata in the trace.
    """
    extra = extra or {}
    trace_id = (
        extra.get("trace_id")
        or extra.get("post_link")
        or (f"post-{extra.get('post_uid')}" if extra.get("post_uid") else None)
        or f"adhoc-{uuid.uuid4().hex[:8]}"
    )
    prompt_version = extra.get("prompt_version", "unknown")
    return {
        "generation_name": f"analyze_job_match[attempt={attempt}]",
        "trace_id": trace_id,
        "session_id": _RUN_ID,
        "tags": [
            "mailrocket",
            "stage:analyze",
            f"provider:{model_info['provider']}",
            f"model:{model_info['name']}",
            f"prompt:{prompt_version}",
        ],
        "post_uid": extra.get("post_uid"),
        "post_link": extra.get("post_link"),
        "query": extra.get("query"),
        "prompt_version": prompt_version,
    }


def _invoke(
    messages: list[dict],
    *,
    trace_metadata: dict[str, Any] | None,
) -> tuple[list, dict]:
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
            metadata = _build_trace_metadata(attempt + 1, current, trace_metadata)
            parsed, _raw = complete_json(current, messages, metadata=metadata)
        except Exception as e:
            logger.warning("Model %s failed: %s", current["name"], e)
            logger.debug("Traceback: %s", traceback.format_exc())
            continue

        normalized = _normalize_result(parsed)
        if normalized is None:
            logger.warning(
                "Model %s returned unexpected shape %s; cycling to next model",
                current["name"], type(parsed).__name__,
            )
            continue
        return normalized, current

    error_result = [{
        "model_name": last_model["name"],
        "error": "All models failed",
        "status": "failed",
        "timestamp": time.time(),
    }]
    return error_result, last_model


def analyze_job_match(
    jobs_text: str,
    *,
    trace_metadata: dict[str, Any] | None = None,
) -> tuple[list, dict]:
    """Analyze how well the configured resume matches a job-posting blob.

    Args:
        jobs_text: The raw text of one (or several) LinkedIn job posts.
        trace_metadata: Optional dict with `post_uid`, `post_link`, `query`,
            etc. — forwarded into Langfuse so traces are searchable by post.
    """
    logger.info("Starting job match analysis")

    params = {
        "resume": load_resume_text(),
        "jobs": jobs_text,
    }
    messages, prompt_version = build_messages(params)

    if trace_metadata is None:
        trace_metadata = {}
    trace_metadata["prompt_version"] = prompt_version

    result, model_info = _invoke(messages, trace_metadata=trace_metadata)
    logger.info("Analysis complete using %s/%s", model_info["provider"], model_info["name"])
    return result, model_info
