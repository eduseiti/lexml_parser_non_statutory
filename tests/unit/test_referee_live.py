"""The one test that talks to a real provider — plan §9.3's live smoke test.

Everything else in the suite is offline by construction: recorded fixtures, an
injected transport, `NullReferee`. That is the design, and §9.3 pins it. But it
leaves one question no offline test can answer — *is the wiring to an actual
provider correct?* — and the cost of not answering it is the failure mode this
file exists to remove: a key configured, a command run, output that looks
plausible, and no way to tell whether the referee was reached.

**Double-guarded, deliberately.** `pyproject.toml` sets
`addopts = "-m 'not live'"`, so a bare `pytest tests/` never collects this; and
the test skips anyway without `LEXML_REFEREE_API_KEY`, so even
`pytest -m live` on a machine with no key is a skip rather than a failure. To
run it on purpose:

    set -a; . ./.env; set +a
    python3 -m pytest tests/unit/test_referee_live.py -m live -v

It asks exactly one question — a few hundred tokens, a fraction of a US cent —
and asserts the *shape* of the answer, never its content. A referee that says
`own` where the rules say `quoted` is a finding to investigate, not a broken
test: adjudication is advisory (§7.3 constraint 4), and pinning a live model's
verdict would make this suite fail whenever a provider updates a checkpoint.
"""

from __future__ import annotations

import os

import pytest

from lexml_nonstat.referee import (
    OWN_ARTICULATION_VERDICTS,
    CachedAPIReferee,
    Verdict,
)
from lexml_nonstat.referee import api as referee_api

pytestmark = pytest.mark.live

API_KEY = os.environ.get("LEXML_REFEREE_API_KEY")

requires_key = pytest.mark.skipif(
    not API_KEY,
    reason="LEXML_REFEREE_API_KEY is not set; the live smoke test needs a provider",
)

#: `par_cosit_26` p#46 — one of the four decisions the corpus actually flags,
#: so this asks the provider a question the tool really asks, not a toy.
EXCERPT = (
    "Art. 2º- O imposto de renda das pessoas físicas será devido, mensalmente, "
    "à medida em que os rendimentos e ganhos de capital forem percebidos."
)
CONTEXT = (
    "O dispositivo transcrito integra a Lei nº 7.713, de 1988, citada no "
    "parágrafo anterior a título de fundamentação."
)


@requires_key
def test_live_provider_answers_one_question() -> None:
    """A real call returns a well-formed `Verdict` from the configured provider.

    The assertions are the contract `adjudicate` relies on, and nothing more:
    a verdict drawn from the closed vocabulary, a confidence in range, and a
    non-abstaining answer. An abstention here is the *interesting* failure —
    it means the key, the base URL, the model id or the JSON mode is wrong —
    so its rationale is surfaced in the assertion message rather than hidden
    behind a bare `assert False`.
    """
    referee = CachedAPIReferee(
        model=os.environ.get("LEXML_REFEREE_MODEL", referee_api.DEFAULT_MODEL),
        base_url=os.environ.get(
            "LEXML_REFEREE_BASE_URL", referee_api.DEFAULT_BASE_URL
        ),
        api_key=API_KEY,
        cache=None,  # never cache a smoke test: a cache hit would prove nothing
    )

    verdict = referee.is_own_articulation(EXCERPT, CONTEXT)

    assert isinstance(verdict, Verdict)
    assert not verdict.abstained, (
        "the provider did not answer — check the key, base URL and model id. "
        f"rationale: {verdict.rationale}"
    )
    assert verdict.verdict in OWN_ARTICULATION_VERDICTS
    assert 0.0 <= verdict.confidence <= 1.0
    assert referee.calls == 1, "exactly one request per question"


@requires_key
def test_live_answer_is_cacheable(tmp_path) -> None:
    """The second ask costs nothing — which is what makes a corpus run cheap.

    Cycle 9's batch over 300+ documents depends on this: the disk cache is what
    turns a rerun into zero calls and zero spend (invariant #4, §7.3 c.3).
    """
    referee = CachedAPIReferee(
        model=os.environ.get("LEXML_REFEREE_MODEL", referee_api.DEFAULT_MODEL),
        base_url=os.environ.get(
            "LEXML_REFEREE_BASE_URL", referee_api.DEFAULT_BASE_URL
        ),
        api_key=API_KEY,
        cache=tmp_path,
    )

    first = referee.is_own_articulation(EXCERPT, CONTEXT)
    assert not first.abstained, f"live call failed: {first.rationale}"
    assert referee.calls == 1

    second = referee.is_own_articulation(EXCERPT, CONTEXT)
    assert referee.calls == 1, "the second ask must come from the cache"
    assert referee.last_cache_hit is True
    assert second.verdict == first.verdict
