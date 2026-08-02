#!/usr/bin/env python3
"""Regenerate the `StyledDoc` goldens.

    python3 scripts/regen_goldens.py                 # all 15 samples
    python3 scripts/regen_goldens.py parecer_93_2018_decor_cgu_agu

Plan §9.4: goldens regenerate only via an explicit command, never as a side
effect of running tests, so every golden diff is a reviewed behaviour change.

Prints what changed. A silent regeneration that quietly rewrites 15 files is
exactly the failure mode the policy exists to prevent — if this reports
"3 changed", those three belong in the commit message.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lexml_nonstat.ingest import read_docx  # noqa: E402  (after sys.path setup)

SAMPLES_DIR = REPO_ROOT / "samples"
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "styled"


def golden_path(sample: Path) -> Path:
    return GOLDEN_DIR / f"{sample.stem}.json"


def regenerate(sample: Path) -> str:
    """Write one golden. Returns 'new', 'changed' or 'unchanged'."""
    target = golden_path(sample)
    content = read_docx(sample).to_json()

    if not target.exists():
        state = "new"
    elif target.read_text(encoding="utf-8") == content:
        state = "unchanged"
    else:
        state = "changed"

    if state != "unchanged":
        target.write_text(content, encoding="utf-8")
    return state


def main(argv: list[str]) -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    if argv:
        samples = []
        for name in argv:
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

    tally = {"new": 0, "changed": 0, "unchanged": 0}
    for sample in samples:
        state = regenerate(sample)
        tally[state] += 1
        marker = {"new": "+", "changed": "~", "unchanged": " "}[state]
        print(f" {marker} {sample.stem}")

    print(
        f"\n{len(samples)} sample(s): "
        f"{tally['new']} new, {tally['changed']} changed, "
        f"{tally['unchanged']} unchanged"
    )
    if tally["new"] or tally["changed"]:
        print("Review the diff before committing — a golden change is a "
              "behaviour change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
