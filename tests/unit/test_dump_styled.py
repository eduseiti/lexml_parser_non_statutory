"""The ``--dump-styled`` debug view.

Guards the plan's Cycle 1 deliverable that a developer can see *what ingestion
actually saw* without writing a script. The invariant is that the JSON form is
round-trippable — a dump that cannot be read back is a dump you cannot trust to
diagnose a golden diff.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc

SAMPLE = "sumula_carf_42.docx"  # smallest sample: 4 blocks, fast to dump


def run_dump(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the entry point as a subprocess.

    Deliberately not calling ``main()`` in-process: the exit code and the
    stdout/stderr split are part of the contract, and a subprocess is the only
    way to test them as a user experiences them.
    """
    env = {"PYTHONPATH": str(repo_root / "src"), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "lexml_nonstat.ingest", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )


def test_dump_json_is_valid_json(repo_root: Path) -> None:
    result = run_dump(repo_root, str(repo_root / "samples" / SAMPLE))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["source"] == SAMPLE
    assert payload["blocks"]


def test_dump_json_round_trips(repo_root: Path) -> None:
    """The dumped JSON reconstructs the StyledDoc it came from."""
    result = run_dump(repo_root, str(repo_root / "samples" / SAMPLE))
    doc = StyledDoc.from_json(result.stdout)
    assert doc.source == SAMPLE
    assert doc.paragraphs
    assert "Súmula CARF nº 42" in doc.text


def test_dump_defaults_to_json(repo_root: Path) -> None:
    """No --format flag means the golden form, not the human summary."""
    result = run_dump(repo_root, str(repo_root / "samples" / SAMPLE))
    json.loads(result.stdout)  # raises if the default were text


def test_dump_text_format(repo_root: Path) -> None:
    result = run_dump(repo_root, "--format=text", str(repo_root / "samples" / SAMPLE))
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0].startswith(f"# {SAMPLE}")
    assert any("Súmula CARF nº 42" in line for line in lines)
    # One header line plus one line per block.
    assert len(lines) == 1 + 4


def test_dump_text_shows_indent_signals(repo_root: Path) -> None:
    """The text view exists to make the indentation evidence visible."""
    result = run_dump(
        repo_root, "--format=text", str(repo_root / "samples" / "parecer_93_2018_decor_cgu_agu.docx")
    )
    assert result.returncode == 0, result.stderr
    assert "ind=2908/2908" in result.stdout


def test_dump_table_blocks_are_labelled(repo_root: Path) -> None:
    result = run_dump(
        repo_root, "--format=text", str(repo_root / "samples" / "REsp_1306393.docx")
    )
    assert "TABLE 5x2" in result.stdout


def test_dump_missing_file_exits_1(repo_root: Path) -> None:
    result = run_dump(repo_root, str(repo_root / "samples" / "does_not_exist.docx"))
    assert result.returncode == 1
    assert "no such file" in result.stderr
    assert result.stdout == ""


def test_dump_non_docx_exits_1(repo_root: Path, tmp_path: Path) -> None:
    bogus = tmp_path / "not_a_docx.docx"
    bogus.write_text("this is not a zip archive", encoding="utf-8")
    result = run_dump(repo_root, str(bogus))
    assert result.returncode == 1
    assert "cannot read" in result.stderr


def test_dump_multiple_files(repo_root: Path) -> None:
    """Every named file is emitted, so a batch dump is reviewable in one pass."""
    result = run_dump(
        repo_root,
        "--format=text",
        str(repo_root / "samples" / SAMPLE),
        str(repo_root / "samples" / "ad_srf_22_19970430.docx"),
    )
    assert result.returncode == 0, result.stderr
    assert f"# {SAMPLE}" in result.stdout
    assert "# ad_srf_22_19970430.docx" in result.stdout


def test_dump_continues_past_a_bad_file(repo_root: Path) -> None:
    """One unreadable file must not suppress the others — but the exit code
    must still report failure, so a script cannot mistake it for success."""
    result = run_dump(
        repo_root,
        "--format=text",
        str(repo_root / "samples" / "does_not_exist.docx"),
        str(repo_root / "samples" / SAMPLE),
    )
    assert result.returncode == 1
    assert f"# {SAMPLE}" in result.stdout
    assert "no such file" in result.stderr


def test_keep_strikethrough_flag(repo_root: Path) -> None:
    """The struck ordinal in sumula_stj_125 reappears when asked for."""
    sample = str(repo_root / "samples" / "sumula_stj_125.docx")
    default = run_dump(repo_root, sample)
    kept = run_dump(repo_root, "--keep-strikethrough", sample)
    assert default.returncode == kept.returncode == 0
    assert "(2ª T, 03.08.1994" not in default.stdout
    assert "(2ª T, 03.08.1994" in kept.stdout


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_exits_0(repo_root: Path, flag: str) -> None:
    result = run_dump(repo_root, flag)
    assert result.returncode == 0
    assert "dump" in result.stdout.lower() or "styleddoc" in result.stdout.lower()
