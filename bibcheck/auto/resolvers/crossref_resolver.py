import requests

from ...sources.common import normalize_whitespace, request_json


def search_crossref(title: str, session: requests.Session, cache, user_agent: str):
    if not title:
        return None
    ck = f"crossref:search:{title}"
    cached = cache.get(ck)
    if cached:
        return cached
    params = {"query.bibliographic": title, "rows": 1}
    payload, error = request_json(session, "https://api.crossref.org/works", params=params, timeout=10)
    if error or not payload:
        return None
    items = payload.get("message", {}).get("items", [])
    if not items:
        return None
    item = items[0]
    data = {
        "source": "crossref",
        "doi": item.get("DOI"),
        "title": normalize_whitespace(" ".join(item.get("title") or [])),
        "authors": [
            " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
            for a in item.get("author", []) if a.get("given") or a.get("family")
        ],
        "year": str((item.get("issued", {}).get("date-parts") or [[None]])[0][0]),
        "venue": (item.get("container-title") or [""])[0],
        "url": item.get("URL"),
    }
    cache.set(ck, data)
    return data
