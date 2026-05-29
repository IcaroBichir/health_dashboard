from __future__ import annotations

from datetime import date

from strava_data import fmt_distance, fmt_duration, fmt_pace, fmt_speed


def filter_runs(activities: list[dict]) -> list[dict]:
    return [a for a in activities if a.get("sport_type") == "Run"]


def runs_in_window(all_activities: list[dict], start: date) -> list[dict]:
    start_str = start.isoformat()
    return [
        a for a in all_activities
        if a.get("sport_type") == "Run"
        and a.get("start_date_local", "")[:10] >= start_str
    ]


def get_detailed_run(activity_id: int) -> dict:
    from strava_mcp.client import StravaClient
    return StravaClient().get_activity(activity_id)


def compute_run_metrics(runs: list[dict]) -> dict:
    if not runs:
        return {}

    n = len(runs)
    total_distance = sum(a.get("distance", 0) or 0 for a in runs)
    total_moving = sum(a.get("moving_time", 0) or 0 for a in runs)
    total_elapsed = sum(a.get("elapsed_time", 0) or 0 for a in runs)
    total_elevation = sum(a.get("total_elevation_gain", 0) or 0 for a in runs)
    total_calories = sum(a.get("calories", 0) or 0 for a in runs)
    total_prs = sum(a.get("pr_count", 0) or 0 for a in runs)
    total_achievements = sum(a.get("achievement_count", 0) or 0 for a in runs)

    longest = max((a.get("distance", 0) or 0 for a in runs), default=0)

    # Per-run paces (sec/km) for runs >= 1 km
    paces = []
    for a in runs:
        d = a.get("distance", 0) or 0
        t = a.get("moving_time", 0) or 0
        if d >= 1000 and t:
            paces.append(t / (d / 1000))
    best_pace = min(paces) if paces else 0
    avg_pace = (total_moving / (total_distance / 1000)) if total_distance >= 1000 else 0

    hr_runs = [a for a in runs if a.get("average_heartrate")]
    avg_hr = sum(a["average_heartrate"] for a in hr_runs) / len(hr_runs) if hr_runs else 0
    max_hr = max((a.get("max_heartrate") or 0 for a in runs), default=0)

    suffer_runs = [a for a in runs if a.get("suffer_score")]
    avg_suffer = sum(a["suffer_score"] for a in suffer_runs) / len(suffer_runs) if suffer_runs else 0

    cal_runs = [a for a in runs if a.get("calories")]
    avg_calories = total_calories / len(cal_runs) if cal_runs else 0

    speed_runs = [a for a in runs if a.get("average_speed")]
    avg_speed = sum(a["average_speed"] for a in speed_runs) / len(speed_runs) if speed_runs else 0
    max_speed = max((a.get("max_speed") or 0 for a in runs), default=0)

    unique_days = len(set(
        a.get("start_date_local", "")[:10]
        for a in runs
        if a.get("start_date_local")
    ))

    return {
        "count": n,
        "unique_days": unique_days,
        "total_distance": total_distance,
        "avg_distance": total_distance / n if n else 0,
        "longest_run": longest,
        "total_moving_time": total_moving,
        "total_elapsed_time": total_elapsed,
        "avg_moving_time": total_moving / n if n else 0,
        "avg_pace": avg_pace,
        "best_pace": best_pace,
        "total_elevation": total_elevation,
        "avg_elevation": total_elevation / n if n else 0,
        "total_calories": round(total_calories),
        "avg_calories": round(avg_calories),
        "avg_hr": round(avg_hr, 1),
        "max_hr": round(max_hr),
        "runs_with_hr": len(hr_runs),
        "avg_suffer": round(avg_suffer, 1),
        "total_prs": total_prs,
        "total_achievements": total_achievements,
        "avg_speed": avg_speed,
        "max_speed": max_speed,
    }


def build_evaluation_context(period_label: str, runs: list[dict], metrics: dict, as_of: date) -> str:
    lines = [
        f"## Running Analysis — {period_label} (as of {as_of.strftime('%B %d, %Y')})",
        "",
        "### Aggregate metrics",
    ]

    if not metrics:
        lines.append("No runs in this period.")
        return "\n".join(lines)

    lines += [
        f"- Runs: {metrics['count']} over {metrics['unique_days']} unique days",
        f"- Total distance: {fmt_distance(metrics['total_distance'])}",
        f"- Avg distance per run: {fmt_distance(metrics['avg_distance'])}",
        f"- Longest run: {fmt_distance(metrics['longest_run'])}",
        f"- Total moving time: {fmt_duration(metrics['total_moving_time'])}",
        f"- Avg pace: {fmt_pace(metrics['total_distance'], metrics['total_moving_time'])}",
    ]

    if metrics["best_pace"]:
        m, s = divmod(int(metrics["best_pace"]), 60)
        lines.append(f"- Best pace (fastest run): {m}:{s:02d} /km")

    if metrics["total_elevation"]:
        lines.append(f"- Total elevation gain: {metrics['total_elevation']:.0f} m "
                     f"(avg {metrics['avg_elevation']:.0f} m/run)")

    if metrics["avg_hr"]:
        lines.append(f"- Avg heart rate: {metrics['avg_hr']:.0f} bpm "
                     f"(max {metrics['max_hr']} bpm, {metrics['runs_with_hr']}/{metrics['count']} runs with HR)")

    if metrics["avg_suffer"]:
        lines.append(f"- Avg suffer score: {metrics['avg_suffer']:.1f}")

    if metrics["total_calories"]:
        lines.append(f"- Total calories burned: {metrics['total_calories']} kcal "
                     f"(avg {metrics['avg_calories']} kcal/run)")

    if metrics["total_prs"]:
        lines.append(f"- PRs set: {metrics['total_prs']}")

    if metrics["total_achievements"]:
        lines.append(f"- Achievements: {metrics['total_achievements']}")

    lines.append("")
    lines.append("### Individual runs (most recent first)")

    for a in sorted(runs, key=lambda x: x.get("start_date_local", ""), reverse=True):
        name = a.get("name", "Run")
        date_str = a.get("start_date_local", "")[:10]
        dist = a.get("distance", 0) or 0
        move = a.get("moving_time", 0) or 0
        hr = a.get("average_heartrate")
        elev = a.get("total_elevation_gain")
        suffer = a.get("suffer_score")
        cals = a.get("calories")
        prs = a.get("pr_count")

        parts = [f"{name} ({date_str})"]
        if dist:
            parts.append(f"{fmt_distance(dist)}")
        if dist and move:
            parts.append(f"pace {fmt_pace(dist, move)}")
        if hr:
            parts.append(f"avg HR {hr:.0f} bpm")
        if elev:
            parts.append(f"elev +{elev:.0f}m")
        if suffer:
            parts.append(f"suffer {suffer}")
        if cals:
            parts.append(f"{cals:.0f} kcal")
        if prs:
            parts.append(f"{prs} PR{'s' if prs > 1 else ''}")

        lines.append(f"- {' | '.join(parts)}")

    return "\n".join(lines)


def fmt_splits(splits: list[dict]) -> list[dict]:
    """Convert Strava splits_metric into display rows."""
    rows = []
    for s in splits:
        km = s.get("distance", 0) / 1000
        t = s.get("moving_time", 0)
        hr = s.get("average_heartrate")
        elev = s.get("elevation_difference")
        if km < 0.05:
            continue
        pace_sec = t / km if km > 0 else 0
        pm, ps = divmod(int(pace_sec), 60)
        row = {
            "km": f"{s.get('split', '?')}",
            "dist": f"{km:.2f} km",
            "pace": f"{pm}:{ps:02d} /km",
            "time": fmt_duration(t),
        }
        if hr:
            row["hr"] = f"{hr:.0f} bpm"
        if elev is not None:
            row["elev"] = f"{elev:+.0f} m"
        rows.append(row)
    return rows
