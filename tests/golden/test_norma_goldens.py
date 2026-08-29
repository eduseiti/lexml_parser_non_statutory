"""Byte-stable `norma` XML goldens — the statutory emitted artifact.

The eighth golden layer, and the third that pins a thing a consumer actually
receives. Unlike its two siblings it covers **one sample**, and that is the
cycle's whole point: §4.4 routes fourteen of fifteen to `generico`, and
"statutory detection's main job is refusing false positives, not finding
statutes". A `norma` golden for `parecer_93` would be a golden for a document
this parser must never produce.

Plan §9.4 — goldens regenerate only via
`python3 scripts/regen_goldens.py --kind=norma`, so any diff here is a reviewed
behaviour change rather than silent drift.

Two files for one sample: `port_mf_277_20180607.xml` and its annex,
`port_mf_277_20180607.anexo1.xml`. The annex is a **standalone sibling
document** (plan §2.9) and — since Cycle 6 folded three copies of that
convention into `render/anexo.py` — it is **byte-identical to the annex the
flat emitter writes**. `test_annex_is_byte_identical_across_emitters` asserts
exactly that, and it is the file-level proof that extracting the shared module
changed no behaviour.

The goldens are written by `render_norma`, **not** `render_statutory`: the
golden is this emitter's output, and routing it through §4.2's fallback would
silently replace it with the flat rendering the moment the statutory render
broke — which is precisely the regression the golden exists to catch.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import all_ids, leaf_texts, local_name, words
from lexml_nonstat.render.norma import ARTIGO_ID_RE, EMITTER, render_norma
from lexml_nonstat.validate.schema import SHIPPED, validate

REPO_ROOT = Path(__file__).resolve().parents[2]
NORMA_DIR = REPO_ROOT / "tests" / "golden" / "norma"
GENERICO_DIR = REPO_ROOT / "tests" / "golden" / "generico"
SAMPLES_DIR = REPO_ROOT / "samples"

#: The samples §4.4 routes to `norma`, and how many annexes each emits.
#: A dict of one, deliberately: fourteen documents having **no** golden here is
#: the artifact-level statement of what this route refuses.
STATUTORY = {"port_mf_277_20180607": 1}

REGEN = (
    "If this change is intended, run "
    "`python3 scripts/regen_goldens.py --kind=norma` and review the diff — "
    "a golden change is a behaviour change (plan §9.4)."
)

_RENDERED: dict[str, object] = {}


def render(name: str):
    """Render one sample statutorily, cached — the emitter is the slow part."""
    if name not in _RENDERED:
        path = SAMPLES_DIR / f"{name}.docx"
        model = build_model(read_docx(path), filename=path.name)
        _RENDERED[name] = render_norma(model)
    return _RENDERED[name]


def golden_files(name: str) -> list[Path]:
    """Every golden file for one sample: the primary, then each annex."""
    files = [NORMA_DIR / f"{name}.xml"]
    for ordinal in range(1, STATUTORY.get(name, 0) + 1):
        files.append(NORMA_DIR / f"{name}.anexo{ordinal}.xml")
    return files


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_golden_matches(name: str):
    """The statutory emitter still produces byte-identically what was reviewed."""
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


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_golden_is_valid(name: str):
    """Every committed golden validates on **both** shipped schemas, from disk.

    Parsed from the file rather than taken from the emitter: a golden that had
    stopped being valid would still match itself, so validity is checked
    against the artifact and not against the code that wrote it.

    The *shipped* generation, unlike the nested emitter's goldens: a `Norma`
    uses nothing the maintainers' unreleased change adds, so this route needs
    no capability probe and must be green on a bare checkout.
    """
    for path in golden_files(name):
        document = etree.parse(str(path))
        report = validate(document, "both", generation=SHIPPED)
        assert report.ok, f"{name}: {path.name} is invalid\n{report.summary()}"


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_golden_is_a_norma(name: str):
    """The primary is a `Norma`, and the annex a `DocumentoGenerico`.

    The anti-vacuity partner of `test_golden_is_valid`: a flat `generico`
    bundle would also validate on both schemas, so validity alone cannot tell
    whether the statutory emitter ran at all. `Anexo` admits `DocumentoGenerico`
    or `DocumentoArticulado` and **never** `Norma` — both schemas reject that —
    which is spec decision D-1 and mirrors the reference parser's
    `isArticulatedAnexo` being false here.
    """
    primary, *annexes = [etree.parse(str(p)).getroot() for p in golden_files(name)]

    kinds = [local_name(child.tag) for child in primary]
    assert "Norma" in kinds, f"{name}: primary is not a Norma, it is {kinds}"

    for annex in annexes:
        kinds = [local_name(child.tag) for child in annex]
        assert "Anexo" in kinds, f"{name}: annex document is not an Anexo: {kinds}"
        anexo = next(c for c in annex if local_name(c.tag) == "Anexo")
        assert [local_name(c.tag) for c in anexo] == ["DocumentoGenerico"], (
            f"{name}: an annex must be a DocumentoGenerico (D-1) — "
            f"got {[local_name(c.tag) for c in anexo]}"
        )


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_golden_norma_child_order(name: str):
    """`ParteInicial ParteFinal Anexos` — the schema's sequence, not ours.

    `HierarchicalStructure` is an `xsd:sequence`, so emitting `Anexos` before
    `ParteFinal` fails on both schemas (spec decision D-2). Asserted on the
    committed file as well as by validation, because the order is a *fact about
    the artifact* a consumer reads positionally, and a future reordering that
    happened to stay valid would still be a behaviour change.
    """
    root = etree.parse(str(golden_files(name)[0])).getroot()
    norma = next(c for c in root if local_name(c.tag) == "Norma")
    order = [local_name(child.tag) for child in norma]

    assert order == ["ParteInicial", "Articulacao", "ParteFinal", "Anexos"], (
        f"{name}: Norma children are {order}. {REGEN}"
    )


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_golden_dispositivo_ids_match_the_schema_pattern(name: str):
    """Every `Artigo`/`Caput` id satisfies `lexml09-flexivel`'s `idArtigo`.

    Not redundant with `test_golden_is_valid`, which would already catch a
    violation: this says *which* ids are dispositivo ids and pins the
    convention `art1` / `art1_cpt` the reference parser uses, so a scheme
    change that happened to stay inside the pattern is still a visible diff.
    Amendment A-6.1 — these ids cannot use Cycle 5's path-composed scheme,
    because `pp1_art1` is rejected by both schemas.
    """
    root = etree.parse(str(golden_files(name)[0])).getroot()

    found = []
    for node in root.iter():
        if local_name(node.tag) in ("Artigo", "Caput", "Paragrafo", "Inciso"):
            ident = node.get("id")
            assert ident is not None, f"{name}: {local_name(node.tag)} has no id"
            assert ARTIGO_ID_RE.match(ident), (
                f"{name}: {ident!r} is not a schema-legal dispositivo id"
            )
            found.append(ident)

    assert found == ["art1", "art1_cpt", "art2", "art2_cpt"], (
        f"{name}: dispositivo ids are {found}. {REGEN}"
    )


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_golden_ids_unique(name: str):
    """`id` uniqueness (plan invariant #5), per document and across the bundle.

    Per document because that is what `xsd:ID` requires; across the bundle
    because Cycle 6 puts **two id grammars** in one artifact — the dispositivo
    ids `art1`/`art1_cpt` and the annex's path-composed `anexo1_pp_agr1` — and
    the argument that they cannot collide deserves an assertion rather than a
    paragraph.
    """
    every: list[str] = []
    for path in golden_files(name):
        root = etree.parse(str(path)).getroot()
        ids = all_ids(root)
        duplicates = [i for i, n in Counter(ids).items() if n > 1]
        assert not duplicates, f"{name}: {path.name} repeats {duplicates}"
        every.extend(ids)

    duplicates = [i for i, n in Counter(every).items() if n > 1]
    assert not duplicates, f"{name}: ids collide across the bundle: {duplicates}"


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_annex_is_byte_identical_across_emitters(name: str):
    """The `norma` annex and the `generico` annex are the same bytes.

    Cycle 6 folded Cycle 5's `_render_annex` and Cycle 5b's copy of it into one
    `render/anexo.py` (spec decision Q-5), on the reasoning that three
    implementations of one ratified convention is the "competing source of
    truth" amendment A-3.4 refused. This is that refactor's file-level proof:
    the statutory route and the open route write the annex from the same code,
    so their committed artifacts cannot drift.
    """
    for ordinal in range(1, STATUTORY[name] + 1):
        statutory = NORMA_DIR / f"{name}.anexo{ordinal}.xml"
        generic = GENERICO_DIR / f"{name}.anexo{ordinal}.xml"
        assert statutory.read_text(encoding="utf-8") == generic.read_text(
            encoding="utf-8"
        ), (
            f"{name}: the norma and generico annex goldens differ. They are "
            "written by the same `render_anexo`, so a difference means one "
            f"emitter has grown its own copy again. {REGEN}"
        )


@pytest.mark.parametrize("name", sorted(STATUTORY))
def test_golden_conserves_the_source_text(name: str):
    """Primary + annex together carry every source word exactly once.

    Plan invariant #2, asserted **across the split** — the property that makes
    a sibling annex document safe rather than a place text goes to be lost. The
    currency is a word multiset, not a string: a source paragraph legitimately
    becomes a `Rotulo` plus the prose that followed it on the same line.

    Read from the committed files, so this pins the artifact rather than the
    emitter that produced it.
    """
    path = SAMPLES_DIR / f"{name}.docx"
    doc = read_docx(path)

    source: list[str] = []
    for block in doc.blocks:
        text = getattr(block, "text", "")
        if text and text.strip():
            source.extend(text.split())

    emitted: list[str] = []
    for golden in golden_files(name):
        emitted.extend(words(leaf_texts(etree.parse(str(golden)).getroot())))

    assert Counter(emitted) == Counter(source), (
        f"{name}: the emitted bundle does not carry the source text exactly "
        f"once. Missing: {sorted((Counter(source) - Counter(emitted)))[:8]}; "
        f"duplicated: {sorted((Counter(emitted) - Counter(source)))[:8]}"
    )


def test_only_statutory_samples_have_norma_goldens():
    """No golden exists for a sample §4.4 does not route to `norma`.

    The directory listing *is* an assertion here. Fourteen of fifteen samples
    must never be published as statutes — `parecer_93`'s 21 quoted articles are
    the corpus's standing reminder of what that would mean — so a stray file
    appearing in this directory is a routing regression that no per-sample test
    would catch, because no per-sample test would run.
    """
    expected = set()
    for name, annexes in STATUTORY.items():
        expected.add(f"{name}.xml")
        for ordinal in range(1, annexes + 1):
            expected.add(f"{name}.anexo{ordinal}.xml")

    found = {p.name for p in NORMA_DIR.glob("*.xml")}
    assert found == expected, (
        f"unexpected statutory goldens: {sorted(found - expected)}; "
        f"missing: {sorted(expected - found)}. {REGEN}"
    )


def test_emitter_name_is_recorded():
    """The bundle says which emitter produced it — `norma`, not `generico`.

    §4.2's fallback makes this load-bearing: a fallen-back document is a
    `generico` artifact, and a consumer must be able to tell the two apart
    without re-inferring the route.
    """
    for name in STATUTORY:
        assert render(name).emitter == EMITTER
