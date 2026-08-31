"""Evidence fusion and confidence — how sure we are, and why.

Plan §3 puts *evidence fusion* at the centre of hierarchy inference: style,
numbering, label, typography and indent are five weak signals that together are
strong. This module holds the weights and the arithmetic; :mod:`.unify` decides
which signals fired and :mod:`.tree` acts on the result.

The point of scoring at all is invariant #8: **low confidence degrades to flat,
never invents structure**. With 15 samples standing in for 300+ unseen
documents, a parser that guesses is worse than one that declines — a flat
document is still fully readable and fully citable, while a fabricated section
is a lie that validates.

Weights are ordered by how much the *source* has committed to the claim. A Word
outline level is an author saying "this is a heading" in the file format itself,
so it outranks everything. A label inside a validated series is nearly as good:
the document numbered itself and the numbers add up. A lone label with no series
behind it is barely evidence at all — ``parecer_93``'s ``46.`` is a quoted
document's paragraph number, and nothing but the absence of a series says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model.nodes import Evidence

__all__ = [
    "CONFIDENCE_THRESHOLD",
    "DocSignals",
    "Evidence",
    "W_LABEL_SERIES",
    "W_LABEL_SOLO",
    "W_PROSE_HEADER_CONFIRMED",
    "W_STYLE",
    "W_UNIT_SERIES",
    "document_confidence",
]

#: A Word outline level or Heading style — the author's own declaration.
W_STYLE = 0.9
#: A label that belongs to a series the document validated (`2.`, `2.1`, `2.2`).
W_LABEL_SERIES = 0.85
#: A repeated named unit (`Súmula CARF nº 1` … `nº 130`).
W_UNIT_SERIES = 0.8
#: A label with no series behind it. Deliberately below the threshold: on its
#: own it is never enough to build a document's structure on.
W_LABEL_SOLO = 0.25

#: A prose-form header a referee confirmed (A-H.4). Matches `W_UNIT_SERIES`:
#: strong evidence, but deliberately not `W_STYLE`-strong — Word declaring a
#: heading remains the better witness than a model agreeing with a typographic
#: guess. Comfortably above `CONFIDENCE_THRESHOLD`, so a document whose only
#: structure is confirmed prose headers is still declared structured rather
#: than flattened.
W_PROSE_HEADER_CONFIRMED = 0.8

#: Below this, the tree is discarded and the body is emitted flat.
CONFIDENCE_THRESHOLD = 0.5

#: A document does not have a *structure* on the strength of one heading. Fewer
#: than this many sections and the mean score is damped towards zero.
MIN_SECTIONS_FOR_FULL_CONFIDENCE = 3


@dataclass(frozen=True)
class DocSignals:
    """What the inference saw, and what it threw away.

    ``rejected`` is not diagnostics padding: Cycle 4b's telemetry has to explain
    why a document routed the way it did, and "we found candidate labels and
    refused them, for these reasons" is the explanation. A rule whose rejections
    are invisible cannot be audited (plan invariant #10).
    """

    n_blocks: int = 0
    n_sections: int = 0
    coverage: float = 0.0
    label_kinds: tuple[str, ...] = ()
    style_headings: int = 0
    rejected: tuple[str, ...] = ()
    confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "n_blocks": self.n_blocks,
            "n_sections": self.n_sections,
            "coverage": round(self.coverage, 4),
            "label_kinds": list(self.label_kinds),
            "style_headings": self.style_headings,
            "rejected": list(self.rejected),
            "confidence": round(self.confidence, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "DocSignals":
        if not data:
            return cls()
        return cls(
            n_blocks=int(data.get("n_blocks", 0)),
            n_sections=int(data.get("n_sections", 0)),
            coverage=float(data.get("coverage", 0.0)),
            label_kinds=tuple(data.get("label_kinds", ())),
            style_headings=int(data.get("style_headings", 0)),
            rejected=tuple(data.get("rejected", ())),
            confidence=float(data.get("confidence", 0.0)),
        )


def document_confidence(scores: list[float]) -> float:
    """Mean section score, damped when there are too few sections to be a shape.

    Damping is what makes a single lone label fall below the threshold while
    three of them in a validated series clear it comfortably. Without it, one
    accidental heading in a 400-paragraph document would score 0.9 and the
    document would be declared structured on the strength of one line.
    """
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    damping = min(1.0, len(scores) / MIN_SECTIONS_FOR_FULL_CONFIDENCE)
    return round(mean * damping, 4)
