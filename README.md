# health-dashboard

Local Streamlit dashboard combining Strava training and MyFitnessPal nutrition data, designed for athletes who want to track load and calorie balance in one place.

---

## Tabs

**Today & Yesterday** — side-by-side columns. Each day shows:
- **Exercise** section: activity cards with distance, time, pace/speed, HR, and calories burned per activity
- **Nutrition** section: calories consumed vs goal, protein / carbs / fat
- **Calorie Balance** card: consumed vs burned (Strava) vs net

**Last 7 Days** — aggregate view:
- Exercise: total activities, run count, run distance, total time, total calories burned
- Nutrition: avg daily calories, protein, carbs, fat
- Calorie Balance: 7-day totals (consumed / burned / net)
- Full activity list

**Last 30 Days** — same structure as 7-day over the full month

---

## Sidebar

**Theme picker** — 5 presets with live color swatch preview:

| Theme | Style |
|---|---|
| Clean Light | Blue on white |
| Forest | Green on near-white |
| Warm Sand | Terracotta on cream |
| Dark Navy | Cyan on dark navy |
| Dark Slate | Purple on dark slate |

Clicking **Apply theme** writes `.streamlit/config.toml` and reloads the app.

---

## Header buttons

**↺ Refresh** — clears Streamlit in-memory cache and reloads.

**⬇ Pull API** — dropdown to choose the range to refresh (Today / Yesterday / Last 7 Days / Last 30 Days), then confirm. Deletes the matching SQLite cache entries for both Strava and MFP, then triggers a fresh API fetch. Use sparingly — both services rate-limit requests.

---

## Prerequisites

- Python 3.11+
- [strava-mcp](../mcp_strava) authenticated (`strava-mcp auth` already run)
- [mcp-myfitnesspal](../mcp_myfitnesspal) authenticated (`mfp-mcp auth` already run)

**MFP limitation:** the MFP mobile JSON API (`api.myfitnesspal.com/v2/diary`) does not return historical diary data — it always returns today's diary regardless of the requested date. Only today's nutrition is populated; past days show "No nutrition logged." See [Known limitations](#known-limitations).

---

## Install

```bash
cd health_dashboard
python3 -m venv .venv
.venv/bin/pip install streamlit
.venv/bin/pip install -e ../mcp_strava       # local path — picks up SQLite cache
.venv/bin/pip install -e ../mcp_myfitnesspal
```

---

## Run

```bash
./start
```

Checks Strava token validity and MFP cookie freshness (shows time remaining or a re-auth warning), then opens the dashboard at http://localhost:8501.

Or run Streamlit directly:

```bash
.venv/bin/streamlit run app.py
```

---

## Cache

| Layer | TTL | Location |
|---|---|---|
| Streamlit in-memory | 5 min | process memory (cleared by ↺ Refresh) |
| Strava activities (per day) | 15 days (5 min today) | `~/.config/strava-mcp/cache.db` |
| Strava detailed activities | 15 days | `~/.config/strava-mcp/cache.db` |
| MFP diary (per day) | 15 days (30 min today) | `~/.config/mfp-mcp/cache.db` |
| MFP cookies | 12 hours | `~/.config/mfp-mcp/cookies.json` |

Strava calories come from the detailed activity endpoint (`/activities/{id}`), which is fetched once per activity and cached separately from the summary list. The first load after a cache clear will make one API call per activity.

---

## Claude chat (optional)

The chat panel is disabled by default. It requires a separate [Anthropic API key](https://console.anthropic.com) (paid, separate from the Claude app subscription).

To enable, create `health_dashboard/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
ENABLE_CLAUDE_CHAT=1
```

Then restart with `./start`. The chat panel will appear at the bottom of the dashboard.

When active, each question is answered by `claude-sonnet-4-6` with the current week's activities and nutrition pre-loaded as context. Conversation history is maintained within the session; the **Clear chat** button resets it.

---

## Known limitations

**MFP historical data** — `api.myfitnesspal.com/v2/diary` returns today's diary for every date query. The date parameter is ignored server-side. Historical nutrition data (yesterday, last 7 days, last 30 days) is not accessible through this endpoint. Only today's nutrition is shown.

Workarounds being investigated:
- Intercepting iOS MFP app network traffic to find the correct historical endpoint
- MFP data export (manual, not automated)

**Strava calories on first load** — the summary `/athlete/activities` endpoint omits calories. Each activity is enriched by fetching its detailed record once; this means first load after a cache clear makes N additional API calls (one per activity). Subsequent loads are instant from cache.

---

## Tests

```bash
.venv/bin/pytest tests/ -v
```

Tests cover `strava_data.py` (formatters, range delegation) and `mfp_data.py` (helpers, error silencing). No live API calls — Strava and MFP clients are mocked.
