"""The structural half of the document model — plan §3.1.

Cycle 2 delivered the metadata half; this is the rest: the content nodes a
document is made of, and the recursive ``Section`` that LexML's shipped schemas
cannot express but every non-statutory document has.

These types are **rendering-agnostic on purpose**. Cycle 5 writes them out flat,
Cycle 5b writes the same objects out nested, and Cycle 6 writes an annex as a
sibling document — none of which changes a line here. Plan §11 predicted that
payoff and the 2026-08-28 schema revision collected it: adopting the
maintainers' recursive ``AgrupamentoHierarquico`` cost one emitter and touched
no model type.

``Inline`` is **not** re-declared. Cycle 1's is field-for-field identical to
§3.1's, and a second frozen record for the same thing is two sources of truth
for one fact (spec decision D-2).

Every node keeps ``source_indices`` — the ``StyledDoc`` block indices it came
from. That is what makes conservation (plan §9.2, invariant #2) checkable by
arithmetic rather than by string comparison, exactly as Cycle 3's spans do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

from ..ingest import Inline

__all__ = [
    "Evidence",
    "ListItem",
    "ListNode",
    "Node",
    "PARA_KINDS",
    "Para",
    "SECTION_KINDS",
    "Section",
    "Table",
    "inlines_from_dict",
    "inlines_to_dict",
]

#: The ratified ``Para.kind`` vocabulary (plan §3.1).
PARA_KINDS = frozenset({"prose", "quote", "citation", "field", "omissis"})

#: The ratified ``Section.kind`` vocabulary.
#:
#: Assigned from label form and depth (spec R-3), and consumed by Cycle 5 as
#: ``Agrupamento/@nome`` (plan §5.1). ``agrupamento`` is the honest default for
#: a section that style evidence found but no label named.
SECTION_KINDS = frozenset(
    {
        "parte",
        "livro",
        "titulo",
        "capitulo",
        "secao",
        "subsecao",
        "item",
        "inciso",
        "alinea",
        "tema",
        "agrupamento",
    }
)


def inlines_to_dict(inlines: tuple[Inline, ...]) -> list[dict[str, Any]]:
    return [i.to_dict() for i in inlines]


def inlines_from_dict(data: Any) -> tuple[Inline, ...]:
    return tuple(Inline.from_dict(i) for i in data or ())


@dataclass(frozen=True)
class Evidence:
    """Why a section is believed to exist, and how strongly.

    Kept on the node rather than in a side table because Cycle 4b's telemetry
    and the referee both need to explain a decision after the fact, and a
    decision whose reasons were discarded cannot be explained.
    """

    signals: tuple[str, ...] = ()
    score: float = 0.0

    def with_signal(self, name: str, weight: float) -> "Evidence":
        """A copy carrying one more signal; the score takes the strongest."""
        if name in self.signals:
            return Evidence(self.signals, max(self.score, weight))
        return Evidence(self.signals + (name,), max(self.score, weight))

    def to_dict(self) -> dict[str, Any]:
        return {"signals": list(self.signals), "score": round(self.score, 4)}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Evidence":
        if not data:
            return cls()
        return cls(
            signals=tuple(data.get("signals", ())),
            score=float(data.get("score", 0.0)),
        )


@dataclass(frozen=True)
class Para:
    """One paragraph of content.

    ``kind`` is the quotation guard's verdict (Cycle 4's ``quotation.py``).
    A quoted paragraph stays in the tree — marking it is how the guard refuses
    to *promote* it, not a licence to drop it (spec decision D-5).
    """

    inlines: tuple[Inline, ...] = ()
    kind: str = "prose"
    indent: int = 0
    source_indices: tuple[int, ...] = ()

    @property
    def text(self) -> str:
        return "".join(i.text for i in self.inlines)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    @property
    def all_source_indices(self) -> tuple[int, ...]:
        """Uniform with the composite nodes, so conservation can walk any node
        without asking what it is."""
        return self.source_indices

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"node": "para", "inlines": inlines_to_dict(self.inlines)}
        if self.kind != "prose":
            data["kind"] = self.kind
        if self.indent:
            data["indent"] = self.indent
        if self.source_indices:
            data["source_indices"] = list(self.source_indices)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Para":
        return cls(
            inlines=inlines_from_dict(data.get("inlines")),
            kind=data.get("kind", "prose"),
            indent=data.get("indent", 0),
            source_indices=tuple(data.get("source_indices", ())),
        )


@dataclass(frozen=True)
class ListItem:
    """One ``<li>``. ``children`` holds nested lists and continuation prose."""

    inlines: tuple[Inline, ...] = ()
    children: tuple[Union["ListNode", Para], ...] = ()
    source_indices: tuple[int, ...] = ()

    @property
    def text(self) -> str:
        return "".join(i.text for i in self.inlines)

    @property
    def all_source_indices(self) -> tuple[int, ...]:
        out = list(self.source_indices)
        for child in self.children:
            out.extend(child.all_source_indices)
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"node": "li", "inlines": inlines_to_dict(self.inlines)}
        if self.children:
            data["children"] = [c.to_dict() for c in self.children]
        if self.source_indices:
            data["source_indices"] = list(self.source_indices)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ListItem":
        return cls(
            inlines=inlines_from_dict(data.get("inlines")),
            children=tuple(node_from_dict(c) for c in data.get("children", ())),
            source_indices=tuple(data.get("source_indices", ())),
        )


@dataclass(frozen=True)
class ListNode:
    """A list. Nests natively in LexML (plan §2.2), so it needs no flattening.

    ``ordered`` is inferred from an explicit enumerator in the item text.
    Word's ``numFmt`` is deliberately not read: capturing it means a new
    ``StyledPara`` field, which rewrites all 15 ``styled`` goldens — a major
    change to Cycle 1's delivered output for a signal Cycle 5 can pay for if it
    turns out to need it (spec decision D-4).
    """

    ordered: bool = False
    items: tuple[ListItem, ...] = ()

    @property
    def all_source_indices(self) -> tuple[int, ...]:
        out: list[int] = []
        for item in self.items:
            out.extend(item.all_source_indices)
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": "list",
            "ordered": self.ordered,
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ListNode":
        return cls(
            ordered=data.get("ordered", False),
            items=tuple(ListItem.from_dict(i) for i in data.get("items", ())),
        )


@dataclass(frozen=True)
class Table:
    """Rows of cells of **inline** content only — LexML's ``<td>`` takes no
    ``<p>`` (plan §2.2), so the restriction is modelled here rather than being
    discovered by the emitter."""

    rows: tuple[tuple[tuple[Inline, ...], ...], ...] = ()
    source_indices: tuple[int, ...] = ()

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.rows), max((len(r) for r in self.rows), default=0))

    @property
    def all_source_indices(self) -> tuple[int, ...]:
        return self.source_indices

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": "table",
            "rows": [[inlines_to_dict(c) for c in row] for row in self.rows],
            "source_indices": list(self.source_indices),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Table":
        return cls(
            rows=tuple(
                tuple(inlines_from_dict(c) for c in row) for row in data.get("rows", ())
            ),
            source_indices=tuple(data.get("source_indices", ())),
        )


@dataclass(frozen=True)
class Section:
    """The recursive hierarchy LexML's shipped schemas lack.

    ``label`` is the rótulo as it appears (``2.1``, ``I``, ``CAPÍTULO II``),
    ``heading`` the nomeAgrupador when the paragraph's remainder reads as a
    heading rather than as prose, and ``level`` the unified 1-based depth.
    """

    label: str | None = None
    heading: str | None = None
    level: int = 1
    kind: str = "agrupamento"
    body: tuple["Node", ...] = ()
    children: tuple["Section", ...] = ()
    evidence: Evidence = field(default_factory=Evidence)
    source_indices: tuple[int, ...] = ()

    @property
    def all_source_indices(self) -> tuple[int, ...]:
        """Every source block under this section, descendants included."""
        out = list(self.source_indices)
        for node in self.body:
            out.extend(node.all_source_indices)
        for child in self.children:
            out.extend(child.all_source_indices)
        return tuple(out)

    @property
    def title(self) -> str:
        """Label and heading joined, for logs and reports."""
        return " ".join(p for p in (self.label, self.heading) if p)

    def walk(self):
        """This section and every descendant, depth-first, document order."""
        yield self
        for child in self.children:
            yield from child.walk()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"node": "section", "level": self.level, "kind": self.kind}
        if self.label is not None:
            data["label"] = self.label
        if self.heading is not None:
            data["heading"] = self.heading
        if self.source_indices:
            data["source_indices"] = list(self.source_indices)
        data["evidence"] = self.evidence.to_dict()
        if self.body:
            data["body"] = [n.to_dict() for n in self.body]
        if self.children:
            data["children"] = [c.to_dict() for c in self.children]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Section":
        return cls(
            label=data.get("label"),
            heading=data.get("heading"),
            level=data.get("level", 1),
            kind=data.get("kind", "agrupamento"),
            body=tuple(node_from_dict(n) for n in data.get("body", ())),
            children=tuple(Section.from_dict(c) for c in data.get("children", ())),
            evidence=Evidence.from_dict(data.get("evidence")),
            source_indices=tuple(data.get("source_indices", ())),
        )


#: Anything that can sit in a ``Section.body``.
Node = Union[Para, ListNode, Table]

_NODE_TYPES = {
    "para": Para,
    "list": ListNode,
    "li": ListItem,
    "table": Table,
    "section": Section,
}


def node_from_dict(data: dict[str, Any]):
    """Rebuild any node from its dict form, dispatching on ``node``."""
    try:
        cls = _NODE_TYPES[data["node"]]
    except KeyError:
        raise ValueError(f"unknown node kind {data.get('node')!r}") from None
    return cls.from_dict(data)
