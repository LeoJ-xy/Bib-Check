import re

DEFAULT_BLOG_DOMAINS = [
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "transformer-circuits.pub",
    "distill.pub",
    "github.com",
    "notion.site",
    "notion.so",
    "substack.com",
    "medium.com",
    "ai.googleblog.com",
    "example.com",
]


def is_web_scholarly(entry: dict, allow_domains=None) -> bool:
    allow_domains = allow_domains or DEFAULT_BLOG_DOMAINS
    etype = entry.get("ENTRYTYPE", "").lower()
    url = entry.get("url") or ""
    doi = entry.get("doi")
    if not url:
        return False
    if etype in {"misc", "online", "techreport", "unpublished"} and (not doi):
        if _domain_match(url, allow_domains):
            return True
    hint = (entry.get("howpublished") or "") + " " + (entry.get("note") or "") + " " + (entry.get("journal") or "")
    if re.search(r"\b(blog|research|thread|project page|distill|transformer circuits)\b", hint, flags=re.I):
        return True
    return False


def _domain_match(url: str, allow_domains) -> bool:
    for d in allow_domains:
        if d in url:
            return True
    return False
