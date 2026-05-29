from __future__ import annotations

from datetime import date, timedelta

from strava_data import fmt_distance, fmt_duration, fmt_pace


def _totals(nutr_day: dict) -> dict:
    return nutr_day.get("daily_totals", {}) if nutr_day else {}


def _avg_nutrition(days: list[dict]) -> dict | None:
    valid = [d for d in days if _totals(d)]
    if not valid:
        return None
    n = len(valid)
    return {
        "n": n,
        "calories": sum(_totals(d).get("calories", 0) for d in valid) / n,
        "protein":  sum(_totals(d).get("protein", 0)  for d in valid) / n,
        "carbs":    sum(_totals(d).get("carbohydrates", 0) for d in valid) / n,
        "fat":      sum(_totals(d).get("fat", 0)       for d in valid) / n,
    }


def compute_correlation_metrics(
    activities: list[dict],
    nutrition_list: list[dict],
    start: date,
) -> dict:
    start_str = start.isoformat()

    acts = [a for a in activities if a.get("start_date_local", "")[:10] >= start_str]
    nutr_by_date: dict[str, dict] = {
        d["date"]: d for d in nutrition_list
        if d["date"] >= start_str and _totals(d)
    }

    act_dates = set(a.get("start_date_local", "")[:10] for a in acts if a.get("start_date_local"))
    nutr_dates = set(nutr_by_date.keys())
    overlap_dates = act_dates & nutr_dates

    workout_day_nutrs = [nutr_by_date[d] for d in nutr_dates if d in act_dates]
    rest_day_nutrs    = [nutr_by_date[d] for d in nutr_dates if d not in act_dates]

    # Build paired days list (sorted newest first)
    paired_days = []
    for d_str in sorted(overlap_dates, reverse=True):
        day_acts = [a for a in acts if a.get("start_date_local", "")[:10] == d_str]
        prev_str = (date.fromisoformat(d_str) - timedelta(days=1)).isoformat()
        paired_days.append({
            "date": d_str,
            "activities": day_acts,
            "nutrition": nutr_by_date[d_str],
            "pre_nutrition": nutr_by_date.get(prev_str),
        })

    # Energy balance on workout days with nutrition data
    total_consumed = sum(_totals(p["nutrition"]).get("calories", 0) for p in paired_days)
    total_burned   = sum(
        sum(a.get("calories", 0) or 0 for a in p["activities"])
        for p in paired_days
    )
    n_paired = len(paired_days)

    return {
        "total_act_days":   len(act_dates),
        "total_nutr_days":  len(nutr_dates),
        "overlap_days":     n_paired,
        "paired_days":      paired_days,
        "workout_day_avg":  _avg_nutrition(workout_day_nutrs),
        "rest_day_avg":     _avg_nutrition(rest_day_nutrs),
        "avg_consumed":     round(total_consumed / n_paired) if n_paired else 0,
        "avg_burned":       round(total_burned   / n_paired) if n_paired else 0,
        "avg_net":          round((total_consumed - total_burned) / n_paired) if n_paired else 0,
    }


def build_correlation_context(
    period_label: str,
    metrics: dict,
    as_of: date,
    body_comp: dict | None = None,
    body_comp_trend: dict | None = None,
) -> str:
    if not metrics or not metrics.get("paired_days"):
        return f"## Nutrition × Exercise — {period_label}\n\nNo days with both exercise and nutrition data."

    lines = [
        f"## Nutrition × Exercise Correlation — {period_label} (as of {as_of.strftime('%B %d, %Y')})",
        "",
    ]

    if body_comp:
        bc_parts = []
        if "weight_kg" in body_comp:
            bc_parts.append(f"weight {body_comp['weight_kg']:.1f} kg")
        if "fat_ratio_pct" in body_comp:
            bc_parts.append(f"body fat {body_comp['fat_ratio_pct']:.1f}%")
        if "muscle_mass_kg" in body_comp:
            bc_parts.append(f"muscle {body_comp['muscle_mass_kg']:.1f} kg")
        if "fat_free_mass_kg" in body_comp:
            bc_parts.append(f"fat-free mass {body_comp['fat_free_mass_kg']:.1f} kg")
        if bc_parts:
            lines += [
                f"### Body composition (most recent reading: {body_comp.get('date', 'n/a')})",
                "- " + " | ".join(bc_parts),
            ]
            if body_comp_trend:
                trend_parts = []
                if "weight_kg" in body_comp_trend:
                    trend_parts.append(f"weight {body_comp_trend['weight_kg']:+.1f} kg")
                if "fat_ratio_pct" in body_comp_trend:
                    trend_parts.append(f"body fat {body_comp_trend['fat_ratio_pct']:+.1f}%")
                if "muscle_mass_kg" in body_comp_trend:
                    trend_parts.append(f"muscle {body_comp_trend['muscle_mass_kg']:+.1f} kg")
                if trend_parts:
                    lines.append(f"- Change over period: " + " | ".join(trend_parts))
            lines.append("")

    lines += [
        "### Overview",
        f"- Workout days: {metrics['total_act_days']}",
        f"- Nutrition-logged days: {metrics['total_nutr_days']}",
        f"- Days with both (paired): {metrics['overlap_days']}",
        "",
        "Note: most workouts are morning sessions (8–10am). Same-day nutrition is "
        "predominantly post-workout fuel. The prior day's nutrition is the primary "
        "pre-workout input to analyze.",
        "",
    ]

    wo = metrics.get("workout_day_avg")
    re = metrics.get("rest_day_avg")
    if wo and re:
        lines += [
            "### Nutrition: workout days vs rest days",
            f"- Workout days ({wo['n']} days): {wo['calories']:.0f} kcal | "
            f"protein {wo['protein']:.0f}g | carbs {wo['carbs']:.0f}g | fat {wo['fat']:.0f}g",
            f"- Rest days    ({re['n']} days): {re['calories']:.0f} kcal | "
            f"protein {re['protein']:.0f}g | carbs {re['carbs']:.0f}g | fat {re['fat']:.0f}g",
            "",
        ]

    if metrics["avg_consumed"] or metrics["avg_burned"]:
        net = metrics["avg_net"]
        net_str = f"{net:+d} kcal ({'surplus' if net >= 0 else 'deficit'})"
        lines += [
            "### Average energy balance (workout days with nutrition data)",
            f"- Avg consumed: {metrics['avg_consumed']} kcal",
            f"- Avg burned (exercise): {metrics['avg_burned']} kcal",
            f"- Avg net: {net_str}",
            "",
        ]

    lines.append("### Day-by-day detail (newest first)")

    for p in metrics["paired_days"]:
        d_str = p["date"]
        day_acts = p["activities"]
        nutr = _totals(p["nutrition"])
        pre_nutr = _totals(p["pre_nutrition"]) if p["pre_nutrition"] else None

        day_lines = [f"**{d_str}**"]

        for a in day_acts:
            sport = a.get("sport_type", "Activity")
            name  = a.get("name", sport)
            dist  = a.get("distance", 0) or 0
            move  = a.get("moving_time", 0) or 0
            hr    = a.get("average_heartrate")
            hr_max = a.get("max_heartrate")
            cals  = a.get("calories") or 0
            suffer = a.get("suffer_score")
            elev  = a.get("total_elevation_gain") or 0

            parts = [f"{sport}: {name}"]
            if dist:
                parts.append(fmt_distance(dist))
            if dist and move:
                parts.append(f"pace {fmt_pace(dist, move)}")
            if hr:
                hr_str = f"avg HR {hr:.0f}"
                if hr_max:
                    hr_str += f" / max {hr_max:.0f} bpm"
                parts.append(hr_str)
            if elev:
                parts.append(f"elev +{elev:.0f}m")
            if cals:
                parts.append(f"{cals:.0f} kcal burned")
            if suffer:
                parts.append(f"suffer {suffer}")
            day_lines.append(f"  - {' | '.join(parts)}")

        # Same-day nutrition
        if nutr:
            day_lines.append(
                f"  - Same-day nutrition: {nutr.get('calories', 0):.0f} kcal | "
                f"protein {nutr.get('protein', 0):.0f}g | "
                f"carbs {nutr.get('carbohydrates', 0):.0f}g | "
                f"fat {nutr.get('fat', 0):.0f}g"
            )

        # Prior-day nutrition (pre-workout fuel for morning runners)
        if pre_nutr:
            prev_str = (date.fromisoformat(d_str) - timedelta(days=1)).isoformat()
            day_lines.append(
                f"  - Prior day ({prev_str}) nutrition: "
                f"{pre_nutr.get('calories', 0):.0f} kcal | "
                f"protein {pre_nutr.get('protein', 0):.0f}g | "
                f"carbs {pre_nutr.get('carbohydrates', 0):.0f}g | "
                f"fat {pre_nutr.get('fat', 0):.0f}g"
            )
        else:
            day_lines.append("  - Prior day nutrition: not logged")

        lines.append("\n".join(day_lines))

    return "\n\n".join(lines)
