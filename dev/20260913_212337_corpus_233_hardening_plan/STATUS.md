# Cycle Status — Corpus 233 Hardening Plan

Plan: [`20260913_212337_corpus_233_hardening_plan.md`](../20260913_212337_corpus_233_hardening_plan.md)

> The plan was written on 2026-09-13 from a measuring run over the
> 233-document corpus at `../br-taxqa-r_v2.0/original/nao_articulados/`. See
> plan §1 for the evidence.
>
> **Five of the six cycles are complete: 4, 2, 3 and 1 (2026-09-13), and 6
> (2026-09-14)**, in the order §3 suggests. Only **Cycle 5** remains. The suite
> is fully green at **6 167 passed / 0 failed / 4 skipped / 2 live-deselected**,
> up from the 6 021-with-3-failures the plan was authored against. The baseline
> table below is preserved as written, as the record of that original state.
>
> Cycle 1 closes §1.2: every flat tree now names its cause and records how much
> of the document its body span covered. It also **corrected the plan** in four
> places (A-1.2 … A-1.5) — including finding that §1.2's "strongest
> recogniser-gap signal", `ad_pgfn` at 14/15 flat, is not a gap at all.
>
> Cycle 6 closes §1.8 and answers §5.3. The measuring run's 625 referee answers
> are published as `tests/corpus_referee_fixtures/`, so a refereed corpus run is
> reproducible **offline, with zero network calls** — the dependency §1.8 warns
> about is closed rather than noted. It also **corrected the plan twice more**:
> the referee's flatness value is now **86 → 83** (three documents, not eight —
> Cycle 3 absorbed the rest), and the 74 `nao`→`secao` overrides **should not**
> become a rule, because 35 of them sit on texts that also appear as refusals.

| Cycle | Title | Date | State | Tests | Spec | Report |
|---|---|---|---|---|---|---|
| 1 | A truthful account of flatness | 2026-09-13 | **complete** | 6151 pass / 0 fail / 4 skip / 2 live-deselected | [spec](20260913_231242_cycle_1_spec.md) | [report](20260913_231242_cycle_1_report.md) |
| 2 | URN completeness and identity collisions | 2026-09-13 | **complete** | 6052 pass / 0 fail / 4 skip / 2 live-deselected | [spec](20260913_222009_cycle_2_spec.md) | [report](20260913_222009_cycle_2_report.md) |
| 3 | A `solucao_consulta` profile | 2026-09-13 | **complete** | 6082 pass / 0 fail / 4 skip / 2 live-deselected | [spec](20260913_224424_cycle_3_spec.md) | [report](20260913_224424_cycle_3_report.md) |
| 4 | Repair the bare-checkout harness | 2026-09-13 | **complete** | 6028 pass / 0 fail / 4 skip / 2 live-deselected | [spec](20260913_220540_cycle_4_spec.md) | [report](20260913_220540_cycle_4_report.md) |
| 5 | Batch robustness, negative cases | — | **not started** | — | — | — |
| 6 | Referee economics and reproducibility | 2026-09-14 | **complete** | 6167 pass / 0 fail / 4 skip / 2 live-deselected | [spec](20260914_112449_cycle_6_spec.md) | [report](20260914_112449_cycle_6_report.md) |

Suggested order (plan §3): **4 → 2 → 3 → 1 → 6 → 5**. **Cycle 5 is the only one
remaining.**

## Baseline at the time of writing

Commit `19338df` ("Cycle 9"), clean tree.

| Measure | Value |
|---|---|
| Suite | 6 021 passed, 4 skipped, **3 failed**, 2 deselected |
| The 3 failures | `tests/regression/test_bare_checkout.py` — pre-existing, environment-induced (plan §1.7), remedy verified |
| Corpus documents parsed | 233 / 233, 0 hard failures |
| XML written | 234 (233 primaries + 1 `!anexo1`), all distinct |
| Schema-valid (both schemas, `proposed`) | 234 / 234 |
| References resolved | 5 071 across 222 documents |
| Flat bodies | 107 / 233 |
| Incomplete URNs | 24 / 233 |
| Referee overrides | 127 across 53 documents |

## Changes already landed (during the measuring run, ahead of this plan)

Recorded here because plan §1.5 and §1.6 inventory them as findings whose
*root causes* remain open cycles. Both were required to produce a trustworthy
artifact and both carry tests.

| Change | File | Why | Tests |
|---|---|---|---|
| Filename disambiguation on a shared URN slug | `src/lexml_nonstat/cli.py::_write_bundle` | Six documents share one sentinel URN; the run wrote 229 files for 233 documents, overwriting five silently | `test_parse_out_never_overwrites_on_a_shared_urn`, `test_parse_out_keeps_the_urn_the_metadata_resolved` |
| Per-document isolation in `parse` | `src/lexml_nonstat/cli.py::_cmd_parse` | One raising document abandoned every later document in the invocation | `test_parse_isolates_a_failing_document` |

Neither change alters the XML any document produces; the first changes only
filenames on collision, the second only what happens after a failure.

## Amendments

| Id | Cycle | Date | What changed, and why |
|---|---|---|---|
| **A-2.1** | 2 | 2026-09-13 | **The URN grammar admits a slug where a number goes.** Answers plan §5.1. Six service descriptions (DBF, DIMOB, DMED, DOI, DIRF, Carnê-Leão) state no number or date in any form, so A-2.3's sentinels collapsed all six onto one URN — the corpus's only collision, six documents claiming one identity. Each states its own name and acronym in its first line, so the slug comes from the document, not its filename. `lexml-base.xsd:1055` types the `URN` attribute `xsd:anyURI` with no pattern, so the grammar was the only constraint. A slug must begin with a letter and so can never collide with the `;0` sentinel. *Decided with the user (Q-4), golden movement confirmed separately (Q-5)* |
| **A-2.2** | 2 | 2026-09-13 | **A profile may derive its URN type per document.** `jurisprudencia_generico` serves súmulas, acórdãos, recursos and ADIs under one fixed `urn_type="sumula"`, so `REsp_1306393` — an acórdão — claimed to be a súmula. `DocumentProfile.urn_type_res` reads the type off the epigraph; profiles declaring none behave exactly as before (verified: 13 of 15 samples byte-identical). The case number is left as the number: it is how these documents are actually cited. *Decided with the user (Q-6)* |
| **A-2.3** | 2 | 2026-09-13 | **A confidently-wrong URN is a defect class the plan did not name, and it is worse than a sentinel.** Four documents read a *citation of another act* as their own identity — `nota_pgfn_crj_1114_2012` emitted `…:portaria:0000;294` from "Portaria PGFN Nº 294/2010" on its second paragraph. Root cause: `_EPIGRAPH_RE`'s type group forbade `/`, so `NOTA PGFN/CRJ/Nº 1114/2012` never matched and the scan fell through. A sentinel is visible to a consumer; a wrong number is not. The plan's §1.3 inventory counts only *incomplete* URNs and should be read as a floor |
| **A-2.4** | 2 | 2026-09-13 | **§1.3's count of 24 is corrected to 46.** It counted `Metadata.missing` only, missing 27 documents that silently inherited `generic`'s `federal` authority default — Finding C (§1.4) surfacing as a URN defect. Cycle 2 was scoped to all 46 by the user; the residue is 23, enumerated in the cycle report §5 |
| **A-3.1** | 3 | 2026-09-13 | **A profile may declare its genre's section headings, admitted without a referee.** Answers Cycle 3 deliverable 2, whose premise was wrong: the plan assumed the *Relatório/Fundamentos/Conclusão* skeleton was a recogniser gap profile data would close. It is not reachable at all — `is_prose_form_header` requires `upper_ratio >= 0.85` and these headings are **title-case** (~0.11), so they were never proposed and **no referee was ever asked**. 125 of the genre's 127 documents were flat under every configuration, including a refereed one. `DocumentProfile.section_res` + `build_tree(section_res=…)` admit them deterministically. Invariant #8 holds: this reads a skeleton the genre states in words rather than guessing. Every pre-Cycle-3 profile declares none and is byte-identical. *Confirmed with the user (M-1, M-2)* |
| **A-3.2** | 3 | 2026-09-13 | **Anchoring an `authority_res` pattern is not always the right repair — Cycle 2's m-6 is qualified, not generalised.** Cycle 3 anchored `jurisprudencia_generico`'s STJ pattern the way m-6 anchored `servico`'s, and reverted it: **unnecessary** (the new profile's 0.9 epigraph outranks the 0.40 either way — 125/127 measured both ways), **insufficient** (two documents open a line "O Superior Tribunal de Justiça (STJ), ao julgar…"), and **not free** (`REsp_1306393` matched only mid-line; dropping it moved `find_preamble`, the front/body boundary 0–12 → 0–5, and the body tree's confidence 0.0 → 0.3 — movement in a delivered sample). m-6 was right because a *fabricated identity* was at stake there. Caught by `test_measured_shape`, which asserts confidence independently of the goldens — **every golden was byte-identical through this defect** |
| **A-1.1** | 1 | 2026-09-13 | **A flat tree names why it is flat, and how much of the document its body span covered.** `DocSignals` gains `flat_cause` (one of the closed `FLAT_CAUSES`) and `span_coverage`. Answers §1.2's "confidence `0.00` is doing double duty — it is emitted both when a document has no structure and when the evidence fusion found no *candidate* at all". The 15 `tests/golden/hierarchy/*.json` move, and **only** those: no other golden kind embeds the tree dict, verified before the change was proposed. Each was compared against its `HEAD` version with the two keys stripped and is byte-identical, so the movement is additive-key-only with no value change anywhere. *Confirmed with the user (Q-1) with the blast radius stated in the question* |
| **A-1.2** | 1 | 2026-09-13 | **§1.2's proposed taxonomy does not match what the corpus contains, in two ways.** The plan proposes splitting flatness into *no candidate* / *candidates found and all rejected* / *a single continuous prose run*. Measured rules-only over all 233: the real partition is **no_candidate 52, all_rejected 15, too_few_sections 8, empty_body_span 11** — summing to all 86 flat documents with none left over. (a) There is no "single continuous prose run" bucket; the fourth real cause is an **empty body span**, which the plan does not model. (b) A "scores too weak" bucket is **structurally unreachable**: a solitary label (`W_LABEL_SOLO`, 0.25) is refused by `unify_levels` at its `solitary`/`orphan` guards *before* `_score` is reached, so across all 155 corpus documents that have assignments the lowest mean score is **0.7553**. Flatness from scoring is therefore always damping, never weak scores, and the shipped vocabulary omits the unreachable code rather than inviting a consumer to handle a case that cannot arise |
| **A-1.3** | 1 | 2026-09-13 | **"No candidate" mostly does not mean "unstructured", so the cause ships with a coverage ratio beside it.** 41 of the 52 `no_candidate` documents have a body span of ≤6 blocks; the bucket's median span coverage is **0.09**, and **82 of all 86** flat documents have a body span covering under half the document. 40 flat documents have ≥2 profile-declared headings in the whole document but <2 inside the body span. Reporting those 52 as "no structure found" would be misleading, so `span_coverage` is recorded on every flat outcome. **It cannot be computed in `build_tree`** — that function receives an already-sliced span and never sees the blocks outside it, and `Span` carries no document total — so it is computed in `infer_hierarchy`. Per the user's decision (Q-3) this is a *field*, not a fifth cause: a segmentation defect and a hierarchy outcome should not be conflated |
| **A-1.4** | 1 | 2026-09-13 | **Cycle 3's report §7 figure "43 of 125" does not reproduce.** Measured over the corpus, `solucao_consulta` documents with fewer than two declared headings inside their body span are **45 of 128** by profile (41 of 123 by `sc*` filename prefix); no grouping yields 125 or 43. 42 of those 45 are flat, and all 42 flat `solucao_consulta` documents have <2 declared headings in body — a near-perfect predictor, and the mechanism behind the genre's residual flatness |
| **A-1.5** | 1 | 2026-09-13 | **§1.2's "strongest recogniser-gap signal" is not a recogniser gap.** `ad_pgfn` at 14/15 flat was investigated per Cycle 1 deliverable 3 and the verdict is **genuine absence of structure — flat is correct**. `is_prose_form_header` fires on exactly 18 paragraphs across the 22 `ad_pgfn`/`adn_cst` documents and **every one is a signature** at upper-ratio 1.000; the 8 near-misses are ementas, portal stamps and signature fragments, with no section heading among them. 21 of 22 documents reject *nothing*, and 19 have a body of 0–3 blocks against `MIN_SECTIONS_FOR_FULL_CONFIDENCE = 3`. Unlike Cycle 3's genre there is no skeleton to declare: **no `section_res` is recommended for `ato_declaratorio`**. Recorded in [`docs/20260913_232034_ad_pgfn_adn_cst_flatness_investigation.md`](../../docs/20260913_232034_ad_pgfn_adn_cst_flatness_investigation.md) |
| **A-1.6** | 1 | 2026-09-13 | **Two segmentation defects found while measuring, deliberately not fixed (Q-4).** `adn_cst_20_19890821` and `adn_cst_29_19860625` have `body = None` because the front-matter hull absorbs their operative `DECLARA, em caráter normativo, …` paragraph, so the act's entire substance is classified as front matter; and `pn_cosit_1_20020924` has `body = None` despite **79 blocks** because segmentation read three ementa headings (`IRRF. RETENÇÃO EXCLUSIVA. RESPONSABILIDADE`, …) as *signatures*. Conservation holds in every case — every block lands somewhere — so no invariant fails and no test catches them. Both are **segmentation**, not hierarchy, and both would still be flat once repaired. Cycle 1 measures; a fix belongs in its own cycle with its own exit criteria |
| **A-3.3** | 3 | 2026-09-13 | **§1.2's flatness figures are rules-only-versus-refereed, and the plan does not say which.** §1.1's 107/233 came from a refereed run; the rules-only figure at the same commit is **115/233** (`sc_cosit` 58/109, not 52). §1.8 already records the referee moving 115 → 107, so the two are consistent — but a cycle whose headline is a flatness delta needs the baseline named. Per the user's decision, Cycle 3 measures **rules-only** (`--referee=none`), which is what the suite pins (§9.3) and what is reproducible offline. Result: **115 → 86** overall, `sc_cosit` **58 → 33** |
| **A-6.1** | 6 | 2026-09-14 | **§1.8's flatness consequence is stale: the referee now buys three documents, not eight.** The override table (74/50/3 across 53 documents) reproduces *exactly* offline — §1.8 is right about what the referee did. But it measured flatness **115 → 107** before Cycle 3 existed. Against Cycle 1's rules-only baseline of 86 the figure is **86 → 83**, and the three are `nota_pgfn_crj_1040_2015`, `parecer_pgfn_crj_701_2016`, `sc_cosit_200_20211214`. Five of §1.8's original eight are soluções de consulta now structured **rules-only** by A-3.1's `section_res`. Both measurements are correct at their own commit; the plan does not say which commit it measured — the same defect A-3.3 records about §1.2. *Decided with the user (Q-3)* |
| **A-6.2** | 6 | 2026-09-14 | **The referee dependency §1.8 warns about is closed, not merely noted.** The measuring run's 625 recorded answers are published as `tests/corpus_referee_fixtures/` (247 KB, all `deepseek-v4-flash`). Replaying all 233 documents through the existing `RefereeCache(…, read_only=True)` seam answers **684 of 694** questions with **zero network calls**, and two replays produce a byte-identical `DecisionsReport`. The 10 non-hits are **abstentions**, which `api.py` deliberately never caches; every one is `rule=nao → final=nao`, so no outcome depends on them — asserted, not assumed. Warm-cache referee overhead is **+0.2 ms/document**. *Cache location and scope decided with the user (Q-1, Q-2)* |
| **A-6.3** | 6 | 2026-09-14 | **§5.3 answered: the 74 `nao`→`secao` overrides should NOT become a rule.** 35 of the 74 sit on texts that also appear as *refusals* — `RELATÓRIO` 19 `secao` / 2 `nao`, `ORDEM DE INTIMAÇÃO` 7 / 1, and bare `I`/`II`/`III`/`IV` on both sides — so a text-keyed rule would fabricate 19 sections to rescue 35. The referee is reading position and neighbours (what `next_ctx` exists for, A-H.2), not applying a table. The 40 unambiguous confirmations are dominated by `FUNDAMENTOS` (17) and `CONCLUSÃO` (8), which A-3.1's `section_res` already admits **without a referee** — the learnable part is learned, and by declared profile data rather than a pattern fitted to 233 documents. Recorded in [`docs/20260914_112449_referee_override_rule_analysis.md`](../../docs/20260914_112449_referee_override_rule_analysis.md). *Decided with the user (Q-4)* |
| **A-6.4** | 6 | 2026-09-14 | **The measuring run's cache existed only in volatile scratch space.** The 625 entries plan §1.1 records were never in the repository; they survived in a job temporary directory that is deleted with the job. Publishing them was made this cycle's first action, before any other work, because every economic and reproducibility claim in Cycle 6 depends on data that could not have been regenerated without paying for the run again — and `--referee=api` needs a key this environment does not have |

Amendments to this plan are recorded here as `A-<cycle>.<n>`.
