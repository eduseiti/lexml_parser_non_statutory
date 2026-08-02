"""The ``servico`` profile — public-service descriptions.

One sample: ``Sistema de Recolhimento Mensal Obrigatório (Carnê-Leão)``. It is
the odd one out of the corpus — a taxpayer-facing web page rather than a legal
act. It has no epigraph, no ementa, no preamble, no signature and no number,
and plan §8's Cycle 3 test makes that explicit ("**no false positives**").

Its hierarchy is carried entirely by Word styles (``Heading1``/``Heading2``)
plus bulleted lists, which is why plan §4.4 routes it to ``generico`` and why
this profile sets ``ementa_absent``.
"""

from __future__ import annotations

import re

from .base import DocumentProfile

SERVICO = DocumentProfile(
    name="servico",
    urn_type="servico",
    urn_authority="ministerio.fazenda;secretaria.receita.federal",
    epigraph_res=(
        re.compile(r"^\s*sistema\s+de\s+recolhimento\b"),
        re.compile(r"carne-leao"),
    ),
    authority_res=(re.compile(r"receita\s+federal"),),
    authority_map=(),
    field_labels=frozenset(),
    ementa_absent=True,
)
