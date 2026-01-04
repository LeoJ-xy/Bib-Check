import time
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

from .cache import HTTPCache
from .normalize import normalize_authors, normalize_doi, normalize_title, normalize_venue, title_similarity, contains_cjk
from .sources.crossref import CrossrefClient
from .sources.openalex import OpenAlexClient
from .sources.semanticscholar import SemanticScholarClient

Issue = Dict[str, object]
Entry = Dict[str, object]


@dataclass
class OnlineValidatorConfig:
    offline: bool = False
    sources: List[str] = None
    verbose: bool = False
    user_agent: str = "bibcheck/0.1"

    def __post_init__(self):
        if self.sources is None:
            self.sources = ["crossref", "openalex", "s2"]


class OnlineValidator:
    def __init__(self, config: OnlineValidatorConfig, cache: Optional[HTTPCache] = None):
        self.config = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = config.user_agent
        self.cache = cache or HTTPCache()
        self.rate_marks = {"crossref": 0.0, "openalex": 0.0, "s2": 0.0}
        self.clients = {
            "crossref": CrossrefClient(self.session, self.cache, self._rate_limit),
            "openalex": OpenAlexClient(self.session, self.cache, self._rate_limit),
            "s2": SemanticScholarClient(self.session, self.cache, self._rate_limit),
        }

    def _rate_limit(self, source: str):
        last = self.rate_marks.get(source, 0.0)
        now = time.time()
        elapsed = now - last
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self.rate_marks[source] = time.time()

    def validate_entry(self, entry: Entry) -> Dict[str, object]:
        online_data = {
            "checked": False,
            "resolved": None,
            "title_match_score": None,
            "candidate_matches": [],
        }
        if self.config.offline:
            return online_data

        online_data["checked"] = True
        doi = normalize_doi(entry.get("doi"))
        issues: List[Issue] = []
        resolved = None

        if doi:
            resolved, candidate_matches, issues = self._check_with_doi(entry, doi)
            online_data["resolved"] = resolved
            online_data["candidate_matches"] = candidate_matches
            if resolved:
                online_data["title_match_score"] = title_similarity(entry.get("title", ""), resolved.get("title", ""))
        else:
            resolved, candidate_matches, issues = self._search_without_doi(entry)
            online_data["resolved"] = resolved
            online_data["candidate_matches"] = candidate_matches
            if resolved:
                online_data["title_match_score"] = title_similarity(entry.get("title", ""), resolved.get("title", ""))

        entry.setdefault("_online_issues", []).extend(issues)
        return online_data

    def _check_with_doi(self, entry: Entry, doi: str) -> Tuple[Optional[dict], List[dict], List[Issue]]:
        issues: List[Issue] = []
        candidate_matches: List[dict] = []
        resolved = None
        for src in self.config.sources:
            client = self.clients.get(src)
            if not client:
                continue
            metadata = client.fetch_by_doi(doi)
            if metadata:
                resolved = metadata
                break
        if not resolved:
            issues.append(
                {
                    "type": "DOI_NOT_FOUND",
                    "severity": "ERROR",
                    "message": f"在线数据源均未找到 DOI {doi}",
                    "details": {},
                }
            )
            return None, candidate_matches, issues

        issues.extend(self._compare_metadata(entry, resolved))
        return resolved, candidate_matches, issues

    def _search_without_doi(self, entry: Entry) -> Tuple[Optional[dict], List[dict], List[Issue]]:
        issues: List[Issue] = []
        candidate_matches: List[dict] = []
        norm_title = normalize_title(entry.get("title", ""))
        authors = normalize_authors(entry.get("author", ""))
        first_author = authors[0] if authors else ""
        year = entry.get("year")

        best_candidate = None
        best_score = 0
        for src in self.config.sources:
            client = self.clients.get(src)
            if not client:
                continue
            matches = client.search(norm_title, year, first_author)
            for m in matches:
                score = title_similarity(entry.get("title", ""), m.get("title", ""))
                m["score"] = score
                candidate_matches.append(m)
                if score > best_score:
                    best_score = score
                    best_candidate = m

        if best_candidate and best_score >= 80:
            issues.append(
                {
                    "type": "CANDIDATE_FOUND_NO_DOI",
                    "severity": "WARNING",
                    "message": f"找到高置信候选，建议补充 DOI {best_candidate.get('doi') or ''}".strip(),
                    "details": best_candidate,
                }
            )
            return best_candidate, candidate_matches, issues

        severity = "WARNING" if contains_cjk(entry.get("title", "")) else "ERROR"
        issues.append(
            {
                "type": "NOT_FOUND_ONLINE",
                "severity": severity,
                "message": "无法在线匹配到候选",
                "details": {},
            }
        )
        return None, candidate_matches, issues

    def _compare_metadata(self, entry: Entry, resolved: dict) -> List[Issue]:
        issues: List[Issue] = []
        score = title_similarity(entry.get("title", ""), resolved.get("title", ""))
        if score < 70:
            issues.append(
                {
                    "type": "TITLE_MISMATCH",
                    "severity": "ERROR",
                    "message": f"标题相似度过低 {score}",
                    "details": {"online_title": resolved.get("title")},
                }
            )
        elif score < 85:
            issues.append(
                {
                    "type": "TITLE_MISMATCH",
                    "severity": "WARNING",
                    "message": f"标题相似度一般 {score}",
                    "details": {"online_title": resolved.get("title")},
                }
            )

        online_year = resolved.get("year")
        local_year = entry.get("year")
        if online_year and local_year and online_year != local_year:
            try:
                ly = int(local_year)
                oy = int(online_year)
                if abs(ly - oy) == 1:
                    sev = "WARNING"
                else:
                    sev = "ERROR"
            except ValueError:
                sev = "ERROR"
            issues.append(
                {
                    "type": "YEAR_MISMATCH",
                    "severity": sev,
                    "message": f"年份不一致: 本地 {local_year} 在线 {online_year}",
                    "details": {},
                }
            )

        local_authors = normalize_authors(entry.get("author", ""))
        online_authors = resolved.get("authors", [])
        if local_authors and online_authors:
            if not _authors_match(local_authors, online_authors):
                issues.append(
                    {
                        "type": "AUTHOR_MISMATCH",
                        "severity": "ERROR",
                        "message": "作者不一致",
                        "details": {"online_authors": online_authors},
                    }
                )

        local_venue = _clean_venue(normalize_venue(entry))
        online_venue = _clean_venue(resolved.get("venue") or "")
        if local_venue and online_venue and local_venue not in online_venue and online_venue not in local_venue:
            issues.append(
                {
                    "type": "VENUE_MISMATCH",
                    "severity": "WARNING",
                    "message": f"venue 不一致: 本地 {local_venue} 在线 {online_venue}",
                    "details": {},
                }
            )
        return issues


def _authors_match(local: List[str], online: List[str]) -> bool:
    if not local or not online:
        return True
    local_first = _surname(local[0])
    online_first = _surname(online[0])
    if local_first and online_first and local_first.lower() != online_first.lower():
        return False
    if abs(len(local) - len(online)) > 3:
        return False
    return True


def _surname(author: str) -> str:
    if "," in author:
        # 形如 "He, Kaiming" -> 取逗号前部分的最后一个词
        left = author.split(",")[0].strip()
        parts = left.split()
        return parts[-1] if parts else left
    parts = author.replace(",", " ").split()
    return parts[-1] if parts else author


def _clean_venue(venue: str) -> str:
    v = venue.lower()
    # 去括号内容与年份
    v = re.sub(r"\([^)]*\)", " ", v)
    v = re.sub(r"\b(19|20)\d{2}\b", " ", v)
    # 去常见前缀
    v = re.sub(r"\bproceedings of the\b", " ", v)
    v = re.sub(r"\bproc\.?\b", " ", v)
    v = re.sub(r"\bconference on\b", " ", v)
    v = re.sub(r"\bieee\b", " ", v)
    v = re.sub(r"\bacm\b", " ", v)
    v = re.sub(r"\s+", " ", v)
    return v.strip()

