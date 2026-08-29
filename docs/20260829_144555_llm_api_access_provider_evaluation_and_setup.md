# LLM API access — which cycles need it, which provider to use, and how to set it up

**Date:** 2026-08-29
**Status:** investigation record (`docs/`), not an instruction. The executing
plan is `dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`;
where the two disagree, `dev/` wins.

**Originating request (verbatim):**

> Check the development plan captured in
> `dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`
> and indicate for which development cycle LLM access has to be available.
> Then, evaluate the currently available LLM API services, their cost and usage
> limits, as I want to find the best for me to use. Consider the main US
> vendors, as well as the Chinese main providers, only considering frontier
> models. Then, describe the step-by-step setup I need to execute in order to
> make the LLM API access available for completing the implementation; also,
> consider an easy-to-reproduce and publish setup, as I would like to make that
> available along with the tool, when it is completed.

---

## 1. Executive summary

1. **No cycle is blocked on LLM access.** The plan makes the referee
   *advisory* (§7.3 constraint 4) and *fail-safe* (constraint 5), and §9.3
   forbids networked calls in the regression suite. Every cycle can be
   completed, and the whole suite kept green, with `--referee=none` — which is
   the default and what the suite pins.
2. **The one cycle that *builds* the LLM path is Cycle 4b — and it is already
   complete** (2026-08-28, 3135 tests passing), built without a key, using
   hand-authored offline fixtures (A-4b.5).
3. **Where a live key genuinely earns its place** is three optional,
   deliberately-out-of-suite activities, none of which gates a cycle exit
   criterion: the §9.3 **live smoke test**, the **fixture refresh** documented
   in `tests/referee_fixtures/README.md`, and **Cycle 9's batch mode over the
   300+ corpus** — the only place where the referee stops being a formality,
   because that corpus is precisely the unseen population the rules were never
   tuned against.
4. **Recommended provider: DeepSeek `deepseek-v4-flash`** as primary
   (~US$0.22–0.44 / 1M input, ~US$0.66–1.32 / 1M output, cache hits at
   ~US$0.007–0.014 / 1M), with **Z.AI `GLM-4.7-Flash` (free)** as the
   zero-cost reproduction path for people who clone the published tool, and
   **Anthropic Claude or OpenAI GPT-5.6** as the quality reference for
   spot-checking adjudications. All are OpenAI-compatible except Anthropic —
   see §4.4.
5. **Realistic bill for the full 300+ corpus: well under US$1**, which is an
   order of magnitude below the plan §7.2 estimate of $1–3. See §5.

> **All prices below were checked on 2026-08-29** and are per 1M tokens in USD.
> Provider pricing moves quickly (DeepSeek introduced peak/off-peak billing on
> 2026-08-16; OpenAI cut GPT-5.6 rates on 2026-07-30; Gemini 3.7 Flash's
> introductory rate expires 2026-12-31). **Verify before committing** — plan
> §7.2 says exactly this.

---

## 2. Which cycles need LLM access

### 2.1 The plan's own position

The referee is a first-class component "from Cycle 4b onward" (§1, decision
#3), but three plan rules together mean *access* is never a prerequisite:

| Rule | Where | Consequence |
|---|---|---|
| Rules run first, always; referee only on flagged decisions | §7.3 c.1 | The deterministic path is complete without it |
| **Advisory** — may break ties, may not override a high-confidence verdict | §7.3 c.4 / invariant #9 | Absence cannot change a correct verdict |
| **Fail-safe** — error/timeout/malformed JSON ⇒ keep the rule verdict, log it | §7.3 c.5 | "A referee outage degrades quality, never availability" |
| `--referee=none` is the default; the suite pins it | §7.3 c.7, §9.3 | No test may reach the network |

Invariant #9 is asserted as an *attack* (A-4b.6): an adversarial referee
answering "own" to every question changes no sample's route. That is the
strongest possible statement that no cycle exit criterion depends on a key.

### 2.2 Cycle-by-cycle

| Cycle | State | Needs a live key? | Note |
|---|---|---|---|
| 0–4 | complete | no | No referee code exists before 4b |
| **4b** — Routing + LLM referee + telemetry | **complete** | **no — and it was in fact built without one** | `CachedAPIReferee`, cache, prompts, JSON constraints, telemetry all landed. Every test bullet is offline: recorded fixtures, injected transport, `NullReferee`. A-4b.5 records the decision, taken with the user, to hand-author the four fixtures rather than make an outbound call |
| 5 | complete | no | Emitter |
| 5b, 6, 7 | not started | no | Emitters and segmentation output |
| **8** — Generalisation, robustness, CLI | not started | **no, but this is where the key becomes *usable*** | The unified `cli.py` lands here. `--referee` must be reachable from the real CLI, and "confidence and referee status surfaced in output" is a test bullet. All satisfiable with `--referee=none` |
| **9** — Regression consolidation and corpus scale-out | not started | **no for the suite; yes in practice for the corpus run** | Two bullets pull in opposite directions and both are real: *"referee disabled ⇒ suite still green (no network dependency anywhere)"* and *"**batch mode over the 300+ corpus** with an aggregate decisions report"*. The suite must pass keyless; the corpus run is where the referee stops being decorative |

### 2.3 The honest answer

**Strictly: none.** **Practically: Cycle 9**, and optionally at any point from
now on for the three out-of-suite activities below.

The reason Cycle 9 is the real answer is the corpus arithmetic. On the 15
samples the referee's entire workload is **four questions** (A-4b.3), and all
four rule verdicts are already correct — so the referee confirms rather than
rescues. The 300+ documents are the population the rules were never tuned
against; §1 decision #3 makes rule-vs-referee disagreement telemetry "a
deliverable, not a debugging aid", and that telemetry is empty without a
referee that actually answers.

### 2.4 The three activities that consume a key

| Activity | Where documented | Frequency | Volume |
|---|---|---|---|
| **Live smoke test** — `@pytest.mark.live`, excluded by default | §9.3 | on demand, verifying wiring | 1–2 calls |
| **Fixture refresh** — explicit command, reviewed diff, never automatic | `tests/referee_fixtures/README.md` | on a provider or model change | 4 calls (the corpus's whole flagged set) |
| **Corpus batch run** — 300+ documents, aggregate decisions report | Cycle 9 | once per rule-tuning iteration | see §5 |

Note the fixture-refresh command already exists and already reads the
environment variable, so nothing needs building:

```bash
export LEXML_REFEREE_API_KEY=…
python3 -m lexml_nonstat.routing --referee=api \
        --referee-model=deepseek-v4-flash \
        --referee-cache=tests/referee_fixtures \
        --decisions-report samples/*.docx
git diff tests/referee_fixtures/    # review before committing
```

---

## 3. What the code already expects

Reading `src/lexml_nonstat/referee/api.py` and `routing/__main__.py` — the
integration surface is small and already fixed by Cycle 4b:

| Item | Value | Where |
|---|---|---|
| Protocol | OpenAI-compatible `POST {base_url}/chat/completions` | `api.py` |
| Auth | `Authorization: Bearer <key>` | `api.py` |
| Env var | **`LEXML_REFEREE_API_KEY`** | `routing/__main__.py:130` |
| Default base URL | `https://api.deepseek.com/v1` | `api.DEFAULT_BASE_URL` |
| Default model | `deepseek-chat` | `api.DEFAULT_MODEL` |
| Structured output | `response_format: {"type": "json_object"}` | `api.py` |
| Temperature | `0.0` — invariant #4 forbids sampling | `api.TEMPERATURE` |
| Timeout | 30 s, then abstain | `api.py` |
| HTTP client | `httpx>=0.27`, **imported lazily** inside the transport | `pyproject.toml` extra `referee` |
| Prompt bound | excerpt ≤ 1200 chars, context ≤ 600 chars | `prompts.py` |
| Cache key | `(model, kind, excerpt, ctx)` hash | `cache.cache_key` |

Three consequences worth stating:

- **`base_url` is not yet a CLI flag.** `--referee-model` exists;
  `--referee-base-url` does not — a non-DeepSeek provider currently needs a
  code-level `base_url` or a small CLI addition. This is the one gap between
  today's code and a multi-provider setup, and it belongs in **Cycle 8**
  (§7.1 below).
- **`deepseek-chat` is a stale alias.** DeepSeek's current lineup is
  `deepseek-v4-flash` / `deepseek-v4-pro`; `DEFAULT_MODEL` should be revisited
  when the key is first wired up. Because the cache key covers the model, this
  is additive — a new model writes new fixture files rather than overwriting
  the existing ones.
- **The cache key covering the model is what makes provider comparison cheap
  and safe.** Running two providers over the same corpus produces two disjoint
  fixture sets and a reviewable diff, exactly as the fixtures README describes.

---

## 4. Provider evaluation

Scope as requested: **frontier models only**, main US vendors and main Chinese
providers. Prices per 1M tokens, USD, checked 2026-08-29.

### 4.1 US vendors

| Vendor | Frontier model | Input | Cached in | Output | Context | OpenAI-compatible |
|---|---|---|---|---|---|---|
| **Anthropic** | Claude Opus 5 | $5.00 | ~$0.50 (0.1×) | $25.00 | 1M | ✗ (own SDK/wire format) |
| Anthropic | Claude Sonnet 5 | $2.00 | ~$0.20 | $10.00 | 1M | ✗ |
| Anthropic | Claude Haiku 4.5 | $1.00 | ~$0.10 | $5.00 | 200K | ✗ |
| **OpenAI** | gpt-5.6-sol | $4.00 | $0.40 | $20.00 | — | ✓ (native) |
| OpenAI | gpt-5.6-terra | $2.00 | $0.20 | $12.00 | — | ✓ |
| OpenAI | gpt-5.6-luna | $0.20 | $0.02 | $1.20 | — | ✓ |
| OpenAI | gpt-5 | $1.25 | $0.125 | $10.00 | — | ✓ |
| **Google** | Gemini 3.1 Pro | $2.00 (→$4.00 >200K) | — | $12.00 (→$18.00) | 1M | ✓ (compat layer) |
| Google | Gemini 3.7 Flash | $0.75 * | — | $3.75 * | 1M | ✓ |
| Google | Gemini 2.5/3.x Flash tiers | **free tier available** | — | free | — | ✓ |

\* Gemini 3.7 Flash introductory rate, through 2026-12-31; doubles to
$1.50/$7.50 on 2027-01-01.

### 4.2 Chinese providers

| Vendor | Frontier model | Input (miss) | Cache hit | Output | Context | OpenAI-compatible |
|---|---|---|---|---|---|---|
| **DeepSeek** | deepseek-v4-flash | $0.22 off-peak / $0.44 peak | $0.007–0.014 | $0.66 / $1.32 | 1M | ✓ |
| DeepSeek | deepseek-v4-pro | $0.66 / $1.32 | $0.022–0.044 | $1.98 / $3.96 | 1M | ✓ |
| **Alibaba / Qwen** | Qwen3.8 Max | $2.00 | $0.25 | $6.00 | — | ✓ |
| Alibaba / Qwen | Qwen3.7 Max | $1.25 | — | $3.75 | — | ✓ |
| Alibaba / Qwen | Qwen3.5 Flash | $0.10 | — | $0.40 | — | ✓ |
| **Zhipu / Z.AI** | GLM-5.3 | $1.40 | $0.26 | $4.40 | — | ✓ |
| Zhipu / Z.AI | GLM-4.7 | $0.60 | $0.11 | $2.20 | — | ✓ |
| Zhipu / Z.AI | **GLM-4.7-Flash** | **free** | free | **free** | — | ✓ |
| **Moonshot / Kimi** | Kimi K3 | (see note) | — | — | 1M | ✓ |
| **MiniMax** | MiniMax-M2 | ~$0.26 | — | ~$1.02 | 205K | ✓ |

DeepSeek peak hours are 01:00–04:00 and 06:00–10:00 UTC, Mon–Fri; all other
hours are off-peak at half price. **For Brazil (UTC−3), peak is 22:00–01:00 and
03:00–07:00 local** — a corpus batch run started in the Brazilian working day
lands entirely in off-peak. Moonshot's per-model figures are on per-model pages
this review did not resolve to a firm number; Kimi K3 is included for its 1M
context, not as a price recommendation.

### 4.3 Usage limits

| Provider | Free grant | Rate limits |
|---|---|---|
| **DeepSeek** | 5M tokens on signup, no card, ~30 days | **No published RPM/TPM quota** — "will try its best to serve every request"; concurrency-capped (2,500 concurrent for v4-flash, 500 for v4-pro) and degradable under load |
| **Z.AI** | GLM-4.7-Flash / GLM-4.5-Flash **permanently free** | Provider-set; adequate for a 4-question workload |
| **Alibaba / Qwen** | 1M tokens **per model**, 90 days, International (Singapore) endpoint | Standard tiered |
| **Google** | Recurring free tier on Flash models | Free tier is rate-limited and **free-tier content is used to improve Google's products** — disqualifying for third-party legal documents, see §4.5 |
| **OpenAI** | none by default | Tiered RPM/TPM by spend history |
| **Anthropic** | none by default | Tier 1: 50 RPM, 500K input TPM, 80K output TPM. Tier 2: 1,000 RPM, 2M input TPM. Cache reads don't count toward input TPM on most models |

Every one of these is comfortably above what this project needs. The workload —
see §5 — is a few thousand requests **total**, not per minute, and the disk
cache means a rerun costs nothing.

### 4.4 Fit against this codebase

| Criterion | Why it matters here | Winner |
|---|---|---|
| **OpenAI-compatible endpoint** | `api.py` is one client for all such providers; Anthropic needs a second `Referee` implementation (~80 lines, its own wire format) | All but Anthropic |
| **`response_format: json_object`** | `_parse` abstains on non-JSON; native JSON mode removes a whole abstention class | DeepSeek, OpenAI, Qwen, Z.AI, Moonshot |
| **`temperature: 0`** | Invariant #4. Note some frontier reasoning models (Claude Opus 5, Fable 5, Sonnet 5) **reject `temperature` outright** — sampling params were removed | DeepSeek, Qwen, Z.AI, GPT-5.x |
| **Prefix caching** | Bounded prompts with a fixed system prefix; cache hits at ~3% of miss price | DeepSeek (largest discount ratio) |
| **Multilingual pt-BR legal prose** | The actual task | Qwen and Claude strongest; DeepSeek adequate and cheap |
| **Cost at corpus scale** | §5 | DeepSeek, then Z.AI free tier |
| **Reproducible by a stranger** | Publishing requirement | Z.AI free tier (no card), then DeepSeek (no card for the grant) |

### 4.5 Data-handling caveat — state it in the published README

The corpus is Brazilian public-administration documents (pareceres, atos
declaratórios, portarias, súmulas) — **published, public-domain legal texts**,
so there is no confidentiality bar to sending excerpts to any provider. Two
things are still worth writing down for whoever reproduces this:

- Prompts carry **at most 1200 characters of excerpt plus 600 of context**
  (`prompts.py`), never a whole document — a Cycle 4b test bullet asserts
  "prompts contain no PII beyond the excerpt".
- **Google's free tier uses submitted content to improve its products.** For
  third-party documents that is the wrong default even when the text is public;
  use the paid tier if choosing Gemini, or choose another provider.

### 4.6 Recommendation

| Role | Choice | Reason |
|---|---|---|
| **Primary** | **DeepSeek `deepseek-v4-flash`** | It is already the code's default base URL. Cheapest frontier option by a wide margin, 1M context, no RPM quota, aggressive prefix caching, 5M-token signup grant covers the whole project before a card is ever needed. Off-peak = Brazilian working hours |
| **Zero-cost reproduction** | **Z.AI `GLM-4.7-Flash`** | Genuinely free, OpenAI-compatible, so a stranger cloning the repo can exercise `--referee=api` end-to-end with no payment method. This is what makes the published setup reproducible rather than merely documented |
| **Quality reference** | **Claude Opus 5** or **gpt-5.6-terra** | For a one-off adjudication of the four flagged decisions plus any Cycle 9 disagreements, to check the budget model is not systematically wrong. ~US$0.02 for the whole exercise. Anthropic needs an `AnthropicReferee` (§7.1); OpenAI works through the existing client with only a base URL and model change |
| **Upgrade path if quality disappoints** | **Qwen3.8 Max** | Strongest multilingual reputation of the OpenAI-compatible options; 3× DeepSeek's input price is still immaterial at this volume |

**Do not build a local `llama.cpp` fallback for cost reasons.** Plan §7.2
already found the GTX 980 Ti (6 GB, Maxwell, no bf16) unsuitable, and at
US$0.10 per corpus run the economic case for local inference is nil. Keep
`LocalReferee` for the offline/air-gapped case it was written for.

---

## 5. Cost sizing — measured, not estimated

Plan §7.2 estimated ~$1–3 for the corpus. Cycle 4b's actual measurement lets us
do much better than an estimate.

**Measured on the 15 samples (A-4b.3):** 415 paragraphs and 25 quoted articles
produce **4 flagged decisions**. That is **0.27 flagged decisions per document**
— because the declared quote band (A-4.1) carries 24 of the 25 quoted articles
on its own.

**Per-question token cost:** bounded at 1200 + 600 chars plus the templates ≈
**~1.2k input tokens**, and a `{verdict, confidence, rationale}` object ≈
**~100 output tokens**.

**Scaling to 300 documents.** The 15 samples are not a random draw, so scale
pessimistically:

| Scenario | Flagged/doc | Questions | Input tok | Output tok | Cost (v4-flash, off-peak) |
|---|---|---|---|---|---|
| Corpus rate holds | 0.27 | ~81 | ~97K | ~8K | **~$0.03** |
| Plan §7.2's assumption | 20 | 6,000 | 7.2M | 600K | **~$1.98** |
| Pessimistic middle | 3 | 900 | 1.1M | 90K | **~$0.30** |

Even the plan's own worst case costs under US$2, and DeepSeek's **5M-token
signup grant alone covers the pessimistic middle scenario several times over**.
Prefix caching (the system prompt is identical on every call) cuts the input
side by a further ~95% on repeat runs, and the disk cache makes a *rerun* free
by construction.

**Conclusion: budget US$5 and never think about it again.** The §10 risk row
"LLM cost/availability — low" is, if anything, understated.

---

## 6. Step-by-step setup

### 6.1 Get a key (DeepSeek — primary, ~5 minutes)

1. Go to `https://platform.deepseek.com/`, sign up (email or Google). The
   signup grant needs no payment method.
2. **API keys → Create new API key**. Copy it immediately; it is shown once.
3. Note the current model id from `https://api-docs.deepseek.com/quick_start/pricing`
   — as of 2026-08-29 it is `deepseek-v4-flash`, **not** the `deepseek-chat`
   alias baked into `api.DEFAULT_MODEL`.

### 6.2 Get a free key (Z.AI — reproduction path, ~5 minutes)

1. Go to `https://z.ai/` (or `https://docs.z.ai/`), sign up, open the API
   keys page.
2. Create a key. Base URL is `https://api.z.ai/api/paas/v4`, model
   `glm-4.7-flash`, price zero.
3. This is the key you name in the published README so that someone cloning
   the tool can run `--referee=api` without a payment method.

### 6.3 Install the optional dependency

The referee extra is deliberately optional — `api.py` imports `httpx` lazily,
inside the transport, so the package imports fine without it.

```bash
python3 -m pip install 'httpx>=0.27'
# or, once the package is installable:  pip install -e '.[referee]'
```

### 6.4 Provide the key to the process

The code reads **`LEXML_REFEREE_API_KEY`** (`routing/__main__.py:130`) and
nothing else. Two mechanisms, in order of preference:

**A. A `.env` file, git-ignored** — the reproducible option, and the one to
publish:

```bash
cp .env.example .env          # see §7.2 for the file to create
$EDITOR .env                  # paste the key
set -a; . ./.env; set +a      # export into the current shell
```

**B. Shell export**, for a one-off:

```bash
export LEXML_REFEREE_API_KEY='sk-…'
```

Never place the key on a command line (it lands in shell history and in `ps`),
and never in `pyproject.toml`, a test, or a fixture.

### 6.5 Add `.env` to `.gitignore`

**Do this before creating `.env`, not after.** The repository's `.gitignore`
currently covers bytecode, pytest and packaging artifacts only.

```gitignore
# Secrets. The referee's API key is read from LEXML_REFEREE_API_KEY; .env is
# the local, never-committed source of it. .env.example is committed and holds
# placeholders only.
.env
.env.*
!.env.example
```

### 6.6 Verify the wiring

Cheapest possible check — a single flagged decision on one sample, ~1.2k input
tokens, a fraction of a US cent:

```bash
python3 -m lexml_nonstat.routing --referee=api \
        --referee-model=deepseek-v4-flash \
        --referee-cache=/tmp/lexml_referee_cache \
        --decisions-report --log=info \
        samples/par_cosit_26_20000629.docx
```

Expected: `referee : consulted=3 overrode=0`, and a decisions report whose
counts reconcile per A-4b.4 (`agreed + overrode + overruled + abstained ==
consulted`, `consulted ≤ flagged`).

**Reading the failure modes** — the referee never raises, so a
misconfiguration shows up as an abstention with a reason in the log rather than
as a traceback:

| Symptom | Cause |
|---|---|
| `no API key configured; referee unavailable` | `LEXML_REFEREE_API_KEY` not exported into *this* shell |
| `referee transport unavailable: No module named 'httpx'` | §6.3 not done |
| `HTTPStatusError: … 401` | Bad or revoked key |
| `HTTPStatusError: … 404` | Wrong base URL, or a model id the provider does not know (`deepseek-chat` on the v4 lineup) |
| `non-JSON content: …` | Provider ignored `response_format` — see §7.1 |
| `consulted=0` | Nothing was flagged; you picked a sample with no low-confidence decision. Use `par_cosit_26_20000629` |

### 6.7 Confirm the suite is unaffected

Non-negotiable, and the point of the whole design:

```bash
unset LEXML_REFEREE_API_KEY
python3 -m pytest tests/ -q          # must stay green — §9.3, invariant #9
```

### 6.8 Refresh the fixtures (only when deliberately changing provider/model)

Follow `tests/referee_fixtures/README.md` verbatim: run the refresh command,
`git diff tests/referee_fixtures/`, review, and **drop the `meta.origin`
hand-authored line** from any file that is now genuinely recorded. A different
model writes new files rather than overwriting the existing ones, because the
cache key covers the model.

---

## 7. Making the setup reproducible and publishable

The publishing goal changes two things: the tool must be **provider-agnostic in
configuration** (not just in code comments), and a stranger must be able to run
it **without a payment method**.

### 7.1 Code changes to propose for Cycle 8

None of these are needed to *finish* the implementation; all of them are needed
to *publish* it well. They are small, additive, and belong with Cycle 8's
unified CLI. **They are proposals for the user's decision, not amendments** —
per CLAUDE.md, plan changes are agreed, not assumed.

| # | Change | Why |
|---|---|---|
| 1 | **`--referee-base-url`**, defaulting to `LEXML_REFEREE_BASE_URL` then `api.DEFAULT_BASE_URL` | Today only the model is switchable; a non-DeepSeek provider needs a code edit. One flag makes every OpenAI-compatible provider a configuration choice, which is exactly what `api.py`'s docstring promises |
| 2 | Read **`LEXML_REFEREE_MODEL`** as the default for `--referee-model` | Lets `.env` alone fully describe a provider — the flags stay available for overrides |
| 3 | Refresh `DEFAULT_MODEL` from `deepseek-chat` to the current id | The alias predates the v4 lineup. Additive: the cache key covers the model |
| 4 | Optional `python-dotenv` load of `.env` when present, behind a `try/except ImportError` | Removes the `set -a; . ./.env` step for people who don't know it. Must stay optional — the package's hard dependencies are `lxml` and `python-docx` and should remain so |
| 5 | An **`AnthropicReferee`** implementing the same `Referee` protocol | Anthropic is not OpenAI-compatible, and it is the strongest quality reference. ~80 lines behind the existing protocol; the `adjudicate`/cache/telemetry layers are untouched |
| 6 | A `--referee-json-mode=auto\|on\|off` escape hatch | `response_format: {"type":"json_object"}` is sent unconditionally; a provider that rejects the field currently fails as an abstention with an opaque reason |

Changes 1–3 are the minimum for a credible published tool; 4–6 are quality of
life.

### 7.2 Files to add to the repository

**`.env.example`** — committed, placeholders only, doubling as the provider
cheat-sheet:

```bash
# LexML non-statutory parser — LLM referee configuration.
#
# The referee is ADVISORY and OFF BY DEFAULT (--referee=none). The parser and
# its whole test suite work with no key at all; this file only enables the
# optional --referee=api path. Copy to .env and fill in. NEVER commit .env.
#
#   cp .env.example .env && $EDITOR .env
#   set -a; . ./.env; set +a

LEXML_REFEREE_API_KEY=

# --- Provider presets (any OpenAI-compatible endpoint works) ---------------
#
# DeepSeek — recommended. 5M free tokens on signup, no card.
#   https://platform.deepseek.com/
LEXML_REFEREE_BASE_URL=https://api.deepseek.com/v1
LEXML_REFEREE_MODEL=deepseek-v4-flash
#
# Z.AI GLM — free model, no payment method needed. Use this to reproduce the
# published results at zero cost.  https://z.ai/
# LEXML_REFEREE_BASE_URL=https://api.z.ai/api/paas/v4
# LEXML_REFEREE_MODEL=glm-4.7-flash
#
# OpenAI.  https://platform.openai.com/
# LEXML_REFEREE_BASE_URL=https://api.openai.com/v1
# LEXML_REFEREE_MODEL=gpt-5.6-terra
#
# Alibaba Qwen (International / Singapore endpoint).
# LEXML_REFEREE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
# LEXML_REFEREE_MODEL=qwen3.8-max
#
# Moonshot Kimi.  https://platform.kimi.ai/
# LEXML_REFEREE_BASE_URL=https://api.moonshot.ai/v1
# LEXML_REFEREE_MODEL=kimi-k3
#
# Anthropic Claude is NOT OpenAI-compatible — it needs AnthropicReferee
# (see docs/20260829_144555_…), not a base-URL change.
```

**A `## LLM referee (optional)` section in the published README**, carrying,
in this order: *the parser needs no API key*; how to get a free Z.AI key; the
`.env` flow; the verification command; the reproduction claim below.

**A reproduction statement**, so a reader knows what a rerun is expected to
show:

> The 15-sample corpus flags **four** decisions. The recorded fixtures in
> `tests/referee_fixtures/` answer all four, so the full test suite runs
> offline and deterministically with `--referee=none`. Enabling
> `--referee=api` on this corpus changes no document's route — invariant #9,
> asserted as an adversarial attack in `tests/unit/test_referee_protocol.py`.

### 7.3 Why publishing the referee this way is defensible

Three properties already in the design carry the publication, and are worth
naming explicitly in the paper as well as the README:

- **Reproducible without a key.** Recorded fixtures plus a read-only cache mean
  a reviewer regenerates every result offline. The referee is a documented,
  auditable component, not an unreproducible dependency.
- **Reproducible without *this* provider.** The cache key covers the model, so
  a different provider's answers land in different files and a comparison is a
  reviewable diff — the fixtures README's design intent, and directly useful
  for a paper's ablation.
- **Auditable.** §7.4's `DecisionRecord` and `--decisions-report` mean every
  adjudication is countable, and every override is a `WARN` carrying both
  verdicts plus the rationale. A reader can ask "how often did the LLM change
  the answer?" and get a number.

---

## 8. Open questions for the user

1. **Provider.** Adopt DeepSeek as primary and Z.AI free as the published
   reproduction path, as recommended in §4.6?
2. **Cycle 8 additions.** Are §7.1's changes 1–3 (base-URL flag, env defaults,
   model-id refresh) accepted as Cycle 8 scope? They are the minimum for a
   provider-agnostic published tool.
3. **`AnthropicReferee`** (§7.1 change 5) — worth building for the quality
   reference, or is an OpenAI-compatible reference model (gpt-5.6-terra,
   Qwen3.8 Max) sufficient?
4. **Fixture refresh.** Should the four hand-authored fixtures be replaced by
   genuinely recorded ones once a key exists? A-4b.5's reasoning still holds
   (they test plumbing, not the model), but recorded fixtures would be a
   stronger claim in a publication.
5. **Cycle 9 corpus run.** Is a live referee pass over the 300+ corpus part of
   Cycle 9's plan, given that its disagreement telemetry is what §1 decision #3
   says the whole design exists to produce?

---

## 9. Sources

Pricing and limits, checked 2026-08-29:

- [DeepSeek — official pricing](https://api-docs.deepseek.com/quick_start/pricing)
- [Z.AI / Zhipu GLM — official pricing](https://docs.z.ai/guides/overview/pricing)
- [OpenAI — official API pricing](https://developers.openai.com/api/docs/pricing)
- [Google Gemini API — official pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Moonshot / Kimi — platform docs](https://platform.kimi.ai/docs/pricing/chat)
- [Qwen API pricing 2026 (BenchLM)](https://benchlm.ai/alibaba/api-pricing)
- [Qwen pricing overview (eesel)](https://www.eesel.ai/blog/qwen-pricing)
- [LLM API rate limits 2026 — OpenAI, Anthropic, DeepSeek (Requesty)](https://www.requesty.ai/blog/rate-limits-for-llm-providers-openai-anthropic-and-deepseek)
- [Claude API token limit tiers (MindStudio)](https://www.mindstudio.ai/blog/claude-api-token-limits-increase-tier-breakdown)
- [MiniMax M2 pricing (OpenRouter)](https://openrouter.ai/minimax/minimax-m2)
- [Gemini 3.1 Pro pricing (Morph)](https://www.morphllm.com/gemini-api-pricing)
- [DeepSeek free tier and grants (Price Per Token)](https://pricepertoken.com/endpoints/deepseek/free)

Anthropic model ids and rates are from the `claude-api` skill's cached model
table (2026-06-24), cross-checked against the rate-limit sources above.

Repository sources: plan §1, §7, §9.2, §9.3, §10; Cycle 4b spec/report and
amendments A-4b.1–A-4b.6; `src/lexml_nonstat/referee/{api,prompts,cache}.py`;
`src/lexml_nonstat/routing/__main__.py`; `tests/referee_fixtures/README.md`;
`pyproject.toml`.
