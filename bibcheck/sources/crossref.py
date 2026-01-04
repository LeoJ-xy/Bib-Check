import time
from typing import Dict, List, Optional

import requests


class CrossrefClient:
    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.base = "https://api.crossref.org"

    def fetch_by_doi(self, doi: str) -> Optional[Dict]:
        cache_key = f"crossref:doi:{doi}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        self.rate_limiter("crossref")
        url = f"{self.base}/works/{doi}"
        data = self._request(url)
        if data and data.get("status") == "ok":
            item = data.get("message", {})
            parsed = self._parse_item(item)
            if parsed:
                self.cache.set(cache_key, parsed)
                return parsed
        return None

    def search(self, norm_title: str, year: str = None, first_author: str = None) -> List[Dict]:
        cache_key = f"crossref:search:{norm_title}:{year}:{first_author}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        params = {"query.bibliographic": norm_title, "rows": 5}
        if year:
            params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
        self.rate_limiter("crossref")
        data = self._request(f"{self.base}/works", params=params)
        results: List[Dict] = []
        if data and data.get("status") == "ok":
            for item in data.get("message", {}).get("items", []):
                parsed = self._parse_item(item)
                if parsed:
                    results.append(parsed)
        self.cache.set(cache_key, results)
        return results

    def _parse_item(self, item: Dict) -> Optional[Dict]:
        title = " ".join(item.get("title", [])).strip()
        if not title:
            return None
        year = None
        if item.get("issued", {}).get("date-parts"):
            year = str(item["issued"]["date-parts"][0][0])
        doi = item.get("DOI")
        authors = []
        for a in item.get("author", []):
            name = " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
            if name:
                authors.append(name)
        venue = item.get("container-title", [])
        venue = venue[0] if venue else None
        return {"source": "crossref", "doi": doi, "title": title, "year": year, "venue": venue, "authors": authors, "url": item.get("URL")}

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


