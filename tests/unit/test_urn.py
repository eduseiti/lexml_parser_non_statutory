"""LexML URN grammar: what we emit, what we accept, and where they must agree.

A URN is the only durable name a document has, so three properties are pinned
here and each one fails silently if it breaks:

1. **Round-trip.** ``parse_urn(build_urn(...))`` must recover *every* part
   unchanged. The two functions share no code — one formats, the other has a
   regex — so nothing but a test keeps them in agreement. Cycle 6 emits annex
   siblings by appending ``!anexo1`` to a parent URN and re-parsing it; if the
   fragment group ever stops surviving the trip, that breaks there, not here.

2. **The grammar is enforced, not assumed.** `is_valid_urn` is what later
   cycles will use to decide whether a metadata block is emittable at all, so
   the negative cases matter as much as the positive ones: an uppercase
   authority or a ``2018-6-7`` date must be rejected, because the reference
   parser's vocabulary is lowercase-and-zero-padded and a near-miss URN is
   worse than an obviously absent one.

3. **The sentinel is honest and complete.** Four of the fifteen samples state
   no date and no number (decision #2 of the cycle spec: never raise, flag
   incompleteness instead). `build_urn` answers with year ``0000`` and number
   ``0``. That is only a defensible answer if the sentinel survives the
   module's *own* parser — a URN we emit but cannot read back would be a
   dead end. `test_sentinel_urn_round_trips` is the guard on that, and
   `UrnDate.is_unknown` is how a caller tells year 0 from a real year.

Accent folding lives in `slugify_authority` and nowhere else. Cycle 1's
`normalize_text` deliberately does *not* fold (see `test_normalize.py`), so the
slug tests below are the only place the NFKD step is pinned.

Two behaviours documented here are true but surprising; both are marked at
their tests rather than hidden:

- `LEXML_URN_RE` validates a date's *shape*, not its *meaning*, so
  ``2018-13-45`` passes `is_valid_urn` and then makes `parse_urn` raise. The
  two functions disagree by design; `test_valid_shape_but_impossible_date`
  names the gap so it is a known limit rather than a surprise in Cycle 6.
- The locality field is a general slug segment, so it accepts municipal forms
  (``br;sp;sao.paulo``) without special-casing them, but equally accepts
  strings that are not real localities. See `test_urn_roundtrip_state_municipal`.
"""

from __future__ import annotations

import dataclasses

import pytest

from lexml_nonstat.model.urn import (
    LEXML_URN_RE,
    UrnDate,
    UrnParts,
    build_urn,
    is_valid_urn,
    parse_urn,
    slugify_authority,
)

# The canonical example from the module docstring and the cycle spec.
FEDERAL_URN = "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277"


# --------------------------------------------------------------------------
# Round-trip: build_urn → parse_urn recovers every part
# --------------------------------------------------------------------------


def test_urn_roundtrip_federal():
    """The reference shape, asserted part by part rather than as one string.

    Asserting only the joined string would let a swap of two fields pass if the
    rendering happened to match, so `parse_urn`'s view is checked field by
    field as well.
    """
    urn = build_urn(
        authority="ministerio.fazenda",
        doc_type="portaria",
        date=UrnDate(2018, 6, 7),
        number="277",
    )

    assert urn == FEDERAL_URN
    assert is_valid_urn(urn)

    parts = parse_urn(urn)

    assert parts.locality == "br"  # the default, never spelled at the call site
    assert parts.authority == "ministerio.fazenda"
    assert parts.doc_type == "portaria"
    assert parts.date == UrnDate(2018, 6, 7)
    assert parts.date.urn_repr == "2018-06-07"
    assert parts.date.iso == "2018-06-07"
    assert parts.date.is_full
    assert parts.number == "277"
    assert parts.fragment is None


def test_urn_roundtrip_state_municipal():
    """State and municipal localities round-trip — including the 3-part form.

    Verified empirically before being asserted: `LEXML_URN_RE`'s locality group
    is the same general slug segment used for authority, and that segment
    already allows ``;`` sub-parts. So ``br;sp;sao.paulo`` needs no special
    case and is accepted today.

    The limitation worth naming is the other side of that generality: the
    regex does not *know* localities. It would accept ``xx;yy;zz`` just as
    happily. Locality correctness is the caller's problem; this test pins only
    that the grammar does not stand in the way of the real forms.
    """
    # Municipality under a state, the fullest form.
    municipal = build_urn(
        locality="br;sp;sao.paulo",
        authority="camara.municipal",
        doc_type="lei.organica",
        date=UrnDate(1990, 4, 6),
        number="1",
    )
    assert municipal == "urn:lex:br;sp;sao.paulo:camara.municipal:lei.organica:1990-04-06;1"
    assert is_valid_urn(municipal)
    assert parse_urn(municipal).locality == "br;sp;sao.paulo"

    # Municipality named directly under the country, the 2-part form.
    two_part = build_urn(
        locality="br;sao.paulo",
        authority="prefeitura",
        doc_type="decreto",
        date=UrnDate(2020, 1, 2),
        number="5",
    )
    assert two_part == "urn:lex:br;sao.paulo:prefeitura:decreto:2020-01-02;5"
    assert parse_urn(two_part).locality == "br;sao.paulo"

    # A *state* authority, which is what the spec row actually asks for: the
    # authority slug, not just the locality, carries the federated entity.
    state = build_urn(
        locality="br;sp",
        authority="assembleia.legislativa.estado.sao.paulo",
        doc_type="resolucao",
        date=UrnDate(2015, 11, 30),
        number="42",
    )
    parts = parse_urn(state)

    assert parts.locality == "br;sp"
    assert parts.authority == "assembleia.legislativa.estado.sao.paulo"
    assert parts.doc_type == "resolucao"
    assert parts.date == UrnDate(2015, 11, 30)
    assert parts.number == "42"


def test_urn_year_only():
    """Year-only is a first-class date, not a degraded one.

    `pn_cst_38` (1980) is cited by year in practice; the reference parser
    models the same either/or. The URN carries a bare ``1980`` and `iso` is
    `None` because there is no ISO date to give.
    """
    urn = build_urn(
        authority="ministerio.fazenda",
        doc_type="parecer.normativo",
        date=UrnDate(1980),
        number="38",
    )

    assert urn == "urn:lex:br:ministerio.fazenda:parecer.normativo:1980;38"
    assert urn.endswith(":1980;38")

    parts = parse_urn(urn)

    assert parts.date == UrnDate(1980)
    assert parts.date.year == 1980
    assert parts.date.month is None
    assert parts.date.day is None
    assert not parts.date.is_full
    assert parts.date.iso is None
    assert parts.number == "38"


def test_urn_with_fragment():
    """The ``!fragment`` annex convention (plan §2.9), which Cycle 6 depends on.

    A sibling annex is the parent URN plus ``!anexo1``. The fragment must
    survive parsing as its own field — not be absorbed into the number — or
    Cycle 6's annex documents would collide with their parent.
    """
    urn = build_urn(
        authority="ministerio.fazenda",
        doc_type="portaria",
        date=UrnDate(2018, 6, 7),
        number="277",
        fragment="anexo1",
    )

    assert urn == FEDERAL_URN + "!anexo1"
    assert is_valid_urn(urn)

    parts = parse_urn(urn)

    assert parts.fragment == "anexo1"
    # The number is unaffected by the suffix.
    assert parts.number == "277"
    # Everything else still matches the fragment-less parent.
    parent = parse_urn(FEDERAL_URN)
    assert dataclasses.replace(parts, fragment=None) == parent


def test_fragment_is_dropped_when_falsy():
    """`build_urn` appends only a truthy fragment, so `None` and `""` agree.

    Pinned because a stray ``!`` would make the URN unparseable, and an empty
    fragment is the easy way to produce one from a caller that defaults to "".
    """
    kwargs = dict(
        authority="ministerio.fazenda",
        doc_type="portaria",
        date=UrnDate(2018, 6, 7),
        number="277",
    )

    assert build_urn(fragment=None, **kwargs) == FEDERAL_URN
    assert build_urn(fragment="", **kwargs) == FEDERAL_URN
    assert not is_valid_urn(FEDERAL_URN + "!")


def test_number_complement_round_trips():
    """``277-1`` is the reference parser's rendering of a "Portaria 277-A".

    The complement is part of the number, not a fragment, so it must come back
    from `parse_urn` attached to the number.
    """
    urn = build_urn(
        authority="ministerio.fazenda",
        doc_type="portaria",
        date=UrnDate(2018, 6, 7),
        number="277-1",
    )

    assert urn == "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277-1"
    assert parse_urn(urn).number == "277-1"


def test_authority_subtype_round_trips():
    """An authority may carry a ``;`` sub-organ, e.g. a secretaria under a
    ministério. The ``;`` inside the authority must not be confused with the
    ``;`` that introduces the number."""
    urn = "urn:lex:br:ministerio.fazenda;secretaria.receita.federal:portaria:2018;38"
    parts = parse_urn(urn)

    assert parts.authority == "ministerio.fazenda;secretaria.receita.federal"
    assert parts.number == "38"
    assert parts.date == UrnDate(1980 + 38)  # 2018, written this way to stay obvious


def test_parse_urn_tolerates_surrounding_whitespace():
    """`parse_urn` and `is_valid_urn` both strip, because URNs arriving from
    extracted document text routinely carry padding."""
    padded = f"  {FEDERAL_URN}  "

    assert is_valid_urn(padded)
    assert parse_urn(padded) == parse_urn(FEDERAL_URN)


def test_parse_urn_returns_urnparts():
    """The return type is the frozen dataclass, so callers can rely on equality
    and on it not mutating under them."""
    parts = parse_urn(FEDERAL_URN)

    assert isinstance(parts, UrnParts)
    with pytest.raises(dataclasses.FrozenInstanceError):
        parts.number = "999"  # type: ignore[misc]


# --------------------------------------------------------------------------
# slugify_authority — the NFKD fold Cycle 1 flagged
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "raw", "expected"),
    [
        # The two cases named explicitly in the cycle spec.
        ("spec example, all caps + accent", "MINISTÉRIO DA FAZENDA", "ministerio.fazenda"),
        ("hyphen becomes a dot", "Advocacia-Geral da União", "advocacia.geral.uniao"),
        # Accents of every kind the corpus contains, folded to bare ASCII.
        ("cedilla and tilde", "Superior Tribunal de Justiça", "superior.tribunal.justica"),
        ("circumflex", "Câmara dos Deputados", "camara.deputados"),
        (
            "several stopwords dropped",
            "Procuradoria-Geral da Fazenda Nacional",
            "procuradoria.geral.fazenda.nacional",
        ),
        (
            "'de' and 'do' both dropped",
            "Secretaria da Receita Federal do Brasil",
            "secretaria.receita.federal.brasil",
        ),
        ("case lowered, no stopwords present", "Senado Federal", "senado.federal"),
        (
            "long name, mixed connectives",
            "Conselho Administrativo de Recursos Fiscais",
            "conselho.administrativo.recursos.fiscais",
        ),
        # "dos" is a stopword, so "São José dos Campos" loses it — matching the
        # reference vocabulary's "camara.deputados", never "camara.dos.deputados".
        (
            "municipal name, 'dos' dropped",
            "Prefeitura Municipal de São José dos Campos",
            "prefeitura.municipal.sao.jose.campos",
        ),
        ("already a slug, unchanged", "ministerio.fazenda", "ministerio.fazenda"),
        # Punctuation is a word boundary like any other, so parentheses vanish
        # and the acronym survives as its own word.
        ("parentheses split, not kept", "Advocacia-Geral da União (AGU)", "advocacia.geral.uniao.agu"),
        ("runs of spaces do not make empty words", "  espaços   múltiplos  ", "espacos.multiplos"),
        # NFKD decomposes the ordinal indicator "º" to "o", which is a stopword
        # and is therefore dropped; digits are kept as words.
        ("ordinal folded then dropped as a stopword", "Nº 1 Órgão", "1.orgao"),
        ("all stopwords collapses to empty", "A E O DA", ""),
        ("empty in, empty out", "", ""),
    ],
)
def test_slugify_authority(label, raw, expected):
    """NFKD fold → lowercase → drop connectives → join with dots.

    Every expectation was produced by running the function and then checked
    against the convention it is meant to follow, rather than the reverse.
    """
    assert slugify_authority(raw) == expected, label


@pytest.mark.parametrize(
    "raw",
    [
        "MINISTÉRIO DA FAZENDA",
        "Advocacia-Geral da União",
        "Prefeitura Municipal de São José dos Campos",
        "Conselho Administrativo de Recursos Fiscais",
    ],
)
def test_slug_output_is_ascii_and_urn_safe(raw):
    """Whatever goes in, the slug must be usable as a URN segment.

    This is the property the individual cases above only sample: the output is
    pure lowercase ASCII, and `LEXML_URN_RE` accepts it in the authority slot.
    """
    slug = slugify_authority(raw)

    assert slug.isascii()
    assert slug == slug.lower()
    assert is_valid_urn(
        build_urn(authority=slug, doc_type="parecer", date=UrnDate(2018), number="1")
    )


def test_slugify_is_idempotent():
    """A slug fed back in is unchanged — `metadata.py` may slugify a value that
    was already slugified, and that must not erode it."""
    for raw in ["MINISTÉRIO DA FAZENDA", "Advocacia-Geral da União", "Senado Federal"]:
        once = slugify_authority(raw)
        assert slugify_authority(once) == once


# --------------------------------------------------------------------------
# The grammar's negative space
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "urn"),
    [
        ("no scheme at all", "ministerio.fazenda:portaria:2018-06-07;277"),
        ("scheme missing 'urn:'", "lex:br:ministerio.fazenda:portaria:2018-06-07;277"),
        ("scheme uppercased", "URN:LEX:br:ministerio.fazenda:portaria:2018-06-07;277"),
        ("empty authority", "urn:lex:br::portaria:2018-06-07;277"),
        ("empty locality", "urn:lex::ministerio.fazenda:portaria:2018-06-07;277"),
        ("doc_type missing entirely", "urn:lex:br:ministerio.fazenda:2018-06-07;277"),
        # Dates are zero-padded or not accepted; "2018-6-7" is the shape a
        # naive f-string produces, so it is the one most likely to appear.
        ("date not zero-padded", "urn:lex:br:ministerio.fazenda:portaria:2018-6-7;277"),
        ("two-digit year", "urn:lex:br:ministerio.fazenda:portaria:18-06-07;277"),
        ("date with slashes", "urn:lex:br:ministerio.fazenda:portaria:07/06/2018;277"),
        ("year and month only", "urn:lex:br:ministerio.fazenda:portaria:2018-06;277"),
        ("no number and no ';'", "urn:lex:br:ministerio.fazenda:portaria:2018-06-07"),
        ("';' present but number empty", "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;"),
        ("non-numeric number", "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;abc"),
        # Uppercase anywhere in a slug: the vocabulary is lowercase.
        ("uppercase locality and authority", "urn:lex:BR:MINISTERIO.FAZENDA:portaria:2018-06-07;277"),
        ("title-cased authority", "urn:lex:br:Ministerio.Fazenda:portaria:2018-06-07;277"),
        ("space inside authority", "urn:lex:br:ministerio fazenda:portaria:2018-06-07;277"),
        ("trailing junk after number", "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277 extra"),
        ("uppercase fragment", "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277!Anexo1"),
        ("hyphen in fragment", "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277!anexo-1"),
        ("empty fragment after '!'", "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;277!"),
        ("empty string", ""),
        ("whitespace only", "   "),
    ],
)
def test_is_valid_urn_negatives(label, urn):
    """Malformed URNs are rejected, and `parse_urn` refuses the same inputs.

    The two must agree: anything `is_valid_urn` calls false, `parse_urn` must
    raise on, or callers that check-then-parse would hit a different failure
    mode than the one they guarded against.
    """
    assert not is_valid_urn(urn), label
    assert LEXML_URN_RE.match(urn.strip()) is None, label

    with pytest.raises(ValueError):
        parse_urn(urn)


def test_parse_urn_error_names_the_input():
    """The message has to identify what failed — these URNs are produced deep
    in a batch run over 15 documents, and "invalid URN" alone is not actionable.
    """
    with pytest.raises(ValueError, match="not a LexML URN"):
        parse_urn("nonsense")


def test_valid_shape_but_impossible_date():
    """DOCUMENTED SURPRISE: `is_valid_urn` and `parse_urn` disagree here.

    `LEXML_URN_RE` checks the date's *shape* (``\\d{4}-\\d{2}-\\d{2}``) and
    nothing more, so ``2018-13-45`` matches the grammar. `parse_urn` then goes
    on to build a `UrnDate`, whose `__post_init__` rejects month 13 — so this
    input is "valid" and unparseable at the same time.

    That is a real limit of the two-layer design, not a bug this test papers
    over: the regex has no way to express calendar validity. Pinned so that a
    caller doing ``if is_valid_urn(u): parse_urn(u)`` knows the guard is not
    total, and so that anyone who later tightens the regex sees this test go
    red rather than discovering the overlap by accident.
    """
    impossible = "urn:lex:br:ministerio.fazenda:portaria:2018-13-45;277"

    assert is_valid_urn(impossible)  # the *shape* is fine

    with pytest.raises(ValueError, match="month out of range"):
        parse_urn(impossible)


def test_build_urn_requires_authority_and_doc_type():
    """Date and number have sentinels; authority and type do not.

    A URN without an authority names nothing at all, so this is the one place
    `build_urn` refuses rather than inventing a placeholder.
    """
    with pytest.raises(ValueError, match="authority is required"):
        build_urn(authority="", doc_type="portaria", date=UrnDate(2018), number="1")

    with pytest.raises(ValueError, match="doc_type is required"):
        build_urn(authority="ministerio.fazenda", doc_type="", date=UrnDate(2018), number="1")


# --------------------------------------------------------------------------
# UrnDate
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2018-06-07", UrnDate(2018, 6, 7)),
        ("2018", UrnDate(2018)),
        ("1980", UrnDate(1980)),
        ("0000", UrnDate(0)),  # the sentinel, readable back out of a URN
        (" 2018 ", UrnDate(2018)),  # stripped before matching
    ],
)
def test_urn_date_from_string_parses(text, expected):
    parsed = UrnDate.from_string(text)

    assert parsed == expected
    # Round-trip: whatever `from_string` accepts, `urn_repr` reproduces.
    assert parsed is not None and parsed.urn_repr == text.strip()


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("empty", ""),
        ("not a date", "junk"),
        ("year and month only", "2018-06"),
        ("unseparated", "20180607"),
        ("Brazilian written form", "07/06/2018"),
        ("not zero-padded", "2018-6-7"),
        ("two digits", "18"),
        ("five digits", "20188"),
        ("trailing text", "2018-06-07 extra"),
    ],
)
def test_urn_date_from_string_returns_none_for_junk(label, text):
    """`from_string` answers `None` rather than raising: it is used to *test*
    whether a string is a date, and exceptions would be the wrong channel.

    Note the division of labour with `__post_init__` below — `from_string`
    returns `None` for anything of the wrong *shape*, while out-of-range values
    that have the right shape still raise.
    """
    assert UrnDate.from_string(text) is None, label


@pytest.mark.parametrize(
    ("label", "args", "message"),
    [
        ("day without month", (2018, None, 7), "a day without a month is not a date"),
        ("year below range", (-1,), "year out of range"),
        ("year above range", (10000,), "year out of range"),
        ("month zero", (2018, 0), "month out of range"),
        ("month above 12", (2018, 13), "month out of range"),
        ("day zero", (2018, 6, 0), "day out of range"),
        ("day above 31", (2018, 6, 32), "day out of range"),
    ],
)
def test_urn_date_rejects_impossible_values(label, args, message):
    """`__post_init__` is the only validation a frozen dataclass gets."""
    with pytest.raises(ValueError, match=message):
        UrnDate(*args)


@pytest.mark.parametrize(
    ("label", "args"),
    [
        ("year 0 is the sentinel, not an error", (0,)),
        ("lowest real year", (1,)),
        ("highest year", (9999,)),
        ("first day of a year", (2018, 1, 1)),
        ("last day of a year", (2018, 12, 31)),
        # Day-of-month is bounded at 31 regardless of the month: the check is
        # on the *field*, not the calendar, so 31 February is accepted.
        ("31 February is not caught", (2018, 2, 31)),
    ],
)
def test_urn_date_accepts_boundary_values(label, args):
    assert UrnDate(*args).year >= 0, label


def test_urn_date_is_frozen():
    """Frozen because a `UrnDate` is shared by `Metadata` and the URN built
    from it; mutating one would desynchronise them."""
    date = UrnDate(2018, 6, 7)

    with pytest.raises(dataclasses.FrozenInstanceError):
        date.year = 1999  # type: ignore[misc]


@pytest.mark.parametrize(
    ("label", "date", "urn_repr", "is_full", "iso"),
    [
        ("full date, zero-padded", UrnDate(2018, 6, 7), "2018-06-07", True, None),
        ("year only", UrnDate(1980), "1980", False, None),
        ("year is padded to four digits", UrnDate(38), "0038", False, None),
        ("sentinel", UrnDate(0), "0000", False, None),
    ],
)
def test_urn_date_rendering(label, date, urn_repr, is_full, iso):
    """`urn_repr` always zero-pads; `iso` exists only for a complete date."""
    assert date.urn_repr == urn_repr, label
    assert date.is_full is is_full, label
    # `iso` mirrors `urn_repr` when full and is None otherwise.
    assert date.iso == (urn_repr if is_full else None), label


@pytest.mark.parametrize(
    "date",
    [UrnDate(2018, 6, 7), UrnDate(1980), UrnDate(0), UrnDate(2018, 12, 31)],
)
def test_urn_date_dict_round_trip(date):
    """`to_dict`/`from_dict` back the metadata goldens, so identity matters.

    Absent components are omitted from the dict rather than stored as `None`,
    which is what keeps a year-only date's JSON a single key.
    """
    as_dict = date.to_dict()

    assert UrnDate.from_dict(as_dict) == date
    assert ("month" in as_dict) is (date.month is not None)
    assert ("day" in as_dict) is (date.day is not None)


# --------------------------------------------------------------------------
# The sentinel path
# --------------------------------------------------------------------------


def test_sentinel_urn_round_trips():
    """A document with no date and no number still gets a usable URN.

    Decision #2 of the cycle spec: never raise, emit a syntactically valid URN
    and flag incompleteness elsewhere. That promise is only kept if the
    sentinel survives this module's own parser — so the assertion is not just
    that `build_urn` produces ``0000;0``, but that `parse_urn` reads it back.

    `is_unknown` is the honest part: year 0 is distinguishable from a real
    year, so a caller can never mistake the sentinel for a document dated in
    the year zero, and `iso` refuses to render it as a date.
    """
    urn = build_urn(authority="conselho.administrativo.recursos.fiscais",
                    doc_type="sumula", date=None, number=None)

    assert urn == "urn:lex:br:conselho.administrativo.recursos.fiscais:sumula:0000;0"
    assert urn.endswith(":0000;0")
    assert is_valid_urn(urn)

    parts = parse_urn(urn)

    assert parts.date == UrnDate(0)
    assert parts.date.is_unknown
    assert parts.date.iso is None  # not a date, and does not pretend to be
    assert parts.number == "0"
    assert parts.authority == "conselho.administrativo.recursos.fiscais"


@pytest.mark.parametrize(
    ("label", "date", "number", "expected_tail"),
    [
        ("both missing", None, None, "0000;0"),
        ("empty number string is also a sentinel", UrnDate(1980), "", "1980;0"),
        ("date missing, number known", None, "38", "0000;38"),
        ("date known, number missing", UrnDate(2018, 6, 7), None, "2018-06-07;0"),
    ],
)
def test_sentinel_substitution_is_per_field(label, date, number, expected_tail):
    """The two sentinels are independent — a document may state one and not the
    other, and the known half must not be discarded with the unknown one."""
    urn = build_urn(authority="ministerio.fazenda", doc_type="portaria",
                    date=date, number=number)

    assert urn.endswith(expected_tail), label
    assert is_valid_urn(urn), label


def test_only_the_sentinel_year_is_unknown():
    """`is_unknown` must be exactly "year 0", or it would swallow real dates."""
    assert UrnDate(0).is_unknown
    assert not UrnDate(1980).is_unknown
    assert not UrnDate(2018, 6, 7).is_unknown
    assert not UrnDate(1).is_unknown
