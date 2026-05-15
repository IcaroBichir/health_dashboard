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

_CHAT_ENABLED = os.environ.get("ENABLE_CLAUDE_CHAT", "0").strip() == "1"
if _CHAT_ENABLED:
    from claude_chat import build_context, stream_response

st.set_page_config(page_title="Health Dashboard", layout="wide", page_icon="🏃")

today = date.today()
yesterday = today - timedelta(days=1)
week_start = today - timedelta(days=6)
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

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["Today & Yesterday", "Last 7 Days", "Last 30 Days"])

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
