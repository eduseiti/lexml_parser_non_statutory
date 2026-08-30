"""The API referee — one OpenAI-compatible client for three providers.

§7.2 recommends a budget frontier API as primary: DeepSeek, Qwen and Moonshot
all expose OpenAI-compatible endpoints, so one client serves all three and the
choice becomes a base URL and a model name rather than a code path.

The transport is injected
-------------------------
``transport`` is a callable ``(url, headers, payload, timeout) -> dict``. The
default builds an ``httpx`` client lazily, on the first call that actually
reaches the network — which means:

* the ``referee`` extra is genuinely optional, and importing this module on a
  machine without ``httpx`` works;
* every failure mode in §7.3 constraint 5 is testable by injecting a callable
  that raises, hangs or lies, with no mock of HTTP itself;
* a cache hit imports nothing and calls nothing, which is what the plan's
  "mocked transport asserts zero calls" test measures.

Nothing here raises. Every path — no key, no ``httpx``, timeout, 5xx, non-JSON,
JSON of the wrong shape, a verdict outside the vocabulary — returns an
abstention carrying its reason, and the caller keeps the rule verdict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .cache import RefereeCache, cache_key
from .prompts import VOCABULARIES, build_prompt
from .protocol import Verdict

__all__ = ["DEFAULT_BASE_URL", "DEFAULT_MODEL", "CachedAPIReferee", "Transport"]

#: ``(url, headers, payload, timeout) -> parsed JSON response``
Transport = Callable[[str, dict, dict, float], dict]

#: §7.2's first candidate: very low cost, strong reasoning, context caching.
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"

#: Temperature 0 everywhere. Invariant #4 wants the same input plus the same
#: cache to give byte-identical output; a sampled referee would break that on
#: the first cache miss.
TEMPERATURE = 0.0


def _httpx_transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    """The default transport. Imports ``httpx`` only when actually called."""
    import httpx  # local, so the extra stays optional

    response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


class CachedAPIReferee:
    """An OpenAI-compatible chat-completions referee, disk-cached.

    Args:
        model: the provider's model id.
        base_url: an OpenAI-compatible endpoint root.
        api_key: sent as a bearer token. Absent ⇒ every call abstains rather
            than making an unauthenticated request.
        cache: a :class:`RefereeCache`; a read-only one over
            ``tests/referee_fixtures/`` turns this into an offline referee.
        transport: see the module docstring.
        timeout: seconds.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        cache: RefereeCache | Path | str | None = None,
        transport: Transport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transport: Transport = transport or _httpx_transport
        if isinstance(cache, (str, Path)):
            cache = RefereeCache(cache)
        self.cache = cache
        #: How many times the transport was actually invoked. The zero-call
        #: assertion in the test plan reads this.
        self.calls = 0
        #: Whether the last answer came from the cache, for `DecisionRecord`.
        self.last_cache_hit = False

    name = "api"

    # -- the protocol ------------------------------------------------------

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        return self.ask("own_articulation", excerpt, ctx)

    def is_heading(self, para: str, ctx: str) -> Verdict:
        return self.ask("heading", para, ctx)

    def section_kind(self, label: str, heading: str) -> Verdict:
        return self.ask("section_kind", label, heading)

    def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
        return self.ask("quotation_boundary", excerpt, ctx)

    # -- the machinery -----------------------------------------------------

    def ask(self, kind: str, excerpt: str, ctx: str = "") -> Verdict:
        """Adjudicate one question. Never raises."""
        self.last_cache_hit = False
        key = cache_key(self.model, kind, excerpt, ctx)

        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                self.last_cache_hit = True
                return cached

        verdict = self._call(kind, excerpt, ctx)

        # Abstentions are not cached: a timeout is a fact about the network,
        # not about the question, and caching it would make one bad minute
        # permanent.
        if self.cache is not None and not verdict.abstained:
            self.cache.put(
                key,
                verdict,
                meta={"model": self.model, "kind": kind, "excerpt": excerpt[:200]},
            )
        return verdict

    def _call(self, kind: str, excerpt: str, ctx: str) -> Verdict:
        if not self.api_key:
            return Verdict.abstain("no API key configured; referee unavailable")

        try:
            system, user = build_prompt(kind, excerpt, ctx)
        except KeyError:
            return Verdict.abstain(f"no prompt template for decision kind {kind!r}")

        payload = {
            "model": self.model,
            "temperature": TEMPERATURE,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self.calls += 1
        try:
            response = self.transport(
                f"{self.base_url}/chat/completions", headers, payload, self.timeout
            )
        except ImportError as exc:
            return Verdict.abstain(f"referee transport unavailable: {exc}")
        except Exception as exc:  # noqa: BLE001 - constraint 5 is total
            # Deliberately broad. Every transport has its own exception tree
            # (httpx.TimeoutException, urllib's URLError, a provider SDK's own)
            # and constraint 5 promises the pipeline completes regardless. A
            # narrower except here would be a list of the failures we happened
            # to think of.
            return Verdict.abstain(f"{type(exc).__name__}: {exc}")

        return self._parse(kind, response)

    @staticmethod
    def _parse(kind: str, response: Any) -> Verdict:
        """Turn a chat-completions response into a verdict, or abstain."""
        if not isinstance(response, dict):
            return Verdict.abstain(
                f"malformed response: expected an object, got {type(response).__name__}"
            )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return Verdict.abstain("malformed response: no choices[0].message.content")

        if isinstance(content, str):
            try:
                data = json.loads(content)
            except ValueError:
                return Verdict.abstain(
                    f"non-JSON content: {content[:120]!r}"
                )
        elif isinstance(content, dict):
            data = content
        else:
            return Verdict.abstain(
                f"malformed content of type {type(content).__name__}"
            )

        if not isinstance(data, dict) or "verdict" not in data:
            return Verdict.abstain(f"JSON without a 'verdict' key: {str(data)[:120]}")

        verdict = data.get("verdict")
        if not isinstance(verdict, str) or not verdict.strip():
            return Verdict.abstain(f"non-string verdict: {verdict!r}")
        verdict = verdict.strip().lower()

        vocabulary = VOCABULARIES.get(kind)
        if vocabulary is not None and verdict not in vocabulary:
            return Verdict.abstain(
                f"verdict {verdict!r} outside the vocabulary for {kind} "
                f"({', '.join(vocabulary)})"
            )

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            return Verdict.abstain(f"non-numeric confidence: {data.get('confidence')!r}")
        confidence = min(1.0, max(0.0, confidence))

        rationale = data.get("rationale") or ""
        if not isinstance(rationale, str):
            rationale = str(rationale)
        return Verdict(verdict, confidence, rationale.strip()[:300])
