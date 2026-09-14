# Should the 74 `nao`→`secao` referee overrides become a rule?

- **Date:** 2026-09-14
- **Asked by:** [corpus-233 hardening plan](../dev/20260913_212337_corpus_233_hardening_plan.md) §5.3, Cycle 6 deliverable 3
- **Measured over:** all 233 documents of `../br-taxqa-r_v2.0/original/nao_articulados/`, replayed offline from `tests/corpus_referee_fixtures/`
- **Answer: no.** Recommendation and evidence below.

---

## 1. The question

Plan §1.8 observed that the referee overrode **74** `heading` decisions from
`nao` to `secao` — "74 prose headers the rules called 'not a section' were real
sections". §5.3 then asks:

> if the 74 `nao`→`secao` overrides can be captured as a rule, should they be?
> It trades referee cost for a rule tuned on 233 documents, which is exactly the
> generalisation risk §10 of the predecessor plan warns about.

The question has two halves, and they have different answers. *Can* they be
captured? Mostly not. *Should* the part that can be, be? It already has been, by
Cycle 3, without a referee.

## 2. The measurement

Replaying the corpus against the recorded answers, the `heading` question is put
**434 times**, and the referee's answers split:

| Referee verdict | Count |
|---|---|
| `secao` (confirms — overrides the `nao` rule verdict) | 75 |
| `nao` (vetoes — agrees with the rule) | 359 |

74 of the 75 confirmations clear `REFEREE_MIN_CONFIDENCE` and become overrides,
which is §1.8's figure.

## 3. Finding 1 — the same text is confirmed in one document and refused in another

This is the finding that decides the question. Seven distinct texts appear on
**both** sides:

| Text | `secao` | `nao` |
|---|---|---|
| `RELATÓRIO` | 19 | 2 |
| `ORDEM DE INTIMAÇÃO` | 7 | 1 |
| `I` | 2 | 5 |
| `II` | 3 | 3 |
| `III` | 2 | 4 |
| `IV` | 1 | 1 |
| `ASSUNTO: PROCESSO ADMINISTRATIVO FISCAL` | 1 | 3 |

Those seven texts carry **35 of the 74 confirmations** — and 19 refusals.

A rule keyed on the paragraph's text cannot reproduce this. Admitting them costs
19 false sections; refusing them costs 35 real ones. The referee is not applying
a lookup table the rules could copy: it is reading the paragraph's **position and
neighbours**, which is precisely what `next_ctx` was added for in A-H.2
(`CONCLUSÃO` followed by `19. A cessão de direitos…` reads as a heading;
`COORDENADOR-GERAL DA COSIT` followed by a disclaimer does not).

The bare roman numerals are the sharpest case. `I`, `II`, `III` and `IV` are
section numbers in one document and enumerated list items inside a quoted norm in
another. No amount of text-pattern tuning separates them.

## 4. Finding 2 — the learnable part is already learned, and not by a rule

The 40 confirmations on unambiguous texts are dominated by the stereotyped
skeleton of the soluções de consulta:

| Text | Confirmations |
|---|---|
| `FUNDAMENTOS` | 17 |
| `CONCLUSÃO` | 8 |
| `FUNDAMENTOS LEGAIS` | 1 |
| `EMENTA` | 1 |
| 13 further texts, one occurrence each | 13 |

Cycle 3 already admits exactly these — deterministically, with **no referee** —
through `DocumentProfile.section_res` on the `solucao_consulta` profile
(amendment A-3.1). So the subset that *is* rule-learnable has been captured, by
profile data rather than by a pattern learned from referee answers.

The 13 singletons are the remainder: `ALIENAÇÃO`, `AUXÍLIO-CRECHE.`,
`ACÓRDÃOS PARADIGMAS`, `VOTO VENCIDO EM PARTE`, `DEDUÇÃO`,
`CONDIÇÃO DE RESIDENTE OU NÃO-RESIDENTE.` and similar. One occurrence each, no
shared shape, and several are ementa topic-phrases rather than section headings
in any reusable sense. A rule built from thirteen one-off strings measured on
this corpus is the generalisation risk §10 warns about, in its purest form.

## 5. Finding 3 — the economic premise has changed

§1.8's case for referee spend was that it moved flatness **115 → 107**, eight
documents gaining structure. Measured today, against Cycle 1's rules-only
baseline:

| | §1.8 (pre-Cycle-3) | Now |
|---|---|---|
| Flat, rules-only | 115 | **86** |
| Flat, refereed | 107 | **83** |
| Documents gaining structure | 8 | **3** |

The three are `nota_pgfn_crj_1040_2015`, `parecer_pgfn_crj_701_2016` and
`sc_cosit_200_20211214`. Five of §1.8's original eight were soluções de consulta
that `section_res` now handles for free.

This does not make the referee worthless — three documents is three documents,
the 50 `quoted`→`own` corrections are untouched by this analysis, and confirm-only
adjudication cannot make a document worse (asserted by
`test_the_referee_never_removes_structure`). It does mean the trade §5.3 poses —
"referee cost versus a tuned rule" — is now a trade over a much smaller prize
than the plan assumed.

## 6. Recommendation

**Do not convert the 74 overrides into a rule.** Three reasons, in order of
weight:

1. **Nearly half of them are not text-separable.** 35 of 74 sit on texts that
   also appear as refusals. A rule would be wrong in both directions, and the
   errors it made would be *invisible* — a fabricated section looks exactly like
   a real one in the output.
2. **The separable part is already covered**, by `section_res`, which is profile
   data a human declared rather than a pattern fitted to 233 documents. That is
   the better mechanism for exactly the reason §10 gives.
3. **The remaining prize is three documents.** Spending a rule change — with its
   own generalisation risk over the 300+ unseen documents — on that is poor
   value against simply keeping the cached referee available.

**What to do instead**, and it is already done: publish the cache
(`tests/corpus_referee_fixtures/`, Cycle 6 deliverable 1) so a refereed run is
reproducible offline and at zero marginal cost. That removes the *dependency*
objection §1.8 raises without taking on the *generalisation* risk a rule would.

If a future genre shows a stereotyped skeleton the way the soluções did, the
right response is another `section_res` — declared from the genre's own
documentation — not a rule inferred from referee verdicts.
