import argparse
import os
import sys
import shutil
import time
from typing import List, Optional, Tuple, Dict

from .parser import load_bib_entries
from .report import ReportBuilder, write_csv_report, write_json_report, print_summary
from .validators_static import run_static_validations
from .validators_online import OnlineValidatorConfig, OnlineValidator
from .fixer import FixPlanner, FixConfig, FixApplier, ApplyConfig, write_changelog, write_fix_summary


class ProgressBar:
    def __init__(
        self,
        total: int,
        stream=sys.stderr,
        enabled: Optional[bool] = None,
    ) -> None:
        self.total = max(0, total)
        self.stream = stream
        self.start_time = time.time()
        if enabled is None:
            enabled = stream.isatty()
        self.enabled = enabled and self.total > 0

    def update(self, current: int) -> None:
        if not self.enabled:
            return
        current = min(current, self.total)
        percent = current / self.total if self.total else 1.0
        elapsed = time.time() - self.start_time
        rate = current / elapsed if elapsed > 0 else 0.0
        remaining = (self.total - current) / rate if rate > 0 else 0.0
        width = shutil.get_terminal_size((80, 20)).columns
        bar_width = max(10, min(40, width - 40))
        filled = int(bar_width * percent)
        bar = "=" * filled + "-" * (bar_width - filled)
        message = (
            f"\rProgress [{bar}] {current}/{self.total} "
            f"({percent:.0%}) {rate:.1f}/s ETA {remaining:.1f}s"
        )
        self.stream.write(message)
        self.stream.flush()

    def finish(self) -> None:
        if not self.enabled:
            return
        self.stream.write("\n")
        self.stream.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BibTeX reference authenticity and consistency checker (online by default)"
    )
    parser.add_argument("bibfile", help="Path to the .bib file to check")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run in explicit offline mode without contacting online data sources",
    )
    parser.add_argument(
        "--outdir",
        default="out",
        help="Report output directory; defaults to out",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=None,
        help="Check at most the first N entries for quick previews",
    )
    parser.add_argument(
        "--sources",
        default="crossref,openalex,s2",
        help="Comma-separated online sources for scholarly lookup",
    )
    parser.add_argument(
        "--enable-arxiv",
        action="store_true",
        default=True,
        help="Enable the arXiv API (enabled by default)",
    )
    parser.add_argument(
        "--disable-arxiv",
        action="store_false",
        dest="enable_arxiv",
        help="Disable the arXiv API",
    )
    parser.add_argument(
        "--enable-dblp",
        action="store_true",
        help="Enable DBLP for computer science entries (disabled by default)",
    )
    parser.add_argument(
        "--enable-citation-cff",
        action="store_true",
        default=True,
        help="Enable GitHub CITATION.cff lookup (enabled by default)",
    )
    parser.add_argument(
        "--disable-citation-cff",
        action="store_false",
        dest="enable_citation_cff",
        help="Disable GitHub CITATION.cff lookup",
    )
    parser.add_argument(
        "--high-conf",
        type=float,
        default=0.8,
        help="High-confidence gating threshold; defaults to 0.8",
    )
    parser.add_argument(
        "--mid-conf",
        type=float,
        default=0.6,
        help="Medium-confidence gating threshold; defaults to 0.6",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print more detailed diagnostic output",
    )
    parser.add_argument(
        "--progress",
        choices=["auto", "always", "never"],
        default="auto",
        help="Progress display mode: auto (TTY only and not verbose), always, or never",
    )
    parser.add_argument(
        "--user-agent",
        default="bibcheck/1.5",
        help="HTTP User-Agent; include contact information when appropriate",
    )
    # Online auto-fix options.
    parser.add_argument("--autofix", action="store_true", help="Enable online auto-correction and write a fixed BibTeX file plus change records")
    parser.add_argument("--no-network", action="store_true", help="Disable network access during autofix")
    parser.add_argument("--min-conf", type=float, default=0.85, help="Minimum confidence for automatic write-back; defaults to 0.85")
    parser.add_argument("--autofix-scope", choices=["high", "all"], default="high", help="Field scope for autofix")
    parser.add_argument("--latex-apostrophe", action="store_true", help="Convert right single quotation marks in author names to {\\textquoteright}")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Enable automatic fixes and write fixed.bib plus a change log; default is check-only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write only the change log without generating fixed.bib",
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="Overwrite the input .bib file after creating a .bak backup",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Also apply medium-confidence fixes; by default only high-confidence fixes are applied",
    )
    parser.add_argument(
        "--fixed-bib",
        default=None,
        help="Custom path for the fixed BibTeX output; defaults to out/<name>.fixed.bib",
    )
    parser.add_argument(
        "--changes-log",
        default=None,
        help="Path for the JSONL change log; defaults to out/changes.jsonl",
    )
    parser.add_argument(
        "--fix-summary",
        default=None,
        help="Path for the Markdown fix summary; defaults to out/fix_summary.md",
    )
    return parser


def parse_sources(src: str) -> List[str]:
    return [s.strip() for s in src.split(",") if s.strip()]


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)

    if not os.path.isfile(args.bibfile):
        print(f"BibTeX file not found: {args.bibfile}", file=sys.stderr)
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
            enable_arxiv=args.enable_arxiv,
            enable_dblp=args.enable_dblp,
            enable_citation_cff=args.enable_citation_cff,
            high_conf=args.high_conf,
            mid_conf=args.mid_conf,
        )
    )

    plans = {}
    if args.progress == "never":
        progress_enabled = False
    elif args.progress == "always":
        progress_enabled = True
    else:
        progress_enabled = None if not args.verbose else False
    progress = ProgressBar(len(entries), enabled=progress_enabled)
    for index, entry in enumerate(entries, start=1):
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
        progress.update(index)
    progress.finish()

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

    # Preserve exit code 1 while errors remain after fix planning.
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
