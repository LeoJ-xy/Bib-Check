import re
import requests


def fetch_blog(url: str, session: requests.Session, cache, user_agent: str):
    if not url:
        return None
    ck = f"blog:{url}"
    cached = cache.get(ck)
    if cached:
        return cached
    headers = {"User-Agent": user_agent}
    try:
        r = session.get(url, headers=headers, timeout=20, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code >= 400:
        return None
    html = r.text
    resolved_url = r.url
    data = {
        "source": "web",
        "url": resolved_url,
        "title": _extract_title(html),
        "canonical_url": _extract_canonical(html) or resolved_url,
        "authors": _extract_meta_list(html, ["citation_author", "author"]),
        "published_date": _extract_meta_first(html, ["citation_publication_date", "article:published_time"]),
        "bibtex_snippet": _extract_bibtex_block(html),
        "evidence": {},
    }
    cache.set(ck, data)
    return data


def _extract_title(html: str):
    m = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r'property="og:title"\s+content="([^"]+)"', html, flags=re.I)
    if m:
        return m.group(1).strip()
    return None


def _extract_canonical(html: str):
    m = re.search(r'rel="canonical"\s+href="([^"]+)"', html, flags=re.I)
    if m:
        return m.group(1).strip()
    return None


def _extract_meta_list(html: str, names):
    vals = []
    for n in names:
        for m in re.finditer(rf'name="{n}"\s+content="([^"]+)"', html, flags=re.I):
            vals.append(m.group(1).strip())
    return vals


def _extract_meta_first(html: str, names):
    for n in names:
        m = re.search(rf'(name|property)="{n}"\s+content="([^"]+)"', html, flags=re.I)
        if m:
            return m.group(2).strip()
    return None


def _extract_bibtex_block(html: str):
    # 简化：找包含 @misc/@article 的 <pre><code> 或 ``` 块
    m = re.search(r"<pre><code[^>]*>(.*?)</code></pre>", html, flags=re.I | re.S)
    if m and "@misc" in m.group(1) or "@article" in m.group(1):
        return m.group(1).strip()
    fence = re.search(r"```(?:bibtex)?(.*?)```", html, flags=re.I | re.S)
    if fence and ("@misc" in fence.group(1) or "@article" in fence.group(1)):
        return fence.group(1).strip()
    return None

