import requests
from ..core.normalize import norm_doi
from ...sources.common import normalize_whitespace, request_json


def resolve_doi(doi: str, session: requests.Session, cache, user_agent: str):
    doi = norm_doi(doi)
    if not doi:
        return None
    ck = f"doi:{doi}"
    cached = cache.get(ck)
    if cached:
        return cached
    url = f"https://api.crossref.org/works/{doi}"
    payload, error = request_json(session, url, timeout=10)
    if error or not payload:
        return None
    msg = payload.get("message", {})
    data = {
        "source": "crossref",
        "doi": msg.get("DOI"),
        "title": normalize_whitespace(" ".join(msg.get("title") or [])),
        "authors": [
            " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
            for a in msg.get("author", []) if a.get("given") or a.get("family")
        ],
        "year": str((msg.get("issued", {}).get("date-parts") or [[None]])[0][0]),
        "venue": (msg.get("container-title") or [""])[0],
        "url": msg.get("URL"),
    }
    cache.set(ck, data)
    return data
