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

Exactly the **thirty-eight** decisions the 15-sample corpus flags — every paragraph whose
quotation verdict the deterministic rules reached with confidence below
`FLAG_THRESHOLD` (0.60), plus (since amendment A-Q.3) every candidate quotation
boundary, which is flagged by construction:

| Key | Sample | Locator | Rule verdict (conf.) | Fixture verdict |
|---|---|---|---|---|
| `5d21d46f…` | `par_cosit_26_20000629` | `p#46` | quoted (0.55) | quoted |
| `1a2ea8e5…` | `par_cosit_26_20000629` | `p#47` | quoted (0.50) | quoted |
| `6d17981b…` | `par_cosit_26_20000629` | `p#53` | quoted (0.50) | quoted |
| `8ac716a4…` | `parecer_93_2018_decor_cgu_agu` | `p#36` | quoted (0.55) | quoted |
| `9eb516e8…` | `par_cosit_26_20000629` | `p#63` | continuation (0.55) | **boundary** |
| `d96f0ede…` | `par_cosit_26_20000629` | `p#69` | continuation (0.55) | **boundary** |
| `31a87dde…` | `par_cosit_26_20000629` | `p#76` | continuation (0.55) | **boundary** |

…plus, since amendment **A-H.1**, **31 `heading` decisions** — one per
prose-form header candidate. They are summarised rather than listed one by one,
because the interesting fact about them is the ratio:

| Sample | Candidates | `secao` | `nao` |
|---|---|---|---|
| `par_cosit_26_20000629` | 15 | `RELATÓRIO`, `FUNDAMENTOS LEGAIS`, `CONCLUSÃO`, `ORDEM DE INTIMAÇÃO` | 6× `Fl. n DF COSIT RFB`, the letterhead block (`COSIT`, `MINISTÉRIO DA FAZENDA`, `0 SECRETARIA DA RECEITA FEDERAL`, `COORDENAÇÃO-GERAL…`), `DOMICÍLIO FISCAL`, `COORDENADOR-GERAL DA COSIT` |
| `sumula_stj_125` | 10 | `VOTO VENCIDO EM PARTE` | 7× `DJ dd.mm.yyyy`, `RECURSO ESPECIAL N. 47.692-SP`, `ANEXO` |
| `sistema_…_CARNE_LEAO` | 4 | — | `NIT/PIS`, `CTPS`, `CBO`, `CPF` |
| `parecer_93_…` | 1 | — | `LEI NO 12.618, DE 2012` |
| `sumula_carf_42` | 1 | `ACÓRDÃOS PARADIGMAS` | — |
| **Total** | **31** | **6** | **25** |

> **Amendment A-H.1 (2026-08-31) added these thirty-one**, of a fourth kind:
> `heading`. They are the corpus's whole prose-form candidate surface — every
> unlabelled, unstyled, upper-case short paragraph inside `Segmentation.body`.
> The generator that proposes them is **deliberately over-inclusive**, because
> the referee can only ever *remove*: 31 proposed, 6 confirmed. The 25
> refusals are not waste — they are the mechanism. A folio stamp and a section
> header are typographically identical in `par_cosit_26`, and the refusals are
> what keep the former out of the tree.
>
> As with the boundary fixtures, a confirmation is recorded as an **override**:
> the rule verdict is `nao` at `PROSE_HEADER_RULE_CONFIDENCE` (0.55, below
> `FLAG_THRESHOLD`), so nothing becomes a section without a referee saying so.
> With `--referee=none` the generator is not even run, and all 135 goldens are
> byte-identical.
>
> **The vocabulary changed with them**: `("heading","prose")` → `("secao","nao")`
> (A-H.2). The old prompt asked a *typographic* question and, put live to the
> corpus, called `Fl. 9 DF COSIT RFB` a heading at confidence 0.95 and the
> signatory's name one at 0.80 — 15 of 17 wrong on `par_cosit_26` alone. The
> replacement asks the *structural* question and scores 31/31. A stale fixture
> answering `heading` or `prose` is now outside the vocabulary and abstains;
> `test_no_heading_fixture_answers_in_the_old_vocabulary` fails on one rather
> than letting a document quietly lose a section.
>
> **`cache_key` gained `next_ctx`**, appended **only when non-empty**, so the
> seven keys above did **not** move — asserted by
> `test_cache_key_unchanged_without_next_ctx` rather than assumed.

> **Amendment A-Q.3 (2026-08-30) added the last three**, of a new kind:
> `quotation_boundary`. They are the three points where `par_cosit_26`'s item
> `14.` — one flat run of 35 paragraphs — changes from one quoted law to the
> next: Lei 8.134, Lei 8.383, Lei 8.981. The run's *first* norm (Lei 7.713,
> block 45) is not a boundary, because it opens the quotation rather than
> changing norms, so it is never put to a referee.
>
> These three **override** their rule verdict, and that is the mechanism rather
> than a disagreement: the rule verdict for a candidate boundary is
> `continuation` — *stay flat* — because `BOUNDARY_RULE_CONFIDENCE` (0.55) sits
> deliberately below `FLAG_THRESHOLD`, so that nothing becomes a nested
> citation without a referee confirming it. Confirming is what an override is
> here. The referee still cannot invent a boundary: it is only ever asked about
> candidates the deterministic head detector already proposed.

> **Re-keyed again 2026-08-30 (A-Q.7).** `own_articulation`'s prompt context
> was widened from "the immediately preceding paragraph" to "the nearest
> preceding citation antecedent". Two keys moved — `p#47` (`1a2ea8e5…` →
> `04f000a5…`) and `p#53` (`6d17981b…` → `b53aaec5…`); `p#46` and `parecer_93`
> `p#36` were already being given their antecedent and did not move. Verdicts,
> confidences, rationales and `origin` are untouched, and the new keys were
> **derived by replaying the corpus**, never typed. This is the repair the
> investigation record's §2.3 asked for: the referee had overridden `p#47` and
> `p#53` wrongly, at confidence 0.95 and 0.70, because the paragraph naming the
> owning law sat two paragraphs back and was outside the one-paragraph window.

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

**Every `own_articulation` fixture agrees with the rule.** That is the finding,
not a convenience:
Cycle 4's guard already convicts all thirty quoted articles in the corpus
correctly, so the referee's job on these documents is to confirm a verdict that
is right but unsure — not to rescue one that is wrong. A future document where
the rules *are* wrong is what the override path exists for, and
`tests/unit/test_referee_protocol.py` exercises it directly.

## Provenance

**The 31 `heading` fixtures are different from the other seven, and their
`meta.origin` says so.** Their *verdicts and confidences were measured against a
live provider* — `deepseek-v4-flash` at temperature 0, during Cycle 8d's
feasibility probe (`docs/20260830_235814_…` §5) — and then transcribed by hand
into these files; only the `rationale` strings are written by us. That probe is
the evidence for A-H.2, so recording what the model actually said is the point:
a hand-invented verdict would have made the 31/31 measurement unfalsifiable.
They were not *written* by a live run, so `read_only=True` still holds and no
test makes a call.

**The seven older fixtures are hand-authored** and were **not** recorded from a
live provider. No API key was available when
Cycle 4b was built, and the cycle's decision (taken with the user) was to author
them by hand rather than make an outbound call, because what the test needs to
prove is the *plumbing*: cache hit ⇒ zero calls, verdict ⇒ adjudication ⇒
`DecisionRecord` ⇒ report. The `meta.origin` field of every file says so.

A wrong fixture cannot pass silently. Each `own_articulation` fixture is
consumed by a test that asserts the referee **agreed**, so one saying `own`
would surface as a spurious override and a changed route, not as a green run.
Each `quotation_boundary` fixture is consumed by a test that asserts the four
nested `citacao` sections appear with the right norms, so one saying
`continuation` would surface as a document that stayed flat.

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
