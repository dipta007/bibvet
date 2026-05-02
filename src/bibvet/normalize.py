"""Pure string-normalization helpers used everywhere comparisons happen."""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

# LaTeX accent commands like \'{e}, \^{o}, \"{u}
_LATEX_ACCENTS = {
    r"\'": {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "y": "ý",
             "A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú", "Y": "Ý",
             "n": "ń", "N": "Ń"},
    r"\`": {"a": "à", "e": "è", "i": "ì", "o": "ò", "u": "ù",
             "A": "À", "E": "È", "I": "Ì", "O": "Ò", "U": "Ù"},
    r"\^": {"a": "â", "e": "ê", "i": "î", "o": "ô", "u": "û",
             "A": "Â", "E": "Ê", "I": "Î", "O": "Ô", "U": "Û"},
    r'\"': {"a": "ä", "e": "ë", "i": "ï", "o": "ö", "u": "ü",
             "A": "Ä", "E": "Ë", "I": "Ï", "O": "Ö", "U": "Ü"},
    r"\~": {"a": "ã", "n": "ñ", "o": "õ", "A": "Ã", "N": "Ñ", "O": "Õ"},
    r"\c": {"c": "ç", "C": "Ç"},
}

# Match \cmd{X} or \cmd X for accent commands
_ACCENT_RE = re.compile(r'\\([\'"`^~c])\{?(\w)\}?')

# Match \textit{X}, \textbf{X}, \emph{X}, etc. — strip command, keep arg
_FORMAT_RE = re.compile(r'\\(?:textit|textbf|emph|texttt|textsc|mathrm|mathit){([^{}]*)}')

# Match \& \% \$ \# \_ — escape sequences for literal chars
_ESCAPE_RE = re.compile(r'\\([&%$#_])')


def strip_latex(s: str) -> str:
    """Strip LaTeX formatting and resolve accents to Unicode characters."""

    def _accent_replace(m: re.Match[str]) -> str:
        cmd, ch = m.group(1), m.group(2)
        key = "\\" + cmd
        return _LATEX_ACCENTS.get(key, {}).get(ch, ch)

    s = _ACCENT_RE.sub(_accent_replace, s)
    s = _FORMAT_RE.sub(r"\1", s)
    s = _ESCAPE_RE.sub(r"\1", s)
    # Strip remaining braces (used for case-protection in BibTeX)
    s = s.replace("{", "").replace("}", "")
    return s


_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_string(s: str) -> str:
    """Aggressive normalization: strip LaTeX, NFKC, lowercase, drop punctuation, collapse whitespace.

    Used for fuzzy-comparing titles, venues, and authors.
    """
    s = strip_latex(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def fuzzy_ratio(a: str, b: str) -> int:
    """Token-set similarity (0-100). Inputs are normalized before comparison."""
    return int(fuzz.token_set_ratio(normalize_string(a), normalize_string(b)))


def normalize_doi(doi: str) -> str:
    """Canonical DOI form: lowercase, no scheme, no `doi:` prefix, no whitespace."""
    s = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s
