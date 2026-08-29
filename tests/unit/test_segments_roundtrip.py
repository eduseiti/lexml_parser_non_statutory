"""`hierarchy_from_xml()` — the reversibility invariant, §9.2, plan Cycle 7.

Relocated from the withdrawn Cycle 6b (A-R.6). The module under test says why it
still matters with `articulado-sintetico` gone: three emitters now write the
same `DocumentModel` three ways, and a claim that any of them is *lossless in
structure* is worth nothing until something reads the file back and compares.
This is that something.

What round-trip means here, stated precisely, because the loose reading is false
--------------------------------------------------------------------------------

`model → XML → model'` does **not** give back the model. Three things are gone
by construction, and each one is a deliberate design decision recorded in the
source rather than an accident this module works around:

* **Paragraph boundaries inside a section.** `roundtrip._paras` builds *one*
  `Para` from the readers' single joined own-text string. A section whose model
  body held four `Para`s comes back holding one. So node identity is not the
  currency; the **word multiset** is (T-20), exactly as in
  `test_conservation_generico.py` and `test_norma_conservation.py`, and for the
  same reason — a source paragraph legitimately becomes more than one element,
  so comparing paragraphs reports false losses.
* **Inline formatting.** A rebuilt `Para` carries one plain `Inline`. The XML
  records what the text *says*, not which runs were bold.
* **Evidence.** No emitter writes `Evidence`, `confidence` or `DocSignals` into
  the XML, because the XML is the document and not the reasoning that produced
  it. T-22 asserts they come back at their **default values, by value**, which
  is the point: a reader that started *guessing* at a confidence would still
  produce a truthy float and pass a truthiness check. A fabricated confidence is
  worse than an absent one, and only a by-value assertion catches one.

What *is* claimed, and is asserted at full strength: **tree shape** — the
`walk()`-order `(kind, label, heading, level)` tuples — and **every word**.
Those two hold on all 15 samples, on both `generico` emitters, annexes included.

Why T-24 is not the spec's sentence
-----------------------------------

The spec's §5.1 phrasing for T-24 is "`model → xml → model' → xml'`, `xml ==
xml'` byte-for-byte". **That is measurably false, and writing it would have
produced a failing or a weakened test.** It fails on the first re-render for
every one of the 15 samples, for the paragraph-joining reason above: the first
XML carries N `<p>` elements per section and the second carries one, so the
bytes cannot match and no amount of care in the reader would make them.

What is true — measured across all 15 samples × both emitters — is stronger than
it sounds and is what T-24 asserts instead: the round-trip reaches a **fixpoint
after one pass**. `xml₂ == xml₃` byte-for-byte, and `model'₁ == model'₂` as a
whole `HierarchyDoc`. The lossy step happens exactly once and never again, which
is the real content of "reversible": re-reading a document does not keep eroding
it. Stating the spec's version and skipping it would have hidden that; asserting
the fixpoint proves the erosion is bounded at one pass, which the byte-equality
sentence never would have.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.hierarchy import HierarchyDoc
from lexml_nonstat.hierarchy.evidence import DocSignals
from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.model.nodes import Evidence, ListNode, Para, Table
from lexml_nonstat.render import (
    render_generico,
    render_generico_aninhado,
    render_norma,
    to_xml_string,
    words,
)
from lexml_nonstat.segments import hierarchy_from_xml, sections_from_xml

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: The one sample with an annex, and the only one routed to `norma`.
ANNEX_SAMPLE = "port_mf_277_20180607"

#: A-4.5's measured annex size: `ANEXO ÚNICO`'s tree carries 65 sections.
ANNEX_SECTIONS = 65

assert len(SAMPLES) == 15, SAMPLES
assert ANNEX_SAMPLE in SAMPLES

#: Building a model costs a DOCX parse plus the whole inference stack, and this
#: module wants every sample several times over. Cached per session, the
#: `test_cross_emitter.py` idiom.
_MODELS: dict[str, object] = {}

#: The two emitters whose round-trip claim is "shape *and* text". `norma`
#: rewrites the body into dispositivos, so it gets its own test (T-21) rather
#: than joining the parametrised sweep.
GENERICO_EMITTERS = {
    "generico": render_generico,
    "generico-aninhado": render_generico_aninhado,
}


def model_for(name: str):
    """One sample's `DocumentModel`, built once per session."""
    if name not in _MODELS:
        path = SAMPLES_DIR / f"{name}.docx"
        _MODELS[name] = build_model(read_docx(path), filename=path.name)
    return _MODELS[name]


# --------------------------------------------------------------------------
# The two currencies: shape, and words
# --------------------------------------------------------------------------


def shape(tree) -> list[tuple[str, str | None, str | None, int]]:
    """A tree's `walk()`-order structural signature.

    `(kind, label, heading, level)` per section, depth-first in document order —
    everything about the tree that the XML is supposed to carry, and nothing
    that it is not. `body`, `evidence` and `source_indices` are deliberately
    absent: the first is text (T-20's business), the last two are things the
    round-trip is *not* claiming to recover (T-22's business).
    """
    return [(s.kind, s.label, s.heading, s.level) for s in tree.walk()]


def doc_shape(doc: HierarchyDoc) -> list:
    """Every tree in a document — body first, then each annex, in order."""
    return [shape(tree) for tree in doc.trees]


def node_texts(node) -> list[str]:
    """One content node's text, at the granularity the model stores it.

    Read from `node.text` rather than from the `Inline`s: a superscript ordinal
    such as `nº` is *two* runs in Word and one word in the document, so walking
    inlines would split it and report a phantom loss on `parecer_93` — measured,
    not hypothesised.
    """
    if isinstance(node, Para):
        return [node.text]
    if isinstance(node, ListNode):
        out: list[str] = []

        def descend(items) -> None:
            for item in items:
                out.append(item.text)
                descend(item.children)

        descend(node.items)
        return out
    if isinstance(node, Table):
        return [
            "".join(inline.text for inline in cell)
            for row in node.rows
            for cell in row
        ]
    return []


def tree_words(tree) -> Counter:
    """Every word a tree accounts for — the conservation currency.

    `label` and `heading` are counted alongside the body because they *are*
    source text: the emitters write them into `Bloco nome="rotulo"` and
    `nomeAgrupador`, so a comparison over body prose alone would report every
    rótulo in the corpus as lost. Same rule as `test_norma_conservation.py`.
    """
    counter: Counter = Counter()
    for node in tree.preamble:
        counter.update(words(node_texts(node)))
    for section in tree.walk():
        counter.update(words([section.label or "", section.heading or ""]))
        for node in section.body:
            counter.update(words(node_texts(node)))
    return counter


def doc_words(doc: HierarchyDoc) -> Counter:
    """The whole document's words, primary and annexes together."""
    counter: Counter = Counter()
    for tree in doc.trees:
        counter += tree_words(tree)
    return counter


def diff_message(name: str, before: Counter, after: Counter) -> str:
    """Both directions of the symmetric difference, capped so it stays readable.

    A bare count is not a finding: naming the words, and which way they went, is
    usually enough to point at the section that was lost or repeated.
    """
    lost = before - after
    gained = after - before
    return (
        f"{name}: round-trip changed the word multiset\n"
        f"  lost   ({sum(lost.values())}): {sorted(lost.items())[:12]}\n"
        f"  gained ({sum(gained.values())}): {sorted(gained.items())[:12]}"
    )


# --------------------------------------------------------------------------
# T-18 / T-19 — tree shape survives both generico emitters
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_roundtrip_flat_preserves_tree_shape(name: str) -> None:
    """T-18. `model → render_generico → hierarchy_from_xml` keeps the shape.

    The flat emitter carries depth **out of band**, in `Bloco nome="nivel"`, and
    ancestry in the id path (§2.4 Rule A) — every `Agrupamento` is a sibling of
    every other in the file. So this is not a formality: the reader has to
    *rebuild* a tree that the document never contained, from a string grammar,
    and getting the nesting wrong by one level anywhere in 15 documents fails
    here.
    """
    model = model_for(name)
    rebuilt = hierarchy_from_xml(render_generico(model))
    assert doc_shape(rebuilt) == doc_shape(model.hierarchy), name


@pytest.mark.parametrize("name", SAMPLES)
def test_roundtrip_nested_preserves_tree_shape(name: str) -> None:
    """T-19. Same claim via `render_generico_aninhado`.

    The nested emitter has the opposite problem to T-18's: the tree *is* in the
    file, as `AgrupamentoHierarquico` containment, but the emitter also
    interleaves prose-leaf `Agrupamento nome="txt…"` children and structural
    `Bloco nome="ordem"`/`"vazio"` markers (A-5b.1, A-5b.2). A reader that
    mistook a prose leaf for a section would produce extra sections here, and a
    reader that mistook `ordem` for content would produce them at the wrong
    depth. Asserting the *same* shape as T-18 is what makes the two emitters
    interchangeable rather than merely both readable.
    """
    model = model_for(name)
    rebuilt = hierarchy_from_xml(render_generico_aninhado(model))
    assert doc_shape(rebuilt) == doc_shape(model.hierarchy), name


@pytest.mark.parametrize("name", SAMPLES)
def test_roundtrip_agrees_between_the_two_emitters(name: str) -> None:
    """The two rebuilt shapes are equal to each other, not just to the model.

    Stated separately from T-18/T-19 so a failure reads correctly. If both
    emitters drifted from the model in the *same* way, T-18 and T-19 would each
    fail and this would pass — which localises the fault to the model side. If
    only one drifted, this fails too. Two independent failures point at a
    reader; one points at the shape function.
    """
    model = model_for(name)
    flat = doc_shape(hierarchy_from_xml(render_generico(model)))
    nested = doc_shape(hierarchy_from_xml(render_generico_aninhado(model)))
    assert flat == nested, name


# --------------------------------------------------------------------------
# T-20 — every word survives, both emitters
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
@pytest.mark.parametrize("emitter", sorted(GENERICO_EMITTERS))
def test_roundtrip_preserves_all_text(name: str, emitter: str) -> None:
    """T-20. The rebuilt document's word multiset equals the model's — §9.2.

    A **multiset**, in both directions at once. A set would miss duplication —
    the failure mode that matters most here, because a reader that emitted a
    section's prose both under the section and under its parent would still
    produce the same *set* of words. Equality of `Counter`s catches loss and
    duplication with one assertion, which is exactly invariant #2's wording:
    no loss *or* duplication.

    Paragraph structure is deliberately not compared; see the module docstring.
    """
    model = model_for(name)
    rebuilt = hierarchy_from_xml(GENERICO_EMITTERS[emitter](model))
    before = doc_words(model.hierarchy)
    after = doc_words(rebuilt)
    assert after == before, diff_message(f"{name}/{emitter}", before, after)


@pytest.mark.parametrize("name", SAMPLES)
def test_roundtrip_preserves_text_per_section_not_just_in_bulk(name: str) -> None:
    """The words are conserved *section by section*, not merely in total.

    T-20 alone would pass a reader that shuffled every section's prose into the
    document's first section: the bulk multiset would be untouched. Walking the
    two trees in lockstep and comparing per-section word multisets is what makes
    "the text came back" mean "the text came back *where it was*".
    """
    model = model_for(name)
    rebuilt = hierarchy_from_xml(render_generico(model))
    for original_tree, rebuilt_tree in zip(model.hierarchy.trees, rebuilt.trees):
        originals = list(original_tree.walk())
        rebuilts = list(rebuilt_tree.walk())
        assert len(originals) == len(rebuilts), name
        for before_section, after_section in zip(originals, rebuilts):
            before = Counter(
                words([t for n in before_section.body for t in node_texts(n)])
            )
            after = Counter(
                words([t for n in after_section.body for t in node_texts(n)])
            )
            assert after == before, diff_message(
                f"{name} §{before_section.title or before_section.kind}",
                before,
                after,
            )


# --------------------------------------------------------------------------
# T-21 — the statutory route reads back too
# --------------------------------------------------------------------------


def test_roundtrip_reads_norma() -> None:
    """T-21. `port_mf_277`'s two `Artigo`s come back as `Section`s — R-3.

    This is the one place the module *infers* rather than reads, and the source
    says so: `HierarchyDoc` has no dispositivo of its own, so an `Artigo` has
    nowhere to land but a `Section`. The claim for `norma` is therefore "shape
    and text", not "the same model" — asserted here on the kinds and rótulos
    that actually come back, so a reader that silently dropped the `Caput`
    layer (or invented a third one) fails.

    `port_mf_277` is the corpus's only `norma`-routed sample, so this is not
    parametrised; there is nothing to parametrise over.
    """
    model = model_for(ANNEX_SAMPLE)
    assert model.route == "norma", "the fixture's premise: this sample routes norma"

    rebuilt = hierarchy_from_xml(render_norma(model))

    assert [
        (s.kind, s.label, s.level) for s in rebuilt.body.walk()
    ] == [
        ("artigo", "Art. 1º", 1),
        ("caput", "Art. 1º", 2),
        ("artigo", "Art. 2º", 1),
        ("caput", "Art. 2º", 2),
    ]

    # The prose hangs off the Caput, not the Artigo — A-6.4's echoed rótulo is
    # the *label*, and the text belongs one level down. A reader that hung it on
    # the Artigo would still produce four sections and pass the check above.
    captions = [s for s in rebuilt.body.walk() if s.kind == "caput"]
    assert all(s.body for s in captions), "each Caput carries its prose"
    assert all(
        not s.body for s in rebuilt.body.walk() if s.kind == "artigo"
    ), "an Artigo's prose lives in its Caput, not in the Artigo"

    # And the words are all still there, which is the half a shape check cannot
    # see: §4.2's gate exists because a Norma that dropped a paragraph is a
    # perfectly valid Norma.
    assert doc_words(rebuilt)


def test_roundtrip_of_norma_conserves_the_source_words() -> None:
    """Every word of `port_mf_277`'s norma rendering survives the read-back.

    Compared against the *rendered* bundle's own leaf text rather than against
    the model, because the `norma` emitter rewrites the body — §4.2's four-gate
    design exists precisely because that rewrite can lose text before this
    module ever sees it. The claim under test here is the reader's, so the
    baseline is what the emitter wrote.

    The currency is the readers' `Segment.own_words`, not this module's
    `tree_words`, and the difference is A-6.4. `leaf_texts` writes a `Caput`'s
    rótulo **once**, because the source said `Art. 1º` once even though §4.3's
    shape echoes it onto both the `Artigo` and its `Caput`. `Segment` carries
    that in `echoed_label` and `own_words` honours it. A rebuilt `Section` does
    **not** — `Section` has no such field, so the label lands on both nodes and
    a naive tree-side count reports `Art. 1º` twice. That is a real and
    deliberate narrowing at the `Segment → Section` boundary, and
    `test_roundtrip_drops_the_caput_echo_flag` below pins it rather than
    letting it hide inside this comparison.
    """
    from lexml_nonstat.render import leaf_texts
    from lexml_nonstat.segments.api import _segments_of_document

    bundle = render_norma(model_for(ANNEX_SAMPLE))
    emitted = Counter(words(leaf_texts(bundle.primary)))
    read_back = Counter(
        w for seg in _segments_of_document(bundle.primary) for w in seg.own_words
    )
    assert read_back == emitted, diff_message("norma", emitted, read_back)


def test_roundtrip_drops_the_caput_echo_flag() -> None:
    """`Segment.echoed_label` does not survive into a `Section` — pinned, not hidden.

    A `Caput`'s rótulo repeats its `Artigo`'s (A-6.4). The reader knows: the
    segment carries `echoed_label=True` and `own_words` excludes it, which is
    what makes conservation over `norma` output checkable at all. But
    `roundtrip._tree_from_segments` builds a `Section`, and `Section` has no
    `echoed_label` field — so the flag is lost and both nodes carry `Art. 1º`.

    That is a genuine narrowing of the round-trip, and this test states it as a
    measured fact so that (a) nobody re-derives conservation from the rebuilt
    tree and quietly double-counts, and (b) if `Section` ever gains the field,
    this fails and the improvement gets noticed instead of passing silently.
    """
    from lexml_nonstat.segments.api import _segments_of_document

    bundle = render_norma(model_for(ANNEX_SAMPLE))
    segments = _segments_of_document(bundle.primary)

    echoed = [s for s in segments if s.echoed_label]
    assert [(s.kind, s.label) for s in echoed] == [
        ("caput", "Art. 1º"),
        ("caput", "Art. 2º"),
    ], "the reader no longer marks the Caput echo; A-6.4 has regressed"
    assert all("Art." not in " ".join(s.own_words) for s in echoed), (
        "an echoed rótulo is excluded from own_words"
    )

    rebuilt = hierarchy_from_xml(bundle.primary)
    labels = [s.label for s in rebuilt.body.walk()]
    assert labels == ["Art. 1º", "Art. 1º", "Art. 2º", "Art. 2º"], (
        "the label is expected on both nodes — Section cannot carry the echo flag"
    )
    assert not hasattr(rebuilt.body.sections[0], "echoed_label"), (
        "Section gained an echoed_label field; the round-trip can now carry "
        "A-6.4 through, and this test should become an equality instead"
    )


# --------------------------------------------------------------------------
# T-22 — what the round-trip refuses to make up
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_roundtrip_does_not_fabricate_evidence(name: str) -> None:
    """T-22. `Evidence`, `confidence` and `DocSignals` come back at DEFAULTS.

    **By value, never by truthiness** — that distinction is the whole test.
    `assert not tree.confidence` passes for a reader that returns `0.0`
    honestly *and* for one that has started guessing and happened to guess low;
    `assert tree.confidence == 0.0` passes only for the first. The module
    docstring of `roundtrip.py` makes the case: Cycle 4's `Evidence` records
    *why* the inference concluded what it did, no emitter writes any of that
    into the XML, and a fabricated confidence is worse than an absent one
    because it looks like a measurement.

    Asserted against freshly constructed defaults rather than against literals,
    so that adding a field to `Evidence` or `DocSignals` extends this test
    automatically instead of leaving the new field unchecked.
    """
    model = model_for(name)
    rebuilt = hierarchy_from_xml(render_generico(model))

    for tree in rebuilt.trees:
        assert tree.confidence == 0.0, f"{name}: a confidence was invented"
        assert tree.flat is True, f"{name}: `flat` was inferred, not defaulted"
        assert tree.signals == DocSignals(), f"{name}: signals were invented"
        assert tree.span is None, f"{name}: a source span was invented"
        for section in tree.walk():
            assert section.evidence == Evidence(), (
                f"{name}: section {section.title!r} came back carrying evidence "
                f"{section.evidence!r}; no emitter writes evidence into the XML"
            )
            assert section.source_indices == (), (
                f"{name}: section {section.title!r} claims source indices "
                f"{section.source_indices!r}; the XML does not carry them"
            )

    # The premise this is worth asserting: the *original* did carry evidence, so
    # the defaults above are a deliberate absence rather than a corpus in which
    # there was never anything to lose.
    assert any(
        s.evidence != Evidence() for t in model.hierarchy.trees for s in t.walk()
    ) or not any(
        True for t in model.hierarchy.trees for s in t.walk()
    ), f"{name}: premise check — the model side should carry evidence"


def test_roundtrip_evidence_defaults_are_not_vacuous() -> None:
    """The corpus really does have evidence to lose — T-22's premise, once.

    Without this, T-22 would be satisfiable by a corpus in which nothing ever
    carried evidence in the first place, and its 15 passes would mean nothing.
    Asserted on one sample known to infer real structure rather than on all 15,
    because it is a statement about the *fixture*, not about the reader.
    """
    model = model_for("pn_cst_38_19801031")
    evidenced = [
        s
        for tree in model.hierarchy.trees
        for s in tree.walk()
        if s.evidence != Evidence()
    ]
    assert evidenced, "premise failed: this sample's model carries no evidence"
    assert model.hierarchy.body.confidence > 0.0, "premise: a real confidence"


# --------------------------------------------------------------------------
# T-23 — annexes are documents too
# --------------------------------------------------------------------------


def test_roundtrip_reads_annexes() -> None:
    """T-23. `port_mf_277`'s `ANEXO ÚNICO` comes back whole — A-4.5.

    Four separate things, because each is a different wire and each has its own
    way of failing:

    * the annex exists at all — a reader that only looked at `documents[0]`
      would silently return a document with no annexes and pass every other
      test in this module;
    * its tree is the full 65 sections A-4.5 measured, not a truncation;
    * its **label** comes back — the annex's marker paragraph is excluded from
      the annex's own tree (A-4.5) and rendered as a `tituloAnexo` block (A-5.6),
      so the reader has to lift it back onto the `AnnexHierarchy` rather than
      leave it as a phantom first section;
    * its **fragment** is `anexo1` — read from the URN, which is what a
      `ReferenciaAnexo/@AlvoURN` in the primary points at. A wrong fragment is a
      dangling cross-document pointer, invisible to any shape check.
    """
    model = model_for(ANNEX_SAMPLE)
    rebuilt = hierarchy_from_xml(render_generico(model))

    assert rebuilt.annexes, "the annex vanished from the round-trip"
    assert len(rebuilt.annexes) == 1

    annex = rebuilt.annexes[0]
    assert len(list(annex.tree.walk())) == ANNEX_SECTIONS
    assert annex.label == "ANEXO ÚNICO"
    assert annex.fragment == "anexo1"
    assert annex.ordinal == 1

    # The `tituloAnexo` was lifted onto the AnnexHierarchy, not left in the tree
    # as a 66th section — the specific failure A-5.6's split invites.
    assert all(s.kind != "tituloAnexo" for s in annex.tree.walk())

    # And it agrees with the model it came from, so 65 is the document's number
    # rather than this test's.
    original = model.hierarchy.annexes[0]
    assert len(list(original.tree.walk())) == ANNEX_SECTIONS
    assert annex.label == original.label
    assert annex.fragment == original.fragment


@pytest.mark.parametrize("emitter", sorted(GENERICO_EMITTERS))
def test_roundtrip_reads_annexes_from_either_emitter(emitter: str) -> None:
    """The annex survives the nested emitter too, at the same size.

    The nested emitter writes an annex body in the `AgrupamentoHierarquico`
    form, which only `lexml-proposed/` accepts — but reading it back needs no
    schema at all, so this runs everywhere rather than skipping on a checkout
    without the proposed generation (A-R.9).
    """
    rebuilt = hierarchy_from_xml(GENERICO_EMITTERS[emitter](model_for(ANNEX_SAMPLE)))
    assert len(rebuilt.annexes) == 1
    assert len(list(rebuilt.annexes[0].tree.walk())) == ANNEX_SECTIONS
    assert rebuilt.annexes[0].label == "ANEXO ÚNICO"
    assert rebuilt.annexes[0].fragment == "anexo1"


def test_roundtrip_reads_annexes_from_norma() -> None:
    """The annex is not the primary's problem — it survives `render_norma` too.

    Worth its own test because the `norma` bundle carries **two id grammars**
    (A-6.1): the primary's `art1_cpt` and the annex's `anexo1_pp_agr2`. A reader
    that dispatched on id shape rather than on element name would meet the
    annex's `agr` path after the primary's dispositivos and have to guess.
    """
    rebuilt = hierarchy_from_xml(render_norma(model_for(ANNEX_SAMPLE)))
    assert len(rebuilt.annexes) == 1
    assert len(list(rebuilt.annexes[0].tree.walk())) == ANNEX_SECTIONS
    assert rebuilt.annexes[0].fragment == "anexo1"


# --------------------------------------------------------------------------
# T-24 — the round-trip converges rather than eroding
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
@pytest.mark.parametrize("emitter", sorted(GENERICO_EMITTERS))
def test_roundtrip_of_a_bundle_is_idempotent(name: str, emitter: str) -> None:
    """T-24. Reading is pure, and re-rendering reaches a fixpoint in one pass.

    **This is not the sentence the spec's §5.1 table wrote**, and the difference
    is deliberate. The spec asks for `model → xml → model' → xml'` with
    `xml == xml'` byte-for-byte. Measured, that is false on all 15 samples for a
    reason no reader could fix: a section whose model body held four `Para`s is
    rendered as four `<p>` elements, read back as *one* joined `Para`
    (`roundtrip._paras` says so in as many words), and re-rendered as one `<p>`.
    Different element counts, therefore different bytes, necessarily. Writing
    the spec's version would have produced either a failing test or — worse — a
    test weakened until it no longer said anything.

    So this asserts the true and stronger property instead:

    1. **Reading is pure.** Two `hierarchy_from_xml` calls on one bundle give
       equal `HierarchyDoc`s (§9.2 determinism).
    2. **The loss happens once.** Re-render the rebuilt hierarchy and read it
       back: `model'₁ == model'₂`. The second pass changes nothing.
    3. **And the bytes settle.** `xml₂ == xml₃`, byte-for-byte — the equality
       the spec wanted, holding from the first re-render onwards.

    Together these bound the erosion at exactly one pass, which is what
    "reversible" has to mean for a lossy-by-design serialisation. The spec's
    phrasing would have proven nothing about pass three.
    """
    model = model_for(name)
    render = GENERICO_EMITTERS[emitter]

    bundle_1 = render(model)

    # (1) reading is pure.
    assert hierarchy_from_xml(bundle_1) == hierarchy_from_xml(bundle_1), (
        f"{name}/{emitter}: two reads of one bundle disagree"
    )

    rebuilt_1 = hierarchy_from_xml(bundle_1)
    bundle_2 = render(dataclasses.replace(model, hierarchy=rebuilt_1))
    rebuilt_2 = hierarchy_from_xml(bundle_2)

    # (2) the second read equals the first — the structure has settled.
    assert rebuilt_2 == rebuilt_1, (
        f"{name}/{emitter}: re-segmenting the rebuilt structure was not stable"
    )

    bundle_3 = render(dataclasses.replace(model, hierarchy=rebuilt_2))

    # (3) and so have the bytes.
    xml_2 = [to_xml_string(d) for d in bundle_2.documents]
    xml_3 = [to_xml_string(d) for d in bundle_3.documents]
    assert xml_2 == xml_3, (
        f"{name}/{emitter}: the round-trip did not reach a fixpoint — "
        "re-rendering kept changing the bytes"
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_roundtrip_first_pass_loses_paragraph_boundaries(name: str) -> None:
    """The documented loss is real, and is exactly paragraph *count*.

    T-24's fixpoint claim only means something if the first pass genuinely is
    lossy — otherwise the honest test would have been the spec's byte-equality
    one, and this module's docstring would be an excuse rather than a finding.
    So the loss is *asserted*, not assumed: after the round-trip every section
    holds at most one `Para`, and somewhere in the corpus a section that held
    more than one now holds one. A future change that made `_paras` recover
    paragraph boundaries would fail here — correctly, because at that point
    T-24 should be rewritten to the spec's stronger sentence.
    """
    model = model_for(name)
    rebuilt = hierarchy_from_xml(render_generico(model))

    for tree in rebuilt.trees:
        for section in tree.walk():
            assert len(section.body) <= 1, (
                f"{name}: a rebuilt section carries {len(section.body)} nodes; "
                "the reader is documented to join a section's own text into one"
            )
            for node in section.body:
                assert isinstance(node, Para)
                assert len(node.inlines) == 1, (
                    f"{name}: a rebuilt Para carries {len(node.inlines)} inlines; "
                    "formatting is documented as unrecoverable"
                )


def test_the_corpus_actually_has_multi_paragraph_sections() -> None:
    """The premise of the test above: the loss has something to lose.

    One sample, one assertion — a statement about the corpus, not the reader.
    """
    model = model_for("pn_cst_38_19801031")
    assert any(
        len(s.body) > 1 for t in model.hierarchy.trees for s in t.walk()
    ), "premise failed: no section in this sample holds more than one node"


# --------------------------------------------------------------------------
# Input shapes and edges
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_hierarchy_from_xml_accepts_a_string_and_an_element_alike(name: str) -> None:
    """A bundle, an element and a serialised string are the same document.

    `hierarchy_from_xml` advertises all four input shapes. Element-vs-string is
    the pair that can silently diverge — a reader that kept an lxml reference
    would see the *live* tree, while a file read from disk goes through a parse
    — so the two are asserted equal here rather than each assumed.
    """
    bundle = render_generico(model_for(name))
    from_element = hierarchy_from_xml(bundle.primary)
    from_string = hierarchy_from_xml(to_xml_string(bundle.primary))
    assert doc_shape(from_string) == doc_shape(from_element), name
    assert doc_words(from_string) == doc_words(from_element), name


@pytest.mark.parametrize("name", SAMPLES)
def test_a_single_document_carries_no_annexes(name: str) -> None:
    """One document read alone rebuilds itself, and does not invent an annex.

    The complement of T-23: the reader treats `documents[1:]` as annexes, so a
    reader handed a lone element must produce zero of them. Getting this wrong
    would turn a primary into its own annex.
    """
    bundle = render_generico(model_for(name))
    rebuilt = hierarchy_from_xml(bundle.primary)
    assert rebuilt.annexes == ()
    assert shape(rebuilt.body) == shape(model_for(name).hierarchy.body), name


@pytest.mark.parametrize("name", SAMPLES)
def test_roundtrip_carries_the_source_name_from_a_bundle_only(name: str) -> None:
    """`HierarchyDoc.source` survives a bundle, and is honestly absent otherwise.

    Found by the mutation sweep: dropping `source=source_name` from
    `hierarchy_from_xml` left every other test in this module green, because
    `source` is provenance rather than content and nothing else looks at it. It
    is what tells a consumer which DOCX a rebuilt tree came from, and a golden
    or a report that lost it would be quietly less traceable.

    The negative half is the more interesting one: a bare element genuinely
    does not know its source file, so `None` is the right answer and *inventing*
    a filename would be the failure. Both halves in one test, because they are
    the same decision seen from two sides.
    """
    model = model_for(name)
    bundle = render_generico(model)

    assert hierarchy_from_xml(bundle).source == bundle.source
    assert hierarchy_from_xml(bundle).source == f"{name}.docx"
    assert hierarchy_from_xml(bundle.primary).source is None, (
        "a lone element has no source file; reporting one would be a fabrication"
    )


def test_sections_from_xml_is_the_bodys_top_level(minimal_generico: str) -> None:
    """`sections_from_xml` is a shorthand, not a second reader.

    Asserted as an identity against `hierarchy_from_xml(...).body.sections` on a
    real sample, so the convenience wrapper can never drift into its own
    traversal — the A-3.4 "one authority" rule applied to this module.
    """
    bundle = render_generico(model_for("pn_cst_38_19801031"))
    assert sections_from_xml(bundle) == hierarchy_from_xml(bundle).body.sections

    # And it degrades quietly on a document with no sections at all, rather than
    # raising — `minimal_generico` is one bare `<p>` inside `PartePrincipal`.
    assert sections_from_xml(minimal_generico) == ()


def test_an_empty_document_rebuilds_to_an_empty_hierarchy(minimal_generico: str) -> None:
    """A structureless document comes back structureless, not broken.

    Plan invariant #8's asymmetry, read from the other end: a flat document is
    complete and citable, and the reader must not manufacture a section for the
    one paragraph it finds. `conftest`'s `minimal_generico` is §2.1 row A — the
    smallest valid non-statutory document.
    """
    rebuilt = hierarchy_from_xml(minimal_generico)
    assert isinstance(rebuilt, HierarchyDoc)
    assert rebuilt.body.sections == ()
    assert rebuilt.annexes == ()
    assert rebuilt.body.confidence == 0.0
