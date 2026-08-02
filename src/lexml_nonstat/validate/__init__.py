"""Dual-schema validation against the LexML schemas, offline.

Plan invariant #1: emitted documents validate against **both** schemas.
"""

from .report import SchemaResult, ValidationReport
from .schema import (
    LEXML_NS,
    SCHEMA_NAMES,
    SCHEMA_SELECTORS,
    MissingStubError,
    OfflineResolver,
    UnknownSchemaError,
    clear_cache,
    load_schema,
    load_schemas,
    resolve_selector,
    schema_dir,
    stub_dir,
    validate,
    validate_all,
)

__all__ = [
    "LEXML_NS",
    "SCHEMA_NAMES",
    "SCHEMA_SELECTORS",
    "MissingStubError",
    "OfflineResolver",
    "SchemaResult",
    "UnknownSchemaError",
    "ValidationReport",
    "clear_cache",
    "load_schema",
    "load_schemas",
    "resolve_selector",
    "schema_dir",
    "stub_dir",
    "validate",
    "validate_all",
]
