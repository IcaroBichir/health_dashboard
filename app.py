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


def force_api_refresh() -> None:
    """Bypass local SQLite caches for today and yesterday, then clear Streamlit cache."""
    strava_db = Path.home() / ".config" / "strava-mcp" / "cache.db"
    mfp_db    = Path.home() / ".config" / "mfp-mcp"    / "cache.db"

    for d in (today, yesterday):
        _delete_from_sqlite(strava_db, f"activities_day:{d.isoformat()}")
        _delete_from_sqlite(mfp_db,    f"diary:%:{d.isoformat()}", like=True)

    # Also evict the athlete stats cache so it re-fetches the latest weekly summary
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

    with st.container(border=True):
        left, right = st.columns([2, 3])
        left.markdown(f"**{emoji} {name}**")
        left.caption(time_str)
        if stats:
            right.caption(stats)


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
    st.warning(
        "This will make live API calls to **Strava** and **MyFitnessPal**, "
        "bypassing today's and yesterday's local cache. "
        "Both services rate-limit requests — use sparingly.",
        icon="⚠️",
    )
    yes_col, no_col, _ = st.columns([1, 1, 5])
    if yes_col.button("Confirm", type="primary"):
        st.session_state.pop("confirm_api_pull", None)
        with st.spinner("Clearing cache and fetching from API…"):
            force_api_refresh()
        st.rerun()
    if no_col.button("Cancel"):
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

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["Today & Yesterday", "Last 7 Days", "Last 30 Days"])

# ── Tab 1: Today & Yesterday ──────────────────────────────────────────────────

with tab1:
    col_today, col_yesterday = st.columns(2)

    with col_today:
        st.subheader(f"Today · {today.strftime('%b %d')}")
        if today_acts:
            for a in today_acts:
                render_activity(a)
        else:
            st.caption("No activities yet")
        st.markdown("**Nutrition**")
        render_nutrition(nutrition_today)

    with col_yesterday:
        st.subheader(f"Yesterday · {yesterday.strftime('%b %d')}")
        if yesterday_acts:
            for a in yesterday_acts:
                render_activity(a)
        else:
            st.caption("No activities")
        st.markdown("**Nutrition**")
        render_nutrition(nutrition_yesterday)

# ── Tab 2: Last 7 Days ────────────────────────────────────────────────────────

with tab2:
    st.subheader(f"Last 7 Days · {week_start.strftime('%b %d')} – {today.strftime('%b %d')}")

    runs  = [a for a in all_week if a.get("sport_type") == "Run"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Activities", len(all_week))
    m2.metric("Runs", len(runs))
    m3.metric("Run Distance", fmt_distance(sum(a.get("distance", 0) for a in runs)))
    m4.metric("Total Time", fmt_duration(sum(a.get("moving_time", 0) for a in all_week)))

    avgs = _nutrition_avgs(nutrition_week)
    if avgs:
        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Avg Calories", f"{avgs['calories']:.0f} kcal",
                  delta=f"{avgs['n']} days logged", delta_color="off")
        n2.metric("Avg Protein", f"{avgs['protein']:.0f} g")
        n3.metric("Avg Carbs",   f"{avgs['carbs']:.0f} g")
        n4.metric("Avg Fat",     f"{avgs['fat']:.0f} g")

    if all_week:
        st.divider()
        for a in all_week:
            render_activity(a)
    else:
        st.caption("No activities this week")

# ── Tab 3: Last 30 Days ───────────────────────────────────────────────────────

with tab3:
    st.subheader(f"Last 30 Days · {month_start.strftime('%b %d')} – {today.strftime('%b %d')}")

    runs_m  = [a for a in all_month if a.get("sport_type") == "Run"]
    rides_m = [a for a in all_month if a.get("sport_type") in ("Ride", "VirtualRide")]
    lifts_m = [a for a in all_month if a.get("sport_type") == "WeightTraining"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Activities", len(all_month))
    m2.metric("Run Distance", fmt_distance(sum(a.get("distance", 0) for a in runs_m)))
    m3.metric("Total Time", fmt_duration(sum(a.get("moving_time", 0) for a in all_month)))
    m4.metric("Runs / Rides / Lifts", f"{len(runs_m)} / {len(rides_m)} / {len(lifts_m)}")

    avgs_m = _nutrition_avgs(nutrition_month)
    if avgs_m:
        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Avg Calories", f"{avgs_m['calories']:.0f} kcal",
                  delta=f"{avgs_m['n']} days logged", delta_color="off")
        n2.metric("Avg Protein", f"{avgs_m['protein']:.0f} g")
        n3.metric("Avg Carbs",   f"{avgs_m['carbs']:.0f} g")
        n4.metric("Avg Fat",     f"{avgs_m['fat']:.0f} g")

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
