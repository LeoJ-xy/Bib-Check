import requests

from ...sources.common import normalize_whitespace, request_json


def search_s2(title: str, session: requests.Session, cache, user_agent: str):
    if not title:
        return None
    ck = f"s2:search:{title}"
    cached = cache.get(ck)
    if cached:
        return cached
    params = {"query": title, "limit": 1, "fields": "title,year,authors,venue,externalIds,url"}
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    payload, error = request_json(session, url, params=params, timeout=10)
    if error or not payload:
        return None
    data = payload.get("data", [])
    if not data:
        return None
    item = data[0]
    doi = (item.get("externalIds") or {}).get("DOI")
    res = {
        "source": "s2",
        "doi": doi,
        "title": normalize_whitespace(item.get("title") or ""),
        "authors": [a.get("name") for a in item.get("authors", []) if a.get("name")],
        "year": str(item.get("year")) if item.get("year") else None,
        "venue": item.get("venue"),
        "url": item.get("url"),
    }
    cache.set(ck, res)
    return res
