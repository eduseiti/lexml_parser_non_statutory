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
a structural marker whose value never appeared in the source.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

from lxml import etree

from ..ingest import Inline, StyledDoc, StyledPara, StyledTable
from ..model.nodes import ListItem, ListNode, Node, Para, Table
from ..segment.model import BackMatter, FrontMatter, Span
from ..segment.render import agrupamento_block

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
    "to_xml_string",
    "words",
]

LEXML_NS = "http://www.lexml.gov.br/1.0"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {None: LEXML_NS, "xlink": XLINK_NS}

#: Elements whose whole string value is one leaf of text.
_WHOLE_TEXT_TAGS = ("p", "td", "th", "Rotulo", "NomeAgrupador")

#: ``Bloco`` names that carry source text. ``nivel`` is a marker, not text.
_TEXT_BLOCOS = ("rotulo", "nomeAgrupador")

#: Children an ``li``'s own text stops at.
_LI_STOP = frozenset({"ol", "ul", "p"})


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


def render_inlines(parent: etree._Element, inlines: Sequence[Inline]) -> None:
    """Render Cycle 1's runs into ``parent``, one nested element per flag.

    Flags nest outermost-first — link, bold, italic, superscript, subscript —
    so a bold italic run is ``<b><i>…</i></b>`` and its text appears once.
    """
    for inline in inlines:
        if not inline.text:
            continue

        tags: list[str] = []
        if inline.href:
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
            _append_text(parent, inline.text)
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
        parent.append(outer)


def render_para(para: Para) -> etree._Element | None:
    """``<p>``, carrying ``class`` for any non-default :attr:`Para.kind`.

    The quotation guard's verdict is the corpus's most consequential inference —
    it is what stops ``parecer_93``'s 21 quoted articles being published as the
    parecer's own — so it survives into the artifact rather than staying an
    in-process opinion. ``class`` adds no text and cannot affect conservation.
    """
    if para.is_empty:
        return None
    element = el("p")
    if para.kind and para.kind != "prose":
        element.set("class", para.kind)
    render_inlines(element, para.inlines)
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


def render_node(node: Node, *, table_id: Callable[[], str]):
    """Render any content node, drawing a table id from ``table_id`` when needed.

    The id comes from a callable rather than from an :class:`IdAllocator`
    directly because the reference convention names an annex's tables
    ``anexoN_tabM`` (plan §2.9) while its ``PartePrincipal`` is ``anexoN_pp`` —
    two bases, one allocator.
    """
    if isinstance(node, Para):
        return render_para(node)
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


def _region_element(
    nome: str,
    ident: str,
    indices: Sequence[int],
    doc: StyledDoc,
    table_id: Callable[[], str],
) -> etree._Element | None:
    """One run of the hull as an ``Agrupamento``, tables included.

    A run is almost always pure text, and then this is exactly Cycle 3's
    :func:`~..segment.render.agrupamento_block`. It is not always: the front
    matter of ``REsp_1306393`` is interrupted by a table, and skipping it would
    lose 31 words — the very failure this module exists to prevent.
    """
    from ..hierarchy.tree import table_node

    blocks = {b.index: b for b in doc.blocks}
    run = [blocks[i] for i in indices if i in blocks]
    if not any(isinstance(b, StyledTable) for b in run):
        lines = _block_lines(indices, doc)
        return agrupamento_block(nome, ident, lines) if lines else None

    children: list[etree._Element] = []
    for block in run:
        if isinstance(block, StyledTable):
            table = render_table(table_node(block), table_id())
            if table is not None:
                children.append(table)
        elif isinstance(block, StyledPara) and block.text.strip():
            paragraph = el("p")
            paragraph.text = block.text.strip()
            children.append(paragraph)
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
    )


def back_region(
    back: BackMatter,
    doc: StyledDoc,
    *,
    table_id: Callable[[], str],
    prefix: str = "pp1",
    start: int = 0,
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
        if tag in _WHOLE_TEXT_TAGS:
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
