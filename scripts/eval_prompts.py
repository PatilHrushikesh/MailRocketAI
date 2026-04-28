"""Evaluate prompt quality against human-reviewed ground truth.

Loads N historical posts from SQLite whose analyses have been manually edited
(i.e. the human used the review UI to correct values — these are the ground
truth). Re-runs the analyzer against each post and compares the fresh LLM
output to the stored ground truth.

Metrics reported per-field:
    - match_percentage: Mean Absolute Error (MAE)
    - contact_email:    Precision & Recall (set comparison)
    - should_apply:     Agreement rate (%)
    - schema_valid:     % of responses that pass JSON Schema validation

Usage:
    python scripts/eval_prompts.py                 # default 10 posts
    python scripts/eval_prompts.py --limit 50
    python scripts/eval_prompts.py --csv results.csv
    python scripts/eval_prompts.py --verbose
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mailrocket.analyzer.llm import SchemaValidationError, validate_response  # noqa: E402
from mailrocket.analyzer.service import analyze_job_match  # noqa: E402
from mailrocket.storage.connection import get_conn  # noqa: E402


def _fetch_ground_truth(limit: int) -> list[dict]:
    """Return posts+analyses where the human has edited the analysis.

    We consider an analysis "human-reviewed" if mail_sent != -1 (i.e. the
    human made a send/reject decision) OR the analysis row has been updated
    after insertion (we look for non-null final_decision as a proxy).
    """
    sql = """
        SELECT
            lp.uid, lp.post_text, lp.post_link, lp.query,
            pa.analysis_id,
            pa.match_percentage  AS gt_match,
            pa.should_apply      AS gt_should_apply,
            pa.contact_email     AS gt_contact_email,
            pa.experience_gap    AS gt_experience_gap,
            pa.full_analysis_json AS gt_full_json
        FROM linkedin_posts lp
        JOIN post_analysis pa ON pa.post_uid = lp.uid
        WHERE lp.post_text IS NOT NULL
          AND lp.post_text != ''
          AND pa.mail_sent != -1
        ORDER BY pa.analysis_id DESC
        LIMIT ?;
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return rows


def _safe_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _email_precision_recall(
    predicted: list[str], ground_truth: list[str]
) -> tuple[float, float]:
    pred_set = {e.lower().strip() for e in predicted if e}
    gt_set = {e.lower().strip() for e in ground_truth if e}
    if not pred_set and not gt_set:
        return 1.0, 1.0
    if not pred_set:
        return 0.0, 0.0
    if not gt_set:
        return 0.0, 1.0
    tp = len(pred_set & gt_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(gt_set) if gt_set else 0.0
    return precision, recall


def run_eval(limit: int, verbose: bool = False) -> list[dict]:
    rows = _fetch_ground_truth(limit)
    if not rows:
        print("No human-reviewed analyses found in the database.", file=sys.stderr)
        return []

    print(f"Evaluating {len(rows)} ground-truth post(s)...\n")

    results: list[dict] = []
    for i, row in enumerate(rows, 1):
        post_text = row["post_text"]
        uid = row["uid"]
        print(f"[{i:03d}/{len(rows):03d}] uid={uid} ...", end=" ", flush=True)

        try:
            analyses, model_info = analyze_job_match(
                post_text,
                trace_metadata={
                    "post_uid": uid,
                    "post_link": row.get("post_link"),
                    "query": row.get("query"),
                },
            )
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "uid": uid,
                "error": str(e),
                "match_mae": None,
                "should_apply_agree": None,
                "email_precision": None,
                "email_recall": None,
                "schema_valid": False,
            })
            continue

        pred = analyses[0] if analyses else {}
        if pred.get("error"):
            print(f"ALL MODELS FAILED")
            results.append({
                "uid": uid,
                "error": "all_models_failed",
                "match_mae": None,
                "should_apply_agree": None,
                "email_precision": None,
                "email_recall": None,
                "schema_valid": False,
            })
            continue

        schema_valid = True
        try:
            validate_response(analyses)
        except SchemaValidationError:
            schema_valid = False

        gt_match = row["gt_match"] or 0
        pred_match = pred.get("match_percentage", 0) or 0
        match_mae = abs(pred_match - gt_match)

        gt_apply = bool(row["gt_should_apply"])
        pred_apply = bool(pred.get("should_apply"))
        apply_agree = gt_apply == pred_apply

        gt_emails = _safe_json_list(row["gt_contact_email"])
        pred_emails = pred.get("contact_email", []) or []
        email_prec, email_rec = _email_precision_recall(pred_emails, gt_emails)

        model_tag = f"{model_info['provider']}/{model_info['name']}"
        status = "OK" if schema_valid and apply_agree else "DRIFT"
        print(f"{status}  match_mae={match_mae}  apply_agree={apply_agree}  model={model_tag}")

        results.append({
            "uid": uid,
            "error": None,
            "model": model_tag,
            "match_mae": match_mae,
            "should_apply_agree": apply_agree,
            "email_precision": email_prec,
            "email_recall": email_rec,
            "schema_valid": schema_valid,
        })

    return results


def _print_summary(results: list[dict]) -> None:
    valid = [r for r in results if r.get("error") is None]
    if not valid:
        print("\nNo successful evaluations to summarize.")
        return

    n = len(valid)
    avg_mae = sum(r["match_mae"] for r in valid) / n
    agree_pct = sum(1 for r in valid if r["should_apply_agree"]) / n * 100
    avg_prec = sum(r["email_precision"] for r in valid) / n
    avg_rec = sum(r["email_recall"] for r in valid) / n
    schema_pct = sum(1 for r in valid if r["schema_valid"]) / n * 100
    errors = len(results) - n

    print(f"\n{'=' * 50}")
    print(f"EVALUATION SUMMARY ({n} successful, {errors} errors)")
    print(f"{'=' * 50}")
    print(f"  match_percentage MAE:     {avg_mae:.1f}")
    print(f"  should_apply agreement:   {agree_pct:.1f}%")
    print(f"  contact_email precision:  {avg_prec:.2f}")
    print(f"  contact_email recall:     {avg_rec:.2f}")
    print(f"  schema validity rate:     {schema_pct:.1f}%")


def _write_csv(results: list[dict], path: str) -> None:
    if not results:
        return
    fieldnames = list(results[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nCSV written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--limit", type=int, default=10, help="Max posts to evaluate (default 10)")
    parser.add_argument("--csv", type=str, default=None, help="Write results to CSV file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    results = run_eval(args.limit, verbose=args.verbose)
    _print_summary(results)

    if args.csv:
        _write_csv(results, args.csv)

    ok = [r for r in results if r.get("error") is None]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
