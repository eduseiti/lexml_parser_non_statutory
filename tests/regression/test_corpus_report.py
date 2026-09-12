"""``corpus`` over the real corpus — Cycle 9, amendment **A-9.3**.

Plan §10's top risk is that rules tuned on 15 samples will not survive 300, and
A-9.3's answer is a batch command that walks a directory, isolates every
document, and emits **one report whose numbers reconcile**. This module is the
regression evidence for that claim, on the only corpus this repository actually
has.

**Two tests here carry the cycle.** The others would survive a `corpus` command
that quietly grew its own opinions.

:func:`test_decisions_reconcile_with_decisions_report` requires the embedded
:class:`~.telemetry.DecisionsReport` to **equal** what the delivered
``decisions-report`` subcommand produces over the same corpus. Decision
telemetry has exactly one source of truth (spec decision N-3); the moment
``corpus`` could disagree with ``decisions-report`` about §7.4's counts, one of
them is wrong and nothing says which.

:func:`test_route_tallies_match_the_library` pins the tally to ``build_model``
and ``assess_viability`` — the library — rather than to a literal. Amendment
**A-8.4** set that precedent for the CLI ("the CLI's answer is pinned to the
library's on all 15 samples, never to a literal"), and the reasoning transfers
exactly: a corpus report that restated ``generico 14 · norma 1`` as a constant
would keep passing after a routing change, which is the one moment it exists to
notice.

**Cost.** A validated run over all 15 samples is the expensive thing in this
module, so it is built **once** per session and shared. Tests that do not need
validation say so, which is also how the corpus report distinguishes
``valid=None`` ("not checked") from ``valid=False``.

§9.3 pins ``--referee=none`` for the whole suite and Cycle 8e's linker defaults
to ``none``, so nothing here reaches the network — asserted directly by
:func:`test_corpus_makes_no_network_call` rather than assumed.
"""

from __future__ import annotations

import io
import json
import re
import socket
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from lexml_nonstat import cli
from lexml_nonstat.corpus import render_corpus_report, run_corpus
from lexml_nonstat.ingest import read_document
from lexml_nonstat.model import build_model
from lexml_nonstat.telemetry import DecisionLog, DecisionsReport

from tests.conftest import LINKER_FIXTURES, REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(SAMPLES_DIR.glob("*.docx"))

#: The linked goldens, whose `Remissao` elements this module's reference tally
#: is pinned against. Sixteen files for fifteen samples — `port_mf_277` carries
#: an annex.
LINKED_GOLDENS = REPO_ROOT / "tests" / "golden" / "generico_linked"

#: The statutory linked goldens — two files for the one sample §4.4 routes to
#: `norma`. Needed because `--emitter=auto` renders that sample *here*, not in
#: `generico_linked/`; see :func:`expected_references_for_the_auto_route`.
NORMA_LINKED_GOLDENS = REPO_ROOT / "tests" / "golden" / "norma_linked"

#: The one sample §4.4 routes to the statutory emitter. Stated once here and
#: cross-checked against the library, never used as the *source* of the claim.
STATUTORY_SAMPLE = "port_mf_277_20180607.docx"


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI in-process — ``test_cli_corpus.py``'s helper, verbatim."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="session")
def corpus_report():
    """One validated run over all 15 samples, shared by the whole module.

    Validation on, because ``valid``/``invalid``/``validated`` are part of what
    the report claims and a run with validation skipped could not support them.
    """
    return run_corpus([SAMPLES_DIR])


@pytest.fixture(scope="session")
def fast_report():
    """The same run with validation skipped — for tests about tallies only."""
    return run_corpus([SAMPLES_DIR], validate_output=False)


# ---------------------------------------------------------------------------
# the report reconciles
# ---------------------------------------------------------------------------


def test_the_corpus_is_the_expected_size() -> None:
    """A sample added without a golden would otherwise pass silently."""
    assert len(SAMPLES) == 15


def test_corpus_over_all_samples_reconciles(corpus_report) -> None:
    """E-7: every identity holds over the real corpus, and nothing failed.

    ``check()`` returning ``None`` is the deliverable A-9.3 calls "reconciling";
    the negative cases proving it *can* fail live in
    ``tests/unit/test_corpus.py``, so this assertion is evidence rather than a
    tautology.
    """
    assert corpus_report.check() is None, corpus_report.check()
    assert corpus_report.total == 15
    assert corpus_report.failed == 0
    assert corpus_report.succeeded == 15


def test_every_sample_validates_in_a_corpus_run(corpus_report) -> None:
    """Invariant #1 at corpus scale, and the tri-state ``valid`` honoured.

    ``validated == total`` is the half that matters: "0 invalid" means nothing
    unless everything was actually checked.
    """
    assert corpus_report.validated == 15
    assert corpus_report.invalid == 0
    assert all(o.valid is True for o in corpus_report.outcomes)


def test_validation_can_be_skipped_and_says_so(fast_report) -> None:
    """``--no-validate`` records "not checked", not "valid".

    Collapsing the two would make a fast run indistinguishable from a clean
    one — the single most misleading thing a corpus report could do.
    """
    assert fast_report.validated == 0
    assert fast_report.invalid == 0
    assert all(o.valid is None for o in fast_report.outcomes)
    assert fast_report.check() is None


def test_exactly_one_sample_routes_to_norma(fast_report) -> None:
    """§4.4's ground truth, agreeing with the existing CLI test.

    ``test_cli_corpus.py::test_exactly_one_sample_routes_to_norma`` makes the
    same claim through ``build_model``. Restating it here as a literal would be
    a second source of truth, so the sample is identified from the report and
    the *library* is asked to confirm it.
    """
    routed = [o for o in fast_report.outcomes if o.route == "norma"]

    assert len(routed) == 1
    assert Path(routed[0].source).name == STATUTORY_SAMPLE
    assert dict(fast_report.by_route())["norma"] == 1

    model = build_model(
        read_document(SAMPLES_DIR / STATUTORY_SAMPLE), filename=STATUTORY_SAMPLE
    )
    assert model.route == "norma", "the library, not this test, decides the route"


def test_route_tallies_match_the_library(fast_report) -> None:
    """**A-8.4's precedent**: pinned to the library, never to a literal.

    Every per-document field the report tallies is recomputed here by calling
    ``build_model`` directly — the same function ``run_corpus`` calls — and the
    aggregate must fall out of it. A corpus report that had started deriving
    routes or profiles of its own would pass an exit-code test and fail this
    one, which is the whole reason this test exists rather than an assertion
    that the tally equals ``generico 14 · norma 1``.
    """
    from collections import Counter

    routes: Counter[str] = Counter()
    profiles: Counter[str] = Counter()
    for path in SAMPLES:
        model = build_model(read_document(path), filename=path.name)
        routes[model.route] += 1
        profiles[model.profile] += 1

    def ranked(counter):
        return tuple(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))

    assert fast_report.by_route() == ranked(routes)
    assert fast_report.by_profile() == ranked(profiles)
    assert sum(n for _, n in fast_report.by_route()) == fast_report.succeeded

    by_source = {Path(o.source).name: o for o in fast_report.outcomes}
    for path in SAMPLES:
        model = build_model(read_document(path), filename=path.name)
        assert by_source[path.name].route == model.route
        assert by_source[path.name].profile == model.profile


def test_blockers_match_the_librarys_viability(fast_report) -> None:
    """The blocker tally is ``assess_viability``'s answer, not a recount.

    §4's blockers are why 14 of 15 samples cannot be published as a `Norma`;
    a corpus report that softened or invented one would misstate exactly the
    thing a 300-document run is being used to measure.
    """
    by_source = {Path(o.source).name: o for o in fast_report.outcomes}

    for path in SAMPLES:
        model = build_model(read_document(path), filename=path.name)
        expected = tuple(b.code for b in model.viability.blockers)
        assert by_source[path.name].blockers == expected, path.name


def test_decisions_reconcile_with_decisions_report(fast_report) -> None:
    """The embedded report **equals** ``decisions-report``'s over the same corpus.

    This is the test that keeps ``corpus`` from becoming a second source of
    truth for §7.4's counts (spec decision N-3). The expected value is built the
    way ``cli._cmd_decisions_report`` builds it — one shared
    :class:`~.telemetry.DecisionLog` threaded through ``build_model`` for every
    document — so equality here means the two commands are reporting the same
    telemetry, not merely similar-looking numbers.

    Equality of the whole frozen dataclass, deliberately: asserting only
    ``total`` would let the per-kind breakdowns drift apart unnoticed.
    """
    log = DecisionLog()
    for path in SAMPLES:
        build_model(read_document(path), filename=path.name, log=log)
    expected = DecisionsReport.from_log(log)

    assert fast_report.decisions == expected
    assert fast_report.decisions.to_dict() == expected.to_dict()
    assert fast_report.decisions.check() is None

    # And the delivered command's own rendered output agrees, which is what a
    # user actually reads. `render_report` is what `decisions-report` prints.
    code, out, _ = _run(["decisions-report"] + [str(p) for p in SAMPLES])
    assert code == 0
    assert f"Decisions:            {expected.total:,}" in out


def test_the_corpus_consults_no_referee(fast_report) -> None:
    """§9.3 pins ``--referee=none``: flagged decisions are never adjudicated.

    A corpus run that started consulting a referee would change cost,
    determinism and the meaning of every number in the report — never quietly.
    """
    assert fast_report.decisions.consulted == 0
    assert fast_report.decisions.agreed == 0
    assert fast_report.decisions.overrode == 0
    assert fast_report.decisions.abstained == 0
    assert fast_report.decisions.flagged_by_kind == (
        ("own_articulation", 4),
        ("quotation_boundary", 3),
    )


# ---------------------------------------------------------------------------
# per-document isolation — the point of the command
# ---------------------------------------------------------------------------


@pytest.fixture
def corpus_with_one_corrupt(tmp_path) -> Path:
    """The 15 samples plus one unreadable file, in a scratch directory.

    Symlinked rather than copied: the corpus is 15 `.docx` files and copying
    them per test is pure cost. Nothing here writes into ``samples/``.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for path in SAMPLES:
        (corpus / path.name).symlink_to(path)
    # Sorts first, so `--stop-on-error` meets it before any good document —
    # otherwise "it stopped" and "it finished" are indistinguishable.
    (corpus / "AAA_corrupt.docx").write_bytes(b"this is not a DOCX package")
    return corpus


def test_one_unreadable_document_does_not_abort_the_run(corpus_with_one_corrupt) -> None:
    """Isolation is the deliverable: 1 bad file among 16 leaves 15 processed.

    A batch that abandoned its work on the first bad document would be useless
    at 300, which is the case A-9.3 is aimed at. The exit code is still ``1`` —
    the failure is isolated, not forgiven.
    """
    report = run_corpus([corpus_with_one_corrupt], validate_output=False)

    assert report.total == 16
    assert report.succeeded == 15
    assert report.failed == 1
    assert report.check() is None, report.check()

    bad = [o for o in report.outcomes if not o.ok]
    assert len(bad) == 1
    assert Path(bad[0].source).name == "AAA_corrupt.docx"
    assert bad[0].error, "a failure must say what happened"
    assert bad[0].route == ""

    code, _, err = _run(
        ["corpus", "--no-validate", str(corpus_with_one_corrupt)]
    )
    assert code == 1, err
    assert "Traceback" not in err


def test_a_failed_document_is_named_in_the_text_report(corpus_with_one_corrupt) -> None:
    """At 300 documents the interesting line is *which* ones did not work."""
    code, out, _ = _run(["corpus", "--no-validate", str(corpus_with_one_corrupt)])

    assert code == 1
    assert "AAA_corrupt.docx" in out
    assert "failed:              1" in out


def test_stop_on_error_stops(corpus_with_one_corrupt) -> None:
    """``--stop-on-error`` opts out of isolation, and actually halts.

    The corrupt file sorts first, so a run that continued would record 16
    outcomes. Recording exactly one — the failure — is the only result that
    distinguishes halting from finishing.
    """
    report = run_corpus(
        [corpus_with_one_corrupt], validate_output=False, stop_on_error=True
    )

    assert report.total == 1
    assert report.failed == 1
    assert report.succeeded == 0
    assert not report.outcomes[0].ok

    code, _, err = _run(
        ["corpus", "--no-validate", "--stop-on-error", str(corpus_with_one_corrupt)]
    )
    assert code == 1, err
    assert "Traceback" not in err


def test_an_all_bad_corpus_still_reconciles(tmp_path) -> None:
    """The degenerate case: nothing succeeded, and the numbers still close.

    A report is most likely to be believed when it is least likely to be
    checked, so the identities have to hold when every document failed too.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name in ("a.docx", "b.docx"):
        (corpus / name).write_bytes(b"not a docx")

    report = run_corpus([corpus], validate_output=False)

    assert (report.total, report.succeeded, report.failed) == (2, 0, 2)
    assert report.by_route() == ()
    assert report.check() is None, report.check()


# ---------------------------------------------------------------------------
# the CLI surface
# ---------------------------------------------------------------------------


def test_corpus_defaults_to_the_samples_directory() -> None:
    """``paths`` is optional here, unlike every other subcommand.

    A bare ``corpus`` means ``samples/`` — the corpus this repository has — so
    the documented ``make corpus`` recipe and the E-7 exit criterion run the
    same thing the tests do.
    """
    code, out, err = _run(["corpus", "--no-validate"])

    assert code == 0, err
    assert "Documents:             15" in out
    assert "Reconciliation: ok" in out


def test_limit_processes_only_the_first_n() -> None:
    """`--limit` is the flag that makes a 300-document corpus explorable."""
    code, out, err = _run(["corpus", "--no-validate", "--limit=3", str(SAMPLES_DIR)])

    assert code == 0, err
    assert "Documents:             3" in out


def test_json_and_text_agree() -> None:
    """Two renderings of one report; neither may hold a number the other lacks.

    A JSON consumer and a human reading the text must not be able to reach
    different conclusions about the same run — the failure mode is a dashboard
    that disagrees with the console and no way to tell which is right.
    """
    _, text, _ = _run(["corpus", "--no-validate", str(SAMPLES_DIR)])
    code, raw, err = _run(
        ["corpus", "--no-validate", "--format=json", str(SAMPLES_DIR)]
    )
    assert code == 0, err
    data = json.loads(raw)

    assert f"Documents:             {data['total']:,}" in text
    assert f"succeeded:           {data['succeeded']:,}" in text
    assert f"failed:              {data['failed']:,}" in text

    for key, label in (
        ("by_route", "Routes:"),
        ("by_profile", "Profiles:"),
        ("by_emitter", "Emitters:"),
        ("by_blocker", "Blockers:"),
        ("by_warning", "Warnings:"),
    ):
        line = next(l for l in text.splitlines() if l.startswith(label))
        for name, count in data[key]:
            assert f"{name} {count}" in line, f"{label} {name} missing from the text"

    assert data["decisions"]["total"] == 50
    assert f"Decisions:            {data['decisions']['total']:,}" in text


def test_json_documents_carry_every_outcome() -> None:
    """`--format=json` reports per-document rows, not only the aggregate."""
    _, raw, _ = _run(["corpus", "--no-validate", "--format=json", str(SAMPLES_DIR)])
    data = json.loads(raw)

    assert len(data["documents"]) == 15
    assert [Path(d["source"]).name for d in data["documents"]] == [
        p.name for p in SAMPLES
    ]
    assert all(d["ok"] for d in data["documents"])


def test_report_is_deterministic() -> None:
    """Invariant #4: two runs are byte-identical, text and JSON alike.

    Determinism is asserted of the emitted XML everywhere else in this suite;
    the corpus report is equally an output — it is what a reviewer diffs between
    two runs to see what a change did to 300 documents.
    """
    _, first_text, _ = _run(["corpus", "--no-validate", str(SAMPLES_DIR)])
    _, second_text, _ = _run(["corpus", "--no-validate", str(SAMPLES_DIR)])
    assert first_text == second_text

    _, first_json, _ = _run(
        ["corpus", "--no-validate", "--format=json", str(SAMPLES_DIR)]
    )
    _, second_json, _ = _run(
        ["corpus", "--no-validate", "--format=json", str(SAMPLES_DIR)]
    )
    assert first_json == second_json

    assert render_corpus_report(
        run_corpus([SAMPLES_DIR], validate_output=False)
    ) == render_corpus_report(run_corpus([SAMPLES_DIR], validate_output=False))


def test_the_text_report_states_its_reconciliation(corpus_report) -> None:
    """The check is *printed*, so a reader never has to trust the tallies blind."""
    text = render_corpus_report(corpus_report)

    assert "Reconciliation: ok" in text
    assert "validated:           15" in text and "(0 invalid)" in text
    assert re.search(r"^Routes: +generico 14 · norma 1$", text, re.MULTILINE)


def test_an_unreconciling_report_is_an_error_exit(monkeypatch) -> None:
    """A report whose numbers do not add up fails the run (exit 1).

    Numbers that do not reconcile are a failure of the run, not a footnote in
    it: a printed report that is known to be inconsistent would still be read,
    and believed.
    """
    from lexml_nonstat import corpus as corpus_module

    broken = corpus_module.CorpusReport(
        outcomes=(
            corpus_module.DocumentOutcome(source="a.docx", ok=True, route="nonsense"),
        )
    )
    monkeypatch.setattr(corpus_module, "run_corpus", lambda *a, **k: broken)

    code, _, err = _run(["corpus", "--no-validate", str(SAMPLES_DIR)])

    assert code == 1
    assert "does not reconcile" in err
    assert "unknown route" in err


# ---------------------------------------------------------------------------
# no network, no subprocess
# ---------------------------------------------------------------------------


def test_corpus_makes_no_network_call(monkeypatch) -> None:
    """E-8: the default configuration reaches nothing.

    The referee defaults to ``none`` (§7.3 constraint 7) and the linker to
    ``none`` (A-L.7), so a corpus run has nothing to call — but "has nothing to
    call" is a claim about code that changes, and this is the assertion that
    keeps it true. ``socket.socket`` is replaced by a constructor that raises,
    so any attempt at any protocol fails the test rather than merely being slow.
    """

    def forbidden(*args, **kwargs):  # pragma: no cover - firing it is the failure
        raise AssertionError("a corpus run reached for the network")

    monkeypatch.setattr(socket, "socket", forbidden)

    report = run_corpus([SAMPLES_DIR], validate_output=False)

    assert report.total == 15
    assert report.failed == 0
    assert report.check() is None


def test_corpus_cli_makes_no_network_call(monkeypatch) -> None:
    """The same guarantee through the command a user actually types."""

    def forbidden(*args, **kwargs):  # pragma: no cover - firing it is the failure
        raise AssertionError("the corpus command reached for the network")

    monkeypatch.setattr(socket, "socket", forbidden)

    code, out, err = _run(["corpus", "--no-validate", str(SAMPLES_DIR)])

    assert code == 0, err
    assert "Reconciliation: ok" in out


# ---------------------------------------------------------------------------
# references — pinned to the committed linked goldens
# ---------------------------------------------------------------------------


def remissao_in(directory: Path, stem: str) -> int:
    """Every ``Remissao`` in one sample's committed goldens, annex included.

    Counted off the golden *files* rather than restated as a number: the
    goldens are the reviewed artifact (plan §9.4), so a linker change moves the
    golden diff and this test together and neither can drift alone.
    """
    from lxml import etree

    from lexml_nonstat.render.common import LEXML_NS

    return sum(
        len(etree.parse(str(path)).findall(f".//{{{LEXML_NS}}}Remissao"))
        for path in sorted(directory.glob(f"{stem}.*xml"))
        if path.name == f"{stem}.xml" or path.name.startswith(f"{stem}.anexo")
    )


def expected_references_for_the_auto_route() -> int:
    """The goldens that correspond to the route each sample **actually takes**.

    ``--emitter=auto`` follows the route, so the comparable golden differs per
    document: ``generico_linked/`` for the 14 open-route samples, and
    ``norma_linked/`` for ``port_mf_277``, the one sample §4.4 sends down the
    statutory route. Summing a bare glob of ``generico_linked/`` instead would
    compare an ``auto`` run against a set of documents it never rendered.

    **The two totals differ by two, and that is not a defect.** ``port_mf_277``
    resolves 17 references rendered flat (15 in the annex, 2 in the primary) but
    15 rendered statutorily — the annex is identical and the primary carries
    none, because ``norma``'s ``ParteInicial`` is not linked. That is Cycle 8e's
    recorded open item **O-4**, reached here through the validate-then-fallback
    artifact of amendment **A-5.5**. Both tallies are correct; they are tallies
    over two different sets of documents.
    """
    statutory_stem = Path(STATUTORY_SAMPLE).stem
    total = sum(
        remissao_in(LINKED_GOLDENS, path.stem)
        for path in SAMPLES
        if path.stem != statutory_stem
    )
    return total + remissao_in(NORMA_LINKED_GOLDENS, statutory_stem)


def test_reference_counts_match_the_linked_goldens() -> None:
    """The ``auto`` corpus tally equals the route-correspondent goldens (Cycle 8e).

    ``auto`` is the default a user gets, so it is the tally worth pinning — and
    it is pinned to the goldens for the emitter each document actually used,
    built by :func:`expected_references_for_the_auto_route`, rather than to a
    literal or to a directory glob that happens to be close.

    The fixture linker serves recorded answers through a read-only cache: no
    binary, no subprocess, and a reference the fixtures do not contain simply
    does not resolve.
    """
    from lexml_nonstat.refs import LinkerCache, build_linker

    linker = build_linker(
        "fixtures", cache=LinkerCache(LINKER_FIXTURES, read_only=True)
    )
    report = run_corpus([SAMPLES_DIR], linker=linker, validate_output=False)

    expected = expected_references_for_the_auto_route()
    assert expected == 251, "the committed linked goldens changed; review the diff"
    assert report.references == expected
    assert dict(report.by_route())["norma"] == 1
    assert report.check() is None


def test_forcing_the_flat_emitter_matches_the_generico_goldens() -> None:
    """The other half of the pair, which makes **both** numbers explicable.

    Forced to ``generico``, every sample is rendered the way
    ``generico_linked/`` was written, and the tally matches that directory
    exactly. Holding both assertions means the 251/253 difference is accounted
    for by ``port_mf_277``'s two flat-primary references (O-4) rather than
    standing as an unexplained discrepancy the next reader must rediscover.
    """
    from lexml_nonstat.refs import LinkerCache, build_linker

    linker = build_linker(
        "fixtures", cache=LinkerCache(LINKER_FIXTURES, read_only=True)
    )
    report = run_corpus(
        [SAMPLES_DIR], emitter="generico", linker=linker, validate_output=False
    )

    expected = sum(remissao_in(LINKED_GOLDENS, path.stem) for path in SAMPLES)
    assert expected == 253, "the committed linked goldens changed; review the diff"
    assert report.references == expected
    assert report.check() is None

    # The gap is exactly `port_mf_277`'s flat primary — O-4, stated as
    # arithmetic so a change in either tally cannot hide inside the other.
    statutory_stem = Path(STATUTORY_SAMPLE).stem
    assert expected - expected_references_for_the_auto_route() == (
        remissao_in(LINKED_GOLDENS, statutory_stem)
        - remissao_in(NORMA_LINKED_GOLDENS, statutory_stem)
    ) == 2


def test_no_references_are_resolved_without_a_linker(fast_report) -> None:
    """A-L.7's default: no linker means no `Remissao`, not a silent best effort."""
    assert fast_report.references == 0
    assert all(o.references == 0 for o in fast_report.outcomes)


def test_the_linked_cli_run_reports_the_same_tally() -> None:
    """The flags a user types reach the same number the library produced.

    ``--linker=fixtures`` requires ``--linker-cache``: without a directory to
    serve recorded answers from there is nothing to resolve against, and the
    CLI refuses rather than silently linking nothing.
    """
    code, raw, err = _run(
        [
            "corpus",
            "--no-validate",
            "--format=json",
            "--emitter=generico",
            "--linker=fixtures",
            f"--linker-cache={LINKER_FIXTURES}",
            str(SAMPLES_DIR),
        ]
    )

    assert code == 0, err
    assert json.loads(raw)["references"] == sum(
        remissao_in(LINKED_GOLDENS, path.stem) for path in SAMPLES
    )
