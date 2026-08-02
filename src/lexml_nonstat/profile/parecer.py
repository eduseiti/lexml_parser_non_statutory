"""The ``parecer`` profile — legal opinions, including *Pareceres Normativos*.

Covers three shapes present in the samples, deliberately in one profile
(spec §2.1 decision #5):

- ``Parecer Cosit nº 26, de 29 de junho de 2000`` — RFB opinion, ``Assunto:`` /
  ``Ementa:`` / ``Dispositivos Legais:`` fields.
- ``Parecer Normativo CST nº 38, de 31 de outubro de 1980`` — a dotted-hierarchy
  normative opinion with subject codes instead of labelled fields.
- ``PARECER n. 00093/2018/DECOR/CGU/AGU`` — AGU opinion, with ``NUP:``,
  ``INTERESSADOS:``, ``ASSUNTO:``, ``EMENTA:`` and a trailing ``Cod. Ement.``.

These are the documents plan §2.5 warns about: they *quote* statutes at length,
which is why the profile never implies articulation.
"""

from __future__ import annotations

import re

from .base import DocumentProfile

PARECER = DocumentProfile(
    name="parecer",
    urn_type="parecer",
    urn_authority=None,
    epigraph_res=(
        re.compile(r"^\s*parecer\b"),
        re.compile(r"^\s*p\s*a\s*r\s*e\s*c\s*e\s*r\b"),
    ),
    authority_res=(
        re.compile(r"^\s*o?\s*coordenador(-geral)?\s+d[oe]\s+sistema\s+de\s+tributacao"),
        re.compile(r"advocacia-geral\s+da\s+uniao"),
        re.compile(r"consultoria-geral\s+da\s+uniao"),
    ),
    authority_map=(
        ("DECOR/CGU/AGU", "advocacia.geral.uniao"),
        ("CGU/AGU", "advocacia.geral.uniao"),
        ("AGU", "advocacia.geral.uniao"),
        ("COSIT", "ministerio.fazenda;secretaria.receita.federal"),
        ("CST", "ministerio.fazenda;secretaria.receita.federal"),
    ),
    field_labels=frozenset(
        {
            "NUP",
            "INTERESSADOS",
            "INTERESSADA",
            "INTERESSADO",
            "ASSUNTO",
            "EMENTA",
            "Cod. Ement.",
            "Dispositivos Legais",
            "Nota Normas",
        }
    ),
)
