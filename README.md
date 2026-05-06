# health-dashboard

Local Streamlit dashboard combining Strava training and MyFitnessPal nutrition data. Three sections: Today, Yesterday, and Last 7 Days — each showing activity cards and nutrition macros side by side.

---

## Prerequisites

- Python 3.11+
- [strava-mcp](../mcp_strava) authenticated (`strava-mcp auth` already run)
- [mcp-myfitnesspal](../mcp_myfitnesspal) authenticated (`mfp-mcp auth` already run) — nutrition sections degrade gracefully if skipped

---

## Install

```bash
cd /Users/icaro/icaro_lifestyle/tech/health_dashboard

python3 -m venv .venv
.venv/bin/pip install streamlit
.venv/bin/pip install -e ../mcp_strava      # local path — picks up SQLite cache
.venv/bin/pip install -e ../mcp_myfitnesspal
```

---

## Run

```bash
./start
```

Checks Strava token and MFP cookie freshness, prints status, then opens the dashboard at http://localhost:8501.

Or directly:

```bash
.venv/bin/streamlit run app.py
```

---

## Cache

| Layer | TTL | Location |
|---|---|---|
| Streamlit in-memory | 5 min | process memory |
| strava-mcp SQLite | 1 hour | `~/.config/strava-mcp/cache.db` |
| MFP cookies | 12 hours | `~/.config/mfp-mcp/cookies.json` |

The **↺ Refresh** button in the UI clears the Streamlit layer. To force a fresh Strava fetch:

```bash
strava-mcp cache clear
```

Then click **↺ Refresh**. To refresh MFP cookies, re-run `mfp-mcp auth`.

---

## Tests

```bash
.venv/bin/pip install pytest
.venv/bin/pytest tests/ -v
```

33 tests covering `strava_data.py` formatters, date-range filtering, and `mfp_data.py` nutrition helpers. No live API calls — Strava and MFP clients are mocked.
