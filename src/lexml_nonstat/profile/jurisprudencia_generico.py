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
    # One profile, four document kinds (Cycle 2, G-6). A fixed `urn_type` made
    # `REsp_1306393` — an acórdão — claim `…:sumula:…`, which is simply the
    # wrong kind of document. The number is left alone: a case number is how
    # these are actually cited (user decision Q-6).
    urn_type_res=(
        (re.compile(r"^\s*sumula\b"), "sumula"),
        (re.compile(r"^\s*s\s*u\s*m\s*u\s*l\s*a\b"), "sumula"),
        (re.compile(r"^\s*recurso\s+extraordinario\b"), "recurso.extraordinario"),
        (re.compile(r"^\s*recurso\s+especial\b"), "recurso.especial"),
        (re.compile(r"^\s*acao\s+direta\s+de\s+inconstitucionalidade\b"), "acao.direta.inconstitucionalidade"),
        (re.compile(r"^\s*agravo\s+regimental\b"), "agravo.regimental"),
        (re.compile(r"^\s*habeas\s+corpus\b"), "habeas.corpus"),
        (re.compile(r"^\s*acordao\b"), "acordao"),
    ),
    urn_authority=None,
    epigraph_res=(
        re.compile(r"^\s*sumula\b"),
        re.compile(r"^\s*s\s*u\s*m\s*u\s*l\s*a\b"),
        re.compile(r"^\s*recurso\s+especial\b"),
        re.compile(r"^\s*agravo\s+regimental\b"),
        re.compile(r"^\s*acordao\s+n"),
        re.compile(r"^\s*habeas\s+corpus\b"),
    ),
    # **Deliberately left unanchored** — Cycle 3 tried to anchor these the way
    # Cycle 2 anchored `servico`'s (m-6) and reverted it, on evidence:
    #
    # 1. It was *unnecessary*. The ten `sc_cosit` documents that scored 0.40
    #    here did so through this branch with no epigraph match, and a solução
    #    de consulta now scores 0.9 on its own epigraph. All ten are reclaimed
    #    by `solucao_consulta` whether or not these patterns are anchored —
    #    measured both ways, 125 of 127 either way.
    # 2. It was *insufficient*. Two documents (`sc_cosit_105`, `sc_cosit_72`)
    #    open a line "O Superior Tribunal de Justiça (STJ), ao julgar…", which
    #    a line-anchored pattern still matches.
    # 3. It was *not free*. `REsp_1306393` block 8 reads "Vistos, relatados e
    #    discutidos esses autos…" and matched only mid-line. Anchoring dropped
    #    it, which moved `find_preamble`, which moved the front/body boundary
    #    from 0–12 to 0–5 and lifted the body tree's confidence 0.0 → 0.3 —
    #    movement in a *delivered sample*, caught by `test_measured_shape`.
    #
    # The lesson is m-6's, read more carefully: anchoring was right for
    # `servico` because a *fabricated identity* was at stake, and it is wrong
    # here because the same edit buys nothing and costs a sample.
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
