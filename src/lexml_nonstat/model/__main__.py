"""Inspect a document's extracted metadata.

    python3 -m lexml_nonstat.model samples/port_mf_277_20180607.docx
    python3 -m lexml_nonstat.model --format=xml samples/parecer_93_*.docx
    python3 -m lexml_nonstat.model --format=json samples/*.docx

Mirrors Cycle 1's ``python -m lexml_nonstat.ingest``. The unified ``cli.py``
arrives in Cycle 8; until then each package carries its own debug view.

The text format leads with provenance (``date_source``, ``authority_source``)
because that is what you need when a URN comes out wrong: the value alone does
not tell you which branch of the extraction chain produced it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..ingest import DocxReadError, read_docx
from ..profile import get_profile
from .metadata import extract_metadata


def _render_text(meta) -> str:
    lines = [
        f"source     : {meta.source or '-'}",
        f"profile    : {meta.profile}",
        f"urn        : {meta.urn}",
        f"complete   : {meta.complete}"
        + ("" if meta.complete else f"   missing: {', '.join(meta.missing)}"),
        f"authority  : {meta.authority or '-'}  ({meta.authority_source or 'none'})",
        f"doc_type   : {meta.doc_type or '-'}",
        f"number     : {meta.number or '-'}",
        f"date       : {meta.date.urn_repr if meta.date else '-'}"
        f"  ({meta.date_source or 'none'})",
        f"epigraph   : {meta.epigraph or '-'}",
    ]
    if meta.proprietary:
        lines.append(f"fields     : {len(meta.proprietary)}")
        for field in meta.proprietary:
            value = field.value if len(field.value) <= 68 else field.value[:65] + "..."
            lines.append(f"  · [{field.source_index}] {field.label}: {value}")
    else:
        lines.append("fields     : none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lexml_nonstat.model",
        description="Extract and display document metadata (URN, profile, fields).",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="DOCX file(s)")
    parser.add_argument(
        "--format",
        choices=("text", "json", "xml"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="force a profile instead of auto-selecting",
    )
    args = parser.parse_args(argv)

    if args.profile is not None:
        try:
            get_profile(args.profile)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    status = 0
    for i, path in enumerate(args.paths):
        try:
            doc = read_docx(path)
        except (DocxReadError, OSError) as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            status = 1
            continue

        meta = extract_metadata(doc, profile=args.profile, filename=path.name)

        if args.format == "json":
            print(meta.to_json(), end="")
        elif args.format == "xml":
            print(meta.to_xml_string(), end="")
        else:
            if len(args.paths) > 1:
                if i:
                    print()
                print(f"=== {path.name} ===")
            print(_render_text(meta))

    return status


if __name__ == "__main__":
    raise SystemExit(main())
