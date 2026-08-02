"""`ValidationReport` semantics: `ok` iff every consulted schema passed."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.validate import (
    SCHEMA_NAMES,
    SchemaResult,
    ValidationReport,
    validate,
)

from tests.conftest import lexml_doc


def test_minimal_generico_validates(minimal_generico):
    """The smallest non-statutory document is valid on both schemas."""
    report = validate(minimal_generico, "both")
    assert report.ok, report.summary()
    assert report.failed == ()


def test_nested_agrupamento_rejected(nested_agrupamento):
    """§2.1's core finding, through the public API: Agrupamento cannot nest."""
    report = validate(nested_agrupamento, "both")

    assert not report.ok
    assert set(report.failed) == set(SCHEMA_NAMES), (
        "both schemas should reject nesting"
    )


def test_ok_true_when_both_pass(minimal_generico):
    report = validate(minimal_generico, "both")
    assert len(report.results) == 2
    assert all(r.valid for r in report.results)
    assert report.ok


@pytest.mark.parametrize("failing", SCHEMA_NAMES)
def test_ok_false_when_either_fails(failing):
    """`ok` requires unanimity — one dissenting schema is enough to fail."""
    results = tuple(
        SchemaResult(name, valid=(name != failing), errors=() if name != failing
                     else ("synthetic error",))
        for name in SCHEMA_NAMES
    )
    report = ValidationReport(results)

    assert not report.ok
    assert report.failed == (failing,)


def test_per_schema_errors_surfaced(nested_agrupamento):
    """Errors are attributable to the schema that raised them."""
    report = validate(nested_agrupamento, "both")

    for name in SCHEMA_NAMES:
        errors = report.errors_for(name)
        assert errors, f"{name} rejected the document but reported no error"
        assert any("Agrupamento" in e for e in errors), (
            f"{name} errors should name the offending element: {errors}"
        )


def test_valid_document_reports_no_errors(minimal_generico):
    report = validate(minimal_generico, "both")
    assert report.all_errors == ()


def test_all_errors_are_tagged_by_schema(nested_agrupamento):
    report = validate(nested_agrupamento, "both")
    assert all(e.startswith(("[rigido]", "[flexivel]")) for e in report.all_errors)


@pytest.mark.parametrize("selector", SCHEMA_NAMES)
def test_single_schema_selection_reports_one_result(minimal_generico, selector):
    """A narrow selection is judged only on what it consulted."""
    report = validate(minimal_generico, selector)

    assert report.schemas == (selector,)
    assert report.ok


def test_report_bool_matches_ok(minimal_generico, nested_agrupamento):
    assert bool(validate(minimal_generico, "both")) is True
    assert bool(validate(nested_agrupamento, "both")) is False


def test_empty_report_is_not_ok():
    """Nothing verified proves nothing."""
    assert not ValidationReport(()).ok


def test_result_for_unknown_schema_raises(minimal_generico):
    report = validate(minimal_generico, "rigido")
    with pytest.raises(KeyError):
        report.errors_for("flexivel")


def test_summary_mentions_each_schema(minimal_generico):
    summary = validate(minimal_generico, "both").summary()
    for name in SCHEMA_NAMES:
        assert name in summary


def test_summary_includes_failure_detail(nested_agrupamento):
    summary = validate(nested_agrupamento, "both").summary()
    assert "INVALID" in summary
    assert "Agrupamento" in summary


def test_accepts_str_bytes_path_and_element(tmp_path, minimal_generico):
    """All four input forms agree, so callers need not pre-convert."""
    path = tmp_path / "doc.xml"
    path.write_text(minimal_generico, encoding="utf-8")

    forms = {
        "str": minimal_generico,
        "bytes": minimal_generico.encode("utf-8"),
        "path": path,
        "element": etree.fromstring(minimal_generico.encode("utf-8")),
        "tree": etree.parse(str(path)),
        "path-as-str": str(path),
    }

    for label, form in forms.items():
        assert validate(form, "both").ok, f"{label} input failed to validate"


def test_malformed_xml_reported_not_raised():
    """A broken document yields a failing report, not an exception."""
    report = validate("<not-well-formed", "both")

    assert not report.ok
    assert report.schemas == SCHEMA_NAMES
    for name in SCHEMA_NAMES:
        assert any("well-formed" in e for e in report.errors_for(name))


def test_unsupported_input_type_raises():
    with pytest.raises(TypeError):
        validate(42, "both")


def test_reports_are_frozen(minimal_generico):
    """Results are immutable, so a report cannot be doctored after the fact."""
    report = validate(minimal_generico, "both")
    with pytest.raises(Exception):
        report.results[0].valid = False


def test_validation_is_repeatable(minimal_generico, nested_agrupamento):
    """Invariant #4 (determinism), at the validation layer.

    lxml's error log is per-schema mutable state, so a cached schema must not
    leak errors from one call into the next.
    """
    assert validate(minimal_generico, "both").ok
    assert not validate(nested_agrupamento, "both").ok
    # The valid document must still pass after a failure went through.
    again = validate(minimal_generico, "both")
    assert again.ok, f"stale error state leaked: {again.summary()}"
    assert again.all_errors == ()


def test_document_without_metadado_is_rejected():
    """LexML requires Metadado; a bare body is not a document."""
    bare = (
        '<LexML xmlns="http://www.lexml.gov.br/1.0">'
        '<DocumentoGenerico><PartePrincipal id="pp1"><p>T</p></PartePrincipal>'
        "</DocumentoGenerico></LexML>"
    )
    assert not validate(bare, "both").ok


def test_anexo_reference_shape_validates():
    """§4.3: the parent's pointer at a sibling annex document.

    Pinned now because Cycle 6 builds the Norma+Anexo split on it.
    """
    document = lexml_doc(
        '<DocumentoGenerico><PartePrincipal id="pp1"><p>Texto</p></PartePrincipal>'
        '<Anexos><ReferenciaAnexo '
        'AlvoURN="urn:lex:br:federal:parecer:2018-12-28;93!anexo1"/></Anexos>'
        "</DocumentoGenerico>"
    )
    assert validate(document, "both").ok
