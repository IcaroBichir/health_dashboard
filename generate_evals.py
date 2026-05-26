#!/usr/bin/env python3
"""
Generate and cache running + correlation evaluations via the Claude Code CLI.

Called by the `start` script on dashboard launch (unless --no-eval is passed).
Uses `claude -p` for non-interactive generation — no separate API key needed.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from running_data import runs_in_window, compute_run_metrics, build_evaluation_context
from correlation_data import compute_correlation_metrics, build_correlation_context
from claude_eval import (
    write_evaluation_to_cache,
    evaluation_is_cached,
    write_correlation_evaluation_to_cache,
    correlation_evaluation_is_cached,
)

_RUN_SYSTEM = """\
You are an expert running coach and sports scientist analyzing an athlete's training data. \
Provide a concise, insightful evaluation of their running performance and progress. \
Focus on training load, pace trends, consistency, recovery indicators from HR data, \
elevation work, and 2-3 specific actionable recommendations. \
Reference the actual numbers from the data. Write 3-5 short paragraphs. \
Tone: direct, coach-like, honest — not generic motivational fluff.\
"""

_CORR_SYSTEM = """\
You are an expert sports nutritionist and endurance coach analyzing an athlete's \
nutrition and exercise data. The athlete runs primarily in the morning (8–10am), \
so the prior day's nutrition is the key pre-workout fuel source. \
Analyze: (1) how prior-day carbs, calories, and protein correlate with next-day \
pace, HR, and suffer score; (2) calorie balance sustainability on hard training days; \
(3) whether protein intake supports recovery between sessions; \
(4) patterns in nutrition on workout days vs rest days. \
Give 2-3 specific, data-driven recommendations. Reference actual dates and numbers \
where patterns are clear. Write 4-6 short paragraphs. \
Tone: direct, analytical — not generic nutrition advice.\
"""

TODAY         = date.today()
WEEK_START    = TODAY - timedelta(days=6)
FIFTEEN_START = TODAY - timedelta(days=14)
MONTH_START   = TODAY - timedelta(days=29)


def _fetch_runs() -> list[dict]:
    from strava_mcp.client import StravaClient
    client = StravaClient()
    activities = client.list_activities_in_range(MONTH_START, TODAY)
    for a in activities:
        if not a.get("calories") and a.get("id"):
            try:
                detailed = client.get_activity(a["id"])
                if detailed.get("calories"):
                    a["calories"] = detailed["calories"]
            except Exception:
                pass
    return activities


def _fetch_nutrition() -> list[dict] | None:
    """Return 30-day nutrition list, or None if MFP is unavailable."""
    try:
        from mfp_data import get_nutrition_range
        data = get_nutrition_range(MONTH_START, TODAY)
        if any(d.get("daily_totals") for d in data):
            return data
        return None
    except Exception:
        return None


def _call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"exit code {result.returncode}")
    return result.stdout.strip()


def _generate_run(period: str, runs: list[dict], metrics: dict, force: bool) -> None:
    if not force and evaluation_is_cached(period):
        print(f"  run/{period:>3}  ✓  cached")
        return
    if not runs:
        print(f"  run/{period:>3}  —  no runs")
        return
    ctx = build_evaluation_context(period, runs, metrics, TODAY)
    print(f"  run/{period:>3}  generating…", end="", flush=True)
    try:
        write_evaluation_to_cache(period, _call_claude(f"{_RUN_SYSTEM}\n\n{ctx}"))
        print(" ✓")
    except Exception as exc:
        print(f" ✗  ({exc})")


def _generate_corr(period: str, label: str, all_month: list[dict],
                   nutrition_month: list[dict], start: date, force: bool) -> None:
    if not force and correlation_evaluation_is_cached(period):
        print(f"  corr/{period:>3}  ✓  cached")
        return
    metrics = compute_correlation_metrics(all_month, nutrition_month, start)
    if not metrics.get("overlap_days"):
        print(f"  corr/{period:>3}  —  no paired days")
        return
    ctx = build_correlation_context(label, metrics, TODAY)
    print(f"  corr/{period:>3}  generating…", end="", flush=True)
    try:
        write_correlation_evaluation_to_cache(period, _call_claude(f"{_CORR_SYSTEM}\n\n{ctx}"))
        print(" ✓")
    except Exception as exc:
        print(f" ✗  ({exc})")


def main(force: bool = False) -> int:
    try:
        all_month = _fetch_runs()
    except Exception as exc:
        print(f"  ✗  could not fetch Strava data: {exc}")
        return 1

    # ── Running evaluations ──────────────────────────────────────────────────
    print("Running evaluations:")
    runs_7d  = runs_in_window(all_month, WEEK_START)
    runs_15d = runs_in_window(all_month, FIFTEEN_START)
    runs_30d = runs_in_window(all_month, MONTH_START)
    _generate_run("7d",  runs_7d,  compute_run_metrics(runs_7d),  force)
    _generate_run("15d", runs_15d, compute_run_metrics(runs_15d), force)
    _generate_run("30d", runs_30d, compute_run_metrics(runs_30d), force)

    # ── Correlation evaluations (only if MFP data available) ─────────────────
    print("Correlation evaluations:")
    nutrition_month = _fetch_nutrition()
    if nutrition_month is None:
        print("  —  MFP data unavailable, skipping correlation evals")
        return 0

    _generate_corr("15d", "Last 15 Days", all_month, nutrition_month, FIFTEEN_START, force)
    _generate_corr("30d", "Last 30 Days", all_month, nutrition_month, MONTH_START,   force)
    return 0


if __name__ == "__main__":
    force = "--force" in sys.argv
    sys.exit(main(force=force))
