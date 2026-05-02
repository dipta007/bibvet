from bibvet.normalize import (
    fuzzy_ratio,
    normalize_doi,
    normalize_string,
    strip_latex,
)


class TestStripLatex:
    def test_strips_braces(self):
        assert strip_latex("{BERT}: pre-training") == "BERT: pre-training"

    def test_strips_textit(self):
        assert strip_latex(r"\textit{Foo}") == "Foo"

    def test_strips_textbf(self):
        assert strip_latex(r"\textbf{Foo}") == "Foo"

    def test_strips_emph(self):
        assert strip_latex(r"\emph{Foo}") == "Foo"

    def test_handles_accents(self):
        assert strip_latex(r"\'{e}") == "é"
        assert strip_latex(r"\^{o}") == "ô"
        assert strip_latex(r'\"{u}') == "ü"

    def test_handles_ampersand(self):
        assert strip_latex(r"Foo \& Bar") == "Foo & Bar"

    def test_handles_nested_braces(self):
        assert strip_latex("{{Foo}}") == "Foo"


class TestNormalizeString:
    def test_lowercases(self):
        assert normalize_string("Hello") == "hello"

    def test_collapses_whitespace(self):
        assert normalize_string("a   b\t\nc") == "a b c"

    def test_unicode_nfkc(self):
        # Composed vs decomposed é
        assert normalize_string("café") == normalize_string("café")

    def test_strips_latex_first(self):
        assert normalize_string(r"{BERT}") == "bert"

    def test_strips_punctuation(self):
        assert normalize_string("hello, world!") == "hello world"


class TestFuzzyRatio:
    def test_identical_strings(self):
        assert fuzzy_ratio("hello world", "hello world") == 100

    def test_completely_different(self):
        assert fuzzy_ratio("hello", "xyz") < 50

    def test_token_set_order_insensitive(self):
        # Same tokens, different order → high score
        assert fuzzy_ratio("foo bar baz", "baz bar foo") >= 95

    def test_normalizes_inputs(self):
        # Already-normalized vs LaTeX form should still score 100
        assert fuzzy_ratio(r"{BERT}: Pre-training", "bert pre training") >= 95


class TestNormalizeDoi:
    def test_strips_doi_prefix(self):
        assert normalize_doi("doi:10.1/abc") == "10.1/abc"

    def test_strips_url_prefix(self):
        assert normalize_doi("https://doi.org/10.1/abc") == "10.1/abc"

    def test_strips_http_url_prefix(self):
        assert normalize_doi("http://doi.org/10.1/abc") == "10.1/abc"

    def test_lowercases(self):
        assert normalize_doi("10.1/ABC") == "10.1/abc"

    def test_handles_plain_doi(self):
        assert normalize_doi("10.1/abc") == "10.1/abc"
