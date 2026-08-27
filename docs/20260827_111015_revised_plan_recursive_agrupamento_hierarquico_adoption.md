# Revised Development Plan — Adopting the LexML Maintainers' Recursive `AgrupamentoHierarquico`

- **Date:** 2026-08-27
- **Status:** Plan revision. Supersedes the routing/emitter sections of `dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md` from Cycle 4 onward; Cycles 0–2 are **already implemented and unaffected**
- **Trigger:** change proposal from the LexML maintainers team, `../atualização_joão_não_articulado/sugestão_mudança.txt`
- **Predecessors:**
  - `docs/20260801_004745_lexml_non_statutory_parser_investigation_and_development_plan.md` — schema investigation, matrix A–R
  - `docs/20260801_142630_design_review_segmentation_statutory_detection_and_lm_support.md` — segmentation proof, statutory detection, LM analysis, §6 recursive `Agrupamento` proposal
  - `dev/20260801_145839_complete_development_plan_lexml_non_statutory_parser.md` — the executing plan (Cycles 0, 1, 2 complete)
- **Evidence in this document is executable.** Every PASS/FAIL below was produced by compiling both schemas offline (`lxml` 5.4.0 / libxml2 2.13.8) and validating real fragments, against an unmodified copy of `lexml/` and against a patched copy carrying the maintainers' edit verbatim.

---

## 0. Originating Prompt (verbatim, for reproducibility)

> Considering the development plan reviewed in @docs/20260801_142630_design_review_segmentation_statutory_detection_and_lm_support.md, analyze the change proposal provided by LexML maintainers team for support hierarchical structures in non-statutory elements, briefly explained in @../atualização_joão_não_articulado/sugestão_mudança.txt.
>
> Evaluate if the proposal achieve what we have been discussing so far and, if so, update the development plan to consider that new LexML definition, taking into consideration the fact that we have already gone through some of the planned development cycles. Capture that plan in a new .md document inside the "docs" folder.

---

## 1. Executive Summary

**Verdict: yes — the proposal achieves what we have been asking for, and it is better than what we proposed.** But it achieves it by a *different route* than our §6 proposal, and that difference changes the emitter design, not just the schema.

Five findings, all empirically established:

1. **The proposal solves the core problem.** `AgrupamentoHierarquico` becomes a genuinely recursive, prose-bearing container. The `pn_cst_38` four-level hierarchy (`2.` → `2.1` → `2.3` → `2.3.1`) validates natively on **both** schemas under the patch, and `ancestor::`/`descendant::` axes recover the hierarchy with no `id`-path parsing (§3.4). This is the requirement from the very first round — *programmatic recoverability of the hierarchy* — met natively rather than by convention.

2. **It is fully backward compatible — verified, not assumed.** All 16 cases of the pinned §2.1 matrix (`tests/unit/matrix_cases.py`) return **identical** verdicts under the current and patched schemas. Nothing that validates today stops validating, and nothing that is correctly rejected today becomes accepted (§3.5).

3. **It supersedes our own §6 proposal, which we should now withdraw.** We proposed making `Agrupamento` recursive via `blocksreq`. The maintainers instead made `AgrupamentoHierarquico` prose-capable. Theirs is the better design: it reuses `hierarchy`, so **`Rotulo` and `NomeAgrupador` become first-class** — which was *secondary observation #1* of our §6.5, resolved for free. Our `<Bloco nome="rotulo">` / `<Bloco nome="nomeAgrupador">` smuggling disappears (§3.3). Notably, `Agrupamento`-in-`Agrupamento` **still fails** under the patch (§3.2) — the maintainers did not adopt our mechanism, and they were right not to.

4. **There is one real constraint the proposal text does not mention, and it will bite the emitter.** Because `AgrupamentoHierarquico` extends `hierarchy`, whose base sequence ends with `AgrupamentoHierarquico*`, XSD's extension model appends the new `choice` **after** the inherited sequence. The consequence: **child subsections must be emitted *before* the parent's own prose.** Natural document order — intro text, then subsections — is **rejected**; `2.`-intro-then-`2.1` does not validate (§3.6). This is a schema wart, not a blocker: the emitter serialises in a canonical order that differs from reading order. §3.7 supplies a one-line refinement to the proposal that removes the wart, which I recommend forwarding to the maintainers.

5. **Cycles 0–2 are unaffected.** The change touches emitters and segmentation — Cycles 5, 6b, 7, and the §11 proposal section. Ingestion, metadata, URN and profiles (all shipped, 788 tests green) need no revision. **No completed work is invalidated.**

**One consequential caveat.** The patched schema is **not yet released**. The maintainers' text says "a mudança que eu devo comitar" — a change they intend to commit. Until it ships in the vendored schemas, `generico-aninhado` cannot be the default: the parser must keep the flat emitter as default and gate the nested one behind a flag and a schema-capability probe (§5.1). This plan therefore adds an emitter and a capability check; it does not replace the existing route.

---

## 2. What the Maintainers Proposed

From `sugestão_mudança.txt`, the change to `lexml-base.xsd`:

```xml
<!-- from -->
<xsd:element name="AgrupamentoHierarquico">
  <xsd:complexType><xsd:complexContent>
    <xsd:extension base="hierarchy">
      <xsd:sequence>
        <xsd:group ref="LXhierCompleto" minOccurs="1" maxOccurs="unbounded"/>
      </xsd:sequence>
      <xsd:attributeGroup ref="nome"/>
    </xsd:extension>
  </xsd:complexContent></xsd:complexType>
</xsd:element>

<!-- to -->
<xsd:element name="AgrupamentoHierarquico">
  <xsd:complexType><xsd:complexContent>
    <xsd:extension base="hierarchy">
      <xsd:choice minOccurs="1" maxOccurs="unbounded">
        <xsd:group ref="LXhierCompleto"/>
        <xsd:element ref="Agrupamento"/>      <!-- ADDED -->
        <xsd:element ref="Bloco"/>            <!-- ADDED -->
      </xsd:choice>
      <xsd:attributeGroup ref="nome"/>
    </xsd:extension>
  </xsd:complexContent></xsd:complexType>
</xsd:element>
```

Two edits: `sequence` → `choice`, and two element references added.

### 2.1 Why this works, structurally

Our §6 analysis concluded "LexML has no element that is simultaneously non-articulated and recursive", and attacked the problem at `blocksreq` (making `Agrupamento` recursive). The maintainers attacked it at the other end, and the reason theirs is better is visible in `lexml-base.xsd:374-383`:

```xml
<xsd:complexType name="hierarchy">
  <xsd:sequence>
    <xsd:element ref="Rotulo"          minOccurs="0" maxOccurs="1"/>
    <xsd:element ref="NomeAgrupador"   minOccurs="0" maxOccurs="1"/>
    <xsd:sequence>
      <xsd:element ref="AgrupamentoHierarquico" minOccurs="0" maxOccurs="unbounded"/>
    </xsd:sequence>
  </xsd:sequence>
  <xsd:attributeGroup ref="corereq"/>
</xsd:complexType>
```

`AgrupamentoHierarquico` **was already recursive** — `hierarchy` admits `AgrupamentoHierarquico*` children. What it lacked was the ability to hold *prose*: `LXhierCompleto` forced every branch to terminate in `Parte|Livro|Titulo|Capitulo|Secao|Subsecao|Artigo`. The maintainers' edit adds `Agrupamento` (a prose block container) and `Bloco` (inline content) to the permitted children. Recursion was never the missing piece — **prose-bearing leaves were**.

And critically, `PartePrincipal` (`lexml-base.xsd:709-718`) *already* accepts `AgrupamentoHierarquico`:

```xml
<xsd:element name="PartePrincipal">
  <xsd:complexType><xsd:choice minOccurs="1" maxOccurs="unbounded">
    <xsd:element ref="AgrupamentoHierarquico"/>   <!-- already there -->
    <xsd:group ref="containerElements"/>
    <xsd:group ref="blockElements"/>
  </xsd:choice>…
```

So the open model reaches the recursive element **with no further change**. This is why the proposal is two lines and not a redesign — and it is why our own §6 proposal, which never noticed this door was already open, was aiming at the wrong wall.

---

## 3. Empirical Evaluation

Method: `lexml/` copied verbatim; the maintainers' edit applied to the copy; both schemas compiled offline through the Cycle 0 stub resolver; fragments validated against both schema sets. `CUR` = current shipped schemas, `PAT` = patched.

### 3.1 The proposal delivers the target structures

| Encoding | CUR rigido | CUR flex | PAT rigido | PAT flex |
|---|---|---|---|---|
| `AH > Agrupamento(p)` — **the proposal's target** | FAIL | FAIL | **PASS** | **PASS** |
| `AH > Bloco` directly | FAIL | FAIL | **PASS** | **PASS** |
| `AH` with **no articulated descendant** | FAIL | FAIL | **PASS** | **PASS** |
| `AH > Agrupamento > nested ol/li` | FAIL | FAIL | **PASS** | **PASS** |
| `AH > Agrupamento > table[@id]` | FAIL | FAIL | **PASS** | **PASS** |
| `Anexo > DocumentoGenerico > AH` nesting | FAIL | FAIL | **PASS** | **PASS** |
| `Norma > Articulacao > AH > Agrupamento` | FAIL | FAIL | **PASS** | **PASS** |
| `AH > Artigo` (statutory, must keep working) | PASS | PASS | **PASS** | **PASS** |

Row 3 is the one that matters most: *"`AgrupamentoHierarquico` without articulated descendant"* is **row F of our pinned matrix** — a documented, load-bearing FAIL that forced the entire flattening design. The patch flips it to PASS. That single row is the whole justification for the workaround, and it is now gone.

### 3.2 What the proposal does *not* change

| Encoding | CUR | PAT |
|---|---|---|
| `Agrupamento` inside `Agrupamento` | FAIL | **FAIL** |
| `div` inside `div` | FAIL | **FAIL** |
| `table/tr/td/p` | FAIL | **FAIL** |
| `Artigo > Agrupamento` | FAIL | **FAIL** |
| `Capitulo > Agrupamento` | FAIL | **FAIL** |

Worth stating plainly: **our §6 proposal was not adopted.** `Agrupamento` remains flat, `blocksreq` is untouched. Recursion is available *only* through `AgrupamentoHierarquico`. Any design of ours that assumed nested `Agrupamento` must be rewritten to use `AgrupamentoHierarquico` as the container and `Agrupamento` as the prose leaf.

The last two rows are a **positive** result: prose cannot leak into `Artigo` or `Capitulo`, so the statutory model keeps its integrity. The change is confined to the aggregator element, which is exactly where it belongs.

`td`-takes-no-`p` (§6.5 secondary observation #2) is untouched and remains worth raising separately.

### 3.3 `Rotulo` and `NomeAgrupador` become first-class

This is the quiet win. Our §6.5 asked for it as a secondary request; the maintainers' route grants it structurally, because `AgrupamentoHierarquico` extends `hierarchy`, which already declares both.

```xml
<!-- today: labels smuggled through Bloco -->
<Agrupamento id="pp1_agr1" nome="secao">
  <Bloco nome="rotulo">2.</Bloco>
  <Bloco nome="nomeAgrupador">DAS SOCIEDADES COOPERATIVAS</Bloco>
  <Bloco nome="nivel">1</Bloco>
  <p>Texto introdutório.</p>
</Agrupamento>

<!-- patched: native, and self-describing -->
<AgrupamentoHierarquico id="pp1_agh1" nome="secao">
  <Rotulo>2.</Rotulo>
  <NomeAgrupador>DAS SOCIEDADES COOPERATIVAS</NomeAgrupador>
  <Agrupamento id="pp1_agh1_txt" nome="texto"><p>Texto introdutório.</p></Agrupamento>
</AgrupamentoHierarquico>
```

Consequences for the plan:

- `<Bloco nome="rotulo">` and `<Bloco nome="nomeAgrupador">` are **retired** in the nested emitter.
- `<Bloco nome="nivel">` is **retired too** — depth is `count(ancestor::AgrupamentoHierarquico)`, so a redundant marker that can disagree with the tree is a liability, not a safeguard.
- Existing community tooling that walks `ancestor::*/NomeAgrupador` — including `scripts/GeraCSVporArtigoPorAgrupador.xsl`, whose breadcrumb logic does exactly this — **now works on non-statutory documents**. That stylesheet's `calculaPos`/breadcrumb machinery was the original motivation of Q1 in the first design review. The maintainers' change closes that loop.

### 3.4 Hierarchy recovers through standard XPath axes

The `pn_cst_38` structure, emitted nested, validated on both patched schemas, then traversed with plain `iterancestors` — no `id` parsing anywhere:

```
depth=1 rotulo=2.      breadcrumb=[]                                                        heading=DAS SOCIEDADES COOPERATIVAS
depth=2 rotulo=2.1     breadcrumb=[DAS SOCIEDADES COOPERATIVAS]                             heading=Empresas de serviços
depth=2 rotulo=2.3     breadcrumb=[DAS SOCIEDADES COOPERATIVAS]                             heading=Operações das Sociedades Cooperativas
depth=3 rotulo=2.3.1   breadcrumb=[DAS SOCIEDADES COOPERATIVAS | Operações das Sociedades…]  heading=Atos Cooperativos
```

Compare with the design review's §2.2 output, which required `starts-with($myid, concat(@id,'_'))` and a `string-length(@id)` sort to reconstruct the same breadcrumbs. **Rule A** (materialise every intermediate `id` prefix) becomes *structurally unnecessary* in the nested emitter — a missing ancestor is now a malformed tree, not a silently broken breadcrumb. It remains required for the flat emitter.

### 3.5 Backward compatibility: all 16 pinned matrix cases

Run against `tests/unit/matrix_cases.py`, the executable form of plan §2.1:

| Row | Encoding | expected | CUR | PAT |
|---|---|---|---|---|
| A | `DocumentoGenerico/PartePrincipal/p` | True | True | True |
| B | `PartePrincipal/Agrupamento[@nome]/p` | True | True | True |
| C | `Agrupamento` inside `Agrupamento` | False | False | False |
| D | `div` inside `div` | False | False | False |
| E | `AgrupamentoHierarquico` containing `p` | False | False | False |
| F | `AgrupamentoHierarquico` without articulated descendant | False | False | False |
| G | sibling `Agrupamento` + `Agrupamento` (flat) | True | True | True |
| H | `PartePrincipal/ol/li` with nested `li/ol` | True | True | True |
| I | `Norma` without `Articulacao` | False | False | False |
| J | `Capitulo/Artigo(Rotulo,Caput)` | True | True | True |
| K | `AgrupamentoHierarquico[@nome]/Artigo(Rotulo,Caput)` | True | True | True |
| L | `ParteInicial + Articulacao + ParteFinal` | True | True | True |
| M | `DocumentoGenerico + Anexos/ReferenciaAnexo` | True | True | True |
| N | `table/tr/td` with inline text | True | True | True |
| O | `table/tr/td/p` | False | False | False |
| P | `Artigo/DispositivoGenerico` | False | False | False |

**Cases whose validity changed: none.** The change is purely additive.

Rows **E** and **F** deserve a note, because they look like they should have flipped and did not:

- **Row E** (`AgrupamentoHierarquico` containing `<p>`) still FAILS — correctly. `<p>` is a `blockElement`, and the proposal adds `Agrupamento` and `Bloco`, **not** `blockElements`. Prose must be wrapped: `AH > Agrupamento > p`. Our emitter must not emit bare `<p>` under an `AH`.
- **Row F** still FAILS **as that case is written**, because our fixture uses `AH` containing only a nested `AH` that itself has no valid content. The `minOccurs="1"` on the extension `choice` means **every `AgrupamentoHierarquico` must contain at least one** `LXhierCompleto | Agrupamento | Bloco`. A purely structural `AH` holding only child `AH`s is **invalid** (§3.6, constraint 2). The §3.1 form of row F — `AH > Agrupamento(p)`, no articulated descendant — does PASS. Both statements are true; they are different documents.

That distinction is a real emitter requirement, not a technicality: **a section with subsections but no text of its own cannot be emitted as a bare container.**

### 3.6 The ordering constraint — the one genuine wart

XSD extension semantics: the effective content model is *base sequence, then extension particle*. So `AgrupamentoHierarquico`'s children must appear as:

```
Rotulo?  NomeAgrupador?  AgrupamentoHierarquico*  (LXhierCompleto | Agrupamento | Bloco)+
   └────── from `hierarchy` (base) ──────┘        └──── from the extension (appended) ────┘
```

Measured consequences:

| Child order | CUR | PAT |
|---|---|---|
| `Rotulo, NomeAgrupador, AH(child), Agrupamento` — **nested-first** | FAIL | **PASS** |
| `Rotulo, NomeAgrupador, Agrupamento, AH(child)` — **natural reading order** | FAIL | **FAIL** |
| `Rotulo, Agrupamento` (leaf section) | FAIL | **PASS** |
| `Rotulo, Bloco, Agrupamento` | FAIL | **PASS** |
| `Rotulo, AH, AH, Agrupamento` | FAIL | **PASS** |
| `Rotulo, AH(child)` only — no own content | FAIL | **FAIL** |

Two binding constraints for the emitter:

> **Constraint 1 — subsections precede own prose.** A section's child `AgrupamentoHierarquico`s must be serialised *before* its own `Agrupamento` prose block. Document order (`2.` intro, then `2.1`) is **not** valid XML under this schema. Serialisation order ≠ reading order, so the emitter must sort, and the segmentation reader must **not** infer reading order from sibling position — it must use `Rotulo` or a recorded source index.

> **Constraint 2 — every `AH` needs at least one non-`AH` child.** `minOccurs="1"` on the extension choice. A section with subsections but no prose of its own must still carry a content child; emit an empty `<Agrupamento nome="texto"/>`… except `Agrupamento` extends `blocksreq`, which is itself `minOccurs="1"`, so an *empty* `Agrupamento` is invalid too. The emitter must therefore either place a `<Bloco>` marker or hoist a child. **This is a design decision for Cycle 5b, flagged in §5.4.**

Constraint 1 is the more damaging of the two, because it makes the XML's document order stop matching the source document's order — the one property that makes hand-inspection of output trustworthy.

### 3.7 A one-line refinement that removes the wart — recommended for forwarding

Moving the recursion from the base into the extension choice makes children order-free. Tested and verified:

```xml
<!-- lexml-base.xsd: hierarchy — drop the trailing AH sequence -->
<xsd:complexType name="hierarchy">
  <xsd:sequence>
    <xsd:element ref="Rotulo"        minOccurs="0" maxOccurs="1"/>
    <xsd:element ref="NomeAgrupador" minOccurs="0" maxOccurs="1"/>
  </xsd:sequence>                              <!-- AH* removed from here -->
  <xsd:attributeGroup ref="corereq"/>
</xsd:complexType>

<!-- AgrupamentoHierarquico — AH joins the choice -->
<xsd:choice minOccurs="1" maxOccurs="unbounded">
  <xsd:group   ref="LXhierCompleto"/>
  <xsd:element ref="AgrupamentoHierarquico"/>  <!-- moved here -->
  <xsd:element ref="Agrupamento"/>
  <xsd:element ref="Bloco"/>
</xsd:choice>
```

| Case | CUR | maintainers' PAT | REFINED |
|---|---|---|---|
| prose-first: `Rotulo, Agrupamento, AH` (**natural order**) | FAIL | FAIL | **PASS** |
| nested-first: `Rotulo, AH, Agrupamento` | FAIL | PASS | **PASS** |
| all 16 pinned matrix cases | — | unchanged | **unchanged** |

The refinement is also fully backward compatible across the matrix. It lets sections interleave prose and subsections in true document order — which, as the design review §6.4 already argued, "is the natural document order (`2.` intro text, then `2.1`)".

**Caveat to state honestly when forwarding:** `hierarchy` is the base type of *all* statutory aggregators (`Parte`, `Livro`, `Titulo`, `Capitulo`, `Secao`, `Subsecao`), so editing it has a wider blast radius than editing `AgrupamentoHierarquico` alone. Those elements override the content model in their own extensions, and the 16-case matrix shows no change — but the maintainers own that judgement, and a narrower alternative exists: leave `hierarchy` alone and accept the ordering constraint. **Our parser works either way** (§5.4); this is an ergonomics improvement to offer, not a blocker to insist on.

---

## 4. Impact on Work Already Completed

| Cycle | State | Impact |
|---|---|---|
| 0 — scaffolding, dual-schema harness | complete, 107 tests | **Additive only.** Matrix gains rows; harness gains a capability probe (§5.2) |
| 1 — DOCX → `StyledDoc` | complete, 373 tests | **None.** Ingestion is schema-independent |
| 2 — metadata, URN, profiles | complete, 788 tests | **None.** `<Metadado>` is untouched by the proposal |
| 3 — front/back matter | not started | **None** |
| 4 — hierarchy inference | not started | **None.** The internal `Section` tree was always a real tree — this is the payoff §11 predicted |
| 4b — routing, referee, telemetry | not started | **Minor.** One new blocker reason; route set unchanged |
| 5 — emitter `generico` | not started | **Unchanged.** Stays the default while the patch is unreleased |
| **5b — emitter `generico-aninhado`** | **new** | The nested emitter (§5.3) |
| 6 — emitter `norma` + `Anexo` | not started | **Minor.** Annex bodies may use the nested form when available |
| 6b — `articulado-sintetico` | not started | **Reduced in importance** (§5.5) — possibly droppable |
| 7 — segmentation output | not started | **Extended.** A native-axis reader joins the id-path reader |
| 8 — CLI | not started | **Minor.** `--emitter` gains a value; capability reporting |
| 9 — regression | not started | **Extended.** Nested goldens; cross-emitter equivalence |

**Nothing implemented is invalidated.** The internal model (`plan §3.1`) is rendering-agnostic by construction, and §11 of the plan predicted this exact outcome: *"a schema improvement costs us one emitter, not a rewrite."* That prediction now holds — with the correction that the emitter targets `AgrupamentoHierarquico`, not the recursive `Agrupamento` we had assumed.

---

## 5. Revised Plan

### 5.1 Governing principle: capability-gated, not schema-forked

The patch is **proposed, not released**. The parser must therefore:

1. Keep `generico` (flat) as the **default** emitter — it validates against the schemas as shipped.
2. Ship `generico-aninhado` as an **opt-in** emitter, selected by `--emitter=generico-aninhado`.
3. **Probe the vendored schemas at startup** for recursion support, rather than hard-coding a version assumption. When the probe says the schemas are flat and the nested emitter is requested, fail with a clear diagnostic naming the missing capability.
4. Flip the default to nested **only** once the change is released and `lexml/*.xsd` is re-vendored — a one-line default change, plus a golden regeneration, gated on the probe.

This keeps the repository honest against whichever schemas are actually vendored, and makes the eventual switch a reviewed diff rather than a rewrite.

### 5.2 Cycle 0 addendum — schema capability probe

Add to `validate/schema.py`:

```python
@dataclass(frozen=True)
class SchemaCapabilities:
    """What the *vendored* schemas actually permit, discovered by probing."""
    recursive_agrupamento_hierarquico: bool   # AH > Agrupamento(p) validates
    prose_bearing_hierarchy: bool             # AH with no articulated descendant
    native_rotulo_nome_agrupador: bool        # Rotulo/NomeAgrupador usable on AH
    interleaved_children: bool                # prose-first order accepted (§3.7)

def probe_capabilities(selector: str = "both") -> SchemaCapabilities:
    """Validate canary fragments to discover schema capabilities.

    Never hard-code a schema version: the vendored files are the truth.
    """
```

Tests
- against the **currently vendored** schemas, all four capabilities are `False` — pinning today's reality
- against a **patched fixture copy** (committed under `tests/fixtures/schemas/`), the first three are `True` and `interleaved_children` is `False`
- against a **refined fixture copy** (§3.7), all four are `True`
- the probe never mutates `lexml/`, and runs offline through the existing resolver
- a capability regression (probe result changing unexpectedly) fails loudly

Extend `tests/unit/matrix_cases.py` with the §3.1 and §3.6 rows, each carrying the capability it depends on, so the matrix stays the single executable statement of what the schemas permit.

> **Amendment A-0.2 (proposed).** The §2.1 matrix is no longer a table of absolute truths — it is a table *conditional on the vendored schema generation*. Cases gain a `requires` field naming the capability; cases needing an unavailable capability are skipped with a reason, not failed.

### 5.3 New Cycle 5b — Emitter `generico-aninhado`

Runs after Cycle 5, reusing its `Section` tree and id scheme.

`render/generico_aninhado.py`:

- `Section` → `<AgrupamentoHierarquico id nome>` with native `<Rotulo>` and `<NomeAgrupador>`
- prose/lists/tables → a single `<Agrupamento nome="texto">` leaf per section (**row E: never bare `<p>` under an `AH`**)
- **child sections emitted before the section's own prose leaf** (Constraint 1), with source order preserved in `Rotulo` and, where a document has unlabelled sections, an explicit `<Bloco nome="ordem">` index
- **Constraint 2 discharged** per §5.4
- ids remain path-composed (`pp1_agh1_agh2_agh1`) — redundant with the nesting, but keeps URN fragments stable and identical across both emitters, so a segment URN means the same thing whichever emitter produced it
- `<Bloco nome="nivel">` **not** emitted — depth is `count(ancestor::AgrupamentoHierarquico)`

Tests
- all 14 `generico`-routed samples validate on **both** patched schemas (skipped when the probe reports flat schemas)
- **native-axis reconstruction:** tree recovered via `ancestor::`/`descendant::` alone equals the tree recovered from `id` paths, for all 14
- `Rotulo`/`NomeAgrupador` native; **no `Bloco nome="rotulo"|"nomeAgrupador"|"nivel"` anywhere** in the output
- **row E regression:** no bare `<p>` is ever a child of `AgrupamentoHierarquico`
- **Constraint 1 regression:** for every `AH`, no `Agrupamento` sibling precedes an `AgrupamentoHierarquico` sibling
- **Constraint 2 regression:** every `AH` has ≥1 non-`AH` child
- **cross-emitter text equivalence:** `generico` and `generico-aninhado` carry byte-identical text content, and identical segment URNs
- `id` uniqueness; conservation (every source paragraph exactly once)
- Rule A is *asserted unnecessary*: a deliberately gapped tree is structurally impossible to emit
- goldens committed for all 14

Exit: nested output validates on both patched schemas; hierarchy recoverable by standard axes; text and URNs identical to the flat emitter.

### 5.4 The Constraint 2 decision (§3.6)

A section with subsections but no prose of its own needs ≥1 non-`AH` child, and an empty `<Agrupamento/>` is itself invalid (`blocksreq` is `minOccurs="1"`). Three options, to decide at Cycle 5b:

| Option | Shape | Cost |
|---|---|---|
| **A — empty-prose marker** (recommended) | `<Bloco nome="vazio"/>` — `Bloco` extends `inline`, `minOccurs="0"`, so genuinely empty is valid | one synthetic element per bare section; explicit and greppable |
| B — `Agrupamento` with empty `<p/>` | `<Agrupamento nome="texto"><p/></Agrupamento>` | injects an empty paragraph into text extraction; risks the conservation invariant |
| C — push the refinement upstream | ask for `minOccurs="0"` on the extension choice | correct, but blocks on the maintainers |

Recommend **A**, verified valid, with a test that the marker is invisible to text extraction and to segmentation. Worth raising C alongside §3.7 when forwarding — `minOccurs="0"` there is as small an edit as the ordering fix, and removes the need for any synthetic element.

### 5.5 Cycle 6b — `articulado-sintetico` reconsidered

Its entire justification was: *"some consumers need real nesting, and the only way to get it is to synthesise fake `Artigo`s."* With the patch, real nesting is available **without asserting articulation the source lacks** — which was always the emitter's semantic sin (§6.3, cost 4: *"semantically false for a parecer"*).

Recommendation: **fold Cycle 6b into 5b and drop the synthetic emitter**, subject to the release caveat. Keep it only if a consumer is known to require `Artigo`-shaped output specifically. This removes an emitter, its goldens, and the provenance-marking machinery that stopped synthetic articles being mistaken for real ones.

The **round-trip reader** from 6b is retained and moves to Cycle 7 — it is the oracle for every emitter and is more valuable now, not less.

### 5.6 Cycle 7 — segmentation, extended

`segmentation/api.py` gains a second reader:

- `segments_from_flat_xml()` — existing `id`-path reconstruction (Rules A/B)
- `segments_from_nested_xml()` — native `ancestor::`/`descendant::`; **Rule A is structurally guaranteed**, Rule B still applies (leaf-only text: nested `ol`/`li` duplication is a list problem, unaffected by the schema change)
- both must agree with segmentation from the in-process model — three-way oracle agreement

`xslt/segment_generico_aninhado.xsl`: with native `Rotulo`/`NomeAgrupador` and real ancestry, this is close to the community's existing `GeraCSVporArtigoPorAgrupador.xsl` idiom. **Worth testing whether that stylesheet runs unmodified** on nested output — if it does, that is the strongest possible argument for the proposal, and belongs in the reply to the maintainers.

Tests
- three-way agreement (model / flat XML / nested XML) on all 15 samples
- breadcrumbs complete via native axes, no `id` parsing
- segment URNs identical across emitters
- `GeraCSVporArtigoPorAgrupador.xsl` compatibility probed and its result recorded (informational, not gating)

### 5.7 Cycles 4b, 6, 8, 9 — minor amendments

- **4b:** add blocker reason `nested_unavailable` when `generico-aninhado` is requested against flat schemas. Routing decisions are **unchanged** — the §4.4 route table stands, since routing is about *what the document is*, not how it is rendered.
- **6:** annex bodies (`Anexo > DocumentoGenerico > PartePrincipal`) may use the nested form — verified PASS (§3.1). `port_mf_277`'s 130-entry `ANEXO ÚNICO` gains real structure.
- **8:** `--emitter` accepts `generico-aninhado`; a `capabilities` CLI command reports what the vendored schemas permit; requesting an unavailable emitter exits cleanly with the probe's diagnostic.
- **9:** nested goldens for all 14; cross-emitter equivalence in the regression suite; the mutation test covers the nested emitter's Constraint 1/2 invariants.

### 5.8 Revised cycle order

```
0, 1, 2  ✅ complete
3, 4, 4b, 5, 5b(new), 6, 7, 8, 9
                   └── 6b folded into 5b (§5.5), round-trip reader → 7
```

| Cycle | Deliverable | Key exit criterion |
|---|---|---|
| 0 ✅ | scaffolding, dual-schema harness | §2.1 matrix green — **+ capability probe (§5.2)** |
| 1 ✅ | DOCX → `StyledDoc` | 15 samples ingest losslessly |
| 2 ✅ | metadata, URN, profiles | correct URN/metadata for all samples |
| 3 | front/back matter | zero false positives on bare documents |
| 4 | hierarchy inference + quotation guard | 21 quoted articles in `parecer_93` rejected |
| 4b | routing + referee + telemetry | routes match §4.4; overrides logged |
| 5 | emitter `generico` (flat, **default**) | 14 samples valid on shipped schemas; Rules A/B |
| **5b** | **emitter `generico-aninhado`** | **native axes recover hierarchy; text ≡ flat emitter** |
| 6 | emitter `norma` + `Anexo` | `port_mf_277` split, conservation across both |
| 7 | segmentation output | three-way oracle agreement |
| 8 | robustness + CLI | degenerate inputs handled; capabilities reported |
| 9 | regression + batch | mutation test bites; corpus report reconciles |

---

## 6. Revised §11 — What to Send Back to the Maintainers

Our §6/§11 proposal (recursive `Agrupamento` via `blocksreq`) should be **withdrawn in favour of theirs**. The reply should say so plainly, and add value rather than restating the problem:

1. **Endorse it, with evidence.** Their change makes `pn_cst_38_19801031`'s four-level hierarchy natively representable, validated on both `lexml-br-rigido.xsd` and `lexml09-flexivel.xsd`. All 16 cases of our pinned encoding matrix are unchanged: the edit is strictly additive.

2. **Confirm the ergonomic win they may not have set out to make.** Because `AgrupamentoHierarquico` extends `hierarchy`, `Rotulo` and `NomeAgrupador` become available to non-articulated documents. This was a separate request in our earlier draft, and their route grants it for free. Existing breadcrumb tooling that walks `ancestor::*/NomeAgrupador` becomes applicable to non-statutory documents.

3. **Report the ordering constraint (§3.6) as a usability finding.** Under the proposal as written, a section's subsections must be serialised *before* its own prose, so XML order stops matching reading order. Offer the §3.7 refinement — moving `AgrupamentoHierarquico` from the `hierarchy` base into the extension `choice` — noting it is verified backward compatible across the same 16 cases, and noting honestly that it touches a type shared by all statutory aggregators.

4. **Raise `minOccurs`** (§5.4 option C): the extension `choice` at `minOccurs="1"` makes a subsections-only section invalid, forcing a synthetic child. `minOccurs="0"` would remove that.

5. **Re-raise the two carried-over observations:** `<td>` accepts inline content but not `<p>`, unlike every other block container; and `<p>` is still not permitted directly under `AgrupamentoHierarquico` (row E), so prose always needs an `Agrupamento` wrapper — worth confirming that is intentional.

6. **Ask the release question.** Which schema version will carry the change, and will `lexml09-flexivel.xsd`/`lexml-br-rigido.xsd` be re-issued together? Our capability probe (§5.2) is designed so the parser adapts automatically, but the vendoring step needs a version to pin.

7. **Offer the corpus.** `pn_cst_38_19801031` and `port_mf_454_19770825` are public-domain motivating examples, and our validation harness reproduces every claim above offline.

---

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Change is never released, or ships altered | medium | flat emitter stays default; capability probe reads the vendored schemas, never a hard-coded version; nested emitter is purely additive |
| Ordering constraint makes XML order ≠ reading order | medium | canonical emit order + `Rotulo`/explicit order index; segmentation never infers order from sibling position; §3.7 refinement offered upstream |
| Constraint 2 forces a synthetic child element | low | §5.4 option A (`<Bloco nome="vazio"/>`), verified valid, tested invisible to text extraction |
| Two emitters diverge in content | medium | cross-emitter text-and-URN equivalence test in Cycle 5b and the Cycle 9 regression suite |
| Nested output breaks consumers expecting flat | low | flat emitter retained indefinitely; both validate; `--emitter` selects |
| Capability probe drifts from reality | low | probe runs against real vendored files each session; the matrix pins expected results and fails loudly on change |
| Our §6 proposal already circulated, causing confusion | low | withdraw explicitly in the reply (§6.1) |

---

## 8. Answer in Brief

**Does the proposal achieve what we have been discussing?** Yes — and by a cleaner route than we proposed.

- It makes non-articulated hierarchy **natively representable and natively traversable**: `ancestor::`/`descendant::` work, breadcrumbs work, existing `NomeAgrupador` tooling applies. That was the requirement from round one.
- It grants `Rotulo`/`NomeAgrupador` to non-articulated documents as a side effect, retiring our `<Bloco nome="rotulo">` workaround — a separate request of ours, resolved for free.
- It is **verified backward compatible**: 16/16 pinned matrix cases unchanged.
- It **supersedes our own §6 proposal**, which should be withdrawn: `Agrupamento` stays flat, and recursion lives in `AgrupamentoHierarquico` instead.
- It carries **one wart** — subsections must be serialised before a section's own prose — which the emitter can absorb, and which a small, tested refinement (§3.7) would remove.
- **Nothing already built is invalidated.** Cycles 0–2 stand untouched at 788 green tests; the change costs **one new emitter (5b)** and probably *removes* one (6b), exactly as the rendering-agnostic model was designed to allow.

The one thing to be careful about: the change is **proposed, not released**. Until it ships, `generico-aninhado` must remain opt-in behind a schema capability probe, with the flat emitter as default.
