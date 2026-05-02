"""End-to-end CLI tests with mocked sources."""
from __future__ import annotations

from unittest.mock import patch

from bibvet.cli import main as cli_main
from bibvet.models import Author, CanonicalRecord, LookupKey


def _patch_pipeline(records_for: dict[str, CanonicalRecord | None]):
    """Patch Pipeline._run_entry to return synthetic reports based on entry citekey."""
    from bibvet import pipeline as pipeline_mod

    async def fake_run_entry(self, entry):
        from bibvet.compare import compare_entry
        rec = records_for.get(entry.citekey)
        records = [rec] if rec else []
        return compare_entry(entry, records)

    return patch.object(pipeline_mod.Pipeline, "_run_entry", fake_run_entry)


def _good_record():
    return CanonicalRecord(
        source="crossref", matched_via=LookupKey(kind="doi", value="x"),
        title="Attention Is All You Need",
        authors=(Author(family="Vaswani", given="Ashish"),),
        year=2017, venue="NeurIPS", doi="10.5555/3295222.3295349",
        arxiv_id=None, entry_type_hint="proceedings-article", raw={},
    )


GOOD_BIB = """\
@inproceedings{good, title = {Attention Is All You Need},
author = {Vaswani, Ashish}, year = {2017}, booktitle = {NeurIPS},
doi = {10.5555/3295222.3295349}}
"""

BAD_BIB = """\
@inproceedings{bad, title = {Attention Is All You Need},
author = {Vaswani, Ashish}, year = {2018}, booktitle = {NeurIPS}}
"""


def test_clean_bib_exits_0(tmp_path, capsys):
    bib = tmp_path / "refs.bib"
    bib.write_text(GOOD_BIB)
    with _patch_pipeline({"good": _good_record()}):
        rc = cli_main([str(bib)])
    assert rc == 0


def test_hallucinated_exits_2(tmp_path, capsys):
    bib = tmp_path / "refs.bib"
    bib.write_text(BAD_BIB)
    with _patch_pipeline({"bad": _good_record()}):
        rc = cli_main([str(bib)])
    assert rc == 2


def test_fix_writes_corrected_file(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(BAD_BIB)
    with _patch_pipeline({"bad": _good_record()}):
        cli_main([str(bib), "--fix"])
    fixed = tmp_path / "refs.fixed.bib"
    assert fixed.exists()
    assert "2017" in fixed.read_text()


def test_format_json(tmp_path, capsys):
    bib = tmp_path / "refs.bib"
    bib.write_text(GOOD_BIB)
    with _patch_pipeline({"good": _good_record()}):
        cli_main([str(bib), "--format", "json"])
    out = capsys.readouterr().out
    assert '"status"' in out


def test_directory_input_finds_bib_files(tmp_path):
    (tmp_path / "a.bib").write_text(GOOD_BIB.replace("good", "a"))
    (tmp_path / "b.bib").write_text(GOOD_BIB.replace("good", "b"))
    with _patch_pipeline({"a": _good_record(), "b": _good_record()}):
        rc = cli_main([str(tmp_path)])
    assert rc == 0


def test_recursive_finds_nested(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.bib").write_text(GOOD_BIB.replace("good", "nested"))
    with _patch_pipeline({"nested": _good_record()}):
        rc = cli_main([str(tmp_path), "--recursive"])
    assert rc == 0


def test_directory_without_bib_files_helpful_error(tmp_path, capsys):
    rc = cli_main([str(tmp_path)])
    assert rc != 0
    err = capsys.readouterr().err
    assert "no .bib files found" in err.lower()


def test_file_not_found(tmp_path, capsys):
    rc = cli_main([str(tmp_path / "nope.bib")])
    assert rc != 0
    err = capsys.readouterr().err
    assert "no such file" in err.lower()


def test_force_required_to_overwrite_fixed(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(BAD_BIB)
    fixed = tmp_path / "refs.fixed.bib"
    fixed.write_text("existing")
    with _patch_pipeline({"bad": _good_record()}):
        rc = cli_main([str(bib), "--fix"])
    assert rc != 0
    with _patch_pipeline({"bad": _good_record()}):
        rc = cli_main([str(bib), "--fix", "--force"])
    assert rc == 2
    assert "2017" in fixed.read_text()
