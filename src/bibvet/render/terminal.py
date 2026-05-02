"""Pretty terminal output via rich. Summary line + problems inline."""
from __future__ import annotations

from collections import Counter

from rich.console import Console

from bibvet.models import EntryReport, FileReport

ICONS = {
    "verified": "✅",
    "fixable": "❌",
    "cross_check_failed": "⚠",
    "unverified": "❓",
    "skipped": "⏭",
}


def render_terminal(
    file_reports: list[FileReport],
    *,
    console: Console | None = None,
    verbose: bool = False,
) -> None:
    console = console or Console()
    grand_total: Counter[str] = Counter()

    for fr in file_reports:
        statuses = Counter(er.status for er in fr.entries)
        grand_total.update(statuses)
        n = len(fr.entries)
        summary_parts = [f"{n} entries"]
        for status, icon in ICONS.items():
            if statuses.get(status):
                summary_parts.append(f"{icon} {statuses[status]} {status}")
        console.print(f"[bold]{fr.path}[/bold] · " + " · ".join(summary_parts))

        for er in fr.entries:
            if er.status in ("verified", "skipped") and not verbose:
                continue
            _render_entry(console, fr.path, er)

    if len(file_reports) > 1:
        total_n = sum(len(fr.entries) for fr in file_reports)
        parts = [f"{total_n} entries"]
        for status, icon in ICONS.items():
            if grand_total.get(status):
                parts.append(f"{icon} {grand_total[status]} {status}")
        console.print("─" * 40)
        console.print("[bold]total[/bold] · " + " · ".join(parts))


def _render_entry(console: Console, path, er: EntryReport) -> None:
    icon = ICONS.get(er.status, "•")
    color = {
        "fixable": "red",
        "cross_check_failed": "yellow",
        "unverified": "magenta",
        "verified": "green",
        "skipped": "dim",
    }.get(er.status, "white")
    console.print(
        f"  {icon} [{color}]{er.entry.citekey}[/{color}] "
        f"({path}:{er.entry.source_line})"
    )
    if er.paper_url:
        console.print(f"     [link]{er.paper_url}[/link]")
    if er.canonical and er.canonical.venue:
        console.print(f"     venue: {er.canonical.venue} ({er.canonical.year})")
    for d in er.diffs:
        sev_color = {"error": "red", "warning": "yellow", "info": "dim"}.get(d.severity, "white")
        console.print(
            f"     [{sev_color}]{d.severity}[/{sev_color}] "
            f"{d.field}: '{d.user_value}' → '{d.canonical_value}' ({d.rationale})"
        )
    for note in er.notes:
        console.print(f"     [dim]note:[/dim] {note}")
