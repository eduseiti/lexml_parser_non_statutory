"""Offline compilation of the LexML schemas, and validation against them.

``lexml-base.xsd`` imports three schemas from w3.org::

    http://www.w3.org/2001/xml.xsd
    http://www.w3.org/Math/XMLSchema/mathml2/common/xlink-href.xsd
    http://www.w3.org/Math/XMLSchema/mathml2/mathml2.xsd

All three are genuinely fetched when lxml compiles a schema, so without
intervention validation needs network access — unacceptable for a test suite
that must run anywhere, and the foundation every later cycle stands on.

The investigation record (``docs/20260801_004745_…`` §11) solved this by
rewriting the ``schemaLocation`` attributes in ``lexml/*.xsd`` on disk. We do
not: that mutates the vendored schemas and destroys the upstream baseline
needed to spot schema drift. Instead an lxml ``Resolver`` maps those URLs onto
vendored stubs at parse time, leaving ``lexml/`` byte-identical to upstream.

(That §11 recipe also stubbed only ``xml.xsd``; the xlink and MathML imports
are equally load-bearing. See the Cycle 0 spec, §2.)

Schema **generations** (§2.11, amendment A-R.2)
-----------------------------------------------
Two directories carry LexML schemas: ``lexml/`` as shipped upstream, and the
generated ``lexml-proposed/`` carrying the maintainers' unreleased recursive
``AgrupamentoHierarquico``. Everything here takes a keyword-only ``generation``
defaulting to ``SHIPPED``, so no existing caller changes meaning.

What a generation *permits* is *probed, never assumed*:
:func:`probe_capabilities` compiles the generation's schemas and validates a
minimal document against them. A generation that is absent from the checkout
answers "no capability" with a diagnostic instead of raising — invariant #12
requires the suite to stay green against ``lexml/`` alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from lxml import etree

from .report import SchemaResult, ValidationReport

#: LexML target namespace, for callers building documents.
LEXML_NS = "http://www.lexml.gov.br/1.0"

#: Schema names, in the order they are run and reported.
SCHEMA_NAMES: tuple[str, ...] = ("rigido", "flexivel")

#: Accepted values of ``--schema``.
SCHEMA_SELECTORS: tuple[str, ...] = ("both", *SCHEMA_NAMES)

_SCHEMA_FILES: Mapping[str, str] = {
    "rigido": "lexml-br-rigido.xsd",
    "flexivel": "lexml09-flexivel.xsd",
}

#: The schemas as shipped upstream. The default everywhere, always.
SHIPPED = "shipped"
#: The generated generation carrying the maintainers' unreleased change.
PROPOSED = "proposed"

#: Accepted values of ``generation``.
GENERATIONS: tuple[str, ...] = (SHIPPED, PROPOSED)

#: generation -> repository directory holding its ``*.xsd``.
_GENERATION_DIRS: Mapping[str, str] = {
    SHIPPED: "lexml",
    PROPOSED: "lexml-proposed",
}

#: Remote import URL -> vendored stub filename.
STUB_MAP: Mapping[str, str] = {
    "http://www.w3.org/2001/xml.xsd": "xml.xsd",
    "http://www.w3.org/Math/XMLSchema/mathml2/common/xlink-href.xsd": "xlink-href.xsd",
    "http://www.w3.org/Math/XMLSchema/mathml2/mathml2.xsd": "mathml2.xsd",
}

_REPO_ROOT = Path(__file__).resolve().parents[3]


class UnknownSchemaError(ValueError):
    """Raised for a schema name or selector that does not exist."""


class MissingStubError(RuntimeError):
    """Raised when a vendored stub for a remote import is absent.

    Deliberately fatal. If a stub goes missing, libxml2 silently falls back to
    fetching the URL over the network, so on a connected machine everything
    keeps working and the offline guarantee rots undetected until someone runs
    the suite without internet. Failing here keeps that breakage visible.
    """


def schema_dir() -> Path:
    """Directory holding the vendored LexML schemas. Read-only, always."""
    return generation_dir(SHIPPED)


def generation_dir(generation: str = SHIPPED) -> Path:
    """Directory holding one generation's schemas.

    The directory may not exist: ``lexml-proposed/`` is generated, and a
    checkout that has not run ``scripts/build_proposed_schemas.py`` will not
    have it. Existence is the caller's question — :func:`probe_capabilities`
    answers it without raising.

    Raises:
        UnknownSchemaError: if ``generation`` is not a known generation.
    """
    if generation not in _GENERATION_DIRS:
        raise UnknownSchemaError(
            f"unknown schema generation {generation!r}; "
            f"expected one of {', '.join(GENERATIONS)}"
        )
    return _REPO_ROOT / _GENERATION_DIRS[generation]


def stub_dir() -> Path:
    """Directory holding our offline stubs for the remote w3.org imports."""
    return Path(__file__).resolve().parent / "stubs"


class OfflineResolver(etree.Resolver):
    """Resolves the three remote w3.org imports to vendored stubs.

    Anything else is passed through to lxml's default handling, so local
    relative imports (``lexml-base.xsd``) resolve normally.
    """

    def __init__(self, stubs: Mapping[str, str] | None = None) -> None:
        self._stubs = dict(STUB_MAP if stubs is None else stubs)
        self._directory = stub_dir()
        #: URLs actually resolved through this resolver — inspected by tests.
        self.resolved: list[str] = []

    def resolve(self, system_url, public_id, context):  # noqa: D102 - lxml API
        stub = self._stubs.get(system_url)
        if stub is None:
            return None

        path = self._directory / stub
        if not path.exists():
            # Never fall through to lxml's default handling here: it would
            # fetch the URL and mask the missing stub on any connected machine.
            raise MissingStubError(
                f"vendored stub {stub!r} for {system_url} is missing from "
                f"{self._directory}. Restore it, or the schemas can only be "
                "compiled with network access."
            )

        self.resolved.append(system_url)
        return self.resolve_filename(str(path), context)


def _parser() -> etree.XMLParser:
    """A parser that resolves the remote imports locally and never fetches.

    ``no_network=True`` is a belt-and-braces guard: with the resolver in place
    nothing should reach the network, and if a future schema adds an import we
    have not stubbed, we want a hard failure rather than a silent download.
    """
    parser = etree.XMLParser(no_network=True)
    parser.resolvers.add(OfflineResolver())
    return parser


#: Compiled schemas, keyed by ``(generation, name)``. The generation is part of
#: the key because the two generations answer differently by design — caching
#: on the name alone would let the first one asked poison the other.
_cache: dict[tuple[str, str], etree.XMLSchema] = {}


def load_schema(
    name: str, *, generation: str = SHIPPED, use_cache: bool = True
) -> etree.XMLSchema:
    """Compile one LexML schema, offline.

    Args:
        name: ``"rigido"`` or ``"flexivel"``.
        generation: ``"shipped"`` (default) or ``"proposed"`` (§2.11).
        use_cache: reuse a previously compiled schema. Compilation is by far
            the expensive step, and later cycles validate repeatedly.

    Raises:
        UnknownSchemaError: if ``name`` or ``generation`` is not known.
        OSError: if the generation's directory or file is absent.
    """
    if name not in _SCHEMA_FILES:
        raise UnknownSchemaError(
            f"unknown schema {name!r}; expected one of {', '.join(SCHEMA_NAMES)}"
        )
    key = (generation, name)
    if use_cache and key in _cache:
        return _cache[key]

    path = generation_dir(generation) / _SCHEMA_FILES[name]
    compiled = etree.XMLSchema(etree.parse(str(path), _parser()))
    if use_cache:
        _cache[key] = compiled
    return compiled


def clear_cache() -> None:
    """Drop compiled schemas. Used by tests that must compile from cold."""
    _cache.clear()


def resolve_selector(selector: str = "both") -> tuple[str, ...]:
    """Expand a ``--schema`` value into schema names.

    Raises:
        UnknownSchemaError: on any other value.
    """
    if selector == "both":
        return SCHEMA_NAMES
    if selector in _SCHEMA_FILES:
        return (selector,)
    raise UnknownSchemaError(
        f"unknown schema selector {selector!r}; "
        f"expected one of {', '.join(SCHEMA_SELECTORS)}"
    )


def load_schemas(
    selector: str = "both", *, generation: str = SHIPPED
) -> dict[str, etree.XMLSchema]:
    """Compile the schemas named by a ``--schema`` selector."""
    return {
        name: load_schema(name, generation=generation)
        for name in resolve_selector(selector)
    }


def _as_element(doc) -> etree._Element | etree._ElementTree:
    """Coerce the accepted input forms to something lxml can validate.

    Accepts an element, a tree, raw ``bytes``/``str`` XML, or a ``Path``.
    """
    if isinstance(doc, (etree._Element, etree._ElementTree)):
        return doc
    if isinstance(doc, Path):
        return etree.parse(str(doc))
    if isinstance(doc, bytes):
        return etree.fromstring(doc)
    if isinstance(doc, str):
        # A short string naming an existing file is a path; otherwise it is XML.
        # Guard the length so we never stat() a whole document.
        if len(doc) < 4096 and not doc.lstrip().startswith("<"):
            candidate = Path(doc)
            if candidate.exists():
                return etree.parse(str(candidate))
        return etree.fromstring(doc.encode("utf-8"))
    raise TypeError(
        f"cannot validate {type(doc).__name__}; expected an lxml element or "
        "tree, XML bytes/str, or a Path"
    )


def _format_errors(schema: etree.XMLSchema) -> tuple[str, ...]:
    return tuple(
        f"line {e.line}: {e.message}" if e.line and e.line > 0 else e.message
        for e in schema.error_log
    )


def validate(
    doc, selector: str = "both", *, generation: str = SHIPPED
) -> ValidationReport:
    """Validate a document against the selected schemas.

    A malformed document yields a report carrying the parse error against every
    selected schema, rather than raising: callers get a uniform failure channel.

    Args:
        doc: element, tree, XML ``bytes``/``str``, or ``Path`` to a file.
        selector: ``both`` (default), ``rigido``, or ``flexivel``.
        generation: which schema generation to validate against (§2.11).
    """
    names = resolve_selector(selector)

    try:
        element = _as_element(doc)
    except etree.XMLSyntaxError as exc:
        message = f"not well-formed XML: {exc}"
        return ValidationReport(
            tuple(SchemaResult(n, False, (message,)) for n in names)
        )

    results = []
    for name in names:
        schema = load_schema(name, generation=generation)
        valid = bool(schema.validate(element))
        results.append(
            SchemaResult(name, valid, () if valid else _format_errors(schema))
        )
    return ValidationReport(tuple(results))


def validate_all(
    docs: Iterable, selector: str = "both", *, generation: str = SHIPPED
) -> list[ValidationReport]:
    """Validate several documents against the same selection."""
    return [validate(d, selector, generation=generation) for d in docs]


# ---------------------------------------------------------------------------
# Capability probe (§2.11, amendment A-R.2)
# ---------------------------------------------------------------------------

#: The document the nested-`Agrupamento` capability is probed with.
#:
#: Not `AgrupamentoHierarquico` wrapping a bare `<p>`: §5.4 constraint 3 says
#: prose needs an `Agrupamento` wrapper, and the maintainers' change adds
#: `Agrupamento` and `Bloco` to the choice — not `p`. Probing the wrong shape
#: would report "no capability" against the very generation that has it, which
#: is the failure mode a probe exists to prevent.
_NESTED_PROBE_DOC = (
    f'<LexML xmlns="{LEXML_NS}">'
    "<Metadado>"
    '<Identificacao URN="urn:lex:br:federal:parecer:2018-12-28;93"/>'
    "</Metadado>"
    '<DocumentoGenerico><PartePrincipal id="pp1">'
    '<AgrupamentoHierarquico id="agh1" nome="tema">'
    '<Agrupamento id="agh1_agr1" nome="prosa"><p>Texto</p></Agrupamento>'
    "</AgrupamentoHierarquico>"
    "</PartePrincipal></DocumentoGenerico>"
    "</LexML>"
)


@dataclass(frozen=True)
class SchemaCapabilities:
    """What one schema generation actually permits, as measured.

    ``diagnostic`` is written to be pasted into a blocker or a log line: it
    names the generation, the directory and the reason, so a user told
    "nested rendering unavailable" can tell a missing directory from an
    unpatched schema without reading the source.
    """

    generation: str
    available: bool
    nested_agrupamento: bool
    diagnostic: str

    def to_dict(self) -> dict[str, object]:
        return {
            "generation": self.generation,
            "available": self.available,
            "nested_agrupamento": self.nested_agrupamento,
            "diagnostic": self.diagnostic,
        }


def probe_capabilities(generation: str = SHIPPED) -> SchemaCapabilities:
    """Measure what ``generation`` permits. Never raises, never assumes.

    Compiles both schemas of the generation and validates
    :data:`_NESTED_PROBE_DOC` against them. The capability is granted only when
    **both** agree it is valid — §2.8 says the two schemas do not differ on the
    `generico` surface, so a disagreement is a finding, not a capability, and
    the diagnostic says so rather than picking a winner.

    A generation whose directory is absent answers ``available=False``. That is
    the whole of invariant #12's mechanism: no caller may branch on a schema
    version, only on what a probe of the schemas actually present reported.
    """
    try:
        directory = generation_dir(generation)
    except UnknownSchemaError as exc:
        return SchemaCapabilities(generation, False, False, str(exc))

    if not directory.is_dir():
        return SchemaCapabilities(
            generation,
            False,
            False,
            f"schema generation {generation!r} unavailable: {directory} does not "
            "exist (run scripts/build_proposed_schemas.py)",
        )

    element = etree.fromstring(_NESTED_PROBE_DOC.encode("utf-8"))
    results: dict[str, bool] = {}
    for name in SCHEMA_NAMES:
        try:
            schema = load_schema(name, generation=generation)
        except (OSError, etree.XMLSchemaParseError, etree.XMLSyntaxError) as exc:
            return SchemaCapabilities(
                generation,
                False,
                False,
                f"schema generation {generation!r} unusable: {name} did not "
                f"compile from {directory}: {exc}",
            )
        results[name] = bool(schema.validate(element))

    agreed = set(results.values())
    if len(agreed) != 1:
        disagreement = ", ".join(f"{n}={results[n]}" for n in SCHEMA_NAMES)
        return SchemaCapabilities(
            generation,
            True,
            False,
            f"schema generation {generation!r} is inconsistent on nested "
            f"Agrupamento ({disagreement}); §2.8 expects the two schemas to "
            "agree on the generico surface",
        )

    nested = agreed.pop()
    if nested:
        diagnostic = (
            f"schema generation {generation!r} ({directory.name}/) accepts "
            "AgrupamentoHierarquico carrying an Agrupamento: nested rendering "
            "is available"
        )
    else:
        diagnostic = (
            f"schema generation {generation!r} ({directory.name}/) rejects "
            "AgrupamentoHierarquico carrying an Agrupamento: the maintainers' "
            "recursive change is not present, so nested rendering is "
            "unavailable (plan §2.10, §11.3)"
        )
    return SchemaCapabilities(generation, True, nested, diagnostic)
