---
name: dev-cycle
description: Implement one development cycle from a development plan in the dev/ folder (e.g. "implement Cycle 4b", "run dev-cycle for cycle 2 of the LexML plan"). Sets up the plan's cycle subfolder, reviews prior cycle results, reconciles mismatches with the user, expands the cycle into a detailed implementation + test spec, implements it with parallelism, tracks changes to existing features, and produces a final report. Use whenever the user asks to implement, execute, or continue a numbered development cycle from a plan document.
---

# Development Cycle Implementation

Implements exactly **one** cycle of a multi-cycle development plan, on top of whatever previous cycles already produced, leaving the repository green and fully documented.

## Inputs

Parse from the user's invocation:

| Input | Required | Notes |
|---|---|---|
| **Plan document** | yes | Path to a `.md` in `dev/`. If omitted and `dev/` holds exactly one plan, use it and say so. If several, ask which. |
| **Cycle id** | yes | E.g. `0`, `4`, `4b`, `6b`. Match case-insensitively against cycle headings. If omitted, list the cycles with their status (done / not started, per §1) and ask. |
| **Extra comments** | no | Additional constraints, scope changes, or focus areas from the user. These are **binding** and override the plan text where they conflict — record the conflict in the cycle spec rather than silently resolving it. |

**Cycle not found:** if the cycle id has no matching section in the plan, stop immediately. Report the exact cycle ids the plan does contain and finalize — do not guess a neighbouring cycle, and do not implement anything.

---

## Step 1 — Cycle workspace

The plan's workspace is a subfolder of `dev/` named after the plan file's stem:

```
dev/<plan-file-stem>/
```

e.g. `dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser/`.

- If it does **not** exist, create it — this is the first cycle for this plan.
- If it **does** exist, reuse it. Its contents are the record of prior cycles; read them in Step 2.

Inside it, each cycle owns files prefixed with the timestamp convention from `CLAUDE.md` (`date +%Y%m%d_%H%M%S`) and suffixed with the cycle id:

```
dev/<plan-stem>/
  YYYYMMDD_HHMMSS_cycle_<id>_spec.md      # Step 3c — expanded goals, plan, tests
  YYYYMMDD_HHMMSS_cycle_<id>_report.md    # Step 6  — final report
  YYYYMMDD_HHMMSS_cycle_<id>_changes.md   # Step 5  — only if existing features changed
  STATUS.md                               # running index of cycles: id, date, state, spec/report links
```

`STATUS.md` has no timestamp prefix (it is an index, continuously updated, not a dated log). Create it on the first cycle; append a row on every subsequent one.

Run `date +%Y%m%d_%H%M%S` once at the start and reuse that stamp for all files of this cycle.

---

## Step 2 — Read the prior state (3a)

Before writing anything:

1. Read `dev/<plan-stem>/STATUS.md` (if present) and every prior cycle's **report** — reports state what was actually built, which supersedes what the plan intended.
2. Read the prior cycle **change logs** (`*_changes.md`) — these record deviations from the plan that the current cycle must build on.
3. Inspect the actual code: source tree layout, `tests/`, `pyproject.toml`/build config, and run the existing test suite to establish a green baseline. **Record the baseline result** (pass/fail counts). If the baseline is already red, report that to the user and ask whether to fix it first or proceed — do not build on a red baseline silently.
4. Check `git log` and `git status` for uncommitted work from an interrupted cycle.

Summarise the inherited state in two or three sentences before moving on.

---

## Step 3 — Reconcile plan vs. reality (3b)

Compare what exists against what this cycle assumes. Look specifically for:

- **Missing prerequisites** — the cycle depends on a module/API/fixture a prior cycle was supposed to deliver but didn't, or delivered under a different name or shape.
- **Drifted interfaces** — a prior cycle implemented a dataclass, function signature, file layout, or CLI flag differently from the plan's snippet. The plan's code snippets are illustrative; the code is authoritative — but the divergence must be surfaced, not absorbed.
- **Contradicted assumptions** — a finding in the plan that prior implementation work disproved.
- **Scope overlap** — a prior cycle already implemented part of this cycle's deliverable.
- **Ambiguity in the cycle text itself** — an exit criterion that cannot be objectively checked, a test description with no unambiguous expected outcome, or a deliverable that could reasonably mean two different things.
- **Conflicts with the user's extra comments.**

**Rule: do not assume anything that is not absolutely clear.** For every open point or decision, ask the user before implementing. Batch the questions into one round using `AskUserQuestion` (up to 4 per call, multiple calls if needed), each with concrete options and a recommendation as the first option. Only proceed once every blocking question is answered.

Non-blocking uncertainties (cosmetic naming, internal helper structure, test file organisation) are yours to decide — note the decision in the spec, don't ask.

---

## Step 4 — Expand the cycle into a spec (3c)

Write `YYYYMMDD_HHMMSS_cycle_<id>_spec.md` in the plan subfolder before any implementation. It must contain:

1. **Header** — cycle id and title, date, plan document path, user's extra comments verbatim.
2. **Inherited state** — what prior cycles delivered that this cycle builds on (from Step 2).
3. **Reconciliation outcomes** — every question asked in Step 3 with the user's answer, and every non-blocking decision you made yourself.
4. **Expanded goals** — the plan's cycle bullets turned into concrete, checkable deliverables: exact modules/files to create or modify, exact public API (dataclasses, function signatures, CLI flags), exact output shapes. Where the plan is terse, expand it; where the plan is precise, quote it.
5. **Implementation plan** — ordered work items, each marked `[parallel]`, `[subagent]`, or `[sequential]`, with dependencies noted. Mark an item `[subagent]` when it meets the fan-out criteria in Step 5. This is what Step 5 executes.
6. **Test plan** — the heart of the spec. Two parts:
   - **New tests** for this cycle's features. Every test named, with its input, its expected outcome, and the plan bullet or exit criterion it discharges. Cover the cycle's own test list from the plan *plus* anything the expansion revealed. These become the cycle's contribution to the regression suite — write them to be re-runnable standalone, with no dependence on cycle-local scratch state.
   - **Reused regression tests** from previous cycles: name them explicitly and state that they must stay green. If a prior test must change, that is a Step 5 change requiring the escalation rules below.
7. **Exit criteria** — the plan's exit criterion for this cycle, restated as commands whose output decides pass/fail (e.g. `pytest tests/ -q` green; `N` samples validating).
8. **Risks** for this cycle specifically.

Tests live in `tests/` per `CLAUDE.md`, not in the `dev/` subfolder. The `dev/` subfolder holds documents only.

Show the user a short summary of the spec (goals + test plan headline) before implementing. If the user's invocation was a plain "implement cycle X", proceed after the summary; only stop for approval if Step 3 raised blocking questions or the spec materially expands the cycle's scope.

---

## Step 5 — Implement

Execute the implementation plan. Parallelise aggressively where it is safe, at two levels.

**Level 1 — batched tool calls (always).** Independent file reads, independent greps, and independent edits to *different* files go in one block. Sequence anything touching the same file, and anything whose interface another item consumes.

**Level 2 — subagent fan-out.** Dispatch work items to subagents (`Agent` tool, `general-purpose` unless a more specific type fits; `Explore` for read-only investigation) whenever the work genuinely decomposes. Good fan-out candidates:

- **Independent modules** in the same cycle — e.g. one agent per package under `src/`, one per emitter, one per profile, one per ingestion format.
- **Per-sample or per-fixture work** — golden generation, per-document validation, per-sample route verification across the 15 samples.
- **Test authoring alongside implementation** — one agent writing the new tests from the spec's test plan while another implements the module, since the spec already fixes the interface between them.
- **Investigation** — schema probing, reference-parser (`../lexml-parser-projeto-lei`) archaeology, corpus measurement. Use `Explore` for these; they are read-only.

Keep it correct:

- **Disjoint file ownership.** Two agents must never write the same file. Partition by file/module in the spec, and state each agent's owned paths in its prompt.
- **Brief each agent fully.** A subagent starts cold: give it the spec path, its exact deliverable, the files it owns, the interfaces it must conform to (verbatim signatures, not "see the plan"), the project conventions from `CLAUDE.md`, and the tests it must make pass. Have it report what it changed and its test results.
- **Sequential for the interface-defining item.** If several items consume one module's API, build that module first, then fan out the consumers.
- **Verify, don't trust.** Subagent reports are claims. Re-run the suite yourself after fan-out; the agent's word that "tests pass" is not evidence.
- **Escalation still applies to you.** A subagent must not decide a major change on its own — instruct each one to report a required major change back rather than making it. Step 5's confirmation rule is yours to enforce.
- **Don't fan out trivia.** A cycle that touches two small files is faster done inline. Fan out when items are genuinely independent and substantial.

Run tests as you go — per-module tests as each module lands, the full suite at the end, by you, after all agents have returned. Write code that matches the surrounding style of whatever prior cycles produced.

### Change tracking (Step 5 requirement)

During implementation and testing, **any change to an existing feature** — behaviour, signature, output shape, file layout, or an existing test — is recorded as you make it in `YYYYMMDD_HHMMSS_cycle_<id>_changes.md`, with:

| Field | Content |
|---|---|
| What changed | file + symbol |
| Before → after | the actual old and new behaviour |
| Why | which cycle goal or failing test forced it |
| Blast radius | other modules/tests affected |
| Plan impact | which plan section is now stale |

**Minor change** — internal refactor, added optional parameter, new branch that doesn't alter existing outcomes, test tightened without changing its meaning: make it, log it, continue.

**Major change** — anything that alters previously-delivered behaviour or output, removes/renames public API, changes an emitted artifact's shape, weakens or deletes an existing regression test, or contradicts a ratified decision in the plan: **stop and ask for confirmation before proceeding**, presenting the change, why it is forced, and the alternatives. Never weaken or delete a passing regression test to make new code pass without explicit confirmation.

### Keep the plan consistent

When a change makes the plan document stale, update the plan (`dev/<plan>.md`) itself so it stays the single source of truth: correct the affected section, and add or extend a short "Amendments" entry noting cycle, date, what changed, and why. Never silently rewrite a ratified decision — amend it visibly. Plan edits for major changes happen only after the user confirms.

Also update `STATUS.md` with this cycle's row and state.

---

## Step 6 — Final report

Write `YYYYMMDD_HHMMSS_cycle_<id>_report.md` in the plan subfolder:

1. **Summary** — cycle, date, one-paragraph outcome, and a plain verdict: complete / partially complete / blocked.
2. **What was built** — every file created or modified, with a line on its role. Public API as delivered. Note which items were fanned out to subagents and how the work was partitioned.
3. **Test results** — the actual command output: counts of new tests, reused regression tests, pass/fail/skip. Report failures honestly with their output; never describe a partially-passing suite as green. Coverage if the plan's exit criterion requires it.
4. **Exit criteria** — each one from the spec, marked met / not met, with the evidence that decides it.
5. **Changes to existing features** — full detail from the change log, majors flagged and their confirmations noted. State "none" explicitly if nothing changed.
6. **Plan updates** — what was amended in the plan document and why.
7. **Deviations and open items** — anything in the cycle deliberately not done, why, and what it blocks. Anything discovered that the next cycle must handle.
8. **Next cycle readiness** — what the next cycle inherits, and any prerequisite it now has.

Then give the user a condensed version in chat: verdict, test results, changes to existing features, open items, and paths to the spec/report.

---

## Guardrails

- **One cycle only.** Do not implement the next cycle because it looks small, even if the current one finished early. Say it's available and stop.
- **Baseline first.** Never build on a red suite without telling the user.
- **The plan is amendable, not disposable.** Divergence gets recorded, not hidden.
- **Ask rather than assume** on anything load-bearing — this is an explicit requirement of the cycle process, not optional caution.
- **Finish the whole cycle.** If part of it is genuinely blocked, complete everything else in full and state precisely what was left out and why.
