"""The corpus data model and the walk — Cycle 9, amendment **A-9.3**.

``corpus`` exists because 15 samples stand in for **300+** unseen documents
(plan §10's top risk), and the instrument that risk asks for is a run whose
numbers can be shown to agree with each other. This module tests the two
halves that make that possible *without* touching the real corpus: the walk
that decides which files are in a run, and :meth:`CorpusReport.check`, the
reconciliation.

**Why the negative cases carry the weight here.** Over ``samples/`` ``check()``
returns ``None``, and it would keep returning ``None`` if its body were
``return None``. A reconciliation that has only ever been observed to pass is
not evidence of anything, so every identity is also broken deliberately below,
against a *synthetic* report, and the failure is required to **name** the
problem — the same discipline
``test_telemetry.py::test_check_detects_a_broken_identity`` applies to §7.4's
counts, and for the same reason: at 300 documents nobody re-derives the
arithmetic by hand, so the message has to do it for them.

Nothing here reads a `.docx`. The walk is exercised on ``tmp_path`` fixtures and
the report on hand-built outcomes, which keeps this module fast and leaves the
corpus-scale assertions to ``tests/regression/test_corpus_report.py``.
"""

from __future__ import annotations

import json

import pytest

from lexml_nonstat.corpus import (
    SUPPORTED_SUFFIXES,
    CorpusReport,
    DocumentOutcome,
    walk_corpus,
)
from lexml_nonstat.ingest import READERS
from lexml_nonstat.routing.viability import BLOCKER_CODES, EMITTERS
from lexml_nonstat.telemetry import DecisionsReport
from lexml_nonstat.warnings import WARNING_CODES

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"


def ok_outcome(source: str, **kwargs) -> DocumentOutcome:
    """A minimally *consistent* successful outcome.

    ``check()`` requires a successful document to carry a route and no error,
    so the helper supplies both defaults. Every test below that wants an
    inconsistent report has to say so explicitly, which is what keeps an
    accidental typo from silently becoming the negative case a test claims to
    be making deliberately.
    """
    kwargs.setdefault("route", "generico")
    return DocumentOutcome(source=source, ok=True, **kwargs)


def failed_outcome(source: str, **kwargs) -> DocumentOutcome:
    kwargs.setdefault("error", "DocxReadError: cannot read it")
    return DocumentOutcome(source=source, ok=False, **kwargs)


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------


def test_supported_suffixes_are_read_from_the_reader_table() -> None:
    """The walk's vocabulary is :data:`~.ingest.READERS`, not a second copy.

    ``ingest`` is "the single place formats are declared". A hand-maintained
    list here would drift the moment a fifth reader landed, and the drift would
    surface as a corpus that simply appears to hold no files of that kind —
    silent, and indistinguishable from a correct empty result.
    """
    assert SUPPORTED_SUFFIXES == tuple(sorted(READERS))
    assert set(SUPPORTED_SUFFIXES) == {".docx", ".htm", ".html", ".txt"}


def test_walk_finds_every_supported_suffix(tmp_path) -> None:
    """All four readers' formats, and nothing else.

    The `.pdf` is the load-bearing half: a walk that collected everything would
    hand ``read_document`` a file it cannot read, turning a file the corpus
    never claimed to support into a *failed document* in the report — noise
    that at 300 documents reads as a parser regression.
    """
    for name in ("a.docx", "b.html", "c.htm", "d.txt", "e.pdf", "f.doc", "notes.md"):
        (tmp_path / name).write_bytes(b"x")

    found = walk_corpus([tmp_path])

    assert [p.name for p in found] == ["a.docx", "b.html", "c.htm", "d.txt"]


def test_walk_recurses_into_subdirectories(tmp_path) -> None:
    """A 300-document corpus is a tree, not a flat directory."""
    nested = tmp_path / "2024" / "pareceres"
    nested.mkdir(parents=True)
    (nested / "deep.docx").write_bytes(b"x")
    (tmp_path / "shallow.docx").write_bytes(b"x")

    # Sorted by full path, so the nested document precedes the shallow one —
    # `2024/pareceres/deep.docx` < `shallow.docx`. Depth does not order the
    # walk; the path string does, which is what makes it reproducible.
    assert [p.name for p in walk_corpus([tmp_path])] == ["deep.docx", "shallow.docx"]


def test_walk_is_deterministic(tmp_path) -> None:
    """Invariant #4. A report whose document order moved could not be diffed.

    Filesystem order is not sorted order, and on some filesystems it is not even
    stable between two listings of the same directory — so the sort is the only
    thing making two runs comparable.
    """
    for name in ("z.docx", "a.docx", "m.txt", "b.html"):
        (tmp_path / name).write_bytes(b"x")

    assert walk_corpus([tmp_path]) == walk_corpus([tmp_path])
    assert list(walk_corpus([tmp_path])) == sorted(walk_corpus([tmp_path]))


def test_walk_accepts_files_and_directories(tmp_path) -> None:
    """Mixed arguments are the union — and a named file is taken as given.

    A caller who names a file meant *that* file. Refusing it because the walk
    would not have collected it (here, a `.pdf`) would be a surprise rather
    than a safeguard, and the module's docstring commits to this explicitly.
    """
    directory = tmp_path / "corpus"
    directory.mkdir()
    (directory / "in_dir.docx").write_bytes(b"x")
    loose = tmp_path / "loose.txt"
    loose.write_bytes(b"x")
    odd = tmp_path / "named.pdf"
    odd.write_bytes(b"x")

    found = walk_corpus([directory, loose, odd])

    assert [p.name for p in found] == ["in_dir.docx", "loose.txt", "named.pdf"]


def test_walk_deduplicates_overlapping_paths(tmp_path) -> None:
    """A directory and a file inside it must not process that file twice.

    Double-counting is the failure mode that makes a corpus report *wrong while
    reconciling*: every identity still closes, because the duplicate is a
    genuine extra outcome — the totals are simply not the corpus. The
    de-duplication is by resolved path, so an equivalent spelling collapses too.
    """
    (tmp_path / "one.docx").write_bytes(b"x")
    (tmp_path / "two.docx").write_bytes(b"x")

    found = walk_corpus([tmp_path, tmp_path / "one.docx", tmp_path / "." / "two.docx"])

    assert [p.name for p in found] == ["one.docx", "two.docx"]
    assert len({p.resolve() for p in found}) == len(found)


def test_walk_respects_limit() -> None:
    """`--limit=N` takes the first N *in sort order*, so it is reproducible.

    Pinned against the real corpus rather than a fixture: a limit that sliced
    before sorting would still return three documents, and only a comparison
    with the full walk's prefix can tell the two apart.
    """
    every = walk_corpus([SAMPLES_DIR])
    assert len(every) == 15

    assert walk_corpus([SAMPLES_DIR], limit=3) == every[:3]
    assert walk_corpus([SAMPLES_DIR], limit=0) == ()
    assert walk_corpus([SAMPLES_DIR], limit=99) == every


def test_empty_directory_is_not_an_error(tmp_path) -> None:
    """An empty corpus is a fact, not a failure.

    ``run_corpus`` over nothing must produce an empty report that still
    reconciles — the degenerate case a batch tool meets on its first run against
    a directory somebody has not populated yet.
    """
    empty = tmp_path / "empty"
    empty.mkdir()

    assert walk_corpus([empty]) == ()
    assert walk_corpus([]) == ()
    assert CorpusReport().check() is None


def test_walk_ignores_directories_that_look_like_documents(tmp_path) -> None:
    """`Bundle.docx/` is a directory, and directories are not documents."""
    (tmp_path / "bundle.docx").mkdir()
    (tmp_path / "real.docx").write_bytes(b"x")

    assert [p.name for p in walk_corpus([tmp_path])] == ["real.docx"]


# ---------------------------------------------------------------------------
# the report's arithmetic
# ---------------------------------------------------------------------------


def test_counts_sum_to_total() -> None:
    report = CorpusReport(
        outcomes=(
            ok_outcome("a.docx"),
            ok_outcome("b.docx"),
            failed_outcome("c.docx"),
        )
    )

    assert (report.total, report.succeeded, report.failed) == (3, 2, 1)
    assert report.succeeded + report.failed == report.total
    assert report.check() is None


def test_validated_and_invalid_distinguish_unrun_validation() -> None:
    """``valid`` is tri-state on purpose, and the properties must honour it.

    ``None`` means validation was not run, which is a different fact from
    ``False``. Collapsing them would make "0 invalid" mean either "everything
    passed" or "nothing was checked" — at corpus scale the difference decides
    whether the number is reassuring or meaningless.
    """
    report = CorpusReport(
        outcomes=(
            ok_outcome("a.docx", valid=True),
            ok_outcome("b.docx", valid=False),
            ok_outcome("c.docx", valid=None),
        )
    )

    assert report.validated == 2, "the unvalidated document is not counted"
    assert report.invalid == 1


def test_references_sum_across_the_corpus() -> None:
    report = CorpusReport(
        outcomes=(
            ok_outcome("a.docx", references=3),
            ok_outcome("b.docx", references=0),
            ok_outcome("c.docx", references=7),
        )
    )
    assert report.references == 10


def test_tallies_ignore_failed_documents() -> None:
    """A document that failed has no route, profile or emitter to tally.

    Counting it would break identity 3 (``route tallies == succeeded``), which
    is precisely the identity that notices a document processed without being
    routed.
    """
    report = CorpusReport(
        outcomes=(ok_outcome("a.docx", profile="parecer"), failed_outcome("b.docx"))
    )

    assert report.by_route() == (("generico", 1),)
    assert report.by_profile() == (("parecer", 1),)
    assert sum(n for _, n in report.by_route()) == report.succeeded
    assert report.check() is None


def test_tallies_are_count_descending_then_name() -> None:
    """:func:`~.telemetry.report.ranked`'s order, so the report is diffable.

    A ``Counter`` is not ordered, and invariant #4 makes determinism a property
    of anything a diff might touch. Ties break by name: two routes with one
    document each must always print in the same order.
    """
    report = CorpusReport(
        outcomes=(
            ok_outcome("a.docx", route="generico", blockers=("no_articles",)),
            ok_outcome("b.docx", route="generico", blockers=("no_articles",)),
            ok_outcome("c.docx", route="norma", blockers=("top_level_table",)),
            ok_outcome("d.docx", route="generico-aninhado", blockers=()),
        )
    )

    assert report.by_route() == (
        ("generico", 2),
        ("generico-aninhado", 1),  # tie with `norma`, broken by name
        ("norma", 1),
    )
    assert report.by_blocker() == (("no_articles", 2), ("top_level_table", 1))


def test_blockers_and_warnings_are_counted_per_occurrence() -> None:
    """One document may carry several codes, and each is its own tally entry."""
    report = CorpusReport(
        outcomes=(
            ok_outcome(
                "a.docx",
                blockers=("no_articles", "top_level_table"),
                warnings=("flat_fallback",),
            ),
            ok_outcome("b.docx", blockers=("no_articles",), warnings=("flat_fallback",)),
        )
    )

    assert report.by_blocker() == (("no_articles", 2), ("top_level_table", 1))
    assert report.by_warning() == (("flat_fallback", 2),)


# ---------------------------------------------------------------------------
# `check()` — the negative cases
# ---------------------------------------------------------------------------
#
# Every identity in the module docstring's list, broken on purpose. A `check()`
# observed only on data where it returns `None` is untested, and these are the
# assertions that make the reconciliation mean something.


def test_unknown_route_fails_check() -> None:
    """Identity 2: every route must be a §4.4 emitter.

    A route the renderers do not implement is how a typo in a routing branch
    would reach a report — tallied, printed, and believed.
    """
    report = CorpusReport(outcomes=(ok_outcome("a.docx", route="generic"),))

    problem = report.check()
    assert problem is not None
    assert "unknown route" in problem and "'generic'" in problem
    assert all(e in problem for e in EMITTERS), "the message should list the valid ones"


def test_unknown_blocker_code_fails_check() -> None:
    """Identity 2, for §4's closed blocker vocabulary."""
    report = CorpusReport(
        outcomes=(ok_outcome("a.docx", blockers=("no_such_blocker",)),)
    )

    problem = report.check()
    assert problem is not None
    assert "unknown blocker code" in problem and "'no_such_blocker'" in problem


def test_unknown_warning_code_fails_check() -> None:
    """Identity 2, for the warning vocabulary ``warnings.py`` declares."""
    report = CorpusReport(
        outcomes=(ok_outcome("a.docx", warnings=("no_such_warning",)),)
    )

    problem = report.check()
    assert problem is not None
    assert "unknown warning code" in problem and "'no_such_warning'" in problem


def test_every_declared_code_is_accepted() -> None:
    """The converse: the vocabularies are the *whole* vocabularies.

    Without this, `check()` could pass every test above by rejecting all but a
    couple of hard-coded codes, and a legitimate blocker would start failing a
    corpus run the first time a document raised it.
    """
    report = CorpusReport(
        outcomes=(ok_outcome("a.docx", blockers=BLOCKER_CODES, warnings=WARNING_CODES),)
    )
    assert report.check() is None

    for route in EMITTERS:
        assert CorpusReport(outcomes=(ok_outcome("a.docx", route=route),)).check() is None


def test_failed_document_with_no_error_fails_check() -> None:
    """Identity 5. A failure nobody can explain is the untrustworthy outcome.

    At 300 documents "12 failed" is only actionable if each one says what
    happened; a blank error would leave the reader to re-run the corpus by hand
    to find out.
    """
    report = CorpusReport(
        outcomes=(DocumentOutcome(source="bad.docx", ok=False, error=""),)
    )

    problem = report.check()
    assert problem is not None
    assert "bad.docx" in problem and "failed with no error recorded" in problem


def test_failed_document_carrying_a_route_fails_check() -> None:
    """Identity 5's other half: a failure that was never routed cannot claim one."""
    report = CorpusReport(
        outcomes=(failed_outcome("bad.docx", route="generico"),)
    )

    problem = report.check()
    assert problem is not None
    assert "bad.docx" in problem and "failed but carries route" in problem


def test_succeeded_document_with_no_route_fails_check() -> None:
    """A processed document is always routed — identity 2 catches the empty one.

    An empty route is still *tallied* as a route, so it reaches the vocabulary
    check before identity 5's per-outcome pass and is reported as an unknown
    route. That is the right diagnosis rather than a near-miss: ``''`` is not a
    §4.4 emitter, and the message says so and lists the three that are.
    """
    report = CorpusReport(
        outcomes=(DocumentOutcome(source="a.docx", ok=True, route=""),)
    )

    problem = report.check()
    assert problem is not None
    assert "unknown route" in problem and "''" in problem


def test_succeeded_document_carrying_an_error_fails_check() -> None:
    """A document cannot both have worked and have failed."""
    report = CorpusReport(
        outcomes=(ok_outcome("a.docx", error="ValueError: something"),)
    )

    problem = report.check()
    assert problem is not None
    assert "a.docx" in problem and "succeeded but carries an error" in problem


def test_a_broken_decisions_report_fails_the_corpus_check() -> None:
    """Identity 4: §7.4's identities are inherited, not re-implemented (N-3).

    The embedded :class:`~.telemetry.DecisionsReport` already checks amendment
    **A-4b.4**'s two identities. This asserts the corpus report *defers* to it
    rather than carrying a second copy of the arithmetic — a second copy being
    exactly the second source of truth N-3 exists to prevent.
    """
    broken = DecisionsReport(total=47, rule_only=40, flagged=4, consulted=0)
    assert broken.check() is not None, "precondition: this report is inconsistent"

    report = CorpusReport(outcomes=(ok_outcome("a.docx"),), decisions=broken)

    problem = report.check()
    assert problem == broken.check()
    assert "rule_only + flagged != total" in problem


def test_check_reports_the_first_problem_only() -> None:
    """One diagnosis at a time, like ``DecisionsReport.check``.

    The contract is "the first failing identity or ``None``" — a caller printing
    the string needs it to name one actionable thing, not concatenate every
    consequence of a single upstream error.
    """
    report = CorpusReport(
        outcomes=(
            ok_outcome("a.docx", route="nonsense", blockers=("no_such_blocker",)),
        )
    )

    problem = report.check()
    assert problem is not None
    assert "unknown route" in problem
    assert "no_such_blocker" not in problem


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------


def test_outcome_to_dict_keeps_every_field() -> None:
    """The JSON format is a pinned surface: a dropped field is a silent loss."""
    outcome = DocumentOutcome(
        source="samples/a.docx",
        ok=True,
        urn="urn:lex:br:federal:parecer:2000-06-29;26",
        profile="parecer",
        route="generico",
        emitter="generico",
        confidence=0.42,
        flat=True,
        documents=2,
        valid=True,
        blockers=("no_articles",),
        warnings=("flat_fallback",),
        references=7,
    )

    assert outcome.to_dict() == {
        "source": "samples/a.docx",
        "ok": True,
        "urn": "urn:lex:br:federal:parecer:2000-06-29;26",
        "profile": "parecer",
        "route": "generico",
        "emitter": "generico",
        "confidence": 0.42,
        "flat": True,
        "documents": 2,
        "valid": True,
        "blockers": ["no_articles"],
        "warnings": ["flat_fallback"],
        "references": 7,
        "error": "",
    }


def test_to_dict_round_trips_through_json() -> None:
    """`--format=json` must survive a real serialisation, not just `dict()`.

    Round-tripping through the *text* is deliberate: it catches a value that
    looks fine in a dict but does not survive JSON — a tuple, a `Path`, a
    dataclass — which is the same trap
    ``test_telemetry.py::test_log_json_round_trips`` guards §7.4 against.
    """
    report = CorpusReport(
        outcomes=(
            ok_outcome("a.docx", valid=True, blockers=("no_articles",), references=2),
            failed_outcome("b.docx"),
        )
    )

    restored = json.loads(json.dumps(report.to_dict(), ensure_ascii=False))

    assert restored["total"] == 2 and restored["succeeded"] == 1
    assert restored["failed"] == 1 and restored["references"] == 2
    assert restored["by_route"] == [["generico", 1]]
    assert restored["by_blocker"] == [["no_articles", 1]]
    assert [d["source"] for d in restored["documents"]] == ["a.docx", "b.docx"]
    assert restored["decisions"] == report.decisions.to_dict()


def test_to_dict_keys_are_stable() -> None:
    """The JSON shape is what a downstream corpus dashboard would bind to."""
    assert set(CorpusReport().to_dict()) == {
        "total",
        "succeeded",
        "failed",
        "validated",
        "invalid",
        "references",
        "by_route",
        "by_profile",
        "by_emitter",
        "by_blocker",
        "by_warning",
        "decisions",
        "documents",
    }


def test_outcomes_are_immutable() -> None:
    """Frozen, like every other report dataclass in the package.

    A tally computed from mutable outcomes could disagree with the outcomes a
    caller later inspects — a report that reconciles at build time and not at
    read time is the worst version of this.
    """
    with pytest.raises(Exception):
        ok_outcome("a.docx").source = "other.docx"  # type: ignore[misc]
    with pytest.raises(Exception):
        CorpusReport().outcomes = ()  # type: ignore[misc]
