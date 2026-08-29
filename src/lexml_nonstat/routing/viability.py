"""The Statutory Viability Analyzer — §4's verdict, and its refusals.

§4.4 measures what this module is actually for: **14 of 15 samples route to
`generico`**, so "statutory detection's main job is refusing false positives,
not finding statutes". Getting `port_mf_277` right is one document; getting
`parecer_93` wrong publishes the Constitution's `Art. 40` as an article of a
legal opinion.

The route turns on four gates, all of which must hold (§4.2):

    articles_own >= 1 · the series is monotonic · coverage >= 0.6 ·
    no vetoing blocker

and on nothing else. In particular it does **not** turn on the genre prior,
which only moves the confidence, and it does not turn on the hierarchy tree's
shape: Cycle 4 found that `parecer_93` keeps three real chapters, so `flat` is
not a proxy for "unstructured" and routing reads the article census instead.

Blockers are the audit trail. A `generico` verdict that says merely "not
statutory" is unreviewable across 300 documents; one that says
`all_articles_quoted: 25 of 25 article paragraphs convicted by the quotation
guard` can be checked by a person in one line. Two classes exist, because
A-R.7 needs the distinction: a **vetoing** blocker refuses the statutory route,
while `nested_unavailable` records that a requested *rendering* is unavailable
and deliberately leaves the route alone — routing is about what the document
*is*, not how it is written out.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from ..hierarchy import HierarchyDoc, QuotationAnalysis, analyse_quotation, infer_hierarchy
from ..ingest import StyledDoc, StyledPara, StyledTable
from ..model import Metadata, extract_metadata
from ..profile import DocumentProfile, select_profile
from ..referee.adjudicate import adjudicate
from ..referee.protocol import FLAG_THRESHOLD
from ..segment import Segmentation, segment_document
from ..telemetry.decisions import DecisionLog
from ..validate.schema import SHIPPED, probe_capabilities
from .coverage import (
    COVERAGE_MIN,
    MIN_OWN_ARTICLES,
    ArticleCensus,
    articulation_coverage,
    census,
    quotation_confidence,
)
from .genre import GenrePrior, genre_prior

__all__ = [
    "BLOCKER_ALL_ARTICLES_QUOTED",
    "BLOCKER_BACK_RESIDUE",
    "BLOCKER_CODES",
    "BLOCKER_LOW_COVERAGE",
    "BLOCKER_NESTED_UNAVAILABLE",
    "BLOCKER_NON_MONOTONIC",
    "BLOCKER_NO_ARTICLES",
    "BLOCKER_STATUTORY_INVALID",
    "BLOCKER_STATUTORY_LOSSY",
    "BLOCKER_TOP_LEVEL_TABLE",
    "EMITTERS",
    "ROUTES",
    "Blocker",
    "StatutoryViability",
    "assess_viability",
]

#: The routes §4 defines. `Jurisprudencia` is deliberately absent (decision #2).
ROUTES: tuple[str, ...] = ("norma", "generico")

#: The emitters a caller may ask for (§5). `generico` and `generico-aninhado`
#: are two renderings of the **same** route (A-R.7).
EMITTERS: tuple[str, ...] = ("generico", "generico-aninhado", "norma")

BLOCKER_NO_ARTICLES = "no_articles"
BLOCKER_ALL_ARTICLES_QUOTED = "all_articles_quoted"
BLOCKER_NON_MONOTONIC = "non_monotonic_series"
BLOCKER_LOW_COVERAGE = "low_coverage"
BLOCKER_TOP_LEVEL_TABLE = "top_level_table"
BLOCKER_NESTED_UNAVAILABLE = "nested_unavailable"
#: Cycle 6's three, raised by the emitter rather than by the analyzer: §4.2's
#: validate-then-fallback is a *rendering* verdict, and it is what makes
#: "prefer statutory when possible" safe by construction rather than by
#: trusting this module's classification.
BLOCKER_STATUTORY_INVALID = "statutory_invalid"
BLOCKER_STATUTORY_LOSSY = "statutory_lossy"
BLOCKER_BACK_RESIDUE = "back_matter_residue"

#: Every code this module can emit. A test asserts no verdict carries anything
#: outside it — a blocker nobody can name is a blocker nobody will fix.
BLOCKER_CODES: tuple[str, ...] = (
    BLOCKER_NO_ARTICLES,
    BLOCKER_ALL_ARTICLES_QUOTED,
    BLOCKER_NON_MONOTONIC,
    BLOCKER_LOW_COVERAGE,
    BLOCKER_TOP_LEVEL_TABLE,
    BLOCKER_NESTED_UNAVAILABLE,
    BLOCKER_STATUTORY_INVALID,
    BLOCKER_STATUTORY_LOSSY,
    BLOCKER_BACK_RESIDUE,
)


@dataclass(frozen=True)
class Blocker:
    """One reason the statutory route was refused, or a rendering unavailable.

    ``vetoes`` is what separates the two. §4.1 types blockers as plain strings,
    but a string cannot carry the A-R.7 distinction, and collapsing it would
    make a missing schema capability silently change a document's route. Spec
    decision D-1.
    """

    code: str
    detail: str
    vetoes: bool = True

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "detail": self.detail, "vetoes": self.vetoes}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Blocker":
        return cls(str(data["code"]), str(data["detail"]), bool(data.get("vetoes", True)))


@dataclass(frozen=True)
class StatutoryViability:
    """§4.1's verdict object, as delivered."""

    route: Literal["norma", "generico"] = "generico"
    confidence: float = 0.0
    articles_found: int = 0
    articles_quoted: int = 0
    numbering_monotonic: bool = False
    coverage: float = 0.0
    has_anexos: bool = False
    blockers: tuple[Blocker, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    referee_consulted: bool = False
    referee_overrode: bool = False
    source: str | None = None
    profile: str | None = None

    @property
    def articles_own(self) -> int:
        """The number the route turns on (spec decision D-2)."""
        return self.articles_found - self.articles_quoted

    @property
    def is_statutory(self) -> bool:
        return self.route == "norma"

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(b.code for b in self.blockers)

    def has_blocker(self, code: str) -> bool:
        return code in self.blocker_codes

    def blocker(self, code: str) -> Blocker | None:
        for b in self.blockers:
            if b.code == code:
                return b
        return None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.source is not None:
            data["source"] = self.source
        if self.profile is not None:
            data["profile"] = self.profile
        data.update(
            {
                "route": self.route,
                "confidence": round(self.confidence, 4),
                "articles_found": self.articles_found,
                "articles_quoted": self.articles_quoted,
                "articles_own": self.articles_own,
                "numbering_monotonic": self.numbering_monotonic,
                "coverage": round(self.coverage, 4),
                "has_anexos": self.has_anexos,
                "blockers": [b.to_dict() for b in self.blockers],
                "referee_consulted": self.referee_consulted,
                "referee_overrode": self.referee_overrode,
                "evidence": self.evidence,
            }
        )
        return data

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StatutoryViability":
        return cls(
            route=data.get("route", "generico"),
            confidence=float(data.get("confidence", 0.0)),
            articles_found=int(data.get("articles_found", 0)),
            articles_quoted=int(data.get("articles_quoted", 0)),
            numbering_monotonic=bool(data.get("numbering_monotonic", False)),
            coverage=float(data.get("coverage", 0.0)),
            has_anexos=bool(data.get("has_anexos", False)),
            blockers=tuple(Blocker.from_dict(b) for b in data.get("blockers", ())),
            evidence=dict(data.get("evidence", {})),
            referee_consulted=bool(data.get("referee_consulted", False)),
            referee_overrode=bool(data.get("referee_overrode", False)),
            source=data.get("source"),
            profile=data.get("profile"),
        )

    @classmethod
    def from_json(cls, text: str) -> "StatutoryViability":
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

#: Contributions to `p_norma`, applied in this order and each recorded in the
#: evidence. Kept as named constants rather than inline numbers because
#: `--decisions-report` exists to tell us which of them is wrong at 300
#: documents, and a number with no name cannot be reported on.
W_HAS_OWN_ARTICLE = 0.25
W_SECOND_OWN_ARTICLE = 0.10
W_MONOTONIC = 0.15
W_NOT_MONOTONIC = -0.20
W_COVERAGE = 0.20
W_ALL_QUOTED = -0.35
W_PER_VETO = -0.05


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _p_norma(
    census_: ArticleCensus,
    coverage: float,
    prior: GenrePrior,
    vetoes: int,
) -> tuple[float, list[tuple[str, float]]]:
    """Fuse the evidence into a probability, keeping every step named."""
    contributions: list[tuple[str, float]] = [("genre_prior", prior.p_norma)]
    p = prior.p_norma

    if census_.n_own >= 1:
        p += W_HAS_OWN_ARTICLE
        contributions.append(("own_article", W_HAS_OWN_ARTICLE))
    if census_.n_own >= 2:
        p += W_SECOND_OWN_ARTICLE
        contributions.append(("second_own_article", W_SECOND_OWN_ARTICLE))

    if census_.found:
        delta = W_MONOTONIC if census_.monotonic else W_NOT_MONOTONIC
        p += delta
        contributions.append(("monotonic" if census_.monotonic else "not_monotonic", delta))

    if census_.all_quoted:
        p += W_ALL_QUOTED
        contributions.append(("all_articles_quoted", W_ALL_QUOTED))

    # Coverage is centred on the gate, so a document exactly at the gate is
    # neutral and one far above or below it moves. It contributes *only* when
    # an articulation exists to measure: a document with no own article has a
    # coverage of zero because there is nothing to cover, and charging it for
    # that would be counting `no_articles` twice — which saturated every
    # `generico` verdict at exactly 1.00 and made the number useless.
    if census_.own:
        delta = round(W_COVERAGE * (coverage - COVERAGE_MIN) / (1 - COVERAGE_MIN), 4)
        p += delta
        contributions.append(("coverage", delta))

    if vetoes:
        delta = round(W_PER_VETO * vetoes, 4)
        p += delta
        contributions.append(("blockers", delta))

    return _clamp(round(p, 4)), contributions


# ---------------------------------------------------------------------------
# The analyzer
# ---------------------------------------------------------------------------


def _body_blocks(doc: StyledDoc, segmentation: Segmentation) -> list:
    if segmentation.body is None:
        return []
    blocks = {b.index: b for b in doc.blocks}
    return [blocks[i] for i in segmentation.body.indices if i in blocks]


def _adjudicate_articles(
    paras: Sequence,
    analysis: QuotationAnalysis,
    census_: ArticleCensus,
    *,
    doc_name: str,
    referee,
    log: DecisionLog | None,
    logger: logging.Logger | None,
) -> tuple[ArticleCensus, bool, bool]:
    """Put every low-confidence quotation verdict to the referee.

    Returns the census as adjudicated, plus whether a referee was consulted at
    all and whether it changed anything. When nothing is flagged — the common
    case, and every case in the corpus except four paragraphs — no referee is
    touched and the census comes back unchanged, which is what keeps invariant
    #4 true under a warm cache.
    """
    by_index = {p.index: p for p in paras}
    order = [p.index for p in paras]
    previous: dict[int, str] = {}
    last = ""
    for para in paras:
        previous[para.index] = last
        text = (getattr(para, "text", "") or "").strip()
        if text:
            last = text

    consulted = overrode = False
    quoted = set(census_.quoted)

    for index in census_.found:
        para = by_index[index]
        confidence, reason = quotation_confidence(para, analysis)
        rule_verdict = "quoted" if index in quoted else "own"
        final, record = adjudicate(
            kind="own_articulation",
            doc=doc_name,
            locator=f"p#{index}",
            rule_verdict=rule_verdict,
            rule_confidence=confidence,
            excerpt=getattr(para, "text", "") or "",
            ctx=previous.get(index, ""),
            reason=reason,
            referee=referee if confidence < FLAG_THRESHOLD else None,
            log=log,
            logger=logger,
        )
        consulted = consulted or record.referee_consulted
        overrode = overrode or record.overridden
        if final == "quoted":
            quoted.add(index)
        else:
            quoted.discard(index)

    if not overrode:
        return census_, consulted, overrode

    return (
        ArticleCensus(
            found=census_.found,
            quoted=tuple(i for i in order if i in quoted and i in census_.found),
            own=tuple(i for i in order if i not in quoted and i in census_.found),
            values=census_.values,
            monotonic=census_.monotonic,
        ),
        consulted,
        overrode,
    )


def assess_viability(
    doc: StyledDoc,
    *,
    segmentation: Segmentation | None = None,
    profile: DocumentProfile | None = None,
    metadata: Metadata | None = None,
    hierarchy: HierarchyDoc | None = None,
    referee=None,
    log: DecisionLog | None = None,
    logger: logging.Logger | None = None,
    emitter: str = "generico",
    generation: str = SHIPPED,
) -> StatutoryViability:
    """Decide whether ``doc`` can be published as an articulated `Norma`.

    Never raises. A document that cannot be assessed routes to `generico` with
    a blocker saying why — §4's whole design is that the statutory route is the
    exception that must earn itself, and the open route is always available.

    Args:
        emitter: the rendering the caller intends. Only affects blockers
            (A-R.7); the route is identical for every emitter.
        generation: the schema generation to probe for capabilities (§2.11).
        referee: any object satisfying the §7.3 protocol, or ``None``.
    """
    if profile is None:
        profile = select_profile(doc)
    if metadata is None:
        metadata = extract_metadata(doc, profile=profile)
    if segmentation is None:
        segmentation = segment_document(doc, profile=profile, metadata=metadata)
    if hierarchy is None:
        hierarchy = infer_hierarchy(
            doc, segmentation=segmentation, profile=profile, metadata=metadata
        )

    doc_name = doc.source or "<document>"
    blocks = _body_blocks(doc, segmentation)
    # `isinstance(b, StyledPara)` verbatim from `hierarchy.tree.build_tree`, not
    # `not isinstance(b, StyledTable)`. The two are equivalent today, and the
    # point is that they must never stop being: `analyse_quotation` is asked the
    # same question over the same paragraphs the hierarchy asked it over, so the
    # two packages cannot reach different quotation verdicts for the same
    # document. Cycle 4's report is explicit that routing "must not become a
    # second source of truth for the same measurements".
    paras = [b for b in blocks if isinstance(b, StyledPara)]
    body_indices = [b.index for b in blocks]

    analysis = analyse_quotation(paras)
    census_ = census(paras, analysis)
    census_, consulted, overrode = _adjudicate_articles(
        paras,
        analysis,
        census_,
        doc_name=doc_name,
        referee=referee,
        log=log,
        logger=logger,
    )

    coverage = articulation_coverage(census_, body_indices)
    prior = genre_prior(profile)

    # -- blockers ----------------------------------------------------------
    blockers: list[Blocker] = []
    if not census_.found:
        blockers.append(
            Blocker(
                BLOCKER_NO_ARTICLES,
                f"no paragraph in the {len(body_indices)}-block body opens an "
                "article",
            )
        )
    elif census_.all_quoted:
        blockers.append(
            Blocker(
                BLOCKER_ALL_ARTICLES_QUOTED,
                f"{census_.n_quoted} of {census_.n_found} article paragraphs "
                "convicted by the quotation guard; the document quotes statutes "
                "it does not enact",
            )
        )
    elif census_.n_own < MIN_OWN_ARTICLES:  # pragma: no cover - implied above
        blockers.append(
            Blocker(BLOCKER_NO_ARTICLES, "no article survived the quotation guard")
        )

    if census_.found and not census_.monotonic:
        blockers.append(
            Blocker(
                BLOCKER_NON_MONOTONIC,
                "the article series does not hold together: "
                f"{', '.join(str(v) for v in census_.values)}",
            )
        )

    if census_.own and coverage < COVERAGE_MIN:
        blockers.append(
            Blocker(
                BLOCKER_LOW_COVERAGE,
                f"articulation covers {coverage:.0%} of the body, below the "
                f"{COVERAGE_MIN:.0%} gate (§4.2)",
            )
        )

    tables = [b.index for b in blocks if isinstance(b, StyledTable)]
    if tables:
        blockers.append(
            Blocker(
                BLOCKER_TOP_LEVEL_TABLE,
                f"{len(tables)} table(s) at body top level, outside any "
                f"dispositivo (blocks {', '.join(str(i) for i in tables)})",
            )
        )

    # A-R.7 — a rendering blocker. Recorded, never vetoing.
    capabilities = None
    if emitter == "generico-aninhado":
        capabilities = probe_capabilities(generation)
        if not capabilities.nested_agrupamento:
            blockers.append(
                Blocker(
                    BLOCKER_NESTED_UNAVAILABLE,
                    capabilities.diagnostic,
                    vetoes=False,
                )
            )

    vetoes = [b for b in blockers if b.vetoes]

    # -- the gates ---------------------------------------------------------
    gates = {
        "own_articles": census_.n_own >= MIN_OWN_ARTICLES,
        "monotonic": census_.monotonic,
        "coverage": coverage >= COVERAGE_MIN,
        "no_vetoing_blocker": not vetoes,
    }
    route = "norma" if all(gates.values()) else "generico"

    p_norma, contributions = _p_norma(census_, coverage, prior, len(vetoes))
    confidence = p_norma if route == "norma" else round(1.0 - p_norma, 4)

    evidence: dict[str, Any] = {
        "genre_prior": prior.to_dict(),
        "census": census_.to_dict(),
        "body_blocks": len(body_indices),
        "quote_band_rule": analysis.bands.rule,
        "omissis": sorted(analysis.omissis),
        "citation_antecedent": sorted(analysis.citation_antecedent),
        "tables_in_body": tables,
        "annexes": [a.label for a in hierarchy.annexes],
        "gates": gates,
        "p_norma": p_norma,
        "contributions": [[name, value] for name, value in contributions],
        "hierarchy": {
            "body_sections": len(list(hierarchy.body.walk())),
            "body_flat": hierarchy.body.flat,
            "body_confidence": hierarchy.body.confidence,
            "rejected": list(hierarchy.body.signals.rejected),
        },
        "emitter": emitter,
    }
    if capabilities is not None:
        evidence["capabilities"] = capabilities.to_dict()

    verdict = StatutoryViability(
        route=route,
        confidence=confidence,
        articles_found=census_.n_found,
        articles_quoted=census_.n_quoted,
        numbering_monotonic=census_.monotonic,
        coverage=coverage,
        has_anexos=bool(hierarchy.annexes),
        blockers=tuple(blockers),
        evidence=evidence,
        referee_consulted=consulted,
        referee_overrode=overrode,
        source=doc.source,
        profile=profile.name,
    )

    # The route decision itself is a decision, and §7.4 wants it in the log
    # under its own kind — that INFO line is the one a batch run is read by.
    adjudicate(
        kind="route",
        doc=doc_name,
        locator="",
        rule_verdict=route,
        rule_confidence=confidence,
        excerpt="",
        reason=(
            "; ".join(str(b) for b in vetoes)
            if vetoes
            else "all statutory gates passed"
        ),
        referee=None,
        log=log,
        logger=logger,
    )
    return verdict
