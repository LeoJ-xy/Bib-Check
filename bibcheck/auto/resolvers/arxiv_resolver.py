import re
import requests

from ...kind import ARXIV_NEW_RE, ARXIV_OLD_RE, ARXIV_URL_RE
from ...sources.arxiv import ArxivClient


def extract_arxiv_id(text: str):
    if not text:
        return None
    m = ARXIV_URL_RE.search(text)
    if m:
        return re.sub(r"\.pdf$", "", m.group(2), flags=re.I)
    m = ARXIV_NEW_RE.search(text) or ARXIV_OLD_RE.search(text)
    if m:
        return m.group(0)
    return None


def resolve_arxiv(eprint_or_url: str, session: requests.Session, cache, user_agent: str):
    arxid = extract_arxiv_id(eprint_or_url)
    if not arxid:
        return None
    ck = f"arxiv:{arxid}"
    cached = cache.get(ck)
    if cached:
        return cached
    client = ArxivClient(session, cache, lambda src: None)
    data = client.fetch_by_id(arxid)
    if not data:
        return None
    data["eprint"] = arxid
    data["doi"] = data.get("doi") or f"10.48550/arxiv.{arxid}".lower()
    cache.set(ck, data)
    return data
