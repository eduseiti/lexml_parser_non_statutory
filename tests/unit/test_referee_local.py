"""The local referee — the fallback, tested where it will actually fail.

§7.2 reached an unusual conclusion about the hardware here: a 6 GB Maxwell card
with no bf16 and no FlashAttention makes ``llama.cpp`` a *fallback*, not the
primary. That decision changes what these tests are for. The API referee has to
survive a hostile network; the local one has to survive **not being installed**,
because on almost every machine this pipeline runs on, ``llama-cli`` is not on
PATH and the GGUF is not on disk. A missing binary at document 240 of 300 must
be an abstention with a legible reason, not a traceback that discards four
minutes of work (§7.3 constraint 5).

Everything below drives :class:`LocalReferee` through an injected
``runner`` — ``(argv, stdin, timeout) -> stdout`` — which is the whole point of
that seam: argv construction, prompt delivery, output salvage, malformed JSON,
timeouts, non-zero exits and a missing binary are all exercised on a machine
with no ``llama.cpp``, no model and no network.

Two assertions here are not conveniences:

* ``--temp 0`` is invariant #4 written as a flag. A sampled local model breaks
  byte-identical output on every cache miss.
* construction must not check that the model exists — a fallback that refuses
  to be built is not a fallback, and the check belongs at ``ask`` time where it
  can degrade instead of raise.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lexml_nonstat.referee import (
    DEFAULT_BINARY,
    SYSTEM_PROMPT,
    LocalReferee,
    RefereeCache,
    Verdict,
    build_referee,
)

MODEL = "/nonexistent/models/qwen2.5-7b-instruct-q4_k_m.gguf"

#: ``(method name, positional args, a verdict the kind's vocabulary allows)``
PROTOCOL_METHODS = (
    ("is_own_articulation", ("Art. 2º Teste.", "Lei nº 7.713, de 1988 -"), "quoted"),
    ("is_heading", ("CONCLUSÃO", "…"), "heading"),
    ("section_kind", ("I -", "DA COMPETÊNCIA"), "capitulo"),
)


def reply(verdict: str = "quoted", confidence: float = 0.9, rationale: str = "porque sim"):
    """A runner that answers with well-formed JSON, as the binary should."""

    def runner(argv: list, stdin: str, timeout: float) -> str:
        return json.dumps(
            {"verdict": verdict, "confidence": confidence, "rationale": rationale}
        )

    return runner


def raises(exc: BaseException):
    """A runner that fails the way ``subprocess`` fails."""

    def runner(argv: list, stdin: str, timeout: float) -> str:
        raise exc

    return runner


def emits(text: str):
    """A runner that returns exactly ``text`` on stdout."""

    def runner(argv: list, stdin: str, timeout: float) -> str:
        return text

    return runner


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def test_argv_pins_the_model_and_zero_temperature():
    """Temperature 0 is invariant #4, not a preference.

    "Same input + same referee cache ⇒ byte-identical output" is a promise
    about the *whole* pipeline. A local model left at its default temperature
    would answer a cache miss differently on every run, and the goldens would
    start moving for reasons no diff could explain.
    """
    referee = LocalReferee(MODEL, binary="llama-cli", n_ctx=4096, n_predict=256)
    argv = referee.argv()

    assert argv[0] == "llama-cli"
    assert argv[argv.index("--model") + 1] == MODEL
    assert argv[argv.index("--temp") + 1] == "0"
    assert argv[argv.index("--ctx-size") + 1] == "4096"
    assert argv[argv.index("--n-predict") + 1] == "256"
    # stdout must carry the answer alone: no echoed prompt, no logging.
    assert "--no-display-prompt" in argv
    assert "--log-disable" in argv
    # The prompt arrives on stdin, so it never reaches a process listing.
    assert argv[-2:] == ["--file", "-"]
    assert all(isinstance(part, str) for part in argv)


def test_argv_is_deterministic_and_honours_the_binary_override():
    """Same construction, same command — and `main` is still `main` upstream."""
    a = LocalReferee(MODEL)
    b = LocalReferee(MODEL)
    assert a.argv() == b.argv()
    assert a.argv()[0] == DEFAULT_BINARY
    assert LocalReferee(MODEL, binary="/opt/llama.cpp/main").argv()[0] == (
        "/opt/llama.cpp/main"
    )


def test_stdin_carries_the_prompt():
    """The question goes down stdin, whole, and nothing else does.

    ``--file -`` means the prompt is never an argv element, so it cannot leak
    into ``ps`` output on a shared machine — the local mirror of the API
    referee's privacy story (see ``test_referee_prompts.py``).
    """
    seen: dict[str, object] = {}

    def runner(argv: list, stdin: str, timeout: float) -> str:
        seen["argv"] = argv
        seen["stdin"] = stdin
        seen["timeout"] = timeout
        return json.dumps({"verdict": "quoted", "confidence": 0.8, "rationale": "r"})

    excerpt = "Art. 2º- O imposto de renda das pessoas físicas será devido."
    ctx = "Lei nº 7.713, de 1988 -"
    referee = LocalReferee(MODEL, runner=runner, timeout=12.5)
    assert referee.ask("own_articulation", excerpt, ctx).verdict == "quoted"

    stdin = seen["stdin"]
    assert SYSTEM_PROMPT in stdin
    assert excerpt in stdin
    assert ctx in stdin
    assert seen["timeout"] == 12.5
    # The excerpt is not smuggled onto the command line as well.
    assert not any(excerpt in part for part in seen["argv"])


# ---------------------------------------------------------------------------
# Parsing what came back
# ---------------------------------------------------------------------------


def test_valid_json_output_yields_a_verdict():
    referee = LocalReferee(MODEL, runner=reply("quoted", 0.82, "citação da Lei 7.713"))
    verdict = referee.ask("own_articulation", "Art. 2º…", "Lei nº 7.713 -")

    assert not verdict.abstained
    assert verdict.verdict == "quoted"
    assert verdict.confidence == pytest.approx(0.82)
    assert verdict.rationale == "citação da Lei 7.713"
    assert referee.calls == 1


def test_json_embedded_in_prose_is_salvaged():
    """A chat model asked for JSON still writes a preamble half the time.

    Salvaging the first balanced ``{...}`` is worth doing — but only when it
    parses; see ``test_unparseable_json_abstains``. Abstaining over a "Claro!"
    would throw away a perfectly good answer and, worse, do it *silently* as a
    fallback-unavailable statistic.
    """
    output = (
        "Claro! Segue a análise solicitada:\n\n"
        '{"verdict": "quoted", "confidence": 0.77, "rationale": "norma externa"}\n\n'
        "Espero ter ajudado."
    )
    verdict = LocalReferee(MODEL, runner=emits(output)).ask("own_articulation", "Art. 2º…")

    assert verdict.verdict == "quoted"
    assert verdict.confidence == pytest.approx(0.77)


# --- the two defects the fan-out found, pinned to their fixed behaviour -----
#
# Both were in this cycle's own code, both were reported by the test-authoring
# agent rather than worked around, and both were reproduced before being fixed.
# These tests would have failed against the original implementation.


@pytest.mark.parametrize(
    "output, expected",
    [
        pytest.param(
            'Aqui: {"verdict": "quoted", "confidence": 0.9, "rationale": "x"}\n\n'
            'Outro exemplo: {"verdict": "own", "confidence": 0.5, "rationale": "y"}',
            "quoted",
            id="model-repeats-itself",
        ),
        pytest.param(
            'Nota {ver anexo}: {"verdict": "quoted", "confidence": 0.9, "rationale": "x"}',
            "quoted",
            id="preamble-contains-braces",
        ),
        pytest.param(
            'Contexto {"nota": 1} e a resposta '
            '{"verdict": "own", "confidence": 0.8, "rationale": "z"}',
            "own",
            id="preamble-is-itself-json",
        ),
    ],
)
def test_the_first_parseable_object_wins_not_the_greedy_span(output: str, expected: str):
    r"""Defect 1: the salvage was a greedy regex, so realistic output was lost.

    ``re.compile(r"\{.*\}", re.DOTALL)`` spans from the *first* brace to the
    *last* one. A model that answers and then repeats itself, or that writes a
    preamble containing braces, produced one unparseable blob and therefore an
    **abstention** — the fallback referee silently ceasing to answer, recorded
    in ``--decisions-report`` as `abstained` rather than as the parse bug it
    was. Fail-safe was never violated; usefulness was.

    The scan now yields every balanced object in order and takes the first that
    parses into an answer.
    """
    verdict = LocalReferee(MODEL, runner=emits(output)).ask("own_articulation", "Art. 2º…")

    assert not verdict.abstained, verdict.rationale
    assert verdict.verdict == expected


@pytest.mark.parametrize(
    "rationale",
    ["uma } chave solta", 'aspas \\" escapadas e { chave', "{aninhado}"],
)
def test_braces_inside_the_rationale_do_not_truncate_the_scan(rationale: str):
    """A brace inside a JSON *string* does not open an object.

    Without tracking quotes and their escapes, a rationale mentioning a brace
    would close the scan early and turn a good answer into an abstention. Legal
    prose quotes punctuation constantly, so this is not hypothetical.
    """
    output = json.dumps(
        {"verdict": "quoted", "confidence": 0.9, "rationale": rationale},
        ensure_ascii=False,
    )
    verdict = LocalReferee(MODEL, runner=emits(output)).ask("own_articulation", "Art. 2º…")

    assert verdict.verdict == "quoted"
    assert verdict.rationale == rationale


def test_cache_key_separates_two_quantisations_of_the_same_file_name(tmp_path: Path):
    """Defect 2: the cache key used the model's basename, not its path.

    ``models/q4/qwen2.5-7b.gguf`` and ``models/q8/qwen2.5-7b.gguf`` is the
    ordinary quantisation layout. They are different models that answer
    differently, and keying on the file name alone made them share a cache —
    serving one model's verdicts as the other's, invisibly, with a `cache_hit`
    recorded in the telemetry to say the answer was trustworthy.
    """
    cache_dir = tmp_path / "cache"
    q4 = LocalReferee(
        tmp_path / "q4" / "qwen2.5-7b.gguf",
        cache=RefereeCache(cache_dir),
        runner=reply("quoted", 0.9, "resposta do q4"),
    )
    q8 = LocalReferee(
        tmp_path / "q8" / "qwen2.5-7b.gguf",
        cache=RefereeCache(cache_dir),
        runner=reply("own", 0.8, "resposta do q8"),
    )

    assert q4.ask("own_articulation", "Art. 2º…").verdict == "quoted"
    assert q8.ask("own_articulation", "Art. 2º…").verdict == "own"
    assert q8.last_cache_hit is False, "q8 was served q4's cached verdict"
    assert q8.calls == 1

    # And each still caches for itself.
    assert q4.ask("own_articulation", "Art. 2º…").verdict == "quoted"
    assert q4.last_cache_hit is True
    assert q4.calls == 1


def test_garbage_output_abstains():
    """No JSON at all: keep the rule, say why."""
    verdict = LocalReferee(MODEL, runner=emits("Não sei responder isso.")).ask(
        "own_articulation", "Art. 2º…"
    )

    assert verdict.abstained
    assert "no JSON object" in verdict.rationale


def test_empty_output_abstains():
    """A binary that produced nothing is a failure, not an answer."""
    verdict = LocalReferee(MODEL, runner=emits("")).ask("own_articulation", "Art. 2º…")
    assert verdict.abstained


def test_unparseable_json_abstains():
    """Balanced braces are not the same thing as JSON."""
    verdict = LocalReferee(MODEL, runner=emits("{verdict: quoted, confidence: 0.9}")).ask(
        "own_articulation", "Art. 2º…"
    )

    assert verdict.abstained
    assert "unparseable JSON" in verdict.rationale


def test_json_without_a_verdict_key_abstains():
    verdict = LocalReferee(MODEL, runner=emits('{"confidence": 0.9}')).ask(
        "own_articulation", "Art. 2º…"
    )
    assert verdict.abstained
    assert "verdict" in verdict.rationale


@pytest.mark.parametrize("answer", ["maybe", "talvez", "own_or_quoted", ""])
def test_verdict_outside_vocabulary_abstains(answer: str):
    """A referee inventing a third answer is a referee to ignore.

    ``own_articulation`` admits exactly ``own`` and ``quoted``. Anything else
    is a model that did not understand the question, and letting it through
    would put an unmodelled string into the census — where "not quoted" reads
    as "the document's own article" and becomes fabricated structure.
    """
    verdict = LocalReferee(MODEL, runner=reply(answer)).ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert verdict.verdict is None


def test_non_numeric_confidence_abstains():
    verdict = LocalReferee(MODEL, runner=emits('{"verdict": "own", "confidence": "alta"}')).ask(
        "own_articulation", "Art. 2º…"
    )
    assert verdict.abstained
    assert "confidence" in verdict.rationale


def test_confidence_is_clamped_to_unit_interval():
    """A model claiming 5.0 is not five times as sure as one claiming 1.0."""
    high = LocalReferee(MODEL, runner=reply("own", 5.0)).ask("own_articulation", "x")
    low = LocalReferee(MODEL, runner=reply("own", -3.0)).ask("own_articulation", "x")

    assert high.confidence == 1.0
    assert low.confidence == 0.0


# ---------------------------------------------------------------------------
# Failure modes — §7.3 constraint 5, in the order they will actually happen
# ---------------------------------------------------------------------------


def test_missing_binary_abstains_with_a_useful_reason():
    """This is the failure that will actually happen in production.

    Not a timeout, not a malformed reply: ``llama-cli`` simply is not there.
    The rationale has to name the binary, because the person reading the
    decisions report is deciding whether to install something.
    """
    referee = LocalReferee(MODEL, binary="llama-cli", runner=raises(FileNotFoundError()))
    verdict = referee.ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert "llama-cli" in verdict.rationale
    assert "not found" in verdict.rationale


def test_timeout_abstains():
    """CPU inference at a few tokens/s means timeouts are routine, not exotic."""
    referee = LocalReferee(
        MODEL, runner=raises(subprocess.TimeoutExpired(cmd="llama-cli", timeout=120.0)),
        timeout=120.0,
    )
    verdict = referee.ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert "timed out" in verdict.rationale
    assert "120" in verdict.rationale


def test_nonzero_exit_abstains():
    """An exit code and the last line of stderr — enough to act on, no more."""
    error = subprocess.CalledProcessError(
        returncode=1,
        cmd=["llama-cli"],
        stderr="warming up\nerror: unable to load model from /nonexistent/…\n",
    )
    verdict = LocalReferee(MODEL, runner=raises(error)).ask("own_articulation", "Art. 2º…")

    assert verdict.abstained
    assert "exited 1" in verdict.rationale
    assert "unable to load model" in verdict.rationale


def test_an_unexpected_runner_exception_still_abstains():
    """Constraint 5 is total: the pipeline completes whatever the runner does."""
    verdict = LocalReferee(MODEL, runner=raises(MemoryError("out of RAM"))).ask(
        "own_articulation", "Art. 2º…"
    )

    assert verdict.abstained
    assert "MemoryError" in verdict.rationale


def test_unknown_kind_abstains_rather_than_raising():
    """A kind with no template must not crash a 300-document batch run."""
    referee = LocalReferee(MODEL, runner=reply())
    verdict = referee.ask("nonsense", "Art. 2º…")

    assert verdict.abstained
    assert "nonsense" in verdict.rationale
    assert referee.calls == 0, "a question with no template must not reach the binary"


def test_construction_does_not_require_the_model_to_exist():
    """A fallback that refuses to be built is not a fallback.

    Checking the GGUF at construction would mean ``--referee=local`` fails at
    startup on every machine that does not have it — turning a graceful
    degradation into a configuration error, which is exactly backwards for the
    component whose job is to be optional.
    """
    missing = Path("/definitely/not/here/model.gguf")
    assert not missing.exists()

    referee = LocalReferee(missing)
    assert referee.model_path == missing
    assert str(missing) in referee.argv()
    assert build_referee("local", model_path=missing).name == "local"

    # And asking degrades rather than raises, even with the real runner absent.
    verdict = LocalReferee(missing, runner=raises(FileNotFoundError())).ask(
        "own_articulation", "Art. 2º…"
    )
    assert verdict.abstained


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_cache_is_keyed_on_the_model_path(tmp_path: Path):
    """Switching models must never reuse the old model's answers.

    A verdict is the *model's* opinion. Sharing a cache across models would
    make a fixture refresh invisible — §9.3 wants a provider or model change to
    show up as a reviewed diff of new files, never as a silent reuse.
    """
    cache_dir = tmp_path / "cache"
    question = ("own_articulation", "Art. 2º Teste.", "Lei nº 7.713 -")

    first = LocalReferee(
        tmp_path / "model-a.gguf",
        cache=RefereeCache(cache_dir),
        runner=reply("quoted", 0.91, "a"),
    )
    assert first.ask(*question).verdict == "quoted"
    assert first.calls == 1

    # Same question, same cache directory, different model: a miss.
    second = LocalReferee(
        tmp_path / "model-b.gguf",
        cache=RefereeCache(cache_dir),
        runner=reply("own", 0.88, "b"),
    )
    assert second.ask(*question).verdict == "own"
    assert second.calls == 1
    assert len(list(cache_dir.glob("*.json"))) == 2

    # And each still gets its own answer back without running anything.
    warm = LocalReferee(
        tmp_path / "model-a.gguf",
        cache=RefereeCache(cache_dir),
        runner=raises(AssertionError("must not run")),
    )
    assert warm.ask(*question).verdict == "quoted"
    assert warm.calls == 0
    assert warm.last_cache_hit is True


def test_cache_hit_does_not_run_the_binary(tmp_path: Path):
    """The seam §9.3 names: a warm cache is an offline referee."""
    cache_dir = tmp_path / "cache"
    question = ("own_articulation", "Art. 16 Teste.", "")

    cold = LocalReferee(
        tmp_path / "m.gguf", cache=RefereeCache(cache_dir), runner=reply("quoted", 0.7)
    )
    assert cold.ask(*question).verdict == "quoted"
    assert cold.last_cache_hit is False

    hot = LocalReferee(
        tmp_path / "m.gguf",
        cache=RefereeCache(cache_dir),
        runner=raises(AssertionError("the binary must not be run on a cache hit")),
    )
    verdict = hot.ask(*question)
    assert verdict.verdict == "quoted"
    assert hot.calls == 0
    assert hot.last_cache_hit is True


def test_abstention_is_not_cached(tmp_path: Path):
    """A missing binary is a fact about the machine, not about the question.

    Caching it would make one broken installation permanent: the referee would
    keep abstaining from disk long after ``llama.cpp`` was installed.
    """
    cache_dir = tmp_path / "cache"
    question = ("own_articulation", "Art. 18 Teste.", "")

    broken = LocalReferee(
        tmp_path / "m.gguf",
        cache=RefereeCache(cache_dir),
        runner=raises(FileNotFoundError()),
    )
    assert broken.ask(*question).abstained
    assert not cache_dir.exists() or list(cache_dir.glob("*.json")) == []

    fixed = LocalReferee(
        tmp_path / "m.gguf", cache=RefereeCache(cache_dir), runner=reply("own", 0.9)
    )
    assert fixed.ask(*question).verdict == "own"
    assert len(list(cache_dir.glob("*.json"))) == 1


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,args,answer", PROTOCOL_METHODS)
def test_all_three_protocol_methods_work(method: str, args: tuple, answer: str):
    """§7.3's protocol is three questions; the local referee answers all three.

    They share one code path deliberately — cache, prompt, runner, parse — so a
    fix to one is a fix to all, and a divergence between them is the bug this
    parametrisation catches.
    """
    referee = LocalReferee(MODEL, runner=reply(answer, 0.83, "porquê"))
    verdict = getattr(referee, method)(*args)

    assert isinstance(verdict, Verdict)
    assert verdict.verdict == answer
    assert verdict.confidence == pytest.approx(0.83)
    assert referee.calls == 1
    assert referee.name == "local"
