"""The article census and the coverage gate — read off Cycle 4, never recomputed.

Cycle 4's report is explicit that this package "must not become a second source
of truth for the same measurements", and it is right to be: the quotation guard
had to census the articles, detect the quote bands and test the series for
monotonicity in order to do its own job, and a second implementation that
disagreed with the first would be a bug nobody could see. So every function
here takes a :class:`~lexml_nonstat.hierarchy.QuotationAnalysis` and *reads* it.

What this module adds is the arithmetic Cycle 4 had no reason to do:

**own = found − quoted.** The number the route turns on. `parecer_93` has 25
articles and 0 own; `port_mf_277` has 2 and 2.

**Coverage.** §4.2's gate — "route to `norma` only when articulation covers
most of the body" — measured over the body span *after the annex split*, which
is what makes `port_mf_277` work: 2 articles against 138 document blocks is
1.4%, but against its 2-block body it is 100%, and the 132-block `ANEXO ÚNICO`
becomes a sibling document instead of a preamble.

**Per-article confidence.** Which quotation verdicts the rules were sure of, so
the referee is asked about the two or three that matter rather than all thirty.
The confidences are attributed from Cycle 4's own cues; nothing is re-decided.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..hierarchy.labels import ARTICLE_RE
from ..hierarchy.quotation import QuotationAnalysis, opens_with_quote

__all__ = [
    "ArticleCensus",
    "COVERAGE_MIN",
    "MIN_OWN_ARTICLES",
    "articulation_coverage",
    "census",
    "quotation_confidence",
]

#: §4.2: articulation must cover most of the body. `port_mf_277` scores 1.0
#: after the annex split; every other sample scores 0.0, so the corpus does not
#: pin this value — it is set where "most" stops being defensible.
COVERAGE_MIN = 0.6

#: Nothing to articulate below this.
MIN_OWN_ARTICLES = 1


@dataclass(frozen=True)
class ArticleCensus:
    """Which body paragraphs open an article, and which survived the guard."""

    found: tuple[int, ...] = ()
    quoted: tuple[int, ...] = ()
    own: tuple[int, ...] = ()
    values: tuple[int, ...] = ()
    monotonic: bool = False

    @property
    def n_found(self) -> int:
        return len(self.found)

    @property
    def n_quoted(self) -> int:
        return len(self.quoted)

    @property
    def n_own(self) -> int:
        return len(self.own)

    @property
    def all_quoted(self) -> bool:
        """Articles were found and the guard convicted every one of them."""
        return bool(self.found) and not self.own

    def to_dict(self) -> dict[str, object]:
        return {
            "found": list(self.found),
            "quoted": list(self.quoted),
            "own": list(self.own),
            "values": list(self.values),
            "monotonic": self.monotonic,
        }


def census(paras: Sequence, analysis: QuotationAnalysis) -> ArticleCensus:
    """Census the body's article paragraphs against Cycle 4's verdicts.

    ``values`` and ``monotonic`` are taken verbatim from ``analysis`` rather
    than recomputed — a test asserts the identity, so a future divergence
    fails loudly instead of drifting.
    """
    found: list[int] = []
    quoted: list[int] = []
    own: list[int] = []
    for para in paras:
        text = getattr(para, "text", "")
        if not text or not ARTICLE_RE.match(text.strip()):
            continue
        index = para.index
        found.append(index)
        (quoted if analysis.is_quoted(index) else own).append(index)

    return ArticleCensus(
        found=tuple(found),
        quoted=tuple(quoted),
        own=tuple(own),
        values=analysis.article_values,
        monotonic=analysis.article_monotonic,
    )


def articulation_coverage(
    census_: ArticleCensus, body_indices: Sequence[int]
) -> float:
    """Fraction of the body an articulation would actually account for.

    An article's extent runs from its own paragraph to the next one, so
    everything from the **first own article** to the end of the body is inside
    the articulation (caputs, parágrafos, incisos), and everything before it is
    preamble. Coverage is therefore the tail the articulation claims.

    This is the measurement §4.2 asks for and the reason `port_mf_277` is safe:
    two articles that begin at the body's first paragraph claim all of it.
    Two articles buried at 90% of a long body claim a tenth, and the gate
    refuses — which is the whole point, because that shape is a document
    *quoting* a statute at the end of an argument.
    """
    if not body_indices:
        return 0.0
    if not census_.own:
        return 0.0
    first = min(census_.own)
    inside = sum(1 for i in body_indices if i >= first)
    return round(inside / len(body_indices), 4)


def quotation_confidence(
    para, analysis: QuotationAnalysis
) -> tuple[float, str]:
    """How sure Cycle 4's guard was about one article paragraph, and why.

    Returns ``(confidence, reason)``. The reason is a human-readable rule name
    — plan invariant #10 wants a rejection to say which rule produced it, and
    a decision log full of bare numbers explains nothing.

    The scale is attributed from the cues Cycle 4 recorded, in the order of how
    much the *document* committed to the claim — the same principle
    :mod:`lexml_nonstat.hierarchy.evidence` scores headings by:

    ============================================  ====  =========
    cue                                           conf  flagged?
    ============================================  ====  =========
    in the quote band (a structural declaration)  0.90  no
    band plus a second cue                        0.95  no
    an *omissis* run (never an original enactment) 0.85  no
    an opening quotation mark                     0.80  no
    a citation antecedent alone                   0.55  **yes**
    only the excerpt-run extension                0.50  **yes**
    acquitted, series monotonic                   0.90  no
    acquitted, series not monotonic               0.60  no
    ============================================  ====  =========

    The two flagged rows are exactly §2.6's residual case: on `par_cosit_26`
    they are three paragraphs, and on `parecer_93` — 415 paragraphs, 25 quoted
    articles — they are one. The band carries the rest.
    """
    index = para.index
    text = (getattr(para, "text", "") or "").strip()

    if not analysis.is_quoted(index):
        if analysis.article_monotonic:
            return 0.90, "acquitted: article series is monotonic from the start"
        return 0.60, "acquitted: no quotation cue, but the series is not monotonic"

    in_band = analysis.bands.contains(para)
    omissis = index in analysis.omissis
    antecedent = index in analysis.citation_antecedent
    quote_mark = opens_with_quote(text)

    if in_band:
        if omissis or quote_mark or antecedent:
            return 0.95, "convicted: in the quote band, with a corroborating cue"
        return 0.90, "convicted: in the document's quote band"
    if omissis:
        return 0.85, "convicted: omissis run — an excerpt's elision, never an enactment"
    if quote_mark:
        return 0.80, "convicted: opens with a quotation mark"
    if antecedent:
        return 0.55, (
            "convicted only by a citation antecedent — half an argument (§2.6), "
            "no indent band in this document"
        )
    return 0.50, (
        "convicted only by excerpt-run extension from an earlier quoted article; "
        "no cue on this paragraph itself"
    )
