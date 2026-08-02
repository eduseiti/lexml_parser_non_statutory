"""Document profiles: per-genre knowledge, kept as data rather than code.

A profile answers three questions about a genre of document:

1. *Is this document one of mine?* — :meth:`DocumentProfile.score`.
2. *What does its URN look like?* — ``urn_type``, ``urn_authority``.
3. *Which labelled front-matter lines are metadata rather than prose?* —
   ``field_labels``.

Ported in spirit from the reference parser's ``DocumentProfile.scala``, which
is likewise a bundle of regexes per genre. The important departure: plan §2.7
established that **genre is a prior, not a rule** — ``port_mf_454`` is a
Portaria that is not articulated. So a profile never decides routing; it only
supplies patterns and defaults. Cycle 4b decides the route on evidence.

Scoring rather than first-match: several profiles can plausibly claim a
document (``Parecer Normativo CST`` matches both ``parecer`` and, weakly, a
generic normative act), and the strongest claim should win regardless of
registration order.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..ingest import StyledDoc

__all__ = ["DocumentProfile", "fold", "head_texts"]


def fold(text: str) -> str:
    """Accent-fold and lowercase, for case/accent-insensitive matching.

    Profile regexes are written against folded text so a single pattern
    matches ``EMENTA``, ``Ementa`` and ``ementa`` — and so ``JURISPRUDÊNCIA``
    matches without the pattern having to carry the accent.
    """
    folded = unicodedata.normalize("NFKD", text)
    return folded.encode("ascii", "ignore").decode("ascii").lower()


def head_texts(doc: StyledDoc, limit: int = 30) -> list[str]:
    """The first ``limit`` non-empty paragraph texts.

    Genre is decided by the front matter; reading the whole document would let
    a quoted statute deep in the body outvote the epigraph.
    """
    out: list[str] = []
    for para in doc.paragraphs:
        if para.is_empty:
            continue
        out.append(para.text.strip())
        if len(out) >= limit:
            break
    return out


@dataclass(frozen=True)
class DocumentProfile:
    """One genre's patterns and URN defaults.

    ``score`` is deliberately a plain method over regex counts rather than
    anything learned: with 15 samples, a fitted model would memorise them.
    """

    name: str
    urn_type: str
    urn_authority: str | None = None
    urn_locality: str = "br"
    #: Patterns that identify this genre, matched against folded head text.
    epigraph_res: tuple[re.Pattern[str], ...] = ()
    #: Preamble openers naming the issuing authority ("o ministro de estado…").
    authority_res: tuple[re.Pattern[str], ...] = ()
    #: Sigla → authority slug, applied to the epigraph ("MF" → ministerio.fazenda).
    authority_map: tuple[tuple[str, str], ...] = ()
    #: The allowlist of labelled front-matter fields (spec §2.2, decision #4).
    field_labels: frozenset[str] = frozenset()
    #: True when documents of this genre routinely carry no ementa.
    ementa_absent: bool = False
    #: Floor score, so `generic` can win when nothing else matches at all.
    base_score: float = 0.0

    def score(self, doc: StyledDoc) -> float:
        """How strongly this profile claims ``doc``, in ``0.0``–``1.0``.

        An epigraph match is worth much more than a preamble match: the
        epigraph names the genre outright, while preamble openers are shared
        across genres (a Secretário issues both Atos Declaratórios and
        Portarias).
        """
        heads = [fold(t) for t in head_texts(doc)]
        if not heads:
            return self.base_score

        score = self.base_score
        # The epigraph is nearly always the first non-empty line, but
        # `parecer_93` puts a date stamp and an institutional header above it,
        # so the first few lines are all candidates.
        for text in heads[:6]:
            if any(r.search(text) for r in self.epigraph_res):
                score = max(score, 0.9)
                break
        else:
            # A later epigraph match still counts, just less: it may be a
            # quotation or a second document appended to the first.
            if any(r.search(t) for t in heads for r in self.epigraph_res):
                score = max(score, 0.5)

        if any(r.search(t) for t in heads for r in self.authority_res):
            score = max(score, min(0.95, score + 0.15) if score else 0.4)

        return min(score, 1.0)

    def matches_label(self, label: str) -> bool:
        """True when ``label`` is one this profile treats as metadata."""
        return fold(label).strip().rstrip(".") in {
            fold(x).strip().rstrip(".") for x in self.field_labels
        }
