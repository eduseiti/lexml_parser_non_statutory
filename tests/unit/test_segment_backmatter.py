"""Back matter: what makes a line a signature, and what merely looks like one.

Spec §6 measures the risk this file exists to hold down: a bare ALL-CAPS rule
scores **six false positives against ten true signatures** on this corpus.
Signatures here are short ALL-CAPS standalone lines near the end of a document,
and so are ``ACÓRDÃO``, ``CONCLUSÃO``, ``ORDEM DE INTIMAÇÃO``,
``ADVOCACIA-GERAL DA UNIÃO``, ``ACÓRDÃOS PARADIGMAS`` and
``COORDENADOR-GERAL DA COSIT``. Shape alone cannot separate them, so
:func:`looks_like_person_name` adds a vocabulary of institution, office and
heading words and demands every non-connective word fall outside it.

Four things are pinned here that nothing else in the suite would notice:

1. **The discriminator itself** (:func:`test_person_name_discriminator`). It is
   parametrised over all 24 strings the implementation was prototyped against,
   each with its expected verdict, so the vocabulary cannot be relaxed —
   nor tightened — without a named test naming the string that moved. The
   accept list is every real signer in the corpus; the reject list is every
   measured false positive plus ``par_cosit_26``'s quoted ementa headline.
2. **Reported dates are not closings** (:func:`test_reported_judgment_date_is_not_a_closing`).
   ``sumula_stj_125`` carries seven ``… (data do julgamento).`` lines — the
   judgment dates of the *precedents it compiles*, not its own closing. Reading
   the last of them (block 344 of 397) as the súmula's closing truncates the
   document 53 blocks early. The profile's ``closing_res`` matches all seven;
   only the ``_REPORTED_DATE_RES`` veto rejects them.
3. **Every signature is kept, in document order** (Q4). ``pn_cst_38`` signs
   twice and both signers carry an office; suppressing either loses text and
   breaks the conservation invariant (plan §9.2).
4. **Zero false positives on unsigned documents.** ``CARNE_LEAO``,
   ``sumula_carf_42``, ``sumula_stj_125`` and ``REsp_1306393`` are the four
   anchors: a document with no signer must yield ``()``, not a plausible guess.

Counts are asserted per sample across all 15 rather than only on the signed
ones, because a discriminator regression shows up as a *count* change on an
unsigned sample long before it changes a name on a signed one.

Samples load from Cycle 1's committed ``tests/golden/styled/*.json`` dumps
rather than from the ``.docx`` files: deterministic, fast, and it keeps this
file measuring the segmenter instead of re-measuring the reader (which
``tests/golden/test_styled_goldens.py`` already owns).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc
from lexml_nonstat.model import UrnDate, extract_metadata
from lexml_nonstat.profile import get_profile, select_profile
from lexml_nonstat.segment import (
    BackMatter,
    Signature,
    Span,
    find_signatures,
    looks_like_person_name,
    segment_back,
    segment_document,
)
from lexml_nonstat.segment.backmatter import is_closing_line, split_trailing_qualifier

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"

#: Sorted so parametrised ids are stable and readable.
SAMPLE_STEMS = sorted(p.stem for p in STYLED_DIR.glob("*.json"))

CARNE_LEAO = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"


# --------------------------------------------------------------------------
# Loading
#
# 15 samples x a dozen parametrised tests would re-segment well over a hundred
# times; both caches are module-scoped, keeping this file to a second or two.
# --------------------------------------------------------------------------

_DOC_CACHE: dict[str, StyledDoc] = {}
_BACK_CACHE: dict[str, BackMatter] = {}


def styled(name: str) -> StyledDoc:
    """Load a sample from Cycle 1's golden rather than re-parsing the DOCX."""
    if name not in _DOC_CACHE:
        _DOC_CACHE[name] = StyledDoc.from_json(
            (STYLED_DIR / f"{name}.json").read_text(encoding="utf-8")
        )
    return _DOC_CACHE[name]


def back(name: str) -> BackMatter:
    """The whole-document back matter, exactly as production computes it.

    Via :func:`segment_document`, not :func:`segment_back` directly, because
    the search window is bounded by the front matter and by any annex — and
    ``port_mf_277`` signs at block 5 with its ``ANEXO ÚNICO`` starting at
    block 6. Testing the unbounded call would not exercise that ordering.
    """
    if name not in _BACK_CACHE:
        doc = styled(name)
        seg = segment_document(
            doc, metadata=extract_metadata(doc, filename=f"{name}.docx")
        )
        _BACK_CACHE[name] = seg.back
    return _BACK_CACHE[name]


def sole(name: str) -> Signature:
    """The one signature of a singly-signed sample, asserting it is the only one."""
    signatures = back(name).signatures
    assert len(signatures) == 1, f"{name}: expected 1 signature, got {len(signatures)}"
    return signatures[0]


# --------------------------------------------------------------------------
# Ground truth (spec §3.4, verified against the implementation)
# --------------------------------------------------------------------------

#: The ten real signers in the corpus. Every one must be accepted, and the
#: ``adn_cst_10`` entry is deliberately the *raw* source line, name and office
#: run together on one paragraph, because that is the form the discriminator
#: actually receives.
NAME_ACCEPT = (
    "CARLOS ALBERTO DE NIZA E CASTRO",
    "JIMIR S. DONIAK",
    "EVERARDO MACIEL",
    "MÁRCIA CRISTINA NOVAIS LABANCA",
    "JOSEFA MARIA COELHO MARQUES Em exercício",
    "ADRIANA QUEIROZ DE CARVALHO",
    "LUÍS INÁCIO LUCENA ADAMS",
    "MÁRIO HENRIQUE SIMONSEN",
    "CARLOS ERVINO GULYAS",
    "EDUARDO REFINETTI GUARDIA",
)

#: The measured false positives of a naive ALL-CAPS rule, plus the headings and
#: institution names that share their shape. The first entry is
#: ``par_cosit_26`` block 33 — a quoted ementa transcribed into the body, whose
#: every word is *unknown* to the institution vocabulary and which is therefore
#: rejected on the opening-quote rule alone.
NAME_REJECT = (
    "“INCIDÊNCIA DO IRRF. CESSÃO DE PRECATÓRIOS.",
    "ADVOCACIA-GERAL DA UNIÃO",
    "ACÓRDÃO",
    "CONCLUSÃO",
    "ORDEM DE INTIMAÇÃO",
    "COORDENADOR-GERAL DA COSIT",
    "CONSULTORIA-GERAL DA UNIÃO",
    "ACÓRDÃOS PARADIGMAS",
    "ADVOGADA DA UNIÃO",
    "ANEXO ÚNICO",
    "MINISTÉRIO DA FAZENDA",
    "EMENTA",
    "SÚMULA N. 125",
    "DOMICÍLIO FISCAL",
)

#: sample -> the signer names expected, in document order. The four samples
#: mapped to ``()`` are the zero-false-positive anchors.
EXPECTED_NAMES: dict[str, tuple[str, ...]] = {
    "ad_pgfn_13_20111220": ("ADRIANA QUEIROZ DE CARVALHO",),
    "ad_pgfn_3_20080918": ("LUÍS INÁCIO LUCENA ADAMS",),
    "ad_srf_22_19970430": ("EVERARDO MACIEL",),
    "ad_srf_3_19990107": ("EVERARDO MACIEL",),
    "adn_cosit_19_20001025": ("CARLOS ALBERTO DE NIZA E CASTRO",),
    "adn_cst_10_19910417": ("JOSEFA MARIA COELHO MARQUES",),
    "par_cosit_26_20000629": ("CARLOS ALBERTO DE NIZA E CASTRO",),
    "parecer_93_2018_decor_cgu_agu": ("MÁRCIA CRISTINA NOVAIS LABANCA",),
    "pn_cst_38_19801031": ("CARLOS ERVINO GULYAS", "JIMIR S. DONIAK"),
    "port_mf_277_20180607": ("EDUARDO REFINETTI GUARDIA",),
    "port_mf_454_19770825": ("MÁRIO HENRIQUE SIMONSEN",),
    "REsp_1306393": (),
    "sumula_carf_42": (),
    "sumula_stj_125": (),
    CARNE_LEAO: (),
}

#: The eleven samples that carry a signature, with the block the signer's own
#: name sits on. The span may start earlier (a closing date) or end later (an
#: office line); this is the name's block, which is the anchor the whole
#: detection hangs from.
SIGNED = {
    "ad_pgfn_13_20111220": 6,
    "ad_pgfn_3_20080918": 5,
    "ad_srf_22_19970430": 4,
    "ad_srf_3_19990107": 6,
    "adn_cosit_19_20001025": 4,
    "adn_cst_10_19910417": 7,
    "par_cosit_26_20000629": 101,
    "parecer_93_2018_decor_cgu_agu": 428,
    "pn_cst_38_19801031": 80,
    "port_mf_277_20180607": 5,
    "port_mf_454_19770825": 19,
}

UNSIGNED = tuple(name for name, names in EXPECTED_NAMES.items() if not names)


def test_ground_truth_covers_every_sample():
    """A new sample must arrive with an expected signature count, not silently.

    Without this the ×15 parametrised tests below would quietly shrink to ×15
    of whatever the golden directory happens to hold.
    """
    assert len(SAMPLE_STEMS) == 15
    assert sorted(EXPECTED_NAMES) == SAMPLE_STEMS


# --------------------------------------------------------------------------
# 1. The discriminator — the core of this file
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [(t, True) for t in NAME_ACCEPT] + [(t, False) for t in NAME_REJECT],
    ids=[f"accept-{t[:28]}" for t in NAME_ACCEPT]
    + [f"reject-{t[:28]}" for t in NAME_REJECT],
)
def test_person_name_discriminator(text: str, expected: bool):
    """All 24 prototyped strings: 10 people accepted, 14 non-people rejected.

    This is the test the cycle's highest-likelihood risk (spec §6, "signature
    heuristic over-fires on institution names") is discharged by. Both
    directions matter and both are asserted from one table: loosening the
    vocabulary re-admits ``COORDENADOR-GERAL DA COSIT``, tightening it drops a
    real signer — and dropping a signer is the *silent* error, since the name
    simply never appears in the output.
    """
    assert looks_like_person_name(text) is expected


def test_discriminator_ratio_is_the_measured_one():
    """10 accepts, 14 rejects — the counts spec §2 records as verified.

    Asserted as counts as well as per-string so that adding a case to one list
    without moving it from the other is caught.
    """
    assert sum(looks_like_person_name(t) for t in NAME_ACCEPT) == 10
    assert sum(looks_like_person_name(t) for t in NAME_REJECT) == 0


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_discriminator_rejects_blank(text: str):
    """Blank paragraphs are kept by the reader as separators, so they arrive here."""
    assert looks_like_person_name(text) is False


def test_discriminator_rejects_lowercase_prose():
    """A signature is ALL-CAPS in this corpus; ordinary prose never qualifies."""
    assert looks_like_person_name("Carlos Alberto de Niza e Castro") is False
    assert looks_like_person_name("o interessado requer a restituição") is False


def test_discriminator_rejects_single_word():
    """One word is a heading (``EMENTA``, ``CONCLUSÃO``), never a full name."""
    assert looks_like_person_name("MACIEL") is False


def test_discriminator_rejects_digits():
    """A digit run marks a number or a code — a process number, never a person."""
    assert looks_like_person_name("PROCESSO 10768 000123 2000 11") is False
    assert looks_like_person_name("NUP 00688 000123 2018 21") is False


def test_discriminator_rejects_long_lines():
    """Beyond a handful of words a line is a sentence, whatever its case."""
    long_caps = "TODO AQUELE QUE RECEBER RENDIMENTOS DE PESSOA FISICA FICA OBRIGADO"
    assert looks_like_person_name(long_caps) is False


# --------------------------------------------------------------------------
# 2-5. Signatures found on the real corpus
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SIGNED))
def test_signature_all_signed_samples(name: str):
    """Each of the 11 signed samples yields its expected signer names, in order.

    The whole point of the discriminator is recall as well as precision; the
    unsigned samples below prove the precision half, this proves the recall.
    """
    found = tuple(s.name for s in back(name).signatures)
    assert found == EXPECTED_NAMES[name]


@pytest.mark.parametrize("name", sorted(SIGNED))
def test_signature_name_block_is_the_expected_one(name: str):
    """The signer's name sits on the block §3.4 says it does.

    Names alone would pass even if the segmenter found the right text in the
    wrong place — and a span in the wrong place moves text between parts.
    """
    signature = back(name).signatures[0]
    assert SIGNED[name] in signature.span, (
        f"{name}: block {SIGNED[name]} not inside {signature.span}"
    )


def test_parecer_93_two_signature_region():
    """``parecer_93``: one recoverable signature, plus a trailing span for the rest.

    Q4 decided that every signature block is kept, and ``parecer_93`` carries
    two signature *regions*: the parecer's own (blocks 428-430 — closing date,
    name, ``ADVOGADA DA UNIÃO``) and an appended ``DESPACHO DO CONSULTOR-GERAL
    DA UNIÃO`` with its own header, NUP and date at blocks 431-449.

    Only one of the two is *recoverable as a signature*, because the despacho's
    signer has no name in the source at all: block 448, where the name would
    sit, is blank. There is nothing for :func:`looks_like_person_name` to
    accept, and fabricating a signer from the surrounding office line would be
    exactly the "no fabricated structure" violation the plan forbids (§9.2).

    What conserves that text is ``back.trailing``: the despacho's 19 blocks are
    claimed by the back matter as trailing content rather than stranded outside
    every part. So the assertion is one signature *and* a non-empty trailing
    span — the pair is what makes losing nothing checkable by arithmetic.
    """
    result = back("parecer_93_2018_decor_cgu_agu")
    assert len(result.signatures) == 1
    signature = result.signatures[0]
    assert signature.name == "MÁRCIA CRISTINA NOVAIS LABANCA"
    assert signature.cargo == "ADVOGADA DA UNIÃO"
    assert signature.local_date == "Brasília, 19 de dezembro de 2018."
    assert signature.date == UrnDate(2018, 12, 19)
    assert signature.span == Span(428, 430)

    # The appended DESPACHO, conserved rather than signed.
    assert result.trailing is not None
    assert result.trailing.start == 431
    assert result.trailing.end >= 449
    assert "DESPACHO" in result.trailing.text(styled("parecer_93_2018_decor_cgu_agu"))


def test_pn_cst_38_two_signatures():
    """``pn_cst_38`` signs twice, and both are kept in document order (Q4).

    The author signs first with the closing date, the coordinator approves
    below. Suppressing either would lose text; picking one is a rendering
    decision, and rendering is Cycles 5 and 6.
    """
    signatures = back("pn_cst_38_19801031").signatures
    assert len(signatures) == 2
    first, second = signatures

    assert first.name == "CARLOS ERVINO GULYAS"
    assert first.cargo == "Fiscal de Tributos Federais"
    assert second.name == "JIMIR S. DONIAK"
    assert second.cargo == "Coordenador do Sistema de Tributação"

    assert first.span.end < second.span.start


def test_cargo_captured():
    """Office lines are captured in all three shapes the corpus uses.

    ``parecer_93`` puts the office on its own ALL-CAPS line below the name;
    ``pn_cst_38`` uses a mixed-case one; ``adn_cst_10`` runs it onto the name's
    own line. All three must land in ``cargo`` — a cargo mistaken for a name is
    a false signature, and a cargo dropped is lost text.
    """
    assert sole("parecer_93_2018_decor_cgu_agu").cargo == "ADVOGADA DA UNIÃO"
    assert (
        back("pn_cst_38_19801031").signatures[0].cargo == "Fiscal de Tributos Federais"
    )
    assert sole("adn_cst_10_19910417").cargo == "Em exercício"


def test_cargo_is_none_when_absent():
    """``ad_srf_22`` signs with a bare name — an absent office stays ``None``.

    Optional means optional: inventing a cargo from the next line would fold
    body prose into the signature.
    """
    assert sole("ad_srf_22_19970430").cargo is None
    assert sole("ad_pgfn_13_20111220").cargo is None


def test_adn_cst_10_name_and_office_share_a_line():
    """``adn_cst_10`` block 7 is one paragraph: ``NOME Em exercício``.

    Word ran the qualifier onto the signature line, so the name is
    unrecoverable without splitting it off — and the *un*split line must still
    be recognised as a person, or the whole signature is lost. Both halves are
    asserted: the split function directly, and the segmentation that depends
    on it.
    """
    assert split_trailing_qualifier("JOSEFA MARIA COELHO MARQUES Em exercício") == (
        "JOSEFA MARIA COELHO MARQUES",
        "Em exercício",
    )

    signature = sole("adn_cst_10_19910417")
    assert signature.name == "JOSEFA MARIA COELHO MARQUES"
    assert signature.cargo == "Em exercício"
    assert signature.span == Span(7, 7)


def test_split_trailing_qualifier_leaves_plain_names_alone():
    """No qualifier means no split, and no stray ``None`` handling downstream."""
    assert split_trailing_qualifier("EVERARDO MACIEL") == ("EVERARDO MACIEL", None)
    assert split_trailing_qualifier("  EVERARDO MACIEL  ") == ("EVERARDO MACIEL", None)


@pytest.mark.parametrize(
    "qualifier",
    ["Em exercício", "em exercicio", "Substituto", "Substituta", "Interino"],
)
def test_split_trailing_qualifier_variants(qualifier: str):
    """The qualifier vocabulary is case- and accent-tolerant.

    These are Word artifacts, so their casing is whatever the author typed.
    """
    name, found = split_trailing_qualifier(f"FULANO DE TAL {qualifier}")
    assert name == "FULANO DE TAL"
    assert found == qualifier


# --------------------------------------------------------------------------
# 7-9. Closing lines and their dates
# --------------------------------------------------------------------------


def test_local_date_closing():
    """The two corpus closings are captured verbatim, punctuation included.

    ``Brasília, 19 de dezembro de 2018.`` and ``CST, em 30 de outubro de 1980``
    differ in city form, in the ``em`` connective and in the trailing period.
    Asserting the exact strings keeps the closing pattern from being narrowed
    to whichever one the implementation was last tuned against.
    """
    assert (
        sole("parecer_93_2018_decor_cgu_agu").local_date
        == "Brasília, 19 de dezembro de 2018."
    )
    assert (
        back("pn_cst_38_19801031").signatures[0].local_date
        == "CST, em 30 de outubro de 1980"
    )


def test_local_date_parsed():
    """A captured closing yields a real ``UrnDate``, not just a string.

    The string alone would satisfy conservation while leaving the date useless
    to the URN; parsing it is what makes the closing evidence rather than text.
    """
    assert sole("parecer_93_2018_decor_cgu_agu").date == UrnDate(2018, 12, 19)
    assert back("pn_cst_38_19801031").signatures[0].date == UrnDate(1980, 10, 30)


def test_no_local_date_leaves_date_none():
    """Most samples carry no closing at all; that must read as ``None``.

    Never as the filename date or the epigraph date — the signature's date is
    a claim about the signature, and a borrowed one would be a fabrication.
    """
    signature = sole("ad_srf_22_19970430")
    assert signature.local_date is None
    assert signature.date is None


def test_reported_judgment_date_is_not_a_closing():
    """A reported proceeding's date is not this document's closing.

    ``sumula_stj_125`` compiles court precedents, and each carries a line
    ``Brasília (DF), <data> (data do julgamento).`` — seven of them. Every one
    matches the profile's ``closing_res`` on shape: city, comma, date. The
    ``(data do julgamento)`` parenthetical is the only thing separating them
    from a real closing.

    Without the veto the last of the seven, at block 344 of 397, is read as the
    súmula's closing and the body is **truncated 53 blocks early** — 53 blocks
    of precedent text silently dropped from a document that is nothing but
    precedents.

    The counter-example is asserted alongside it, on the ``parecer`` profile,
    so the veto cannot be "fixed" by rejecting closings outright.
    """
    jurisprudencia = get_profile("jurisprudencia_generico")
    parecer = get_profile("parecer")

    reported = "Brasília (DF), 19 de setembro de 1994 (data do julgamento)."
    assert is_closing_line(reported, jurisprudencia) is False
    assert is_closing_line("Brasília, 19 de dezembro de 2018.", parecer) is True


def test_reported_date_shape_would_otherwise_match():
    """The veto is doing the work, not the closing pattern's own strictness.

    If ``closing_res`` stopped matching the judgment lines for some unrelated
    reason, the test above would pass for the wrong reason and the veto could
    be deleted unnoticed. So: the raw pattern matches all seven, and
    :func:`is_closing_line` rejects all seven.
    """
    doc = styled("sumula_stj_125")
    profile = select_profile(doc)
    judgment_lines = [
        p.text.strip() for p in doc.paragraphs if "data do julgamento" in p.text
    ]
    assert len(judgment_lines) == 7

    assert all(
        any(r.match(text) for r in profile.closing_res) for text in judgment_lines
    )
    assert not any(is_closing_line(text, profile) for text in judgment_lines)


def test_reported_date_veto_covers_publication_and_session():
    """``(data da publicação)`` and ``(data da sessão)`` are reported dates too.

    The corpus only exhibits ``julgamento``, but the same parenthetical
    convention names the other two, and the 300+ unseen documents will carry
    them. Genre-agnostic evidence over sample-specific literals (plan §12).
    """
    profile = get_profile("jurisprudencia_generico")
    for parenthetical in ("data da publicação", "data da sessão", "data da sessao"):
        text = f"Brasília (DF), 19 de setembro de 1994 ({parenthetical})."
        assert is_closing_line(text, profile) is False


# --------------------------------------------------------------------------
# 10-12. Zero false positives
# --------------------------------------------------------------------------


def test_carne_leao_no_signature():
    """``CARNE_LEAO`` is a service page: no front matter, no back matter, no signer.

    One of the cycle's two zero-false-positive anchors (spec §3.4, exit
    criterion 2). It is a bare document, so *anything* the segmenter reports
    here is invented.
    """
    result = back(CARNE_LEAO)
    assert result.is_empty
    assert result.signatures == ()
    assert result.local_date is None


def test_sumula_stj_no_signature():
    """``sumula_stj_125`` is unsigned — the ministers named in it are not signers.

    The document is dense with ALL-CAPS headings and with ``O Sr. Ministro …``
    lines. Every one must be rejected.
    """
    assert back("sumula_stj_125").signatures == ()


@pytest.mark.parametrize("name", sorted(UNSIGNED))
def test_unsigned_samples_yield_nothing(name: str):
    """All four unsigned samples: ``signatures == ()``, no near misses."""
    assert back(name).signatures == ()


def test_institution_lines_rejected():
    """Institution and heading lines are never signatures, on strings or on samples.

    Asserted twice over, because the two failure modes are different: the
    discriminator can regress in isolation, and the surrounding search can
    regress by widening its window until it reaches lines the discriminator
    never sees.

    The sample half's sharpest case is ``par_cosit_26`` block 33, a quoted
    ementa transcribed into the body: ``“INCIDÊNCIA DO IRRF. CESSÃO DE
    PRECATÓRIOS.`` Every one of its words is unknown to the institution
    vocabulary, so the vocabulary alone cannot reject it — only the opening
    quotation mark does. The sample must yield exactly one signature, not two.
    """
    for text in NAME_REJECT:
        assert not looks_like_person_name(text), f"false positive: {text!r}"

    doc = styled("par_cosit_26_20000629")
    assert doc.blocks[33].text.strip().startswith("“INCIDÊNCIA DO IRRF")

    # Unbounded search over the whole document, so block 33 is inside the
    # window — the bounded production call would not even look at it.
    signatures = find_signatures(doc, select_profile(doc))
    assert len(signatures) == 1
    assert signatures[0].name == "CARLOS ALBERTO DE NIZA E CASTRO"


def test_advocacia_geral_banner_not_signed():
    """``parecer_93``'s institutional banner sits above its epigraph, in caps.

    ``ADVOCACIA-GERAL DA UNIÃO`` / ``CONSULTORIA-GERAL DA UNIÃO`` would be two
    extra "signatures" under a naive rule, at the very top of the document.
    """
    doc = styled("parecer_93_2018_decor_cgu_agu")
    signatures = find_signatures(doc, select_profile(doc))
    names = {s.name for s in signatures}
    assert "ADVOCACIA-GERAL DA UNIÃO" not in names
    assert "CONSULTORIA-GERAL DA UNIÃO" not in names


# --------------------------------------------------------------------------
# 13-14. Whole-corpus invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_signature_count_all_samples(name: str):
    """Every sample's signature count, asserted exactly (spec §3.4).

    Counts across all 15 — signed and unsigned alike — are the cheapest place
    a discriminator change shows up. A vocabulary word removed adds a count on
    an unsigned sample; one added drops a count on a signed one.
    """
    assert len(back(name).signatures) == len(EXPECTED_NAMES[name])


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_signatures_in_document_order(name: str):
    """Signature spans are strictly increasing and never overlap.

    Q4 keeps every block, so order is what makes "the parecer's own signature
    then the despacho's" meaningful. Overlap would mean one block counted in
    two signatures — text duplication, which the conservation invariant
    (plan §9.2) forbids as firmly as text loss.
    """
    spans = [s.span for s in back(name).signatures]
    for previous, current in zip(spans, spans[1:]):
        assert previous.end < current.start, (
            f"{name}: {previous} overlaps or follows {current}"
        )


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_signature_spans_resolve_to_real_blocks(name: str):
    """Every span index addresses a block that exists in the document.

    Spans are indices, not copies, so an index outside the document is an
    unresolvable reference: it would surface as missing text in Cycle 5/6's
    rendering, far from the cause.
    """
    doc = styled(name)
    indices = {b.index for b in doc.blocks}
    for signature in back(name).signatures:
        assert set(signature.span.indices) <= indices


@pytest.mark.parametrize("name", sorted(SIGNED))
def test_signature_name_appears_in_its_span_text(name: str):
    """The name reported is text actually present in the span it points at.

    This is the conservation invariant at signature level: a name is evidence
    read off the document, never a value synthesised from the metadata.
    """
    for signature in back(name).signatures:
        assert signature.name in signature.span.text(styled(name))


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_is_empty_agrees_with_contents(name: str):
    """``is_empty`` summarises the parts; it must not drift from them.

    A ``BackMatter`` reporting empty while holding a signature would make the
    body/back boundary silently wrong for every consumer that trusts the flag.
    """
    result = back(name)
    parts = (result.signatures, result.local_date, result.trailing)
    assert result.is_empty == (not any(parts))


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_segmentation_is_deterministic(name: str):
    """Segmenting the same document twice gives the identical back matter.

    Determinism is a cross-cutting invariant (plan §9.2). Dict and set
    iteration inside the search are the plausible ways it could be lost.
    """
    doc = styled(name)
    metadata = extract_metadata(doc, filename=f"{name}.docx")
    first = segment_document(doc, metadata=metadata).back
    second = segment_document(doc, metadata=metadata).back
    assert first == second


@pytest.mark.parametrize("name", SAMPLE_STEMS)
def test_segment_back_never_raises_without_metadata(name: str):
    """``segment_back`` is total: any document, any profile, no exception.

    Spec §3.2 — a document with no back matter yields an empty ``BackMatter``,
    which is a result, not a failure. Called here with the default whole-file
    window, the widest input it can receive.
    """
    doc = styled(name)
    result = segment_back(doc, select_profile(doc))
    assert isinstance(result, BackMatter)


def test_within_window_bounds_the_search():
    """``within`` genuinely restricts the search, rather than being advisory.

    The ordering that depends on it is real: ``port_mf_277`` signs at block 5
    and its ``ANEXO ÚNICO`` opens at block 6, so production narrows the window
    to the primary body before searching. A window that excluded the signer
    must therefore find nothing — and one that includes it must find him.
    """
    doc = styled("port_mf_277_20180607")
    profile = select_profile(doc)

    assert find_signatures(doc, profile, within=Span(0, 4)) == ()

    found = find_signatures(doc, profile, within=Span(0, 5))
    assert [s.name for s in found] == ["EDUARDO REFINETTI GUARDIA"]


def test_signature_found_although_an_annex_follows():
    """``port_mf_277``'s signer survives the annex split (spec §6, last risk).

    Signed at block 5 of 138, with the annex taking blocks 6 onward. Search the
    file's tail — the obvious implementation — and the signer is 130 blocks
    behind the window, buried inside the annex. Asserted through
    :func:`segment_document`, which is where that ordering lives.
    """
    signature = sole("port_mf_277_20180607")
    assert signature.name == "EDUARDO REFINETTI GUARDIA"
    assert signature.span == Span(5, 5)
