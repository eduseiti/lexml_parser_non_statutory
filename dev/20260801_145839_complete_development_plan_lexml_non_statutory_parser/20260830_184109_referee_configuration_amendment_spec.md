# Referee configuration amendment — spec

**Date:** 2026-08-30
**Plan:** [`20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`](../20260801_145839_complete_development_plan_lexml_non_statutory_parser.md)
**Kind:** interstitial amendment, **not a numbered cycle**. Cycle 9 remains not
started, and nothing here discharges any Cycle 9 exit criterion.
**Investigation record:** [`docs/20260830_144415_referee_setup_verification_cli_usage_and_base_url_gap.md`](../../docs/20260830_144415_referee_setup_verification_cli_usage_and_base_url_gap.md)

**User's instruction (verbatim):**

> I checked the "docs/20260830_144415_referee_setup_verification_cli_usage_and_base_url_gap.md"
> document and I liked the suggestions, including P-1a recommendation. Go ahead
> amend the development plan and execute the changes to accomplish the
> suggestions. Do not finish cycle 9 though, only the LLM API changes you
> capture in the new .md document.

Scope is therefore **P-1a, P-2, P-3 and P-4** of that record. **P-5 (recording
live fixtures) is explicitly out of scope** — it changes what the fixtures
assert and remains LLM-doc open question 4.

---

## 1. Why this is not a cycle

The dev-cycle skill implements one *numbered* cycle from the plan. This work is
none of Cycle 9's bullets: it repairs a defect introduced after Cycle 8 closed,
and adopts three proposals the LLM-access record raised as open questions that
Cycle 8 ran without resolving. Filing it as "Cycle 9" would claim exit criteria
(corpus scale-out, regression consolidation) that are untouched here.

It follows the cycle *discipline* — baseline, spec, change log, report, visible
plan amendment — because that is what keeps `dev/` trustworthy. `STATUS.md`
gains an interstitial row, not a cycle row.

---

## 2. Inherited state

| Item | State |
|---|---|
| Cycle 8 | complete, 2026-08-30, 5250 pass / 0 fail / 4 skip |
| Cycle 9 | not started — **and stays that way** |
| `cli.py` | eight subcommands; `--referee`, `--referee-model`, `--referee-cache` |
| `referee/api.py` | `CachedAPIReferee(model=, base_url=, api_key=, cache=, transport=, timeout=)` — `base_url` is a constructor keyword already |
| `referee/cache.py` | `cache_key(model, kind, excerpt, ctx)` — **the model is part of the key** |
| `tests/referee_fixtures/` | 4 hand-authored fixtures, keyed under `model="deepseek-chat"` |
| `pyproject.toml` | `markers = ["live: …", "slow: …"]`, `addopts = "-m 'not live'"` — the marker exists, **no test uses it** |
| `.env.example` | committed in `e2ecd26`; declares `LEXML_REFEREE_BASE_URL` and `LEXML_REFEREE_MODEL`, **which no code reads** |
| README | does not exist |

### 2.1 The baseline is RED — and that is the first thing to fix

```
7 failed, 5243 passed, 4 skipped
```

All seven are referee tests. **Root cause, confirmed:** commit `e2ecd26`
changed `api.DEFAULT_MODEL` from `deepseek-chat` to `deepseek-v4-flash`. The
cache key covers the model, so `fixture_referee()` — which does not pass a
model and therefore inherits `DEFAULT_MODEL` — computes four keys that no
fixture file matches. Every lookup misses, falls through to the transport, and
the transport in those tests is an `explodes()` guard that asserts it is never
called:

```
REFEREE ABSTAINED: AssertionError: the transport was called;
                   this path must make no network calls
assert referee.calls == 0  →  assert 3 == 0
```

The fixtures are unmodified and still committed at `8be4549` (Cycle 4b); only
the key moved. This is precisely the failure mode the investigation record
§3.3 predicted for a model change — it simply arrived through `DEFAULT_MODEL`
rather than through the base-URL confusion.

Failing tests: `test_referee_api.py::{test_par_cosit_26_resolves_from_recorded_fixture,
test_parecer_93_resolves_from_recorded_fixture, test_fixture_referee_over_whole_corpus,
test_the_referee_is_only_asked_about_flagged_decisions[par_cosit_26_20000629],
test_the_referee_is_only_asked_about_flagged_decisions[parecer_93_2018_decor_cgu_agu]}`
and `test_telemetry.py::{test_plan_identity_holds_with_an_active_referee,
test_report_renders_every_section}`.

---

## 3. Reconciliation — questions asked and answered

| # | Question | Answer |
|---|---|---|
| Q1 | How to repair the red baseline? | **Re-key the 4 fixtures to `deepseek-v4-flash`** (rename to new hashes, update `meta.model`), keeping verdicts byte-identical. Rejected: pinning the tests to `deepseek-chat`; recording live fixtures (that is P-5, out of scope) |
| Q2 | How much README? | **Full README, all five P-3 sections**, including the LLM-referee section and the reproduction statement |

### Non-blocking decisions taken here

- **D-1.** `--referee-base-url` is added to the shared `_add_referee` helper in
  `cli.py`, so `parse` and `decisions-report` both gain it in one place, and
  mirrored into `routing/__main__.py` — whose `_build_referee` docstring already
  promises it "mirrors `routing/__main__`'s construction exactly". That promise
  becomes a test.
- **D-2.** Precedence is **flag > environment > `api.DEFAULT_*`**, matching how
  `LEXML_REFEREE_API_KEY` already resolves, and stated in `--help`.
- **D-3.** The env lookup happens at *parse time* as an `argparse` default, not
  inside `_build_referee`, so `--help` can show the effective value and a test
  can set `os.environ` and read `args`.
- **D-4.** `base_url` is passed only for `--referee=api`. `LocalReferee` has no
  such parameter; passing it would raise `TypeError`.
- **D-5.** The live smoke test (P-2) goes in a new `tests/unit/test_referee_live.py`
  rather than into `test_referee_api.py`, so the offline file keeps its
  invariant that nothing in it can ever reach the network.
- **D-6.** No `python-dotenv` dependency (LLM-doc §7.1 change 4 is *not* in the
  accepted set). The README documents `set -a; . ./.env; set +a`.

---

## 4. Deliverables

### P-0 — Repair the red baseline (prerequisite for everything)

Re-key the four fixtures from `deepseek-chat` to `deepseek-v4-flash`:

| Old key | Sample | Locator |
|---|---|---|
| `2b9c8bda45572e8253148db50cf9b6d7` | `par_cosit_26_20000629` | `p#46` |
| `c476d7f5075ccde1149d5cae023ddcbe` | `par_cosit_26_20000629` | `p#47` |
| `a80195c5c6b68ca5926e27d66ab9cf97` | `par_cosit_26_20000629` | `p#53` |
| `3f88154033d5efc38d9a8d944f93385b` | `parecer_93_2018_decor_cgu_agu` | `p#36` |

New names are `cache_key("deepseek-v4-flash", kind, excerpt, ctx)`, computed
from each file's own recorded `meta`, never typed by hand. `meta.model` is
updated in place; `verdict`, `confidence`, `rationale` and
`meta.origin` (the hand-authored provenance, A-4b.5) are **untouched**.

`tests/referee_fixtures/README.md`'s key table is updated, plus a note that the
files were re-keyed and why.

### P-1a — `--referee-base-url` and environment defaults

| Surface | Change |
|---|---|
| `cli.py::_add_referee` | new `--referee-base-url`, default `os.environ.get("LEXML_REFEREE_BASE_URL")`; `--referee-model` default becomes `os.environ.get("LEXML_REFEREE_MODEL")` |
| `cli.py::_build_referee` | pass `base_url` when set, for `api` only |
| `routing/__main__.py` | the same two flags and the same construction |

`.env.example` becomes true as written: both variables it already declares are
read. Nothing about `--referee=none` changes, so §9.3 is untouched.

### P-2 — Live smoke test

`tests/unit/test_referee_live.py`, one test, `@pytest.mark.live`, skipped unless
`LEXML_REFEREE_API_KEY` is set. Excluded by default through the existing
`addopts = "-m 'not live'"`. Asserts a real call returns a well-formed
`Verdict` from the configured provider — turning "it apparently worked but I
can't tell" into a green or red line.

### P-3 — README.md

Five sections per the investigation record: what the tool does; install and
`PYTHONPATH=src`; the eight subcommands with **`parse` named first and
unmistakably as the XML producer**; `## LLM referee (optional)` with the Z.AI
zero-cost path, the `.env` flow, the verification command and the reproduction
statement; dual-schema validation and the `regen_goldens.py` contract.

### P-4 — Correct the LLM-access record's §6.6

`docs/20260829_144555_…` is a historical record, so it is corrected by a dated
**footnote**, not a rewrite: `routing` emits no XML, `parse` does, and the
predicted `consulted=3` line is actually `consulted=True overrode=False` with
the count in the decisions report.

---

## 5. Implementation plan

| # | Item | Mode | Depends on |
|---|---|---|---|
| 1 | P-0 re-key fixtures + fixtures README | `[sequential]` | — |
| 2 | Verify baseline green | `[sequential]` | 1 |
| 3 | P-1a in `cli.py` + `routing/__main__.py` | `[sequential]` | 2 |
| 4 | P-1a tests in `tests/unit/test_cli.py` | `[sequential]` | 3 |
| 5 | P-2 live smoke test | `[parallel]` with 4 | 3 |
| 6 | P-3 README | `[parallel]` with 4, 5 | 3 |
| 7 | P-4 footnote | `[parallel]` | — |
| 8 | Plan amendment + STATUS row + change log + report | `[sequential]` | all |

Too small and too interdependent for subagent fan-out: items 3–4 touch the two
files everything else depends on, and 5–7 are a file each.

---

## 6. Test plan

### New tests (`tests/unit/test_cli.py`)

| Test | Asserts | Discharges |
|---|---|---|
| `test_referee_base_url_flag_is_accepted` | `parse --referee-base-url=… --referee=api` parses; the value reaches `args` | P-1a |
| `test_referee_base_url_defaults_to_environment` | `LEXML_REFEREE_BASE_URL` set ⇒ that is the default | P-1a, D-2 |
| `test_referee_model_defaults_to_environment` | `LEXML_REFEREE_MODEL` set ⇒ that is the default | P-1a, D-2 |
| `test_referee_flag_beats_environment` | both set ⇒ **the flag wins** | D-2 |
| `test_referee_base_url_reaches_the_referee` | constructed `CachedAPIReferee.base_url` is the requested host, not DeepSeek — the bug of record | P-1a |
| `test_referee_base_url_absent_uses_the_default` | no flag, no env ⇒ `api.DEFAULT_BASE_URL` | D-2 |
| `test_local_referee_gets_no_base_url` | `--referee=local` does not pass `base_url` | D-4 |
| `test_routing_and_cli_build_the_same_referee` | both entry points agree on model + base_url | D-1 |

### New test (`tests/unit/test_referee_live.py`)

| Test | Asserts |
|---|---|
| `test_live_provider_answers_one_question` | `@pytest.mark.live`; skipped without a key; a real adjudication returns a `Verdict` with a known verdict token and `0.0 ≤ confidence ≤ 1.0` |

### Reused regression tests — must stay green

- All 7 currently-failing referee tests, **green after P-0**.
- `test_referee_api.py` in full — especially `test_cache_hit_makes_zero_network_calls`
  and the adversarial invariant #9 test (A-4b.6).
- `test_cli.py::` the existing `--referee=none` default assertions (§9.3).
- All 135 goldens across 9 kinds: **byte-identical**. This amendment changes no
  emitted artifact.

### Exit criteria

| # | Criterion | Command |
|---|---|---|
| E-1 | Suite green, no regressions vs. Cycle 8's 5250 | `python3 -m pytest tests/ -q` |
| E-2 | Live test excluded by default | absent from the default run; collected under `-m live` |
| E-3 | `.env.example`'s two variables are honoured | new CLI tests |
| E-4 | Goldens byte-identical | golden tests within E-1 |
| E-5 | README exists and names `parse` as the XML command | file present |
| E-6 | Cycle 9 still not started | `STATUS.md` unchanged for the Cycle 9 row |

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Re-keying breaks the offline guarantee | Keys are *computed* from each fixture's own `meta`, then the suite proves the hits (`cache.hits == len(flagged)`, `calls == 0`) |
| A stale `LEXML_REFEREE_*` in the developer's environment leaks into tests | Every env-sensitive test uses `monkeypatch` and sets or deletes explicitly |
| The live test runs in CI by accident | Double-guarded: `addopts = "-m 'not live'"` **and** a skip on the missing key |
| Scope creep into Cycle 9 | Deliverables enumerated above; `STATUS.md` Cycle 9 row stays `not started` |
