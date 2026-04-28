"""Centralised configuration loader.

Precedence (highest first):
    1. Environment variables prefixed MAILROCKET_ / MAILROCKET_SECRET_
    2. config/secrets.yaml (gitignored)
    3. config/config.yaml (gitignored)
    4. config/config.example.yaml / secrets.example.yaml (committed defaults)

Usage:
    from mailrocket.settings import settings
    settings.paths.db                # -> Path
    settings.candidate.full_name     # -> str
    settings.secrets.gemini_api_key  # -> str
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"


@dataclass(frozen=True)
class Paths:
    db: Path
    cookies: Path
    queries: Path
    prompts_dir: Path
    resume_text: Path
    resume_pdf: Path
    log_file: Path | None
    chrome_profile: Path
    debug_dir: Path


@dataclass(frozen=True)
class Candidate:
    full_name: str
    phone_number: str
    resume_url: str
    linkedin_profile_url: str
    preferred_roles: tuple[str, ...]
    role_specific_emphasis: tuple[dict, ...]


@dataclass(frozen=True)
class EmailDefaults:
    from_mail: str
    self_review_mail: str
    subject_postfix: str
    body_closer: str


@dataclass(frozen=True)
class Filters:
    match_threshold: int
    max_experience_gap: float
    reject_employment_types: tuple[str, ...]


@dataclass(frozen=True)
class ScraperConfig:
    headless: bool
    max_post_age_weeks: int
    per_query_delay_seconds: int
    manual_login_timeout_seconds: int
    dump_after_login: bool


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    file: Path | None


@dataclass(frozen=True)
class LLMConfig:
    models: tuple[dict, ...]
    groq_temperature: float
    google_temperature: float
    openrouter_temperature: float
    cerebras_temperature: float
    mistral_temperature: float
    github_temperature: float
    few_shot: bool


@dataclass(frozen=True)
class Secrets:
    linkedin_username: str
    linkedin_password: str
    gemini_api_key: str
    groq_api_key: str
    openrouter_api_key: str
    cerebras_api_key: str
    mistral_api_key: str
    github_token: str
    gmail_client_secret_path: Path
    gmail_token_path: Path
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str


@dataclass(frozen=True)
class Settings:
    paths: Paths
    candidate: Candidate
    email: EmailDefaults
    filters: Filters
    scraper: ScraperConfig
    logging: LoggingConfig
    llm: LLMConfig
    secrets: Secrets


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at top level of {path}, got {type(data)}")
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_path(value: str | Path | None) -> Path | None:
    if value is None or value == "":
        return None
    p = Path(value)
    return p if p.is_absolute() else REPO_ROOT / p


def _env_override(env_name: str, current: Any) -> Any:
    """Return the env var value if present (string-cast), else current."""
    raw = os.environ.get(env_name)
    if raw is None:
        return current
    if isinstance(current, bool):
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    return raw


def _load_config_dict() -> dict[str, Any]:
    example = _load_yaml(CONFIG_DIR / "config.example.yaml")
    user = _load_yaml(CONFIG_DIR / "config.yaml")
    return _deep_merge(example, user)


def _load_secrets_dict() -> dict[str, Any]:
    example = _load_yaml(CONFIG_DIR / "secrets.example.yaml")
    user = _load_yaml(CONFIG_DIR / "secrets.yaml")
    return _deep_merge(example, user)


def load_settings() -> Settings:
    cfg = _load_config_dict()
    sec = _load_secrets_dict()

    paths_cfg = cfg.get("paths", {})
    paths = Paths(
        db=_resolve_path(_env_override("MAILROCKET_DB", paths_cfg.get("db", "data/linkedin_posts.db"))),
        cookies=_resolve_path(_env_override("MAILROCKET_COOKIES", paths_cfg.get("cookies", "data/cookies.pkl"))),
        queries=_resolve_path(_env_override("MAILROCKET_QUERIES", paths_cfg.get("queries", "config/search_queries.yaml"))),
        prompts_dir=_resolve_path(_env_override("MAILROCKET_PROMPTS_DIR", paths_cfg.get("prompts_dir", "prompts"))),
        resume_text=_resolve_path(_env_override("MAILROCKET_RESUME_TEXT", paths_cfg.get("resume_text", "data/resume.txt"))),
        resume_pdf=_resolve_path(_env_override("MAILROCKET_RESUME_PDF", paths_cfg.get("resume_pdf", "data/resume.pdf"))),
        log_file=_resolve_path(cfg.get("logging", {}).get("file")),
        chrome_profile=_resolve_path(_env_override("MAILROCKET_CHROME_PROFILE", paths_cfg.get("chrome_profile", "data/chrome-profile"))),
        debug_dir=_resolve_path(_env_override("MAILROCKET_DEBUG_DIR", paths_cfg.get("debug_dir", "data/debug"))),
    )

    cand_cfg = cfg.get("candidate", {})
    candidate = Candidate(
        full_name=_env_override("MAILROCKET_FULL_NAME", cand_cfg.get("full_name", "")),
        phone_number=_env_override("MAILROCKET_PHONE_NUMBER", cand_cfg.get("phone_number", "")),
        resume_url=_env_override("MAILROCKET_RESUME_URL", cand_cfg.get("resume_url", "")),
        linkedin_profile_url=_env_override("MAILROCKET_LINKEDIN_PROFILE_URL", cand_cfg.get("linkedin_profile_url", "")),
        preferred_roles=tuple(cand_cfg.get("preferred_roles", [])),
        role_specific_emphasis=tuple(cand_cfg.get("role_specific_emphasis", [])),
    )

    email_cfg = cfg.get("email", {})
    raw_closer = email_cfg.get("body_closer", "")
    body_closer = raw_closer.format(
        resume_url=candidate.resume_url,
        linkedin_profile_url=candidate.linkedin_profile_url,
        full_name=candidate.full_name,
        phone_number=candidate.phone_number,
    ) if raw_closer else ""
    email = EmailDefaults(
        from_mail=_env_override("MAILROCKET_FROM_MAIL", email_cfg.get("from_mail", "")),
        self_review_mail=_env_override("MAILROCKET_SELF_REVIEW_MAIL", email_cfg.get("self_review_mail", "")),
        subject_postfix=_env_override("MAILROCKET_SUBJECT_POSTFIX", email_cfg.get("subject_postfix", "")),
        body_closer=body_closer,
    )

    filt_cfg = cfg.get("filters", {})
    filters = Filters(
        match_threshold=int(_env_override("MAILROCKET_MATCH_THRESHOLD", filt_cfg.get("match_threshold", 68))),
        max_experience_gap=float(_env_override("MAILROCKET_MAX_EXPERIENCE_GAP", filt_cfg.get("max_experience_gap", 1))),
        reject_employment_types=tuple(t.lower() for t in filt_cfg.get("reject_employment_types", ["internship"])),
    )

    scr_cfg = cfg.get("scraper", {})
    scraper = ScraperConfig(
        headless=bool(_env_override("MAILROCKET_HEADLESS", scr_cfg.get("headless", True))),
        max_post_age_weeks=int(scr_cfg.get("max_post_age_weeks", 10)),
        per_query_delay_seconds=int(scr_cfg.get("per_query_delay_seconds", 10)),
        manual_login_timeout_seconds=int(scr_cfg.get("manual_login_timeout_seconds", 300)),
        dump_after_login=bool(_env_override("MAILROCKET_DUMP_AFTER_LOGIN", scr_cfg.get("dump_after_login", False))),
    )

    log_cfg = cfg.get("logging", {})
    logging_cfg = LoggingConfig(
        level=_env_override("MAILROCKET_LOG_LEVEL", log_cfg.get("level", "INFO")),
        file=_resolve_path(log_cfg.get("file")),
    )

    llm_cfg = cfg.get("llm", {})
    llm = LLMConfig(
        models=tuple(llm_cfg.get("models", [])),
        groq_temperature=float(llm_cfg.get("groq_temperature", 0.4)),
        google_temperature=float(llm_cfg.get("google_temperature", 0.2)),
        openrouter_temperature=float(llm_cfg.get("openrouter_temperature", 0.4)),
        cerebras_temperature=float(llm_cfg.get("cerebras_temperature", 0.4)),
        mistral_temperature=float(llm_cfg.get("mistral_temperature", 0.4)),
        github_temperature=float(llm_cfg.get("github_temperature", 0.4)),
        few_shot=bool(_env_override("MAILROCKET_FEW_SHOT", llm_cfg.get("few_shot", False))),
    )

    li = sec.get("linkedin", {}) or {}
    gm = sec.get("gmail", {}) or {}
    lf = sec.get("langfuse", {}) or {}
    secrets = Secrets(
        linkedin_username=_env_override("MAILROCKET_SECRET_LINKEDIN_USERNAME", li.get("username", "")),
        linkedin_password=_env_override("MAILROCKET_SECRET_LINKEDIN_PASSWORD", li.get("password", "")),
        gemini_api_key=_env_override("MAILROCKET_SECRET_GEMINI_API_KEY", sec.get("gemini_api_key", "")),
        groq_api_key=_env_override("MAILROCKET_SECRET_GROQ_API_KEY", sec.get("groq_api_key", "")),
        openrouter_api_key=_env_override("MAILROCKET_SECRET_OPENROUTER_API_KEY", sec.get("openrouter_api_key", "")),
        cerebras_api_key=_env_override("MAILROCKET_SECRET_CEREBRAS_API_KEY", sec.get("cerebras_api_key", "")),
        mistral_api_key=_env_override("MAILROCKET_SECRET_MISTRAL_API_KEY", sec.get("mistral_api_key", "")),
        github_token=_env_override("MAILROCKET_SECRET_GITHUB_TOKEN", sec.get("github_token", "")),
        gmail_client_secret_path=_resolve_path(_env_override("MAILROCKET_SECRET_GMAIL_CLIENT_SECRET_PATH", gm.get("client_secret_path", "data/gmail/client_secret.json"))),
        gmail_token_path=_resolve_path(_env_override("MAILROCKET_SECRET_GMAIL_TOKEN_PATH", gm.get("token_path", "data/gmail/token.json"))),
        langfuse_public_key=_env_override("MAILROCKET_SECRET_LANGFUSE_PUBLIC_KEY", lf.get("public_key", "")),
        langfuse_secret_key=_env_override("MAILROCKET_SECRET_LANGFUSE_SECRET_KEY", lf.get("secret_key", "")),
        langfuse_host=_env_override("MAILROCKET_SECRET_LANGFUSE_HOST", lf.get("host", "https://cloud.langfuse.com")),
    )

    return Settings(
        paths=paths,
        candidate=candidate,
        email=email,
        filters=filters,
        scraper=scraper,
        logging=logging_cfg,
        llm=llm,
        secrets=secrets,
    )


settings: Settings = load_settings()
