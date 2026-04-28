"""Health-check every model in `config/config.yaml -> llm.models`.

Sends a minimal prompt ("Reply with the single word OK.") with a tight token
budget so this can be run repeatedly without burning quota. Prints a summary
table of which models responded and which failed (with a short error reason).

Usage:
    python scripts/test_models.py            # test all configured models
    python scripts/test_models.py --provider groq   # filter by provider
    python scripts/test_models.py --model llama-3.1-8b-instant
    python scripts/test_models.py --max-tokens 8 --timeout 20
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mailrocket.analyzer.llm import _api_key_for, complete_json  # noqa: E402
from mailrocket.settings import settings  # noqa: E402

PROMPT = 'Respond with this exact JSON, no prose, no markdown: {"ok": true}'


@dataclass
class Result:
    provider: str
    name: str
    ok: bool
    latency_ms: int
    reply: str
    error: str


def _short(text: str, n: int = 80) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


PROVIDERS = ("groq", "google", "openrouter", "cerebras", "mistral", "github")


def _ping(model_info: dict, max_tokens: int, timeout: float) -> Result:
    provider = model_info["provider"]
    name = model_info["name"]

    if not _api_key_for(provider):
        return Result(provider, name, False, 0, "", f"missing api key for provider '{provider}'")

    start = time.perf_counter()
    try:
        # Plain user message; we don't need the JSON-shaped analyzer prompt here.
        messages = [{"role": "user", "content": PROMPT}]
        _parsed, raw = complete_json(
            model_info,
            messages,
            metadata={"generation_name": "health_check", "tags": ["mailrocket", "health"]},
            max_tokens=max_tokens,
            timeout=timeout,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        return Result(provider, name, True, elapsed, _short(raw, 60), "")
    except Exception as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        return Result(provider, name, False, elapsed, "", _short(str(e), 140))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--provider", choices=PROVIDERS, help="Test only one provider")
    p.add_argument("--model", help="Substring match on model name (case-insensitive)")
    p.add_argument("--max-tokens", type=int, default=8, help="Cap output tokens (default 8)")
    p.add_argument("--timeout", type=float, default=20.0, help="Per-call timeout in seconds (default 20)")
    p.add_argument("-v", "--verbose", action="store_true", help="Show full error tracebacks")
    return p.parse_args()


def _filter(models: list[dict], args: argparse.Namespace) -> list[dict]:
    out = list(models)
    if args.provider:
        out = [m for m in out if m.get("provider") == args.provider]
    if args.model:
        needle = args.model.lower()
        out = [m for m in out if needle in str(m.get("name", "")).lower()]
    return out


def _print_table(results: list[Result]) -> None:
    headers = ("STATUS", "PROVIDER", "MODEL", "LATENCY", "REPLY / ERROR")
    rows = []
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        latency = f"{r.latency_ms} ms" if r.latency_ms else "-"
        rows.append((status, r.provider, r.name, latency, r.reply if r.ok else r.error))

    widths = [max(len(str(c)) for c in col) for col in zip(headers, *rows)]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    sep = "-" * (sum(widths) + 2 * (len(widths) - 1))

    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*row))


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    models = _filter(list(settings.llm.models), args)
    if not models:
        print("No models match the given filters.", file=sys.stderr)
        return 2

    print(f"Pinging {len(models)} model(s) with prompt={PROMPT!r}, max_tokens={args.max_tokens}\n")

    results: list[Result] = []
    for i, m in enumerate(models, 1):
        provider = m.get("provider", "?")
        name = m.get("name", "?")
        print(f"[{i:02d}/{len(models):02d}] {provider}/{name} ...", end=" ", flush=True)
        r = _ping(m, max_tokens=args.max_tokens, timeout=args.timeout)
        results.append(r)
        print(("OK " + str(r.latency_ms) + "ms") if r.ok else ("FAIL " + r.error))

    print()
    _print_table(results)

    ok = sum(1 for r in results if r.ok)
    print(f"\nSummary: {ok}/{len(results)} models responded.")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
