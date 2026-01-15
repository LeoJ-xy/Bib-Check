def confidence_from_resolved(title_score: int = None, resolved_from_doi: bool = False, author_match: bool = True) -> float:
    """根据标题相似度、是否 DOI 解析、作者是否匹配估计置信度 0-1。"""
    score = 0.0
    if resolved_from_doi:
        score = 1.0
    if title_score is not None:
        score = max(score, title_score / 100.0)
    if not author_match and not resolved_from_doi:
        score = min(score, 0.7)
    return min(1.0, max(score, 0.0))


def confidence_from_candidate(title_score: int) -> float:
    if title_score is None:
        return 0.0
    return max(0.0, min(1.0, title_score / 100.0))
from dataclasses import dataclass


@dataclass
class ConfidenceResult:
    score: float
    level: str  # high / medium / low
    reason: str


def classify_confidence(title_score: int, doi_match: bool, author_match: bool) -> ConfidenceResult:
    """
    根据标题相似度、DOI 是否匹配、作者是否匹配给出置信度。
    """
    if doi_match:
        return ConfidenceResult(1.0, "high", "doi_match")
    score = (title_score or 0) / 100.0
    if score >= 0.9 and author_match:
        return ConfidenceResult(score, "high", "title>=0.9_and_author")
    if score >= 0.8:
        return ConfidenceResult(score, "medium", "title>=0.8")
    return ConfidenceResult(score, "low", "title<0.8")
