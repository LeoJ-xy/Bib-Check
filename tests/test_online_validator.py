import requests
import responses

from bibcheck.kind import classify_entry, extract_arxiv_id, extract_github_repo
from bibcheck.cache import HTTPCache
from bibcheck.validators_online import OnlineValidator, OnlineValidatorConfig


ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1234.56789v2</id>
    <title>Test Paper</title>
    <author><name>Alice Smith</name></author>
    <published>2020-01-01T00:00:00Z</published>
    <updated>2020-01-02T00:00:00Z</updated>
    <arxiv:doi>10.48550/arxiv.1234.56789</arxiv:doi>
  </entry>
</feed>
"""


ARXIV_EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""


@responses.activate
def test_arxiv_match_and_compare():
    responses.add(
        responses.GET,
        "https://export.arxiv.org/api/query",
        body=ARXIV_FEED,
        status=200,
        match=[responses.matchers.query_param_matcher({"id_list": "1234.56789"})],
    )
    cache = HTTPCache(path=":memory:")
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=True, enable_citation_cff=False),
        cache=cache,
    )
    entry = {
        "ID": "k1",
        "ENTRYTYPE": "misc",
        "title": "Test Paper",
        "author": "Alice Smith",
        "year": "2019",
        "eprint": "1234.56789",
    }
    online = validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert online["resolved"]["source"] == "arxiv"
    assert "NOT_FOUND_ON_ARXIV" not in issue_types
    assert "YEAR_MISMATCH" in issue_types


@responses.activate
def test_arxiv_not_found():
    responses.add(
        responses.GET,
        "https://export.arxiv.org/api/query",
        body=ARXIV_EMPTY_FEED,
        status=200,
        match=[responses.matchers.query_param_matcher({"id_list": "1234.56789"})],
    )
    cache = HTTPCache(path=":memory:")
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=True, enable_citation_cff=False),
        cache=cache,
    )
    entry = {
        "ID": "k2",
        "ENTRYTYPE": "misc",
        "title": "Missing Paper",
        "author": "Bob Lee",
        "year": "2020",
        "eprint": "1234.56789",
    }
    validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert "NOT_FOUND_ON_ARXIV" in issue_types


@responses.activate
def test_arxiv_transport_error_is_not_reported_as_not_found():
    for _ in range(3):
        responses.add(
            responses.GET,
            "https://export.arxiv.org/api/query",
            body=requests.ConnectionError("dns failed"),
            match=[responses.matchers.query_param_matcher({"id_list": "1234.56789"})],
        )
    cache = HTTPCache(path=":memory:")
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=True, enable_citation_cff=False),
        cache=cache,
    )
    entry = {
        "ID": "k2b",
        "ENTRYTYPE": "misc",
        "title": "Known Paper",
        "author": "Bob Lee",
        "year": "2020",
        "eprint": "1234.56789",
    }
    validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert "ARXIV_SOURCE_UNAVAILABLE" in issue_types
    assert "NOT_FOUND_ON_ARXIV" not in issue_types
    assert cache.get("arxiv:id:1234.56789") is None


@responses.activate
def test_doi_transport_error_is_not_reported_as_missing_doi():
    doi = "10.1234/example"
    for _ in range(3):
        responses.add(
            responses.GET,
            f"https://api.crossref.org/works/{doi}",
            body=requests.ConnectionError("network down"),
        )
    cache = HTTPCache(path=":memory:")
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=["crossref"], enable_arxiv=False, enable_citation_cff=False),
        cache=cache,
    )
    entry = {
        "ID": "k2c",
        "ENTRYTYPE": "article",
        "title": "Known DOI Paper",
        "author": "Alice Smith",
        "year": "2020",
        "doi": doi,
    }
    validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert "ONLINE_SOURCE_UNAVAILABLE" in issue_types
    assert "DOI_NOT_FOUND" not in issue_types
    assert cache.get(f"crossref:doi:{doi}") is None


@responses.activate
def test_search_transport_error_is_not_reported_as_not_found_online():
    for _ in range(3):
        responses.add(
            responses.GET,
            "https://api.crossref.org/works",
            body=requests.ConnectionError("network down"),
            match=[
                responses.matchers.query_param_matcher(
                    {"query.bibliographic": "cats on mat", "rows": "5", "filter": "from-pub-date:2020,until-pub-date:2020"}
                )
            ],
        )
    cache = HTTPCache(path=":memory:")
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=["crossref"], enable_arxiv=False, enable_citation_cff=False),
        cache=cache,
    )
    entry = {
        "ID": "k2d",
        "ENTRYTYPE": "inproceedings",
        "title": "Cats on Mat",
        "author": "Alice Smith",
        "year": "2020",
        "booktitle": "Proc. TestConf",
    }
    validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert "ONLINE_SOURCE_UNAVAILABLE" in issue_types
    assert "NOT_FOUND_ONLINE" not in issue_types
    assert cache.get("crossref:search:cats on mat:2020:Alice Smith") is None


@responses.activate
def test_dblp_low_confidence_gating():
    responses.add(
        responses.GET,
        "https://dblp.org/search/publ/api",
        json={
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Completely Different Paper",
                                "authors": {"author": [{"text": "Someone Else"}]},
                                "year": "2018",
                                "venue": "TestConf",
                                "url": "https://dblp.org/rec/conf/test/xyz",
                            }
                        }
                    ]
                }
            }
        },
        status=200,
        match=[responses.matchers.query_param_matcher({"q": "cats on mat 2020 Alice Smith", "format": "json"})],
    )
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_dblp=True, enable_arxiv=False, enable_citation_cff=False),
        cache=HTTPCache(path=":memory:"),
    )
    entry = {
        "ID": "k3",
        "ENTRYTYPE": "inproceedings",
        "title": "Cats on Mat",
        "author": "Alice Smith",
        "year": "2020",
        "booktitle": "Proc. TestConf",
    }
    validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert "LOW_CONFIDENCE_CANDIDATE" in issue_types
    assert "TITLE_MISMATCH" not in issue_types


@responses.activate
def test_citation_cff_fallback_and_parse():
    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/owner/repo/main/CITATION.cff",
        status=404,
    )
    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/owner/repo/master/CITATION.cff",
        body=(
            "title: My Tool\n"
            "doi: 10.1234/zenodo.1234\n"
            "version: 1.0\n"
            "date-released: 2021-03-01\n"
            "authors:\n"
            "  - family-names: Smith\n"
            "    given-names: Alice\n"
        ),
        status=200,
    )
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=False, enable_citation_cff=True),
        cache=HTTPCache(path=":memory:"),
    )
    entry = {
        "ID": "k4",
        "ENTRYTYPE": "misc",
        "title": "My Tool",
        "author": "Alice Smith",
        "url": "https://github.com/owner/repo",
    }
    online = validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert online["resolved"]["source"] == "citation_cff"
    assert "CITATION_CFF_MISSING" not in issue_types


@responses.activate
def test_citation_cff_missing():
    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/owner/repo/main/CITATION.cff",
        status=404,
    )
    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/owner/repo/master/CITATION.cff",
        status=404,
    )
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=False, enable_citation_cff=True),
        cache=HTTPCache(path=":memory:"),
    )
    entry = {
        "ID": "k5",
        "ENTRYTYPE": "misc",
        "title": "My Tool",
        "author": "Alice Smith",
        "url": "https://github.com/owner/repo",
    }
    validator.validate_entry(entry)
    issue_types = {i["type"] for i in entry.get("_online_issues", [])}
    assert "CITATION_CFF_MISSING" in issue_types


def test_confidence_gating_levels():
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=False, enable_citation_cff=False),
        cache=HTTPCache(path=":memory:"),
    )
    entry = {
        "ID": "k6",
        "ENTRYTYPE": "article",
        "title": "Cats on Mat",
        "author": "Alice Smith and Bob Lee",
        "year": "2020",
    }
    high_candidate = {
        "source": "mock",
        "title": "Cats on Mat",
        "authors": ["Alice Smith", "Bob Lee"],
        "year": "2020",
    }
    mid_candidate = {
        "source": "mock",
        "title": "Cats on Mat",
        "authors": ["Charlie Brown"],
        "year": "2020",
    }
    low_candidate = {
        "source": "mock",
        "title": "Completely Different",
        "authors": ["Someone Else"],
        "year": "2010",
    }

    resolved, _, issues = validator._apply_confidence_gating(entry, [high_candidate], "unknown")
    assert resolved is not None
    assert not any(i["type"] in {"AMBIGUOUS_MATCH", "LOW_CONFIDENCE_CANDIDATE"} for i in issues)

    resolved_mid, _, issues_mid = validator._apply_confidence_gating(entry, [mid_candidate], "unknown")
    assert resolved_mid is None
    assert any(i["type"] == "AMBIGUOUS_MATCH" for i in issues_mid)

    resolved_low, _, issues_low = validator._apply_confidence_gating(entry, [low_candidate], "unknown")
    assert resolved_low is None
    assert any(i["type"] == "LOW_CONFIDENCE_CANDIDATE" for i in issues_low)


def test_extract_arxiv_old_style_id_with_dotted_archive():
    entry = {"eprint": "math.AG/0601001v2", "archivePrefix": "arXiv"}
    assert extract_arxiv_id(entry) == "math.AG/0601001v2"


def test_formal_entry_with_arxiv_copy_is_not_classified_as_preprint():
    entry = {
        "ENTRYTYPE": "article",
        "title": "Published Paper",
        "journal": "Journal of Tests",
        "url": "https://arxiv.org/abs/2401.12345",
    }
    assert classify_entry(entry) == "scholarly_cslike"


def test_nested_github_url_is_not_treated_as_software_repo():
    entry = {
        "ENTRYTYPE": "misc",
        "title": "Dataset Report",
        "url": "https://github.com/owner/repo/blob/main/report.pdf",
    }
    assert extract_github_repo(entry) is None


def test_invalid_doi_skips_online_lookup():
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=["crossref"], enable_arxiv=False, enable_citation_cff=False),
        cache=HTTPCache(path=":memory:"),
    )
    entry = {
        "ID": "bad",
        "ENTRYTYPE": "article",
        "title": "Bad DOI",
        "author": "Alice Smith",
        "year": "2020",
        "doi": "bad_doi/xyz",
    }
    online = validator.validate_entry(entry)
    assert online["checked"] is True
    assert entry.get("_online_issues") is None
