import os
import requests

from .cache import HTTPCache
from .matchers.title_match import title_score
from .matchers.author_match import author_score
from .matchers.venue_match import venue_score
from .core.confidence import confidence
from .core.normalize import norm_doi
from .resolvers.doi_resolver import resolve_doi
from .resolvers.arxiv_resolver import resolve_arxiv
from .resolvers.crossref_resolver import search_crossref
from .resolvers.semanticscholar_resolver import search_s2
from .resolvers.openalex_resolver import search_openalex
from ..parser import load_bib_entries
from ..cache import HTTPCache as LegacyCache
from ..report import ReportBuilder, write_json_report, write_csv_report
from ..validators_static import run_static_validations
from ..validators_online import OnlineValidator, OnlineValidatorConfig


def run_autofix(
    bibfile: str,
    out_bib: str,
    out_report_json: str,
    out_report_csv: str,
    min_conf: float = 0.85,
    scope: str = "high",
    allow_network: bool = True,
    user_agent: str = "bibcheck/auto-fix",
):
    entries, parse_issues = load_bib_entries(bibfile, max_entries=None)
    report_builder = ReportBuilder()
    for issue in parse_issues:
        report_builder.add_file_issue(issue)

    static_results = run_static_validations(entries)
    online_validator = OnlineValidator(
        OnlineValidatorConfig(
            offline=not allow_network,
            sources=["crossref", "openalex", "s2"],
            verbose=False,
            user_agent=user_agent,
        )
    )
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    cache = HTTPCache()

    for entry in entries:
        issues = static_results.get(entry["ID"], [])
        online_result = online_validator.validate_entry(entry)
        # corrections_suggested/applied
        suggested, applied = _plan_and_apply(entry, online_result, session, cache, min_conf, scope, allow_network, user_agent)
        # blog-aware autofix
        if scope in ("high", "all") and allow_network:
            from .blog_fixer import plan_blog_fix
            blog_suggested, blog_applied = plan_blog_fix(entry, session, cache, user_agent, min_conf, accessed_date=None)
            suggested.extend(blog_suggested)
            applied.extend(blog_applied)
        entry["_auto_patches"] = {"suggested": suggested, "applied": applied}
        report_builder.collect_entry(entry, issues, online_result, fix_plan_preview=suggested)

    report_data = report_builder.build()
    write_json_report(report_data, out_report_json)
    write_csv_report(report_data, out_report_csv)
    _write_bib(entries, out_bib)
    return report_data


def _plan_and_apply(entry, online_result, session, cache, min_conf, scope, allow_network, user_agent):
    suggested = []
    applied = []
    resolved = online_result.get("resolved")
    candidates = online_result.get("candidate_matches") or []
    target_fields = ["title", "author", "year", "doi", "url", "eprint", "journal", "howpublished"]
    if scope == "all":
        target_fields += ["booktitle", "volume", "number", "pages"]

    # 额外来源：直接解析 doi/arxiv/模糊检索
    if allow_network and not resolved:
        if entry.get("doi"):
            resolved = resolve_doi(entry.get("doi"), session, cache, user_agent)
        if not resolved and entry.get("eprint"):
            resolved = resolve_arxiv(entry.get("eprint"), session, cache, user_agent)
        if not resolved and entry.get("url"):
            if "arxiv.org" in entry.get("url", ""):
                resolved = resolve_arxiv(entry.get("url"), session, cache, user_agent)
        if not resolved:
            resolved = search_crossref(entry.get("title", ""), session, cache, user_agent) or \
                       search_s2(entry.get("title", ""), session, cache, user_agent) or \
                       search_openalex(entry.get("title", ""), session, cache, user_agent)

    if not resolved:
        return suggested, applied

    t = title_score(entry.get("title"), resolved.get("title"))
    a = author_score(entry.get("author", ""), resolved.get("authors", []))
    v = venue_score(entry.get("journal") or entry.get("booktitle") or "", resolved.get("venue", ""))
    conf = confidence(t, a, v, resolved_by_doi=bool(entry.get("doi") or resolved.get("doi")))

    for f in target_fields:
        new_val = resolved.get(f)
        if not new_val:
            continue
        patch = {
            "citekey": entry["ID"],
            "field": f,
            "old": entry.get(f),
            "new": new_val,
            "confidence": conf,
            "source": resolved.get("source", "online"),
        }
        suggested.append(patch)
        if conf >= min_conf:
            # 移动 arXiv journal -> howpublished
            if f == "journal" and "arxiv" in str(new_val).lower():
                entry.pop("journal", None)
                entry.pop("booktitle", None)
                entry["howpublished"] = "arXiv preprint"
                patch["field"] = "howpublished"
                patch["new"] = "arXiv preprint"
            else:
                entry[f] = new_val
            applied.append(patch)
    return suggested, applied


def _write_bib(entries, path: str):
    from bibtexparser.bibdatabase import BibDatabase
    from bibtexparser.bwriter import BibTexWriter

    db = BibDatabase()
    db.entries = []
    for e in entries:
        clean = {}
        for k, v in e.items():
            if k.startswith("_"):
                continue
            if k in ("ID", "ENTRYTYPE"):
                clean[k] = v
                continue
            if v is None:
                continue
            if not isinstance(v, str):
                continue
            clean[k] = v
        db.entries.append(clean)
    writer = BibTexWriter()
    writer.order_entries_by = None
    with open(path, "w", encoding="utf-8") as f:
        f.write(writer.write(db))

