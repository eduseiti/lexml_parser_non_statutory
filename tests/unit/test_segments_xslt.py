"""The XSLT reference path — plan §6.2.

Three stylesheets ship, and their whole value is that they are a **second
implementation**. A reference stylesheet nobody ever ran against the primary
path is documentation; one whose rows are required to equal the Python API's,
document for document, is evidence. That is what
`test_xslt_rows_match_python_rows_*` is, and it has already earned its place:
the first nested stylesheet emitted `descendant::` text in *document* order,
which under §5.4 Constraint 1 is not reading order, and the comparison caught
it on five samples.

Saxon is optional (`pip install 'lexml-nonstat[xslt]'`). Without it every test
here skips **with the reason** `xslt.saxon_reason` reports — never a silent
pass, and never a traceback (plan §9.3's posture, applied to a second optional
dependency).

The community-stylesheet probe (§6.2)
--------------------------------------

Plan §6.2 asks Cycle 7 to probe whether `scripts/GeraCSVporArtigoPorAgrupador.xsl`
"runs unmodified on nested output" and to record the result as informational.
`test_community_stylesheet_probe` runs it on all three of our output shapes and
pins what actually happens. The answer is not the one §6.2 anticipated, and it
is *more* useful than the anticipated one — see that test's docstring and the
cycle report.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import (
    render_generico,
    render_generico_aninhado,
    render_norma,
)
from lexml_nonstat.segments import CSV_COLUMNS, csv_row
from lexml_nonstat.segments.api import _segments_of_document
from lexml_nonstat.segments.xslt import (
    COMMUNITY_STYLESHEET,
    HAVE_SAXON,
    STYLESHEETS,
    SaxonUnavailable,
    rows,
    saxon_reason,
    stylesheet_for,
    transform,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.name for p in SAMPLES_DIR.glob("*.docx"))
STATUTORY_SAMPLE = "port_mf_277_20180607.docx"

requires_saxon = pytest.mark.skipif(
    not HAVE_SAXON, reason=saxon_reason or "saxonche unavailable"
)

_MODELS: dict[str, object] = {}


def model_for(name: str):
    if name not in _MODELS:
        _MODELS[name] = build_model(read_docx(SAMPLES_DIR / name), filename=name)
    return _MODELS[name]


def python_rows(document) -> tuple[tuple[str, ...], ...]:
    """What the primary path would write for this document."""
    return tuple(csv_row(s) for s in _segments_of_document(document))


def xslt_rows(document, emitter: str) -> tuple[tuple[str, ...], ...]:
    """What the reference stylesheet writes, header dropped."""
    return rows(document, stylesheet_for(emitter))[1:]


def sheet_for_document(emitter: str, position: int) -> str:
    """Which stylesheet a bundle's `position`-th document needs.

    An annex is a `DocumentoGenerico` whatever route the primary took (§2.9,
    amendment A-6.5), so the statutory bundle's annex is read by the *generico*
    stylesheet. Getting this wrong would silently compare a document with a
    stylesheet that matches none of its elements and produces a header and
    nothing else — which is exactly the failure mode the community probe below
    documents, so it is worth naming rather than leaving to a lucky index.
    """
    if position == 0:
        return emitter
    return "generico-aninhado" if emitter == "generico-aninhado" else "generico"


@requires_saxon
def test_stylesheets_compile():
    """T-38 — all three compile. A stylesheet that does not is not a reference."""
    from saxonche import PySaxonProcessor

    with PySaxonProcessor(license=False) as proc:
        processor = proc.new_xslt30_processor()
        for emitter, path in STYLESHEETS.items():
            assert path.exists(), f"{emitter}: {path} is missing"
            executable = processor.compile_stylesheet(stylesheet_file=str(path))
            assert executable is not None, f"{emitter} failed to compile"


@requires_saxon
@pytest.mark.parametrize("name", SAMPLES)
def test_xslt_rows_match_python_rows_flat(name):
    """T-35 — the flat stylesheet and the Python reader agree, row for row."""
    bundle = render_generico(model_for(name))
    for position, document in enumerate(bundle.documents):
        assert xslt_rows(
            document, sheet_for_document("generico", position)
        ) == python_rows(document)


@requires_saxon
@pytest.mark.parametrize("name", SAMPLES)
def test_xslt_rows_match_python_rows_nested(name):
    """T-36 — the nested stylesheet and the Python reader agree, row for row.

    This is the one that found a real defect. `string-join((descendant::p,
    descendant::li), ' ')` concatenates two *sequences* in the order written,
    not one node-set in document order, and `descendant::` is document order,
    which Constraint 1 makes different from reading order. Both had to be
    fixed: a union `|` for the first, and a recursive walk sorted by
    `Bloco[@nome='ordem']` for the second.
    """
    bundle = render_generico_aninhado(model_for(name))
    for position, document in enumerate(bundle.documents):
        assert xslt_rows(
            document, sheet_for_document("generico-aninhado", position)
        ) == python_rows(document)


@requires_saxon
def test_xslt_rows_match_python_rows_norma():
    """T-37 — the statutory stylesheet, on the one sample that routes there."""
    bundle = render_norma(model_for(STATUTORY_SAMPLE))
    for position, document in enumerate(bundle.documents):
        assert xslt_rows(
            document, sheet_for_document("norma", position)
        ) == python_rows(document)


@requires_saxon
def test_every_stylesheet_emits_the_declared_columns():
    """The header is `CSV_COLUMNS`, in all three, with no second copy of it.

    The Python writer and the stylesheets have to agree on the header or the
    row comparison above is comparing shifted columns and would still pass.
    """
    model = model_for("pn_cst_38_19801031.docx")
    documents = {
        "generico": render_generico(model).primary,
        "generico-aninhado": render_generico_aninhado(model).primary,
        "norma": render_norma(model_for(STATUTORY_SAMPLE)).primary,
    }
    for emitter, document in documents.items():
        header = rows(document, stylesheet_for(emitter))[0]
        assert header == CSV_COLUMNS, f"{emitter} header drifted"


def test_saxon_absence_is_a_clean_skip():
    """T-40 — the absent-Saxon path is a diagnosis, not a traceback.

    Runs whether or not Saxon is installed, because what it checks is the
    *contract*: `HAVE_SAXON` and `saxon_reason` agree, the reason is
    actionable when there is one, and asking for a transform without Saxon
    raises `SaxonUnavailable` rather than `ImportError` from somewhere inside
    lxml. A user on a bare checkout should be told what to install.
    """
    assert HAVE_SAXON == (saxon_reason is None)
    if not HAVE_SAXON:
        assert "saxonche" in saxon_reason
        assert "xslt" in saxon_reason
        with pytest.raises(SaxonUnavailable):
            transform("<LexML/>", stylesheet_for("generico"))


def test_unknown_emitter_is_refused_by_name():
    """A typo must not silently select a stylesheet, or none."""
    with pytest.raises(ValueError) as excinfo:
        stylesheet_for("generico-aninhada")
    assert "generico-aninhado" in str(excinfo.value)


@requires_saxon
@pytest.mark.skipif(
    not COMMUNITY_STYLESHEET.exists(),
    reason="scripts/GeraCSVporArtigoPorAgrupador.xsl is only in a source checkout",
)
def test_community_stylesheet_probe():
    """§6.2's probe — **informational**, and the answer is not the expected one.

    Plan §6.2 predicts the community stylesheet "runs unmodified on nested
    output" and calls that "the strongest available argument for the
    maintainers' change". Measured here, it does something more interesting:

    * on `norma` output it produces **real rows** — 4 for `port_mf_277`;
    * on `generico` output, **a header and nothing else**;
    * on `generico-aninhado` output, **a header and nothing else**.

    The reason is one grep: the stylesheet contains zero occurrences of
    `AgrupamentoHierarquico`. It selects on statutory element *names*
    (`//Artigo`, `//Capitulo`, `//Secao`, …), so no `Agrupamento`-based
    document reaches it, nested or flat.

    **This does not weaken the case for the maintainers' change — it sharpens
    it.** §6.2's argument was that the recursive form is what community tooling
    already speaks, and the *idiom* half of that is true: the breadcrumb here
    really is `ancestor::*/NomeAgrupador`, exactly what
    `segment_generico_aninhado.xsl` uses and what the flat stylesheet has to
    fake with `starts-with(@id, …)` arithmetic. What the probe adds is that
    element *names* matter too: a non-statutory document is invisible to this
    tool today whichever way we emit it, so the reply to the maintainers (§11)
    should ask for `AgrupamentoHierarquico` in the stylesheet's selection as
    well as in the schema. That is a concrete, checkable request, which the
    predicted "it just works" would not have been.

    Pinned as an assertion rather than printed, so the day the community
    stylesheet *does* grow those selectors, this test fails and the cycle
    report's claim gets revisited instead of quietly ageing.
    """
    import csv
    import io

    model = model_for(STATUTORY_SAMPLE)
    outputs = {
        "norma": transform(render_norma(model).primary, COMMUNITY_STYLESHEET),
        "generico": transform(render_generico(model).primary, COMMUNITY_STYLESHEET),
        "generico-aninhado": transform(
            render_generico_aninhado(model_for("pn_cst_38_19801031.docx")).primary,
            COMMUNITY_STYLESHEET,
        ),
    }
    counts = {
        emitter: len([r for r in csv.reader(io.StringIO(text)) if r]) - 1
        for emitter, text in outputs.items()
    }

    assert counts["norma"] == 4, "the statutory route is the one it reads"
    assert counts["generico"] == 0
    assert counts["generico-aninhado"] == 0

    # The measured cause, asserted so the explanation cannot drift from the
    # numbers above.
    assert "AgrupamentoHierarquico" not in COMMUNITY_STYLESHEET.read_text(
        encoding="utf-8"
    )
