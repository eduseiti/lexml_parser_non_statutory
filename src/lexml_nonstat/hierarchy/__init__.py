"""Hierarchy inference: a segmented document's body becomes a tree.

Plan §3's third stage. Cycle 3 divided every sample into front matter, a body
and any annexes; this cycle gives the body — and, per the decision ratified with
the user, each annex — the recursive structure the source document has and the
LexML schemas, as shipped, cannot express.

    from lexml_nonstat.hierarchy import infer_hierarchy
    doc = infer_hierarchy(read_docx(path))
    doc.body.sections        # the tree
    doc.annexes[0].tree      # `port_mf_277`'s ANEXO ÚNICO, 65 súmulas deep

Five modules, each holding one kind of judgement:

===============  ==========================================================
:mod:`.labels`   what a rótulo looks like, and what only looks like one
:mod:`.quotation` whether a paragraph is this document's or one it quotes
:mod:`.evidence` how much each signal is worth, and when to stop believing
:mod:`.unify`    heterogeneous label sequences reconciled to one depth scale
:mod:`.tree`     assignments and blocks assembled, or discarded for flat
===============  ==========================================================

The module that matters most is :mod:`.quotation`. Plan §2.5 measured what
happens without it: two of the corpus's three article-bearing documents are
opinions *quoting* statutes, and articulating them would publish the
Constitution's ``Art. 40`` as an article of a legal opinion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ingest import StyledDoc
from ..model import Metadata, extract_metadata
from ..model.nodes import (
    Evidence,
    ListItem,
    ListNode,
    Node,
    Para,
    Section,
    Table,
)
from ..profile import DocumentProfile, select_profile
from ..segment import Segmentation, segment_document
from .evidence import CONFIDENCE_THRESHOLD, DocSignals, document_confidence
from .labels import Label, alpha_to_int, looks_like_heading, parse_label, roman_to_int
from .quotation import (
    QuotationAnalysis,
    QuoteBands,
    analyse_quotation,
    carries_omissis,
    detect_quote_bands,
    is_monotonic_series,
    is_omissis,
    names_external_norm,
)
from .tree import (
    AnnexHierarchy,
    HierarchyTree,
    build_tree,
    split_inlines,
    table_node,
)
from .unify import (
    Assignment,
    Candidate,
    collect_candidates,
    demote_numbered_containers,
    detect_unit_series,
    section_kind,
    style_level,
    unify_levels,
    validate_top_series,
)

__all__ = [
    "CONFIDENCE_THRESHOLD",
    "AnnexHierarchy",
    "Assignment",
    "Candidate",
    "DocSignals",
    "Evidence",
    "HierarchyDoc",
    "HierarchyTree",
    "Label",
    "ListItem",
    "ListNode",
    "Node",
    "Para",
    "QuotationAnalysis",
    "QuoteBands",
    "Section",
    "Table",
    "alpha_to_int",
    "analyse_quotation",
    "build_tree",
    "carries_omissis",
    "collect_candidates",
    "demote_numbered_containers",
    "detect_quote_bands",
    "detect_unit_series",
    "document_confidence",
    "infer_hierarchy",
    "is_monotonic_series",
    "is_omissis",
    "looks_like_heading",
    "names_external_norm",
    "parse_label",
    "roman_to_int",
    "section_kind",
    "split_inlines",
    "style_level",
    "table_node",
    "unify_levels",
    "validate_top_series",
]


@dataclass(frozen=True)
class HierarchyDoc:
    """A whole document's inferred structure: the body and every annex.

    The annexes are here rather than deferred to Cycle 6 because amendment
    A-R.8 wants ``port_mf_277``'s ``ANEXO ÚNICO`` to carry real structure, and
    because an annex is a body like any other — inferring it costs one loop and
    saves Cycle 6 from importing this whole package to do it again.
    """

    body: HierarchyTree
    annexes: tuple[AnnexHierarchy, ...] = ()
    source: str | None = None
    profile: str | None = None

    @property
    def trees(self) -> tuple[HierarchyTree, ...]:
        return (self.body,) + tuple(a.tree for a in self.annexes)

    @property
    def source_indices(self) -> tuple[int, ...]:
        """Every source block index the document's trees account for."""
        out: list[int] = []
        for tree in self.trees:
            out.extend(tree.section_indices)
            out.extend(tree.content_indices)
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.source is not None:
            data["source"] = self.source
        if self.profile is not None:
            data["profile"] = self.profile
        data["body"] = self.body.to_dict()
        data["annexes"] = [a.to_dict() for a in self.annexes]
        return data

    def to_json(self, *, indent: int = 2) -> str:
        """Golden-file form, in the Cycle 1–3 house style."""
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HierarchyDoc":
        return cls(
            body=HierarchyTree.from_dict(data["body"]),
            annexes=tuple(AnnexHierarchy.from_dict(a) for a in data.get("annexes", ())),
            source=data.get("source"),
            profile=data.get("profile"),
        )

    @classmethod
    def from_json(cls, text: str) -> "HierarchyDoc":
        import json

        return cls.from_dict(json.loads(text))


def infer_hierarchy(
    doc: StyledDoc,
    *,
    segmentation: Segmentation | None = None,
    profile: DocumentProfile | None = None,
    metadata: Metadata | None = None,
    referee: Any | None = None,
    log: Any | None = None,
    logger: Any | None = None,
) -> HierarchyDoc:
    """Infer the hierarchy of ``doc``'s body and of each of its annexes.

    Never raises, and never invents. A document whose evidence does not hold
    together comes back flat — complete, citable, and honest about having no
    structure worth claiming.

    ``referee`` defaults to ``None``, which is what plan §9.3 pins for the whole
    suite. Amendment A-Q.3 is the first thing in the plan to put a referee
    *inside* hierarchy inference rather than only in routing, and it does so
    confirm-only: with no referee, nothing is confirmed, no quotation is nested,
    and every tree is exactly the tree this function built before.
    """
    if profile is None:
        profile = select_profile(doc)
    if metadata is None:
        metadata = extract_metadata(doc, profile=profile)
    if segmentation is None:
        segmentation = segment_document(doc, profile=profile, metadata=metadata)

    blocks = {b.index: b for b in doc.blocks}

    def span_blocks(span):
        return [blocks[i] for i in span.indices if i in blocks] if span else []

    name = doc.source or ""
    body = build_tree(
        span_blocks(segmentation.body),
        span=segmentation.body,
        doc_name=name,
        referee=referee,
        log=log,
        logger=logger,
    )
    annexes = tuple(
        AnnexHierarchy(
            label=annex.label,
            ordinal=annex.ordinal,
            fragment=annex.fragment,
            # The annex's own marker paragraph is its title, not part of its
            # body: `ANEXO ÚNICO` is the heading Cycle 6 renders, and leaving it
            # in would make it the first section of its own annex.
            tree=build_tree(
                span_blocks(annex.span)[1:],
                span=annex.span,
                doc_name=name,
                referee=referee,
                log=log,
                logger=logger,
            ),
        )
        for annex in segmentation.annexes
    )

    return HierarchyDoc(
        body=body,
        annexes=annexes,
        source=doc.source,
        profile=profile.name,
    )
