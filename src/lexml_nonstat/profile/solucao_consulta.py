"""The ``solucao_consulta`` profile — soluções de consulta and divergência.

The corpus's dominant genre by a wide margin: **127 of 233 documents (54.5%)**
— 109 ``sc_cosit``, 12 ``sci_cosit``, 4 ``sd_cosit`` and 2 bare ``sc``. Plan
§1.4 records the gap this profile closes; until Cycle 3 every one of them landed
on ``generic`` (and twelve, worse, on a profile for another genre entirely).

Four sub-genres under one profile, distinguished by ``urn_type_res`` — Cycle 2's
A-2.2 mechanism, reused rather than reinvented:

- ``Solução de Consulta Cosit nº 100, de 28 de setembro de 2020``
- ``Solução de Consulta Interna Cosit nº 10, de 5 de junho de 2014``
- ``Solução de Divergência Cosit nº 10, de 14 de agosto de 2014``
- ``Solução de Consulta Disit/SRRF03 nº 15, de 9 de março de 2009``

The epigraph is exceptionally regular — every one of the 127 states its genre,
number and date on its first non-empty paragraph — so the profile needs no
fallback guessing. One variant shape exists and is covered:
``Solução de Divergência COSIT Nº 16 DE 27/09/2012`` (``sd_cosit_16``).

**``authority_res`` is deliberately empty.** The epigraph already carries the
sigla for 113 of the 127, and an unanchored authority pattern is precisely the
bug this cycle had to repair in two other profiles: a bare "Receita Federal"
here would claim every document that mentions the Receita, exactly as
``servico``'s did (Cycle 2, m-6) and ``jurisprudencia_generico``'s bare STJ
pattern did (Cycle 3). A profile for 54% of the corpus is the last place that
mistake should be repeated.
"""

from __future__ import annotations

import re

from .base import DocumentProfile

SOLUCAO_CONSULTA = DocumentProfile(
    name="solucao_consulta",
    urn_type="solucao.consulta",
    # Longest-prefix first: "Solução de Consulta Interna" also matches the
    # plain "Solução de Consulta" pattern, and first match wins.
    urn_type_res=(
        (re.compile(r"^\s*solucao\s+de\s+consulta\s+interna\b"), "solucao.consulta.interna"),
        (re.compile(r"^\s*solucao\s+de\s+divergencia\b"), "solucao.divergencia"),
        (re.compile(r"^\s*solucao\s+de\s+consulta\b"), "solucao.consulta"),
    ),
    urn_authority=None,
    epigraph_res=(
        re.compile(r"^\s*solucao\s+de\s+consulta\b"),
        re.compile(r"^\s*solucao\s+de\s+divergencia\b"),
    ),
    # Empty on purpose — see the module docstring.
    authority_res=(),
    # Every issuing unit the 127 documents actually name on their epigraph.
    # `DISIT` and `SRRF` appear as `Disit/SRRF03`, so both are listed.
    authority_map=(
        ("COSIT", "ministerio.fazenda;secretaria.receita.federal"),
        ("DISIT", "ministerio.fazenda;secretaria.receita.federal"),
        ("SRRF", "ministerio.fazenda;secretaria.receita.federal"),
        ("RFB", "ministerio.fazenda;secretaria.receita.federal"),
        ("SRF", "ministerio.fazenda;secretaria.receita.federal"),
    ),
    field_labels=frozenset(
        {
            "ASSUNTO",
            "Assunto",
            "EMENTA",
            "Ementa",
            "DISPOSITIVOS LEGAIS",
            "Dispositivos Legais",
            "Dispositivos legais",
        }
    ),
    # The genre's skeleton, and the reason Cycle 3 needed `section_res` at all
    # (M-1). 125 of the 127 carry all three of these as standalone paragraphs,
    # in *title case* — so `is_prose_form_header`, which demands an upper-case
    # ratio of 0.85, never proposes them and no referee is ever asked. Anchored
    # end-to-end so only a paragraph that is *nothing but* the heading matches:
    # a sentence opening "Conclusão: o consulente…" is prose about a conclusion,
    # not the division itself.
    section_res=(
        re.compile(r"^relatorio$"),
        re.compile(r"^fundamentos?$"),
        re.compile(r"^conclusao$"),
    ),
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
