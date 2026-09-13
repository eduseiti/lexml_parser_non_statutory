"""The ``generic`` catch-all profile.

Plan §1 and §4.4 make ``generico`` the default *route*; this is the matching
default *profile*. It claims every document weakly (``base_score`` above zero,
below any real match), so :func:`~.registry.select_profile` always returns
something and no document is ever left unprofiled.

It carries no epigraph patterns by design. Adding some would make it compete
with the specific profiles it exists to back up.
"""

from __future__ import annotations

import re

from .base import DocumentProfile

GENERIC = DocumentProfile(
    name="generic",
    urn_type="documento",
    urn_authority="federal",
    epigraph_res=(),
    authority_res=(),
    # Cycle 2 (corpus-233 plan §1.3/§2.1). 27 documents reached this profile and
    # inherited its `federal` default, so their URN named the wrong issuer — a
    # worse outcome than naming none, because nothing flags it. These are the
    # siglas the 233-document corpus actually contains, read off the epigraph
    # the documents already state ("Solução de Consulta Cosit nº 100").
    #
    # They live here rather than on a `solucao_consulta` profile because that
    # profile is **Cycle 3's** deliverable; Cycle 3 should move them onto it.
    authority_map=(
        ("COSIT", "ministerio.fazenda;secretaria.receita.federal"),
        ("DISIT", "ministerio.fazenda;secretaria.receita.federal"),
        ("SRRF", "ministerio.fazenda;secretaria.receita.federal"),
        ("RFB", "ministerio.fazenda;secretaria.receita.federal"),
        ("SRF", "ministerio.fazenda;secretaria.receita.federal"),
        ("PGFN", "procuradoria.geral.fazenda.nacional"),
        ("AGU", "advocacia.geral.uniao"),
        ("CARF", "ministerio.fazenda;conselho.administrativo.recursos.fiscais"),
        ("TSE", "tribunal.superior.eleitoral"),
        ("STJ", "superior.tribunal.justica"),
        ("STF", "supremo.tribunal.federal"),
    ),
    # Some labelled fields are genre-independent enough to be worth capturing
    # even when we could not identify the genre.
    field_labels=frozenset({"ASSUNTO", "EMENTA", "Assunto", "Ementa", "NUP"}),
    base_score=0.05,
    enacting_res=(
        re.compile(r"^\s*(?:declara|resolve|determina|estabelece)\b", re.I),
    ),
    annex_res=(
        re.compile(r"^\s*anexo\s+(?:unico|[ivxlcdm]+|[a-z]|\d+)\b", re.I),
    ),
    closing_res=(
        # "Brasília, 19 de dezembro de 2018." / "CST, em 30 de outubro de 1980"
        re.compile(
            r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w\s.\-()]{1,40},\s*(?:em\s+)?"
            r"[\d.]{1,4}\s*de\s+\w+\s+de\s+\d{4}",
            re.I,
        ),
    ),
)
