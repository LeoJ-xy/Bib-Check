import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Optional


class HTTPCache:
    """简单 SQLite 缓存，按 key 存储 JSON 串。"""

    def __init__(self, path: Optional[str] = None):
        self._conn_obj: Optional[sqlite3.Connection] = None
        if path is None:
            home = os.path.expanduser("~")
            cache_dir = os.path.join(home, ".cache", "bibcheck")
            os.makedirs(cache_dir, exist_ok=True)
            path = os.path.join(cache_dir, "cache.sqlite")
        elif path == ":memory:":
            self._conn_obj = sqlite3.connect(":memory:")
        self.path = path
        self._ensure_table()

    @contextmanager
    def _conn(self):
        if self._conn_obj is not None:
            try:
                yield self._conn_obj
                self._conn_obj.commit()
            finally:
                return
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

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
