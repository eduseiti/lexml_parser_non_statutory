# Cycle Status — Corpus 233 Hardening Plan

Plan: [`20260913_212337_corpus_233_hardening_plan.md`](../20260913_212337_corpus_233_hardening_plan.md)

> The plan was written on 2026-09-13 from a measuring run over the
> 233-document corpus at `../br-taxqa-r_v2.0/original/nao_articulados/`. See
> plan §1 for the evidence.
>
> **Cycle 4 is complete (2026-09-13)** — the first executed cycle, taken first
> per §3. It repairs the three `test_bare_checkout.py` failures §1.7 records,
> and **the suite is now fully green: 6 028 passed / 0 failed / 4 skipped / 2
> live-deselected.** The baseline table below is preserved as written, as the
> record of the state the plan was authored against.

| Cycle | Title | Date | State | Tests | Spec | Report |
|---|---|---|---|---|---|---|
| 1 | A truthful account of flatness | — | **not started** | — | — | — |
| 2 | URN completeness and identity collisions | 2026-09-13 | **complete** | 6052 pass / 0 fail / 4 skip / 2 live-deselected | [spec](20260913_222009_cycle_2_spec.md) | [report](20260913_222009_cycle_2_report.md) |
| 3 | A `solucao_consulta` profile | — | **not started** | — | — | — |
| 4 | Repair the bare-checkout harness | 2026-09-13 | **complete** | 6028 pass / 0 fail / 4 skip / 2 live-deselected | [spec](20260913_220540_cycle_4_spec.md) | [report](20260913_220540_cycle_4_report.md) |
| 5 | Batch robustness, negative cases | — | **not started** | — | — | — |
| 6 | Referee economics and reproducibility | — | **not started** | — | — | — |

Suggested order (plan §3): **4 → 2 → 3 → 1 → 6 → 5**.

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

Amendments to this plan are recorded here as `A-<cycle>.<n>`.
