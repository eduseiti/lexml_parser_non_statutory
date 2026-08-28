"""The two renderings of front and back matter.

There are two because the schema gives no choice. ``ParteInicial`` and
``ParteFinal`` are declared inside ``HierarchicalStructure`` only, so they are
available to ``Norma`` and rejected inside ``DocumentoGenerico``::

    Element 'ParteInicial': This element is not expected.
    Expected is one of ( PartePrincipal, Anexos )

Plan §4.4 routes 14 of the 15 samples to ``generico``, which is
``DocumentoGenerico``. A single rendering would therefore have served either
one sample or fourteen, never both — so this module emits the native elements
for the statutory route and ``Agrupamento``-wrapped equivalents for the open
one. Both shapes were probed against both schemas before being written.

**The plan's §4.3 snippet is not valid and was amended (A-3.2).**
``LocalDataFecho`` and ``FormulaPromulgacao`` are ``textoSimplesType``: they
require an ``id`` *and* element-only content, so the text must be wrapped in
``<p>``. ``Epigrafe`` and ``Ementa`` are ``inlineReq`` and require an ``id``
but take text directly::

    <LocalDataFecho id="ldf1"><p>Brasília, 7 de junho de 2018.</p></LocalDataFecho>

Element order inside ``ParteInicial`` is a schema ``xsd:sequence`` —
``FormulaPromulgacao``, ``Epigrafe``, ``Ementa``, ``Preambulo`` — and is not
document order. ``ad_srf_22`` reads epigraph, ementa, preamble, *then*
``DECLARA``; the formula is emitted first regardless.
"""

from __future__ import annotations

from lxml import etree

from ..ingest import StyledDoc
from .model import BackMatter, FrontMatter, Span

__all__ = [
    "LEXML_NS",
    "render_back_generico",
    "render_front_generico",
    "render_parte_final",
    "render_parte_inicial",
]

LEXML_NS = "http://www.lexml.gov.br/1.0"


def _el(tag: str, **attrs: str) -> etree._Element:
    element = etree.Element(f"{{{LEXML_NS}}}{tag}", nsmap={None: LEXML_NS})
    for name, value in attrs.items():
        element.set(name, value)
    return element


def _lines(span: Span | None, doc: StyledDoc) -> list[str]:
    """The non-blank text lines of ``span``."""
    if span is None:
        return []
    text = span.text(doc)
    return [line for line in text.split("\n") if line.strip()]


def _texto_simples(tag: str, span: Span | None, doc: StyledDoc, ident: str):
    """A ``textoSimplesType`` element: ``id`` required, ``<p>`` children only."""
    lines = _lines(span, doc)
    if not lines:
        return None
    element = _el(tag, id=ident)
    for line in lines:
        paragraph = _el("p")
        paragraph.text = line
        element.append(paragraph)
    return element


def _inline_req(tag: str, span: Span | None, doc: StyledDoc, ident: str):
    """An ``inlineReq`` element: ``id`` required, text content directly."""
    lines = _lines(span, doc)
    if not lines:
        return None
    element = _el(tag, id=ident)
    element.text = " ".join(lines)
    return element


def render_parte_inicial(
    front: FrontMatter, doc: StyledDoc, *, prefix: str = ""
) -> etree._Element | None:
    """``<ParteInicial>`` for the statutory route, or ``None`` if empty.

    Children are emitted in the schema's sequence order, which is not
    document order.
    """
    if front.is_empty:
        return None

    element = _el("ParteInicial")
    children = (
        _texto_simples(
            "FormulaPromulgacao", front.enacting_formula, doc, f"{prefix}fp1"
        ),
        _inline_req("Epigrafe", front.epigraph, doc, f"{prefix}epi1"),
        _inline_req("Ementa", front.ementa, doc, f"{prefix}eme1"),
        _texto_simples("Preambulo", front.preamble, doc, f"{prefix}pre1"),
    )
    for child in children:
        if child is not None:
            element.append(child)

    return element if len(element) else None


def render_parte_final(
    back: BackMatter, doc: StyledDoc, *, prefix: str = ""
) -> etree._Element | None:
    """``<ParteFinal>`` for the statutory route, or ``None`` if empty.

    The closing date comes from the first signature that carries one, since
    ``ParteFinal`` allows a single ``LocalDataFecho`` before the signatures.
    """
    if back.is_empty:
        return None

    element = _el("ParteFinal")

    closing_text: str | None = next(
        (s.local_date for s in back.signatures if s.local_date), None
    )
    if closing_text is None and back.local_date is not None:
        lines = _lines(back.local_date, doc)
        closing_text = lines[0] if lines else None

    if closing_text:
        closing = _el("LocalDataFecho", id=f"{prefix}ldf1")
        paragraph = _el("p")
        paragraph.text = closing_text
        closing.append(paragraph)
        element.append(closing)

    for signature in back.signatures:
        assinatura = _el("Assinatura")
        nome = _el("NomePessoa")
        nome.text = signature.name
        assinatura.append(nome)
        if signature.cargo:
            cargo = _el("Cargo")
            cargo.text = signature.cargo
            assinatura.append(cargo)
        element.append(assinatura)

    return element if len(element) else None


def _agrupamento(nome: str, ident: str, lines: list[str]) -> etree._Element:
    """An ``<Agrupamento nome=…>`` carrying one ``<p>`` per line."""
    element = _el("Agrupamento", id=ident, nome=nome)
    for line in lines:
        paragraph = _el("p")
        paragraph.text = line
        element.append(paragraph)
    return element


def render_front_generico(
    front: FrontMatter, doc: StyledDoc, *, prefix: str = "pp1"
) -> tuple[etree._Element, ...]:
    """Front matter for the open route, as ``Agrupamento`` blocks.

    ``DocumentoGenerico`` has no ``ParteInicial``, so each part becomes a named
    ``Agrupamento``. The names mirror the statutory element names, which is
    what lets a segment carry the same meaning whichever emitter produced it.
    """
    if front.is_empty:
        return ()

    parts = (
        ("epigrafe", front.epigraph),
        ("ementa", front.ementa),
        ("preambulo", front.preamble),
        ("formulaPromulgacao", front.enacting_formula),
    )

    out: list[etree._Element] = []
    for ordinal, (nome, span) in enumerate(parts, start=1):
        lines = _lines(span, doc)
        if lines:
            out.append(_agrupamento(nome, f"{prefix}_agr{ordinal}", lines))
    return tuple(out)


def render_back_generico(
    back: BackMatter, doc: StyledDoc, *, prefix: str = "pp1"
) -> tuple[etree._Element, ...]:
    """Back matter for the open route, as ``Agrupamento`` blocks.

    ``Assinatura`` is likewise unavailable inside ``DocumentoGenerico``, so a
    signature becomes an ``Agrupamento nome="assinatura"`` whose lines are the
    closing date, the name and the office — preserving the text, which is what
    the conservation invariant requires, at the cost of the typing.
    """
    if back.is_empty:
        return ()

    out: list[etree._Element] = []
    ordinal = 0

    if back.local_date is not None and not any(
        s.local_date for s in back.signatures
    ):
        lines = _lines(back.local_date, doc)
        if lines:
            ordinal += 1
            out.append(
                _agrupamento("localDataFecho", f"{prefix}_agrf{ordinal}", lines)
            )

    for signature in back.signatures:
        ordinal += 1
        lines = [
            line
            for line in (signature.local_date, signature.name, signature.cargo)
            if line
        ]
        out.append(_agrupamento("assinatura", f"{prefix}_agrf{ordinal}", lines))

    return tuple(out)
