import time
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

from .kind import classify_entry, extract_arxiv_id, extract_github_repo, get_field
from .matching import compute_match_confidence
from .cache import HTTPCache
from .normalize import normalize_authors, normalize_doi, normalize_title, normalize_venue, title_similarity, contains_cjk
from .sources.arxiv import ArxivClient
from .sources.citation_cff import CitationCffClient
from .sources.crossref import CrossrefClient
from .sources.dblp import DblpClient
from .sources.openalex import OpenAlexClient
from .sources.semanticscholar import SemanticScholarClient

Issue = Dict[str, object]
Entry = Dict[str, object]


@dataclass
class OnlineValidatorConfig:
    offline: bool = False
    sources: List[str] = None
    verbose: bool = False
    user_agent: str = "bibcheck/1.5"
    enable_arxiv: bool = True
    enable_dblp: bool = False
    enable_citation_cff: bool = True
    high_conf: float = 0.8
    mid_conf: float = 0.6

    def __post_init__(self):
        if self.sources is None:
            self.sources = ["crossref", "openalex", "s2"]


class OnlineValidator:
    def __init__(self, config: OnlineValidatorConfig, cache: Optional[HTTPCache] = None):
        self.config = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = config.user_agent
        self.cache = cache or HTTPCache()
        self.rate_marks = {
            "crossref": 0.0,
            "openalex": 0.0,
            "s2": 0.0,
            "arxiv": 0.0,
            "dblp": 0.0,
            "citation_cff": 0.0,
        }
        self.rate_delays = {
            "crossref": 1.0,
            "openalex": 1.0,
            "s2": 1.0,
            "arxiv": 3.0,
            "dblp": 1.0,
            "citation_cff": 1.0,
        }
        self.clients = {
            "crossref": CrossrefClient(self.session, self.cache, self._rate_limit),
            "openalex": OpenAlexClient(self.session, self.cache, self._rate_limit),
            "s2": SemanticScholarClient(self.session, self.cache, self._rate_limit),
            "arxiv": ArxivClient(self.session, self.cache, self._rate_limit),
            "dblp": DblpClient(self.session, self.cache, self._rate_limit),
            "citation_cff": CitationCffClient(self.session, self.cache, self._rate_limit),
        }

    def _rate_limit(self, source: str):
        last = self.rate_marks.get(source, 0.0)
        now = time.time()
        elapsed = now - last
        delay = self.rate_delays.get(source, 1.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.rate_marks[source] = time.time()

    def validate_entry(self, entry: Entry) -> Dict[str, object]:
        online_data = {
            "checked": False,
            "resolved": None,
            "title_match_score": None,
            "candidate_matches": [],
            "entry_kind": None,
        }
        if self.config.offline:
            return online_data

        online_data["checked"] = True
        entry_kind = classify_entry(entry)
        online_data["entry_kind"] = entry_kind
        doi = normalize_doi(get_field(entry, "doi"))
        issues: List[Issue] = []
        resolved = None

        if doi and not _valid_doi_for_lookup(doi):
            return online_data

        if doi:
            resolved, candidate_matches, issues = self._check_with_doi(entry, doi)
            online_data["resolved"] = resolved
            online_data["candidate_matches"] = candidate_matches
            if resolved:
                online_data["title_match_score"] = title_similarity(entry.get("title", ""), resolved.get("title", ""))
        else:
            if entry_kind == "preprint_arxiv" and self.config.enable_arxiv:
                arxiv_id = extract_arxiv_id(entry)
                resolved, candidate_matches, issues = self._check_with_arxiv(entry, arxiv_id)
            elif entry_kind == "software_github" and self.config.enable_citation_cff:
                repo = extract_github_repo(entry)
                resolved, candidate_matches, issues = self._check_with_citation_cff(entry, repo)
            elif entry_kind == "web_generic":
                resolved, candidate_matches, issues = None, [], []
            else:
                resolved, candidate_matches, issues = self._search_without_doi(entry, entry_kind)
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
            source_errors = self._collect_source_errors(self.config.sources)
            if source_errors:
                issues.append(
                    self._source_unavailable_issue(
                        "ONLINE_SOURCE_UNAVAILABLE",
                        "Some online sources are temporarily unavailable; DOI existence could not be confirmed.",
                        source_errors,
                    )
                )
                return None, candidate_matches, issues
            issues.append(
                {
                    "type": "DOI_NOT_FOUND",
                    "severity": "ERROR",
                    "message": f"No configured online source found DOI {doi}",
                    "details": {},
                }
            )
            return None, candidate_matches, issues

        issues.extend(self._compare_metadata(entry, resolved))
        return resolved, candidate_matches, issues

    def _check_with_arxiv(self, entry: Entry, arxiv_id: Optional[str]) -> Tuple[Optional[dict], List[dict], List[Issue]]:
        issues: List[Issue] = []
        candidate_matches: List[dict] = []
        if not arxiv_id:
            issues.append(
                {
                    "type": "NOT_FOUND_ON_ARXIV",
                    "severity": "ERROR",
                    "message": "Unable to parse arXiv ID",
                    "details": {},
                }
            )
            return None, candidate_matches, issues
        client = self.clients.get("arxiv")
        resolved = client.fetch_by_id(arxiv_id) if client else None
        if not resolved:
            source_errors = self._collect_source_errors(["arxiv"])
            if source_errors:
                issues.append(
                    self._source_unavailable_issue(
                        "ARXIV_SOURCE_UNAVAILABLE",
                        f"The arXiv API is temporarily unavailable; existence of {arxiv_id} could not be confirmed.",
                        source_errors,
                    )
                )
                return None, candidate_matches, issues
            issues.append(
                {
                    "type": "NOT_FOUND_ON_ARXIV",
                    "severity": "ERROR",
                    "message": f"arXiv did not find {arxiv_id}",
                    "details": {"arxiv_id": arxiv_id},
                }
            )
            return None, candidate_matches, issues
        candidate_matches.append(resolved)
        resolved, candidate_matches, gate_issues = self._apply_confidence_gating(entry, candidate_matches, "preprint_arxiv")
        issues.extend(gate_issues)
        return resolved, candidate_matches, issues

    def _check_with_citation_cff(self, entry: Entry, repo: Optional[str]) -> Tuple[Optional[dict], List[dict], List[Issue]]:
        issues: List[Issue] = []
        candidate_matches: List[dict] = []
        if not repo:
            issues.append(
                {
                    "type": "CITATION_CFF_MISSING",
                    "severity": "WARNING",
                    "message": "GitHub repository URL was not recognized; CITATION.cff cannot be fetched.",
                    "details": {},
                }
            )
            return None, candidate_matches, issues
        owner, repo_name = repo.split("/", 1)
        client = self.clients.get("citation_cff")
        result = client.fetch_by_repo(owner, repo_name) if client else {"status": "missing", "candidate": None}
        if result.get("status") != "found":
            source_errors = self._collect_source_errors(["citation_cff"])
            if source_errors:
                issues.append(
                    self._source_unavailable_issue(
                        "CITATION_CFF_UNAVAILABLE",
                        "GitHub CITATION.cff is temporarily unavailable.",
                        source_errors,
                    )
                )
                return None, candidate_matches, issues
            issues.append(
                {
                    "type": "CITATION_CFF_MISSING",
                    "severity": "WARNING",
                    "message": "CITATION.cff was not found (optional).",
                    "details": {"repo": repo},
                }
            )
            return None, candidate_matches, issues
        candidate = result.get("candidate")
        if candidate:
            candidate_matches.append(candidate)
        resolved, candidate_matches, gate_issues = self._apply_confidence_gating(entry, candidate_matches, "software_github")
        issues.extend(gate_issues)
        return resolved, candidate_matches, issues

    def _search_without_doi(self, entry: Entry, entry_kind: str) -> Tuple[Optional[dict], List[dict], List[Issue]]:
        issues: List[Issue] = []
        candidate_matches: List[dict] = []
        norm_title = normalize_title(entry.get("title", ""))
        authors = normalize_authors(entry.get("author", ""))
        first_author = authors[0] if authors else ""
        year = entry.get("year")

        sources = list(self.config.sources)
        arxiv_id = extract_arxiv_id(entry)
        if self.config.enable_arxiv and arxiv_id:
            client = self.clients.get("arxiv")
            arxiv_match = client.fetch_by_id(arxiv_id) if client else None
            if arxiv_match:
                arxiv_match["score"] = title_similarity(entry.get("title", ""), arxiv_match.get("title", ""))
                candidate_matches.append(arxiv_match)
        if self.config.enable_dblp and entry_kind == "scholarly_cslike":
            sources.append("dblp")
        for src in sources:
            client = self.clients.get(src)
            if not client:
                continue
            matches = client.search(norm_title, year, first_author)
            for m in matches:
                score = title_similarity(entry.get("title", ""), m.get("title", ""))
                m["score"] = score
                candidate_matches.append(m)

        if not candidate_matches:
            source_errors = self._collect_source_errors(sources)
            if source_errors:
                issues.append(
                    self._source_unavailable_issue(
                        "ONLINE_SOURCE_UNAVAILABLE",
                        "Some online sources are temporarily unavailable; candidate search could not be completed.",
                        source_errors,
                    )
                )
                return None, candidate_matches, issues

        resolved, candidate_matches, gate_issues = self._apply_confidence_gating(entry, candidate_matches, entry_kind)
        issues.extend(gate_issues)
        return resolved, candidate_matches, issues

    def _collect_source_errors(self, sources: List[str]) -> List[dict]:
        errors = []
        for src in sources:
            client = self.clients.get(src)
            error = getattr(client, "last_error", None)
            if error:
                errors.append(error)
        return errors

    def _source_unavailable_issue(self, issue_type: str, message: str, source_errors: List[dict]) -> Issue:
        return {
            "type": issue_type,
            "severity": "WARNING",
            "message": message,
            "details": {"sources": source_errors},
        }

    def _apply_confidence_gating(self, entry: Entry, candidates: List[dict], entry_kind: str) -> Tuple[Optional[dict], List[dict], List[Issue]]:
        issues: List[Issue] = []
        if not candidates:
            if entry_kind in {"scholarly_doi", "preprint_arxiv", "scholarly_cslike", "unknown"}:
                severity = "WARNING" if contains_cjk(entry.get("title", "")) else "ERROR"
                issues.append(
                    {
                        "type": "NOT_FOUND_ONLINE",
                        "severity": severity,
                        "message": "No online candidate could be matched.",
                        "details": {},
                    }
                )
            return None, candidates, issues

        for c in candidates:
            if "score" not in c:
                c["score"] = title_similarity(entry.get("title", ""), c.get("title", ""))
            conf, components = compute_match_confidence(entry, c)
            c["confidence"] = conf
            c["confidence_components"] = components

        candidates.sort(key=lambda m: m.get("confidence", 0.0), reverse=True)
        best = candidates[0]
        best_conf = best.get("confidence", 0.0)

        if best_conf >= self.config.high_conf:
            resolved = best
            if not entry.get("doi") and best.get("doi"):
                issues.append(
                    {
                        "type": "CANDIDATE_FOUND_NO_DOI",
                        "severity": "WARNING",
                        "message": f"High-confidence candidate found; consider adding DOI {best.get('doi') or ''}".strip(),
                        "details": best,
                    }
                )
            issues.extend(self._compare_metadata(entry, resolved))
            return resolved, candidates, issues

        top_candidates = [
            {
                "title": c.get("title"),
                "year": c.get("year"),
                "doi": c.get("doi"),
                "source": c.get("source"),
                "confidence": c.get("confidence"),
            }
            for c in candidates[:3]
        ]
        if best_conf >= self.config.mid_conf:
            issues.append(
                {
                    "type": "AMBIGUOUS_MATCH",
                    "severity": "WARNING",
                    "message": "Candidate match has medium confidence and needs manual review.",
                    "details": {"candidates": top_candidates},
                }
            )
            return None, candidates, issues

        issues.append(
            {
            "type": "LOW_CONFIDENCE_CANDIDATE",
            "severity": "WARNING",
            "message": "Candidate confidence is too low; manual review is recommended.",
                "details": {"candidates": top_candidates},
            }
        )
        return None, candidates, issues

    def _compare_metadata(self, entry: Entry, resolved: dict) -> List[Issue]:
        issues: List[Issue] = []
        score = title_similarity(entry.get("title", ""), resolved.get("title", ""))
        if score < 70:
            issues.append(
                {
                    "type": "TITLE_MISMATCH",
                    "severity": "ERROR",
                    "message": f"Title similarity is too low: {score}",
                    "details": {"online_title": resolved.get("title")},
                }
            )
        elif score < 85:
            issues.append(
                {
                    "type": "TITLE_MISMATCH",
                    "severity": "WARNING",
                    "message": f"Title similarity is moderate: {score}",
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
                    "message": f"Year mismatch: local {local_year}, online {online_year}",
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
                        "message": "Author list mismatch",
                        "details": {"online_authors": online_authors},
                    }
                )

        local_venue = _clean_venue(normalize_venue(entry))
        online_venue = _clean_venue(resolved.get("venue") or "")
        skip_arxiv_copy_venue = resolved.get("source") == "arxiv" and local_venue and "arxiv" not in local_venue
        if local_venue and online_venue and not skip_arxiv_copy_venue and not _venue_match(local_venue, online_venue):
            issues.append(
                {
                    "type": "VENUE_MISMATCH",
                    "severity": "WARNING",
                    "message": f"Venue mismatch: local {local_venue}, online {online_venue}",
                    "details": {},
                }
            )
        return issues


def _valid_doi_for_lookup(doi: str) -> bool:
    return bool(doi and re.fullmatch(r"10\.\d{4,9}/\S+", doi))


def _authors_match(local: List[str], online: List[str]) -> bool:
    if not local or not online:
        return True
    local_has_wildcard = any(a.strip().lower().strip("{} ") in {"others", "other", "et al", "et al.", "etal"} for a in local)
    local_first = _surname(local[0])
    online_first = _surname(online[0])
    if local_first and online_first and local_first.lower() != online_first.lower():
        return False
    if not local_has_wildcard and abs(len(local) - len(online)) > 3:
        return False
    return True


def _surname(author: str) -> str:
    author = (author or "").replace("{", " ").replace("}", " ").strip()
    if "," in author:
        # For "He, Kaiming", use the final token before the comma as the surname.
        left = author.split(",")[0].strip()
        parts = left.split()
        return _clean_author_token(parts[-1] if parts else left)
    parts = author.replace(",", " ").split()
    return _clean_author_token(parts[-1] if parts else author)


def _clean_author_token(value: str) -> str:
    token = "".join(ch.lower() for ch in value if ch.isalnum())
    if token in {"etal", "others", "other"}:
        return ""
    return token


def _clean_venue(venue: str) -> str:
    v = venue.lower().replace("{", " ").replace("}", " ")
    # Remove parenthesized text and years.
    v = re.sub(r"\([^)]*\)", " ", v)
    v = re.sub(r"\b(19|20)\d{2}\b", " ", v)
    # Remove common venue prefixes.
    v = re.sub(r"\bproceedings of the\b", " ", v)
    v = re.sub(r"\bproc\.?\b", " ", v)
    v = re.sub(r"\bconference on\b", " ", v)
    v = re.sub(r"\bieee\b", " ", v)
    v = re.sub(r"\bacm\b", " ", v)
    v = re.sub(r"[^a-z0-9]+", " ", v)
    v = re.sub(r"\s+", " ", v)
    return v.strip()


def _venue_match(local: str, online: str) -> bool:
    if local in online or online in local:
        return True
    local_aliases = _venue_aliases(local)
    online_aliases = _venue_aliases(online)
    return bool(local_aliases.intersection(online_aliases))


def _venue_aliases(venue: str) -> set:
    aliases = {venue}
    if "icml" in venue or "international conference machine learning" in venue:
        aliases.add("icml")
    if "neurips" in venue or "nips" in venue or "neural information processing systems" in venue:
        aliases.add("neurips")
    if "royal statistical society series b" in venue:
        aliases.add("jrssb")
    if "compstat" in venue:
        aliases.add("compstat")
    return aliases
