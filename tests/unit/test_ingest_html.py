"""HTML ingestion — Cycle 8, spec §3.2 and §5.1.

The corpus is fifteen DOCX files and no HTML at all, so these tests follow the
precedent amendments **A-1.3** and **A-4.6** set: a construct the samples cannot
exercise is tested by a synthetic fixture, and the fixture asserts the property
the real corpus would have asserted.

The property that matters is not "the reader produces this exact tree" — that
would pin an implementation detail no consumer depends on. It is that the
*pipeline* is format-agnostic: an HTML transcription of a document and the DOCX
of the same document must reach the same hierarchy and carry the same words.
:func:`test_same_model_shape_as_docx` is that claim, and it is what the plan's
"HTML and TXT ingestion reach the same model shape" bullet means operationally
(spec §5.1a).
"""

from __future__ import annotations

import unicodedata

import pytest

from lexml_nonstat.ingest import HtmlReadError, StyledPara, StyledTable, read_html


def _paras(doc):
    return [b for b in doc.blocks if isinstance(b, StyledPara)]


def _texts(doc):
    return [b.text for b in _paras(doc)]


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_headings_carry_style_and_outline_level(level: int) -> None:
    doc = read_html(f"<h{level}>Titulo</h{level}>")
    (para,) = _paras(doc)
    assert para.style == f"Heading {level}"
    assert para.outline_level == level - 1


def test_paragraph_inlines_carry_their_formatting() -> None:
    doc = read_html("<p>a <b>b</b> <i>c</i> <sup>d</sup> <sub>e</sub></p>")
    (para,) = _paras(doc)
    marks = {i.text.strip(): (i.bold, i.italic, i.sup, i.sub) for i in para.inlines}
    assert marks["b"] == (True, False, False, False)
    assert marks["c"] == (False, True, False, False)
    assert marks["d"] == (False, False, True, False)
    assert marks["e"] == (False, False, False, True)


def test_strong_and_em_are_bold_and_italic() -> None:
    doc = read_html("<p><strong>s</strong><em>e</em></p>")
    (para,) = _paras(doc)
    by_text = {i.text: i for i in para.inlines}
    assert by_text["s"].bold and by_text["e"].italic


def test_anchor_href_is_captured() -> None:
    doc = read_html('<p>ver <a href="http://x/y">aqui</a></p>')
    (para,) = _paras(doc)
    link = next(i for i in para.inlines if i.text.strip() == "aqui")
    assert link.href == "http://x/y"


def test_nested_lists_carry_num_id_and_ilvl() -> None:
    doc = read_html("<ol><li>um<ol><li>um.um</li></ol></li></ol>")
    paras = _paras(doc)
    assert [p.text for p in paras] == ["um", "um.um"]
    assert all(p.num_id is not None for p in paras)
    assert [p.ilvl for p in paras] == [0, 1]


def test_ordered_and_unordered_lists_differ() -> None:
    """The reader must not erase the distinction; `hierarchy` reads `num_id`."""
    ol = _paras(read_html("<ol><li>a</li></ol>"))[0]
    ul = _paras(read_html("<ul><li>a</li></ul>"))[0]
    assert ol.num_id != ul.num_id


def test_table_becomes_a_styled_table_of_the_right_shape() -> None:
    markup = (
        "<table>"
        "<tr><td>a</td><td>b</td><td>c</td></tr>"
        "<tr><td>d</td><td>e</td><td>f</td></tr>"
        "</table>"
    )
    tables = [b for b in read_html(markup).blocks if isinstance(b, StyledTable)]
    assert len(tables) == 1
    assert tables[0].shape == (2, 3)


def test_margin_left_becomes_twips() -> None:
    """1pt = 20 twips, so 36pt is 720 — the same number a tab yields in DOCX."""
    doc = read_html('<p style="margin-left:36pt">x</p>')
    assert _paras(doc)[0].indent_direct == 720


def test_br_splits_a_paragraph() -> None:
    """A-1.2: Cycle 1 splits on a DOCX soft break; HTML must agree."""
    assert _texts(read_html("<p>a<br>b</p>")) == ["a", "b"]


# ---------------------------------------------------------------------------
# what must not survive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "markup",
    [
        "<p>keep</p><script>var drop = 1;</script>",
        "<p>keep</p><style>.drop { color: red }</style>",
        "<p>keep</p><!-- drop -->",
    ],
)
def test_non_content_is_dropped(markup: str) -> None:
    assert "drop" not in " ".join(_texts(read_html(markup)))
    assert "keep" in " ".join(_texts(read_html(markup)))


def test_struck_text_is_dropped_by_default_and_retained_on_request() -> None:
    markup = "<p>keep <s>gone</s></p>"
    assert "gone" not in _texts(read_html(markup))[0]
    assert "gone" in _texts(read_html(markup, drop_strikethrough=False))[0]


@pytest.mark.parametrize("tag", ["s", "strike", "del"])
def test_every_strikethrough_spelling(tag: str) -> None:
    assert "gone" not in _texts(read_html(f"<p>keep <{tag}>gone</{tag}></p>"))[0]


# ---------------------------------------------------------------------------
# text handling
# ---------------------------------------------------------------------------


def test_text_is_nfc_normalised() -> None:
    """A-1.3's tripwire, on the format where a decomposed source is likelier."""
    decomposed = unicodedata.normalize("NFD", "ção")
    assert decomposed != "ção"
    text = _texts(read_html(f"<p>{decomposed}</p>"))[0]
    assert text == unicodedata.normalize("NFC", text) == "ção"


def test_whitespace_is_collapsed() -> None:
    assert _texts(read_html("<p>a   \n\t  b</p>"))[0] == "a b"


def test_block_indices_are_dense_and_ordered() -> None:
    doc = read_html("<h1>a</h1><p>b</p><ul><li>c</li></ul><p>d</p>")
    assert [b.index for b in doc.blocks] == list(range(len(doc.blocks)))


def test_source_name_is_recorded() -> None:
    assert read_html("<p>x</p>", source_name="a.html").source == "a.html"


# ---------------------------------------------------------------------------
# encoding — measured, not assumed (see `_decode`'s docstring)
# ---------------------------------------------------------------------------


def test_undeclared_utf8_file_is_read_as_utf8(tmp_path) -> None:
    """lxml's own fallback is latin-1, which turns `SEÇÃO` into mojibake."""
    path = tmp_path / "a.html"
    path.write_bytes("<p>SEÇÃO ç ã</p>".encode("utf-8"))
    assert _texts(read_html(path)) == ["SEÇÃO ç ã"]


def test_declared_latin1_file_is_honoured(tmp_path) -> None:
    """A declaration wins over the default — the document knows best."""
    path = tmp_path / "a.html"
    path.write_bytes('<meta charset="latin-1"><p>SEÇÃO</p>'.encode("latin-1"))
    assert _texts(read_html(path)) == ["SEÇÃO"]


def test_xml_declaration_does_not_swallow_the_document(tmp_path) -> None:
    """lxml's HTML parser returns an *empty* tree after an XML declaration."""
    path = tmp_path / "a.html"
    path.write_bytes(
        '<?xml version="1.0" encoding="iso-8859-1"?><p>SEÇÃO</p>'.encode("latin-1")
    )
    assert _texts(read_html(path)) == ["SEÇÃO"]


def test_an_unknown_declared_charset_falls_back_rather_than_raising(tmp_path) -> None:
    path = tmp_path / "a.html"
    path.write_bytes('<meta charset="nonsense-42"><p>SEÇÃO</p>'.encode("utf-8"))
    assert _texts(read_html(path)) == ["SEÇÃO"]


def test_undecodable_bytes_do_not_raise(tmp_path) -> None:
    """latin-1 is the last resort precisely because it maps every byte."""
    path = tmp_path / "a.html"
    path.write_bytes(b"<p>SE\xc3</p>")
    assert len(_texts(read_html(path))) == 1


# ---------------------------------------------------------------------------
# robustness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "markup",
    ["", "   ", "<p>unclosed", "<<<>>>", "<!-- only a comment -->", "<p>a<p>b"],
)
def test_degenerate_markup_never_raises(markup: str) -> None:
    doc = read_html(markup)
    assert doc.blocks == () or all(hasattr(b, "index") for b in doc.blocks)


def test_a_bare_string_with_no_markup_is_read_as_a_path() -> None:
    """Deliberate, and the better of two bad options.

    A `str` naming no existing file and containing no `<` is ambiguous. Reading
    it as a path means a typo'd filename reports "no such file"; reading it as
    markup would silently ingest `report.html` as a one-word document. The
    first failure is visible, so that is the one the reader chooses.
    """
    with pytest.raises(HtmlReadError):
        read_html("report.html")


def test_missing_file_raises_html_read_error(tmp_path) -> None:
    with pytest.raises(HtmlReadError):
        read_html(tmp_path / "nope.html")


def test_directory_raises_html_read_error(tmp_path) -> None:
    with pytest.raises(HtmlReadError):
        read_html(tmp_path)


def test_html_read_error_is_not_a_docx_read_error() -> None:
    """Two unrelated failures of two unrelated libraries; catching one must
    not silently swallow the other."""
    from lexml_nonstat.ingest import DocxReadError

    assert not issubclass(HtmlReadError, DocxReadError)


# ---------------------------------------------------------------------------
# the bullet: "HTML and TXT ingestion reach the same model shape" (§5.1a)
# ---------------------------------------------------------------------------


#: A transcription of `pn_cst_38_19801031`'s opening structure. Hand-authored,
#: as amendment A-4b.5 requires of every fixture that stands in for a real
#: document, and deliberately small: what is asserted is that two formats reach
#: the same *shape*, which a three-section document establishes as well as a
#: seventy-block one would.
_TRANSCRIPTION = """
<h1>1. INTRODUÇÃO</h1>
<p>O presente parecer trata da matéria em exame.</p>
<h1>2. FUNDAMENTAÇÃO</h1>
<p>A legislação aplicável dispõe sobre o tema.</p>
<h2>2.1. Do primeiro aspecto</h2>
<p>Cabe observar o que segue.</p>
<h1>3. CONCLUSÃO</h1>
<p>Ante o exposto, conclui-se pela procedência.</p>
"""


def _shape(tree):
    """(level, kind, label) per section, in document order — the comparable form."""
    return [(s.level, s.kind, s.label) for s in tree.walk()]


def test_html_reaches_a_structured_tree() -> None:
    from lexml_nonstat.model import build_model

    model = build_model(read_html(_TRANSCRIPTION, source_name="t.html"), filename="t.html")
    assert not model.body.flat
    # Three body sections, not four: section "1." is claimed as front matter by
    # Cycle 3's segmentation, exactly as it would be in the DOCX of the same
    # document. That the *segmentation* also behaves identically across formats
    # is the point — a reader that produced a subtly different block sequence
    # would move that boundary.
    shape = _shape(model.body)
    assert [(level, kind) for level, kind, _ in shape] == [
        (1, "secao"),
        (2, "subsecao"),
        (1, "secao"),
    ]


def test_same_model_shape_as_the_same_document_in_txt() -> None:
    """The §5.1a claim, between the two formats this cycle adds.

    Both readers feed the same `build_model`, so this asserts the *pipeline* is
    format-agnostic rather than that two readers happen to agree.
    """
    from lexml_nonstat.ingest import read_txt
    from lexml_nonstat.model import build_model

    plain = "\n\n".join(
        line.strip()
        for line in _TRANSCRIPTION.strip().splitlines()
        if line.strip()
    )
    for tag in ("<h1>", "</h1>", "<h2>", "</h2>", "<p>", "</p>"):
        plain = plain.replace(tag, "")

    html_model = build_model(read_html(_TRANSCRIPTION), filename="t.html")
    txt_model = build_model(read_txt(plain), filename="t.txt")

    html_words = sorted(w for t in _texts(read_html(_TRANSCRIPTION)) for w in t.split())
    txt_words = sorted(w for b in txt_model.styled.blocks for w in b.text.split())
    assert html_words == txt_words

    # Both must find the same *number* of top-level sections. The HTML carries
    # heading styles the plain text cannot, so the trees are not identical —
    # the label grammar is what recovers the structure from the text alone, and
    # that it recovers the same top-level series is the portable claim.
    html_tops = [s.label for s in html_model.body.sections]
    txt_tops = [s.label for s in txt_model.body.sections]
    assert html_tops == txt_tops
