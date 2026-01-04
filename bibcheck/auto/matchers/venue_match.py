from ..core.normalize import norm_text


def venue_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    na, nb = norm_text(a), norm_text(b)
    if na in nb or nb in na:
        return 1.0
    return 0.0

