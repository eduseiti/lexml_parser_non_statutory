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
    "BOUNDARY_VERDICTS",
    "FLAG_THRESHOLD",
    "HEADING_VERDICTS",
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

#: The vocabulary of ``is_heading`` (A-H.2). ``"secao"`` **confirms** that the
#: paragraph opens a thematic division of the document; ``"nao"`` **vetoes**.
#:
#: It was ``("heading", "prose")`` until amendment A-H.2, and the rename is the
#: point rather than cosmetic. That question was typographic — *is this set like
#: a title, or is it an emphasised phrase?* — and put live to the corpus it
#: answered "heading" for `Fl. 9 DF COSIT RFB` at 0.95 and for the signatory's
#: name at 0.80, because both **are** set like titles. The question the tree
#: needs is structural, and a vocabulary naming typographic roles invites the
#: typographic answer.
HEADING_VERDICTS: tuple[str, ...] = ("secao", "nao")

#: The vocabulary of ``quotation_boundary`` (A-Q.3). Two answers, and the
#: question is only ever asked about a candidate the deterministic generator
#: already proposed — so ``"boundary"`` **confirms** and ``"continuation"``
#: **vetoes**. Neither can create a boundary the rules did not find, which is
#: what keeps invariant #8 an argument about the generator rather than a hope
#: about the model.
BOUNDARY_VERDICTS: tuple[str, ...] = ("boundary", "continuation")


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
    """Plan §7.3's protocol. Four questions, no more.

    The fourth, ``quotation_boundary``, was added by amendment A-Q.3 and is
    deliberately shaped differently from the other three: it is **confirm-only**
    — put to the referee about a candidate the rules already found, never asked
    open-endedly. Record §2.3 measured why that inversion is necessary: on the
    per-paragraph questions the model answered two of three wrongly, at
    confidences of 0.95 and 0.70.

    Each returns a :class:`Verdict` and **never raises**. Implementations are
    free to be slow, cached, remote or absent; they are not free to fail.
    """

    name: str

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        """Is ``excerpt`` this document's own article, or one it quotes?"""

    def is_heading(self, para: str, ctx: str, next_ctx: str = "") -> Verdict:
        """Does ``para`` open a thematic division of the document (A-H.2)?

        Asked **only** about a paragraph the deterministic prose-form gate
        already proposed, so — like ``quotation_boundary`` — it confirms or
        vetoes and can never volunteer a header.

        ``next_ctx`` is the following paragraph, and it is not padding: a
        heading is defined by what follows it as much as by what precedes it.
        ``CONCLUSÃO`` followed by ``19. A cessão de direitos…`` reads as a
        heading; ``COORDENADOR-GERAL DA COSIT`` followed by a disclaimer does
        not.
        """

    def section_kind(self, label: str, heading: str) -> Verdict:
        """What kind of section does ``label``/``heading`` name?"""

    def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
        """Does ``excerpt`` begin a NEW quotation, of a different norm?

        Asked **only** about a candidate the deterministic head detector already
        proposed. A referee cannot volunteer a boundary, so the worst a wrong
        answer can do is leave a document flat — never fabricate a citable unit
        (A-Q.3).
        """


def is_flagged(confidence: float) -> bool:
    """Did the rule fall below the threshold at which we ask for help?"""
    return confidence < FLAG_THRESHOLD
