"""Byte-stable `Segmentation` goldens for all 15 samples.

The third layer of goldens, after Cycle 1's `StyledDoc` (what the reader saw)
and Cycle 2's `Metadata` (what the extractor concluded): these pin how the
document was *divided*.

Plan §9.4 — goldens regenerate only via
`python3 scripts/regen_goldens.py --kind=segment`, so any diff here is a
reviewed behaviour change rather than silent drift.

A golden alone is weak evidence — one containing a bug passes forever — so
this module also asserts the invariants that must hold whatever the golden
happens to say. The load-bearing one is **text conservation** (plan §9.2):
the four parts must form a *partition* of the document's blocks. Every
non-empty block lands in exactly one of front / body / back / annex, none
twice and none nowhere. That property is what makes it safe for Cycles 5 and
6 to render the parts independently and still reconstruct the whole document.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.segment import Segmentation, segment_document

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"
SEGMENT_DIR = REPO_ROOT / "tests" / "golden" / "segment"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: The two samples that carry no front or back matter at all. Plan §8's Cycle 3
#: test list names them as the "no false positives" requirement, and plan §12
#: makes it this cycle's exit criterion.
BARE_SAMPLES = ("sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO",)


def _styled(name: str) -> StyledDoc:
    """Load a sample from Cycle 1's golden rather than re-parsing the DOCX.

    Keeps this module fast and makes a segmentation diff impossible to blame
    on a reader change: that would show up in Cycle 1's goldens first.
    """
    return StyledDoc.from_json(
        (STYLED_DIR / f"{name}.json").read_text(encoding="utf-8")
    )


def _segment(name: str) -> Segmentation:
    doc = _styled(name)
    return segment_document(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))


def _parts_counter(seg: Segmentation, doc: StyledDoc) -> Counter:
    """How many parts claim each block index. A partition means all ones."""
    counts: Counter = Counter()
    hull = seg.front.hull(seg.first_index)
    if hull is not None:
        counts.update(hull.indices)
    if seg.body is not None:
        counts.update(seg.body.indices)
    back_span = seg.back.span
    if back_span is not None:
        counts.update(back_span.indices)
    for annex in seg.annexes:
        counts.update(annex.span.indices)
    return counts


def test_sample_inventory_is_complete():
    """15 samples, 15 goldens — a new sample must bring a golden with it."""
    assert len(SAMPLES) == 15
    goldens = sorted(p.stem for p in SEGMENT_DIR.glob("*.json"))
    assert goldens == SAMPLES


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_matches(name: str):
    """The segmenter's output is byte-identical to the committed golden."""
    golden = (SEGMENT_DIR / f"{name}.json").read_text(encoding="utf-8")
    assert _segment(name).to_json() == golden, (
        f"segmentation for {name} changed; if intended, run "
        f"`python3 scripts/regen_goldens.py --kind=segment` and review the diff"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_roundtrips(name: str):
    """`from_dict(to_dict())` reproduces the golden exactly."""
    data = json.loads((SEGMENT_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert (
        Segmentation.from_dict(data).to_json()
        == json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_determinism(name: str):
    """Same input ⇒ identical output (plan invariant #4)."""
    doc = _styled(name)
    meta = extract_metadata(doc, filename=f"{name}.docx")
    first = segment_document(doc, metadata=meta).to_json()
    second = segment_document(doc, metadata=meta).to_json()
    assert first == second


@pytest.mark.parametrize("name", SAMPLES)
def test_no_text_lost(name: str):
    """Every non-empty block lands in some part (plan §9.2, no loss).

    The half of text conservation that catches an over-narrow boundary: a
    front-matter rule that stops one block early strands that block in no part
    at all, and nothing downstream would ever emit it.
    """
    doc = _styled(name)
    seg = segment_document(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))
    non_empty = {
        b.index for b in doc.blocks if not (hasattr(b, "is_empty") and b.is_empty)
    }
    missing = sorted(non_empty - seg.covered)
    assert not missing, f"{name}: blocks in no part at all: {missing[:10]}"


@pytest.mark.parametrize("name", SAMPLES)
def test_no_text_duplicated(name: str):
    """No block lands in two parts (plan §9.2, no duplication).

    The other half. An over-wide boundary would let Cycles 5 and 6 emit the
    same paragraph twice — as an ementa *and* as body text — which validates
    happily and is silently wrong.
    """
    doc = _styled(name)
    seg = segment_document(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))
    duplicated = sorted(i for i, n in _parts_counter(seg, doc).items() if n > 1)
    assert not duplicated, f"{name}: blocks claimed by two parts: {duplicated[:10]}"


@pytest.mark.parametrize("name", SAMPLES)
def test_parts_are_a_partition(name: str):
    """Front, body, back and annexes partition the document exactly."""
    doc = _styled(name)
    seg = segment_document(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))
    counts = _parts_counter(seg, doc)
    all_indices = {b.index for b in doc.blocks}
    assert set(counts) <= all_indices, f"{name}: part covers a non-existent block"
    assert all(n == 1 for n in counts.values())


@pytest.mark.parametrize("name", SAMPLES)
def test_spans_are_within_the_document(name: str):
    """No span points outside the document's block indices."""
    doc = _styled(name)
    seg = segment_document(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))
    valid = {b.index for b in doc.blocks}
    spans = list(seg.front.parts)
    if seg.body is not None:
        spans.append(seg.body)
    if seg.back.span is not None:
        spans.append(seg.back.span)
    spans.extend(a.span for a in seg.annexes)
    for span in spans:
        assert span.start <= span.end
        assert span.start in valid and span.end in valid


@pytest.mark.parametrize("name", SAMPLES)
def test_parts_are_in_document_order(name: str):
    """Front precedes body precedes back; annexes come last.

    Cycle 6 emits an annex as a *sibling document*, so an annex that began
    before the signature would mean the primary document had been cut in the
    wrong place.
    """
    doc = _styled(name)
    seg = segment_document(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))
    hull = seg.front.hull(seg.first_index)
    if hull is not None and seg.body is not None:
        assert hull.end < seg.body.start
    for annex in seg.annexes:
        if seg.body is not None:
            assert seg.body.end < annex.span.start


@pytest.mark.parametrize("name", BARE_SAMPLES)
def test_bare_documents_have_no_front_or_back_matter(name: str):
    """The cycle's exit criterion: zero false positives on a bare document.

    `CARNE_LEAO` is a taxpayer-facing web page, not a legal act — no epigraph,
    no ementa, no preamble, no signature, no annex. Every rule in this cycle
    must decline to fire on it. It is the one sample where a *positive* result
    is unambiguously a bug, which is what makes it the cycle's best test.
    """
    seg = _segment(name)
    assert seg.front.is_empty, seg.front
    assert seg.back.is_empty, seg.back
    assert seg.annexes == ()
    assert seg.body is not None, "a bare document is all body"


@pytest.mark.parametrize("name", SAMPLES)
def test_annex_ordinals_are_sequential(name: str):
    """Annex ordinals run 1..N in document order, feeding the `!anexoN` URN."""
    seg = _segment(name)
    assert [a.ordinal for a in seg.annexes] == list(range(1, len(seg.annexes) + 1))
    for annex in seg.annexes:
        assert annex.fragment == f"anexo{annex.ordinal}"


@pytest.mark.parametrize("name", SAMPLES)
def test_signature_spans_do_not_overlap(name: str):
    """Signature blocks are disjoint and in document order."""
    seg = _segment(name)
    previous_end = -1
    for signature in seg.back.signatures:
        assert signature.span.start > previous_end, seg.back.signatures
        previous_end = signature.span.end


@pytest.mark.parametrize("name", SAMPLES)
def test_profile_is_recorded(name: str):
    """Every segmentation names the profile that produced it.

    Cycle 4b's telemetry reads this: a segmentation is only interpretable
    alongside the profile whose patterns produced it, because the annex and
    enacting-formula rules are profile-gated.
    """
    seg = _segment(name)
    assert seg.profile
    assert seg.source == f"{name}.docx"
