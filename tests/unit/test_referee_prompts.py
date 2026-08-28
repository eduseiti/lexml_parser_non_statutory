"""What leaves the machine — the referee's prompt, and nothing else.

The cycle's test list carries one line about prompts, and it is a privacy
requirement rather than a formatting one: *prompts contain no PII beyond the
excerpt; excerpt length bounded*. Both halves guard the same failure. A parecer
carries names, roles, NUP numbers and a signature block, and a parser that
ships whole documents to a third-party API to settle a formatting question is
exfiltrating a legal corpus one question at a time — 300 documents' worth,
silently, at a few cents each.

So the assertions here are about what a prompt **is not**:

* it is not the document — only the excerpt under judgement and one paragraph
  of context, each truncated, reach the wire (:data:`MAX_EXCERPT_CHARS`,
  :data:`MAX_CONTEXT_CHARS`);
* it is not a description of the machine — no path, no filename, no URN;
* it never picks up the signature block on its own, because nothing in
  :func:`build_prompt` reads the document at all;
* it is byte-stable for a given question, which is what makes the cache key
  (model, kind, excerpt, context) an honest name for what was asked. A template
  that varied per call would serve hits for questions never asked in that form,
  and take invariant #4 with it.

The last one is why :func:`build_prompt` raises ``KeyError`` on an unknown kind
instead of falling back to a generic template: a question with no template is a
question we do not know how to ask, and asking it anyway produces an answer
nobody can audit.
"""

from __future__ import annotations

import re

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.referee import (
    MAX_CONTEXT_CHARS,
    MAX_EXCERPT_CHARS,
    SYSTEM_PROMPT,
    VOCABULARIES,
    build_prompt,
    truncate,
)

from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"

PARECER_93 = "parecer_93_2018_decor_cgu_agu"
PAR_COSIT_26 = "par_cosit_26_20000629"

#: ``par_cosit_26`` closes with a named signatory (blocks 97 and 101). If a
#: prompt ever grew a "document tail" for context, this is the name that would
#: leave the building.
PAR_COSIT_26_SIGNER = "Carlos Alberto de Niza e Castro"

#: Every kind :func:`build_prompt` knows how to ask.
KINDS: tuple[str, ...] = ("own_articulation", "heading", "section_kind")

#: A conservative sweep: an address in any of the shapes a machine leaks one.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

#: Absolute paths rooted where this pipeline actually runs. Deliberately not a
#: generic ``/\w+/`` — a legal text may legitimately contain a URL, and a test
#: that fired on one would be noise rather than a guard.
ABSOLUTE_PATH_RE = re.compile(r"/(?:work|home|usr|var|etc|tmp|opt|mnt|Users|root)/")

_DOCS: dict[str, object] = {}


def paragraphs(name: str) -> list[str]:
    """Every non-empty paragraph of a sample, in document order."""
    if name not in _DOCS:
        _DOCS[name] = read_docx(SAMPLES_DIR / f"{name}.docx")
    doc = _DOCS[name]
    return [
        text
        for text in ((getattr(b, "text", "") or "").strip() for b in doc.blocks)
        if text
    ]


def a_substantial_paragraph(name: str, *, minimum: int = 120) -> str:
    """The first paragraph long enough to be a real excerpt, deterministically."""
    for text in paragraphs(name):
        if len(text) >= minimum:
            return text
    raise AssertionError(f"{name} has no paragraph of {minimum}+ characters")


# ---------------------------------------------------------------------------
# Bounds — "excerpt length bounded"
# ---------------------------------------------------------------------------


def test_excerpt_is_truncated_to_the_bound():
    """A pathological paragraph must not become a pathological prompt.

    The cap is not about cost. An unbounded excerpt means an unbounded amount
    of one document reaching a third party because a single paragraph happened
    to run long.
    """
    excerpt = "A" * 5000
    _, user = build_prompt("own_articulation", excerpt)

    cut = truncate(excerpt, MAX_EXCERPT_CHARS)
    assert len(cut) == MAX_EXCERPT_CHARS
    assert cut.endswith("…"), "the cut must be visible to the model, not silent"
    assert cut in user
    assert excerpt not in user
    # Nothing longer than the bound survives anywhere in the prompt.
    assert "A" * (MAX_EXCERPT_CHARS + 1) not in user


def test_context_is_truncated_to_the_bound():
    """§2.6's cue is the *preceding* paragraph; one, bounded, is the whole need."""
    ctx = "B" * 5000
    _, user = build_prompt("own_articulation", "Art. 1º Teste.", ctx)

    cut = truncate(ctx, MAX_CONTEXT_CHARS)
    assert len(cut) == MAX_CONTEXT_CHARS
    assert cut.endswith("…")
    assert cut in user
    assert ctx not in user
    assert "B" * (MAX_CONTEXT_CHARS + 1) not in user


def test_truncate_collapses_whitespace():
    """Whitespace is not information here, and it is cache-key noise.

    Two paragraphs differing only in how Word wrapped them are the same
    question; collapsing first makes them the same key.
    """
    assert truncate("a  \n\t b\r\nc  ", 100) == "a b c"
    assert truncate("", 10) == ""
    assert truncate("   ", 10) == ""
    # The bound is inclusive and the marker is inside it, never appended past it.
    assert truncate("abcdef", 4) == "abc…"
    assert len(truncate("abcdef", 4)) == 4
    assert truncate("abcd", 4) == "abcd"


# ---------------------------------------------------------------------------
# Determinism — invariant #4, upstream of the cache
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_prompt_is_deterministic(kind: str):
    """Same question, same bytes.

    The cache key covers the model, the kind, the excerpt and the context — but
    not the template. A prompt that varied per call would hand out cache hits
    for a question that was never asked in that form, and invariant #4 ("same
    input + same referee cache ⇒ byte-identical output") would quietly stop
    being true.
    """
    excerpt = a_substantial_paragraph(PARECER_93)
    ctx = paragraphs(PARECER_93)[0]
    first = build_prompt(kind, excerpt, ctx)
    second = build_prompt(kind, excerpt, ctx)
    assert first == second
    assert isinstance(first, tuple) and len(first) == 2


# ---------------------------------------------------------------------------
# Privacy — "no PII beyond the excerpt"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sample", [PARECER_93, PAR_COSIT_26])
@pytest.mark.parametrize("kind", KINDS)
def test_prompt_carries_no_filesystem_path(sample: str, kind: str):
    """Nothing about *this machine* is any provider's business.

    Not the repository root, not the sample's filename, not the fact that the
    input was a ``.docx`` at all. The referee is asked about a paragraph, not
    about a file.
    """
    body = paragraphs(sample)
    system, user = build_prompt(kind, body[len(body) // 2], body[len(body) // 2 - 1])
    prompt = f"{system}\n{user}"

    assert str(REPO_ROOT) not in prompt
    assert "/work/" not in prompt
    assert ".docx" not in prompt
    assert sample not in prompt
    assert "samples" not in prompt
    assert "urn:lex" not in prompt
    assert ABSOLUTE_PATH_RE.search(prompt) is None


@pytest.mark.parametrize("sample", [PARECER_93, PAR_COSIT_26])
def test_prompt_carries_no_email_address(sample: str):
    """A regex sweep over every prompt the corpus could produce.

    Cheap, and it fails loudly the day someone widens the context window to
    "the surrounding page" and picks up a signature footer with an address in
    it.
    """
    body = paragraphs(sample)
    previous = ""
    for text in body:
        for kind in KINDS:
            system, user = build_prompt(kind, text, previous)
            found = EMAIL_RE.findall(f"{system}\n{user}")
            assert not found, f"{sample}: address(es) {found} reached the prompt"
        previous = text


def test_prompt_contains_only_the_supplied_text():
    """The prompt is the excerpt, the context, and the template. Full stop.

    ``build_prompt`` never sees a document, so the only way another paragraph
    could appear is if some caller widened what it passes. This asserts the
    property from the outside: build one question out of ``parecer_93`` and
    demand that none of its other 425 paragraphs — the epigraph, the NUP, the
    despacho, the signature block — comes along.
    """
    body = paragraphs(PARECER_93)
    index = next(i for i, t in enumerate(body) if len(t) >= 120)
    excerpt, ctx = body[index], body[index - 1]

    system, user = build_prompt("own_articulation", excerpt, ctx)
    prompt = f"{system}\n{user}"

    others = [
        text
        for i, text in enumerate(body)
        if i not in (index, index - 1) and len(text) >= 40
    ]
    assert others, "guard: the sweep must actually have something to sweep"
    leaked = [text for text in others if text in prompt]
    assert not leaked, f"{len(leaked)} unrelated paragraph(s) reached the prompt"

    # And the whole of it is accounted for by the template plus the two pieces.
    assert truncate(excerpt, MAX_EXCERPT_CHARS) in user
    assert truncate(ctx, MAX_CONTEXT_CHARS) in user


@pytest.mark.parametrize("kind", KINDS)
def test_signature_text_is_never_included_implicitly(kind: str):
    """The named signatory of a signed sample must not travel with the question.

    ``par_cosit_26`` ends with its Coordenador-Geral's name in two casings.
    Judging a paragraph in the *body* must not carry either of them; a referee
    deciding whether ``Art. 2º`` is quoted has no use for who signed the
    document, and a provider log that ends up holding the name is a disclosure
    nobody authorised.
    """
    body = paragraphs(PAR_COSIT_26)
    index = next(i for i, t in enumerate(body) if len(t) >= 120)
    system, user = build_prompt(kind, body[index], body[index - 1])
    prompt = f"{system}\n{user}".casefold()

    assert PAR_COSIT_26_SIGNER.casefold() not in prompt
    for word in ("niza", "castro", "coordenador-geral"):
        assert word not in prompt


# ---------------------------------------------------------------------------
# Shape — §7.3 constraint 2, "structured output only"
# ---------------------------------------------------------------------------


def test_json_instruction_is_present():
    """The system prompt demands the three keys the parser will look for.

    Both referees parse ``{verdict, confidence, rationale}`` and abstain on
    anything else, so a system prompt that stopped asking for them would turn
    every live call into an abstention — a silent, total loss of the referee
    that no other test would notice.
    """
    assert "JSON" in SYSTEM_PROMPT
    for key in ("verdict", "confidence", "rationale"):
        assert f'"{key}"' in SYSTEM_PROMPT
    # And it forbids the one output shape that must never come back (§7.1: the
    # referee never generates XML).
    assert "XML" in SYSTEM_PROMPT


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_asks_for_its_own_vocabulary(kind: str):
    """A question whose allowed answers are never stated invites a third one."""
    _, user = build_prompt(kind, "Art. 2º Teste.", "Lei nº 7.713, de 1988 -")
    assert "verdict" in user
    for word in VOCABULARIES.get(kind, ()):
        assert f'"{word}"' in user, f"{kind} never names its own verdict {word!r}"


def test_every_decision_kind_with_a_vocabulary_has_a_template():
    """The two halves of the contract must not drift apart.

    ``VOCABULARIES`` is what the parsers validate against; ``_TEMPLATES`` is
    what gets asked. A kind in one and not the other is either a question with
    no template (``KeyError`` at runtime, mid-corpus) or an answer nobody
    checks.
    """
    for kind in VOCABULARIES:
        system, user = build_prompt(kind, "excerto", "contexto")
        assert system == SYSTEM_PROMPT
        assert user.strip()


def test_unknown_kind_raises():
    """Better a ``KeyError`` here than a model answering a question we did not ask.

    The API referee turns this into an abstention rather than a crash — but the
    builder itself must refuse, so a typo cannot become a generic prompt whose
    answer is then validated against no vocabulary at all.
    """
    with pytest.raises(KeyError):
        build_prompt("nonsense", "Art. 1º Teste.")
    with pytest.raises(KeyError):
        build_prompt("", "Art. 1º Teste.")
