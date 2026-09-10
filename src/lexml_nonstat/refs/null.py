"""The linker that never resolves — and the default everywhere.

A-L.1 makes ``NullLinker`` the default in the package, the CLI and the whole
regression suite, for the same reason §7.3 constraint 7 makes ``--referee=none``
the pinned setting: an external process must never enter a test run unasked.
Invariant #4 then makes output deterministic by construction, and the 125
goldens delivered by Cycles 1–8d keep rendering byte-identically because the
renderer they exercise is handed no references at all.

It returns ``()`` rather than raising, so it is a drop-in for a real linker and
the no-references path — the one every existing golden depends on — is
exercised on every test run.

``enabled = False`` mirrors :class:`~..referee.null.NullReferee`: a caller that
keeps counters can skip an inert linker entirely instead of recording fifteen
samples' worth of lookups the default configuration never intended to make.
"""

from __future__ import annotations

from .protocol import DEFAULT_CONTEXT_URN, Reference

__all__ = ["NullLinker"]


class NullLinker:
    """Resolves nothing. No subprocess, no cache, no state."""

    name = "none"

    #: An inert linker is not consulted at all.
    enabled = False

    def find_refs(
        self, text: str, context_urn: str = DEFAULT_CONTEXT_URN
    ) -> tuple[Reference, ...]:
        return ()

    def close(self) -> None:
        """Nothing to close. Present so callers need not ask what they hold."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "NullLinker()"
