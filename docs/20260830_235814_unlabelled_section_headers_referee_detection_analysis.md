# Unlabelled section headers: why `RELATÓRIO` and `CONCLUSÃO` are lost, and how a referee recovers them

- **Date:** 2026-08-30
- **Status:** analysis and proposed fix. **Nothing implemented.**
- **Trigger:** user observation on `par_cosit_26_20000629` — `CONCLUSÃO` sits
  inside `pp1_agr21_agr1` (the container for item `18.1.`), and item `19.` is
  its sibling rather than its child; `RELATÓRIO` is buried in the body preamble.
- **Recommendation:** **one new cycle, `8d`**, in the same interstitial slot as
  the referee-configuration amendment and Cycle 8c. Not a separate development
  plan — see §9.

---

## 0. The originating prompt (verbatim, for reproducibility)

> I ran the following test:
>
>     PYTHONPATH=src python3 -m lexml_nonstat parse \
>                 --referee=api \
>                 --referee-cache=/tmp/lexml_referee_cache \
>                 samples/par_cosit_26_20000629.docx > par_cosit_26_with_referee.xml
>
> And I got the following problems:
>
> 1. Is "AgrupamentoHierarquico" been used? […] wouldn't be better to use an
>    "AgrupamentoHierarquico" to nest elements "pp1_agr17_agr1" … "pp1_agr17_agr4"
>    instead of using the "Bloco nome="nivel" to indicate nesting? […]
> 2. […] Clearly, "CONCLUSÃO" is a different section, and "19" should be nested
>    inside it. Instead, "CONCLUSÃO" is inside "Agrupamento" "pp1_agr21_agr1",
>    holding the item "18.1", which is clearly wrong. In fact, right at the
>    beginning, there is a "RELATÓRIO" section, which should be a separated
>    "AgrupamentoHierárquico", holding every item inside of it, and "CONCLUSÃO"
>    should be another "AgrupamentoHierárquico" at the same level.

And, on the fix:

> Properly identifying that "RELATÓRIO" and "CONCLUSÃO" should be section
> separators might need LLM usage. Please check how to apply it to solve such
> scenario.

---

## 1. Executive summary

Two problems were reported. They have **different answers**, and separating
them is most of the work.

| # | Report | Verdict |
|---|---|---|
| 1 | `AgrupamentoHierarquico` not used; nesting carried by `Bloco nome="nivel"` | **Not a defect.** The command ran the default *flat* emitter. The nested emitter exists, is complete, and produces exactly the requested shape — measured in §2. |
| 2 | `RELATÓRIO` / `CONCLUSÃO` not recognised as sections | **A real defect, confirmed, and present in *both* emitters.** It lives in hierarchy inference, not in rendering. Root cause in §3. |

The defect's cause is a single line of policy:

> `Candidate.is_candidate` (`hierarchy/unify.py:161`) admits a paragraph as a
> possible section header **only** if Word gave it an outline level *or* it
> carries a parseable rótulo. A paragraph that is a heading by **meaning alone**
> can never open a section.

`par_cosit_26`'s `RELATÓRIO` has `style='Normal'`, `outline_level=None`,
`bold=False`, `indent_effective=0` and no label — formatting that is
**byte-for-byte identical** to `Fl. 7 DF COSIT RFB` and to the signature line
`Carlos Alberto de Niza e Castro`. No deterministic formatting rule can separate
them, because there is no formatting difference to read. The user's instinct is
correct: this is a semantic judgement, and it is exactly the case the plan built
a referee for.

**And the referee already has the question.** `Referee.is_heading` is declared
in the protocol (`referee/protocol.py`), implemented in all three backends,
prompted, cached, and covered by tests — and **no code in the pipeline ever
calls it** (§4). It is a dead question. This analysis proposes calling it, after
replacing its prompt, which §5 measures as unusable in its current form.

Measured outcome of the redesigned prompt on the corpus's three hardest
documents: **17/17 correct** on `par_cosit_26`, **26/26** on `sumula_stj_125`,
**4/4** on `REsp_1306393` (§5.2).

---

## 2. Report 1 is not a defect: the nested emitter already does this

### 2.1 What was actually run

```bash
python3 -m lexml_nonstat parse --referee=api … samples/par_cosit_26_20000629.docx
```

`--emitter` defaults to `auto`, and `auto` follows the route (plan §4.4,
amendment A-R.7). `par_cosit_26` routes to `generico`, so the **flat** emitter
ran. In the flat emitter, flattening into siblings with depth carried
out-of-band **is the design**, stated at `render/generico.py:1-30`:

> `Agrupamento` cannot nest (§2.1 row C, pinned as a test), so the tree is
> **flattened into siblings** and its depth is carried out of band, three
> redundant ways: the `id` path; `<Bloco nome="nivel">`; `@nome`.

This is required because the *shipped* schemas (`lexml/`) reject nesting. The
flat emitter is the default precisely so the parser's correctness does not
depend on an unreleased schema (A-R.9).

### 2.2 What the nested emitter produces

Running the same document through the maintainers' change:

```bash
python3 -m lexml_nonstat parse --emitter=generico-aninhado --generation=proposed \
        --referee=api --referee-cache=/tmp/lexml_referee_cache \
        samples/par_cosit_26_20000629.docx
```

gives, for the very elements the report names:

```xml
<AgrupamentoHierarquico id="pp1_agh13" nome="secao">
  <Rotulo>14.</Rotulo>
  <AgrupamentoHierarquico id="pp1_agh13_agh1" nome="citacao">
    <NomeAgrupador>Lei nº 7.713, de 1988</NomeAgrupador>
    …
  </AgrupamentoHierarquico>
  <AgrupamentoHierarquico id="pp1_agh13_agh2" nome="citacao">
    <NomeAgrupador>Lei 8.134, de 1990</NomeAgrupador>
```

Real containment, `Rotulo`/`NomeAgrupador` instead of `Bloco nome="rotulo"`, and
**no `Bloco nome="nivel"` at all** — `render/generico_aninhado.py:15` records
that the marker is retired in this emitter as "a redundant marker that can
disagree with" the structure.

So the answer to *"haven't you replaced that artificial nesting structure by the
maintainers' proposal?"* is: **yes, in the emitter built for it.** The flat
emitter keeps the artificial encoding because it must; it targets schemas where
nesting is invalid.

### 2.3 The one thing worth changing here

Nothing in the tool told the user which emitter ran, or that another was
available. That is a usability gap, not a correctness one, and it is worth a
small deliverable (§7, F-6): name the emitter in the `--summary` output and in a
comment on the emitted XML, and — when `--generation=proposed` would have been
available — say so.

---

## 3. Report 2 is a real defect, and it is in inference, not rendering

### 3.1 It is not an emitter problem

The same fault appears in the nested output, in the same place:

```xml
<AgrupamentoHierarquico id="pp1_agh17_agh1" nome="subsecao">
  <Rotulo>18.1.</Rotulo>
  <Agrupamento id="pp1_agh17_agh1_txt1" nome="texto">
    <p>Em função da natureza jurídica do crédito cedido, …</p>
    <p>CONCLUSÃO</p>          <!-- ← swallowed by 18.1, exactly as in flat -->
  </Agrupamento>
</AgrupamentoHierarquico>
```

Both emitters faithfully render the tree they are given. The tree is wrong.

### 3.2 The measured cause

`hierarchy/unify.py:161`:

```python
@property
def is_candidate(self) -> bool:
    if self.quoted:
        return False
    if self.style is not None:          # Word outline level / Heading N
        return True
    return self.label is not None and not self.label.is_dispositivo
```

Two admission routes, both **formal**. `RELATÓRIO` has neither:

```
inlines = (Inline(text='RELATÓRIO', bold=False, italic=False, …),)
style = 'Normal'      outline_level = None     indent_effective = 0
num_id = None         ilvl = None              alignment = None
```

So it is never a `Candidate`, never reaches `unify_levels`, and falls through
`build_tree` into ordinary body content. Blocks 3–17 precede the first surviving
candidate (`2.`, block 18), so they become the tree's **preamble** — 15 nodes,
`RELATÓRIO` among them. `CONCLUSÃO` (block 92) falls between `18.1.` (block 91)
and `19.` (block 93), so it attaches to the *earlier* header, which is `18.1.`.
That is precisely the reported symptom, and it is correct behaviour for a
paragraph the system has classified as prose.

### 3.3 A correction to a docstring, found on the way

`hierarchy/tree.py:14` says blocks before the first header become the preamble,
*"which is how `par_cosit_26`'s `1.` sits in the front matter"*. There is no
`1.` in `par_cosit_26`. A regex for `^1[.\s]` over every block returns **zero
matches** — the source document simply never numbers its first item. The
preamble mechanism is right; the example given for it is not. Worth fixing while
in the file (F-7).

### 3.4 Why this matters beyond one sample

Preamble nodes are body content in no section at all:

| Sample | Sections | Preamble nodes |
|---|---|---|
| `parecer_93_2018_decor_cgu_agu` | 3 | **98** |
| `par_cosit_26_20000629` | 18 | **15** |
| `sumula_stj_125` | 7 | 9 |
| `pn_cst_38_19801031` | 6 | 6 |
| `REsp_1306393` | 0 | 6 |

`parecer_93`'s 98 preamble nodes are the same disease at scale: its `1 - REGIME
DE PREVIDÊNCIA COMPLEMENTAR`, `11 - BENEFÍCIO ESPECIAL` and `V - CÁLCULO DO
BENEFÍCIO ESPECIAL` are all `style='Normal'`, and its top numeric series was
rejected wholesale by A-4.2 as implausible (`1, 11, 111, 46, 194, 74`). Only
three roman-numeral headings survive.

### 3.5 The counter-example that proves the diagnosis

`sumula_stj_125` **already produces exactly what the user is asking for**:

```
'AGRAVO REGIMENTAL NO AGRAVO DE INSTRUMENTO N. 46.146-SP'  secao   lvl 1
   'EMENTA'      subsecao lvl 2
   'ACÓRDÃO'     subsecao lvl 2
   'RELATÓRIO'   subsecao lvl 2
   'VOTO'        subsecao lvl 2
```

Same words, same document genre, correct tree. The difference is one attribute:
`sumula_stj_125`'s headings carry `style='Heading 1'`, `outline_level=0`.
`par_cosit_26`'s carry nothing.

**This is the whole finding.** The inference is already correct *when the
evidence exists*. The gap is documents where the evidence was destroyed —
which, per §3.4, is most of the corpus and presumably most of the 300+ unseen
documents, since the conversion pipeline that flattened `par_cosit_26`'s headers
and footers into body paragraphs (`docs/20260830_205825_…`) is the same one that
flattened its heading styles into `Normal`.

---

## 4. The referee already has this question, and nothing asks it

`referee/protocol.py` declares four questions. The second:

```python
def is_heading(self, para: str, ctx: str) -> Verdict:
    """Is ``para`` a heading, or an emphasised sentence?"""
```

with a ratified vocabulary `HEADING_VERDICTS = ("heading", "prose")`, a prompt
template `_TEMPLATES["heading"]`, an `adjudicate` mapping
`"heading": "is_heading"`, implementations in `api.py`, `local.py` and
`null.py`, and tests in four test modules.

Grepping every caller outside the referee package itself:

```
src/lexml_nonstat/referee/protocol.py:58    (the vocabulary constant)
src/lexml_nonstat/referee/adjudicate.py:42  (the kind → method mapping)
tests/unit/test_referee_protocol.py:163
tests/unit/test_referee_api.py:629
tests/unit/test_telemetry.py:159
tests/unit/test_referee_local.py:49
```

**Zero production callers.** The infrastructure was built and never wired up.
That is fortunate for the fix — the transport, cache, adjudication, telemetry,
override accounting and fixture machinery all already exist and are tested. What
is missing is a *generator* of candidates to ask about, and a prompt worth
asking.

---

## 5. Can the referee actually do it? Measured, not assumed.

### 5.1 The current prompt is unusable — this is the load-bearing measurement

`_TEMPLATES["heading"]` asks:

> *O trecho abaixo é um TÍTULO de seção, ou uma frase enfatizada dentro do texto
> corrido?*

Put to the live API referee (`deepseek-v4-flash`) over `par_cosit_26`'s 17
uppercase short paragraphs:

| Block | Verdict | Conf. | Text |
|---|---|---|---|
| 4 | prose | 0.70 | `Fl. 6 DF COSIT RFB` |
| 5 | **heading** | 0.90 | `COSIT` |
| 8 | **heading** | 0.95 | `MINISTÉRIO DA FAZENDA` |
| 9 | **heading** | 0.95 | `0 SECRETARIA DA RECEITA FEDERAL` |
| 10 | **heading** | 0.95 | `COORDENAÇÃO-GERAL DO SISTEMA DE TRIBUTAÇÃO` |
| 12 | **heading** | 0.95 | `DOMICÍLIO FISCAL` |
| 16 | heading | 0.98 | `RELATÓRIO` ✔ |
| 21 | **heading** | 0.95 | `Fl. 7 DF COSIT RFB` |
| 32 | **heading** | 0.70 | `Fl. 8 DF COSIT RFB` |
| 36 | heading | 0.95 | `FUNDAMENTOS LEGAIS` ✔ |
| 42, 56, 75 | **heading** | 0.95–1.00 | `Fl. 9…11 DF COSIT RFB` |
| 92 | heading | 0.95 | `CONCLUSÃO` ✔ |
| 94 | heading | 0.95 | `ORDEM DE INTIMAÇÃO` ✔ |
| 97 | **heading** | 0.80 | `Carlos Alberto de Niza e Castro` |
| 98 | **heading** | 0.90 | `COORDENADOR-GERAL DA COSIT` |

**15 of 17 answered "heading", at confidences up to 1.00.** Wiring this prompt
in unchanged would turn every folio stamp and the signatory's name into a
section of the parecer — a far worse artifact than the one being fixed.

The prompt is not wrong about typography. `Fl. 9 DF COSIT RFB` *is* set like a
heading. The prompt asks the wrong question: **typographic role**, when what the
tree needs is **document-structural role**.

This vindicates the plan's own §7.1 caution and record §2.3's measurement that
the model answered two of three per-paragraph questions wrongly at 0.95 and
0.70. It is also why A-Q.3 inverted `quotation_boundary` to confirm-only.

### 5.2 A redesigned question answers it correctly

Replacing the question with a *structural* one, naming the negative classes the
corpus actually contains, and supplying **both** neighbours as context:

> Em um documento jurídico não articulado, um CABEÇALHO DE SEÇÃO abre uma
> divisão temática do raciocínio do próprio documento (ex.: RELATÓRIO,
> FUNDAMENTOS, CONCLUSÃO, VOTO, EMENTA).
>
> NÃO são cabeçalhos de seção:
> - artefatos de página: número de folha, rodapé de autenticação, URL, "Fl. 9",
>   "Página 2 de 7", código de localização;
> - timbre/órgão emissor no alto da primeira página;
> - nome de pessoa e cargo em bloco de assinatura;
> - rótulo de campo do formulário (ex.: DOMICÍLIO FISCAL, INTERESSADO);
> - frase enfatizada dentro do texto corrido.
>
> Contexto — parágrafo anterior: {prev}
> Contexto — parágrafo seguinte: {next}
> Trecho em julgamento: {excerpt}
>
> Responda "verdict": "secao" se abre uma seção temática do documento, ou "nao"
> caso contrário.

Same model, same temperature 0, same 17 paragraphs:

```
OK    4 got=   nao exp=   nao 0.95  'Fl. 6 DF COSIT RFB'
OK    5 got=   nao exp=   nao 0.95  'COSIT'
OK    8 got=   nao exp=   nao 0.95  'MINISTÉRIO DA FAZENDA'
OK    9 got=   nao exp=   nao 0.95  '0 SECRETARIA DA RECEITA FEDERAL'
OK   10 got=   nao exp=   nao 0.95  'COORDENAÇÃO-GERAL DO SISTEMA DE TRIBUTAÇÃO'
OK   12 got=   nao exp=   nao 0.95  'DOMICÍLIO FISCAL'
OK   16 got= secao exp= secao 1.00  'RELATÓRIO'
OK   21 got=   nao exp=   nao 1.00  'Fl. 7 DF COSIT RFB'
OK   32 got=   nao exp=   nao 1.00  'Fl. 8 DF COSIT RFB'
OK   36 got= secao exp= secao 0.95  'FUNDAMENTOS LEGAIS'
OK   42 got=   nao exp=   nao 1.00  'Fl. 9 DF COSIT RFB'
OK   56 got=   nao exp=   nao 1.00  'Fl. 10 DF COSIT RFB'
OK   75 got=   nao exp=   nao 1.00  'Fl. 11 DF COSIT RFB'
OK   92 got= secao exp= secao 1.00  'CONCLUSÃO'
OK   94 got= secao exp= secao 0.80  'ORDEM DE INTIMAÇÃO'
OK   97 got=   nao exp=   nao 0.95  'Carlos Alberto de Niza e Castro'
OK   98 got=   nao exp=   nao 0.95  'COORDENADOR-GERAL DA COSIT'
--- 17/17 correct
```

On `sumula_stj_125`, the corpus's densest and most adversarial case (48
candidates; the rules already get this document right, so any disagreement is a
regression):

```
     0  secao 0.95  'SÚMULA N. 125'
    24  secao 0.95  'EMENTA'          34  nao 0.98  'DJ 22.08.1994'
    28  secao 0.95  'ACÓRDÃO'         69  nao 0.95  'RECURSO ESPECIAL N. 34.988-SP (93.0013182-6)'
    35  secao 1.00  'RELATÓRIO'       86  nao 0.95  'DJ 08.11.1993'
    54  secao 1.00  'VOTO'           165  nao 0.95  'RECURSO ESPECIAL N. 36.084-SP'
   128  secao 0.95  'VOTO-VISTA'     182  nao 0.95  'DJ 27.06.1994'
   …                                 204  nao 0.95  'RECURSO ESPECIAL N. 40.136-SP (93.0030048-2)'
--- 26/26 correct
```

and on `REsp_1306393`, 4/4 — including `nao` for
`ATUAR COMO CONSULTORES NO ÂMBITO DO PNUD/ONU.` (an all-caps *ementa fragment*,
the exact trap) and `nao` for the case number.

**47 of 47 across the three documents.** Enough to build on, and — critically —
its errors on `sumula_stj_125` would be *visible as a regression against
existing goldens*, which is how §7's test plan proposes to keep it honest.

### 5.3 Why the answer improved

Three changes, each doing work:

1. **The question changed from typographic to structural.** "Is this set like a
   title?" and "does this open a division of the document's reasoning?" have
   different answers for `Fl. 9 DF COSIT RFB`, and only the second is the
   question the tree is asking.
2. **The negative classes are named.** Every one of them is a real class from
   this corpus — folio stamps (`docs/20260830_205825_…`), the letterhead block,
   signature names (A-3.5's signature regions), and form-field labels (A-2.2's
   allowlist). This is the "genre-agnostic evidence fusion" CLAUDE.md asks for:
   the classes generalise, the samples do not.
3. **Both neighbours are supplied.** A heading is defined by what follows it as
   much as by what precedes it. `CONCLUSÃO` followed by `19. A cessão de
   direitos…` reads as a heading; `COORDENADOR-GERAL DA COSIT` followed by a
   disclaimer does not.

---

## 6. The design: confirm-only, exactly as A-Q.3

The referee must **not** be allowed to volunteer sections. Plan invariant #8 and
§7.3's "rules run first, always" both forbid it, and A-Q.3 already established
the pattern for precisely this situation. So the fix is in two halves.

### 6.1 A deterministic generator that proposes, and cannot impose

A new admission route in `unify.py` — call it a **prose-form candidate** — that
marks a paragraph as a *possible* header when it is typographically distinctive
but formally unlabelled. Proposed gate, every clause measured against the corpus
census in §5:

- non-empty, **≤ 7 words** and **≤ 60 characters**;
- **≥ 85 % of its letters uppercase**, or Word says bold-and-alone;
- not `quoted` (the existing quotation guard still vetoes first);
- not purely numeric/punctuation;
- **inside `Segmentation.body`** — front and back matter are already segmented
  and must not be re-litigated;
- carries **no parseable label** (a labelled heading already has a route).

This is a *generator*, not a decision. It is deliberately **over-inclusive** —
the §5 census shows it proposes 19 candidates on `par_cosit_26` for 4 true
headers, and 48 on `sumula_stj_125`. Over-inclusion is safe here and precision
is not, because the next stage can only ever *remove*.

Its confidence is pinned **below** `FLAG_THRESHOLD` (0.60) — the
`BOUNDARY_RULE_CONFIDENCE = 0.55` precedent from A-Q.3 — so that:

- every prose-form candidate is **flagged**;
- with `--referee=none`, **nothing is confirmed and every tree is byte-identical
  to today's**. All 135 goldens hold. This is invariant #8 for free, and it is
  what makes the change safe to land.

### 6.2 The referee confirms, one candidate at a time

For each flagged candidate, ask the redesigned question (§5.2). A candidate
becomes a `Candidate` with `is_candidate == True` **only** when the referee
answers `secao` at `confidence ≥ REFEREE_MIN_CONFIDENCE` (0.60). Everything else
— `nao`, low confidence, abstention, timeout, outage, malformed JSON — leaves
the paragraph as prose, i.e. leaves today's behaviour.

The two guarantees this preserves, stated as they will be tested:

- **No fabrication.** The referee cannot name a paragraph the generator did not
  propose, so no answer, however confident or wrong, can invent a citable unit
  with its own URN.
- **No degradation of a correct tree.** Where Word evidence exists it still
  wins: `style is not None` admits a candidate before the referee is consulted,
  so `sumula_stj_125` reaches the referee with its structure already built.

### 6.3 Where the confirmed header lands in the tree

This is the part §6.1–6.2 do not settle, and it is the fix's real design
question. A confirmed `RELATÓRIO` must not simply become another depth-1
sibling — that would put it *beside* items `2.`–`18.`, not *above* them, and the
user's report is explicit that it should hold "every item inside of it".

The rule proposed, consistent with `unify_levels`' existing stack machine:

> A referee-confirmed prose-form header opens a **new sequence key of its own**
> and therefore a new stack level. Any *labelled* series that was open is closed
> and re-opened **beneath** it — because a numeric series that continues across
> the header (`18.`, then `CONCLUSÃO`, then `19.`) is evidence that the header
> divides the document at a level *above* that series.

Two sub-cases, both present in the corpus and both needing a decision:

- **`par_cosit_26`.** The `2.`–`19.` series runs *through* `RELATÓRIO` (block
  16) and `CONCLUSÃO` (block 92). Under the rule above, `RELATÓRIO` and
  `CONCLUSÃO` become depth-1 `secao`s and the numbered items become their
  depth-2 children — which is exactly what the report asks for. Note the
  consequence: **`19.` becomes a child of `CONCLUSÃO`**, and items `2.`–`18.1.`
  become descendants of `RELATÓRIO`, deepening the whole tree by one level and
  moving every body `id` in both emitters.
- **`sumula_stj_125`.** Headers are already at depth 2 under case containers, by
  Word evidence, and the referee must change nothing.

**This is the load-bearing decision in the whole fix, and it is the one I want
confirmed before implementation** (§8, Q-1). It changes every body `id` on at
least one sample and therefore moves goldens — a reviewed behaviour change, but
a large one.

### 6.4 A named heading is a `NomeAgrupador`, not lost text

A confirmed header's text must become the section's `heading`, which both
emitters already render (`Bloco nome="nomeAgrupador"` flat, `<NomeAgrupador>`
nested) — and **must not also remain a `<p>`**, or text conservation counts it
twice. Cycle 6's A-6.4 established exactly this rule for `Caput`'s echoed
`Rotulo`, and `leaf_texts` already reads `nomeAgrupador` as text-bearing
(`render/common.py:94`). So conservation stays arithmetic; the paragraph moves
from body to heading rather than being duplicated or dropped.

---

## 7. The fix, as deliverables

| ID | Deliverable | Where |
|---|---|---|
| **F-1** | **Replace the `heading` prompt** with the structural question of §5.2, including the named negative classes and the next-paragraph context slot. Retire the current template — §5.1 measures it as actively harmful. Vocabulary changes `("heading","prose")` → `("secao","nao")`; `HEADING_VERDICTS` and `VOCABULARIES` follow. | `referee/prompts.py`, `referee/protocol.py` |
| **F-2** | `is_heading` gains a **next-paragraph** context argument (or `ctx` becomes a structured two-field string). The protocol's four questions stay four. | `referee/protocol.py`, `api.py`, `local.py`, `null.py` |
| **F-3** | **The prose-form candidate generator** of §6.1, at a confidence below `FLAG_THRESHOLD`, gated to `Segmentation.body`. | `hierarchy/unify.py` |
| **F-4** | **Wire the referee into candidate admission**, confirm-only, through the existing `adjudicate` path so telemetry, override accounting and the cache all apply unchanged. | `hierarchy/tree.py`, `hierarchy/__init__.py` |
| **F-5** | **The depth rule** of §6.3, once Q-1 is answered. | `hierarchy/unify.py` |
| **F-6** | **Emitter transparency** (§2.3): `--summary` and an XML comment name the emitter that ran, and note when `generico-aninhado` was available but not selected. | `cli.py`, `render/common.py` |
| **F-7** | **Docstring correction** (§3.3): `par_cosit_26` has no `1.`. | `hierarchy/tree.py:14` |
| **F-8** | **Recorded fixtures** for the new question, hand-authored and documented as such per A-4b.5, so the suite stays green and offline. | `tests/fixtures/referee/` |

### 7.1 Test plan

- **Invariant #8 regression, the most important test.** With `--referee=none`,
  **all 135 goldens across 9 kinds byte-identical**. If this fails, the
  generator is imposing rather than proposing.
- **`sumula_stj_125` non-regression.** With the referee *on*, its tree is
  unchanged — 7 cases × their subsections. This is the test that catches a
  referee overreaching into a document the rules already got right.
- **Adversarial referee (invariant #9, the A-4b.6 pattern).** A referee
  answering `secao` to *every* question must not change `sumula_stj_125`'s tree
  (Word evidence wins) and must not fabricate a section outside
  `Segmentation.body`.
- **Abstaining referee.** Identical output to `--referee=none`, on all 15
  samples.
- **Conservation over the new heading** (§6.4): no word lost, none duplicated,
  ×15, both emitters.
- **Cross-emitter equivalence (invariant #11)** re-asserted after the depth
  change: identical text and identical segment-URN *structure* in flat and
  nested output.
- **Prompt-regression fixtures** pinning the §5.2 measurements, so a future
  prompt edit that reintroduces §5.1's behaviour fails loudly.

---

## 8. Open questions for the user

**Q-1 — the depth rule (§6.3). Load-bearing; blocks F-5.**
Should a confirmed `RELATÓRIO`/`CONCLUSÃO` become a **parent** of the numbered
series that runs through it (so `19.` nests under `CONCLUSÃO`, and every body
`id` on `par_cosit_26` changes, in both emitters), or a **sibling** marker at
the same depth (smaller golden churn, but it does not deliver what the report
asks for)? My recommendation is **parent** — it is what the document means, and
it is what was reported — but the golden churn is large enough that it should be
your call, not mine.

**Q-2 — scope of the referee's new authority.**
Confirm-only over an over-inclusive generator (§6.1) is the A-Q.3-consistent
design and what I recommend. The alternative — letting the referee scan the
whole body and volunteer headers — would find headers the generator's
typographic gate misses (a title-case heading, say), at the cost of invariant #8
no longer being structural. I recommend **confirm-only**; flagging in case you
want the wider net for the 300+ unseen documents.

**Q-3 — interaction with the running-header work.**
`docs/20260830_205825_…` proposes detecting and suppressing `Fl. n` /
`Documento de 7 página(s)` artifacts, still unimplemented. If that lands first,
this fix's generator proposes ~13 fewer candidates on `par_cosit_26` and the
referee is asked ~13 fewer questions. The two are independent and either order
works; doing the artifact work first is cheaper. Worth deciding the order.

---

## 9. Should this be a separate development plan?

**No. One new cycle, `8d`, in the existing plan.** The reasoning, against the
same criteria the 8c decision used:

| Criterion | Reading |
|---|---|
| Does it invalidate delivered work? | **No.** Cycles 0–8c stand. With `--referee=none` — what §9.3 pins for the whole suite — output is byte-identical. |
| Does it need new architecture? | **No.** The referee protocol, transport, cache, adjudication, telemetry, override accounting and fixture conventions all exist and are tested. This wires up a question that was already declared. |
| Does it change the schema story? | **No.** `Agrupamento/@nome` is an open `xsd:string`; both generations are unaffected; the capability probe is untouched. |
| Does it change delivered behaviour? | **Yes, under `--referee=api` only** — and materially, per Q-1. That makes it a cycle with a changes-file, which is exactly what the `dev-cycle` process is for. |
| Blast radius | Three modules (`unify.py`, `tree.py`, `referee/prompts.py`) plus the CLI touch of F-6. Comparable to 8c, which touched a similar set. |

A separate plan would duplicate §9.2's cross-cutting invariants and the referee
contract, and create the second source of truth A-3.4 and A-8.2 both refused.

Proposed placement, extending STATUS.md's interstitial run:

```
… 8 → referee configuration amendment → 8c → 8d (this) → 9
```

It **does not begin Cycle 9**, for the same reason 8c did not: Cycle 9 is
regression consolidation and corpus scale-out, and it should consolidate a
hierarchy inference that is finished.

Anticipated amendments, to be assigned on implementation: **A-H.1** (the
prose-form candidate route and its sub-threshold confidence), **A-H.2** (the
`heading` prompt replacement, with §5.1's measurement as its justification),
**A-H.3** (the depth rule, per Q-1), **A-H.4** (heading text moves rather than
duplicates, extending A-6.4).

---

## 10. What was verified, and how

Every claim above that could be checked by command was:

| Claim | Method |
|---|---|
| The nested emitter produces real `AgrupamentoHierarquico` nesting | Ran `--emitter=generico-aninhado --generation=proposed`; read the output |
| The defect is in inference, not rendering | Same fault, same paragraph, in both emitters' output |
| `RELATÓRIO` carries no formatting evidence | Dumped every `StyledPara` field for block 16 |
| `par_cosit_26` contains no `1.` | Regex `^1[.\s]` over all blocks — zero matches |
| `sumula_stj_125` already gets this right | Walked its section tree; read `style`/`outline_level` on blocks 24, 28, 35, 54 |
| `is_heading` has no production caller | `grep -rn is_heading src/ tests/` |
| The current prompt is unusable | Live API call, 17 paragraphs — 15 wrong |
| The redesigned prompt works | Live API call, same 17 + 26 + 4 — 47/47 correct |
| Preamble census | `infer_hierarchy` over all 15 samples |

Not verified, and flagged as such: whether the redesigned prompt holds on the
300+ unseen documents. The corpus is 15 samples standing in for them, and §5.3's
argument — that the *negative classes* generalise even though the samples do not
— is a design argument, not a measurement. F-8's fixtures and §7.1's adversarial
tests are what keep it honest.
