"""The schemas compile with no network access, and without being modified.

The offline guarantee is the foundation of every later cycle: if validation
needs w3.org, the suite is hostage to a third party.
`test_every_remote_import_is_served_from_a_stub` is the test that matters most
here — it catches a remote import we have failed to stub, which is exactly the
defect in the investigation record's §11 recipe (it stubbed one import of
three).
"""

from __future__ import annotations

import hashlib

import pytest
from lxml import etree

from lexml_nonstat.validate import (
    SCHEMA_NAMES,
    MissingStubError,
    OfflineResolver,
    UnknownSchemaError,
    clear_cache,
    load_schema,
    schema_dir,
    stub_dir,
)
from lexml_nonstat.validate.schema import STUB_MAP, _SCHEMA_FILES


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_both_schemas_compile(name):
    """Both LexML schemas compile to usable validators."""
    assert isinstance(load_schema(name), etree.XMLSchema)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_every_remote_import_is_served_from_a_stub(name):
    """Compiling resolves all three w3.org imports from vendored files.

    This is the offline guarantee, checked the only way that actually works.

    Two lower-level controls were tried and rejected: banning Python's
    `socket` does nothing (libxml2 does its HTTP in C, below Python), and
    `XMLParser(no_network=True)` does not reach the loader `XMLSchema()` uses
    for imports. Both compiled happily with a stub deleted. What *is* reliable
    is observing which URLs our own resolver served: if a remote import were
    unstubbed, it would not appear here.
    """
    clear_cache()
    resolver = OfflineResolver()

    parser = etree.XMLParser(no_network=True)
    parser.resolvers.add(resolver)

    path = schema_dir() / _SCHEMA_FILES[name]
    schema = etree.XMLSchema(etree.parse(str(path), parser))

    assert isinstance(schema, etree.XMLSchema)
    assert set(resolver.resolved) == set(STUB_MAP), (
        f"{name} resolved {sorted(resolver.resolved)} locally, but the schemas "
        f"import {sorted(STUB_MAP)}. An import not served from a stub is being "
        "fetched over the network."
    )


def test_missing_stub_fails_loudly():
    """A deleted stub raises, instead of silently falling back to the network.

    Without this guard the offline guarantee rots invisibly: libxml2 responds
    to an unreadable local file by fetching the URL, so on a connected machine
    everything keeps working and the breakage only surfaces for whoever runs
    the suite offline. Verified: with a stub removed, compilation succeeded via
    a silent download.
    """
    resolver = OfflineResolver({"http://example.invalid/x.xsd": "absent-stub.xsd"})

    with pytest.raises(MissingStubError) as exc:
        resolver.resolve("http://example.invalid/x.xsd", None, None)

    message = str(exc.value)
    assert "absent-stub.xsd" in message
    assert "network" in message, "the error should explain the consequence"


def test_resolver_declines_urls_it_does_not_stub():
    """Local and unknown references fall through to lxml's normal handling."""
    resolver = OfflineResolver()

    assert resolver.resolve("lexml-base.xsd", None, None) is None
    assert resolver.resolve("http://example.org/other.xsd", None, None) is None
    assert resolver.resolved == []


def test_vendored_schemas_are_never_modified(schema_files):
    """`lexml/*.xsd` stays byte-identical to upstream.

    We resolve remote imports through a resolver precisely so the vendored
    schemas need no rewriting. Keeping them pristine is what makes a future
    `git diff` on `lexml/` show LexML's changes and nothing of ours.
    """
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in schema_files}

    clear_cache()
    for name in SCHEMA_NAMES:
        load_schema(name)

    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in schema_files}
    assert before == after, "compiling the schemas modified lexml/ on disk"


def test_unknown_schema_name_raises():
    with pytest.raises(UnknownSchemaError) as exc:
        load_schema("bogus")

    message = str(exc.value)
    assert "bogus" in message
    for name in SCHEMA_NAMES:
        assert name in message, "the error should name the valid schemas"


def test_compilation_is_cached():
    """Compiling is the expensive step; later cycles validate repeatedly."""
    clear_cache()
    first = load_schema("rigido")
    assert load_schema("rigido") is first


def test_cache_can_be_bypassed():
    first = load_schema("rigido")
    assert load_schema("rigido", use_cache=False) is not first


@pytest.mark.parametrize("url,filename", sorted(STUB_MAP.items()))
def test_every_stub_exists_and_is_wellformed(url, filename):
    """Each stubbed import has a parseable file declaring a target namespace.

    The namespace is checked against the actual import in
    `test_stub_namespaces_match_the_schema_imports`; here we only establish
    that the file exists and is a well-formed schema.
    """
    path = stub_dir() / filename
    assert path.exists(), f"missing stub for {url}"

    root = etree.parse(str(path)).getroot()
    assert root.tag == "{http://www.w3.org/2001/XMLSchema}schema", (
        f"{filename} is not an XML Schema document"
    )
    assert root.get("targetNamespace"), f"{filename} declares no targetNamespace"


def test_stub_namespaces_match_the_schema_imports():
    """Each stub's targetNamespace equals the namespace of the import it serves."""
    base = etree.parse(str(schema_dir() / "lexml-base.xsd"))
    xsd = "{http://www.w3.org/2001/XMLSchema}import"

    imports = {
        node.get("schemaLocation"): node.get("namespace")
        for node in base.iter(xsd)
    }

    for url, filename in STUB_MAP.items():
        if url not in imports:
            continue  # stubbed for another schema in the set
        expected_ns = imports[url]
        stub_ns = etree.parse(str(stub_dir() / filename)).getroot().get("targetNamespace")
        assert stub_ns == expected_ns, (
            f"{filename} targets {stub_ns!r} but {url} imports {expected_ns!r}"
        )


def test_all_remote_imports_are_stubbed():
    """No schema in `lexml/` imports a remote URL we have not stubbed.

    The direct regression test for the §11 defect: it enumerates the imports
    rather than trusting a list written by hand.
    """
    xsd = "{http://www.w3.org/2001/XMLSchema}import"
    unstubbed = set()

    for path in schema_dir().glob("*.xsd"):
        for node in etree.parse(str(path)).iter(xsd):
            location = node.get("schemaLocation") or ""
            if location.startswith(("http://", "https://")) and location not in STUB_MAP:
                unstubbed.add(location)

    assert not unstubbed, f"remote imports without a vendored stub: {sorted(unstubbed)}"
