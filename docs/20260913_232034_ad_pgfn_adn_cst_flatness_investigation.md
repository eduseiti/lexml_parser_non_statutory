# `ad_pgfn` and `adn_cst`: why they are flat, and why that is correct

- **Date:** 2026-09-13
- **Raised by:** [`dev/20260913_212337_corpus_233_hardening_plan.md`](../dev/20260913_212337_corpus_233_hardening_plan.md)
  §1.2 and §2 Cycle 1, deliverable 3
- **Status:** investigation record. **Nothing here was acted on** — the plan
  scopes Cycle 1 to measurement ("Cycle 1 measures; Cycle 3 acts"), and the
  finding is in any case that no repair is warranted.
- **Configuration:** rules-only (`referee=None`), the configuration §9.3 pins
  for the suite and amendment A-3.3 fixes as this plan's baseline.

---

## 1. The question

Plan §1.2 calls `ad_pgfn` at 14 of 15 flat "the signal that matters":

> a genre where nearly every document is flat is far more likely to be a
> **recogniser gap** than 15 genuinely unstructured documents.

That reasoning was vindicated once already. Cycle 3 found exactly such a gap in
the corpus's largest genre: soluções de consulta carry a stereotyped
*Relatório / Fundamentos / Conclusão* skeleton in **title case**, while
`is_prose_form_header` requires an upper-case ratio of 0.85. Those headings were
never proposed as candidates, so **no referee was ever asked about them**, and
125 of 127 documents were flat under every configuration. The repair was
`DocumentProfile.section_res` (amendment A-3.1).

The question for this investigation is whether `ad_pgfn` and `adn_cst` are the
same story. **They are not.**

---

## 2. Verdict

| Genre | Flat | Verdict |
|---|---|---|
| `ad_pgfn` | 14 / 15 | **Cause (a): genuine absence of structure. Flat is correct. No gap.** |
| `adn_cst` | 6 / 7 | **Cause (a) for 5 of 7**, plus a *segmentation* defect in 2 — not a recogniser gap |

**Recommendation: do not add a `section_res` to `ato_declaratorio`.** There is
nothing to declare. This is a negative finding, and it is the useful kind: the
plan asked whether a recogniser gap was hiding here, and the answer is no.

---

## 3. The evidence

### 3.1 Per-document measurements

| Document | flat | conf | body span | body blocks | total | sections | rejected |
|---|---|---|---|---|---|---|---|
| ad_pgfn_1_20050218 | yes | 0.0 | 4–7 | 4 | 10 | 0 | — |
| ad_pgfn_1_20090327 | yes | 0.0 | 4–5 | 2 | 7 | 0 | — |
| ad_pgfn_1_20140102 | yes | 0.0 | 7–9 | 2 | 12 | 0 | — |
| ad_pgfn_1_20180312 | yes | 0.0 | 3–4 | 2 | 6 | 0 | — |
| ad_pgfn_2_20180403 | yes | 0.0 | 3–5 | 3 | 8 | 0 | — |
| **ad_pgfn_3_20080918** | yes | 0.0 | 3–4 | 2 | 6 | 0 | — |
| ad_pgfn_4_20020812 | yes | 0.0 | 3–4 | 2 | 6 | 0 | — |
| ad_pgfn_4_20061116 | yes | 0.0 | 3–4 | 2 | 8 | 0 | — |
| ad_pgfn_5_20061116 | yes | 0.0 | 3–4 | 2 | 8 | 0 | — |
| ad_pgfn_5_20160503 | yes | 0.0 | 3–4 | 2 | 7 | 0 | — |
| ad_pgfn_6_20061116 | yes | 0.0 | 3–4 | 2 | 8 | 0 | — |
| ad_pgfn_6_20081201 | yes | 0.0 | 3–4 | 2 | 6 | 0 | — |
| ad_pgfn_9_20111220 | yes | 0.0 | 3–4 | 2 | 6 | 0 | — |
| **ad_pgfn_13_20111220** | **no** | 0.5667 | 3–5 | 3 | 7 | 2 | — |
| ad_pgfn_14_20081201 | yes | 0.0 | 3–4 | 2 | 6 | 0 | — |
| adn_cst_8_19790228 | yes | 0.0 | 4–5 | 2 | 6 | 0 | — |
| adn_cst_10_19910417 | **no** | 0.85 | 4–6 | 3 | 8 | 3 | — |
| adn_cst_11_19780713 | yes | 0.0 | 6–6 | 0 | 7 | 0 | — |
| adn_cst_16_19790727 | yes | 0.0 | 5–7 | 1 | 8 | 0 | — |
| adn_cst_20_19890821 | yes | 0.0 | **None** | 0 | 5 | 0 | — |
| adn_cst_25_19891213 | yes | 0.0 | 4–4 | 1 | 6 | 0 | `top numeric series implausible: 2` |
| adn_cst_29_19860625 | yes | 0.0 | **None** | 0 | 5 | 0 | — |

Two numbers in this table decide the question.

**The body-block count.** Nineteen of the 22 documents have a body of **0–3
blocks**, against `MIN_SECTIONS_FOR_FULL_CONFIDENCE = 3`. A two-paragraph body
cannot hold a three-section skeleton. There is no room for structure to hide.

**The empty `rejected` column.** **21 of 22 documents reject nothing at all.**
This is the precise inverse of a Cycle 3 gap. There, the machinery collected
candidates and discarded them, or would have had the gate let them through;
here nothing heading-shaped is ever proposed, because nothing heading-shaped is
present.

### 3.2 The genre template — `ad_pgfn`

All 15 share one template. `ad_pgfn_3_20080918` in full (6 blocks, verbatim):

```
[00] Ato Declaratório PGFN nº 3, de 18 de setembro de 2008         ← epigraph
[01] "Autoriza a dispensa de apresentação de contestação e de interposição de
     recursos, bem como a desistência dos já interpostos, nas ações judiciais
     que especifica."                                              ← ementa
[02] O PROCURADOR-GERAL DA FAZENDA NACIONAL, no uso da competência legal …
     DECLARA que fica autorizada a dispensa …                      ← preamble
[03] "nas ações judiciais que visem obter a declaração de que não incide
     imposto de renda sobre o pagamento da parcela indenizatória devida aos
     parlamentares em face de convocação para sessão legislativa
     extraordinária."                                     ← THE OPERATIVE CONTENT
[04] JURISPRUDÊNCIA: REsp 502739/PE, DJ 17/11/2003; …              ← field label
[05] LUÍS INÁCIO LUCENA ADAMS                                      ← signature
```

The body is blocks 3–4: **one quoted sentence and a citation list.** That is the
whole act. The genre's function is to authorise the PGFN to stop litigating one
specific question — one question, one sentence. There is no
Relatório/Fundamentos/Conclusão analogue because there is nothing to relate,
reason about, or conclude.

The stereotypy is real, but it lives in the **front matter**, which is already
segmented correctly: the recurring strings are the preamble
(`O PROCURADOR-GERAL DA FAZENDA NACIONAL,` — 13 of 15, already matched by
`authority_res`), the ementa, the operative quote, and the signature. **None is
a section heading.**

### 3.3 The genre template — `adn_cst`

`adn_cst_29_19860625` in full (5 blocks, verbatim):

```
[00] Ato Declaratório Normativo CST nº 29, de 25 de junho de 1986   ← epigraph
[01] "Dispõe sobre a não retenção do imposto de renda na fonte sobre
     rendimentos pagos ou creditados por condomínios a profissionais
     liberais, trabalhadores autônomos e empreiteiros de obras (pessoas
     físicas)".                                                     ← ementa
[02] O Coordenador do Sistema de Tributação, Substituto, no uso das
     atribuições …                                                  ← preamble
[03] DECLARA, em caráter normativo, às unidades descentralizadas da
     Secretaria da Receita Federal e aos demais interessados, que os
     rendimentos … não estão sujeitos à retenção do imposto de renda na
     fonte.                                                ← operative content
[04] RAUL MENEZES                                                   ← signature
```

The one genre-wide recurring string is `DECLARA, em caráter normativo,` (6 of
7). That is an **enacting formula**, already declared in
`ato_declaratorio.enacting_res` as `^\s*declara\b` and belonging in
`FormulaPromulgacao`. It is never a standalone paragraph — it always runs on
into the operative sentence. Promoting it to a section heading would be a
category error.

### 3.4 The prose-form gate is not suppressing anything

This is the direct test of the Cycle 3 hypothesis, run over every paragraph of
all 22 documents. The gate is `upper_ratio >= 0.85`, `words <= 7`,
`chars <= 60`.

`is_prose_form_header` fires on exactly **18** paragraphs, and **every single
one is a signature** at upper-ratio 1.000:

```
ad_pgfn_13  [6] 1.000  ADRIANA QUEIROZ DE CARVALHO
ad_pgfn_3   [5] 1.000  LUÍS INÁCIO LUCENA ADAMS
adn_cst_20  [4] 1.000  PAULO BALTAZAR CARNEIRO
adn_cst_29  [4] 1.000  RAUL MENEZES
…  (18 in total, across 18 of the 22 documents)
```

All are claimed by back-matter segmentation and sit outside the body span, so
they never reach candidate collection.

The **near-misses** — short enough to be headers, below the upper-case gate —
are the list that would matter if a skeleton were being suppressed. All 8:

| Document | idx | upper | text | what it is |
|---|---|---|---|---|
| adn_cst_10 | 7 | 0.714 | `JOSEFA MARIA COELHO MARQUES Em exercício` | signature |
| adn_cst_16 | 6 | 0.677 | `JIMIR SEBASTIÃO DONIAK - Coordenador` | signature |
| ad_pgfn_1_20140102 | 0 | 0.391 | `Ato Declaratório PGFN Nº 1 DE 02/01/2014` | epigraph |
| ad_pgfn_1_20140102 | 2 | 0.211 | `Publicado no DOU em 3 jan 2014` | portal stamp |
| adn_cst_8 | 4 | 0.150 | `Jimir Sebastião Doniak` | signature |
| adn_cst_8 | 5 | 0.095 | `Coordenador Substituto` | signature |
| adn_cst_10 | 1 | 0.069 | `O ato não possui ementa. Ver íntegra` | portal artifact |
| adn_cst_20 | 1 | 0.043 | `Rendimento não tributável` | ementa |

**Not one is a section heading.** In Cycle 3 this list was full of real headings
the threshold excluded; here it is ementas, portal stamps and signatures.
Lowering `PROSE_HEADER_MIN_UPPER` would admit **no** true heading in these
genres and several false ones.

### 3.5 The two structured documents prove the machinery works

Where these genres *do* number themselves, the parser finds it unaided:

- **`ad_pgfn_13_20111220`** carries literal `I -` / `II -` incisos → structured,
  confidence 0.5667, signals `label:roman,series`.
- **`adn_cst_10_19910417`** carries `1.`, `1.1`, `2.` → structured, confidence
  0.85, correctly nesting `1.1` under `1.`.

Label-bearing paragraphs appear in only 5 of 22 documents, and the three
non-structured cases are correctly refused: `adn_cst_11`'s
`I. R. (PF) - Declaração do Espólio…` is a subject line (`I. R.` = Imposto de
Renda, not roman numeral I); `adn_cst_8`'s `5.13.28.01 - Obrigatoriedade…` is a
subject-classification code; and `adn_cst_25`'s lone `2.` has no `1.` to anchor
it, so `validate_top_series` refuses a top series of `[2]` as implausible. Even
had it been admitted, one section damps to 0.2833 and falls below the 0.5
threshold. The refusal is right.

---

## 4. Why the Cycle 3 analogy does not transfer

| Diagnostic marker | Cycle 3 (soluções de consulta) | `ad_pgfn` / `adn_cst` |
|---|---|---|
| Recurring standalone heading text | `Relatório`/`Fundamentos`/`Conclusão`, 125 of 127 | **none found** |
| Headings sitting just below the gate | title case, ratio ≈ 0.11 vs 0.85 | near-misses are ementas, stamps, signatures |
| A body large enough to divide | many blocks | **0–4 blocks** |

All three markers are absent. A `section_res` for `ato_declaratorio` would have
no literal to match.

---

## 5. A separate finding: two documents lose their operative text to front matter

Not a recogniser gap, and **not fixed here** — recorded because the measurement
found it and a future cycle should own it.

**`adn_cst_20_19890821` and `adn_cst_29_19860625` have `body = None`.** Their
substantive `DECLARA, em caráter normativo, …` paragraph at index 3 — the entire
operative content of the act — is absorbed into the front-matter hull, leaving
no body at all. Verified directly:

```
adn_cst_20_19890821: total=5 body=None
   [00] Ato Declaratório Normativo CST nº 20, de 21 de agosto de 1989
   [01] Rendimento não tributável
   [02] O COORDENADOR DO SISTEMA DE TRIBUTAÇÃO-SUBSTITUTO, no uso das atribuições…
   [03] DECLARA, em caráter normativo, às Superintendências Regionais…   ← operative
   [04] PAULO BALTAZAR CARNEIRO
```

Mechanism: `epigraph` = 0, `ementa` = 1, `preamble` = 2, `enacting` = None;
`front.hull(0)` spans 0–3 because `hull` takes `min(start)…max(end)` over the
front parts, and `_absorb_gaps` attaches the unclaimed index 3 to the adjacent
front matter rather than opening a body. Back matter is 4, so
`primary_start = 4 > primary_end = 3` and the body is `None`.

**No invariant fails** — every block lands somewhere, so conservation holds and
no test catches it. But the act's operative sentence is classified as front
matter and will render inside `ParteInicial` rather than as body content.
`adn_cst_11` (body = index 6, an empty trailing paragraph) and `adn_cst_16`
(body 5–7, 1 block) are milder versions, driven by portal-export artifacts.

Even with a correct body, all of these would still and rightly be **flat** — a
one-paragraph body has no structure. The defect is about *where the text lives*,
not about hierarchy. The code comments in `_absorb_gaps` describe attaching
stray notes, not operative text, which suggests this is unanticipated rather
than intended; that should be confirmed before any repair.

A related and larger instance appears elsewhere in the corpus:
`pn_cosit_1_20020924` has `body = None` despite **79 blocks**, because
segmentation read three ementa headings (`IRRF. RETENÇÃO EXCLUSIVA.
RESPONSABILIDADE`, …) as *signatures*, so back matter swallowed the document.

---

## 6. The two delivered goldens

Both are pinned samples, so anything touching them is high-stakes.

**`ad_pgfn_3_20080918`** — flat, confidence 0.0, body span 3–4, **zero
candidates, zero rejections**. Its flatness is correct and structurally forced:
a two-paragraph body of one quoted sentence and a citation list. Its golden
records `"flat": true, "confidence": 0.0` with both paragraphs in `preamble`.
Any change giving this document sections would be a regression, and since it
collects no candidates at all, only a new admission route could do so.

**`ad_pgfn_13_20111220`** — the genre's structured outlier and the higher-stakes
of the two. Golden: `flat: false`, confidence 0.5667, two `inciso` sections
`I -` and `II -`, each scoring 0.85 with signals `['label:roman', 'series']`. It
reaches 0.5667 because `document_confidence` damps two sections by 2/3
(0.85 × 2/3), clearing the 0.5 threshold **by only 0.0667** — verified:
`document_confidence([0.85, 0.85])` → 0.5667. This document is the canary for
any change to label admission, series validation, or the damping constant.

---

## 7. What was observed, and what was inferred

**Observed directly:** every figure in §3.1; full text dumps of all 22
documents; the `is_prose_form_header` results and upper-case ratios (re-run
independently of the investigation that first reported them — the count is
**18**, not the 17 first reported); the label scan; the recurring-string counts;
the segmentation spans; the golden contents; the confidence arithmetic.

**Inferred:** that `ad_pgfn`'s single-sentence form reflects the genre's legal
function — supported by the uniform template across all 15 documents, not by an
external source; that the `adn_cst_20`/`_29` front-hull absorption is
undesirable rather than intended, read from `_absorb_gaps`'s own comments; and
that lowering `PROSE_HEADER_MIN_UPPER` would admit false positives here, which
follows from the near-miss table in §3.4 but was not confirmed by running a
referee.
