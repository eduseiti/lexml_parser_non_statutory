"""Byte-stable `StatutoryViability` goldens for all 15 samples.

The fifth layer, after Cycle 1's `StyledDoc` (what the reader saw), Cycle 2's
`Metadata` (what the extractor concluded), Cycle 3's `Segmentation` (how the
document was divided) and Cycle 4's `HierarchyDoc` (what shape the body has):
these pin *the routing decision and the evidence behind it*.

Plan §9.4 — goldens regenerate only via
`python3 scripts/regen_goldens.py --kind=routing`, so any diff here is a
reviewed behaviour change rather than silent drift. They are generated with
`referee=None` on purpose (§9.3): a golden that could move because a language
model had a different day would not be a golden.

What makes these worth pinning is not the route — there are only two, and
`tests/unit/test_routing.py` asserts the §4.4 table directly. It is the
**evidence**. A verdict that says `generico` is unreviewable across 300
documents; one that says `all_articles_quoted: 25 of 25 article paragraphs
convicted by the quotation guard` and shows the contributions that produced its
confidence can be checked by a person. If a future cycle retunes a weight,
these files show exactly which documents moved and by how much.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexml_nonstat.hierarchy import infer_hierarchy
from lexml_nonstat.ingest import StyledDoc
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.routing import BLOCKER_CODES, ROUTES, StatutoryViability, assess_viability
from lexml_nonstat.segment import segment_document

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"
ROUTING_DIR = REPO_ROOT / "tests" / "golden" / "routing"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: Plan §4.4's route table — the ground truth these goldens must agree with.
#: Duplicated here deliberately: a golden that agrees only with itself proves
#: nothing, and this is the one assertion that must not be regenerable.
EXPECTED_ROUTES = {
    "port_mf_277_20180607": "norma",
    "parecer_93_2018_decor_cgu_agu": "generico",
    "par_cosit_26_20000629": "generico",
    "pn_cst_38_19801031": "generico",
    "port_mf_454_19770825": "generico",
    "ad_srf_3_19990107": "generico",
    "ad_pgfn_13_20111220": "generico",
    "ad_pgfn_3_20080918": "generico",
    "ad_srf_22_19970430": "generico",
    "adn_cosit_19_20001025": "generico",
    "adn_cst_10_19910417": "generico",
    "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO": "generico",
    "sumula_carf_42": "generico",
    "sumula_stj_125": "generico",
    "REsp_1306393": "generico",
}

_CACHE: dict[str, StatutoryViability] = {}


def _assess(name: str) -> StatutoryViability:
    """Assess from Cycle 1's golden rather than re-parsing the DOCX.

    Keeps the module fast, and makes a routing diff impossible to blame on a
    reader change: that would show up in Cycle 1's goldens first.
    """
    if name not in _CACHE:
        doc = StyledDoc.from_json(
            (STYLED_DIR / f"{name}.json").read_text(encoding="utf-8")
        )
        metadata = extract_metadata(doc, filename=f"{name}.docx")
        segmentation = segment_document(doc, metadata=metadata)
        hierarchy = infer_hierarchy(doc, metadata=metadata, segmentation=segmentation)
        _CACHE[name] = assess_viability(
            doc,
            metadata=metadata,
            segmentation=segmentation,
            hierarchy=hierarchy,
        )
    return _CACHE[name]


def _golden(name: str) -> dict:
    return json.loads((ROUTING_DIR / f"{name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The goldens themselves
# ---------------------------------------------------------------------------


def test_every_sample_has_a_golden():
    missing = [name for name in SAMPLES if not (ROUTING_DIR / f"{name}.json").exists()]
    assert not missing, f"missing routing goldens: {missing}"


def test_no_orphan_goldens():
    """A golden with no sample is a sample that was renamed and left behind."""
    orphans = [p.stem for p in ROUTING_DIR.glob("*.json") if p.stem not in SAMPLES]
    assert not orphans, f"goldens with no sample: {orphans}"


@pytest.mark.parametrize("name", SAMPLES)
def test_verdict_matches_golden(name: str):
    assert json.loads(_assess(name).to_json()) == _golden(name)


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_round_trips_through_the_dataclass(name: str):
    """`from_dict` reconstructs what `to_dict` wrote — the reader Cycle 5 needs."""
    restored = StatutoryViability.from_dict(_golden(name))
    assert restored.route == _assess(name).route
    assert restored.confidence == pytest.approx(_assess(name).confidence)
    assert restored.blocker_codes == _assess(name).blocker_codes
    assert restored.articles_found == _assess(name).articles_found
    assert restored.articles_quoted == _assess(name).articles_quoted
    assert restored.coverage == pytest.approx(_assess(name).coverage)


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_is_deterministic(name: str):
    """Two independent assessments serialise identically (invariant #4)."""
    doc = StyledDoc.from_json((STYLED_DIR / f"{name}.json").read_text(encoding="utf-8"))
    first = assess_viability(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))
    second = assess_viability(doc, metadata=extract_metadata(doc, filename=f"{name}.docx"))
    assert first.to_json() == second.to_json()


# ---------------------------------------------------------------------------
# What must hold whatever the goldens say
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_route_matches_the_plan_table(name: str):
    """The one assertion in this file that is not regenerable (plan §4.4)."""
    assert _golden(name)["route"] == EXPECTED_ROUTES[name]


def test_exactly_one_sample_routes_to_norma():
    """§4.4's headline: 14 of 15 are `generico`.

    Stated as a count rather than only per-sample, because the failure this
    guards against is a *relaxation* — a change that makes several documents
    look statutory would pass fourteen individual tests before failing the
    fifteenth, and this fails immediately with the number.
    """
    routes = [_golden(name)["route"] for name in SAMPLES]
    assert routes.count("norma") == 1
    assert routes.count("generico") == 14


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_blocker_codes_are_known(name: str):
    for blocker in _golden(name)["blockers"]:
        assert blocker["code"] in BLOCKER_CODES


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_route_is_known(name: str):
    assert _golden(name)["route"] in ROUTES


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_carries_no_referee_involvement(name: str):
    """§9.3: goldens are the deterministic rule verdicts and nothing else."""
    golden = _golden(name)
    assert golden["referee_consulted"] is False
    assert golden["referee_overrode"] is False


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_articles_arithmetic_holds(name: str):
    golden = _golden(name)
    assert golden["articles_own"] == golden["articles_found"] - golden["articles_quoted"]
    assert golden["articles_quoted"] <= golden["articles_found"]
    assert golden["articles_own"] >= 0


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_gates_explain_the_route(name: str):
    """The gates are the *reason*, not decoration (plan §4.2)."""
    golden = _golden(name)
    gates = golden["evidence"]["gates"]
    assert (golden["route"] == "norma") == all(gates.values())


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_generico_verdicts_always_say_why(name: str):
    """No unexplained refusal.

    Invariant #10 is about auditing 300 documents nobody will read by hand.
    A `generico` verdict with an empty `blockers` list would be exactly the
    silent guess the whole design refuses to make.
    """
    golden = _golden(name)
    if golden["route"] != "generico":
        return
    vetoes = [b for b in golden["blockers"] if b["vetoes"]]
    assert vetoes, f"{name} routes generico with no vetoing blocker"
    for blocker in vetoes:
        assert blocker["detail"].strip(), f"{name}: blocker {blocker['code']} has no detail"


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_confidence_is_a_probability(name: str):
    assert 0.0 <= _golden(name)["confidence"] <= 1.0


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_evidence_carries_the_audit_trail(name: str):
    """Every key `--decisions-report` and Cycle 5 will read."""
    evidence = _golden(name)["evidence"]
    for key in (
        "genre_prior",
        "census",
        "body_blocks",
        "quote_band_rule",
        "gates",
        "p_norma",
        "contributions",
        "hierarchy",
        "emitter",
    ):
        assert key in evidence, f"{name}: evidence is missing {key!r}"
    assert evidence["contributions"], f"{name}: confidence with no named contributions"
    assert evidence["contributions"][0][0] == "genre_prior"


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_census_is_consistent_with_the_counts(name: str):
    golden = _golden(name)
    census = golden["evidence"]["census"]
    assert len(census["found"]) == golden["articles_found"]
    assert len(census["quoted"]) == golden["articles_quoted"]
    assert len(census["own"]) == golden["articles_own"]
    assert set(census["quoted"]) | set(census["own"]) == set(census["found"])
    assert not set(census["quoted"]) & set(census["own"])


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_coverage_is_zero_without_own_articles(name: str):
    """Coverage measures an articulation; with none there is nothing to cover."""
    golden = _golden(name)
    if golden["articles_own"] == 0:
        assert golden["coverage"] == 0.0


def test_only_port_mf_277_has_anexos():
    """Cycle 3 found exactly one annex in the corpus; routing must agree."""
    with_anexos = [name for name in SAMPLES if _golden(name)["has_anexos"]]
    assert with_anexos == ["port_mf_277_20180607"]


def test_port_mf_277_golden_is_the_annex_split_case():
    """Plan §4.2's worked example, pinned.

    2 genuine articles among 138 document blocks is 1.4%; among its 2-block
    body, after Cycle 3 split off the 132-block `ANEXO ÚNICO`, it is 100%. The
    annex split is what makes the statutory route correct here, and this golden
    is where that shows.
    """
    golden = _golden("port_mf_277_20180607")
    assert golden["route"] == "norma"
    assert golden["has_anexos"] is True
    assert golden["evidence"]["body_blocks"] == 2
    assert golden["coverage"] == 1.0
    assert golden["evidence"]["annexes"] == ["ANEXO ÚNICO"]
    assert golden["blockers"] == []


def test_the_two_quoting_opinions_are_refused_for_the_right_reason():
    """`parecer_93` and `par_cosit_26` — plan §2.5's whole motivation.

    30 `Art.` between them, every one a quotation. What matters is not only
    that they route `generico` but that the *stated reason* is the quotation
    guard: a document refused for the wrong reason would still be refused
    today and accepted the moment that other reason changed.
    """
    for name, found in (("parecer_93_2018_decor_cgu_agu", 25), ("par_cosit_26_20000629", 5)):
        golden = _golden(name)
        assert golden["route"] == "generico"
        assert golden["articles_found"] == found
        assert golden["articles_quoted"] == found
        assert golden["articles_own"] == 0
        codes = [b["code"] for b in golden["blockers"]]
        assert "all_articles_quoted" in codes, name
