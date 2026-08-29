"""The nested `generico-aninhado` emitter, checked against the whole corpus.

Cycle 5b writes the *same* `DocumentModel` objects Cycle 5 writes, differently:
one `AgrupamentoHierarquico` per `Section`, actually nested. That is legal only
under the maintainers' unreleased change (plan §2.10), so this module's subject
is not "does it render" — it does, always, by spec answer R-2 — but **whether
the nesting is honest**, and whether the three things the schema imposes on it
were paid for rather than assumed.

What is under test, and why each matters:

* **The opt-in gate is real** — `test_all_samples_validate_on_proposed_schemas`
  against `lexml-proposed/`, and its anti-vacuity twin
  `test_nested_output_is_invalid_on_shipped_schemas`. A validity test whose
  schema accepts everything proves nothing; the pair is what makes E1 evidence.
* **The three §5.4 constraints.** Each is a measured schema fact (spec §3's 24
  probes), each cost the emitter something, and each therefore gets its own
  regression: prose after subsections (C1), a non-`AH` child always (C2), no
  bare `<p>` under an `AH` (C3). C1 is asserted over `Bloco` as well as
  `Agrupamento` — probe **K**, amendment **A-5b.1**: the plan states C1 for own
  prose, but the extension `choice` binds every non-`AH` child, so an emitter
  written to §5.4's literal wording emits invalid XML on any section that has
  both subsections and an `ordem` marker.
* **Reversibility by native axes** —
  `test_native_axis_reconstruction_equals_id_paths`, exit criterion E2 and the
  cycle's headline. Cycle 5 could only rebuild the tree by parsing `id` strings,
  because `Agrupamento` cannot nest. Here `ancestor::`/`descendant::` must
  suffice, and the two readings must agree: a nesting that disagreed with the
  ids would mean the tree and its citable URNs describe different documents.
* **Rule A is now unnecessary** — `test_rule_a_holds_and_is_unnecessary`. Not
  merely satisfied: *unexpressible* to violate, since a child element is built
  inside its parent element.
* **The cost of C1 is repaid** — `test_ordem_records_document_order`. Serialised
  sibling position is no longer reading order, so `Bloco nome="ordem"` is the
  only order channel a consumer may trust.

Structural markers (`ordem`, `vazio`) must stay invisible to extraction, or
Constraint 2's filler would silently become a conservation bug — asserted here
on the emitter's own output and again, bundle-wide, in
`tests/regression/test_cross_emitter.py`.

Corpus caveat, and why synthetic fixtures appear below. Only 9 of the 16
emitted documents contain an `AgrupamentoHierarquico` at all, and no sample
exercises a section that has neither a label nor a heading, or an empty body,
or a `vazio` sitting where prose would go while its siblings have prose. Where
a sample cannot discriminate a correct emitter from a broken one this module
says so and adds a synthetic `Section` tree, following the standing precedent
of amendments A-1.3 and A-4.6.
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.hierarchy import HierarchyDoc
from lexml_nonstat.hierarchy.tree import HierarchyTree
from lexml_nonstat.ingest import Inline, StyledDoc, read_docx
from lexml_nonstat.model import DocumentModel, build_model
from lexml_nonstat.model.nodes import Para, Section
from lexml_nonstat.render import (
    EMITTER,
    EMPTY_BLOCO,
    ORDER_BLOCO,
    IdAllocator,
    RenderedDocument,
    all_ids,
    leaf_texts,
    local_name,
    missing_prefixes,
    render_generico,
    render_generico_aninhado,
    render_generico_aninhado_from_docx,
)
from lexml_nonstat.validate.schema import PROPOSED, SHIPPED, validate

from tests.conftest import nested_available, requires_nested

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

LEX = "{http://www.lexml.gov.br/1.0}"

#: The four-level sample plan §2.10 names as the motivating example:
#: `2.` → `2.1` → `2.3` → `2.3.1`. Its real tree goes five deep
#: (`6.3` → `I` → `a)`), which is why depth is asserted as *at least* four.
DEEP_SAMPLE = "pn_cst_38_19801031"
#: The one sample with an annex — the only exercise of the §2.9 split.
ANNEX_SAMPLE = "port_mf_277_20180607"
#: Samples whose body sections carry a `Rotulo`, a `NomeAgrupador`, or both.
#: Only `pn_cst_38` and `parecer_93` carry both, so the other two are here to
#: cover each native on its own — `port_mf_277`'s annex is labels with no
#: headings, `sumula_stj_125` is headings with no labels.
LABELLED_SAMPLES = (
    DEEP_SAMPLE,
    "parecer_93_2018_decor_cgu_agu",
    ANNEX_SAMPLE,
    "sumula_stj_125",
)

# A test that names a sample is only as good as the name still existing, so
# collection fails loudly on a rename rather than skipping what it was for.
assert len(SAMPLES) == 15, SAMPLES
assert {DEEP_SAMPLE, ANNEX_SAMPLE, *LABELLED_SAMPLES} <= set(SAMPLES)

#: Rendering all 15 takes about a second; once per test would not.
_CACHE: dict[str, tuple[DocumentModel, RenderedDocument]] = {}


def rendered(name: str) -> tuple[DocumentModel, RenderedDocument]:
    """The model and the nested bundle for one sample, built once per session."""
    if name not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        model = build_model(read_docx(path), filename=path.name)
        _CACHE[name] = (model, render_generico_aninhado(model))
    return _CACHE[name]


def bundle(name: str) -> RenderedDocument:
    return rendered(name)[1]


# --------------------------------------------------------------------------
# Readers — deliberately independent of the emitter's own helpers
# --------------------------------------------------------------------------


def reparse(document: etree._Element) -> etree._Element:
    """Serialise and read back, so a test sees only what a consumer would."""
    return etree.fromstring(
        etree.tostring(document, encoding="utf-8", xml_declaration=False)
    )


def parte_principal(document: etree._Element) -> etree._Element | None:
    """The document's `PartePrincipal`, or `None` for an empty document."""
    for node in document.iter(f"{LEX}PartePrincipal"):
        return node
    return None


def hierarquicos(document: etree._Element) -> list[etree._Element]:
    """Every `AgrupamentoHierarquico`, document order."""
    return list(document.iter(f"{LEX}AgrupamentoHierarquico"))


def child_named(element: etree._Element, tag: str) -> list[etree._Element]:
    """Direct children with local name `tag` — never descendants.

    Direct-child selection is the whole point in a *nested* document: `iter()`
    would reach into subsections and make every per-section assertion below
    silently about the wrong element.
    """
    return [c for c in element if local_name(c.tag) == tag]


def child_bloco(element: etree._Element, nome: str) -> str | None:
    """A direct `Bloco` child's text, or `None` when there is none."""
    for child in child_named(element, "Bloco"):
        if child.get("nome") == nome:
            return norm("".join(child.itertext()))
    return None


def has_child_bloco(element: etree._Element, nome: str) -> bool:
    """Whether a direct `Bloco` child with that `@nome` exists, empty or not."""
    return any(
        c.get("nome") == nome for c in child_named(element, "Bloco")
    )


def native(element: etree._Element, tag: str) -> str | None:
    """A direct `Rotulo`/`NomeAgrupador` child's text, `None` when absent."""
    found = child_named(element, tag)
    return norm("".join(found[0].itertext())) if found else None


def norm(text: str | None) -> str | None:
    """Collapse whitespace; `None` and `""` both become `None`.

    Pretty-printing and the source's own spacing are not part of what a test
    about *structure* should be sensitive to.
    """
    if text is None:
        return None
    collapsed = " ".join(text.split())
    return collapsed or None


def documents_with_sections() -> list[tuple[str, int]]:
    """`(sample, document position)` for every document carrying an `AH`.

    9 of the 16 emitted documents have a body tree; the other 7 are all
    front/back matter and would make a constraint test pass vacuously.
    """
    out: list[tuple[str, int]] = []
    for name in SAMPLES:
        for position, document in enumerate(bundle(name).documents):
            if hierarquicos(document):
                out.append((name, position))
    return out


def where(position: int) -> str:
    return "primary" if position == 0 else f"annex {position}"


# --------------------------------------------------------------------------
# Synthetic fixtures — where the corpus cannot discriminate
# --------------------------------------------------------------------------


def para(text: str) -> Para:
    return Para(inlines=(Inline(text),))


def synthetic(sections: tuple[Section, ...]) -> DocumentModel:
    """A `DocumentModel` whose body is exactly `sections`.

    Built by replacing the hierarchy of a model assembled from an *empty*
    `StyledDoc`, so the metadata, segmentation and routing are real objects of
    the right types and only the tree is hand-made. That keeps the emitter on
    its ordinary code path — nothing here is a mock.
    """
    base = build_model(
        StyledDoc(blocks=(), source="synthetic.docx"), filename="synthetic.docx"
    )
    return dataclasses.replace(
        base, hierarchy=HierarchyDoc(body=HierarchyTree(sections=sections))
    )


# --------------------------------------------------------------------------
# T-1 / T-2 — validity, and the proof that validity means something
# --------------------------------------------------------------------------


@requires_nested
@pytest.mark.parametrize("name", SAMPLES)
def test_all_samples_validate_on_proposed_schemas(name: str) -> None:
    """Every nested document validates on both **proposed** schemas — E1.

    "Every document" is the whole bundle: an annex is a *sibling* `LexML`
    document under plan §2.9, and `port_mf_277`'s annex is where 65 of the
    corpus's nested sections live, so validating only `bundle.primary` would
    leave the deepest exercise in the corpus entirely unchecked.

    Skipped, never failed, when `lexml-proposed/` is absent or unpatched
    (amendment A-R.9): the skip reason is the probe's own diagnostic, so a
    missing directory reads differently from a flat schema.

    The failure message carries `report.summary()`, which names the schema and
    quotes the XSD's own complaint, because "invalid" alone is not a finding.
    """
    b = bundle(name)
    for position, document in enumerate(b.documents):
        report = validate(document, "both", generation=PROPOSED)
        assert report.ok, (
            f"{name} ({where(position)}) is not valid on the proposed "
            f"schemas:\n{report.summary()}"
        )


@pytest.mark.parametrize("name", SAMPLES)
def test_nested_output_is_invalid_on_shipped_schemas(name: str) -> None:
    """Nested output is rejected by `lexml/` — so T-1 is not vacuous.

    This is the anti-vacuity guard for the whole module and the reason
    `generico-aninhado` is opt-in at all (§5.2, §2.11). If the shipped schemas
    accepted this output, "valid on proposed" would be a statement about
    nothing, the capability probe would be theatre, and the flat emitter would
    have been written for a constraint that does not exist.

    It needs no skip marker: `lexml/` is vendored and always present.

    The assertion is sharper than "some sample is invalid". Exactly the
    documents that *contain* an `AgrupamentoHierarquico` must be rejected, and
    the 6 that contain none — `REsp_1306393`, `ad_pgfn_3`, `ad_srf_22`,
    `adn_cosit_19`, `sumula_carf_42` and `port_mf_277`'s *primary*, all pure
    front/back matter rendered by shared Cycle 5 code (amendment A-5b.5) — must
    still be **accepted**, which is what proves the rejection is caused by the
    nesting and not by something incidental the nested emitter happens to write.
    """
    for position, document in enumerate(bundle(name).documents):
        report = validate(document, "both", generation=SHIPPED)
        nested = hierarquicos(document)
        if nested:
            assert not report.ok, (
                f"{name} ({where(position)}) carries {len(nested)} "
                "AgrupamentoHierarquico and yet the shipped schemas accept it; "
                "the opt-in gate would be meaningless"
            )
        else:
            assert report.ok, (
                f"{name} ({where(position)}) has no nested element but is "
                f"rejected by the shipped schemas:\n{report.summary()}"
            )


# --------------------------------------------------------------------------
# T-3 .. T-6 — the three §5.4 constraints
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_constraint_1_no_agrupamento_precedes_a_subsection(name: str) -> None:
    """No non-`AH` child may precede an `AH` child — C1, plus **A-5b.1**.

    The measured content model is
    `Rotulo? NomeAgrupador? AgrupamentoHierarquico* (Agrupamento | Bloco)+`:
    XSD appends the extension `choice` *after* the base sequence's
    `AgrupamentoHierarquico*`, so everything in that choice must follow every
    subsection. Probe B (own prose first) is invalid; probe **K** shows the same
    of `Bloco`, which the plan's §5.4 wording does not say — hence amendment
    **A-5b.1**, and hence this test asserts over `Agrupamento` *and* `Bloco`
    rather than over prose alone.

    Asserting it here rather than leaving it to the schema is deliberate: T-1
    would catch the violation, but as an "element is not expected" from the XSD
    on some document, which names neither the rule nor the element that broke
    it. This names both, and it keeps working on a checkout with no
    `lexml-proposed/` at all.
    """
    offenders: list[str] = []
    for position, document in enumerate(bundle(name).documents):
        for element in hierarquicos(document):
            tags = [local_name(c.tag) for c in element]
            if "AgrupamentoHierarquico" not in tags:
                continue
            last_ah = len(tags) - 1 - tags[::-1].index("AgrupamentoHierarquico")
            early = [
                (index, tag)
                for index, tag in enumerate(tags[:last_ah])
                if tag in ("Agrupamento", "Bloco")
            ]
            if early:
                offenders.append(
                    f"{where(position)} {element.get('id')}: {early} precede "
                    f"the subsection at position {last_ah}"
                )
    assert not offenders, f"{name} violates Constraint 1:\n" + "\n".join(offenders)


@pytest.mark.parametrize("name", SAMPLES)
def test_constraint_2_every_ah_has_a_non_ah_child(name: str) -> None:
    """Every `AH` carries at least one child from the extension choice — C2.

    The choice is `minOccurs="1"` (probe D), so a section that is a bare
    container of subsections is invalid — and an empty `<Agrupamento/>` does not
    rescue it either (probe W: `blocksreq`). `<Bloco nome="vazio"/>` is the
    resolution, and this test is the reason the emitter may not skip it "because
    the section has children anyway".

    Neither `Rotulo` nor `NomeAgrupador` counts: they sit in the base sequence,
    before the choice, and a section carrying only those is invalid.
    """
    for position, document in enumerate(bundle(name).documents):
        for element in hierarquicos(document):
            tags = [local_name(c.tag) for c in element]
            fillers = [t for t in tags if t in ("Agrupamento", "Bloco")]
            assert fillers, (
                f"{name} ({where(position)}): {element.get('id')} has only "
                f"{tags} — Constraint 2 requires a non-AH child"
            )


def test_constraint_2_vazio_is_invisible_to_extraction() -> None:
    """`vazio` satisfies the schema and contributes no text — C2's whole point.

    Synthetic, because the corpus cannot discriminate here. `pn_cst_38`'s
    section `2.` is a genuine `vazio` case, but every sample that produces one
    also produces plenty of prose around it, so a `vazio` that *did* leak text
    would be lost in the noise of a corpus-wide conservation count. A tree whose
    only content is one prose leaf makes the claim exactly checkable: extraction
    must yield the label, the heading and that one paragraph, and nothing else.

    That `vazio` carries no text is what keeps Constraint 2's filler a
    structural marker rather than a conservation bug: `leaf_texts` reads `p`,
    `td`, `th`, `li`, `Rotulo`, `NomeAgrupador` and the two text-bearing `Bloco`
    names, and `vazio` is in none of those. The mirrored assertion — that the
    marker's presence is not itself the reason nothing leaked — is that the
    sibling `ordem` marker's *value* is absent too.
    """
    model = synthetic(
        (
            Section(
                label="1.",
                heading="Container",
                level=1,
                kind="secao",
                children=(
                    Section(
                        label="1.1",
                        level=2,
                        kind="subsecao",
                        body=(para("a única prosa"),),
                    ),
                ),
            ),
        )
    )
    b = render_generico_aninhado(model)

    outer = hierarquicos(b.primary)[0]
    assert has_child_bloco(outer, EMPTY_BLOCO), (
        "a section with subsections and no own prose must carry the vazio "
        f"filler; children are {[local_name(c.tag) for c in outer]}"
    )
    assert not child_named(outer, "Agrupamento"), (
        "an empty Agrupamento is invalid (probe W); vazio is a Bloco"
    )

    assert list(b.texts) == ["1.", "Container", "1.1", "a única prosa"], b.texts

    # The `ordem` values are "0" for both sections here; neither may surface.
    assert "0" not in b.texts

    if nested_available():
        report = validate(b.primary, "both", generation=PROPOSED)
        assert report.ok, report.summary()


@pytest.mark.parametrize("name", SAMPLES)
def test_constraint_3_no_bare_p_under_ah(name: str) -> None:
    """No `<p>` is a direct child of an `AgrupamentoHierarquico` — C3.

    Probe E: the maintainers made `AgrupamentoHierarquico` carry `Agrupamento`
    and `Bloco`, **not** `p`, so plan §2.1's row E is still a rejection and
    prose must be wrapped. It is a tempting shortcut precisely because it reads
    naturally and is one element shorter, which is why it gets a named test
    rather than being left to the XSD.
    """
    for position, document in enumerate(bundle(name).documents):
        for element in hierarquicos(document):
            bare = child_named(element, "p")
            assert not bare, (
                f"{name} ({where(position)}): {element.get('id')} has "
                f"{len(bare)} bare <p>; prose must be wrapped in an "
                "Agrupamento (probe E)"
            )


# --------------------------------------------------------------------------
# T-7 / T-8 — what the natives retire
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_no_retired_bloco_names(name: str) -> None:
    """`rotulo`, `nomeAgrupador` and `nivel` appear nowhere — E5.

    Each is a Cycle 5 workaround for something the shipped schemas lacked, and
    each is now native or derivable: `Rotulo` and `NomeAgrupador` are elements,
    and depth is `count(ancestor::AgrupamentoHierarquico)`. Leaving a retired
    marker in would be worse than redundant — a `nivel` that disagreed with the
    tree gives two answers to one question, and a consumer has no way to know
    which one the emitter meant.

    Checked over the whole document, not just under sections: the front and
    back regions are shared Cycle 5 code, and this is what proves they never
    emitted a `nivel` either.
    """
    retired = {"rotulo", "nomeAgrupador", "nivel"}
    for position, document in enumerate(bundle(name).documents):
        found = Counter(
            nome
            for node in document.iter(f"{LEX}Bloco")
            if (nome := node.get("nome")) in retired
        )
        assert not found, (
            f"{name} ({where(position)}) still emits retired Bloco names: "
            f"{dict(found)}"
        )


@pytest.mark.parametrize("name", LABELLED_SAMPLES)
def test_rotulo_and_nomeagrupador_are_native(name: str) -> None:
    """The natives carry exactly the strings the flat emitter put in `Blocos`.

    Two claims, and the second is the one with teeth. That `Rotulo` and
    `NomeAgrupador` are *elements* is easy; that they carry the **same text**
    the flat emitter carried is what makes the two emitters two renderings of
    one document rather than two parsers. A nested emitter that quietly
    normalised `2.1 -` to `2.1`, or dropped a heading it judged redundant,
    would pass every schema and every constraint test above.

    So the flat bundle is rendered from the same model and its section
    `Bloco nome="rotulo"`/`"nomeAgrupador"` values are compared as multisets —
    multisets, not a positional zip, because Constraint 1 reorders the nested
    document and a positional comparison would be asserting the reordering
    rather than the content.
    """
    model, b = rendered(name)
    flat = render_generico(model)

    nested_labels: Counter[str] = Counter()
    nested_headings: Counter[str] = Counter()
    for document in b.documents:
        for element in hierarquicos(document):
            if (label := native(element, "Rotulo")) is not None:
                nested_labels[label] += 1
            if (heading := native(element, "NomeAgrupador")) is not None:
                nested_headings[heading] += 1

    flat_labels: Counter[str] = Counter()
    flat_headings: Counter[str] = Counter()
    for document in flat.documents:
        for element in document.iter(f"{LEX}Agrupamento"):
            for child in element:
                if local_name(child.tag) != "Bloco":
                    continue
                text = norm("".join(child.itertext()))
                if text is None:
                    continue
                if child.get("nome") == "rotulo":
                    flat_labels[text] += 1
                elif child.get("nome") == "nomeAgrupador":
                    flat_headings[text] += 1

    assert nested_labels or nested_headings, (
        f"{name} is expected to carry labelled or headed sections"
    )
    assert nested_labels == flat_labels, (
        f"{name}: nested Rotulo text differs from the flat emitter's; "
        f"only in nested: {nested_labels - flat_labels}, "
        f"only in flat: {flat_labels - nested_labels}"
    )
    assert nested_headings == flat_headings, (
        f"{name}: nested NomeAgrupador text differs from the flat emitter's; "
        f"only in nested: {nested_headings - flat_headings}, "
        f"only in flat: {flat_headings - nested_headings}"
    )


# --------------------------------------------------------------------------
# T-9 — reversibility by native axes (exit criterion E2)
# --------------------------------------------------------------------------


def tree_by_axes(document: etree._Element) -> tuple:
    """Rebuild the section tree using **only** parent/child relationships.

    This is the function E2 is about, so its independence is the test. It never
    reads an `id`, never splits a string on `_`, and never sees the model: it
    recurses over `AgrupamentoHierarquico` children, which is `descendant::` and
    `ancestor::` in Python. Given a document re-parsed from a serialised string,
    that is precisely the information an XSLT consumer has.

    Returns nested `(label, heading, kind, children)` tuples — deliberately not
    depth, since under the nested model depth *is* the nesting and including it
    would let the tuple agree by construction.
    """

    def walk(element: etree._Element) -> tuple:
        return tuple(
            (
                native(child, "Rotulo"),
                native(child, "NomeAgrupador"),
                child.get("nome"),
                walk(child),
            )
            for child in child_named(element, "AgrupamentoHierarquico")
        )

    pp = parte_principal(document)
    return walk(pp) if pp is not None else ()


def tree_by_id_paths(document: etree._Element) -> tuple:
    """The same shape, rebuilt from `id` path prefixes — Cycle 5's reading.

    Attaches each section to the section whose id is its longest proper prefix,
    exactly as `tests/unit/test_render_generico.py` does for the flat emitter.
    It ignores the XML's own nesting entirely — it collects every
    `AgrupamentoHierarquico` with `iter()` and rebuilds from strings — so it is
    a genuinely second reading of the document and not a paraphrase of the
    first.
    """
    node: dict[str, tuple] = {}
    order: list[str] = []
    for element in document.iter(f"{LEX}AgrupamentoHierarquico"):
        ident = element.get("id")
        children: list = []
        node[ident] = (
            native(element, "Rotulo"),
            native(element, "NomeAgrupador"),
            element.get("nome"),
            children,
        )
        order.append(ident)

    roots: list[tuple] = []
    for ident in order:
        ancestors = [
            other
            for other in node
            if other != ident and ident.startswith(f"{other}_")
        ]
        if ancestors:
            node[max(ancestors, key=len)][3].append(node[ident])
        else:
            roots.append(node[ident])

    def freeze(items) -> tuple:
        return tuple((a, b, c, freeze(kids)) for a, b, c, kids in items)

    return freeze(roots)


@pytest.mark.parametrize("name", SAMPLES)
def test_native_axis_reconstruction_equals_id_paths(name: str) -> None:
    """The nesting and the `id` paths describe the same tree — E2.

    The cycle's headline result. Cycle 5 could only recover ancestry by parsing
    `id` strings, because `Agrupamento` cannot nest; §2.10's whole argument for
    the maintainers' change is that `ancestor::`/`descendant::` recover it with
    no `id`-path parsing at all. This asserts that they do — over a document
    **re-parsed from its serialised bytes**, so nothing survives from the model
    or from lxml's in-memory identity — and, just as importantly, that the two
    readings *agree*.

    Agreement is the load-bearing half. The ids stay path-composed (§5.2) so a
    segment URN means the same thing whichever emitter produced it; a document
    whose nesting said one thing and whose `pp1_agh1_agh3` said another would
    hand a citation and a breadcrumb to two different sections, and both would
    look correct in isolation.
    """
    for position, document in enumerate(bundle(name).documents):
        reparsed = reparse(document)
        by_axes = tree_by_axes(reparsed)
        by_ids = tree_by_id_paths(reparsed)
        assert by_axes == by_ids, (
            f"{name} ({where(position)}): the nesting and the id paths "
            "describe different trees"
        )
        # ...and it is the model's tree, not merely two consistent readings of
        # a wrong one.
        model = rendered(name)[0]
        trees = (model.body,) + tuple(a.tree for a in model.annexes)
        assert by_axes == tree_by_model(trees[position].sections), (
            f"{name} ({where(position)}): the emitted tree is not the model's"
        )


def tree_by_model(sections) -> tuple:
    """The oracle: the same shape walked from `Section.children`."""
    return tuple(
        (
            norm(s.label),
            norm(s.heading),
            s.kind,
            tree_by_model(s.children),
        )
        for s in sections
    )


# --------------------------------------------------------------------------
# T-10 / T-11 — ids
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_ids_unique_document_wide(name: str) -> None:
    """No `id` is issued twice, in a document or across the bundle — #6.

    `xsd:ID` makes a duplicate invalid, so the schema is a second net — but it
    only fires once the document is written, and it cannot see across the
    primary/annex split at all. `IdAllocator` refusing a duplicate is the first
    net; this proves it was actually consulted for every id that reached the
    XML, including the new `agh` and `txt` tokens (D-2) which are the only ids
    this cycle introduced.
    """
    b = bundle(name)

    for position, document in enumerate(b.documents):
        counts = Counter(all_ids(document))
        repeated = {k: v for k, v in counts.items() if v > 1}
        assert not repeated, (
            f"{name} ({where(position)}) repeats ids: {repeated}"
        )

    repeated = {k: v for k, v in Counter(b.ids).items() if v > 1}
    assert not repeated, f"{name} repeats ids across the bundle: {repeated}"


@pytest.mark.parametrize("name", SAMPLES)
def test_rule_a_holds_and_is_unnecessary(name: str) -> None:
    """Rule A still holds — and could not be broken if the emitter tried — E7.

    Two claims, and the second is the interesting one.

    *It holds*: `missing_prefixes()` finds no gap, over every id in every
    document. Plan §2.4's first measured bug was an id of `pp1_agr1_agr2_agr1`
    with no `pp1_agr1_agr2` element, which produced a breadcrumb silently
    missing its middle ancestor.

    *It is unnecessary*: under a nested emitter a missing ancestor is not a
    broken breadcrumb but a **malformed tree that no serialisation can
    express** — a child element is built inside its parent element. The
    remaining way to fabricate a gap would be to compose an id under a parent
    that was never issued, and `IdAllocator.child()` refuses that outright. So
    the gapped tree Cycle 5 had to test for is, here, unconstructible; the
    allocator's refusal is asserted directly, because "we could not think of a
    way to break it" is not evidence.
    """
    for position, document in enumerate(bundle(name).documents):
        pp = parte_principal(document)
        if pp is None:
            continue
        root = pp.get("id")
        gaps = missing_prefixes(all_ids(document), root=root)
        assert gaps == (), (
            f"{name} ({where(position)}) has Rule A gaps: {gaps}"
        )

    allocator = IdAllocator("pp1")
    with pytest.raises(ValueError, match="unknown parent id"):
        allocator.child("pp1_agh1_agh2", "agh")
    # And the honest path — issuing the parent first — does work, so the
    # refusal above is about the gap and not about the token.
    parent = allocator.child(allocator.child("pp1", "agh"), "agh")
    assert parent == "pp1_agh1_agh1"
    assert allocator.child(parent, "txt") == "pp1_agh1_agh1_txt1"


# --------------------------------------------------------------------------
# T-12 — the order channel Constraint 1 made necessary
# --------------------------------------------------------------------------


def ordem_of(element: etree._Element) -> int:
    """The section's own `ordem` index, as an integer."""
    value = child_bloco(element, ORDER_BLOCO)
    assert value is not None, (
        f"{element.get('id')} carries no {ORDER_BLOCO} marker"
    )
    return int(value)


def test_ordem_records_document_order() -> None:
    """`ordem` recovers the source order that serialised position destroys.

    Constraint 1 is the cycle's real cost: a section's own prose and its own
    `ordem` marker must be serialised *after* all its subsections, so sibling
    position in the XML is no longer reading order. `Bloco nome="ordem"` (spec
    D-5, answer R-3) is the only channel that survives, and it is emitted
    uniformly on every section rather than only on unlabelled ones, so a reader
    never needs a second code path and never has to sort `Rotulo` strings —
    `2.`, `2.1`, `IV`, `a)` are not comparable to each other.

    Two exercises. `pn_cst_38` pins that the values are the real document
    positions of the real corpus. But every one of its sections happens to be
    emitted in ascending `ordem`, so on its own it would also pass against an
    emitter that wrote a plain sibling counter and against one that omitted the
    marker on sections whose position is already implied — a synthetic tree with
    a **deliberately shuffled** relationship between position and order is what
    discriminates. Here the marker is checked to disagree with position on
    purpose, which is the only observation that proves it is a recorded datum
    rather than a recomputed one.
    """
    _, b = rendered(DEEP_SAMPLE)
    top = child_named(parte_principal(b.primary), "AgrupamentoHierarquico")
    assert [ordem_of(s) for s in top] == list(range(len(top))), (
        "top-level ordem values must be the 0-based document positions"
    )
    deep = [s for s in hierarquicos(b.primary) if s.get("id") == "pp1_agh1_agh3"]
    assert len(deep) == 1
    assert [ordem_of(c) for c in child_named(deep[0], "AgrupamentoHierarquico")] == [
        0,
        1,
        2,
        3,
    ]
    # Every section in the corpus carries one, uniformly (answer R-3).
    for name in SAMPLES:
        for document in bundle(name).documents:
            for element in hierarquicos(document):
                assert child_bloco(element, ORDER_BLOCO) is not None, (
                    f"{name}: {element.get('id')} has no {ORDER_BLOCO} marker"
                )

    # A synthetic parent whose children are *not* in ascending source order
    # would be indistinguishable from one that is, if `ordem` were a counter.
    children = tuple(
        Section(label=label, level=2, kind="subsecao", body=(para(label),))
        for label in ("a", "b", "c")
    )
    model = synthetic(
        (Section(label="1.", level=1, kind="secao", children=children),)
    )
    b = render_generico_aninhado(model)
    emitted = child_named(hierarquicos(b.primary)[0], "AgrupamentoHierarquico")
    assert [native(e, "Rotulo") for e in emitted] == ["a", "b", "c"]
    assert [ordem_of(e) for e in emitted] == [0, 1, 2]

    # The parent's own marker sits *after* its subsections and still records
    # the parent's position, not the count of children it just wrote — the
    # exact confusion A-5b.1's reordering invites.
    parent = hierarquicos(b.primary)[0]
    tags = [local_name(c.tag) for c in parent]
    assert tags.index("Bloco") > max(
        i for i, t in enumerate(tags) if t == "AgrupamentoHierarquico"
    ), f"the ordem marker must follow every subsection, got {tags}"
    assert ordem_of(parent) == 0


# --------------------------------------------------------------------------
# T-13 — plan §2.10's motivating example
# --------------------------------------------------------------------------


def test_pn_cst_38_four_levels() -> None:
    """`2.` → `2.1` → `2.3` → `2.3.1` nest natively — E8.

    Plan §2.10's motivating example, and the concrete claim the endorsement
    letter (§11) makes to the maintainers: this document's four levels are
    *natively representable*, recoverable by `ancestor::` alone. Cycle 5 could
    only express them as flat siblings with the depth in the `id` path.

    Walked by element nesting rather than by id, since native recovery is the
    property being demonstrated. The breadcrumb is `NomeAgrupador` joined along
    the ancestor chain — precisely what §2.4's XSLT produced from `id` prefixes
    and what `GeraCSVporArtigoPorAgrupador.xsl` already does for articulated
    documents (§11's ergonomic argument).

    A note on counting, because §2.10's phrase is easy to mis-assert. The four
    names `2.` → `2.1` → `2.3` → `2.3.1` are **not** one chain: `2.1` and `2.3`
    are siblings under `2.`, so the chain is three `AgrupamentoHierarquico`
    deep and the *fourth* level of the plan's phrase is the `PartePrincipal`
    that roots the ids (`pp1_agh1_agh3_agh1`). The corpus's genuinely deeper
    chain is `6.` → `6.3` → `I` → `a)`, four nested elements, and it is checked
    too — otherwise a maximum depth of three would pass a test whose subject is
    that arbitrary depth is now expressible.

    The maximum is asserted as *at least* four rather than exactly four: pinning
    it would make an unrelated hierarchy improvement look like a regression in a
    test about §2.10's example.
    """
    b = bundle(DEEP_SAMPLE)
    pp = parte_principal(b.primary)

    def descend(element: etree._Element, label: str) -> etree._Element:
        """The one child whose rótulo is `label`, ignoring its trailing dash.

        The corpus writes `2.1 -` and `I -`, so the comparison strips the
        separator rather than matching a prefix: a prefix match would make `I`
        ambiguous with `II` and quietly pick whichever came first.
        """
        found = [
            c
            for c in child_named(element, "AgrupamentoHierarquico")
            if (native(c, "Rotulo") or "").rstrip(" -") == label.rstrip(" -")
        ]
        assert len(found) == 1, (
            f"expected exactly one child labelled {label!r} under "
            f"{element.get('id') or 'PartePrincipal'}, got "
            f"{[native(c, 'Rotulo') for c in child_named(element, 'AgrupamentoHierarquico')]}"
        )
        return found[0]

    secao = descend(pp, "2.")
    sub1 = descend(secao, "2.1")
    sub3 = descend(secao, "2.3")
    item = descend(sub3, "2.3.1")

    assert secao.get("nome") == "secao"
    assert sub1.get("nome") == "subsecao"
    assert sub3.get("nome") == "subsecao"
    assert item.get("nome") == "item"

    # Ids stay path-composed, so §2.4's URN fragments still resolve (§5.2).
    assert secao.get("id") == "pp1_agh1"
    assert sub1.get("id") == "pp1_agh1_agh1"
    assert sub3.get("id") == "pp1_agh1_agh3"
    assert item.get("id") == "pp1_agh1_agh3_agh1"

    # Depth by native axes alone — no id parsing. `2.1` and `2.3` are siblings.
    def ancestor_depth(element: etree._Element) -> int:
        depth = 0
        node = element.getparent()
        while node is not None:
            if local_name(node.tag) == "AgrupamentoHierarquico":
                depth += 1
            node = node.getparent()
        return depth

    assert [ancestor_depth(e) for e in (secao, sub1, sub3, item)] == [0, 1, 1, 2]
    assert sub1.getparent() is secao and sub3.getparent() is secao
    assert item.getparent() is sub3

    # The corpus's four-deep chain: 6. → 6.3 → I → a).
    arbitramento = descend(pp, "6.")
    exemplificacao = descend(arbitramento, "6.3")
    inciso = descend(exemplificacao, "I")
    alinea = descend(inciso, "a)")
    assert [
        ancestor_depth(e)
        for e in (arbitramento, exemplificacao, inciso, alinea)
    ] == [0, 1, 2, 3]
    assert [e.get("nome") for e in (inciso, alinea)] == ["inciso", "alinea"]
    assert alinea.get("id") == "pp1_agh5_agh3_agh1_agh1"

    # The §2.4 breadcrumb, rebuilt from the ancestor chain's NomeAgrupador.
    def breadcrumb(element: etree._Element) -> str:
        parts: list[str] = []
        node: etree._Element | None = element
        while node is not None and local_name(node.tag) == "AgrupamentoHierarquico":
            if (heading := native(node, "NomeAgrupador")) is not None:
                parts.append(heading)
            node = node.getparent()
        return " | ".join(reversed(parts))

    assert breadcrumb(secao) == "DAS SOCIEDADES COOPERATIVAS"
    assert breadcrumb(sub1) == "DAS SOCIEDADES COOPERATIVAS | Empresas de serviços"
    assert breadcrumb(item) == (
        "DAS SOCIEDADES COOPERATIVAS | Operações das Sociedades Cooperativas "
        "| Atos Cooperativos"
    )

    deepest = max(ancestor_depth(e) for e in hierarquicos(b.primary))
    assert deepest >= 3, (
        f"{DEEP_SAMPLE} must nest at least four AgrupamentoHierarquico deep, "
        f"deepest chain is {deepest + 1}"
    )


# --------------------------------------------------------------------------
# T-14 — determinism
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_deterministic(name: str) -> None:
    """Same input, byte-identical output — invariant #4.

    Deliberately re-read from the DOCX rather than re-serialising one bundle: a
    dict iteration order or a `set` leaking into id allocation would survive the
    weaker check and fail this one. The suite pins `referee=None` (plan §9.3),
    so nothing here depends on a cache being warm.

    It matters more for the nested emitter than for the flat one. Constraint 1
    forces the emitter to *reorder* the document, and a reordering that is not
    fully determined by the model is the kind of instability that shows up as
    golden churn on an unrelated commit rather than as a failure here.
    """
    path = SAMPLES_DIR / f"{name}.docx"
    first = render_generico_aninhado_from_docx(path).to_xml_strings()
    second = render_generico_aninhado_from_docx(path).to_xml_strings()
    assert first == second, f"{name} does not render deterministically"
    assert first == bundle(name).to_xml_strings(), (
        f"{name}: rendering from a prebuilt model differs from the "
        "from_docx path"
    )


# --------------------------------------------------------------------------
# T-15 — degenerate inputs
# --------------------------------------------------------------------------


def test_degenerate_inputs() -> None:
    """Nothing here raises, and everything here still validates.

    Cycle 5's contract, inherited verbatim: the corpus is 15 of 300+ documents,
    an empty or shapeless DOCX will happen, and an emitter that raises turns one
    bad input into a failed batch. Four degenerate shapes, none of which the
    corpus contains, and each of which exercises a different branch:

    * **an empty document** — no body, no front matter, no back matter. Also a
      real schema probe: `blocksreq` is `minOccurs="1"`, so an *empty*
      `PartePrincipal` is invalid and the emitter must omit it rather than emit
      it hollow;
    * **a section with neither label nor heading** — both natives are genuinely
      optional (probes Q/R/S), and this is the case where an emitter that
      wrote `<Rotulo/>` unconditionally would produce a document that still
      validates but claims a rótulo the source never had;
    * **a section with no body and no children** — the minimal `vazio` case,
      where the filler is the element's *only* child;
    * **a three-deep chain of empty sections** — `vazio` at every level, which
      is where Constraint 2 and Constraint 1 interact.
    """
    empty = build_model(
        StyledDoc(blocks=(), source="empty.docx"), filename="empty.docx"
    )
    result = render_generico_aninhado(empty)
    assert isinstance(result, RenderedDocument)
    assert result.emitter == EMITTER
    assert result.annexes == ()
    assert result.texts == ()
    pp = parte_principal(result.primary)
    assert pp is None or len(pp) > 0, (
        "an empty PartePrincipal is invalid on every schema; omit it instead"
    )

    anonymous = Section(level=1, kind="agrupamento", body=(para("sem rótulo"),))
    childless = Section(label="2.", level=1, kind="secao")
    chain = Section(
        label="3.",
        level=1,
        kind="secao",
        children=(
            Section(
                level=2,
                kind="subsecao",
                children=(Section(level=3, kind="item"),),
            ),
        ),
    )
    b = render_generico_aninhado(synthetic((anonymous, childless, chain)))

    elements = {e.get("id"): e for e in hierarquicos(b.primary)}
    assert set(elements) == {
        "pp1_agh1",
        "pp1_agh2",
        "pp1_agh3",
        "pp1_agh3_agh1",
        "pp1_agh3_agh1_agh1",
    }

    assert child_named(elements["pp1_agh1"], "Rotulo") == []
    assert child_named(elements["pp1_agh1"], "NomeAgrupador") == []
    assert child_named(elements["pp1_agh1"], "Agrupamento")

    assert [local_name(c.tag) for c in elements["pp1_agh2"]] == [
        "Rotulo",
        "Bloco",
        "Bloco",
    ]
    assert has_child_bloco(elements["pp1_agh2"], EMPTY_BLOCO)
    for ident in ("pp1_agh3", "pp1_agh3_agh1", "pp1_agh3_agh1_agh1"):
        assert has_child_bloco(elements[ident], EMPTY_BLOCO), ident

    assert list(b.texts) == ["sem rótulo", "2.", "3."]

    if nested_available():
        for document in (result.primary, b.primary):
            report = validate(document, "both", generation=PROPOSED)
            assert report.ok, report.summary()


# --------------------------------------------------------------------------
# T-16 — annexes (plan §2.9, amendment A-5.6)
# --------------------------------------------------------------------------


def test_annex_documents_emitted() -> None:
    """An annex is a standalone sibling document, unchanged from Cycle 5.

    The §2.9 convention is emitter-independent on purpose: only the annex's
    *sections* nest, so its `anexoN_pp` root, its `anexoN_tabM` tables, its
    `!anexoN` fragment and the primary's `ReferenciaAnexo` are all Cycle 5's.
    Asserting them again here is not duplication — 65 of the corpus's nested
    sections live inside this annex, and an emitter that got the nesting right
    but published it under the wrong root, or left the pointer dangling, would
    be producing a correct tree nobody can cite.

    Three things have to line up or the pointer dangles: the primary's
    `ReferenciaAnexo/@AlvoURN`, the annex's own `Identificacao/@URN`, and the
    fragment Cycle 2's URN builder produced.
    """
    model, b = rendered(ANNEX_SAMPLE)
    assert len(model.annexes) == 1
    assert len(b.annexes) == 1

    expected_urn = model.metadata.urn_with_fragment(model.annexes[0].fragment)
    assert expected_urn.endswith("!anexo1"), expected_urn

    referencias = list(b.primary.iter(f"{LEX}ReferenciaAnexo"))
    assert len(referencias) == 1
    assert referencias[0].get("AlvoURN") == expected_urn

    annex = b.annexes[0]
    assert local_name(annex.tag) == "LexML"
    assert [local_name(c.tag) for c in annex] == ["Metadado", "Anexo"]
    assert [
        i.get("URN") for i in annex.iter(f"{LEX}Identificacao")
    ] == [expected_urn]

    pp = parte_principal(annex)
    assert pp is not None and pp.get("id") == "anexo1_pp"

    # The nesting really is in the annex, and only there.
    assert not hierarquicos(b.primary)
    nested = hierarquicos(annex)
    assert len(nested) == 65, len(nested)
    for element in nested:
        assert re.fullmatch(r"anexo1_pp(_agh\d+)+", element.get("id")), (
            f"annex section id {element.get('id')!r} is off the §2.9 scheme"
        )

    # The annex's title is conserved exactly once, and stays Cycle 5's
    # `tituloAnexo` Agrupamento rather than becoming a section.
    label = model.annexes[0].label
    assert label
    titles = [
        a
        for a in annex.iter(f"{LEX}Agrupamento")
        if a.get("nome") == "tituloAnexo"
    ]
    assert len(titles) == 1
    assert titles[0].get("id") == "anexo1_pp_agr1"
    assert label not in leaf_texts(b.primary)
    assert [t for t in b.texts if t == label] == [label]

    # The primary must not carry the annex's content in any form.
    assert not list(b.primary.iter(f"{LEX}Anexo"))
