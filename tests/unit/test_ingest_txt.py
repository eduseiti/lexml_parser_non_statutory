"""Plain-text ingestion — Cycle 8, spec §3.3 and §5.1.

A text file carries no typography, and the reader must not invent any: plan
invariant #8 says low confidence degrades to flat and never fabricates
structure, and a reader that guessed a heading from ALL CAPS would be
fabricating at the earliest possible point, where nothing downstream could
detect it.

So these tests are as much about what the reader *refuses* to produce — no
styles, no outline levels, no tables, no bold — as about what it does. The one
signal a text file genuinely carries is leading whitespace, and that becomes
`indent_direct`, which is the field the quotation guard (A-1.1, A-4.1) reads.
"""

from __future__ import annotations

import unicodedata

import pytest

from lexml_nonstat.ingest import StyledPara, TxtReadError, read_txt


def _texts(doc):
    return [b.text for b in doc.blocks]


# ---------------------------------------------------------------------------
# blocking
# ---------------------------------------------------------------------------


def test_blank_line_separates_blocks() -> None:
    assert _texts(read_txt("a\n\nb")) == ["a", "b"]


def test_wrapped_lines_join_with_one_space() -> None:
    """A hard-wrapped paragraph is one paragraph, not four."""
    assert _texts(read_txt("uma linha\nquebrada aqui\n\noutra")) == [
        "uma linha quebrada aqui",
        "outra",
    ]


def test_runs_of_blank_lines_are_one_separator() -> None:
    assert _texts(read_txt("a\n\n\n\n\nb")) == ["a", "b"]


def test_leading_and_trailing_blank_lines_produce_no_blocks() -> None:
    assert _texts(read_txt("\n\n\na\n\n\n")) == ["a"]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_every_line_ending_yields_the_same_blocks(newline: str) -> None:
    """A DOS or classic-Mac file must not segment differently from a Unix one."""
    text = newline.join(["a", "", "b"])
    assert _texts(read_txt(text)) == ["a", "b"]


def test_block_indices_are_dense_and_ordered() -> None:
    doc = read_txt("a\n\nb\n\nc")
    assert [b.index for b in doc.blocks] == [0, 1, 2]


# ---------------------------------------------------------------------------
# indentation — the one signal plain text really carries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spaces,twips", [(0, None), (1, 180), (2, 360), (4, 720), (8, 1440)]
)
def test_leading_spaces_become_twips(spaces: int, twips: int | None) -> None:
    """4 spaces → 720, Word's default tab stop and the number the DOCX of the
    same document would report for one tab."""
    doc = read_txt(" " * spaces + "texto")
    assert doc.blocks[0].indent_direct == twips


def test_indent_is_taken_from_the_first_line_of_a_block() -> None:
    doc = read_txt("    primeira\n    segunda")
    (para,) = doc.blocks
    assert para.indent_direct == 720
    assert para.text == "primeira segunda"


def test_indent_effective_matches_indent_direct() -> None:
    """There is no style to inherit from, so declared and effective agree.

    A-4.1's discriminator is *declared vs inherited*; in plain text everything
    is declared, which is a fact about the format worth pinning.
    """
    (para,) = read_txt("    x").blocks
    assert para.indent_effective == para.indent_direct == 720


# ---------------------------------------------------------------------------
# what the reader must refuse to invent (invariant #8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["TITULO EM MAIUSCULAS", "1. Introducao", "Art. 1º Fica instituido"]
)
def test_no_style_or_outline_level_is_ever_invented(text: str) -> None:
    (para,) = read_txt(text).blocks
    assert para.style is None
    assert para.style_id is None
    assert para.outline_level is None
    assert para.num_id is None
    assert para.ilvl is None
    assert para.alignment is None


def test_every_block_is_a_paragraph_never_a_table() -> None:
    doc = read_txt("a | b | c\n\nd | e | f")
    assert all(isinstance(b, StyledPara) for b in doc.blocks)


def test_one_plain_inline_per_block() -> None:
    (para,) = read_txt("**nao e negrito**").blocks
    assert len(para.inlines) == 1
    inline = para.inlines[0]
    assert not (inline.bold or inline.italic or inline.sup or inline.sub)
    assert inline.href is None


# ---------------------------------------------------------------------------
# text handling
# ---------------------------------------------------------------------------


def test_text_is_nfc_normalised() -> None:
    decomposed = unicodedata.normalize("NFD", "ção")
    assert decomposed != "ção"
    assert _texts(read_txt(decomposed)) == ["ção"]


def test_internal_whitespace_is_collapsed() -> None:
    assert _texts(read_txt("a  \t  b")) == ["a b"]


def test_source_name_is_recorded() -> None:
    assert read_txt("x", source_name="a.txt").source == "a.txt"


# ---------------------------------------------------------------------------
# files, encodings, degenerate input
# ---------------------------------------------------------------------------


def test_reads_a_utf8_file(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("SEÇÃO ç ã", encoding="utf-8")
    assert _texts(read_txt(path)) == ["SEÇÃO ç ã"]


def test_latin1_file_falls_back_rather_than_raising(tmp_path) -> None:
    """A legacy corpus will contain both encodings; neither may crash a run."""
    path = tmp_path / "a.txt"
    path.write_bytes("SEÇÃO".encode("latin-1"))
    assert len(_texts(read_txt(path))) == 1


def test_undecodable_bytes_do_not_raise(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"SE\xc3\x28O")
    assert isinstance(_texts(read_txt(path)), list)


@pytest.mark.parametrize("text", ["", "   ", "\n\n\n", "\t\t"])
def test_empty_and_whitespace_only_input_yields_no_blocks(text: str) -> None:
    assert read_txt(text).blocks == ()


def test_missing_file_raises_txt_read_error(tmp_path) -> None:
    with pytest.raises(TxtReadError):
        read_txt(tmp_path / "nope.txt")


def test_directory_raises_txt_read_error(tmp_path) -> None:
    with pytest.raises(TxtReadError):
        read_txt(tmp_path)


def test_txt_read_error_is_catchable_as_a_docx_read_error() -> None:
    """A subclass on purpose — the opposite of `HtmlReadError`'s choice.

    Callers written before this cycle catch `DocxReadError` to mean "ingestion
    failed on a file", and they are right to; the distinct name exists so the
    message about a `.txt` does not say *DOCX*, not to break them.
    """
    from lexml_nonstat.ingest import DocxReadError

    assert issubclass(TxtReadError, DocxReadError)


def test_a_very_long_line_is_one_block() -> None:
    doc = read_txt("palavra " * 5000)
    assert len(doc.blocks) == 1


# ---------------------------------------------------------------------------
# the bullet: reaching the same model shape (§5.1a)
# ---------------------------------------------------------------------------


def test_txt_reaches_a_model_that_renders_and_validates() -> None:
    """End to end: the format is new, so the whole pipeline must accept it."""
    from lexml_nonstat.model import build_model
    from lexml_nonstat.render import render_generico
    from lexml_nonstat.validate import validate

    text = (
        "PARECER NORMATIVO Nº 1, DE 1 DE JANEIRO DE 2020\n\n"
        "1. INTRODUÇÃO\n\n"
        "O presente parecer trata da matéria em exame.\n\n"
        "2. CONCLUSÃO\n\n"
        "Ante o exposto, conclui-se pela procedência.\n"
    )
    model = build_model(read_txt(text, source_name="p.txt"), filename="p.txt")
    rendered = render_generico(model)
    assert validate(rendered.primary, "both").ok


def test_txt_conserves_every_word_into_the_rendering() -> None:
    """Invariant #2 on the new format: nothing lost, nothing duplicated."""
    from collections import Counter

    from lexml_nonstat.model import build_model
    from lexml_nonstat.render import render_generico

    text = "Primeiro paragrafo aqui.\n\nSegundo paragrafo distinto.\n\nTerceiro."
    doc = read_txt(text, source_name="c.txt")
    model = build_model(doc, filename="c.txt")
    rendered = render_generico(model)

    source_words = Counter(w for b in doc.blocks for w in b.text.split())
    out_words = Counter(w for t in rendered.texts for w in t.split())
    assert source_words == out_words
