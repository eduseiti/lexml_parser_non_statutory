"""The annex split — one implementation of plan §2.9, shared by every emitter.

An annex is a **standalone sibling document**, not a subtree. The primary
carries only a pointer::

    <Anexos><ReferenciaAnexo AlvoURN="urn:…;277!anexo1"/></Anexos>

and the annex is its own ``<LexML>``, with its own ``Metadado``, its own
``xsd:ID`` scope, ``PartePrincipal id="anexoN_pp"`` and tables named
``anexoN_tabM`` — the convention the reference parser uses for
``lei_5070_19660707.anexo1.xml``, matched exactly. That is also what makes
conservation checkable *across* the split rather than only within one file.

Two schema facts, measured against both shipped schemas rather than read off
the XSD:

* ``Anexo`` is a ``choice`` of ``DocumentoGenerico`` and ``DocumentoArticulado``
  — **never ``Norma``**, which both schemas reject. An annex here is always
  ``DocumentoGenerico``, mirroring the reference parser's ``isArticulatedAnexo``
  being false for ``port_mf_277`` (spec decision D-1).
* ``Anexos`` must follow ``ParteFinal`` inside ``Norma``: the ``Anexos`` /
  ``ParteFinal`` order is an ``xsd:sequence`` and reversing it fails on both
  schemas (D-2). :func:`anexos_element` returns the element; where it goes is
  the emitter's business.

**Why this module exists.** Cycle 5 delivered all of the above (A-5.6), and
Cycle 5b delivered it a second time so its annexes could nest. Cycle 6 needs it
a third time for the statutory route, and three copies of one ratified
convention is the "competing source of truth" A-3.4 refused. The two existing
copies are folded into this one; the 32 committed goldens are the proof that
folding them changed nothing.

``nested`` selects the annex body's form (**A-R.8**). It is an explicit flag,
never a capability probe: output that changed depending on which directories
exist on the machine would break determinism (§9.2) and make goldens
un-committable. ``generico`` and ``norma`` pass ``False``, ``generico-aninhado``
passes ``True``, and a nested annex is valid on ``lexml-proposed/`` and
correctly rejected on ``lexml/`` — which is what opt-in means.
"""

from __future__ import annotations

from lxml import etree

from ..model.document import DocumentModel
from .common import LEXML_NS, XLINK_NS, agrupamento, el

__all__ = [
    "ANEXO_FORMS",
    "anexo_urn",
    "anexos_element",
    "lexml_root",
    "render_anexo",
]

#: The two forms an annex body may take (A-R.8). Not a capability, a choice.
ANEXO_FORMS: tuple[str, ...] = ("flat", "nested")


def lexml_root() -> etree._Element:
    """An empty ``<LexML>`` root with both namespaces declared.

    Shared so the three emitters cannot drift on the nsmap — a difference there
    would change every golden without changing any behaviour.
    """
    return etree.Element(
        f"{{{LEXML_NS}}}LexML", nsmap={None: LEXML_NS, "xlink": XLINK_NS}
    )


def anexo_urn(model: DocumentModel, annex) -> str:
    """The annex's own URN — the primary's, plus its ``!anexoN`` fragment."""
    return model.metadata.urn_with_fragment(annex.fragment)


def anexos_element(model: DocumentModel) -> etree._Element | None:
    """``<Anexos>`` with one ``ReferenciaAnexo`` per annex, or ``None``.

    ``None`` rather than an empty element because ``Anexos`` requires at least
    one ``ReferenciaAnexo`` (``minOccurs="1"``) and an empty one is invalid.
    """
    if not model.annexes:
        return None
    anexos = el("Anexos")
    for annex in model.annexes:
        referencia = el("ReferenciaAnexo")
        referencia.set("AlvoURN", anexo_urn(model, annex))
        anexos.append(referencia)
    return anexos


def render_anexo(
    model: DocumentModel, annex, *, nested: bool = False
) -> etree._Element:
    """One annex as a standalone ``<LexML><Metadado/><Anexo>`` document.

    The two forms differ **only** in how the annex's sections are written —
    same ``anexoN_pp`` root, same ``anexoN_tabM`` tables, same ``!anexoN``
    fragment, same ``tituloAnexo`` block. That is what lets one conservation
    check cover both.
    """
    # Imported here: `generico` and `generico_aninhado` both import this
    # module, so a module-level import would close the cycle.
    from .generico import Scope, _tree_elements as _flat_tree_elements
    from .generico_aninhado import _tree_elements as _nested_tree_elements

    root = lexml_root()

    meta = el("Metadado")
    identificacao = el("Identificacao")
    identificacao.set("URN", anexo_urn(model, annex))
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

    tree_elements = _nested_tree_elements if nested else _flat_tree_elements
    for element in tree_elements(annex.tree, scope):
        parte.append(element)

    documento = el("DocumentoGenerico")
    if len(parte):
        documento.append(parte)

    anexo = el("Anexo")
    anexo.append(documento)
    root.append(anexo)
    return root
