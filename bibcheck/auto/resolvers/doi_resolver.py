import requests
from ..core.normalize import norm_doi


def resolve_doi(doi: str, session: requests.Session, cache, user_agent: str):
    doi = norm_doi(doi)
    if not doi:
        return None
    ck = f"doi:{doi}"
    cached = cache.get(ck)
    if cached:
        return cached
    headers = {"User-Agent": user_agent}
    url = f"https://api.crossref.org/works/{doi}"
    r = session.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return None
    msg = r.json().get("message", {})
    data = {
        "source": "crossref",
        "doi": msg.get("DOI"),
        "title": " ".join(msg.get("title") or []),
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

