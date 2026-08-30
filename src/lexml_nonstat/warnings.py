"""Structured warnings — what the parser wants the operator to know.

    from lexml_nonstat.warnings import collect_warnings
    for warning in collect_warnings(model, rendered):
        print(warning.format(), file=sys.stderr)

**Why this is not telemetry.** :mod:`..telemetry` is plan §7.4's rule-vs-referee
channel: it counts *decisions*, and its report answers "will the rules survive
300 documents". A warning answers a different question for a different reader —
"is anything about *this* document worth your attention" — and folding the two
would make §7.4's counts include things that are not decisions at all.

**Why a closed code list.** The same reason :data:`..routing.BLOCKER_CODES` is
closed: a diagnostic a caller cannot enumerate is a diagnostic a caller cannot
act on, and a free-text warning channel degrades into log lines nobody reads.
:class:`Warning` refuses an undeclared code at construction, so a typo is a test
failure rather than a warning that never fires.

**Why nothing here decides anything.** :func:`collect_warnings` is a pure
function of objects the pipeline has already produced. It computes no coverage,
infers no structure and validates nothing — it reads conclusions that
:mod:`..routing`, :mod:`..hierarchy` and :mod:`..render` already reached. A
warning channel that reached its own conclusions would be a second source of
truth for them, which is the failure Cycle 4b's report warned about for routing.

**The name.** ``Warning`` shadows the builtin, deliberately and narrowly: this
module is never ``import *``-ed, the codebase uses the builtin nowhere, and the
alternatives (``CliWarning``, ``Diagnostic``) each say less about what the thing
is. It is not an exception and is not a subclass of one — a test pins that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "LOW_CONFIDENCE",
    "WARNING_CODES",
    "Warning",
    "collect_warnings",
]

#: A bundle had annex documents and no ``-o`` directory to write them to.
ANNEXES_NOT_WRITTEN = "annexes_not_written"
#: A rendering was requested that the schemas present cannot validate.
EMITTER_UNAVAILABLE = "emitter_unavailable"
#: §4.2's validate-then-fallback declined the statutory rendering.
STATUTORY_FALLBACK = "statutory_fallback"
#: An emitted document did not validate.
INVALID_OUTPUT = "invalid_output"
#: Routing reached its verdict with little to go on.
LOW_CONFIDENCE_CODE = "low_confidence"
#: Hierarchy inference found no structure and fell back to a flat body.
FLAT_FALLBACK = "flat_fallback"
#: Metadata could not assemble a complete URN (A-2.3 — four samples cannot).
INCOMPLETE_URN = "incomplete_urn"
#: One file of a multi-file run could not be read.
UNREADABLE_SOURCE = "unreadable_source"
#: The source produced no blocks at all.
EMPTY_DOCUMENT = "empty_document"

WARNING_CODES: tuple[str, ...] = (
    ANNEXES_NOT_WRITTEN,
    EMITTER_UNAVAILABLE,
    STATUTORY_FALLBACK,
    INVALID_OUTPUT,
    LOW_CONFIDENCE_CODE,
    FLAT_FALLBACK,
    INCOMPLETE_URN,
    UNREADABLE_SOURCE,
    EMPTY_DOCUMENT,
)

#: Below this, routing's own confidence is worth saying out loud. Deliberately
#: *not* :data:`..hierarchy.evidence.CONFIDENCE_THRESHOLD`: that one decides
#: whether a tree is structured, this one decides whether to mention it.
LOW_CONFIDENCE = 0.60


@dataclass(frozen=True)
class Warning:
    """One thing worth telling the operator about one document.

    ``source`` is the document it concerns, so a multi-file run's warnings stay
    attributable after they are collected into one list.
    """

    code: str
    detail: str
    source: str | None = None

    def __post_init__(self) -> None:
        if self.code not in WARNING_CODES:
            raise ValueError(
                f"unknown warning code {self.code!r}; "
                f"declared codes are {', '.join(WARNING_CODES)}"
            )

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "detail": self.detail, "source": self.source}

    def format(self) -> str:
        """One line, no trailing newline — ready for ``print(..., file=stderr)``."""
        where = f"{self.source}: " if self.source else ""
        return f"warning: {where}{self.code}: {self.detail}"


def _confidence_of(viability: Any) -> float | None:
    value = getattr(viability, "confidence", None)
    return float(value) if isinstance(value, (int, float)) else None


def collect_warnings(
    model: Any,
    rendered: Any = None,
    *,
    report: Any = None,
    requested_emitter: str = "auto",
    wrote_annexes: bool = False,
) -> tuple[Warning, ...]:
    """Everything worth saying about one already-processed document.

    Never raises and never computes: every argument is optional and every field
    is read defensively, because this is called on the degenerate documents
    Cycle 8 exists to survive — a model whose ``metadata`` is a stub is a case
    to describe, not a case to crash on.

    Args:
        model: the :class:`~..model.DocumentModel`, or ``None``.
        rendered: the :class:`~..render.RenderedDocument`, or ``None``.
        report: a :class:`~..validate.ValidationReport` for the primary
            document, or ``None`` when validation was not run.
        requested_emitter: what the caller asked for, so a fallback can be
            reported as a fallback rather than as the ordinary outcome.
        wrote_annexes: whether the annex documents reached a file.
    """
    source = getattr(model, "source", None) if model is not None else None
    out: list[Warning] = []

    if model is not None:
        styled = getattr(model, "styled", None)
        if styled is not None and not getattr(styled, "blocks", ()):
            out.append(
                Warning(EMPTY_DOCUMENT, "the source produced no content blocks", source)
            )

        metadata = getattr(model, "metadata", None)
        if metadata is not None and not getattr(metadata, "complete", True):
            missing = ", ".join(getattr(metadata, "missing", ()) or ("unknown",))
            out.append(
                Warning(
                    INCOMPLETE_URN,
                    f"the URN is a best effort; missing: {missing}",
                    source,
                )
            )

        body = getattr(model, "body", None)
        if body is not None and getattr(body, "flat", False):
            out.append(
                Warning(
                    FLAT_FALLBACK,
                    "no hierarchy was inferred; the body is rendered flat "
                    f"(confidence {getattr(body, 'confidence', 0.0):.2f})",
                    source,
                )
            )

        confidence = _confidence_of(getattr(model, "viability", None))
        if confidence is not None and confidence < LOW_CONFIDENCE:
            out.append(
                Warning(
                    LOW_CONFIDENCE_CODE,
                    f"route {getattr(model, 'route', '?')} decided with "
                    f"confidence {confidence:.2f}, below {LOW_CONFIDENCE}",
                    source,
                )
            )

    if rendered is not None:
        emitter = getattr(rendered, "emitter", None)
        # A-6.3: `RenderedDocument.emitter` records which emitter actually
        # produced the artifact, which is exactly what makes a fallback visible.
        wanted = (
            getattr(model, "route", None) if requested_emitter == "auto" else requested_emitter
        )
        if wanted == "norma" and emitter is not None and emitter != "norma":
            out.append(
                Warning(
                    STATUTORY_FALLBACK,
                    "the statutory rendering did not pass §4.2's gates; "
                    f"emitted as {emitter} instead",
                    source,
                )
            )

        annexes = getattr(rendered, "annexes", ())
        if annexes and not wrote_annexes:
            out.append(
                Warning(
                    ANNEXES_NOT_WRITTEN,
                    f"{len(annexes)} annex document(s) were rendered but not "
                    "written; pass -o DIR to keep them",
                    source,
                )
            )

    if report is not None and not getattr(report, "ok", True):
        summary = getattr(report, "summary", lambda: "")()
        first = summary.splitlines()[0] if summary else "no detail"
        out.append(Warning(INVALID_OUTPUT, first, source))

    return tuple(out)
