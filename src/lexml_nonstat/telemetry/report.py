"""``--decisions-report`` — the instrument for judging rule generalisation.

Plan §7.4 calls the ``referee agreed`` / ``referee overrode`` split "the key
metric": a high agreement rate means the thresholds are too conservative and
cheap to tighten; a high override rate localises which rule is wrong, and on
which genres. Neither number means anything unless the counts reconcile, so
the report checks its own arithmetic.

Two identities, not the plan's one
----------------------------------
§7.4 states ``agreed + overrode == flagged``. That is false under the suite's
own default. §9.3 pins ``--referee=none`` for every regression test, so flagged
decisions are never put to a referee and both terms are zero while ``flagged``
is not. A referee may also *abstain* — a timeout, a malformed reply, or
``NullReferee``. The identities that actually hold are::

    rule_only + flagged                       == total
    agreed + overrode + overruled + abstained == consulted   (consulted <= flagged)

`overruled` is the fourth bucket: a referee that answered, contradicted the
rule, and was refused the override — because it was itself unsure, or because
the rule was too confident to touch. It is neither an agreement nor an
override, and folding it into `agreed` (the first version of this module did)
inflates "rules were right but unsure" with cases where nothing confirmed the
rule at all.

The plan's form is the special case where every flagged decision is consulted,
none abstains and none is overruled, and :meth:`DecisionsReport.check` reports
which identity broke rather than merely that something did. Recorded as
amendment A-4b.4.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .decisions import DecisionLog

__all__ = ["DecisionsReport", "render_report"]


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


@dataclass(frozen=True)
class DecisionsReport:
    """§7.4's per-corpus summary, as data."""

    total: int = 0
    rule_only: int = 0
    flagged: int = 0
    consulted: int = 0
    agreed: int = 0
    overrode: int = 0
    overruled: int = 0
    abstained: int = 0
    cache_hits: int = 0
    overrides_by_kind: tuple[tuple[str, int], ...] = ()
    overrides_by_doc: tuple[tuple[str, int], ...] = ()
    flagged_by_kind: tuple[tuple[str, int], ...] = ()

    @property
    def flagged_pct(self) -> float:
        return _pct(self.flagged, self.total)

    @property
    def rule_only_pct(self) -> float:
        return _pct(self.rule_only, self.total)

    @property
    def agreed_pct(self) -> float:
        return _pct(self.agreed, self.consulted)

    @property
    def overrode_pct(self) -> float:
        return _pct(self.overrode, self.consulted)

    @property
    def overruled_pct(self) -> float:
        return _pct(self.overruled, self.consulted)

    @property
    def cache_hit_pct(self) -> float:
        return _pct(self.cache_hits, self.consulted)

    def check(self) -> str | None:
        """Return the first identity that fails, or ``None`` when both hold."""
        if self.rule_only + self.flagged != self.total:
            return (
                f"rule_only + flagged != total "
                f"({self.rule_only} + {self.flagged} != {self.total})"
            )
        if (
            self.agreed + self.overrode + self.overruled + self.abstained
            != self.consulted
        ):
            return (
                f"agreed + overrode + overruled + abstained != consulted "
                f"({self.agreed} + {self.overrode} + {self.overruled} + "
                f"{self.abstained} != {self.consulted})"
            )
        if self.consulted > self.flagged:
            return (
                f"consulted > flagged ({self.consulted} > {self.flagged}): a "
                "referee was asked about a decision the rules were sure of"
            )
        return None

    @classmethod
    def from_log(cls, log: DecisionLog) -> "DecisionsReport":
        by_kind: Counter[str] = Counter()
        by_doc: Counter[str] = Counter()
        flagged_kind: Counter[str] = Counter()
        rule_only = flagged = consulted = 0
        agreed = overrode = overruled = abstained = hits = 0

        for record in log:
            if record.rule_flagged:
                flagged += 1
                flagged_kind[record.kind] += 1
            else:
                rule_only += 1
            if record.referee_consulted:
                consulted += 1
                if record.cache_hit:
                    hits += 1
                if record.abstained:
                    abstained += 1
                elif record.overridden:
                    overrode += 1
                    by_kind[record.kind] += 1
                    by_doc[record.doc] += 1
                elif record.agreed:
                    agreed += 1
                else:
                    overruled += 1

        def ranked(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
            # Count descending, then name — so the report is deterministic even
            # when two documents tie, which invariant #4 requires of anything
            # a golden or a diff might touch.
            return tuple(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))

        return cls(
            total=len(log),
            rule_only=rule_only,
            flagged=flagged,
            consulted=consulted,
            agreed=agreed,
            overrode=overrode,
            overruled=overruled,
            abstained=abstained,
            cache_hits=hits,
            overrides_by_kind=ranked(by_kind),
            overrides_by_doc=ranked(by_doc),
            flagged_by_kind=ranked(flagged_kind),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "rule_only": self.rule_only,
            "flagged": self.flagged,
            "consulted": self.consulted,
            "agreed": self.agreed,
            "overrode": self.overrode,
            "overruled": self.overruled,
            "abstained": self.abstained,
            "cache_hits": self.cache_hits,
            "overrides_by_kind": [list(p) for p in self.overrides_by_kind],
            "overrides_by_doc": [list(p) for p in self.overrides_by_doc],
            "flagged_by_kind": [list(p) for p in self.flagged_by_kind],
        }


def render_report(log: DecisionLog | DecisionsReport) -> str:
    """§7.4's summary as text, for ``--decisions-report``."""
    report = log if isinstance(log, DecisionsReport) else DecisionsReport.from_log(log)

    def pairs(label: str, items: tuple[tuple[str, int], ...]) -> str:
        if not items:
            return f"{label} none"
        return f"{label} " + " · ".join(f"{name} {n}" for name, n in items)

    lines = [
        f"Decisions:            {report.total:,}",
        f"Rule-only (confident): {report.rule_only:,}  ({report.rule_only_pct}%)",
        f"Flagged:               {report.flagged:,}  ({report.flagged_pct}%)",
        f"  put to a referee:    {report.consulted:,}",
        f"    referee agreed:    {report.agreed:,}  "
        f"({report.agreed_pct}% of consulted)  ← rules were right but unsure",
        f"    referee overrode:  {report.overrode:,}  "
        f"({report.overrode_pct}% of consulted)  ← rules were wrong",
        f"    referee overruled: {report.overruled:,}  "
        f"← referee disagreed but was refused",
        f"    referee abstained: {report.abstained:,}",
        f"Cache hit rate:        {report.cache_hit_pct}%",
        pairs("Flagged by kind:  ", report.flagged_by_kind),
        pairs("Overrides by kind:", report.overrides_by_kind),
        pairs("Top override docs:", report.overrides_by_doc),
    ]

    problem = report.check()
    lines.append(
        "Counts reconcile." if problem is None else f"COUNTS DO NOT RECONCILE: {problem}"
    )
    return "\n".join(lines)
