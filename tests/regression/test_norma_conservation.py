"""Conservation and the fallback gate on the statutory route — §9.2, §4.2.

The flat route's conservation is asserted sample by sample in
`test_conservation_generico.py`. This module is the statutory twin, and it
exists because the `norma` emitter breaks conservation in ways the `generico`
emitter structurally cannot:

* it renders **named parts** — `Epigrafe`, `Ementa`, `Preambulo`, `Assinatura` —
  out of a closed content model, so any source block that fits none of them has
  nowhere to go. `generico` has an `Agrupamento` for everything; `Norma` does
  not, and A-6.2 is the whole design consequence;
* it **rewrites the body** into `Artigo`/`Caput`/`Paragrafo`/`Inciso` rather
  than transcribing it. A builder that mis-reads a label does not raise — it
  silently absorbs a paragraph into the wrong dispositivo, or drops it;
* it carries **two id grammars** in one bundle: the primary's `art1_cpt` and the
  annex's `anexo1_pp_agr2` (A-6.1). Two independent allocators sharing one
  `xsd:ID` space is a collision waiting for the document that triggers it.

Which is why §4.2's gate is not "validate and publish". A schema cannot see lost
text: a `Norma` that dropped a paragraph is a perfectly valid `Norma`. So the
gate is validity **and** conservation **and** coverage **and** back-matter
placement, four named blockers, and the emitter falls back to `generico` rather
than publishing a document that says something different from the one it was
given (A-6.3).

**Testing a fallback requires forcing it.** The corpus cannot: `port_mf_277` is
the only norma-routed sample and it passes all four gates cleanly — zero front
residue, zero back residue, coverage 1.0, valid, conserving. A gate that never
fires on any input is indistinguishable from a gate that is not wired up, so
each of the four is provoked here, two by `monkeypatch` against the module's own
seams and two by a model edited into the shape that trips them. Every one
asserts three things together — the blocker code, the emitter that actually came
back, and the `WARN` in the log — because those are three separate wires and
each has failed independently in this codebase's history.

**The currency is a multiset of words**, as in the flat module and for the same
reason: a source paragraph legitimately becomes two elements — an `Artigo`'s
`Rotulo` and the `<p>` carrying the prose that followed it on the same line — so
comparing whole paragraphs would report a false loss on every article.

Two exclusions are pinned here rather than assumed, because both are places
where "conserved" and "emitted" deliberately part company:

* `Bloco nome="nivel"` — a depth marker whose value was never in the source;
* a `Caput`'s `Rotulo`, which repeats its `Artigo`'s. Plan §4.3's snippet writes
  the rótulo twice and the reference parser does too (D-3), but the *source*
  said it once. Counting both copies would report a word the document never
  said twice, and `test_caput_rotulo_echo_is_excluded_exactly_once` is what
  makes that exclusion a measured claim rather than a comment (A-6.4).
"""

from __future__ import annotations

import dataclasses
import logging
from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc, StyledPara, StyledTable, read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import norma as norma_module
from lexml_nonstat.render import (
    all_ids,
    leaf_texts,
    local_name,
    render_generico,
    render_norma,
    render_norma_checked,
    render_statutory,
    words,
)
from lexml_nonstat.routing.viability import BLOCKER_CODES, Blocker
from lexml_nonstat.segment.model import Span

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

LEX = "{http://www.lexml.gov.br/1.0}"

#: The one statutory sample. Everything about the `norma` route that the corpus
#: can say, it says through this document.
NORMA_SAMPLE = "port_mf_277_20180607"

#: The logger the §4.2 gate writes its refusals to. Named here rather than
#: passed to `caplog.set_level` inline, so a rename breaks one line.
GATE_LOGGER = "lexml_nonstat.render.norma"

assert len(SAMPLES) == 15, SAMPLES
assert NORMA_SAMPLE in SAMPLES

_CACHE: dict[str, object] = {}


def model(name: str = NORMA_SAMPLE):
    """One sample's `DocumentModel`, built once per session."""
    if name not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        _CACHE[name] = build_model(read_docx(path), filename=path.name)
    return _CACHE[name]


def source_doc(name: str = NORMA_SAMPLE) -> StyledDoc:
    key = f"doc:{name}"
    if key not in _CACHE:
        _CACHE[key] = read_docx(SAMPLES_DIR / f"{name}.docx")
    return _CACHE[key]  # type: ignore[return-value]


def source_texts(doc: StyledDoc) -> list[str]:
    """Every piece of text Cycle 1's reader saw — paragraphs and table cells.

    Identical to the flat module's reader, deliberately: the two routes must be
    measured against the *same* notion of "the source", or a difference between
    them would be a difference between two definitions rather than between two
    emitters.
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


def source_words(doc: StyledDoc) -> Counter:
    return Counter(words(source_texts(doc)))


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


def codes(blockers) -> list[str]:
    return [b.code for b in blockers]


# --------------------------------------------------------------------------
# Conservation across the statutory split
# --------------------------------------------------------------------------


def test_primary_plus_annex_conserve_all_source_text():
    """`port_mf_277`: primary ∪ annex == the source, word for word.

    Plan bullet 4 and exit criterion E-4. The statutory route is where this is
    hardest: the primary keeps three front-matter parts, two articles and a
    signature, while 132 blocks of `ANEXO ÚNICO` leave for a sibling document —
    and neither file is wrong on its own if a block falls between them.

    Addition makes this a disjointness test as well as a completeness one. A
    word the source has once, emitted defensively into *both* documents, makes
    the sum exceed the source and fails the equality; a word emitted into
    neither fails it the other way. The anchors below then say which end of the
    split each side owns, so a failure points at a document rather than at a
    total.
    """
    doc = source_doc()
    bundle = render_norma(model())

    assert bundle.emitter == "norma"
    assert len(bundle.annexes) == 1

    primary = Counter(words(leaf_texts(bundle.primary)))
    annex = Counter(words(leaf_texts(bundle.annexes[0])))
    source = source_words(doc)

    assert primary and annex, "both documents must carry text"
    assert primary + annex == source, diff_message(
        NORMA_SAMPLE, source, primary + annex
    )

    # Anchors: the epigraph belongs to the primary, the annex title to the annex.
    primary_texts = leaf_texts(bundle.primary)
    annex_texts = leaf_texts(bundle.annexes[0])
    assert any(t.startswith("Portaria MF") for t in primary_texts)
    assert "ANEXO ÚNICO" in annex_texts
    assert "ANEXO ÚNICO" not in primary_texts


def test_no_word_appears_twice():
    """Multiset equality in both directions — invariant #2, stated whole.

    "Nothing lost" and "nothing duplicated" are one assertion, and separating
    them is what makes a failure diagnosable. The set-level halves are checked
    as well as the multiset one because the two fail differently: a set-level
    miss means a whole block went missing (a vocabulary only one side has),
    while a multiset-only miss means a block was rendered the wrong *number* of
    times — which on this route is the likelier bug, since `Caput` echoes its
    `Artigo`'s rótulo and the emitter has to not count the echo.
    """
    doc = source_doc()
    bundle = render_norma(model())

    source = source_words(doc)
    emitted = Counter(words(bundle.texts))

    assert emitted == source, diff_message(NORMA_SAMPLE, source, emitted)

    missing = sorted(set(source) - set(emitted))
    unexpected = sorted(set(emitted) - set(source))
    assert not missing, f"source words never emitted: {missing[:10]}"
    assert not unexpected, f"emitted words with no source: {unexpected[:10]}"


def test_caput_rotulo_echo_is_excluded_exactly_once():
    """`Caput/Rotulo` repeats its `Artigo`'s and is counted once — A-6.4.

    D-3 has the emitter write the rótulo twice: once on the `Artigo`, once on
    its `Caput`. Plan §4.3's snippet does it, the reference parser does it, and
    it is valid — but the *source* wrote `Art. 1º` once, so extraction must read
    one of the two copies and not both.

    That exclusion is load-bearing for every conservation assertion above, and
    "excluded" is only trustworthy if it is also **exact**. This pins both
    halves: the echo really is present in the document (or the exclusion is
    guarding nothing and the tests above pass vacuously), and removing the
    `Caput`'s copies from the tree changes the extracted words not at all —
    which is only true if `leaf_texts` was already skipping precisely those and
    nothing else.
    """
    import copy

    bundle = render_norma(model())

    artigos = list(bundle.primary.iter(f"{LEX}Artigo"))
    assert artigos, "the sample must render articles, or this test is vacuous"

    for artigo in artigos:
        artigo_rotulo = artigo.find(f"{LEX}Rotulo")
        caput = artigo.find(f"{LEX}Caput")
        assert artigo_rotulo is not None and caput is not None
        caput_rotulo = caput.find(f"{LEX}Rotulo")
        assert caput_rotulo is not None, "D-3: a Caput carries its own Rotulo"
        assert caput_rotulo.text == artigo_rotulo.text, (
            "the Caput's rótulo is an echo; if it ever carries different text "
            "it is source text and excluding it becomes a conservation hole"
        )

    before = Counter(words(leaf_texts(bundle.primary)))

    stripped = copy.deepcopy(bundle.primary)
    removed = 0
    for caput in stripped.iter(f"{LEX}Caput"):
        rotulo = caput.find(f"{LEX}Rotulo")
        if rotulo is not None:
            caput.remove(rotulo)
            removed += 1

    assert removed == len(artigos)
    after = Counter(words(leaf_texts(stripped)))

    assert before == after, (
        f"removing the Caput rótulo echoes changed the extracted words by "
        f"{list((before - after).items())[:10]} — leaf_texts is not excluding "
        f"exactly the echo (A-6.4)"
    )


def test_norma_and_generico_bundles_carry_the_same_words():
    """The two emitters, one model, the same words — §9.2 and the gate's premise.

    Invariant #11 across the route boundary. It matters twice over. As an
    equivalence it says the statutory rendering is a *rendering* and not an
    editorial act: `Art. 1º` becomes a `Rotulo` on the norma route and a
    `Bloco nome="rotulo"` on the generic one, and nothing else changes.

    And as a premise it underwrites the gate itself. `_conservation_blocker`
    compares the statutory bundle against the **generic** one rather than
    against the source, on the grounds that the generic render's conservation is
    already asserted for all 15 samples. That reasoning is only sound if the two
    really do agree here — so this test is what stops the gate from being
    calibrated against a reference that had itself drifted.

    Both are rendered from one `DocumentModel`, so a model-level difference
    cannot hide inside an emitter-level one.
    """
    shared = model()
    statutory = render_norma(shared)
    generic = render_generico(shared)

    assert statutory.emitter == "norma"
    assert generic.emitter == "generico"

    statutory_words = Counter(words(statutory.texts))
    generic_words = Counter(words(generic.texts))

    assert statutory_words, "the statutory bundle must carry text"
    assert statutory_words == generic_words, diff_message(
        NORMA_SAMPLE, generic_words, statutory_words
    )

    # The documents are genuinely different, so the equality is about content
    # rather than about the two emitters having collapsed into one.
    assert statutory.to_xml_string() != generic.to_xml_string()
    assert list(statutory.primary.iter(f"{LEX}Articulacao"))
    assert not list(generic.primary.iter(f"{LEX}Articulacao"))


def test_ids_unique_across_the_bundle():
    """No `xsd:ID` collides, in either document or between them — invariant #5.

    The statutory bundle is the one place in this codebase where **two
    independent id allocators** write into one artifact: `DispositivoIds` issues
    `art1`, `art1_cpt` under the schema's `idArtigo` pattern, while the annex's
    `IdAllocator` issues `anexo1_pp_agr2` down a composed path (A-6.1). They are
    argued never to meet — a `Norma` primary has no `Agrupamento`, an annex has
    no dispositivo — and this is that argument checked rather than trusted.

    Per-document uniqueness is what `xsd:ID` actually requires and is asserted
    first. Cross-document uniqueness is stricter than the schema demands and is
    asserted anyway, because a consumer that loads the primary and its annex
    together — the normal way to read a document with an annex — needs the union
    to be addressable, and two `pp1`s would make it not.
    """
    bundle = render_norma(model())

    for position, document in enumerate(bundle.documents):
        where = "primary" if position == 0 else f"annex {position}"
        idents = all_ids(document)
        duplicates = [i for i, n in Counter(idents).items() if n > 1]
        assert not duplicates, f"{where}: duplicate xsd:ID {duplicates[:10]}"

    everything = list(bundle.ids)
    duplicates = [i for i, n in Counter(everything).items() if n > 1]
    assert not duplicates, (
        f"ids collide across the split: {duplicates[:10]} — the two allocators "
        f"(A-6.1) are meeting where they were argued not to"
    )

    # And the two grammars really are both present, or the test proves nothing.
    assert "art1" in everything and "art1_cpt" in everything
    assert any(i.startswith("anexo1_pp_agr") for i in everything)


# --------------------------------------------------------------------------
# §4.2 — the four gates, each forced
# --------------------------------------------------------------------------


def test_fallback_on_forced_invalid_render(monkeypatch, caplog):
    """An invalid statutory render falls back and says so — plan bullet 6.

    The gate's first duty. `render_articulacao` is monkeypatched to stamp a
    **path-composed** id — `pp1_art1`, Cycle 5's grammar — onto the first
    `Artigo`. That is not an arbitrary corruption: it is precisely the mistake
    A-6.1 exists to prevent, the one a developer makes by reaching for the
    `IdAllocator` that every other emitter uses, and both shipped schemas reject
    it on the `idArtigo` pattern.

    Three assertions, because they are three independent wires: the blocker
    carries the right *code*, the bundle that comes back says
    `emitter == "generico"` so the fallback is visible in the artifact and not
    only in the log, and the reason is logged at `WARN` so an operator running a
    batch of 300 sees it go by.
    """
    original = norma_module.render_articulacao

    def with_illegal_id(articulacao):
        element = original(articulacao)
        if element is not None:
            for node in element.iter():
                if node.get("id") == "art1":
                    node.set("id", "pp1_art1")
        return element

    monkeypatch.setattr(norma_module, "render_articulacao", with_illegal_id)

    _, blockers = render_norma_checked(model())
    assert codes(blockers) == [norma_module.BLOCKER_INVALID]
    assert "pp1_art1" in blockers[0].detail, (
        "the blocker must name what the schema rejected, or it is a log line "
        "nobody can act on"
    )

    with caplog.at_level(logging.WARNING, logger=GATE_LOGGER):
        result = render_statutory(model())

    assert result.emitter == "generico", (
        "the artifact must say which emitter produced it (§3.2)"
    )
    assert not list(result.primary.iter(f"{LEX}Norma"))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "the refusal must be logged at WARN"
    assert norma_module.BLOCKER_INVALID in warnings[0].getMessage()


def test_fallback_on_forced_text_loss(monkeypatch, caplog):
    """A *valid* render that lost a paragraph still falls back — A-6.3.

    This is the gate's reason for existing. The builder is patched to drop the
    first article's caput prose; the result is a completely well-formed `Norma`
    that both schemas accept, because **no schema can detect lost text**. Under
    a validity-only gate it would publish — a document that says something
    different from the one it was given, which invariant #2 forbids outright.

    The validity of the mutilated render is asserted explicitly, not assumed,
    because that is the entire premise: if a dropped paragraph happened to make
    the document invalid, this test would be re-testing the previous gate and
    A-6.3's argument would be untested.
    """
    original = norma_module.build_articulacao

    def dropping_a_paragraph(m):
        artigos = original(m)
        if not artigos:
            return artigos
        first = artigos[0]
        assert first.caput.paragraphs, "the fixture needs prose to drop"
        return (
            dataclasses.replace(
                first, caput=dataclasses.replace(first.caput, paragraphs=())
            ),
            *artigos[1:],
        )

    monkeypatch.setattr(norma_module, "build_articulacao", dropping_a_paragraph)

    rendered, blockers = render_norma_checked(model())

    # The premise: what was rendered is *valid*, and lossy anyway.
    from lexml_nonstat.validate.schema import SHIPPED, load_schemas

    for name, schema in load_schemas(generation=SHIPPED).items():
        assert schema.validate(rendered.primary), (
            f"{name} rejected the mutilated render, so this test is exercising "
            f"the validity gate rather than the conservation one"
        )

    assert codes(blockers) == [norma_module.BLOCKER_LOSSY]
    assert "missing" in blockers[0].detail

    with caplog.at_level(logging.WARNING, logger=GATE_LOGGER):
        result = render_statutory(model())

    assert result.emitter == "generico"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings
    assert norma_module.BLOCKER_LOSSY in warnings[0].getMessage()

    # And the fallback conserves what the statutory render would have dropped.
    assert Counter(words(result.texts)) == source_words(source_doc())


def test_fallback_on_back_matter_residue(caplog):
    """Back matter with no legal home refuses the route — A-6.2.

    `ParteFinal` is a closed sequence of `LocalDataFecho` and `Assinatura`: an
    extra `<p>` inside `Assinatura` is rejected, a childless
    `AgrupamentoHierarquico` is rejected, and `Agrupamento` is rejected outright.
    So unlike front residue — which folds into `Preambulo`, a `textoSimplesType`
    that takes several `<p>` — back residue has **nowhere legal to go**, and the
    only two options are dropping it or falling back. A-6.2 chooses falling
    back: text is never dropped to keep a route.

    `port_mf_277` has zero back residue, so the situation is synthesised by
    widening `BackMatter.trailing` over blocks that no signature claims. That is
    the real mechanism rather than a mock — `trailing` exists exactly to extend
    the back region over closing notes (`par_cosit_26`'s `Nota Normas:`,
    `port_mf_454`'s publication note), and those samples are why documents in
    the unseen 300 will carry it.
    """
    base = model()
    back = dataclasses.replace(base.segmentation.back, trailing=Span(3, 5))
    segmentation = dataclasses.replace(base.segmentation, back=back)
    mutated = dataclasses.replace(base, segmentation=segmentation)

    residue = norma_module.back_residue(mutated)
    assert residue, "the fixture must actually produce residue"
    assert norma_module.back_residue(base) == (), (
        "the real sample has none, which is why this has to be synthesised"
    )

    _, blockers = render_norma_checked(mutated)
    assert norma_module.BLOCKER_BACK_RESIDUE in codes(blockers)

    blocker = next(
        b for b in blockers if b.code == norma_module.BLOCKER_BACK_RESIDUE
    )
    assert residue[0][:20] in blocker.detail, (
        "the blocker must quote what could not be placed — a caller inspecting "
        "it deserves to see the text, not just a count"
    )

    with caplog.at_level(logging.WARNING, logger=GATE_LOGGER):
        result = render_statutory(mutated)

    assert result.emitter == "generico"
    assert any(
        norma_module.BLOCKER_BACK_RESIDUE in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


def test_fallback_on_low_coverage(caplog):
    """An articulation covering too little of the body refuses the route — §4.2.

    Cycle 4b's existing `low_coverage` blocker, reused rather than reinvented:
    §4.2's gate is three conditions and this is the third, and a second coverage
    threshold living in the emitter would be the competing source of truth
    A-3.4 refused. `COVERAGE_MIN` is imported rather than written as `0.6`, so
    retuning the threshold cannot leave this test asserting the old one.

    The fixture edits the model's *viability* rather than its body, which is the
    honest way to test this gate: coverage is Cycle 4b's measurement, and
    mangling the body to depress it would test the measurement instead of the
    gate that reads it.
    """
    from lexml_nonstat.routing.coverage import COVERAGE_MIN
    from lexml_nonstat.routing.viability import BLOCKER_LOW_COVERAGE

    base = model()
    assert base.viability.coverage >= COVERAGE_MIN, (
        "the real sample passes this gate, which is why it must be forced"
    )

    viability = dataclasses.replace(base.viability, coverage=COVERAGE_MIN / 2)
    mutated = dataclasses.replace(base, viability=viability)

    _, blockers = render_norma_checked(mutated)
    assert codes(blockers) == [BLOCKER_LOW_COVERAGE]

    with caplog.at_level(logging.WARNING, logger=GATE_LOGGER):
        result = render_statutory(mutated)

    assert result.emitter == "generico"
    assert any(
        BLOCKER_LOW_COVERAGE in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


# --------------------------------------------------------------------------
# The route boundary, and the blocker vocabulary
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", [s for s in SAMPLES if s != NORMA_SAMPLE])
def test_generico_routed_samples_never_render_norma(name):
    """The 14 non-statutory samples come back generic — §4.4, and A-R.6's lesson.

    "Statutory detection's main job is refusing false positives", and building
    an articulation a source does not have is the sin that got Cycle 6b
    withdrawn. `render_statutory` is the public entry point for *every*
    document, so a routing regression that promoted a parecer to `Norma` would
    reach the artifact through here — and the parecer would come out with two
    thirds of its numbered paragraphs rewritten as articles.

    Asserted at three depths, because a fallback can fail at any of them: the
    bundle's declared emitter, the absence of any `Norma` element in the
    artifact, and conservation of the source's words — the last so a fallback
    that fired but returned a damaged bundle is not mistaken for a clean refusal.
    """
    document = model(name)
    assert document.route == "generico"

    result = render_statutory(document)

    assert result.emitter == "generico", (
        f"{name}: routed generico but rendered as {result.emitter}"
    )
    assert not list(result.primary.iter(f"{LEX}Norma"))
    assert not list(result.primary.iter(f"{LEX}Articulacao"))

    emitted = Counter(words(result.texts))
    source = source_words(source_doc(name))
    assert emitted == source, diff_message(name, source, emitted)


def test_blocker_codes_are_all_declared():
    """Every code this route can emit is in `BLOCKER_CODES` — Cycle 4b's rule.

    "A blocker nobody can name is a blocker nobody will fix." `routing.viability`
    owns the vocabulary; `render/norma.py` re-exports from it rather than
    declaring its own constants, and this is that arrangement checked from the
    outside — a code invented locally would pass every other test in this module
    while being unnameable by any verdict, untranslatable in telemetry, and
    invisible to the CLI.

    The identity assertions matter as much as the membership one: a module-local
    `BLOCKER_INVALID = "statutory_invalid"` would satisfy `in BLOCKER_CODES` by
    coincidence and drift the moment either side was renamed.
    """
    from lexml_nonstat.routing import viability

    exported = {
        norma_module.BLOCKER_INVALID,
        norma_module.BLOCKER_LOSSY,
        norma_module.BLOCKER_BACK_RESIDUE,
    }
    assert exported <= set(BLOCKER_CODES), (
        f"undeclared blocker code(s): {sorted(exported - set(BLOCKER_CODES))}"
    )

    # Re-exported, not redeclared — the same objects, not merely equal strings.
    assert norma_module.BLOCKER_INVALID is viability.BLOCKER_STATUTORY_INVALID
    assert norma_module.BLOCKER_LOSSY is viability.BLOCKER_STATUTORY_LOSSY
    assert norma_module.BLOCKER_BACK_RESIDUE is viability.BLOCKER_BACK_RESIDUE

    # And every blocker the gate actually produces, across every forced path
    # exercised in this module, is a declared code carrying a real reason.
    produced: list[Blocker] = []
    base = model()

    back = dataclasses.replace(base.segmentation.back, trailing=Span(3, 5))
    produced.extend(
        render_norma_checked(
            dataclasses.replace(
                base, segmentation=dataclasses.replace(base.segmentation, back=back)
            )
        )[1]
    )
    produced.extend(
        render_norma_checked(
            dataclasses.replace(
                base, viability=dataclasses.replace(base.viability, coverage=0.0)
            )
        )[1]
    )

    assert produced, "no blocker was produced, so nothing was checked"
    for blocker in produced:
        assert blocker.code in BLOCKER_CODES, blocker.code
        assert blocker.detail.strip(), f"{blocker.code} carries no reason"
        assert blocker.vetoes, (
            f"{blocker.code} must veto: §4.2's gates all refuse the route, and "
            f"a non-vetoing one would be silently ignored by the fallback"
        )
