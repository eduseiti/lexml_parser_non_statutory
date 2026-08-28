"""Schema capabilities are probed, never assumed (§2.11, amendment A-R.2).

Two generations of the LexML schemas now live in the repository: ``lexml/`` as
shipped upstream, and the generated ``lexml-proposed/`` carrying the
maintainers' not-yet-released recursive ``AgrupamentoHierarquico``. The moment
a second generation exists, "which schema is this?" becomes a question code can
get wrong, and A-R.2's answer is that no cycle may hard-code it: behaviour is
gated on a probe of the schemas *actually present*.

Three things follow, and each has a test here.

**The probe must measure, not recite.** `test_the_two_generations_disagree` is
the whole reason for having two directories — if the probe answered the same
for both, it would be reporting a constant, and every `nested_unavailable`
blocker downstream would be decoration.

**The probe must never raise.** Invariant #12 requires the suite to be green
against ``lexml/`` alone, on a checkout that never ran
``scripts/build_proposed_schemas.py``. An unknown generation and an absent
directory both have to come back as *"no capability, and here is why"*, which
is what `test_probe_never_raises_on_an_unknown_generation` and
`test_absent_generation_directory_degrades_gracefully` pin.

**Nothing existing may move.** The generation parameter is keyword-only with a
default of ``shipped``, so every Cycle 0–4 caller keeps its meaning; and the
compiled-schema cache is keyed on the generation, because a cache keyed on the
name alone would let whichever generation was asked for first answer for the
other — a bug that would make the probe report the opposite of the truth.

Reading ``lexml-proposed/`` also makes this the first cycle to touch a second
schema directory, so Cycle 0's "the vendored schemas are never modified"
invariant is reasserted here rather than assumed to still hold.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys

import pytest
from lxml import etree

from lexml_nonstat.validate import (
    GENERATIONS,
    PROPOSED,
    SCHEMA_NAMES,
    SHIPPED,
    UnknownSchemaError,
    clear_cache,
    generation_dir,
    load_schema,
    probe_capabilities,
    validate,
)
from lexml_nonstat.validate import schema as schema_module

from tests.conftest import REPO_ROOT, lexml_doc

#: The canary the probe asks its question with: an `AgrupamentoHierarquico`
#: carrying an `Agrupamento` of prose. Not a bare `<p>` — §5.4 constraint 3
#: says prose needs the wrapper, and the maintainers' change adds `Agrupamento`
#: to the choice, not `p`. Probing the wrong shape would report "no capability"
#: against the very generation that has it.
PROBE_DOC = lexml_doc(
    '<DocumentoGenerico><PartePrincipal id="pp1">'
    '<AgrupamentoHierarquico id="agh1" nome="tema">'
    '<Agrupamento id="agh1_agr1" nome="prosa"><p>Texto</p></Agrupamento>'
    "</AgrupamentoHierarquico>"
    "</PartePrincipal></DocumentoGenerico>"
)

#: `lexml-proposed/` is *generated*. A clean checkout may not have it, and
#: invariant #12 says that must skip, never fail.
proposed_present = pytest.mark.skipif(
    not generation_dir(PROPOSED).is_dir(),
    reason="lexml-proposed/ is generated; run scripts/build_proposed_schemas.py",
)


# ---------------------------------------------------------------------------
# What each generation permits
# ---------------------------------------------------------------------------


def test_shipped_generation_lacks_nested_agrupamento():
    """Today's shipped reality, pinned: `lexml/` rejects the nested encoding.

    This is §2.1's headline finding restated as a capability. While it holds,
    `generico` (flat) stays the default emitter and `generico-aninhado` is
    opt-in — so if upstream ever ships the change and this test goes red, that
    red is the signal to re-vendor and flip the default, not a defect.
    """
    capabilities = probe_capabilities(SHIPPED)

    assert capabilities.generation == SHIPPED
    assert capabilities.available is True
    assert capabilities.nested_agrupamento is False

    diagnostic = capabilities.diagnostic
    assert diagnostic, "a probe result without a diagnostic is unactionable"
    assert SHIPPED in diagnostic, "the diagnostic must name the generation"
    assert "lexml/" in diagnostic, "and the directory it measured"


@proposed_present
def test_proposed_generation_has_nested_agrupamento():
    """`lexml-proposed/` accepts it — the change is real and is measured here.

    Without this, the probe could be a constant `False` and every test above
    would still pass.
    """
    capabilities = probe_capabilities(PROPOSED)

    assert capabilities.generation == PROPOSED
    assert capabilities.available is True
    assert capabilities.nested_agrupamento is True
    assert PROPOSED in capabilities.diagnostic
    assert "lexml-proposed/" in capabilities.diagnostic


@proposed_present
def test_the_two_generations_disagree():
    """The point of having two generations, as one assertion.

    A probe that answered identically for both would be reporting nothing, and
    the `nested_unavailable` blocker (A-R.7) would be unreachable code.
    """
    shipped = probe_capabilities(SHIPPED)
    proposed = probe_capabilities(PROPOSED)

    assert shipped.available and proposed.available
    assert shipped.nested_agrupamento != proposed.nested_agrupamento, (
        "the two generations answer the same question the same way; either "
        "lexml-proposed/ is stale or the probe is not measuring anything"
    )
    assert shipped.diagnostic != proposed.diagnostic


@pytest.mark.parametrize(
    "generation",
    [SHIPPED, pytest.param(PROPOSED, marks=proposed_present)],
)
def test_capability_agrees_on_both_schemas(generation):
    """§2.8: `rigido` and `flexivel` do not diverge on the `generico` surface.

    The probe grants a capability only when both schemas agree, so this checks
    the premise directly rather than through the probe: the two schemas are
    validated separately and their verdicts compared. A divergence would be a
    finding about the schemas — the probe would report it as a diagnostic and
    refuse the capability — not something to resolve by picking a winner.
    """
    element = etree.fromstring(PROBE_DOC.encode("utf-8"))
    verdicts = {
        name: bool(load_schema(name, generation=generation).validate(element))
        for name in SCHEMA_NAMES
    }

    assert verdicts["rigido"] == verdicts["flexivel"], (
        f"generation {generation!r} diverges between schemas: {verdicts}"
    )
    assert probe_capabilities(generation).nested_agrupamento is verdicts["rigido"], (
        "the probe reports something other than what the schemas said"
    )


# ---------------------------------------------------------------------------
# Graceful degradation — invariant #12's mechanism
# ---------------------------------------------------------------------------


def test_probe_never_raises_on_an_unknown_generation():
    """An unknown generation answers "no", with a reason. It never raises.

    This is invariant #12's mechanism: a caller asks the probe and branches on
    the answer, so the probe must have an answer for every input. If it raised,
    every call site would need a `try` — and the first one to forget it would
    take down a pipeline over a typo in a flag.
    """
    capabilities = probe_capabilities("bogus")

    assert capabilities.available is False
    assert capabilities.nested_agrupamento is False
    assert "bogus" in capabilities.diagnostic
    for name in GENERATIONS:
        assert name in capabilities.diagnostic, (
            "the diagnostic should name the generations that do exist"
        )


def test_absent_generation_directory_degrades_gracefully(monkeypatch):
    """A checkout that never generated `lexml-proposed/` still runs green.

    `lexml-proposed/` is a build product, so its absence is an ordinary state
    of the repository, not an error. The probe has to say *which* directory is
    missing and how to produce it — a bare `False` would send the reader into
    the source to find out why nested rendering is unavailable.
    """
    monkeypatch.setattr(
        schema_module,
        "_GENERATION_DIRS",
        {SHIPPED: "lexml", PROPOSED: "lexml-proposed-not-generated"},
    )
    assert not generation_dir(PROPOSED).is_dir(), "the monkeypatch did not take"

    capabilities = probe_capabilities(PROPOSED)

    assert capabilities.available is False
    assert capabilities.nested_agrupamento is False
    assert "lexml-proposed-not-generated" in capabilities.diagnostic
    assert "scripts/build_proposed_schemas.py" in capabilities.diagnostic, (
        "the diagnostic must tell the user how to produce the generation"
    )

    # The shipped generation is unaffected by the other one being absent.
    assert probe_capabilities(SHIPPED).available is True


def test_generation_dir_rejects_an_unknown_name():
    """Asking for a directory is not asking a question — here, a typo raises.

    `probe_capabilities` is the forgiving surface because it answers a
    question; `generation_dir` returns a path, and there is no honest path to
    return for a name that does not exist.
    """
    with pytest.raises(UnknownSchemaError) as exc:
        generation_dir("bogus")

    message = str(exc.value)
    assert "bogus" in message
    for name in GENERATIONS:
        assert name in message, "the error should name the valid generations"


# ---------------------------------------------------------------------------
# Nothing existing moves (A-R.2 is additive)
# ---------------------------------------------------------------------------


def test_default_generation_is_shipped():
    """Every existing caller keeps meaning what it meant before A-R.2.

    `lexml/` stays the default everywhere; `lexml-proposed/` is opt-in until
    upstream ships the change. A default that silently became `proposed` would
    make the suite validate against schemas nobody has.
    """
    assert probe_capabilities() == probe_capabilities(SHIPPED)
    assert generation_dir() == generation_dir(SHIPPED) == REPO_ROOT / "lexml"


def test_load_schema_default_is_unchanged():
    """`load_schema(name)` still means the shipped generation, and still caches.

    The cache is keyed on `(generation, name)`, so the default call and the
    explicit one must land on the same entry — otherwise the "compilation is
    cached" property Cycle 0 established would quietly halve in value.
    """
    for name in SCHEMA_NAMES:
        assert load_schema(name) is load_schema(name, generation=SHIPPED)

    # And the behaviour every existing caller depends on: the shipped schemas
    # reject the nested encoding, through the public `validate` with no
    # generation named.
    minimal = lexml_doc(
        '<DocumentoGenerico><PartePrincipal id="pp1"><p>Texto</p>'
        "</PartePrincipal></DocumentoGenerico>"
    )
    assert validate(minimal).ok
    assert not validate(PROBE_DOC).ok


@proposed_present
def test_generations_do_not_share_a_cache_entry():
    """The bug the generation-keyed cache exists to prevent.

    Keyed on the schema name alone, whichever generation was compiled first
    would answer for both — and the probe would then report the *other*
    generation's capability, confidently and wrongly. Compiling `proposed`
    first and asking `shipped` immediately afterwards is the order that catches
    it.
    """
    clear_cache()

    proposed = load_schema("rigido", generation=PROPOSED)
    shipped = load_schema("rigido", generation=SHIPPED)

    assert proposed is not shipped
    assert load_schema("rigido", generation=PROPOSED) is proposed
    assert load_schema("rigido", generation=SHIPPED) is shipped

    # Object identity is the mechanism; the verdicts are the point.
    element = etree.fromstring(PROBE_DOC.encode("utf-8"))
    assert proposed.validate(element) is True
    assert shipped.validate(element) is False


@proposed_present
def test_validate_accepts_a_generation():
    """The capability reaches callers through the public `validate`, both ways.

    The same document, invalid on the schemas we ship against and valid on the
    ones the maintainers propose: that difference is what `--emitter` will be
    gated on, so it is asserted through the API a caller actually uses.
    """
    shipped = validate(PROBE_DOC, "both", generation=SHIPPED)
    proposed = validate(PROBE_DOC, "both", generation=PROPOSED)

    assert not shipped.ok
    assert {r.schema for r in shipped.results} == set(SCHEMA_NAMES)
    assert all(r.errors for r in shipped.results), (
        "an invalid document must surface per-schema errors, not a bare False"
    )

    assert proposed.ok
    assert all(not r.errors for r in proposed.results)


# ---------------------------------------------------------------------------
# The vendored baseline
# ---------------------------------------------------------------------------


def test_lexml_directory_is_untouched(schema_files):
    """Cycle 0's invariant, reasserted by the first cycle to read two generations.

    `lexml/` stays byte-identical to upstream: that is what makes a future
    `git diff` there show LexML's changes and nothing of ours, and it is what
    `lexml-proposed/` exists to avoid disturbing. Probing must be a read.
    """
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in schema_files}
    assert before, "no schemas found in lexml/"

    clear_cache()
    for generation in GENERATIONS:
        probe_capabilities(generation)
    for name in SCHEMA_NAMES:
        load_schema(name)

    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in schema_files}
    assert before == after, "probing the schema generations modified lexml/ on disk"


@proposed_present
def test_proposed_generation_is_current():
    """The committed `lexml-proposed/` is still what the generator produces.

    It is generated and never hand-edited, so a drift here means either the
    upstream schemas moved under it or somebody patched it by hand — and in
    both cases every capability measured against it is suspect. The generator's
    own `check` is imported rather than shelled out, so a failure names the
    stale file instead of an exit code.
    """
    script = REPO_ROOT / "scripts" / "build_proposed_schemas.py"
    spec = importlib.util.spec_from_file_location("build_proposed_schemas", script)
    module = importlib.util.module_from_spec(spec)
    # `scripts/` is not a package, so the module has to be registered before it
    # executes: its dataclasses resolve their annotations through
    # `sys.modules[cls.__module__]`, which is absent for an unregistered module.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        problems = module.check(generation_dir(PROPOSED))
    finally:
        sys.modules.pop(spec.name, None)

    assert problems == [], (
        "lexml-proposed/ is not what scripts/build_proposed_schemas.py would "
        f"write: {problems}"
    )
