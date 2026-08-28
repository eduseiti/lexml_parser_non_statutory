"""Building the tree: assignments and blocks become ``Section``s and content.

Three jobs, in order.

**Content.** Every block in the span that is not a section header becomes a
``Para``, a ``ListNode`` or a ``Table``. Word lists are reconstructed from
``num_id``/``ilvl`` — contiguous runs of one ``num_id`` form a list, and ``ilvl``
gives the nesting, normalised so a document that starts at ``ilvl=1`` with no
``ilvl=0`` above it (``CARNE_LEAO`` blocks 76–86) does not produce a list with a
hole in it.

**Structure.** Assignments are threaded onto a depth stack; blocks between two
headers belong to the earlier one; blocks before the first header become the
tree's ``preamble``, which is how ``par_cosit_26``'s opening paragraphs survive
the fact that its ``1.`` sits in the front matter.

**Judgement.** If the fused evidence does not clear
:data:`~.evidence.CONFIDENCE_THRESHOLD`, the sections are thrown away and the
body is returned flat. That is plan invariant #8, and it is a deliberate
asymmetry: a flat document is complete and citable, while a fabricated section
is a falsehood that validates.

One thing this module does **not** do: turn `Art. 1º` into a `Section`.
Articulation is the ``norma`` route's shape (Cycles 4b and 6); on the generic
route an article is prose, which is what makes the plan's regression-critical
``parecer_93`` requirement — *all* its indented articles are content, never
structure — a property of the design rather than of a rule that could regress
(spec decision D-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..ingest import Inline, StyledDoc, StyledPara, StyledTable
from ..model.nodes import Evidence, ListItem, ListNode, Node, Para, Section, Table
from ..segment.model import Span
from .evidence import CONFIDENCE_THRESHOLD, DocSignals, document_confidence
from .labels import parse_label
from .quotation import QuotationAnalysis, analyse_quotation
from .unify import (
    Assignment,
    collect_candidates,
    demote_numbered_containers,
    detect_unit_series,
    unify_levels,
)

__all__ = [
    "AnnexHierarchy",
    "HierarchyTree",
    "build_tree",
    "split_inlines",
]


def split_inlines(inlines: Sequence[Inline], offset: int) -> tuple[Inline, ...]:
    """The inlines from character ``offset`` onwards, run boundaries respected.

    Splitting on characters rather than dropping the first run matters: a
    rótulo and the text after it are frequently one Word run, and a rótulo is
    frequently bold while its paragraph is not.
    """
    if offset <= 0:
        return tuple(inlines)
    remaining = offset
    out: list[Inline] = []
    for inline in inlines:
        if remaining >= len(inline.text):
            remaining -= len(inline.text)
            continue
        if remaining:
            out.append(
                Inline(
                    inline.text[remaining:],
                    inline.bold,
                    inline.italic,
                    inline.sup,
                    inline.sub,
                    inline.href,
                )
            )
            remaining = 0
            continue
        out.append(inline)
    return tuple(out)


def _para_node(para: StyledPara, analysis: QuotationAnalysis) -> Para:
    kind = "prose"
    if analysis.is_quoted(para.index):
        kind = "omissis" if para.index in analysis.omissis else "quote"
    elif para.index in analysis.omissis:
        kind = "omissis"
    return Para(
        inlines=tuple(para.inlines),
        kind=kind,
        indent=para.indent_effective,
        source_indices=(para.index,),
    )


def _table_node(table: StyledTable) -> Table:
    rows = tuple(
        tuple(
            tuple(
                inline
                for position, cell_para in enumerate(cell.paras)
                for inline in (
                    ((Inline(" "),) if position and cell_para.inlines else ())
                    + tuple(cell_para.inlines)
                )
            )
            for cell in row.cells
        )
        for row in table.rows
    )
    return Table(rows=rows, source_indices=(table.index,))


def _list_node(run: Sequence[StyledPara]) -> ListNode:
    """One Word list, nested by ``ilvl``.

    Levels are *ranked* rather than used raw. ``CARNE_LEAO`` has lists whose
    only level is ``ilvl=1``; taking that literally would build a list whose
    items all hang off a level that does not exist.

    The corpus has no contiguous multi-level Word list at all — every sample's
    lists are single-level — so nesting is exercised by a synthetic fixture
    rather than by a golden (amendment A-4.6). That is the same situation
    amendment A-1.3 met with NFC normalisation, and it is resolved the same
    way: the code is written for the general case and tested with a fixture
    that produces it, because a rule the corpus cannot reach is exactly the
    rule that silently rots.
    """
    levels = sorted({p.ilvl or 0 for p in run})
    rank = {level: position for position, level in enumerate(levels)}
    entries = [(rank[p.ilvl or 0], p) for p in run]

    ordered = False
    for _, para in entries:
        label = parse_label(para.text.strip())
        if label is not None and label.kind in {"numeric", "roman", "alpha", "compound"}:
            ordered = True
            break

    return ListNode(ordered=ordered, items=_items(entries, 0))


def _items(
    entries: Sequence[tuple[int, StyledPara]], depth: int
) -> tuple[ListItem, ...]:
    """Build the items at ``depth``, recursing into anything deeper.

    A run that opens deeper than its own base — which happens when Word records
    only the inner level — is clamped up rather than dropped. Losing an item to
    a malformed numbering definition would be a conservation failure, and a
    silent one.
    """
    out: list[ListItem] = []
    position = 0
    while position < len(entries):
        level, para = entries[position]
        if level > depth and not out:
            level = depth  # clamp: nothing above it to nest under
        if level > depth:
            end = position
            while end < len(entries) and entries[end][0] > depth:
                end += 1
            nested = ListNode(ordered=False, items=_items(entries[position:end], depth + 1))
            previous = out[-1]
            out[-1] = ListItem(
                previous.inlines, previous.children + (nested,), previous.source_indices
            )
            position = end
            continue
        out.append(ListItem(inlines=tuple(para.inlines), source_indices=(para.index,)))
        position += 1
    return tuple(out)


def _build_content(
    blocks: Sequence[StyledPara | StyledTable],
    analysis: QuotationAnalysis,
) -> tuple[Node, ...]:
    """Blocks → content nodes, with Word lists reassembled."""
    out: list[Node] = []
    run: list[StyledPara] = []
    run_id: str | None = None

    def flush() -> None:
        nonlocal run, run_id
        if run:
            out.append(_list_node(run) if len(run) > 1 else _para_node(run[0], analysis))
            run = []
            run_id = None

    for block in blocks:
        if isinstance(block, StyledTable):
            flush()
            out.append(_table_node(block))
            continue
        if block.is_empty:
            continue
        if block.num_id is not None:
            if run_id is not None and block.num_id != run_id:
                flush()
            run_id = block.num_id
            run.append(block)
            continue
        flush()
        out.append(_para_node(block, analysis))
    flush()
    return tuple(out)


@dataclass(frozen=True)
class HierarchyTree:
    """The inferred structure of one span of a document."""

    sections: tuple[Section, ...] = ()
    preamble: tuple[Node, ...] = ()
    confidence: float = 0.0
    flat: bool = True
    signals: DocSignals = field(default_factory=DocSignals)
    span: Span | None = None

    @property
    def is_empty(self) -> bool:
        return not self.sections and not self.preamble

    def walk(self):
        """Every section in the tree, depth-first, document order."""
        for section in self.sections:
            yield from section.walk()

    @property
    def section_indices(self) -> tuple[int, ...]:
        """Source indices of the section *headers*, in document order."""
        return tuple(i for s in self.walk() for i in s.source_indices)

    @property
    def content_indices(self) -> tuple[int, ...]:
        """Source indices claimed by content nodes, in document order."""
        out = [i for node in self.preamble for i in node.all_source_indices]
        for section in self.walk():
            for node in section.body:
                out.extend(node.all_source_indices)
        return tuple(out)

    @property
    def max_depth(self) -> int:
        return max((s.level for s in self.walk()), default=0)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "confidence": round(self.confidence, 4),
            "flat": self.flat,
            "signals": self.signals.to_dict(),
        }
        if self.span is not None:
            data["span"] = self.span.to_dict()
        if self.preamble:
            data["preamble"] = [n.to_dict() for n in self.preamble]
        data["sections"] = [s.to_dict() for s in self.sections]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "HierarchyTree":
        from ..model.nodes import node_from_dict

        span = data.get("span")
        return cls(
            sections=tuple(Section.from_dict(s) for s in data.get("sections", ())),
            preamble=tuple(node_from_dict(n) for n in data.get("preamble", ())),
            confidence=float(data.get("confidence", 0.0)),
            flat=bool(data.get("flat", True)),
            signals=DocSignals.from_dict(data.get("signals")),
            span=Span.from_dict(span) if span else None,
        )


@dataclass(frozen=True)
class AnnexHierarchy:
    """One annex's tree, carrying the fragment Cycle 2's URN builder wants."""

    label: str
    ordinal: int
    fragment: str
    tree: HierarchyTree

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "ordinal": self.ordinal,
            "fragment": self.fragment,
            "tree": self.tree.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "AnnexHierarchy":
        return cls(
            label=str(data["label"]),
            ordinal=int(data["ordinal"]),
            fragment=str(data["fragment"]),
            tree=HierarchyTree.from_dict(data["tree"]),
        )


def _assemble(
    assignments: Sequence[Assignment],
    blocks: Sequence[StyledPara | StyledTable],
    analysis: QuotationAnalysis,
) -> tuple[tuple[Section, ...], tuple[Node, ...]]:
    """Thread assignments onto a depth stack and hang the content off them."""
    by_index = {a.index: a for a in assignments}
    lookup = {b.index: b for b in blocks}

    roots: list[list[Section]] = [[]]
    stack: list[tuple[int, list[Section], list[Node], Assignment]] = []
    preamble_blocks: list[StyledPara | StyledTable] = []

    def close_to(depth: int) -> None:
        while stack and stack[-1][0] >= depth:
            _, children, body, assignment = stack.pop()
            section = _finish(assignment, body, children, lookup, analysis)
            (stack[-1][1] if stack else roots[0]).append(section)

    for block in blocks:
        assignment = by_index.get(block.index)
        if assignment is None:
            (stack[-1][2] if stack else preamble_blocks).append(block)
            continue
        close_to(assignment.depth)
        stack.append((assignment.depth, [], [], assignment))
    close_to(0)

    return tuple(roots[0]), _build_content(preamble_blocks, analysis)


def _finish(
    assignment: Assignment,
    body_blocks: list,
    children: list[Section],
    lookup: dict,
    analysis: QuotationAnalysis,
) -> Section:
    """Turn one assignment plus its blocks into a ``Section``.

    A label whose remainder is prose keeps that prose as the section's first
    paragraph — split at the rótulo, run boundaries intact — so the text stays
    exactly once in the tree and the rótulo is not repeated inside it.
    """
    body: list[Node] = []
    header = lookup.get(assignment.index)
    if (
        assignment.heading is None
        and assignment.label is not None
        and assignment.label.text.strip()
        and isinstance(header, StyledPara)
    ):
        text = header.text
        remainder = assignment.label.text.strip()
        offset = text.rfind(remainder)
        inlines = split_inlines(header.inlines, offset if offset >= 0 else 0)
        body.append(
            Para(
                inlines=inlines,
                kind="quote" if analysis.is_quoted(assignment.index) else "prose",
                indent=header.indent_effective,
                source_indices=(assignment.index,),
            )
        )
    body.extend(_build_content(body_blocks, analysis))

    return Section(
        label=assignment.label.raw if assignment.label is not None else None,
        heading=assignment.heading,
        level=assignment.depth,
        kind=assignment.kind,
        body=tuple(body),
        children=tuple(children),
        evidence=Evidence(signals=assignment.signals, score=assignment.score),
        source_indices=(assignment.index,),
    )


def build_tree(
    blocks: Sequence[StyledPara | StyledTable],
    *,
    span: Span | None = None,
) -> HierarchyTree:
    """Infer the hierarchy of one contiguous span of blocks.

    Never raises. An empty span yields an empty tree, which is the correct
    answer for ``ad_srf_22`` and ``adn_cosit_19`` — documents whose whole
    content is front and back matter.
    """
    blocks = [b for b in blocks if isinstance(b, StyledTable) or not b.is_empty]
    paras = [b for b in blocks if isinstance(b, StyledPara)]
    if not blocks:
        return HierarchyTree(span=span)

    analysis = analyse_quotation(paras)
    unit_heads = detect_unit_series(paras)
    candidates = collect_candidates(paras, analysis, unit_heads=unit_heads)
    assignments, rejected = unify_levels(candidates)
    assignments = demote_numbered_containers(
        assignments, texts={p.index: p.text.strip() for p in paras}
    )

    confidence = document_confidence([a.score for a in assignments])
    flat = confidence < CONFIDENCE_THRESHOLD

    signals = DocSignals(
        n_blocks=len(blocks),
        n_sections=0 if flat else len(assignments),
        coverage=0.0 if flat else round(len(assignments) / len(blocks), 4),
        label_kinds=tuple(
            sorted({a.label.kind for a in assignments if a.label is not None})
        ),
        style_headings=sum(1 for a in assignments if a.style is not None),
        rejected=tuple(rejected),
        confidence=confidence,
    )

    if flat:
        return HierarchyTree(
            sections=(),
            preamble=_build_content(blocks, analysis),
            confidence=confidence,
            flat=True,
            signals=signals,
            span=span,
        )

    sections, preamble = _assemble(assignments, blocks, analysis)
    return HierarchyTree(
        sections=sections,
        preamble=preamble,
        confidence=confidence,
        flat=False,
        signals=signals,
        span=span,
    )
