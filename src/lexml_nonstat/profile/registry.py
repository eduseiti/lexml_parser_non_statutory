"""The profile registry and genre selection.

Selection is by score, not by first match (see :mod:`.base`), and is
deterministic: ties break by registration order, so the same document always
yields the same profile. Plan invariant #4 requires that, and Cycle 4b's
routing telemetry is unreadable without it.
"""

from __future__ import annotations

from ..ingest import StyledDoc
from .ato_declaratorio import ATO_DECLARATORIO
from .base import DocumentProfile
from .generic import GENERIC
from .jurisprudencia_generico import JURISPRUDENCIA_GENERICO
from .parecer import PARECER
from .portaria import PORTARIA
from .servico import SERVICO

__all__ = [
    "UnknownProfileError",
    "all_profiles",
    "get_profile",
    "register",
    "score_profiles",
    "select_profile",
]


class UnknownProfileError(KeyError):
    """Raised when a profile is requested by a name nobody registered."""


# Insertion order is the tie-break order, so this list is the priority order.
# `generic` is last: it wins only when nothing else scores above its floor.
_REGISTRY: dict[str, DocumentProfile] = {}


def register(profile: DocumentProfile, *, replace: bool = False) -> DocumentProfile:
    """Add a profile. Refuses to shadow an existing name unless asked."""
    if profile.name in _REGISTRY and not replace:
        raise ValueError(f"profile {profile.name!r} is already registered")
    _REGISTRY[profile.name] = profile
    return profile


def get_profile(name: str) -> DocumentProfile:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise UnknownProfileError(f"unknown profile {name!r}; known: {known}") from None


def all_profiles() -> tuple[DocumentProfile, ...]:
    """Every registered profile, in registration order."""
    return tuple(_REGISTRY.values())


def score_profiles(doc: StyledDoc) -> tuple[tuple[DocumentProfile, float], ...]:
    """Every profile with its score, best first.

    Exposed because Cycle 4b's telemetry wants the runner-up as well as the
    winner: a document whose top two profiles score alike is one whose genre
    prior should carry little weight.
    """
    scored = [(p, p.score(doc)) for p in _REGISTRY.values()]
    order = {p.name: i for i, p in enumerate(_REGISTRY.values())}
    scored.sort(key=lambda ps: (-ps[1], order[ps[0].name]))
    return tuple(scored)


def select_profile(doc: StyledDoc) -> DocumentProfile:
    """The best-scoring profile for ``doc``; never ``None``."""
    return score_profiles(doc)[0][0]


for _p in (
    PARECER,
    ATO_DECLARATORIO,
    PORTARIA,
    JURISPRUDENCIA_GENERICO,
    SERVICO,
    GENERIC,
):
    register(_p)
