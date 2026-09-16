# STF acórdãos: URN from the court cover, and the bare `EMENTA` heading

## Symptom

```bash
PYTHONPATH=src python3 -m lexml_nonstat parse \
            --emitter=generico-aninhado --generation=proposed \
            --referee=api \
            --referee-cache=/tmp/lexml_referee_cache \
            --linker=/usr/local/bin/linkertool --linker-cache=.cache/linker \
            -o ../br-taxqa-r_v2.0/lexml \
            ../br-taxqa-r_v2.0/original/nao_articulados/adi_5422_STF.docx
```

printed

```
warning: adi_5422_STF.docx: incomplete_urn: the URN is a best effort; missing: doc_type, number
urn        : urn:lex:br:federal:documento:2022-06-06;0
profile    : generic
```

when the document's LexML identity is

```
urn:lex:br:supremo.tribunal.federal;plenario:acordao;adi:2022-06-06;5422
```

## Investigation

### 1. Wrong profile

The document opens with a court *cover*, not an epigraph:

```
0  06/06/2022 PLENÁRIO
1  AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422 DISTRITO FEDERAL
2  <table: requerentes / interessados>
3  EMENTA
   …
16 ACÓRDÃO
17 Vistos, relatados e discutidos estes autos, acordam os Ministros do Supremo Tribunal Federal, …
```

`jurisprudencia_generico` listed `acao.direta.inconstitucionalidade` in its
`urn_type_res`, but **not** in its `epigraph_res`. Its `authority_res` names
only STJ and CARF. So the profile scored 0.0, and `generic` won with its 0.05
floor. Two other corpus documents have the same problem: `adi_5583_STF` and
`re_855091_tema_808`.

### 2. No reader for the cover

Even with the right profile, `_find_epigraph` could not read the cover:

- `_EPIGRAPH_RE` requires `nº` between type and number. The cover writes
  `AÇÃO DIRETA DE INCONSTITUCIONALIDADE 5.422` without it.
- `_BARE_DATE_RE` accepts a date stamp only when the date is alone on the line.
  The cover writes `06/06/2022 PLENÁRIO`. (The date was right before the fix
  only because the closing line `Brasília, 6 de junho de 2022.` agrees.)
- The number fallback `_number_from_filename` does not match `adi_5422_STF`
  (trailing `_STF`), so the number fell to the `;0` sentinel.
- Nothing produced the `acordao;<classe>` type or the `<tribunal>;<órgão>`
  authority that LexML uses for court decisions.

The linker (`linkertool`) was checked as a possible source for the URN form.
It resolves no court-decision citations (`ADI 5.422`, `RE 855.091/RS`,
`REsp 1.306.393/DF` all return nothing), so it cannot help here.

### 3. A side effect found while fixing it: the bare `EMENTA` heading

Once the profile was right, the class line (block 1) became the epigraph.
`find_ementa`'s *unlabelled* rule then claimed the next paragraph as the
ementa. That paragraph is the bare **heading** `EMENTA` (block 3). The heading
left the body, which then had only one section (`ACÓRDÃO`), so the tree went
from `structured (0.60)` to `flat (0.30, too_few_sections)`.

The committed sample `REsp_1306393` **already had this defect**. Its goldens
contained

```xml
<Agrupamento id="pp1_agr3" nome="ementa">
  <p>EMENTA</p>
</Agrupamento>
```

## Fix

### Court-cover recognition (`profile/base.py`, `profile/jurisprudencia_generico.py`, `model/metadata.py`)

Three new data fields on `DocumentProfile`, all defaulting to `()`. They are
empty on every profile except `jurisprudencia_generico`:

| Field | Content |
|---|---|
| `decision_class_res` | class-line pattern → sigla: `ado`, `adi`, `adc`, `adpf`, `are`, `re`, `resp`, `ms`, `hc`, `rcl` (most specific first) |
| `decision_body_res` | órgão-julgador names allowed on the stamp: `plenario`, `tribunal pleno`, `corte especial`, `<ordinal> turma/secao` |
| `court_res` | court name → authority slug (`supremo.tribunal.federal`, `superior.tribunal.justica`) |

`jurisprudencia_generico.epigraph_res` gains one pattern for STF class lines
(ADI/ADO/ADC/ADPF/RE/ARE). The pattern **requires a number after the class
name**, so a sentence that merely begins with "Recurso extraordinário." does
not claim the genre. `authority_res` was deliberately **not** extended with
"Supremo Tribunal Federal". That pattern is unanchored, and rulings and notes
routinely *mention* the STF.

`_find_court_cover()` in `model/metadata.py` requires **both** of these:

1. a stamp `dd/mm/yyyy <ÓRGÃO>` in the first three non-empty paragraphs, where
   the órgão fully matches `decision_body_res`, and
2. a class line matching `decision_class_res` within the first six paragraphs,
   after the stamp.

When it fires, it takes precedence over `_find_epigraph`:

| URN part | Source | Provenance recorded |
|---|---|---|
| number | class line, dots removed (`5.422` → `5422`) | `number_source="cover"` |
| date | the stamp (the judgment date) | `date_source="cover"` |
| authority | `court_res` searched in the front matter, plus `;<órgão>` from the stamp | `authority_source="cover"` |
| type | `acordao;<sigla>`, **only** if an `ACÓRDÃO` heading exists in the front matter (whitespace-insensitive, since `adi_5583` writes `A C Ó R D Ã O`); otherwise the profile's class type | — |

The court slug comes only from the document text. If no court name is found,
the authority stays missing and is reported as such, never guessed.

### Bare `EMENTA` heading (`segment/frontmatter.py`)

`find_ementa`'s unlabelled rule no longer claims a paragraph that is only the
word `EMENTA` (case-, accent-, spacing- and trailing-period-insensitive). A
heading is not a summary, and it stays in the body as a section header. The
labelled `EMENTA: …` rule is unchanged.

## Measured effect

Profile + URN over 249 files (the 234 corpus documents plus the 15 samples,
most of which also appear in the corpus). **Only these three changed:**

| Document | Before | After |
|---|---|---|
| `adi_5422_STF` | `generic` · `urn:lex:br:federal:documento:2022-06-06;0` | `jurisprudencia_generico` · `urn:lex:br:supremo.tribunal.federal;plenario:acordao;adi:2022-06-06;5422` |
| `adi_5583_STF` | `generic` · `urn:lex:br:federal:documento:2021-05-14;0` | `jurisprudencia_generico` · `urn:lex:br:supremo.tribunal.federal;plenario:acordao;adi:2021-05-17;5583` |
| `re_855091_tema_808` | `generic` · `urn:lex:br:federal:documento:2021-03-15;0` | `jurisprudencia_generico` · `urn:lex:br:supremo.tribunal.federal;plenario:acordao;re:2021-03-15;855091` |

`adi_5583`'s date moves from 05-14 to 05-17. The old value was read from the
closing line `Brasília, 7 a 14 de maio de 2021.`, which gives a session *range*.
The new value is the cover's judgment-date stamp `17/05/2021`.

The ementa-heading rule changed the ementa span of exactly two documents:
`adi_5422_STF` and `REsp_1306393` (both the corpus copy and the sample).

Hierarchy, rendered with the command above:

| Document | Before | After |
|---|---|---|
| `adi_5422_STF` | structured 0.60 (`EMENTA`, `ACÓRDÃO`) | structured 0.60 (`EMENTA`, `ACÓRDÃO`) |
| `adi_5583_STF` | flat 0.00 (`all_rejected`) | flat 0.00 (`all_rejected`), unchanged |
| `re_855091_tema_808` | structured 0.90 | structured 0.90 |
| `REsp_1306393` | flat 0.00 | flat 0.00, but without the false `Ementa` block |

All three STF outputs validate against both `lexml-br-rigido.xsd` and
`lexml09-flexivel.xsd` (`--generation=proposed`).

## Tests and goldens (both changes approved by the user before they were made)

- **`REsp_1306393` goldens regenerated** (`scripts/regen_goldens.py
  REsp_1306393`): 5 of 11 kinds changed (`generico`, `generico-aninhado`,
  `generico-linked`, `segment`, `segments`). The diff removes the
  `nome="ementa"` Agrupamento that held only `EMENTA`, and renumbers the ids
  after it. The ground truth in `test_segment_frontmatter.py` now has
  `"ementa": None` for this sample.
- **`test_referee_economics.py`**: `EXPECTED_QUESTIONS`/`EXPECTED_HITS` changed
  from 694/684 to 691/681. With the class lines read as epigraphs, three
  header questions are no longer asked: `adi_5422` p#1, `re_855091` p#1 and
  p#3. All three had been answered `nao`, so no outcome changed.
- **New `tests/unit/test_court_cover.py`** (18 tests):
  - synthetic covers: ADI, RE, ARE-before-RE, ADO-before-ADI, and the
    letter-spaced `ACÓRDÃO` heading
  - no `ACÓRDÃO` heading → the class type is used
  - no court name → no invented authority
  - a stamp without a known órgão is not a cover
  - a class name without a number does not claim the genre
  - the cover is ignored under other profiles
  - the bare-heading ementa rule, and the labelled ementa rule unchanged
  - the three corpus documents (skipped when the corpus is absent)

### Pre-existing failures, not caused by this fix

The corpus folder now holds **234** documents (refreshed 2026-09-15), while the
corpus-233 plan pinned 233. These four tests fail identically on a clean
`HEAD`:

- `test_flatness_causes.py::test_the_corpus_flat_count`
- `test_flatness_causes.py::test_the_corpus_cause_partition`
- `test_flatness_causes.py::test_truncation_is_visible_in_span_coverage`
- `test_referee_economics.py::test_the_referee_now_moves_flatness_86_to_83`

They need a re-pin against the grown corpus, which is outside this fix.

Separately, while `adi_5422_STF.docx` was open in Word, its lock file
`~$i_5422_STF.docx` sat in the corpus folder. Every corpus test that uses
`CORPUS.glob("*.docx")` then **errored** trying to read it. The corpus globs
should probably skip `~$*` files.

## Known limits / follow-ups

- **Stale outputs.** The output file name comes from the URN. Re-running the
  command writes new files (`urn_lex_br_supremo.tribunal.federal_…`) next to
  the old `urn_lex_br_federal_documento_2022-06-06_0.xml`,
  `…_2021-05-14_0.xml` and `…_2021-03-15_0.xml` in `../br-taxqa-r_v2.0/lexml/`.
  Those old files are not deleted automatically.
- **`REsp_1306393` keeps its old URN form**
  (`superior.tribunal.justica:recurso.especial:0000;1306393`). Its cover is an
  STJ layout (`RECURSO ESPECIAL Nº …`, no date/órgão stamp), so the cover
  reader does not fire. Moving STJ acórdãos to
  `superior.tribunal.justica;primeira.secao:acordao;resp:2012-10-24;1306393`
  would need an órgão reader for the "acordam os Ministros da PRIMEIRA SEÇÃO"
  sentence and a date from "Brasília (DF), 24 de outubro de 2012". That would
  move committed goldens, so it was left out.
- **`re_855091_tema_808`'s ementa span** is block 3,
  `TRABALHADORES EM EDUCAÇÃO - CNTE`, which is table text spilling out of the
  cover's party table rather than the ementa. Before the fix, under `generic`,
  the span was block 0 (the stamp), which was also wrong. The real ementa
  follows the `EMENTA` heading. A better rule for court covers would take the
  paragraphs after that heading; that is not implemented.
- `adi_5583_STF` is still flat (`all_rejected`), as before.
