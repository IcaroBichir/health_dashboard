import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from strava_data import (
    SPORT_EMOJI,
    fmt_distance,
    fmt_duration,
    fmt_pace,
    fmt_speed,
    get_activities_in_range,
)
from mfp_data import get_nutrition_for_date, get_nutrition_range
from withings_data import get_withings_measurements, latest_measurement, body_comp_trend
from running_data import (
    runs_in_window,
    compute_run_metrics,
    build_evaluation_context,
    get_detailed_run,
    fmt_splits,
)
from claude_eval import (
    get_run_evaluation,
    evaluation_is_cached,
    invalidate_run_evaluations,
    get_correlation_evaluation,
    write_correlation_evaluation_to_cache,
    correlation_evaluation_is_cached,
    invalidate_all_evaluations,
)
from correlation_data import (
    compute_correlation_metrics,
    build_correlation_context,
)

_CHAT_ENABLED = os.environ.get("ENABLE_CLAUDE_CHAT", "0").strip() == "1"
if _CHAT_ENABLED:
    from claude_chat import build_context, stream_response

st.set_page_config(page_title="Health Dashboard", layout="wide", page_icon="🏃")

today = date.today()
yesterday = today - timedelta(days=1)
week_start = today - timedelta(days=6)
fifteen_start = today - timedelta(days=14)
month_start = today - timedelta(days=29)

_CONFIG_PATH = Path(__file__).parent / ".streamlit" / "config.toml"

# ── Theme definitions ─────────────────────────────────────────────────────────

THEMES: dict[str, dict] = {
    "Clean Light": {
        "base": "light",
        "primaryColor": "#1B6CA8",
        "backgroundColor": "#FFFFFF",
        "secondaryBackgroundColor": "#F0F4F8",
        "textColor": "#1A1A2E",
    },
    "Forest": {
        "base": "light",
        "primaryColor": "#2D7D46",
        "backgroundColor": "#FAFFF9",
        "secondaryBackgroundColor": "#EEF4EC",
        "textColor": "#1A2E1E",
    },
    "Warm Sand": {
        "base": "light",
        "primaryColor": "#C25E2A",
        "backgroundColor": "#FDFAF5",
        "secondaryBackgroundColor": "#F2EDE3",
        "textColor": "#2E1A0E",
    },
    "Dark Navy": {
        "base": "dark",
        "primaryColor": "#00B4D8",
        "backgroundColor": "#0D1B2A",
        "secondaryBackgroundColor": "#1B2F45",
        "textColor": "#E0EAF4",
    },
    "Dark Slate": {
        "base": "dark",
        "primaryColor": "#A78BFA",
        "backgroundColor": "#1A1A2E",
        "secondaryBackgroundColor": "#16213E",
        "textColor": "#E8E8F8",
    },
}


def _read_current_theme() -> str:
    """Return the name of the currently active theme, or the first theme as fallback."""
    try:
        text = _CONFIG_PATH.read_text()
        for name, t in THEMES.items():
            if f'primaryColor = "{t["primaryColor"]}"' in text:
                return name
    except OSError:
        pass
    return next(iter(THEMES))


def _write_theme(name: str) -> None:
    t = THEMES[name]
    _CONFIG_PATH.write_text(
        f'[theme]\n'
        f'base = "{t["base"]}"\n'
        f'primaryColor = "{t["primaryColor"]}"\n'
        f'backgroundColor = "{t["backgroundColor"]}"\n'
        f'secondaryBackgroundColor = "{t["secondaryBackgroundColor"]}"\n'
        f'textColor = "{t["textColor"]}"\n'
        f'font = "sans serif"\n'
    )


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _delete_from_sqlite(db_path: Path, pattern: str, like: bool = False) -> None:
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as conn:
        op = "LIKE" if like else "="
        conn.execute(f"DELETE FROM cache WHERE key {op} ?", (pattern,))


def force_api_refresh(start: date) -> None:
    """Bypass local SQLite caches from start up to today."""
    strava_db = Path.home() / ".config" / "strava-mcp" / "cache.db"
    mfp_db    = Path.home() / ".config" / "mfp-mcp"    / "cache.db"

    d = today
    while d >= start:
        _delete_from_sqlite(strava_db, f"activities_day:{d.isoformat()}")
        _delete_from_sqlite(mfp_db,    f"diary:%:{d.isoformat()}", like=True)
        d -= timedelta(days=1)

    _delete_from_sqlite(strava_db, "athlete_stats:%", like=True)
    st.cache_data.clear()


# ── Sidebar: theme picker ─────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Theme")
    current_theme = _read_current_theme()
    chosen = st.radio(
        "Choose a theme",
        list(THEMES.keys()),
        index=list(THEMES.keys()).index(current_theme),
        label_visibility="collapsed",
        format_func=lambda n: n,
    )

    # Color swatches preview
    swatch_cols = st.columns(4)
    t = THEMES[chosen]
    for col, (label, key) in zip(swatch_cols, [
        ("BG",     "backgroundColor"),
        ("Card",   "secondaryBackgroundColor"),
        ("Text",   "textColor"),
        ("Accent", "primaryColor"),
    ]):
        col.markdown(
            f'<div title="{label}" style="background:{t[key]};height:18px;'
            f'border-radius:4px;border:1px solid #ccc"></div>',
            unsafe_allow_html=True,
        )

    if chosen != current_theme:
        if st.button("Apply theme", use_container_width=True):
            _write_theme(chosen)
            st.success("Theme saved — reloading…")
            st.rerun()
    else:
        st.caption(f"Active: {current_theme}")


# ── Data fetching ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_activities(start: date, end: date) -> list[dict]:
    return get_activities_in_range(start, end)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_nutrition(d: date) -> dict:
    return get_nutrition_for_date(d)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_nutrition_range(start: date, end: date) -> list[dict]:
    return get_nutrition_range(start, end)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_withings(start: date, end: date) -> list[dict]:
    return get_withings_measurements(start, end)


# ── Rendering helpers ─────────────────────────────────────────────────────────

def _activity_stats(a: dict) -> str:
    sport = a.get("sport_type", "")
    dist = a.get("distance")
    duration = a.get("moving_time")
    hr = a.get("average_heartrate")
    parts = []
    if dist:
        parts.append(fmt_distance(dist))
    if duration:
        parts.append(fmt_duration(duration))
    if dist and duration:
        if sport == "Run":
            parts.append(fmt_pace(dist, duration))
        elif sport in ("Ride", "VirtualRide"):
            parts.append(fmt_speed(a.get("average_speed")))
    if hr:
        parts.append(f"{hr:.0f} bpm")
    return "  ·  ".join(parts)


def render_activity(a: dict) -> None:
    sport = a.get("sport_type", "Other")
    emoji = SPORT_EMOJI.get(sport, "⚡")
    name = a.get("name", sport)
    time_str = a.get("start_date_local", "")[:16].replace("T", " ")
    stats = _activity_stats(a)
    cals = int(a.get("calories") or 0)

    with st.container(border=True):
        left, mid, right = st.columns([2, 3, 1])
        left.markdown(f"**{emoji} {name}**")
        left.caption(time_str)
        if stats:
            mid.caption(stats)
        if cals:
            right.metric("Burned", f"{cals} kcal")


def render_nutrition(data: dict) -> None:
    totals = data.get("daily_totals", {})
    goals = data.get("goals", {})
    if not totals:
        st.caption("No nutrition logged")
        return
    calories = totals.get("calories", 0)
    cal_goal = goals.get("calories", 0)
    protein = totals.get("protein", 0)
    carbs = totals.get("carbohydrates", 0)
    fat = totals.get("fat", 0)

    with st.container(border=True):
        remaining = round(cal_goal - calories) if cal_goal else None
        delta_str = f"{remaining:+.0f} rem" if remaining is not None else None
        delta_color = "normal" if (remaining is None or remaining >= 0) else "inverse"
        cal_label = f"{calories:.0f} / {cal_goal:.0f}" if cal_goal else f"{calories:.0f} kcal"

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Calories", cal_label, delta=delta_str, delta_color=delta_color)
        c2.metric("Protein", f"{protein:.0f} g",
                  delta=f"goal {goals['protein']:.0f}" if "protein" in goals else None,
                  delta_color="off")
        c3.metric("Carbs", f"{carbs:.0f} g")
        c4.metric("Fat", f"{fat:.0f} g")


def render_calorie_balance(calories_consumed: int, calories_burned: int) -> None:
    if not calories_consumed and not calories_burned:
        return
    net = calories_consumed - calories_burned
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Consumed", f"{calories_consumed} kcal" if calories_consumed else "—")
        c2.metric("Burned", f"{calories_burned} kcal" if calories_burned else "—")
        c3.metric("Net", f"{net:+d} kcal")


def render_body_comp(measurement: dict, trend: dict | None = None, compact: bool = False) -> None:
    """Render a body composition card. compact=True shows fewer fields."""
    date_str = measurement.get("date", "")
    weight = measurement.get("weight_kg")
    fat_pct = measurement.get("fat_ratio_pct")
    muscle = measurement.get("muscle_mass_kg")
    fat_free = measurement.get("fat_free_mass_kg")
    fat_mass = measurement.get("fat_mass_kg")

    with st.container(border=True):
        if date_str:
            st.caption(f"Scale reading: {date_str}")

        if compact:
            c1, c2, c3 = st.columns(3)
            c1.metric("Weight", f"{weight:.1f} kg" if weight else "—",
                      delta=f"{trend['weight_kg']:+.1f} kg" if trend and "weight_kg" in trend else None,
                      delta_color="off")
            c2.metric("Body Fat", f"{fat_pct:.1f}%" if fat_pct else "—",
                      delta=f"{trend['fat_ratio_pct']:+.1f}%" if trend and "fat_ratio_pct" in trend else None,
                      delta_color="inverse")
            c3.metric("Muscle", f"{muscle:.1f} kg" if muscle else "—",
                      delta=f"{trend['muscle_mass_kg']:+.1f} kg" if trend and "muscle_mass_kg" in trend else None,
                      delta_color="normal")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Weight", f"{weight:.2f} kg" if weight else "—",
                      delta=f"{trend['weight_kg']:+.2f} kg" if trend and "weight_kg" in trend else None,
                      delta_color="off")
            c2.metric("Body Fat", f"{fat_pct:.1f}%" if fat_pct else "—",
                      delta=f"{trend['fat_ratio_pct']:+.1f}%" if trend and "fat_ratio_pct" in trend else None,
                      delta_color="inverse")
            c3.metric("Muscle Mass", f"{muscle:.2f} kg" if muscle else "—",
                      delta=f"{trend['muscle_mass_kg']:+.2f} kg" if trend and "muscle_mass_kg" in trend else None,
                      delta_color="normal")
            c4.metric("Fat-Free Mass", f"{fat_free:.2f} kg" if fat_free else "—",
                      delta=f"{trend['fat_free_mass_kg']:+.2f} kg" if trend and "fat_free_mass_kg" in trend else None,
                      delta_color="normal")

            if fat_mass or measurement.get("bone_mass_kg") or measurement.get("hydration_kg"):
                c5, c6, c7, _ = st.columns(4)
                c5.metric("Fat Mass", f"{fat_mass:.2f} kg" if fat_mass else "—")
                c6.metric("Bone Mass", f"{measurement.get('bone_mass_kg', 0):.2f} kg"
                          if measurement.get("bone_mass_kg") else "—")
                c7.metric("Hydration", f"{measurement.get('hydration_kg', 0):.2f} kg"
                          if measurement.get("hydration_kg") else "—")


def _nutrition_avgs(days: list[dict]) -> dict | None:
    with_data = [d for d in days if d.get("daily_totals")]
    if not with_data:
        return None
    n = len(with_data)
    return {
        "n":        n,
        "calories": sum(d["daily_totals"].get("calories", 0)       for d in with_data) / n,
        "protein":  sum(d["daily_totals"].get("protein", 0)        for d in with_data) / n,
        "carbs":    sum(d["daily_totals"].get("carbohydrates", 0)  for d in with_data) / n,
        "fat":      sum(d["daily_totals"].get("fat", 0)            for d in with_data) / n,
    }


def _total_burned(activities: list[dict]) -> int:
    return round(sum(a.get("calories", 0) for a in activities))


# ── Header ────────────────────────────────────────────────────────────────────

hdr_col, btn_col, api_col = st.columns([5, 1, 1])
hdr_col.title("Health Dashboard")
hdr_col.caption(today.strftime("%A, %B %d, %Y"))

if btn_col.button("↺ Refresh", use_container_width=True, help="Clear in-memory cache and reload"):
    st.cache_data.clear()
    st.rerun()

if api_col.button("⬇ Pull API", use_container_width=True, help="Bypass local cache and fetch latest from Strava & MFP"):
    st.session_state["confirm_api_pull"] = True

if st.session_state.get("confirm_api_pull"):
    _REFRESH_RANGES = {
        "Today":        today,
        "Yesterday":    yesterday,
        "Last 7 Days":  week_start,
        "Last 30 Days": month_start,
    }
    sel_col, yes_col, no_col, _ = st.columns([2, 1, 1, 4])
    selected_range = sel_col.selectbox(
        "Range",
        list(_REFRESH_RANGES.keys()),
        index=3,
        label_visibility="collapsed",
    )
    start_of_range = _REFRESH_RANGES[selected_range]
    regen_evals = st.checkbox(
        "Regenerate AI coach evaluations (Running tab)",
        value=False,
        help="Invalidates cached Claude evaluations so they are regenerated on next view.",
    )
    st.warning(
        f"This will make live API calls to **Strava** and **MyFitnessPal** "
        f"for **{selected_range}**, bypassing the local cache. "
        "Both services rate-limit requests — use sparingly.",
        icon="⚠️",
    )
    if yes_col.button("Confirm", type="primary", use_container_width=True):
        st.session_state.pop("confirm_api_pull", None)
        with st.spinner(f"Clearing cache and fetching {selected_range} from API…"):
            force_api_refresh(start_of_range)
            if regen_evals:
                invalidate_all_evaluations()
        st.rerun()
    if no_col.button("Cancel", use_container_width=True):
        st.session_state.pop("confirm_api_pull", None)
        st.rerun()

# ── Fetch data ────────────────────────────────────────────────────────────────

with st.spinner("Loading…"):
    all_week  = fetch_activities(week_start, today)
    all_month = fetch_activities(month_start, today)
    nutrition_today     = fetch_nutrition(today)
    nutrition_yesterday = fetch_nutrition(yesterday)
    nutrition_week  = fetch_nutrition_range(week_start, today)
    nutrition_month = fetch_nutrition_range(month_start, today)
    withings_month  = fetch_withings(month_start, today)

today_acts     = [a for a in all_week if a.get("start_date_local", "")[:10] == str(today)]
yesterday_acts = [a for a in all_week if a.get("start_date_local", "")[:10] == str(yesterday)]

# Per-day lookups used by the 7-day tab
acts_by_day: dict[str, list[dict]] = {}
for _a in all_week:
    _day = _a.get("start_date_local", "")[:10]
    if _day:
        acts_by_day.setdefault(_day, []).append(_a)

nutr_by_day: dict[str, dict] = {d["date"]: d for d in nutrition_week}

today_burned     = _total_burned(today_acts)
yesterday_burned = _total_burned(yesterday_acts)
week_burned      = _total_burned(all_week)
month_burned     = _total_burned(all_month)

def _consumed(data: dict) -> int:
    return round(data.get("daily_totals", {}).get("calories", 0))

today_consumed     = _consumed(nutrition_today)
yesterday_consumed = _consumed(nutrition_yesterday)
week_consumed      = round(sum(_consumed(d) for d in nutrition_week))
month_consumed     = round(sum(_consumed(d) for d in nutrition_month))

latest_body_comp   = latest_measurement(withings_month)
month_body_trend   = body_comp_trend(withings_month)

# ── Nutrition availability check (determines if correlation tab is shown) ─────

def _has_nutrition(nutrition_list: list[dict]) -> bool:
    return any(d.get("daily_totals") for d in nutrition_list)


# If the regular fetch returned no data, try a direct (cache-bypassing) fetch.
_nutrition_month = nutrition_month
if not _has_nutrition(_nutrition_month):
    try:
        _nutrition_month = get_nutrition_range(month_start, today)
    except Exception:
        pass

_show_correlation_tab = _has_nutrition(_nutrition_month)

# ── Tabs ──────────────────────────────────────────────────────────────────────

_tab_names = ["Today & Yesterday", "Last 7 Days", "Last 30 Days", "🏃 Running"]
if _show_correlation_tab:
    _tab_names.append("🔗 Nutrition × Exercise")

_tabs = st.tabs(_tab_names)
tab1, tab2, tab3, tab4 = _tabs[:4]
tab5 = _tabs[4] if _show_correlation_tab else None

# ── Tab 1: Today & Yesterday ──────────────────────────────────────────────────

with tab1:
    col_today, col_yesterday = st.columns(2)

    with col_today:
        st.subheader(f"Today · {today.strftime('%b %d')}")
        st.markdown("**Exercise**")
        if today_acts:
            for a in today_acts:
                render_activity(a)
        else:
            st.caption("No activities yet")
        st.markdown("**Nutrition**")
        render_nutrition(nutrition_today)
        st.markdown("**Calorie Balance**")
        render_calorie_balance(today_consumed, today_burned)
        if latest_body_comp:
            st.markdown("**Body Composition**")
            render_body_comp(latest_body_comp, compact=True)

    with col_yesterday:
        st.subheader(f"Yesterday · {yesterday.strftime('%b %d')}")
        st.markdown("**Exercise**")
        if yesterday_acts:
            for a in yesterday_acts:
                render_activity(a)
        else:
            st.caption("No activities")
        st.markdown("**Nutrition**")
        render_nutrition(nutrition_yesterday)
        st.markdown("**Calorie Balance**")
        render_calorie_balance(yesterday_consumed, yesterday_burned)

# ── Tab 2: Last 7 Days ────────────────────────────────────────────────────────

with tab2:
    # ── Weekly summary row ───────────────────────────────────────────────────
    runs_w = [a for a in all_week if a.get("sport_type") == "Run"]
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.metric("Days", 7)
    s2.metric("Activities", len(all_week))
    s3.metric("Run Distance", fmt_distance(sum(a.get("distance", 0) for a in runs_w)))
    s4.metric("Total Time", fmt_duration(sum(a.get("moving_time", 0) for a in all_week)))
    s5.metric("Total Burned", f"{week_burned} kcal")
    s6.metric("Total Consumed", f"{week_consumed} kcal")

    withings_7d = [m for m in withings_month if m["date"] >= week_start.isoformat()]
    latest_bc_7d = latest_measurement(withings_7d)
    trend_7d = body_comp_trend(withings_7d)
    if latest_bc_7d:
        st.markdown("**Body Composition**")
        if len(withings_7d) >= 2:
            oldest_7d = withings_7d[-1]
            st.caption(
                f"Most recent reading: **{latest_bc_7d['date']}**. "
                f"Trend deltas vs {oldest_7d['date']} ({len(withings_7d)} readings this week)."
            )
        else:
            st.caption(f"Most recent reading: **{latest_bc_7d['date']}**. Only 1 reading this week — no trend.")
        render_body_comp(latest_bc_7d, trend=trend_7d)

    st.divider()

    # ── Per-day breakdown ────────────────────────────────────────────────────
    for i in range(7):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        day_acts = acts_by_day.get(d_str, [])
        day_nutr = nutr_by_day.get(d_str, {"daily_totals": {}, "goals": {}})
        day_burned   = _total_burned(day_acts)
        day_consumed = _consumed(day_nutr)

        label = "Today" if i == 0 else ("Yesterday" if i == 1 else d.strftime("%A"))
        st.subheader(f"{label} · {d.strftime('%b %d')}")

        ex_col, nutr_col = st.columns(2)
        with ex_col:
            st.markdown("**Exercise**")
            if day_acts:
                for a in day_acts:
                    render_activity(a)
            else:
                st.caption("No activities")
        with nutr_col:
            st.markdown("**Nutrition**")
            render_nutrition(day_nutr)

        st.markdown("**Calorie Balance**")
        render_calorie_balance(day_consumed, day_burned)

        if i < 6:
            st.divider()

# ── Tab 3: Last 30 Days ───────────────────────────────────────────────────────

with tab3:
    st.subheader(f"Last 30 Days · {month_start.strftime('%b %d')} – {today.strftime('%b %d')}")

    runs_m  = [a for a in all_month if a.get("sport_type") == "Run"]
    rides_m = [a for a in all_month if a.get("sport_type") in ("Ride", "VirtualRide")]
    lifts_m = [a for a in all_month if a.get("sport_type") == "WeightTraining"]
    avg_burned_month = round(month_burned / 30)

    st.markdown("**Exercise**")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Activities", len(all_month))
    m2.metric("Runs / Rides / Lifts", f"{len(runs_m)} / {len(rides_m)} / {len(lifts_m)}")
    m3.metric("Run Distance", fmt_distance(sum(a.get("distance", 0) for a in runs_m)))
    m4.metric("Total Time", fmt_duration(sum(a.get("moving_time", 0) for a in all_month)))
    m5.metric("Calories Burned", f"{month_burned} kcal")

    avgs_m = _nutrition_avgs(nutrition_month)
    if avgs_m:
        st.markdown("**Nutrition**")
        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Avg Calories", f"{avgs_m['calories']:.0f} kcal",
                  delta=f"{avgs_m['n']} days logged", delta_color="off")
        n2.metric("Avg Protein", f"{avgs_m['protein']:.0f} g")
        n3.metric("Avg Carbs",   f"{avgs_m['carbs']:.0f} g")
        n4.metric("Avg Fat",     f"{avgs_m['fat']:.0f} g")

    st.markdown("**Calorie Balance (30-day total)**")
    render_calorie_balance(month_consumed, month_burned)

    if latest_body_comp:
        st.markdown("**Body Composition**")
        if len(withings_month) >= 2:
            oldest = withings_month[-1]
            st.caption(
                f"Scale readings: {oldest['date']} → {latest_body_comp['date']} "
                f"({len(withings_month)} readings). Deltas show change over that span."
            )
        render_body_comp(latest_body_comp, trend=month_body_trend)

# ── Tab 4: Running ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_detailed_run(activity_id: int) -> dict:
    return get_detailed_run(activity_id)


def _fmt_metric_pace(sec_per_km: float) -> str:
    if not sec_per_km:
        return "—"
    m, s = divmod(int(sec_per_km), 60)
    return f"{m}:{s:02d} /km"


def _render_run_metrics(metrics: dict) -> None:
    if not metrics:
        st.caption("No runs in this period.")
        return

    r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
    r1c1.metric("Runs", metrics["count"])
    r1c2.metric("Total Distance", fmt_distance(metrics["total_distance"]))
    r1c3.metric("Avg Distance", fmt_distance(metrics["avg_distance"]))
    r1c4.metric("Longest Run", fmt_distance(metrics["longest_run"]))
    r1c5.metric("Total Time", fmt_duration(metrics["total_moving_time"]))

    r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
    r2c1.metric("Avg Pace", _fmt_metric_pace(metrics["avg_pace"]))
    r2c2.metric("Best Pace", _fmt_metric_pace(metrics["best_pace"]))
    r2c3.metric("Total Elev Gain", f"{metrics['total_elevation']:.0f} m" if metrics["total_elevation"] else "—")
    r2c4.metric("Avg Elev / Run", f"{metrics['avg_elevation']:.0f} m" if metrics["avg_elevation"] else "—")
    r2c5.metric("Unique Days", metrics["unique_days"])

    r3c1, r3c2, r3c3, r3c4, r3c5 = st.columns(5)
    r3c1.metric("Avg HR", f"{metrics['avg_hr']:.0f} bpm" if metrics["avg_hr"] else "—")
    r3c2.metric("Max HR", f"{metrics['max_hr']} bpm" if metrics["max_hr"] else "—")
    r3c3.metric("Total Calories", f"{metrics['total_calories']} kcal" if metrics["total_calories"] else "—")
    r3c4.metric("Avg Calories", f"{metrics['avg_calories']} kcal" if metrics["avg_calories"] else "—")
    r3c5_parts = []
    if metrics["avg_suffer"]:
        r3c5_parts.append(f"Suffer: {metrics['avg_suffer']:.1f}")
    if metrics["total_prs"]:
        r3c5_parts.append(f"PRs: {metrics['total_prs']}")
    if r3c5_parts:
        r3c5.metric("Suffer / PRs", " · ".join(r3c5_parts))
    elif metrics["total_achievements"]:
        r3c5.metric("Achievements", metrics["total_achievements"])


_PENDING_DIR = Path.home() / ".config" / "health-dashboard" / "pending_evals"


def _pending_path(period: str) -> Path:
    return _PENDING_DIR / f"{period}.txt"


def _render_eval_box(period: str, runs: list[dict], metrics: dict) -> None:
    """Render the Claude coach evaluation box.

    Evaluations are generated by Claude Code (not a standalone API key).
    Clicking the button saves the context to a file so the user can ask
    Claude Code to generate it; the result is then written back to cache.
    """
    st.markdown("**🤖 AI Coach Evaluation**")
    with st.container(border=True):
        is_cached = evaluation_is_cached(period)

        if is_cached:
            text = get_run_evaluation(period)
            st.markdown(text)
            st.divider()
            btn_col, _ = st.columns([1, 3])
            if btn_col.button("↺ Request new evaluation", key=f"eval_btn_{period}", use_container_width=True):
                ctx = build_evaluation_context(period, runs, metrics, today)
                _PENDING_DIR.mkdir(parents=True, exist_ok=True)
                _pending_path(period).write_text(ctx)
                invalidate_run_evaluations()
                st.info(
                    f"Context saved. Ask Claude Code: **\"Generate my running evaluations\"**, then restart the dashboard to see it.",
                    icon="💬",
                )
        else:
            pending = _pending_path(period)
            if pending.exists():
                st.info(
                    "Context is ready. Ask Claude Code: **\"Generate my running evaluations\"**, then restart the dashboard to see it.",
                    icon="💬",
                )
            else:
                btn_col, _ = st.columns([1, 3])
                if btn_col.button("✨ Request evaluation", key=f"eval_btn_{period}", use_container_width=True):
                    ctx = build_evaluation_context(period, runs, metrics, today)
                    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
                    _pending_path(period).write_text(ctx)
                    st.info(
                        "Context saved. Ask Claude Code: **\"Generate my running evaluations\"**",
                        icon="💬",
                    )
                else:
                    st.caption("Click **Request evaluation** — Claude Code will generate it from this session.")


def _render_detailed_run_card(a: dict) -> None:
    """Render one detailed run activity inside an expander."""
    name = a.get("name", "Run")
    date_str = a.get("start_date_local", "")[:10]
    time_str = a.get("start_date_local", "")[:16].replace("T", " ")
    dist = a.get("distance", 0) or 0
    move = a.get("moving_time", 0) or 0
    elapsed = a.get("elapsed_time", 0) or 0
    hr_avg = a.get("average_heartrate")
    hr_max = a.get("max_heartrate")
    elev = a.get("total_elevation_gain") or 0
    suffer = a.get("suffer_score")
    cals = a.get("calories") or 0
    prs = a.get("pr_count") or 0
    achievements = a.get("achievement_count") or 0
    avg_speed = a.get("average_speed") or 0
    max_speed = a.get("max_speed") or 0

    label_parts = [f"🏃 {name}", date_str]
    if dist:
        label_parts.append(fmt_distance(dist))
    if dist and move:
        label_parts.append(fmt_pace(dist, move))

    with st.expander(" · ".join(label_parts)):
        st.caption(f"Started {time_str}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Distance", fmt_distance(dist))
        c2.metric("Moving Time", fmt_duration(move))
        c3.metric("Pace", fmt_pace(dist, move))
        c4.metric("Avg Speed", fmt_speed(avg_speed) if avg_speed else "—")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Avg HR", f"{hr_avg:.0f} bpm" if hr_avg else "—")
        c6.metric("Max HR", f"{hr_max:.0f} bpm" if hr_max else "—")
        c7.metric("Elapsed Time", fmt_duration(elapsed))
        c8.metric("Max Speed", fmt_speed(max_speed) if max_speed else "—")

        c9, c10, c11, c12 = st.columns(4)
        c9.metric("Elevation Gain", f"{elev:.0f} m" if elev else "—")
        c10.metric("Calories", f"{cals:.0f} kcal" if cals else "—")
        c11.metric("Suffer Score", suffer if suffer else "—")
        prs_label = f"{prs} PR{'s' if prs > 1 else ''}" if prs else "—"
        c12.metric("PRs / Achievements", f"{prs_label} / {achievements}")

        # Fetch detailed data for cadence and splits
        act_id = a.get("id")
        if act_id:
            try:
                detailed = fetch_detailed_run(act_id)
                cadence = detailed.get("average_cadence")
                perc_effort = detailed.get("perceived_exertion")
                avg_watts = detailed.get("average_watts")
                splits = detailed.get("splits_metric") or []

                extra_cols = [x for x in [
                    ("Avg Cadence", f"{cadence:.0f} spm" if cadence else None),
                    ("Perceived Effort", str(perc_effort) if perc_effort else None),
                    ("Avg Power", f"{avg_watts:.0f} W" if avg_watts else None),
                ] if x[1]]

                if extra_cols:
                    ex_cols = st.columns(len(extra_cols))
                    for col, (label, val) in zip(ex_cols, extra_cols):
                        col.metric(label, val)

                if splits:
                    rows = fmt_splits(splits)
                    if rows:
                        st.markdown("**Per-km Splits**")
                        headers = list(rows[0].keys())
                        col_widths = [1] * len(headers)
                        hcols = st.columns(col_widths)
                        for hcol, h in zip(hcols, headers):
                            hcol.caption(h.upper())
                        for row in rows:
                            rcols = st.columns(col_widths)
                            for rcol, h in zip(rcols, headers):
                                rcol.write(row.get(h, ""))
            except Exception:
                pass


with tab4:
    st.subheader("Running")

    runs_30d = runs_in_window(all_month, month_start)
    runs_15d = runs_in_window(all_month, fifteen_start)
    runs_7d  = runs_in_window(all_month, week_start)

    metrics_30d = compute_run_metrics(runs_30d)
    metrics_15d = compute_run_metrics(runs_15d)
    metrics_7d  = compute_run_metrics(runs_7d)

    # ── 7-day summary + individual runs ───────────────────────────────────────
    st.markdown(f"### 📅 Last 7 Days · {week_start.strftime('%b %d')} – {today.strftime('%b %d')}")
    _render_run_metrics(metrics_7d)

    if runs_7d:
        st.markdown("**Individual Runs**")
        for run in sorted(runs_7d, key=lambda x: x.get("start_date_local", ""), reverse=True):
            _render_detailed_run_card(run)

    _render_eval_box("7d", runs_7d, metrics_7d)

    st.divider()

    # ── 15-day summary ────────────────────────────────────────────────────────
    st.markdown(f"### 📅 Last 15 Days · {fifteen_start.strftime('%b %d')} – {today.strftime('%b %d')}")
    _render_run_metrics(metrics_15d)
    _render_eval_box("15d", runs_15d, metrics_15d)

    st.divider()

    # ── 30-day summary ────────────────────────────────────────────────────────
    st.markdown(f"### 📅 Last 30 Days · {month_start.strftime('%b %d')} – {today.strftime('%b %d')}")
    _render_run_metrics(metrics_30d)
    _render_eval_box("30d", runs_30d, metrics_30d)

# ── Tab 5: Nutrition × Exercise (conditional) ────────────────────────────────

_CORR_SYSTEM = """\
You are an expert sports nutritionist and endurance coach analyzing an athlete's \
nutrition, exercise, and body composition data. The athlete runs primarily in the \
morning (8–10am), so the prior day's nutrition is the primary pre-workout fuel source. \
Analyze: (1) how prior-day carbs, calories, and protein correlate with next-day \
pace, HR, and suffer score; (2) calorie balance sustainability on hard training days; \
(3) whether protein intake supports recovery between sessions; \
(4) patterns in nutrition on workout days vs rest days; \
(5) whether the calorie balance and macros are consistent with the body composition \
trend shown by the Withings scale (weight, fat%, muscle mass) — call out if the data \
supports or contradicts the athlete's likely goals. \
Give 2-3 specific, data-driven recommendations. Reference actual dates and numbers \
where patterns are clear. Write 4-6 short paragraphs. \
Tone: direct, analytical — not generic nutrition advice.\
"""

_CORR_PENDING_DIR = Path.home() / ".config" / "health-dashboard" / "pending_corr_evals"


def _corr_pending_path(period: str) -> Path:
    return _CORR_PENDING_DIR / f"{period}.txt"


def _render_corr_metrics(metrics: dict) -> None:
    if not metrics.get("overlap_days"):
        st.caption("No days found with both exercise and nutrition data.")
        return

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("Days w/ Both", metrics["overlap_days"])
    r1c2.metric("Workout Days", metrics["total_act_days"])
    r1c3.metric("Nutrition Days", metrics["total_nutr_days"])
    net = metrics["avg_net"]
    r1c4.metric("Avg Net Balance", f"{net:+d} kcal",
                delta="surplus" if net >= 0 else "deficit",
                delta_color="normal" if net >= 0 else "inverse")

    wo = metrics.get("workout_day_avg")
    re = metrics.get("rest_day_avg")
    if wo and re:
        st.markdown("**Nutrition: workout days vs rest days**")
        wc1, wc2, wc3, wc4 = st.columns(4)
        wc1.metric("Calories (workout)", f"{wo['calories']:.0f} kcal",
                   delta=f"{wo['calories'] - re['calories']:+.0f} vs rest", delta_color="off")
        wc2.metric("Protein (workout)", f"{wo['protein']:.0f} g",
                   delta=f"{wo['protein'] - re['protein']:+.0f} vs rest", delta_color="off")
        wc3.metric("Carbs (workout)", f"{wo['carbs']:.0f} g",
                   delta=f"{wo['carbs'] - re['carbs']:+.0f} vs rest", delta_color="off")
        wc4.metric("Fat (workout)", f"{wo['fat']:.0f} g",
                   delta=f"{wo['fat'] - re['fat']:+.0f} vs rest", delta_color="off")

    if metrics["avg_consumed"] or metrics["avg_burned"]:
        st.markdown("**Energy balance (workout days with nutrition data)**")
        ec1, ec2, ec3 = st.columns(3)
        ec1.metric("Avg Consumed", f"{metrics['avg_consumed']} kcal")
        ec2.metric("Avg Burned", f"{metrics['avg_burned']} kcal")
        ec3.metric("Avg Net", f"{metrics['avg_net']:+d} kcal")


def _render_corr_eval_box(
    period: str,
    metrics: dict,
    body_comp: dict | None = None,
    bc_trend: dict | None = None,
) -> None:
    st.markdown("**🤖 AI Coach Evaluation**")
    with st.container(border=True):
        is_cached = correlation_evaluation_is_cached(period)

        if is_cached:
            text = get_correlation_evaluation(period)
            st.markdown(text)
            st.divider()
            btn_col, _ = st.columns([1, 3])
            if btn_col.button("↺ Request new evaluation", key=f"corr_btn_{period}", use_container_width=True):
                ctx = build_correlation_context(
                    f"Last {period.replace('d', ' Days')}",
                    metrics, today,
                    body_comp=body_comp,
                    body_comp_trend=bc_trend,
                )
                _CORR_PENDING_DIR.mkdir(parents=True, exist_ok=True)
                _corr_pending_path(period).write_text(ctx)
                from claude_eval import invalidate_all_evaluations
                invalidate_all_evaluations()
                st.info("Context saved. Ask Claude Code: **\"Generate my correlation evaluations\"**, then restart the dashboard to see it.", icon="💬")
        else:
            pending = _corr_pending_path(period)
            if pending.exists():
                st.info("Context is ready. Ask Claude Code: **\"Generate my correlation evaluations\"**, then restart the dashboard to see it.", icon="💬")
            else:
                btn_col, _ = st.columns([1, 3])
                if btn_col.button("✨ Request evaluation", key=f"corr_btn_{period}", use_container_width=True):
                    ctx = build_correlation_context(
                        f"Last {period.replace('d', ' Days')}",
                        metrics, today,
                        body_comp=body_comp,
                        body_comp_trend=bc_trend,
                    )
                    _CORR_PENDING_DIR.mkdir(parents=True, exist_ok=True)
                    _corr_pending_path(period).write_text(ctx)
                    st.info("Context saved. Ask Claude Code: **\"Generate my correlation evaluations\"**, then restart the dashboard to see it.", icon="💬")
                else:
                    st.caption("Click **Request evaluation** — Claude Code will generate it from this session.")


if tab5 is not None:
    with tab5:
        st.subheader("Nutrition × Exercise")

        # ── Body Composition snapshot ─────────────────────────────────────────
        if latest_body_comp:
            st.markdown("### ⚖️ Body Composition")
            if len(withings_month) >= 2:
                oldest = withings_month[-1]
                st.caption(
                    f"Most recent reading: **{latest_body_comp['date']}**. "
                    f"Trend deltas vs earliest reading in window ({oldest['date']})."
                )
            else:
                st.caption(f"Most recent reading: **{latest_body_comp['date']}**.")
            render_body_comp(latest_body_comp, trend=month_body_trend)
            st.divider()

        nutr_fifteen = [d for d in _nutrition_month
                        if d["date"] >= fifteen_start.isoformat()]

        corr_15d = compute_correlation_metrics(all_month, _nutrition_month, fifteen_start)
        corr_30d = compute_correlation_metrics(all_month, _nutrition_month, month_start)

        # Withings trend for the 15-day window
        withings_15d = [m for m in withings_month if m["date"] >= fifteen_start.isoformat()]
        latest_bc_15d = latest_measurement(withings_15d)
        trend_15d = body_comp_trend(withings_15d)

        # ── 15-day section ────────────────────────────────────────────────────
        st.markdown(f"### 📅 Last 15 Days · {fifteen_start.strftime('%b %d')} – {today.strftime('%b %d')}")
        _render_corr_metrics(corr_15d)
        if corr_15d.get("overlap_days"):
            _render_corr_eval_box("15d", corr_15d, latest_bc_15d, trend_15d)

        st.divider()

        # ── 30-day section ────────────────────────────────────────────────────
        st.markdown(f"### 📅 Last 30 Days · {month_start.strftime('%b %d')} – {today.strftime('%b %d')}")
        _render_corr_metrics(corr_30d)
        if corr_30d.get("overlap_days"):
            _render_corr_eval_box("30d", corr_30d, latest_body_comp, month_body_trend)

# ── Chat (optional) ───────────────────────────────────────────────────────────

if _CHAT_ENABLED:
    st.divider()
    title_col, clear_col = st.columns([8, 1])
    title_col.subheader("Ask Claude")
    if clear_col.button("Clear chat", use_container_width=True):
        st.session_state.chat_messages = []
        st.rerun()

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about your training or nutrition…"):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        context = build_context(today, all_week, nutrition_today, nutrition_yesterday, nutrition_week)
        api_messages = [{"role": m["role"], "content": m["content"]}
                        for m in st.session_state.chat_messages]
        with st.chat_message("assistant"):
            reply = st.write_stream(stream_response(api_messages, context))
        st.session_state.chat_messages.append({"role": "assistant", "content": reply})
