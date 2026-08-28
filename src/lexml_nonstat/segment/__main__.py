"""Inspect a document's front/back matter segmentation.

    python3 -m lexml_nonstat.segment samples/port_mf_277_20180607.docx
    python3 -m lexml_nonstat.segment --format=json samples/*.docx
    python3 -m lexml_nonstat.segment --format=xml samples/ad_srf_22_19970430.docx

Mirrors Cycle 1's ``python -m lexml_nonstat.ingest`` and Cycle 2's
``python -m lexml_nonstat.model``. The unified ``cli.py`` arrives in Cycle 8;
until then each package carries its own debug view.

The text format shows spans as ``start-end`` with the block text beside them,
because a segmentation bug is nearly always a boundary off by one block, and
the number alone does not say which paragraph moved.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lxml import etree

from ..ingest import DocxReadError, StyledDoc, read_docx
from ..profile import get_profile
from . import segment_document
from .model import Segmentation
from .render import (
    render_back_generico,
    render_front_generico,
    render_parte_final,
    render_parte_inicial,
)


def _line(label: str, span, doc: StyledDoc, *, width: int = 62) -> str:
    if span is None:
        return f"  {label:<18} -"
    text = span.text(doc).replace("\n", " ⏎ ")
    if len(text) > width:
        text = text[: width - 3] + "..."
    return f"  {label:<18} [{span.start}-{span.end}] {text}"


def _render_text(seg: Segmentation, doc: StyledDoc) -> str:
    front, back = seg.front, seg.back
    lines = [
        f"source     : {seg.source or '-'}",
        f"profile    : {seg.profile}",
        "front      :" + ("  (none)" if front.is_empty else ""),
    ]
    if not front.is_empty:
        lines += [
            _line("epigrafe", front.epigraph, doc),
            _line("ementa", front.ementa, doc),
            _line("preambulo", front.preamble, doc),
            _line("formula", front.enacting_formula, doc),
        ]
        if front.fields:
            lines.append(f"  {'fields':<18} {len(front.fields)}")
            for field in front.fields:
                lines.append(f"    · [{field.source_index}] {field.label}")

    lines.append("body       :" + _line("", seg.body, doc)[20:])

    lines.append("back       :" + ("  (none)" if back.is_empty else ""))
    for signature in back.signatures:
        lines.append(
            f"  signature          [{signature.span.start}-{signature.span.end}] "
            f"{signature.name}"
            + (f" / {signature.cargo}" if signature.cargo else "")
        )
        if signature.local_date:
            date = f" → {signature.date.urn_repr}" if signature.date else ""
            lines.append(f"    local/date       {signature.local_date}{date}")
    if back.local_date is not None:
        lines.append(_line("local/date", back.local_date, doc))
    if back.trailing is not None:
        lines.append(_line("trailing", back.trailing, doc))

    if seg.annexes:
        lines.append(f"annexes    : {len(seg.annexes)}")
        for annex in seg.annexes:
            lines.append(
                f"  · [{annex.span.start}-{annex.span.end}] "
                f"{annex.label}  (!{annex.fragment})"
            )
    else:
        lines.append("annexes    : none")

    return "\n".join(lines)


def _render_xml(seg: Segmentation, doc: StyledDoc) -> str:
    """Both renderings side by side — the statutory one and the open one."""

    def dump(element) -> str:
        return etree.tostring(element, pretty_print=True, encoding="unicode")

    out: list[str] = ["<!-- norma: ParteInicial / ParteFinal -->"]
    for element in (
        render_parte_inicial(seg.front, doc),
        render_parte_final(seg.back, doc),
    ):
        out.append(dump(element) if element is not None else "<!-- (none) -->")

    out.append("<!-- generico: Agrupamento blocks -->")
    blocks = render_front_generico(seg.front, doc) + render_back_generico(
        seg.back, doc
    )
    out.extend(dump(e) for e in blocks)
    if not blocks:
        out.append("<!-- (none) -->")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lexml_nonstat.segment",
        description="Segment a document into front matter, body, back matter, annexes.",
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

    profile = None
    if args.profile is not None:
        try:
            profile = get_profile(args.profile)
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

        seg = segment_document(doc, profile=profile)

        if args.format == "json":
            print(seg.to_json(), end="")
        elif args.format == "xml":
            if len(args.paths) > 1:
                print(f"<!-- === {path.name} === -->")
            print(_render_xml(seg, doc))
        else:
            if len(args.paths) > 1:
                if i:
                    print()
                print(f"=== {path.name} ===")
            print(_render_text(seg, doc))

    return status


if __name__ == "__main__":
    raise SystemExit(main())
