"""Document profiles: per-genre patterns, URN defaults and field allowlists.

Seven profiles: plan §8's Cycle 2 list of six, plus ``solucao_consulta``, added
by Cycle 3 of the corpus-233 hardening plan for the genre that is 54% of that
corpus. ``nota_tecnica`` appears in the plan's §3 layout but has no sample in
the corpus, so it is deliberately not built — see the Cycle 2 spec, decision #5.
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
from .solucao_consulta import SOLUCAO_CONSULTA

__all__ = [
    "ATO_DECLARATORIO",
    "DocumentProfile",
    "GENERIC",
    "JURISPRUDENCIA_GENERICO",
    "PARECER",
    "PORTARIA",
    "SERVICO",
    "SOLUCAO_CONSULTA",
    "UnknownProfileError",
    "all_profiles",
    "fold",
    "get_profile",
    "head_texts",
    "register",
    "score_profiles",
    "select_profile",
]
