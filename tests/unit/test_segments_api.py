"""The segmentation API — plan §6.1, Cycle 7's spec table T-1…T-17.

Cycle 7 turns the emitted XML into **citable units**. A segment is what a
retrieval consumer points at: one section, one dispositivo, or one front/back
matter region, carrying the address it is cited by and the ancestry it is read
in. This module is that contract in executable form.

Four producers, one answer — which is the whole design
-------------------------------------------------------

`segments()` has four backends and they reach their answers by genuinely
different routes:

* `segments_from_model` walks Cycle 4's `HierarchyDoc` and composes ids the way
  the chosen emitter *would*. It never builds or parses XML.
* `segments_from_flat_xml` reconstructs ancestry from the **id path** — §2.4's
  Rule A, `pp1_agr4_agr1`'s parent is `pp1_agr4` — and reads depth out of band
  from `Bloco nome="nivel"`.
* `segments_from_nested_xml` reads **no id at all** for structure: ancestry is
  `AgrupamentoHierarquico` containment and order is `Bloco nome="ordem"`.
* `segments_from_norma_xml` walks statutory elements by name, because amendment
  **A-6.1** gave dispositivo ids a schema-pattern-constrained grammar in which
  `art1_cpt` is *not* "the `cpt`-th child of `art1`".

That independence is what makes T-2 and T-3 evidence rather than tautology. If
the readers delegated to the model path, their agreement would prove only that
one function agrees with itself. This module's job is to keep them honest
separately; `tests/regression/test_three_way_oracle.py` compares all three at
once.

Two addresses, and why a test must never conflate them
--------------------------------------------------------

Amendment **A-5b.4** measured — it was not designed, it was found — that the
flat and nested emitters give the *same* section two different ids. The token
differs (`agr` vs `agh`) and so does the top-level ordinal, because the flat
emitter numbers body sections in the same `agr` sequence as the root-level
front regions. So `pn_cst_38`'s first body section is `pp1_agr4` flat and
`pp1_agh1` nested.

Amendment **A-7.2** splits the two claims that were tangled in plan §6.1's
"segment URNs identical across emitters":

* `Segment.urn` is **literal** — `{document urn}!{id}` of the artifact it came
  from. T-9 asserts it resolves there, T-7 that it is unique there, T-8 that it
  is stable. It is never compared across emitters, because that comparison is
  false and a test asserting it would have to be wrong or vacuous.
* `Segment.path` is **emitter-independent** — body-section ordinals, root
  first. T-2 and T-3 compare *this*.

The conservation currency is `own_words`, not `text`
------------------------------------------------------

T-6 is Rule B end to end: no word of the source appears in two segments, and
none goes missing. It counts `Segment.own_words`, which is label + heading +
text with an echoed `Caput` rótulo skipped (amendment **A-6.4**).

A check over `.text` alone would fail, and correctly so: `label` and `heading`
are *source text* the emitters write into the XML, held here in typed fields
rather than smeared back into the prose. Counting only `text` would report
every rótulo in the corpus as lost; counting `text` *and* re-including a
`Caput`'s echoed rótulo would report it twice, because plan §4.3 and the
reference parser both write it a second time though the source said it once.
`own_words` is the field that gets both right, and the equality it satisfies is
exact — `Counter(own_words) == Counter(words(bundle.texts))` — not a
containment or a tolerance.

The corpus is 15 documents standing in for 300+ unseen ones, so every test that
can run over all 15 does, parametrised by sample stem. The three tests that
cannot — T-11's reverse-serialised children, T-12's gapped id path, T-16's
empty document — are hand-built, because no sample exhibits the condition and
waiting for one to appear in the 300 is not a test strategy.

Two surviving mutations, recorded rather than hidden
------------------------------------------------------

A mutation sweep over `segments/api.py` (16 single-line changes, run against a
private copy of `src/`) left two survivors. Both were traced, and both are
**unreachable defence-in-depth rather than untested behaviour** — recorded here
so a later reader does not mistake either for a gap:

1. `_nested_node`'s `if tag == "Bloco" and child.get("nome") in _MARKER_BLOCOS:
   continue`. Deleting it changes nothing, because `render.common.leaf_texts`
   already admits only `Bloco/@nome in ("rotulo", "nomeAgrupador")`. The
   *reachable* form of that mutation — widening `_TEXT_BLOCOS` to admit `ordem`
   and `vazio` — is caught by T-17 on 10 of the 15 samples, so the property is
   tested even though this particular line is redundant.
2. `_flat_parent`'s `and candidate not in region_ids`. Deleting it changes
   nothing on this corpus, because a region's id (`pp1_agr3`) is never a
   *prefix* of a body section's (`pp1_agr4_agr1`) — the flat emitter's shared
   `agr` sequence makes them siblings, not ancestors (A-5b.4). The guard would
   matter only on a document where a region and a body section shared a path
   prefix, which the emitter cannot currently produce.
"""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import (
    LEXML_NS,
    local_name,
    render_generico,
    render_generico_aninhado,
    render_norma,
    words,
)
from lexml_nonstat.segments import (
    REGION_LEVEL,
    Segment,
    segments,
    segments_from_flat_xml,
    segments_from_nested_xml,
    segments_from_norma_xml,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

LEX = f"{{{LEXML_NS}}}"

#: The one `norma`-routed sample, and the one with an annex — the same
#: document, which is why it carries T-4 and T-14 both.
NORMA_SAMPLE = "port_mf_277_20180607"
#: The deepest sample: four levels of nesting, 35 body sections, a section that
#: has *both* own prose and children. T-15 needs that last property and only a
#: handful of segments in the corpus have it.
DEEP_SAMPLE = "pn_cst_38_19801031"

# A test that picks a sample by name is only as good as the name still
# existing, so collection fails loudly on a rename rather than silently
# skipping the case it was written for.
assert len(SAMPLES) == 15, SAMPLES
assert NORMA_SAMPLE in SAMPLES
assert DEEP_SAMPLE in SAMPLES

#: The three emitters, as `segments(model, emitter=…)` names them, paired with
#: the renderer that produces the artifact those ids resolve against.
EMITTERS = (
    ("generico", render_generico),
    ("generico-aninhado", render_generico_aninhado),
)

#: Every `Segment` field that is *not* an address. T-3 and T-10 compare exactly
#: this set, because `id`/`urn` are the two the emitters and the mutation are
#: allowed to differ on and everything else is the document's content.
CONTENT_FIELDS = (
    "kind",
    "level",
    "label",
    "echoed_label",
    "heading",
    "breadcrumb",
    "text",
    "path",
    "order",
    "descendant_texts",
)

#: Every element a segment urn is allowed to resolve to — T-9's whitelist.
#: Enumerated rather than left open so that a urn resolving to, say, a `p` or a
#: `Bloco` fails: an id that selects *something* is not the same claim as an id
#: that selects the citable unit the segment says it is.
ADDRESSABLE_TAGS = frozenset(
    {
        # generico, flat and nested
        "Agrupamento",
        "AgrupamentoHierarquico",
        # norma dispositivos — the second id grammar, A-6.1
        "Artigo",
        "Caput",
        "Paragrafo",
        "Inciso",
        # norma regions — A-6.2's ParteInicial / ParteFinal parts
        "Epigrafe",
        "Ementa",
        "Preambulo",
        "FormulaPromulgacao",
        "LocalDataFecho",
    }
)

#: The one sample with **no** front or back matter at all: an untitled excerpt
#: whose every block the segmenter reads as body. Named rather than skipped by
#: an `if not regions` guard, because that guard would also silently excuse a
#: real regression on the other fourteen.
NO_REGION_SAMPLE = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"
assert NO_REGION_SAMPLE in SAMPLES


_CACHE: dict[str, object] = {}


def model(name: str):
    """The `DocumentModel` for one sample, built once per session.

    `build_model` runs the whole pipeline — ingest, profile, metadata,
    segmentation, hierarchy, routing — and the corpus is 15 documents, so
    rebuilding it per test would dominate the suite's runtime. The cache is
    the idiom `tests/regression/test_cross_emitter.py` already uses.
    """
    key = f"model:{name}"
    if key not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        _CACHE[key] = build_model(read_docx(path), filename=path.name)
    return _CACHE[key]


def bundle(name: str, emitter: str):
    """One sample's rendering by `emitter`, cached.

    Rendered from the **same** `DocumentModel` every time, so a model-level
    difference can never hide inside a reader-vs-reader disagreement.
    """
    key = f"bundle:{emitter}:{name}"
    if key not in _CACHE:
        renderers = {
            "generico": render_generico,
            "generico-aninhado": render_generico_aninhado,
            "norma": render_norma,
        }
        _CACHE[key] = renderers[emitter](model(name))
    return _CACHE[key]


def content_of(segment: Segment) -> tuple:
    """A segment's content fields — everything but its literal address."""
    return tuple(getattr(segment, field) for field in CONTENT_FIELDS)


def document_urn(document: etree._Element) -> str:
    """The `Identificacao/@URN` a segment's `document` field must match."""
    ident = document.find(f".//{LEX}Identificacao")
    return (ident.get("URN") or "") if ident is not None else ""


# --------------------------------------------------------------------------
# Synthetic document builders — the three conditions the corpus cannot show
# --------------------------------------------------------------------------


def el(tag: str, **attrib: str) -> etree._Element:
    """One LexML-namespaced element. The nsmap keeps `tostring` readable."""
    element = etree.Element(f"{LEX}{tag}", nsmap={None: LEXML_NS})
    for key, value in attrib.items():
        element.set(key, value)
    return element


def synthetic_document(urn: str = "urn:lex:br:test:parecer:2020-01-01;1"):
    """An empty but well-formed `DocumentoGenerico`, and its `PartePrincipal`.

    Built by hand rather than by rendering a stub model: these tests are about
    what the *readers* do with markup, and a reader that is only ever fed its
    own emitter's output is untested against the malformed and the minimal —
    which is exactly what 300 unseen documents will eventually supply.
    """
    root = el("LexML")
    metadado = el("Metadado")
    metadado.append(el("Identificacao", URN=urn))
    root.append(metadado)
    generico = el("DocumentoGenerico")
    root.append(generico)
    parte = el("PartePrincipal", id="pp1")
    generico.append(parte)
    return root, parte


def bloco(nome: str, text: str) -> etree._Element:
    marker = el("Bloco", nome=nome)
    marker.text = text
    return marker


def para(text: str) -> etree._Element:
    element = el("p")
    element.text = text
    return element


# --------------------------------------------------------------------------
# T-1 — the primary path covers the model exactly
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_model_path_segments_every_section(name: str) -> None:
    """One body segment per `Section`, in `walk()` order — plan §6.1.

    "Every section" is the claim that makes segmentation *complete*: a
    consumer that walks the segments has seen the document, not a filtered
    view of it. Asserted as an equality of the ordered `(kind, label, heading,
    level)` sequence rather than as a count, because a count is satisfied by
    any permutation and by any substitution — segmenting the same section
    twice while dropping another would pass a count and lose a document.

    `HierarchyDoc.trees` is body-then-annexes, which is the order `segments()`
    emits documents in, so the two sequences line up without re-sorting. That
    they do is part of the claim: an annex is a separate document (§2.9) but
    it is not a separate *reading*.
    """
    doc = model(name)
    expected = [
        (section.kind, section.label, section.heading, section.level)
        for tree in doc.hierarchy.trees
        for section in tree.walk()
    ]
    body = [s for s in segments(doc) if not s.is_region]
    actual = [(s.kind, s.label, s.heading, s.level) for s in body]

    assert actual == expected, (
        f"{name}: the model path must emit exactly one segment per Section, in "
        f"walk() order; got {len(actual)} for {len(expected)} sections"
    )


# --------------------------------------------------------------------------
# T-2, T-3 — the readers rebuild what the model said
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_flat_xml_reconstructs_the_model_sections(name: str) -> None:
    """Flat XML segments to what the model segments to — §2.4 Rule A.

    This is reversibility (§9.2 invariant #3) stated as a comparison. The flat
    emitter cannot nest `Agrupamento` (§2.1), so it writes the tree as siblings
    and carries depth out of band; if the id path plus `Bloco nome="nivel"`
    does not rebuild the tree, the emitter is a lossy renderer rather than a
    parser and every citation into its output is approximate.

    `path` is compared, never `urn`. Within one emitter the two carry the same
    information, but `path` is the field that keeps its meaning when the
    comparison later widens to two emitters (A-7.2), and using it here means
    the flat and nested legs of the oracle are literally the same assertion.
    """
    from_model = segments(model(name), emitter="generico")
    from_xml = segments(bundle(name, "generico"))

    assert [content_of(s) for s in from_xml] == [content_of(s) for s in from_model], (
        f"{name}: the flat reader's reconstruction diverges from the model"
    )
    # The ids are the same too, on this leg — the model path composes them the
    # way this emitter does, which is what makes its `urn` resolve (T-9).
    assert [s.id for s in from_xml] == [s.id for s in from_model]


@pytest.mark.parametrize("name", SAMPLES)
def test_nested_xml_reconstructs_the_model_sections(name: str) -> None:
    """Nested XML segments to what the model segments to — amendment A-R.5.

    The nested reader has the harder job of the two and the easier temptation:
    the ids are right there and splitting them on `_` would work. It must not,
    and T-10 is the test that it does not; this test is the other half, that
    refusing to read ids still produces the *right* answer.

    §5.4 Constraint 1 is why that matters. The nested schema forces a section's
    own prose to be serialised **after** its subsections, so sibling position
    is not reading order and a reader that trusted either position or the id
    ordinals would reassemble the document wrongly — silently, and only for
    documents that actually nest.
    """
    from_model = segments(model(name), emitter="generico-aninhado")
    from_xml = segments(bundle(name, "generico-aninhado"))

    assert [content_of(s) for s in from_xml] == [content_of(s) for s in from_model], (
        f"{name}: the nested reader's reconstruction diverges from the model"
    )
    assert [s.id for s in from_xml] == [s.id for s in from_model]


@pytest.mark.parametrize("name", SAMPLES)
def test_model_and_xml_agree_on_route(name: str) -> None:
    """`route` is read from the artifact, never re-inferred — decision D-3.

    Not in the spec's T-1…T-17 table, and deliberately added: `route` is the
    one `Segment` field T-2 and T-3 do *not* compare, which makes it the one
    field where the model path and the readers can drift without any test
    noticing. D-3 says the value comes from the artifact — the document
    element, `Norma` or not — precisely so that a reader never becomes a
    second router.

    `emitter` and `route` are separate axes (amendment A-R.7): a
    `norma`-routed document is still written out by the flat or nested
    generico emitter when asked, and the resulting artifact is a
    `DocumentoGenerico`. Its segments' route is therefore a fact about the
    *file*, not about how the router classified the DOCX.

    Written after a measured disagreement: `ids._region_segments` and the
    tituloAnexo block copied `model.route` (`norma`) while `ids._tree_segments`
    wrote `generico`, so `segments(model, emitter="generico")` and
    `segments(render_generico(model))` differed on exactly `port_mf_277`'s four
    region segments and its tituloAnexo. `port_mf_277` is the corpus's only
    `norma`-routed sample, so it is the only one that could ever have shown
    it — which is why this runs over all fifteen rather than over that one:
    the other fourteen are the guard that a future drift is still confined to
    a cause someone reasoned about.
    """
    for emitter, _ in EMITTERS:
        from_model = segments(model(name), emitter=emitter)
        from_xml = segments(bundle(name, emitter))
        assert [s.route for s in from_model] == [s.route for s in from_xml], (
            f"{name}/{emitter}: model says "
            f"{sorted({s.route for s in from_model})}, XML says "
            f"{sorted({s.route for s in from_xml})}"
        )

    # A `norma` artifact really is `norma`, so the field is not simply
    # constant — without this the assertion above is satisfied by a segmenter
    # that hardcodes `"generico"` everywhere.
    if model(name).route == "norma":
        assert "norma" in {s.route for s in segments(bundle(name, "norma"))}


# --------------------------------------------------------------------------
# T-4 — the statutory route
# --------------------------------------------------------------------------


def test_norma_xml_segments_statutory_elements() -> None:
    """`port_mf_277`'s articles, caputs and regions — Cycle 7's statutory leg.

    The second id grammar (amendment **A-6.1**) is the point. Both schemas
    *pattern-constrain* a dispositivo id, so `art1_cpt` is spelled like a path
    but is not one: it is a `Caput` element inside an `Artigo` element, and the
    reader must reach it by containment. A reader that reused the flat one's
    `_`-arithmetic would happen to get the same parent here and would break the
    moment it met `art1_par1u` — the unnumbered sole paragraph, whose id ends
    in a letter.

    `route == "norma"` is asserted on every segment because spec decision D-3
    makes route a property *read from the artifact*, never re-inferred. A
    reader that re-derived it would be a second router, and the corpus has one
    router already.
    """
    b = bundle(NORMA_SAMPLE, "norma")
    segs = segments_from_norma_xml(b.primary)
    by_id = {s.id: s for s in segs}

    # The four dispositivos this document actually has, with their nesting.
    for ident, kind, level, path in (
        ("art1", "artigo", 1, (1,)),
        ("art1_cpt", "caput", 2, (1, 1)),
        ("art2", "artigo", 1, (2,)),
        ("art2_cpt", "caput", 2, (2, 1)),
    ):
        assert ident in by_id, f"{ident} missing from {sorted(by_id)}"
        seg = by_id[ident]
        assert (seg.kind, seg.level, seg.path) == (kind, level, path), (
            f"{ident}: expected {(kind, level, path)}, got "
            f"{(seg.kind, seg.level, seg.path)}"
        )

    # The `ParteInicial` / `ParteFinal` regions, which carry the epígrafe,
    # ementa and preâmbulo — the text an article-only reader would drop.
    kinds = [s.kind for s in segs if s.is_region]
    assert kinds == ["epigrafe", "ementa", "preambulo", "assinatura"], kinds

    # Reading order, not element-name order: `ParteFinal`'s assinatura comes
    # after the articulation, and a reader that fetched the regions by name
    # would have appended it before `art1`.
    order = [s.kind for s in segs]
    assert order.index("assinatura") > order.index("caput")

    assert {s.route for s in segs} == {"norma"}

    # A caput's rótulo repeats its article's (A-6.4). It stays as `label`
    # because a reader wants the caption; conservation skips it because the
    # source said it once — and that flag is the mechanism, so it is pinned.
    assert by_id["art1_cpt"].echoed_label is True
    assert by_id["art1"].echoed_label is False
    assert by_id["art1_cpt"].label == by_id["art1"].label == "Art. 1º"


# --------------------------------------------------------------------------
# T-5 — breadcrumbs
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_breadcrumbs_are_complete(name: str) -> None:
    """Every ancestor is in the breadcrumb, in order, with no gaps — Rule A.

    Plan §2.4's first measured bug was a breadcrumb silently missing its middle
    ancestor: an id of `pp1_agr1_agr2_agr1` whose `pp1_agr1_agr2` did not
    exist. "Silently" is the operative word — the breadcrumb still rendered,
    still looked plausible, and pointed at the wrong context.

    The check is structural rather than string-matching: a segment's breadcrumb
    must be exactly the `title` of each segment along its `path` prefix chain,
    and `len(breadcrumb) == len(path) - 1`. That is stronger than "the ancestor
    appears somewhere", which a breadcrumb of every title in the document would
    also satisfy.

    Spec decision **D-4** says a section with neither label nor heading
    contributes `""`. So the assertion is that no entry is `None` and that the
    *count* is right — an empty string records the depth honestly, where a
    dropped entry would silently promote a grandchild to a child.
    """
    for emitter, _ in EMITTERS:
        b = bundle(name, emitter)
        for document in b.documents:
            segs = segments(document)
            by_path = {s.path: s for s in segs if s.path}
            for seg in segs:
                if seg.is_region:
                    assert seg.breadcrumb == (), (
                        f"{name}/{emitter}: region {seg.id} has a breadcrumb"
                    )
                    continue

                assert len(seg.breadcrumb) == len(seg.path) - 1, (
                    f"{name}/{emitter}: {seg.id} at path {seg.path} has "
                    f"{len(seg.breadcrumb)} breadcrumb entries"
                )
                assert seg.depth == len(seg.breadcrumb)
                assert all(entry is not None for entry in seg.breadcrumb)

                # Each entry is the title of the ancestor at that prefix — the
                # part a missing middle ancestor gets wrong.
                for cut in range(1, len(seg.path)):
                    ancestor = by_path.get(seg.path[:cut])
                    assert ancestor is not None, (
                        f"{name}/{emitter}: {seg.id}'s ancestor at "
                        f"{seg.path[:cut]} is not itself a segment"
                    )
                    assert seg.breadcrumb[cut - 1] == ancestor.title, (
                        f"{name}/{emitter}: {seg.id} breadcrumb[{cut - 1}] is "
                        f"{seg.breadcrumb[cut - 1]!r}, ancestor "
                        f"{ancestor.id} is titled {ancestor.title!r}"
                    )


# --------------------------------------------------------------------------
# T-6 — conservation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_no_duplicated_text_across_segments(name: str) -> None:
    """The segments' words are the document's words, exactly — Rule B.

    A **multiset** equality, in both directions at once, which is the only form
    that catches both of §2.4's measured failures with one assertion:

    * *Loss* — a subsection's prose that no segment reports, which a subset
      check would pass.
    * *Duplication* — the `descendant::p|descendant::li` idiom counting nested
      list text under both the list and the item, which a **set** comparison
      would hide entirely. Deduplicating here would make the test blind to the
      exact bug that motivated Rule B.

    The currency is `own_words`, not `text` (see the module docstring):
    `label` and `heading` are source text held in typed fields, and an echoed
    `Caput` rótulo is written twice by the emitter though the source said it
    once (A-6.4). `own_words` is the field that reconciles those; a check over
    `text` alone reports every rótulo in the corpus as lost.
    """
    for emitter, _ in EMITTERS:
        b = bundle(name, emitter)
        segs = segments(b)
        got = Counter(w for s in segs for w in s.own_words)
        expected = Counter(words(b.texts))

        assert got == expected, (
            f"{name}/{emitter}: lost {sorted((expected - got).elements())[:8]}, "
            f"duplicated {sorted((got - expected).elements())[:8]}"
        )

    # The model path carries the same guarantee without ever building XML —
    # otherwise conservation would be a property of the serialiser rather than
    # of the segmentation.
    flat = bundle(name, "generico")
    model_segs = segments(model(name), emitter="generico")
    assert Counter(w for s in model_segs for w in s.own_words) == Counter(
        words(flat.texts)
    ), f"{name}: the model path does not conserve the document's words"


# --------------------------------------------------------------------------
# T-7, T-8, T-9 — the urn is an address
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_segment_urns_are_unique(name: str) -> None:
    """No two segments in a bundle share a urn — §9.2 invariant #5.

    A citation is only a citation if it denotes one thing. Uniqueness is
    checked across the **whole bundle**, primary and annexes together, because
    an annex is a separate document with its own id root (§2.9) and a check
    per-document would miss a collision between them.

    `port_mf_277`'s `Assinatura` is the corpus's one id-less segment — the
    LexML schema gives `Assinatura` no `id` attribute at all — so its urn is
    the document urn with an empty fragment. It is unique because there is one
    of it; the test does not exempt it, and a second id-less segment in the
    same document would rightly fail here.
    """
    emitters = ["generico", "generico-aninhado"]
    if model(name).route == "norma":
        emitters.append("norma")

    for emitter in emitters:
        urns = [s.urn for s in segments(bundle(name, emitter))]
        duplicates = [u for u, n in Counter(urns).items() if n > 1]
        assert not duplicates, f"{name}/{emitter}: duplicate urns {duplicates[:5]}"
        assert len(urns) == len(set(urns))


@pytest.mark.parametrize("name", SAMPLES)
def test_segment_urns_are_stable_across_reruns(name: str) -> None:
    """Two runs give the same segments — §9.2 determinism.

    Segmentation runs twice over **independently parsed** copies of the same
    XML, not over the same element twice: re-segmenting one in-memory tree
    would only prove the function is not stateful, while a nondeterministic
    *reader* — one iterating a set or a dict built from attributes — would
    still pass. Reparsing forces fresh element objects with fresh identities,
    which is where iteration-order nondeterminism actually shows up.

    Determinism is asserted on the whole record, not just the urn: an unstable
    `order` or `breadcrumb` would make goldens flap for reasons no diff
    explains.
    """
    b = bundle(name, "generico")
    payloads = [
        etree.tostring(document, encoding="utf-8") for document in b.documents
    ]

    def run() -> list[tuple]:
        out: list[tuple] = []
        for payload in payloads:
            for seg in segments(etree.fromstring(payload)):
                out.append((seg.urn,) + content_of(seg))
        return out

    first, second = run(), run()
    assert first == second, f"{name}: segmentation is not deterministic"

    # The model path is the one goldens are written from, so it is pinned too.
    a = segments(model(name), emitter="generico")
    c = segments(model(name), emitter="generico")
    assert [(s.urn,) + content_of(s) for s in a] == [
        (s.urn,) + content_of(s) for s in c
    ]


@pytest.mark.parametrize("name", SAMPLES)
def test_segment_urns_resolve_to_their_element(name: str) -> None:
    """Each urn's id half selects exactly one element in its own document.

    This is what makes `urn` a citation rather than a label. A urn that
    resolves to nothing is a dangling reference; one that resolves to two is
    ambiguous; and both failures are invisible until a consumer tries to
    follow one, which is generally long after the document was published.

    Resolution is scoped by `Segment.document`, so an annex's segment is looked
    up in the annex (§2.9) — a bundle-wide search would let a primary id stand
    in for a missing annex id and pass for the wrong reason.

    The one documented exception is `Assinatura`, which the LexML base schema
    declares with **no `id` attribute**: it can carry text but cannot be
    addressed. Its segment is emitted anyway — excluding it would put its text
    outside T-6's reach — and the test asserts that it is the *only* id-less
    segment in the corpus rather than skipping id-less segments as a class.
    """
    emitters = ["generico", "generico-aninhado"]
    if model(name).route == "norma":
        emitters.append("norma")

    unaddressable: list[tuple[str, str]] = []
    for emitter in emitters:
        b = bundle(name, emitter)
        by_urn = {document_urn(d): d for d in b.documents}

        for seg in segments(b):
            assert seg.urn == f"{seg.document}!{seg.id}", (
                f"{name}/{emitter}: {seg.urn!r} is not "
                f"{{document}}!{{id}} of {seg.document!r} / {seg.id!r}"
            )
            document = by_urn.get(seg.document)
            assert document is not None, (
                f"{name}/{emitter}: {seg.urn} names document {seg.document!r}, "
                f"which is not in the bundle {sorted(by_urn)}"
            )

            if not seg.id:
                unaddressable.append((emitter, seg.kind))
                continue

            found = [e for e in document.iter() if e.get("id") == seg.id]
            assert len(found) == 1, (
                f"{name}/{emitter}: {seg.urn} selects {len(found)} elements"
            )
            # The element it resolves to must be the *kind* the segment claims,
            # so a urn cannot resolve to a neighbouring element by accident.
            tag = local_name(found[0].tag)
            assert tag in ADDRESSABLE_TAGS, (
                f"{name}/{emitter}: {seg.urn} resolves to a {tag}, which is "
                f"not an element this project addresses"
            )

    assert unaddressable == [] or unaddressable == [("norma", "assinatura")], (
        f"{name}: unexpected id-less segments {unaddressable}; only "
        f"Assinatura, which the schema gives no id attribute, may be one"
    )


# --------------------------------------------------------------------------
# T-10 — the nested reader does not read ids
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_nested_reader_ignores_ids(name: str) -> None:
    """Rewrite every `id`; every field but `id`/`urn` comes back identical.

    Cycle 7's risk #1, asserted rather than intended. The nested emitter still
    writes path-composed ids, so a reader that split them on `_` would produce
    the right answer on every sample in the corpus — and would be a second copy
    of the flat reader wearing the nested one's name. The moment a nested
    document arrived from anywhere else, or was hand-edited, it would break.

    The mutation is total **and destroys the path grammar**, which is stronger
    than the prefixing the spec's column suggests. Prefixing every id leaves
    `Xpp1_agh1_agh2` — still four underscore-separated steps in ascending
    order — so a reader deriving depth from `id.count("_")` would survive it
    and the test would certify a cheat. Measured: that exact one-line cheat
    passes a prefix-only mutation.

    So every id is replaced with a flat, opaque, **counter-ordered** token:
    no separators to split, no ordinals to read, and an ordering that is the
    document's serialised order rather than its reading order. Nothing about
    the tree is recoverable from the ids afterwards. If `level`, `path`,
    `breadcrumb` or `order` came from an id at any point, they move.

    `id` and `urn` are excluded because the reader copies the attribute into
    them by design — that is a value it carries, not structure it infers, and
    the spec says so explicitly. `document` stays put because a document's URN
    lives in `Identificacao/@URN`, which is not an `id`.
    """
    for document in bundle(name, "generico-aninhado").documents:
        original = segments_from_nested_xml(document)

        mutated_doc = copy.deepcopy(document)
        replacements: list[str] = []
        for counter, element in enumerate(mutated_doc.iter()):
            if element.get("id") is not None:
                # No `_`, no ordinal that tracks position in the tree, and
                # assigned in serialised order — which §5.4 Constraint 1
                # guarantees is *not* reading order for a nesting document.
                opaque = f"z{counter:04d}"
                element.set("id", opaque)
                replacements.append(opaque)
        assert replacements, f"{name}: nothing to mutate — the test is vacuous"
        assert not any("_" in r for r in replacements)

        mutated = segments_from_nested_xml(mutated_doc)

        assert [content_of(s) for s in mutated] == [
            content_of(s) for s in original
        ], f"{name}: the nested reader's output depends on the ids"
        assert [s.document for s in mutated] == [s.document for s in original]

        # And the mutation really did reach the segments, so the comparison
        # above is a comparison and not two identical runs.
        assert [s.id for s in mutated] != [s.id for s in original]
        assert set(s.id for s in mutated) <= set(replacements)


# --------------------------------------------------------------------------
# T-11 — order comes from `ordem`
# --------------------------------------------------------------------------


def test_order_comes_from_ordem_not_position() -> None:
    """Children serialised backwards still segment in reading order.

    Plan §5.4 Constraint 1 forces a section's own prose to be serialised
    *after* its subsections, which means sibling position in nested output is
    not reading order. Amendment **A-5b.2** answers that with
    `Bloco nome="ordem"` — a 0-based document-order index, the **only** order
    channel the nested format has.

    No sample can test this, because the emitter writes `ordem` in ascending
    order and a reader that ignored it would still get the corpus right. So the
    document is hand-built with the children serialised in *reverse* `ordem`
    order: a position-trusting reader returns C, B, A and a marker-reading one
    returns A, B, C. The two answers are maximally different, which is the
    point of reversing rather than shuffling.
    """
    root, parte = synthetic_document()
    section = el("AgrupamentoHierarquico", id="pp1_agh1", nome="secao")
    rotulo = el("Rotulo")
    rotulo.text = "1."
    section.append(rotulo)
    parte.append(section)

    # Serialised C, B, A — carrying ordem 2, 1, 0.
    for label, ordem in (("C", "2"), ("B", "1"), ("A", "0")):
        child = el("AgrupamentoHierarquico", id=f"pp1_agh1_agh{label}", nome="subsecao")
        child_rotulo = el("Rotulo")
        child_rotulo.text = label
        child.append(child_rotulo)
        child.append(bloco("ordem", ordem))
        leaf = el("Agrupamento", id=f"pp1_agh1_agh{label}_txt1", nome="txt")
        leaf.append(para(f"texto {label}"))
        child.append(leaf)
        section.append(child)

    segs = segments_from_nested_xml(root)
    children = [s for s in segs if len(s.path) == 2]

    assert [s.label for s in children] == ["A", "B", "C"], (
        "the nested reader followed sibling position instead of "
        f"Bloco nome='ordem': got {[s.label for s in children]}"
    )
    # `order` is the marker's value, restated — not the position it was found
    # at, and not the position it ended up in by accident.
    assert [s.order for s in children] == [0, 1, 2]
    # And `path` follows reading order too, so a citation into the reordered
    # document points at the section a reader would call the first one.
    assert [s.path for s in children] == [(1, 1), (1, 2), (1, 3)]
    assert [s.text for s in children] == ["texto A", "texto B", "texto C"]


# --------------------------------------------------------------------------
# T-12 — a broken id path degrades, it does not crash
# --------------------------------------------------------------------------


def test_flat_reader_survives_a_gapped_id_path() -> None:
    """A missing intermediate `Agrupamento` loses no text and is not bridged.

    Rule A says every proper prefix of an id exists — and plan §2.4 recorded
    what happens when it does not: the breadcrumb silently loses its middle
    ancestor and the segment appears one level shallower than it is. The corpus
    satisfies Rule A everywhere, so the failing case has to be constructed.

    `pp1_agr1` and `pp1_agr1_agr2_agr1` exist; `pp1_agr1_agr2` does not. The
    contract asserted here is *graceful degradation*, the plan's standing
    preference over rules tuned to the corpus:

    * no exception — a hand-edited or truncated file must still segment;
    * no text loss — the orphan is attached to the nearest ancestor that does
      exist, not dropped;
    * **the gap stays visible** — the orphan keeps its declared `level` of 3
      while its breadcrumb has one entry, so `level - 1 != depth` is the
      discrepancy a validator can detect. A reader that renumbered it to level
      2 would have silently invented an ancestry the document does not have,
      which is the §9.2 "no fabricated structure" invariant.
    """
    root, parte = synthetic_document()
    for ident, nivel, text in (
        ("pp1_agr1", "1", "alfa"),
        ("pp1_agr1_agr2_agr1", "3", "beta"),
    ):
        agrupamento = el("Agrupamento", id=ident, nome="secao")
        agrupamento.append(bloco("nivel", nivel))
        agrupamento.append(para(text))
        parte.append(agrupamento)

    segs = segments_from_flat_xml(root)

    assert [s.id for s in segs] == ["pp1_agr1", "pp1_agr1_agr2_agr1"], (
        f"the gapped document lost a segment: {[s.id for s in segs]}"
    )
    # No text loss: both words survive, exactly once each.
    assert Counter(w for s in segs for w in s.own_words) == Counter(["alfa", "beta"])

    orphan = segs[1]
    # Attached to the nearest *existing* ancestor, not to the root and not
    # dropped — so its path descends from `pp1_agr1`'s.
    assert orphan.path[:1] == segs[0].path
    # The gap is reported, not bridged: the declared depth and the recoverable
    # ancestry disagree, and that disagreement is the diagnostic.
    assert orphan.level == 3
    assert orphan.depth == 1
    assert orphan.level - 1 != orphan.depth, (
        "a gapped id path must stay detectable; this reader has silently "
        "bridged the missing ancestor"
    )


# --------------------------------------------------------------------------
# T-13 — regions
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_regions_are_segments_with_empty_path(name: str) -> None:
    """Front/back matter is segmented, at `path == ()` and `level == 0`.

    Spec decision **D-6**. Regions are `Agrupamento` children of
    `PartePrincipal` with real ids and real text (A-5.1), and excluding them
    would put the epígrafe, the ementa and the assinatura outside T-6's reach —
    which would make "no text is missing from the segments" unassertable rather
    than true.

    `level == 0` rather than 1 is the substantive part: a region is not the
    first level of the body, it is outside the body hierarchy entirely, and
    `path == ()` says so in the field a consumer compares across emitters. A
    region that consumed a path ordinal would shift every body section's
    address by the number of front regions — which is exactly the flat/nested
    id offset A-5b.4 measured, and exactly what `path` exists to normalise
    away.

    Fourteen of the fifteen samples have regions; `CARNE_LEAO` is an untitled
    excerpt with no front or back matter at all, so its region population is
    legitimately empty. That is asserted by *name* rather than tolerated by an
    `if regions:` guard — a guard would let the other fourteen quietly lose
    their regions and still pass, which is the failure mode this test exists to
    catch.
    """
    for emitter, _ in EMITTERS:
        segs = segments(bundle(name, emitter))
        regions = [s for s in segs if s.is_region]

        if name == NO_REGION_SAMPLE:
            assert regions == [], (
                f"{name} is the corpus's one region-less document; it now has "
                f"{[r.kind for r in regions]}"
            )
        else:
            assert regions, f"{name}/{emitter}: no region segments at all"

        for region in regions:
            assert region.path == (), f"{name}/{emitter}: {region.id} has a path"
            assert region.level == REGION_LEVEL == 0
            assert region.breadcrumb == ()

        # `is_region` is derived from `path`, so the two must not disagree.
        assert [s.is_region for s in segs] == [not s.path for s in segs]

        # Body sections start at ordinal 1 regardless of how many regions
        # preceded them — the A-5b.4 offset normalised away.
        tops = [s.path for s in segs if len(s.path) == 1]
        assert tops == [(i + 1,) for i in range(len(tops))], (
            f"{name}/{emitter}: top-level paths are {tops[:6]}, so a region "
            f"consumed a body ordinal"
        )


# --------------------------------------------------------------------------
# T-14 — annexes are separate documents
# --------------------------------------------------------------------------


def test_annex_segments_carry_the_annex_urn() -> None:
    """`port_mf_277` segments span the primary **and** the annex — §2.9.

    The corpus's only annex, and the reason `Segment.document` exists as a
    field rather than being implied by the bundle. An annex is a separate
    document with its own URN fragment (`…!anexo1`) and its own id root
    (`anexo1_pp`), so an annex segment's urn is `…!anexo1!anexo1_pp_agr2` — two
    fragment separators, which is correct and looks wrong enough to be worth
    pinning.

    Both halves are asserted, in every emitter. A segmenter that stopped at the
    primary would pass every other test in this module — the primary is
    self-consistent — while silently dropping 65 súmulas.
    """
    primary_urn = model(NORMA_SAMPLE).metadata.urn
    annex_urn = f"{primary_urn}!anexo1"

    for emitter in ("generico", "generico-aninhado", "norma"):
        segs = segments(bundle(NORMA_SAMPLE, emitter))
        documents = {s.document for s in segs}
        assert documents == {primary_urn, annex_urn}, (
            f"{emitter}: segments span {sorted(documents)}"
        )

        primary = [s for s in segs if s.document == primary_urn]
        annex = [s for s in segs if s.document == annex_urn]
        assert primary and annex

        # Document order: the primary is finished before the annex begins, so
        # a consumer reading the tuple reads the document.
        assert [s.document for s in segs] == [primary_urn] * len(primary) + [
            annex_urn
        ] * len(annex)

        # Each annex segment's urn opens with its own document's urn, and its
        # id hangs off the annex's own root rather than the primary's `pp1`.
        for seg in annex:
            assert seg.urn.startswith(f"{annex_urn}!")
            if seg.id:
                assert seg.id.startswith("anexo1_pp"), seg.id

        # The 65 súmulas of A-4.5, plus the `tituloAnexo` block (A-5.6).
        assert len([s for s in annex if not s.is_region]) == 65
        assert annex[0].kind == "tituloAnexo"
        assert annex[0].text == "ANEXO ÚNICO"


# --------------------------------------------------------------------------
# T-15 — full_text vs text
# --------------------------------------------------------------------------


def test_full_text_is_cumulative_and_text_is_not() -> None:
    """A parent's `full_text` contains its child's prose; its `text` does not.

    Spec decision **R-5**, and the reason T-6 is writable at all. §6.2's
    stylesheet idiom (`descendant::p`) produces the *cumulative* reading, which
    is what a retrieval consumer usually wants — and which, if it were
    `Segment.text`, would put every child's words in every ancestor and make
    "no duplicated text" false by construction rather than by bug.

    So both readings exist and this test measures the difference between them
    rather than asserting each separately: the exact words `full_text` adds to
    `text` must be exactly the descendants' own words. A `full_text` that
    merely *contained* the child would also be satisfied by one that repeated
    the parent, and this corpus's deepest section has seven descendants to
    repeat.
    """
    segs = segments(model(DEEP_SAMPLE))
    by_path = {s.path: s for s in segs if s.path}

    # `pp1_agr4_agr3` — a section with *both* its own prose and children, which
    # is the only shape that can tell the two readings apart.
    parent = by_path[(1, 3)]
    assert parent.text, "the chosen parent must have own text"
    assert parent.descendant_texts, "the chosen parent must have children"

    descendants = [
        s for s in segs if s.path[: len(parent.path)] == parent.path and s is not parent
    ]
    assert descendants

    for child in descendants:
        if not child.text:
            continue
        assert child.text in parent.full_text, (
            f"{child.id}'s text is missing from {parent.id}'s full_text"
        )
        assert child.text not in parent.text, (
            f"{child.id}'s text leaked into {parent.id}'s own text — Rule B"
        )

    # The difference is exactly the descendants' own words, no more and no
    # less: nothing invented, nothing counted twice.
    assert Counter(parent.full_text.split()) == Counter(parent.text.split()) + Counter(
        w for d in descendants for w in d.text.split()
    )

    # A leaf's two readings coincide — otherwise `full_text` is adding
    # something that is not a descendant.
    leaves = [s for s in segs if s.path and not s.descendant_texts]
    assert leaves
    assert all(leaf.full_text == leaf.text for leaf in leaves)


# --------------------------------------------------------------------------
# T-16 — the degenerate document
# --------------------------------------------------------------------------


def test_empty_document_segments_to_nothing() -> None:
    """An empty document gives `()`, not an exception and not a phantom.

    Robustness, in the shape the 300 unseen documents will eventually supply:
    a document whose body the pipeline could not populate. The two wrong
    answers are a traceback — which would take down a batch run for one bad
    input — and a single empty segment standing in for "the document", which
    would put a fabricated unit into a citation index.

    Both readers and the dispatcher are checked, because `segments()` chooses
    its reader by inspecting the markup (there is no `AgrupamentoHierarquico`
    here, so it must land on the flat one) and an empty document is precisely
    where a dispatcher's fallback is untested.
    """
    root, _ = synthetic_document()

    assert segments_from_flat_xml(root) == ()
    assert segments_from_nested_xml(root) == ()
    assert segments(root) == ()

    # No `PartePrincipal` at all — a `Norma` shell, or a truncated file.
    bare = el("LexML")
    metadado = el("Metadado")
    metadado.append(el("Identificacao", URN="urn:lex:br:test:parecer:2020-01-01;1"))
    bare.append(metadado)
    assert segments(bare) == ()
    assert segments_from_norma_xml(bare) == ()

    # And the same through the string/path forms of the entry point, which a
    # batch caller is far more likely to use than a parsed element.
    assert segments(etree.tostring(root, encoding="unicode")) == ()


# --------------------------------------------------------------------------
# T-17 — the nested emitter's markers stay out of the text channel
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_vazio_and_ordem_blocos_are_not_text(name: str) -> None:
    """`Bloco nome="ordem"` / `"vazio"` are structure, never prose — A-5b.2.

    The nested emitter carries two things out of band that the flat one does
    not need: the reading-order index (§5.4 Constraint 1's answer) and an
    explicit empty-section marker. Both are `Bloco` elements, and a reader that
    extracted text by "everything under this element" would sweep them into the
    prose — where they would inflate T-6's word multiset with integers and with
    the literal string `vazio`, and would leak into every excerpt a consumer
    ever showed a human.

    Asserted **differentially**, not by pattern-matching the text. A digit
    heuristic cannot work: the corpus's prose is full of legitimate standalone
    numbers — article references, percentages, súmula numbers — so "no segment
    contains an integer" is false of correct output, and narrowing it to "no
    integer that some marker in this document also holds" is false of
    `sumula_stj_125`, whose section 6 both exists and is numbered 6.

    So the marker values are **changed** instead, to strings no document could
    plausibly contain, and the segments are re-derived. If a marker were
    reaching the text channel the two runs would differ; because it is not,
    they are identical in every field but `order`, which is the one field the
    `ordem` marker is *supposed* to feed. That distinguishes "read as
    structure" from "swept into prose" without guessing at what prose looks
    like.
    """
    b = bundle(name, "generico-aninhado")
    for document in b.documents:
        markers = [
            e
            for e in document.iter(f"{LEX}Bloco")
            if e.get("nome") in ("ordem", "vazio", "nivel")
        ]
        if not markers:
            # A document with no sections has no markers, and nothing to
            # confuse — but the corpus must not be marker-free overall, which
            # the assertion after this loop pins.
            continue

        original = segments_from_nested_xml(document)
        assert original, f"{name}: nothing segmented, so nothing is measured"

        # No literal `vazio` reaches any text-bearing field. That one *is*
        # checkable directly: it is not a Portuguese word the corpus uses.
        for seg in original:
            assert "vazio" not in seg.text, f"{name}: {seg.id} carries `vazio`"
            assert seg.label != "vazio" and seg.heading != "vazio"

        # Now poison every marker and re-read. `SENTINELA` cannot appear in
        # prose, so any leak becomes visible as a text difference.
        poisoned = copy.deepcopy(document)
        touched = 0
        for element in poisoned.iter(f"{LEX}Bloco"):
            if element.get("nome") in ("ordem", "vazio", "nivel"):
                element.text = "SENTINELA"
                touched += 1
        assert touched == len(markers)

        after = segments_from_nested_xml(poisoned)
        for before_seg, after_seg in zip(original, after):
            assert "SENTINELA" not in after_seg.text, (
                f"{name}: {before_seg.id} swept a marker Bloco into its text"
            )
            assert "SENTINELA" not in (after_seg.label or "")
            assert "SENTINELA" not in (after_seg.heading or "")
            assert after_seg.text == before_seg.text, (
                f"{name}: {before_seg.id}'s text depends on a marker's value"
            )

    # The markers exist exactly when there are body sections to order — five
    # of the fifteen samples are flat front-matter-only documents with no
    # sections and therefore, correctly, no markers. Tying the expectation to
    # the section count rather than skipping those five means an emitter that
    # stopped writing `ordem` on a document that *has* sections fails here,
    # which is the regression that would otherwise make the loop above vacuous.
    all_markers = [
        e
        for document in b.documents
        for e in document.iter(f"{LEX}Bloco")
        if e.get("nome") in ("ordem", "vazio", "nivel")
    ]
    body_sections = [s for s in segments(b) if not s.is_region]
    assert bool(all_markers) == bool(body_sections), (
        f"{name}: {len(body_sections)} body sections but "
        f"{len(all_markers)} order/empty markers"
    )

    # And conservation still holds, which is the reason this matters: a marker
    # counted as text is a word the source never said.
    segs = segments(b)
    assert Counter(w for s in segs for w in s.own_words) == Counter(words(b.texts))
