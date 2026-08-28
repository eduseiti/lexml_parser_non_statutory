"""Hand-authored ground truth for the inferred trees.

Plan §8's Cycle 4 exit criterion reads "all 15 samples produce trees matching
**hand-authored** goldens". The goldens in `tests/golden/hierarchy/` are
generated and reviewed, which is how Cycles 1–3 discharged theirs — but a
generated golden has one weakness that matters here: if the inference is wrong,
the golden records the wrong answer and passes forever.

So this module is the other half, ratified with the user during reconciliation
(spec R-4). Every expectation below was read off the source documents by hand
and written out as a literal, independently of what the code produces. If the
inference changes, a golden diff says *something* moved; these say *what should
have been there*.

The tables are deliberately verbose. A test that asserts "35 sections" catches
almost nothing; one that asserts the exact `(rótulo, depth)` sequence catches a
level assigned one too deep in the middle of a document, which is the failure
this cycle is actually at risk of.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.hierarchy import CONFIDENCE_THRESHOLD, HierarchyDoc, infer_hierarchy
from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.model.nodes import Para, Section
from lexml_nonstat.segment import segment_document

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"

_CACHE: dict[str, HierarchyDoc] = {}


def infer(name: str) -> HierarchyDoc:
    """Infer once per sample per session — `parecer_93` is 428 blocks."""
    if name not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        doc = read_docx(path)
        metadata = extract_metadata(doc, filename=path.name)
        _CACHE[name] = infer_hierarchy(
            doc,
            metadata=metadata,
            segmentation=segment_document(doc, metadata=metadata),
        )
    return _CACHE[name]


def shape(sections) -> list[tuple[str | None, int]]:
    """The tree flattened to `(rótulo-or-heading, depth)`, document order."""
    out: list[tuple[str | None, int]] = []

    def walk(nodes: tuple[Section, ...]) -> None:
        for section in nodes:
            out.append((section.label or section.heading, section.level))
            walk(section.children)

    walk(tuple(sections))
    return out


# --------------------------------------------------------------------------
# `pn_cst_38_19801031` — the plan's worked example of a four-level document.
# Read off the source: `2.` → `2.1` → `2.3` → `2.3.1` yields depths 1/2/2/3.
# --------------------------------------------------------------------------

PN_CST_38 = [
    ("2.", 1),
    ("2.1 -", 2),
    ("2.2 -", 2),
    ("2.3 -", 2),
    ("2.3.1 -", 3),
    ("2.3.2 -", 3),
    ("I -", 4),
    ("II -", 4),
    ("III -", 4),
    ("2.3.3 -", 3),
    ("2.3.4 -", 3),
    ("2.4 -", 2),
    ("2.5 -", 2),
    ("3.", 1),
    ("3.1 -", 2),
    ("3.2 -", 2),
    ("3.3 -", 2),
    ("3.4 -", 2),
    ("3.5 -", 2),
    ("4.", 1),
    ("5.", 1),
    ("5.1 -", 2),
    ("5.2 -", 2),
    ("6.", 1),
    ("6.1 -", 2),
    ("6.2 -", 2),
    ("6.3 -", 2),
    ("I -", 3),
    ("a)", 4),
    ("b)", 4),
    ("II -", 3),
    ("a)", 4),
    ("b)", 4),
    ("6.4 -", 2),
    ("7", 1),
]


def test_pn_cst_38_shape() -> None:
    """The plan's own example, asserted rótulo by rótulo.

    This single sequence exercises four separate rules: a dotted label anchors
    to its parent's depth, a roman track opens one level below the numeric one
    it sits in, an alpha track opens below the roman, and returning to a
    previously seen key pops the stack back to it rather than nesting again.
    """
    assert shape(infer("pn_cst_38_19801031").body.sections) == PN_CST_38


def test_pn_cst_38_subject_codes_are_not_sections() -> None:
    """Blocks 2–4 are subject-classification codes, not a fourth-level section.

        1.24.20.25 - Rendimentos Distribuídos pelas Pessoas Jurídicas…
        2.08.30.00 - Isenção das Sociedades Cooperativas
        2.16.25.00 - Lucro Arbitrado

    Two are refused by the grammar (a zero-padded component is not an ordinal);
    the third is refused by unification (its parent `1.24.20` was never opened).
    Both refusals are needed — amendment A-4.2.
    """
    labels = {label for label, _ in shape(infer("pn_cst_38_19801031").body.sections)}
    assert not any(label and label.startswith(("1.24", "2.08", "2.16")) for label in labels)


def test_pn_cst_38_headings_read_off_the_source() -> None:
    """`nomeAgrupador` is filled only where the remainder really is a heading."""
    by_label = {
        section.label: section.heading
        for section in infer("pn_cst_38_19801031").body.walk()
    }
    assert by_label["2."] == "DAS SOCIEDADES COOPERATIVAS"
    assert by_label["2.1 -"] == "Empresas de serviços"
    assert by_label["2.3.1 -"] == "Atos Cooperativos"
    assert by_label["4."] == "TRATAMENTO TRIBUTÁRIO"
    assert by_label["7"] == "DECORRÊNCIA"
    # `2.2 - O artigo 111 da Lei nº 5.764, de 16.12.71, que define…` is a
    # numbered *paragraph*, not a titled subsection: its remainder is prose.
    assert by_label["2.2 -"] is None


# --------------------------------------------------------------------------
# `port_mf_454_19770825` — the plan's `1.`, `2.`, `2.1`, `a)` case.
# --------------------------------------------------------------------------

PORT_MF_454 = [
    ("1.", 1),
    ("2.", 1),
    ("a)", 2),
    ("b)", 2),
    ("2.1 -", 2),
    ("3.", 1),
    ("3.1 -", 2),
    ("3.2 -", 2),
    ("4.", 1),
    ("4.1.", 2),
    ("5.", 1),
    ("6.", 1),
    ("7.", 1),
    ("7.1 -", 2),
    ("8.", 1),
]


def test_port_mf_454_shape() -> None:
    assert shape(infer("port_mf_454_19770825").body.sections) == PORT_MF_454


def test_port_mf_454_dotted_label_anchors_to_its_parent() -> None:
    """`2.1` is a child of `2.`, at depth 2 — not depth 3.

    In the source, `a)` and `b)` sit between `2.` and `2.1` and open a level of
    their own. A depth taken from the stack's height would put `2.1` under
    `b)`; a depth taken from its parent's puts it where the document says.
    """
    sections = {
        (section.label, section.level) for section in infer("port_mf_454_19770825").body.walk()
    }
    assert ("2.1 -", 2) in sections
    parent = next(
        s for s in infer("port_mf_454_19770825").body.sections if s.label == "2."
    )
    assert [c.label for c in parent.children] == ["a)", "b)", "2.1 -"]


# --------------------------------------------------------------------------
# `adn_cst_10_19910417` — the smallest dotted document, read off in full.
# --------------------------------------------------------------------------


def test_adn_cst_10_shape() -> None:
    """`1.`, `1.1`, `2.` — and `1.1` carries no separator in the source.

    `1.1 Na apuração do ganho de capital…` has a dot between its components
    and nothing after them. A rule requiring a trailing separator loses it.
    """
    assert shape(infer("adn_cst_10_19910417").body.sections) == [
        ("1.", 1),
        ("1.1", 2),
        ("2.", 1),
    ]


# --------------------------------------------------------------------------
# `par_cosit_26_20000629` — plan §2.6's residual hard case.
# --------------------------------------------------------------------------

PAR_COSIT_26 = [
    ("2.", 1),
    ("3.", 1),
    ("4.", 1),
    ("5.", 1),
    ("6.", 1),
    ("7.", 1),
    ("8.", 1),
    ("9.", 1),
    ("10.", 1),
    ("11.", 1),
    ("12.", 1),
    ("13.", 1),
    ("14.", 1),
    ("15.", 1),
    ("16.", 1),
    ("16.1.", 2),
    ("16.2.", 2),
    ("16.3.", 2),
    ("17.", 1),
    ("17.1.", 2),
    ("17.2.", 2),
    ("18.", 1),
    ("18.1.", 2),
    ("19.", 1),
]


def test_par_cosit_26_shape() -> None:
    """Its own numbering runs `2.`…`19.`; the statutes it quotes do not appear.

    The document starts at `2.` because `1.` sits in its front matter, which is
    why a top-level series is allowed to open at 1 *or* 2.
    """
    assert shape(infer("par_cosit_26_20000629").body.sections) == PAR_COSIT_26


def test_par_cosit_26_quoted_articles_are_inside_section_14() -> None:
    """Blocks 45–79 are quoted statute and belong to the section they interrupt.

    The excerpt sits between the document's own `14.` and `15.`, so every one
    of its paragraphs — five `Art.`, the `§` subdivisions, the `I`–`V` incisos
    and the omissis rules — lands in `14.`'s body as content, never as
    structure. Plan §2.6.
    """
    section = next(s for s in infer("par_cosit_26_20000629").body.walk() if s.label == "14.")
    indices = {i for node in section.body for i in node.all_source_indices}
    assert {46, 47, 53, 54, 64, 72, 79} <= indices
    assert not section.children
    quoted = {
        node.source_indices[0]
        for node in section.body
        if isinstance(node, Para) and node.kind in {"quote", "omissis"}
    }
    assert {46, 47, 53, 64, 72} <= quoted


# --------------------------------------------------------------------------
# `parecer_93_2018_decor_cgu_agu` — the regression-critical sample.
# --------------------------------------------------------------------------


def test_parecer_93_no_article_is_structure() -> None:
    """The plan's regression-critical requirement, stated as a property.

    Plan §2.5 measured 21 paragraph-initial `Art.` in this parecer under a
    strict regex and this cycle measures 25 under a quote-tolerant one; the
    number is not the point. Every one of them is a statute the opinion quotes,
    and articulating any would publish the Constitution's `Art. 40` as an
    article of a legal opinion.

    Nothing here depends on a threshold: on the generic route an article is
    prose by construction (spec decision D-3), so this holds however the
    confidence arithmetic is later retuned.
    """
    result = infer("parecer_93_2018_decor_cgu_agu")
    for section in result.body.walk():
        assert not (section.label or "").lower().startswith(("art", "§"))
        assert section.kind not in {"artigo", "paragrafo"}


def test_parecer_93_recovers_its_own_roman_chapters() -> None:
    """What survives is the parecer's own numbering, not the statutes'.

    Corrected from this spec's own first draft, which predicted zero sections
    (correction C-1). The document really is organised `I`–`VI`; `I`, `II` and
    `III` are lost only because the scan mangled `III -` into `111 -`, and
    recovering the remaining three is the right answer rather than fabrication.
    """
    assert shape(infer("parecer_93_2018_decor_cgu_agu").body.sections) == [
        ("IV -", 1),
        ("V -", 1),
        ("VI -", 1),
    ]
    headings = {s.label: s.heading for s in infer("parecer_93_2018_decor_cgu_agu").body.walk()}
    assert headings["V -"] == "CÁLCULO DO BENEFÍCIO ESPECIAL"
    assert headings["VI -"] == "CONCLUSÃO"


def test_parecer_93_quoted_numbering_is_not_structure() -> None:
    """Its numeric candidates read `1, 11, 111, 46, 194, 74` in document order.

    Those are fragments of quoted documents and an OCR'd `III`. A document does
    not number itself backwards, and the top-series rule is what says so
    (amendment A-4.2).
    """
    result = infer("parecer_93_2018_decor_cgu_agu")
    assert any("top numeric series" in reason for reason in result.body.signals.rejected)
    assert "numeric" not in result.body.signals.label_kinds


# --------------------------------------------------------------------------
# Style-driven documents.
# --------------------------------------------------------------------------


def test_carne_leao_shape() -> None:
    """`Heading 1` → depth 1, `Heading 2` → depth 2, children attached."""
    result = infer("sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO")
    assert len(result.body.sections) == 1
    root = result.body.sections[0]
    assert root.level == 1
    assert root.heading == "Sistema de Recolhimento Mensal Obrigatório (Carnê-Leão)"
    assert [c.heading for c in root.children] == [
        "O que é?",
        "Quem pode utilizar este serviço?",
        "Etapas para a realização deste serviço",
        "Outras Informações",
        "Lei Geral de Proteção de Dados Pessoais - LGPD",
    ]
    assert {c.level for c in root.children} == {2}


def test_sumula_stj_125_groups_by_case() -> None:
    """Seven cases, each with its own parts — amendment A-4.3.

    Word records all 38 headings at the same outline level with identical
    typography, alignment and indent, so the grouping has to be read from what
    the headings say about themselves: a heading carrying its own identifier
    names a thing, and identifier-free headings after it name parts of it.
    """
    result = infer("sumula_stj_125")
    tops = result.body.sections
    assert len(tops) == 7
    for top in tops:
        assert top.level == 1
        assert any(char.isdigit() for char in top.heading or "")
        assert top.children
        for child in top.children:
            assert child.level == 2
            assert not any(char.isdigit() for char in child.heading or "")
    assert [c.heading for c in tops[1].children] == [
        "EMENTA",
        "ACÓRDÃO",
        "RELATÓRIO",
        "VOTO",
        "VOTO-VISTA",
        "VOTO",
    ]


def test_carne_leao_grouping_declines() -> None:
    """The same rule must decline where no heading is identified.

    `CARNE_LEAO`'s five `Heading 2` blocks carry no identifier at all, so
    nothing may be demoted under anything — the negative half of A-4.3.
    """
    result = infer("sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO")
    for section in result.body.walk():
        assert "demoted" not in section.evidence.signals


# --------------------------------------------------------------------------
# Incisos, annexes, and the documents with nothing to infer.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ad_pgfn_13_20111220", [("I -", 1), ("II -", 1)]),
        ("ad_srf_3_19990107", [("I -", 1), ("II -", 1), ("III -", 1)]),
    ],
    ids=["ad_pgfn_13", "ad_srf_3"],
)
def test_declaratory_acts_are_incisos(name: str, expected: list) -> None:
    """`DECLARA` + incisos — plan §2.7's genre note, read off the source."""
    assert shape(infer(name).body.sections) == expected
    assert {s.kind for s in infer(name).body.walk()} == {"inciso"}


def test_port_mf_277_body_is_prose_and_the_annex_has_structure() -> None:
    """The articles stay prose; the annex gains real structure (A-R.8).

    `port_mf_277` is the corpus's one genuinely articulated document and routes
    to `norma` in Cycle 6, where `Art. 1º`/`Art. 2º` become `Dispositivo`s. On
    the generic route they are prose, which is why the body tree is flat. The
    annex is a different matter: 65 numbered súmulas are a heading series by
    any reading.
    """
    result = infer("port_mf_277_20180607")
    assert result.body.sections == ()
    assert result.body.flat is True

    assert len(result.annexes) == 1
    annex = result.annexes[0]
    assert (annex.label, annex.ordinal, annex.fragment) == ("ANEXO ÚNICO", 1, "anexo1")
    sections = annex.tree.sections
    assert len(sections) == 65
    assert {s.level for s in sections} == {1}
    assert {s.kind for s in sections} == {"item"}
    assert sections[0].label == "Súmula CARF nº 1"
    assert sections[-1].label == "Súmula CARF nº 107"
    # The gaps are the súmulas CARF revoked. A sibling-gap limit would have cut
    # the annex off at nº 33.
    assert "Súmula CARF nº 40" in {s.label for s in sections}


@pytest.mark.parametrize(
    "name",
    [
        "REsp_1306393",
        "ad_pgfn_3_20080918",
        "ad_srf_22_19970430",
        "adn_cosit_19_20001025",
        "sumula_carf_42",
    ],
)
def test_documents_with_no_structure_stay_flat(name: str) -> None:
    """Five documents genuinely have no body structure. None is invented.

    Plan invariant #8. A flat document is complete and citable; a fabricated
    section is a falsehood that validates, so the degradation is deliberately
    one-way.
    """
    tree = infer(name).body
    assert tree.sections == ()
    assert tree.flat is True
    assert tree.confidence < CONFIDENCE_THRESHOLD


def test_no_sample_exceeds_the_depth_its_source_declares() -> None:
    """Maximum depth per sample, read off the source documents by hand."""
    expected = {
        "REsp_1306393": 0,
        "ad_pgfn_13_20111220": 1,
        "ad_pgfn_3_20080918": 0,
        "ad_srf_22_19970430": 0,
        "ad_srf_3_19990107": 1,
        "adn_cosit_19_20001025": 0,
        "adn_cst_10_19910417": 2,
        "par_cosit_26_20000629": 2,
        "parecer_93_2018_decor_cgu_agu": 1,
        "pn_cst_38_19801031": 4,
        "port_mf_277_20180607": 0,
        "port_mf_454_19770825": 2,
        "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO": 2,
        "sumula_carf_42": 0,
        "sumula_stj_125": 2,
    }
    assert {name: infer(name).body.max_depth for name in expected} == expected
