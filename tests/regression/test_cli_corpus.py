"""The CLI over the whole corpus, every emitter — Cycle 8, spec §5.1 and E-2.

Plan §8's Cycle 8 asks for "CLI end-to-end on all 15 samples, all emitters".
That is 60 invocations, and the value is not that they exit 0 — it is that what
the CLI writes is *exactly* what the library renders. A CLI that quietly
re-implemented a rendering would pass an exit-code test while making every
golden in `tests/golden/` stop covering what a user actually runs.

So the load-bearing tests here are the byte-identity ones:
:func:`test_cli_output_matches_the_library` and
:func:`test_segment_matches_the_library`. The rest establish that no sample
crashes and that the emitters' outputs validate where they are supposed to.

The nested leg's *validity* assertions are gated on the capability probe
(A-5b.3, A-R.9): nested output is invalid against the shipped schemas by
design, and the suite must stay green on a checkout without `lexml-proposed/`.
Its *rendering* is not gated — A-7.4's finding that reading and writing nested
markup needs no schema at all applies here too.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat import cli
from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import (
    render_generico,
    render_generico_aninhado,
    render_statutory,
)
from lexml_nonstat.segments import segments_from_model, to_csv
from lexml_nonstat.validate import validate

from tests.conftest import requires_nested

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = sorted((REPO_ROOT / "samples").glob("*.docx"))
SAMPLE_IDS = [p.stem for p in SAMPLES]

#: Every emitter the CLI offers, `auto` included — spec §3.5's `CHOOSABLE_EMITTERS`.
EMITTERS = cli.CHOOSABLE_EMITTERS

#: The emitters a bare checkout can *select*. Plan §5.2 is explicit that
#: **emitter selection** refuses with the probe's diagnostic when the vendored
#: schemas are flat, while the renderer itself always renders (A-5b.3). So a
#: CLI request for `generico-aninhado` is answered with exit 2 on a checkout
#: without `lexml-proposed/` — correct behaviour, and the reason these
#: parametrisations are gated rather than the gate being loosened.
ALWAYS_SELECTABLE = tuple(e for e in EMITTERS if e != "generico-aninhado")


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def models() -> dict:
    """One model per sample, built once — 15 pipelines is the expensive part."""
    return {p.stem: build_model(read_docx(p), filename=p.name) for p in SAMPLES}


def test_the_corpus_is_the_expected_size() -> None:
    """A sample added without a golden would otherwise pass silently."""
    assert len(SAMPLES) == 15


# ---------------------------------------------------------------------------
# 15 samples × 4 emitters — the plan's bullet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("emitter", ALWAYS_SELECTABLE)
@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_parse_every_sample_every_emitter(path: Path, emitter: str) -> None:
    code, out, err = _run(["parse", f"--emitter={emitter}", str(path)])
    assert code == 0, err
    assert etree.fromstring(out.encode("utf-8")) is not None
    assert "Traceback" not in err


@requires_nested
@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_parse_every_sample_nested(path: Path) -> None:
    """The fourth emitter, where the checkout can select it."""
    code, out, err = _run(["parse", "--emitter=generico-aninhado", str(path)])
    assert code == 0, err
    assert etree.fromstring(out.encode("utf-8")) is not None
    assert "Traceback" not in err


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_nested_selection_is_answered_one_way_or_the_other(path: Path) -> None:
    """Whatever the checkout holds, the answer is clean — never a traceback.

    This is the assertion that runs in *both* configurations, and it is what
    makes A-R.9's "exits cleanly with the probe's diagnostic" checkable on the
    bare checkout that amendment most wants green.
    """
    code, out, err = _run(["parse", "--emitter=generico-aninhado", str(path)])
    assert code in (0, 2)
    assert "Traceback" not in err
    if code == 0:
        assert etree.fromstring(out.encode("utf-8")) is not None
    else:
        assert out == ""
        assert err.strip()


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_every_sample_exits_zero_without_strict(path: Path) -> None:
    """Cycle 8's "handles any document" criterion, on the real corpus."""
    assert _run(["parse", str(path)])[0] == 0


# ---------------------------------------------------------------------------
# the CLI adds no rendering of its own
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_cli_output_matches_the_library(models, path: Path) -> None:
    _, out, _ = _run(["parse", "--emitter=generico", str(path)])
    assert out == render_generico(models[path.stem]).to_xml_string()


@requires_nested
@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_cli_nested_output_matches_the_library(models, path: Path) -> None:
    _, out, _ = _run(["parse", "--emitter=generico-aninhado", str(path)])
    assert out == render_generico_aninhado(models[path.stem]).to_xml_string()


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_segment_matches_the_library(models, path: Path) -> None:
    _, out, _ = _run(["segment", str(path)])
    assert out == to_csv(segments_from_model(models[path.stem]))


# ---------------------------------------------------------------------------
# validity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_flat_output_validates_on_both_shipped_schemas(path: Path) -> None:
    """Invariant #1 through the CLI, on the generation that actually ships."""
    _, out, _ = _run(["parse", "--emitter=generico", str(path)])
    report = validate(etree.fromstring(out.encode("utf-8")), "both")
    assert report.ok, report.summary()


@requires_nested
@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_nested_output_validates_on_the_proposed_schemas(path: Path) -> None:
    _, out, _ = _run(["parse", "--emitter=generico-aninhado", str(path)])
    report = validate(
        etree.fromstring(out.encode("utf-8")), "both", generation="proposed"
    )
    assert report.ok, report.summary()


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_auto_output_validates(path: Path) -> None:
    """`auto` may pick the statutory emitter, which targets the shipped schemas."""
    _, out, _ = _run(["parse", str(path)])
    report = validate(etree.fromstring(out.encode("utf-8")), "both")
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# `auto` follows the route, and says which emitter actually ran
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_auto_matches_render_statutory(models, path: Path) -> None:
    """A-6.3: the reported emitter is the one that actually produced the bytes."""
    _, out, _ = _run(["parse", "--format=json", str(path)])
    report = json.loads(out)
    expected = render_statutory(models[path.stem])
    assert report["emitter"] == expected.emitter
    assert report["route"] == models[path.stem].route


def test_exactly_one_sample_routes_to_norma(models) -> None:
    """§4.4's ground truth, restated where a CLI change would break it."""
    routed = [name for name, model in models.items() if model.route == "norma"]
    assert routed == ["port_mf_277_20180607"]


# ---------------------------------------------------------------------------
# the bundle, written to disk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", SAMPLES, ids=SAMPLE_IDS)
def test_out_writes_every_document_of_the_bundle(models, path: Path, tmp_path) -> None:
    target = tmp_path / path.stem
    code, _, _ = _run(["parse", "-o", str(target), str(path)])
    assert code == 0
    written = sorted(target.glob("*.xml"))
    assert len(written) == len(render_statutory(models[path.stem]).documents)
    for document in written:
        assert etree.parse(str(document)) is not None


def test_the_annex_bearing_sample_writes_two_documents(tmp_path) -> None:
    """§2.9's convention, end to end: a primary and an `!anexo1` sibling."""
    sample = REPO_ROOT / "samples" / "port_mf_277_20180607.docx"
    _run(["parse", "-o", str(tmp_path), str(sample)])
    names = sorted(p.name for p in tmp_path.glob("*.xml"))
    assert len(names) == 2
    assert sum("!anexo1" in name for name in names) == 1


# ---------------------------------------------------------------------------
# whole-corpus invocations
# ---------------------------------------------------------------------------


def test_the_whole_corpus_in_one_invocation() -> None:
    code, out, err = _run(["parse", "--format=json"] + [str(p) for p in SAMPLES])
    assert code == 0, err
    assert out.count('"urn"') == len(SAMPLES)
    assert "Traceback" not in err


def test_decisions_report_over_the_whole_corpus() -> None:
    """§7.4's summary, reconciling across every sample at once."""
    code, out, _ = _run(["decisions-report"] + [str(p) for p in SAMPLES])
    assert code == 0
    assert "Decisions:" in out
    # A-4b.3: the corpus flags exactly four decisions and consults nobody,
    # because §9.3 pins `--referee=none`.
    assert "Flagged:               4" in out
    assert "put to a referee:    0" in out


def test_every_sample_dumps_and_segments() -> None:
    for command in ("dump-styled", "dump-tree", "segment"):
        code, out, err = _run([command] + [str(p) for p in SAMPLES])
        assert code == 0, f"{command}: {err}"
        assert out.strip()
        assert "Traceback" not in err
