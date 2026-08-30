# Recorded referee fixtures

A read-only [`RefereeCache`](../../src/lexml_nonstat/referee/cache.py). Plan
§9.3 makes the cache layer *the seam* through which the referee is tested:
point a `CachedAPIReferee` at this directory and every question the corpus asks
is already answered, so the referee's whole surface — adjudication, override
policy, telemetry, determinism — is exercised with **zero network calls**.

```python
referee = CachedAPIReferee(cache=RefereeCache(FIXTURES, read_only=True))
```

`read_only=True` matters. Without it, a question with no fixture would silently
become a live call on the next run, which is precisely what §9.3 forbids.

## What is here

Exactly the four decisions the 15-sample corpus flags — every paragraph whose
quotation verdict the deterministic rules reached with confidence below
`FLAG_THRESHOLD` (0.60):

| Key | Sample | Locator | Rule verdict (conf.) | Fixture verdict |
|---|---|---|---|---|
| `5d21d46f…` | `par_cosit_26_20000629` | `p#46` | quoted (0.55) | quoted |
| `1a2ea8e5…` | `par_cosit_26_20000629` | `p#47` | quoted (0.50) | quoted |
| `6d17981b…` | `par_cosit_26_20000629` | `p#53` | quoted (0.50) | quoted |
| `8ac716a4…` | `parecer_93_2018_decor_cgu_agu` | `p#36` | quoted (0.55) | quoted |

> **Re-keyed 2026-08-30.** These files were originally written under
> `model="deepseek-chat"` (keys `2b9c8bda…`, `c476d7f5…`, `a80195c5…`,
> `3f881540…`). When `api.DEFAULT_MODEL` was refreshed to `deepseek-v4-flash`,
> the key — which covers the model — moved with it, every lookup missed, and
> seven tests failed by falling through to a transport that asserts it is never
> called. The four files were renamed to the keys the new model computes and
> their `meta.model` updated; **verdicts, confidences and rationales are
> untouched**, and the `origin` line still records that they are hand-authored.
> The new keys were *derived* by replaying the corpus, not typed: the old keys
> reproduce exactly under `deepseek-chat`, which is what proves the mapping.

Three of the four are plan §2.6's residual case: `par_cosit_26` "resists
indentation entirely", so its quoted statutes carry no band and are convicted
by a citation antecedent or by excerpt-run extension alone. The fourth is the
one paragraph in `parecer_93`'s 415 that its declared quote band does not
reach.

**Every fixture agrees with the rule.** That is the finding, not a convenience:
Cycle 4's guard already convicts all thirty quoted articles in the corpus
correctly, so the referee's job on these documents is to confirm a verdict that
is right but unsure — not to rescue one that is wrong. A future document where
the rules *are* wrong is what the override path exists for, and
`tests/unit/test_referee_protocol.py` exercises it directly.

## Provenance — these are hand-authored

They were **not** recorded from a live provider. No API key was available when
Cycle 4b was built, and the cycle's decision (taken with the user) was to author
them by hand rather than make an outbound call, because what the test needs to
prove is the *plumbing*: cache hit ⇒ zero calls, verdict ⇒ adjudication ⇒
`DecisionRecord` ⇒ report. The `meta.origin` field of every file says so.

A wrong fixture cannot pass silently. Each is consumed by a test that asserts
the referee **agreed**, so a fixture saying `own` would surface as a spurious
override and a changed route, not as a green run.

## Refreshing them from a live provider

Explicit and manual, never automatic (§9.3: "a provider change shows up as a
reviewed diff"):

```bash
export LEXML_REFEREE_API_KEY=…
python3 -m lexml_nonstat.routing --referee=api \
        --referee-model=deepseek-v4-flash \
        --referee-cache=tests/referee_fixtures \
        --decisions-report samples/*.docx
git diff tests/referee_fixtures/    # review before committing
```

The cache key covers the **model**, the decision kind, the excerpt and its
context, so a different model writes new files rather than overwriting these —
switching providers is additive, and the diff shows exactly which answers moved.

Note that a live refresh writes `meta` without the `origin` line above; keep it
if the file is still hand-authored, drop it once it is genuinely recorded.
