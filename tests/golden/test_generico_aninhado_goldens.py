"""Byte-stable `generico-aninhado` XML goldens — the nested emitted artifact.

The seventh golden layer, and the second that pins a thing a consumer actually
receives. Its flat twin is `test_generico_goldens.py`; the two together are the
file-level form of plan invariant #11 — the same fifteen samples, the same
sixteen documents, written two different ways, carrying the same text.

Plan §9.4 — goldens regenerate only via
`python3 scripts/regen_goldens.py --kind=generico-aninhado`, so any diff here
is a reviewed behaviour change rather than silent drift.

Sixteen files for fifteen samples, mirroring Cycle 5 exactly (spec decision
R-4, following amendment A-5.5): `port_mf_277_20180607` carries an annex, and
an annex is a **standalone sibling document** under the reference parser's
convention (plan §2.9), written as `port_mf_277_20180607.anexo1.xml`.

Two things are different here, and both are the point of the cycle.

**Validity is gated, and the gate is a probe.** Nested output is valid only
against `lexml-proposed/`, the generated generation carrying the maintainers'
unreleased §2.10 change. So `test_golden_is_valid` validates against the
*proposed* generation and **skips with the probe's own diagnostic** when that
generation is absent — amendment A-R.2's "probed, never assumed", and A-R.9's
requirement that the suite stay green against `lexml/` alone. The companion
`test_golden_is_invalid_on_shipped_schemas_iff_nested` is what stops that skip
from being a hiding place: it runs everywhere, needs no proposed schemas, and
would fail loudly if the emitter ever quietly started producing
flat-compatible output where it should nest. Its `iff` is not hedging — six of
the sixteen documents have no body sections at all, so both emitters render
them identically and they are *correctly* valid on the shipped schemas.

**Rule A is asserted, and asserted redundant.** The flat emitter needs Rule A
because its hierarchy lives in the `id` path; here the hierarchy is the element
tree, so a missing ancestor is not expressible. The check is kept anyway, on
the committed files, because a golden recording a broken invariant passes
forever otherwise.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.render import local_name, missing_prefixes
from lexml_nonstat.render import render_generico_aninhado_from_docx
from lexml_nonstat.validate.schema import PROPOSED, SHIPPED, validate
from tests.conftest import requires_nested

REPO_ROOT = Path(__file__).resolve().parents[2]
NESTED_DIR = REPO_ROOT / "tests" / "golden" / "generico_aninhado"
SAMPLES_DIR = REPO_ROOT / "samples"

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: The samples that emit an annex document, and how many.
ANNEXED = {"port_mf_277_20180607": 1}

REGEN = (
    "If this change is intended, run "
    "`python3 scripts/regen_goldens.py --kind=generico-aninhado` and review "
    "the diff — a golden change is a behaviour change (plan §9.4)."
)

_RENDERED: dict[str, object] = {}


def render(name: str):
    """Render one sample, cached — the emitter is the slow part of this module."""
    if name not in _RENDERED:
        _RENDERED[name] = render_generico_aninhado_from_docx(
            SAMPLES_DIR / f"{name}.docx", filename=f"{name}.docx"
        )
    return _RENDERED[name]


def golden_files(name: str) -> list[Path]:
    """Every golden file for one sample: the primary, then each annex."""
    files = [NESTED_DIR / f"{name}.xml"]
    for ordinal in range(1, ANNEXED.get(name, 0) + 1):
        files.append(NESTED_DIR / f"{name}.anexo{ordinal}.xml")
    return files


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_matches(name: str):
    """The nested emitter still produces byte-identically what was reviewed."""
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


@requires_nested
@pytest.mark.parametrize("name", SAMPLES)
def test_golden_is_valid(name: str):
    """Every committed golden validates on **both** proposed schemas, from disk.

    Parsed from the file rather than taken from the emitter: a golden that had
    stopped being valid would still match itself, so validity is checked
    against the artifact and not against the code that wrote it.
    """
    for path in golden_files(name):
        document = etree.parse(str(path))
        report = validate(document, "both", generation=PROPOSED)
        assert report.ok, f"{name}: {path.name} is invalid\n{report.summary()}"


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_is_invalid_on_shipped_schemas_iff_nested(name: str):
    """A golden carrying an `AgrupamentoHierarquico` is rejected by `lexml/`.

    This is `test_golden_is_valid`'s anti-vacuity partner and the reason its
    skip is safe: it needs no proposed schemas, so it runs on every checkout.
    If the emitter ever produced nested output the shipped schemas accepted,
    the §2.10 premise of this whole cycle would be wrong, and a skipped
    validity test would not have noticed.

    The `iff` is load-bearing and was found by this test failing. **Six of the
    sixteen documents contain no `AgrupamentoHierarquico` at all** —
    `REsp_1306393`, `ad_pgfn_3`, `ad_srf_22`, `adn_cosit_19`, `sumula_carf_42`
    and `port_mf_277`'s *primary* (its 65 sections all live in the annex).
    Those documents are nothing but front and back matter, which both emitters
    render identically through the shared `front_region`/`back_region`
    (amendment A-5.1), so their output is byte-identical to the flat golden and
    is *correctly* valid on the shipped schemas. Asserting invalidity for all
    sixteen would have pinned a defect rather than a property; asserting it for
    exactly those that nest says the true thing, and `test_golden_matches`
    already pins that the byte-identical six really are byte-identical.
    """
    for path in golden_files(name):
        document = etree.parse(str(path))
        nests = any(
            local_name(node.tag) == "AgrupamentoHierarquico"
            for node in document.getroot().iter()
        )
        report = validate(document, "both", generation=SHIPPED)

        if nests:
            assert not report.ok, (
                f"{name}: {path.name} nests `AgrupamentoHierarquico` yet "
                "validates against the *shipped* schemas. Nested "
                "`AgrupamentoHierarquico` is unreleased (§2.10), so this means "
                "the vendored schemas in `lexml/` have been modified, which "
                "CLAUDE.md forbids."
            )
        else:
            assert report.ok, (
                f"{name}: {path.name} carries no `AgrupamentoHierarquico`, so "
                "it is ordinary flat `generico` output and must still validate "
                f"on the shipped schemas\n{report.summary()}"
            )


def test_exactly_the_expected_documents_nest():
    """Which documents nest is itself pinned — a count, not an assumption.

    Ten of the sixteen carry an `AgrupamentoHierarquico`; the other six have no
    body sections to nest. If a change to hierarchy inference moved a document
    between those groups, the sibling test above would quietly change meaning
    rather than fail, so the partition is asserted directly.
    """
    flat_only = set()
    for name in SAMPLES:
        for path in golden_files(name):
            root = etree.parse(str(path)).getroot()
            if not any(
                local_name(node.tag) == "AgrupamentoHierarquico"
                for node in root.iter()
            ):
                flat_only.add(path.stem)

    assert flat_only == {
        "REsp_1306393",
        "ad_pgfn_3_20080918",
        "ad_srf_22_19970430",
        "adn_cosit_19_20001025",
        "port_mf_277_20180607",
        "sumula_carf_42",
    }, (
        "the set of documents with no nestable body sections changed: "
        f"{sorted(flat_only)}. {REGEN}"
    )


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


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_has_no_orphan_ids(name: str):
    """Rule A on the committed files — and it should be trivially satisfied.

    In the flat emitter this is load-bearing: `pp1_agr1_agr2` must exist or the
    breadcrumb for `pp1_agr1_agr2_agr1` silently loses its middle ancestor.
    Here the tree carries itself, so this asserts a property the structure
    already guarantees. Kept because "guaranteed by construction" is a claim
    about code, and a golden is evidence about output.
    """
    for path in golden_files(name):
        root = etree.parse(str(path)).getroot()
        parte = next(
            (n for n in root.iter() if local_name(n.tag) == "PartePrincipal"),
            None,
        )
        if parte is None:
            continue
        root_id = parte.get("id") or "pp1"
        ids = [
            value
            for node in parte.iter()
            if (value := node.get("id")) is not None
        ]
        gaps = missing_prefixes(ids, root=root_id)
        assert not gaps, f"{name}: {path.name} has orphan id prefixes {gaps}"


@pytest.mark.parametrize("name", SAMPLES)
def test_golden_carries_no_retired_bloco(name: str):
    """`rotulo`, `nomeAgrupador` and `nivel` are retired — checked on disk.

    The nested form makes all three native or derivable, and §5.2 is explicit
    that a redundant depth marker which can disagree with the tree is a
    liability. Asserted on the committed artifact so a regression cannot hide
    behind a golden that was regenerated without review.
    """
    retired = {"rotulo", "nomeAgrupador", "nivel"}
    for path in golden_files(name):
        root = etree.parse(str(path)).getroot()
        found = {
            node.get("nome")
            for node in root.iter()
            if local_name(node.tag) == "Bloco" and node.get("nome") in retired
        }
        assert not found, f"{name}: {path.name} still emits Bloco {sorted(found)}"


def test_goldens_exist_for_every_sample():
    """Fifteen primaries, one annex, and nothing orphaned.

    The orphan half matters as much as the missing half: a golden left behind
    by a renamed sample is a file nothing regenerates and nothing checks, which
    is exactly the silent drift §9.4 exists to prevent.
    """
    expected = {path.name for name in SAMPLES for path in golden_files(name)}
    present = {path.name for path in NESTED_DIR.glob("*.xml")}

    assert not expected - present, f"missing goldens: {sorted(expected - present)}. {REGEN}"
    assert not present - expected, f"orphaned goldens: {sorted(present - expected)}. {REGEN}"
    assert len(expected) == len(SAMPLES) + sum(ANNEXED.values()) == 16


def test_nested_and_flat_golden_sets_are_parallel():
    """The two emitters commit the same sixteen documents, named identically.

    Invariant #11 at the file level: cross-emitter equivalence is only
    checkable file-for-file if the two golden directories name the same
    documents. A sample present in one and missing from the other is an
    equivalence claim nothing tests.
    """
    flat = {p.name for p in (REPO_ROOT / "tests" / "golden" / "generico").glob("*.xml")}
    nested = {p.name for p in NESTED_DIR.glob("*.xml")}
    assert flat == nested, (
        "golden sets diverge — "
        f"flat only: {sorted(flat - nested)}; nested only: {sorted(nested - flat)}"
    )
