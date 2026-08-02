"""`--schema=both|rigido|flexivel`: selector plumbing and the entry point.

Cycle 8 owns the full CLI; this covers the selector Cycle 0 delivers, end to
end, so the flag is exercised rather than merely present.
"""

from __future__ import annotations

import pytest

from lexml_nonstat.validate import (
    SCHEMA_NAMES,
    SCHEMA_SELECTORS,
    UnknownSchemaError,
    load_schemas,
    resolve_selector,
)
from lexml_nonstat.validate.__main__ import main


def test_selector_both_loads_two_in_order():
    assert resolve_selector("both") == SCHEMA_NAMES
    assert tuple(load_schemas("both")) == SCHEMA_NAMES


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_selector_single_loads_one(name):
    assert resolve_selector(name) == (name,)
    assert tuple(load_schemas(name)) == (name,)


def test_default_selector_is_both():
    """Plan invariant #1: validate against both schemas unless told otherwise."""
    assert resolve_selector() == SCHEMA_NAMES


@pytest.mark.parametrize("bad", ["", "BOTH", "rigid", "all", "none"])
def test_invalid_selector_raises_clean_error(bad):
    with pytest.raises(UnknownSchemaError) as exc:
        resolve_selector(bad)

    message = str(exc.value)
    for valid in SCHEMA_SELECTORS:
        assert valid in message, "the error should list the accepted values"


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_main_exit_code_zero_on_valid(tmp_path, capsys, minimal_generico):
    path = _write(tmp_path, "valid.xml", minimal_generico)

    assert main([path, "--schema=both"]) == 0
    assert "OK" in capsys.readouterr().out


def test_main_exit_code_one_on_invalid(tmp_path, capsys, nested_agrupamento):
    path = _write(tmp_path, "invalid.xml", nested_agrupamento)

    assert main([path, "--schema=both"]) == 1

    err = capsys.readouterr().err
    assert "INVALID" in err
    assert "Agrupamento" in err, "the diagnostic should name the offending element"


@pytest.mark.parametrize("selector", SCHEMA_SELECTORS)
def test_main_accepts_every_selector(tmp_path, selector, minimal_generico):
    path = _write(tmp_path, "valid.xml", minimal_generico)
    assert main([path, f"--schema={selector}"]) == 0


def test_main_validates_several_files(tmp_path, minimal_generico, nested_agrupamento):
    """One bad file fails the run, and the good file is still reported."""
    good = _write(tmp_path, "good.xml", minimal_generico)
    bad = _write(tmp_path, "bad.xml", nested_agrupamento)

    assert main([good]) == 0
    assert main([good, bad]) == 1


def test_main_missing_file_is_a_clean_error(tmp_path, capsys):
    assert main([str(tmp_path / "absent.xml")]) == 1

    err = capsys.readouterr().err
    assert "no such file" in err
    assert "Traceback" not in err


def test_main_quiet_suppresses_success_output(tmp_path, capsys, minimal_generico):
    path = _write(tmp_path, "valid.xml", minimal_generico)

    assert main([path, "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_main_rejects_unknown_selector(tmp_path, minimal_generico):
    """argparse rejects it before validation runs — exit 2, no traceback."""
    path = _write(tmp_path, "valid.xml", minimal_generico)

    with pytest.raises(SystemExit) as exc:
        main([path, "--schema=bogus"])
    assert exc.value.code == 2
