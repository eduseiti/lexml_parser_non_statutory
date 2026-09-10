#!/usr/bin/env python3
"""Record the linker's answers as committed fixtures.

    python3 scripts/record_linker_fixtures.py            # record all 15 samples
    python3 scripts/record_linker_fixtures.py --check    # verify, write nothing
    python3 scripts/record_linker_fixtures.py par_cosit_26_20000629
    python3 scripts/record_linker_fixtures.py --stats    # per-norm-type rates

Amendment **A-L.6**, and the same rule §9.3 gives the referee: refreshing
fixtures is an **explicit documented command, never automatic**. A linker
upgrade must show up as a reviewed diff in this repository, not as output that
silently changed under a passing test.

This is what the linked goldens are built from, and it is why they compare on a
checkout with **no binary present**: the recorded answers carry the URNs, so
`--linker=fixtures` resolves references without spawning anything. Only
*recording* needs `linkertool`.

``--check`` is the cycle's "binary present" exit criterion, executable: it
re-asks the live linker every question the committed fixtures answer and fails
on any difference, which is what proves the recorded answers are live answers
rather than a snapshot that drifted.

The fixture key is ``(context_urn, paragraph text)``, and the context URN is
always :data:`~lexml_nonstat.refs.DEFAULT_CONTEXT_URN` (A-L.9) — a document's
own URN carries a non-federal authority, which makes the linker resolve
**nothing**, silently.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lexml_nonstat.ingest import read_docx  # noqa: E402  (after sys.path setup)
from lexml_nonstat.model import build_model  # noqa: E402
from lexml_nonstat.model.nodes import Para  # noqa: E402
from lexml_nonstat.refs import (  # noqa: E402
    DEFAULT_CONTEXT_URN,
    LinkerCache,
    LinkertoolLinker,
    cache_key,
    probe_linker,
)
from lexml_nonstat.render.anexo import render_anexo  # noqa: E402
from lexml_nonstat.render.generico import render_generico  # noqa: E402

SAMPLES_DIR = REPO_ROOT / "samples"
FIXTURES_DIR = REPO_ROOT / "tests" / "linker_fixtures"


def samples() -> list[Path]:
    return sorted(SAMPLES_DIR.glob("*.docx"))


class _Recorder:
    """A linker that records every question, and every answer, in order.

    Wraps the real backend rather than subclassing it: the point is to observe
    exactly the questions the *emitters* ask, so that the recorded set is
    neither larger nor smaller than what a fixture-backed render will look up.
    A set built by a separate traversal would drift from the renderer's the
    moment either changed.
    """

    name = "recorder"
    enabled = True

    def __init__(self, inner) -> None:
        self.inner = inner
        self.asked: list[str] = []
        self.answers: dict[str, tuple] = {}

    def find_refs(self, text: str, context_urn: str = DEFAULT_CONTEXT_URN):
        references = self.inner.find_refs(text, context_urn)
        if text not in self.answers:
            self.asked.append(text)
            self.answers[text] = references
        return references


def _ask_every_paragraph(sample: Path, linker) -> None:
    """Drive the real emitters over ``sample`` so ``linker`` sees their questions.

    Both the primary document and its annexes: an annex is a standalone sibling
    document (plan §2.9) and its paragraphs cite statutes too.
    """
    model = build_model(read_docx(sample), filename=sample.name)
    render_generico(model, linker=linker)
    for annex in model.annexes:
        render_anexo(model, annex, linker=linker)


def record(sample: Path, cache: LinkerCache, *, check: bool) -> dict[str, int]:
    """Record (or verify) one sample's fixtures. Returns a small tally."""
    live = LinkertoolLinker()
    recorder = _Recorder(live)
    try:
        _ask_every_paragraph(sample, recorder)
    finally:
        live.close()

    tally = Counter()
    for text in recorder.asked:
        references = recorder.answers[text]
        key = cache_key(DEFAULT_CONTEXT_URN, text)
        tally["asked"] += 1
        tally["refs"] += len(references)

        if check:
            recorded = cache.get(key)
            if recorded is None:
                tally["missing"] += 1
                print(f"  MISSING fixture for: {text[:70]!r}")
            elif tuple(recorded) != tuple(references):
                tally["differs"] += 1
                print(f"  DIFFERS: {text[:70]!r}")
                print(f"    recorded: {[r.urn for r in recorded]}")
                print(f"    live    : {[r.urn for r in references]}")
            else:
                tally["match"] += 1
            continue

        before = cache.path_for(key).read_bytes() if cache.path_for(key).is_file() else None
        cache.put(
            key,
            references,
            meta={"text": text, "sample": sample.name, "context": DEFAULT_CONTEXT_URN},
        )
        after = cache.path_for(key).read_bytes()
        if before is None:
            tally["new"] += 1
        elif before != after:
            tally["changed"] += 1
        else:
            tally["unchanged"] += 1
    return tally


def _stats(cache: LinkerCache) -> None:
    """The per-norm-type resolution rate A-L.8 requires the report to state."""
    import json

    by_type: Counter = Counter()
    urns: set[str] = set()
    paragraphs = linked = 0
    for path in sorted(cache.directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        references = data.get("references", [])
        paragraphs += 1
        if references:
            linked += 1
        for reference in references:
            urn = reference.get("urn", "")
            urns.add(urn)
            parts = urn.split(":")
            by_type[parts[4] if len(parts) > 4 else "?"] += 1

    print(f"paragraphs recorded : {paragraphs}")
    print(f"  with references   : {linked}")
    print(f"  distinct URNs     : {len(urns)}")
    print("references by norm type:")
    for norm_type, count in by_type.most_common():
        print(f"  {norm_type:24s} {count}")
    print(
        "\nnot recognised by the grammar (A-L.8): portaria, instrução "
        "normativa,\nparecer, ato declaratório, solução de consulta; the "
        "súmula rule is commented out."
    )


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stats = "--stats" in argv
    wanted = [a for a in argv if not a.startswith("--")]

    cache = LinkerCache(FIXTURES_DIR, read_only=check)

    if stats:
        _stats(cache)
        return 0

    capabilities = probe_linker()
    if not capabilities.available:
        print(f"error: {capabilities.diagnostic}", file=sys.stderr)
        print(
            "\nRecording fixtures needs the linkertool binary. The suite does "
            "not:\nthe committed fixtures already carry the answers.",
            file=sys.stderr,
        )
        return 2

    chosen = [s for s in samples() if not wanted or any(w in s.stem for w in wanted)]
    if not chosen:
        print(f"error: no sample matched {wanted}", file=sys.stderr)
        return 2

    print(f"linker: {capabilities.path}")
    print(f"context: {DEFAULT_CONTEXT_URN}\n")

    total = Counter()
    for sample in chosen:
        tally = record(sample, cache, check=check)
        total.update(tally)
        if check:
            state = (
                "OK"
                if not tally["missing"] and not tally["differs"]
                else f"{tally['missing']} missing, {tally['differs']} differ"
            )
        else:
            state = (
                f"{tally['new']} new, {tally['changed']} changed, "
                f"{tally['unchanged']} unchanged"
            )
        print(f"{sample.stem:58s} {tally['asked']:4d} asked  {state}")

    print(
        f"\n{total['asked']} paragraphs asked, {total['refs']} references resolved"
    )
    if check:
        bad = total["missing"] + total["differs"]
        if bad:
            print(
                f"\n{bad} fixture(s) do not reproduce. The committed answers "
                "are not\nthe linker's current answers — review the difference, "
                "then re-record\ndeliberately.",
                file=sys.stderr,
            )
            return 1
        print(f"all {total['match']} committed fixtures reproduce exactly.")
    else:
        print(
            f"{total['new']} new, {total['changed']} changed, "
            f"{total['unchanged']} unchanged"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
