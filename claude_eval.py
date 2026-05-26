from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dashboard_cache import DashboardCache

_ENV_FILE = Path(__file__).parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

_MODEL = "claude-sonnet-4-6"
_EVAL_TTL = 28800  # 8 hours

_cache = DashboardCache()

_EVAL_SYSTEM = """\
You are an expert running coach and sports scientist analyzing an athlete's training data. \
Provide a concise, insightful evaluation of their running performance and progress. \
Focus on training load, pace trends, consistency, recovery indicators from HR data, \
elevation work, and 2-3 specific actionable recommendations. \
Reference the actual numbers from the data. Write 3-5 short paragraphs. \
Tone: direct, coach-like, honest — not generic motivational fluff."""


def _eval_cache_key(period: str) -> str:
    return f"run_eval:{period}:{date.today().isoformat()}"


def get_run_evaluation(period: str, context: str, force: bool = False) -> str:
    """Return cached Claude evaluation for a running period, generating it if needed."""
    import anthropic

    cache_key = _eval_cache_key(period)
    if not force:
        cached = _cache.get(cache_key)
        if cached:
            return cached

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=_MODEL,
        max_tokens=900,
        system=_EVAL_SYSTEM,
        messages=[{"role": "user", "content": context}],
    )
    evaluation = response.content[0].text
    _cache.set(cache_key, evaluation, _EVAL_TTL)
    return evaluation


def evaluation_is_cached(period: str) -> bool:
    return _cache.get(_eval_cache_key(period)) is not None


def invalidate_run_evaluations() -> None:
    _cache.delete_like("run_eval:%")
