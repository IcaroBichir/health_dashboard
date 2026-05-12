from __future__ import annotations

from datetime import date, datetime, timezone

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

    client = StravaClient()
    # Widen timestamps by 1 day on each side so UTC-vs-local timezone edge cases
    # don't silently drop activities; we filter precisely by start_date_local below.
    after_ts = int(datetime(start.year, start.month, start.day,
                            tzinfo=timezone.utc).timestamp()) - 86400
    before_ts = int(datetime(end.year, end.month, end.day, 23, 59, 59,
                             tzinfo=timezone.utc).timestamp()) + 86400

    raw = client.list_activities(after=after_ts, before=before_ts, per_page=200)

    s, e = str(start), str(end)
    filtered = [a for a in raw if s <= a.get("start_date_local", "")[:10] <= e]
    return sorted(filtered, key=lambda a: a.get("start_date_local", ""), reverse=True)


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
