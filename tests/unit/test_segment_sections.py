"""The body/annex boundary split — and the false positive it must not make.

An annex is a *separate document* in LexML: plan §4.3 emits it as a sibling
``<LexML><Anexo>`` with its own ``!anexoN`` URN fragment. Deciding that block
*n* begins an annex therefore decides that blocks *n*..*end* leave the primary
document altogether. That asymmetry is the whole design of
:mod:`lexml_nonstat.segment.sections` and the reason these tests exist:

* a **missed** annex is recoverable — the text simply stays in the body, and a
  later cycle can still find it;
* a **false** annex silently amputates the document, and nothing downstream can
  tell that text is gone.

Cycle 3's spec §2 Q3 settled this the way amendment A-2.2 settled labelled
metadata fields: annex patterns are a per-profile field (``annex_res``), empty
for the genres that do not carry annexes. The corpus contains exactly the pair
that proves the rule is needed — ``port_mf_277``'s genuine ``ANEXO ÚNICO`` and
``sumula_stj_125``'s bare paragraph reading ``ANEXO`` inside a compilation of
court precedents with no annex at all.

Samples are loaded from the Cycle 1 ``styled`` goldens rather than re-read from
``.docx``, which keeps the file fast and makes an ingestion regression show up
as a golden diff instead of as noise here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.profile import fold, get_profile
from lexml_nonstat.segment import Annex, Span, find_annexes, segment_document

from tests.conftest import REPO_ROOT

STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"

#: Every sample in the corpus, by golden stem. Fifteen documents standing in
#: for the 300+ unseen ones, so a rule that needs all fifteen named is a rule
#: tuned to the corpus.
SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in STYLED_DIR.glob("*.json")))

#: The one sample that genuinely has an annex (spec §3.4).
ANNEXED = "port_mf_277_20180607"

#: The near-miss: a bare `ANEXO` paragraph that is *not* an annex (spec §2 Q3).
BARE_ANEXO = "sumula_stj_125"


def load(name: str) -> StyledDoc:
    """The Cycle 1 styled golden for ``name``, as a ``StyledDoc``."""
    return StyledDoc.from_json((STYLED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def segment(name: str):
    """Segment a sample the way the pipeline does — profile selected from metadata."""
    doc = load(name)
    return doc, segment_document(
        doc, metadata=extract_metadata(doc, filename=f"{name}.docx")
    )


def block_text(doc: StyledDoc, index: int) -> str:
    """The raw text of one block, for tests that must quote the source."""
    return next(b.text for b in doc.blocks if b.index == index)


def test_corpus_is_the_expected_fifteen():
    """Guards the parametrisations below against a sample being added or lost."""
    assert len(SAMPLES) == 15, SAMPLES
    assert ANNEXED in SAMPLES
    assert BARE_ANEXO in SAMPLES


# --------------------------------------------------------------------------
# The genuine annex
# --------------------------------------------------------------------------


def test_port_mf_277_annex_boundary():
    """``port_mf_277`` carries exactly one annex, and its extent is exact.

    ``ANEXO ÚNICO`` stands alone at block 6 and runs to the end of the document
    at block 137 — 132 blocks of CARF súmulas that the portaria's two articles
    give binding effect to. The ordinal is what becomes the ``!anexo1`` URN
    fragment, so it is asserted alongside the span rather than left implicit.
    """
    doc, seg = segment(ANNEXED)

    assert len(seg.annexes) == 1, [a.label for a in seg.annexes]
    annex = seg.annexes[0]

    assert annex.label == "ANEXO ÚNICO"
    assert annex.span == Span(6, 137)
    assert annex.ordinal == 1
    assert annex.fragment == "anexo1"

    # The label is the block's own text, not a normalised reconstruction.
    assert block_text(doc, 6).strip() == "ANEXO ÚNICO"
    # And the span really does reach the last block of the document.
    assert annex.span.end == max(b.index for b in doc.blocks)


def test_port_mf_277_body_excludes_annex():
    """The primary body stops before the annex begins.

    Were it not to, the annex's 132 súmulas would be emitted twice — once in
    the body and once in the ``!anexo1`` document — which breaks the text
    conservation invariant (plan §9.2) on the duplication side rather than the
    loss side.
    """
    _doc, seg = segment(ANNEXED)

    assert seg.body is not None
    assert seg.body.end < 6, seg.body
    assert seg.body == Span(3, 4)  # the portaria's two articles

    annex_indices = set(seg.annexes[0].span.indices)
    assert not annex_indices & set(seg.body.indices)


def test_annex_marker_must_be_standalone():
    """A mid-sentence mention of an annex is prose, not a boundary.

    ``port_mf_277`` block 3 reads "…relacionadas no Anexo Único desta
    Portaria…". A pattern applied anywhere in a paragraph would cut the
    document at its own Art. 1º, losing both articles. The marker rule requires
    a short standalone line, so only block 6 qualifies.
    """
    doc, seg = segment(ANNEXED)

    mention = block_text(doc, 3)
    assert "Anexo Único" in mention, mention
    assert len(mention.split()) > 5, "block 3 must stay a long prose paragraph"

    starts = [a.span.start for a in seg.annexes]
    assert starts == [6], starts


# --------------------------------------------------------------------------
# The false positive this cycle exists to avoid
# --------------------------------------------------------------------------


def test_sumula_stj_bare_anexo_not_annex():
    """THE regression test of this file (spec §2 Q3).

    ``sumula_stj_125`` block 369 is a paragraph whose text is exactly
    ``ANEXO`` — the shortest, most marker-looking line imaginable. It is not an
    annex heading: the document is a ``jurisprudencia_generico`` compilation of
    court precedents that has no annex, and 369 is an artefact of the source
    formatting.

    An ungated ``^ANEXO`` rule fires here and amputates blocks 369..396 — 28
    blocks — into a non-existent annex document. That text would vanish from
    the primary document with no downstream signal that anything was lost,
    which is precisely the failure mode profile gating prevents.
    """
    doc, seg = segment(BARE_ANEXO)

    # The hazard is real: the block genuinely reads "ANEXO".
    assert block_text(doc, 369).strip() == "ANEXO"

    assert seg.annexes == ()
    assert seg.profile == "jurisprudencia_generico"

    # And the 28 blocks that an ungated rule would have taken are still here.
    assert seg.body is not None
    assert 369 in seg.body
    assert seg.body.end == max(b.index for b in doc.blocks) == 396


def test_sumula_stj_bare_anexo_would_match_an_ungated_pattern():
    """Names the counterfactual, so the gate is not mistaken for dead code.

    Block 369 is defended **twice over**, and the two defences are worth
    keeping apart because they fail differently.

    The naive rule the plan warns about is `^ANEXO` — and it does match, which
    is what makes the hazard real: it would take blocks 369–396 out of the body
    and into a sibling annex document that does not exist.

    Neither shipped defence lets it through. `jurisprudencia_generico` declares
    no annex patterns at all (amendment A-3.3), so nothing is even tried. And
    the pattern the annex-bearing profiles *do* declare requires a qualifier —
    `ANEXO ÚNICO`, `ANEXO I`, `ANEXO 2` — so a bare `ANEXO` fails it even under
    `portaria`. Belt and braces: the gate protects genres, the qualifier
    protects against a bare marker in a genre that does carry annexes.
    """
    doc = load(BARE_ANEXO)
    marker = next(b for b in doc.paragraphs if b.index == 369).text.strip()
    assert marker == "ANEXO"

    # The hazard is real: the naive rule the plan warns about does match.
    assert re.match(r"^\s*anexo\b", fold(marker))

    # Defence 1 — the profile gate. Nothing is tried at all.
    assert get_profile("jurisprudencia_generico").annex_res == ()
    assert find_annexes(doc, get_profile("jurisprudencia_generico")) == ()

    # Defence 2 — the qualifier requirement, independent of the gate.
    portaria = get_profile("portaria")
    assert portaria.annex_res != ()
    assert not any(r.match(fold(marker)) for r in portaria.annex_res)
    assert find_annexes(doc, portaria) == ()

    # …while a qualified marker under the same profile IS found, so defence 2
    # is a real discriminator rather than a pattern that never matches.
    assert any(r.match(fold("ANEXO ÚNICO")) for r in portaria.annex_res)


def test_profile_gate_is_load_bearing_on_its_own():
    """The gate must matter even where the qualifier rule would also fire.

    Measured by mutation: deleting the qualifier requirement fails tests, but
    deleting the *gate* alone failed none — because the corpus's only stray
    marker, `sumula_stj_125` block 369, is a bare `ANEXO` that the qualifier
    catches anyway. That left amendment A-3.3's gate asserted only indirectly,
    which is how a load-bearing rule quietly becomes dead code.

    A *qualified* stray marker separates them. `ANEXO I` satisfies the
    qualifier rule, so only the profile gate can reject it — and a
    jurisprudence compilation citing `ANEXO I` of some other act is exactly
    the shape the 300+ unseen documents will contain.
    """
    blocks = tuple(
        StyledPara(inlines=(Inline(text=text),), index=index)
        for index, text in enumerate(
            [
                "SÚMULA N. 200",
                "Enunciado da súmula.",
                "ANEXO I",
                "Texto que não é um anexo desta súmula.",
            ]
        )
    )
    doc = StyledDoc(blocks=blocks, source="synthetic.docx")

    # The qualifier rule alone would accept it…
    portaria = get_profile("portaria")
    assert any(r.match(fold("ANEXO I")) for r in portaria.annex_res)
    assert [a.span.start for a in find_annexes(doc, portaria)] == [2]

    # …so only the gate keeps it out of a jurisprudence document.
    juris = get_profile("jurisprudencia_generico")
    assert juris.annex_res == ()
    assert find_annexes(doc, juris) == ()

    # End to end: the document keeps all four blocks, none amputated.
    seg = segment_document(doc, profile=juris)
    assert seg.annexes == ()
    assert seg.body is not None and 2 in seg.body and 3 in seg.body


@pytest.mark.parametrize(
    ("profile_name", "has_patterns"),
    [
        ("jurisprudencia_generico", False),
        ("servico", False),
        ("portaria", True),
        ("ato_declaratorio", True),
    ],
)
def test_annex_detection_is_profile_gated(profile_name: str, has_patterns: bool):
    """Annex patterns are declared per genre, not globally.

    Genres that do not carry annexes declare none, so no marker-shaped line in
    a súmula compilation or a service leaflet can ever cut the document. Genres
    that do carry them declare patterns and pay the recall.
    """
    profile = get_profile(profile_name)
    assert bool(profile.annex_res) is has_patterns, profile.annex_res


# --------------------------------------------------------------------------
# Ordering, numbering, and the rest of the corpus
# --------------------------------------------------------------------------


def _synthetic(lines: list[str]) -> StyledDoc:
    """A minimal ``StyledDoc`` from plain lines, one paragraph each."""
    return StyledDoc(
        blocks=tuple(
            StyledPara(inlines=(Inline(text=text),), index=i)
            for i, text in enumerate(lines)
        ),
        source="synthetic.docx",
    )


def test_annex_ordinals_sequential():
    """Two annexes number 1 and 2, and each stops where the next begins.

    The corpus has no multi-annex document, but the 300+ unseen ones will, and
    the ordinal is load-bearing: it becomes the ``!anexoN`` URN fragment, so an
    off-by-one or a shared number produces two documents claiming one URN.
    """
    doc = _synthetic(
        [
            "Portaria X, de 1 de janeiro de 2020",           # 0
            "Art. 1º Ficam aprovados os anexos.",            # 1
            "ANEXO I",                                       # 2
            "Conteúdo do primeiro anexo.",                   # 3
            "Mais conteúdo do primeiro anexo.",              # 4
            "ANEXO II",                                      # 5
            "Conteúdo do segundo anexo.",                    # 6
        ]
    )

    annexes = find_annexes(doc, get_profile("portaria"))

    assert [a.ordinal for a in annexes] == [1, 2]
    assert [a.label for a in annexes] == ["ANEXO I", "ANEXO II"]
    assert [a.span for a in annexes] == [Span(2, 4), Span(5, 6)]
    assert [a.fragment for a in annexes] == ["anexo1", "anexo2"]

    # Adjacent, non-overlapping, and reaching the end of the document.
    assert annexes[0].span.end + 1 == annexes[1].span.start
    assert annexes[-1].span.end == len(doc.blocks) - 1


def test_synthetic_annex_markers_are_gated_too():
    """The same synthetic document yields nothing under an annex-free profile."""
    doc = _synthetic(["ANEXO I", "texto", "ANEXO II", "texto"])

    assert find_annexes(doc, get_profile("jurisprudencia_generico")) == ()
    assert find_annexes(doc, get_profile("servico")) == ()


@pytest.mark.parametrize("name", [s for s in SAMPLES if s != ANNEXED])
def test_no_annex_in_remaining_samples(name: str):
    """Fourteen of the fifteen samples have no annex at all.

    This is the zero-false-positive floor: any loosening of the marker rule
    that starts cutting documents shows up here as a broad failure rather than
    as a single surprising diff.
    """
    _doc, seg = segment(name)
    assert seg.annexes == (), [(a.label, a.span) for a in seg.annexes]


@pytest.mark.parametrize("name", SAMPLES)
def test_all_samples_annexes_within_bounds(name: str):
    """Every annex span resolves to real blocks of its own document.

    A span is only indices; nothing copies text. So a span that runs past the
    last block is not caught by construction — it is caught here.
    """
    doc, seg = segment(name)
    valid = {b.index for b in doc.blocks}

    for annex in seg.annexes:
        assert isinstance(annex, Annex)
        assert annex.span.start in valid, (name, annex.span)
        assert annex.span.end in valid, (name, annex.span)
        assert set(annex.span.indices) <= valid
        assert annex.ordinal >= 1
        assert annex.label.strip()


@pytest.mark.parametrize("name", SAMPLES)
def test_annexes_are_ordered_and_disjoint(name: str):
    """Annexes come in document order, do not overlap, and number 1..n."""
    _doc, seg = segment(name)

    assert [a.ordinal for a in seg.annexes] == list(range(1, len(seg.annexes) + 1))

    seen: set[int] = set()
    previous_end = -1
    for annex in seg.annexes:
        assert annex.span.start > previous_end, (name, annex.span)
        indices = set(annex.span.indices)
        assert not indices & seen
        seen |= indices
        previous_end = annex.span.end


@pytest.mark.parametrize("name", SAMPLES)
def test_body_never_overlaps_an_annex(name: str):
    """The two partitions this module produces stay disjoint everywhere."""
    _doc, seg = segment(name)
    if seg.body is None:
        return

    body = set(seg.body.indices)
    for annex in seg.annexes:
        assert not body & set(annex.span.indices), (name, seg.body, annex.span)


# --------------------------------------------------------------------------
# Why the order of operations matters
# --------------------------------------------------------------------------


def test_signature_before_annex_still_found():
    """``port_mf_277`` signs at block 5, one block *before* its annex starts.

    This is why annexes are split **before** signatures are searched. Signature
    detection looks at the tail of the primary document; if the annex were
    still attached, that tail would be block 137 — the last CARF súmula — and
    the signer would sit 132 blocks behind the search window, inside a region
    that is not even part of this document any more.

    So the two facts are asserted together: the annex begins at 6, and the
    signer is nonetheless found at 5.
    """
    _doc, seg = segment(ANNEXED)

    assert seg.annexes[0].span.start == 6

    names = [s.name for s in seg.back.signatures]
    assert "EDUARDO REFINETTI GUARDIA" in names, names

    signer = next(s for s in seg.back.signatures if s.name == "EDUARDO REFINETTI GUARDIA")
    assert signer.span == Span(5, 5)
    assert signer.span.end < seg.annexes[0].span.start


def test_signature_is_not_inside_the_annex():
    """No detected signature may fall inside an annex's span.

    A signature found at block 130 of ``port_mf_277`` would mean the tail
    search ran against the annex — the exact failure the ordering prevents.
    """
    for name in SAMPLES:
        _doc, seg = segment(name)
        annex_indices = {i for a in seg.annexes for i in a.span.indices}
        for signature in seg.back.signatures:
            assert not set(signature.span.indices) & annex_indices, (
                name,
                signature.name,
                signature.span,
            )
