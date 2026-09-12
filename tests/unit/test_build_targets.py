"""The `Makefile` and the coverage gate — Cycle 9, amendments **A-9.4**/**A-9.2**.

Two small deliverables that are easy to let rot, and one test module that stops
them rotting.

**The Makefile is a table of contents, not a second source of truth.** Plan §8's
Cycle 9 asks for ``make regression``, but this project documents
``python3 -m pytest tests/ -q`` in `CLAUDE.md`, the README and `STATUS.md`. A
Makefile that owned its own recipes would be a fourth place the invocation
lives, and the first time someone changed one and not the others they would
disagree silently — a contributor running ``make test`` and a maintainer
running the documented command would be testing different things. So every
recipe wraps a command the documentation already names, and
:func:`test_every_make_target_wraps_a_documented_command` is what makes that
checkable rather than merely intended.

**A gate that can be weakened invisibly is not a gate.** The coverage floor and
the omit list live in ``pyproject.toml`` in the open, and the tests below pin
both. This is §9.4's reasoning about goldens applied to the threshold itself:
lowering it must be a reviewed diff, not a quiet edit inside a recipe.

The omit list is the part worth guarding. A-9.2 omits the per-package
``__main__.py`` debug views — superseded by Cycle 8's unified CLI, and one of
them (``routing/__main__.py``) is never imported by the suite at all. That is a
defensible exclusion of *debug entry points*; it would not be defensible if it
quietly grew to cover a module of real logic, which is exactly what
:func:`test_coverage_omits_only_debug_entry_points` refuses to allow.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: Where a documented command may legitimately be written down. A recipe has to
#: appear in at least one of these, so `make` can never become the only place
#: that knows how to run something.
DOC_SOURCES = (
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "dev" / "20260801_145839_complete_development_plan_lexml_non_statutory_parser" / "STATUS.md",
)


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _documentation() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in DOC_SOURCES if p.exists()
    )


def _recipes() -> dict[str, list[str]]:
    """``target -> [recipe lines]``, with line continuations folded.

    Parsed rather than imported because a Makefile has no other reader here,
    and a regex over the real file is what keeps this test honest about the
    file that actually ships.
    """
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    pending = ""

    for raw in _makefile_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("\t"):
            if current is None:
                continue
            line = pending + raw.strip()
            if line.endswith("\\"):
                pending = line[:-1].strip() + " "
                continue
            pending = ""
            recipes.setdefault(current, []).append(line)
            continue
        pending = ""
        match = re.match(r"^([A-Za-z0-9_ /-]+):(?!=)", raw)
        if match:
            # `test regression:` declares two targets sharing one recipe.
            names = match.group(1).split()
            current = names[0]
            for name in names:
                recipes.setdefault(name, [])
            # Point every alias at the same list object so the recipe is shared.
            for name in names[1:]:
                recipes[name] = recipes[current]
    return recipes


def test_the_makefile_exists() -> None:
    assert MAKEFILE.is_file(), "Cycle 9 (A-9.4) delivers a Makefile"


def test_the_documented_targets_are_all_present() -> None:
    """The targets the cycle promised, and the plan's `make regression`."""
    recipes = _recipes()
    for target in ("help", "test", "regression", "coverage", "goldens", "schemas", "corpus", "fixtures"):
        assert target in recipes, f"missing target: {target}"


def test_make_targets_are_phony() -> None:
    """No target may be mistaken for a file it builds.

    Every one of these produces no file of its own name, so without `.PHONY` a
    stray file called `test` or `coverage` in the repository root would make
    `make` declare the target up to date and run nothing — a suite that
    silently does not run is worse than one that fails.
    """
    phony = set()
    for line in _makefile_text().splitlines():
        if line.startswith(".PHONY:"):
            phony.update(line.split(":", 1)[1].split())

    for target in _recipes():
        assert target in phony, f"{target} is not declared .PHONY"


@pytest.mark.parametrize(
    "target",
    ["test", "regression", "coverage", "goldens", "schemas", "corpus", "fixtures"],
)
def test_every_make_target_wraps_a_documented_command(target: str) -> None:
    """A recipe must invoke something the documentation already names.

    Checked on the recipe's *script*, with `$(PYTHON)` resolved, so a target
    that quietly grew its own pipeline would fail here rather than become a
    second way to run the project.
    """
    documentation = _documentation()
    recipe = " ".join(_recipes()[target]).replace("$(PYTHON)", "python3")

    # The distinguishing fragment of each recipe — the script or module it
    # runs — must appear verbatim in the documentation.
    fragments = {
        "test": "python3 -m pytest tests/ -q",
        "regression": "python3 -m pytest tests/ -q",
        "coverage": "--cov-fail-under=85",
        "goldens": "python3 scripts/regen_goldens.py",
        "schemas": "python3 scripts/build_proposed_schemas.py --check",
        "corpus": "python3 -m lexml_nonstat corpus",
        "fixtures": "python3 scripts/record_linker_fixtures.py --check",
    }
    fragment = fragments[target]
    assert fragment in recipe, f"{target}'s recipe no longer runs {fragment!r}"
    assert fragment in documentation, (
        f"{target} runs {fragment!r}, which no documentation names — "
        "the Makefile must not be the only place a command lives (A-9.4)"
    )


def test_no_recipe_writes_into_the_vendored_schemas() -> None:
    """`lexml/` is byte-identical to upstream and never modified (CLAUDE.md).

    `make schemas` *checks* the generated `lexml-proposed/`; nothing here may
    write to either, because schema drift is only detectable while the vendored
    copy is untouched.
    """
    text = _makefile_text()
    for line in text.splitlines():
        if not line.startswith("\t"):
            continue
        assert "> lexml/" not in line and "rm " not in line, (
            f"recipe line writes into vendored schemas: {line.strip()!r}"
        )


# ---------------------------------------------------------------------------
# the coverage gate (A-9.2)
# ---------------------------------------------------------------------------


def test_coverage_floor_is_eighty_five() -> None:
    """Plan §8 Cycle 9: "coverage ≥ 85% on hierarchy/, routing/, render/"."""
    recipe = " ".join(_recipes()["coverage"])
    assert "--cov-fail-under=85" in recipe

    for package in ("hierarchy", "routing", "render"):
        assert f"--cov=lexml_nonstat.{package}" in recipe, (
            f"the gate no longer measures {package}/, which the plan names"
        )


def test_coverage_omits_only_debug_entry_points() -> None:
    """The omit list may hide debug views — never a module of real logic.

    A-9.2 excludes the per-package ``__main__.py`` debug entry points, whose
    behaviour the CLI's own tests already cover through the library. If this
    list ever grew to omit anything else, the gate would be measuring a
    denominator someone chose to make easy.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    block = text.split("[tool.coverage.run]", 1)[1].split("[tool.", 1)[0]
    omitted = re.findall(r'"([^"]+)"', block.split("omit", 1)[1])

    assert omitted, "the omit list is empty — A-9.2 expects the __main__ views"
    for pattern in omitted:
        assert pattern.endswith("__main__.py"), (
            f"omit pattern {pattern!r} hides more than a debug entry point"
        )


def test_the_gate_is_not_in_the_default_pytest_run() -> None:
    """Spec decision N-6: coverage is an explicit command, not `addopts`.

    A gate inside the default run would slow every ordinary invocation and
    couple the suite to an optional dependency — and `pytest-cov` is declared
    in the `dev` extra precisely because a bare checkout need not have it.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    addopts = re.search(r'addopts\s*=\s*"([^"]*)"', text)
    assert addopts is not None
    assert "--cov" not in addopts.group(1)
