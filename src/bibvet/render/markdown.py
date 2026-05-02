"""Markdown report — same data as terminal, written to a file."""
from __future__ import annotations

from collections import Counter

from bibvet.models import EntryReport, FileReport
from bibvet.normalize import normalize_doi

STATUS_ORDER = ["fixable", "cross_check_failed", "unverified", "verified", "skipped"]


def render_markdown(file_reports: list[FileReport]) -> str:
    lines: list[str] = ["# bibvet report", ""]
    grand_total: Counter[str] = Counter()
    for fr in file_reports:
        statuses = Counter(er.status for er in fr.entries)
        grand_total.update(statuses)
        lines.append(f"## {fr.path}")
        lines.append("")
        lines.append(_summary_line(len(fr.entries), statuses))
        lines.append("")
        for status in STATUS_ORDER:
            grouped = [er for er in fr.entries if er.status == status]
            if not grouped:
                continue
            if status in ("verified", "skipped"):
                continue
            lines.append(f"### {status.replace('_', ' ').title()} ({len(grouped)})")
            lines.append("")
            for er in grouped:
                lines.append(_entry_block(er))
            lines.append("")

    if len(file_reports) > 1:
        total_n = sum(len(fr.entries) for fr in file_reports)
        lines.append("---")
        lines.append(f"**Total:** {_summary_line(total_n, grand_total)}")
    return "\n".join(lines)


def _summary_line(n: int, statuses: Counter) -> str:
    bits = [f"{n} entries"]
    for status in STATUS_ORDER:
        c = statuses.get(status)
        if c:
            bits.append(f"{c} {status}")
    return " · ".join(bits)


def _entry_block(er: EntryReport) -> str:
    out = [f"- **`{er.entry.citekey}`** (`{er.entry.source_file}:{er.entry.source_line}`)"]
    if er.paper_url:
        out.append(f"  - <{er.paper_url}>")
    if er.canonical and er.canonical.venue:
        out.append(f"  - venue: {er.canonical.venue} ({er.canonical.year})")
    for d in er.diffs:
        user_disp = _format_value(d.field, d.user_value)
        canonical_disp = _format_value(d.field, d.canonical_value)
        out.append(
            f"  - **{d.severity}** `{d.field}`: {user_disp} → {canonical_disp} ({d.rationale})"
        )
    for note in er.notes:
        out.append(f"  - _note:_ {note}")
    return "\n".join(out)


def _format_value(field: str, value: str) -> str:
    """Render a diff value: DOIs become clickable links, other fields stay as code."""
    if not value:
        return "`<empty>`"
    if field == "doi":
        normalized = normalize_doi(value)
        return f"[`{value}`](https://doi.org/{normalized})"
    return f"`{value}`"
