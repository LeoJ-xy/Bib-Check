import csv
import json
from collections import defaultdict
from typing import Dict, List


class ReportBuilder:
    def __init__(self):
        self.entries = []
        self.file_issues = []

    def add_file_issue(self, issue: dict):
        self.file_issues.append(issue)

    def collect_entry(self, entry: dict, issues: List[dict], online_data: dict, fix_plan_preview: List[dict] = None):
        # 去重同类问题，避免重复出现（如同一 citekey 多条目共享静态问题）
        combined = issues + entry.get("_online_issues", [])
        seen = set()
        all_issues = []
        for iss in combined:
            key = (iss.get("type"), iss.get("message"))
            if key in seen:
                continue
            seen.add(key)
            all_issues.append(iss)
        status = _status_from_issues(all_issues)
        record = {
            "citekey": entry["ID"],
            "entry_type": entry.get("ENTRYTYPE"),
            "fields_summary": {
                "title": entry.get("title"),
                "author": entry.get("author"),
                "year": entry.get("year"),
                "doi": entry.get("doi"),
                "url": entry.get("url"),
                "pages": entry.get("pages"),
                "venue": entry.get("journal") or entry.get("booktitle") or entry.get("publisher"),
            },
            "status": status,
            "issues": all_issues,
            "online": online_data,
            "fix_plan_preview": fix_plan_preview or [],
        }
        self.entries.append(record)
        return status

    def build(self) -> dict:
        stats = {
            "total": len(self.entries),
            "ok": 0,
            "warning": 0,
            "error": 0,
            "by_issue_type": defaultdict(int),
        }
        for e in self.entries:
            if e["status"] == "OK":
                stats["ok"] += 1
            elif e["status"] == "WARNING":
                stats["warning"] += 1
            else:
                stats["error"] += 1
            for iss in e["issues"]:
                stats["by_issue_type"][iss["type"]] += 1

        return {
            "entries": self.entries,
            "file_issues": self.file_issues,
            "stats": stats,
        }


def _status_from_issues(issues: List[dict]) -> str:
    severities = [i["severity"] for i in issues]
    if "ERROR" in severities:
        return "ERROR"
    if "WARNING" in severities:
        return "WARNING"
    return "OK"


def write_json_report(report: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=_default_serializer)


def write_csv_report(report: dict, path: str):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["citekey", "status", "issue_types", "issue_messages", "doi", "title", "year"])
        for e in report["entries"]:
            issue_types = ";".join(i["type"] for i in e["issues"])
            issue_messages = ";".join(i["message"] for i in e["issues"])
            fs = e["fields_summary"]
            writer.writerow([e["citekey"], e["status"], issue_types, issue_messages, fs["doi"], fs["title"], fs["year"]])


def print_summary(report: dict):
    stats = report["stats"]
    print("====== BibCheck 汇总 ======")
    print(f"总条目数: {stats['total']}")
    print(f"OK/WARNING/ERROR: {stats['ok']}/{stats['warning']}/{stats['error']}")
    if report["file_issues"]:
        print(f"文件级问题: {len(report['file_issues'])}")
        for iss in report["file_issues"]:
            print(f"  {iss['type']}: {iss['message']}")
    print("按错误类型计数:")
    for k, v in stats["by_issue_type"].items():
        print(f"  {k}: {v}")
    error_keys = [e["citekey"] for e in report["entries"] if e["status"] == "ERROR"]
    if error_keys:
        print("ERROR citekey 列表:")
        print(", ".join(error_keys))


def _default_serializer(obj):
    if isinstance(obj, defaultdict):
        return dict(obj)
    raise TypeError(f"Type not serializable: {type(obj)}")

