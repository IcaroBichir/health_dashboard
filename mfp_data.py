from __future__ import annotations

from datetime import date, timedelta


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


def get_nutrition_for_date(d: date) -> dict:
    """Returns {daily_totals, goals} for one day. Returns empty dicts on any failure."""
    try:
        client = _client()
        day = client.get_date(d.year, d.month, d.day)
        goals = {k: _to_number(v) for k, v in dict(day.goals).items()} if day.goals else {}
        return {"daily_totals": _sum_meal_totals(day), "goals": goals}
    except Exception:
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
    except Exception:
        return []
