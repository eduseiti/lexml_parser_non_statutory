"""Segmentation — plan §6.1, the primary path and the three XML readers.

    from lexml_nonstat.segments import segments
    for seg in segments(model):
        print(seg.urn, " | ".join(seg.breadcrumb), seg.text[:60])

**Segmenting the in-process model is the primary path.** The XML readers exist
as the round-trip *oracle* — the reversibility invariant (§9.2) stated as a
comparison rather than as an intention — and, since amendment **A-R.5**, that
oracle is three-way: model, flat XML, nested XML must agree.

Four producers, and why each is separate
-----------------------------------------

:func:`segments_from_model` walks Cycle 4's ``HierarchyDoc`` and composes ids
the way whichever emitter would. It touches no XML at all, so an agreement
between it and a reader is genuinely independent evidence rather than one
function checking its own arithmetic.

:func:`segments_from_flat_xml` reconstructs ancestry from the **id path**
(§2.3, §2.4's Rules A and B): ``pp1_agr4_agr1``'s parent is ``pp1_agr4``. It
reads depth from ``Bloco nome="nivel"`` and the rótulo/heading from the
matching ``Bloco``s.

:func:`segments_from_nested_xml` **parses no ``id``s for structure at all**.
Ancestry is ``AgrupamentoHierarquico`` containment, the rótulo and heading are
native ``Rotulo``/``NomeAgrupador``, and order is ``Bloco nome="ordem"`` — never
sibling position, because §5.4 Constraint 1 forces a section's own prose to be
serialised *after* its subsections, so position is not reading order. It copies
the ``id`` attribute into :attr:`~.model.Segment.id` and nothing more; mutate
every id in the document and every other field comes back identical, which is
asserted by mutating them.

:func:`segments_from_norma_xml` walks statutory elements. It cannot share the
flat reader's ``_``-path arithmetic because amendment **A-6.1** gave dispositivo
ids a schema-constrained grammar of their own — ``art1_cpt`` is a caput, not
"the ``cpt``-th child of ``art1``" in the ``Agrupamento`` sense — so it
dispatches on element name and never on id shape.

Regions are segments
--------------------

Front and back matter are ``Agrupamento`` children of ``PartePrincipal``
carrying real ids and real text (amendment A-5.1). They are emitted as segments
with ``path=()`` and ``level=0``: not part of the body hierarchy, but present,
because "no text is missing from the segments" is only checkable if nothing is
excluded by construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from lxml import etree

from ..render.common import LEXML_NS, leaf_texts, local_name
from .model import Segment

__all__ = [
    "REGION_LEVEL",
    "STATUTORY_KINDS",
    "segments",
    "segments_from_flat_xml",
    "segments_from_model",
    "segments_from_nested_xml",
    "segments_from_norma_xml",
    "parse_document",
]

#: A front/back-matter region's :attr:`~.model.Segment.level`. Zero rather than
#: one: a region is not the first level of the body, it is outside it.
REGION_LEVEL = 0

#: Statutory elements the ``norma`` reader emits a segment for, in the nesting
#: order the schemas fix (amendment A-6.1). ``Caput`` is included because it is
#: what the community stylesheet cites and what carries an article's prose.
STATUTORY_KINDS: tuple[str, ...] = ("Artigo", "Caput", "Paragrafo", "Inciso")

#: Elements that are front/back-matter parts in a ``Norma`` (amendment A-6.2).
_NORMA_REGION_TAGS: tuple[str, ...] = (
    "Epigrafe",
    "Ementa",
    "Preambulo",
    "FormulaPromulgacao",
    "Assinatura",
    "LocalDataFecho",
)

#: ``Bloco/@nome`` the nested emitter writes as markers, never as content.
#:
#: **Belt and braces, and measured to be so.** Cycle 6's
#: :func:`~..render.common.leaf_texts` already reads only ``rotulo`` and
#: ``nomeAgrupador`` ``Bloco``s, so a marker cannot reach a segment's text even
#: with this guard removed — a mutation sweep confirmed it survives, and no
#: test was contrived to kill it. It stays because it states the *intent* at
#: the call site: a reader should not have to know `leaf_texts`' allowlist to
#: see that ``ordem`` is a marker. A guard that duplicates an upstream rule is
#: honest documentation; a guard presented as load-bearing when it is not
#: would be the thing to remove.
_MARKER_BLOCOS = frozenset({"ordem", "vazio", "nivel"})

#: Dispositivos whose ``Rotulo`` echoes their parent's rather than adding text.
#: Exactly Cycle 6's ``_ECHOED_ROTULO_PARENTS``, and for exactly its reason
#: (amendment A-6.4): plan §4.3 and the reference parser both write a
#: ``Caput``'s rótulo a second time, but the source said it once. The segment
#: reports it as :attr:`~.model.Segment.label` — a caption for the reader, not
#: a second occurrence — and conservation counts it once, on the ``Artigo``.
_ECHOED_LABEL_KINDS = frozenset({"caput"})


# --------------------------------------------------------------------------
# A tree of pending segments, shared by all four producers
# --------------------------------------------------------------------------


class _Node:
    """One segment under construction, plus its children.

    The producers differ only in how they *find* the tree; everything after
    that — breadcrumbs, paths, cumulative text — is arithmetic over this, done
    once. A second copy of that arithmetic is a second place for the flat and
    nested readers to disagree for reasons that have nothing to do with the
    emitters.
    """

    __slots__ = ("kind", "label", "heading", "level", "ident", "text", "order",
                 "children", "is_region", "echoed_label")

    def __init__(
        self,
        *,
        kind: str,
        ident: str,
        label: str | None = None,
        heading: str | None = None,
        level: int = 1,
        text: str = "",
        order: int = 0,
        is_region: bool = False,
        echoed_label: bool = False,
    ) -> None:
        self.kind = kind
        self.ident = ident
        self.label = label
        self.heading = heading
        self.level = level
        self.text = text
        self.order = order
        self.is_region = is_region
        self.echoed_label = echoed_label
        self.children: list[_Node] = []

    @property
    def title(self) -> str:
        return " ".join(p for p in (self.label, self.heading) if p)

    def descendant_texts(self) -> tuple[str, ...]:
        out: list[str] = []
        for child in self.children:
            if child.text:
                out.append(child.text)
            out.extend(child.descendant_texts())
        return tuple(out)


def _flatten(
    nodes: Sequence[_Node],
    *,
    document_urn: str,
    route: str,
    breadcrumb: tuple[str, ...] = (),
    path: tuple[int, ...] = (),
) -> list[Segment]:
    """Depth-first, document order — the order a reader reads the document in.

    A region does not consume a path ordinal. It is not part of the body
    hierarchy, and the two emitters disagree about whether it consumes an *id*
    ordinal (A-5b.4) — which is precisely the difference
    :attr:`~.model.Segment.path` exists to normalise away. Counting only body
    sections makes the path the same tuple on both sides by construction, and
    the id difference stays visible in the urn, where it belongs.
    """
    out: list[Segment] = []
    ordinal = 0
    for node in nodes:
        if node.is_region:
            here: tuple[int, ...] = ()
        else:
            ordinal += 1
            here = path + (ordinal,)
        out.append(
            Segment(
                urn=f"{document_urn}!{node.ident}" if document_urn else node.ident,
                id=node.ident,
                kind=node.kind,
                level=REGION_LEVEL if node.is_region else node.level,
                label=node.label,
                echoed_label=node.echoed_label,
                heading=node.heading,
                breadcrumb=breadcrumb,
                text=node.text,
                route=route,
                path=here,
                order=node.order,
                document=document_urn,
                descendant_texts=node.descendant_texts(),
            )
        )
        out.extend(
            _flatten(
                node.children,
                document_urn=document_urn,
                route=route,
                breadcrumb=breadcrumb + (node.title,),
                path=here,
            )
        )
    return out


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def segments(source: Any, *, emitter: str | None = None) -> tuple[Segment, ...]:
    """Hierarchical segments of ``source`` — plan §6.1's one entry point.

    ``source`` may be a :class:`~..model.document.DocumentModel` (the primary
    path), a :class:`~..render.generico.RenderedDocument` bundle, a parsed
    element, an XML string, or a path to an XML file.

    ``emitter`` selects which emitter's ids a *model* should be addressed by;
    it is meaningless for XML, which already has its ids, and passing it there
    is an error rather than a silently ignored argument.
    """
    if _is_model(source):
        return segments_from_model(source, emitter=emitter or "generico")

    if emitter is not None:
        raise ValueError(
            "emitter= selects how a DocumentModel is addressed; XML input "
            "already carries the ids of the emitter that wrote it"
        )

    if hasattr(source, "documents") and hasattr(source, "urn"):
        out: list[Segment] = []
        for document in source.documents:
            out.extend(_segments_of_document(document))
        return tuple(out)

    return _segments_of_document(parse_document(source))


def _is_model(source: Any) -> bool:
    return hasattr(source, "segmentation") and hasattr(source, "hierarchy")


def parse_document(source: Any) -> etree._Element:
    """An ``<LexML>`` element from an element, a string, bytes, or a path."""
    if isinstance(source, etree._ElementTree):
        return source.getroot()
    if hasattr(source, "tag"):
        return source
    if isinstance(source, bytes):
        return etree.fromstring(source)
    if isinstance(source, str) and source.lstrip().startswith("<"):
        return etree.fromstring(source.encode("utf-8"))
    return etree.parse(str(Path(source))).getroot()


def _segments_of_document(document: etree._Element) -> tuple[Segment, ...]:
    """Dispatch on what the document *is*, never on who is said to have made it.

    A file read from disk has no ``RenderedDocument.emitter`` to consult, so
    the reader must be able to tell from the markup — and one dispatch that
    always works beats two that agree only when the caller is careful.
    """
    if _find(document, "Norma") is not None:
        return segments_from_norma_xml(document)
    if _find(document, "AgrupamentoHierarquico") is not None:
        return segments_from_nested_xml(document)
    return segments_from_flat_xml(document)


# --------------------------------------------------------------------------
# XML helpers
# --------------------------------------------------------------------------


def _find(root: etree._Element, tag: str) -> etree._Element | None:
    return root.find(f".//{{{LEXML_NS}}}{tag}")


def _document_urn(document: etree._Element) -> str:
    identificacao = _find(document, "Identificacao")
    if identificacao is None:
        return ""
    return identificacao.get("URN") or ""


def _own_text_of(element: etree._Element, *, skip: Iterable[etree._Element] = ()) -> str:
    """Rule B text of ``element``, with ``skip``'s subtrees removed first.

    Cycle 6's :func:`~..render.common.leaf_texts` is the single authority on
    what text an element carries (amendment A-6.4), so own-text is expressed as
    "all of it, minus the children's" rather than as a second traversal that
    could disagree about, say, a ``Caput``'s echoed rótulo.
    """
    skipped = set(id(s) for s in skip)
    if not skipped:
        return " ".join(leaf_texts(element))

    clone = _copy_without(element, skipped)
    return " ".join(leaf_texts(clone))


def _copy_without(
    element: etree._Element, skipped: set[int]
) -> etree._Element:
    """``element`` with the subtrees in ``skipped`` pruned. Never mutates."""
    clone = etree.Element(element.tag, dict(element.attrib))
    clone.text = element.text
    for child in element:
        if id(child) in skipped:
            # The tail belongs to the parent's flow, not to the pruned child.
            if len(clone):
                clone[-1].tail = (clone[-1].tail or "") + (child.tail or "")
            else:
                clone.text = (clone.text or "") + (child.tail or "")
            continue
        copied = _copy_without(child, skipped)
        copied.tail = child.tail
        clone.append(copied)
    return clone


def _bloco_text(element: etree._Element, nome: str) -> str | None:
    """The direct-child ``Bloco`` with ``@nome``, or ``None``."""
    for child in element:
        if local_name(child.tag) == "Bloco" and child.get("nome") == nome:
            text = " ".join((child.text or "").split())
            return text or None
    return None


def _native_text(element: etree._Element, tag: str) -> str | None:
    for child in element:
        if local_name(child.tag) == tag:
            text = " ".join(("".join(child.itertext())).split())
            return text or None
    return None


# --------------------------------------------------------------------------
# Producer 1 — the model (primary path)
# --------------------------------------------------------------------------


def segments_from_model(model: Any, *, emitter: str = "generico") -> tuple[Segment, ...]:
    """Segment the in-process model — no XML, no serialisation, no reader.

    The ids are composed exactly as ``emitter`` would compose them, so the
    resulting :attr:`~.model.Segment.urn` resolves against that emitter's
    output. That is what makes the three-way oracle a comparison of
    *independent* derivations rather than of one derivation with itself.
    """
    from .ids import model_segment_tree

    return model_segment_tree(model, emitter=emitter)


# --------------------------------------------------------------------------
# Producer 2 — flat XML, ancestry from the id path (Rules A/B)
# --------------------------------------------------------------------------


def segments_from_flat_xml(document: etree._Element) -> tuple[Segment, ...]:
    """Segments of a flat ``generico`` document, ancestry from the id path.

    Rule A says every proper prefix of an id exists as an ``Agrupamento``, and
    that is what makes this reconstruction possible at all. When it does not
    hold — a hand-edited or truncated file — the orphan is attached to the
    nearest ancestor that *does* exist rather than dropped, so a broken input
    loses no text and the gap is visible in the breadcrumb rather than fatal.
    """
    parte = _find(document, "PartePrincipal")
    if parte is None:
        return ()

    document_urn = _document_urn(document)
    by_id: dict[str, _Node] = {}
    roots: list[_Node] = []
    region_ids: set[str] = set()

    order_counters: dict[str, int] = {}

    for element in parte:
        if local_name(element.tag) != "Agrupamento":
            continue
        ident = element.get("id") or ""
        nome = element.get("nome") or "agrupamento"
        nivel = _bloco_text(element, "nivel")

        node = _Node(
            kind=nome,
            ident=ident,
            label=_bloco_text(element, "rotulo"),
            heading=_bloco_text(element, "nomeAgrupador"),
            level=int(nivel) if nivel and nivel.isdigit() else 1,
            text=_region_or_section_text(element),
            is_region=nivel is None,
        )
        if node.is_region:
            region_ids.add(ident)

        parent = _flat_parent(ident, by_id, region_ids)
        key = parent.ident if parent is not None else ""
        node.order = order_counters.get(key, 0)
        order_counters[key] = node.order + 1

        by_id[ident] = node
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)

    return tuple(_flatten(roots, document_urn=document_urn, route="generico"))


def _region_or_section_text(element: etree._Element) -> str:
    """A flat ``Agrupamento``'s own text.

    Everything under it *is* its own — the flat emitter puts a subsection in a
    *sibling* element, not inside this one — so no pruning is needed. The
    ``rotulo``/``nomeAgrupador`` ``Bloco``s are excluded because they are
    reported as :attr:`~.model.Segment.label` and
    :attr:`~.model.Segment.heading`; counting them in ``text`` as well would be
    the duplication Rule B exists to prevent.
    """
    parts: list[str] = []
    for child in element:
        if local_name(child.tag) == "Bloco":
            continue
        parts.extend(leaf_texts(child))
    return " ".join(p for p in parts if p)


def _flat_parent(
    ident: str, by_id: dict[str, _Node], region_ids: set[str]
) -> _Node | None:
    """The nearest already-issued ancestor of ``ident`` by id path.

    ``pp1_agr4_agr1``'s ancestors are ``pp1_agr4`` then ``pp1``. A region is
    never anyone's parent: the flat emitter numbers regions and body sections
    in one ``agr`` sequence, so they are siblings, not a hierarchy (A-5b.4).

    **The region check is unreachable from this corpus, and stays anyway.**
    Measured across all fifteen samples: a region id is a proper prefix of a
    body id **zero** times, because the shared sequence makes them siblings —
    so a mutation removing the check survives. Unlike the ``_MARKER_BLOCOS``
    guard above, though, this one is not redundant *in principle*: nothing in
    the id grammar forbids a region from taking an ordinal that a later body
    section then extends, and this reader is fed files it did not write. The
    corpus stands in for 300+ unseen documents (``CLAUDE.md``), which is
    exactly the situation where "no sample reaches it" is a statement about
    the sample, not about the input space. Found by a test-authoring subagent's
    mutation sweep and kept deliberately.
    """
    parts = ident.split("_")
    for cut in range(len(parts) - 1, 0, -1):
        candidate = "_".join(parts[:cut])
        node = by_id.get(candidate)
        if node is not None and candidate not in region_ids:
            return node
    return None


# --------------------------------------------------------------------------
# Producer 3 — nested XML, native ancestry, no id parsing
# --------------------------------------------------------------------------


def segments_from_nested_xml(document: etree._Element) -> tuple[Segment, ...]:
    """Segments of a nested ``generico-aninhado`` document — plan A-R.5.

    **No ``id`` is parsed for structure.** Ancestry is containment, depth is
    ``count(ancestor::AgrupamentoHierarquico)``, and order is
    ``Bloco nome="ordem"``. The ``id`` attribute is copied into the segment and
    used for nothing else, which is why mutating every id in the document
    changes only :attr:`~.model.Segment.id` and
    :attr:`~.model.Segment.urn`.
    """
    parte = _find(document, "PartePrincipal")
    if parte is None:
        return ()

    document_urn = _document_urn(document)
    roots: list[_Node] = []
    order = 0

    for element in parte:
        tag = local_name(element.tag)
        if tag == "Agrupamento":
            # A root-level `Agrupamento` in nested output is a front/back
            # region or the body preamble — the nested emitter puts every body
            # section in an `AgrupamentoHierarquico` (A-5b.5). This is the one
            # place the two document shapes are told apart by element name
            # rather than by counting.
            node = _Node(
                kind=element.get("nome") or "agrupamento",
                ident=element.get("id") or "",
                text=_region_or_section_text(element),
                order=order,
                is_region=True,
            )
            order += 1
            roots.append(node)
        elif tag == "AgrupamentoHierarquico":
            node = _nested_node(element, level=1)
            # Root-level sections carry an `ordem` that counts among *this*
            # level's sections; at the root they share the sequence with the
            # regions, so the reader restates it in document order.
            node.order = order
            order += 1
            roots.append(node)

    # Root level is **not** reordered. Constraint 1 applies inside an
    # `AgrupamentoHierarquico`, where a section's own prose must follow its
    # subsections; `PartePrincipal`'s own children are written in document
    # order and carry no `ordem` marker, so sorting them by a defaulted 0
    # would interleave the front regions with the first body section — which
    # is what the first run of this reader actually did.
    return tuple(_flatten(roots, document_urn=document_urn, route="generico"))


def _nested_node(element: etree._Element, *, level: int) -> _Node:
    """One ``AgrupamentoHierarquico``, recursively.

    Own text is the prose leaf ``Agrupamento`` — the child sections live in
    their own elements, so pruning is by element type rather than by id.
    """
    children = [
        _nested_node(child, level=level + 1)
        for child in element
        if local_name(child.tag) == "AgrupamentoHierarquico"
    ]
    order = _bloco_text(element, "ordem")

    prose: list[str] = []
    for child in element:
        tag = local_name(child.tag)
        if tag in ("AgrupamentoHierarquico", "Rotulo", "NomeAgrupador"):
            continue
        if tag == "Bloco" and child.get("nome") in _MARKER_BLOCOS:
            continue
        prose.extend(leaf_texts(child))

    node = _Node(
        kind=element.get("nome") or "agrupamento",
        ident=element.get("id") or "",
        label=_native_text(element, "Rotulo"),
        heading=_native_text(element, "NomeAgrupador"),
        level=level,
        text=" ".join(p for p in prose if p),
        order=int(order) if order and order.lstrip("-").isdigit() else 0,
    )
    node.children = _in_reading_order(children)
    return node


def _in_reading_order(nodes: list[_Node]) -> list[_Node]:
    """``nodes`` sorted by their recorded order, ties keeping serialised order.

    Plan §5.4 Constraint 1 makes sibling position meaningless in nested output:
    a section's own prose must be serialised *after* its subsections, so the
    emitter records each child's true document-order index in
    ``Bloco nome="ordem"`` (A-5b.2). A reader that trusted position would put
    the document back together in the wrong order — silently, and only for
    documents that actually nest.
    """
    ordered = sorted(enumerate(nodes), key=lambda pair: (pair[1].order, pair[0]))
    return [node for _, node in ordered]


# --------------------------------------------------------------------------
# Producer 4 — norma XML, statutory elements
# --------------------------------------------------------------------------


def segments_from_norma_xml(document: etree._Element) -> tuple[Segment, ...]:
    """Segments of a statutory ``Norma`` document — the second id grammar.

    Amendment A-6.1 gave dispositivos ids the schemas *pattern-constrain*
    (``art1``, ``art1_cpt``, ``art1_par1u``), so the flat reader's ``_``-path
    arithmetic does not apply: ``art1_cpt``'s parent is ``art1`` by element
    containment, and the id says so only by coincidence of spelling. This
    reader therefore never splits an id.
    """
    norma = _find(document, "Norma")
    if norma is None:
        return ()

    document_urn = _document_urn(document)
    roots: list[_Node] = []
    order = 0

    # `Norma`'s children in document order: `ParteInicial`, `Articulacao`,
    # `ParteFinal`, `Anexos`. Walking them in that order rather than fetching
    # each by name is what keeps the segments in reading order — `ParteFinal`
    # must come after the articulation, not be appended to a list of regions.
    for child in norma:
        tag = local_name(child.tag)
        if tag in ("ParteInicial", "ParteFinal"):
            for region in child.iter():
                if local_name(region.tag) not in _NORMA_REGION_TAGS:
                    continue
                roots.append(
                    _Node(
                        kind=local_name(region.tag)[0].lower()
                        + local_name(region.tag)[1:],
                        ident=region.get("id") or "",
                        text=" ".join(leaf_texts(region)),
                        order=order,
                        is_region=True,
                    )
                )
                order += 1
        elif tag == "Articulacao":
            for position, artigo in enumerate(
                c for c in child if local_name(c.tag) == "Artigo"
            ):
                roots.append(_statutory_node(artigo, level=1, order=position))

    return tuple(_flatten(roots, document_urn=document_urn, route="norma"))


def _statutory_node(element: etree._Element, *, level: int, order: int) -> _Node:
    """One dispositivo and its children, by element containment."""
    children: list[_Node] = []
    position = 0
    for child in element:
        if local_name(child.tag) in STATUTORY_KINDS:
            children.append(_statutory_node(child, level=level + 1, order=position))
            position += 1

    kind = local_name(element.tag).lower()
    node = _Node(
        kind=kind,
        ident=element.get("id") or "",
        label=_native_text(element, "Rotulo"),
        echoed_label=kind in _ECHOED_LABEL_KINDS,
        level=level,
        # The child dispositivos carry their own text, and this element's own
        # `Rotulo` is reported as `label` — counting it here as well would be
        # the duplication Rule B exists to prevent, and it is the same
        # reasoning A-6.4 already applied to a `Caput`'s echoed rótulo.
        text=_own_text_of(
            element,
            skip=[
                c
                for c in element
                if local_name(c.tag) in STATUTORY_KINDS
                or local_name(c.tag) == "Rotulo"
            ],
        ),
        order=order,
    )
    node.children = children
    return node
