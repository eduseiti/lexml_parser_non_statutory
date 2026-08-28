"""The rendering-agnostic document model.

Cycle 2 delivered its metadata half: URNs and ``Metadata``. Cycle 4 adds the
content nodes and the recursive ``Section`` (:mod:`.nodes`). ``Dispositivo`` and
``DocumentModel`` arrive with the statutory route in Cycles 4b and 6.
"""

from .nodes import (
    PARA_KINDS,
    SECTION_KINDS,
    Evidence,
    ListItem,
    ListNode,
    Node,
    Para,
    Section,
    Table,
    node_from_dict,
)
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
from .document import DocumentModel, build_model

__all__ = [
    "LEXML_URN_RE",
    "METADATA_SOURCE_URI",
    "PARA_KINDS",
    "SECTION_KINDS",
    "DocumentModel",
    "Evidence",
    "ListItem",
    "ListNode",
    "Metadata",
    "Node",
    "Para",
    "ProprietaryField",
    "Section",
    "Table",
    "UrnDate",
    "UrnParts",
    "build_model",
    "build_urn",
    "extract_metadata",
    "is_valid_urn",
    "node_from_dict",
    "parse_pt_date",
    "parse_urn",
    "slugify_authority",
]
