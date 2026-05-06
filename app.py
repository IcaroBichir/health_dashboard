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

st.set_page_config(page_title="Health Dashboard", layout="wide", page_icon="🏃")

today = date.today()
yesterday = today - timedelta(days=1)
week_start = today - timedelta(days=6)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_week(start: date, end: date) -> list[dict]:
    return get_activities_in_range(start, end)


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

today_acts = [a for a in all_week if a.get("start_date_local", "")[:10] == str(today)]
yesterday_acts = [a for a in all_week if a.get("start_date_local", "")[:10] == str(yesterday)]

# ── Today / Yesterday ─────────────────────────────────────────────────────────
col_today, col_yesterday = st.columns(2)

with col_today:
    render_section(f"Today  ·  {today.strftime('%b %d')}", today_acts)

with col_yesterday:
    render_section(f"Yesterday  ·  {yesterday.strftime('%b %d')}", yesterday_acts)

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

    st.markdown("---")
    for a in all_week:
        render_activity(a)
else:
    st.caption("No activities in the last 7 days")
