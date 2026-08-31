"""Cross-cutting invariants with a prose header in the tree — amendment A-H.

Amendment A-H.4 deepens `par_cosit_26` by a level and moves every body `id` in
both emitters. That is a large change to make on the strength of a model's
answer, so the invariants it could plausibly break are re-asserted here against
the *refereed* pipeline rather than only against the default one:

* **#2 conservation** — the header's text moves to `NomeAgrupador`; it must not
  also stay a `<p>` (A-H.5), and nothing else may be lost or duplicated;
* **#6 id uniqueness** and **Rule A** — a deeper tree is more id path, and a
  gap in the path is the failure Rule A exists to catch;
* **#11 cross-emitter equivalence** — a serialisation choice must not change
  what the document says, with the new level present;
* **the fixtures themselves** — 31 recorded answers, pinned, so a future prompt
  edit that reintroduces the pre-A-H.2 typographic behaviour fails here rather
  than silently reshaping documents.

Conservation is compared as a **character multiset**, following A-Q.6: moving a
paragraph's text into a heading moves a leaf boundary, so a leaf- or word-level
comparison cannot tell a legitimate move from real damage.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.referee import CachedAPIReferee, RefereeCache
from lexml_nonstat.referee.api import DEFAULT_MODEL
from lexml_nonstat.referee.cache import cache_key
from lexml_nonstat.render import render_generico, render_generico_aninhado
from lexml_nonstat.render.common import all_ids, leaf_texts
from lexml_nonstat.render.ids import missing_prefixes

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"
FIXTURES = REPO_ROOT / "tests" / "referee_fixtures"

SAMPLES: tuple[str, ...] = tuple(sorted(p.stem for p in SAMPLES_DIR.glob("*.docx")))

#: The samples A-H.1 actually changes. Named so the tests below can say which
#: claim they carry on which document, instead of asserting a corpus-wide
#: average that would hide a regression in the one document that moved most.
CHANGED_BY_A_H: tuple[str, ...] = ("par_cosit_26_20000629", "sumula_stj_125")


def explodes(*args, **kwargs):
    raise AssertionError("the transport was called; this path must make no network calls")


def fixture_referee() -> CachedAPIReferee:
    return CachedAPIReferee(
        cache=RefereeCache(FIXTURES, read_only=True),
        api_key="test-key-not-a-secret",
        transport=explodes,
    )


_MODELS: dict[tuple[str, bool], object] = {}


def model(name: str, *, refereed: bool):
    key = (name, refereed)
    if key not in _MODELS:
        doc = read_docx(SAMPLES_DIR / f"{name}.docx")
        _MODELS[key] = build_model(doc, referee=fixture_referee() if refereed else None)
    return _MODELS[key]


def chars(elements) -> Counter:
    """Every non-space character the artifact carries, as a multiset (A-Q.6)."""
    counter: Counter = Counter()
    for element in elements:
        for text in leaf_texts(element):
            counter.update(c for c in text if not c.isspace())
    return counter


def bundle(rendered) -> tuple:
    return (rendered.primary,) + tuple(rendered.annexes)


# ---------------------------------------------------------------------------
# T-8d.9 — invariant #2, conservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
@pytest.mark.parametrize("render", [render_generico, render_generico_aninhado])
def test_conservation_survives_the_referee(name: str, render):
    """T-8d.9. Referee on vs. off, same characters, ×15, both emitters.

    The comparison that catches A-H.5 going wrong: promoting a header's text to
    `NomeAgrupador` *and* leaving the paragraph behind would show up here as a
    duplicated run of characters, and dropping the paragraph without promoting
    it would show up as a missing one. No schema can detect either (the A-6.3
    lesson), so this is the only place it is caught.
    """
    plain = chars(bundle(render(model(name, refereed=False))))
    refereed = chars(bundle(render(model(name, refereed=True))))
    assert refereed == plain


def test_the_promoted_header_text_is_moved_not_copied():
    """T-8d.9 / A-H.5. A promoted heading appears once, not twice.

    Asserted on the rendered XML rather than on the tree, because the tree
    could be right and the emitter still write the text twice — precisely the
    defect A-6.4 found in the statutory route.

    `par_cosit_26` only. `sumula_stj_125` legitimately carries seven
    `RELATÓRIO`s — one per case — so a global count of the *word* proves
    nothing there; its equivalent guarantee is the conservation test above,
    which compares before and after rather than counting occurrences.
    """
    refereed = model("par_cosit_26_20000629", refereed=True)
    plain = model("par_cosit_26_20000629", refereed=False)
    for render in (render_generico, render_generico_aninhado):
        after: Counter = Counter()
        for element in bundle(render(refereed)):
            after.update(t.strip() for t in leaf_texts(element) if t.strip())
        before: Counter = Counter()
        for element in bundle(render(plain)):
            before.update(t.strip() for t in leaf_texts(element) if t.strip())
        for heading in ("RELATÓRIO", "CONCLUSÃO", "FUNDAMENTOS LEGAIS", "ORDEM DE INTIMAÇÃO"):
            assert after[heading] == before[heading] == 1, (
                f"{heading}: {before[heading]} → {after[heading]}"
            )


# ---------------------------------------------------------------------------
# T-8d.15 — invariant #6 and Rule A, with a deeper tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
@pytest.mark.parametrize("render", [render_generico, render_generico_aninhado])
def test_ids_stay_unique_and_gapless(name: str, render):
    """T-8d.15. A deeper tree is more id path; Rule A is what proves it whole."""
    ns = {"lex": "http://www.lexml.gov.br/1.0"}
    every: list[str] = []
    for element in bundle(render(model(name, refereed=True))):
        every.extend(all_ids(element))
        parte = element.find(".//lex:PartePrincipal", ns)
        if parte is None:
            continue
        root = parte.get("id") or "pp1"
        ids = [value for node in parte.iter() if (value := node.get("id")) is not None]
        assert missing_prefixes(ids, root=root) == (), (
            f"{name}: Rule A — an intermediate level is missing"
        )
    assert len(every) == len(set(every)), "an id was issued twice"


# ---------------------------------------------------------------------------
# T-8d.11 — invariant #11, cross-emitter equivalence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_both_emitters_still_say_the_same_thing(name: str):
    """T-8d.11. A-Q.6's character-multiset comparison, with a prose header in.

    The new level is exactly the kind of change that could make one emitter
    drop a wrapper the other keeps, so invariant #11 is re-measured rather than
    assumed to survive.
    """
    refereed = model(name, refereed=True)
    assert chars(bundle(render_generico_aninhado(refereed))) == chars(
        bundle(render_generico(refereed))
    )


def test_par_cosit_26_gains_the_same_level_in_both_emitters():
    """T-8d.11. The reported fix, asserted on both artifacts.

    `CONCLUSÃO` must be a top-level grouping in each, holding item `19.` — the
    flat emitter saying so through its id path and `Bloco nome="nomeAgrupador"`,
    the nested one through real containment and `<NomeAgrupador>`.
    """
    refereed = model("par_cosit_26_20000629", refereed=True)

    flat = render_generico(refereed).primary
    nested = render_generico_aninhado(refereed).primary

    ns = {"lex": "http://www.lexml.gov.br/1.0"}

    flat_names = [
        b.text
        for b in flat.iterfind(".//lex:Agrupamento/lex:Bloco", ns)
        if b.get("nome") == "nomeAgrupador"
    ]
    assert "CONCLUSÃO" in flat_names and "RELATÓRIO" in flat_names

    nested_names = [
        e.text for e in nested.iterfind(".//lex:AgrupamentoHierarquico/lex:NomeAgrupador", ns)
    ]
    assert "CONCLUSÃO" in nested_names and "RELATÓRIO" in nested_names

    # And the containment the report asked for: `19.` inside `CONCLUSÃO`.
    for group in nested.iterfind(".//lex:AgrupamentoHierarquico", ns):
        name = group.find("lex:NomeAgrupador", ns)
        if name is not None and name.text == "CONCLUSÃO":
            rotulos = [r.text for r in group.iterfind("lex:AgrupamentoHierarquico/lex:Rotulo", ns)]
            assert rotulos == ["19."]
            break
    else:  # pragma: no cover - the assertion above would have fired first
        pytest.fail("CONCLUSÃO is not an AgrupamentoHierarquico in the nested output")


# ---------------------------------------------------------------------------
# T-8d.12 / T-8d.13 — the fixtures and the cache key
# ---------------------------------------------------------------------------


def heading_fixtures() -> list[dict]:
    out = []
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("meta", {}).get("kind") == "heading":
            data["_path"] = path
            out.append(data)
    return out


def test_there_are_exactly_thirty_one_heading_fixtures():
    """T-8d.12. One per candidate the generator proposes, and no more.

    A surplus fixture is an answer to a question nobody asks — dead weight that
    hides a narrowed generator. A missing one becomes a live network call on
    the next run, which §9.3 forbids outright.
    """
    assert len(heading_fixtures()) == 31


def test_exactly_six_heading_fixtures_confirm():
    """T-8d.12. The prompt-regression alarm.

    The pre-A-H.2 prompt answered "heading" to 15 of `par_cosit_26`'s 17
    upper-case paragraphs, including every folio stamp. If a future edit
    reintroduces that behaviour — or a fixture refresh records a model that
    behaves that way — this count moves and the test fails, before any document
    is reshaped.
    """
    verdicts = Counter(f["verdict"]["verdict"] for f in heading_fixtures())
    assert verdicts == {"nao": 25, "secao": 6}


@pytest.mark.parametrize(
    "text",
    ["Fl. 7 DF COSIT RFB", "MINISTÉRIO DA FAZENDA", "DOMICÍLIO FISCAL", "DJ 22.08.1994"],
)
def test_the_known_traps_are_refused(text: str):
    """T-8d.12. Named individually, because each is a distinct failure class.

    A page artifact, a letterhead line, a form-field label and a publication
    date. Every one of them is set exactly like a heading, and every one of them
    was called a heading at ≥0.70 by the prompt this amendment replaced.
    """
    for fixture in heading_fixtures():
        if fixture["meta"]["excerpt"].strip() == text:
            assert fixture["verdict"]["verdict"] == "nao", text
            return
    pytest.fail(f"no heading fixture for {text!r}")


def test_every_heading_fixture_is_reachable():
    """T-8d.12. Each file's key must be the key the pipeline actually computes.

    Derived by replay from the fixture's own recorded excerpt and contexts — the
    A-C.4 method. A fixture whose filename does not match its content is a
    silent cache miss, and a silent cache miss is a live call.
    """
    for fixture in heading_fixtures():
        meta = fixture["meta"]
        expected = cache_key(
            DEFAULT_MODEL,
            "heading",
            meta["excerpt"],
            meta.get("ctx", ""),
            meta.get("next_ctx", ""),
        )
        assert fixture["_path"].stem == expected, meta["locator"]


def test_cache_key_unchanged_without_next_ctx():
    """T-8d.13. The seven pre-A-H.2 fixtures must not move.

    `next_ctx` joins the key only when it is non-empty, so every question asked
    before this amendment hashes exactly as it did. Asserted against the
    literal pre-amendment construction rather than against a stored constant,
    so the property is checked rather than remembered.
    """
    import hashlib

    def pre_amendment(model: str, kind: str, excerpt: str, ctx: str = "") -> str:
        payload = "\x1f".join((model, kind, excerpt, ctx)).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]

    for kind in ("own_articulation", "quotation_boundary", "heading"):
        assert cache_key(DEFAULT_MODEL, kind, "Art. 2º", "antecedente") == pre_amendment(
            DEFAULT_MODEL, kind, "Art. 2º", "antecedente"
        )

    # …and a non-empty `next_ctx` must genuinely change it, or it would not be
    # in the key at all.
    assert cache_key(DEFAULT_MODEL, "heading", "CONCLUSÃO", "a", "b") != cache_key(
        DEFAULT_MODEL, "heading", "CONCLUSÃO", "a"
    )


def test_no_heading_fixture_answers_in_the_old_vocabulary():
    """T-8d.14. A stale recorded answer must not survive the rename.

    `adjudicate` would abstain on one anyway, but an abstention is a quiet
    degradation: the document silently loses a section it should have. Better
    to fail here.
    """
    for fixture in heading_fixtures():
        assert fixture["verdict"]["verdict"] in ("secao", "nao"), fixture["meta"]["locator"]
