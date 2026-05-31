import re
from typing import Dict, List, Optional

import requests

from .common import SourceClientMixin, normalize_whitespace, request_json


class OpenAlexClient(SourceClientMixin):
    source_name = "openalex"

    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.base = "https://api.openalex.org/works"
        self.last_error = None

    def fetch_by_doi(self, doi: str) -> Optional[Dict]:
        self._clear_error()
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
        self._clear_error()
        cache_key = f"openalex:search:{norm_title}:{year}:{first_author}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        params = {"filter": f"display_name.search:{norm_title}", "per-page": 5}
        if year:
            params["filter"] += f",from_publication_date:{year}-01-01,to_publication_date:{year}-12-31"
        if first_author:
            clean_author = _clean_filter_value(first_author)
            if clean_author:
                params["filter"] += f",authorships.author.display_name.search:{clean_author}"
        self.rate_limiter("openalex")
        data = self._request(self.base, params=params)
        results: List[Dict] = []
        if self.last_error:
            return results
        if data and "results" in data:
            for item in data["results"]:
                parsed = self._parse_item(item)
                if parsed:
                    results.append(parsed)
        self.cache.set(cache_key, results)
        return results

    def _parse_item(self, item: Dict) -> Optional[Dict]:
        title = normalize_whitespace(item.get("title") or item.get("display_name") or "")
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
        data, error = request_json(self.session, url, params=params, timeout=10)
        if error:
            details = {k: v for k, v in error.items() if k != "message"}
            self._record_error(str(error.get("message", "request failed")), **details)
        return data


def _clean_filter_value(value: str) -> str:
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", value or "").split())
