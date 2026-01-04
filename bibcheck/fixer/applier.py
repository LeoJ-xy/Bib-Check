import os
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Tuple

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter

from .formatters import normalize_doi_value


@dataclass
class ApplyConfig:
    aggressive: bool = False
    high_threshold: float = 0.9
    mid_threshold: float = 0.8
    dry_run: bool = False
    inplace: bool = False


class FixApplier:
    def __init__(self, config: ApplyConfig):
        self.config = config

    def apply(self, entries: List[dict], plans: Dict[str, Dict]) -> Tuple[List[dict], List[dict], List[dict]]:
        new_entries = deepcopy(entries)
        applied: List[dict] = []
        suggested: List[dict] = []

        entry_by_key = {e["ID"]: e for e in new_entries}
        for citekey, plan in plans.items():
            entry = entry_by_key.get(citekey)
            if not entry:
                continue
            for action in plan.get("actions", []):
                if self._should_apply(action["confidence"]):
                    # 处理需要删除的字段（如 arXiv 迁移时删除 journal/booktitle）
                    extra = action.get("extra") or {}
                    for rf in extra.get("remove_fields", []):
                        entry.pop(rf, None)
                    entry[action["field"]] = action["new"]
                    applied.append(self._make_change_record(action, applied=True))
                else:
                    suggested.append(self._make_change_record(action, applied=False))
        return new_entries, applied, suggested

    def _should_apply(self, confidence: float) -> bool:
        if confidence >= self.config.high_threshold:
            return True
        if self.config.aggressive and confidence >= self.config.mid_threshold:
            return True
        return False

    def _make_change_record(self, action: dict, applied: bool) -> dict:
        return {
            "timestamp": int(time.time()),
            "citekey": action["citekey"],
            "field": action["field"],
            "old": action.get("old"),
            "new": action.get("new"),
            "confidence": action.get("confidence"),
            "source": action.get("source"),
            "reason": action.get("reason"),
            "applied": applied,
        }

    def write_bib(self, entries: List[dict], path: str):
        cleaned_entries = [self._clean_entry(e) for e in entries]
        db = BibDatabase()
        db.entries = cleaned_entries
        writer = BibTexWriter()
        writer.order_entries_by = None
        with open(path, "w", encoding="utf-8") as f:
            f.write(writer.write(db))

    def _clean_entry(self, entry: dict) -> dict:
        """移除内部字段与非字符串值，避免写出失败。"""
        keep = {}
        for k, v in entry.items():
            if k.startswith("_"):
                continue
            if k in ("ID", "ENTRYTYPE"):
                keep[k] = v
                continue
            if v is None:
                continue
            if not isinstance(v, str):
                # 丢弃非字符串，避免 writer 抛错
                continue
            keep[k] = v
        return keep

