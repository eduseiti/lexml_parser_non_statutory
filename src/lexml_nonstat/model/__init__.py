"""The rendering-agnostic document model.

Cycle 2 delivers its metadata half: URNs and ``Metadata``. The structural half
(``Section``, ``Dispositivo``, ``DocumentModel`` — plan §3.1) arrives with the
hierarchy cycles.
"""

from .metadata import (
    METADATA_SOURCE_URI,
    Metadata,
    ProprietaryField,
    extract_metadata,
    parse_pt_date,
)
from .urn import (
    LEXML_URN_RE,
    UrnDate,
    UrnParts,
    build_urn,
    is_valid_urn,
    parse_urn,
    slugify_authority,
)

__all__ = [
    "LEXML_URN_RE",
    "METADATA_SOURCE_URI",
    "Metadata",
    "ProprietaryField",
    "UrnDate",
    "UrnParts",
    "build_urn",
    "extract_metadata",
    "is_valid_urn",
    "parse_pt_date",
    "parse_urn",
    "slugify_authority",
]
