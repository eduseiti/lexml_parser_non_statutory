# Front matter: layout tables, "O PRESIDENTE DA REPÚBLICA", portal publication lines

- **Written:** 2026-10-08
- **Found in:** `../br-taxqa-r_v2.0`, rebuild step R7 (segmentation) of
  `../br-taxqa-r_v2.0/docs/20261007_180833_corpus_fixes_and_full_rebuild_plan.md`. Nine treaty
  decrees and two old INs moved from the statutory to the non-statutory path on 2026-10-07. The
  segmentation's coverage check failed on a dropped table, and every chunk of those documents
  carried a wrong ementa in its metadata prefix.

## Symptoms (before)

| Document | Agrupamento `ementa` | Real ementa |
|---|---|---|
| Decreto 27.784/1950, 59.308/1966, 62.125/1968, 93.153/1986 | the preamble ("O PRESIDENTE DA REPÚBLICA…") | inside a one-row table (empty first cell, ementa in the second), read as a data table in `preliminar` |
| Decreto 63.151/1968 | "Download para anexo" | same table; the masthead and the preamble are one-row tables too |
| Decreto 59.309/1966 | "Vide Recurso extraordinário nº 522897 Texto compilado …" (Planalto link line) | the next paragraph |
| IN SRF 23/1983, 67/1988, PN CST 38/1975, 72/1979, 25/1976 … (18 Receita portal pages) | "Norma Federal - Publicado no DO em …" / "Publicado no DOU em …" | the next paragraph, or none |

## Changes

| File | Change |
|---|---|
| `src/lexml_nonstat/ingest/__init__.py` | `unwrap_layout_tables(doc, window=12)`, applied by `read_document`: a **one-row** table among the first 12 blocks becomes one paragraph per non-empty cell (the cell's paragraphs joined; the first paragraph's properties kept), and block indices are renumbered. Tables with ≥ 2 rows, and every table after the window, are untouched. On the 232 `.docx` of the br-taxqa corpus the rule fires in exactly 5 documents (7 tables) |
| `src/lexml_nonstat/segment/frontmatter.py` | `_PREAMBLE_RES` + `^o presidente da república\b` (the presidential decree opener, with or without "dos Estados Unidos do Brasil" and the comma). `_EDITORIAL_RES`: lines starting with "Vide", "Texto compilado/original/para impressão", "Download", "(Norma Federal -) Publicado no D(O|OU)" are skipped before the unlabelled-ementa rule takes "the paragraph after the epigraph" |
| `tests/unit/test_front_layout_tables.py` | 5 tests: unwrap (merge, renumber, data and late tables kept), ementa from the unwrapped cell, presidential preamble, editorial lines skipped |

## Effect

- `pytest tests`: the 5 new tests pass; the same 11 corpus-dependent tests fail as before the change
  (see `docs/20261008_003108_declared_urn_option.md`). The goldens are unchanged.
- br-taxqa-r_v2.0 re-parse (same command as in that note, referee answers cached): 27 of 245 files
  change and 218 are byte-identical. The 27 are the 9 treaty decrees, IN SRF 23/67/84, portaria MF
  80/1979, AD SRF 11/1978 and 16/1979, 10 PN CST, SD Cosit 16/2012 and AD PGFN 1/2014. In each, the
  `ementa` Agrupamento is now the real ementa, or absent where the source has none (IN SRF 84/1979,
  AD 16/1979, SD 16/2012, AD PGFN 1/2014). The publication line moved to `preliminar`, and the
  decrees' preamble to `preambulo`.
