from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_DB_PATH = Path.home() / ".config" / "health-dashboard" / "cache.db"


class DashboardCache:
    def __init__(self, db_path: Path = _DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, data TEXT, expires_at REAL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def get(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM cache WHERE key = ? AND expires_at > ?",
                (key, time.time()),
            ).fetchone()
        return row[0] if row else None

    def set(self, key: str, data: str, ttl: int = 28800) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, data, expires_at) VALUES (?, ?, ?)",
                (key, data, time.time() + ttl),
            )

    def delete(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))

    def delete_like(self, pattern: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE key LIKE ?", (pattern,))
