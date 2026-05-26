from __future__ import annotations

from datetime import date
from pathlib import Path

from dashboard_cache import DashboardCache

_EVAL_TTL = 28800  # 8 hours

_cache = DashboardCache()

# ── Running evaluations ───────────────────────────────────────────────────────

def _run_key(period: str) -> str:
    return f"run_eval:{period}:{date.today().isoformat()}"


def get_run_evaluation(period: str) -> str:
    return _cache.get(_run_key(period)) or ""


def write_evaluation_to_cache(period: str, text: str) -> None:
    _cache.set(_run_key(period), text, _EVAL_TTL)


def evaluation_is_cached(period: str) -> bool:
    return bool(_cache.get(_run_key(period)))


# ── Correlation (nutrition × exercise) evaluations ───────────────────────────

def _corr_key(period: str) -> str:
    return f"corr_eval:{period}:{date.today().isoformat()}"


def get_correlation_evaluation(period: str) -> str:
    return _cache.get(_corr_key(period)) or ""


def write_correlation_evaluation_to_cache(period: str, text: str) -> None:
    _cache.set(_corr_key(period), text, _EVAL_TTL)


def correlation_evaluation_is_cached(period: str) -> bool:
    return bool(_cache.get(_corr_key(period)))


# ── Invalidation ──────────────────────────────────────────────────────────────

def invalidate_run_evaluations() -> None:
    _cache.delete_like("run_eval:%")


def invalidate_all_evaluations() -> None:
    _cache.delete_like("run_eval:%")
    _cache.delete_like("corr_eval:%")
