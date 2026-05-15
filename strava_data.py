from __future__ import annotations

from datetime import date

SPORT_EMOJI: dict[str, str] = {
    "Run": "🏃",
    "Ride": "🚴",
    "VirtualRide": "🚴",
    "Swim": "🏊",
    "Walk": "🚶",
    "WeightTraining": "🏋️",
    "Hike": "🥾",
}


def get_activities_in_range(start: date, end: date) -> list[dict]:
    from strava_mcp.client import StravaClient
    return StravaClient().list_activities_in_range(start, end)


def fmt_distance(meters) -> str:
    return f"{meters / 1000:.1f} km" if meters else "—"


def fmt_duration(seconds) -> str:
    if not seconds:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_pace(meters, seconds) -> str:
    if not meters or not seconds or meters < 100:
        return "—"
    pace = seconds / (meters / 1000)
    m, s = divmod(int(pace), 60)
    return f"{m}:{s:02d} /km"


def fmt_speed(ms) -> str:
    return f"{ms * 3.6:.1f} km/h" if ms else "—"
