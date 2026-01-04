import re


def norm_text(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def norm_doi(d: str) -> str:
    if not d:
        return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", d.strip(), flags=re.I)


def apostrophe_to_unicode(name: str) -> str:
    return name.replace(r"{\textquoteright}", "’").replace("'", "’")


def apostrophe_to_latex(name: str) -> str:
    return name.replace("’", r"{\textquoteright}")

