"""Byte-stable `Metadata` goldens for all 15 samples.

The companion to Cycle 1's `test_styled_goldens.py`, one layer up: those pin
what the reader saw, these pin what the extractor concluded from it.

Plan §9.4 — goldens regenerate only via `python3 scripts/regen_goldens.py`,
so any diff here is a reviewed behaviour change rather than a silent drift.

A golden alone is weak evidence (a golden containing a bug passes forever), so
this module also asserts the invariants that must hold regardless of what the
golden happens to say: every URN parses, every recorded provenance is one of
the sources the extractor can actually report, and `complete`/`missing` agree
with the fields they summarise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc
from lexml_nonstat.model import Metadata, extract_metadata, is_valid_urn, parse_urn

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"
METADATA_DIR = REPO_ROOT / "tests" / "golden" / "metadata"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: Every value `date_source` / `authority_source` are allowed to take. A new
#: source appearing without this list being updated is a change worth noticing.
DATE_SOURCES = {None, "epigraph", "header", "signature", "filename"}
AUTHORITY_SOURCES = {None, "epigraph", "preamble", "profile"}


def _styled(name: str) -> StyledDoc:
    """Load a sample from Cycle 1's golden rather than re-parsing the DOCX.

    Keeps this module fast and makes it depend on a committed artifact, so a
    metadata golden diff can never be caused by a reader change going
    unnoticed — that would show up in Cycle 1's goldens first.
    """
    return StyledDoc.from_json((STYLED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _extract(name: str) -> Metadata:
    return extract_metadata(_styled(name), filename=f"{name}.docx")


def test_sample_inventory_is_complete():
    """15 samples, 15 goldens — a new sample must bring a golden with it."""
    assert len(SAMPLES) == 15
    goldens = sorted(p.stem for p in METADATA_DIR.glob("*.json"))
    assert goldens == SAMPLES


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_matches(name: str):
    """The extractor's output is byte-identical to the committed golden."""
    golden = (METADATA_DIR / f"{name}.json").read_text(encoding="utf-8")
    assert _extract(name).to_json() == golden, (
        f"metadata for {name} changed; if intended, run "
        f"`python3 scripts/regen_goldens.py --kind=metadata` and review the diff"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_roundtrips(name: str):
    """`from_dict(to_dict())` reproduces the golden exactly."""
    data = json.loads((METADATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert Metadata.from_dict(data).to_json() == json.dumps(
        data, indent=2, ensure_ascii=False
    ) + "\n"


@pytest.mark.parametrize("name", SAMPLES)
def test_determinism(name: str):
    """Same input ⇒ identical output (plan invariant #4)."""
    doc = _styled(name)
    first = extract_metadata(doc, filename=f"{name}.docx").to_json()
    second = extract_metadata(doc, filename=f"{name}.docx").to_json()
    assert first == second


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_urn_is_wellformed(name: str):
    """Every golden's URN parses — including the incomplete ones.

    This is the invariant behind the spec's decision #2: a document with no
    number and no date still yields a *syntactically valid* URN, so nothing
    downstream has to special-case it.
    """
    meta = _extract(name)
    assert is_valid_urn(meta.urn), meta.urn
    parts = parse_urn(meta.urn)
    assert parts.locality == meta.locality
    if meta.date is not None:
        assert parts.date == meta.date
    if meta.number is not None:
        assert parts.number == meta.number


@pytest.mark.parametrize("name", SAMPLES)
def test_provenance_is_recorded_and_known(name: str):
    """Provenance is present whenever the value it explains is."""
    meta = _extract(name)
    assert meta.date_source in DATE_SOURCES
    assert meta.authority_source in AUTHORITY_SOURCES
    # A value without a recorded source would make a corpus-scale audit of the
    # extraction chain impossible, which is the whole point of keeping them.
    assert (meta.date is None) == (meta.date_source is None)
    assert (meta.authority is None) == (meta.authority_source is None)


@pytest.mark.parametrize("name", SAMPLES)
def test_complete_agrees_with_missing(name: str):
    """`complete` is exactly `missing == ()`, and `missing` names real gaps."""
    meta = _extract(name)
    assert meta.complete == (meta.missing == ())
    for gap in meta.missing:
        assert getattr(meta, gap) in (None, "")


@pytest.mark.parametrize("name", SAMPLES)
def test_proprietary_fields_point_at_real_paragraphs(name: str):
    """Each captured field cites the paragraph index it came from.

    Cycle 3 segments the front matter and needs to skip exactly those
    paragraphs; an index that does not resolve would silently duplicate the
    text into the body.
    """
    doc = _styled(name)
    meta = extract_metadata(doc, filename=f"{name}.docx")
    by_index = {p.index: p for p in doc.paragraphs}
    for field in meta.proprietary:
        assert field.source_index in by_index, field
        assert field.value in by_index[field.source_index].text
