"""Shared emitter primitives: inlines, blocks, regions, and Rule B extraction.

Everything in :mod:`lexml_nonstat.render.common` is used by every emitter, so a
defect here is a defect in all three renderings at once. Three groups of claims
are pinned in this module.

**Probed schema facts** (Cycle 5 spec §2). Each row of that table was an
executed validation, and each is re-executed here rather than trusted:

* a hyperlink is ``<a xlink:href="…">``. A plain ``href`` is **rejected by both
  shipped schemas** — the ``link`` attribute group declares ``xlink:href`` and
  declares it required — so :func:`test_href_renders_as_xlink` asserts both the
  presence of the namespaced attribute *and* the absence of the plain one, and
  validates a wrapping document in both directions;
* ``<table>`` carries ``idreq``: a table with no ``id`` is invalid;
* a ``<td>`` takes inline content only, never ``<p>``;
* nested ``ol``/``li``/``ol`` is valid, so lists need no flattening (§2.2).

**Regions, not parts** — spec decision D-6, plan amendment **A-5.1**, and this
cycle's central finding. ``FrontMatter.span`` and ``BackMatter.span`` are
contiguous *hulls* (amendment A-3.5), deliberately, so the parts partition the
document; but Cycle 3's ``render_front_generico`` / ``render_back_generico``
render the *named parts only*. Measured over the corpus, **40 non-empty blocks
in 6 samples** sit inside a hull and inside no named part, and a whole-document
emitter that rendered parts would lose all 40 and fail invariant #2.
:func:`test_front_region_covers_the_hull` and
:func:`test_back_region_covers_the_hull` are the regression: they are arithmetic
over the hull — every word of every non-empty hull block, as a multiset — and
not a list of part names, so an unseen document with an unclaimed run nobody
anticipated is covered by construction rather than by enumeration.

Two witnesses are worth naming because they are the awkward shapes:
``REsp_1306393`` has a **table** inside its front hull (31 words that a
text-only region renderer would drop), and ``pn_cst_38_19801031`` has two
paragraphs — ``De acordo`` and ``Publique-se`` — *between* its two signature
blocks, so the back region cannot be "everything after the last named part".

**Rule B** (plan §2.4). Text is read from leaves only.
:func:`test_leaf_text_does_not_double_count` is the regression for the plan's
own §2.4 experiment: a naive ``//text()`` counts a parent ``li``'s words once
for itself and again as part of its nested list, while the reference XSLT's
``li[not(ol|ul)]`` avoids the duplication by *dropping* the parent's own words.
Neither is acceptable for a conservation invariant that fails on loss **and** on
duplication, so both failure modes are asserted, by name, against the plan's own
example.
"""

from __future__ import annotations

import itertools
from collections import Counter
from typing import Callable

import pytest
from lxml import etree

from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara, StyledTable
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.model.nodes import PARA_KINDS, ListItem, ListNode, Para, Table
from lexml_nonstat.render.common import (
    NSMAP,
    XLINK_NS,
    agrupamento,
    all_ids,
    back_region,
    el,
    front_region,
    leaf_text,
    leaf_texts,
    local_name,
    render_inlines,
    render_list,
    render_node,
    render_para,
    render_table,
    to_xml_string,
    words,
)
from lexml_nonstat.segment import (
    Segmentation,
    render_front_generico,
    segment_document,
)
from lexml_nonstat.validate import validate

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"

#: Every sample in the corpus, by stem — the fifteen documents standing in for
#: the 300+ unseen ones.
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: The sample whose front-matter hull is interrupted by a table (spec §3.2).
FRONT_TABLE = "REsp_1306393"

#: The sample whose back matter has prose *between* two signature blocks.
BETWEEN_SIGNATURES = "pn_cst_38_19801031"

#: ``Agrupamento/@nome`` values ``front_region`` may write: Cycle 3's four named
#: parts, plus the residue name D-6 gives an unclaimed run.
FRONT_NOMES = frozenset(
    {"epigrafe", "ementa", "preambulo", "formulaPromulgacao", "preliminar"}
)

#: Likewise for ``back_region``.
BACK_NOMES = frozenset({"assinatura", "localDataFecho", "nota"})

_CACHE: dict[str, tuple[StyledDoc, Segmentation]] = {}


def load(name: str) -> tuple[StyledDoc, Segmentation]:
    """Cycle 1's golden rather than the DOCX — fast, and it makes a region diff
    impossible to blame on the reader: that would show up in Cycle 1's goldens
    first (the ``test_hierarchy_goldens`` precedent)."""
    if name not in _CACHE:
        doc = StyledDoc.from_json(
            (STYLED_DIR / f"{name}.json").read_text(encoding="utf-8")
        )
        metadata = extract_metadata(doc, filename=f"{name}.docx")
        _CACHE[name] = (doc, segment_document(doc, metadata=metadata))
    return _CACHE[name]


def table_ids(prefix: str = "pp1") -> Callable[[], str]:
    """A fresh ``pp1_tab1, pp1_tab2, …`` supply, as the emitter passes in."""
    counter = itertools.count(1)
    return lambda: f"{prefix}_tab{next(counter)}"


def hull_words(doc: StyledDoc, span) -> list[str]:
    """Every word of every non-empty block of ``span``, in document order.

    Computed straight off the ``StyledDoc`` — not via any renderer — so it is an
    independent statement of what the region *must* contain. A table's words are
    read from its cells' own text, which is where the ``REsp_1306393`` front
    table's 31 words live.
    """
    if span is None:
        return []
    blocks = {b.index: b for b in doc.blocks}
    out: list[str] = []
    for index in span.indices:
        block = blocks.get(index)
        if isinstance(block, StyledPara):
            out.extend(block.text.split())
        elif isinstance(block, StyledTable):
            for row in block.rows:
                for cell in row.cells:
                    out.extend(cell.text.split())
    return out


def region_words(elements) -> list[str]:
    """Every word the region actually emitted, in document order (Rule B)."""
    return [w for element in elements for w in words(leaf_texts(element))]


def wrap(children) -> etree._Element:
    """A complete, Metadado-bearing ``DocumentoGenerico`` around ``children``.

    Built with :func:`el` rather than by string surgery so the root carries the
    ``xlink`` namespace declaration that ``<a xlink:href>`` needs — a fragment
    validated without it fails for the wrong reason.
    """
    root = el("LexML")
    metadado = el("Metadado")
    metadado.append(
        el("Identificacao", URN="urn:lex:br:federal:parecer:2018-12-28;93")
    )
    root.append(metadado)
    generico = el("DocumentoGenerico")
    principal = el("PartePrincipal", id="pp1")
    for child in children:
        principal.append(child)
    generico.append(principal)
    root.append(generico)
    return root


def assert_valid(element: etree._Element, context: str) -> None:
    """Assert a document validates on *both* shipped schemas, quoting the report."""
    report = validate(element, "both")
    assert report.ok, f"{context}\n{report.summary()}\n{to_xml_string(element)[:2000]}"


def tags(element: etree._Element) -> list[str]:
    """Local names of every element under ``element``, itself included."""
    return [local_name(node.tag) for node in element.iter() if local_name(node.tag)]


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------


def test_inline_flags_render() -> None:
    """Each of Cycle 1's four formatting flags becomes its own element.

    All four occur in the corpus (62 bold, 80 italic, 305 superscript runs), and
    Cycle 1 kept them precisely so that a rendering could be faithful rather
    than flattened. The text appears exactly once in each case.
    """
    for flag, tag in (("bold", "b"), ("italic", "i"), ("sup", "sup"), ("sub", "sub")):
        para = render_para(Para(inlines=(Inline("marcado", **{flag: True}),)))
        assert para is not None
        assert tags(para) == ["p", tag], flag
        assert leaf_texts(para) == ("marcado",), flag

    plain = render_para(Para(inlines=(Inline("sem marca"),)))
    assert plain is not None
    assert tags(plain) == ["p"]
    assert plain.text == "sem marca"


def test_href_renders_as_xlink() -> None:
    """A link is ``xlink:href`` — a plain ``href`` is rejected by both schemas.

    This is the probed schema row that most easily regresses, because a plain
    ``href`` is what every other XML dialect uses and it looks right in a diff.
    Three things are asserted: the namespaced attribute is present with the
    right value, the plain one is **absent**, and the difference is real — the
    ``xlink`` document validates and the plain-``href`` document does not.
    """
    para = render_para(
        Para(
            inlines=(
                Inline("veja "),
                Inline("o sítio", href="http://www.planalto.gov.br"),
            )
        )
    )
    assert para is not None

    anchors = [n for n in para.iter() if local_name(n.tag) == "a"]
    assert len(anchors) == 1
    anchor = anchors[0]
    assert anchor.get(f"{{{XLINK_NS}}}href") == "http://www.planalto.gov.br"
    assert anchor.get("href") is None, "a plain href is rejected by both schemas"
    assert anchor.text == "o sítio"

    assert_valid(wrap([para]), "xlink:href must validate")

    # The negative half: the same document with a plain href is rejected, which
    # is what makes the assertion above load-bearing rather than cosmetic.
    plain_para = el("p")
    plain_anchor = el("a")
    plain_anchor.set("href", "http://www.planalto.gov.br")
    plain_anchor.text = "o sítio"
    plain_para.append(plain_anchor)
    assert not validate(wrap([plain_para]), "both").ok, (
        "a plain href unexpectedly validated — the schema fact this test "
        "defends has changed"
    )


def test_combined_flags_nest() -> None:
    """A bold italic run is ``<b><i>…</i></b>``, and its text appears once.

    Rule B's other half: if the flags were rendered as *siblings* the text would
    have to be repeated in each, and conservation would report a duplication.
    """
    para = render_para(
        Para(inlines=(Inline("negrito itálico", bold=True, italic=True),))
    )
    assert para is not None
    assert tags(para) == ["p", "b", "i"]

    bold = para[0]
    assert local_name(bold.tag) == "b"
    assert local_name(bold[0].tag) == "i"
    assert bold[0].text == "negrito itálico"

    assert leaf_texts(para) == ("negrito itálico",)
    assert words(leaf_texts(para)).count("itálico") == 1

    # A link that is also bold nests too, with the anchor outermost so the
    # xlink attribute stays on the element the schema expects it on.
    linked = render_para(
        Para(inlines=(Inline("texto", bold=True, href="http://x.gov.br"),))
    )
    assert linked is not None
    assert tags(linked) == ["p", "a", "b"]
    assert leaf_texts(linked) == ("texto",)


def test_para_class_only_for_non_prose() -> None:
    """``Para.kind`` survives into the XML as ``@class`` — spec Q4.

    ``prose`` is the default and is written as no attribute at all, so the
    common case stays clean; every other ratified kind is emitted, which is what
    lets Cycle 7's round-trip recover the quotation guard's verdict. ``class``
    adds no text, so conservation is untouched either way.
    """
    prose = render_para(Para(inlines=(Inline("Texto comum."),), kind="prose"))
    assert prose is not None
    assert prose.get("class") is None

    for kind in sorted(PARA_KINDS - {"prose"}):
        para = render_para(Para(inlines=(Inline("Texto."),), kind=kind))
        assert para is not None
        assert para.get("class") == kind, kind
        assert_valid(wrap([para]), f"p[@class={kind!r}] must validate")

    # An empty paragraph is not emitted at all: `blocksreq` makes an empty
    # container invalid, and an empty `p` would carry no source text anyway.
    assert render_para(Para(inlines=(Inline("   "),))) is None
    assert render_para(Para()) is None


# ---------------------------------------------------------------------------
# Lists and tables
# ---------------------------------------------------------------------------


def _plan_list() -> ListNode:
    """The plan §2.4 example: ``<li>segundo item<ol><li>subitem</li></ol></li>``."""
    return ListNode(
        ordered=True,
        items=(
            ListItem(inlines=(Inline("primeiro item"),)),
            ListItem(
                inlines=(Inline("segundo item"),),
                children=(
                    ListNode(
                        ordered=True,
                        items=(ListItem(inlines=(Inline("subitem"),)),),
                    ),
                ),
            ),
        ),
    )


def test_nested_list_renders_nested() -> None:
    """Lists nest natively in LexML (§2.2), so they are never flattened.

    The probed fact is that ``ol/li/ol/li`` validates; the corollary the plan
    draws from it is that a nested list needs no synthetic ``Agrupamento`` and
    no renumbering, both of which would fabricate structure (invariant #8).
    """
    element = render_list(_plan_list())
    assert element is not None
    assert local_name(element.tag) == "ol"
    assert tags(element) == ["ol", "li", "li", "ol", "li"]

    outer_items = [n for n in element if local_name(n.tag) == "li"]
    assert len(outer_items) == 2
    nested = [n for n in outer_items[1] if local_name(n.tag) == "ol"]
    assert len(nested) == 1
    assert [n.text for n in nested[0]] == ["subitem"]

    # `ol`/`ul` take no attributes at all — an `ol id="…"` is INVALID.
    assert element.attrib == {}
    assert all_ids(element) == ()

    assert_valid(wrap([element]), "nested ol must validate")

    # `ordered` chooses the element, and an empty list is not emitted.
    unordered = render_list(ListNode(ordered=False, items=(ListItem(inlines=(Inline("a"),)),)))
    assert unordered is not None
    assert local_name(unordered.tag) == "ul"
    assert render_list(ListNode(ordered=True, items=())) is None


def test_leaf_text_does_not_double_count() -> None:
    """**Rule B regression** — plan §2.4, on the plan's own example.

    A parent ``li`` carries its own words *and* a nested list. Two wrong answers
    exist and both are named here so neither can come back:

    * ``//text()`` yields ``"segundo itemsubitem"`` — the parent's words
      concatenated with the child's, and the child's words counted twice once
      the nested ``li`` is visited in its own right. That is duplication, and
      conservation fails on duplication;
    * ``li[not(ol|ul)]`` — the reference XSLT's selector — silently drops
      ``"segundo item"`` entirely. That is loss, and conservation fails on loss.

    The correct answer is the parent's own words once and the child's once.
    """
    element = render_list(_plan_list())
    assert element is not None

    texts = leaf_texts(element)
    assert texts == ("primeiro item", "segundo item", "subitem")

    # Neither failure mode is present, said in the words of the failure.
    assert "segundo itemsubitem" not in texts
    assert not any("segundo itemsubitem" in t for t in texts)
    assert texts.count("subitem") == 1
    assert "segundo item" in texts, "li[not(ol|ul)] would have dropped this"

    counted = Counter(words(texts))
    assert counted["subitem"] == 1
    assert counted["segundo"] == 1
    assert counted["item"] == 2  # 'primeiro item' and 'segundo item', once each

    assert leaf_text(element) == "primeiro item segundo item subitem"

    # Deeper nesting behaves the same way: every level's own words, once.
    three_deep = ListNode(
        ordered=True,
        items=(
            ListItem(
                inlines=(Inline("nível 1"),),
                children=(
                    ListNode(
                        ordered=True,
                        items=(
                            ListItem(
                                inlines=(Inline("nível 2"),),
                                children=(
                                    ListNode(
                                        ordered=True,
                                        items=(
                                            ListItem(inlines=(Inline("nível 3"),)),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    deep = render_list(three_deep)
    assert deep is not None
    assert leaf_texts(deep) == ("nível 1", "nível 2", "nível 3")


def test_table_cells_are_inline_only() -> None:
    """``<td><p>`` is **INVALID**; ``<table>`` without an ``id`` is **INVALID**.

    Both are probed rows of spec §2, and together they are why
    :class:`~lexml_nonstat.model.nodes.Table` models a cell as inlines rather
    than as paragraphs: the restriction lives in the model, so the emitter
    cannot violate it by accident.
    """
    table = Table(
        rows=(
            ((Inline("Súmula"),), (Inline("Enunciado"),)),
            ((Inline("125"),), (Inline("O pagamento", bold=True), Inline(" indevido"))),
        )
    )
    element = render_table(table, "pp1_tab1")
    assert element is not None

    assert local_name(element.tag) == "table"
    assert element.get("id") == "pp1_tab1"
    assert all_ids(element) == ("pp1_tab1",)

    cells = [n for n in element.iter() if local_name(n.tag) == "td"]
    assert len(cells) == 4
    for cell in cells:
        assert not [c for c in cell.iter() if local_name(c.tag) == "p"], (
            "a <p> under <td> is rejected by both schemas"
        )
    assert "p" not in tags(element)

    # Inline formatting inside a cell survives, and its text is read once.
    assert leaf_texts(element) == ("Súmula", "Enunciado", "125", "O pagamento indevido")

    assert_valid(wrap([element]), "table with inline cells must validate")

    # A table with no rows is not emitted, and `render_node` routes each node
    # type to the right renderer, drawing a table id only when it needs one.
    assert render_table(Table(rows=()), "pp1_tab9") is None
    supply = table_ids()
    assert local_name(render_node(Para(inlines=(Inline("t"),)), table_id=supply).tag) == "p"
    routed = render_node(table, table_id=supply)
    assert routed.get("id") == "pp1_tab1", "no id was consumed by the paragraph"


def test_agrupamento_is_never_emitted_empty() -> None:
    """``blocksreq`` is ``minOccurs="1"``: an empty ``Agrupamento`` is INVALID.

    :func:`agrupamento` returns ``None`` rather than an empty element, which is
    how the emitter makes the invalid shape unreachable instead of relying on a
    caller to check.
    """
    assert agrupamento("secao", "pp1_agr1", []) is None
    assert agrupamento("secao", "pp1_agr1", [None]) is None

    filled = agrupamento("secao", "pp1_agr1", [render_para(Para(inlines=(Inline("T"),)))])
    assert filled is not None
    assert filled.get("id") == "pp1_agr1"
    assert filled.get("nome") == "secao"
    assert_valid(wrap([filled]), "Agrupamento with one p must validate")


# ---------------------------------------------------------------------------
# Regions — spec decision D-6 / amendment A-5.1 / the 40-block hole
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_front_region_covers_the_hull(name: str) -> None:
    """**The 40-block regression.** Nothing in the front hull is left behind.

    ``FrontMatter.hull(first_index)`` is the contiguous region the segmentation
    assigns to the front matter, blocks between the named parts included
    (amendment A-3.5). Rendering the parts alone loses those blocks; this asserts
    the *arithmetic*, as a multiset of words over the whole hull, so a run nobody
    anticipated is covered by construction rather than by enumeration.

    ``REsp_1306393``'s front hull contains a table, which a text-only region
    renderer would skip; that sample is in the parametrisation for exactly that
    reason.
    """
    doc, segmentation = load(name)
    hull = segmentation.front.hull(segmentation.first_index)
    elements = front_region(
        segmentation.front,
        doc,
        table_id=table_ids(),
        first_index=segmentation.first_index,
    )

    expected = Counter(hull_words(doc, hull))
    actual = Counter(region_words(elements))

    assert actual == expected, (
        f"{name}: front region does not conserve its hull\n"
        f"  lost   (in hull, not emitted): {sorted((expected - actual).items())[:20]}\n"
        f"  gained (emitted, not in hull): {sorted((actual - expected).items())[:20]}"
    )

    # A hull with content must produce at least one element; an empty front
    # matter must produce none, rather than an empty Agrupamento.
    if expected:
        assert elements, f"{name}: hull has {sum(expected.values())} words, nothing emitted"
    else:
        assert elements == ()


@pytest.mark.parametrize("name", SAMPLES)
def test_back_region_covers_the_hull(name: str) -> None:
    """**The 40-block regression, closing half.** ``BackMatter.span`` likewise.

    ``pn_cst_38_19801031`` is the shape that forces this: its ``De acordo`` and
    ``Publique-se`` lines sit *between* its two signature blocks, so they are
    inside the hull, inside no named part, and unreachable to any renderer that
    walks parts.
    """
    doc, segmentation = load(name)
    elements = back_region(segmentation.back, doc, table_id=table_ids())

    expected = Counter(hull_words(doc, segmentation.back.span))
    actual = Counter(region_words(elements))

    assert actual == expected, (
        f"{name}: back region does not conserve its hull\n"
        f"  lost   (in hull, not emitted): {sorted((expected - actual).items())[:20]}\n"
        f"  gained (emitted, not in hull): {sorted((actual - expected).items())[:20]}"
    )

    if expected:
        assert elements, f"{name}: hull has {sum(expected.values())} words, nothing emitted"
    else:
        assert elements == ()


@pytest.mark.parametrize("name", SAMPLES)
def test_region_agrupamentos_are_document_ordered(name: str) -> None:
    """Regions walk the hull in **document order**, not in part order.

    Cycle 3's part renderers emit a fixed sequence (epigraph, ementa, preamble,
    formula) regardless of where those parts actually sit. A region cannot do
    that: a residue run between two named parts has to be emitted *between*
    them, or the reading order of the finished document would not be the reading
    order of the source. Asserting the emitted word **sequence** equals the
    hull's word sequence is a stronger statement than the multiset equality
    above, and it is what pins the ordering.
    """
    doc, segmentation = load(name)
    supply = table_ids()

    front = front_region(
        segmentation.front,
        doc,
        table_id=supply,
        first_index=segmentation.first_index,
    )
    back = back_region(segmentation.back, doc, table_id=supply)

    assert region_words(front) == hull_words(
        doc, segmentation.front.hull(segmentation.first_index)
    ), f"{name}: front region is out of document order"
    assert region_words(back) == hull_words(
        doc, segmentation.back.span
    ), f"{name}: back region is out of document order"

    # Ids are issued in emission order too, so the id sequence is itself a
    # record of document order.
    assert [e.get("id") for e in front] == [
        f"pp1_agr{n}" for n in range(1, len(front) + 1)
    ]
    assert [e.get("id") for e in back] == [
        f"pp1_agrf{n}" for n in range(1, len(back) + 1)
    ]


@pytest.mark.parametrize("name", SAMPLES)
def test_region_nomes_come_from_the_vocabulary(name: str) -> None:
    """Every region ``@nome`` is a name some other layer already understands.

    The named parts keep the names Cycle 3 gave them, so a segment means the
    same thing whichever route produced it; and an unclaimed run is named
    honestly — ``preliminar`` in the front, ``nota`` in the back — rather than
    being given the name of whichever part happens to precede it, which would
    assert a claim about the text that nobody made.
    """
    doc, segmentation = load(name)
    supply = table_ids()
    front = front_region(
        segmentation.front, doc, table_id=supply, first_index=segmentation.first_index
    )
    back = back_region(segmentation.back, doc, table_id=supply)

    front_names = [e.get("nome") for e in front]
    back_names = [e.get("nome") for e in back]

    assert set(front_names) <= FRONT_NOMES, f"{name}: {front_names}"
    assert set(back_names) <= BACK_NOMES, f"{name}: {back_names}"

    # Every element is an Agrupamento carrying both required attributes: `id` is
    # required by `corereq` and a missing one is INVALID.
    for element in (*front, *back):
        assert local_name(element.tag) == "Agrupamento"
        assert element.get("id")
        assert element.get("nome")
        assert len(element), "an empty Agrupamento is INVALID (blocksreq)"


def test_front_residue_is_named_preliminar() -> None:
    """The residue name is real, and it is where the lost blocks went.

    ``parecer_93`` is the worst case in the corpus — 21 unclaimed blocks, 7 of
    them in the front — and its portal stamp and institutional banner precede
    the epigraph, so the first thing the document emits is a residue run.
    """
    doc, segmentation = load("parecer_93_2018_decor_cgu_agu")
    elements = front_region(
        segmentation.front,
        doc,
        table_id=table_ids(),
        first_index=segmentation.first_index,
    )
    names = [e.get("nome") for e in elements]

    assert "preliminar" in names
    assert names[0] == "preliminar", "the portal stamp precedes the epigraph"
    assert "epigrafe" in names and "ementa" in names

    # The residue carries real text, not an empty placeholder.
    residue = [e for e in elements if e.get("nome") == "preliminar"]
    assert all(leaf_texts(e) for e in residue)


def test_back_region_names_the_run_between_two_signatures() -> None:
    """``pn_cst_38``'s ``De acordo`` / ``Publique-se`` — the D-6 witness.

    These lines sit between the two signature blocks. They are back matter by
    position, belong to no named part, and are the seven blocks the measurement
    in spec §3.2 attributes to this sample. The order of the emitted names shows
    the run really is *between* the signatures and not appended after them.
    """
    doc, segmentation = load(BETWEEN_SIGNATURES)
    assert len(segmentation.back.signatures) == 2

    elements = back_region(segmentation.back, doc, table_id=table_ids())
    names = [e.get("nome") for e in elements]

    assert names == ["assinatura", "nota", "assinatura"], names

    middle = leaf_texts(elements[1])
    assert middle, "the run between the signatures is empty"
    joined = " ".join(middle)
    assert "De acordo" in joined or "Publique-se" in joined, joined


def test_front_region_renders_a_table_inside_the_hull() -> None:
    """``REsp_1306393``'s front hull contains a table — spec §3.2's other shape.

    A region renderer that assumed a run is always prose would skip it and lose
    31 words. The table is emitted as a real ``<table>`` with an ``id`` drawn
    from the same supply the body uses, because ``idreq`` makes an id-less table
    invalid wherever it appears.
    """
    doc, segmentation = load(FRONT_TABLE)
    hull = segmentation.front.hull(segmentation.first_index)
    blocks = {b.index: b for b in doc.blocks}
    assert any(isinstance(blocks.get(i), StyledTable) for i in hull.indices), (
        "the premise of this test has changed: no table in the front hull"
    )

    elements = front_region(
        segmentation.front,
        doc,
        table_id=table_ids(),
        first_index=segmentation.first_index,
    )
    tables = [
        node
        for element in elements
        for node in element.iter()
        if local_name(node.tag) == "table"
    ]
    assert len(tables) == 1
    assert tables[0].get("id") == "pp1_tab1"
    assert "p" not in [local_name(n.tag) for n in tables[0].iter()]


@pytest.mark.parametrize("name", SAMPLES)
def test_agrupamento_block_matches_cycle3(name: str) -> None:
    """One implementation of the element shape, not two — amendment A-3.4.

    ``render/common.py`` does not re-implement Cycle 3's ``Agrupamento``: it
    imports the very function. The identity check below says so at the strongest
    possible level, and the byte comparison says it again behaviourally — where
    a front hull is pure prose with no unclaimed run, the region renderer's
    output is *identical* to what Cycle 3 already emits, id for id and byte for
    byte. Where there is a residue run or a table the two legitimately differ,
    and that difference is the whole point of D-6.
    """
    from lexml_nonstat.render import common
    from lexml_nonstat.segment import render as segment_render

    assert common.agrupamento_block is segment_render.agrupamento_block

    doc, segmentation = load(name)
    hull = segmentation.front.hull(segmentation.first_index)
    if hull is None:
        return

    claimed = {i for part in segmentation.front.parts for i in part.indices}
    blocks = {b.index: b for b in doc.blocks}
    prose_only = all(
        not isinstance(blocks.get(i), StyledTable) for i in hull.indices
    )
    residue = [
        i
        for i in hull.indices
        if i not in claimed
        and isinstance(blocks.get(i), StyledPara)
        and blocks[i].text.strip()
    ]
    if residue or not prose_only:
        return

    region = front_region(
        segmentation.front,
        doc,
        table_id=table_ids(),
        first_index=segmentation.first_index,
    )
    cycle3 = render_front_generico(segmentation.front, doc)
    serialise = lambda els: [etree.tostring(e, encoding="unicode") for e in els]
    assert serialise(region) == serialise(cycle3), name


# ---------------------------------------------------------------------------
# Element construction and extraction helpers
# ---------------------------------------------------------------------------


def test_el_declares_both_namespaces() -> None:
    """Every element is in the LexML namespace and carries the ``xlink`` prefix.

    The prefix has to be declared on any element that might come to hold an
    ``<a xlink:href>``, and declaring it uniformly is what lets a fragment be
    serialised and re-parsed on its own without losing the attribute.
    """
    element = el("Agrupamento", id="pp1_agr1", nome="secao")
    assert element.tag == "{http://www.lexml.gov.br/1.0}Agrupamento"
    assert element.nsmap == NSMAP
    assert element.get("id") == "pp1_agr1"
    assert local_name(element.tag) == "Agrupamento"
    assert local_name(None) == ""


def test_leaf_texts_skips_structural_markers() -> None:
    """``Bloco nome="nivel"`` is a marker, not source text — spec D-7.

    ``rotulo`` and ``nomeAgrupador`` carry words the document actually said, so
    they are extracted; ``nivel`` carries a depth this package inferred, and
    counting it as text would make conservation report words the source never
    contained.
    """
    section = el("Agrupamento", id="pp1_agr1", nome="secao")
    for nome, text in (
        ("rotulo", "2."),
        ("nomeAgrupador", "DAS SOCIEDADES COOPERATIVAS"),
        ("nivel", "1"),
    ):
        bloco = el("Bloco", nome=nome)
        bloco.text = text
        section.append(bloco)
    section.append(render_para(Para(inlines=(Inline("Texto introdutório."),))))

    assert leaf_texts(section) == (
        "2.",
        "DAS SOCIEDADES COOPERATIVAS",
        "Texto introdutório.",
    )
    assert "1" not in leaf_texts(section)


def test_words_and_all_ids() -> None:
    """The two small helpers conservation and uniqueness are counted with.

    ``words`` is the conservation currency: a source paragraph may legitimately
    become a rótulo ``Bloco`` plus the prose that followed it on the same line,
    so whole-paragraph comparison would report a false loss where word
    comparison reports none.
    """
    assert words(["um dois", "  três  "]) == ["um", "dois", "três"]
    assert words([]) == []

    container = el("PartePrincipal", id="pp1")
    inner = el("Agrupamento", id="pp1_agr1", nome="secao")
    inner.append(render_table(Table(rows=(((Inline("c"),),),)), "pp1_tab1"))
    container.append(inner)

    assert all_ids(container) == ("pp1", "pp1_agr1", "pp1_tab1")
    assert len(set(all_ids(container))) == 3


def test_render_inlines_drops_empty_runs_and_keeps_order() -> None:
    """Empty runs add no elements; surviving runs keep their source order.

    An empty ``<b/>`` would be a formatting element around nothing — invisible
    in the text, but a difference in the XML that a golden would record and a
    round-trip would have to explain.
    """
    parent = el("p")
    render_inlines(
        parent,
        (Inline(""), Inline("um "), Inline("dois", bold=True), Inline(" três")),
    )
    assert tags(parent) == ["p", "b"]
    assert leaf_texts(parent) == ("um dois três",)
    assert parent.text == "um "
    assert parent[0].tail == " três"


def test_render_node_rejects_a_non_content_node() -> None:
    """A node type the emitter does not know is an error, not silence.

    Dropping it would be a conservation failure that no test could attribute,
    because the text would simply never appear.
    """
    with pytest.raises(TypeError, match="not a content node"):
        render_node("uma string", table_id=table_ids())
