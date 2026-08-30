"""Degenerate and malformed input — Cycle 8, spec §5.1; plan §9.1's robustness layer.

The corpus is fifteen real documents standing in for 300+ unseen ones, and the
unseen ones will include the shapes no author would submit deliberately: a file
that is empty, one that is a single wall of text, one whose "headings" are bold
centred lines with no number, one that is nothing but a table. Cycle 8's exit
criterion is that every one of them yields **valid output or a clean
diagnostic** — never a crash, and never a traceback in front of a user.

Two claims, tested separately because they fail differently:

* a *degenerate* document is still a document — it must traverse the whole
  pipeline and emit XML that validates on both schemas;
* a *malformed* file is not a document at all — it must be refused with one
  line and a non-zero exit, and the process must not print a traceback.

The fixtures are built in-process by `python-docx` (`tests/fixtures/degenerate.py`),
following the synthetic-fixture precedent of amendments A-1.3 and A-4.6: nothing
binary is committed, and each case's construction is readable where it is built.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest
from lxml import etree

from tests.fixtures.degenerate import (
    DEGENERATE_CASES,
    build_all,
    corrupt_docx,
    truncated_docx,
    zip_that_is_not_a_docx,
)
from lexml_nonstat import cli
from lexml_nonstat.ingest import DocxReadError, read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import render_generico, render_generico_aninhado
from lexml_nonstat.segments import segments_from_model
from lexml_nonstat.validate import validate


@pytest.fixture(scope="module")
def cases(tmp_path_factory) -> dict:
    """Every degenerate document, built once for the module (~0.14s)."""
    return build_all(tmp_path_factory.mktemp("degenerate"))


@pytest.fixture(scope="module")
def models(cases) -> dict:
    """Each case's model, built once — the pipeline runs are what is slow."""
    return {
        name: build_model(read_docx(path), filename=path.name)
        for name, path in cases.items()
    }


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Drive the CLI in-process, capturing both streams."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# every stage of the pipeline survives every degenerate shape
# ---------------------------------------------------------------------------


def test_the_fixture_set_is_the_declared_one(cases) -> None:
    assert tuple(cases) == DEGENERATE_CASES


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_ingests(cases, name: str) -> None:
    doc = read_docx(cases[name])
    assert [b.index for b in doc.blocks] == list(range(len(doc.blocks)))


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_builds_a_model(models, name: str) -> None:
    model = models[name]
    assert model.profile
    assert model.route in ("generico", "norma")


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_renders_flat(models, name: str) -> None:
    assert render_generico(models[name]).primary is not None


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_renders_nested(models, name: str) -> None:
    """A-5b.3: the nested renderer always renders; the probe gates *validation*."""
    assert render_generico_aninhado(models[name]).primary is not None


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_flat_output_is_valid_on_both_schemas(models, name: str) -> None:
    """Cycle 8's exit criterion, stated on the hardest inputs available."""
    report = validate(render_generico(models[name]).primary, "both")
    assert report.ok, report.summary()


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_segments(models, name: str) -> None:
    assert isinstance(segments_from_model(models[name]), tuple)


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_ids_are_unique(models, name: str) -> None:
    """Invariant #5, document-wide, including `duplicate_headings`."""
    ids = render_generico(models[name]).ids
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_text_is_conserved(cases, models, name: str) -> None:
    """Invariant #2: no word lost, none duplicated, on every degenerate shape."""
    from collections import Counter

    from lexml_nonstat.ingest import StyledPara

    doc = read_docx(cases[name])
    # Paragraph text only: a `StyledTable` holds its words in its cells, and
    # the emitter carries them into `<table>` — counted on the emitted side but
    # not reachable as `.text` on the source side.
    source = Counter(
        w for b in doc.blocks if isinstance(b, StyledPara) for w in b.text.split()
    )
    emitted = Counter(w for t in render_generico(models[name]).texts for w in t.split())
    assert not (source - emitted), f"{name}: lost {source - emitted}"


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_no_structure_is_fabricated(models, name: str) -> None:
    """Invariant #8, where it is easiest to violate.

    `unlabelled_prose` and `no_headings` carry nothing a grammar could read as
    a label. A tree that came back structured from either would mean the
    inference invented one.
    """
    if name in ("unlabelled_prose", "no_headings"):
        assert models[name].body.flat


# ---------------------------------------------------------------------------
# the same, through the CLI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_cli_parses_every_degenerate_document(cases, name: str) -> None:
    code, out, err = _run(["parse", str(cases[name])])
    assert code == 0, err
    assert etree.fromstring(out.encode("utf-8")) is not None
    assert "Traceback" not in err


@pytest.mark.parametrize("name", DEGENERATE_CASES)
def test_cli_emits_valid_xml_for_every_degenerate_document(cases, name: str) -> None:
    _, out, _ = _run(["parse", str(cases[name])])
    assert validate(etree.fromstring(out.encode("utf-8")), "both").ok


def test_empty_document_warns_rather_than_failing(cases) -> None:
    """A document with no content is a fact to report, not an error.

    It still emits a valid `LexML`, so `--strict` is what turns the warning
    into a non-zero exit; without it the run succeeds and says why.
    """
    code, out, err = _run(["parse", "--format=json", str(cases["empty"])])
    assert code == 0
    assert "empty_document" in err
    assert "empty_document" in out


def test_empty_document_fails_under_strict(cases) -> None:
    code, _, _ = _run(["parse", "--strict", str(cases["empty"])])
    assert code == 1


# ---------------------------------------------------------------------------
# malformed files — clean error, non-zero exit, no traceback
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def broken(tmp_path_factory) -> dict:
    directory = tmp_path_factory.mktemp("broken")
    return {
        "corrupt": corrupt_docx(directory),
        "truncated": truncated_docx(directory),
        "not_a_docx": zip_that_is_not_a_docx(directory),
    }


@pytest.mark.parametrize("kind", ["corrupt", "truncated", "not_a_docx"])
def test_malformed_docx_raises_a_typed_error(broken, kind: str) -> None:
    """Three files, three failure layers: not-a-ZIP, truncated ZIP, wrong package."""
    with pytest.raises(DocxReadError):
        read_docx(broken[kind])


@pytest.mark.parametrize("kind", ["corrupt", "truncated", "not_a_docx"])
def test_cli_refuses_a_malformed_docx_cleanly(broken, kind: str) -> None:
    code, out, err = _run(["parse", str(broken[kind])])
    assert code == 1
    assert out == ""
    assert "Traceback" not in err
    assert err.strip().splitlines()[0].startswith("error: ")


def test_missing_file_names_the_path(tmp_path) -> None:
    missing = tmp_path / "nao_existe.docx"
    code, _, err = _run(["parse", str(missing)])
    assert code == 1
    assert "nao_existe.docx" in err
    assert "Traceback" not in err


def test_a_directory_is_a_misuse_not_a_document(tmp_path) -> None:
    code, _, err = _run(["parse", str(tmp_path)])
    assert code == 2
    assert "directory" in err
    assert "Traceback" not in err


def test_an_unsupported_suffix_names_the_supported_ones(tmp_path) -> None:
    path = tmp_path / "relatorio.pdf"
    path.write_bytes(b"%PDF-1.4")
    code, _, err = _run(["parse", str(path)])
    assert code == 2
    for suffix in (".docx", ".html", ".txt"):
        assert suffix in err
    assert "Traceback" not in err


def test_an_empty_file_with_a_docx_suffix(tmp_path) -> None:
    path = tmp_path / "vazio.docx"
    path.write_bytes(b"")
    code, _, err = _run(["parse", str(path)])
    assert code == 1
    assert "Traceback" not in err


def test_html_and_txt_files_that_are_empty(tmp_path) -> None:
    """An empty source in a *readable* format is a degenerate document, not a
    malformed file — it must parse and emit."""
    for suffix in (".html", ".txt"):
        path = tmp_path / f"vazio{suffix}"
        path.write_text("")
        code, out, err = _run(["parse", str(path)])
        assert code == 0, err
        assert etree.fromstring(out.encode("utf-8")) is not None


def test_one_bad_file_does_not_abandon_the_good_ones(cases, broken) -> None:
    """A batch that stops at the first bad document is useless on 300 of them."""
    argv = [
        "parse",
        "--format=json",
        str(cases["single_paragraph"]),
        str(broken["corrupt"]),
        str(cases["duplicate_headings"]),
    ]
    code, out, err = _run(argv)
    assert code == 1
    assert out.count('"urn"') == 2
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# nothing, anywhere, prints a traceback
# ---------------------------------------------------------------------------


def test_no_invocation_in_this_module_ever_printed_a_traceback(
    cases, broken, tmp_path
) -> None:
    """The exit criterion as one assertion over every bad input at once."""
    bad = [
        str(broken["corrupt"]),
        str(broken["truncated"]),
        str(broken["not_a_docx"]),
        str(tmp_path / "missing.docx"),
        str(tmp_path),
    ]
    for path in bad:
        for command in ("parse", "dump-styled", "dump-tree", "segment"):
            _, _, err = _run([command, path])
            assert "Traceback" not in err, f"{command} {path}"
