import re
from typing import Dict, List, Tuple

import bibtexparser
from bibtexparser.bparser import BibTexParser

Issue = Dict[str, object]
Entry = Dict[str, object]


def load_bib_entries(path: str, max_entries: int = None) -> Tuple[List[Entry], List[Issue]]:
    """解析 BibTeX 文件，返回条目与解析问题。"""
    parser = BibTexParser(common_strings=True)
    parser.customization = None
    parse_issues: List[Issue] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        parse_issues.append(
            {
                "type": "PARSE_ERROR",
                "severity": "ERROR",
                "message": f"无法读取文件: {exc}",
                "details": {"line": None},
            }
        )
        return [], parse_issues

    try:
        bib_db = bibtexparser.loads(content, parser=parser)
    except Exception as exc:  # bibtexparser 的异常信息里通常含有行号
        line_no = _extract_line_number(str(exc))
        ctx = _extract_context(content, line_no) if line_no else None
        parse_issues.append(
            {
                "type": "PARSE_ERROR",
                "severity": "ERROR",
                "message": f"BibTeX 解析失败: {exc}",
                "details": {"line": line_no, "context": ctx},
            }
        )
        return [], parse_issues

    entries = bib_db.entries
    if max_entries:
        entries = entries[:max_entries]
    return entries, parse_issues


def _extract_line_number(msg: str):
    m = re.search(r"line\s+(\d+)", msg)
    if m:
        return int(m.group(1))
    return None


def _extract_context(content: str, line_no: int, window: int = 2) -> str:
    lines = content.splitlines()
    idx = max(0, line_no - 1)
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    return "\n".join(f"{i+1}:{lines[i]}" for i in range(start, end))


