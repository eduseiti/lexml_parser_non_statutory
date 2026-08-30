"""Cross-emitter equivalence — plan §9.2, invariant #11.

**The same `DocumentModel`, written two ways, says the same thing.** The flat
`generico` emitter (Cycle 5) flattens the section tree into `Agrupamento`
siblings and carries depth out of band; the nested `generico-aninhado` emitter
(Cycle 5b) writes the tree *as* a tree of `AgrupamentoHierarquico`. Amendment
A-R.3's whole case for shipping a second emitter is that the choice is a
serialisation choice and nothing more — a consumer gets the same content and
addresses the same segments either way. This module is that claim in executable
form; without it "equivalent" is a design intention rather than a property.

What equivalence does and does not mean here
--------------------------------------------

It means **text** and **segment addressing**. It does not mean identical bytes,
identical element names, or identical `id` strings — the two emitters
deliberately differ on all three, and a test that pretended otherwise would
have to be either false or vacuous. Spec decision **D-2** fixes the difference:
a body section is `Agrupamento` with an `agr` id token flat, and
`AgrupamentoHierarquico` with an `agh` token (plus a `txt` prose leaf) nested.

So the tests split three ways, and each is honest about which claim it carries:

* **T-17** compares the extracted text as a **multiset**. A multiset rather
  than a set, because deduplication would hide exactly the failure mode
  Constraint 1's reordering makes plausible — a section's prose emitted twice,
  or a subsection's text emitted under both its parent and itself.
* **T-18** compares **segment URNs of body sections** — after normalising away
  the two documented, purely-notational differences (§ "The T-18
  normalisation" below). This is where the real content of invariant #11 lives.
* **T-21** pins the *rest* of the id difference: front and back matter region
  ids are byte-for-byte identical, because both emitters call the very same
  `front_region()` / `back_region()` (amendment A-5.1) on the very same model.
  Anything outside that identical core is enumerated, not waved at.

T-19 and T-20 are not comparisons at all: T-19 re-runs invariant #2 against the
nested bundle (the nested twin of `test_conservation_generico`, not its
replacement), and T-20 proves the nested emitter's two structural markers stay
outside the text channel, which is what makes T-17 and T-19 measure content
rather than punctuation.

The T-18 normalisation — and why it is not a weakening
-------------------------------------------------------

A segment URN is `{document urn}!{id}`, and an `id` is a path: root, then one
ordinal per level. What a URN *denotes* is therefore "the nth child at each
level down from the root". Two notational facts stand between the emitters'
raw id strings and that denotation, and **both are measured here rather than
assumed** (`test_only_two_documented_id_notations_differ`):

1. **Token spelling.** `agr` flat vs `agh` nested, per D-2. Pure spelling: the
   token names an element type, not a position.
2. **Top-level ordinal origin.** This one is *not* in the spec and is the
   substantive finding of this module. The flat emitter numbers body sections
   in the same `agr` sequence as the root-level front-matter regions, so with
   three front regions the first body section is `pp1_agr4`. The nested emitter
   gives body sections their own `agh` sequence, so the same section is
   `pp1_agh1`. Both are "the first body section"; the flat id is the nested id
   plus a constant offset — the number of root-level `Agrupamento` children
   preceding the body. Measured across the corpus the shift is exact, on all 15
   samples and the annex, at every depth.

Normalising those two away leaves the **path shape** — depth, and sibling
ordinal within the body at each level — which is what a consumer resolving a
segment URN actually uses.

The offset can only be counted on the **nested** side, and that is itself part
of the finding. In flat output a top-level body section and a front-matter
region are structurally indistinguishable — both are `Agrupamento` children of
`PartePrincipal` carrying an all-`agr` id — so flat output alone does not say
where its front matter stops. The nested emitter separates the two by element
name, so its `Agrupamento` children *are* the regions. The count is therefore
taken from the nested regions and applied to the flat ordinals; it is not the
two sides being handed each other's answer, because the quantity measured (how
many regions there are) and the quantity checked (where each section sits) are
different, and `test_only_two_documented_id_notations_differ` re-derives the
relationship section by section rather than trusting the set comparison.

**The verdict this module records.** Under D-2 the plan's phrase "identical
segment URNs" cannot hold *literally*: the id strings differ, and by more than
a token rename. What holds — and what the plan's intent is — is that the two
emitters address the same segments in the same order at the same depths, and
that the front and back matter halves of the id space are literally identical.
That is asserted here at full strength, with the difference enumerated rather
than excused. A consumer that resolves `urn…!pp1_agr4` against flat output and
`urn…!pp1_agh1` against nested output reaches the same section; a consumer that
assumes one id string works against both output of both emitters does not, and
the offset above is the reason.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc, StyledPara, StyledTable, read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.referee.protocol import Verdict
from lexml_nonstat.render import (
    EMPTY_BLOCO,
    ORDER_BLOCO,
    RenderedDocument,
    leaf_texts,
    local_name,
    render_generico,
    render_generico_aninhado,
    words,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

LEX = "{http://www.lexml.gov.br/1.0}"

#: The one sample with an annex — 16 documents across the corpus, not 15.
ANNEX_SAMPLE = "port_mf_277_20180607"

assert len(SAMPLES) == 15, SAMPLES
assert ANNEX_SAMPLE in SAMPLES

#: D-2's two id tokens for a body section, flat and nested.
FLAT_SECTION_TOKEN = "agr"
NESTED_SECTION_TOKEN = "agh"

#: The nested emitter's prose leaf. It has no flat counterpart — flat prose sits
#: directly inside the section's own `Agrupamento` — so it is excluded from the
#: T-18 comparison and accounted for explicitly in T-21.
NESTED_LEAF_TOKEN = "txt"

_CACHE: dict[str, tuple[StyledDoc, RenderedDocument, RenderedDocument]] = {}


def both(name: str) -> tuple[StyledDoc, RenderedDocument, RenderedDocument]:
    """The source, its flat rendering and its nested rendering.

    Built once per session and — the point of this module — from **one**
    `DocumentModel`. Rendering each emitter from its own `build_model()` call
    would leave a model-level divergence able to hide inside an equivalence
    failure, and would test the model's determinism instead of the emitters'.
    """
    if name not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        doc = read_docx(path)
        model = build_model(doc, filename=path.name)
        _CACHE[name] = (doc, render_generico(model), render_generico_aninhado(model))
    return _CACHE[name]


# --------------------------------------------------------------------------
# Id paths
# --------------------------------------------------------------------------


def document_root(document) -> str:
    """The `PartePrincipal` id every path in this document hangs from.

    Read from the document rather than assumed, because the root is **not** one
    underscore-separated token: the primary's is `pp1` but an annex's is
    `anexo1_pp` (§2.9). Splitting an id on `_` and dropping the first field
    silently reads `anexo1_pp_agh1` as the two steps `pp`, `agh1`, which is not
    a path at all — and would quietly exclude the annex, the one document in
    the corpus where the two emitters have the most to disagree about.
    """
    for parte in document.iter(f"{LEX}PartePrincipal"):
        return parte.get("id") or ""
    return ""


def _id_steps(ident: str, root: str) -> tuple[str, ...]:
    """`ident`'s path steps below `root`: `anexo1_pp_agh1` → `("agh1",)`.

    Empty when `ident` is the root itself or does not descend from it.
    """
    if not root or not ident.startswith(f"{root}_"):
        return ()
    return tuple(ident[len(root) + 1 :].split("_"))


def _steps_of(token: str, ident: str, root: str) -> tuple[int, ...] | None:
    """The ordinals of `ident` when every step is `{token}{n}`, else `None`.

    `re.fullmatch` rather than `startswith`: `agrf1` — a back-matter region —
    begins with `agr` and is emphatically not a body section. Getting that
    wrong would silently pull the back matter into the body comparison, where
    it happens to be identical, and make T-18 pass for the wrong reason.
    """
    steps = _id_steps(ident, root)
    if not steps:
        return None
    out = []
    for step in steps:
        match = re.fullmatch(rf"{token}(\d+)", step)
        if match is None:
            return None
        out.append(int(match.group(1)))
    return tuple(out)


def region_ids(document) -> list[tuple[str, str]]:
    """The `(id, nome)` of every root-level `Agrupamento` child of `PartePrincipal`.

    In a **nested** document these are exactly the regions — front matter, the
    body preamble, back matter, an annex's `tituloAnexo` — because every body
    section is an `AgrupamentoHierarquico` instead. In a **flat** document the
    same list also holds the top-level body sections, which is precisely why the
    offset below can only be measured on the nested side.
    """
    out: list[tuple[str, str]] = []
    for parte in document.iter(f"{LEX}PartePrincipal"):
        for child in parte:
            if local_name(child.tag) == "Agrupamento":
                out.append((child.get("id") or "", child.get("nome") or ""))
    return out


def _root_region_count(nested_document) -> int:
    """How many root-level `agr` regions the flat emitter numbered before the body.

    **Measurable only on the nested document**, and that is a finding rather
    than a convenience. The flat emitter's body sections continue the very same
    root `agr` sequence the front-matter regions started (`Scope.adopt` advances
    the counter past them), so in flat output `pp1_agr4` is structurally
    indistinguishable from a region: both are `Agrupamento` children of
    `PartePrincipal` with an all-`agr` id. The nested emitter separates them by
    element name, so its `Agrupamento` children *are* the regions and its
    `AgrupamentoHierarquico` children *are* the body.

    Back matter's `agrf` ids never entered the `agr` sequence, so they are not
    counted — `_steps_of` uses `re.fullmatch` and rejects `agrf1`.

    This is not the two sides copying each other's answer: the count comes from
    the nested document's *region* list, and is applied to the flat document's
    *body* ordinals. A section that moved between the body and the front matter
    in one emitter and not the other would change one and not the other, and
    `test_only_two_documented_id_notations_differ` would fail.
    """
    root = document_root(nested_document)
    return sum(
        1
        for ident, _ in region_ids(nested_document)
        if _steps_of(FLAT_SECTION_TOKEN, ident, root) is not None
    )


def flat_body_paths(document, offset: int) -> set[tuple[int, ...]]:
    """Body-section path shapes in a flat document, top-level ordinals rebased.

    A flat body section is an `Agrupamento` whose id is all-`agr` steps and
    whose top-level ordinal is past the root-level regions. Subtracting
    `offset` puts its first body section at 1, matching the nested emitter's
    origin; deeper ordinals are already per-parent and untouched.
    """
    root = document_root(document)
    paths: set[tuple[int, ...]] = set()
    for node in document.iter(f"{LEX}Agrupamento"):
        steps = _steps_of(FLAT_SECTION_TOKEN, node.get("id") or "", root)
        if steps is None or steps[0] <= offset:
            continue
        paths.add((steps[0] - offset,) + steps[1:])
    return paths


def nested_body_paths(document) -> set[tuple[int, ...]]:
    """Body-section path shapes in a nested document.

    Every `AgrupamentoHierarquico` is a body section by construction — the
    regions stay flat `Agrupamento` — and its ordinals already start at 1, so
    there is nothing to rebase.
    """
    root = document_root(document)
    paths: set[tuple[int, ...]] = set()
    for node in document.iter(f"{LEX}AgrupamentoHierarquico"):
        steps = _steps_of(NESTED_SECTION_TOKEN, node.get("id") or "", root)
        assert steps is not None, (
            f"AgrupamentoHierarquico id {node.get('id')!r} is not an all-`agh` "
            "path — D-2's token scheme has changed and T-18 no longer measures "
            "what its docstring claims"
        )
        paths.add(steps)
    return paths


def _document_urn(bundle: RenderedDocument, position: int, document) -> str:
    """The URN a segment in this bundle document is addressed under.

    An annex is a *sibling document* with its own URN (§2.9), so `!…1` in the
    primary and `!…1` in the annex are different segments even where the paths
    coincide. The primary's URN is on the bundle; an annex's is on its own
    `Identificacao`, which both emitters write from the same
    `urn_with_fragment`.
    """
    if not position:
        return bundle.urn
    for ident in document.iter(f"{LEX}Identificacao"):
        return ident.get("URN") or bundle.urn
    return bundle.urn


def flat_segment_urns(bundle: RenderedDocument, offsets: list[int]) -> set[str]:
    """Body-section segment URNs of a flat bundle, paths rebased by `offsets`."""
    out: set[str] = set()
    for position, document in enumerate(bundle.documents):
        urn = _document_urn(bundle, position, document)
        for path in flat_body_paths(document, offsets[position]):
            out.add(f"{urn}!" + "_".join(str(n) for n in path))
    return out


def nested_segment_urns(bundle: RenderedDocument) -> set[str]:
    """Body-section segment URNs of a nested bundle. No rebasing needed."""
    out: set[str] = set()
    for position, document in enumerate(bundle.documents):
        urn = _document_urn(bundle, position, document)
        for path in nested_body_paths(document):
            out.add(f"{urn}!" + "_".join(str(n) for n in path))
    return out


def offsets_of(nested: RenderedDocument) -> list[int]:
    """The per-document top-level ordinal offset, measured on the nested side."""
    return [_root_region_count(document) for document in nested.documents]


# --------------------------------------------------------------------------
# Source text, for conservation (T-19)
# --------------------------------------------------------------------------


def source_texts(doc: StyledDoc) -> list[str]:
    """Every piece of text Cycle 1's reader saw — paragraphs and table cells.

    Deliberately the same extraction `test_conservation_generico` uses, kept
    here rather than imported so that the nested conservation claim does not
    silently inherit a future change made for the flat one. A divergence
    between the two copies would be a test bug either way; a *shared* copy
    quietly changing both claims at once would be worse.
    """
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


def diff_message(name: str, source: Counter, emitted: Counter) -> str:
    """Both directions of the symmetric difference, capped so it stays readable."""
    lost = source - emitted
    extra = emitted - source
    return (
        f"{name}: {sum(lost.values())} word(s) lost, "
        f"{sum(extra.values())} emitted without a source.\n"
        f"  lost (first 10):  {list(lost.items())[:10]}\n"
        f"  extra (first 10): {list(extra.items())[:10]}"
    )


# --------------------------------------------------------------------------
# T-17 — text
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_text_identical_across_emitters(name):
    """The two emitters extract the **same multiset** of leaf texts.

    Invariant #11's first half, and the one a consumer feels immediately: a
    search index or an LLM corpus built from nested output must contain neither
    more nor less than one built from flat output.

    A multiset, not a set. Constraint 1 makes the nested emitter serialise a
    section's own prose *after* its subsections, and Constraint 2 makes it emit
    a filler where there is no prose at all — both are places a plausible bug
    writes a section's text twice, or writes a parent's text into each child.
    `set` equality is blind to every one of those; `Counter` is not.

    Compared over the whole bundle rather than per document, because the
    equivalence claim is about the content the model carries, and on
    `port_mf_277` part of that content is in a sibling annex document.
    """
    _, flat, nested = both(name)
    assert Counter(nested.texts) == Counter(flat.texts), (
        f"{name}: emitters disagree on text.\n"
        f"  only nested: {list((Counter(nested.texts) - Counter(flat.texts)).items())[:5]}\n"
        f"  only flat:   {list((Counter(flat.texts) - Counter(nested.texts)).items())[:5]}"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_text_order_diverges_exactly_where_constraint_1_says(name):
    """Reading order is **not** preserved — and that is the documented cost.

    The negative half of T-17, and the reason T-17 must be a multiset rather
    than a sequence. Constraint 1 forces a section's own prose to be serialised
    *after* its subsections, so document-order extraction of nested output is
    not source order wherever a section has both. On `sumula_stj_125` the two
    diverge from index 32: the flat emitter reads a section's `Relator:` and
    `Agravante:` lines before its subsections, the nested one after.

    This is risk **K-1**, accepted deliberately (R-3), not a defect — and it is
    exactly why every section carries `Bloco nome="ordem"`. Pinning it here
    does two things a silent acceptance would not: it stops someone "fixing"
    T-17 into a sequence comparison and finding it inexplicably red, and it
    makes the day the upstream refinement removes Constraint 1 visible, because
    the samples listed below would start agreeing.

    The claim is precise: order diverges **only** on documents with a section
    that has both children and own prose, and nowhere else.
    """
    doc, flat, nested = both(name)
    model = build_model(doc, filename=f"{name}.docx")

    def reordered(section) -> bool:
        return bool(section.children) and any(
            reordered(child) for child in section.children
        ) or (bool(section.children) and bool(section.body))

    trees = [model.body] + [annex.tree for annex in model.annexes]
    expect_divergence = any(
        reordered(section) for tree in trees for section in tree.sections
    )

    same_order = list(nested.texts) == list(flat.texts)
    assert same_order != expect_divergence, (
        f"{name}: sections with both subsections and own prose = "
        f"{expect_divergence}, but text order preserved = {same_order}. "
        "Constraint 1 reorders exactly those and nothing else."
    )


# --------------------------------------------------------------------------
# T-18 — segment URNs
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_segment_urns_identical_across_emitters(name):
    """Body sections denote the same segments under both emitters.

    Invariant #11's second half. See the module docstring for the full
    argument; in brief, a segment URN's *meaning* is a path of sibling
    ordinals, and the two emitters write that same path with two documented
    notational differences — D-2's `agr`/`agh` token, and a top-level ordinal
    origin (flat continues the root region sequence, nested restarts). Both are
    normalised away here, and **only** those two: the resulting comparison is
    over depth and per-level ordinal, which is exactly what a consumer
    resolving a URN traverses.

    The normalisation is asymmetric-safe. The flat side's offset is recovered
    from the flat document's own root-level regions and the nested side's from
    the nested document's; neither is derived from the other, so a genuine
    structural divergence — a section gained, lost, or reparented — cannot be
    absorbed by the rebasing.

    `test_only_two_documented_id_notations_differ` is this test's guard: it
    fails if a *third* difference appears, which would make this normalisation
    a weakening rather than a translation.
    """
    _, flat, nested = both(name)
    flat_urns = flat_segment_urns(flat, offsets_of(nested))
    nested_urns = nested_segment_urns(nested)

    assert nested_urns == flat_urns, (
        f"{name}: body segment URNs differ after normalisation.\n"
        f"  only nested: {sorted(nested_urns - flat_urns)[:5]}\n"
        f"  only flat:   {sorted(flat_urns - nested_urns)[:5]}"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_segment_urn_comparison_is_not_vacuous(name):
    """A sample with body sections actually contributes segment URNs.

    Six of the fifteen samples have no body sections at all — `ad_srf_22` and
    `adn_cosit_19` are nothing but front and back matter — so on those the
    comparison above is `set() == set()` and proves nothing. That is fine
    provided it is *known*: this test pins which samples carry the weight, so a
    regression that emptied the body of every document could not turn T-18
    green by making both sides vacuous.
    """
    _, flat, nested = both(name)
    model_sections = sum(
        1 for d in nested.documents for _ in d.iter(f"{LEX}AgrupamentoHierarquico")
    )
    urns = nested_segment_urns(nested)
    assert len(urns) == model_sections, (
        f"{name}: {model_sections} nested sections but {len(urns)} distinct "
        "segment URNs — two sections share an address"
    )
    if model_sections:
        assert flat_segment_urns(flat, offsets_of(nested)), (
            f"{name}: nested emitted {model_sections} body sections, flat emitted none"
        )


@pytest.mark.parametrize("name", SAMPLES)
def test_only_two_documented_id_notations_differ(name):
    """Nothing but the token and the top-level origin separates the id paths.

    The guard that keeps T-18's normalisation honest. It asserts the *exact*
    arithmetic relationship claimed in the module docstring — flat top-level
    ordinal == nested top-level ordinal + the number of root-level `agr`
    regions, with every deeper ordinal equal — as a sorted, positional
    comparison over the whole body. A section reparented one level up, an
    ordinal skipped, or a third notational drift would break this while T-18's
    set comparison might still absorb it.
    """
    _, flat, nested = both(name)
    for position, (flat_doc, nested_doc) in enumerate(
        zip(flat.documents, nested.documents)
    ):
        where = "primary" if position == 0 else f"annex {position}"
        offset = _root_region_count(nested_doc)
        flat_root = document_root(flat_doc)
        raw_flat = sorted(
            steps
            for node in flat_doc.iter(f"{LEX}Agrupamento")
            if (steps := _steps_of(FLAT_SECTION_TOKEN, node.get("id") or "", flat_root))
            is not None
            and steps[0] > offset
        )
        raw_nested = sorted(nested_body_paths(nested_doc))
        assert len(raw_flat) == len(raw_nested), (
            f"{name} ({where}): {len(raw_flat)} flat body sections vs "
            f"{len(raw_nested)} nested"
        )
        for f_steps, n_steps in zip(raw_flat, raw_nested):
            assert f_steps[0] - offset == n_steps[0] and f_steps[1:] == n_steps[1:], (
                f"{name} ({where}): flat {f_steps} and nested {n_steps} differ by "
                f"more than the documented offset {offset}"
            )


# --------------------------------------------------------------------------
# T-19 — conservation, nested
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_conservation_nested(name):
    """Invariant #2 on the nested bundle: every source word, exactly once.

    The nested twin of `test_conservation_generico`, not its replacement — the
    flat emitter's conservation is no evidence at all for the nested one, which
    reorders every section's children (Constraint 1), inserts a filler where a
    section has no prose (Constraint 2), and wraps every section's prose in an
    extra `Agrupamento nome="texto"` the flat shape does not have. Each of
    those is an opportunity to drop or repeat a block.

    The currency is a multiset of **words**, for the reason that module records:
    one source paragraph legitimately becomes two elements — a label and the
    prose that followed it on the same line — so comparing whole paragraphs
    would report a false loss on every labelled section in the corpus.
    Equality of multisets is simultaneously "nothing lost" and "nothing
    duplicated", which is the strongest form the invariant has.

    Measured over `PartePrincipal` only, inheriting the flat module's stated
    caveat: `Metadado/MetadadoProprietario/campo` *extracts* fields and so
    repeats source text verbatim by design. `leaf_texts` never descends into
    `Metadado`, and `RenderedDocument.texts` is `leaf_texts` over each
    document, so the exclusion is structural rather than something this test
    arranges.
    """
    doc, _, nested = both(name)
    source = Counter(words(source_texts(doc)))
    emitted = Counter(words(nested.texts))
    assert emitted == source, diff_message(name, source, emitted)


def test_conservation_nested_across_the_annex_split():
    """`port_mf_277`: nested primary ∪ nested annex == source, disjointly.

    Plan §9.2 says "including across `Norma` + `Anexo`", and §2.9 makes an
    annex a *sibling document*. That is the arrangement conservation breaks in
    most quietly: neither file is wrong alone, and a block that fell between
    them — or was defensively written into both — is invisible to a check that
    reads one file. Addition makes this a disjointness test as well as a
    completeness one: a word emitted in both documents would make the sum
    exceed the source.
    """
    doc, _, nested = both(ANNEX_SAMPLE)
    assert len(nested.annexes) == 1

    primary = Counter(words(leaf_texts(nested.primary)))
    annex = Counter(words(leaf_texts(nested.annexes[0])))
    source = Counter(words(source_texts(doc)))

    assert primary + annex == source, diff_message(
        ANNEX_SAMPLE, source, primary + annex
    )
    assert primary and annex, "both documents must carry text"

    annex_texts = leaf_texts(nested.annexes[0])
    assert "ANEXO ÚNICO" in annex_texts
    assert "ANEXO ÚNICO" not in leaf_texts(nested.primary)


# --------------------------------------------------------------------------
# T-20 — structural markers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_structural_markers_add_no_text(name):
    """`Bloco nome="ordem"` and `Bloco nome="vazio"` are invisible to extraction.

    Both markers exist to satisfy the schema, not to say anything: `ordem`
    carries the document-order index Constraint 1 destroys (spec decision D-5),
    and `vazio` is the non-`AH` child Constraint 2 demands of a section that has
    no prose of its own. Neither value was ever in the source document.

    That makes their invisibility load-bearing twice over. If `ordem`'s digits
    reached `leaf_texts`, T-17's multiset would gain a word per section and
    T-19's conservation would report an unsourced word per section — but worse,
    both failures would look like *content* bugs. And any segmentation built on
    Rule B extraction would find "0", "1", "2" interleaved through the prose.

    Three assertions, weakest to strongest:

    1. the markers are actually **there** — a test that the emitter's filler is
       invisible proves nothing if the emitter stopped emitting filler;
    2. no marker's value appears among the extracted texts;
    3. the marker values are of the shape claimed — `ordem` a non-negative
       integer, `vazio` genuinely empty — so a future marker that smuggled prose
       into either name would be caught here rather than diluted into T-19.
    """
    _, _, nested = both(name)

    orders: list[str] = []
    empties = 0
    for document in nested.documents:
        for node in document.iter(f"{LEX}Bloco"):
            nome = node.get("nome")
            if nome == ORDER_BLOCO:
                orders.append(node.text or "")
            elif nome == EMPTY_BLOCO:
                empties += 1
                assert not (node.text or "").strip(), (
                    f"{name}: Bloco nome={EMPTY_BLOCO!r} carries text "
                    f"{node.text!r} — the Constraint 2 filler is not empty"
                )
                assert len(node) == 0, (
                    f"{name}: Bloco nome={EMPTY_BLOCO!r} has children"
                )

    sections = sum(
        1 for d in nested.documents for _ in d.iter(f"{LEX}AgrupamentoHierarquico")
    )
    assert len(orders) == sections, (
        f"{name}: {sections} sections but {len(orders)} {ORDER_BLOCO!r} markers — "
        "R-3 says every section carries one"
    )

    for value in orders:
        assert value.isdigit(), (
            f"{name}: {ORDER_BLOCO!r} value {value!r} is not a document-order index"
        )

    # A bare "is '2' among the texts?" would be worthless: "2" is a perfectly
    # ordinary word in these documents, so a coincidental match would fail a
    # correct emitter and a real leak would hide behind one. The measurement
    # that *is* sound is a **before/after**: re-label the markers so that
    # `leaf_texts` is willing to read them, and see how much text appears that
    # did not before. If the markers are invisible, the difference is exactly
    # their values; if one had been leaking, it would already be in the lean
    # extraction and the difference would fall short.
    for position, document in enumerate(nested.documents):
        where = "primary" if position == 0 else f"annex {position}"
        lean = Counter(words(leaf_texts(document)))
        relabelled = copy.deepcopy(document)
        exposed: list[str] = []
        for node in relabelled.iter(f"{LEX}Bloco"):
            if node.get("nome") in (ORDER_BLOCO, EMPTY_BLOCO):
                exposed.append(node.text or "")
                node.set("nome", "rotulo")  # a name `leaf_texts` does read
        full = Counter(words(leaf_texts(relabelled)))

        assert full - lean == Counter(words(exposed)), (
            f"{name} ({where}): making the structural markers readable adds "
            f"{list((full - lean).items())[:5]}, but the markers hold "
            f"{Counter(words(exposed)).most_common(5)} — the two disagree, so a "
            "marker's value is already reaching the text channel"
        )
        assert lean - full == Counter(), (
            f"{name} ({where}): re-labelling removed text, which cannot happen"
        )

    # Constraint 2's filler must appear exactly where a section has no prose
    # leaf, and nowhere else — the two counts partition the sections.
    leaves = sum(
        1
        for d in nested.documents
        for node in d.iter(f"{LEX}Agrupamento")
        if _steps_of_leaf(node.get("id") or "", document_root(d))
    )
    assert leaves + empties == sections, (
        f"{name}: {sections} sections carry {leaves} prose leaves and {empties} "
        f"{EMPTY_BLOCO!r} fillers — Constraint 2 says every section has exactly one"
    )


def _steps_of_leaf(ident: str, root: str) -> bool:
    """Whether `ident` is a nested prose leaf: an all-`agh` path ending in `txt`."""
    steps = _id_steps(ident, root)
    if not steps or not re.fullmatch(rf"{NESTED_LEAF_TOKEN}\d+", steps[-1]):
        return False
    return all(
        re.fullmatch(rf"{NESTED_SECTION_TOKEN}\d+", step) for step in steps[:-1]
    )


# --------------------------------------------------------------------------
# T-21 — where the id sets differ, and why
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_id_sets_differ_only_where_documented(name):
    """The two emitters' id sets: identical outside the body, disjoint inside.

    Written to be *honest* rather than optimistic. Invariant #11 is sometimes
    read as "the same ids"; that is false under D-2 and pretending otherwise
    would either fail or be quietly softened until it meant nothing. So this
    test states the true shape of the difference, in three parts, and would go
    red if any of them drifted:

    1. **The shared core is literally identical.** Every id that is *not* a
       body section or a nested prose leaf — the `PartePrincipal` root, front
       matter `agr`, back matter `agrf`, the body preamble, tables, an annex's
       `tituloAnexo` — is byte-for-byte the same in both. It has to be: both
       emitters call the same `front_region()` / `back_region()` (A-5.1) on the
       same model, and neither renumbers what the other issued.

    2. **The body ids are disjoint, by construction.** No flat `agr` body id
       appears in the nested set and no `agh`/`txt` id in the flat set. A
       *partial* overlap would be the alarming outcome — it would mean one
       scheme had drifted into the other's namespace and a URN could resolve
       to the wrong segment depending on which emitter ran.

    3. **The counts line up.** The nested emitter has exactly one extra id per
       section that owns prose (its `txt` leaf) and no other surplus, so the
       difference in id count is fully explained rather than merely tolerated.
    """
    _, flat, nested = both(name)

    for position, (flat_doc, nested_doc) in enumerate(
        zip(flat.documents, nested.documents)
    ):
        where = "primary" if position == 0 else f"annex {position}"
        offset = _root_region_count(nested_doc)

        flat_ids = {node.get("id") for node in flat_doc.iter() if node.get("id")}
        nested_ids = {node.get("id") for node in nested_doc.iter() if node.get("id")}

        flat_root = document_root(flat_doc)
        nested_root = document_root(nested_doc)
        flat_body = {
            i
            for i in flat_ids
            if (steps := _steps_of(FLAT_SECTION_TOKEN, i, flat_root)) is not None
            and steps[0] > offset
        }
        nested_body = {
            i
            for i in nested_ids
            if _steps_of(NESTED_SECTION_TOKEN, i, nested_root) is not None
            or _steps_of_leaf(i, nested_root)
        }

        # 1. The shared core.
        assert flat_ids - flat_body == nested_ids - nested_body, (
            f"{name} ({where}): ids outside the body differ — front/back matter "
            "is supposed to be the same elements from the same shared functions.\n"
            f"  only flat:   {sorted((flat_ids - flat_body) - (nested_ids - nested_body))[:5]}\n"
            f"  only nested: {sorted((nested_ids - nested_body) - (flat_ids - flat_body))[:5]}"
        )

        # 2. Disjointness inside the body.
        assert not (flat_body & nested_ids), (
            f"{name} ({where}): flat body ids reappear in the nested document: "
            f"{sorted(flat_body & nested_ids)[:5]}"
        )
        assert not (nested_body & flat_ids), (
            f"{name} ({where}): nested body ids reappear in the flat document: "
            f"{sorted(nested_body & flat_ids)[:5]}"
        )

        # 3. The surplus is exactly the prose leaves.
        leaves = {i for i in nested_body if _steps_of_leaf(i, nested_root)}
        sections = nested_body - leaves
        assert len(sections) == len(flat_body), (
            f"{name} ({where}): {len(flat_body)} flat sections vs "
            f"{len(sections)} nested"
        )
        assert len(nested_ids) - len(flat_ids) == len(leaves), (
            f"{name} ({where}): nested has {len(nested_ids) - len(flat_ids)} more "
            f"ids than flat, but only {len(leaves)} prose leaves to account for it"
        )


@pytest.mark.parametrize("name", SAMPLES)
def test_front_and_back_region_ids_are_identical(name):
    """Front and back matter: same ids, same `nome`, same order, both emitters.

    Split out from the set comparison above because this is the part of
    invariant #11 that *does* hold literally, and it deserves to fail on its
    own terms. `front_region()` and `back_region()` (A-5.1) are called with the
    same arguments from both emitters; if their output ever diverged, the 40
    unclaimed blocks amendment A-5.1 was written to recover would be at risk in
    one emitter and not the other, and the set comparison's message would blame
    the body.
    """
    _, flat, nested = both(name)

    for position, (flat_doc, nested_doc) in enumerate(
        zip(flat.documents, nested.documents)
    ):
        where = "primary" if position == 0 else f"annex {position}"
        nested_regions = region_ids(nested_doc)
        flat_regions = region_ids(flat_doc)
        # The nested emitter's root-level `Agrupamento`s are *only* the regions;
        # the flat emitter's list also holds its top-level body sections. Every
        # nested region must appear in the flat list, at the same id and nome.
        flat_by_id = dict(flat_regions)
        for ident, nome in nested_regions:
            assert flat_by_id.get(ident) == nome, (
                f"{name} ({where}): region {ident!r} is {nome!r} nested but "
                f"{flat_by_id.get(ident)!r} flat"
            )
        # …and in the same relative order.
        order = [i for i, _ in flat_regions if i in dict(nested_regions)]
        assert order == [i for i, _ in nested_regions], (
            f"{name} ({where}): regions appear in a different order"
        )


# ---------------------------------------------------------------------------
# Nested quotations across the two emitters (amendment A-Q.6)
# ---------------------------------------------------------------------------
#
# A-Q.4 adds a level of nesting under `par_cosit_26`'s `pp1_agr17`, and the
# risk A-5b.4 already identified is that a new level introduces a *third* way
# the two emitters can drift. It cannot be checked by re-running the tests
# above, because the default model has no referee and therefore no citations —
# so these build the confirmed model explicitly.


class _ConfirmBoundaries:
    """Confirms every boundary candidate; abstains on everything else."""

    name = "confirm-boundaries"
    enabled = True
    last_cache_hit = False

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        return Verdict.abstain("not under test")

    def is_heading(self, para: str, ctx: str) -> Verdict:
        return Verdict.abstain("not under test")

    def section_kind(self, label: str, heading: str) -> Verdict:
        return Verdict.abstain("not under test")

    def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
        return Verdict("boundary", 0.9, "test double")


def _confirmed(name: str):
    """One sample rendered both ways from **one** model with citations nested."""
    path = SAMPLES_DIR / f"{name}.docx"
    doc = read_docx(path)
    model = build_model(doc, filename=path.name, referee=_ConfirmBoundaries())
    return model, render_generico(model), render_generico_aninhado(model)


@pytest.mark.parametrize("name", SAMPLES)
def test_text_multiset_survives_nesting(name):
    """T-8c.19. T-17's guarantee, re-asserted with citations in the tree.

    A `Counter`, not a `set` and not a sequence: Constraint 1 reorders, and
    only a multiset is blind to reordering while still catching a paragraph
    emitted twice or dropped.
    """
    _model, flat, nested = _confirmed(name)
    assert Counter(nested.texts) == Counter(flat.texts), (
        f"{name}: nesting a citation moved text between the emitters\n"
        f"  only nested: {list((Counter(nested.texts) - Counter(flat.texts)).items())[:5]}\n"
        f"  only flat:   {list((Counter(flat.texts) - Counter(nested.texts)).items())[:5]}"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_nesting_conserves_text_against_the_unnested_render(name):
    """The other half of A-Q.5, measured where it is actually visible.

    Compared on **characters**, not on the leaf multiset and not on words, and
    the granularity is the whole difficulty. Splitting a quotation moves a leaf
    *boundary*: the head paragraph

        Lei nº 7.713, de 1988 - "Art. 1º- Os rendimentos…

    becomes a `NomeAgrupador` carrying `Lei nº 7.713, de 1988` and a `<p>`
    carrying `- "Art. 1º- Os rendimentos…`, so one leaf legitimately becomes
    two and `1991,` legitimately becomes `1991` + `,`. Neither a leaf multiset
    nor a word multiset can tell that apart from real damage; the character
    multiset can, and it is what invariant #2 actually claims.

    Two real defects were caught here, both silent to every schema. The first
    implementation left the norm's name at the head of the paragraph *as well
    as* promoting it to the heading — invariant #2's duplication half. The
    second consumed the separator into the cut, losing two `-` and two commas —
    the loss half. Only reading the output found either.
    """
    plain = render_generico(
        build_model(read_docx(SAMPLES_DIR / f"{name}.docx"), filename=f"{name}.docx")
    )
    _model, split, _ = _confirmed(name)

    assert Counter(re.sub(r"\s+", "", "".join(split.texts))) == Counter(
        re.sub(r"\s+", "", "".join(plain.texts))
    ), f"{name}: splitting a quotation changed the document's text"


def test_par_cosit_26_emits_four_nested_citacao_agrupamentos():
    """T-8c.20's concrete half, on both emitters.

    §2.3's sanctioned hierarchy channel on the flat emitter — a deeper id path
    under `pp1_agr17` — and a real nested element with a real `NomeAgrupador`
    on the nested one, which is the shape §11.2's argument to the maintainers
    is asking for.
    """
    _model, flat, nested = _confirmed("par_cosit_26_20000629")

    flat_xml = flat.to_xml_string()
    assert flat_xml.count('nome="citacao"') == 4
    for ordinal in range(1, 5):
        assert f'id="pp1_agr17_agr{ordinal}"' in flat_xml

    nested_xml = nested.to_xml_string()
    assert nested_xml.count('nome="citacao"') == 4
    for norm in (
        "Lei nº 7.713, de 1988",
        "Lei 8.134, de 1990",
        "Lei 8.383, de 1991",
        "Lei 8.981, de 1995",
    ):
        assert f"<NomeAgrupador>{norm}</NomeAgrupador>" in nested_xml


@pytest.mark.parametrize("name", SAMPLES)
def test_segment_addresses_survive_nesting(name):
    """T-8c.20. Invariant #11, re-measured with a citation level in the tree.

    A-Q.6's real worry: A-5b.4 already documented that the two emitters differ
    in **two** ways — D-2's `agr`/`agh` token and a top-level ordinal origin —
    and a new level under `pp1_agr17` must not introduce a *third*. This reuses
    the same normalisation the unnested test uses, so a third difference shows
    up here as a failure rather than being absorbed.
    """
    _model, flat, nested = _confirmed(name)
    flat_urns = flat_segment_urns(flat, offsets_of(nested))
    nested_urns = nested_segment_urns(nested)

    assert nested_urns == flat_urns, (
        f"{name}: body segment URNs diverge once a citation nests.\n"
        f"  only nested: {sorted(nested_urns - flat_urns)[:5]}\n"
        f"  only flat:   {sorted(flat_urns - nested_urns)[:5]}"
    )
