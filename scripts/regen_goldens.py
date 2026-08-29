#!/usr/bin/env python3
"""Regenerate the goldens.

    python3 scripts/regen_goldens.py                 # all kinds, all 15 samples
    python3 scripts/regen_goldens.py parecer_93_2018_decor_cgu_agu
    python3 scripts/regen_goldens.py --kind=metadata

Plan §9.4: goldens regenerate only via an explicit command, never as a side
effect of running tests, so every golden diff is a reviewed behaviour change.

Prints what changed. A silent regeneration that quietly rewrites 15 files is
exactly the failure mode the policy exists to prevent — if this reports
"3 changed", those three belong in the commit message.

Seven kinds so far: ``styled`` (Cycle 1's `StyledDoc`), ``metadata``
(Cycle 2's `Metadata`), ``segment`` (Cycle 3's `Segmentation`),
``hierarchy`` (Cycle 4's `HierarchyDoc`), ``routing`` (Cycle 4b's
`StatutoryViability`), ``generico`` (Cycle 5's flat XML) and
``generico-aninhado`` (Cycle 5b's nested XML). Later cycles add theirs to
``KINDS`` rather than writing another script.

The nested goldens are written **unconditionally**, on every checkout. They are
the emitter's output, which does not depend on which schemas are present; it is
only *validating* them that needs `lexml-proposed/`, and that is the golden
test's business, not this script's (spec decision R-2).

A renderer returns ``{suffix: content}`` rather than a bare string, because one
sample can produce more than one file: an annex is a **standalone sibling
document** (plan §2.9), written as ``<stem>.anexo1.xml`` — the same file naming
the reference parser uses for `lei_5070_19660707.anexo1.xml`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lexml_nonstat.hierarchy import infer_hierarchy  # noqa: E402
from lexml_nonstat.ingest import read_docx  # noqa: E402  (after sys.path setup)
from lexml_nonstat.model import extract_metadata  # noqa: E402
from lexml_nonstat.render import (  # noqa: E402
    render_generico_aninhado_from_docx,
    render_generico_from_docx,
)
from lexml_nonstat.routing import assess_viability  # noqa: E402
from lexml_nonstat.segment import segment_document  # noqa: E402

SAMPLES_DIR = REPO_ROOT / "samples"
GOLDEN_ROOT = REPO_ROOT / "tests" / "golden"
GOLDEN_DIR = GOLDEN_ROOT / "styled"


def _styled_json(sample: Path) -> dict[str, str]:
    return {"": read_docx(sample).to_json()}


def _metadata_json(sample: Path) -> dict[str, str]:
    # `filename` is passed exactly as production does, so the filename-date
    # fallback is exercised by the golden rather than only by a unit test.
    return {"": extract_metadata(read_docx(sample), filename=sample.name).to_json()}


def _segment_json(sample: Path) -> dict[str, str]:
    doc = read_docx(sample)
    metadata = extract_metadata(doc, filename=sample.name)
    return {"": segment_document(doc, metadata=metadata).to_json()}


def _hierarchy_json(sample: Path) -> dict[str, str]:
    doc = read_docx(sample)
    metadata = extract_metadata(doc, filename=sample.name)
    segmentation = segment_document(doc, metadata=metadata)
    return {
        "": infer_hierarchy(
            doc, metadata=metadata, segmentation=segmentation
        ).to_json()
    }


def _routing_json(sample: Path) -> dict[str, str]:
    # `referee=None` on purpose: goldens are the deterministic rule verdicts,
    # so a golden diff can never be an LLM having a different day (§9.3).
    doc = read_docx(sample)
    metadata = extract_metadata(doc, filename=sample.name)
    segmentation = segment_document(doc, metadata=metadata)
    hierarchy = infer_hierarchy(doc, metadata=metadata, segmentation=segmentation)
    return {
        "": assess_viability(
            doc, metadata=metadata, segmentation=segmentation, hierarchy=hierarchy
        ).to_json()
    }


def _generico_xml(sample: Path) -> dict[str, str]:
    # The whole pipeline, exactly as production runs it. `port_mf_277` routes
    # to `norma`, and is rendered here too: the flat emitter is the documented
    # validate-then-fallback rendering (plan §3), and it is the corpus's only
    # exercise of `Anexos`/`ReferenciaAnexo`.
    bundle = render_generico_from_docx(sample, filename=sample.name)
    out = {"": bundle.to_xml_string(bundle.primary)}
    for ordinal, annex in enumerate(bundle.annexes, start=1):
        out[f".anexo{ordinal}"] = bundle.to_xml_string(annex)
    return out


def _generico_aninhado_xml(sample: Path) -> dict[str, str]:
    # The same 16 documents as `generico`, written nested (spec decision R-4),
    # so cross-emitter equivalence is checkable file-for-file over the bundle.
    bundle = render_generico_aninhado_from_docx(sample, filename=sample.name)
    out = {"": bundle.to_xml_string(bundle.primary)}
    for ordinal, annex in enumerate(bundle.annexes, start=1):
        out[f".anexo{ordinal}"] = bundle.to_xml_string(annex)
    return out


#: kind → (output directory, renderer, file extension)
#:
#: A renderer maps a file-stem suffix to that file's content; ``""`` is the
#: sample's own golden and ``".anexo1"`` its first annex document.
KINDS: dict[str, tuple[Path, object, str]] = {
    "styled": (GOLDEN_ROOT / "styled", _styled_json, ".json"),
    "metadata": (GOLDEN_ROOT / "metadata", _metadata_json, ".json"),
    "segment": (GOLDEN_ROOT / "segment", _segment_json, ".json"),
    "hierarchy": (GOLDEN_ROOT / "hierarchy", _hierarchy_json, ".json"),
    "routing": (GOLDEN_ROOT / "routing", _routing_json, ".json"),
    "generico": (GOLDEN_ROOT / "generico", _generico_xml, ".xml"),
    "generico-aninhado": (
        GOLDEN_ROOT / "generico_aninhado",
        _generico_aninhado_xml,
        ".xml",
    ),
}


def golden_path(sample: Path, kind: str = "styled", suffix: str = "") -> Path:
    directory, _, extension = KINDS[kind]
    return directory / f"{sample.stem}{suffix}{extension}"


def regenerate(sample: Path, kind: str = "styled") -> str:
    """Write one sample's goldens for ``kind``.

    Returns the strongest state across the files written: 'new' beats 'changed'
    beats 'unchanged', so a sample that gains an annex file reports 'new'.
    """
    parts = KINDS[kind][1](sample)
    states = []
    for suffix, content in parts.items():
        target = golden_path(sample, kind, suffix)
        if not target.exists():
            state = "new"
        elif target.read_text(encoding="utf-8") == content:
            state = "unchanged"
        else:
            state = "changed"
        if state != "unchanged":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        states.append(state)

    for state in ("new", "changed"):
        if state in states:
            return state
    return "unchanged"


def main(argv: list[str]) -> int:
    kinds = list(KINDS)
    names = []
    for arg in argv:
        if arg.startswith("--kind="):
            wanted = arg.split("=", 1)[1]
            if wanted not in KINDS:
                known = ", ".join(KINDS)
                print(f"error: unknown kind {wanted!r}; known: {known}", file=sys.stderr)
                return 1
            kinds = [wanted]
        elif arg.startswith("-"):
            print(f"error: unknown option: {arg}", file=sys.stderr)
            return 1
        else:
            names.append(arg)

    if names:
        samples = []
        for name in names:
            path = SAMPLES_DIR / name
            if path.suffix != ".docx":
                path = path.with_suffix(".docx")
            if not path.exists():
                print(f"error: no such sample: {path.name}", file=sys.stderr)
                return 1
            samples.append(path)
    else:
        samples = sorted(SAMPLES_DIR.glob("*.docx"))

    if not samples:
        print("error: no samples found", file=sys.stderr)
        return 1

    total = {"new": 0, "changed": 0, "unchanged": 0}
    for kind in kinds:
        KINDS[kind][0].mkdir(parents=True, exist_ok=True)
        print(f"[{kind}]")
        for sample in samples:
            state = regenerate(sample, kind)
            total[state] += 1
            marker = {"new": "+", "changed": "~", "unchanged": " "}[state]
            print(f" {marker} {sample.stem}")

    print(
        f"\n{len(samples)} sample(s) × {len(kinds)} kind(s): "
        f"{total['new']} new, {total['changed']} changed, "
        f"{total['unchanged']} unchanged"
    )
    if total["new"] or total["changed"]:
        print("Review the diff before committing — a golden change is a "
              "behaviour change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
