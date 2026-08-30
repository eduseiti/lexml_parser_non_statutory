# Referee configuration amendment — report

**Date:** 2026-08-30
**Plan:** [`20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`](../20260801_145839_complete_development_plan_lexml_non_statutory_parser.md)
**Spec:** [`20260830_184109_referee_configuration_amendment_spec.md`](20260830_184109_referee_configuration_amendment_spec.md)
**Changes:** [`20260830_184109_referee_configuration_amendment_changes.md`](20260830_184109_referee_configuration_amendment_changes.md)
**Source record:** [`docs/20260830_144415_referee_setup_verification_cli_usage_and_base_url_gap.md`](../../docs/20260830_144415_referee_setup_verification_cli_usage_and_base_url_gap.md)

**Verdict: complete.** 5261 passing, 0 failing, 4 skipped, 2 live-deselected.
All 135 goldens byte-identical. **Cycle 9 is not started**, as instructed.

---

## 1. Summary

Adopted proposals **P-1a, P-2, P-3 and P-4** from the 2026-08-30 investigation
record, as an interstitial amendment rather than a cycle. Two things were found
during the work that the record had not:

1. **The suite was already red** — 7 failing tests, caused by the
   post-Cycle-8 `DEFAULT_MODEL` refresh moving the referee cache key out from
   under the four recorded fixtures. Repaired first, before any new work.
2. **`--referee` was inert across the entire unified CLI** — accepted by
   `parse` and `decisions-report`, built, then discarded. No subcommand of
   `lexml_nonstat` could consult a referee at all. Escalated as a major change,
   approved, and repaired.

The second finding is why this amendment matters more than its size suggests:
P-1a's whole purpose is making a non-DeepSeek provider reachable, and without
that repair the new flag would have configured a referee that `cli.py` never
used.

---

## 2. What was built

| File | Change |
|---|---|
| `src/lexml_nonstat/cli.py` | `--referee-base-url` added to the shared `_add_referee`; `--referee-model`/`--referee-base-url` default from the environment; `_build_referee` passes `base_url` for `api` only; `_cmd_parse` and `_cmd_decisions_report` now **pass the referee to `build_model`** |
| `src/lexml_nonstat/routing/__main__.py` | the same two flags and the same construction, keeping the mirror its docstring promises |
| `src/lexml_nonstat/model/document.py` | `build_model(..., referee=None)`, threaded into `assess_viability`; docstring rewritten to say why the parameter exists |
| `tests/referee_fixtures/*.json` | four fixtures re-keyed to `deepseek-v4-flash` |
| `tests/referee_fixtures/README.md` | new key table, re-keying note, corrected refresh command |
| `tests/unit/test_cli.py` | **+11 tests** for referee configuration and the inert-flag repair |
| `tests/unit/test_referee_live.py` | **new** — 2 live smoke tests, double-guarded |
| `README.md` | **new** — five sections, per P-3 |
| `docs/20260829_144555_…` | dated correction footnote (P-4) |
| plan `.md` | new §15 amendment log (A-C.1–A-C.5); Cycle 8 deliverable and E-7 annotated |
| `STATUS.md` | interstitial row, change-log entry, cycle-order note |

### Public API delivered

```python
build_model(doc, *, filename=None, profile=None, metadata=None,
            segmentation=None, hierarchy=None, viability=None, log=None,
            referee=None)          # ← new, default None
```

```
--referee-base-url URL     # parse, decisions-report, and routing
                           # default: $LEXML_REFEREE_BASE_URL, then api.DEFAULT_BASE_URL
--referee-model ID         # default now: $LEXML_REFEREE_MODEL
```

Precedence: **flag > environment > `api.DEFAULT_*`**.

No subagents were used — the work was two source files plus tests, too
interdependent to partition usefully.

---

## 3. Test results

```
$ python3 -m pytest tests/ -q
5261 passed, 4 skipped, 2 deselected in 30.82s

$ python3 scripts/regen_goldens.py
15 sample(s) × 9 kind(s): 0 new, 0 changed, 135 unchanged

$ python3 scripts/build_proposed_schemas.py --check
lexml-proposed/ is current (1 patch(es) applied).

$ python3 -m pytest tests/unit/test_referee_live.py -m live -q
2 skipped                      # no key exported in this shell
```

| Stage | Result |
|---|---|
| Baseline (inherited) | **7 failed**, 5243 passed, 4 skipped |
| After the fixture re-key | 5250 passed — Cycle 8's exact count restored |
| After the full amendment | **5261 passed**, 4 skipped, 2 deselected |

Net **+11 tests**: 11 new in `test_cli.py`, plus 2 live tests that are
deselected by default and therefore not counted in the pass total.

### New tests

| Test | Asserts |
|---|---|
| `test_referee_base_url_flag_is_accepted` | the flag parses at all |
| `test_referee_base_url_reaches_the_referee` | the constructed referee's `base_url` is the requested host — the bug of record; asserting on `args` alone would not have caught it |
| `test_referee_base_url_defaults_to_environment` | `LEXML_REFEREE_BASE_URL` is honoured |
| `test_referee_model_defaults_to_environment` | `LEXML_REFEREE_MODEL` is honoured |
| `test_referee_flag_beats_environment` | precedence |
| `test_referee_without_configuration_uses_the_defaults` | falls back to `api.DEFAULT_*` |
| `test_local_referee_is_not_given_a_base_url` | `LocalReferee` takes none |
| `test_decisions_report_accepts_the_base_url_too` | both referee-bearing subcommands |
| `test_routing_and_cli_agree_on_referee_configuration` | the two entry points stay mirrored |
| `test_parse_consults_the_referee_it_was_given` | **the C-2 repair**, via an offline stub that records questions |
| `test_referee_none_still_consults_nobody` | §9.3's invariant is intact |
| `test_live_provider_answers_one_question` | `@live` — a real call returns a well-formed `Verdict` |
| `test_live_answer_is_cacheable` | `@live` — the second ask is a cache hit, zero calls |

### Manual end-to-end verification

With an intentionally invalid key, to prove the request goes where configured:

```
$ … --referee=api --referee-base-url=https://api.z.ai/api/paas/v4 --summary
REFEREE ABSTAINED: HTTPStatusError: Client error '401 Unauthorized'
                   for url 'https://api.z.ai/api/paas/v4/chat/completions'
referee    : consulted, did not override
```

Z.AI, not DeepSeek, and `consulted` rather than `not consulted` — the two
defects this amendment fixes, both visible in one line.

---

## 4. Exit criteria

| # | Criterion | Met | Evidence |
|---|---|---|---|
| E-1 | Suite green, no regression vs. Cycle 8 | ✅ | 5261 passed / 0 failed (was 5250 before, +11 new) |
| E-2 | Live test excluded by default | ✅ | `2 deselected`; skips rather than fails under `-m live` without a key |
| E-3 | `.env.example`'s two variables honoured | ✅ | 4 environment tests + manual Z.AI run |
| E-4 | Goldens byte-identical | ✅ | `0 new, 0 changed, 135 unchanged` |
| E-5 | README exists, names `parse` as the XML command | ✅ | `README.md`, stated in the opening lines and the command table |
| E-6 | **Cycle 9 still not started** | ✅ | `STATUS.md` Cycle 9 row unchanged: `not started` |

---

## 5. Changes to existing features

Four, detailed in the change log. **One major (C-2), confirmed with the user
before implementation.**

| ID | Change | Kind |
|---|---|---|
| C-1 | Four referee fixtures re-keyed to `deepseek-v4-flash` | repair (approved) |
| C-2 | `build_model()` gains `referee`; `cli.py` stops discarding it | **major** (approved) |
| C-3 | `--referee-base-url` + `LEXML_REFEREE_*` defaults | additive |
| C-4 | `tests/referee_fixtures/README.md` key table and refresh command | documentation |

Six changes were considered and rejected, including recording live fixtures
(P-5) and adding `python-dotenv`.

---

## 6. Plan updates

New **§15** amendment log with A-C.1 … A-C.5, plus two in-body annotations so
§8 is not stale: Cycle 8's deliverable line now names the new flags, and its
exit criterion E-7 is annotated to record that the referee status was surfaced
but could not vary until this repair.

---

## 7. Deviations and open items

**Deliberately not done:**

- **P-5 — recording live fixtures.** Out of the approved scope. It changes what
  the fixtures assert, and A-4b.5's reasoning still holds. Still open as
  LLM-doc question 4.
- **`python-dotenv`** (LLM-doc §7.1 change 4) and **`AnthropicReferee`**
  (change 5, question 3) — neither was in the approved set.
- **`--referee-json-mode`** (change 6) — not requested.

**Still open for the user:** LLM-doc §8 questions 1 (adopt DeepSeek as the
declared primary?), 3 (`AnthropicReferee`?), 4 (P-5?), and 5 (is a live referee
pass over the 300+ corpus part of Cycle 9?). Question 5 is the one Cycle 9
needs answered before it starts.

**Observation for Cycle 9, not acted on:** `decisions-report` builds one
`DecisionLog` across all input paths and prints a single aggregate. That is
right for a corpus report, but Cycle 9's "aggregate decisions report over the
300+ corpus" may want per-document breakdown too. Noted, not changed.

---

## 8. Next-cycle readiness

Cycle 9 inherits a green suite, byte-identical goldens, and three things it did
not have before:

1. A referee reachable from the real CLI, against **any** OpenAI-compatible
   provider — which is what a corpus run needs, and what P-1a existed to
   deliver.
2. A live smoke test to confirm provider wiring before committing to a long
   batch run.
3. A README carrying the reproduction statement a published corpus run should
   be measured against.

The one prerequisite Cycle 9 still needs from the user is question 5: whether
the live referee pass over the 300+ corpus is in its scope.
