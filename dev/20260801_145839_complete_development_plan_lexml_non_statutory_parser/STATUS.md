# Cycle Status — LexML Parser for Non-Statutory Documents

Plan: [`20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`](../20260801_145839_complete_development_plan_lexml_non_statutory_parser.md)

| Cycle | Title | Date | State | Tests | Spec | Report |
|---|---|---|---|---|---|---|
| 0 | Scaffolding and the schema harness | 2026-08-02 | **complete** | 107 pass / 0 fail | [spec](20260802_140857_cycle_0_spec.md) | [report](20260802_140857_cycle_0_report.md) |
| 1 | DOCX ingestion → `StyledDoc` | 2026-08-02 | **complete** | 373 pass / 0 fail | [spec](20260802_224308_cycle_1_spec.md) | [report](20260802_224308_cycle_1_report.md) |
| 2 | Metadata, URN and profiles | 2026-08-02 | **complete** | 788 pass / 0 fail | [spec](20260802_231852_cycle_2_spec.md) | [report](20260802_231852_cycle_2_report.md) |
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
| 2 | [changes](20260802_231852_cycle_2_changes.md) — no delivered behaviour changed (additive cycle); `regen_goldens.py` generalised to multiple golden kinds; `.gitignore` added; four plan amendments, all agreed with the user. **Includes an incident record: a subagent edited `src/` against instruction; mutations were transient, verified reverted, and all four are now covered by failing-on-mutation tests** |

## Plan amendments

| ID | Cycle | Summary |
|---|---|---|
| A-0.1 | 0 | Offline harness needs **three** stubs (`xml`, `xlink`, `mathml`), not one, and uses a resolver rather than rewriting `lexml/*.xsd` in place |
| A-1.1 | 1 | The `parecer_93` indent discriminator is **quote band vs small band**, not vs "modal 0" — the modal *is* 2908. `StyledPara` keeps both `indent_direct` and `indent_effective`. **Load-bearing for Cycle 4** |
| A-1.2 | 1 | Struck runs dropped, soft breaks split, hyperlink `href` captured — three constructs present in the samples but absent from the plan's deliverable list |
| A-1.3 | 1 | The NFC test cannot be written against the samples (all are already NFC); synthetic fixture + corpus tripwire instead |
| A-1.4 | 1 | "Ingests losslessly" discharged by a multiset text-conservation test, not by golden equality alone |
| A-2.1 | 2 | `parecer_93`'s `2018-12-28` is a **header stamp**, not the epigraph (which carries no date) and not the signature (19/12). Extraction uses an epigraph→header→signature→filename chain, recording `date_source`. A bare 4-digit run is **not** a date — without the `de` cue, `PORTARIA MF nº 277` parses as year 277 |
| A-2.2 | 2 | `MetadadoProprietario` capture is **allowlist-gated per profile**: a naive `LABEL:` rule captures `Advogados:`×7, `Relator:`, `Some-se:` from `sumula_stj_125` as metadata. The plan's 4-field list is extended by a 15-sample census |
| A-2.3 | 2 | 4 samples cannot yield a complete URN; best-effort URN + `complete`/`missing` flags, never raising. Sentinels must survive `parse_urn`, so `UrnDate` accepts year 0 (`is_unknown`). Known limit: `is_valid_urn` checks date *shape*, not calendar validity |
| A-2.4 | 2 | `nota_tecnica` deliberately **not** built — no sample exists, so no test could discharge it. Six profiles registered |

## Running the suite

```bash
python3 -m pytest tests/ -q          # from the repository root
```
