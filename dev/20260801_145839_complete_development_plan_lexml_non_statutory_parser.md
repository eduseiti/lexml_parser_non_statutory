# Complete Development Plan — LexML Parser for Non-Statutory Documents

- **Date:** 2026-08-01
- **Status:** Consolidated and approved plan — supersedes the open questions of both predecessor documents.
  **Revised 2026-08-28** to adopt the LexML maintainers' recursive `AgrupamentoHierarquico` proposal; see §14 for the amendment log and §2.10 for the finding that drives it. Cycles 0–2 are unaffected.
- **Target language:** Python 3
- **Predecessors (investigation record, retained for traceability):**
  - `docs/20260801_004745_lexml_non_statutory_parser_investigation_and_development_plan.md` — schema investigation, validation matrix A–R
  - `docs/20260801_142630_design_review_segmentation_statutory_detection_and_lm_support.md` — segmentation proof, statutory detection, LM analysis, recursive `Agrupamento` proposal
  - `docs/20260827_111015_revised_plan_recursive_agrupamento_hierarquico_adoption.md` — **evaluation of the LexML maintainers' `AgrupamentoHierarquico` change; source of Amendments A-R.1 … A-R.9 (§14)**
- **Reference implementation:** `../lexml-parser-projeto-lei` (Scala, Senado Federal)
- **Schemas:** `lexml/lexml-base.xsd`, `lexml/lexml-br-rigido.xsd`, `lexml/lexml09-flexivel.xsd` — vendored, byte-identical to upstream, never modified
- **Proposed schemas:** `lexml-proposed/*.xsd` — *generated* by `scripts/build_proposed_schemas.py`, carrying the LexML maintainers' not-yet-released `AgrupamentoHierarquico` change (§2.10)

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

**Out of scope:** RAG chunking/embedding (deferred by decision); the `Jurisprudencia` document type (deferred by decision); modifying the vendored LexML schemas (`lexml/` stays byte-identical to upstream — but see §2.10: the maintainers' own proposed change is carried in the *generated* `lexml-proposed/`, and the parser must keep working against the schemas as shipped, with the nested emitter opt-in until the change is released).

---

## 2. Findings That Constrain the Design

Established empirically across the two investigation rounds. These are load-bearing; each one changed the design.

### 2.1 `OpenStructure` cannot nest — *in the schemas as shipped*

> **Amended 2026-08-28 (A-R.1).** This finding remains true of the **vendored** schemas and therefore still governs the default emitter. It is **no longer true of the schemas the maintainers intend to ship** — see §2.10. The table below is consequently a statement about *a schema generation*, not an absolute: every row carries the generation it was measured against.

LexML supports non-statutory documents via `OpenStructure` (`<DocumentoGenerico>`), the counterpart of `HierarchicalStructure` (`<Norma>`). But it is deliberately flat. Verified against both vendored schemas:

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

**Consequence (vendored schemas):** LexML has no element that is both non-articulated and recursive. Hierarchy must be preserved out-of-band — the `id` path of §2.3, rendered by the `generico` emitter of §5.1.

**Consequence (proposed schemas, §2.10):** `AgrupamentoHierarquico` becomes exactly that element. Hierarchy is preserved *in-band*, and the `id` path becomes redundant belt-and-braces rather than the sole channel. Both consequences are live simultaneously, which is why the plan carries two emitters.

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

### 2.10 `AgrupamentoHierarquico` becomes prose-bearing and recursive (maintainers' proposal)

**Added 2026-08-28 (A-R.1).** Full evidence: `docs/20260827_111015_revised_plan_recursive_agrupamento_hierarquico_adoption.md`.

The LexML maintainers proposed a two-line change to `lexml-base.xsd` that makes `AgrupamentoHierarquico` a genuinely prose-bearing recursive container:

```xml
<xsd:extension base="hierarchy">
  <xsd:choice minOccurs="1" maxOccurs="unbounded">   <!-- was xsd:sequence -->
    <xsd:group   ref="LXhierCompleto"/>
    <xsd:element ref="Agrupamento"/>                 <!-- ADDED -->
    <xsd:element ref="Bloco"/>                       <!-- ADDED -->
  </xsd:choice>
  <xsd:attributeGroup ref="nome"/>
</xsd:extension>
```

Four findings, all measured against both schemas offline:

1. **It solves the core problem.** `AgrupamentoHierarquico` was *already* recursive — `hierarchy` admits `AgrupamentoHierarquico*`. What it lacked was prose-bearing leaves. `PartePrincipal` already accepts `AgrupamentoHierarquico`, so the open model reaches the recursive element with no further change. `pn_cst_38`'s four-level hierarchy (`2.` → `2.1` → `2.3` → `2.3.1`) validates natively, and `ancestor::`/`descendant::` recover it with **no `id`-path parsing**.
2. **It is verified backward compatible.** All 16 cases of the §2.1 matrix return identical verdicts under `lexml/` and `lexml-proposed/`. The edit is strictly additive.
3. **It supersedes our own §11 proposal**, which is withdrawn — see §11. `Agrupamento` stays flat; `Agrupamento`-in-`Agrupamento` still FAILS. Recursion lives *only* in `AgrupamentoHierarquico`. `Rotulo` and `NomeAgrupador` become first-class, retiring the `<Bloco nome="rotulo">` smuggling of §5.1.
4. **It carries three binding emitter constraints** (§5.4), of which the ordering one is a genuine wart.

**Release status — the reason this does not simply replace §2.1.** The change is **proposed, not released**. `lexml-proposed/` is *generated* from `lexml/` by `scripts/build_proposed_schemas.py`, verified to differ from upstream only by the edit above. Until upstream ships it, `generico` (flat) stays the default emitter and `generico-aninhado` is opt-in behind a **schema capability probe** (§2.11) that reads the schemas actually present rather than assuming a version.

### 2.11 Schema capabilities are probed, never assumed

**Added 2026-08-28 (A-R.2).** With two schema generations in the repository, no cycle may hard-code which one is present. `validate/schema.py` gains a probe that discovers, by validating canary fragments:

| Capability | Question it answers |
|---|---|
| `recursive_agrupamento_hierarquico` | does `AH > Agrupamento(p)` validate? |
| `prose_bearing_hierarchy` | may an `AH` have no articulated descendant? |
| `native_rotulo_nome_agrupador` | are `Rotulo`/`NomeAgrupador` usable on an `AH`? |
| `interleaved_children` | is prose-before-subsections order accepted? (§11 refinement only) |

Against `lexml/` all four are `False`; against `lexml-proposed/` the first three are `True` and `interleaved_children` is `False` — the maintainers' change does not remove the ordering constraint, and we do not build as though it did.

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
│ RENDERING              norma (+anexos) | generico | generico-aninhado   │
│  · validate-then-fallback: statutory attempt → generico on failure       │
├──────────────────────────────────────────────────────────────────────────┤
│ VALIDATION             lxml XMLSchema × 2 (rigido + flexivel) + rules    │
│  · schema-generation aware: lexml/ (shipped) | lexml-proposed/  ★ 2.11  │
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
  render/      generico.py  generico_aninhado.py  norma.py  anexo.py
               common.py  ids.py
  validate/    schema.py  rules.py  report.py
  segmentation/ api.py  xslt/segment_generico.xsl  xslt/segment_norma.xsl
                xslt/segment_generico_aninhado.xsl
  telemetry/   decisions.py  report.py
  cli.py
tests/
  unit/  golden/  fixtures/  regression/  referee_fixtures/  conftest.py
```

### 3.1 Internal model

Rendering-agnostic by design — this is what lets the emitters coexist without a rewrite. **That design paid off exactly as §11 predicted:** the maintainers' schema change (§2.10) costs one new emitter and *removes* another, and touches no line of the model below. `Section` was always a real tree; only the rendering of it changes.

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
class DocumentModel:                     # A-5.2: as delivered it stores the
                                         # component objects and derives the
                                         # rest; see the Cycle 5 amendment
    metadata: Metadata
    front: FrontMatter
    body: list[Section | Para | ListNode | Table]
    articulacao: list[Dispositivo]      # non-empty only on the norma route
    anexos: list[Anexo]
    back: BackMatter
    profile: str
    route: Literal["norma","generico"]   # rendering is chosen separately (§5)
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
    blockers: tuple[Blocker, ...] # A-4b.2: Blocker(code, detail, vetoes), not
                                  # bare strings — `nested_unavailable` is
                                  # recorded but must NOT veto the route (A-R.7),
                                  # and a string cannot carry that distinction.
                                  # `blocker_codes` gives this flat view back.
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

> **Note (A-R.7).** `route=generico` names a **routing** decision — *this document is not articulated* — not an emitter. A `generico`-routed document is rendered by either `generico` (flat) or `generico-aninhado` (nested) per §5, and the route table above is identical under both. Routing is about what the document *is*; rendering is about how it is written out.

---

## 5. Emitters

### 5.1 `generico` (flat, default)

**The default while the maintainers' change (§2.10) is unreleased.** Validates against the schemas as shipped.

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

The snippet is illustrative and omits three encodings the schemas require — a `<table>` must carry an `id`, a link is `<a xlink:href>` and never a plain `href`, and `ol`/`ul` take no attributes at all. See **A-5.3**. It also predates **A-5.1** (front and back matter are rendered as *regions*, so nothing between the named parts is lost), **A-5.4** (`<p class="quote">` carries `Para.kind`) and **A-5.7** (a body preamble is wrapped in `Agrupamento nome="texto"`).

### 5.2 `generico-aninhado` (nested, opt-in) — added 2026-08-28 (A-R.3)

Requires the §2.10 capability `recursive_agrupamento_hierarquico`. Selected by `--emitter=generico-aninhado`; **emitter selection** refuses with the probe's diagnostic when the vendored schemas are flat — the renderer itself always renders, see **A-5b.3**. **Becomes the default only once the change is released and `lexml/` is re-vendored** — a one-line default change plus a reviewed golden regeneration, gated on the probe (§2.11).

```xml
<DocumentoGenerico>
  <PartePrincipal id="pp1">
    <AgrupamentoHierarquico id="pp1_agh1" nome="secao">
      <Rotulo>2.</Rotulo>
      <NomeAgrupador>DAS SOCIEDADES COOPERATIVAS</NomeAgrupador>
      <AgrupamentoHierarquico id="pp1_agh1_agh1" nome="subsecao">
        <Rotulo>2.1</Rotulo>
        <NomeAgrupador>Empresas de serviços</NomeAgrupador>
        <Agrupamento id="pp1_agh1_agh1_txt" nome="texto">
          <p>Em linhas gerais, as cooperativas…</p>
        </Agrupamento>
      </AgrupamentoHierarquico>
      <Agrupamento id="pp1_agh1_txt" nome="texto">
        <p>Texto introdutório.</p>
      </Agrupamento>
    </AgrupamentoHierarquico>
  </PartePrincipal>
</DocumentoGenerico>
```

Differences from §5.1, each load-bearing:

- `Rotulo` and `NomeAgrupador` are **native**; `<Bloco nome="rotulo"|"nomeAgrupador">` is retired.
- `<Bloco nome="nivel">` is retired too — depth is `count(ancestor::AgrupamentoHierarquico)`, and a redundant marker that can disagree with the tree is a liability, not a safeguard.
- Prose lives in a single `<Agrupamento nome="texto">` leaf per section. **Never a bare `<p>` under an `AgrupamentoHierarquico`** — the proposal adds `Agrupamento` and `Bloco`, not `blockElements` (§2.1 row E still FAILS, correctly).
- **Rule A becomes structurally unnecessary**: a missing ancestor is a malformed tree, not a silently broken breadcrumb. Rule B still applies — nested-`li` duplication is a list problem, untouched by the schema change.
- `id`s stay path-composed (`pp1_agh1_agh1`) even though the nesting makes them redundant, so a segment URN means the same thing whichever emitter produced it.

Existing community tooling that walks `ancestor::*/NomeAgrupador` — including `scripts/GeraCSVporArtigoPorAgrupador.xsl` — becomes applicable to non-statutory documents, which was the original motivation of the whole investigation.

### 5.3 `norma` (+ `anexo`)

Per §4.3, matching the reference parser's conventions. Annex bodies (`Anexo > DocumentoGenerico > PartePrincipal`) may use the nested form when the capability is present — verified valid — giving `port_mf_277`'s 130-entry `ANEXO ÚNICO` real structure.

### 5.4 Three constraints binding on `generico-aninhado`

Measured against `lexml-proposed/`, not assumed. **Added 2026-08-28 (A-R.4).**

**Constraint 1 — subsections precede own prose.** Because `AgrupamentoHierarquico` extends `hierarchy`, whose base sequence ends with `AgrupamentoHierarquico*`, XSD appends the extension `choice` *after* it. The effective content model is:

```
Rotulo?  NomeAgrupador?  AgrupamentoHierarquico*  (LXhierCompleto | Agrupamento | Bloco)+
```

So a section's child sections must be serialised **before** its own prose — and, per **A-5b.1**, before *every* non-`AgrupamentoHierarquico` child, `Bloco` markers included. Natural reading order — `2.` intro text, then `2.1` — is **rejected**. Two consequences: the emitter sorts into a canonical order that is not document order, and **the segmentation reader must never infer reading order from sibling position** — it uses `Rotulo` or a recorded source index. This is the one property that made hand-inspection of flat output trustworthy, and it is lost; §11 offers a refinement upstream that would restore it.

**Constraint 2 — every `AgrupamentoHierarquico` needs at least one non-`AH` child** (`minOccurs="1"` on the extension choice). A section with subsections but no prose of its own cannot be a bare container, and an empty `<Agrupamento/>` is itself invalid (`blocksreq` is `minOccurs="1"`). **Resolution: emit `<Bloco nome="vazio"/>`** — `Bloco` extends `inline` at `minOccurs="0"`, so a genuinely empty one is valid. Verified. Alternatives considered and rejected: an `<Agrupamento><p/></Agrupamento>` injects an empty paragraph into text extraction and risks the conservation invariant; waiting for a `minOccurs="0"` upstream blocks on the maintainers (raised in §11 regardless). A test asserts the marker is invisible to text extraction and to segmentation.

**Constraint 3 — prose always needs an `Agrupamento` wrapper.** Restated from §5.2; it is a schema fact, not a style choice, and gets its own regression.

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

Segmenting from the in-process model is the primary path; the XML readers exist as the round-trip **test oracle**, which is exactly the reversibility invariant the suite requires. **Amended 2026-08-28 (A-R.5):** there are now two XML readers, and agreement is three-way:

```python
def segments_from_flat_xml(doc)   -> Iterator[Segment]:  # id-path reconstruction (Rules A/B)
def segments_from_nested_xml(doc) -> Iterator[Segment]:  # native ancestor::/descendant::
```

- `segments_from_nested_xml` parses **no `id`s at all**. Rule A is structurally guaranteed; Rule B still applies. Order comes from `Rotulo` or the recorded source index, never from sibling position (§5.4 Constraint 1), and the `<Bloco nome="vazio"/>` marker of Constraint 2 is skipped.
- **Three-way oracle agreement** — model, flat XML, nested XML — is the invariant. Segment URNs must be identical across all three, so a citation survives an emitter switch.

### 6.2 XSLT reference stylesheets

`segment_generico.xsl` (below, with Rules A/B applied), `segment_norma.xsl` (statutory-element based, adapting `GeraCSVporArtigoPorAgrupador.xsl`), and — **added 2026-08-28 (A-R.5)** — `segment_generico_aninhado.xsl`.

The nested stylesheet is markedly simpler than the flat one below: with native `Rotulo`/`NomeAgrupador` and real ancestry, the breadcrumb is `ancestor::AgrupamentoHierarquico/NomeAgrupador` and the `starts-with($myid, concat(@id,'_'))` / `string-length(@id)` machinery disappears entirely. That is the same idiom `scripts/GeraCSVporArtigoPorAgrupador.xsl` already uses, so **Cycle 7 probes whether that community stylesheet runs unmodified on nested output** and records the result — informational, not gating, but it is the strongest available argument for the maintainers' change and belongs in the reply to them (§11).

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

> **A-4b.4 (2026-08-28, Cycle 4b).** The reconciliation above assumes every
> flagged decision reaches a referee. It does not. §9.3 pins `--referee=none`
> for the whole regression suite, so flagged decisions are commonly *not*
> consulted; and a referee may **abstain** — a timeout, a 5xx, a malformed
> reply. The identities that hold in general are
>
> ```
> rule_only + flagged                       == total
> agreed + overrode + overruled + abstained == consulted   (consulted <= flagged)
> ```
>
> `agreed + overrode == flagged` is the special case where every flagged
> decision is consulted, none abstains and none is overruled, and it is
> asserted in exactly that form under an active referee. The report therefore
> carries `consulted`, `overruled` and `abstained` rows, and
> `DecisionsReport.check()` names whichever identity broke rather than merely
> returning false. Forcing the original identity by counting an unconsulted
> decision as an agreement was considered and rejected: it would report the
> rules as *confirmed* by a referee that was never asked, corrupting the one
> metric this section exists to produce.
>
> **`overruled` is a fourth bucket, and it is reachable.** A referee that
> answers, *contradicts* the rule, and is refused the override — because it was
> itself below `REFEREE_MIN_CONFIDENCE`, or because the rule was above
> `RULE_HIGH_CONFIDENCE` — has neither agreed nor overridden. Cycle 4b first
> implemented `agreed` as "consulted, not abstained, not overridden", which
> silently folded these in; a mutation sweep caught it. The error runs in the
> damaging direction: it manufactures evidence that the rules are right and
> merely too timid, out of cases where the referee actually disagreed. That
> reading is what §7.4 says should prompt tightening the thresholds.

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

**Amendment A-R.2 (Cycle 0 addendum, 2026-08-28) — the harness becomes schema-generation aware, and the §2.1 matrix becomes conditional.**

Cycle 0 shipped complete and stays complete; this is **additive work, scheduled with Cycle 5b** since nothing before it needs the capability. Three additions:

1. **Generation selection.** `validate/schema.py` learns a second schema root — `lexml-proposed/` (§2.10) alongside `lexml/` — so `load_schema`/`validate` can target either. `lexml/` remains read-only and byte-identical to upstream; `lexml-proposed/` is *generated* and equally never hand-edited.
2. **The capability probe** of §2.11:

```python
@dataclass(frozen=True)
class SchemaCapabilities:
    # What the schemas actually present permit, discovered by probing.
    recursive_agrupamento_hierarquico: bool
    prose_bearing_hierarchy: bool
    native_rotulo_nome_agrupador: bool
    interleaved_children: bool

def probe_capabilities(generation: str = "vendored") -> SchemaCapabilities: ...
```

   Never hard-code a schema version: the files present are the truth.

3. **The §2.1 matrix gains a `requires` field** naming the capability each case depends on. A case needing an unavailable capability is **skipped with a reason, not failed** — the matrix stops being a table of absolute truths and becomes a table conditional on the schema generation, which is what §2.1 now says it is.

Tests
- against `lexml/`, all four capabilities are `False` — pinning today's shipped reality
- against `lexml-proposed/`, the first three are `True` and `interleaved_children` is `False` (the maintainers' change does not remove the ordering constraint)
- **all 16 existing matrix cases return identical verdicts under both generations** — the backward-compatibility claim of §2.10, kept executable
- new matrix rows for the §2.10 encodings, each carrying its `requires` capability
- the probe never mutates either schema directory, and runs offline through the existing resolver
- `scripts/build_proposed_schemas.py --check` passes — the generated schemas are current
- a capability regression (a probe result changing unexpectedly) fails loudly

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
- `parecer_93` → authority `advocacia.geral.uniao`, type `parecer`, number `93`, date `2018-12-28` — **the date comes from a bare header stamp, not the epigraph; see Amendment A-2.1**
- `port_mf_277` → `ministerio.fazenda`, `portaria`, `277`, `2018-06-07`
- date forms: `28/12/2018`, `7 de junho de 2018`, ISO
- number normalisation `00093/2018` → `93`
- profile auto-selection correct for all 15 samples
- unmapped fields land in `MetadadoProprietario`; none dropped — **allowlist-gated per profile, see Amendment A-2.2**
- **4 of 15 samples carry no number/date and yield a best-effort URN flagged incomplete — see Amendment A-2.3**
- `<Metadado>` fragment validates on both schemas

**Amendment A-2.1 (Cycle 2, 2026-08-02) — `parecer_93`'s date is a header artifact, and the extractor needs a four-step chain, not an epigraph read.**

The expected value `2018-12-28` is correct, but it is **not on the epigraph line**: `PARECER n. 00093/2018/DECOR/CGU/AGU` carries no date at all. Three different dates appear in the document — a bare `28/12/2018` stamp at block 0 (a portal header artifact), the signature `Brasília, 19 de dezembro de 2018` at block 428, and the approving despacho's 27/12/2018. Extraction therefore uses an explicit chain, **epigraph → bare header stamp → signature → filename**, and records which branch fired in `Metadata.date_source` (`parecer_93` → `"header"`, the other 11 dated samples → `"epigraph"`).

Two consequences worth carrying forward:

1. **A year-only epigraph date does not end the chain.** The path-form epigraph yields only `2018`; a later source may *refine* it to a full date, but only when the years agree, so a stray date elsewhere cannot overwrite the epigraph's.
2. **A bare four-digit run is not a date.** Requiring the `de` cue is load-bearing: without it `PORTARIA MF nº 277` parses as the year 277. Caught by a test, not by review. *(Decided with the user during Cycle 2 reconciliation; the filename fallback is sanctioned as a last resort only.)*

**Amendment A-2.2 (Cycle 2, 2026-08-02) — `MetadadoProprietario` capture must be allowlist-gated, and the plan's field list is incomplete.**

The plan names four fields, all from `parecer_93`. A census across all 15 samples finds more that belong in the same channel — `Assunto`, `Ementa`, `Dispositivos Legais` (`par_cosit_26`), `JURISPRUDÊNCIA` (`ad_pgfn_*`), `Referência`, `Precedentes` (`sumula_stj_125`), `Nota Normas` (`port_mf_454`) — and, more importantly, shows that a naive `LABEL:` rule **captures prose as metadata**: `sumula_stj_125` alone yields `Advogados:` ×7, `Relator:`, `Recorrente:`, `Some-se:` and `O Sr. Ministro Garcia Vieira:`. Those lines are the structure of the *acórdão being reported*, not fields of the document.

Capture is therefore gated on a **per-profile allowlist**, plus a bounded-recall heuristic (ALL-CAPS label, ≤4 words) confined to the front-matter region. A missed field is recoverable — the text stays in the body for Cycle 3 to segment — whereas a false field is silent corruption. *(Decided with the user during Cycle 2 reconciliation.)*

**Amendment A-2.3 (Cycle 2, 2026-08-02) — four samples cannot produce a complete URN, and that is a first-class outcome.**

`sumula_carf_42`, `sumula_stj_125`, `REsp_1306393` and `CARNE_LEAO` carry no authority+type+number+date quadruple: súmulas and acórdãos are cited by number without a promulgation date, and the service description is not a legal act at all. Extraction is therefore **best-effort and never raises**: it emits a syntactically valid URN using sentinels (`0000` for an unknown date, `0` for an unknown number) and reports the gap honestly via `Metadata.complete` / `.missing`.

The sentinel must survive the module's own parser — `parse_urn(build_urn(...))` — so `UrnDate` accepts year 0 and exposes `is_unknown` to distinguish it from a real year. A test caught the original defect, where `build_urn` emitted `0000` and `parse_urn` then rejected it.

Known limit, documented rather than fixed: `is_valid_urn` checks the date's *shape*, not calendar validity, so `2018-13-45` passes it while `parse_urn` raises. Cycle 6 should not treat `is_valid_urn` as a guard for `parse_urn`. *(Decided with the user during Cycle 2 reconciliation.)*

**Amendment A-2.4 (Cycle 2, 2026-08-02) — `nota_tecnica` is deliberately not built.**

Plan §3's layout lists `profile/nota_tecnica.py`, but no sample in the corpus is a nota técnica. Building it would mean shipping untested regexes that no test could discharge. Six profiles are registered — `parecer` (covering *Parecer Normativo*), `ato_declaratorio`, `portaria`, `jurisprudencia_generico`, `servico`, `generic` — and `nota_tecnica` joins them when a sample exists. *(Decided with the user during Cycle 2 reconciliation.)*

### Cycle 3 — Front/back matter segmentation

`segment/`: epigraph, ementa, preamble, enacting formula (`DECLARA`, `RESOLVE:`), local/date closing, signatures, annex boundaries (`ANEXO ÚNICO`, `ANEXO I`), named fields; per-profile regex sets ported in spirit from `DocumentProfile.scala`; tolerance for absent front matter.

Tests
- `parecer_93`: epigraph `PARECER n. 00093/2018/DECOR/CGU/AGU`; ementa from `EMENTA:`
- `EMENTA:` with no space after colon still splits (observed in sample — in the
  source the label is followed by `<w:tab/>`, not a space)
- `ad_*`/`adn_*`: enacting formula `DECLARA` recognised; `port_mf_454`: `RESOLVE:`
- `port_mf_277`: `ANEXO ÚNICO` boundary found; annex body separated
- `sumula_stj_125`: its bare `ANEXO` paragraph is **not** an annex (A-3.3)
- `adn_cst_10`: the portal artifact `O ato não possui ementa. Ver íntegra` is
  **not** read as an ementa
- `CARNE_LEAO`: no ementa/preamble/signature — **no false positives**
- signature blocks (`NomePessoa` + optional `Cargo`) for all signed samples,
  with institution and heading lines rejected (`ACÓRDÃO`, `ADVOCACIA-GERAL DA
  UNIÃO`, `ACÓRDÃOS PARADIGMAS`, …)
- `ParteInicial`/`ParteFinal` fragments validate on both schemas — **and** the
  `generico` `Agrupamento` rendering does too, for all 15 samples (A-3.1)
- front / body / back / annexes **partition** the document's blocks (A-3.5)

**Amendment A-3.1 (Cycle 3, 2026-08-28) — front/back matter needs *two* renderings, because `ParteInicial`/`ParteFinal` do not exist in `DocumentoGenerico`.**

A schema probe run during Cycle 3 established that `ParteInicial` and
`ParteFinal` are declared inside `HierarchicalStructure` only. Placed inside
`DocumentoGenerico` (`OpenStructure`) both schemas reject them:

```
Element 'ParteInicial': This element is not expected.
Expected is one of ( PartePrincipal, Anexos )
```

Since §4.4 routes **14 of the 15 samples** to `generico`, a single rendering
would have served either one sample or fourteen, never both. Cycle 3 therefore
delivers a rendering-agnostic model plus two verified renderings: the native
elements for the statutory route, and `<Agrupamento nome="epigrafe"|"ementa"|
"preambulo"|"formulaPromulgacao"|"assinatura"|"localDataFecho">` blocks for the
open one. Both were probed valid on both schemas for all 15 samples. This
follows §3.1's rendering-agnostic design: the model is decided once, the
rendering twice. *(Decided with the user during Cycle 3 reconciliation.)*

**Amendment A-3.2 (Cycle 3, 2026-08-28) — `LocalDataFecho` and `FormulaPromulgacao` require an `id` and `<p>` wrapping.**

Both are `textoSimplesType`, which is **element-only**. Bare text is rejected on
both schemas, as is a missing `id`:

```
Element 'LocalDataFecho': The attribute 'id' is required but missing.
Element 'LocalDataFecho': Character content other than whitespace is not
allowed because the content type is 'element-only'
```

The valid shape is `<LocalDataFecho id="ldf1"><p>Brasília, 7 de junho de
2018.</p></LocalDataFecho>`. `Epigrafe` and `Ementa` differ — they are
`inlineReq`, so they take text directly but still require an `id`.

§4.3's snippet is **unaffected**: it carries no `LocalDataFecho`, and was
re-validated during this cycle and confirmed valid exactly as written. The
constraint is recorded here because Cycle 6 emits the closing line that §4.3
omits, and would otherwise discover it by failing. Pinned by tests in
`tests/unit/test_segment_render.py`.

**Amendment A-3.3 (Cycle 3, 2026-08-28) — annex detection is allowlisted per profile.**

An ungated `^ANEXO` rule fires twice on the corpus: correctly on
`port_mf_277`'s `ANEXO ÚNICO` (block 6), and catastrophically on
`sumula_stj_125` block 369 — a bare paragraph reading `ANEXO` inside a
compilation of court precedents that has no annex, where it would amputate 28
blocks into a non-existent sibling document.

`DocumentProfile` therefore gains `annex_res`, empty for
`jurisprudencia_generico` and `servico`. This is the A-2.2 reasoning applied
again: a missed annex is recoverable because the text stays in the body,
whereas a false annex is silent corruption. `DocumentProfile` also gains
`enacting_res` and `closing_res`, all three defaulting to `()` so no existing
construction changes. *(Decided with the user during Cycle 3 reconciliation.)*

**Amendment A-3.4 (Cycle 3, 2026-08-28) — `segment/fields.py` is not built; Cycle 2's capture is re-exported.**

§3's layout lists `segment/fields.py`, but labelled-field capture already
shipped in Cycle 2's `model/metadata.py` under the allowlist ratified by
A-2.2. A second implementation would be a competing source of truth for a
decision already taken, so `FrontMatter.fields` re-exports
`Metadata.proprietary` instead. `segment/` ships `model.py`, `frontmatter.py`,
`backmatter.py`, `sections.py`, `render.py` and `__main__.py`.

**Amendment A-3.5 (Cycle 3, 2026-08-28) — every signature block is recorded, and the parts form a partition.**

`parecer_93` carries an appended `DESPACHO DO CONSULTOR-GERAL DA UNIÃO` after
its own signature, with its own header, NUP, date and signer;
`pn_cst_38` carries two signatures outright. `BackMatter.signatures` is
therefore an ordered tuple of every block found, and `BackMatter.trailing`
covers closing notes below the last signature (`par_cosit_26`'s `Nota Normas:`
disclaimer, `port_mf_454`'s "originally published without an ementa").

Correspondingly, `FrontMatter.span` is the **contiguous hull** of its parts,
not their union: `parecer_93`'s epigraph is block 3, behind a portal date
stamp and an institutional banner, and its ementa is block 9, behind `NUP:`,
`INTERESSADOS:` and `ASSUNTO:`. Together these make front / body / back /
annexes a **partition** of the document's blocks — every non-empty block in
exactly one part, none twice and none nowhere — which is text conservation
(§9.2) stated as arithmetic and asserted for all 15 samples.
*(Decided with the user during Cycle 3 reconciliation.)*

### Cycle 4 — Hierarchy inference

`hierarchy/`: `labels.py` (`1.`, `1.1`, `1.1.1`, `I -`, `a)`, `c. 1)`, `CAPÍTULO`, `Seção`, `Subseção`, ordinals, roman, `único`, `-A`); **`quotation.py` redesigned** around indentation + citation antecedent + numbering monotonicity + omissis runs; `evidence.py`; `unify.py` (level unification, depth monotonicity); `tree.py`; confidence scoring; flat fallback.

Tests
- label grammar: ~40 parametrised forms → (kind, value, arity), **including negatives** (`1.500/2014` in a citation is not a label; `Lei nº 12.618` is not a label, and neither is `2.08.30.00` or `06.12` — A-4.2)
- **quotation guard: every paragraph-initial `Art.` in `parecer_93` is content, not structure** (regression-critical; 25 under a quote-tolerant regex, 21 under §2.5's stricter one — the count is not the point)
- `par_cosit_26`: `Art. 52. .........` recognised as omissis-bearing quotation; numbering `2,3,16,18,52` flagged non-monotonic
- `CARNE_LEAO`: `Heading1`→1, `Heading2`→2, children attached correctly
- `pn_cst_38`: `2.` → `2.1` → `2.3` → `2.3.1` yields depths 1/2/2/3
- `port_mf_454`: `1.`, `2.`, `2.1`, `a)` hierarchy correct
- depth monotonicity: never increases by more than 1 between consecutive headings
- nested list reconstruction from `ilvl` — **synthetic fixture**, no sample has a contiguous multi-level Word list (A-4.6)
- style/label evidence conflict resolves deterministically
- low confidence ⇒ flat fallback, no fabricated sections
- idempotence: inferring twice yields an identical tree
- **`sumula_stj_125` groups by case** — 7 identified headings, 31 parts (A-4.3)
- **`port_mf_277`'s annex carries its own tree** — 65 `Súmula CARF nº N` sections (A-4.5, discharging A-R.8 early)

Exit: all 15 samples produce trees matching hand-authored goldens.

**Amendment A-4.1 (Cycle 4, 2026-08-28) — the indent discriminator is declared-vs-inherited, not deviation.**

§2.5 proposed measuring each paragraph's indent against the document's modal
body indent. On `parecer_93` that arithmetic does not work: the quote band is
**2908** and the modal body indent is **2909**, one twip *above* it. What
separates them is where the number comes from — ordinary body text *inherits*
2909 from the `Normal` style (216 of 397 paragraphs declare no direct indent at
all), while every quoted paragraph *declares* its own. `detect_quote_bands`
therefore has two rules and picks whichever the document supports: `deviation`
(values ≥ modal + 300 twips, ≥3 paragraphs) and `declared` (modal is inherited,
and declared indents ≥300 cluster). `sumula_stj_125` resolves by the first,
`parecer_93` only by the second, and eight samples by neither.

A precedence rule falls out of the same measurement: **a paragraph Word itself
declares a heading is never quoted.** Without it, `sumula_stj_125`'s eight
centred `EMENTA` headings (1371 twips against a body of 893) land in the
deviation band and the document loses half its structure.

**Amendment A-4.2 (Cycle 4, 2026-08-28) — three negative rules the grammar needs, each forced by a real paragraph.**

1. **A zero or zero-padded component is not an ordinal.** `pn_cst_38` opens with
   `1.24.20.25 -`, `2.08.30.00 -`, `2.16.25.00 -` — subject-classification
   codes, not fourth-level sections. The same rule disposes of
   `sumula_stj_125`'s `06.12`/`06.10`, and it is what lets a two-component date
   be told apart from `2.1`, which by shape alone it cannot be.
2. **An orphan dotted label is not a label.** `1.24.20.25` survives rule 1, and
   is refused instead by unification: its parent `1.24.20` was never opened.
   This belongs to the document, not to the grammar — `2.3.1` is a good label
   when `2.3` is open and noise when it is not.
3. **A top-level numeric series must start at 1 or 2 and step by ≤3, or the
   whole series is rejected.** `parecer_93`'s depth-1 numeric candidates read
   `1, 11, 111, 46, 194, 74` in document order; a document does not number
   itself backwards. (`par_cosit_26` starts at `2.` because its `1.` sits in
   the front matter, which is why 2 is allowed.)

A fourth, smaller rule joins them: a **solitary** roman/alpha label is not an
enumeration. `parecer_93` block 330 is an OCR'd footnote marker `n.` that would
otherwise become a section of the parecer.

**Amendment A-4.3 (Cycle 4, 2026-08-28) — numbered-container demotion.**
*(Decided with the user during Cycle 4 reconciliation.)*

`sumula_stj_125`'s body is 38 `Heading 1` blocks: seven naming a case
(`RECURSO ESPECIAL N. 34.988-SP`) and thirty-one naming a part of one
(`EMENTA`, `ACÓRDÃO`, `RELATÓRIO`, `VOTO`). Word records **no** difference
between them — identical style, outline level, typography, alignment and
indent — so the grouping is read from what the headings say about themselves: a
heading carrying its own identifier names a thing, and identifier-free headings
after it name parts of it.

Deliberately not a vocabulary rule. Three guards keep it from firing on a
document that merely happens to have a number in a heading: the run of
same-level style headings must be ≥4 long, must **start** with an identified
heading, and must genuinely mix the two (≥2 identified, ≥1 bare). `CARNE_LEAO`
declines on the first count (no heading carries an identifier) and
`port_mf_277`'s annex on the third (all 65 do).

**Amendment A-4.4 (Cycle 4, 2026-08-28) — named units are a series, not a grammar rule.**

`Súmula CARF nº 1` is a heading only because 65 of them run in order through
`port_mf_277`'s annex. `detect_unit_series` requires ≥3 whole-paragraph
occurrences sharing a folded head word with strictly increasing numbers, and
feeds the heads it finds back into `parse_label`. That is what stops
`Lei nº 12.618` from ever parsing as a label: it appears only inside sentences,
never as a paragraph of its own.

The sibling-gap limit does **not** apply to a unit series, which was validated
document-wide already. The annex runs `1, 3, 4 … 33, 40, 41 …` — the gaps are
the súmulas CARF revoked — and a gap limit would amputate it at nº 33.

**Amendment A-4.5 (Cycle 4, 2026-08-28) — the deliverable is a `HierarchyDoc`: body *and* each annex.**
*(Decided with the user during Cycle 4 reconciliation.)*

Hierarchy is inferred over the body span and over each annex span separately,
so `infer_hierarchy` returns a `HierarchyDoc` carrying one `HierarchyTree` per
region rather than a bare tree. This discharges **A-R.8** a cycle early:
`port_mf_277`'s `ANEXO ÚNICO` gains 65 real sections instead of being a flat
blob, and Cycle 6 inherits the result rather than re-importing this package to
compute it. The annex's own marker paragraph is its *title*, not part of its
body.

**Amendment A-4.6 (Cycle 4, 2026-08-28) — `ilvl` nesting is tested synthetically.**

**No sample has a contiguous multi-level Word list.** `CARNE_LEAO`'s `ilvl=1`
and `ilvl=2` paragraphs (blocks 22 and 34) are eleven blocks apart, so they are
two single-level lists rather than one nested one. Nesting is therefore
exercised by a synthetic fixture, following the A-1.3 precedent for NFC
normalisation — and it earned its place immediately: the first implementation
dropped every nested item, and no corpus golden could have caught it.

### Cycle 4b — Statutory Viability Analyzer + LLM Referee + Telemetry

> **Amended 2026-08-28 by the executing cycle** — A-4b.1 … A-4b.6 below. The
> deliverables stand; five test bullets are corrected in place and one is added.

`routing/`: article census, indentation discrimination, numbering monotonicity, omissis/citation cues, genre priors, coverage; structured `StatutoryViability` with blockers.
`referee/`: `Referee` protocol, `NullReferee`, `CachedAPIReferee` (OpenAI-compatible ⇒ DeepSeek/Qwen/Moonshot), `LocalReferee` (llama.cpp), disk cache, prompt templates, JSON schema constraints.
`telemetry/`: `DecisionRecord`, structured logging, `--decisions-report`.

Tests — routing
- **expected route for all 15 samples matches §4.4** (labelled fixture table)
- `parecer_93` and `par_cosit_26` **must not** route to `norma`
- `port_mf_277` routes to `norma` **with** annex split; coverage computed after separation
- coverage gate rejects low-coverage articulation
- verdicts deterministic under `NullReferee`
- **A-R.7:** requesting `generico-aninhado` against flat schemas yields blocker `nested_unavailable` with the probe's diagnostic. **Routing decisions are otherwise unchanged** — the §4.4 route table stands, because routing is about *what the document is*, not how it is rendered. *(A-4b.1: the probe this needs was pulled forward from the Cycle 0 addendum into 4b.)*
- **A-4b.2:** the route turns on **four gates** — `articles_own ≥ 1`, monotonic series, `coverage ≥ 0.6`, no vetoing blocker — and `articles_own = articles_found − articles_quoted` is the number that discriminates. Measured: `port_mf_277` is the only sample with a surviving own article (2, monotonic, coverage 1.0 after the annex split); `parecer_93` is 25/25 quoted and `par_cosit_26` 5/5

Tests — referee
- `NullReferee` ⇒ byte-identical output to referee-disabled
- cache hit avoids network (mocked transport asserts zero calls)
- malformed/non-JSON LM response ⇒ rule verdict retained, `WARN` logged
- API timeout/5xx ⇒ graceful fallback, pipeline completes
- referee **cannot** flip a high-confidence rule verdict
- `par_cosit_26` resolves correctly with a **recorded fixture** (`tests/referee_fixtures/`), no live API. *(A-4b.5: the fixtures are hand-authored, documented as such, with a documented refresh command; and they assert the referee **agrees** with a rule verdict that is already correct — see A-4b.3.)*
- prompts contain no PII beyond the excerpt; excerpt length bounded
- **A-4b.3:** the corpus flags exactly **four** decisions — `par_cosit_26` p#46/p#47/p#53 and `parecer_93` p#36 — so the referee's whole corpus workload is four questions, all of which the rules already answered correctly
- **A-4b.6:** an **adversarial** referee answering "own" to every question changes no sample's route. Invariant #9 asserted as an attack, not only as a threshold

Tests — telemetry
- every flagged decision produces a `DecisionRecord`
- **override emits `WARN` containing both rule and referee verdicts plus rationale** (asserted on log text)
- **rule failure emits `RULE FAILED` with the reason**
- `--decisions-report` counts reconcile: `rule_only + flagged == total`; `agreed + overrode == flagged` — **corrected by A-4b.4** to `agreed + overrode + abstained == consulted`, with `consulted ≤ flagged`. The original form is false under `--referee=none`, which §9.3 pins for the whole regression suite; it is asserted in its original form under an active referee
- records are stable across reruns given a warm cache

Exit: routing correct for all 15 samples; referee integrated, cached, fail-safe; interventions visibly logged and countable.

### Cycle 5 — Emitter `generico` (flat, default)

`model/document.py` (**`DocumentModel`, landing here rather than in 4b or 6 — A-5.2**); `render/generico.py`; `render/ids.py` (path-composed unique ids, **Rule A** materialising every intermediate prefix); `render/common.py` (**front/back matter rendered as *regions*, not parts — A-5.1**); flattening with `<Bloco nome="rotulo"|"nomeAgrupador"|"nivel">`; nested `ol`/`ul`; tables **with inline-only cell content (§2.2)** and a required `id` (**A-5.3**); `Anexos`/`ReferenciaAnexo` **plus the sibling annex documents themselves (A-5.6)**.

Tests
- all 14 `generico`-routed samples validate on **both** schemas — **and `port_mf_277` too, rendered flat as §3's fallback (A-5.5)**
- `id`s unique document-wide (explicit `xsd:ID` check)
- **Rule A: every proper prefix of every `Agrupamento` `id` exists** (the breadcrumb-gap regression)
- **Rule B: leaf-only text — no duplication** (the nested-`li` regression)
- `id` path encodes depth; **tree reconstructable from XML alone**
- nested lists survive as nested `ol`/`ul`
- tables emit inline cell content, never `<p>` (guards the `td` finding)
- text conservation: every source paragraph's text appears exactly once — **including the 40 blocks that sit inside a front/back hull and inside no named part (A-5.1)**
- goldens committed for all 15, **16 files: an annex is its own document (A-5.6)**

**Amendment A-5.1 (Cycle 5, 2026-08-28) — front and back matter are rendered as *regions*, not as parts, or 40 blocks are lost.**

Cycle 3 delivered `render_front_generico` / `render_back_generico`, which render
the **named parts**: epigraph, ementa, preamble, enacting formula, signatures,
closing date. But `FrontMatter.span` and `BackMatter.span` are the contiguous
**hulls**, deliberately so (A-3.5), because that is what makes front / body /
back / annexes a partition of the document. The blocks *between* the named
parts are therefore inside the segmentation and inside no rendered element.

Measured over the corpus, that is **40 non-empty blocks in 6 of the 15
samples**: `parecer_93` 21 (its portal date stamp, its three-line institutional
banner, its `NUP:` / `INTERESSADOS:` / `ASSUNTO:` lines, and 14 blocks of
closing matter), `pn_cst_38` 7 (a classification header, `De acordo` and
`Publique-se`, sitting *between* its two signature blocks), `REsp_1306393` 7,
`par_cosit_26` 3, `adn_cst_10` 1, `port_mf_454` 1. An emitter that renders
parts fails invariant #2 on its first document.

`render/common.py`'s `front_region()` / `back_region()` therefore walk each hull
in document order, emit every named part exactly as Cycle 3 does — reusing its
`agrupamento_block()` primitive rather than reimplementing the shape (the A-3.4
rule) — and emit every maximal run of unclaimed non-empty blocks as
`Agrupamento nome="preliminar"` (front) or `nome="nota"` (back). Cycle 3's two
functions are unchanged and still tested; they are simply not what a
whole-document emitter calls. Conservation becomes arithmetic over regions
rather than over an enumerated list of part names, which is what makes it hold
on the 285 documents not yet seen.

One consequence for Cycle 5b and Cycle 6: a region is not optional decoration,
and a nested or statutory emitter that renders only the typed elements will
reintroduce the same hole.

**Amendment A-5.2 (Cycle 5, 2026-08-28) — `DocumentModel` lands in Cycle 5, and §3.1's field list is corrected.**

§3.1 places `DocumentModel` in `model/document.py`; Cycle 4b was expected to
build it and did not, so the first cycle that genuinely needs all five views of
a document at once builds it. *Decided with the user.*

The delivered shape differs from §3.1's sketch in one structural way: it stores
the **component objects** — `metadata`, `segmentation`, `hierarchy`,
`viability`, `styled` — rather than re-flattening their contents into
`front` / `body` / `anexos` / `back` fields. `body` and `annexes` are
properties reading through to the `HierarchyDoc`; front and back matter are
read from the `Segmentation`. Copying them out would produce a second, and
divergeable, copy of what Cycles 3 and 4 already own. `articulacao` is declared
and empty until Cycle 6, exactly as §3.1 intends. `decisions` is declared **and
populated**: Cycle 4b already records why a routing call went the way it did,
and `DecisionRecord` carries no timestamp, so determinism (invariant #4) holds.

`model/document.py` imports `Segmentation` under `TYPE_CHECKING` only — the
`segment` package imports `model`, so a module-level import is a cycle.

**Amendment A-5.3 (Cycle 5, 2026-08-28) — three encodings §5.1's snippet does not show, each forced by the schemas.**

Probed against both shipped schemas before a line was written:

- **`<table>` requires an `id`** (`idreq`), and both schemas reject one without.
  Table ids follow §2.9's reference convention: `pp1_tabN` in the primary,
  `anexoN_tabM` inside an annex.
- **A hyperlink is `<a xlink:href="…">`.** The `link` attribute group declares
  `xlink:href` and declares it *required*; a plain HTML `href` is **rejected**.
  Cycle 1 captures 11 hyperlink targets across the corpus, so this is live.
- **`ol` and `ul` accept no attributes at all** — not even an `id`. A list is
  reachable only through its containing `Agrupamento`.

Two further facts the emitter depends on, also measured: an `Agrupamento` with
no children is **invalid** (`blocksreq` is `minOccurs="1"`), which is why
`<Bloco nome="nivel">` is emitted unconditionally rather than only when useful;
and an `xsd:ID` is an `NCName`, so no id may begin with a digit.

**Amendment A-5.4 (Cycle 5, 2026-08-28) — `Para.kind` survives into the XML as `@class`.**

The quotation guard's verdict is the corpus's most consequential inference — it
is what stops `parecer_93`'s 21 quoted articles being published as the parecer's
own — and discarding it at the emitter would make the artifact unable to say
what the parser concluded. A non-default kind is written as `<p class="quote">`
(likewise `citation`, `field`, `omissis`); `prose` writes nothing. `class` is on
`HTMLattrs` and valid on both schemas; it adds no text, so conservation is
untouched. Cycle 7's round-trip reader can therefore recover `kind` rather than
comparing text and structure alone. *Decided with the user.*

**Amendment A-5.5 (Cycle 5, 2026-08-28) — all 15 samples are rendered flat, not 14.**

The exit criterion is unchanged: the **14** `generico`-routed samples must
validate on both schemas. But `port_mf_277` is rendered and pinned too. It is
plan §3's documented validate-then-fallback rendering, so every document must
have one; and it is the corpus's **only** document with an annex, hence the only
exercise of `Anexos`/`ReferenciaAnexo` and of conservation across the annex
split. Cycle 6 emits `norma` for it and this golden stays as the fallback
evidence. *Decided with the user.*

**Amendment A-5.6 (Cycle 5, 2026-08-28) — the annex *documents* are emitted here, not deferred to Cycle 6.**

Cycle 5's deliverable list names `Anexos`/`ReferenciaAnexo` and Cycle 6's names
the sibling `<LexML><Anexo>` documents. A pointer with no target loses the
annex's text, so the pointer alone cannot satisfy invariant #2 —
`port_mf_277`'s `ANEXO ÚNICO` is 65 sections. `render_generico` therefore
returns a **bundle**: the primary carrying
`<Anexos><ReferenciaAnexo AlvoURN="…!anexo1"/></Anexos>`, plus one
`<LexML><Metadado/><Anexo><DocumentoGenerico>` document per annex, with
`PartePrincipal id="anexo1_pp"` and tables `anexo1_tabM` — §2.9's convention
verbatim. Cycle 6 reuses this for the statutory route rather than inventing it.
The annex's own marker paragraph is emitted as `Agrupamento nome="tituloAnexo"`,
because A-4.5 deliberately excludes it from the annex's tree and the emitter is
the only place it can be conserved. *Decided with the user.*

**Amendment A-5.7 (Cycle 5, 2026-08-28) — a body preamble is wrapped in `Agrupamento nome="texto"`.**

`HierarchyTree.preamble` — the body content preceding the first section, which
is the *entire* body of the seven samples that come back flat — could be emitted
as bare `<p>` under `PartePrincipal`, which is valid (§2.1 row A). It is
wrapped instead, so that every content node sits in a citable, `id`-bearing
container: that is what §2.4's segmentation consumes, and an unwrapped
paragraph has no URN fragment to be cited by. `texto` is also the `nome` §5.2
gives a nested prose leaf, so the two emitters agree on segment URNs, which is
what invariant #11 requires of Cycle 5b. This is a flat container, not inferred
hierarchy, so invariant #8 is untouched.

**Amendment A-5b.1 (Cycle 5b, 2026-08-29) — Constraint 1 binds *every* non-`AgrupamentoHierarquico` child, not only prose.**

§5.4 states Constraint 1 in terms of a section's own prose: subsections must be
serialised before it. Measured against `lexml-proposed/` before implementation,
the constraint is broader — **a `Bloco` may not precede an
`AgrupamentoHierarquico` either.** The extension `choice` follows the base
sequence's `AgrupamentoHierarquico*` for `Bloco` exactly as it does for
`Agrupamento`, so the effective content model is:

```
AgrupamentoHierarquico[@id required][@nome required] ::=
    Rotulo?  NomeAgrupador?  AgrupamentoHierarquico*  (Agrupamento | Bloco | LXhierCompleto)+
```

An emitter written to §5.4's literal wording produces **invalid** XML on any
section that has both subsections and an order marker. The emitter's canonical
child order therefore places the marker after the subsections, alongside the
prose leaf. Twenty-four probe cases pin the model, including the negatives that
matter: prose-before-subsections fails, a `Bloco` before a subsection fails, an
`AH` with no non-`AH` child fails, a bare `<p>` under an `AH` fails (so §2.1 row
E survives the change, correctly), and `NomeAgrupador` before `Rotulo` fails.

**Amendment A-5b.2 (Cycle 5b, 2026-08-29) — `<Bloco nome="ordem">` is emitted on *every* child, not only unlabelled ones.**

Cycle 5b's bullet gives an explicit order index "for unlabelled sections",
§5.4 saying a reader "uses `Rotulo` or a recorded source index". Both children
of an `AgrupamentoHierarquico` — subsection and prose leaf alike — now carry a
0-based document-order index instead. Two reasons. A reader then needs **one**
rule rather than two, and a rule with no fallback cannot fall back wrongly.
And `Rotulo` is not reliably sortable: `2.`, `2.1`, `IV` and `a)` do not order
under any single comparison, so "use `Rotulo` where present" is a sort key that
works until it silently does not. The marker carries no source text, so
extraction and conservation are untouched — asserted, not assumed.
*Decided with the user.*

**Amendment A-5b.3 (Cycle 5b, 2026-08-29) — the nested emitter renders unconditionally; the *capability gate* is on validation and emitter selection.**

§5.2 says `generico-aninhado` "refuses with the probe's diagnostic when the
vendored schemas are flat". Read literally that refuses on every default
checkout: `lexml/` — the shipped generation, and the default everywhere — **is**
flat, so the emitter could not be exercised even by its own tests. Corrected:
`render_generico_aninhado()` is a pure function and always renders. What
consults `probe_capabilities()` is *emitter selection* (the CLI's
`--emitter=generico-aninhado`, Cycle 8) and *validation*. Every nested
assertion in the suite skips with the probe's own diagnostic when the capability
is absent, which is how A-R.9's "suite green against `lexml/` alone" is met.
*Decided with the user.*

**Amendment A-5b.4 (Cycle 5b, 2026-08-29) — invariant #11 is cross-emitter equivalence of *text* and *segment URN structure*, not of `id` strings.**

§5.2 keeps ids path-composed "so a segment URN means the same thing whichever
emitter produced it". Measured, the two emitters' body ids differ in **two**
independent ways, and the second was not anticipated by the plan:

1. **The token.** §5.2's own snippet fixes `pp1_agh1_agh1` for a nested section
   and `pp1_agh1_txt` for its prose leaf, while Cycle 5's `agr` scheme is fixed
   by sixteen committed goldens.
2. **A top-level ordinal offset.** The flat emitter numbers body sections in the
   *same* root `agr` sequence as the front-matter regions — `Scope.adopt`
   advances that counter past them — while the nested emitter opens a fresh
   `agh` sequence. With three front regions, `pn_cst_38`'s first section is
   `pp1_agr4` flat and `pp1_agh1` nested. `IdAllocator` keys its counters on
   `(parent, token)`, so the two sequences are independent by construction.

The practical consequence, which belongs in any consumer documentation: **a
segment URN is not portable between emitters.** `!pp1_agr4` and `!pp1_agh1`
name the same section under different addresses.

Renaming either scheme to force literal equality would contradict a ratified
artifact — §5.2's snippet on one side, sixteen goldens on the other — in order
to simplify a test, and sharing the ordinal sequence would still leave the
tokens different. So what is asserted instead: **identical text** (as a
multiset, across the whole bundle) and **identical segment-URN structure** for
body sections — the path of sibling ordinals, normalising away exactly those two
differences and no others. The front and back matter region ids *are*
byte-identical, because both emitters call the same `front_region`/`back_region`.
Tests pin the boundary in both directions: the region ids must match, and the
body offset must remain exactly the front-region count, so a third drift or a
reparented section fails loudly rather than being absorbed.

One asymmetry is itself a finding: the offset is measurable only on the nested
side. In flat output a top-level body section and a front-matter region are
structurally indistinguishable — both are `Agrupamento` children of
`PartePrincipal` with all-`agr` ids — while nested output separates them by
element name.

**Amendment A-5b.5 (Cycle 5b, 2026-08-29) — six of the sixteen documents contain no `AgrupamentoHierarquico` at all.**

`REsp_1306393`, `ad_pgfn_3`, `ad_srf_22`, `adn_cosit_19`, `sumula_carf_42` and
`port_mf_277`'s **primary** (all 65 of its sections live in the annex) have no
body sections to nest. They are front and back matter, which both emitters
render identically through the shared regions (A-5.1), so their nested output is
**byte-identical to their flat output** and is *correctly* valid on the shipped
schemas. Consequence for the test suite: "nested output is invalid on `lexml/`"
is true **iff** the document actually nests. Asserting it unconditionally pins a
defect rather than a property — this was found by writing the stronger assertion
first and watching it fail on exactly those six.

### Cycle 5b — Emitter `generico-aninhado` (nested, opt-in) — added 2026-08-28 (A-R.3)

Runs after Cycle 5, reusing its `Section` tree and `id` scheme. Carries the Cycle 0 addendum (A-R.2) with it — the capability probe lands here, because this is the first cycle that needs it.

`render/generico_aninhado.py`, per §5.2:

- `Section` → `<AgrupamentoHierarquico id nome>` with native `<Rotulo>`/`<NomeAgrupador>`
- prose, lists and tables → one `<Agrupamento nome="texto">` leaf per section
- **child sections emitted before the section's own prose leaf** (§5.4 Constraint 1), with source order preserved in `Rotulo` and, for unlabelled sections, an explicit `<Bloco nome="ordem">` index
- **`<Bloco nome="vazio"/>`** for sections with subsections but no prose of their own (Constraint 2)
- `id`s path-composed, identical to Cycle 5's, so segment URNs match across emitters
- `<Bloco nome="rotulo"|"nomeAgrupador"|"nivel">` **not emitted**

Tests
- all 14 `generico`-routed samples validate on **both** `lexml-proposed/` schemas (skipped, with a reason, when the probe reports flat schemas)
- **native-axis reconstruction:** the tree recovered via `ancestor::`/`descendant::` alone equals the tree recovered from `id` paths, for all 14
- **Constraint 1 regression:** for every `AH`, no `Agrupamento` sibling precedes an `AgrupamentoHierarquico` sibling
- **Constraint 2 regression:** every `AH` has ≥1 non-`AH` child; the `vazio` marker is invisible to text extraction and segmentation
- **Constraint 3 regression:** no bare `<p>` is ever a child of an `AgrupamentoHierarquico`
- no `Bloco nome="rotulo"|"nomeAgrupador"|"nivel"` anywhere in the output
- **cross-emitter equivalence:** `generico` and `generico-aninhado` carry identical text content and identical segment URNs
- `id` uniqueness; conservation (every source paragraph exactly once)
- **Rule A asserted unnecessary:** a deliberately gapped tree is structurally impossible to emit
- `pn_cst_38`'s four levels (`2.` → `2.1` → `2.3` → `2.3.1`) reproduce the §2.10 depth/breadcrumb output exactly
- goldens committed for all 14

Exit: nested output validates on both proposed schemas; hierarchy recoverable by standard axes with no `id` parsing; text and URNs identical to the flat emitter.

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
- **A-R.8:** with the capability present, annex bodies may use the nested form — verified valid — giving `port_mf_277`'s 130-entry `ANEXO ÚNICO` real structure; conservation and URN fragments hold identically either way

**Amendment A-6.1 (Cycle 6, 2026-08-29) — dispositivo ids are pattern-constrained, so they need their own allocator.**

`lexml09-flexivel.xsd` restricts `idArtigo` with an `xsd:pattern`:

```
art(\d+(-[0-9]{1,3}){0,3}|1u)((_cpt|(_(par|dpg)(\d+…|1u)))(_(inc|ali|dpg)\d+…)?)?
```

so `art1`, `art1_cpt`, `art1_par1`, `art1_cpt_inc1` are legal and **`pp1_art1`
is rejected by both schemas**:

```
Element 'Artigo', attribute 'id': [facet 'pattern'] The value 'pp1_art1' is
not accepted by the pattern …
```

Cycle 5's path-composed `IdAllocator` therefore cannot issue dispositivo ids —
its `child()` contract *composes an id from a parent it has issued*, which is
exactly what this pattern forbids. `render/norma.py` declares a separate
`DispositivoIds`. The two id spaces coexist in one document without colliding,
because a `Norma` primary has no `Agrupamento` and an annex has no dispositivo;
a test asserts uniqueness across the whole bundle rather than trusting the
argument. §4.3's snippet was already using the right ids — it just did not say
they were mandatory. *(Decided with the user during Cycle 6 reconciliation.)*

**Amendment A-6.2 (Cycle 6, 2026-08-29) — `ParteInicial`/`ParteFinal` are closed, so A-5.1's region rendering has no statutory equivalent.**

Both elements are `xsd:sequence`s of **only** their named parts. Measured:
`<Agrupamento>` and a bare `<p>` are rejected inside each of them:

```
Element 'Agrupamento': This element is not expected. Expected is ( LocalDataFecho )
Element 'p': This element is not expected. Expected is one of ( FormulaPromulgacao, Epigrafe, … )
```

So the rendering amendment A-5.1 forced for `generico` — regions, not parts,
because 40 non-empty blocks in 6 samples sit inside a hull and inside no named
part — **cannot be reproduced here**. One escape exists and one does not:

* `Preambulo` is `textoSimplesType` and takes several `<p>`, so **front residue
  folds into it**, in document order, ahead of the preamble's own lines;
* `ParteFinal` offers nothing — an extra `<p>` inside `Assinatura`, a childless
  `AgrupamentoHierarquico` and an `Agrupamento` are all rejected — so **back
  residue makes the document unrenderable as a `Norma`** and it falls back to
  `generico` with blocker `back_matter_residue`.

`port_mf_277` carries zero residue of either kind, so this changes nothing for
the corpus and prevents silent loss in the 300+ unseen documents. Text is never
dropped to keep a route. *(Decided with the user during Cycle 6 reconciliation.)*

**Amendment A-6.3 (Cycle 6, 2026-08-29) — the validate-then-fallback gate is validity *and* conservation *and* coverage.**

§4.2 says "if it fails schema validation or the conservation/coverage
invariants", and all three are implemented, because **no schema can detect lost
text**. That is not hypothetical: this cycle's first statutory render of
`port_mf_277` was valid on both schemas and 29 words short, and the conservation
gate is what caught it (the defect was in extraction — see A-6.4).

Four named blockers, three of them new in `BLOCKER_CODES`:

| Gate | Code |
|---|---|
| fails either shipped schema | `statutory_invalid` |
| word multiset ≠ the `generico` render's | `statutory_lossy` |
| back-matter residue with no legal home (A-6.2) | `back_matter_residue` |
| articulation coverage < 0.6 | `low_coverage` *(existing)* |

`RenderedDocument.emitter` records which emitter actually produced the artifact,
so a fallback is visible in the output and not only in the log. **Routing is
unchanged** — this is a *rendering* verdict, exactly as A-R.7 separates the two.
*(Decided with the user during Cycle 6 reconciliation.)*

**Amendment A-6.4 (Cycle 6, 2026-08-29) — `leaf_texts` reads the statutory elements, and skips a `Caput`'s echoed `Rotulo`.**

`render/common.py::leaf_texts` was written for `generico` and knew nothing of
`Epigrafe`, `Ementa`, `NomePessoa` or `Cargo` — all four declared **only**
inside `HierarchicalStructure`, so no `generico` document can contain one, and
their absence went unnoticed for three cycles. On a `Norma` it is a 29-word
conservation hole.

The second half is a decision, not a fix. §4.3's snippet and the reference
parser both give `Caput` its own `Rotulo`, copying the `Artigo`'s — but the
source wrote that rótulo **once**. Counting the copy reports a word the document
never said twice. `leaf_texts` therefore skips a `Rotulo` whose parent is a
`Caput`, on exactly the precedent already in that module: `Bloco nome="nivel"`
is excluded because it carries a value *this package inferred* rather than text
the source contained. The alternative — stop emitting the copy, which is valid —
was rejected because §5.3 requires matching the reference parser's conventions.
Adds no text and removes none, so the `generico` route is untouched: all 32
committed goldens are byte-identical. *(Escalated to and decided with the user.)*

**Amendment A-6.5 (Cycle 6, 2026-08-29) — the annex convention is one shared module, and A-R.8's nesting is a flag, not a probe.**

Cycle 5 delivered plan §2.9's annex convention (A-5.6) and Cycle 5b copied it so
its annexes could nest. A third copy for the statutory route would be the
"competing source of truth" A-3.4 refused, so all three now call
`render/anexo.py::render_anexo(model, annex, *, nested=False)`. The refactor is
byte-identical by construction and by assertion: 32 committed goldens did not
move, and a test compares the `norma` and `generico` annex goldens directly.

`nested` is an **explicit flag** chosen by the emitter (`generico` and `norma`
flat, `generico-aninhado` nested), never read from `probe_capabilities()`.
Selecting it from the probe — A-R.8's most literal reading — would make emitted
output depend on which directories exist on the machine, breaking determinism
(§9.2) and making the goldens un-committable. A-R.8 is discharged by tests
proving a nested annex body is valid on `lexml-proposed/` and correctly rejected
on `lexml/`, skipping with the probe's own diagnostic when the generation is
absent (A-5b.3's rule). *(Decided with the user during Cycle 6 reconciliation.)*

**Also measured during Cycle 6, and recorded because the emitter depends on it:**
`Anexo` is a `choice` of `DocumentoGenerico` and `DocumentoArticulado` and
**never `Norma`**, which both schemas reject; `Anexos` must follow `ParteFinal`
inside `Norma`, the reverse order failing on both; an `Artigo` without a
`Rotulo` and a `Caput` before its `Rotulo` are each rejected, which is what makes
"a deliberately mis-ordered tree fails validation" assertable against the schema
rather than against a check of our own; and a `table` or an `ol` inside a
`Caput` is rejected, so a body article carrying one cannot be articulated and
falls back.

### Cycle 6b — Emitter `articulado-sintetico` — ~~planned~~ **withdrawn 2026-08-28 (A-R.6)**

**This cycle is dropped. Its round-trip reader moves to Cycle 7.**

The emitter's entire justification was: *some consumers need genuinely nested XML, and the only way to get it is to synthesise `Artigo`s the source does not have.* §2.10 removes that premise — real nesting is now available **without asserting articulation the source lacks**, which was always this emitter's semantic sin: presenting a parecer's numbered sections as articles of a statute is exactly the misreading the Cycle 4 quotation guard exists to prevent, committed deliberately on output.

Dropping it removes the emitter, its goldens, and the `MetadadoProprietario` provenance machinery that existed solely to stop synthetic articles being mistaken for real ones.

**Retained and relocated:** `hierarchy_from_xml()`, the round-trip reader, moves to **Cycle 7**. It is the oracle for every emitter and is *more* valuable now, not less — with two emitters in play it is what proves they agree.

**Reinstate only if** a consumer is identified that specifically requires `Artigo`-shaped output. Recorded here rather than deleted, so the reasoning survives if that consumer appears.

### Cycle 7 — Segmentation output

`segmentation/api.py` with **both** XML readers (§6.1); `segment_generico.xsl`; `segment_norma.xsl`; **`segment_generico_aninhado.xsl`**; `hierarchy_from_xml()` round-trip reader **relocated here from the withdrawn Cycle 6b (A-R.6)**; CSV/JSONL writers.

Tests
- **A-R.5: three-way oracle agreement** — model, flat XML and nested XML segment identically on all 15 samples (the nested leg skipped, with a reason, when the capability is absent)
- **segment URNs identical across emitters** — a citation survives an emitter switch
- **nested reader parses no `id`s**: asserted by mutating every `id` in a nested document and checking the segments are unchanged
- **order comes from `Rotulo`/source index, never sibling position** (§5.4 Constraint 1) — a document whose serialisation order differs from reading order still segments in reading order
- **round-trip:** `model → generico → model'` and `model → generico-aninhado → model''` preserve tree shape and all text
- **`GeraCSVporArtigoPorAgrupador.xsl` compatibility probed on nested output and the result recorded** — informational, not gating (§6.2)
- breadcrumbs complete for all 15 samples — **no missing ancestors** (Rule A end-to-end)
- **no duplicated text in any segment** (Rule B end-to-end)
- segment URNs unique, stable across reruns, and resolvable to their `Agrupamento`/dispositivo
- XSLT and Python paths produce equivalent rows (skipped if `saxonche` absent)
- `norma`-routed documents segment via statutory elements
- `port_mf_277` segments span primary **and** annex

### Cycle 8 — Generalisation, robustness, CLI

`cli.py`: `parse`, `dump-styled`, `dump-tree`, `segment`, `validate`, `list-profiles`, `decisions-report`, **`capabilities`** (mirroring `FECmdLine`'s shape); HTML and plain-text ingestion; `generic` catch-all profile; structured warnings; confidence reporting; `--profile`/`--emitter`/`--schema`/`--referee`/`--strict`.

Tests
- CLI end-to-end on all 15 samples, all emitters
- degenerate inputs: empty document, single paragraph, headings only, no headings, deeply nested lists, unlabelled prose, tables only — none crash, all emit valid XML
- malformed/corrupt DOCX ⇒ clean error, non-zero exit, no traceback
- HTML and TXT ingestion reach the same model shape
- `--strict` fails on validation error; default warns and continues
- confidence and referee status surfaced in output
- **A-R.9:** `--emitter` accepts `generico-aninhado`; a `capabilities` command reports what the schemas present permit; requesting an unavailable emitter exits cleanly with the probe's diagnostic and a non-zero status, never a traceback

Exit: "handles any document" demonstrated — valid output or a clean diagnostic for every fixture.

### Cycle 9 — Regression consolidation and corpus scale-out

Promote all goldens to `tests/regression/`; `make regression`; coverage gate; corpus-expansion guide (new document = fixture + expected route + golden); **batch mode for the 300+ corpus** with an aggregate decisions report; documentation of `docs/`/`dev/` conventions.

Tests
- full suite green; coverage ≥ 85% on `hierarchy/`, `routing/`, `render/`
- every golden regenerable by one documented command
- **a deliberate mutation fails the suite** (proving the tests bite)
- batch mode over all samples produces a single reconciling decisions report
- referee disabled ⇒ suite still green (no network dependency anywhere)
- **A-R.9:** nested goldens for all 14; cross-emitter equivalence in the regression suite; the mutation test bites on the §5.4 Constraint 1/2/3 invariants
- **the whole suite passes against `lexml/` alone** — with `lexml-proposed/` absent, nested tests skip with a reason and nothing fails. The parser's correctness must not depend on an unreleased schema

---

## 9. Test Strategy

### 9.1 Layers

| Layer | Purpose | Location |
|---|---|---|
| Unit | label grammar, URN, evidence scoring, id generation, coverage math | `tests/unit/` |
| Schema matrix | the §2.1 encodings stay true, on both schemas, **per generation (§2.11)** | `tests/unit/test_schema_matrix.py` |
| Capability probe | what `lexml/` vs `lexml-proposed/` permit, pinned | `tests/unit/test_capabilities.py` |
| Golden | byte-stable `StyledDoc` / tree / XML / segments per sample | `tests/golden/` |
| Routing | expected route per sample (§4.4) | `tests/unit/test_routing.py` |
| Referee | recorded-fixture adjudication; fail-safe paths | `tests/referee_fixtures/` |
| Telemetry | override/failure logging, report reconciliation | `tests/unit/test_telemetry.py` |
| Round-trip | XML → model preserves shape and text, **both emitters** | `tests/regression/` |
| Cross-emitter | flat and nested carry identical text and segment URNs | `tests/regression/` |
| Conservation | no text lost or duplicated, including across the annex split | `tests/regression/` |
| Robustness | degenerate/corrupt inputs never crash | `tests/unit/test_robustness.py` |
| Validation | every emitted document validates on both schemas | all cycles |

### 9.2 Cross-cutting invariants

Asserted throughout — these are what make the parser trustworthy on the 285 documents we have not seen.

1. **Validity** — output validates against **both** schemas (configurable).
2. **Conservation** — all source text present exactly once, including across `Norma`+`Anexo`.
3. **Reversibility** — hierarchy reconstructable from output alone: the `id` path on the flat emitter, native `ancestor::`/`descendant::` axes on the nested one.
4. **Determinism** — same input + same referee cache ⇒ byte-identical output.
5. **`id` uniqueness** — required by `xsd:ID`; enforced document-wide.
6. **Ancestor totality (Rule A)** — every proper prefix of an `id` path exists. *Required of the flat emitter; structurally guaranteed by the nested one, where a gap is a malformed tree (§5.2).*
7. **No text duplication (Rule B)** — leaf-only extraction.
8. **No fabrication** — low confidence degrades to flat, never invents structure.
9. **Referee is advisory** — cannot override high-confidence rules; disabling it never breaks the pipeline.
10. **Observability** — every rule failure and referee override is logged and counted.
11. **Cross-emitter equivalence (A-R.3)** — every emitter carries identical text content and identical segment URNs. Choosing a rendering must never change what the document *says* or how a segment is cited. *Refined by **A-5b.4**: equivalence is asserted on text (as a multiset) and on segment-URN **structure** for body sections. The id token necessarily differs there — `agr` flat, `agh`/`txt` nested, both fixed by ratified artifacts — while the front/back region ids are byte-identical.*
12. **Capability honesty (A-R.2)** — no code assumes a schema generation. Behaviour is gated on the probe, and the suite is green against `lexml/` alone.

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
| `OpenStructure` cannot nest (§2.1) | high — core requirement | dual-representation; depth in `id` path + `Bloco nivel`; reversibility test. **Largely retired by §2.10 once released** |
| **Maintainers' change never ships, or ships altered** | medium | flat emitter stays default; the probe reads the schemas present, never a hard-coded version; nested emitter is purely additive; suite green without `lexml-proposed/` |
| **Nested serialisation order ≠ reading order (§5.4 C1)** | medium | canonical emit order + `Rotulo`/explicit order index; segmentation never infers order from sibling position; refinement offered upstream (§11) |
| **Constraint 2 forces a synthetic child** | low | `<Bloco nome="vazio"/>`, verified valid, tested invisible to text extraction and segmentation |
| **Two emitters diverge in content** | medium | cross-emitter equivalence is invariant #11, asserted in Cycle 5b and the Cycle 9 regression suite |
| **`lexml-proposed/` drifts from `lexml/`** | low | *generated*, never hand-edited; `build_proposed_schemas.py --check` in the suite; the patch failing to apply is the signal upstream has shipped |
| Quoted statute misread as articulation | **high — silent corruption** | indentation + citation antecedent + monotonicity + omissis; regression on `parecer_93`'s 21 quotes; referee on residue |
| 15 samples ⇏ 300+ corpus | high | genre-agnostic evidence fusion; `generic` profile; flat fallback; **telemetry to measure rule generalisation**; batch mode (Cycle 9) |
| Coverage misjudged ⇒ lossy statutory render | high | coverage gate + validate-then-fallback + conservation invariant |
| Referee nondeterminism leaks into output | medium | advisory-only; cached; `NullReferee` in tests; invariant #4 |
| LLM cost/availability | low | ~$1–3/corpus; cached; fail-safe to rules |
| Rule A / Rule B regressions | medium | both are explicit invariants with dedicated tests (both were real bugs) |
| `<td>` rejects `<p>` | medium | in the schema matrix from Cycle 0; reference parser confirms inline-only |
| Strict `Artigo` ordering | medium | matrix cases; emitter asserts order |
| ~~Synthetic articles mislead consumers~~ | — | **retired: the `articulado-sintetico` emitter is withdrawn (A-R.6)** |
| Schema/version drift | medium | §2.1 matrix re-runs on any schema change, **per generation**; capability probe fails loudly on an unexpected result |
| DOCX style inheritance (`basedOn`) missed | low | explicit resolution + test |

---

## 11. Engagement with the LexML Community

**Rewritten 2026-08-28 (A-R.6).** This section previously carried *our* proposal to make `Agrupamento` recursive via `blocksreq`. **That proposal is withdrawn.** The maintainers proposed a better change, by a different route, and it is theirs that the plan now builds against (§2.10). The original text is preserved in `docs/20260801_142630_…` §6 for the record.

### 11.1 Why ours was withdrawn

We attacked `blocksreq`, making `Agrupamento` recursive. The maintainers attacked the other end, making `AgrupamentoHierarquico` prose-bearing. Theirs is better for a reason we had missed entirely: **`AgrupamentoHierarquico` was already recursive**, and `PartePrincipal` already accepted it. Recursion was never the missing piece — prose-bearing leaves were. Our proposal was aiming at a wall while the door stood open.

Theirs also reuses `hierarchy`, so `Rotulo` and `NomeAgrupador` come along for free. That was a *separate*, secondary request in our draft; their route grants it structurally. And because `Agrupamento` stays flat, prose cannot leak into `Artigo` or `Capitulo` — the statutory model keeps its integrity, which ours would have put at risk.

**Consequence for the plan:** any design assuming nested `Agrupamento` is rewritten to use `AgrupamentoHierarquico` as the container and `Agrupamento` as the prose leaf. `Agrupamento`-in-`Agrupamento` still FAILS and always will.

### 11.2 What to send back to the maintainers

The reply should endorse their change and add value rather than restate the problem:

1. **Endorse it, with evidence.** Their change makes `pn_cst_38_19801031`'s four-level hierarchy natively representable, validated on both `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd`. All 16 cases of our pinned §2.1 matrix are unchanged: the edit is strictly additive. Our harness reproduces every claim offline.

2. **Withdraw ours explicitly**, so no one implements two competing changes.

3. **Confirm the ergonomic win they may not have set out to make.** `Rotulo`/`NomeAgrupador` become available to non-articulated documents, so existing breadcrumb tooling that walks `ancestor::*/NomeAgrupador` — `GeraCSVporArtigoPorAgrupador.xsl` among it — becomes applicable to them. Cycle 7 probes whether that stylesheet runs *unmodified* on nested output; if it does, that result is the strongest argument for the change and belongs in the reply.

4. **Report the ordering constraint (§5.4 C1) as a usability finding, and offer the refinement.** Moving `AgrupamentoHierarquico` out of the `hierarchy` base and into the extension `choice` makes children order-free, letting sections interleave prose and subsections in true document order:

```xml
<xsd:complexType name="hierarchy">
  <xsd:sequence>
    <xsd:element ref="Rotulo"        minOccurs="0" maxOccurs="1"/>
    <xsd:element ref="NomeAgrupador" minOccurs="0" maxOccurs="1"/>
  </xsd:sequence>                              <!-- AH* removed from here -->
  <xsd:attributeGroup ref="corereq"/>
</xsd:complexType>

<xsd:choice minOccurs="1" maxOccurs="unbounded">
  <xsd:group   ref="LXhierCompleto"/>
  <xsd:element ref="AgrupamentoHierarquico"/>  <!-- moved here -->
  <xsd:element ref="Agrupamento"/>
  <xsd:element ref="Bloco"/>
</xsd:choice>
```

   Verified: prose-first order flips FAIL → PASS, nested-first keeps passing, and all 16 matrix cases stay unchanged. **State the caveat honestly:** `hierarchy` is the base type of every statutory aggregator (`Parte`, `Livro`, `Titulo`, `Capitulo`, `Secao`, `Subsecao`), so this has a wider blast radius than editing `AgrupamentoHierarquico` alone. The maintainers own that judgement. **This is an ergonomics improvement to offer, not a blocker to insist on** — the parser works either way, and §5.4 C1 is how it absorbs the constraint if they decline.

5. **Raise `minOccurs`** (§5.4 C2): the extension `choice` at `minOccurs="1"` makes a subsections-only section invalid, forcing a synthetic `<Bloco nome="vazio"/>` child. `minOccurs="0"` would remove that need, and is as small an edit as the ordering fix.

6. **Re-raise the two carried-over observations.** `<td>` accepts inline content but not `<p>`, unlike every other block container. And `<p>` is still not permitted directly under `AgrupamentoHierarquico` (§2.1 row E), so prose always needs an `Agrupamento` wrapper — worth confirming that is intentional.

7. **Ask the release question.** Which schema version carries the change, and will `lexml-br-rigido.xsd` / `lexml09-flexivel.xsd` be re-issued together? The capability probe (§2.11) means the parser adapts automatically, but the re-vendoring step needs a version to pin.

8. **Offer the corpus.** `pn_cst_38_19801031` and `port_mf_454_19770825` are public-domain motivating examples.

### 11.3 When the change ships

A tracked, reviewable sequence — not a rewrite:

1. Re-vendor `lexml/` from upstream.
2. Run `python3 scripts/build_proposed_schemas.py --check`. **It will fail**, because the region the patch targets no longer matches. *That failure is the signal.*
3. Delete `lexml-proposed/` and `scripts/build_proposed_schemas.py`; point validation at `lexml/` alone.
4. Flip the default emitter to `generico-aninhado` — one line, gated on the probe — and regenerate goldens as a reviewed diff.
5. The capability probe stays. It is how the next schema change is discovered rather than assumed.

---

## 12. Cycle Summary

Revised 2026-08-28 (§14). Cycle order:

```
0, 1, 2, 3, 4, 4b, 5, 5b  ✅ complete  →  6, 7, 8, 9
                                          └── 6b withdrawn; round-trip reader → 7
```

| Cycle | Deliverable | Key exit criterion |
|---|---|---|
| 0 ✅ | Scaffolding, dual-schema harness | §2.1 matrix executable and green — **+ capability probe (A-R.2): the probe landed in 4b (A-4b.1), the matrix `requires`/skip machinery in 5b (C-6). Addendum complete** |
| 1 ✅ | DOCX → `StyledDoc` (incl. indentation) | 15 samples ingest losslessly |
| 2 ✅ | Metadata, URN, profiles | correct URN/metadata for all samples |
| 3 ✅ | Front/back matter segmentation | zero false positives on bare documents |
| 4 ✅ | Hierarchy inference + quotation guard | every quoted article in `parecer_93` rejected; 15 trees match hand-authored goldens |
| 4b ✅ | Routing + LLM referee + telemetry | routes match §4.4; overrides logged and counted |
| 5 ✅ | Emitter `generico` (flat, **default**) | 14 samples valid on the **shipped** schemas; Rules A/B hold — **all 15 rendered and pinned (A-5.5); conservation covers the 40 inter-part blocks (A-5.1)** |
| 5b ✅ | Emitter `generico-aninhado` (nested, opt-in) | native axes recover hierarchy; text and URNs ≡ flat emitter — **16 documents rendered and pinned; Constraint 1 binds `Bloco` too (A-5b.1); `ordem` on every child (A-5b.2)** |
| 6 | Emitter `norma` + `Anexo` split | `port_mf_277` split, conservation across both documents |
| ~~6b~~ | ~~Emitter `articulado-sintetico`~~ | **withdrawn (A-R.6)** — round-trip reader relocated to Cycle 7 |
| 7 | Segmentation output (API + XSLT) | **three-way oracle agreement**; breadcrumbs complete |
| 8 | Robustness + CLI | every degenerate input handled cleanly; capabilities reported |
| 9 | Regression consolidation + batch | mutation test bites; corpus report reconciles; **suite green without `lexml-proposed/`** |

---

## 13. Traceability

Everything in this plan is grounded in verified evidence rather than assumption. The investigation record is preserved in `docs/`:

- **`docs/20260801_004745_…`** — schema investigation; validation matrix A–R; reference-parser survey; §11 reproducible schema harness (offline `xml.xsd` stub + `schemaLocation` rewrite).
- **`docs/20260801_142630_…`** — segmentation proof (Saxon XSLT 3.0, verbatim output); Rules A/B discovered by running the transform; indentation discriminator across 15 samples; local-SLM feasibility; dual-schema equivalence analysis; **our recursive `Agrupamento` proposal — since withdrawn (§11.1), retained for the record**.
- **`docs/20260827_111015_…`** — evaluation of the maintainers' `AgrupamentoHierarquico` change: the §3.1/§3.2 encoding tables, the 16-case backward-compatibility run, the ordering-constraint measurements, and the §3.7 refinement. **Source of every amendment in §14.**
- **`docs/20260828_011050_plan_update_recursive_agrupamento_hierarquico.md`** — the record of *applying* that evaluation to this plan: what changed, what did not, and why.
- **This document** — the consolidated plan, as amended.

Both predecessor documents contain the originating prompts verbatim, for reproducibility.

---

## 14. Amendment Log — 2026-08-28 Revision

Source: `docs/20260827_111015_revised_plan_recursive_agrupamento_hierarquico_adoption.md`. Cycles 0–2 are **complete and unaffected**; no delivered work is invalidated.

| ID | Section(s) | Amendment |
|---|---|---|
| A-R.1 | §2.1, §2.10 | §2.1 is re-scoped to *the schemas as shipped* and is no longer absolute. New §2.10 records the maintainers' prose-bearing recursive `AgrupamentoHierarquico`, its four findings, and its unreleased status |
| A-R.2 | §2.11, Cycle 0 addendum, §9.1, §9.2 | Schema capabilities are **probed, never assumed**. `validate/schema.py` gains a second generation (`lexml-proposed/`) and `probe_capabilities()`; matrix cases gain `requires` and skip rather than fail. New invariant #12 |
| A-R.3 | §5.2, Cycle 5b, §9.2 | New emitter `generico-aninhado` and new **Cycle 5b**. New invariant #11 (cross-emitter equivalence) |
| A-R.4 | §5.4 | Three binding constraints on the nested emitter: subsections-before-prose, ≥1 non-`AH` child (`<Bloco nome="vazio"/>`), prose needs an `Agrupamento` wrapper |
| A-R.5 | §6.1, §6.2, Cycle 7 | Segmentation gains `segments_from_nested_xml()` and `segment_generico_aninhado.xsl`; the oracle becomes **three-way** |
| A-R.6 | §11, Cycle 6b, §10, §12 | **Cycle 6b withdrawn** — `articulado-sintetico` is dropped, its round-trip reader relocated to Cycle 7. **Our own §11 recursive-`Agrupamento` proposal is withdrawn** in favour of the maintainers'; §11 becomes the engagement plan, including the §3.7 refinement to offer and the ship sequence |
| A-R.7 | Cycle 4b | Blocker reason `nested_unavailable`. Routing decisions otherwise unchanged — the §4.4 route table stands |
| A-R.8 | Cycle 6 | Annex bodies may use the nested form when the capability is present |
| A-R.9 | Cycle 8, Cycle 9 | `--emitter=generico-aninhado`; new `capabilities` CLI command; nested goldens and cross-emitter equivalence in the regression suite; **the suite must stay green against `lexml/` alone** |

**Decisions taken with the user while applying this revision (2026-08-28):**

1. **Cycle 6b is dropped**, not merely deferred (A-R.6). Its round-trip reader is retained and relocated.
2. **`lexml-proposed/` is the patched-schema location**, replacing the revision document's proposed `tests/fixtures/schemas/`. Verified by diff: it carries the maintainers' change *verbatim and nothing else* — only the `AgrupamentoHierarquico` edit plus a generated-file header — so the location is a repository-layout matter that leaves the proposal untouched.
3. **The maintainers' proposal prevails.** The §3.7 refinement is *ours*, and is **forwarded upstream as a suggestion only** (§11.2 item 4). The emitter is built against the maintainers' change as written and absorbs the ordering constraint (§5.4 C1). No third "refined" schema generation is produced, and `interleaved_children` probes `False` against both generations present.
