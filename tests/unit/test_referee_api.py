"""The API referee — every failure mode, and not one packet on the wire.

§9.3 is categorical: *networked LLM calls must never enter the regression
suite*. It also says how to obey that without stubbing out the thing under
test — **the cache layer is the seam**. So this file drives the real
:class:`CachedAPIReferee` through two injected surfaces and nothing else:

* a ``transport`` callable ``(url, headers, payload, timeout) -> dict``, which
  is how a timeout, a 5xx, a malformed body or a lying provider becomes a unit
  test; and
* a :class:`RefereeCache` directory — ``tests/referee_fixtures/`` opened
  read-only — which is how the *whole* referee path, adjudication and telemetry
  included, runs over the real corpus with the transport wired to raise.

Nothing here may import ``httpx``. That is not an inconvenience being worked
around; it is the property being tested. The ``referee`` extra is optional, and
a module-level import would make it mandatory for everybody —
``test_httpx_is_not_imported`` pins that, by asserting that exercising the
referee does not *add* ``httpx`` to ``sys.modules``. Whether some unrelated
pytest plugin already put it there is not ours to control and not what the
invariant claims.

The invariants under test, in order of what they cost when broken:

* **§7.3 constraint 5, fail-safe.** Every hostile answer — timeout, exception,
  non-JSON, JSON of the wrong shape, a verdict outside the vocabulary, an
  absurd confidence — returns an *abstention*, never an exception. A referee
  outage degrades quality; it may never degrade availability. The pipeline test
  at the bottom asserts this end-to-end over a real document.
* **§7.3 constraint 3, cached by excerpt hash.** A hit makes zero calls; an
  abstention is never cached, because a timeout is a fact about the network and
  not about the question, and caching it would make one bad minute permanent.
* **Invariant #4, determinism.** Temperature 0 and a JSON-constrained response
  format on every request. A sampled referee breaks byte-identical output on
  the first cache miss.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.referee import (
    DEFAULT_MODEL,
    OWN_ARTICULATION_VERDICTS,
    SYSTEM_PROMPT,
    CachedAPIReferee,
    RefereeCache,
    Verdict,
    cache_key,
)
from lexml_nonstat.routing import assess_viability
from lexml_nonstat.telemetry import DecisionLog, DecisionsReport

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"
FIXTURES = REPO_ROOT / "tests" / "referee_fixtures"

#: Every sample in the corpus, by stem — fifteen documents standing in for 300+.
SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

PAR_COSIT_26 = "par_cosit_26_20000629"
PARECER_93 = "parecer_93_2018_decor_cgu_agu"

#: The three low-confidence quotation verdicts ``par_cosit_26`` produces — the
#: document §2.6 calls the residual hard case, because it "resists indentation
#: entirely" and its quoted statutes are convicted by a citation antecedent or
#: by excerpt-run extension alone. See ``tests/referee_fixtures/README.md``.
PAR_COSIT_26_FLAGGED = ("p#46", "p#47", "p#53")

#: The fourth and last flagged decision in the whole corpus.
PARECER_93_FLAGGED = ("p#36",)

#: A test key must not need an API key to be a real one.
API_KEY = "test-key-not-a-secret"

_DOCS: dict[str, object] = {}


def sample(name: str):
    """Read a sample once per session; ``parecer_93`` is 428 blocks."""
    if name not in _DOCS:
        _DOCS[name] = read_docx(SAMPLES_DIR / f"{name}.docx")
    return _DOCS[name]


# ---------------------------------------------------------------------------
# Injected transports
# ---------------------------------------------------------------------------


def chat_response(verdict: str = "quoted", confidence=0.9, rationale: str = "porque sim"):
    """An OpenAI-compatible chat-completions body, as a provider returns it."""
    content = json.dumps(
        {"verdict": verdict, "confidence": confidence, "rationale": rationale}
    )
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def replies(response=None):
    """A transport that answers, and records what it was asked."""
    seen: list[dict] = []

    def transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
        seen.append(
            {"url": url, "headers": headers, "payload": payload, "timeout": timeout}
        )
        return chat_response() if response is None else response

    transport.seen = seen  # type: ignore[attr-defined]
    return transport


def returns(response):
    """A transport that returns exactly ``response``, however wrong it is."""

    def transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
        return response

    return transport


def explodes(exc: BaseException | None = None):
    """A transport that must never be called — or that fails when it is."""

    def transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
        raise exc if exc is not None else AssertionError(
            "the transport was called; this path must make no network calls"
        )

    return transport


def entries(directory: Path) -> list[Path]:
    """Cache files on disk, tolerating a directory that was never created."""
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def fixture_referee(**kwargs) -> CachedAPIReferee:
    """The offline referee §9.3 describes: recorded answers, no transport.

    ``read_only=True`` matters. Without it an unrecorded question would grow a
    new file in ``tests/referee_fixtures/`` and become a silent live call on the
    next run — precisely what the policy forbids.
    """
    kwargs.setdefault("transport", explodes())
    return CachedAPIReferee(
        cache=RefereeCache(FIXTURES, read_only=True), api_key=API_KEY, **kwargs
    )


# ---------------------------------------------------------------------------
# The cache — §7.3 constraint 3
# ---------------------------------------------------------------------------


def test_cache_hit_makes_zero_network_calls(tmp_path: Path):
    """The plan's own wording: "mocked transport asserts zero calls" (§9.3).

    This is the property that makes a warm cache an *offline* referee rather
    than a cheap one, and it is what lets the corpus test below run the real
    adjudication path with the network wired to raise.
    """
    cache = RefereeCache(tmp_path)
    excerpt, ctx = "Art. 2º Teste.", "Lei nº 7.713, de 1988 -"
    cache.put(
        cache_key(DEFAULT_MODEL, "own_articulation", excerpt, ctx),
        Verdict("quoted", 0.93, "citação de norma externa"),
    )

    referee = CachedAPIReferee(api_key=API_KEY, cache=cache, transport=explodes())
    verdict = referee.ask("own_articulation", excerpt, ctx)

    assert verdict.verdict == "quoted"
    assert verdict.confidence == pytest.approx(0.93)
    assert verdict.rationale == "citação de norma externa"
    assert referee.calls == 0
    assert cache.hits == 1


def test_cache_miss_calls_transport_once_then_caches(tmp_path: Path):
    """Near-zero repeat cost, and a re-run that asks nothing a second time."""
    transport = replies()
    referee = CachedAPIReferee(
        api_key=API_KEY, cache=RefereeCache(tmp_path), transport=transport
    )

    first = referee.ask("own_articulation", "Art. 3º Teste.", "ctx")
    assert first.verdict == "quoted"
    assert referee.calls == 1
    assert len(entries(tmp_path)) == 1

    second = referee.ask("own_articulation", "Art. 3º Teste.", "ctx")
    assert second == first
    assert referee.calls == 1, "the second ask must not reach the transport"
    assert len(transport.seen) == 1


def test_last_cache_hit_reports_the_source(tmp_path: Path):
    """``DecisionRecord.cache_hit`` is only as honest as this flag.

    §7.4's cache-hit rate is one of the numbers ``--decisions-report`` exists to
    produce; a flag that never cleared would report 100% forever.
    """
    referee = CachedAPIReferee(
        api_key=API_KEY, cache=RefereeCache(tmp_path), transport=replies()
    )

    referee.ask("own_articulation", "Art. 4º Teste.")
    assert referee.last_cache_hit is False

    referee.ask("own_articulation", "Art. 4º Teste.")
    assert referee.last_cache_hit is True

    referee.ask("own_articulation", "Art. 5º Outro.")
    assert referee.last_cache_hit is False, "a new question is a miss again"


def test_abstention_is_not_cached(tmp_path: Path):
    """A timeout is a fact about the network, not about the question.

    Caching it would make one bad minute permanent: every later run would read
    the failure off disk and never retry, and the referee would be silently
    dead while the report showed a healthy cache-hit rate.
    """
    cache_dir = tmp_path / "cache"
    question = ("own_articulation", "Art. 16 Teste.", "ctx")

    referee = CachedAPIReferee(
        api_key=API_KEY,
        cache=RefereeCache(cache_dir),
        transport=explodes(TimeoutError("read timeout")),
    )
    assert referee.ask(*question).abstained
    assert entries(cache_dir) == [], "an abstention must leave no trace on disk"

    referee.transport = replies()
    verdict = referee.ask(*question)
    assert not verdict.abstained
    assert len(entries(cache_dir)) == 1, "the recovered answer is cached normally"


def test_read_only_cache_never_writes(tmp_path: Path):
    """A fixture directory must not grow a file because a test asked something.

    That is the whole reason ``read_only`` exists: an unrecorded question that
    silently records itself turns the next run's *live call* into a passing
    test, and §9.3's guarantee evaporates without a diff to show for it.
    """
    cache_dir = tmp_path / "fixtures"
    cache_dir.mkdir()
    cache = RefereeCache(cache_dir, read_only=True)
    referee = CachedAPIReferee(api_key=API_KEY, cache=cache, transport=replies())

    verdict = referee.ask("own_articulation", "Art. 52 Teste.", "ctx")
    assert verdict.verdict == "quoted"
    assert entries(cache_dir) == []

    # And it stays a miss, so the cost is visible rather than hidden.
    referee.ask("own_articulation", "Art. 52 Teste.", "ctx")
    assert referee.calls == 2
    assert cache.misses == 2


def test_a_corrupt_cache_entry_is_a_miss_not_a_crash(tmp_path: Path):
    """One truncated JSON file must not end a 300-document run."""
    key = cache_key(DEFAULT_MODEL, "own_articulation", "Art. 7º Teste.", "")
    (tmp_path / f"{key}.json").write_text("{ not json", encoding="utf-8")

    referee = CachedAPIReferee(
        api_key=API_KEY, cache=RefereeCache(tmp_path), transport=replies()
    )
    assert referee.ask("own_articulation", "Art. 7º Teste.").verdict == "quoted"
    assert referee.calls == 1


def test_a_referee_without_a_cache_still_works(tmp_path: Path):
    """``cache=None`` is a supported configuration, not an unhandled one."""
    referee = CachedAPIReferee(api_key=API_KEY, cache=None, transport=replies())
    assert referee.ask("own_articulation", "Art. 8º Teste.").verdict == "quoted"
    assert referee.calls == 1
    assert referee.last_cache_hit is False


def test_a_cache_given_as_a_path_is_adopted(tmp_path: Path):
    """``--referee-cache=<dir>`` arrives as a string; it must still cache."""
    referee = CachedAPIReferee(api_key=API_KEY, cache=str(tmp_path), transport=replies())
    referee.ask("own_articulation", "Art. 9º Teste.")
    assert isinstance(referee.cache, RefereeCache)
    assert len(entries(tmp_path)) == 1


# ---------------------------------------------------------------------------
# The cache key
# ---------------------------------------------------------------------------


def test_cache_key_is_stable_for_equal_inputs():
    """Reproducibility first, cost second: the same question is the same file."""
    a = cache_key("deepseek-chat", "own_articulation", "Art. 2º", "ctx")
    b = cache_key("deepseek-chat", "own_articulation", "Art. 2º", "ctx")
    assert a == b


@pytest.mark.parametrize(
    "args",
    [
        ("qwen-plus", "own_articulation", "Art. 2º", "ctx"),
        ("deepseek-chat", "heading", "Art. 2º", "ctx"),
        ("deepseek-chat", "own_articulation", "Art. 3º", "ctx"),
        ("deepseek-chat", "own_articulation", "Art. 2º", "outro contexto"),
        ("deepseek-chat", "own_articulation", "Art. 2º", ""),
    ],
)
def test_cache_key_covers_everything_that_could_change_the_answer(args: tuple):
    """Model, kind, excerpt and context all move the key.

    §9.3 wants a provider change to appear as a *reviewed diff*. That only
    works if a different model writes new files instead of reading the old
    one's opinions — which is also why the fixture README can promise that
    switching providers is additive.
    """
    baseline = cache_key("deepseek-chat", "own_articulation", "Art. 2º", "ctx")
    assert cache_key(*args) != baseline


def test_cache_key_is_filesystem_safe():
    """A key is a filename. Excerpts contain slashes, accents and newlines."""
    key = cache_key(
        "deepseek-chat",
        "own_articulation",
        "Art. 2º/§ 1º — vide fls. 3/4\nDOU de 30/06/2000",
        "…",
    )
    assert re.fullmatch(r"[0-9a-f]{32}", key), key


def test_path_for_stays_inside_the_cache_directory(tmp_path: Path):
    cache = RefereeCache(tmp_path)
    path = cache.path_for(cache_key(DEFAULT_MODEL, "own_articulation", "x"))
    assert path.parent == tmp_path
    assert path.suffix == ".json"


# ---------------------------------------------------------------------------
# Hostile answers — §7.3 constraint 5
# ---------------------------------------------------------------------------


def test_malformed_json_response_abstains():
    """Content that is not JSON at all, despite ``response_format``."""
    response = {"choices": [{"message": {"content": "Claro! O trecho é uma citação."}}]}
    verdict = CachedAPIReferee(api_key=API_KEY, transport=returns(response)).ask(
        "own_articulation", "Art. 2º…"
    )

    assert verdict.abstained
    assert "non-JSON content" in verdict.rationale


@pytest.mark.parametrize("content", [42, 3.5, None, ["quoted"], True])
def test_non_json_content_type_abstains(content):
    """A provider that returns content of an unexpected type is still a failure."""
    response = {"choices": [{"message": {"content": content}}]}
    verdict = CachedAPIReferee(api_key=API_KEY, transport=returns(response)).ask(
        "own_articulation", "Art. 2º…"
    )
    assert verdict.abstained


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"choices": []},
        {"error": {"message": "insufficient balance"}},
        {"choices": [{"message": {}}]},
        {"choices": "not a list"},
        "a bare string",
        None,
        [1, 2, 3],
    ],
)
def test_response_without_choices_abstains(response):
    """Every shape a provider returns when something went wrong upstream.

    Rate limits, an exhausted balance and a proxy's HTML error page all arrive
    here. None of them may raise: an outage degrades quality, never
    availability.
    """
    verdict = CachedAPIReferee(api_key=API_KEY, transport=returns(response)).ask(
        "own_articulation", "Art. 2º…"
    )

    assert verdict.abstained
    assert "malformed response" in verdict.rationale


@pytest.mark.parametrize(
    "data",
    [
        {"confidence": 0.9, "rationale": "…"},
        {"answer": "quoted"},
        {},
        {"verdict": None},
        {"verdict": ""},
        {"verdict": 7},
    ],
)
def test_json_without_verdict_key_abstains(data: dict):
    """JSON of the wrong shape is as useless as no JSON, and just as harmless."""
    response = {"choices": [{"message": {"content": json.dumps(data)}}]}
    verdict = CachedAPIReferee(api_key=API_KEY, transport=returns(response)).ask(
        "own_articulation", "Art. 2º…"
    )

    assert verdict.abstained
    assert verdict.verdict is None


@pytest.mark.parametrize("answer", ["maybe", "talvez", "own or quoted", "heading"])
def test_verdict_outside_vocabulary_abstains(answer: str):
    """``own_articulation`` admits exactly ``own`` and ``quoted``.

    A third answer is a model that did not understand the question. Letting it
    through would put an unmodelled string into the article census, where
    anything that is not ``quoted`` counts as the document's *own* article —
    that is, as fabricated structure (invariant #8).
    """
    verdict = CachedAPIReferee(
        api_key=API_KEY, transport=returns(chat_response(answer))
    ).ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert answer in verdict.rationale
    for allowed in OWN_ARTICULATION_VERDICTS:
        assert allowed in verdict.rationale, "the reason must name what was allowed"


def test_a_verdict_is_normalised_before_it_is_checked():
    """Providers pad and capitalise; that is not a vocabulary violation."""
    verdict = CachedAPIReferee(
        api_key=API_KEY, transport=returns(chat_response("  QUOTED  "))
    ).ask("own_articulation", "Art. 2º…")

    assert verdict.verdict == "quoted"


def test_section_kind_has_no_closed_vocabulary():
    """§7.1 lists section-kind naming as open semantic labelling.

    ``capitulo``/``secao``/``item``/``topico`` are examples in the prompt, not an
    enumeration, so an unlisted-but-sensible answer must survive rather than
    abstain.
    """
    verdict = CachedAPIReferee(
        api_key=API_KEY, transport=returns(chat_response("subsecao"))
    ).section_kind("I -", "DA COMPETÊNCIA")

    assert not verdict.abstained
    assert verdict.verdict == "subsecao"


@pytest.mark.parametrize("confidence", ["alta", "muito alta", [0.9], {}])
def test_non_numeric_confidence_abstains(confidence):
    """Confidence gates the override (``REFEREE_MIN_CONFIDENCE``).

    A value that cannot be compared to a threshold cannot be allowed to pass
    one, so it abstains rather than defaulting to zero and being silently
    ignored.
    """
    verdict = CachedAPIReferee(
        api_key=API_KEY, transport=returns(chat_response("quoted", confidence))
    ).ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert "confidence" in verdict.rationale


@pytest.mark.parametrize(
    "claimed,expected", [(5.0, 1.0), (1.5, 1.0), (-2.0, 0.0), (0.0, 0.0), (0.75, 0.75)]
)
def test_confidence_is_clamped_to_unit_interval(claimed: float, expected: float):
    """A model claiming 5.0 is not five times as sure as one claiming 1.0.

    Clamping rather than abstaining is deliberate: the answer is usable, only
    the self-report is out of range, and the number then means the same thing
    everywhere ``REFEREE_MIN_CONFIDENCE`` is compared against it.
    """
    verdict = CachedAPIReferee(
        api_key=API_KEY, transport=returns(chat_response("quoted", claimed))
    ).ask("own_articulation", "Art. 2º…")

    assert not verdict.abstained
    assert verdict.confidence == pytest.approx(expected)


def test_transport_timeout_falls_back():
    """The commonest live failure, and it must cost nothing but a warning."""
    verdict = CachedAPIReferee(
        api_key=API_KEY, transport=explodes(TimeoutError("read timeout after 30s"))
    ).ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert "TimeoutError" in verdict.rationale, "the reason must name the failure type"
    assert "read timeout" in verdict.rationale


def test_transport_5xx_falls_back():
    """Every transport has its own exception tree; the fallback catches all of them.

    The broad ``except`` in the referee is the point, not an oversight: a
    narrower one would be a list of the failures we happened to think of, and
    the one we did not think of would take down the run.
    """
    class ServerError(RuntimeError):
        pass

    verdict = CachedAPIReferee(
        api_key=API_KEY, transport=explodes(ServerError("502 Bad Gateway"))
    ).ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert "ServerError" in verdict.rationale
    assert "502" in verdict.rationale


def test_missing_api_key_abstains_without_calling():
    """No key ⇒ no unauthenticated request, and no exception either.

    Running with ``--referee=api`` and a forgotten environment variable is a
    misconfiguration; it must show up as abstentions in the decisions report,
    not as a run that dies or, worse, as 300 rejected requests.
    """
    referee = CachedAPIReferee(api_key=None, transport=explodes())
    verdict = referee.ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert "API key" in verdict.rationale
    assert referee.calls == 0


def test_unknown_kind_abstains_without_calling():
    """A question with no template must not become a request."""
    referee = CachedAPIReferee(api_key=API_KEY, transport=explodes())
    verdict = referee.ask("nonsense", "Art. 2º…")

    assert verdict.abstained
    assert "nonsense" in verdict.rationale
    assert referee.calls == 0


# ---------------------------------------------------------------------------
# The request itself
# ---------------------------------------------------------------------------


def test_payload_is_deterministic_and_json_constrained():
    """Invariant #4 lives in this payload.

    "Same input + same referee cache ⇒ byte-identical output" is only true if
    the referee is deterministic on a *miss* too, which means temperature 0 —
    and §7.3 constraint 2 ("structured output only") means asking the provider
    for a JSON object rather than hoping for one. Both are asserted here
    because both are invisible until a golden starts moving for no reason.
    """
    transport = replies()
    referee = CachedAPIReferee(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=API_KEY,
        transport=transport,
    )
    referee.ask("own_articulation", "Art. 2º Teste.", "Lei nº 7.713, de 1988 -")

    call = transport.seen[0]
    payload = call["payload"]

    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["model"] == "deepseek-chat"

    system, user = payload["messages"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user["role"] == "user"
    assert "Art. 2º Teste." in user["content"]
    assert "Lei nº 7.713, de 1988 -" in user["content"]

    assert call["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["timeout"] == 30.0

    # The same question twice produces the same request, byte for byte.
    referee.ask("own_articulation", "Art. 2º Teste.", "Lei nº 7.713, de 1988 -")
    assert transport.seen[1]["payload"] == payload


def test_a_trailing_slash_in_the_base_url_does_not_double():
    """Providers document their roots inconsistently; the URL must not care."""
    transport = replies()
    CachedAPIReferee(
        base_url="https://api.deepseek.com/v1/", api_key=API_KEY, transport=transport
    ).ask("own_articulation", "Art. 2º…")

    assert transport.seen[0]["url"] == "https://api.deepseek.com/v1/chat/completions"


@pytest.mark.parametrize(
    "method,args,answer",
    [
        ("is_own_articulation", ("Art. 2º Teste.", "Lei nº 7.713 -"), "quoted"),
        ("is_heading", ("CONCLUSÃO", "…"), "heading"),
        ("section_kind", ("I -", "DA COMPETÊNCIA"), "capitulo"),
    ],
)
def test_all_three_protocol_methods_route_to_ask(method: str, args: tuple, answer: str):
    """§7.3's protocol is three questions sharing one piece of machinery.

    Cache, prompt, transport, parse, clamp — one path. A divergence between the
    three would mean a failure mode fixed in one and still live in the others,
    which is exactly the class of bug this parametrisation is cheap insurance
    against.
    """
    transport = replies(chat_response(answer, 0.84, "porquê"))
    referee = CachedAPIReferee(api_key=API_KEY, transport=transport)

    verdict = getattr(referee, method)(*args)

    assert isinstance(verdict, Verdict)
    assert verdict.verdict == answer
    assert verdict.confidence == pytest.approx(0.84)
    assert referee.calls == 1
    assert referee.name == "api"
    assert args[0] in transport.seen[0]["payload"]["messages"][1]["content"]


# ---------------------------------------------------------------------------
# The recorded fixtures over the real corpus — §9.3's seam, end to end
# ---------------------------------------------------------------------------


def test_par_cosit_26_resolves_from_recorded_fixture():
    """The cycle's headline referee test: a real document, adjudicated offline.

    ``par_cosit_26`` is §2.6's residual hard case — it "resists indentation
    entirely", so three of its five quoted articles are convicted by a citation
    antecedent or by excerpt-run extension alone, at 0.50–0.55 confidence.
    Those are the only paragraphs in this document the rules were unsure about,
    and the recorded fixtures answer all three.

    What the assertions pin, in order:

    * **zero transport calls** — the whole referee path ran from disk (§9.3);
    * **exactly the flagged three were consulted** — §7.3 constraint 1, "rules
      run first, always": the other two articles were decided at high
      confidence and never became a question;
    * **the referee agreed on all three** — which is the finding, not a
      convenience. Cycle 4's guard was already right; the referee's job here is
      to confirm a verdict that is right but unsure;
    * **the route is still `generico`** — the outcome that actually matters. A
      fixture saying ``own`` would surface here as a changed route, not as a
      quiet mislabelled paragraph.
    """
    referee = fixture_referee()
    log = DecisionLog()
    verdict = assess_viability(sample(PAR_COSIT_26), referee=referee, log=log)

    assert referee.calls == 0, "a recorded fixture must never touch the network"
    assert referee.cache.hits == len(PAR_COSIT_26_FLAGGED)

    consulted = [r for r in log if r.referee_consulted]
    assert tuple(r.locator for r in consulted) == PAR_COSIT_26_FLAGGED

    for record in consulted:
        assert record.doc == f"{PAR_COSIT_26}.docx"
        assert record.kind == "own_articulation"
        assert record.rule_flagged is True
        assert record.rule_confidence < 0.60
        assert record.abstained is False, "every one of the three was answered"
        assert record.overridden is False, "the referee agreed; nothing was rescued"
        assert record.agreed is True
        assert record.final_verdict == record.rule_verdict == "quoted"
        assert record.referee_verdict == "quoted"
        assert record.referee_confidence >= 0.60
        assert record.referee_name == "api"
        assert record.cache_hit is True
        assert record.referee_rationale

    assert verdict.route == "generico"
    assert verdict.referee_consulted is True
    assert verdict.referee_overrode is False
    assert verdict.articles_found == 5
    assert verdict.articles_quoted == 5
    assert verdict.articles_own == 0
    assert verdict.has_blocker("all_articles_quoted")


def test_parecer_93_resolves_from_recorded_fixture():
    """The corpus's fourth flagged decision, and the only one outside `par_cosit_26`.

    ``parecer_93`` declares a quote band that its 25 quoted articles sit in —
    except one paragraph the band does not reach, which the rules convict on a
    citation antecedent alone. Publishing the Constitution's ``Art. 40`` as an
    article of a legal opinion is the failure this whole guard exists to
    prevent, so the referee agreeing here is load-bearing.
    """
    referee = fixture_referee()
    log = DecisionLog()
    verdict = assess_viability(sample(PARECER_93), referee=referee, log=log)

    consulted = [r for r in log if r.referee_consulted]
    assert tuple(r.locator for r in consulted) == PARECER_93_FLAGGED
    assert all(r.agreed and not r.abstained and not r.overridden for r in consulted)
    assert referee.calls == 0
    assert verdict.route == "generico"
    assert verdict.articles_found == verdict.articles_quoted == 25


def test_fixture_referee_over_whole_corpus():
    """One referee, fifteen documents, no network — and the same fifteen routes.

    This is the measurement §7.4 is built to produce, run against the whole
    corpus: **47 decisions, 43 rule-only, 4 flagged, 4 consulted, 4 agreed, 0
    overridden, 0 abstained**. A 100% agreement rate on four decisions is not a
    grade for the referee; §7.4 reads it the other way round — the rules were
    right and merely unsure, so the thresholds are conservative, which is the
    safe direction to be wrong in.

    The route comparison is the invariant underneath: consulting a referee that
    agrees must change *nothing* about the output. If it did, the fixtures
    would be steering the corpus rather than confirming it.
    """
    baseline = {name: assess_viability(sample(name)).route for name in SAMPLES}

    referee = fixture_referee()
    log = DecisionLog()
    routed = {
        name: assess_viability(sample(name), referee=referee, log=log).route
        for name in SAMPLES
    }

    assert routed == baseline, "an agreeing referee must not move a single route"
    assert baseline["port_mf_277_20180607"] == "norma"
    assert sum(1 for route in baseline.values() if route == "generico") == 14

    report = DecisionsReport.from_log(log)
    assert report.check() is None, report.check()
    assert (report.total, report.rule_only, report.flagged) == (47, 43, 4)
    assert (report.consulted, report.agreed) == (4, 4)
    assert (report.overrode, report.abstained) == (0, 0)
    assert report.cache_hits == 4

    assert referee.calls == 0
    assert referee.cache.hits == 4
    assert referee.cache.misses == 0, "every flagged question is recorded"

    flagged = {(r.doc, r.locator) for r in log if r.rule_flagged}
    assert flagged == {
        (f"{PAR_COSIT_26}.docx", locator) for locator in PAR_COSIT_26_FLAGGED
    } | {(f"{PARECER_93}.docx", locator) for locator in PARECER_93_FLAGGED}


@pytest.mark.parametrize("name", SAMPLES)
def test_the_referee_is_only_asked_about_flagged_decisions(name: str):
    """§7.3 constraint 1, per sample: a confident rule is never put to a vote.

    43 of the corpus's 47 decisions never reach the referee. That ratio is the
    cost model (§7.2 sizes the corpus at a dollar or three) *and* the safety
    model: a referee that saw every decision could move one the rules already
    knew the answer to.
    """
    referee = fixture_referee()
    log = DecisionLog()
    assess_viability(sample(name), referee=referee, log=log)

    for record in log:
        if record.referee_consulted:
            assert record.rule_flagged, f"{record.locator} was consulted while confident"
        elif record.rule_flagged:
            raise AssertionError(f"{record.locator} was flagged and never adjudicated")
    assert referee.calls == 0


# ---------------------------------------------------------------------------
# The outage — §7.3 constraint 5, end to end
# ---------------------------------------------------------------------------


def test_pipeline_completes_with_a_failing_referee():
    """A referee outage degrades quality; it never degrades availability.

    Every transport call raises, so all three of ``par_cosit_26``'s flagged
    decisions abstain. The verdict must be the referee-disabled one, exactly —
    route, coverage and blockers — because an abstention keeps the rule verdict
    and the deterministic rules produce valid output on their own, always.
    """
    baseline = assess_viability(sample(PAR_COSIT_26))

    referee = CachedAPIReferee(
        api_key=API_KEY, transport=explodes(ConnectionError("network unreachable"))
    )
    log = DecisionLog()
    verdict = assess_viability(sample(PAR_COSIT_26), referee=referee, log=log)

    assert verdict.route == baseline.route
    assert verdict.coverage == baseline.coverage
    assert verdict.blocker_codes == baseline.blocker_codes
    assert verdict.articles_found == baseline.articles_found
    assert verdict.articles_quoted == baseline.articles_quoted
    assert verdict.referee_overrode is False

    consulted = [r for r in log if r.referee_consulted]
    assert tuple(r.locator for r in consulted) == PAR_COSIT_26_FLAGGED
    assert referee.calls == len(PAR_COSIT_26_FLAGGED)
    for record in consulted:
        assert record.abstained is True
        assert record.overridden is False
        assert record.agreed is False, "an abstention is neither agreement nor override"
        assert record.final_verdict == record.rule_verdict
        assert "ConnectionError" in record.referee_rationale

    report = DecisionsReport.from_log(log)
    assert report.abstained == len(PAR_COSIT_26_FLAGGED)
    assert report.overrode == 0


def test_pipeline_completes_with_a_referee_that_has_no_key():
    """The misconfiguration case, over a real document: abstain, never call."""
    baseline = assess_viability(sample(PAR_COSIT_26))
    referee = CachedAPIReferee(api_key=None, transport=explodes())

    verdict = assess_viability(sample(PAR_COSIT_26), referee=referee)

    assert verdict.route == baseline.route
    assert verdict.blocker_codes == baseline.blocker_codes
    assert referee.calls == 0


# ---------------------------------------------------------------------------
# The optional extra
# ---------------------------------------------------------------------------


def test_httpx_is_not_imported():
    """The ``referee`` extra must stay genuinely optional.

    ``httpx`` is imported inside the default transport, on the first call that
    actually reaches the network — so importing this module, constructing a
    referee, serving a cache hit and running an injected transport must all
    leave it untouched. A module-level import would make an HTTP client a hard
    dependency of a parser whose default referee is ``none``, and the suite
    would not notice until an install without the extra failed to collect.

    Asserted **in a clean subprocess**, and that is not incidental. The obvious
    in-process form — ``assert "httpx" not in sys.modules`` — is a claim about
    the whole interpreter, which this test does not own: it failed here on a
    ``langsmith`` pytest plugin that imports ``httpx`` at plugin-load, before
    any test collects, while the package under test was entirely clean. The
    equally obvious repair, snapshotting presence before and after, is *worse*:
    once a third party has imported ``httpx``, a genuine module-level import in
    our own code changes nothing about the snapshot, and the guard silently
    stops guarding — verified by mutation, which it failed to kill.

    A subprocess with ``-I`` (isolated) and no pytest plugins is the only place
    the question "does *our* import graph pull in ``httpx``?" can actually be
    asked. It kills the mutation.
    """
    import subprocess

    probe = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import lexml_nonstat.referee.api as api\n"
        "from lexml_nonstat.referee import CachedAPIReferee, RefereeCache\n"
        "r = CachedAPIReferee(api_key='k',\n"
        "                     cache=RefereeCache(%r, read_only=True),\n"
        "                     transport=lambda *a, **k: (_ for _ in ()).throw(\n"
        "                         AssertionError('no network')))\n"
        "r.ask('own_articulation', 'x')\n"
        "print('httpx' in sys.modules)\n"
    ) % (str(REPO_ROOT / "src"), str(FIXTURES))

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"the probe itself failed:\n{result.stdout}\n{result.stderr}"
    )
    assert result.stdout.strip() == "False", (
        "importing `lexml_nonstat.referee` and asking the referee a question "
        "pulled in `httpx`. It must be imported only inside the default "
        "transport, on a call that actually reaches the network, so the "
        f"`referee` extra stays optional.\nprobe said: {result.stdout.strip()!r}"
    )

    # And the in-process objects still work without it having been needed here.
    referee = fixture_referee()
    assess_viability(sample(PAR_COSIT_26), referee=referee)
    CachedAPIReferee(api_key=API_KEY, transport=replies()).ask("own_articulation", "x")
    assert sys.modules["lexml_nonstat.referee.api"] is not None
