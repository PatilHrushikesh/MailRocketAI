"""LLM provider plumbing.

The list of models is configured in `config/config.yaml` under `llm.models`;
this module just translates a (provider, name) entry into a langchain client.

Supported providers: `groq`, `google`, `openrouter`, `cerebras`, `mistral`, `github`.

`openrouter`, `cerebras`, and `github` all speak the OpenAI chat-completions
protocol, so they share `ChatOpenAI` with different `base_url`/API key. Mistral
needs the native `ChatMistralAI` because their server rejects the OpenAI-newer
`max_completion_tokens` field that `langchain-openai` emits.
"""
from __future__ import annotations

import logging
from typing import Iterator

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI

from mailrocket.settings import settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"


def _openai_compatible(name: str, base_url: str, api_key: str, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        model=name,
        base_url=base_url,
        api_key=api_key or None,
        temperature=temperature,
        max_retries=2,
    )


def get_llm(model_info: dict):
    """Instantiate a langchain Chat model for one entry of `llm.models`."""
    provider = model_info["provider"]
    name = model_info["name"]

    if provider == "groq":
        return ChatGroq(
            model=name,
            temperature=settings.llm.groq_temperature,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            groq_api_key=settings.secrets.groq_api_key or None,
        )
    if provider == "google":
        return ChatGoogleGenerativeAI(
            model=name,
            google_api_key=settings.secrets.gemini_api_key or None,
            temperature=settings.llm.google_temperature,
        )
    if provider == "openrouter":
        return _openai_compatible(
            name=name,
            base_url=OPENROUTER_BASE_URL,
            api_key=settings.secrets.openrouter_api_key,
            temperature=settings.llm.openrouter_temperature,
        )
    if provider == "cerebras":
        return _openai_compatible(
            name=name,
            base_url=CEREBRAS_BASE_URL,
            api_key=settings.secrets.cerebras_api_key,
            temperature=settings.llm.cerebras_temperature,
        )
    if provider == "mistral":
        return ChatMistralAI(
            model=name,
            api_key=settings.secrets.mistral_api_key or None,
            temperature=settings.llm.mistral_temperature,
            max_retries=2,
        )
    if provider == "github":
        return _openai_compatible(
            name=name,
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=settings.secrets.github_token,
            temperature=settings.llm.github_temperature,
        )

    raise ValueError(f"Unsupported provider: {provider}")


def model_cycle() -> Iterator[dict]:
    """Cycle through configured models forever (callers should bound attempts)."""
    import itertools

    if not settings.llm.models:
        raise RuntimeError("No LLM models configured (config/config.yaml -> llm.models)")
    return itertools.cycle(settings.llm.models)
