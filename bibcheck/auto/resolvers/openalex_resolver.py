import requests

from ...sources.common import normalize_whitespace, request_json


def search_openalex(title: str, session: requests.Session, cache, user_agent: str):
    if not title:
        return None
    ck = f"openalex:search:{title}"
    cached = cache.get(ck)
    if cached:
        return cached
    params = {"filter": f"display_name.search:{title}", "per-page": 1}
    payload, error = request_json(session, "https://api.openalex.org/works", params=params, timeout=10)
    if error or not payload:
        return None
    data = payload.get("results", [])
    if not data:
        return None
    item = data[0]
    res = {
        "source": "openalex",
        "doi": item.get("doi"),
        "title": normalize_whitespace(item.get("title") or item.get("display_name") or ""),
        "authors": [a.get("author", {}).get("display_name") for a in item.get("authorships", []) if a.get("author")],
        "year": str(item.get("publication_year")) if item.get("publication_year") else None,
        "venue": (item.get("primary_location") or {}).get("source", {}).get("display_name"),
        "url": item.get("id"),
    }
    cache.set(ck, res)
    return res
