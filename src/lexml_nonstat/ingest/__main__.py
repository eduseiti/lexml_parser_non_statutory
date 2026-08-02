"""``--dump-styled``: inspect what ingestion actually saw.

    python -m lexml_nonstat.ingest samples/parecer_93_2018_decor_cgu_agu.docx
    python -m lexml_nonstat.ingest --format=text samples/*.docx

Mirrors Cycle 0's ``python -m lexml_nonstat.validate``. The unified ``cli.py``
with a ``dump-styled`` subcommand is Cycle 8's deliverable; this is the debug
view Cycle 1 owes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .docx_reader import DocxReadError, read_docx
from .styled import StyledDoc, StyledPara, StyledTable


def _format_text(doc: StyledDoc) -> str:
    """One line per block, showing the signals that drive later cycles."""
    lines: list[str] = [f"# {doc.source or '(unnamed)'} — {len(doc.blocks)} blocks"]
    for block in doc.blocks:
        if isinstance(block, StyledTable):
            rows, cols = block.shape
            lines.append(f"[{block.index:4d}] TABLE {rows}x{cols}")
            continue
        marks = []
        if block.style and block.style != "Normal":
            marks.append(block.style)
        if block.num_id is not None:
            marks.append(f"num={block.num_id}/{block.ilvl}")
        marks.append(f"ind={block.indent_direct if block.indent_direct is not None else '-'}"
                     f"/{block.indent_effective}")
        if block.alignment:
            marks.append(block.alignment)
        prefix = f"[{block.index:4d}] {' '.join(marks)}"
        lines.append(f"{prefix} :: {block.text}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lexml_nonstat.ingest",
        description="Dump the StyledDoc a .docx file ingests to.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="DOCX files to read")
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="json (default) for the golden form, text for a readable summary",
    )
    parser.add_argument(
        "--keep-strikethrough",
        action="store_true",
        help="retain struck-through runs, which are dropped by default",
    )
    args = parser.parse_args(argv)

    failed = False
    for path in args.files:
        try:
            doc = read_docx(path, drop_strikethrough=not args.keep_strikethrough)
        except DocxReadError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failed = True
            continue
        if args.format == "json":
            sys.stdout.write(doc.to_json())
        else:
            print(_format_text(doc))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
