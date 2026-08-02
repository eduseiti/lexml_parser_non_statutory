"""The ``portaria`` profile — ministerial ordinances.

Two samples that disagree about structure, which is the whole point of plan
§2.7: ``port_mf_277`` is articulated (``Art. 1º``, ``Art. 2º``, plus an
``ANEXO ÚNICO``), while ``port_mf_454`` is item-based (``1.``, ``2.1``, ``a)``)
after a ``RESOLVE:`` enacting formula. The profile therefore supplies URN
defaults and patterns only — it takes no position on articulation, which
Cycle 4b decides from evidence.
"""

from __future__ import annotations

import re

from .base import DocumentProfile

PORTARIA = DocumentProfile(
    name="portaria",
    urn_type="portaria",
    urn_authority=None,
    epigraph_res=(
        re.compile(r"^\s*portaria\b"),
        re.compile(r"^\s*p\s*o\s*r\s*t\s*a\s*r\s*i\s*a\b"),
    ),
    authority_res=(
        re.compile(r"^\s*o\s+ministro\s+de\s+estado\s+d[ae]\s+fazenda"),
        re.compile(r"^\s*o\s+ministro\s+de\s+estado"),
    ),
    authority_map=(
        ("MF", "ministerio.fazenda"),
        ("RFB", "ministerio.fazenda;secretaria.receita.federal"),
        ("SRF", "ministerio.fazenda;secretaria.receita.federal"),
    ),
    field_labels=frozenset({"Nota Normas", "REFERÊNCIA"}),
)
