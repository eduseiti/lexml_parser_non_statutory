# lexml-nonstat

Converts Brazilian **non-statutory** legal documents — *documentos não
articulados*: pareceres, atos declaratórios, older portarias, súmulas — from
DOCX, HTML or plain text into valid [LexML](https://www.lexml.gov.br/) XML,
preserving the hierarchy the document actually has rather than imposing the
article/paragraph structure of a statute.

Output validates against **both** official schemas, `lexml-br-rigido.xsd` and
`lexml09-flexivel.xsd`.

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse samples/par_cosit_26_20000629.docx > out.xml
```

That is the command that produces LexML XML. Everything else below is detail.

---

## Why this exists

The reference LexML parser handles *articulated* documents — laws, decrees,
anything whose skeleton is `Art. 1º … Art. 2º …`. A large share of Brazilian
administrative legal output is not shaped that way: a parecer argues in
numbered paragraphs and quotes statutes it does not enact; a súmula is a single
holding; an older portaria mixes both. Feeding those to an articulated parser
produces either a refusal or, worse, a plausible-looking document in which
quoted statute has been silently promoted to the document's own articulation.

This parser routes each document to one of three targets, decides
quoted-versus-own article by article, and refuses to invent structure it cannot
evidence.

---

## Install

Requires Python **3.10+**. Runtime dependencies are `lxml` and `python-docx`.

```bash
git clone <this repo> && cd lexml_parser_non_statutory
python3 -m pip install -e .
lexml-nonstat parse samples/par_cosit_26_20000629.docx > out.xml
```

**Or run without installing** — the way the test suite does:

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse samples/…docx
```

The package is deliberately *not* installed in development: `tests/conftest.py`
puts `src/` on `sys.path`, so `pytest` works from a clean checkout. The
consequence is that a bare `import lexml_nonstat` fails outside pytest unless
you set `PYTHONPATH=src` or install the package. Note it is `PYTHONPATH=src`
with the module named `lexml_nonstat` — **not** `src.lexml_nonstat`, which
resolves only by namespace-package accident and gives the package a different
dotted name than its own relative imports assume.

Optional extras:

```bash
pip install -e '.[referee]'   # httpx — only for the optional LLM referee
pip install -e '.[xslt]'      # saxonche — the reference XSLT stylesheets
pip install -e '.[dev]'       # pytest
```

---

## Commands

Eight subcommands over one argument vocabulary. **`parse` is the one that emits
LexML XML;** the other seven inspect, validate or explain.

| Command | What it does |
|---|---|
| **`parse`** | **render a document to LexML XML** |
| `dump-styled` | what ingestion saw — the styled paragraph stream |
| `dump-tree` | the inferred hierarchy, with `--why` for the evidence |
| `segment` | citable segments as CSV or JSONL |
| `validate` | validate existing XML against the LexML schemas |
| `list-profiles` | the registered document profiles |
| `decisions-report` | the rule-vs-referee summary (plan §7.4) |
| `capabilities` | what the schemas in this checkout permit |

Common options: `--profile`, `--emitter`, `--schema`, `--strict`, `-o/--out`,
`--format`, `-q/--quiet`. Run `--help` on any subcommand for the full set.

```bash
# XML to stdout; diagnostics go to stderr, so a redirect stays clean
PYTHONPATH=src python3 -m lexml_nonstat parse samples/pn_cst_38_19801031.docx > out.xml

# a whole bundle — including split annexes — into a directory
PYTHONPATH=src python3 -m lexml_nonstat parse -o out/ samples/*.docx

# a text summary instead of the XML: route, confidence, warnings
PYTHONPATH=src python3 -m lexml_nonstat parse --summary samples/*.docx

# citable segments
PYTHONPATH=src python3 -m lexml_nonstat segment --format=csv samples/port_mf_277_20180607.docx
```

**Exit codes:** `0` every document handled; `1` a document failed (unreadable
source, invalid output, or any warning under `--strict`); `2` the invocation
itself was wrong (unknown profile or emitter, unsupported format).

There is also a per-stage debug entry point, `python3 -m lexml_nonstat.routing`,
which prints one document's routing verdict with the gates and blockers behind
it. **It never emits XML** — use `parse` for that.

---

## LLM referee (optional)

**The parser needs no API key.** The deterministic rules produce valid output on
their own, the referee defaults to `none`, and the entire test suite runs
offline — `--referee=none` is pinned throughout. The referee only adjudicates
decisions the rules already flagged as low-confidence, it is advisory (it may
break a tie, never overturn a confident verdict), and it is fail-safe: a
timeout, an HTTP error or malformed JSON keeps the rule's answer and logs the
abstention. A referee outage degrades quality, never availability.

On the 15-sample corpus it changes nothing — see the reproduction note below.
Its value is at corpus scale, where it measures how well rules tuned on 15
documents generalise to 300+.

### Setting it up

```bash
pip install -e '.[referee]'      # httpx, imported lazily
cp .env.example .env             # then paste your key into it
set -a; . ./.env; set +a         # export into the current shell
```

`.env` is git-ignored; `.env.example` is committed and holds placeholders and
provider presets only. Three variables are read:

| Variable | Meaning |
|---|---|
| `LEXML_REFEREE_API_KEY` | the bearer token. Absent ⇒ every call abstains |
| `LEXML_REFEREE_BASE_URL` | any OpenAI-compatible endpoint root |
| `LEXML_REFEREE_MODEL` | the provider's model id |

Precedence is **flag > environment > built-in default**, so
`--referee-base-url` and `--referee-model` override `.env` for a single run.

**A free provider works.** Z.AI's `glm-4.7-flash` costs nothing and needs no
payment method, which is what lets anyone reproduce the referee path:

```bash
LEXML_REFEREE_BASE_URL=https://api.z.ai/api/paas/v4
LEXML_REFEREE_MODEL=glm-4.7-flash
```

DeepSeek is the default (`https://api.deepseek.com/v1`, `deepseek-v4-flash`)
and grants 5M tokens on signup without a card. A full run over 300+ documents
costs well under US$1.

### Verifying it works

```bash
PYTHONPATH=src python3 -m lexml_nonstat decisions-report \
    --referee=api --referee-cache=/tmp/lexml_referee_cache \
    samples/par_cosit_26_20000629.docx
```

This sample flags three decisions. A working key shows `put to a referee: 3`
with three under `referee agreed`. The referee never raises, so a
misconfiguration appears as an abstention with its reason, not a traceback:

| Symptom | Cause |
|---|---|
| `no API key configured` | `LEXML_REFEREE_API_KEY` not exported into *this* shell |
| `No module named 'httpx'` | the `referee` extra is not installed |
| `HTTPStatusError: … 401` | bad or revoked key |
| `HTTPStatusError: … 404` | wrong base URL, or a model id the provider does not know |
| `non-JSON content` | the provider ignored `response_format` |
| `put to a referee: 0` | nothing was flagged — pick a sample that has low-confidence decisions |

There is also a live smoke test, excluded from normal runs:

```bash
python3 -m pytest tests/unit/test_referee_live.py -m live -v
```

### Reproduction

> The 15-sample corpus flags **four** decisions. The recorded fixtures in
> `tests/referee_fixtures/` answer all four, so the full test suite runs
> offline and deterministically with `--referee=none`. Enabling
> `--referee=api` on this corpus changes no document's route — an invariant
> asserted adversarially in `tests/unit/test_referee_protocol.py`: a referee
> answering "own" to every question still reroutes nothing.

Because the cache key covers the model, a different provider's answers land in
different files rather than overwriting existing ones, so comparing two
providers is a reviewable diff.

---

## Validation and goldens

Output must validate against **both** schemas; `--schema=both` is the default.
The `lexml/` directory is the official schema set, vendored **byte-identical to
upstream and never modified** — that is what makes schema drift detectable.
`lexml-proposed/` is *generated* from it by
`scripts/build_proposed_schemas.py` and carries the maintainers' not-yet-released
change making `AgrupamentoHierarquico` prose-bearing and recursive; never
hand-edit it.

```bash
python3 -m pytest tests/ -q                        # the full suite
python3 scripts/build_proposed_schemas.py --check  # generated schemas current?
```

Goldens regenerate **only** on an explicit command, never as a side effect of
running tests — so a golden diff is always a reviewed behaviour change:

```bash
python3 scripts/regen_goldens.py                        # all kinds, all samples
python3 scripts/regen_goldens.py --kind=metadata        # one kind
python3 scripts/regen_goldens.py par_cosit_26_20000629  # one sample
```

---

## Repository layout

| Path | Contents |
|---|---|
| `src/lexml_nonstat/` | the package |
| `samples/` | 15 sample `.docx` — the corpus the tests run against |
| `tests/` | `unit/`, `golden/`, `regression/`, `referee_fixtures/` |
| `lexml/` | official schemas, vendored, never modified |
| `lexml-proposed/` | generated schemas with the recursive-grouping change |
| `scripts/` | golden regeneration, schema generation, reference XSLT |
| `dev/` | the executing development plan and its cycle records |
| `docs/` | the investigation record that led to the plan |

The 15 samples stand in for **300+** unseen documents, so the design prefers
genre-agnostic evidence fusion and graceful degradation over rules tuned to fit
the corpus.

---

## Status

Development follows a numbered plan in `dev/`; cycles 0–8 are complete and
Cycle 9 (regression consolidation and corpus scale-out) is not yet started. See
`dev/*/STATUS.md` for the current state.
