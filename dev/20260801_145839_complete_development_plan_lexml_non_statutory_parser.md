# Complete Development Plan — LexML Parser for Non-Statutory Documents

- **Date:** 2026-08-01
- **Status:** Consolidated and approved plan — supersedes the open questions of both predecessor documents
- **Target language:** Python 3
- **Predecessors (investigation record, retained for traceability):**
  - `docs/20260801_004745_lexml_non_statutory_parser_investigation_and_development_plan.md` — schema investigation, validation matrix A–R
  - `docs/20260801_142630_design_review_segmentation_statutory_detection_and_lm_support.md` — segmentation proof, statutory detection, LM analysis, recursive `Agrupamento` proposal
- **Reference implementation:** `../lexml-parser-projeto-lei` (Scala, Senado Federal)
- **Schemas:** `lexml/lexml-base.xsd`, `lexml/lexml-br-rigido.xsd`, `lexml/lexml09-flexivel.xsd`

---

## 0. Decisions Ratified in This Round

The user's answers closing the second design review:

| # | Question | Decision |
|---|---|---|
| 1 | `port_mf_277` routing | **Split into `Norma` + `Anexo`** — matches what the statutory LexML parser already does |
| 2 | Jurisprudence scope | **No `Jurisprudencia` emitter.** Súmulas and acórdãos route to `generico`, because many documents stop at the acórdão part and cannot satisfy `Acordao`'s required children |
| 3 | LLM support | **Include from the start.** The 15 samples are a sample of **300+** documents with widely varying structure. **Logs must always state when rules failed and the LLM referee changed the decision**, so rule effectiveness stays measurable |
| 4 | §7.1 routing table | The three `jurisprudencia` entries become **`generico`** (consequence of #2) |

Carried forward from earlier rounds: `generico` is the default emitter; dual-schema validation is kept; RAG integration is out of scope.

Decision #3 changes the character of the project. The LLM is no longer a deferred option for a single residual case — it is a first-class component from Cycle 4b onward, with **observability as an explicit requirement**. Rule-vs-referee disagreement telemetry is a deliverable, not a debugging aid: it is how we learn whether the deterministic rules generalise from 15 samples to 300+.

---

## 1. Objective and Scope

Build a Python parser converting Brazilian legal **non-statutory documents** ("documentos não articulados") into valid LexML XML, preserving every hierarchical element present in the source — chapters, sections, subsections, numbered and bulleted lists — while extracting the statute-like front matter these documents typically carry (publication authority, publication date, numbering, epigraph, ementa, preamble, enacting formula, signatures).

**In scope:** DOCX (primary), HTML, plain text; the three routing targets of §4; hierarchical segmentation output; LLM referee with telemetry; dual-schema validation; a regression suite.

**Out of scope:** RAG chunking/embedding (deferred by decision); the `Jurisprudencia` document type (deferred by decision); modifying the LexML schemas (a proposal exists — §11 — but the parser must work against the schemas as shipped).

---

## 2. Findings That Constrain the Design

Established empirically across the two investigation rounds. These are load-bearing; each one changed the design.

### 2.1 `OpenStructure` cannot nest

LexML supports non-statutory documents via `OpenStructure` (`<DocumentoGenerico>`), the counterpart of `HierarchicalStructure` (`<Norma>`). But it is deliberately flat. Verified against both schemas:

| Candidate encoding | rigido | flexivel |
|---|---|---|
| `DocumentoGenerico/PartePrincipal/p` | PASS | PASS |
| `PartePrincipal/Agrupamento[@nome]/p` | PASS | PASS |
| `Agrupamento` inside `Agrupamento` | **FAIL** | **FAIL** |
| `div` inside `div` | **FAIL** | **FAIL** |
| `AgrupamentoHierarquico` containing `<p>` | **FAIL** | **FAIL** |
| `AgrupamentoHierarquico` without articulated descendant | **FAIL** | **FAIL** |
| sibling `Agrupamento` + `Agrupamento` (flat) | PASS | PASS |
| `PartePrincipal/ol/li` with nested `li/ol` | PASS | PASS |
| `Norma` without `Articulacao` | **FAIL** | **FAIL** |
| `Capitulo/Artigo(Rotulo,Caput)` | PASS | PASS |
| `AgrupamentoHierarquico[@nome]/Artigo(Rotulo,Caput)` | PASS | PASS |
| `ParteInicial` + `Articulacao` + `ParteFinal` | PASS | PASS |
| `DocumentoGenerico` + `Anexos/ReferenciaAnexo` | PASS | PASS |
| `table/tr/td` with inline text | PASS | PASS |
| `table/tr/td/p` | **FAIL** | **FAIL** |
| `Artigo/DispositivoGenerico` | **FAIL** | **FAIL** |

Root cause: `Agrupamento` and `div` derive from `blocksreq`, whose content group `blockElements` = `{p, ul, ol, table, Bloco, ConteudoExterno}` holds no container, making recursion structurally impossible. `AgrupamentoHierarquico` derives from `hierarchy` and requires `LXhierCompleto` (`Parte|Livro|Titulo|Capitulo|Secao|Subsecao|Artigo`) — a statutory device that always terminates in `Artigo` and cannot hold prose.

**Consequence:** LexML has no element that is both non-articulated and recursive. Hierarchy must be preserved out-of-band (§5.2).

### 2.2 Lists nest natively; `<td>` takes no `<p>`

`ol`/`ul` nest via `li → ol|ul` — the one place the open model preserves real depth, so lists need no flattening. Conversely `<td>` accepts inline content only. The reference parser's own output confirms this: `lei_5070_19660707.anexo1.xml` emits `<td>SERVIÇO</td>` with bare text throughout.

### 2.3 The `id` grammar is a sanctioned hierarchy channel

`lexml09-flexivel.xsd` defines `idAgregador` with an `agh` alternative at every aggregator level, composed with `_`:

```
(prt|agh)\d+
((prt|agh)\d+_)?(liv|agh)\d+
(((prt|agh)\d+_)?(liv|agh)\d+_)?(tit|agh)\d+   …  (cap|agh) … (sec|agh) … (sub|agh)
```

Path-composed ids are therefore idiomatic LexML, not a private convention. Note `Agrupamento`'s `id` is typed `xsd:ID` via `corereq`, **not** constrained to `idAgregador`, so our `pp…_agr…` scheme is free-form and uniqueness must be enforced by us.

### 2.4 Segmentation from `generico` works — proven

An XSLT 3.0 stylesheet run under Saxon against a `generico` document produced correct per-section rows with level, label, breadcrumb, text, and citable URN fragment, recovering ancestry from the `id` path. Verbatim output:

```csv
Tipo,Nivel,Rotulo,Breadcrumb,Texto,urn
secao,1,"2.","DAS SOCIEDADES COOPERATIVAS","Texto introdutorio da secao 2.",urn:…;38!pp1_agr1
subsecao,2,"2.1","DAS SOCIEDADES COOPERATIVAS | Empresas de servicos","Em linhas gerais…",urn:…;38!pp1_agr1_agr1
```

Two bugs surfaced in that experiment, now binding requirements:

- **Rule A — materialise intermediate levels.** An id of `pp1_agr1_agr2_agr1` with no `pp1_agr1_agr2` element produced a breadcrumb silently missing its middle ancestor. Every proper prefix of an `id` path must exist as an `Agrupamento`.
- **Rule B — leaf-only text extraction.** `string-join(descendant::p|descendant::li)` double-counts nested list text (`benssubitem subitem`). Select `li[not(ol|ul)]` and insert separators.

The existing `scripts/GeraCSVporArtigoPorAgrupador.xsl` cannot consume `generico` output — it selects `//Artigo`, `//Capitulo`, `//Secao` and walks `ancestor::*/NomeAgrupador`. A `generico` stylesheet is supplied instead (§6.2). Per the user, that script is illustrative, not a contract.

### 2.5 Statutory detection is required, and indentation is the discriminator

Naive paragraph-initial `Art. N` counting false-positives on **2 of 3** candidates across the 15 samples: `parecer_93_2018_decor_cgu_agu` (21 matches) and `par_cosit_26_20000629` (4 matches) are *opinions quoting statutes*. Articulating them would present the Constitution's `Art. 40` as an article of the parecer.

The originally-proposed leading-quotation-mark guard **fails on the real corpus** — quoted statutes appear as indented block quotes with no opening quote on the article line:

```
prev: A pretensão da Consultoria Jurídica junto ao Ministério…    ind=0
ART   Art. 40. Os pareceres do Advogado-Geral da União…          ind=2908   ← quoted
```

Measuring `w:ind/@w:left` against each document's modal body indent:

| Sample | modal indent | at body indent | indented ≫ | verdict |
|---|---|---|---|---|
| `parecer_93_2018_decor_cgu_agu` | 0 | **1** | **20** | non-statutory |
| `port_mf_277_20180607` | 0 | **2** | 0 | **statutory** |
| `par_cosit_26_20000629` | 0 | **4** | 0 | non-statutory (residual) |
| all others | 0 / 893 | 0 | 0 | non-statutory |

Indentation collapses the parecer from 21 spurious articles to 1 — a decisive correction to the first plan.

### 2.6 The residual hard case, and why the LLM is warranted

`par_cosit_26_20000629` resists indentation entirely; its quoted articles are introduced inline:

```
Lei nº 7.713, de 1988 - “Art. 1º- Os rendimentos e ganhos de capital percebidos…
Art. 2º- O imposto de renda das pessoas físicas será devido…      ind=0
Art. 16 - O custo de aquisição dos bens e direitos será o preço…  ind=0
Art. 52. ....................................................     ind=0
```

Three deterministic cues remain: **citation antecedent** (preceding paragraph names an external norm, then `“Art.`), **ellipsis runs** (`Art. 52. .........` is classic *omissis* of an excerpt, never of an original enactment), and **numbering monotonicity** (real articulation runs `1º, 2º, 3º…` from 1; this jumps `1º, 2º, 3º, 16, 52`).

These likely resolve this document — but with 300+ documents of varying structure, the deterministic rule set cannot be assumed complete. This is the empirical basis for decision #3.

### 2.7 Genre priors are priors, not rules

| Genre | Samples | Articulated? |
|---|---|---|
| Portaria / Resolução | `port_mf_277` | **often yes** |
| Portaria (older, item-based) | `port_mf_454` | **no** — `1.`, `2.1`, `a)` |
| Ato Declaratório (Normativo) | `ad_*`, `adn_*` | no — `DECLARA` + incisos |
| Parecer (Normativo) | `par_cosit_26`, `pn_cst_38`, `parecer_93` | no — quotes statutes |
| Súmula / Acórdão | `sumula_*`, `REsp_1306393` | no |

`port_mf_454_19770825` is a Portaria that is *not* articulated, so genre alone cannot decide — it informs a prior only.

### 2.8 Dual-schema validation is nearly free

`lexml09-flexivel.xsd` redefines only `idArtigo`/`idAgregador`, `DispositivoType`, and `AlteracaoType`; `lexml-br-rigido.xsd` redefines the same types more strictly. **Neither touches `OpenStructure`, `PartePrincipal`, `Agrupamento`, `Bloco`, `div`, or the HTML block elements** — the entire `generico` surface. Hence every case above behaved identically on both. Divergence can only arise on the `norma` route (relaxed `id` patterns, e.g. `Art. 1º-A`), where it is a useful signal.

### 2.9 The reference parser's `Anexo` convention (to be matched)

Confirmed from `ProjetoLei.scala:49-64` and the emitted `lei_5070_19660707.anexo1.xml`:

- Each `Anexo` is a **standalone sibling document**: `<LexML><Metadado/><Anexo>…</Anexo></LexML>`.
- The parent holds only `<Anexos><ReferenciaAnexo AlvoURN="…!anexo1"/></Anexos>`.
- URN fragment is `!anexoN`; `PartePrincipal` id is `anexoN_pp`; tables get `anexoN_tabM`.
- Inside `<Anexo>`, the choice is `DocumentoArticulado` (when articulated) or `DocumentoGenerico`.
- `isArticulatedAnexo` (`LexmlRenderer.scala:415-427`) refuses the articulated route when top-level tables/OLs exist, because `Articulacao` accepts only `hierElements` and `Preambulo` only `<p>`.

Matching this exactly means our `Norma` + `Anexo` output is interoperable with existing statutory tooling.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ INGESTION              docx / html / txt  →  StyledDoc                   │
│  · python-docx + numbering.xml + styles.xml (basedOn inheritance)        │
│  · paragraph = text + style + list level + INDENT + runs(b/i/sup/sub)    │
│  · NFC normalisation, whitespace collapse                                │
├──────────────────────────────────────────────────────────────────────────┤
│ SEGMENTATION           StyledDoc → DocumentSections                      │
│  · profile regexes: front matter / body / back matter / named fields     │
├──────────────────────────────────────────────────────────────────────────┤
│ HIERARCHY INFERENCE    body → HierarchyTree                              │
│  · evidence fusion: style · numbering · label · typography · indent      │
│  · quotation guard (indent + citation antecedent + monotonicity)         │
│  · level unification; confidence; flat fallback                          │
├──────────────────────────────────────────────────────────────────────────┤
│ ROUTING                StatutoryViabilityAnalyzer            ★ Cycle 4b  │
│  · genre prior · article census · indent discrimination                  │
│  · numbering monotonicity · omissis/citation cues · coverage             │
│  · LLM REFEREE on low-confidence decisions (logged, cached)              │
├──────────────────────────────────────────────────────────────────────────┤
│ MODEL                  DocumentModel  (rendering-agnostic, typed)        │
├──────────────────────────────────────────────────────────────────────────┤
│ RENDERING              norma (+anexos)  |  generico  |  articulado-sint. │
│  · validate-then-fallback: statutory attempt → generico on failure       │
├──────────────────────────────────────────────────────────────────────────┤
│ VALIDATION             lxml XMLSchema × 2 (rigido + flexivel) + rules    │
├──────────────────────────────────────────────────────────────────────────┤
│ SEGMENTATION OUTPUT    model → hierarchical segments (API + XSLT)        │
├──────────────────────────────────────────────────────────────────────────┤
│ TELEMETRY              rule-vs-referee decision log            ★ Cycle 4b│
└──────────────────────────────────────────────────────────────────────────┘
```

Layout:

```
src/lexml_nonstat/
  ingest/      docx_reader.py  html_reader.py  txt_reader.py  styled.py
  profile/     base.py  parecer.py  ato_declaratorio.py  portaria.py
               nota_tecnica.py  servico.py  jurisprudencia_generico.py
               generic.py  registry.py
  segment/     frontmatter.py  backmatter.py  fields.py  sections.py
  hierarchy/   evidence.py  labels.py  quotation.py  tree.py  unify.py
  routing/     viability.py  coverage.py  genre.py
  referee/     protocol.py  null.py  api.py  local.py  cache.py  prompts.py
  model/       document.py  nodes.py  metadata.py  urn.py
  render/      generico.py  norma.py  anexo.py  articulado.py  common.py  ids.py
  validate/    schema.py  rules.py  report.py
  segmentation/ api.py  xslt/segment_generico.xsl  xslt/segment_norma.xsl
  telemetry/   decisions.py  report.py
  cli.py
tests/
  unit/  golden/  fixtures/  regression/  referee_fixtures/  conftest.py
```

### 3.1 Internal model

Rendering-agnostic by design — this is what lets three emitters and a possible fourth (§11) coexist without a rewrite.

```python
@dataclass
class Inline:
    text: str; bold: bool = False; italic: bool = False
    sup: bool = False; sub: bool = False; href: str | None = None

@dataclass
class Para:
    inlines: list[Inline]
    kind: Literal["prose","quote","citation","field","omissis"] = "prose"
    indent: int = 0                    # twips — load-bearing for the quotation guard

@dataclass
class ListNode:                        # nests natively in LexML (§2.2)
    ordered: bool
    items: list["ListItem"]

@dataclass
class ListItem:
    inlines: list[Inline]
    children: list["ListNode | Para"] = field(default_factory=list)

@dataclass
class Table:
    rows: list[list[list[Inline]]]     # cells hold INLINE content only (§2.2)

@dataclass
class Section:                         # the recursive hierarchy LexML lacks
    label: str | None                  # "1.1", "CAPÍTULO II", "c. 1)"
    heading: str | None
    level: int                         # normalised depth, 1-based
    kind: str                          # capitulo|secao|subsecao|tema|item|…
    body: list[Para | ListNode | Table]
    children: list["Section"]
    evidence: "Evidence"

@dataclass
class Dispositivo:                     # statutory route only
    rotulo: str
    kind: Literal["artigo","paragrafo","inciso","alinea","item","caput"]
    body: list[Para]
    children: list["Dispositivo"]

@dataclass
class Anexo:
    num: int
    titulo: Para | None
    body: list[Section | Para | ListNode | Table]
    articulated: bool = False
    @property
    def urn_fragment(self) -> str: return f"anexo{self.num}"

@dataclass
class DocumentModel:
    metadata: Metadata
    front: FrontMatter
    body: list[Section | Para | ListNode | Table]
    articulacao: list[Dispositivo]      # non-empty only on the norma route
    anexos: list[Anexo]
    back: BackMatter
    profile: str
    route: Literal["norma","generico"]
    viability: "StatutoryViability"
    decisions: list["DecisionRecord"]   # telemetry, incl. referee interventions
```

---

## 4. Routing

Three targets. `Jurisprudencia` is deliberately absent (decision #2).

```
                    StatutoryViabilityAnalyzer
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   route=norma          route=generico      route=norma + anexos
   full articulation    flat + id path      articles + sibling
   (+ ParteInicial/     (default)           Anexo documents
    ParteFinal)                             (port_mf_277)
```

### 4.1 Verdict object

```python
@dataclass
class StatutoryViability:
    route: Literal["norma", "generico"]
    confidence: float
    articles_found: int
    articles_quoted: int          # excluded by indent / citation / omissis cues
    numbering_monotonic: bool
    coverage: float               # fraction of body inside articulation
    has_anexos: bool
    blockers: list[str]           # e.g. "top-level table outside dispositivo"
    evidence: dict
    referee_consulted: bool
    referee_overrode: bool        # ← must appear in logs (decision #3)
```

### 4.2 Two safety rules

**Coverage gate.** Route to `norma` only when articulation covers most of the body. `port_mf_277` shows why: 2 genuine articles but 138 paragraphs, the bulk being `ANEXO ÚNICO` with 130+ `Súmula CARF nº N` entries. Articulating 2 articles and dumping 130 paragraphs into a preamble is worse than `generico`. The annex split (§4.3) is what makes the statutory route correct here — the articles cover most of the *main body* once the annex is separated.

**Validate-then-fallback.** Attempt the statutory render; if it fails schema validation or the conservation/coverage invariants, fall back to `generico` automatically and record why. This makes "prefer statutory when possible" safe by construction rather than by trusting the classifier.

### 4.3 `Norma` + `Anexo` split (decision #1)

Matching the reference parser exactly (§2.9):

**Primary document**

```xml
<LexML xmlns="http://www.lexml.gov.br/1.0">
  <Metadado><Identificacao URN="urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277"/></Metadado>
  <Norma>
    <ParteInicial>
      <Epigrafe id="epi1">Portaria MF nº 277, de 7 de junho de 2018</Epigrafe>
      <Ementa   id="eme1">Atribui a súmulas do CARF efeito vinculante…</Ementa>
      <Preambulo id="pre1"><p>O MINISTRO DE ESTADO DA FAZENDA, no uso das atribuições…</p></Preambulo>
    </ParteInicial>
    <Articulacao>
      <Artigo id="art1"><Rotulo>Art. 1º</Rotulo>
        <Caput id="art1_cpt"><Rotulo>Art. 1º</Rotulo><p>Fica atribuído às súmulas…</p></Caput>
      </Artigo>
      <Artigo id="art2"><Rotulo>Art. 2º</Rotulo>
        <Caput id="art2_cpt"><Rotulo>Art. 2º</Rotulo><p>Esta Portaria entra em vigor…</p></Caput>
      </Artigo>
    </Articulacao>
    <ParteFinal>
      <Assinatura><NomePessoa>EDUARDO REFINETTI GUARDIA</NomePessoa></Assinatura>
    </ParteFinal>
    <Anexos><ReferenciaAnexo AlvoURN="urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277!anexo1"/></Anexos>
  </Norma>
</LexML>
```

**Sibling annex document** (`…!anexo1`)

```xml
<LexML xmlns="http://www.lexml.gov.br/1.0">
  <Metadado><Identificacao URN="urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277!anexo1"/></Metadado>
  <Anexo>
    <DocumentoGenerico>
      <PartePrincipal id="anexo1_pp">
        <p>ANEXO ÚNICO</p>
        <Agrupamento id="anexo1_pp_agr1" nome="item">
          <Bloco nome="rotulo">Súmula CARF nº 1</Bloco>
          <Bloco nome="nivel">1</Bloco>
          <p>Importa renúncia às instâncias administrativas…</p>
        </Agrupamento>
        <!-- … one Agrupamento per súmula … -->
      </PartePrincipal>
    </DocumentoGenerico>
  </Anexo>
</LexML>
```

Verified: both shapes validate on both schemas (`ParteInicial`+`Articulacao`+`ParteFinal`; `DocumentoGenerico`+`Anexos/ReferenciaAnexo`).

### 4.4 Expected routing — ground truth for Cycle 4b

Updated per decision #4: the three former `jurisprudencia` entries are now `generico`.

| Sample | Route | Rationale |
|---|---|---|
| `port_mf_277_20180607` | **`norma` + `anexo1`** | `Art. 1º–2º` genuine; `ANEXO ÚNICO` split off |
| `parecer_93_2018_decor_cgu_agu` | `generico` | 21 quoted articles (indent ≈2908) must be rejected |
| `par_cosit_26_20000629` | `generico` | **hard case** — inline-quoted articles, no indent |
| `pn_cst_38_19801031` | `generico` | 4-level dotted hierarchy (`2.` → `2.3.1`) |
| `port_mf_454_19770825` | `generico` | item-based Portaria — genre prior would mislead |
| `ad_srf_3_19990107` | `generico` | `DECLARA` + incisos, no articles |
| `ad_pgfn_13_20111220` | `generico` | incisos only |
| `ad_pgfn_3_20080918` | `generico` | short declaratory act |
| `ad_srf_22_19970430` | `generico` | short declaratory act |
| `adn_cosit_19_20001025` | `generico` | short declaratory act |
| `adn_cst_10_19910417` | `generico` | dotted items `1.`, `1.1`, `2.` |
| `…CARNE_LEAO` | `generico` | style-driven `Heading1/2` + lists |
| `sumula_carf_42` | `generico` | decision #2 |
| `sumula_stj_125` | `generico` | decision #2 — has EMENTA/ACÓRDÃO/RELATÓRIO but incomplete for `Acordao` |
| `REsp_1306393` | `generico` | decision #2 |

14 of 15 route to `generico` — confirming it as the correct default, and confirming that **statutory detection's main job is refusing false positives**, not finding statutes.

---

## 5. Emitters

### 5.1 `generico` (default)

```xml
<DocumentoGenerico>
  <PartePrincipal id="pp1">
    <Agrupamento id="pp1_agr1" nome="secao">
      <Bloco nome="rotulo">2.</Bloco>
      <Bloco nome="nomeAgrupador">DAS SOCIEDADES COOPERATIVAS</Bloco>
      <Bloco nome="nivel">1</Bloco>
      <p>Texto introdutório.</p>
    </Agrupamento>
    <Agrupamento id="pp1_agr1_agr1" nome="subsecao">
      <Bloco nome="rotulo">2.1</Bloco>
      <Bloco nome="nomeAgrupador">Empresas de serviços</Bloco>
      <Bloco nome="nivel">2</Bloco>
      <p>Em linhas gerais, as cooperativas…</p>
      <ol><li>primeiro item</li><li>segundo item<ol><li>subitem</li></ol></li></ol>
    </Agrupamento>
  </PartePrincipal>
</DocumentoGenerico>
```

Depth is recoverable three redundant ways: `id` path, `<Bloco nome="nivel">`, `@nome`. **Rule A** (materialise every intermediate `id` prefix) and **Rule B** (leaf-only text) are emitter requirements.

### 5.2 `norma` (+ `anexo`)

Per §4.3, matching the reference parser's conventions.

### 5.3 `articulado-sintetico` (opt-in, retained)

Maps `Section` → `AgrupamentoHierarquico` and prose → synthetic `Artigo`/`Caput`, giving genuinely nested XML at the cost of asserting articulation the source lacks. Retained because it validates and some consumers need real nesting; **not the default**, and synthetic articles are marked via `MetadadoProprietario` provenance so they are never mistaken for real ones.

---

## 6. Hierarchical Segmentation Output

### 6.1 Python API (primary)

```python
def segments(model_or_xml) -> Iterator[Segment]:
    """Hierarchical segments with breadcrumbs, from the model or from XML."""
```

```python
@dataclass
class Segment:
    urn: str          # "urn:lex:…;38!pp1_agr1_agr1"  — stable, citable
    kind: str         # secao | subsecao | artigo | …
    level: int
    label: str | None
    heading: str | None
    breadcrumb: list[str]
    text: str
    route: str
```

Segmenting from the in-process model is the primary path; the XML reader exists as the round-trip **test oracle**, which is exactly the reversibility invariant the suite requires.

### 6.2 XSLT reference stylesheets

`segment_generico.xsl` (below, with Rules A/B applied) and `segment_norma.xsl` (statutory-element based, adapting `GeraCSVporArtigoPorAgrupador.xsl`).

```xslt
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="3.0"
  xpath-default-namespace="http://www.lexml.gov.br/1.0">
 <xsl:output method="text"/>
 <xsl:template match="/">
  <xsl:text>Tipo,Nivel,Rotulo,Breadcrumb,Texto,urn&#10;</xsl:text>
  <xsl:variable name="urn" select="/LexML/Metadado/Identificacao/@URN"/>
  <xsl:for-each select="//Agrupamento">
   <xsl:variable name="myid" select="@id"/>
   <xsl:variable name="anc" select="//Agrupamento[starts-with($myid, concat(@id,'_'))]"/>
   <xsl:value-of select="@nome"/><xsl:text>,</xsl:text>
   <xsl:value-of select="Bloco[@nome='nivel']"/><xsl:text>,"</xsl:text>
   <xsl:value-of select="Bloco[@nome='rotulo']"/><xsl:text>","</xsl:text>
   <xsl:for-each select="$anc"><xsl:sort select="string-length(@id)"/>
     <xsl:value-of select="Bloco[@nome='nomeAgrupador']"/><xsl:text> | </xsl:text>
   </xsl:for-each>
   <xsl:value-of select="Bloco[@nome='nomeAgrupador']"/><xsl:text>","</xsl:text>
   <xsl:value-of select="normalize-space(
        string-join((descendant::p, descendant::li[not(ol|ul)]), ' '))"/>
   <xsl:text>",</xsl:text>
   <xsl:value-of select="concat($urn,'!',@id)"/><xsl:text>&#10;</xsl:text>
  </xsl:for-each>
 </xsl:template>
</xsl:stylesheet>
```

---

## 7. LLM Referee

Included from the start (decision #3), with observability as a first-class requirement.

### 7.1 Role

The referee **adjudicates flagged decisions**; it never parses documents or generates XML. Deterministic rules remain the default path and must always produce valid output on their own.

| Decision | Why rules struggle | Referee |
|---|---|---|
| Quoted vs. own articulation | needs "is this text *about* another norm?" | **yes** |
| Heading vs. emphasised sentence | no style, no label — rhetorical role only | **yes** |
| Section-kind naming | semantic labelling | yes |
| Genre classification | usually clear from epigraph | tie-break only |
| Label parsing, list nesting, front matter | exact patterns | **never** |

### 7.2 Hardware finding: skip the local SLM as primary

| GTX 980 Ti property | Value | Consequence |
|---|---|---|
| VRAM | **6 GB** | caps ~7B at 4-bit, little context room |
| Architecture | Maxwell, CC 5.2 (2015) | **no bf16, no FlashAttention** |
| Support | dropped by recent CUDA/PyTorch | vLLM etc. unavailable; `llama.cpp` viable |

Long-context legal pt-BR discrimination is precisely where small models are weakest, and it is exactly what we would delegate. 62 GB RAM is ample for CPU inference in a *batch* pipeline (a few tokens/s) — acceptable offline, not interactive.

*Caveat:* this container reports `Failed to initialize NVML` and `torch.cuda.is_available() == False`, so the GPU was not benchmarked here; the table is from published specs.

**Recommendation: budget frontier API as primary, `llama.cpp` local as fallback.** Candidates: DeepSeek `deepseek-chat` (very low cost, strong reasoning, context caching), Qwen `qwen-plus` (excellent multilingual), Moonshot `kimi-k2` (long context). All expose OpenAI-compatible endpoints, so one client serves all three.

**Cost sizing.** 300 documents × ~20 flagged decisions × ~1.5k tokens ≈ 9M input tokens ⇒ roughly **$1–3** for the whole corpus at budget-tier rates, less with caching. Even at 10× this is immaterial. Verify current pricing before committing.

### 7.3 Design constraints

```python
class Referee(Protocol):
    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict: ...
    def is_heading(self, para: str, ctx: str) -> Verdict: ...
    def section_kind(self, label: str, heading: str) -> Verdict: ...

class NullReferee:      # deterministic, no network — the test default
class CachedAPIReferee: # DeepSeek/Qwen/Moonshot, JSON-constrained, disk-cached
class LocalReferee:     # llama.cpp, optional fallback
```

1. **Rules run first, always.** The referee is consulted only when deterministic confidence falls below threshold.
2. **Structured output only** — `{verdict, confidence, rationale}` JSON. Never free-form XML.
3. **Disk-cached by excerpt hash** — reproducibility plus near-zero repeat cost.
4. **Advisory** — may break ties; may **not** override a high-confidence deterministic verdict.
5. **Fail-safe** — API error/timeout/malformed JSON ⇒ fall back to the rule verdict and log it. A referee outage degrades quality, never availability.
6. **Fully logged** (§7.4).
7. **`--referee=none|api|local`**, default configurable; regression tests pin `none`.

### 7.4 Telemetry — rule effectiveness tracking (explicit requirement)

Every adjudicated decision is recorded:

```python
@dataclass
class DecisionRecord:
    decision_id: str              # stable: f"{doc}:{kind}:{locator}"
    kind: str                     # own_articulation | heading | section_kind | route
    locator: str                  # paragraph index / id path
    rule_verdict: Any
    rule_confidence: float
    rule_flagged: bool            # was confidence below threshold?
    referee_consulted: bool
    referee_verdict: Any | None
    referee_confidence: float | None
    referee_rationale: str | None
    final_verdict: Any
    overridden: bool              # referee changed the outcome
    cache_hit: bool
    excerpt: str                  # truncated, for audit
```

Log lines make interventions unmistakable:

```
INFO  routing  port_mf_277        rule=norma conf=0.91  referee=skipped        final=norma
WARN  rules    par_cosit_26 p#12  RULE FAILED: art label at body indent, citation antecedent ambiguous
                                  rule=own_articulation conf=0.41 (flagged)
WARN  referee  par_cosit_26 p#12  REFEREE OVERRODE RULE: rule=own conf=0.41 →
                                  referee=quoted conf=0.88  final=quoted
                                  rationale="preceded by 'Lei nº 7.713, de 1988 -' introducing a quotation"
INFO  referee  parecer_93   p#88  referee agreed with rule (quoted); no override
```

`--decisions-report` emits a per-corpus summary — the instrument for judging whether the rules generalise from 15 to 300+:

```
Decisions:            4,182
Rule-only (confident): 3,947  (94.4%)
Flagged to referee:      235  ( 5.6%)
  referee agreed:        198  (84.3% of flagged)  ← rules were right but unsure
  referee overrode:       37  (15.7% of flagged)  ← rules were wrong
Cache hit rate:        91.2%
Overrides by kind:  own_articulation 24 · heading 11 · section_kind 2
Top override documents:  par_cosit_26 (7) · pn_cst_38 (5) · …
```

The `referee agreed` vs `referee overrode` split is the key metric: a high agreement rate means thresholds are too conservative (cheap to tighten); a high override rate localises which rule needs work, and on which genres.

---

## 8. Development Cycles

Each cycle is independently verifiable and leaves the repository green. Tests accumulate into the regression suite.

### Cycle 0 — Scaffolding and the schema harness

Package skeleton; `pyproject.toml` (`lxml`, `python-docx`, `pytest`, `pytest-cov`, `httpx`, optional `saxonche`); **three** vendored offline stubs (`xml.xsd`, `xlink-href.xsd`, `mathml2.xsd`) resolved through a custom `lxml` resolver — see Amendment A-0.1; `validate.schema` compiling **both** schemas; `ValidationReport` with per-schema results; `--schema=both|rigido|flexivel`.

Tests
- both schemas compile offline
- minimal `DocumentoGenerico` validates; nested `Agrupamento` is rejected
- **the full §2.1 matrix as a parametrised test** (both schemas per case)
- `ValidationReport.ok` iff both pass; per-schema errors surfaced

Exit: `pytest` green; the investigation is now executable, so schema drift immediately shows which assumptions broke.

**Amendment A-0.1 (Cycle 0, 2026-08-02) — the offline harness needs three stubs and a resolver, not one stub and a rewrite.**

Two corrections to the description above and to `docs/20260801_004745_…` §11, both found by executing the recipe:

1. **Three remote imports, not one.** `lexml-base.xsd` imports `xml.xsd`, `xlink-href.xsd` **and** `mathml2.xsd` from w3.org, and all three are genuinely fetched during compilation. §11 stubbed only `xml.xsd`; its recipe therefore *fails on a machine without internet* — the exact condition Cycle 0 must guarantee. It appeared to work only because the investigation ran on a connected machine. Cycle 0 vendors all three.
2. **Resolver instead of in-place rewrite.** §11 rewrote `schemaLocation` inside `lexml/*.xsd` on disk. Cycle 0 uses an `lxml` `Resolver` mapping those URLs onto the vendored stubs at parse time, leaving `lexml/` byte-identical to upstream, so a future `git diff` there shows LexML's changes and nothing of ours. A regression test asserts the vendored files are unmodified. *(Decided with the user during Cycle 0 reconciliation.)*

A third point, discovered while implementing: **a missing stub is silently masked**, because libxml2 answers an unreadable local `schemaLocation` by fetching the URL. Neither banning Python's `socket` (libxml2's HTTP is in C) nor `XMLParser(no_network=True)` (does not reach the schema-import loader) prevents this. `OfflineResolver` therefore raises `MissingStubError` when a mapped stub is absent, rather than declining and letting libxml2 fall back.

### Cycle 1 — DOCX ingestion → `StyledDoc`

`ingest/docx_reader.py`: paragraphs, `pStyle` (with `basedOn` inheritance), `numPr` (`numId`/`ilvl`), **`w:ind/@w:left` indentation — both direct and style-resolved, see Amendment A-1.1**, `w:jc` alignment, runs (bold/italic/sup/sub), tables, **struck runs dropped, soft breaks split, hyperlink targets captured — see Amendment A-1.2**; NFC normalisation and whitespace collapse mirroring `DOCXReader.breakText`; `--dump-styled`.

Tests
- golden `StyledDoc` JSON for all 15 samples
- `Heading1/2` detected in `CARNE_LEAO`; `sumula_stj_125` heading styles detected
- list `ilvl` captured; nested levels distinguished
- **indentation captured — the 21 quoted articles in `parecer_93` show `ind≈2880–2930` (20 of the 21) against a body of small *direct* indents (7–60), not against a modal 0 — see Amendment A-1.1**
- NFC unifies composed/decomposed accents **(synthetic fixture — no sample is decomposed, see Amendment A-1.3)**; NBSP and runs of spaces collapse
- run formatting preserved; tables extracted with row/cell shape
- **text conservation: every source paragraph appears in `StyledDoc` exactly once (Amendment A-1.4)**

Exit: all 15 samples ingest losslessly; goldens committed.

**Amendment A-1.1 (Cycle 1, 2026-08-02) — the indentation discriminator is *direct* `w:ind`, not effective indent, and the modal value is not 0.**

Measured on `parecer_93` before implementing. The count and band are confirmed: exactly **21** `Art.`-initial paragraphs, at `w:ind/@w:left` ∈ {2880, 2908 (×18), 2930}. The comparison baseline was wrong:

1. **The modal indent is not 0 — it is 2908, the quote band itself.** The 2880–2930 band holds **137 non-empty paragraphs**, not 21: the whole quoted excerpt — the incisos, alíneas and continuation paragraphs of each quoted article — carries the same indent as the `Art.` line heading it, spread across blocks 10–416. Only **37** paragraphs (front matter and unquoted commentary) sit in the small band at 7–60. So the discriminator is **"quote band vs small band"**, *not* "quote band vs modal": a Cycle 4 rule thresholding against the modal indent would classify the majority of the document as unquoted body. The two bands are disjoint by an order of magnitude, so any threshold in 100–2800 separates them cleanly.
2. **Resolving inheritance destroys the signal.** 226 paragraphs carry no direct `w:ind`, so they inherit 2909 — one twip from the quote band at 2908. Read effective indent alone and quotations become indistinguishable from body text. Read direct indent alone and 226 paragraphs report nothing. (Of those 226, **219 are empty or section artifacts**; only one is a non-empty real paragraph.)
3. **`StyledPara` therefore carries both** `indent_direct` and `indent_effective`. Cycle 4's quotation guard chooses whichever discriminates. *(Decided with the user during Cycle 1 reconciliation.)*
4. **One of the 21 is not deeply indented:** `Art. 4º - São atribuições do Advogado-Geral da União:` sits at `indent_direct=240`. Cycle 4 must not assume indentation alone separates every quotation — §2.5 already pairs it with citation antecedent and monotonicity, and this is why.
5. **Indentation marks quoted *regions*, not article openers.** Of the 137 in-band paragraphs only 20 begin with `Art.`. Cycle 4 should read the band as a region marker and use the label grammar to find article boundaries *within* it, rather than treating "indented" and "is an article" as the same predicate.

This matters beyond Cycle 1: §10 lists "quoted statute misread as articulation" as a **high, silently-corrupting** risk, and this is the evidence channel that mitigates it.

**Amendment A-1.2 (Cycle 1, 2026-08-02) — three DOCX constructs the deliverable list omitted, all present in the samples.**

- **Struck runs** (18, `sumula_stj_125`) are **dropped**, toggle-aware (`w:val` ∈ {`false`,`0`,`off`} disables), matching `DOCXReader.stripStruckRuns`. They are **ordinal markers inside live sentences** — `ª` ×9, `º` ×8, `º,` ×1 — split 7 in the document's table and 11 in body prose: `(2ª T, 03.08.1994)` → `(2 T, 03.08.1994)`, `art. 3º, § 4º` → `art. 3, § 4`. `read_docx(..., drop_strikethrough=False)` retains them, and a test asserts that path conserves them, so the loss is bounded and reversible. Struck ordinals are a Portuguese legal-typography idiom, so **Cycle 9 should expect them corpus-wide**, and any cycle reasoning about article numbers must read the dropped form.
- **Soft breaks** (`<w:br/>`; 7 in `pn_cst_38`, 3 each in `par_cosit_26` and CARNE_LEAO) **split the paragraph**, as the reference does. Block counts consequently exceed source paragraph counts: 85→92, 100→103, 109→112. `StyledPara.index` is assigned *after* splitting and is authoritative.
- **Hyperlink targets** (11, CARNE_LEAO) are captured into `Inline.href`, which §3.1 already declares.

Strike stripping runs **before** soft-break splitting — a struck run can contain `<w:br/>`-separated text, so splitting first would let struck text escape its `<w:rPr>`. *(Decided with the user during Cycle 1 reconciliation.)*

**Amendment A-1.3 (Cycle 1, 2026-08-02) — the NFC test cannot be written against the samples.**

All 15 samples are **already NFC**, so a test asserting "NFC unifies composed/decomposed accents" would pass with the normaliser deleted. NFC is therefore tested against **synthetic decomposed input** (mutation-verified: removing the `unicodedata.normalize` call fails 8 tests), plus a standing assertion that all 15 samples are NFC-unchanged, which acts as a tripwire for the first non-NFC corpus document.

Note also that `DOCXReader.breakText` does **not** normalise — it only collapses whitespace. NFC is our deliberate addition, justified by the 300+ unseen corpus: one decomposed `ç` breaks profile regexes, the conservation invariant and byte-stable goldens simultaneously, and does so invisibly. *(Decided with the user during Cycle 1 reconciliation.)*

**Amendment A-1.4 (Cycle 1, 2026-08-02) — "ingests losslessly" made checkable.**

The exit criterion is discharged by a **text-conservation test** (§9.2 invariant #2 applied at ingestion): every non-empty source paragraph's normalised text appears in `StyledDoc` exactly once, compared as a multiset so duplication fails as loudly as loss, and cross-checked by reading the source with `python-docx` independently of our reader. The two sanctioned transformations above (soft-break splitting, struck-run dropping) are accounted for explicitly rather than excused. Goldens alone were rejected as the criterion: a byte-identical match to a golden containing a bug passes forever. *(Decided with the user during Cycle 1 reconciliation.)*

### Cycle 2 — Metadata, URN and profiles

`model/urn.py`; `model/metadata.py`; `profile/base.py` + registry; profiles for `parecer`, `ato_declaratorio`, `portaria`, `servico`, `jurisprudencia_generico`, `generic`; authority/type/number/date extraction; `MetadadoProprietario` for unmapped fields (`NUP`, `INTERESSADOS`, `ASSUNTO`, `Cod. Ement.`).

Tests
- URN round-trip for federal/state/municipal authorities
- `parecer_93` → authority `advocacia.geral.uniao`, type `parecer`, number `93`, date `2018-12-28`
- `port_mf_277` → `ministerio.fazenda`, `portaria`, `277`, `2018-06-07`
- date forms: `28/12/2018`, `7 de junho de 2018`, ISO
- number normalisation `00093/2018` → `93`
- profile auto-selection correct for all 15 samples
- unmapped fields land in `MetadadoProprietario`; none dropped
- `<Metadado>` fragment validates on both schemas

### Cycle 3 — Front/back matter segmentation

`segment/`: epigraph, ementa, preamble, enacting formula (`DECLARA`, `RESOLVE:`), local/date closing, signatures, annex boundaries (`ANEXO ÚNICO`, `ANEXO I`), named fields; per-profile regex sets ported in spirit from `DocumentProfile.scala`; tolerance for absent front matter.

Tests
- `parecer_93`: epigraph `PARECER n. 00093/2018/DECOR/CGU/AGU`; ementa from `EMENTA:`
- `EMENTA:` with no space after colon still splits (observed in sample)
- `ad_*`/`adn_*`: enacting formula `DECLARA` recognised; `port_mf_454`: `RESOLVE:`
- `port_mf_277`: `ANEXO ÚNICO` boundary found; annex body separated
- `CARNE_LEAO`: no ementa/preamble/signature — **no false positives**
- signature blocks (`NomePessoa` + optional `Cargo`) for all signed samples
- `ParteInicial`/`ParteFinal` fragments validate on both schemas

### Cycle 4 — Hierarchy inference

`hierarchy/`: `labels.py` (`1.`, `1.1`, `1.1.1`, `I -`, `a)`, `c. 1)`, `CAPÍTULO`, `Seção`, `Subseção`, ordinals, roman, `único`, `-A`); **`quotation.py` redesigned** around indentation + citation antecedent + numbering monotonicity + omissis runs; `evidence.py`; `unify.py` (level unification, depth monotonicity); `tree.py`; confidence scoring; flat fallback.

Tests
- label grammar: ~40 parametrised forms → (kind, value, arity), **including negatives** (`1.500/2014` in a citation is not a label; `Lei nº 12.618` is not a label)
- **quotation guard: all 21 indented `Art.` in `parecer_93` are content, not structure** (regression-critical)
- `par_cosit_26`: `Art. 52. .........` recognised as omissis-bearing quotation; numbering `1º,2º,3º,16,52` flagged non-monotonic
- `CARNE_LEAO`: `Heading1`→1, `Heading2`→2, children attached correctly
- `pn_cst_38`: `2.` → `2.1` → `2.3` → `2.3.1` yields depths 1/2/2/3
- `port_mf_454`: `1.`, `2.`, `2.1`, `a)` hierarchy correct
- depth monotonicity: never increases by more than 1 between consecutive headings
- nested list reconstruction from `ilvl`
- style/label evidence conflict resolves deterministically
- low confidence ⇒ flat fallback, no fabricated sections
- idempotence: inferring twice yields an identical tree

Exit: all 15 samples produce trees matching hand-authored goldens.

### Cycle 4b — Statutory Viability Analyzer + LLM Referee + Telemetry

`routing/`: article census, indentation discrimination, numbering monotonicity, omissis/citation cues, genre priors, coverage; structured `StatutoryViability` with blockers.
`referee/`: `Referee` protocol, `NullReferee`, `CachedAPIReferee` (OpenAI-compatible ⇒ DeepSeek/Qwen/Moonshot), `LocalReferee` (llama.cpp), disk cache, prompt templates, JSON schema constraints.
`telemetry/`: `DecisionRecord`, structured logging, `--decisions-report`.

Tests — routing
- **expected route for all 15 samples matches §4.4** (labelled fixture table)
- `parecer_93` and `par_cosit_26` **must not** route to `norma`
- `port_mf_277` routes to `norma` **with** annex split; coverage computed after separation
- coverage gate rejects low-coverage articulation
- verdicts deterministic under `NullReferee`

Tests — referee
- `NullReferee` ⇒ byte-identical output to referee-disabled
- cache hit avoids network (mocked transport asserts zero calls)
- malformed/non-JSON LM response ⇒ rule verdict retained, `WARN` logged
- API timeout/5xx ⇒ graceful fallback, pipeline completes
- referee **cannot** flip a high-confidence rule verdict
- `par_cosit_26` resolves correctly with a **recorded fixture** (`tests/referee_fixtures/`), no live API
- prompts contain no PII beyond the excerpt; excerpt length bounded

Tests — telemetry
- every flagged decision produces a `DecisionRecord`
- **override emits `WARN` containing both rule and referee verdicts plus rationale** (asserted on log text)
- **rule failure emits `RULE FAILED` with the reason**
- `--decisions-report` counts reconcile: `rule_only + flagged == total`; `agreed + overrode == flagged`
- records are stable across reruns given a warm cache

Exit: routing correct for all 15 samples; referee integrated, cached, fail-safe; interventions visibly logged and countable.

### Cycle 5 — Emitter `generico` (default)

`render/generico.py`; `render/ids.py` (path-composed unique ids, **Rule A** materialising every intermediate prefix); flattening with `<Bloco nome="rotulo"|"nomeAgrupador"|"nivel">`; nested `ol`/`ul`; tables **with inline-only cell content (§2.2)**; `Anexos`/`ReferenciaAnexo`.

Tests
- all 14 `generico`-routed samples validate on **both** schemas
- `id`s unique document-wide (explicit `xsd:ID` check)
- **Rule A: every proper prefix of every `Agrupamento` `id` exists** (the breadcrumb-gap regression)
- **Rule B: leaf-only text — no duplication** (the nested-`li` regression)
- `id` path encodes depth; **tree reconstructable from XML alone**
- nested lists survive as nested `ol`/`ul`
- tables emit inline cell content, never `<p>` (guards the `td` finding)
- text conservation: every source paragraph's text appears exactly once
- goldens committed for all 14

### Cycle 6 — Emitter `norma` + `Anexo` split

`render/norma.py`, `render/anexo.py`: `ParteInicial`/`Articulacao`/`ParteFinal`; strict element ordering (`Rotulo` before `Caput`; `Caput` carries its own `Rotulo`); sibling `<LexML><Anexo>` documents with `!anexoN` URN fragments, `anexoN_pp` ids, `anexoN_tabM` tables; parent `ReferenciaAnexo` pointers; validate-then-fallback to `generico`.

Tests
- `port_mf_277` primary + `anexo1` both validate on both schemas
- URN fragment/ids match the reference convention (`!anexo1`, `anexo1_pp`)
- element ordering enforced; a deliberately mis-ordered tree fails validation
- **conservation across the split: primary + annex together contain all source text exactly once**
- `ReferenciaAnexo` targets resolve to the emitted annex URNs
- validate-then-fallback: a forced statutory-render failure falls back to `generico` and logs the reason
- annex containing tables uses `DocumentoGenerico`, mirroring `isArticulatedAnexo`

### Cycle 6b — Emitter `articulado-sintetico` + round-trip

`render/articulado.py`; `hierarchy_from_xml()` reader for round-trip testing of all emitters.

Tests
- samples validate in `articulado-sintetico` on both schemas
- nesting depth preserved exactly (no flattening)
- synthetic articles marked and countable
- **round-trip: `model → generico → model'` and `model → articulado → model''` preserve tree shape and all text**
- cross-emitter equivalence: all emitters carry identical text content

### Cycle 7 — Segmentation output

`segmentation/api.py`; `segment_generico.xsl`; `segment_norma.xsl`; CSV/JSONL writers.

Tests
- segments from the model equal segments read back from XML (**oracle agreement**)
- breadcrumbs complete for all 15 samples — **no missing ancestors** (Rule A end-to-end)
- **no duplicated text in any segment** (Rule B end-to-end)
- segment URNs unique, stable across reruns, and resolvable to their `Agrupamento`/dispositivo
- XSLT and Python paths produce equivalent rows (skipped if `saxonche` absent)
- `norma`-routed documents segment via statutory elements
- `port_mf_277` segments span primary **and** annex

### Cycle 8 — Generalisation, robustness, CLI

`cli.py`: `parse`, `dump-styled`, `dump-tree`, `segment`, `validate`, `list-profiles`, `decisions-report` (mirroring `FECmdLine`'s shape); HTML and plain-text ingestion; `generic` catch-all profile; structured warnings; confidence reporting; `--profile`/`--emitter`/`--schema`/`--referee`/`--strict`.

Tests
- CLI end-to-end on all 15 samples, all emitters
- degenerate inputs: empty document, single paragraph, headings only, no headings, deeply nested lists, unlabelled prose, tables only — none crash, all emit valid XML
- malformed/corrupt DOCX ⇒ clean error, non-zero exit, no traceback
- HTML and TXT ingestion reach the same model shape
- `--strict` fails on validation error; default warns and continues
- confidence and referee status surfaced in output

Exit: "handles any document" demonstrated — valid output or a clean diagnostic for every fixture.

### Cycle 9 — Regression consolidation and corpus scale-out

Promote all goldens to `tests/regression/`; `make regression`; coverage gate; corpus-expansion guide (new document = fixture + expected route + golden); **batch mode for the 300+ corpus** with an aggregate decisions report; documentation of `docs/`/`dev/` conventions.

Tests
- full suite green; coverage ≥ 85% on `hierarchy/`, `routing/`, `render/`
- every golden regenerable by one documented command
- **a deliberate mutation fails the suite** (proving the tests bite)
- batch mode over all samples produces a single reconciling decisions report
- referee disabled ⇒ suite still green (no network dependency anywhere)

---

## 9. Test Strategy

### 9.1 Layers

| Layer | Purpose | Location |
|---|---|---|
| Unit | label grammar, URN, evidence scoring, id generation, coverage math | `tests/unit/` |
| Schema matrix | the §2.1 encodings stay true, on both schemas | `tests/unit/test_schema_matrix.py` |
| Golden | byte-stable `StyledDoc` / tree / XML / segments per sample | `tests/golden/` |
| Routing | expected route per sample (§4.4) | `tests/unit/test_routing.py` |
| Referee | recorded-fixture adjudication; fail-safe paths | `tests/referee_fixtures/` |
| Telemetry | override/failure logging, report reconciliation | `tests/unit/test_telemetry.py` |
| Round-trip | XML → model preserves shape and text | `tests/regression/` |
| Conservation | no text lost or duplicated, including across the annex split | `tests/regression/` |
| Robustness | degenerate/corrupt inputs never crash | `tests/unit/test_robustness.py` |
| Validation | every emitted document validates on both schemas | all cycles |

### 9.2 Cross-cutting invariants

Asserted throughout — these are what make the parser trustworthy on the 285 documents we have not seen.

1. **Validity** — output validates against **both** schemas (configurable).
2. **Conservation** — all source text present exactly once, including across `Norma`+`Anexo`.
3. **Reversibility** — hierarchy reconstructable from output alone (`id` path or native nesting).
4. **Determinism** — same input + same referee cache ⇒ byte-identical output.
5. **`id` uniqueness** — required by `xsd:ID`; enforced document-wide.
6. **Ancestor totality (Rule A)** — every proper prefix of an `id` path exists.
7. **No text duplication (Rule B)** — leaf-only extraction.
8. **No fabrication** — low confidence degrades to flat, never invents structure.
9. **Referee is advisory** — cannot override high-confidence rules; disabling it never breaks the pipeline.
10. **Observability** — every rule failure and referee override is logged and counted.

### 9.3 Referee testing policy

Networked LLM calls must never enter the regression suite.

- **Default `NullReferee`** for all regression tests; invariant #4 keeps output deterministic.
- **Recorded fixtures** (`tests/referee_fixtures/*.json`, keyed by excerpt hash) exercise referee logic offline. The cache layer is the seam.
- **Mocked transport** asserts cache hits make zero network calls, and that timeouts/5xx/malformed JSON fall back to rule verdicts.
- **One opt-in live smoke test**, marked `@pytest.mark.live`, excluded by default, for verifying API wiring on demand.
- **Fixture refresh** is an explicit documented command, never automatic — so a provider change shows up as a reviewed diff.

### 9.4 Golden-file policy

Goldens regenerate only via an explicit documented command. A diff always represents a reviewed behaviour change. Every sample carries: `StyledDoc` JSON, hierarchy tree JSON, expected route, emitted XML (per emitter), and segment CSV/JSONL.

---

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `OpenStructure` cannot nest (§2.1) | high — core requirement | dual-representation; depth in `id` path + `Bloco nivel`; reversibility test; §11 proposal |
| Quoted statute misread as articulation | **high — silent corruption** | indentation + citation antecedent + monotonicity + omissis; regression on `parecer_93`'s 21 quotes; referee on residue |
| 15 samples ⇏ 300+ corpus | high | genre-agnostic evidence fusion; `generic` profile; flat fallback; **telemetry to measure rule generalisation**; batch mode (Cycle 9) |
| Coverage misjudged ⇒ lossy statutory render | high | coverage gate + validate-then-fallback + conservation invariant |
| Referee nondeterminism leaks into output | medium | advisory-only; cached; `NullReferee` in tests; invariant #4 |
| LLM cost/availability | low | ~$1–3/corpus; cached; fail-safe to rules |
| Rule A / Rule B regressions | medium | both are explicit invariants with dedicated tests (both were real bugs) |
| `<td>` rejects `<p>` | medium | in the schema matrix from Cycle 0; reference parser confirms inline-only |
| Strict `Artigo` ordering | medium | matrix cases; emitter asserts order |
| Synthetic articles mislead consumers | medium | not default; provenance markers; documented |
| Schema/version drift | medium | §2.1 matrix re-runs on any schema change |
| DOCX style inheritance (`basedOn`) missed | low | explicit resolution + test |

---

## 11. The Recursive `Agrupamento` Proposal (for the LexML community)

Retained here because the user can reach the community. Full text with reproducible evidence is in `docs/20260801_142630_…` §6; summary:

**Problem.** A large class of Brazilian legal documents is non-articulated yet deeply hierarchical (pareceres, pareceres normativos, atos declaratórios normativos, older portarias, service descriptions). `OpenStructure` cannot represent them, because `Agrupamento` and `div` derive from `blocksreq` → `blockElements`, which contains no container element; and `AgrupamentoHierarquico` requires articulated descendants and cannot hold prose. **No LexML element is both non-articulated and recursive.**

**Evidence.** `Agrupamento`-in-`Agrupamento` and `div`-in-`div` both **FAIL** on `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd`. Real motivating documents: `pn_cst_38_19801031` (`2.` → `2.1` → `2.3` → `2.3.1`), `port_mf_454_19770825` (`1.`, `2.1`, `a)`).

**Proposed change** — additive, backward compatible:

```xml
<xsd:complexType name="blocksreq">
  <xsd:choice minOccurs="1" maxOccurs="unbounded">
    <xsd:group ref="blockElements"/>
    <xsd:group ref="containerElements"/>   <!-- ADDED: div | Agrupamento -->
  </xsd:choice>
  <xsd:attributeGroup ref="corereq"/>
</xsd:complexType>
```

`sequence`→`choice` allows interleaving prose with subsections, the natural document order. Every currently-valid document stays valid. Precedent: Akoma Ntoso models exactly this with a recursive `<hcontainer>`; `Agrupamento` is its natural LexML analogue and already carries the required `@nome` role attribute under LexML's documented *Generic Document + Role Attribute* pattern.

**Secondary observations worth raising:**
- `Rotulo`/`NomeAgrupador` are children of `hierarchy` only, so non-articulated sections must smuggle labels through `<Bloco nome="rotulo">`. Permitting them on `Agrupamento` would make non-articulated headings first-class and reusable by existing stylesheets.
- `<td>` accepts inline content but not `<p>`, unlike every other block container — an inconsistency that complicates faithful table rendering.

**Route.** Open an issue on the schema repository with the problem statement, attach the reproducible validation script (`docs/20260801_004745_…` §11), offer the public-domain corpus documents as examples, and note that `lexml-parser-projeto-lei` already faces this limitation (`LexmlRenderer.isArticulatedAnexo`).

**If adopted**, add a fourth emitter `generico-aninhado`. Because the internal model is already a real tree, this is purely a rendering addition — the payoff of keeping the model rendering-agnostic is that a schema improvement costs one emitter, not a rewrite.

---

## 12. Cycle Summary

| Cycle | Deliverable | Key exit criterion |
|---|---|---|
| 0 | Scaffolding, dual-schema harness | §2.1 matrix executable and green |
| 1 | DOCX → `StyledDoc` (incl. indentation) | 15 samples ingest losslessly |
| 2 | Metadata, URN, profiles | correct URN/metadata for all samples |
| 3 | Front/back matter segmentation | zero false positives on bare documents |
| 4 | Hierarchy inference + quotation guard | 21 quoted articles in `parecer_93` rejected |
| **4b** | **Routing + LLM referee + telemetry** | **routes match §4.4; overrides logged and counted** |
| 5 | Emitter `generico` | 14 samples valid on both schemas; Rules A/B hold |
| 6 | Emitter `norma` + `Anexo` split | `port_mf_277` split, conservation across both docs |
| 6b | Emitter `articulado-sintetico` + round-trip | round-trip preserves shape and text |
| 7 | Segmentation output (API + XSLT) | breadcrumbs complete; oracle agreement |
| 8 | Robustness + CLI | every degenerate input handled cleanly |
| 9 | Regression consolidation + batch | mutation test fails; corpus report reconciles |

---

## 13. Traceability

Everything in this plan is grounded in verified evidence rather than assumption. The investigation record is preserved in `docs/`:

- **`docs/20260801_004745_…`** — schema investigation; validation matrix A–R; reference-parser survey; §11 reproducible schema harness (offline `xml.xsd` stub + `schemaLocation` rewrite).
- **`docs/20260801_142630_…`** — segmentation proof (Saxon XSLT 3.0, verbatim output); Rules A/B discovered by running the transform; indentation discriminator across 15 samples; local-SLM feasibility; dual-schema equivalence analysis; recursive `Agrupamento` proposal.
- **This document** — consolidated plan incorporating the four ratified decisions.

Both predecessor documents contain the originating prompts verbatim, for reproducibility.
