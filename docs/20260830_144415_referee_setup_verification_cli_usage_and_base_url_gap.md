# Referee setup verification — why §6.6 shows no XML, and the `--referee-base-url` misalignment

**Date:** 2026-08-30
**Status:** investigation record (`docs/`), not an instruction. The executing
plan is `dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`;
where the two disagree, `dev/` wins. **Nothing in the repository was changed by
this investigation** — §6 proposes amendments for the user's decision.

**Originating request (verbatim):**

> I have applied the deepseek key configuration described in
> `@docs/20260829_144555_llm_api_access_provider_evaluation_and_setup.md` and
> apparently successfully executed the test in section 6.6 — adding a "src." in
> front of "lexml_nonstat.routing", in order to properly find the model.
> Through the output it seemed the LLM API access worked, but I could not see
> the resulting LexML output, not sure why: I realized there is no README or
> easy-to-find documentation on how to use the tool, so I could not verify if
> the test command was only to verify the referee API usage, or something else
> was missing in order to get the actual lexml output.
>
> Other thing that caught my attention: in section 3 it is mentioned
> "--referee-base-url" is not an available parameter right now, but the
> .env.example does define it. That seemed to be misalignment in the plan: I'm
> not sure if that has already been implemented in cycle 8 — that .md document
> about the LLM API access had been created before executing dev cycle 8, which
> I have already accomplished.

---

## 1. Executive summary

| # | Question | Answer |
|---|---|---|
| 1 | Why no LexML XML from the §6.6 command? | **Working as designed.** `python3 -m lexml_nonstat.routing` is a *diagnostic* entry point that prints a routing verdict and a decisions report. It never emits XML — by design, in any mode. The XML command is `python3 -m lexml_nonstat parse` |
| 2 | Was §6.6 only a referee wiring check? | **Yes**, and that is all it claims. Nothing was missing from your setup |
| 3 | Did the referee actually work? | Almost certainly yes — see §2.3 for the one line of your output that settles it, and how to confirm |
| 4 | Was `--referee-base-url` implemented in Cycle 8? | **No.** It does not exist anywhere in the repository |
| 5 | Is §3 of the LLM doc therefore still accurate? | **Yes** — it is the one statement in the pair that is still true |
| 6 | So where is the misalignment? | In **`.env.example`**, not in the plan. It declares `LEXML_REFEREE_BASE_URL` and `LEXML_REFEREE_MODEL`; **no code reads either variable.** They are silently inert |
| 7 | Is the plan wrong? | **No.** Plan §8 (Cycle 8) scopes the CLI flags as `--profile/--emitter/--schema/--referee/--strict` — no base-URL flag. Cycle 8 delivered exactly its scope. The LLM doc's §7.1 changes were *proposals awaiting your decision* (its §8 open question 2), and were never adopted |
| 8 | Is there a README? | **No.** `ls README*` returns nothing, and the plan never scopes one. This is a real gap for a tool intended for publication |

The one genuine defect this investigation found is item 6: a committed file
that promises configuration the code ignores. Everything else is a
documentation gap, not a code fault.

---

## 2. Point 1 — why the §6.6 command showed no LexML output

### 2.1 The `routing` entry point does not emit XML, in any mode

`src/lexml_nonstat/routing/__main__.py` says so in its own docstring:

> Inspect a document's routing verdict, and the decisions behind it. […]
> Mirrors Cycles 1–3's per-package debug views. Cycle 8's
> `python3 -m lexml_nonstat decisions-report` covers §7.4's summary; this stays
> because no CLI subcommand prints a *per-document* verdict with its gates.

It is one of seven per-package debug entry points (`ingest`, `model`,
`hierarchy`, `segment`, `segments`, `validate`, `routing`), each predating the
unified CLI and each answering one question about one stage. `routing` answers
*"which of §4's three routes does this document take, and why"*. There is no
flag, on that module, that would have produced XML.

So: **your command did what it was supposed to do, and nothing was missing from
your setup.** §6.6 is titled "Verify the wiring", and the verification it
performs is of the referee call path only.

### 2.2 The command that produces LexML XML

Cycle 8 landed `src/lexml_nonstat/cli.py` — the unified CLI, exposed both as
`python3 -m lexml_nonstat` and (once installed) as the `lexml-nonstat` console
script from `[project.scripts]`. Its eight subcommands:

| Subcommand | What it does |
|---|---|
| **`parse`** | **render a document to LexML XML** ← the one you were looking for |
| `dump-styled` | what ingestion saw |
| `dump-tree` | the inferred hierarchy |
| `segment` | citable segments, CSV or JSONL |
| `validate` | validate XML against the LexML schemas |
| `list-profiles` | the registered document profiles |
| `decisions-report` | §7.4's rule-vs-referee summary |
| `capabilities` | what the schemas present permit (A-R.9) |

Verified in this repository, on your own sample:

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse samples/par_cosit_26_20000629.docx
```

which prints (exit code 0, confirmed):

```xml
<LexML xmlns="http://www.lexml.gov.br/1.0" xmlns:xlink="http://www.w3.org/1999/xlink">
  <Metadado>
    <Identificacao URN="urn:lex:br:ministerio.fazenda;secretaria.receita.federal:parecer:2000-06-29;26"/>
    <MetadadoProprietario fonte="http://www.lexml.gov.br/nonstat">
      <campo nome="Assunto">Imposto sobre a Renda de Pessoa Física - IRPF</campo>
      …
  <DocumentoGenerico>
    <PartePrincipal id="pp1">
      <Agrupamento id="pp1_agr1" nome="epigrafe">
        <p>Parecer Cosit nº 26, de 29 de junho de 2000</p>
      …
```

The structured warnings you saw on the routing run appear here too, on
**stderr**, so `> out.xml` captures clean XML while diagnostics stay on the
terminal:

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse samples/par_cosit_26_20000629.docx > out.xml
```

Useful variants of `parse`: `-o DIR` (write the whole bundle, including split
annexes), `--format=json` (report the run rather than the XML), `--summary`
(text summary instead of XML), `--emitter=`, `--schema=`, `--strict`.

### 2.3 On `PYTHONPATH` versus `src.lexml_nonstat`

Your `src.` prefix works by accident and will bite later. The package is not
installed, and `src/` has no `__init__.py`, so `src.lexml_nonstat` resolves
only under Python 3.3+ namespace-package rules and gives the module a different
dotted name than the one the package's own relative imports and the test
suite assume. CLAUDE.md states the supported form:

> The package is **not installed**; `tests/conftest.py` puts `src/` on
> `sys.path` […] Outside pytest, use `PYTHONPATH=src`.

So prefer:

```bash
PYTHONPATH=src python3 -m lexml_nonstat.routing …     # not src.lexml_nonstat
PYTHONPATH=src python3 -m lexml_nonstat parse …
```

Or install it once and drop the prefix entirely: `pip install -e .` then
`lexml-nonstat parse …`.

### 2.4 Did your referee call actually reach DeepSeek?

The line that settles it is the referee counter. Three outcomes are
distinguishable:

| What the output says | Meaning |
|---|---|
| `referee : consulted=True overrode=False` and `put to a referee: 3` with `referee agreed: 3` | **The API answered.** Three flagged decisions adjudicated, rules confirmed |
| Same counters, but `referee abstained: 3` and `REFEREE ABSTAINED: HTTPStatusError … 401` | Key rejected |
| `referee=skipped` on every line, `consulted=False` | The referee was never consulted — `--referee=none`, or the key was not exported into that shell |

This was confirmed empirically here. Running your §6.6 command with a
deliberately invalid key produced a genuine outbound request and a real
provider rejection:

```
WARNING referee  par_cosit_26_20000629.docx p#46  REFEREE ABSTAINED:
        HTTPStatusError: Client error '401 Unauthorized' for url
        'https://api.deepseek.com/v1/chat/completions'
…
referee    : consulted=True overrode=False
  put to a referee:    3
    referee abstained: 3
```

The three flagged decisions are exactly the ones `tests/referee_fixtures/README.md`
documents for this sample (p#46, p#47, p#53). If your run showed
`referee agreed: 3` instead of `abstained: 3`, the key worked and the referee
confirmed all three rule verdicts — which is the expected result, per A-4b.3:
**on this corpus the referee confirms, it never rescues.**

One correction to the LLM doc while we are here: its §6.6 predicts
`referee : consulted=3 overrode=0`, but the actual text line is
`referee : consulted=True overrode=False` (a per-document boolean); the
*count* 3 appears in the decisions report below it, as `put to a referee: 3`.

### 2.5 Where the referee changes the XML — and where it cannot

Worth stating plainly, because it affects how you'd verify a referee run:

- `--referee` is accepted by **`parse`** and **`decisions-report`**, so you can
  run a live referee and get XML in one command.
- On the 15 samples it will change **nothing** in that XML. Invariant #9 and
  amendment A-4b.6 assert this as an adversarial property: a referee answering
  "own" to every question changes no sample's route. All four corpus fixtures
  agree with the rules.
- The referee's value is Cycle 9's 300+ corpus, where the rules are unproven —
  which is what the LLM doc §2.3 concluded.

So a live referee run on `samples/` is a *wiring* check, and the decisions
report — not the XML — is where you read the result.

### 2.6 There is no README, and the plan never asked for one

`ls README*` returns nothing at the repository root, and `grep -i readme` over
the plan finds no occurrence. The only user-facing documentation is CLAUDE.md
(addressed to an agent, not a user), the per-module `__main__` docstrings, and
`--help`. The LLM doc §7.2 assumes a "published README" exists to add an
`## LLM referee (optional)` section to; it does not.

For a tool whose stated goal includes publication alongside a paper, this is a
real gap. See amendment proposal **P-3**.

---

## 3. Point 2 — the `--referee-base-url` misalignment

### 3.1 What the code actually contains

Verified by exhaustive search across `src/`, `tests/`, `scripts/`,
`pyproject.toml` and `dev/`:

```
grep -rn "LEXML_REFEREE_BASE_URL\|LEXML_REFEREE_MODEL\|referee-base-url\|referee_base_url\|dotenv"
→ no matches anywhere
```

| Item | State today | Where |
|---|---|---|
| `--referee` | ✅ exists, default `none` | `cli.py:647`, `routing/__main__.py:88` |
| `--referee-model` | ✅ exists, default `None` | `cli.py:652` |
| `--referee-cache` | ✅ exists | `cli.py:654` |
| **`--referee-base-url`** | ❌ **does not exist** | — |
| `LEXML_REFEREE_API_KEY` | ✅ read | `cli.py:133`, `routing/__main__.py:132` |
| **`LEXML_REFEREE_BASE_URL`** | ❌ **read by nothing** | — |
| **`LEXML_REFEREE_MODEL`** | ❌ **read by nothing** | — |
| `api.DEFAULT_BASE_URL` | `https://api.deepseek.com/v1`, constructor-only | `referee/api.py:41` |
| `api.DEFAULT_MODEL` | **`deepseek-v4-flash`** — refreshed | `referee/api.py:42` |
| `python-dotenv` | not a dependency; extras are `referee`/`xslt`/`dev` | `pyproject.toml:24-31` |

`CachedAPIReferee.__init__` does take a `base_url=` keyword — so the capability
is there in the library; only the *configuration surface* is missing.

### 3.2 So §3 of the LLM doc is right, and `.env.example` is what drifted

The LLM doc's §3 states:

> **`base_url` is not yet a CLI flag.** `--referee-model` exists;
> `--referee-base-url` does not — a non-DeepSeek provider currently needs a
> code-level `base_url` or a small CLI addition. This is the one gap between
> today's code and a multi-provider setup, and it belongs in **Cycle 8**
> (§7.1 below).

**That paragraph is still accurate.** It correctly says the flag does not exist
and correctly identifies Cycle 8 as where it *would belong*. What it could not
know is that Cycle 8 would be executed without adopting it.

The `.env.example` file is the newer artifact and the one that overstates. Git
confirms the sequence:

| Commit | Date | Contents |
|---|---|---|
| `4a4cdee` Cycle 8 | 2026-08-30 | `cli.py` (794 lines), HTML/TXT readers, `warnings.py`, `[project.scripts]`, 5 test files. **No referee configuration change** |
| `e2ecd26` Configuring LLM referee test | 2026-08-30 14:32 | `.env.example` (new, 32 lines), `.gitignore` (+4, the secrets block), `api.py` (**1 line**: `DEFAULT_MODEL` → `deepseek-v4-flash`) |

So `.env.example` was added *after* Cycle 8, by hand, transcribed verbatim from
the LLM doc §7.2 — where it was written as a **proposal contingent on §7.1
changes 1 and 2 being accepted**. Those changes were never made, so the file
ships two variables the code cannot see.

### 3.3 Why this matters more than it looks

It is not merely cosmetic. `.env.example` is committed, is the file a
reproducer copies, and doubles as the provider cheat-sheet. In its current
state:

- Uncommenting the Z.AI block and running `--referee=api` **silently calls
  DeepSeek anyway**, with a Z.AI key. The failure surfaces as an opaque `401`
  abstention against the wrong host.
- Setting `LEXML_REFEREE_MODEL=glm-4.7-flash` has no effect; the model stays
  `deepseek-v4-flash` unless `--referee-model` is passed on the command line.
- Because the disk cache key covers the model (`cache.cache_key`), a run
  believed to be Z.AI would write fixtures labelled `deepseek-v4-flash`,
  corrupting exactly the provider-comparison property the fixtures README
  advertises.

The last point is the one with lasting consequences: it makes bad data, not
just a bad error message.

### 3.4 Cycle 8 is not at fault

Plan §8, Cycle 8's deliverable line (plan line 1602), reads:

> `cli.py`: `parse`, `dump-styled`, `dump-tree`, `segment`, `validate`,
> `list-profiles`, `decisions-report`, **`capabilities`** […] structured
> warnings; confidence reporting;
> `--profile`/`--emitter`/`--schema`/`--referee`/`--strict`.

No base-URL flag, no env-var defaults. Cycle 8 delivered that list in full
(5250 tests passing, 135 goldens byte-identical, six amendments A-8.1–A-8.6,
none of them referee-related). The LLM doc itself flagged its §7.1 as
undecided:

> **They are proposals for the user's decision, not amendments** — per
> CLAUDE.md, plan changes are agreed, not assumed.

and asked directly, in its §8 open question 2, whether changes 1–3 were
accepted as Cycle 8 scope. That question was never answered, so the cycle ran
without them. The process worked; only the `.env.example` commit got ahead of
it.

Note that §7.1 **change 3 did land**, in that same manual commit: `DEFAULT_MODEL`
is now `deepseek-v4-flash`, not the stale `deepseek-chat`. So of the three
"minimum for a credible published tool" changes, one is done and two are open.

---

## 4. Everything verified, in one table

| Claim | Verdict | Evidence |
|---|---|---|
| `routing` never emits XML | ✅ confirmed | module docstring; run produces verdict + report only |
| `parse` emits XML | ✅ confirmed | run on `par_cosit_26_20000629.docx`, exit 0, valid `<LexML>` |
| Warnings go to stderr, XML to stdout | ✅ confirmed | redirect test |
| §6.6 was a wiring check only | ✅ confirmed | its own section title |
| Referee reaches the network with `--referee=api` + key | ✅ confirmed | invalid key → real 401 from `api.deepseek.com` |
| The sample flags exactly 3 decisions | ✅ confirmed | p#46/p#47/p#53, matching the fixtures README |
| §6.6's predicted `consulted=3` text | ⚠️ inaccurate | actual line is `consulted=True overrode=False`; the 3 is in the report |
| `--referee-base-url` exists | ❌ does not | exhaustive grep, 0 matches |
| `LEXML_REFEREE_BASE_URL` / `_MODEL` read anywhere | ❌ they are not | exhaustive grep, 0 matches |
| `DEFAULT_MODEL` refreshed to `deepseek-v4-flash` | ✅ done | `api.py:42`, commit `e2ecd26` |
| Cycle 8 was scoped to include the flag | ❌ it was not | plan line 1602 |
| `.gitignore` protects `.env` | ✅ done | commit `e2ecd26`; only `.env.example` is tracked |
| `httpx` is an optional extra | ✅ | `pyproject.toml:27` |
| A README exists | ❌ no | `ls README*` empty; plan has no occurrence of "readme" |

---

## 5. What to do right now, with no code change

To get LexML XML:

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse samples/par_cosit_26_20000629.docx > out.xml
PYTHONPATH=src python3 -m lexml_nonstat --help          # all eight subcommands
```

To run a live referee **and** get XML in one command:

```bash
set -a; . ./.env; set +a
PYTHONPATH=src python3 -m lexml_nonstat parse \
    --referee=api --referee-model=deepseek-v4-flash \
    --referee-cache=/tmp/lexml_referee_cache \
    samples/par_cosit_26_20000629.docx > out.xml
```

To use a **non-DeepSeek** provider today, the only working route is Python,
because no flag reaches `base_url`:

```python
import sys; sys.path.insert(0, "src")
from lexml_nonstat.referee import CachedAPIReferee
referee = CachedAPIReferee(
    model="glm-4.7-flash",
    base_url="https://api.z.ai/api/paas/v4",
    api_key=os.environ["LEXML_REFEREE_API_KEY"],
)
```

Until P-1 below is adopted, **treat `LEXML_REFEREE_BASE_URL` and
`LEXML_REFEREE_MODEL` in your `.env` as documentation, not configuration.**

---

## 6. Proposed amendments — for your decision, not applied

Nothing below has been changed in the repository. Cycle 9 is the natural home
for all of it: it is the next cycle, it is the one that runs the corpus at
scale, and its exit criteria already include the regression consolidation these
touch.

### P-1 — Close the `.env.example` gap (**recommended; this is the actual defect**)

Two mutually exclusive options. Doing *neither* is the only bad answer, because
the current state is a committed file that lies.

| Option | Change | Cost | Consequence |
|---|---|---|---|
| **P-1a (recommended)** | Implement LLM doc §7.1 changes 1 + 2: add `--referee-base-url`, and read `LEXML_REFEREE_BASE_URL` / `LEXML_REFEREE_MODEL` as defaults for the two flags | ~20 lines in `cli.py` + `routing/__main__.py`, plus tests | `.env.example` becomes true as written; every OpenAI-compatible provider becomes a configuration choice, which is what `api.py`'s docstring already promises and what the publication goal needs |
| **P-1b** | Leave the code alone; edit `.env.example` to comment out the two inert variables with a note that only `LEXML_REFEREE_API_KEY` is read, and that non-DeepSeek providers need the Python API | ~6 lines of comment | Honest, zero risk, but leaves the tool single-provider in practice and undercuts the Z.AI zero-cost reproduction path the LLM doc §4.6 recommends |

**P-1a is the better answer** given the stated publication intent: the free Z.AI
path is what lets a stranger reproduce the results without a payment method,
and it is unreachable from the CLI today. The precedence should be flag > env
var > `api.DEFAULT_*`, matching how `LEXML_REFEREE_API_KEY` already works.

Suggested amendment text, if you accept:

> **A-9.x** — Cycle 8's referee flags are extended with `--referee-base-url`,
> and `--referee-base-url`/`--referee-model` take their defaults from
> `LEXML_REFEREE_BASE_URL`/`LEXML_REFEREE_MODEL`. Plan §8's flag list
> (`--profile/--emitter/--schema/--referee/--strict`) predates `.env.example`,
> which was committed after Cycle 8 and already documents both variables as
> live. Precedence is flag > environment > `api.DEFAULT_*`. Deferred from
> Cycle 8, where the LLM-access record proposed it as an undecided open
> question that was never resolved before the cycle ran.

### P-2 — Add a live-provider smoke test (**recommended**)

Plan §9.3 already reserves a `@pytest.mark.live` test, excluded by default. It
does not exist yet. One test, skipped unless `LEXML_REFEREE_API_KEY` is set,
asserting that a real call returns a parseable `Verdict`, would have turned
your "it apparently worked but I can't tell" into a green or red line. It costs
a fraction of a cent per run and never runs in CI.

### P-3 — Write a README (**recommended, and larger than it sounds**)

The plan scopes no user-facing documentation at all, which is defensible for
cycles 0–8 and indefensible for a published tool. Minimum contents:

1. What the tool does, and the DOCX → LexML XML one-liner.
2. Install / `PYTHONPATH=src`, and why a bare `import lexml_nonstat` fails.
3. The eight subcommands, one line each — with **`parse` named first and
   unmistakably as the one that produces XML**. This report exists because that
   sentence was nowhere to be found.
4. The `## LLM referee (optional)` section the LLM doc §7.2 already drafted:
   *no key is needed*, the free Z.AI path, the `.env` flow, the verification
   command, the §7.2 reproduction statement.
5. The dual-schema validation rule and the `regen_goldens.py` contract.

### P-4 — Correct the LLM doc's §6.6 expected output (**minor**)

Change the predicted `referee : consulted=3 overrode=0` to the actual
`referee : consulted=True overrode=False` plus `put to a referee: 3` in the
decisions report, and add one line saying that `routing` prints no XML and that
`lexml_nonstat parse` is the XML command. As a `docs/` record the file is
historical and arguably should stay as written; a dated footnote pointing at
*this* document would preserve the record while removing the trap.

### P-5 — Revisit the four hand-authored fixtures (**your call, unchanged from before**)

The LLM doc §8 question 4 is still open, and now you have a key. A-4b.5's
reasoning still holds (the fixtures test plumbing, not the model), but recorded
fixtures would be the stronger claim in a paper. The refresh command and its
reviewed-diff discipline are documented in `tests/referee_fixtures/README.md`.
Note that under P-1a the refresh becomes provider-switchable from the CLI,
which is the cheap moment to do a two-provider comparison.

### Still-open questions inherited from the LLM doc §8

Questions 1 (provider), 3 (`AnthropicReferee`), and 5 (live referee pass over
the 300+ corpus as Cycle 9 scope) remain unanswered. Question 2 is effectively
answered by events — the changes were not adopted in Cycle 8 — and P-1 above
re-poses it for Cycle 9.

---

## 7. Sources

Repository, as of commit `e2ecd26` (2026-08-30):

- `src/lexml_nonstat/cli.py` — subcommands and `_add_referee` (lines 645–656)
- `src/lexml_nonstat/routing/__main__.py` — module docstring, `--referee` args
- `src/lexml_nonstat/referee/api.py` — `DEFAULT_BASE_URL`, `DEFAULT_MODEL`,
  `CachedAPIReferee.__init__`
- `src/lexml_nonstat/referee/adjudicate.py` — the `consult` predicate
- `src/lexml_nonstat/referee/__init__.py` — `build_referee`, `REFEREE_MODES`
- `pyproject.toml` — `[project.scripts]`, optional dependencies
- `.env.example`, `.gitignore` — commit `e2ecd26`
- `tests/referee_fixtures/README.md` — the four fixtures and their provenance
- Plan §7.3, §7.4, §8 (Cycle 8 deliverables, line 1602), §9.3
- `dev/…/STATUS.md` — cycle states and amendments A-8.1–A-8.6
- `docs/20260829_144555_llm_api_access_provider_evaluation_and_setup.md` — §3,
  §6.6, §7.1, §7.2, §8

Live checks performed for this report (all offline except where noted): `parse`
and `routing` runs on `samples/par_cosit_26_20000629.docx`; one deliberate
invalid-key call to `api.deepseek.com` to confirm the transport path (rejected
with 401, as intended, no billable tokens); exhaustive grep for the two
environment variables and the base-URL flag.
