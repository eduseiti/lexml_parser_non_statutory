"""The label grammar: what a rótulo looks like, and what only looks like one.

Plan §8 Cycle 4 lists the positive forms — ``1.``, ``1.1``, ``1.1.1``, ``I -``,
``a)``, ``c. 1)``, ``CAPÍTULO``, ``Seção``, ``Subseção``, ordinals, roman,
``único``, ``-A``. Getting those right is the easy half.

The hard half is the negatives, and the corpus supplied three the plan does not
list (amendment A-4.2). Each is a real paragraph from a real sample:

    2.08.30.00 - Isenção das Sociedades Cooperativas       pn_cst_38 block 3
    06.12.1993 …                                           sumula_stj_125 block 61
    Lei nº 12.618, de 2012, que instituiu o regime…        parecer_93, everywhere

A ``00`` is not an ordinal, a date is not a section number, and a norm citation
is not a heading. Two of the three are refused here; the third — the orphan
prefix — needs document context and is refused in :mod:`.unify`, because
``2.3.1`` is a perfectly good label when ``2.3`` is open and noise when it is
not. The grammar answers "could this be a label?"; the document answers "is it?".

Named units (``Súmula CARF nº 1``) are likewise **not** a grammar rule. They are
detected as a series over the whole document (:func:`.unify.detect_unit_series`)
and passed back in through ``unit_heads``, which is exactly what stops
``Lei nº 12.618`` from ever parsing as one (amendment A-4.4).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = [
    "ARTICLE_RE",
    "Label",
    "alpha_to_int",
    "fold",
    "looks_like_heading",
    "parse_label",
    "roman_to_int",
    "strip_leading_quote",
]

#: Section-naming words that head a `named` label (`CAPÍTULO II`, `Seção I`).
#: Ordered longest-first so `SUBSEÇÃO` never matches as `SEÇÃO`.
_NAMED_UNITS: tuple[tuple[str, str], ...] = (
    ("subsecao", "subsecao"),
    ("secao", "secao"),
    ("capitulo", "capitulo"),
    ("titulo", "titulo"),
    ("livro", "livro"),
    ("parte", "parte"),
)

#: Words that head a norm citation. A paragraph starting with one of these is
#: naming another document, not labelling itself — `Lei nº 12.618` is the plan's
#: own worked example of a non-label.
_CITATION_HEADS = frozenset(
    {
        "lei",
        "leis",
        "decreto",
        "decretos",
        "decreto-lei",
        "medida",
        "emenda",
        "constituicao",
        "portaria",
        "instrucao",
        "resolucao",
        "ato",
        "parecer",
        "acordao",
        "processo",
        "recurso",
        "agravo",
        "sumula",
        "oficio",
        "nota",
        "circular",
    }
)

#: `Art. 1º`, `Art 40.`, `Art. 1º-A`, with an optional opening quote.
ARTICLE_RE = re.compile(
    r"^\s*[\"“'«]?\s*Art\.?\s*(\d+)\s*[ºo°]?\s*(-\s*[A-Z])?\s*[.\-–—)]?\s*",
    re.IGNORECASE,
)

#: `§ 2º`, `§ 4º-A` — the `-A` suffix is as real on a parágrafo as on an artigo.
_PARAGRAFO_RE = re.compile(
    r"^\s*[\"“'«]?\s*§\s*(\d+)\s*[ºo°]?\s*(-\s*[A-Z])?\s*[.\-–—)]?\s*"
)
_PARAGRAFO_UNICO_RE = re.compile(r"^\s*[\"“'«]?\s*par[áa]grafo\s+[úu]nico\s*[.\-–—:]?\s*", re.I)

#: A dotted numeric run, with an optional trailing separator.
_NUMERIC_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3})*)\s*([.)\-–—])?\s+")
#: The same, but ending the paragraph (`2.1`).
_NUMERIC_ONLY_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3})*)\s*([.)\-–—])?\s*$")

_ROMAN_RE = re.compile(r"^\s*([IVXLCDM]{1,7})\s*([.)\-–—])\s+", re.IGNORECASE)
_ROMAN_ONLY_RE = re.compile(r"^\s*([IVXLCDM]{1,7})\s*([.)\-–—])?\s*$")
_ALPHA_RE = re.compile(r"^\s*([a-z])\s*([.)])\s+")
_ALPHA_ONLY_RE = re.compile(r"^\s*([a-z])\s*([.)])\s*$")
#: `c. 1)` — an alpha label subdivided by a numeric one.
_COMPOUND_RE = re.compile(r"^\s*([a-z])\s*[.)]\s*(\d{1,3})\s*([.)])\s+")

_ORDINAL_RE = re.compile(r"^\s*(\d{1,3})\s*[ºo°ª]\s*([.)\-–—])?\s+")
#: The same, ending the paragraph. Every other kind has an end-of-string twin;
#: without this one a bare `1º` on a line of its own parses as nothing at all.
#: No sample contains one, so this is written for the 300+ unseen documents.
_ORDINAL_ONLY_RE = re.compile(r"^\s*(\d{1,3})\s*[ºo°ª]\s*([.)\-–—])?\s*$")

_UNIT_RE = re.compile(
    r"^\s*(?P<head>[^\d\n]{2,60}?)\s*(?:n[ºo°]\.?|n\.|nº)\s*(?P<num>\d{1,4})\s*$",
    re.IGNORECASE,
)

#: A number written with thousands groups, or followed by a year — the shape of
#: a citation, never of a section number.
_GROUPED_NUMBER_RE = re.compile(r"\d\.\d{3}(?!\d)")
#: `29.11.1993`, `17/11/2003` — three components ending in a year. Two-component
#: dates (`06.12`) are caught instead by the leading-zero rule below, because
#: `2.1` is indistinguishable from a two-component date by shape alone.
_DATE_LIKE_RE = re.compile(r"^\s*\d{1,2}[./]\d{1,2}[./]\d{2,4}\s*[.\-–—]?\s*$")
_YEAR_SUFFIX_RE = re.compile(r"^\s*\d{1,4}\s*/\s*\d{4}")

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

#: Words that can only be a roman numeral by accident. `C` is a real numeral but
#: `I` heading a Portuguese sentence is far more often the pronoun-free article,
#: so a roman label always needs a separator (enforced by `_ROMAN_RE`).
_ROMAN_STRICT = re.compile(r"^(?=[MDCLXVI])M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")

#: How long a remainder may be and still read as a heading rather than prose.
_HEADING_MAX_WORDS = 12


def fold(text: str) -> str:
    """Accent-fold and lowercase — the same rule Cycle 2's profiles use."""
    folded = unicodedata.normalize("NFKD", text)
    return folded.encode("ascii", "ignore").decode("ascii").lower()


def strip_leading_quote(text: str) -> str:
    """Drop an opening quotation mark, keeping the fact that it was there to
    the caller. The quotation guard wants the mark; the grammar does not."""
    return re.sub(r'^\s*["“\'«]\s*', "", text)


def roman_to_int(value: str) -> int | None:
    """Roman numeral → int, strictly. Returns ``None`` for malformed input."""
    upper = value.upper()
    if not upper or not _ROMAN_STRICT.match(upper):
        return None
    total = 0
    previous = 0
    for char in reversed(upper):
        current = _ROMAN_VALUES[char]
        total = total - current if current < previous else total + current
        previous = max(previous, current)
    return total


def alpha_to_int(value: str) -> int | None:
    """``a`` → 1 … ``z`` → 26. Single letters only, which is all the corpus uses."""
    folded = fold(value)
    if len(folded) != 1 or not ("a" <= folded <= "z"):
        return None
    return ord(folded) - ord("a") + 1


def looks_like_heading(text: str) -> bool:
    """True when a label's remainder reads as a heading, not as prose.

    ``2. DAS SOCIEDADES COOPERATIVAS`` is a heading; ``5.1 - Como foi dito
    inicialmente, deve o imposto…`` is a numbered paragraph whose remainder is
    its own body. The distinction is what fills ``nomeAgrupador`` (plan §5.1)
    without inventing one.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith((".", ";", ":", ",")):
        # A closing period is the reliable prose tell — but not on an
        # abbreviation-free single word like `DECORRÊNCIA.`
        if len(stripped.split()) > 3:
            return False
    words = stripped.split()
    if len(words) > _HEADING_MAX_WORDS:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.8:
        return True
    return len(words) <= 6 and not stripped.endswith(".")


def _is_citation_start(text: str) -> bool:
    """True when the paragraph opens by naming another norm."""
    head = fold(strip_leading_quote(text)).split()
    return bool(head) and head[0].strip(",.;:") in _CITATION_HEADS


def _components_valid(parts: list[str]) -> bool:
    """Every component must be a plain positive ordinal.

    Two rejections, both forced by real paragraphs (amendment A-4.2). A zero
    component is not an ordinal, and neither is a zero-*padded* one: nobody
    numbers a section ``08``. That single rule disposes of ``pn_cst_38``'s
    subject-classification codes (``2.08.30.00``) and of ``sumula_stj_125``'s
    dates (``06.12``) — and it is what lets a two-component date be told apart
    from ``2.1``, which by shape alone it cannot be.
    """
    for part in parts:
        stripped = part.strip()
        if not stripped or not stripped.isdigit() or int(stripped) <= 0:
            return False
        if len(stripped) > 1 and stripped[0] == "0":
            return False
    return True


@dataclass(frozen=True)
class Label:
    """A parsed rótulo and what remains of its paragraph."""

    raw: str
    kind: str
    value: tuple[int, ...]
    text: str = ""
    separator: str | None = None
    unit_head: str | None = None
    quoted: bool = False

    @property
    def depth(self) -> int:
        """How deep the label itself declares it is — ``2.3.1`` is 3."""
        return len(self.value) if self.kind == "numeric" else 1

    @property
    def canonical(self) -> str:
        """The rótulo without its separator — ``2.1 -`` becomes ``2.1``.

        ``raw`` keeps the document's own punctuation, which is what a faithful
        rendering wants; ``canonical`` is what an ``id`` path or a lookup key
        wants. Cycle 5 chooses.
        """
        if self.kind == "numeric":
            return ".".join(str(v) for v in self.value)
        return self.raw.rstrip(" .)-–—")

    @property
    def is_dispositivo(self) -> bool:
        """True for statutory labels, which never become sections on the
        generic route (spec decision D-3)."""
        return self.kind in {"artigo", "paragrafo"}

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "raw": self.raw,
            "kind": self.kind,
            "value": list(self.value),
        }
        if self.separator:
            data["separator"] = self.separator
        if self.unit_head:
            data["unit_head"] = self.unit_head
        if self.quoted:
            data["quoted"] = True
        return data


def _named(text: str) -> Label | None:
    folded = fold(text)
    for token, kind in _NAMED_UNITS:
        if not folded.startswith(token):
            continue
        rest = text[len(token) :].lstrip(" \t-–—.:")
        rest_folded = fold(rest)
        if rest_folded.startswith(("unico", "unica")):
            width = len(rest.split()[0]) if rest.split() else 0
            return Label(text[: len(token)], kind, (1,), rest[width:].strip(), None)
        head = rest.split()[0] if rest.split() else ""
        number = roman_to_int(head.rstrip(".-–—")) if head else None
        if number is None and head.rstrip(".-–—").isdigit():
            number = int(head.rstrip(".-–—"))
        if number is None:
            # `PARTE ESPECIAL`, `LIVRO COMPLEMENTAR` — named but unnumbered.
            if rest and rest[0].isupper():
                return Label(text[: len(token)], kind, (1,), rest.strip(), None)
            return None
        raw = text[: len(token)] + " " + head
        return Label(raw.strip(), kind, (number,), rest[len(head) :].strip(), None)
    return None


def parse_label(
    text: str, *, unit_heads: frozenset[str] = frozenset(), allow_bare_numeric: bool = True
) -> Label | None:
    """Parse a paragraph-initial label, or return ``None``.

    ``unit_heads`` carries the named-unit series the document was found to use
    (amendment A-4.4). Without it, ``Súmula CARF nº 1`` is just a sentence — and
    that is the point: it stops ``Lei nº 12.618`` from ever being a label.
    """
    if not text or not text.strip():
        return None
    quoted = bool(re.match(r'^\s*["“\'«]', text))
    body = strip_leading_quote(text).strip()
    if not body:
        return None

    # Statutory labels first: they are unambiguous and must not be mistaken for
    # an ordinal or a numeric item.
    match = _PARAGRAFO_UNICO_RE.match(body)
    if match:
        return Label(match.group(0).strip(), "paragrafo", (1,), body[match.end() :].strip(), None, quoted=quoted)
    match = _PARAGRAFO_RE.match(body)
    if match:
        return Label(match.group(0).strip(), "paragrafo", (int(match.group(1)),), body[match.end() :].strip(), None, quoted=quoted)
    match = ARTICLE_RE.match(body)
    if match and match.end() > 0:
        return Label(match.group(0).strip(), "artigo", (int(match.group(1)),), body[match.end() :].strip(), None, quoted=quoted)

    named = _named(body)
    if named is not None:
        return Label(named.raw, named.kind, named.value, named.text, named.separator, quoted=quoted)

    # A named unit the document was shown to use as a heading series.
    if unit_heads:
        match = _UNIT_RE.match(body)
        if match and fold(match.group("head")).strip() in unit_heads:
            return Label(body, "unit", (int(match.group("num")),), "", None, fold(match.group("head")).strip(), quoted=quoted)

    if _is_citation_start(body):
        return None
    if _DATE_LIKE_RE.match(body) or _YEAR_SUFFIX_RE.match(body):
        return None

    match = _COMPOUND_RE.match(body)
    if match:
        alpha = alpha_to_int(match.group(1))
        if alpha is not None:
            return Label(match.group(0).strip(), "compound", (alpha, int(match.group(2))), body[match.end() :].strip(), match.group(3), quoted=quoted)

    # The whole-paragraph pattern is tried first. `_NUMERIC_RE` requires
    # trailing whitespace, so on a bare `2.1 -` it backtracks past the hyphen
    # and reports `raw="2.1"` with the separator stranded in the remainder —
    # which would give a heading-only paragraph a body consisting of `-`.
    for pattern, only in ((_NUMERIC_ONLY_RE, True), (_NUMERIC_RE, False)):
        match = pattern.match(body)
        if not match:
            continue
        digits = match.group(1)
        rest = "" if only else body[match.end() :].strip()
        if _GROUPED_NUMBER_RE.search(digits):
            # `1.500/2014`, `12.618` — thousands groups, not a dotted path.
            return None
        parts = digits.split(".")
        if not _components_valid(parts):
            return None
        separator = match.group(2)
        if separator is None and not only and len(parts) == 1:
            # `7 DECORRÊNCIA` is a label; `7 pessoas foram ouvidas…` is prose.
            # A *single* number with no separator is ambiguous, so the remainder
            # must read as a heading and the caller must still find the value
            # continues an established series. A dotted label needs neither
            # test: the dot is already the separator, and `adn_cst_10`'s
            # `1.1 Na apuração do ganho…` is a real subsection whose remainder
            # is ordinary prose.
            if not allow_bare_numeric or not looks_like_heading(rest):
                return None
        value = tuple(int(p) for p in parts)
        raw = match.group(0).strip() if not only else body.strip()
        return Label(raw, "numeric", value, rest, separator, quoted=quoted)

    for pattern, only in ((_ROMAN_RE, False), (_ROMAN_ONLY_RE, True)):
        match = pattern.match(body)
        if not match:
            continue
        number = roman_to_int(match.group(1))
        if number is None:
            break
        if only and match.group(2) is None:
            break
        rest = "" if only else body[match.end() :].strip()
        return Label(match.group(0).strip(), "roman", (number,), rest, match.group(2), quoted=quoted)

    for pattern, only in ((_ALPHA_RE, False), (_ALPHA_ONLY_RE, True)):
        match = pattern.match(body)
        if not match:
            continue
        number = alpha_to_int(match.group(1))
        if number is None:
            break
        rest = "" if only else body[match.end() :].strip()
        return Label(match.group(0).strip(), "alpha", (number,), rest, match.group(2), quoted=quoted)

    for pattern, only in ((_ORDINAL_ONLY_RE, True), (_ORDINAL_RE, False)):
        match = pattern.match(body)
        if match:
            rest = "" if only else body[match.end() :].strip()
            return Label(
                match.group(0).strip(),
                "ordinal",
                (int(match.group(1)),),
                rest,
                match.group(2),
                quoted=quoted,
            )

    return None
