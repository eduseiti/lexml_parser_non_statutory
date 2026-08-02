"""Minimal validation entry point.

    python -m lexml_nonstat.validate --schema=both file.xml [file.xml ...]

Cycle 8 delivers the full CLI (``parse``, ``segment``, ``validate``, …). This
exists so the ``--schema`` selector required by Cycle 0 is exercised end to end
rather than only through the library API.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .schema import SCHEMA_SELECTORS, UnknownSchemaError, validate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lexml_nonstat.validate",
        description="Validate documents against the LexML schemas, offline.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="XML files to validate")
    parser.add_argument(
        "--schema",
        default="both",
        choices=SCHEMA_SELECTORS,
        help="which schema(s) to validate against (default: both)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="only report failures"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Returns 0 when every file validates, 1 otherwise."""
    args = build_parser().parse_args(argv)

    failures = 0
    for path in args.files:
        if not path.exists():
            print(f"{path}: no such file", file=sys.stderr)
            failures += 1
            continue

        try:
            report = validate(path, args.schema)
        except UnknownSchemaError as exc:  # pragma: no cover - argparse guards
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if report.ok:
            if not args.quiet:
                print(f"{path}: OK ({', '.join(report.schemas)})")
        else:
            failures += 1
            print(f"{path}: INVALID", file=sys.stderr)
            for line in report.summary().splitlines():
                print(f"  {line}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
