"""Read .bib files into UserEntry lists.

Wraps bibtexparser v2 with a narrow surface and informative errors.
"""
from __future__ import annotations

import logging
from pathlib import Path

import bibtexparser

from bibvet.models import UserEntry

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when a .bib file cannot be parsed (and lenient mode wasn't requested)."""


def parse_bib_file(path: Path, *, lenient: bool = False) -> list[UserEntry]:
    """Parse a single .bib file. Returns entries in document order.

    If `lenient`, malformed entries are skipped with a warning. Otherwise raises ParseError.
    """
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []

    library = bibtexparser.parse_string(text)

    if library.failed_blocks and not lenient:
        first = library.failed_blocks[0]
        raise ParseError(
            f"{path}:{first.start_line + 1}: parse error in entry"
        )

    if library.failed_blocks and lenient:
        for fb in library.failed_blocks:
            logger.warning(
                "%s:%s: skipping malformed entry",
                path,
                fb.start_line + 1,
            )

    entries: list[UserEntry] = []
    for block in library.entries:
        fields = {f.key.lower(): str(f.value) for f in block.fields}
        entries.append(
            UserEntry(
                citekey=block.key,
                entry_type=block.entry_type.lower(),
                fields=fields,
                source_file=path,
                source_line=block.start_line + 1,
            )
        )
    return entries
