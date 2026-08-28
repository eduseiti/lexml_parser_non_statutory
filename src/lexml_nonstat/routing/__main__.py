"""Inspect a document's routing verdict, and the decisions behind it.

    python3 -m lexml_nonstat.routing samples/*.docx
    python3 -m lexml_nonstat.routing --format=json samples/port_mf_277_20180607.docx
    python3 -m lexml_nonstat.routing --decisions-report samples/*.docx
    python3 -m lexml_nonstat.routing --emitter=generico-aninhado samples/pn_cst_38_19801031.docx

Mirrors Cycles 1–3's per-package debug views; the unified ``cli.py`` arrives in
Cycle 8. ``--referee`` defaults to ``none`` (§7.3 constraint 7): this command
makes no network call unless asked to.

The text format leads with the blockers rather than the route, because on this
corpus the route is `generico` fourteen times out of fifteen and the
interesting question is always *why*.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from ..ingest import DocxReadError, read_docx
from ..profile import get_profile
from ..referee import REFEREE_MODES, build_referee
from ..telemetry import DecisionLog, render_report
from ..validate.schema import GENERATIONS, SHIPPED
from .viability import EMITTERS, StatutoryViability, assess_viability


def _render_text(verdict: StatutoryViability) -> str:
    lines = [
        f"source     : {verdict.source or '-'}",
        f"profile    : {verdict.profile}",
        f"route      : {verdict.route}  (confidence {verdict.confidence:.2f})",
        f"articles   : {verdict.articles_found} found, "
        f"{verdict.articles_quoted} quoted, {verdict.articles_own} own"
        f"  monotonic={verdict.numbering_monotonic}",
        f"coverage   : {verdict.coverage:.0%}"
        f"   anexos={'yes' if verdict.has_anexos else 'no'}",
        f"referee    : consulted={verdict.referee_consulted} "
        f"overrode={verdict.referee_overrode}",
    ]
    gates = verdict.evidence.get("gates", {})
    if gates:
        lines.append(
            "gates      : "
            + "  ".join(f"{'✓' if ok else '✗'} {name}" for name, ok in gates.items())
        )
    if verdict.blockers:
        lines.append("blockers   :")
        for blocker in verdict.blockers:
            mark = "veto" if blocker.vetoes else "note"
            lines.append(f"  [{mark}] {blocker.code}")
            lines.append(f"         {blocker.detail}")
    else:
        lines.append("blockers   : none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lexml_nonstat.routing",
        description="Decide whether a document can be published as an articulated Norma.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="DOCX file(s)")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )
    parser.add_argument("--profile", default=None, help="force a profile")
    parser.add_argument(
        "--emitter",
        choices=EMITTERS,
        default="generico",
        help="the rendering intended; affects blockers only, never the route (A-R.7)",
    )
    parser.add_argument(
        "--generation",
        choices=GENERATIONS,
        default=SHIPPED,
        help="schema generation to probe for capabilities",
    )
    parser.add_argument(
        "--referee",
        choices=REFEREE_MODES,
        default="none",
        help="adjudicator for low-confidence decisions (default: none)",
    )
    parser.add_argument(
        "--referee-model", default=None, help="model id or GGUF path for the referee"
    )
    parser.add_argument(
        "--referee-cache", type=Path, default=None, help="referee disk cache directory"
    )
    parser.add_argument(
        "--decisions-report",
        action="store_true",
        help="print §7.4's decision summary after the verdicts",
    )
    parser.add_argument(
        "--log",
        choices=("quiet", "info", "debug"),
        default="quiet",
        help="decision log verbosity (default: quiet — warnings only)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(levelname)-5s %(message)s",
        level={"quiet": logging.WARNING, "info": logging.INFO, "debug": logging.DEBUG}[
            args.log
        ],
        stream=sys.stderr,
    )

    profile = None
    if args.profile is not None:
        try:
            profile = get_profile(args.profile)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    referee_kwargs: dict = {}
    if args.referee == "api":
        if args.referee_model:
            referee_kwargs["model"] = args.referee_model
        referee_kwargs["api_key"] = os.environ.get("LEXML_REFEREE_API_KEY")
        referee_kwargs["cache"] = args.referee_cache
    elif args.referee == "local":
        if not args.referee_model:
            print(
                "error: --referee=local needs --referee-model=<path to .gguf>",
                file=sys.stderr,
            )
            return 2
        referee_kwargs["model_path"] = args.referee_model
        referee_kwargs["cache"] = args.referee_cache

    try:
        referee = build_referee(args.referee, **referee_kwargs)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    log = DecisionLog()
    status = 0
    for i, path in enumerate(args.paths):
        try:
            doc = read_docx(path)
        except (DocxReadError, OSError) as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            status = 1
            continue

        verdict = assess_viability(
            doc,
            profile=profile,
            referee=referee,
            log=log,
            emitter=args.emitter,
            generation=args.generation,
        )

        if args.format == "json":
            print(verdict.to_json(), end="")
        else:
            if len(args.paths) > 1:
                if i:
                    print()
                print(f"=== {path.name} ===")
            print(_render_text(verdict))

    if args.decisions_report:
        print()
        print(render_report(log))

    return status


if __name__ == "__main__":
    raise SystemExit(main())
