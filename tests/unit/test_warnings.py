"""The structured-warning channel — Cycle 8, spec §3.1 and §5.1.

Two halves. :class:`Warning` is a record with a closed code list, and the tests
for it are about the *closure*: an undeclared code must not construct, because
a diagnostic channel a caller cannot enumerate is one a caller cannot act on.

:func:`collect_warnings` is a pure function of already-computed objects, so
every test here builds the smallest stub that carries the field it is about.
That is deliberate: a test that had to parse a real document to check that an
incomplete URN warns would be testing metadata extraction, which Cycle 2
already covers, rather than the warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lexml_nonstat.warnings import (
    LOW_CONFIDENCE,
    WARNING_CODES,
    Warning,
    collect_warnings,
)


# ---------------------------------------------------------------------------
# stubs — the shapes `collect_warnings` reads, and nothing more
# ---------------------------------------------------------------------------


@dataclass
class _Styled:
    blocks: tuple = ()


@dataclass
class _Metadata:
    complete: bool = True
    missing: tuple[str, ...] = ()


@dataclass
class _Body:
    flat: bool = False
    confidence: float = 0.9


@dataclass
class _Viability:
    confidence: float = 0.95
    referee_consulted: bool = False
    referee_overrode: bool = False


@dataclass
class _Model:
    styled: _Styled = field(default_factory=lambda: _Styled(blocks=(object(),)))
    metadata: _Metadata = field(default_factory=_Metadata)
    body: _Body = field(default_factory=_Body)
    viability: _Viability = field(default_factory=_Viability)
    route: str = "generico"
    source: str | None = "doc.docx"


@dataclass
class _Rendered:
    emitter: str = "generico"
    annexes: tuple = ()


@dataclass
class _Report:
    ok: bool = True
    lines: tuple[str, ...] = ()

    def summary(self) -> str:
        return "\n".join(self.lines)


def _codes(warnings) -> set[str]:
    return {w.code for w in warnings}


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", WARNING_CODES)
def test_every_declared_code_constructs(code: str) -> None:
    assert Warning(code, "detail").code == code


def test_unknown_code_rejected() -> None:
    with pytest.raises(ValueError) as exc:
        Warning("definitely_not_a_code", "detail")
    assert "definitely_not_a_code" in str(exc.value)


def test_unknown_code_error_names_the_declared_codes() -> None:
    """A rejection that does not say what *is* allowed costs a source dive."""
    with pytest.raises(ValueError) as exc:
        Warning("nope", "detail")
    for code in WARNING_CODES:
        assert code in str(exc.value)


def test_codes_are_a_tuple_with_no_duplicates() -> None:
    assert isinstance(WARNING_CODES, tuple)
    assert len(set(WARNING_CODES)) == len(WARNING_CODES)


def test_format_is_one_line_with_the_source() -> None:
    line = Warning("flat_fallback", "no structure", "a.docx").format()
    assert line == "warning: a.docx: flat_fallback: no structure"
    assert "\n" not in line


def test_format_omits_an_absent_source() -> None:
    assert Warning("flat_fallback", "d").format() == "warning: flat_fallback: d"


def test_to_dict_carries_exactly_three_fields() -> None:
    assert Warning("flat_fallback", "d", "s").to_dict() == {
        "code": "flat_fallback",
        "detail": "d",
        "source": "s",
    }


def test_warning_is_frozen() -> None:
    warning = Warning("flat_fallback", "d")
    with pytest.raises(Exception):
        warning.code = "other"  # type: ignore[misc]


def test_warning_is_not_an_exception() -> None:
    """The name shadows the builtin; the *type* must not be confusable with it.

    Spec §7's risk: someone later writing ``except Warning:`` and meaning the
    builtin. This asserts the two are unrelated, so such a line is a type error
    rather than a silently-never-matching handler.
    """
    import builtins

    assert not issubclass(Warning, BaseException)
    assert Warning is not builtins.Warning


# ---------------------------------------------------------------------------
# collection
# ---------------------------------------------------------------------------


def test_clean_document_warns_about_nothing() -> None:
    assert collect_warnings(_Model(), _Rendered()) == ()


def test_empty_document() -> None:
    model = _Model(styled=_Styled(blocks=()))
    assert "empty_document" in _codes(collect_warnings(model))


def test_incomplete_urn_names_what_is_missing() -> None:
    model = _Model(metadata=_Metadata(complete=False, missing=("date", "number")))
    warnings = collect_warnings(model)
    assert "incomplete_urn" in _codes(warnings)
    detail = next(w.detail for w in warnings if w.code == "incomplete_urn")
    assert "date" in detail and "number" in detail


def test_flat_fallback() -> None:
    model = _Model(body=_Body(flat=True, confidence=0.2))
    assert "flat_fallback" in _codes(collect_warnings(model))


def test_structured_body_does_not_warn() -> None:
    assert "flat_fallback" not in _codes(collect_warnings(_Model()))


def test_low_confidence() -> None:
    model = _Model(viability=_Viability(confidence=LOW_CONFIDENCE - 0.01))
    assert "low_confidence" in _codes(collect_warnings(model))


def test_confidence_exactly_at_the_threshold_does_not_warn() -> None:
    """The boundary is a decision, so it is pinned rather than left to drift."""
    model = _Model(viability=_Viability(confidence=LOW_CONFIDENCE))
    assert "low_confidence" not in _codes(collect_warnings(model))


def test_statutory_fallback_on_the_auto_route() -> None:
    """A-6.3: `RenderedDocument.emitter` is what makes a fallback visible."""
    model = _Model(route="norma")
    rendered = _Rendered(emitter="generico")
    assert "statutory_fallback" in _codes(collect_warnings(model, rendered))


def test_statutory_success_does_not_warn() -> None:
    model = _Model(route="norma")
    rendered = _Rendered(emitter="norma")
    assert "statutory_fallback" not in _codes(collect_warnings(model, rendered))


def test_statutory_fallback_when_norma_was_forced() -> None:
    model = _Model(route="generico")
    warnings = collect_warnings(
        model, _Rendered(emitter="generico"), requested_emitter="norma"
    )
    assert "statutory_fallback" in _codes(warnings)


def test_forcing_generico_on_a_norma_route_is_not_a_fallback() -> None:
    """Asking for flat and getting flat is the caller's own choice, not a failure."""
    model = _Model(route="norma")
    warnings = collect_warnings(
        model, _Rendered(emitter="generico"), requested_emitter="generico"
    )
    assert "statutory_fallback" not in _codes(warnings)


def test_annexes_not_written_counts_them() -> None:
    rendered = _Rendered(annexes=(object(), object()))
    warnings = collect_warnings(_Model(), rendered, wrote_annexes=False)
    assert "annexes_not_written" in _codes(warnings)
    detail = next(w.detail for w in warnings if w.code == "annexes_not_written")
    assert "2" in detail


def test_written_annexes_do_not_warn() -> None:
    rendered = _Rendered(annexes=(object(),))
    warnings = collect_warnings(_Model(), rendered, wrote_annexes=True)
    assert "annexes_not_written" not in _codes(warnings)


def test_invalid_output_carries_the_first_summary_line() -> None:
    report = _Report(ok=False, lines=("rigido: line 3: bad element", "and more"))
    warnings = collect_warnings(_Model(), _Rendered(), report=report)
    assert "invalid_output" in _codes(warnings)
    detail = next(w.detail for w in warnings if w.code == "invalid_output")
    assert detail == "rigido: line 3: bad element"


def test_valid_output_does_not_warn() -> None:
    warnings = collect_warnings(_Model(), _Rendered(), report=_Report(ok=True))
    assert "invalid_output" not in _codes(warnings)


def test_every_warning_carries_the_source() -> None:
    model = _Model(
        source="x.docx",
        body=_Body(flat=True),
        metadata=_Metadata(complete=False, missing=("date",)),
    )
    warnings = collect_warnings(model, _Rendered(annexes=(object(),)))
    assert warnings
    assert all(w.source == "x.docx" for w in warnings)


def test_collect_never_raises_on_absent_arguments() -> None:
    assert collect_warnings(None) == ()
    assert collect_warnings(None, None, report=None) == ()


def test_collect_survives_a_model_missing_every_field() -> None:
    """The degenerate case Cycle 8 exists for: a stub with nothing on it."""

    class _Bare:
        pass

    assert isinstance(collect_warnings(_Bare(), _Bare()), tuple)


def test_collect_returns_a_tuple() -> None:
    assert isinstance(collect_warnings(_Model()), tuple)


def test_every_emitted_code_is_declared() -> None:
    """Nothing may reach the operator that `WARNING_CODES` does not name."""
    model = _Model(
        styled=_Styled(blocks=()),
        metadata=_Metadata(complete=False, missing=("date",)),
        body=_Body(flat=True),
        viability=_Viability(confidence=0.1),
        route="norma",
    )
    warnings = collect_warnings(
        model,
        _Rendered(emitter="generico", annexes=(object(),)),
        report=_Report(ok=False, lines=("bad",)),
    )
    assert len(warnings) >= 6
    assert _codes(warnings) <= set(WARNING_CODES)
