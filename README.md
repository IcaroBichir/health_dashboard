# health-dashboard

Local Streamlit dashboard displaying Strava training data. Three sections: Today, Yesterday, and Last 7 Days.

---

## Prerequisites

- Python 3.11+
- [strava-mcp](../mcp_strava) authenticated (`strava-mcp auth` already run)

---

## Install

```bash
cd /Users/icaro/icaro_lifestyle/tech/health_dashboard

python3 -m venv .venv
.venv/bin/pip install streamlit
.venv/bin/pip install -e ../mcp_strava
```

The second pip install pulls strava-mcp from the local path so the SQLite response cache is included.

---

## Run

```bash
.venv/bin/streamlit run app.py
```

Opens at http://localhost:8501.

---

## Cache

Activity data is cached at two layers:

| Layer | TTL | Location |
|---|---|---|
| Streamlit in-memory | 5 min | process memory |
| strava-mcp SQLite | 1 hour | `~/.config/strava-mcp/cache.db` |

The **↺ Refresh** button in the UI clears the Streamlit layer. To force a fresh fetch from the Strava API, clear the SQLite cache first:

```bash
strava-mcp cache clear
```

Then click **↺ Refresh** in the browser.
