from typing import Dict, List, Optional

import requests

from .common import SourceClientMixin, normalize_whitespace, request_json


class DblpClient(SourceClientMixin):
    source_name = "dblp"

    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.base = "https://dblp.org/search/publ/api"
        self.last_error = None

    def fetch_by_doi(self, doi: str) -> Optional[Dict]:
        results = self.search(doi, year=None, first_author=None)
        return results[0] if results else None

    def search(self, norm_title: str, year: str = None, first_author: str = None) -> List[Dict]:
        self._clear_error()
        cache_key = f"dblp:search:{norm_title}:{year}:{first_author}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        query = norm_title
        if year:
            query = f"{query} {year}"
        if first_author:
            query = f"{query} {first_author}"
        params = {"q": query.strip(), "format": "json"}
        self.rate_limiter("dblp")
        data = self._request(self.base, params=params)
        results: List[Dict] = []
        if self.last_error:
            return results
        hits = (data or {}).get("result", {}).get("hits", {}).get("hit", [])
        for hit in hits[:5]:
            info = hit.get("info", {})
            parsed = self._parse_item(info)
            if parsed:
                results.append(parsed)
        self.cache.set(cache_key, results)
        return results

    def _parse_item(self, info: Dict) -> Optional[Dict]:
        title = normalize_whitespace(info.get("title") or "")
        if not title:
            return None
        authors = []
        author_data = info.get("authors", {}).get("author", [])
        if isinstance(author_data, dict):
            author_data = [author_data]
        for author in author_data:
            name = author.get("text") if isinstance(author, dict) else author
            if name:
                authors.append(name)
        year = info.get("year")
        venue = info.get("venue")
        return {
            "source": "dblp",
            "title": title,
            "year": str(year) if year else None,
            "venue": venue,
            "authors": authors,
            "doi": info.get("doi"),
            "url": info.get("url") or info.get("ee"),
            "id": info.get("key"),
        }

    def _request(self, url: str, params: Dict = None):
        data, error = request_json(self.session, url, params=params, timeout=10)
        if error:
            details = {k: v for k, v in error.items() if k != "message"}
            self._record_error(str(error.get("message", "request failed")), **details)
        return data
