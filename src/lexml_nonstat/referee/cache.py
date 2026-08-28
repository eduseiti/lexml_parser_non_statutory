"""The disk cache — reproducibility first, cost second.

§7.3 constraint 3 asks for a cache "by excerpt hash", and §9.3 identifies it as
*the seam*: recorded fixtures are simply a cache directory the tests are told
not to write to. That is why this module is more than an optimisation. It is
what makes a referee-assisted run repeatable (invariant #4), and what lets the
whole referee surface be tested offline without a single mock of the referee
itself.

The key covers everything that could change the answer — model, decision kind,
excerpt and context — so refreshing a fixture after a provider change produces
a *new* file rather than silently reusing an answer from a different model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .protocol import Verdict

__all__ = ["RefereeCache", "cache_key"]


def cache_key(model: str, kind: str, excerpt: str, ctx: str = "") -> str:
    """A stable, filesystem-safe key for one question put to one model."""
    payload = "\x1f".join((model, kind, excerpt, ctx)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


class RefereeCache:
    """One JSON file per adjudicated question, under ``directory``.

    Args:
        directory: where entries live. ``tests/referee_fixtures/`` is one of
            these, opened read-only.
        read_only: never write. A fixture directory must not grow a new file
            because a test asked an unrecorded question — that would turn a
            missing fixture into a silent live call on the next run.
    """

    def __init__(self, directory: Path | str, *, read_only: bool = False) -> None:
        self.directory = Path(directory)
        self.read_only = read_only
        #: Counters, for tests and for `--decisions-report`.
        self.hits = 0
        self.misses = 0

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> Verdict | None:
        path = self.path_for(key)
        if not path.is_file():
            self.misses += 1
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt entry is a miss, not a crash. The next call refills it
            # (or, read-only, simply declines) — never a hard failure over a
            # cache file.
            self.misses += 1
            return None
        self.hits += 1
        return Verdict.from_dict(data.get("verdict", data))

    def put(self, key: str, verdict: Verdict, *, meta: dict[str, Any] | None = None) -> None:
        if self.read_only:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"verdict": verdict.to_dict()}
        if meta:
            payload["meta"] = meta
        self.path_for(key).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        mode = "read-only" if self.read_only else "read-write"
        return f"RefereeCache({self.directory}, {mode}, hits={self.hits}, misses={self.misses})"
