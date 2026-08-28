"""Path-composed ids: Rule A held by construction, and the checker that proves it.

:mod:`lexml_nonstat.render.ids` is small, and that is the point — it is the one
place in the emitter where an ``xsd:ID`` comes from. Two probed schema facts
(Cycle 5 spec §2) make it load-bearing rather than clerical:

* ``xsd:ID`` is an ``NCName``, so an id may not begin with a digit. ``1pp`` is
  rejected by **both** shipped schemas, and a renderer that composed a numeric
  token into the head of an id would produce a document nothing accepts.
* ``xsd:ID`` is unique document-wide. The schema does catch a collision — but
  only after the document has been written, and only if someone validates. The
  allocator refuses one at the moment it would be created.

**Rule A** (plan §2.4) says every proper ``_``-separated prefix of an
``Agrupamento`` id must itself exist as an ``Agrupamento``: that is what lets
Cycle 7 rebuild the tree from a flat document by longest-prefix matching, and
therefore what makes invariant #3 (reversibility) reachable at all. The
allocator makes it structural — :meth:`IdAllocator.child` refuses a parent it
has not issued — and :func:`missing_prefixes` is the independent checker.

A checker is only worth having if it can fail. Spec §8's third risk row is
exactly that: "Rule A silently broken by a future emitter change", mitigated by
a **positive** test. :func:`test_missing_prefixes_detects_a_gap` is that test —
it feeds a deliberately gapped id set and requires a complaint, so
``missing_prefixes`` cannot rot into ``return ()`` while every other Rule A test
in the suite stays green.
"""

from __future__ import annotations

import re

import pytest

from lexml_nonstat.render.ids import (
    ID_RE,
    IdAllocator,
    compose,
    is_valid_id,
    missing_prefixes,
    path_prefixes,
)

#: An id must start with a letter, not merely with an ``NCName`` start char.
#: ``ID_RE`` also admits a leading underscore; nothing this package emits uses
#: one, and asserting the stricter property catches a token that begins with a
#: digit *and* one that begins with punctuation.
_STARTS_WITH_LETTER = re.compile(r"^[A-Za-z]")


# ---------------------------------------------------------------------------
# compose / path_prefixes — the Rule A machinery
# ---------------------------------------------------------------------------


def test_compose_and_path_prefixes() -> None:
    """The two halves of the path scheme are exact inverses of each other.

    ``compose`` builds ``pp1_agr1_agr2`` from its parts; ``path_prefixes``
    recovers the ancestors it was built from — ``("pp1", "pp1_agr1")``, shortest
    first, and **never the id itself**: Rule A constrains ancestors, and an id
    that had to be its own ancestor could never be satisfied.
    """
    assert compose("pp1", "agr1", "agr2") == "pp1_agr1_agr2"
    assert path_prefixes("pp1_agr1_agr2") == ("pp1", "pp1_agr1")

    # Every prefix is itself composable from the same parts — the scheme is
    # closed, which is what makes longest-prefix reconstruction well-defined.
    assert path_prefixes(compose("pp1", "agr7")) == ("pp1",)


def test_compose_skips_empty_parts() -> None:
    """Empty parts vanish rather than producing ``__`` or a trailing ``_``.

    Callers compose from optional fragments (an annex base, a token, an
    ordinal); a missing one must not leave a separator behind, because
    ``pp1__agr1`` and ``pp1_agr1`` would be two different ids for one element.
    """
    assert compose("pp1", "", "agr1") == "pp1_agr1"
    assert compose("", "pp1") == "pp1"
    assert compose("pp1", "") == "pp1"
    assert compose() == ""


def test_path_prefixes_of_a_root_has_no_ancestors() -> None:
    """A single-token id is a root: it has no proper prefix, so Rule A is
    vacuously satisfied for it and the checker must not invent one."""
    assert path_prefixes("pp1") == ()
    assert path_prefixes("anexo1") == ()


def test_is_valid_id_rejects_what_the_schemas_reject() -> None:
    """``is_valid_id`` agrees with the probed ``NCName`` facts (spec §2).

    The row that matters is "id beginning with a digit → **INVALID**". The
    others are the cheap neighbours of it: an empty id, an id with a space, an
    id with a colon (which would be read as a namespace prefix).
    """
    assert is_valid_id("pp1")
    assert is_valid_id("pp1_agr1_agr2")
    assert is_valid_id("anexo1_tab3")

    assert not is_valid_id("1pp")          # NCName may not start with a digit
    assert not is_valid_id("")             # nor be empty
    assert not is_valid_id("pp1 agr1")     # nor contain a space
    assert not is_valid_id("lex:pp1")      # nor a colon


# ---------------------------------------------------------------------------
# IdAllocator
# ---------------------------------------------------------------------------


def test_allocator_issues_its_root_immediately() -> None:
    """The root is taken at construction, not on first use.

    ``child(root, …)`` is only legal because the root has already been issued;
    if construction left it unclaimed, Rule A's base case would be a special
    case rather than an instance of the general one.
    """
    allocator = IdAllocator("pp1")
    assert allocator.root == "pp1"
    assert allocator.issued == ("pp1",)
    assert "pp1" in allocator
    assert len(allocator) == 1


def test_allocator_refuses_duplicate() -> None:
    """The same id twice is a ``ValueError``, not a silently reused id.

    Invariant #5. Both schemas type ``id`` as ``xsd:ID`` and would reject the
    finished document — but a duplicate discovered at validation time has
    already been written into two places, and nothing says which one was meant.
    """
    allocator = IdAllocator("pp1")
    allocator.take("pp1_agr1")

    with pytest.raises(ValueError, match="duplicate"):
        allocator.take("pp1_agr1")

    # The refused id was not appended a second time.
    assert allocator.issued == ("pp1", "pp1_agr1")

    # The root is registered, so re-taking it is a duplicate too.
    with pytest.raises(ValueError, match="duplicate"):
        allocator.take("pp1")


def test_allocator_refuses_a_non_ncname() -> None:
    """A syntactically invalid id is refused at the point of allocation.

    The probed fact is that both schemas reject an id beginning with a digit;
    catching it here means the emitter never gets far enough to write one.
    """
    allocator = IdAllocator("pp1")
    with pytest.raises(ValueError, match="not a valid xsd:ID"):
        allocator.take("1agr")
    with pytest.raises(ValueError, match="not a valid xsd:ID"):
        allocator.take("")


def test_allocator_rejects_a_root_that_is_not_an_ncname() -> None:
    """A bad root would poison every id composed from it, so it fails at
    construction rather than producing a document-wide fault."""
    with pytest.raises(ValueError, match="root id is not a valid xsd:ID"):
        IdAllocator("1pp")


def test_child_ids_are_path_composed() -> None:
    """``child`` appends ``{token}{n}`` to the *parent's own id* — plan §2.3.

    The counter is per ``(parent, token)`` pair, so siblings number from 1 under
    each parent independently and the id encodes the path, not a global
    sequence. That is what makes ``id.count("_")`` a redundant channel for the
    section's depth (spec §5.1's three channels).
    """
    allocator = IdAllocator("pp1")
    first = allocator.next("agr")
    assert first == "pp1_agr1"

    assert allocator.child("pp1_agr1") == "pp1_agr1_agr1"
    assert allocator.child("pp1_agr1") == "pp1_agr1_agr2"

    # A second parent starts its own children at 1 — the counter is not global.
    second = allocator.next("agr")
    assert second == "pp1_agr2"
    assert allocator.child(second) == "pp1_agr2_agr1"

    # Depth is readable straight off the id.
    assert "pp1_agr1_agr2".count("_") == 2


def test_child_tokens_count_independently() -> None:
    """``agr`` and ``tab`` under the same parent keep separate ordinals, so a
    table never consumes an ``Agrupamento``'s number (spec D-4)."""
    allocator = IdAllocator("pp1")
    assert allocator.next("agr") == "pp1_agr1"
    assert allocator.next("tab") == "pp1_tab1"
    assert allocator.next("agr") == "pp1_agr2"
    assert allocator.next("tab") == "pp1_tab2"


def test_child_on_an_unissued_parent_raises() -> None:
    """This is the mechanism that makes Rule A structural.

    A child may only be composed from an id the allocator has already issued.
    If an unissued parent were allowed, ``pp1_agr7_agr1`` could be written while
    ``pp1_agr7`` never existed — precisely the gap
    :func:`missing_prefixes` is there to detect, created by the very component
    that is supposed to make it impossible.
    """
    allocator = IdAllocator("pp1")
    with pytest.raises(ValueError, match="unknown parent"):
        allocator.child("pp1_agr7")

    # And once the parent genuinely exists, the same call succeeds.
    allocator.take("pp1_agr7")
    assert allocator.child("pp1_agr7") == "pp1_agr7_agr1"


def test_peek_and_advance_continue_a_sequence() -> None:
    """``advance`` reserves ordinals another module already emitted (spec D-1).

    Cycle 3's ``render_front_generico`` writes ``pp1_agr1…pp1_agr{k}`` itself.
    The emitter's allocator did not issue those, so without ``advance`` its
    first section would be ``pp1_agr1`` again — a duplicate id in the finished
    document. ``advance`` moves the counter past them without claiming the
    names, and ``peek`` reports where the counter stands.
    """
    allocator = IdAllocator("pp1")
    assert allocator.peek("pp1", "agr") == 0

    allocator.advance("pp1", "agr", 4)
    assert allocator.peek("pp1", "agr") == 4
    assert allocator.next("agr") == "pp1_agr5"
    assert allocator.peek("pp1", "agr") == 5

    # Advancing backwards is a no-op: the counter never loses ground, because
    # rewinding it would hand out an ordinal that is already in the document.
    allocator.advance("pp1", "agr", 2)
    assert allocator.peek("pp1", "agr") == 5
    assert allocator.next("agr") == "pp1_agr6"


def test_every_issued_id_is_ncname() -> None:
    """A thousand allocations, every one of them a legal ``xsd:ID``.

    Volume matters here: the schema fact being defended is about the *first
    character*, and it only bites on ids the corpus's fifteen documents happen
    not to produce. Allocating deep and wide over several tokens exercises
    ordinals past 9, past 99 and a five-level path.
    """
    allocator = IdAllocator("pp1")
    parents = [allocator.next("agr") for _ in range(160)]
    for parent in parents[:100]:
        for _ in range(8):
            allocator.child(parent, "agr")
    for parent in parents[:40]:
        allocator.child(parent, "tab")
    deep = parents[0]
    for _ in range(5):
        deep = allocator.child(deep, "agr")

    issued = allocator.issued
    assert len(issued) >= 1000
    assert len(set(issued)) == len(issued), "an id was issued twice"

    for ident in issued:
        assert ID_RE.match(ident), f"not an NCName: {ident!r}"
        assert _STARTS_WITH_LETTER.match(ident), f"does not start with a letter: {ident!r}"
        assert is_valid_id(ident)

    # The allocation really did go deep and wide, or the assertions above would
    # be checking a handful of shallow ids: a three-digit ordinal and a
    # seven-token path both occur.
    assert "pp1_agr160" in issued
    assert max(i.count("_") for i in issued) >= 6
    assert any(re.search(r"_agr1\d\d$", i) for i in issued)

    # Deep and wide, and still gapless.
    assert missing_prefixes(issued, root="pp1") == ()


# ---------------------------------------------------------------------------
# missing_prefixes — Rule A's checker
# ---------------------------------------------------------------------------


def test_missing_prefixes_detects_a_gap() -> None:
    """**Rule A regression.** A gapped id set must be reported, not tolerated.

    ``pp1_agr1_agr2_agr1`` claims an ancestor ``pp1_agr1_agr2`` that no element
    provides. If ``missing_prefixes`` returned ``()`` here it would be a no-op,
    and every other Rule A assertion in the suite — including the whole-corpus
    ``test_rule_a_every_prefix_exists`` — would pass vacuously for ever. This
    test is the reason the checker cannot rot (spec §8).
    """
    ids = {"pp1", "pp1_agr1", "pp1_agr1_agr2_agr1"}
    assert missing_prefixes(ids, root="pp1") == ("pp1_agr1_agr2",)

    # Filling the gap silences the checker — the complaint is about this
    # specific ancestor, not a blanket refusal of deep ids.
    assert missing_prefixes(ids | {"pp1_agr1_agr2"}, root="pp1") == ()


def test_missing_prefixes_reports_several_gaps_sorted() -> None:
    """More than one gap comes back sorted, so an assertion message is stable
    and a diff between two runs is a real change rather than set ordering."""
    ids = {"pp1", "pp1_agr9_agr1", "pp1_agr2_agr3_agr4"}
    assert missing_prefixes(ids, root="pp1") == (
        "pp1_agr2",
        "pp1_agr2_agr3",
        "pp1_agr9",
    )


def test_missing_prefixes_ignores_the_root_and_anything_outside_it() -> None:
    """The ``PartePrincipal``'s own id is a prefix of every path but is not an
    ``Agrupamento``, so prefixes at or above the root are not required to exist;
    and ids belonging to another document's scope are not this root's business.

    ``anexo1_pp_agr1`` is a real id — an annex is a separate ``xsd:ID`` scope
    with its own root — and checking it against ``pp1`` must not manufacture a
    complaint about ``anexo1_pp``.
    """
    assert missing_prefixes({"pp1_agr1"}, root="pp1") == ()
    assert missing_prefixes({"pp1", "pp1_agr1", "anexo1_pp_agr1"}, root="pp1") == ()
    assert missing_prefixes((), root="pp1") == ()


def test_missing_prefixes_empty_on_allocator_output() -> None:
    """Rule A by construction: an allocator-built tree has no gaps, ever.

    The tree below is the shape the flat emitter actually produces — regions and
    sections as root-level siblings, descendants as path-composed siblings, and
    tables interleaved on their own token — so this is the unit-level statement
    of the whole-corpus ``test_rule_a_every_prefix_exists``.
    """
    allocator = IdAllocator("pp1")
    for _ in range(3):
        allocator.next("agr")
    section = allocator.next("agr")
    child = allocator.child(section)
    grandchild = allocator.child(child)
    allocator.child(grandchild)
    allocator.child(section)
    allocator.next("tab")
    allocator.next("tab")

    assert missing_prefixes(allocator.issued, root=allocator.root) == ()

    # Removing one interior id from the *reported* set is enough to break it,
    # which shows the assertion above is a property of the ids and not of the
    # checker being generous.
    gapped = [i for i in allocator.issued if i != child]
    assert missing_prefixes(gapped, root=allocator.root) == (child,)
