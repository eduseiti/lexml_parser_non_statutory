"""``DocumentModel``: the five views of a document, assembled once.

Plan §3.1 specifies this type and no cycle had built it — Cycle 4b was expected
to and did not, which is Cycle 5 spec §3.1 Q1. The answer was to build it now,
minus ``articulacao``, and to give every emitter **one** argument instead of
five. That is not tidiness: passing five components through every emitter, every
cycle, is five chances to hand one emitter a segmentation computed from a
different profile than the metadata beside it, and nothing in the output would
say so.

Three properties are worth asserting about an assembler that mostly delegates.

* **It agrees with the goldens.** ``build_model`` runs the same call chain
  ``scripts/regen_goldens.py`` runs, so ``model.route`` must equal the ``route``
  in ``tests/golden/routing/<stem>.json`` for all fifteen samples. If the two
  ever drift, an emitter would be rendering a document the routing goldens say
  is a different kind of thing.
* **It is deterministic** (invariant #4). Two builds from the same input compare
  equal, component by component, including Cycle 4b's ``decisions`` telemetry —
  a record that varied between runs would make every downstream golden unstable.
* **It computes only what it was not given.** A caller that has already paid for
  a segmentation must get *that* object back, not an equal one: identity is
  asserted rather than equality, because an equal-but-recomputed component means
  the work was done twice and the "precomputed" argument is decorative.

``articulacao`` is deliberately empty here and stays empty for every sample,
including the one routed to ``norma``. Cycle 6 fills it; asserting emptiness now
is what makes that cycle's arrival visible as a change rather than a surprise.

The models are built from Cycle 1's ``styled`` goldens rather than from the
``.docx`` files — much faster, and it makes a drift here impossible to blame on
the reader, which would show up in Cycle 1's goldens first.
"""

from __future__ import annotations

import json

import pytest

from lexml_nonstat.hierarchy import infer_hierarchy
from lexml_nonstat.ingest import StyledDoc, StyledPara, StyledTable
from lexml_nonstat.model import DocumentModel, build_model, extract_metadata
from lexml_nonstat.profile import select_profile
from lexml_nonstat.routing import assess_viability
from lexml_nonstat.segment import segment_document

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"
ROUTING_DIR = REPO_ROOT / "tests" / "golden" / "routing"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: A parecer with tables, footnote-heavy prose and 104 blocks — big enough that
#: `blocks` and `block_text` are saying something, small enough to be quick.
ANCHOR = "par_cosit_26_20000629"

_DOCS: dict[str, StyledDoc] = {}


def styled(name: str) -> StyledDoc:
    if name not in _DOCS:
        _DOCS[name] = StyledDoc.from_json(
            (STYLED_DIR / f"{name}.json").read_text(encoding="utf-8")
        )
    return _DOCS[name]


def routing_golden(name: str) -> dict:
    return json.loads((ROUTING_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", SAMPLES)
def test_build_model_from_each_sample(name: str) -> None:
    """Every sample assembles, every field is populated, and the route agrees.

    The cross-check against ``tests/golden/routing/<stem>.json`` is the point:
    ``build_model`` and ``regen_goldens.py`` must be walking the same call chain
    with the same defaults — in particular ``referee=None``, which plan §9.3
    pins for the whole suite. A model that consulted a referee would route
    differently on some documents and nothing else in the suite would notice.
    """
    doc = styled(name)
    model = build_model(doc, filename=f"{name}.docx")

    assert isinstance(model, DocumentModel)
    assert model.styled is doc
    assert model.source == f"{name}.docx"

    for field in ("metadata", "segmentation", "hierarchy", "viability"):
        assert getattr(model, field) is not None, field

    golden = routing_golden(name)
    assert model.route == golden["route"], (
        f"{name}: model routes to {model.route!r}, routing golden says "
        f"{golden['route']!r}"
    )
    assert model.profile == golden["profile"]
    assert model.route == model.viability.route

    # The convenience properties really do reach through to the hierarchy.
    assert model.body is model.hierarchy.body
    assert model.annexes is model.hierarchy.annexes
    assert isinstance(model.annexes, tuple)

    # `metadata` carries a URN, which is what the emitter writes into
    # `Identificacao/@URN` and what an annex's `!anexoN` fragment extends.
    assert model.metadata.urn


def test_build_model_accepts_precomputed() -> None:
    """A supplied component is used **verbatim** — identity, not equality.

    ``regen_goldens.py``, the emitter and the test suite all compute these
    objects once and pass them down. If ``build_model`` quietly recomputed one,
    the model could disagree with the very golden that was just written from the
    caller's copy, and the work would have been done twice.
    """
    name = ANCHOR
    doc = styled(name)

    profile = select_profile(doc)
    metadata = extract_metadata(doc, profile=profile, filename=f"{name}.docx")
    segmentation = segment_document(doc, profile=profile, metadata=metadata)
    hierarchy = infer_hierarchy(
        doc, segmentation=segmentation, profile=profile, metadata=metadata
    )
    viability = assess_viability(
        doc, metadata=metadata, segmentation=segmentation, hierarchy=hierarchy
    )

    model = build_model(
        doc,
        filename=f"{name}.docx",
        profile=profile,
        metadata=metadata,
        segmentation=segmentation,
        hierarchy=hierarchy,
        viability=viability,
    )

    assert model.metadata is metadata
    assert model.segmentation is segmentation
    assert model.hierarchy is hierarchy
    assert model.viability is viability
    assert model.styled is doc

    # `profile` is stored by name, and the name is the supplied profile's.
    assert model.profile == profile.name
    assert model.route == viability.route

    # Supplying only some components still works: the rest are computed, and
    # the ones that were given are still the given objects.
    partial = build_model(doc, filename=f"{name}.docx", metadata=metadata)
    assert partial.metadata is metadata
    assert partial.segmentation is not segmentation
    assert partial.segmentation == segmentation


def test_build_model_is_deterministic() -> None:
    """Invariant #4. Two builds from one input are equal, component by component.

    Asserted per component as well as on the whole model, so a failure names the
    layer that varied instead of reporting that two large objects differ. The
    ``decisions`` telemetry is included: it is populated from the start (unlike
    ``articulacao``), and a record that varied between runs — a timestamp, a set
    iteration order — would make every downstream golden unstable.
    """
    name = ANCHOR
    doc = styled(name)

    first = build_model(doc, filename=f"{name}.docx")
    second = build_model(doc, filename=f"{name}.docx")

    assert first.metadata == second.metadata
    assert first.segmentation == second.segmentation
    assert first.hierarchy == second.hierarchy
    assert first.viability == second.viability
    assert first.profile == second.profile
    assert first.route == second.route
    assert first.decisions == second.decisions
    assert first == second

    # A different document is genuinely different, so the equality above is not
    # an artefact of a model that compares equal to everything.
    other = build_model(
        styled("ad_srf_22_19970430"), filename="ad_srf_22_19970430.docx"
    )
    assert other != first


@pytest.mark.parametrize("name", SAMPLES)
def test_articulacao_empty_on_generico(name: str) -> None:
    """The Cycle 6 boundary, stated as an assertion rather than a comment.

    ``articulacao`` is declared now so Cycle 6 adds a *route* rather than a
    field, and it is empty for every sample — including ``port_mf_277``, the one
    document routed to ``norma``, which this cycle renders flat as the
    documented §3 fallback. When Cycle 6 lands, this test fails on exactly that
    sample, which is the correct way for a boundary to move.
    """
    model = build_model(styled(name), filename=f"{name}.docx")
    assert model.articulacao == ()
    assert isinstance(model.articulacao, tuple)


def test_blocks_and_block_text() -> None:
    """``blocks`` and ``block_text`` are how a renderer reaches text by span.

    Every part of the segmentation is a ``Span`` of *indices* — no part ever
    copies text — so the emitter needs an index-keyed view of the source, and it
    has to be complete: a missing index would be a block no renderer could reach
    and therefore a conservation failure.

    ``block_text`` returns ``""`` for a table rather than raising or inventing a
    flattened string, because a table's text belongs in cells and a caller that
    wanted it must go through the table renderer.
    """
    name = ANCHOR
    doc = styled(name)
    model = build_model(doc, filename=f"{name}.docx")

    blocks = model.blocks
    assert len(blocks) == len(doc.blocks)
    assert set(blocks) == {b.index for b in doc.blocks}
    for block in doc.blocks:
        assert blocks[block.index] is block

    paragraphs = [b for b in doc.blocks if isinstance(b, StyledPara)]
    assert paragraphs, "the anchor sample has no paragraphs"
    for block in paragraphs:
        assert model.block_text(block.index) == block.text

    for block in doc.blocks:
        if isinstance(block, StyledTable):
            assert model.block_text(block.index) == ""

    # An index that is not a block is empty, not an exception: a renderer walks
    # spans, and a span's arithmetic must not depend on block presence.
    assert model.block_text(10**6) == ""
    assert model.block_text(-1) == ""

    # `blocks` is rebuilt per call, so a caller cannot mutate the model's view
    # of its own source.
    assert model.blocks is not blocks
    assert model.blocks == blocks
