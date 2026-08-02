"""Profiles: genre selection is correct, deterministic and decided by a margin.

The cycle's headline exit criterion is *"profile auto-selection correct for all
15 samples"* (spec §6 row 2), and :func:`test_profile_autoselect_all_samples`
is that criterion, one case per sample.

Three things beyond bare correctness are guarded here, because a selector that
returns the right answer for the wrong reason will not survive the 300+ document
corpus the plan is aiming at:

1. **The win is by a margin, not by a coin toss.** ``score_profiles`` breaks
   ties by registration order, so a document whose top two profiles score
   *equally* would be assigned by a list literal in ``registry.py`` rather than
   by evidence — and would silently flip the day a profile is reordered.
   :func:`test_winning_margin` requires strict inequality, so that failure mode
   is loud.
2. **Selection is deterministic** (plan invariant #4) — :func:`test_selection_is_deterministic`.
3. **The false positive the cycle exists to prevent stays prevented.**
   ``Relator:``, ``Advogados:`` and ``Recorrente:`` are acórdão *body*
   structure, not document metadata; spec §2.1 decision #4 rules them out and
   :func:`test_matches_label` pins that.

Samples are loaded from Cycle 1's committed JSON goldens rather than re-read
from ``.docx``. Selection consumes only ``StyledDoc``, the goldens are asserted
byte-equal to ``read_docx`` output by ``tests/golden/test_styled_goldens.py``,
and this way the file runs in milliseconds without a Word parse — a failure
here is always a profile bug, never an ingestion one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexml_nonstat.ingest import Inline, StyledDoc, StyledPara
from lexml_nonstat.profile import (
    ATO_DECLARATORIO,
    GENERIC,
    JURISPRUDENCIA_GENERICO,
    PARECER,
    PORTARIA,
    SERVICO,
    DocumentProfile,
    UnknownProfileError,
    all_profiles,
    fold,
    get_profile,
    head_texts,
    register,
    score_profiles,
    select_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "styled"

#: Spec §3.3's profile table, as data. Sample stem → expected profile name.
#: This is the cycle's ground truth; changing an entry changes what the cycle
#: claims to do, so it belongs in review, not in a fixup commit.
EXPECTED_PROFILE: dict[str, str] = {
    # parecer — legal opinions, including the Parecer Normativo (decision #5).
    "parecer_93_2018_decor_cgu_agu": "parecer",
    "par_cosit_26_20000629": "parecer",
    "pn_cst_38_19801031": "parecer",
    # ato_declaratorio — declaratory acts, normative or not.
    "ad_srf_3_19990107": "ato_declaratorio",
    "ad_srf_22_19970430": "ato_declaratorio",
    "ad_pgfn_3_20080918": "ato_declaratorio",
    "ad_pgfn_13_20111220": "ato_declaratorio",
    "adn_cosit_19_20001025": "ato_declaratorio",
    "adn_cst_10_19910417": "ato_declaratorio",
    # portaria — one articulated, one item-based (plan §2.7).
    "port_mf_277_20180607": "portaria",
    "port_mf_454_19770825": "portaria",
    # jurisprudencia_generico — two súmulas and a bare acórdão.
    "sumula_carf_42": "jurisprudencia_generico",
    "sumula_stj_125": "jurisprudencia_generico",
    "REsp_1306393": "jurisprudencia_generico",
    # servico — the taxpayer-facing page, the corpus' odd one out.
    "sistema_de_recolhimento_mensal_obrigatorio_CARNE_LEAO": "servico",
}

#: Sorted so ids read predictably and a parametrisation over an empty glob
#: cannot masquerade as a pass.
SAMPLE_STEMS = sorted(EXPECTED_PROFILE)

#: The registry's contents per spec §2.1 decision #5, in registration order.
#: ``generic`` is last because it is the floor: it wins only unopposed.
EXPECTED_REGISTRY = (
    "parecer",
    "ato_declaratorio",
    "portaria",
    "jurisprudencia_generico",
    "servico",
    "generic",
)


# --------------------------------------------------------------------------
# Sample loading
# --------------------------------------------------------------------------

_DOC_CACHE: dict[str, StyledDoc] = {}


def load_sample(stem: str) -> StyledDoc:
    """A Cycle-1 golden, deserialised once per session."""
    if stem not in _DOC_CACHE:
        path = GOLDEN_DIR / f"{stem}.json"
        _DOC_CACHE[stem] = StyledDoc.from_json(path.read_text(encoding="utf-8"))
    return _DOC_CACHE[stem]


def para(text: str, index: int) -> StyledPara:
    """A plain, unstyled paragraph — the building block for synthetic docs."""
    return StyledPara(inlines=(Inline(text=text),), index=index)


def test_ground_truth_covers_every_sample():
    """Guards the guard.

    Every assertion below is parametrised over :data:`EXPECTED_PROFILE`. If a
    sample were dropped from the corpus, or a golden went missing, the
    parametrisation would shrink and the suite would report fewer passes rather
    than a failure. Anchoring to the golden directory makes that impossible.
    """
    goldens = {p.stem for p in GOLDEN_DIR.glob("*.json")}

    assert len(SAMPLE_STEMS) == 15
    assert set(SAMPLE_STEMS) == goldens, (
        f"ground truth without a golden: {sorted(set(SAMPLE_STEMS) - goldens)}; "
        f"goldens without ground truth: {sorted(goldens - set(SAMPLE_STEMS))}"
    )


# --------------------------------------------------------------------------
# 1. Auto-selection — the cycle's exit criterion
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_profile_autoselect_all_samples(stem: str):
    """Spec §6 row 2: the right genre for every sample, chosen unaided.

    The failure message carries the full score table, because "expected
    parecer, got generic" says nothing about *why* — whereas seeing that every
    profile scored its floor immediately localises the bug to the epigraph
    patterns rather than to the scoring arithmetic.
    """
    doc = load_sample(stem)
    chosen = select_profile(doc)
    expected = EXPECTED_PROFILE[stem]

    assert chosen.name == expected, (
        f"{stem}: expected profile {expected!r}, got {chosen.name!r}.\n"
        "  scores: "
        + ", ".join(f"{p.name}={s:.2f}" for p, s in score_profiles(doc))
    )


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_winning_margin(stem: str):
    """The winner beats the runner-up *strictly* — no silent tie-breaks.

    ``score_profiles`` sorts by ``(-score, registration_index)``, so equal
    scores are resolved by the order of the loop at the bottom of
    ``registry.py``. That is deterministic, which invariant #4 requires, but it
    is not *evidence*: a document sitting on a tie is one whose genre was
    decided by a list literal, and it would flip the day someone reorders that
    list for unrelated reasons.

    Verified empirically across all 15 before being asserted: the smallest
    observed margin is ``port_mf_277`` at 0.300 (portaria 0.950 vs
    jurisprudencia_generico 0.650 — its ANEXO ÚNICO quotes acórdão-shaped
    headings). Every sample clears strict inequality, so ``>`` is asserted
    rather than ``>=``; if a future profile addition compresses a margin to
    zero, this test is where that surfaces.
    """
    scored = score_profiles(load_sample(stem))
    (winner, top), (runner_up, second) = scored[0], scored[1]

    assert top > second, (
        f"{stem}: {winner.name!r} and {runner_up.name!r} both score {top:.3f} — "
        "the genre is being decided by registration order, not by evidence.\n"
        "  scores: " + ", ".join(f"{p.name}={s:.2f}" for p, s in scored)
    )


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_selection_is_deterministic(stem: str):
    """Plan invariant #4, on both the winner and the whole ranking.

    Asserting only that the *winner* repeats would miss instability further
    down the table, which Cycle 4b's telemetry reads (it wants the runner-up).
    So the full ``(name, score)`` sequence is compared, and it must be
    identical — same order, same values, including ties.
    """
    doc = load_sample(stem)

    assert select_profile(doc) is select_profile(doc)

    def ranking() -> tuple[tuple[str, float], ...]:
        return tuple((p.name, s) for p, s in score_profiles(doc))

    first, second, third = ranking(), ranking(), ranking()
    assert first == second == third, (
        f"{stem}: score_profiles is not stable across calls: {first} vs {second}"
    )


# --------------------------------------------------------------------------
# 2. Registry integrity
# --------------------------------------------------------------------------


def test_registry_contains_expected_profiles():
    """Exactly the 6 profiles of decision #5 — no more, no fewer.

    The ``nota_tecnica`` assertion is the interesting half. The plan's §3
    layout names it, so its absence looks like an omission unless it is pinned
    as deliberate: there is no ``nota_tecnica`` sample in the corpus, and a
    profile with no sample is untested speculation whose regexes nothing
    contradicts. If a sample ever arrives, this test fails and forces the
    decision to be re-taken rather than silently inherited.
    """
    names = tuple(p.name for p in all_profiles())

    assert names == EXPECTED_REGISTRY, (
        f"registry contents changed: expected {EXPECTED_REGISTRY}, got {names}"
    )
    # Registration order is the documented tie-break order, and `generic` must
    # be last for the floor to behave as a floor.
    assert names[-1] == "generic"

    for name in EXPECTED_REGISTRY:
        assert get_profile(name).name == name

    # The constants exported from the package are the registered objects
    # themselves, not copies — so `select_profile(doc) is PARECER` is meaningful.
    for constant in (
        PARECER,
        ATO_DECLARATORIO,
        PORTARIA,
        JURISPRUDENCIA_GENERICO,
        SERVICO,
        GENERIC,
    ):
        assert get_profile(constant.name) is constant

    assert "nota_tecnica" not in names, (
        "nota_tecnica is deliberately not built (spec §2.1 decision #5): no "
        "sample exists, so its patterns would be untested speculation"
    )
    with pytest.raises(UnknownProfileError):
        get_profile("nota_tecnica")


def test_get_profile_error_names_the_alternatives():
    """An unknown name reports what *is* known.

    ``UnknownProfileError`` subclasses ``KeyError``, whose ``str()`` re-quotes
    its argument; the message is asserted through ``.args`` so the test reads
    the text the code wrote rather than ``repr``'s decoration.
    """
    with pytest.raises(UnknownProfileError) as excinfo:
        get_profile("no_such_profile")

    message = excinfo.value.args[0]
    assert "no_such_profile" in message
    assert "parecer" in message and "generic" in message


# --------------------------------------------------------------------------
# 3. The floor
# --------------------------------------------------------------------------


def test_generic_is_the_floor():
    """Prose with no epigraph and no known opener lands on ``generic``.

    Built synthetically rather than from a sample precisely because no sample
    has this shape — all 15 are classifiable, so the fallback path is otherwise
    unexercised. The text is deliberately inert: ordinary Portuguese sentences
    naming no genre, no authority and no document type.
    """
    doc = StyledDoc(
        blocks=(
            para("Este documento nao possui epigrafe nem preambulo.", 0),
            para("Trata-se de um texto corrido, sem qualquer marca de genero.", 1),
            para("Nao ha numero, data, tipo nem autoridade a identificar.", 2),
        ),
        source="synthetic.docx",
    )

    assert select_profile(doc) is GENERIC

    scored = dict((p.name, s) for p, s in score_profiles(doc))
    assert scored["generic"] == pytest.approx(GENERIC.base_score)
    # The floor is a floor only while nothing else reaches it.
    assert all(
        score < scored["generic"]
        for name, score in scored.items()
        if name != "generic"
    ), f"a specific profile claimed pure prose: {scored}"


def test_generic_wins_an_empty_document():
    """A document with no paragraphs at all still selects, and never raises.

    ``score`` short-circuits to ``base_score`` when there is no head text, so
    every profile ties at its floor — of which only ``generic``'s is non-zero.
    """
    assert select_profile(StyledDoc(blocks=())) is GENERIC


# --------------------------------------------------------------------------
# 4. Label matching — the false positive this cycle exists to prevent
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    ["NUP", "nup", "ASSUNTO", "assunto", "Cod. Ement.", "cod. ement", "EMENTA"],
)
def test_matches_label_parecer_accepts(label: str):
    """The allowlist is case-, accent- and trailing-dot-insensitive.

    Comparison runs both sides through :func:`fold`, so ``INTERESSADOS`` and
    ``Interessados`` are one entry, and a trailing ``.`` is stripped so the
    label ``Cod. Ement.`` matches whether or not the document's copy ends in a
    period.
    """
    assert PARECER.matches_label(label) is True


@pytest.mark.parametrize("label", ["Advogados", "Relator", "Recorrente", "Some-se"])
def test_matches_label_parecer_rejects(label: str):
    """Prose that merely *looks* labelled is not metadata.

    These are the strings spec §2.1 decision #4 was written about: they appear
    as ``LABEL:`` in the corpus and would be captured by a naive rule.
    """
    assert PARECER.matches_label(label) is False


def test_matches_label_folding_is_accent_insensitive():
    """``JURISPRUDÊNCIA`` and ``JURISPRUDENCIA`` are the same label.

    ``ato_declaratorio`` carries both spellings explicitly, so this proves the
    *folding*, not the redundancy: an entry listed only with its accent still
    matches an unaccented occurrence, and vice versa.
    """
    assert ATO_DECLARATORIO.matches_label("JURISPRUDÊNCIA") is True
    assert ATO_DECLARATORIO.matches_label("JURISPRUDENCIA") is True
    assert ATO_DECLARATORIO.matches_label("jurisprudencia") is True
    # Listed with an accent only, matched without one.
    assert JURISPRUDENCIA_GENERICO.matches_label("Referencia") is True
    assert JURISPRUDENCIA_GENERICO.matches_label("REFERÊNCIA") is True


def test_matches_label_is_punctuation_literal_inside_the_label():
    """Folding normalises case and accents — not interior punctuation.

    ``matches_label("Cod Ement")`` is **False**: only a *trailing* dot is
    stripped, so the interior dot in ``Cod.`` must be present. This is asserted
    rather than treated as a gap because it is the extractor's actual contract —
    ``metadata.py`` queries the canonical spelling ``"Cod. Ement."`` when its
    dedicated no-colon pattern fires (spec §3.4), so the dot-less form never
    reaches this method in production. Pinning it means a future decision to
    fold punctuation too is a visible change, not an accident.
    """
    assert PARECER.matches_label("Cod. Ement.") is True
    assert PARECER.matches_label("Cod. Ement") is True  # trailing dot optional
    assert PARECER.matches_label("Cod Ement") is False  # interior dot required


@pytest.mark.parametrize("label", ["Relator", "Advogados", "Recorrente"])
def test_matches_label_jurisprudencia_rejects_acordao_body(label: str):
    """The regression this cycle exists to prevent (spec §6 row 6).

    ``sumula_stj_125`` contains ``Advogados:`` seven times, plus ``Relator:``
    and ``Recorrente:``. Those lines are the *structure of the acórdão being
    quoted* — parties and counsel of the underlying case — not metadata about
    the súmula. Capturing them would put litigants' names into
    ``<MetadadoProprietario>``, which is silent corruption rather than a merely
    noisy result: a missed field leaves its text in the body, recoverable; an
    invented field does not announce itself.
    """
    assert JURISPRUDENCIA_GENERICO.matches_label(label) is False


def test_jurisprudencia_keeps_its_genuine_labels():
    """Rejecting body structure must not mean capturing nothing.

    Paired with the test above so the allowlist cannot be trivially satisfied
    by emptying it — ``Referência:`` and ``Precedentes:`` are genuine
    document-level metadata on ``sumula_stj_125`` and must survive.
    """
    assert JURISPRUDENCIA_GENERICO.matches_label("Referência") is True
    assert JURISPRUDENCIA_GENERICO.matches_label("Precedentes") is True


def test_servico_matches_no_labels():
    """``servico`` has an empty allowlist, so nothing is metadata.

    The CARNE_LEAO page is a web document with no front matter at all; plan §8
    demands "no false positives" from it, and the strongest way to get that is
    to have nothing to match.
    """
    assert SERVICO.field_labels == frozenset()
    for label in ("ASSUNTO", "EMENTA", "NUP", "Referência"):
        assert SERVICO.matches_label(label) is False


# --------------------------------------------------------------------------
# 5. Registration
# --------------------------------------------------------------------------


@pytest.fixture
def pristine_registry():
    """Restores the registry after a test mutates it.

    ``_REGISTRY`` is module-level global state shared by the whole session, so
    a leaked ``replace=True`` from this file would change what
    ``test_metadata.py`` and the goldens see — a cross-file failure with no
    visible cause. The snapshot is taken and reinstated in place, so identity
    (``get_profile("parecer") is PARECER``) survives too.
    """
    from lexml_nonstat.profile import registry as registry_module

    snapshot = dict(registry_module._REGISTRY)
    try:
        yield
    finally:
        registry_module._REGISTRY.clear()
        registry_module._REGISTRY.update(snapshot)


def test_register_rejects_duplicate(pristine_registry):
    """A duplicate name is refused unless shadowing is asked for explicitly.

    Silent replacement is the dangerous default here: two modules registering
    ``parecer`` would leave the winner decided by import order, and the loser's
    patterns would vanish without a word.
    """
    with pytest.raises(ValueError, match="already registered"):
        register(PARECER)

    # The failed registration changed nothing.
    assert get_profile("parecer") is PARECER
    assert tuple(p.name for p in all_profiles()) == EXPECTED_REGISTRY

    # Opting in works, and returns the profile for chaining.
    assert register(PARECER, replace=True) is PARECER
    assert get_profile("parecer") is PARECER

    replacement = DocumentProfile(name="parecer", urn_type="parecer.substituto")
    register(replacement, replace=True)
    assert get_profile("parecer") is replacement
    # Replacing keeps the slot's position, so the tie-break order is unchanged.
    assert tuple(p.name for p in all_profiles()) == EXPECTED_REGISTRY


def test_register_new_profile_appends_at_the_end(pristine_registry):
    """A newly registered profile joins last, and is retrievable.

    Registration order is the tie-break order, so where a new profile lands is
    behaviour, not bookkeeping: appending means it can never displace an
    incumbent on a tie.
    """
    extra = DocumentProfile(name="nota_tecnica", urn_type="nota.tecnica")
    register(extra)

    assert get_profile("nota_tecnica") is extra
    assert tuple(p.name for p in all_profiles()) == EXPECTED_REGISTRY + (
        "nota_tecnica",
    )


def test_registry_state_is_restored_after_mutation():
    """The fixture's own guarantee, asserted rather than assumed.

    This test carries no ``pristine_registry`` on purpose: it runs after the
    two that do and re-checks the global. Without it, a bug in the fixture
    would surface as an unrelated failure in another file.
    """
    assert tuple(p.name for p in all_profiles()) == EXPECTED_REGISTRY
    assert get_profile("parecer") is PARECER
    with pytest.raises(UnknownProfileError):
        get_profile("nota_tecnica")


# --------------------------------------------------------------------------
# 6. Helpers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MINISTÉRIO DA FAZENDA", "ministerio da fazenda"),
        ("JURISPRUDÊNCIA", "jurisprudencia"),
        ("Referência", "referencia"),
        ("SÚMULA", "sumula"),
        ("Carnê-Leão", "carne-leao"),
        ("PARECER", "parecer"),
        ("já", "ja"),
        ("", ""),
        # Punctuation and digits pass through untouched — folding is about
        # case and accents only.
        ("Cod. Ement.34", "cod. ement.34"),
    ],
)
def test_fold(raw: str, expected: str):
    """NFKD decomposition, combining marks dropped, then lowercased.

    Every profile regex is written against folded text, so this function is
    what lets a single pattern match ``EMENTA``, ``Ementa`` and ``ementa`` — and
    what lets ``JURISPRUDÊNCIA`` match a pattern that carries no accent.
    """
    assert fold(raw) == expected


def test_fold_is_idempotent():
    """Folding folded text changes nothing.

    Matters because both sides of ``matches_label`` are folded, and a
    non-idempotent transform there would make the comparison depend on how many
    times each side had been through it.
    """
    for raw in ("MINISTÉRIO DA FAZENDA", "Referência", "Cod. Ement."):
        assert fold(fold(raw)) == fold(raw)


def test_head_texts_skips_empties_and_strips():
    """Empty paragraphs are not head text, and surviving text is edge-stripped.

    Spacer paragraphs are pervasive in these documents; counting them toward
    the 30-paragraph window would let a document with a decorative gap push its
    own epigraph out of scoring range.
    """
    doc = StyledDoc(
        blocks=(
            para("", 0),
            para("   ", 1),
            para("  PORTARIA MF Nº 277  ", 2),
            para("", 3),
            para("O MINISTRO DE ESTADO DA FAZENDA", 4),
        ),
        source="synthetic.docx",
    )

    assert head_texts(doc) == ["PORTARIA MF Nº 277", "O MINISTRO DE ESTADO DA FAZENDA"]


def test_head_texts_respects_its_limit():
    """The window is a hard cap, and counts non-empty paragraphs only.

    Interleaving empties proves the two behaviours compose: with ``limit=3``,
    three *texts* come back, not the first three *blocks*.
    """
    blocks = []
    index = 0
    for n in range(10):
        blocks.append(para("", index))
        index += 1
        blocks.append(para(f"linha {n}", index))
        index += 1
    doc = StyledDoc(blocks=tuple(blocks), source="synthetic.docx")

    assert head_texts(doc, limit=3) == ["linha 0", "linha 1", "linha 2"]
    assert head_texts(doc, limit=1) == ["linha 0"]
    assert len(head_texts(doc)) == 10  # fewer paragraphs than the default cap
    assert head_texts(doc, limit=100) == head_texts(doc)


def test_head_texts_limit_zero_still_yields_one():
    """A documented wart at the degenerate boundary, pinned rather than fixed.

    ``head_texts`` appends before testing ``len(out) >= limit``, so ``limit=0``
    returns one paragraph instead of none. Nothing in production passes 0 —
    ``base.py`` scores with the default window and the extractor caps at 40 —
    so this is inert today, and "fix" would be a behaviour change belonging to
    whoever first needs ``limit=0`` to mean *nothing*.

    It is asserted, not ignored: an untested boundary that later acquires a
    caller is how an off-by-one becomes a truncated document.
    """
    doc = StyledDoc(blocks=(para("primeira", 0), para("segunda", 1)))

    assert head_texts(doc, limit=0) == ["primeira"]


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_head_texts_default_window_is_bounded(stem: str):
    """The default window never exceeds 30 on a real document.

    Scoring reads only the front matter (``base.py``'s ``head_texts(doc)``); if
    the cap regressed, a statute quoted at length in a Parecer's body could
    outvote the epigraph — exactly the failure mode plan §2.5 warns about.
    """
    assert len(head_texts(load_sample(stem))) <= 30


# --------------------------------------------------------------------------
# 7. Scoring shape
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_scores_are_bounded_and_complete(stem: str):
    """Every profile is scored, exactly once, within ``0.0``–``1.0``.

    ``score`` composes ``max``/``min`` over several branches; the clamp at the
    end is what keeps a document matching both an epigraph and an authority
    pattern from exceeding 1.0. Asserting the range here means the invariant is
    checked on every sample rather than on the one that happened to saturate.
    """
    scored = score_profiles(load_sample(stem))

    assert tuple(sorted(p.name for p, _ in scored)) == tuple(sorted(EXPECTED_REGISTRY))
    for profile, score in scored:
        assert 0.0 <= score <= 1.0, f"{stem}: {profile.name} scored {score}"

    # Best first, as documented.
    assert [s for _, s in scored] == sorted((s for _, s in scored), reverse=True)


@pytest.mark.parametrize("stem", SAMPLE_STEMS)
def test_select_profile_agrees_with_score_profiles(stem: str):
    """``select_profile`` is the head of ``score_profiles`` — one source of truth.

    They are separate entry points, and Cycle 4b reads the second while the
    extractor reads the first; if they ever disagreed, telemetry would describe
    a decision that was not taken.
    """
    doc = load_sample(stem)

    assert select_profile(doc) is score_profiles(doc)[0][0]
