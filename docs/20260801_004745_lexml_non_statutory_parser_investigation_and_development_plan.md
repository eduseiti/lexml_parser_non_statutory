# LexML Parser for Non-Statutory Documents — Investigation and Development Plan

- **Date:** 2026-08-01
- **Status:** Investigation complete; plan proposed, not yet implemented
- **Target language:** Python 3
- **Reference implementation consulted:** `../lexml-parser-projeto-lei` (Scala, Senado Federal)
- **Schemas consulted:** `lexml/lexml-base.xsd`, `lexml/lexml-br-rigido.xsd`, `lexml/lexml09-flexivel.xsd`

---

## 1. Originating Prompt (verbatim, for reproducibility)

> I want to create a LexML parser capable of handling non statutory documents. Investigate how LexML can support non-statutory documents ― "documentos não articulados" ― in a way to incorporate any available hierarchical elements inside the document, such as chapters, sections, subsections, numbered or bulleted lists, considering the target documents will always be from the Brazilian legal domain, and will have most of the statute specifications, like publication authority, publication date, numbering, preamble, enacting formula, etc. From the investigation result, create a detailed development plan, devising development cycles including verification tests which can later be used for regression. Ideally, the parser should be able to handle any document, properly identifying the relevant parts. If you judge relevant, look at the parser implementation in "../lexml-parser-projeto-lei" for a reference of a LexML statutory documents parser, written in Scala, although for this current parser, I prefer it in Python. Capture everything in a .md document inside the "docs" folder, including this requesting prompt for reproductibility purposes.

---

## 2. Executive Summary of Findings

LexML **does** support non-statutory documents, through a content model the schema calls **`OpenStructure`**, exposed as the `<DocumentoGenerico>` document type. This is the counterpart of `HierarchicalStructure` (`<Norma>`), used for statutes.

However — and this is the single most consequential finding of this investigation — **the `OpenStructure` model is deliberately flat. It cannot express recursive hierarchy.** I verified this empirically against the real schemas with `lxml` (see §4.3 for the full validation matrix, and §11 for the reproducible harness). Both the rigid and the flexible schema reject nested grouping in the non-articulated model:

- `<Agrupamento>` inside `<Agrupamento>` → **rejected**
- `<div>` inside `<div>` → **rejected**
- `<AgrupamentoHierarquico>` containing text blocks (`<p>`) → **rejected**
- `<AgrupamentoHierarquico>` with no articulated descendant → **rejected**

The root cause is in `lexml-base.xsd`. `Agrupamento` and `div` both derive from the complexType `blocksreq`, whose content is the group `blockElements` = `{p, ul, ol, table, Bloco, ConteudoExterno}`. That group contains **no container element**, so recursion is structurally impossible. Meanwhile `AgrupamentoHierarquico` derives from `hierarchy` and is required to contain `LXhierCompleto` (`Parte | Livro | Titulo | Capitulo | Secao | Subsecao | Artigo`) — i.e. it is a *statutory* grouping device and always bottoms out in `Artigo`.

This produces a genuine dilemma for our target corpus, which is characterised precisely by having **deep hierarchy but no articles**: a *parecer* with sections `1`, `1.1`, `1.1.a`; a service description with `Heading1`/`Heading2` plus bulleted lists. LexML, as specified, has no single element that is both non-articulated and recursive.

**Resolution adopted by this plan:** a *dual-representation* architecture. The parser builds one rich internal hierarchical model, then emits it through one of two selectable target profiles:

- **Profile `generico` (default, strictly schema-valid):** `<DocumentoGenerico>/<PartePrincipal>` with a **flattened** sequence of sibling `<Agrupamento>` elements. Hierarchy is not lost — it is preserved *out-of-band*, in the hierarchical `id` path (`pp1_agr1_agr2`), in `@nome`, and in a `<Bloco nome="nivel">` marker. This validates against `lexml-br-rigido.xsd` today, with zero schema modification.
- **Profile `articulado-sintetico` (opt-in, lossless nesting):** map hierarchy onto native `AgrupamentoHierarquico` + `Artigo`, which *is* recursive and *does* validate (verified: PASS on both schemas). The cost is that non-articulated section bodies must be synthesised as `Artigo`/`Caput`, which is a semantic fiction.

Both were validated; §4.3 records the evidence. The recommendation is to ship `generico` as the default because it never lies about the document's nature, and to offer `articulado-sintetico` for consumers (e.g. RAG chunkers) that need real tree nesting in the XML itself.

---

## 3. The Target Corpus

Two real samples are in `samples/`. I dumped their DOCX paragraph structure (style + numbering + text) to ground the design in reality rather than assumption.

### 3.1 `parecer_93_2018_decor_cgu_agu.docx` — a legal opinion (AGU)

Structure observed:

```
[]        28/12/2018                                     ← publication date
[Heading1] ADVOCACIA-GERAL DA UNIÃO / CONSULTORIA-GERAL…  ← authority
[Heading1] PARECER n. 00093/2018/DECOR/CGU/AGU            ← epigraph (type + number + year)
[]        NUP: 03154.004642/2018-50                       ← process number
[]        INTERESSADOS: …                                 ← named field
[]        ASSUNTO: BENEFÍCIO ESPECIAL PREVISTO NA LEI…     ← named field
[]        EMENTA: ADMINISTRATIVO. SERVIDOR PÚBLICO. …      ← ementa (abstract)
[]        I - A teor do §1º do art. 3º da Lei nº 12.618…   ← roman-numbered conclusions
[]NUM     - O beneficio especial de que trata o § 1º…      ← Word-numbered list items
[]        Cod. Ement. 34
[]NUM     Cuidam os autos de pedido formulado pela…        ← numbered body paragraphs
[]        "o Beneficio Especial corresponde a uma…         ← block quotations
[]        Art. 40. Os pareceres do Advogado-Geral…         ← QUOTED statute text (not our articles!)
[]        § 1º O parecer aprovado e publicado…             ← quoted statute
[]        1 - REGIME DE PREVIDÊNCIA COMPLEMENTAR           ← numbered section heading
[]        c. 1) contribuições previdenciárias a serem…     ← sub-sub-heading
```

Key lessons this sample teaches:

1. It has **most statutory front matter** (authority, date, epigraph, ementa) — confirming the user's premise. `<ParteInicial>`-style extraction is applicable.
2. Its hierarchy is expressed by **numbered headings in body text** (`1 -`, `c. 1)`), *not* by Word styles. Style-based detection alone is insufficient.
3. It **quotes statutory text** (`Art. 40.`, `§ 1º`). A naive article recogniser would catastrophically misread these quotations as the document's own articulation. This is the single biggest correctness hazard in the corpus and is why Cycle 4 has a dedicated quotation-guard requirement.
4. `[]NUM` markers show Word list numbering is load-bearing and must be read from `numbering.xml`.

### 3.2 `sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO.docx` — a service description (Receita Federal)

```
[Heading1] Sistema de Recolhimento Mensal Obrigatório (Carnê-Leão)
[Heading2] O que é?
[]        O Carnê-leão é o imposto sobre a renda…
[Heading2] Quem pode utilizar este serviço?
[]NUM     pessoas físicas, residentes no Brasil…      ← bulleted list
[Heading2] Etapas para a realização deste serviço
[]NUM     Informar rendimentos e emitir o DARF
[]        Legislação
[]NUM     Instrução Normativa RFB nº 2.006/2021        ← citations
```

Lessons: hierarchy here *is* style-driven (`Heading1`/`Heading2`), it has **no** statutory front matter at all (no ementa, no enacting formula, no signature), and lists are the dominant structure. This is the polar opposite of the parecer, which validates the need for a **profile system** rather than one hard-coded pipeline.

Together the two samples bracket the design space: **style-driven vs. text-driven hierarchy**, and **statute-like vs. bare** front matter. The parser must handle both without a corpus-specific hack.

---

## 4. Schema Investigation (evidence)

### 4.1 The two content models

`lexml-base.xsd:499-515`:

```xml
<xsd:complexType name="HierarchicalStructure">     <!-- statutes -->
  <xsd:sequence>
    <xsd:element ref="ParteInicial" minOccurs="0"/>
    <xsd:element ref="Articulacao"/>                <!-- REQUIRED -->
    <xsd:element ref="ParteFinal"  minOccurs="0"/>
    <xsd:element ref="Anexos"      minOccurs="0"/>
  </xsd:sequence>
</xsd:complexType>

<xsd:complexType name="OpenStructure">             <!-- non-articulated -->
  <xsd:sequence>
    <xsd:element ref="PartePrincipal" minOccurs="0"/>
    <xsd:element ref="Anexos"         minOccurs="0"/>
  </xsd:sequence>
</xsd:complexType>
```

Document types (`lexml-base.xsd:471-545`) — the root `<LexML>` takes `Metadado` then one of:

| Element | Type | Use |
|---|---|---|
| `Norma` | `HierarchicalStructure` | enacted statutes |
| `ProjetoNorma` | `Norma` + `Justificacao` + `AutorProjeto` | bills |
| `Jurisprudencia` | `Sumula \| Acordao` | case law |
| **`DocumentoGenerico`** | **`OpenStructure`** | **← our target** |
| `Anexo` | `DocumentoArticulado \| DocumentoGenerico` | annexes |

`OpenStructure` is *also* reused for `Justificacao`, and for the `Acordao` sub-parts (`EmentaTexto`, `RelatorioTexto`, `VotoTexto`, `ExtratoAtaTexto`) — evidence that LexML's own designers treat it as the general-purpose free-prose container.

### 4.2 What `PartePrincipal` actually admits

`lexml-base.xsd:705-716`:

```xml
<xsd:element name="PartePrincipal">
  <xsd:complexType>
    <xsd:choice minOccurs="1" maxOccurs="unbounded">
      <xsd:element ref="AgrupamentoHierarquico"/>   <!-- requires articulated content -->
      <xsd:group   ref="containerElements"/>        <!-- div | Agrupamento -->
      <xsd:group   ref="blockElements"/>            <!-- p | ul | ol | table | Bloco | ConteudoExterno -->
    </xsd:choice>
    <xsd:attributeGroup ref="coreopt"/>
  </xsd:complexType>
</xsd:element>
```

And the generic extension elements (`lexml-base.xsd:834-887`), each carrying a **required `@nome`** — LexML's *Generic Document + Role Attribute* pattern, explicitly documented in the schema as the escape hatch "para atender necessidades específicas ou situações não previstas no modelo original":

| Element | Base type | Content | Recursive? |
|---|---|---|---|
| `AgrupamentoHierarquico` | `hierarchy` | `Rotulo?`, `NomeAgrupador?`, `LXhierCompleto+` | yes, but statutory-only |
| `Agrupamento` | `blocksreq` | `blockElements+` | **no** |
| `Bloco` | `inline` (mixed) | inline | no |
| `EmLinha` | `inline` (mixed) | inline | no |
| `Marcador` | `markerreq` | empty | n/a |
| `ConteudoExterno` | `anyOther` | `##other` namespace | escape hatch |

The flatness is now explicit: `blocksreq → blockElements`, and `blockElements` contains no container.

### 4.3 Validation matrix (empirically verified)

Run with `lxml` 5.4.0 against both compiled schemas. `rig` = `lexml-br-rigido.xsd`, `flex` = `lexml09-flexivel.xsd`. Harness in §11.

| # | Candidate encoding | rig | flex | Consequence |
|---|---|---|---|---|
| A | `DocumentoGenerico/PartePrincipal/p` | PASS | PASS | baseline works |
| B | `PartePrincipal/Agrupamento[@nome="capitulo"]/p` | PASS | PASS | named grouping works |
| C | `Agrupamento/Agrupamento` (nested) | **FAIL** | **FAIL** | no recursion |
| D | `div/div` (nested) | **FAIL** | **FAIL** | no recursion |
| E | `AgrupamentoHierarquico/p` | **FAIL** | **FAIL** | cannot hold prose |
| F | `AgrupamentoHierarquico` with no `Artigo` descendant | **FAIL** | **FAIL** | needs articulation |
| G | `PartePrincipal/ol/li` (+ nested `li/ol`) | PASS | PASS | **lists nest natively** |
| H | `Norma` without `Articulacao` | **FAIL** | **FAIL** | statutes need articles |
| I | sibling `Agrupamento` + `Agrupamento` (flat) | PASS | PASS | **→ Profile `generico`** |
| J | `Agrupamento/Bloco[@nome]` | PASS | PASS | heading/label carrier |
| K | `PartePrincipal/div/p` (single level) | PASS | PASS | one wrapper level only |
| L | `table/tr/td` with **text** children | PASS | PASS | tables OK… |
| M | `table/tr/td/p` | **FAIL** | **FAIL** | …but `td` takes no `<p>` |
| N | `Capitulo/Artigo(Rotulo,Caput)` in `Articulacao` | PASS | PASS | native statutory nesting |
| O | `AgrupamentoHierarquico[@nome]/Artigo(Rotulo,Caput)` | PASS | PASS | **→ Profile `articulado-sintetico`** |
| P | full `ParteInicial`+`Articulacao`+`ParteFinal` | PASS | PASS | front/back matter model OK |
| Q | `DocumentoGenerico` + `Anexos/ReferenciaAnexo` | PASS | PASS | annexes by URN reference |
| R | `Artigo/DispositivoGenerico` | **FAIL** | **FAIL** | ordering-constrained |

Notable incidental findings, each of which would have cost implementation time to discover late:

- **(M)** `<td>` accepts inline content, **not** `<p>`. Table cell rendering must emit bare text/inline, unlike every other container. The reference Scala parser has a whole `DESIGN_TABLE_PARSING.md` devoted to table handling; this constraint is the reason.
- **(G)** `<ol>`/`<ul>` **do** nest natively via `li → ol|ul`. Lists are therefore the *one* place where the non-articulated model preserves real depth. This is exploitable: deep list structures need no flattening at all.
- **(N/O)** Element order inside `Artigo` is strict: `Rotulo` precedes `Caput`, and `Caput` carries its own `Rotulo`. Getting this wrong is the first error the validator reports (cases S3/S4 in the harness failed on ordering before I corrected them).
- **(F)** confirms `AgrupamentoHierarquico` is unusable as a pure prose grouper — it is not the non-articulated hierarchy element it superficially appears to be.

### 4.4 The `id` grammar as a hierarchy channel

`lexml09-flexivel.xsd` defines `idAgregador` patterns that admit an `agh` (AgrupamentoHierarquico) prefix at *every* aggregator level, composed with `_`:

```
(prt|agh)\d+
((prt|agh)\d+_)?(liv|agh)\d+
(((prt|agh)\d+_)?(liv|agh)\d+_)?(tit|agh)\d+
… (cap|agh) … (sec|agh) … (sub|agh)
```

This is the decisive enabler for Profile `generico`: because `id`s are *defined* to be path-composed, encoding depth in the `id` (`pp1_agr1_agr2_agr1`) is idiomatic LexML rather than a private convention. Hierarchy survives flattening in a form consumers can parse deterministically. Note that `Agrupamento`'s `id` is typed `xsd:ID` (via `corereq`), not constrained to `idAgregador`, so our `pp…_agr…` scheme is free-form and must be uniqueness-checked by us — hence the dedicated `id`-uniqueness test in Cycle 6.

### 4.5 Metadata model

`MetaSection` (`lexml-base.xsd:1041`): `Identificacao` (required, `@URN`), then optional `CicloDeVida`, `EventosGerados`, `Notas`, `Recursos`, `MetadadoProprietario`. `CicloDeVida/Evento` carries `Publicacao`, `EntradaEmVigor`, `Retificacao`, etc. with a required `@data`.

The URN follows the LexML naming standard (Parte 2). For a non-statutory federal opinion:

```
urn:lex:br:advocacia.geral.uniao:parecer:2018-12-28;93
     └─┬─┘ └┬┘ └────────┬────────┘ └──┬──┘ └───┬────┘└┬┘
      lex  país     autoridade        tipo    data   número
```

`MetadadoProprietario` is the sanctioned place for information with no LexML slot — for the parecer, that is `NUP`, `INTERESSADOS`, `ASSUNTO`, `Cod. Ement.`. Using it avoids either discarding those fields or abusing a semantic element.

### 4.6 Reference parser (Scala) — what transfers

`../lexml-parser-projeto-lei`, ~9.2k lines of Scala. Directly relevant precedents:

- **`output/LexmlRenderer.scala:486-497`** already renders an `OpenStructure`: `renderAnexoGenerico` emits `<DocumentoGenerico><PartePrincipal id="…_pp">`. It even documents the exact dilemma we face — `isArticulatedAnexo` (l. 415-427) refuses the articulated route when top-level tables/OLs exist because "`Articulacao` only accepts `hierElements`, and `Preambulo` only accepts `<p>`". Our two-profile design generalises that decision to whole documents.
- **`profile/DocumentProfile.scala`** (750 lines): regex-driven profiles (`regexLocalData`, `regexJustificativa`, `regexEpigrafe`, `epigrafeObrigatoria`) plus `TipoNormaProfile`/`AutoridadeProfile` supplying `urnFragTipoNorma`/`urnFragAutoridade`. This is the pattern to port for `parecer`, `nota-tecnica`, `instrucao-normativa`, `servico`, …
- **`rotulo/rotuloParser.scala`**: parser-combinator label recognition (`parte`, `livro`, `titulo`, `capitulo`, `secao`, `subsecao`), tolerant of ordinals, roman numerals, `único`, and `-A` suffixes. Port as a Python regex/PEG label recogniser, **extended** with the non-statutory forms the samples show (`1.`, `1.1`, `c. 1)`, `I -`).
- **`block/Block.scala`** (962 lines): the `Block` model and a 14-step normalise → recognise → organise → number → path pipeline. The staged shape is worth copying even though the recognisers differ.
- **`docx/DOCXReader.scala`**: reads DOCX via StAX into styled segments, normalises ` `/whitespace, tracks bold/italic/sup/sub. In Python, `python-docx` (already installed) plus direct `numbering.xml` access covers this.
- **`Alteracao` recognition by quotation marks**: the mechanism the reference parser uses to detect amendment text is exactly what we need *inverted* — to detect quoted statute in a parecer and refuse to articulate it (§3.1 hazard 3).

Not to be ported: Pekko actors (the linker's parallelism is unnecessary at our scale), AbiWord conversion, StringTemplate epigraph templating.

---

## 5. Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│ INGESTION            docx / html / txt  →  StyledDoc              │
│  · python-docx + numbering.xml + styles.xml                       │
│  · paragraph = text + style + list-level + runs(b/i/sup/sub)      │
│  · NFC normalisation, whitespace collapse                         │
├───────────────────────────────────────────────────────────────────┤
│ SEGMENTATION         StyledDoc → DocumentSections                 │
│  · profile regexes split front matter / body / back matter        │
│  · epigrafe, ementa, preambulo, fórmula de promulgação,           │
│    local-data-fecho, assinaturas, anexos, named fields            │
├───────────────────────────────────────────────────────────────────┤
│ HIERARCHY INFERENCE  body → HierarchyTree      ★ core novelty     │
│  · evidence fusion: style · numbering · text label · typography   │
│  · quotation guard (do not articulate quoted statute)             │
│  · level unification → single consistent tree                     │
├───────────────────────────────────────────────────────────────────┤
│ MODEL                DocumentModel (profile-independent, typed)   │
├───────────────────────────────────────────────────────────────────┤
│ RENDERING            two selectable emitters                      │
│  · generico             → DocumentoGenerico (flat + id path)      │
│  · articulado-sintetico → Norma (AgrupamentoHierarquico/Artigo)   │
├───────────────────────────────────────────────────────────────────┤
│ VALIDATION           lxml XMLSchema (rigido + flexivel) + rules   │
└───────────────────────────────────────────────────────────────────┘
```

Proposed layout:

```
src/lexml_nonstat/
  ingest/       docx_reader.py  html_reader.py  txt_reader.py  styled.py
  profile/      base.py  parecer.py  nota_tecnica.py  instrucao_normativa.py
                servico.py  generic.py  registry.py
  segment/      frontmatter.py  backmatter.py  fields.py  sections.py
  hierarchy/    evidence.py  labels.py  quotation.py  tree.py  unify.py
  model/        document.py  nodes.py  metadata.py  urn.py
  render/       generico.py  articulado.py  common.py  ids.py
  validate/     schema.py  rules.py
  cli.py
tests/
  unit/  golden/  fixtures/  regression/  conftest.py
```

### 5.1 Internal model (rendering-agnostic — the key to dual output)

```python
@dataclass
class Inline:            # text run with formatting
    text: str; bold: bool = False; italic: bool = False
    sup: bool = False; sub: bool = False; href: str | None = None

@dataclass
class Para:
    inlines: list[Inline]
    kind: Literal["prose","quote","citation","field"] = "prose"

@dataclass
class ListNode:          # nests natively in LexML (finding G)
    ordered: bool
    items: list["ListItem"]

@dataclass
class ListItem:
    inlines: list[Inline]
    children: list["ListNode | Para"] = field(default_factory=list)

@dataclass
class Section:           # the recursive hierarchy LexML lacks
    label: str | None            # "1.1", "CAPÍTULO II", "c. 1)"
    heading: str | None          # "REGIME DE PREVIDÊNCIA COMPLEMENTAR"
    level: int                   # normalised depth, 1-based
    kind: str                    # capitulo|secao|subsecao|tema|item|...
    body: list[Para | ListNode | Table]
    children: list["Section"]
    evidence: "Evidence"         # provenance, for debugging + confidence

@dataclass
class DocumentModel:
    metadata: Metadata           # URN, authority, dates, numbering, type
    front: FrontMatter           # epigrafe, ementa, preambulo, formula, fields
    body: list[Section | Para | ListNode | Table]
    back: BackMatter             # local/data, assinaturas, anexos
    profile: str
```

`Section.children` is where the real tree lives. Both emitters consume the same model; flattening is a *rendering* concern, never a parsing loss. This separation is what makes the schema's flatness survivable.

### 5.2 Profile `generico` — flattening scheme

```xml
<DocumentoGenerico>
  <PartePrincipal id="pp1">
    <Agrupamento id="pp1_agr1" nome="secao">
      <Bloco nome="rotulo">1</Bloco>
      <Bloco nome="nomeAgrupador">REGIME DE PREVIDÊNCIA COMPLEMENTAR</Bloco>
      <Bloco nome="nivel">1</Bloco>
      <p>A partir da Emenda Constitucional nº 20, de 1998, …</p>
    </Agrupamento>
    <Agrupamento id="pp1_agr1_agr1" nome="subsecao">
      <Bloco nome="rotulo">c. 1)</Bloco>
      <Bloco nome="nomeAgrupador">contribuições previdenciárias …</Bloco>
      <Bloco nome="nivel">2</Bloco>
      <ol><li>contribuição social paga sobre a gratificação natalina</li>
          <li>contribuições ao regime de previdência do militar</li></ol>
    </Agrupamento>
  </PartePrincipal>
</DocumentoGenerico>
```

Depth is recoverable three ways, redundantly: the `id` path (`pp1_agr1_agr1`), `<Bloco nome="nivel">`, and `@nome` semantics. Validated as cases I + J + G. Round-trip reconstruction of the tree from the XML is a Cycle 6 test requirement — that test is what turns "flattening" from a lossy compromise into a proven-reversible transform.

### 5.3 Profile `articulado-sintetico` — nested alternative

```xml
<Norma>
  <ParteInicial>
    <Epigrafe id="epi1">PARECER n. 00093/2018/DECOR/CGU/AGU</Epigrafe>
    <Ementa   id="eme1">ADMINISTRATIVO. SERVIDOR PÚBLICO. …</Ementa>
  </ParteInicial>
  <Articulacao>
    <AgrupamentoHierarquico id="agh1" nome="secao">
      <Rotulo>1</Rotulo>
      <NomeAgrupador>REGIME DE PREVIDÊNCIA COMPLEMENTAR</NomeAgrupador>
      <AgrupamentoHierarquico id="agh1_agh1" nome="subsecao">
        <Rotulo>c. 1)</Rotulo>
        <NomeAgrupador>contribuições previdenciárias …</NomeAgrupador>
        <Artigo id="art1">
          <Rotulo>1</Rotulo>
          <Caput id="art1_cpt"><Rotulo>1</Rotulo><p>texto do parágrafo…</p></Caput>
        </Artigo>
      </AgrupamentoHierarquico>
    </AgrupamentoHierarquico>
  </Articulacao>
</Norma>
```

Validated as cases O + N + P. **Documented caveat:** every prose block becomes a synthetic `Artigo`, asserting articulation the source lacks. Emit `<Bloco nome="sintetico">`/`MetadadoProprietario` provenance so downstream consumers can tell synthetic articles from real ones. Not the default, for that reason.

---

## 6. Hierarchy Inference — the core algorithm

This is where the real engineering risk sits, because the two samples disagree about how hierarchy is signalled. The design is **evidence fusion**: collect independent signals per paragraph, score them, then unify into one consistent tree.

### 6.1 Evidence sources

| Source | Signal | Reliability | Sample |
|---|---|---|---|
| Word style | `Heading1..9`, `Título N` | high when present | carnê-leão |
| Word numbering | `numPr` → `numId`/`ilvl` from `numbering.xml` | high for lists | both |
| Text label | `1.`, `1.1`, `1.1.1`, `I -`, `a)`, `c. 1)`, `CAPÍTULO II`, `Seção I` | medium — ambiguous | parecer |
| Typography | all-caps, bold, centred, short line, no terminal period | weak — corroborating | parecer |
| Statutory label | `Art. N`, `§ N`, `inciso`, `alínea` | high, **but** see quotation guard | parecer |

No single source suffices: the carnê-leão doc has styles and no numeric labels; the parecer has numeric labels and (mostly) no heading styles. Hence fusion rather than a priority chain.

### 6.2 Algorithm

```
1. For each paragraph, gather Evidence{style_level, list_level, label_kind,
   label_value, typography_score, in_quotation}.
2. Quotation guard: mark spans inside quotation marks (" " " '' ) or
   styled as block quotes. Statutory labels inside such spans are
   *content*, never structure.  ← prevents misreading quoted Art. 40
3. Candidate headings = paragraphs with (style_level) OR (label_kind in
   HEADING_KINDS) OR (typography_score ≥ threshold), and not in_quotation.
4. Level unification: build a per-document mapping from heterogeneous
   signals to a single 1..N depth, using
     (a) dotted-label arity     — "1.1"  → depth 2
     (b) style ordinal          — Heading2 → depth 2
     (c) first-seen ordering    — new label family opens next depth
   Reconcile conflicts by majority + document order monotonicity
   (a depth may increase by at most 1 between consecutive headings).
5. Attach non-heading paragraphs to the nearest open Section.
6. Lists: reconstruct from numbering ilvl into nested ListNode.
7. Emit HierarchyTree; record unresolved conflicts as warnings.
```

Step 4's monotonicity constraint is what keeps a stray bold line from opening a spurious depth-5 branch. Step 2 is non-negotiable for the parecer.

### 6.3 Confidence and fallback

Each `Section` keeps its `Evidence`. Overall confidence is reported; below a threshold the parser degrades gracefully to a **flat body of `<p>`** rather than inventing structure. "Handle any document" means *never crash and never fabricate* — a flat but correct rendering beats a confident wrong tree. Confidence must be a CLI-visible number so operators can triage a corpus.

---

## 7. Development Cycles

Each cycle is independently verifiable and leaves the repository green. Tests accumulate into the regression suite. Suggested cadence: one cycle per working session.

### Cycle 0 — Scaffolding and the schema harness (foundation)

Deliverables: package skeleton; `pyproject.toml` (`lxml`, `python-docx`, `pytest`, `pytest-cov`); vendored **offline** `xml.xsd` stub plus the `schemaLocation` rewrite needed to compile the schemas without network (see §11 — this was required to make validation work at all); `validate.schema` API compiling both schemas; CI-friendly `pytest` config.

Tests (`tests/unit/test_schema_harness.py`):
- both schemas compile offline
- known-good minimal `DocumentoGenerico` validates
- known-bad (nested `Agrupamento`) is rejected
- **the entire §4.3 matrix A–R is encoded as a parametrised test**

Exit: `pytest` green; the matrix is executable, so any future schema swap immediately shows which assumptions broke. This is the highest-leverage cycle — it turns the investigation into a permanent guard.

### Cycle 1 — DOCX ingestion → `StyledDoc`

Deliverables: `ingest/docx_reader.py` reading paragraphs, `pStyle`, `numPr` (`numId`/`ilvl`), runs with bold/italic/sup/sub, tables; `numbering.xml`/`styles.xml` resolution (incl. style inheritance via `basedOn`); NFC normalisation and whitespace collapse mirroring `DOCXReader.breakText`; a `--dump-styled` debug view.

Tests:
- golden `StyledDoc` JSON for both samples (`tests/golden/`)
- `Heading1`/`Heading2` correctly detected in carnê-leão
- list items carry `ilvl`; nested levels distinguished
- NFC: composed/decomposed accents unify
- non-breaking spaces and multiple spaces collapse
- run formatting preserved (bold/italic/sup/sub)
- tables extracted with row/cell shape

Exit: both samples ingest losslessly; golden files committed as regression baselines.

### Cycle 2 — Metadata, URN and profiles

Deliverables: `model/urn.py` (LexML URN builder/parser); `model/metadata.py`; `profile/base.py` + registry; `parecer` and `servico` profiles; authority/type/number/date extraction; `MetadadoProprietario` for unmapped fields (`NUP`, `INTERESSADOS`, `ASSUNTO`).

Tests:
- URN round-trip build→parse for federal/state/municipal authorities
- parecer: authority `advocacia.geral.uniao`, type `parecer`, number `93`, date `2018-12-28`
- date parsing: `28/12/2018`, `28 de dezembro de 2018`, ISO
- number normalisation: `00093/2018` → `93`, year `2018`
- profile auto-selection from content for both samples
- unmapped fields land in `MetadadoProprietario`, none silently dropped
- `<Metadado>` fragment schema-validates

Exit: correct URN + metadata for both samples.

### Cycle 3 — Front/back matter segmentation

Deliverables: `segment/` — epigraph, ementa, preamble, enacting formula (`fórmula de promulgação`), local/date closing, signatures, annex boundaries, named fields; regex sets per profile ported in spirit from `DocumentProfile.scala`; tolerance for *absent* front matter (carnê-leão).

Tests:
- parecer: epigraph = `PARECER n. 00093/2018/DECOR/CGU/AGU`; ementa captured from `EMENTA:`; authority block recognised
- carnê-leão: no ementa/preamble/signature → empty, **no** false positives
- `EMENTA:` with no space after colon still splits (observed in sample)
- signature block with `NomePessoa` + `Cargo`
- `LocalDataFecho` recognition
- absent-front-matter path yields a valid document
- rendered `ParteInicial`/`ParteFinal` fragments schema-validate

Exit: both samples segmented with zero false positives on the bare document.

### Cycle 4 — Hierarchy inference (the core)

Deliverables: `hierarchy/` — `labels.py` (label grammar incl. `1.`, `1.1`, `I -`, `a)`, `c. 1)`, `CAPÍTULO`, `Seção`, `Subseção`, ordinals, roman, `único`, `-A`); `quotation.py` (**quotation guard**); `evidence.py`; `unify.py` (level unification + monotonicity); `tree.py`; confidence scoring and flat fallback.

Tests (largest suite):
- label grammar: parametrised table of ~40 label forms → (kind, value, depth-arity), including negatives (`1.500/2014` in a citation is **not** a label; `Lei nº 12.618` is not a label)
- **quotation guard: quoted `Art. 40.` / `§ 1º` in the parecer do NOT become structure** (regression-critical)
- carnê-leão: `Heading1` → depth 1, `Heading2` → depth 2, correct child assignment
- parecer: `1 - REGIME…` → depth 1; `c. 1) …` nested beneath
- dotted labels `1` / `1.1` / `1.1.1` → depths 1/2/3
- monotonicity: depth never jumps by more than 1
- nested list reconstruction from `ilvl`
- mixed style + label evidence conflict resolves deterministically
- low confidence → flat fallback, no fabricated sections
- idempotence: inferring twice yields an identical tree

Exit: both samples produce a hierarchy tree matching a hand-authored expected tree (committed as golden).

### Cycle 5 — Emitter `generico` (default)

Deliverables: `render/generico.py`; `render/ids.py` (path-composed `id`s, uniqueness guaranteed); flattening with `<Bloco nome="rotulo"|"nomeAgrupador"|"nivel">`; list emission (nested `ol`/`ul`); table emission **with the `<td>`-takes-no-`<p>` constraint (finding M)**; `Anexos`/`ReferenciaAnexo`.

Tests:
- both samples render and **validate against `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd`**
- `id`s unique across the document (explicit check — `xsd:ID`, §4.4)
- `id` path encodes depth; **tree reconstructable from XML alone** (round-trip)
- nested lists survive as nested `ol`/`ul`
- tables emit inline cell content, not `<p>` (guards finding M)
- text-content conservation: every source paragraph's text appears exactly once in the output (no loss, no duplication)
- golden XML committed for both samples

Exit: schema-valid XML for both samples with proven round-trip and conservation.

### Cycle 6 — Emitter `articulado-sintetico` + round-trip

Deliverables: `render/articulado.py` mapping `Section`→`AgrupamentoHierarquico` and prose→synthetic `Artigo`/`Caput` with correct element ordering (finding N/O); synthetic-provenance markers; `ParteInicial`/`ParteFinal`; a `hierarchy_from_xml()` reader for round-trip testing of *both* profiles.

Tests:
- both samples validate in `articulado-sintetico` on both schemas
- element ordering `Rotulo` → `Caput`, `Caput` carries its own `Rotulo`
- nesting depth preserved exactly (no flattening)
- synthetic articles are marked and countable
- **round-trip: `model → generico → model'` and `model → articulado → model''` both preserve the tree shape and all text**
- cross-profile equivalence: both emitters carry identical text content

Exit: two validated emitters; round-trip proven for each.

### Cycle 7 — Generalisation, robustness, CLI

Deliverables: `cli.py` (`parse`, `dump-styled`, `dump-tree`, `validate`, `list-profiles` — mirroring `FECmdLine`'s shape); HTML and plain-text ingestion; `generic` catch-all profile; structured warnings; confidence reporting; `--profile`/`--emitter`/`--strict` flags.

Tests:
- CLI end-to-end on both samples, both emitters
- degenerate inputs: empty document, single paragraph, headings only, no headings, deeply nested lists, unlabelled prose — none crash, all emit valid XML
- malformed/corrupt DOCX → clean error, non-zero exit, no traceback
- HTML and TXT ingestion reach the same model shape
- `--strict` fails on validation error; default mode warns and continues
- confidence surfaced in output

Exit: "handles any document" demonstrated — valid output or a clean diagnostic for every fixture.

### Cycle 8 — Regression suite consolidation

Deliverables: `tests/regression/` promoting all goldens; `make regression`; coverage gate; a corpus-expansion guide (adding a document = adding a fixture + golden); documentation of `docs/` conventions.

Tests: full suite green; coverage ≥ 85% on `hierarchy/` and `render/`; every golden regenerable via a single documented command; a deliberate mutation is shown to fail the suite (proving the tests actually bite).

Exit: reproducible regression baseline for all later work.

### Cycle 9 (optional) — RAG-oriented outputs

Given this lives under `RAG_evaluation/`, likely next: hierarchy-aware chunking (chunk = `Section` with ancestor-label breadcrumb), stable chunk ids from LexML `id` paths, JSON/JSONL export, citation extraction (`Lei nº 12.618, de 2012` → URN, reusing the reference `linker`'s ideas). Tests: chunk boundary stability across re-parses, breadcrumb correctness, citation→URN accuracy.

---

## 8. Test Strategy

| Layer | Purpose | Location |
|---|---|---|
| Unit | label grammar, URN, evidence scoring, id generation | `tests/unit/` |
| Schema matrix | the §4.3 encodings stay true (A–R) | `tests/unit/test_schema_matrix.py` |
| Golden | byte-stable `StyledDoc` / tree / XML per sample | `tests/golden/` |
| Round-trip | XML → model preserves shape and text | `tests/regression/` |
| Conservation | no text lost or duplicated end-to-end | `tests/regression/` |
| Robustness | degenerate/corrupt inputs never crash | `tests/unit/test_robustness.py` |
| Validation | every emitted document validates on both schemas | all cycles |

Cross-cutting invariants asserted throughout — these are the properties that make the parser trustworthy on unseen documents:

1. **Validity** — output validates against `lexml-br-rigido.xsd` (and `lexml09-flexivel.xsd`).
2. **Conservation** — all source text present exactly once.
3. **Reversibility** — hierarchy reconstructable from output alone.
4. **Determinism / idempotence** — same input ⇒ byte-identical output.
5. **`id` uniqueness** — required by `xsd:ID`.
6. **No fabrication** — low confidence degrades to flat, never invents structure.

Golden files are regenerated by an explicit documented command, never silently, so a diff always represents a reviewed behaviour change.

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `OpenStructure` cannot nest (§2) | high — core requirement | dual profiles; depth in `id` path + `Bloco nome="nivel"`; round-trip test proves reversibility |
| Quoted statute misread as articulation | high — silent corruption of pareceres | dedicated quotation guard + regression test on the real parecer |
| Heterogeneous hierarchy signalling | medium | evidence fusion, not a priority chain; confidence + flat fallback |
| `<td>` rejects `<p>` (finding M) | medium — late-discovered validation failures | encoded in the schema matrix from Cycle 0 |
| Strict element ordering in `Artigo` | medium | matrix cases N/O; emitter asserts order |
| Synthetic articles mislead consumers | medium | not default; provenance markers; documented |
| Schema/version drift | medium | matrix A–R re-runs on any schema change |
| Over-fitting to two samples | medium | `generic` profile + degenerate-input suite; corpus-expansion guide |
| DOCX style inheritance (`basedOn`) missed | low | explicit resolution + test |

---

## 10. Key Decisions

1. **`DocumentoGenerico`/`OpenStructure` is the correct LexML home** for non-articulated documents — confirmed by the schema's own reuse of `OpenStructure` for `Justificacao` and `Acordao` parts.
2. **Default emitter is `generico`** — strictly valid, no semantic fiction, hierarchy preserved out-of-band and provably reversible.
3. **`articulado-sintetico` is offered, not default** — real nesting, but asserts articulation the source lacks.
4. **No schema modification.** Everything validates against the shipped schemas. (A future upstream proposal to make `Agrupamento` recursive would be the clean fix, and this document is the evidence base for it.)
5. **Internal model is rendering-agnostic** — parsing loss is never a rendering artefact.
6. **Statutory front matter is reused as-is** — `Epigrafe`, `Ementa`, `Preambulo`, `FormulaPromulgacao`, `LocalDataFecho`, `Assinatura` all apply to our corpus, matching the user's premise.
7. **Profiles over hard-coding**, following `DocumentProfile.scala`.
8. **Python with `lxml` + `python-docx`** (both already present) rather than porting Scala idioms.

---

## 11. Reproducing the Schema Investigation

Both schemas import `http://www.w3.org/2001/xml.xsd`. Compiling offline requires a local stub and a `schemaLocation` rewrite — without this, schema compilation fails and none of §4.3 is reproducible:

```python
from lxml import etree
import os

# 1. point the xml.xsd import at a local file
for f in [f for f in os.listdir('.') if f.endswith('.xsd')]:
    s = open(f, encoding='utf8').read()
    s = s.replace('schemaLocation="http://www.w3.org/2001/xml.xsd"',
                  'schemaLocation="xml.xsd"')
    open(f, 'w', encoding='utf8').write(s)

# 2. minimal stub for the xml: namespace attributes actually used
open('xml.xsd', 'w').write('''<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
  targetNamespace="http://www.w3.org/XML/1998/namespace"
  xmlns:xml="http://www.w3.org/XML/1998/namespace">
  <xs:attribute name="lang"  type="xs:string"/>
  <xs:attribute name="space" type="xs:string"/>
  <xs:attribute name="base"  type="xs:anyURI"/>
  <xs:attribute name="id"    type="xs:ID"/>
</xs:schema>''')

# 3. compile and validate a candidate
schema = etree.XMLSchema(etree.parse('lexml-br-rigido.xsd'))
NS = 'http://www.lexml.gov.br/1.0'
doc = f'''<LexML xmlns="{NS}">
  <Metadado><Identificacao URN="urn:lex:br:federal:parecer:2018-12-28;93"/></Metadado>
  <DocumentoGenerico><PartePrincipal id="pp1"><p>Texto</p></PartePrincipal></DocumentoGenerico>
</LexML>'''
x = etree.fromstring(doc.encode())
print(schema.validate(x), schema.error_log)
```

Sample structure was dumped by walking `word/document.xml` and printing, per paragraph, `[pStyle]`, presence of `w:numPr`, and concatenated `w:t` text (§3). Both steps are to be committed as Cycle 0 test utilities so the investigation stays live rather than becoming stale prose.

---

## 12. Open Questions for the User

1. **Emitter preference** — is `generico` (valid, flat, reversible) the right default for your RAG pipeline, or do you want nested `articulado-sintetico` XML despite the synthetic articles?
2. **Corpus breadth** — beyond *parecer* and *serviço*, which document types should get first-class profiles (nota técnica, instrução normativa, ofício, portaria, acórdão)?
3. **Schema target** — standardise on `lexml-br-rigido.xsd`, or must output also satisfy `lexml09-flexivel.xsd`? (The plan currently validates against both.)
4. **RAG integration** — should Cycle 9 (hierarchy-aware chunking, citation→URN) be in scope now, since this sits under `RAG_evaluation/`?
5. **Upstream** — is proposing a recursive `Agrupamento` to the LexML community of interest? §4.3 is ready-made evidence.
