"""The ``jurisprudencia_generico`` profile — súmulas and acórdãos.

Named ``…_generico`` on purpose. Plan decision #2 is that **no
``Jurisprudencia`` emitter is built**: many documents of this genre stop at the
acórdão part and cannot satisfy ``Acordao``'s required children, so all three
samples route to ``generico`` (plan §4.4). This profile exists to get their
metadata and field labels right, not to unlock a statutory route.

Three shapes:

- ``Súmula CARF nº 42`` — administrative-court súmula, then ``ACÓRDÃOS
  PARADIGMAS``.
- ``SÚMULA N. 125`` — STJ súmula, with ``Referência:`` / ``Precedentes:`` and
  full acórdão texts appended.
- ``RECURSO ESPECIAL Nº 1.306.393 - DF (2012/0013476-0)`` — a bare acórdão with
  ``EMENTA`` / ``ACÓRDÃO`` headings.

None carries a date on its epigraph line, so all three exercise the
incomplete-metadata path of spec §2.1 decision #2.
"""

from __future__ import annotations

import re

from .base import DocumentProfile

JURISPRUDENCIA_GENERICO = DocumentProfile(
    name="jurisprudencia_generico",
    urn_type="sumula",
    urn_authority=None,
    epigraph_res=(
        re.compile(r"^\s*sumula\b"),
        re.compile(r"^\s*s\s*u\s*m\s*u\s*l\s*a\b"),
        re.compile(r"^\s*recurso\s+especial\b"),
        re.compile(r"^\s*agravo\s+regimental\b"),
        re.compile(r"^\s*acordao\s+n"),
        re.compile(r"^\s*habeas\s+corpus\b"),
    ),
    authority_res=(
        re.compile(r"superior\s+tribunal\s+de\s+justica"),
        re.compile(r"conselho\s+administrativo\s+de\s+recursos\s+fiscais"),
    ),
    authority_map=(
        ("CARF", "ministerio.fazenda;conselho.administrativo.recursos.fiscais"),
        ("STJ", "superior.tribunal.justica"),
        ("STF", "supremo.tribunal.federal"),
    ),
    # `Relator:`, `Advogados:`, `Recorrente:` are *acórdão body* structure, not
    # document metadata, and capturing them is exactly the false positive
    # spec §2.1 decision #4 rules out. Only genuinely document-level labels
    # are listed.
    field_labels=frozenset({"Referência", "Referencia", "Precedentes"}),
    ementa_absent=False,
    closing_res=(
        # "Brasília, 19 de dezembro de 2018." / "CST, em 30 de outubro de 1980"
        re.compile(
            r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w\s.\-()]{1,40},\s*(?:em\s+)?"
            r"[\d.]{1,4}\s*de\s+\w+\s+de\s+\d{4}",
            re.I,
        ),
    ),
)
