"""Front matter: epigraph, ementa, preamble, enacting formula.

Four parts, found in that order, each optional. The corpus makes the
optionality real rather than defensive: ``pn_cst_38`` has an epigraph and
nothing else, ``sumula_carf_42`` has an epigraph and an ementa, and
``CARNE_LEAO`` has none of the four — plan §8's Cycle 3 test list calls that
last case out explicitly as the **no false positives** requirement.

Two traps in the corpus, both pinned by tests:

``adn_cst_10``'s "ementa" is the literal string ``O ato não possui ementa. Ver
íntegra`` — a portal artifact saying the act *has* no ementa. Reading it as one
would put a scraping notice into the document's `<Ementa>` element.

``parecer_93``'s ementa label is separated from its value by ``<w:tab/>``, not
a space: the source reads ``EMENTA:`` then a tab then ``ADMINISTRATIVO.``. Plan
§8 lists this as "``EMENTA:`` with no space after colon still splits".
"""

from __future__ import annotations

import re

from ..ingest import StyledDoc, StyledPara
from ..model import Metadata
from ..profile import DocumentProfile, fold
from .model import FrontMatter, Span

__all__ = [
    "EMENTA_LABEL_RE",
    "find_ementa",
    "find_enacting_formula",
    "find_epigraph",
    "find_preamble",
    "segment_front",
    "split_label",
]

#: How far into a document front matter can possibly reach. `parecer_93` has
#: the deepest — its epigraph is block 3 and its ementa block 9 — but scanning
#: the whole document would let a quoted `EMENTA:` in a transcribed acórdão
#: outvote the real one.
FRONT_WINDOW = 12

#: ``EMENTA:``/``Ementa:``, with or without whitespace before the value. The
#: value group may be empty, which is how the tab-separated `parecer_93` form
#: and the space-separated `par_cosit_26` form share one pattern.
EMENTA_LABEL_RE = re.compile(r"^\s*(ementa)\s*:\s*(.*)$", re.I | re.S)

#: Portal artifacts that announce the *absence* of an ementa. Matched on folded
#: text so accents and case do not matter.
_NO_EMENTA_RES = (
    re.compile(r"^\s*o\s+ato\s+nao\s+possui\s+ementa"),
    re.compile(r"^\s*(este\s+)?ato\s+.*\s+sem\s+(a\s+)?ementa"),
    re.compile(r"^\s*sem\s+ementa\s*\.?\s*$"),
    re.compile(r"^\s*ementa\s+nao\s+(disponivel|informada)"),
)

#: Preamble openers: the sentence naming the authority and its competence.
#: Genre-agnostic on purpose — every issuing authority in the corpus opens the
#: same way, and the 300+ unseen documents will use authorities not sampled here.
_PREAMBLE_RES = (
    re.compile(r"^\s*[oa]\s+[a-zçãéíóúâêô\-]+.*,\s*no\s+uso\b", re.I),
    re.compile(r"^\s*[oa]\s+[a-zçãéíóúâêô\-]+.*,\s*tendo\s+em\s+vista\b", re.I),
    re.compile(r"^\s*[oa]s?\s+(ministr|secretari|procurador|coordenador|advogad)", re.I),
)

#: An ementa is a summary, not a whole argument. `parecer_93`'s runs long, but
#: an unbounded rule would swallow the body of a document whose first paragraph
#: happens to follow the epigraph.
_MAX_EMENTA_BLOCKS = 8


def split_label(text: str) -> tuple[str, str] | None:
    """``"EMENTA: ADMINISTRATIVO."`` → ``("EMENTA", "ADMINISTRATIVO.")``.

    Returns ``None`` when the paragraph carries no ``LABEL:`` prefix. The value
    may be empty: ``EMENTA:`` alone on a line is a valid label whose value is
    the paragraphs that follow.
    """
    match = re.match(r"^\s*([^:\n]{1,40}?)\s*:\s*(.*)$", text, re.S)
    if match is None:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _is_no_ementa_artifact(text: str) -> bool:
    """True for portal notices announcing that there is no ementa."""
    folded = fold(text).strip()
    return any(r.match(folded) for r in _NO_EMENTA_RES)


def _head_paras(doc: StyledDoc, limit: int = FRONT_WINDOW) -> list[StyledPara]:
    """The first ``limit`` non-empty paragraphs, in order."""
    out: list[StyledPara] = []
    for para in doc.paragraphs:
        if para.is_empty:
            continue
        out.append(para)
        if len(out) >= limit:
            break
    return out


def find_epigraph(
    doc: StyledDoc, profile: DocumentProfile, metadata: Metadata | None = None
) -> Span | None:
    """The epigraph's span.

    Cycle 2's ``Metadata.epigraph_index`` is authoritative when metadata was
    supplied — **including when it is ``None``**. That chain is already tested
    across all 15 samples, and re-deciding here would mean two answers to one
    question. ``CARNE_LEAO`` is why the null case matters: it is a web page
    whose title matches the ``servico`` profile's own pattern, so a fallback
    scan promotes a page heading to an epigraph and breaks the cycle's
    "no false positives" requirement.
    """
    if metadata is not None:
        if metadata.epigraph_index is None:
            return None
        return Span(metadata.epigraph_index, metadata.epigraph_index)

    for para in _head_paras(doc, 6):
        folded = fold(para.text).strip()
        if any(r.search(folded) for r in profile.epigraph_res):
            return Span(para.index, para.index)
    return None


def find_ementa(
    doc: StyledDoc,
    profile: DocumentProfile,
    *,
    after: int = -1,
) -> Span | None:
    """The ementa's span, searched after block ``after``.

    Two shapes, in priority order: an explicit ``EMENTA:`` label, or — for
    genres that habitually omit the label — the paragraph immediately following
    the epigraph, when it reads like a summary rather than a preamble.
    """
    if profile.ementa_absent:
        return None

    heads = [p for p in _head_paras(doc) if p.index > after]

    # 1. An explicit label wins wherever it appears in the front window.
    for position, para in enumerate(heads):
        match = EMENTA_LABEL_RE.match(para.text)
        if match is None:
            continue
        if _is_no_ementa_artifact(para.text):
            return None
        end = para.index
        # A labelled ementa may continue over unlabelled continuation lines.
        for following in heads[position + 1 :]:
            if end - para.index + 1 >= _MAX_EMENTA_BLOCKS:
                break
            if split_label(following.text) is not None:
                break
            if any(r.match(following.text) for r in _PREAMBLE_RES):
                break
            if any(r.match(following.text.strip()) for r in profile.enacting_res):
                break
            end = following.index
        return Span(para.index, end)

    # 2. Unlabelled: the line after the epigraph, if it is not something else.
    for para in heads[:1]:
        text = para.text.strip()
        if not text or _is_no_ementa_artifact(text):
            return None
        if any(r.match(text) for r in _PREAMBLE_RES):
            return None
        if any(r.match(text) for r in profile.enacting_res):
            return None
        if any(r.match(text) for r in profile.annex_res):
            return None
        if split_label(text) is not None:
            # A different labelled field (`Assunto:`) is not the ementa.
            label, _ = split_label(text)
            if not fold(label).startswith("ementa"):
                return None
        return Span(para.index, para.index)
    return None


def find_preamble(
    doc: StyledDoc, profile: DocumentProfile, *, after: int = -1
) -> Span | None:
    """The preamble: the authority's opening sentence."""
    for para in _head_paras(doc):
        if para.index <= after:
            continue
        text = para.text.strip()
        if any(r.match(text) for r in _PREAMBLE_RES):
            return Span(para.index, para.index)
        if any(r.search(fold(text)) for r in profile.authority_res):
            return Span(para.index, para.index)
    return None


def find_enacting_formula(
    doc: StyledDoc, profile: DocumentProfile, *, after: int = -1
) -> Span | None:
    """``DECLARA``, ``RESOLVE:`` — the formula opening the dispositive part."""
    if not profile.enacting_res:
        return None
    for para in _head_paras(doc):
        if para.index <= after:
            continue
        text = para.text.strip()
        if any(r.match(text) for r in profile.enacting_res):
            return Span(para.index, para.index)
    return None


def segment_front(
    doc: StyledDoc,
    profile: DocumentProfile,
    metadata: Metadata | None = None,
) -> FrontMatter:
    """All four front-matter parts, each found after the previous one ends.

    Sequential search rather than independent: the parts appear in a fixed
    order in every sample, and searching independently lets the preamble rule
    match a sentence inside the ementa.
    """
    epigraph = find_epigraph(doc, profile, metadata)
    cursor = epigraph.end if epigraph is not None else -1

    ementa = find_ementa(doc, profile, after=cursor)
    if ementa is not None:
        cursor = ementa.end

    preamble = find_preamble(doc, profile, after=cursor)
    if preamble is not None:
        cursor = preamble.end

    enacting = find_enacting_formula(doc, profile, after=cursor)

    fields = metadata.proprietary if metadata is not None else ()
    return FrontMatter(
        epigraph=epigraph,
        ementa=ementa,
        preamble=preamble,
        enacting_formula=enacting,
        fields=tuple(fields),
    )
