"""The flat ``generico`` emitter — plan §5.1, the **default** rendering.

``DocumentoGenerico`` is what 14 of the 15 samples are, and — until the
maintainers' recursive ``AgrupamentoHierarquico`` ships (§2.10) — the only
shape the shipped schemas offer for a document with real internal hierarchy
that is not articulated. ``Agrupamento`` cannot nest (§2.1 row C, pinned as a
test), so the tree is **flattened into siblings** and its depth is carried
out of band, three redundant ways:

* the ``id`` path — ``pp1_agr6_agr1`` is a child of ``pp1_agr6`` (§2.3);
* ``<Bloco nome="nivel">`` — the unified depth, as a number;
* ``@nome`` — the section kind.

Two emitter rules come from the §2.4 segmentation experiment, and both have
their own regression:

**Rule A — materialise every intermediate level.** An id of
``pp1_agr1_agr2_agr1`` whose ``pp1_agr1_agr2`` does not exist produced a
breadcrumb silently missing its middle ancestor. Here it holds by construction:
:class:`~.ids.IdAllocator` only composes a child id from a parent it has already
issued, and the tree is walked depth-first from the root, so a gap cannot be
written. :func:`~.ids.missing_prefixes` proves it afterwards.

**Rule B — leaf-only text.** Handled in :func:`~.common.leaf_texts`.

An annex is a **standalone sibling document** (§2.9), matching the reference
parser exactly: the primary carries only
``<Anexos><ReferenciaAnexo AlvoURN="…!anexoN"/></Anexos>``, the annex is
``<LexML><Metadado/><Anexo><DocumentoGenerico>``, its ``PartePrincipal`` is
``anexoN_pp`` and its tables are ``anexoN_tabM``. That is also what makes
conservation checkable *across* the split rather than only within one file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from lxml import etree

from ..model.document import DocumentModel
from ..model.nodes import Section
from .common import (
    LEXML_NS,
    XLINK_NS,
    agrupamento,
    all_ids,
    back_region,
    el,
    front_region,
    leaf_texts,
    render_node,
    to_xml_string,
)
from .ids import IdAllocator

__all__ = [
    "AUXILIARY_NOMES",
    "RenderedDocument",
    "render_generico",
    "render_generico_from_docx",
]

#: ``Agrupamento/@nome`` values that are **not** a ``Section.kind``: the front
#: and back matter regions, the body preamble and an annex's title. Every other
#: ``nome`` the emitter writes comes from the ratified ``SECTION_KINDS``.
AUXILIARY_NOMES: tuple[str, ...] = (
    "epigrafe",
    "ementa",
    "preambulo",
    "formulaPromulgacao",
    "preliminar",
    "localDataFecho",
    "assinatura",
    "nota",
    "texto",
    "tituloAnexo",
)


@dataclass(frozen=True)
class RenderedDocument:
    """One emitted document and its annex documents.

    A bundle rather than a single element because an annex is a *sibling*
    ``LexML`` document under the reference convention (§2.9), not a subtree —
    and because conservation must be checked over the whole bundle.
    """

    primary: etree._Element
    annexes: tuple[etree._Element, ...] = ()
    urn: str = ""
    emitter: str = "generico"
    source: str | None = None

    @property
    def documents(self) -> tuple[etree._Element, ...]:
        """Primary first, then each annex in document order."""
        return (self.primary,) + self.annexes

    def to_xml_string(self, element: etree._Element | None = None) -> str:
        return to_xml_string(self.primary if element is None else element)

    def to_xml_strings(self) -> tuple[str, ...]:
        return tuple(to_xml_string(d) for d in self.documents)

    @property
    def ids(self) -> tuple[str, ...]:
        """Every ``id`` in the bundle, primary first."""
        return tuple(i for d in self.documents for i in all_ids(d))

    @property
    def texts(self) -> tuple[str, ...]:
        """Rule B leaf text across the whole bundle."""
        return tuple(t for d in self.documents for t in leaf_texts(d))


class _Scope:
    """One document's id space: an allocator plus the §2.9 table base."""

    def __init__(self, root: str, table_base: str) -> None:
        self.ids = IdAllocator(root)
        self.table_base = table_base
        self._tables = 0

    def table_id(self) -> str:
        self._tables += 1
        return self.ids.take(f"{self.table_base}_tab{self._tables}")

    def adopt(self, elements: tuple[etree._Element, ...], token: str) -> None:
        """Register ids another module already issued on our scheme (D-1)."""
        for element in elements:
            ident = element.get("id")
            if ident is not None:
                self.ids.take(ident)
        self.ids.advance(self.ids.root, token, len(elements))


def _bloco(nome: str, text: str) -> etree._Element:
    element = el("Bloco", nome=nome)
    element.text = text
    return element


def _section_elements(
    section: Section, parent_id: str, scope: _Scope
) -> Iterator[etree._Element]:
    """One section, then its descendants — depth-first, pre-order, flattened.

    Yielding the parent before recursing is what keeps Rule A true: the child's
    id is composed from an id already issued, and the element carrying it has
    already been emitted.
    """
    ident = scope.ids.child(parent_id, "agr")

    children: list[etree._Element] = []
    if section.label:
        children.append(_bloco("rotulo", section.label))
    if section.heading:
        children.append(_bloco("nomeAgrupador", section.heading))
    # Always emitted: it is the third depth channel, and it also guarantees the
    # `Agrupamento` is never empty, which `blocksreq` rejects on both schemas.
    children.append(_bloco("nivel", str(section.level)))
    for node in section.body:
        rendered = render_node(node, table_id=scope.table_id)
        if rendered is not None:
            children.append(rendered)

    element = agrupamento(section.kind, ident, children)
    if element is not None:
        yield element

    for child in section.children:
        yield from _section_elements(child, ident, scope)


def _tree_elements(tree, scope: _Scope) -> list[etree._Element]:
    """A ``HierarchyTree``'s preamble and sections, as ``PartePrincipal`` children.

    The preamble is wrapped in a single ``Agrupamento nome="texto"`` rather than
    dropped loose under ``PartePrincipal`` (spec decision D-2): every content
    node then sits in a citable, id-bearing container, which is what §2.4's
    segmentation consumes, and it is the same ``nome`` §5.2 gives a prose leaf,
    so segment URNs line up across the two emitters.
    """
    out: list[etree._Element] = []

    if tree.preamble:
        ident = scope.ids.child(scope.ids.root, "agr")
        rendered = [
            node
            for node in (
                render_node(n, table_id=scope.table_id) for n in tree.preamble
            )
            if node is not None
        ]
        element = agrupamento("texto", ident, rendered)
        if element is not None:
            out.append(element)

    for section in tree.sections:
        out.extend(_section_elements(section, scope.ids.root, scope))

    return out


def _lexml_root() -> etree._Element:
    return etree.Element(f"{{{LEXML_NS}}}LexML", nsmap={None: LEXML_NS, "xlink": XLINK_NS})


def _render_annex(model: DocumentModel, annex) -> etree._Element:
    """One annex as a standalone ``<LexML><Metadado/><Anexo>`` document (§2.9)."""
    root = _lexml_root()

    meta = el("Metadado")
    identificacao = el("Identificacao")
    identificacao.set("URN", model.metadata.urn_with_fragment(annex.fragment))
    meta.append(identificacao)
    root.append(meta)

    scope = _Scope(f"{annex.fragment}_pp", annex.fragment)
    parte = el("PartePrincipal", id=scope.ids.root)

    # Cycle 4 excludes the annex's own marker paragraph from its tree — it is
    # the annex's title, not its first section — so this is the only place
    # `ANEXO ÚNICO` can be conserved (spec decision D-5).
    if annex.label:
        title = el("p")
        title.text = annex.label
        element = agrupamento(
            "tituloAnexo", scope.ids.child(scope.ids.root, "agr"), [title]
        )
        if element is not None:
            parte.append(element)

    for element in _tree_elements(annex.tree, scope):
        parte.append(element)

    documento = el("DocumentoGenerico")
    if len(parte):
        documento.append(parte)

    anexo = el("Anexo")
    anexo.append(documento)
    root.append(anexo)
    return root


def render_generico(model: DocumentModel) -> RenderedDocument:
    """Render ``model`` as a flat ``DocumentoGenerico`` bundle.

    Never raises on a real document: an empty body, absent front matter and
    absent back matter are all ordinary in this corpus (``ad_srf_22`` and
    ``adn_cosit_19`` are nothing *but* front and back matter), and each simply
    contributes nothing.
    """
    root = _lexml_root()
    root.append(model.metadata.to_xml())

    scope = _Scope("pp1", "pp1")
    parte = el("PartePrincipal", id=scope.ids.root)

    front = front_region(
        model.segmentation.front,
        model.styled,
        table_id=scope.table_id,
        first_index=model.segmentation.first_index,
        prefix=scope.ids.root,
    )
    scope.adopt(front, "agr")
    for element in front:
        parte.append(element)

    for element in _tree_elements(model.body, scope):
        parte.append(element)

    back = back_region(
        model.segmentation.back,
        model.styled,
        table_id=scope.table_id,
        prefix=scope.ids.root,
    )
    scope.adopt(back, "agrf")
    for element in back:
        parte.append(element)

    documento = el("DocumentoGenerico")
    if len(parte):
        documento.append(parte)

    annexes = tuple(_render_annex(model, annex) for annex in model.annexes)
    if model.annexes:
        anexos = el("Anexos")
        for annex in model.annexes:
            referencia = el("ReferenciaAnexo")
            referencia.set(
                "AlvoURN", model.metadata.urn_with_fragment(annex.fragment)
            )
            anexos.append(referencia)
        documento.append(anexos)

    root.append(documento)

    return RenderedDocument(
        primary=root,
        annexes=annexes,
        urn=model.metadata.urn,
        emitter="generico",
        source=model.source,
    )


def render_generico_from_docx(path, *, filename: str | None = None) -> RenderedDocument:
    """Read a DOCX and render it flat — the whole pipeline in one call."""
    from pathlib import Path

    from ..ingest import read_docx
    from ..model import build_model

    path = Path(path)
    model = build_model(read_docx(path), filename=filename or path.name)
    return render_generico(model)
