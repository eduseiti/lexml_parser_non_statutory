"""Byte-stable **linked** XML goldens — `<Remissao>` as a committed artifact.

The tenth and eleventh golden kinds (Cycle 8e, amendment A-L.6), and the first
that depend on an *external* tool's answers. That is exactly why they are
fixture-backed: `tests/linker_fixtures/` carries what the linker said, so these
goldens regenerate and compare on a checkout with **no `linkertool` at all**.
Only *refreshing* the answers needs the binary, through the explicit
`scripts/record_linker_fixtures.py` — §9.3's rule, so a linker upgrade arrives
as a reviewed fixture diff rather than as output that quietly changed.

Sixteen `generico-linked` files for fifteen samples (`port_mf_277` carries an
annex), and two `norma-linked` files for the one sample §4.4 routes to `norma`.

`sumula_carf_42` is committed with **zero** references, deliberately. A golden
proving that a document renders identically linked and unlinked is as much a
regression test as one full of `Remissao` — it is what would catch a linker
that started inventing citations.

As in the other golden modules, the committed *files* are re-checked rather
than only compared: a golden that had stopped validating, or that had quietly
lost text, would still match itself. Conservation here is asserted on the
**character** multiset against the unlinked twin (A-L.4, A-Q.6) — splitting a
run at a reference boundary moves a leaf boundary, and a word-level comparison
cannot tell that from real damage. It is the assertion that actually caught a
defect in this cycle: lxml's pretty-printer indented an all-element paragraph
and injected three spaces into `CARNE_LEAO`, in a document that was valid on
both schemas.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.render.common import leaf_texts
from lexml_nonstat.validate import validate

REPO_ROOT = Path(__file__).resolve().parents[2]
LINKED_DIR = REPO_ROOT / "tests" / "golden" / "generico_linked"
NORMA_LINKED_DIR = REPO_ROOT / "tests" / "golden" / "norma_linked"
GENERICO_DIR = REPO_ROOT / "tests" / "golden" / "generico"
NORMA_DIR = REPO_ROOT / "tests" / "golden" / "norma"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: The samples that emit an annex document, and how many.
ANNEXED = {"port_mf_277_20180607": 1}

#: The one sample §4.4 routes to the statutory emitter.
STATUTORY = "port_mf_277_20180607"

REGEN = (
    "If this change is intended, run "
    "`python3 scripts/regen_goldens.py --kind=generico-linked` (or "
    "`--kind=norma-linked`) and review the diff — a golden change is a "
    "behaviour change (plan §9.4). If the *linker's answers* changed, that is "
    "`scripts/record_linker_fixtures.py`, and the fixture diff is the review."
)

_RENDERED: dict[str, object] = {}


def render(name: str):
    """Render one sample with the fixture-backed linker, cached.

    Built here rather than imported from `regen_goldens.py` so the test
    exercises the same public API a user would: `render_generico(model,
    linker=…)`. A test that called the generator's private helper could not
    catch a generator that had drifted from the emitter.
    """
    if name not in _RENDERED:
        from lexml_nonstat.ingest import read_docx
        from lexml_nonstat.model import build_model
        from lexml_nonstat.render.generico import render_generico

        from tests.conftest import fixture_linker

        model = build_model(
            read_docx(SAMPLES_DIR / f"{name}.docx"), filename=f"{name}.docx"
        )
        _RENDERED[name] = render_generico(model, linker=fixture_linker())
    return _RENDERED[name]


def golden_files(name: str) -> list[Path]:
    files = [LINKED_DIR / f"{name}.xml"]
    for ordinal in range(1, ANNEXED.get(name, 0) + 1):
        files.append(LINKED_DIR / f"{name}.anexo{ordinal}.xml")
    return files


def unlinked_twin(path: Path) -> Path:
    """The same document rendered with `NullLinker` — the conservation control."""
    if path.parent == LINKED_DIR:
        return GENERICO_DIR / path.name
    return NORMA_DIR / path.name


def all_linked_files() -> list[Path]:
    return sorted(LINKED_DIR.glob("*.xml")) + sorted(NORMA_LINKED_DIR.glob("*.xml"))


# ---------------------------------------------------------------------------
# The goldens themselves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_linked_golden_matches(name: str):
    """T-G2 — byte-identical, and with **no binary present**.

    The fixtures carry the answers, so this test is not conditional on
    `requires_linker`. That is the whole point of A-L.6: an optional external
    tool must not make a golden un-runnable.
    """
    bundle = render(name)
    documents = bundle.documents
    files = golden_files(name)

    assert len(documents) == len(files), (
        f"{name}: emitter produced {len(documents)} document(s) but "
        f"{len(files)} golden file(s) exist. {REGEN}"
    )

    for document, path in zip(documents, files):
        assert path.exists(), f"{name}: missing golden {path.name}. {REGEN}"
        assert bundle.to_xml_string(document) == path.read_text(
            encoding="utf-8"
        ), f"{name}: {path.name} differs. {REGEN}"


@pytest.mark.parametrize("path", all_linked_files(), ids=lambda p: p.name)
def test_linked_golden_is_valid(path: Path):
    """Invariant #1 — every linked golden validates on **both** schemas.

    Read from disk, not from the emitter: matrix row R2 pins that a `Remissao`
    without `xlink:href` is invalid, and this is where a renderer that started
    emitting one would be caught.
    """
    report = validate(etree.parse(str(path)), "both")
    assert report.ok, f"{path.name} is invalid\n{report.summary()}"


@pytest.mark.parametrize("path", all_linked_files(), ids=lambda p: p.name)
def test_linked_golden_conserves_text(path: Path):
    """T-C1 — the character multiset equals the unlinked twin's (A-L.4).

    A `Remissao` wraps existing text and adds none, so this must hold exactly.
    No schema can see a violation — Cycle 6's first statutory render was valid
    on both schemas and 29 words short (A-6.4) — and this cycle's own
    pretty-print defect was invisible to everything except this assertion.
    """
    twin = unlinked_twin(path)
    assert twin.exists(), f"no unlinked twin for {path.name}"

    linked = Counter("".join(leaf_texts(etree.parse(str(path)).getroot())))
    plain = Counter("".join(leaf_texts(etree.parse(str(twin)).getroot())))

    assert linked == plain, (
        f"{path.name}: linking changed the text.\n"
        f"  gained: {dict(linked - plain)}\n"
        f"  lost  : {dict(plain - linked)}"
    )


@pytest.mark.parametrize("path", all_linked_files(), ids=lambda p: p.name)
def test_linked_golden_ids_are_unchanged(path: Path):
    """T-C5 — a `Remissao` carries no `id`, so invariant #11 cannot move.

    Stated as a test rather than as a fact about the element: it is what keeps
    the `segments` goldens' urls resolvable against the linked artifact too.
    """
    twin = unlinked_twin(path)

    def ids(target: Path) -> list[str]:
        return [
            value
            for node in etree.parse(str(target)).getroot().iter()
            if (value := node.get("id")) is not None
        ]

    assert ids(path) == ids(twin), f"{path.name}: linking moved an id"


@pytest.mark.parametrize("path", all_linked_files(), ids=lambda p: p.name)
def test_every_remissao_carries_a_urn(path: Path):
    """T-N7, on the committed artifacts."""
    root = etree.parse(str(path)).getroot()
    remissoes = root.findall(".//{http://www.lexml.gov.br/1.0}Remissao")

    for remissao in remissoes:
        href = remissao.get("{http://www.w3.org/1999/xlink}href")
        assert href, f"{path.name}: a Remissao carries no xlink:href"
        assert href.startswith("urn:lex:"), (
            f"{path.name}: {href!r} is not a urn:lex: — the whole point of the "
            "element is that a citation resolves to a LexML identity"
        )
        assert "".join(remissao.itertext()).strip(), (
            f"{path.name}: an empty Remissao wraps nothing and means nothing"
        )


# ---------------------------------------------------------------------------
# The corpus-level facts these goldens record
# ---------------------------------------------------------------------------


def test_goldens_exist_for_every_sample():
    """Sixteen linked primaries plus one annex; nothing missing, nothing orphaned."""
    expected = {path.name for name in SAMPLES for path in golden_files(name)}
    present = {path.name for path in LINKED_DIR.glob("*.xml")}

    assert not expected - present, f"missing: {sorted(expected - present)}. {REGEN}"
    assert not present - expected, f"orphaned: {sorted(present - expected)}. {REGEN}"
    assert len(expected) == len(SAMPLES) + sum(ANNEXED.values()) == 16


def test_the_statutory_sample_has_linked_norma_goldens():
    """`norma-linked` covers exactly what `norma` covers — one sample."""
    present = {path.name for path in NORMA_LINKED_DIR.glob("*.xml")}

    assert present == {f"{STATUTORY}.xml", f"{STATUTORY}.anexo1.xml"}, (
        f"norma-linked must mirror the norma kind's coverage. {REGEN}"
    )


def test_references_were_actually_resolved():
    """The goldens must *contain* references, or they pin nothing.

    A-C.1's lesson generalised to the artifact: a linked golden identical to
    its unlinked twin would pass every other test in this module while proving
    the feature does nothing.
    """
    total = sum(
        len(etree.parse(str(path)).getroot().findall(
            ".//{http://www.lexml.gov.br/1.0}Remissao"
        ))
        for path in all_linked_files()
    )

    assert total > 200, (
        f"only {total} Remissao elements across the linked goldens; the "
        "corpus resolves far more than that, so something stopped linking"
    )


def test_the_zero_reference_sample_is_committed_unchanged():
    """`sumula_carf_42` resolves nothing, and that is a recorded fact.

    The linker's grammar has no rule for súmulas — the `súmula` rule is
    commented out upstream (`Regras2.hs:1009-1012`) — so this document is the
    corpus's negative case, and it must render **identically** linked and
    unlinked. If it ever gains a `Remissao`, either the grammar changed or we
    started fabricating, and both need a human to look.
    """
    linked = LINKED_DIR / "sumula_carf_42.xml"
    plain = GENERICO_DIR / "sumula_carf_42.xml"

    assert linked.read_text(encoding="utf-8") == plain.read_text(encoding="utf-8")
    assert "<Remissao" not in linked.read_text(encoding="utf-8")


def test_the_linked_goldens_differ_from_their_twins_where_they_should():
    """Every other sample that resolves references must actually differ."""
    differing = [
        path.name
        for path in all_linked_files()
        if path.read_text(encoding="utf-8")
        != unlinked_twin(path).read_text(encoding="utf-8")
    ]

    assert len(differing) >= 13, (
        f"only {len(differing)} linked goldens differ from their unlinked "
        "twins; the corpus resolves references in 14 of 15 samples"
    )
