import json
import time
from typing import Any, Dict, Optional, Tuple

import requests


TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def normalize_whitespace(value: str) -> str:
    return " ".join((value or "").split())


class SourceClientMixin:
    source_name = "unknown"

    def _clear_error(self) -> None:
        self.last_error = None

    def _record_error(self, message: str, **details: object) -> None:
        payload = {"source": self.source_name, "message": message}
        payload.update({k: v for k, v in details.items() if v is not None})
        self.last_error = payload


def request_json(
    session: requests.Session,
    url: str,
    *,
    params: Optional[Dict] = None,
    timeout: int = 10,
    attempts: int = 3,
) -> Tuple[Optional[Any], Optional[Dict[str, object]]]:
    text, error = request_text(session, url, params=params, timeout=timeout, attempts=attempts)
    if text is None or error:
        return None, error
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, {"message": f"invalid JSON response: {exc}", "url": url}


def request_text(
    session: requests.Session,
    url: str,
    *,
    params: Optional[Dict] = None,
    timeout: int = 10,
    attempts: int = 3,
) -> Tuple[Optional[str], Optional[Dict[str, object]]]:
    backoff = 0.5
    last_error: Optional[Dict[str, object]] = None
    for attempt in range(attempts):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code == 404:
                return None, None
            if resp.status_code in TRANSIENT_STATUS_CODES:
                last_error = {
                    "message": f"HTTP {resp.status_code}",
                    "status_code": resp.status_code,
                    "url": resp.url,
                }
                if attempt < attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2
                continue
            if resp.status_code >= 400:
                return None, {
                    "message": f"HTTP {resp.status_code}",
                    "status_code": resp.status_code,
                    "url": resp.url,
                }
            return resp.text, None
        except requests.RequestException as exc:
            last_error = {"message": str(exc), "url": url}
            if attempt < attempts - 1:
                time.sleep(backoff)
                backoff *= 2
    return None, last_error
