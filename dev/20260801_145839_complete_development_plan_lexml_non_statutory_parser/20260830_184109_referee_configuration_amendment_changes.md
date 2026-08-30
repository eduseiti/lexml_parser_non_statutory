# Referee configuration amendment — changes to existing features

**Date:** 2026-08-30
**Spec:** [`20260830_184109_referee_configuration_amendment_spec.md`](20260830_184109_referee_configuration_amendment_spec.md)

Four changes to already-delivered behaviour. **One is major** (C-2) and was
confirmed with the user before implementation; the rest are additive or
repairs to a broken state.

---

## C-1 — The four referee fixtures are re-keyed *(repair; approved)*

| Field | Detail |
|---|---|
| **What changed** | `tests/referee_fixtures/{2b9c8bda…,c476d7f5…,a80195c5…,3f881540…}.json` renamed to `{5d21d46f…,1a2ea8e5…,6d17981b…,8ac716a4…}.json`; each file's `meta.model` updated `deepseek-chat` → `deepseek-v4-flash` |
| **Before → after** | Before: 7 tests failing — every cache lookup missed and fell through to the `explodes()` transport (`assert referee.calls == 0` → `assert 3 == 0`). After: 5250 passing, all four fixtures hit |
| **Why** | Commit `e2ecd26` refreshed `api.DEFAULT_MODEL`, and `cache_key` covers the model, so every key moved. The fixtures were correct; only their names were stale |
| **Blast radius** | `tests/unit/test_referee_api.py` (5 tests), `tests/unit/test_telemetry.py` (2), `tests/referee_fixtures/README.md` |
| **Plan impact** | A-C.4 |

**Verdicts, confidences, rationales and the `origin` provenance line are
byte-identical** — only the key and `meta.model` moved. The new keys were
*derived*, never typed: replaying the corpus with an instrumented referee
reproduced all four old keys exactly under `deepseek-chat`, which is what
proves the mapping. `meta.excerpt` could not be used for this, being an
abridged human-readable record rather than the true `(excerpt, ctx)` pair.

---

## C-2 — `build_model()` gains a `referee` parameter *(**MAJOR** — confirmed)*

| Field | Detail |
|---|---|
| **What changed** | `src/lexml_nonstat/model/document.py::build_model` gains keyword-only `referee: Any = None`, passed to `assess_viability(...)`. `cli.py::_cmd_parse` and `_cmd_decisions_report` now pass the referee they build |
| **Before → after** | Before: `cli.py` built a referee from `--referee` and **discarded it**; `parse --referee=api` and `decisions-report --referee=api` made no network call and always printed "not consulted". After: both consult, and the printed status varies with what actually happened |
| **Why** | Discovered while implementing P-1a: the new `--referee-base-url` would have plumbed into a dead end on `cli.py`. A flag the `--help` advertises must do something |
| **Blast radius** | `build_model` is called by `cli.py` (3 sites), `scripts/regen_goldens.py`, and ~20 tests. All pass `referee` implicitly as `None`, so every existing caller is unchanged |
| **Plan impact** | A-C.2; plan §8 Cycle 8 deliverable and exit criterion E-7 annotated |

**Why this is major:** it changes previously-delivered behaviour — a command
that made no network call can now make one. It was escalated and approved
before implementation.

**Why it is nonetheless safe:** the parameter defaults to `None`, which is what
`assess_viability` already defaulted to, so *nothing changes unless the user
explicitly passes `--referee=api|local`*. §9.3's pinned `--referee=none` is
untouched, and all 135 goldens across 9 kinds are byte-identical.

**Note on Cycle 8's exit criterion E-7.** Its report marks "confidence and
referee status surfaced" as met, and the status *was* surfaced — it simply
could not vary, because nothing ever consulted a referee. The criterion was
satisfied as literally worded; this repair makes it meaningful.

---

## C-3 — Referee flags gain a base URL and environment defaults *(additive)*

| Field | Detail |
|---|---|
| **What changed** | `cli.py::_add_referee` and `routing/__main__.py` gain `--referee-base-url`; `--referee-model` and `--referee-base-url` default from `LEXML_REFEREE_MODEL` / `LEXML_REFEREE_BASE_URL`. `_build_referee` passes `base_url` for `--referee=api` only |
| **Before → after** | Before: only `--referee-model` was switchable; a non-DeepSeek provider needed a code edit, and `.env.example`'s two variables were read by nothing. After: any OpenAI-compatible provider is a configuration choice |
| **Why** | P-1a. `.env.example` shipped presets the code ignored, so a Z.AI preset silently called DeepSeek — and, because the cache key covers the model, would have written fixtures labelled with the wrong provider |
| **Blast radius** | Both entry points; no existing flag changes meaning; `--referee=none` unchanged |
| **Plan impact** | A-C.1 |

Precedence is **flag > environment > `api.DEFAULT_*`**, matching how
`LEXML_REFEREE_API_KEY` already resolved. The environment is read at argparse
default time so `--help` shows the value that will actually be used.

`LocalReferee` is deliberately never given a `base_url` — it has no such
parameter, and passing one would raise `TypeError`. A test pins this.

---

## C-4 — `tests/referee_fixtures/README.md` updated *(documentation)*

The key table now lists the new hashes, with a dated note recording the
re-keying, its cause and the derivation method. The refresh command's
`--referee-model=deepseek-chat` is corrected to `deepseek-v4-flash`.

---

## Considered and rejected

| # | Change | Why rejected |
|---|---|---|
| R-1 | Record the four fixtures live, replacing the hand-authored ones | That is the record's **P-5** and LLM-doc open question 4 — out of the approved scope. It changes what the fixtures *assert*, and A-4b.5's reasoning (they test plumbing, not the model) still holds |
| R-2 | Pin the referee tests to `model="deepseek-chat"` explicitly | Decouples the suite from `DEFAULT_MODEL` permanently, but then the fixtures no longer describe the model the tool actually uses. Rejected by the user in favour of re-keying |
| R-3 | Refactor `routing/__main__.py` to expose a `build_parser()` for testability | Cycle 4b's module builds its parser inside `main()`. Refactoring delivered code purely to make a new test convenient is the wrong trade; the mirror test drives `--help` in a subprocess instead |
| R-4 | Add `python-dotenv` so `.env` loads automatically | LLM-doc §7.1 change 4, **not** in the approved set. The package's hard dependencies are `lxml` and `python-docx` and should stay that way; the README documents `set -a; . ./.env; set +a` |
| R-5 | Add an `AnthropicReferee` | LLM-doc §7.1 change 5 / open question 3 — undecided, and unnecessary for the OpenAI-compatible providers this amendment enables |
| R-6 | Fix only `decisions-report`, leaving `parse --referee` inert | Would leave `parse` accepting a flag it ignores — the same class of defect this amendment exists to remove |
