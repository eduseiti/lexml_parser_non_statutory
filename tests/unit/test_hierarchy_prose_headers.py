"""The prose-form header route — amendment A-H.1, and the referee that gates it.

`par_cosit_26`'s `RELATÓRIO` is a section header. It carries `style='Normal'`,
`outline_level=None`, `bold=False` and `indent_effective=0` — formatting
**byte-for-byte identical** to `Fl. 7 DF COSIT RFB` two paragraphs later and to
the signatory's name at the foot of the document. There is no formatting
difference to read, so no deterministic rule can separate them, and until this
amendment the header simply fell through into body prose: `CONCLUSÃO` attached
to the *preceding* header (`18.1.`) and item `19.` became its sibling instead
of its child.

The fix is two-staged, and the split is what makes it safe:

* a **generator** proposes, on typographic evidence alone, at a confidence
  deliberately below `FLAG_THRESHOLD`. It is over-inclusive by design — 31
  candidates across the corpus for 6 true headers;
* a **referee** confirms or vetoes, one candidate at a time, and can only ever
  *remove*. It is never asked an open question, so no answer it gives can
  invent a section (A-H.3, the A-Q.3 pattern).

The consequence tested first, because everything else depends on it: with no
referee the generator's output is discarded and every tree is the tree Cycle 8c
built. Invariant #8 is a property of the wiring, not a hope about a model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.hierarchy import infer_hierarchy
from lexml_nonstat.hierarchy.unify import (
    PROSE_HEADER_MAX_CHARS,
    PROSE_HEADER_MAX_WORDS,
    PROSE_HEADER_RULE_CONFIDENCE,
    is_prose_form_header,
    upper_ratio,
)
from lexml_nonstat.ingest import StyledPara, read_docx
from lexml_nonstat.ingest.styled import Inline
from lexml_nonstat.referee import CachedAPIReferee, RefereeCache, Verdict
from lexml_nonstat.referee.protocol import FLAG_THRESHOLD, HEADING_VERDICTS
from lexml_nonstat.segment import segment_document

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"
FIXTURES = REPO_ROOT / "tests" / "referee_fixtures"

SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

#: Every prose-form candidate the generator proposes, per sample (T-8d.2).
#: Pinned rather than counted so that a candidate appearing in a *new* document
#: fails loudly — the corpus is 15 samples standing in for 300+, and a silent
#: widening of the generator is exactly the drift worth catching.
EXPECTED_CANDIDATES: dict[str, tuple[int, ...]] = {
    "par_cosit_26_20000629": (4, 5, 8, 9, 10, 12, 16, 21, 32, 36, 42, 89, 92, 94, 98),
    "sumula_stj_125": (34, 86, 182, 221, 268, 306, 347, 369, 370, 371),
    "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO": (78, 79, 80, 83),
    "parecer_93_2018_decor_cgu_agu": (100,),
    "sumula_carf_42": (2,),
}

#: The six the fixtures confirm, and the only six. Everything else is refused.
CONFIRMED: dict[str, tuple[int, ...]] = {
    "par_cosit_26_20000629": (16, 36, 92, 94),
    "sumula_stj_125": (371,),
    "sumula_carf_42": (2,),
}

_DOCS: dict[str, object] = {}


def sample(name: str):
    if name not in _DOCS:
        _DOCS[name] = read_docx(SAMPLES_DIR / f"{name}.docx")
    return _DOCS[name]


def para(text: str, *, index: int = 0, style: str = "Normal", outline=None) -> StyledPara:
    """A minimal `StyledPara`, for the shape tests that need no document."""
    return StyledPara(
        inlines=(Inline(text=text),),
        style=style,
        outline_level=outline,
        index=index,
    )


def explodes(*args, **kwargs):
    raise AssertionError("the transport was called; this path must make no network calls")


def fixture_referee() -> CachedAPIReferee:
    """Recorded answers, read-only, transport wired to raise (§9.3's seam)."""
    return CachedAPIReferee(
        cache=RefereeCache(FIXTURES, read_only=True),
        api_key="test-key-not-a-secret",
        transport=explodes,
    )


class ScriptedReferee:
    """A referee that answers `answer` to every heading question."""

    name = "scripted"
    enabled = True

    def __init__(self, answer: str | None, confidence: float = 1.0) -> None:
        self.answer = answer
        self.confidence = confidence
        self.asked: list[str] = []

    def is_heading(self, para: str, ctx: str, next_ctx: str = "") -> Verdict:
        self.asked.append(para)
        if self.answer is None:
            return Verdict.abstain("scripted abstention")
        return Verdict(self.answer, self.confidence, "scripted")

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        return Verdict.abstain("not under test")

    def section_kind(self, label: str, heading: str) -> Verdict:
        return Verdict.abstain("not under test")

    def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
        return Verdict.abstain("not under test")


def tree_shape(tree) -> tuple:
    """A hashable summary of a section tree: label, kind, level, heading, sizes."""

    def walk(sections):
        return tuple(
            (
                s.label,
                s.kind,
                s.level,
                s.heading,
                len(s.body),
                walk(s.children),
            )
            for s in sections
        )

    return (walk(tree.sections), len(tree.preamble), tree.flat)


def hierarchy(name: str, referee=None):
    doc = sample(name)
    return infer_hierarchy(doc, segmentation=segment_document(doc), referee=referee)


# ---------------------------------------------------------------------------
# T-8d.1 — the gate's shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("RELATÓRIO", True),
        ("CONCLUSÃO", True),
        ("FUNDAMENTOS LEGAIS", True),
        ("Fl. 7 DF COSIT RFB", True),  # proposed, and refused by the referee
        ("", False),
        ("   ", False),
        # Lower-case: below `PROSE_HEADER_MIN_UPPER`.
        ("Relatório do parecer", False),
        # Nine words: over `PROSE_HEADER_MAX_WORDS`.
        ("ESTE PARÁGRAFO TEM NOVE PALAVRAS E NÃO É UM CABEÇALHO", False),
        # No letters at all — `par_cosit_26` block 7 is exactly this.
        ("_______________", False),
        ("2.08.30.00", False),
    ],
)
def test_prose_form_gate_shape(text: str, expected: bool):
    """T-8d.1. Each refusal is forced by a real paragraph, not a hypothesis."""
    assert is_prose_form_header(para(text)) is expected


def test_a_long_paragraph_is_never_a_candidate():
    """T-8d.1. Over `PROSE_HEADER_MAX_CHARS`, however few words and however cased."""
    text = "A" * (PROSE_HEADER_MAX_CHARS + 1)
    assert len(text.split()) <= PROSE_HEADER_MAX_WORDS
    assert upper_ratio(text) == 1.0
    assert is_prose_form_header(para(text)) is False


def test_a_styled_paragraph_is_never_a_prose_candidate():
    """T-8d.1. Word already said it is a heading; the styled route admits it.

    This is what keeps `sumula_stj_125` at 10 candidates instead of 48 — and
    why the referee is never asked about a document the rules already read
    correctly.
    """
    assert is_prose_form_header(para("RELATÓRIO", outline=0)) is False
    assert is_prose_form_header(para("RELATÓRIO", style="Heading 1")) is False


def test_a_labelled_paragraph_is_never_a_prose_candidate():
    """T-8d.1. A rótulo is its own admission route; two would compete."""
    assert is_prose_form_header(para("2. DAS SOCIEDADES COOPERATIVAS")) is False


def test_a_quoted_paragraph_is_never_a_candidate():
    """T-8d.3. A header inside a transcribed norm belongs to that norm."""
    assert is_prose_form_header(para("CONCLUSÃO"), quoted=True) is False


def test_the_gate_sits_below_the_flag_threshold():
    """A-H.1. The generator proposes; it must never impose.

    If this rises to or above `FLAG_THRESHOLD`, candidates stop being flagged,
    stop reaching a referee, and start becoming structure on typographic
    evidence alone — which is the failure this whole design exists to prevent.
    """
    assert PROSE_HEADER_RULE_CONFIDENCE < FLAG_THRESHOLD


# ---------------------------------------------------------------------------
# T-8d.2 / T-8d.4 — the corpus surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_generator_proposes_exactly_the_pinned_candidates(name: str):
    """T-8d.2. Per sample, in document order."""
    doc = sample(name)
    segmentation = segment_document(doc)
    body = segmentation.body
    proposed: list[int] = []
    if body is not None:
        from lexml_nonstat.hierarchy.quotation import analyse_quotation

        paras = [
            b
            for b in doc.blocks
            if isinstance(b, StyledPara) and not b.is_empty and body.start <= b.index <= body.end
        ]
        analysis = analyse_quotation(paras)
        proposed = [
            p.index
            for p in paras
            if is_prose_form_header(p, quoted=analysis.is_quoted(p.index))
        ]
    assert tuple(proposed) == EXPECTED_CANDIDATES.get(name, ())


def test_the_corpus_surface_is_thirty_one():
    """T-8d.2. The total, stated once so the per-sample table cannot drift."""
    assert sum(len(v) for v in EXPECTED_CANDIDATES.values()) == 31


@pytest.mark.parametrize("name", ["ad_srf_22_19970430", "adn_cosit_19_20001025"])
def test_documents_with_no_body_propose_nothing(name: str):
    """T-8d.4. The body gate, measured on the two samples that have no body.

    Both are entirely front and back matter (A-3.5), so `Segmentation.body` is
    `None` and `build_tree` is never called. Their signatory names are
    upper-case, short and unlabelled — they would sail through the typographic
    gate — and the referee is never asked about them. A census that scanned
    whole documents counted them; the implementation does not, and that
    difference is this test.
    """
    assert segment_document(sample(name)).body is None
    assert name not in EXPECTED_CANDIDATES


# ---------------------------------------------------------------------------
# T-8d.5 / T-8d.8 — invariant #8, the load-bearing regression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_no_referee_leaves_every_tree_untouched(name: str):
    """T-8d.5. `--referee=none` ⇒ the Cycle 8c tree, exactly.

    Asserted against a tree built with `referee=None` *and* against one built
    with an explicitly disabled referee, because those are two different code
    paths into the same guarantee.
    """
    from lexml_nonstat.referee import NullReferee

    baseline = tree_shape(hierarchy(name).body)
    assert tree_shape(hierarchy(name, referee=None).body) == baseline
    assert tree_shape(hierarchy(name, referee=NullReferee()).body) == baseline


@pytest.mark.parametrize("name", SAMPLES)
def test_an_abstaining_referee_changes_nothing(name: str):
    """T-8d.8. §7.3 constraint 5: an abstention keeps the rule verdict.

    A referee outage must degrade quality, never availability — and here
    "quality" means the document stays flat rather than gaining a section
    nobody vouched for.
    """
    assert tree_shape(hierarchy(name, referee=ScriptedReferee(None)).body) == tree_shape(
        hierarchy(name).body
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_a_refusing_referee_changes_nothing(name: str):
    """T-8d.8. A referee that answers `nao` to everything is a referee-less run.

    The complement of the adversarial test below: confirm-only means a *veto*
    is the default outcome, so vetoing everything must reproduce the baseline
    exactly rather than merely closely.
    """
    referee = ScriptedReferee("nao")
    assert tree_shape(hierarchy(name, referee=referee).body) == tree_shape(
        hierarchy(name).body
    )


def test_a_low_confidence_confirmation_is_refused():
    """§7.3 constraint 4. A referee that is itself unsure does not break a tie."""
    unsure = ScriptedReferee("secao", confidence=0.30)
    assert tree_shape(hierarchy("par_cosit_26_20000629", referee=unsure).body) == tree_shape(
        hierarchy("par_cosit_26_20000629").body
    )


def test_an_out_of_vocabulary_answer_is_refused():
    """T-8d.14. The pre-A-H.2 words are now outside the vocabulary.

    A referee still answering `heading` — an older implementation, a stale
    prompt, a provider replaying a cached answer — must abstain rather than be
    counted, which is what `adjudicate`'s closed-vocabulary check delivers.
    """
    assert "heading" not in HEADING_VERDICTS
    assert "prose" not in HEADING_VERDICTS
    stale = ScriptedReferee("heading")
    assert tree_shape(hierarchy("par_cosit_26_20000629", referee=stale).body) == tree_shape(
        hierarchy("par_cosit_26_20000629").body
    )


# ---------------------------------------------------------------------------
# T-8d.6 / T-8d.7 — overreach
# ---------------------------------------------------------------------------


def test_sumula_stj_125_keeps_its_styled_structure_under_the_referee():
    """T-8d.6. The overreach guard, on the document the rules already get right.

    `sumula_stj_125` carries `Heading 1` on every real header, so its case
    structure is correct before any referee is consulted: 7 cases, each with
    EMENTA / ACÓRDÃO / RELATÓRIO / VOTO beneath it. Nine of the ten candidates
    the generator proposes there are refused — publication dates, a case
    number, a bare `ANEXO` that A-3.3 records is not one.

    The tenth is **confirmed, and correctly**: block 371's
    `VOTO VENCIDO EM PARTE` opens a real part of the last case, in a tail whose
    heading styling the conversion lost. So the assertion is not "nothing
    changed" — it is the sharper claim that matters: **the styled tree is
    untouched, and the one addition lands inside it, never beside it.**
    """
    baseline = hierarchy("sumula_stj_125").body
    refereed = hierarchy("sumula_stj_125", referee=fixture_referee()).body

    assert len(refereed.sections) == len(baseline.sections) == 7
    for before, after in zip(baseline.sections, refereed.sections):
        assert (after.heading, after.kind, after.level) == (
            before.heading,
            before.kind,
            before.level,
        )
        # Every styled subsection survives, in order, at its own depth.
        styled = [(c.heading, c.level) for c in before.children]
        assert [(c.heading, c.level) for c in after.children][: len(styled)] == styled

    last = refereed.sections[-1]
    assert ("VOTO VENCIDO EM PARTE", 2) in [(c.heading, c.level) for c in last.children]


@pytest.mark.parametrize("name", SAMPLES)
def test_an_adversarial_referee_cannot_reach_beyond_the_generator(name: str):
    """T-8d.7. Invariant #9, as an attack (the A-4b.6 pattern).

    A referee answering `secao` at confidence 1.0 to *every* question is the
    worst case the design admits. It may confirm every candidate the generator
    proposed — that is what confirm-only means — but it must not produce a
    section anywhere else. So every heading in the resulting tree is either one
    the baseline already had, or the text of a proposed candidate.
    """
    attacker = ScriptedReferee("secao", confidence=1.0)
    attacked = hierarchy(name, referee=attacker).body
    baseline = hierarchy(name).body

    proposed_texts = {
        b.text.strip()
        for b in sample(name).blocks
        if isinstance(b, StyledPara)
        and not b.is_empty
        and b.index in EXPECTED_CANDIDATES.get(name, ())
    }

    def headings(sections) -> set[str]:
        out: set[str] = set()
        for s in sections:
            if s.heading:
                out.add(s.heading)
            out |= headings(s.children)
        return out

    new = headings(attacked.sections) - headings(baseline.sections)
    assert new <= proposed_texts, f"referee invented headings: {new - proposed_texts}"


def test_an_adversarial_referee_does_not_move_sumula_stj_125():
    """T-8d.7. Style evidence wins, even against a referee saying yes to all.

    The ten candidates in this document are all refusable noise, so an
    all-confirming referee is the sharpest possible test of whether the styled
    route still dominates. Its 7×4 case structure must survive intact.
    """
    attacked = hierarchy("sumula_stj_125", referee=ScriptedReferee("secao", 1.0)).body
    assert len(attacked.sections) == 7
    for case in attacked.sections:
        assert case.level == 1
        assert {child.heading for child in case.children} >= {
            "EMENTA",
            "ACÓRDÃO",
            "RELATÓRIO",
            "VOTO",
        }


# ---------------------------------------------------------------------------
# T-8d.10 — the depth rule (A-H.4), the shape the user reported as correct
# ---------------------------------------------------------------------------


def test_par_cosit_26_gains_the_reported_structure():
    """T-8d.10. `CONCLUSÃO` parents `19.`; `RELATÓRIO` parents the early items.

    This is the defect closed, stated as the tree it produces. Before A-H.4,
    `CONCLUSÃO` was a `<p>` inside the container for item `18.1.` and `19.` was
    that container's sibling — the document said the opposite of what it meant.
    """
    tree = hierarchy("par_cosit_26_20000629", referee=fixture_referee()).body

    top = [(s.heading, s.kind, s.level) for s in tree.sections]
    assert top == [
        ("RELATÓRIO", "secao", 1),
        ("FUNDAMENTOS LEGAIS", "secao", 1),
        ("CONCLUSÃO", "secao", 1),
        ("ORDEM DE INTIMAÇÃO", "secao", 1),
    ]

    by_heading = {s.heading: s for s in tree.sections}

    conclusao = by_heading["CONCLUSÃO"]
    assert [c.label for c in conclusao.children] == ["19."]
    assert conclusao.children[0].level == 2

    relatorio = by_heading["RELATÓRIO"]
    assert [c.label for c in relatorio.children] == [
        "2.", "3.", "4.", "5.", "6.", "7.", "8."
    ]
    assert all(c.level == 2 for c in relatorio.children)


def test_the_citation_children_survive_the_deeper_tree():
    """T-8d.10. A-Q.4's nested citations still hang off item `14.`.

    Item `14.` moved from depth 1 to depth 2 under `FUNDAMENTOS LEGAIS`, so its
    four `citacao` children moved from 2 to 3. The amendment must deepen the
    tree, not disturb it — a regression here would mean A-H.4 had eaten A-Q.4.
    """
    tree = hierarchy("par_cosit_26_20000629", referee=fixture_referee()).body
    fundamentos = next(s for s in tree.sections if s.heading == "FUNDAMENTOS LEGAIS")
    item14 = next(c for c in fundamentos.children if c.label == "14.")
    assert [g.heading for g in item14.children] == [
        "Lei nº 7.713, de 1988",
        "Lei 8.134, de 1990",
        "Lei 8.383, de 1991",
        "Lei 8.981, de 1995",
    ]
    assert all(g.kind == "citacao" and g.level == 3 for g in item14.children)


@pytest.mark.parametrize("name", ["par_cosit_26_20000629", "sumula_stj_125"])
def test_every_confirmed_header_becomes_a_section(name: str):
    """T-8d.10. Each confirmed header, in the document it belongs to.

    `sumula_carf_42` is excluded deliberately and tested separately below: its
    single confirmed header is not enough evidence to declare the document
    structured, so it stays flat. That is invariant #8, not a failure.
    """
    doc = sample(name)
    texts = {
        b.index: b.text.strip()
        for b in doc.blocks
        if isinstance(b, StyledPara) and not b.is_empty
    }
    tree = hierarchy(name, referee=fixture_referee()).body

    def headings(sections) -> set[str]:
        out: set[str] = set()
        for s in sections:
            if s.heading:
                out.add(s.heading)
            out |= headings(s.children)
        return out

    found = headings(tree.sections)
    for index in CONFIRMED[name]:
        assert texts[index] in found, f"{name} p#{index} was confirmed but is not a section"


def test_a_lone_confirmed_header_does_not_make_a_document_structured():
    """Invariant #8, met by the *existing* damping rather than by new code.

    `sumula_carf_42`'s `ACÓRDÃOS PARADIGMAS` is confirmed at 0.95, and the
    document still comes back flat: `document_confidence` damps a single
    section towards zero (`MIN_SECTIONS_FOR_FULL_CONFIDENCE` is 3), so
    0.8 × 1/3 = 0.267 falls below `CONFIDENCE_THRESHOLD`.

    This is worth pinning precisely because it is the tempting thing to
    "fix". A document does not have a structure on the strength of one
    heading — the same rule that has always refused a lone rótulo refuses a
    lone confirmed header, and a referee gets no exemption from it.
    """
    from lexml_nonstat.hierarchy.evidence import CONFIDENCE_THRESHOLD

    tree = hierarchy("sumula_carf_42", referee=fixture_referee()).body
    assert tree.flat is True
    assert tree.sections == ()
    assert 0 < tree.confidence < CONFIDENCE_THRESHOLD
