"""Plain text → :class:`StyledDoc`.

The third reader, and by far the poorest in evidence — which is the point. A
text file carries no typography at all: no styles, no outline levels, no
numbering, no bold. The temptation is to recover some of it — to read an
ALL-CAPS line as a heading, or ``1.`` at the start of a line as a list item —
and that temptation is exactly what plan invariant #8 forbids. Structure that
is *inferred* belongs to Cycle 4, which infers it from evidence and records its
confidence; structure invented by a reader arrives downstream indistinguishable
from structure that was really in the source, and nothing later can tell the
difference. So every block this module produces is a ``StyledPara`` with
``style=None`` and exactly one plain ``Inline``, and the only signal it reports
is the one plain text genuinely carries: **indentation**.

What text *does* encode, and this module therefore reads:

- **Blank lines separate blocks.** The near-universal convention of plain-text
  documents, and the only paragraph boundary the format has.
- **Wrapped lines belong to one paragraph.** A line break inside a block is
  hard-wrapping, not a paragraph break, so the lines join with a single space
  — the same result :func:`~.docx_reader.normalize_text` gives a DOCX
  paragraph whose text spans several runs.
- **Leading spaces are a displacement.** ``indent_direct = 180 * n_spaces``,
  so four spaces come to 720 twips: Word's default tab stop, and therefore the
  number a DOCX of the same document would carry. Cycle 4's quotation guard
  reads that field, so an indented quotation in a text file reaches it as the
  same evidence it would from a DOCX.

**Encoding is a robustness question, not a correctness one.** A 300+ document
legacy corpus will hold Latin-1 alongside UTF-8, and refusing to read one of
them helps nobody. UTF-8 is tried first because it is both the modern default
and self-validating — arbitrary bytes are usually *not* valid UTF-8 — and
Latin-1 is the fallback because it maps every byte to some character and so
cannot itself fail. The result is a reader that never raises on content, only
on a file it cannot open.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .docx_reader import DocxReadError, normalize_text


class TxtReadError(DocxReadError):
    """Raised when a text *source* cannot be read.

    A **subclass** of :class:`~.docx_reader.DocxReadError` rather than a sibling,
    which is the opposite of :class:`~.html_reader.HtmlReadError`'s choice, and
    for the opposite reason. ``HtmlReadError`` describes failures of a different
    library that a caller should not silently conflate. This describes the one
    failure mode a text file has — "could not open it", already described by the
    OS — so a caller catching ``DocxReadError`` to mean "ingestion failed on a
    file" is right, and should keep working. The distinct name is here so the
    message a user sees does not say *DOCX* about a ``.txt``.
    """
from .styled import Inline, StyledDoc, StyledPara

__all__ = [
    "TxtReadError",
    "read_txt",
]

#: Twips per leading space. Four spaces → 720, Word's default tab stop, which
#: is the number the DOCX of the same document would report for one tab.
_TWIPS_PER_SPACE = 180

#: A tab in a text file means the same displacement as the tab stop it moves
#: to. Counted as four spaces so ``\t`` and ``"    "`` — which look identical
#: in the source and were meant identically by the author — do not produce two
#: different indents.
_SPACES_PER_TAB = 4


def _looks_like_path(text: str) -> bool:
    """True when a ``str`` with no newline should be tried as a filename.

    Consulted only after the filesystem has already been asked and said no, so
    this settles the genuinely ambiguous leftover. A newline or a blank string
    is content; anything else short and pathlike is worth reporting as a
    missing file rather than silently ingesting as a one-word document, which
    is how a typo'd path would otherwise disappear.
    """
    return "\n" not in text and "\r" not in text and bool(text.strip())


def _decode(payload: bytes) -> str:
    """UTF-8, then Latin-1. See the module docstring for why, in that order."""
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        # Latin-1 maps all 256 byte values, so this cannot raise. Mojibake is
        # a better outcome than a refusal: the text is still segmentable and
        # citable, and a human reviewing the output can see what happened.
        return payload.decode("latin-1")


def _read_source(source: Any) -> tuple[str, str | None]:
    """Resolve ``source`` into (text, default source name).

    A ``Path`` always means the filesystem; ``bytes`` are always content
    (a caller holding bytes has already read them); a ``str`` is a file when it
    names one, and content otherwise.
    """
    if isinstance(source, Path):
        return _decode(_read_file(source)), source.name
    if isinstance(source, bytes):
        return _decode(source), None
    if isinstance(source, str):
        try:
            candidate = Path(source)
            is_file = candidate.is_file()
        except (OSError, ValueError):
            # An embedded NUL or an over-long path: not a filename, so it is
            # content by elimination.
            is_file = False
            candidate = None
        if is_file and candidate is not None:
            return _decode(_read_file(candidate)), candidate.name
        if _looks_like_path(source) and _plausible_filename(source):
            return _decode(_read_file(Path(source))), Path(source).name
        return source, None
    raise TxtReadError(f"cannot read {type(source).__name__} as text")


def _plausible_filename(text: str) -> bool:
    """True when a single-line string is shaped like a filename.

    Without this, ``read_txt("hello")`` would report "no such file" for what is
    plainly a one-word document. With it, only a string carrying a path
    separator or a short suffix is retried as a path — enough to catch a
    mistyped ``docs/nota.txt`` while leaving prose alone.
    """
    if "/" in text or "\\" in text:
        return True
    suffix = Path(text).suffix
    return bool(suffix) and len(suffix) <= 6 and " " not in text


def _read_file(path: Path) -> bytes:
    """Read a file as bytes; :func:`_decode` chooses the encoding."""
    if not path.exists():
        raise TxtReadError(f"no such file: {path}")
    if path.is_dir():
        raise TxtReadError(f"not a file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise TxtReadError(f"cannot read {path.name}: {exc}") from exc


def _leading_indent(line: str) -> int:
    """The line's leading whitespace as twips.

    Measured on the *first* line of a block, since that is the one whose
    displacement an author controls; continuation lines of a hard-wrapped
    paragraph carry the same indentation by convention and would only
    contribute the same number again.
    """
    spaces = 0
    for char in line:
        if char == " ":
            spaces += 1
        elif char == "\t":
            spaces += _SPACES_PER_TAB
        else:
            break
    return spaces * _TWIPS_PER_SPACE


def read_txt(source: Any, *, source_name: str | None = None) -> StyledDoc:
    """Read plain text into a :class:`StyledDoc`.

    Blank-line-separated blocks become paragraphs; lines within a block join
    with a single space. ``\\r\\n`` and a lone ``\\r`` are treated exactly as
    ``\\n``, so a DOS or classic-Mac file yields the same blocks as a Unix one.

    Args:
        source: a :class:`~pathlib.Path`, a ``str`` naming an existing file, or
            the text itself as ``str`` or ``bytes``. A ``str`` that names no
            file is treated as content unless it is shaped like a filename
            (a path separator, or a short suffix and no spaces), in which case
            the missing file is reported rather than silently ingested.
        source_name: the name recorded in ``StyledDoc.source``. Defaults to the
            file's basename when reading a file, and to ``None`` for text
            passed in directly.

    Returns:
        A ``StyledDoc`` of ``StyledPara`` blocks with dense indices
        ``0..n-1``, each with ``style=None`` and one plain ``Inline``. Empty
        or whitespace-only input yields a document with zero blocks.

    Raises:
        TxtReadError: the source is a file that is missing, is a directory, or
            cannot be opened. Never raised for the file's *content* — an
            undecodable byte sequence falls back to Latin-1 rather than
            failing, because a legacy corpus contains both encodings.
    """
    text, default_name = _read_source(source)
    name = source_name or default_name

    # One normalisation of line endings up front, so the block splitter below
    # sees a single convention rather than three.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    blocks: list[StyledPara] = []
    current: list[str] = []
    indent: int | None = None

    def flush() -> None:
        nonlocal indent
        lines, current[:] = list(current), []
        block_indent, indent = indent, None
        if not lines:
            return
        # Join first, normalise once: ``normalize_text`` collapses the joining
        # spaces along with any the lines already carried, so a hard-wrapped
        # paragraph and its unwrapped equivalent produce identical text.
        joined = normalize_text(" ".join(lines)).strip()
        if not joined:
            return
        props: dict[str, Any] = {}
        if block_indent:
            props["indent_direct"] = block_indent
            props["indent_effective"] = block_indent
        blocks.append(
            StyledPara(
                inlines=(Inline(text=joined),),
                index=len(blocks),
                **props,
            )
        )

    for line in text.split("\n"):
        if not line.strip():
            # A blank line closes the current block. Consecutive blank lines
            # close nothing further, so runs of them do not produce empty
            # paragraphs — unlike DOCX, where an empty paragraph is an object
            # the author created and Cycle 1 therefore keeps.
            flush()
            continue
        if not current:
            indent = _leading_indent(line)
        current.append(line.strip())
    flush()

    return StyledDoc(blocks=tuple(blocks), source=name)
