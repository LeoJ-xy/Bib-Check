import time
from typing import Dict, List, Optional

import requests


class OpenAlexClient:
    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.base = "https://api.openalex.org/works"

    def fetch_by_doi(self, doi: str) -> Optional[Dict]:
        cache_key = f"openalex:doi:{doi}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        self.rate_limiter("openalex")
        url = f"{self.base}/https://doi.org/{doi}"
        data = self._request(url)
        if data:
            parsed = self._parse_item(data)
            if parsed:
                self.cache.set(cache_key, parsed)
                return parsed
        return None

    def search(self, norm_title: str, year: str = None, first_author: str = None) -> List[Dict]:
        cache_key = f"openalex:search:{norm_title}:{year}:{first_author}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        params = {"filter": f"display_name.search:{norm_title}", "per-page": 5}
        if year:
            params["filter"] += f",from_publication_date:{year}-01-01,to_publication_date:{year}-12-31"
        if first_author:
            params["filter"] += f",authorships.author.display_name.search:{first_author}"
        self.rate_limiter("openalex")
        data = self._request(self.base, params=params)
        results: List[Dict] = []
        if data and "results" in data:
            for item in data["results"]:
                parsed = self._parse_item(item)
                if parsed:
                    results.append(parsed)
        self.cache.set(cache_key, results)
        return results

    def _parse_item(self, item: Dict) -> Optional[Dict]:
        title = item.get("title") or item.get("display_name")
        if not title:
            return None
        year = None
        if item.get("publication_year"):
            year = str(item["publication_year"])
        elif item.get("publication_date"):
            year = item["publication_date"][:4]
        doi = item.get("doi")
        authors = []
        for a in item.get("authorships", []):
            name = a.get("author", {}).get("display_name")
            if name:
                authors.append(name)
        venue = None
        if item.get("primary_location") and item["primary_location"].get("source"):
            venue = item["primary_location"]["source"].get("display_name")
        return {"source": "openalex", "doi": doi, "title": title, "year": year, "venue": venue, "authors": authors, "url": item.get("id")}

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

