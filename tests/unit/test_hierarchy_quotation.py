"""The quotation guard — the regression suite the cycle exists for.

A parecer that quotes the Constitution must never be published as a document
whose ``Art. 40`` is its own. Plan §2.5 counted the damage a naive
paragraph-initial ``Art. N`` rule does: ``parecer_93`` alone carries 25 such
matches in its body and **every one of them is quoted statute**. Articulating
them would put the Constitution's ``Art. 40`` inside a legal opinion, and
nothing downstream could tell that the document had been misread.

What this file protects, in order of severity:

* **No quoted article becomes structure.** A missed quotation costs nothing —
  the paragraph stays in the tree as prose. A quoted article promoted to a
  ``Section`` is a fabrication (plan §9.2, invariant "no fabricated
  structure"), and it is silent.
* **The band rules keep their reasons.** ``parecer_93`` needs the *declared*
  rule and ``sumula_stj_125`` the *deviation* rule; a document with neither
  must get ``rule == "none"`` rather than a band invented out of noise.
* **Style beats indent.** Word's own outline level is an authorial
  declaration. Without that precedence ``sumula_stj_125``'s centred ``EMENTA``
  headings fall inside its deviation band and the document loses half its
  structure.
* **The pure predicates hold their grammar** without a sample in sight, so a
  regression in them is localised instead of surfacing as a mysterious tree
  diff on one document.

The corpus is 15 documents standing in for 300+ unseen ones, so the assertions
below aim at a rule's *reason* wherever a sample's exact output would do.
"""

from __future__ import annotations

import pytest

from lexml_nonstat.hierarchy import infer_hierarchy
from lexml_nonstat.hierarchy.labels import ARTICLE_RE
from lexml_nonstat.hierarchy.quotation import (
    DECLARED_BAND_TOLERANCE,
    MIN_BAND_PARAGRAPHS,
    QUOTE_INDENT_MARGIN,
    SERIES_MAX_GAP,
    SERIES_START_MAX,
    QuotationAnalysis,
    analyse_quotation,
    carries_omissis,
    detect_quote_bands,
    is_monotonic_series,
    is_omissis,
    names_external_norm,
    opens_with_quote,
)
from lexml_nonstat.ingest import Inline, StyledPara, read_docx
from lexml_nonstat.model import extract_metadata
from lexml_nonstat.segment import segment_document

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"

#: Every sample in the corpus, by stem.
SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

PARECER_93 = "parecer_93_2018_decor_cgu_agu"
PAR_COSIT_26 = "par_cosit_26_20000629"
SUMULA_STJ_125 = "sumula_stj_125"
CARNE_LEAO = "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO"

#: ``parecer_93``'s quote band sits one twip *below* its modal body indent.
PARECER_93_BODY_INDENT = 2909
PARECER_93_QUOTE_INDENT = 2908


class Parsed:
    """One sample, parsed once: the pipeline's own view of its body."""

    __slots__ = ("name", "doc", "segmentation", "paras", "result", "analysis")

    def __init__(self, name: str) -> None:
        path = SAMPLES_DIR / f"{name}.docx"
        self.name = name
        self.doc = read_docx(path)
        metadata = extract_metadata(self.doc, filename=path.name)
        self.segmentation = segment_document(self.doc, metadata=metadata)
        self.result = infer_hierarchy(
            self.doc, metadata=metadata, segmentation=self.segmentation
        )
        # The exact paragraph list `build_tree` analyses: the body span, empty
        # paragraphs dropped. Analysing anything else would test a document the
        # pipeline never sees.
        blocks = {b.index: b for b in self.doc.blocks}
        span = self.segmentation.body
        body = [blocks[i] for i in span.indices if i in blocks] if span else []
        self.paras: tuple[StyledPara, ...] = tuple(
            b for b in body if isinstance(b, StyledPara) and not b.is_empty
        )
        self.analysis: QuotationAnalysis = analyse_quotation(self.paras)

    def para(self, index: int) -> StyledPara:
        return next(p for p in self.paras if p.index == index)

    def text(self, index: int) -> str:
        return self.para(index).text.strip()


@pytest.fixture(scope="session")
def sample():
    """Parse each sample at most once — ``parecer_93`` alone is 428 blocks."""
    cache: dict[str, Parsed] = {}

    def load(name: str) -> Parsed:
        if name not in cache:
            cache[name] = Parsed(name)
        return cache[name]

    return load


def styled(index: int, indent: int, *, declared: bool = True) -> StyledPara:
    """A minimal paragraph carrying nothing but an indent — band detection input."""
    return StyledPara(
        inlines=(Inline("x"),),
        indent_effective=indent,
        indent_direct=indent if declared else None,
        index=index,
    )


# ---------------------------------------------------------------------------
# Band detection
# ---------------------------------------------------------------------------


def test_parecer_93_uses_declared_rule(sample) -> None:
    """Amendment A-4.1: a plain deviation test cannot find this band.

    ``parecer_93``'s quote band is 2908 and its modal body indent is 2909 — the
    quoted material sits ONE TWIP BELOW ordinary prose, so "further in than the
    body" is not merely too weak here, it points the wrong way. What actually
    separates the two is provenance: body text *inherits* 2909 from the
    ``Normal`` style, while every quoted paragraph *declares* its own indent
    directly. Retuning ``QUOTE_INDENT_MARGIN`` will never recover this
    document; only the declared/inherited distinction does.
    """
    bands = sample(PARECER_93).analysis.bands

    assert bands.rule == "declared"
    assert bands.field == "indent_direct"
    assert bands.body_indent == PARECER_93_BODY_INDENT
    assert PARECER_93_QUOTE_INDENT in bands.quote_values
    # The band is a cluster, not a value: a hand-dragged Word ruler leaves 2879,
    # 2880, 2908, 2930 behind, and all of them are the same quotation.
    assert len(bands.quote_values) > 1
    assert max(bands.quote_values) - min(bands.quote_values) <= 2 * DECLARED_BAND_TOLERANCE


def test_sumula_stj_125_uses_deviation_rule(sample) -> None:
    """The straightforward case still has to work: quotes visibly further in."""
    bands = sample(SUMULA_STJ_125).analysis.bands

    assert bands.rule == "deviation"
    assert bands.body_indent == 893
    assert bands.field == "indent_effective"
    assert all(v >= 893 + QUOTE_INDENT_MARGIN for v in bands.quote_values)


@pytest.mark.parametrize(
    "name",
    [PAR_COSIT_26, "pn_cst_38_19801031", "port_mf_454_19770825", CARNE_LEAO,
     "port_mf_277_20180607"],
    ids=["par_cosit_26", "pn_cst_38", "port_mf_454", "CARNE_LEAO", "port_mf_277"],
)
def test_no_band_on_flat_documents(sample, name: str) -> None:
    """A document with no block quotes must get no band, not a band from noise.

    Inventing one here would convict ordinary prose of being quoted and cost
    these documents their sections — ``pn_cst_38``'s 35 and ``port_mf_454``'s
    15 among them.
    """
    bands = sample(name).analysis.bands

    assert bands.rule == "none"
    assert bands.quote_values == frozenset()
    assert not any(bands.contains(p) for p in sample(name).paras)


def test_band_needs_minimum_paragraphs() -> None:
    """Two deviating paragraphs are an accident; a band needs a population.

    ``MIN_BAND_PARAGRAPHS`` is what stops a stray centred line or a single
    hand-indented aside from redefining a whole document as quotation.
    """
    body = [styled(i, 0, declared=False) for i in range(10)]
    deviating = [styled(10, 1000), styled(11, 1000)]

    assert len(deviating) < MIN_BAND_PARAGRAPHS
    assert detect_quote_bands(body + deviating).rule == "none"

    # One more, and it is a band — the threshold, not the mechanism, is what
    # rejected the pair above.
    assert detect_quote_bands(body + deviating + [styled(12, 1000)]).rule == "deviation"


def test_declared_rule_needs_inherited_modal() -> None:
    """The declared rule reads provenance, so it must not fire without it.

    A-4.1's discriminator only means anything when the modal indent is
    *inherited* from the style. Where body paragraphs declare their own indent
    too, "declares an indent" separates nothing, and the rule must decline
    rather than pick the larger cluster and call it a quotation.
    """
    quoted = [styled(i, PARECER_93_QUOTE_INDENT) for i in range(10, 14)]

    # Modal paragraphs declare their indent: no provenance signal, no rule.
    all_declared = [styled(i, PARECER_93_BODY_INDENT) for i in range(10)]
    bands = detect_quote_bands(all_declared + quoted)
    assert bands.rule == "none"
    assert bands.body_indent == PARECER_93_BODY_INDENT

    # Same geometry, modal indent inherited: now the rule fires. The only thing
    # that changed is where the modal number came from.
    inherited = [styled(i, PARECER_93_BODY_INDENT, declared=False) for i in range(10)]
    bands = detect_quote_bands(inherited + quoted)
    assert bands.rule == "declared"
    assert bands.field == "indent_direct"
    assert PARECER_93_QUOTE_INDENT in bands.quote_values


# ---------------------------------------------------------------------------
# parecer_93 — regression-critical
# ---------------------------------------------------------------------------


def test_parecer_93_no_article_becomes_a_section(sample) -> None:
    """Plan §2.5, the failure this whole cycle exists to prevent.

    ``parecer_93``'s body contains 25 paragraph-initial ``Art.`` matches and
    every one of them is quoted statute. Promoting any of them would publish
    the Constitution's ``Art. 40`` as an article of a legal opinion — a
    fabricated structure that no later stage can detect or undo.
    """
    result = sample(PARECER_93).result

    sections = tuple(result.body.walk())
    assert sections, "the parecer does have structure — roman incisos"

    for section in sections:
        for field in (section.label, section.heading):
            assert field is None or not ARTICLE_RE.match(field), (
                f"section {field!r} came from a quoted article"
            )

    # Belt and braces: no *dispositivo* label kind reached the tree at all.
    assert "artigo" not in result.body.signals.label_kinds
    assert "paragrafo" not in result.body.signals.label_kinds


def test_parecer_93_article_census(sample) -> None:
    """The 25 matches are counted and rejected, not merely never seen.

    A census that came back empty would pass the test above for the wrong
    reason — a broken ``ARTICLE_RE`` looks exactly like a clean document.
    """
    analysis = sample(PARECER_93).analysis

    assert analysis.article_count == 25
    assert len(analysis.article_values) == 25
    assert analysis.article_monotonic is False


def test_parecer_93_quote_band_paragraphs_are_marked(sample) -> None:
    """Everything in the band is convicted — the band is not advisory."""
    parsed = sample(PARECER_93)

    in_band = [p for p in parsed.paras if p.indent_direct == PARECER_93_QUOTE_INDENT]
    assert len(in_band) > MIN_BAND_PARAGRAPHS

    unmarked = [p.index for p in in_band if not parsed.analysis.is_quoted(p.index)]
    assert unmarked == []


def test_parecer_93_own_prose_not_quoted(sample) -> None:
    """Over-marking is structurally harmless and still dishonest.

    The paragraphs that merely inherit 2909 are the parecer's own argument. The
    band must not reach them; a ``Para(kind="quote")`` on the author's own
    reasoning misattributes it even though nothing about the tree's shape
    changes. The handful that *are* convicted are convicted textually — they
    open with a quotation mark or are an *omissis* — never by the band.
    """
    parsed = sample(PARECER_93)
    own = [
        p
        for p in parsed.paras
        if p.indent_effective == PARECER_93_BODY_INDENT and p.indent_direct is None
    ]
    assert len(own) > 100, "this is the bulk of the document"

    assert not any(parsed.analysis.bands.contains(p) for p in own)

    convicted = {p.index for p in own if parsed.analysis.is_quoted(p.index)}
    textual = {
        p.index
        for p in own
        if opens_with_quote(p.text.strip())
        or is_omissis(p.text.strip())
        or carries_omissis(p.text.strip())
    }
    assert convicted == textual


# ---------------------------------------------------------------------------
# par_cosit_26 — plan §2.6's residual hard case: no indentation at all
# ---------------------------------------------------------------------------


def test_par_cosit_26_articles_non_monotonic(sample) -> None:
    """Numbering is the cue that survives when indentation says nothing.

    ``1º, 2º, 3º, 16, 52`` is not a document articulating itself: real
    articulation runs from the beginning and does not jump. With no band to
    lean on, this verdict is what lets the textual cues convict.
    """
    analysis = sample(PAR_COSIT_26).analysis

    assert analysis.bands.rule == "none"
    assert analysis.article_values == (2, 3, 16, 18, 52)
    assert analysis.article_monotonic is False


@pytest.mark.parametrize("index", [46, 47, 53, 64, 72])
def test_par_cosit_26_all_quoted_articles_convicted(sample, index: int) -> None:
    """Each quoted article is caught, whatever cue happens to catch it."""
    parsed = sample(PAR_COSIT_26)

    assert ARTICLE_RE.match(parsed.text(index)), "the block really is an Art. line"
    assert parsed.analysis.is_quoted(index) is True


def test_par_cosit_26_own_numbering_survives(sample) -> None:
    """The guard convicts quotations, not the document doing the quoting.

    Blocks 18…93 are ``par_cosit_26``'s own ``2.``–``19.`` numbering. Marking
    them quoted would cost the document all 24 of its sections — the exact
    over-correction that makes a quotation guard dangerous.
    """
    parsed = sample(PAR_COSIT_26)

    own = (18, 19, 24, 80, 81, 85, 90, 93)
    marked = [i for i in own if parsed.analysis.is_quoted(i)]
    assert marked == []

    assert len(tuple(parsed.result.body.walk())) == 24


def test_par_cosit_26_omissis(sample) -> None:
    """An excerpt is elided; an original enactment never is.

    Both shapes matter: a paragraph that *is* an elision mark, and a paragraph
    that *carries* one — ``Art. 52. ...........`` is a statute article the
    parecer cut short, which an enacting document could not produce.
    """
    parsed = sample(PAR_COSIT_26)

    for index in (48, 52, 61, 66, 71):
        assert is_omissis(parsed.text(index)), parsed.text(index)
        assert index in parsed.analysis.omissis

    bearer = parsed.text(72)
    assert ARTICLE_RE.match(bearer)
    assert is_omissis(bearer) is False
    assert carries_omissis(bearer) is True
    assert 72 in parsed.analysis.omissis


def test_par_cosit_26_excerpt_run_bounded(sample) -> None:
    """A run must close, and it closes on the document's own voice.

    The excerpt opens at block 46 and runs through the parenthetical aside at
    79 (``(os grifos não são dos originais)``), which belongs to the quotation.
    Block 80 — ``15. Dirimida a forma…`` — is the parecer speaking again, and
    the run has to stop there. Left unbounded it would swallow the rest of the
    document; stopped early it would leave quoted incisos free to become
    sections.
    """
    parsed = sample(PAR_COSIT_26)

    assert parsed.analysis.is_quoted(46) is True
    assert parsed.analysis.is_quoted(79) is True
    assert parsed.analysis.is_quoted(80) is False

    # Everything between the opening article and the closer is inside the run.
    interior = [
        p.index for p in parsed.paras if 46 <= p.index <= 79
    ]
    assert all(parsed.analysis.is_quoted(i) for i in interior)


# ---------------------------------------------------------------------------
# Style precedence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_style_headings_are_never_quoted(sample, name: str) -> None:
    """Word's outline level is an authorial declaration; indent cannot outvote it.

    Without this precedence ``sumula_stj_125``'s centred ``EMENTA`` headings
    — 1361–1372 twips against a body of 893 — land squarely inside the
    deviation band, are convicted as quotation, and the document loses half its
    structure. The rule is asserted across all 15 samples because it is a
    property of the guard, not a fact about one document.
    """
    parsed = sample(name)
    declared = [p for p in parsed.paras if p.outline_level is not None]

    convicted = [p.index for p in declared if parsed.analysis.is_quoted(p.index)]
    assert convicted == []


def test_sumula_stj_125_headings_would_fall_in_the_band(sample) -> None:
    """The teeth behind the test above: those headings really are in the band.

    If this stops being true the precedence rule is no longer being exercised
    by the corpus, and ``test_style_headings_are_never_quoted`` has quietly
    become vacuous on the one document that proves it.
    """
    parsed = sample(SUMULA_STJ_125)
    declared = [p for p in parsed.paras if p.outline_level is not None]

    in_band = [p for p in declared if parsed.analysis.bands.contains(p)]
    assert len(in_band) == 7
    assert {p.text.strip() for p in in_band} == {"EMENTA"}


# ---------------------------------------------------------------------------
# Pure predicates — no samples, no ingestion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("..............", True),
        (". . . . . . . .", True),
        ("(...)", True),
        ("[…]", True),
        ("Art. 52. ....", False),
        ("Uma frase normal.", False),
        ("", False),
        ("   ", False),
        ("1.500,00", False),
        ("2.1", False),
    ],
    ids=[
        "dots", "spaced-dots", "bracketed-round", "bracketed-square",
        "omissis-bearing-not-omissis", "prose", "empty", "blank",
        "money", "label",
    ],
)
def test_is_omissis(text: str, expected: bool) -> None:
    """A paragraph that is *nothing but* an elision mark.

    ``Art. 52. ....`` is deliberately False here: it is omissis-*bearing*, and
    conflating the two would let a whole article line be treated as a
    contentless separator and dropped from rendering.
    """
    assert is_omissis(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Art. 52. .............", True),
        ("Lei 8.383, de 1991, Art. 12. ..........", True),
        ("Uma frase normal.", False),
        ("", False),
    ],
    ids=["article-elided", "cited-article-elided", "prose", "empty"],
)
def test_carries_omissis(text: str, expected: bool) -> None:
    """Plan §2.6: an excerpt is cut short, an enactment is not.

    This is the cue that convicts ``par_cosit_26``'s ``Art. 52.`` with no
    indentation, no quotation mark and no monotonic series to help.
    """
    assert carries_omissis(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('Lei nº 7.713, de 1988 - "Art. 1º- Os rendimentos e ganhos de capital', True),
        ("Nos termos da Lei nº 8.383, de 1991:", True),
        ("Aplica-se o disposto no art. 3º da Lei nº 7.713, de 1988:", True),
        (
            "A Lei nº 9.250 alterou a sistemática de tributação sem revogar o "
            "regime anterior, como se verá adiante.",
            False,
        ),
        ("", False),
        ("   ", False),
    ],
    ids=[
        "inline-handoff", "colon-handoff", "article-reference-handoff",
        "passing-mention", "empty", "blank",
    ],
)
def test_names_external_norm(text: str, expected: bool) -> None:
    """An antecedent hands off to another norm; a mention merely refers to one.

    The hand-off is what makes the cue usable: the trailing colon or dash, or
    an opening quote straight onto ``Art.``. Without that discrimination every
    paragraph of a tax parecer would read as a citation antecedent and the cue
    would convict the entire document.
    """
    assert names_external_norm(text) is expected


def test_names_external_norm_recognises_constitutional_adjective() -> None:
    """Plan §2.6's own worked antecedent — the adjective, not only the noun.

    ``parecer_93`` block 342 hands off to a quoted excerpt with "observe-se os
    dispositivos **constitucionais** pertinentes:". This test was written as a
    strict xfail against a vocabulary that carried only ``constituicao``, and
    ``_NORM_WORDS`` gained the adjective forms in response.

    Harmless on ``parecer_93``, whose declared band already convicts the
    excerpt below it — but the citation antecedent is precisely the cue that
    has to carry indentation-free documents (§2.6), which is the shape most of
    the 300+ unseen corpus is expected to take.
    """
    assert names_external_norm(
        "179. A respeito dos dois últimos regimes mencionados, observe-se os "
        "dispositivos constitucionais pertinentes:"
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((1, 2, 3), True),
        ((2, 3, 4, 5), True),
        ((1, 2, 4), True),
        ((2, 3, 16, 18, 52), False),
        ((111, 46, 194, 74), False),
        ((46, 74, 194), False),
        ((3,), False),
        ((), False),
        ((1, 1, 2), False),
    ],
    ids=[
        "from-one", "from-two", "gap-of-two", "par_cosit_26-quoted-articles",
        "parecer_93-numeric-noise", "starts-too-high", "too-short", "empty",
        "not-strictly-increasing",
    ],
)
def test_is_monotonic_series(values: tuple[int, ...], expected: bool) -> None:
    """Three conditions, each earned from the corpus (amendment A-4.2).

    A document numbers itself from its beginning, in order, without jumping.
    ``(2, 3, 16, 18, 52)`` — ``par_cosit_26``'s quoted articles — fails the
    third; ``(111, 46, 194, 74)`` — ``parecer_93``'s numeric noise — fails the
    first and the second; ``(46, 74, 194)`` increases cleanly and still fails,
    because a document does not begin at 46.
    """
    assert is_monotonic_series(values) is expected


def test_is_monotonic_series_thresholds_are_overridable() -> None:
    """The two thresholds are parameters, so a caller can loosen either one.

    Both defaults must be genuinely load-bearing: relaxing ``start_max`` alone
    rescues a high-starting run, relaxing ``max_gap`` alone rescues a jumping
    one, and neither relaxation leaks into the other's verdict.
    """
    assert is_monotonic_series((46, 47, 48)) is False
    assert is_monotonic_series((46, 47, 48), start_max=50) is True

    assert is_monotonic_series((1, 2, 9)) is False
    assert is_monotonic_series((1, 2, 9), max_gap=10) is True

    # Loosening one threshold does not excuse the other.
    assert is_monotonic_series((46, 47, 48), max_gap=10) is False
    assert is_monotonic_series((1, 2, 9), start_max=50) is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"Art. 18 - É sujeita ao pagamento', True),
        ("“o Beneficio Especial corresponde", True),
        ("'trecho citado", True),
        ("«citação", True),
        ("  “com espaço à esquerda", True),
        ("Art. 40. Os pareceres do Advogado-Geral", False),
        ("uma citação no meio: “assim”", False),
        ("", False),
    ],
    ids=[
        "straight", "curly", "apostrophe", "guillemet", "leading-space",
        "article-no-quote", "quote-not-at-start", "empty",
    ],
)
def test_opens_with_quote(text: str, expected: bool) -> None:
    """Only an *opening* quote counts — position 0, whitespace aside.

    Plan §2.5 measured why: quoted statutes routinely appear with no quote mark
    at all, so this cue may never be relaxed into "contains a quote mark" to
    compensate. That would convict every paragraph that quotes a phrase.
    """
    assert opens_with_quote(text) is expected


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_module_constants_keep_their_measured_values() -> None:
    """Each of these was measured, not chosen — retuning one is a design change.

    * ``QUOTE_INDENT_MARGIN = 300`` twips ≈ 0.53 cm: under a centimetre, so a
      first-line indent never qualifies, and well under the corpus's real
      offsets (2908, 893, 450).
    * ``DECLARED_BAND_TOLERANCE = 64``: ``parecer_93``'s band is four values,
      2879–2930, the spread a hand-dragged Word ruler leaves.
    * ``MIN_BAND_PARAGRAPHS = 3``: below this a band is an accident.
    * ``SERIES_START_MAX = 2``: ``par_cosit_26`` starts at ``2.`` only because
      ``1.`` sits in its front matter.
    * ``SERIES_MAX_GAP = 3``: what rejects ``2, 3, 16, 18, 52``.

    This test exists so that changing a number here fails loudly rather than
    quietly moving a verdict on 300+ unseen documents.
    """
    assert QUOTE_INDENT_MARGIN == 300
    assert DECLARED_BAND_TOLERANCE == 64
    assert MIN_BAND_PARAGRAPHS == 3
    assert SERIES_START_MAX == 2
    assert SERIES_MAX_GAP == 3
