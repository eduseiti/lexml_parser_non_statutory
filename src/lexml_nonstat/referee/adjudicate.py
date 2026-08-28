"""Adjudication — the one place a referee is allowed to change an outcome.

Everything the plan promises about the referee is enforced here, in one
function, rather than at each call site:

* **§7.3 constraint 1** — a confident rule is not even asked. The referee is
  consulted only below :data:`FLAG_THRESHOLD`.
* **§7.3 constraint 4 / invariant #9** — a rule at or above
  :data:`RULE_HIGH_CONFIDENCE` can never be overridden, and a referee below
  :data:`REFEREE_MIN_CONFIDENCE` never breaks a tie. Both checks live here even
  though the flag threshold already implies the first, because a future caller
  that consults a referee directly must not be able to route around the
  guarantee.
* **§7.3 constraint 5** — an abstention keeps the rule verdict.
* **§7.4 / invariant #10** — every adjudicated decision, consulted or not,
  produces a :class:`DecisionRecord` and its log lines.

Returning ``(verdict, record)`` rather than mutating anything keeps the caller
honest: routing has to decide what to do with the record, and cannot silently
apply a referee's answer without also recording that it did.
"""

from __future__ import annotations

import logging
from typing import Any

from ..telemetry.decisions import DecisionLog, DecisionRecord
from .protocol import (
    FLAG_THRESHOLD,
    REFEREE_MIN_CONFIDENCE,
    RULE_HIGH_CONFIDENCE,
    Verdict,
)

__all__ = ["adjudicate"]

#: Decision kind -> the referee method that answers it.
_METHODS = {
    "own_articulation": "is_own_articulation",
    "heading": "is_heading",
    "section_kind": "section_kind",
}


def adjudicate(
    *,
    kind: str,
    doc: str,
    locator: str,
    rule_verdict: Any,
    rule_confidence: float,
    excerpt: str = "",
    ctx: str = "",
    reason: str = "",
    referee: Any | None = None,
    log: DecisionLog | None = None,
    logger: logging.Logger | None = None,
) -> tuple[Any, DecisionRecord]:
    """Settle one decision, record it, and return ``(final_verdict, record)``.

    ``referee=None`` means referee-disabled, and a ``NullReferee`` — which sets
    ``enabled = False`` — is skipped identically, so the plan's first referee
    test (*NullReferee ⇒ byte-identical output to referee-disabled*) holds by
    construction rather than by coincidence.
    """
    flagged = rule_confidence < FLAG_THRESHOLD
    method = _METHODS.get(kind)

    # `enabled` lets a referee declare itself inert. `NullReferee` does, so
    # "--referee=none" and "no referee at all" produce the same record, not
    # merely the same verdict.
    consult = (
        flagged
        and referee is not None
        and getattr(referee, "enabled", True)
        and method is not None
    )
    if not consult:
        record = DecisionRecord.build(
            kind=kind,
            doc=doc,
            locator=locator,
            rule_verdict=rule_verdict,
            rule_confidence=rule_confidence,
            rule_flagged=flagged,
            final_verdict=rule_verdict,
            excerpt=excerpt,
            reason=reason,
        )
        record.emit(logger)
        if log is not None:
            log.add(record)
        return rule_verdict, record

    verdict = getattr(referee, method)(excerpt, ctx)
    if not isinstance(verdict, Verdict):
        # A referee that returns something else has broken the protocol. Treat
        # it exactly like a malformed API reply: abstain, keep the rule, say so.
        verdict = Verdict.abstain(
            f"referee returned {type(verdict).__name__}, expected Verdict"
        )

    overridable = (
        not verdict.abstained
        and rule_confidence < RULE_HIGH_CONFIDENCE
        and verdict.confidence >= REFEREE_MIN_CONFIDENCE
    )
    overridden = overridable and verdict.verdict != rule_verdict
    final = verdict.verdict if overridden else rule_verdict

    record = DecisionRecord.build(
        kind=kind,
        doc=doc,
        locator=locator,
        rule_verdict=rule_verdict,
        rule_confidence=rule_confidence,
        rule_flagged=flagged,
        final_verdict=final,
        excerpt=excerpt,
        reason=reason,
        referee_consulted=True,
        referee_verdict=verdict.verdict,
        referee_confidence=verdict.confidence,
        referee_rationale=verdict.rationale,
        referee_name=getattr(referee, "name", type(referee).__name__),
        overridden=overridden,
        abstained=verdict.abstained,
        cache_hit=bool(getattr(referee, "last_cache_hit", False)),
    )
    record.emit(logger)
    if log is not None:
        log.add(record)
    return final, record
