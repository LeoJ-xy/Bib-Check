import json
import os
import sqlite3
import time
from typing import Any, Optional


class HTTPCache:
    """简单 SQLite 缓存，按 key 存储 JSON 串。"""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            home = os.path.expanduser("~")
            cache_dir = os.path.join(home, ".cache", "bibcheck")
            os.makedirs(cache_dir, exist_ok=True)
            path = os.path.join(cache_dir, "cache.sqlite")
        self.path = path
        self._ensure_table()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _ensure_table(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS responses(
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def get(self, key: str) -> Optional[Any]:
        with self._conn() as conn:
            cur = conn.execute("SELECT payload FROM responses WHERE key=?", (key,))
            row = cur.fetchone()
            if not row:
                return None
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return None

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value)
        ts = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO responses(key, payload, updated_at) VALUES (?, ?, ?)",
                (key, payload, ts),
            )


