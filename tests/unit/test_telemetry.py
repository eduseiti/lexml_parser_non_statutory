"""Decision telemetry — the instrument, and the interventions it must show.

Plan §7.4 makes observability a deliverable, not a debugging aid, and invariant
#10 states the promise plainly: *every rule failure and referee override is
logged and counted*. This file is that promise made executable, in two halves.

**The log lines.** A person scanning a batch run must be able to see, without a
``--verbose``, where a rule did not know its own answer and where a referee
changed it. So the tests here assert on the text of the ``WARNING`` and
``INFO`` lines §7.4 specifies, through ``caplog`` on the
``lexml_nonstat.decisions`` channel — not on the record fields alone, which
would leave the human-facing half of §7.4 untested.

**The counts.** ``--decisions-report`` is what tells us whether rules tuned on
15 samples will survive 300, and a report whose arithmetic does not close is
worse than no report: it reads as evidence while being noise. Hence
``check()``, and hence tests that break the identities deliberately and require
the failure to *name* itself.

The corpus numbers below (47 decisions, 43 rule-only, 4 flagged) are measured
ground truth for Cycle 4b. They are pinned on purpose:
``test_corpus_run_logs_exactly_four_rule_failures`` is the test that notices if
a flagging threshold drifts and the referee quietly starts being asked about
paragraphs the rules used to be sure of — a change in cost, in determinism and
in what the report means, which must never happen silently.
"""

from __future__ import annotations

import json
import logging

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.referee import (
    CachedAPIReferee,
    RefereeCache,
    Verdict,
    adjudicate,
)
from lexml_nonstat.routing import assess_viability
from lexml_nonstat.telemetry import (
    LOGGER_NAME,
    MAX_EXCERPT_IN_RECORD,
    DecisionLog,
    DecisionRecord,
    DecisionsReport,
    render_report,
)

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"
FIXTURES_DIR = REPO_ROOT / "tests" / "referee_fixtures"

#: Every sample in the corpus, by stem.
SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

#: `StyledDoc.source` is the file *name*, so that is what a record's `doc` is.
def doc_name(stem: str) -> str:
    return f"{stem}.docx"


# -- measured ground truth --------------------------------------------------
#
# Cycle 4b, whole corpus, `referee=None`. One `route` decision per sample plus
# one `own_articulation` decision per article paragraph found.

CORPUS_TOTAL = 47
CORPUS_RULE_ONLY = 43
CORPUS_FLAGGED = 4

#: The only four decisions in 15 documents that fall below `FLAG_THRESHOLD`,
#: with the substring of the reason each must carry. Three are plan §2.6's
#: residual case in `par_cosit_26`, which "resists indentation entirely"; the
#: fourth is the one paragraph `parecer_93`'s declared quote band misses.
FLAGGED_DECISIONS: dict[str, dict[str, tuple[float, str]]] = {
    "par_cosit_26_20000629": {
        "p#46": (0.55, "citation antecedent"),
        "p#47": (0.50, "excerpt-run extension"),
        "p#53": (0.50, "excerpt-run extension"),
    },
    "parecer_93_2018_decor_cgu_agu": {
        "p#36": (0.55, "citation antecedent"),
    },
}


# -- helpers ----------------------------------------------------------------


def sweep(referee=None) -> DecisionLog:
    """Route all 15 samples into one decision log, as a batch run would."""
    log = DecisionLog()
    for stem in SAMPLES:
        assess_viability(read_docx(SAMPLES_DIR / f"{stem}.docx"), referee=referee, log=log)
    return log


def offline_referee() -> CachedAPIReferee:
    """The §9.3 seam: recorded fixtures, read-only, transport that must not fire.

    Any question without a fixture would otherwise become a live call. Here it
    becomes a failed test instead, which is the only version of "no network in
    the regression suite" that stays true as the corpus changes.
    """

    def forbidden(*args, **kwargs):  # pragma: no cover - firing it is the failure
        raise AssertionError("the referee reached for the network in a unit test")

    return CachedAPIReferee(
        cache=RefereeCache(FIXTURES_DIR, read_only=True), transport=forbidden
    )


class StubReferee:
    """A referee with a fixed answer — the seam for the override policy.

    Deliberately not a mock of HTTP: §7.3's guarantees are about what
    `adjudicate` does with a verdict, so the verdict is what a test should be
    able to dictate.
    """

    name = "stub"
    enabled = True

    def __init__(self, verdict: Verdict, *, cache_hit: bool = False) -> None:
        self.verdict = verdict
        self.last_cache_hit = cache_hit
        self.asked: list[tuple[str, str]] = []

    def _answer(self, excerpt: str, ctx: str) -> Verdict:
        self.asked.append((excerpt, ctx))
        return self.verdict

    is_own_articulation = _answer
    is_heading = _answer
    section_kind = _answer


def decision_lines(caplog) -> list[logging.LogRecord]:
    """Only the decision channel — never whatever else a module logged."""
    return [r for r in caplog.records if r.name == LOGGER_NAME]


def warnings_containing(caplog, needle: str) -> list[str]:
    return [
        r.getMessage()
        for r in decision_lines(caplog)
        if r.levelno == logging.WARNING and needle in r.getMessage()
    ]


@pytest.fixture(scope="module")
def corpus_log() -> DecisionLog:
    """The whole corpus, refereeless — §9.3's pinned default."""
    return sweep(referee=None)


@pytest.fixture(scope="module")
def refereed_log() -> DecisionLog:
    """The whole corpus with the recorded-fixture referee active."""
    return sweep(referee=offline_referee())


# ---------------------------------------------------------------------------
# Records and identifiers (§7.4)
# ---------------------------------------------------------------------------


def test_decision_id_is_stable_and_composed():
    """§7.4 fixes the id as ``f"{doc}:{kind}:{locator}"``.

    Stability is the point: it is what lets two runs' logs be diffed decision
    by decision, so a threshold change shows up as *which* decisions moved
    rather than as a wall of renumbered lines.
    """
    args = dict(
        kind="own_articulation",
        doc="par_cosit_26_20000629.docx",
        locator="p#46",
        rule_verdict="quoted",
        rule_confidence=0.55,
        rule_flagged=True,
        final_verdict="quoted",
    )
    record = DecisionRecord.build(**args)

    assert record.decision_id == "par_cosit_26_20000629.docx:own_articulation:p#46"
    assert DecisionRecord.build(**args).decision_id == record.decision_id

    moved = DecisionRecord.build(**{**args, "locator": "p#47"})
    assert moved.decision_id != record.decision_id, "the locator must discriminate"

    other_kind = DecisionRecord.build(**{**args, "kind": "heading"})
    assert other_kind.decision_id != record.decision_id, "the kind must discriminate"


def test_decision_ids_are_unique_within_a_document(corpus_log):
    """Two decisions sharing an id would silently merge in any report.

    Checked per document *and* across the corpus: the id carries the document
    name, so a collision across documents would mean the name is not being
    recorded, which the per-document check alone would not catch.
    """
    for stem in SAMPLES:
        ids = [r.decision_id for r in corpus_log.for_doc(doc_name(stem))]
        assert len(ids) == len(set(ids)), f"duplicate decision ids in {stem}: {ids}"

    all_ids = [r.decision_id for r in corpus_log]
    assert len(all_ids) == len(set(all_ids)) == len(corpus_log)


@pytest.mark.parametrize("stem", SAMPLES)
def test_every_flagged_decision_produces_a_record(stem, corpus_log):
    """Invariant #10, first half: a rule failure is never silent.

    Every decision the rules reached below `FLAG_THRESHOLD` is in the log,
    carries `rule_flagged`, and *says why* — a flag without a reason is an
    alarm nobody can act on across 300 documents.
    """
    records = corpus_log.for_doc(doc_name(stem))
    assert records, f"{stem} produced no decisions at all"

    flagged = {r.locator: r for r in records if r.rule_flagged}
    expected = FLAGGED_DECISIONS.get(stem, {})

    assert set(flagged) == set(expected), (
        f"{stem}: flagged {sorted(flagged)}, expected {sorted(expected)}"
    )

    for locator, (confidence, reason_substring) in expected.items():
        record = flagged[locator]
        assert record.rule_confidence == pytest.approx(confidence)
        assert reason_substring in record.reason, (
            f"{stem} {locator}: reason {record.reason!r} does not name its cause"
        )
        assert record.final_verdict == record.rule_verdict, (
            "with no referee the rule verdict must stand (§7.3 constraint 5)"
        )


def test_excerpt_is_bounded_in_the_record(corpus_log):
    """A decision log over 300 documents must stay a log, not a second corpus.

    `MAX_EXCERPT_IN_RECORD` is what keeps the excerpt an audit aid. Truncation
    also has to be visible, or a clipped excerpt reads as a short paragraph.
    """
    long_text = "Art. 1º " + "palavra " * 500
    record = DecisionRecord.build(
        kind="own_articulation",
        doc="synthetic.docx",
        locator="p#1",
        rule_verdict="own",
        rule_confidence=0.4,
        rule_flagged=True,
        final_verdict="own",
        excerpt=long_text,
    )

    assert len(record.excerpt) == MAX_EXCERPT_IN_RECORD
    assert record.excerpt.endswith("…"), "truncation must be visible in the text"
    assert record.excerpt.startswith("Art. 1º")

    for stored in corpus_log:
        assert len(stored.excerpt) <= MAX_EXCERPT_IN_RECORD, (
            f"{stored.decision_id} stores {len(stored.excerpt)} characters"
        )


def test_record_round_trips_through_dict(corpus_log):
    """The record is the report's raw material and must survive serialisation.

    Checked on a fully populated record — every referee field set — and then
    on all 47 real ones, because the fields that matter most (`overridden`,
    `abstained`, `cache_hit`) are exactly the ones a corpus run leaves False.
    """
    record = DecisionRecord.build(
        kind="own_articulation",
        doc="par_cosit_26_20000629.docx",
        locator="p#46",
        rule_verdict="own",
        rule_confidence=0.5,
        rule_flagged=True,
        final_verdict="quoted",
        excerpt="Art. 2º- O imposto de renda das pessoas físicas será devido.",
        reason="convicted only by a citation antecedent",
        referee_consulted=True,
        referee_verdict="quoted",
        referee_confidence=0.88,
        referee_rationale="preceded by a citation opening a quotation",
        referee_name="api",
        overridden=True,
        cache_hit=True,
    )

    assert DecisionRecord.from_dict(record.to_dict()) == record

    for stored in corpus_log:
        assert DecisionRecord.from_dict(stored.to_dict()) == stored


def test_log_json_round_trips(corpus_log):
    """`--decisions-report` writes JSON; a log that cannot be re-read is a leak.

    Round-tripping through the *text* rather than the dict is deliberate: it
    catches a value that serialises but does not survive JSON (a tuple, a
    dataclass, a float that stringifies lossily).
    """
    restored = DecisionLog.from_dict(json.loads(corpus_log.to_json()))

    assert len(restored) == len(corpus_log) == CORPUS_TOTAL
    assert restored.records == corpus_log.records
    assert restored.to_json() == corpus_log.to_json()


@pytest.mark.parametrize(
    "consulted, abstained, overridden, referee_verdict, final, agreed, overruled",
    [
        (False, False, False, None, "own", False, False),  # never asked
        (True, False, False, "own", "own", True, False),  # answered, said the same
        (True, True, False, None, "own", False, False),  # answered nothing
        (True, False, True, "quoted", "quoted", False, False),  # answered, overrode
        (True, False, False, "quoted", "own", False, True),  # answered, refused
    ],
)
def test_agreed_and_overruled_properties(
    consulted, abstained, overridden, referee_verdict, final, agreed, overruled
):
    """"Agreed" means the referee said what the rule said. Nothing weaker.

    This test originally asserted `agreed == consulted and not abstained and
    not overridden`, which is what the module first implemented. A mutation
    sweep showed the definition is wrong, and wrong in the direction that
    matters: a referee whose verdict **contradicts** the rule but is refused the
    override — because it was itself below `REFEREE_MIN_CONFIDENCE`, which is
    reachable with the shipped constants — was being counted as an agreement.
    §7.4 reads that number as *the rules were right but unsure*, so the error
    manufactures evidence that the thresholds are too conservative out of cases
    where nothing confirmed the rule at all.

    Hence the fourth bucket, `overruled`, and the last row below.
    """
    record = DecisionRecord.build(
        kind="own_articulation",
        doc="d.docx",
        locator="p#1",
        rule_verdict="own",
        rule_confidence=0.5,
        rule_flagged=True,
        final_verdict=final,
        referee_consulted=consulted,
        referee_verdict=referee_verdict,
        abstained=abstained,
        overridden=overridden,
    )
    assert record.agreed is agreed
    assert record.overruled is overruled
    assert not (record.agreed and record.overruled)


# ---------------------------------------------------------------------------
# The log lines (§7.4, invariant #10)
# ---------------------------------------------------------------------------


def test_rule_failure_emits_rule_failed_with_the_reason(caplog):
    """A rule that did not know its own answer says so, at WARNING.

    WARNING rather than INFO is the design: a flagged rule should not need a
    verbosity flag to become visible in a 300-document batch.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    reason = "convicted only by excerpt-run extension from an earlier quoted article"

    final, record = adjudicate(
        kind="own_articulation",
        doc="par_cosit_26_20000629.docx",
        locator="p#47",
        rule_verdict="quoted",
        rule_confidence=0.5,
        reason=reason,
        referee=None,
    )

    assert final == "quoted" and record.rule_flagged
    failures = warnings_containing(caplog, "RULE FAILED:")
    assert len(failures) == 1, failures
    line = failures[0]
    assert reason in line
    assert "par_cosit_26_20000629.docx p#47" in line
    assert "rule=quoted" in line and "conf=0.50" in line


def test_override_emits_warn_with_both_verdicts_and_the_rationale(caplog):
    """The line §7.4 draws in full: an override must be unmistakable.

    Both verdicts, both confidences and the rationale, because an override is
    the record of a rule having been *wrong*, and the next person's question is
    always "wrong how?".
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    rationale = "preceded by 'Lei nº 7.713, de 1988 -' introducing a quotation"
    referee = StubReferee(Verdict("quoted", 0.88, rationale))

    final, record = adjudicate(
        kind="own_articulation",
        doc="par_cosit_26_20000629.docx",
        locator="p#12",
        rule_verdict="own",
        rule_confidence=0.5,
        excerpt="Art. 2º- O imposto de renda…",
        reason="art label at body indent, citation antecedent ambiguous",
        referee=referee,
    )

    assert final == "quoted"
    assert record.overridden and record.referee_consulted and not record.abstained

    overrides = warnings_containing(caplog, "REFEREE OVERRODE RULE:")
    assert len(overrides) == 1, overrides
    line = overrides[0]
    assert "rule=own" in line and "conf=0.50" in line
    assert "referee=quoted" in line and "conf=0.88" in line
    assert "final=quoted" in line
    assert f'rationale="{rationale}"' in line


def test_agreement_is_logged_at_info_without_override(caplog):
    """Agreement is INFO: it is confirmation, not an intervention."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    referee = StubReferee(Verdict("quoted", 0.9, "the antecedent opens a quotation"))

    final, record = adjudicate(
        kind="own_articulation",
        doc="parecer_93_2018_decor_cgu_agu.docx",
        locator="p#36",
        rule_verdict="quoted",
        rule_confidence=0.55,
        referee=referee,
    )

    assert final == "quoted" and record.agreed and not record.overridden
    assert not warnings_containing(caplog, "REFEREE OVERRODE RULE:")

    agreed = [
        r.getMessage()
        for r in decision_lines(caplog)
        if r.levelno == logging.INFO and "referee agreed with rule" in r.getMessage()
    ]
    assert len(agreed) == 1, agreed
    assert "(quoted); no override" in agreed[0]
    assert "parecer_93_2018_decor_cgu_agu.docx p#36" in agreed[0]


def test_abstention_is_logged_as_warning(caplog):
    """An abstention is an outage, not an agreement, and is reported as one.

    §7.3 constraint 5 keeps the pipeline running; invariant #10 requires that
    it be visible that quality, not availability, is what degraded.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    referee = StubReferee(Verdict.abstain("ReadTimeout: provider did not answer"))

    final, record = adjudicate(
        kind="own_articulation",
        doc="par_cosit_26_20000629.docx",
        locator="p#53",
        rule_verdict="quoted",
        rule_confidence=0.5,
        referee=referee,
    )

    assert final == "quoted", "the rule verdict is retained on an abstention"
    assert record.abstained and not record.agreed and not record.overridden

    abstentions = warnings_containing(caplog, "REFEREE ABSTAINED:")
    assert len(abstentions) == 1, abstentions
    assert "ReadTimeout" in abstentions[0]
    assert "rule=quoted conf=0.50 retained" in abstentions[0]


def test_unconsulted_decision_logs_referee_skipped(caplog):
    """A confident rule is not asked — and the line says so, at INFO.

    This is §7.3 constraint 1 visible in the log: `referee=skipped` is how a
    reader distinguishes "the referee agreed" from "the referee was never
    needed", which is the difference between a cost and no cost.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    referee = StubReferee(Verdict("quoted", 0.99, "never asked"))

    final, record = adjudicate(
        kind="route",
        doc="port_mf_277_20180607.docx",
        locator="",
        rule_verdict="norma",
        rule_confidence=0.9,
        reason="all statutory gates passed",
        referee=referee,
    )

    assert final == "norma"
    assert referee.asked == [], "a confident rule must not reach the referee"
    assert not record.rule_flagged and not record.referee_consulted

    skipped = [
        r.getMessage()
        for r in decision_lines(caplog)
        if r.levelno == logging.INFO and "referee=skipped" in r.getMessage()
    ]
    assert len(skipped) == 1, skipped
    assert "rule=norma" in skipped[0] and "final=norma" in skipped[0]
    assert not warnings_containing(caplog, "RULE FAILED:")


def test_corpus_run_logs_exactly_four_rule_failures(caplog):
    """The threshold-drift alarm: 15 documents, four flagged decisions.

    If a change to the quotation guard's confidences moves this number, the
    referee starts being consulted about paragraphs the rules used to be sure
    of — a change in cost, in determinism under a cold cache, and in what
    `--decisions-report` means. That must never happen quietly, so the count
    and the four locators are pinned here rather than derived.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    sweep(referee=None)

    failures = warnings_containing(caplog, "RULE FAILED:")
    assert len(failures) == CORPUS_FLAGGED, "\n".join(failures)

    expected = {
        f"{doc_name(stem)} {locator}"
        for stem, locators in FLAGGED_DECISIONS.items()
        for locator in locators
    }
    for where in expected:
        assert any(where in line for line in failures), (
            f"no RULE FAILED line for {where}"
        )


# ---------------------------------------------------------------------------
# `--decisions-report` (§7.4)
# ---------------------------------------------------------------------------


def test_report_identities_reconcile_over_the_corpus(corpus_log):
    """Every document's counts close, and so do the corpus's.

    §9.3 pins `--referee=none` for the regression suite, which is why the
    plan's own `agreed + overrode == flagged` cannot be the identity checked
    here: nothing flagged is ever consulted, so both terms are zero while
    `flagged` is four. Amendment A-4b.4's two identities are the ones that hold
    in general, and `check()` is what asserts them.
    """
    for stem in SAMPLES:
        per_doc = DecisionLog(list(corpus_log.for_doc(doc_name(stem))))
        report = DecisionsReport.from_log(per_doc)
        assert report.check() is None, f"{stem}: {report.check()}"

    corpus = DecisionsReport.from_log(corpus_log)
    assert corpus.check() is None, corpus.check()
    assert corpus.total == CORPUS_TOTAL
    assert corpus.rule_only == CORPUS_RULE_ONLY
    assert corpus.flagged == CORPUS_FLAGGED
    assert corpus.consulted == 0, "§9.3: the default suite consults no referee"
    assert corpus.agreed == corpus.overrode == corpus.abstained == 0
    assert corpus.flagged_by_kind == (("own_articulation", CORPUS_FLAGGED),)


def test_plan_identity_holds_with_an_active_referee(refereed_log):
    """§7.4's own form of the identity, in the case where it applies.

    With every flagged decision consulted and none abstaining,
    `agreed + overrode == flagged` exactly — which is the plan's arithmetic,
    recovered as the special case A-4b.4 says it is. The referee reads recorded
    fixtures through a read-only cache and a transport that raises, so this is
    also the standing proof that the referee-assisted path costs zero network
    calls (§9.3).
    """
    report = DecisionsReport.from_log(refereed_log)

    assert report.check() is None, report.check()
    assert report.flagged == CORPUS_FLAGGED
    assert report.consulted == CORPUS_FLAGGED
    assert report.agreed + report.overrode == report.flagged
    assert report.agreed == CORPUS_FLAGGED, "every fixture confirms the rule"
    assert report.overrode == 0 and report.abstained == 0
    assert report.cache_hits == CORPUS_FLAGGED
    assert report.cache_hit_pct == 100.0
    assert report.total == CORPUS_TOTAL


def test_check_detects_a_broken_identity():
    """A report must fail loudly, and say *which* sum did not close.

    Returning False would leave the reader to re-derive the arithmetic by hand;
    the failure names the identity and shows the numbers, so a broken count is
    a one-line diagnosis.
    """
    broken = DecisionsReport(total=47, rule_only=40, flagged=4, consulted=0)
    problem = broken.check()

    assert problem is not None
    assert "rule_only + flagged != total" in problem
    assert "40" in problem and "4" in problem and "47" in problem

    miscounted = DecisionsReport(
        total=10, rule_only=6, flagged=4, consulted=4, agreed=2, overrode=1
    )
    problem = miscounted.check()
    assert problem is not None
    assert "agreed + overrode + overruled + abstained != consulted" in problem

    # The fourth bucket closes it: 2 + 1 + 1 + 0 == 4.
    balanced = DecisionsReport(
        total=10, rule_only=6, flagged=4, consulted=4, agreed=2, overrode=1, overruled=1
    )
    assert balanced.check() is None


def test_an_unsure_disagreeing_referee_lands_in_the_overruled_bucket():
    """The fourth bucket, end to end from `adjudicate` to the rendered report.

    This is the reachable case, not a hypothetical: with the shipped constants
    every flagged decision sits below `RULE_HIGH_CONFIDENCE`, so what decides an
    override is the *referee's* confidence. A referee that answers "own" against
    a rule's "quoted" at 0.4 confidence is refused — and must be counted as
    having been refused, not as having agreed.

    Before the `overruled` bucket existed this record was reported as an
    agreement, i.e. as evidence that the rules are right and merely too timid.
    """
    from lexml_nonstat.referee import REFEREE_MIN_CONFIDENCE, Verdict, adjudicate

    class UnsureDissenter:
        name = "unsure"

        def is_own_articulation(self, excerpt, ctx):
            return Verdict("own", REFEREE_MIN_CONFIDENCE - 0.2, "não tenho certeza")

        def is_heading(self, para, ctx):  # pragma: no cover - unused
            return Verdict()

        def section_kind(self, label, heading):  # pragma: no cover - unused
            return Verdict()

    log = DecisionLog()
    final, record = adjudicate(
        kind="own_articulation",
        doc="d.docx",
        locator="p#9",
        rule_verdict="quoted",
        rule_confidence=0.5,
        excerpt="Art. 16 - O custo de aquisição…",
        referee=UnsureDissenter(),
        log=log,
    )

    assert final == "quoted", "an unsure referee must not break a tie"
    assert record.referee_consulted and not record.abstained
    assert record.overridden is False
    assert record.agreed is False, "it disagreed; that is not agreement"
    assert record.overruled is True

    report = DecisionsReport.from_log(log)
    assert (report.consulted, report.agreed, report.overrode, report.overruled) == (
        1,
        0,
        0,
        1,
    )
    assert report.check() is None
    assert "referee overruled: 1" in render_report(report)


def test_consulted_may_not_exceed_flagged():
    """§7.3 constraint 1 as arithmetic: a confident rule is never adjudicated.

    A report showing more consultations than flags means somebody asked a
    referee about a decision the rules were sure of — money spent, determinism
    weakened, invariant #9 in doubt. `check()` catches it.
    """
    report = DecisionsReport(
        total=5, rule_only=4, flagged=1, consulted=2, agreed=2, overrode=0
    )
    problem = report.check()

    assert problem is not None
    assert "consulted > flagged" in problem
    assert "sure of" in problem, "the message should say why this is wrong"


def test_report_renders_every_section(refereed_log):
    """`--decisions-report` prints the whole §7.4 summary, reconciliation included.

    The rendered text is the artefact a human actually reads when deciding
    whether the rules generalise, so each number §7.4 names is asserted to be
    on the page — and so is the statement that the counts add up.
    """
    text = render_report(refereed_log)

    assert "Decisions:" in text and str(CORPUS_TOTAL) in text
    assert "Rule-only (confident):" in text and str(CORPUS_RULE_ONLY) in text
    assert "Flagged:" in text and "(8.5%)" in text
    assert "put to a referee:" in text
    assert "referee agreed:" in text and "referee overrode:" in text
    assert "referee abstained:" in text
    assert "Cache hit rate:" in text and "100.0%" in text
    assert "Flagged by kind:" in text and "own_articulation 4" in text
    assert "Counts reconcile." in text

    broken = DecisionsReport(total=47, rule_only=40, flagged=4)
    assert "COUNTS DO NOT RECONCILE:" in render_report(broken)


def test_report_ordering_is_deterministic():
    """Ties break by name, so the report is diffable (invariant #4).

    Anything a golden or a diff might touch has to be ordered, and a `Counter`
    is not. Two documents with one override each must always appear in the same
    order; a document with more overrides must always come first.
    """

    def override(doc: str, locator: str) -> DecisionRecord:
        return DecisionRecord.build(
            kind="own_articulation",
            doc=doc,
            locator=locator,
            rule_verdict="own",
            rule_confidence=0.5,
            rule_flagged=True,
            final_verdict="quoted",
            referee_consulted=True,
            referee_verdict="quoted",
            referee_confidence=0.9,
            overridden=True,
        )

    tied = DecisionLog([override("b_doc", "p#1"), override("a_doc", "p#1")])
    assert DecisionsReport.from_log(tied).overrides_by_doc == (
        ("a_doc", 1),
        ("b_doc", 1),
    )

    ranked = DecisionLog(
        [override("a_doc", "p#1"), override("b_doc", "p#1"), override("b_doc", "p#2")]
    )
    assert DecisionsReport.from_log(ranked).overrides_by_doc == (
        ("b_doc", 2),
        ("a_doc", 1),
    )


def test_records_stable_across_reruns_given_a_warm_cache():
    """Invariant #4: same input plus same cache ⇒ byte-identical telemetry.

    Determinism is usually asserted of the emitted XML, but the decision log is
    equally an output — it is what `--decisions-report` summarises and what a
    reviewer diffs between runs. If it moved between runs, every other
    determinism claim would be unverifiable through it.
    """
    first = sweep(referee=offline_referee())
    second = sweep(referee=offline_referee())

    assert first.to_json() == second.to_json()
    assert DecisionsReport.from_log(first).to_dict() == (
        DecisionsReport.from_log(second).to_dict()
    )
