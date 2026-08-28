"""The flat `generico` emitter, checked against the whole corpus.

Cycle 5's deliverable is one function — `render_generico(model)` — and its
exit criteria are almost all *invariants*, not outputs: the goldens in
`tests/golden/generico/` record what the emitter says, and this module records
what it must never stop being true of, whatever it says.

Six of plan §9.2's cross-cutting invariants are discharged here:

* **#1 validity** — `test_all_15_validate_on_both_schemas`, the cycle's exit
  criterion E1/E2. Every document in the bundle, primary *and* annex, on
  `lexml-br-rigido.xsd` *and* `lexml09-flexivel.xsd`.
* **#3 reversibility** — `test_tree_reconstructable_from_xml_alone`. The one
  that justifies the whole flattening design: `Agrupamento` cannot nest
  (plan §2.1), so the tree is emitted as siblings and its depth carried out of
  band. If the tree cannot be rebuilt from the XML, the flattening has lost the
  document's shape and the emitter is a lossy renderer rather than a parser.
* **#4 determinism** — `test_rendering_is_deterministic`.
* **#5 id uniqueness** — `test_ids_unique_document_wide`.
* **#6 ancestor totality (Rule A)** — `test_rule_a_every_prefix_exists`. Plan
  §2.4's first measured bug: an id of `pp1_agr1_agr2_agr1` whose
  `pp1_agr1_agr2` does not exist produced a breadcrumb silently missing its
  middle ancestor.
* **#7 no duplication (Rule B)** — `test_rule_b_no_text_duplication`. Plan
  §2.4's second: `descendant::p|descendant::li` double-counts nested list text.

The corpus is 15 documents standing in for 300+ unseen ones, so every test that
can run over all 15 does, parametrised by sample stem rather than asserting
against a hand-picked pair.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.ingest import Inline, StyledDoc, read_docx
from lexml_nonstat.model import (
    PARA_KINDS,
    SECTION_KINDS,
    DocumentModel,
    ListItem,
    ListNode,
    build_model,
)
from lexml_nonstat.render import (
    AUXILIARY_NOMES,
    RenderedDocument,
    local_name,
    missing_prefixes,
    render_generico,
    render_generico_from_docx,
    render_list,
    words,
)
from lexml_nonstat.validate import validate

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

LEX = "{http://www.lexml.gov.br/1.0}"

#: The one sample with an annex — plan §2.9's only corpus exercise.
ANNEX_SAMPLE = "port_mf_277_20180607"
#: The one sample whose DOCX carries Word list numbering.
LIST_SAMPLE = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"
#: Samples with a table. `REsp_1306393`'s sits inside the *front matter* hull,
#: which is why `render/common.py` renders regions rather than named parts.
TABLE_SAMPLES = ("par_cosit_26_20000629", "sumula_stj_125", "REsp_1306393")
#: The sample with 21 quoted articles — the corpus's quotation guard exercise.
KIND_SAMPLE = "parecer_93_2018_decor_cgu_agu"

# Every test that picks a sample by name is only as good as the name still
# existing, so collection fails loudly on a rename rather than silently
# skipping the case it was written for.
assert len(SAMPLES) == 15, SAMPLES
assert {ANNEX_SAMPLE, LIST_SAMPLE, KIND_SAMPLE, *TABLE_SAMPLES} <= set(SAMPLES)

#: Rendering all 15 takes about a second; doing it once per test would not.
_CACHE: dict[str, tuple[DocumentModel, RenderedDocument]] = {}


def rendered(name: str) -> tuple[DocumentModel, RenderedDocument]:
    """The model and the bundle for one sample, built once per session."""
    if name not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        model = build_model(read_docx(path), filename=path.name)
        _CACHE[name] = (model, render_generico(model))
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


def agrupamentos(document: etree._Element) -> list[etree._Element]:
    return list(document.iter(f"{LEX}Agrupamento"))


def bloco(element: etree._Element, nome: str) -> str | None:
    """A direct `Bloco` child's text, or `None` when the element has none."""
    for child in element:
        if local_name(child.tag) == "Bloco" and child.get("nome") == nome:
            return norm("".join(child.itertext()))
    return None


def norm(text: str | None) -> str | None:
    """Collapse whitespace; `None` and `""` both become `None`.

    Pretty-printing and the source's own spacing are not part of what a test
    about *structure* should be sensitive to.
    """
    if text is None:
        return None
    collapsed = " ".join(text.split())
    return collapsed or None


def sections(document: etree._Element) -> list[etree._Element]:
    """Section `Agrupamento`s only.

    A section is exactly an `Agrupamento` carrying `Bloco nome="nivel"`. The
    front and back region containers, the body preamble (`nome="texto"`) and an
    annex's title carry no `nivel` and are not sections — they are
    `AUXILIARY_NOMES`, and counting them as sections would make every depth and
    reversibility assertion below wrong.
    """
    return [a for a in agrupamentos(document) if bloco(a, "nivel") is not None]


def id_depth(ident: str, root: str) -> int:
    """How many `_agr` steps `ident` sits below `root`."""
    assert ident.startswith(f"{root}_"), f"{ident!r} is not below {root!r}"
    return len(ident[len(root) + 1 :].split("_"))


def nesting_depth(element: etree._Element, tags: tuple[str, ...]) -> int:
    """The deepest nesting of `tags` within `element`, 0 when absent."""

    def walk(node: etree._Element, depth: int) -> int:
        if local_name(node.tag) in tags:
            depth += 1
        return max([depth] + [walk(child, depth) for child in node])

    return walk(element, 0)


def model_list_depth(node: ListNode, depth: int = 1) -> int:
    """The deepest `ListNode` nesting inside `node`."""
    best = depth
    for item in node.items:
        for child in item.children:
            if isinstance(child, ListNode):
                best = max(best, model_list_depth(child, depth + 1))
    return best


def content_nodes(tree) -> list:
    """Every content node of a `HierarchyTree` — preamble and section bodies."""
    out = list(tree.preamble)
    for section in tree.walk():
        out.extend(section.body)
    return out


# --------------------------------------------------------------------------
# Invariant #1 — validity (exit criteria E1, E2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_all_15_validate_on_both_schemas(name):
    """Every emitted document validates on both shipped schemas.

    The cycle's exit criterion (E1/E2). "Every document" is the whole bundle:
    an annex is a *sibling* `LexML` document under plan §2.9, so validating
    only `bundle.primary` would leave `port_mf_277`'s annex — 65 sections and
    the only `Anexo` in the corpus — entirely unchecked.

    The failure message carries `report.summary()`, which names the schema and
    quotes the XSD's own error, because "invalid" on its own is not a finding.
    """
    b = bundle(name)
    for position, document in enumerate(b.documents):
        report = validate(document, "both")
        where = "primary" if position == 0 else f"annex {position}"
        assert report.ok, f"{name} ({where}) is not valid:\n{report.summary()}"


# --------------------------------------------------------------------------
# Invariant #5 — id uniqueness
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_ids_unique_document_wide(name):
    """No `id` is issued twice, in a document or across the bundle.

    `xsd:ID` makes a duplicate invalid, so the schema is a second net — but it
    only fires once the document has already been written, and it cannot see
    across the primary/annex split at all. `IdAllocator` refusing a duplicate is
    the first net; this is the proof that it was actually consulted for every id
    that reached the XML.
    """
    b = bundle(name)

    for position, document in enumerate(b.documents):
        counts = Counter(
            value
            for node in document.iter()
            if (value := node.get("id")) is not None
        )
        repeated = {k: v for k, v in counts.items() if v > 1}
        where = "primary" if position == 0 else f"annex {position}"
        assert not repeated, f"{name} ({where}) repeats ids: {repeated}"

    bundle_counts = Counter(b.ids)
    repeated = {k: v for k, v in bundle_counts.items() if v > 1}
    assert not repeated, f"{name} repeats ids across the bundle: {repeated}"


# --------------------------------------------------------------------------
# Invariant #6 — Rule A
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_rule_a_every_prefix_exists(name):
    """Every proper prefix of an `Agrupamento` id exists as an element.

    Plan §2.4's **Rule A**, and the regression for the breadcrumb-gap bug the
    segmentation experiment surfaced: `pp1_agr1_agr2_agr1` with no
    `pp1_agr1_agr2` yields a breadcrumb missing its middle ancestor, silently.

    `IdAllocator` makes this true by construction — a child id is only composed
    from a parent already issued — so the point of asserting it here is that
    *the elements were actually emitted*, not merely that the ids were legal.
    The `PartePrincipal` id joins the set because it is the root of every path
    and is not itself an `Agrupamento`.
    """
    for position, document in enumerate(bundle(name).documents):
        pp = parte_principal(document)
        if pp is None:
            continue
        root = pp.get("id")
        ids = [root] + [a.get("id") for a in agrupamentos(document)]
        where = "primary" if position == 0 else f"annex {position}"
        gaps = missing_prefixes(ids, root=root)
        assert gaps == (), f"{name} ({where}) has Rule A gaps: {gaps}"


# --------------------------------------------------------------------------
# Invariant #7 — Rule B
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_rule_b_no_text_duplication(name):
    """No source word is emitted more often than the source contains it.

    Plan §2.4's **Rule B**. The failure mode it guards is specific: a nested
    list read with `descendant::p|descendant::li` yields the parent item's text
    once for the parent and again inside every ancestor's string value
    (`benssubitem subitem`). It is a *duplication* test, so it asserts one
    direction only — the loss direction is
    `tests/regression/test_conservation_generico.py`'s job, and keeping the two
    apart means a failure here names the right bug.
    """
    styled = rendered(name)[0].styled
    source = Counter(words(source_texts(styled)))
    emitted = Counter(words(bundle(name).texts))

    duplicated = emitted - source
    sample = list(duplicated.items())[:10]
    assert not duplicated, (
        f"{name} emits {sum(duplicated.values())} word(s) more often than the "
        f"source has them (first {len(sample)}): {sample}"
    )


def source_texts(doc: StyledDoc) -> list[str]:
    """Every piece of text the reader saw: paragraphs and table cells."""
    from lexml_nonstat.ingest import StyledPara, StyledTable

    out: list[str] = []
    for block in doc.blocks:
        if isinstance(block, StyledPara):
            if block.text.strip():
                out.append(block.text)
        elif isinstance(block, StyledTable):
            for row in block.rows:
                for cell in row.cells:
                    for para in cell.paras:
                        if para.text.strip():
                            out.append(para.text)
    return out


# --------------------------------------------------------------------------
# §5.1's three redundant depth channels
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_id_path_encodes_depth(name):
    """The `id` path and `Bloco nome="nivel"` say the same thing.

    Plan §5.1 makes depth recoverable three redundant ways — the `id` path, the
    `nivel` block and `@nome`. Redundancy is only useful while the channels
    agree; the moment they diverge a consumer that trusted one of them is
    reading a different document from a consumer that trusted the other.

    Only sections take part. Region `Agrupamento`s (`epigrafe`, `assinatura`,
    the `nota`/`preliminar` residue runs), the body preamble (`nome="texto"`)
    and an annex's `tituloAnexo` carry no `nivel` and sit flat under the
    `PartePrincipal`, so their ids encode no depth to check.
    """
    for position, document in enumerate(bundle(name).documents):
        pp = parte_principal(document)
        if pp is None:
            continue
        root = pp.get("id")
        where = "primary" if position == 0 else f"annex {position}"
        for section in sections(document):
            ident = section.get("id")
            level = int(bloco(section, "nivel"))
            assert id_depth(ident, root) == level, (
                f"{name} ({where}): id {ident!r} is "
                f"{id_depth(ident, root)} step(s) below {root!r} but declares "
                f'nivel {level}'
            )


# --------------------------------------------------------------------------
# Invariant #3 — reversibility
# --------------------------------------------------------------------------


def tree_from_xml(document: etree._Element) -> tuple:
    """Rebuild the section tree from the XML **alone**.

    This function may not look at the model, and does not: it takes an element
    and nothing else. It is the consumer plan §2.4 proved out in XSLT, written
    in Python — attach each section to the section whose id is its longest
    proper prefix, and whatever has no such ancestor is a root.

    Returns nested `(label, heading, level, kind, children)` tuples.
    """
    found: list[tuple[str, list]] = []
    node: dict[str, tuple] = {}
    for element in document.iter(f"{LEX}Agrupamento"):
        level = bloco(element, "nivel")
        if level is None:
            continue
        ident = element.get("id")
        children: list = []
        node[ident] = (
            bloco(element, "rotulo"),
            bloco(element, "nomeAgrupador"),
            int(level),
            element.get("nome"),
            children,
        )
        found.append((ident, children))

    roots: list[tuple] = []
    for ident, _ in found:
        ancestors = [
            other
            for other in node
            if other != ident and ident.startswith(f"{other}_")
        ]
        if ancestors:
            node[max(ancestors, key=len)][4].append(node[ident])
        else:
            roots.append(node[ident])
    return tuple(roots)


def tree_from_model(sections_) -> tuple:
    """The same shape, walked from `Section.children` — the oracle."""
    return tuple(
        (
            norm(s.label),
            norm(s.heading),
            s.level,
            s.kind,
            list(tree_from_model(s.children)),
        )
        for s in sections_
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_tree_reconstructable_from_xml_alone(name):
    """Invariant #3, and the load-bearing test of this module.

    `Agrupamento` cannot contain an `Agrupamento` on either shipped schema
    (plan §2.1, pinned in `tests/conftest.py`'s `nested_agrupamento`), so Cycle
    5 flattens the tree into siblings and carries depth in the `id` path. That
    is only an honest representation if the tree comes back — otherwise the
    emitter has quietly published a document whose structure the parser knew
    and the artifact does not.

    So: serialise, throw the model away, rebuild by longest-proper-prefix, and
    require the result to equal the tree walked from `HierarchyDoc`, label,
    heading, level and kind included. The body tree answers for the primary and
    `annex.tree` for each annex — the split is plan §2.9's, and a section that
    landed in the wrong document would fail here.
    """
    model, b = rendered(name)

    got = tree_from_xml(reparse(b.primary))
    expected = tree_from_model(model.body.sections)
    assert got == expected, f"{name}: primary tree not reconstructable"

    assert len(b.annexes) == len(model.annexes)
    for position, annex in enumerate(model.annexes):
        got = tree_from_xml(reparse(b.annexes[position]))
        expected = tree_from_model(annex.tree.sections)
        assert got == expected, (
            f"{name}: annex {position + 1} ({annex.fragment}) tree not "
            "reconstructable"
        )


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_nome_is_a_ratified_section_kind(name):
    """`@nome` comes from a ratified vocabulary, never from free text.

    Spec decision D-7 makes `Agrupamento/@nome` the `Section.kind` verbatim.
    `nome` is a free-form `xsd:string`, so the schema will accept anything — the
    vocabulary is entirely ours to keep, and a consumer grouping by `@nome` is
    the party that pays when it drifts.

    Two vocabularies, split by the same rule as everywhere in this module: a
    section (it has a `nivel`) draws from `SECTION_KINDS`, and everything else
    is a region, preamble or annex title and draws from `AUXILIARY_NOMES`.
    """
    for document in bundle(name).documents:
        for element in agrupamentos(document):
            nome = element.get("nome")
            if bloco(element, "nivel") is not None:
                assert nome in SECTION_KINDS, (
                    f"{name}: section {element.get('id')!r} has unratified "
                    f"nome {nome!r}"
                )
            else:
                assert nome in AUXILIARY_NOMES, (
                    f"{name}: auxiliary {element.get('id')!r} has unknown "
                    f"nome {nome!r}"
                )


# --------------------------------------------------------------------------
# Lists and tables — plan §2.2
# --------------------------------------------------------------------------


def test_nested_lists_survive():
    """Lists keep their real depth — the one place the open model does.

    Plan §2.2: `ol`/`ul` nest via `li → ol|ul`, so unlike `Agrupamento` a list
    needs no flattening and losing its depth would be a self-inflicted wound.

    Two exercises, because the corpus alone is not enough evidence. The sample
    pins that whatever depth the model inferred reached the XML; but
    `CARNE_LEAO`'s lists are all one level deep, so on its own it would pass
    against an emitter that flattened everything. The synthetic three-level
    `ListNode` is the one that would actually catch that, and it goes through
    the same `render_list` the emitter calls.
    """
    inner = ListNode(
        ordered=True, items=(ListItem(inlines=(Inline("terceiro nível"),)),)
    )
    middle = ListNode(
        ordered=True,
        items=(ListItem(inlines=(Inline("segundo nível"),), children=(inner,)),),
    )
    outer = ListNode(
        ordered=True,
        items=(ListItem(inlines=(Inline("primeiro nível"),), children=(middle,)),),
    )
    assert model_list_depth(outer) == 3

    element = render_list(outer)
    assert element is not None
    assert nesting_depth(element, ("ol", "ul")) == 3, (
        "a three-level ListNode must render as three nested ol elements, "
        f"got {nesting_depth(element, ('ol', 'ul'))}"
    )

    model, b = rendered(LIST_SAMPLE)
    lists = [n for n in content_nodes(model.body) if isinstance(n, ListNode)]
    assert lists, f"{LIST_SAMPLE} is expected to carry Word lists"
    expected = max(model_list_depth(node) for node in lists)
    got = max(
        nesting_depth(document, ("ol", "ul")) for document in b.documents
    )
    assert got == expected, (
        f"{LIST_SAMPLE}: model list depth {expected}, XML list depth {got}"
    )


@pytest.mark.parametrize("name", TABLE_SAMPLES)
def test_tables_emit_inline_cells(name):
    """`<td>` takes inline content only, and `<table>` requires an `id`.

    Both are measured schema facts, not style: `<td><p>` is rejected by both
    shipped schemas, and `table` carries `idreq` so a table without an `id` is
    invalid. Plan §2.9 fixes the id form, `pp1_tabN` in the primary and
    `anexoN_tabM` in an annex, which is what makes a table citable across the
    annex split.

    `REsp_1306393` is in this list on purpose: its table sits inside the
    *front-matter hull*, not the body, so it is rendered by
    `render/common.py`'s region path rather than by `render_node`. Without it
    the two table paths would not both be covered.
    """
    import re

    b = bundle(name)
    tables = [t for d in b.documents for t in d.iter(f"{LEX}table")]
    assert tables, f"{name} is expected to carry at least one table"

    for table in tables:
        ident = table.get("id")
        assert ident is not None, f"{name}: a table has no id"
        assert re.fullmatch(r"(pp1|anexo\d+)_tab\d+", ident), (
            f"{name}: table id {ident!r} does not follow the §2.9 convention"
        )
        for cell in list(table.iter(f"{LEX}td")) + list(table.iter(f"{LEX}th")):
            offenders = list(cell.iter(f"{LEX}p"))
            assert not offenders, (
                f"{name}: table {ident} has {len(offenders)} <p> inside a cell; "
                "both schemas reject <td><p>"
            )


# --------------------------------------------------------------------------
# Annexes — plan §2.9, reconciliation answer Q3
# --------------------------------------------------------------------------


def test_anexos_pointer_and_sibling_document():
    """An annex is a sibling document reached by URN, never a subtree.

    Reconciliation answer Q3 and plan §2.9, matching the reference parser's own
    `lei_5070_19660707.anexo1.xml`. Three things have to line up or the pointer
    dangles: the primary's `ReferenciaAnexo/@AlvoURN`, the annex's own
    `Identificacao/@URN`, and the fragment Cycle 2's URN builder produced.
    """
    model, b = rendered(ANNEX_SAMPLE)
    assert len(model.annexes) == 1
    assert len(b.annexes) == 1

    expected_urn = model.metadata.urn_with_fragment(model.annexes[0].fragment)
    assert expected_urn.endswith("!anexo1"), expected_urn

    referencias = list(b.primary.iter(f"{LEX}ReferenciaAnexo"))
    assert len(referencias) == 1
    assert referencias[0].get("AlvoURN") == expected_urn

    anexos = list(b.primary.iter(f"{LEX}Anexos"))
    assert len(anexos) == 1
    assert anexos[0].getparent().tag == f"{LEX}DocumentoGenerico"

    annex = b.annexes[0]
    assert local_name(annex.tag) == "LexML"
    assert [local_name(c.tag) for c in annex] == ["Metadado", "Anexo"]
    identificacao = list(annex.iter(f"{LEX}Identificacao"))
    assert [i.get("URN") for i in identificacao] == [expected_urn]

    pp = parte_principal(annex)
    assert pp is not None and pp.get("id") == "anexo1_pp"

    # The primary must not carry the annex's content in any form.
    assert not list(b.primary.iter(f"{LEX}Anexo"))


def test_annex_title_is_conserved():
    """`ANEXO ÚNICO` survives, exactly once, in the annex document.

    Spec decision D-5. Cycle 4 deliberately excludes the annex's marker
    paragraph from its tree — `build_tree(span_blocks(annex.span)[1:])`, because
    leaving it in would make the annex the first section of itself — so the
    emitter is the *only* place that text can be conserved, and dropping it
    would be a silent one-block conservation hole.
    """
    model, b = rendered(ANNEX_SAMPLE)
    label = model.annexes[0].label
    assert label, "the annex is expected to carry a label"

    occurrences = [t for t in b.texts if t == label]
    assert len(occurrences) == 1, (
        f"{ANNEX_SAMPLE}: annex label {label!r} appears "
        f"{len(occurrences)} time(s) in the bundle, expected exactly 1"
    )

    from lexml_nonstat.render import leaf_texts

    assert label not in leaf_texts(b.primary)
    assert label in leaf_texts(b.annexes[0])

    titles = [
        a
        for a in agrupamentos(b.annexes[0])
        if a.get("nome") == "tituloAnexo"
    ]
    assert len(titles) == 1
    assert titles[0].get("id") == "anexo1_pp_agr1"


@pytest.mark.parametrize("name", [s for s in SAMPLES if s != ANNEX_SAMPLE])
def test_no_annexes_no_anexos_element(name):
    """A document with no annex emits no `Anexos` and no annex document.

    `Anexos` is optional in `DocumentoGenerico`; an empty one would be either
    invalid or a dangling promise. The 14 samples without an annex are the
    evidence that the pointer is emitted *because* there is an annex, not
    unconditionally.
    """
    model, b = rendered(name)
    assert model.annexes == ()
    assert b.annexes == ()
    assert not list(b.primary.iter(f"{LEX}Anexos"))
    assert not list(b.primary.iter(f"{LEX}ReferenciaAnexo"))


# --------------------------------------------------------------------------
# Invariant #4 — determinism
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_rendering_is_deterministic(name):
    """Same input, byte-identical output — plan §9.2 invariant #4.

    Deliberately re-read from the DOCX rather than re-serialising one bundle: a
    dict iteration order or a `set` leaking into id allocation would survive the
    weaker check and fail this one. The suite pins `referee=None` (plan §9.3),
    so nothing here depends on a cache being warm.
    """
    path = SAMPLES_DIR / f"{name}.docx"
    first = render_generico_from_docx(path).to_xml_strings()
    second = render_generico_from_docx(path).to_xml_strings()
    assert first == second, f"{name} does not render deterministically"


# --------------------------------------------------------------------------
# Robustness and `Para.kind`
# --------------------------------------------------------------------------


def test_empty_document_does_not_crash():
    """A document with nothing in it renders, rather than raising.

    The corpus is 15 of 300+ documents; an unreadable or empty DOCX will happen,
    and an emitter that raises turns one bad input into a failed batch. The
    degenerate case also probes a real schema constraint: `blocksreq` is
    `minOccurs="1"`, so an *empty* `PartePrincipal` would be invalid on both
    schemas — the emitter must omit it rather than emit it hollow.
    """
    doc = StyledDoc(blocks=(), source="empty.docx")
    model = build_model(doc, filename="empty.docx")
    result = render_generico(model)

    assert isinstance(result, RenderedDocument)
    assert result.annexes == ()
    assert result.texts == ()

    pp = parte_principal(result.primary)
    assert pp is None or len(pp) > 0, (
        "an empty PartePrincipal is invalid on both schemas; omit it instead"
    )
    assert validate(result.primary, "both").ok, (
        validate(result.primary, "both").summary()
    )


def test_para_kind_survives_to_xml():
    """`Para.kind` reaches the artifact as `<p class="…">`.

    Reconciliation answer Q4. The quotation guard's verdict is the corpus's most
    consequential inference — it is what stops `parecer_93`'s 21 quoted articles
    being published as the parecer's own text — and an inference that stays
    in-process cannot be reviewed, cited or round-tripped. `class` carries no
    text, so conservation is untouched.

    `prose` is the default and is omitted, so `class` appearing at all is the
    signal; every value that does appear must come from the ratified
    `PARA_KINDS`, since `class` is free-form as far as the schema cares.
    """
    b = bundle(KIND_SAMPLE)
    classed = [
        p
        for d in b.documents
        for p in d.iter(f"{LEX}p")
        if p.get("class") is not None
    ]
    assert classed, f"{KIND_SAMPLE} is expected to carry quoted paragraphs"

    values = {p.get("class") for p in classed}
    assert values <= set(PARA_KINDS), f"unratified Para.kind emitted: {values}"
    assert "prose" not in values, "the default kind must not be written out"

    for name in SAMPLES:
        for document in bundle(name).documents:
            seen = {
                p.get("class")
                for p in document.iter(f"{LEX}p")
                if p.get("class") is not None
            }
            assert seen <= set(PARA_KINDS), f"{name}: {seen - set(PARA_KINDS)}"
