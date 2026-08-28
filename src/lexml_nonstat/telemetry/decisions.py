"""The decision record — what the rules decided, and what the referee did.

Plan §7.4 makes observability a deliverable rather than a debugging aid, for a
specific reason: 15 samples stand in for 300+ unseen documents, and the only
instrument that can say whether the rules generalise is a count of how often
they were unsure and how often they were wrong. A rule that quietly guesses is
indistinguishable from a rule that knows — until the corpus grows.

So every adjudicated decision leaves a :class:`DecisionRecord`, and the log
lines are written to be read by a person scanning a batch run:

    INFO  routing  port_mf_277        rule=norma conf=0.86  referee=skipped  final=norma
    WARN  rules    par_cosit_26 p#47  RULE FAILED: convicted only by excerpt-run extension
    WARN  referee  par_cosit_26 p#47  REFEREE OVERRODE RULE: rule=own conf=0.50 ->
                                      referee=quoted conf=0.88  final=quoted
                                      rationale="..."
    INFO  referee  par_cosit_26 p#46  referee agreed with rule (quoted); no override

``WARN`` is deliberate on both the rule failure and the override. A flagged rule
is a rule that did not know its own answer; an override is a rule that was
wrong. Neither should need a ``--verbose`` to become visible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterator

__all__ = [
    "DECISION_KINDS",
    "DecisionLog",
    "DecisionRecord",
    "LOGGER_NAME",
    "MAX_EXCERPT_IN_RECORD",
    "logger",
]

#: One logger for the whole decision channel, so a batch run can raise or
#: silence adjudication chatter without touching anything else.
LOGGER_NAME = "lexml_nonstat.decisions"

#: The decision kinds §7.4 names. ``route`` and ``own_articulation`` are the two
#: the pipeline makes today (spec decision D-3); ``heading`` and
#: ``section_kind`` are on the referee protocol (§7.3) and reserved here so a
#: later cycle wiring them needs no vocabulary change.
DECISION_KINDS: tuple[str, ...] = (
    "route",
    "own_articulation",
    "heading",
    "section_kind",
)

#: Excerpts are for audit, not for reconstruction. Bounded so a decision log
#: over 300 documents stays a log rather than a second copy of the corpus.
MAX_EXCERPT_IN_RECORD = 200


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def _truncate(text: str, limit: int = MAX_EXCERPT_IN_RECORD) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class DecisionRecord:
    """One adjudicated decision, in §7.4's fields.

    ``abstained`` is not in the plan's list. It has to be: a referee that was
    consulted and answered nothing is neither an agreement nor an override, and
    collapsing it into either would misreport exactly the metric §7.4 exists to
    produce. See the spec's §2.3 and amendment A-4b.4.
    """

    decision_id: str
    kind: str
    doc: str
    locator: str
    rule_verdict: Any
    rule_confidence: float
    rule_flagged: bool
    final_verdict: Any
    referee_consulted: bool = False
    referee_verdict: Any | None = None
    referee_confidence: float | None = None
    referee_rationale: str | None = None
    referee_name: str | None = None
    overridden: bool = False
    abstained: bool = False
    cache_hit: bool = False
    excerpt: str = ""
    reason: str = ""

    @property
    def answered(self) -> bool:
        """Consulted and produced a usable verdict."""
        return self.referee_consulted and not self.abstained

    @property
    def agreed(self) -> bool:
        """Consulted, answered, and said the same thing the rule said.

        Not "did not change the outcome" — that was the first definition here
        and it was wrong in a way that corrupts the one metric §7.4 exists to
        produce. A referee whose verdict **contradicts** the rule but is refused
        the override — because it was itself unsure (below
        ``REFEREE_MIN_CONFIDENCE``) or because the rule was too confident to
        touch — did not agree with anything. Counting it as an agreement
        inflates "rules were right but unsure", which is precisely the number
        used to decide whether the thresholds can be tightened.

        The low-confidence case is reachable with the shipped constants; a
        mutation test surfaced it.
        """
        return self.answered and self.referee_verdict == self.rule_verdict

    @property
    def overruled(self) -> bool:
        """Consulted, answered, contradicted the rule, and was refused.

        The fourth bucket. It is the interesting one for tuning: a referee that
        keeps being overruled is either wrong or being gated too hard, and
        neither shows up in the agreed/overrode split.
        """
        return self.answered and not self.overridden and self.referee_verdict != self.rule_verdict

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "kind": self.kind,
            "doc": self.doc,
            "locator": self.locator,
            "rule_verdict": self.rule_verdict,
            "rule_confidence": round(self.rule_confidence, 4),
            "rule_flagged": self.rule_flagged,
            "final_verdict": self.final_verdict,
            "referee_consulted": self.referee_consulted,
            "referee_verdict": self.referee_verdict,
            "referee_confidence": (
                None
                if self.referee_confidence is None
                else round(self.referee_confidence, 4)
            ),
            "referee_rationale": self.referee_rationale,
            "referee_name": self.referee_name,
            "overridden": self.overridden,
            "abstained": self.abstained,
            "cache_hit": self.cache_hit,
            "excerpt": self.excerpt,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRecord":
        return cls(
            decision_id=str(data["decision_id"]),
            kind=str(data["kind"]),
            doc=str(data.get("doc", "")),
            locator=str(data.get("locator", "")),
            rule_verdict=data.get("rule_verdict"),
            rule_confidence=float(data.get("rule_confidence", 0.0)),
            rule_flagged=bool(data.get("rule_flagged", False)),
            final_verdict=data.get("final_verdict"),
            referee_consulted=bool(data.get("referee_consulted", False)),
            referee_verdict=data.get("referee_verdict"),
            referee_confidence=data.get("referee_confidence"),
            referee_rationale=data.get("referee_rationale"),
            referee_name=data.get("referee_name"),
            overridden=bool(data.get("overridden", False)),
            abstained=bool(data.get("abstained", False)),
            cache_hit=bool(data.get("cache_hit", False)),
            excerpt=str(data.get("excerpt", "")),
            reason=str(data.get("reason", "")),
        )

    @classmethod
    def build(
        cls,
        *,
        kind: str,
        doc: str,
        locator: str,
        rule_verdict: Any,
        rule_confidence: float,
        rule_flagged: bool,
        final_verdict: Any,
        excerpt: str = "",
        reason: str = "",
        **rest: Any,
    ) -> "DecisionRecord":
        """Construct a record with §7.4's stable ``decision_id``.

        ``f"{doc}:{kind}:{locator}"`` — stable across runs and unique within a
        document, which is what makes two runs' logs diffable.
        """
        return cls(
            decision_id=f"{doc}:{kind}:{locator}",
            kind=kind,
            doc=doc,
            locator=locator,
            rule_verdict=rule_verdict,
            rule_confidence=rule_confidence,
            rule_flagged=rule_flagged,
            final_verdict=final_verdict,
            excerpt=_truncate(excerpt),
            reason=reason,
            **rest,
        )

    # -- log lines ---------------------------------------------------------
    #
    # Emitted by `emit`, not by the constructor, so a caller can build records
    # for a report without narrating them a second time.

    @property
    def _where(self) -> str:
        return f"{self.doc} {self.locator}".strip()

    def emit(self, log: logging.Logger | None = None) -> None:
        """Write this decision's §7.4 log lines."""
        log = log or logger()

        if self.rule_flagged:
            log.warning(
                "rules    %s  RULE FAILED: %s  rule=%s conf=%.2f (flagged)",
                self._where,
                self.reason or "confidence below threshold",
                self.rule_verdict,
                self.rule_confidence,
            )

        if not self.referee_consulted:
            log.info(
                "%-8s %s  rule=%s conf=%.2f  referee=skipped  final=%s",
                self.kind,
                self._where,
                self.rule_verdict,
                self.rule_confidence,
                self.final_verdict,
            )
            return

        if self.abstained:
            log.warning(
                "referee  %s  REFEREE ABSTAINED: %s  rule=%s conf=%.2f retained",
                self._where,
                self.referee_rationale or "no verdict",
                self.rule_verdict,
                self.rule_confidence,
            )
        elif self.overridden:
            log.warning(
                "referee  %s  REFEREE OVERRODE RULE: rule=%s conf=%.2f -> "
                'referee=%s conf=%.2f  final=%s  rationale="%s"',
                self._where,
                self.rule_verdict,
                self.rule_confidence,
                self.referee_verdict,
                self.referee_confidence or 0.0,
                self.final_verdict,
                self.referee_rationale or "",
            )
        else:
            log.info(
                "referee  %s  referee agreed with rule (%s); no override",
                self._where,
                self.final_verdict,
            )


@dataclass
class DecisionLog:
    """Every decision made while processing one or more documents, in order."""

    records: list[DecisionRecord] = field(default_factory=list)

    def add(self, record: DecisionRecord) -> DecisionRecord:
        self.records.append(record)
        return record

    def extend(self, other: "DecisionLog") -> None:
        self.records.extend(other.records)

    def __iter__(self) -> Iterator[DecisionRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def for_doc(self, doc: str) -> tuple[DecisionRecord, ...]:
        return tuple(r for r in self.records if r.doc == doc)

    def of_kind(self, kind: str) -> tuple[DecisionRecord, ...]:
        return tuple(r for r in self.records if r.kind == kind)

    def to_dict(self) -> dict[str, Any]:
        return {"records": [r.to_dict() for r in self.records]}

    def to_json(self, *, indent: int = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionLog":
        return cls(records=[DecisionRecord.from_dict(r) for r in data.get("records", ())])
