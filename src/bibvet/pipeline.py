"""Orchestrate parse → resolve → fetch → compare across all input files.

Bounded concurrency at the entry level: max 5 entries in flight across all sources.
A failure for one entry doesn't kill the run.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path

from bibvet.compare import compare_entry
from bibvet.models import (
    CanonicalRecord,
    EntryReport,
    FileReport,
    UserEntry,
)
from bibvet.parser import parse_bib_file
from bibvet.resolve import resolve_lookup_keys
from bibvet.sources.base import Source

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 5


class Pipeline:
    def __init__(
        self,
        sources: list[Source],
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        lenient: bool = False,
        strict: bool = False,
    ):
        self._sources = sources
        self._sem = asyncio.Semaphore(concurrency)
        self._lenient = lenient
        self._strict = strict

    async def run(self, paths: list[Path]) -> list[FileReport]:
        return await asyncio.gather(*(self._run_file(p) for p in paths))

    async def _run_file(self, path: Path) -> FileReport:
        entries = parse_bib_file(path, lenient=self._lenient)
        reports = await asyncio.gather(*(self._run_entry(e) for e in entries))
        return FileReport(path=path, entries=tuple(reports))

    async def _run_entry(self, entry: UserEntry) -> EntryReport:
        async with self._sem:
            keys = resolve_lookup_keys(entry)
            records: list[CanonicalRecord] = []
            errors: list[str] = []
            for key in keys:
                for source in self._sources:
                    if not source.supports(key):
                        continue
                    try:
                        rec = await source.fetch(key)
                    except Exception as e:
                        errors.append(f"fetch error from {source.name}: {e}")
                        logger.warning("fetch error %s/%s: %s", source.name, key.value, e)
                        continue
                    if rec is not None:
                        records.append(rec)

        report = compare_entry(entry, records, strict=self._strict)
        if errors and not records:
            report = replace(
                report,
                status="unverified",
                notes=tuple(report.notes) + tuple(errors),
            )
        return report
