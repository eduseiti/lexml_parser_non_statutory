"""Ingestion: source documents → :class:`StyledDoc`.

DOCX today; HTML and plain text join in Cycle 8 against the same model.
"""

from .docx_reader import DocxReadError, StyleResolver, normalize_text, read_docx
from .styled import (
    Block,
    Inline,
    StyledCell,
    StyledDoc,
    StyledPara,
    StyledRow,
    StyledTable,
)

__all__ = [
    "Block",
    "DocxReadError",
    "Inline",
    "StyleResolver",
    "StyledCell",
    "StyledDoc",
    "StyledPara",
    "StyledRow",
    "StyledTable",
    "normalize_text",
    "read_docx",
]
