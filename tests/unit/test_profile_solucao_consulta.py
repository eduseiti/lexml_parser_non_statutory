"""The ``solucao_consulta`` profile — Cycle 3 of the corpus-233 hardening plan.

Plan §1.4: soluções de consulta are **127 of the 233 documents (54.5%)** — the
corpus's dominant genre — and had no profile at all. They landed on ``generic``,
and twelve of them on a profile built for another genre entirely.

Two things are pinned here, and the second is the one that needed a design
decision.

**Identity.** The epigraph is exceptionally regular across all four sub-genres
(consulta, consulta interna, divergência, and the ``Disit/SRRF`` regional
shape), so the profile claims them at 0.9 and reads the right ``urn_type`` off
the epigraph — Cycle 2's A-2.2 mechanism, reused.

**Structure.** 125 of the 127 carry a ``Relatório`` / ``Fundamentos`` /
``Conclusão`` skeleton, and *none of it was visible to the parser*.
``is_prose_form_header`` requires an upper-case ratio of 0.85 and these headings
are title-case (``Relatório`` scores ~0.11), so they were never proposed, the
referee was never asked about them, and the documents rendered flat under every
configuration. ``par_cosit_26``'s upper-case ``RELATÓRIO`` — the paragraph
A-H.1 was written for — is why that gate looked sufficient.

M-1's answer is ``DocumentProfile.section_res``: literal headings a genre
declares, admitted **deterministically, with no referee**. The safety argument
is that it is genre knowledge scoped to one profile — every profile that
predates Cycle 3 declares none, so no document that does not select this
profile can be touched. The tests below assert that scoping rather than trusting
it.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from lexml_nonstat import cli
from lexml_nonstat.hierarchy import infer_hierarchy
from lexml_nonstat.hierarchy.evidence import W_SECTION_DECLARED
from lexml_nonstat.hierarchy.quotation import analyse_quotation
from lexml_nonstat.hierarchy.tree import build_tree
from lexml_nonstat.hierarchy.unify import declared_section_indices
from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara, read_docx
from lexml_nonstat.model.metadata import extract_metadata
from lexml_nonstat.profile import (
    GENERIC,
    SERVICO,
    SOLUCAO_CONSULTA,
    all_profiles,
    get_profile,
    score_profiles,
    select_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_GOLDENS = REPO_ROOT / "tests" / "golden" / "styled"

#: The 233-document corpus, outside the repository by design (research data,
#: not a fixture) — the convention `test_urn_completeness.py` established.
CORPUS = REPO_ROOT.parent / "br-taxqa-r_v2.0" / "original" / "nao_articulados"

requires_corpus = pytest.mark.skipif(
    not CORPUS.is_dir(),
    reason=f"the 233-document corpus is not present at {CORPUS} (research data, not a fixture)",
)


def run(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI in-process — the idiom `test_cli.py` uses."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def para(text: str, index: int, **kw) -> StyledPara:
    return StyledPara(inlines=(Inline(text=text),), index=index, **kw)


def _corpus_doc(stem: str) -> StyledDoc:
    return read_docx(CORPUS / f"{stem}.docx")


# ---------------------------------------------------------------------------
# 1. Registration — the plan's exit criterion "the profile is registered and
#    `list-profiles` shows it"
# ---------------------------------------------------------------------------


def test_the_profile_is_registered_before_the_floor():
    """Registered, retrievable, and ahead of ``generic``.

    Position is behaviour, not bookkeeping: registration order is the tie-break
    order, and ``generic`` must stay last for its floor to behave as a floor.
    """
    names = tuple(p.name for p in all_profiles())

    assert "solucao_consulta" in names
    assert get_profile("solucao_consulta") is SOLUCAO_CONSULTA
    assert names[-1] == "generic"
    assert names.index("solucao_consulta") < names.index("generic")


def test_list_profiles_shows_it_in_both_formats():
    """The exit criterion, through the interface a user actually has."""
    _, text, _ = run(["list-profiles"])
    assert "solucao_consulta" in text

    records = {r["name"]: r for r in json.loads(run(["list-profiles", "--format=json"])[1])}
    assert records["solucao_consulta"]["urn_type"] == "solucao.consulta"
    # No `urn_authority` default: the epigraph carries the sigla for 113 of the
    # 127, and a default here would silently name an issuer for the rest — the
    # Finding C defect (§1.4) that Cycle 2 had to repair on `generic`.
    assert records["solucao_consulta"]["urn_authority"] is None


# ---------------------------------------------------------------------------
# 2. Identity — epigraph, sub-genre and URN type
# ---------------------------------------------------------------------------


def _epigraph_doc(line: str) -> StyledDoc:
    return StyledDoc(
        blocks=(
            para(line, 0),
            para("ASSUNTO: Imposto sobre a Renda de Pessoa Física - IRPF", 1),
            para("Texto corrido do documento.", 2),
        ),
        source="synthetic.docx",
    )


@pytest.mark.parametrize(
    "line",
    [
        "Solução de Consulta Cosit nº 100, de 28 de setembro de 2020",
        "Solução de Consulta Interna Cosit nº 10, de 5 de junho de 2014",
        "Solução de Divergência Cosit nº 10, de 14 de agosto de 2014",
        "Solução de Consulta Disit/SRRF03 nº 15, de 9 de março de 2009",
        # The one variant shape in the corpus — `sd_cosit_16`, which writes its
        # number and date in a different style from every other document.
        "Solução de Divergência COSIT Nº 16 DE 27/09/2012",
    ],
)
def test_every_subgenre_epigraph_is_claimed(line: str):
    """0.9 on the epigraph, for all four sub-genres and the variant shape."""
    doc = _epigraph_doc(line)
    scored = dict((p.name, s) for p, s in score_profiles(doc))

    assert select_profile(doc) is SOLUCAO_CONSULTA
    assert scored["solucao_consulta"] == pytest.approx(0.9)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Solução de Consulta Cosit nº 100, de 28 de setembro de 2020", "solucao.consulta"),
        ("Solução de Consulta Interna Cosit nº 10, de 5 de junho de 2014", "solucao.consulta.interna"),
        ("Solução de Divergência Cosit nº 10, de 14 de agosto de 2014", "solucao.divergencia"),
    ],
)
def test_urn_type_is_read_off_the_epigraph(line: str, expected: str):
    """One profile, three document kinds — A-2.2's mechanism.

    ``Solução de Consulta Interna`` also matches the plain
    ``Solução de Consulta`` pattern, so this additionally pins that the more
    specific pattern is tried first. Order-dependence that is asserted is a
    contract; order-dependence that is merely true is a trap.
    """
    assert SOLUCAO_CONSULTA.urn_type_for(line) == expected


# ---------------------------------------------------------------------------
# 3. The samples do not move — the load-bearing exit criterion
# ---------------------------------------------------------------------------


def test_no_sample_is_claimed_by_the_new_profile():
    """None of the 15 samples is a solução de consulta.

    The plan's own risk note for this cycle: "adding a profile changes profile
    scoring for every document", and the exit criterion that no existing
    golden moves is therefore load-bearing. This is that criterion asserted at
    its source rather than inferred from the goldens staying byte-equal.
    """
    claimed = []
    for path in sorted(STYLED_GOLDENS.glob("*.json")):
        doc = StyledDoc.from_json(path.read_text(encoding="utf-8"))
        if select_profile(doc) is SOLUCAO_CONSULTA:
            claimed.append(path.stem)

    assert claimed == []


def test_carne_leao_keeps_its_profile_by_a_margin():
    """The `servico` sample survives Cycle 3's anchoring of its own patterns.

    ``servico``'s epigraph list carried a bare ``carne-leao`` that matched any
    line *mentioning* the carnê-leão. Two soluções de consulta about carnê-leão
    rendimentos scored 0.9 on it, tying with their own epigraph match and
    winning only on registration order. Anchoring it costs the sample nothing —
    its first line is "Sistema de Recolhimento Mensal Obrigatório (Carnê-Leão)",
    which the *other* pattern matches — and this test is what proves that claim
    rather than assuming it.
    """
    doc = StyledDoc.from_json(
        (STYLED_GOLDENS / "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO.json").read_text(
            encoding="utf-8"
        )
    )
    scored = score_profiles(doc)

    assert scored[0][0] is SERVICO
    assert scored[0][1] == pytest.approx(0.9)
    assert scored[0][1] > scored[1][1], "the sample's genre is decided by a tie-break"


# ---------------------------------------------------------------------------
# 4. `section_res` — M-1, the deterministic admission route
# ---------------------------------------------------------------------------


def _body(*texts: str) -> list[StyledPara]:
    return [para(t, i) for i, t in enumerate(texts)]


def test_declared_headings_are_admitted_with_no_referee():
    """M-1's whole point: structure without an API call.

    These headings are title-case, so the prose-form generator never proposes
    them and no referee is ever consulted. Before Cycle 3 this body was flat.
    """
    paras = _body(
        "Relatório",
        "1. O consulente formula consulta sobre a legislação tributária.",
        "Fundamentos",
        "2. A dedução das despesas de custeio é prevista em lei.",
        "Conclusão",
        "3. A consulta é solucionada nos termos acima.",
    )
    tree = build_tree(paras, section_res=SOLUCAO_CONSULTA.section_res, referee=None)

    assert tree.flat is False
    headings = [s.heading for s in tree.sections]
    assert headings == ["Relatório", "Fundamentos", "Conclusão"]


def test_a_declared_heading_records_its_own_provenance():
    """A declared heading is not a referee confirmation and must not claim to be.

    Telemetry reads these signals to explain why a document got the structure
    it did; "a genre declares this heading" is a different — and cheaper, and
    offline — answer from "a model confirmed this paragraph".
    """
    paras = _body("Relatório", "1. Texto.", "Conclusão", "2. Texto.")
    analysis = analyse_quotation(paras)
    declared = declared_section_indices(
        paras, analysis, section_res=SOLUCAO_CONSULTA.section_res
    )

    assert declared == frozenset({0, 2})

    tree = build_tree(paras, section_res=SOLUCAO_CONSULTA.section_res, referee=None)
    for section in tree.sections:
        assert "profile_declared" in section.evidence.signals
        assert "referee_confirmed" not in section.evidence.signals
        assert section.evidence.score == pytest.approx(W_SECTION_DECLARED)


def test_a_profile_declaring_no_sections_is_unchanged():
    """The safety property the whole design rests on.

    Every profile that predates Cycle 3 declares no ``section_res``, so a
    document routed through one of them must build *exactly* the tree it built
    before. Asserted by building the same body both ways, on two shapes:

    * a body whose only candidate headings are the declared words, which is
      flat without them and must *stay* flat for a profile declaring none;
    * a body that also carries a numeric series, so the comparison is not
      trivially between two empty trees — the tree that exists must be
      identical, not merely absent.
    """
    assert GENERIC.section_res == ()

    headings_only = _body("Relatório", "Texto corrido.", "Conclusão", "Mais texto.")
    without = build_tree(headings_only, referee=None)
    declared_none = build_tree(headings_only, section_res=GENERIC.section_res, referee=None)

    assert without.flat is True, "the fixture must be inert without declarations"
    assert without.to_dict() == declared_none.to_dict()

    # The same property where a tree genuinely exists. `1.`/`2.` is a valid
    # numeric series, so this body is structured either way — and declaring no
    # sections must leave that structure untouched rather than merely absent.
    with_series = _body("Relatório", "1. Texto.", "Conclusão", "2. Texto.")
    series_without = build_tree(with_series, referee=None)
    series_declared_none = build_tree(
        with_series, section_res=GENERIC.section_res, referee=None
    )

    assert series_without.flat is False
    assert series_without.to_dict() == series_declared_none.to_dict()


def test_a_declared_heading_inside_a_quotation_is_refused():
    """A solução that *quotes* another one is quoting, not dividing itself.

    Fabricated structure is the failure mode invariant #8 exists to prevent,
    and a heading lifted out of transcribed material is exactly that.
    """
    paras = [
        para("2. Transcreve-se a Solução de Consulta Cosit nº 8, de 2012:", 0),
        para("“Relatório", 1),
        para("O consulente daquele processo formulou consulta.", 2),
        para("Conclusão", 3),
        para("Aquela consulta foi solucionada.”", 4),
    ]
    analysis = analyse_quotation(paras)
    declared = declared_section_indices(
        paras, analysis, section_res=SOLUCAO_CONSULTA.section_res
    )

    for index in sorted(declared):
        assert not analysis.is_quoted(index), (
            f"block {index} was admitted as a section from inside a quotation"
        )


def test_a_styled_heading_keeps_its_own_route():
    """Word's own declaration outranks a name we matched.

    ``is_prose_form_header`` refuses a styled paragraph for this reason, and
    the declared route must refuse it identically — otherwise two admission
    routes compete for one paragraph and the winner depends on call order.
    """
    paras = [
        para("Relatório", 0, outline_level=0),
        para("1. Texto.", 1),
    ]
    analysis = analyse_quotation(paras)

    assert declared_section_indices(
        paras, analysis, section_res=SOLUCAO_CONSULTA.section_res
    ) == frozenset()


def test_a_heading_that_opens_a_sentence_is_not_a_division():
    """``section_res`` is anchored end-to-end, and this is why.

    "Conclusão: o consulente deve recolher…" is prose *about* a conclusion. A
    pattern that matched it would turn a sentence into a section header in
    every document of the genre.
    """
    paras = _body(
        "Conclusão: o consulente deverá recolher o imposto devido.",
        "Relatório da autoridade fiscal sobre o caso concreto.",
    )
    analysis = analyse_quotation(paras)

    assert declared_section_indices(
        paras, analysis, section_res=SOLUCAO_CONSULTA.section_res
    ) == frozenset()


def test_the_headings_are_matched_folded():
    """``Relatório``, ``RELATÓRIO`` and ``relatorio`` are one heading.

    The corpus writes them in title case; `par_cosit_26` writes its in upper
    case. Folding is what lets one pattern serve both without the profile
    carrying three spellings of every word.
    """
    paras = _body("RELATÓRIO", "1. Texto.", "relatorio", "2. Texto.", "Fundamento", "3. Texto.")
    analysis = analyse_quotation(paras)

    assert declared_section_indices(
        paras, analysis, section_res=SOLUCAO_CONSULTA.section_res
    ) == frozenset({0, 2, 4})


def test_annexes_do_not_inherit_the_genres_skeleton():
    """An annex is a different document travelling with this one.

    ``infer_hierarchy`` passes ``section_res=()`` for every annex span. Pinned
    through the public entry point rather than by reading the call site, so a
    future refactor that threads the profile everywhere fails here.
    """
    paras = _body("Conclusão", "Texto do anexo.")

    assert build_tree(paras, section_res=(), referee=None).flat is True


# ---------------------------------------------------------------------------
# 5. The corpus — the cycle's headline, and the twelve reclaimed documents
# ---------------------------------------------------------------------------


@requires_corpus
def test_the_genre_selects_its_own_profile():
    """125 of the 127 sc/sci/sd documents. The other two are a known residue.

    ``sc_15_20090309`` and ``sc_6007_20190325`` are bare-``sc`` regional
    soluções whose first line is a portal banner rather than an epigraph; Cycle
    2's report §5 already records them as residue.
    """
    selected = {}
    for path in sorted(CORPUS.glob("*.docx")):
        stem = path.stem
        if not stem.startswith(("sc_", "sci_", "sd_")):
            continue
        selected[stem] = select_profile(read_docx(path)).name

    claimed = [s for s, n in selected.items() if n == "solucao_consulta"]

    assert len(selected) == 127
    assert len(claimed) >= 125, sorted(set(selected) - set(claimed))


@requires_corpus
@pytest.mark.parametrize(
    "stem",
    [
        # The ten that scored 0.40 on `jurisprudencia_generico`'s STJ pattern
        # with no epigraph match of their own — a solução discussing STJ case
        # law read as a court document.
        "sc_cosit_102_20140407",
        "sc_cosit_105_20140407",
        "sc_cosit_152_20180926",
        # The two that tied with `servico` at 0.9 on a bare `carne-leao`
        # pattern and won it on registration order, emitting `:servico:`.
        "sc_cosit_116_20190326",
        "sc_cosit_14_20170116",
    ],
)
def test_the_misprofiled_documents_are_reclaimed(stem: str):
    """Twelve documents were profiled as another genre entirely (§2.2).

    Two of them emitted a ``:servico:`` URN type — a solução de consulta
    claiming to be a taxpayer service page. The URN is the assertion that
    matters: a mis-profiled document is recoverable, a mis-identified one is
    cited wrongly forever.
    """
    doc = _corpus_doc(stem)
    profile = select_profile(doc)
    meta = extract_metadata(doc, profile=profile, filename=f"{stem}.docx")

    assert profile is SOLUCAO_CONSULTA
    assert ":servico:" not in meta.urn
    assert ":sumula:" not in meta.urn
    assert meta.urn.startswith(
        "urn:lex:br:ministerio.fazenda;secretaria.receita.federal:solucao.consulta"
    )


@requires_corpus
def test_no_document_of_the_genre_sits_on_a_scoring_tie():
    """A tie is a genre decided by a list literal, not by evidence.

    This is ``test_winning_margin``'s property, asserted over the 127 real
    documents rather than the 15 samples — and it is the test that would have
    caught the ``servico`` collision had it existed when that profile was
    written.
    """
    ties = []
    for path in sorted(CORPUS.glob("*.docx")):
        if not path.stem.startswith(("sc_", "sci_", "sd_")):
            continue
        scored = score_profiles(read_docx(path))
        if scored[0][1] == scored[1][1]:
            ties.append((path.stem, scored[0][0].name, scored[1][0].name))

    assert ties == []


@requires_corpus
def test_sc_cosit_flatness_falls():
    """The cycle's headline (deliverable 3), rules-only per the user's Q-2.

    Measured before this cycle: **58 of 109** ``sc_cosit`` documents rendered
    flat under ``--referee=none``. The bound asserted here is deliberately
    loose — the claim is that the skeleton is now *read*, not that a particular
    count is sacred, and a brittle equality would fail the day one document's
    segmentation improves.
    """
    from lexml_nonstat.model import build_model

    flat = 0
    total = 0
    for path in sorted(CORPUS.glob("sc_cosit_*.docx")):
        total += 1
        model = build_model(read_docx(path), filename=path.name)
        if bool(getattr(model.body, "flat", True)):
            flat += 1

    assert total == 109
    assert flat < 58, "sc_cosit flatness did not fall"
    # Measured at 33 when the cycle landed. A generous ceiling, so this fails
    # on a regression rather than on ordinary drift.
    assert flat <= 40, f"sc_cosit flatness regressed to {flat}"


@requires_corpus
def test_a_solucao_gains_its_skeleton_end_to_end():
    """One real document, through the public entry point, with no referee.

    The unit tests above build synthetic bodies; this proves the wiring holds
    on a document nobody arranged — profile selection, segmentation, declared
    headings and tree building all composing.
    """
    result = infer_hierarchy(_corpus_doc("sc_cosit_102_20140407"))

    assert result.profile == "solucao_consulta"
    assert result.body.flat is False
    headings = [s.heading for s in result.body.sections]
    assert "Relatório" in headings
    assert "Fundamentos" in headings
    assert "Conclusão" in headings
