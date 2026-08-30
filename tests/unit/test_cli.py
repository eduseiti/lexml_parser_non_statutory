"""The unified CLI — Cycle 8, spec §3.5 and §5.1.

Every test drives :func:`lexml_nonstat.cli.main` in-process and asserts on
*content*, never merely on an exit code. A CLI is unusually easy to test
shallowly — `assert code == 0` passes for a command that silently emits
nothing — so the assertions here are pinned to the library's own answers: the
CSV header is `CSV_COLUMNS`, the block count is what `read_docx` reports, and
`tests/regression/test_cli_corpus.py` goes further and pins the XML byte for
byte against `render_generico`.

One test uses a subprocess, to prove `python3 -m lexml_nonstat` reaches the same
entry point. The rest do not: a subprocess per case would multiply a 20-second
suite by the interpreter start-up cost for no additional claim.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat import cli
from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.profile import all_profiles
from lexml_nonstat.render import render_generico
from lexml_nonstat.segments import CSV_COLUMNS, segments_from_model
from lexml_nonstat.validate.schema import GENERATIONS, SCHEMA_SELECTORS

from tests.conftest import requires_nested

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "samples" / "pn_cst_38_19801031.docx"
ANNEX_SAMPLE = REPO_ROOT / "samples" / "port_mf_277_20180607.docx"


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def sample_model():
    return build_model(read_docx(SAMPLE), filename=SAMPLE.name)


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def test_every_declared_command_is_in_the_help() -> None:
    parser = cli.build_parser()
    help_text = parser.format_help()
    for command in cli.COMMANDS:
        assert command in help_text


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


def test_no_command_is_a_misuse() -> None:
    code, _, err = run([])
    assert code == 2
    assert "command is required" in err
    for command in cli.COMMANDS:
        assert command in err


def test_unknown_command_is_a_misuse() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["nonsense"])
    assert exc.value.code == 2


def test_version_reports_the_package_version() -> None:
    from lexml_nonstat import __version__

    with pytest.raises(SystemExit):
        run(["--version"])
    assert __version__ in cli._version_string()


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


def test_parse_writes_one_well_formed_document_to_stdout() -> None:
    code, out, err = run(["parse", str(SAMPLE)])
    assert code == 0, err
    root = etree.fromstring(out.encode("utf-8"))
    assert etree.QName(root).localname == "LexML"


def test_parse_output_is_exactly_what_the_library_renders(sample_model) -> None:
    """The CLI must add no rendering of its own — see the module docstring."""
    _, out, _ = run(["parse", "--emitter=generico", str(SAMPLE)])
    assert out == render_generico(sample_model).to_xml_string()


def test_parse_is_deterministic() -> None:
    """Invariant #4: same input, same referee ⇒ byte-identical output."""
    _, first, _ = run(["parse", str(SAMPLE)])
    _, second, _ = run(["parse", str(SAMPLE)])
    assert first == second


def test_parse_json_carries_the_run_report() -> None:
    code, out, _ = run(["parse", "--format=json", str(SAMPLE)])
    assert code == 0
    report = json.loads(out)
    for key in (
        "source", "urn", "profile", "route", "emitter", "confidence",
        "hierarchy_confidence", "flat", "referee", "blockers", "warnings",
        "documents", "written", "xml",
    ):
        assert key in report
    assert report["source"] == SAMPLE.name
    assert report["urn"].startswith("urn:lex:br:")


def test_parse_out_writes_the_whole_bundle(tmp_path) -> None:
    """§2.9's naming: the primary, then `!anexoN` beside it."""
    code, out, _ = run(["parse", "-o", str(tmp_path), str(ANNEX_SAMPLE)])
    assert code == 0
    written = sorted(p.name for p in tmp_path.glob("*.xml"))
    assert len(written) == 2
    assert any("!anexo1" in name for name in written)
    assert all(str(tmp_path) in line for line in out.splitlines() if "wrote" in line)
    for path in tmp_path.glob("*.xml"):
        assert etree.parse(str(path)) is not None


def test_parse_without_out_warns_about_unwritten_annexes() -> None:
    code, _, err = run(["parse", str(ANNEX_SAMPLE)])
    assert code == 0
    assert "annexes_not_written" in err


def test_parse_with_out_does_not_warn_about_annexes(tmp_path) -> None:
    _, _, err = run(["parse", "-o", str(tmp_path), str(ANNEX_SAMPLE)])
    assert "annexes_not_written" not in err


@pytest.mark.parametrize("emitter", cli.CHOOSABLE_EMITTERS)
def test_every_emitter_name_is_accepted_by_the_parser(emitter: str) -> None:
    """A-R.9: `--emitter` *accepts* `generico-aninhado` among the rest.

    Accepting the name is argument parsing and is unconditional. Whether the
    rendering can then be *selected* depends on the probe — plan §5.2 — which
    is what the two tests below cover in their respective configurations.
    """
    args = cli.build_parser().parse_args(["parse", f"--emitter={emitter}", str(SAMPLE)])
    assert args.emitter == emitter


@pytest.mark.parametrize("emitter", ("auto", "generico", "norma"))
def test_every_unconditional_emitter_renders(emitter: str) -> None:
    code, out, err = run(["parse", f"--emitter={emitter}", str(SAMPLE)])
    assert code == 0, err
    assert etree.fromstring(out.encode("utf-8")) is not None


@requires_nested
def test_the_nested_emitter_renders_where_it_can_be_selected() -> None:
    code, out, err = run(["parse", "--emitter=generico-aninhado", str(SAMPLE)])
    assert code == 0, err
    assert etree.fromstring(out.encode("utf-8")) is not None


def test_unknown_emitter_is_a_misuse() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["parse", "--emitter=nonsense", str(SAMPLE)])
    assert exc.value.code == 2


@requires_nested
def test_nested_emitter_produces_nested_markup() -> None:
    _, out, _ = run(["parse", "--emitter=generico-aninhado", str(SAMPLE)])
    assert "AgrupamentoHierarquico" in out


def test_flat_emitter_produces_no_nested_markup() -> None:
    _, out, _ = run(["parse", "--emitter=generico", str(SAMPLE)])
    assert "AgrupamentoHierarquico" not in out


def test_auto_routes_the_annex_sample_statutorily() -> None:
    """Cycle 6's `render_statutory` is reachable from the CLI by default."""
    _, out, _ = run(["parse", "--format=json", str(ANNEX_SAMPLE)])
    report = json.loads(out)
    assert report["route"] == "norma"
    assert report["emitter"] == "norma"


def test_forcing_generico_on_a_norma_route_is_honoured() -> None:
    _, out, _ = run(["parse", "--format=json", "--emitter=generico", str(ANNEX_SAMPLE)])
    report = json.loads(out)
    assert report["route"] == "norma"
    assert report["emitter"] == "generico"


def test_unknown_profile_is_a_misuse_and_names_the_known_ones() -> None:
    code, _, err = run(["parse", "--profile=nonsense", str(SAMPLE)])
    assert code == 2
    assert "nonsense" in err
    assert "generic" in err


def test_forcing_a_profile_changes_the_reported_profile() -> None:
    _, out, _ = run(["parse", "--format=json", "--profile=generic", str(SAMPLE)])
    assert json.loads(out)["profile"] == "generic"


# ---------------------------------------------------------------------------
# warnings, --strict and confidence
# ---------------------------------------------------------------------------


def test_warnings_go_to_stderr_and_never_pollute_stdout() -> None:
    """`parse | validate -` must not be broken by a diagnostic."""
    _, out, err = run(["parse", str(ANNEX_SAMPLE)])
    assert "warning:" in err
    assert "warning:" not in out
    assert etree.fromstring(out.encode("utf-8")) is not None


def test_strict_changes_only_the_exit_code() -> None:
    """Spec §7's pinned risk: `--strict` must not swallow or alter output."""
    lenient_code, lenient_out, _ = run(["parse", str(ANNEX_SAMPLE)])
    strict_code, strict_out, _ = run(["parse", "--strict", str(ANNEX_SAMPLE)])
    assert lenient_out == strict_out
    assert lenient_code == 0
    assert strict_code == 1


def test_strict_is_silent_when_nothing_warns() -> None:
    code, _, err = run(["parse", "--strict", str(SAMPLE)])
    assert "warning:" not in err
    assert code == 0


def test_confidence_and_referee_status_in_json() -> None:
    _, out, _ = run(["parse", "--format=json", str(SAMPLE)])
    report = json.loads(out)
    assert 0.0 <= report["confidence"] <= 1.0
    assert 0.0 <= report["hierarchy_confidence"] <= 1.0
    assert report["referee"] == {"consulted": False, "overrode": False}


def test_confidence_and_referee_status_in_text(tmp_path) -> None:
    _, out, _ = run(["parse", "--summary", str(SAMPLE)])
    assert "confidence" in out
    assert "referee" in out
    assert "route" in out


def test_the_referee_defaults_to_none() -> None:
    """§7.3 constraint 7 — nothing here may make a network call unasked."""
    parser = cli.build_parser()
    args = parser.parse_args(["parse", str(SAMPLE)])
    assert args.referee == "none"


def test_referee_local_without_a_model_is_a_misuse() -> None:
    code, _, err = run(["parse", "--referee=local", str(SAMPLE)])
    assert code == 2
    assert "referee-model" in err


# ---------------------------------------------------------------------------
# dump-styled / dump-tree
# ---------------------------------------------------------------------------


def test_dump_styled_json_reports_the_blocks_ingestion_saw() -> None:
    code, out, _ = run(["dump-styled", str(SAMPLE)])
    assert code == 0
    assert len(json.loads(out)["blocks"]) == len(read_docx(SAMPLE).blocks)


def test_dump_styled_text_is_readable() -> None:
    code, out, _ = run(["dump-styled", "--format=text", str(SAMPLE)])
    assert code == 0
    assert SAMPLE.name in out
    assert out.count("\n") >= len(read_docx(SAMPLE).blocks)


def test_dump_tree_text_reports_the_section_count(sample_model) -> None:
    code, out, _ = run(["dump-tree", str(SAMPLE)])
    assert code == 0
    expected = len(list(sample_model.body.walk()))
    assert f"sections={expected}" in out


def test_dump_tree_json_parses() -> None:
    code, out, _ = run(["dump-tree", "--format=json", str(SAMPLE)])
    assert code == 0
    assert "body" in json.loads(out)


def test_dump_tree_why_shows_more() -> None:
    _, plain, _ = run(["dump-tree", str(SAMPLE)])
    _, verbose, _ = run(["dump-tree", "--why", str(SAMPLE)])
    assert len(verbose) > len(plain)


# ---------------------------------------------------------------------------
# segment
# ---------------------------------------------------------------------------


def test_segment_csv_header_is_the_declared_columns() -> None:
    code, out, _ = run(["segment", str(SAMPLE)])
    assert code == 0
    assert out.splitlines()[0] == ",".join(CSV_COLUMNS)


def test_segment_csv_matches_the_library(sample_model) -> None:
    from lexml_nonstat.segments import to_csv

    _, out, _ = run(["segment", str(SAMPLE)])
    assert out == to_csv(segments_from_model(sample_model))


def test_segment_jsonl_is_one_object_per_line(sample_model) -> None:
    code, out, _ = run(["segment", "--format=jsonl", str(SAMPLE)])
    assert code == 0
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == len(segments_from_model(sample_model))
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_segment_reads_an_xml_file_back(tmp_path) -> None:
    """A file from disk has no `emitter`; the reader dispatches on markup (A-7.3)."""
    _, xml, _ = run(["parse", "--emitter=generico", str(SAMPLE)])
    path = tmp_path / "d.xml"
    path.write_text(xml, encoding="utf-8")
    code, out, _ = run(["segment", str(path)])
    assert code == 0
    assert out.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(out.splitlines()) > 1


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_accepts_a_document_the_parser_produced(tmp_path) -> None:
    _, xml, _ = run(["parse", str(SAMPLE)])
    path = tmp_path / "d.xml"
    path.write_text(xml, encoding="utf-8")
    code, out, _ = run(["validate", str(path)])
    assert code == 0
    assert "OK" in out


def test_validate_rejects_a_broken_document(tmp_path) -> None:
    path = tmp_path / "bad.xml"
    path.write_text(
        '<LexML xmlns="http://www.lexml.gov.br/1.0"><NaoExiste/></LexML>',
        encoding="utf-8",
    )
    code, _, err = run(["validate", str(path)])
    assert code == 1
    assert "INVALID" in err


def test_validate_reports_a_missing_file(tmp_path) -> None:
    code, _, err = run(["validate", str(tmp_path / "nope.xml")])
    assert code == 1
    assert "no such file" in err


@pytest.mark.parametrize("selector", SCHEMA_SELECTORS)
def test_validate_accepts_every_schema_selector(tmp_path, selector: str) -> None:
    _, xml, _ = run(["parse", str(SAMPLE)])
    path = tmp_path / "d.xml"
    path.write_text(xml, encoding="utf-8")
    code, _, _ = run(["validate", f"--schema={selector}", str(path)])
    assert code == 0


def test_validate_quiet_prints_nothing_when_valid(tmp_path) -> None:
    _, xml, _ = run(["parse", str(SAMPLE)])
    path = tmp_path / "d.xml"
    path.write_text(xml, encoding="utf-8")
    code, out, _ = run(["validate", "-q", str(path)])
    assert code == 0
    assert out == ""


# ---------------------------------------------------------------------------
# list-profiles
# ---------------------------------------------------------------------------


def test_list_profiles_needs_no_document() -> None:
    code, out, _ = run(["list-profiles"])
    assert code == 0
    assert out.strip()


def test_list_profiles_lists_every_registered_profile() -> None:
    _, out, _ = run(["list-profiles"])
    for profile in all_profiles():
        assert profile.name in out


def test_list_profiles_json_is_a_list_of_records() -> None:
    _, out, _ = run(["list-profiles", "--format=json"])
    records = json.loads(out)
    assert len(records) == len(all_profiles())
    for record in records:
        assert {"name", "urn_type", "base_score"} <= set(record)


def test_the_generic_catch_all_profile_is_registered() -> None:
    """Cycle 8's `generic` bullet, discharged by assertion (spec §2 R-1).

    It landed in Cycle 2. What this cycle owes is the guarantee it exists and
    claims everything weakly, so no document is ever left unprofiled.
    """
    records = {r["name"]: r for r in json.loads(run(["list-profiles", "--format=json"])[1])}
    assert "generic" in records
    assert records["generic"]["base_score"] > 0
    assert all(
        r["base_score"] <= records["generic"]["base_score"] or name == "generic"
        for name, r in records.items()
    )


# ---------------------------------------------------------------------------
# decisions-report
# ---------------------------------------------------------------------------


def test_decisions_report_runs_over_the_corpus() -> None:
    code, out, _ = run(["decisions-report", str(SAMPLE), str(ANNEX_SAMPLE)])
    assert code == 0
    assert "Decisions:" in out


def test_decisions_report_consults_no_referee_by_default() -> None:
    """§9.3: the suite pins `--referee=none`, so nothing is ever consulted."""
    _, out, _ = run(["decisions-report", str(SAMPLE)])
    assert "put to a referee:    0" in out


# ---------------------------------------------------------------------------
# capabilities — A-R.9
# ---------------------------------------------------------------------------


def test_capabilities_reports_every_generation() -> None:
    code, out, _ = run(["capabilities"])
    assert code == 0
    for generation in GENERATIONS:
        assert generation in out


def test_capabilities_json_round_trips_the_probe() -> None:
    from lexml_nonstat.validate.schema import probe_capabilities

    _, out, _ = run(["capabilities", "--format=json"])
    records = json.loads(out)
    assert len(records) == len(GENERATIONS)
    for record in records:
        assert record == probe_capabilities(record["generation"]).to_dict()


def test_capabilities_carries_a_diagnostic_for_each_generation() -> None:
    _, out, _ = run(["capabilities", "--format=json"])
    for record in json.loads(out):
        assert record["diagnostic"].strip()


def test_capabilities_exits_zero_whatever_the_checkout_holds() -> None:
    """A missing generation is a fact about the checkout, not a failure."""
    assert run(["capabilities"])[0] == 0
    assert run(["capabilities", "--format=json"])[0] == 0


def test_capabilities_names_the_nested_emitter_availability() -> None:
    _, out, _ = run(["capabilities"])
    assert "generico-aninhado" in out


def test_requesting_an_unavailable_emitter_exits_cleanly(monkeypatch) -> None:
    """A-R.9 verbatim: non-zero status, the probe's diagnostic, no traceback."""
    from lexml_nonstat.validate.schema import SchemaCapabilities

    monkeypatch.setattr(
        cli,
        "probe_capabilities",
        lambda generation: SchemaCapabilities(
            generation, False, False, "schema generation 'proposed' unavailable: no such directory"
        ),
    )
    code, out, err = run(["parse", "--emitter=generico-aninhado", str(SAMPLE)])
    assert code == 2
    assert out == ""
    assert "no such directory" in err
    assert "Traceback" not in err


def test_an_available_emitter_is_not_refused() -> None:
    """The gate must not fire on the emitters that need no patched schema."""
    for emitter in ("auto", "generico", "norma"):
        code, _, err = run(["parse", f"--emitter={emitter}", str(SAMPLE)])
        assert code == 0, err


# ---------------------------------------------------------------------------
# multi-file runs
# ---------------------------------------------------------------------------


def test_multiple_documents_in_one_invocation() -> None:
    code, out, _ = run(["parse", "--format=json", str(SAMPLE), str(ANNEX_SAMPLE)])
    assert code == 0
    assert out.count('"urn"') == 2


def test_multi_file_text_output_carries_per_document_headers() -> None:
    code, out, _ = run(["dump-tree", str(SAMPLE), str(ANNEX_SAMPLE)])
    assert code == 0
    assert f"=== {SAMPLE.name} ===" in out
    assert f"=== {ANNEX_SAMPLE.name} ===" in out


def test_quiet_suppresses_the_headers() -> None:
    _, out, _ = run(["dump-tree", "-q", str(SAMPLE), str(ANNEX_SAMPLE)])
    assert "===" not in out


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------


def test_module_form_reaches_the_same_entry_point() -> None:
    """`python3 -m lexml_nonstat` — the form the docs and the suite use."""
    result = subprocess.run(
        [sys.executable, "-m", "lexml_nonstat", "capabilities"],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "generation" in result.stdout
    assert "Traceback" not in result.stderr


def test_the_console_script_points_at_cli_main() -> None:
    """`[project.scripts]` must name a real, callable entry point."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'lexml-nonstat = "lexml_nonstat.cli:main"' in text
    assert callable(cli.main)
