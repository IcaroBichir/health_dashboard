#!/usr/bin/env python3
"""
Generate and cache running evaluations via the Claude Code CLI.

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
from claude_eval import write_evaluation_to_cache, evaluation_is_cached

_COACHING_SYSTEM = """\
You are an expert running coach and sports scientist analyzing an athlete's training data. \
Provide a concise, insightful evaluation of their running performance and progress. \
Focus on training load, pace trends, consistency, recovery indicators from HR data, \
elevation work, and 2-3 specific actionable recommendations. \
Reference the actual numbers from the data. Write 3-5 short paragraphs. \
Tone: direct, coach-like, honest — not generic motivational fluff.\
"""

TODAY = date.today()
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


def _generate(period: str, runs: list[dict], metrics: dict, force: bool) -> None:
    if not force and evaluation_is_cached(period):
        print(f"  {period:>3}  ✓  cached")
        return
    if not runs:
        print(f"  {period:>3}  —  no runs in this period")
        return

    ctx = build_evaluation_context(period, runs, metrics, TODAY)
    full_prompt = f"{_COACHING_SYSTEM}\n\n{ctx}"

    print(f"  {period:>3}  generating…", end="", flush=True)
    try:
        text = _call_claude(full_prompt)
        write_evaluation_to_cache(period, text)
        print(" ✓")
    except Exception as exc:
        print(f" ✗  ({exc})")


def main(force: bool = False) -> int:
    print("Running evaluations:")
    try:
        all_month = _fetch_runs()
    except Exception as exc:
        print(f"  ✗  could not fetch Strava data: {exc}")
        return 1

    runs_7d  = runs_in_window(all_month, WEEK_START)
    runs_15d = runs_in_window(all_month, FIFTEEN_START)
    runs_30d = runs_in_window(all_month, MONTH_START)

    _generate("7d",  runs_7d,  compute_run_metrics(runs_7d),  force)
    _generate("15d", runs_15d, compute_run_metrics(runs_15d), force)
    _generate("30d", runs_30d, compute_run_metrics(runs_30d), force)
    return 0


if __name__ == "__main__":
    force = "--force" in sys.argv
    sys.exit(main(force=force))
