"""The body/annex boundary split.

An annex is a *separate document* in LexML — plan §4.3 emits it as a sibling
``<LexML><Anexo>`` with its own ``!anexoN`` URN fragment — so finding its
boundary is the one structural decision this cycle makes about the body.

The rule is deliberately conservative and **gated per profile**. Applied
ungated to the corpus it fires twice: once correctly, on ``port_mf_277``'s
``ANEXO ÚNICO`` at block 6, and once catastrophically, on ``sumula_stj_125``
block 369 — a bare paragraph reading ``ANEXO`` inside a compilation of court
precedents that has no annex at all. Taking that at face value would amputate
28 blocks into a non-existent annex document.

This is the same trade-off amendment A-2.2 settled for labelled metadata
fields: a missed annex is recoverable, because the text simply stays in the
body, whereas a false annex silently corrupts the output. So genres that do not
carry annexes (``jurisprudencia_generico``, ``servico``) declare no patterns.
"""

from __future__ import annotations

from ..ingest import StyledDoc
from ..profile import DocumentProfile, fold
from .model import Annex, Span

__all__ = ["find_annexes", "split_body"]

#: An annex marker is a short standalone line. A paragraph that merely mentions
#: "Anexo Único" mid-sentence (``port_mf_277`` block 3 does exactly that:
#: "relacionadas no Anexo Único desta Portaria") is prose, not a boundary.
_MAX_MARKER_WORDS = 5


def _is_marker(text: str, profile: DocumentProfile) -> bool:
    """True when ``text`` is a standalone annex heading for this genre."""
    stripped = text.strip()
    if not stripped or len(stripped.split()) > _MAX_MARKER_WORDS:
        return False
    # Folded: the marker is `ANEXO ÚNICO`, and the accent is not a signal.
    return any(r.match(fold(stripped)) for r in profile.annex_res)


def find_annexes(doc: StyledDoc, profile: DocumentProfile) -> tuple[Annex, ...]:
    """Every annex in ``doc``, in document order, numbered from 1.

    Each annex runs from its marker to the block before the next marker, or to
    the end of the document. Returns ``()`` when the profile declares no annex
    patterns, which is how the ``sumula_stj_125`` false positive is avoided.
    """
    # A fast path, not the gate itself: `_is_marker` already returns False
    # against an empty pattern tuple. The real gate is the profile declaring
    # no `annex_res` at all (amendment A-3.3), which is asserted directly in
    # `test_profile_gate_is_load_bearing_on_its_own`.
    if not profile.annex_res:
        return ()

    markers: list[tuple[int, str]] = []
    for para in doc.paragraphs:
        if _is_marker(para.text, profile):
            markers.append((para.index, para.text.strip()))

    if not markers:
        return ()

    last_index = max(b.index for b in doc.blocks)
    annexes: list[Annex] = []
    for ordinal, (start, label) in enumerate(markers, start=1):
        end = markers[ordinal][0] - 1 if ordinal < len(markers) else last_index
        if end < start:
            continue
        annexes.append(Annex(label=label, span=Span(start, end), ordinal=ordinal))
    return tuple(annexes)


def split_body(
    doc: StyledDoc,
    *,
    front_end: int | None = None,
    back_start: int | None = None,
    annexes: tuple[Annex, ...] = (),
) -> Span | None:
    """The primary body: what remains once front, back and annexes are removed.

    ``None`` when nothing remains — a document that is entirely front matter,
    which ``sumula_carf_42`` comes close to being.
    """
    blocks = [b.index for b in doc.blocks]
    if not blocks:
        return None

    start = min(blocks) if front_end is None else front_end + 1
    end = max(blocks)

    # An annex always terminates the primary body, and it can precede the
    # signature: `port_mf_277` signs at block 5, before `ANEXO ÚNICO` at 6.
    if annexes:
        end = min(end, annexes[0].span.start - 1)
    if back_start is not None and back_start <= end:
        end = back_start - 1

    if end < start:
        return None
    return Span(start, end)
