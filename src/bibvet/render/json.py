"""JSON report — machine-readable shape of all FileReports."""
from __future__ import annotations

import json

from bibvet.models import EntryReport, FileReport


def render_json(file_reports: list[FileReport], *, indent: int | None = 2) -> str:
    return json.dumps({"files": [_file(fr) for fr in file_reports]}, indent=indent)


def _file(fr: FileReport) -> dict:
    return {
        "path": str(fr.path),
        "entries": [_entry(er) for er in fr.entries],
    }


def _entry(er: EntryReport) -> dict:
    return {
        "citekey": er.entry.citekey,
        "entry_type": er.entry.entry_type,
        "source_file": str(er.entry.source_file),
        "source_line": er.entry.source_line,
        "status": er.status,
        "paper_url": er.paper_url,
        "canonical": _canonical(er.canonical) if er.canonical else None,
        "diffs": [
            {
                "field": d.field, "user_value": d.user_value,
                "canonical_value": d.canonical_value,
                "severity": d.severity, "rationale": d.rationale,
            }
            for d in er.diffs
        ],
        "notes": list(er.notes),
    }


def _canonical(c) -> dict:
    return {
        "source": c.source,
        "title": c.title,
        "authors": [{"family": a.family, "given": a.given} for a in c.authors],
        "year": c.year,
        "venue": c.venue,
        "doi": c.doi,
        "arxiv_id": c.arxiv_id,
        "entry_type_hint": c.entry_type_hint,
    }
