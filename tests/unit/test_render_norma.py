"""The statutory `norma` emitter, and the four schema facts it was built against.

One sample in fifteen routes here — `port_mf_277_20180607`, whose two genuine
articles survive Cycle 4's quotation guard while its 130-entry `ANEXO ÚNICO`
splits off as a sibling document. That is a thin corpus for an emitter with four
dispositivo levels, and thinness is the organising problem of this module: a
single positive sample can show that the emitter *works*, but it cannot show
that any of the constraints it obeys are real. So the tests come in two kinds.

**Corpus tests** assert what `port_mf_277` actually produces: two `Artigo`s with
the reference convention's ids, the `Caput`'s duplicated `Rotulo`, `Anexos` after
`ParteFinal`, Cycle 3's `ParteInicial` reused rather than rewritten, and
determinism across two renders.

**Negative schema tests** are the ones with teeth, and they exist because
spec §2's decisions D-4, A-6.1 and Q-1 are each a claim about what the schemas
*reject*. A test that only ever validates correct output would pass just as
happily against a schema that accepts anything — so `pp1_art1`, a `Caput` before
its `Rotulo`, and an `Artigo` with no `Rotulo` at all are each hand-built and
asserted **invalid on both shipped schemas**. Those three assertions are what
make the positive ones evidence. In particular they are asserted against the XSD
itself and not against a check of our own, which is the point spec D-4 makes:
the mis-ordering test is only worth writing because the schema, not this module,
is the authority on element order.

**Synthetic fixtures**, following the standing A-1.3 / A-4.6 precedent. The
corpus exercises only `Artigo` + `Caput`. Nothing in fifteen samples produces a
`Paragrafo`, an `Inciso`, an `Artigo único`, a `Parágrafo único`, an enacting
formula on the statutory route, or front-matter residue needing to be folded
into `Preambulo` — yet each of those is code that ships, and each of A-6.2, D-5
and Q-3 is a decision that would go unchecked without one. `synthetic()` below
therefore builds a real `StyledDoc` and a real `DocumentModel` with a hand-made
`Segmentation` and `HierarchyDoc`, so the emitter runs its ordinary code path
over hand-chosen input. Nothing here is a mock: `build_model` accepts pre-built
components precisely so a test can supply them.

One measurement recorded here rather than assumed: `parse_label`'s `ARTICLE_RE`
requires digits (`Art\\.?\\s*(\\d+)`), so the string `Art. único` is **not** a
label and `build_articulacao` can never reach its `unico` branch from a document —
the emitter says so in its own comment, and deliberately does not invent a number
the grammar refused to read (A-R.6). `DispositivoIds.artigo(None, unico=True)` is
therefore tested at the allocator level, which is where D-5's `art1u` claim
actually lives, rather than end to end through a document that cannot produce it.
The `Parágrafo único` case *does* run end to end, because `_PARAGRAFO_UNICO_RE`
matches both spellings — and it is the case that caught a real defect: see
`test_paragrafo_unico_id`.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.hierarchy import HierarchyDoc
from lexml_nonstat.hierarchy.tree import HierarchyTree
from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara, read_docx
from lexml_nonstat.model import DocumentModel, build_model
from lexml_nonstat.model.nodes import ListItem, ListNode, Para, Section, Table
from lexml_nonstat.render.common import local_name, to_xml_string
from lexml_nonstat.render.norma import (
    ARTIGO_ID_RE,
    BLOCKER_BACK_RESIDUE,
    BLOCKER_INVALID,
    EMITTER,
    Artigo,
    Caput,
    DispositivoIds,
    Inciso,
    Paragrafo,
    back_residue,
    build_articulacao,
    render_articulacao,
    render_norma,
    render_norma_checked,
)
from lexml_nonstat.segment.model import (
    BackMatter,
    FrontMatter,
    Segmentation,
    Signature,
    Span,
)
from lexml_nonstat.validate import SHIPPED, load_schemas

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"

LEX = "{http://www.lexml.gov.br/1.0}"

#: The one sample plan §4.4 routes to `norma`. Named rather than discovered:
#: if routing ever sends a second document here, or none, a test that silently
#: adapted would stop being about this emitter at all.
NORMA_SAMPLE = "port_mf_277_20180607"

# A test that names a sample is only as good as the name still existing, so
# collection fails loudly on a rename rather than quietly skipping.
assert (SAMPLES_DIR / f"{NORMA_SAMPLE}.docx").exists(), NORMA_SAMPLE

#: Reading and modelling the sample takes about a second; once per test would
#: not be free, and every test below wants the same immutable objects.
_CACHE: dict[str, tuple[DocumentModel, object]] = {}


def sample() -> tuple[DocumentModel, object]:
    """The norma-routed sample's model and its ungated statutory bundle."""
    if NORMA_SAMPLE not in _CACHE:
        path = SAMPLES_DIR / f"{NORMA_SAMPLE}.docx"
        model = build_model(read_docx(path), filename=path.name)
        _CACHE[NORMA_SAMPLE] = (model, render_norma(model))
    return _CACHE[NORMA_SAMPLE]


def sample_model() -> DocumentModel:
    return sample()[0]


def sample_bundle():
    return sample()[1]


# --------------------------------------------------------------------------
# Readers — deliberately independent of the emitter's own helpers
# --------------------------------------------------------------------------


def norma_element(document: etree._Element) -> etree._Element:
    """The document's `<Norma>`; fails loudly rather than returning `None`.

    Every assertion below is about what is *inside* `Norma`, so a missing one
    should read as "this is not a statutory document" and not as an
    `AttributeError` fifteen lines later.
    """
    found = list(document.iter(f"{LEX}Norma"))
    assert found, (
        "no <Norma> in the emitted document; children are "
        f"{[local_name(c.tag) for c in document]}"
    )
    return found[0]


def child_names(element: etree._Element) -> list[str]:
    """Local names of the direct children, in document order."""
    return [local_name(child.tag) for child in element]


def artigos(document: etree._Element) -> list[etree._Element]:
    return list(document.iter(f"{LEX}Artigo"))


def find_all(document: etree._Element, tag: str) -> list[etree._Element]:
    return list(document.iter(f"{LEX}{tag}"))


def child_named(element: etree._Element, tag: str) -> list[etree._Element]:
    """Direct children with that local name — never descendants.

    Direct-child selection matters inside an `Artigo`: `iter()` would reach the
    `Caput`'s own `Rotulo` and make "the article's rótulo" the wrong element.
    """
    return [c for c in element if local_name(c.tag) == tag]


def text_of(element: etree._Element | None) -> str | None:
    """An element's whitespace-collapsed string value, `None` when absent."""
    if element is None:
        return None
    return " ".join("".join(element.itertext()).split()) or None


def schemas():
    """Both shipped schemas, loaded once by the module's own cache."""
    return load_schemas(generation=SHIPPED)


def validity(document: etree._Element) -> dict[str, str]:
    """`{schema name: ""}` when valid, `{name: the XSD's complaint}` when not.

    Returning the message rather than a bool is what makes a failure a finding:
    "invalid" alone does not say which schema objected or to what.
    """
    out: dict[str, str] = {}
    for name, schema in schemas().items():
        if schema.validate(document):
            out[name] = ""
        else:
            message = str(schema.error_log[0].message) if len(schema.error_log) else "?"
            out[name] = message
    return out


def assert_valid(document: etree._Element, what: str) -> None:
    report = validity(document)
    bad = {name: message for name, message in report.items() if message}
    assert not bad, f"{what} is rejected: {bad}"


def assert_invalid(document: etree._Element, what: str) -> None:
    report = validity(document)
    good = [name for name, message in report.items() if not message]
    assert not good, (
        f"{what} was accepted by {good}; the constraint it is supposed to "
        "violate does not exist, and every positive test resting on it is "
        f"vacuous.\n{to_xml_string(document)}"
    )


# --------------------------------------------------------------------------
# Hand-built documents — for the negative schema tests
# --------------------------------------------------------------------------

#: The sample's own URN, so a hand-built document differs from a real one only
#: in the structure under test.
URN = "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277"


def hand_built(articulacao_xml: str) -> etree._Element:
    """A minimal `Norma` document carrying exactly `articulacao_xml`.

    Written as a string rather than through the emitter on purpose: these are
    the shapes the emitter must *never* produce, so building them with its own
    helpers would only prove that the helpers refuse to build them.
    """
    return etree.fromstring(
        f'<LexML xmlns="http://www.lexml.gov.br/1.0">'
        f'<Metadado><Identificacao URN="{URN}"/></Metadado>'
        f"<Norma>{articulacao_xml}</Norma>"
        f"</LexML>".encode("utf-8")
    )


# --------------------------------------------------------------------------
# Synthetic fixtures — where the corpus cannot discriminate (A-1.3 / A-4.6)
# --------------------------------------------------------------------------


def synthetic(
    texts: tuple[str, ...],
    *,
    body: tuple[int, ...],
    front: FrontMatter | None = None,
    back: BackMatter | None = None,
) -> DocumentModel:
    """A `DocumentModel` whose blocks are `texts` and whose body is `body`.

    Real `StyledDoc`, real `Metadata`, hand-made `Segmentation` and
    `HierarchyDoc`. Supplying the last two rather than letting `build_model`
    infer them is the whole point: the inferred segmentation of a three-line
    document reads its first article as an ementa, which would make every
    assertion below about the segmenter rather than about the emitter. The
    components are the real dataclasses and the emitter runs unchanged over
    them — this is the A-1.3 / A-4.6 synthetic-fixture precedent, not a mock.

    `route` is forced to `norma` because these documents are never routed at
    all; routing is Cycle 4b's subject and has its own suite.
    """
    blocks = tuple(
        StyledPara(inlines=(Inline(text),), index=index)
        for index, text in enumerate(texts)
    )
    doc = StyledDoc(blocks=blocks, source="synthetic.docx")
    segmentation = Segmentation(
        front=front if front is not None else FrontMatter(),
        body=Span(min(body), max(body)) if body else None,
        back=back if back is not None else BackMatter(),
        first_index=0,
    )
    preamble = tuple(
        Para(inlines=(Inline(texts[index]),), source_indices=(index,)) for index in body
    )
    model = build_model(
        doc,
        filename="synthetic.docx",
        segmentation=segmentation,
        hierarchy=HierarchyDoc(body=HierarchyTree(preamble=preamble)),
    )
    return dataclasses.replace(model, route=EMITTER)


# --------------------------------------------------------------------------
# The sample — the emitter does what §4.3 says on the one document that routes
# --------------------------------------------------------------------------


def test_port_mf_277_renders_norma() -> None:
    """The one norma-routed sample emits a `Norma` with an `Articulacao`.

    The plan's first bullet, and the smallest statement this cycle can make.
    Both halves matter: `emitter == "norma"` is what the artifact *claims* it
    is, and `Norma/Articulacao` is what it actually contains. An emitter that
    labelled its output `norma` while emitting a `DocumentoGenerico` would pass
    half of this and be wrong in the half that a consumer reads.

    The route is asserted too, because if Cycle 4b ever stopped sending this
    sample to `norma` the rest of this module would be testing an emitter no
    document reaches.
    """
    model, bundle = sample()

    assert model.route == EMITTER, (
        f"{NORMA_SAMPLE} is routed to {model.route!r}, so the statutory "
        "emitter has no document in the corpus"
    )
    assert bundle.emitter == EMITTER, bundle.emitter

    norma = norma_element(bundle.primary)
    assert "Articulacao" in child_names(norma), child_names(norma)


def test_primary_validates_both_schemas() -> None:
    """The statutory primary is valid on `lexml/`'s two schemas — E-1.

    Both, not either: `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd` disagree
    about how much they constrain, and the project's standing rule (CLAUDE.md,
    "dual-schema validation") is that output must satisfy the stricter one as
    well. `flexivel` is the one that carries the `idArtigo` pattern this cycle
    had to be redesigned around, so validating only against `rigido` would let
    A-6.1's entire reason for existing pass unnoticed.

    Only the primary here; the annex is `tests/unit/test_render_anexo.py`'s
    subject and the bundle-wide claim is the regression suite's.
    """
    assert_valid(sample_bundle().primary, f"{NORMA_SAMPLE}'s statutory primary")


def test_two_articles_two_artigo_elements() -> None:
    """`port_mf_277`'s two articles become exactly two `Artigo`s — §4.3.

    "Exactly" is the assertion. Cycle 4b measured `articles_own = 2` for this
    document, and the failure this guards is not producing too few — that would
    fail conservation loudly — but producing too *many*, by reading the
    preamble's citation of `art. 87` or `art. 75` of other laws as an article of
    this one. The rótulos are compared as well, so an emitter that found two
    `Artigo`s made of the wrong paragraphs does not pass.
    """
    found = artigos(sample_bundle().primary)
    labels = [text_of(child_named(a, "Rotulo")[0]) for a in found]

    assert labels == ["Art. 1º", "Art. 2º"], (
        f"expected the sample's two articles, got {len(found)}: {labels}"
    )


def test_artigo_ids_are_reference_convention() -> None:
    """Ids are `art1`/`art2` and `art1_cpt`/`art2_cpt` — E-2.

    The reference convention, not an invention of ours: these ids are what a
    LexML consumer cites, so a document whose article 1 is `art0` or `artigo1`
    is citable only by someone who has read our source. Asserted as an exact
    ordered list rather than a membership test, because the pairing between an
    article and its caput is the part that a renumbering bug would break while
    leaving the id *set* intact.
    """
    found = artigos(sample_bundle().primary)
    pairs = [
        (a.get("id"), child_named(a, "Caput")[0].get("id")) for a in found
    ]

    assert pairs == [("art1", "art1_cpt"), ("art2", "art2_cpt")], pairs


def test_caput_carries_its_own_rotulo() -> None:
    """Every `Caput` repeats its `Artigo`'s rótulo — spec decision D-3.

    Convention rather than necessity, and that is exactly why it needs a test.
    Probe N4 measured a `Caput` *without* a `Rotulo` to be valid too, so the
    schema will never notice if this is dropped; §4.3's snippet does it and the
    reference parser does it, and matching the reference is the whole reason a
    consumer's XSLT written against real LexML works on our output.

    The duplication has a conservation consequence, discharged in Cycle 5's
    `common.py` by A-6.4: `leaf_texts` skips a `Caput`'s `Rotulo` precisely
    because the source wrote that rótulo once. This test is the other half of
    that pair — it asserts the copy is really there to be skipped.
    """
    for artigo in artigos(sample_bundle().primary):
        caput = child_named(artigo, "Caput")[0]
        rotulos = child_named(caput, "Rotulo")
        assert rotulos, (
            f"{caput.get('id')} has no Rotulo of its own; children are "
            f"{child_names(caput)}"
        )
        assert text_of(rotulos[0]) == text_of(child_named(artigo, "Rotulo")[0]), (
            f"{caput.get('id')}'s rótulo {text_of(rotulos[0])!r} does not "
            f"repeat its article's {text_of(child_named(artigo, 'Rotulo')[0])!r}"
        )


def test_rotulo_precedes_caput() -> None:
    """`Rotulo` is the first child of every `Artigo`, before `Caput` — D-4.

    The schema's `xsd:sequence`, asserted here on real output so that a failure
    names the element rather than arriving as "Caput: this element is not
    expected" from the XSD on some document. `test_misordered_tree_fails_
    validation` is its negative twin and proves the ordering is the schema's
    rule and not merely our habit.
    """
    for artigo in artigos(sample_bundle().primary):
        names = child_names(artigo)
        assert names[0] == "Rotulo", (
            f"{artigo.get('id')} opens with {names[0]!r}, not Rotulo: {names}"
        )
        assert names.index("Rotulo") < names.index("Caput"), names


def test_dispositivo_ids_match_flexivel_pattern() -> None:
    """Every emitted dispositivo id satisfies `ARTIGO_ID_RE` — A-6.1.

    The fast check. `ARTIGO_ID_RE` is a transcription of `lexml09-flexivel`'s
    `idArtigo` pattern, and a transcription can drift from its original, so the
    schema stays the authority: `test_primary_validates_both_schemas` is the
    slow check over the same ids, and `test_path_composed_artigo_id_is_rejected`
    is what proves the schema really enforces the pattern at all. This test adds
    the thing neither of those gives — a failure that names the offending id.

    Scoped to the dispositivo elements. The front matter's `epi1`/`eme1`/`pre1`
    and the annex's `anexo1_pp` belong to Cycle 5's *other* id grammar, and the
    two never meet inside one element (A-6.1's coexistence argument).
    """
    document = sample_bundle().primary
    idents = [
        node.get("id")
        for tag in ("Artigo", "Caput", "Paragrafo", "Inciso")
        for node in find_all(document, tag)
    ]

    assert idents, "no dispositivo carried an id; the check would be vacuous"
    offenders = [i for i in idents if i is None or not ARTIGO_ID_RE.match(i)]
    assert not offenders, (
        f"{offenders} do not match the flexivel idArtigo pattern "
        f"{ARTIGO_ID_RE.pattern}"
    )


def test_parte_inicial_reuses_cycle_3() -> None:
    """The front matter is Cycle 3's `ParteInicial`, ids and all — §3.1 reuse.

    Cycle 3 delivered `render_parte_inicial()` and probed it valid ×15
    (A-3.1, A-3.2); Cycle 6 wires it. The ids `epi1`, `eme1`, `pre1` are that
    module's, so finding them here is what shows the statutory front matter was
    reused rather than reimplemented — a second implementation would be the
    competing source of truth A-3.4 refused, and would drift the moment either
    side changed.

    `Preambulo` is checked to hold `<p>` children rather than bare text because
    it is `textoSimplesType` (A-3.2): the same fact that makes A-6.2's residue
    folding possible at all.
    """
    parte_inicial = find_all(sample_bundle().primary, "ParteInicial")
    assert parte_inicial, "the sample has front matter but no ParteInicial"

    ids = {local_name(c.tag): c.get("id") for c in parte_inicial[0]}
    assert ids == {"Epigrafe": "epi1", "Ementa": "eme1", "Preambulo": "pre1"}, ids

    preambulo = child_named(parte_inicial[0], "Preambulo")[0]
    assert child_names(preambulo) == ["p"], child_names(preambulo)


def test_anexos_follow_parte_final() -> None:
    """`Anexos` is `Norma`'s last child, after `ParteFinal` — D-2.

    `HierarchicalStructure` is an `xsd:sequence`
    (`ParteInicial? Articulacao ParteFinal? Anexos?`), so the annex pointers go
    last **whatever the document order** — the same rule Cycle 3 already applies
    inside `ParteInicial`, where the enacting formula is emitted first even
    though `ad_srf_22` writes it last. Probed: reversing the two fails on both
    schemas.

    Asserted as the full ordered child list, not just "Anexos is last", so that
    a regression which dropped `ParteFinal` altogether — which would also leave
    `Anexos` last — is still a failure.
    """
    norma = norma_element(sample_bundle().primary)
    assert child_names(norma) == [
        "ParteInicial",
        "Articulacao",
        "ParteFinal",
        "Anexos",
    ], child_names(norma)


def test_articulacao_is_deterministic() -> None:
    """Two renders of one model are byte-identical — §9.2's determinism.

    Rendered from a *freshly built* model rather than the cached one, so the
    comparison covers everything a second run would redo: reading the DOCX,
    metadata extraction, segmentation, the hierarchy, and the id allocator's
    counters. A `DispositivoIds` that was module-level state rather than
    per-render would sail through a same-model comparison and fail this one on
    the second article's id.

    Byte-identical, not merely equivalent: goldens are committed for this
    sample, so anything less than byte stability would make a golden diff mean
    nothing.
    """
    path = SAMPLES_DIR / f"{NORMA_SAMPLE}.docx"
    first = render_norma(build_model(read_docx(path), filename=path.name))
    second = render_norma(build_model(read_docx(path), filename=path.name))

    assert first.to_xml_strings() == second.to_xml_strings()


# --------------------------------------------------------------------------
# Negative schema tests — what makes the positive ones evidence
# --------------------------------------------------------------------------


def test_path_composed_artigo_id_is_rejected() -> None:
    """`id="pp1_art1"` is invalid on **both** schemas — A-6.1, and its reason.

    This is the measurement that forced `DispositivoIds` into existence. Cycle
    5's `IdAllocator` composes ids from the ancestor path (`pp1_agr1_p2`), which
    is correct for `DocumentoGenerico` and *illegal* for a dispositivo: the
    `idArtigo` pattern admits no prefix but `art`. Without this test A-6.1 reads
    as a preference for two allocators, and a future cycle could reasonably
    "simplify" them back into one.

    The document is otherwise exactly the shape the emitter produces, so the
    rejection can only be about the id — which is why the assertion is on the
    *pair* of documents: the same structure with `art1` must be accepted.
    """
    caput = '<Caput id="{0}_cpt"><Rotulo>Art. 1º</Rotulo><p>Texto.</p></Caput>'
    template = (
        '<Articulacao><Artigo id="{0}"><Rotulo>Art. 1º</Rotulo>' + caput +
        "</Artigo></Articulacao>"
    )

    assert_valid(
        hand_built(template.format("art1")),
        "the same structure with a conventional id",
    )
    assert_invalid(
        hand_built(template.format("pp1_art1")),
        "an Artigo with Cycle 5's path-composed id",
    )


def test_misordered_tree_fails_validation() -> None:
    """A `Caput` written before its `Rotulo` is invalid on both — E-3, D-4.

    The plan asks for "a deliberately mis-ordered tree fails validation", and
    D-4's point is that this must be assertable against the schema rather than
    against a check of our own. It is: `DispositivoType` is an `xsd:sequence`
    beginning with `Rotulo`, so a swapped pair is rejected outright.

    That is what licenses `render_articulacao` to append children in a fixed
    order and never re-sort them — the ordering is enforced downstream, so the
    emitter needs no defensive logic and a future edit that broke it cannot
    ship a valid-looking document.
    """
    assert_invalid(
        hand_built(
            '<Articulacao><Artigo id="art1">'
            '<Caput id="art1_cpt"><Rotulo>Art. 1º</Rotulo><p>Texto.</p></Caput>'
            "<Rotulo>Art. 1º</Rotulo>"
            "</Artigo></Articulacao>"
        ),
        "an Artigo whose Caput precedes its Rotulo",
    )


def test_artigo_without_rotulo_fails_validation() -> None:
    """An `Artigo` with no `Rotulo` at all is invalid on both — D-4.

    The other half of D-4, and the sharper half. That `Rotulo` must come *first*
    could be satisfied by an emitter that simply never emitted one; this says
    the element is required, so "no rótulo survived the label parse" can never
    be resolved by omitting it. An article whose label the emitter could not
    read has to fail the gate and fall back, which is A-R.6's rule — do not
    publish a structure the source did not state.
    """
    assert_invalid(
        hand_built(
            '<Articulacao><Artigo id="art1">'
            '<Caput id="art1_cpt"><p>Texto.</p></Caput>'
            "</Artigo></Articulacao>"
        ),
        "an Artigo with no Rotulo",
    )


def test_empty_articulacao_is_not_emitted() -> None:
    """No articles → no `<Articulacao>` element, and the gate refuses — N7.

    Three claims, and they belong together.

    First the schema's: `Articulacao` requires at least one `hierElements`
    child, so `<Articulacao/>` is rejected on both — which is why
    `render_articulacao` returns `None` rather than an empty element, and why
    that is not a stylistic choice.

    Then the emitter's: rendering a body that reads as no articulation at all
    produces a `Norma` with no `Articulacao` — it does not invent one, which is
    exactly the Cycle 6b sin (A-R.6).

    Then the gate's: such a document must not be published as a `Norma`. It
    raises `statutory_invalid` with a detail that says *why*, and separately
    `low_coverage`, so a reader of the telemetry learns both that the body did
    not read as an articulation and that nothing was covered.
    """
    assert_invalid(hand_built("<Articulacao/>"), "an empty Articulacao")

    model = synthetic(("Um texto corrido sem qualquer artigo.",), body=(0,))

    assert build_articulacao(model) == ()
    assert render_articulacao(()) is None

    rendered, blockers = render_norma_checked(model)
    assert "Articulacao" not in child_names(norma_element(rendered.primary))

    codes = {b.code for b in blockers}
    assert BLOCKER_INVALID in codes, blockers
    assert all(b.vetoes for b in blockers), blockers


# --------------------------------------------------------------------------
# Synthetic — the levels and labels the corpus never reaches (Q-3, D-5, A-6.2)
# --------------------------------------------------------------------------


def test_paragrafo_built_and_valid() -> None:
    """`§ 1º`/`§ 2º` become `Paragrafo`s under their article — Q-3.

    Synthetic, and unavoidably so: no sample in the corpus contains a `§` in
    body position, so `build_articulacao`'s parágrafo branch and
    `render_articulacao`'s `Paragrafo` loop ship entirely untested by the
    corpus. Q-3 chose to build this level because it was probed valid (N9), and
    "probed valid" is a statement about a hand-written XML fragment — this test
    is what connects it to the code that has to produce that fragment.

    Three things at once, because they fail independently: the parágrafos hang
    off the *article* (not the caput), their ids number from the article
    (`art1_par1`, `art1_par2`) rather than restarting some global counter, and
    the result validates. Element order is asserted too — `Caput` before the
    parágrafos is the schema's sequence, and the same rule
    `test_misordered_tree_fails_validation` shows is enforced.
    """
    model = synthetic(
        (
            "Art. 1º Fica instituído o programa.",
            "§ 1º O programa tem duração anual.",
            "§ 2º O prazo pode ser prorrogado uma vez.",
        ),
        body=(0, 1, 2),
    )

    built = build_articulacao(model)
    assert len(built) == 1, built
    assert [p.ident for p in built[0].paragrafos] == ["art1_par1", "art1_par2"]
    assert [p.rotulo for p in built[0].paragrafos] == ["§ 1º", "§ 2º"]

    bundle = render_norma(model)
    artigo = artigos(bundle.primary)[0]
    assert child_names(artigo) == ["Rotulo", "Caput", "Paragrafo", "Paragrafo"]
    assert [p.get("id") for p in child_named(artigo, "Paragrafo")] == [
        "art1_par1",
        "art1_par2",
    ]
    assert_valid(bundle.primary, "a synthetic Artigo with two Paragrafos")


def test_inciso_built_and_valid() -> None:
    """`I -`/`II -` become `Inciso`s inside the `Caput` — Q-3.

    Synthetic for the same reason as the parágrafos: nothing in the corpus puts
    a roman-numbered item in an articulated body. The id shape is the claim with
    the most surface — `art1_cpt_inc1` says the inciso hangs off the *caput*,
    not off the article, and that is a schema fact (the pattern's `_inc` segment
    follows `_cpt` or `_par`) rather than a naming taste.

    The incisos are asserted to be children of the `Caput` element itself and to
    follow its prose, which is `DispositivoType`'s sequence: `Rotulo`, then the
    `<p>`s, then the nested dispositivos. An emitter that appended them to the
    `Artigo` would produce a document that still validates in some arrangements
    and cites wrongly in all of them.
    """
    model = synthetic(
        (
            "Art. 1º Ficam estabelecidos os seguintes critérios:",
            "I - o primeiro critério;",
            "II - o segundo critério.",
        ),
        body=(0, 1, 2),
    )

    built = build_articulacao(model)
    assert len(built) == 1, built
    assert [i.ident for i in built[0].caput.incisos] == [
        "art1_cpt_inc1",
        "art1_cpt_inc2",
    ]
    assert built[0].paragrafos == (), "an inciso must not become a parágrafo"

    bundle = render_norma(model)
    caput = child_named(artigos(bundle.primary)[0], "Caput")[0]
    assert child_names(caput) == ["Rotulo", "p", "Inciso", "Inciso"], child_names(caput)
    assert [i.get("id") for i in child_named(caput, "Inciso")] == [
        "art1_cpt_inc1",
        "art1_cpt_inc2",
    ]
    assert_valid(bundle.primary, "a synthetic Caput with two Incisos")


def test_paragrafo_unico_id_unaccented() -> None:
    """An unaccented `Paragrafo unico` also takes the id `art1_par1u` — D-5.

    The accented spelling is the one documents use and is asserted in
    `test_paragrafo_unico_id`; this is its twin for the unaccented form, which
    OCR'd and older sources do produce. Both must reach the same id, because the
    two spellings are the same rótulo and a consumer citing `art1_par1u` should
    not have to know which way the source spelt it.

    Worth a separate case rather than a parametrisation because the two
    spellings fail *differently*. The builder folds the label through Cycle 4's
    `fold()` before looking for `unic`; an implementation that dropped the fold
    would keep this test green and break the accented one, and an
    implementation that compared against the accented literal alone would do the
    reverse. Only the pair pins both.
    """
    model = synthetic(
        (
            "Art. 1º Fica instituido o programa.",
            "Paragrafo unico. O programa e anual.",
        ),
        body=(0, 1),
    )

    built = build_articulacao(model)
    assert [p.ident for p in built[0].paragrafos] == ["art1_par1u"], built
    assert built[0].paragrafos[0].rotulo == "Paragrafo unico."

    bundle = render_norma(model)
    assert [p.get("id") for p in find_all(bundle.primary, "Paragrafo")] == [
        "art1_par1u"
    ]
    assert_valid(bundle.primary, "a synthetic Parágrafo único")


def test_paragrafo_unico_id() -> None:
    """`Parágrafo único` — accented, as documents write it — is `art1_par1u`.

    The spec's own §5.1 row, and the case that matters: every real Brazilian
    legal text writes `único` with the accent. `1u` is the `idArtigo` pattern's
    own escape hatch — it admits `1u` exactly where it admits a number — so an
    unnumbered parágrafo gets a schema-legal id instead of being renumbered `1`
    and cited as a `§ 1º` the document never wrote.

    The accent is the whole difficulty and the reason this test is not
    decoration. `parse_label` returns value `(1,)` for a parágrafo único exactly
    as it does for `§ 1º`, so the value cannot distinguish them; the emitter has
    to re-read the rótulo, and it must do so through Cycle 4's `fold()`. A plain
    lowercase substring test for `"unic"` matches `paragrafo unico` and misses
    `parágrafo único` — every accented document would silently be numbered
    `art1_par1`. This test is what catches that, and it caught it.

    The rendered document is validated as well as the id inspected, because
    `1u` being in the pattern is the entire justification for the special case —
    if it were not, this would be a plausible-looking id that no consumer
    accepts.
    """
    model = synthetic(
        (
            "Art. 1º Fica instituído o programa.",
            "Parágrafo único. O programa é anual.",
        ),
        body=(0, 1),
    )

    built = build_articulacao(model)
    assert [p.ident for p in built[0].paragrafos] == ["art1_par1u"], built
    assert built[0].paragrafos[0].rotulo == "Parágrafo único."

    bundle = render_norma(model)
    assert [p.get("id") for p in find_all(bundle.primary, "Paragrafo")] == [
        "art1_par1u"
    ]
    assert_valid(bundle.primary, "a synthetic Parágrafo único")


def test_artigo_unico_id_is_art1u() -> None:
    """`DispositivoIds.artigo(unico=True)` issues `art1u`, and it validates — D-5.

    Tested at the allocator rather than end-to-end, and the reason is a
    measurement worth recording. `parse_label`'s `ARTICLE_RE` is
    `Art\\.?\\s*(\\d+)…` — it requires **digits** — so `Art. único` parses to
    `None` and `build_articulacao`'s `unico` branch cannot be reached from any
    document. That branch's condition (`not label.value`) is additionally
    unreachable for `kind == "artigo"`, whose value is always `(n,)`. So D-5's
    claim about articles lives entirely in `DispositivoIds`, and that is where
    it is asserted; the `Parágrafo único` case above is the one that does run
    end to end, because `_PARAGRAFO_UNICO_RE` does match its label.

    Both halves are checked: the allocator issues `art1u`, and a document
    carrying it is accepted by both schemas — because an id the schema rejects
    would make the allocator's special case worse than useless.
    """
    ids = DispositivoIds()
    artigo_id = ids.artigo(None, unico=True)

    assert artigo_id == "art1u"
    assert ids.caput(artigo_id) == "art1u_cpt"
    assert ARTIGO_ID_RE.match(artigo_id), ARTIGO_ID_RE.pattern

    assert_valid(
        hand_built(
            '<Articulacao><Artigo id="art1u"><Rotulo>Art. único</Rotulo>'
            '<Caput id="art1u_cpt"><Rotulo>Art. único</Rotulo><p>Texto.</p></Caput>'
            "</Artigo></Articulacao>"
        ),
        "an Artigo único carrying the id art1u",
    )


def test_parte_inicial_schema_order() -> None:
    """`FormulaPromulgacao` is emitted first, before the epigraph — A-3.2, B16.

    `ParteInicial` is an `xsd:sequence`
    (`FormulaPromulgacao? Epigrafe? Ementa? Preambulo?`), and that is **not**
    document order: `ad_srf_22` reads epigraph, ementa, preamble, then `DECLARA`.
    Cycle 3 settled this for the statutory renderer and Cycle 6 inherits it, so
    the test is here to keep the inheritance honest — the norma emitter wraps
    `render_parte_inicial` with residue folding, and a fold that appended in
    document order would break the sequence.

    Synthetic because no norma-routed sample carries an enacting formula:
    `port_mf_277`'s front matter is epigraph, ementa and preamble only, so the
    corpus cannot tell a schema-ordered emitter from a document-ordered one.
    """
    model = synthetic(
        (
            "Portaria nº 1, de 2 de março de 2018",
            "Dispõe sobre o programa.",
            "O MINISTRO DE ESTADO, no uso de suas atribuições,",
            "RESOLVE:",
            "Art. 1º Fica instituído o programa.",
        ),
        body=(4,),
        front=FrontMatter(
            epigraph=Span(0, 0),
            ementa=Span(1, 1),
            preamble=Span(2, 2),
            enacting_formula=Span(3, 3),
        ),
    )

    bundle = render_norma(model)
    parte_inicial = find_all(bundle.primary, "ParteInicial")[0]

    assert child_names(parte_inicial) == [
        "FormulaPromulgacao",
        "Epigrafe",
        "Ementa",
        "Preambulo",
    ], child_names(parte_inicial)
    assert_valid(bundle.primary, "a synthetic front with an enacting formula")


def test_front_residue_folds_into_preambulo() -> None:
    """A front block in no named part reappears inside `Preambulo` — A-6.2.

    The measured problem: `FrontMatter.span` is a contiguous *hull* (A-3.5), so
    blocks between the named parts belong to the front matter and to no part —
    40 of them across 6 samples, `parecer_93`'s portal stamp and institutional
    banner among them. On the `generico` route A-5.1 renders regions rather than
    parts and keeps them. `ParteInicial` is a closed sequence and offers no such
    escape, so the only legal home is `Preambulo`, which is `textoSimplesType`
    and takes several `<p>` (probe C1).

    Three assertions, and the ordering one is the substantive one. The residue
    is folded *before* the preamble's own lines because that is where it stands
    in the document — a fold that appended would keep the text and lose its
    place, and reversibility (§9.2) is about both.

    Synthetic because `port_mf_277` has zero residue: this changes nothing for
    the corpus and everything for the 300 unseen documents, which is precisely
    the situation the A-1.3 precedent exists for.
    """
    model = synthetic(
        (
            "MINISTÉRIO DA FAZENDA",
            "Portaria nº 1, de 2 de março de 2018",
            "Dispõe sobre o programa.",
            "O MINISTRO DE ESTADO resolve:",
            "Art. 1º Fica instituído o programa.",
        ),
        body=(4,),
        front=FrontMatter(
            epigraph=Span(1, 1), ementa=Span(2, 2), preamble=Span(3, 3)
        ),
    )

    bundle = render_norma(model)
    preambulo = find_all(bundle.primary, "Preambulo")[0]
    lines = [text_of(p) for p in child_named(preambulo, "p")]

    assert lines == [
        "MINISTÉRIO DA FAZENDA",
        "O MINISTRO DE ESTADO resolve:",
    ], (
        "the unclaimed front block must be folded into Preambulo, ahead of the "
        f"preamble's own line; got {lines}"
    )
    assert_valid(bundle.primary, "a synthetic front with folded residue")

    # And the fold is the *reason* it survives: without it the block is in no
    # element of a closed sequence, which is what makes back residue a blocker.
    assert "MINISTÉRIO DA FAZENDA" in " ".join(bundle.texts)


def test_back_residue_has_no_home_and_blocks() -> None:
    """A back block in no signature is reported, not dropped — A-6.2's other half.

    `ParteFinal` admits only `LocalDataFecho` and `Assinatura`; an extra `<p>`
    inside `Assinatura` is rejected (probe C2) and a childless
    `AgrupamentoHierarquico` is too (C6). So the folding trick that rescues
    front residue has no back-matter equivalent, and the decision A-6.2 records
    is that the *document* loses the route rather than the text losing its
    place.

    This is the test that keeps that decision from being quietly reversed by an
    emitter that "just drops the trailing note". `back_residue` names the
    orphaned text — it is public because it is a gate input, not an
    implementation detail — and `render_norma_checked` refuses with
    `back_matter_residue`, which vetoes.

    Not covered by the spec's own §5.1 table, which routes the fallback
    assertions to the regression suite; asserted here because the blocker's
    *input* is this module's function and a wrong `back_residue` would make the
    regression test pass for the wrong reason.
    """
    model = synthetic(
        (
            "Art. 1º Fica instituído o programa.",
            "FULANO DE TAL",
            "Nota: publicado no DOU de 3 de março de 2018.",
        ),
        body=(0,),
        back=BackMatter(
            signatures=(Signature(name="FULANO DE TAL", span=Span(1, 1)),),
            trailing=Span(2, 2),
        ),
    )

    assert back_residue(model) == (
        "Nota: publicado no DOU de 3 de março de 2018.",
    )

    _, blockers = render_norma_checked(model)
    residue_blockers = [b for b in blockers if b.code == BLOCKER_BACK_RESIDUE]
    assert residue_blockers, [b.code for b in blockers]
    assert residue_blockers[0].vetoes
    assert "Nota" in residue_blockers[0].detail, residue_blockers[0].detail


# --------------------------------------------------------------------------
# The allocator on its own — uniqueness and the pattern it must not leave
# --------------------------------------------------------------------------


def test_dispositivo_ids_refuse_collisions_and_illegal_shapes() -> None:
    """`DispositivoIds` refuses a duplicate and refuses a non-conforming id.

    `xsd:ID` requires uniqueness, but a schema catches a collision only after
    the whole document is written, at which point the error names two elements
    and not the code that numbered them. The allocator therefore enforces it at
    the point of issue — and enforces the pattern there too, so a future level
    added without checking its id shape fails loudly at the first call rather
    than producing a document that no consumer accepts.

    `issued` is asserted to report every id, because it is what a caller uses to
    check bundle-wide uniqueness without re-walking the tree.
    """
    ids = DispositivoIds()
    artigo_id = ids.artigo(1)
    caput_id = ids.caput(artigo_id)

    with pytest.raises(ValueError, match="duplicate"):
        ids.artigo(1)
    with pytest.raises(ValueError, match="schema-legal"):
        ids.caput("pp1")

    assert ids.paragrafo(artigo_id, 2) == "art1_par2"
    assert ids.inciso(caput_id) == "art1_cpt_inc1"
    assert ids.inciso(caput_id) == "art1_cpt_inc2", "incisos number per parent"
    assert ids.issued == (
        "art1",
        "art1_cpt",
        "art1_cpt_inc1",
        "art1_cpt_inc2",
        "art1_par2",
    ), ids.issued


def test_artigo_reports_every_source_index_it_consumed() -> None:
    """`Artigo.all_source_indices` reaches every level's blocks — invariant #2.

    Conservation is checked by arithmetic over source indices (the segmentation
    model keeps spans, never copies), so an articulation that rendered a
    parágrafo's text while forgetting to record its index would report a loss
    that did not happen — or, worse, let a real loss hide behind a level the
    walk never visits.

    The fixture reaches all four levels at once, which is the only arrangement
    that can catch a walk that skips one: incisos under a parágrafo are the
    deepest path, and they are the branch a naive implementation forgets.
    """
    model = synthetic(
        (
            "Art. 1º Ficam estabelecidos os critérios:",
            "I - o primeiro critério;",
            "§ 1º O parágrafo dispõe:",
            "II - o critério do parágrafo.",
        ),
        body=(0, 1, 2, 3),
    )

    built = build_articulacao(model)
    assert len(built) == 1, built
    assert sorted(set(built[0].all_source_indices)) == [0, 1, 2, 3], (
        "every source block the articulation consumed must be reachable; got "
        f"{built[0].all_source_indices}"
    )
    # The inciso after a parágrafo belongs to it, not back to the caput.
    assert [i.ident for i in built[0].paragrafos[0].incisos] == ["art1_par1_inc1"]


def test_build_articulacao_refuses_prose_before_the_first_article() -> None:
    """Body text ahead of `Art. 1º` makes the whole body unarticulable — A-R.6.

    The alternative an emitter is tempted into is absorbing the stray paragraph
    into the first article's caput, which reads plausibly and is a fabrication:
    the document did not say that sentence was part of article 1. Refusing
    returns `()`, the gate raises `statutory_invalid`, and the document is
    published as `generico` — where the same text is expressible without
    inventing a structure for it.

    This is the Cycle 6b sin stated as a test rather than as a warning in a
    docstring, and it is worth its own case because the refusal is a *silent*
    return: nothing raises, so only an assertion on the return value notices if
    the branch is ever softened into absorption.
    """
    model = synthetic(
        (
            "Considerando o que dispõe a legislação vigente.",
            "Art. 1º Fica instituído o programa.",
        ),
        body=(0, 1),
    )

    assert build_articulacao(model) == (), (
        "prose before the first article must make the body unarticulable, not "
        "be absorbed into article 1's caput"
    )


def test_unlabelled_prose_continues_the_open_dispositivo() -> None:
    """A paragraph with no label joins whatever dispositivo is open — invariant #2.

    Statutory articles run over several paragraphs all the time: only the first
    carries `Art. 1º`, and the rest are continuation prose the grammar cannot
    and should not label. They have exactly one honest home — the dispositivo
    that is currently open — and an emitter that dropped them, or started a new
    article for each, would lose text or invent structure respectively.

    Both destinations are asserted, because "the open dispositivo" changes as
    the document goes and the two cases fail apart. Prose after the caput joins
    the **caput**; prose after a `§ 1º` joins the **parágrafo**, not back to the
    caput above it. A single-target implementation passes one of these and fails
    the other, which is why they are in one test with two `<p>`s to place.

    The source indices are checked alongside the text: conservation is verified
    by arithmetic over indices elsewhere in the suite, so prose that arrived in
    the right element while its index went missing would report a loss that did
    not happen.
    """
    model = synthetic(
        (
            "Art. 1º Fica instituído o programa.",
            "O programa será executado em etapas sucessivas.",
            "§ 1º A primeira etapa começa em março.",
            "A segunda etapa começa em setembro.",
        ),
        body=(0, 1, 2, 3),
    )

    built = build_articulacao(model)
    assert len(built) == 1, (
        f"unlabelled prose must not open a new article; got {len(built)}"
    )

    caput = built[0].caput
    assert caput.paragraphs == (
        "Fica instituído o programa.",
        "O programa será executado em etapas sucessivas.",
    ), caput.paragraphs
    assert caput.source_indices == (0, 1), caput.source_indices

    paragrafo = built[0].paragrafos[0]
    assert paragrafo.paragraphs == (
        "A primeira etapa começa em março.",
        "A segunda etapa começa em setembro.",
    ), paragrafo.paragraphs
    assert paragrafo.source_indices == (2, 3), paragrafo.source_indices

    bundle = render_norma(model)
    artigo = artigos(bundle.primary)[0]
    assert child_names(child_named(artigo, "Caput")[0]) == ["Rotulo", "p", "p"]
    assert child_names(child_named(artigo, "Paragrafo")[0]) == ["Rotulo", "p", "p"]
    assert_valid(bundle.primary, "an article with continuation prose")


def test_a_nested_body_section_makes_it_unarticulable() -> None:
    """A body tree with nested sections refuses articulation — A-R.6.

    The builder reads `HierarchyTree.preamble` and each section's own `body`,
    flat. A section with **children** is a body that Cycle 4 found real
    hierarchy in — chapters, subsections, a numbered outline — and this cycle
    builds no `Agrupamento`-level statutory element for it (Q-3 stops at
    `Artigo`, and `Alinea`/`Item` were deliberately not built either). Flattening
    such a tree into a run of articles would discard the nesting the hierarchy
    cycle worked to find, and publishing a structure the source did not state is
    the sin A-R.6 withdrew a whole cycle over.

    So the body is refused and the document goes to `generico`, whose nested
    emitter (Cycle 5b) renders exactly that hierarchy. Refusal here is not a
    limitation being papered over — it is the routing working.
    """
    model = synthetic(("Art. 1º Fica instituído o programa.",), body=(0,))
    nested = dataclasses.replace(
        model,
        hierarchy=HierarchyDoc(
            body=HierarchyTree(
                sections=(
                    Section(
                        label="1.",
                        level=1,
                        body=model.body.preamble,
                        children=(
                            Section(label="1.1", level=2, body=(
                                Para(
                                    inlines=(Inline("Detalhe da subseção."),),
                                    source_indices=(1,),
                                ),
                            )),
                        ),
                    ),
                )
            )
        ),
    )

    assert build_articulacao(nested) == (), (
        "a body with nested sections must be refused, not flattened into a run "
        "of articles"
    )
    _, blockers = render_norma_checked(nested)
    assert BLOCKER_INVALID in {b.code for b in blockers}, blockers


def test_a_table_in_the_body_makes_it_unarticulable() -> None:
    """A body carrying a `Table` refuses articulation rather than dropping it — D-6.

    Measured: probes B10 and B11 found `<table>` and `<ol>`/`<ul>` **rejected
    inside `Caput`**. That leaves an emitter exactly two options for a body
    article whose content includes one, and only one of them is honest. It can
    drop the node — which validates, reads plausibly, and silently loses every
    word of the table, a text-conservation failure (invariant #2) that no schema
    can see. Or it can refuse the whole body, which sends the document to
    `generico`, where the same table *is* expressible.

    D-6 chose to refuse, and this is the test that keeps it chosen. A mutation
    turning `_body_paras`'s `raise` into a `continue` produces a document that
    is valid, well-formed, and missing a table — and passes every other test in
    this module. It does not pass this one.

    `build_articulacao` returns `()` rather than raising: an unarticulable body
    is a routing outcome, not an error. So the assertion is on the return value,
    and on the gate refusing afterwards, since a silent `()` that nothing acted
    on would be the same loss by a longer route.
    """
    model = synthetic(("Art. 1º Ficam estabelecidos os critérios:",), body=(0,))
    table = Table(
        rows=((( Inline("Critério"),), (Inline("Prazo"),)),),
        source_indices=(1,),
    )
    with_table = dataclasses.replace(
        model,
        hierarchy=HierarchyDoc(
            body=HierarchyTree(
                preamble=model.body.preamble + (table,)
            )
        ),
    )

    assert build_articulacao(with_table) == (), (
        "a Table cannot sit inside a Caput, so the body must be refused, not "
        "silently emptied of it"
    )

    _, blockers = render_norma_checked(with_table)
    assert BLOCKER_INVALID in {b.code for b in blockers}, blockers

    # And the refusal is caused by the table, not by the article: the same body
    # without it articulates fine.
    assert len(build_articulacao(model)) == 1


def test_a_list_in_the_body_makes_it_unarticulable() -> None:
    """The same for a `ListNode` — D-6's other half.

    Separate from the table case because they are separate probes (B11 and
    B10) and separate `isinstance` arms, and because a list is the one that
    tempts: an inciso *looks* like a list item, so an emitter that quietly
    turned a `ListNode` into incisos would produce something that validates and
    that a reader might even prefer. It would also be inventing a dispositivo
    level the source did not label, which is precisely the fabrication A-R.6
    withdrew a cycle over — the source wrote a Word list, not `I -` and `II -`.
    """
    model = synthetic(("Art. 1º Ficam estabelecidos os critérios:",), body=(0,))
    listing = ListNode(
        ordered=True,
        items=(
            ListItem(inlines=(Inline("o primeiro critério;"),), source_indices=(1,)),
            ListItem(inlines=(Inline("o segundo critério."),), source_indices=(2,)),
        ),
    )
    with_list = dataclasses.replace(
        model,
        hierarchy=HierarchyDoc(
            body=HierarchyTree(preamble=model.body.preamble + (listing,))
        ),
    )

    assert build_articulacao(with_list) == ()
    _, blockers = render_norma_checked(with_list)
    assert BLOCKER_INVALID in {b.code for b in blockers}, blockers


def test_render_articulacao_writes_the_dataclasses_it_is_given() -> None:
    """`render_articulacao` is a pure function of the records — Q-3's four levels.

    Called with hand-made dataclasses rather than with a built articulation, so
    that the renderer is separated from the builder: every other test above
    exercises them together, and a renderer that quietly ignored, reordered or
    renamed a level would be indistinguishable from a builder that never
    produced one.

    The four levels appear at once and the result validates, which is the
    end-to-end form of probes N1, N9 and N10 — the fragments those probes
    measured, produced by the code that has to produce them.
    """
    articulacao = (
        Artigo(
            rotulo="Art. 1º",
            ident="art1",
            caput=Caput(
                rotulo="Art. 1º",
                ident="art1_cpt",
                paragraphs=("Ficam estabelecidos os critérios:",),
                incisos=(Inciso(rotulo="I -", ident="art1_cpt_inc1",
                                paragraphs=("o primeiro critério;",)),),
            ),
            paragrafos=(
                Paragrafo(
                    rotulo="§ 1º",
                    ident="art1_par1",
                    paragraphs=("O parágrafo dispõe:",),
                    incisos=(Inciso(rotulo="II -", ident="art1_par1_inc1",
                                    paragraphs=("o critério do parágrafo.",)),),
                ),
            ),
        ),
    )

    element = render_articulacao(articulacao)
    assert element is not None

    artigo = element[0]
    assert child_names(artigo) == ["Rotulo", "Caput", "Paragrafo"]
    assert child_names(child_named(artigo, "Caput")[0]) == ["Rotulo", "p", "Inciso"]
    assert child_names(child_named(artigo, "Paragrafo")[0]) == [
        "Rotulo",
        "p",
        "Inciso",
    ]

    document = hand_built("")
    norma_element(document).append(element)
    assert_valid(document, "a hand-built four-level articulation")


def test_artigo_id_re_agrees_with_the_shipped_schema() -> None:
    """`ARTIGO_ID_RE`'s verdicts match the XSD's on the shapes this cycle emits.

    A transcribed pattern is a second source of truth, which A-3.4 warns about,
    and the mitigation the module chose is that the schema stays the authority
    while the regex is only the fast check. That mitigation is worth nothing
    unless the two agree, so this test puts each shape through both.

    The negatives are the interesting ones. `pp1_art1` is A-6.1's whole reason,
    and `Art1`/`artigo1` are the plausible near-misses a hand-written id would
    take. `art1_inc1` is the shape the two patterns *disagree* about, and it has
    its own xfail below.
    """
    template = (
        '<Articulacao><Artigo id="{0}"><Rotulo>Art. 1º</Rotulo>'
        '<Caput id="art9_cpt"><Rotulo>Art. 1º</Rotulo><p>Texto.</p></Caput>'
        "</Artigo></Articulacao>"
    )

    for ident in ("art1", "art1u", "art12"):
        assert ARTIGO_ID_RE.match(ident), ident
        assert_valid(hand_built(template.format(ident)), f"id {ident!r}")

    for ident in ("pp1_art1", "Art1", "artigo1"):
        assert not ARTIGO_ID_RE.match(ident), (
            f"{ident!r} matches the transcribed pattern but must not"
        )
        assert_invalid(hand_built(template.format(ident)), f"id {ident!r}")


def test_artigo_id_re_is_never_wider_than_the_schema() -> None:
    """`ARTIGO_ID_RE` rejects `art1_inc1`, which both schemas reject too.

    The module's docstring makes a specific promise about this regex: it is
    "the fast check and the schema is the authority". That is only safe while
    the regex is *narrower* than the XSD. Narrower means an unsupported shape
    fails loudly at `DispositivoIds._take`, at the call that made it, naming the
    id. Wider would mean the allocator waves an illegal id through and the
    failure surfaces at the end of a whole render as an XSD facet complaint that
    names an element and not the code that numbered it — and only if someone
    validates at all.

    `art1_inc1` is the shape that tests the direction, and it is not
    hypothetical. `DispositivoIds.inciso` composes `f"{parent_id}_inc{n}"` from
    whatever parent it is handed, and its docstring says that parent is "a
    `Caput` or `Paragrafo`" — the grouping in the pattern is what enforces it. A
    caller passing an `Artigo` id (the obvious mistake, since an inciso does
    conceptually belong to its article) must be refused at the allocator, not
    three hundred lines later by a schema.
    """
    template = (
        '<Articulacao><Artigo id="{0}"><Rotulo>Art. 1º</Rotulo>'
        '<Caput id="art9_cpt"><Rotulo>Art. 1º</Rotulo><p>Texto.</p></Caput>'
        "</Artigo></Articulacao>"
    )

    assert_invalid(hand_built(template.format("art1_inc1")), "id 'art1_inc1'")
    assert not ARTIGO_ID_RE.match("art1_inc1"), (
        "an inciso may not hang off an Artigo: idArtigo requires _inc to "
        "follow _cpt or _par, so the fast check must refuse it too"
    )


def test_transcribed_pattern_is_a_subset_of_the_schemas() -> None:
    """The regex never accepts an id the schema rejects — the safe direction.

    The two patterns are deliberately *not* equal: `ARTIGO_ID_RE` covers only
    the four levels this cycle builds, while `idArtigo` also admits `_ali`,
    `_ite`, `_dpg`, `_alt` and the `-NNN` suffixes. Narrower is fine and is what
    the module's docstring claims. Wider would not be: an id the fast check
    waved through and the schema rejects turns a clear allocator error into a
    validation failure at the end of a render.

    So the direction is asserted, not the equality, over the shapes the
    allocator can actually produce.
    """
    issued = []
    ids = DispositivoIds()
    for number in (1, 2):
        artigo_id = ids.artigo(number)
        issued.append(artigo_id)
        caput_id = ids.caput(artigo_id)
        issued.extend([caput_id, ids.inciso(caput_id)])
        par_id = ids.paragrafo(artigo_id, 1)
        issued.extend([par_id, ids.inciso(par_id)])
    issued.append(DispositivoIds().paragrafo("art1", 1, unico=True))

    for ident in issued:
        assert ARTIGO_ID_RE.match(ident), ident
        assert re.match(
            r"art(\d+(-[0-9]{1,3}){0,3}|1u)"
            r"((_cpt|(_(par|dpg)(\d+(-[0-9]{1,3}){0,3}|1u)))"
            r"(_(inc|ali|dpg)\d+(-[0-9]{1,3}){0,3})?)?$",
            ident,
        ), f"{ident!r} passes ARTIGO_ID_RE but not the XSD's own idArtigo pattern"
