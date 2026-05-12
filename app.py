import streamlit as st
from datetime import date, timedelta

from strava_data import (
    SPORT_EMOJI,
    fmt_distance,
    fmt_duration,
    fmt_pace,
    fmt_speed,
    get_activities_in_range,
)
from mfp_data import get_nutrition_for_date, get_nutrition_range

st.set_page_config(page_title="Health Dashboard", layout="wide", page_icon="🏃")

today = date.today()
yesterday = today - timedelta(days=1)
week_start = today - timedelta(days=6)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_week(start: date, end: date) -> list[dict]:
    return get_activities_in_range(start, end)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_nutrition(d: date) -> dict:
    return get_nutrition_for_date(d)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_nutrition_week(start: date, end: date) -> list[dict]:
    return get_nutrition_range(start, end)


def render_activity(a: dict) -> None:
    sport = a.get("sport_type", "Other")
    emoji = SPORT_EMOJI.get(sport, "⚡")
    dist = a.get("distance")
    duration = a.get("moving_time")
    hr = a.get("average_heartrate")
    elev = a.get("total_elevation_gain", 0)
    time_str = a.get("start_date_local", "")[:16].replace("T", " ")

    with st.container(border=True):
        st.markdown(f"**{emoji} {a.get('name', sport)}**")
        st.caption(time_str)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Distance", fmt_distance(dist))
        c2.metric("Time", fmt_duration(duration))
        if sport == "Run":
            c3.metric("Pace", fmt_pace(dist, duration))
        elif sport in ("Ride", "VirtualRide"):
            c3.metric("Speed", fmt_speed(a.get("average_speed")))
        else:
            c3.metric("Elev.", f"{elev:.0f} m")
        c4.metric("HR", f"{hr:.0f} bpm" if hr else "—")


def render_section(title: str, activities: list[dict]) -> None:
    st.subheader(title)
    if not activities:
        st.caption("No activities")
        return
    for a in activities:
        render_activity(a)


def render_nutrition(data: dict, title: str) -> None:
    totals = data.get("daily_totals", {})
    goals = data.get("goals", {})
    st.subheader(title)
    if not totals:
        st.caption("No nutrition data")
        return
    calories = totals.get("calories", 0)
    cal_goal = goals.get("calories", 0)
    protein = totals.get("protein", 0)
    carbs = totals.get("carbohydrates", 0)
    fat = totals.get("fat", 0)
    with st.container(border=True):
        remaining = round(cal_goal - calories) if cal_goal else None
        delta_str = f"{remaining:+.0f} remaining" if remaining is not None else None
        # Positive remaining = good (under goal); negative = over goal
        delta_color = "normal" if (remaining is None or remaining >= 0) else "inverse"
        cal_label = f"{calories:.0f} / {cal_goal:.0f} kcal" if cal_goal else f"{calories:.0f} kcal"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Calories", cal_label, delta=delta_str, delta_color=delta_color)
        c2.metric("Protein", f"{protein:.0f} g", delta=f"goal {goals['protein']:.0f} g" if "protein" in goals else None, delta_color="off")
        c3.metric("Carbs", f"{carbs:.0f} g", delta=f"goal {goals['carbohydrates']:.0f} g" if "carbohydrates" in goals else None, delta_color="off")
        c4.metric("Fat", f"{fat:.0f} g", delta=f"goal {goals['fat']:.0f} g" if "fat" in goals else None, delta_color="off")


# ── Header ────────────────────────────────────────────────────────────────────
st.title("Health Dashboard")
st.caption(f"{today.strftime('%A, %B %d, %Y')}")

hcol, _ = st.columns([1, 7])
if hcol.button("↺  Refresh", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# ── Fetch ─────────────────────────────────────────────────────────────────────
with st.spinner("Loading activities..."):
    all_week = fetch_week(week_start, today)

with st.spinner("Loading nutrition..."):
    nutrition_today = fetch_nutrition(today)
    nutrition_yesterday = fetch_nutrition(yesterday)
    nutrition_week = fetch_nutrition_week(week_start, today)

today_acts = [a for a in all_week if a.get("start_date_local", "")[:10] == str(today)]
yesterday_acts = [a for a in all_week if a.get("start_date_local", "")[:10] == str(yesterday)]

# ── Today / Yesterday ─────────────────────────────────────────────────────────
col_today, col_yesterday = st.columns(2)

with col_today:
    render_section(f"Today  ·  {today.strftime('%b %d')}", today_acts)
    render_nutrition(nutrition_today, "Nutrition")

with col_yesterday:
    render_section(f"Yesterday  ·  {yesterday.strftime('%b %d')}", yesterday_acts)
    render_nutrition(nutrition_yesterday, "Nutrition")

st.divider()

# ── Last 7 Days ───────────────────────────────────────────────────────────────
st.subheader(f"Last 7 Days  ·  {week_start.strftime('%b %d')} – {today.strftime('%b %d')}")

if all_week:
    runs = [a for a in all_week if a.get("sport_type") == "Run"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Activities", len(all_week))
    m2.metric("Runs", len(runs))
    m3.metric("Run Distance", fmt_distance(sum(a.get("distance", 0) for a in runs)))
    m4.metric("Total Time", fmt_duration(sum(a.get("moving_time", 0) for a in all_week)))
else:
    st.caption("No activities in the last 7 days")

days_with_data = [d for d in nutrition_week if d.get("daily_totals")]
if days_with_data:
    n = len(days_with_data)
    avg_cal = sum(d["daily_totals"].get("calories", 0) for d in days_with_data) / n
    avg_protein = sum(d["daily_totals"].get("protein", 0) for d in days_with_data) / n
    avg_carbs = sum(d["daily_totals"].get("carbohydrates", 0) for d in days_with_data) / n
    avg_fat = sum(d["daily_totals"].get("fat", 0) for d in days_with_data) / n
    cal_goal = next((d["goals"].get("calories") for d in days_with_data if d.get("goals")), None)
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Avg Calories", f"{avg_cal:.0f} kcal", delta=f"goal {cal_goal:.0f}" if cal_goal else None, delta_color="off")
    n2.metric("Avg Protein", f"{avg_protein:.0f} g")
    n3.metric("Avg Carbs", f"{avg_carbs:.0f} g")
    n4.metric("Avg Fat", f"{avg_fat:.0f} g")

if all_week:
    st.markdown("---")
    for a in all_week:
        render_activity(a)
