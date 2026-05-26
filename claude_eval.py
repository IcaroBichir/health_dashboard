from __future__ import annotations

from datetime import date
from pathlib import Path

from dashboard_cache import DashboardCache

_EVAL_TTL = 28800  # 8 hours

_cache = DashboardCache()


def _eval_cache_key(period: str) -> str:
    return f"run_eval:{period}:{date.today().isoformat()}"


def get_run_evaluation(period: str, context: str = "", force: bool = False) -> str:
    """Return the cached evaluation for a period.

    Evaluations are written to the cache externally (by Claude Code via
    write_evaluation_to_cache). This function is read-only — it never
    calls an LLM directly.
    """
    cache_key = _eval_cache_key(period)
    cached = _cache.get(cache_key)
    return cached or ""


def write_evaluation_to_cache(period: str, text: str) -> None:
    """Write a Claude-generated evaluation into the cache (called by Claude Code)."""
    _cache.set(_eval_cache_key(period), text, _EVAL_TTL)


def evaluation_is_cached(period: str) -> bool:
    return bool(_cache.get(_eval_cache_key(period)))


def invalidate_run_evaluations() -> None:
    _cache.delete_like("run_eval:%")
