"""The linker contract, and the one context URN this corpus can actually use.

Plan §18 (A-L.1) is precise about the role, and it mirrors the referee's: the
linker **resolves a citation to a URN**; it never parses documents, never
decides structure, and never generates XML. Deterministic rules remain the
whole of the pipeline, and a document renders identically whether or not a
linker was configured — the references are additive decoration over text that
was already there.

Two things live here and nothing else: the answer shape, and the protocol.

**A reference is a character span, not a run.** A citation crosses formatting
boundaries — ``Lei nº **7.713**`` is three runs and one citation — so
:class:`~..ingest.Inline` is the wrong unit. A :class:`Reference` addresses
``Para.text``, the concatenation of the paragraph's runs, and the renderer
splits runs at the span boundaries (A-L.3). That is also what keeps references
out of the model: they are computed at render time, so the ``styled``,
``hierarchy``, ``metadata``, ``segment`` and ``routing`` goldens cannot move.

**``find_refs`` never raises.** Every failure mode — no binary, a timeout, a
dead co-process, output that does not parse — comes back as an empty tuple.
This is :class:`~..referee.protocol.Verdict`'s abstention rule transposed to a
different question: a linker outage degrades quality, never availability. The
suite's default is :class:`~.null.NullLinker`, so the fail-safe path is
exercised on every test run rather than only in the tests written for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "DEFAULT_CONTEXT_URN",
    "Linker",
    "Reference",
]

#: The ``--contexto`` URN passed to the linker, always (A-L.9).
#:
#: It is the reference parser's own default (`FECmdLine.scala:114`), and A-L.8
#: named it as the *fallback* for the case where our own URNs are rejected.
#: Cycle 8e measured which case that is, and the answer promoted the fallback
#: to the only usable value:
#:
#: * a non-statutory **type** token — ``parecer``, ``ato.declaratorio``,
#:   ``portaria`` — is accepted, and links normally;
#: * A-2.3's ``0000`` year **sentinel** is accepted, and links normally;
#: * a non-``federal`` **authority** — ``ministerio.fazenda``,
#:   ``superior.tribunal.justica``, or any ``;``-joined pair — makes the linker
#:   return the input **unchanged**, silently, resolving nothing.
#:
#: Every one of the 15 samples carries such an authority. So passing a
#: document's own URN as context would resolve zero references on the entire
#: corpus while looking exactly like a document that cites nothing — the worst
#: shape a failure can take. ``find_refs`` keeps ``context_urn`` a parameter so
#: a linker that later learns these authorities needs no new API, but the
#: callers in this package all pass this constant.
DEFAULT_CONTEXT_URN = "urn:lex:br:federal:lei:2000-01-01;1"


@dataclass(frozen=True, order=True)
class Reference:
    """One resolved citation: a character span of ``Para.text`` and its URN.

    Ordered by ``(start, end, urn, text)`` so overlapping spans resolve
    deterministically without a key function at every call site — invariant #4
    is not a thing to re-derive per module.

    ``text`` is the source's own spelling of the norm, kept verbatim. That
    matches :mod:`~..hierarchy.quotation`'s rule, which already refuses to
    normalise a designation because "a document's own spelling of a law is the
    citable fact" — the URN is what gets normalised, and it travels beside the
    text rather than replacing it.
    """

    start: int
    end: int
    urn: str
    text: str = ""

    @property
    def is_empty(self) -> bool:
        return self.end <= self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "urn": self.urn,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reference":
        return cls(
            start=int(data.get("start", 0)),
            end=int(data.get("end", 0)),
            urn=str(data.get("urn", "") or ""),
            text=str(data.get("text", "") or ""),
        )


@runtime_checkable
class Linker(Protocol):
    """A-L.1's protocol. One question, no more.

    Implementations are free to be slow, cached, absent or backed by a Haskell
    co-process; they are not free to fail.
    """

    name: str

    def find_refs(
        self, text: str, context_urn: str = DEFAULT_CONTEXT_URN
    ) -> tuple[Reference, ...]:
        """Every citation in ``text``, as spans over ``text`` itself.

        Returns ``()`` when nothing was found **and** when anything went wrong;
        the two are deliberately indistinguishable to a caller, because a
        renderer has the same job either way. A backend that wants the
        difference recorded puts it in its own diagnostics, not in this answer.
        """
