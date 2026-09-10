"""The ``linkertool`` co-process backend.

A-L.1 is explicit that the recogniser itself is **not** ported: ``lexml-linker``
is a Haskell Alex+Parsec compiler carrying ~5,561 municípios, the 27 states, the
apelidos and the STF legacy codes, and reimplementing that grammar in Python is
a different project from calling it. So this module does exactly what the
reference parser's ``LinkerActor.scala`` does, and nothing more.

**The wire protocol** (`LinkerActor.scala:29-37,63-85`). The binary is started
once as ``linkertool --hxml --xml --contexto=INLINE`` and kept alive across
paragraphs. Per query: write the context URN line, write the HTML fragment,
write ``###LEXML-END###``; then read lines until ``###LEXML-END###`` comes back.
Spawning is **lazy** — the first uncached query starts it — so a run served
entirely from the fixture cache spawns nothing at all, which is what makes
A-L.6's zero-spawn assertion structural rather than incidental.

**Three things measured during Cycle 8e that the protocol description does not
tell you:**

1. *The linker's output is not well-formed XML.* It writes
   ``<span xlink:href="…">`` without ever declaring the ``xlink`` prefix, so
   parsing the reply directly raises ``XMLSyntaxError``. The reply is wrapped in
   a prefix-declaring root before parsing.
2. *Offsets must come from the parsed tree, never from string indices.* The
   reply is XML-escaped — ``&amp;``, ``&lt;``, ``&quot;`` — so a citation's
   position in the reply string is not its position in the source text.
   :func:`_spans_of` walks the tree and counts *decoded* characters, and
   :meth:`LinkertoolLinker.find_refs` then verifies ``text[start:end]`` equals
   what the linker wrapped. A mismatch discards the reference rather than
   emitting a URN over the wrong words.
3. *The child needs a UTF-8 locale* (:func:`~.probe.linker_env`). Without one it
   dies on the first accented character, and every paragraph here is Portuguese.

**Nothing raises.** A dead process, a timeout, a reply that will not parse, a
binary that vanished — all of them answer ``()``, and the next call is free to
respawn. The protocol's contract is that a linker degrades quality, never
availability.
"""

from __future__ import annotations

import atexit
import subprocess
import threading
from pathlib import Path
from xml.sax.saxutils import escape

from lxml import etree

from .cache import LinkerCache, cache_key
from .probe import linker_env, resolve_binary
from .protocol import DEFAULT_CONTEXT_URN, Reference

__all__ = ["END_MARKER", "LinkertoolLinker"]

#: The framing token both sides write (`LinkerTool.hs`, `LinkerActor.scala:71`).
END_MARKER = "###LEXML-END###"

_XLINK_NS = "http://www.w3.org/1999/xlink"
_WRAPPER_OPEN = f'<lexml-linker-reply xmlns:xlink="{_XLINK_NS}">'
_WRAPPER_CLOSE = "</lexml-linker-reply>"


def _spans_of(element: etree._Element) -> tuple[tuple[int, int, str, str], ...]:
    """Every ``span/@xlink:href`` under ``element``, as decoded-character spans.

    The walk counts characters of the *parsed* text, so entity escaping in the
    reply cannot shift an offset. Nested spans are not descended into: the
    linker wraps a citation once, and a span inside a span would double-count
    its text.
    """
    out: list[tuple[int, int, str, str]] = []
    position = 0

    def walk(node: etree._Element) -> None:
        nonlocal position
        position += len(node.text or "")
        for child in node:
            start = position
            inner = "".join(child.itertext())
            if etree.QName(child).localname == "span" and child.get(
                f"{{{_XLINK_NS}}}href"
            ):
                position += len(inner)
                out.append(
                    (start, position, child.get(f"{{{_XLINK_NS}}}href") or "", inner)
                )
            else:
                walk(child)
            position += len(child.tail or "")

    walk(element)
    return tuple(out)


class LinkertoolLinker:
    """A long-lived ``linkertool`` child process, optionally cached.

    Args:
        binary: path to the executable. ``None`` uses
            :func:`~.probe.resolve_binary`'s search order — upstream's
            ``/usr/local/bin/linkertool`` first, then ``PATH``.
        cache: a :class:`~.cache.LinkerCache`, consulted **before** the process
            is spawned. A read-only fixture cache therefore never spawns.
        timeout: seconds to wait for one reply before giving the process up.
    """

    name = "linkertool"
    enabled = True

    def __init__(
        self,
        binary: str | Path | None = None,
        *,
        cache: LinkerCache | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.binary = binary
        self.cache = cache
        self.timeout = timeout
        #: How many child processes this linker has started. Asserted by the
        #: fixtures-only tests, which require it to stay at zero.
        self.spawns = 0
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._closed = False
        atexit.register(self.close)

    # -- process lifecycle -------------------------------------------------

    def _ensure_process(self) -> subprocess.Popen | None:
        """The live child, spawning one if needed. ``None`` if unavailable."""
        if self._process is not None and self._process.poll() is None:
            return self._process
        path = resolve_binary(self.binary)
        if path is None:
            return None
        try:
            self._process = subprocess.Popen(
                [path, "--hxml", "--xml", f"--contexto=INLINE"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=linker_env(),
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except (OSError, subprocess.SubprocessError):
            self._process = None
            return None
        self.spawns += 1
        return self._process

    def close(self) -> None:
        """Stop the child, if any. Idempotent, and safe at interpreter exit."""
        process, self._process = self._process, None
        self._closed = True
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        finally:
            if process.poll() is None:  # pragma: no cover - slow child
                process.kill()

    def _discard_process(self) -> None:
        """Drop a child that misbehaved, so the next call starts a fresh one."""
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.kill()
        except OSError:  # pragma: no cover - already gone
            pass

    # -- the one question --------------------------------------------------

    def _exchange(self, context_urn: str, fragment: str) -> str | None:
        """One request/reply round trip, or ``None`` if anything went wrong."""
        process = self._ensure_process()
        if process is None or process.stdin is None or process.stdout is None:
            return None
        try:
            process.stdin.write(f"{context_urn}\n{fragment}\n{END_MARKER}\n")
            process.stdin.flush()
        except (OSError, ValueError):
            self._discard_process()
            return None

        lines: list[str] = []
        while True:
            try:
                line = process.stdout.readline()
            except (OSError, ValueError):
                self._discard_process()
                return None
            if not line:
                # EOF: the child died mid-answer.
                self._discard_process()
                return None
            if line.rstrip("\n") == END_MARKER:
                return "".join(lines)
            lines.append(line)

    def find_refs(
        self, text: str, context_urn: str = DEFAULT_CONTEXT_URN
    ) -> tuple[Reference, ...]:
        """Every citation in ``text``. Never raises; ``()`` on any failure.

        A cache hit answers without touching the process, so ``spawns`` stays
        at zero for a fully recorded run.
        """
        if not text.strip():
            return ()

        key = cache_key(context_urn, text)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        with self._lock:
            reply = self._exchange(context_urn, f"<p>{escape(text)}</p>")

        references = self._parse_reply(reply, text) if reply is not None else ()

        if self.cache is not None and reply is not None:
            self.cache.put(key, references, meta={"text": text, "linker": self.name})
        return references

    def _parse_reply(self, reply: str, text: str) -> tuple[Reference, ...]:
        """Turn one decorated fragment into verified spans over ``text``."""
        try:
            root = etree.fromstring(
                (_WRAPPER_OPEN + reply.strip() + _WRAPPER_CLOSE).encode("utf-8")
            )
        except etree.XMLSyntaxError:
            return ()

        out: list[Reference] = []
        for start, end, urn, inner in _spans_of(root):
            # The span must address the text we sent. If the linker echoed
            # something else — a normalisation, a dropped entity, a bug — the
            # offsets are meaningless and a URN over the wrong words is worse
            # than no URN at all.
            if not urn or start >= end or end > len(text):
                continue
            if text[start:end] != inner:
                continue
            out.append(Reference(start, end, urn, inner))
        return tuple(sorted(out))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"LinkertoolLinker(binary={self.binary!r}, spawns={self.spawns})"
