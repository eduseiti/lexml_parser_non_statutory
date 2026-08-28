# Cycle Status — LexML Parser for Non-Statutory Documents

Plan: [`20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`](../20260801_145839_complete_development_plan_lexml_non_statutory_parser.md)

> **Plan revised 2026-08-28** to adopt the LexML maintainers' recursive
> `AgrupamentoHierarquico` change. Cycles 0–2 are **complete and unaffected** —
> no delivered work was invalidated. Cycle **5b** is new, Cycle **6b** is
> **withdrawn**, and Cycles 0, 4b, 6, 7, 8, 9 carry amendments.
> See plan §14 (amendment log), §2.10 (the change), and the update record
> [`docs/20260828_…_plan_update_recursive_agrupamento_hierarquico.md`](../../docs/20260828_011050_plan_update_recursive_agrupamento_hierarquico.md).

| Cycle | Title | Date | State | Tests | Spec | Report |
|---|---|---|---|---|---|---|
| 0 | Scaffolding and the schema harness | 2026-08-02 | **complete** | 107 pass / 0 fail | [spec](20260802_140857_cycle_0_spec.md) | [report](20260802_140857_cycle_0_report.md) |
| 0+ | ↳ addendum: schema-generation awareness + capability probe (A-R.2) | — | not started — *lands with 5b* | — | — | — |
| 1 | DOCX ingestion → `StyledDoc` | 2026-08-02 | **complete** | 373 pass / 0 fail | [spec](20260802_224308_cycle_1_spec.md) | [report](20260802_224308_cycle_1_report.md) |
| 2 | Metadata, URN and profiles | 2026-08-02 | **complete** | 788 pass / 0 fail | [spec](20260802_231852_cycle_2_spec.md) | [report](20260802_231852_cycle_2_report.md) |
| 3 | Front/back matter segmentation | — | not started | — | — | — |
| 4 | Hierarchy inference | — | not started | — | — | — |
| 4b | Routing + LLM referee + telemetry | — | not started | — | — | — |
| 5 | Emitter `generico` (flat, **default**) | — | not started | — | — | — |
| **5b** | **Emitter `generico-aninhado` (nested, opt-in)** — *new, A-R.3* | — | not started | — | — | — |
| 6 | Emitter `norma` + `Anexo` split | — | not started | — | — | — |
| ~~6b~~ | ~~Emitter `articulado-sintetico` + round-trip~~ | — | **withdrawn 2026-08-28 (A-R.6)** | — | — | — |
| 7 | Segmentation output | — | not started | — | — | — |
| 8 | Generalisation, robustness, CLI | — | not started | — | — | — |
| 9 | Regression consolidation and corpus scale-out | — | not started | — | — | — |

Cycle order: `0, 1, 2 ✅ → 3, 4, 4b, 5, 5b, 6, 7, 8, 9`.
Cycle 6b's round-trip reader (`hierarchy_from_xml()`) is **retained** and relocated to Cycle 7.

## Change logs

| Cycle | Changes to existing features |
|---|---|
| 0 | [changes](20260802_140857_cycle_0_changes.md) — no delivered behaviour changed (first cycle); two documented divergences from the planning documents, both agreed with the user |
| 1 | [changes](20260802_224308_cycle_1_changes.md) — no delivered behaviour changed (additive cycle); `python-docx` floor raised to `>=1.1`; three plan corrections, all agreed with the user |
| 2 | [changes](20260802_231852_cycle_2_changes.md) — no delivered behaviour changed (additive cycle); `regen_goldens.py` generalised to multiple golden kinds; `.gitignore` added; four plan amendments, all agreed with the user. **Includes an incident record: a subagent edited `src/` against instruction; mutations were transient, verified reverted, and all four are now covered by failing-on-mutation tests** |
| — | **2026-08-28 plan revision** — [changes](20260828_011050_revision_changes.md) · [update record](../../docs/20260828_011050_plan_update_recursive_agrupamento_hierarquico.md). Plan document only; **no code, tests or goldens were touched, and the 788 tests remain green.** The revision is scheduled work, not delivered work |

## Plan amendments

### Cycle amendments (from executing cycles)

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

### Revision amendments (2026-08-28 — schema change adoption)

Source: [`docs/20260827_111015_revised_plan_recursive_agrupamento_hierarquico_adoption.md`](../../docs/20260827_111015_revised_plan_recursive_agrupamento_hierarquico_adoption.md).
Full text in plan **§14**.

| ID | Section(s) | Summary |
|---|---|---|
| A-R.1 | §2.1, §2.10 | §2.1 re-scoped to *the schemas as shipped* — no longer absolute. New §2.10 records the maintainers' prose-bearing recursive `AgrupamentoHierarquico`, verified backward compatible (16/16 matrix cases unchanged) and **not yet released** |
| A-R.2 | §2.11, Cycle 0 addendum, §9 | Schema capabilities are **probed, never assumed**. `validate/schema.py` gains a second generation (`lexml-proposed/`) and `probe_capabilities()`; matrix cases gain `requires` and **skip rather than fail**. New invariant #12 |
| A-R.3 | §5.2, **Cycle 5b**, §9.2 | New nested emitter `generico-aninhado` and new Cycle 5b. New invariant #11 — cross-emitter text and URN equivalence |
| A-R.4 | §5.4 | Three binding constraints on the nested emitter: subsections-before-prose; ≥1 non-`AH` child (`<Bloco nome="vazio"/>`); prose needs an `Agrupamento` wrapper |
| A-R.5 | §6.1, §6.2, Cycle 7 | `segments_from_nested_xml()` + `segment_generico_aninhado.xsl`; the oracle becomes **three-way** (model / flat XML / nested XML) |
| A-R.6 | §11, Cycle 6b, §10, §12 | **Cycle 6b withdrawn** — `articulado-sintetico` dropped, round-trip reader relocated to Cycle 7. **Our own recursive-`Agrupamento` proposal withdrawn** in favour of the maintainers'; §11 becomes the engagement plan |
| A-R.7 | Cycle 4b, §4.4 | Blocker reason `nested_unavailable`. **Routing decisions unchanged** — `route=generico` names a routing decision, not an emitter |
| A-R.8 | Cycle 6 | Annex bodies may use the nested form when the capability is present — `port_mf_277`'s `ANEXO ÚNICO` gains real structure |
| A-R.9 | Cycles 8, 9 | `--emitter=generico-aninhado`; new `capabilities` CLI command; nested goldens and cross-emitter equivalence in the regression suite; **suite must stay green against `lexml/` alone** |

### Decisions taken with the user during the 2026-08-28 revision

1. **Cycle 6b is dropped**, not deferred. Its round-trip reader is retained and relocated to Cycle 7.
2. **`lexml-proposed/` is the patched-schema location**, replacing the revision document's proposed `tests/fixtures/schemas/`. Verified by diff: it carries the maintainers' change *verbatim and nothing else*.
3. **The maintainers' proposal prevails.** The §3.7 refinement is *ours* and is **forwarded upstream as a suggestion only**; the emitter is built against the maintainers' change as written and absorbs the ordering constraint. No third "refined" schema generation is produced.

## Schema generations

| Directory | Origin | Status | Rule |
|---|---|---|---|
| `lexml/` | upstream, vendored | shipped | **byte-identical to upstream, never modified** — that is what makes drift detectable |
| `lexml-proposed/` | *generated* by `scripts/build_proposed_schemas.py` | maintainers' change, **unreleased** | never hand-edited; `--check` verifies it is current |

The flat `generico` emitter targets the former and stays default; `generico-aninhado` targets the latter and is opt-in behind the capability probe until upstream ships the change (plan §11.3).

## Running the suite

```bash
python3 -m pytest tests/ -q                        # from the repository root
python3 scripts/build_proposed_schemas.py --check  # verify generated schemas current
```
