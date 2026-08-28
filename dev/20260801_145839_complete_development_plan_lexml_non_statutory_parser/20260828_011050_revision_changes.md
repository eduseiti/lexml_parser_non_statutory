# 2026-08-28 Plan Revision — Changes to existing features

- **Trigger:** `docs/20260827_111015_revised_plan_recursive_agrupamento_hierarquico_adoption.md`
- **Date:** 2026-08-28
- **Scope:** the plan document and this folder's index. **No source, test, golden or schema file was touched.**
- **Update record:** `docs/20260828_011050_plan_update_recursive_agrupamento_hierarquico.md`

This is not a cycle. It is a **plan revision** applied between cycles, recorded
in the cycle-changes format because it changes what later cycles are obliged to
build, and one delivered artefact's *interpretation*.

`python3 -m pytest tests/ -q` → **788 passed, 0 failed**, unchanged before and
after. Nothing delivered was altered, removed or weakened.

---

## Change 1 — the §2.1 encoding matrix becomes conditional, not absolute

| Field | Content |
|---|---|
| **What changed** | Plan §2.1 (re-scoped) and the future contract of `tests/unit/matrix_cases.py` / `tests/unit/test_schema_matrix.py`. **The test files themselves are untouched in this revision** — the change is scheduled into the Cycle 0 addendum (A-R.2), landing with Cycle 5b. |
| **Before → after** | Before: §2.1 asserted 16 absolute truths about "the LexML schemas", and `MatrixCase` carried `(row, encoding, fragment, expected, generico)`. After: §2.1 asserts 16 truths about **a named schema generation**, and `MatrixCase` will gain a `requires` field naming the capability a case depends on. A case whose capability is absent **skips with a reason** rather than failing. |
| **Why** | The repository now holds two schema generations — `lexml/` (shipped) and `lexml-proposed/` (the maintainers' unreleased change). A row like *"`AgrupamentoHierarquico` without articulated descendant → FAIL"* is true of the first and false of the second. Stated as an absolute it would be wrong half the time; stated per generation it stays the single executable statement of what the schemas permit. |
| **Blast radius** | None yet — no test changed. When A-R.2 lands, the 16 existing cases must return **identical verdicts under both generations** (that is the backward-compatibility claim of §2.10, and it is asserted rather than assumed), so the existing 52 matrix assertions should survive unmodified with skips added around new rows only. |
| **Plan impact** | §2.1 amended in place with a visible note; §2.10 and §2.11 added; the Cycle 0 addendum (A-R.2) schedules the work. |
| **Severity** | **moderate** — no behaviour changed today, but a delivered test's contract is redefined, and the redefinition is load-bearing for Cycle 5b. |

## Change 2 — Cycle 0's report is now partially historical

| Field | Content |
|---|---|
| **What changed** | Nothing in the file. `20260802_140857_cycle_0_report.md` is **left exactly as written**. |
| **Before → after** | No edit. |
| **Why** | Recorded because the report's line 13 claims the matrix is *"the empirical basis for the entire design"* and line 172 says Cycle 5's emitter *"must satisfy rows B, G, H, M and N, and must never produce C, D or O"*. Both remain **true of the flat `generico` emitter**, which is what Cycle 5 builds. Neither is true without qualification of the nested emitter: `generico-aninhado` produces encodings that row F declares invalid *under the shipped schemas*. Per the repository convention, **reports state what was actually built and are not rewritten**; the qualification belongs in the plan and in this file. |
| **Blast radius** | None. A reader who follows the CLAUDE.md order — STATUS.md, then the plan — meets the revision banner and §14 before reaching the report. |
| **Plan impact** | None beyond §2.1's amendment note. |
| **Severity** | **none** (no edit) — recorded for traceability. |

## Change 3 — `lexml-proposed/` and `build_proposed_schemas.py` enter the plan

| Field | Content |
|---|---|
| **What changed** | Plan header, §1, §2.10, §2.11, §10, §11.3, and STATUS.md's new *Schema generations* table now describe `lexml-proposed/` and `scripts/build_proposed_schemas.py`. |
| **Before → after** | Before: these existed in the repository (commit `a1b3124`) and in `CLAUDE.md`, but the plan did not mention them — the plan said only *"modifying the LexML schemas is out of scope"*. After: the plan states that `lexml/` stays byte-identical to upstream **and** that a *generated* second generation carries the maintainers' change, with the ship sequence in §11.3. |
| **Why** | The plan is the single source of truth for what later cycles build against. A directory that Cycle 5b validates against cannot be invisible to the plan. |
| **Blast radius** | Documentation only. `scripts/build_proposed_schemas.py --check` was confirmed passing; the generated schemas are current. |
| **Plan impact** | Additive throughout; no ratified decision reversed. |
| **Severity** | **minor** — the plan catches up with the repository. |

## Change 4 — Cycle 6b withdrawn; its round-trip reader relocated

| Field | Content |
|---|---|
| **What changed** | Plan Cycle 6b replaced by a withdrawal record; `render/articulado.py` removed from the §3 package layout; the *"synthetic articles mislead consumers"* risk retired in §10; §12 and STATUS.md updated. `hierarchy_from_xml()` moves to Cycle 7. |
| **Before → after** | Before: a fourth emitter, `articulado-sintetico`, synthesising `Artigo`/`Caput` from prose to obtain nesting, plus `MetadadoProprietario` provenance markers so the synthetic articles were not mistaken for real ones. After: dropped. Real nesting comes from §2.10 without asserting articulation the source lacks. |
| **Why** | The emitter's sole justification was *"nesting is only reachable by synthesising articles"*, and §2.10 falsifies the premise. Emitting a parecer's sections as `Artigo`s is precisely the misreading Cycle 4's quotation guard exists to prevent — committed deliberately, on output. **User-confirmed on 2026-08-28: dropped, not deferred.** |
| **Blast radius** | None — Cycle 6b was never started, so no code, test or golden exists to remove. The removal is entirely prospective. |
| **Plan impact** | One cycle removed; one deliverable (`hierarchy_from_xml()`) relocated to Cycle 7, where it becomes the oracle proving the two surviving emitters agree. Reinstatement conditions are recorded rather than deleted. |
| **Severity** | **moderate** — a planned deliverable is cancelled, by user decision. |

## Change 5 — our own recursive-`Agrupamento` proposal withdrawn

| Field | Content |
|---|---|
| **What changed** | Plan §11 rewritten from *"The Recursive `Agrupamento` Proposal"* to *"Engagement with the LexML Community"*. |
| **Before → after** | Before: the plan carried our proposal to make `Agrupamento` recursive by adding `containerElements` to `blocksreq`, to be sent to the maintainers. After: that proposal is **withdrawn**; §11.1 records why it was inferior; §11.2 is the reply endorsing the maintainers' change; §11.3 is the ship sequence. |
| **Why** | The maintainers proposed a better change by a different route. `AgrupamentoHierarquico` was **already** recursive and `PartePrincipal` already accepted it — recursion was never missing, prose-bearing leaves were. Ours also risked letting prose leak toward the statutory model; theirs confines the change to the aggregator and grants `Rotulo`/`NomeAgrupador` for free. Circulating two competing proposals would create confusion. |
| **Blast radius** | Documentation only. The original text survives in `docs/20260801_142630_…` §6, and §13 says so. |
| **Plan impact** | §11 replaced. The §3.7 refinement from the revision document is carried as **§11.2 item 4 — a suggestion to forward, never something we build against.** |
| **Severity** | **moderate** — a ratified plan section is reversed, visibly and with reasons. |

## Change 6 — reversibility, Rule A and the invariant set

| Field | Content |
|---|---|
| **What changed** | Plan §9.2 invariants: #3 (reversibility) and #6 (Rule A) reworded; **#11 (cross-emitter equivalence) and #12 (capability honesty) added**. §9.1 gains two test layers. |
| **Before → after** | #3 before: *"hierarchy reconstructable from output alone (`id` path or native nesting)"*. After: names which emitter uses which channel. #6 before: an unqualified requirement. After: *required of the flat emitter; structurally guaranteed by the nested one*, where a gap is a malformed tree rather than a silent breadcrumb bug. |
| **Why** | Rule A exists because a missing intermediate `id` silently truncated a breadcrumb in the original XSLT experiment. Under nesting that failure mode cannot be expressed. Stating it as still-required would demand machinery against an impossible bug; deleting it would break the flat emitter. It is scoped instead. |
| **Blast radius** | No delivered test asserts Rule A yet (Cycle 5 is not started), so nothing to revise. |
| **Plan impact** | §9.1, §9.2 amended; the new invariants bind Cycles 5b, 7 and 9. |
| **Severity** | **minor** — scoping and addition, no invariant weakened. |

---

## What was deliberately *not* changed

| Area | Why untouched |
|---|---|
| `src/`, `tests/`, `tests/golden/` | This is a plan revision. No cycle was executed. 788 tests pass identically before and after. |
| `lexml/` | Byte-identical to upstream, always. |
| `lexml-proposed/`, `scripts/build_proposed_schemas.py` | Already correct; `--check` passes. Verified by diff to carry the maintainers' change verbatim and nothing else. |
| Cycles 0, 1, 2 specs, reports and changes files | Historical records of what was built. The convention is that reports are not rewritten. |
| Cycles 1, 2, 3, 4, 5 content | Genuinely unaffected. Ingestion, metadata, URN, profiles, front/back matter, hierarchy inference and the flat emitter are all schema-generation-independent — the payoff of the rendering-agnostic model. |
| §0 ratified decisions | None reversed. The four decisions concern routing, jurisprudence scope, LLM support and the §7.1 table; the schema change touches none of them. |
| §4.4 route table | Routing is about what a document *is*, not how it is rendered. A clarifying note was added (A-R.7); no route changed. |
