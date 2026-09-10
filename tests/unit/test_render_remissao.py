"""`<Remissao>` emission — the encoding, and what it must never disturb.

Cycle 8e, amendments A-L.2 and A-L.3. Every test here builds its references by
hand: the encoding is a separate question from whether a linker found the
citation, and mixing the two would make a rendering bug look like a linker bug.

The conservation assertion appears in almost every test, in the same shape:
``"".join(element.itertext())`` must equal the paragraph's text. A `Remissao`
wraps text and adds none, so anything else is text damage — and no schema can
see that (A-6.4, where Cycle 6's first statutory render was valid on both
schemas and 29 words short).
"""

from __future__ import annotations

from lxml import etree

from lexml_nonstat.ingest import Inline
from lexml_nonstat.model.nodes import Para
from lexml_nonstat.refs import NullLinker, Reference
from lexml_nonstat.render.common import (
    LEXML_NS,
    XLINK_NS,
    el,
    leaf_texts,
    render_inlines,
    render_para,
    resolve_references,
    to_xml_string,
)

_URN = "urn:lex:br:federal:lei:1988-12-22;7713"


def _para(*inlines: Inline) -> Para:
    return Para(inlines=inlines)


def _text_of(element: etree._Element) -> str:
    return "".join(element.itertext())


def _remissoes(element: etree._Element) -> list[etree._Element]:
    return element.findall(f".//{{{LEXML_NS}}}Remissao")


def _href(element: etree._Element) -> str | None:
    return element.get(f"{{{XLINK_NS}}}href")


# ---------------------------------------------------------------------------
# The encoding
# ---------------------------------------------------------------------------


def test_one_reference_becomes_one_remissao():
    """T-N1 — the shape A-L.2 pins, and the text is untouched."""
    para = _para(Inline(text="A Lei nº 7.713, de 1988 dispõe."))
    element = render_para(
        para, references=(Reference(2, 23, _URN, "Lei nº 7.713, de 1988"),)
    )

    (remissao,) = _remissoes(element)
    assert _href(remissao) == _URN
    assert _text_of(remissao) == "Lei nº 7.713, de 1988"
    assert _text_of(element) == para.text


def test_a_reference_crossing_a_bold_run_stays_one_remissao():
    """T-N2 — Q-6: split the runs, keep the formatting, keep the text.

    ``Lei nº **7.713**, de 1988`` is three runs and **one** citation. The
    `Remissao` wraps the whole span and the inner runs keep their own
    formatting, rather than the citation fragmenting into three references.
    """
    para = _para(
        Inline(text="A Lei nº "),
        Inline(text="7.713", bold=True),
        Inline(text=", de 1988 dispõe."),
    )
    element = render_para(
        para, references=(Reference(2, 23, _URN, "Lei nº 7.713, de 1988"),)
    )

    (remissao,) = _remissoes(element)
    assert _text_of(remissao) == "Lei nº 7.713, de 1988"
    assert remissao.findall(f"{{{LEXML_NS}}}b"), "the bold run survives the split"
    assert _text_of(element) == para.text


def test_a_reference_starting_and_ending_inside_one_run_splits_it():
    """The run is cut into three pieces, and only the middle is wrapped."""
    para = _para(Inline(text="antes Lei nº 7.713 depois", italic=True))
    element = render_para(para, references=(Reference(6, 18, _URN, "Lei nº 7.713"),))

    (remissao,) = _remissoes(element)
    assert _text_of(remissao) == "Lei nº 7.713"
    assert _text_of(element) == para.text
    # Every piece keeps the italic it started with.
    assert len(element.findall(f".//{{{LEXML_NS}}}i")) == 3


def test_a_reference_inside_a_hyperlink_nests_remissao_within_a():
    """T-N3 — Q-2's order, and `CARNE_LEAO` is why the question is real.

    That sample carries citations *inside* SIJUT hyperlinks. Both nesting
    directions were measured legal on both schemas and both generations (matrix
    rows R3/R4); this one keeps the source's own hyperlink as the outer,
    verbatim fact and puts the resolved URN inside it.
    """
    para = _para(
        Inline(text="ver "),
        Inline(text="Lei nº 7.713", href="http://normas.example/ato"),
    )
    element = render_para(para, references=(Reference(4, 16, _URN, "Lei nº 7.713"),))

    anchor = element.find(f"{{{LEXML_NS}}}a")
    assert anchor is not None
    assert _href(anchor) == "http://normas.example/ato"

    (remissao,) = _remissoes(element)
    assert remissao.getparent() is anchor
    assert _href(remissao) == _URN
    assert _text_of(element) == para.text


def test_a_citation_spanning_two_different_hyperlinks_splits_the_remissao():
    """One `Remissao` cannot sit inside two `a` elements, so it becomes two.

    Contrived, but the alternative is markup that cannot be expressed — and
    silently dropping the second half would lose a link the source carried.
    """
    para = _para(
        Inline(text="Lei nº ", href="http://a/"),
        Inline(text="7.713", href="http://b/"),
    )
    element = render_para(para, references=(Reference(0, 12, _URN, "Lei nº 7.713"),))

    assert len(_remissoes(element)) == 2
    assert all(_href(r) == _URN for r in _remissoes(element))
    assert _text_of(element) == para.text


def test_overlapping_references_resolve_first_wins():
    """T-N4 — deterministic, and never interleaved."""
    para = _para(Inline(text="A Lei nº 7.713, de 1988 dispõe."))
    overlapping = (
        Reference(2, 23, _URN, "Lei nº 7.713, de 1988"),
        Reference(8, 30, "urn:lex:br:federal:decreto:1967;200", "7.713, de 1988 dispõe"),
    )

    element = render_para(para, references=overlapping)
    (remissao,) = _remissoes(element)

    assert _href(remissao) == _URN
    assert _text_of(element) == para.text


def test_the_longest_of_two_references_starting_together_wins():
    """`(start, -end)` — the earliest, then the longest."""
    para = _para(Inline(text="Lei nº 7.713, de 1988 dispõe."))
    element = render_para(
        para,
        references=(
            Reference(0, 6, "urn:short", "Lei nº"),
            Reference(0, 21, _URN, "Lei nº 7.713, de 1988"),
        ),
    )

    (remissao,) = _remissoes(element)
    assert _href(remissao) == _URN


def test_the_reference_order_does_not_change_the_output():
    """Invariant #4 — a backend's ordering must not reach the artifact."""
    para = _para(Inline(text="A Lei nº 7.713 e o Decreto nº 200 valem."))
    first = Reference(2, 14, _URN, "Lei nº 7.713")
    second = Reference(19, 33, "urn:lex:br:federal:decreto:1967;200", "Decreto nº 200")

    forward = to_xml_string(render_para(para, references=(first, second)))
    backward = to_xml_string(render_para(para, references=(second, first)))

    assert forward == backward


def test_a_reference_outside_the_text_is_dropped_not_truncated():
    """T-N5 — a URN over words it was not resolved from is worse than none."""
    para = _para(Inline(text="curto"))
    element = render_para(para, references=(Reference(0, 500, _URN, "curto e mais"),))

    assert _remissoes(element) == []
    assert _text_of(element) == para.text


def test_a_reference_with_no_urn_is_dropped():
    """Matrix row R2: a `Remissao` without `xlink:href` is invalid on both
    schemas, so an unresolved citation must stay plain text."""
    para = _para(Inline(text="A Lei nº 7.713 dispõe."))
    element = render_para(para, references=(Reference(2, 14, "", "Lei nº 7.713"),))

    assert _remissoes(element) == []
    assert _text_of(element) == para.text


def test_an_inverted_or_empty_span_is_dropped():
    para = _para(Inline(text="A Lei nº 7.713 dispõe."))

    assert _remissoes(render_para(para, references=(Reference(9, 2, _URN, "x"),))) == []
    assert _remissoes(render_para(para, references=(Reference(5, 5, _URN, ""),))) == []


def test_every_emitted_remissao_carries_a_non_empty_href():
    """T-N7 — the invariant matrix row R2 makes load-bearing."""
    para = _para(
        Inline(text="A "),
        Inline(text="Lei nº 7.713", bold=True),
        Inline(text=" e o Decreto nº 200."),
    )
    element = render_para(
        para,
        references=(
            Reference(2, 14, _URN, "Lei nº 7.713"),
            Reference(19, 33, "urn:lex:br:federal:decreto:1967;200", "Decreto nº 200"),
        ),
    )

    remissoes = _remissoes(element)
    assert len(remissoes) == 2
    assert all(_href(r) for r in remissoes)


def test_adjacent_references_do_not_merge():
    """Two citations that touch stay two `Remissao` elements."""
    para = _para(Inline(text="Lei nº 1Decreto nº 2"))
    element = render_para(
        para,
        references=(
            Reference(0, 8, "urn:a", "Lei nº 1"),
            Reference(8, 20, "urn:b", "Decreto nº 2"),
        ),
    )

    assert [_href(r) for r in _remissoes(element)] == ["urn:a", "urn:b"]
    assert _text_of(element) == para.text


# ---------------------------------------------------------------------------
# What it must not disturb
# ---------------------------------------------------------------------------


def test_no_references_renders_exactly_as_before():
    """T-N6 — the guarantee that keeps 135 goldens byte-identical.

    Every caller before Cycle 8e passes no references, so this is the delivered
    Cycle 5 renderer and must stay byte-for-byte identical to it.
    """
    para = _para(
        Inline(text="A "),
        Inline(text="Lei", bold=True, italic=True),
        Inline(text=" nº 7.713", href="http://x/"),
        Inline(text="2", sup=True),
    )

    with_none = to_xml_string(render_para(para))
    with_empty = to_xml_string(render_para(para, references=()))

    assert with_none == with_empty
    assert "Remissao" not in with_none
    assert '<b><i>Lei</i></b>' in with_none, "the delivered nesting order"
    assert _text_of(render_para(para)) == para.text


def test_a_dropped_reference_leaves_the_paragraph_byte_identical():
    """A reference that cannot be rendered must not perturb the markup at all."""
    para = _para(Inline(text="A Lei nº 7.713.", bold=True))

    plain = to_xml_string(render_para(para))
    dropped = to_xml_string(render_para(para, references=(Reference(0, 900, _URN, "x"),)))

    assert plain == dropped


def test_leaf_texts_reads_through_remissao():
    """T-C1 in miniature — A-L.4, asserted on the character multiset.

    A `Remissao` adds no text, so an extractor that stopped at it would report
    a paragraph short. This is the A-6.4 failure mode and no schema can see it.
    """
    para = _para(Inline(text="A Lei nº 7.713, de 1988 dispõe."))
    linked = el("Agrupamento", id="a1", nome="x")
    linked.append(render_para(para, references=(Reference(2, 23, _URN, "Lei nº 7.713, de 1988"),)))
    plain = el("Agrupamento", id="a1", nome="x")
    plain.append(render_para(para))

    assert leaf_texts(linked) == leaf_texts(plain)


def test_the_class_attribute_survives_linking():
    """The quotation guard's verdict must not be lost to a reference."""
    para = Para(inlines=(Inline(text="A Lei nº 7.713 dispõe."),), kind="quoted")
    element = render_para(para, references=(Reference(2, 14, _URN, "Lei nº 7.713"),))

    assert element.get("class") == "quoted"


def test_an_empty_paragraph_stays_none():
    assert render_para(Para(inlines=(Inline(text="   "),)), references=()) is None


def test_render_inlines_defaults_to_no_references():
    """The signature stays back-compatible for every existing caller."""
    element = el("p")
    render_inlines(element, (Inline(text="A Lei nº 7.713."),))

    assert _remissoes(element) == []
    assert _text_of(element) == "A Lei nº 7.713."


# ---------------------------------------------------------------------------
# resolve_references — the one place a linker is consulted
# ---------------------------------------------------------------------------


def test_resolve_references_without_a_linker_is_empty():
    assert resolve_references(_para(Inline(text="A Lei nº 7.713.")), None) == ()


def test_resolve_references_skips_an_inert_linker():
    """A `NullLinker` is `enabled = False`, so it is not even asked."""
    assert resolve_references(_para(Inline(text="A Lei nº 7.713.")), NullLinker()) == ()


def test_resolve_references_skips_a_blank_paragraph():
    class _Loud:
        name = "loud"
        enabled = True

        def find_refs(self, text, context_urn=""):
            raise AssertionError("a blank paragraph must never be asked")

    assert resolve_references(_para(Inline(text="   ")), _Loud()) == ()


def test_resolve_references_survives_a_linker_that_raises():
    """The protocol forbids it; a third-party implementation might anyway.

    A citation is not worth a failed render — availability over quality, the
    same rule the referee follows.
    """

    class _Broken:
        name = "broken"
        enabled = True

        def find_refs(self, text, context_urn=""):
            raise RuntimeError("backend exploded")

    assert resolve_references(_para(Inline(text="A Lei nº 7.713.")), _Broken()) == ()


def test_resolve_references_passes_the_paragraph_text_and_context():
    seen: list[tuple[str, str]] = []

    class _Recording:
        name = "recording"
        enabled = True

        def find_refs(self, text, context_urn=""):
            seen.append((text, context_urn))
            return ()

    para = _para(Inline(text="A "), Inline(text="Lei nº 7.713", bold=True))
    resolve_references(para, _Recording(), "urn:lex:br:federal:lei:2000-01-01;1")

    assert seen == [("A Lei nº 7.713", "urn:lex:br:federal:lei:2000-01-01;1")]
