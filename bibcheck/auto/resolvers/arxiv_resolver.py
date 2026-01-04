import re
import requests


def extract_arxiv_id(text: str):
    if not text:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})", text)
    if m:
        return m.group(1)
    m = re.search(r"arxiv\.org/(abs|pdf)/([\w\.\-]+)", text)
    if m:
        return m.group(2)
    return None


def resolve_arxiv(eprint_or_url: str, session: requests.Session, cache, user_agent: str):
    arxid = extract_arxiv_id(eprint_or_url)
    if not arxid:
        return None
    ck = f"arxiv:{arxid}"
    cached = cache.get(ck)
    if cached:
        return cached
    headers = {"User-Agent": user_agent}
    # 简化：使用 arXiv export API
    api = f"https://export.arxiv.org/api/query?id_list={arxid}"
    r = session.get(api, headers=headers, timeout=10)
    if r.status_code != 200:
        return None
    # 这里为简化，仅返回关键字段；实际可解析 Atom XML
    data = {
        "source": "arxiv",
        "eprint": arxid,
        "title": None,
        "authors": [],
        "year": None,
        "venue": "arXiv",
        "url": f"https://arxiv.org/abs/{arxid}",
        "doi": f"10.48550/arxiv.{arxid}".lower(),
    }
    cache.set(ck, data)
    return data

