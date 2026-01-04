import bibtexparser
from .blog_detector import is_web_scholarly
from .resolvers.blog_resolver import fetch_blog
from .matchers.title_match import title_score
from .matchers.author_match import author_score
from .core.confidence import confidence


def plan_blog_fix(entry: dict, session, cache, user_agent: str, min_conf: float, accessed_date: str):
    if not is_web_scholarly(entry):
        return [], []
    resolved = fetch_blog(entry.get("url"), session, cache, user_agent)
    if not resolved:
        return [], []
    suggested = []
    applied = []
    t = title_score(entry.get("title"), resolved.get("title"))
    a = author_score(entry.get("author", ""), resolved.get("authors", []))
    conf = confidence(t, a, 0.0, resolved_by_doi=False)

    def add_patch(field, new, source="web", conf_override=None):
        c = conf_override if conf_override is not None else conf
        patch = {"citekey": entry["ID"], "field": field, "old": entry.get(field), "new": new, "confidence": c, "source": source}
        suggested.append(patch)
        if c >= min_conf:
            entry[field] = new
            applied.append(patch)

    if resolved.get("canonical_url") and resolved.get("canonical_url") != entry.get("url"):
        add_patch("url", resolved["canonical_url"], source="web:canonical", conf_override=0.9)
    if resolved.get("title"):
        add_patch("title", resolved["title"])
    if resolved.get("authors"):
        add_patch("author", " and ".join(resolved["authors"]))
    if resolved.get("published_date"):
        year = resolved["published_date"][:4]
        add_patch("year", year)
        if len(resolved["published_date"]) >= 7:
            add_patch("month", resolved["published_date"][5:7])
        if len(resolved["published_date"]) >= 10:
            add_patch("day", resolved["published_date"][8:10])

    add_patch("howpublished", "Research Blog", source="web:blog", conf_override=0.9)
    if accessed_date:
        note = entry.get("note") or ""
        if "Accessed" not in note:
            add_patch("note", f"Accessed: {accessed_date}", source="web:accessed", conf_override=0.9)

    if resolved.get("bibtex_snippet"):
        try:
            parsed = bibtexparser.loads(resolved["bibtex_snippet"])
            if parsed.entries:
                snippet_entry = parsed.entries[0]
                for k, v in snippet_entry.items():
                    if k in ("ID", "ENTRYTYPE"):
                        continue
                    add_patch(k, v, source="web:bibtex", conf_override=0.95)
        except Exception:
            pass
    return suggested, applied

