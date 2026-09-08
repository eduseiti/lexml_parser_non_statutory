# External reference URNs: does this parser link cited documents, and what would it take?

- **Date:** 2026-09-08
- **Status:** analysis and proposed cycle. **Nothing implemented.**
- **Trigger:** user question — does the parser built by
  `dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md`
  create the external URN for referenced documents, as the statutory parser
  `../lexml-parser-projeto-lei` does working with `../lexml-linker`?
- **Answer:** **no.** All `urn:lex:` generation is self-identity.
- **Recommendation:** **one new cycle, `8e`**, in the same interstitial slot as
  the referee-configuration amendment, Cycle 8c and Cycle 8d — **before**
  Cycle 9, not inside it. See §8.

---

## 0. The originating prompts (verbatim, for reproducibility)

> I have a question about the parser implemented by the
> "dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md":
> does it create the external URN for referenced documents, just like done by
> the statutory documents parser captured in "../lexml-parser-projeto-lei",
> working with the lexml linker, captured in "../lexml-linker"?

Then, on scheduling:

> Actually, before planning, I just realized cycle 9 has not bee executed. Can
> you confirm that and indicates what is missing?

> If we go for including the URN parser, most probably reusing the lexml-linker
> solution specifically for statutory documents, would that be captured in a
> development cycle before cycle 9, or within cycle 9?

---

## 1. Executive summary

1. **The parser creates no external URNs.** `model/urn.py:173` is the only URN
   builder in the package and its three call sites are all self-identity: the
   document's own `Identificacao/@URN`, its own `!anexoN` fragment, and the
   `ReferenciaAnexo/@AlvoURN` pointer from a document to its own annex.
2. **Citations survive as verbatim source hyperlinks**, not as resolved
   references — `<a xlink:href="http://normas.receita.fazenda.gov.br/…">`,
   never `<Remissao xlink:href="urn:lex:…">`.
3. **The schema already offers the vocabulary and no emitter uses it.**
   `Remissao`, `RemissaoMultipla` and `Alteracao` are legal inline elements in
   both vendored schemas and are never constructed.
4. **The statutory parser does not build these URNs itself either.** It
   delegates entirely to the Haskell `linkertool` binary, spawned as a
   long-lived co-process over stdin/stdout. Remove the linker and it produces
   zero references.
5. **The linker covers statutory norm types only.** It cannot recognise
   portaria, instrução normativa, parecer, ato declaratório or solução de
   consulta, and its `súmula` rule is commented out — i.e. it does not
   recognise the genres this parser exists for. It would resolve citations
   *to statutes* inside our documents, which is most of what they cite, and
   nothing citing a sibling non-statutory act.
6. **This belongs in a cycle before Cycle 9**, because Cycle 9's deliverable is
   to freeze the goldens this work would move.
7. **The linker must be an optional, probed capability**, joining the LLM
   referee and `lexml-proposed/` as the third external thing the repository
   works without. *Decided with the user.*

---

## 2. The answer, measured

### 2.1 One URN builder, three self-identity call sites

`src/lexml_nonstat/model/urn.py` is the only URN construction in the package.
`build_urn()` (`:173`) assembles
`urn:lex:{locality}:{authority}:{doc_type}:{date};{number}[!fragment]` at
`:198`. Its module docstring is explicit that the fragment is the annex
convention of plan §2.9, not a citation mechanism (`:20-22`).

| Call site | What it builds |
|---|---|
| `model/metadata.py:147` (`Metadata.urn`), emitted at `:261` | the document's own `<Metadado><Identificacao URN="…"/>` |
| `model/metadata.py:163` (`urn_with_fragment`) | the document's own annex, `…;277!anexo1` |
| `render/anexo.py:71` (`anexo_urn`), used at `:87` and `:111` | `ReferenciaAnexo/@AlvoURN` — an intra-bundle pointer |

`segments/api.py:194` composes `f"{document_urn}!{node.ident}"`, reading the
document URN back out of `Identificacao/@URN` (`:296-300`) — again the
document's own address plus an internal id.

There is no `link*.py`, no `remissao*.py`, no `citation*.py`, and
`grep -rn "Remissao\|EnumRemissao" src/` returns nothing.

### 2.2 The golden census

`grep -rhoE 'URN="[^"]*"' tests/golden/ | sort -u` yields **16 distinct URNs
across the 15 samples** — one per sample, plus
`urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277!anexo1`. Zero URNs
belong to a referenced document.

### 2.3 What a citation renders as today

Only two golden files contain `xlink:href` at all, and every value is an
`http(s)` URL copied from the source file. From
`tests/golden/generico/sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO.xml:102`:

```xml
<a xlink:href="http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?visao=anotado&amp;idAto=115115">Instrução Normativa RFB nº 2.006/2021</a>
```

That is a citation of IN RFB nº 2.006/2021 carrying the source page's SIJUT
URL. The path is ingestion-only: `ingest/docx_reader.py:309`
(`_hyperlink_target`) and `ingest/html_reader.py:419` fill `Inline.href`
(declared at plan §3.1, `:288`, and captured by amendment A-1.2), and
`render/common.py:157,177` writes it back out. Nothing resolves, normalises or
constructs anything.

### 2.4 The schema offers the vocabulary; no emitter uses it

`lexml/lexml-base.xsd`:

- `:125-129` — group `LXinline` is exactly the reference elements:
  `Remissao`, `RemissaoMultipla`, `Alteracao`, `Formula`. It is referenced from
  `inlineElements` (`:216`), so a `Remissao` is legal anywhere inline content
  is.
- `:760-768` — `Remissao`, `mixed="true"`, extending `inline`, carrying
  `attributeGroup ref="link"`.
- `:252-254` — `link` is `xlink:href`, **required**. A `urn:lex:` would go
  there.
- `:770-777` — `RemissaoMultipla`, requiring `xml:base`.
- `:790-792` — `Alteracao`.
- `EnumRemissao` does **not** exist in either schema.
- `attributeGroup name="linkURN"` (`:260-263`, `URN` + `showAs`) is declared
  and referenced by nothing.

`lexml-proposed/lexml-base.xsd` mirrors this at `:141-144`, `:232`, `:776`,
`:786`. The emitters (`render/generico.py`, `render/generico_aninhado.py`,
`render/norma.py`, `render/anexo.py`, `render/common.py`) construct none of
them.

### 2.5 The near-miss already in the code

`src/lexml_nonstat/hierarchy/quotation.py` already recognises norm
designations, and deliberately stops short of linking them:

- `:266-282` `_NORM_WORD_PATTERNS` — `leis?`, `decretos?(?:[-\s]leis?)?`,
  `medidas? provis[oó]rias?`, `instru[cç][oõ]es? normativas?`, `s[uú]mulas?`,
  `ac[oó]rd[aã]os?`, …
- `:290-299` `_NORM_DESIGNATION_RE` — matches a designation at the start of a
  paragraph: `Lei nº 7.713, de 1988`, `Decreto-lei nº 200, de 1967`.
- `:344-347` states the design:

  > The norm comes back **as written**, never normalised — it becomes a
  > `NomeAgrupador`, and a document's own spelling of a law is the citable fact.

- `:117-118` `_ARTICLE_REFERENCE_RE` matches `art. 3º da Lei` / `nos termos do
  artigo 111`, and is used by `names_external_norm` (`:142-158`) to **reject a
  false heading** — never to build a link.

So the machinery to *spot* a norm designation partially exists (paragraph-
initial only, as a quotation-run head, Cycle 8c's `kind="citacao"` sections),
and its output is plain text. That is the seam a linker would hook into.

### 2.6 Where the idea went in the plan

The only mention of citation→URN anywhere in the repository is in the
*pre-plan* investigation,
`docs/20260801_004745_lexml_non_statutory_parser_investigation_and_development_plan.md:556`,
under "Cycle 9 (optional) — RAG-oriented outputs":

> …hierarchy-aware chunking …, JSON/JSONL export, **citation extraction
> (`Lei nº 12.618, de 2012` → URN, reusing the reference `linker`'s ideas)**.
> Tests: … **citation→URN accuracy**.

It was **cut when the plan was ratified**. The plan's §1 (`:40`) puts RAG
outputs out of scope, and its Cycle 9 (`:1629`) is regression consolidation and
corpus scale-out. `grep -riE "remiss(a|ã|õ|o)"` over `dev/`, `docs/`, `src/`,
`README.md` and `CLAUDE.md` returns nothing but the false positive *premissa*;
`linker` appears twice in `docs/` and never in `dev/` or `src/`.

The linker's other appearance is
`docs/20260801_004745_…:231`, §4.6 "Reference parser (Scala) — what transfers":

> Not to be ported: Pekko actors (**the linker's parallelism** is unnecessary
> at our scale), AbiWord conversion, StringTemplate epigraph templating.

Note what that sentence declines: the *parallelism*, not the linker.

---

## 3. How the statutory parser does it

`../lexml-parser-projeto-lei` (Scala, v1.14.23-SNAPSHOT).

### 3.1 The split — own URN local, referenced URNs entirely delegated

The document's own URN is built in Scala, exactly as we build ours
(`metadado/Metadado.scala:145`):

```scala
lazy val urn: String = s"urn:lex:$urnFragLocalidade:$urnFragAutoridade:$urnFragTipoNorma:${id.map(_.urnRepr).getOrElse("LEXML_URN_ID")}"
```

with the components coming from a `DocumentProfile` (`:142-144`) — the same
design our `profile/base.py:69-71` uses. `urnContextoLinker` (`:146`) is that
same URN, handed to the linker as context.

URNs of **referenced** documents are never assembled by the parser. It only
(a) extracts them from the linker's output (`linker/LinkerActor.scala:85`):

```scala
val links: Set[String] = (r \\ "span").collect({ case (e: Elem) =>
  e.attributes.find(_.prefixedKey == "xlink:href").map(_.value.text) }).flatten.toSet
```

(b) validates them with a regex (`linker/LinkMatcher.scala:17`), (c) ranks
candidates against the ids of dispositivos inside an `Alteracao`
(`LinkMatcher.scala:31-56`, `:207-249`), and (d) copies the winner's base into
`Alteracao.baseURN` (`:98`, `:152`).

`ProjetoLei.scala:256-263` runs `reconheceLinks` after all structural
recognition, only `if (useLinker)`. Without `--linker`, `LinkerActor.receive`'s
`case None` (`:88-90`) returns the input unchanged with an **empty link set**.

### 3.2 The wire protocol

Not HTTP, not a library — a `ProcessBuilder` child process kept alive across
calls (`linker/LinkerActor.scala:29-37`):

```scala
val process = new ProcessBuilder(cmdPath.getCanonicalPath,
      "--hxml","--xml","--contexto=INLINE").start
```

`LinkerActor.scala:63-81` writes the context URN line, then the XML fragment,
then `###LEXML-END###`; reads lines until `###LEXML-END###`; wraps the result
and parses it (`:83`). The Haskell side is `LinkerTool.hs` — `endMarker`,
`readUntilEndMarker`, and the trailing `hPutStrLn outHandle "###LEXML-END###"`.

Configuration is by Java system property, not environment variable:
`lexml.linkertool` (default `/usr/local/bin/linkertool`, `:25`),
`lexml.skiplinker` (`:21`), `linker.numInstances` (8, `Linker.scala:29`),
`linker.timeoutSeconds` (30, `:30`). CLI flag `--linker <file>`
(`fe/FECmdLine.scala:366-369`): *"caminho para o executável do linker. Se
omitido o linker não será usado"*. Default parse context when none is supplied:
`urn:lex:br:federal:lei:2000-01-01;1` (`FECmdLine.scala:114`).

### 3.3 What it emits

Three forms, and notably **not** `<Remissao>` — the string does not appear
anywhere in that repository:

1. **Inline `<span xlink:href="urn:lex:…">` inside `<p>`** — the linker's own
   decoration passed through verbatim. `span` is whitelisted as a preserved
   inline label at `Block.scala:326`; `LexmlRenderer.scala:286-290` renders the
   paragraph's nodes untouched; the `xlink` namespace is declared on the root
   at `:331`.
2. **XML comments per dispositivo** listing the URNs found
   (`LexmlRenderer.scala:260`, `Comment("Link: " + l)`).
3. **`xml:base` on `<Alteracao>` plus a relative `xlink:href` on the altered
   `Dispositivo`** (`LexmlRenderer.scala:222-241`, `:278-283`) — how "this block
   amends article X of that other norm" is expressed.

The repository has no `src/test`, no fixtures and no sample output, so there is
no committed example of the shape.

---

## 4. What `lexml-linker` is, and what it covers

`../lexml-linker`, v1.4.12, upstream `git@github.com:lexml/lexml-linker.git`.
README line 1: *"LexML Linker — Parser de remissões entre normas legislativas"*.

### 4.1 Architecture

**Haskell** (GHC 9.4.7, cabal/stack), ~26 sources, of which roughly 11k lines
are generated municipality and state tables. Two executables and **no library
stanza** (`lexml-parser.cabal:16-18`, `:48-50`): `linkertool` and
`simplelinker`. Pipeline (`LexML/Linker.hs:115-158`): TagSoup parse → Alex
lexer (`Linker/Lexer.x`) → Parsec grammar over the token stream
(`Linker/Parser.hs:48-57`) → `DecorationMap` → either a URN list or decorated
tags.

`Dockerfile` builds `lexmlbr/lexml-linker:<version>` with
`CMD ["/usr/bin/linkertool"]`.

**There is no server.** It was removed in commits `efefb4d` ("Remoção do
servidor do Linker: não é mais usado") and `05afa40`. `LexML/ServerMode.hs`
(port 8909) survives as dead code, imported by nothing. The long-running
co-process with `--contexto=INLINE` and `###LEXML-END###` framing is what
replaced it.

### 4.2 Interface

CLI, via `cmdargs` (`LinkerTool.hs:26-63`): `-f/--frase`, `--entrada`,
`-s/--saida`, `-t/--text | --hxml`, `-u/--urns | --html | -x/--xml`,
`--enderecoresolver`, `--contexto`, plus debug flags.

Output modes:

| Mode | Shape | Source |
|---|---|---|
| `OT_URNS` (`-u`) | newline-separated, sorted, de-duplicated URN strings; **positions discarded** | `Linker.hs:142` |
| `OT_AHREF` (`--html`) | `<a href="https://www.lexml.gov.br/urn/urn:lex:…" class="lexmlurnlink">` | `Decorator.hs:61` |
| `OT_XLINK` (`--xml`) | `<span xlink:href="urn:lex:…">…</span>` — the raw URN | `Decorator.hs:73` |

The internal `DecorationMap` (`Decorator.hs:39`) does carry spans, but no
output mode exposes them; the `--xml` mode is the only one that preserves
position, by wrapping in place. Serialisation of the URN itself is
`URN/Show.hs:22-25`.

README's worked example:

```bash
echo '<p>Os incisos I e III do par. 3o do art. 8o da Lei n.o. 12.527, de 18 de novembro de 2011</p>' \
  | linker --hxml --xml
```

yields the same `<p>` with the matched ranges wrapped in
`<span xlink:href="urn:lex:br:federal:lei:2011-11-18;12527!art8_par3_inc1">`
(and `…inc3`).

### 4.3 Recognised norm types — a short, closed list

No regex and no model: a hand-written Alex lexer plus a Parsec grammar. Top
rule `norma` (`Regras2.hs:641-642`) is *(optional device chain) + (norm
designation)*, and because `combineM` (`ParserBase.hs:235-239`) requires the
right-hand side, **a bare `art. 5º` with no norm is not linked**.

`tipoNorma` (`Regras2.hs:995-1016`) recognises:

| Recognised | Where |
|---|---|
| lei, lei complementar, lei delegada (federal/estadual/municipal/distrital) | `Regras2.hs:947-967` |
| resolução — **only** if the context URN is itself a resolução | `:998-1004`, guard `:985-993` |
| decreto, decreto-lei, decreto legislativo | `:969-983` |
| emenda constitucional | `:1006-1008` |
| medida provisória | `:1013-1015` |
| constituição (federal/estadual, `CF/1988`) | `:658-683`, `:1040-1044` |
| CLT → decreto-lei 5.452/1943 | `:704-716`, `:1026-1035` |
| Código Civil / Código Penal (apelidos) | `:685-702` |
| Regimentos internos, ADCT | `:745-760` |
| STF legacy codes `LEG-FED-LEI-…` | `Linker/RegrasSTF.hs:46-100` |

Device chains (`art`/`cpt`/`par`/`inc`/`ali`/`ite`) build the `!fragment`
(`Regras2.hs:104-165`, `URN/Show.hs:193-208`). Qualifiers cover dates, numbers,
the 27 states (`Linker/Estados.hs`), ~5,561 municípios
(`Linker/Municipios.hs`) and a tiny authority list (`Regras2.hs:923-934`).

### 4.4 What it does not recognise

`portaria`, `instrução normativa`, `parecer`, `ato declaratório`, `circular`,
`solução de consulta`, `despacho`, `aviso`, `ordem de serviço` — a
case-insensitive grep across `src/main/haskell/` finds none of them.

**`súmula` is explicitly disabled** — the rule is commented out at
`Regras2.hs:1009-1012`, while `"súmula"`/`"sumula"` remain in `initialWords`
(`:1135-1136`), so a parse is attempted and always fails.

### 4.5 Relative references are unhandled

There is no rule for *desta Lei*, *deste Decreto*, *do artigo anterior*, *do
mesmo artigo*, *supracitado*, *retro* or *acima*. A grep for all of those over
`src/main/haskell/LexML/` returns exactly one hit, and it is unrelated
(`Regras2.hs:693`, `"Código Civil anterior"`).

What exists instead is the `--contexto` URN, threaded as `lpsContexto`
(`ParserBase.hs:48`). Every rule is a `URNLexML -> URNLexML` transformer
applied to it (`:129-131`), and it supplies **locality and authority defaults
only** (`Atalhos.hs:89-102`, `URN/Utils.hs:48-53`). It never lets a device
chain resolve against the containing document — `o art. 5º desta Lei` produces
nothing, because `norma'` (`Regras2.hs:645-656`) allows only `de|do|da` before
the norm name and then requires a literal norm type.

---

## 5. The coverage gap for non-statutory documents

The linker recognises exactly the genres this parser does **not** handle, and
none of the genres it does. Our six registered profiles are `parecer`,
`ato_declaratorio`, `portaria`, `servico`, `jurisprudencia_generico` and
`generic` (A-2.4); the linker can name none of those as a *referenced* type,
and its `súmula` rule is dead.

That is not a reason to decline it. Non-statutory documents overwhelmingly cite
**statutes** — a parecer reasons about the Lei, the Decreto-lei and the
Constituição — so the linker addresses most of the citation surface. What it
cannot do is link a parecer citing another parecer, or an ato declaratório
citing an instrução normativa, which the corpus also contains.

The measured size of that gap is the input to any later decision about a native
Python recogniser, and measuring it is a deliverable of the cycle proposed
below — not a thing to assume now.

---

## 6. Risks to measure in the cycle's spec phase

1. **Context-URN compatibility — the load-bearing risk.** `--contexto` is
   parsed by `parseURNLexML` (`URN/Parser.hs:22`). Our URNs carry
   `;`-joined authorities (`ministerio.fazenda;secretaria.receita.federal`),
   non-statutory type tokens (`ato.declaratorio`, `sumula`) and, for four
   samples, the `0000` year sentinel A-2.3 introduced. Whether the linker
   accepts them is unknown and must be measured, with the reference parser's
   own default `urn:lex:br:federal:lei:2000-01-01;1` (`FECmdLine.scala:114`)
   as the documented fallback.
2. **Determinism (invariant #4).** The same paragraph must produce the same
   URNs across process restarts and across `--contexto` values we actually use.
3. **Conservation (invariant #2).** A `<Remissao>` wraps existing text and adds
   none, so conservation *should* be untouched — but only if `leaf_texts`
   (`render/common.py:470`), the `segments/` readers and both XSLT stylesheets
   read through it. This is precisely the A-6.4 failure mode: Cycle 6's first
   statutory render was valid on both schemas and **29 words short**.
4. **Nesting inside an existing hyperlink.** The CARNE_LEAO sample has
   citations *inside* source `<a>` elements. `Remissao` extends `inline` and
   `a` sits in the same `inlineElements` choice, so nesting is probably legal
   in both directions — measured on both schemas and both generations before
   the encoding is chosen, per §2.8's method, never argued.
5. **Run splitting.** A citation spans runs; `Inline` is the wrong unit. The
   reference must be a character span over `Para.text`, with `render_inlines`
   (`render/common.py:146`) splitting at span boundaries.
6. **Availability.** `linkertool` is a Haskell binary normally run under
   Docker. A-R.9 requires the suite to stay green against `lexml/` alone, and
   Cycle 9 requires "no network dependency anywhere". The dependency must
   therefore behave like the referee and like `lexml-proposed/`.

---

## 7. Decisions taken with the user (2026-09-08)

1. **A cycle before Cycle 9, not inside it.** Cycle 9's deliverable is to
   *freeze* the suite — promote the 125 goldens to `tests/regression/`, add a
   coverage gate, make a mutation bite. This work moves goldens across up to
   four kinds. §9.4 requires that "a diff always represents a reviewed
   behaviour change"; folding a golden-moving feature into the consolidation
   cycle makes the consolidation diff unreviewable. The precedent is stated
   three times in `STATUS.md:33-35`, where the referee configuration
   amendment, Cycle 8c and Cycle 8d each "**does not begin Cycle 9**".
   Landing it first also lets Cycle 9's 300+ corpus sweep measure citation
   resolution in the same pass rather than needing a second one.
2. **The linker is an optional, probed capability**, never a required runtime
   dependency — the third external thing this repository works without, after
   the LLM referee and `lexml-proposed/`. That is what preserves A-R.9,
   Cycle 9's "no network dependency anywhere", and invariant #4.

---

## 8. Recommended shape of Cycle 8e

Adopted into the plan as **§18, amendments A-L.1 … A-L.7**. Summarised here;
the plan is authoritative.

**New subpackage `src/lexml_nonstat/refs/`**, mirroring `referee/` module for
module:

| Module | Contents | Mirrors |
|---|---|---|
| `protocol.py` | `Reference(start, end, urn, text)`; `Linker` Protocol with `find_refs(text, context_urn)` | `referee/protocol.py` |
| `null.py` | `NullLinker` — no references. **The default everywhere** | `referee/null.py` |
| `linkertool.py` | co-process backend: `--hxml --xml --contexto=INLINE`, `###LEXML-END###` framing, `span/@xlink:href` harvesting | `LinkerActor.scala:31,64-85` |
| `cache.py` | one JSON file per `(context_urn, paragraph text)` hash, `read_only` for fixtures | `referee/cache.py` |
| `probe.py` | `probe_linker() -> LinkerCapabilities(available, diagnostic, version)`; never raises | `validate/schema.py:359` |

**Encoding:** `<Remissao xlink:href="urn:lex:…">texto</Remissao>`, pinned as a
new row in `tests/unit/matrix_cases.py` so the claim is executable on both
schemas and both generations rather than argued from the XSD.

**Resolution happens at render time**, from a `linker=` argument threaded
through the three emitters — not stored on `Para`. Keeping references out of
the model is what leaves the `styled` and `hierarchy` goldens untouched.

**Golden policy:** existing kinds keep `NullLinker`, so **all 125 goldens stay
byte-identical**; two new fixture-backed kinds, `generico-linked` and
`norma-linked`, are added to `scripts/regen_goldens.py`'s `KINDS`. Because the
fixtures carry the answers, the linked goldens compare with no binary present;
only *refreshing* them needs `linkertool`, through an explicit documented
`scripts/record_linker_fixtures.py` — never automatically, per §9.3.

**Three configurations must all be green:** bare checkout (reference
assertions skip with the probe's diagnostic); fixtures only (linked goldens
byte-identical, zero subprocess spawns asserted the way the referee asserts
zero network calls); binary present (recording reproduces every committed
fixture unchanged, proving the recorded answers are live answers).

**The cycle report must state the measured resolution rate per norm type**,
naming what the statutory-only grammar cannot reach (§5).

---

## 9. Cycle 9 status, established in the same session

Confirmed **not started**, from four independent sources: `STATUS.md:30`
(`not started`), `STATUS.md:32` (`… 8, 8c, 8d ✅ → 9`), the absence of any
`*_cycle_9_*` file in the plan's cycle folder, and `README.md:248`.

Deliverables (plan `:1631`):

| # | Deliverable | State |
|---|---|---|
| 1 | Promote all goldens to `tests/regression/` | **Not done.** 125 golden files across 9 kinds remain in `tests/golden/`. `tests/regression/` holds 6 cross-cutting modules written during Cycles 5–8d, not the goldens |
| 2 | `make regression` | **Not done.** There is no `Makefile` |
| 3 | Coverage gate | **Not done.** `pytest-cov` is declared at `pyproject.toml:31` and never used; no `[tool.coverage]`, no `--cov-fail-under`; `addopts` is `-m 'not live'` |
| 4 | Corpus-expansion guide | **Not done** |
| 5 | Batch mode + aggregate decisions report | **Partial.** `decisions-report` takes `nargs="+"` documents and `cli.py:415` reasons about not abandoning a batch on one bad document, but there is no sweep command and no reconciling aggregate |
| 6 | `docs/`/`dev/` conventions documented | **Partial.** `CLAUDE.md` records the layout and the timestamp rule |

Tests (plan `:1634-1640`):

| Criterion | State |
|---|---|
| Full suite green | ✅ 5589 pass / 0 fail / 4 skip / 2 live-deselected as recorded by Cycle 8d. Re-run while writing this record: **5555 passed / 38 skipped / 2 deselected** — the same 5593 total, with 34 extra skips because `saxonche` (the `[xslt]` extra) is absent from this machine. Nothing regressed |
| Coverage ≥ 85 % on `hierarchy/`, `routing/`, `render/` | ❌ never measured |
| Every golden regenerable by one documented command | ✅ in practice (`scripts/regen_goldens.py`, `KINDS` at `:186`); not asserted |
| **A deliberate mutation fails the suite** | ❌ **not committed.** The per-cycle sweeps (15/15, 16/16, 25/25, 62 across three sweeps in Cycle 7) were ad hoc and recorded in the `*_changes.md` files; nothing in `tests/` runs one |
| Batch mode → single reconciling report | ❌ |
| Referee disabled ⇒ green | ✅ pinned suite-wide (§9.3) |
| A-R.9 nested goldens for all 14 | ✅ 16 documents in `tests/golden/generico_aninhado/` |
| A-R.9 cross-emitter equivalence in the regression suite | ✅ `tests/regression/test_cross_emitter.py` |
| A-R.9 mutation test bites on §5.4 Constraints 1/2/3 | ❌ same gap |
| Suite green against `lexml/` alone | ✅ verified in Cycle 8 (A-8.5) |

Open questions Cycle 9 owns, per the 8d report `:200-205` and the plan's §17
close: whether the 8c/8d referee verdicts generalise to the 300+ unseen
documents ("a design argument, not a measurement — **Cycle 9's corpus scale-out
is the thing that will answer it**"); **P-5**, recording live fixtures, for
which 8d created the precedent with 31 `meta.origin`-marked live verdicts; and
LLM-doc §8 questions 1, 3 and 5.

Explicitly **not** Cycle 9: the running-header/footer artifact work
(`docs/20260830_205825_…`), deferred by the user's answer to 8d's Q-4, and this
document's reference-URN work, which is Cycle 8e.

---

## 10. What was verified, and how

Everything above is measured, not recalled. The commands:

```bash
# self-URN only
grep -rn "urn:lex" src/ --include=*.py
grep -rn "Remissao\|EnumRemissao" src/
grep -rhoE 'URN="[^"]*"' tests/golden/ | sort -u          # 16 URNs
grep -rhoE 'xlink:href="[^"]*"' tests/golden/ | sort -u   # all http(s)

# the idea's history
grep -riE "remiss(a|ã|õ|o)" dev/ docs/ src/ README.md CLAUDE.md
grep -rn "linker" dev/ docs/ src/

# schema vocabulary
sed -n '125,129p;250,258p;758,780p' lexml/lexml-base.xsd

# the reference implementations
grep -rn "ProcessBuilder\|LEXML-END\|xlink:href" ../lexml-parser-projeto-lei/src/main/scala/br/gov/lexml/parser/pl/linker/
sed -n '995,1016p' ../lexml-linker/src/main/haskell/LexML/Linker/Regras2.hs
git -C ../lexml-linker log --oneline | grep -i "servidor\|LinkerServer"

# cycle 9
sed -n '1629,1641p' dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md
ls dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser/ | grep cycle_9   # empty
```

The suite was re-run to confirm nothing executable moved:

```bash
python3 -m pytest tests/ -q
# 5555 passed, 38 skipped, 2 deselected in 87.61s
python3 scripts/build_proposed_schemas.py --check
# lexml-proposed/ is current (1 patch(es) applied).
```

**Nothing in `src/`, `tests/` or `scripts/` was modified while producing this
record.** The only changes are this document, plan §12 and §18, `STATUS.md`
and the README's Status paragraph.
