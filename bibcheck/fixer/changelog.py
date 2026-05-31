import json
import os
from typing import List


def write_changelog(changes: List[dict], path: str):
    if not changes:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ch in changes:
            json.dump(ch, f, ensure_ascii=False)
            f.write("\n")


def write_fix_summary(applied: List[dict], suggested: List[dict], path: str, fixed_path: str, dry_run: bool):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append("# bibcheck Fix Summary")
    lines.append("")
    lines.append(f"- Applied fixes: {len([c for c in applied if c['applied']])}")
    lines.append(f"- Suggestions not applied automatically: {len([c for c in suggested if not c['applied']])}")
    lines.append(f"- Output file: {'none (dry-run)' if dry_run else fixed_path}")
    if applied:
        lines.append("\n## Applied")
        for c in applied:
            lines.append(f"- {c['citekey']} {c['field']}: {c.get('old')} -> {c.get('new')} (conf={c.get('confidence'):.2f}, src={c.get('source')})")
    if suggested:
        lines.append("\n## Suggestions (not applied automatically)")
        for c in suggested:
            lines.append(f"- {c['citekey']} {c['field']}: {c.get('old')} -> {c.get('new')} (conf={c.get('confidence'):.2f}, src={c.get('source')})")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
import json
import time
from typing import List, Dict


def write_changes_jsonl(changes: List[Dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for c in changes:
            payload = dict(c)
            payload.setdefault("timestamp", time.time())
            f.write(json.dumps(payload, ensure_ascii=False))
            f.write("\n")
