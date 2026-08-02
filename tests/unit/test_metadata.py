"""Metadata extraction is honest about what it found, and about where.

This file pins four things that spec §2.1's ratified decisions bought, and
which nothing else in the suite would notice if they regressed:

1. **Provenance, not just values** (decision #1). ``parecer_93``'s date is
   ``2018-12-28``, but that date is *not* on its epigraph — it is a bare header
   stamp at block 0, while the document was signed on 19/12/2018 and the
   approving despacho is dated 27/12. Asserting only the date would leave the
   whole precedence chain free to shuffle. So ``date_source`` is asserted
   alongside every date: ``header`` for ``parecer_93``, ``epigraph`` for
   ``port_mf_277``. Those two assertions are the ordering.
2. **Best-effort URNs, never exceptions** (decision #2). Four of the fifteen
   samples carry no authority+type+number+date quadruple. They must still yield
   a syntactically valid URN *and* report ``complete is False`` with an exact
   ``missing`` list — a valid-looking URN built on sentinels is only safe while
   something says so out loud.
3. **The filename is a last resort, not a source** (decision #3).
   :func:`test_filename_fallback_only_when_needed` feeds ``port_mf_277`` a
   filename dated 1901 and demands the epigraph still win. A test that only
   showed the fallback *works* would pass just as happily if the fallback ran
   first and clobbered every in-document date in the corpus.
4. **Zero proprietary-field false positives** (decision #4). This is the
   regression the cycle exists to prevent: without the allowlist,
   ``sumula_stj_125`` captures ``Some-se:``, ``O Sr. Ministro Garcia Vieira:``
   and seven ``Advogados:`` lines — ministers' prose filed as document
   metadata. Silent corruption, invisible in a URN.

Samples are loaded from Cycle 1's committed ``tests/golden/styled/*.json``
dumps rather than from the ``.docx`` files: deterministic, and it keeps this
file measuring the extractor instead of re-measuring the reader (which
``tests/golden/test_styled_goldens.py`` already owns). ``filename=`` is passed
on every call so the fallback path is exercised exactly as production does.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara
from lexml_nonstat.model import (
    METADATA_SOURCE_URI,
    Metadata,
    UrnDate,
    extract_metadata,
    is_valid_urn,
    parse_pt_date,
)
from lexml_nonstat.validate import validate

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLED_DIR = REPO_ROOT / "tests" / "golden" / "styled"
LEXML_NS = "http://www.lexml.gov.br/1.0"

#: Sorted so parametrised ids are stable and readable.
SAMPLE_STEMS = sorted(p.stem for p in STYLED_DIR.glob("*.json"))

#: The four samples that legitimately carry no full identity (decision #2),
#: mapped to the exact gaps each has. Exact, not merely non-empty: "missing is
#: truthy" would stay green if the extractor started losing numbers too.
INCOMPLETE = {
    "sumula_carf_42": ("date",),
    "sumula_stj_125": ("date",),
    "REsp_1306393": ("date",),
    "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO": ("number", "date"),
}

# --------------------------------------------------------------------------
# Loading
#
# 15 samples x 5 parametrised tests would re-parse and re-extract dozens of
# times; both caches are module-scoped, keeping the file to a second or two.
# --------------------------------------------------------------------------

_DOC_CACHE: dict[str, StyledDoc] = {}
_META_CACHE: dict[str, Metadata] = {}


def styled_doc(stem: str) -> StyledDoc:
    """A sample as Cycle 1 committed it — no DOCX parsing involved."""
    if stem not in _DOC_CACHE:
        _DOC_CACHE[stem] = StyledDoc.from_json(
            (STYLED_DIR / f"{stem}.json").read_text(encoding="utf-8")
        )
    return _DOC_CACHE[stem]


def meta(stem: str) -> Metadata:
    """Metadata for a sample, extracted the way the pipeline extracts it."""
    if stem not in _META_CACHE:
        _META_CACHE[stem] = extract_metadata(styled_doc(stem), filename=f"{stem}.docx")
    return _META_CACHE[stem]


def test_samples_are_present():
    """Guards the guard: parametrising over an empty glob is 0 silent passes."""
    assert len(SAMPLE_STEMS) == 15, f"expected 15 styled goldens, found {SAMPLE_STEMS}"


# --------------------------------------------------------------------------
# 1. The two documents the plan names, field by field
# --------------------------------------------------------------------------


def test_parecer_93_metadata():
    """Plan §8's ``parecer_93`` expectation, with its provenance attached.

    ``date_source == "header"`` is the load-bearing assertion here (spec §2.1
    decision #1). The epigraph ``PARECER n. 00093/2018/DECOR/CGU/AGU`` yields
    only the year 2018; the full ``28/12/2018`` comes from the bare stamp at
    block 0, and the chain is allowed to *refine* a year-only epigraph date
    only when the finer source agrees on the year. Assert the date alone and
    that whole rule is free to change unnoticed.
    """
    m = meta("parecer_93_2018_decor_cgu_agu")

    assert m.profile == "parecer"
    assert m.authority == "advocacia.geral.uniao"
    assert m.authority_source == "epigraph"
    assert m.doc_type == "parecer"
    assert m.number == "93"  # from "00093/2018", leading zeros stripped
    assert m.date == UrnDate(2018, 12, 28)
    assert m.date_source == "header"
    assert m.epigraph == "PARECER n. 00093/2018/DECOR/CGU/AGU"
    assert m.locality == "br"
    assert m.urn == "urn:lex:br:advocacia.geral.uniao:parecer:2018-12-28;93"
    assert m.complete is True
    assert m.missing == ()


def test_port_mf_277_metadata():
    """Plan §8's ``port_mf_277`` expectation — the well-behaved case.

    Everything comes off one epigraph line, ``PORTARIA MF nº 277, de 7 de junho
    de 2018``: the sigla ``MF`` gives the authority, the number and the date.
    ``date_source == "epigraph"`` is what distinguishes this from ``parecer_93``
    and is the other half of decision #1's ordering.
    """
    m = meta("port_mf_277_20180607")

    assert m.profile == "portaria"
    assert m.authority == "ministerio.fazenda"
    assert m.authority_source == "epigraph"
    assert m.doc_type == "portaria"
    assert m.number == "277"
    assert m.date == UrnDate(2018, 6, 7)
    assert m.date_source == "epigraph"
    assert m.locality == "br"
    assert m.urn == "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277"
    assert m.complete is True
    assert m.missing == ()


# --------------------------------------------------------------------------
# 2. The primitives: dates and numbers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # The four forms the corpus actually writes dates in.
        pytest.param("28/12/2018", UrnDate(2018, 12, 28), id="dd/mm/yyyy"),
        pytest.param("7 de junho de 2018", UrnDate(2018, 6, 7), id="por-extenso"),
        pytest.param(
            "1º de dezembro de 2008", UrnDate(2008, 12, 1), id="ordinal-primeiro"
        ),
        pytest.param("2018-06-07", UrnDate(2018, 6, 7), id="iso"),
        # Year-only is a first-class result, not a degraded one: pn_cst_38
        # (1980) is cited by year in practice, and UrnDate models exactly that.
        pytest.param("de 1980", UrnDate(1980), id="year-only"),
        # A real line from a signature block, matched inside surrounding text.
        pytest.param(
            "Brasília, 19 de dezembro de 2018",
            UrnDate(2018, 12, 19),
            id="signature-line",
        ),
        # No date: None rather than an exception, so callers can chain
        # fallbacks with plain `or`-style logic instead of try/except.
        pytest.param("PORTARIA MF", None, id="junk-no-digits"),
        pytest.param("nada de nada", None, id="junk-with-de"),
        pytest.param("", None, id="empty"),
        # A bare year with no "de" is NOT a date: four consecutive digits occur
        # in process numbers and monetary values far more often than as a
        # document's date, so the parser requires the "de 1980" cue.
        pytest.param("2018", None, id="bare-year-rejected"),
    ],
)
def test_date_forms(text: str, expected: UrnDate | None):
    """Every date shape in the corpus parses; anything else yields ``None``."""
    assert parse_pt_date(text) == expected


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        # "PARECER n. 00093/2018/DECOR/CGU/AGU" — the number is fused into a
        # path; only the head is the number, and its zeros are padding.
        pytest.param("parecer_93_2018_decor_cgu_agu", "93", id="00093/2018-to-93"),
        # "RECURSO ESPECIAL Nº 1.306.393 - DF" — thousands separators dropped.
        pytest.param("REsp_1306393", "1306393", id="1.306.393-to-1306393"),
        # "ATO DECLARATÓRIO PGFN Nº 3" — a plain number survives unchanged.
        pytest.param("ad_pgfn_3_20080918", "3", id="plain-3"),
    ],
)
def test_number_normalisation(stem: str, expected: str):
    """Numbers reach the URN normalised, whatever the epigraph wrote.

    Driven through :func:`extract_metadata` rather than the private helper on
    purpose: the helper only ever sees the epigraph regex's digit capture, so
    testing it directly would not prove that the *right* substring is handed to
    it. ``1.306.393 - DF (2012/0013476-0)`` in particular is a case where the
    capture boundary matters as much as the normalisation.
    """
    assert meta(stem).number == expected


def test_number_normalisation_reaches_the_urn():
    """The normalised number is what the URN carries, not a re-derived one."""
    assert meta("REsp_1306393").urn.endswith(";1306393")
    assert meta("parecer_93_2018_decor_cgu_agu").urn.endswith(";93")


# --------------------------------------------------------------------------
# 3. Corpus-wide invariants (decision #2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_all_samples_produce_valid_urn(stem: str):
    """Extraction never raises, and always yields a URN matching the grammar.

    Decision #2: a document the extractor cannot identify still has to produce
    output — Cycle 8's "handles any document" starts here. The four incomplete
    samples reach this bar on sentinels (``0000`` for the date, ``0`` for the
    number), which is exactly why the next test exists.
    """
    m = extract_metadata(styled_doc(stem), filename=f"{stem}.docx")

    assert is_valid_urn(m.urn), f"{stem}: {m.urn!r} does not match the URN grammar"


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_incomplete_metadata_flagged(stem: str):
    """``complete``/``missing`` tell the truth for all 15, not just the four.

    Parametrised over the whole corpus rather than over ``INCOMPLETE`` alone:
    checking only the four would let a change that marks *everything*
    incomplete pass unnoticed, and a permanently-False flag is no safer than a
    permanently-True one.
    """
    m = meta(stem)

    if stem in INCOMPLETE:
        assert m.complete is False
        assert m.missing == INCOMPLETE[stem]
    else:
        assert m.complete is True, f"{stem} unexpectedly incomplete: {m.missing}"
        assert m.missing == ()


def test_exactly_four_samples_are_incomplete():
    """A tripwire on the scope of the exemption.

    The per-sample test above reads ``INCOMPLETE`` as its ground truth, so it
    would happily follow that dict wherever it went. This asserts the count
    independently: if a sixteenth sample arrives, or the extractor starts
    losing a date it used to find, the *size* of the exemption changes here.
    """
    incomplete = {s for s in SAMPLE_STEMS if not meta(s).complete}

    assert incomplete == set(INCOMPLETE)


# --------------------------------------------------------------------------
# 4. The filename fallback ordering (decision #3)
# --------------------------------------------------------------------------


def _synthetic_para(text: str, index: int) -> StyledPara:
    return StyledPara(inlines=(Inline(text=text),), index=index)


def test_filename_fallback_only_when_needed():
    """The filename is consulted last, and only when nothing else spoke.

    Two halves, and the first is the one that matters. Filenames in this corpus
    encode a date the document often lacks, which makes reading them useful and
    reading them *early* catastrophic: the 300+ document corpus need not follow
    the convention at all, so a filename date that outranked the epigraph would
    silently mis-date every document whose name disagreed with its text.

    (a) feeds ``port_mf_277`` — whose epigraph says 7 June 2018 — a filename
    claiming 1 January 1901, and demands the epigraph win, with ``date_source``
    still ``"epigraph"``. A test that only exercised (b) would pass identically
    if the fallback ran first.

    (b) proves the capability is actually wired up. No sample exercises it (all
    15 state a date, or state none and have none in their filename either), so
    the document is synthetic: an epigraph with a number but no date, and a
    filename that carries one.
    """
    # (a) an in-document date is never overridden by a contradictory filename.
    contradicted = extract_metadata(
        styled_doc("port_mf_277_20180607"), filename="port_mf_277_19010101.docx"
    )

    assert contradicted.date == UrnDate(2018, 6, 7)
    assert contradicted.date_source == "epigraph"
    assert contradicted.urn == "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277"

    # (b) with no date anywhere in the text, the filename is read and said so.
    dateless = StyledDoc(
        blocks=(
            _synthetic_para("PORTARIA MF nº 277", 0),
            _synthetic_para(
                "O MINISTRO DE ESTADO DA FAZENDA, no uso de suas atribuições, "
                "resolve:",
                1,
            ),
            _synthetic_para("Art. 1º Fica aprovado o regimento interno.", 2),
        ),
        source="port_sintetica_20180607.docx",
    )
    fallback = extract_metadata(dateless, filename="port_sintetica_20180607.docx")

    assert fallback.date == UrnDate(2018, 6, 7)
    assert fallback.date_source == "filename"
    assert fallback.complete is True

    # Omitting `filename` does not disable the fallback: `read_docx` records the
    # file's name on `StyledDoc.source`, so a document read from disk carries
    # its own name and the chain still reaches it. The explicit argument only
    # overrides that, which is what makes (a) above testable at all.
    unnamed = extract_metadata(dateless, filename=None)

    assert unnamed.date == UrnDate(2018, 6, 7)
    assert unnamed.date_source == "filename"

    # Only when there is no name anywhere does the chain end — no date, no
    # source, no exception, and `missing` says which component is absent.
    anonymous = extract_metadata(
        StyledDoc(blocks=dateless.blocks, source=None), filename=None
    )

    assert anonymous.date is None
    assert anonymous.date_source is None
    assert anonymous.missing == ("date",)


# --------------------------------------------------------------------------
# 5. Proprietary fields (decision #4)
# --------------------------------------------------------------------------


def test_proprietary_fields_parecer_93():
    """The plan's named fields are captured, with their values intact.

    ``parecer_93`` is the corpus's richest front matter and the source of the
    plan's field list. ``Cod. Ement.`` is the awkward one: block 16 writes it
    as ``Cod. Ement.34``, with no colon at all, so it needs its own pattern
    rather than the generic ``LABEL: value`` rule.
    """
    m = meta("parecer_93_2018_decor_cgu_agu")

    assert m.field("NUP") == "03154.004642/2018-50"
    assert m.field("INTERESSADOS") == (
        "CONSULTORIA JURÍDICA JUNTO AO MINISTÉRIO DO PLANEJAMENTO,"
    )
    assert m.field("ASSUNTO") == (
        "BENEFÍCIO ESPECIAL PREVISTO NA LEI NO 12.618, DE 2012"
    )
    assert m.field("EMENTA") == (
        "ADMINISTRATIVO. SERVIDOR PÚBLICO. REGIME DE PREVIDÊNCIA COMPLEMENTAR. "
        "BENEFÍCIO ESPECIAL. LEI NO 12.618, DE 2012."
    )
    assert m.field("Cod. Ement.") == "34"

    # Lookup is case- and accent-insensitive, and tolerates a missing trailing
    # dot — callers should not have to reproduce the document's punctuation.
    assert m.field("nup") == m.field("NUP")
    assert m.field("cod. ement") == "34"

    # An unknown label is None, not a KeyError: `field` is a query, not an index.
    assert m.field("Relator") is None

    # The labels are exactly these five, in document order. Set equality would
    # tolerate a sixth field appearing; this does not.
    assert [f.label for f in m.proprietary] == [
        "NUP",
        "INTERESSADOS",
        "ASSUNTO",
        "EMENTA",
        "Cod. Ement.",
    ]
    # Each field remembers the paragraph it came from, so a future cycle can
    # remove it from the body without re-finding it.
    assert all(f.source_index >= 0 for f in m.proprietary)


def test_par_cosit_26_fields():
    """The second field-bearing profile: a Parecer written with prose labels.

    ``Assunto``/``Ementa``/``Dispositivos Legais`` are title-case, not shouted,
    so they are captured by the allowlist rather than by the ALL-CAPS
    heuristic — which is the half of decision #4 that the ``parecer_93`` test,
    whose labels are all upper-case, cannot exercise.
    """
    m = meta("par_cosit_26_20000629")

    assert m.number == "26"
    assert m.date == UrnDate(2000, 6, 29)
    assert [f.label for f in m.proprietary] == [
        "Assunto",
        "Ementa",
        "Dispositivos Legais",
    ]
    assert m.field("Dispositivos Legais").startswith("Arts. 123 da Lei nº 5.172")


#: Labels that prose in the jurisprudence samples offers up to a naive
#: ``LABEL:`` matcher. Every one of these is either a minister speaking, a
#: party to the case or a page footer — none is document metadata. Without the
#: allowlist, ``sumula_stj_125`` captures eight of them.
PROSE_LABELS = (
    "Some-se",
    "O Sr. Ministro Garcia Vieira",
    "O Sr. Ministro Milton Pereira",
    "O Sr. Ministro Antônio de Pádua Ribeiro",
    "Advogados",
    "Relator",
    "Recorrente",
    "Recorrido",
    "Agravante",
    "Agravado",
    "Procuradores",
    "Documento",
)


def _folded_labels(m: Metadata) -> set[str]:
    """Captured labels, folded the way ``Metadata.field`` folds them.

    Comparing raw strings would let ``RELATOR:`` or ``Relator :`` slip past a
    test written against ``Relator``; the guard has to be as insensitive as the
    lookup it protects.
    """
    return {
        f.label.strip().rstrip(".").casefold().replace("ó", "o").replace("ô", "o")
        for f in m.proprietary
    }


@pytest.mark.parametrize("stem", ["sumula_stj_125", "REsp_1306393"])
def test_no_false_positive_fields_sumula_stj(stem: str):
    """No minister's prose is filed as document metadata. **The regression.**

    Spec §2.1 decision #4, and the reason this cycle has an allowlist at all.
    A naive ``LABEL: value`` sweep over ``sumula_stj_125``'s front matter finds
    ``Relator:``, ``Agravante:``, ``Procuradores:``, ``Agravado:``,
    ``Advogados:`` and ``O Sr. Ministro Antônio de Pádua Ribeiro:`` — the last
    being the opening of a vote, forty words of judicial reasoning captured as
    if it were a metadata value. ``REsp_1306393`` offers ``Documento:`` from a
    page footer.

    The asymmetry decision #4 rests on: a missed field is recoverable, because
    the text stays in the body for Cycle 3/4 to segment. A false field is
    silent corruption that reaches the XML with a ``fonte`` attribute vouching
    for it. So the assertion is zero, not few.

    Measured behaviour is that both samples capture **no** fields at all.
    ``Referência:`` and ``Precedentes:`` are on ``jurisprudencia_generico``'s
    allowlist and do appear in ``sumula_stj_125``, but each writes its value on
    the *following* paragraph, leaving an empty value that the extractor drops.
    That is a capture gap, not a false positive; it is pinned here as the
    current truth so that closing it later shows up as a deliberate change.
    """
    m = meta(stem)
    captured = _folded_labels(m)

    forbidden = {
        label.strip().rstrip(".").casefold().replace("ó", "o").replace("ô", "o")
        for label in PROSE_LABELS
    }
    leaked = captured & forbidden

    assert not leaked, (
        f"{stem}: prose captured as metadata: {sorted(leaked)}. "
        "These are ministers speaking and parties to a case, not document "
        "metadata — the allowlist of spec decision #4 has been weakened."
    )
    assert m.proprietary == (), (
        f"{stem}: expected no proprietary fields, got "
        f"{[(f.label, f.value[:40]) for f in m.proprietary]}"
    )


# --------------------------------------------------------------------------
# 6. XML emission (decision #6) and serialisation round-trip
# --------------------------------------------------------------------------


def _host_document(m: Metadata) -> etree._Element:
    """The smallest valid LexML document carrying ``m``'s ``<Metadado>``.

    ``to_xml()`` returns a fragment, and a fragment cannot be validated on its
    own — the schema constrains it only in the context of a ``<LexML>`` root.
    The rest of the document is the minimal ``DocumentoGenerico`` of plan §2.1
    row A, deliberately trivial so any failure is attributable to the metadata.
    """
    root = etree.Element(f"{{{LEXML_NS}}}LexML", nsmap={None: LEXML_NS})
    root.append(m.to_xml())
    dg = etree.SubElement(root, f"{{{LEXML_NS}}}DocumentoGenerico")
    pp = etree.SubElement(dg, f"{{{LEXML_NS}}}PartePrincipal")
    pp.set("id", "pp1")
    etree.SubElement(pp, f"{{{LEXML_NS}}}p").text = "x"
    return root


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_metadado_fragment_validates(stem: str):
    """Plan invariant #1, for the half of the document Cycle 2 owns.

    Both schemas, not either — the two disagree in places, and a fragment that
    satisfies only one is not portable. ``MetadadoProprietario`` is the part
    worth watching: it extends ``xsd:anyType`` so its ``<campo>`` children are
    unconstrained, but it *requires* a ``fonte`` URI, and an element that
    carries arbitrary children is exactly the sort that stops being checked.
    """
    m = meta(stem)
    report = validate(_host_document(m), "both")

    assert report.ok, f"{stem}: <Metadado> rejected\n{report.summary()}"

    # The required attribute is present exactly when the element is, and the
    # element is present exactly when there is something to put in it
    # (schema minOccurs="0" — an empty MetadadoProprietario is noise).
    prop = m.to_xml().find(f"{{{LEXML_NS}}}MetadadoProprietario")
    if m.proprietary:
        assert prop is not None, f"{stem}: {len(m.proprietary)} fields but no element"
        assert prop.get("fonte") == METADATA_SOURCE_URI
        campos = prop.findall(f"{{{LEXML_NS}}}campo")
        assert len(campos) == len(m.proprietary)
        assert [c.get("nome") for c in campos] == [f.label for f in m.proprietary]
        assert [c.text for c in campos] == [f.value for f in m.proprietary]
    else:
        assert prop is None, f"{stem}: empty MetadadoProprietario emitted"

    # The URN reaches the XML unaltered — the only place it is actually
    # consumed downstream.
    ident = m.to_xml().find(f"{{{LEXML_NS}}}Identificacao")
    assert ident is not None and ident.get("URN") == m.urn


def test_metadado_proprietario_present_for_at_least_one_sample():
    """Both branches of the test above are actually taken.

    Four samples carry fields and eleven do not; if that ever became "none
    carry fields", the ``fonte`` assertion would quietly stop running while
    :func:`test_metadado_fragment_validates` still reported fifteen passes.
    """
    with_fields = {s for s in SAMPLE_STEMS if meta(s).proprietary}

    assert with_fields == {
        "parecer_93_2018_decor_cgu_agu",
        "par_cosit_26_20000629",
        "ad_pgfn_3_20080918",
        "ad_pgfn_13_20111220",
        "port_mf_454_19770825",
    }


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_metadata_roundtrip(stem: str):
    """``from_dict(to_dict(m))`` recovers every field, for all 15.

    ``to_dict`` omits ``None``-valued fields for golden readability and adds
    three derived keys (``urn``, ``complete``, ``missing``) that ``from_dict``
    ignores. So the round trip is only lossless if every omitted field
    reconstructs to its default — and a field that silently did not would be
    invisible data loss in the metadata goldens themselves.

    Full dataclass equality holds (verified for all 15), and is asserted
    *first* because it covers fields nobody thought to list. The field-by-field
    comparison follows anyway: when equality fails it says only "not equal",
    and on an eleven-field frozen dataclass that is not a useful failure report.
    """
    m = meta(stem)
    revived = Metadata.from_dict(m.to_dict())

    for name in (
        "profile",
        "locality",
        "authority",
        "doc_type",
        "number",
        "date",
        "date_source",
        "authority_source",
        "epigraph",
        "epigraph_index",
        "proprietary",
        "source",
    ):
        assert getattr(revived, name) == getattr(m, name), f"{stem}: {name} differs"

    assert revived == m
    # The derived properties follow from the fields, so they must survive too.
    assert revived.urn == m.urn
    assert revived.complete == m.complete
    assert revived.missing == m.missing
    # And the JSON layer, which the goldens actually go through.
    assert Metadata.from_json(m.to_json()) == m
