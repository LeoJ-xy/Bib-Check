import re
from typing import List, Optional


def normalize_pages(pages: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    """规范化 pages：去掉前缀，统一双短横。"""
    if pages is None:
        return fallback
    p = pages.strip()
    p = re.sub(r"^[pP]\.?\s*", "", p)
    p = p.replace("–", "-").replace("—", "-")
    if re.fullmatch(r"\d+-\d+", p):
        start, end = p.split("-")
        if start == end:
            return start
        return f"{start}--{end}"
    if re.fullmatch(r"\d+", p):
        return p
    # 若格式异常且提供 fallback，则用 fallback
    if fallback:
        return normalize_pages(fallback)
    return p


def normalize_doi_value(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    return doi.strip()


def format_authors_list(authors: List[str]) -> str:
    """将作者列表格式化为 BibTeX author 字段的 'Last, First and ...'。"""
    formatted = []
    for a in authors:
        name = a.strip()
        if "," in name:
            formatted.append(name)
            continue
        parts = name.split()
        if len(parts) == 1:
            formatted.append(parts[0])
        else:
            last = parts[-1]
            first = " ".join(parts[:-1])
            formatted.append(f"{last}, {first}")
    return " and ".join(formatted)
import re
from typing import List, Optional

from ..normalize import normalize_doi


def format_authors_bibtex(authors: List[str]) -> str:
    """
    把 ['Kaiming He','Xiangyu Zhang'] 转换为 'He, Kaiming and Zhang, Xiangyu'
    若已经是 'Last, First' 格式则直接保留。
    """
    formatted = []
    for a in authors:
        if "," in a:
            formatted.append(a.strip())
            continue
        parts = a.strip().split()
        if len(parts) == 1:
            formatted.append(parts[0])
            continue
        last = parts[-1]
        first = " ".join(parts[:-1])
        formatted.append(f"{last}, {first}")
    return " and ".join([x for x in formatted if x])


def normalize_pages(pages: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    if not pages:
        return fallback
    p = pages.strip()
    p = re.sub(r"^p\.?\s*", "", p, flags=re.I)
    p = p.replace("–", "-").replace("—", "-")
    if "-" in p and "--" not in p:
        p = p.replace("-", "--", 1)
    if not re.fullmatch(r"\d+(--\d+)?", p):
        return fallback or p
    return p


def normalize_doi_str(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    return normalize_doi(doi)

