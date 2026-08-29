"""Shared fixtures.

Kept deliberately small: later cycles add their own fixture modules.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Importable without installation, so the suite runs straight from a checkout.
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

LEXML_NS = "http://www.lexml.gov.br/1.0"

#: Every document the tests build carries a Metadado, which LexML requires.
METADADO = (
    "<Metadado>"
    '<Identificacao URN="urn:lex:br:federal:parecer:2018-12-28;93"/>'
    "</Metadado>"
)


def lexml_doc(inner: str) -> str:
    """Wrap a fragment in a complete, Metadado-bearing LexML document."""
    return f'<LexML xmlns="{LEXML_NS}">{METADADO}{inner}</LexML>'


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def schema_files(repo_root: Path) -> list[Path]:
    """The vendored LexML schemas, which must never be modified."""
    return sorted((repo_root / "lexml").glob("*.xsd"))


@pytest.fixture
def minimal_generico() -> str:
    """The smallest valid non-statutory document (plan §2.1 row A)."""
    return lexml_doc(
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        "<p>Texto</p>"
        "</PartePrincipal></DocumentoGenerico>"
    )


@pytest.fixture
def nested_agrupamento() -> str:
    """Agrupamento inside Agrupamento — the core §2.1 finding, must be rejected."""
    return lexml_doc(
        '<DocumentoGenerico><PartePrincipal id="pp1">'
        '<Agrupamento id="pp1_agr1" nome="secao">'
        '<Agrupamento id="pp1_agr1_agr1" nome="subsecao"><p>Texto</p></Agrupamento>'
        "</Agrupamento>"
        "</PartePrincipal></DocumentoGenerico>"
    )


# ---------------------------------------------------------------------------
# Schema capabilities (§2.11, amendment A-R.2) — Cycle 5b
# ---------------------------------------------------------------------------
#
# Cycle 5b's nested output is valid only against `lexml-proposed/`, the
# *generated* generation carrying the maintainers' unreleased change. That
# directory can legitimately be absent from a checkout, and amendment A-R.9
# requires the suite to stay green against `lexml/` alone — so every nested
# assertion **skips with the probe's own diagnostic** rather than failing.
#
# Invariant #12: nothing here branches on a schema *version*. It branches only
# on what a probe of the schemas actually present reported.


def nested_capabilities():
    """The proposed generation's measured capabilities. Never raises."""
    from lexml_nonstat.validate.schema import PROPOSED, probe_capabilities

    return probe_capabilities(PROPOSED)


def nested_available() -> bool:
    """Whether nested `AgrupamentoHierarquico` is available to validate against."""
    return nested_capabilities().nested_agrupamento


#: Skip marker for tests that must validate nested output. The reason is the
#: probe's diagnostic, so a skipped run says *why* — a missing directory reads
#: differently from an unpatched schema, and a user should not have to read the
#: source to tell them apart.
requires_nested = pytest.mark.skipif(
    not nested_available(),
    reason=nested_capabilities().diagnostic,
)
