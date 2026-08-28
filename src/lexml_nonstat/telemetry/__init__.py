"""Rule-vs-referee decision telemetry (plan §7.4).

    from lexml_nonstat.telemetry import DecisionLog, render_report

    log = DecisionLog()
    ...                                   # routing fills it
    print(render_report(log))

Plan invariant #10: every rule failure and referee override is logged **and
counted**. The log line is for the person watching one document; the report is
for the person asking whether the rules will survive 300.
"""

from .decisions import (
    DECISION_KINDS,
    LOGGER_NAME,
    MAX_EXCERPT_IN_RECORD,
    DecisionLog,
    DecisionRecord,
    logger,
)
from .report import DecisionsReport, render_report

__all__ = [
    "DECISION_KINDS",
    "LOGGER_NAME",
    "MAX_EXCERPT_IN_RECORD",
    "DecisionLog",
    "DecisionRecord",
    "DecisionsReport",
    "logger",
    "render_report",
]
