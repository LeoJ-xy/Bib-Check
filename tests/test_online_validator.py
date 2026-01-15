import responses

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
        "http://export.arxiv.org/api/query",
        body=ARXIV_FEED,
        status=200,
        match=[responses.matchers.query_param_matcher({"id_list": "1234.56789"})],
    )
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=True, enable_citation_cff=False),
        cache=HTTPCache(path=":memory:"),
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
        "http://export.arxiv.org/api/query",
        body=ARXIV_EMPTY_FEED,
        status=200,
        match=[responses.matchers.query_param_matcher({"id_list": "1234.56789"})],
    )
    validator = OnlineValidator(
        OnlineValidatorConfig(sources=[], enable_arxiv=True, enable_citation_cff=False),
        cache=HTTPCache(path=":memory:"),
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
