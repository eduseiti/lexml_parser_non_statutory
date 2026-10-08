"""``parse --urn`` / ``--metadata``: a declared URN overrides the inferred one.

See ``docs/20261008_*_declared_urn_option.md``. The declared identity must reach
the ``Identificacao`` element, the annex URNs and the output file name, and the
``*_source`` fields must say it was declared.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lxml import etree

from lexml_nonstat import cli
from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import declare_urn, extract_metadata

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "samples" / "pn_cst_38_19801031.docx"
ANNEX_SAMPLE = REPO_ROOT / "samples" / "port_mf_277_20180607.docx"
NS = {"l": "http://www.lexml.gov.br/1.0"}
DECLARED = "urn:lex:br:ministerio.fazenda;secretaria.receita.federal:parecer.normativo:1980-10-31;38"


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _urn(xml: str) -> str:
    root = etree.fromstring(xml.encode("utf-8"))
    return root.find(".//l:Identificacao", NS).get("URN")


def test_declare_urn_replaces_every_component_and_marks_the_source() -> None:
    meta = declare_urn(extract_metadata(read_docx(SAMPLE), filename=SAMPLE.name), DECLARED)
    assert meta.urn == DECLARED
    assert meta.authority_source == meta.date_source == meta.number_source == "declared"


def test_parse_urn_reaches_identificacao() -> None:
    code, out, err = run(["parse", "--urn", DECLARED, str(SAMPLE)])
    assert code == 0, err
    assert _urn(out) == DECLARED


def test_parse_metadata_tsv_names_the_files_and_the_annexes(tmp_path: Path) -> None:
    urn = "urn:lex:br:ministerio.fazenda:portaria:2018-06-07;9277"
    tsv = tmp_path / "meta.tsv"
    tsv.write_text(f"stem\turn\n{ANNEX_SAMPLE.stem}\t{urn}\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    code, _, err = run(["parse", "--metadata", str(tsv), "-o", str(out_dir), str(ANNEX_SAMPLE)])
    assert code == 0, err
    names = sorted(p.name for p in out_dir.iterdir())
    assert "urn_lex_br_ministerio.fazenda_portaria_2018-06-07_9277.xml" in names
    annexes = [p for p in out_dir.iterdir() if "!anexo" in p.name]
    assert annexes, names
    for p in annexes:
        assert _urn(p.read_text(encoding="utf-8")).startswith(urn + "!anexo")


def test_stems_missing_from_the_table_keep_the_inferred_urn(tmp_path: Path) -> None:
    tsv = tmp_path / "meta.tsv"
    tsv.write_text("stem\turn\nsomething_else\t" + DECLARED + "\n", encoding="utf-8")
    code, out, err = run(["parse", "--metadata", str(tsv), str(SAMPLE)])
    assert code == 0, err
    _, inferred, _ = run(["parse", str(SAMPLE)])
    assert _urn(out) == _urn(inferred)


def test_misuse_is_refused(tmp_path: Path) -> None:
    assert run(["parse", "--urn", DECLARED, str(SAMPLE), str(ANNEX_SAMPLE)])[0] == 2
    assert run(["parse", "--urn", "not-a-urn", str(SAMPLE)])[0] == 2
    assert run(["parse", "--urn", DECLARED + "!anexo1", str(SAMPLE)])[0] == 2
    tsv = tmp_path / "meta.tsv"
    tsv.write_text("a\tb\n", encoding="utf-8")
    assert run(["parse", "--metadata", str(tsv), str(SAMPLE)])[0] == 2
