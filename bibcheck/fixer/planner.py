import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..normalize import normalize_title, normalize_doi
from ..validators_online import _surname  # reuse surname helper
from .confidence import confidence_from_resolved, confidence_from_candidate
from .formatters import normalize_pages, format_authors_list, normalize_doi_value


@dataclass
class FixConfig:
    aggressive: bool = False
    high_threshold: float = 0.9
    mid_threshold: float = 0.8


class FixPlanner:
    def __init__(self, config: FixConfig):
        self.config = config

    def build_plan(self, entry: dict, issues: List[dict], online_data: dict) -> Dict:
        actions: List[dict] = []
        resolved = online_data.get("resolved")
        title_score = online_data.get("title_match_score")

        # arXiv DOI 规范化（优先处理）
        arxiv_action = self._plan_arxiv_doi(entry)
        if arxiv_action:
            actions.append(arxiv_action)

        # 检查当前 journal 是否为 arXiv，若是则生成迁移到 howpublished 的 action
        arxiv_venue_action = self._plan_arxiv_venue_migration(entry)
        if arxiv_venue_action:
            actions.append(arxiv_venue_action)

        if resolved:
            actions.extend(self._plan_from_resolved(entry, resolved, title_score))
        else:
            actions.extend(self._plan_from_candidates(entry, online_data.get("candidate_matches", [])))

        # pages 规范化（若未从在线覆盖）
        if not any(a["field"] == "pages" for a in actions):
            normalized_pages = normalize_pages(entry.get("pages"))
            if normalized_pages and normalized_pages != entry.get("pages"):
                actions.append(
                    self._make_action(
                        entry,
                        field="pages",
                        new=normalized_pages,
                        confidence=0.85,
                        source="local_normalize",
                        reason="规范化 pages 为双短横/去前缀",
                    )
                )

        preview = [
            f"{a['field']}: {a.get('old')} -> {a.get('new')} (conf={a['confidence']:.2f}, src={a['source']})"
            for a in actions
        ]
        return {"citekey": entry["ID"], "actions": actions, "preview": preview}

    def _plan_arxiv_doi(self, entry: dict) -> Optional[dict]:
        """arXiv DOI 统一小写；若无 DOI 但有 eprint/url 含 arXiv id 则补全。"""
        doi = entry.get("doi")
        eprint = entry.get("eprint") or entry.get("arxivid")
        url = entry.get("url", "") or ""
        arxiv_id = None

        if doi and re.match(r"10\.48550/ARXIV\.", doi, flags=re.I):
            suffix = re.sub(r"^10\.48550/ARXIV\.", "", doi, flags=re.I)
            arxiv_id = suffix
            new_doi = f"10.48550/arxiv.{suffix}".lower().strip()
            if new_doi != doi:
                return self._make_action(entry, "doi", new=new_doi, confidence=0.95, source="normalize", reason="arXiv DOI 统一小写")

        if not doi:
            if eprint:
                arxiv_id = eprint
            elif "arxiv.org" in url:
                m = re.search(r"arxiv\.org/(abs|pdf)/([\w\.\-]+)", url)
                if m:
                    arxiv_id = m.group(2)
            if arxiv_id:
                new_doi = f"10.48550/arxiv.{arxiv_id}".lower()
                return self._make_action(entry, "doi", new=new_doi, confidence=0.9, source="arxiv", reason="从 eprint/url 推断 arXiv DOI")
        return None

    def _plan_arxiv_venue_migration(self, entry: dict) -> Optional[dict]:
        """若当前 journal/booktitle 含 arxiv，则迁移到 howpublished 并标记删除原字段。"""
        journal = entry.get("journal") or ""
        booktitle = entry.get("booktitle") or ""
        current_venue = journal or booktitle
        if current_venue and "arxiv" in current_venue.lower():
            # 生成迁移 action：写入 howpublished，并标记需要清理 journal/booktitle
            return self._make_action(
                entry,
                field="howpublished",
                new=f"arXiv preprint",
                confidence=0.95,
                source="normalize",
                reason="arXiv 条目迁移 venue 到 howpublished",
                extra={"remove_fields": ["journal", "booktitle"]},
            )
        return None

    def _plan_from_resolved(self, entry: dict, resolved: dict, title_score: int) -> List[dict]:
        actions = []
        conf = confidence_from_resolved(
            title_score=title_score,
            resolved_from_doi=bool(resolved.get("doi")),
            author_match=_authors_loose_match(entry.get("author", ""), resolved.get("authors", [])),
        )

        # DOI
        if resolved.get("doi"):
            doi_new = normalize_doi_value(resolved["doi"])
            if doi_new and doi_new != normalize_doi_value(entry.get("doi")):
                actions.append(self._make_action(entry, "doi", new=doi_new, confidence=conf, source=resolved.get("source", "online"), reason="权威源 DOI"))

        # Title
        if resolved.get("title"):
            if normalize_title(resolved["title"]) and normalize_title(resolved["title"]) != normalize_title(entry.get("title", "")):
                actions.append(self._make_action(entry, "title", new=resolved["title"], confidence=conf, source=resolved.get("source", "online"), reason="同步权威标题"))

        # Author
        if resolved.get("authors"):
            formatted_authors = format_authors_list(resolved["authors"])
            if formatted_authors and normalize_title(entry.get("author", "")) != normalize_title(formatted_authors):
                actions.append(self._make_action(entry, "author", new=formatted_authors, confidence=conf, source=resolved.get("source", "online"), reason="同步权威作者"))

        # Year
        if resolved.get("year"):
            if resolved["year"] != entry.get("year"):
                actions.append(self._make_action(entry, "year", new=str(resolved["year"]), confidence=conf, source=resolved.get("source", "online"), reason="同步权威年份"))

        # Venue
        venue = resolved.get("venue")
        if venue:
            current_venue = entry.get("journal") or entry.get("booktitle") or entry.get("publisher")
            if venue != current_venue:
                # arXiv 场景：更稳妥放在 howpublished，而非 journal；已有 journal 为 arXiv 也迁移到 howpublished
                is_arxiv = "arxiv" in venue.lower() or (current_venue and "arxiv" in current_venue.lower())
                if is_arxiv:
                    field = "howpublished"
                    new_venue = "arXiv preprint"
                    extra = {"remove_fields": ["journal", "booktitle"]}
                else:
                    field = "journal" if entry.get("journal") else ("booktitle" if entry.get("booktitle") else "journal")
                    new_venue = venue
                    extra = None
                actions.append(self._make_action(entry, field, new=new_venue, confidence=conf, source=resolved.get("source", "online"), reason="同步 venue", extra=extra))

        # Volume/Number/Pages
        for f in ["volume", "number", "pages"]:
            if resolved.get(f):
                new_val = resolved[f]
                if f == "pages":
                    new_val = normalize_pages(new_val)
                if new_val and new_val != entry.get(f):
                    actions.append(self._make_action(entry, f, new=new_val, confidence=conf, source=resolved.get("source", "online"), reason=f"补全 {f}"))
        return actions

    def _plan_from_candidates(self, entry: dict, candidates: List[dict]) -> List[dict]:
        actions = []
        if not candidates:
            return actions
        best = max(candidates, key=lambda m: m.get("score", 0))
        score = best.get("score", 0)
        conf = confidence_from_candidate(score)
        if best.get("doi") and conf >= self.config.mid_threshold:
            doi_new = normalize_doi_value(best["doi"])
            if doi_new and doi_new != normalize_doi_value(entry.get("doi")):
                actions.append(self._make_action(entry, "doi", new=doi_new, confidence=conf, source=best.get("source", "candidate"), reason="高置信候选 DOI"))
        return actions

    def _make_action(self, entry: dict, field: str, new, confidence: float, source: str, reason: str, extra: dict = None) -> dict:
        action = {
            "citekey": entry["ID"],
            "field": field,
            "old": entry.get(field),
            "new": new,
            "confidence": confidence,
            "source": source,
            "reason": reason,
        }
        if extra:
            action["extra"] = extra
        return action


def _authors_loose_match(local_author_field: str, online_authors: List[str]) -> bool:
    if not local_author_field or not online_authors:
        return True
    local_first = _surname(local_author_field.split(" and ")[0])
    online_first = _surname(online_authors[0])
    return local_first.lower() == online_first.lower()
