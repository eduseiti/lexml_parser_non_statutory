"""The three-way oracle — plan §6.1, amendment **A-R.5**, invariant #11.

**One model, three derivations, one answer.** The in-process `HierarchyDoc`,
the flat `generico` XML and the nested `generico-aninhado` XML must segment
*identically*. Cycle 5b's `test_cross_emitter.py` compared the two emitters'
output; this compares the two emitters' output **and** the model that produced
them, which is what makes the agreement evidence rather than symmetry.

The three derivations really are independent, and that is the point:

* `segments_from_model` walks Cycle 4's tree and composes ids arithmetically.
  It parses no XML and calls no emitter.
* `segments_from_flat_xml` knows nothing about the model. It reconstructs
  ancestry from the **id path** (§2.3), depth from `Bloco nome="nivel"`.
* `segments_from_nested_xml` knows nothing about the model *or* about ids. It
  reconstructs ancestry from `AgrupamentoHierarquico` containment and order
  from `Bloco nome="ordem"`.

Three routes to the same tuple of segments. A bug in any one of them shows up
here as a disagreement, and a bug shared by all three would have to be a bug in
the model — which is Cycle 4's goldens' job, not this file's.

What is compared, and the one thing that is not
------------------------------------------------

Compared: `kind`, `level`, `label`, `heading`, `text`, `breadcrumb`, `order`
and `path`. **Not** compared: `urn`. Amendment **A-5b.4** measured that a flat
`urn` and a nested `urn` for the same section differ two ways — the id token
(`agr` vs `agh`) and a top-level ordinal offset — so requiring them equal would
require one emitter to be wrong. Plan §6.1's "segment URNs identical across
emitters" is met by `path`, which is the address a urn *denotes*; the urns
themselves are checked against the artifacts they came from, where each is
correct (amendment **A-7.2**).

`test_urns_differ_exactly_by_the_two_documented_notations` re-derives that
difference here rather than importing `test_cross_emitter`'s finding. Two
modules reaching the same measurement independently is worth more than one
module asserting it twice.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import (
    render_generico,
    render_generico_aninhado,
    render_norma,
    words,
)
from lexml_nonstat.segments import (
    segments,
    segments_from_flat_xml,
    segments_from_model,
    segments_from_nested_xml,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.name for p in SAMPLES_DIR.glob("*.docx"))

#: The one sample §4.4 routes to `norma`, and the corpus's only annex.
STATUTORY_SAMPLE = "port_mf_277_20180607.docx"

#: The fields the three derivations must agree on. `urn` is excluded for the
#: reason the module docstring gives at length — it is a notation, not the
#: address, and A-5b.4 measured that the notations differ.
COMPARED = ("kind", "level", "label", "heading", "text", "breadcrumb", "path", "order")

_MODELS: dict[str, object] = {}


def model_for(name: str):
    """One built model per sample, cached — building all 15 is not free."""
    if name not in _MODELS:
        path = SAMPLES_DIR / name
        _MODELS[name] = build_model(read_docx(path), filename=name)
    return _MODELS[name]


def compared(segment) -> tuple:
    return tuple(getattr(segment, field) for field in COMPARED)


def shape(rows) -> list[tuple]:
    return [compared(s) for s in rows]


@pytest.mark.parametrize("name", SAMPLES)
def test_three_way_agreement(name):
    """T-30 — model, flat XML and nested XML segment identically (A-R.5).

    The nested leg does **not** skip when `lexml-proposed/` is absent. Cycle
    5b's amendment A-5b.3 settled that the renderer always renders and only
    *validation* is capability-gated; this test reads the nested XML it just
    built, and reading needs no schema at all. Skipping it on a bare checkout
    would silently retire a third of the oracle on the configuration the plan
    (A-R.9) most wants green.
    """
    model = model_for(name)
    flat = render_generico(model)
    nested = render_generico_aninhado(model)

    from_model = segments_from_model(model, emitter="generico")
    from_flat = segments(flat)
    from_nested = segments(nested)

    assert shape(from_model) == shape(from_flat), "model and flat XML disagree"
    assert shape(from_flat) == shape(from_nested), "flat and nested XML disagree"


@pytest.mark.parametrize("name", SAMPLES)
def test_paths_are_identical_across_emitters(name):
    """T-31 — "a citation survives an emitter switch", in the form that is true.

    A consumer holding `path == (2, 3, 1)` finds the same section in flat and
    in nested output. That is the whole of plan §6.1's intent that survives
    A-5b.4's measurement, and it is asserted here at full strength: the tuples
    are equal element for element, in order, including the empty tuples the
    front and back regions carry.
    """
    model = model_for(name)
    flat_paths = [s.path for s in segments(render_generico(model))]
    nested_paths = [s.path for s in segments(render_generico_aninhado(model))]
    model_paths = [s.path for s in segments_from_model(model)]

    assert flat_paths == nested_paths == model_paths


@pytest.mark.parametrize("name", SAMPLES)
def test_urns_differ_exactly_by_the_two_documented_notations(name):
    """T-32 — the id difference is the two documented ones, and nothing else.

    Re-derived here rather than imported. For each *body* section the flat id
    and the nested id are compared component by component: every component but
    the first must differ only in its token spelling (`agr` → `agh`), and the
    first must additionally differ by a constant offset equal to the number of
    front-matter regions. A third kind of drift — a renumbering, a reordering,
    a lost level — fails this even though the set comparison in
    `test_paths_are_identical_across_emitters` might survive it.
    """
    import re

    model = model_for(name)
    flat_all = segments(render_generico(model))
    nested_all = segments(render_generico_aninhado(model))

    # Per *document*: the primary and each annex have their own id root
    # (`pp1`, `anexo1_pp`) and their own region count, so the offset is a
    # per-document quantity. Measuring it once for the bundle would silently
    # apply the primary's offset to the annex — which on `port_mf_277` is the
    # difference between `anexo1_pp_agr2` and `anexo1_pp_agh1`.
    for document_urn in dict.fromkeys(s.document for s in flat_all):
        flat = [s for s in flat_all if s.document == document_urn]
        nested = [s for s in nested_all if s.document == document_urn]

        # Only the regions written *before* the body shift it: the back
        # regions use the `agrf` token and follow the body (A-5.1).
        leading = 0
        for segment in flat:
            if not segment.is_region:
                break
            if re.search(r"_agr\d+$", segment.id):
                leading += 1

        body_flat = [s for s in flat if not s.is_region]
        body_nested = [s for s in nested if not s.is_region]
        assert len(body_flat) == len(body_nested)

        for f, n in zip(body_flat, body_nested):
            f_parts = f.id.split("_")
            n_parts = n.id.split("_")
            assert len(f_parts) == len(n_parts), f"{f.id} vs {n.id}: different depth"

            # The id root is shared: only the body components are renamed.
            root_len = len(f_parts) - _body_depth(f_parts)
            assert f_parts[:root_len] == n_parts[:root_len]

            # First body component: token rename *plus* the offset.
            f_head = re.fullmatch(r"agr(\d+)", f_parts[root_len])
            n_head = re.fullmatch(r"agh(\d+)", n_parts[root_len])
            assert f_head and n_head, f"unexpected token in {f.id} / {n.id}"
            assert int(f_head.group(1)) == int(n_head.group(1)) + leading, (
                f"{f.id} vs {n.id}: offset is not the {leading} leading regions"
            )

            # Deeper components: token rename only, same ordinal.
            for f_part, n_part in zip(f_parts[root_len + 1 :], n_parts[root_len + 1 :]):
                assert f_part.replace("agr", "") == n_part.replace("agh", ""), (
                    f"{f.id} vs {n.id}: ordinals differ below the top level"
                )


def _body_depth(parts: list[str]) -> int:
    """How many trailing components of an id are body-section ordinals.

    `pp1_agr4_agr1` has two; `anexo1_pp_agr2` has one, because `anexo1_pp` is
    the annex's id **root**, not a section. Counting from the end rather than
    assuming a root of `pp1` is what lets one assertion cover both documents.
    """
    import re as _re

    depth = 0
    for part in reversed(parts):
        if _re.fullmatch(r"(agr|agh)\d+", part):
            depth += 1
        else:
            break
    return depth


@pytest.mark.parametrize("name", SAMPLES)
def test_every_urn_resolves_in_the_artifact_it_came_from(name):
    """A urn is only worth having if it points at something.

    The complement of T-31: `path` is the portable address, and `urn` is the
    one that *resolves*. Each segment's id half must select exactly one element
    in the document its `document` names — no more (a duplicate id) and no
    fewer (a urn for an element the emitter never wrote).
    """
    model = model_for(name)
    for bundle in (render_generico(model), render_generico_aninhado(model)):
        by_urn = {}
        for document in bundle.documents:
            identificacao = document.find(
                ".//{http://www.lexml.gov.br/1.0}Identificacao"
            )
            by_urn[identificacao.get("URN")] = document

        for segment in segments(bundle):
            document = by_urn[segment.document]
            found = [
                element
                for element in document.iter()
                if element.get("id") == segment.id
            ]
            assert len(found) == 1, f"{segment.urn} selects {len(found)} elements"


@pytest.mark.parametrize("name", SAMPLES)
def test_segments_conserve_the_source_text(name):
    """Invariant #2, stated over segments rather than over XML.

    The currency is `Segment.own_words` — label, heading and text — because
    `label` and `heading` are source words the emitters write into the markup;
    a check over `text` alone would report every rótulo in the corpus as lost.
    An **echoed** label is excluded, which is amendment A-6.4's rule applied
    one layer out: a `Caput` repeats its `Artigo`'s rótulo, and the source said
    it once.

    Exact equality both ways: no word lost, and — the half a naive
    implementation fails — no word gained.
    """
    model = model_for(name)
    for bundle in (render_generico(model), render_generico_aninhado(model)):
        from_segments = Counter(w for s in segments(bundle) for w in s.own_words)
        from_xml = Counter(words(bundle.texts))
        assert from_segments == from_xml, (
            f"{bundle.emitter}: "
            f"lost {sum((from_xml - from_segments).values())}, "
            f"gained {sum((from_segments - from_xml).values())}"
        )


def test_norma_and_generico_agree_on_text():
    """T-33 — the statutory rendering says the same words as the flat one.

    §4.2's fallback means one document can legitimately be published either
    way, so the two must carry the same content. They do not carry the same
    *structure* — that is the whole difference between the routes — so this
    compares the word multiset and nothing else.
    """
    model = model_for(STATUTORY_SAMPLE)
    statutory = Counter(w for s in segments(render_norma(model)) for w in s.own_words)
    flat = Counter(w for s in segments(render_generico(model)) for w in s.own_words)
    assert statutory == flat


def test_port_mf_277_segments_span_primary_and_annex():
    """T-34 — the split is a split, not an amputation (plan Cycle 7).

    `port_mf_277`'s `ANEXO ÚNICO` is a **standalone sibling document** (§2.9)
    carrying 65 of the document's sections. A segmenter that read only the
    primary would report a five-segment document and lose the part a user
    actually cites.
    """
    model = model_for(STATUTORY_SAMPLE)
    for bundle in (
        render_generico(model),
        render_generico_aninhado(model),
        render_norma(model),
    ):
        rows = segments(bundle)
        primary = [s for s in rows if s.document == model.metadata.urn]
        annex = [s for s in rows if s.document.endswith("!anexo1")]
        assert primary, f"{bundle.emitter}: no primary segments"
        assert len(annex) >= 65, f"{bundle.emitter}: {len(annex)} annex segments"


@pytest.mark.parametrize("name", SAMPLES)
def test_the_three_derivations_are_not_the_same_code(name):
    """Anti-vacuity: the oracle must not agree because it asked once.

    An agreement test is worthless if the three producers share the traversal
    that decides the answer. They do not — and the cheapest proof is that they
    disagree the moment they are given different *inputs*: segmenting the flat
    document with the nested reader (or the reverse) yields a different result
    on any sample that actually nests, because each reader looks for a
    different element.

    Six of the sixteen documents contain no `AgrupamentoHierarquico` at all
    (A-5b.5) — they are pure front and back matter — so on those the two
    readers legitimately agree, and the assertion is conditional on the
    document nesting. Pinning that condition is the point: it is the same
    measurement A-5b.5 records, arrived at from the reading side.
    """
    model = model_for(name)
    nested_bundle = render_generico_aninhado(model)
    document = nested_bundle.primary

    nests = (
        document.find(".//{http://www.lexml.gov.br/1.0}AgrupamentoHierarquico")
        is not None
    )
    correct = segments_from_nested_xml(document)
    wrong = segments_from_flat_xml(document)

    if nests:
        assert shape(correct) != shape(wrong), (
            "the flat reader found the nested tree — the readers share a path"
        )
    else:
        assert shape(correct) == shape(wrong)
