# Cycle Status — Corpus 233 Hardening Plan

Plan: [`20260913_212337_corpus_233_hardening_plan.md`](../20260913_212337_corpus_233_hardening_plan.md)

> **No cycle of this plan has been executed.** The plan was written on
> 2026-09-13 from a measuring run over the 233-document corpus at
> `../br-taxqa-r_v2.0/original/nao_articulados/`. See plan §1 for the evidence.

| Cycle | Title | Date | State | Tests | Spec | Report |
|---|---|---|---|---|---|---|
| 1 | A truthful account of flatness | — | **not started** | — | — | — |
| 2 | URN completeness and identity collisions | — | **not started** | — | — | — |
| 3 | A `solucao_consulta` profile | — | **not started** | — | — | — |
| 4 | Repair the bare-checkout harness | — | **not started** | — | — | — |
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

None yet. Amendments to this plan are recorded here as `A-<cycle>.<n>` once
cycles begin.
