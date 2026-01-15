import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, Optional

import requests


ARXIV_ID_RE = re.compile(r"arxiv\.org/(abs|pdf)/([^?#\s]+)", flags=re.I)


class ArxivClient:
    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.base = "http://export.arxiv.org/api/query"

    def fetch_by_id(self, arxiv_id: str) -> Optional[Dict]:
        cache_key = f"arxiv:id:{arxiv_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        self.rate_limiter("arxiv")
        data = self._request(self.base, params={"id_list": arxiv_id})
        parsed = self._parse_atom(data) if data else None
        self.cache.set(cache_key, parsed)
        return parsed

    def _parse_atom(self, text: str) -> Optional[Dict]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        if not title:
            return None
        authors = []
        for author in entry.findall("atom:author", ns):
            name = (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            if name:
                authors.append(name)
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        updated = entry.findtext("atom:updated", default="", namespaces=ns) or ""
        year = (published or updated)[:4] if (published or updated) else None
        url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        arxiv_id = None
        if url:
            m = ARXIV_ID_RE.search(url)
            if m:
                arxiv_id = re.sub(r"\.pdf$", "", m.group(2), flags=re.I)
        doi = entry.findtext("arxiv:doi", default="", namespaces=ns) or None
        return {
            "source": "arxiv",
            "id": arxiv_id,
            "doi": doi,
            "title": title,
            "year": year,
            "venue": "arXiv",
            "authors": authors,
            "url": url,
        }

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
                return resp.text
            except requests.RequestException:
                time.sleep(backoff)
                backoff *= 2
        return None
