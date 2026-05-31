import requests
import responses

from bibcheck.auto.autofix import _write_bib


def test_citekey_unchanged(tmp_path):
    entries = [{"ID": "Key1", "ENTRYTYPE": "article", "title": "A", "author": "B"}]
    out = tmp_path / "out.bib"
    _write_bib(entries, out)
    assert "Key1" in out.read_text(encoding="utf-8")


def test_autofix_no_network_skips(monkeypatch, tmp_path):
    from bibcheck.auto.autofix import run_autofix
    infile = tmp_path / "in.bib"
    infile.write_text("@article{K, title={A}, author={B}, year={2020}}\n", encoding="utf-8")
    out_bib = tmp_path / "out.bib"
    out_json = tmp_path / "r.json"
    out_csv = tmp_path / "r.csv"
    run_autofix(str(infile), str(out_bib), str(out_json), str(out_csv), allow_network=False)
    text = out_bib.read_text(encoding="utf-8")
    assert "K" in text


def test_conf_threshold_applied(monkeypatch, tmp_path):
    # patch resolve to force low confidence -> not applied
    from bibcheck.auto import autofix as af
    def fake_plan(entry, online_result, session, cache, min_conf, scope, allow_network, user_agent):
        return [], [{"citekey": entry["ID"], "field": "title", "old": entry.get("title"), "new": "NEW", "confidence": 0.5, "source": "mock"}]
    monkeypatch.setattr(af, "_plan_and_apply", fake_plan)
    infile = tmp_path / "in.bib"
    infile.write_text("@article{K, title={A}, author={B}, year={2020}}\n", encoding="utf-8")
    out_bib = tmp_path / "out.bib"
    out_json = tmp_path / "r.json"
    out_csv = tmp_path / "r.csv"
    af.run_autofix(str(infile), str(out_bib), str(out_json), str(out_csv), allow_network=False)
    text = out_bib.read_text(encoding="utf-8")
    assert "NEW" not in text


@responses.activate
def test_autofix_arxiv_resolver_parses_metadata():
    from bibcheck.auto.cache import HTTPCache
    from bibcheck.auto.resolvers.arxiv_resolver import resolve_arxiv

    responses.add(
        responses.GET,
        "https://export.arxiv.org/api/query",
        body=(
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom'>"
            "<entry>"
            "<id>http://arxiv.org/abs/1234.56789v2</id>"
            "<title>Test Paper</title>"
            "<author><name>Alice Smith</name></author>"
            "<published>2020-01-01T00:00:00Z</published>"
            "</entry>"
            "</feed>"
        ),
        status=200,
        match=[responses.matchers.query_param_matcher({"id_list": "1234.56789"})],
    )
    session = requests.Session()
    session.headers["User-Agent"] = "bibcheck-test"
    resolved = resolve_arxiv("https://arxiv.org/abs/1234.56789", session, HTTPCache(path=":memory:"), "bibcheck-test")
    assert resolved["title"] == "Test Paper"
    assert resolved["authors"] == ["Alice Smith"]
    assert resolved["year"] == "2020"
    assert resolved["doi"] == "10.48550/arxiv.1234.56789"
