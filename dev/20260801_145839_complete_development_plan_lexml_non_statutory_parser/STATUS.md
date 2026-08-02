# Cycle Status — LexML Parser for Non-Statutory Documents

Plan: [`20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`](../20260801_145839_complete_development_plan_lexml_non_statutory_parser.md)

| Cycle | Title | Date | State | Tests | Spec | Report |
|---|---|---|---|---|---|---|
| 0 | Scaffolding and the schema harness | 2026-08-02 | **complete** | 107 pass / 0 fail | [spec](20260802_140857_cycle_0_spec.md) | [report](20260802_140857_cycle_0_report.md) |
| 1 | DOCX ingestion → `StyledDoc` | 2026-08-02 | **complete** | 373 pass / 0 fail | [spec](20260802_224308_cycle_1_spec.md) | [report](20260802_224308_cycle_1_report.md) |
| 2 | Metadata, URN and profiles | — | not started | — | — | — |
| 3 | Front/back matter segmentation | — | not started | — | — | — |
| 4 | Hierarchy inference | — | not started | — | — | — |
| 4b | Routing + LLM referee + telemetry | — | not started | — | — | — |
| 5 | Emitter `generico` | — | not started | — | — | — |
| 6 | Emitter `norma` + `Anexo` split | — | not started | — | — | — |
| 6b | Emitter `articulado-sintetico` + round-trip | — | not started | — | — | — |
| 7 | Segmentation output | — | not started | — | — | — |
| 8 | Generalisation, robustness, CLI | — | not started | — | — | — |
| 9 | Regression consolidation and corpus scale-out | — | not started | — | — | — |

## Change logs

| Cycle | Changes to existing features |
|---|---|
| 0 | [changes](20260802_140857_cycle_0_changes.md) — no delivered behaviour changed (first cycle); two documented divergences from the planning documents, both agreed with the user |
| 1 | [changes](20260802_224308_cycle_1_changes.md) — no delivered behaviour changed (additive cycle); `python-docx` floor raised to `>=1.1`; three plan corrections, all agreed with the user |

## Plan amendments

| ID | Cycle | Summary |
|---|---|---|
| A-0.1 | 0 | Offline harness needs **three** stubs (`xml`, `xlink`, `mathml`), not one, and uses a resolver rather than rewriting `lexml/*.xsd` in place |
| A-1.1 | 1 | The `parecer_93` indent discriminator is **quote band vs small band**, not vs "modal 0" — the modal *is* 2908. `StyledPara` keeps both `indent_direct` and `indent_effective`. **Load-bearing for Cycle 4** |
| A-1.2 | 1 | Struck runs dropped, soft breaks split, hyperlink `href` captured — three constructs present in the samples but absent from the plan's deliverable list |
| A-1.3 | 1 | The NFC test cannot be written against the samples (all are already NFC); synthetic fixture + corpus tripwire instead |
| A-1.4 | 1 | "Ingests losslessly" discharged by a multiset text-conservation test, not by golden equality alone |

## Running the suite

```bash
python3 -m pytest tests/ -q          # from the repository root
```
