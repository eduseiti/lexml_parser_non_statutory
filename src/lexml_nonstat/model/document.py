"""The whole document, assembled — plan §3.1's ``DocumentModel``.

Four cycles each produced one view of a document: what the reader saw
(:class:`~..ingest.StyledDoc`), what the extractor concluded
(:class:`~.metadata.Metadata`), how it divides
(:class:`~..segment.Segmentation`), what shape its body has
(:class:`~..hierarchy.HierarchyDoc`) and whether it may be published as a
``Norma`` (:class:`~..routing.StatutoryViability`). An emitter needs all five
at once, and passing five arguments through every emitter, every cycle, is five
chances to pass them inconsistently.

``articulacao`` is declared and left empty. Plan §3.1 puts it here, the
statutory route fills it in Cycle 6, and declaring it now is what lets Cycle 6
add a route rather than a field.

``decisions`` is §3.1's telemetry channel, and unlike ``articulacao`` it is
populated from the start: Cycle 4b already records why each routing call went
the way it did, and a model that discarded the reasons could not explain its
own route afterwards.

This type carries **no serialisation of its own** (spec decision D-3): its five
components already have byte-stable goldens, and a sixth would make one
behaviour change diff twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..ingest import Block, StyledDoc, StyledPara

if TYPE_CHECKING:  # `segment` imports `model`, so this one stays a name only.
    from ..segment import Segmentation

__all__ = ["DocumentModel", "build_model"]


@dataclass(frozen=True)
class DocumentModel:
    """One document, in every view an emitter needs.

    ``route`` is the routing decision (``norma`` | ``generico``), not the
    emitter: amendment A-R.7 separates the two, and a ``generico``-routed
    document is written out by either the flat or the nested emitter.
    """

    metadata: Any
    segmentation: "Segmentation"
    hierarchy: Any
    viability: Any
    styled: StyledDoc
    profile: str = "generic"
    route: str = "generico"
    #: ``Dispositivo`` tuple on the statutory route — Cycle 6.
    articulacao: tuple[Any, ...] = ()
    #: Cycle 4b's rule-vs-referee records for this document (plan §7.4).
    decisions: tuple[Any, ...] = ()

    @property
    def source(self) -> str | None:
        return self.styled.source

    @property
    def body(self):
        """The body's inferred tree."""
        return self.hierarchy.body

    @property
    def annexes(self) -> tuple[Any, ...]:
        """Each annex's tree, in document order."""
        return self.hierarchy.annexes

    @property
    def blocks(self) -> dict[int, Block]:
        """Source blocks by index, so a renderer can reach text by span."""
        return {b.index: b for b in self.styled.blocks}

    def block_text(self, index: int) -> str:
        """One source block's text, or ``""`` when the index is not a block."""
        block = self.blocks.get(index)
        if block is None or not isinstance(block, StyledPara):
            return ""
        return block.text


def build_model(
    doc: StyledDoc,
    *,
    filename: str | None = None,
    profile: Any = None,
    metadata: Any = None,
    segmentation: "Segmentation | None" = None,
    hierarchy: Any = None,
    viability: Any = None,
    log: Any = None,
) -> DocumentModel:
    """Assemble a :class:`DocumentModel`, computing whatever was not supplied.

    The call chain is the one ``scripts/regen_goldens.py`` already uses, so a
    model built here and a golden regenerated there cannot drift apart. The
    referee is deliberately not consulted: routing's default is
    ``referee=None`` and plan §9.3 pins that for the whole suite.
    """
    from ..hierarchy import infer_hierarchy
    from ..profile import select_profile
    from ..routing import assess_viability
    from ..segment import segment_document
    from ..telemetry import DecisionLog
    from .metadata import extract_metadata

    if log is None:
        log = DecisionLog()

    if profile is None:
        profile = select_profile(doc)
    if metadata is None:
        metadata = extract_metadata(doc, profile=profile, filename=filename)
    if segmentation is None:
        segmentation = segment_document(doc, profile=profile, metadata=metadata)
    if hierarchy is None:
        hierarchy = infer_hierarchy(
            doc, segmentation=segmentation, profile=profile, metadata=metadata
        )
    if viability is None:
        viability = assess_viability(
            doc,
            metadata=metadata,
            segmentation=segmentation,
            hierarchy=hierarchy,
            log=log,
        )

    return DocumentModel(
        metadata=metadata,
        segmentation=segmentation,
        hierarchy=hierarchy,
        viability=viability,
        styled=doc,
        profile=profile.name,
        route=viability.route,
        decisions=tuple(log.records),
    )
