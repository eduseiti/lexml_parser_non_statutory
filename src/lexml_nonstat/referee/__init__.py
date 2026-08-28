"""The LLM referee (plan §7) — advisory, cached, fail-safe, fully logged.

    from lexml_nonstat.referee import NullReferee, build_referee

    referee = build_referee("none")            # the suite's default (§9.3)
    referee = build_referee("api", api_key=…)  # DeepSeek / Qwen / Moonshot
    referee = build_referee("local", model_path=…)

The referee adjudicates *flagged* decisions and nothing else. It never parses a
document and never emits XML; the deterministic rules produce valid output on
their own, always. :func:`~.adjudicate.adjudicate` is where that promise is
kept — see its docstring for the constraint-by-constraint mapping.
"""

from .adjudicate import adjudicate
from .api import DEFAULT_BASE_URL, DEFAULT_MODEL, CachedAPIReferee, Transport
from .cache import RefereeCache, cache_key
from .local import DEFAULT_BINARY, LocalReferee, Runner
from .null import NullReferee
from .prompts import (
    MAX_CONTEXT_CHARS,
    MAX_EXCERPT_CHARS,
    SYSTEM_PROMPT,
    VOCABULARIES,
    build_prompt,
    truncate,
)
from .protocol import (
    FLAG_THRESHOLD,
    HEADING_VERDICTS,
    OWN_ARTICULATION_VERDICTS,
    REFEREE_MIN_CONFIDENCE,
    RULE_HIGH_CONFIDENCE,
    Referee,
    Verdict,
    is_flagged,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_BINARY",
    "DEFAULT_MODEL",
    "FLAG_THRESHOLD",
    "HEADING_VERDICTS",
    "MAX_CONTEXT_CHARS",
    "MAX_EXCERPT_CHARS",
    "OWN_ARTICULATION_VERDICTS",
    "REFEREE_MIN_CONFIDENCE",
    "RULE_HIGH_CONFIDENCE",
    "REFEREE_MODES",
    "SYSTEM_PROMPT",
    "VOCABULARIES",
    "CachedAPIReferee",
    "LocalReferee",
    "NullReferee",
    "Referee",
    "RefereeCache",
    "Runner",
    "Transport",
    "Verdict",
    "adjudicate",
    "build_prompt",
    "build_referee",
    "cache_key",
    "is_flagged",
    "truncate",
]

#: Accepted values of ``--referee`` (§7.3 constraint 7). ``none`` is default.
REFEREE_MODES: tuple[str, ...] = ("none", "api", "local")


def build_referee(mode: str = "none", **kwargs):
    """Construct a referee from a ``--referee`` value.

    ``none`` returns a :class:`NullReferee` rather than ``None`` so a caller
    always has an object to talk to; adjudication reaches the same outcome
    either way, by design.

    Raises:
        ValueError: on an unknown mode — a typo in ``--referee`` must not
            silently disable adjudication.
    """
    if mode == "none":
        return NullReferee()
    if mode == "api":
        return CachedAPIReferee(**kwargs)
    if mode == "local":
        return LocalReferee(**kwargs)
    raise ValueError(
        f"unknown referee mode {mode!r}; expected one of {', '.join(REFEREE_MODES)}"
    )
