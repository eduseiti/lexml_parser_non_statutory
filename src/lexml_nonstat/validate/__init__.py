"""Dual-schema validation against the LexML schemas, offline.

Plan invariant #1: emitted documents validate against **both** schemas.
"""

from .report import SchemaResult, ValidationReport
from .schema import (
    GENERATIONS,
    LEXML_NS,
    PROPOSED,
    SCHEMA_NAMES,
    SCHEMA_SELECTORS,
    SHIPPED,
    MissingStubError,
    OfflineResolver,
    SchemaCapabilities,
    UnknownSchemaError,
    clear_cache,
    generation_dir,
    load_schema,
    load_schemas,
    probe_capabilities,
    resolve_selector,
    schema_dir,
    stub_dir,
    validate,
    validate_all,
)

__all__ = [
    "GENERATIONS",
    "LEXML_NS",
    "PROPOSED",
    "SCHEMA_NAMES",
    "SCHEMA_SELECTORS",
    "SHIPPED",
    "MissingStubError",
    "OfflineResolver",
    "SchemaCapabilities",
    "SchemaResult",
    "UnknownSchemaError",
    "ValidationReport",
    "clear_cache",
    "generation_dir",
    "load_schema",
    "load_schemas",
    "probe_capabilities",
    "resolve_selector",
    "schema_dir",
    "stub_dir",
    "validate",
    "validate_all",
]
