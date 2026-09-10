"""External reference URNs — the optional, probed linker (plan §18, A-L.1…A-L.9).

The parser generates URNs for a document's own identity; this subpackage is
what lets a *cited* norm become one too, so that
``Lei nº 7.713, de 22 de dezembro de 1988`` in the body of a parecer renders as

.. code-block:: xml

    <Remissao xlink:href="urn:lex:br:federal:lei:1988-12-22;7713">Lei nº 7.713, de 22 de dezembro de 1988</Remissao>

rather than surviving only as whatever hyperlink the source file happened to
carry.

**It is optional, and off by default.** ``--linker`` defaults to ``none``
everywhere, exactly as ``--referee`` does, and :class:`~.null.NullLinker` is
what the whole regression suite runs against. That is what keeps A-R.9 true
(the suite stays green against ``lexml/`` alone), keeps Cycle 9's "no network
dependency anywhere" reachable, and keeps the 125 goldens delivered by earlier
cycles byte-identical: a renderer handed no references emits exactly what it
emitted before this cycle existed.

**Four modes**, mirroring the referee's three:

``none``
    :class:`~.null.NullLinker`. Resolves nothing. The default.
``auto``
    Probe for the binary; use it if present, degrade to ``none`` if not.
``fixtures``
    A :class:`~.linkertool.LinkertoolLinker` over a **read-only** cache. Serves
    recorded answers and **cannot spawn a subprocess** — this is the mode the
    linked goldens regenerate under, which is why they compare on a checkout
    with no binary at all (A-L.6).
``<path>``
    That executable, spawned as a co-process.

**What it can and cannot reach** (A-L.8). The Haskell grammar recognises lei,
lei complementar and delegada, decreto, decreto-lei, decreto legislativo,
emenda constitucional, medida provisória, constituição, the apelidos and the
STF legacy codes. It recognises **no** portaria, instrução normativa, parecer,
ato declaratório or solução de consulta — the genres this parser exists for —
and its ``súmula`` rule is commented out. Measured over the 15 samples it
resolves 379 references in 14 of them, all statutory. A parecer citing another
parecer stays unlinked, and that gap is a measurement this cycle publishes
rather than a limitation it hides.
"""

from __future__ import annotations

from .cache import LinkerCache, cache_key
from .linkertool import END_MARKER, LinkertoolLinker
from .null import NullLinker
from .probe import (
    DEFAULT_LINKER_PATH,
    LinkerCapabilities,
    linker_env,
    probe_linker,
    resolve_binary,
)
from .protocol import DEFAULT_CONTEXT_URN, Linker, Reference

__all__ = [
    "DEFAULT_CONTEXT_URN",
    "DEFAULT_LINKER_PATH",
    "END_MARKER",
    "LINKER_MODES",
    "Linker",
    "LinkerCache",
    "LinkerCapabilities",
    "LinkertoolLinker",
    "NullLinker",
    "Reference",
    "build_linker",
    "cache_key",
    "linker_env",
    "probe_linker",
    "resolve_binary",
]

#: The values ``--linker`` accepts, besides an explicit path.
LINKER_MODES: tuple[str, ...] = ("none", "auto", "fixtures")


def build_linker(mode: str = "none", **kwargs):
    """Construct a linker from a ``--linker`` value.

    ``none`` returns a :class:`~.null.NullLinker` rather than ``None`` so a
    caller always has an object to talk to; rendering reaches the same output
    either way, by design.

    ``auto`` degrades to :class:`~.null.NullLinker` when the probe finds no
    usable binary — A-L.5's rule, and the reason a bare checkout needs no
    special-casing anywhere else in the package.

    ``fixtures`` requires a ``cache`` and opens it read-only, so a fixture miss
    is an empty answer rather than a silent live subprocess.

    Raises:
        ValueError: on an unknown mode — a typo in ``--linker`` must not
            silently disable linking, the same rule ``build_referee`` follows.
    """
    if mode == "none":
        return NullLinker()

    if mode == "auto":
        capabilities = probe_linker(kwargs.get("binary"))
        if not capabilities.available:
            return NullLinker()
        return LinkertoolLinker(
            capabilities.path,
            cache=kwargs.get("cache"),
            timeout=kwargs.get("timeout", 30.0),
        )

    if mode == "fixtures":
        cache = kwargs.get("cache")
        if cache is None:
            raise ValueError("--linker=fixtures needs a cache directory")
        if not cache.read_only:
            raise ValueError("--linker=fixtures needs a read-only cache")
        # `binary=""` can never resolve, so a fixture miss answers `()` instead
        # of reaching for a process. The mode's guarantee is structural.
        return LinkertoolLinker("", cache=cache, timeout=kwargs.get("timeout", 30.0))

    if mode in LINKER_MODES:  # pragma: no cover - exhaustive by construction
        raise ValueError(f"unhandled linker mode {mode!r}")

    # Anything else is a path.
    return LinkertoolLinker(
        mode, cache=kwargs.get("cache"), timeout=kwargs.get("timeout", 30.0)
    )
