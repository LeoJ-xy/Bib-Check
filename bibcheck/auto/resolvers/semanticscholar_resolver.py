import requests


def search_s2(title: str, session: requests.Session, cache, user_agent: str):
    if not title:
        return None
    ck = f"s2:search:{title}"
    cached = cache.get(ck)
    if cached:
        return cached
    headers = {"User-Agent": user_agent}
    params = {"query": title, "limit": 1, "fields": "title,year,authors,venue,externalIds,url"}
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    r = session.get(url, params=params, headers=headers, timeout=10)
    if r.status_code != 200:
        return None
    data = r.json().get("data", [])
    if not data:
        return None
    item = data[0]
    doi = (item.get("externalIds") or {}).get("DOI")
    res = {
        "source": "s2",
        "doi": doi,
        "title": item.get("title"),
        "authors": [a.get("name") for a in item.get("authors", []) if a.get("name")],
        "year": str(item.get("year")) if item.get("year") else None,
        "venue": item.get("venue"),
        "url": item.get("url"),
    }
    cache.set(ck, res)
    return res

