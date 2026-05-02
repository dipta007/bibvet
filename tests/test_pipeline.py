from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bibvet.models import Author, CanonicalRecord, LookupKey, UserEntry
from bibvet.pipeline import Pipeline


@pytest.mark.asyncio
async def test_pipeline_runs_entry_through_all_stages(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{x, title = {Attention Is All You Need}, "
        "author = {Vaswani, Ashish}, year = {2017}, journal = {NeurIPS}, "
        "doi = {10.5555/3295222.3295349}}"
    )

    canonical = CanonicalRecord(
        source="crossref",
        matched_via=LookupKey(kind="doi", value="10.5555/3295222.3295349"),
        title="Attention Is All You Need",
        authors=(Author(family="Vaswani", given="Ashish"),),
        year=2017, venue="NeurIPS", doi="10.5555/3295222.3295349",
        arxiv_id=None, entry_type_hint="proceedings-article", raw={},
    )

    fake_source = AsyncMock()
    fake_source.name = "crossref"
    fake_source.supports = lambda key: key.kind == "doi"
    fake_source.fetch = AsyncMock(return_value=canonical)

    pipeline = Pipeline(sources=[fake_source])
    file_reports = await pipeline.run([bib])
    assert len(file_reports) == 1
    assert len(file_reports[0].entries) == 1
    assert file_reports[0].entries[0].status == "verified"


@pytest.mark.asyncio
async def test_pipeline_handles_multiple_files(tmp_path):
    a = tmp_path / "a.bib"
    a.write_text("@article{a, title = {T}, author = {X, Y}, year = {2020}, journal = {J}}")
    b = tmp_path / "b.bib"
    b.write_text("@article{b, title = {T2}, author = {X, Y}, year = {2021}, journal = {J}}")

    fake = AsyncMock()
    fake.name = "crossref"
    fake.supports = lambda key: True
    fake.fetch = AsyncMock(return_value=None)

    pipeline = Pipeline(sources=[fake])
    file_reports = await pipeline.run([a, b])
    assert {fr.path for fr in file_reports} == {a, b}


@pytest.mark.asyncio
async def test_per_entry_fetch_failure_marks_unverified(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{x, title = {T}, author = {X, Y}, year = {2020}, journal = {J}}")

    fake = AsyncMock()
    fake.name = "crossref"
    fake.supports = lambda key: True
    fake.fetch = AsyncMock(side_effect=RuntimeError("boom"))

    pipeline = Pipeline(sources=[fake])
    reports = await pipeline.run([bib])
    er = reports[0].entries[0]
    assert er.status == "unverified"
    assert any("fetch error" in n for n in er.notes)
