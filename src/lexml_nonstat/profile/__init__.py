"""Document profiles: per-genre patterns, URN defaults and field allowlists.

Six profiles, matching plan §8's Cycle 2 list. ``nota_tecnica`` appears in the
plan's §3 layout but has no sample in the corpus, so it is deliberately not
built — see the Cycle 2 spec, decision #5.
"""

from .ato_declaratorio import ATO_DECLARATORIO
from .base import DocumentProfile, fold, head_texts
from .generic import GENERIC
from .jurisprudencia_generico import JURISPRUDENCIA_GENERICO
from .parecer import PARECER
from .portaria import PORTARIA
from .registry import (
    UnknownProfileError,
    all_profiles,
    get_profile,
    register,
    score_profiles,
    select_profile,
)
from .servico import SERVICO

__all__ = [
    "ATO_DECLARATORIO",
    "DocumentProfile",
    "GENERIC",
    "JURISPRUDENCIA_GENERICO",
    "PARECER",
    "PORTARIA",
    "SERVICO",
    "UnknownProfileError",
    "all_profiles",
    "fold",
    "get_profile",
    "head_texts",
    "register",
    "score_profiles",
    "select_profile",
]
