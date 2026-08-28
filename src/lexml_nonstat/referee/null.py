"""The referee that never answers — and the default everywhere.

§7.3 constraint 7 makes ``--referee=none`` the pinned setting for the whole
regression suite, and §9.3 explains why: networked LLM calls must never enter
it. Invariant #4 then makes output deterministic by construction.

``NullReferee`` abstains rather than raising, so it is a drop-in for a real one
and the fail-safe path gets exercised on every test run rather than only in the
tests written for it.

It also sets ``enabled = False``, and :func:`~.adjudicate.adjudicate` skips a
disabled referee entirely instead of asking it and recording an abstention.
That is what makes the plan's first referee test — *NullReferee ⇒ byte-identical
output to referee-disabled* — true of the **whole verdict**, bookkeeping fields
included, rather than only of the route. It also keeps the abstention count in
``--decisions-report`` meaning what it should: a referee that was genuinely
asked and genuinely failed, never the fifteen samples' worth of questions the
default configuration never intended to ask.
"""

from __future__ import annotations

from .protocol import Verdict

__all__ = ["NullReferee"]

_REASON = "null referee: no adjudication performed"


class NullReferee:
    """Abstains on every question. No network, no cache, no state."""

    name = "none"

    #: Read by `adjudicate`: an inert referee is not consulted at all.
    enabled = False

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        return Verdict.abstain(_REASON)

    def is_heading(self, para: str, ctx: str) -> Verdict:
        return Verdict.abstain(_REASON)

    def section_kind(self, label: str, heading: str) -> Verdict:
        return Verdict.abstain(_REASON)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "NullReferee()"
