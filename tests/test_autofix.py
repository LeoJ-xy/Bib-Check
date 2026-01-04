import os

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

