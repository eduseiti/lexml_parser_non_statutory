"""``hierarchy_from_xml()`` — the round-trip reader, plan Cycle 7 (A-R.6).

Relocated here from the withdrawn Cycle 6b. Dropping ``articulado-sintetico``
removed an emitter; it did not remove the need to prove that what the emitters
write can be read back, and with **three** emitters in play that proof is worth
more than it was, not less. This is the reversibility invariant (§9.2) in
executable form: ``model → XML → model'`` must preserve the tree's shape and
every word of its text.

What comes back, and what deliberately does not
------------------------------------------------

Structure and text come back: kinds, labels, headings, levels, nesting, and
every paragraph. **Evidence does not.** Cycle 4's :class:`~..model.nodes.Evidence`
records *why* the inference reached a conclusion — which signals fired, at what
weight — and no emitter writes any of that into the XML, because the XML is the
document, not the reasoning that produced it. So a recovered
:class:`~..hierarchy.HierarchyTree` carries default ``Evidence``, ``confidence``
of ``0.0`` and empty ``DocSignals``, and a test asserts those values by name.
Leaving it implied would let a future reader quietly start guessing at them,
and a fabricated confidence is worse than an absent one.

Three shapes in, one shape out
-------------------------------

``DocumentoGenerico`` flat (ancestry from the id path), ``DocumentoGenerico``
nested (ancestry by containment) and ``Norma`` (statutory elements) all rebuild
into the same :class:`~..hierarchy.HierarchyDoc`. The statutory reading is the
one inference this module makes rather than reads: an ``Artigo`` becomes a
:class:`~..model.nodes.Section`, because ``HierarchyDoc`` has no dispositivo of
its own to put it in. That is recorded here rather than hidden, and it is why
the round-trip claim for ``norma`` is "tree shape and text", not "the same
model".
"""

from __future__ import annotations

from typing import Any

from lxml import etree

from ..hierarchy import HierarchyDoc
from ..hierarchy.tree import AnnexHierarchy, HierarchyTree
from ..ingest.styled import Inline
from ..model.nodes import Para, Section
from .api import _document_urn, _find, parse_document
from .model import Segment

__all__ = ["hierarchy_from_xml", "sections_from_xml"]


def hierarchy_from_xml(source: Any) -> HierarchyDoc:
    """Rebuild a :class:`~..hierarchy.HierarchyDoc` from emitted XML.

    ``source`` may be a bundle, an element, an XML string, or a path. A bundle
    rebuilds body *and* annexes; a single document rebuilds whatever it is.
    """
    if hasattr(source, "documents") and hasattr(source, "urn"):
        documents = list(source.documents)
        source_name = getattr(source, "source", None)
    else:
        documents = [parse_document(source)]
        source_name = None

    if not documents:
        return HierarchyDoc(body=HierarchyTree())

    body = _tree_of(documents[0])
    annexes: list[AnnexHierarchy] = []
    for ordinal, document in enumerate(documents[1:], start=1):
        fragment = _annex_fragment(document, ordinal)
        tree, label = _annex_tree_of(document)
        annexes.append(
            AnnexHierarchy(
                label=label,
                ordinal=ordinal,
                fragment=fragment,
                tree=tree,
            )
        )

    return HierarchyDoc(body=body, annexes=tuple(annexes), source=source_name)


def sections_from_xml(source: Any) -> tuple[Section, ...]:
    """Just the body's top-level sections — the common case, without the doc."""
    return hierarchy_from_xml(source).body.sections


# --------------------------------------------------------------------------
# One document → one tree
# --------------------------------------------------------------------------


def _tree_of(document: etree._Element) -> HierarchyTree:
    """Rebuild one document's tree from its segments.

    Built on the readers rather than beside them: they already resolved
    ancestry, order and Rule B text for all three shapes, and a second
    traversal here would be a second place for the round-trip and the oracle to
    disagree.
    """
    from .api import _segments_of_document

    return _tree_from_segments(_segments_of_document(document))


def _annex_tree_of(document: etree._Element) -> tuple[HierarchyTree, str]:
    """An annex's tree, and the ``tituloAnexo`` label the emitters split off.

    Cycle 4 excludes the annex's marker paragraph from the annex's own tree
    (A-4.5) and Cycle 5 renders it as a ``tituloAnexo`` block (A-5.6), so the
    round-trip has to put it back where it came from — on the
    :class:`~..hierarchy.tree.AnnexHierarchy`, not into the tree.
    """
    from .api import _segments_of_document

    segments = list(_segments_of_document(document))
    label = ""
    for index, segment in enumerate(segments):
        if segment.kind == "tituloAnexo":
            label = segment.text
            segments.pop(index)
            break
    return _tree_from_segments(tuple(segments)), label


def _annex_fragment(document: etree._Element, ordinal: int) -> str:
    """``anexo1`` — read from the URN fragment, falling back to the ordinal."""
    urn = _document_urn(document)
    if "!" in urn:
        return urn.rsplit("!", 1)[1]
    parte = _find(document, "PartePrincipal")
    ident = parte.get("id") if parte is not None else None
    if ident and ident.endswith("_pp"):
        return ident[: -len("_pp")]
    return f"anexo{ordinal}"


def _tree_from_segments(segments: tuple[Segment, ...]) -> HierarchyTree:
    """Segments → a ``HierarchyTree``, using ``path`` as the ancestry."""
    preamble: list[Para] = []
    roots: list[list] = []
    by_path: dict[tuple[int, ...], dict] = {}

    for segment in segments:
        if segment.is_region:
            # A front/back region is not part of the body tree. The body
            # preamble is the one exception: it is `nome="texto"` at the root
            # and it *is* body content (A-5.7).
            if segment.kind == "texto" and segment.text:
                preamble.extend(_paras(segment.text))
            continue

        record = {
            "label": segment.label,
            "heading": segment.heading,
            "level": segment.level,
            "kind": segment.kind,
            "body": tuple(_paras(segment.text)),
            "children": [],
        }
        by_path[segment.path] = record
        parent = by_path.get(segment.path[:-1])
        if parent is None:
            roots.append(record)
        else:
            parent["children"].append(record)

    return HierarchyTree(
        sections=tuple(_section(r) for r in roots),
        preamble=tuple(preamble),
    )


def _section(record: dict) -> Section:
    return Section(
        label=record["label"],
        heading=record["heading"],
        level=record["level"],
        kind=record["kind"],
        body=record["body"],
        children=tuple(_section(c) for c in record["children"]),
    )


def _paras(text: str) -> list[Para]:
    """A segment's own text as content nodes.

    One :class:`~..model.nodes.Para` rather than the original several: the
    readers report a segment's own text as a single joined string, so
    paragraph boundaries inside a section are **not** recoverable. That is why
    the round-trip claim is tree shape and *word* conservation rather than node
    identity, and saying so here keeps the next reader from assuming otherwise.

    The formatting is not recoverable either — a rebuilt ``Para`` carries one
    plain :class:`~..ingest.styled.Inline`, because the XML records what the
    text *says*, not which runs were bold.
    """
    return [Para(inlines=(Inline(text=text),))] if text else []
