"""Level unification: turning heterogeneous labels into one consistent depth.

A document does not number itself in one system. ``pn_cst_38`` runs ``2.`` →
``2.3`` → ``2.3.1``, then drops into ``I``/``II``/``III``, then into ``a)``/
``b)``, then climbs back to ``2.3.3`` — and every one of those transitions has
to land on the right depth or the tree is wrong in a way no schema will catch.

The machine is a stack of open sections. Each candidate computes a **key**
naming the sequence it belongs to: for a dotted numeric, its parent prefix, so
``6.3`` and ``6.4`` share one; for the other kinds, the kind itself. A key
already on the stack means "sibling" — pop to it. A key that is not means "new,
one level deeper". A dotted numeric additionally anchors to its parent's depth
rather than to the stack's height, which is what keeps ``port_mf_454``'s ``2.1``
at depth 2 even though ``a)`` and ``b)`` opened a level between them.

Three refusals live here rather than in the grammar, because each needs the
document to answer it (amendment A-4.2):

* **orphans** — ``1.24.20.25`` is a four-component label whose parent ``1.24.20``
  was never opened. It is a subject-classification code at the head of
  ``pn_cst_38``, not a fourth-level section.
* **implausible top series** — ``parecer_93``'s depth-1 numeric candidates read
  ``111, 46, 194, 74`` in document order. A document does not number itself
  backwards; those are fragments of quoted documents.
* **named-unit series** — ``Súmula CARF nº 1`` is a heading only because 130 of
  them run in order. One would be a sentence, and ``Lei nº 12.618`` is a
  sentence however many times it appears (amendment A-4.4).

And one promotion, ratified with the user (amendment A-4.3):
:func:`demote_numbered_containers`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Sequence

from ..ingest import StyledPara
from .evidence import (
    W_LABEL_SERIES,
    W_LABEL_SOLO,
    W_PROSE_HEADER_CONFIRMED,
    W_STYLE,
    W_UNIT_SERIES,
)
from .labels import Label, fold, looks_like_heading, parse_label
from .quotation import QuotationAnalysis, is_monotonic_series

__all__ = [
    "Assignment",
    "Candidate",
    "MIN_UNIT_SERIES",
    "PROSE_HEADER_MAX_CHARS",
    "PROSE_HEADER_MAX_WORDS",
    "PROSE_HEADER_MIN_UPPER",
    "PROSE_HEADER_RULE_CONFIDENCE",
    "collect_candidates",
    "demote_numbered_containers",
    "detect_unit_series",
    "is_prose_form_header",
    "style_level",
    "upper_ratio",
    "unify_levels",
    "validate_top_series",
]

#: How many occurrences make a repeated named unit a heading series.
MIN_UNIT_SERIES = 3

#: How long a run of same-depth style headings must be before the
#: numbered-container rule is even considered. Below this a run is not a
#: pattern, and reading one into it is fabrication.
MIN_DEMOTION_RUN = 4

#: The largest step a sibling sequence may take before it stops being one.
MAX_SIBLING_GAP = 3

#: How confident the typographic gate is on its own, before a referee is asked
#: (A-H.1). Deliberately **below** ``FLAG_THRESHOLD`` (0.60), exactly as
#: ``BOUNDARY_RULE_CONFIDENCE`` is: the gate is confident enough to *propose* a
#: header and not confident enough to *impose* one. With no referee configured
#: nothing is confirmed, no prose-form paragraph becomes a section, and every
#: tree is the tree Cycle 8c built.
PROSE_HEADER_RULE_CONFIDENCE = 0.55

#: The prose-form gate's shape limits. A section header is short; a paragraph
#: that runs on is prose however it is cased.
PROSE_HEADER_MAX_WORDS = 7
PROSE_HEADER_MAX_CHARS = 60

#: …and this fraction of its letters are upper-case. 0.85 rather than 1.0
#: admits `0 SECRETARIA DA RECEITA FEDERAL` and `RECURSO ESPECIAL N. 34.988-SP`
#: — both of which the referee then correctly refuses. Over-inclusion here is
#: safe by construction (the referee can only remove); under-inclusion is not.
PROSE_HEADER_MIN_UPPER = 0.85

#: A candidate must contain at least one letter. `_______________` and
#: `2.08.30.00` are not headers in any casing.
_HAS_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

_UNIT_LINE_RE = re.compile(
    r"^\s*(?P<head>[^\d\n]{2,60}?)\s*(?:n[ºo°]\.?|n\.)\s*(?P<num>\d{1,4})\s*$",
    re.IGNORECASE,
)
_HEADING_STYLE_RE = re.compile(r"^(heading|titulo|header)\s*(\d+)?", re.IGNORECASE)
#: An identifier inside a heading — `N. 46.146-SP`, `nº 3`, `2018/0012345-6`.
_IDENTIFIER_RE = re.compile(r"\d")

#: Label kinds that only mean anything as part of a sequence. One of these on
#: its own is noise — `parecer_93` block 330 is an OCR'd footnote marker `n.`
#: that would otherwise become a section of the parecer.
_SEQUENCE_KINDS = frozenset({"roman", "alpha", "compound", "ordinal"})

#: Label kind → `Section.kind` (spec R-3). Dotted numerics are resolved by
#: depth instead; see `section_kind`.
_KIND_BY_LABEL = {
    "roman": "inciso",
    "alpha": "alinea",
    "compound": "alinea",
    "unit": "item",
    "capitulo": "capitulo",
    "secao": "secao",
    "subsecao": "subsecao",
    "titulo": "titulo",
    "livro": "livro",
    "parte": "parte",
    "ordinal": "item",
}
_KIND_BY_DEPTH = ("secao", "subsecao", "item")


def section_kind(label: Label | None, depth: int) -> str:
    """The ``Agrupamento/@nome`` this section will carry (plan §5.1)."""
    if label is None:
        return _KIND_BY_DEPTH[min(depth, len(_KIND_BY_DEPTH)) - 1] if depth else "agrupamento"
    if label.kind == "numeric":
        return _KIND_BY_DEPTH[min(depth, len(_KIND_BY_DEPTH)) - 1]
    return _KIND_BY_LABEL.get(label.kind, "agrupamento")


def style_level(para: StyledPara) -> int | None:
    """Word's declared outline level, 0-based, or ``None``.

    ``outline_level`` is authoritative when present; the style *name* is the
    fallback for documents whose heading styles carry no `w:outlineLvl`.
    """
    if para.outline_level is not None:
        return para.outline_level
    if not para.style:
        return None
    match = _HEADING_STYLE_RE.match(fold(para.style))
    if match and match.group(2):
        return int(match.group(2)) - 1
    return None


def detect_unit_series(paras: Sequence[StyledPara]) -> frozenset[str]:
    """Folded head words that the document uses as a numbered heading series.

    Requires whole-paragraph matches — a mention inside a sentence is a
    citation, not a heading — and strictly increasing numbers, which is what
    ``port_mf_277``'s ``Súmula CARF nº 1 … nº 130`` has and a repeated statutory
    reference never does.
    """
    seen: dict[str, list[int]] = {}
    for para in paras:
        if para.is_empty:
            continue
        match = _UNIT_LINE_RE.match(para.text.strip())
        if not match:
            continue
        head = fold(match.group("head")).strip(" -–—.:")
        if not head:
            continue
        seen.setdefault(head, []).append(int(match.group("num")))
    heads = set()
    for head, values in seen.items():
        if len(values) < MIN_UNIT_SERIES:
            continue
        if all(b > a for a, b in zip(values, values[1:])):
            heads.add(head)
    return frozenset(heads)


@dataclass(frozen=True)
class Candidate:
    """One paragraph that could open a section."""

    index: int
    label: Label | None = None
    style: int | None = None
    quoted: bool = False
    text: str = ""
    #: A referee **confirmed** this paragraph as a section header (A-H.1).
    #: Never set by :func:`collect_candidates` from the text alone — only from
    #: `prose_form_indices`, which is populated by the confirmation step in
    #: `tree.py`. So a candidate nobody confirmed is invisible here, and the
    #: `--referee=none` tree is unchanged.
    prose_form: bool = False

    @property
    def is_candidate(self) -> bool:
        if self.quoted:
            return False
        if self.style is not None:
            return True
        if self.prose_form:
            return True
        return self.label is not None and not self.label.is_dispositivo


@dataclass(frozen=True)
class Assignment:
    """A candidate that survived, with the depth and kind it was given."""

    index: int
    depth: int
    kind: str
    label: Label | None
    style: int | None
    heading: str | None
    score: float
    signals: tuple[str, ...]


def upper_ratio(text: str) -> float:
    """What fraction of ``text``'s letters are upper-case. No letters ⇒ 0.0."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def is_prose_form_header(para: StyledPara, *, quoted: bool = False) -> bool:
    """Is ``para`` typographically distinctive but formally unlabelled (A-H.1)?

    This is a **generator**, not a decision. It proposes candidates for a
    referee to confirm or veto, and it is deliberately over-inclusive: measured
    over the corpus it proposes **33 paragraphs across 7 samples** for **6**
    true headers. Over-inclusion is safe because the confirmation step can only
    ever remove; precision here would cost real headers and buy nothing.

    Five refusals, each forced by a real paragraph:

    * **quoted** — a header inside a transcribed norm belongs to that norm, and
      the quotation guard has already ruled on it;
    * **styled** — Word already said it is a heading, so the existing route
      admits it and this one must not compete (`sumula_stj_125` is entirely
      this case, which is why it contributes 10 candidates and not 48);
    * **labelled** — a rótulo is its own admission route;
    * **too long** — `PROSE_HEADER_MAX_WORDS` / `_MAX_CHARS`;
    * **not enough letters, or none** — `_______________` at `par_cosit_26`
      block 7, and `2.08.30.00`.
    """
    if quoted or para.is_empty:
        return False
    if para.outline_level is not None or style_level(para) is not None:
        return False
    text = para.text.strip()
    if not text:
        return False
    if len(text) > PROSE_HEADER_MAX_CHARS or len(text.split()) > PROSE_HEADER_MAX_WORDS:
        return False
    if not _HAS_LETTER_RE.search(text):
        return False
    if upper_ratio(text) < PROSE_HEADER_MIN_UPPER:
        return False
    return parse_label(text) is None


def collect_candidates(
    paras: Sequence[StyledPara],
    analysis: QuotationAnalysis,
    *,
    unit_heads: frozenset[str] = frozenset(),
    prose_form_indices: frozenset[int] = frozenset(),
) -> tuple[Candidate, ...]:
    """Parse every non-empty paragraph into a (possibly empty) candidate.

    ``prose_form_indices`` names the paragraphs a referee has **already
    confirmed** as section headers (A-H.1). It is empty by default and empty
    under ``--referee=none``, which is what makes this function's answer — and
    every tree built from it — identical to Cycle 8c's on that path.
    """
    out: list[Candidate] = []
    for para in paras:
        if para.is_empty:
            continue
        text = para.text.strip()
        out.append(
            Candidate(
                index=para.index,
                label=parse_label(text, unit_heads=unit_heads),
                style=style_level(para),
                quoted=analysis.is_quoted(para.index),
                text=text,
                prose_form=para.index in prose_form_indices,
            )
        )
    return tuple(out)


def validate_top_series(candidates: Sequence[Candidate]) -> tuple[bool, tuple[int, ...]]:
    """Does the document's depth-1 numeric labelling look like its own?

    Returns the verdict and the values it judged, so a rejection can be
    reported rather than merely happening.
    """
    values = tuple(
        c.label.value[0]
        for c in candidates
        if c.is_candidate
        and c.style is None
        and c.label is not None
        and c.label.kind == "numeric"
        and len(c.label.value) == 1
    )
    if not values:
        return True, values
    return is_monotonic_series(values), values


@dataclass
class _Open:
    key: tuple
    depth: int
    value: tuple[int, ...]


def unify_levels(
    candidates: Sequence[Candidate],
) -> tuple[tuple[Assignment, ...], tuple[str, ...]]:
    """Assign a depth to every surviving candidate.

    Returns the assignments in document order and the reasons candidates were
    rejected — the latter feeding :class:`~.evidence.DocSignals.rejected`, and
    through it Cycle 4b's telemetry.
    """
    top_ok, top_values = validate_top_series(candidates)
    rejected: list[str] = []
    if not top_ok:
        rejected.append(
            "top numeric series implausible: " + ",".join(str(v) for v in top_values)
        )

    # A lone `n.` is not an enumeration. `parecer_93` block 330 is an OCR'd
    # footnote marker that parses as `alinea a)` would; without this it becomes
    # a section of the parecer. A sequence needs at least two members.
    counts: dict[tuple, int] = {}
    for c in candidates:
        if c.is_candidate and c.style is None and c.label is not None:
            if c.label.kind in _SEQUENCE_KINDS:
                counts[_sequence_key(c.label)] = counts.get(_sequence_key(c.label), 0) + 1
    singletons = {k for k, n in counts.items() if n < 2}

    style_levels = sorted({c.style for c in candidates if c.is_candidate and c.style is not None})
    style_rank = {level: rank + 1 for rank, level in enumerate(style_levels)}

    stack: list[_Open] = []
    out: list[Assignment] = []
    previous_depth = 0

    for candidate in candidates:
        if not candidate.is_candidate:
            continue

        # A-H.4. A referee-confirmed prose header parents whatever runs through
        # it. It clears the stack and opens at depth 1 under a key unique to
        # itself, so two of them are never read as a series — `RELATÓRIO` and
        # `CONCLUSÃO` are not `1.` and `2.` of anything.
        #
        # Checked before `style`, though the two are mutually exclusive by the
        # gate in `is_prose_form_header`, because that exclusivity belongs to
        # the generator and this loop should not depend on it holding.
        if candidate.prose_form and candidate.style is None:
            # **A confirmed prose header never outranks a styled one.** Where
            # the document declares outline levels, those are the author's own
            # statement of its structure and a referee's answer must slot
            # *inside* them, not above. So the header opens directly beneath
            # the innermost styled section still on the stack, and only becomes
            # a depth-1 division when there is none — which is the
            # `par_cosit_26` case this amendment was written for, where Word
            # declares nothing at all.
            #
            # Measured on `sumula_stj_125` under an adversarial referee: without
            # this, its 7 cases × 4 styled subsections collapse into 48 (and,
            # with only the styled branch anchored, into 13 with publication
            # dates parenting the subsections). With it, the styled tree is
            # untouched whatever the referee says.
            styled_open = next(
                (o for o in reversed(stack) if o.key[0] == "style"), None
            )
            depth = styled_open.depth + 1 if styled_open is not None else 1
            while stack and stack[-1].depth >= depth:
                stack.pop()
            stack.append(_Open(("prose", candidate.index), depth, ()))
            out.append(
                Assignment(
                    index=candidate.index,
                    depth=depth,
                    kind=section_kind(None, depth),
                    label=None,
                    style=None,
                    heading=candidate.text.strip() or None,
                    score=W_PROSE_HEADER_CONFIRMED,
                    signals=("prose_form", "referee_confirmed"),
                )
            )
            previous_depth = depth
            continue

        if candidate.style is not None:
            # A styled heading always reclaims its own rank, popping any prose
            # header that opened beneath it (A-H.4). Word's declaration is the
            # stronger evidence and must not be displaced by a referee's.
            depth = style_rank[candidate.style]
            while stack and stack[-1].depth >= depth:
                stack.pop()
            stack.append(_Open(("style", candidate.style), depth, ()))
            heading = candidate.text
            out.append(
                Assignment(
                    index=candidate.index,
                    depth=depth,
                    kind=section_kind(candidate.label, depth),
                    label=candidate.label,
                    style=candidate.style,
                    heading=heading.strip() or None,
                    score=W_STYLE,
                    signals=("style",),
                )
            )
            previous_depth = depth
            continue

        label = candidate.label
        assert label is not None  # guaranteed by `is_candidate`

        if label.kind in _SEQUENCE_KINDS and _sequence_key(label) in singletons:
            rejected.append(f"solitary {label.raw!r} at block {candidate.index}")
            continue

        if label.kind == "numeric":
            if len(label.value) == 1:
                if not top_ok:
                    continue
                # A-H.4. A top-level numeric normally *is* the top level, and
                # resets the stack. But when a confirmed prose header is open,
                # the series runs underneath it: `par_cosit_26` numbers `2.` …
                # `18.` inside RELATÓRIO and continues `19.` inside CONCLUSÃO,
                # so the numbering is evidence about the items, not about the
                # divisions holding them. Anchor to the header rather than
                # emptying the stack, and the parenting the user asked for
                # falls out with no change to any other branch.
                prose_open = next(
                    (o for o in reversed(stack) if o.key[0] == "prose"), None
                )
                if prose_open is not None:
                    depth = prose_open.depth + 1
                    key: tuple = ("numeric", ())
                    while stack and stack[-1].depth >= depth:
                        stack.pop()
                else:
                    depth = 1
                    key = ("numeric", ())
                    stack = []
            else:
                parent = label.value[:-1]
                anchor = next(
                    (o for o in reversed(stack) if o.key[0] == "numeric" and o.value == parent),
                    None,
                )
                if anchor is None:
                    rejected.append(f"orphan label {label.raw!r} at block {candidate.index}")
                    continue
                depth = anchor.depth + 1
                key = ("numeric", parent)
                while stack and stack[-1].depth >= depth:
                    stack.pop()
        else:
            key = _sequence_key(label)
            existing = next((o for o in reversed(stack) if o.key == key), None)
            if existing is not None:
                # A `unit` series was already validated document-wide by
                # `detect_unit_series`, so it needs only to keep increasing.
                # `port_mf_277`'s súmulas run 1, 3, 4 … 33, 40, 41 — the gaps
                # are the ones CARF revoked, and a gap limit would amputate the
                # annex at nº 33.
                gap_limit = None if label.kind == "unit" else MAX_SIBLING_GAP
                if label.value[-1] <= existing.value[-1] or (
                    gap_limit is not None
                    and label.value[-1] - existing.value[-1] > gap_limit
                ):
                    rejected.append(
                        f"non-sequential {label.raw!r} at block {candidate.index}"
                    )
                    continue
                depth = existing.depth
                while stack and stack[-1].depth >= depth:
                    stack.pop()
            else:
                depth = min(len(stack) + 1, previous_depth + 1) if previous_depth else 1
                while stack and stack[-1].depth >= depth:
                    stack.pop()

        # Depth monotonicity (plan §8 Cycle 4): never more than one deeper than
        # the heading before it. A jump means the evidence is inconsistent, and
        # clamping is the honest response — the alternative is a tree with a
        # hole in it.
        if previous_depth and depth > previous_depth + 1:
            depth = previous_depth + 1

        sibling = next((o for o in reversed(stack) if o.key == key), None)
        if sibling is not None and label.value[-1] <= sibling.value[-1]:
            rejected.append(f"non-sequential {label.raw!r} at block {candidate.index}")
            continue

        stack.append(_Open(key, depth, label.value))
        score, signals = _score(label, top_ok)
        # `2. DAS SOCIEDADES COOPERATIVAS` names the section; `5.1 - Como foi
        # dito inicialmente, deve o imposto…` *is* the section's first
        # paragraph. Only the first fills `nomeAgrupador`; the second stays
        # prose, and :mod:`.tree` puts it in the body so no text is lost.
        remainder = label.text.strip()
        heading = remainder if remainder and looks_like_heading(remainder) else None
        out.append(
            Assignment(
                index=candidate.index,
                depth=depth,
                kind=section_kind(label, depth),
                label=label,
                style=None,
                heading=heading,
                score=score,
                signals=signals,
            )
        )
        previous_depth = depth

    return tuple(out), tuple(rejected)


def _sequence_key(label: Label) -> tuple:
    if label.kind == "compound":
        return ("compound", label.value[0])
    if label.kind == "unit":
        return ("unit", label.unit_head)
    return (label.kind,)


def _score(label: Label, top_ok: bool) -> tuple[float, tuple[str, ...]]:
    if label.kind == "unit":
        return W_UNIT_SERIES, ("label:unit", "series")
    if label.kind == "numeric" and top_ok:
        return W_LABEL_SERIES, (f"label:{label.kind}", "series")
    if label.kind in {"roman", "alpha", "compound"}:
        return W_LABEL_SERIES, (f"label:{label.kind}", "series")
    if label.kind in {"capitulo", "secao", "subsecao", "titulo", "livro", "parte"}:
        return W_LABEL_SERIES, (f"label:{label.kind}",)
    return W_LABEL_SOLO, (f"label:{label.kind}",)


def _is_numbered_heading(text: str) -> bool:
    """True when a heading carries its own identifier.

    ``RECURSO ESPECIAL N. 34.988-SP`` names a specific thing; ``EMENTA`` names a
    part of whatever thing it sits inside. That asymmetry — not a vocabulary of
    Brazilian court-document section names — is what the demotion rule reads.
    """
    return bool(_IDENTIFIER_RE.search(text or ""))


def demote_numbered_containers(
    assignments: Sequence[Assignment], *, texts: dict[int, str]
) -> tuple[Assignment, ...]:
    """Nest identifier-free headings under the identified heading above them.

    Amendment A-4.3, ratified with the user. ``sumula_stj_125`` is 38 sibling
    ``Heading 1`` blocks in which eight name a case and thirty name a part of
    one; Word records no difference between them, so the difference has to be
    read from what the headings say about themselves.

    Three guards keep it from firing on a document that merely happens to have
    a number in a heading: the run must be at least
    :data:`MIN_DEMOTION_RUN` long and **start** with an identified heading, and
    it must genuinely mix the two (≥2 identified, ≥1 bare). ``CARNE_LEAO``'s
    five ``Heading 2`` blocks carry no identifier at all and the rule declines;
    ``port_mf_277``'s 130 ``Súmula CARF nº N`` are all identified and it
    declines again.
    """
    if not assignments:
        return tuple(assignments)

    result = list(assignments)
    # A-H.4. A referee-confirmed prose header sits *inside* the styled tree, so
    # it must not break a styled run in half — that would silently disable this
    # rule for the rest of the document. Measured on `sumula_stj_125` under an
    # adversarial referee: one confirmed `DJ 22.08.1994` between two `Heading 1`
    # blocks split the 38-heading run and left all 38 at depth 1, undoing A-4.3
    # entirely. Prose headers are therefore skipped over when the run is
    # collected, and are never themselves demoted — they are already positioned
    # relative to the styled heading above them.
    demotable = [i for i, a in enumerate(result) if "prose_form" not in a.signals]

    start = 0
    while start < len(demotable):
        depth = result[demotable[start]].depth
        end = start
        while (
            end < len(demotable)
            and result[demotable[end]].depth == depth
            and result[demotable[end]].style is not None
        ):
            end += 1
        run = [result[i] for i in demotable[start:end]]
        if len(run) >= MIN_DEMOTION_RUN:
            flags = [_is_numbered_heading(texts.get(a.index, "")) for a in run]
            if flags[0] and sum(flags) >= 2 and sum(1 for f in flags if not f) >= 1:
                for offset, (assignment, numbered) in enumerate(zip(run, flags)):
                    if not numbered:
                        index = demotable[start + offset]
                        result[index] = replace(
                            assignment,
                            depth=depth + 1,
                            kind="subsecao",
                            signals=assignment.signals + ("demoted",),
                        )
        start = max(end, start + 1)
    return tuple(result)
