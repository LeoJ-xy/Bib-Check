from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from .normalize import normalize_title, normalize_authors, normalize_doi


def title_score(local_title: str, candidate_title: str) -> float:
    if not local_title or not candidate_title:
        return 0.0
    return fuzz.token_set_ratio(normalize_title(local_title), normalize_title(candidate_title)) / 100.0


def _surname(author: str) -> str:
    if not author:
        return ""
    if "," in author:
        left = author.split(",")[0].strip()
        parts = left.split()
        return parts[-1].lower() if parts else left.lower()
    parts = author.replace(",", " ").split()
    return parts[-1].lower() if parts else author.lower()


def author_score(local_author_field: str, candidate_authors: List[str]) -> float:
    local = normalize_authors(local_author_field)
    if not local or not candidate_authors:
        return 0.0
    local_surnames = {_surname(a) for a in local if _surname(a)}
    candidate_surnames = {_surname(a) for a in candidate_authors if _surname(a)}
    if not local_surnames or not candidate_surnames:
        return 0.0
    overlap = local_surnames.intersection(candidate_surnames)
    return len(overlap) / max(len(local_surnames), len(candidate_surnames))


def year_score(local_year: Optional[str], candidate_year: Optional[str]) -> float:
    if not local_year or not candidate_year:
        return 0.0
    try:
        ly = int(local_year)
        cy = int(candidate_year)
    except ValueError:
        return 0.0
    if ly == cy:
        return 1.0
    diff = abs(ly - cy)
    if diff == 1:
        return 0.8
    if diff == 2:
        return 0.5
    return 0.0


def venue_score(local_venue: str, candidate_venue: str) -> float:
    if not local_venue or not candidate_venue:
        return 0.0
    return fuzz.token_set_ratio(normalize_title(local_venue), normalize_title(candidate_venue)) / 100.0


def compute_match_confidence(entry: dict, candidate: dict) -> Tuple[float, Dict[str, float]]:
    local_doi = normalize_doi(entry.get("doi"))
    candidate_doi = normalize_doi(candidate.get("doi"))
    if local_doi and candidate_doi and local_doi.lower() == candidate_doi.lower():
        return 1.0, {"title": 1.0, "authors": 1.0, "year": 1.0, "venue": 1.0, "doi_match": 1.0}

    t_score = title_score(entry.get("title", ""), candidate.get("title", ""))
    a_score = author_score(entry.get("author", ""), candidate.get("authors", []) or [])
    y_score = year_score(entry.get("year"), candidate.get("year"))
    v_score = venue_score(
        entry.get("journal") or entry.get("booktitle") or entry.get("publisher") or "",
        candidate.get("venue") or "",
    )

    total = 0.55 * t_score + 0.30 * a_score + 0.10 * y_score + 0.05 * v_score
    return max(0.0, min(1.0, total)), {"title": t_score, "authors": a_score, "year": y_score, "venue": v_score, "doi_match": 0.0}
