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
the fact that the document **never numbers its first item at all** — its body
opens at ``2.``, and a regex for a leading ``1.`` over every block returns zero
matches. (This example previously read "its ``1.`` sits in the front matter",
which is not what the file contains; corrected by A-H's cycle.)

Since amendment A-H.1 there is a third admission route into ``Section``: a
paragraph that is a header **by meaning alone**, with no outline level and no
rótulo, confirmed one at a time by a referee. It is confirm-only — see
:func:`_confirm_prose_headers` — so with no referee this module's answer is
exactly what it was.

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
from ..referee.adjudicate import adjudicate
from ..referee.protocol import FLAG_THRESHOLD
from ..segment.model import Span
from .evidence import CONFIDENCE_THRESHOLD, DocSignals, document_confidence
from .labels import parse_label
from .quotation import QuotationAnalysis, QuoteRun, analyse_quotation
from .unify import (
    PROSE_HEADER_RULE_CONFIDENCE,
    Assignment,
    collect_candidates,
    demote_numbered_containers,
    detect_unit_series,
    is_prose_form_header,
    unify_levels,
)

__all__ = [
    "AnnexHierarchy",
    "HierarchyTree",
    "BOUNDARY_RULE_CONFIDENCE",
    "build_tree",
    "split_citations",
    "split_inlines",
    "table_node",
]

#: How much a quotation head is worth on its own, before a referee is asked.
#:
#: Deliberately **below** :data:`~..referee.protocol.FLAG_THRESHOLD` (0.60), so
#: every boundary candidate is flagged and every candidate is put to a referee
#: when one is configured. That is the whole point of A-Q.3's inversion: the
#: rule is confident enough to *propose* a boundary and not confident enough to
#: *impose* one, so with no referee the document stays flat (invariant #8) and
#: with a referee the answer is confirm-or-veto on a candidate that already
#: exists. It is also below :data:`RULE_HIGH_CONFIDENCE`, so invariant #9 never
#: blocks the veto.
BOUNDARY_RULE_CONFIDENCE = 0.55


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


def table_node(table: StyledTable) -> Table:
    """A ``StyledTable`` as a model ``Table``: cells are inlines only (§2.2).

    Public because Cycle 5's emitter meets tables outside the body too —
    ``REsp_1306393`` carries one inside its front-matter hull — and a second
    conversion would be a second answer to "what is a cell".
    """
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
            out.append(table_node(block))
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


def _split_tree(
    section: Section,
    analysis: QuotationAnalysis,
    doc_name: str,
    referee: object | None,
    log: object | None,
    logger: object | None,
) -> Section:
    """Apply :func:`split_citations` to ``section`` and to every descendant."""
    children = tuple(
        _split_tree(child, analysis, doc_name, referee, log, logger)
        for child in section.children
    )
    if children != section.children:
        section = Section(
            label=section.label,
            heading=section.heading,
            level=section.level,
            kind=section.kind,
            body=section.body,
            children=children,
            evidence=section.evidence,
            source_indices=section.source_indices,
        )
    return split_citations(
        section,
        analysis,
        doc_name=doc_name,
        referee=referee,
        log=log,
        logger=logger,
    )


def _run_of(node: Node, analysis: QuotationAnalysis) -> QuoteRun | None:
    """The single run a content node belongs to, or ``None``.

    ``None`` for an unquoted node **and** for a node straddling two runs. A
    straddling node cannot be assigned to one child without splitting it, and
    splitting a ``ListNode`` or a ``Table`` to make a quotation boundary fall
    where we want it would be inventing structure inside content — so it is
    reported as unassignable and A-Q.5's gate refuses the whole section.
    """
    indices = node.all_source_indices
    if not indices:
        return None
    runs = {analysis.run_for(index) for index in indices}
    if len(runs) != 1:
        return None
    return runs.pop()


def split_citations(
    section: Section,
    analysis: QuotationAnalysis,
    *,
    doc_name: str = "",
    referee: object | None = None,
    log: object | None = None,
    logger: object | None = None,
) -> Section:
    """Divide one section's body into a child ``Section`` per quoted norm.

    This is amendment A-Q.4, and every guard in it is amendment A-Q.5.

    `par_cosit_26`'s item ``14.`` announces four laws and then transcribes them
    as **one flat run of 35 paragraphs**. A human reader sees four quotations;
    the XML said "thirty-five paragraphs, some of them quoted". The boundary
    between Lei 7.713 and Lei 8.134 is a paragraph that literally begins
    ``Lei 8.134, de 1990 - "Art. 2º…`` and it was invisible in the output.

    Four conditions, all of which must hold, or the section is returned
    **unchanged**:

    1. **Two or more named runs.** One quotation is not a division — wrapping a
       lone excerpt in a child that adds no distinction is structure for its own
       sake, and it would churn a golden on every sample in the corpus for no
       gain.
    2. **Every body node assignable.** A node straddling two runs, or a run
       whose paragraphs are not contiguous among the body nodes, aborts the
       whole split.
    3. **A referee confirms each boundary**, when one is configured. The rule
       alone sits at :data:`BOUNDARY_RULE_CONFIDENCE`, below the flag
       threshold, so with no referee nothing is confirmed and the section stays
       flat — invariant #8, for free, exactly as ``--referee=none`` requires.
    4. **Conservation.** The children's bodies plus the parent's remaining body
       must reproduce the original body exactly, in order, with nothing lost
       and nothing duplicated. Checked *before* the new section is returned,
       not after — the A-6.3 lesson, where a render was valid on both schemas
       and 29 words short.

    The referee is **confirm-only**: it is asked about candidates the head
    detector already proposed and can only veto them. It cannot volunteer a
    boundary, so no answer it gives — however confident, however wrong — can
    fabricate a citable unit with its own URN.
    """
    if not section.body:
        return section

    # 1. Group the body nodes into consecutive stretches by run.
    groups: list[tuple[QuoteRun | None, list[Node]]] = []
    for node in section.body:
        run = _run_of(node, analysis)
        if groups and groups[-1][0] is run:
            groups[-1][1].append(node)
            continue
        groups.append((run, [node]))

    named = [(run, nodes) for run, nodes in groups if run is not None and run.norm]
    if len(named) < 2:
        return section

    # 2. A run must not be scattered across several groups: that would mean the
    #    document's own prose interleaves the quotation, and a child section
    #    would silently reorder it.
    seen: set[tuple[int, ...]] = set()
    for run, _ in named:
        if run.indices in seen:
            return section
        seen.add(run.indices)

    # 3. Adjudicate each candidate boundary. The *first* named run is not a
    #    boundary — it opens the quotation rather than changing norms — but it
    #    still becomes a child once any later boundary is confirmed, because a
    #    division into "the rest" and "Lei 8.134" would misattribute the first
    #    norm's text.
    confirmed: set[tuple[int, ...]] = set()
    for run, _ in named[1:]:
        if _confirm_boundary(
            run,
            doc_name=doc_name,
            referee=referee,
            log=log,
            logger=logger,
        ):
            confirmed.add(run.indices)

    if not confirmed:
        return section

    # 4. Build the children, keeping every unassigned node where it was.
    body: list[Node] = []
    children: list[Section] = list(section.children)
    citations: list[Section] = []
    for run, nodes in groups:
        if run is not None and run.norm and (run.indices in confirmed or run is named[0][0]):
            citations.append(
                Section(
                    label=None,
                    heading=run.norm,
                    level=section.level + 1,
                    kind="citacao",
                    body=_promote_head(tuple(nodes), run),
                    children=(),
                    evidence=run.evidence.with_signal("referee_confirmed", 0.8)
                    if run.indices in confirmed
                    else run.evidence,
                    source_indices=(),
                )
            )
            continue
        body.extend(nodes)

    if len(citations) < 2:
        return section

    # 5. Conservation, as a precondition (A-Q.5). Compared on source indices in
    #    document order: the split moves nodes, so the multiset *and* the order
    #    of what the section accounts for must be exactly what it accounted for
    #    before.
    before = [i for node in section.body for i in node.all_source_indices]
    after = [
        i
        for node in body
        for i in node.all_source_indices
    ] + [
        i
        for child in citations
        for node in child.body
        for i in node.all_source_indices
    ]
    if sorted(before) != sorted(after) or len(before) != len(after):
        return section

    return Section(
        label=section.label,
        heading=section.heading,
        level=section.level,
        kind=section.kind,
        body=tuple(body),
        children=tuple(citations) + tuple(children),
        evidence=section.evidence.with_signal("citacao_split", 0.6),
        source_indices=section.source_indices,
    )


def _promote_head(nodes: tuple[Node, ...], run: QuoteRun) -> tuple[Node, ...]:
    """Cut the norm's name off the head paragraph, since it becomes the heading.

    Without this the split **duplicates text**: ``Lei nº 7.713, de 1988`` would
    appear once as the child's ``NomeAgrupador`` and again at the front of the
    paragraph the heading was taken from. Invariant #2 forbids loss *and*
    duplication, and a `Counter` comparison across the two emitters catches it
    immediately — which is how this was found.

    It is the same move ``_finish`` already makes for a rótulo, done with the
    same tool: :func:`split_inlines` cuts at a character offset with run
    boundaries intact, because a norm name and the article after it are
    routinely one Word run.
    """
    if not nodes or run.norm is None:
        return nodes
    head = nodes[0]
    if not isinstance(head, Para):
        return nodes

    text = head.text
    offset = text.find(run.norm)
    if offset < 0:
        return nodes

    # Cut **exactly** at the end of the norm's name, then drop only whitespace.
    # The separator characters stay with the remainder, and that is not
    # fastidiousness: `Lei 8.383, de 1991, Art. 12` and
    # `Lei nº 7.713, de 1988 - "Art. 1º-` were losing a comma and a dash to the
    # cut, and punctuation is text. Invariant #2 counts words, and the words it
    # counted came back two `-` and two commas short.
    cut = offset + len(run.norm)
    while cut < len(text) and text[cut].isspace():
        cut += 1

    remainder = split_inlines(head.inlines, cut)
    if not "".join(i.text for i in remainder).strip():
        # The head is nothing but the norm's name. Dropping the paragraph would
        # lose no text (the heading carries it) but would lose the block, so
        # keep the run's other nodes and let the heading stand alone.
        return nodes[1:]

    return (
        Para(
            inlines=remainder,
            kind=head.kind,
            indent=head.indent,
            source_indices=head.source_indices,
        ),
    ) + nodes[1:]


def _confirm_boundary(
    run: QuoteRun,
    *,
    doc_name: str,
    referee: object | None,
    log: object | None,
    logger: object | None,
) -> bool:
    """Put one candidate boundary to the referee; ``True`` only if confirmed.

    The rule verdict is **``"continuation"``** at
    :data:`BOUNDARY_RULE_CONFIDENCE`. That is not pessimism about the head
    detector — it is invariant #8 expressed as the default: a candidate nobody
    confirmed does not become structure. With ``--referee=none`` this function
    always returns ``False`` and every document stays exactly as it was, which
    is what keeps §9.3's pinned suite and all 135 goldens honest.
    """
    excerpt = run.head_text
    ctx = run.antecedent_text
    final, _record = adjudicate(
        kind="quotation_boundary",
        doc=doc_name,
        locator=f"p#{run.head}",
        rule_verdict="continuation",
        rule_confidence=BOUNDARY_RULE_CONFIDENCE,
        excerpt=excerpt,
        ctx=ctx,
        reason=(
            "quotation head proposed a norm change; a referee must confirm it "
            "before it becomes a nested citation (A-Q.3, confirm-only)"
        ),
        referee=referee,
        log=log,
        logger=logger,
    )
    return final == "boundary"


def _confirm_prose_headers(
    paras: Sequence[StyledPara],
    analysis: QuotationAnalysis,
    *,
    doc_name: str,
    referee: object | None,
    log: object | None,
    logger: object | None,
) -> frozenset[int]:
    """Which prose-form candidates a referee confirmed as section headers.

    The rule verdict is **``"nao"``** at
    :data:`~.unify.PROSE_HEADER_RULE_CONFIDENCE`, mirroring
    :func:`_confirm_boundary` exactly. That is invariant #8 expressed as the
    default: a paragraph nobody confirmed does not become structure. With
    ``--referee=none`` this returns an empty set on every document, so
    `collect_candidates` sees what it always saw and all 135 goldens hold.

    Both neighbours are passed as context (A-H.2), because a heading is defined
    by what follows it as much as by what precedes it.
    """
    if referee is None or not getattr(referee, "enabled", True):
        return frozenset()

    texts = {p.index: p.text.strip() for p in paras if not p.is_empty}
    order = [p.index for p in paras if not p.is_empty]
    position = {index: i for i, index in enumerate(order)}

    confirmed: set[int] = set()
    for para in paras:
        if not is_prose_form_header(para, quoted=analysis.is_quoted(para.index)):
            continue
        i = position[para.index]
        prev = texts[order[i - 1]] if i > 0 else ""
        following = texts[order[i + 1]] if i + 1 < len(order) else ""
        final, _record = adjudicate(
            kind="heading",
            doc=doc_name,
            locator=f"p#{para.index}",
            rule_verdict="nao",
            rule_confidence=PROSE_HEADER_RULE_CONFIDENCE,
            excerpt=texts[para.index],
            ctx=prev,
            next_ctx=following,
            reason=(
                "unlabelled, unstyled paragraph proposed as a section header on "
                "typographic evidence alone; a referee must confirm it before it "
                "becomes structure (A-H.3, confirm-only)"
            ),
            referee=referee,
            log=log,
            logger=logger,
        )
        if final == "secao":
            confirmed.add(para.index)
    return frozenset(confirmed)


def build_tree(
    blocks: Sequence[StyledPara | StyledTable],
    *,
    span: Span | None = None,
    doc_name: str = "",
    referee: object | None = None,
    log: object | None = None,
    logger: object | None = None,
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
    # A-H.1/A-H.3. `build_tree` is already called per *span* — the body and each
    # annex separately — so gating the generator to `Segmentation.body` needs no
    # extra check here: front and back matter never reach this function.
    prose_form = _confirm_prose_headers(
        paras, analysis, doc_name=doc_name, referee=referee, log=log, logger=logger
    )
    candidates = collect_candidates(
        paras, analysis, unit_heads=unit_heads, prose_form_indices=prose_form
    )
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

    # A-Q.4. Applied after assembly rather than during it: a section's quoted
    # material can only be divided once the section knows its whole body, and
    # doing it here keeps `_assemble` the single answer to "which blocks belong
    # to which header". With no referee configured this is an identity
    # transform on every sample — `split_citations` confirms nothing, so it
    # returns each section unchanged.
    sections = tuple(
        _split_tree(section, analysis, doc_name, referee, log, logger)
        for section in sections
    )

    return HierarchyTree(
        sections=sections,
        preamble=preamble,
        confidence=confidence,
        flat=False,
        signals=signals,
        span=span,
    )
