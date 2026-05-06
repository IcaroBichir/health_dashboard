from __future__ import annotations

import os
from datetime import date, timedelta

# Set MFP_REQUIRED=1 to make the dashboard hard-fail if MFP auth is missing,
# instead of showing "No nutrition data" silently.
_MFP_REQUIRED = os.environ.get("MFP_REQUIRED", "0").strip() == "1"


def _to_number(v) -> float | int:
    if isinstance(v, float):
        return round(v, 1)
    if hasattr(v, "value"):
        return round(v.value, 1)
    return v


def _sum_meal_totals(day) -> dict:
    totals: dict = {}
    for meal in day.meals:
        for k, v in dict(meal.totals).items():
            n = _to_number(v)
            totals[k] = round(totals.get(k, 0) + (n or 0), 1)
    return totals


def _client():
    from mfp_mcp.client import MFPClient
    return MFPClient()


def _handle_mfp_error(exc: Exception):
    """Raise if MFP_REQUIRED=1, otherwise return a sentinel that callers treat as 'no data'."""
    if _MFP_REQUIRED:
        raise RuntimeError(
            f"MFP auth failed: {exc}\n\n"
            "Run: cd ../mcp_myfitnesspal && .venv/bin/mfp-mcp auth\n"
            "Then restart the dashboard."
        ) from exc


def get_nutrition_for_date(d: date) -> dict:
    """Returns {daily_totals, goals} for one day. Raises if MFP_REQUIRED=1 and auth fails."""
    try:
        client = _client()
        day = client.get_date(d.year, d.month, d.day)
        goals = {k: _to_number(v) for k, v in dict(day.goals).items()} if day.goals else {}
        return {"daily_totals": _sum_meal_totals(day), "goals": goals}
    except Exception as exc:
        _handle_mfp_error(exc)
        return {"daily_totals": {}, "goals": {}}


def get_nutrition_range(start: date, end: date) -> list[dict]:
    """Returns [{date, daily_totals, goals}, ...] for each day in range, newest first."""
    try:
        client = _client()
        results = []
        current = start
        while current <= end:
            day = client.get_date(current.year, current.month, current.day)
            goals = {k: _to_number(v) for k, v in dict(day.goals).items()} if day.goals else {}
            results.append({
                "date": str(current),
                "daily_totals": _sum_meal_totals(day),
                "goals": goals,
            })
            current += timedelta(days=1)
        results.sort(key=lambda x: x["date"], reverse=True)
        return results
    except Exception as exc:
        _handle_mfp_error(exc)
        return []
