import os
import sqlite3
import json
import time


class HTTPCache:
    """Simple sqlite cache for HTTP responses."""

    def __init__(self, path=None):
        if path is None:
            path = os.path.expanduser("~/.cache/bibcheck/httpcache.sqlite")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        with sqlite3.connect(self.path) as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, payload TEXT, ts REAL)"
            )

    def get(self, key):
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT payload FROM cache WHERE key=?", (key,)).fetchone()
            if not row:
                return None
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return None

    def set(self, key, payload):
        with sqlite3.connect(self.path) as c:
            c.execute(
                "INSERT OR REPLACE INTO cache(key,payload,ts) VALUES (?,?,?)",
                (key, json.dumps(payload), time.time()),
            )

