"""Byte-stable `HierarchyDoc` goldens for all 15 samples.

The fourth layer, after Cycle 1's `StyledDoc` (what the reader saw), Cycle 2's
`Metadata` (what the extractor concluded) and Cycle 3's `Segmentation` (how the
document was divided): these pin the *shape* inferred over the body and each
annex.

Plan §9.4 — goldens regenerate only via
`python3 scripts/regen_goldens.py --kind=hierarchy`, so any diff here is a
reviewed behaviour change rather than silent drift.

A golden on its own is weak evidence: one recording a bug passes forever. Two
things guard against that. The hand-authored expectations in
`tests/unit/test_hierarchy_truth.py` are written from the source documents and
are independent of whatever these files happen to say (spec R-4); and this
module asserts the invariants that must hold regardless of the golden's
content. The load-bearing one is **conservation** (plan §9.2, invariant #2):
every non-empty block of the body and of each annex is claimed by the tree
exactly once, so a rendering built from the tree can reconstruct the document.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.hierarchy import HierarchyDoc, infer_hierarchy
from lexml_nonstat.ingest import StyledDoc, StyledTable
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.model.nodes import PARA_KINDS, SECTION_KINDS, ListNode, Para, Table
from lexml_nonstat.segment import Segmentation, segment_document

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"
HIERARCHY_DIR = REPO_ROOT / "tests" / "golden" / "hierarchy"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

_CACHE: dict[str, tuple[StyledDoc, Segmentation, HierarchyDoc]] = {}


def _infer(name: str) -> tuple[StyledDoc, Segmentation, HierarchyDoc]:
    """Infer from Cycle 1's golden rather than re-parsing the DOCX.

    Keeps the module fast, and makes a hierarchy diff impossible to blame on a
    reader change: that would show up in Cycle 1's goldens first.
    """
    if name not in _CACHE:
        doc = StyledDoc.from_json((STYLED_DIR / f"{name}.json").read_text(encoding="utf-8"))
        metadata = extract_metadata(doc, filename=f"{name}.docx")
        segmentation = segment_document(doc, metadata=metadata)
        _CACHE[name] = (
            doc,
            segmentation,
            infer_hierarchy(doc, metadata=metadata, segmentation=segmentation),
        )
    return _CACHE[name]


def _expected_indices(doc: StyledDoc, seg: Segmentation) -> set[int]:
    """Every block the trees must account for.

    The annex's **first** block is excluded: `ANEXO ÚNICO` is the annex's own
    title, which Cycle 6 renders as the sibling document's heading. Leaving it
    inside would make the annex the first section of itself.
    """
    blocks = {b.index: b for b in doc.blocks}
    out: set[int] = set()
    spans = [(seg.body, False)] + [(a.span, True) for a in seg.annexes]
    for span, is_annex in spans:
        if span is None:
            continue
        indices = list(span.indices)
        if is_annex:
            indices = indices[1:]
        for index in indices:
            block = blocks.get(index)
            if block is None:
                continue
            if isinstance(block, StyledTable) or not block.is_empty:
                out.add(index)
    return out


def _node_text(node) -> str:
    if isinstance(node, Para):
        return node.text
    if isinstance(node, ListNode):
        return "".join(_item_text(item) for item in node.items)
    if isinstance(node, Table):
        return "".join(
            "".join(inline.text for inline in cell) for row in node.rows for cell in row
        )
    return ""


def _item_text(item) -> str:
    return item.text + "".join(_node_text(child) for child in item.children)


def _tree_text(tree) -> str:
    parts = [_node_text(node) for node in tree.preamble]
    for section in tree.walk():
        parts.append(section.label or "")
        parts.append(section.heading or "")
        parts.extend(_node_text(node) for node in section.body)
    return "".join(parts)


def _source_text(doc: StyledDoc, seg: Segmentation) -> str:
    blocks = {b.index: b for b in doc.blocks}
    parts: list[str] = []
    for index in sorted(_expected_indices(doc, seg)):
        block = blocks[index]
        if isinstance(block, StyledTable):
            parts.append("".join(cell.text for row in block.rows for cell in row.cells))
        else:
            parts.append(block.text)
    return "".join(parts)


# --------------------------------------------------------------------------
# The goldens themselves
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_exists(name: str) -> None:
    assert (HIERARCHY_DIR / f"{name}.json").is_file(), (
        f"missing golden for {name}; run "
        f"python3 scripts/regen_goldens.py --kind=hierarchy"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_matches(name: str) -> None:
    """Byte-for-byte. A diff here is a behaviour change and must be reviewed."""
    _, _, result = _infer(name)
    assert result.to_json() == (HIERARCHY_DIR / f"{name}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_roundtrips(name: str) -> None:
    """The golden is a faithful serialisation, not a lossy report."""
    text = (HIERARCHY_DIR / f"{name}.json").read_text(encoding="utf-8")
    assert HierarchyDoc.from_json(text).to_json() == text


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_is_valid_json_with_the_expected_keys(name: str) -> None:
    data = json.loads((HIERARCHY_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert data["source"] == f"{name}.docx"
    assert set(data) <= {"source", "profile", "body", "annexes"}
    assert {"confidence", "flat", "signals", "sections"} <= set(data["body"])


def test_golden_count() -> None:
    assert len(list(HIERARCHY_DIR.glob("*.json"))) == len(SAMPLES) == 15


# --------------------------------------------------------------------------
# Invariants that hold whatever the golden says
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_no_text_lost(name: str) -> None:
    """Plan §9.2 invariant #2. Every block reaches the tree."""
    doc, seg, result = _infer(name)
    claimed = set()
    for tree in result.trees:
        claimed.update(tree.section_indices)
        claimed.update(tree.content_indices)
    assert _expected_indices(doc, seg) - claimed == set()


@pytest.mark.parametrize("name", SAMPLES)
def test_nothing_invented(name: str) -> None:
    """The mirror image: the tree claims no block outside its spans."""
    doc, seg, result = _infer(name)
    claimed = set()
    for tree in result.trees:
        claimed.update(tree.section_indices)
        claimed.update(tree.content_indices)
    assert claimed - _expected_indices(doc, seg) == set()


@pytest.mark.parametrize("name", SAMPLES)
def test_no_block_heads_two_sections(name: str) -> None:
    """No source paragraph may be the header of more than one section."""
    _, _, result = _infer(name)
    counts: Counter = Counter()
    for tree in result.trees:
        counts.update(tree.section_indices)
    assert [index for index, n in counts.items() if n > 1] == []


@pytest.mark.parametrize("name", SAMPLES)
def test_no_block_appears_in_two_content_nodes(name: str) -> None:
    """Plan §9.2 Rule B, at the model layer: leaf content is not duplicated.

    A section header index *may* also appear on exactly one content `Para` —
    a labelled paragraph whose remainder is prose (`5.1 - Como foi dito
    inicialmente…`) is one source block that legitimately produced both the
    rótulo and the section's first paragraph. What may never happen is the same
    block appearing in two content nodes.
    """
    _, _, result = _infer(name)
    counts: Counter = Counter()
    for tree in result.trees:
        counts.update(tree.content_indices)
    assert [index for index, n in counts.items() if n > 1] == []


@pytest.mark.parametrize("name", SAMPLES)
def test_text_conservation(name: str) -> None:
    """Conservation as text, not only as arithmetic over indices.

    The index test would pass if a node kept the right index and the wrong
    string. This one compares the characters.
    """
    doc, seg, result = _infer(name)
    trees = "".join(_tree_text(tree) for tree in result.trees)
    assert "".join(trees.split()) == "".join(_source_text(doc, seg).split())


@pytest.mark.parametrize("name", SAMPLES)
def test_determinism(name: str) -> None:
    """Plan invariant #4. Same input, byte-identical output, every time."""
    doc, seg, first = _infer(name)
    metadata = extract_metadata(doc, filename=f"{name}.docx")
    second = infer_hierarchy(doc, metadata=metadata, segmentation=seg)
    assert first.to_json() == second.to_json()
    assert first == second


@pytest.mark.parametrize("name", SAMPLES)
def test_depth_monotonicity(name: str) -> None:
    """Depth never rises by more than one between consecutive headings.

    A jump means the evidence disagreed with itself; clamping is the honest
    response, because the alternative is a tree with a hole in it.
    """
    _, _, result = _infer(name)
    for tree in result.trees:
        previous = 0
        for section in tree.walk():
            assert section.level <= previous + 1, (
                f"{name}: depth jumped from {previous} to {section.level} "
                f"at {section.title!r}"
            )
            previous = section.level


@pytest.mark.parametrize("name", SAMPLES)
def test_vocabularies(name: str) -> None:
    """Every emitted `kind` is one Cycle 5 knows how to render."""
    _, _, result = _infer(name)
    for tree in result.trees:
        for section in tree.walk():
            assert section.kind in SECTION_KINDS
        for node in list(tree.preamble) + [n for s in tree.walk() for n in s.body]:
            if isinstance(node, Para):
                assert node.kind in PARA_KINDS


@pytest.mark.parametrize("name", SAMPLES)
def test_no_fabricated_articulation(name: str) -> None:
    """Plan §2.5, as a property of every sample rather than of one.

    On the generic route an article is prose. `parecer_93` is the sample this
    protects — 25 quoted `Art.` in one document — but asserting it everywhere
    is what keeps a future rule from quietly reintroducing it elsewhere.
    """
    _, _, result = _infer(name)
    for tree in result.trees:
        for section in tree.walk():
            assert section.kind not in {"artigo", "paragrafo"}
            assert not (section.label or "").lower().startswith(("art", "§"))


@pytest.mark.parametrize("name", SAMPLES)
def test_flat_trees_keep_all_their_content(name: str) -> None:
    """Degrading to flat must lose nothing — invariant #8's other half."""
    doc, seg, result = _infer(name)
    for tree in result.trees:
        if not tree.flat:
            continue
        assert tree.sections == ()
        assert len(tree.content_indices) == len(set(tree.content_indices))


def test_goldens_are_current() -> None:
    """Regenerating changes nothing — the committed goldens are the output.

    Deliberately re-parses the DOCX files, exactly as `regen_goldens.py` does,
    so a divergence between the reader and Cycle 1's goldens shows up here too.
    """
    from lexml_nonstat.ingest import read_docx

    for name in SAMPLES:
        path = SAMPLES_DIR / f"{name}.docx"
        doc = read_docx(path)
        metadata = extract_metadata(doc, filename=path.name)
        segmentation = segment_document(doc, metadata=metadata)
        produced = infer_hierarchy(
            doc, metadata=metadata, segmentation=segmentation
        ).to_json()
        assert produced == (HIERARCHY_DIR / f"{name}.json").read_text(encoding="utf-8"), (
            f"{name}: goldens are stale; run "
            f"python3 scripts/regen_goldens.py --kind=hierarchy and review the diff"
        )
