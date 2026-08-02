"""The ``ato_declaratorio`` profile — declaratory acts, normative or not.

Six samples: ``ad_srf_*``, ``ad_pgfn_*``, ``adn_cosit_*``, ``adn_cst_*``. Their
shape is consistent — epigraph, ementa in quotes, a preamble naming the
issuing officer, then ``DECLARA`` followed by incisos (``I -``, ``II -``) or
dotted items. Plan §2.7 records them as never articulated.

``adn_cst_10``'s ementa line is the literal ``O ato não possui ementa. Ver
íntegra`` — a portal artifact rather than an ementa, which is why
``ementa_absent`` is set: Cycle 3 must not take it at face value.
"""

from __future__ import annotations

import re

from .base import DocumentProfile

ATO_DECLARATORIO = DocumentProfile(
    name="ato_declaratorio",
    urn_type="ato.declaratorio",
    urn_authority=None,
    epigraph_res=(
        re.compile(r"^\s*ato\s+declaratorio\b"),
        re.compile(r"^\s*a\s*t\s*o\s+d\s*e\s*c\s*l\s*a\s*r\s*a\s*t\s*o\s*r\s*i\s*o\b"),
    ),
    authority_res=(
        re.compile(r"^\s*[oa]\s+secretari[oa]\s+d[ae]\s+receita\s+federal"),
        re.compile(r"^\s*[oa]\s+procurador(a)?-geral\s+d[ae]\s+fazenda\s+nacional"),
        re.compile(r"^\s*[oa]\s+coordenador(-geral)?\s+d[oe]\s+sistema\s+de\s+tributacao"),
    ),
    authority_map=(
        ("PGFN", "procuradoria.geral.fazenda.nacional"),
        ("SRF", "ministerio.fazenda;secretaria.receita.federal"),
        ("COSIT", "ministerio.fazenda;secretaria.receita.federal"),
        ("CST", "ministerio.fazenda;secretaria.receita.federal"),
    ),
    field_labels=frozenset({"JURISPRUDÊNCIA", "JURISPRUDENCIA", "REFERÊNCIA", "Nota Normas"}),
    ementa_absent=False,
)
