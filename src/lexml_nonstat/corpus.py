"""Batch mode over a whole corpus — plan §8 Cycle 9, amendment **A-9.3**.

    python3 -m lexml_nonstat corpus samples/
    python3 -m lexml_nonstat corpus --format=json --linker=fixtures corpus/

The 15 samples stand in for **300+** unseen documents (plan §10's top risk), and
the instrument that risk asks for is a run over all of them that *reconciles*:
one report saying how they routed, what blocked the statutory route, what the
rules were unsure of, and what failed outright — with the counts checkable
against each other rather than merely printed.

**Three things this module deliberately does not do.**

It does not render to files — that is ``parse``'s job, and a second writer
would be a second source of truth for §2.9's naming. It does not re-derive
§7.4's referee counts: it *embeds* :class:`~.telemetry.DecisionsReport`, whose
:meth:`~.telemetry.DecisionsReport.check` already asserts the two identities
amendment **A-4b.4** corrected (spec decision N-3). And it does not infer a
document's route — :func:`~.model.build_model` decides that, here as everywhere
else, so a corpus tally and a per-document ``parse`` can never disagree.

**Per-document isolation is the whole point.** One unreadable file among 300
must not abandon the other 299. Every document is processed inside a
``try``/``except`` that records the failure against that document and
continues; ``stop_on_error`` opts out for a caller who wants the first failure
to be fatal. This mirrors :func:`~.cli._for_each_document`, whose docstring
already anticipated "the 300-document corpus Cycle 9 is aimed at".

**Reconciliation is a checkable property, not a word.**
:meth:`CorpusReport.check` returns the first failing identity or ``None``: the
outcome counts must sum, every route must be a declared emitter, every blocker
and warning code must be in its closed vocabulary, and a failed document must
carry an error and no route while a successful one carries a route and no
error. A report that printed plausible numbers which did not add up would be
worse than no report, because it would be believed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .ingest import READERS, read_document
from .routing.viability import BLOCKER_CODES, EMITTERS
from .telemetry import DecisionLog, DecisionsReport
from .warnings import WARNING_CODES, collect_warnings

__all__ = [
    "CorpusReport",
    "DocumentOutcome",
    "render_corpus_report",
    "run_corpus",
    "walk_corpus",
]

#: The suffixes a corpus walk collects, read from the reader table rather than
#: restated. :data:`~.ingest.READERS` is "the single place formats are
#: declared"; a hand-maintained copy here would drift the moment a reader is
#: added, and the drift would look like a corpus that simply has no files of
#: that kind — silent, and indistinguishable from a correct empty result.
SUPPORTED_SUFFIXES: tuple[str, ...] = tuple(sorted(READERS))


def _ranked(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    """Count descending, then name — :func:`~.telemetry.report.ranked`'s order.

    Deterministic even when two entries tie, which invariant #4 requires of
    anything a golden, a diff or a report might touch.
    """
    return tuple(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


@dataclass(frozen=True)
class DocumentOutcome:
    """What became of one document in a corpus run.

    ``ok`` and ``error`` are the discriminator, and :meth:`CorpusReport.check`
    asserts they agree with the rest: a failed document has an error and no
    route, a successful one has a route and no error. Recording a failure as a
    document with an empty route and no explanation is exactly the outcome that
    makes a batch report untrustworthy at 300 documents.

    ``valid`` is tri-state on purpose. ``None`` means validation was not run,
    which is a different fact from ``False`` — and at corpus scale the
    difference decides whether "0 invalid" is reassuring or meaningless.
    """

    source: str
    ok: bool
    urn: str = ""
    profile: str = ""
    route: str = ""
    emitter: str = ""
    confidence: float = 0.0
    flat: bool = True
    documents: int = 0
    valid: bool | None = None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    references: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ok": self.ok,
            "urn": self.urn,
            "profile": self.profile,
            "route": self.route,
            "emitter": self.emitter,
            "confidence": self.confidence,
            "flat": self.flat,
            "documents": self.documents,
            "valid": self.valid,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "references": self.references,
            "error": self.error,
        }


@dataclass(frozen=True)
class CorpusReport:
    """One run over a corpus, as data.

    ``decisions`` is an embedded :class:`~.telemetry.DecisionsReport` rather
    than a recount (spec decision N-3). §7.4's identities are already checked
    there, and a second implementation of them would be a second thing to keep
    right.
    """

    outcomes: tuple[DocumentOutcome, ...] = ()
    decisions: DecisionsReport = field(default_factory=DecisionsReport)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def succeeded(self) -> int:
        return sum(1 for o in self.outcomes if o.ok)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if not o.ok)

    @property
    def references(self) -> int:
        """Every resolved external reference in the run (Cycle 8e)."""
        return sum(o.references for o in self.outcomes)

    @property
    def invalid(self) -> int:
        """Documents that were validated and rejected. ``None`` does not count."""
        return sum(1 for o in self.outcomes if o.valid is False)

    @property
    def validated(self) -> int:
        return sum(1 for o in self.outcomes if o.valid is not None)

    def by_route(self) -> tuple[tuple[str, int], ...]:
        return _ranked(Counter(o.route for o in self.outcomes if o.ok))

    def by_profile(self) -> tuple[tuple[str, int], ...]:
        return _ranked(Counter(o.profile for o in self.outcomes if o.ok))

    def by_emitter(self) -> tuple[tuple[str, int], ...]:
        return _ranked(Counter(o.emitter for o in self.outcomes if o.ok))

    def by_blocker(self) -> tuple[tuple[str, int], ...]:
        return _ranked(Counter(c for o in self.outcomes for c in o.blockers))

    def by_warning(self) -> tuple[tuple[str, int], ...]:
        return _ranked(Counter(c for o in self.outcomes for c in o.warnings))

    def check(self) -> str | None:
        """Return the first identity that fails, or ``None`` when all hold.

        Modelled on :meth:`~.telemetry.DecisionsReport.check`, and for the same
        reason: a report is only worth printing if its numbers can be shown to
        agree with each other.
        """
        if self.succeeded + self.failed != self.total:
            return (
                f"succeeded + failed != total "
                f"({self.succeeded} + {self.failed} != {self.total})"
            )

        routed = sum(n for _, n in self.by_route())
        if routed != self.succeeded:
            return (
                f"route tallies != succeeded ({routed} != {self.succeeded}): a "
                "document was processed without being routed"
            )

        for route, _ in self.by_route():
            if route not in EMITTERS:
                return f"unknown route {route!r}; §4.4 declares {', '.join(EMITTERS)}"

        for code, _ in self.by_blocker():
            if code not in BLOCKER_CODES:
                return f"unknown blocker code {code!r}"

        for code, _ in self.by_warning():
            if code not in WARNING_CODES:
                return f"unknown warning code {code!r}"

        for outcome in self.outcomes:
            if outcome.ok and not outcome.route:
                return f"{outcome.source}: succeeded with no route"
            if outcome.ok and outcome.error:
                return f"{outcome.source}: succeeded but carries an error"
            if not outcome.ok and not outcome.error:
                return f"{outcome.source}: failed with no error recorded"
            if not outcome.ok and outcome.route:
                return f"{outcome.source}: failed but carries route {outcome.route!r}"

        return self.decisions.check()

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "validated": self.validated,
            "invalid": self.invalid,
            "references": self.references,
            "by_route": [list(p) for p in self.by_route()],
            "by_profile": [list(p) for p in self.by_profile()],
            "by_emitter": [list(p) for p in self.by_emitter()],
            "by_blocker": [list(p) for p in self.by_blocker()],
            "by_warning": [list(p) for p in self.by_warning()],
            "decisions": self.decisions.to_dict(),
            "documents": [o.to_dict() for o in self.outcomes],
        }


def walk_corpus(
    paths: Iterable[Path | str], *, limit: int | None = None
) -> tuple[Path, ...]:
    """Every supported document under ``paths``, sorted and deduplicated.

    A directory is walked recursively; a file is taken as itself, whatever its
    suffix — a caller who names a file meant that file, and refusing it because
    the walk would not have found it is a surprise, not a safeguard.

    Sorted because invariant #4 makes determinism a property of this pipeline,
    and a corpus report whose document order depended on the filesystem could
    not be diffed between runs.
    """
    found: list[Path] = []
    seen: set[Path] = set()

    for entry in paths:
        path = Path(entry)
        if path.is_dir():
            candidates = sorted(
                p
                for p in path.rglob("*")
                if p.is_file() and p.suffix.lower() in READERS
            )
        else:
            candidates = [path]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                found.append(candidate)

    if limit is not None:
        found = found[:limit]
    return tuple(found)


def _reference_count(rendered: Any) -> int:
    """Resolved ``Remissao`` elements across the bundle (Cycle 8e).

    Counted off the rendered artifact rather than asked of the linker: what
    reached the document is the fact worth reporting, and it is the same thing
    the linked goldens pin.
    """
    from .render.common import LEXML_NS

    try:
        return sum(
            len(document.findall(f".//{{{LEXML_NS}}}Remissao"))
            for document in rendered.documents
        )
    except Exception:  # noqa: BLE001 - a tally must never fail a run
        return 0


def run_corpus(
    paths: Sequence[Path | str],
    *,
    emitter: str = "auto",
    schema: str = "both",
    generation: str | None = None,
    profile: Any = None,
    referee: Any = None,
    linker: Any = None,
    validate_output: bool = True,
    stop_on_error: bool = False,
    limit: int | None = None,
) -> CorpusReport:
    """Process every document under ``paths`` and reconcile the results.

    Every document is isolated: an exception is recorded against that document
    and the walk continues, because a batch that abandons its work on the first
    bad file is useless at 300 documents. ``stop_on_error`` opts out.

    ``referee`` and ``linker`` default to ``None`` — the same default every
    other entry point carries (§7.3 constraint 7, A-L.7), so a corpus run makes
    no network call and spawns no subprocess unless asked to in so many words.
    """
    from .cli import _generation_for, _render, _validate_documents
    from .model import build_model

    log = DecisionLog()
    outcomes: list[DocumentOutcome] = []

    for path in walk_corpus(paths, limit=limit):
        source = str(path)
        try:
            doc = read_document(path)
            model = build_model(
                doc, filename=path.name, profile=profile, log=log, referee=referee
            )
            rendered = _render(model, emitter, linker=linker)

            report = None
            if validate_output:
                report = _validate_documents(
                    rendered,
                    schema,
                    _generation_for(rendered.emitter, generation or "shipped"),
                )

            warnings = collect_warnings(
                model, rendered, report=report, requested_emitter=emitter
            )
            viability = model.viability
            outcomes.append(
                DocumentOutcome(
                    source=source,
                    ok=True,
                    urn=rendered.urn,
                    profile=model.profile,
                    route=model.route,
                    emitter=rendered.emitter,
                    confidence=round(
                        float(getattr(viability, "confidence", 0.0)), 4
                    ),
                    flat=bool(getattr(model.body, "flat", True)),
                    documents=len(rendered.documents),
                    # `_validate_documents` returns the first *bad* report, or
                    # None when every document passed — so "no report" means
                    # valid here, and only `validate_output=False` means
                    # unknown.
                    valid=(report is None) if validate_output else None,
                    blockers=tuple(
                        b.code for b in getattr(viability, "blockers", ())
                    ),
                    warnings=tuple(w.code for w in warnings),
                    references=_reference_count(rendered),
                )
            )
        except Exception as exc:  # noqa: BLE001 - isolation is the deliverable
            outcomes.append(
                DocumentOutcome(
                    source=source,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
                )
            )
            if stop_on_error:
                break

    return CorpusReport(
        outcomes=tuple(outcomes), decisions=DecisionsReport.from_log(log)
    )


def render_corpus_report(report: CorpusReport) -> str:
    """The corpus summary as text.

    Leads with the failures, then the reconciliation check, then the tallies.
    At 300 documents the interesting line is never "297 succeeded" — it is
    which three did not, and whether the numbers describing the other 297 can
    be trusted.
    """
    from .telemetry import render_report

    lines = [
        f"Documents:             {report.total:,}",
        f"  succeeded:           {report.succeeded:,}",
        f"  failed:              {report.failed:,}",
    ]

    if report.validated:
        lines.append(
            f"  validated:           {report.validated:,}  "
            f"({report.invalid:,} invalid)"
        )
    if report.references:
        lines.append(f"  references resolved: {report.references:,}")

    for outcome in report.outcomes:
        if not outcome.ok:
            lines.append(f"  ! {outcome.source}: {outcome.error}")

    def pairs(label: str, items: tuple[tuple[str, int], ...]) -> str:
        if not items:
            return f"{label} none"
        return f"{label} " + " · ".join(f"{name} {n}" for name, n in items)

    lines.extend(
        [
            "",
            pairs("Routes:               ", report.by_route()),
            pairs("Profiles:             ", report.by_profile()),
            pairs("Emitters:             ", report.by_emitter()),
            pairs("Blockers:             ", report.by_blocker()),
            pairs("Warnings:             ", report.by_warning()),
            "",
            render_report(report.decisions),
        ]
    )

    problem = report.check()
    lines.extend(
        ["", f"Reconciliation: {'ok' if problem is None else 'FAILED — ' + problem}"]
    )
    return "\n".join(lines)
