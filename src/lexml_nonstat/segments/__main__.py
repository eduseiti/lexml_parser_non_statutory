"""Dump a document's segments.

    PYTHONPATH=src python3 -m lexml_nonstat.segments samples/pn_cst_38_19801031.docx
    PYTHONPATH=src python3 -m lexml_nonstat.segments --format=jsonl tests/golden/generico/*.xml

A DOCX runs the whole pipeline and segments the model (the primary path); an
XML file is read back through whichever reader its markup calls for. Cycle 8's
``python3 -m lexml_nonstat segment`` is the supported form and takes the global
options; this one stays as the package's own debug view.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    fmt = "csv"
    emitter = "generico"
    for flag in (a for a in argv if a.startswith("--")):
        name, _, value = flag[2:].partition("=")
        if name == "format" and value in ("csv", "jsonl"):
            fmt = value
        elif name == "emitter":
            emitter = value
        else:
            print(f"unknown option: {flag}", file=sys.stderr)
            return 2

    if not args:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    from . import segments, segments_from_model, to_csv, to_jsonl

    write = to_csv if fmt == "csv" else to_jsonl
    for path in args:
        source = Path(path)
        if source.suffix.lower() == ".docx":
            from ..ingest import read_docx
            from ..model import build_model

            model = build_model(read_docx(source), filename=source.name)
            rows = segments_from_model(model, emitter=emitter)
        else:
            rows = segments(source)
        sys.stdout.write(write(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
