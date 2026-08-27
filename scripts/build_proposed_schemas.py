#!/usr/bin/env python3
"""Generate ``lexml-proposed/`` from ``lexml/`` by applying the maintainers' change.

The LexML maintainers have proposed making ``AgrupamentoHierarquico`` a
prose-bearing recursive container (``docs/20260827_111015_…`` §2), but the
change is not yet released in the official schema repository. Until it is, this
script produces a **local schema generation** carrying the change, so the
parser's nested emitter can be built and tested now.

Why generate rather than commit a hand-edited fork
--------------------------------------------------
A forked copy rots silently: when upstream re-issues ``lexml-base.xsd``, a
hand-edited duplicate keeps validating against the *old* baseline and nobody
notices. Deriving the variant from ``lexml/`` on demand means:

* the diff against upstream is always exactly the proposal, and is reviewable;
* ``lexml/`` stays byte-identical to upstream, preserving drift detection;
* when upstream ships the change, the patch stops applying and says so — which
  is the signal to re-vendor and retire this script.

The generated directory is committed, so a clean checkout needs no build step.
Run ``--check`` to confirm it is still what this script would produce; a stale
or hand-edited tree is reported rather than left to drift quietly.

Usage::

    python3 scripts/build_proposed_schemas.py           # regenerate
    python3 scripts/build_proposed_schemas.py --check    # verify, don't write
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = REPO_ROOT / "lexml"
GENERATED = REPO_ROOT / "lexml-proposed"

#: Marks the generated files, so nobody mistakes one for an upstream schema.
BANNER = """\
<!--
  ==========================================================================
  GENERATED FILE — DO NOT EDIT BY HAND.

  Produced by scripts/build_proposed_schemas.py from lexml/{source}.

  This is a LOCAL schema generation carrying the LexML maintainers' proposed
  change to AgrupamentoHierarquico (see the "sugestao_mudanca" proposal and
  docs/20260827_111015_revised_plan_recursive_agrupamento_hierarquico_adoption.md).

  The change is NOT yet released upstream. This directory exists so the nested
  emitter can be developed and tested before the official schemas ship it.
  When upstream releases the change, re-vendor lexml/ and delete this tree.
  ==========================================================================
-->
"""


class PatchError(RuntimeError):
    """A patch did not apply cleanly — upstream has changed underneath us."""


@dataclass(frozen=True)
class Patch:
    """One exact-match text substitution against an upstream schema file."""

    name: str
    filename: str
    old: str
    new: str

    def apply(self, text: str) -> str:
        found = text.count(self.old)
        if found != 1:
            raise PatchError(
                f"patch {self.name!r} expected exactly one match in "
                f"{self.filename}, found {found}. Upstream has changed: review "
                "the proposal against the new schema before regenerating."
            )
        return text.replace(self.old, self.new)


# The proposal, verbatim. `sequence` -> `choice`, plus Agrupamento and Bloco.
_AH_OLD = """\t\t\t\t<xsd:extension base="hierarchy">
\t\t\t\t\t<xsd:sequence>
\t\t\t\t\t\t<xsd:group ref="LXhierCompleto" minOccurs="1" maxOccurs="unbounded"/>
\t\t\t\t\t</xsd:sequence>
\t\t\t\t\t<xsd:attributeGroup ref="nome"/>
\t\t\t\t</xsd:extension>"""

_AH_NEW = """\t\t\t\t<xsd:extension base="hierarchy">
\t\t\t\t\t<xsd:choice minOccurs="1" maxOccurs="unbounded">
\t\t\t\t\t\t<xsd:group ref="LXhierCompleto"/>
\t\t\t\t\t\t<xsd:element ref="Agrupamento"/>
\t\t\t\t\t\t<xsd:element ref="Bloco"/>
\t\t\t\t\t</xsd:choice>
\t\t\t\t\t<xsd:attributeGroup ref="nome"/>
\t\t\t\t</xsd:extension>"""

PATCHES: tuple[Patch, ...] = (
    Patch(
        "agrupamento_hierarquico_accepts_prose",
        "lexml-base.xsd",
        _AH_OLD,
        _AH_NEW,
    ),
)


def _banner_for(source: str) -> str:
    return BANNER.format(source=source)


def _insert_banner(text: str, source: str) -> str:
    """Put the banner directly after the XML declaration, if there is one."""
    banner = _banner_for(source)
    if text.startswith("<?xml"):
        end = text.index("?>") + 2
        # Keep the remainder byte-identical to upstream, so a diff against
        # lexml/ shows the patches and nothing else.
        return f"{text[:end]}\n{banner}{text[end:]}"
    return banner + text


def generate(destination: Path) -> dict[str, str]:
    """Write the patched generation into ``destination``.

    Every ``*.xsd`` in ``lexml/`` is copied; those with patches are patched.
    Returns a mapping of filename to final text, for the checking path.
    """
    if not UPSTREAM.is_dir():
        raise FileNotFoundError(f"upstream schema directory missing: {UPSTREAM}")

    by_file: dict[str, list[Patch]] = {}
    for patch in PATCHES:
        by_file.setdefault(patch.filename, []).append(patch)

    unknown = set(by_file) - {p.name for p in UPSTREAM.glob("*.xsd")}
    if unknown:
        raise PatchError(f"patches target files absent from {UPSTREAM}: {sorted(unknown)}")

    written: dict[str, str] = {}
    destination.mkdir(parents=True, exist_ok=True)

    for source in sorted(UPSTREAM.glob("*.xsd")):
        text = source.read_text(encoding="utf-8")
        for patch in by_file.get(source.name, ()):
            text = patch.apply(text)
        text = _insert_banner(text, source.name)
        written[source.name] = text
        (destination / source.name).write_text(text, encoding="utf-8")

    return written


def check(destination: Path) -> list[str]:
    """Return a list of problems if ``destination`` is not what we would write."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        expected = generate(Path(tmp))

    problems = []
    if not destination.is_dir():
        return [f"{destination} does not exist; run scripts/build_proposed_schemas.py"]

    for name, text in expected.items():
        path = destination / name
        if not path.exists():
            problems.append(f"missing: {name}")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"stale: {name}")

    for path in destination.glob("*.xsd"):
        if path.name not in expected:
            problems.append(f"unexpected extra file: {path.name}")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed generation is current; write nothing",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=GENERATED,
        help=f"destination directory (default: {GENERATED.name}/)",
    )
    args = parser.parse_args(argv)

    try:
        if args.check:
            problems = check(args.out)
            if problems:
                print(f"{args.out.name}/ is out of date:", file=sys.stderr)
                for problem in problems:
                    print(f"  - {problem}", file=sys.stderr)
                print(
                    "\nRegenerate with: python3 scripts/build_proposed_schemas.py",
                    file=sys.stderr,
                )
                return 1
            print(f"{args.out.name}/ is current ({len(PATCHES)} patch(es) applied).")
            return 0

        # Remove only the schemas we own, so hand-written companions in the
        # directory (README.md) survive regeneration.
        if args.out.exists():
            for stale in args.out.glob("*.xsd"):
                stale.unlink()
        written = generate(args.out)
    except (PatchError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {len(written)} schema(s) to {args.out}/")
    for patch in PATCHES:
        print(f"  applied {patch.name} to {patch.filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
