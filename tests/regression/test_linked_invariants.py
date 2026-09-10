"""Cross-cutting invariants under a linker (plan §9.2, amendments A-L.4…A-L.7).

The golden modules pin *what* the linked artifacts are. This module pins the
properties that must hold whatever they are, and it covers the three
configurations the cycle promises are all green:

**bare checkout** — no `linkertool`, nothing fails;
**fixtures only** — recorded answers, and **zero subprocess spawns**;
**binary present** — the recording reproduces (that one lives in
`tests/unit/test_refs_linkertool.py`, beside the wire protocol it checks).

The zero-spawn assertion is written the way `test_referee_api.py` asserts zero
network calls: by making the forbidden operation *raise*, rather than by
counting it afterwards. A count can be read after the damage; a raise cannot be
passed through.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.refs import (
    DEFAULT_CONTEXT_URN,
    LinkerCache,
    NullLinker,
    build_linker,
)
from lexml_nonstat.render.common import all_ids, leaf_texts
from lexml_nonstat.render.generico import render_generico
from lexml_nonstat.render.generico_aninhado import render_generico_aninhado
from lexml_nonstat.validate import validate

from tests.conftest import LINKER_FIXTURES, fixture_linker

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: A sample that resolves many references — used where one document suffices.
CITING = "parecer_93_2018_decor_cgu_agu"

_MODELS: dict[str, object] = {}


def model(name: str):
    if name not in _MODELS:
        _MODELS[name] = build_model(
            read_docx(SAMPLES_DIR / f"{name}.docx"), filename=f"{name}.docx"
        )
    return _MODELS[name]


def _chars(document: etree._Element) -> Counter:
    return Counter("".join(leaf_texts(document)))


# ---------------------------------------------------------------------------
# Conservation — invariant #2, on the character multiset (A-L.4, A-Q.6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_linking_conserves_text_exactly(name: str):
    """T-C1 — a `Remissao` adds no text and loses none, on all 15 samples.

    Characters rather than words: splitting a run at a reference boundary moves
    a *leaf boundary*, so `leaf_texts` legitimately returns a different tuple
    of strings; what may never change is the characters in them. A word-level
    comparison would have missed this cycle's own pretty-print defect, which
    added three spaces inside two `CARNE_LEAO` paragraphs.
    """
    linked = render_generico(model(name), linker=fixture_linker())
    plain = render_generico(model(name))

    for a, b in zip(linked.documents, plain.documents):
        gained = _chars(a) - _chars(b)
        lost = _chars(b) - _chars(a)
        assert not gained and not lost, (
            f"{name}: linking changed the text — gained {dict(gained)}, "
            f"lost {dict(lost)}"
        )


@pytest.mark.parametrize("name", SAMPLES)
def test_linking_conserves_text_in_the_nested_emitter(name: str):
    """T-C1 — and the same holds for `generico-aninhado`.

    Both emitters go through `render_node`, but they build their regions
    differently, and A-L.4 names the readers of *both*.
    """
    linked = render_generico_aninhado(model(name), linker=fixture_linker())
    plain = render_generico_aninhado(model(name))

    for a, b in zip(linked.documents, plain.documents):
        assert _chars(a) == _chars(b), f"{name}: nested linking changed the text"


@pytest.mark.parametrize("name", SAMPLES)
def test_linking_never_moves_an_id(name: str):
    """T-C5 — invariant #11 is untouched: a `Remissao` carries no `id`."""
    linked = render_generico(model(name), linker=fixture_linker())
    plain = render_generico(model(name))

    for a, b in zip(linked.documents, plain.documents):
        assert all_ids(a) == all_ids(b), f"{name}: linking moved an id"


@pytest.mark.parametrize("name", SAMPLES)
def test_every_linked_document_validates(name: str):
    """T-C4 — invariant #1, on both schemas, for every linked render."""
    linked = render_generico(model(name), linker=fixture_linker())

    for document in linked.documents:
        report = validate(document, "both")
        assert report.ok, f"{name}: linked render is invalid\n{report.summary()}"


# ---------------------------------------------------------------------------
# Determinism — invariant #4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_rendering_twice_is_byte_identical(name: str):
    """T-C6 — the same model and the same fixtures give the same bytes."""
    first = render_generico(model(name), linker=fixture_linker())
    second = render_generico(model(name), linker=fixture_linker())

    assert [first.to_xml_string(d) for d in first.documents] == [
        second.to_xml_string(d) for d in second.documents
    ]


def test_rendering_is_byte_identical_across_a_process_restart(tmp_path):
    """T-C6 — invariant #4 **across processes**, which is the harder half.

    A cache keyed on in-process state, or a `set` iteration order leaking into
    the output, would pass the same-process test and fail this one.
    """
    script = tmp_path / "render_once.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'src')!r})\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from lexml_nonstat.ingest import read_docx\n"
        "from lexml_nonstat.model import build_model\n"
        "from lexml_nonstat.refs import LinkerCache, build_linker\n"
        "from lexml_nonstat.render.generico import render_generico\n"
        f"m = build_model(read_docx({str(SAMPLES_DIR / f'{CITING}.docx')!r}),"
        f" filename={CITING + '.docx'!r})\n"
        f"linker = build_linker('fixtures',"
        f" cache=LinkerCache({str(LINKER_FIXTURES)!r}, read_only=True))\n"
        "b = render_generico(m, linker=linker)\n"
        "sys.stdout.write(b.to_xml_string(b.primary))\n",
        encoding="utf-8",
    )

    runs = [
        subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=True
        ).stdout
        for _ in range(2)
    ]

    assert runs[0] == runs[1]
    assert "<Remissao" in runs[0], "the subprocess must actually have linked"


# ---------------------------------------------------------------------------
# Fixtures only — zero subprocess spawns (A-L.6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_the_fixture_linker_never_spawns_a_subprocess(name: str, monkeypatch):
    """T-F2 — asserted by making a spawn *raise*, not by counting one.

    This is what lets the linked goldens be regenerated and compared on a
    checkout with no `linkertool`, and it is the structural half of A-L.6: the
    `fixtures` mode holds no binary path, so there is nothing for it to start
    even on a cache miss.
    """

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "a subprocess was spawned; the fixtures path must serve recorded "
            "answers only"
        )

    monkeypatch.setattr(subprocess, "Popen", forbidden)

    bundle = render_generico(model(name), linker=fixture_linker())
    assert bundle.documents


def test_a_fixture_run_still_resolves_references(monkeypatch):
    """The companion to the test above: zero spawns **and** real output.

    Asserting only "no subprocess" would pass for a linker that answered
    nothing at all, which is A-C.1's failure shape.
    """
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: pytest.fail("spawned a subprocess")
    )

    bundle = render_generico(model(CITING), linker=fixture_linker())
    xml = bundle.to_xml_string(bundle.primary)

    assert xml.count("<Remissao") > 50, "the fixtures carry this sample's answers"


def test_the_fixture_cache_is_never_written_to():
    """A fixture directory must not grow a file because a render asked.

    Checked as a property of the object the suite uses, so a future change that
    opened it read-write would fail here rather than by leaving untracked files
    in the working tree for someone to notice.
    """
    linker = fixture_linker()
    assert linker.cache is not None
    assert linker.cache.read_only is True
    assert linker.cache.directory == LINKER_FIXTURES


# ---------------------------------------------------------------------------
# Bare checkout — no binary, nothing fails (A-L.5, A-R.9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_a_null_linker_renders_exactly_the_delivered_output(name: str):
    """T-G1's mechanism — the default path is untouched by this cycle.

    `NullLinker` and no linker at all must be byte-identical, and both must
    equal what Cycle 5 delivered. The committed `generico` goldens are the
    other half of this claim; this is the half that does not need files.
    """
    default = render_generico(model(name))
    null = render_generico(model(name), linker=NullLinker())

    assert [default.to_xml_string(d) for d in default.documents] == [
        null.to_xml_string(d) for d in null.documents
    ]


@pytest.mark.parametrize("name", SAMPLES)
def test_a_linker_whose_binary_is_absent_degrades_silently(name: str):
    """A-L.5 — an unavailable linker renders, it does not raise.

    Deliberately a `LinkertoolLinker` pointed at nothing rather than a
    `NullLinker`: the fail-safe being tested is the *real* backend's, which is
    the one a user on a bare checkout would hold with `--linker=auto`.
    """
    from lexml_nonstat.refs import LinkertoolLinker

    absent = LinkertoolLinker("/nonexistent/linkertool")
    bundle = render_generico(model(name), linker=absent)

    assert absent.spawns == 0
    assert "<Remissao" not in bundle.to_xml_string(bundle.primary)
    assert validate(bundle.primary, "both").ok


def test_a_linker_that_raises_does_not_break_a_render():
    """The protocol forbids raising; a render must survive it anyway.

    Availability over quality — the referee's rule, and the reason a citation
    is never worth a failed document.
    """

    class _Broken:
        name = "broken"
        enabled = True

        def find_refs(self, text, context_urn=DEFAULT_CONTEXT_URN):
            raise RuntimeError("backend exploded")

    bundle = render_generico(model(CITING), linker=_Broken())

    assert "<Remissao" not in bundle.to_xml_string(bundle.primary)
    assert validate(bundle.primary, "both").ok


def test_a_linker_returning_nonsense_cannot_corrupt_a_document():
    """Spans that do not match the text are dropped, so the artifact is safe.

    The backend verifies its own spans, but a *different* `Linker`
    implementation — the protocol is public — might not. The renderer is the
    last line, and it must hold on its own.
    """
    from lexml_nonstat.refs import Reference

    class _Liar:
        name = "liar"
        enabled = True

        def find_refs(self, text, context_urn=DEFAULT_CONTEXT_URN):
            return (
                Reference(0, 10_000, "urn:lex:br:federal:lei:2000-01-01;1", "?"),
                Reference(-5, 3, "urn:lex:br:federal:lei:2000-01-01;1", "?"),
                Reference(2, 1, "", ""),
            )

    lying = render_generico(model(CITING), linker=_Liar())
    plain = render_generico(model(CITING))

    assert lying.to_xml_string(lying.primary) == plain.to_xml_string(plain.primary)


# ---------------------------------------------------------------------------
# The context URN — A-L.9
# ---------------------------------------------------------------------------


def test_the_emitters_ask_with_the_documented_context():
    """A-L.9 — the corpus's own URNs resolve nothing, so the constant is used.

    Recorded as a test because the failure it prevents is **silent**: passing a
    document's own URN would leave every paragraph unlinked while every test
    that only checks "a linker was configured" kept passing.
    """
    seen: list[str] = []

    class _Recording:
        name = "recording"
        enabled = True

        def find_refs(self, text, context_urn=DEFAULT_CONTEXT_URN):
            seen.append(context_urn)
            return ()

    render_generico(model(CITING), linker=_Recording())

    assert seen, "the emitter asked nothing at all"
    assert set(seen) == {DEFAULT_CONTEXT_URN}


def test_front_and_back_matter_are_linked_too():
    """45 % of the corpus's references live outside the body (measured).

    Two samples — `ad_srf_22` and `adn_cosit_19` — are *nothing but* front and
    back matter, and an ato declaratório's ementa citing the Lei it construes
    is exactly the citation a reader wants. A body-only linker resolved 210 of
    379; threading the regions reaches all of them.
    """
    for name in ("ad_srf_22_19970430", "adn_cosit_19_20001025"):
        bundle = render_generico(model(name), linker=fixture_linker())
        assert "<Remissao" in bundle.to_xml_string(bundle.primary), (
            f"{name} is pure front/back matter and cites statutes; if it "
            "resolves nothing, the region path stopped being linked"
        )


def test_a_read_write_cache_records_what_was_asked(tmp_path):
    """The recorder's own mechanism, without the binary.

    `build_linker` with a writable cache must persist answers, or
    `record_linker_fixtures.py` would silently record nothing.
    """
    from lexml_nonstat.refs import Reference, cache_key

    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "A Lei nº 7.713 dispõe.")
    cache.put(key, (Reference(2, 14, "urn:lex:br:federal:lei:1988;7713", "Lei nº 7.713"),))

    served = build_linker("fixtures", cache=LinkerCache(tmp_path, read_only=True))
    assert served.find_refs("A Lei nº 7.713 dispõe.")[0].urn == (
        "urn:lex:br:federal:lei:1988;7713"
    )
