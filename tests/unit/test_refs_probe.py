"""The linker probe — measured, never assumed (A-L.5).

The probe is the whole of the mechanism that makes the linker optional. These
tests deliberately spend most of their effort on the **absent** case, because
that is the configuration the plan promises works: A-R.9 requires the suite to
stay green against `lexml/` alone, and Cycle 9 requires no network dependency
anywhere.
"""

from __future__ import annotations

import os
import stat

import pytest

from lexml_nonstat.refs import (
    DEFAULT_LINKER_PATH,
    LinkerCapabilities,
    linker_env,
    probe_linker,
    resolve_binary,
)

from tests.conftest import linker_capabilities, requires_linker


def test_a_missing_binary_answers_unavailable_without_raising():
    """T-R1 — the bare-checkout case, and it must never be an exception."""
    capabilities = probe_linker("/nonexistent/definitely/not/here/linkertool")

    assert capabilities.available is False
    assert capabilities.path == ""
    assert capabilities.version == ""
    assert "/nonexistent/definitely/not/here/linkertool" in capabilities.diagnostic


def test_the_diagnostic_says_why_and_says_it_is_optional():
    """A skip reason a user reads must not look like a broken checkout."""
    diagnostic = probe_linker("/nonexistent/x").diagnostic

    assert "unavailable" in diagnostic
    assert "optional" in diagnostic


def test_a_present_but_unexecutable_file_is_unavailable(tmp_path):
    """T-R1 — on disk is not the same as usable, and the diagnostic says so."""
    fake = tmp_path / "linkertool"
    fake.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    fake.chmod(stat.S_IRUSR)

    capabilities = probe_linker(fake)
    assert capabilities.available is False
    assert "not executable" in capabilities.diagnostic


def test_a_binary_that_resolves_nothing_is_unusable(tmp_path):
    """A file that runs but is not the linker must not pass for one.

    Answering `available=True` here would move the failure to the first real
    document, which is exactly the shape of failure the probe exists to
    prevent.
    """
    fake = tmp_path / "linkertool"
    fake.write_text("#!/bin/sh\necho '<p>nada</p>'\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    capabilities = probe_linker(fake)
    assert capabilities.available is False
    assert "unusable" in capabilities.diagnostic


def test_a_binary_that_will_not_execute_is_reported_not_raised(tmp_path):
    """An unrunnable file (bad interpreter) is a diagnostic, not an OSError."""
    fake = tmp_path / "linkertool"
    fake.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    capabilities = probe_linker(fake)
    assert capabilities.available is False
    assert capabilities.diagnostic


def test_resolve_binary_prefers_the_upstream_default_over_path(monkeypatch):
    """T-R2 — A-L.5's search order, and it is not arbitrary.

    `/usr/local/bin/linkertool` is upstream's own default for the
    `lexml.linkertool` property (`Linker.scala:25`), so a checkout following
    the reference deployment is found with no configuration.
    """
    monkeypatch.setattr(os.path, "isfile", lambda p: p == DEFAULT_LINKER_PATH)
    monkeypatch.setattr(
        "lexml_nonstat.refs.probe.shutil.which", lambda name: "/somewhere/else/linkertool"
    )

    assert resolve_binary() == DEFAULT_LINKER_PATH


def test_resolve_binary_falls_back_to_path(monkeypatch):
    """T-R2 — and `PATH` is consulted when the default is not there."""
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    monkeypatch.setattr(
        "lexml_nonstat.refs.probe.shutil.which", lambda name: "/opt/bin/linkertool"
    )

    assert resolve_binary() == "/opt/bin/linkertool"


def test_resolve_binary_answers_none_when_there_is_nothing(monkeypatch):
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    monkeypatch.setattr("lexml_nonstat.refs.probe.shutil.which", lambda name: None)

    assert resolve_binary() is None


def test_an_explicit_path_is_not_second_guessed(monkeypatch):
    """A caller naming a path gets that path or nothing — never a fallback."""
    monkeypatch.setattr(os.path, "isfile", lambda p: p == DEFAULT_LINKER_PATH)

    assert resolve_binary("/some/other/linkertool") is None


def test_the_child_environment_forces_utf8():
    """The measured hazard: the binary dies on accented text otherwise.

    `linkertool --help` under a non-UTF-8 locale fails with
    ``commitBuffer: invalid argument (cannot encode character '\\227')``. Every
    paragraph in this corpus is Portuguese, so that is the first paragraph, not
    an edge case — and Cycle 8 lost four defects to encoding, one of which
    conservation structurally could not detect.
    """
    env = linker_env()
    assert env["LC_ALL"] == "C.UTF-8"
    assert env["LANG"] == "C.UTF-8"
    assert "PATH" in env, "the child still needs the rest of the environment"


def test_capabilities_serialise():
    payload = LinkerCapabilities(True, "/x", "1.4.10", "ok").to_dict()
    assert payload == {
        "available": True,
        "path": "/x",
        "version": "1.4.10",
        "diagnostic": "ok",
    }


def test_the_skip_marker_carries_the_probes_own_diagnostic():
    """T-R3 — a skipped run must say *why*, the `requires_nested` rule.

    A missing binary reads differently from one that is present and broken, and
    a user should not have to read the source to tell them apart.
    """
    capabilities = linker_capabilities()
    assert capabilities.diagnostic
    assert requires_linker.kwargs["reason"] == capabilities.diagnostic


@requires_linker
def test_a_real_binary_probes_available():
    """The binary present in this environment answers `available=True`."""
    capabilities = probe_linker()

    assert capabilities.available is True
    assert capabilities.path
    assert os.path.isfile(capabilities.path)
    assert "available at" in capabilities.diagnostic


def test_a_banner_without_a_digit_is_not_recorded_as_a_version(tmp_path):
    """`--version` printing a banner must not fill the version field.

    Measured on the build installed here: `linkertool --version` prints
    `The analise program`, the cmdargs banner, with no version in it. A field
    labelled "version" holding that is worse than an empty one, and nothing
    branches on it anyway (invariant #12).
    """
    from lexml_nonstat.refs.probe import _version_of

    fake = tmp_path / "linkertool"
    fake.write_text("#!/bin/sh\necho 'The analise program'\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    assert _version_of(str(fake)) == ""


def test_a_real_version_string_is_recorded(tmp_path):
    from lexml_nonstat.refs.probe import _version_of

    fake = tmp_path / "linkertool"
    fake.write_text("#!/bin/sh\necho 'lexml-linker 1.4.10'\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    assert _version_of(str(fake)) == "lexml-linker 1.4.10"
