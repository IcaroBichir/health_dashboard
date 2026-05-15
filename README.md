# health-dashboard

Local Streamlit dashboard combining Strava training and MyFitnessPal nutrition data.

**Today / Yesterday** — side-by-side columns, each with individual activity cards (distance, time, pace/speed, HR) and a nutrition card (calories vs goal, protein/carbs/fat).

**Last 7 Days** — aggregate activity metrics (total activities, run distance, total time) alongside average daily nutrition (avg calories vs goal, avg macros), followed by a full activity list.

**Ask Claude** *(optional)* — chat panel at the bottom that answers questions about your data using the week's activities and nutrition as context. Disabled by default; see below.

---

## Prerequisites

- Python 3.11+
- [strava-mcp](../mcp_strava) authenticated (`strava-mcp auth` already run)
- [mcp-myfitnesspal](../mcp_myfitnesspal) authenticated (`mfp-mcp auth` already run) — nutrition sections show "No nutrition data" gracefully if skipped

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
| Streamlit in-memory | 5 min | process memory (cleared by ↺ Refresh button) |
| strava-mcp SQLite (activities per day) | 15 days (5 min today) | `~/.config/strava-mcp/cache.db` |
| MFP diary SQLite (per day) | 15 days (30 min today) | `~/.config/mfp-mcp/cache.db` |
| MFP cookies | 12 hours | `~/.config/mfp-mcp/cookies.json` |

To force a fresh Strava fetch (e.g. after a new workout syncs):

```bash
strava-mcp cache clear
```

Then click **↺ Refresh** in the browser. To refresh MFP data, re-run `mfp-mcp auth`.

---

## Claude chat (optional)

The chat panel is disabled by default. It requires a separate [Anthropic API key](https://console.anthropic.com) (paid, separate from the Claude app subscription).

To enable, create `health_dashboard/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
ENABLE_CLAUDE_CHAT=1
```

Then restart with `./start`. The chat panel will appear at the bottom of the dashboard.

When active, each question is answered by `claude-sonnet-4-6` with the current week's activities and nutrition pre-loaded as context — so you can ask things like "how was my training this week?" or "am I hitting my protein goal?" without pasting any data manually. Conversation history is maintained within the session; the **Clear chat** button resets it.

---

## Tests

```bash
.venv/bin/pytest tests/ -v
```

Tests cover `strava_data.py` (formatters, range delegation) and `mfp_data.py` (helpers, error silencing). No live API calls — Strava and MFP clients are mocked.
