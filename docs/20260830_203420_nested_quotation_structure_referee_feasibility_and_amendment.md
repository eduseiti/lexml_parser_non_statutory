# Nested quotation structure — can the LLM referee find it?

**Date:** 2026-08-30
**Status:** analysis + proposed plan amendment. **Nothing implemented.**
**Trigger:** user observation on `par_cosit_26_20000629`, item `14.`
(`pp1_agr17`), run with `--referee=api --referee-cache=/tmp/lexml_referee_cache`.

---

## 1. The observation

Item `14.` of `par_cosit_26` announces that it will quote four different laws:

> …como dispõem os arts. 1º a 3º e 16 da **Lei nº 7.713, de dezembro de 1988**,
> com as alterações dadas pelos arts. 2º e 18 da **Lei nº 8.134**, 27 de
> dezembro de 1990, 52 da **Lei nº 8.383**, de 30 de dezembro 1991, e 21 da
> **Lei nº 8.981**, de 20 de janeiro de 1995, *in verbis*:

The four excerpts that follow are emitted as **one flat run of 35 `<p>`
siblings** inside `Agrupamento id="pp1_agr17"`. The boundary between
*Lei 7.713* and *Lei 8.134* — a paragraph that literally begins
`Lei 8.134, de 1990 - "Art. 2º…` — is invisible in the output. A human reader
sees four quotations; the XML says "thirty-five paragraphs, some of them
quoted".

The user's expectation: each quoted law becomes a nested `Agrupamento`,
capturing the quotation hierarchy. The user's own framing — *"applying a
deterministic rule to identify that nested quotation structure would be very
hard, but I expected the LLM referee to be able to grasp that"* — is the right
diagnosis of the difficulty and, as it turns out, **the wrong diagnosis of why
it did not happen**.

---

## 2. Why the referee did not fix it: it was never asked, and could not act

Three separate facts, each verified in this session.

### 2.1 The referee has no question about quotation *structure*

`referee/protocol.py` declares exactly three methods, and plan §7.3 fixes them:

| Method | Question | Grain |
|---|---|---|
| `is_own_articulation(excerpt, ctx)` | is *this paragraph* our article or a quoted one? | one paragraph |
| `is_heading(para, ctx)` | is *this paragraph* a heading or prose? | one paragraph |
| `section_kind(label, heading)` | what kind of grouping does this rótulo name? | one label |

All three are **per-paragraph classification with a closed vocabulary**. None of
them can express "paragraphs 45–62 are one quotation of Lei 7.713 and 63–68 are
another of Lei 8.134". The verdict shape (`Verdict = {verdict: str,
confidence: float, rationale: str}`) has no room for a span, a boundary list, or
a name. So the referee did not fail to grasp the structure — **the structure is
not in its vocabulary**.

### 2.2 The referee is not wired into hierarchy inference at all

Verified by inspection of the call graph:

```
build_model()                       model/document.py:111-140
  ├─ segment_document(...)          no referee
  ├─ infer_hierarchy(...)           no referee  ← builds the tree, sets Para.kind
  └─ assess_viability(..., referee=referee)     ← the ONLY referee call site
```

`grep -rn "adjudicate\|referee" src/lexml_nonstat --include=*.py` outside
`referee/` returns hits in exactly two modules: `routing/viability.py` (the call
site) and `cli.py` (construction). `hierarchy/` contains none.

`hierarchy/tree.py:412` calls `analyse_quotation(paras)` directly and uses its
answer to set `Para.kind` — the thing that becomes `class="quote"` in the XML.
`routing/viability.py:302 _adjudicate_articles` runs the *same* quotation
analysis again, adjudicates it, and uses the adjudicated result **only to
recompute the article census that decides `norma` vs `generico`**. The
adjudicated verdicts are never fed back into the tree.

**Measured consequence.** On `par_cosit_26` with the warm cache:

```
$ python3 -m lexml_nonstat parse --referee=api --referee-cache=… sample.docx  > with_ref.xml
$ python3 -m lexml_nonstat parse                                  sample.docx  > no_ref.xml
$ diff with_ref.xml no_ref.xml   →  IDENTICAL
```

The referee's answers changed **nothing** in the emitted XML, even though the
decisions report shows it overrode two verdicts. Today the referee can only
change the *route*; it cannot change a single element of a `generico` artifact.

### 2.3 The referee, when it *was* asked, answered wrong twice out of three

This is the most consequential finding for the amendment, and it is evidence,
not speculation. The decisions report from the user's own cache:

```
rules   p#46  RULE FAILED: convicted only by a citation antecedent …  rule=quoted conf=0.55 (flagged)
rules   p#47  RULE FAILED: convicted only by excerpt-run extension …  rule=quoted conf=0.50 (flagged)
referee p#47  REFEREE OVERRODE RULE: rule=quoted conf=0.50 -> referee=own conf=0.95  final=own
              rationale="O Art. 3º é dispositivo subsequente ao Art. 2º no mesmo diploma legal,
                         indicando articulação própria do documento."
rules   p#53  RULE FAILED: convicted only by excerpt-run extension …  rule=quoted conf=0.50 (flagged)
referee p#53  REFEREE OVERRODE RULE: rule=quoted conf=0.50 -> referee=own conf=0.70  final=own
              rationale="O artigo apresentado como 'Art. 16' sem referência explícita a norma
                         externa sugere articulação própria do documento."

  referee agreed:    1   referee overrode:  2   referee overruled: 0   referee abstained: 0
```

`Art. 3º` (p#47) and `Art. 16` (p#53) are both **quoted text from Lei 7.713**.
The rule had them right at conf 0.50; the referee overrode both, at
confidence 0.95 and 0.70, with rationales that are internally coherent and
factually wrong. Read the first rationale closely: *"Art. 3º is the article
after Art. 2º in the same statute, therefore it is the document's own
articulation."* The model reasoned correctly about the statute and then drew the
exact wrong conclusion about **whose** statute it is — because the prompt showed
it one paragraph plus one paragraph of context, and the sentence that names the
owner (`Lei nº 7.713, de 1988 - "Art. 1º-…`, block 45) was **two** paragraphs
back and therefore outside `MAX_CONTEXT_CHARS`' single-paragraph window.

The route survived only because A-4b.2's monotonicity gate held it — which is
invariant #9 doing precisely the job it was designed for, and is exactly the
attack A-4b.6 already asserts. **The safety net worked. The referee did not.**

This changes what the amendment has to be. "Give the referee a new question"
is not enough; the evidence says the current prompt's *context window is the
defect*, and a span-level question is partly a fix for that — it puts the norm
that owns the excerpt inside the same prompt as the excerpt.

---

## 3. A second, smaller defect found on the way

Block **45** — `Lei nº 7.713, de 1988 - "Art. 1º- Os rendimentos e ganhos de
capital…` — is **not marked quoted**, which is why it renders as a bare `<p>`
with no `class="quote"` while every paragraph after it carries the class. The
user's excerpt shows this and it is easy to miss.

Cause, traced through `hierarchy/quotation.py`:

- `opens_with_quote` is false: the paragraph opens with `Lei`, not with `“`.
- `carries_omissis` is false.
- `names_external_norm` is **true** — but that only makes block 45 an
  *antecedent* for block 46, never a conviction of block 45 itself.
- the *weak* rule requires `ARTICLE_RE.match(text)`, and block 45's text starts
  `Lei nº 7.713…`, not `Art.` — so it does not match.
- `_extend_flat_excerpts` opens its run on a *convicted article*; block 45 is
  not convicted, so the run opens at block 46 and block 45 is left outside it.

The same pattern is present at blocks 63, 69 and 76 (`Lei 8.134, de 1990 -
"Art. 2º…`, `Lei 8.383, de 1991, Art. 12. ……`, `Lei 8.981, de 1995, "Art. 21.`),
but those *are* marked quoted — not because a rule recognised them, but because
they happen to sit **inside** an already-open run. The first one in a section is
the one that escapes.

This is the "inline-introduced quotation head" — `{norm name} - "{Art. N}…` — and
it is exactly the shape §2.6 identified as the residual hard case. It is
independently worth fixing and it is, conveniently, the *same* cue a span-level
referee question would key on.

**Corpus census** (`NORM_HEAD` = paragraph opens with a norm noun, and is
inside a quoted run):

| Sample | norm-heading paragraphs inside quoted runs |
|---|---|
| `par_cosit_26_20000629` | 3 — blocks 63, 69, 76 |
| `parecer_93_2018_decor_cgu_agu` | 2 — blocks 268, 321 |
| all other 13 samples | 0 |

Plus block 45, which the census misses precisely *because* it is unmarked. So
the true surface is **6 boundaries across 2 of 15 samples**.

---

## 4. Corpus sizing — how big is the problem actually?

Measured across all 15 samples:

| Sample | band rule | quoted paras | maximal quoted runs | body paras |
|---|---|---|---|---|
| `parecer_93_2018_decor_cgu_agu` | declared | 153 | 59 | 426 |
| `par_cosit_26_20000629` | none | 37 | **4** | 103 |
| `sumula_stj_125` | deviation | 13 | 11 | 359 |
| `REsp_1306393` | deviation | 9 | 3 | 15 |
| `pn_cst_38_19801031` | none | 2 | 2 | 88 |
| `ad_pgfn_3_20080918` | none | 2 | 2 | 6 |
| `ad_pgfn_13_20111220` | none | 1 | 1 | 7 |
| `port_mf_454_19770825` | none | 1 | 1 | 21 |
| other 7 samples | none | 0 | 0 | — |

Two readings matter.

**The problem is real but narrow.** Only `par_cosit_26` has a long multi-norm
run in a single section — 35 paragraphs, 4 quoted norms. `parecer_93` has 59
runs but they are short and each is introduced by its own antecedent in the
indent band, so a band-delimited run already corresponds one-to-one with a
quotation. The other 13 samples have nothing to nest.

**Which is exactly why this must not be tuned to `par_cosit_26`.** CLAUDE.md's
standing constraint: the 15 samples stand in for 300+ unseen documents. A rule
that splits on "paragraph begins with `Lei`" would fire correctly on 6
paragraphs here and unpredictably on 300 documents we have not read. This is
the textbook case for evidence fusion with graceful degradation — and, on the
evidence of §2.3, for a referee that is *asked* rather than *trusted*.

---

## 5. Is the target representable? Yes — three separate "yes"es

### 5.1 The internal model already nests

`model/nodes.py:260 Section` is recursive: `children: tuple["Section", ...]`.
A quotation becomes a child `Section` with `kind` naming it and `heading`
carrying the norm's name. **No model change is required** — this is the payoff
plan §11 predicted and the 2026-08-28 revision already collected once.

### 5.2 The flat emitter needs no schema change at all

`Agrupamento/@nome` is declared `type="xsd:string"` (`lexml/lexml-base.xsd:241`)
— an **open** attribute. `nome="citacao"` is valid on both shipped schemas
today. The flat emitter's `_section_elements` already recurses over
`section.children` and composes the id path (`pp1_agr17_agr1`), so a nested
quotation would emit as a sibling `Agrupamento` with a deeper id — which is
exactly §2.3's sanctioned hierarchy channel, and Rule A holds by construction.

### 5.3 The nested emitter gets it natively

`generico-aninhado` writes one `AgrupamentoHierarquico` per `Section`. A
quotation child becomes a real nested element with a real `NomeAgrupador`
carrying the norm's name — which is `ancestor::` addressable, and which is the
shape the community stylesheet argument in §11.2 / A-7.6 is asking for.

**So the ceiling is not the schema and not the model.** Everything blocking this
is in `hierarchy/` and in the referee's question vocabulary.

---

## 6. Can the LLM referee actually do it? Assessment

**Yes, with three qualifications — and it must be gated, not trusted.**

**In favour.** The task is genuinely well-suited to an LLM and badly suited to a
regex: "which of these paragraphs starts quoting a different norm" is semantic
segmentation over Portuguese legal prose, and the announcing sentence (*"como
dispõem os arts. 1º a 3º e 16 da Lei 7.713 … 8.134 … 8.383 … 8.981, in
verbis:"*) **names all four norms in advance, in order**. A model given the
announcement plus the numbered run has a near-oracle: it is matching a stated
list against candidate boundaries, not inventing structure. The corpus surface
is 6 boundaries in 2 samples — small enough to verify by hand, which is what
makes a fixture-based test honest.

**Against, and this is the §2.3 evidence.** The same model, on the same
document, answered 2 of 3 per-paragraph questions wrong at confidences of 0.95
and 0.70. High confidence was not correlated with correctness. Any design that
lets a span-level answer construct structure on the strength of its own
`confidence` field will fabricate structure — and invariant #8 ("low confidence
degrades to flat, never invents structure") is the plan's most load-bearing
promise. A wrong `class="quote"` is a mislabelling; a wrong nested
`Agrupamento` is a **fabricated citable unit with its own URN**, and §6.1's
segmentation output will hand it to a RAG system as an addressable fact.

**The resolution.** Invert the referee's role for this question. Do not let the
referee *propose* boundaries. Let a deterministic pass propose candidate
boundaries from cues that are already in the codebase, and put each candidate to
the referee as a **yes/no confirmation** — the same advisory shape §7.1 already
mandates, with the same closed vocabulary and the same `REFEREE_MIN_CONFIDENCE`
gate. A referee that can only *veto or confirm* a candidate the rules already
found cannot invent a section, which keeps invariant #8 an argument about the
candidate generator rather than a hope about the model.

This also fixes §2.3's actual defect for free: the confirmation prompt shows the
model the **announcing sentence and the candidate head together**, which is the
context the per-paragraph prompt structurally could not include.

---

## 7. Proposed amendment — A-9.1 / A-Q series

Offered for the user's approval. **Not implemented.** Placement: this is not
Cycle 9 work (Cycle 9 is regression consolidation and corpus scale-out); it is
a **new Cycle 8c**, sitting between the 2026-08-30 referee configuration
amendment and Cycle 9, in the same slot the configuration amendment took.

### A-Q.1 — Quotation runs become first-class, and the guard returns spans

`hierarchy/quotation.py` today returns `QuotationAnalysis.quoted`, a
`frozenset[int]` — a set of paragraph indices with no notion of where one
quotation ends and the next begins. Add a `runs: tuple[QuoteRun, ...]` field:

```python
@dataclass(frozen=True)
class QuoteRun:
    indices: tuple[int, ...]      # the paragraphs, in document order
    head: int | None              # the paragraph that introduces the norm
    norm: str | None              # "Lei nº 7.713, de 1988" — as written, never normalised
    antecedent: int | None        # the announcing paragraph, outside the run
    evidence: Evidence            # why we think this is a boundary
```

`quoted` stays exactly as it is, so every existing consumer — `tree.py`'s
`Para.kind`, `viability.py`'s census, all 135 goldens — is untouched. This is
additive by construction, which is the test: **the amendment's first commit must
leave all 135 goldens byte-identical.**

### A-Q.2 — Deterministic candidate generation, deliberately over-generous

A boundary candidate is proposed where a paragraph inside a quoted run *opens*
with a norm designation followed by an article marker — the
`{norm} - "{Art. N}` / `{norm}, {Art. N}` shape at blocks 45, 63, 69, 76. Reuse
`quotation.py`'s existing `_NORM_WORDS` vocabulary rather than adding a second
one; the folded-accent matching is already there.

Over-generation is the point. The generator's job is recall; precision is the
referee's and the gate's. It must be tuned to *not miss* the six known
boundaries, not to avoid proposing a seventh.

**A-Q.2 also discharges §3's defect independently.** A paragraph recognised as a
quotation head is quoted material, so block 45 gains `class="quote"` whether or
not the nesting lands. This is a **golden-changing** step and must be its own
reviewed commit — one sample, one paragraph, `par_cosit_26`.

### A-Q.3 — A fourth referee question: `quotation_boundary`, confirm-only

Extend the §7.3 protocol by one method:

```python
def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
    """Does `excerpt` begin a NEW quotation of a different norm?"""
```

with vocabulary `("boundary", "continuation")`, added to `prompts.VOCABULARIES`
and `_METHODS` in `adjudicate.py`. The prompt carries the **announcing
paragraph** as `ctx` (not merely the preceding one) and the candidate head as
`excerpt`, within the existing `MAX_CONTEXT_CHARS` / `MAX_EXCERPT_CHARS` caps —
so it inherits every §7.3 privacy guarantee unchanged, and it repairs the
context gap that produced §2.3's two wrong answers.

Adjudication goes through the existing `adjudicate()` unchanged: same
`FLAG_THRESHOLD`, same `RULE_HIGH_CONFIDENCE`, same
`REFEREE_MIN_CONFIDENCE`, same `DecisionRecord`, same cache. `NullReferee` and
`--referee=none` answer nothing and the document stays flat, which is invariant
#8 for free and keeps §9.3's default green.

**The referee may only veto.** A candidate the generator did not propose can
never become a boundary, whatever the referee says. This is the §6 resolution
written as code, and it should be asserted as an *attack* in the A-4b.6 style:
**an adversarial referee answering `"boundary"` to every question must not
change any sample's output**, because it has no candidates to answer about
outside the six.

### A-Q.4 — Confirmed runs become child `Section`s

In `tree.py`, a confirmed multi-run quotation inside one section becomes one
child `Section` per run:

- `kind = "citacao"` — a new member of `SECTION_KINDS`
- `heading = run.norm` — the norm as written; this becomes `NomeAgrupador`
- `body` = the run's paragraphs, `Para.kind` unchanged
- `evidence` records the cue and whether a referee confirmed it

`SECTION_KINDS` gains one member. `Agrupamento/@nome` is `xsd:string`, so
`nome="citacao"` is valid on both shipped schemas with **no schema work**
(§5.2 above).

### A-Q.5 — The gate: nest only when the whole run is accounted for

A section's quoted run splits into children **only if** every paragraph of the
run lands in exactly one child. A run with orphan paragraphs stays flat. This
makes conservation (invariant #2) a *precondition* of nesting rather than
something checked afterwards — the Cycle 6 lesson from A-6.3, where a render
was valid on both schemas and 29 words short.

Single-run sections stay flat: wrapping a lone quotation in a child that adds
no distinction is structure for its own sake, and it would churn goldens on
every sample in §4's table for no gain.

### A-Q.6 — Cross-emitter equivalence is the real regression risk

Invariant #11 and A-5b.4 are the exposure. A new nesting level changes body
ids on **both** emitters, and A-5b.4 already documented that the flat and
nested emitters disagree by a token *and* a top-level ordinal offset. Adding a
level under `pp1_agr17` must be verified not to introduce a *third* drift.
A-7.2's `Segment.path` (body ordinals, identical across derivations) is the
right assertion surface; `Segment.urn` is not.

Concretely: `par_cosit_26`'s goldens across up to 5 kinds change, and the
segmentation CSV/JSONL gains 4 rows. Every other sample must be byte-identical.

---

## 8. Risks, and what would make this not worth doing

| Risk | Severity | Mitigation |
|---|---|---|
| Referee fabricates a boundary → a fabricated citable URN | **high** — worst outcome in the plan | A-Q.3's confirm-only inversion; adversarial-referee attack test (A-4b.6 style) |
| §2.3 repeats: high-confidence wrong answers | **high**, and **already observed** | A-Q.3's wider `ctx`; `REFEREE_MIN_CONFIDENCE` still applies; A-Q.5's conservation gate |
| Tuning to `par_cosit_26` | medium — CLAUDE.md's standing constraint | 6 boundaries / 2 samples is too thin to tune on; A-Q.2 must be written from the *shape*, and its rejections logged (the A-4.2 / `DocSignals.rejected` precedent) |
| Golden churn | medium | staged commits: A-Q.1 changes nothing; A-Q.2 changes one paragraph; A-Q.4 changes one sample |
| Invariant #11 drift | medium | A-Q.6; assert on `Segment.path`, not `urn` |
| Cost/latency of a fourth question | low | 6 candidates across 15 samples; disk-cached; §7.2's sizing is unaffected |

**The honest counter-argument.** The whole nesting payoff, on the corpus we can
see, is **4 child sections in 1 of 15 samples**. If the 300+ unseen documents
turn out not to contain multi-norm quotation runs, A-Q.3–A-Q.6 buy very little
for a new referee question and a new `SECTION_KINDS` member.

That argument does **not** extend to A-Q.1 and A-Q.2, which are worth doing on
their own merits: A-Q.2 fixes a real mislabelling (§3, block 45) that exists
today and is visible in the user's own output, and A-Q.1 is a pure refactor that
gives the guard the vocabulary to *describe* what it found. A defensible reduced
scope is **A-Q.1 + A-Q.2 now, A-Q.3–A-Q.6 deferred until Cycle 9's corpus
scale-out says how common multi-norm runs actually are** — which is precisely
the question Cycle 9 exists to answer, and it would arrive with A-Q.1's `runs`
field already in place to measure it.

---

## 9. Open questions for the user

1. **Scope.** Full A-Q.1–A-Q.6 as one Cycle 8c, or the reduced A-Q.1 + A-Q.2
   now with the referee work deferred to Cycle 9's evidence? (§8's
   counter-argument is real; the recommendation is the reduced scope, because
   Cycle 9 is about to measure the exact number the full scope is betting on.)
2. **`kind` name.** `"citacao"` is proposed. `"transcricao"` and `"excerto"` are
   the alternatives; the LexML vocabulary does not settle it, since `@nome` is
   an open `xsd:string`.
3. **§2.3's override.** The referee overrode two verdicts wrongly at conf 0.95
   and 0.70 on the *existing* question. Independently of this amendment, should
   `own_articulation`'s `ctx` be widened from one preceding paragraph to the
   nearest preceding citation antecedent? That is a change to a delivered
   feature, it moves every cache key for that kind, and it is arguably the
   highest-value single fix this investigation found.
4. **Fixtures.** A-4b.5 established that referee fixtures are hand-authored and
   documented as such. The `quotation_boundary` fixtures should follow that
   precedent — 6 hand-authored answers — rather than recording whatever the live
   model says, given §2.3.

---

## 10. Verification log

Everything asserted above was measured in this session, against the working
tree at `64fba0b`, not inferred:

| Claim | How checked |
|---|---|
| Referee reaches only `routing/viability.py` | `grep -rn "adjudicate\|referee" src/lexml_nonstat --include=*.py`, excluding `referee/` |
| `infer_hierarchy` takes no referee | `model/document.py:111-140` read directly |
| Referee changes no XML | `parse` with and without `--referee=api`, warm cache → `diff` IDENTICAL |
| Referee overrode 2 of 3, both wrong | `decisions-report --referee=api --referee-cache=/tmp/lexml_referee_cache` |
| Cached answers and rationales | the 3 JSON files in `/tmp/lexml_referee_cache/` |
| Block 45 unquoted; 63/69/76 quoted | `analyse_quotation` over `par_cosit_26`, blocks 44–80 dumped |
| Why block 45 escapes | `opens_with_quote` / `carries_omissis` / `ARTICLE_RE` / `names_external_norm` probed per-block |
| Corpus run census (§4 table) | `analyse_quotation` over all 15 samples, maximal quoted runs counted |
| Norm-heading census (§3 table) | `NORM_HEAD` regex over paragraphs inside quoted runs, all 15 samples |
| `Section` is recursive | `model/nodes.py:260` |
| `@nome` is `xsd:string` | `lexml/lexml-base.xsd:241` |
| `Agrupamento`/`AgrupamentoHierarquico` declarations | `lexml/lexml-base.xsd:834-855` |
