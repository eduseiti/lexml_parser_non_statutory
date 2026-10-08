"""Front matter of Planalto treaty decrees and Receita portal pages.

See ``docs/20261008_*_front_matter_layout_tables_and_portal_lines.md``: the ementa in a one-row
layout table, "O PRESIDENTE DA REPÚBLICA" as a preamble, and portal editorial lines before the
ementa.
"""

from __future__ import annotations

from lexml_nonstat.ingest import (Inline, StyledCell, StyledDoc, StyledPara, StyledRow, StyledTable,
                                  unwrap_layout_tables)
from lexml_nonstat.profile import get_profile
from lexml_nonstat.segment.frontmatter import find_ementa, find_preamble


def para(text: str, index: int = 0) -> StyledPara:
    return StyledPara(inlines=(Inline(text=text),), index=index)


def table(rows, index: int) -> StyledTable:
    return StyledTable(rows=tuple(StyledRow(cells=tuple(StyledCell(paras=tuple(para(t) for t in cell))
                                                         for cell in row)) for row in rows), index=index)


def decree() -> StyledDoc:
    return StyledDoc(blocks=(
        para("DECRETO Nº 62.125, DE 16 DE JANEIRO DE 1968.", 0),
        table([[[""], ["Promulga o", "Acôrdo entre o Fundo das Nações Unidas para a Infância", "e o Brasil."]]], 1),
        para("O PRESIDENTE DA REPÚBLICA,", 2),
        para("HAVENDO o Congresso Nacional aprovado …", 3),
    ))


def test_one_row_layout_table_becomes_one_paragraph_per_cell():
    doc = unwrap_layout_tables(decree())
    texts = [b.text for b in doc.blocks]
    assert texts[1] == "Promulga o Acôrdo entre o Fundo das Nações Unidas para a Infância e o Brasil."
    assert [b.index for b in doc.blocks] == list(range(len(doc.blocks)))
    assert not any(isinstance(b, StyledTable) for b in doc.blocks)


def test_data_tables_and_late_tables_are_kept():
    data = table([[["a"], ["b"]], [["c"], ["d"]]], 1)
    doc = StyledDoc(blocks=(para("x", 0), data))
    assert unwrap_layout_tables(doc) is doc
    late = StyledDoc(blocks=tuple(para(f"p{i}", i) for i in range(12)) + (table([[["", "z"]]], 12),))
    assert unwrap_layout_tables(late) is late


def test_ementa_is_the_unwrapped_cell_and_the_president_line_is_the_preamble():
    doc = unwrap_layout_tables(decree())
    profile = get_profile("generic")
    ementa = find_ementa(doc, profile, after=0)
    assert ementa is not None and doc.blocks[ementa.start].text.startswith("Promulga o Acôrdo")
    preamble = find_preamble(doc, profile, after=ementa.end)
    assert preamble is not None and doc.blocks[preamble.start].text == "O PRESIDENTE DA REPÚBLICA,"


def test_the_president_line_alone_is_not_an_ementa():
    doc = StyledDoc(blocks=(para("DECRETO Nº 27.784, DE 16 DE FEVEREIRO DE 1950.", 0),
                            para("O PRESIDENTE DA REPÚBLICA DOS ESTADOS UNIDOS DO BRASIL:", 1)))
    assert find_ementa(doc, get_profile("generic"), after=0) is None


def test_portal_editorial_lines_before_the_ementa_are_skipped():
    profile = get_profile("generic")
    for line in ("Vide Recurso extraordinário nº 522897 Texto compilado Texto original",
                 "Norma Federal - Publicado no DO em 29 mar 1983",
                 "Download para anexo"):
        doc = StyledDoc(blocks=(para("Instrução Normativa SRF nº 23 de 25/03/1983", 0), para(line, 1),
                                para("Altera normas para a apuração e tributação do lucro.", 2),
                                para("O Secretário da Receita Federal, no uso de suas atribuições,", 3)))
        ementa = find_ementa(doc, profile, after=0)
        assert ementa is not None and ementa.start == 2, line
