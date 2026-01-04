from bibcheck.fixer.planner import FixPlanner, FixConfig
from bibcheck.fixer.applier import FixApplier, ApplyConfig


def test_arxiv_doi_normalize():
    entry = {"ID": "k1", "ENTRYTYPE": "article", "title": "A", "author": "A", "year": "2020", "doi": "10.48550/ARXIV.1234.5678"}
    planner = FixPlanner(FixConfig())
    plan = planner.build_plan(entry, [], {"checked": False, "candidate_matches": []})
    doi_actions = [a for a in plan["actions"] if a["field"] == "doi"]
    assert doi_actions
    assert doi_actions[0]["new"] == "10.48550/arxiv.1234.5678"


def test_author_fix_applied_high_confidence():
    entry = {"ID": "k2", "ENTRYTYPE": "article", "title": "A", "author": "Foo", "year": "2020"}
    online = {
        "resolved": {
            "source": "crossref",
            "doi": "10.1/xyz",
            "title": "A",
            "year": "2020",
            "authors": ["Alice Smith", "Bob Lee"],
        },
        "title_match_score": 100,
        "candidate_matches": [],
    }
    planner = FixPlanner(FixConfig())
    plan = planner.build_plan(entry, [], online)
    applier = FixApplier(ApplyConfig())
    new_entries, applied, suggested = applier.apply([entry], {"k2": plan})
    assert any(c["field"] == "author" and c["applied"] for c in applied)
    assert new_entries[0]["author"].startswith("Smith")


def test_pages_normalize():
    entry = {"ID": "k3", "ENTRYTYPE": "article", "title": "A", "author": "A", "year": "2020", "pages": "p.123-130"}
    planner = FixPlanner(FixConfig())
    plan = planner.build_plan(entry, [], {"checked": False, "candidate_matches": []})
    page_actions = [a for a in plan["actions"] if a["field"] == "pages"]
    assert page_actions
    assert page_actions[0]["new"] == "123--130"


def test_aggressive_threshold():
    entry = {"ID": "k4", "ENTRYTYPE": "article", "title": "A", "author": "A", "year": "2020"}
    candidate = {"source": "crossref", "doi": "10.1/abc", "score": 85}
    planner = FixPlanner(FixConfig(aggressive=False))
    plan = planner.build_plan(entry, [], {"checked": True, "candidate_matches": [candidate]})
    applier = FixApplier(ApplyConfig(aggressive=False))
    _, applied, suggested = applier.apply([entry], {"k4": plan})
    assert not applied  # 未应用

    applier_aggr = FixApplier(ApplyConfig(aggressive=True))
    _, applied2, _ = applier_aggr.apply([entry], {"k4": plan})
    assert any(c["field"] == "doi" and c["applied"] for c in applied2)


