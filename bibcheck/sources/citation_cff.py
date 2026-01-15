import time
from typing import Dict, Optional

import requests
import yaml


class CitationCffClient:
    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter

    def fetch_by_repo(self, owner: str, repo: str) -> Dict[str, Optional[Dict]]:
        cache_key = f"citationcff:{owner}/{repo}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        result = {"status": "missing", "candidate": None}
        for branch in ("main", "master"):
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/CITATION.cff"
            self.rate_limiter("citation_cff")
            data = self._request(url)
            if data is None:
                continue
            parsed = self._parse_cff(data, owner, repo)
            if parsed:
                result = {"status": "found", "candidate": parsed}
                break

        self.cache.set(cache_key, result)
        return result

    def _parse_cff(self, text: str, owner: str, repo: str) -> Optional[Dict]:
        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError:
            return None
        if not isinstance(payload, dict):
            return None
        title = payload.get("title") or payload.get("message")
        if not title:
            return None
        authors = []
        for a in payload.get("authors", []) or []:
            if not isinstance(a, dict):
                continue
            family = a.get("family-names") or a.get("family") or ""
            given = a.get("given-names") or a.get("given") or ""
            name = " ".join(part for part in [given, family] if part).strip()
            if name:
                authors.append(name)
        date_released = payload.get("date-released") or payload.get("release-date")
        year = date_released[:4] if isinstance(date_released, str) else None
        return {
            "source": "citation_cff",
            "title": title,
            "authors": authors,
            "doi": payload.get("doi"),
            "version": payload.get("version"),
            "year": year,
            "url": f"https://github.com/{owner}/{repo}",
        }

    def _request(self, url: str) -> Optional[str]:
        backoff = 0.5
        for _ in range(3):
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 500:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                resp.raise_for_status()
                return resp.text
            except requests.RequestException:
                time.sleep(backoff)
                backoff *= 2
        return None
