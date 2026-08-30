"""Ingestion: source documents → :class:`StyledDoc`.

DOCX, HTML and plain text, all reaching the same model. Three readers, one
shape: everything downstream — segmentation, hierarchy inference, routing,
rendering — was written once against ``StyledDoc`` and is therefore
format-agnostic by construction rather than by three parallel code paths kept
in step by hand.

:func:`read_document` is the dispatching front door and the one the CLI calls,
so a fourth format costs one reader module and one entry in :data:`READERS`.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable

from .docx_reader import DocxReadError, StyleResolver, normalize_text, read_docx
from .html_reader import HtmlReadError, read_html
from .styled import (
    Block,
    Inline,
    StyledCell,
    StyledDoc,
    StyledPara,
    StyledRow,
    StyledTable,
)
from .txt_reader import TxtReadError, read_txt

__all__ = [
    "Block",
    "DocxReadError",
    "HtmlReadError",
    "Inline",
    "READERS",
    "StyleResolver",
    "StyledCell",
    "StyledDoc",
    "StyledPara",
    "StyledRow",
    "StyledTable",
    "TxtReadError",
    "UnsupportedFormatError",
    "normalize_text",
    "read_docx",
    "read_document",
    "read_html",
    "read_txt",
]

#: Filename suffix → the reader that handles it. Lowercase keys; the lookup
#: lowercases the suffix, so ``REPORT.HTM`` from a legacy export dispatches.
#:
#: This table is the single place formats are declared. The error message names
#: its keys rather than a hand-maintained list, so the two cannot disagree.
READERS: dict[str, Callable[..., StyledDoc]] = {
    ".docx": read_docx,
    ".html": read_html,
    ".htm": read_html,
    ".txt": read_txt,
}


class UnsupportedFormatError(Exception):
    """Raised by :func:`read_document` for a suffix no reader claims.

    Distinct from :class:`DocxReadError` and :class:`HtmlReadError`, which mean
    "the right reader tried and could not". This one means "no reader applies",
    which is a mistake in the *invocation* rather than a problem with the
    document — the CLI maps it to exit 2 for exactly that reason.
    """


def _accepted_kwargs(reader: Callable[..., StyledDoc], kwargs: dict[str, Any]) -> dict[str, Any]:
    """The subset of ``kwargs`` the reader actually declares.

    Callers dispatching over a mixed batch pass one set of options for the
    whole run — ``drop_strikethrough`` means something to DOCX and HTML and
    nothing to plain text. Filtering here lets the caller stay format-blind,
    which is the entire point of having a dispatcher; raising ``TypeError``
    would push the format knowledge back out to every caller.

    A reader declaring ``**kwargs`` receives everything, so this stays correct
    if a future reader forwards its options on.
    """
    try:
        signature = inspect.signature(reader)
    except (TypeError, ValueError):  # a builtin or C callable declares nothing
        return dict(kwargs)
    parameters = signature.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return dict(kwargs)
    return {name: value for name, value in kwargs.items() if name in parameters}


def read_document(path: str | Path, **kwargs: Any) -> StyledDoc:
    """Read any supported document, dispatching on its filename suffix.

    Args:
        path: the document to read. The suffix decides the reader, so this is
            a real path — pass markup or text to :func:`read_html` /
            :func:`read_txt` directly if you have it in hand.
        **kwargs: forwarded to the chosen reader, filtered to the keywords it
            declares (see :func:`_accepted_kwargs`). An option meaningless to
            one format is dropped for that format, not an error.

    Returns:
        A :class:`StyledDoc`.

    Raises:
        UnsupportedFormatError: no reader claims the suffix. The message names
            every supported suffix, so the caller need not know this table.
        DocxReadError, HtmlReadError: the reader could not read the file.
    """
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        supported = ", ".join(sorted(READERS))
        suffix = path.suffix or "(none)"
        raise UnsupportedFormatError(
            f"unsupported format {suffix!r} for {path.name}; supported: {supported}"
        )
    return reader(path, **_accepted_kwargs(reader, kwargs))
