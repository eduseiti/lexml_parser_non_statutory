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
| 0+ | ↳ addendum: schema-generation awareness + capability probe (A-R.2) | 2026-08-28 | **partial** — probe landed in 4b (A-4b.1); matrix `requires`/skip still with 5b | (in 4b) | — | — |
| 1 | DOCX ingestion → `StyledDoc` | 2026-08-02 | **complete** | 373 pass / 0 fail | [spec](20260802_224308_cycle_1_spec.md) | [report](20260802_224308_cycle_1_report.md) |
| 2 | Metadata, URN and profiles | 2026-08-02 | **complete** | 788 pass / 0 fail | [spec](20260802_231852_cycle_2_spec.md) | [report](20260802_231852_cycle_2_report.md) |
| 3 | Front/back matter segmentation | 2026-08-28 | **complete** | 1681 pass / 0 fail | [spec](20260828_011822_cycle_3_spec.md) | [report](20260828_011822_cycle_3_report.md) |
| 4 | Hierarchy inference | 2026-08-28 | **complete** | 2462 pass / 0 fail | [spec](20260828_111240_cycle_4_spec.md) | [report](20260828_111240_cycle_4_report.md) |
| 4b | Routing + LLM referee + telemetry | 2026-08-28 | **complete** | 3135 pass / 0 fail | [spec](20260828_161250_cycle_4b_spec.md) | [report](20260828_161250_cycle_4b_report.md) |
| 5 | Emitter `generico` (flat, **default**) | — | not started | — | — | — |
| **5b** | **Emitter `generico-aninhado` (nested, opt-in)** — *new, A-R.3* | — | not started | — | — | — |
| 6 | Emitter `norma` + `Anexo` split | — | not started | — | — | — |
| ~~6b~~ | ~~Emitter `articulado-sintetico` + round-trip~~ | — | **withdrawn 2026-08-28 (A-R.6)** | — | — | — |
| 7 | Segmentation output | — | not started | — | — | — |
| 8 | Generalisation, robustness, CLI | — | not started | — | — | — |
| 9 | Regression consolidation and corpus scale-out | — | not started | — | — | — |

Cycle order: `0, 1, 2, 3, 4, 4b ✅ → 5, 5b, 6, 7, 8, 9`.
Cycle 6b's round-trip reader (`hierarchy_from_xml()`) is **retained** and relocated to Cycle 7.

## Change logs

| Cycle | Changes to existing features |
|---|---|
| 0 | [changes](20260802_140857_cycle_0_changes.md) — no delivered behaviour changed (first cycle); two documented divergences from the planning documents, both agreed with the user |
| 1 | [changes](20260802_224308_cycle_1_changes.md) — no delivered behaviour changed (additive cycle); `python-docx` floor raised to `>=1.1`; three plan corrections, all agreed with the user |
| 2 | [changes](20260802_231852_cycle_2_changes.md) — no delivered behaviour changed (additive cycle); `regen_goldens.py` generalised to multiple golden kinds; `.gitignore` added; four plan amendments, all agreed with the user. **Includes an incident record: a subagent edited `src/` against instruction; mutations were transient, verified reverted, and all four are now covered by failing-on-mutation tests** |
| 3 | [changes](20260828_011822_cycle_3_changes.md) — no delivered behaviour changed (additive cycle); `DocumentProfile` gains three pattern fields, all defaulting to `()`; `regen_goldens.py` gains a third golden kind; five plan amendments. **Two changes were considered and deliberately rejected as major: extending Cycle 0's `matrix_cases.py`, and 'correcting' plan §4.3 — which re-validation showed is correct as written** |
| 4 | [changes](20260828_111240_cycle_4_changes.md) — no delivered behaviour changed (additive cycle); `model/__init__.py` gains 10 exports from the new `nodes` module; `regen_goldens.py` gains a fourth golden kind; six plan amendments. **One change deliberately rejected as major: capturing Word's `numFmt` on `StyledPara`, which would rewrite all 15 Cycle 1 `styled` goldens. Three defects in this cycle's own code were found by its tests and fixed — one of them, silently dropped nested list items, was unreachable from the corpus** |
| 4b | [changes](20260828_161250_cycle_4b_changes.md) — no delivered behaviour changed (additive cycle); `validate/schema.py` gains keyword-only `generation` + `probe_capabilities()`, `validate/__init__.py` gains 9 exports, `regen_goldens.py` gains a fifth golden kind; six plan amendments. **One change rejected as major: forcing §7.4's `agreed + overrode == flagged` identity, which is false under the suite's own `--referee=none` default — the plan was amended instead. Three defects in this cycle's own code were found and fixed — two reported by a test-authoring subagent under "report, do not fix", and one, `agreed` counting a disagreeing referee as agreeing, found by a mutation sweep. Four of 27 mutations initially survived, all in branches the 15-sample corpus cannot reach** |
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

| A-3.1 | 3 | Front/back matter needs **two renderings**: `ParteInicial`/`ParteFinal` exist only in `HierarchicalStructure` and are rejected inside `DocumentoGenerico`, where 14 of 15 samples live. Both renderings probed valid on both schemas ×15 |
| A-3.2 | 3 | `LocalDataFecho` and `FormulaPromulgacao` are `textoSimplesType` — they require an `id` **and** `<p>` wrapping; `Epigrafe`/`Ementa` are `inlineReq` and require an `id` but take text directly. §4.3's snippet is unaffected and was re-validated as correct |
| A-3.3 | 3 | Annex detection is **allowlisted per profile**. An ungated `^ANEXO` rule amputates 28 blocks off `sumula_stj_125`, whose bare `ANEXO` paragraph is not an annex. `DocumentProfile` gains `enacting_res`, `annex_res`, `closing_res` |
| A-3.4 | 3 | `segment/fields.py` deliberately **not built** — Cycle 2's allowlist-gated capture (A-2.2) is re-exported rather than reimplemented |
| A-3.5 | 3 | Every signature block is recorded, in order (`parecer_93` and `pn_cst_38` carry two regions). `FrontMatter.span` is the **contiguous hull**, and `BackMatter.trailing` absorbs closing notes, so the parts form a **partition** — text conservation as arithmetic, asserted ×15 |

| A-4.1 | 4 | The indent discriminator is **declared-vs-inherited**, not deviation: `parecer_93`'s quote band (2908) is one twip *below* the modal body indent (2909), which is *inherited from the style* while every quoted paragraph *declares* its own. Two band rules, `deviation` and `declared`. Corollary: **a paragraph Word declares a heading is never quoted** — without it `sumula_stj_125` loses a level of structure |
| A-4.2 | 4 | Three negative rules the grammar needs, each forced by a real paragraph: a **zero or zero-padded component** is not an ordinal (`2.08.30.00`, `06.12`); an **orphan** dotted label is not a label (`1.24.20.25`), refused by the document rather than the grammar; a **top-level numeric series must start at 1 or 2 and step by ≤3** or the whole series is rejected (`parecer_93`'s `1, 11, 111, 46, 194, 74`). Plus: a **solitary** roman/alpha/ordinal label is not an enumeration |
| A-4.3 | 4 | **Numbered-container demotion.** `sumula_stj_125`'s 38 same-level headings group into 7 cases × 31 parts, read from whether a heading carries its own identifier — Word records no difference between them. Three guards; declines on `CARNE_LEAO` and on `port_mf_277`'s annex. *Decided with the user* |
| A-4.4 | 4 | Named units (`Súmula CARF nº 1`) are a **document-level series**, not a grammar rule — ≥3 whole-paragraph occurrences with increasing numbers. This is what stops `Lei nº 12.618` from ever parsing as a label. The sibling-gap limit does not apply to a unit series (the annex runs 1, 3, 4 … 33, 40 …) |
| A-4.5 | 4 | The deliverable is a **`HierarchyDoc`**: body *and* each annex, discharging **A-R.8** a cycle early — `port_mf_277`'s `ANEXO ÚNICO` gains 65 real sections. *Decided with the user* |
| A-4.6 | 4 | **No sample has a contiguous multi-level Word list**, so `ilvl` nesting is tested by a synthetic fixture (the A-1.3 precedent). It caught a real bug on its first run: the implementation dropped every nested item |

| A-4b.1 | 4b | The **capability probe was pulled forward** from the Cycle 0 addendum, because A-R.7's `nested_unavailable` blocker needs a real diagnostic. `validate/schema.py` gains keyword-only `generation` on `load_schema`/`load_schemas`/`validate`/`validate_all`, plus `probe_capabilities()`. The probe document is **not** Cycle 0's matrix case E: case E wraps a bare `<p>`, which `lexml-proposed/` also rejects — the maintainers' change adds `Agrupamento` and `Bloco` to the choice, not `p`. *Decided with the user* |
| A-4b.2 | 4b | The route turns on **four gates** — `articles_own ≥ 1`, monotonic series, `coverage ≥ 0.6` measured *after the annex split*, no vetoing blocker. `articles_own = found − quoted` is the discriminator, and `port_mf_277` is the only sample with a non-zero value. §4.1's `blockers` retyped `list[str]` → `tuple[Blocker, ...]`, because a bare string cannot carry A-R.7's veto/no-veto distinction |
| A-4b.3 | 4b | The corpus flags exactly **four** decisions — `par_cosit_26` p#46/p#47/p#53 and `parecer_93` p#36. 415 paragraphs and 25 quoted articles generate **one** referee question, because the declared quote band carries the other 24 |
| A-4b.4 | 4b | §7.4's `agreed + overrode == flagged` is **false under `--referee=none`**, which §9.3 pins for the whole suite. Corrected to `agreed + overrode + overruled + abstained == consulted`, with `consulted ≤ flagged`. **`overruled` is a fourth bucket and it is reachable**: a referee that answers, contradicts the rule and is refused the override has neither agreed nor overridden, and folding it into `agreed` manufactures the exact evidence §7.4 uses to justify consulting the referee *less* |
| A-4b.5 | 4b | The recorded fixtures are **hand-authored** and documented as such per file, with a refresh command. They assert the referee **agrees** with a rule verdict that is already correct — a wrong fixture would surface as a spurious override and a changed route, not a silent pass. *Decided with the user* |
| A-4b.6 | 4b | Invariant #9 asserted as an **attack**: an adversarial referee answering "own" to every question changes no sample's route. On `par_cosit_26` it genuinely overrides three verdicts and the monotonicity gate holds the route anyway |

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
python3 -m lexml_nonstat.routing --decisions-report samples/*.docx   # Cycle 4b
```

The referee defaults to `none` everywhere and the suite pins it (§9.3): nothing
here makes a network call.
