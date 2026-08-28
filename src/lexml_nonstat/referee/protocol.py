"""The referee contract, and the thresholds that keep it advisory.

Plan §7.1 is precise about the role: the referee **adjudicates flagged
decisions**; it never parses documents and never generates XML. Deterministic
rules remain the default path and must always produce valid output alone. So
this module defines three things and nothing else — the answer shape, the
protocol, and the numbers that decide when an answer is allowed to matter.

Three thresholds, each doing a different job:

``FLAG_THRESHOLD`` (0.60)
    Below this a rule did not know its own answer. Only these decisions are
    put to a referee — §7.3 constraint 1, "rules run first, always".

``RULE_HIGH_CONFIDENCE`` (0.75)
    At or above this a rule verdict is unassailable, whatever a referee says.
    This is invariant #9 written as a number. It is deliberately *above*
    ``FLAG_THRESHOLD`` rather than equal to it, so the guarantee survives a
    caller that consults a referee directly instead of going through
    :func:`~.adjudicate.adjudicate`.

``REFEREE_MIN_CONFIDENCE`` (0.60)
    A referee that is itself unsure does not get to break a tie. An LLM asked a
    hard question answers something; this is what stops "something" from
    becoming structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "FLAG_THRESHOLD",
    "OWN_ARTICULATION_VERDICTS",
    "REFEREE_MIN_CONFIDENCE",
    "RULE_HIGH_CONFIDENCE",
    "Referee",
    "Verdict",
    "is_flagged",
]

#: A rule below this confidence is flagged for adjudication.
FLAG_THRESHOLD = 0.60

#: A rule at or above this confidence can never be overridden (invariant #9).
RULE_HIGH_CONFIDENCE = 0.75

#: A referee below this confidence may not change an outcome.
REFEREE_MIN_CONFIDENCE = 0.60

#: The vocabulary of ``is_own_articulation``. Anything else is malformed and
#: abstains — a referee inventing a third answer is a referee to ignore.
OWN_ARTICULATION_VERDICTS: tuple[str, ...] = ("own", "quoted")

#: The vocabulary of ``is_heading``.
HEADING_VERDICTS: tuple[str, ...] = ("heading", "prose")


@dataclass(frozen=True)
class Verdict:
    """A referee's answer, or its refusal to give one.

    ``verdict is None`` means **abstained**: the referee was asked and produced
    nothing usable. Every failure mode in §7.3 constraint 5 — timeout, 5xx,
    non-JSON, JSON of the wrong shape, a missing binary — arrives here as an
    abstention carrying its reason in ``rationale``, never as an exception. A
    referee outage degrades quality; it never degrades availability.
    """

    verdict: str | None = None
    confidence: float = 0.0
    rationale: str = ""

    @property
    def abstained(self) -> bool:
        return self.verdict is None

    @classmethod
    def abstain(cls, reason: str) -> "Verdict":
        return cls(None, 0.0, reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": round(self.confidence, 4),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Verdict":
        return cls(
            verdict=data.get("verdict"),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            rationale=str(data.get("rationale", "") or ""),
        )


@runtime_checkable
class Referee(Protocol):
    """Plan §7.3's protocol. Three questions, no more.

    Each returns a :class:`Verdict` and **never raises**. Implementations are
    free to be slow, cached, remote or absent; they are not free to fail.
    """

    name: str

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        """Is ``excerpt`` this document's own article, or one it quotes?"""

    def is_heading(self, para: str, ctx: str) -> Verdict:
        """Is ``para`` a heading, or an emphasised sentence?"""

    def section_kind(self, label: str, heading: str) -> Verdict:
        """What kind of section does ``label``/``heading`` name?"""


def is_flagged(confidence: float) -> bool:
    """Did the rule fall below the threshold at which we ask for help?"""
    return confidence < FLAG_THRESHOLD
