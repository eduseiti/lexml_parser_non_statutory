"""Byte-stable `generico` XML goldens — the first *emitted artifact* goldens.

The fifth golden layer, and the first that is not an internal representation:
Cycles 1–4b pinned what the reader saw, what the extractor concluded, how the
document divides, what shape its body has and how it routes. This pins the
thing a consumer actually receives.

Plan §9.4 — goldens regenerate only via
`python3 scripts/regen_goldens.py --kind=generico`, so any diff here is a
reviewed behaviour change rather than silent drift.

Sixteen files for fifteen samples: `port_mf_277_20180607` carries an annex, and
an annex is a **standalone sibling document** under the reference parser's
convention (plan §2.9), written as `port_mf_277_20180607.anexo1.xml` — the same
naming as its own `lei_5070_19660707.anexo1.xml`.

`port_mf_277` routes to `norma` and is rendered flat here anyway. That is not a
mistake and not a pre-emption of Cycle 6: the flat emitter is plan §3's
documented validate-then-fallback rendering, so every document must have one,
and this sample is the corpus's only exercise of `Anexos`/`ReferenciaAnexo`.

A golden on its own is weak evidence — one recording a bug passes forever. So
this module also re-checks, **against the committed files rather than against a
freshly rendered tree**, the two properties a golden could otherwise silently
record as broken: that each file validates on both schemas, and that ids are
unique. A golden that stopped validating would still match itself.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.render import render_generico_from_docx
from lexml_nonstat.validate import validate

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERICO_DIR = REPO_ROOT / "tests" / "golden" / "generico"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: The samples that emit an annex document, and how many.
ANNEXED = {"port_mf_277_20180607": 1}

REGEN = (
    "If this change is intended, run "
    "`python3 scripts/regen_goldens.py --kind=generico` and review the diff — "
    "a golden change is a behaviour change (plan §9.4)."
)

_RENDERED: dict[str, object] = {}


def render(name: str):
    """Render one sample, cached — the emitter is the slow part of this module."""
    if name not in _RENDERED:
        _RENDERED[name] = render_generico_from_docx(
            SAMPLES_DIR / f"{name}.docx", filename=f"{name}.docx"
        )
    return _RENDERED[name]


def golden_files(name: str) -> list[Path]:
    """Every golden file for one sample: the primary, then each annex."""
    files = [GENERICO_DIR / f"{name}.xml"]
    for ordinal in range(1, ANNEXED.get(name, 0) + 1):
        files.append(GENERICO_DIR / f"{name}.anexo{ordinal}.xml")
    return files


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_matches(name: str):
    """The emitter still produces byte-identically what was reviewed."""
    bundle = render(name)
    documents = bundle.documents
    files = golden_files(name)

    assert len(documents) == len(files), (
        f"{name}: emitter produced {len(documents)} document(s) but "
        f"{len(files)} golden file(s) exist. {REGEN}"
    )

    for document, path in zip(documents, files):
        assert path.exists(), f"{name}: missing golden {path.name}. {REGEN}"
        expected = path.read_text(encoding="utf-8")
        actual = bundle.to_xml_string(document)
        assert actual == expected, f"{name}: {path.name} differs. {REGEN}"


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_is_valid(name: str):
    """Every committed golden validates on **both** schemas, read from disk.

    Deliberately parsed from the file rather than taken from the emitter: a
    golden that had stopped being valid would still match itself, so validity
    has to be checked against the artifact, not against the code that wrote it.
    This is plan invariant #1 asserted where it is hardest to fake.
    """
    for path in golden_files(name):
        document = etree.parse(str(path))
        report = validate(document, "both")
        assert report.ok, f"{name}: {path.name} is invalid\n{report.summary()}"


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_ids_unique(name: str):
    """`id` uniqueness (plan invariant #5), per document and across the bundle.

    Per document because `xsd:ID` scopes to a document; across the bundle too,
    because a citation names a document *and* a fragment, and a fragment that
    means two things in one bundle is a citation that cannot be resolved.
    """
    seen: list[str] = []
    for path in golden_files(name):
        root = etree.parse(str(path)).getroot()
        ids = [
            value
            for node in root.iter()
            if (value := node.get("id")) is not None
        ]
        duplicates = [i for i, n in Counter(ids).items() if n > 1]
        assert not duplicates, f"{name}: {path.name} repeats ids {duplicates}"
        seen.extend(ids)

    across = [i for i, n in Counter(seen).items() if n > 1]
    assert not across, f"{name}: ids shared between bundle documents: {across}"


def test_goldens_exist_for_every_sample():
    """Fifteen primaries, one annex, and nothing orphaned.

    The orphan half matters as much as the missing half: a golden left behind
    by a renamed sample is a file nothing regenerates and nothing checks, which
    is exactly the silent drift §9.4 exists to prevent.
    """
    expected = {path.name for name in SAMPLES for path in golden_files(name)}
    present = {path.name for path in GENERICO_DIR.glob("*.xml")}

    assert not expected - present, f"missing goldens: {sorted(expected - present)}. {REGEN}"
    assert not present - expected, f"orphaned goldens: {sorted(present - expected)}. {REGEN}"
    assert len(expected) == len(SAMPLES) + sum(ANNEXED.values()) == 16
