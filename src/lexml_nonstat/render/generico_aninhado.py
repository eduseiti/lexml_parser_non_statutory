"""The nested ``generico-aninhado`` emitter — plan §5.2, opt-in.

Where :mod:`.generico` flattens the section tree into siblings and carries its
depth out of band, this emitter writes the tree *as a tree*: one
``AgrupamentoHierarquico`` per :class:`~..model.nodes.Section`, nested. That is
possible only under the maintainers' unreleased change (§2.10), which makes
``AgrupamentoHierarquico`` prose-bearing and recursive, so the output validates
against ``lexml-proposed/`` and **not** against the shipped ``lexml/``.

Three things become native, and each retires a flat-emitter workaround:

* ``<Rotulo>`` and ``<NomeAgrupador>`` are real elements, so
  ``<Bloco nome="rotulo"|"nomeAgrupador">`` is retired;
* depth is ``count(ancestor::AgrupamentoHierarquico)``, so ``<Bloco
  nome="nivel">`` is retired too — a redundant marker that can disagree with
  the tree is a liability, not a safeguard;
* **Rule A becomes structurally unnecessary.** A missing ancestor is now a
  malformed tree that no serialisation can express, not a silently broken
  breadcrumb. The ids stay path-composed anyway (§5.2), so a segment URN means
  the same thing whichever emitter produced it.

**The refusal gate is not here.** This function always renders; it is *emitter
selection* (the CLI) and *validation* that consult
:func:`~..validate.schema.probe_capabilities`. A pure renderer that refused to
run against the default checkout could not be tested on the default checkout
(spec decision R-2).

The canonical child order — measured, not assumed
-------------------------------------------------

``AgrupamentoHierarquico`` extends ``hierarchy``, whose base sequence ends with
``AgrupamentoHierarquico*``; XSD appends the extension ``choice`` *after* it.
Twenty-four probes against ``lexml-proposed/`` pin the effective model::

    Rotulo?  NomeAgrupador?  AgrupamentoHierarquico*  (Agrupamento | Bloco)+

so this emitter writes, in order:

1. ``Rotulo`` (iff labelled), 2. ``NomeAgrupador`` (iff headed),
3. every child section, 4. ``Bloco nome="ordem"``, 5. the prose leaf
``Agrupamento nome="texto"`` — or ``Bloco nome="vazio"`` when there is no own
prose.

Two consequences, both load-bearing:

**Constraint 1 costs reading order.** A section's own prose must be serialised
*after* its subsections, which is not document order. The plan states this for
prose; probe K found it is true of ``Bloco`` as well, so the ``ordem`` marker
also sits after the subsections (amendment **A-5b.1**). Because sibling
position no longer means reading order, every child records its 0-based
document-order index in ``<Bloco nome="ordem">`` — a reader must use that and
never infer order from position.

**Constraint 2 needs a filler.** The extension choice is ``minOccurs="1"``, so
a section with subsections but no prose of its own cannot be a bare container;
an empty ``<Agrupamento/>`` is invalid too (``blocksreq``). ``<Bloco
nome="vazio"/>`` is the resolution — ``Bloco`` extends ``inline`` at
``minOccurs="0"``, so a genuinely empty one is valid. It carries no text, so
:func:`~.common.leaf_texts` never sees it and conservation is untouched.

Everything outside the body is Cycle 5's, unchanged and shared: the front and
back matter **regions** (amendment A-5.1 — hulls, not named parts), the
preamble wrapper (A-5.7), and the annex-as-sibling-document convention (§2.9).
"""

from __future__ import annotations

from typing import Iterator

from lxml import etree

from ..model.document import DocumentModel
from ..model.nodes import Section
from .common import (
    LEXML_NS,
    XLINK_NS,
    agrupamento,
    back_region,
    el,
    front_region,
    render_node,
)
from .generico import RenderedDocument, Scope

__all__ = [
    "EMITTER",
    "ORDER_BLOCO",
    "EMPTY_BLOCO",
    "render_generico_aninhado",
    "render_generico_aninhado_from_docx",
]

#: This emitter's name, as it appears in :attr:`RenderedDocument.emitter` and
#: on the CLI's ``--emitter`` flag (Cycle 8).
EMITTER = "generico-aninhado"

#: ``Bloco/@nome`` recording a child's 0-based document-order index. Constraint
#: 1 makes sibling position meaningless, so this is the only order channel.
ORDER_BLOCO = "ordem"

#: ``Bloco/@nome`` satisfying Constraint 2 for a section with no own prose.
EMPTY_BLOCO = "vazio"


def _bloco(nome: str, text: str | None = None) -> etree._Element:
    """A ``Bloco`` marker. Empty when ``text`` is ``None`` — which is legal."""
    element = el("Bloco", nome=nome)
    if text is not None:
        element.text = text
    return element


def _native(tag: str, text: str) -> etree._Element:
    element = el(tag)
    element.text = text
    return element


def _prose_leaf(
    section: Section, ident: str, scope: Scope
) -> etree._Element | None:
    """The section's own content as one ``Agrupamento nome="texto"``.

    ``None`` when the section has no renderable content of its own, which is
    what makes the ``vazio`` marker necessary rather than decorative.
    """
    children = [
        rendered
        for rendered in (
            render_node(node, table_id=scope.table_id) for node in section.body
        )
        if rendered is not None
    ]
    return agrupamento("texto", ident, children)


def _section_element(
    section: Section, parent_id: str, scope: Scope, order: int
) -> etree._Element:
    """One section as a nested ``AgrupamentoHierarquico``.

    Recursion is what makes Rule A unnecessary: a child element is built
    *inside* its parent element, so there is no serialisation in which an
    ancestor is missing. The id is still composed from a parent the allocator
    has already issued, so the path scheme is unchanged from the flat emitter.
    """
    ident = scope.ids.child(parent_id, "agh")
    element = el("AgrupamentoHierarquico", id=ident, nome=section.kind)

    # 1-2. The natives, in the order the schema fixes (probe J: swapping fails).
    if section.label:
        element.append(_native("Rotulo", section.label))
    if section.heading:
        element.append(_native("NomeAgrupador", section.heading))

    # 3. Child sections first — Constraint 1. Their `ordem` is their true
    #    document-order position among *all* of this section's children.
    for index, child in enumerate(section.children):
        element.append(_section_element(child, ident, scope, index))

    # 4. This section's own order index, after the subsections (A-5b.1: a
    #    `Bloco` may not precede an `AgrupamentoHierarquico` either).
    element.append(_bloco(ORDER_BLOCO, str(order)))

    # 5. Own prose, or the Constraint 2 filler.
    leaf = _prose_leaf(section, scope.ids.child(ident, "txt"), scope)
    element.append(leaf if leaf is not None else _bloco(EMPTY_BLOCO))

    return element


def _tree_elements(tree, scope: Scope) -> Iterator[etree._Element]:
    """A ``HierarchyTree``'s preamble and its top-level sections.

    The preamble keeps the flat emitter's shape — ``Agrupamento nome="texto"``
    directly under ``PartePrincipal`` (A-5.7) — because it belongs to no
    section, and because ``nome="texto"`` is what §5.2 gives a prose leaf, so
    the two emitters agree on its segment URN.
    """
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
            yield element

    for index, section in enumerate(tree.sections):
        yield _section_element(section, scope.ids.root, scope, index)


def _lexml_root() -> etree._Element:
    return etree.Element(f"{{{LEXML_NS}}}LexML", nsmap={None: LEXML_NS, "xlink": XLINK_NS})


def _render_annex(model: DocumentModel, annex) -> etree._Element:
    """One annex as a standalone ``<LexML><Metadado/><Anexo>`` document (§2.9).

    Identical in shape to the flat emitter's annex — same ``anexoN_pp`` root,
    same ``anexoN_tabM`` tables, same ``!anexoN`` fragment — differing only in
    that its sections nest. That is what lets conservation be checked *across*
    the split with one implementation of the check.
    """
    root = _lexml_root()

    meta = el("Metadado")
    identificacao = el("Identificacao")
    identificacao.set("URN", model.metadata.urn_with_fragment(annex.fragment))
    meta.append(identificacao)
    root.append(meta)

    scope = Scope(f"{annex.fragment}_pp", annex.fragment)
    parte = el("PartePrincipal", id=scope.ids.root)

    # Cycle 4 excludes the annex's marker paragraph from its own tree (A-4.5),
    # so this is the only place `ANEXO ÚNICO` can be conserved (A-5.6).
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


def render_generico_aninhado(model: DocumentModel) -> RenderedDocument:
    """Render ``model`` as a nested ``DocumentoGenerico`` bundle.

    Never raises on a real document, on the same terms as the flat emitter:
    an empty body, absent front matter and absent back matter are all ordinary
    in this corpus, and each simply contributes nothing.

    The result is invalid against the **shipped** schemas by design — that is
    what ``generico-aninhado`` being opt-in *means*. Callers gate on
    :func:`~..validate.schema.probe_capabilities`; this function does not.
    """
    root = _lexml_root()
    root.append(model.metadata.to_xml())

    scope = Scope("pp1", "pp1")
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
        emitter=EMITTER,
        source=model.source,
    )


def render_generico_aninhado_from_docx(
    path, *, filename: str | None = None
) -> RenderedDocument:
    """Read a DOCX and render it nested — the whole pipeline in one call."""
    from pathlib import Path

    from ..ingest import read_docx
    from ..model import build_model

    path = Path(path)
    model = build_model(read_docx(path), filename=filename or path.name)
    return render_generico_aninhado(model)
