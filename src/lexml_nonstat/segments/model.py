"""The :class:`Segment` record — plan §6.1.

A segment is one **citable** unit of a document: a section, a dispositivo, or a
front/back-matter region, together with the address a consumer uses to point at
it and the ancestry a consumer needs to read it in context.

Two address fields, not one, and the difference is the whole point
------------------------------------------------------------------

:attr:`Segment.urn` is the literal ``{document urn}!{id}`` of the artifact the
segment came from. It resolves — feed its ``id`` half to that document and you
get exactly one element back (asserted, not assumed).

:attr:`Segment.path` is the emitter-independent address: the tuple of
body-section ordinals from the root down. ``(1, 2)`` is "the second child of the
first body section", whichever emitter wrote the file.

Both exist because amendment **A-5b.4** measured that they cannot be the same
string. The flat ``generico`` emitter and the nested ``generico-aninhado``
emitter give the *same* section two different ids — the token differs (``agr``
vs ``agh``) and so does the top-level ordinal, because the flat emitter numbers
body sections in the same sequence as the front-matter regions. Plan §6.1 asks
for "segment URNs identical across emitters"; taken as string equality that is
false, and a test asserting it would have to be either wrong or vacuous. Taken
as *what a URN denotes* it is true, and :attr:`path` is that denotation made
explicit (amendment **A-7.2**).

So: cite with :attr:`urn` against the artifact you have; compare with
:attr:`path` across artifacts.

Text is own-text
----------------

:attr:`text` is the segment's **own** prose, excluding its descendants' — plan
§2.4's Rule B, end to end. Concatenating every segment of a document therefore
reproduces that document's words exactly once, which is what makes conservation
(§9.2) checkable over segment output rather than merely hoped for.
:attr:`full_text` is the cumulative form — the segment and everything under it,
in document order — which is what §6.2's ``descendant::p`` idiom produces and
what a retrieval consumer usually wants. Both come from Cycle 6's
:func:`~..render.common.leaf_texts`; this module is not a second text authority
(the amendment A-3.4 rule).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

__all__ = [
    "Segment",
    "segments_to_dicts",
    "segments_from_dicts",
]


@dataclass(frozen=True)
class Segment:
    """One citable unit of an emitted document."""

    #: ``{document urn}!{id}`` — resolvable *in the artifact this came from*.
    urn: str = ""
    #: The raw ``id`` attribute: ``pp1_agr4_agr1`` flat, ``pp1_agh1_agh1``
    #: nested, ``art1_cpt`` statutory.
    id: str = ""
    #: ``Agrupamento/@nome``, or the statutory element name lowercased.
    kind: str = "agrupamento"
    #: 1-based section depth. ``0`` for a front/back-matter region, which is
    #: not part of the body hierarchy at all.
    level: int = 0
    #: The rótulo as the source wrote it (``2.1 -``, ``Art. 1º``, ``I``).
    label: str | None = None
    #: True when :attr:`label` **repeats** an ancestor's rather than adding
    #: text — a ``Caput``'s rótulo, which plan §4.3 and the reference parser
    #: both write twice though the source said it once (amendment A-6.4).
    #: The label stays, because a reader wants the caption; conservation skips
    #: it, because the document did not say it twice.
    echoed_label: bool = False
    #: The nomeAgrupador — a heading, when the document gave one.
    heading: str | None = None
    #: Ancestor titles, root-first, **excluding** this segment.
    breadcrumb: tuple[str, ...] = ()
    #: This segment's own text only — Rule B.
    text: str = ""
    #: ``generico`` or ``norma``, read from the artifact (never re-inferred).
    route: str = "generico"
    #: Emitter-independent address: body-section ordinals, root-first. Empty
    #: for a region, which has no position in the body hierarchy.
    path: tuple[int, ...] = ()
    #: 0-based position among siblings, in **reading** order. On nested output
    #: this comes from ``Bloco nome="ordem"``, never from sibling position
    #: (plan §5.4 Constraint 1).
    order: int = 0
    #: The URN of the document this segment belongs to. An annex is a separate
    #: document (§2.9), so its segments carry ``…!anexo1``.
    document: str = ""
    #: Descendants' own texts, in document order. Kept so :attr:`full_text` is
    #: derivable from the record alone, without the tree it came from.
    descendant_texts: tuple[str, ...] = field(default=(), repr=False)

    @property
    def full_text(self) -> str:
        """This segment and everything under it, in document order.

        The cumulative reading, for consumers that want a self-contained
        passage. :attr:`text` stays own-text so the two are not the same
        number, which is exactly what the no-duplication test measures.
        """
        return " ".join(t for t in (self.text,) + self.descendant_texts if t)

    @property
    def depth(self) -> int:
        """How many ancestors this segment has."""
        return len(self.breadcrumb)

    @property
    def title(self) -> str:
        """Label and heading joined — the breadcrumb entry a child sees."""
        return " ".join(p for p in (self.label, self.heading) if p)

    @property
    def own_words(self) -> tuple[str, ...]:
        """Every word this segment contributes — the conservation currency.

        :attr:`label` and :attr:`heading` are source text the emitters write
        into the XML, so a conservation check over :attr:`text` alone would
        report every rótulo in the corpus as lost. An echoed label is excluded
        for the reason :attr:`echoed_label` records.
        """
        parts = (
            "" if self.echoed_label else (self.label or ""),
            self.heading or "",
            self.text,
        )
        return tuple(w for part in parts for w in part.split())

    @property
    def is_region(self) -> bool:
        """True for a front/back-matter region rather than a body section."""
        return not self.path

    def to_dict(self) -> dict[str, Any]:
        """The JSONL form. Empty optional fields are omitted, house style."""
        data: dict[str, Any] = {
            "urn": self.urn,
            "id": self.id,
            "kind": self.kind,
            "level": self.level,
        }
        if self.label is not None:
            data["label"] = self.label
        if self.echoed_label:
            data["echoed_label"] = True
        if self.heading is not None:
            data["heading"] = self.heading
        if self.breadcrumb:
            data["breadcrumb"] = list(self.breadcrumb)
        data["text"] = self.text
        data["route"] = self.route
        if self.path:
            data["path"] = list(self.path)
        data["order"] = self.order
        if self.document:
            data["document"] = self.document
        if self.descendant_texts:
            data["descendant_texts"] = list(self.descendant_texts)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Segment":
        return cls(
            urn=data.get("urn", ""),
            id=data.get("id", ""),
            kind=data.get("kind", "agrupamento"),
            level=data.get("level", 0),
            label=data.get("label"),
            echoed_label=data.get("echoed_label", False),
            heading=data.get("heading"),
            breadcrumb=tuple(data.get("breadcrumb", ())),
            text=data.get("text", ""),
            route=data.get("route", "generico"),
            path=tuple(data.get("path", ())),
            order=data.get("order", 0),
            document=data.get("document", ""),
            descendant_texts=tuple(data.get("descendant_texts", ())),
        )

    def to_json(self) -> str:
        """One JSONL line — no trailing newline, the writer adds it."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)


def segments_to_dicts(segments: Iterable[Segment]) -> list[dict[str, Any]]:
    return [s.to_dict() for s in segments]


def segments_from_dicts(data: Iterable[dict[str, Any]]) -> tuple[Segment, ...]:
    return tuple(Segment.from_dict(d) for d in data)
