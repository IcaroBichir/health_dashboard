from __future__ import annotations

from datetime import date, timedelta

from withings_mcp.client import WithingsClient


def get_withings_measurements(start: date, end: date) -> list[dict]:
    """Body composition measurements, newest first. Returns [] on any error."""
    try:
        return WithingsClient().get_measurements(start, end)
    except Exception:
        return []


def latest_measurement(measurements: list[dict]) -> dict | None:
    """Return the single most recent measurement record, or None."""
    return measurements[0] if measurements else None


def body_comp_trend(measurements: list[dict]) -> dict | None:
    """
    Compare the newest and oldest readings in the list.
    Returns a dict of {field: delta} for the key body comp fields.
    Returns None if fewer than 2 readings.
    """
    if len(measurements) < 2:
        return None
    newest = measurements[0]
    oldest = measurements[-1]
    fields = ("weight_kg", "fat_ratio_pct", "fat_mass_kg", "muscle_mass_kg",
               "fat_free_mass_kg", "bone_mass_kg", "hydration_kg")
    deltas: dict[str, float] = {}
    for f in fields:
        if f in newest and f in oldest:
            deltas[f] = round(newest[f] - oldest[f], 3)
    return deltas if deltas else None
