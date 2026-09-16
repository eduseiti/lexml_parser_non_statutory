"""Court-decision covers: STF acórdãos and their LexML URN.

A court acórdão identifies itself by a *cover* rather than an epigraph::

    06/06/2022 PLENÁRIO
    AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DISTRITO FEDERAL

and LexML names it ``urn:lex:br:<tribunal>;<órgão>:acordao;<classe>:<data>;<n>``.
Before this fix all three STF documents in the corpus fell to the ``generic``
profile and emitted ``urn:lex:br:federal:documento:<data>;0``.

See ``docs/20260916_204656_stf_acordao_cover_urn_and_ementa_heading.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara, read_docx
from lexml_nonstat.model.metadata import extract_metadata
from lexml_nonstat.model.urn import is_valid_urn
from lexml_nonstat.profile import get_profile, select_profile
from lexml_nonstat.segment.frontmatter import find_ementa

CORPUS = Path(__file__).resolve().parents[3] / "br-taxqa-r_v2.0" / "original" / "nao_articulados"

requires_corpus = pytest.mark.skipif(
    not CORPUS.is_dir(),
    reason=f"the corpus is not present at {CORPUS} (research data, not a fixture)",
)


def _doc(*texts: str) -> StyledDoc:
    return StyledDoc(
        blocks=tuple(
            StyledPara(inlines=(Inline(text=t),), index=i) for i, t in enumerate(texts)
        ),
        source="synthetic.docx",
    )


_ACORDAO_TAIL = (
    "EMENTA",
    "Ação direta de inconstitucionalidade. Direito tributário.",
    "ACÓRDÃO",
    "Vistos, relatados e discutidos estes autos, acordam os Ministros do "
    "Supremo Tribunal Federal, em sessão virtual do Plenário.",
    "Brasília, 6 de junho de 2022.",
)


# ---------------------------------------------------------------------------
# 1. synthetic covers — no corpus needed
# ---------------------------------------------------------------------------


def test_adi_cover_yields_the_lexml_acordao_urn():
    doc = _doc(
        "06/06/2022 PLENÁRIO",
        "AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DISTRITO FEDERAL",
        *_ACORDAO_TAIL,
    )
    assert select_profile(doc).name == "jurisprudencia_generico"
    m = extract_metadata(doc)
    assert m.urn == "urn:lex:br:supremo.tribunal.federal;plenario:acordao;adi:2022-06-06;5422"
    assert m.complete
    assert (m.authority_source, m.date_source, m.number_source) == ("cover", "cover", "cover")
    assert m.epigraph_index == 1
    assert is_valid_urn(m.urn)


@pytest.mark.parametrize(
    ("stamp", "class_line", "expected"),
    [
        pytest.param(
            "15/03/2021 PLENÁRIO",
            "RECURSO EXTRAORDINÁRIO 855.091 RIO GRANDE DO SUL",
            "supremo.tribunal.federal;plenario:acordao;re:2021-03-15;855091",
            id="re",
        ),
        pytest.param(
            "01/02/2020 PRIMEIRA TURMA",
            "RECURSO EXTRAORDINÁRIO COM AGRAVO 1.234 SÃO PAULO",
            "supremo.tribunal.federal;primeira.turma:acordao;are:2020-02-01;1234",
            id="are-before-re",
        ),
        pytest.param(
            "10/10/2019 PLENÁRIO",
            "AÇÃO DIRETA DE INCONSTITUCIONALIDADE POR OMISSÃO 26 DISTRITO FEDERAL",
            "supremo.tribunal.federal;plenario:acordao;ado:2019-10-10;26",
            id="ado-before-adi",
        ),
    ],
)
def test_class_and_body_vocabulary(stamp: str, class_line: str, expected: str):
    m = extract_metadata(_doc(stamp, class_line, *_ACORDAO_TAIL))
    assert m.urn == f"urn:lex:br:{expected}"


def test_letter_spaced_acordao_heading_still_counts():
    """`adi_5583_STF` writes the heading ``A C Ó R D Ã O``."""
    tail = tuple("A C Ó R D Ã O" if t == "ACÓRDÃO" else t for t in _ACORDAO_TAIL)
    doc = _doc("17/05/2021 PLENÁRIO", "AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.583 DF", *tail)
    assert ":acordao;adi:" in extract_metadata(doc).urn


def test_without_acordao_heading_the_type_is_the_class():
    """A cover alone does not make the document the court's acórdão."""
    tail = tuple(t for t in _ACORDAO_TAIL if t != "ACÓRDÃO")
    doc = _doc("06/06/2022 PLENÁRIO", "AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DF", *tail)
    m = extract_metadata(doc)
    assert m.doc_type == "acao.direta.inconstitucionalidade"
    assert m.authority == "supremo.tribunal.federal;plenario"


def test_without_court_name_the_authority_is_not_invented():
    tail = tuple(t for t in _ACORDAO_TAIL if "Supremo" not in t)
    doc = _doc("06/06/2022 PLENÁRIO", "AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DF", *tail)
    m = extract_metadata(doc)
    assert m.authority is None
    assert "authority" in m.missing


@pytest.mark.parametrize(
    "stamp",
    [
        pytest.param("06/06/2022", id="bare-date"),
        pytest.param("06/06/2022 BRASÍLIA", id="unknown-body"),
    ],
)
def test_a_stamp_without_a_known_body_is_not_a_cover(stamp: str):
    doc = _doc(stamp, "AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DF", *_ACORDAO_TAIL)
    m = extract_metadata(doc, profile="jurisprudencia_generico")
    assert m.authority_source != "cover"
    assert m.number_source != "cover"


def test_a_class_name_without_a_number_does_not_claim_the_genre():
    doc = _doc("Recurso extraordinário. Repercussão geral. Imposto de renda.")
    assert get_profile("jurisprudencia_generico").score(doc) == 0.0


def test_the_cover_is_inert_on_other_profiles():
    doc = _doc("06/06/2022 PLENÁRIO", "AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DF", *_ACORDAO_TAIL)
    m = extract_metadata(doc, profile="generic")
    assert "cover" not in (m.authority_source, m.date_source, m.number_source)


# ---------------------------------------------------------------------------
# 2. the bare EMENTA heading is a section header, not the ementa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("heading", ["EMENTA", "E M E N T A", "Ementa."])
def test_bare_ementa_heading_is_not_claimed_as_the_ementa(heading: str):
    doc = _doc("AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DF", heading, "Texto da ementa.")
    assert find_ementa(doc, get_profile("jurisprudencia_generico"), after=0) is None


def test_labelled_ementa_is_unaffected():
    doc = _doc("PORTARIA Nº 1", "EMENTA: Texto da ementa.")
    span = find_ementa(doc, get_profile("generic"), after=0)
    assert span is not None and span.start == 1


# ---------------------------------------------------------------------------
# 3. the corpus documents that motivated the fix
# ---------------------------------------------------------------------------


@requires_corpus
@pytest.mark.parametrize(
    ("stem", "urn"),
    [
        (
            "adi_5422_STF",
            "urn:lex:br:supremo.tribunal.federal;plenario:acordao;adi:2022-06-06;5422",
        ),
        (
            "adi_5583_STF",
            "urn:lex:br:supremo.tribunal.federal;plenario:acordao;adi:2021-05-17;5583",
        ),
        (
            "re_855091_tema_808",
            "urn:lex:br:supremo.tribunal.federal;plenario:acordao;re:2021-03-15;855091",
        ),
    ],
)
def test_corpus_stf_acordaos(stem: str, urn: str):
    path = CORPUS / f"{stem}.docx"
    if not path.is_file():
        pytest.skip(f"{path.name} not in the corpus")
    m = extract_metadata(read_docx(path), filename=path.name)
    assert m.profile == "jurisprudencia_generico"
    assert m.urn == urn
    assert m.complete
