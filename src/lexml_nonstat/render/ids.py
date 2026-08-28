"""Path-composed, unique, ``xsd:ID``-safe identifiers — plan §2.3, Rule A.

Two schema facts drive this module, both measured rather than assumed:

* ``Agrupamento``'s ``id`` is typed ``xsd:ID`` via ``corereq``, **not**
  constrained to ``idAgregador``. The path scheme is therefore ours to choose,
  and uniqueness is ours to enforce — the schema will catch a collision, but
  only after we have already written the document.
* ``xsd:ID`` is an ``NCName``: an id may not begin with a digit. ``pp1_agr1``
  is legal; ``1pp`` is not, and both schemas reject it.

**Rule A** (plan §2.4) says every proper prefix of an ``Agrupamento`` id must
exist as an ``Agrupamento``. Here it holds *by construction*: a child id is only
ever composed from a parent id the allocator has already issued, so a gap
cannot be created. :func:`missing_prefixes` is the independent checker that
proves it after the fact — kept public, and kept honest by a test that feeds it
a deliberately gapped set and requires it to complain.
"""

from __future__ import annotations

import re
from typing import Iterable

__all__ = [
    "ID_RE",
    "IdAllocator",
    "compose",
    "is_valid_id",
    "missing_prefixes",
    "path_prefixes",
]

#: ``xsd:ID`` is an ``NCName``: letter or underscore first, then name chars.
#: Deliberately narrower than the XML spec — this is what *we* emit, and a
#: conservative pattern is a check, not a limitation.
ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def is_valid_id(value: str) -> bool:
    """Whether ``value`` may be used as an ``xsd:ID``."""
    return bool(value) and bool(ID_RE.match(value))


def compose(*parts: str) -> str:
    """Join id parts with ``_``, skipping empty ones.

    ``compose("pp1", "agr1")`` → ``"pp1_agr1"``.
    """
    return "_".join(p for p in parts if p)


def path_prefixes(ident: str) -> tuple[str, ...]:
    """Every proper ``_``-separated prefix of ``ident``, shortest first.

    ``"pp1_agr1_agr2"`` → ``("pp1", "pp1_agr1")``. The id itself is never
    included: Rule A is about *ancestors*.
    """
    parts = ident.split("_")
    return tuple("_".join(parts[: i + 1]) for i in range(len(parts) - 1))


def missing_prefixes(ids: Iterable[str], *, root: str) -> tuple[str, ...]:
    """Rule A's checker: prefixes below ``root`` that nothing claims.

    ``root`` is the ``PartePrincipal``'s id, which is a prefix of every path but
    is not itself an ``Agrupamento`` — so prefixes at or above it are not
    required to exist. Anything strictly between ``root`` and an id is.

    Returns the missing prefixes, sorted, or ``()`` when the set is complete.
    """
    present = set(ids)
    gaps: set[str] = set()
    for ident in present:
        if not ident.startswith(f"{root}_"):
            continue
        for prefix in path_prefixes(ident):
            if len(prefix) <= len(root):
                continue
            if prefix not in present:
                gaps.add(prefix)
    return tuple(sorted(gaps))


class IdAllocator:
    """Issues every id in one document, and refuses to issue one twice.

    One allocator per emitted document — the primary and each annex are
    separate documents with separate ``xsd:ID`` scopes, so each gets its own.
    """

    def __init__(self, root: str = "pp1") -> None:
        if not is_valid_id(root):
            raise ValueError(f"root id is not a valid xsd:ID: {root!r}")
        self.root = root
        self._issued: list[str] = []
        self._seen: set[str] = set()
        self._counters: dict[tuple[str, str], int] = {}
        self.take(root)

    def take(self, ident: str) -> str:
        """Register ``ident`` as used. Raises on a duplicate or a bad name."""
        if not is_valid_id(ident):
            raise ValueError(f"not a valid xsd:ID: {ident!r}")
        if ident in self._seen:
            raise ValueError(f"duplicate id: {ident!r}")
        self._seen.add(ident)
        self._issued.append(ident)
        return ident

    def child(self, parent: str, token: str = "agr") -> str:
        """The next ``{parent}_{token}{n}`` under ``parent``.

        ``parent`` must already have been issued: that is what makes Rule A
        structural rather than aspirational.
        """
        if parent not in self._seen:
            raise ValueError(f"unknown parent id: {parent!r}")
        key = (parent, token)
        self._counters[key] = self._counters.get(key, 0) + 1
        return self.take(f"{parent}_{token}{self._counters[key]}")

    def next(self, token: str) -> str:
        """The next root-level sibling id, e.g. ``pp1_tab3``."""
        return self.child(self.root, token)

    def peek(self, parent: str, token: str = "agr") -> int:
        """How many ``token`` children ``parent`` has been given so far."""
        return self._counters.get((parent, token), 0)

    def advance(self, parent: str, token: str, count: int) -> None:
        """Reserve ``count`` ordinals under ``parent`` without issuing them.

        Used where another module already emitted ids on the same scheme —
        Cycle 3's front-matter ``Agrupamento``s — so this allocator continues
        the sequence rather than colliding with it (spec decision D-1).
        """
        key = (parent, token)
        self._counters[key] = max(self._counters.get(key, 0), count)

    @property
    def issued(self) -> tuple[str, ...]:
        """Every id issued, in issue order."""
        return tuple(self._issued)

    def __contains__(self, ident: object) -> bool:
        return ident in self._seen

    def __len__(self) -> int:
        return len(self._issued)
