"""The local referee — ``llama.cpp`` as a subprocess, and why it is the fallback.

§7.2 measured the hardware and reached an unusual conclusion: **skip the local
SLM as primary**. A 6 GB Maxwell card (CC 5.2, no bf16, no FlashAttention, and
dropped by recent CUDA/PyTorch) caps a 4-bit 7B with little context room, and
long-context legal pt-BR discrimination is precisely where small models are
weakest — which is exactly what we would delegate. CPU inference on 62 GB of
RAM is fine for a *batch* pipeline at a few tokens a second.

So this is the fallback, not the default, and it is built the way a fallback
should be: the thing most likely to go wrong is that the binary or the model is
simply not there, and that has to be an abstention with a clear reason rather
than a stack trace at the end of a long run.

The runner is injected
----------------------
``runner`` is ``(argv, stdin, timeout) -> str``, defaulting to
:func:`subprocess.run`. Injecting it makes argv construction, output parsing,
malformed output, timeouts and a missing binary all testable on a machine with
no ``llama.cpp`` and no model — which is every machine this suite runs on.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from .cache import RefereeCache, cache_key
from .prompts import VOCABULARIES, build_prompt
from .protocol import Verdict

__all__ = ["DEFAULT_BINARY", "LocalReferee", "Runner"]

#: ``(argv, stdin, timeout) -> stdout``
Runner = Callable[[list, str, float], str]

#: `llama.cpp`'s CLI. Renamed from `main` upstream; overridable per instance.
DEFAULT_BINARY = "llama-cli"

#: Local inference is slow by design here (§7.2: "a few tokens/s — acceptable
#: offline, not interactive"), so the default timeout is generous.
DEFAULT_TIMEOUT = 120.0

def _json_objects(text: str):
    r"""Yield every **balanced** ``{...}`` in ``text``, in order.

    A chat model asked for JSON still wraps it in prose, so salvaging the
    object beats abstaining over a preamble. The obvious ``r"\{.*\}"`` with
    ``DOTALL`` does not do that: it is greedy, so it spans from the *first*
    brace to the *last* one, and two realistic outputs become abstentions — a
    preamble containing braces, and a model that answers then repeats itself.
    Both were reproduced before this was written.

    Yielding *every* candidate rather than only the first is what handles
    ``Nota {ver anexo}: {"verdict": …}``: the caller takes the first one that
    actually parses into an answer, so a brace-bearing preamble costs a failed
    ``json.loads`` instead of a lost verdict.

    A brace inside a JSON string does not open an object, so quotes and their
    escapes are tracked; without that, a rationale containing ``{`` would close
    the scan early.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text or ""):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                yield text[start : i + 1]


def _subprocess_runner(argv: list, stdin: str, timeout: float) -> str:
    completed = subprocess.run(
        argv,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return completed.stdout


class LocalReferee:
    """``llama.cpp`` behind the same protocol as the API referee.

    Args:
        model_path: the GGUF file. Not checked at construction — a fallback
            that refuses to be built is not a fallback.
        binary: the ``llama.cpp`` CLI to run.
        cache: shared with the API referee's cache type; the full model path is
            part of the key, so switching models — including between two
            quantisations of the same file name — never reuses the old answers.
        runner: see the module docstring.
        n_ctx: context window passed to the binary.
    """

    name = "local"

    def __init__(
        self,
        model_path: Path | str,
        *,
        binary: str = DEFAULT_BINARY,
        cache: RefereeCache | Path | str | None = None,
        runner: Runner | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        n_ctx: int = 4096,
        n_predict: int = 256,
    ) -> None:
        self.model_path = Path(model_path)
        self.binary = binary
        self.timeout = timeout
        self.n_ctx = n_ctx
        self.n_predict = n_predict
        self.runner: Runner = runner or _subprocess_runner
        if isinstance(cache, (str, Path)):
            cache = RefereeCache(cache)
        self.cache = cache
        self.calls = 0
        self.last_cache_hit = False

    # -- the protocol ------------------------------------------------------

    def is_own_articulation(self, excerpt: str, ctx: str) -> Verdict:
        return self.ask("own_articulation", excerpt, ctx)

    def is_heading(self, para: str, ctx: str, next_ctx: str = "") -> Verdict:
        return self.ask("heading", para, ctx, next_ctx)

    def section_kind(self, label: str, heading: str) -> Verdict:
        return self.ask("section_kind", label, heading)

    def quotation_boundary(self, excerpt: str, ctx: str) -> Verdict:
        return self.ask("quotation_boundary", excerpt, ctx)

    # -- the machinery -----------------------------------------------------

    def argv(self) -> list:
        """The command line, as a list. Pinned by a test.

        ``--temp 0`` is not a preference: invariant #4 requires the same input
        and the same cache to produce byte-identical output, and a sampled
        local model would break that on every cache miss.
        """
        return [
            self.binary,
            "--model",
            str(self.model_path),
            "--ctx-size",
            str(self.n_ctx),
            "--n-predict",
            str(self.n_predict),
            "--temp",
            "0",
            "--no-display-prompt",
            "--log-disable",
            "--file",
            "-",
        ]

    def ask(
        self, kind: str, excerpt: str, ctx: str = "", next_ctx: str = ""
    ) -> Verdict:
        """Adjudicate one question locally. Never raises."""
        self.last_cache_hit = False
        # The **resolved** path, not the basename: `models/q4/qwen2.5-7b.gguf`
        # and `models/q8/qwen2.5-7b.gguf` are the ordinary quantisation layout,
        # they answer differently, and keying on the filename alone would serve
        # one model's verdicts for the other.
        key = cache_key(f"local:{self.model_path}", kind, excerpt, ctx, next_ctx)

        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                self.last_cache_hit = True
                return cached

        verdict = self._call(kind, excerpt, ctx, next_ctx)
        if self.cache is not None and not verdict.abstained:
            self.cache.put(key, verdict, meta={"model": str(self.model_path), "kind": kind})
        return verdict

    def _call(
        self, kind: str, excerpt: str, ctx: str, next_ctx: str = ""
    ) -> Verdict:
        try:
            system, user = build_prompt(kind, excerpt, ctx, next_ctx)
        except KeyError:
            return Verdict.abstain(f"no prompt template for decision kind {kind!r}")

        self.calls += 1
        try:
            output = self.runner(self.argv(), f"{system}\n\n{user}\n", self.timeout)
        except FileNotFoundError:
            return Verdict.abstain(
                f"local referee unavailable: {self.binary!r} not found on PATH"
            )
        except subprocess.TimeoutExpired:
            return Verdict.abstain(
                f"local referee timed out after {self.timeout:g}s"
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip().splitlines()
            return Verdict.abstain(
                f"local referee exited {exc.returncode}: "
                f"{detail[-1] if detail else 'no stderr'}"
            )
        except Exception as exc:  # noqa: BLE001 - constraint 5 is total
            return Verdict.abstain(f"{type(exc).__name__}: {exc}")

        return self._parse(kind, output)

    @staticmethod
    def _parse(kind: str, output: str) -> Verdict:
        data = None
        candidates = list(_json_objects(output or ""))
        parsed: list[str] = []
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except ValueError:
                continue
            parsed.append(candidate)
            if isinstance(value, dict) and "verdict" in value:
                data = value
                break

        if data is None:
            if not candidates:
                return Verdict.abstain(
                    f"no JSON object in output: {(output or '')[:120]!r}"
                )
            if not parsed:
                return Verdict.abstain(
                    f"unparseable JSON in output: {candidates[0][:120]!r}"
                )
            return Verdict.abstain(f"JSON without a 'verdict' key: {parsed[0][:120]}")

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
