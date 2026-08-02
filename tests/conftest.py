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
