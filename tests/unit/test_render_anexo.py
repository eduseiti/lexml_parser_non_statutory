"""The annex split — plan §2.9, spec decisions D-1/Q-5/Q-6, amendment A-R.8.

`render/anexo.py` is not a new feature. It is the *third* caller of a convention
Cycle 5 already delivered (A-5.6) and Cycle 5b already delivered a second time,
folded back into one implementation before Cycle 6 could make it a third copy.
So this module tests two different kinds of claim, and keeping them apart is
what makes a failure here readable:

* **What the convention is.** An annex is a standalone sibling `<LexML>`
  document — its own `Metadado`, its own `xsd:ID` scope rooted at `anexoN_pp`,
  its tables named `anexoN_tabM`, reached from the primary only by a
  `ReferenciaAnexo/@AlvoURN` carrying the `!anexoN` fragment. That is the
  reference parser's own arrangement for `lei_5070_19660707.anexo1.xml`, and
  every one of those five things is a place a pointer can dangle or an id space
  can collide.
* **That folding three copies into one changed nothing.** The 32 committed
  `generico` + `generico_aninhado` goldens are the file-level proof; the
  `test_flat_anexo_matches_cycle_5_output` here is the same proof stated as an
  equality between what this module returns and what Cycle 5's bundle carries,
  so a reader diagnosing a golden diff can tell a refactor regression from an
  emitter change without reading either emitter.

**Why `nested` is a flag and not a probe (Q-6).** A nested annex body is valid
only against `lexml-proposed/`, and that directory can legitimately be absent.
It would have been easy to have `render_anexo` ask the capability probe what to
emit — and it would have been wrong: output that changed depending on which
directories exist on the machine breaks determinism (§9.2) and makes a golden
un-committable, because regenerating it on two developers' machines would
produce two different files. The form is therefore chosen by the *emitter*
(`generico` and `norma` flat, `generico-aninhado` nested), and
`test_anexo_form_does_not_depend_on_probe` is what stops that decision quietly
reverting.

The A-R.8 pair is deliberately asymmetric, following A-5b.3. The *positive*
half — nested output validates on the proposed generation — **skips with the
probe's own diagnostic** when that generation is absent, because A-R.9 requires
the suite to stay green against `lexml/` alone. The *negative* half — nested
output is rejected by the shipped schemas — runs everywhere and needs no
proposed schemas at all, so the skip can never become a hiding place: if the
nested form ever quietly started emitting shipped-compatible output, the
negative test fails loudly on every machine even where the positive one is
skipped.

One corpus caveat, stated rather than worked around: `port_mf_277` is the only
sample with an annex, and its annex has **no table**. `anexoN_tabM` therefore
cannot be observed on the corpus at all, and the alternative to a synthetic
fixture is not a weaker test but no test — the id convention would ship
unexercised. `test_anexo_table_ids` builds an annex tree carrying a table, the
A-1.3 / A-4.6 precedent.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.hierarchy.tree import HierarchyTree
from lexml_nonstat.ingest import Inline, read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.model.nodes import Para, Table
from lexml_nonstat.render import (
    ANEXO_FORMS,
    anexo_urn,
    anexos_element,
    all_ids,
    leaf_texts,
    lexml_root,
    local_name,
    render_anexo,
    render_generico,
    render_generico_aninhado,
    render_norma,
    to_xml_string,
    words,
)
from lexml_nonstat.validate.schema import PROPOSED, SHIPPED, load_schemas
from tests.conftest import requires_nested

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

LEX = "{http://www.lexml.gov.br/1.0}"

#: The one sample with an annex — plan §2.9's only corpus exercise, and the
#: reason every synthetic fixture below starts from a *real* annex rather than
#: from an invented one.
ANNEX_SAMPLE = "port_mf_277_20180607"

# Collection fails loudly on a rename rather than silently skipping the case
# these tests were written for.
assert len(SAMPLES) == 15, SAMPLES
assert ANNEX_SAMPLE in SAMPLES

_CACHE: dict[str, object] = {}


def model(name: str = ANNEX_SAMPLE):
    """One sample's `DocumentModel`, built once per session.

    Every test here renders from the *same* model, because the annex split is a
    property of the emitters and a per-test `build_model()` would let a model
    difference hide inside a rendering difference.
    """
    if name not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        _CACHE[name] = build_model(read_docx(path), filename=path.name)
    return _CACHE[name]


def annex(name: str = ANNEX_SAMPLE):
    """The sample's single `AnnexHierarchy`."""
    annexes = model(name).annexes
    assert len(annexes) == 1, f"{name}: expected exactly one annex"
    return annexes[0]


def parte_principal(document: etree._Element) -> etree._Element | None:
    for node in document.iter(f"{LEX}PartePrincipal"):
        return node
    return None


def child_names(element: etree._Element) -> list[str]:
    """Direct children's local names — the shape a consumer reads first."""
    return [local_name(c.tag) for c in element]


def valid_on(document: etree._Element, generation: str) -> dict[str, bool]:
    """Both schemas of one generation, by name, so a failure says *which*."""
    return {
        name: bool(schema.validate(document))
        for name, schema in load_schemas(generation=generation).items()
    }


def table_annex():
    """A synthetic annex whose tree carries a table.

    The corpus cannot exercise `anexoN_tabM`: its one annex has no table. The
    fixture is built by replacing only the *tree* of the real annex, so the
    label, ordinal and fragment stay exactly what Cycle 4 produced and the test
    is about table id allocation and nothing else.
    """
    cell = lambda text: (Inline(text=text),)  # noqa: E731
    tree = HierarchyTree(
        preamble=(
            Para(inlines=cell("Intro")),
            Table(rows=((cell("A"), cell("B")), (cell("C"), cell("D")))),
        )
    )
    return dataclasses.replace(annex(), tree=tree)


# --------------------------------------------------------------------------
# The convention: a standalone sibling document
# --------------------------------------------------------------------------


def test_anexo_is_standalone_lexml_document():
    """`<LexML><Metadado/><Anexo><DocumentoGenerico>` — a document, not a subtree.

    Plan §2.9's central claim, and the one that makes every other test in this
    module meaningful. An annex rendered as a *subtree* of the primary would
    satisfy conservation, satisfy validity and satisfy id uniqueness while being
    the wrong artifact entirely: a consumer resolving `!anexo1` would find
    nothing to resolve it against.

    The root's namespace map is asserted too. `lexml_root()` exists so the three
    emitters cannot drift on it, and a divergence there would rewrite every one
    of the 32 committed goldens without changing a single byte of content —
    a diff that looks like a behaviour change and is not.
    """
    document = render_anexo(model(), annex())

    assert local_name(document.tag) == "LexML"
    assert child_names(document) == ["Metadado", "Anexo"]

    anexo = document[1]
    assert child_names(anexo) == ["DocumentoGenerico"]

    parte = parte_principal(document)
    assert parte is not None, "the annex must carry its content"
    assert parte.getparent().tag == f"{LEX}DocumentoGenerico"

    # The same nsmap `lexml_root()` issues, checked against a freshly built one
    # rather than against a literal, so the two cannot be updated apart.
    assert document.nsmap == lexml_root().nsmap

    assert valid_on(document, SHIPPED) == {"rigido": True, "flexivel": True}


def test_anexo_urn_fragment():
    """The annex's URN is the primary's plus `!anexo1`.

    The fragment is the *whole* addressing mechanism: the primary carries no
    annex content, so `!anexo1` is the only thing connecting the two files.
    Asserted three ways — the helper's return, the document's own
    `Identificacao/@URN`, and the relationship to the primary's URN — because a
    fragment that was right in the helper and dropped on the way into the
    document would leave a document nothing can address.
    """
    urn = anexo_urn(model(), annex())

    assert urn.endswith("!anexo1"), urn
    assert urn == f"{model().metadata.urn}!anexo1"

    document = render_anexo(model(), annex())
    identificacao = [i.get("URN") for i in document.iter(f"{LEX}Identificacao")]
    assert identificacao == [urn], (
        "the annex must carry exactly its own URN, once — a second "
        "Identificacao would make the document ambiguous to address"
    )


def test_anexo_pp_id():
    """The annex's id space is rooted at `anexo1_pp`, not at `pp1`.

    This is what keeps two documents' `xsd:ID` spaces from colliding when a
    consumer loads both. `pp1` is the *primary's* root, and an annex reusing it
    would produce two files each internally valid and jointly unusable — the
    failure `test_ids_unique_across_the_bundle` in the conservation module
    checks from the other end.

    Every id in the annex is asserted to descend from that root, not just the
    root itself: a single stray `pp1_…` deeper in the tree is the realistic
    version of this bug, and checking only the root would miss it.
    """
    document = render_anexo(model(), annex())

    parte = parte_principal(document)
    assert parte is not None
    assert parte.get("id") == "anexo1_pp"

    idents = all_ids(document)
    assert idents[0] == "anexo1_pp"
    stray = [i for i in idents if not i.startswith("anexo1")]
    assert not stray, (
        f"annex ids must all live under the annex's own root: {stray[:10]}"
    )


def test_anexo_table_ids():
    """A table inside an annex is `anexo1_tabM`, numbered from 1.

    §2.9's table convention, and the one part of it the corpus cannot reach —
    `port_mf_277`'s annex has no table, so without a synthetic fixture this id
    scheme ships unexercised (the A-1.3 / A-4.6 precedent).

    Note what the expected id is *not*: `anexo1_pp_agr2_tab1`. A table id is
    based on the annex fragment rather than composed down the containing path,
    which is a deliberate departure from Cycle 5's `IdAllocator` scheme and
    exactly the sort of detail a refactor silently normalises.
    """
    document = render_anexo(model(), table_annex())

    tables = list(document.iter(f"{LEX}table"))
    assert len(tables) == 1, "the fixture carries exactly one table"
    assert tables[0].get("id") == "anexo1_tab1"

    assert valid_on(document, SHIPPED) == {"rigido": True, "flexivel": True}


def test_referencia_anexo_targets_resolve():
    """Every `AlvoURN` in the primary names an annex document that exists.

    Plan bullet 5. The two halves of the split are written by different code
    paths — `anexos_element` builds the pointers, `render_anexo` builds the
    targets — so nothing but a test makes them agree. A dangling pointer is
    also invisible to both schema validation and conservation: each file is
    perfectly well-formed on its own, and only the *relationship* is broken.

    Checked as set equality rather than containment, so the test catches an
    annex emitted with no pointer to it just as loudly as a pointer with no
    annex.
    """
    bundle = render_norma(model())

    targets = [
        r.get("AlvoURN") for r in bundle.primary.iter(f"{LEX}ReferenciaAnexo")
    ]
    emitted = [
        i.get("URN")
        for document in bundle.annexes
        for i in document.iter(f"{LEX}Identificacao")
    ]

    assert targets, "the sample carries an annex, so it must carry a pointer"
    assert set(targets) == set(emitted), (
        f"pointer/target mismatch — pointers {targets}, annexes {emitted}"
    )
    assert len(targets) == len(set(targets)), "a target is pointed at twice"

    # And the element the pointers live in exists only because there are annexes.
    assert anexos_element(model()) is not None
    other = model("sumula_stj_125")
    assert not other.annexes
    assert anexos_element(other) is None, (
        "an empty Anexos is invalid — ReferenciaAnexo is minOccurs=1 — so a "
        "document with no annex must emit no element at all"
    )


def test_anexo_uses_documento_generico():
    """An annex is always `DocumentoGenerico`, never `Norma`.

    Spec decision D-1, and it is a schema fact before it is a choice: `Anexo` is
    a `choice` of `DocumentoGenerico` and `DocumentoArticulado`, and **both
    shipped schemas reject `Norma` inside it**. So an emitter that reasoned "the
    primary is a `Norma`, therefore its annex is one too" would produce an
    invalid document — which is precisely the reasoning error worth pinning on
    the statutory route, where a `Norma` primary is sitting right there.

    Asserted across all three emitters, because each one calls `render_anexo`
    from a different place and D-1 has to hold in all of them.
    """
    bundles = {
        "generico": render_generico(model()),
        "generico-aninhado": render_generico_aninhado(model()),
        "norma": render_norma(model()),
    }

    for emitter, bundle in bundles.items():
        assert len(bundle.annexes) == 1, emitter
        document = bundle.annexes[0]
        assert child_names(document[1]) == ["DocumentoGenerico"], emitter
        assert not list(document.iter(f"{LEX}Norma")), (
            f"{emitter}: an annex must never contain a Norma (D-1)"
        )
        assert not list(document.iter(f"{LEX}DocumentoArticulado")), (
            f"{emitter}: this cycle emits no articulated annex"
        )


# --------------------------------------------------------------------------
# Q-5 — the extraction is behaviour-preserving
# --------------------------------------------------------------------------


def test_flat_anexo_matches_cycle_5_output():
    """`render_anexo(nested=False)` is byte-for-byte Cycle 5's annex.

    Q-5's whole case for extracting the module rather than writing a third copy.
    The 32 committed goldens prove this at the file level, but they prove it
    about *whole bundles*: a reader watching a golden diff cannot tell whether
    the annex moved or the primary did. This states the claim about the annex
    alone, from three directions at once.

    `generico` and `norma` must agree with each other too, and that is the
    stronger half. They are separate emitters with separate primaries, and the
    only reason their annexes are identical is that both delegate here — so if
    one of them ever grew its own annex rendering, this is where it shows up,
    even if its own goldens were regenerated along with it.
    """
    direct = to_xml_string(render_anexo(model(), annex()))
    from_generico = render_generico(model()).to_xml_string(
        render_generico(model()).annexes[0]
    )
    from_norma = render_norma(model()).to_xml_string(render_norma(model()).annexes[0])

    assert direct == from_generico, "the flat annex is no longer Cycle 5's"
    assert direct == from_norma, (
        "generico and norma must share one annex implementation, not two"
    )


def test_anexo_form_does_not_depend_on_probe():
    """Flat by default, whatever the schema capability reports (Q-6).

    The determinism clause of §9.2, made executable. If `render_anexo` consulted
    `probe_capabilities` to decide its form, this repository would emit one
    artifact on a machine with `lexml-proposed/` and a different one without —
    two developers regenerating the same golden would produce two files, and the
    golden would become un-committable.

    The test is written to be *insensitive* to whether the proposed generation
    is present, which is the only way it can make that claim: it asserts the
    default equals the explicit `nested=False` form and differs from the
    `nested=True` form, and both of those hold identically on a checkout that
    has the proposed schemas and one that does not. `requires_nested` is
    deliberately **not** applied here — a skip would defeat the point.
    """
    default = to_xml_string(render_anexo(model(), annex()))
    flat = to_xml_string(render_anexo(model(), annex(), nested=False))
    nested = to_xml_string(render_anexo(model(), annex(), nested=True))

    assert default == flat, "the default annex form must be flat (Q-6)"
    assert default != nested, (
        "the two forms must actually differ, or this test is vacuous and "
        "A-R.8 is untested"
    )

    # The nested form is a form, not a capability — the names are declared.
    assert ANEXO_FORMS == ("flat", "nested")

    # And the flat default is what the shipped schemas accept, which is the
    # practical reason the default is the safe one.
    assert valid_on(render_anexo(model(), annex()), SHIPPED) == {
        "rigido": True,
        "flexivel": True,
    }


# --------------------------------------------------------------------------
# A-R.8 — the nested annex body
# --------------------------------------------------------------------------


@requires_nested
def test_nested_anexo_valid_on_proposed():
    """A nested annex body validates against `lexml-proposed/`.

    **A-R.8 discharged.** The maintainers' unreleased change makes
    `AgrupamentoHierarquico` prose-bearing and recursive, and until it ships
    there is no way to say "nested annexes are correct" except by validating
    against the generation that carries it.

    Skips with the probe's *own diagnostic* when that generation is absent
    (A-5b.3, A-R.9): a missing `lexml-proposed/` directory and a present but
    unpatched one are different situations, and a reader of a skipped run
    should not have to open the source to tell them apart. What stops the skip
    from being a hiding place is its companion below, which needs no proposed
    schemas and runs everywhere.
    """
    document = render_anexo(model(), annex(), nested=True)

    assert list(document.iter(f"{LEX}AgrupamentoHierarquico")), (
        "the nested form must actually nest, or validating it proves nothing"
    )
    assert valid_on(document, PROPOSED) == {"rigido": True, "flexivel": True}


def test_nested_anexo_invalid_on_shipped():
    """The shipped schemas reject a nested annex — and that is correct.

    A-R.8's other half, and the one that runs on every machine. Nested output is
    **opt-in** precisely because it is not yet legal upstream; if it validated
    on `lexml/` there would be no capability to probe, no reason for the flag,
    and no reason for the default to be flat.

    So this test is the guard on the skip above. Should the nested renderer ever
    quietly start emitting shipped-compatible output — a regression that would
    make `test_nested_anexo_valid_on_proposed` pass for entirely the wrong
    reason, and skip silently where the proposed schemas are absent — it fails
    here, loudly, everywhere.
    """
    document = render_anexo(model(), annex(), nested=True)

    assert valid_on(document, SHIPPED) == {"rigido": False, "flexivel": False}, (
        "nested annex output is opt-in because the shipped schemas reject it; "
        "if they now accept it, A-R.8's premise has changed and the flag, the "
        "probe and the flat default all need revisiting"
    )


def test_nested_and_flat_anexo_texts_agree():
    """Both annex forms carry the same words — A-R.8's conservation clause.

    The two forms differ in how sections are *written*: flat emits sibling
    `Agrupamento`s carrying depth out of band in a `Bloco nome="nivel"`, nested
    emits a real tree of `AgrupamentoHierarquico` with a `txt` prose leaf. That
    is a serialisation difference and must be nothing more — invariant #11's
    claim, applied to the one document where it is easiest to break, because
    the nested renderer relocates prose into a child element and a relocation
    that lost or duplicated a paragraph would still validate.

    A multiset, not a set: deduplication would hide exactly the failure the
    relocation makes plausible — a section's prose emitted both under its parent
    and under itself. The two forms are also asserted to be genuinely different
    documents, so the equality cannot pass by the forms having collapsed.
    """
    flat = render_anexo(model(), annex(), nested=False)
    nested = render_anexo(model(), annex(), nested=True)

    assert to_xml_string(flat) != to_xml_string(nested)

    flat_words = Counter(words(leaf_texts(flat)))
    nested_words = Counter(words(leaf_texts(nested)))

    assert flat_words, "the annex must carry text, or this test is vacuous"
    assert flat_words == nested_words, (
        f"the two annex forms disagree — "
        f"flat-only {list((flat_words - nested_words).items())[:10]}, "
        f"nested-only {list((nested_words - flat_words).items())[:10]}"
    )
