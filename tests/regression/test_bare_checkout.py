"""The bare checkout, and the absence of the network — Cycle 9, G-5 (A-R.9).

Two properties the plan states as requirements and that the suite, until this
module, only ever verified **by hand**. Cycle 7 and Cycle 8 each checked them
the same way: move `lexml-proposed/` aside, run the suite, look at the numbers,
move it back. Both cycles recorded the result (A-7.4 cites "4635 pass / 79
skip"), and neither left anything behind that re-runs. A property checked by
hand once is not protected against regression — the next change that makes the
parser quietly depend on the unreleased schema, or that imports an HTTP client
at module level, breaks a stated requirement and nothing says so.

**1. The suite passes against `lexml/` alone (A-R.9).**

`lexml-proposed/` holds *generated* schemas carrying the LexML maintainers'
not-yet-released recursive `AgrupamentoHierarquico`. It can legitimately be
absent — it is produced by `scripts/build_proposed_schemas.py`, not checked in
as upstream truth — so the parser's correctness must not depend on it. Every
nested assertion is supposed to **skip with the capability probe's own
diagnostic** rather than fail (A-5b.3 puts the gate on *validation and emitter
selection*, never on the renderer; A-7.4 keeps the oracle's nested leg running
because reading nested markup needs no schema at all).

The skip *reason* is as load-bearing as the skip. A missing directory and a
present-but-unpatched schema are different situations with different remedies,
and a bare "skipped" makes a user read the source to tell them apart. So this
module asserts the diagnostic travels, not merely that the count is non-zero.

**2. No network dependency.**

Plan §9.3 pins `--referee=none` for the whole suite, and the cycle text asks for
"referee disabled ⇒ suite still green (no network dependency anywhere)". That is
three separate claims — the referee default, the linker default, and the import
graph — and they fail independently, so they are asserted independently.

How `lexml-proposed/` is hidden
-------------------------------
**Nothing in the real tree is moved, renamed or deleted.** That is not caution
for its own sake: a test that `git mv`s a vendored schema directory and then
crashes leaves the repository broken, which is the same reasoning N-2 applies to
the mutation harness.

The obvious seam would be an environment variable, and there is none:
`validate/schema.py` derives `_REPO_ROOT` from `Path(__file__).resolve()`, and
`generation_dir()` hangs `lexml-proposed` off that. So the honest way to give a
subprocess a different answer is to give it a different `__file__` — a mirror of
the repository in `tmp_path` holding real copies of `src/` and `tests/`, with
the bulk read-only inputs (`lexml/`, `samples/`, `scripts/`) symlinked, and
`lexml-proposed/` simply never created.

`src/` and `tests/` must be **copied rather than symlinked**, and that was
measured rather than assumed: `Path.resolve()` follows symlinks, so a symlinked
`src/` resolves straight back to the real checkout and `_REPO_ROOT` finds the
real `lexml-proposed/` again — the probe reported the capability *available*
under a mirror built that way, hiding nothing. The copy is ~2 MB of Python and
costs a fraction of a second; the symlinked inputs keep the 11 MB of goldens and
1 MB of samples out of the copy entirely.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directories copied into the mirror. These hold the code whose `__file__`
#: decides where `_REPO_ROOT` points, so they cannot be symlinked (see above).
_MIRROR_COPY = ("src", "tests")

#: Entries symlinked into the mirror: read-only inputs nothing resolves a
#: repository root from. `lexml-proposed` is deliberately absent from this list
#: — omitting it is the whole mechanism.
_MIRROR_LINK = ("lexml", "samples", "scripts", "pyproject.toml")

#: The subset the bare-checkout subprocess runs.
#:
#: Chosen for what it *proves*, not for breadth. It has to contain the nested
#: assertions that are supposed to skip, and at least one module that must keep
#: passing regardless, or a green result would be consistent with the suite
#: having quietly skipped everything:
#:
#: * `test_capabilities` / `test_refs_probe` — the probes themselves, the things
#:   every gate in the suite consults.
#: * `test_schema_matrix` — the §2.1 surface matrix, where the `proposed` rows
#:   skip and the `shipped` rows must still run and pass.
#: * `test_render_generico_aninhado` / `test_render_anexo` — the nested
#:   renderer, which A-5b.3 says renders *unconditionally*; only its validity
#:   assertions skip. If hiding the schemas ever stopped the renderer working,
#:   this is where it shows.
#: * `test_generico_aninhado_goldens` — the nested goldens (A-R.9 asks for all
#:   14); comparison is byte-identity against committed files, which needs no
#:   schema, so these must *pass*, while their validity leg skips.
#: * `test_cli_corpus` — the end-to-end leg, including A-8.5's ungated
#:   `test_nested_selection_is_answered_one_way_or_the_other`, the one assertion
#:   written to run in *both* configurations.
#:
#: Measured at ~7s for 509 passed / 131 skipped, against ~40s for the full
#: suite. Running everything in the subprocess would be affordable too, but it
#: would re-run ~5400 assertions that cannot observe the schema generation at
#: all, to learn nothing this subset does not already say.
_SUBSET = (
    "tests/unit/test_capabilities.py",
    "tests/unit/test_refs_probe.py",
    "tests/unit/test_schema_matrix.py",
    "tests/unit/test_render_generico_aninhado.py",
    "tests/unit/test_render_anexo.py",
    "tests/golden/test_generico_aninhado_goldens.py",
    "tests/regression/test_cli_corpus.py",
)

#: How long the subprocess run is given. Generous against the ~7s measured: a
#: timeout is a guard against a hang, not a performance assertion.
_TIMEOUT = 600


def _build_mirror(root: Path) -> Path:
    """A checkout with no `lexml-proposed/`, built without touching the real one.

    Returns the mirror's root. Asserts the absence rather than trusting it —
    if a future entry were added to `_MIRROR_LINK` by mistake, the mirror would
    silently stop being bare and every assertion here would pass vacuously.
    """
    mirror = root / "bare_checkout"
    mirror.mkdir()

    for name in _MIRROR_COPY:
        shutil.copytree(
            REPO_ROOT / name,
            mirror / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            symlinks=True,
        )
    for name in _MIRROR_LINK:
        source = REPO_ROOT / name
        if source.exists():
            (mirror / name).symlink_to(source)

    assert not (mirror / "lexml-proposed").exists(), (
        "the mirror is supposed to be a checkout without the generated "
        "schemas, and it has them — every assertion in this module would pass "
        "for the wrong reason"
    )
    assert (mirror / "lexml").is_dir(), (
        "the mirror has no shipped schemas either, which is not a bare "
        "checkout but a broken one"
    )
    return mirror


def _run_pytest(mirror: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Run pytest inside the mirror, with an environment the child can import in.

    `tests/conftest.py` puts the mirror's own `src/` on `sys.path`, so the child
    imports the copied package rather than the real one — but only if nothing in
    the inherited environment points elsewhere. `PYTHONPATH` is therefore
    cleared rather than passed through: inheriting a `PYTHONPATH=src` from the
    parent's shell would resolve against the real checkout and re-expose the
    schemas this mirror exists to hide.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    # Keep the child's own caches out of the mirror's copied tree.
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=str(mirror),
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )


@pytest.fixture(scope="module")
def bare_run(tmp_path_factory) -> subprocess.CompletedProcess:
    """One bare-checkout subprocess run, shared by the assertions below.

    Module-scoped because the run is the expensive part (~7s) and every test
    here asks a different question of the *same* result.
    """
    mirror = _build_mirror(tmp_path_factory.mktemp("bare"))
    return _run_pytest(mirror, ["-q", "-rs", *_SUBSET])


# ---------------------------------------------------------------------------
# 1. the bare checkout (A-R.9)
# ---------------------------------------------------------------------------


def test_the_mirror_actually_hides_the_proposed_schemas(tmp_path) -> None:
    """The mechanism, asserted before anything is concluded from it.

    Without this, a mirror that failed to hide the directory would make every
    other test in this module green while measuring nothing. The probe is asked
    inside the mirror, and must report the capability *unavailable* with the
    "does not exist" diagnostic — the same answer a genuine bare checkout gives.
    """
    mirror = _build_mirror(tmp_path)
    probe = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from lexml_nonstat.validate.schema import PROPOSED, probe_capabilities\n"
        "c = probe_capabilities(PROPOSED)\n"
        "print(c.available)\n"
        "print(c.nested_agrupamento)\n"
        "print(c.diagnostic)\n"
    ) % str(mirror / "src")

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    assert result.returncode == 0, f"the probe failed:\n{result.stderr}"

    available, nested, diagnostic = result.stdout.splitlines()[:3]
    assert available == "False", (
        "the mirror still sees a `proposed` generation, so it is not a bare "
        "checkout. `Path.resolve()` follows symlinks — if `src/` or `tests/` "
        "moved from _MIRROR_COPY to _MIRROR_LINK, the package resolves back to "
        "the real repository and finds the real `lexml-proposed/`."
    )
    assert nested == "False"
    assert "lexml-proposed" in diagnostic and "does not exist" in diagnostic, (
        "the bare checkout's diagnostic should name the missing directory and "
        f"say it is missing; it said: {diagnostic!r}"
    )

    # And the real directory is exactly where it was. The mirror is built from
    # copies and symlinks precisely so this can never be otherwise.
    assert (REPO_ROOT / "lexml-proposed").is_dir(), (
        "the real `lexml-proposed/` is gone. Nothing in this module may move, "
        "rename or delete it; see the module docstring."
    )


def test_suite_subset_passes_without_the_proposed_schemas(bare_run) -> None:
    """A-R.9's headline: `lexml/` alone is enough. Exit 0, zero failures.

    This is the assertion Cycle 7 and Cycle 8 each made by hand. Failing here
    means the parser has acquired a dependency on an unreleased schema.
    """
    assert bare_run.returncode == 0, (
        "the suite does not pass against `lexml/` alone (A-R.9).\n"
        f"--- stdout ---\n{bare_run.stdout}\n--- stderr ---\n{bare_run.stderr}"
    )
    summary = bare_run.stdout.strip().splitlines()[-1]
    assert "failed" not in summary and "error" not in summary, (
        f"the bare-checkout run reported failures: {summary}"
    )


def test_the_bare_run_still_exercises_the_parser(bare_run) -> None:
    """Green because it ran, not green because it skipped.

    A configuration in which *everything* gated itself away would satisfy the
    test above while proving nothing at all. The nested renderer and the nested
    goldens need no schema (A-5b.3, A-7.4), so a large majority of the subset
    must still execute.
    """
    summary = bare_run.stdout.strip().splitlines()[-1]
    passed = _count(summary, "passed")
    skipped = _count(summary, "skipped")

    assert passed > 0, f"nothing ran in the bare checkout: {summary}"
    assert passed > skipped, (
        "more of the bare-checkout subset skipped than ran, which is not the "
        "graceful degradation A-5b.3 describes — the renderer and the golden "
        f"comparisons should still execute without any schema.\n{summary}"
    )


def test_skips_carry_the_probe_diagnostic(bare_run) -> None:
    """Every skip says *why*, in the probe's own words.

    `tests/conftest.py` builds `requires_nested` with the capability's
    `diagnostic` as the reason for exactly this purpose. A bare "skipped" would
    leave a user unable to distinguish "you never generated the schemas" from
    "your schemas are the unpatched upstream ones" — different situations, with
    different remedies, and the diagnostic names which one holds.
    """
    reasons = [
        line for line in bare_run.stdout.splitlines() if line.startswith("SKIPPED")
    ]
    assert reasons, (
        "no skips at all in the bare checkout. The nested validity assertions "
        "are supposed to skip when `lexml-proposed/` is absent; if they now "
        "pass, something is validating against schemas that are not there."
    )

    for reason in reasons:
        # The three phrasings a bare run actually produces, each naming a cause
        # *and* a remedy — measured, not assumed:
        #
        #   "… does not exist (run scripts/build_proposed_schemas.py)"
        #       the probe's diagnostic for an absent generation
        #   "… rejects AgrupamentoHierarquico carrying an Agrupamento …"
        #       the probe's diagnostic for a present-but-unpatched generation
        #   "lexml-proposed/ is generated; run scripts/build_proposed_schemas.py"
        #       `test_capabilities.py`'s own marker, which gates tests *about*
        #       the probe and so cannot use the probe's output as its reason
        #
        # What is being excluded is a bare "skipped", or a reason that names no
        # remedy. A reader must be able to tell a missing directory from an
        # unpatched schema without opening the source.
        assert (
            "does not exist" in reason
            or "rejects" in reason
            or "is generated" in reason
        ), (
            "a skip reason does not say why it skipped. It should name either "
            "a missing directory or an unpatched schema, and the command that "
            f"fixes it, so the reader knows which situation they are in.\n"
            f"  {reason}"
        )
        assert "build_proposed_schemas.py" in reason or "rejects" in reason, (
            "a skip reason names no remedy. The generated schemas are produced "
            "by `scripts/build_proposed_schemas.py`, and a reason that omits "
            f"it leaves the reader stuck.\n  {reason}"
        )


def test_the_nested_assertions_are_the_ones_that_skip(bare_run) -> None:
    """The skips land where A-R.9 says they should.

    Pins the *shape* of the degradation, not just its volume: the modules that
    skip must be the nested ones. A future change that started skipping, say,
    the flat conservation tests on a bare checkout would still exit 0 and still
    carry diagnostics — and would be a serious regression.
    """
    skipped_modules = {
        line.split("tests/", 1)[1].split(":", 1)[0]
        for line in bare_run.stdout.splitlines()
        if line.startswith("SKIPPED") and "tests/" in line
    }
    assert skipped_modules, "expected skips naming their module"

    # The modules a bare run is allowed to skip within: every one either
    # targets the nested surface or tests the capability probe itself.
    # `render_anexo` is here because §2.9's annex bundle has a nested leg too
    # (one `requires_nested` case), not because annexes are a nested feature.
    nested_or_probe = (
        "aninhado",
        "schema_matrix",
        "capabilities",
        "cli_corpus",
        "render_anexo",
        "refs_probe",
    )
    for module in skipped_modules:
        assert any(token in module for token in nested_or_probe), (
            f"`{module}` skipped on a bare checkout. Only the nested and "
            "schema-capability assertions are supposed to degrade; a flat "
            "module skipping here means the parser's core now depends on the "
            "unreleased schemas."
        )


# ---------------------------------------------------------------------------
# 2. no network dependency (plan §9.3, §7.3 constraint 7, A-L.7)
# ---------------------------------------------------------------------------


def _default_for(command: str, flag: str) -> str:
    """The argparse default of `flag` on `command`'s subparser."""
    from lexml_nonstat import cli

    parser = cli.build_parser()
    # argparse keeps subparsers in the single _SubParsersAction's choices map.
    actions = [
        action
        for action in parser._actions  # noqa: SLF001 - argparse exposes no public API
        if hasattr(action, "choices") and isinstance(action.choices, dict)
    ]
    assert actions, "the CLI has no subcommands, which cannot be right"
    subparsers = actions[0].choices
    assert command in subparsers, f"no `{command}` subcommand"

    for action in subparsers[command]._actions:  # noqa: SLF001
        if flag in action.option_strings:
            return action.default
    raise AssertionError(f"`{command}` has no `{flag}`")


#: Entry points carrying `--referee`. `corpus` is Cycle 9's own (A-9.3); it is
#: looked up dynamically so this module does not fail while that command is
#: still being built alongside it.
def _commands_with(flag: str) -> tuple[str, ...]:
    from lexml_nonstat import cli

    parser = cli.build_parser()
    actions = [
        a for a in parser._actions if hasattr(a, "choices") and isinstance(a.choices, dict)  # noqa: SLF001
    ]
    found = []
    for name, sub in actions[0].choices.items():
        if any(flag in a.option_strings for a in sub._actions):  # noqa: SLF001
            found.append(name)
    return tuple(sorted(found))


def test_referee_defaults_to_none_at_every_entry_point() -> None:
    """§7.3 constraint 7: the adjudicator is opt-in, everywhere, always.

    A default of anything else would make an ordinary `parse` reach for a
    network service — which is why the plan pins it and why this asserts it at
    *every* entry point rather than at the one that happens to be tested.
    """
    commands = _commands_with("--referee")
    assert "parse" in commands and "decisions-report" in commands, (
        f"expected the referee on at least parse and decisions-report: {commands}"
    )
    for command in commands:
        assert _default_for(command, "--referee") == "none", (
            f"`{command} --referee` does not default to `none`, so the default "
            "configuration can reach the network (§7.3 constraint 7)."
        )


def test_linker_defaults_to_none_at_every_entry_point() -> None:
    """A-L.7, the same property for the external-reference resolver.

    `none` here means no subprocess rather than no socket, but the reasoning is
    identical: the default configuration must not reach outside the process.
    """
    commands = _commands_with("--linker")
    assert "parse" in commands, f"expected the linker on parse at least: {commands}"
    for command in commands:
        assert _default_for(command, "--linker") == "none", (
            f"`{command} --linker` does not default to `none`, so the default "
            "configuration spawns a linker subprocess (A-L.7)."
        )


def test_build_model_takes_no_referee_by_default() -> None:
    """The library entry point, beneath the CLI.

    The CLI's default is only half the claim: `build_model` is what
    `regen_goldens.py`, the corpus runner and every test call directly, and a
    referee defaulting to anything but `None` there would reach the network on
    paths no CLI flag governs.
    """
    import inspect

    from lexml_nonstat.model import build_model

    parameters = inspect.signature(build_model).parameters
    assert parameters["referee"].default is None, (
        "`build_model(referee=...)` no longer defaults to None; plan §9.3 pins "
        "the whole suite to no referee."
    )


def test_corpus_entry_points_default_to_none() -> None:
    """Cycle 9's own batch runner, held to the same rule (A-9.3).

    Skipped rather than failed while `corpus` is still landing: this module is
    built in parallel with it, and a test that fails because a sibling item has
    not merged yet reports the wrong thing.
    """
    import inspect

    corpus = pytest.importorskip(
        "lexml_nonstat.corpus", reason="the `corpus` module has not landed yet"
    )
    parameters = inspect.signature(corpus.run_corpus).parameters
    assert parameters["referee"].default is None, (
        "`run_corpus(referee=...)` must default to None — a 300-document batch "
        "is the last place a surprise network call belongs."
    )
    assert parameters["linker"].default is None, (
        "`run_corpus(linker=...)` must default to None (A-L.7)."
    )


def test_httpx_is_not_imported_by_the_package() -> None:
    """Extends Cycle 5b's `test_httpx_is_not_imported`, at package scope.

    That test asks whether *exercising the referee* pulls in `httpx`; this asks
    whether merely importing the package does. They fail independently — a
    module-level `import httpx` added to, say, `cli.py` would leave the referee
    test green.

    The technique is deliberately the same, and the reason is recorded in that
    test's docstring: the in-process form (`"httpx" not in sys.modules`) is a
    claim about the whole interpreter, which no single test owns — it failed on
    a third-party pytest plugin importing `httpx` at plugin-load time — and the
    obvious repair, snapshotting before and after, was *measured to be strictly
    weaker*: once anything else has imported `httpx`, a genuine module-level
    import of our own changes nothing about the snapshot. It survived the
    mutation. A clean `-I` subprocess with no plugins is the only place the
    question can honestly be asked, so this reuses it rather than reinventing a
    weaker form.
    """
    probe = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import lexml_nonstat\n"
        "import lexml_nonstat.cli\n"
        "import lexml_nonstat.model\n"
        "import lexml_nonstat.render\n"
        "import lexml_nonstat.routing\n"
        "import lexml_nonstat.validate\n"
        "print('httpx' in sys.modules)\n"
    ) % str(REPO_ROOT / "src")

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    assert result.returncode == 0, (
        f"the probe itself failed:\n{result.stdout}\n{result.stderr}"
    )
    assert result.stdout.strip() == "False", (
        "importing the package pulled in `httpx`. It must be imported only "
        "inside the referee's default transport, on a call that actually "
        "reaches the network, so the `referee` extra stays optional and the "
        "default configuration has no HTTP client at all."
    )


def test_no_network_in_the_default_configuration(tmp_path) -> None:
    """The end-to-end claim: a real run, with the socket layer removed.

    The defaults asserted above are each necessary and none is sufficient — a
    network call could still be made by something that consults no flag. So this
    patches `socket.socket` to raise and runs the pipeline the CLI actually
    runs, over a real sample, through to rendered XML.

    `socket.socket` rather than a higher-level seam because it is the narrowest
    thing every network path in Python must pass through, whichever client
    library reaches for it.
    """
    from lexml_nonstat import cli

    sample = REPO_ROOT / "samples" / "par_cosit_26_20000629.docx"
    assert sample.exists(), f"the sample this test runs on is missing: {sample}"

    class _NoNetwork(socket.socket):
        def __init__(self, *args, **kwargs):  # noqa: D107
            raise AssertionError(
                "the default configuration opened a socket. The referee and "
                "the linker both default to `none`; nothing in a plain parse "
                "may reach the network (plan §9.3)."
            )

    out = tmp_path / "out"
    original = socket.socket
    socket.socket = _NoNetwork
    try:
        code = cli.main(["parse", "--quiet", "-o", str(out), str(sample)])
    finally:
        socket.socket = original

    assert code == 0, "the parse failed with the socket layer disabled"
    assert list(out.glob("*.xml")), "the run produced no XML"


def _count(summary: str, word: str) -> int:
    """`N` from a pytest summary line's `N <word>`, or 0 if absent."""
    tokens = summary.replace(",", " ").split()
    for index, token in enumerate(tokens):
        if token.startswith(word) and index:
            try:
                return int(tokens[index - 1])
            except ValueError:
                return 0
    return 0
