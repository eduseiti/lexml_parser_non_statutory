"""The disk cache — reproducibility first, cost second.

A-L.6 identifies this as *the seam*, exactly as §9.3 does for the referee:
recorded fixtures are simply a cache directory the tests are told not to write
to. That is what lets the two linked golden kinds compare with **no binary
present**, and what makes "zero subprocess spawns" an assertion rather than a
hope — a cache hit is served before anything is spawned, so a fully warm cache
spawns nothing at all.

The key covers everything that could change the answer: the context URN and the
paragraph text. Nothing else is in scope — there is no model here to version,
and A-L.5 forbids branching on a linker *version*, so a linker upgrade that
changes an answer must show up as a **reviewed diff** in a re-recorded fixture
rather than as a new cache key that silently coexists with the old one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .protocol import DEFAULT_CONTEXT_URN, Reference

__all__ = ["LinkerCache", "cache_key"]


def cache_key(context_urn: str, text: str) -> str:
    """A stable, filesystem-safe key for one paragraph asked in one context.

    ``\\x1f`` joins the parts so a text ending in the separator cannot collide
    with a different split — the same construction ``referee/cache.py`` uses.
    """
    payload = "\x1f".join([context_urn, text]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


class LinkerCache:
    """One JSON file per asked paragraph, under ``directory``.

    Args:
        directory: where entries live. ``tests/linker_fixtures/`` is one of
            these, opened read-only.
        read_only: never write. A fixture directory must not grow a new file
            because a test asked an unrecorded question — that would turn a
            missing fixture into a silent live subprocess on the next run, and
            the recorded corpus would stop being reviewable.
    """

    def __init__(self, directory: Path | str, *, read_only: bool = False) -> None:
        self.directory = Path(directory)
        self.read_only = read_only
        #: Counters, for tests and for diagnostics.
        self.hits = 0
        self.misses = 0

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> tuple[Reference, ...] | None:
        """The recorded references, or ``None`` for a miss.

        ``None`` and ``()`` are different answers and the distinction matters:
        ``()`` is a *recorded* "this paragraph cites nothing", which a fixture
        run must serve without spawning anything, while ``None`` means nobody
        has ever asked.
        """
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
        entries = data.get("references", [])
        if not isinstance(entries, list):
            return ()
        return tuple(Reference.from_dict(e) for e in entries if isinstance(e, dict))

    def put(
        self,
        key: str,
        references: Sequence[Reference],
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if self.read_only:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "references": [r.to_dict() for r in references],
        }
        if meta:
            payload["meta"] = meta
        self.path_for(key).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def entry_text(self, key: str) -> str | None:
        """The ``meta.text`` a recorded entry carries, for the ``--check`` run."""
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        meta = data.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("text"), str):
            return meta["text"]
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        mode = "read-only" if self.read_only else "read-write"
        return (
            f"LinkerCache({self.directory}, {mode}, "
            f"hits={self.hits}, misses={self.misses})"
        )


#: Re-exported for callers that build a key without importing the protocol.
DEFAULT_CONTEXT = DEFAULT_CONTEXT_URN
