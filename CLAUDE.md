# LexML parser for non statutory documents

Python parser converting Brazilian **non-statutory** legal documents
("documentos não articulados" — pareceres, atos declaratórios, older portarias,
súmulas) from DOCX into valid LexML XML, preserving their internal hierarchy.

## Start here

Read these two, in this order, before doing anything else:

1. `dev/<plan>/STATUS.md` — which cycles are done, and the amendments log.
2. The plan document `dev/*.md` it links to — the authoritative development plan.

**`dev/` holds the executing plan; `docs/` holds the investigation record that
led to it.** When the two disagree, `dev/` wins — and the cycle *reports* in
`dev/<plan>/` win over the plan itself, because they state what was actually
built.

## Folders structure

- **dev**: the executing development plan and its cycle records. Managed by the
  `dev-cycle` skill (`.claude/skills/dev-cycle/SKILL.md`) — read it before
  implementing any cycle. Layout:
  - `dev/<plan>.md` — the plan; cycles are numbered `0, 1, 2, 3, 4, 4b, 5, …`
  - `dev/<plan-file-stem>/` — one subfolder per plan, holding:
    - `STATUS.md` — running index: cycle, state, test counts, spec/report links,
      plus the **plan amendments** table (`A-<cycle>.<n>`). No timestamp prefix.
    - `*_cycle_<id>_spec.md` — expanded goals + test plan, written before coding
    - `*_cycle_<id>_report.md` — what was actually built, with test results
    - `*_cycle_<id>_changes.md` — changes to already-delivered features
  - Documents only. Tests go in `tests/`, never here.
- **docs**: investigation and design records — schema analysis, design reviews,
  plan revisions. Historical context, not instructions.
- **lexml**: the official LexML schemas, vendored. **Byte-identical to upstream
  and never modified** — that is what makes schema drift detectable. Offline
  compilation works via a resolver mapping the three remote w3.org imports onto
  stubs in `src/lexml_nonstat/validate/stubs/`.
- **lexml-proposed**: *generated* schemas carrying the LexML maintainers'
  not-yet-released change making `AgrupamentoHierarquico` prose-bearing and
  recursive. Produced by `scripts/build_proposed_schemas.py` from `lexml/`;
  never hand-edit. See its README.
- **samples**: 15 sample `.docx` files — the whole corpus the tests run against.
- **scripts**: utilities (`regen_goldens.py`, `build_proposed_schemas.py`) and
  the community reference stylesheet `GeraCSVporArtigoPorAgrupador.xsl`.
- **src/lexml_nonstat**: the package. Subpackages appear as their cycle lands —
  `ingest/`, `model/`, `profile/`, `validate/` exist today.
- **tests**: `unit/`, `golden/`, and `conftest.py`. All test scripts created
  through the development cycles live here.

Every `.md` in `docs/` and `dev/` takes a `YYYYMMDD_HHMMSS_` prefix from
`date +%Y%m%d_%H%M%S`. `STATUS.md` is the one exception (it is an index, not a
dated log).

## Running things

```bash
python3 -m pytest tests/ -q                        # full suite, from the repo root
python3 scripts/build_proposed_schemas.py --check  # verify generated schemas current
```

The package is **not installed**; `tests/conftest.py` puts `src/` on `sys.path`,
so pytest works from a clean checkout but a bare `import lexml_nonstat` does
not. Outside pytest, use `PYTHONPATH=src`.

Goldens regenerate only via an explicit command — never as a side effect of
running tests, so a golden diff is always a reviewed behaviour change:

```bash
python3 scripts/regen_goldens.py                  # all kinds, all 15 samples
python3 scripts/regen_goldens.py --kind=metadata  # one kind
python3 scripts/regen_goldens.py par_cosit_26_20000629   # one sample
```

## Conventions that bite

- **Dual-schema validation.** Output must validate against *both*
  `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd`. Default `--schema=both`.
- **Never modify `lexml/`.** Patch by generating into a separate directory.
- **Cross-cutting invariants** (plan §9.2): validity, text conservation (no loss
  *or* duplication), reversibility, determinism, `id` uniqueness, no fabricated
  structure. These are asserted throughout the suite, not just at the end.
- **Ask rather than assume** on load-bearing decisions — an explicit requirement
  of the cycle process, not optional caution.
- The corpus is 15 samples standing in for **300+** unseen documents, so prefer
  genre-agnostic evidence fusion and graceful degradation over rules tuned to
  the samples.
