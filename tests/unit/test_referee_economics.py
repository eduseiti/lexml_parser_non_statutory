"""Referee economics and reproducibility — Cycle 6 of the corpus-233 plan.

Plan §1.8 says the referee "earns its place": it overrode 127 rule decisions
across 53 documents and moved flatness 115 → 107. That makes it a **dependency
rather than an option**, and a dependency on a paid API is a reproducibility
problem before it is a cost problem.

This module pins the answer to both halves.

**Reproducibility.** `tests/corpus_referee_fixtures/` holds every answer the
233-document run asked for — 625 entries, recorded live from
`deepseek-v4-flash`. Replayed through the ordinary `RefereeCache(…,
read_only=True)` seam with the transport wired to raise, the whole corpus
adjudicates with **zero network calls**, and two replays agree byte for byte.

**Economics.** The referee's *marginal* value is not what §1.8 measured any
more, and that is this cycle's headline. Against the rules-only baseline Cycle 1
established (86 flat), the referee now buys **three** documents, not eight:
Cycle 3's `section_res` already admits the `RELATÓRIO`/`FUNDAMENTOS`/`CONCLUSÃO`
skeleton deterministically, which is most of what referee spend used to pay for.

**The rule question (§5.3), answered "no".** 35 of the 74 `nao`→`secao`
confirmations sit on texts that *also* appear as refusals — `RELATÓRIO` is
confirmed 19× and refused 2×, and bare roman numerals land on both sides — so a
text-keyed rule would be wrong in both directions. `test_the_heading_overrides_
are_not_rule_learnable` is that finding as an assertion rather than a claim.

The corpus these run against is **not** in `samples/`, so every test that needs
it skips when it is absent — the same graceful degradation `requires_nested`,
`requires_linker` and `test_urn_completeness.py` already apply.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.referee import CachedAPIReferee, NullReferee, RefereeCache
from lexml_nonstat.referee.api import DEFAULT_MODEL
from lexml_nonstat.telemetry import DecisionLog, DecisionsReport

from tests.conftest import REPO_ROOT

#: The committed answers, published by Cycle 6 deliverable 1.
FIXTURES = REPO_ROOT / "tests" / "corpus_referee_fixtures"

#: The 233-document corpus. Research data, outside the repository by design.
CORPUS = REPO_ROOT.parent / "br-taxqa-r_v2.0" / "original" / "nao_articulados"

requires_corpus = pytest.mark.skipif(
    not CORPUS.is_dir(),
    reason=f"the 233-document corpus is not present at {CORPUS} "
    "(research data, not a fixture)",
)

#: What the run recorded. A literal, because the point of a fixture set is that
#: it does not move: a changed count is either a deliberate re-record (reviewed
#: as a diff) or a bug.
EXPECTED_ENTRIES = 625

#: The measured replay, 2026-09-14. Asserted rather than described.
EXPECTED_QUESTIONS = 694
EXPECTED_HITS = 684
EXPECTED_MISSES = 10

#: Plan §1.8's override table, which reproduces exactly from the cache.
EXPECTED_OVERRIDES = {
    ("heading", "nao", "secao"): 74,
    ("own_articulation", "quoted", "own"): 50,
    ("quotation_boundary", "continuation", "boundary"): 3,
}
EXPECTED_OVERRIDE_DOCS = 53

#: Cycle 1's rules-only baseline, and what the referee moves it to (A-6.1).
FLAT_RULES_ONLY = 86
FLAT_REFEREED = 83

#: The three documents that actually gain structure from referee spend. Named,
#: because "three documents" is a number and *which* three is the finding.
GAINS_STRUCTURE = (
    "nota_pgfn_crj_1040_2015",
    "parecer_pgfn_crj_701_2016",
    "sc_cosit_200_20211214",
)


def explodes(*args, **kwargs):
    """A transport that must never be called."""
    raise AssertionError(
        "the transport was called; this path must make no network calls"
    )


def fixture_referee() -> CachedAPIReferee:
    """The offline corpus referee: recorded answers, no transport, no writes."""
    return CachedAPIReferee(
        cache=RefereeCache(FIXTURES, read_only=True),
        api_key=None,
        transport=explodes,
    )


_DOCS: list[tuple[Path, object]] = []


def corpus_documents():
    """Read the 233 documents once per session; re-reading them costs ~2.3s."""
    if not _DOCS:
        for path in sorted(CORPUS.glob("*.docx")):
            _DOCS.append((path, read_docx(path)))
    return _DOCS


def replay(referee):
    """Build every corpus model with ``referee``; return ``(log, shapes)``."""
    log = DecisionLog()
    shapes: dict[str, tuple] = {}
    for path, doc in corpus_documents():
        model = build_model(doc, filename=path.name, log=log, referee=referee)
        body = model.body
        signals = getattr(body, "signals", None)
        shapes[path.stem] = (
            bool(getattr(body, "flat", True)),
            str(getattr(signals, "flat_cause", "")),
            len(getattr(body, "sections", ()) or ()),
        )
    return log, shapes


_REPLAY: dict[str, tuple] = {}


def refereed_replay():
    """One cached refereed replay, shared — it is the expensive fixture here."""
    if "refereed" not in _REPLAY:
        referee = fixture_referee()
        cache = referee.cache
        log, shapes = replay(referee)
        _REPLAY["refereed"] = (log, shapes, referee, cache)
    return _REPLAY["refereed"]


def rules_only_replay():
    if "rules" not in _REPLAY:
        _REPLAY["rules"] = replay(NullReferee())
    return _REPLAY["rules"]


# ---------------------------------------------------------------------------
# 1. the fixture set itself (deliverable 1)
# ---------------------------------------------------------------------------


def test_the_fixture_set_is_the_recorded_size():
    """625 entries. A changed count is a re-record, and must be a reviewed diff."""
    entries = sorted(FIXTURES.glob("*.json"))
    assert len(entries) == EXPECTED_ENTRIES, (
        f"expected {EXPECTED_ENTRIES} recorded answers, found {len(entries)}; "
        "if this was a deliberate re-record, update EXPECTED_ENTRIES in the same commit"
    )


def test_every_fixture_parses_and_names_the_current_model():
    """The cache key covers the model, so an entry under another model is dead.

    This is the A-H.2 failure mode as an assertion: when `api.DEFAULT_MODEL` was
    last refreshed, every key moved, every lookup missed, and seven tests failed
    by falling through to a transport that asserts it is never called.
    """
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "verdict" in data, f"{path.name} carries no verdict"
        meta = data.get("meta") or {}
        assert meta.get("model") == DEFAULT_MODEL, (
            f"{path.name} was recorded under {meta.get('model')!r}, but the cache "
            f"key covers the model and the default is now {DEFAULT_MODEL!r} — "
            "this entry can never be found"
        )


def test_fixture_filenames_are_cache_keys():
    """A key is a filename: 32 hex characters, nothing else."""
    for path in sorted(FIXTURES.glob("*.json")):
        assert re.fullmatch(r"[0-9a-f]{32}", path.stem), path.name


def test_the_fixture_set_has_a_readme():
    """Provenance is not optional: these are live answers, and that must be said."""
    readme = FIXTURES / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert DEFAULT_MODEL in text
    assert "read_only" in text or "read-only" in text


# ---------------------------------------------------------------------------
# 2. reproducibility — the cycle's exit criterion
# ---------------------------------------------------------------------------


@requires_corpus
def test_a_refereed_corpus_run_makes_no_network_call():
    """§9.3's guarantee at corpus scale, and Cycle 6's exit criterion.

    The transport raises on any call. Reaching the end of all 233 documents is
    therefore proof that every question was answered from disk.
    """
    _log, _shapes, referee, _cache = refereed_replay()
    assert referee.calls == 0, (
        f"{referee.calls} network call(s) were made; a refereed corpus run must "
        "be reproducible offline"
    )


@requires_corpus
def test_the_cache_answers_almost_every_question():
    """684 of 694, and the ten that miss are abstentions (see below)."""
    _log, _shapes, _referee, cache = refereed_replay()
    assert cache.hits == EXPECTED_HITS
    assert cache.misses == EXPECTED_MISSES
    assert cache.hits / (cache.hits + cache.misses) > 0.98


@requires_corpus
def test_the_misses_are_all_abstentions_that_change_nothing():
    """A miss is acceptable only because `api.py` never caches an abstention.

    "A timeout is a fact about the network, not about the question." So these
    ten are absent *by design*, not missing — and every one retains its rule
    verdict, so the published set reproduces the run exactly.
    """
    log, _shapes, _referee, _cache = refereed_replay()
    abstentions = [record for record in log if record.abstained]

    assert len(abstentions) == EXPECTED_MISSES, (
        f"expected {EXPECTED_MISSES} abstentions to match the {EXPECTED_MISSES} "
        f"cache misses, found {len(abstentions)}"
    )
    changed = [r for r in abstentions if r.rule_verdict != r.final_verdict]
    assert not changed, (
        "an abstention changed an outcome, so the missing entries are not inert: "
        + ", ".join(f"{r.doc} {r.locator}" for r in changed)
    )


@requires_corpus
def test_the_read_only_fixture_cache_never_grows():
    """An unrecorded question must not silently record itself.

    Without `read_only=True` a miss would write a new file here and become a
    live call on the next run — §9.3's guarantee evaporating with no diff to
    show for it.
    """
    before = {path.name for path in FIXTURES.glob("*.json")}
    referee = fixture_referee()
    replay(referee)
    after = {path.name for path in FIXTURES.glob("*.json")}
    assert after == before, f"the read-only cache grew: {after - before}"


@requires_corpus
def test_two_refereed_runs_are_identical():
    """Invariant #4 with a referee in the loop: same input, same cache, same output."""
    first_log, first_shapes = replay(fixture_referee())
    second_log, second_shapes = replay(fixture_referee())

    assert first_shapes == second_shapes
    assert (
        DecisionsReport.from_log(first_log).to_dict()
        == DecisionsReport.from_log(second_log).to_dict()
    )


@requires_corpus
def test_the_decision_counts_reconcile():
    """§7.4's identities hold over 233 documents, not just 15 samples."""
    log, _shapes, _referee, _cache = refereed_replay()
    report = DecisionsReport.from_log(log)
    assert report.check() is None, report.check()


# ---------------------------------------------------------------------------
# 3. what the referee actually buys (deliverable 2, amendment A-6.1)
# ---------------------------------------------------------------------------


@requires_corpus
def test_the_overrides_reproduce_the_plans_table():
    """Plan §1.8's 127 overrides, from disk, with no network call.

    §1.8 is *right* about what the referee did. It is only the flatness
    consequence that has moved — see the next test.
    """
    log, _shapes, _referee, _cache = refereed_replay()
    pairs: collections.Counter = collections.Counter()
    docs: set[str] = set()
    for record in log:
        if record.overridden:
            pairs[
                (record.kind, str(record.rule_verdict), str(record.referee_verdict))
            ] += 1
            docs.add(record.doc)

    assert dict(pairs) == EXPECTED_OVERRIDES
    assert sum(pairs.values()) == 127
    assert len(docs) == EXPECTED_OVERRIDE_DOCS


@requires_corpus
def test_the_referee_now_moves_flatness_86_to_83():
    """Amendment A-6.1 — the cycle's headline, and a correction to §1.8.

    §1.8 records 115 → 107 (eight documents). That was measured *before*
    Cycle 3, whose `section_res` admits the soluções' title-case skeleton with
    no referee at all. Against Cycle 1's rules-only baseline of 86, the referee
    now buys three documents.
    """
    _rules_log, rules_shapes = rules_only_replay()
    _log, shapes, _referee, _cache = refereed_replay()

    flat_rules = sum(1 for shape in rules_shapes.values() if shape[0])
    flat_refereed = sum(1 for shape in shapes.values() if shape[0])

    assert flat_rules == FLAT_RULES_ONLY, (
        f"Cycle 1's rules-only baseline was {FLAT_RULES_ONLY}; measured {flat_rules}"
    )
    assert flat_refereed == FLAT_REFEREED
    assert flat_rules - flat_refereed == 3


@requires_corpus
def test_the_three_documents_that_gain_structure_are_named():
    """Which three, not just how many — the finding is the identity."""
    _rules_log, rules_shapes = rules_only_replay()
    _log, shapes, _referee, _cache = refereed_replay()

    gained = tuple(
        sorted(
            stem
            for stem in shapes
            if rules_shapes[stem][0] and not shapes[stem][0]
        )
    )
    assert gained == tuple(sorted(GAINS_STRUCTURE))


@requires_corpus
def test_the_referee_never_removes_structure():
    """Confirm-only, at corpus scale: a referee may add sections, never delete them.

    Invariant #8 as an economic statement — referee spend cannot make a document
    worse, which is what makes a cache miss a degradation in quality only.
    """
    _rules_log, rules_shapes = rules_only_replay()
    _log, shapes, _referee, _cache = refereed_replay()

    regressions = [
        stem
        for stem in shapes
        if not rules_shapes[stem][0] and shapes[stem][0]
    ]
    assert not regressions, (
        f"the referee made these documents flat that the rules did not: {regressions}"
    )


# ---------------------------------------------------------------------------
# 4. should the overrides become a rule? (deliverable 3, plan §5.3 — "no")
# ---------------------------------------------------------------------------


def _heading_texts(log):
    confirmed: list[str] = []
    refused: list[str] = []
    for record in log:
        if record.kind != "heading" or not record.referee_consulted:
            continue
        (confirmed if record.referee_verdict == "secao" else refused).append(
            record.excerpt
        )
    return collections.Counter(confirmed), collections.Counter(refused)


@requires_corpus
def test_the_heading_overrides_are_not_rule_learnable():
    """§5.3 answered: a text-keyed rule would be wrong in both directions.

    The same string is confirmed in one document and refused in another —
    `RELATÓRIO` 19 `secao` / 2 `nao`, `ORDEM DE INTIMAÇÃO` 7 / 1, and the bare
    roman numerals on both sides. This is the evidence behind Cycle 6's
    recommendation *not* to convert the 74 overrides into a rule.
    """
    log, _shapes, _referee, _cache = refereed_replay()
    confirmed, refused = _heading_texts(log)

    ambiguous = set(confirmed) & set(refused)
    assert ambiguous, (
        "no heading text appears as both 'secao' and 'nao'; if that is now true, "
        "the rule question in plan §5.3 deserves to be re-opened"
    )
    assert "RELATÓRIO" in ambiguous

    covered = sum(confirmed[text] for text in ambiguous)
    assert covered >= 30, (
        f"only {covered} confirmations sit on ambiguous texts; the recommendation "
        "in docs/ is calibrated against ~35 of 74"
    )


@requires_corpus
def test_the_unambiguous_confirmations_are_mostly_already_declared_sections():
    """The learnable part is the part Cycle 3 already learned, without a referee.

    `FUNDAMENTOS`, `CONCLUSÃO` and `RELATÓRIO` dominate the unambiguous
    confirmations — and `solucao_consulta.section_res` admits exactly those
    deterministically. That is *why* the flatness delta fell from 8 to 3, and
    why paying an API for them a second time buys nothing.
    """
    log, _shapes, _referee, _cache = refereed_replay()
    confirmed, refused = _heading_texts(log)

    unambiguous = {
        text: count for text, count in confirmed.items() if text not in refused
    }
    assert unambiguous

    skeleton = {"FUNDAMENTOS", "CONCLUSÃO", "FUNDAMENTOS LEGAIS", "EMENTA"}
    from_skeleton = sum(
        count for text, count in unambiguous.items() if text in skeleton
    )
    assert from_skeleton >= 0.5 * sum(unambiguous.values()), (
        "the unambiguous confirmations are no longer dominated by the declared "
        "skeleton; deliverable 3's recommendation should be re-measured"
    )
