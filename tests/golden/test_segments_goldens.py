"""Byte-stable segment goldens — the ninth golden layer, and the last artifact.

`tests/golden/segments/*.jsonl` is what a consumer actually receives: one JSON
object per citable unit, with the urn it cites by, the breadcrumb it reads in
context, and the text. The XML goldens pin what the *emitters* write; these pin
what a *reader* gets out again, which is a different claim and the one §2.4's
segmentation experiment was really about.

Written from the model on the flat emitter's ids — the primary path (§6.1),
addressed the way `--kind=generico` writes it — so a urn in
`tests/golden/segments/pn_cst_38_19801031.jsonl` resolves against
`tests/golden/generico/pn_cst_38_19801031.xml` sitting beside it. That is
asserted here, across the two golden directories, rather than assumed.

The nested emitter's segments are deliberately **not** committed a second time.
Cross-emitter equality is the three-way oracle's job
(`tests/regression/test_three_way_oracle.py`), and a golden restating it would
move whenever the *other* emitter changed — a golden diff that means nothing is
worse than no golden.

Plan §9.4 — these regenerate only via
`python3 scripts/regen_goldens.py --kind=segments`, so any diff is a reviewed
behaviour change.

**Read from disk, not recomputed.** Every assertion below opens the committed
file. A golden test that re-derives its expectation from the same code it is
checking proves only that the code is deterministic.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import words
from lexml_nonstat.segments import Segment, segments_from_model, to_jsonl

REPO_ROOT = Path(__file__).resolve().parents[2]
SEGMENTS_DIR = REPO_ROOT / "tests" / "golden" / "segments"
GENERICO_DIR = REPO_ROOT / "tests" / "golden" / "generico"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))
LEXML_NS = "http://www.lexml.gov.br/1.0"


def golden_files(stem: str) -> list[Path]:
    """The committed files for one sample: its own, then each annex's."""
    return sorted(
        SEGMENTS_DIR.glob(f"{stem}.jsonl"),
    ) + sorted(SEGMENTS_DIR.glob(f"{stem}.anexo*.jsonl"))


def load(path: Path) -> tuple[Segment, ...]:
    return tuple(
        Segment.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def test_every_sample_has_a_golden():
    """Fifteen samples, fifteen goldens — plus `port_mf_277`'s annex.

    A missing golden is the one failure a per-sample parametrisation cannot
    report, because the parameter that would have caught it is generated from
    the same glob that is empty.
    """
    assert len(SAMPLES) == 15
    for stem in SAMPLES:
        assert golden_files(stem), f"{stem} has no committed segments golden"
    assert (SEGMENTS_DIR / "port_mf_277_20180607.anexo1.jsonl").exists()
    assert len(list(SEGMENTS_DIR.glob("*.jsonl"))) == 16


@pytest.mark.parametrize("stem", SAMPLES)
def test_golden_matches_current_output(stem):
    """T-41 — byte equality. The whole point of a golden."""
    model = build_model(read_docx(SAMPLES_DIR / f"{stem}.docx"), filename=f"{stem}.docx")
    rows = segments_from_model(model, emitter="generico")

    expected = {"": model.metadata.urn}
    for ordinal, annex in enumerate(model.annexes, start=1):
        expected[f".anexo{ordinal}"] = model.metadata.urn_with_fragment(annex.fragment)

    for suffix, document_urn in expected.items():
        path = SEGMENTS_DIR / f"{stem}{suffix}.jsonl"
        produced = to_jsonl(s for s in rows if s.document == document_urn)
        assert path.read_text(encoding="utf-8") == produced, (
            f"{path.name} is stale — run "
            f"`python3 scripts/regen_goldens.py --kind=segments` and review the diff"
        )


@pytest.mark.parametrize("stem", SAMPLES)
def test_golden_reparses_to_equal_segments(stem):
    """T-42 — JSONL is lossless: `from_dict(json.loads(line))` is the record.

    A writer that dropped a field would still produce a byte-stable golden;
    only reparsing catches it.
    """
    for path in golden_files(stem):
        text = path.read_text(encoding="utf-8")
        rows = load(path)
        assert rows, f"{path.name} is empty"
        assert to_jsonl(rows) == text


@pytest.mark.parametrize("stem", SAMPLES)
def test_golden_breadcrumbs_complete(stem):
    """T-43 — Rule A end to end, read from disk.

    Every segment's breadcrumb must have exactly one entry per ancestor, and
    each of those ancestors must itself be present as a segment. That is the
    §2.4 failure the whole id scheme exists to prevent: a breadcrumb silently
    missing its middle ancestor, which reads as plausible and is wrong.
    """
    for path in golden_files(stem):
        rows = load(path)
        by_path = {s.path: s for s in rows if s.path}
        for segment in rows:
            assert len(segment.breadcrumb) == len(segment.path[:-1]), (
                f"{segment.urn}: breadcrumb of {len(segment.breadcrumb)} "
                f"for depth {len(segment.path) - 1}"
            )
            for depth in range(1, len(segment.path)):
                ancestor = by_path.get(segment.path[:depth])
                assert ancestor is not None, (
                    f"{segment.urn}: ancestor {segment.path[:depth]} is missing"
                )
                assert segment.breadcrumb[depth - 1] == ancestor.title


@pytest.mark.parametrize("stem", SAMPLES)
def test_golden_conserves_the_source_text(stem):
    """T-44 — Rule B end to end, read from disk.

    The committed segments carry every word of the emitted document, exactly
    once. Both directions: nothing lost, and nothing gained — the second half
    is what a cumulative-text implementation fails, and it is why
    `Segment.text` is own-text (spec decision R-5).
    """
    model = build_model(read_docx(SAMPLES_DIR / f"{stem}.docx"), filename=f"{stem}.docx")
    from lexml_nonstat.render import render_generico

    bundle = render_generico(model)

    from_goldens: Counter[str] = Counter()
    for path in golden_files(stem):
        for segment in load(path):
            from_goldens.update(segment.own_words)

    from_xml = Counter(words(bundle.texts))
    assert from_goldens == from_xml, (
        f"lost {sum((from_xml - from_goldens).values())}, "
        f"gained {sum((from_goldens - from_xml).values())}"
    )


@pytest.mark.parametrize("stem", SAMPLES)
def test_golden_urns_unique(stem):
    """T-45 — a urn addresses one thing. Across the whole bundle, not per file.

    Per-file uniqueness would be satisfied by a primary and an annex that both
    call their first section `pp1_agr1` — which is exactly why the annex gets
    its own id root (`anexo1_pp`) and its own URN fragment (§2.9).
    """
    urns = [s.urn for path in golden_files(stem) for s in load(path)]
    assert urns
    duplicates = [urn for urn, count in Counter(urns).items() if count > 1]
    assert not duplicates, f"duplicate urns: {duplicates[:5]}"


@pytest.mark.parametrize("stem", SAMPLES)
def test_golden_urns_resolve_against_the_committed_xml(stem):
    """A citation must find its element in the artifact shipped beside it.

    This crosses two golden directories on purpose. `tests/golden/segments/`
    and `tests/golden/generico/` are regenerated by the same command but by
    different code paths — the model walker and the emitter — and this is what
    would catch them drifting apart: an id the segmenter composes that the
    emitter never writes.
    """
    for path in golden_files(stem):
        xml_path = GENERICO_DIR / (path.name[: -len(".jsonl")] + ".xml")
        assert xml_path.exists(), f"no XML golden beside {path.name}"
        document = etree.parse(str(xml_path)).getroot()
        ids = {
            element.get("id")
            for element in document.iter()
            if element.get("id") is not None
        }
        identificacao = document.find(f".//{{{LEXML_NS}}}Identificacao")
        document_urn = identificacao.get("URN")

        for segment in load(path):
            assert segment.document == document_urn, (
                f"{segment.urn} claims a document the XML does not declare"
            )
            assert segment.id in ids, f"{segment.urn} points at no element"
            assert segment.urn == f"{document_urn}!{segment.id}"


@pytest.mark.parametrize("stem", SAMPLES)
def test_golden_is_utf8_and_unescaped(stem):
    """Portuguese is written as Portuguese — the Cycle 1–4 house style.

    `ensure_ascii=False`, so `Não` is three characters in the file rather than
    `N\\u00e3o`. A golden a human cannot read in a diff is a golden nobody
    reviews, and §9.4's whole policy rests on the diff being reviewed.
    """
    for path in golden_files(stem):
        raw = path.read_bytes()
        assert raw.decode("utf-8")
        assert b"\\u00" not in raw
        assert raw.endswith(b"\n")


def test_regions_and_body_are_both_represented():
    """Anti-vacuity: the goldens must contain both kinds of segment.

    Every property above would pass on a file containing only front matter —
    breadcrumbs trivially complete, paths trivially unique. `pn_cst_38` is the
    corpus's deepest document, so it is the one that proves the goldens hold
    real hierarchy rather than a flat list of epigraphs.
    """
    rows = load(SEGMENTS_DIR / "pn_cst_38_19801031.jsonl")
    assert any(s.is_region for s in rows), "no front/back regions"
    assert any(not s.is_region for s in rows), "no body sections"
    assert max(len(s.path) for s in rows) >= 4, "the deepest sample lost its depth"
    assert any(s.breadcrumb for s in rows), "nothing has ancestry"
