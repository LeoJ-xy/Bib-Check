import requests


def search_crossref(title: str, session: requests.Session, cache, user_agent: str):
    if not title:
        return None
    ck = f"crossref:search:{title}"
    cached = cache.get(ck)
    if cached:
        return cached
    headers = {"User-Agent": user_agent}
    params = {"query.bibliographic": title, "rows": 1}
    r = session.get("https://api.crossref.org/works", params=params, headers=headers, timeout=10)
    if r.status_code != 200:
        return None
    items = r.json().get("message", {}).get("items", [])
    if not items:
        return None
    item = items[0]
    data = {
        "source": "crossref",
        "doi": item.get("DOI"),
        "title": " ".join(item.get("title") or []),
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

