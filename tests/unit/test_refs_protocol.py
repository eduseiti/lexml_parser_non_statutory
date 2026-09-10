"""The linker contract — the answer shape, the default, and the constant.

Cycle 8e, amendments A-L.1 and A-L.9. Nothing here needs a binary: the
protocol's whole point is that a caller can hold a linker without knowing
whether one exists.
"""

from __future__ import annotations

import pytest

from lexml_nonstat.refs import (
    DEFAULT_CONTEXT_URN,
    LINKER_MODES,
    Linker,
    LinkerCache,
    NullLinker,
    Reference,
    build_linker,
)


def test_null_linker_satisfies_the_protocol():
    """T-P1 — a `NullLinker` is a `Linker`, structurally."""
    linker = NullLinker()
    assert isinstance(linker, Linker)
    assert linker.name == "none"
    assert linker.enabled is False


def test_null_linker_resolves_nothing():
    """T-P1 — and it says so with an empty tuple, never an exception."""
    linker = NullLinker()
    assert linker.find_refs("A Lei nº 7.713, de 1988 dispõe.") == ()
    assert linker.find_refs("") == ()
    linker.close()  # present, and a no-op


def test_reference_round_trips():
    """T-P2 — `to_dict`/`from_dict` is the fixture format's whole contract."""
    reference = Reference(2, 23, "urn:lex:br:federal:lei:1988-12-22;7713", "Lei nº 7.713")
    assert Reference.from_dict(reference.to_dict()) == reference


def test_reference_from_dict_tolerates_a_partial_entry():
    """A hand-edited fixture must not crash the reader."""
    assert Reference.from_dict({}) == Reference(0, 0, "", "")
    assert Reference.from_dict({"start": 1, "end": 4, "urn": "u"}).text == ""


def test_references_sort_by_position():
    """T-P2 — ordering is on the dataclass, so no call site re-derives it.

    Invariant #4 is not a thing to re-implement per module: a backend that
    returns spans in an arbitrary order must still render deterministically.
    """
    late = Reference(10, 20, "urn:b", "b")
    early = Reference(2, 8, "urn:a", "a")
    assert sorted((late, early)) == [early, late]


def test_reference_is_empty():
    assert Reference(5, 5, "u", "").is_empty
    assert Reference(5, 4, "u", "").is_empty
    assert not Reference(4, 5, "u", "x").is_empty


def test_default_context_urn_is_the_federal_lei_sentinel():
    """T-P3 — A-L.9's constant, pinned exactly.

    This is not cosmetic. A non-``federal`` authority makes the linker resolve
    **nothing**, silently, and every one of the 15 samples carries one — so a
    change to this string would turn the whole feature off while every test
    that only checks "a linker was configured" kept passing.
    """
    assert DEFAULT_CONTEXT_URN == "urn:lex:br:federal:lei:2000-01-01;1"


def test_build_linker_none_is_the_null_linker():
    """T-P4 — the default everywhere, and an object rather than `None`."""
    assert isinstance(build_linker(), NullLinker)
    assert isinstance(build_linker("none"), NullLinker)


def test_build_linker_rejects_a_mode_that_is_not_a_path(tmp_path):
    """T-P4 — `fixtures` without a read-only cache is a misuse, not a default.

    A typo must not silently disable linking, which is `build_referee`'s rule
    and the reason it raises on an unknown mode.
    """
    with pytest.raises(ValueError, match="cache"):
        build_linker("fixtures")

    with pytest.raises(ValueError, match="read-only"):
        build_linker("fixtures", cache=LinkerCache(tmp_path))


def test_linker_modes_are_the_documented_three():
    """The CLI validates against this tuple, so it is part of the contract."""
    assert LINKER_MODES == ("none", "auto", "fixtures")


def test_auto_degrades_to_null_without_a_binary(monkeypatch):
    """T-X5 — `auto` on a bare checkout is a `NullLinker`, never an error.

    A-L.5: the linker is the third external thing this repository works
    without. `auto` means "use it if it is here", and a checkout where it is
    not must render exactly as `none` does.
    """
    import lexml_nonstat.refs as refs

    monkeypatch.setattr(
        refs,
        "probe_linker",
        lambda binary=None: refs.LinkerCapabilities(
            False, "", "", "linkertool unavailable: nothing here"
        ),
    )
    assert isinstance(build_linker("auto"), NullLinker)
