"""The `linkertool` co-process — the wire protocol, pinned.

Two groups. The first needs the binary and is marked `requires_linker`: it
pins what the live linker actually answers, including the one thing that would
otherwise fail silently (A-L.9's context rule). The second needs nothing and
covers the failure modes, because "never raises" is a claim that has to be
tested with things that would otherwise raise.
"""

from __future__ import annotations

import pytest

from lexml_nonstat.refs import (
    DEFAULT_CONTEXT_URN,
    END_MARKER,
    LinkerCache,
    LinkertoolLinker,
    Reference,
    cache_key,
)
from lexml_nonstat.refs.linkertool import _spans_of

from tests.conftest import requires_linker

#: The linker README's own worked example.
_README_SENTENCE = (
    "Os incisos I e III do par. 3o do art. 8o da Lei n.o. 12.527, "
    "de 18 de novembro de 2011"
)

#: A sentence from the shape this corpus actually contains.
_CORPUS_SENTENCE = (
    "A Lei nº 7.713, de 22 de dezembro de 1988 & o Decreto-lei nº 200, "
    'de 1967 são "normas".'
)


@pytest.fixture
def live_linker():
    """A real co-process, closed afterwards even if the test fails."""
    linker = LinkertoolLinker()
    try:
        yield linker
    finally:
        linker.close()


# ---------------------------------------------------------------------------
# With the binary (A-L.5: skipped, never failed, where it is absent)
# ---------------------------------------------------------------------------


@requires_linker
def test_the_readme_example_resolves(live_linker):
    """T-L1 — the linker's own documented example, end to end."""
    references = live_linker.find_refs(_README_SENTENCE)
    urns = {r.urn for r in references}

    assert "urn:lex:br:federal:lei:2011-11-18;12527!art8_par3_inc1" in urns
    assert "urn:lex:br:federal:lei:2011-11-18;12527!art8_par3_inc3" in urns


@requires_linker
def test_spans_address_the_text_we_sent(live_linker):
    """T-L2 — the offsets are exact, through entity escaping and accents.

    The linker's reply is XML-escaped (`&amp;`, `&quot;`) and the input is
    Portuguese, so a naive string-index would be wrong on both counts. This is
    the assertion that catches it: it compares against the **input**, not
    against another copy of the output, which is the lesson of Cycle 8's
    mojibake defect that conservation structurally could not see.
    """
    references = live_linker.find_refs(_CORPUS_SENTENCE)

    assert references, "the corpus sentence cites two statutes"
    for reference in references:
        assert _CORPUS_SENTENCE[reference.start : reference.end] == reference.text


@requires_linker
def test_the_corpus_sentence_resolves_both_norms(live_linker):
    urns = {r.urn for r in live_linker.find_refs(_CORPUS_SENTENCE)}

    assert "urn:lex:br:federal:lei:1988-12-22;7713" in urns
    assert "urn:lex:br:federal:decreto.lei:1967;200" in urns


@requires_linker
def test_a_paragraph_with_no_citation_resolves_nothing(live_linker):
    assert live_linker.find_refs("Sem citação alguma neste parágrafo.") == ()


@requires_linker
def test_the_same_question_answers_the_same_way_twice(live_linker):
    """T-L3 — invariant #4, within one process."""
    first = live_linker.find_refs(_CORPUS_SENTENCE)
    second = live_linker.find_refs(_CORPUS_SENTENCE)

    assert first == second
    assert live_linker.spawns == 1, "the co-process is reused, not respawned"


@requires_linker
def test_the_same_question_answers_the_same_way_in_a_fresh_process():
    """T-L3 — invariant #4, **across** process restarts.

    A cache would hide a non-deterministic backend, so this asks two genuinely
    separate children.
    """
    first_linker = LinkertoolLinker()
    second_linker = LinkertoolLinker()
    try:
        assert first_linker.find_refs(_CORPUS_SENTENCE) == second_linker.find_refs(
            _CORPUS_SENTENCE
        )
    finally:
        first_linker.close()
        second_linker.close()


@requires_linker
def test_a_non_federal_authority_context_resolves_nothing(live_linker):
    """T-L4 — A-L.9's measurement, pinned as a regression.

    This is the cycle's load-bearing finding. Passing a document's own URN as
    `--contexto` makes the linker return the fragment **unchanged**, silently:
    a rejected context is indistinguishable from a paragraph that cites
    nothing. Every one of the 15 samples carries such an authority.

    Pinned so that a linker which later *learns* these authorities shows up as
    a failing test — a finding to act on — rather than as a silent improvement
    nobody notices.
    """
    own_urn = "urn:lex:br:ministerio.fazenda;secretaria.receita.federal:parecer:2000-06-29;26"

    assert live_linker.find_refs(_CORPUS_SENTENCE, own_urn) == ()
    assert live_linker.find_refs(_CORPUS_SENTENCE, DEFAULT_CONTEXT_URN) != ()


@requires_linker
def test_a_non_statutory_type_and_the_year_sentinel_are_both_accepted(live_linker):
    """A-L.9's other half: what A-L.8 predicted would break, does not.

    The `;`-joined authority is the only breaking component — a non-statutory
    *type* token and A-2.3's `0000` sentinel both link normally. Recorded so
    the amendment's reasoning stays checkable.
    """
    assert live_linker.find_refs(
        _CORPUS_SENTENCE, "urn:lex:br:federal:ato.declaratorio:2018-06-07;277"
    )
    assert live_linker.find_refs(_CORPUS_SENTENCE, "urn:lex:br:federal:lei:0000;277")


@requires_linker
def test_a_killed_process_respawns_rather_than_raising(live_linker):
    """T-L5 — availability survives the child dying mid-run."""
    assert live_linker.find_refs(_CORPUS_SENTENCE)
    assert live_linker.spawns == 1

    live_linker.close()

    assert live_linker.find_refs(_CORPUS_SENTENCE)
    assert live_linker.spawns == 2


@requires_linker
def test_a_warm_cache_is_consulted_before_the_process(tmp_path):
    """T-L6 — a cache hit spawns nothing. This is A-L.6's whole mechanism."""
    cache = LinkerCache(tmp_path)
    warm = LinkertoolLinker(cache=cache)
    try:
        references = warm.find_refs(_CORPUS_SENTENCE)
        assert warm.spawns == 1
    finally:
        warm.close()

    cold = LinkertoolLinker(cache=LinkerCache(tmp_path, read_only=True))
    try:
        assert cold.find_refs(_CORPUS_SENTENCE) == references
        assert cold.spawns == 0, "a recorded answer must not start a process"
    finally:
        cold.close()


@requires_linker
def test_recorded_answers_survive_the_binary_going_away(tmp_path):
    """The fixtures-only guarantee, stated as a test.

    A linker whose binary cannot be found still answers from the cache — which
    is why the linked goldens compare on a checkout with no `linkertool`.
    """
    cache = LinkerCache(tmp_path)
    warm = LinkertoolLinker(cache=cache)
    try:
        expected = warm.find_refs(_CORPUS_SENTENCE)
    finally:
        warm.close()

    absent = LinkertoolLinker("", cache=LinkerCache(tmp_path, read_only=True))
    assert absent.find_refs(_CORPUS_SENTENCE) == expected
    assert absent.spawns == 0


# ---------------------------------------------------------------------------
# Without the binary — "never raises" tested with things that would raise
# ---------------------------------------------------------------------------


def test_a_missing_binary_answers_empty_rather_than_raising():
    """The protocol's contract: degrade quality, never availability."""
    linker = LinkertoolLinker("/nonexistent/linkertool")

    assert linker.find_refs(_CORPUS_SENTENCE) == ()
    assert linker.spawns == 0


def test_blank_text_is_never_asked():
    """No process for a paragraph with nothing in it."""
    linker = LinkertoolLinker("/nonexistent/linkertool")

    assert linker.find_refs("") == ()
    assert linker.find_refs("   \n ") == ()


def test_close_is_idempotent_and_safe_on_a_linker_that_never_ran():
    linker = LinkertoolLinker("/nonexistent/linkertool")
    linker.close()
    linker.close()


def test_a_fixture_miss_answers_empty_without_a_process(tmp_path):
    """`--linker=fixtures` is structurally incapable of spawning."""
    linker = LinkertoolLinker("", cache=LinkerCache(tmp_path, read_only=True))

    assert linker.find_refs("nunca gravado") == ()
    assert linker.spawns == 0


def test_the_end_marker_is_the_reference_parsers_marker():
    """The framing token both sides write (`LinkerTool.hs`)."""
    assert END_MARKER == "###LEXML-END###"


# ---------------------------------------------------------------------------
# Reply parsing — the three things measurement revealed
# ---------------------------------------------------------------------------


def _parse(reply: str, text: str) -> tuple[Reference, ...]:
    return LinkertoolLinker("/nonexistent/linkertool")._parse_reply(reply, text)


def test_a_reply_using_an_undeclared_prefix_still_parses():
    """Measured: the linker never declares the `xlink` prefix it writes.

    Parsing its reply directly raises `XMLSyntaxError`, so the reply is wrapped
    in a prefix-declaring root first. Without this the backend would resolve
    nothing at all, on every paragraph.
    """
    text = "ver Lei nº 7.713 aqui"
    reply = (
        '<p>ver <span xlink:href="urn:lex:br:federal:lei:1988;7713">'
        "Lei nº 7.713</span> aqui</p>"
    )

    references = _parse(reply, text)
    assert len(references) == 1
    assert references[0] == Reference(4, 16, "urn:lex:br:federal:lei:1988;7713", "Lei nº 7.713")


def test_offsets_are_counted_in_decoded_characters():
    """Escaping in the reply must not shift a span (measured hazard)."""
    text = 'a & b Lei nº 7.713 "x"'
    reply = (
        '<p>a &amp; b <span xlink:href="urn:u">Lei nº 7.713</span> &quot;x&quot;</p>'
    )

    (reference,) = _parse(reply, text)
    assert text[reference.start : reference.end] == "Lei nº 7.713"


def test_a_span_that_does_not_match_the_input_is_discarded():
    """A URN over the wrong words is worse than no URN.

    If the linker echoes something other than what we sent — a normalisation, a
    dropped entity, a bug — the offsets are meaningless, so the reference is
    dropped rather than emitted against text it was not resolved from.
    """
    text = "ver Lei nº 7.713 aqui"
    reply = '<p>ver <span xlink:href="urn:u">OUTRA COISA</span> aqui</p>'

    assert _parse(reply, text) == ()


def test_a_span_reaching_past_the_text_is_discarded():
    text = "curto"
    reply = '<p><span xlink:href="urn:u">curto e muito mais longo</span></p>'

    assert _parse(reply, text) == ()


def test_a_span_without_an_href_is_ignored():
    text = "ver Lei aqui"
    reply = "<p>ver <span>Lei</span> aqui</p>"

    assert _parse(reply, text) == ()


def test_an_unparseable_reply_is_empty_not_an_exception():
    assert _parse("<p>unclosed", "qualquer texto") == ()
    assert _parse("", "qualquer texto") == ()


def test_references_come_back_sorted():
    text = "A Lei nº 1 e o Decreto nº 2"
    reply = (
        '<p>A <span xlink:href="urn:a">Lei nº 1</span> e o '
        '<span xlink:href="urn:b">Decreto nº 2</span></p>'
    )

    references = _parse(reply, text)
    assert [r.start for r in references] == sorted(r.start for r in references)


def test_nested_spans_are_not_double_counted():
    """The linker wraps a citation once; a span inside a span would double-count."""
    element_text = "Lei nº 7.713"
    reply = (
        '<p><span xlink:href="urn:outer">'
        '<span xlink:href="urn:inner">Lei nº 7.713</span></span></p>'
    )

    references = _parse(reply, element_text)
    assert len(references) == 1
    assert references[0].urn == "urn:outer"


def test_spans_of_counts_through_unrelated_markup():
    """`_spans_of` walks the tree, so `<b>` between spans cannot shift offsets."""
    from lxml import etree

    root = etree.fromstring(
        '<r xmlns:xlink="http://www.w3.org/1999/xlink">'
        "<p>a <b>bold</b> c <span xlink:href=\"urn:u\">Lei</span></p></r>".encode(
            "utf-8"
        )
    )

    # "a bold c " is nine characters — the `<b>` contributes its text and no
    # markup, which is the property being asserted.
    ((start, end, urn, inner),) = _spans_of(root)
    assert (start, end, inner) == (9, 12, "Lei")
    assert "".join(root.itertext())[start:end] == "Lei"
