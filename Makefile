# Development targets — plan §8 Cycle 9, amendment A-9.4.
#
# Every recipe below is a **verbatim wrapper** around a command this project
# already documents in CLAUDE.md, the README or dev/*/STATUS.md. That is the
# whole design: a Makefile that owned its own recipes would become a second
# source of truth for how to run the suite, and the two would drift the first
# time someone changed one and not the other. This one is a table of contents.
#
# `tests/unit/test_build_targets.py` asserts exactly that — each recipe's
# command appears in the documentation — so the drift cannot happen silently.
#
# Nothing here writes into `lexml/` (vendored, byte-identical to upstream and
# never modified) or into `src/`.

PYTHON ?= python3

.PHONY: help test regression coverage goldens schemas corpus fixtures

help:
	@echo "targets:"
	@echo "  test / regression  the full suite"
	@echo "  coverage           the suite with the Cycle 9 coverage gate (>=85%)"
	@echo "  goldens            regenerate every golden (reviewed diff, plan 9.4)"
	@echo "  schemas            verify the generated schemas are current"
	@echo "  corpus             the batch corpus report over samples/"
	@echo "  fixtures           verify the recorded linker fixtures reproduce"

# The full suite. CLAUDE.md's documented invocation, unchanged.
test regression:
	$(PYTHON) -m pytest tests/ -q

# The Cycle 9 coverage gate (A-9.2): the three packages the plan names, with
# the per-package debug `__main__.py` views omitted in pyproject.toml — they
# are superseded by the Cycle 8 unified CLI, whose own tests cover the same
# behaviour through the library.
#
# Deliberately NOT in pytest's `addopts` (spec decision N-6): a gate inside the
# default run would slow every ordinary invocation and couple the suite to an
# optional dependency a bare checkout need not have.
coverage:
	$(PYTHON) -m pytest tests/ -q \
	  --cov=lexml_nonstat.hierarchy \
	  --cov=lexml_nonstat.routing \
	  --cov=lexml_nonstat.render \
	  --cov-report=term-missing \
	  --cov-fail-under=85

# Goldens regenerate only via this explicit command, never as a side effect of
# running tests, so a golden diff is always a reviewed behaviour change (§9.4).
goldens:
	$(PYTHON) scripts/regen_goldens.py

# `lexml-proposed/` is *generated*; --check verifies it is current. The patch
# failing to apply is the signal that upstream has shipped the change.
schemas:
	$(PYTHON) scripts/build_proposed_schemas.py --check

# Batch mode over the corpus (A-9.3). Defaults to samples/; point it at a
# directory of the 300+ documents to get the same report over those.
corpus:
	$(PYTHON) -m lexml_nonstat corpus samples/

# The recorded linker answers, verified to reproduce exactly (A-L.6). Needs the
# `linkertool` binary; without it the check reports the probe's diagnostic.
fixtures:
	$(PYTHON) scripts/record_linker_fixtures.py --check
