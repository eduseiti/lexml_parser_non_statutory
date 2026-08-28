"""The label grammar: what may be a rótulo, and what only looks like one.

Cycle 4's plan bullet asks for "~40 parametrised forms → (kind, value, arity),
**including negatives**". The positives are the cheap half — every sample in the
corpus numbers itself, and the shapes repeat. What this file exists to hold down
is the other half, because the grammar is the first place a 300-document corpus
can go wrong in silence:

1. **A number is not a label just because it is initial.** ``Lei nº 12.618``,
   ``1.500/2014``, ``29.11.1993``, ``Cr$ 380.000,00`` and ``2.08.30.00`` all
   open a real corpus paragraph with digits and none of them numbers a section.
   Each negative below is a paragraph that actually occurs (the sample is named
   in the case id or the docstring), so a relaxed rule is caught by the document
   that motivated the rule rather than by a synthetic string.

2. **The zero rule is one rule, doing two jobs** (amendment A-4.2). "A component
   with a leading zero, or a zero component, is not an ordinal" is what rejects
   ``pn_cst_38``'s subject codes (``2.08.30.00``) *and* ``sumula_stj_125``'s
   two-component dates (``06.12``) — which by shape alone are indistinguishable
   from ``2.1``. Testing only one of the two would let the rule be narrowed to
   the other and still pass.

3. **The grammar deliberately does not reject the orphan deep label.**
   ``1.24.20.25`` parses here and is refused in :mod:`.unify`, because ``2.3.1``
   is a good label when ``2.3`` is open and noise when it is not. That division
   of labour is pinned by :func:`test_orphan_deep_label_still_parses_here`; if
   it ever moves, both files must move together.

4. **Named units need the document's consent** (amendment A-4.4).
   ``Súmula CARF nº 1`` is a heading only because ``port_mf_277``'s annex was
   *shown* to run such a series; the same rule, applied without ``unit_heads``,
   would promote every ``Lei nº …`` in ``parecer_93`` into a section.

Everything here is pure string→``Label``, so no sample is loaded: the grammar's
contract is with the shapes, and the corpus contributes the shapes, not fixtures.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from lexml_nonstat.hierarchy.labels import (
    ARTICLE_RE,
    Label,
    alpha_to_int,
    fold,
    looks_like_heading,
    parse_label,
    roman_to_int,
    strip_leading_quote,
)

#: Every kind the grammar is allowed to emit (spec §4.2, as implemented).
KINDS = frozenset(
    {
        "numeric",
        "roman",
        "alpha",
        "compound",
        "ordinal",
        "artigo",
        "paragrafo",
        "unit",
        "capitulo",
        "secao",
        "subsecao",
        "titulo",
        "livro",
        "parte",
    }
)

SUMULA_HEADS = frozenset({"sumula carf"})


def _parsed(text: str, **kwargs: object) -> Label:
    """Parse and insist it parsed — keeps the positive tables readable."""
    label = parse_label(text, **kwargs)  # type: ignore[arg-type]
    assert label is not None, f"expected {text!r} to parse as a label"
    return label


# ---------------------------------------------------------------------------
# Positives
# ---------------------------------------------------------------------------

NUMERIC_FORMS = [
    ("1.", (1,), 1),
    ("2.1", (2, 1), 2),
    ("2.3.1 -", (2, 3, 1), 3),
    ("10.", (10,), 1),
    ("4.1.", (4, 1), 2),
    ("1.1", (1, 1), 2),
    ("2.3", (2, 3), 2),
    ("7 DECORRÊNCIA", (7,), 1),
    # Real paragraph openings, sample by sample.
    ("1. O Demonstrativo da Apuração dos Ganhos de Capital", (1,), 1),  # adn_cst_10
    ("1.1 Na apuração do ganho de capital na alienação de bens", (1, 1), 2),  # adn_cst_10
    ("2. DAS SOCIEDADES COOPERATIVAS", (2,), 1),  # pn_cst_38
    ("2.1 - Empresas de serviços", (2, 1), 2),  # pn_cst_38
    ("2.3.1 - Do resultado das operações", (2, 3, 1), 3),  # pn_cst_38 shape
    ("16.3 - Conclusão", (16, 3), 2),  # par_cosit_26 shape
    ("1 - REGIME DE PREVIDÊNCIA COMPLEMENTAR", (1,), 1),  # parecer_93
    ("11 - BENEFÍCIO ESPECIAL", (11,), 1),  # parecer_93
    ("111 - NATUREZA JURÍDICA DO BENEFÍCIO ESPECIAL", (111,), 1),  # parecer_93
]


@pytest.mark.parametrize(
    ("text", "value", "depth"),
    NUMERIC_FORMS,
    ids=[case[0][:32] for case in NUMERIC_FORMS],
)
def test_numeric_forms(text: str, value: tuple[int, ...], depth: int) -> None:
    """A dotted run is a label and its arity is its depth.

    ``depth`` is the only property that carries the nesting the document
    declared about itself, so it is asserted on every numeric form rather than
    trusted to follow from ``value``.
    """
    label = _parsed(text)
    assert label.kind == "numeric"
    assert label.value == value
    assert label.depth == depth
    assert label.depth == len(label.value)
    assert label.is_dispositivo is False


ROMAN_FORMS = [
    ("I -", 1),
    ("II.", 2),
    ("IV -", 4),
    ("IX -", 9),
    ("XIV -", 14),
    ("III - o valor da avaliação no inventário;", 3),  # par_cosit_26
    ("X - fixar a interpretação da Constituição", 10),  # parecer_93
    ("XXX - a última hipótese", 30),
]


@pytest.mark.parametrize(
    ("text", "value"), ROMAN_FORMS, ids=[case[0][:24] for case in ROMAN_FORMS]
)
def test_roman_forms(text: str, value: int) -> None:
    """Roman incisos reduce to an ordinal and are always depth 1.

    A roman label is worth nothing without its separator (``I`` opens plenty of
    Portuguese sentences), so every accepted form here carries one.
    """
    label = _parsed(text)
    assert label.kind == "roman"
    assert label.value == (value,)
    assert label.depth == 1
    assert label.separator in {".", ")", "-", "–", "—"}


ALPHA_FORMS = [
    ("a)", 1),
    ("b)", 2),
    ("c.", 3),
    ("z)", 26),
    ("a) Serviços", 1),  # pn_cst_38
    ("b) Bens", 2),  # pn_cst_38
    ("a) uniformização da jurisprudência administrativa;", 1),  # parecer_93
]


@pytest.mark.parametrize(
    ("text", "value"), ALPHA_FORMS, ids=[case[0][:24] for case in ALPHA_FORMS]
)
def test_alpha_forms(text: str, value: int) -> None:
    """Alíneas reduce to an ordinal, ``a`` → 1, and stay depth 1."""
    label = _parsed(text)
    assert label.kind == "alpha"
    assert label.value == (value,)
    assert label.depth == 1


COMPOUND_FORMS = [
    ("c. 1) coisa", (3, 1), "coisa"),
    ("c. 1) contribuições previdenciárias a serem consideradas", (3, 1), None),  # parecer_93
    ("a. 2) outra coisa", (1, 2), "outra coisa"),
]


@pytest.mark.parametrize(
    ("text", "value", "rest"),
    COMPOUND_FORMS,
    ids=[case[0][:24] for case in COMPOUND_FORMS],
)
def test_compound_forms(text: str, value: tuple[int, int], rest: str | None) -> None:
    """``c. 1)`` is one label, not an alínea followed by prose.

    ``parecer_93`` subdivides its alíneas this way. Parsing it as ``c.`` alone
    would silently drop the ``1)`` into the paragraph body and collapse every
    sub-item of ``c.`` onto the same level.
    """
    label = _parsed(text)
    assert label.kind == "compound"
    assert label.value == value
    assert label.depth == 1
    if rest is not None:
        assert label.text == rest


NAMED_UNITS = [
    ("CAPÍTULO II", "capitulo", (2,)),
    ("Seção I", "secao", (1,)),
    ("Subseção Única", "subsecao", (1,)),
    ("Subseção I", "subsecao", (1,)),
    ("TÍTULO I", "titulo", (1,)),
    ("TÍTULO II - DA COISA JULGADA", "titulo", (2,)),
    ("LIVRO I", "livro", (1,)),
    ("LIVRO II", "livro", (2,)),
    ("PARTE ESPECIAL", "parte", (1,)),
    ("CAPÍTULO I - DISPOSIÇÕES GERAIS", "capitulo", (1,)),
    ("CAPÍTULO 2 - Dos atos", "capitulo", (2,)),
]


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    NAMED_UNITS,
    ids=[case[0][:28] for case in NAMED_UNITS],
)
def test_named_units(text: str, kind: str, value: tuple[int, ...]) -> None:
    """A named unit keeps its own kind, so Cycle 5 can map it to the LexML
    element the document actually named — ``Seção`` must never arrive as a
    generic ``numeric`` that happened to be first on the line.

    ``SUBSEÇÃO`` is checked ahead of ``SEÇÃO``; if that order were lost,
    ``Subseção I`` would come back as a ``secao`` and silently flatten a level.
    """
    label = _parsed(text)
    assert label.kind == kind
    assert label.value == value
    assert label.depth == 1
    assert label.is_dispositivo is False


def test_named_unit_ordering_subsecao_beats_secao() -> None:
    """``Subseção`` is not a ``Seção`` with a prefix — the longest-first order in
    ``_NAMED_UNITS`` is load-bearing and has no other test."""
    assert _parsed("Subseção I").kind == "subsecao"
    assert _parsed("SUBSEÇÃO ÚNICA").kind == "subsecao"
    assert _parsed("Seção I").kind == "secao"


@pytest.mark.parametrize(
    "text",
    ["Parágrafo único", "Parágrafo único.", "Subseção Única", "SUBSEÇÃO ÚNICA", "Seção Única"],
    ids=["par-unico", "par-unico-dot", "subsecao-unica", "SUBSECAO-UNICA", "secao-unica"],
)
def test_unico_is_ordinal_one(text: str) -> None:
    """``único``/``única`` is the ordinal 1, not a missing number.

    Giving it an empty ``value`` would make it unorderable against its siblings
    and unnumberable in an ``id`` path; giving it 1 is what the LexML
    ``parágrafo único`` convention means.
    """
    label = _parsed(text)
    assert label.value == (1,)
    assert label.depth == 1


ORDINALS = [
    ("1º Fica atribuído", 1, "ordinal"),
    ("2ª via do documento", 2, "ordinal"),
    ("2º) Regime Próprio dos Servidores Públicos", 2, "ordinal"),  # parecer_93
    ("3o do mesmo artigo", 3, "ordinal"),
]


@pytest.mark.parametrize(
    ("text", "value", "kind"), ORDINALS, ids=[case[0][:24] for case in ORDINALS]
)
def test_ordinals(text: str, value: int, kind: str) -> None:
    """The masculine and feminine ordinal marks are both numbers.

    ``parecer_93`` numbers one of its tracks ``1º) 2º) …``; reading ``2º)`` as
    prose loses the track entirely.
    """
    label = _parsed(text)
    assert label.kind == kind
    assert label.value == (value,)
    assert label.depth == 1


@pytest.mark.parametrize(
    ("text", "value"),
    [("1º", 1), ("2ª", 2), ("1º ", 1), ("3o", 3), ("1º)", 1)],
    ids=["1o", "2a", "1o-space", "3o", "1o-paren"],
)
def test_bare_ordinal_without_remainder_parses(text: str, value: int) -> None:
    """An ordinal that *is* the whole paragraph is still a rótulo.

    This test was first written the other way round, pinning a gap: the ordinal
    pattern required a remainder after the mark while every other kind had an
    end-of-string twin, so a lone ``1º`` on a line of its own parsed as nothing
    at all. ``_ORDINAL_ONLY_RE`` closed it.

    **No paragraph in the 15-sample corpus is a bare ordinal** (measured:
    zero), so no golden moved and nothing observable depended on either
    behaviour. It is written for the 300+ unseen documents, which is exactly
    the case where a silently unparsed heading would never be noticed. A lone
    ordinal still cannot become a section on its own — `unify` rejects
    singleton sequences — so closing the gap adds recognition, not structure.
    """
    label = parse_label(text)
    assert label is not None
    assert label.kind == "ordinal"
    assert label.value == (value,)
    assert label.text == ""


ARTIGO_PARAGRAFO = [
    ("Art. 1º Fica atribuído", "artigo", (1,)),
    ("Art 40. Aos servidores", "artigo", (40,)),
    ("Art. 1º-A", "artigo", (1,)),
    ("§ 4º-A Os demais", "paragrafo", (4,)),
    ("Art. 52. Na apuração", "artigo", (52,)),
    ("§ 2º", "paragrafo", (2,)),
    ("§ 1º", "paragrafo", (1,)),
    ("§ 3º As demais hipóteses", "paragrafo", (3,)),
    ("Parágrafo único.", "paragrafo", (1,)),
    ("Parágrafo único - Fica vedado", "paragrafo", (1,)),
]


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    ARTIGO_PARAGRAFO,
    ids=[case[0][:24] for case in ARTIGO_PARAGRAFO],
)
def test_artigo_paragrafo(text: str, kind: str, value: tuple[int, ...]) -> None:
    """Statutory labels are recognised *and* flagged as such.

    ``is_dispositivo`` is the flag decision D-3 rests on: an ``Art.`` never
    becomes a section on the generic route, and 25 of them in ``parecer_93``
    plus 5 in ``par_cosit_26`` are quoted from *other* norms. If the flag were
    lost, every quoted article in the corpus would compete for a heading.
    """
    label = _parsed(text)
    assert label.kind == kind
    assert label.value == value
    assert label.is_dispositivo is True


def test_non_statutory_labels_are_not_dispositivo() -> None:
    """The other side of D-3: a section number must not claim to be statutory."""
    for text in ("1.", "I -", "a)", "CAPÍTULO II", "c. 1) coisa", "2º) Regime"):
        assert _parsed(text).is_dispositivo is False


@pytest.mark.parametrize(
    ("quoted_text", "plain_text"),
    [
        ('"Art. 3. Será devido o imposto', "Art. 3. Será devido o imposto"),
        ('“Art. 18 - O disposto', "Art. 18 - O disposto"),
        ('"I - o valor atribuído', "I - o valor atribuído"),
        ('"2.1 - Empresas de serviços', "2.1 - Empresas de serviços"),
    ],
    ids=["art-3", "art-18-curly", "inciso", "numeric"],
)
def test_leading_quote_recorded(quoted_text: str, plain_text: str) -> None:
    """An opening quotation mark changes the verdict of the caller, never of the
    grammar. ``quoted`` is how the mark reaches :mod:`.quotation`, which needs
    it; the kind and value must be exactly what the unquoted paragraph gives,
    because a quoted ``Art. 3`` is still an article — it just belongs to
    somebody else's norm.
    """
    quoted = _parsed(quoted_text)
    plain = _parsed(plain_text)
    assert quoted.quoted is True
    assert plain.quoted is False
    assert (quoted.kind, quoted.value) == (plain.kind, plain.value)


def test_kind_vocabulary_is_closed() -> None:
    """Every form this file accepts emits a kind Cycle 5 knows how to render."""
    forms = (
        [case[0] for case in NUMERIC_FORMS]
        + [case[0] for case in ROMAN_FORMS]
        + [case[0] for case in ALPHA_FORMS]
        + [case[0] for case in COMPOUND_FORMS]
        + [case[0] for case in NAMED_UNITS]
        + [case[0] for case in ORDINALS]
        + [case[0] for case in ARTIGO_PARAGRAFO]
        + ["Súmula CARF nº 1"]
    )
    for text in forms:
        label = _parsed(text, unit_heads=SUMULA_HEADS)
        assert label.kind in KINDS, f"{text!r} produced unknown kind {label.kind!r}"


# ---------------------------------------------------------------------------
# Negatives
# ---------------------------------------------------------------------------

NORM_CITATIONS = [
    "Lei nº 12.618, de 2012",
    "Lei nº 12.618, de 2012, que instituiu o regime de previdência complementar",
    "1.500/2014 é o número",
    "1.500/2014",
    "Decreto-lei nº 1.510, de 27 de dezembro de 1976",
    "Decretos nº 3.000, de 1999",
    "Resolução nº 01, de 15 de outubro de 2003",
    "Súmula CARF nº 1",
    "Portaria MF nº 454, de 25 de agosto de 1977",
    "Instrução Normativa SRF nº 84, de 2001",
    "Acórdão nº 104-23033",
    "Parecer Normativo CST nº 38, de 1980",
]


@pytest.mark.parametrize("text", NORM_CITATIONS, ids=[t[:30] for t in NORM_CITATIONS])
def test_negative_norm_citations(text: str) -> None:
    """A paragraph that opens by naming another norm is not numbering itself.

    Every string here is a real corpus opening — ``parecer_93`` cites
    ``Lei nº 12.618`` on nearly every page, ``port_mf_454`` opens on
    ``Decreto-lei nº 1.510``, ``sumula_stj_125`` on ``Acórdão nº …``. Two
    independent rules must both hold for this to keep working: the citation-head
    vocabulary, and the thousands-group rule that kills ``12.618`` and
    ``1.500/2014`` even where no head word precedes them.

    ``Súmula CARF nº 1`` is listed here *without* ``unit_heads`` on purpose:
    outside ``port_mf_277``'s annex it is a citation like any other
    (amendment A-4.4, and see :func:`test_unit_requires_detected_head`).
    """
    assert parse_label(text) is None


DATES = [
    "06.12",
    "29.11.1993",
    "17/11/2003",
    "06.12.1993",
    "1º.01.2004",
    "31/12/1998",
]


@pytest.mark.parametrize("text", DATES, ids=[t[:16] for t in DATES])
def test_negative_dates(text: str) -> None:
    """Dates are not section numbers.

    ``sumula_stj_125`` carries a judgment date on nearly every precedent it
    compiles (block 61 is ``06.12.1993``). Three-component dates are refused by
    shape; the two-component ``06.12`` is refused only because ``06`` is
    zero-padded — by shape alone it is ``2.1``. That is why the zero rule and
    the date rule are tested separately: neither covers the other.
    """
    assert parse_label(text) is None


ZERO_PADDED = [
    "2.08.30.00 - Isenção das Sociedades Cooperativas",
    "2.16.25.00 - Lucro Arbitrado",
    "1.00.20",
    "1.00.20 - Imposto sobre a Renda",
    "0.1 - nada",
    "2.0",
    "08. Alguma coisa",
    "2.08",
]


@pytest.mark.parametrize("text", ZERO_PADDED, ids=[t[:26] for t in ZERO_PADDED])
def test_negative_zero_padded_components(text: str) -> None:
    """A component with a leading zero, or a zero component, is not an ordinal.

    ``pn_cst_38`` blocks 3–4 are the subject-classification codes
    ``2.08.30.00`` / ``2.16.25.00`` sitting immediately above the document's own
    ``1.`` … ``7.`` numbering. Accepting them opens two spurious four-deep
    branches at the top of the tree and pushes every real section down a level.

    Nobody numbers a section ``08`` and nobody numbers one ``0``, which is what
    makes this a *rule* rather than a patch for two paragraphs (amendment A-4.2).
    """
    assert parse_label(text) is None


MONEY_AND_PROSE = [
    "Cr$ 380.000,00",
    "Cr$ 380.000,00 de lucro apurado",
    "R$ 1.500,00",
    "Em linhas gerais, as cooperativas são definidas como sociedades de pessoas",
    "Trata-se de consulta formulada por contribuinte domiciliado nesta capital",
    "",
    "   ",
    "\t\n ",
]


@pytest.mark.parametrize(
    "text", MONEY_AND_PROSE, ids=[repr(t)[:34] for t in MONEY_AND_PROSE]
)
def test_negative_money_and_prose(text: str) -> None:
    """Currency amounts and ordinary sentences produce nothing.

    ``pn_cst_38``'s worked examples are full of ``Cr$ 380.000,00``; the
    thousands group is the same signal that rejects ``Lei nº 12.618``. The empty
    and whitespace-only cases are here because a segmenter hands the grammar
    whatever the document contains, blank paragraphs included, and ``None`` is
    the only safe answer.
    """
    assert parse_label(text) is None


def test_negative_bare_numeric_before_prose() -> None:
    """A lone number with no separator is a label only if what follows is a
    heading.

    ``7 DECORRÊNCIA`` (``pn_cst_38``'s last section) and ``7 pessoas físicas
    foram ouvidas…`` are the same shape: digit, space, words. Nothing but the
    remainder separates them, so the remainder decides — and the caller must
    still find that 7 continues a series (``allow_bare_numeric`` is how
    :mod:`.unify` turns the whole guess off).

    A *dotted* label needs neither test: the dot is already the separator, which
    is why ``adn_cst_10``'s ``1.1 Na apuração do ganho…`` survives with an
    ordinary prose remainder.
    """
    assert parse_label("7 pessoas físicas foram ouvidas durante o processo e depois disso") is None
    assert parse_label("2 vezes o valor da contribuição foi recolhido pelo contribuinte") is None

    heading = _parsed("7 DECORRÊNCIA")
    assert (heading.kind, heading.value) == ("numeric", (7,))

    # The same string, with the guess switched off.
    assert parse_label("7 DECORRÊNCIA", allow_bare_numeric=False) is None

    # The switch is scoped to the ambiguous case only: a dotted or separated
    # label is unaffected by it.
    assert parse_label("1.1 Na apuração do ganho de capital", allow_bare_numeric=False) is not None
    assert parse_label("1 - REGIME DE PREVIDÊNCIA COMPLEMENTAR", allow_bare_numeric=False) is not None


# ---------------------------------------------------------------------------
# The load-bearing non-rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1.24.20.25 - Rendimentos Distribuídos pelas Pessoas Jurídicas", (1, 24, 20, 25)),
        ("2.3.1 - Do resultado", (2, 3, 1)),
        ("16.3.2.1 - Outra coisa", (16, 3, 2, 1)),
    ],
    ids=["pn_cst_38-orphan", "well-parented", "deep"],
)
def test_orphan_deep_label_still_parses_here(text: str, value: tuple[int, ...]) -> None:
    """The grammar accepts a deep label with no parent; :mod:`.unify` rejects it.

    ``1.24.20.25`` opens ``pn_cst_38`` with no ``1.``, ``1.24`` or ``1.24.20``
    anywhere above it — it is a subject-classification code, and it must not
    become a four-deep section. But it is refused **in unify, not here**, and
    that is a deliberate division of labour:

        the grammar answers "could this be a label?";
        the document answers "is it?".

    ``2.3.1`` is the proof that no local rule can decide it. The exact same
    string is a perfectly good sub-item when ``2.3`` is open above it and noise
    when it is not, so a grammar that rejected orphans by shape would have to
    reject the real ones too. Both forms are asserted here, identically, to make
    that indistinguishability explicit.

    If this ever changes, ``test_hierarchy_unify.py``'s
    ``test_orphan_dotted_label_rejected`` and
    ``test_pn_cst_38_subject_codes_rejected`` are the tests that must change
    with it — the corpus behaviour (blocks 2–4 yield no section) is theirs to
    protect, not this file's.
    """
    label = _parsed(text)
    assert label.kind == "numeric"
    assert label.value == value
    assert label.depth == len(value)


# ---------------------------------------------------------------------------
# Named units
# ---------------------------------------------------------------------------


def test_unit_requires_detected_head() -> None:
    """A named unit is a label only for a document shown to run that series.

    ``port_mf_277``'s annex numbers 65 items ``Súmula CARF nº 1`` … ``nº 100``;
    the head is discovered over the whole document by
    :func:`.unify.detect_unit_series` and handed back in. The same paragraph in
    isolation is a citation, which is exactly what stops the rule from firing on
    the hundreds of ``Lei nº …`` lines elsewhere in the corpus (amendment A-4.4).
    """
    assert parse_label("Súmula CARF nº 1") is None
    assert parse_label("Súmula CARF nº 100") is None

    label = _parsed("Súmula CARF nº 1", unit_heads=SUMULA_HEADS)
    assert label.kind == "unit"
    assert label.value == (1,)
    assert label.unit_head == "sumula carf"
    assert label.depth == 1

    hundred = _parsed("Súmula CARF nº 100", unit_heads=SUMULA_HEADS)
    assert (hundred.kind, hundred.value) == ("unit", (100,))


@pytest.mark.parametrize(
    "text",
    [
        "Lei nº 12.618",
        "Lei nº 12.618, de 2012",
        "Acórdão nº 104-23033",
        "Decreto-lei nº 1.510",
        "Portaria MF nº 454",
        "Súmula STJ nº 125",
    ],
    ids=["lei", "lei-de-2012", "acordao", "decreto-lei", "portaria", "other-sumula"],
)
def test_unit_head_must_match(text: str) -> None:
    """Consent is granted to one head, not to the ``nº`` shape.

    Every string here has the shape ``<words> nº <digits>`` that
    ``Súmula CARF nº 1`` has. If ``unit_heads`` were treated as "this document
    uses named units" rather than "this document uses *these* named units",
    ``parecer_93``'s ``Lei nº 12.618`` would become a heading — the plan's own
    worked example of a non-label. ``Súmula STJ nº 125`` is included because a
    near-miss head must miss too.
    """
    assert parse_label(text, unit_heads=SUMULA_HEADS) is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROMAN_I_TO_XXX = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
    "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20, "XXI": 21,
    "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25, "XXVI": 26, "XXVII": 27,
    "XXVIII": 28, "XXIX": 29, "XXX": 30,
}


def test_roman_to_int() -> None:
    """Roman numerals convert strictly: malformed input is ``None``, never a
    best guess.

    I–XXX is the whole range the corpus uses (``parecer_93`` reaches X, statutes
    it quotes reach XIV). Strictness is the point of the second half: ``IIII``
    and ``VV`` are not numerals, and a lenient additive parser would happily
    return 4 and 10 for them — which would let ordinary words beginning with
    roman letters (``VV`` never occurs, but ``MIX``, ``DIVIDIR``, ``CIVIL`` do)
    slip in as inciso numbers.
    """
    for numeral, expected in ROMAN_I_TO_XXX.items():
        assert roman_to_int(numeral) == expected, numeral
        assert roman_to_int(numeral.lower()) == expected, numeral

    for bad in ("IIII", "VV", "", "banana", "IC", "XXXX", "VX", "IL", "MMMM", "1", "I I"):
        assert roman_to_int(bad) is None, bad


def test_alpha_to_int() -> None:
    """``a`` → 1 … ``z`` → 26; anything that is not one letter is ``None``.

    Single letters are all the corpus uses for alíneas, and the ``None`` half is
    what keeps a two-letter word from being read as one.
    """
    for offset in range(26):
        letter = chr(ord("a") + offset)
        assert alpha_to_int(letter) == offset + 1
        assert alpha_to_int(letter.upper()) == offset + 1

    for bad in ("ab", "aa", "", "1", ")", " ", "á b", "abc"):
        assert alpha_to_int(bad) is None, bad


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("DAS SOCIEDADES COOPERATIVAS", True),
        ("CONCLUSÃO", True),
        ("DECORRÊNCIA", True),
        ("Atos Cooperativos", True),
        ("Exemplificação", True),
        ("Empresas de serviços", True),
        (
            "Como foi dito inicialmente, deve o imposto de renda ter por base de "
            "cálculo o resultado apurado",
            False,
        ),
        (
            "Na apuração do ganho de capital na alienação de bens adquiridos por "
            "herança, o custo será o constante do inventário.",
            False,
        ),
        ("", False),
        ("   ", False),
    ],
    ids=[
        "caps-phrase", "caps-word", "caps-accent", "title-case", "single-word",
        "short-phrase", "long-prose", "prose-with-period", "empty", "blank",
    ],
)
def test_looks_like_heading(text: str, expected: bool) -> None:
    """What separates a section title from a numbered paragraph's own body.

    ``2. DAS SOCIEDADES COOPERATIVAS`` names a section; ``5.1 - Como foi dito
    inicialmente…`` is a numbered paragraph whose remainder *is* its text. This
    predicate decides which, and so decides what can fill ``nomeAgrupador``
    without inventing one (plan §5.1). It is also the sole guard on the
    ambiguous bare-numeric case, so relaxing it costs false sections directly.
    """
    assert looks_like_heading(text) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Art. 3. Será devido', "Art. 3. Será devido"),
        ("“Art. 18 - O disposto", "Art. 18 - O disposto"),
        ("'a) Serviços", "a) Serviços"),
        ("«I - o valor", "I - o valor"),
        ('  "  2.1 - Empresas', "2.1 - Empresas"),
        ("Art. 3. Sem aspas", "Art. 3. Sem aspas"),
        ("", ""),
    ],
    ids=["straight", "curly", "apostrophe", "guillemet", "padded", "unquoted", "empty"],
)
def test_strip_leading_quote(raw: str, expected: str) -> None:
    """All four opening marks the corpus uses are removed, and only leading ones.

    The mark matters to :mod:`.quotation` and is noise to the grammar, so it is
    recorded and dropped rather than either kept or ignored.
    """
    assert strip_leading_quote(raw) == expected


def test_strip_leading_quote_leaves_inner_marks() -> None:
    """Only the *opening* mark goes: quotes inside a paragraph are its text."""
    text = 'A Disit afirmou que "a cessão de direitos" não se aplica'
    assert strip_leading_quote(text) == text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Subseção Única", "subsecao unica"),
        ("CAPÍTULO", "capitulo"),
        ("Súmula CARF", "sumula carf"),
        ("Decreto-lei", "decreto-lei"),
        ("Acórdão", "acordao"),
        ("PARÁGRAFO ÚNICO", "paragrafo unico"),
        ("Ato Declaratório", "ato declaratorio"),
        ("", ""),
    ],
    ids=["subsecao", "capitulo", "sumula", "decreto-lei", "acordao", "paragrafo", "ato", "empty"],
)
def test_fold(raw: str, expected: str) -> None:
    """Accent-folding and lowercasing, the same rule Cycle 2's profiles use.

    Every vocabulary lookup in this module — named units, citation heads, unit
    heads — goes through ``fold``, so a document that writes ``CAPITULO``
    without the accent must land on the same key as one that writes ``CAPÍTULO``.
    """
    assert fold(raw) == expected


def test_canonical_drops_separator() -> None:
    """``raw`` keeps the document's punctuation; ``canonical`` is the key.

    A faithful rendering wants ``2.1 -`` exactly as written; an ``id`` path or a
    parent lookup wants ``2.1``. Keeping both on the same object is what lets
    Cycle 5 choose per use without re-parsing.
    """
    label = _parsed("2.1 - Empresas de serviços")
    assert label.raw == "2.1 -"
    assert label.separator == "-"
    assert label.canonical == "2.1"
    assert label.text == "Empresas de serviços"

    dotted = _parsed("2.3.1 - Do resultado")
    assert dotted.raw == "2.3.1 -"
    assert dotted.canonical == "2.3.1"

    # Non-numeric kinds canonicalise by stripping the trailing punctuation.
    assert _parsed("I - o valor").canonical == "I"
    assert _parsed("a) Serviços").canonical == "a"
    assert _parsed("II.").canonical == "II"

    # A separator with nothing after it is still the label's separator, and the
    # remainder is empty — a heading whose title sits on the next line.
    #
    # This pinned a real defect when it was first written: `_NUMERIC_RE` needs
    # trailing whitespace, so it backtracked past the hyphen and reported
    # `raw="2.1"` with the separator stranded in `text`. `canonical` hid it
    # (it is rebuilt from `value`), but the section would have carried a body
    # paragraph reading `-`. The whole-paragraph pattern is now tried first.
    dangling = _parsed("2.1 -")
    assert dangling.canonical == "2.1"
    assert dangling.raw == "2.1 -"
    assert dangling.text == ""
    assert dangling.separator == "-"


ARTICLE_MATCHES = [
    "Art. 1º",
    "Art 40. Aos servidores",
    '"Art. 18 - O disposto neste artigo',
    "Art. 52. ....",
    "Art. 1º-A Fica acrescido",
    "art. 201 da Constituição Federal",
    "“Art. 3º É devido",
]

ARTICLE_NON_MATCHES = [
    "O disposto no art. 201 da Constituição Federal",
    "na forma do art. 3º da Lei nº 12.618",
    "Artigo indefinido",
    "Art. sem número",
    "Artigos 1º e 2º",
    "",
]


@pytest.mark.parametrize("text", ARTICLE_MATCHES, ids=[t[:26] for t in ARTICLE_MATCHES])
def test_article_re_matches_corpus_forms(text: str) -> None:
    """``ARTICLE_RE`` covers every way the corpus writes an article opening.

    The corpus writes ``Art.``, ``Art`` with no dot, an opening quote before it,
    a masculine-ordinal number, a plain one, and a ``-A`` suffix — 25 in
    ``parecer_93`` and 5 in ``par_cosit_26``, most of them quoted from other
    norms. Missing any form means the quotation guard never sees the article and
    a foreign statute competes for a heading (decision D-3).
    """
    assert ARTICLE_RE.match(text) is not None


@pytest.mark.parametrize(
    "text", ARTICLE_NON_MATCHES, ids=[t[:28] or "empty" for t in ARTICLE_NON_MATCHES]
)
def test_article_re_rejects_non_initial_and_unnumbered(text: str) -> None:
    """The pattern is anchored and needs a number.

    ``art. 201 da Constituição Federal`` is an article reference in the middle
    of a sentence — it is only a label when it *opens* the paragraph, so the
    anchor is the whole rule, and ``search`` must fail as surely as ``match``
    (no ``MULTILINE``). ``Artigo indefinido`` shows the digit is required:
    without it, any word starting ``Art`` would open an article.
    """
    assert ARTICLE_RE.match(text) is None
    assert ARTICLE_RE.search(text) is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_parse_label_is_deterministic_and_frozen() -> None:
    """Same input, same ``Label`` — the grammar holds no state.

    Determinism is a cross-cutting invariant (plan §9.2) and the grammar is the
    cheapest place to assert it. ``Label`` being frozen and comparable is what
    lets the goldens compare by value.
    """
    for text in ("2.1 - Empresas de serviços", "I - o valor", "Súmula CARF nº 1"):
        first = parse_label(text, unit_heads=SUMULA_HEADS)
        second = parse_label(text, unit_heads=SUMULA_HEADS)
        assert first == second

    with pytest.raises(FrozenInstanceError):
        _parsed("1.").kind = "roman"  # type: ignore[misc]
