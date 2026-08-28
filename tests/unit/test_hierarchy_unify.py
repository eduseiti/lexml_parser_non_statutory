"""Level unification: one depth scale out of a document's several numberings.

A Brazilian parecer does not number itself in one system. ``pn_cst_38`` runs
``2.`` → ``2.3`` → ``2.3.1``, drops into ``I``/``II``/``III``, drops again into
``a)``/``b)``, then climbs back to ``2.3.3``. Every one of those transitions has
to land on the right depth, and **no schema will catch it if it does not** —
a section nested one level too deep is perfectly valid LexML and perfectly
wrong. That is why this file pins depth sequences on real samples rather than
trusting the tree tests downstream.

Three kinds of test live here, and they protect different things:

* **depth sequences on real samples** — the anchoring rules, in the documents
  that motivated them;
* **rejections** — every refusal must reach the caller as a *readable reason*,
  because a rule whose rejections are invisible cannot be audited (plan
  invariant #10 and Cycle 4b's telemetry);
* **synthetic guards** — the negative half of each rule, expressed in fixtures
  the 15-sample corpus cannot produce. The corpus stands in for 300+ unseen
  documents, so a rule tested only where it fires is a rule tuned to the corpus.

Depths are asserted through ``Label.canonical``, which is the rótulo without its
separator: the document's ``2.`` and ``2.1 -`` canonicalise to ``"2"`` and
``"2.1"``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from lexml_nonstat.hierarchy import infer_hierarchy
from lexml_nonstat.hierarchy.evidence import (
    CONFIDENCE_THRESHOLD,
    W_LABEL_SERIES,
    W_LABEL_SOLO,
    W_STYLE,
    W_UNIT_SERIES,
    DocSignals,
    document_confidence,
)
from lexml_nonstat.hierarchy.labels import Label
from lexml_nonstat.hierarchy.quotation import QuotationAnalysis, analyse_quotation
from lexml_nonstat.hierarchy.unify import (
    MIN_DEMOTION_RUN,
    MIN_UNIT_SERIES,
    Assignment,
    Candidate,
    collect_candidates,
    demote_numbered_containers,
    detect_unit_series,
    section_kind,
    style_level,
    unify_levels,
    validate_top_series,
)
from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara, StyledTable, read_docx
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.model.nodes import Evidence, SECTION_KINDS
from lexml_nonstat.segment import segment_document

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"

#: Every sample in the corpus. Fifteen documents standing in for 300+ unseen
#: ones — a rule that needs all fifteen named is a rule tuned to the corpus.
SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

PN_CST_38 = "pn_cst_38_19801031"
PORT_MF_454 = "port_mf_454_19770825"
ADN_CST_10 = "adn_cst_10_19910417"
PARECER_93 = "parecer_93_2018_decor_cgu_agu"
PORT_MF_277 = "port_mf_277_20180607"
SUMULA_STJ = "sumula_stj_125"
CARNE_LEAO = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"


def test_corpus_is_the_expected_fifteen():
    """Guards every parametrisation below against a sample being added or lost."""
    assert len(SAMPLES) == 15, SAMPLES
    for name in (PN_CST_38, PORT_MF_454, ADN_CST_10, PARECER_93, PORT_MF_277,
                 SUMULA_STJ, CARNE_LEAO):
        assert name in SAMPLES


# --------------------------------------------------------------------------
# Running the real pipeline over a real span
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Unified:
    """One span of one sample, taken through unification exactly as the tree does."""

    paras: tuple[StyledPara, ...]
    analysis: QuotationAnalysis
    unit_heads: frozenset[str]
    candidates: tuple[Candidate, ...]
    assignments: tuple[Assignment, ...]
    rejected: tuple[str, ...]

    @property
    def texts(self) -> dict[int, str]:
        return {p.index: p.text.strip() for p in self.paras}

    @property
    def shape(self) -> tuple[tuple[str | None, int], ...]:
        """``(label.canonical, depth)`` in document order — the whole assertion."""
        return tuple(
            (a.label.canonical if a.label is not None else None, a.depth)
            for a in self.assignments
        )

    @property
    def indices(self) -> tuple[int, ...]:
        return tuple(a.index for a in self.assignments)


_DOCS: dict[str, StyledDoc] = {}
_RUNS: dict[tuple[str, str], Unified] = {}


def document(name: str) -> StyledDoc:
    """The sample, read once per session — ``parecer_93`` is ~430 blocks."""
    if name not in _DOCS:
        _DOCS[name] = read_docx(SAMPLES_DIR / f"{name}.docx")
    return _DOCS[name]


def _span_blocks(name: str, which: str) -> list[StyledPara | StyledTable]:
    doc = document(name)
    metadata = extract_metadata(doc, filename=f"{name}.docx")
    seg = segment_document(doc, metadata=metadata)
    blocks = {b.index: b for b in doc.blocks}
    if which == "body":
        span = seg.body
        chosen = [blocks[i] for i in span.indices if i in blocks] if span else []
    else:
        # The annex's own `ANEXO ÚNICO` marker is its title, not its first
        # section — `infer_hierarchy` drops it the same way.
        annex = seg.annexes[0]
        chosen = [blocks[i] for i in annex.span.indices if i in blocks][1:]
    return [b for b in chosen if isinstance(b, StyledTable) or not b.is_empty]


def unified(name: str, *, which: str = "body") -> Unified:
    """Run ``name``'s span through the real unification pipeline.

    Mirrors :func:`lexml_nonstat.hierarchy.tree.build_tree` step for step, so a
    change to the pipeline's order shows up here rather than hiding behind a
    tree that happens to come out the same.
    """
    key = (name, which)
    if key not in _RUNS:
        span_blocks = _span_blocks(name, which)
        paras = [b for b in span_blocks if isinstance(b, StyledPara)]
        analysis = analyse_quotation(paras)
        heads = detect_unit_series(paras)
        cands = collect_candidates(paras, analysis, unit_heads=heads)
        assignments, rejected = unify_levels(cands)
        assignments = demote_numbered_containers(
            assignments, texts={p.index: p.text.strip() for p in paras}
        )
        _RUNS[key] = Unified(
            paras=tuple(paras),
            analysis=analysis,
            unit_heads=heads,
            candidates=cands,
            assignments=tuple(assignments),
            rejected=tuple(rejected),
        )
    return _RUNS[key]


# --------------------------------------------------------------------------
# Synthetic fixtures — the negative half of every rule
# --------------------------------------------------------------------------


def para(
    text: str,
    *,
    index: int = 0,
    style: str | None = None,
    outline_level: int | None = None,
) -> StyledPara:
    """One paragraph, carrying only what unification reads."""
    return StyledPara(
        inlines=(Inline(text),),
        style=style,
        outline_level=outline_level,
        index=index,
    )


def candidates_for(paras: list[StyledPara]) -> tuple[Candidate, ...]:
    """Synthetic paragraphs taken through the same front half of the pipeline."""
    analysis = analyse_quotation(paras)
    return collect_candidates(
        paras, analysis, unit_heads=detect_unit_series(paras)
    )


def numeric_candidate(value: int, index: int) -> Candidate:
    """A bare depth-1 numeric candidate, for judging a top series directly."""
    return Candidate(
        index=index,
        label=Label(raw=f"{value}.", kind="numeric", value=(value,)),
        style=None,
        quoted=False,
        text=f"{value}. TEXTO",
    )


def style_assignment(index: int, depth: int = 1, *, style: int | None = 0) -> Assignment:
    """A style-evidenced heading, as ``unify_levels`` would have emitted it."""
    return Assignment(
        index=index,
        depth=depth,
        kind="secao",
        label=None,
        style=style,
        heading=None,
        score=W_STYLE,
        signals=("style",),
    )


# ==========================================================================
# Depth assignment on real samples
# ==========================================================================


#: `pn_cst_38` in document order. One sequence exercising every anchoring rule:
#: sub-labels anchoring to their parent (`2.3.1` under `2.3`), a roman track
#: opening below a numeric one (`I` under `2.3.2`), an alpha track opening below
#: the roman (`a` under `I`), and a return to a seen key popping back (`6.4`).
PN_CST_38_SHAPE: tuple[tuple[str, int], ...] = (
    ("2", 1),
    ("2.1", 2),
    ("2.2", 2),
    ("2.3", 2),
    ("2.3.1", 3),
    ("2.3.2", 3),
    ("I", 4),
    ("II", 4),
    ("III", 4),
    ("2.3.3", 3),
    ("2.3.4", 3),
    ("2.4", 2),
    ("2.5", 2),
    ("3", 1),
    ("3.1", 2),
    ("3.2", 2),
    ("3.3", 2),
    ("3.4", 2),
    ("3.5", 2),
    ("4", 1),
    ("5", 1),
    ("5.1", 2),
    ("5.2", 2),
    ("6", 1),
    ("6.1", 2),
    ("6.2", 2),
    ("6.3", 2),
    ("I", 3),
    ("a", 4),
    ("b", 4),
    ("II", 3),
    ("a", 4),
    ("b", 4),
    ("6.4", 2),
    ("7", 1),
)

#: `port_mf_454`: `a)`/`b)` open a level under `2.`, and `2.1` must come back to
#: depth 2 anyway.
PORT_MF_454_SHAPE: tuple[tuple[str, int], ...] = (
    ("1", 1),
    ("2", 1),
    ("a", 2),
    ("b", 2),
    ("2.1", 2),
    ("3", 1),
    ("3.1", 2),
    ("3.2", 2),
    ("4", 1),
    ("4.1", 2),
    ("5", 1),
    ("6", 1),
    ("7", 1),
    ("7.1", 2),
    ("8", 1),
)

ADN_CST_10_SHAPE: tuple[tuple[str, int], ...] = (("1", 1), ("1.1", 2), ("2", 1))


def test_pn_cst_38_depths():
    """The four-level sample: every anchoring rule, in the document that has them.

    A single wrong depth here is a section nested under the wrong parent — valid
    XML, wrong document.
    """
    run = unified(PN_CST_38)
    assert len(run.assignments) == 35
    assert run.shape == PN_CST_38_SHAPE


def test_port_mf_454_depths():
    """Mixed alpha and dotted-numeric tracks under one numeric parent."""
    run = unified(PORT_MF_454)
    assert len(run.assignments) == 15
    assert run.shape == PORT_MF_454_SHAPE


def test_dotted_label_anchors_to_parent_not_stack_height():
    """`2.1` is a child of `2.`, whatever was opened in between.

    ``port_mf_454`` puts `a)` and `b)` between `2.` and `2.1`. Placing a dotted
    numeric by the *stack's height* would make `2.1` a child of `b)` at depth 3;
    placing it by its own parent prefix keeps it a sibling of `a)`/`b)`'s parent
    at depth 2. This is the rule, isolated from the rest of the sequence.
    """
    run = unified(PORT_MF_454)
    by_canonical = {
        (a.label.canonical if a.label else None): a for a in run.assignments
    }
    assert by_canonical["2"].depth == 1
    assert by_canonical["a"].depth == 2
    assert by_canonical["b"].depth == 2
    assert by_canonical["2.1"].depth == 2, "anchored to the stack, not to `2.`"
    # …and it really does come after the alpha track, or the test proves nothing.
    order = [a.label.canonical for a in run.assignments if a.label is not None]
    assert order.index("a") < order.index("2.1")
    assert order.index("b") < order.index("2.1")


def test_adn_cst_10_depths():
    """The smallest structured sample — three headings, two levels."""
    run = unified(ADN_CST_10)
    assert run.shape == ADN_CST_10_SHAPE


@pytest.mark.parametrize("name", SAMPLES)
def test_depth_monotonicity_all_samples(name: str):
    """Depth never jumps: a tree with a hole in it is not a tree (plan §8).

    Enforced rather than hoped for — clamping is the honest response to
    inconsistent evidence, and the first heading is always a root.
    """
    run = unified(name)
    # Six of the fifteen are genuinely flat; an empty sequence is monotonic and
    # is asserted as such rather than skipped.
    assert all(a.depth >= 1 for a in run.assignments)
    if run.assignments:
        assert run.assignments[0].depth == 1, "the first heading is always a root"
    for previous, current in zip(run.assignments, run.assignments[1:]):
        assert current.depth <= previous.depth + 1, (
            f"{name}: depth {previous.depth} → {current.depth} at block "
            f"{current.index}"
        )


# ==========================================================================
# Rejections — each must arrive as a readable reason
# ==========================================================================


def test_pn_cst_38_subject_codes_rejected():
    """`1.24.20.25 -` is a subject-classification code, not a fourth-level section.

    Two of the three codes never get past the grammar (a leading-zero component
    is not a rótulo); the third is well-formed and has to be refused *here*,
    because only the document can say that `1.24.20` was never opened.
    """
    run = unified(PN_CST_38)
    codes = {2: "1.24.20.25", 3: "2.08.30.00", 4: "2.16.25.00"}
    assert set(codes) & set(run.indices) == set(), "a subject code became a section"

    by_index = {c.index: c for c in run.candidates}
    for index, text in codes.items():
        assert by_index[index].text.startswith(text)
    parsed = [i for i in codes if by_index[i].label is not None]
    assert parsed == [2], "the leading-zero rule should stop the other two"

    orphan = [r for r in run.rejected if "orphan" in r]
    assert orphan, run.rejected
    assert any("1.24.20.25" in r for r in orphan)
    assert any("block 2" in r for r in orphan)


def test_parecer_93_top_series_rejected():
    """A document does not number itself 1, 11, 111, 46, 194, 74.

    Those are paragraph numbers of the documents ``parecer_93`` quotes. The
    whole depth-1 numeric track goes, and the rejection says which values it
    judged so the decision can be explained afterwards.
    """
    run = unified(PARECER_93)
    reasons = [r for r in run.rejected if "top numeric series" in r]
    assert reasons, run.rejected
    assert "1,11,111,46,194,74" in reasons[0]

    assert not [
        a for a in run.assignments if a.label is not None and a.label.kind == "numeric"
    ]
    assert run.shape == (("IV", 1), ("V", 1), ("VI", 1))


def test_parecer_93_solitary_alpha_rejected():
    """A lone `n.` is an OCR'd footnote marker, not an enumeration.

    Block 330 reads `n. Nesse contexto, …`. Nothing but the absence of an `m.`
    or an `o.` anywhere in 400 paragraphs says so.
    """
    run = unified(PARECER_93)
    assert 330 not in run.indices
    solitary = [r for r in run.rejected if "solitary" in r]
    assert solitary, run.rejected
    assert any("block 330" in r for r in solitary)

    text = {p.index: p.text for p in run.paras}[330]
    assert text.strip().startswith("n. Nesse contexto")


def test_validate_top_series():
    """The verdict *and* the values it judged, so a rejection can be reported."""
    low = [numeric_candidate(v, i) for i, v in enumerate((2, 3, 4))]
    assert validate_top_series(low) == (True, (2, 3, 4))

    high = [numeric_candidate(v, i) for i, v in enumerate((46, 74, 194))]
    verdict, values = validate_top_series(high)
    assert verdict is False
    assert values == (46, 74, 194), "the rejection must carry its evidence"

    assert validate_top_series([]) == (True, ()), "nothing to judge is not a failure"


# ==========================================================================
# Named-unit series (amendment A-4.4)
# ==========================================================================


def test_unit_series_found_in_annex():
    """`Súmula CARF nº N` is a heading only because dozens of them run in order."""
    assert unified(PORT_MF_277, which="annex").unit_heads == frozenset({"sumula carf"})
    assert unified(PORT_MF_277).unit_heads == frozenset(), "the series is in the annex"


@pytest.mark.parametrize("name", [s for s in SAMPLES if s != PORT_MF_277])
def test_no_unit_series_in_other_samples(name: str):
    """No other body invents a unit series — the rule must not be trigger-happy."""
    assert unified(name).unit_heads == frozenset()


def test_unit_series_needs_three_increasing():
    """Two occurrences are a coincidence; numbers that fall are not a series."""
    two = [para("Súmula CARF nº 1", index=0), para("Súmula CARF nº 2", index=1)]
    assert detect_unit_series(two) == frozenset()
    assert MIN_UNIT_SERIES == 3

    three = two + [para("Súmula CARF nº 3", index=2)]
    assert detect_unit_series(three) == frozenset({"sumula carf"})

    unordered = [
        para("Súmula CARF nº 5", index=0),
        para("Súmula CARF nº 3", index=1),
        para("Súmula CARF nº 9", index=2),
    ]
    assert detect_unit_series(unordered) == frozenset()


def test_lei_never_becomes_a_unit_head():
    """`Lei nº 12.618` is a citation however many times it appears.

    Two things stop it, and the second is the honest one. The number `12.618`
    never reaches the end of the line, so the whole-paragraph match fails; and
    even a clean `Lei nº 12` repeated is not *increasing*.

    The rule is shape-based, not vocabulary-based: three paragraphs reading
    `Lei nº 1`, `Lei nº 2`, `Lei nº 3` and nothing else DO form a series, and
    are read as one. That is deliberate — a document that really did head its
    sections that way should be read that way. What protects ``parecer_93`` is
    that its `Lei nº …` mentions sit mid-sentence and are never whole
    paragraphs.
    """
    repeated = [para("Lei nº 12.618", index=i) for i in range(3)]
    assert detect_unit_series(repeated) == frozenset()

    shaped_like_a_series = [
        para("Lei nº 1", index=0),
        para("Lei nº 2", index=1),
        para("Lei nº 3", index=2),
    ]
    assert detect_unit_series(shaped_like_a_series) == frozenset({"lei"})

    # …and this is why the corpus is safe: the real mentions are mid-sentence.
    mid_sentence = [
        para("nos termos da Lei nº 1, de 1988, o contribuinte…", index=i)
        for i in range(3)
    ]
    assert detect_unit_series(mid_sentence) == frozenset()


def test_unit_series_gap_tolerated():
    """The annex's gaps are súmulas CARF revoked, not the end of the series.

    ``port_mf_277`` runs 1, 3, 4 … 33, 40 … — applying ``MAX_SIBLING_GAP`` to a
    document-wide validated unit series would amputate the annex at nº 33 and
    lose every súmula after it.
    """
    run = unified(PORT_MF_277, which="annex")
    assert len(run.assignments) == 65
    raws = [a.label.raw.strip() for a in run.assignments if a.label is not None]
    assert "Súmula CARF nº 40" in raws, "the annex was amputated at the first gap"
    assert raws[0] == "Súmula CARF nº 1"
    assert {a.depth for a in run.assignments} == {1}
    assert {a.kind for a in run.assignments} == {"item"}
    assert not [r for r in run.rejected if "non-sequential" in r]


# ==========================================================================
# Numbered-container demotion (amendment A-4.3)
# ==========================================================================


def test_demotion_fires_on_sumula_stj_125():
    """Word calls all 38 headings level 1; only seven of them name a case.

    `RECURSO ESPECIAL N. 34.988-SP` names a specific thing; `EMENTA` names a
    part of whatever thing it sits inside. That asymmetry — an identifier in the
    heading, not a vocabulary of court-document section names — is the whole
    rule, and it is what turns a flat list of 38 into 7 cases of 4-6 parts.
    """
    run = unified(SUMULA_STJ)
    assert len(run.assignments) == 38

    tops = [a for a in run.assignments if a.depth == 1]
    nested = [a for a in run.assignments if a.depth == 2]
    assert len(tops) == 7
    assert len(nested) == 31
    assert len(tops) + len(nested) == len(run.assignments)

    texts = run.texts
    assert all(re.search(r"\d", texts[a.index]) for a in tops)
    assert not any(re.search(r"\d", texts[a.index]) for a in nested)

    assert all("demoted" in a.signals for a in nested)
    assert not any("demoted" in a.signals for a in tops)
    assert {a.kind for a in nested} == {"subsecao"}


def test_demotion_declines_on_carne_leao():
    """Five `Heading 2` blocks with no identifier between them: nothing to nest.

    A rule that fired here would read a hierarchy into `O que é?` /
    `Quem pode utilizar este serviço?` — fabrication, which invariant #8 puts
    below flatness.
    """
    run = unified(CARNE_LEAO)
    nested = [a for a in run.assignments if a.depth == 2]
    assert len(nested) == 5
    assert all(a.style is not None for a in run.assignments)
    assert not any("demoted" in a.signals for a in run.assignments)
    assert [a.depth for a in run.assignments] == [1, 2, 2, 2, 2, 2]


def test_demotion_declines_on_all_numbered_run():
    """Every heading identified and none bare — ``port_mf_277``'s annex shape.

    The rule needs the run to genuinely *mix* the two kinds. Six identified
    siblings are six siblings.
    """
    run = [style_assignment(i) for i in range(6)]
    texts = {i: f"Súmula CARF nº {i + 1}" for i in range(6)}
    assert demote_numbered_containers(run, texts=texts) == tuple(run)


def test_demotion_needs_minimum_run():
    """Below ``MIN_DEMOTION_RUN`` a run is not a pattern, and reading one in is
    fabrication."""
    assert MIN_DEMOTION_RUN == 4
    # Numbered first, and a genuine mix — every other guard is satisfied.
    short = [style_assignment(i) for i in range(3)]
    texts = {0: "RECURSO ESPECIAL N. 1", 1: "EMENTA", 2: "RECURSO ESPECIAL N. 2"}
    assert demote_numbered_containers(short, texts=texts) == tuple(short)

    # One more heading and the same shape does fire — so it is the length, and
    # nothing else, that this test is pinning.
    longer = [style_assignment(i) for i in range(4)]
    texts[3] = "VOTO"
    fired = demote_numbered_containers(longer, texts=texts)
    assert [a.depth for a in fired] == [1, 2, 1, 2]


def test_demotion_needs_numbered_first():
    """A run that opens with a bare heading has no container to nest under.

    Demoting anyway would hang `EMENTA`'s siblings off nothing, or off whatever
    section happened to precede the run.
    """
    run = [style_assignment(i) for i in range(5)]
    texts = {
        0: "EMENTA",
        1: "RECURSO ESPECIAL N. 34.988-SP",
        2: "VOTO",
        3: "ACÓRDÃO",
        4: "RELATÓRIO",
    }
    assert demote_numbered_containers(run, texts=texts) == tuple(run)


def test_demotion_only_applies_to_style_headings():
    """Label-evidenced sections already placed themselves; demotion is for the
    case where Word declared one flat level and said nothing else.

    ``sumula_stj_125``'s shape with ``style=None`` must come back untouched.
    """
    run = [style_assignment(i, style=None) for i in range(6)]
    texts = {
        0: "RECURSO ESPECIAL N. 34.988-SP",
        1: "EMENTA",
        2: "ACÓRDÃO",
        3: "RELATÓRIO",
        4: "VOTO",
        5: "RECURSO ESPECIAL N. 36.084-SP",
    }
    assert demote_numbered_containers(run, texts=texts) == tuple(run)


def test_demotion_of_empty_input_is_empty():
    """The flat documents reach this function too, and it must not raise."""
    assert demote_numbered_containers((), texts={}) == ()


# ==========================================================================
# Kind vocabulary
# ==========================================================================


@pytest.mark.parametrize(
    ("kind", "depth", "expected"),
    [
        ("numeric", 1, "secao"),
        ("numeric", 2, "subsecao"),
        ("numeric", 3, "item"),
        ("numeric", 4, "item"),
        ("roman", 1, "inciso"),
        ("roman", 4, "inciso"),
        ("alpha", 2, "alinea"),
        ("compound", 3, "alinea"),
        ("unit", 1, "item"),
        ("ordinal", 1, "item"),
        ("capitulo", 2, "capitulo"),
        ("secao", 3, "secao"),
        ("subsecao", 1, "subsecao"),
        ("titulo", 2, "titulo"),
        ("livro", 1, "livro"),
        ("parte", 1, "parte"),
    ],
    ids=lambda v: str(v),
)
def test_section_kind_mapping(kind: str, depth: int, expected: str):
    """Label form and depth decide ``Agrupamento/@nome`` (plan §5.1, spec R-3)."""
    label = Label(raw="x", kind=kind, value=(1,))
    assert section_kind(label, depth) == expected
    assert expected in SECTION_KINDS


@pytest.mark.parametrize(
    ("depth", "expected"),
    [(0, "agrupamento"), (1, "secao"), (2, "subsecao"), (3, "item"), (9, "item")],
)
def test_section_kind_without_a_label(depth: int, expected: str):
    """A section style evidence found but no label named falls back on depth."""
    assert section_kind(None, depth) == expected
    assert expected in SECTION_KINDS


@pytest.mark.parametrize("name", SAMPLES)
def test_all_sample_kinds_are_in_vocabulary(name: str):
    """Nothing reaches Cycle 5 with a ``@nome`` the schemas have never heard of."""
    doc = infer_hierarchy(document(name))
    for tree in doc.trees:
        for section in tree.walk():
            assert section.kind in SECTION_KINDS, (name, section.kind)


# ==========================================================================
# Style level, and style against label
# ==========================================================================


def test_style_level():
    """Word's own declaration first; the style *name* only as a fallback."""
    assert style_level(para("x", style="Heading 2", outline_level=3)) == 3
    assert style_level(para("x", style=None, outline_level=0)) == 0

    assert style_level(para("x", style="Heading 2")) == 1
    assert style_level(para("x", style="heading 1")) == 0
    assert style_level(para("x", style="Título 1")) == 0

    assert style_level(para("x", style="Normal")) is None
    assert style_level(para("x", style="Heading")) is None
    assert style_level(para("x")) is None


def test_style_and_label_conflict_is_deterministic():
    """A paragraph that is both a `Heading 2` and a `2.1` resolves one way, always.

    Style is the author saying "this is a heading" in the file format itself, so
    it outranks a label the grammar merely recognised (``W_STYLE`` 0.9 against
    ``W_LABEL_SERIES`` 0.85). What this test protects is not which one wins but
    that the choice is made *once*, in the code, rather than by iteration order:
    five runs, identical results.
    """
    paras = [para("2.1 Objeto do contrato", index=7, style="Heading 2")]
    cands = candidates_for(paras)
    assert cands[0].style == 1
    assert cands[0].label is not None, "the conflict must be real"
    assert cands[0].label.canonical == "2.1"

    results = [unify_levels(cands) for _ in range(5)]
    assert all(r == results[0] for r in results)

    (assignment,), rejected = results[0]
    assert rejected == ()
    assert assignment.signals == ("style",), "style evidence must win"
    assert assignment.score == W_STYLE
    assert assignment.style == 1
    assert assignment.depth == 1


def test_unify_levels_is_deterministic_on_the_deepest_sample():
    """Determinism is a cross-cutting invariant (plan §9.2), not a synthetic one."""
    run = unified(PN_CST_38)
    first = unify_levels(run.candidates)
    for _ in range(3):
        assert unify_levels(run.candidates) == first


# ==========================================================================
# Evidence and confidence
# ==========================================================================


def test_document_confidence_damping():
    """One heading is not a structure.

    Without damping, a single accidental heading in a 400-paragraph document
    would score 0.9 and the document would be declared structured on the
    strength of one line.
    """
    assert document_confidence([0.9]) == 0.3
    assert document_confidence([0.85] * 3) == 0.85
    assert document_confidence([]) == 0.0
    assert document_confidence([0.25, 0.25]) == 0.1667

    assert document_confidence([0.9]) < CONFIDENCE_THRESHOLD
    assert document_confidence([0.85] * 3) > CONFIDENCE_THRESHOLD


def test_confidence_threshold_constant():
    """The weights are ordered by how much the source committed to the claim.

    A lone label sits deliberately below the threshold: on its own it is never
    enough to build a document's structure on.
    """
    assert CONFIDENCE_THRESHOLD == 0.5
    assert W_STYLE == 0.9
    assert W_LABEL_SERIES == 0.85
    assert W_UNIT_SERIES == 0.8
    assert W_LABEL_SOLO == 0.25
    assert W_LABEL_SOLO < CONFIDENCE_THRESHOLD < W_UNIT_SERIES < W_LABEL_SERIES < W_STYLE


def test_evidence_with_signal():
    """Signals are a set with a high-water score, not a growing list."""
    once = Evidence().with_signal("style", 0.9)
    assert once.signals == ("style",)
    assert once.score == 0.9

    again = once.with_signal("style", 0.5)
    assert again.signals == ("style",), "duplicated signal"
    assert again.score == 0.9, "the strongest evidence stands"

    assert once.signals == ("style",) and once.score == 0.9, "Evidence is frozen"

    both = again.with_signal("label:numeric", 0.85)
    assert both.signals == ("style", "label:numeric")
    assert both.score == 0.9


def test_docsignals_roundtrip():
    """Telemetry survives the golden files — including the rejection reasons."""
    signals = DocSignals(
        n_blocks=78,
        n_sections=35,
        coverage=0.4487,
        label_kinds=("numeric", "roman", "alpha"),
        style_headings=0,
        rejected=("orphan label '1.24.20.25 -' at block 2",),
        confidence=0.85,
    )
    assert DocSignals.from_dict(signals.to_dict()) == signals
    assert DocSignals.from_dict(None) == DocSignals()
    assert DocSignals.from_dict({}) == DocSignals()


def test_real_rejections_are_human_readable():
    """Every rejection names the rule and the block, so 4b can explain a routing.

    A rule whose rejections are invisible cannot be audited (plan invariant #10).
    """
    seen = [r for name in SAMPLES for r in unified(name).rejected]
    assert seen, "the corpus does reject things"
    for reason in seen:
        assert reason == reason.strip() and reason
        assert re.search(
            r"orphan|top numeric series|solitary|non-sequential", reason
        ), reason
