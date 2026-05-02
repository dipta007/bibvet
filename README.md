# bibvet

> Vet your bibliography. Catches hallucinated citations, wrong years, and fabricated DOIs.

`bibvet` reads `.bib` files and verifies every entry against [CrossRef](https://www.crossref.org), [Semantic Scholar](https://www.semanticscholar.org), and [arXiv](https://arxiv.org). It cross-checks the DOI a paper claims against the title it claims to have — catching the most common LLM citation hallucinations — and can write a cleaned `.bib` with canonical fields.

## Install

```bash
# uv (recommended) — installs the `bibvet` command
uv tool install git+https://github.com/dipta007/bibvet.git

# or run without installing
uvx --from git+https://github.com/dipta007/bibvet.git bibvet refs.bib

# or pipx
pipx install git+https://github.com/dipta007/bibvet.git

# or plain pip
pip install git+https://github.com/dipta007/bibvet.git
```

No API keys, no config, no setup needed.

## Quick start

```bash
bibvet refs.bib                # check one file
bibvet refs.bib --strict       # high-recall sweep (recommended pre-submission)
bibvet refs.bib --fix          # also write refs.fixed.bib with canonical fields
```

## What it catches

- **Hallucinated DOIs** — fabricated `doi:` strings that don't exist
- **Wrong year** — paper exists, but the cited year is off
- **Wrong / swapped authors** — first author is missing, or author order is wrong
- **Mismatched title and DOI** — DOI resolves to one paper, title matches another (the LLM mixed two real papers)
- **Fully hallucinated entries** — paper doesn't exist at any source
- **Venue mismatches** — softer signal, often cosmetic
- **Cosmetic differences** — `Y. Bengio` vs `Yoshua Bengio` (informational only)

## Usage

```bash
bibvet refs.bib                        # check one file
bibvet refs1.bib refs2.bib refs3.bib   # multiple files
bibvet ./papers/                       # all .bib files in a directory
bibvet ./papers/ --recursive           # also search subdirectories
bibvet refs.bib --fix                  # additionally write refs.fixed.bib
bibvet refs.bib --explain mycite2024   # detail for one entry
bibvet refs.bib --format md            # write report.md (clickable links)
bibvet refs.bib --format json          # machine-readable
bibvet refs.bib --skip-source arxiv    # disable a source if it's rate-limiting
cat refs.bib | bibvet -                # read from stdin
```

## Exit codes

- `0` — everything verified or skipped
- `1` — warnings only
- `2` — at least one entry needs attention

CI-friendly: drop `bibvet refs.bib` into a pre-submission check and fail the build on `2`.

## Output

```
refs.bib · 23 entries · 20 verified · 2 fixable · 1 warning
  bad-cite (refs.bib:42)
     https://doi.org/10.5555/3295222.3295349
     venue: Advances in Neural Information Processing Systems (2017)
     error doi: '10.1234/fake' -> '10.5555/3295222.3295349' (DOI does not match canonical record)
     error year: '2018' -> '2017' (year mismatch)
```

`--fix` writes `<name>.fixed.bib` next to each input with **only the fields bibvet verifies**: `author, title, year, journal/booktitle, doi, eprint`. Unverified fields like `pages`, `volume`, `number` are dropped — they're commonly hallucinated and we can't confirm them. Entries that can't be auto-fixed (cross-check failures, unverified) are left byte-identical with a `% bibvet:` comment above them — `grep '^% bibvet:' refs.fixed.bib` to find what needs review.

## Strict mode

```bash
bibvet refs.bib --strict
```

For high-recall hallucination sweeps. Promotes warnings to errors:

- Any title difference flagged (was: cosmetic differences silenced)
- Venue mismatches treated as errors (was: warnings)
- Books, theses, and `@misc` entries with no canonical match flagged (was: silently skipped)
- Single-source matches noted for manual review

Slightly more false positives, but won't miss subtly altered citations.

## Configuration

bibvet works with no config. Optional environment variables:

- `SEMANTIC_SCHOLAR_API_KEY` — higher quota for Semantic Scholar
- `CROSSREF_MAILTO` — opts into CrossRef's polite pool

Cache lives at the platform-default user cache directory (`~/Library/Caches/bibvet/` on macOS, `~/.cache/bibvet/` on Linux). 30-day TTL. `bibvet cache clear` to purge.

## License

MIT.
