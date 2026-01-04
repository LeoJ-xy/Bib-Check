import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from .normalize import normalize_doi, normalize_venue

Issue = Dict[str, object]
Entry = Dict[str, object]

REQUIRED_FIELDS = {
    "article": ["title", "author", "year", "journal"],
    "inproceedings": ["title", "author", "year", "booktitle"],
    "proceedings": ["title", "year"],
    "book": ["title", "author", "year", "publisher"],
    "misc": ["title"],
}


def run_static_validations(entries: List[Entry]) -> Dict[str, List[Issue]]:
    issues_by_key: Dict[str, List[Issue]] = defaultdict(list)
    citekey_counter = defaultdict(int)
    for e in entries:
        citekey_counter[e["ID"]] += 1
    for key, cnt in citekey_counter.items():
        if cnt > 1:
            issues_by_key[key].append(
                {
                    "type": "DUPLICATE_CITEKEY",
                    "severity": "ERROR",
                    "message": f"citekey `{key}` 重复 {cnt} 次",
                    "details": {},
                }
            )

    current_year = datetime.now().year
    for e in entries:
        key = e["ID"]
        etype = e.get("ENTRYTYPE", "").lower()
        required = REQUIRED_FIELDS.get(etype, ["title", "author", "year"])
        missing = [f for f in required if not e.get(f)]
        if missing:
            issues_by_key[key].append(
                {
                    "type": "MISSING_REQUIRED_FIELDS",
                    "severity": "ERROR",
                    "message": f"缺少必要字段: {', '.join(missing)}",
                    "details": {"missing": missing},
                }
            )

        year_val = e.get("year")
        if year_val and not _valid_year(year_val, current_year):
            issues_by_key[key].append(
                {
                    "type": "BAD_YEAR",
                    "severity": "ERROR",
                    "message": f"year 非法: {year_val}",
                    "details": {},
                }
            )

        doi_raw = e.get("doi")
        if doi_raw:
            doi = normalize_doi(doi_raw)
            if not _valid_doi(doi):
                issues_by_key[key].append(
                    {
                        "type": "BAD_DOI_FORMAT",
                        "severity": "ERROR",
                        "message": f"DOI 格式异常: {doi_raw}",
                        "details": {},
                    }
                )

        url_val = e.get("url")
        if url_val and not _valid_url(url_val):
            issues_by_key[key].append(
                {
                    "type": "BAD_URL_FORMAT",
                    "severity": "WARNING",
                    "message": f"URL 格式异常: {url_val}",
                    "details": {"url": url_val},
                }
            )

        pages_val = e.get("pages")
        if pages_val:
            norm_pages = normalize_pages_field(pages_val)
            if not _pages_ok(norm_pages):
                issues_by_key[key].append(
                    {
                        "type": "SUSPICIOUS_METADATA",
                        "severity": "WARNING",
                        "message": "pages 格式异常",
                        "details": {
                            "pages_raw": pages_val,
                            "pages_norm": norm_pages,
                            "pattern": "digit or A?digit with -- range",
                            "hint": "将 –/— 改为 --，或将单短横范围改为双短横",
                        },
                    }
                )

        suspicious = _detect_suspicious(e)
        if suspicious:
            issues_by_key[key].append(
                {
                    "type": "SUSPICIOUS_METADATA",
                    "severity": "WARNING",
                    "message": "; ".join(suspicious),
                    "details": {},
                }
            )
    return issues_by_key


def _valid_year(year: str, current_year: int) -> bool:
    if not re.fullmatch(r"\d{4}", str(year).strip()):
        return False
    val = int(year)
    return 1500 <= val <= current_year + 1


def _valid_doi(doi: str) -> bool:
    if not doi:
        return False
    return bool(re.fullmatch(r"10\.\d{4,9}/\S+", doi))


def _valid_url(url: str) -> bool:
    return bool(re.fullmatch(r"https?://[^\s]+", url.strip()))


def _detect_suspicious(entry: Entry) -> List[str]:
    msgs = []
    title = entry.get("title", "")
    if title and (title.isupper() or title.islower()):
        msgs.append("标题大小写异常")
    authors = entry.get("author", "")
    if authors and len(authors.split("and")) > 20:
        msgs.append("作者数量过多，疑似格式问题")
    venue = normalize_venue(entry)
    if venue and len(venue) < 3:
        msgs.append("venue 过短，疑似缺失")
    return msgs


def normalize_pages_field(p: str) -> str:
    p = (p or "").strip()
    p = p.replace("–", "--").replace("—", "--")
    p = re.sub(r"(\d)\s*-\s*(\d)", r"\1--\2", p)
    p = re.sub(r"\s+", " ", p)
    return p


def _pages_ok(p: str) -> bool:
    if not p:
        return False
    if re.fullmatch(r"\d+", p):
        return True
    if re.fullmatch(r"\d+--\d+", p):
        return True
    if re.fullmatch(r"[A-Za-z]?\d+--[A-Za-z]?\d+", p):
        return True
    return False


