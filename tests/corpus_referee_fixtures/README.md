# Recorded referee fixtures — the 233-document corpus

A read-only [`RefereeCache`](../../src/lexml_nonstat/referee/cache.py) holding
**every answer the 233-document corpus run asked for**. Plan §9.3 makes the cache
layer *the seam* through which the referee is tested; this directory is that seam
at corpus scale.

```python
referee = CachedAPIReferee(
    cache=RefereeCache(CORPUS_FIXTURES, read_only=True),
    api_key=None,
    transport=explodes(),   # asserts nothing reaches the network
)
```

**This is a different directory from [`../referee_fixtures/`](../referee_fixtures/)
on purpose.** That one holds the 38 decisions the *15 samples* flag, seven of them
hand-authored, and it is consumed by six test modules that count and enumerate it.
A corpus-scale set merged into it would perturb all of them. The two never mix.

## What is here

**625 entries**, 247 KB, one JSON file per adjudicated question:

| Kind | Entries | Verdicts |
|---|---|---|
| `heading` | 376 | `nao` 301, `secao` 75 |
| `own_articulation` | 246 | `quoted` 196, `own` 50 |
| `quotation_boundary` | 3 | `boundary` 3 |

Every entry carries `meta.model = "deepseek-v4-flash"` — the current
`api.DEFAULT_MODEL`. The cache key covers the model, so if that default is ever
refreshed, **every key here moves** and the whole set must be re-recorded. That is
the A-H.2 failure mode, and it is why the recording script has a `--check`.

## What it buys, measured

Replaying all 233 documents against this directory, with the transport wired to
raise:

| Measure | Value |
|---|---|
| Questions asked | 694 |
| Cache hits | **684 (98.6%)** |
| Network calls | **0** |
| Overrides reproduced | **127 across 53 documents** (74 `nao`→`secao`, 50 `quoted`→`own`, 3 `continuation`→`boundary`) |
| Flatness, rules-only → refereed | **86 → 83** |
| Referee overhead, warm cache | **+0.2 ms/document** |

Two identical replays produce a byte-identical `DecisionsReport` and identical
per-document shapes — invariant #4, asserted rather than assumed by
`tests/unit/test_referee_economics.py`.

### The 10 non-hits are abstentions, and they change nothing

Ten questions miss, and every one is a question whose recorded answer was an
**abstention**. `api.py` deliberately never caches an abstention ("a timeout is a
fact about the network, not about the question"), so these are absent *by design*
rather than missing:

```
parecer_pgfn_pga_1888_2008    p#14   'I'
parecer_pgfncat_815_2010_…    p#24   'I'
sc_cosit_180_20230816         p#11   'RELATÓRIO'
sc_cosit_202_20230830         p#11   'RELATÓRIO'
sci_cosit_10_20140605         p#2    'Fl. 23 DF COSIT RFB'
sci_cosit_10_20140605         p#6    'CÓPIA'
sci_cosit_2_20140114          p#2    'Fl. 12 DF COSIT RFB'
sci_cosit_2_20140114          p#6    'CÓPIA'
sci_cosit_6_20150518          p#2    'Fl. 58 DF COSIT RFB'
sci_cosit_6_20150518          p#6    'CÓPIA'
```

Every one is `rule=nao → final=nao`: the rule verdict is retained and **no
outcome changes**. Pinned by
`test_the_misses_are_all_abstentions_that_change_nothing`, so a future change that
turns one of these into an outcome-changing miss fails rather than passing quietly.

## Provenance

**These are live answers.** Unlike the seven hand-authored entries in
`../referee_fixtures/`, every file here was written by a real DeepSeek
(`deepseek-v4-flash`, temperature 0) run over the 233-document corpus on
2026-09-13 — the measuring run recorded in plan §1.1. The rationales are the
model's own words, in Portuguese, not ours.

That run's cache survived only in a scratch directory that would have been
deleted with the job. Publishing it here is Cycle 6 deliverable 1, and it is what
makes a refereed corpus run reproducible offline and at zero cost.

## Refreshing them from a live provider

Explicit and manual, never automatic (§9.3: "a provider change shows up as a
reviewed diff"):

```bash
export LEXML_REFEREE_API_KEY=…
python3 scripts/record_corpus_referee_fixtures.py --check   # verify, write nothing
python3 scripts/record_corpus_referee_fixtures.py           # re-record
git diff tests/corpus_referee_fixtures/                     # review before committing
```

`--check` re-asks nothing; it replays the corpus against the committed answers and
reports the hit rate, the miss list and the override tally, so a prompt edit or a
model change that invalidates these keys is visible **before** a test run turns
mysteriously red.

Recording needs the 233-document corpus at
`../br-taxqa-r_v2.0/original/nao_articulados/`, which is research data and is not
part of this repository. Every test that needs it skips without it.
