"""Front matter: the four parts are found where they are, and nowhere else.

Cycle 3's front-matter segmenter answers four questions per document — where
the epigraph, ementa, preamble and enacting formula are — and the plan's exit
criterion is that it answers all four correctly for all 15 samples *without
inventing any of them*. Both halves of that are load-bearing, and this file is
organised around the second half, because a segmenter that finds structure
where none exists is the failure mode that corrupts silently:

1. **No false positives** (spec §5.1, plan §12 exit criterion 2).
   ``CARNE_LEAO`` is a ``servico``-profile web page whose title matches the
   ``servico`` profile's *own* epigraph pattern. It must yield
   ``front.is_empty``. :func:`test_carne_leao_no_front_matter` is the headline
   test, and :func:`test_carne_leao_epigraph_needs_metadata_to_be_suppressed`
   sits beside it to record *why* it passes: only because ``find_epigraph``
   defers to Cycle 2's ``metadata.epigraph_index is None`` rather than running
   its own scan. Called without metadata the very same document yields a
   spurious ``Span(0, 0)``. A test asserting only ``is_empty`` would stay green
   if that deference were removed and something else happened to suppress the
   match.
2. **The portal artifact is not an ementa** (Cycle 2 caution).
   ``adn_cst_10`` block 1 reads ``O ato não possui ementa. Ver íntegra`` — a
   scraping notice saying the act *has* no ementa. Reading it as one would file
   a portal banner as the document's official summary.
   :func:`test_adn_cst_10_portal_artifact_is_not_ementa` asserts both that the
   ementa is ``None`` and that block 1 really is that string, so the test still
   documents its own premise if the corpus ever changes.
3. **Labels split even without a space** (plan §8 bullet 2). ``parecer_93``'s
   ementa label is separated from its value by ``<w:tab/>``, so the naive
   ``": "`` split loses it entirely.

The exact spans of §3.4's ground-truth table live in :data:`GROUND_TRUTH` as
module-level data. That table is what the cycle *claims to do*: changing an
entry changes the claim and belongs in review, never in a fixup commit.

Samples are loaded from Cycle 1's committed ``tests/golden/styled/*.json``
dumps rather than from the ``.docx`` files, exactly as ``test_metadata.py``
and ``test_profiles.py`` do — deterministic, fast, and it keeps a failure here
attributable to the segmenter rather than to the DOCX reader (which
``tests/golden/test_styled_goldens.py`` already owns).

``metadata=`` is passed on every whole-document call, because production's
``segment_document()`` always supplies it and ``find_epigraph``'s behaviour
differs when it is absent (see point 1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc
from lexml_nonstat.model import Metadata, extract_metadata
from lexml_nonstat.profile import DocumentProfile, get_profile, select_profile
from lexml_nonstat.segment import (
    EMENTA_LABEL_RE,
    FrontMatter,
    Span,
    find_ementa,
    find_enacting_formula,
    find_epigraph,
    find_preamble,
    segment_front,
    split_label,
)
from lexml_nonstat.segment.frontmatter import _is_no_ementa_artifact

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"

#: Sorted so parametrised ids are stable and readable.
SAMPLE_STEMS = sorted(p.stem for p in STYLED_DIR.glob("*.json"))

# Long stems, spelled once, so the tables below stay legible.
PARECER_93 = "parecer_93_2018_decor_cgu_agu"
CARNE_LEAO = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"

#: Spec §3.4's front-matter ground truth, as ``(start, end)`` pairs — inclusive
#: on both ends, matching :class:`Span`. ``None`` means the part is genuinely
#: absent, and absence is asserted just as strictly as presence: the two zero-
#: false-positive anchors of the cycle (``adn_cst_10``'s ementa and every part
#: of ``CARNE_LEAO``) are entries in this table, not special cases beside it.
GROUND_TRUTH: dict[str, dict[str, tuple[int, int] | None]] = {
    "ad_pgfn_13_20111220": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": (2, 2),
        "enacting_formula": None,
    },
    "ad_pgfn_3_20080918": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": (2, 2),
        "enacting_formula": None,
    },
    "ad_srf_22_19970430": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": (2, 2),
        "enacting_formula": (3, 3),
    },
    "ad_srf_3_19990107": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": (2, 2),
        "enacting_formula": None,
    },
    "adn_cosit_19_20001025": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": (2, 2),
        "enacting_formula": (3, 3),
    },
    # Block 1 is the portal artifact, hence no ementa.
    "adn_cst_10_19910417": {
        "epigraph": (0, 0),
        "ementa": None,
        "preamble": (2, 2),
        "enacting_formula": (3, 3),
    },
    "par_cosit_26_20000629": {
        "epigraph": (0, 0),
        "ementa": (2, 2),
        "preamble": None,
        "enacting_formula": None,
    },
    # The deepest front matter in the corpus: a portal date stamp and an
    # institutional banner precede the epigraph, and three labelled fields
    # separate it from the ementa, which then runs over four blocks.
    PARECER_93: {
        "epigraph": (3, 3),
        "ementa": (9, 12),
        "preamble": None,
        "enacting_formula": None,
    },
    "pn_cst_38_19801031": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": None,
        "enacting_formula": None,
    },
    "port_mf_277_20180607": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": (2, 2),
        "enacting_formula": None,
    },
    "port_mf_454_19770825": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": (2, 2),
        "enacting_formula": (3, 3),
    },
    "REsp_1306393": {
        "epigraph": (2, 2),
        "ementa": (5, 5),
        "preamble": (12, 12),
        "enacting_formula": None,
    },
    "sumula_carf_42": {
        "epigraph": (0, 0),
        "ementa": (1, 1),
        "preamble": None,
        "enacting_formula": None,
    },
    "sumula_stj_125": {
        "epigraph": (0, 0),
        "ementa": (2, 2),
        "preamble": None,
        "enacting_formula": None,
    },
    # The no-false-positive anchor: a web page with no front matter at all.
    CARNE_LEAO: {
        "epigraph": None,
        "ementa": None,
        "preamble": None,
        "enacting_formula": None,
    },
}

#: The four part names, in the order they appear in a document. Used to
#: parametrise the ground-truth test one part at a time, so a failure names the
#: part that moved rather than dumping a whole document's segmentation.
PART_NAMES = ("epigraph", "ementa", "preamble", "enacting_formula")

# --------------------------------------------------------------------------
# Loading
#
# 15 samples across a dozen parametrised tests would re-parse and re-segment
# hundreds of times; all three caches are module-scoped, keeping the file to
# well under a second.
# --------------------------------------------------------------------------

_DOC_CACHE: dict[str, StyledDoc] = {}
_META_CACHE: dict[str, Metadata] = {}
_FRONT_CACHE: dict[str, FrontMatter] = {}


def styled(name: str) -> StyledDoc:
    """Load a sample from Cycle 1's golden rather than re-parsing the DOCX."""
    if name not in _DOC_CACHE:
        _DOC_CACHE[name] = StyledDoc.from_json(
            (STYLED_DIR / f"{name}.json").read_text(encoding="utf-8")
        )
    return _DOC_CACHE[name]


def metadata(name: str) -> Metadata:
    """Cycle 2's metadata, extracted the way production does — with a filename."""
    if name not in _META_CACHE:
        _META_CACHE[name] = extract_metadata(styled(name), filename=f"{name}.docx")
    return _META_CACHE[name]


def front(name: str) -> FrontMatter:
    """Segment ``name`` exactly as ``segment_document()`` does.

    Metadata is passed explicitly because it changes the answer: see this
    module's docstring, point 1.
    """
    if name not in _FRONT_CACHE:
        doc = styled(name)
        _FRONT_CACHE[name] = segment_front(doc, select_profile(doc), metadata(name))
    return _FRONT_CACHE[name]


def block_text(name: str, index: int) -> str:
    """The text of one source block, by index."""
    for block in styled(name).blocks:
        if block.index == index:
            return block.text
    raise AssertionError(f"{name} has no block {index}")


def as_pair(span: Span | None) -> tuple[int, int] | None:
    """A span as the ``(start, end)`` pair :data:`GROUND_TRUTH` records."""
    return None if span is None else (span.start, span.end)


# --------------------------------------------------------------------------
# parecer_93 — the deepest front matter in the corpus (plan §8 bullet 1)
# --------------------------------------------------------------------------


def test_parecer_93_epigraph() -> None:
    """The epigraph is block 3, not block 0.

    Blocks 0–2 are a portal date stamp and a two-line institutional banner.
    Any rule that took "the first paragraph" as the epigraph would return the
    stamp, so asserting the *index* matters as much as asserting the text.
    """
    span = front(PARECER_93).epigraph
    assert span == Span(3, 3)
    assert span.text(styled(PARECER_93)) == "PARECER n. 00093/2018/DECOR/CGU/AGU"


def test_parecer_93_ementa_from_label() -> None:
    """The ementa is found by its ``EMENTA:`` label, six blocks below the epigraph.

    ``NUP:``, ``INTERESSADOS:`` and ``ASSUNTO:`` sit between the two. The label
    is what locates the ementa here; position alone cannot.
    """
    span = front(PARECER_93).ementa
    assert span is not None
    assert span.start == 9
    text = block_text(PARECER_93, 9)
    assert text.startswith("EMENTA:")
    assert split_label(text) is not None
    label, value = split_label(text)
    assert label == "EMENTA"
    assert value.startswith("ADMINISTRATIVO.")


def test_parecer_93_ementa_continues_over_unlabelled_lines() -> None:
    """The ementa runs 9–12: the label block plus three continuation lines.

    Continuation stops at the next labelled paragraph, so this pins both that
    the run extends *and* that it is bounded — an unbounded rule would swallow
    the body of the parecer.
    """
    span = front(PARECER_93).ementa
    assert as_pair(span) == (9, 12)
    assert len(span) == 4
    # Every continuation block is unlabelled prose; had one carried a label,
    # the run would (correctly) have stopped before it.
    for index in span.indices[1:]:
        assert split_label(block_text(PARECER_93, index)) is None


def test_parecer_93_has_no_preamble_or_enacting_formula() -> None:
    """A parecer states an opinion; it neither invokes competence nor enacts.

    The `parecer` profile carries no ``enacting_res`` at all, so this is also a
    check that profile gating actually suppresses the search.
    """
    matter = front(PARECER_93)
    assert matter.preamble is None
    assert matter.enacting_formula is None
    assert get_profile("parecer").enacting_res == ()


# --------------------------------------------------------------------------
# Label splitting (plan §8 bullet 2)
# --------------------------------------------------------------------------


def test_ementa_label_without_space_splits() -> None:
    """``EMENTA:ADMINISTRATIVO.`` splits, and the value keeps no leading colon.

    This is ``parecer_93``'s raw form: in the DOCX the label is followed by
    ``<w:tab/>``, not a space. A ``": "`` split would miss the label entirely
    and fall through to the unlabelled heuristic, which looks at the *wrong*
    block.
    """
    assert split_label("EMENTA:ADMINISTRATIVO.") == ("EMENTA", "ADMINISTRATIVO.")

    match = EMENTA_LABEL_RE.match("EMENTA:ADMINISTRATIVO.")
    assert match is not None
    assert match.group(2) == "ADMINISTRATIVO."
    assert not match.group(2).startswith(":")


def test_ementa_label_tab_separated_splits() -> None:
    """The tab form — literally what the DOCX contains — splits identically."""
    assert split_label("EMENTA:\tADMINISTRATIVO.") == ("EMENTA", "ADMINISTRATIVO.")

    match = EMENTA_LABEL_RE.match("EMENTA:\tADMINISTRATIVO.")
    assert match is not None
    assert match.group(2).strip() == "ADMINISTRATIVO."
    assert not match.group(2).lstrip().startswith(":")


@pytest.mark.parametrize(
    "text",
    [
        "EMENTA:",
        "Ementa:",
        "EMENTA :",
        "ementa:",
        "EMENTA:  ",
    ],
)
def test_ementa_label_variants(text: str) -> None:
    """Case and spacing around the colon are noise, not signal.

    The corpus spells the label at least three ways; the 300+ unseen documents
    will spell it more. An empty value is legitimate — ``EMENTA:`` alone on a
    line is a heading whose value is the paragraphs beneath it.
    """
    match = EMENTA_LABEL_RE.match(text)
    assert match is not None, f"{text!r} did not match EMENTA_LABEL_RE"
    assert match.group(1).lower() == "ementa"

    split = split_label(text)
    assert split is not None
    assert split[0].lower().rstrip(" :") == "ementa"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("EMENTA: ADMINISTRATIVO.", ("EMENTA", "ADMINISTRATIVO.")),
        ("EMENTA:ADMINISTRATIVO.", ("EMENTA", "ADMINISTRATIVO.")),
        ("EMENTA:\tADMINISTRATIVO.", ("EMENTA", "ADMINISTRATIVO.")),
        ("EMENTA : ADMINISTRATIVO.", ("EMENTA", "ADMINISTRATIVO.")),
        ("  Ementa:  Texto  ", ("Ementa", "Texto")),
        ("NUP: 00688.000178/2018-11", ("NUP", "00688.000178/2018-11")),
        ("ASSUNTO:", ("ASSUNTO", "")),
    ],
)
def test_split_label_pairs(text: str, expected: tuple[str, str]) -> None:
    """``split_label`` strips surrounding whitespace from both halves."""
    assert split_label(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "ADMINISTRATIVO. SERVIDOR PÚBLICO.",
        "O ato não possui ementa. Ver íntegra",
        "PARECER n. 00093/2018/DECOR/CGU/AGU",
        # A whole sentence before a colon is prose, not a label: the 40-char
        # bound is what stops a mid-paragraph colon from inventing a field.
        "Considerando o disposto no art. 3o da Lei no 12.618, de 2012: o beneficio",
    ],
)
def test_split_label_rejects_non_labels(text: str) -> None:
    """No colon, or too much text before it, means no label.

    The second case is the one that matters for the 300+ unseen corpus: legal
    prose is full of colons, and treating every prefix as a label would file
    arbitrary sentence fragments as document metadata.
    """
    assert split_label(text) is None


def test_split_label_rejects_multiline_prefix() -> None:
    """A label cannot span a line break — the prefix pattern excludes ``\\n``."""
    assert split_label("EMENTA\nADMINISTRATIVO.") is None


# --------------------------------------------------------------------------
# adn_cst_10 — the portal artifact (Cycle 2 caution)
# --------------------------------------------------------------------------


def test_adn_cst_10_portal_artifact_is_not_ementa() -> None:
    """``O ato não possui ementa. Ver íntegra`` is a scraping notice, not an ementa.

    It sits exactly where an ementa would sit — block 1, right below the
    epigraph — so position alone accepts it. Block 1's text is asserted here as
    well as the ``None`` result, so the test carries its own premise: if the
    corpus were ever re-scraped without the banner, this test would fail loudly
    rather than pass vacuously.
    """
    name = "adn_cst_10_19910417"
    assert block_text(name, 1).strip() == "O ato não possui ementa. Ver íntegra"
    assert front(name).ementa is None


@pytest.mark.parametrize(
    "text",
    [
        "O ato não possui ementa. Ver íntegra",
        "O ato nao possui ementa",
        "O ATO NÃO POSSUI EMENTA. VER ÍNTEGRA",
        "Sem ementa.",
        "sem ementa",
        "Ementa não disponível",
        "Ementa nao informada",
    ],
)
def test_no_ementa_artifacts_recognised(text: str) -> None:
    """Absence notices are matched on folded text, so accents and case are noise.

    Written against the *rule* rather than the one sample, because 300+ unseen
    documents will carry the same notice under other spellings.
    """
    assert _is_no_ementa_artifact(text)


@pytest.mark.parametrize(
    "text",
    [
        "EMENTA: ADMINISTRATIVO. SERVIDOR PÚBLICO.",
        "Imposto sobre a renda. Ementa do acórdão recorrido.",
        "Súmula CARF nº 42",
        "",
    ],
)
def test_real_ementas_are_not_absence_notices(text: str) -> None:
    """The rejection rule is narrow: it must not swallow real summaries."""
    assert not _is_no_ementa_artifact(text)


# --------------------------------------------------------------------------
# Enacting formulas (plan §8 bullet 3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["ad_srf_22_19970430", "adn_cosit_19_20001025", "adn_cst_10_19910417"],
)
def test_enacting_formula_declara(name: str) -> None:
    """``DECLARA,`` opens the dispositive part of an ato declaratório — block 3.

    ``adn_cosit_19`` spells it lowercase (``declara,``), so the rule cannot be
    case-sensitive; ``adn_cst_10`` reaches block 3 despite having no ementa, so
    the sequential cursor cannot assume all four parts are present.
    """
    span = front(name).enacting_formula
    assert as_pair(span) == (3, 3)
    assert span.text(styled(name)).lower().startswith("declara,")


def test_enacting_formula_resolve() -> None:
    """``port_mf_454`` block 3 is the bare formula ``RESOLVE:``."""
    name = "port_mf_454_19770825"
    span = front(name).enacting_formula
    assert as_pair(span) == (3, 3)
    assert span.text(styled(name)) == "RESOLVE:"


@pytest.mark.parametrize(
    "name",
    sorted(n for n, gt in GROUND_TRUTH.items() if gt["enacting_formula"] is None),
)
def test_no_enacting_formula_where_none_exists(name: str) -> None:
    """Ten of the fifteen samples enact nothing, and must say so.

    Pareceres, súmulas and acórdãos have no enacting formula by genre; the
    ``servico`` page has no structure at all. Asserting the negative across all
    of them is what keeps the ``DECLARA``/``RESOLVE`` patterns from drifting
    into ordinary prose.
    """
    assert front(name).enacting_formula is None


def test_enacting_formula_is_profile_gated() -> None:
    """Profiles without an enacting genre never search for one.

    ``find_enacting_formula`` returns early on an empty ``enacting_res``, so a
    parecer or an acórdão cannot acquire a ``DECLARA`` from quoted text.
    """
    for profile_name in ("parecer", "jurisprudencia_generico", "servico"):
        profile = get_profile(profile_name)
        assert profile.enacting_res == ()
    # And the gate is real, not incidental: run the ato-declaratório document
    # under the parecer profile and no formula is found at all.
    doc = styled("ad_srf_22_19970430")
    assert find_enacting_formula(doc, get_profile("parecer")) is None
    assert find_enacting_formula(doc, select_profile(doc)) == Span(3, 3)


# --------------------------------------------------------------------------
# CARNE_LEAO — the cycle's headline no-false-positive test
# --------------------------------------------------------------------------


def test_carne_leao_no_front_matter() -> None:
    """A web page has no front matter, and the segmenter must invent none.

    This is the cycle's headline requirement (plan §12 exit criterion 2, spec
    §5.1 "no false positives"). ``CARNE_LEAO`` is a Receita Federal service
    page — a title, some explanatory prose, a table of rates. It has no
    epigraph, no ementa, no preamble and no enacting formula, and every one of
    those must come back ``None``.

    It is the hardest of the fifteen to get right precisely because it *looks*
    structured: its page title matches the ``servico`` profile's own epigraph
    pattern, so a segmenter that scanned for the pattern itself would promote a
    heading to an epigraph, then hand Cycle 5 a document whose ``<Epigrafe>``
    is a web page's ``<h1>``. That failure is silent — the output still
    validates — which is why it is asserted here part by part rather than only
    through ``is_empty``.
    """
    matter = front(CARNE_LEAO)
    assert matter.epigraph is None
    assert matter.ementa is None
    assert matter.preamble is None
    assert matter.enacting_formula is None
    assert matter.parts == ()
    assert matter.span is None
    assert matter.hull(0) is None
    assert matter.is_empty


def test_carne_leao_epigraph_needs_metadata_to_be_suppressed() -> None:
    """Records *why* the previous test passes: deference to Cycle 2, not luck.

    ``find_epigraph`` treats ``Metadata.epigraph_index`` as authoritative
    **including when it is ``None``**. Called without metadata, the same
    document and the same profile yield a spurious ``Span(0, 0)`` — the page
    title matching the ``servico`` profile's epigraph pattern.

    Without this test, deleting the metadata branch would leave
    ``test_carne_leao_no_front_matter`` failing with no indication of which of
    two plausible mechanisms had broken. With it, the deference itself is
    pinned.
    """
    doc = styled(CARNE_LEAO)
    profile = select_profile(doc)
    assert profile.name == "servico"

    assert metadata(CARNE_LEAO).epigraph_index is None
    assert find_epigraph(doc, profile, metadata(CARNE_LEAO)) is None

    # The fallback scan, shown firing, so the value of the deference is visible.
    assert find_epigraph(doc, profile) == Span(0, 0)


def test_carne_leao_ementa_gated_by_profile() -> None:
    """A second, independent guard: the ``servico`` profile declares no ementa.

    ``ementa_absent`` short-circuits ``find_ementa`` before any pattern runs,
    so the page's first prose paragraph cannot be promoted to a summary even if
    an epigraph were somehow found above it. Defence in depth, asserted so it
    stays that way.
    """
    doc = styled(CARNE_LEAO)
    profile = select_profile(doc)
    assert profile.ementa_absent is True
    assert find_ementa(doc, profile) is None


# --------------------------------------------------------------------------
# Whole-corpus invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_all_samples_frontmatter_within_bounds(name: str) -> None:
    """Every span names real blocks of the document it was computed from.

    Spans are indices, not copies, so an out-of-range or inverted span is a
    segmentation that cannot be rendered at all — and one that would surface
    two cycles later as a confusing ``KeyError`` in the renderer rather than
    here.
    """
    doc = styled(name)
    valid = {block.index for block in doc.blocks}
    assert valid, f"{name} has no blocks"

    for part_name in PART_NAMES:
        span = getattr(front(name), part_name)
        if span is None:
            continue
        assert span.start <= span.end, f"{name}.{part_name} is inverted"
        for index in span.indices:
            assert index in valid, f"{name}.{part_name} names missing block {index}"
        # Resolvable: the span can produce its own text without raising.
        assert isinstance(span.text(doc), str)


@pytest.mark.parametrize("name", sorted(GROUND_TRUTH))
@pytest.mark.parametrize("part_name", PART_NAMES)
def test_frontmatter_matches_ground_truth(name: str, part_name: str) -> None:
    """Spec §3.4's table, one part per case, presence and absence alike.

    Parametrised per part rather than per document so a failure names exactly
    which of the sixty answers moved.
    """
    expected = GROUND_TRUTH[name][part_name]
    assert as_pair(getattr(front(name), part_name)) == expected


def test_ground_truth_covers_every_sample() -> None:
    """The table and the corpus agree, so no sample is silently unasserted."""
    assert sorted(GROUND_TRUTH) == SAMPLE_STEMS


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_front_parts_are_ordered(name: str) -> None:
    """``parts`` is document order, and the four parts never overlap.

    Ordering is what lets Cycle 5 render the parts by iterating; overlap would
    duplicate text, breaking the conservation invariant (plan §9.2) in the
    direction that is hardest to notice.
    """
    parts = front(name).parts
    starts = [span.start for span in parts]
    assert starts == sorted(starts)

    for earlier, later in zip(parts, parts[1:]):
        assert earlier.end < later.start, f"{name}: {earlier} overlaps {later}"


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_front_parts_follow_canonical_order(name: str) -> None:
    """Epigraph, then ementa, then preamble, then enacting formula.

    ``segment_front`` searches sequentially with a cursor, so this holds by
    construction — which is exactly why it is worth asserting: a future change
    to independent searching would break it silently on documents where the
    preamble rule can match a sentence inside the ementa.
    """
    matter = front(name)
    present = [
        (part_name, getattr(matter, part_name))
        for part_name in PART_NAMES
        if getattr(matter, part_name) is not None
    ]
    starts = [span.start for _, span in present]
    assert starts == sorted(starts), f"{name}: {present} is out of canonical order"


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_front_hull_covers_parts(name: str) -> None:
    """The hull is contiguous from block 0 and contains every part.

    Front matter is a *region*, not a set of scattered parts: ``parecer_93``'s
    portal stamp (blocks 0–2) and its ``NUP:``/``INTERESSADOS:``/``ASSUNTO:``
    fields (blocks 4–8) sit between the parts and are front matter by position.
    Leaving them in no part at all would break text conservation, so the hull —
    not the union — is what Cycle 5 will render from.
    """
    matter = front(name)
    hull = matter.hull(0)

    if matter.is_empty:
        assert hull is None
        return

    assert hull is not None
    assert hull.start == 0, f"{name}: hull starts at {hull.start}, not the document start"
    for span in matter.parts:
        for index in span.indices:
            assert index in hull, f"{name}: hull misses block {index}"
    assert hull.end == max(span.end for span in matter.parts)


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_is_empty_agrees_with_parts(name: str) -> None:
    """``is_empty`` summarises ``parts`` and cannot disagree with it.

    Only ``CARNE_LEAO`` is empty; the other fourteen must not be, or the "no
    false positives" test would be passing for the wrong reason.
    """
    matter = front(name)
    assert matter.is_empty == (matter.parts == ())
    assert matter.is_empty == (name == CARNE_LEAO)


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_segmentation_is_deterministic(name: str) -> None:
    """Segmenting twice gives the identical answer (plan invariant #4).

    ``FrontMatter`` and ``Span`` are frozen dataclasses, so equality is
    structural and this compares spans, not object identity.
    """
    doc = styled(name)
    profile = select_profile(doc)
    meta = metadata(name)
    first = segment_front(doc, profile, meta)
    second = segment_front(doc, profile, meta)
    assert first == second


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_epigraph_follows_metadata(name: str) -> None:
    """The epigraph is Cycle 2's ``epigraph_index``, never a second opinion.

    Amendment A-3.4's principle applied to the epigraph: one question, one
    answer. Two implementations that agree today drift apart the first time one
    of them is tuned.
    """
    expected_index = metadata(name).epigraph_index
    span = front(name).epigraph
    if expected_index is None:
        assert span is None
    else:
        assert span == Span(expected_index, expected_index)


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_front_fields_come_from_cycle_2(name: str) -> None:
    """``fields`` re-exports Cycle 2's allowlist capture rather than recomputing it.

    Amendment A-3.4. Asserted as identity of content across all 15 samples, so
    a reimplementation appearing in ``segment/`` would fail here rather than
    quietly becoming a competing source of truth.
    """
    assert front(name).fields == tuple(metadata(name).proprietary)


# --------------------------------------------------------------------------
# The finder functions on their own, outside segment_front's cursor
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_find_functions_respect_after(name: str) -> None:
    """``after=`` is exclusive: nothing is ever returned at or before it.

    ``segment_front`` chains the four searches with this parameter, so an
    off-by-one here would let a part re-match the block the previous part
    already claimed — producing overlapping spans and duplicated text.
    """
    doc = styled(name)
    profile = select_profile(doc)
    last = max((block.index for block in doc.blocks), default=0)

    for finder in (find_ementa, find_enacting_formula, find_preamble):
        for cutoff in (-1, 0, 3, last):
            span = finder(doc, profile, after=cutoff)
            if span is not None:
                assert span.start > cutoff, f"{name}: {finder.__name__} ignored after={cutoff}"


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_find_functions_never_raise(name: str) -> None:
    """Tolerance is a deliverable: no input in the corpus makes a finder throw.

    ``segment_document`` promises never to raise, and it can only keep that
    promise if the four finders keep it first.
    """
    doc = styled(name)
    profile = select_profile(doc)
    find_epigraph(doc, profile, metadata(name))
    find_ementa(doc, profile)
    find_preamble(doc, profile)
    find_enacting_formula(doc, profile)


def test_finders_tolerate_an_empty_document() -> None:
    """An empty ``StyledDoc`` yields four ``None``s and an empty ``FrontMatter``.

    Not a corpus case, but the 300+ unseen documents will include a DOCX that
    reads as nothing at all, and it must degrade gracefully rather than raise.
    """
    doc = StyledDoc(blocks=())
    profile = get_profile("generic")
    assert find_epigraph(doc, profile) is None
    assert find_ementa(doc, profile) is None
    assert find_preamble(doc, profile) is None
    assert find_enacting_formula(doc, profile) is None

    matter = segment_front(doc, profile, None)
    assert matter.is_empty
    assert matter.hull(0) is None


def test_segment_front_without_metadata_still_returns_frontmatter() -> None:
    """``metadata=None`` is legal — the epigraph then comes from the profile scan.

    Not how production calls it (see the module docstring), but the signature
    permits it and a caller doing so must get a ``FrontMatter``, not a crash.
    """
    doc = styled("ad_srf_22_19970430")
    matter = segment_front(doc, select_profile(doc), None)
    assert isinstance(matter, FrontMatter)
    assert matter.epigraph == Span(0, 0)
    assert matter.fields == ()


@pytest.mark.parametrize(
    "profile_name",
    ["parecer", "ato_declaratorio", "portaria", "jurisprudencia_generico", "servico", "generic"],
)
def test_every_profile_can_be_segmented_against(profile_name: str) -> None:
    """No profile makes the front-matter search fail, whatever it is applied to.

    Profiles gain fields as cycles land (Cycle 3 added ``enacting_res``,
    ``annex_res``, ``closing_res``); running each of the six over one real
    document is the cheapest guard against a profile registered without them.
    """
    doc = styled("port_mf_454_19770825")
    profile: DocumentProfile = get_profile(profile_name)
    matter = segment_front(doc, profile, None)
    assert isinstance(matter, FrontMatter)
