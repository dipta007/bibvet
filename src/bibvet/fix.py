"""Write the cleaned `<name>.fixed.bib` from a FileReport.

- verified, skipped → original entry text passed through
- fixable → re-emit with canonical field set (BibTeX required fields + DOI)
- cross_check_failed, unverified → original text + leading `% bibvet:` comment
"""
from __future__ import annotations

import re
from pathlib import Path

from bibvet.models import CanonicalRecord, EntryReport, FileReport, UserEntry

REQUIRED_FIELDS = {
    "article": ["author", "title", "journal", "year", "volume", "number", "pages", "doi"],
    "inproceedings": ["author", "title", "booktitle", "year", "pages", "doi"],
    "conference": ["author", "title", "booktitle", "year", "pages", "doi"],
    "incollection": ["author", "title", "booktitle", "publisher", "year", "pages", "doi"],
    "book": ["author", "title", "publisher", "year"],
    "phdthesis": ["author", "title", "school", "year"],
    "mastersthesis": ["author", "title", "school", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["author", "title", "year", "eprint", "archiveprefix", "doi"],
}


def write_fixed_bib(
    report: FileReport,
    out_path: Path,
    *,
    original_text: str,
    force: bool = False,
) -> None:
    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} already exists; pass force=True to overwrite")

    chunks: list[str] = []
    blocks = _split_into_blocks(original_text, [er.entry for er in report.entries])
    for er, block in zip(report.entries, blocks, strict=True):
        chunks.append(_render_entry(er, block))
    out_path.write_text("\n\n".join(chunks).strip() + "\n", encoding="utf-8")


def _render_entry(er: EntryReport, original_block: str) -> str:
    if er.status == "fixable" and er.canonical is not None:
        return _rewrite_with_canonical(er.entry, er.canonical)
    if er.status == "unverified":
        msg = "UNVERIFIED — no high-confidence match in any source; manual review required"
        return f"% bibvet: {msg}\n{original_block}"
    if er.status == "cross_check_failed":
        note = "; ".join(er.notes) if er.notes else "DOI and title-search disagree"
        return f"% bibvet: CROSS-CHECK FAILED — {note}; manual review required\n{original_block}"
    return original_block


def _rewrite_with_canonical(entry: UserEntry, canonical: CanonicalRecord) -> str:
    type_lc = entry.entry_type.lower()
    field_order = REQUIRED_FIELDS.get(type_lc, ["author", "title", "year", "doi"])

    values: dict[str, str] = {}
    if canonical.title:
        values["title"] = canonical.title
    if canonical.authors:
        values["author"] = " and ".join(
            f"{a.family}, {a.given}" if a.given else a.family
            for a in canonical.authors
        )
    if canonical.year:
        values["year"] = str(canonical.year)
    if canonical.venue:
        values["journal"] = canonical.venue
        values["booktitle"] = canonical.venue
    if canonical.doi:
        values["doi"] = canonical.doi
    if canonical.arxiv_id:
        values["eprint"] = canonical.arxiv_id
        values["archiveprefix"] = "arXiv"

    for k in field_order:
        if k not in values and k in entry.fields:
            values[k] = entry.fields[k]

    lines = [f"@{type_lc}{{{entry.citekey},"]
    for k in field_order:
        if v := values.get(k):
            lines.append(f"  {k} = {{{v}}},")
    lines.append("}")
    return "\n".join(lines)


_ENTRY_HEAD_RE = re.compile(r"@\w+\s*\{([^,]+),", re.MULTILINE)


def _split_into_blocks(text: str, entries: list[UserEntry]) -> list[str]:
    if not text or not entries:
        return ["" for _ in entries]

    positions: list[tuple[str, int]] = []
    for m in _ENTRY_HEAD_RE.finditer(text):
        positions.append((m.group(1).strip(), m.start()))

    by_citekey = {ck: pos for ck, pos in positions}
    sorted_starts = sorted(pos for _, pos in positions)
    blocks: list[str] = []
    for entry in entries:
        start = by_citekey.get(entry.citekey)
        if start is None:
            blocks.append(_stub_render(entry))
            continue
        next_starts = [s for s in sorted_starts if s > start]
        end = next_starts[0] if next_starts else len(text)
        blocks.append(text[start:end].rstrip())
    return blocks


def _stub_render(entry: UserEntry) -> str:
    lines = [f"@{entry.entry_type}{{{entry.citekey},"]
    for k, v in entry.fields.items():
        lines.append(f"  {k} = {{{v}}},")
    lines.append("}")
    return "\n".join(lines)
