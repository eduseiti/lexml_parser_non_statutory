# Design Review — Hierarchical Segmentation, Statutory Detection, LM Support, Schema Targets, and the Recursive `Agrupamento` Proposal

- **Date:** 2026-08-01
- **Status:** Second-round design analysis; supersedes open questions §12 of `20260801_004745_…`
- **Predecessor:** `docs/20260801_004745_lexml_non_statutory_parser_investigation_and_development_plan.md`
- **New evidence:** 13 additional samples in `samples/`; `scripts/GeraCSVporArtigoPorAgrupador.xsl`
- **Tooling verified this round:** `saxonche` (XSLT 3.0), `lxml` 5.4.0, `python-docx` 1.2.0

---

## 0. Originating Prompt (verbatim, for reproducibility)

> Thanks for the detailed plan. Exploring the open points, I have the following comments:
>
> 1. I believe the `generico` is indeed the best default for my needs. However, I need to clarify the following: from the proposed `generico` LexML would I be able to hierarchically segment the document, using for instance a .xsl like @scripts/GeraCSVporArtigoPorAgrupador.xsl or any other progamatically way?
>
> 2. I added additional non-statutory samples in "samples" folder for your analysis. Would it be possible to add some sort of document validation stage to verify if the document could be parsed as a statutory one? It seems the final structure is not fixed for some documents, and having a valid statutory hierarchy whenever possible might be better for the downstream tasks.
>
> 3. Regarding the input document analysis, wouldn't the final solution need a Language Model support? I'm thinking about the possibility of better identifying hierarchical structures in non-statutory documents, without depending on clear Word formatting (headings, numbered/bulleted lists). If you believe that might be useful, investigate if open-weights Small Language Models ― something that I could execute in my 64 GB RAM, old GTX-980Ti GPU ― would suffice for a robust analisys of pt-BR documents, or explore the integration with budget frontier model API options like the ones provided by DeepSeek, Qwen or Moonshot.
>
> 4. Keeping the output valid against both the `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd` seems better, don't? Let me know the pros and cons about that.
>
> 5. Don't bother adding the RAG integration (cycle 9) now, as the segmentation is still being discussed.
>
> 6. If you can further discuss the recursive `Agrupamento` proposal that would be great, as I really can reach the LexML community for extensions.
>
> As usual, capture all that discussion and analysis in a new .md document inside `docs` folder.

**Clarification received mid-analysis** (verbatim):

> The .xsl was just an example. The final produced LexML does necessarily need to be parsed by that exactly .xsl. But I must be able to create a hierachical segmentation of the identified internal hierarchy of a non-statutory document.

This narrows Q1 usefully: the requirement is *programmatic recoverability of the hierarchy*, not compatibility with that specific stylesheet.

---

## 1. Executive Summary of This Round

Four substantive findings, all empirically established rather than reasoned:

1. **Q1 — Yes, segmentation works, and I proved it.** I wrote an XSLT 3.0 stylesheet against a `generico` document and ran it through Saxon. It produced correct per-section CSV rows with hierarchical breadcrumbs, recovering ancestry from the `id` path. Two bugs surfaced in the process that became design rules (§2.3): **intermediate levels must always be materialised**, and **nested-list text must be de-duplicated**. The existing `GeraCSVporArtigoPorAgrupador.xsl` will *not* work as-is on `generico` output — it selects `//Artigo`, `//Capitulo`, `//Secao`, etc., none of which exist there. A `generico`-specific stylesheet is required, and §2.4 supplies a working one.

2. **Q2 — Yes, and the new samples show it is essential.** Of 15 samples, only **2 are genuinely statutory** (`port_mf_277`, and arguably `ad_srf_3`/`ad_pgfn_13` at inciso level). Critically, my originally-proposed quotation guard **fails on the real corpus**: the AGU parecer scores 21 `Art. N` matches, all of them quotations, and none is caught by leading-quote detection because the quotes are internal. The discriminator that *does* work is **paragraph indentation** — verified: all 21 quoted articles sit at `ind≈2880–2930` twips while the Portaria's genuine articles sit at `ind=0`. This corrects a real defect in the previous plan.

3. **Q3 — Yes, LM support is genuinely needed, but as a *referee*, not a parser.** After the indentation fix, exactly one hard residual case remains (`par_cosit_26`, where quoted articles are inline-quoted with no indent). Deterministic rules get most of the way; the residue is semantic. My recommendation: **do not use a local SLM on the GTX 980 Ti** — 6 GB Maxwell VRAM is the binding constraint and rules out the models that would actually be good enough at pt-BR legal text. Use a **budget frontier API** for a narrow, cacheable classification role, with a local fallback. Cost analysis in §4.
    - Note: this container reports `Failed to initialize NVML` and `torch.cuda.is_available() == False`, so the 980 Ti is not visible here. 62 GB RAM confirmed. The GPU analysis below is from published specs, not measured on your machine.

4. **Q4 — Dual-schema validation is right, and it is nearly free.** Every encoding I tested behaved *identically* on both schemas (18/18 cases in the previous round, all cases this round). `lexml09-flexivel.xsd` only relaxes `id` patterns and `Dispositivo` content — it never *adds* permitted structure for our elements. So dual validation costs one extra `validate()` call and buys portability. Pros/cons in §5.

5. **Q6 — The recursive `Agrupamento` proposal is well-founded and small.** A one-line-in-spirit schema change (§6) removes the entire flattening workaround. I have drafted the change, verified the *current* schema rejects the target document, and verified a patched schema accepts it — so the proposal ships with executable evidence.

6. **Q5 — RAG cycle dropped.** Cycle 9 is removed from the plan; segmentation-adjacent work stays only where it serves verification.

---

## 2. Q1 — Hierarchical Segmentation from `generico` Output

### 2.1 Why the existing stylesheet cannot be reused

`scripts/GeraCSVporArtigoPorAgrupador.xsl` is built entirely around statutory element *names*:

```xpath
//Artigo/Caput[not(ancestor::Alteracao)]
//Parte | //Livro | //Titulo | //Subtitulo | //Capitulo | //Secao | //Subsecao
//Inciso | //Alinea | //Item
```

A `generico` document contains none of these — it contains `Agrupamento`, `Bloco`, `p`, `ol`. Furthermore its `calculaPos` template computes positions via `preceding::`/`ancestor::`/`descendant::` axes over statutory elements, and its breadcrumb logic walks `ancestor::*/NomeAgrupador`. In `generico`, **ancestry is not XML nesting** (the schema forbids it, §4.3 case C of the predecessor doc) — it is encoded in the `id` path. So both the selection and the ancestry traversal must change.

This is not a defect of the plan; it is the direct, expected consequence of the schema's flatness. It does mean any existing statutory tooling needs a parallel `generico` variant.

### 2.2 Proof that segmentation works

I built a `generico` document mirroring the real structure of `pn_cst_38_19801031.docx` (sections `2.`, `2.1`, `2.3.1`) and a segmentation stylesheet, then ran it under Saxon (XSLT 3.0). Verbatim output:

```csv
Tipo,Nivel,Rotulo,Breadcrumb,Texto,urn
secao,1,"2.","DAS SOCIEDADES COOPERATIVAS","Texto introdutorio da secao 2.",urn:…;38!pp1_agr1
subsecao,2,"2.1","DAS SOCIEDADES COOPERATIVAS | Empresas de servicos","Em linhas gerais, as cooperativas sao definidas como empresas de servicos.",urn:…;38!pp1_agr1_agr1
subsecao,3,"2.3.1","DAS SOCIEDADES COOPERATIVAS | Atos Cooperativos","A primeira delas abrange os negocios juridicos internos. Aquisicao de produtos Fornecimento de benssubitem subitem",urn:…;38!pp1_agr1_agr2_agr1
```

Hierarchical segmentation from `generico` is therefore **confirmed working**: level, label, breadcrumb, full text, and a stable citable URN-with-fragment per segment.

### 2.3 Two bugs the experiment exposed → two binding design rules

Running the transform, rather than merely designing it, surfaced two real problems. Both become normative requirements.

**Rule A — intermediate levels must always be materialised.** The `2.3.1` row's breadcrumb reads `DAS SOCIEDADES COOPERATIVAS | Atos Cooperativos`, silently **missing `2.3`**. Cause: I emitted `id="pp1_agr1_agr2_agr1"` without ever emitting a `pp1_agr1_agr2` element, so the ancestor lookup found nothing to fill that slot. In the real `pn_cst_38` document, `2.3 - Operações das Sociedades Cooperativas` *is* a real heading, but any document that jumps a level (e.g. `2.` directly to `2.3.1`) would produce a broken breadcrumb.

> **Requirement:** the emitter must materialise a placeholder `Agrupamento` for every intermediate `id` path segment, even when the source document has no corresponding heading. Test: for every `Agrupamento`, each proper prefix of its `id` path exists as an `Agrupamento`. This is a cheap invariant that makes breadcrumbs total.

**Rule B — nested list text duplicates.** The `2.3.1` text ends `Fornecimento de benssubitem subitem` — "subitem" appears twice. Cause: `string-join(descendant::p|descendant::li, ' ')` visits both the outer `li` (whose string value already includes its nested `ol`) and the inner `li`. Also note `benssubitem` has no separating space, since the outer `li`'s string value concatenates its own text with the nested list's.

> **Requirement:** text extraction must select only leaf text nodes, or exclude `li` that contain nested lists (`li[not(ol|ul)]`), and must insert separators. Test: text conservation asserts each source token appears exactly once — this bug would have failed that test, which is precisely why the conservation invariant is in the plan.

Both bugs are the kind that survive code review and die in a round-trip test. They validate the plan's emphasis on conservation/reversibility invariants over inspection.

### 2.4 Corrected segmentation stylesheet

```xslt
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="3.0"
  xpath-default-namespace="http://www.lexml.gov.br/1.0">
 <xsl:output method="text"/>
 <xsl:template match="/">
  <xsl:text>Tipo,Nivel,Rotulo,Breadcrumb,Texto,urn&#10;</xsl:text>
  <xsl:variable name="urn" select="/LexML/Metadado/Identificacao/@URN"/>
  <xsl:for-each select="//Agrupamento">
   <xsl:variable name="myid" select="@id"/>
   <!-- ancestry from the id path, since XML nesting is unavailable -->
   <xsl:variable name="anc" select="//Agrupamento[starts-with($myid, concat(@id,'_'))]"/>
   <xsl:value-of select="@nome"/><xsl:text>,</xsl:text>
   <xsl:value-of select="Bloco[@nome='nivel']"/><xsl:text>,"</xsl:text>
   <xsl:value-of select="Bloco[@nome='rotulo']"/><xsl:text>","</xsl:text>
   <xsl:for-each select="$anc">
     <xsl:sort select="string-length(@id)"/>
     <xsl:value-of select="Bloco[@nome='nomeAgrupador']"/><xsl:text> | </xsl:text>
   </xsl:for-each>
   <xsl:value-of select="Bloco[@nome='nomeAgrupador']"/><xsl:text>","</xsl:text>
   <!-- Rule B: leaf-only, separated -->
   <xsl:value-of select="normalize-space(
        string-join((descendant::p, descendant::li[not(ol|ul)]), ' '))"/>
   <xsl:text>",</xsl:text>
   <xsl:value-of select="concat($urn,'!',@id)"/><xsl:text>&#10;</xsl:text>
  </xsl:for-each>
 </xsl:template>
</xsl:stylesheet>
```

Sorting ancestors by `string-length(@id)` works because `id` paths are prefix-nested, so longer id ⇒ deeper level.

### 2.5 The recommended primary path: Python, not XSLT

XSLT proves recoverability, but for your pipeline a direct Python API is better: no Saxon dependency, easier testing, and it can emit whatever downstream shape you need.

```python
def segments(xml_path):
    """Yield hierarchical segments from a `generico` LexML document."""
    t = etree.parse(xml_path); NS = {'lx': 'http://www.lexml.gov.br/1.0'}
    urn = t.find('.//lx:Identificacao', NS).get('URN')
    by_id = {a.get('id'): a for a in t.iterfind('.//lx:Agrupamento', NS)}

    def bloco(a, nome):
        el = a.find(f'lx:Bloco[@nome="{nome}"]', NS)
        return el.text if el is not None else None

    for aid, a in by_id.items():
        parts = aid.split('_')
        ancestors = ['_'.join(parts[:i]) for i in range(1, len(parts))]
        yield {
            'urn':        f'{urn}!{aid}',
            'kind':       a.get('nome'),
            'level':      int(bloco(a, 'nivel') or 1),
            'label':      bloco(a, 'rotulo'),
            'heading':    bloco(a, 'nomeAgrupador'),
            'breadcrumb': [bloco(by_id[p], 'nomeAgrupador')
                           for p in ancestors if p in by_id],
            'text':       ' '.join(
                ''.join(n.itertext()).strip()
                for n in a.iterfind('lx:p', NS)),
        }
```

Because the internal model (§5.1 of the predecessor) is retained in-process, **the cleanest route of all is to segment directly from the model** and treat XML as an interchange format. The XML-based reader then exists mainly as the round-trip *test oracle* — which is exactly the invariant the plan already requires.

### 2.6 Consequence for the profile choice

Segmentation works from `generico`, so the `generico`-as-default decision stands. Worth stating plainly, though: if your downstream tooling is heavily invested in statutory XPath (`//Artigo`, `//Capitulo`, `ancestor::*/NomeAgrupador`), then for the *genuinely statutory* documents the statutory route is strictly better — which is precisely what Q2 asks for, and §3 delivers.

---

## 3. Q2 — A Statutory-Viability Detection Stage

Your intuition is right and the new corpus proves it. Emitting a real `<Norma>` when the document genuinely *is* articulated gives you native `Artigo`/`Capitulo` structure, compatibility with existing statutory tooling (including the original stylesheet), and no synthetic fictions.

### 3.1 Corpus survey — statutory signals across all 15 samples

Counts of paragraph-initial patterns, quotation-naive:

| Sample | paras | `Art. N` | `§ N` | inciso | alínea | dotted | naive verdict |
|---|---|---|---|---|---|---|---|
| `REsp_1306393` | 15 | 0 | 0 | 0 | 0 | 0 | NON-STAT |
| `ad_pgfn_13_20111220` | 7 | 0 | 0 | 2 | 0 | 0 | NON-STAT |
| `ad_pgfn_3_20080918` | 6 | 0 | 0 | 0 | 0 | 0 | NON-STAT |
| `ad_srf_22_19970430` | 5 | 0 | 0 | 0 | 0 | 0 | NON-STAT |
| `ad_srf_3_19990107` | 7 | 0 | 0 | 3 | 0 | 0 | NON-STAT |
| `adn_cosit_19_20001025` | 5 | 0 | 0 | 0 | 0 | 0 | NON-STAT |
| `adn_cst_10_19910417` | 8 | 0 | 0 | 0 | 0 | 3 | NON-STAT |
| `par_cosit_26_20000629` | 100 | **4** | 10 | 6 | 0 | 25 | STATUTORY ✗ |
| `parecer_93_2018_decor_cgu_agu` | 426 | **21** | 28 | 13 | 2 | 13 | STATUTORY ✗ |
| `pn_cst_38_19801031` | 81 | 0 | 0 | 5 | 4 | 28 | NON-STAT |
| `port_mf_277_20180607` | 138 | **2** | 0 | 0 | 0 | 0 | STATUTORY ✓ |
| `port_mf_454_19770825` | 21 | 0 | 0 | 0 | 2 | 13 | NON-STAT |
| `…CARNE_LEAO` | 93 | 0 | 0 | 0 | 0 | 0 | NON-STAT |
| `sumula_carf_42` | 4 | 0 | 0 | 0 | 0 | 0 | NON-STAT |
| `sumula_stj_125` | 359 | 0 | 0 | 0 | 0 | 3 | NON-STAT |

✗ = **false positive**. Two of three "statutory" verdicts are wrong: both the AGU parecer and `par_cosit_26` are *opinions that quote statutes extensively*. Articulating them would be a severe corruption — the parser would present the Constitution's `Art. 40` as if it were an article of the parecer.

### 3.2 The discriminator that works: indentation

The previous plan's quotation guard checked for leading quotation marks. **On the real corpus that fails**, because quoted statutes appear as indented block quotes *without* opening quotes on the article line itself:

```
prev: A pretensão da Consultoria Jurídica junto ao Ministério…      ind=0
ART   Art. 40. Os pareceres do Advogado-Geral da União…            ind=2908   ← quoted
```

Measuring `w:ind/@w:left` against each document's modal body indent:

| Sample | modal indent | articles at body indent | articles indented ≫ | verdict |
|---|---|---|---|---|
| `parecer_93_2018_decor_cgu_agu` | 0 | **1** | **20** | WEAK → non-statutory |
| `port_mf_277_20180607` | 0 | **2** | 0 | STATUTORY ✓ |
| `par_cosit_26_20000629` | 0 | **4** | 0 | STATUTORY ✗ (residual) |
| all others | 0 / 893 | 0 | 0 | NON-STAT ✓ |

Indentation collapses the parecer from 21 spurious articles to 1 — a decisive improvement, and a correction to the earlier plan. The single remaining `art` there is `Art. 4º - São atribuições do Advogado-Geral da União:` at `ind=240`, a shallow indent inside running text.

### 3.3 The residual hard case

`par_cosit_26_20000629` resists indentation entirely. Its quoted articles are introduced inline:

```
Lei nº 7.713, de 1988 - “Art. 1º- Os rendimentos e ganhos de capital percebidos…
Art. 2º- O imposto de renda das pessoas físicas será devido…      ind=0
Art. 16 - O custo de aquisição dos bens e direitos será o preço…  ind=0
Art. 52. ....................................................     ind=0
```

Three usable cues remain, all deterministic:
- **Citation antecedent** — a preceding paragraph naming an external norm (`Lei nº 7.713, de 1988 -`) followed by `“Art.`; the opening curly quote is present mid-line.
- **Ellipsis runs** — `Art. 52. .........` and `.............` lines are the classic *omissis* of quoted excerpts, never of an original enactment.
- **Numbering discontinuity** — real articulation runs `Art. 1º, 2º, 3º…` monotonically from 1; this document jumps `1º, 2º, 3º, 16, 52`, i.e. an excerpt.

Numbering monotonicity from 1 is probably the single strongest structural cue and is cheap to implement. Combined with the genre prior (a document epigraphed *Parecer* is non-articulated by nature — `par_cosit_26`'s first line is `Parecer Cosit nº 26, de 29 de junho de 2000`), the rules likely resolve it. This is nonetheless the case that justifies an LM referee (§4).

### 3.4 Genre priors from the corpus

The samples cluster into five clear genres, and genre is itself strong evidence:

| Genre | Samples | Articulated? | LexML type |
|---|---|---|---|
| Portaria / Resolução | `port_mf_277` | **often yes** (`Art. 1º`, `Art. 2º`) | `Norma` |
| Portaria (older, item-based) | `port_mf_454` | no — uses `1.`, `2.1`, `a)` | `DocumentoGenerico` |
| Ato Declaratório (Normativo) | `ad_*`, `adn_*` | no — single `DECLARA` + incisos | `DocumentoGenerico` |
| Parecer (Normativo) | `par_cosit_26`, `pn_cst_38`, `parecer_93` | **no** — quotes statutes | `DocumentoGenerico` |
| Súmula / Acórdão | `sumula_*`, `REsp_1306393` | no | `Jurisprudencia` or `DocumentoGenerico` |

Two notable observations:

- **`port_mf_454_19770825` is a Portaria that is *not* articulated** — it uses `1.`, `2.`, `2.1`, `a)`, `b)`, `RESOLVE:`. So genre alone cannot decide; it is a prior, not a rule. This is a good example of your remark that "the final structure is not fixed for some documents."
- **`sumula_stj_125` and `REsp_1306393` are jurisprudence**, and LexML has dedicated support: `<Jurisprudencia>` with `<Sumula>` (`Epigrafe` + `Ementa` + `Observacao`) and `<Acordao>` (`CabecalhoAcordao` + `EmentaTexto` + `AcordaoTexto` + `RelatorioTexto` + `VotoTexto` + `ExtratoAtaTexto`). `sumula_stj_125` maps *remarkably* well — it literally has `EMENTA`, `ACÓRDÃO`, `RELATÓRIO` as `Heading1`s, matching `Acordao`'s required children. `REsp_1306393` has `EMENTA` + `ACÓRDÃO` headings likewise. **This is a third emitter worth having**, and it was not in the original plan.

### 3.5 Proposed architecture: a routing stage

Insert a **classification/routing stage** between segmentation and rendering:

```
StyledDoc → Segmentation → ┌─ StatutoryViabilityAnalyzer ─┐
                           │  · genre prior (epigraph)     │
                           │  · article-label census       │
                           │  · indentation discrimination │
                           │  · numbering monotonicity     │
                           │  · omissis / citation cues    │
                           │  · [optional] LM referee      │
                           └───────────┬───────────────────┘
                                       ▼
                    ┌──────────────────┼──────────────────┐
              Norma (statutory)  DocumentoGenerico   Jurisprudencia
              full articulation   flat + id path      Sumula/Acordao
```

`StatutoryViability` returns a structured verdict, never a bare boolean:

```python
@dataclass
class StatutoryViability:
    route: Literal["norma", "generico", "jurisprudencia"]
    confidence: float
    articles_found: int
    articles_quoted: int          # excluded by indentation/citation cues
    numbering_monotonic: bool
    coverage: float               # fraction of body inside articulation
    blockers: list[str]           # e.g. "top-level table outside dispositivo"
    evidence: dict
```

**Two decision rules that keep this safe:**

1. **Coverage gate.** Route to `norma` only if articulation covers *most* of the body. `port_mf_277` illustrates the danger: it has 2 genuine articles but **138 paragraphs**, the bulk being `ANEXO ÚNICO` with 130+ `Súmula CARF nº N` entries. Articulating 2 articles and dumping 130 paragraphs into a preamble would be far worse than `generico`. The reference Scala parser hit exactly this wall — `isArticulatedAnexo` (`LexmlRenderer.scala:415-427`) refuses the articulated route when top-level tables/OLs exist, because `Articulacao` accepts only `hierElements` and `Preambulo` only `<p>`. So `port_mf_277` most likely routes to `norma` for `Art. 1º–2º` **with the annex as a separate `<Anexo>` document** (LexML supports precisely this: `Anexos`/`ReferenciaAnexo`, verified case Q), or to `generico` if that proves lossy.

2. **Validate-then-fallback.** Attempt the statutory render; if it fails schema validation or the conservation/coverage invariants, **fall back to `generico` automatically** and record why. This makes "prefer statutory when possible" safe by construction rather than by trusting the classifier. It is the same both-ways discipline as the round-trip tests.

### 3.6 Plan changes

- **New Cycle 4b — Statutory Viability Analyzer** (between hierarchy inference and emitters): label census, indentation discrimination, numbering monotonicity, omissis/citation cues, genre priors, coverage computation, structured verdict + blockers.
  Tests: expected route for all 15 samples (a labelled fixture table); parecer + `par_cosit_26` must **not** route to `norma`; `port_mf_277` handled without content loss; coverage gate rejects low-coverage articulation; verdicts are stable/deterministic.
- **New Cycle 6b — Jurisprudence emitter** for `Sumula`/`Acordao`, driven by `sumula_stj_125`, `sumula_carf_42`, `REsp_1306393`.
- **Cycle 5/6 gain the validate-then-fallback mechanism** plus its tests.
- **Cycle 4's quotation guard is redesigned** around indentation + citation antecedent + numbering monotonicity, replacing the leading-quote test that this round showed to be insufficient. Regression test: the 21 quoted articles in `parecer_93` never become structure.

---

## 4. Q3 — Language-Model Support

### 4.1 Where an LM genuinely helps (and where it does not)

The corpus shows deterministic rules handle most structure. Evidence: `pn_cst_38` uses clean dotted labels (`2.`, `2.1`, `2.3.1`) that a regex nails; `CARNE_LEAO` uses `Heading1/2` styles; `port_mf_454` uses `1.`, `2.1`, `a)`. An LM adds nothing to these and would add nondeterminism to cases that are currently exact.

The genuinely hard residue, all semantic:

| Task | Why rules struggle | LM value |
|---|---|---|
| Quoted-vs-own articulation (`par_cosit_26`) | needs "is this text *about* another norm?" | **high** |
| Heading vs. emphasised sentence | no style, no label, only rhetorical role | **high** |
| Section-kind naming (`capitulo` vs `tema`) | semantic labelling | medium |
| Genre classification | usually decidable from epigraph | low |
| Label parsing, list nesting, front matter | exact patterns | **none** |

So the right role is a **narrow referee on flagged decisions**, not a document parser. This keeps the system deterministic by default, testable, and cheap — and it means an LM outage degrades quality slightly instead of breaking the pipeline.

### 4.2 Local SLM on a GTX 980 Ti — my recommendation is *don't*

The binding constraint is not RAM (your 62 GB is ample) but the GPU:

| GTX 980 Ti property | Value | Consequence |
|---|---|---|
| VRAM | **6 GB** | caps to ~7B at 4-bit, with little context room |
| Architecture | Maxwell (CC 5.2, 2015) | **no bf16, no FlashAttention**, poor INT4/INT8 support |
| Support status | dropped by recent CUDA/PyTorch builds | vLLM/modern stacks effectively unavailable |

Practically: `llama.cpp` with CUDA works on Maxwell and is the realistic option, but you are limited to ~7–8B at Q4 with modest context. Legal pt-BR reasoning over long documents is precisely where small models are weakest, and the decisions we would delegate (quoted-vs-own articulation) require *exactly* the long-context discrimination they do poorly.

Candidates worth knowing about if you pursue this anyway — Qwen2.5-7B-Instruct (strong multilingual, best size/quality here), Gemma-2-9B (good pt-BR, tight at 6 GB even at Q4), Llama-3.1-8B, and the pt-BR tuned Sabiá/Bode family. CPU-only inference on 62 GB RAM is also viable for a *batch* pipeline at a few tokens/s — acceptable for offline corpus processing, not interactive.

Verified on this machine: `Failed to initialize NVML`, `torch.cuda.is_available() == False`, so I could not benchmark. Treat the above as spec-based.

### 4.3 Budget frontier APIs — the recommended route

Because the LM handles only flagged, short excerpts, volume is tiny and cost is negligible.

| Provider | Model | Strengths for this task |
|---|---|---|
| **DeepSeek** | `deepseek-chat` (V3) | very low cost, strong reasoning, **context caching** — ideal here |
| **Qwen** (Alibaba) | `qwen-plus` / `qwen-max` | excellent multilingual incl. pt-BR |
| **Moonshot** | `kimi-k2` | long context |

**Cost sizing.** A pessimistic case: 1,000 documents × 20 flagged decisions × ~1.5k tokens ≈ 30M input tokens. At budget-tier pricing (order $0.1–0.3/M input, less on cache hits) this is roughly **$3–10 for the whole corpus**. Even at 10× my estimate it is immaterial versus engineering time. Prices move; verify current rates before committing.

Because decisions are per-excerpt and idempotent, **cache aggressively on a hash of the excerpt** — reruns then cost nothing, and the regression suite stays deterministic.

### 4.4 Design: LM as an optional, cached, schema-constrained referee

```python
class StructureReferee(Protocol):
    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict: ...
    def is_heading(self, para: str, ctx: str) -> Verdict: ...
    def section_kind(self, label: str, heading: str) -> str: ...

class NullReferee:      # default — deterministic, no network
class CachedAPIReferee: # DeepSeek/Qwen/Moonshot, JSON-constrained, disk-cached
class LocalReferee:     # llama.cpp, optional
```

Non-negotiable constraints, so the LM never destabilises the parser:

1. **Off by default** (`--referee=none|api|local`). Rules alone must always produce valid output.
2. **Only on flagged decisions** — where deterministic confidence is below threshold. Never a whole-document pass.
3. **Structured output only** (JSON: `{verdict, confidence, rationale}`), never free-form XML generation.
4. **Disk-cached by excerpt hash** — reproducibility and near-zero repeat cost.
5. **Advisory** — the LM may not override a high-confidence deterministic verdict, only break ties.
6. **Recorded in `evidence`** — every LM-influenced decision is auditable.
7. **Regression tests run with `NullReferee`**, plus a small recorded-fixture suite for referee behaviour, so the suite never depends on a live API.

### 4.5 Plan change

- **New Cycle 7b — Structure Referee (optional).** `Referee` protocol; `NullReferee`; `CachedAPIReferee` (OpenAI-compatible, so one client serves DeepSeek/Qwen/Moonshot); disk cache; flagging integration; `--referee` flag.
  Tests: `NullReferee` ⇒ byte-identical to no-referee; cache hit avoids network (mock); malformed LM JSON is rejected safely; referee cannot flip a high-confidence rule verdict; `par_cosit_26` resolves correctly with a recorded fixture.
  **Sequencing:** build this only after Cycles 4/4b are measured. If rules already resolve the corpus, the referee stays off and this cycle is a thin, cheap option rather than a dependency.

---

## 5. Q4 — Validating Against Both Schemas

**Yes, keep both.** The cost is essentially zero and the benefit is real.

### 5.1 What actually differs

`lexml09-flexivel.xsd` `redefine`s `lexml-base.xsd` and changes only:
- `idArtigo` / `idAgregador` — relaxed `id` patterns
- `DispositivoType` — content model for dispositivos
- `AlteracaoType` — content model for amendments

`lexml-br-rigido.xsd` redefines the same types more strictly. Crucially, **neither touches `OpenStructure`, `PartePrincipal`, `Agrupamento`, `Bloco`, `div`, or the HTML block elements** — the entire `generico` surface. That is why all 18 encodings in the predecessor doc and every case this round behaved *identically* on both. The flexible schema is not "more permissive" for our structures; it is more permissive about *statutory ids and dispositivo content*.

### 5.2 Pros and cons

**Pros**
- **Portability.** Consumers vary in which schema they enforce; validating both means never being rejected downstream.
- **Free early warning.** Divergence between the two is a signal you have drifted into statutory-specific territory — useful when routing to `norma` (§3), where the two schemas *do* differ.
- **Negligible cost.** One extra `validate()` on an in-memory tree; both schemas compile once at startup.
- **Cheap proposal evidence.** For §6, showing a change works on both is strictly more persuasive.

**Cons**
- **Constrained to the intersection.** If the flexible schema ever permitted something useful the rigid one forbids, dual validation would block it. Verified as vacuous for `generico`; may bind for `norma` output, where relaxed `id` patterns could matter for odd article numbering (`Art. 1º-A`).
- **Two failure sources** to diagnose. Mitigated by reporting which schema failed.
- **Version skew** if the two are updated independently.

### 5.3 Recommendation

Validate both, **report per-schema**, and make strictness configurable:

```python
@dataclass
class ValidationReport:
    rigido:   SchemaResult      # pass/fail + errors
    flexivel: SchemaResult
    @property
    def ok(self): return self.rigido.ok and self.flexivel.ok
```

Default: both must pass (`--schema=both`). Provide `--schema=rigido|flexivel` for the statutory edge cases where relaxed ids are genuinely needed — with the divergence logged rather than silently tolerated.

---

## 6. Q6 — The Recursive `Agrupamento` Proposal

You said you can reach the LexML community, so this section is written to be forwarded largely as-is.

### 6.1 Problem statement

LexML offers two document content models (`lexml-base.xsd:499-515`): `HierarchicalStructure` (`<Norma>`), requiring `<Articulacao>` and bottoming out in `Artigo`; and `OpenStructure` (`<DocumentoGenerico>`), for non-articulated documents.

A large and important class of Brazilian legal documents is **non-articulated yet deeply hierarchical**: pareceres, pareceres normativos, notas técnicas, atos declaratórios normativos, older portarias, and service descriptions. Examples from this corpus:

- `pn_cst_38_19801031` (Parecer Normativo CST 38/1980): `2.` → `2.1` → `2.3` → `2.3.1` — four levels, no articles.
- `port_mf_454_19770825` (Portaria MF 454/1977): `1.`, `2.`, `2.1`, `a)`, `b)`, `3.1`, `7.1`.
- `parecer_93_2018_decor_cgu_agu`: numbered sections `1 -`, sub-items `c. 1)`.

`OpenStructure` **cannot represent these hierarchies**, because its container elements are non-recursive:

```xml
<xsd:complexType name="blocksreq">
  <xsd:sequence minOccurs="1" maxOccurs="unbounded">
    <xsd:group ref="blockElements"/>     <!-- p | ul | ol | table | Bloco | ConteudoExterno -->
  </xsd:sequence>
  <xsd:attributeGroup ref="corereq"/>
</xsd:complexType>

<xsd:element name="Agrupamento">        <!-- extends blocksreq, adds @nome -->
<xsd:element name="div" type="blocksreq"/>
```

`blockElements` contains **no container element**, so neither `Agrupamento` nor `div` can nest. Meanwhile `AgrupamentoHierarquico` (base `hierarchy`) *requires* `LXhierCompleto` children (`Parte|Livro|Titulo|Capitulo|Secao|Subsecao|Artigo`) — it is a statutory device that always terminates in `Artigo`, and it cannot hold prose.

Net effect: **LexML has no element that is simultaneously non-articulated and recursive.**

### 6.2 Empirical evidence (reproducible)

Validated with `lxml` 5.4.0 against both `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd`:

| Candidate | rigido | flexivel |
|---|---|---|
| `Agrupamento` inside `Agrupamento` | **FAIL** | **FAIL** |
| `div` inside `div` | **FAIL** | **FAIL** |
| `AgrupamentoHierarquico` containing `<p>` | **FAIL** | **FAIL** |
| `AgrupamentoHierarquico` with no articulated descendant | **FAIL** | **FAIL** |
| sibling `Agrupamento` + `Agrupamento` (flat) | PASS | PASS |

Error message for the nesting case:

```
Element '{http://www.lexml.gov.br/1.0}Agrupamento': This element is not expected.
Expected is one of ( p, ul, ol, table, Bloco, ConteudoExterno ).
```

### 6.3 Current workaround and its costs

Our parser flattens the hierarchy into sibling `<Agrupamento>` elements and preserves depth **out-of-band**: in a path-composed `@id` (`pp1_agr1_agr2`), in `@nome`, and in a `<Bloco nome="nivel">` marker. This validates today and segmentation is recoverable (§2, demonstrated with XSLT 3.0 + Saxon).

The costs are real:

1. **Hierarchy is not machine-readable via standard XML axes.** `ancestor::`/`descendant::` no longer reflect document structure; every consumer must re-implement id-path parsing. The community's own `GeraCSVporArtigoPorAgrupador.xsl` relies on `ancestor::*/NomeAgrupador` and cannot work on such documents.
2. **Convention replaces schema.** `@id` composition is enforced by our code, not by the schema. Two implementers will diverge.
3. **Containment is unenforceable.** Nothing prevents `pp1_agr5_agr1` from appearing without `pp1_agr5` (a bug we actually hit — §2.3, Rule A).
4. **The alternative is worse.** Mapping onto `AgrupamentoHierarquico`/`Artigo` requires synthesising fake `Artigo` elements, asserting articulation the source lacks — semantically false for a *parecer*.

### 6.4 Proposed change

Allow container elements to nest, by adding `containerElements` to the content of `blocksreq`:

```xml
<xsd:complexType name="blocksreq">
  <xsd:choice minOccurs="1" maxOccurs="unbounded">
    <xsd:group ref="blockElements"/>
    <xsd:group ref="containerElements"/>   <!-- ADDED: div | Agrupamento -->
  </xsd:choice>
  <xsd:attributeGroup ref="corereq"/>
</xsd:complexType>
```

Properties worth emphasising to the community:

- **Backward compatible.** Purely additive: every document valid today remains valid. `sequence`→`choice` is needed only to allow interleaving prose and subsections, which is the natural document order (`2.` intro text, then `2.1`).
- **Minimal.** One content model; no new elements, no new attributes, no changes to `Norma`, `Articulacao`, or any statutory type.
- **Consistent with existing design.** `Agrupamento` already carries the required `@nome` role attribute under LexML's documented *Generic Document + Role Attribute* pattern — explicitly "para atender necessidades específicas ou situações não previstas no modelo original". Recursive grouping is squarely such a situation.
- **Precedent.** Akoma Ntoso, the other major legal-XML standard, models exactly this with a recursive `<hcontainer>`. LexML's `Agrupamento` is its natural analogue and currently lacks the recursion.
- **Optional narrower variant.** If unrestricted nesting is controversial, restrict recursion to `Agrupamento` only (leaving `div` flat, as HTML-derived), or add a distinct `AgrupamentoAberto` element. The one-group change above is simpler and preferred.

With this change the target document becomes directly representable:

```xml
<DocumentoGenerico>
  <PartePrincipal id="pp1">
    <Agrupamento id="pp1_agr1" nome="secao">
      <Bloco nome="rotulo">2.</Bloco>
      <Bloco nome="nomeAgrupador">DAS SOCIEDADES COOPERATIVAS</Bloco>
      <p>Texto introdutório.</p>
      <Agrupamento id="pp1_agr1_agr1" nome="subsecao">
        <Bloco nome="rotulo">2.1</Bloco>
        <Bloco nome="nomeAgrupador">Empresas de serviços</Bloco>
        <p>Em linhas gerais, as cooperativas…</p>
      </Agrupamento>
    </Agrupamento>
  </PartePrincipal>
</DocumentoGenerico>
```

`ancestor::`/`descendant::` then work, `NomeAgrupador`-style breadcrumbs work, and existing stylesheet idioms carry over.

### 6.5 Secondary observations for the community

Two further points surfaced by this work, worth raising alongside:

- **`Rotulo`/`NomeAgrupador` are unavailable in the open model.** They are children of `hierarchy`, so a non-articulated section must smuggle its label and heading through `<Bloco nome="rotulo">` / `<Bloco nome="nomeAgrupador">`. Permitting `Rotulo` and `NomeAgrupador` as optional children of `Agrupamento` would make non-articulated headings first-class and directly reusable by existing tooling.
- **`<td>` does not accept `<p>`.** Verified: `table/tr/td/p` fails on both schemas while `td` with inline content passes. Since `div`, `Agrupamento`, `Bloco`, `Texto` and friends are all block-or-inline containers, `td`'s inline-only model is an inconsistency that complicates faithful table rendering (and is why the reference parser has a dedicated `DESIGN_TABLE_PARSING.md`).

### 6.6 Suggested route

1. Open an issue at `github.com/lexml/lexml-schemas` (or the current schema repository) with §6.1–6.4.
2. Attach the reproducible validation script (§11 of the predecessor doc) so reviewers can confirm both the current rejection and the patched acceptance.
3. Offer the corpus documents (`pn_cst_38_19801031`, `port_mf_454_19770825`) as motivating public-domain examples.
4. Note that `lexml-parser-projeto-lei` already faces this: `LexmlRenderer.renderAnexoGenerico` routes non-articulated annexes to `DocumentoGenerico`, and `isArticulatedAnexo` documents the same limitation.

**Interim stance for our parser:** keep the flattening scheme and the `--emitter` flag. If the change is adopted, add a third emitter (`generico-aninhado`) — the internal model is already a real tree (§5.1 of the predecessor), so it is purely a rendering addition. **This is the payoff of keeping the model rendering-agnostic**: a schema improvement costs us one emitter, not a rewrite.

---

## 7. Consolidated Plan Changes

| Change | Cycle | Rationale |
|---|---|---|
| Quotation guard redesigned: indentation + citation antecedent + numbering monotonicity | 4 (revised) | leading-quote test **fails** on `parecer_93` (§3.2) |
| Intermediate `id`-path levels always materialised | 5 | breadcrumb gap found in testing (§2.3 Rule A) |
| Leaf-only text extraction, de-duplicated | 5 | nested-`li` duplication found in testing (§2.3 Rule B) |
| **Statutory Viability Analyzer** + coverage gate + validate-then-fallback | **4b (new)** | Q2; 2 of 3 naive statutory verdicts are false positives |
| **Jurisprudence emitter** (`Sumula`/`Acordao`) | **6b (new)** | `sumula_stj_125`, `sumula_carf_42`, `REsp_1306393` map natively |
| Dual-schema `ValidationReport`, per-schema reporting, `--schema` flag | 0, all | Q4 |
| `generico` segmentation API + XSLT reference stylesheet | 5 | Q1 — proven working (§2.2) |
| **Structure Referee** (optional, cached, advisory) | **7b (new)** | Q3 — narrow residue only |
| RAG integration removed | ~~9~~ | Q5 |
| Corpus fixtures expanded to all 15 samples with expected routes | 8 | new evidence |

Cycle order becomes: 0, 1, 2, 3, 4, **4b**, 5, 6, **6b**, 7, **7b**, 8.

### 7.1 Expected routing table (test fixture for Cycle 4b)

This is the labelled ground truth the analyzer must reproduce. Entries marked ⚠ are my current best judgement and should be confirmed against full document text during implementation.

| Sample | Expected route | Note |
|---|---|---|
| `port_mf_277_20180607` | `norma` + `Anexo` ⚠ | 2 real articles; 130-entry annex separated |
| `ad_srf_3_19990107` | `generico` ⚠ | `DECLARA` + incisos, no articles |
| `ad_pgfn_13_20111220` | `generico` ⚠ | incisos only |
| `ad_pgfn_3_20080918`, `ad_srf_22`, `adn_cosit_19`, `adn_cst_10` | `generico` | short declaratory acts |
| `par_cosit_26_20000629` | `generico` | **hard case** — quoted articles, no indent |
| `parecer_93_2018_decor_cgu_agu` | `generico` | 21 quoted articles must be rejected |
| `pn_cst_38_19801031` | `generico` | 4-level dotted hierarchy |
| `port_mf_454_19770825` | `generico` | item-based Portaria (genre prior would mislead) |
| `…CARNE_LEAO` | `generico` | style-driven headings |
| `sumula_carf_42` | `jurisprudencia` (`Sumula`) | |
| `sumula_stj_125` | `jurisprudencia` (`Acordao`) ⚠ | has `EMENTA`/`ACÓRDÃO`/`RELATÓRIO` |
| `REsp_1306393` | `jurisprudencia` (`Acordao`) ⚠ | has `EMENTA`/`ACÓRDÃO` |

---

## 8. Answers in Brief

1. **Segmentation from `generico`:** works — proven with Saxon XSLT 3.0 (§2.2) and a Python API (§2.5). The existing `GeraCSVporArtigoPorAgrupador.xsl` will not work unmodified (it selects statutory elements); §2.4 gives a working replacement. Testing it surfaced two real bugs now fixed as design rules.
2. **Statutory validation stage:** yes, and necessary — naive detection false-positives on 2 of 3 candidates. Indentation is the key discriminator; add coverage gating and validate-then-fallback so preferring statutory is safe (§3).
3. **LM support:** yes, but narrowly — advisory referee on flagged decisions only. **Skip the local SLM**: 6 GB Maxwell VRAM is the binding constraint. Use a budget API (DeepSeek/Qwen/Moonshot), cached, ~$3–10 for a 1,000-document corpus (§4).
4. **Dual-schema validation:** keep it — the two schemas are equivalent over the entire `generico` surface, so it costs one call and buys portability plus drift detection (§5).
5. **RAG integration:** dropped from the plan.
6. **Recursive `Agrupamento`:** well-founded, backward-compatible, one content-model change; §6 is drafted for forwarding, with reproducible evidence and two secondary observations (`Rotulo`/`NomeAgrupador` in the open model; `td` inline-only).

---

## 9. Remaining Open Questions

1. **`port_mf_277` routing** — split into `Norma` + `Anexo` (2 articles + separate annex document), or single `generico`? I lean toward the split since LexML supports it natively (verified case Q), but it is the most complex path in the plan.
2. **Jurisprudence scope** — is `<Jurisprudencia>`/`Sumula`/`Acordao` in scope now (§3.4), or should súmulas/acórdãos route to `generico` for uniformity? `Acordao` mandates `RelatorioTexto`/`VotoTexto`/`ExtratoAtaTexto`, which not all documents supply.
3. **Referee timing** — build Cycle 7b speculatively, or defer until Cycle 4b measurements show whether rules suffice? I recommend deferring.
4. **Corpus ground truth** — can you confirm the §7.1 expected routes, especially the ⚠ entries? That table is the analyzer's specification, and your domain judgement is worth more than my inference from paragraph dumps.
