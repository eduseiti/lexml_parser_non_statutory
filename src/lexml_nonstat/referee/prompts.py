"""Prompt construction — bounded, deterministic, and free of anything private.

Two requirements from the cycle's test list drive every line here: *prompts
contain no PII beyond the excerpt*, and *excerpt length is bounded*. Both are
about the same thing. A legal opinion carries names, roles and signatures, and
a parser that ships whole documents to a third-party API to settle a formatting
question is exfiltrating a corpus one question at a time.

So a prompt is built from exactly two pieces of document text — the excerpt
under judgement and one paragraph of context — each truncated, and neither ever
drawn from a signature block. No filename, no path, no URN, no metadata.

The prompts are also fixed strings, not f-string mosaics, because the cache key
covers the excerpt and the model but not the template: a template that varied
per call would produce cache hits for questions that were never actually asked
in that form.
"""

from __future__ import annotations

from .protocol import BOUNDARY_VERDICTS, HEADING_VERDICTS, OWN_ARTICULATION_VERDICTS

__all__ = [
    "MAX_CONTEXT_CHARS",
    "MAX_EXCERPT_CHARS",
    "SYSTEM_PROMPT",
    "build_prompt",
    "truncate",
]

#: The paragraph under judgement. An article caput is well under this; the cap
#: exists for the pathological paragraph, not the ordinary one.
MAX_EXCERPT_CHARS = 1200

#: One paragraph of antecedent. §2.6's cue is the *preceding* paragraph naming
#: an external norm, so one is enough and two would only add exposure.
#:
#: Which paragraph that *is* changed with amendments A-Q.3 and A-Q.7: the
#: caller now passes the nearest preceding **citation antecedent** rather than
#: whatever paragraph happened to be immediately above. Record §2.3 traced two
#: wrong high-confidence overrides to exactly that gap — the sentence naming
#: the owning law sat two paragraphs back, outside this window. The cap is
#: unchanged; only the caller's choice of which paragraph to spend it on is.
MAX_CONTEXT_CHARS = 600

SYSTEM_PROMPT = (
    "Você é um revisor técnico de documentos jurídicos brasileiros. "
    "Responda EXCLUSIVAMENTE com um objeto JSON com as chaves "
    '"verdict", "confidence" e "rationale". '
    '"confidence" é um número entre 0 e 1. '
    '"rationale" tem no máximo 200 caracteres. '
    "Não escreva XML, não escreva explicações fora do JSON."
)

_TEMPLATES: dict[str, str] = {
    "own_articulation": (
        "O trecho abaixo é um artigo DO PRÓPRIO documento, ou um artigo de "
        "outra norma que o documento está CITANDO?\n\n"
        "Parágrafo anterior (contexto):\n{ctx}\n\n"
        "Trecho em julgamento:\n{excerpt}\n\n"
        'Responda "verdict": "own" se for articulação própria do documento, '
        'ou "quoted" se for citação de norma externa.'
    ),
    "heading": (
        "O trecho abaixo é um TÍTULO de seção, ou uma frase enfatizada dentro "
        "do texto corrido?\n\n"
        "Parágrafo anterior (contexto):\n{ctx}\n\n"
        "Trecho em julgamento:\n{excerpt}\n\n"
        'Responda "verdict": "heading" ou "prose".'
    ),
    "quotation_boundary": (
        "O documento anunciou que vai transcrever trechos de VÁRIAS normas "
        "diferentes. O trecho em julgamento inicia a transcrição de uma norma "
        "DIFERENTE da anterior, ou é continuação da mesma transcrição?\n\n"
        "Parágrafo que anuncia as normas transcritas:\n{ctx}\n\n"
        "Trecho em julgamento:\n{excerpt}\n\n"
        'Responda "verdict": "boundary" se o trecho inicia a transcrição de '
        'outra norma, ou "continuation" se pertence à transcrição anterior.'
    ),
    "section_kind": (
        "Que tipo de agrupamento o rótulo abaixo introduz?\n\n"
        "Rótulo:\n{excerpt}\n\n"
        "Título:\n{ctx}\n\n"
        'Responda "verdict" com uma única palavra minúscula, por exemplo '
        '"capitulo", "secao", "item", "topico".'
    ),
}

#: What each kind is allowed to answer, for the caller that checks.
VOCABULARIES: dict[str, tuple[str, ...]] = {
    "own_articulation": OWN_ARTICULATION_VERDICTS,
    "heading": HEADING_VERDICTS,
    "quotation_boundary": BOUNDARY_VERDICTS,
}


def truncate(text: str, limit: int) -> str:
    """Collapse whitespace and cut to ``limit`` characters, marking the cut."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_prompt(kind: str, excerpt: str, ctx: str = "") -> tuple[str, str]:
    """Return ``(system, user)`` for one question.

    Raises:
        KeyError: if ``kind`` is not a known decision kind — better than
            silently asking a model a question with no template.
    """
    template = _TEMPLATES[kind]
    return SYSTEM_PROMPT, template.format(
        excerpt=truncate(excerpt, MAX_EXCERPT_CHARS),
        ctx=truncate(ctx, MAX_CONTEXT_CHARS) or "(nenhum)",
    )
