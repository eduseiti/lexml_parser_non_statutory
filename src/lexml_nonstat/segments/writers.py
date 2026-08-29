"""CSV and JSONL writers for segment output — plan Cycle 7.

Two formats, for two consumers. **CSV** matches §6.2's reference stylesheets
column for column, so the XSLT path and this Python path are comparable row by
row — which is what makes "XSLT and Python produce equivalent rows" a test
rather than a hope. **JSONL** is lossless: every field of every
:class:`~.model.Segment`, one object per line, reparsing to an equal record.

Determinism (plan §9.2) is a property of both: no dict ordering, no locale, no
timestamps, ``\\n`` line endings written explicitly rather than left to the
platform.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from .model import Segment

__all__ = [
    "BREADCRUMB_SEPARATOR",
    "CSV_COLUMNS",
    "csv_row",
    "to_csv",
    "to_jsonl",
]

#: The reference stylesheets' header, verbatim — plan §6.2. Portuguese because
#: that is what the community stylesheet emits and what its consumers parse.
CSV_COLUMNS: tuple[str, ...] = (
    "Tipo",
    "Nivel",
    "Rotulo",
    "Breadcrumb",
    "Texto",
    "urn",
)

#: What joins breadcrumb entries, matching §6.2's ``' | '``.
BREADCRUMB_SEPARATOR = " | "


def csv_row(segment: Segment) -> tuple[str, ...]:
    """One segment as the reference stylesheets would write it.

    ``Texto`` is :attr:`~.model.Segment.full_text` — the cumulative reading —
    because that is what §6.2's ``descendant::p`` produces and what a CSV
    consumer expects from a row. The own-text/cumulative distinction lives in
    the record; the CSV is the reference *format*, and matching it is the
    point.
    """
    breadcrumb = BREADCRUMB_SEPARATOR.join(
        entry for entry in segment.breadcrumb if entry
    )
    return (
        segment.kind,
        str(segment.level),
        segment.label or "",
        breadcrumb,
        segment.full_text,
        segment.urn,
    )


def to_csv(
    segments: Iterable[Segment], stream: Any = None, *, header: bool = True
) -> str:
    """Write ``segments`` as CSV; returns the text, and writes it if given."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    if header:
        writer.writerow(CSV_COLUMNS)
    for segment in segments:
        writer.writerow(csv_row(segment))
    text = buffer.getvalue()
    if stream is not None:
        stream.write(text)
    return text


def to_jsonl(segments: Iterable[Segment], stream: Any = None) -> str:
    """Write ``segments`` as JSON Lines — one object per line, lossless."""
    text = "".join(segment.to_json() + "\n" for segment in segments)
    if stream is not None:
        stream.write(text)
    return text
