#!/usr/bin/env python3
"""Record (or verify) the referee's answers over the 233-document corpus.

    python3 scripts/record_corpus_referee_fixtures.py --check    # verify, write nothing
    python3 scripts/record_corpus_referee_fixtures.py            # record live
    python3 scripts/record_corpus_referee_fixtures.py --stats    # what the set buys

Cycle 6 deliverable 1, and the same rule §9.3 gives the linker: refreshing
fixtures is an **explicit documented command, never automatic**. A model change
or a prompt edit must show up as a reviewed diff in this repository, not as
output that silently changed under a passing test.

``--check`` is the interesting mode, and it is the one that runs offline. It
replays the whole corpus against the committed answers with the transport wired
to raise, then reports the hit rate, the miss list and the override tally. That
is what catches the A-H.2 failure mode — a prompt edit moves every cache key, so
the questions asked stop matching the answers recorded — **before** a test run
turns mysteriously red.

Recording (no ``--check``) needs ``LEXML_REFEREE_API_KEY`` and makes real calls;
it is the only mode that does. Both modes need the corpus, which is research
data living outside this repository.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lexml_nonstat.ingest import read_docx  # noqa: E402  (after sys.path setup)
from lexml_nonstat.model import build_model  # noqa: E402
from lexml_nonstat.referee import (  # noqa: E402
    CachedAPIReferee,
    NullReferee,
    RefereeCache,
    cache_key,
)
from lexml_nonstat.referee.api import DEFAULT_MODEL  # noqa: E402
from lexml_nonstat.telemetry import DecisionLog, DecisionsReport  # noqa: E402

#: The committed answers. 625 entries at the time of recording.
FIXTURES = REPO_ROOT / "tests" / "corpus_referee_fixtures"

#: The 233-document corpus. Outside the repository by design — research data,
#: not a fixture — so every mode here reports its absence rather than failing
#: obscurely.
CORPUS = REPO_ROOT.parent / "br-taxqa-r_v2.0" / "original" / "nao_articulados"


def _explodes(*args, **kwargs):
    """A transport that must never be called."""
    raise AssertionError(
        "the transport was called; --check must make no network call"
    )


def _documents(limit: int | None = None):
    paths = sorted(CORPUS.glob("*.docx"))
    if limit is not None:
        paths = paths[:limit]
    return [(path, read_docx(path)) for path in paths]


def _replay(docs, referee) -> tuple[DecisionLog, dict[str, tuple]]:
    """Build every model with ``referee``, returning the log and the shapes.

    The shape tuple is ``(flat, flat_cause, sections)`` per document — enough to
    tell whether two runs agreed about every document, which is what invariant
    #4 asks of a cached referee.
    """
    log = DecisionLog()
    shapes: dict[str, tuple] = {}
    for path, doc in docs:
        model = build_model(doc, filename=path.name, log=log, referee=referee)
        body = model.body
        signals = getattr(body, "signals", None)
        shapes[path.stem] = (
            bool(getattr(body, "flat", True)),
            str(getattr(signals, "flat_cause", "")),
            len(getattr(body, "sections", ()) or ()),
        )
    return log, shapes


def _asked(referee_cls, cache, **kwargs):
    """A referee that records every question and whether it was already answered."""
    questions: list[dict] = []

    class Probe(referee_cls):  # type: ignore[misc, valid-type]
        def ask(self, kind, excerpt, ctx="", next_ctx=""):
            key = cache_key(self.model, kind, excerpt, ctx, next_ctx)
            questions.append(
                {
                    "kind": kind,
                    "key": key,
                    "hit": cache.path_for(key).is_file(),
                    "excerpt": excerpt[:120],
                }
            )
            return super().ask(kind, excerpt, ctx, next_ctx)

    return Probe(cache=cache, **kwargs), questions


def _overrides(log: DecisionLog):
    pairs: collections.Counter = collections.Counter()
    docs: set[str] = set()
    for record in log:
        if record.overridden:
            pairs[
                (record.kind, str(record.rule_verdict), str(record.referee_verdict))
            ] += 1
            docs.add(record.doc)
    return pairs, docs


def cmd_check(args) -> int:
    """Replay the corpus against the committed answers. No network, no writes."""
    docs = _documents(args.limit)
    print(f"corpus:   {len(docs)} documents")
    print(f"fixtures: {len(list(FIXTURES.glob('*.json')))} entries in {FIXTURES}")

    before = {p.name for p in FIXTURES.glob("*.json")}

    cache = RefereeCache(FIXTURES, read_only=True)
    referee, questions = _asked(
        CachedAPIReferee, cache, api_key=None, transport=_explodes
    )

    started = time.time()
    log, shapes = _replay(docs, referee)
    elapsed = time.time() - started

    report = DecisionsReport.from_log(log)
    misses = [q for q in questions if not q["hit"]]

    print(f"\nreplayed in {elapsed:.2f}s  ({1000 * elapsed / len(docs):.1f} ms/doc)")
    print(f"questions asked:  {len(questions)}")
    print(f"cache hits:       {cache.hits}  ({report.cache_hit_pct}%)")
    print(f"network calls:    {referee.calls}")

    # A miss is only acceptable when the recorded answer was an abstention,
    # which `api.py` deliberately never caches. Any other miss means the keys
    # have moved — a prompt edit, a model change — and the set is stale.
    unexplained = []
    abstained = {(r.doc, r.locator) for r in log if r.abstained}
    for record in log:
        if record.abstained and record.rule_verdict != record.final_verdict:
            unexplained.append(record)

    print(f"misses:           {len(misses)}")
    for miss in misses:
        print(f"  {miss['kind']:20s} {miss['excerpt']!r}")
    print(f"abstentions:      {len(abstained)} (a miss is an abstention by design)")

    pairs, override_docs = _overrides(log)
    print(f"\noverrides: {sum(pairs.values())} across {len(override_docs)} documents")
    for (kind, rule, ref), count in pairs.most_common():
        print(f"  {kind:20s} {rule:14s} -> {ref:14s} {count}")

    flat = sum(1 for shape in shapes.values() if shape[0])
    rules_log, rules_shapes = _replay(docs, NullReferee())
    flat_rules = sum(1 for shape in rules_shapes.values() if shape[0])
    gained = sorted(s for s in shapes if rules_shapes[s][0] and not shapes[s][0])
    print(f"\nflat: rules-only {flat_rules} -> refereed {flat}")
    for stem in gained:
        print(f"  gained structure: {stem}")

    after = {p.name for p in FIXTURES.glob("*.json")}
    problems = []
    if referee.calls:
        problems.append(f"{referee.calls} network call(s) were made")
    if after != before:
        problems.append(f"the read-only cache changed on disk: {after ^ before}")
    if unexplained:
        problems.append(f"{len(unexplained)} abstention(s) changed an outcome")
    if report.check() is not None:
        problems.append(f"decision counts do not reconcile: {report.check()}")

    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nok — the committed answers still answer every question that matters.")
    return 0


def cmd_record(args) -> int:
    """Re-record every answer from a live provider. Makes real calls."""
    api_key = os.environ.get("LEXML_REFEREE_API_KEY")
    if not api_key:
        print(
            "error: LEXML_REFEREE_API_KEY is not set; recording makes live calls",
            file=sys.stderr,
        )
        return 2

    docs = _documents(args.limit)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    cache = RefereeCache(FIXTURES)  # read-write: this is the recording path
    referee = CachedAPIReferee(cache=cache, api_key=api_key, model=args.model)

    print(f"recording {len(docs)} documents against {args.model} …")
    started = time.time()
    log, _shapes = _replay(docs, referee)
    elapsed = time.time() - started

    report = DecisionsReport.from_log(log)
    print(f"\nrecorded in {elapsed:.1f}s")
    print(f"consulted:     {report.consulted}")
    print(f"cache hits:    {report.cache_hits}  ({report.cache_hit_pct}%)")
    print(f"network calls: {referee.calls}")
    print(f"entries now:   {len(list(FIXTURES.glob('*.json')))}")
    print("\nreview the diff before committing:  git diff tests/corpus_referee_fixtures/")
    return 0


def cmd_stats(args) -> int:
    """What the committed set contains, without touching the corpus."""
    import json

    kinds: collections.Counter = collections.Counter()
    verdicts: collections.Counter = collections.Counter()
    models: collections.Counter = collections.Counter()
    total = 0

    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("meta") or {}
        kinds[meta.get("kind")] += 1
        models[meta.get("model")] += 1
        verdicts[(data.get("verdict") or {}).get("verdict")] += 1
        total += path.stat().st_size

    print(f"entries: {sum(kinds.values())}  ({total / 1024:.0f} KB)")
    print(f"models:  {dict(models)}")
    if set(models) != {DEFAULT_MODEL}:
        print(
            f"  WARNING: entries not recorded under {DEFAULT_MODEL!r} will never "
            "be found — the cache key covers the model"
        )
    print("kinds:")
    for kind, count in kinds.most_common():
        print(f"  {kind:20s} {count}")
    print("verdicts:")
    for verdict, count in verdicts.most_common():
        print(f"  {str(verdict):20s} {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="replay against the committed answers; write nothing, call nothing",
    )
    parser.add_argument(
        "--stats", action="store_true", help="summarise the committed set and exit"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help="provider model id (recording only)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="process at most this many documents"
    )
    args = parser.parse_args(argv)

    if args.stats:
        return cmd_stats(args)

    if not CORPUS.is_dir():
        print(
            f"error: the 233-document corpus is not present at {CORPUS}\n"
            "       (research data, not part of this repository)",
            file=sys.stderr,
        )
        return 2

    return cmd_check(args) if args.check else cmd_record(args)


if __name__ == "__main__":
    raise SystemExit(main())
