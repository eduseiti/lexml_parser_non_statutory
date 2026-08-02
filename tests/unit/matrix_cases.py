"""The §2.1 encoding matrix, as data.

Each row of the plan's table §2.1 ("`OpenStructure` cannot nest") becomes one
case here. The table is the empirical basis for the whole design — it is why
hierarchy must be carried out-of-band in the `id` path — so it is pinned as an
executable test rather than left as prose. If a schema revision changes any of
these answers, the corresponding assumption in the plan has broken, and the
test names say which.

``expected`` is the validity on **both** schemas: §2.8 established that the two
schemas do not differ anywhere on this surface, and `test_schema_matrix`
asserts that agreement explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.conftest import lexml_doc


@dataclass(frozen=True)
class MatrixCase:
    row: str          # the plan's row label
    encoding: str     # the plan's description, verbatim
    fragment: str     # body of the LexML document
    expected: bool    # valid on both schemas?
    generico: bool    # part of the OpenStructure surface? (§2.8 agreement)

    @property
    def id(self) -> str:
        return f"{self.row}-{self.encoding}"

    @property
    def document(self) -> str:
        return lexml_doc(self.fragment)


def _artigo(num: str = "1") -> str:
    """A well-formed Artigo: Rotulo first, Caput carrying its own Rotulo."""
    return (
        f'<Artigo id="art{num}"><Rotulo>Art. {num}º</Rotulo>'
        f'<Caput id="art{num}_cpt"><Rotulo>Art. {num}º</Rotulo>'
        f"<p>Texto do artigo.</p></Caput></Artigo>"
    )


MATRIX: tuple[MatrixCase, ...] = (
    MatrixCase(
        "A", "DocumentoGenerico/PartePrincipal/p",
        '<DocumentoGenerico><PartePrincipal id="pp1"><p>Texto</p>'
        "</PartePrincipal></DocumentoGenerico>",
        True, True,
    ),
    MatrixCase(
        "B", "PartePrincipal/Agrupamento[@nome]/p",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<Agrupamento id="pp1_agr1" nome="secao"><p>Texto</p></Agrupamento>'
        "</PartePrincipal></DocumentoGenerico>",
        True, True,
    ),
    MatrixCase(
        "C", "Agrupamento inside Agrupamento",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<Agrupamento id="pp1_agr1" nome="secao">'
        '<Agrupamento id="pp1_agr1_agr1" nome="subsecao"><p>Texto</p></Agrupamento>'
        "</Agrupamento></PartePrincipal></DocumentoGenerico>",
        False, True,
    ),
    MatrixCase(
        "D", "div inside div",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<div id="div1"><div id="div2"><p>Texto</p></div></div>'
        "</PartePrincipal></DocumentoGenerico>",
        False, True,
    ),
    MatrixCase(
        "E", "AgrupamentoHierarquico containing p",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<AgrupamentoHierarquico id="agh1" nome="tema"><p>Texto</p>'
        "</AgrupamentoHierarquico></PartePrincipal></DocumentoGenerico>",
        False, True,
    ),
    MatrixCase(
        "F", "AgrupamentoHierarquico without articulated descendant",
        "<Norma><Articulacao>"
        '<AgrupamentoHierarquico id="agh1" nome="tema"/>'
        "</Articulacao></Norma>",
        False, False,
    ),
    MatrixCase(
        "G", "sibling Agrupamento + Agrupamento (flat)",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<Agrupamento id="pp1_agr1" nome="secao"><p>Um</p></Agrupamento>'
        '<Agrupamento id="pp1_agr2" nome="secao"><p>Dois</p></Agrupamento>'
        "</PartePrincipal></DocumentoGenerico>",
        True, True,
    ),
    MatrixCase(
        "H", "PartePrincipal/ol/li with nested li/ol",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        "<ol><li>primeiro item</li>"
        "<li>segundo item<ol><li>subitem</li></ol></li></ol>"
        "</PartePrincipal></DocumentoGenerico>",
        True, True,
    ),
    MatrixCase(
        "I", "Norma without Articulacao",
        '<Norma><ParteInicial><Epigrafe id="epi1">Epigrafe</Epigrafe>'
        "</ParteInicial></Norma>",
        False, False,
    ),
    MatrixCase(
        "J", "Capitulo/Artigo(Rotulo,Caput)",
        "<Norma><Articulacao>"
        '<Capitulo id="cap1"><Rotulo>CAPÍTULO I</Rotulo>'
        "<NomeAgrupador>DAS DISPOSIÇÕES PRELIMINARES</NomeAgrupador>"
        f"{_artigo()}</Capitulo>"
        "</Articulacao></Norma>",
        True, False,
    ),
    MatrixCase(
        "K", "AgrupamentoHierarquico[@nome]/Artigo(Rotulo,Caput)",
        "<Norma><Articulacao>"
        '<AgrupamentoHierarquico id="agh1" nome="tema">'
        f"{_artigo()}</AgrupamentoHierarquico>"
        "</Articulacao></Norma>",
        True, False,
    ),
    MatrixCase(
        "L", "ParteInicial + Articulacao + ParteFinal",
        "<Norma>"
        '<ParteInicial><Epigrafe id="epi1">Portaria MF nº 277</Epigrafe>'
        '<Ementa id="eme1">Atribui efeito vinculante.</Ementa></ParteInicial>'
        f"<Articulacao>{_artigo()}</Articulacao>"
        "<ParteFinal><Assinatura>"
        "<NomePessoa>EDUARDO REFINETTI GUARDIA</NomePessoa>"
        "</Assinatura></ParteFinal>"
        "</Norma>",
        True, False,
    ),
    MatrixCase(
        "M", "DocumentoGenerico + Anexos/ReferenciaAnexo",
        '<DocumentoGenerico><PartePrincipal id="pp1"><p>Texto</p></PartePrincipal>'
        "<Anexos><ReferenciaAnexo "
        'AlvoURN="urn:lex:br:federal:parecer:2018-12-28;93!anexo1"/></Anexos>'
        "</DocumentoGenerico>",
        True, True,
    ),
    MatrixCase(
        "N", "table/tr/td with inline text",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<table id="tab1"><tr><td>SERVIÇO</td></tr></table>'
        "</PartePrincipal></DocumentoGenerico>",
        True, True,
    ),
    MatrixCase(
        "O", "table/tr/td/p",
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<table id="tab1"><tr><td><p>SERVIÇO</p></td></tr></table>'
        "</PartePrincipal></DocumentoGenerico>",
        False, True,
    ),
    MatrixCase(
        "P", "Artigo/DispositivoGenerico",
        "<Norma><Articulacao>"
        '<Artigo id="art1"><Rotulo>Art. 1º</Rotulo>'
        '<Caput id="art1_cpt"><Rotulo>Art. 1º</Rotulo><p>Texto</p></Caput>'
        '<DispositivoGenerico id="art1_dpg1"><p>Genérico</p></DispositivoGenerico>'
        "</Artigo></Articulacao></Norma>",
        False, False,
    ),
)

#: Rows of the plan's §2.1 table. Pinned so a row cannot be silently dropped.
PLAN_ROW_COUNT = 16
