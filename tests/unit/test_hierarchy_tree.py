"""Tree assembly, the content-node model, and Cycle 4's share of §9.2.

:mod:`lexml_nonstat.hierarchy.tree` is where inference stops being an opinion
and becomes a document. Everything upstream of it — labels, quotation bands,
evidence weights, depth unification — produces *judgements*; this module turns
those judgements into ``Section``s and content nodes, or throws them away and
returns the span flat. Two of the plan's cross-cutting invariants (§9.2) can
therefore only be checked here, on the finished tree:

* **#2 conservation** — every non-empty source block in the inferred spans
  appears in the tree exactly once, and the text reachable from the tree is,
  character for character, the text of those blocks. Loss and duplication are
  asserted separately because they are different failures: loss amputates the
  document, duplication makes it say a thing twice.
* **#8 no fabrication** — a span whose evidence does not clear
  :data:`~lexml_nonstat.hierarchy.evidence.CONFIDENCE_THRESHOLD` comes back with
  *zero* sections and all of its content in ``preamble``. Degrading to flat is
  only honest if nothing is lost on the way down, so the flat tests assert the
  content survives rather than merely that the sections are gone.

The other two properties this file protects are **determinism** (#4: the same
input yields an equal tree, an equal tree yields identical JSON, and a re-read
of the same ``.docx`` yields identical JSON) and the design decision that keeps
the regression-critical ``parecer_93`` requirement true by construction: on the
generic route an article is prose, never structure (spec decision D-3). That is
asserted over the whole corpus as a property — ``no Section is an article`` —
rather than over the one sample that motivated it, because a rule stated as a
property cannot regress quietly on the 300+ documents nobody has seen.

Two rules the corpus cannot reach are tested synthetically, following the A-1.3
precedent: multi-level Word list nesting (amendment **A-4.6** — no sample has a
contiguous multi-level list) and the below-threshold flat fallback on a document
whose single heading is not a structure.
"""

from __future__ import annotations

import re

import pytest

from lexml_nonstat.hierarchy import (
    CONFIDENCE_THRESHOLD,
    AnnexHierarchy,
    HierarchyDoc,
    HierarchyTree,
    build_tree,
    infer_hierarchy,
    split_inlines,
)
from lexml_nonstat.hierarchy.quotation import quotation_head
from lexml_nonstat.hierarchy.tree import (
    BOUNDARY_RULE_CONFIDENCE,
    _items,
    _list_node,
)
from lexml_nonstat.referee import NullReferee
from lexml_nonstat.referee.protocol import (
    FLAG_THRESHOLD,
    REFEREE_MIN_CONFIDENCE,
    Verdict,
)
from lexml_nonstat.ingest import Inline, StyledPara, StyledTable, read_docx
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.model.nodes import (
    PARA_KINDS,
    SECTION_KINDS,
    Evidence,
    ListItem,
    ListNode,
    Para,
    Section,
    Table,
    node_from_dict,
)
from lexml_nonstat.segment import segment_document

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"

#: The one sample with a multi-norm quotation run (amendments A-Q.1–A-Q.5).
PAR_COSIT_26 = "par_cosit_26_20000629"

#: Every sample in the corpus, by stem. Fifteen documents standing in for the
#: 300+ unseen ones.
SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

#: The two samples whose whole content is front and back matter — ``body`` is
#: ``None`` and the correct tree is the empty one.
NO_BODY: tuple[str, ...] = ("ad_srf_22_19970430", "adn_cosit_19_20001025")

#: The samples whose body evidence does not clear the threshold (spec C-1: this
#: set is *not* ``parecer_93``, which does have three real chapters).
FLAT_BODIES: tuple[str, ...] = (
    "REsp_1306393",
    "ad_pgfn_3_20080918",
    "ad_srf_22_19970430",
    "adn_cosit_19_20001025",
    "port_mf_277_20180607",
    "sumula_carf_42",
)

#: The one sample with a genuine annex (Cycle 3 §3.4, amendment A-R.8).
ANNEXED = "port_mf_277_20180607"

CARNE_LEAO = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"

#: Ground truth, measured and reviewed (R-4): ``(sections, max_depth, flat,
#: confidence)`` for each sample's **body** tree, where ``sections`` counts every
#: section in the tree, descendants included.
MEASURED_SHAPE: dict[str, tuple[int, int, bool, float]] = {
    "REsp_1306393": (0, 0, True, 0.0),
    "ad_pgfn_13_20111220": (2, 1, False, 0.5667),
    "ad_pgfn_3_20080918": (0, 0, True, 0.0),
    "ad_srf_22_19970430": (0, 0, True, 0.0),
    "ad_srf_3_19990107": (3, 1, False, 0.85),
    "adn_cosit_19_20001025": (0, 0, True, 0.0),
    "adn_cst_10_19910417": (3, 2, False, 0.85),
    "par_cosit_26_20000629": (24, 2, False, 0.85),
    "parecer_93_2018_decor_cgu_agu": (3, 1, False, 0.85),
    "pn_cst_38_19801031": (35, 4, False, 0.85),
    "port_mf_277_20180607": (0, 0, True, 0.0),
    "port_mf_454_19770825": (15, 2, False, 0.85),
    CARNE_LEAO: (6, 2, False, 0.9),
    "sumula_carf_42": (0, 0, True, 0.0),
    "sumula_stj_125": (38, 2, False, 0.9),
}


# --------------------------------------------------------------------------
# Fixtures — every sample inferred once for the whole session
# --------------------------------------------------------------------------


def _infer(stem: str):
    """Read, segment and infer one sample the way the pipeline does."""
    path = SAMPLES_DIR / f"{stem}.docx"
    doc = read_docx(path)
    metadata = extract_metadata(doc, filename=path.name)
    segmentation = segment_document(doc, metadata=metadata)
    return doc, segmentation, infer_hierarchy(
        doc, metadata=metadata, segmentation=segmentation
    )


@pytest.fixture(scope="session")
def corpus() -> dict[str, tuple]:
    """``stem -> (StyledDoc, Segmentation, HierarchyDoc)`` for all 15 samples.

    Session-scoped on purpose: ``parecer_93`` and ``sumula_stj_125`` are ~400
    blocks each, and this file walks every sample a dozen times over.
    """
    return {stem: _infer(stem) for stem in SAMPLES}


def test_corpus_is_the_expected_fifteen():
    """Guards every parametrisation below against a sample being added or lost."""
    assert len(SAMPLES) == 15, SAMPLES
    assert ANNEXED in SAMPLES
    assert set(MEASURED_SHAPE) == set(SAMPLES)


# --------------------------------------------------------------------------
# Robustness and shape
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_all_samples_infer(corpus, stem):
    """Inference never raises on a real document, whatever it contains.

    ``infer_hierarchy`` is the pipeline's third stage and has no error return:
    a document it cannot read structure in must come back flat, not blow up.
    A crash here would take a whole document out of a 300-document batch.
    """
    _, _, result = corpus[stem]
    assert isinstance(result, HierarchyDoc)
    assert isinstance(result.body, HierarchyTree)
    assert all(isinstance(a, AnnexHierarchy) for a in result.annexes)


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_measured_shape(corpus, stem):
    """The hand-reviewed ground truth for each body tree (R-4).

    Asserted independently of the ``hierarchy`` goldens, which is the point: a
    golden proves the output has not changed, this proves it was right in the
    first place. A regenerated golden carrying a wrong tree passes forever;
    this table does not.
    """
    _, _, result = corpus[stem]
    tree = result.body
    expected = MEASURED_SHAPE[stem]
    actual = (
        len(list(tree.walk())),
        tree.max_depth,
        tree.flat,
        round(tree.confidence, 4),
    )
    assert actual == expected


@pytest.mark.parametrize("stem", NO_BODY, ids=NO_BODY)
def test_empty_body_yields_empty_tree(corpus, stem):
    """A document that is *all* front and back matter yields the empty tree.

    ``ad_srf_22`` and ``adn_cosit_19`` have ``segmentation.body is None``. The
    honest answer is a tree with nothing in it — not a crash, and not a section
    invented so the output looks populated.
    """
    _, segmentation, result = corpus[stem]
    assert segmentation.body is None
    tree = result.body
    assert tree.sections == ()
    assert tree.preamble == ()
    assert tree.flat is True
    assert tree.is_empty is True
    assert tree.max_depth == 0


def test_build_tree_on_empty_input():
    """``build_tree([])`` is the empty flat tree, not an error.

    Callers (``infer_hierarchy`` itself, and Cycle 6's annex loop) hand it
    whatever a span resolves to, and an absent span resolves to nothing.
    """
    tree = build_tree([])
    assert tree.is_empty is True
    assert tree.flat is True
    assert tree.sections == ()
    assert tree.preamble == ()
    assert tree.confidence == 0.0


# --------------------------------------------------------------------------
# Conservation — plan §9.2 invariant #2
# --------------------------------------------------------------------------


def _expected_indices(doc, segmentation) -> set[int]:
    """Every source block index the trees are accountable for.

    The invariant, stated exactly: **every non-empty block index in the body
    span, plus every non-empty block index in each annex span except the
    annex's first block.** That exception is not a fudge — the annex's marker
    paragraph (``ANEXO ÚNICO``) is the annex's *title*, carried on
    ``AnnexHierarchy.label`` and rendered by Cycle 6 as the annex's heading.
    Leaving it in the span would make the annex the first section of itself.
    """
    blocks = {b.index: b for b in doc.blocks}

    def present(index: int) -> bool:
        block = blocks.get(index)
        if block is None:
            return False
        return isinstance(block, StyledTable) or not block.is_empty

    expected = set()
    if segmentation.body is not None:
        expected |= {i for i in segmentation.body.indices if present(i)}
    for annex in segmentation.annexes:
        expected |= {i for i in tuple(annex.span.indices)[1:] if present(i)}
    return expected


def _claimed_indices(result: HierarchyDoc) -> set[int]:
    return set(result.source_indices)


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_conservation_no_loss(corpus, stem):
    """No block is dropped: expected ⊆ everything the trees claim.

    Invariant #2's first half. A lost block is the failure nothing downstream
    can detect — the XML validates, the goldens are stable, and a paragraph of
    the document is simply gone.
    """
    doc, segmentation, result = corpus[stem]
    expected = _expected_indices(doc, segmentation)
    claimed = _claimed_indices(result)
    assert not (expected - claimed), sorted(expected - claimed)


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_conservation_nothing_extra(corpus, stem):
    """No block is invented: everything the trees claim ⊆ expected.

    The mirror of the previous test. A tree reaching outside its own span would
    pull front matter, back matter or another annex's text into the body, which
    is how a signature block ends up published as a section.
    """
    doc, segmentation, result = corpus[stem]
    expected = _expected_indices(doc, segmentation)
    claimed = _claimed_indices(result)
    assert not (claimed - expected), sorted(claimed - expected)


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_conservation_no_duplicate_sections(corpus, stem):
    """One source block heads at most one section, across every tree.

    Invariant #2's second half applied to structure: a block appearing twice in
    ``section_indices`` means the same paragraph became two ``Section``s, which
    would give one piece of text two ``id``s and break invariant #5 downstream.
    """
    _, _, result = corpus[stem]
    headers = [i for tree in result.trees for i in tree.section_indices]
    assert len(headers) == len(set(headers)), sorted(
        i for i in set(headers) if headers.count(i) > 1
    )


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_conservation_no_duplicate_content(corpus, stem):
    """One source block produces at most one content node, across every tree.

    Duplication has to fail as loudly as loss: text emitted twice reads as the
    document saying a thing twice, and no reader can tell it was the parser.
    """
    _, _, result = corpus[stem]
    content = [i for tree in result.trees for i in tree.content_indices]
    assert len(content) == len(set(content)), sorted(
        i for i in set(content) if content.count(i) > 1
    )


_WHITESPACE = re.compile(r"\s+")


def _squash(text: str) -> str:
    """Text with all whitespace removed, for comparisons that ignore layout."""
    return _WHITESPACE.sub("", text)


def _node_text(node) -> str:
    if isinstance(node, Para):
        return node.text
    if isinstance(node, ListNode):
        return "".join(_item_text(item) for item in node.items)
    if isinstance(node, Table):
        return "".join(
            inline.text for row in node.rows for cell in row for inline in cell
        )
    raise AssertionError(f"unexpected content node {type(node).__name__}")


def _item_text(item: ListItem) -> str:
    children = "".join(
        _item_text(c) if isinstance(c, ListItem) else _node_text(c)
        for c in item.children
    )
    return item.text + children


def _section_text(section: Section) -> str:
    return (
        (section.label or "")
        + (section.heading or "")
        + "".join(_node_text(n) for n in section.body)
        + "".join(_section_text(c) for c in section.children)
    )


def _tree_text(tree: HierarchyTree) -> str:
    return "".join(_node_text(n) for n in tree.preamble) + "".join(
        _section_text(s) for s in tree.sections
    )


def _block_text(block) -> str:
    if isinstance(block, StyledTable):
        return "".join(
            para.text
            for row in block.rows
            for cell in row.cells
            for para in cell.paras
        )
    return block.text


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_text_conservation(corpus, stem):
    """The trees say exactly what the source spans say — no more, no less.

    Invariant #2 stated over *text* rather than over indices, which is the
    stronger form: index arithmetic proves a block was accounted for, this
    proves its characters survived. The tree's text is read in document order
    as section ``label`` + ``heading``, then every ``Para.text``, every
    ``ListItem.text``, and every table cell's inline text; the source's is the
    same spans' block text, under the same rule as
    :func:`_expected_indices` (annex marker paragraph excluded, since it lives
    on ``AnnexHierarchy.label``). Whitespace is squashed out of both sides
    because paragraph boundaries are structure, not content.

    **Why a section header index can legitimately appear twice** — once in
    ``section_indices`` and once on a content ``Para``: a labelled paragraph
    whose remainder is prose, such as ``5.1 - Como foi dito inicialmente…``, is
    *one* source block that produced *two* things — the rótulo (``5.1 -``,
    which becomes ``Section.label``) and the section's first paragraph
    (``Como foi dito inicialmente…``). ``_finish`` splits the inlines at the
    rótulo, so the characters are still present exactly once even though the
    index is claimed by both. This test is what proves that split is exact: a
    repeated rótulo or a swallowed first sentence shows up here immediately.
    """
    doc, segmentation, result = corpus[stem]
    blocks = {b.index: b for b in doc.blocks}

    indices: list[int] = list(segmentation.body.indices) if segmentation.body else []
    for annex in segmentation.annexes:
        indices += list(annex.span.indices)[1:]

    source = _squash("".join(_block_text(blocks[i]) for i in indices if i in blocks))
    inferred = _squash("".join(_tree_text(tree) for tree in result.trees))
    assert inferred == source


def test_body_and_annex_indices_are_disjoint(corpus):
    """The body tree and the annex tree partition the document, never share it.

    An annex is a *separate document* in LexML — Cycle 6 emits ``port_mf_277``'s
    ``ANEXO ÚNICO`` as a sibling ``<Anexo>`` with its own ``!anexo1`` URN. A
    block claimed by both trees would be published twice under two different
    URNs, so the disjointness is a citation property, not just tidiness.
    """
    _, _, result = corpus[ANNEXED]
    assert len(result.annexes) == 1
    body = set(result.body.section_indices) | set(result.body.content_indices)
    annex_tree = result.annexes[0].tree
    annex = set(annex_tree.section_indices) | set(annex_tree.content_indices)
    assert body
    assert annex
    assert not (body & annex)


# --------------------------------------------------------------------------
# Determinism and idempotence — plan §9.2 invariant #4
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_idempotence(corpus, stem):
    """Inferring twice over one ``StyledDoc`` yields an identical tree.

    The plan's Cycle 4 bullet, asserted by dataclass equality so it covers
    evidence, signals and source indices as well as shape. Any dependence on
    dict ordering, mutable module state or a cache that survives a call would
    surface here rather than as an unreproducible golden diff months later.
    """
    doc, segmentation, result = corpus[stem]
    metadata = extract_metadata(doc, filename=f"{stem}.docx")
    again = infer_hierarchy(doc, metadata=metadata, segmentation=segmentation)
    assert again == result


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_determinism_across_reads(corpus, stem):
    """A fresh read of the same ``.docx`` produces byte-identical JSON.

    Invariant #4 across the whole pipeline, not just this stage: same input,
    byte-identical output. This is what makes a golden diff mean *a behaviour
    changed* rather than *the parser was run again*.
    """
    _, _, result = corpus[stem]
    _, _, reread = _infer(stem)
    assert reread.to_json() == result.to_json()


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_roundtrip_to_dict(corpus, stem):
    """``HierarchyDoc`` survives its own dict form unchanged.

    The dict form is what the goldens hold and what Cycles 5 and 6 read back,
    so a field the serialiser forgets is a field those cycles silently lose.
    Round-tripping the whole document catches that; round-tripping a hand-built
    node would not, because it would never contain the field.
    """
    _, _, result = corpus[stem]
    assert HierarchyDoc.from_dict(result.to_dict()) == result


def test_roundtrip_to_json(corpus):
    """The JSON form is stable under a parse-and-re-emit cycle."""
    for stem in SAMPLES:
        _, _, result = corpus[stem]
        assert HierarchyDoc.from_json(result.to_json()).to_json() == result.to_json()


# --------------------------------------------------------------------------
# No fabrication — plan §9.2 invariant #8
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stem", FLAT_BODIES, ids=FLAT_BODIES)
def test_flat_fallback_produces_no_sections(corpus, stem):
    """Below the threshold: zero sections, and *nothing lost* going flat.

    Six bodies in the corpus have no structure worth claiming — four short
    declaratory acts, a court decision, and ``port_mf_277``'s two-article
    portaria whose real content is its annex. The important half of this test
    is the last assertion: degrading to flat is only honest if every block
    lands in ``preamble``. A fallback that dropped what it could not structure
    would trade fabrication for amputation, which is the worse failure.
    """
    doc, segmentation, result = corpus[stem]
    tree = result.body
    assert tree.sections == ()
    assert tree.flat is True
    assert tree.confidence < CONFIDENCE_THRESHOLD
    assert tree.section_indices == ()

    blocks = {b.index: b for b in doc.blocks}
    expected = set()
    if segmentation.body is not None:
        expected = {
            i
            for i in segmentation.body.indices
            if i in blocks
            and (isinstance(blocks[i], StyledTable) or not blocks[i].is_empty)
        }
    assert {i for node in tree.preamble for i in node.all_source_indices} == expected


def test_flat_fallback_below_threshold():
    """One heading is not a structure — it scores 0.3 and the span stays flat.

    Synthetic because no sample produces exactly this: a document with a single
    Word heading and nothing else. ``document_confidence`` damps the mean by
    ``len(scores) / 3``, so one perfect style signal (0.9) yields 0.3 — below
    :data:`CONFIDENCE_THRESHOLD`. Without the damping, one stray heading in a
    400-paragraph document would declare that document structured, which is the
    exact fabrication invariant #8 exists to prevent.
    """
    blocks = [
        StyledPara(inlines=(Inline("DA COISA JULGADA"),), style="Heading 1", index=0)
    ] + [
        StyledPara(inlines=(Inline(f"Prosa {i}."),), index=i) for i in range(1, 5)
    ]
    tree = build_tree(blocks)
    assert tree.confidence == 0.3
    assert tree.confidence < CONFIDENCE_THRESHOLD
    assert tree.flat is True
    assert tree.sections == ()
    assert len(tree.preamble) == 5


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_articles_never_become_sections(corpus, stem):
    """No article, in any sample or in the annex, ever becomes a ``Section``.

    Spec decision D-3, stated as a property of the whole corpus rather than as
    a fact about ``parecer_93``. The plan's regression-critical requirement —
    that none of ``parecer_93``'s 25 quoted ``Art.`` paragraphs become structure
    — is discharged here **by design, not by a rule**: on the generic route
    articulation is simply not a shape the tree builder can produce, because
    ``artigo``/``paragrafo`` labels never reach ``_assemble``. Articulation is
    the ``norma`` route's business (Cycles 4b and 6).

    Pinned as a property because a rule tuned to one sample regresses silently
    on the 300+ documents nobody has read; a shape the builder cannot emit
    cannot regress at all, and this test is what keeps that true.
    """
    _, _, result = corpus[stem]
    for tree in result.trees:
        for section in tree.walk():
            assert section.kind not in {"artigo", "paragrafo"}, section.title
            assert not (section.label or "").startswith("Art"), section.title


# --------------------------------------------------------------------------
# Content nodes and list reconstruction
# --------------------------------------------------------------------------


def _listed(texts, ilvls) -> list[StyledPara]:
    """Paragraphs Word considers one list, at the given ``ilvl``s."""
    return [
        StyledPara(inlines=(Inline(text),), num_id="9", ilvl=ilvl, index=i)
        for i, (text, ilvl) in enumerate(zip(texts, ilvls))
    ]


def test_list_nesting_three_levels():
    """``ilvl`` nesting reconstructs a real tree, and loses nothing doing it.

    Amendment **A-4.6**: *no sample has a contiguous multi-level Word list* —
    ``CARNE_LEAO``'s ``ilvl=1`` and ``ilvl=2`` paragraphs are eleven blocks
    apart and form two separate lists (spec correction C-4). The rule therefore
    cannot be discharged by a golden and is tested synthetically, the same
    resolution amendment A-1.3 reached for NFC normalisation.

    It earned that place immediately: **the first implementation dropped every
    nested item**, and no corpus golden could have caught it. That is exactly
    the failure mode a rule the corpus cannot reach is prone to, which is why
    the conservation assertion below — all five indices present — is the point
    of the test rather than a decoration on it.
    """
    node = _list_node(_listed(["a", "a.1", "a.1.1", "b", "b.1"], [0, 1, 2, 0, 1]))

    assert len(node.items) == 2
    first, second = node.items
    assert first.text == "a"
    assert second.text == "b"

    inner = first.children[0]
    assert isinstance(inner, ListNode)
    assert [i.text for i in inner.items] == ["a.1"]
    innermost = inner.items[0].children[0]
    assert isinstance(innermost, ListNode)
    assert [i.text for i in innermost.items] == ["a.1.1"]

    assert [i.text for i in second.children[0].items] == ["b.1"]
    assert sorted(node.all_source_indices) == [0, 1, 2, 3, 4]


def test_list_orphan_ilvl_clamped():
    """A list whose only level is ``ilvl=1`` is a flat list, not a hole.

    ``CARNE_LEAO``'s blocks 76–86 are exactly this: Word records the inner
    level and never the outer one. Taking ``ilvl`` literally would build a list
    whose every item hangs off a level that does not exist, so levels are
    *ranked* rather than used raw.
    """
    node = _list_node(_listed(["um", "dois"], [1, 1]))
    assert [i.text for i in node.items] == ["um", "dois"]
    assert all(item.children == () for item in node.items)
    assert sorted(node.all_source_indices) == [0, 1]


def test_list_deep_first_item_clamped():
    """A list that *opens* deeper than its own base clamps up, never drops.

    There is nothing above the first item to nest it under. Discarding it would
    be a conservation failure caused by a malformed numbering definition — and
    a silent one, since the item simply would not appear.
    """
    node = _list_node(_listed(["deep", "top", "under"], [2, 0, 1]))
    assert [i.text for i in node.items] == ["deep", "top"]
    assert node.items[0].children == ()
    assert [i.text for i in node.items[1].children[0].items] == ["under"]
    assert sorted(node.all_source_indices) == [0, 1, 2]


def test_list_skipped_level():
    """A skipped ``ilvl`` nests one step, rather than leaving an empty level.

    ``[0, 2]`` is a list with a hole in its numbering definition. Ranking the
    levels that are actually present turns it into plain one-deep nesting, and
    nothing is lost.
    """
    node = _list_node(_listed(["top", "way under"], [0, 2]))
    assert [i.text for i in node.items] == ["top"]
    nested = node.items[0].children[0]
    assert isinstance(nested, ListNode)
    assert [i.text for i in nested.items] == ["way under"]
    assert sorted(node.all_source_indices) == [0, 1]


def test_list_ordered_inference():
    """``ordered`` comes from the enumerator in the item's own text.

    Spec decision **D-4**: Word's ``numFmt`` is deliberately *not* read.
    Capturing it would mean a new ``StyledPara`` field, and that rewrites all
    15 Cycle 1 ``styled`` goldens — a major change to delivered output for a
    signal Cycle 5 can pay for if it turns out to need it. The text is the
    evidence that is already in hand.
    """
    assert _list_node(_listed(["1. um", "2. dois"], [0, 0])).ordered is True
    assert _list_node(_listed(["um", "dois"], [0, 0])).ordered is False


def test_items_returns_empty_for_no_entries():
    """The recursion's base case is the empty tuple, not a crash."""
    assert _items([], 0) == ()


def _content_nodes(tree: HierarchyTree):
    """Every content node in a tree, preamble first, then section bodies."""
    yield from tree.preamble
    for section in tree.walk():
        yield from section.body


def test_carne_leao_lists(corpus):
    """``CARNE_LEAO``'s six Word lists survive as six ``ListNode``s.

    The only sample with real Word lists, and the reason list reconstruction
    exists at all. All six are bullets — no item carries an enumerator — so
    ``ordered`` is False throughout, which is D-4's inference doing the right
    thing on the one document that exercises it.
    """
    _, _, result = corpus[CARNE_LEAO]
    lists = [n for n in _content_nodes(result.body) if isinstance(n, ListNode)]
    assert [len(node.items) for node in lists] == [2, 9, 3, 9, 11, 2]
    assert all(node.ordered is False for node in lists)


def test_tables_preserved(corpus):
    """Every table inside an inferred span reaches the tree, shape intact.

    ``par_cosit_26`` (2×3, block 11) and ``sumula_stj_125`` (7×4, block 10) are
    the corpus's two in-span tables — both mid-document, never appended, which
    is why Cycle 1 kept blocks interleaved. Cells hold **inline content only**:
    LexML's ``<td>`` takes no ``<p>`` (plan §2.2), and modelling that
    restriction here rather than discovering it in the emitter is the whole
    reason ``Table.rows`` is typed the way it is.
    """
    seen: set[str] = set()
    for stem in SAMPLES:
        doc, segmentation, result = corpus[stem]
        spans = [segmentation.body] if segmentation.body else []
        spans += [a.span for a in segmentation.annexes]
        source = {
            b.index: b.shape
            for b in doc.blocks
            if isinstance(b, StyledTable) and any(b.index in s for s in spans)
        }
        if not source:
            continue
        seen.add(stem)
        tables = [
            n for tree in result.trees for n in _content_nodes(tree) if isinstance(n, Table)
        ]
        assert {t.source_indices[0]: t.shape for t in tables} == source
        for table in tables:
            for row in table.rows:
                for cell in row:
                    assert all(isinstance(i, Inline) for i in cell)

    assert seen == {"par_cosit_26_20000629", "sumula_stj_125"}


def test_split_inlines():
    """Splitting at a character offset respects run boundaries and formatting.

    A rótulo and the prose after it are frequently one Word run, and the rótulo
    is frequently bold while its paragraph is not — so dropping the first run
    would lose the sentence, and keeping it whole would repeat the rótulo. The
    surviving fragment must keep the run's own formatting, or a bold rótulo
    silently un-bolds the sentence that followed it in the same run.
    """
    inlines = (Inline("2.1 - Como", bold=True), Inline(" foi"))

    tail = split_inlines(inlines, 6)
    assert [i.text for i in tail] == ["Como", " foi"]
    assert tail[0].bold is True
    assert tail[1].bold is False

    assert split_inlines(inlines, 0) == inlines
    assert split_inlines(inlines, -3) == inlines
    assert split_inlines(inlines, 100) == ()


# --------------------------------------------------------------------------
# The model nodes themselves
# --------------------------------------------------------------------------


def test_node_roundtrips():
    """Every node type survives ``from_dict(to_dict(x)) == x``.

    The serialisation is not a debugging convenience: it is the golden format
    and the hand-off to Cycles 5 and 6. A field omitted from ``to_dict`` is a
    field those cycles never see, and a default-valued field that fails to
    round-trip turns a reviewed golden into a lossy one.
    """
    para = Para(
        inlines=(Inline("texto", bold=True), Inline(" mais")),
        kind="quote",
        indent=2908,
        source_indices=(7,),
    )
    inner = ListNode(ordered=True, items=(ListItem(inlines=(Inline("a"),), source_indices=(2,)),))
    item = ListItem(inlines=(Inline("um"),), children=(inner,), source_indices=(1,))
    listnode = ListNode(ordered=False, items=(item,))
    table = Table(
        rows=(((Inline("a"),), (Inline("b"),)), ((Inline("c"),), (Inline("d"),))),
        source_indices=(11,),
    )
    section = Section(
        label="2.1 -",
        heading="Empresas de serviços",
        level=2,
        kind="subsecao",
        body=(para, listnode, table),
        children=(Section(label="a)", level=3, kind="alinea", source_indices=(9,)),),
        evidence=Evidence(signals=("label_series",), score=0.85),
        source_indices=(8,),
    )

    for node in (para, item, listnode, table, section):
        assert node_from_dict(node.to_dict()) == node

    evidence = Evidence(signals=("style", "label_series"), score=0.9)
    assert Evidence.from_dict(evidence.to_dict()) == evidence


def test_node_from_dict_rejects_unknown():
    """An unrecognised ``node`` kind is a ``ValueError``, never a silent skip.

    A golden or a hand-edited dict naming a node type that does not exist is a
    mistake; dispatching it to nothing would drop the content and everything
    beneath it without a word.
    """
    with pytest.raises(ValueError):
        node_from_dict({"node": "banana"})
    with pytest.raises(ValueError):
        node_from_dict({})


def test_section_all_source_indices_includes_descendants():
    """A section accounts for its own block, its body's, and its children's.

    This is the property conservation is computed from, so it has to hold for a
    nested tree and not merely for a leaf: a section that reported only its own
    indices would make a whole subtree invisible to the conservation tests.
    """
    grandchild = Section(
        label="2.1.1",
        level=3,
        body=(Para(inlines=(Inline("neta"),), source_indices=(5,)),),
        source_indices=(4,),
    )
    child = Section(
        label="2.1",
        level=2,
        body=(Para(inlines=(Inline("filha"),), source_indices=(3,)),),
        children=(grandchild,),
        source_indices=(2,),
    )
    parent = Section(
        label="2.",
        level=1,
        body=(Para(inlines=(Inline("mãe"),), source_indices=(1,)),),
        children=(child,),
        source_indices=(0,),
    )
    assert parent.all_source_indices == (0, 1, 2, 3, 4, 5)
    assert child.all_source_indices == (2, 3, 4, 5)
    assert grandchild.all_source_indices == (4, 5)


def test_section_walk_is_document_order():
    """``walk`` is depth-first and in document order, self before descendants.

    Emission, ``id`` assignment and the CSV segment export all read the tree
    through ``walk``. If it yielded children before their parent, or siblings
    out of order, every one of those outputs would reorder the document.
    """
    tree_root = Section(
        label="2.",
        level=1,
        children=(
            Section(
                label="2.1",
                level=2,
                children=(Section(label="2.1.1", level=3),),
            ),
            Section(label="2.2", level=2),
        ),
    )
    assert [s.label for s in tree_root.walk()] == ["2.", "2.1", "2.1.1", "2.2"]

    doc_tree = HierarchyTree(sections=(tree_root, Section(label="3.", level=1)), flat=False)
    assert [s.label for s in doc_tree.walk()] == ["2.", "2.1", "2.1.1", "2.2", "3."]
    assert doc_tree.max_depth == 3


@pytest.mark.parametrize("stem", SAMPLES, ids=SAMPLES)
def test_para_kinds_vocabulary(corpus, stem):
    """Every ``Para.kind`` the corpus produces is in the ratified vocabulary.

    ``PARA_KINDS`` is plan §3.1's contract with Cycle 5, which switches on it to
    choose an element. A kind invented here would reach the emitter as an
    unhandled case rather than as a failing test.
    """
    _, _, result = corpus[stem]
    kinds = {
        n.kind
        for tree in result.trees
        for n in _content_nodes(tree)
        if isinstance(n, Para)
    }
    assert kinds <= PARA_KINDS, kinds - PARA_KINDS


# --------------------------------------------------------------------------
# Section shapes on real samples
# --------------------------------------------------------------------------


def test_labelled_prose_remainder_becomes_body_para(corpus):
    """A rótulo followed by prose splits into label + first paragraph, once.

    ``port_mf_454``'s ``1.`` is one Word paragraph reading
    ``1. Para os efeitos do artigo 1º…``. It is a *section*, not a heading, so
    ``heading`` stays ``None`` and the remainder becomes the section's first
    body ``Para`` — with the rótulo removed, because leaving it in would emit
    ``1.`` twice: once as the section's label and once inside its own text.
    """
    _, _, result = corpus["port_mf_454_19770825"]
    section = next(s for s in result.body.walk() if s.label == "1.")
    assert section.heading is None
    first = section.body[0]
    assert isinstance(first, Para)
    assert first.text.startswith("Para os efeitos do artigo 1º")
    assert not first.text.lstrip().startswith("1.")


def test_heading_remainder_becomes_heading(corpus):
    """A rótulo followed by a heading becomes ``heading``, not a paragraph.

    ``pn_cst_38``'s ``2. DAS SOCIEDADES COOPERATIVAS`` is the other half of the
    same decision: the remainder reads as a title, so it becomes the section's
    ``heading`` (Cycle 5's ``nomeAgrupador``) and no body ``Para`` repeats it.
    Emitting it in both places would publish the heading text twice.
    """
    _, _, result = corpus["pn_cst_38_19801031"]
    section = next(s for s in result.body.walk() if s.label == "2.")
    assert section.heading == "DAS SOCIEDADES COOPERATIVAS"
    assert not any(
        isinstance(n, Para) and "SOCIEDADES COOPERATIVAS" in n.text for n in section.body
    )


def test_preamble_holds_content_before_first_section(corpus):
    """Content ahead of the first section survives, in ``preamble``.

    ``par_cosit_26``'s ``1.`` sits in the front matter, so its body opens with
    unlabelled prose that belongs to no section. Without a preamble that text
    would have nowhere to go — the failure this field exists to prevent.
    """
    _, _, result = corpus["par_cosit_26_20000629"]
    tree = result.body
    assert tree.flat is False
    assert tree.preamble
    first_section = tree.sections[0].source_indices[0]
    assert all(
        i < first_section for node in tree.preamble for i in node.all_source_indices
    )


def test_annex_tree(corpus):
    """``port_mf_277``'s ``ANEXO ÚNICO`` is a tree of 65 súmulas.

    Amendment A-R.8, discharged early by R-2: the annex is inferred as its own
    tree rather than deferred to Cycle 6. ``fragment`` is what becomes the
    ``!anexo1`` URN, so it is asserted alongside the shape. The 65 sections are
    heading/text *pairs* over 131 blocks, not 130 headings (spec correction
    C-3), and they are found by unit-series detection — ≥3 whole-paragraph
    occurrences of one folded head word with strictly increasing numbers
    (amendment A-4.4), which is the rule that keeps ``Lei nº 12.618`` from ever
    parsing as a heading.
    """
    _, _, result = corpus[ANNEXED]
    assert len(result.annexes) == 1
    annex = result.annexes[0]
    assert annex.label == "ANEXO ÚNICO"
    assert annex.ordinal == 1
    assert annex.fragment == "anexo1"

    tree = annex.tree
    assert tree.flat is False
    assert len(tree.sections) == 65
    assert len(list(tree.walk())) == 65
    assert {s.level for s in tree.walk()} == {1}
    assert {s.kind for s in tree.walk()} == {"item"}
    assert tree.sections[0].label == "Súmula CARF nº 1"


# ---------------------------------------------------------------------------
# Nested quotations (amendments A-Q.3, A-Q.4, A-Q.5)
# ---------------------------------------------------------------------------
#
# `par_cosit_26`'s item `14.` announces four laws and transcribes them as one
# flat run of 35 `<p>` siblings. A human reader sees four quotations; the XML
# said "thirty-five paragraphs, some of them quoted". These tests pin the
# division — and, far more importantly, pin that it cannot happen by accident.


class _Boundary:
    """A referee that confirms every boundary put to it, and nothing else.

    Deliberately answers the *other* three questions with an abstention: this
    is the seam for A-Q.4, and a double that also moved `own_articulation`
    would make a failure here ambiguous between the two.
    """

    name = "always-boundary"
    enabled = True
    last_cache_hit = False

    def __init__(self, verdict: str = "boundary", confidence: float = 0.9) -> None:
        self._verdict = verdict
        self._confidence = confidence
        self.asked: list[tuple[str, str]] = []

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        return Verdict.abstain("not under test")

    def is_heading(self, para: str, ctx: str) -> Verdict:
        return Verdict.abstain("not under test")

    def section_kind(self, label: str, heading: str) -> Verdict:
        return Verdict.abstain("not under test")

    def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
        self.asked.append((excerpt, ctx))
        return Verdict(self._verdict, self._confidence, "test double")


def _refereed(stem: str, referee=None):
    """One sample's hierarchy, built with ``referee`` in the loop."""
    path = SAMPLES_DIR / f"{stem}.docx"
    doc = read_docx(path)
    metadata = extract_metadata(doc, filename=path.name)
    return infer_hierarchy(
        doc,
        metadata=metadata,
        segmentation=segment_document(doc, metadata=metadata),
        referee=referee,
    )


def _citations(result) -> list:
    return [
        section
        for tree in result.trees
        for section in tree.walk()
        if section.kind == "citacao"
    ]


def test_citacao_is_a_ratified_section_kind():
    """T-8c.18. `Agrupamento/@nome` is an open `xsd:string`, so this is the
    only place the new kind has to be declared — but it does have to be, or
    Cycle 5's "every nome comes from SECTION_KINDS" assertion fails."""
    assert "citacao" in SECTION_KINDS


def test_par_cosit_26_nests_four_citacoes_when_confirmed():
    """T-8c.14. The amendment's target, end to end.

    Four child sections, one per announced law, each headed by the norm exactly
    as the document writes it — which is what becomes `NomeAgrupador`, and what
    makes the quotation `ancestor::`-addressable for §6.1's segmentation.
    """
    result = _refereed(PAR_COSIT_26, _Boundary())
    citations = _citations(result)

    assert [section.heading for section in citations] == [
        "Lei nº 7.713, de 1988",
        "Lei 8.134, de 1990",
        "Lei 8.383, de 1991",
        "Lei 8.981, de 1995",
    ]
    parents = [
        section
        for tree in result.trees
        for section in tree.walk()
        if any(child.kind == "citacao" for child in section.children)
    ]
    assert len(parents) == 1, "all four belong to the one section that announced them"
    assert parents[0].label == "14."
    for child in citations:
        assert child.level == parents[0].level + 1
        assert child.body, "a citation with no body is not a citation"


def test_no_referee_means_no_nesting():
    """T-8c.9 / invariant #8. The default configuration changes nothing.

    `BOUNDARY_RULE_CONFIDENCE` sits below `FLAG_THRESHOLD` precisely so that a
    candidate nobody confirmed stays a candidate. This is what keeps §9.3's
    pinned `--referee=none` suite and all 135 goldens honest, and it is the
    reason the amendment is safe to land at all.
    """
    assert BOUNDARY_RULE_CONFIDENCE < FLAG_THRESHOLD
    for stem in SAMPLES:
        assert _citations(_refereed(stem)) == [], stem
        assert _citations(_refereed(stem, NullReferee())) == [], stem


def test_a_vetoing_referee_leaves_the_document_flat():
    """T-8c.13's sibling. `continuation` is a veto, and a veto is respected."""
    assert _citations(_refereed(PAR_COSIT_26, _Boundary("continuation", 0.9))) == []


def test_an_unsure_referee_cannot_confirm():
    """T-8c.13. `REFEREE_MIN_CONFIDENCE` still gates, on the new question too.

    An LLM asked a hard question answers *something*; this is what stops
    "something" from becoming a citable unit with its own URN.
    """
    unsure = _Boundary("boundary", REFEREE_MIN_CONFIDENCE - 0.01)
    assert _citations(_refereed(PAR_COSIT_26, unsure)) == []
    assert unsure.asked, "it must still have been consulted, just not obeyed"


def test_the_referee_is_only_asked_about_generated_candidates():
    """T-8c.12, first half. The referee cannot volunteer a boundary.

    It is asked exactly three times on the whole corpus, always about a
    paragraph the deterministic head detector proposed. This is A-Q.3's
    inversion stated as a count: whatever the model says, it is answering a
    closed question about a candidate that already exists.
    """
    referee = _Boundary()
    for stem in SAMPLES:
        _refereed(stem, referee)

    assert len(referee.asked) == 3
    for excerpt, ctx in referee.asked:
        assert quotation_head(excerpt) is not None, excerpt[:60]
        # The prompt carries the *announcing* paragraph, not merely the one
        # above — the repair the record's §2.3 asked for (A-Q.3, A-Q.7).
        assert "1º a 3º e 16 da Lei nº 7.713" in ctx


@pytest.mark.parametrize("name", SAMPLES)
def test_an_adversarial_referee_changes_nothing_it_was_not_asked(name):
    """T-8c.12. The A-4b.6 attack, for the boundary question.

    A referee answering "boundary" to every question, at maximum confidence,
    must not change any sample's output beyond the candidates the rules already
    found. Invariant #8's promise — *low confidence degrades to flat, never
    invents structure* — is thereby an argument about the candidate generator
    rather than a hope about the model, which is the whole reason the question
    is confirm-only.

    A wrong `class="quote"` is a mislabelling. A wrong nested `Agrupamento` is
    a fabricated citable unit with its own URN, which §6.1's segmentation would
    hand to a RAG system as an addressable fact.
    """
    hostile = _refereed(name, _Boundary("boundary", 1.0))
    citations = _citations(hostile)

    if name == PAR_COSIT_26:
        assert len(citations) == 4
    else:
        assert citations == [], (
            f"{name}: an adversarial referee invented {len(citations)} citations "
            "out of candidates that do not exist"
        )


@pytest.mark.parametrize("name", SAMPLES)
def test_conservation_holds_across_the_split(name):
    """T-8c.15. A-Q.5's gate, asserted as invariant #2 over the whole corpus.

    The split *moves* nodes out of a parent's body and into children. Moving is
    the only safe operation: a copy duplicates text and a partial move loses
    it, and neither is visible to any schema — Cycle 6's first statutory render
    was valid on both schemas and 29 words short.
    """
    flat = _refereed(name)
    split = _refereed(name, _Boundary())

    assert sorted(split.source_indices) == sorted(flat.source_indices)
    assert len(split.source_indices) == len(flat.source_indices), "duplication"


def test_a_single_run_section_is_not_wrapped():
    """T-8c.17. One quotation is not a division.

    Wrapping a lone excerpt in a child that adds no distinction is structure
    for its own sake, and it would churn a golden on every sample in the corpus
    that quotes anything at all.
    """
    for stem in SAMPLES:
        if stem == PAR_COSIT_26:
            continue
        assert _citations(_refereed(stem, _Boundary())) == [], stem
