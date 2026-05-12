from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from strava_data import (
    fmt_distance,
    fmt_duration,
    fmt_pace,
    fmt_speed,
    get_activities_in_range,
)


# ── Formatters ────────────────────────────────────────────────────────────────

def test_fmt_distance_normal():
    assert fmt_distance(10000) == "10.0 km"


def test_fmt_distance_fractional():
    assert fmt_distance(5500) == "5.5 km"


def test_fmt_distance_zero():
    assert fmt_distance(0) == "—"


def test_fmt_distance_none():
    assert fmt_distance(None) == "—"


def test_fmt_duration_minutes_seconds():
    assert fmt_duration(3 * 60 + 45) == "3:45"


def test_fmt_duration_hours():
    assert fmt_duration(3661) == "1:01:01"


def test_fmt_duration_zero_seconds():
    assert fmt_duration(60) == "1:00"


def test_fmt_duration_none():
    assert fmt_duration(None) == "—"


def test_fmt_duration_zero():
    assert fmt_duration(0) == "—"


def test_fmt_pace_normal():
    # 10 km in 50 min = 5:00 /km
    assert fmt_pace(10000, 3000) == "5:00 /km"


def test_fmt_pace_sub_100m():
    assert fmt_pace(50, 30) == "—"


def test_fmt_pace_none_distance():
    assert fmt_pace(None, 300) == "—"


def test_fmt_pace_none_seconds():
    assert fmt_pace(5000, None) == "—"


def test_fmt_speed_normal():
    # 10 m/s = 36 km/h
    assert fmt_speed(10.0) == "36.0 km/h"


def test_fmt_speed_none():
    assert fmt_speed(None) == "—"


# ── get_activities_in_range ───────────────────────────────────────────────────

def _make_activity(date_str: str, sport: str = "Run") -> dict:
    return {"start_date_local": f"{date_str}T08:00:00Z", "sport_type": sport, "distance": 5000}


@patch("strava_mcp.client.StravaClient")
def test_activities_filtered_to_range(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.list_activities.return_value = [
        _make_activity("2026-05-01"),
        _make_activity("2026-05-03"),
        _make_activity("2026-05-07"),  # outside range
    ]

    result = get_activities_in_range(date(2026, 5, 1), date(2026, 5, 5))

    dates = [a["start_date_local"][:10] for a in result]
    assert "2026-05-01" in dates
    assert "2026-05-03" in dates
    assert "2026-05-07" not in dates


@patch("strava_mcp.client.StravaClient")
def test_activities_boundary_dates_included(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.list_activities.return_value = [
        _make_activity("2026-05-01"),
        _make_activity("2026-05-07"),
    ]

    result = get_activities_in_range(date(2026, 5, 1), date(2026, 5, 7))

    dates = [a["start_date_local"][:10] for a in result]
    assert "2026-05-01" in dates
    assert "2026-05-07" in dates


@patch("strava_mcp.client.StravaClient")
def test_activities_sorted_newest_first(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.list_activities.return_value = [
        _make_activity("2026-05-01"),
        _make_activity("2026-05-05"),
        _make_activity("2026-05-03"),
    ]

    result = get_activities_in_range(date(2026, 5, 1), date(2026, 5, 7))

    dates = [a["start_date_local"][:10] for a in result]
    assert dates == sorted(dates, reverse=True)


@patch("strava_mcp.client.StravaClient")
def test_activities_empty_range(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.list_activities.return_value = []

    result = get_activities_in_range(date(2026, 5, 1), date(2026, 5, 7))
    assert result == []


@patch("strava_mcp.client.StravaClient")
def test_activities_timestamp_buffer(mock_cls):
    """Verify after/before params include ±1 day buffer."""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.list_activities.return_value = []

    from datetime import datetime, timezone
    start = date(2026, 5, 3)
    end = date(2026, 5, 5)
    get_activities_in_range(start, end)

    call_kwargs = mock_client.list_activities.call_args.kwargs
    expected_after = int(datetime(2026, 5, 3, tzinfo=timezone.utc).timestamp()) - 86400
    expected_before = int(datetime(2026, 5, 5, 23, 59, 59, tzinfo=timezone.utc).timestamp()) + 86400
    assert call_kwargs["after"] == expected_after
    assert call_kwargs["before"] == expected_before
