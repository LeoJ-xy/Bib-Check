import re
from typing import Optional


ARXIV_NEW_RE = re.compile(r"\b(\d{4}\.\d{4,5})(v\d+)?\b", flags=re.I)
ARXIV_OLD_RE = re.compile(r"\b([a-z\-]+/\d{7})(v\d+)?\b", flags=re.I)
ARXIV_URL_RE = re.compile(r"arxiv\.org/(abs|pdf)/([^?#\s]+)", flags=re.I)
GITHUB_REPO_RE = re.compile(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)", flags=re.I)


def get_field(entry: dict, name: str) -> Optional[str]:
    if name in entry:
        return entry.get(name)
    lower = name.lower()
    if lower in entry:
        return entry.get(lower)
    upper = name.upper()
    if upper in entry:
        return entry.get(upper)
    return None


def extract_arxiv_id(entry: dict) -> Optional[str]:
    eprint = get_field(entry, "eprint") or get_field(entry, "arxivid")
    if eprint:
        match = ARXIV_NEW_RE.search(eprint) or ARXIV_OLD_RE.search(eprint)
        if match:
            return match.group(0)
    url = get_field(entry, "url") or ""
    if url:
        m = ARXIV_URL_RE.search(url)
        if m:
            arxiv_id = m.group(2)
            return re.sub(r"\.pdf$", "", arxiv_id, flags=re.I)
    archive_prefix = get_field(entry, "archiveprefix") or get_field(entry, "archivePrefix")
    if archive_prefix and str(archive_prefix).lower() == "arxiv":
        if eprint:
            match = ARXIV_NEW_RE.search(eprint) or ARXIV_OLD_RE.search(eprint)
            if match:
                return match.group(0)
    return None


def extract_github_repo(entry: dict) -> Optional[str]:
    url = get_field(entry, "url") or ""
    howpublished = get_field(entry, "howpublished") or ""
    note = get_field(entry, "note") or ""
    for field in (url, howpublished, note):
        if not field:
            continue
        m = GITHUB_REPO_RE.search(field)
        if m:
            owner = m.group(1)
            repo = re.sub(r"\.git$", "", m.group(2))
            return f"{owner}/{repo}".lower()
    return None


def classify_entry(entry: dict) -> str:
    doi = get_field(entry, "doi")
    arxiv_id = extract_arxiv_id(entry)
    github_repo = extract_github_repo(entry)
    url = get_field(entry, "url")
    entry_type = (get_field(entry, "ENTRYTYPE") or "").lower()

    if doi:
        return "scholarly_doi"
    if arxiv_id:
        return "preprint_arxiv"
    if github_repo:
        return "software_github"
    if entry_type in {"misc", "online", "software", "manual"} and url:
        return "web_generic"
    if entry_type in {"inproceedings", "proceedings"} or get_field(entry, "booktitle"):
        return "scholarly_cslike"
    if get_field(entry, "journal") or get_field(entry, "booktitle"):
        return "scholarly_cslike"
    return "unknown"
