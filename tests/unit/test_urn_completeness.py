"""URN completeness and identity — Cycle 2 of the corpus-233 hardening plan.

The 233-document measuring run found 46 documents whose URN carried a sentinel
or a defaulted component, and — worse — four whose URN was **confidently
wrong**: they named a *cited* document's number as their own. A sentinel is
honest and a consumer can see it; a wrong number looks exactly like a right one.

This module pins the four repairs that distinction motivated:

1. **A path-form epigraph is the document's own** (``NOTA PGFN/CRJ/Nº
   1114/2012``). Before Cycle 2 the type group forbade ``/``, so the line did
   not match, the scan fell through, and paragraph 2's citation of another act
   became the document's identity.
2. **A filename may supply a number**, at A-2.1's last-resort rank, recorded in
   ``number_source`` so it is never mistaken for a document-derived value.
3. **A service description's identity is its name.** Six taxpayer-facing pages
   state no number or date in any form; A-2.3's sentinels collapsed all six onto
   one URN, the corpus's only collision.
4. **One profile may cover several document kinds.** ``jurisprudencia_generico``
   serves súmulas, acórdãos, recursos and ADIs, and a single fixed ``urn_type``
   made every one of them a ``sumula``.

The corpus documents these run against are **not** in `samples/`, so the tests
that need one are skipped when the corpus is absent — the same graceful
degradation `requires_nested` and `requires_linker` apply to the other two
external things this repository works without.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.ingest import Inline, StyledPara, read_docx
from lexml_nonstat.model.metadata import (
    _number_from_filename,
    _number_looks_like_citation,
    _service_slug,
    extract_metadata,
)
from lexml_nonstat.model.urn import build_urn, is_valid_urn, parse_urn
from lexml_nonstat.profile import get_profile

#: The 233-document corpus this cycle measured. Outside the repository by
#: design — it is research data, not a fixture — so every assertion that needs a
#: real document skips without it rather than failing.
CORPUS = Path(__file__).resolve().parents[3] / "br-taxqa-r_v2.0" / "original" / "nao_articulados"

requires_corpus = pytest.mark.skipif(
    not CORPUS.is_dir(),
    reason=f"the 233-document corpus is not present at {CORPUS} (research data, not a fixture)",
)


def _meta(stem: str):
    return extract_metadata(read_docx(CORPUS / f"{stem}.docx"), filename=f"{stem}.docx")


def _para(text: str) -> StyledPara:
    """One paragraph carrying ``text``. ``StyledPara.text`` is derived from its
    inlines, so a test paragraph is built the way the reader builds one."""
    return StyledPara(inlines=(Inline(text=text),), index=0)


# ---------------------------------------------------------------------------
# 1. a citation is not an identity (G-1, G-4)
# ---------------------------------------------------------------------------


@requires_corpus
def test_path_form_epigraph_is_read_as_the_documents_own():
    """``NOTA PGFN/CRJ/Nº 1114/2012`` identifies *this* document.

    The number is 1114 and the year 2012 — both stated on the document's own
    first line. Before Cycle 2 this URN read ``…:portaria:0000;294``, taken from
    a citation on the *following* paragraph.
    """
    m = _meta("nota_pgfn_crj_1114_2012")
    assert m.number == "1114", (
        f"the document's own number is 1114; got {m.number!r} from {m.epigraph!r}"
    )


@requires_corpus
def test_a_citation_is_not_read_as_identity():
    """The act a document *cites* must never become the act it *is*.

    `nota_pgfn_crj_1114_2012`'s second paragraph opens "Portaria PGFN Nº
    294/2010. Parecer PGFN/CDA Nº 2025/2011." — the subject of the nota, not the
    nota. 294 appearing as this document's number is the exact defect §2.2
    records.
    """
    m = _meta("nota_pgfn_crj_1114_2012")
    assert m.number != "294", (
        "the document's number is the one it cites, not the one it states — the "
        "epigraph scan fell through to a citation"
    )


def test_citation_cue_distinguishes_a_summary_from_an_epigraph():
    """The guard fires on a list of cited acts and not on a plain epigraph."""
    assert _number_looks_like_citation(
        "Portaria PGFN Nº 294/2010. Parecer PGFN/CDA Nº 2025/2011."
    )
    assert not _number_looks_like_citation("NOTA PGFN/CRJ/Nº 1114/2012")
    assert not _number_looks_like_citation("PORTARIA MF nº 277, de 7 de junho de 2018")
    assert not _number_looks_like_citation(
        "Solução de Consulta Cosit nº 100, de 28 de setembro de 2020"
    )


# ---------------------------------------------------------------------------
# 2. the authority the document actually names (G-2, m-5)
# ---------------------------------------------------------------------------


@requires_corpus
def test_cosar_resolves_its_authority():
    """`ad_cosar_47` named no authority the map knew, so it fell to `federal`."""
    m = _meta("ad_cosar_47_20001127")
    assert m.authority == "ministerio.fazenda;secretaria.receita.federal"
    assert ":federal:" not in m.urn


@requires_corpus
def test_mesa_do_congresso_resolves_from_the_preamble():
    """The epigraph wraps across two paragraphs, so only the preamble can say.

    "ATO DECLARATÓRIO DO PRESIDENTE DA MESA DO" / "CONGRESSO NACIONAL Nº 38, DE
    2005" — no sigla map could ever match that, which is why the fix is a
    preamble pattern rather than another map entry.
    """
    m = _meta("ad_mesa_cn_38_20051014")
    assert m.authority == "congresso.nacional"
    assert m.authority_source == "preamble"


@requires_corpus
def test_solucao_de_consulta_authority_is_not_federal():
    """53% of the corpus stated its issuer and was recorded as `federal` anyway."""
    m = _meta("sc_cosit_100_20200928")
    assert m.authority == "ministerio.fazenda;secretaria.receita.federal"
    assert ":federal:" not in m.urn


# ---------------------------------------------------------------------------
# 3. the filename, at last resort only (G-3)
# ---------------------------------------------------------------------------


def test_number_from_filename_reads_the_corpus_convention():
    """The shape 209 of 233 corpus filenames follow."""
    assert _number_from_filename("sc_15_20090309.docx") == "15"
    assert _number_from_filename("ad_cosar_47_20001127.docx") == "47"
    assert _number_from_filename("parecer_pgfn_crj_701_2016.docx") == "701"


def test_a_four_digit_year_is_not_a_number():
    """``parecer_pgfn_crj_701_2016`` is number 701 of 2016, not number 2016.

    Both trailing date shapes the corpus uses are accepted — a full
    ``YYYYMMDD`` and a bare year — and in both the *number* is what comes back.
    Written before the helper handled the bare-year form, and it caught that:
    the four `_YYYY` documents were being recovered by the epigraph fix alone.
    """
    assert _number_from_filename("parecer_pgfn_crj_701_2016.docx") == "701"
    assert _number_from_filename("nota_pgfn_crj_1104_2017.docx") == "1104"
    assert _number_from_filename("sc_15_20090309.docx") == "15"


def test_number_from_filename_declines_what_it_cannot_read():
    """No convention, no number — silence beats a guess."""
    assert _number_from_filename("declaracao_benficios_fiscais_DBF.docx") is None
    assert _number_from_filename(None) is None


@requires_corpus
def test_filename_number_is_recorded_as_such():
    """Provenance is the whole point: a filename number must be visible as one.

    Plan deliverable 2 — "recorded with its own `*_source` provenance value so a
    filename-derived component is never mistaken for a document-derived one".
    """
    m = _meta("sc_15_20090309")
    assert m.number == "15"
    assert m.number_source == "filename"


@requires_corpus
def test_a_body_number_outranks_the_filename():
    """A-2.1's rank, preserved: the document's own word wins.

    `port_mf_277_20180607` states 277 and its filename agrees, so the test that
    matters is the *source*, not the value — it must be the epigraph.
    """
    doc = Path(__file__).resolve().parents[1] / ".." / "samples" / "port_mf_277_20180607.docx"
    m = extract_metadata(read_docx(doc), filename="port_mf_277_20180607.docx")
    assert m.number == "277"
    assert m.number_source == "epigraph", (
        "a filename must never pre-empt a number the document states itself"
    )


# ---------------------------------------------------------------------------
# 4. a service description's identity is its name (G-5)
# ---------------------------------------------------------------------------


def test_service_slug_comes_from_the_documents_own_line():
    """The acronym each page states, not its filename."""
    assert _service_slug([_para("Declaração de Benefícios Fiscais — DBF")]) == "dbf"
    assert (
        _service_slug([_para("Sistema de Recolhimento Mensal Obrigatório (Carnê-Leão)")])
        == "carne.leao"
    )
    assert _service_slug([_para("Declaração sobre Operações Imobiliárias (DOI)")]) == "doi"


def test_service_slug_declines_a_document_without_the_shape():
    """A document reaching `servico` without being one of these pages keeps ``;0``.

    Silence rather than a fabricated identity — the same reasoning A-2.2 applies
    to field capture: a missed value is recoverable, a false one is corruption.
    """
    assert _service_slug([_para("Uma linha qualquer sem sigla")]) is None


@requires_corpus
def test_the_six_service_documents_get_distinct_urns():
    """The corpus's only URN collision, closed.

    Six documents shared ``…:servico:0000;0`` — every one of them claiming the
    same identity to any consumer keyed on URN rather than filename.
    """
    stems = [
        "declaracao_benficios_fiscais_DBF",
        "declaracao_de_informacoes_sobre_atividades_imobiliarias_DIMOB",
        "declaracao_de_servicos_medicos_e_de_saude_DMED",
        "declaracao_sobre_operacoes_imobiliarias_DOI",
        "declaração_de_imposto_de_renda_retido_na_fonte_DIRF",
        "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO",
    ]
    urns = {stem: _meta(stem).urn for stem in stems if (CORPUS / f"{stem}.docx").exists()}
    assert len(urns) == 6, f"expected all six service documents, found {len(urns)}"
    assert len(set(urns.values())) == 6, (
        f"the six service descriptions still share an identity: {urns}"
    )
    for urn in urns.values():
        assert is_valid_urn(urn), urn


def test_a_slug_urn_round_trips():
    """The grammar's own parser reads back what its builder wrote (A-2.3's rule)."""
    urn = build_urn(
        authority="ministerio.fazenda;secretaria.receita.federal",
        doc_type="servico",
        date=None,
        number="carne.leao",
    )
    assert parse_urn(urn).number == "carne.leao"
    assert parse_urn(urn).date.is_unknown


# ---------------------------------------------------------------------------
# 5. one profile, several document kinds (G-6)
# ---------------------------------------------------------------------------


@requires_corpus
def test_an_acordao_is_not_a_sumula():
    """`REsp_1306393` is a recurso especial; it used to claim ``:sumula:``."""
    m = _meta("REsp_1306393")
    assert m.doc_type == "recurso.especial", (
        f"an acórdão is not a súmula; got {m.doc_type!r}"
    )


def test_a_profile_without_type_patterns_is_unchanged():
    """`urn_type_for` must be inert for the profiles that declare no patterns.

    This is what makes G-6 additive: six of the seven profiles carry no
    `urn_type_res` and must answer exactly `urn_type`, as they did before.
    """
    for name in ("parecer", "portaria", "ato_declaratorio", "servico", "generic"):
        profile = get_profile(name)
        assert profile.urn_type_res == ()
        assert profile.urn_type_for("qualquer epígrafe") == profile.urn_type
        assert profile.urn_type_for(None) == profile.urn_type


def test_jurisprudencia_reads_its_type_off_the_epigraph():
    """Each of the four kinds the profile serves resolves to its own type."""
    profile = get_profile("jurisprudencia_generico")
    cases = {
        "SÚMULA N. 125": "sumula",
        "RECURSO ESPECIAL Nº 1.306.393 - DF": "recurso.especial",
        "AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422": "acao.direta.inconstitucionalidade",
        "HABEAS CORPUS Nº 1234": "habeas.corpus",
    }
    for epigraph, expected in cases.items():
        assert profile.urn_type_for(epigraph) == expected, epigraph


# ---------------------------------------------------------------------------
# 6. the corpus-wide properties the cycle exists to establish
# ---------------------------------------------------------------------------


@requires_corpus
def test_no_two_corpus_documents_share_a_urn():
    """Cycle 2's headline exit criterion, asserted over all 233 documents.

    Slow (it parses the whole corpus), but this is the one property that cannot
    be established from any single document, and §1.5's silent overwrite is
    exactly what happens when it goes unchecked.
    """
    urns: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for path in sorted(CORPUS.glob("*.docx")):
        urn = extract_metadata(read_docx(path), filename=path.name).urn
        if urn in urns.values():
            collisions.setdefault(urn, [k for k, v in urns.items() if v == urn]).append(path.stem)
        urns[path.stem] = urn

    assert not collisions, (
        "two or more corpus documents claim one identity, which makes them "
        f"indistinguishable to any URN-keyed consumer: {collisions}"
    )


@requires_corpus
def test_every_corpus_document_produces_a_valid_urn():
    """Extraction never raises and never emits an ungrammatical URN (A-2.3)."""
    for path in sorted(CORPUS.glob("*.docx")):
        urn = extract_metadata(read_docx(path), filename=path.name).urn
        assert is_valid_urn(urn), f"{path.stem}: {urn!r}"
