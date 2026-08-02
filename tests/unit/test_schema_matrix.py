"""The §2.1 encoding matrix, executed against both schemas.

This is the cycle's headline deliverable: the investigation's central table
stops being prose and becomes an assertion. Every design decision downstream —
flat `generico` output, hierarchy in the `id` path, inline-only table cells —
rests on one of these rows.
"""

from __future__ import annotations

import pytest
from lxml import etree

from lexml_nonstat.validate import SCHEMA_NAMES, load_schema, validate

from .matrix_cases import MATRIX, PLAN_ROW_COUNT


@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c.id)
@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_matrix_case(case, schema_name):
    """Each §2.1 encoding validates (or fails) exactly as the plan documents."""
    schema = load_schema(schema_name)
    document = etree.fromstring(case.document.encode("utf-8"))

    assert schema.validate(document) is case.expected, (
        f"row {case.row} ({case.encoding}) on {schema_name}: "
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
