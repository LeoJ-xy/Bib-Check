from rapidfuzz import fuzz
from ..core.normalize import norm_text


def title_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(norm_text(a), norm_text(b)) / 100.0

