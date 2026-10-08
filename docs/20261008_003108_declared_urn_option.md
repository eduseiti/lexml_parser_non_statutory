# `parse --urn` / `--metadata`: declared document identity

- **Written:** 2026-10-08
- **Requested by:** `../br-taxqa-r_v2.0`, rebuild step R3c of
  `../br-taxqa-r_v2.0/docs/20261007_180833_corpus_fixes_and_full_rebuild_plan.md` (§3.2, decision D8)

## Problem

`parse` infers each document's identity (`urn:lex:br:<authority>:<type>:<date>;<number>`) from the
text and the profile. On the 233-document br-taxqa-r_v2.0 corpus some guesses were wrong. Examples
(stem → inferred authority:type):

| Document | Inferred | Should be |
|---|---|---|
| `nota_pgfn_981_20151104` | `…secretaria.receita.federal : sumula` | `procuradoria.geral.fazenda.nacional : nota` |
| `nota_pgfn_crj_1104_2017` | `superior.tribunal.justica : solucao.consulta` | `procuradoria.geral.fazenda.nacional : nota` |
| `par_pgfn_2271_20131210`, `parecer_sei_110_2018` | `superior.tribunal.justica : parecer` | `procuradoria.geral.fazenda.nacional : parecer` |
| `in_srf_84_19791220` | `…receita.federal : ato.declaratorio` | `…receita.federal : instrucao.normativa` |
| `sc_cosit_69/140/194`, `sc_6007` | `federal : solucao.consulta` | `…receita.federal : solucao.consulta` |

The current rules also leave the date as `0000` for 20 documents (court decisions, súmulas, PGFN
notes cited by year). The URN is the document's identity across the dataset (gold references, chunk
`doc_urn`, `Remissao` targets), so a wrong guess breaks every cross-reference. For a curated corpus
the identity is known from outside the text and should be **declared**, not inferred.

## Change

| File | Change |
|---|---|
| `src/lexml_nonstat/model/metadata.py` | `declare_urn(metadata, urn)`: replaces locality/authority/type/date/number with the declared URN's and sets `authority_source`, `date_source`, `number_source` to `"declared"`. A URN with a fragment (`!anexo1`) is refused |
| `src/lexml_nonstat/model/__init__.py` | exports `declare_urn` |
| `src/lexml_nonstat/cli.py` | `parse --urn URN` (exactly one source) and `parse --metadata TSV` (header with `stem` and `urn` columns; stems not listed keep the inferred URN; `#` lines are comments). The declared metadata goes into `build_model(metadata=…)`, so `Identificacao`, the annex URNs (`…!anexoN`) and the `-o` file names all follow it. Invalid URNs and misuse exit 2 |
| `tests/unit/test_declared_urn.py` | 5 tests: components and sources, `Identificacao`, file and annex names from a TSV, unlisted stems unchanged, misuse refused |

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse --urn \
    'urn:lex:br:procuradoria.geral.fazenda.nacional:nota:2015-11-04;981' nota_pgfn_981_20151104.docx
PYTHONPATH=src python3 -m lexml_nonstat parse --metadata nonstat_metadata.tsv -o out/ docs/*.docx
```

Without `--urn`/`--metadata`, output is unchanged.

## Tests

`pytest tests`: the 5 new tests pass. **11 tests fail with and without this change** (same list):
`test_flatness_causes.py` (4), `test_profile_solucao_consulta.py` (2) and `test_referee_economics.py`
(5). They read the live corpus at `../br-taxqa-r_v2.0/original/nao_articulados/` and pin its
2026-09 state (233 documents, flatness counts, cached referee answers). That corpus changed on
2026-10-07: 22 wrong documents were replaced, 11 moved in from `articulados/`, 4 removed, and 12
soluções de consulta are now PDFs. These tests need new expected values (or a frozen copy of the
corpus); that is left for a later cycle of this repository.

## Use in br-taxqa-r_v2.0 (2026-10-08)

All 244 non-statutory sources were parsed with
`--emitter=generico-aninhado --generation=proposed --referee=api --linker=/usr/local/bin/linkertool
--metadata ../br-taxqa-r_v2.0/scripts/lexml/nonstat_metadata.tsv`. Result: 244 documents + 1 annex,
schema-valid, exit 0. 12 sources are plain text made from PDFs by br-taxqa-r_v2.0's
`scripts/lexml/pdf_to_text.py`; all 12 route to the `solucao_consulta` profile and get the right URN
even without the declaration.

**Linker round trip (plan §3.2 step 3) is not possible for these types.** `linkertool` recognizes
federal statutory acts only. It returns nothing for "Nota PGFN/CRJ nº 981/2015", "Solução de
Consulta Cosit nº 166, de 28 de maio de 2019", "Parecer PGFN/CRJ nº 2.118, de 2011", "Ato
Declaratório PGFN nº 3, de 30 de março de 2016", "Súmula CARF nº 42" or "Instrução Normativa SRF
nº 23, de 1983". For "Decreto nº 27.784, de 16 de fevereiro de 1950" it gives the declared URN. The
vocabulary of the declared URNs therefore follows the conventions this parser and the statutory
side already use (e.g. `instrucao.normativa`, `procuradoria.geral.fazenda.nacional`).
