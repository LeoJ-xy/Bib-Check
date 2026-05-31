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
                    "message": f"citekey `{key}` appears {cnt} times",
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
                    "message": f"Missing required fields: {', '.join(missing)}",
                    "details": {"missing": missing},
                }
            )

        year_val = e.get("year")
        if year_val and not _valid_year(year_val, current_year):
            issues_by_key[key].append(
                {
                    "type": "BAD_YEAR",
                    "severity": "ERROR",
                    "message": f"Invalid year: {year_val}",
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
                        "message": f"Invalid DOI format: {doi_raw}",
                        "details": {},
                    }
                )

        url_val = e.get("url")
        if url_val and not _valid_url(url_val):
            issues_by_key[key].append(
                {
                    "type": "BAD_URL_FORMAT",
                    "severity": "WARNING",
                    "message": f"Invalid URL format: {url_val}",
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
                        "message": "Invalid pages format",
                        "details": {
                            "pages_raw": pages_val,
                            "pages_norm": norm_pages,
                            "pattern": "digit or A?digit with -- range",
                            "hint": "Use -- for page ranges and replace en/em dashes or single hyphens in ranges.",
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
        msgs.append("Title capitalization looks suspicious")
    authors = entry.get("author", "")
    if _looks_like_author_separator_issue(authors):
        msgs.append("Author separators look suspicious")
    venue = normalize_venue(entry)
    if venue and len(venue) < 3:
        msgs.append("Venue is unusually short")
    return msgs


def _looks_like_author_separator_issue(authors: str) -> bool:
    if not authors:
        return False
    if re.search(r"\band\b", authors, flags=re.I):
        return False
    if ";" in authors:
        return False
    return authors.count(",") >= 4


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
