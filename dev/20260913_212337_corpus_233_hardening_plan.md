# Development Plan — Hardening the Parser Against the 233-Document Corpus

- **Date:** 2026-09-13
- **Status:** Proposed. **Not yet executed** — no cycle of this plan has been implemented.
- **Predecessor plan:** [`20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`](20260801_145839_complete_development_plan_lexml_non_statutory_parser.md) — complete through Cycle 9. This plan does not supersede it; it is the follow-on that §10's top risk ("15 samples ⇏ 300+ corpus") always anticipated.
- **Corpus:** `../br-taxqa-r_v2.0/original/nao_articulados/` — 233 `.docx`
- **Output of the measuring run:** `../br-taxqa-r_v2.0/lexml/` — 234 XML files
- **Evidence:** every number in §1 comes from the run recorded in §1.1, not from estimation.

---

## 0. Why this plan exists

The predecessor plan was built and tested against **15 samples**. Its own §10
named the risk that those 15 would not represent the 300+ documents the parser
is aimed at, and Cycle 9 built the `corpus` subcommand precisely so the question
could eventually be asked. This plan is the answer to it, for the first 233
real documents.

**The headline is that the parser did not break.** All 233 parsed, all 234
emitted documents validate against *both* schemas at the `proposed` generation,
and no document raised. What the corpus exposes is not fragility but **silence**:
the parser degrades gracefully in places where the degradation is invisible in
the artifact, and a downstream consumer cannot tell a document that genuinely
has no internal structure from one whose structure was not recognised.

Every cycle below turns one of those silences into either a fix or an explicit,
checkable statement.

### 0.1 A note on scope discipline

Two things in §1 are **already fixed** and are recorded here only so the plan's
inventory is complete and honest: the filename collision (§1.5) and the batch
isolation gap (§1.6). They were repaired during the measuring run, with tests,
because the run could not produce a trustworthy artifact otherwise. Their
*root causes* remain open and are Cycles 2 and 5 below.

---

## 1. What the 233-document run measured

### 1.1 The run

```bash
python3 -m lexml_nonstat parse \
  --emitter=generico-aninhado --generation=proposed \
  --referee=api --referee-cache=<cache> --linker=auto \
  --summary --quiet -o ../br-taxqa-r_v2.0/lexml \
  ../br-taxqa-r_v2.0/original/nao_articulados/*.docx
```

Exit `0`. Referee: DeepSeek over the OpenAI-compatible endpoint, disk-cached
(623 cache entries). Linker: `linkertool` at `/usr/local/bin/linkertool`.

| Measure | Result |
|---|---|
| Documents parsed | **233 / 233** |
| Hard failures (exceptions) | **0** |
| XML files written | **234** (233 primaries + 1 `!anexo1`) |
| Schema-valid, both schemas, `proposed` | **234 / 234** |
| External references resolved (`Remissao`) | **5 071** across 222 documents |
| Structured bodies | 126 |
| Flat bodies | **107** |
| Documents with an incomplete URN | **24** |
| Low-confidence routes | 2 |
| Rule decisions flagged as uncertain | **691** |
| Referee overrides | **127**, across 53 documents |

Routing: 230 `generico`, 3 `norma`. Profiles: `servico` 67, `generic` 62,
`parecer` 42, `ato_declaratorio` 38, `jurisprudencia_generico` 19, `portaria` 5.

### 1.2 Finding A — 107 documents render flat, and cannot be distinguished from genuinely flat ones

> **Qualified by Cycle 3 (amendments A-3.1, A-3.3, 2026-09-13).** Two
> corrections, both material to how this section should be read:
>
> 1. **The figures below are from a *refereed* run.** The rules-only figure at
>    the same commit is **115/233**, with `sc_cosit` at **58**/109, not 52.
>    §1.8 records the referee closing that gap (115 → 107), so the numbers are
>    consistent — but this section does not say which configuration it measured,
>    and a cycle whose headline is a flatness delta needs that stated.
> 2. **The `sc_cosit` flatness was not a referee-reachable gap at all.** The
>    *Relatório / Fundamentos / Conclusão* skeleton §2's Cycle 3 names is
>    **title-case**, and `is_prose_form_header` requires an upper-case ratio of
>    0.85 — so those headings were never proposed as candidates and **no
>    referee was ever asked about them**. They were invisible under every
>    configuration. A-3.1's `section_res` is the repair.
>
> Cycle 3 reduced flatness **115 → 86** overall and `sc_cosit` **58 → 33**,
> rules-only. See its
> [report](20260913_212337_corpus_233_hardening_plan/20260913_224424_cycle_3_report.md).

Nearly **46%** of the corpus (107/233) emits `flat_fallback`: hierarchy
inference found nothing and the body is a flat run of paragraphs at confidence
`0.00`. The concentration is not uniform — it tracks genre:

| Genre prefix | Flat | Approx. total | Note |
|---|---|---|---|
| `sc_cosit` | 52 | 109 | soluções de consulta — the corpus's largest genre |
| `ad_pgfn` | 14 | 15 | almost every one |
| `sci_cosit` | 8 | 12 | |
| `adn_cst` | 6 | 7 | |
| `adn_cosit` | 4 | 6 | |
| others | 23 | — | 1–3 each across 15 prefixes |

`ad_pgfn` at 14 of 15 is the signal that matters: a genre where nearly every
document is flat is far more likely to be a **recogniser gap** than 15
genuinely unstructured documents. `sc_cosit` at 52 of 109 is the volume case.

> **Cycle 1 investigated this and the hypothesis did not hold (A-1.5).**
> `ad_pgfn` is 14/15 flat because those documents genuinely have no internal
> structure: the whole operative content of the act is **one quoted sentence**,
> and 19 of the 22 `ad_pgfn`/`adn_cst` documents have a body of 0–3 blocks
> against `MIN_SECTIONS_FOR_FULL_CONFIDENCE = 3`. `is_prose_form_header` fires
> 18 times across the genre and **every hit is a signature**; 21 of 22
> documents reject nothing at all, because nothing heading-shaped is ever
> proposed. Unlike Cycle 3's soluções de consulta there is no title-case
> skeleton being suppressed — **flat is the correct answer**, and no
> `section_res` is recommended for `ato_declaratorio`.

Confidence `0.00` is doing double duty here — it is emitted both when a
document has no structure and when the evidence fusion found no *candidate* at
all. Those are different facts, and the artifact does not separate them.

> **Closed by Cycle 1 (2026-09-13), which also corrected this section's
> proposed taxonomy — amendments A-1.2 through A-1.5.**
>
> Every flat tree now carries a `flat_cause` and a `span_coverage`. Measured
> rules-only over all 233 documents, the partition is **`no_candidate` 52,
> `all_rejected` 15, `too_few_sections` 8, `empty_body_span` 11** — all 86 flat
> documents, none unexplained. Four corrections this section should be read
> with:
>
> 1. **The proposed three-way split is not the corpus's shape.** There is no
>    "single continuous prose run" bucket; the fourth real cause is an **empty
>    body span**, which this section does not model.
> 2. **A "scores too weak" cause is unreachable.** A solitary label is refused
>    by `unify_levels` *before* it is scored, so across the 155 documents with
>    assignments the lowest mean score is **0.7553**. Flatness from scoring is
>    always damping.
> 3. **"No candidate" mostly does not mean "unstructured."** 41 of the 52 have a
>    body span of ≤6 blocks, and **82 of 86** flat documents have a span
>    covering under half the document (median 9%). That is why the cause ships
>    with `span_coverage` beside it.
> 4. **`ad_pgfn` at 14/15 is not a recogniser gap** — see §1.2's genre table
>    note below and A-1.5. The investigation found no skeleton to recognise.
>
> See the [report](20260913_212337_corpus_233_hardening_plan/20260913_231242_cycle_1_report.md).

### 1.3 Finding B — 24 documents carry a best-effort URN, in six distinct shapes

> **Corrected by Cycle 2 (amendment A-2.4, 2026-09-13): the true figure is 46.**
> The table below counts `Metadata.missing` — components extraction did not
> find. It does **not** count the 27 documents that silently take
> `authority="federal"` from the `generic` profile default, whose URN therefore
> names the *wrong* issuer rather than none. Read this section as a floor.
> Cycle 2 reduced the 46 to a residue of 23, enumerated in its
> [report](20260913_212337_corpus_233_hardening_plan/20260913_222009_cycle_2_report.md) §5.
>
> Cycle 2 also found a defect class this section does not model at all: four
> documents emitted a **confidently wrong** URN, having read a citation of
> another act as their own identity (amendment A-2.3).

| Missing components | Count | Examples |
|---|---|---|
| `number, date` | 9 | the six `servico` declarations, `nota_pgfn_crj_1104_2017`, `parecer_pgfn_crj_701_2016`, `parecer_pgfn_pga_2683_2008` |
| `date` | 7 | `REsp_1306393`, `sumula_stj_125`, `sumula_stj_136`, `sumula_carf_42`, three `nota_pgfn_crj` |
| `doc_type, number` | 3 | `adi_5422_STF`, `adi_5583_STF`, `re_855091_tema_808` |
| `number` | 2 | `sc_15_20090309`, `sc_6007_20190325` |
| `authority` | 2 | `ad_cosar_47_20001127`, `ad_mesa_cn_38_20051014` |
| `authority, number, date` | 1 | `parecer_pgfncat_1503_2010` |

**This is the warning the user first reported.** `ad_cosar_47_20001127` is
missing its authority: "Cosar" is not in `ato_declaratorio`'s `authority_map`,
so the URN falls back to the `federal` default. `ad_mesa_cn_38_20051014` (Mesa
do Congresso Nacional) is the same shape.

A-2.3 established that a best-effort URN is *acceptable*. What the corpus adds
is that **17 documents now carry the `0000` date sentinel and 10 the `;0` number
sentinel** in a URN that is written to a file and will be cited. Several of
these are recoverable from the filename or the document body; `sc_15_20090309`
and `sc_6007_20190325` in particular have both number and date in their
filenames.

### 1.4 Finding C — 62 documents route through the `generic` profile

> **Closed by Cycle 3 (2026-09-13).** The `solucao_consulta` profile now claims
> **125 of the 127** sc/sci/sd documents, reading the right `urn_type` per
> sub-genre off the epigraph. Two further findings this section does not model:
>
> - **Twelve of them were not on `generic` at all** — ten scored 0.40 on
>   `jurisprudencia_generico`'s unanchored STJ pattern (a solução *discussing*
>   STJ case law), and two tied at 0.9 with `servico` on a bare `carne-leao`
>   pattern, winning on registration order. Those two emitted a `:servico:`
>   URN type — a solução claiming to be a taxpayer service page.
> - **A tie is a genre decided by a list literal.** `test_winning_margin` pins
>   that for the 15 samples; Cycle 3 adds the same assertion over the 127.
>
> The residue is `sc_15_20090309` and `sc_6007_20190325`, bare-`sc` regional
> soluções whose first line is a portal banner rather than an epigraph — already
> recorded as residue in Cycle 2's report §5.

`solução de consulta` is the corpus's dominant genre (109 `sc_cosit` + 12
`sci_cosit` + 2 `sc` = 123 documents, **53% of the corpus**) and there is no
profile for it. Most land on `servico` or `generic`. The URN type comes out as
`solucao.consulta.cosit` — which is correct and is evidence the metadata layer
is doing well — but with no profile there is no epigraph pattern, no authority
map, and no genre-specific hierarchy expectation for the single largest class
of document in the corpus.

`generic` carries `base_score=0.05` and `urn_authority="federal"`, so any
document reaching it inherits `federal` regardless of its actual issuer.

### 1.5 Finding D — a degraded URN is not a unique filename *(fixed; root cause open)*

Six documents — `declaracao_benficios_fiscais_DBF`,
`declaracao_de_informacoes_sobre_atividades_imobiliarias_DIMOB`,
`declaracao_de_servicos_medicos_e_de_saude_DMED`,
`declaracao_sobre_operacoes_imobiliarias_DOI`,
`declaração_de_imposto_de_renda_retido_na_fonte_DIRF`,
`sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO` — carry neither number
nor date, so all six reduce to the identical URN:

```
urn:lex:br:ministerio.fazenda;secretaria.receita.federal:servico:0000;0
```

Since `_write_bundle` named files from the URN slug, the first pass wrote
**229 files for 233 documents**: five documents were silently overwritten. Every
individual parse reported success; the loss was visible only by counting.

**Fixed during the run** (`src/lexml_nonstat/cli.py::_write_bundle`): a `taken`
set threaded through the run disambiguates a clashing slug with the source stem,
changing *only the filename* — the URN inside the document is untouched. Two
tests pin it. The run now writes 234 distinct files.

Two things remain open, and they are Cycle 2:

1. The sentinel URN itself is unchanged — six documents still *claim* the same
   identity, which matters for any consumer keyed on URN rather than filename.
2. The fix is **per-invocation**. Eight parallel `parse` processes each hold
   their own `taken` set and will still overwrite each other. This was observed
   directly during the measuring run.

### 1.6 Finding E — `parse` abandoned the batch on any failure *(fixed; hardening open)*

`_cmd_parse` isolated an unreadable source but ran model building, rendering and
validation unguarded. One document raising took every later document in the same
invocation with it — at 233 sources, one defect would have meant up to 232
missing outputs. `corpus` already had per-document isolation; `parse`, the
subcommand that actually *writes files*, did not.

**Fixed during the run** (`src/lexml_nonstat/cli.py::_cmd_parse`): per-document
`try`/`except`, the failure reported against that document, the run continuing,
exit code `1`. One test pins it.

The corpus found **0** documents that trigger it, so this is latent. That is
worth stating plainly rather than treating as reassurance: it means the guard is
untested by real data, and Cycle 5 asks for the negative cases.

### 1.7 Finding F — three regression tests fail at `HEAD`, for an environment reason

`tests/regression/test_bare_checkout.py` fails three of its eleven tests at
commit `19338df`, on a clean tree, **before any change in this work**:

- `test_the_bare_run_still_exercises_the_parser`
- `test_skips_carry_the_probe_diagnostic`
- `test_the_nested_assertions_are_the_ones_that_skip`

**Root cause, verified.** The fixture runs pytest in a subprocess with
`["-q", "-rs", ...]` and parses its stdout. pytest emits ANSI colour, so the
summary line arrives as:

```
'\x1b[32m\x1b[32m\x1b[1m509 passed\x1b[0m, \x1b[33m4 skipped\x1b[0m...'
```

`_count` tokenises on whitespace and reads the token *before* `"passed"`, which
is `\x1b[1m509`, not `509` — so it returns `0`. Likewise
`line.startswith("SKIPPED")` never matches a colourised line. The bare-checkout
run itself is **healthy**: 509 passed, 131 skipped, exit 0.

Verified remedy: adding `--color=no` to the subprocess arguments restores both —
the summary parses and the `SKIPPED` lines match.

```
args=['-q','-rs']              summary='\x1b[32m...128 passed...'  SKIPPED lines=0
args=['-q','-rs','--color=no'] summary='128 passed, 4 skipped...'  SKIPPED lines=2
```

The rest of the suite is green: **6 021 passed, 4 skipped, 3 failed** (these
three), 2 deselected.

### 1.8 Finding G — the referee earns its place, and the rules are uncertain a lot

> **Corrected by Cycle 6 (amendment A-6.1, 2026-09-14): the flatness figures
> below are pre-Cycle-3 and no longer hold.** The override table is exactly
> right and reproduces to the number offline — but its *consequence* has moved.
> Measured against Cycle 1's rules-only baseline of 86, the referee now takes
> flatness **86 → 83**: **three** documents gain structure, not eight. Five of
> the original eight were soluções de consulta that Cycle 3's `section_res`
> (A-3.1) now admits **with no referee at all**.
>
> The dependency this section warns about is also **closed**: Cycle 6 publishes
> the run's 625 recorded answers as `tests/corpus_referee_fixtures/`, so a
> refereed corpus run is reproducible offline, at zero marginal cost, with zero
> network calls.
>
> See the [report](20260913_212337_corpus_233_hardening_plan/20260914_112449_cycle_6_report.md).

691 rule decisions were flagged as uncertain across the corpus. The referee
overrode **127** of them in 53 documents:

| Rule verdict | Referee verdict | Count |
|---|---|---|
| `nao` | `secao` | 74 |
| `quoted` | `own` | 50 |
| `continuation` | `boundary` | 3 |

Eight documents gained structure they did not have in the rules-only pass:
`nota_pgfn_crj_1040_2015`, `parecer_pgfn_crj_701_2016`, `sc_cosit_140_20230714`,
`sc_cosit_159_20230807`, `sc_cosit_17_20220420`, `sc_cosit_181_20230818`,
`sc_cosit_200_20211214`, `sc_cosit_98_20230510` (flat: 115 → 107).

> **Post-Cycle-3 this is three, not eight** (A-6.1): `nota_pgfn_crj_1040_2015`,
> `parecer_pgfn_crj_701_2016` and `sc_cosit_200_20211214`. The five `sc_cosit`
> documents in the list are now structured **rules-only**, by `section_res`.

Read the other way: **74 prose headers** the rules called "not a section" were
real sections, and **50 paragraphs** the rules called quoted material were the
document's own articulation. That is a large systematic correction, and it is
the strongest available evidence about where the deterministic rules
under-recognise at corpus scale. It is also a **cost and reproducibility
dependency** — a rules-only run of this corpus is measurably worse.

### 1.9 Finding H — two low-confidence routes

`resol_tse_22_20060523` (0.44) and `sc_cosit_134_20140602` (0.52) routed to
`generico` below the 0.60 threshold. Both produced valid output. Low, but only
two — routing generalised well.

---

## 2. Cycles

Numbered from 1 to keep them distinct from the predecessor plan's 0–9. Each
cycle is implemented with the `dev-cycle` skill and lands green.

### Cycle 1 — A truthful account of flatness

**Problem:** §1.2. 107 documents are flat and the artifact cannot say why.

**Deliverables**

1. Split the flat outcome into distinguishable causes, recorded on the model and
   surfaced in `--format=json` and the corpus report: *no candidate structure was
   found* vs. *candidates were found and all were rejected* vs. *the document is
   a single continuous prose run*.
2. A per-genre flatness report in `corpus`, so `ad_pgfn` at 14/15 is visible as a
   pattern rather than as fifteen unrelated documents.
3. A `dump-tree --why` investigation of the `ad_pgfn` and `adn_cst` genres, whose
   near-total flatness is the strongest recogniser-gap signal. Findings written
   to `docs/`, **not** acted on in this cycle.

**Exit criteria** — every flat document carries a cause; the corpus report
groups flatness by genre; the `ad_pgfn` investigation is recorded. No golden
moves (this cycle adds reporting, not structure).

**Explicitly not in scope:** changing what is recognised. Cycle 1 measures; Cycle 3 acts.

### Cycle 2 — URN completeness and identity collisions

**Problem:** §1.3 and the open root cause of §1.5.

**Deliverables**

1. `authority_map` entries for the issuers the corpus actually contains, driven
   by the two documents that miss authority today (`Cosar`, `Mesa do Congresso
   Nacional`) and audited across all 233 rather than fixed one at a time.
2. A **filename-derived fallback** for number and date, applied only when the
   body yields nothing, recorded with its own `*_source` provenance value so a
   filename-derived component is never mistaken for a document-derived one. This
   directly recovers `sc_15_20090309`, `sc_6007_20190325` and several `nota_pgfn_crj`.
3. A decision, **put to the user**, on what identity the six sentinel `servico`
   documents should carry — they are service descriptions (DBF, DIMOB, DMED, DOI,
   DIRF, Carnê-Leão) with no number or date in any form. Options: a slug-based
   URN component derived from the service name; the `!` fragment convention; or
   accepting the shared URN and treating filename disambiguation as the answer.
4. Cross-process collision safety, or an explicit statement that `parse -o` is
   single-invocation and a documented refusal when two processes target one
   directory.

**Exit criteria** — the 24 incomplete URNs are reduced to a stated, justified
residue; every remaining sentinel is a recorded decision, not an accident; no
two documents in the corpus share a URN unless §2.3's decision says they may.

### Cycle 3 — A `solucao_consulta` profile

**Problem:** §1.4. 53% of the corpus has no profile.

**Deliverables**

1. A `solucao_consulta` profile — epigraph patterns, authority map, field labels
   — covering `sc_cosit`, `sci_cosit` and bare `sc`.
2. Genre-specific front-matter expectations (these documents carry a stereotyped
   *Relatório* / *Fundamentos* / *Conclusão* skeleton that the generic
   recogniser is not looking for), which is the most likely single remedy for
   the 52 flat `sc_cosit` documents in §1.2.
3. Re-measurement of flatness across the corpus, before and after, as the
   cycle's headline number.

**Exit criteria** — `sc_cosit` flatness falls measurably; no existing sample's
routing or golden changes; the profile is registered and `list-profiles` shows it.

**Risk:** this is the cycle most likely to move existing behaviour, because
adding a profile changes profile scoring for every document. The exit criterion
that no existing golden moves is therefore load-bearing, and any movement is an
escalation under the `dev-cycle` rules.

### Cycle 4 — Repair the bare-checkout harness

**Problem:** §1.7. Three regression tests fail at `HEAD` for a colour-code
reason, and a suite with three known-red tests trains its readers to ignore red.

**Deliverables** — `--color=no` on the subprocess invocation (verified remedy),
plus an assertion that the harness's own parsing is exercised, so the next
formatting change fails loudly instead of silently reading zero.

**Exit criteria** — `pytest tests/ -q` fully green, 0 failures.

**This is the cheapest cycle here and should probably be done first**; it is
listed fourth only because it is unrelated to the corpus findings.

### Cycle 5 — Batch robustness, negative cases

**Problem:** §1.6. The isolation guard is untested by real data.

**Deliverables** — deliberately corrupt, truncated, empty and wrong-format
documents in `tests/fixtures/`; assertions that a batch of 200 with 5 bad
documents writes 195 files, reports 5 failures and exits 1; and the same for
`corpus`. Plus a documented resumability story: re-running over a directory that
already holds output should be safe and cheap.

**Exit criteria** — a batch survives every degenerate input the fixtures
contain; no traceback reaches the user for any of them.

### Cycle 6 — Referee economics and reproducibility

**Problem:** §1.8. The referee materially improves the corpus, which makes it a
dependency rather than an option.

**Deliverables**

1. Publish the corpus's referee cache as a fixture set, so a refereed run is
   reproducible offline and at zero cost — the same seam
   `tests/referee_fixtures/` already uses.
2. Measure and record cost and wall time per document, and the cache hit rate on
   a second run.
3. A recommendation, with evidence, on whether the 74 `nao`→`secao` overrides
   should become a rule change instead. 74 corrections of one kind is a pattern,
   and a rule that learns it is cheaper and more reproducible than an API call.

**Exit criteria** — a refereed corpus run reproducible with no network; the
override analysis recorded in `docs/`.

---

## 3. Suggested order

**Cycle 4** (green suite, ~1 hour) → **Cycle 2** (URN correctness, unblocks
citation) → **Cycle 3** (the 53% profile gap, the largest single win) →
**Cycle 1** (flatness diagnosis, informed by 3) → **Cycle 6** (referee
economics) → **Cycle 5** (robustness hardening).

Cycle 1 is deliberately placed after Cycle 3: if the `solucao_consulta` profile
resolves much of the `sc_cosit` flatness, the flatness taxonomy should be
designed against what remains rather than against the current picture.

---

## 4. What this plan does not do

- It does not touch `lexml/`. The vendored schemas stay byte-identical.
- It does not revisit the `generico-aninhado` / `proposed` arrangement. 234/234
  documents validate; the emitter and the maintainers' schema change are working
  exactly as the predecessor plan intended.
- It does not add a `Jurisprudencia` emitter. The 19 `jurisprudencia_generico`
  documents (súmulas, ADIs, REsp) validate as `generico`, per ratified decision #2.
- It does not change the referee's confirm-only discipline or the thresholds in
  §7.3 of the predecessor plan.

---

## 5. Open questions for the user

1. **§1.3 / Cycle 2.3** — what identity should the six sentinel `servico`
   documents carry?
2. **Cycle 2.2** — is a filename-derived URN component acceptable at all, given
   that it is metadata from outside the document? The provenance field makes it
   *visible*; the question is whether it is *wanted*.
3. **Cycle 6.3** — if the 74 `nao`→`secao` overrides can be captured as a rule,
   should they be? It trades referee cost for a rule tuned on 233 documents,
   which is exactly the generalisation risk §10 of the predecessor plan warns about.

   > **Answered by Cycle 6 (A-6.3, 2026-09-14): no.** 35 of the 74 confirmations
   > sit on texts that *also* appear as refusals (`RELATÓRIO` 19 `secao` / 2
   > `nao`; bare `I`/`II`/`III` on both sides), so a text-keyed rule would be
   > wrong in both directions. The separable remainder is dominated by
   > `FUNDAMENTOS`/`CONCLUSÃO`, which Cycle 3's `section_res` already admits
   > deterministically. Evidence in
   > [`docs/20260914_112449_referee_override_rule_analysis.md`](../docs/20260914_112449_referee_override_rule_analysis.md).
