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

Two kinds so far: ``styled`` (Cycle 1's `StyledDoc`) and ``metadata``
(Cycle 2's `Metadata`). Later cycles add theirs to ``KINDS`` rather than
writing another script.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lexml_nonstat.ingest import read_docx  # noqa: E402  (after sys.path setup)
from lexml_nonstat.model import extract_metadata  # noqa: E402

SAMPLES_DIR = REPO_ROOT / "samples"
GOLDEN_ROOT = REPO_ROOT / "tests" / "golden"
GOLDEN_DIR = GOLDEN_ROOT / "styled"


def _styled_json(sample: Path) -> str:
    return read_docx(sample).to_json()


def _metadata_json(sample: Path) -> str:
    # `filename` is passed exactly as production does, so the filename-date
    # fallback is exercised by the golden rather than only by a unit test.
    return extract_metadata(read_docx(sample), filename=sample.name).to_json()


#: kind → (output directory, renderer)
KINDS: dict[str, tuple[Path, object]] = {
    "styled": (GOLDEN_ROOT / "styled", _styled_json),
    "metadata": (GOLDEN_ROOT / "metadata", _metadata_json),
}


def golden_path(sample: Path, kind: str = "styled") -> Path:
    return KINDS[kind][0] / f"{sample.stem}.json"


def regenerate(sample: Path, kind: str = "styled") -> str:
    """Write one golden. Returns 'new', 'changed' or 'unchanged'."""
    target = golden_path(sample, kind)
    content = KINDS[kind][1](sample)

    if not target.exists():
        state = "new"
    elif target.read_text(encoding="utf-8") == content:
        state = "unchanged"
    else:
        state = "changed"

    if state != "unchanged":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return state


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
