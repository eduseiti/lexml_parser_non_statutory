"""The §2.1 encoding matrix, executed against both schemas.

This is the cycle's headline deliverable: the investigation's central table
stops being prose and becomes an assertion. Every design decision downstream —
flat `generico` output, hierarchy in the `id` path, inline-only table cells —
rests on one of these rows.

Cycle 5b (amendment **A-R.2**) runs the matrix against every schema
*generation*, and adds the two nested cases the maintainers' §2.10 change makes
expressible. A case naming a capability in ``requires`` **skips with the
probe's own diagnostic** on a generation that lacks it, rather than failing —
so the suite stays green against `lexml/` alone (A-R.9). The skip decision
lives in :func:`skip_reason`, a pure function of a case and a *probe result*:
invariant #12 forbids branching on a schema version, and a helper that cannot
see a version cannot violate it.
"""

from __future__ import annotations

import dataclasses

import pytest
from _pytest.outcomes import Skipped
from lxml import etree

from lexml_nonstat.validate import (
    GENERATIONS,
    PROPOSED,
    SCHEMA_NAMES,
    SHIPPED,
    SchemaCapabilities,
    load_schema,
    probe_capabilities,
    validate,
)

from .matrix_cases import ALL_CASES, MATRIX, NESTED_MATRIX, PLAN_ROW_COUNT


#: Capability names a case may legitimately require: the boolean fields the
#: probe actually sets on :class:`SchemaCapabilities`. Derived from the dataclass
#: rather than written out, so a capability added upstream needs no edit here and
#: a misspelled one cannot pass for a real one.
CAPABILITY_NAMES: frozenset[str] = frozenset(
    field.name
    for field in dataclasses.fields(SchemaCapabilities)
    if field.type in (bool, "bool")
)


def skip_reason(case, capabilities: SchemaCapabilities) -> str | None:
    """Why ``case`` cannot run against the generation ``capabilities`` describes.

    Returns ``None`` when the case may run — always, for a case with no
    ``requires`` — and otherwise the probe's own ``diagnostic``, which names the
    generation, its directory and the reason, so a skipped run explains itself.

    This is the whole of A-R.2's mechanism, deliberately factored out as a pure
    function so it can be asserted directly (T-23) rather than only through its
    effect on a test run.
    """
    if not case.requires:
        return None
    if case.requires not in CAPABILITY_NAMES:
        raise ValueError(
            f"case {case.id!r} requires unknown capability {case.requires!r}; "
            f"known: {sorted(CAPABILITY_NAMES)}. A typo here would otherwise "
            "read as a capability nothing provides, and the case would skip "
            "silently and permanently — a test that never runs and never says so."
        )
    if getattr(capabilities, case.requires):
        return None
    return capabilities.diagnostic


def _capabilities(generation: str) -> SchemaCapabilities:
    """Probe once per generation. Compilation is cached by `validate.schema`."""
    return probe_capabilities(generation)


def _skip_unless_supported(case, generation: str) -> None:
    """Skip the calling test when ``generation`` cannot answer for ``case``.

    Two distinct skips, both from the probe and neither from a version check:
    a generation that is not in this checkout at all cannot be asked anything
    (``available``), and a generation that is present but lacks the capability
    a case requires cannot answer *that* case (:func:`skip_reason`).
    """
    capabilities = _capabilities(generation)
    if not capabilities.available:
        pytest.skip(capabilities.diagnostic)

    reason = skip_reason(case, capabilities)
    if reason is not None:
        pytest.skip(f"case {case.row} requires {case.requires!r}: {reason}")


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("generation", GENERATIONS)
@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_matrix_case(case, schema_name, generation):
    """Each encoding validates (or fails) exactly as the plan documents.

    The 16 §2.1 rows require nothing and so are asserted against **every**
    generation — which is A-R.1's "16/16 backward compatible" finding, restated
    as a running assertion rather than a one-off measurement. The nested cases
    skip where the capability is absent.
    """
    _skip_unless_supported(case, generation)

    schema = load_schema(schema_name, generation=generation)
    document = etree.fromstring(case.document.encode("utf-8"))

    assert schema.validate(document) is case.expected, (
        f"row {case.row} ({case.encoding}) on {schema_name}/{generation}: "
        f"expected {'PASS' if case.expected else 'FAIL'}, got the opposite.\n"
        f"{schema.error_log}"
    )


@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c.id)
def test_rigido_and_flexivel_agree(case):
    """§2.8: the two schemas do not diverge on any matrix encoding.

    They redefine only `idArtigo`/`idAgregador`, `DispositivoType` and
    `AlteracaoType` — none of which touch the OpenStructure surface. A failure
    here means a schema was revised in a way the plan does not account for.
    """
    report = validate(case.document, "both")
    verdicts = {r.schema: r.valid for r in report.results}

    assert verdicts["rigido"] == verdicts["flexivel"], (
        f"row {case.row} ({case.encoding}) diverges between schemas: {verdicts}. "
        "§2.8 asserts they agree across this surface."
    )


def test_matrix_covers_every_plan_row():
    """Guards against a row being dropped from the matrix as it is edited."""
    assert len(MATRIX) == PLAN_ROW_COUNT
    assert len({c.row for c in MATRIX}) == PLAN_ROW_COUNT, "duplicate row labels"


def test_open_structure_cannot_nest():
    """§2.1's headline conclusion, stated as one assertion.

    No LexML element is both non-articulated and recursive: neither
    `Agrupamento` nor `div` may contain itself. This is the finding that forces
    hierarchy out-of-band, so it gets a test of its own that names it.
    """
    recursive = {c.row: c for c in MATRIX if c.row in ("C", "D")}

    for row, case in recursive.items():
        report = validate(case.document, "both")
        assert not report.ok, (
            f"row {row} ({case.encoding}) validated — OpenStructure now nests. "
            "If this is a genuine schema improvement, plan §11's proposal is "
            "resolved and the `generico` emitter can nest natively."
        )


def test_lists_nest_natively():
    """§2.2: `ol`/`ul` are the one place the open model keeps real depth."""
    nested_list = next(c for c in MATRIX if c.row == "H")
    assert validate(nested_list.document, "both").ok


def test_table_cells_reject_paragraphs():
    """§2.2: `<td>` takes inline content only — never `<p>`.

    Pinned because the `generico` emitter (Cycle 5) must emit bare inline text
    in cells, matching the reference parser's own output.
    """
    inline_cell = next(c for c in MATRIX if c.row == "N")
    paragraph_cell = next(c for c in MATRIX if c.row == "O")

    assert validate(inline_cell.document, "both").ok
    assert not validate(paragraph_cell.document, "both").ok


# ---------------------------------------------------------------------------
# Amendment A-R.2 — `requires` skips, never fails (Cycle 5b, T-22…T-24)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c.id)
def test_plan_rows_require_nothing_and_hold_on_shipped(case):
    """T-22 — the 16 §2.1 verdicts are unchanged, and unconditional.

    Two claims in one, because they are the same claim: none of the plan's
    rows names a `requires`, so none of them can be skipped by A-R.2's new
    machinery, and each still returns its documented verdict on the **shipped**
    generation. A row silently acquiring a `requires` would turn a ratified
    verdict into a skip — green, but no longer evidence — so the emptiness is
    asserted rather than assumed.
    """
    assert case.requires == "", (
        f"row {case.row} is a §2.1 plan row and must run everywhere; "
        f"it now requires {case.requires!r}, which would let it skip."
    )
    assert skip_reason(case, _capabilities(SHIPPED)) is None

    report = validate(case.document, "both", generation=SHIPPED)
    assert report.ok is case.expected, (
        f"row {case.row} ({case.encoding}) changed verdict on shipped: "
        f"expected {case.expected}, got {report.ok}"
    )


def test_requires_is_skipped_not_failed():
    """T-23 — A-R.2's mechanism: a required capability skips, never fails.

    Asserted on :func:`skip_reason` directly, against **synthesised** probe
    results, so the test states the rule rather than whatever this checkout
    happens to have: a capability that is absent yields a reason (the probe's
    diagnostic), a capability that is present yields ``None``, and a case with
    no `requires` yields ``None`` either way. A helper that always answered
    "run" fails the first assertion; one that always answered "skip" fails the
    second and third.
    """
    case = NESTED_MATRIX[0]
    assert case.requires, "T-23 needs a case that actually requires something"

    absent = SchemaCapabilities(
        generation="stand-in",
        available=True,
        nested_agrupamento=False,
        diagnostic="the recursive change is not present",
    )
    present = SchemaCapabilities(
        generation="stand-in",
        available=True,
        nested_agrupamento=True,
        diagnostic="nested rendering is available",
    )

    assert skip_reason(case, absent) == absent.diagnostic
    assert skip_reason(case, present) is None
    plain = MATRIX[0]
    assert skip_reason(plain, absent) is None
    assert skip_reason(plain, present) is None


def test_requires_skips_rather_than_fails_in_a_real_run():
    """T-23 — the same rule, observed end to end through `pytest.skip`.

    The synthesised half above proves the rule; this half proves the rule is
    the one `test_matrix_case` actually obeys. Whatever the probe reports for
    each generation, a `requires` case either **runs** (capability present) or
    raises `Skipped` (absent). It must never fail, and it must never error.
    """
    case = NESTED_MATRIX[0]

    for generation in GENERATIONS:
        capabilities = _capabilities(generation)
        supported = capabilities.available and getattr(
            capabilities, case.requires, False
        )
        try:
            _skip_unless_supported(case, generation)
        except BaseException as exc:  # pytest.skip raises Skipped
            assert isinstance(exc, Skipped), exc
            assert not supported, (
                f"{generation} reports {case.requires!r} present, "
                "yet the case was skipped"
            )
            assert capabilities.diagnostic in str(exc), (
                "a skip must carry the probe's own diagnostic, not a bare "
                f"'unsupported'; got: {exc}"
            )
        else:
            assert supported, (
                f"{generation} lacks {case.requires!r} yet the case ran — "
                "A-R.2 requires a skip here, not a failure downstream"
            )


def test_nested_cases_are_marked_and_documented():
    """T-24 — the nested surface is exactly the two cases §4.4 names."""
    assert len(NESTED_MATRIX) == 2
    assert [c.row for c in NESTED_MATRIX] == ["N1", "N2"]
    assert all(c.requires == "nested_agrupamento" for c in NESTED_MATRIX)
    assert ALL_CASES == MATRIX + NESTED_MATRIX
    assert len({c.row for c in ALL_CASES}) == len(ALL_CASES), "duplicate rows"


def test_nested_agrupamento_is_valid_where_the_capability_is_present():
    """T-24 — N1: `AH` carrying an `Agrupamento` is the §2.10 change itself.

    Runs against whichever generations report the capability, and is skipped
    (never failed) where none does — which is the point of A-R.2.
    """
    case = next(c for c in NESTED_MATRIX if c.row == "N1")
    assert case.expected is True

    ran = 0
    for generation in GENERATIONS:
        capabilities = _capabilities(generation)
        if skip_reason(case, capabilities) is not None:
            continue
        report = validate(case.document, "both", generation=generation)
        assert report.ok, (
            f"{generation} reports {case.requires!r} present, yet N1 is "
            f"invalid there: {report}"
        )
        ran += 1

    if not ran:
        pytest.skip(_capabilities(PROPOSED).diagnostic)


def test_bare_p_under_ah_is_invalid_on_every_generation():
    """T-24 — N2: §2.1 row E survives the maintainers' change.

    The change adds `Agrupamento` and `Bloco` to `AgrupamentoHierarquico`'s
    choice — **not** `p`. So prose still needs its `Agrupamento` wrapper
    (§5.4 constraint 3) on *both* generations, and this row is what proves the
    capability probe measures the right shape: probing with a bare `<p>` would
    report "no capability" against the very generation that has the change.
    """
    case = next(c for c in NESTED_MATRIX if c.row == "N2")
    assert case.expected is False

    row_e = next(c for c in MATRIX if c.row == "E")
    assert case.fragment == row_e.fragment, (
        "N2 must be row E's own encoding, re-asked of the changed schema"
    )

    checked = 0
    for generation in GENERATIONS:
        capabilities = _capabilities(generation)
        if not capabilities.available:
            continue
        report = validate(case.document, "both", generation=generation)
        assert not report.ok, (
            f"a bare <p> under AgrupamentoHierarquico validated on "
            f"{generation}: §2.1 row E has been overturned, and "
            "`_NESTED_PROBE_DOC` in validate/schema.py must be re-measured."
        )
        checked += 1

    assert checked, "no schema generation was available to check N2 against"


def test_an_unknown_requires_is_an_error_not_a_silent_skip():
    """A misspelled capability name must fail loudly, not skip forever.

    `skip_reason` reaches the capability by name, so a typo would otherwise read
    as "a capability this generation lacks" and the case would skip on **every**
    generation — a test that never runs and never says why, which is strictly
    worse than one that fails. Raised at the point of use rather than validated
    at import, so the message can name the offending case.
    """
    from .matrix_cases import MatrixCase

    typo = MatrixCase(
        "X", "typo", "<DocumentoGenerico/>", True, True,
        requires="nested_agrupamentoo",
    )
    with pytest.raises(ValueError, match="unknown capability"):
        skip_reason(typo, _capabilities(PROPOSED))


def test_capability_names_come_from_the_probe_not_a_hand_list():
    """`CAPABILITY_NAMES` tracks `SchemaCapabilities`, so it cannot drift.

    A hand-maintained list would reject a capability the probe genuinely gained,
    which is the same silent-skip failure in the other direction.
    """
    assert "nested_agrupamento" in CAPABILITY_NAMES
    assert all(
        isinstance(getattr(_capabilities(SHIPPED), name), bool)
        for name in CAPABILITY_NAMES
    )
