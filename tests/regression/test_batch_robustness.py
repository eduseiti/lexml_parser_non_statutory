"""Batch robustness and the negative cases — Cycle 5 of the corpus-233 plan.

Plan §1.6's finding is that ``parse`` used to abandon its whole batch on any
failure, that the guard repairing it was added during the measuring run, and
that **the corpus never triggered it**: 0 of 233 documents raised. A guard no
real data exercises is a guard nobody has seen work, and §1.6 says so plainly
rather than treating the zero as reassurance. This module supplies the negative
cases the corpus could not.

**What is new here, and what is not.** The fixtures are *not* new: predecessor
Cycle 8 built ``tests/fixtures/degenerate.py`` — ten degenerate DOCX shapes and
three malformed files graded by how far into the read they fail — and
``tests/unit/test_robustness.py`` already pins that each is refused cleanly, one
document at a time. What has never been asserted anywhere is the **batch
arithmetic**: that a run of N good and 5 bad documents writes *exactly N files*.

That distinction is the whole point of the module. §1.5's defect wrote **229
files for 233 sources** while reporting success for every one of the 233 — the
loss was invisible in stdout and visible only by counting the directory. The
nearest existing test (`test_one_bad_file_does_not_abandon_the_good_ones`) runs
three documents with ``--format=json`` and no ``-o`` at all, counting ``"urn"``
occurrences in stdout. It would not have caught that defect, because stdout was
never the thing that was wrong. **Here the assertion is the file count**, which
is the thing that was.

**On the plan's "200".** The plan words the deliverable as "a batch of 200 with
5 bad documents writes 195 files". The property is scale-independent — 195 of
200 and 20 of 25 exercise the same guard — and 200 real DOCX files per run buys
nothing but wall time against an 81-second suite. Recorded as amendment
**A-5.1**; the shape is the plan's, the cardinality is not.

**On resumability.** The plan asks for "a documented resumability story:
re-running over a directory that already holds output should be safe and cheap".
Measured, exactly half of that is true today, and this module asserts both
halves rather than the flattering one: a re-run **is** safe (byte-identical
output, stable file count, no accumulating disambiguation suffixes) and is **not
cheap** (every document is re-rendered; nothing is skipped). See
``docs/20260914_115058_batch_resumability.md``.
"""

from __future__ import annotations

import hashlib
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat import cli
from lexml_nonstat.corpus import run_corpus
from lexml_nonstat.validate import validate

from tests.fixtures.degenerate import (
    DEGENERATE_CASES,
    build_all,
    corrupt_docx,
    truncated_docx,
    zip_that_is_not_a_docx,
)

#: How many good documents the mixed batch carries. The ten degenerate cases,
#: twice, under distinct names — so every document has an output file of its
#: own and the count below is a real per-document tally rather than a tally of
#: distinct URNs.
GOOD = 2 * len(DEGENERATE_CASES)

#: How many bad ones. The plan's number, and deliberately more than one: every
#: isolation test that existed before this module used exactly one bad
#: document, which cannot distinguish "the guard recovers" from "the guard
#: recovers once".
BAD = 5


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI in-process — ``test_corpus_report.py``'s helper, verbatim."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _written(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.glob("*.xml"))


def _digests(directory: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.glob("*.xml"))
    }


# ---------------------------------------------------------------------------
# the mixed batch
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def good_documents(tmp_path_factory) -> list[Path]:
    """Twenty readable documents: the ten degenerate cases, twice.

    Two copies under different stems rather than twenty distinct shapes,
    because the question here is batch arithmetic and not document variety —
    the variety is `test_robustness.py`'s subject, and duplicating its coverage
    would be a second source of truth for it.

    The copies matter for a second reason: two documents built from the same
    source resolve to the **same URN**, so the batch exercises
    ``_write_bundle``'s disambiguation at scale as a side effect. Twenty
    documents, twenty files, ten of them disambiguated.
    """
    directory = tmp_path_factory.mktemp("batch_good")
    built = build_all(directory)

    documents: list[Path] = []
    for copy in ("a", "b"):
        for name, source in built.items():
            path = directory / f"{copy}_{name}.docx"
            path.write_bytes(source.read_bytes())
            documents.append(path)
    return documents


@pytest.fixture(scope="module")
def bad_documents(tmp_path_factory) -> list[Path]:
    """Five unreadable files, spanning every failure layer the fixtures reach.

    Not five copies of one shape. ``corrupt`` fails at the outermost layer (not
    a ZIP), ``truncated`` one layer in (valid ZIP, no central directory),
    ``not_a_docx`` at the innermost (valid OPC package, no
    ``word/document.xml``), and the zero-byte file fails before any of them.
    The fifth sorts first in the batch, so a run that halted at the first
    failure would be distinguishable from one that isolated it.
    """
    directory = tmp_path_factory.mktemp("batch_bad")

    first = directory / "AAA_sorts_first.docx"
    first.write_bytes(b"this is not a DOCX package")

    empty = directory / "zero_bytes.docx"
    empty.write_bytes(b"")

    return [
        first,
        corrupt_docx(directory),
        truncated_docx(directory),
        zip_that_is_not_a_docx(directory),
        empty,
    ]


@pytest.fixture(scope="module")
def mixed_batch(good_documents, bad_documents) -> list[str]:
    """Every source path, good and bad, as the CLI would receive them."""
    return [str(p) for p in (*good_documents, *bad_documents)]


def test_the_batch_fixture_is_what_it_claims(
    good_documents, bad_documents
) -> None:
    """A fixture nobody checks is a fixture that can quietly stop testing.

    The arithmetic below is only meaningful if these two numbers are what the
    module says they are, so they are asserted rather than trusted — and the
    names are asserted distinct, because two sources with one name would write
    one file and make the central count wrong for a reason unrelated to the
    guard.
    """
    assert len(good_documents) == GOOD == 20
    assert len(bad_documents) == BAD == 5

    names = [p.name for p in (*good_documents, *bad_documents)]
    assert len(set(names)) == len(names), "two sources share a name"


# ---------------------------------------------------------------------------
# G-1 — the plan's headline assertion
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mixed_run(tmp_path_factory, mixed_batch) -> tuple[int, str, str, Path]:
    """One ``parse -o`` over the mixed batch, shared by the assertions below.

    Module-scoped because it is the expensive thing here — 20 documents through
    the whole pipeline — and every assertion in this section reads a different
    facet of the *same* run. Splitting it per test would multiply the cost by
    six and assert nothing extra.
    """
    out_dir = tmp_path_factory.mktemp("batch_out")
    code, out, err = _run(["parse", "--quiet", "-o", str(out_dir), *mixed_batch])
    return code, out, err, out_dir


def test_a_mixed_batch_writes_one_file_per_good_document(mixed_run) -> None:
    """**The assertion this module exists for.**

    §1.5's defect wrote 229 files for 233 sources and reported success for all
    233; the loss was invisible except by counting. So the count is the
    assertion, and it is exact: `>= 20` would pass a run that wrote 20 files for
    25 documents by overwriting five, which is the defect itself.
    """
    _, _, err, out_dir = mixed_run

    assert len(_written(out_dir)) == GOOD, (
        f"expected exactly {GOOD} files for {GOOD} good documents, got "
        f"{len(_written(out_dir))} — a short directory means a document was "
        f"silently overwritten or silently dropped\n{err}"
    )


def test_a_mixed_batch_reports_every_failure(mixed_run, bad_documents) -> None:
    """Five failures, each naming its own source.

    At 233 documents "5 failed" is only actionable if each says *which*, so the
    per-document name is asserted rather than the count of error lines — a run
    that printed one error five times would satisfy a count.
    """
    _, _, err, _ = mixed_run

    for path in bad_documents:
        assert path.name in err, f"{path.name} failed without being named"


def test_a_mixed_batch_exits_one(mixed_run) -> None:
    """The failure is isolated, not forgiven — §1.6's exit code."""
    code, _, _, _ = mixed_run
    assert code == 1


def test_a_mixed_batch_prints_no_traceback(mixed_run) -> None:
    """Cycle 5's exit criterion: no traceback reaches the user, at any scale."""
    _, _, err, _ = mixed_run
    assert "Traceback" not in err


def test_every_written_file_is_wellformed_xml(mixed_run) -> None:
    """A survivor must be whole. A half-written file is worse than a missing one.

    The failure mode this guards is a document interrupted mid-write by its
    neighbour's exception: the file exists, the count reconciles, and the
    content is truncated — a loss that every count-based assertion above would
    wave through.
    """
    _, _, _, out_dir = mixed_run

    for path in sorted(out_dir.glob("*.xml")):
        assert etree.parse(str(path)) is not None, f"{path.name} is not well-formed"


def test_every_written_file_validates(mixed_run) -> None:
    """Invariant #1 at batch scale: a batch's survivors are publishable output.

    Degenerate input is still valid output — that is predecessor Cycle 8's
    exit criterion — and a neighbouring failure must not weaken it.
    """
    _, _, _, out_dir = mixed_run

    for path in sorted(out_dir.glob("*.xml")):
        report = validate(etree.parse(str(path)).getroot(), "both")
        assert report.ok, f"{path.name}: {report.summary()}"


# ---------------------------------------------------------------------------
# G-2 — position must not matter
# ---------------------------------------------------------------------------


def test_a_bad_document_first_does_not_block_the_rest(
    tmp_path, good_documents, bad_documents
) -> None:
    """The §1.6 shape exactly: the first document raises, the rest must land.

    This is the ordering the old code failed on — one raise took every later
    document with it.
    """
    out_dir = tmp_path / "out"
    argv = [str(bad_documents[0]), *(str(p) for p in good_documents)]

    code, _, err = _run(["parse", "--quiet", "-o", str(out_dir), *argv])

    assert code == 1
    assert len(_written(out_dir)) == GOOD, (
        "a failure in first position cost the documents after it"
    )
    assert "Traceback" not in err


def test_a_bad_document_last_does_not_undo_the_rest(
    tmp_path, good_documents, bad_documents
) -> None:
    """The converse ordering, which fails differently.

    A guard that recovered by discarding accumulated state would pass the
    first-position test and lose everything here.
    """
    out_dir = tmp_path / "out"
    argv = [*(str(p) for p in good_documents), str(bad_documents[0])]

    code, _, err = _run(["parse", "--quiet", "-o", str(out_dir), *argv])

    assert code == 1
    assert len(_written(out_dir)) == GOOD, (
        "a failure in last position retroactively cost the documents before it"
    )
    assert "Traceback" not in err


def test_a_failure_after_read_is_isolated_at_batch_scale(
    tmp_path, monkeypatch, good_documents
) -> None:
    """§1.6's *actual* gap: `_read` was always isolated; everything after it was not.

    Every bad document above fails inside ``_read``. That path was guarded even
    before the measuring run's fix, so on its own it cannot tell the repaired
    code from the broken code. The defect §1.6 names lived in model building,
    rendering and validation — which no malformed *file* can reach, because a
    malformed file never gets that far.

    So the failure is injected where it actually was, by making ``_render``
    raise on one document in the middle of the batch. `test_cli.py` does this
    for two documents; here it is done at batch scale **and the written count is
    asserted**, because a removed guard changes how many files land and an
    exit-code-only assertion would not notice.
    """
    from lexml_nonstat import cli as cli_module

    real_render = cli_module._render
    seen: list[str] = []
    target = good_documents[len(good_documents) // 2].name

    def explode(model, emitter, linker=None):
        seen.append(model.source or "")
        if (model.source or "").endswith(target):
            raise RuntimeError("boom")
        return real_render(model, emitter, linker=linker)

    monkeypatch.setattr(cli_module, "_render", explode)

    out_dir = tmp_path / "out"
    code, _, err = _run(
        ["parse", "--quiet", "-o", str(out_dir), *(str(p) for p in good_documents)]
    )

    assert code == 1, "a failed document must make the run fail"
    assert len(seen) == GOOD, (
        "the run stopped early: every document must still be attempted"
    )
    assert len(_written(out_dir)) == GOOD - 1, (
        "isolation is what lets the other documents land; the count says "
        "whether they did"
    )
    assert "Traceback" not in err


def test_a_failure_after_read_names_the_document(
    tmp_path, monkeypatch, good_documents
) -> None:
    """An isolated failure must say which document it was, and why."""
    from lexml_nonstat import cli as cli_module

    real_render = cli_module._render
    target = good_documents[0].name

    def explode(model, emitter, linker=None):
        if (model.source or "").endswith(target):
            raise RuntimeError("boom")
        return real_render(model, emitter, linker=linker)

    monkeypatch.setattr(cli_module, "_render", explode)

    out_dir = tmp_path / "out"
    _, _, err = _run(
        ["parse", "--quiet", "-o", str(out_dir), *(str(p) for p in good_documents)]
    )

    assert "RuntimeError: boom" in err
    assert target in err


# ---------------------------------------------------------------------------
# the two degenerate batches
# ---------------------------------------------------------------------------


def test_an_all_bad_batch_writes_nothing_and_exits_one(
    tmp_path, bad_documents
) -> None:
    """Nothing succeeded, and the run still ends cleanly.

    The mirror of `test_an_all_bad_corpus_still_reconciles`: a batch tool is
    most likely to be believed when it is least likely to be checked.
    """
    out_dir = tmp_path / "out"
    code, _, err = _run(
        ["parse", "--quiet", "-o", str(out_dir), *(str(p) for p in bad_documents)]
    )

    assert code == 1
    # Written as two statements rather than one conditional expression: the
    # obvious `assert _written(...) == [] if out_dir.exists() else True` parses
    # as `assert (x == [] if cond else True)` and passes vacuously whenever the
    # directory is absent — which is the common case here, since nothing
    # succeeded and `-o` is created lazily. A test that cannot fail is the risk
    # this cycle's own spec §7 names.
    assert not out_dir.exists() or _written(out_dir) == [], (
        "a batch in which every document failed still wrote a file"
    )
    assert "Traceback" not in err


def test_an_all_good_batch_exits_zero(tmp_path, good_documents) -> None:
    """The converse, and it is load-bearing.

    Without it every assertion above could be satisfied by a ``parse`` that
    always exits 1 and always writes 20 files. This is the test that makes
    exit 1 mean "something failed" rather than "this command exits 1".
    """
    out_dir = tmp_path / "out"
    code, _, err = _run(
        ["parse", "--quiet", "-o", str(out_dir), *(str(p) for p in good_documents)]
    )

    assert code == 0, err
    assert len(_written(out_dir)) == GOOD


# ---------------------------------------------------------------------------
# G-3 — the same arithmetic for `corpus`
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mixed_directory(tmp_path_factory, good_documents, bad_documents) -> Path:
    """The mixed batch as a *directory*, which is what ``corpus`` walks.

    Symlinked rather than copied, following `test_corpus_report.py`'s fixture:
    the documents already exist and copying 25 files per module is pure cost.
    """
    directory = tmp_path_factory.mktemp("mixed_corpus") / "corpus"
    directory.mkdir()
    for path in (*good_documents, *bad_documents):
        (directory / path.name).symlink_to(path)
    return directory


def test_corpus_reports_the_same_arithmetic(mixed_directory) -> None:
    """`corpus` and `parse` must agree about how many documents worked.

    Two commands over one directory disagreeing about the failure count would
    mean one of them is wrong and nothing says which.
    """
    report = run_corpus([mixed_directory], validate_output=False)

    assert report.total == GOOD + BAD
    assert report.succeeded == GOOD
    assert report.failed == BAD
    assert report.check() is None, report.check()


def test_corpus_failures_each_carry_an_error_and_no_route(mixed_directory) -> None:
    """Five failures, five explanations — `check()`'s identity 5, at multiplicity.

    Every isolation test before this module used exactly one bad document, so
    "each failure carries its own error" had never been distinguished from "a
    failure carries an error".
    """
    report = run_corpus([mixed_directory], validate_output=False)
    failures = [o for o in report.outcomes if not o.ok]

    assert len(failures) == BAD
    for outcome in failures:
        assert outcome.error, f"{outcome.source}: a failure must say what happened"
        assert outcome.route == "", f"{outcome.source}: a failure cannot claim a route"
    assert len({o.source for o in failures}) == BAD


def test_corpus_cli_on_a_mixed_directory(mixed_directory) -> None:
    """The same through the command the user actually runs."""
    code, out, err = _run(["corpus", "--no-validate", str(mixed_directory)])

    assert code == 1, err
    assert "Traceback" not in err
    assert f"failed:              {BAD}" in out


# ---------------------------------------------------------------------------
# G-4 — resumability, both halves
# ---------------------------------------------------------------------------


def test_rerunning_a_batch_is_byte_identical(tmp_path, good_documents) -> None:
    """"Safe" — the half of the plan's claim that is true.

    Invariant #4 says same input ⇒ byte-identical output; this asserts the
    property survives the output directory already being populated, which is
    the case the plan asks about and which nothing else in the suite covers.
    """
    out_dir = tmp_path / "out"
    argv = ["parse", "--quiet", "-o", str(out_dir), *(str(p) for p in good_documents)]

    code_one, _, _ = _run(argv)
    first = _digests(out_dir)
    code_two, _, _ = _run(argv)
    second = _digests(out_dir)

    assert code_one == code_two == 0
    assert first == second, "a re-run changed the bytes of an already-written file"


def test_rerunning_a_batch_does_not_change_the_file_count(
    tmp_path, good_documents
) -> None:
    """A re-run must not *add* files either.

    The failure mode is disambiguation misreading an existing file as a
    collision and writing `…_b.xml` beside it, so the directory grows on every
    run. `taken` is per-invocation and seeded empty, so it does not — asserted
    rather than reasoned, because the reasoning is exactly what a future change
    would invalidate.
    """
    out_dir = tmp_path / "out"
    argv = ["parse", "--quiet", "-o", str(out_dir), *(str(p) for p in good_documents)]

    _run(argv)
    first = _written(out_dir)
    _run(argv)
    second = _written(out_dir)

    assert first == second == sorted(first)
    assert len(second) == GOOD


def test_rerunning_colliding_urns_does_not_grow_suffixes(tmp_path) -> None:
    """Three runs of two documents sharing one URN: always the same two names.

    The sharp case for the test above. These two sources resolve to one URN, so
    the second is written under a disambiguated name; if a re-run treated that
    disambiguated file as itself a collision the names would grow `_b`, `_b_b`,
    `_b_b_b` across runs.
    """
    sample = sorted((Path(__file__).resolve().parents[2] / "samples").glob("*.docx"))[0]
    first, second = tmp_path / "a.docx", tmp_path / "b.docx"
    first.write_bytes(sample.read_bytes())
    second.write_bytes(sample.read_bytes())
    out_dir = tmp_path / "out"

    argv = ["parse", "--quiet", "-o", str(out_dir), str(first), str(second)]
    runs = []
    for _ in range(3):
        _run(argv)
        runs.append(_written(out_dir))

    assert runs[0] == runs[1] == runs[2]
    assert len(runs[0]) == 2, f"suffixes accumulated across runs: {runs}"


def test_a_rerun_re_renders_rather_than_skipping(
    tmp_path, monkeypatch, good_documents
) -> None:
    """"Cheap" — the half of the plan's claim that is **false**, asserted as false.

    Nothing skips work when the output already exists: a second run renders
    every document again. This is deliberately pinned rather than left
    unstated, because "safe and cheap" reads as a delivered property and only
    one half of it was delivered. If a later cycle implements skip-on-existing,
    this test is the one that must change, and changing it is the signal that
    the contract moved.
    """
    from lexml_nonstat import cli as cli_module

    real_render = cli_module._render
    renders: list[str] = []

    def counting(model, emitter, linker=None):
        renders.append(model.source or "")
        return real_render(model, emitter, linker=linker)

    monkeypatch.setattr(cli_module, "_render", counting)

    out_dir = tmp_path / "out"
    argv = ["parse", "--quiet", "-o", str(out_dir), *(str(p) for p in good_documents)]

    _run(argv)
    after_first = len(renders)
    _run(argv)
    after_second = len(renders)

    assert after_first == GOOD
    assert after_second == 2 * GOOD, (
        "a re-run skipped work — the resumability contract changed and "
        "docs/20260914_115058_batch_resumability.md is now stale"
    )


# ---------------------------------------------------------------------------
# G-5 — nothing, at batch scale, prints a traceback
# ---------------------------------------------------------------------------


def test_no_batch_invocation_prints_a_traceback(
    tmp_path, good_documents, bad_documents
) -> None:
    """Cycle 5's exit criterion as one assertion over every bad input at once.

    `test_robustness.py` makes this claim for the single-document inspection
    commands; this makes it for the two commands that process a *batch*, which
    are the ones §1.6 is about.
    """
    mixed = [str(bad_documents[0]), str(good_documents[0]), str(bad_documents[1])]

    _, _, err = _run(["parse", "--quiet", "-o", str(tmp_path / "a"), *mixed])
    assert "Traceback" not in err

    _, _, err = _run(["parse", "--quiet", "-o", str(tmp_path / "b"),
                      *(str(p) for p in bad_documents)])
    assert "Traceback" not in err

    for path in bad_documents:
        _, _, err = _run(["corpus", "--no-validate", str(path)])
        assert "Traceback" not in err, path.name
