import os
import sqlite3
import json
import time
from contextlib import contextmanager


class HTTPCache:
    """Simple sqlite cache for HTTP responses."""

    def __init__(self, path=None):
        self._conn_obj = None
        if path is None:
            path = os.path.expanduser("~/.cache/bibcheck/httpcache.sqlite")
        elif path == ":memory:":
            self._conn_obj = sqlite3.connect(":memory:")
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self.path = path
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, payload TEXT, ts REAL)")

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

    def get(self, key):
        with self._conn() as c:
            row = c.execute("SELECT payload FROM cache WHERE key=?", (key,)).fetchone()
            if not row:
                return None
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return None

    def set(self, key, payload):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO cache(key,payload,ts) VALUES (?,?,?)",
                (key, json.dumps(payload), time.time()),
            )
