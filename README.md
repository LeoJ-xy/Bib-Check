# Bib-Check 1.5: BibTeX Reference Authenticity and Consistency Checker

## Overview

Bib-Check is a BibTeX validation and online correction tool for research and engineering workflows. By default it only checks files and does not modify them; fixed BibTeX files and change logs are written only when `--fix` or `--autofix` is explicitly enabled. Version 1.5 focuses on preventing temporary online-source failures from being misreported as missing papers, and improves handling for arXiv records, long author lists, venues, web pages, and dataset entries.

Core capabilities:

- Static validation: parse errors, duplicate citekeys, missing required fields, year/DOI/URL format checks, and page-range normalization.
- Online consistency checks: Crossref, OpenAlex, Semantic Scholar, arXiv, DBLP, and CITATION.cff; title, author, year, venue, and DOI alignment; confidence-gated candidate matching.
- Optional auto-fix: high-confidence DOI, author, title, year, venue, and page fixes; arXiv DOI normalization; page-range normalization.
- Optional blog-aware correction: detects research blogs and project pages, fetches web metadata or official BibTeX snippets, and can fill title, author, date, URL, `howpublished`, and `note`.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

- Check with online sources enabled by default: `python -m bibcheck sample.bib`
- Run explicitly offline: `python -m bibcheck sample.bib --offline`
- Generate traditional fix suggestions and a fixed file, mainly for high-confidence DOI and metadata fixes: `python -m bibcheck sample.bib --fix`
- Run online autofix with blog-aware support; changes at confidence `>=0.85` are written automatically and lower-confidence changes remain suggestions: `python -m bibcheck sample.bib --autofix --outdir out --min-conf 0.85 --autofix-scope high`
- Use `--dry-run` to preview changes only. Use `--no-network` to disable network access during autofix.

## Common Options

- `--outdir out`: report and artifact output directory.
- `--max-entries N`: check only the first N entries.
- `--sources crossref,openalex,s2`: online scholarly lookup sources.
- `--enable-arxiv` / `--disable-arxiv`: enable or disable the arXiv API; enabled by default.
- `--enable-dblp`: enable DBLP for computer science entries; disabled by default.
- `--enable-citation-cff` / `--disable-citation-cff`: enable or disable GitHub CITATION.cff lookup; enabled by default.
- `--high-conf` / `--mid-conf`: confidence gating thresholds; defaults are `0.8` and `0.6`.
- `--user-agent`: custom HTTP User-Agent.
- Fix options: `--fix`, `--dry-run`, `--inplace`, `--aggressive`.
- Autofix options: `--autofix`, `--no-network`, `--min-conf`, `--autofix-scope`, `--fixed-bib`, `--changes-log`, `--fix-summary`.
- `--latex-apostrophe`: convert right single quotation marks in author names to `{\\textquoteright}`.

Exit code: Bib-Check returns `1` when ERROR-level issues remain, and `0` otherwise. This makes it suitable for CI checks.

## Outputs

- `out/report.json`: structured report.
- `out/report.csv`: summary rows with citekey, status, issues, DOI, title, and year.
- Terminal summary: total entries, OK/WARNING/ERROR counts, issue counts by type, and ERROR citekeys.
- Additional Fix/Autofix outputs:
  - `out/<name>.fixed.bib`, or the original file when `--inplace` is used.
  - `out/changes.jsonl`: change log with citekey, field, old/new values, source, confidence, and timestamp.
  - `out/fix_summary.md`: Markdown fix summary.

## Main Issue Types

- Static: `PARSE_ERROR`, `DUPLICATE_CITEKEY`, `MISSING_REQUIRED_FIELDS`, `BAD_YEAR`, `BAD_DOI_FORMAT`, `BAD_URL_FORMAT`, `SUSPICIOUS_METADATA`.
- Online: `DOI_NOT_FOUND`, `TITLE_MISMATCH`, `YEAR_MISMATCH`, `AUTHOR_MISMATCH`, `VENUE_MISMATCH`, `CANDIDATE_FOUND_NO_DOI`, `NOT_FOUND_ONLINE`.
- arXiv, software, and confidence gating: `NOT_FOUND_ON_ARXIV`, `CITATION_CFF_MISSING`, `AMBIGUOUS_MATCH`, `LOW_CONFIDENCE_CANDIDATE`.
- Blog-aware: `WEB_CITATION_NEEDS_URLDATE`, `WEB_TITLE_MISMATCH`, `WEB_AUTHOR_MISMATCH`, `WEB_DATE_MISMATCH`, `WEB_CITATION_HAS_FAKE_DOI`, `WEB_BIBTEX_AVAILABLE`.

## Typical Workflow

1. Export a `.bib` file from Overleaf, Zotero, or another reference manager.
2. Run `python -m bibcheck your.bib` and inspect the report.
3. Fix clear problems manually or in the reference manager.
4. Use `python -m bibcheck your.bib --fix` when you want high-confidence DOI or metadata fixes.
5. Use `python -m bibcheck your.bib --autofix --min-conf 0.85` for research blogs, project pages, and online metadata alignment.
6. arXiv preprints are checked with the arXiv API, GitHub software entries can use CITATION.cff, and DBLP can be enabled as an optional fallback for computer science entries.

## Development and Tests

```bash
pytest
```

All online requests in the test suite are mocked with `responses`; tests do not require real network access.

## Example

`sample.bib` includes:

- Correct DOI entries.
- A formally published entry that also includes an arXiv copy.
- arXiv preprint entries.
- A research blog entry.
- A GitHub-hosted report URL that should not be treated as a software repository root.
- A deliberately faulty entry with invalid year, DOI, URL, and pages.

Example commands:

```bash
python -m bibcheck sample.bib
python -m bibcheck sample.bib --autofix --outdir out --min-conf 0.85
```
