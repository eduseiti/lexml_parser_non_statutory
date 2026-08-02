"""LexML URN construction and parsing.

A LexML URN names a document by *what it is* rather than where it lives::

    urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277
            │  │                  │        │          └ number
            │  │                  │        └ date (or bare year)
            │  │                  └ document type
            │  └ authority
            └ locality

The grammar mirrors the reference parser's ``Metadado.scala:145``
(``urn:lex:$localidade:$autoridade:$tipoNorma:${id.urnRepr}``) and
``Id.urnRepr`` (``anoOuDataUrn + ";" + num``), so URNs we emit are
interchangeable with those the statutory parser produces for the same
authority.

The ``!fragment`` suffix is the annex convention of plan §2.9 — a sibling
annex document is ``…;277!anexo1``. Cycle 6 needs it; it is built here
because the grammar belongs in one place.

Accent folding lives here too. Cycle 1's ``normalize_text`` deliberately does
*not* fold — it normalises to NFC, preserving ``ç`` and ``ã`` because the
document text must survive intact. A URN slug is the opposite case: it must be
ASCII, so ``MINISTÉRIO DA FAZENDA`` becomes ``ministerio.fazenda``. The two
normalisations serve different masters and are kept apart.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = [
    "LEXML_URN_RE",
    "UrnDate",
    "UrnParts",
    "build_urn",
    "is_valid_urn",
    "parse_urn",
    "slugify_authority",
]


# A slug segment: lowercase ASCII words joined by dots, optionally with a
# ``;`` sub-type (the reference uses this for e.g. "projeto.lei;pls", and we
# use it for "ministerio.fazenda;secretaria.receita.federal").
_SEGMENT = r"[a-z0-9]+(?:[.-][a-z0-9]+)*(?:;[a-z0-9]+(?:[.-][a-z0-9]+)*)*"

# The date component is either a full ISO date or a bare year: LexML permits
# both, and many older documents in this corpus are known only by year.
_DATE = r"\d{4}(?:-\d{2}-\d{2})?"

# The number may carry a complement ("-A" style, rendered "-1" by the
# reference parser's renderComplemento).
_NUMBER = r"[0-9]+(?:-[0-9]+)?"

LEXML_URN_RE = re.compile(
    rf"^urn:lex:(?P<locality>{_SEGMENT}):(?P<authority>{_SEGMENT})"
    rf":(?P<doc_type>{_SEGMENT}):(?P<date>{_DATE});(?P<number>{_NUMBER})"
    rf"(?:!(?P<fragment>[a-z0-9_]+))?$"
)


@dataclass(frozen=True)
class UrnDate:
    """A date as a URN carries it: full, or year-only when that is all we know.

    Year-only is not a degraded form to be avoided — plan §2.7's older
    documents (``pn_cst_38``, 1980) are cited by year in practice, and the
    reference parser models exactly this with ``Either[Int, Data]``.
    """

    year: int
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        if self.month is None and self.day is not None:
            raise ValueError("a day without a month is not a date")
        # Year 0 is the sentinel :func:`build_urn` emits when a document states
        # no date at all (four of the fifteen samples). It has to be accepted
        # here, or the URNs this module produces would not survive its own
        # parser — `is_unknown` is how callers tell it apart from a real year.
        if not 0 <= self.year <= 9999:
            raise ValueError(f"year out of range: {self.year}")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError(f"month out of range: {self.month}")
        if self.day is not None and not 1 <= self.day <= 31:
            raise ValueError(f"day out of range: {self.day}")

    @property
    def is_full(self) -> bool:
        return self.month is not None and self.day is not None

    @property
    def is_unknown(self) -> bool:
        """True for the year-0 sentinel meaning "the document states no date"."""
        return self.year == 0

    @property
    def urn_repr(self) -> str:
        """``2018-06-07`` when complete, ``1980`` when only the year is known."""
        if self.is_full:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        return f"{self.year:04d}"

    @property
    def iso(self) -> str | None:
        """ISO-8601, or ``None`` if the date is year-only."""
        return self.urn_repr if self.is_full else None

    @classmethod
    def from_string(cls, text: str) -> "UrnDate | None":
        """Parse ``2018-06-07`` or ``2018``. Returns ``None`` if neither."""
        text = text.strip()
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.fullmatch(r"(\d{4})", text)
        if m:
            return cls(int(m.group(1)))
        return None

    def to_dict(self) -> dict[str, int]:
        data = {"year": self.year}
        if self.month is not None:
            data["month"] = self.month
        if self.day is not None:
            data["day"] = self.day
        return data

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "UrnDate":
        return cls(data["year"], data.get("month"), data.get("day"))


@dataclass(frozen=True)
class UrnParts:
    """The result of taking a URN apart. ``build_urn(**parts)`` rebuilds it."""

    locality: str
    authority: str
    doc_type: str
    date: UrnDate
    number: str
    fragment: str | None = None


def slugify_authority(text: str) -> str:
    """Fold arbitrary Portuguese text into a dotted lowercase ASCII slug.

    ``MINISTÉRIO DA FAZENDA`` → ``ministerio.fazenda``. Connective words are
    dropped, matching the observed convention in the reference parser's
    vocabulary (``senado.federal``, ``camara.deputados``, never
    ``camara.dos.deputados``).

    NFKD then ASCII-encoding is the fold: it decomposes ``é`` into ``e`` plus a
    combining acute, and dropping non-ASCII removes the accent while keeping
    the letter.
    """
    folded = unicodedata.normalize("NFKD", text)
    folded = folded.encode("ascii", "ignore").decode("ascii").lower()
    # Hyphens are meaningful inside a name (procuradoria-geral) but the slug
    # convention writes them as dots, like every other word boundary.
    words = re.split(r"[^a-z0-9]+", folded)
    stop = {"da", "de", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na"}
    kept = [w for w in words if w and w not in stop]
    return ".".join(kept)


def build_urn(
    *,
    locality: str = "br",
    authority: str,
    doc_type: str,
    date: UrnDate | None,
    number: str | None,
    fragment: str | None = None,
) -> str:
    """Assemble a LexML URN.

    ``date`` and ``number`` are optional at the call site because plan §4.4's
    corpus contains documents that carry neither (``CARNE_LEAO`` is a service
    description; ``REsp_1306393`` is an acórdão). Rather than raising — which
    would break "every document produces output" long before Cycle 8 — a
    missing date becomes year ``0000`` and a missing number becomes ``0``.
    Both are syntactically valid and obviously sentinel, and
    :attr:`Metadata.complete` is the flag that says so honestly.
    """
    if not authority:
        raise ValueError("authority is required")
    if not doc_type:
        raise ValueError("doc_type is required")
    date_part = date.urn_repr if date is not None else "0000"
    number_part = number if number else "0"
    urn = f"urn:lex:{locality}:{authority}:{doc_type}:{date_part};{number_part}"
    if fragment:
        urn = f"{urn}!{fragment}"
    return urn


def parse_urn(urn: str) -> UrnParts:
    """Take a URN apart. Raises :class:`ValueError` if it does not match."""
    m = LEXML_URN_RE.match(urn.strip())
    if m is None:
        raise ValueError(f"not a LexML URN: {urn!r}")
    date = UrnDate.from_string(m.group("date"))
    if date is None:  # pragma: no cover - the regex guarantees a parseable date
        raise ValueError(f"unparseable date in URN: {urn!r}")
    return UrnParts(
        locality=m.group("locality"),
        authority=m.group("authority"),
        doc_type=m.group("doc_type"),
        date=date,
        number=m.group("number"),
        fragment=m.group("fragment"),
    )


def is_valid_urn(urn: str) -> bool:
    """True when ``urn`` matches the grammar this module emits."""
    return LEXML_URN_RE.match(urn.strip()) is not None
