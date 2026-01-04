import argparse
import os
import sys
import shutil
from typing import List, Optional, Tuple, Dict

from .parser import load_bib_entries
from .report import ReportBuilder, write_csv_report, write_json_report, print_summary
from .validators_static import run_static_validations
from .validators_online import OnlineValidatorConfig, OnlineValidator
from .fixer import FixPlanner, FixConfig, FixApplier, ApplyConfig, write_changelog, write_fix_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BibTeX 引用真实性/一致性校验器（默认联网）"
    )
    parser.add_argument("bibfile", help="待校验的 .bib 文件路径")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="显式离线模式（不访问在线数据源）",
    )
    parser.add_argument(
        "--outdir",
        default="out",
        help="报告输出目录，默认 out",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=None,
        help="最多检查前 N 条，便于快速预览",
    )
    parser.add_argument(
        "--sources",
        default="crossref,openalex,s2",
        help="逗号分隔的在线数据源，默认全开",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出更详细的调试信息",
    )
    parser.add_argument(
        "--user-agent",
        default="bibcheck/0.1 (+https://example.com/contact)",
        help="HTTP User-Agent，建议带联系方式",
    )
    # auto-fix online (new, 仅新增不与已有重复)
    parser.add_argument("--autofix", action="store_true", help="启用自动联网矫正（生成 fixed bib 与 change 记录）")
    parser.add_argument("--no-network", action="store_true", help="禁止联网（autofix 时跳过在线解析）")
    parser.add_argument("--min-conf", type=float, default=0.85, help="自动写回的最小置信度阈值，默认 0.85")
    parser.add_argument("--autofix-scope", choices=["high", "all"], default="high", help="autofix 字段范围")
    parser.add_argument("--latex-apostrophe", action="store_true", help="将作者名中的 ’ 转为 {\\textquoteright}")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="启用自动修复（生成 fixed.bib 与 change log，默认仅检查）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅输出 change log，不生成 fixed.bib",
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="覆盖原 bib 文件（会先备份为 .bak）",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="中置信修复也自动应用（默认仅高置信）",
    )
    parser.add_argument(
        "--fixed-bib",
        default=None,
        help="自定义修复后 bib 输出路径，默认 out/<name>.fixed.bib",
    )
    parser.add_argument(
        "--changes-log",
        default=None,
        help="变更日志 jsonl 路径，默认 out/changes.jsonl",
    )
    parser.add_argument(
        "--fix-summary",
        default=None,
        help="修复汇总 markdown 路径，默认 out/fix_summary.md",
    )
    return parser


def parse_sources(src: str) -> List[str]:
    return [s.strip() for s in src.split(",") if s.strip()]


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)

    if not os.path.isfile(args.bibfile):
        print(f"找不到 bib 文件: {args.bibfile}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)

    if args.autofix:
        exit_code = run_autofix_cli(args)
    elif args.fix:
        exit_code = run_fix(args)
    else:
        exit_code = run_check(args)
    sys.exit(exit_code)


def run_check(args, planner: FixPlanner = None) -> int:
    entries, parse_issues = load_bib_entries(args.bibfile, args.max_entries)

    report_builder = ReportBuilder()
    for issue in parse_issues:
        report_builder.add_file_issue(issue)

    static_results = run_static_validations(entries)
    online_validator = OnlineValidator(
        OnlineValidatorConfig(
            offline=args.offline,
            sources=parse_sources(args.sources),
            verbose=args.verbose,
            user_agent=args.user_agent,
        )
    )

    plans = {}
    for entry in entries:
        issues = static_results.get(entry["ID"], [])
        online_result = online_validator.validate_entry(entry)
        fix_preview = None
        if planner:
            plan = planner.build_plan(entry, issues, online_result)
            plans[entry["ID"]] = plan
            fix_preview = plan.get("preview")
        entry_status = report_builder.collect_entry(entry, issues, online_result, fix_plan_preview=fix_preview)
        if args.verbose:
            print(f"[{entry['ID']}] status={entry_status} issues={len(issues)}")

    report_data = report_builder.build()

    json_path = os.path.join(args.outdir, "report.json")
    csv_path = os.path.join(args.outdir, "report.csv")
    write_json_report(report_data, json_path)
    write_csv_report(report_data, csv_path)
    print_summary(report_data)

    has_file_error = any(i["severity"] == "ERROR" for i in report_data.get("file_issues", []))
    exit_code = 1 if report_data["stats"]["error"] > 0 or has_file_error else 0
    return exit_code if not planner else (exit_code, entries, plans, report_data)


def run_fix(args) -> int:
    planner = FixPlanner(FixConfig(aggressive=args.aggressive))
    result = run_check(args, planner=planner)
    # result is (exit_code, entries, plans, report_data)
    if isinstance(result, int):
        # Should not happen, but guard
        return result
    exit_code, entries, plans, report_data = result

    applier = FixApplier(
        ApplyConfig(
            aggressive=args.aggressive,
            high_threshold=0.9,
            mid_threshold=0.8,
            dry_run=args.dry_run,
            inplace=args.inplace,
        )
    )
    new_entries, applied, suggested = applier.apply(entries, plans)

    base_name = os.path.splitext(os.path.basename(args.bibfile))[0]
    fixed_path = args.fixed_bib or os.path.join(args.outdir, f"{base_name}.fixed.bib")
    changes_path = args.changes_log or os.path.join(args.outdir, "changes.jsonl")
    summary_path = args.fix_summary or os.path.join(args.outdir, "fix_summary.md")

    target_path = fixed_path
    if not args.dry_run:
        if args.inplace:
            backup = args.bibfile + ".bak"
            shutil.copy2(args.bibfile, backup)
            target_path = args.bibfile
        applier.write_bib(new_entries, target_path)

    write_changelog(applied + suggested, changes_path)
    write_fix_summary(applied, suggested, summary_path, target_path if not args.dry_run else "dry-run", args.dry_run)

    # 如果修复后仍有 ERROR，保持退出码 1；否则 0
    has_file_error = any(i["severity"] == "ERROR" for i in report_data.get("file_issues", []))
    exit_code = 1 if report_data["stats"]["error"] > 0 or has_file_error else 0
    return exit_code


def run_autofix_cli(args) -> int:
    from .auto.autofix import run_autofix

    base_name = os.path.splitext(os.path.basename(args.bibfile))[0]
    fixed_path = args.fixed_bib or os.path.join(args.outdir, f"{base_name}.fixed.bib")
    json_path = os.path.join(args.outdir, "report.json")
    csv_path = os.path.join(args.outdir, "report.csv")

    os.makedirs(args.outdir, exist_ok=True)
    run_autofix(
        bibfile=args.bibfile,
        out_bib=fixed_path,
        out_report_json=json_path,
        out_report_csv=csv_path,
        min_conf=args.min_conf,
        scope=args.autofix_scope,
        allow_network=not args.no_network,
        user_agent=args.user_agent,
    )
    return 0

