"""The `--linker` CLI flag — Cycle 8e, spec §4.5 (amendment A-L.7).

Mirrors `test_cli.py`'s referee-configuration tests in style: `run()` drives
`cli.main` in-process and asserts on content, never merely on an exit code.

**A-C.1's lesson, discharged here.** A previous cycle shipped `--referee`
accepted, built, and then discarded — inert on the whole CLI. T-X1 is the
headline test: it proves `--linker` moves bytes, not merely that argparse
accepts it.
"""

from __future__ import annotations

import io
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from lexml_nonstat import cli
from lexml_nonstat.refs import LinkerCapabilities

from tests.conftest import LINKER_FIXTURES, REPO_ROOT

PARECER_93 = REPO_ROOT / "samples" / "parecer_93_2018_decor_cgu_agu.docx"
SAMPLE = REPO_ROOT / "samples" / "pn_cst_38_19801031.docx"


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# T-X1 — the headline: --linker demonstrably changes output
# ---------------------------------------------------------------------------


def test_linker_none_and_fixtures_produce_different_output() -> None:
    """A-C.1's lesson, discharged: the flag must actually reach the emitter."""
    code_none, out_none, err_none = run(
        ["parse", "--linker=none", str(PARECER_93)]
    )
    code_fixtures, out_fixtures, err_fixtures = run(
        [
            "parse", "--linker=fixtures",
            f"--linker-cache={LINKER_FIXTURES}", str(PARECER_93),
        ]
    )
    assert code_none == 0, err_none
    assert code_fixtures == 0, err_fixtures
    assert out_none != out_fixtures
    assert "<Remissao" not in out_none
    assert "<Remissao" in out_fixtures


# ---------------------------------------------------------------------------
# T-X2 — default is none
# ---------------------------------------------------------------------------


def test_default_linker_is_none() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["parse", str(SAMPLE)])
    assert args.linker == "none"


def test_default_parse_emits_no_remissao() -> None:
    code, out, err = run(["parse", str(PARECER_93)])
    assert code == 0, err
    assert "<Remissao" not in out


# ---------------------------------------------------------------------------
# T-X3 — an unknown --linker value is a misuse
# ---------------------------------------------------------------------------


def test_unknown_linker_value_is_a_misuse() -> None:
    code, _, err = run(["parse", "--linker=nonsense", str(SAMPLE)])
    assert code == 2
    assert "linker" in err
    assert "nonsense" in err


def test_fixtures_without_a_cache_is_a_misuse() -> None:
    code, _, err = run(["parse", "--linker=fixtures", str(SAMPLE)])
    assert code == 2
    assert "linker-cache" in err


# ---------------------------------------------------------------------------
# T-X4 — capabilities reports the linker
# ---------------------------------------------------------------------------


def test_capabilities_reports_the_linker_text() -> None:
    code, out, err = run(["capabilities"])
    assert code == 0, err
    assert "linker" in out.lower()


def test_capabilities_json_keeps_the_existing_schema_list_shape() -> None:
    """The JSON payload is pinned elsewhere (`test_cli.py`) as a bare list of
    schema-generation records; the linker is reported in the text format only
    (see `test_capabilities_reports_the_linker_text` above), so this just
    confirms `--format=json` still works and is unaffected by `--linker`."""
    import json

    code, out, err = run(["capabilities", "--format=json"])
    assert code == 0, err
    assert isinstance(json.loads(out), list)


def test_capabilities_never_crashes_without_the_binary(monkeypatch) -> None:
    """T-X4: works whether or not the binary is present."""

    def fake_probe(binary=None):
        return LinkerCapabilities(
            available=False, path="", version="",
            diagnostic="linkertool: not found (faked for this test)",
        )

    monkeypatch.setattr(cli, "probe_linker", fake_probe)
    code, out, err = run(["capabilities"])
    assert code == 0, err
    assert "linker" in out.lower()
    assert "not found" in out


# ---------------------------------------------------------------------------
# T-X5 — auto never errors even with no binary
# ---------------------------------------------------------------------------


def test_linker_auto_degrades_gracefully_with_no_binary(monkeypatch) -> None:
    from lexml_nonstat import refs as refs_pkg

    def fake_probe(binary=None):
        return LinkerCapabilities(
            available=False, path="", version="",
            diagnostic="linkertool: not found (faked for this test)",
        )

    monkeypatch.setattr(refs_pkg, "probe_linker", fake_probe)
    code, out, err = run(["parse", "--linker=auto", str(SAMPLE)])
    assert code == 0, err
    assert out  # still produced output
    assert "<Remissao" not in out


# ---------------------------------------------------------------------------
# fixtures mode spawns no subprocess
# ---------------------------------------------------------------------------


def test_fixtures_mode_spawns_no_subprocess(monkeypatch) -> None:
    """Mirrors `test_referee_api.py`'s zero-network-call assertion.

    ``LinkertoolLinker`` spawns its co-process via `subprocess.Popen` inside
    `refs/linkertool.py`; patching it to raise proves a fully cache-backed
    fixtures run never reaches that call.
    """

    def boom(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("fixtures mode must not spawn a subprocess")

    monkeypatch.setattr(
        "lexml_nonstat.refs.linkertool.subprocess.Popen", boom
    )
    code, out, err = run(
        [
            "parse", "--linker=fixtures",
            f"--linker-cache={LINKER_FIXTURES}", str(PARECER_93),
        ]
    )
    assert code == 0, err
    assert "<Remissao" in out
