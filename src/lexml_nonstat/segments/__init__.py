"""Hierarchical segmentation output — plan §6.

    from lexml_nonstat.segments import segments, to_csv
    print(to_csv(segments(model)))

**What a segment is.** One citable unit of a document — a section, a
dispositivo, or a front/back-matter region — with the address a consumer cites
it by and the ancestry a consumer reads it in. This is the package Cycle 7
delivers, and it is what §2.4's segmentation experiment was a prototype of.

**Why the package is `segments` and not `segmentation`.** Plan §6.1 names
`segmentation/api.py`, but `lexml_nonstat.segment` has meant something else
since Cycle 3 — the *spans* that divide a document into front matter, body,
back matter and annexes. Two packages three letters apart, exporting
similar-sounding names for unrelated concepts, is a readability hazard worth
one plan amendment (**A-7.1**). `segment` divides; `segments` cites.

**Two addresses, deliberately.** `Segment.urn` resolves against the artifact it
came from; `Segment.path` is emitter-independent. Amendment **A-5b.4** measured
that these cannot be one field, and `model.py` explains why at length.

The three-way oracle
--------------------

Plan **A-R.5** makes reversibility a three-way agreement: the in-process model,
the flat XML and the nested XML must segment identically. `segments_from_model`
reaches its answer without touching XML; the readers reach theirs without
touching the model. `tests/regression/test_three_way_oracle.py` is that claim.
"""

from .api import (
    REGION_LEVEL,
    STATUTORY_KINDS,
    parse_document,
    segments,
    segments_from_flat_xml,
    segments_from_model,
    segments_from_nested_xml,
    segments_from_norma_xml,
)
from .ids import EMITTER_TOKENS, model_segment_tree
from .model import Segment, segments_from_dicts, segments_to_dicts
from .roundtrip import hierarchy_from_xml, sections_from_xml
from .writers import (
    BREADCRUMB_SEPARATOR,
    CSV_COLUMNS,
    csv_row,
    to_csv,
    to_jsonl,
)

__all__ = [
    "BREADCRUMB_SEPARATOR",
    "CSV_COLUMNS",
    "EMITTER_TOKENS",
    "REGION_LEVEL",
    "STATUTORY_KINDS",
    "Segment",
    "csv_row",
    "hierarchy_from_xml",
    "model_segment_tree",
    "parse_document",
    "sections_from_xml",
    "segments",
    "segments_from_dicts",
    "segments_from_flat_xml",
    "segments_from_model",
    "segments_from_nested_xml",
    "segments_from_norma_xml",
    "segments_to_dicts",
    "to_csv",
    "to_jsonl",
]
