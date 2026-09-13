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
    # Both anchored to the opening of a line. Cycle 3: the bare `carne-leao`
    # matched any line *mentioning* the carnê-leão, and two soluções de consulta
    # about carnê-leão rendimentos (`sc_cosit_116`, `sc_cosit_14`) therefore
    # scored 0.9 here — tying with `solucao_consulta`'s own epigraph match and
    # winning only on registration order, which is precisely the coin toss
    # `test_winning_margin` exists to forbid. They went on to emit a
    # `:servico:` URN type.
    #
    # This costs the sample nothing: `CARNE_LEAO`'s first line is
    # "Sistema de Recolhimento Mensal Obrigatório (Carnê-Leão)", which the
    # first pattern already matches at 0.9 on its own. The second now catches
    # only a page that *titles* itself with the service name, which is what it
    # was always for. Same lesson as `authority_res` in m-6 — an unanchored
    # pattern claims documents that merely discuss the subject.
    epigraph_res=(
        re.compile(r"^\s*sistema\s+de\s+recolhimento\b"),
        re.compile(r"^\s*carne-leao\b"),
    ),
    # Anchored to the *opening* of a line, and to the service-page phrasing
    # ("Entregue … à Receita Federal"). Cycle 2 found the bare
    # `receita\s+federal` claiming any document that merely mentions the
    # Receita — `sc_15_20090309` and `sc_6007_20190325`, two soluções de
    # consulta, scored 0.40 here on that alone with no epigraph match, and were
    # profiled as service descriptions. That mattered once G-5 gave `servico`
    # documents a name-derived URN: a mis-profiled document would have acquired
    # a fabricated identity.
    authority_res=(
        re.compile(r"^\s*(?:entregue|preencha\s+e\s+envie|declare)\b.*receita\s+federal"),
    ),
    authority_map=(),
    field_labels=frozenset(),
    ementa_absent=True,
)
