"""The committed mutation harness — plan §8 Cycle 9, amendment **A-R.9**.

Cycle 9's test list asks for "**a deliberate mutation fails the suite** (proving
the tests bite)", and A-R.9 sharpens it: the mutation test must bite on the §5.4
Constraint 1/2/3 invariants specifically. This module is that, as standing code
rather than as a sweep someone ran once (spec decision **N-1**).

What a green run here actually claims
-------------------------------------

Not "the parser is correct" — no test says that. It says: for each of ten
delivered behaviours, **the assertion that defends it is still present and still
sensitive**. That is a claim about the *test suite*, and it is the only claim a
5923-test suite cannot make about itself by passing. A suite whose conservation
check had rotted into `assert True` would stay green forever; it would fail here,
under M-4, naming conservation.

The distinction matters because the corpus is 15 samples standing in for 300+
unseen documents. Every guard in this repository is a bet that a property
measured on fifteen files holds on three hundred, and a guard that has silently
stopped measuring anything is the most expensive possible way to lose that bet:
it costs nothing today and everything at scale.

Why the mutations are in-process — decision **N-2**
---------------------------------------------------

None of these touch a file. Each rebinds one attribute on an imported module and
restores it in a `finally` (see :mod:`.mutation_harness`). A harness that edited
`src/` and then crashed would leave the tree corrupt in a way that reads as
authored code, and Cycle 2's incident record is why that is treated as a hard
constraint rather than a preference. :func:`test_no_mutation_leaks` measures the
outcome rather than trusting the intent.

Reading a failure here
----------------------

* ``test_every_mutation_is_caught[M-n] failed: M-n SURVIVED`` — the suite has a
  **gap**. The mutation's ``attacks`` field names the unguarded invariant. This
  is a finding to report, not a mutation to delete: the harness has done exactly
  its job, and deleting the mutation would be deleting the evidence.
* ``test_the_harness_itself_is_not_vacuous`` failed — the harness reports
  "caught" for a no-op, so **every other verdict in this module is worthless**.
  Fix this before believing anything else here.
* ``test_no_mutation_leaks`` failed — a mutation escaped its `finally` and is
  live in the interpreter. Every test that ran after it is suspect.

The ten mutations, and what each one is really asking
-----------------------------------------------------

M-1, M-2 and M-3 are A-R.9's three, and all three ask the same question of
§5.4's constraints: *are these actually enforced by the schema, or do we merely
believe they are?* They are the only ones gated on ``requires_nested``, because
each asserts **invalidity against `lexml-proposed/`** and a checkout without that
generation cannot judge it. The harness and M-4…M-10 run everywhere, which is
what keeps A-R.9's "green against `lexml/` alone" true of this module too.
"""

from __future__ import annotations

import contextlib
import importlib
import re
from collections import Counter
from pathlib import Path

import pytest

import lexml_nonstat.refs.linkertool as linkertool_module
import lexml_nonstat.render.generico as generico_module
import lexml_nonstat.render.generico_aninhado as nested_module

#: The adjudication **module**, reached through `importlib` rather than by
#: `import lexml_nonstat.referee.adjudicate as …`.
#:
#: `referee/__init__.py` does `from .adjudicate import adjudicate`, which binds
#: the *function* to that attribute of the package and shadows the submodule of
#: the same name. The plain import statement therefore yields a function object,
#: and patching an attribute on it raises `AttributeError` — which the harness
#: reports as a caught mutation, making M-8 look defended when it never ran.
#: `import_module` resolves the real module regardless of the shadow.
adjudicate_module = importlib.import_module("lexml_nonstat.referee.adjudicate")
from lexml_nonstat.ingest import StyledDoc, StyledPara, StyledTable, read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.referee.protocol import (
    RULE_HIGH_CONFIDENCE,
    Verdict,
)
from lexml_nonstat.render import (
    EMPTY_BLOCO,
    ORDER_BLOCO,
    local_name,
    missing_prefixes,
    render_generico,
    render_generico_aninhado,
    words,
)
from lexml_nonstat.segments import segments
from lexml_nonstat.validate import validate
from lexml_nonstat.validate.schema import PROPOSED

from tests.conftest import fixture_linker, requires_nested
from tests.regression.mutation_harness import Mutation, guard_fails, patched

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "generico"

LEX = "{http://www.lexml.gov.br/1.0}"

#: The carrier document for every mutation that needs real structure.
#:
#: Chosen by measurement, not convenience. `pn_cst_38` is the only sample that
#: carries all three nested shapes at once: **35** `AgrupamentoHierarquico`, **5**
#: `Bloco nome="vazio"` fillers, and **4** sections having *both* subsections and
#: their own prose. That last count is what makes M-1 non-vacuous — Constraint 1
#: only bites where a section has both — and the `vazio` count is what makes M-2
#: non-vacuous. `par_cosit_26`, the obvious alternative, emits **zero** `vazio`
#: markers, so M-2 against it would drop nothing and be reported as a surviving
#: mutation for a reason that had nothing to do with the invariant.
CARRIER = "pn_cst_38_19801031"

#: A sample the fixture linker resolves many references in — M-10's carrier.
#: `parecer_93` resolves 132, so a harvest that returns nothing is unmissable.
CITING = "parecer_93_2018_decor_cgu_agu"

_MODELS: dict[str, object] = {}


def model(name: str):
    """One built model per sample, cached. Building is the slow step."""
    if name not in _MODELS:
        _MODELS[name] = build_model(
            read_docx(SAMPLES_DIR / f"{name}.docx"), filename=f"{name}.docx"
        )
    return _MODELS[name]


def source_words(name: str) -> Counter:
    """The source's word multiset — deliberately the same extraction the
    conservation module uses, so M-4 and M-5 attack the real currency.

    Copied rather than imported from `test_conservation_generico`, following
    that module's own stated reasoning about `test_cross_emitter`: two modules
    reaching the same measurement independently is worth more than one module
    asserting it twice, and a shared copy quietly changing both claims at once
    would be worse than a divergence.
    """
    doc: StyledDoc = read_docx(SAMPLES_DIR / f"{name}.docx")
    out: list[str] = []
    for block in doc.blocks:
        if isinstance(block, StyledPara):
            if block.text.strip():
                out.append(block.text)
        elif isinstance(block, StyledTable):
            for row in block.rows:
                for cell in row.cells:
                    for para in cell.paras:
                        if para.text.strip():
                            out.append(para.text)
    return Counter(words(out))


# ===========================================================================
# The guards — each one calls the REAL library and asserts a REAL invariant
# ===========================================================================
#
# Nothing below re-implements a check. Each guard is the narrowest existing
# assertion that ought to reject its mutation, lifted so it can be run against
# one document instead of against the whole corpus. The spec is explicit that
# running the full 5923-test suite per mutation would take hours; running the
# *specific* guard is both faster and a sharper claim, because a mutation caught
# by its named guard proves that guard works, while a mutation caught by "some
# test somewhere" proves much less.


def guard_nested_validity() -> None:
    """§5.4's constraints are schema facts — so the schema must reject a breach.

    The guard for M-1, M-2 and M-3. All three mutations produce output that is
    *well-formed* and looks plausible; only `lexml-proposed/` can say it is
    illegal, which is precisely why the three are gated on `requires_nested`.
    """
    bundle = render_generico_aninhado(model(CARRIER))
    for document in bundle.documents:
        report = validate(document, "both", generation=PROPOSED)
        assert report.ok, (
            f"{CARRIER}: nested render is invalid against the proposed "
            f"schemas\n{report.summary()}"
        )


def guard_constraint_1_order() -> None:
    """No non-`AH` child may precede an `AgrupamentoHierarquico` sibling.

    Constraint 1 as the plan states it (§5.4, widened by **A-5b.1** to bind
    `Bloco` as well as prose). Asserted structurally as well as by the schema
    because the structural form names the *offending element*, which a schema
    error message does not.
    """
    bundle = render_generico_aninhado(model(CARRIER))
    for document in bundle.documents:
        for node in document.iter(f"{LEX}AgrupamentoHierarquico"):
            seen_other = None
            for child in node:
                tag = local_name(child.tag)
                if tag in ("Rotulo", "NomeAgrupador"):
                    continue
                if tag == "AgrupamentoHierarquico":
                    assert seen_other is None, (
                        f"{CARRIER}: in {node.get('id')!r} a {seen_other!r} "
                        "precedes an AgrupamentoHierarquico — §5.4 Constraint 1 "
                        "requires subsections first (A-5b.1)"
                    )
                elif seen_other is None:
                    seen_other = tag


def guard_constraint_2_filler() -> None:
    """Every `AgrupamentoHierarquico` carries at least one non-`AH` child.

    Constraint 2's `minOccurs="1"`. A section with subsections but no prose of
    its own needs the `<Bloco nome="vazio"/>` filler, and this is what notices
    when the filler stops being emitted.
    """
    bundle = render_generico_aninhado(model(CARRIER))
    for document in bundle.documents:
        for node in document.iter(f"{LEX}AgrupamentoHierarquico"):
            others = [
                local_name(c.tag)
                for c in node
                if local_name(c.tag) not in ("AgrupamentoHierarquico",)
            ]
            assert others, (
                f"{CARRIER}: {node.get('id')!r} has only AgrupamentoHierarquico "
                "children — §5.4 Constraint 2 requires at least one other"
            )


def guard_constraint_3_wrapper() -> None:
    """Prose never sits directly inside an `AgrupamentoHierarquico`.

    Constraint 3, restated from §5.2: a `<p>` needs an `Agrupamento` wrapper.
    It is a schema fact, and §5.4 says it "gets its own regression" — this is it.
    """
    bundle = render_generico_aninhado(model(CARRIER))
    for document in bundle.documents:
        for node in document.iter(f"{LEX}AgrupamentoHierarquico"):
            bare = [local_name(c.tag) for c in node if local_name(c.tag) == "p"]
            assert not bare, (
                f"{CARRIER}: {node.get('id')!r} carries a bare <p> — §5.4 "
                "Constraint 3 requires an Agrupamento wrapper around prose"
            )


def guard_conservation() -> None:
    """Invariant #2 — every source word emitted exactly once.

    Equality of multisets, which is simultaneously "nothing lost" and "nothing
    duplicated". M-4 attacks the loss half and M-5 the duplication half, and the
    same assertion catches both, which is the point of stating it as equality.
    """
    bundle = render_generico(model(CARRIER))
    emitted = Counter(words(bundle.texts))
    source = source_words(CARRIER)
    lost = source - emitted
    extra = emitted - source
    assert emitted == source, (
        f"{CARRIER}: {sum(lost.values())} word(s) lost, "
        f"{sum(extra.values())} emitted without a source"
    )


def guard_id_uniqueness() -> None:
    """Invariant #5 — `xsd:ID` uniqueness, per document and across the bundle.

    Both halves, for the golden modules' own reason: `xsd:ID` scopes to a
    document, but a citation names a document *and* a fragment, so a fragment
    meaning two things in one bundle is a citation that cannot be resolved.
    """
    bundle = render_generico(model(CARRIER))
    seen: list[str] = []
    for document in bundle.documents:
        ids = [v for n in document.iter() if (v := n.get("id")) is not None]
        duplicates = [i for i, n in Counter(ids).items() if n > 1]
        assert not duplicates, f"{CARRIER}: repeated ids {duplicates[:5]}"
        seen.extend(ids)
    across = [i for i, n in Counter(seen).items() if n > 1]
    assert not across, f"{CARRIER}: ids shared between documents: {across[:5]}"


def guard_rule_a() -> None:
    """Invariant #6 — every proper prefix of an id path exists (Rule A).

    The flat emitter's reversibility depends on it: `pp1_agr1_agr2_agr1` with no
    `pp1_agr1_agr2` yields a breadcrumb silently missing its middle ancestor,
    which is the exact defect §2.4's segmentation experiment surfaced.
    `missing_prefixes` is the library's own checker, called here rather than
    reimplemented.
    """
    bundle = render_generico(model(CARRIER))
    for document in bundle.documents:
        parte = next(
            (n for n in document.iter() if local_name(n.tag) == "PartePrincipal"),
            None,
        )
        if parte is None:
            continue
        root = parte.get("id") or "pp1"
        ids = [v for n in parte.iter() if (v := n.get("id")) is not None]
        gaps = missing_prefixes(ids, root=root)
        assert gaps == (), f"{CARRIER}: Rule A gaps {gaps}"


def guard_referee_is_advisory() -> None:
    """Invariant #9 — a high-confidence rule can never be overridden.

    §7.3 constraint 4, written as a number in `RULE_HIGH_CONFIDENCE`. The
    referee here is deliberately maximally confident and maximally wrong: if the
    guarantee holds, a 0.99 referee still loses to a 0.80 rule. Measured across
    the band rather than at one point, because an off-by-one in the comparison
    would pass a single-point check.

    No network: the double answers in-process, which is also §9.3's rule for the
    whole suite.
    """

    class _Contrarian:
        name = "contrarian"
        enabled = True
        last_cache_hit = False

        def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
            return Verdict("own", 0.99, "test double: always contradicts")

        def is_heading(self, para: str, ctx: str) -> Verdict:
            return Verdict("heading", 0.99, "test double")

        def section_kind(self, label: str, heading: str) -> Verdict:
            return Verdict("secao", 0.99, "test double")

        def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
            return Verdict("boundary", 0.99, "test double")

    for confidence in (RULE_HIGH_CONFIDENCE, 0.80, 0.90, 1.0):
        final, record = adjudicate_module.adjudicate(
            kind="own_articulation",
            doc=CARRIER,
            locator="p#1",
            rule_verdict="quoted",
            rule_confidence=confidence,
            excerpt="Art. 1º Esta portaria entra em vigor.",
            ctx="",
            referee=_Contrarian(),
        )
        assert not record.overridden, (
            f"a referee overrode a rule at confidence {confidence} — invariant "
            f"#9 says a rule at or above {RULE_HIGH_CONFIDENCE} is unassailable"
        )
        assert final == "quoted", (
            f"the rule verdict did not survive at confidence {confidence}: "
            f"final={final!r}"
        )


def guard_order_recoverability() -> None:
    """A-5b.2/A-7.5 — document order is recoverable from `Bloco nome="ordem"`.

    Constraint 1 destroys sibling position as an order channel, so `ordem` is
    the *only* one left. The three-way oracle depends on it: the nested reader
    infers order from this marker and from nothing else. A section's children
    must therefore carry a contiguous 0-based sequence — non-monotonic ordinals
    mean two children claim the same position, or a position is missing, and
    either way reading order is no longer recoverable.
    """
    bundle = render_generico_aninhado(model(CARRIER))
    for document in bundle.documents:
        for node in document.iter(f"{LEX}AgrupamentoHierarquico"):
            orders: list[int] = []
            for child in node:
                if (
                    local_name(child.tag) == "Bloco"
                    and child.get("nome") == ORDER_BLOCO
                ):
                    orders.append(int((child.text or "0").strip() or 0))
            for child in node.iter(f"{LEX}AgrupamentoHierarquico"):
                if child is node or child.getparent() is not node:
                    continue
                for grandchild in child:
                    if (
                        local_name(grandchild.tag) == "Bloco"
                        and grandchild.get("nome") == ORDER_BLOCO
                    ):
                        orders.append(int((grandchild.text or "0").strip() or 0))
                    break

    # The real claim, stated over the whole document: every `ordem` value is a
    # non-negative integer, and the multiset of a parent's children's ordinals is
    # exactly range(n) — contiguous, 0-based, no repeats.
    for document in bundle.documents:
        for parent in document.iter():
            if local_name(parent.tag) not in (
                "AgrupamentoHierarquico",
                "PartePrincipal",
            ):
                continue
            child_orders = []
            for child in parent:
                if local_name(child.tag) != "AgrupamentoHierarquico":
                    continue
                marker = next(
                    (
                        g
                        for g in child
                        if local_name(g.tag) == "Bloco"
                        and g.get("nome") == ORDER_BLOCO
                    ),
                    None,
                )
                if marker is not None:
                    child_orders.append(int((marker.text or "").strip() or -1))
            if not child_orders:
                continue
            assert sorted(child_orders) == list(range(len(child_orders))), (
                f"{CARRIER}: {parent.get('id')!r} children carry ordinals "
                f"{child_orders} — A-7.5 needs a contiguous 0-based sequence, "
                "because Constraint 1 makes this the only order channel"
            )


def guard_linker_resolves() -> None:
    """The linked path must actually resolve something (A-C.1's failure shape).

    A linker that answers nothing is indistinguishable from a document that
    cites nothing, which is the worst shape a failure can take — it is silent,
    and every test that only checks "a linker was configured" keeps passing.
    `parecer_93` resolves 132 references from the committed fixtures, so a
    harvest that returns the input unchanged is unmissable here.
    """
    bundle = render_generico(model(CITING), linker=fixture_linker())
    xml = bundle.to_xml_string(bundle.primary)
    assert xml.count("<Remissao") > 50, (
        f"{CITING}: the fixtures carry this sample's answers, but the render "
        f"produced {xml.count('<Remissao')} Remissao elements"
    )


# ===========================================================================
# The mutations
# ===========================================================================


def _mutate_constraint_1_prose_first():
    """M-1 — emit a section's own prose **before** its child sections.

    Natural reading order, and exactly what §5.4 Constraint 1 forbids: the
    schema's effective content model puts `AgrupamentoHierarquico*` before the
    extension choice, so prose-first is *invalid*. This is the mutation A-R.9
    names first, and it is the one a well-meaning refactor is most likely to
    introduce, because the mutated order is the order a human would choose.
    """
    original = nested_module._section_element

    def prose_first(section, parent_id, scope, order, **kwargs):
        element = original(section, parent_id, scope, order, **kwargs)
        children = list(element)
        natives = [
            c for c in children if local_name(c.tag) in ("Rotulo", "NomeAgrupador")
        ]
        subsections = [
            c for c in children if local_name(c.tag) == "AgrupamentoHierarquico"
        ]
        rest = [c for c in children if c not in natives and c not in subsections]
        if not (subsections and rest):
            return element
        for child in children:
            element.remove(child)
        for child in natives + rest + subsections:  # prose before subsections
            element.append(child)
        return element

    return patched(nested_module, "_section_element", prose_first)


def _mutate_constraint_2_drop_filler():
    """M-2 — stop emitting the `<Bloco nome="vazio"/>` filler.

    Constraint 2's extension choice is `minOccurs="1"`, so a section with
    subsections and no prose of its own becomes a bare container, which is
    invalid. The filler looks like decoration — it carries no text and no
    meaning — which is exactly why it is the piece most likely to be "cleaned
    up" by someone who has not read §5.4.
    """
    original = nested_module._section_element

    def bare_container(section, parent_id, scope, order, **kwargs):
        element = original(section, parent_id, scope, order, **kwargs)
        kinds = [local_name(child.tag) for child in element]
        # Only a section that has subsections and *no* prose leaf of its own is
        # the shape Constraint 2 is about. Stripping its `Bloco` children leaves
        # a container whose every child is an `AgrupamentoHierarquico`, which the
        # `minOccurs="1"` extension choice forbids.
        #
        # Removing the `vazio` marker alone is **not** enough, and that is worth
        # recording: `ORDER_BLOCO` is appended to every section unconditionally
        # (A-5b.1/A-5b.2), so it keeps satisfying the choice by itself. A
        # mutation that dropped only the filler would leave valid output and be
        # reported as surviving — a false gap. Measured on the carrier: dropping
        # `vazio` alone leaves 0 bare sections; dropping every `Bloco` leaves 5,
        # and the proposed schemas reject the result.
        if "AgrupamentoHierarquico" in kinds and "Agrupamento" not in kinds:
            for child in list(element):
                if local_name(child.tag) == "Bloco":
                    element.remove(child)
        return element

    return patched(nested_module, "_section_element", bare_container)


def _mutate_constraint_3_bare_prose():
    """M-3 — emit a prose leaf as a bare `<p>`, with no `Agrupamento` wrapper.

    Constraint 3 is a schema fact restated from §5.2: the maintainers' change
    adds `Agrupamento` and `Bloco` to the choice, **not** `p`. So unwrapped
    prose is invalid — and note the capability probe in `validate/schema.py`
    makes the same point from the other direction, deliberately probing the
    wrapped shape because probing a bare `<p>` would report "no capability"
    against the very generation that has it.
    """
    original = nested_module._prose_leaf

    def unwrapped(section, ident, scope, **kwargs):
        element = original(section, ident, scope, **kwargs)
        if element is None or not len(element):
            return element
        # Hand back the first child directly: the prose, with its wrapper gone.
        return element[0]

    return patched(nested_module, "_prose_leaf", unwrapped)


def _mutate_drop_a_block():
    """M-4 — drop the last content block of every rendered section.

    Invariant #2's loss half, and the failure a parser can commit most quietly:
    a document that is valid, well-formed, correctly structured and *says
    something different from the one it was given*. No schema can see this. Only
    a conservation check can.
    """
    original = generico_module.agrupamento

    def lossy(nome, ident, children):
        children = list(children)
        if len(children) > 1:
            children = children[:-1]
        return original(nome, ident, children)

    return patched(generico_module, "agrupamento", lossy)


def _mutate_duplicate_leaf_text():
    """M-5 — emit one leaf's text twice.

    Invariant #7 / Rule B's duplication half. The plan's own §2.4 experiment hit
    exactly this shape: a nested list read with `descendant::p|descendant::li`
    yields a parent item's text once for the parent and again inside every
    ancestor. Conservation is stated as multiset *equality* precisely so that
    duplication fails as loudly as loss.
    """
    original = generico_module.leaf_texts

    def duplicating(element):
        texts = original(element)
        if not texts:
            return texts
        return texts + (texts[0],)

    return patched(generico_module, "leaf_texts", duplicating)


def _mutate_reuse_an_id():
    """M-6 — issue a duplicate `id`.

    Invariant #5. `xsd:ID` makes this a validity failure too, but the guard
    asserted here is the *uniqueness* check rather than the schema, because the
    golden modules check uniqueness against the committed artifacts and that is
    the assertion which must stay sensitive. `IdAllocator.take` refuses a
    duplicate by raising, so the mutation collides at the element level instead —
    it rewrites the id after allocation, which is the shape a real bug takes.
    """
    original = generico_module.agrupamento
    state: dict[str, str] = {}

    def colliding(nome, ident, children):
        element = original(nome, ident, children)
        if element is None:
            return element
        if "first" not in state:
            state["first"] = ident
        else:
            element.set("id", state["first"])
        return element

    return patched(generico_module, "agrupamento", colliding)


def _mutate_skip_a_level():
    """M-7 — skip a level in the flat id path.

    Invariant #6, Rule A. `pp1_agr1_agr2_agr1` whose `pp1_agr1_agr2` does not
    exist produces a breadcrumb silently missing its middle ancestor. The nested
    emitter makes this structurally impossible (§5.2) — which is precisely why
    the flat emitter needs it asserted, and why `missing_prefixes` exists as an
    independent checker rather than a comment about `IdAllocator`.
    """
    original = generico_module.agrupamento

    def gapped(nome, ident, children):
        element = original(nome, ident, children)
        if element is None:
            return element
        parts = ident.split("_")
        if len(parts) >= 3:
            # Deepen the path by one invented level, so the id's own parent
            # prefix is a level that was never emitted.
            element.set("id", "_".join(parts[:-1] + ["agr9", parts[-1]]))
        return element

    return patched(generico_module, "agrupamento", gapped)


def _mutate_referee_overrides_high_confidence():
    """M-8 — let a referee override a high-confidence rule.

    Invariant #9, and §7.3 constraint 4. The mutation removes the
    `rule_confidence < RULE_HIGH_CONFIDENCE` term from `adjudicate`'s
    `overridable` expression — the second of the two independent guards, and the
    one that survives a caller consulting a referee directly instead of going
    through the flag threshold. `adjudicate`'s own docstring says both checks
    live there for exactly that reason, so removing one must be caught.
    """
    original = adjudicate_module.adjudicate

    def permissive(**kwargs):
        referee = kwargs.get("referee")
        if referee is None or not getattr(referee, "enabled", True):
            return original(**kwargs)
        method = adjudicate_module._METHODS.get(kwargs.get("kind", ""))
        if method is None:
            return original(**kwargs)
        # Consult regardless of the flag threshold, and honour the answer
        # regardless of how confident the rule was — the guarantee removed.
        verdict = getattr(referee, method)(
            kwargs.get("excerpt", ""), kwargs.get("ctx", "")
        )
        if not isinstance(verdict, Verdict) or verdict.abstained:
            return original(**kwargs)
        final, record = original(**kwargs)
        if verdict.verdict != kwargs.get("rule_verdict"):
            record = type(record)(
                **{
                    **{
                        f: getattr(record, f)
                        for f in record.__dataclass_fields__  # type: ignore[attr-defined]
                    },
                    "final_verdict": verdict.verdict,
                    "referee_consulted": True,
                    "overridden": True,
                }
            )
            return verdict.verdict, record
        return final, record

    return patched(adjudicate_module, "adjudicate", permissive)


def _mutate_non_monotonic_order():
    """M-9 — make the `ORDER_BLOCO` ordinals non-monotonic.

    Attacks order recoverability (A-5b.2, A-7.5). Because §5.4 Constraint 1
    destroys sibling position as an order channel, `Bloco nome="ordem"` is the
    *only* way a reader can recover reading order — so a wrong ordinal is not a
    cosmetic defect, it is a document that segments in the wrong order while
    remaining perfectly valid. The three-way oracle is what notices.
    """
    original = nested_module._bloco

    def scrambled(nome, text=None):
        if nome == ORDER_BLOCO and text is not None:
            # A constant ordinal: every sibling now claims position 0, so the
            # sequence is neither contiguous nor a permutation of range(n).
            return original(nome, "0")
        return original(nome, text)

    return patched(nested_module, "_bloco", scrambled)


def _mutate_linker_returns_input_unchanged():
    """M-10 — the span harvest returns nothing.

    This is A-L.8's *measured* failure mode, not an invented one: a non-`federal`
    authority makes the real `linkertool` return the input unchanged, silently,
    resolving nothing. Cycle 8e found that passing a document's own URN as
    context would have resolved zero references across the entire corpus while
    looking exactly like a corpus that cites nothing.

    Patched at `find_refs` rather than at `_spans_of`, and the reason is a
    finding worth recording: under `--linker=fixtures` the cache answers from
    recorded replies and returns **before** `_parse_reply` is ever called, so
    `_spans_of` runs **zero** times on the whole corpus (measured). A mutation
    there would patch code the fixture path never reaches and be reported as
    surviving — a false gap. `find_refs` is the seam the harvest is actually
    observed through, and returning `()` from it is precisely "the input, with
    nothing resolved".
    """
    return patched(
        linkertool_module.LinkertoolLinker,
        "find_refs",
        lambda self, text, context_urn=None: (),
    )


#: The ten mutations, in the spec's order.
#:
#: `attacks` carries the plan's own numbering so a surviving mutation names the
#: unguarded invariant rather than merely reporting that something is wrong.
MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        name="M-1",
        attacks="§5.4 Constraint 1 — subsections precede own prose (A-5b.1)",
        guard="nested validity + Constraint 1 order",
        apply=_mutate_constraint_1_prose_first,
        check=lambda: (guard_constraint_1_order(), guard_nested_validity()),
        constraint=1,
        requires_nested=True,
    ),
    Mutation(
        name="M-2",
        attacks="§5.4 Constraint 2 — every AH needs a non-AH child",
        guard="nested validity + Constraint 2 filler",
        apply=_mutate_constraint_2_drop_filler,
        check=lambda: (guard_constraint_2_filler(), guard_nested_validity()),
        constraint=2,
        requires_nested=True,
    ),
    Mutation(
        name="M-3",
        attacks="§5.4 Constraint 3 — prose needs an Agrupamento wrapper",
        guard="nested validity + Constraint 3 wrapper",
        apply=_mutate_constraint_3_bare_prose,
        check=lambda: (guard_constraint_3_wrapper(), guard_nested_validity()),
        constraint=3,
        requires_nested=True,
    ),
    Mutation(
        name="M-4",
        attacks="invariant #2 — conservation, the loss half",
        guard="test_conservation_generico",
        apply=_mutate_drop_a_block,
        check=guard_conservation,
    ),
    Mutation(
        name="M-5",
        attacks="invariant #7 — no text duplication (Rule B)",
        guard="test_conservation_generico",
        apply=_mutate_duplicate_leaf_text,
        check=guard_conservation,
    ),
    Mutation(
        name="M-6",
        attacks="invariant #5 — id uniqueness",
        guard="golden + bundle id uniqueness",
        apply=_mutate_reuse_an_id,
        check=guard_id_uniqueness,
    ),
    Mutation(
        name="M-7",
        attacks="invariant #6 — ancestor totality (Rule A)",
        guard="flat reversibility / missing_prefixes",
        apply=_mutate_skip_a_level,
        check=guard_rule_a,
    ),
    Mutation(
        name="M-8",
        attacks="invariant #9 — the referee is advisory (§7.3 constraint 4)",
        guard="routing / referee attack tests",
        apply=_mutate_referee_overrides_high_confidence,
        check=guard_referee_is_advisory,
    ),
    Mutation(
        name="M-9",
        attacks="order recoverability (A-5b.2, A-7.5)",
        guard="three-way oracle / ordem markers",
        apply=_mutate_non_monotonic_order,
        check=guard_order_recoverability,
    ),
    Mutation(
        name="M-10",
        attacks="linked invariants — a harvest that resolves nothing (A-L.8)",
        guard="linked goldens / test_linked_invariants",
        apply=_mutate_linker_returns_input_unchanged,
        check=guard_linker_resolves,
    ),
)

BY_NAME = {m.name: m for m in MUTATIONS}


def _marks(mutation: Mutation):
    """`requires_nested` for the three that judge validity against the proposal.

    A-R.9 requires the suite to stay green with `lexml-proposed/` absent, and
    M-1…M-3 assert *invalidity* against it — a claim a bare checkout cannot
    make. The other seven, and the harness itself, carry no marker and run
    everywhere, which is what stops this module from being a nested-only test.
    """
    return [requires_nested] if mutation.requires_nested else []


# ===========================================================================
# The tests
# ===========================================================================


@pytest.mark.parametrize(
    "mutation",
    [pytest.param(m, id=m.name, marks=_marks(m)) for m in MUTATIONS],
)
def test_every_mutation_is_caught(mutation: Mutation):
    """Under each mutation, the named guard **fails** — and then it is reverted.

    The cycle's headline deliverable (§8 Cycle 9, "a deliberate mutation fails
    the suite"). A mutation that survives is a **gap in the test suite**, not a
    bug in the mutation: it means the invariant named in `attacks` is currently
    undefended, and the assertion below says which one so the finding is
    actionable rather than merely alarming.

    Reverting is unconditional — `Mutation.run` holds the patch in a context
    manager whose `finally` restores the original — and `test_no_mutation_leaks`
    measures that it worked.
    """
    result = mutation.run()

    assert result.caught, (
        f"{mutation.name} SURVIVED — this is a gap in the test suite, not a "
        f"defect in the mutation.\n"
        f"  attacks: {mutation.attacks}\n"
        f"  guard that should have caught it: {mutation.guard}\n"
        f"The named invariant is currently undefended: the mutated behaviour "
        f"passed the assertion that exists to reject it. Report this rather "
        f"than deleting the mutation (plan §10's risk table)."
    )


def test_the_harness_itself_is_not_vacuous():
    """A **no-op** mutation must leave the guard GREEN.

    Without this, `test_every_mutation_is_caught` is unfalsifiable: a harness
    that reported "caught" for everything — because `guard_fails` swallowed the
    wrong exception, or because the guards raise for an unrelated reason — would
    pass all ten and prove nothing whatsoever.

    So the control runs a **real** guard (the same conservation assertion M-4
    attacks) under **no** mutation and requires it to pass. "Survived" here means
    the guard genuinely ran and genuinely approved unmutated output, which is the
    only thing that makes the other ten verdicts mean anything.
    """

    @contextlib.contextmanager
    def no_mutation():
        yield

    result = guard_fails("M-0", guard_conservation)

    assert not result.caught, (
        "the harness reported a NO-OP mutation as caught, so its verdicts "
        "cannot be trusted: every other assertion in this module would pass "
        f"regardless of whether the suite bites. Guard said: {result.detail}"
    )

    # And the same through the full Mutation machinery, so the control covers
    # `Mutation.run`'s path and not only `guard_fails`.
    control = Mutation(
        name="M-0",
        attacks="nothing — the harness's own control",
        guard="conservation",
        apply=no_mutation,
        check=guard_conservation,
    )
    assert not control.run().caught, (
        "Mutation.run reported a no-op as caught — the patching path itself "
        "changes behaviour, so no verdict from this module is meaningful"
    )


def test_constraint_mutations_are_declared():
    """M-1/M-2/M-3 exist and are tagged to §5.4's three constraints.

    Amendment **A-R.9** does not ask merely for "a mutation test"; it asks that
    the mutation test *bite on the §5.4 Constraint 1/2/3 invariants* by name. A
    future edit that quietly dropped one of the three — or retagged it — would
    leave the other tests green while silently retiring the specific demand the
    amendment makes. This is the assertion that notices.

    It also pins the `requires_nested` gating, because that is the other half of
    A-R.9: these three assert invalidity against `lexml-proposed/`, which a bare
    checkout cannot judge, so they must skip rather than fail there.
    """
    tagged = {m.constraint: m for m in MUTATIONS if m.constraint is not None}

    assert set(tagged) == {1, 2, 3}, (
        f"§5.4 has three constraints; the harness declares mutations for "
        f"{sorted(tagged)}. A-R.9 requires all three to be attacked by name."
    )
    assert [tagged[c].name for c in (1, 2, 3)] == ["M-1", "M-2", "M-3"], (
        "the constraint mutations have been renumbered; the spec's table and "
        "the cycle report name them M-1, M-2 and M-3"
    )

    for number, mutation in sorted(tagged.items()):
        assert mutation.requires_nested, (
            f"{mutation.name} asserts invalidity against lexml-proposed/, so it "
            "must be gated on `requires_nested` — A-R.9 requires the suite to "
            "stay green with that directory absent"
        )
        assert f"Constraint {number}" in mutation.attacks, (
            f"{mutation.name} is tagged constraint {number} but its `attacks` "
            f"field says {mutation.attacks!r}"
        )

    # The converse: nothing *else* claims to be a constraint mutation, so the
    # set above is the whole of A-R.9's demand rather than a sample of it.
    unnested = [m.name for m in MUTATIONS if m.requires_nested and not m.constraint]
    assert not unnested, (
        f"{unnested} are gated on requires_nested without naming a §5.4 "
        "constraint; only the constraint mutations need that gate, and an "
        "unnecessary one silently retires a mutation on a bare checkout"
    )


def test_every_mutation_declares_what_it_attacks():
    """Each mutation names an invariant and a guard, in the plan's own numbering.

    A mutation whose failure message said only "something broke" would be a
    worse instrument than no mutation at all: the whole value of committing this
    harness is that a *survival* localises the gap. That requires every entry to
    carry a real `attacks` string, so this asserts the metadata is populated
    rather than trusting the author of the next mutation to remember.
    """
    for mutation in MUTATIONS:
        assert mutation.attacks.strip(), f"{mutation.name} names no invariant"
        assert mutation.guard.strip(), f"{mutation.name} names no guard"
        assert re.fullmatch(r"M-\d+", mutation.name), (
            f"{mutation.name!r} does not follow the spec's M-<n> naming"
        )

    assert len(MUTATIONS) >= 10, (
        f"the spec's table lists ten mutations; {len(MUTATIONS)} are declared"
    )
    assert len(BY_NAME) == len(MUTATIONS), "two mutations share a name"


def test_no_mutation_leaks():
    """After the module runs, a canary render is byte-identical to its golden.

    Decision **N-2** measured rather than asserted. Every mutation above rebinds
    a module attribute; if any `finally` failed to restore one — an exception in
    an unexpected place, a nested patch applied in the wrong order, a guard that
    swallowed something — the patched function would still be live in this
    interpreter, and every test that ran afterwards would be silently testing
    mutated code.

    The canary is a **committed golden**, not a re-render compared with itself: a
    self-comparison under a leaked mutation would agree perfectly, because both
    sides would be mutated. Only an artifact reviewed and written to disk before
    this module existed can tell the difference.

    Run explicitly at the end rather than as a fixture so that the assertion, and
    its reasoning, are visible in the file that needs them.
    """
    # Re-apply and release every mutation first, so this test measures the state
    # the module actually leaves behind rather than a state no mutation touched.
    for mutation in MUTATIONS:
        with contextlib.suppress(Exception):
            mutation.run()

    golden = GOLDEN_DIR / f"{CARRIER}.xml"
    assert golden.exists(), (
        f"the canary golden {golden.name} is missing; without it this test "
        "cannot distinguish restored code from leaked mutations"
    )

    bundle = render_generico(
        build_model(
            read_docx(SAMPLES_DIR / f"{CARRIER}.docx"), filename=f"{CARRIER}.docx"
        )
    )
    actual = bundle.to_xml_string(bundle.primary)
    expected = golden.read_text(encoding="utf-8")

    assert actual == expected, (
        f"{CARRIER}: the render no longer matches its committed golden after "
        "the mutation harness ran — a mutation leaked past its `finally` and is "
        "still live. Every test that ran after this module is suspect."
    )

    # Every patched name must be the library's own object again, not a wrapper.
    #
    # The byte comparison above already catches a *behavioural* leak; this
    # catches a leaked **identity** — a pass-through wrapper that happens to be
    # faithful on this one document — which would otherwise survive to corrupt a
    # later, different assertion. The list is exactly the set of attributes the
    # mutations above rebind, so a new mutation patching a new name must add its
    # site here too.
    for owner, attribute, where in (
        (generico_module, "agrupamento", "render.generico.agrupamento"),
        (generico_module, "leaf_texts", "render.generico.leaf_texts"),
        (nested_module, "_bloco", "generico_aninhado._bloco"),
        (nested_module, "_section_element", "generico_aninhado._section_element"),
        (nested_module, "_prose_leaf", "generico_aninhado._prose_leaf"),
        (adjudicate_module, "adjudicate", "referee.adjudicate.adjudicate"),
        (
            linkertool_module.LinkertoolLinker,
            "find_refs",
            "refs.linkertool.LinkertoolLinker.find_refs",
        ),
    ):
        restored = getattr(owner, attribute)
        assert getattr(restored, "__module__", "").startswith("lexml_nonstat"), (
            f"{where} is still patched — a mutation leaked past its `finally`"
        )


def test_the_guards_pass_on_unmutated_code():
    """Every guard is green before any mutation — the other half of vacuity.

    `test_the_harness_itself_is_not_vacuous` proves the *harness* discriminates;
    this proves each individual **guard** does. A guard that raised
    unconditionally — a typo in an xpath, a missing file, a stale constant —
    would make its mutation look caught while measuring nothing at all, and that
    failure is per-guard rather than global, so it needs its own assertion.

    The nested guards are included unconditionally: they read XML the emitter
    just built, and reading needs no schema (A-7.4's finding). Only
    `guard_nested_validity`, which genuinely consults `lexml-proposed/`, is left
    to the gated mutations.
    """
    for guard in (
        guard_constraint_1_order,
        guard_constraint_2_filler,
        guard_constraint_3_wrapper,
        guard_conservation,
        guard_id_uniqueness,
        guard_rule_a,
        guard_referee_is_advisory,
        guard_order_recoverability,
        guard_linker_resolves,
    ):
        result = guard_fails(guard.__name__, guard)
        assert not result.caught, (
            f"{guard.__name__} fails on **unmutated** code, so the mutation it "
            f"guards would be reported as caught while measuring nothing: "
            f"{result.how} {result.detail}"
        )


@requires_nested
def test_the_nested_validity_guard_passes_on_unmutated_code():
    """`guard_nested_validity` is green before mutation — gated, for A-R.9.

    Split from the test above because this is the one guard that consults
    `lexml-proposed/`. On a bare checkout it must skip rather than fail, which is
    the whole of A-R.9's "the parser's correctness must not depend on an
    unreleased schema".
    """
    result = guard_fails("guard_nested_validity", guard_nested_validity)
    assert not result.caught, (
        "the nested render does not validate against the proposed schemas "
        f"before any mutation is applied: {result.how} {result.detail}"
    )


def test_the_carrier_document_exercises_every_nested_shape():
    """The carrier really does carry all three nested shapes.

    Anti-vacuity for the *fixture* rather than for the harness. M-1 only bites on
    a section having both subsections and its own prose; M-2 only bites where a
    `vazio` filler exists. A carrier lacking either would make the corresponding
    mutation a no-op that the harness would then report as a **surviving**
    mutation — a false gap, which is worse than a missed one because it sends a
    reader hunting for a defect that is not there.

    The counts are pinned because they were *measured* when the carrier was
    chosen: `par_cosit_26`, the obvious alternative, emits zero `vazio` markers.
    """
    bundle = render_generico_aninhado(model(CARRIER))
    document = bundle.primary

    sections = sum(1 for _ in document.iter(f"{LEX}AgrupamentoHierarquico"))
    fillers = sum(
        1
        for node in document.iter(f"{LEX}Bloco")
        if node.get("nome") == EMPTY_BLOCO
    )
    both = 0
    for node in document.iter(f"{LEX}AgrupamentoHierarquico"):
        kinds = {local_name(child.tag) for child in node}
        if "AgrupamentoHierarquico" in kinds and "Agrupamento" in kinds:
            both += 1

    assert sections >= 10, f"{CARRIER}: only {sections} nested sections"
    assert fillers >= 1, (
        f"{CARRIER}: no `{EMPTY_BLOCO}` filler, so M-2 would drop nothing and "
        "be reported as a surviving mutation for the wrong reason"
    )
    assert both >= 1, (
        f"{CARRIER}: no section has both subsections and its own prose, so "
        "M-1's reordering would be a no-op and Constraint 1 would go untested"
    )


def test_mutations_make_no_network_call(monkeypatch):
    """The whole harness runs with `socket.socket` made to raise.

    Plan §9.3 pins `--referee=none` across the suite and §8's Cycle 9 list asks
    for "referee disabled ⇒ suite still green (no network dependency anywhere)".
    The referee double in `guard_referee_is_advisory` answers in-process and the
    linker guard is served from committed fixtures, so nothing here should reach
    a socket — asserted the way `test_linked_invariants` asserts zero subprocess
    spawns, by making the forbidden operation **raise** rather than counting it
    afterwards. A count can be read after the damage; a raise cannot be passed
    through.
    """
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "the mutation harness opened a socket; every referee and linker it "
            "uses must answer in-process or from committed fixtures"
        )

    monkeypatch.setattr(socket, "socket", forbidden)

    for mutation in MUTATIONS:
        if mutation.requires_nested:
            continue
        mutation.run()

    guard_conservation()
    guard_linker_resolves()
