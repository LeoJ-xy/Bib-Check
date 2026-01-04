def confidence(title_score: float, author_score: float, venue_score: float, resolved_by_doi: bool = False) -> float:
    base = max(title_score or 0.0, author_score or 0.0, venue_score or 0.0)
    if resolved_by_doi:
        base = max(base, 0.95)
    return max(0.0, min(1.0, base))

