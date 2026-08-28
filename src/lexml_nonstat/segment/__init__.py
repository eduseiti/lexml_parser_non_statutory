"""Front/back matter segmentation.

Divides a ``StyledDoc`` into front matter, a primary body, back matter and any
annexes, as spans of source-block indices. Nothing is copied and nothing is
discarded, so the conservation invariant (plan §9.2) is checkable by arithmetic.

The order of operations is load-bearing. Annexes are separated **before**
signatures are searched, because ``port_mf_277`` signs at block 5 and its
``ANEXO ÚNICO`` starts at block 6: search the file's tail and the signer is 130
blocks behind the search window, inside the annex.

Labelled-field capture is *not* reimplemented here. Cycle 2 shipped it in
``model/metadata.py`` under the allowlist ratified by amendment A-2.2, and this
package re-exports that result rather than becoming a second source of truth
(amendment A-3.4).
"""

from __future__ import annotations

from ..ingest import StyledDoc
from ..model import Metadata, extract_metadata
from ..profile import DocumentProfile, select_profile
from .backmatter import find_signatures, looks_like_person_name, segment_back
from .frontmatter import (
    EMENTA_LABEL_RE,
    find_ementa,
    find_enacting_formula,
    find_epigraph,
    find_preamble,
    segment_front,
    split_label,
)
from .model import Annex, BackMatter, FrontMatter, Segmentation, Signature, Span
from .render import (
    render_back_generico,
    render_front_generico,
    render_parte_final,
    render_parte_inicial,
)
from .sections import find_annexes, split_body

__all__ = [
    "EMENTA_LABEL_RE",
    "Annex",
    "BackMatter",
    "FrontMatter",
    "Segmentation",
    "Signature",
    "Span",
    "find_annexes",
    "find_ementa",
    "find_enacting_formula",
    "find_epigraph",
    "find_preamble",
    "find_signatures",
    "looks_like_person_name",
    "render_back_generico",
    "render_front_generico",
    "render_parte_final",
    "render_parte_inicial",
    "segment_back",
    "segment_document",
    "segment_front",
    "split_body",
    "split_label",
]


def segment_document(
    doc: StyledDoc,
    *,
    profile: DocumentProfile | None = None,
    metadata: Metadata | None = None,
) -> Segmentation:
    """Segment ``doc`` into front matter, body, back matter and annexes.

    Never raises. A document with no front or back matter — ``CARNE_LEAO`` is
    the corpus's example — yields empty ``FrontMatter`` and ``BackMatter`` and
    a body spanning everything, which is exactly the plan's "no false
    positives" requirement rather than a degraded result.
    """
    if profile is None:
        profile = select_profile(doc)
    if metadata is None:
        metadata = extract_metadata(doc, profile=profile)

    front = segment_front(doc, profile, metadata)

    # Annexes first: they bound the primary body, and `port_mf_277` signs
    # before its annex begins.
    annexes = find_annexes(doc, profile)

    first_index = min((b.index for b in doc.blocks), default=0)
    front_hull = front.hull(first_index)
    front_end = front_hull.end if front_hull is not None else None
    primary_end = (
        annexes[0].span.start - 1
        if annexes
        else (max((b.index for b in doc.blocks), default=-1))
    )
    primary_start = (front_end + 1) if front_end is not None else 0
    primary = (
        Span(primary_start, primary_end) if primary_end >= primary_start else None
    )

    back = segment_back(doc, profile, within=primary)

    back = _extend_back(back, doc, annexes)
    back_span = back.span
    body = split_body(
        doc,
        front_end=front_end,
        back_start=back_span.start if back_span is not None else None,
        annexes=annexes,
    )

    # Conservation (plan §9.2): every block must land in exactly one part.
    # Blocks stranded between parts — `parecer_93`'s portal header stamp and
    # institutional banner above the epigraph, `par_cosit_26`'s trailing
    # `Nota Normas:` note below the signature — belong to the nearest
    # enclosing part rather than to nothing.
    body = _absorb_gaps(doc, front_hull, body, back_span, annexes)

    return Segmentation(
        front=front,
        body=body,
        back=back,
        annexes=annexes,
        source=doc.source,
        profile=profile.name,
        first_index=first_index,
    )


def _extend_back(
    back: BackMatter, doc: StyledDoc, annexes: tuple[Annex, ...]
) -> BackMatter:
    """``back`` with its ``trailing`` span covering any notes below it.

    Several samples append a note after the signature — ``par_cosit_26``'s
    ``Nota Normas:`` disclaimer, ``port_mf_454``'s "originally published
    without an ementa". Those blocks close the document; leaving them below
    the back matter would strand them outside every part.

    Never extended past an annex, which is a separate document.
    """
    span = back.span
    if span is None:
        return back
    last = max((b.index for b in doc.blocks), default=span.end)
    for annex in annexes:
        if annex.span.start > span.end:
            last = min(last, annex.span.start - 1)
    if last <= span.end:
        return back
    from dataclasses import replace

    return replace(back, trailing=Span(span.end + 1, last))


def _absorb_gaps(
    doc: StyledDoc,
    front_hull: Span | None,
    body: Span | None,
    back_span: Span | None,
    annexes: tuple[Annex, ...],
) -> Span | None:
    """Widen ``body`` over blocks that no other part claimed.

    With the front matter taken as a contiguous hull and the back matter
    extended over its trailing notes, the only blocks that can remain
    unclaimed are ones adjacent to the body. Growing the body over them keeps
    ``Segmentation.covered`` a partition of the document: every block in
    exactly one part, which is text conservation (plan §9.2) stated as
    arithmetic.
    """
    indices = sorted(b.index for b in doc.blocks)
    if not indices:
        return body

    claimed: set[int] = set()
    if front_hull is not None:
        claimed.update(front_hull.indices)
    if back_span is not None:
        claimed.update(back_span.indices)
    for annex in annexes:
        claimed.update(annex.span.indices)
    if body is not None:
        claimed.update(body.indices)

    unclaimed = {i for i in indices if i not in claimed}
    if not unclaimed:
        return body

    if body is None:
        run_start = run_end = min(unclaimed)
        while run_end + 1 in unclaimed:
            run_end += 1
        return Span(run_start, run_end)

    start, end = body.start, body.end
    while start - 1 in unclaimed:
        start -= 1
    while end + 1 in unclaimed:
        end += 1
    return Span(start, end)
