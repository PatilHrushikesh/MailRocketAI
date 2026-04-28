"""LiteLLM-backed multi-provider chat client + optional Langfuse tracing.

Why this module exists:
    - The analyzer needs to talk to one of ~6 LLM providers (groq, google,
      openrouter, cerebras, mistral, github) and rotate across them when the
      currently-cycling one fails or is rate-limited.
    - LiteLLM gives us *one* call signature for all of them, plus retry
      semantics and a built-in Langfuse callback. That removes ~80 lines of
      provider-specific langchain glue this file used to carry.
    - When Langfuse keys are present, every call (success or failure) is
      automatically traced: prompt, response, latency, token usage, cost,
      and any metadata we attach. When the keys are absent, the callbacks
      are simply not registered and the system runs unchanged.

The list of models is configured in `config/config.yaml` under `llm.models`
as `(provider, name)` tuples. We translate each into the LiteLLM-style
`<provider>/<name>` model identifier and pass the right API key.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import re
import threading
from collections.abc import Iterable, Iterator
from typing import Any

import jsonschema
import litellm

from mailrocket.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output schema validation
# ---------------------------------------------------------------------------

_SCHEMA: dict | None = None


def _load_output_schema() -> dict | None:
    """Load the JSON Schema from prompts/v1/output_schema.json for validation."""
    global _SCHEMA
    if _SCHEMA is not None:
        return _SCHEMA
    schema_path = settings.paths.prompts_dir / "v1" / "output_schema.json"
    if not schema_path.exists():
        logger.debug("No v1 output_schema.json found; schema validation disabled")
        return None
    try:
        _SCHEMA = json.loads(schema_path.read_text(encoding="utf-8"))
        return _SCHEMA
    except Exception:
        logger.warning("Failed to load output schema; validation disabled", exc_info=True)
        return None


class SchemaValidationError(RuntimeError):
    """Raised when the LLM response doesn't conform to the output schema."""


# ---------------------------------------------------------------------------
# One-time Langfuse + LiteLLM setup
# ---------------------------------------------------------------------------

_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def _init_litellm() -> None:
    """Configure LiteLLM (and Langfuse, if keys are present) exactly once.

    Safe to call from any thread; no-op after the first call.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INIT_LOCK:
        if _INITIALIZED:
            return

        # Don't let a single failing provider take the whole pipeline down.
        # LiteLLM raises on 4xx/5xx by default, which is what we want — the
        # caller (`service.py`) catches and rotates. We only adjust logging.
        litellm.set_verbose = False
        litellm.drop_params = True  # silently drop unsupported kwargs per provider

        public_key = settings.secrets.langfuse_public_key
        secret_key = settings.secrets.langfuse_secret_key
        host = settings.secrets.langfuse_host

        if public_key and secret_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", public_key)
            os.environ.setdefault("LANGFUSE_SECRET_KEY", secret_key)
            if host:
                os.environ.setdefault("LANGFUSE_HOST", host)
            litellm.success_callback = ["langfuse"]
            litellm.failure_callback = ["langfuse"]
            logger.info("Langfuse tracing enabled (host=%s)", host or "default")
        else:
            logger.info("Langfuse keys not configured; LLM tracing disabled")

        _INITIALIZED = True


# ---------------------------------------------------------------------------
# Provider -> LiteLLM model string + API key resolution
# ---------------------------------------------------------------------------

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"

_TEMPERATURE_BY_PROVIDER = {
    "groq": lambda: settings.llm.groq_temperature,
    "google": lambda: settings.llm.google_temperature,
    "openrouter": lambda: settings.llm.openrouter_temperature,
    "cerebras": lambda: settings.llm.cerebras_temperature,
    "mistral": lambda: settings.llm.mistral_temperature,
    "github": lambda: settings.llm.github_temperature,
}


def _api_key_for(provider: str) -> str:
    return {
        "groq": settings.secrets.groq_api_key,
        "google": settings.secrets.gemini_api_key,
        "openrouter": settings.secrets.openrouter_api_key,
        "cerebras": settings.secrets.cerebras_api_key,
        "mistral": settings.secrets.mistral_api_key,
        "github": settings.secrets.github_token,
    }.get(provider, "")


def _to_litellm_model(provider: str, name: str) -> tuple[str, dict[str, Any]]:
    """Translate (provider, name) into the LiteLLM `model=` string + extra kwargs.

    Returns (model_id, extra_kwargs). The extra kwargs include `api_base` for
    providers that LiteLLM doesn't recognise natively (cerebras, openrouter
    are both reachable via their OpenAI-compatible endpoints).
    """
    if provider == "groq":
        return f"groq/{name}", {}
    if provider == "google":
        # LiteLLM uses the `gemini/` prefix for Google AI Studio (free tier),
        # which matches the `langchain-google-genai` package's target.
        return f"gemini/{name}", {}
    if provider == "mistral":
        return f"mistral/{name}", {}
    if provider == "openrouter":
        return f"openrouter/{name}", {}
    if provider == "cerebras":
        # `cerebras/` prefix exists in recent LiteLLM. Pass api_base anyway as
        # a belt-and-braces against version drift.
        return f"cerebras/{name}", {"api_base": _CEREBRAS_BASE_URL}
    if provider == "github":
        # GitHub Models in LiteLLM expects the bare model name (no publisher
        # prefix), e.g. `github/gpt-4o`, not `github/openai/gpt-4o`. We strip
        # leading `<publisher>/` so existing config entries like
        # `name: openai/gpt-4o` continue to work unchanged.
        bare = name.split("/", 1)[1] if "/" in name else name
        return f"github/{bare}", {}

    raise ValueError(f"Unsupported provider: {provider}")


# ---------------------------------------------------------------------------
# JSON parsing (replaces langchain's JsonOutputParser)
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.MULTILINE)
_JSON_OBJECT_RE = re.compile(r"(\{[\s\S]*\}|\[[\s\S]*\])")


def parse_json_response(text: str) -> Any | None:
    """Parse an LLM text response into JSON, tolerant of markdown fences.

    Returns None if no valid JSON can be recovered. Caller treats that as a
    model failure and tries the next one.
    """
    if not text:
        return None
    cleaned = _JSON_FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Last-ditch: grab the first balanced JSON object/array we can find.
    match = _JSON_OBJECT_RE.search(cleaned)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Model rotation iterator
# ---------------------------------------------------------------------------


def model_cycle() -> Iterator[dict]:
    """Cycle through configured models forever (callers should bound attempts).

    The cycle is shared across `analyze_job_match()` invocations so consecutive
    posts naturally round-robin across providers, spreading rate-limit pressure.
    """
    if not settings.llm.models:
        raise RuntimeError("No LLM models configured (config/config.yaml -> llm.models)")
    return itertools.cycle(settings.llm.models)


# ---------------------------------------------------------------------------
# The single public entry point for sending one chat completion
# ---------------------------------------------------------------------------


def validate_response(parsed: Any) -> None:
    """Validate parsed JSON against the v1 output schema.

    Raises ``SchemaValidationError`` if validation fails, which the caller
    treats as a model failure and rotates to the next model.
    """
    schema = _load_output_schema()
    if schema is None:
        return
    try:
        jsonschema.validate(instance=parsed, schema=schema)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(
            f"Response failed schema validation: {exc.message}"
        ) from exc


def complete_json(
    model_info: dict,
    messages: list[dict],
    *,
    metadata: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    json_mode: bool = True,
) -> tuple[Any, str]:
    """Send one chat completion and return (parsed_json, raw_text).

    Raises on transport / API errors so the caller can rotate to the next
    model. JSON parse failures *do not* raise — they return (None, raw_text).
    Schema validation failures raise ``SchemaValidationError``.

    When *json_mode* is True (the default), ``response_format`` is set to
    ``{"type": "json_object"}`` which most OpenAI-compatible providers
    respect. LiteLLM's ``drop_params=True`` silently ignores it for
    providers that don't support it, so the textual schema in the system
    message acts as a fallback.

    ``metadata`` is forwarded to LiteLLM, where Langfuse picks up keys like
    ``trace_id``, ``session_id``, ``tags``, ``generation_name``,
    ``trace_user_id``.
    """
    _init_litellm()

    provider = model_info["provider"]
    name = model_info["name"]
    api_key = _api_key_for(provider)
    if not api_key:
        raise RuntimeError(f"Missing API key for provider {provider!r}")

    model_id, extra = _to_litellm_model(provider, name)
    temperature = _TEMPERATURE_BY_PROVIDER[provider]()

    kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "api_key": api_key,
        "temperature": temperature,
        "num_retries": 2,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if timeout is not None:
        kwargs["timeout"] = timeout
    if metadata:
        kwargs["metadata"] = metadata
    kwargs.update(extra)

    response = litellm.completion(**kwargs)

    try:
        text = response.choices[0].message.content or ""
    except (AttributeError, IndexError, KeyError) as e:
        raise RuntimeError(f"Unexpected LiteLLM response shape: {e!r}") from e

    parsed = parse_json_response(text)

    if parsed is not None:
        validate_response(parsed)

    return parsed, text


# Backward-compat shim: scripts/test_models.py used to call `get_llm()` and
# bind langchain runnables. We expose a thin function with the same name that
# returns the data needed to call `complete_json` instead. This keeps the
# script useful without a full rewrite of its CLI surface.
def get_llm(model_info: dict) -> dict:  # pragma: no cover - compat only
    """Deprecated: returns the model_info unchanged. Use `complete_json` directly."""
    return model_info


__all__ = [
    "SchemaValidationError",
    "complete_json",
    "model_cycle",
    "parse_json_response",
    "validate_response",
    "get_llm",
]


# Allow `from mailrocket.analyzer.llm import _api_key_for` for diagnostic
# scripts (e.g. scripts/test_models.py) without re-exporting in __all__.
_PUBLIC_HELPERS: Iterable[Any] = (_api_key_for,)
