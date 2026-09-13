"""A truthful account of flatness — Cycle 1 of the corpus-233 hardening plan.

Confidence `0.00` was doing double duty. It is emitted both when a document has
no structure and when evidence fusion found no *candidate* at all, and the
artifact did not separate them — so a downstream consumer could not tell a
genuinely unstructured document from one whose structure was not recognised.
Plan §1.2 is that finding; this module pins the repair.

Four things are asserted here, and the third is the one that would catch a
regression nobody was looking for:

1. **Every flat tree carries a cause**, and every non-flat tree carries none.
2. **The vocabulary is closed and every code is occupied** — measured over the
   233-document corpus, not asserted.
3. **`span_coverage` is what stops `no_candidate` being read as "unstructured"**.
   82 of the corpus's 86 flat documents have a body span covering less than half
   the document; the median is 9%. A taxonomy without this field would report
   most of the corpus's flatness as an absence of structure when the real story
   is a truncated body span.
4. **The cause is derived, never causal.** Nothing here feeds back into
   inference, so no tree's shape depends on it — `test_measured_shape` and the
   hierarchy goldens are the independent check, and they did not move.

The corpus documents are **not** in `samples/`; they are research data outside
the repository. Every assertion that needs one skips without it, the same
graceful degradation `requires_nested`, `requires_linker` and Cycle 2's
`requires_corpus` already apply.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.corpus import DocumentOutcome, CorpusReport, genre_of
from lexml_nonstat.hierarchy import FLAT_CAUSES, infer_hierarchy
from lexml_nonstat.hierarchy.evidence import DocSignals
from lexml_nonstat.hierarchy.tree import build_tree
from lexml_nonstat.ingest import Inline, StyledPara, read_docx

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: The 233-document corpus this cycle measured. Outside the repository by
#: design, so every assertion that needs a real document skips without it.
CORPUS = REPO_ROOT.parent / "br-taxqa-r_v2.0" / "original" / "nao_articulados"

requires_corpus = pytest.mark.skipif(
    not CORPUS.is_dir(),
    reason=f"the 233-document corpus is not present at {CORPUS} (research data, not a fixture)",
)

#: The partition measured over the corpus, rules-only. Written from the
#: measurement rather than from the implementation: if a change moves one of
#: these, that is a behaviour change to review, not a number to update.
EXPECTED_PARTITION = {
    "no_candidate": 52,
    "all_rejected": 15,
    "too_few_sections": 8,
    "empty_body_span": 11,
}
EXPECTED_FLAT = 86
EXPECTED_TOTAL = 233


def _para(index: int, text: str, **kw) -> StyledPara:
    return StyledPara(index=index, inlines=(Inline(text=text),), **kw)


@pytest.fixture(scope="module")
def corpus_bodies():
    """Every corpus document's body tree, inferred once."""
    if not CORPUS.is_dir():
        pytest.skip("corpus absent")
    return {
        p.stem: infer_hierarchy(read_docx(p)).body for p in sorted(CORPUS.glob("*.docx"))
    }


# --------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------


def test_flat_causes_is_a_closed_vocabulary() -> None:
    """Four codes, each occupied by real documents.

    Deliberately *not* five. A "scores too weak" code is unreachable: a
    solitary label is refused by `unify_levels` before `_score` is called, so a
    weak score never becomes an assignment. Shipping it would invite a consumer
    to handle a case that cannot arise.
    """
    assert FLAT_CAUSES == (
        "no_candidate",
        "all_rejected",
        "too_few_sections",
        "empty_body_span",
    )
    assert len(set(FLAT_CAUSES)) == len(FLAT_CAUSES)


def test_a_default_docsignals_carries_no_cause() -> None:
    """The inert default the round-trip contract depends on.

    `segments/roundtrip.py` rebuilds trees from XML with no signals at all, and
    `test_segments_roundtrip` asserts `tree.signals == DocSignals()` against
    freshly-constructed defaults precisely so that a new field extends that
    test rather than breaking it.
    """
    assert DocSignals().flat_cause == ""
    assert DocSignals().span_coverage == 0.0


def test_the_cause_survives_a_round_trip() -> None:
    signals = DocSignals(flat_cause="no_candidate", span_coverage=0.1234)
    restored = DocSignals.from_dict(signals.to_dict())
    assert restored.flat_cause == "no_candidate"
    assert restored.span_coverage == 0.1234
    assert restored == signals


def test_to_dict_carries_both_fields() -> None:
    data = DocSignals().to_dict()
    assert data["flat_cause"] == ""
    assert data["span_coverage"] == 0.0


# --------------------------------------------------------------------------
# Each cause, at its own smallest reproduction
# --------------------------------------------------------------------------


def test_empty_span_is_empty_body_span() -> None:
    """`build_tree([])` is flat for a reason, and says which.

    Without this the honest answer for `ad_srf_22` — a document whose whole
    content is front and back matter — would be an empty cause on a flat tree,
    which reads as "no reason recorded".
    """
    tree = build_tree([])
    assert tree.flat is True
    assert tree.signals.flat_cause == "empty_body_span"


def test_no_candidate_when_nothing_is_heading_shaped() -> None:
    """Prose with no labels, no styles and no declared headings.

    The test is `is_candidate`, not an empty list: `collect_candidates` appends
    a `Candidate` for every non-empty paragraph and lets the property decide
    which could open a section, so the raw list is never empty here.
    """
    blocks = [
        _para(0, "Trata-se de consulta formulada pelo interessado acerca da matéria."),
        _para(1, "Não há o que reparar na conclusão adotada pela unidade de origem."),
    ]
    tree = build_tree(blocks)
    assert tree.flat is True
    assert tree.signals.flat_cause == "no_candidate"


def test_all_rejected_when_candidates_are_refused() -> None:
    """A lone `2.` with no `1.`: `validate_top_series` refuses it.

    `adn_cst_25_19891213` is the corpus document with exactly this shape, and
    the refusal is correct — the first point is unlabelled, inside the DECLARA
    paragraph, so the series really does start at 2.
    """
    blocks = [
        _para(0, "2. Conseqüentemente, o representante comercial não pode optar."),
    ]
    tree = build_tree(blocks)
    assert tree.flat is True
    assert tree.signals.flat_cause == "all_rejected"
    assert tree.signals.rejected, "a rejection cause must name its rejections"


def test_too_few_sections_when_damping_decides() -> None:
    """One strong section is not a shape — `document_confidence` damps it.

    This is the *only* way scoring produces flatness. Verified over the whole
    corpus by `test_no_corpus_document_has_a_sub_threshold_mean`.
    """
    blocks = [
        _para(0, "1. DO RELATÓRIO", outline_level=1),
        _para(1, "Trata-se de consulta sobre a incidência do tributo."),
    ]
    tree = build_tree(blocks)
    assert tree.flat is True
    assert tree.signals.flat_cause == "too_few_sections"
    assert tree.confidence < 0.5


# --------------------------------------------------------------------------
# The samples: every flat tree has a cause, every structured tree has none
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_every_flat_tree_carries_a_cause(name: str) -> None:
    """The cycle's exit criterion, at the sample level."""
    result = infer_hierarchy(read_docx(SAMPLES_DIR / f"{name}.docx"))
    for tree in result.trees:
        if tree.flat:
            assert tree.signals.flat_cause in FLAT_CAUSES, (
                f"{name}: a flat tree with no cause is the silence this cycle "
                f"exists to remove"
            )
        else:
            assert tree.signals.flat_cause == "", (
                f"{name}: a structured tree has no reason to be flat"
            )


@pytest.mark.parametrize("name", SAMPLES)
def test_span_coverage_is_a_ratio(name: str) -> None:
    result = infer_hierarchy(read_docx(SAMPLES_DIR / f"{name}.docx"))
    assert 0.0 <= result.body.signals.span_coverage <= 1.0


@pytest.mark.parametrize("name", SAMPLES)
def test_annexes_carry_no_span_coverage(name: str) -> None:
    """An annex is a different document travelling with this one.

    Its size as a fraction of the whole file is not a meaningful ratio — the
    same reasoning that gives annexes `section_res=()` at the call site.
    """
    result = infer_hierarchy(read_docx(SAMPLES_DIR / f"{name}.docx"))
    for annex in result.annexes:
        assert annex.tree.signals.span_coverage == 0.0


# --------------------------------------------------------------------------
# Genre grouping — plan Cycle 1 deliverable 2
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,expected",
    [
        ("ad_pgfn_13_20111220.docx", "ad_pgfn"),
        ("sc_cosit_100_20200928.docx", "sc_cosit"),
        ("adn_cst_8_19790228.docx", "adn_cst"),
        ("nota_pgfn_crj_1040_2015.docx", "nota_pgfn_crj"),
        ("/a/path/pn_cst_38_19801031.docx", "pn_cst"),
        ("REsp_1306393.docx", "REsp"),
        # No digit-initial segment: the whole stem is the genre.
        ("declaracao_de_servicos_medicos_e_de_saude_DMED.docx",
         "declaracao_de_servicos_medicos_e_de_saude_DMED"),
    ],
)
def test_genre_of_derives_the_plan_table_genres(source: str, expected: str) -> None:
    """The genres plan §1.2's table is built from."""
    assert genre_of(source) == expected


def test_by_genre_flatness_is_deterministic() -> None:
    """Flat count descending, then name — invariant #4."""
    outcomes = tuple(
        DocumentOutcome(source=s, ok=True, route="generico", flat=f, genre=g)
        for s, g, f in [
            ("a_1.docx", "alpha", True),
            ("b_1.docx", "beta", True),
            ("b_2.docx", "beta", True),
            ("c_1.docx", "gamma", False),
        ]
    )
    report = CorpusReport(outcomes=outcomes)
    assert report.by_genre_flatness() == (
        ("beta", 2, 2),
        ("alpha", 1, 1),
        ("gamma", 1, 0),
    )


def test_by_flat_cause_counts_only_flat_documents() -> None:
    """A structured document must not appear as an empty-string bucket."""
    outcomes = (
        DocumentOutcome(
            source="a.docx", ok=True, route="generico", flat=True,
            flat_cause="no_candidate",
        ),
        DocumentOutcome(
            source="b.docx", ok=True, route="generico", flat=True,
            flat_cause="no_candidate",
        ),
        DocumentOutcome(
            source="c.docx", ok=True, route="generico", flat=True,
            flat_cause="all_rejected",
        ),
        DocumentOutcome(source="d.docx", ok=True, route="generico", flat=False),
    )
    report = CorpusReport(outcomes=outcomes)
    assert report.by_flat_cause() == (("no_candidate", 2), ("all_rejected", 1))
    assert sum(n for _, n in report.by_flat_cause()) == 3


def test_genre_falls_back_to_the_source_when_unset() -> None:
    """An outcome built before the field existed still groups correctly."""
    report = CorpusReport(
        outcomes=(
            DocumentOutcome(source="ad_pgfn_3_20080918.docx", ok=True,
                            route="generico", flat=True),
        )
    )
    assert report.by_genre_flatness() == (("ad_pgfn", 1, 1),)


# --------------------------------------------------------------------------
# The corpus — the measurement this cycle is accountable to
# --------------------------------------------------------------------------


@requires_corpus
def test_the_corpus_flat_count(corpus_bodies) -> None:
    """86 of 233, rules-only. Amendment A-3.3's baseline, re-verified."""
    assert len(corpus_bodies) == EXPECTED_TOTAL
    assert sum(1 for b in corpus_bodies.values() if b.flat) == EXPECTED_FLAT


@requires_corpus
def test_the_corpus_cause_partition(corpus_bodies) -> None:
    """The measured partition, code by code.

    Not a summary statistic: if a change moves one bucket into another, this
    says which two, which is the thing a reader needs.
    """
    counts = Counter(
        b.signals.flat_cause for b in corpus_bodies.values() if b.flat
    )
    assert dict(counts) == EXPECTED_PARTITION
    assert sum(counts.values()) == EXPECTED_FLAT


@requires_corpus
def test_every_corpus_flat_document_has_a_cause(corpus_bodies) -> None:
    """Zero unexplained — the exit criterion, over the real corpus."""
    unexplained = [
        stem
        for stem, body in corpus_bodies.items()
        if body.flat and body.signals.flat_cause not in FLAT_CAUSES
    ]
    assert unexplained == []


@requires_corpus
def test_no_corpus_document_has_a_sub_threshold_mean(corpus_bodies) -> None:
    """Why `FLAT_CAUSES` has no "scores too weak" code.

    A solitary label (0.25) is refused before it is scored, so every assignment
    sits in the strong band. Measured: the lowest mean across the corpus is
    0.7553. If this ever fails, the fifth code has become reachable and the
    vocabulary needs it.
    """
    for stem, body in corpus_bodies.items():
        if body.flat and body.signals.flat_cause == "too_few_sections":
            assert body.signals.n_blocks > 0
            # Damped by section count, not by weak scores: recover the mean.
            mean = body.confidence * 3
            assert mean >= 0.5, f"{stem}: mean {mean} is below the threshold"


@requires_corpus
def test_truncation_is_visible_in_span_coverage(corpus_bodies) -> None:
    """82 of 86 flat documents have a body span under half the document.

    This is the number that makes `no_candidate` legible. Reporting 52
    documents as "no structure found" without it would be misleading: the span
    was too small to contain a candidate in most of them.
    """
    flat = [b for b in corpus_bodies.values() if b.flat]
    assert sum(1 for b in flat if b.signals.span_coverage < 0.5) == 82


@requires_corpus
def test_ad_pgfn_is_flat_but_proposes_nothing(corpus_bodies) -> None:
    """Plan §1.2's strongest recogniser-gap signal — which turned out not to be one.

    14 of 15 flat, every one `no_candidate` with nothing rejected: nothing
    heading-shaped is ever proposed. The investigation in
    `docs/20260913_232034_ad_pgfn_adn_cst_flatness_investigation.md` establishes
    that this is a genuine absence of structure, not a gap.
    """
    pgfn = {s: b for s, b in corpus_bodies.items() if s.startswith("ad_pgfn")}
    assert len(pgfn) == 15
    flat = {s: b for s, b in pgfn.items() if b.flat}
    assert len(flat) == 14
    assert set(s for s in pgfn if not pgfn[s].flat) == {"ad_pgfn_13_20111220"}
    for stem, body in flat.items():
        assert body.signals.flat_cause == "no_candidate", stem
        assert body.signals.rejected == (), f"{stem}: nothing was proposed to reject"
