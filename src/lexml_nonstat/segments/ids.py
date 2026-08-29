"""The primary path — segmenting a :class:`~..model.document.DocumentModel`.

This walks Cycle 4's ``HierarchyDoc`` directly and composes each section's id
**the way the chosen emitter would**, so the resulting
:attr:`~.model.Segment.urn` resolves against that emitter's output. No XML is
built and none is parsed.

That independence is the point. If the primary path re-used the emitters, an
agreement between it and a reader would only prove that one function agrees
with itself; here the model path and the readers reach the same answer by
genuinely different routes, which is what makes the three-way oracle (A-R.5)
evidence rather than tautology.

The id schemes, and why there are three of them
------------------------------------------------

``generico`` (Cycle 5) numbers body sections in the **same** ``agr`` sequence as
the root-level front-matter regions, so a document with three front regions has
its first body section at ``pp1_agr4``. ``generico-aninhado`` (Cycle 5b) gives
body sections their own ``agh`` sequence starting at 1, and hangs a ``txt``
prose leaf off each. That difference is amendment **A-5b.4**, measured rather
than designed, and it is exactly why :attr:`~.model.Segment.path` exists
alongside the urn.

``norma`` (Cycle 6) is a different grammar again — ``art1``, ``art1_cpt`` — and
amendment **A-6.1** records that both schemas *pattern-constrain* it, so it
could not have been path-composed even if we wanted it to be.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..render.common import LEXML_NS, leaf_texts, local_name
from .model import Segment

__all__ = ["EMITTER_TOKENS", "model_segment_tree"]

#: emitter → (body-section id token, whether body numbering continues the
#: front-region sequence). A-5b.4's two documented notations, in one table.
EMITTER_TOKENS: dict[str, tuple[str, bool]] = {
    "generico": ("agr", True),
    "generico-aninhado": ("agh", False),
}

#: emitter → the ``route`` its segments carry.
#:
#: **The artifact decides, not the router** (spec decision D-3). ``route`` says
#: what shape the document *is*, so that a consumer holding a segment knows
#: whether to expect ``Agrupamento`` or ``Artigo`` — and a ``DocumentoGenerico``
#: is ``generico`` however §4.4 classified the DOCX it came from. §4.2's
#: fallback makes the two genuinely come apart: ``port_mf_277`` is
#: ``route="norma"`` on the model and is nonetheless published flat whenever
#: the statutory render fails its gate, and `RenderedDocument.emitter` (Cycle
#: 6) records exactly that. Reading ``model.route`` here made the model path
#: disagree with its own XML readers on that one sample's five region
#: segments — found by a test-authoring subagent, which reported it as a
#: strict xfail rather than fixing it (the Cycle 6 precedent).
ROUTE_OF_EMITTER: dict[str, str] = {
    "generico": "generico",
    "generico-aninhado": "generico",
    "norma": "norma",
}


def model_segment_tree(model: Any, *, emitter: str = "generico") -> tuple[Segment, ...]:
    """Segments of ``model``, addressed as ``emitter`` would address them."""
    if emitter == "norma":
        return _norma_segments(model)
    if emitter not in EMITTER_TOKENS:
        raise ValueError(
            f"unknown emitter {emitter!r}; expected one of "
            + ", ".join(sorted(EMITTER_TOKENS) + ["norma"])
        )

    token, continues = EMITTER_TOKENS[emitter]
    out: list[Segment] = []

    # The primary document, in the order the emitters write it: front regions,
    # then the body, then back regions. `PartePrincipal`'s children are in
    # document order and the readers report them that way, so a segmenter that
    # emitted the back matter before the body would disagree with its own
    # oracle about reading order.
    document_urn = model.metadata.urn
    front, back = _region_segments(
        model, document_urn, route=ROUTE_OF_EMITTER[emitter]
    )
    out.extend(front)

    # A-5b.4's top-level ordinal offset, taken from the *front* regions only.
    # The back regions use their own `agrf` token and are written after the
    # body, so they shift nothing.
    start = len(front) if continues else 0
    out.extend(
        _tree_segments(
            model.body,
            root="pp1",
            token=token,
            document_urn=document_urn,
            start=start,
            emitter=emitter,
            order_start=len(front),
            preamble_start=len(front),
        )
    )
    # The back regions follow every root-level body child, so their document
    # order position is only known now.
    root_children = sum(1 for s in out if len(s.path) <= 1)
    out.extend(
        replace(segment, order=root_children + offset)
        for offset, segment in enumerate(back)
    )

    # Each annex is its own document (§2.9), with its own id root and URN.
    for annex in model.annexes:
        annex_urn = model.metadata.urn_with_fragment(annex.fragment)
        root = f"{annex.fragment}_pp"
        offset = 0
        if annex.label:
            # The annex's `tituloAnexo` block takes the first `agr` ordinal
            # (A-5.6), in both emitters, so the body starts one later.
            out.append(
                Segment(
                    urn=f"{annex_urn}!{root}_agr1",
                    id=f"{root}_agr1",
                    kind="tituloAnexo",
                    level=0,
                    text=annex.label,
                    route=ROUTE_OF_EMITTER[emitter],
                    order=0,
                    document=annex_urn,
                )
            )
            offset = 1
        out.extend(
            _tree_segments(
                annex.tree,
                root=root,
                token=token,
                document_urn=annex_urn,
                start=offset if continues else 0,
                emitter=emitter,
                order_start=offset,
                preamble_start=offset,
            )
        )

    return tuple(out)


# --------------------------------------------------------------------------
# Regions
# --------------------------------------------------------------------------


def _region_segments(
    model: Any, document_urn: str, *, route: str = "generico"
) -> tuple[list[Segment], list[Segment]]:
    """Front and back regions, as both generico emitters write them.

    Cycle 5's and Cycle 5b's emitters call the very same ``front_region()`` and
    ``back_region()`` on the very same model (A-5.1), and amendment A-5b.4
    measured that the region ids they produce are byte-identical. Rather than
    re-derive the region boundaries here — which would be a second segmenter,
    and the A-3.4 rule forbids that — this asks those functions for the
    elements and reads the ids off them.
    """
    from ..render.common import back_region, front_region

    tables = _TableIds()

    front = front_region(
        model.segmentation.front,
        model.styled,
        table_id=tables.next,
        first_index=model.segmentation.first_index,
        prefix="pp1",
    )
    back = back_region(
        model.segmentation.back,
        model.styled,
        table_id=tables.next,
        prefix="pp1",
    )

    def region(element, order: int) -> Segment:
        ident = element.get("id") or ""
        return Segment(
            urn=f"{document_urn}!{ident}" if document_urn else ident,
            id=ident,
            kind=element.get("nome") or "agrupamento",
            level=0,
            text=" ".join(
                t
                for child in element
                if local_name(child.tag) != "Bloco"
                for t in leaf_texts(child)
            ),
            route=route,
            order=order,
            document=document_urn,
        )

    # `order` is the position among **all** of `PartePrincipal`'s children, in
    # document order, which is what the readers report. The back regions
    # therefore start after the front regions *and* after the body, so their
    # numbering is filled in by the caller, which is the only party that knows
    # how many body children there were.
    front_out = [region(e, order) for order, e in enumerate(front)]
    back_out = [region(e, order) for order, e in enumerate(back)]
    return front_out, back_out


class _TableIds:
    """A table-id source for the region renderers, which require one.

    The ids it issues are never read here — a table lives *inside* a region's
    text, not beside it — but the renderers take a callable and a segmenter
    that passed a lambda returning a constant would issue duplicates into
    output it does not own. This is the smallest honest stand-in.
    """

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"pp1_tab{self._n}"


# --------------------------------------------------------------------------
# Body sections
# --------------------------------------------------------------------------


def _tree_segments(
    tree: Any,
    *,
    root: str,
    token: str,
    document_urn: str,
    start: int,
    emitter: str,
    order_start: int = 0,
    preamble_start: int | None = None,
) -> list[Segment]:
    """One ``HierarchyTree``'s preamble and sections.

    ``preamble_start`` is how many ``agr`` ordinals the regions already
    consumed; it defaults to ``start``, which is right for the flat emitter,
    where the two sequences are one.
    """
    if preamble_start is None:
        preamble_start = start
    out: list[Segment] = []
    ordinal = start
    order = order_start

    if tree.preamble:
        # The body preamble is an `Agrupamento nome="texto"` in *both* emitters
        # (A-5.7), and both draw its ordinal from the **same** allocator the
        # front regions used — so it continues the `agr` sequence even under
        # `generico-aninhado`, where the sections themselves start a fresh
        # `agh` one. Measured: `pn_cst_38`'s preamble is `pp1_agr3` in the
        # nested golden, not `pp1_agr1`.
        ident = f"{root}_agr{preamble_start + 1}"
        out.append(
            Segment(
                urn=f"{document_urn}!{ident}" if document_urn else ident,
                id=ident,
                kind="texto",
                level=0,
                text=" ".join(_node_text(n) for n in tree.preamble).strip(),
                # Reached only by the two generico emitters — `norma` goes
                # through `_norma_segments` — but read from the table anyway,
                # so there is one place that says what an emitter's route is.
                route=ROUTE_OF_EMITTER[emitter],
                order=order,
                document=document_urn,
            )
        )
        order += 1
        if emitter == "generico":
            # The flat emitter's sections share the `agr` sequence the
            # preamble just consumed, so they start one later.
            ordinal += 1

    for index, section in enumerate(tree.sections):
        out.extend(
            _section_segments(
                section,
                parent_id=root,
                parent_ordinal=ordinal + index if emitter == "generico" else index,
                token=token,
                document_urn=document_urn,
                breadcrumb=(),
                path=(),
                child_index=index,
                order=order + index,
                emitter=emitter,
            )
        )
    return out


def _section_segments(
    section: Any,
    *,
    parent_id: str,
    parent_ordinal: int,
    token: str,
    document_urn: str,
    breadcrumb: tuple[str, ...],
    path: tuple[int, ...],
    child_index: int,
    order: int,
    emitter: str,
) -> list[Segment]:
    """One section and its descendants, depth-first, document order."""
    ident = f"{parent_id}_{token}{parent_ordinal + 1}"
    here = path + (child_index + 1,)
    title = " ".join(p for p in (section.label, section.heading) if p)

    own = " ".join(_node_text(n) for n in section.body).strip()
    children_out: list[Segment] = []
    for index, child in enumerate(section.children):
        children_out.extend(
            _section_segments(
                child,
                parent_id=ident,
                parent_ordinal=index,
                token=token,
                document_urn=document_urn,
                breadcrumb=breadcrumb + (title,),
                path=here,
                child_index=index,
                order=index,
                emitter=emitter,
            )
        )

    segment = Segment(
        urn=f"{document_urn}!{ident}" if document_urn else ident,
        id=ident,
        kind=section.kind,
        level=section.level,
        label=section.label,
        heading=section.heading,
        breadcrumb=breadcrumb,
        text=own,
        route=ROUTE_OF_EMITTER[emitter],
        path=here,
        order=order,
        document=document_urn,
        descendant_texts=tuple(c.text for c in children_out if c.text),
    )
    return [segment] + children_out


def _node_text(node: Any) -> str:
    """A content node's text, as the emitters would write it.

    Delegates to the same ``render_node`` + ``leaf_texts`` pair the emitters
    use, so this cannot drift from what actually lands in the XML — which is
    the whole reason the oracle can compare the two.
    """
    from ..render.common import render_node

    counter = _TableIds()
    element = render_node(node, table_id=counter.next)
    if element is None:
        return ""
    return " ".join(leaf_texts(element))


# --------------------------------------------------------------------------
# The statutory route
# --------------------------------------------------------------------------


def _norma_segments(model: Any) -> tuple[Segment, ...]:
    """Segments of a model addressed as the ``norma`` emitter would.

    Built by asking Cycle 6 for the articulation rather than re-deriving it:
    ``build_articulacao`` is where the dispositivo grammar lives, and a second
    implementation of it here would be a second router (spec decision D-3).
    """
    from .api import segments_from_norma_xml
    from ..render.norma import render_norma

    bundle = render_norma(model)
    out: list[Segment] = list(segments_from_norma_xml(bundle.primary))
    for annex in bundle.annexes:
        from .api import _segments_of_document

        out.extend(_segments_of_document(annex))
    return tuple(out)
