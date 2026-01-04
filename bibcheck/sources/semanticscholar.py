import time
from typing import Dict, List, Optional

import requests


class SemanticScholarClient:
    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.base = "https://api.semanticscholar.org/graph/v1/paper"

    def fetch_by_doi(self, doi: str) -> Optional[Dict]:
        cache_key = f"s2:doi:{doi}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        self.rate_limiter("s2")
        url = f"{self.base}/DOI:{doi}"
        params = {"fields": "title,year,authors,venue,url"}
        data = self._request(url, params=params)
        if data and data.get("title"):
            parsed = self._parse_item(data)
            self.cache.set(cache_key, parsed)
            return parsed
        return None

    def search(self, norm_title: str, year: str = None, first_author: str = None) -> List[Dict]:
        cache_key = f"s2:search:{norm_title}:{year}:{first_author}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        params = {"query": norm_title, "limit": 5, "fields": "title,year,authors,venue,url,externalIds"}
        self.rate_limiter("s2")
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        data = self._request(url, params=params)
        results: List[Dict] = []
        if data and data.get("data"):
            for item in data["data"]:
                parsed = self._parse_item(item)
                if parsed:
                    results.append(parsed)
        self.cache.set(cache_key, results)
        return results

    def _parse_item(self, item: Dict) -> Optional[Dict]:
        title = item.get("title")
        if not title:
            return None
        year = item.get("year")
        doi = None
        ext = item.get("externalIds") or {}
        if "DOI" in ext:
            doi = ext["DOI"]
        authors = [a.get("name") for a in item.get("authors", []) if a.get("name")]
        venue = item.get("venue")
        return {"source": "s2", "doi": doi, "title": title, "year": str(year) if year else None, "venue": venue, "authors": authors, "url": item.get("url")}

    def _request(self, url: str, params: Dict = None):
        backoff = 0.5
        for _ in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=10)
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 500:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException:
                time.sleep(backoff)
                backoff *= 2
        return None


