import re
import string
from typing import List, Optional

from rapidfuzz import fuzz


_latex_cmd_re = re.compile(r"\\[a-zA-Z]+\s*|\{|\}")
_latex_math_re = re.compile(r"\$[^$]*\$")
_whitespace_re = re.compile(r"\s+")
_punct_tbl = str.maketrans("", "", string.punctuation)


def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = _latex_math_re.sub(" ", title)
    t = _latex_cmd_re.sub(" ", t)
    t = t.translate(_punct_tbl)
    t = _whitespace_re.sub(" ", t).strip().lower()
    return t


def normalize_authors(authors: Optional[str]) -> List[str]:
    """优先按 'and' 分隔作者，避免把“Last, First”误拆。"""
    if not authors:
        return []
    # 若包含 and，以 and 为准
    if re.search(r"\band\b", authors, flags=re.I):
        parts = re.split(r"\s+and\s+", authors, flags=re.I)
    elif ";" in authors:
        parts = authors.split(";")
    else:
        # 最后兜底才用逗号，避免误拆姓/名
        parts = [authors]
    return [a.strip() for a in parts if a.strip()]


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    return doi.strip()


def normalize_venue(entry: dict) -> str:
    return entry.get("journal") or entry.get("booktitle") or entry.get("publisher") or ""


def title_similarity(a: str, b: str) -> int:
    na = normalize_title(a)
    nb = normalize_title(b)
    if not na or not nb:
        return 0
    return int(fuzz.token_set_ratio(na, nb))


def contains_cjk(text: str) -> bool:
    if not text:
        return False
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)
