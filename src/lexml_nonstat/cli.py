"""The unified command line — plan §8, Cycle 8.

    lexml-nonstat parse samples/pn_cst_38_19801031.docx
    python3 -m lexml_nonstat parse --emitter=generico-aninhado -o out/ samples/*.docx
    python3 -m lexml_nonstat capabilities
    python3 -m lexml_nonstat segment --format=csv samples/port_mf_277_20180607.docx

Eight subcommands over the same argument vocabulary, mirroring `FECmdLine`'s
shape: ``parse``, ``dump-styled``, ``dump-tree``, ``segment``, ``validate``,
``list-profiles``, ``decisions-report`` and ``capabilities``.

**This module renders nothing.** Every subcommand is a thin adapter over a
library function seven earlier cycles delivered, and
``tests/regression/test_cli_corpus.py`` asserts that byte-for-byte: what
``parse --emitter=generico`` writes is exactly ``render_generico(...)``'s
output, and what ``segment --format=csv`` writes is exactly ``to_csv(...)``'s.
A CLI that re-implemented a rendering would be a second source of truth for it,
and the goldens would stop covering what the user actually runs.

**Three exit codes, one meaning each.** ``0`` every document handled; ``1`` a
document failed — unreadable source, invalid output, or any warning under
``--strict``; ``2`` the invocation itself is wrong — unknown profile, unknown
emitter, unsupported format, or a rendering the schemas present cannot
validate. The last of those is amendment **A-R.9**'s requirement: asking for
``generico-aninhado`` on a checkout without the patched schemas exits cleanly
with the probe's own diagnostic and never a traceback.

**The referee defaults to ``none``** (§7.3 constraint 7), as it does in every
other entry point here. Nothing this module does makes a network call unless
asked to in so many words.

**Warnings go to stderr, output to stdout.** Always, in every format, so
``parse | validate -`` is never polluted by a diagnostic. ``--strict`` changes
the *exit code* and nothing else — a test pins that stdout is identical with
and without it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Sequence

from .ingest import DocxReadError, StyledDoc, UnsupportedFormatError, read_document
from .profile import UnknownProfileError, all_profiles, get_profile
from .referee import DEFAULT_BASE_URL, REFEREE_MODES, build_referee
from .routing.viability import EMITTERS
from .telemetry import DecisionLog, render_report
from .validate.schema import (
    GENERATIONS,
    PROPOSED,
    SCHEMA_SELECTORS,
    SHIPPED,
    probe_capabilities,
)
from .warnings import EMITTER_UNAVAILABLE, UNREADABLE_SOURCE, Warning, collect_warnings

__all__ = ["CHOOSABLE_EMITTERS", "COMMANDS", "build_parser", "main"]

#: What ``--emitter`` accepts. ``auto`` is the default and follows the route:
#: a `norma`-routed document goes through §4.2's validate-then-fallback, every
#: other through the flat emitter. The three named emitters are §4.4's
#: :data:`~.routing.viability.EMITTERS` verbatim — the CLI adds no fourth.
CHOOSABLE_EMITTERS: tuple[str, ...] = ("auto",) + EMITTERS

COMMANDS: tuple[str, ...] = (
    "parse",
    "dump-styled",
    "dump-tree",
    "segment",
    "validate",
    "list-profiles",
    "decisions-report",
    "capabilities",
)

_OK, _FAILED, _MISUSE = 0, 1, 2

#: An `xsd:ID` is an NCName and a filename should be no worse: the URN's colons
#: and semicolons are not portable across filesystems, so a written document is
#: named by a slug of its URN. ``!`` is kept, because §2.9's annex convention
#: uses it and it is legal in every filesystem this runs on.
_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9._!-]+")


# ---------------------------------------------------------------------------
# shared plumbing
# ---------------------------------------------------------------------------


def _slug(urn: str, fallback: str) -> str:
    slug = _SLUG_UNSAFE.sub("_", urn).strip("_")
    return slug or fallback


def _emit(text: str, stream) -> None:
    """Write without adding a newline the caller did not ask for."""
    stream.write(text)
    if text and not text.endswith("\n"):
        stream.write("\n")


def _report_warnings(warnings: Sequence[Warning], stderr) -> None:
    for warning in warnings:
        print(warning.format(), file=stderr)


def _resolve_profile(name: str | None, stderr):
    """``(profile, ok)``. An unknown name is a misuse, not a document failure."""
    if name is None:
        return None, True
    try:
        return get_profile(name), True
    except (KeyError, UnknownProfileError) as exc:
        # The registry's own message already names every profile, so this does
        # not repeat them. `KeyError.__str__` quotes its argument; strip that.
        detail = exc.args[0] if exc.args else str(exc)
        print(f"error: {detail}", file=stderr)
        return None, False


def _build_referee(args, stderr):
    """``(referee, ok)``. Mirrors ``routing/__main__``'s construction exactly."""
    kwargs: dict[str, Any] = {}
    if args.referee == "api":
        if args.referee_model:
            kwargs["model"] = args.referee_model
        # Only for `api`: LocalReferee has no base_url, and passing one would
        # be a TypeError rather than a no-op.
        if getattr(args, "referee_base_url", None):
            kwargs["base_url"] = args.referee_base_url
        kwargs["api_key"] = os.environ.get("LEXML_REFEREE_API_KEY")
        kwargs["cache"] = args.referee_cache
    elif args.referee == "local":
        if not args.referee_model:
            print(
                "error: --referee=local needs --referee-model=<path to .gguf>",
                file=stderr,
            )
            return None, False
        kwargs["model_path"] = args.referee_model
        kwargs["cache"] = args.referee_cache
    try:
        return build_referee(args.referee, **kwargs), True
    except ValueError as exc:
        print(f"error: {exc}", file=stderr)
        return None, False


def _read(path: Path, stderr) -> tuple[StyledDoc | None, int]:
    """Read one source. Returns ``(doc, exit_code)``; ``doc`` is ``None`` on failure.

    This is the whole of Cycle 8's "malformed input ⇒ clean error, no
    traceback" claim. The two failure codes are not interchangeable: a *corrupt*
    document is a document failure (``1``) — the other fifteen files in the run
    still deserve processing — while a path that is not a document at all (a
    directory, a ``.pdf``) is a misuse of the command (``2``), and no amount of
    retrying will make it one.
    """
    if path.is_dir():
        print(f"error: {path}: is a directory, not a document", file=stderr)
        return None, _MISUSE
    try:
        return read_document(path), _OK
    except UnsupportedFormatError as exc:
        print(f"error: {exc}", file=stderr)
        return None, _MISUSE
    except (DocxReadError, OSError, ValueError) as exc:
        print(f"error: {path}: {exc}", file=stderr)
        return None, _FAILED


def _generation_for(emitter: str, requested: str) -> str:
    """Which generation an emitter's output must be validated against.

    Not a free choice. Amendment **A-5b.3**: nested output is invalid against
    the shipped schemas *by design* — that is what ``generico-aninhado`` being
    opt-in means. Validating it against ``lexml/`` would report 35 errors that
    are the schema's absence rather than the document's defect, so the nested
    emitter carries its generation with it.

    An explicitly requested non-default generation still wins: a user who typed
    ``--generation`` meant it.
    """
    if emitter == "generico-aninhado" and requested == SHIPPED:
        return PROPOSED
    return requested


def _capabilities_blocker(emitter: str, generation: str) -> str | None:
    """The A-R.9 gate: is the requested rendering validatable here?

    Only ``generico-aninhado`` needs the maintainers' unreleased change (§2.10).
    The flat and statutory emitters use nothing it adds, so they are never
    gated — amendment A-6.5's point that the annex's nesting is a flag rather
    than a probe applies here too.
    """
    if emitter != "generico-aninhado":
        return None
    probe = probe_capabilities(_generation_for(emitter, generation))
    if probe.nested_agrupamento:
        return None
    return probe.diagnostic


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


def _render(model, emitter: str):
    """The one place an emitter name becomes a rendering. Nothing else chooses."""
    from .render import render_generico, render_generico_aninhado, render_statutory
    from .render.norma import render_norma_checked

    if emitter == "generico":
        return render_generico(model)
    if emitter == "generico-aninhado":
        return render_generico_aninhado(model)
    if emitter == "norma":
        # Forcing `norma` still runs §4.2's gates: the point of the
        # validate-then-fallback is that it cannot be talked out of.
        rendered, blockers = render_norma_checked(model)
        return rendered if not blockers else render_generico(model)
    # `auto` — follow the route. `render_statutory` is itself a no-op for a
    # `generico`-routed document, but going through it keeps one code path.
    return render_statutory(model)


def _validate_documents(rendered, selector: str, generation: str):
    """Validate every document in the bundle; return the first bad report.

    The whole bundle, not just the primary: an annex is a sibling document
    under §2.9's convention, and one that does not validate is exactly as
    unpublishable as a primary that does not.
    """
    from .validate import validate

    for document in rendered.documents:
        report = validate(document, selector, generation=generation)
        if not report.ok:
            return report
    return None


def _write_bundle(rendered, out_dir: Path, source: str | None) -> tuple[Path, ...]:
    """§2.9's naming: ``<slug>.xml`` for the primary, ``<slug>!anexoN.xml`` beside it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    base = _slug(rendered.urn, Path(source or "documento").stem)
    written: list[Path] = []
    for i, xml in enumerate(rendered.to_xml_strings()):
        name = f"{base}.xml" if i == 0 else f"{base}!anexo{i}.xml"
        path = out_dir / name
        path.write_text(xml, encoding="utf-8")
        written.append(path)
    return tuple(written)


def _parse_json(model, rendered, warnings, written) -> dict[str, Any]:
    viability = model.viability
    return {
        "source": model.source,
        "urn": rendered.urn,
        "profile": model.profile,
        "route": model.route,
        "emitter": rendered.emitter,
        "confidence": round(float(getattr(viability, "confidence", 0.0)), 4),
        "hierarchy_confidence": round(float(getattr(model.body, "confidence", 0.0)), 4),
        "flat": bool(getattr(model.body, "flat", True)),
        "referee": {
            "consulted": bool(getattr(viability, "referee_consulted", False)),
            "overrode": bool(getattr(viability, "referee_overrode", False)),
        },
        "blockers": [
            {"code": b.code, "detail": b.detail, "vetoes": b.vetoes}
            for b in getattr(viability, "blockers", ())
        ],
        "warnings": [w.to_dict() for w in warnings],
        "documents": len(rendered.documents),
        "written": [str(p) for p in written],
        "xml": None if written else rendered.to_xml_string(),
    }


def _nested_hint(rendered) -> str:
    """Say when the nested emitter was available and simply not chosen.

    A reader who sees `Bloco nome="nivel"` in the output and knows the
    maintainers' recursive `AgrupamentoHierarquico` exists has no way, from the
    artifact alone, to tell "this parser cannot nest" from "you did not ask it
    to". `--emitter=auto` follows the route (A-R.7) and the route says
    `generico`, so the flat emitter is correct *and* surprising. One line
    removes the ambiguity.
    """
    if rendered.emitter != "generico":
        return ""
    try:
        from .validate import probe_capabilities

        if not probe_capabilities(generation="proposed").nested_agrupamento:
            return ""
    except Exception:  # noqa: BLE001 - a hint must never fail a parse
        return ""
    return "  (generico-aninhado available: --emitter=generico-aninhado --generation=proposed)"


def _parse_text_summary(model, rendered, written) -> str:
    viability = model.viability
    lines = [
        f"source     : {model.source or '-'}",
        f"urn        : {rendered.urn}",
        f"profile    : {model.profile}",
        f"route      : {model.route}  (confidence "
        f"{float(getattr(viability, 'confidence', 0.0)):.2f})",
        f"emitter    : {rendered.emitter}{_nested_hint(rendered)}",
        f"hierarchy  : {'flat' if getattr(model.body, 'flat', True) else 'structured'}"
        f"  (confidence {float(getattr(model.body, 'confidence', 0.0)):.2f})",
        f"referee    : {'consulted' if getattr(viability, 'referee_consulted', False) else 'not consulted'}"
        f", {'overrode' if getattr(viability, 'referee_overrode', False) else 'did not override'}",
        f"documents  : {len(rendered.documents)}",
    ]
    lines.extend(f"wrote      : {p}" for p in written)
    return "\n".join(lines)


def _cmd_parse(args, streams) -> int:
    stdout, stderr = streams
    log = DecisionLog()

    profile, ok = _resolve_profile(args.profile, stderr)
    if not ok:
        return _MISUSE
    referee, ok = _build_referee(args, stderr)
    if not ok:
        return _MISUSE

    unavailable = _capabilities_blocker(args.emitter, args.generation)
    if unavailable is not None:
        _report_warnings(
            (Warning(EMITTER_UNAVAILABLE, unavailable, args.emitter),), stderr
        )
        print(f"error: emitter {args.emitter!r} is unavailable here", file=stderr)
        return _MISUSE

    status = _OK
    warned = False
    for position, path in enumerate(args.paths):
        doc, code = _read(path, stderr)
        if doc is None:
            if code == _MISUSE:
                return _MISUSE
            _report_warnings(
                (Warning(UNREADABLE_SOURCE, "could not be read", str(path)),), stderr
            )
            status = _FAILED
            continue

        from .model import build_model

        model = build_model(
            doc, filename=path.name, profile=profile, log=log, referee=referee
        )
        rendered = _render(model, args.emitter)

        report = _validate_documents(
            rendered, args.schema, _generation_for(rendered.emitter, args.generation)
        )
        written = (
            _write_bundle(rendered, args.out, model.source) if args.out else ()
        )
        warnings = collect_warnings(
            model,
            rendered,
            report=report,
            requested_emitter=args.emitter,
            wrote_annexes=bool(written),
        )
        warned = warned or bool(warnings)

        if args.format == "json":
            _emit(json.dumps(_parse_json(model, rendered, warnings, written), indent=2,
                             ensure_ascii=False), stdout)
        elif written or args.summary:
            if len(args.paths) > 1 and not args.quiet:
                if position:
                    print(file=stdout)
                print(f"=== {path.name} ===", file=stdout)
            _emit(_parse_text_summary(model, rendered, written), stdout)
        else:
            _emit(rendered.to_xml_string(), stdout)

        _report_warnings(warnings, stderr)
        if report is not None and not report.ok:
            status = _FAILED

    if args.strict and warned:
        return _FAILED
    return status


# ---------------------------------------------------------------------------
# the inspection commands — each delegates to the package that owns the view
# ---------------------------------------------------------------------------


def _for_each_document(args, streams, render_one) -> int:
    """The shape every inspection command shares: read, compute, print, continue.

    One unreadable file among fifteen must not stop the other fourteen — a
    batch that abandons its work on the first bad document is useless on the
    300-document corpus Cycle 9 is aimed at.
    """
    stdout, stderr = streams
    profile, ok = _resolve_profile(args.profile, stderr)
    if not ok:
        return _MISUSE

    status = _OK
    for position, path in enumerate(args.paths):
        doc, code = _read(path, stderr)
        if doc is None:
            if code == _MISUSE:
                return _MISUSE
            status = _FAILED
            continue
        text = render_one(doc, path, profile)
        if len(args.paths) > 1 and not args.quiet and args.format == "text":
            if position:
                print(file=stdout)
            print(f"=== {path.name} ===", file=stdout)
        _emit(text, stdout)
    return status


def _cmd_dump_styled(args, streams) -> int:
    from .ingest.__main__ import _format_text

    def render_one(doc, path, profile):
        return doc.to_json() if args.format == "json" else _format_text(doc)

    return _for_each_document(args, streams, render_one)


def _cmd_dump_tree(args, streams) -> int:
    from .hierarchy import infer_hierarchy
    from .hierarchy.__main__ import _render_text

    def render_one(doc, path, profile):
        result = infer_hierarchy(doc, profile=profile)
        if args.format == "json":
            return result.to_json()
        return _render_text(result, verbose=args.why)

    return _for_each_document(args, streams, render_one)


def _cmd_segment(args, streams) -> int:
    from .model import build_model
    from .segments import segments, segments_from_model, to_csv, to_jsonl

    write = to_csv if args.format == "csv" else to_jsonl
    emitter = "generico" if args.emitter == "auto" else args.emitter

    stdout, stderr = streams
    profile, ok = _resolve_profile(args.profile, stderr)
    if not ok:
        return _MISUSE

    status = _OK
    for path in args.paths:
        if path.suffix.lower() == ".xml":
            # A file read from disk has no `RenderedDocument.emitter`; the
            # reader dispatches on markup instead (A-7.3).
            try:
                rows = segments(path)
            except (OSError, ValueError) as exc:
                print(f"error: {path}: {exc}", file=stderr)
                status = _FAILED
                continue
        else:
            doc, code = _read(path, stderr)
            if doc is None:
                if code == _MISUSE:
                    return _MISUSE
                status = _FAILED
                continue
            model = build_model(doc, filename=path.name, profile=profile)
            rows = segments_from_model(model, emitter=emitter)
        stdout.write(write(rows))
    return status


def _cmd_validate(args, streams) -> int:
    from .validate import validate
    from .validate.schema import UnknownSchemaError

    stdout, stderr = streams
    failures = 0
    for path in args.paths:
        if not path.exists():
            print(f"error: {path}: no such file", file=stderr)
            failures += 1
            continue
        try:
            report = validate(path, args.schema, generation=args.generation)
        except UnknownSchemaError as exc:  # pragma: no cover - argparse guards
            print(f"error: {exc}", file=stderr)
            return _MISUSE
        except (OSError, ValueError) as exc:
            print(f"error: {path}: {exc}", file=stderr)
            failures += 1
            continue

        if report.ok:
            if not args.quiet:
                print(f"{path}: OK ({', '.join(report.schemas)})", file=stdout)
        else:
            failures += 1
            print(f"{path}: INVALID", file=stderr)
            for line in report.summary().splitlines():
                print(f"  {line}", file=stderr)
    return _FAILED if failures else _OK


def _cmd_list_profiles(args, streams) -> int:
    stdout, _ = streams
    profiles = all_profiles()
    if args.format == "json":
        _emit(
            json.dumps(
                [
                    {
                        "name": p.name,
                        "urn_type": p.urn_type,
                        "urn_authority": p.urn_authority,
                        "urn_locality": p.urn_locality,
                        "base_score": p.base_score,
                        "field_labels": sorted(p.field_labels),
                        "epigraph_patterns": len(p.epigraph_res),
                    }
                    for p in profiles
                ],
                indent=2,
                ensure_ascii=False,
            ),
            stdout,
        )
        return _OK

    width = max(len(p.name) for p in profiles)
    lines = [f"{len(profiles)} registered profiles"]
    for p in profiles:
        lines.append(
            f"  {p.name:<{width}}  urn_type={p.urn_type:<12} "
            f"authority={p.urn_authority or '-':<10} base_score={p.base_score:.2f}"
            f"  epigraph_patterns={len(p.epigraph_res)}"
        )
    _emit("\n".join(lines), stdout)
    return _OK


def _cmd_decisions_report(args, streams) -> int:
    from .model import build_model

    stdout, stderr = streams
    profile, ok = _resolve_profile(args.profile, stderr)
    if not ok:
        return _MISUSE
    referee, ok = _build_referee(args, stderr)
    if not ok:
        return _MISUSE

    log = DecisionLog()
    status = _OK
    for path in args.paths:
        doc, code = _read(path, stderr)
        if doc is None:
            if code == _MISUSE:
                return _MISUSE
            status = _FAILED
            continue
        build_model(
            doc, filename=path.name, profile=profile, log=log, referee=referee
        )

    _emit(render_report(log), stdout)
    return status


def _cmd_capabilities(args, streams) -> int:
    """A-R.9: report what the schemas actually present permit.

    Both generations, always — the interesting answer is usually the *pair*:
    "shipped says no, proposed says yes" is a working checkout, and "both say
    no" is a checkout without ``lexml-proposed/``. Exit is 0 either way; a
    missing generation is a fact about the checkout, not a failure.
    """
    stdout, _ = streams
    probes = [probe_capabilities(g) for g in GENERATIONS]

    if args.format == "json":
        _emit(json.dumps([p.to_dict() for p in probes], indent=2, ensure_ascii=False),
              stdout)
        return _OK

    lines = []
    for probe in probes:
        lines.append(f"generation {probe.generation}")
        lines.append(f"  available            : {'yes' if probe.available else 'no'}")
        lines.append(
            f"  nested Agrupamento   : "
            f"{'yes' if probe.nested_agrupamento else 'no'}"
        )
        lines.append(f"  {probe.diagnostic}")
    nested = any(p.nested_agrupamento for p in probes)
    lines.append("")
    lines.append(
        "emitter generico-aninhado: "
        + ("available" if nested else "unavailable on this checkout")
    )
    _emit("\n".join(lines), stdout)
    return _OK


_DISPATCH = {
    "parse": _cmd_parse,
    "dump-styled": _cmd_dump_styled,
    "dump-tree": _cmd_dump_tree,
    "segment": _cmd_segment,
    "validate": _cmd_validate,
    "list-profiles": _cmd_list_profiles,
    "decisions-report": _cmd_decisions_report,
    "capabilities": _cmd_capabilities,
}


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def _add_documents(sub: argparse.ArgumentParser, *, required: bool = True) -> None:
    sub.add_argument(
        "paths",
        nargs="+" if required else "*",
        type=Path,
        help="source document(s): .docx, .html, .htm or .txt",
    )


def _add_profile(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--profile", default=None, help="force a profile (see list-profiles)")


def _add_schema(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--schema",
        default="both",
        choices=SCHEMA_SELECTORS,
        help="which schema(s) to validate against (default: both)",
    )
    sub.add_argument(
        "--generation",
        default=SHIPPED,
        choices=GENERATIONS,
        help=f"schema generation (default: {SHIPPED})",
    )


def _add_referee(sub: argparse.ArgumentParser) -> None:
    """The referee flags, shared by `parse` and `decisions-report`.

    ``--referee-model`` and ``--referee-base-url`` fall back to
    ``LEXML_REFEREE_MODEL`` / ``LEXML_REFEREE_BASE_URL``, so `.env.example`'s
    provider presets are configuration rather than documentation. Precedence is
    flag > environment > `api.DEFAULT_*`, matching how the API key already
    resolves. Reading the environment *here*, as an argparse default, is what
    lets ``--help`` show the value that will actually be used.
    """
    sub.add_argument(
        "--referee",
        default="none",
        choices=REFEREE_MODES,
        help="adjudicator for low-confidence decisions (default: none — no network)",
    )
    sub.add_argument(
        "--referee-model",
        default=os.environ.get("LEXML_REFEREE_MODEL"),
        help="model id or GGUF path (default: $LEXML_REFEREE_MODEL)",
    )
    sub.add_argument(
        "--referee-base-url",
        default=os.environ.get("LEXML_REFEREE_BASE_URL"),
        help=(
            "OpenAI-compatible endpoint root for --referee=api "
            f"(default: $LEXML_REFEREE_BASE_URL, then {DEFAULT_BASE_URL})"
        ),
    )
    sub.add_argument(
        "--referee-cache", type=Path, default=None, help="referee disk cache directory"
    )


def _add_quiet(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "-q", "--quiet", action="store_true", help="suppress per-document headers"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lexml-nonstat",
        description="Convert Brazilian non-statutory legal documents to LexML XML.",
    )
    parser.add_argument(
        "--version", action="version", version=_version_string()
    )
    subs = parser.add_subparsers(dest="command", metavar="command")

    p = subs.add_parser("parse", help="render a document to LexML XML")
    _add_documents(p)
    _add_profile(p)
    _add_schema(p)
    _add_referee(p)
    _add_quiet(p)
    p.add_argument(
        "--emitter",
        default="auto",
        choices=CHOOSABLE_EMITTERS,
        help="rendering; auto (default) follows the route",
    )
    p.add_argument(
        "-o", "--out", type=Path, default=None,
        help="write every document of the bundle into this directory",
    )
    p.add_argument(
        "--format", default="xml", choices=("xml", "json"),
        help="xml (default) writes the primary document; json reports the run",
    )
    p.add_argument(
        "--summary", action="store_true",
        help="print a text summary instead of the XML",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="exit non-zero if anything warned (default: warn and continue)",
    )

    p = subs.add_parser("dump-styled", help="what ingestion saw")
    _add_documents(p)
    _add_profile(p)
    _add_quiet(p)
    p.add_argument("--format", default="json", choices=("json", "text"))

    p = subs.add_parser("dump-tree", help="the inferred hierarchy")
    _add_documents(p)
    _add_profile(p)
    _add_quiet(p)
    p.add_argument("--format", default="text", choices=("text", "json"))
    p.add_argument(
        "--why", action="store_true",
        help="show evidence signals, body nodes and rejected candidates",
    )

    p = subs.add_parser("segment", help="citable segments, CSV or JSONL")
    _add_documents(p)
    _add_profile(p)
    _add_quiet(p)
    p.add_argument("--format", default="csv", choices=("csv", "jsonl"))
    p.add_argument(
        "--emitter", default="auto", choices=CHOOSABLE_EMITTERS,
        help="which emitter's addresses to cite (default: auto — flat)",
    )

    p = subs.add_parser("validate", help="validate XML against the LexML schemas")
    p.add_argument("paths", nargs="+", type=Path, help="XML file(s)")
    _add_schema(p)
    _add_quiet(p)

    p = subs.add_parser("list-profiles", help="the registered document profiles")
    p.add_argument("--format", default="text", choices=("text", "json"))

    p = subs.add_parser("decisions-report", help="§7.4's rule-vs-referee summary")
    _add_documents(p)
    _add_profile(p)
    _add_referee(p)
    _add_quiet(p)
    p.add_argument("--format", default="text", choices=("text",))

    p = subs.add_parser(
        "capabilities", help="what the schemas present permit (A-R.9)"
    )
    p.add_argument("--format", default="text", choices=("text", "json"))

    return parser


def _version_string() -> str:
    from . import __version__

    return f"lexml-nonstat {__version__}"


def main(argv: list[str] | None = None) -> int:
    """Run one CLI invocation. Returns the process exit code, never raises.

    The blanket ``except`` is not defensive habit: Cycle 8's exit criterion is
    that *no* input produces a traceback, and a bug in a rendering path is
    exactly the case a typed ``except`` would miss. The traceback is not
    discarded — ``LEXML_TRACEBACK=1`` prints it, so a developer keeps what a
    user should never see.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_usage(sys.stderr)
        print("error: a command is required", file=sys.stderr)
        print(f"       choose one of: {', '.join(COMMANDS)}", file=sys.stderr)
        return _MISUSE

    streams = (sys.stdout, sys.stderr)
    try:
        return _DISPATCH[args.command](args, streams)
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("interrupted", file=sys.stderr)
        return _FAILED
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        if os.environ.get("LEXML_TRACEBACK"):
            traceback.print_exc()
        else:
            print(
                "       (set LEXML_TRACEBACK=1 for the traceback)", file=sys.stderr
            )
        return _FAILED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
