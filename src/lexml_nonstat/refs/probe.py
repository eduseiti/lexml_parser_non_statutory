"""Is a linker actually here? — measured, never assumed.

A-L.5 makes the linker **the third external thing this repository works
without**, after the LLM referee and ``lexml-proposed/``. This module is the
whole of that mechanism, and it follows
:func:`~..validate.schema.probe_capabilities` exactly: it **never raises**, and
a missing binary answers ``available=False`` with a diagnostic saying *why* — a
binary that is absent reads differently from one that is present and broken,
and a user should not have to read the source to tell them apart.

Invariant #12 applies here as it does to the schemas: nothing in this package
branches on a linker *version*. Callers branch only on what a probe of the
binary actually present reported. ``version`` is captured for the report and
for fixture provenance, never for a decision.

Search order is A-L.5's, and it is not arbitrary: ``/usr/local/bin/linkertool``
is upstream's own default for the ``lexml.linkertool`` property
(`Linker.scala:25`), so a checkout that follows the reference deployment is
found without configuration. ``PATH`` comes second.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DEFAULT_LINKER_PATH", "LinkerCapabilities", "linker_env", "probe_linker"]

#: Upstream's default install location (`Linker.scala:25`), searched first.
DEFAULT_LINKER_PATH = "/usr/local/bin/linkertool"

#: How long the probe waits for a version banner before giving up.
_PROBE_TIMEOUT = 10.0


def linker_env() -> dict[str, str]:
    """The environment a ``linkertool`` child must run under.

    Measured, not defensive: with a non-UTF-8 locale the binary dies with
    ``commitBuffer: invalid argument (cannot encode character '\\227')`` the
    moment it writes an accented character. Every paragraph in this corpus is
    Portuguese, so that is not an edge case — it is the first paragraph.

    Cycle 8 lost four defects to encoding, one of which **conservation
    structurally could not detect** because both sides of the comparison
    carried the same mojibake. Pinning the child's locale is cheaper than
    finding that class of bug again.
    """
    return {**os.environ, "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}


@dataclass(frozen=True)
class LinkerCapabilities:
    """What a probe of the binary actually present reported.

    ``diagnostic`` is always non-empty and always names the path it looked at,
    so it can be used verbatim as a pytest skip reason (A-L.5) — the
    ``requires_nested`` pattern Cycle 5b established.
    """

    available: bool
    path: str
    version: str
    diagnostic: str

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "path": self.path,
            "version": self.version,
            "diagnostic": self.diagnostic,
        }


def resolve_binary(binary: str | Path | None = None) -> str | None:
    """The linker path to use, or ``None`` when there is none.

    ``binary`` wins if given. Otherwise :data:`DEFAULT_LINKER_PATH` first, then
    ``PATH``.
    """
    if binary is not None:
        candidate = str(binary)
        return candidate if os.path.isfile(candidate) else None
    if os.path.isfile(DEFAULT_LINKER_PATH):
        return DEFAULT_LINKER_PATH
    return shutil.which("linkertool")


def probe_linker(binary: str | Path | None = None) -> LinkerCapabilities:
    """Measure whether a usable ``linkertool`` is present. Never raises.

    "Usable" is not "on disk": the probe spawns the binary and puts a known
    citation to it, because a file that will not execute — wrong architecture,
    a dangling symlink into an unbuilt tree, a missing shared library — is
    exactly as unavailable as a file that is not there, and answering
    ``available=True`` for it would move the failure to the first real
    document.
    """
    path = resolve_binary(binary)
    if path is None:
        looked = str(binary) if binary is not None else (
            f"{DEFAULT_LINKER_PATH} or PATH"
        )
        return LinkerCapabilities(
            False,
            "",
            "",
            f"linkertool unavailable: no executable found at {looked} "
            "(the linker is optional; references resolve to none without it)",
        )

    if not os.access(path, os.X_OK):
        return LinkerCapabilities(
            False,
            path,
            "",
            f"linkertool unavailable: {path} exists but is not executable",
        )

    try:
        completed = subprocess.run(
            [path, "--hxml", "--xml", "--frase", _PROBE_SENTENCE],
            capture_output=True,
            timeout=_PROBE_TIMEOUT,
            env=linker_env(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return LinkerCapabilities(
            False,
            path,
            "",
            f"linkertool unavailable: {path} did not run: {exc}",
        )

    output = completed.stdout.decode("utf-8", errors="replace")
    if _PROBE_URN not in output:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        return LinkerCapabilities(
            False,
            path,
            "",
            f"linkertool unusable: {path} ran but did not resolve a known "
            f"citation (expected {_PROBE_URN})"
            + (f": {detail[:200]}" if detail else ""),
        )

    return LinkerCapabilities(
        True,
        path,
        _version_of(path),
        f"linkertool available at {path}",
    )


#: A citation the linker has resolved since long before this cycle, used to
#: prove the binary works rather than merely exists. Deliberately federal: a
#: non-federal authority in the *context* would resolve nothing (A-L.9), and a
#: probe must not fail for a reason unrelated to the binary's health.
_PROBE_SENTENCE = "Lei nº 12.527, de 18 de novembro de 2011"
_PROBE_URN = "urn:lex:br:federal:lei:2011-11-18;12527"


def _version_of(path: str) -> str:
    """A best-effort version string. Recorded, never branched on (#12).

    Returns ``""`` rather than a guess when the binary has nothing to say.
    Measured on the build installed here: ``linkertool --version`` prints
    ``The analise program`` — the `cmdargs` banner, with no version in it. That
    is worth *nothing* to a reader, and worse than nothing in a field labelled
    "version", so it is filtered out: only a string actually containing a digit
    is recorded.

    Nothing in this package branches on the result (invariant #12), so an empty
    answer costs no capability. It only means the report says "unknown" instead
    of asserting something false.
    """
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            timeout=_PROBE_TIMEOUT,
            env=linker_env(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = completed.stdout.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    first = text.splitlines()[0].strip()
    return first if any(character.isdigit() for character in first) else ""
