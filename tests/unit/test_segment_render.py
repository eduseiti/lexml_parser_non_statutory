"""The two renderings of front and back matter, checked against both schemas.

There are two renderings because the schema leaves no choice, and this file is
where that claim stops being an assertion in a design document and becomes an
executable one.

``ParteInicial`` and ``ParteFinal`` are declared inside
``HierarchicalStructure`` only. ``Norma`` may carry them; ``DocumentoGenerico``
may not, and says so::

    Element 'ParteInicial': This element is not expected.
    Expected is one of ( PartePrincipal, Anexos )

Plan §4.4 routes **14 of the 15 samples** to ``generico``. A single rendering
would therefore have served either one sample or fourteen, never both — which
is Cycle 3 spec §2 Q1, and is why ``segment/render.py`` emits the native
elements for the statutory route and ``Agrupamento``-wrapped equivalents for
the open one.

Two further schema facts are pinned here as amendment **A-3.2**, because the
plan's own §4.3 snippet does not validate:

* ``LocalDataFecho`` and ``FormulaPromulgacao`` are ``textoSimplesType`` — they
  require an ``id`` *and* element-only content, so the text must be wrapped in
  ``<p>``;
* ``Epigrafe`` and ``Ementa`` are ``inlineReq`` — they require an ``id`` but
  take text directly.

Every fragment is validated against *both* ``lexml-br-rigido.xsd`` and
``lexml09-flexivel.xsd`` via ``validate(doc, "both")``, matching the Cycle 0
matrix style: the report's ``.ok`` is true only when both accepted it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.ingest import StyledDoc
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.segment import (
    render_back_generico,
    render_front_generico,
    render_parte_final,
    render_parte_inicial,
    segment_document,
)
from lexml_nonstat.validate import SCHEMA_NAMES, validate

from tests.conftest import REPO_ROOT, lexml_doc

STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"

SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in STYLED_DIR.glob("*.json")))

#: The sample with no front or back matter at all — the tolerance anchor.
BARE = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"

#: The one sample carrying all four front parts (spec §3.4).
FULL_FRONT = "ad_srf_22_19970430"

#: A minimal well-formed Articulacao, so `Norma` has a body to hold the
#: ParteInicial/ParteFinal we are actually testing. Shaped exactly as
#: `matrix_cases._artigo`: Rotulo first, Caput carrying its own Rotulo.
ART = (
    '<Articulacao><Artigo id="art1"><Rotulo>Art. 1º</Rotulo>'
    '<Caput id="art1_cpt"><Rotulo>Art. 1º</Rotulo><p>T</p></Caput></Artigo></Articulacao>'
)


def norma_doc(pi_xml: str, pf_xml: str) -> str:
    """A complete `Norma` document wrapping the statutory-route fragments."""
    return lexml_doc(f"<Norma>{pi_xml}{ART}{pf_xml}</Norma>")


def generico_doc(front_xml: str, back_xml: str) -> str:
    """A complete `DocumentoGenerico` wrapping the open-route fragments."""
    return lexml_doc(
        f'<DocumentoGenerico><PartePrincipal id="pp1">'
        f"{front_xml}<p>corpo</p>{back_xml}"
        f"</PartePrincipal></DocumentoGenerico>"
    )


def xml(element) -> str:
    """Serialise an element, or the empty string when there is nothing to emit."""
    if element is None:
        return ""
    return etree.tostring(element, encoding="unicode")


def xml_all(elements) -> str:
    """Serialise a tuple of elements in order."""
    return "".join(xml(e) for e in elements)


def load(name: str) -> StyledDoc:
    return StyledDoc.from_json((STYLED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def segment(name: str):
    doc = load(name)
    return doc, segment_document(
        doc, metadata=extract_metadata(doc, filename=f"{name}.docx")
    )


def assert_valid(document: str, context: str) -> None:
    """Assert a document validates on *both* schemas, quoting the report if not."""
    report = validate(document, "both")
    assert report.ok, f"{context}\n{report.summary()}\n{document[:2000]}"


def assert_invalid(document: str, context: str) -> None:
    """Assert a document is rejected by *every* consulted schema."""
    report = validate(document, "both")
    assert not report.ok, f"{context}: unexpectedly validated\n{document[:2000]}"
    assert len(report.failed) == len(SCHEMA_NAMES), (
        f"{context}: expected rejection on both schemas, "
        f"got only {[r.schema for r in report.failed]}"
    )


def test_corpus_is_the_expected_fifteen():
    assert len(SAMPLES) == 15, SAMPLES
    assert BARE in SAMPLES
    assert FULL_FRONT in SAMPLES


# --------------------------------------------------------------------------
# Plan Cycle 3 exit bullet: the statutory fragments validate on both schemas
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_parte_inicial_validates_all_samples(name: str):
    """Every sample's `<ParteInicial>` validates inside `Norma`, on both schemas.

    This discharges the plan's Cycle 3 exit bullet "``ParteInicial``/
    ``ParteFinal`` fragments validate on both schemas". A sample with no front
    matter renders nothing, and an empty `ParteInicial` is not emitted — the
    `Norma` is still checked, so the wrapper itself stays honest.
    """
    doc, seg = segment(name)
    fragment = xml(render_parte_inicial(seg.front, doc))

    assert_valid(norma_doc(fragment, ""), f"{name}: ParteInicial in Norma")


@pytest.mark.parametrize("name", SAMPLES)
def test_parte_final_validates_all_samples(name: str):
    """Every sample's `<ParteFinal>` validates inside `Norma`, on both schemas.

    The other half of the same exit bullet. `parecer_93` is the demanding case:
    it carries two signatures (spec §2 Q4 — the parecer's own and the appended
    DESPACHO's), and `ParteFinal` must accept both without a second
    `LocalDataFecho`.
    """
    doc, seg = segment(name)
    fragment = xml(render_parte_final(seg.back, doc))

    assert_valid(norma_doc("", fragment), f"{name}: ParteFinal in Norma")


@pytest.mark.parametrize("name", SAMPLES)
def test_parte_inicial_and_final_validate_together(name: str):
    """Both statutory fragments in one `Norma`, in schema-sequence order.

    Checked jointly as well as separately, because `HierarchicalStructure` is
    an `xsd:sequence`: two fragments that each validate alone can still be
    rejected in combination.
    """
    doc, seg = segment(name)
    document = norma_doc(
        xml(render_parte_inicial(seg.front, doc)),
        xml(render_parte_final(seg.back, doc)),
    )

    assert_valid(document, f"{name}: ParteInicial + ParteFinal in Norma")


# --------------------------------------------------------------------------
# A-3.2 — the plan's own §4.3 snippet is invalid
# --------------------------------------------------------------------------


def test_local_data_fecho_requires_id_and_p():
    """Amendment **A-3.2**: `LocalDataFecho` is `textoSimplesType`.

    The plan's §4.3 example is::

        <LocalDataFecho>Brasília, 7 de junho de 2018.</LocalDataFecho>

    and both schemas reject it twice over — the `id` attribute is required, and
    the content type is element-only, so bare character content is not allowed.
    The verified shape wraps the text in `<p>` and carries an `id`.

    Pinned here so that a schema revision breaks a named test instead of
    silently invalidating everything Cycles 5 and 6 emit.
    """
    valid_shape = (
        '<LocalDataFecho id="ldf1"><p>Brasília, 7 de junho de 2018.</p></LocalDataFecho>'
    )
    assert_valid(norma_doc("", f"<ParteFinal>{valid_shape}</ParteFinal>"),
                 "A-3.2 LocalDataFecho with id and <p>")

    plan_shape = "<LocalDataFecho>Brasília, 7 de junho de 2018.</LocalDataFecho>"
    assert_invalid(norma_doc("", f"<ParteFinal>{plan_shape}</ParteFinal>"),
                   "A-3.2 the plan's original bare-text LocalDataFecho")


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param('<LocalDataFecho><p>Brasília.</p></LocalDataFecho>', id="no-id"),
        pytest.param('<LocalDataFecho id="ldf1">Brasília.</LocalDataFecho>', id="no-p"),
    ],
)
def test_local_data_fecho_needs_both_halves(shape: str):
    """Each half of A-3.2 is independently required: drop either and it fails."""
    assert_invalid(norma_doc("", f"<ParteFinal>{shape}</ParteFinal>"),
                   f"A-3.2 partial shape {shape}")


def test_formula_promulgacao_requires_id_and_p():
    """Amendment **A-3.2** again: `FormulaPromulgacao` is `textoSimplesType` too.

    The enacting formula (``DECLARA,`` / ``RESOLVE:``) takes exactly the same
    shape as the closing date, for exactly the same reason — same schema type,
    same two requirements.
    """
    valid_shape = '<FormulaPromulgacao id="fp1"><p>DECLARA,</p></FormulaPromulgacao>'
    assert_valid(norma_doc(f"<ParteInicial>{valid_shape}</ParteInicial>", ""),
                 "A-3.2 FormulaPromulgacao with id and <p>")

    bare_text = "<FormulaPromulgacao>DECLARA,</FormulaPromulgacao>"
    assert_invalid(norma_doc(f"<ParteInicial>{bare_text}</ParteInicial>", ""),
                   "A-3.2 bare-text FormulaPromulgacao")

    no_id = "<FormulaPromulgacao><p>DECLARA,</p></FormulaPromulgacao>"
    assert_invalid(norma_doc(f"<ParteInicial>{no_id}</ParteInicial>", ""),
                   "A-3.2 FormulaPromulgacao without id")


def test_epigrafe_requires_id():
    """`Epigrafe` is `inlineReq`: `id` required, but text goes in directly.

    The contrast with `LocalDataFecho` is the point — both require an `id`, and
    only one of them wants `<p>`. Getting that backwards produces output that
    fails on the *other* half of A-3.2.
    """
    assert_invalid(norma_doc("<ParteInicial><Epigrafe>E</Epigrafe></ParteInicial>", ""),
                   "bare <Epigrafe> without id")

    assert_valid(
        norma_doc('<ParteInicial><Epigrafe id="epi1">E</Epigrafe></ParteInicial>', ""),
        "Epigrafe with id, text directly",
    )


def test_ementa_requires_id():
    """`Ementa` is `inlineReq` on the same terms as `Epigrafe`."""
    assert_invalid(
        norma_doc(
            '<ParteInicial><Epigrafe id="epi1">E</Epigrafe>'
            "<Ementa>Assunto.</Ementa></ParteInicial>",
            "",
        ),
        "bare <Ementa> without id",
    )

    assert_valid(
        norma_doc(
            '<ParteInicial><Epigrafe id="epi1">E</Epigrafe>'
            '<Ementa id="eme1">Assunto.</Ementa></ParteInicial>',
            "",
        ),
        "Ementa with id",
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_rendered_texto_simples_elements_carry_id_and_p(name: str):
    """The renderer obeys A-3.2 for real corpus output, not only for probes.

    Reading the constraint back off the emitted tree catches a renderer that
    validates by accident — because a sample happened to have no enacting
    formula, say — rather than by construction.
    """
    doc, seg = segment(name)
    ns = "{http://www.lexml.gov.br/1.0}"

    for element in (render_parte_inicial(seg.front, doc), render_parte_final(seg.back, doc)):
        if element is None:
            continue
        for tag in ("FormulaPromulgacao", "Preambulo", "LocalDataFecho"):
            for node in element.iter(f"{ns}{tag}"):
                assert node.get("id"), (name, tag, "missing id")
                assert not (node.text or "").strip(), (name, tag, "bare character content")
                assert len(node), (name, tag, "no <p> children")
                assert all(child.tag == f"{ns}p" for child in node)
        for tag in ("Epigrafe", "Ementa"):
            for node in element.iter(f"{ns}{tag}"):
                assert node.get("id"), (name, tag, "missing id")
                assert (node.text or "").strip(), (name, tag, "empty inlineReq")


# --------------------------------------------------------------------------
# Q1 — the finding that justifies two renderings
# --------------------------------------------------------------------------


def test_parte_inicial_rejected_in_documento_generico():
    """**This is the finding that justifies the whole two-rendering design.**

    `ParteInicial` belongs to `HierarchicalStructure`, which `Norma` uses and
    `DocumentoGenerico` does not. Put it inside a `DocumentoGenerico` and both
    schemas answer::

        Element 'ParteInicial': This element is not expected.
        Expected is one of ( PartePrincipal, Anexos )

    Since plan §4.4 routes 14 of 15 samples to `generico`, a Cycle 3 that
    emitted only `ParteInicial` would have produced front matter that 14
    samples cannot carry — hence `render_front_generico`. If this test ever
    starts failing because the element became legal there, the second rendering
    is redundant and the design should be revisited, which is why the assertion
    names the reason.
    """
    document = lexml_doc(
        "<DocumentoGenerico>"
        '<ParteInicial><Epigrafe id="epi1">E</Epigrafe></ParteInicial>'
        '<PartePrincipal id="pp1"><p>corpo</p></PartePrincipal>'
        "</DocumentoGenerico>"
    )
    assert_invalid(document, "Q1: ParteInicial inside DocumentoGenerico")

    report = validate(document, "both")
    assert any("ParteInicial" in e for e in report.all_errors), report.all_errors


def test_parte_final_rejected_in_documento_generico():
    """The same holds for the back-matter element — hence `render_back_generico`."""
    document = lexml_doc(
        "<DocumentoGenerico>"
        '<PartePrincipal id="pp1"><p>corpo</p></PartePrincipal>'
        '<ParteFinal><LocalDataFecho id="ldf1"><p>Brasília.</p></LocalDataFecho>'
        "</ParteFinal>"
        "</DocumentoGenerico>"
    )
    assert_invalid(document, "Q1: ParteFinal inside DocumentoGenerico")


def test_agrupamento_is_the_generico_substitute():
    """The replacement really is legal where the native element is not.

    Row B of the Cycle 0 matrix already establishes that
    `PartePrincipal/Agrupamento[@nome]/p` validates; asserted again here beside
    its rejected counterpart so the substitution reads as one fact.
    """
    assert_valid(
        generico_doc('<Agrupamento id="pp1_agr1" nome="epigrafe"><p>E</p></Agrupamento>', ""),
        "Agrupamento nome=epigrafe inside DocumentoGenerico",
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_front_generico_validates(name: str):
    """Every sample's open-route front matter validates, on both schemas."""
    doc, seg = segment(name)
    fragment = xml_all(render_front_generico(seg.front, doc))

    assert_valid(generico_doc(fragment, ""), f"{name}: front generico")


@pytest.mark.parametrize("name", SAMPLES)
def test_back_generico_validates(name: str):
    """Every sample's open-route back matter validates, on both schemas."""
    doc, seg = segment(name)
    fragment = xml_all(render_back_generico(seg.back, doc))

    assert_valid(generico_doc("", fragment), f"{name}: back generico")


@pytest.mark.parametrize("name", SAMPLES)
def test_generico_front_and_back_validate_together(name: str):
    """The whole open-route `PartePrincipal`, front and back in place."""
    doc, seg = segment(name)
    document = generico_doc(
        xml_all(render_front_generico(seg.front, doc)),
        xml_all(render_back_generico(seg.back, doc)),
    )

    assert_valid(document, f"{name}: front + back generico")


@pytest.mark.parametrize("name", SAMPLES)
def test_generico_agrupamentos_are_flat(name: str):
    """No `Agrupamento` nests inside another — the Cycle 0 §2.1 headline.

    `OpenStructure` cannot recurse, so the open rendering must stay one level
    deep. This checks the emitted tree directly rather than relying on the
    validator to notice.
    """
    doc, seg = segment(name)
    ns = "{http://www.lexml.gov.br/1.0}"

    for element in render_front_generico(seg.front, doc) + render_back_generico(seg.back, doc):
        assert element.tag == f"{ns}Agrupamento"
        assert element.get("nome"), "Agrupamento must be named"
        assert element.get("id"), "Agrupamento must carry an id"
        assert not list(element.iter(f"{ns}Agrupamento"))[1:], "nested Agrupamento"


# --------------------------------------------------------------------------
# Element order, emptiness, and cross-rendering equivalence
# --------------------------------------------------------------------------


def test_render_element_order():
    """`ParteInicial`'s children follow the schema sequence, not document order.

    `ad_srf_22` reads epigraph (block 0), ementa (1), preamble (2), then
    ``DECLARA,`` (3). The schema declares an `xsd:sequence`
    ``FormulaPromulgacao`` → ``Epigrafe`` → ``Ementa`` → ``Preambulo``, so the
    enacting formula that comes *last* in the document is emitted *first*. The
    schema sequence overrides document order; a renderer that preserved reading
    order would emit invalid output for exactly this sample.
    """
    doc, seg = segment(FULL_FRONT)

    # All four parts really are present, or the test proves nothing.
    assert seg.front.epigraph is not None
    assert seg.front.ementa is not None
    assert seg.front.preamble is not None
    assert seg.front.enacting_formula is not None

    # And the enacting formula does come last in the source.
    assert seg.front.enacting_formula.start > seg.front.epigraph.start
    assert seg.front.enacting_formula.start > seg.front.ementa.start
    assert seg.front.enacting_formula.start > seg.front.preamble.start

    element = render_parte_inicial(seg.front, doc)
    assert element is not None
    tags = [etree.QName(child).localname for child in element]

    assert tags == ["FormulaPromulgacao", "Epigrafe", "Ementa", "Preambulo"]
    assert_valid(norma_doc(xml(element), ""), f"{FULL_FRONT}: ordered ParteInicial")


def test_empty_front_renders_none():
    """`CARNE_LEAO` has no front matter, and nothing is invented for it.

    An empty `<ParteInicial/>` would not validate — and, worse, would assert a
    structure the source does not have, breaking the "no fabricated structure"
    invariant (plan §9.2). Both renderings decline instead.
    """
    doc, seg = segment(BARE)

    assert seg.front.is_empty
    assert render_parte_inicial(seg.front, doc) is None
    assert render_front_generico(seg.front, doc) == ()


def test_empty_back_renders_none():
    """`CARNE_LEAO` likewise has no signature and no closing date."""
    doc, seg = segment(BARE)

    assert seg.back.is_empty
    assert render_parte_final(seg.back, doc) is None
    assert render_back_generico(seg.back, doc) == ()


def test_empty_document_still_validates_both_routes():
    """The bare sample's empty renderings produce valid documents on both routes."""
    doc, seg = segment(BARE)

    assert_valid(norma_doc("", ""), "CARNE_LEAO: empty Norma route")
    assert_valid(generico_doc("", ""), "CARNE_LEAO: empty generico route")
    assert xml(render_parte_inicial(seg.front, doc)) == ""


def _words(elements) -> set[str]:
    """Every non-whitespace word carried by a set of rendered elements."""
    words: set[str] = set()
    for element in elements:
        if element is None:
            continue
        for text in element.itertext():
            words.update(re.split(r"\s+", text.strip()))
    words.discard("")
    return words


@pytest.mark.parametrize("name", SAMPLES)
def test_cross_rendering_text_equivalence(name: str):
    """Both renderings of a document carry exactly the same text.

    **This pre-figures plan invariant #11, cross-emitter equivalence**: the
    `norma` and `generico` emitters must be two spellings of one segmentation,
    differing in structure and not in content. Asserting it already at the
    fragment level means Cycles 5 and 6 inherit a guarantee rather than a hope.

    Comparison is on the set of whitespace-normalised tokens, because the two
    shapes legitimately differ in how text is distributed across elements — one
    `<Ementa>` of joined lines against an `<Agrupamento>` of one `<p>` per line.
    """
    doc, seg = segment(name)

    norma_words = _words(
        [render_parte_inicial(seg.front, doc), render_parte_final(seg.back, doc)]
    )
    generico_words = _words(
        render_front_generico(seg.front, doc) + render_back_generico(seg.back, doc)
    )

    assert norma_words == generico_words, (
        f"{name}: renderings diverge\n"
        f"only in norma: {sorted(norma_words - generico_words)[:20]}\n"
        f"only in generico: {sorted(generico_words - norma_words)[:20]}"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_ids_unique_within_rendering(name: str):
    """Every emitted `id` is unique — plan §9.2's `id` uniqueness invariant.

    Checked across both renderings of the same document together, since the two
    share a segmentation and a prefix scheme; a collision between them would
    become a real collision the moment either is embedded in a whole document.
    """
    doc, seg = segment(name)

    for label, elements in (
        ("norma", (render_parte_inicial(seg.front, doc), render_parte_final(seg.back, doc))),
        ("generico", render_front_generico(seg.front, doc) + render_back_generico(seg.back, doc)),
    ):
        ids: list[str] = []
        for element in elements:
            if element is None:
                continue
            for node in element.iter():
                value = node.get("id")
                if value is not None:
                    ids.append(value)

        assert len(ids) == len(set(ids)), f"{name} ({label}): duplicate ids in {ids}"


@pytest.mark.parametrize("name", SAMPLES)
def test_rendering_is_deterministic(name: str):
    """Rendering the same segmentation twice yields byte-identical XML.

    Determinism is a cross-cutting invariant (plan §9.2) and the precondition
    for the goldens this cycle commits.
    """
    doc, seg = segment(name)

    first = (
        xml(render_parte_inicial(seg.front, doc)),
        xml(render_parte_final(seg.back, doc)),
        xml_all(render_front_generico(seg.front, doc)),
        xml_all(render_back_generico(seg.back, doc)),
    )
    second = (
        xml(render_parte_inicial(seg.front, doc)),
        xml(render_parte_final(seg.back, doc)),
        xml_all(render_front_generico(seg.front, doc)),
        xml_all(render_back_generico(seg.back, doc)),
    )

    assert first == second


@pytest.mark.parametrize("name", SAMPLES)
def test_prefix_is_honoured(name: str):
    """A caller-supplied prefix reaches every emitted `id`.

    Cycles 5 and 6 place these fragments inside a whole document, where ids
    must be unique across it. The prefix is how they arrange that, so an
    ignored prefix is a latent collision.
    """
    doc, seg = segment(name)

    element = render_parte_inicial(seg.front, doc, prefix="x_")
    if element is not None:
        for node in element.iter():
            value = node.get("id")
            if value is not None:
                assert value.startswith("x_"), (name, value)

    for element in render_front_generico(seg.front, doc, prefix="zz1"):
        assert element.get("id", "").startswith("zz1"), (name, element.get("id"))
