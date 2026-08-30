# Running header/footer artifacts in the body — detection analysis

**Date:** 2026-08-30
**Status:** analysis only. **Nothing implemented.**
**Trigger:** user observation on `par_cosit_26_20000629` — `Documento de 7
página(s) autenticado digitalmente…` ×7 and `Fl. <n> DF COSIT RFB` ×7 reaching
the LexML output as body paragraphs.

---

## 1. The observation, confirmed and quantified

`par_cosit_26` carries **14 artifact paragraphs** in its body:

| Block | Text |
|---|---|
| 4 | `Fl. 6 DF COSIT RFB` |
| 20, 31, 41, 55, 74, 88, 100 | `Documento de 7 página(s) autenticado digitalmente. Pode ser consultado no endereço https://cav.receita.fazenda.gov.br/eCAC/publico/login.aspx pelo código de localização EP23.0118.14172.QC77. Consulte a página de autenticação no final deste documento.` |
| 21, 32, 42, 56, 75, 89 | `Fl. 7…12 DF COSIT RFB` |

They total **217 of the document's 3 275 words — 6.6%**. All 14 are inside
`Segmentation.body` (verified), so Cycle 3's front/back matter machinery does
not and cannot reach them.

Two structural facts make them unusually tractable:

- the boilerplate is **byte-identical across all 7 occurrences** (verified with
  a `Counter` over exact strings — one key, count 7);
- the folio is a **strict arithmetic progression**, `Fl. 6 … Fl. 12`, step 1,
  no gaps;
- and they occur as an **adjacent pair** (`Documento de…` immediately followed
  by `Fl. n`) at every page break except the first, where `Fl. 6` appears alone
  at block 4.

The pairing is the page boundary: footer-of-page-*n* then header-of-page-*n+1*,
flattened in reading order.

### 1.1 The user's diagnosis is correct, and verifiable from the file

`par_cosit_26_20000629.docx` contains **no `word/header*.xml` or
`word/footer*.xml` parts at all** (`unzip -l`). By contrast `sumula_stj_125` has
18 such parts and `parecer_93` has 43. So this is not a reader bug: the
fetching/conversion mechanism dissolved the real header and footer objects into
`document.xml` as ordinary paragraphs, and by the time the DOCX reaches us the
distinction has already been destroyed.

`ingest/docx_reader.py:519` walks `document.element.body` and nothing else, so
**genuine** headers and footers are already correctly excluded — `parecer_93`'s
`header1.xml` holds `https://sapiens.agu.gov.br/documento/195475868` and never
appears in `StyledDoc`. The problem is confined to documents where the
provenance was flattened upstream.

---

## 2. The corpus surface — smaller than it looks, and one trap

Scanning all 15 samples for artifact-shaped paragraphs (URL, `Fl. n`,
`página(s)`, `autenticado/assinado digitalmente`, `Página n de m`):

| Sample | Hits | In body? | Verdict |
|---|---|---|---|
| `par_cosit_26_20000629` | 14 | all body | **artifacts** |
| `parecer_93_2018_decor_cgu_agu` | 4 | 1 body, 2 back matter, 1 false hit | **1 artifact** (block 65) |
| `REsp_1306393` | 1 | body | **artifact** (block 15) |
| `sistema_…_CARNE_LEAO` | 1 | body | **CONTENT — must not be filtered** |
| other 11 samples | 0 | — | — |

**The real body-resident surface is 16 paragraphs across 3 of 15 samples.**

Three of the four non-`par_cosit_26` cases repay individual inspection, because
they are what any rule has to get right:

**`parecer_93` block 65 — a genuine artifact, and a singleton.**
`zot 10 https://sapiens.agu.gov.br/documento/195475868` sits at indent 0
between block 64 (`Art. 33. Esta Lei entra em vigor:`, indent 2908) and block 66
(`I - quanto ao disposto no Cupítulo I…`, indent 2908). It is a flattened
header — the same URL that `header1.xml` legitimately carries — and it splits an
article from its own inciso. Note it occurs **once**: any rule keyed on
repetition misses it entirely.

**`REsp_1306393` block 15 — a genuine artifact, also a singleton.**
`Documento: 25489411 - EMENTA / ACORDÃO - Site certificado - DJe: 07/11/2012
Página 1 de 2`, sitting between two sentences of the acórdão's attendance list.

**`CARNE_LEAO` block 110 — content, and the trap.**
`https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/lgpd/termo-de-uso`
is preceded by block 109, `Link da política de privacidade/termo de uso do
serviço`. It is a bare URL on its own line, at indent 0, in a body — which is
*exactly* the shape of `parecer_93`'s block 65 — and it is **real document
content**, introduced by its own antecedent. A URL-shaped rule filters it and
loses information the document meant to convey.

That pair — `parecer_93` #65 vs `CARNE_LEAO` #110 — is the precision test any
proposal has to pass. They differ in one respect only: #110 answers the
paragraph before it, and #65 interrupts the paragraph before it.

---

## 3. Why the obvious rules fail — measured, not argued

### 3.1 Exact repetition ≥ 3 would mutilate `sumula_stj_125`

Counting exactly-repeated non-empty paragraphs across the corpus:

| Sample | Repeated text | n |
|---|---|---|
| `par_cosit_26` | `Documento de 7 página(s)…` | 7 |
| `par_cosit_26` | `………………` (omissis) | 4 |
| `sumula_stj_125` | `VOTO` | **8** |
| `sumula_stj_125` | `EMENTA` / `ACÓRDÃO` / `RELATÓRIO` / `É o relatório.` | **7 each** |
| `sumula_stj_125` | `Recorrente: Fazenda do Estado de São Paulo` | 5 |
| `parecer_93` | `(...)` | 6 |

`sumula_stj_125`'s repeats are its **structure**: A-4.3 records that its 38
same-level headings group into 7 cases × 31 parts, and `VOTO` / `EMENTA` /
`ACÓRDÃO` / `RELATÓRIO` are precisely those headings. A repetition rule deletes
a level of the document's hierarchy. `parecer_93`'s `(...)` ×6 is omissis, which
Cycle 4 already models as `Para.kind="omissis"`.

**So repetition alone is disqualifying, not qualifying.**

### 3.2 Positional regularity does not separate them either

Computing the coefficient of variation of the gaps between occurrences (a page
footer should recur at near-constant intervals):

| Text | n | gap CV | Word heading? |
|---|---|---|---|
| `Documento de 7 página(s)…` | 7 | **0.219** | no |
| `Art. 3º (...)` (`parecer_93`) | 3 | 0.192 | no |
| `VOTO` | 8 | **0.302** | **yes** |
| `É o relatório.` | 7 | 0.407 | no |
| `ACÓRDÃO` / `EMENTA` / `RELATÓRIO` | 7 | 0.41–0.43 | **yes** |

The artifact's 0.219 and `VOTO`'s 0.302 are not separable by any threshold that
survives contact with an unseen document. Page breaks in a document with
variable-length paragraphs are simply not that regular, and structural headings
in a repetitive genre are not that irregular.

### 3.3 What *does* separate them

Two signals do the work, and both are already computable from existing state:

**(a) Word's own heading declaration.** All four of `sumula_stj_125`'s dangerous
repeats carry `outline_level=0` / `style="Heading 1"`. Every artifact in the
corpus is `style="Normal"`, `outline_level=None`. This is the same authorial
declaration `quotation.py:_is_style_heading` already treats as
outvoting-everything (A-4.1's corollary), and reusing it keeps one rule rather
than inventing a second.

**(b) Interruption vs. answering.** Collapsing the `Documento de…`+`Fl. n` pair
into a single unit and asking what the label sequence does across it:

```
block 55  prev: 'I - o valor atribuído para efeito de pagamento do imposto de transmissão;'
block 56  [artifact pair]
block 57  next: 'II - o valor que tenha servido de base para o cálculo do imposto…'
```

The enumeration runs `I → [artifact] → II`. The artifact **interrupts a sequence
that resumes**. Same at blocks 41/42 (`numeric → artifact → numeric`), 88/89,
and at `parecer_93` #65 (`Art. 33. … entra em vigor:` → artifact → `I - quanto
ao disposto…`).

`CARNE_LEAO` #110 does the opposite: block 109 introduces it (`Link da política
de privacidade/termo de uso do serviço`) and nothing resumes after it. It
**answers** its antecedent rather than interrupting it. This is structurally the
same discrimination `names_external_norm` already makes for citation
antecedents, and it is what the two-signal fusion has to key on.

---

## 4. The blocker: dropping text violates invariant #2, hard

This is not a soft constraint and it is the reason the answer cannot simply be
"filter them out".

`tests/regression/test_conservation_generico.py:139` asserts **multiset
equality** between source words and emitted words, per sample:

```python
source = source_words(doc)
emitted = emitted_words(bundle)
assert emitted == source, diff_message(name, source, emitted)
```

and `:154` asserts set equality in both directions. Plan §9.2 invariant #2 is
"all source text present exactly once". Deleting 217 words from `par_cosit_26`
turns both tests red immediately, and the second one's failure message —
"source words never emitted" — is exactly right: they *were* in the source.

There is a deeper reason than the test. A-8.6 recorded that an encoding bug was
invisible to every invariant the plan has, because *both sides of the comparison
carried the same mojibake*. Conservation is the parser's only structural defence
against silent loss. A feature whose whole purpose is to make text disappear is
the one feature that can disable that defence — and once "the emitter may drop
paragraphs it dislikes" is true, no conservation test can distinguish a filtered
footer from a lost page.

**Corollary: a `--strip-artifacts` flag that deletes text is the wrong design**,
even as an opt-in, because the invariant it suspends is the one that catches
every *other* bug in the pipeline.

---

## 5. The recommendation: classify and mark, never delete

Mark artifacts with a `Para.kind`, exactly as Cycle 4's quotation guard marks
quoted text and refuses to promote it (spec decision D-5, A-5.4).

```
PARA_KINDS = {"prose", "quote", "citation", "field", "omissis"}   # today
PARA_KINDS = {..., "artefato"}                                     # proposed
```

`render_para` (`render/common.py:188`) already writes any non-`prose` kind as
`<p class="…">`, and `class` **adds no text**, so conservation is untouched by
construction — the same argument A-5.4 made for `class="quote"` and A-5b.2 made
for `<Bloco nome="ordem">`. `Agrupamento/@nome` and HTML `@class` are both
unconstrained by the schemas, so **no schema work is required** and output stays
valid on both.

What this buys, concretely:

- The artifact is **visible and machine-filterable** in the output:
  `//p[not(@class="artefato")]` is a one-line XPath, and Cycle 7's segmentation
  (§6.1) can exclude them from `Segment` text so a downstream RAG index never
  sees them — which is the actual goal.
- The parser **says what it concluded** instead of silently acting on it, which
  is invariant #10 and the reason `class="quote"` exists at all.
- A wrong verdict costs a mislabelled paragraph, not a lost one. Given §3's
  measurements — a rule that gets `CARNE_LEAO` #110 wrong is entirely plausible
  — this asymmetry is the whole argument.
- Conservation keeps working as a defence for everything else.

**Consumers that genuinely want the text gone** get it at the segmentation
layer (drop `artefato` paragraphs when building `Segment.text`), where nothing
claims to conserve the source, rather than at the emitter, where something does.

### 5.1 Detection design, if it is built

Fusion of cues already in the codebase, in the plan's established idiom — no
single cue convicts:

| Cue | Source | Note |
|---|---|---|
| exact repetition ≥ 3 | new counter over body blocks | **necessary, never sufficient** (§3.1) |
| Word heading declaration | `quotation.py:_is_style_heading` | **vetoes** — protects `sumula_stj_125` |
| folio arithmetic progression | new; `Fl. n`, `Página n de m`, step 1 | very high precision, low recall |
| provenance vocabulary | new, profile-gated | `autenticado/assinado digitalmente`, `código de localização`, `Site certificado` |
| interrupts a resuming label sequence | `labels.parse_label`, already there | separates `parecer_93` #65 from `CARNE_LEAO` #110 (§3.3b) |
| answers its own antecedent | `names_external_norm` idiom | **vetoes** — protects `CARNE_LEAO` #110 |
| the DOCX has **no** header/footer parts | new; `unzip -l`-equivalent at ingest | a document-level *prior*, not a per-paragraph rule |

The last one deserves emphasis. `par_cosit_26` having zero header/footer parts
while every comparable sample has dozens is the cleanest document-level evidence
in this investigation: it says *this file's provenance was flattened*, which is
precisely the precondition for the whole phenomenon. It cannot convict a
paragraph on its own, but it is the right thing to gate the aggressive cues on —
and it costs one boolean on `StyledDoc`.

**Profile gating.** A-3.3's precedent is directly on point: an ungated `^ANEXO`
rule amputated 28 blocks off `sumula_stj_125`. The provenance vocabulary is
issuer-specific (`DF COSIT RFB` is Receita Federal; `Site certificado` is STJ;
`sapiens.agu.gov.br` is AGU), so it belongs in `DocumentProfile` as a
`artifact_res: tuple[re.Pattern, ...] = ()` field defaulting to empty — the same
shape as `enacting_res` / `annex_res` / `closing_res`.

**Singletons are the hard half.** Repetition catches 14 of the 16; `parecer_93`
#65 and `REsp_1306393` #15 occur **once each** and can only be reached by the
vocabulary cue plus the interruption cue. Recall on singletons should be
expected to be poor, and that is acceptable under a marking design in a way it
would never be under a deleting one.

### 5.2 The referee has a defensible role here — a smaller one than it looks

This is the same question as the companion investigation
(`20260830_203420_…nested_quotation…`), and it gets the same answer for the same
reason. §2.3 of that document measured the referee answering **2 of 3 wrong at
confidence 0.95 and 0.70** on this very sample. A referee allowed to *propose*
"this paragraph is an artifact" would be a referee allowed to mark real content
as noise.

If a referee is used, it should be **confirm-only** over candidates the
deterministic cues already produced, via a fourth-question extension of the
kind that document's A-Q.3 proposes — and the `CARNE_LEAO` #110 vs `parecer_93`
#65 discrimination is a genuinely good LLM question, since it is semantic
("does this answer the previous line or interrupt it?") and hopeless for a
regex. 16 candidates across 15 samples is a trivially cacheable volume.

---

## 6. Interaction with existing work

| Area | Effect |
|---|---|
| Invariant #2 (conservation) | **untouched** — marking adds no text and removes none. This is the design's central claim |
| Invariant #8 (no fabrication) | a mislabel is not fabricated structure; degradation is to `prose`, which is today's behaviour |
| Cycle 3 front/back matter | unaffected; `parecer_93` #432/#434 are already in back matter and need nothing |
| Cycle 4 quotation guard | artifacts currently land **inside** quoted runs (blocks 55/56, 74/75 sit within the Lei 7.713 excerpt) and are marked `class="quote"` — which is wrong today and would be corrected by a more specific kind |
| Cycle 7 segmentation | the payoff surface: `Segment.text` can exclude `artefato` so a RAG index never sees the boilerplate |
| Goldens | `par_cosit_26` (14 paragraphs), `parecer_93` (1), `REsp_1306393` (1) change across up to 5 kinds; the other 12 samples must stay byte-identical, and that is the test |
| Schemas | **no change** — `@class` is free-form, `@nome` is `xsd:string` (`lexml/lexml-base.xsd:241`) |
| `PARA_KINDS` | gains one member; `tests/golden/test_hierarchy_goldens.py:268` and `test_render_common.py:300` already iterate the frozenset and will cover it automatically |

---

## 7. Honest assessment

**Worth doing, at marking scope, with modest expectations.**

In favour: the artifacts are real, they are 6.6% of one sample, they corrupt a
quoted excerpt by splitting `I -` from `II -`, and they are exactly the kind of
noise that degrades a RAG index — which is this repository's parent purpose.
The detection signals are genuinely available and the strongest of them
(no header/footer parts in the DOCX) is close to decisive at document level.

Against: the corpus gives **16 positive examples in 3 samples and one
near-identical negative** (`CARNE_LEAO` #110). That is a thin basis for a rule
meant to run on 300+ unseen documents from issuers whose boilerplate we have
not seen, and CLAUDE.md's standing constraint applies with full force. Recall
on singletons will be poor.

Which is precisely why the marking design is the right one and a deleting
design is not: **at marking scope, being wrong is cheap and recoverable; at
deleting scope, being wrong is silent and permanent** — and it disables the one
invariant that catches unrelated bugs.

A defensible minimal first step, if the user wants the smallest useful change:
record the **document-level** `has_header_footer_parts` boolean at ingest and
surface it as a `warnings.py` code (`flattened_provenance`). That tells an
operator "this file's headers were dissolved into the body, expect artifacts"
without classifying a single paragraph, changes no golden, and gives Cycle 9's
corpus scale-out the instrument to measure how common the phenomenon actually
is before any rule is tuned to three samples.

---

## 8. Open questions for the user

1. **Scope.** Full detection + `kind="artefato"`, or the §7 minimal step
   (document-level warning only) with detection deferred until Cycle 9 has
   measured prevalence? Recommendation: the minimal step, for the same reason
   the companion document recommends deferring its referee work — Cycle 9 is
   about to supply the number both proposals are guessing at.
2. **Kind name.** `artefato` is proposed. `ruido`, `paginacao` and `cabecalho`
   are alternatives; `@class` is free-form so nothing external constrains it.
3. **Deletion escape hatch.** Should a `--drop-artifacts` flag exist at all
   (suspending conservation, loudly, with a warning)? My recommendation is
   **no** — offer the exclusion in Cycle 7's segmentation output instead, where
   no conservation claim is being made.
4. **Profile gating.** Confirm the A-3.3 precedent applies — `artifact_res` on
   `DocumentProfile`, defaulting to empty, rather than a global vocabulary.

---

## 9. Verification log

Everything above was measured in this session against the working tree at
`64fba0b`:

| Claim | How checked |
|---|---|
| 14 artifacts, blocks and text | `read_docx` over `par_cosit_26`, filtered on `Fl.` / `Documento de` |
| 217 / 3 275 words = 6.6% | word count over the same blocks |
| boilerplate byte-identical ×7 | `Counter` over exact stripped strings |
| folio is `6…12`, step 1 | printed all `Fl.` variants |
| `par_cosit_26` has no header/footer parts | `unzip -l` on all three samples |
| genuine headers are already excluded | `unzip -p … word/header1.xml` on `parecer_93`; reader walks `document.element.body` (`docx_reader.py:519`) |
| corpus repetition census (§3.1) | `Counter` over non-empty blocks, all 15 samples, n ≥ 3 |
| `sumula_stj_125` repeats are Word headings | `outline_level` / `style` per occurrence |
| gap-CV table (§3.2) | `pstdev/mean` of occurrence gaps, all 15 samples |
| artifact-cue census (§2) | regex over all 15 samples |
| which hits are in body vs front/back | `segment_document` per sample, membership tested |
| `CARNE_LEAO` #110 is content | blocks 109–111 printed with context |
| interruption vs answering (§3.3b) | prev/next non-empty neighbours printed for every candidate |
| label sequence resumes across artifacts | `parse_label` on prev/next neighbours |
| conservation is multiset equality | `tests/regression/test_conservation_generico.py:139,154` |
| `class` adds no text | `render/common.py:188 render_para` |
| `@nome` is `xsd:string` | `lexml/lexml-base.xsd:241` |
| `DocumentProfile` `*_res` precedent | `profile/base.py:73-94` |
