"""Routing — is this document articulated, or is it not? (plan §4)

    from lexml_nonstat.routing import assess_viability
    verdict = assess_viability(read_docx(path))
    verdict.route          # "norma" | "generico"
    verdict.blockers       # why, in words

Three modules:

===============  =========================================================
:mod:`.genre`    genre priors — §2.7's "priors, not rules"
:mod:`.coverage` the article census and the coverage gate, read off Cycle 4
:mod:`.viability` the verdict, its four gates and its blockers
===============  =========================================================

§4.4 is the measure of success and it is a strange one: **14 of the 15 samples
route to `generico`**. This package earns its place by refusing, not by
finding — `port_mf_277` is the only document in the corpus that may be
published as an articulated `Norma`, and the other fourteen include two
opinions whose 30 combined `Art.` are quotations of statutes they do not enact.
"""

from .coverage import (
    COVERAGE_MIN,
    MIN_OWN_ARTICLES,
    ArticleCensus,
    articulation_coverage,
    census,
    quotation_confidence,
)
from .genre import DEFAULT_PRIOR, PRIORS, GenrePrior, genre_prior
from .viability import (
    BLOCKER_ALL_ARTICLES_QUOTED,
    BLOCKER_CODES,
    BLOCKER_LOW_COVERAGE,
    BLOCKER_NESTED_UNAVAILABLE,
    BLOCKER_NON_MONOTONIC,
    BLOCKER_NO_ARTICLES,
    BLOCKER_TOP_LEVEL_TABLE,
    EMITTERS,
    ROUTES,
    Blocker,
    StatutoryViability,
    assess_viability,
)

__all__ = [
    "BLOCKER_ALL_ARTICLES_QUOTED",
    "BLOCKER_CODES",
    "BLOCKER_LOW_COVERAGE",
    "BLOCKER_NESTED_UNAVAILABLE",
    "BLOCKER_NON_MONOTONIC",
    "BLOCKER_NO_ARTICLES",
    "BLOCKER_TOP_LEVEL_TABLE",
    "COVERAGE_MIN",
    "DEFAULT_PRIOR",
    "EMITTERS",
    "MIN_OWN_ARTICLES",
    "PRIORS",
    "ROUTES",
    "ArticleCensus",
    "Blocker",
    "GenrePrior",
    "StatutoryViability",
    "articulation_coverage",
    "assess_viability",
    "census",
    "genre_prior",
    "quotation_confidence",
]
