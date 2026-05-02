"""bibvet CLI.

Usage:
    bibvet REFS [REFS ...]                 # one or more files / directories / "-"
    bibvet REFS --fix                      # additionally write <name>.fixed.bib
    bibvet REFS --format {terminal|md|json}
    bibvet REFS --recursive                # search subdirs of any directory inputs
    bibvet REFS --explain CITEKEY          # detail for one entry
    bibvet cache clear                     # purge disk cache
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from bibvet import __version__
from bibvet.cache import DiskCache, default_cache_root
from bibvet.fix import write_fixed_bib
from bibvet.http import HttpClient
from bibvet.models import FileReport
from bibvet.pipeline import Pipeline
from bibvet.render.json import render_json
from bibvet.render.markdown import render_markdown
from bibvet.render.terminal import render_terminal
from bibvet.sources.arxiv import ArxivSource
from bibvet.sources.crossref import CrossRefSource
from bibvet.sources.semantic_scholar import SemanticScholarSource

EXAMPLES = """\
Examples:
  bibvet refs.bib                          # check one file
  bibvet *.bib                             # check via shell glob
  bibvet ./papers/                         # check all .bib in directory
  bibvet ./papers/ --recursive             # also search subdirs
  bibvet refs.bib --fix                    # write refs.fixed.bib
  bibvet refs.bib --explain mycite2024     # detail for one entry
  bibvet refs.bib --format json            # machine-readable
  cat refs.bib | bibvet -                  # read from stdin
"""


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Handle `bibvet cache <action>` before main parser to avoid positional conflict
    if argv and argv[0] == "cache":
        return _run_cache_subcommand(argv[1:])

    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if getattr(args, "debug", False):
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        paths = _collect_paths(args.inputs, recursive=args.recursive)
    except _CliError as e:
        print(f"bibvet: {e}", file=sys.stderr)
        return 2

    try:
        return asyncio.run(_run(paths, args))
    except KeyboardInterrupt:
        print("\nbibvet: interrupted", file=sys.stderr)
        return 130


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bibvet",
        description="Verify .bib entries against CrossRef, Semantic Scholar, and arXiv.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"bibvet {__version__}")
    p.add_argument("inputs", nargs="*", help="files, directories, or '-' for stdin")
    p.add_argument("--fix", action="store_true", help="write <name>.fixed.bib next to input")
    p.add_argument("--force", action="store_true", help="overwrite existing .fixed.bib output")
    p.add_argument("--recursive", "-r", action="store_true", help="recurse into subdirectories")
    p.add_argument("--format", choices=["terminal", "md", "json"], default="terminal")
    p.add_argument("--verbose", "-v", action="store_true", help="show verified entries too")
    p.add_argument("--explain", metavar="CITEKEY", help="show detailed report for one citekey")
    p.add_argument("--lenient", action="store_true", help="skip malformed entries instead of failing")
    p.add_argument(
        "--strict",
        action="store_true",
        help="promote warnings to errors and flag single-source matches",
    )
    p.add_argument(
        "--skip-source",
        action="append",
        default=[],
        choices=["crossref", "semantic_scholar", "arxiv"],
        metavar="SOURCE",
        help="skip a source (repeatable). Useful when one is rate-limiting you.",
    )
    p.add_argument("--no-cache", action="store_true", help="bypass the disk cache")
    p.add_argument("--debug", action="store_true", help="show full tracebacks on errors")
    return p


class _CliError(Exception):
    pass


def _collect_paths(inputs: list[str], *, recursive: bool) -> list[Path]:
    if not inputs:
        raise _CliError("no input files (try `bibvet refs.bib`)")
    paths: list[Path] = []
    for raw in inputs:
        if raw == "-":
            paths.append(Path("-"))
            continue
        p = Path(raw)
        if not p.exists():
            raise _CliError(f"{p}: no such file or directory")
        if p.is_dir():
            pattern = "**/*.bib" if recursive else "*.bib"
            found = sorted(p.glob(pattern))
            if not found:
                hint = "" if recursive else " (use --recursive to search subdirectories)"
                raise _CliError(f"{p}: no .bib files found{hint}")
            paths.extend(found)
        else:
            paths.append(p)
    return paths


async def _run(paths: list[Path], args) -> int:
    cache = _make_cache(args)
    skip = set(args.skip_source)
    async with HttpClient() as http:
        all_sources = {
            "crossref": CrossRefSource(http, cache),
            "semantic_scholar": SemanticScholarSource(http, cache),
            "arxiv": ArxivSource(http, cache),
        }
        sources = [s for name, s in all_sources.items() if name not in skip]
        if not sources:
            print("bibvet: no sources enabled (all skipped)", file=sys.stderr)
            return 2
        for s in sources:
            s.http = http
        path_args = await _resolve_stdin(paths)

        # Set up progress bar (only if format is terminal and stderr is a tty).
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
        )

        progress_console = Console(stderr=True)
        show_progress = args.format == "terminal" and progress_console.is_terminal

        if show_progress:
            counter = Pipeline(
                sources=sources, lenient=args.lenient, strict=args.strict
            )
            total_entries = counter.total_entries(path_args)
            # Rough estimate: each entry hits up to 3 sources times ~1.5 keys.
            # Cache hits are also fetches (instant), so total includes cached calls.
            total_fetches_est = max(total_entries * 4, 1)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=progress_console,
                transient=False,
                refresh_per_second=20,
            ) as progress:
                entry_task = progress.add_task("entries verified", total=total_entries)
                fetch_task = progress.add_task("api calls", total=total_fetches_est)
                progress.refresh()  # render once immediately so even fast runs show the bar

                def _on_entry(entry, report):
                    progress.advance(entry_task)

                def _on_fetch(entry, source_name, key_value, found):
                    progress.advance(fetch_task)

                pipeline = Pipeline(
                    sources=sources,
                    lenient=args.lenient,
                    strict=args.strict,
                    on_entry_done=_on_entry,
                    on_fetch_done=_on_fetch,
                )
                file_reports = await pipeline.run(path_args)
        else:
            pipeline = Pipeline(sources=sources, lenient=args.lenient, strict=args.strict)
            file_reports = await pipeline.run(path_args)

    if args.explain:
        file_reports = _filter_explain(file_reports, args.explain)

    _emit(file_reports, args)
    refused = False
    if args.fix:
        refused = _write_fixed(file_reports, args)
    rc = _exit_code(file_reports)
    return max(rc, 2) if refused else rc


def _make_cache(args) -> DiskCache:
    if args.no_cache:
        return DiskCache(Path("/dev/null"), ttl_seconds=0)
    return DiskCache(default_cache_root())


async def _resolve_stdin(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if str(p) == "-":
            import tempfile
            data = sys.stdin.read()
            with tempfile.NamedTemporaryFile("w", suffix=".bib", delete=False, encoding="utf-8") as f:
                f.write(data)
                out.append(Path(f.name))
        else:
            out.append(p)
    return out


def _filter_explain(file_reports: list[FileReport], citekey: str) -> list[FileReport]:
    return [
        FileReport(path=fr.path, entries=tuple(er for er in fr.entries if er.entry.citekey == citekey))
        for fr in file_reports
    ]


def _emit(file_reports: list[FileReport], args) -> None:
    if args.format == "terminal":
        render_terminal(file_reports, verbose=args.verbose)
    elif args.format == "json":
        sys.stdout.write(render_json(file_reports) + "\n")
    elif args.format == "md":
        out_path = Path("report.md")
        out_path.write_text(render_markdown(file_reports), encoding="utf-8")
        print(f"wrote {out_path}")


def _write_fixed(file_reports: list[FileReport], args) -> bool:
    """Returns True if any write was refused due to existing output without --force."""
    refused = False
    for fr in file_reports:
        if str(fr.path).endswith(".bib"):
            out = fr.path.with_suffix(".fixed.bib")
        else:
            out = Path(str(fr.path) + ".fixed.bib")
        original = fr.path.read_text(encoding="utf-8") if fr.path.exists() else ""
        try:
            write_fixed_bib(fr, out, original_text=original, force=args.force)
            print(f"wrote {out}")
        except FileExistsError as e:
            print(f"bibvet: {e}", file=sys.stderr)
            refused = True
    return refused


def _exit_code(file_reports: list[FileReport]) -> int:
    has_error = False
    has_warning = False
    for fr in file_reports:
        for er in fr.entries:
            if er.status in ("fixable", "cross_check_failed", "unverified"):
                has_error = True
            for d in er.diffs:
                if d.severity == "warning":
                    has_warning = True
    if has_error:
        return 2
    if has_warning:
        return 1
    return 0


def _run_cache_subcommand(remaining: list[str]) -> int:
    p = argparse.ArgumentParser(prog="bibvet cache")
    p.add_argument("action", choices=["clear"])
    args = p.parse_args(remaining)
    cache = DiskCache(default_cache_root())
    if args.action == "clear":
        cache.clear()
        print("cache cleared")
    return 0
