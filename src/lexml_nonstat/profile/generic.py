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
    authority_map=(),
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
