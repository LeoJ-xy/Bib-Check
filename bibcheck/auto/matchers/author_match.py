from ..core.normalize import norm_text


def author_score(local_author_field: str, online_authors: list) -> float:
    if not local_author_field or not online_authors:
        return 0.0
    local_first = norm_text(local_author_field.split(" and ")[0])
    online_first = norm_text(online_authors[0])
    return 1.0 if local_first == online_first else 0.0

