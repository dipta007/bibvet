# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`bibvet` is a CLI that verifies `.bib` entries against CrossRef, Semantic Scholar, and arXiv — primarily to catch LLM-hallucinated citations (fabricated DOIs, wrong years, swapped authors, mismatched title/DOI pairs). The full design intent lives in `docs/superpowers/specs/2026-05-01-bibvet-design.md` (gitignored locally; treat it as authoritative when changing core behavior).

## Common commands

```bash
uv sync --all-extras              # install runtime + dev deps
uv run pytest -q                  # full suite
uv run pytest tests/test_compare.py::test_wrong_year_is_fixable -v   # single test
uv run pytest -k "strict" -v      # by name pattern
uv run ruff check src tests       # lint
uv run ruff check src tests --fix # auto-fix what's safe
uv run bibvet refs.bib            # run the CLI against a .bib
uv run bibvet cache clear         # purge ~/Library/Caches/bibvet
```

## Architecture

Five-stage async pipeline in `src/bibvet/`:

```
parser.py  →  resolve.py  →  sources/*.py  →  compare.py  →  render/*.py
   .bib       UserEntry      CanonicalRecord   EntryReport    terminal/md/json
            → LookupKey      (per source)
```

`pipeline.py` orchestrates with bounded concurrency (5 entries at a time) and per-fetch progress callbacks. `cli.py` is a thin argparse layer over `Pipeline`.

**Module responsibilities** — each file has one thing it owns:

- **`models.py`** — frozen dataclasses that are the contracts between modules: `UserEntry`, `LookupKey`, `CanonicalRecord`, `FieldDiff`, `EntryReport`, `FileReport`. Don't put logic here.
- **`compare.py`** — pure decision logic, no I/O. The "brain": classifies each entry as `verified` / `fixable` / `cross_check_failed` / `unverified` / `skipped`. **All hallucination detection lives here.** Most-tested module.
- **`normalize.py`** — pure string helpers: LaTeX-strip, NFKC, fuzzy ratio, DOI normalize, `title_match_score` (used by sources to disambiguate same-titled papers using year + first-author).
- **`resolve.py`** — `UserEntry → list[LookupKey]`. Knows where to find arXiv IDs (eprint, journal, doi, url, note).
- **`sources/{base,crossref,semantic_scholar,arxiv}.py`** — each source implements `Source.supports(key)` and `async fetch(key) -> CanonicalRecord | None`. Each source has its own `RateLimiter` (arXiv 3s, S2 1s/0.05s with key, CrossRef 0.1s).
- **`http.py`** — `HttpClient` wraps httpx with retry-until-terminal-answer (retries forever on 429/5xx/network errors with exponential backoff + jitter; 4xx raises `TerminalNegative`). Surfaces long retries (>= 4s) to stderr.
- **`cache.py`** — `DiskCache` at platform user-cache dir, 30-day TTL, self-healing on corrupt files, falls back to in-memory if dir is unwritable. Cache hits skip rate-limiting.
- **`fix.py`** — writes `<name>.fixed.bib`. `REQUIRED_FIELDS` defines per-entry-type field set kept in canonical output; **only fields we actually verify** (`author`, `title`, `year`, `journal/booktitle`, `doi`, `eprint`) — `pages`, `volume`, `number` are deliberately dropped.
- **`render/{terminal,markdown,json}.py`** — pure functions over `list[FileReport]`. Renderers are interchangeable.
- **`ratelimit.py`** — async lock + min-interval gate; instance per source.

**Cross-checking is the core hallucination defense:** `compare_entry` looks at the record returned by DOI/arXiv lookup and the record returned by title-search. If they disagree (different DOI, or title fuzzy similarity < 90), status becomes `cross_check_failed` — that's the LLM-mixed-up-papers signal.

## Conventions

- **TDD**: write the failing test, run it (must fail with ImportError or AssertionError), implement minimal code, run again, commit. Most existing tests follow this pattern.
- **Frozen dataclasses with tuples** (not lists) for collection fields in `models.py` — they're hashable and signal immutability.
- **Pure functions where possible**: `compare.py`, `normalize.py`, `render/*` are I/O-free. They're the easiest to test and the most-tested.
- **Sources are interchangeable** behind one `Source` interface. Adding a fourth source = one file in `sources/` plus registering it in `cli.py:_run`.
- **Rate-limit only HTTP, not cache hits.** Each source's `_http_fetch` calls `await self._rate_limiter.acquire()`; `fetch` calls cache first.
- **Determinism**: no LLMs in the verification path. `title_match_score` and tiered fuzzy thresholds replace what an LLM might guess at.
- **`--strict` is high-recall**: collapse warning band into errors, treat unmatched non-paper types as unverified, flag single-source matches. The user's stated priority is "must not miss anything hallucinated" even at the cost of false positives.

## Testing notes

- `tests/test_compare.py` is the most important file in the suite — every status transition and severity tier should have a test there.
- `tests/test_real_world.py` has scenarios that mimic LLM hallucination patterns (misspelled authors, fabricated DOIs, partial mismatches). Add new failure modes here.
- Source tests use `respx` to mock httpx; recorded JSON/XML fixtures live under `tests/fixtures/<source>/`.
- `test_cli.py` patches `Pipeline._run_entry` (`_patch_pipeline` and `_patch_pipeline_strict` helpers) so CLI tests don't make HTTP calls.
- Don't write tests that hit live APIs — the only "live" verification is the manual smoke described in the original implementation plan.

## Things that bite

- **arXiv rate-limits aggressively** (3s between requests is their published guideline; they remember IPs). When debugging a slow run, `--skip-source arxiv` is the workaround. arXiv title-search is intentionally disabled (`ArxivSource.supports` only matches `kind="arxiv"`); only direct ID lookups go through arXiv.
- **CrossRef returns `None` in `date-parts[0][0]`** for some records — always go through `_extract_year` in `crossref.py`, never `int(...)` directly on the field.
- **Token-set fuzzy ratios collide** for same-token-set titles ("Attention Is All You Need" vs "Is Attention All You Need?"). `title_match_score` adds year + author bonuses (and a -50 penalty for year diff > 5) to disambiguate. Don't replace it with plain `fuzzy_ratio` for source candidate selection.
- **Tests that assert on titles like "T" (1 char)**: `resolve_lookup_keys` requires title >= 5 chars to emit a `title_query`, so tests using "T" produce no key and the source is never called. Use realistic titles in fixtures.
- **`docs/superpowers/`** is gitignored via `.git/info/exclude`. Don't add it to `.gitignore` (which would commit a reference to it). Don't try to commit anything inside that directory.
- **`uv sync --all-extras --python <ver>`** in CI silently skipped dev extras with `setup-uv@v3`. CI uses `setup-uv@v4` + `uv sync --extra dev` + `uvx ruff` for the lint step. Don't revert.

## What `--fix` actually changes

`<name>.fixed.bib` is a complete drop-in replacement, entries in original order:

- `verified` / `skipped` → original block byte-identical
- `fixable` → re-emitted with the canonical field set (entry type preserved)
- `cross_check_failed` / `unverified` → original block + leading `% bibvet:` comment for `grep`-ability

The original `.bib` is never modified. `--force` is required to overwrite an existing `.fixed.bib`.
