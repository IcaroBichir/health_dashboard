from __future__ import annotations

from datetime import date
from typing import Iterator

import anthropic

_MODEL = "claude-sonnet-4-6"

_SYSTEM = """\
You are a personal health and fitness assistant with access to real-time training \
and nutrition data pulled from Strava and MyFitnessPal. Answer questions about \
training load, nutrition, recovery, trends, and goals. Reference specific numbers \
from the data when relevant. Be concise."""


def _fmt_activity(a: dict) -> str:
    name = a.get("name") or a.get("sport_type", "Activity")
    dist = a.get("distance", 0)
    move = a.get("moving_time", 0)
    hr = a.get("average_heartrate")
    date_str = a.get("start_date_local", "")[:10]
    parts = [f"{name} ({date_str})"]
    if dist:
        parts.append(f"{dist / 1000:.1f} km")
    if move:
        h, rem = divmod(int(move), 3600)
        m, s = divmod(rem, 60)
        parts.append(f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")
    if hr:
        parts.append(f"avg HR {hr:.0f} bpm")
    elev = a.get("total_elevation_gain")
    if elev:
        parts.append(f"{elev:.0f} m elev")
    return " | ".join(parts)


def build_context(
    today: date,
    all_week: list[dict],
    nutrition_today: dict,
    nutrition_yesterday: dict,
    nutrition_week: list[dict],
) -> str:
    lines: list[str] = [f"## Health Data — {today.strftime('%A, %B %d, %Y')}\n"]

    # Activities this week
    if all_week:
        lines.append(f"### Activities this week ({len(all_week)} total)")
        for a in all_week:
            lines.append(f"- {_fmt_activity(a)}")
    else:
        lines.append("### No activities this week")

    lines.append("")

    # Today's nutrition
    t = nutrition_today.get("daily_totals", {})
    g = nutrition_today.get("goals", {})
    if t:
        lines.append("### Today's nutrition")
        cal_str = f"{t.get('calories', 0):.0f}"
        if g.get("calories"):
            cal_str += f" / {g['calories']:.0f} kcal goal"
        lines.append(f"- Calories: {cal_str}")
        lines.append(f"- Protein: {t.get('protein', 0):.0f}g" +
                     (f" / {g['protein']:.0f}g goal" if g.get("protein") else ""))
        lines.append(f"- Carbs: {t.get('carbohydrates', 0):.0f}g")
        lines.append(f"- Fat: {t.get('fat', 0):.0f}g")
    else:
        lines.append("### No nutrition logged today")

    lines.append("")

    # Yesterday's nutrition
    ty = nutrition_yesterday.get("daily_totals", {})
    if ty:
        lines.append("### Yesterday's nutrition")
        lines.append(f"- Calories: {ty.get('calories', 0):.0f} kcal")
        lines.append(f"- Protein: {ty.get('protein', 0):.0f}g")
        lines.append(f"- Carbs: {ty.get('carbohydrates', 0):.0f}g")
        lines.append(f"- Fat: {ty.get('fat', 0):.0f}g")

    lines.append("")

    # 7-day nutrition averages
    days_with_data = [d for d in nutrition_week if d.get("daily_totals")]
    if days_with_data:
        n = len(days_with_data)
        avg_cal = sum(d["daily_totals"].get("calories", 0) for d in days_with_data) / n
        avg_pro = sum(d["daily_totals"].get("protein", 0) for d in days_with_data) / n
        avg_carb = sum(d["daily_totals"].get("carbohydrates", 0) for d in days_with_data) / n
        avg_fat = sum(d["daily_totals"].get("fat", 0) for d in days_with_data) / n
        lines.append(f"### 7-day nutrition averages ({n} days with data)")
        lines.append(f"- Avg calories: {avg_cal:.0f} kcal/day")
        lines.append(f"- Avg protein: {avg_pro:.0f}g/day")
        lines.append(f"- Avg carbs: {avg_carb:.0f}g/day")
        lines.append(f"- Avg fat: {avg_fat:.0f}g/day")

    return "\n".join(lines)


def stream_response(messages: list[dict], context: str) -> Iterator[str]:
    """Yield text chunks from Claude, streaming the reply."""
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=_MODEL,
        max_tokens=1024,
        system=f"{_SYSTEM}\n\n{context}",
        messages=messages,
    ) as stream:
        yield from stream.text_stream
