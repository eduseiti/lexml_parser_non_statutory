# Corpus expansion and repository conventions

- **Written:** 2026-09-12, Cycle 9 (deliverable G-6)
- **Plan:** [`dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`](../dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md) §8 Cycle 9
- **Audience:** anyone adding a document to the corpus, or adding a document to
  `docs/` or `dev/`

Two questions this repository gets asked, answered in one place: *how do I add a
document to the test corpus?* and *where does a new markdown file go?*

---

## Part 1 — Adding a document to the corpus

The 15 samples in `samples/` stand in for **300+** unseen documents. Adding the
sixteenth is not a matter of dropping a file in — the plan's Cycle 9 states the
recipe as **fixture + expected route + golden**, and each of the three exists to
catch a different kind of regression.

### Why three things and not one

| Artifact | Catches |
|---|---|
| **Fixture** — the source document | nothing on its own; it is the input the other two are about |
| **Expected route** — `generico` or `norma` | a routing regression: the document silently changing which emitter claims it |
| **Goldens** — the emitted artifacts | an output regression: the same route producing different bytes |

A fixture with no golden is a document the suite reads and never checks. A
golden with no expected route passes forever while the document quietly routes
the wrong way and the golden records the wrong emitter's output. Both are needed.

### The procedure

**1. Put the document in `samples/`.**

Supported suffixes are read from `ingest.READERS` — `.docx`, `.html`, `.htm`,
`.txt`. Name it so the stem is a usable identifier: the goldens, the segment
ids and the test parametrisation ids are all derived from it.

```bash
cp ~/novo_parecer.docx samples/par_cosit_99_20240115.docx
```

**2. Look at what the parser makes of it, before committing anything.**

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse --summary samples/par_cosit_99_20240115.docx
PYTHONPATH=src python3 -m lexml_nonstat dump-tree samples/par_cosit_99_20240115.docx
```

The summary names the profile, the route, the confidence and any warnings. This
is the step where you decide whether the answer is *right*, because everything
after it records the answer as correct by definition.

**3. Record the expected route.**

§4.4 is the ground truth for routing. Add the document to the routing
expectations in `tests/unit/test_routing.py` with its expected route, and — if
it is not obvious — a comment saying *why* that route is right. A route that
nobody can justify in a sentence is usually a bug being canonised.

**4. Generate the goldens.**

```bash
python3 scripts/regen_goldens.py par_cosit_99_20240115
```

This writes every kind for that one sample — currently eleven: `styled`,
`metadata`, `segment`, `hierarchy`, `routing`, `generico`,
`generico-aninhado`, `norma`, `segments`, `generico-linked`, `norma-linked`.
The `norma` kinds write only for a document that actually routes there, so most
documents produce nine files.

**5. Read the goldens you just generated.**

This is the step people skip, and it is the one that matters. A golden is a
recording: if the parser is wrong about this document, `regen_goldens.py`
faithfully records the wrong answer and the suite will defend it forever. Open
the emitted XML and check it says what the source document says.

Cycle 8's experience is the cautionary tale — an encoding bug made `SEÇÃO` read
as `SEÃÃO`, and **conservation could not detect it**, because both sides of the
comparison carried the same mojibake. Only reading the output found it.

**6. Run the suite.**

```bash
make test          # or: python3 -m pytest tests/ -q
```

The corpus-wide regression tests pick the new document up automatically — they
parametrise over `samples/*.docx` rather than over a list — so conservation,
cross-emitter equivalence, the three-way oracle and the CLI end-to-end tests all
extend to it with no further edit. If one of them fails, the new document has
found a real gap: that is the corpus doing its job.

**7. Commit the goldens with the document.**

```
samples/par_cosit_99_20240115.docx
tests/golden/*/par_cosit_99_20240115.*
tests/unit/test_routing.py
```

The golden diff belongs in the commit message: a golden change is a behaviour
change (§9.4), and a reviewer must be able to see which.

### If you are adding many documents at once

Use batch mode rather than fifteen invocations:

```bash
PYTHONPATH=src python3 -m lexml_nonstat corpus /path/to/corpus/
```

It walks the directory, isolates per-document failures — one unreadable file
never abandons the rest — and prints one reconciling report: routes, profiles,
emitters, blockers, warnings, the §7.4 decision counts and the resolved
reference tally. `--format=json` gives the same report as data, and
`--no-validate` trades schema validation for speed on a large sweep.

That report is the instrument for the question the 15 samples cannot answer:
**do the rules generalise?** A blocker or warning that is rare in `samples/` and
common at 300 documents is the signal to look at, and it is why the tallies are
ordered by count.

---

## Part 2 — `docs/` and `dev/`, and which one wins

### The split

| Folder | Holds | Status |
|---|---|---|
| **`dev/`** | the **executing** development plan and its cycle records | instructions |
| **`docs/`** | the **investigation record** that led to the plan | historical context |

**`dev/` wins when the two disagree** — and within `dev/`, the cycle *reports*
win over the plan itself, because they state what was actually built rather than
what was intended.

That ordering is not bureaucratic. `docs/` accumulates investigations that were
true when written and were sometimes superseded three cycles later; a reader who
follows a `docs/` finding over a cycle report will implement something the
repository has already moved past.

### The layout of `dev/`

```
dev/<plan>.md                       the plan; cycles numbered 0, 1, 2, 3, 4, 4b, 5, …
dev/<plan-file-stem>/               one subfolder per plan, holding:
    STATUS.md                       running index + the plan-amendments table
    *_cycle_<id>_spec.md            expanded goals + test plan, written BEFORE coding
    *_cycle_<id>_report.md          what was actually built, with test results
    *_cycle_<id>_changes.md         changes to already-delivered features
```

Documents only. **Tests go in `tests/`, never in `dev/`.**

### The timestamp rule

Every `.md` in `docs/` and `dev/` takes a `YYYYMMDD_HHMMSS_` prefix:

```bash
date +%Y%m%d_%H%M%S
```

One stamp per cycle, reused across that cycle's spec, report and changes files,
so they sort together.

**`STATUS.md` is the one exception** — it is an index that is continuously
updated, not a dated log, so it carries no prefix.

### Amendments

When implementation contradicts the plan, the plan is **amended visibly**, never
silently rewritten. An amendment gets an id (`A-<cycle>.<n>`), a row in
`STATUS.md`'s amendments table, and a paragraph in the plan saying what changed
and why. The amendment log is the reason a reader can trust the plan: every
place it diverged from its own first draft is recorded, with the measurement
that forced the divergence.

---

## The commands, in one place

```bash
make test          # python3 -m pytest tests/ -q              — the full suite
make coverage      # the suite with Cycle 9's ≥85% gate
make goldens       # python3 scripts/regen_goldens.py         — reviewed diff only
make schemas       # verify lexml-proposed/ is current
make corpus        # python3 -m lexml_nonstat corpus samples/ — the batch report
make fixtures      # verify the recorded linker fixtures reproduce
```

Every `make` target wraps a command documented in `CLAUDE.md` or the README
verbatim; `tests/unit/test_build_targets.py` asserts it, so the Makefile cannot
become a second source of truth for how to run this project.
