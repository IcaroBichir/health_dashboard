from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from mfp_data import (
    _sum_meal_totals,
    _to_number,
    get_nutrition_for_date,
    get_nutrition_range,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def test_to_number_float():
    assert _to_number(3.14159) == 3.1


def test_to_number_value_attr():
    obj = SimpleNamespace(value=200.0)
    assert _to_number(obj) == 200.0


def test_to_number_int():
    assert _to_number(42) == 42


def _make_meal(totals: dict):
    meal = MagicMock()
    meal.totals = totals
    return meal


def _make_day(meals_data: list[dict], goals: dict | None = None):
    day = MagicMock()
    day.meals = [_make_meal(t) for t in meals_data]
    day.goals = goals
    return day


def test_sum_meal_totals_single_meal():
    day = _make_day([{"calories": 500.0, "protein": 30.0}])
    result = _sum_meal_totals(day)
    assert result["calories"] == 500.0
    assert result["protein"] == 30.0


def test_sum_meal_totals_multiple_meals():
    day = _make_day([
        {"calories": 400.0, "protein": 20.0},
        {"calories": 600.0, "protein": 40.0},
    ])
    result = _sum_meal_totals(day)
    assert result["calories"] == 1000.0
    assert result["protein"] == 60.0


def test_sum_meal_totals_empty():
    day = _make_day([])
    assert _sum_meal_totals(day) == {}


# ── get_nutrition_for_date ────────────────────────────────────────────────────

@patch("mfp_data._client")
def test_get_nutrition_for_date_returns_totals_and_goals(mock_client_fn):
    day = _make_day(
        [{"calories": 1800.0, "protein": 140.0, "carbohydrates": 180.0, "fat": 60.0}],
        goals={"calories": 2200, "protein": 150},
    )
    mock_client_fn.return_value.get_date.return_value = day

    result = get_nutrition_for_date(date(2026, 5, 6))

    assert result["daily_totals"]["calories"] == 1800.0
    assert result["daily_totals"]["protein"] == 140.0
    assert result["goals"]["calories"] == 2200


@patch("mfp_data._client")
def test_get_nutrition_for_date_no_goals(mock_client_fn):
    day = _make_day([{"calories": 1500.0}], goals=None)
    mock_client_fn.return_value.get_date.return_value = day

    result = get_nutrition_for_date(date(2026, 5, 6))
    assert result["goals"] == {}


@patch("mfp_data._client")
def test_get_nutrition_for_date_silent_on_error(mock_client_fn):
    mock_client_fn.side_effect = Exception("no cookies")

    result = get_nutrition_for_date(date(2026, 5, 6))
    assert result == {"daily_totals": {}, "goals": {}}


# ── get_nutrition_range ───────────────────────────────────────────────────────

@patch("mfp_data._client")
def test_get_nutrition_range_one_entry_per_day(mock_client_fn):
    day = _make_day([{"calories": 2000.0}], goals={"calories": 2200})
    mock_client_fn.return_value.get_date.return_value = day

    result = get_nutrition_range(date(2026, 5, 1), date(2026, 5, 3))

    assert len(result) == 3
    dates = [r["date"] for r in result]
    assert "2026-05-01" in dates
    assert "2026-05-02" in dates
    assert "2026-05-03" in dates


@patch("mfp_data._client")
def test_get_nutrition_range_sorted_newest_first(mock_client_fn):
    day = _make_day([{"calories": 2000.0}])
    mock_client_fn.return_value.get_date.return_value = day

    result = get_nutrition_range(date(2026, 5, 1), date(2026, 5, 5))

    dates = [r["date"] for r in result]
    assert dates == sorted(dates, reverse=True)


@patch("mfp_data._client")
def test_get_nutrition_range_silent_on_error(mock_client_fn):
    mock_client_fn.side_effect = RuntimeError("auth failure")

    result = get_nutrition_range(date(2026, 5, 1), date(2026, 5, 5))
    assert result == []


@patch("mfp_data._client")
def test_get_nutrition_range_single_day(mock_client_fn):
    day = _make_day([{"calories": 1900.0}])
    mock_client_fn.return_value.get_date.return_value = day

    result = get_nutrition_range(date(2026, 5, 4), date(2026, 5, 4))
    assert len(result) == 1
    assert result[0]["date"] == "2026-05-04"
