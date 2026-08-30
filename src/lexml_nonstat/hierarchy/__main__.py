"""Inspect a document's inferred hierarchy.

    python3 -m lexml_nonstat.hierarchy samples/pn_cst_38_19801031.docx
    python3 -m lexml_nonstat.hierarchy --format=json samples/*.docx
    python3 -m lexml_nonstat.hierarchy --why samples/parecer_93_2018_decor_cgu_agu.docx

Mirrors Cycles 1–3's package debug views. Cycle 8's
``python3 -m lexml_nonstat dump-tree`` delegates to exactly the renderers below,
so the two agree by construction rather than by maintenance.

``--why`` is the one that earns its keep. When a document comes back flat, the
question is always *what did you throw away and why*, and
``DocSignals.rejected`` has the answer — that is what it is recorded for
(plan invariant #10).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..ingest import DocxReadError, read_docx
from ..model.nodes import ListNode, Para, Section, Table
from ..profile import get_profile
from . import HierarchyDoc, HierarchyTree, infer_hierarchy


def _node_summary(node) -> str:
    if isinstance(node, Para):
        text = node.text.strip().replace("\n", " ")
        mark = "" if node.kind == "prose" else f"[{node.kind}] "
        return f"{mark}{text[:70]}"
    if isinstance(node, ListNode):
        return f"<list {'ol' if node.ordered else 'ul'} × {len(node.items)}>"
    if isinstance(node, Table):
        rows, cols = node.shape
        return f"<table {rows}×{cols}>"
    return "<?>"


def _render_section(section: Section, indent: int, lines: list[str], *, verbose: bool) -> None:
    head = " ".join(p for p in (section.label, section.heading) if p) or "(untitled)"
    lines.append(
        "  " * indent
        + f"L{section.level} {section.kind:<10} {head[:64]}"
        + (f"   ← {','.join(section.evidence.signals)}" if verbose else "")
    )
    if verbose:
        for node in section.body:
            lines.append("  " * (indent + 1) + "· " + _node_summary(node))
    for child in section.children:
        _render_section(child, indent + 1, lines, verbose=verbose)


def _render_tree(tree: HierarchyTree, title: str, *, verbose: bool) -> str:
    lines = [
        f"{title}: {'flat' if tree.flat else 'structured'}  "
        f"confidence={tree.confidence}  sections={len(list(tree.walk()))}  "
        f"depth={tree.max_depth}  blocks={tree.signals.n_blocks}"
    ]
    if tree.preamble:
        lines.append(f"  preamble ({len(tree.preamble)} nodes)")
        if verbose:
            for node in tree.preamble:
                lines.append("    · " + _node_summary(node))
    for section in tree.sections:
        _render_section(section, 1, lines, verbose=verbose)
    if verbose and tree.signals.rejected:
        lines.append(f"  rejected ({len(tree.signals.rejected)}):")
        lines.extend("    ! " + reason for reason in tree.signals.rejected)
    return "\n".join(lines)


def _render_text(result: HierarchyDoc, *, verbose: bool) -> str:
    out = [
        f"source     : {result.source or '-'}",
        f"profile    : {result.profile}",
        _render_tree(result.body, "body", verbose=verbose),
    ]
    for annex in result.annexes:
        out.append(
            _render_tree(annex.tree, f"annex {annex.fragment} ({annex.label})", verbose=verbose)
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lexml_nonstat.hierarchy",
        description="Infer the hierarchy of a document's body and annexes.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="DOCX file(s)")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )
    parser.add_argument(
        "--why",
        action="store_true",
        help="show evidence signals, body nodes and rejected candidates",
    )
    parser.add_argument("--profile", default=None, help="force a profile")
    args = parser.parse_args(argv)

    profile = None
    if args.profile is not None:
        try:
            profile = get_profile(args.profile)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    status = 0
    for position, path in enumerate(args.paths):
        try:
            doc = read_docx(path)
        except (DocxReadError, OSError) as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            status = 1
            continue

        result = infer_hierarchy(doc, profile=profile)
        if args.format == "json":
            print(result.to_json(), end="")
            continue
        if len(args.paths) > 1:
            if position:
                print()
            print(f"=== {path.name} ===")
        print(_render_text(result, verbose=args.why))

    return status


if __name__ == "__main__":
    raise SystemExit(main())
