"""Primitives every emitter shares: inlines, blocks, regions and extraction.

Three groups of things live here.

**Content rendering.** ``Para``, ``ListNode`` and ``Table`` become ``p``,
``ol``/``ul`` and ``table``. Three schema facts, each measured against both
shipped schemas rather than read off the XSD, shape this:

* a hyperlink is ``<a xlink:href="…">``. Plain ``href`` is **rejected** — the
  ``link`` attribute group declares ``xlink:href`` and declares it *required*;
* ``<table>`` carries ``idreq``, so a table without an ``id`` is invalid, while
  ``ol``/``ul`` accept no attributes at all;
* a ``<td>`` takes inline content only (plan §2.2), which is why
  :class:`~..model.nodes.Table` models a cell as inlines and not as paragraphs.

**Regions, not parts** (spec decision D-6, amendment A-5.1). Cycle 3's
``render_front_generico`` / ``render_back_generico`` render the *named parts* —
epigraph, ementa, preamble, formula, signatures. But ``FrontMatter.span`` and
``BackMatter.span`` are contiguous **hulls** (amendment A-3.5), deliberately, so
that the parts partition the document. Measured over the corpus, 40 non-empty
blocks in 6 samples sit inside a hull and inside no named part:
``parecer_93``'s portal stamp, institutional banner and ``NUP:``/
``INTERESSADOS:`` lines; ``pn_cst_38``'s ``De acordo`` and ``Publique-se``
*between* its two signature blocks; ``par_cosit_26``'s ``Nota Normas:``
disclaimer. An emitter that renders parts loses all 40 and fails the
conservation invariant. :func:`front_region` and :func:`back_region` therefore
walk the hull in document order and emit every unclaimed run as well, reusing
Cycle 3's :func:`~..segment.render.agrupamento_block` so there is one
implementation of the element shape rather than two.

**Extraction.** :func:`leaf_texts` is **Rule B** (plan §2.4): text is read from
leaves only. The plan's own XSLT selects ``li[not(ol|ul)]``, which avoids the
double-counting bug but silently drops a parent item's own words; here an
``li``'s text is read *without* descending into a nested list, so nothing is
counted twice and nothing is dropped. ``Bloco nome="nivel"`` is excluded: it is
a structural marker whose value never appeared in the source. So is a
``Caput``'s ``Rotulo``, which repeats its ``Artigo``'s — the reference
convention writes the rótulo twice, the document said it once (A-6.4).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Callable, Iterable, Sequence

from lxml import etree

from ..ingest import Inline, StyledDoc, StyledPara, StyledTable
from ..model.nodes import ListItem, ListNode, Node, Para, Table
from ..refs.protocol import DEFAULT_CONTEXT_URN
from ..segment.model import BackMatter, FrontMatter, Span
from ..segment.render import agrupamento_block

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..refs.protocol import Linker, Reference

__all__ = [
    "LEXML_NS",
    "NSMAP",
    "XLINK_NS",
    "agrupamento",
    "all_ids",
    "back_region",
    "el",
    "front_region",
    "leaf_text",
    "leaf_texts",
    "local_name",
    "render_inlines",
    "render_list",
    "render_node",
    "render_para",
    "render_table",
    "resolve_references",
    "to_xml_string",
    "words",
]

LEXML_NS = "http://www.lexml.gov.br/1.0"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {None: LEXML_NS, "xlink": XLINK_NS}

#: Elements whose whole string value is one leaf of text. The last three are
#: statutory (Cycle 6): they exist only under ``Norma``, so adding them changes
#: nothing the ``generico`` emitters produce — but without them a statutory
#: document's epigraph, ementa and signatures are silently unread, which is a
#: conservation hole no schema can see.
_WHOLE_TEXT_TAGS = (
    "p",
    "td",
    "th",
    "Rotulo",
    "NomeAgrupador",
    "Epigrafe",
    "Ementa",
    "NomePessoa",
    "Cargo",
)

#: ``Bloco`` names that carry source text. ``nivel`` is a marker, not text.
_TEXT_BLOCOS = ("rotulo", "nomeAgrupador")

#: Children an ``li``'s own text stops at.
_LI_STOP = frozenset({"ol", "ul", "p"})

#: Elements whose ``Rotulo`` repeats their parent's rather than adding text.
#: ``Caput`` carries a copy of its ``Artigo``'s rótulo — plan §4.3's snippet
#: does it and the reference parser does it — but the source wrote that rótulo
#: **once**. Counting the copy would report a word the document never said
#: twice, which is the same reasoning that excludes ``Bloco nome="nivel"``
#: (Cycle 6, amendment A-6.4).
_ECHOED_ROTULO_PARENTS = frozenset({"Caput"})


def el(tag: str, **attrs: str) -> etree._Element:
    """A LexML element. Attribute names are plain; ``xlink:href`` is set after."""
    element = etree.Element(f"{{{LEXML_NS}}}{tag}", nsmap=NSMAP)
    for name, value in attrs.items():
        element.set(name, value)
    return element


def local_name(tag: object) -> str:
    """The local part of a possibly-namespaced tag, or ``""`` for a comment."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def to_xml_string(element: etree._Element) -> str:
    """Serialise one document, pretty-printed, with an XML declaration."""
    return etree.tostring(
        element, pretty_print=True, encoding="unicode", xml_declaration=False
    )


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------


def _append_text(parent: etree._Element, text: str) -> None:
    """Add bare text at the current end of ``parent``."""
    if not text:
        return
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def _usable_references(
    references: Sequence["Reference"], length: int
) -> tuple["Reference", ...]:
    """The references that can actually be rendered over a string of ``length``.

    Two filters, both deliberate:

    * a span that does not lie wholly inside the text is **dropped, never
      truncated** — a URN placed over words it was not resolved from is worse
      than no URN, and a truncation would produce exactly that silently;
    * overlapping spans are resolved **first-wins** by ``(start, -end)``, so the
      earliest and then the longest survives. Interleaved markup is impossible
      to express in XML, and picking a winner deterministically is what keeps
      invariant #4 true regardless of the order a backend returned them in.
    """
    candidates = sorted(
        (r for r in references if r.urn and 0 <= r.start < r.end <= length),
        key=lambda r: (r.start, -r.end),
    )
    out: list["Reference"] = []
    reach = 0
    for reference in candidates:
        if reference.start < reach:
            continue
        out.append(reference)
        reach = reference.end
    return tuple(out)


def _split_inlines(
    inlines: Sequence[Inline], references: Sequence["Reference"]
) -> list[tuple[Inline, str | None]]:
    """Pair each run with the URN covering it, splitting runs at boundaries.

    A citation crosses formatting boundaries — ``Lei nº **7.713**`` is three
    runs and one reference — so a run that a span starts or ends inside is cut
    into pieces that each carry their original formatting (A-L.3). The text is
    only ever *partitioned*: concatenating the pieces reproduces the paragraph
    exactly, which is what makes conservation free rather than lucky.
    """
    out: list[tuple[Inline, str | None]] = []
    position = 0
    for inline in inlines:
        start, end = position, position + len(inline.text)
        position = end
        if not inline.text:
            continue
        cuts = {start, end}
        for reference in references:
            for boundary in (reference.start, reference.end):
                if start < boundary < end:
                    cuts.add(boundary)
        edges = sorted(cuts)
        for left, right in zip(edges, edges[1:]):
            piece = replace(inline, text=inline.text[left - start : right - start])
            urn = next(
                (r.urn for r in references if r.start <= left and right <= r.end),
                None,
            )
            out.append((piece, urn))
    return out


def render_inlines(
    parent: etree._Element,
    inlines: Sequence[Inline],
    references: Sequence["Reference"] = (),
) -> None:
    """Render Cycle 1's runs into ``parent``, one nested element per flag.

    Flags nest outermost-first — link, **reference**, bold, italic, superscript,
    subscript — so a bold italic run is ``<b><i>…</i></b>`` and its text appears
    once.

    ``Remissao`` takes its place directly inside ``a`` (A-L.2, and the user's
    2026-09-10 decision). Both orders were measured legal on both schemas and
    both generations, and this one extends the delivered nesting order rather
    than inverting it: the source's own hyperlink stays the outer, verbatim
    fact, and the resolved URN sits inside it. ``CARNE_LEAO`` is the sample
    that makes the question real — its citations arrive *inside* SIJUT
    hyperlinks.

    With ``references=()`` — every caller before Cycle 8e, and every existing
    golden — this is byte-for-byte the Cycle 5 renderer.
    """
    usable = _usable_references(references, sum(len(i.text) for i in inlines))
    if not usable:
        # No reference survived the filters, so this is exactly the delivered
        # Cycle 5 renderer — including its serialisation. Returning through the
        # same code path as before is what makes "a dropped reference changes
        # nothing" true byte-for-byte rather than approximately.
        _render_runs(parent, [(inline, None) for inline in inlines if inline.text])
        return

    _render_runs(parent, _split_inlines(inlines, usable))

    # Suppress lxml's pretty-printer inside this paragraph.
    #
    # `pretty_print=True` indents an element whose `.text` is `None`, and only
    # then. Splitting runs at a reference boundary can leave a `<p>` whose
    # content is *entirely* elements — an all-bold paragraph carrying a
    # citation becomes `<b>…(</b><Remissao><b>…</b></Remissao><b>)</b>` — and
    # the printer would then put each on its own line, injecting indentation
    # that survives reparsing as **real text**.
    #
    # Measured on `CARNE_LEAO`: three spaces appeared inside two paragraphs,
    # turning `adotada (Lei 13709/2018)` into `adotada ( Lei 13709/2018 )`. The
    # document was still valid on both schemas — no schema can see this — and
    # the character-multiset conservation gate is what caught it (A-L.4, and
    # the A-6.4 precedent). Setting `.text` to the empty string adds no
    # character and tells lxml the element has mixed content.
    for element in (parent, *parent.iter(f"{{{LEXML_NS}}}Remissao")):
        if element.text is None and len(element):
            element.text = ""


def _render_runs(
    parent: etree._Element, pieces: Sequence[tuple[Inline, str | None]]
) -> None:
    """Write ``(run, urn)`` pairs into ``parent``, nesting outermost-first."""

    open_urn: str | None = None
    open_href: str | None = None
    remissao: etree._Element | None = None

    for inline, urn in pieces:
        if not inline.text:
            continue

        # A run of consecutive pieces sharing a URN becomes ONE `Remissao`, so
        # a citation that spans formatting is a single reference rather than
        # one per fragment. The href is part of that identity: a citation whose
        # second half sits inside a different hyperlink cannot share one
        # `Remissao` with its first half, because the `a` wraps the `Remissao`.
        if urn != open_urn or (urn is not None and inline.href != open_href):
            remissao = None
            open_urn = urn
            open_href = inline.href
            if urn is not None:
                remissao = el("Remissao")
                remissao.set(f"{{{XLINK_NS}}}href", urn)
                if inline.href:
                    anchor = el("a")
                    anchor.set(f"{{{XLINK_NS}}}href", inline.href)
                    anchor.append(remissao)
                    parent.append(anchor)
                else:
                    parent.append(remissao)

        target = remissao if remissao is not None else parent

        tags: list[str] = []
        if inline.href and remissao is None:
            tags.append("a")
        if inline.bold:
            tags.append("b")
        if inline.italic:
            tags.append("i")
        if inline.sup:
            tags.append("sup")
        if inline.sub:
            tags.append("sub")

        if not tags:
            _append_text(target, inline.text)
            continue

        outer: etree._Element | None = None
        node: etree._Element | None = None
        for tag in tags:
            child = el(tag)
            if tag == "a":
                child.set(f"{{{XLINK_NS}}}href", inline.href or "")
            if node is None:
                outer = child
            else:
                node.append(child)
            node = child
        assert node is not None and outer is not None
        node.text = inline.text
        target.append(outer)


def resolve_references(
    para: Para,
    linker: "Linker | None",
    context_urn: str = DEFAULT_CONTEXT_URN,
) -> tuple["Reference", ...]:
    """Ask ``linker`` about ``para``'s text. Never raises, ``()`` when absent.

    The one place a linker is consulted. A backend that is missing, inert or
    broken is handled here rather than at every call site, which is what lets
    the emitters stay identical whether or not one was configured.
    """
    if linker is None or not getattr(linker, "enabled", True):
        return ()
    text = para.text
    if not text.strip():
        return ()
    try:
        return tuple(linker.find_refs(text, context_urn))
    except Exception:  # pragma: no cover - the protocol forbids this
        # `find_refs` is documented never to raise. If a third-party
        # implementation does anyway, a citation is not worth a failed render.
        return ()


def render_para(
    para: Para, *, references: Sequence["Reference"] = ()
) -> etree._Element | None:
    """``<p>``, carrying ``class`` for any non-default :attr:`Para.kind`.

    The quotation guard's verdict is the corpus's most consequential inference —
    it is what stops ``parecer_93``'s 21 quoted articles being published as the
    parecer's own — so it survives into the artifact rather than staying an
    in-process opinion. ``class`` adds no text and cannot affect conservation.

    ``references`` (A-L.3) are resolved by the caller and are spans over
    :attr:`Para.text`; with none, this is the Cycle 5 renderer unchanged.
    """
    if para.is_empty:
        return None
    element = el("p")
    if para.kind and para.kind != "prose":
        element.set("class", para.kind)
    render_inlines(element, para.inlines, references)
    return element


def _render_item(item: ListItem) -> etree._Element:
    element = el("li")
    render_inlines(element, item.inlines)
    for child in item.children:
        if isinstance(child, ListNode):
            nested = render_list(child)
            if nested is not None:
                element.append(nested)
        else:
            paragraph = render_para(child)
            if paragraph is not None:
                element.append(paragraph)
    return element


def render_list(node: ListNode) -> etree._Element | None:
    """``<ol>`` or ``<ul>``, nested natively — lists need no flattening (§2.2)."""
    if not node.items:
        return None
    element = el("ol" if node.ordered else "ul")
    for item in node.items:
        element.append(_render_item(item))
    return element


def render_table(table: Table, ident: str) -> etree._Element | None:
    """``<table id=…>`` with inline-only cells.

    The ``id`` is not decoration: ``table`` carries ``idreq`` and both schemas
    reject a table without one.
    """
    rows = [row for row in table.rows if row]
    if not rows:
        return None
    element = el("table", id=ident)
    for row in rows:
        tr = el("tr")
        for cell in row:
            td = el("td")
            render_inlines(td, cell)
            tr.append(td)
        element.append(tr)
    return element


def render_node(
    node: Node,
    *,
    table_id: Callable[[], str],
    linker: "Linker | None" = None,
    context_urn: str = DEFAULT_CONTEXT_URN,
):
    """Render any content node, drawing a table id from ``table_id`` when needed.

    The id comes from a callable rather than from an :class:`IdAllocator`
    directly because the reference convention names an annex's tables
    ``anexoN_tabM`` (plan §2.9) while its ``PartePrincipal`` is ``anexoN_pp`` —
    two bases, one allocator.

    ``linker`` defaults to ``None``, which is the whole of A-L.3's guarantee:
    an emitter that does not pass one renders exactly what it rendered before
    Cycle 8e, so the 125 goldens cannot move. References are asked for
    per-paragraph only — a table cell and a list item are left for a later
    cycle, and because the extractors read through ``Remissao`` regardless,
    widening that later moves no golden either.
    """
    if isinstance(node, Para):
        return render_para(
            node, references=resolve_references(node, linker, context_urn)
        )
    if isinstance(node, ListNode):
        return render_list(node)
    if isinstance(node, Table):
        return render_table(node, table_id())
    raise TypeError(f"not a content node: {type(node).__name__}")


def agrupamento(
    nome: str, ident: str, children: Iterable[etree._Element]
) -> etree._Element | None:
    """``<Agrupamento nome=… id=…>``, or ``None`` when it would be empty.

    ``blocksreq`` is ``minOccurs="1"``: an empty ``Agrupamento`` is invalid on
    both schemas, so one is never emitted.
    """
    element = el("Agrupamento", id=ident, nome=nome)
    for child in children:
        if child is not None:
            element.append(child)
    return element if len(element) else None


# --------------------------------------------------------------------------
# Regions
# --------------------------------------------------------------------------


def _block_lines(indices: Sequence[int], doc: StyledDoc) -> list[str]:
    """The non-blank text of ``indices``, one line per block, in order."""
    blocks = {b.index: b for b in doc.blocks}
    lines = []
    for index in indices:
        block = blocks.get(index)
        if isinstance(block, StyledPara) and block.text.strip():
            lines.append(block.text.strip())
    return lines


def _linked_paragraph(
    text: str, linker: "Linker | None", context_urn: str
) -> etree._Element:
    """One ``<p>`` of region text, with any citations it carries resolved.

    The front and back matter are not decoration: measured over the corpus,
    **169 of the 379 references the linker can resolve — 45 % — live here**,
    in 12 of the 15 samples, and two samples (``ad_srf_22``, ``adn_cosit_19``)
    are *nothing but* front and back matter. An ato declaratório's ementa
    citing the Lei it construes is precisely the citation a reader wants, and a
    body-only linker would silently drop it.

    With ``linker=None`` this sets ``.text`` exactly as Cycle 3's
    :func:`~..segment.render.agrupamento_block` does, so the delivered output
    does not move.
    """
    paragraph = el("p")
    references = _text_references(text, linker, context_urn)
    if not references:
        paragraph.text = text
        return paragraph
    render_inlines(paragraph, (Inline(text=text),), references)
    return paragraph


def _text_references(
    text: str, linker: "Linker | None", context_urn: str
) -> tuple["Reference", ...]:
    """:func:`resolve_references` for a bare string rather than a ``Para``.

    The region path and the statutory path both build a ``<p>`` from plain
    text, having no ``Para`` to hand; the guard is identical, and it is here
    rather than duplicated so that "never raises" is one implementation.
    """
    if linker is None or not getattr(linker, "enabled", True) or not text.strip():
        return ()
    try:
        return tuple(linker.find_refs(text, context_urn))
    except Exception:  # pragma: no cover - the protocol forbids this
        return ()


def _region_element(
    nome: str,
    ident: str,
    indices: Sequence[int],
    doc: StyledDoc,
    table_id: Callable[[], str],
    linker: "Linker | None" = None,
    context_urn: str = DEFAULT_CONTEXT_URN,
) -> etree._Element | None:
    """One run of the hull as an ``Agrupamento``, tables included.

    A run is almost always pure text, and then this is exactly Cycle 3's
    :func:`~..segment.render.agrupamento_block` — until a linker is supplied,
    at which point the lines need per-paragraph reference resolution and this
    builds the same shape itself. Without one it still delegates, so there
    remains one implementation of the element shape for the delivered path.

    It is not always pure text: the front matter of ``REsp_1306393`` is
    interrupted by a table, and skipping it would lose 31 words — the very
    failure this module exists to prevent.
    """
    from ..hierarchy.tree import table_node

    blocks = {b.index: b for b in doc.blocks}
    run = [blocks[i] for i in indices if i in blocks]
    if not any(isinstance(b, StyledTable) for b in run):
        lines = _block_lines(indices, doc)
        if not lines:
            return None
        if linker is None:
            return agrupamento_block(nome, ident, lines)
        return agrupamento(
            nome,
            ident,
            [_linked_paragraph(line, linker, context_urn) for line in lines],
        )

    children: list[etree._Element] = []
    for block in run:
        if isinstance(block, StyledTable):
            table = render_table(table_node(block), table_id())
            if table is not None:
                children.append(table)
        elif isinstance(block, StyledPara) and block.text.strip():
            children.append(
                _linked_paragraph(block.text.strip(), linker, context_urn)
            )
    return agrupamento(nome, ident, children)


def _runs(
    hull: Span, claims: Sequence[tuple[str, Span]]
) -> list[tuple[str, list[int]]]:
    """Group the hull's indices into maximal runs by the part that claims them.

    First claim wins, so overlapping spans cannot render a block twice.
    """
    owner: dict[int, str] = {}
    for nome, span in claims:
        for index in span.indices:
            owner.setdefault(index, nome)

    runs: list[tuple[str, list[int]]] = []
    for index in hull.indices:
        nome = owner.get(index, "")
        if runs and runs[-1][0] == nome:
            runs[-1][1].append(index)
        else:
            runs.append((nome, [index]))
    return runs


def _region(
    hull: Span | None,
    claims: Sequence[tuple[str, Span]],
    doc: StyledDoc,
    *,
    residue_nome: str,
    prefix: str,
    token: str,
    start: int,
    table_id: Callable[[], str],
    linker: "Linker | None" = None,
    context_urn: str = DEFAULT_CONTEXT_URN,
) -> tuple[etree._Element, ...]:
    if hull is None:
        return ()
    out: list[etree._Element] = []
    ordinal = start
    for nome, indices in _runs(hull, claims):
        ordinal += 1
        element = _region_element(
            nome or residue_nome,
            f"{prefix}_{token}{ordinal}",
            indices,
            doc,
            table_id,
            linker,
            context_urn,
        )
        if element is None:
            ordinal -= 1
            continue
        out.append(element)
    return tuple(out)


def front_region(
    front: FrontMatter,
    doc: StyledDoc,
    *,
    table_id: Callable[[], str],
    first_index: int = 0,
    prefix: str = "pp1",
    start: int = 0,
    linker: "Linker | None" = None,
    context_urn: str = DEFAULT_CONTEXT_URN,
) -> tuple[etree._Element, ...]:
    """The whole front-matter hull, in document order, nothing left behind.

    Named parts keep the names Cycle 3 gave them, so a segment means the same
    thing whichever route produced it; the blocks between them become
    ``nome="preliminar"``.
    """
    claims = [
        (nome, span)
        for nome, span in (
            ("epigrafe", front.epigraph),
            ("ementa", front.ementa),
            ("preambulo", front.preamble),
            ("formulaPromulgacao", front.enacting_formula),
        )
        if span is not None
    ]
    return _region(
        front.hull(first_index),
        claims,
        doc,
        residue_nome="preliminar",
        prefix=prefix,
        token="agr",
        start=start,
        table_id=table_id,
        linker=linker,
        context_urn=context_urn,
    )


def back_region(
    back: BackMatter,
    doc: StyledDoc,
    *,
    table_id: Callable[[], str],
    prefix: str = "pp1",
    start: int = 0,
    linker: "Linker | None" = None,
    context_urn: str = DEFAULT_CONTEXT_URN,
) -> tuple[etree._Element, ...]:
    """The whole back-matter hull, in document order.

    Signatures are claimed first, so a closing date that overlaps one is not
    emitted twice; everything else in the hull — closing notes, the
    ``De acordo`` and ``Publique-se`` lines that sit between ``pn_cst_38``'s
    two signatures — becomes ``nome="nota"``.
    """
    claims: list[tuple[str, Span]] = [
        ("assinatura", signature.span) for signature in back.signatures
    ]
    if back.local_date is not None:
        claims.append(("localDataFecho", back.local_date))
    return _region(
        back.span,
        claims,
        doc,
        residue_nome="nota",
        prefix=prefix,
        token="agrf",
        start=start,
        table_id=table_id,
        linker=linker,
        context_urn=context_urn,
    )


# --------------------------------------------------------------------------
# Extraction — Rule B
# --------------------------------------------------------------------------


def _own_text(node: etree._Element, stop: frozenset[str]) -> str:
    """``node``'s text, not descending into any child named in ``stop``."""
    parts = [node.text or ""]
    for child in node:
        if local_name(child.tag) not in stop:
            parts.append(_own_text(child, stop))
        parts.append(child.tail or "")
    return "".join(parts)


def leaf_texts(element: etree._Element) -> tuple[str, ...]:
    """Every leaf of text under ``element``, in document order — **Rule B**.

    An ``li``'s own words are read without descending into a nested list, so a
    parent item is counted once and a child item once: neither the duplication
    the plan's §2.4 experiment hit, nor the loss that ``li[not(ol|ul)]`` causes.
    """
    out: list[str] = []
    for node in element.iter():
        tag = local_name(node.tag)
        if tag == "Rotulo" and local_name(
            node.getparent().tag if node.getparent() is not None else ""
        ) in _ECHOED_ROTULO_PARENTS:
            continue
        elif tag in _WHOLE_TEXT_TAGS:
            text = _own_text(node, frozenset())
        elif tag == "li":
            text = _own_text(node, _LI_STOP)
        elif tag == "Bloco" and node.get("nome") in _TEXT_BLOCOS:
            text = _own_text(node, frozenset())
        else:
            continue
        text = " ".join(text.split())
        if text:
            out.append(text)
    return tuple(out)


def leaf_text(element: etree._Element, *, separator: str = " ") -> str:
    """All of :func:`leaf_texts`, joined."""
    return separator.join(leaf_texts(element))


def words(texts: Iterable[str]) -> list[str]:
    """The whitespace-separated words of ``texts`` — the conservation currency.

    A source paragraph may legitimately be rendered as two elements (a rótulo
    ``Bloco`` and the prose that followed it on the same line), so conservation
    is checked as a multiset of words rather than of whole paragraphs.
    """
    out: list[str] = []
    for text in texts:
        out.extend(text.split())
    return out


def all_ids(element: etree._Element) -> tuple[str, ...]:
    """Every ``id`` attribute under ``element``, in document order."""
    return tuple(
        value for node in element.iter() if (value := node.get("id")) is not None
    )
