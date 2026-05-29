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
def test_get_activities_calls_list_activities_in_range(mock_cls):
    """get_activities_in_range delegates directly to client.list_activities_in_range."""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.list_activities_in_range.return_value = []

    start = date(2026, 5, 3)
    end = date(2026, 5, 7)
    get_activities_in_range(start, end)

    mock_client.list_activities_in_range.assert_called_once_with(start, end)


@patch("strava_mcp.client.StravaClient")
def test_get_activities_returns_client_result_unchanged(mock_cls):
    """get_activities_in_range passes the client's return value through without modification."""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    expected = [_make_activity("2026-05-05"), _make_activity("2026-05-03")]
    mock_client.list_activities_in_range.return_value = expected

    result = get_activities_in_range(date(2026, 5, 1), date(2026, 5, 7))
    assert result is expected


@patch("strava_mcp.client.StravaClient")
def test_get_activities_empty_result(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.list_activities_in_range.return_value = []

    result = get_activities_in_range(date(2026, 5, 1), date(2026, 5, 7))
    assert result == []
