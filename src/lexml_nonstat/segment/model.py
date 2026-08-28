"""The segmentation model: which source blocks are front matter, body, or back.

A segmentation never copies text. Every part is a :class:`Span` of indices into
the ``StyledDoc`` it was computed from, so the document remains the single
source of truth and the conservation invariant (plan §9.2) is checkable by
arithmetic rather than by string comparison.

The model keeps *evidence*, not conclusions, following the same rule as
:mod:`..ingest.styled`. ``BackMatter`` records **every** signature block it
finds, in document order, because ``parecer_93`` carries two — the parecer's
own and an appended ``DESPACHO DO CONSULTOR-GERAL`` with its own header, date
and signer. Deciding that one of them is "the" signature is a rendering
question, and rendering is Cycles 5 and 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from ..model import ProprietaryField, UrnDate

__all__ = [
    "Annex",
    "BackMatter",
    "FrontMatter",
    "Segmentation",
    "Signature",
    "Span",
]


@dataclass(frozen=True)
class Span:
    """A contiguous run of source blocks, ``start``..``end`` inclusive.

    Inclusive rather than half-open because every boundary in this cycle is
    discovered as "the block that is the ementa", not "the block after it", and
    an off-by-one in a segmentation silently moves text between parts.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"empty span: {self.start}..{self.end}")

    @property
    def indices(self) -> tuple[int, ...]:
        return tuple(range(self.start, self.end + 1))

    def __contains__(self, index: int) -> bool:
        return self.start <= index <= self.end

    def __len__(self) -> int:
        return self.end - self.start + 1

    def __iter__(self) -> Iterator[int]:
        return iter(self.indices)

    def text(self, doc: Any) -> str:
        """The span's text, one block per line, blanks dropped."""
        by_index = {b.index: b for b in doc.blocks}
        lines = []
        for i in self.indices:
            block = by_index.get(i)
            if block is None or not hasattr(block, "text"):
                continue
            if block.text.strip():
                lines.append(block.text.strip())
        return "\n".join(lines)

    def to_dict(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "Span":
        return cls(start=data["start"], end=data["end"])


def _span_or_none(data: dict[str, Any] | None) -> Span | None:
    return Span.from_dict(data) if data else None


@dataclass(frozen=True)
class FrontMatter:
    """Epigraph, ementa, preamble and enacting formula, as spans.

    ``fields`` is Cycle 2's allowlist-gated ``ProprietaryField`` capture,
    re-exported rather than recomputed: amendment A-2.2 settled which labelled
    lines count as metadata, and a second implementation here would be a
    competing source of truth (amendment A-3.4).
    """

    epigraph: Span | None = None
    ementa: Span | None = None
    preamble: Span | None = None
    enacting_formula: Span | None = None
    fields: tuple[ProprietaryField, ...] = ()

    @property
    def parts(self) -> tuple[Span, ...]:
        """Every present span, in document order."""
        present = [
            s
            for s in (self.epigraph, self.ementa, self.preamble, self.enacting_formula)
            if s is not None
        ]
        return tuple(sorted(present, key=lambda s: s.start))

    @property
    def span(self) -> Span | None:
        """The contiguous hull of the front matter, or ``None`` when empty.

        The *hull*, not the union of the parts: front matter is a contiguous
        region of the document, and the blocks between its parts belong to it.
        ``parecer_93`` is the case that settles this — its epigraph is block 3,
        behind a portal date stamp and a three-line institutional banner, and
        its ementa is block 9, behind ``NUP:``, ``INTERESSADOS:`` and
        ``ASSUNTO:``. Those blocks are front matter by position and by content;
        leaving them between the parts would strand them in no part at all and
        break text conservation (plan §9.2).
        """
        parts = self.parts
        if not parts:
            return None
        return Span(parts[0].start, max(p.end for p in parts))

    def hull(self, first_index: int = 0) -> Span | None:
        """The front matter's span extended back to the document's start."""
        span = self.span
        if span is None:
            return None
        return Span(min(span.start, first_index), span.end)

    @property
    def is_empty(self) -> bool:
        return not self.parts

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name in ("epigraph", "ementa", "preamble", "enacting_formula"):
            value = getattr(self, name)
            if value is not None:
                data[name] = value.to_dict()
        if self.fields:
            data["fields"] = [f.to_dict() for f in self.fields]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrontMatter":
        return cls(
            epigraph=_span_or_none(data.get("epigraph")),
            ementa=_span_or_none(data.get("ementa")),
            preamble=_span_or_none(data.get("preamble")),
            enacting_formula=_span_or_none(data.get("enacting_formula")),
            fields=tuple(
                ProprietaryField.from_dict(f) for f in data.get("fields", ())
            ),
        )


@dataclass(frozen=True)
class Signature:
    """One signature block: a person, optionally their office and a closing date.

    ``cargo`` and ``local_date`` are optional because they genuinely are:
    ``ad_srf_22`` signs with a bare ``EVERARDO MACIEL`` and no office line, and
    most samples carry no closing date at all.
    """

    name: str
    cargo: str | None = None
    local_date: str | None = None
    span: Span = field(default_factory=lambda: Span(0, 0))
    date: UrnDate | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "span": self.span.to_dict()}
        if self.cargo is not None:
            data["cargo"] = self.cargo
        if self.local_date is not None:
            data["local_date"] = self.local_date
        if self.date is not None:
            data["date"] = self.date.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Signature":
        raw_date = data.get("date")
        return cls(
            name=data["name"],
            cargo=data.get("cargo"),
            local_date=data.get("local_date"),
            span=Span.from_dict(data["span"]),
            date=UrnDate.from_dict(raw_date) if raw_date else None,
        )


@dataclass(frozen=True)
class BackMatter:
    """Closing matter: every signature block found, in document order.

    ``trailing`` extends the region past the last signature over notes that
    close the document — ``par_cosit_26``'s ``Nota Normas:`` disclaimer,
    ``port_mf_454``'s "originally published without an ementa" note. They are
    back matter by position, and without them the region would leave blocks in
    no part at all.
    """

    signatures: tuple[Signature, ...] = ()
    local_date: Span | None = None
    trailing: Span | None = None

    @property
    def is_empty(self) -> bool:
        return not self.signatures and self.local_date is None

    @property
    def span(self) -> Span | None:
        """The hull of the closing date and every signature."""
        starts = [s.span.start for s in self.signatures]
        ends = [s.span.end for s in self.signatures]
        if self.local_date is not None:
            starts.append(self.local_date.start)
            ends.append(self.local_date.end)
        if self.trailing is not None:
            starts.append(self.trailing.start)
            ends.append(self.trailing.end)
        if not starts:
            return None
        return Span(min(starts), max(ends))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.signatures:
            data["signatures"] = [s.to_dict() for s in self.signatures]
        if self.local_date is not None:
            data["local_date"] = self.local_date.to_dict()
        if self.trailing is not None:
            data["trailing"] = self.trailing.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackMatter":
        return cls(
            signatures=tuple(
                Signature.from_dict(s) for s in data.get("signatures", ())
            ),
            local_date=_span_or_none(data.get("local_date")),
            trailing=_span_or_none(data.get("trailing")),
        )


@dataclass(frozen=True)
class Annex:
    """One annex, separated from the primary document.

    ``ordinal`` is 1-based and feeds the ``!anexoN`` URN fragment convention
    that Cycle 2's :meth:`Metadata.urn_with_fragment` already implements and
    Cycle 6 will use to emit sibling annex documents.
    """

    label: str
    span: Span
    ordinal: int = 1

    @property
    def fragment(self) -> str:
        return f"anexo{self.ordinal}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "span": self.span.to_dict(),
            "ordinal": self.ordinal,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Annex":
        return cls(
            label=data["label"],
            span=Span.from_dict(data["span"]),
            ordinal=data.get("ordinal", 1),
        )


@dataclass(frozen=True)
class Segmentation:
    """A whole document divided into front matter, body, back matter, annexes.

    ``body`` may be ``None`` for a document that is nothing but front matter
    (``sumula_carf_42`` comes close), and every part may be absent at once for
    a document like ``CARNE_LEAO`` that carries no front or back matter at all.
    Tolerance for absent matter is a deliverable of this cycle, not an edge case.
    """

    front: FrontMatter = field(default_factory=FrontMatter)
    body: Span | None = None
    back: BackMatter = field(default_factory=BackMatter)
    annexes: tuple[Annex, ...] = ()
    source: str | None = None
    profile: str | None = None
    #: The document's first block index, so ``covered`` can extend the front
    #: matter's hull back to the start of the document.
    first_index: int = 0

    @property
    def covered(self) -> frozenset[int]:
        """Every block index assigned to some part.

        The conservation invariant at segmentation level: no index may appear
        twice, and every non-empty block must appear once.
        """
        out: set[int] = set()
        front_hull = self.front.hull(self.first_index)
        if front_hull is not None:
            out.update(front_hull.indices)
        if self.body is not None:
            out.update(self.body.indices)
        back_span = self.back.span
        if back_span is not None:
            out.update(back_span.indices)
        for annex in self.annexes:
            out.update(annex.span.indices)
        return frozenset(out)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.source is not None:
            data["source"] = self.source
        if self.profile is not None:
            data["profile"] = self.profile
        if self.first_index:
            data["first_index"] = self.first_index
        front = self.front.to_dict()
        if front:
            data["front"] = front
        if self.body is not None:
            data["body"] = self.body.to_dict()
        back = self.back.to_dict()
        if back:
            data["back"] = back
        if self.annexes:
            data["annexes"] = [a.to_dict() for a in self.annexes]
        return data

    def to_json(self, *, indent: int = 2) -> str:
        """Golden-file form, matching :meth:`StyledDoc.to_json`'s conventions."""
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Segmentation":
        return cls(
            front=FrontMatter.from_dict(data.get("front", {})),
            body=_span_or_none(data.get("body")),
            back=BackMatter.from_dict(data.get("back", {})),
            annexes=tuple(Annex.from_dict(a) for a in data.get("annexes", ())),
            source=data.get("source"),
            profile=data.get("profile"),
            first_index=data.get("first_index", 0),
        )

    @classmethod
    def from_json(cls, text: str) -> "Segmentation":
        import json

        return cls.from_dict(json.loads(text))
