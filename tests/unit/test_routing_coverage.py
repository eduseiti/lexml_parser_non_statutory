"""The census, the coverage gate and the genre priors, on their own.

:mod:`lexml_nonstat.routing.viability` is tested through whole documents in
``test_routing.py``. This module tests the three things it is built out of,
because each of them can be wrong in a way a route table cannot see.

**The census must read Cycle 4, never recompute it.** Cycle 4's report says the
routing package "must not become a second source of truth for the same
measurements", and it is right: the quotation guard already had to census the
articles, detect the quote bands and test the series for monotonicity to do its
own job. Two implementations that disagreed would be a bug nobody could see
from either side. So the guarantee is asserted twice — the identity on the
real samples, and then, with a hand-substituted
:class:`~lexml_nonstat.hierarchy.QuotationAnalysis`, the proof that the census
*reports what it was handed* rather than arriving at the same answer by its own
route.

**Coverage arithmetic** is where §4.2's gate actually lives, and the corpus
cannot exercise it: fourteen samples score 0.0 and the fifteenth scores 1.0.
The interesting values in between only exist here.

**Per-article confidence** decides which handful of verdicts a referee is ever
asked about. Across the corpus's 32 article paragraphs exactly **four** fall
below ``FLAG_THRESHOLD``, and that number is the flagging policy: if a
threshold is retuned by accident it becomes forty, and §7's "ask about the two
or three that matter" quietly becomes "ask about everything".

**Genre priors** are §2.7's "priors, not rules". The assertion that matters is
structural rather than per-genre: no prior may reach 0.5, so no genre can clear
a gate by itself.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from lexml_nonstat.hierarchy import QuotationAnalysis, analyse_quotation
from lexml_nonstat.ingest import StyledDoc, StyledTable, read_docx
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.profile import all_profiles, get_profile, select_profile
from lexml_nonstat.referee import FLAG_THRESHOLD
from lexml_nonstat.routing import (
    COVERAGE_MIN,
    DEFAULT_PRIOR,
    PRIORS,
    ArticleCensus,
    articulation_coverage,
    census,
    genre_prior,
    quotation_confidence,
)
from lexml_nonstat.segment import segment_document

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

PARECER_93 = "parecer_93_2018_decor_cgu_agu"
PAR_COSIT_26 = "par_cosit_26_20000629"
PORT_MF_277 = "port_mf_277_20180607"

#: The three samples that carry an ``Art.`` at all. Everything the census and
#: the confidence scale have to say about the corpus, it says about these.
ARTICLE_BEARING: tuple[str, ...] = (PAR_COSIT_26, PARECER_93, PORT_MF_277)

_BODY: dict[str, tuple[list, QuotationAnalysis]] = {}


def body(name: str) -> tuple[list, QuotationAnalysis]:
    """The body paragraphs the analyzer sees, plus Cycle 4's verdicts on them.

    Built the way :func:`assess_viability` builds them — profile, metadata,
    segmentation, then the body span with tables removed — so a divergence here
    would be a divergence in the pipeline, not in the fixture.
    """
    if name not in _BODY:
        doc: StyledDoc = read_docx(SAMPLES_DIR / f"{name}.docx")
        profile = select_profile(doc)
        metadata = extract_metadata(doc, profile=profile)
        segmentation = segment_document(doc, profile=profile, metadata=metadata)
        blocks = {b.index: b for b in doc.blocks}
        span = [] if segmentation.body is None else list(segmentation.body.indices)
        paras = [
            blocks[i]
            for i in span
            if i in blocks and not isinstance(blocks[i], StyledTable)
        ]
        _BODY[name] = (paras, analyse_quotation(paras))
    return _BODY[name]


def confidence_at(name: str, index: int) -> tuple[float, str]:
    """``quotation_confidence`` for one body paragraph, by source block index."""
    paras, analysis = body(name)
    para = next(p for p in paras if p.index == index)
    return quotation_confidence(para, analysis)


# ---------------------------------------------------------------------------
# census() — no second source of truth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ARTICLE_BEARING)
def test_census_reads_cycle_4s_series(name: str) -> None:
    """The census reports Cycle 4's series verbatim (spec: no second source).

    ``values`` and ``monotonic`` are the two measurements the quotation guard
    already made. If routing recomputed them the two could drift apart, and a
    document would be non-monotonic to one module and monotonic to the other.
    """
    paras, analysis = body(name)
    result = census(paras, analysis)
    assert result.values == analysis.article_values
    assert result.monotonic == analysis.article_monotonic
    assert result.n_found == len(result.found)
    assert set(result.quoted) | set(result.own) == set(result.found)
    assert not set(result.quoted) & set(result.own)


@pytest.mark.parametrize("name", ARTICLE_BEARING)
def test_census_reads_rather_than_recomputes(name: str) -> None:
    """The proof, not the coincidence.

    An identity between two correct implementations still passes when both are
    computed independently. Hand the census an analysis carrying a series no
    document has — and the opposite monotonicity verdict — and it must report
    *that*. Anything else means routing is measuring the articles a second
    time, which is exactly what Cycle 4's report forbids.
    """
    paras, analysis = body(name)
    substituted = dataclasses.replace(
        analysis,
        article_values=(4242, 7, 4242),
        article_monotonic=not analysis.article_monotonic,
    )
    result = census(paras, substituted)
    assert result.values == (4242, 7, 4242)
    assert result.monotonic is (not analysis.article_monotonic)
    # The paragraph-level census is unchanged: only the read-through fields moved.
    assert result.found == census(paras, analysis).found


def test_census_of_a_document_without_articles() -> None:
    """Fourteen of fifteen samples land here; the empty census must be quiet."""
    paras, analysis = body("ad_srf_3_19990107")
    result = census(paras, analysis)
    assert result.found == () and result.quoted == () and result.own == ()
    assert result.n_found == result.n_quoted == result.n_own == 0
    assert result.all_quoted is False


def test_census_counts_port_mf_277_as_two_own() -> None:
    """The corpus's only articulation, at the census level."""
    paras, analysis = body(PORT_MF_277)
    result = census(paras, analysis)
    assert result.found == (3, 4)
    assert result.quoted == ()
    assert result.own == (3, 4)
    assert result.values == (1, 2)
    assert result.monotonic is True
    assert result.to_dict() == {
        "found": [3, 4],
        "quoted": [],
        "own": [3, 4],
        "values": [1, 2],
        "monotonic": True,
    }


# ---------------------------------------------------------------------------
# ArticleCensus.all_quoted
# ---------------------------------------------------------------------------


def test_all_quoted_is_found_and_nothing_survived() -> None:
    """`all_quoted` is the blocker `all_articles_quoted` turns on, so its edge
    case matters: a document with *no* articles has not had them all quoted."""
    assert ArticleCensus().all_quoted is False
    assert ArticleCensus(found=(1,), quoted=(1,), own=()).all_quoted is True
    assert ArticleCensus(found=(1, 2), quoted=(1,), own=(2,)).all_quoted is False
    assert ArticleCensus(found=(1,), quoted=(), own=(1,)).all_quoted is False


@pytest.mark.parametrize(
    "name,expected", [(PAR_COSIT_26, True), (PARECER_93, True), (PORT_MF_277, False)]
)
def test_all_quoted_on_the_corpus(name: str, expected: bool) -> None:
    """The two opinions quote statutes they do not enact (§2.5); the Portaria
    enacts its own."""
    paras, analysis = body(name)
    assert census(paras, analysis).all_quoted is expected


# ---------------------------------------------------------------------------
# articulation_coverage() — §4.2's arithmetic
# ---------------------------------------------------------------------------


def test_coverage_of_an_empty_body_is_zero() -> None:
    """Nothing to cover. Not an error, and never a division by zero."""
    assert articulation_coverage(ArticleCensus(found=(1,), own=(1,)), []) == 0.0


def test_coverage_without_own_articles_is_zero() -> None:
    """A document whose every article is quoted articulates nothing — which is
    the state fourteen of the fifteen samples are in."""
    quoted_only = ArticleCensus(found=(2, 5), quoted=(2, 5), own=())
    assert articulation_coverage(quoted_only, list(range(10))) == 0.0
    assert articulation_coverage(ArticleCensus(), list(range(10))) == 0.0


def test_coverage_from_the_first_body_index_is_total() -> None:
    """`port_mf_277`'s shape: an article at the body's first paragraph claims
    all of it, because an article's extent runs to the next one."""
    census_ = ArticleCensus(found=(0,), own=(0,), values=(1,), monotonic=True)
    assert articulation_coverage(census_, list(range(10))) == 1.0


def test_coverage_halfway_through_the_body() -> None:
    """Everything before the first own article is preamble, everything after
    is inside the articulation."""
    census_ = ArticleCensus(found=(5,), own=(5,))
    assert articulation_coverage(census_, list(range(10))) == pytest.approx(0.5)
    assert articulation_coverage(census_, list(range(10))) < COVERAGE_MIN


def test_coverage_is_measured_from_the_first_own_article() -> None:
    """Several own articles do not each claim their own tail — the first one
    opens the articulation and the rest are inside it."""
    many = ArticleCensus(found=(2, 4, 6, 8), own=(2, 4, 6, 8), values=(1, 2, 3, 4))
    one = ArticleCensus(found=(2,), own=(2,), values=(1,))
    indices = list(range(10))
    assert articulation_coverage(many, indices) == articulation_coverage(one, indices)
    assert articulation_coverage(many, indices) == pytest.approx(0.8)


def test_coverage_is_positional_not_absolute() -> None:
    """The body span rarely starts at block 0 — front matter comes first.

    Coverage is a fraction of the *body's* blocks, so a body running 100..199
    with its first own article at 150 scores a half, not a hundredth.
    """
    census_ = ArticleCensus(found=(150,), own=(150,))
    assert articulation_coverage(census_, list(range(100, 200))) == pytest.approx(0.5)


def test_coverage_ignores_own_articles_outside_the_body() -> None:
    """A degenerate call must still return a fraction, never a number above 1."""
    census_ = ArticleCensus(found=(999,), own=(999,))
    value = articulation_coverage(census_, list(range(10)))
    assert 0.0 <= value <= 1.0
    assert value == 0.0


# ---------------------------------------------------------------------------
# quotation_confidence() — which verdicts the rules were sure of
# ---------------------------------------------------------------------------

#: Every reason the scale can give names one of these rules. A confidence with
#: no rule behind it is the thing plan invariant #10 forbids.
_RULE_NAMES = re.compile(
    r"quote band|omissis|quotation mark|citation antecedent|"
    r"excerpt-run extension|monotonic"
)


def test_parecer_93_band_articles_are_high_confidence() -> None:
    """§2.5's 25 quoted articles: the indent band carries almost all of them,
    so the referee is never asked about them."""
    paras, analysis = body(PARECER_93)
    result = census(paras, analysis)
    assert result.n_found == 25
    band = [
        (p.index, quotation_confidence(p, analysis))
        for p in paras
        if p.index in result.found and analysis.bands.contains(p)
    ]
    assert band, "parecer_93 has a quote band"
    for index, (conf, reason) in band:
        assert conf >= 0.90, (index, conf, reason)
        assert "quote band" in reason, (index, reason)


def test_par_cosit_26_citation_antecedent_is_flagged() -> None:
    """§2.6's residual case. `par_cosit_26` has no indentation at all, so p#46
    is convicted on half an argument — and says so."""
    conf, reason = confidence_at(PAR_COSIT_26, 46)
    assert conf == pytest.approx(0.55)
    assert conf < FLAG_THRESHOLD
    assert "citation antecedent" in reason


@pytest.mark.parametrize("index", [47, 53])
def test_par_cosit_26_excerpt_run_extension_is_flagged(index: int) -> None:
    """Convicted only by inheritance from an earlier quoted article — the
    weakest verdict the guard can reach, and the one worth asking about."""
    conf, reason = confidence_at(PAR_COSIT_26, index)
    assert conf == pytest.approx(0.50)
    assert conf < FLAG_THRESHOLD
    assert "excerpt-run extension" in reason


@pytest.mark.parametrize("index", [3, 4])
def test_port_mf_277_acquittals_are_high_confidence(index: int) -> None:
    """An acquittal backed by a monotonic series starting at 1 is as strong as
    a conviction in the band — which is why the corpus's one Norma is never
    put to a referee."""
    conf, reason = confidence_at(PORT_MF_277, index)
    assert conf == pytest.approx(0.90)
    assert conf >= FLAG_THRESHOLD
    assert reason.startswith("acquitted")
    assert "monotonic" in reason


@pytest.mark.parametrize("name", ARTICLE_BEARING)
def test_every_reason_names_a_rule(name: str) -> None:
    """Plan invariant #10: a decision log full of bare numbers explains nothing."""
    paras, analysis = body(name)
    result = census(paras, analysis)
    for p in paras:
        if p.index not in result.found:
            continue
        conf, reason = quotation_confidence(p, analysis)
        assert 0.0 < conf <= 1.0
        assert reason and reason == reason.strip()
        assert reason.startswith(("convicted", "acquitted")), reason
        assert _RULE_NAMES.search(reason), reason


def test_exactly_four_decisions_in_the_corpus_are_flagged() -> None:
    """The flagging policy, measured over the whole corpus (§7.2).

    32 article paragraphs in the fifteen documents — the ``own_articulation``
    half of the corpus's 47 decisions, the other 15 being one ``route`` apiece
    — and exactly **4** of them fall below ``FLAG_THRESHOLD``. This is the test
    that catches a threshold retuned by accident: nudge the scale and "ask the
    referee about the two or three that matter" becomes "ask about every
    article in every parecer", which is a networked call per paragraph across
    300 documents.
    """
    total = 0
    flagged: list[tuple[str, str, float, str]] = []
    for name in SAMPLES:
        paras, analysis = body(name)
        result = census(paras, analysis)
        for p in paras:
            if p.index not in result.found:
                continue
            total += 1
            conf, reason = quotation_confidence(p, analysis)
            if conf < FLAG_THRESHOLD:
                flagged.append((name, f"p#{p.index}", conf, reason))

    assert total == 32
    assert [(n, loc, c) for n, loc, c, _ in flagged] == [
        (PAR_COSIT_26, "p#46", 0.55),
        (PAR_COSIT_26, "p#47", 0.50),
        (PAR_COSIT_26, "p#53", 0.50),
        (PARECER_93, "p#36", 0.55),
    ]
    assert "citation antecedent" in flagged[0][3]
    assert "excerpt-run extension" in flagged[1][3]
    assert "excerpt-run extension" in flagged[2][3]
    assert "citation antecedent" in flagged[3][3]


# ---------------------------------------------------------------------------
# genre_prior() — §2.7, priors and never rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile", [p.name for p in all_profiles()])
def test_every_registered_profile_has_a_prior(profile: str) -> None:
    """A Cycle 2 profile with no prior would silently fall back to `generic`,
    and the genre signal the pipeline does have would go unused."""
    assert profile in PRIORS
    prior = genre_prior(profile)
    assert prior.profile == profile
    assert prior is PRIORS[profile]
    # The same answer whether given the name or the profile object.
    assert genre_prior(get_profile(profile)) is prior


def test_unknown_profile_falls_back_without_raising() -> None:
    """The corpus is 15 documents standing in for 300+; an unrecognised genre
    must degrade to the neutral prior rather than take the pipeline down."""
    prior = genre_prior("nota_tecnica_that_does_not_exist")
    assert prior.p_norma == DEFAULT_PRIOR.p_norma
    assert prior.note == DEFAULT_PRIOR.note
    assert prior.profile == "nota_tecnica_that_does_not_exist"
    # And the empty cases, which `select_profile` can hand it.
    assert genre_prior(None) is PRIORS["generic"]
    assert genre_prior("") is PRIORS["generic"]


def test_no_prior_can_clear_a_gate_by_itself() -> None:
    """§2.7's arithmetic guarantee, and the reason the numbers are small.

    ``port_mf_277`` and ``port_mf_454`` are both Portarias with opposite
    structure, so a genre that reached 0.5 would start deciding routes on the
    epigraph alone. Every prior stays strictly inside (0, 0.5).
    """
    assert PRIORS
    for name, prior in PRIORS.items():
        assert prior.profile == name
        assert 0.0 < prior.p_norma < 0.5, (name, prior.p_norma)
        assert prior.note.strip(), name
        assert prior.to_dict() == {
            "profile": name,
            "p_norma": prior.p_norma,
            "note": prior.note,
        }
    assert max(p.p_norma for p in PRIORS.values()) == PRIORS["portaria"].p_norma
    assert DEFAULT_PRIOR is PRIORS["generic"]


# ---------------------------------------------------------------------------
# Branches the corpus cannot reach
# ---------------------------------------------------------------------------
#
# A mutation sweep over this cycle's code found two `quotation_confidence`
# branches that no sample exercises, so a mutation to either survived the whole
# suite. That is the A-1.3 / A-4.6 precedent for the third time in this project:
# 15 samples stand in for 300+ documents, and the branches they *cannot* reach
# are precisely the ones the unseen corpus will land on. Both are covered here
# synthetically.
#
# Measured branch coverage over the 15 samples (32 article paragraphs):
#
#     23x  0.95  in the quote band, with a corroborating cue
#      2x  0.80  opens with a quotation mark
#      2x  0.90  acquitted, series monotonic
#      2x  0.55  citation antecedent alone          <- flagged
#      2x  0.50  excerpt-run extension alone        <- flagged
#      1x  0.85  omissis run
#      0x  0.90  in the quote band, no other cue    <- unreachable
#      0x  0.60  acquitted, series not monotonic    <- unreachable

from dataclasses import replace as _replace  # noqa: E402

from lexml_nonstat.hierarchy.quotation import QuoteBands as _QuoteBands  # noqa: E402
from lexml_nonstat.ingest import Inline as _Inline, StyledPara as _StyledPara  # noqa: E402


def _para(index: int, text: str, *, indent_effective: int = 0) -> _StyledPara:
    return _StyledPara(
        inlines=(_Inline(text=text),),
        index=index,
        indent_effective=indent_effective,
    )


def test_band_conviction_without_a_corroborating_cue_is_confident():
    """A paragraph in the quote band and nothing else still scores 0.90.

    Every banded article in `parecer_93` happens to *also* carry a citation
    antecedent, so the corpus only ever reaches the 0.95 branch and this one is
    dead to it. It is not dead to the 285 unseen documents: a block-quoted
    statute introduced by a colon rather than by a named norm lands here, and if
    it scored below the flag threshold every such paragraph in every such
    document would become a referee question — turning a four-question corpus
    workload into a per-document one.
    """
    para = _para(7, "Art. 40. Aos servidores titulares de cargos efetivos…", indent_effective=2908)
    analysis = QuotationAnalysis(
        bands=_QuoteBands(body_indent=0, quote_values=frozenset({2908}), rule="deviation"),
        quoted=frozenset({7}),
        article_values=(40,),
        article_monotonic=False,
    )

    confidence, reason = quotation_confidence(para, analysis)

    assert confidence == 0.90
    assert confidence >= FLAG_THRESHOLD, "a banded conviction must not be flagged"
    assert "quote band" in reason


def test_acquittal_against_a_broken_series_is_not_confident():
    """An unconvicted article in a document whose numbering does not hold: 0.60.

    No sample reaches this either — the corpus's only acquitted articles are
    `port_mf_277`'s two, and its series is monotonic. The branch matters
    because it is the *conservative* half of the acquittal: an article the
    guard could not convict, in a document whose series already looks wrong, is
    exactly the case that should sit just at the threshold rather than be
    asserted as this document's own.
    """
    para = _para(11, "Art. 52. O custo de aquisição será o preço pago.")
    analysis = QuotationAnalysis(
        bands=_QuoteBands(),
        quoted=frozenset(),
        article_values=(2, 3, 16, 52),
        article_monotonic=False,
    )

    confidence, reason = quotation_confidence(para, analysis)

    assert confidence == 0.60
    assert confidence >= FLAG_THRESHOLD, "0.60 is the threshold itself, not below it"
    assert "not monotonic" in reason


def test_the_two_acquittal_branches_are_ordered():
    """A monotonic series makes an acquittal *more* trustworthy, never less."""
    para = _para(3, "Art. 1º Fica atribuído…")
    broken = QuotationAnalysis(article_values=(1, 9, 40), article_monotonic=False)
    sound = _replace(broken, article_values=(1, 2, 3), article_monotonic=True)

    assert quotation_confidence(para, sound)[0] > quotation_confidence(para, broken)[0]
