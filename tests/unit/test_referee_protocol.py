"""The referee is **advisory** — plan invariant #9, asserted directly.

Every other referee test in this cycle checks that the machinery works. This
one checks that the machinery cannot do damage, which is a different question
and the more important of the two. Decision #3 admitted a language model into a
pipeline whose whole purpose is to *refuse* to invent structure; the promises
that make that safe are:

1. a confident rule is not even asked (§7.3 constraint 1);
2. a rule at or above `RULE_HIGH_CONFIDENCE` can never be overridden, whatever
   the referee says and however sure it claims to be (constraint 4);
3. a referee below `REFEREE_MIN_CONFIDENCE` never breaks a tie;
4. an abstention keeps the rule verdict (constraint 5);
5. disabling the referee never changes an outcome;
6. and every one of those decisions is recorded (§7.4).

The last test in this module is the one that matters most: an **adversarial**
referee — one answering "own" to every question ever put to it — still leaves
all fifteen samples on the route the rules chose. If that ever fails, an LLM
outage or a prompt-injected document could publish the Constitution's `Art. 40`
as an article of a legal opinion, which is precisely the outcome plan §2.5
exists to prevent.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.referee import (
    FLAG_THRESHOLD,
    HEADING_VERDICTS,
    OWN_ARTICULATION_VERDICTS,
    REFEREE_MIN_CONFIDENCE,
    REFEREE_MODES,
    RULE_HIGH_CONFIDENCE,
    CachedAPIReferee,
    LocalReferee,
    NullReferee,
    Referee,
    Verdict,
    adjudicate,
    build_referee,
    is_flagged,
)
from lexml_nonstat.routing import assess_viability
from lexml_nonstat.telemetry import LOGGER_NAME, DecisionLog

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))


class StubReferee:
    """A referee that answers whatever it was told to, and counts the asking."""

    name = "stub"

    def __init__(self, verdict: Verdict) -> None:
        self._verdict = verdict
        self.calls = 0
        self.last_cache_hit = False

    def _answer(self) -> Verdict:
        self.calls += 1
        return self._verdict

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        return self._answer()

    def is_heading(self, para: str, ctx: str) -> Verdict:
        return self._answer()

    def section_kind(self, label: str, heading: str) -> Verdict:
        return self._answer()


class AlwaysOwnReferee(StubReferee):
    """The adversary: maximally confident that nothing is ever quoted."""

    name = "always-own"

    def __init__(self) -> None:
        super().__init__(Verdict("own", 1.0, "everything is this document's own"))


def _adjudicate(rule_verdict, rule_confidence, referee, **kwargs):
    return adjudicate(
        kind="own_articulation",
        doc="doc",
        locator="p#1",
        rule_verdict=rule_verdict,
        rule_confidence=rule_confidence,
        excerpt="Art. 40. Aos servidores titulares de cargos efetivos…",
        ctx="Dispõe a Constituição Federal:",
        referee=referee,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def test_verdict_defaults_to_an_abstention():
    assert Verdict().abstained


def test_abstain_carries_its_reason():
    verdict = Verdict.abstain("transport exploded")
    assert verdict.abstained
    assert verdict.confidence == 0.0
    assert "transport exploded" in verdict.rationale


def test_verdict_round_trips():
    verdict = Verdict("quoted", 0.88, "cita a Lei nº 8.112")
    assert Verdict.from_dict(verdict.to_dict()) == verdict


def test_verdict_from_dict_tolerates_nulls():
    """A provider that sends `null` for confidence must not crash the run."""
    restored = Verdict.from_dict({"verdict": "own", "confidence": None, "rationale": None})
    assert restored.verdict == "own"
    assert restored.confidence == 0.0
    assert restored.rationale == ""


def test_thresholds_are_ordered():
    """The guarantee must survive a caller that bypasses `adjudicate`.

    `RULE_HIGH_CONFIDENCE` sits strictly above `FLAG_THRESHOLD` on purpose: the
    flag threshold decides who gets *asked*, and the high-confidence bar decides
    who can be *overruled*. Collapsing them would make invariant #9 an accident
    of the call site rather than a property of the module.
    """
    assert 0.0 < FLAG_THRESHOLD < RULE_HIGH_CONFIDENCE <= 1.0
    assert 0.0 < REFEREE_MIN_CONFIDENCE <= 1.0


def test_is_flagged_is_the_threshold():
    assert is_flagged(FLAG_THRESHOLD - 0.01)
    assert not is_flagged(FLAG_THRESHOLD)


# ---------------------------------------------------------------------------
# NullReferee
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda r: r.is_own_articulation("Art. 1º", ""),
        lambda r: r.is_heading("CAPÍTULO I", ""),
        lambda r: r.section_kind("1.", "Introdução"),
    ],
)
def test_null_referee_abstains_on_every_question(call):
    verdict = call(NullReferee())
    assert verdict.abstained
    assert verdict.rationale


def test_null_referee_declares_itself_inert():
    """`enabled = False` is what makes `--referee=none` and no referee equal."""
    assert NullReferee().enabled is False


def test_null_referee_satisfies_the_protocol():
    assert isinstance(NullReferee(), Referee)


def test_stub_referee_satisfies_the_protocol():
    assert isinstance(StubReferee(Verdict("own", 1.0)), Referee)


def test_api_and_local_referees_satisfy_the_protocol():
    assert isinstance(CachedAPIReferee(), Referee)
    assert isinstance(LocalReferee("/nonexistent/model.gguf"), Referee)


# ---------------------------------------------------------------------------
# build_referee
# ---------------------------------------------------------------------------


def test_build_referee_defaults_to_none():
    assert isinstance(build_referee(), NullReferee)


def test_build_referee_knows_its_modes():
    assert REFEREE_MODES == ("none", "api", "local")
    assert isinstance(build_referee("api", api_key=None), CachedAPIReferee)
    assert isinstance(build_referee("local", model_path="/x.gguf"), LocalReferee)


def test_build_referee_rejects_an_unknown_mode():
    """A typo in `--referee` must not silently disable adjudication."""
    with pytest.raises(ValueError, match="unknown referee mode"):
        build_referee("gpt")


# ---------------------------------------------------------------------------
# adjudicate — the advisory guarantee
# ---------------------------------------------------------------------------


def test_confident_rule_is_not_even_consulted():
    """§7.3 constraint 1: rules run first, always."""
    referee = StubReferee(Verdict("quoted", 0.99, "sure"))
    final, record = _adjudicate("own", 0.95, referee)
    assert final == "own"
    assert referee.calls == 0
    assert record.referee_consulted is False
    assert record.rule_flagged is False


def test_high_confidence_rule_is_not_consulted_at_all():
    """A rule at `RULE_HIGH_CONFIDENCE` never reaches a referee.

    Today the flag threshold alone achieves this, since 0.75 > 0.60. That is
    why the *next* test exists: this one only proves the first line of defence,
    and a mutation removing the second survived the whole suite until it was
    written.
    """
    referee = StubReferee(Verdict("quoted", 1.0, "certain"))
    final, record = _adjudicate("own", RULE_HIGH_CONFIDENCE, referee)
    assert final == "own"
    assert referee.calls == 0
    assert record.overridden is False


def test_high_confidence_rule_survives_a_lowered_flag_threshold(monkeypatch):
    """Invariant #9's second line of defence, made reachable.

    `RULE_HIGH_CONFIDENCE` (0.75) sits above `FLAG_THRESHOLD` (0.60), so with
    the shipped constants a rule can never be both *flagged* and *high
    confidence* — the guard inside `adjudicate` is unreachable, and a mutation
    deleting it passed all 3128 tests.

    That does not make it dead code; it makes it the guarantee that survives
    someone retuning the flag threshold, which Cycle 9 is expected to do once
    the corpus reaches 300 documents and 5.6% flagged becomes too many
    questions. Raising the threshold here is exactly that future change,
    applied now: a 0.90-confidence rule is flagged, a maximally confident
    referee contradicts it, and the rule must still win.
    """
    # The module, not the string path: `referee/__init__.py` re-exports the
    # `adjudicate` *function* under the submodule's name, so the dotted string
    # resolves to the function and monkeypatch raises.
    module = importlib.import_module("lexml_nonstat.referee.adjudicate")
    monkeypatch.setattr(module, "FLAG_THRESHOLD", 1.0)
    referee = StubReferee(Verdict("quoted", 1.0, "absolutely certain"))

    final, record = _adjudicate("own", 0.90, referee)

    assert referee.calls == 1, "the lowered threshold must actually flag this"
    assert record.referee_consulted is True
    assert record.rule_flagged is True
    assert final == "own", "a high-confidence rule was overridden (invariant #9)"
    assert record.overridden is False
    assert record.agreed is False, "disagreeing is not agreeing"


def test_a_confident_abstention_cannot_override():
    """A `Verdict(None, 0.95)` is malformed, and must not become the outcome.

    `Verdict.abstain()` always sets confidence 0.0, so the confidence check
    alone masks this — which is why a mutation deleting the `abstained` guard
    survived. But a referee implementation is free to construct a `Verdict`
    directly, and without the guard `final_verdict` would be set to `None`:
    not a wrong answer, but *no answer at all*, silently replacing a perfectly
    good rule verdict downstream.
    """
    referee = StubReferee(Verdict(None, 0.95, "confidently says nothing"))

    final, record = _adjudicate("own", 0.41, referee)

    assert final == "own"
    assert final is not None
    assert record.abstained is True
    assert record.overridden is False


def test_low_confidence_rule_can_be_overridden():
    referee = StubReferee(Verdict("quoted", 0.88, "precedido de 'Lei nº 7.713 -'"))
    final, record = _adjudicate("own", 0.41, referee)
    assert final == "quoted"
    assert record.overridden is True
    assert record.referee_verdict == "quoted"
    assert record.referee_rationale


def test_unsure_referee_does_not_break_a_tie():
    referee = StubReferee(Verdict("quoted", REFEREE_MIN_CONFIDENCE - 0.01, "hmm"))
    final, record = _adjudicate("own", 0.41, referee)
    assert final == "own"
    assert record.overridden is False
    assert record.referee_consulted is True


def test_referee_at_the_minimum_confidence_may_override():
    referee = StubReferee(Verdict("quoted", REFEREE_MIN_CONFIDENCE, "just enough"))
    final, _ = _adjudicate("own", 0.41, referee)
    assert final == "quoted"


def test_abstention_retains_the_rule_verdict():
    referee = StubReferee(Verdict.abstain("timeout"))
    final, record = _adjudicate("own", 0.41, referee)
    assert final == "own"
    assert record.abstained is True
    assert record.overridden is False
    assert record.agreed is False


def test_agreement_is_not_an_override():
    referee = StubReferee(Verdict("own", 0.9, "própria articulação"))
    final, record = _adjudicate("own", 0.41, referee)
    assert final == "own"
    assert record.overridden is False
    assert record.agreed is True


def test_a_referee_breaking_the_protocol_is_treated_as_malformed():
    """Returning something that is not a `Verdict` must not crash a batch run."""

    class BrokenReferee:
        name = "broken"

        def is_own_articulation(self, excerpt, ctx):
            return {"verdict": "quoted"}

        def is_heading(self, para, ctx):  # pragma: no cover - unused
            return None

        def section_kind(self, label, heading):  # pragma: no cover - unused
            return None

    final, record = _adjudicate("own", 0.41, BrokenReferee())
    assert final == "own"
    assert record.abstained is True
    assert "expected Verdict" in (record.referee_rationale or "")


def test_no_referee_and_null_referee_produce_the_same_record():
    """The plan's first referee test, at the adjudication level."""
    _, without = _adjudicate("own", 0.41, None)
    _, null = _adjudicate("own", 0.41, NullReferee())
    assert without.to_dict() == null.to_dict()


def test_an_unknown_decision_kind_is_never_put_to_a_referee():
    """`route` has no referee method; asking anyway would be a silent bug."""
    referee = StubReferee(Verdict("norma", 1.0, "looks statutory"))
    final, record = adjudicate(
        kind="route",
        doc="doc",
        locator="",
        rule_verdict="generico",
        rule_confidence=0.3,
        referee=referee,
    )
    assert final == "generico"
    assert referee.calls == 0
    assert record.referee_consulted is False
    assert record.rule_flagged is True


def test_every_adjudication_produces_a_record_in_the_log():
    log = DecisionLog()
    _adjudicate("own", 0.95, None, log=log)
    _adjudicate("own", 0.41, StubReferee(Verdict("quoted", 0.9, "r")), log=log)
    assert len(log) == 2
    assert [r.rule_flagged for r in log] == [False, True]


def test_override_is_logged_as_a_warning(caplog):
    """Invariant #10: an intervention must be impossible to miss."""
    referee = StubReferee(Verdict("quoted", 0.88, "cita a Lei nº 7.713"))
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _adjudicate("own", 0.41, referee, logger=logging.getLogger(LOGGER_NAME))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    text = "\n".join(r.getMessage() for r in warnings)
    assert "REFEREE OVERRODE RULE" in text
    assert "own" in text and "quoted" in text
    assert "cita a Lei nº 7.713" in text


# ---------------------------------------------------------------------------
# The adversary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_adversarial_referee_cannot_change_any_route(name: str):
    """A referee answering "own" to everything changes nothing. Invariant #9.

    This is the test that makes decision #3 safe. Two independent guards hold
    the line, and the corpus exercises both: on `parecer_93` and every banded
    document the quotation verdicts are above the flag threshold, so the
    adversary is never even asked; on `par_cosit_26`, where three verdicts *are*
    flagged and the adversary does get to answer, the article series still runs
    `2, 3, 16, 18, 52` and the monotonicity gate refuses the statutory route on
    its own.

    Belt and braces, deliberately: either guard alone would pass this test
    today, and the 285 unseen documents are exactly where one of them will not.
    """
    doc = read_docx(SAMPLES_DIR / f"{name}.docx")
    baseline = assess_viability(doc)
    attacked = assess_viability(doc, referee=AlwaysOwnReferee())
    assert attacked.route == baseline.route


def test_adversarial_referee_does_not_flip_par_cosit_26():
    """The residual case, stated explicitly (plan §2.6).

    Its three flagged verdicts are the only ones in the corpus an adversary can
    reach at all, so this is the single document where the guarantee is doing
    real work rather than being vacuously true.
    """
    doc = read_docx(SAMPLES_DIR / "par_cosit_26_20000629.docx")
    attacked = assess_viability(doc, referee=AlwaysOwnReferee())
    assert attacked.route == "generico"
    assert attacked.referee_consulted is True
    assert attacked.referee_overrode is True
    assert attacked.has_blocker("non_monotonic_series")


def test_adversarial_referee_is_recorded_when_it_overrides():
    """Being overruled is not the same as being ignored — §7.4 wants both seen."""
    doc = read_docx(SAMPLES_DIR / "par_cosit_26_20000629.docx")
    log = DecisionLog()
    assess_viability(doc, referee=AlwaysOwnReferee(), log=log)
    overrides = [r for r in log if r.overridden]
    assert len(overrides) == 3
    assert {r.locator for r in overrides} == {"p#46", "p#47", "p#53"}
    for record in overrides:
        assert record.rule_verdict == "quoted"
        assert record.final_verdict == "own"
        assert record.referee_name == "always-own"


def test_vocabularies_are_closed():
    """A referee inventing a third answer is a referee to ignore."""
    assert OWN_ARTICULATION_VERDICTS == ("own", "quoted")
    assert HEADING_VERDICTS == ("heading", "prose")
