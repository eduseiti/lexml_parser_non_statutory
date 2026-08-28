"""The quotation guard — the module this cycle exists to get right.

A parecer quoting the Constitution must not be published as a document whose
`Art. 40` is its own. Plan §2.5 measured the damage a naive rule does: 21 of the
`Art.` matches in ``parecer_93`` are quoted statute, and 4 more in
``par_cosit_26``. Plan §2.5 proposed indentation as the discriminator; the
corpus says the idea is right and the arithmetic is not.

**Amendment A-4.1.** A plain "indent deviates from the modal" test fails on
``parecer_93``, because the quote band is 2908 and the modal body indent is
2909 — one twip *above* it. What actually separates them is where the number
comes from: ordinary body text **inherits** 2909 from the ``Normal`` style,
while every quoted paragraph **declares** its own indent directly. So band
detection has two rules and picks whichever the document supports:

    deviation   values ≥ modal + 300 twips, covering ≥3 paragraphs
    declared    the modal indent is inherited, and a declared indent clusters
                somewhere ≥300 — that cluster is the quote band
    none        neither applies; fall back to the textual cues

Three textual cues run regardless, because ``par_cosit_26`` (plan §2.6) has no
indentation at all: an opening quotation mark, an *omissis* run
(``Art. 52. ..........`` — classic excerpt elision, never an original
enactment), and a citation antecedent — a preceding paragraph that names an
external norm — weighed together with whether the article series is monotonic.

The guard never deletes anything. A paragraph it convicts stays in the tree as
``Para(kind="quote")``; what it loses is only the right to become a
``Section`` (spec decision D-5, plan invariant #2).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ..ingest import StyledPara
from .labels import ARTICLE_RE, fold, looks_like_heading, parse_label, strip_leading_quote

__all__ = [
    "DECLARED_BAND_TOLERANCE",
    "QUOTE_INDENT_MARGIN",
    "QuotationAnalysis",
    "QuoteBands",
    "analyse_quotation",
    "detect_quote_bands",
    "is_monotonic_series",
    "is_omissis",
    "names_external_norm",
    "opens_with_quote",
]

#: How far above the body indent a paragraph must sit to read as a block quote.
#: 300 twips ≈ 0.53 cm — below a centimetre, so a first-line indent never
#: qualifies, and well under the corpus's real quote offsets (2908, 893, 450).
QUOTE_INDENT_MARGIN = 300

#: How far apart two declared indents may be and still be the same band.
#: `parecer_93`'s quote band is not one value but four — 2879, 2880, 2908,
#: 2930 — the spread a hand-dragged Word ruler leaves behind.
DECLARED_BAND_TOLERANCE = 64

#: A band needs this many paragraphs before it is a band rather than an accident.
MIN_BAND_PARAGRAPHS = 3

#: A numeric series may start no higher than this and still be *this* document's
#: numbering. `parecer_93`'s candidates start at 46 — those are a quoted
#: document's paragraph numbers, not the parecer's.
SERIES_START_MAX = 2

#: The largest step a series may take. `2, 3, 16, 18, 52` (par_cosit_26's quoted
#: articles) is what this rejects.
SERIES_MAX_GAP = 3

#: Runs of dots, with or without spaces, optionally bracketed: the omissis mark.
_OMISSIS_RE = re.compile(r"^[\s.·…]*(?:\.\s*){4,}[\s.·…]*$")
_BRACKETED_OMISSIS_RE = re.compile(r"^\s*[\(\[]\s*(?:\.{2,}|…)\s*[\)\]]\s*$")
#: An omissis *inside* a paragraph — `Art. 52. ...........`
_TRAILING_OMISSIS_RE = re.compile(r"(?:\.\s*){6,}\s*$|…\s*$|\(\s*(?:\.{3}|…)\s*\)\s*$")

_OPEN_QUOTE_RE = re.compile(r'^\s*["“\'«]')

#: Words that name an external norm. Deliberately the same vocabulary
#: `labels.py` refuses to read as a label — a paragraph that *cites* Lei nº X is
#: the antecedent of the excerpt that follows it.
_NORM_WORDS = (
    "lei",
    "leis",
    "decreto",
    "decreto-lei",
    "medida provisoria",
    "emenda constitucional",
    "constituicao",
    # The adjective, not only the noun. Plan §2.6's own worked antecedent is
    # `parecer_93` block 342 — "observe-se os dispositivos **constitucionais**
    # pertinentes:" — which the noun alone does not reach, and the citation
    # antecedent is precisely the cue that has to carry indentation-free
    # documents.
    "constitucional",
    "constitucionais",
    "portaria",
    "instrucao normativa",
    "resolucao",
    "ato declaratorio",
    "codigo",
    "estatuto",
    "regimento",
    "sumula",
    "acordao",
)
_NORM_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _NORM_WORDS) + r")\b")
#: `art. 3º da Lei`, `nos termos do artigo 111` — a reference, not a heading.
_ARTICLE_REFERENCE_RE = re.compile(r"\bart(?:igo)?s?\.?\s*\d", re.IGNORECASE)


def opens_with_quote(text: str) -> bool:
    return bool(_OPEN_QUOTE_RE.match(text or ""))


def is_omissis(text: str) -> bool:
    """True for a paragraph that is nothing but an elision mark."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if _BRACKETED_OMISSIS_RE.match(stripped):
        return True
    return bool(_OMISSIS_RE.match(stripped))


def carries_omissis(text: str) -> bool:
    """True when a paragraph *ends* in an elision — ``Art. 52. .........``.

    Plan §2.6: an excerpt is elided; an original enactment is not.
    """
    stripped = (text or "").strip()
    return bool(stripped) and bool(_TRAILING_OMISSIS_RE.search(stripped))


def names_external_norm(text: str) -> bool:
    """True when a paragraph names another norm and hands off to it.

    The trailing colon matters: ``…observe-se os dispositivos constitucionais
    pertinentes:`` is an antecedent, while a passing mention of a law in the
    middle of an argument is not.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    folded = fold(stripped)
    if not (_NORM_RE.search(folded) or _ARTICLE_REFERENCE_RE.search(stripped)):
        return False
    return stripped.endswith((":", "-", "–", "—")) or bool(
        re.search(r'["“]\s*art', stripped, re.IGNORECASE)
    )


def is_monotonic_series(
    values: Sequence[int],
    *,
    start_max: int = SERIES_START_MAX,
    max_gap: int = SERIES_MAX_GAP,
) -> bool:
    """True when ``values`` look like a document numbering itself.

    Three conditions, each earned from the corpus (amendment A-4.2):
    it starts low (a document numbers from its beginning — ``par_cosit_26``
    starts at ``2.`` only because ``1.`` sits in its front matter), it
    increases, and it does not jump. ``(2, 3, 16, 18, 52)`` — ``par_cosit_26``'s
    quoted articles — fails the third; ``(111, 46, 194, 74)`` — ``parecer_93``'s
    numeric noise — fails the second and the first.
    """
    if len(values) < 2:
        return False
    if values[0] > start_max:
        return False
    for previous, current in zip(values, values[1:]):
        if current <= previous or current - previous > max_gap:
            return False
    return True


@dataclass(frozen=True)
class QuoteBands:
    """Which indent values, if any, mark quoted material in this document."""

    body_indent: int = 0
    quote_values: frozenset[int] = frozenset()
    rule: str = "none"
    field: str = "indent_effective"

    def contains(self, para: StyledPara) -> bool:
        if self.rule == "none":
            return False
        value = para.indent_direct if self.field == "indent_direct" else para.indent_effective
        return value is not None and value in self.quote_values

    def to_dict(self) -> dict[str, object]:
        return {
            "body_indent": self.body_indent,
            "rule": self.rule,
            "field": self.field,
            "quote_values": sorted(self.quote_values),
        }


def _non_empty(paras: Iterable[StyledPara]) -> list[StyledPara]:
    return [p for p in paras if not p.is_empty]


def _is_style_heading(para: StyledPara) -> bool:
    """True when Word itself declares the paragraph a heading."""
    if para.outline_level is not None:
        return True
    return bool(para.style) and fold(para.style).startswith(("heading", "titulo"))


def detect_quote_bands(paras: Iterable[StyledPara]) -> QuoteBands:
    """Choose the indent band that marks quotations, or decide there is none."""
    body = _non_empty(paras)
    if len(body) < MIN_BAND_PARAGRAPHS:
        return QuoteBands()

    effective = Counter(p.indent_effective for p in body)
    modal_indent, _ = effective.most_common(1)[0]

    # Rule 1 — deviation. The straightforward case: quoted text is visibly
    # further in than body text.
    high = {v for v in effective if v >= modal_indent + QUOTE_INDENT_MARGIN}
    covered = sum(effective[v] for v in high)
    if covered >= MIN_BAND_PARAGRAPHS:
        return QuoteBands(modal_indent, frozenset(high), "deviation", "indent_effective")

    # Rule 2 — declared vs inherited (A-4.1). The modal indent comes from the
    # style, so paragraphs that override it are the marked ones.
    modal_paras = [p for p in body if p.indent_effective == modal_indent]
    inherited = sum(1 for p in modal_paras if p.indent_direct is None)
    if modal_paras and inherited / len(modal_paras) > 0.5:
        declared = Counter(
            p.indent_direct
            for p in body
            if p.indent_direct is not None and p.indent_direct >= QUOTE_INDENT_MARGIN
        )
        if declared:
            centre, count = declared.most_common(1)[0]
            band = {
                v for v in declared if abs(v - centre) <= DECLARED_BAND_TOLERANCE
            }
            if sum(declared[v] for v in band) >= MIN_BAND_PARAGRAPHS:
                return QuoteBands(
                    modal_indent, frozenset(band), "declared", "indent_direct"
                )

    return QuoteBands(modal_indent, frozenset(), "none", "indent_effective")


@dataclass(frozen=True)
class QuotationAnalysis:
    """Per-document quotation verdicts, keyed by source block index."""

    bands: QuoteBands = field(default_factory=QuoteBands)
    quoted: frozenset[int] = frozenset()
    omissis: frozenset[int] = frozenset()
    citation_antecedent: frozenset[int] = frozenset()
    article_values: tuple[int, ...] = ()
    article_monotonic: bool = False

    def is_quoted(self, index: int) -> bool:
        return index in self.quoted

    @property
    def article_count(self) -> int:
        return len(self.article_values)

    def to_dict(self) -> dict[str, object]:
        return {
            "bands": self.bands.to_dict(),
            "quoted": sorted(self.quoted),
            "omissis": sorted(self.omissis),
            "citation_antecedent": sorted(self.citation_antecedent),
            "article_values": list(self.article_values),
            "article_monotonic": self.article_monotonic,
        }


def analyse_quotation(paras: Sequence[StyledPara]) -> QuotationAnalysis:
    """Decide, for each paragraph, whether it is quoted material.

    Order matters. The article census runs first, because whether *this*
    document's article series is monotonic is what decides how much weight a
    citation antecedent carries — a single cue that is weak alone and decisive
    alongside a series that jumps from 3 to 16.
    """
    body = _non_empty(paras)
    bands = detect_quote_bands(body)

    articles: list[int] = []
    for para in body:
        match = ARTICLE_RE.match(para.text.strip())
        if match:
            articles.append(int(match.group(1)))
    monotonic = is_monotonic_series(articles) if articles else False

    omissis: set[int] = set()
    antecedents: set[int] = set()
    quoted: set[int] = set()

    previous: StyledPara | None = None
    for para in body:
        text = para.text.strip()
        index = para.index
        if _is_style_heading(para):
            # Word's own outline level is an authorial declaration, and indent
            # cannot outvote it. Without this, `sumula_stj_125`'s seven centred
            # `EMENTA` headings (1371/1372 twips against a body of 893) land in
            # the deviation band and the document loses a level of structure.
            previous = para
            continue

        if is_omissis(text) or carries_omissis(text):
            omissis.add(index)

        antecedent = previous is not None and names_external_norm(previous.text)
        if antecedent:
            antecedents.add(index)

        strong = (
            bands.contains(para)
            or opens_with_quote(text)
            or index in omissis
        )
        # A citation antecedent is only half an argument. It convicts when the
        # paragraph it introduces is itself an article and the document's
        # article series does not hold together — plan §2.6's residual case.
        weak = antecedent and bool(ARTICLE_RE.match(text)) and not monotonic
        if strong or weak:
            quoted.add(index)
        previous = para

    # An excerpt does not end at its first line. Once a quotation opens, the
    # paragraphs that follow it inside the same indent band belong to it too —
    # this is what carries `§ 1º` along with the `Art. 40` above it.
    if bands.rule != "none":
        for para in body:
            if bands.contains(para) and not _is_style_heading(para):
                quoted.add(para.index)

    # Plan §2.6's residual case. `par_cosit_26` "resists indentation entirely":
    # its quoted statutes sit at indent 0 alongside the parecer's own prose, so
    # the run has to be found textually — from a convicted article to the next
    # paragraph that carries *this* document's own structure.
    #
    # Gated on `rule == "none"` on purpose. Where a band exists it has already
    # decided the question far more reliably, and letting a textual run loose in
    # `parecer_93` would swallow 400 paragraphs of the parecer's own argument.
    if bands.rule == "none" and articles and not monotonic:
        quoted |= _extend_flat_excerpts(body, quoted)

    return QuotationAnalysis(
        bands=bands,
        quoted=frozenset(quoted),
        omissis=frozenset(omissis),
        citation_antecedent=frozenset(antecedents),
        article_values=tuple(articles),
        article_monotonic=monotonic,
    )


def _extend_flat_excerpts(body: Sequence[StyledPara], quoted: set[int]) -> set[int]:
    """Carry a convicted article's excerpt along to the document's next heading.

    An excerpt does not stop at the article line. ``par_cosit_26`` quotes
    thirty-four consecutive paragraphs — caputs, ``§``, ``I``–``V`` incisos,
    omissis rules and two scanner page-footers — and resumes its own argument at
    ``15.``. So the run opens on a convicted article and closes on the first
    paragraph that carries *this* document's own structure:

    * a numeric or named label (``15.``, ``CAPÍTULO II``) — the document
      speaking again;
    * a roman or alpha label whose remainder reads as a **heading**, which is
      what a chapter title looks like and what a quoted inciso never does
      (``I - o valor atribuído para efeito de pagamento…`` keeps the run open,
      ``VI - CONCLUSÃO`` closes it);
    * a heading Word itself declared.
    """
    closers = {"numeric", "unit", "capitulo", "secao", "subsecao", "titulo", "livro", "parte"}
    extra: set[int] = set()
    inside = False
    for para in body:
        text = para.text.strip()
        if para.index in quoted:
            inside = bool(ARTICLE_RE.match(text)) or is_omissis(text) or inside
            continue
        if not inside:
            continue
        if _is_style_heading(para):
            inside = False
            continue
        label = parse_label(strip_leading_quote(text))
        if label is not None:
            if label.kind in closers:
                inside = False
                continue
            if label.kind in {"roman", "alpha", "compound"} and looks_like_heading(
                label.text
            ):
                inside = False
                continue
        extra.add(para.index)
    return extra
