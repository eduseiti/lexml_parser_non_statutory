"""Validation results, reported per schema.

A document is validated against one or both LexML schemas. Keeping the results
separate is what makes divergence visible: the two schemas agree across the
whole ``generico`` surface (plan §2.8), so a per-schema difference is a signal,
not noise.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaResult:
    """The outcome of validating one document against one schema."""

    schema: str
    valid: bool
    errors: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.valid


@dataclass(frozen=True)
class ValidationReport:
    """Results for every schema the document was checked against."""

    results: tuple[SchemaResult, ...]

    @property
    def ok(self) -> bool:
        """True iff every consulted schema accepted the document.

        With the default ``--schema=both`` this is the plan's "ok iff both
        pass". A narrower selection is judged only on what it consulted.

        An empty report is not ok: nothing was verified, so nothing is proven.
        """
        return bool(self.results) and all(r.valid for r in self.results)

    def __bool__(self) -> bool:
        return self.ok

    @property
    def schemas(self) -> tuple[str, ...]:
        """Names of the schemas consulted, in the order they were run."""
        return tuple(r.schema for r in self.results)

    @property
    def failed(self) -> tuple[str, ...]:
        """Names of the schemas that rejected the document."""
        return tuple(r.schema for r in self.results if not r.valid)

    def result_for(self, schema: str) -> SchemaResult:
        """The result for one schema.

        Raises:
            KeyError: if that schema was not consulted.
        """
        for result in self.results:
            if result.schema == schema:
                return result
        raise KeyError(
            f"schema {schema!r} was not consulted; "
            f"this report covers {', '.join(self.schemas) or '(none)'}"
        )

    def errors_for(self, schema: str) -> tuple[str, ...]:
        """Validation errors reported by one schema."""
        return self.result_for(schema).errors

    @property
    def all_errors(self) -> tuple[str, ...]:
        """Every error from every schema, each tagged with its schema name."""
        return tuple(
            f"[{r.schema}] {e}" for r in self.results for e in r.errors
        )

    def summary(self) -> str:
        """One human-readable line per schema."""
        if not self.results:
            return "no schema consulted"
        lines = []
        for r in self.results:
            head = f"{r.schema}: {'valid' if r.valid else 'INVALID'}"
            if r.errors:
                head += f" ({len(r.errors)} error{'s' if len(r.errors) > 1 else ''})"
                head += "".join(f"\n    {e}" for e in r.errors)
            lines.append(head)
        return "\n".join(lines)
