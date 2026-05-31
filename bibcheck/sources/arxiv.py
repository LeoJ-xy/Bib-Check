import re
import xml.etree.ElementTree as ET
from typing import Dict, Optional

import requests

from .common import SourceClientMixin, normalize_whitespace, request_text


ARXIV_ID_RE = re.compile(r"arxiv\.org/(abs|pdf)/([^?#\s]+)", flags=re.I)


class ArxivClient(SourceClientMixin):
    source_name = "arxiv"

    def __init__(self, session: requests.Session, cache, rate_limiter):
        self.session = session
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.base = "https://export.arxiv.org/api/query"
        self.last_error = None

    def fetch_by_id(self, arxiv_id: str) -> Optional[Dict]:
        self._clear_error()
        cache_key = f"arxiv:id:{arxiv_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        self.rate_limiter("arxiv")
        data = self._request(self.base, params={"id_list": arxiv_id})
        if self.last_error:
            return None
        parsed = self._parse_atom(data) if data else None
        if parsed:
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
        title = normalize_whitespace(entry.findtext("atom:title", default="", namespaces=ns) or "")
        if not title:
            return None
        authors = []
        for author in entry.findall("atom:author", ns):
            name = normalize_whitespace(author.findtext("atom:name", default="", namespaces=ns) or "")
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
        data, error = request_text(self.session, url, params=params, timeout=10)
        if error:
            details = {k: v for k, v in error.items() if k != "message"}
            self._record_error(str(error.get("message", "request failed")), **details)
        return data
