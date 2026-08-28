"""The Statutory Viability Analyzer — the refusals it must keep making.

Plan §4.4 states this cycle's exit criterion as a number that reads like a
failure: **14 of the 15 samples must route to `generico`**. Routing earns its
place by refusing. Getting ``port_mf_277`` right is one Portaria; getting
``parecer_93`` wrong publishes the Constitution's ``Art. 40`` as an article
*of a legal opinion*, and nothing downstream can tell the document was misread.

What this module protects, in order of severity:

* **The route table itself** (§4.4). One parametrised assertion over all 15
  samples, written as a literal so a change of route is a diff a reviewer reads
  rather than a count that still says "14".
* **Coverage is measured over the body, after the annex split** (§4.2).
  ``port_mf_277`` is 138 blocks, of which 132 are ``ANEXO ÚNICO``; its two
  articles cover 1.4% of the document and 100% of the body. Measure the wrong
  span and the only articulated document in the corpus routes to `generico`.
* **The gates are the reason, not decoration** (§4.2). ``route == "norma"``
  holds exactly when all four gates hold — so a future contributor cannot add
  a fifth influence without the evidence saying so.
* **A genre never decides alone** (§2.7). ``port_mf_454`` carries the highest
  prior in the table (*portaria*, 0.45) and has no article at all.
* **A rendering blocker never changes a route** (amendment A-R.7). Asking for
  ``generico-aninhado`` against schemas that cannot express it records the
  fact and leaves the route alone: routing is about what the document *is*,
  not how it is written out.
* **Determinism under the pinned referee** (§9.3, invariant #4). The whole
  suite runs with ``--referee=none``, and ``NullReferee()`` must be
  byte-identical to no referee at all — of the entire verdict, bookkeeping
  fields included, not merely of the route.

The corpus is 15 documents standing in for 300+ unseen ones, so the invariant
tests below (blocker codes known, details human-readable, ``articles_own``
identity, JSON round-trip, never raises) are deliberately shape assertions that
hold for any document, not for these fifteen.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import pytest

from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara, read_docx
from lexml_nonstat.referee import NullReferee
from lexml_nonstat.routing import (
    BLOCKER_ALL_ARTICLES_QUOTED,
    BLOCKER_CODES,
    BLOCKER_LOW_COVERAGE,
    BLOCKER_NESTED_UNAVAILABLE,
    BLOCKER_NON_MONOTONIC,
    BLOCKER_NO_ARTICLES,
    BLOCKER_TOP_LEVEL_TABLE,
    COVERAGE_MIN,
    EMITTERS,
    ROUTES,
    ArticleCensus,
    StatutoryViability,
    articulation_coverage,
    assess_viability,
)
from lexml_nonstat.validate import probe_capabilities

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"

#: Every sample in the corpus, by stem.
SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

PARECER_93 = "parecer_93_2018_decor_cgu_agu"
PAR_COSIT_26 = "par_cosit_26_20000629"
PORT_MF_277 = "port_mf_277_20180607"
PORT_MF_454 = "port_mf_454_19770825"
SUMULA_STJ_125 = "sumula_stj_125"

_DOCS: dict[str, StyledDoc] = {}
_VERDICTS: dict[tuple, StatutoryViability] = {}


def load(name: str) -> StyledDoc:
    """One sample, read once per session. ``parecer_93`` is 428 blocks."""
    if name not in _DOCS:
        _DOCS[name] = read_docx(SAMPLES_DIR / f"{name}.docx")
    return _DOCS[name]


def assess(name: str, **kwargs) -> StatutoryViability:
    """The verdict for a sample, memoised per keyword combination.

    Never used by the determinism tests — those call the analyzer afresh, which
    is the whole point of them.
    """
    key = (name, tuple(sorted(kwargs.items())))
    if key not in _VERDICTS:
        _VERDICTS[key] = assess_viability(load(name), **kwargs)
    return _VERDICTS[key]


def para(index: int, text: str, **kwargs) -> StyledPara:
    """A synthetic paragraph, for shapes the corpus does not contain."""
    return StyledPara(inlines=(Inline(text),), index=index, **kwargs)


# ---------------------------------------------------------------------------
# §4.4 — the route table
# ---------------------------------------------------------------------------


class Route(NamedTuple):
    """One row of §4.4's expected outcome, written out as a literal."""

    route: str
    confidence: float
    found: int
    quoted: int
    own: int
    coverage: float
    blockers: tuple[str, ...]


#: The cycle's headline exit criterion (plan §4.4): fourteen refusals and one
#: statute. Written as literals rather than derived, so that a rule change
#: shows up here as a reviewable diff instead of as a still-passing count.
EXPECTED: dict[str, Route] = {
    "REsp_1306393": Route("generico", 0.95, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    "ad_pgfn_13_20111220": Route("generico", 0.85, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    "ad_pgfn_3_20080918": Route("generico", 0.85, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    "ad_srf_22_19970430": Route("generico", 0.85, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    "ad_srf_3_19990107": Route("generico", 0.85, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    "adn_cosit_19_20001025": Route("generico", 0.85, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    "adn_cst_10_19910417": Route("generico", 0.85, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    PAR_COSIT_26: Route(
        "generico",
        1.0,
        5,
        5,
        0,
        0.0,
        (BLOCKER_ALL_ARTICLES_QUOTED, BLOCKER_NON_MONOTONIC, BLOCKER_TOP_LEVEL_TABLE),
    ),
    PARECER_93: Route(
        "generico",
        1.0,
        25,
        25,
        0,
        0.0,
        (BLOCKER_ALL_ARTICLES_QUOTED, BLOCKER_NON_MONOTONIC),
    ),
    "pn_cst_38_19801031": Route("generico", 0.9, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    # The one document in the corpus that may be published as a Norma.
    PORT_MF_277: Route("norma", 1.0, 2, 0, 2, 1.0, ()),
    PORT_MF_454: Route("generico", 0.6, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO": Route(
        "generico", 0.9, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)
    ),
    "sumula_carf_42": Route("generico", 0.95, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES,)),
    SUMULA_STJ_125: Route(
        "generico", 1.0, 0, 0, 0, 0.0, (BLOCKER_NO_ARTICLES, BLOCKER_TOP_LEVEL_TABLE)
    ),
}


def test_the_expected_table_covers_the_whole_corpus() -> None:
    """A guard on the guard: a new sample must not slip past §4.4 unasserted."""
    assert tuple(sorted(EXPECTED)) == SAMPLES == tuple(sorted(SAMPLES))
    assert len(SAMPLES) == 15


@pytest.mark.parametrize("name", SAMPLES)
def test_expected_route_table(name: str) -> None:
    """Plan §4.4, the cycle's exit criterion: 14 refusals and one statute.

    Asserted per sample rather than as an aggregate count, because "14 of 15"
    stays true when two documents swap routes.
    """
    expected = EXPECTED[name]
    verdict = assess(name)
    actual = Route(
        verdict.route,
        verdict.confidence,
        verdict.articles_found,
        verdict.articles_quoted,
        verdict.articles_own,
        verdict.coverage,
        verdict.blocker_codes,
    )
    assert actual == expected


def test_exactly_one_sample_is_statutory() -> None:
    """§4.4 in one line — the shape of the corpus, not of any one document."""
    statutory = [n for n in SAMPLES if assess(n).is_statutory]
    assert statutory == [PORT_MF_277]


# ---------------------------------------------------------------------------
# §2.5/§2.6 — the two opinions that quote statutes they do not enact
# ---------------------------------------------------------------------------


def test_parecer_93_is_not_norma() -> None:
    """§2.5's worked disaster: 25 `Art.` matches, every one quoted statute.

    A naive paragraph-initial rule would articulate the Constitution's
    ``Art. 40`` inside a legal opinion. The blocker has to be the *reason*
    given — `all_articles_quoted`, not a bare low confidence.
    """
    verdict = assess(PARECER_93)
    assert verdict.route == "generico"
    assert not verdict.is_statutory
    assert verdict.has_blocker(BLOCKER_ALL_ARTICLES_QUOTED)
    assert verdict.articles_found == 25
    assert verdict.articles_quoted == 25
    assert verdict.articles_own == 0
    assert verdict.evidence["census"]["own"] == []


def test_par_cosit_26_is_not_norma() -> None:
    """§2.6's residual case: no indentation at all, so the textual cues carry it.

    Its five quoted articles are ``2, 3, 16, 18, 52`` — a series no document
    enacts, which is why the census records the values and not just the count.
    """
    verdict = assess(PAR_COSIT_26)
    assert verdict.route == "generico"
    assert verdict.has_blocker(BLOCKER_ALL_ARTICLES_QUOTED)
    assert verdict.articles_found == 5
    assert verdict.articles_quoted == 5
    assert verdict.articles_own == 0
    assert tuple(verdict.evidence["census"]["values"]) == (2, 3, 16, 18, 52)


# ---------------------------------------------------------------------------
# The one statute, and the measurement that makes it possible
# ---------------------------------------------------------------------------


def test_port_mf_277_routes_to_norma_with_annex() -> None:
    """The single articulated document: two own articles and an annex.

    No blocker at all — not even a non-vetoing one — because a `norma` verdict
    with a recorded objection is the shape a reviewer would have to read twice.
    """
    verdict = assess(PORT_MF_277)
    assert verdict.route == "norma"
    assert verdict.is_statutory
    assert verdict.has_anexos is True
    assert verdict.coverage == 1.0
    assert verdict.articles_own == 2
    assert verdict.articles_quoted == 0
    assert verdict.numbering_monotonic is True
    assert verdict.blockers == ()
    assert verdict.evidence["annexes"] == ["ANEXO ÚNICO"]


def test_coverage_measured_after_annex_split() -> None:
    """Plan §4.2's central safety property, and the reason `port_mf_277` works.

    The document is 138 blocks, 132 of which are ``ANEXO ÚNICO``; its body is
    2. Two articles against the *document* cover 1.4% and the gate refuses;
    against the **body span** they cover 100%. Measuring the wrong span loses
    the only articulated document in the corpus, silently.
    """
    doc = load(PORT_MF_277)
    assert len(doc.blocks) == 138
    verdict = assess(PORT_MF_277)
    assert verdict.evidence["body_blocks"] == 2
    assert verdict.coverage == 1.0
    # Explicitly: the annex is not part of what coverage was measured over.
    assert verdict.evidence["body_blocks"] < len(doc.blocks)
    assert verdict.has_anexos is True


# ---------------------------------------------------------------------------
# The gates, on shapes the corpus does not contain
# ---------------------------------------------------------------------------


def test_coverage_gate_rejects_low_coverage() -> None:
    """§4.2's gate on the shape it was written for — a document *ending* in
    articles rather than made of them.

    No sample has it: fourteen have no own article at all and the fifteenth
    scores 1.0. So the gate is exercised twice, synthetically. First on the
    arithmetic — an own article at 90% of a 100-block body claims a tenth —
    and then end-to-end, on a document whose two articles sit at the tail of
    forty blocks of prose, which is precisely the shape of an argument that
    quotes a statute at its close.
    """
    census_ = ArticleCensus(found=(90,), own=(90,), values=(1,), monotonic=True)
    coverage = articulation_coverage(census_, list(range(100)))
    assert coverage == pytest.approx(0.1)
    assert coverage < COVERAGE_MIN

    blocks = [
        para(0, "PORTARIA Nº 9, DE 2 DE MARÇO DE 2020"),
        para(1, "O MINISTRO DE ESTADO resolve:"),
    ]
    blocks += [
        para(i, f"Parágrafo de prosa número {i}, expondo a matéria em detalhe.")
        for i in range(2, 40)
    ]
    blocks.append(para(40, "Art. 1º Fica instituído o procedimento desta portaria."))
    blocks.append(para(41, "Art. 2º Este ato entra em vigor na data de sua publicação."))

    verdict = assess_viability(StyledDoc(blocks=tuple(blocks), source="low_coverage.docx"))
    assert verdict.route == "generico"
    assert verdict.articles_own == 2
    assert verdict.numbering_monotonic is True
    assert verdict.coverage < COVERAGE_MIN
    assert verdict.evidence["gates"]["own_articles"] is True
    assert verdict.evidence["gates"]["monotonic"] is True
    assert verdict.evidence["gates"]["coverage"] is False
    assert verdict.blocker_codes == (BLOCKER_LOW_COVERAGE,)
    assert f"{COVERAGE_MIN:.0%}" in verdict.blocker(BLOCKER_LOW_COVERAGE).detail


def test_non_monotonic_series_blocks_norma() -> None:
    """A series that does not hold together is not this document's numbering.

    ``2, 3, 16, 18, 52`` (``par_cosit_26``) and ``40, 4, 14, 40, …``
    (``parecer_93``) are quoted statutes' numbers. The synthetic case isolates
    the rule from the quotation guard: two *acquitted* articles numbered 5 and
    91 still fail the gate, so the blocker is the series and nothing else.
    """
    blocks = (
        para(0, "PORTARIA Nº 1, DE 1º DE JANEIRO DE 2020"),
        para(1, "O MINISTRO DE ESTADO resolve:"),
        para(2, "Art. 5º Primeiro dispositivo desta portaria sintética."),
        para(3, "Art. 91. Segundo dispositivo, fora de série."),
    )
    verdict = assess_viability(StyledDoc(blocks=blocks, source="non_monotonic.docx"))
    assert verdict.articles_own == 2  # the guard acquitted both
    assert verdict.coverage == 1.0  # coverage is not the reason
    assert verdict.numbering_monotonic is False
    assert verdict.blocker_codes == (BLOCKER_NON_MONOTONIC,)
    assert verdict.route == "generico"
    assert verdict.evidence["gates"]["monotonic"] is False

    for name in (PAR_COSIT_26, PARECER_93):
        assert assess(name).has_blocker(BLOCKER_NON_MONOTONIC), name


def test_top_level_table_blocks_norma() -> None:
    """A table outside any dispositivo cannot be articulated (§4.2).

    Exactly two samples carry one; asserting the other thirteen do *not* is
    what keeps the rule from firing on any document that merely has a table
    somewhere.
    """
    with_tables = {name for name in SAMPLES if assess(name).has_blocker(BLOCKER_TOP_LEVEL_TABLE)}
    assert with_tables == {PAR_COSIT_26, SUMULA_STJ_125}
    for name in with_tables:
        blocker = assess(name).blocker(BLOCKER_TOP_LEVEL_TABLE)
        assert blocker.vetoes is True
        assert assess(name).evidence["tables_in_body"], name


# ---------------------------------------------------------------------------
# §2.7 — priors, not rules
# ---------------------------------------------------------------------------


def test_genre_prior_never_decides_alone() -> None:
    """§2.7. ``port_mf_454`` is a Portaria — the highest prior in the table,
    0.45 — numbered ``1.``, ``2.1``, ``a)``, with no article anywhere.

    Same genre as ``port_mf_277``, opposite structure. If a prior could carry
    a route, this is the document it would carry, so the assertion is that the
    prior is present, is the largest, and changes nothing.
    """
    verdict = assess(PORT_MF_454)
    prior = verdict.evidence["genre_prior"]
    assert prior["profile"] == "portaria"
    assert prior["p_norma"] == 0.45
    assert verdict.route == "generico"
    assert verdict.articles_found == 0
    assert verdict.has_blocker(BLOCKER_NO_ARTICLES)
    # Same prior, opposite verdict — the evidence, not the genre, decides.
    assert assess(PORT_MF_277).evidence["genre_prior"]["profile"] == "portaria"
    assert assess(PORT_MF_277).route == "norma"


# ---------------------------------------------------------------------------
# §9.3 — the referee is pinned off, and must be provably inert
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_verdicts_deterministic_under_null_referee(name: str) -> None:
    """Invariant #4. Three fresh assessments, one answer.

    Deliberately bypasses the module's cache: a memoised verdict would make
    this test assert nothing at all.
    """
    doc = load(name)
    runs = [assess_viability(doc, referee=NullReferee()).to_json() for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


@pytest.mark.parametrize("name", SAMPLES)
def test_null_referee_matches_referee_disabled(name: str) -> None:
    """The plan's first referee test (§9.3): a null referee is *no* referee.

    Byte-identical over the whole serialised verdict, bookkeeping fields
    included — so ``referee_consulted`` may not quietly flip, and the
    abstention count in ``--decisions-report`` keeps meaning "genuinely asked
    and genuinely failed".
    """
    doc = load(name)
    assert (
        assess_viability(doc, referee=NullReferee()).to_json()
        == assess_viability(doc, referee=None).to_json()
    )


# ---------------------------------------------------------------------------
# A-R.7 — a rendering blocker is not a routing blocker
# ---------------------------------------------------------------------------


def test_nested_unavailable_blocker() -> None:
    """A-R.7. Asking for a rendering the shipped schemas cannot express is
    *recorded*, with the probe's own words, and does not veto.

    The detail is the capability probe's diagnostic verbatim rather than a
    paraphrase: a user told "nested rendering unavailable" must be able to
    tell a missing directory from an unpatched schema without reading source.
    """
    verdict = assess(PORT_MF_277, emitter="generico-aninhado", generation="shipped")
    blocker = verdict.blocker(BLOCKER_NESTED_UNAVAILABLE)
    assert blocker is not None
    assert blocker.vetoes is False
    assert blocker.detail == probe_capabilities("shipped").diagnostic
    assert "shipped" in blocker.detail
    assert "nested rendering" in blocker.detail
    assert "unavailable" in blocker.detail
    assert verdict.evidence["emitter"] == "generico-aninhado"
    assert verdict.evidence["capabilities"]["nested_agrupamento"] is False
    assert verdict.evidence["capabilities"]["available"] is True


def test_nested_available_on_proposed() -> None:
    """The other side of A-R.7: the maintainers' recursive change is present in
    ``lexml-proposed/``, so nothing is recorded.

    Skipped rather than failed when the generated generation is absent —
    invariant #12 requires the suite to stay green against ``lexml/`` alone,
    and a checkout that has not run ``scripts/build_proposed_schemas.py`` is a
    missing input, not a routing regression.
    """
    if not probe_capabilities("proposed").available:
        pytest.skip("lexml-proposed/ absent; run scripts/build_proposed_schemas.py")
    verdict = assess(PORT_MF_277, emitter="generico-aninhado", generation="proposed")
    assert not verdict.has_blocker(BLOCKER_NESTED_UNAVAILABLE)
    assert verdict.evidence["capabilities"]["generation"] == "proposed"
    assert verdict.evidence["capabilities"]["nested_agrupamento"] is True


@pytest.mark.parametrize("name", SAMPLES)
def test_nested_blocker_does_not_change_route(name: str) -> None:
    """A-R.7's second sentence, and the load-bearing test of this group.

    Routing is about what the document *is*, not how it is written out. If a
    missing schema capability could move a route, the corpus's answer to "is
    this a statute?" would depend on which directory happened to be checked
    out — and ``port_mf_277`` would stop being a Norma the moment a caller
    asked for nested output.
    """
    plain = assess(name, emitter="generico")
    nested = assess(name, emitter="generico-aninhado")
    assert nested.route == plain.route
    assert nested.confidence == plain.confidence
    assert nested.coverage == plain.coverage
    assert nested.evidence["gates"] == plain.evidence["gates"]
    # The only difference is the recorded, non-vetoing observation.
    assert tuple(b for b in nested.blockers if b.vetoes) == tuple(
        b for b in plain.blockers if b.vetoes
    )
    extra = [c for c in nested.blocker_codes if c not in plain.blocker_codes]
    assert extra in ([], [BLOCKER_NESTED_UNAVAILABLE])


# ---------------------------------------------------------------------------
# Invariants — true of any document, not only of these fifteen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_blocker_codes_are_known(name: str) -> None:
    """A blocker nobody can name is a blocker nobody will fix (§4.1)."""
    for verdict in (assess(name), assess(name, emitter="generico-aninhado")):
        for code in verdict.blocker_codes:
            assert code in BLOCKER_CODES, code


@pytest.mark.parametrize("name", SAMPLES)
def test_blocker_details_are_human_readable(name: str) -> None:
    """Plan invariant #10, following Cycle 4's `test_real_rejections_are_human_readable`.

    A refusal has to be checkable by a person in one line across 300 documents,
    so every detail names something concrete — a count, a percentage, the
    article series, or the schema generation that lacks the capability.
    """
    for verdict in (assess(name), assess(name, emitter="generico-aninhado")):
        for blocker in verdict.blockers:
            detail = blocker.detail
            assert detail and detail == detail.strip()
            assert len(detail.split()) >= 4, detail
            assert re.search(r"\d|shipped|proposed", detail), detail
            assert str(blocker) == f"{blocker.code}: {detail}"


@pytest.mark.parametrize("name", SAMPLES)
def test_evidence_is_json_round_trippable(name: str) -> None:
    """§7's telemetry is only useful if a verdict survives being written down."""
    verdict = assess(name, emitter="generico-aninhado")
    restored = StatutoryViability.from_json(verdict.to_json())
    assert restored.route == verdict.route
    assert restored.confidence == round(verdict.confidence, 4)
    assert restored.articles_found == verdict.articles_found
    assert restored.articles_quoted == verdict.articles_quoted
    assert restored.articles_own == verdict.articles_own
    assert restored.coverage == round(verdict.coverage, 4)
    assert restored.has_anexos == verdict.has_anexos
    assert restored.numbering_monotonic == verdict.numbering_monotonic
    assert restored.blockers == verdict.blockers
    assert restored.evidence == verdict.evidence
    assert restored.to_json() == verdict.to_json()


@pytest.mark.parametrize("name", SAMPLES)
def test_never_raises_on_any_sample(name: str) -> None:
    """§4: the open route is always available.

    A document that cannot be assessed routes to `generico` with a blocker
    saying why — it never propagates an exception, because the statutory route
    is the exception that must earn itself.
    """
    doc = load(name)
    for emitter in EMITTERS:
        verdict = assess_viability(doc, emitter=emitter)
        assert isinstance(verdict, StatutoryViability)
    # An unknown generation is a caller error the analyzer absorbs, not raises.
    assert isinstance(
        assess_viability(doc, emitter="generico-aninhado", generation="bogus"),
        StatutoryViability,
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_articles_own_identity(name: str) -> None:
    """Spec decision D-2: `own` is derived, never independently counted."""
    verdict = assess(name)
    assert verdict.articles_own == verdict.articles_found - verdict.articles_quoted
    census_ = verdict.evidence["census"]
    assert len(census_["own"]) == verdict.articles_own
    assert len(census_["found"]) == verdict.articles_found
    assert len(census_["quoted"]) == verdict.articles_quoted


@pytest.mark.parametrize("name", SAMPLES)
def test_route_is_always_a_known_route(name: str) -> None:
    """Decision #2: there is no `Jurisprudencia` route, however tempting."""
    verdict = assess(name)
    assert verdict.route in ROUTES
    assert verdict.is_statutory == (verdict.route == "norma")
    assert 0.0 <= verdict.confidence <= 1.0


@pytest.mark.parametrize("name", SAMPLES)
def test_gates_agree_with_route(name: str) -> None:
    """§4.2: the four gates are the reason, not decoration.

    ``route == "norma"`` **iff** all four hold. Asserted as an equivalence so
    that a fifth influence on the route cannot be added without the evidence
    recording it.
    """
    verdict = assess(name)
    gates = verdict.evidence["gates"]
    assert set(gates) == {"own_articles", "monotonic", "coverage", "no_vetoing_blocker"}
    assert all(isinstance(v, bool) for v in gates.values())
    assert (verdict.route == "norma") == all(gates.values())
    # And each gate says what it is measuring.
    assert gates["own_articles"] == (verdict.articles_own >= 1)
    assert gates["monotonic"] == verdict.numbering_monotonic
    assert gates["coverage"] == (verdict.coverage >= COVERAGE_MIN)
    assert gates["no_vetoing_blocker"] == (not [b for b in verdict.blockers if b.vetoes])
