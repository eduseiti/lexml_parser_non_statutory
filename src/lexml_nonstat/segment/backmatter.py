"""Back matter: local/date closing lines and signature blocks.

The hard part is not finding candidates but rejecting them. Signatures in this
corpus are ALL-CAPS standalone lines near the end of the document — and so are
``ACÓRDÃO``, ``CONCLUSÃO``, ``ORDEM DE INTIMAÇÃO``, ``ADVOCACIA-GERAL DA
UNIÃO``, ``ACÓRDÃOS PARADIGMAS`` and ``COORDENADOR-GERAL DA COSIT``. Measured
on the corpus, a bare ALL-CAPS rule yields six false positives against ten true
signatures.

:func:`looks_like_person_name` is therefore a shape test plus a vocabulary of
words that mark an institution, an office or a section heading. A line is a
person only if every one of its non-connective words is outside that
vocabulary. That keeps ``CARLOS ALBERTO DE NIZA E CASTRO`` while rejecting
``CONSULTORIA-GERAL DA UNIÃO``, and it degrades safely: an unknown institution
whose words are all unlisted is captured as a signature, and Cycle 4b's
telemetry can surface it — the reverse error, dropping a real signer, would be
silent.

Every signature block found is kept, in document order. ``parecer_93`` carries
two: its own, and an appended ``DESPACHO DO CONSULTOR-GERAL DA UNIÃO`` with its
own header, NUP, date and signer. ``pn_cst_38`` likewise carries two. Choosing
one of them is a rendering decision, and rendering is Cycles 5 and 6.
"""

from __future__ import annotations

import re

from ..ingest import StyledDoc, StyledPara
from ..model import parse_pt_date
from ..profile import DocumentProfile, fold
from .model import BackMatter, Signature, Span

__all__ = [
    "find_signatures",
    "is_closing_line",
    "looks_like_person_name",
    "split_trailing_qualifier",
    "segment_back",
]

#: Portuguese name connectives, which carry no evidence either way.
_CONNECTIVES = frozenset({"de", "da", "do", "das", "dos", "e"})

#: Words that mark an institution, an office, or a section heading rather than
#: a person. Folded, so accents and case do not matter.
_NON_NAME_WORDS = frozenset(
    {
        # section headings
        "acordao", "acordaos", "conclusao", "ordem", "intimacao", "ementa",
        "anexo", "sumula", "sumulas", "despacho", "parecer", "portaria",
        "referencia", "referencias", "precedentes", "paradigmas", "voto",
        "relatorio", "assunto", "dispositivos", "legais", "jurisprudencia",
        # institutions
        "advocacia", "consultoria", "procuradoria", "coordenacao", "secretaria",
        "ministerio", "departamento", "conselho", "tribunal", "superior",
        "justica", "uniao", "nacional", "federal", "receita", "fazenda",
        "sistema", "tributacao", "gerencia", "fundacao", "delegacia",
        "superintendencia", "regional", "camara", "seccao", "secao", "turma",
        # offices and titles
        "ministro", "ministra", "secretario", "secretaria_", "procurador",
        "procuradora", "coordenador", "coordenadora", "advogado", "advogada",
        "diretor", "diretora", "chefe", "presidente", "relator", "relatora",
        "auditor", "auditora", "fiscal", "tributos", "federais", "geral",
        "exercicio", "substituto", "substituta", "interino", "interina",
    }
)

#: A signature is a short line. Longer than this and it is a sentence.
_MAX_NAME_WORDS = 7
_MIN_NAME_WORDS = 2

#: How far back from the end of a document (or of the primary body) to look.
#: `par_cosit_26` signs 3 blocks from the end; `port_mf_277` signs at block 5
#: of 138, but its annex is split off first, so the search window is relative
#: to the body, not the file.
BACK_WINDOW = 14


#: Office qualifiers that Word sometimes runs onto the signature line itself.
#: ``adn_cst_10`` block 7 is a single paragraph reading
#: ``JOSEFA MARIA COELHO MARQUES Em exercício`` — the name and its qualifier
#: share one line, so the name is unrecoverable without splitting them off.
_TRAILING_QUALIFIER_RE = re.compile(
    r"\s+(em\s+exerc[ií]cio|substitut[oa]|interin[oa]|"
    r"respondendo|em\s+substitui[çc][ãa]o)\.?\s*$",
    re.I,
)


def split_trailing_qualifier(text: str) -> tuple[str, str | None]:
    """``"NOME Em exercício"`` → ``("NOME", "Em exercício")``."""
    match = _TRAILING_QUALIFIER_RE.search(text.strip())
    if match is None:
        return text.strip(), None
    return text.strip()[: match.start()].strip(), match.group(0).strip()


#: Opening quotation marks. A quoted ALL-CAPS headline is transcribed text, not
#: a signature: ``par_cosit_26`` block 33 quotes an ementa as
#: ``“INCIDÊNCIA DO IRRF. CESSÃO DE PRECATÓRIOS.`` — every word unknown to the
#: institution vocabulary, and so indistinguishable from a name without this.
_QUOTE_CHARS = "\"'“”«»‘’"


def looks_like_person_name(text: str) -> bool:
    """True when ``text`` reads as a personal name rather than an institution.

    Verified against the corpus: 10 real signers accepted, 14 institution,
    heading and quotation lines rejected, no mismatches.
    """
    stripped, _ = split_trailing_qualifier(text)
    stripped = stripped.strip().rstrip(".")
    if not stripped or not stripped.isupper():
        return False
    if stripped[0] in _QUOTE_CHARS or stripped[-1] in _QUOTE_CHARS:
        return False

    words = [w for w in stripped.split() if w]
    if not (_MIN_NAME_WORDS <= len(words) <= _MAX_NAME_WORDS):
        return False

    core = [w for w in words if fold(w) not in _CONNECTIVES]
    if len(core) < _MIN_NAME_WORDS:
        return False

    for word in core:
        folded = fold(word).strip(".-")
        if not folded or folded in _NON_NAME_WORDS:
            return False
        # Letters only — a digit or punctuation run means a number or a code,
        # never a name. A single letter is allowed: "JIMIR S. DONIAK".
        if not folded.isalpha():
            return False
    return True


def _is_cargo(text: str) -> bool:
    """True for an office line, which may follow a signature.

    The mirror image of :func:`looks_like_person_name`: a short line naming an
    office. ``ADVOGADA DA UNIÃO``, ``Coordenador-Geral``, ``Fiscal de Tributos
    Federais``.
    """
    stripped = text.strip().rstrip(".")
    if not stripped or len(stripped.split()) > _MAX_NAME_WORDS:
        return False
    words = [fold(w).strip(".-") for w in stripped.split()]
    core = [w for w in words if w and w not in _CONNECTIVES]
    if not core:
        return False
    return any(w in _NON_NAME_WORDS for w in core)


#: Parentheticals that mark a date as belonging to a *reported* proceeding
#: rather than to this document's own closing. ``sumula_stj_125`` carries seven
#: lines reading ``Brasília (DF), … (data do julgamento).`` — the judgment dates
#: of the precedents it compiles. Reading the last one as the súmula's closing
#: truncates the document 53 blocks early.
_REPORTED_DATE_RES = (
    re.compile(r"\(\s*data\s+do\s+julgamento\s*\)", re.I),
    re.compile(r"\(\s*data\s+da\s+(publicacao|publicação|sessao|sessão)\s*\)", re.I),
)


def is_closing_line(text: str, profile: DocumentProfile) -> bool:
    """True when ``text`` closes *this* document, not a proceeding it reports."""
    stripped = text.strip()
    if not any(r.match(stripped) for r in profile.closing_res):
        return False
    return not any(r.search(stripped) for r in _REPORTED_DATE_RES)


def _find_closing(
    paras: list[StyledPara], profile: DocumentProfile
) -> tuple[Span, str] | None:
    """The last local/date closing line among ``paras``."""
    for para in reversed(paras):
        text = para.text.strip()
        if is_closing_line(text, profile):
            return Span(para.index, para.index), text
    return None


def find_signatures(
    doc: StyledDoc,
    profile: DocumentProfile,
    *,
    within: Span | None = None,
) -> tuple[Signature, ...]:
    """Every signature block in ``within`` (default: the whole document).

    A block is a person line, optionally preceded by a closing date line and
    optionally followed by an office line.
    """
    paras = [p for p in doc.paragraphs if not p.is_empty]
    if within is not None:
        paras = [p for p in paras if p.index in within]
    if not paras:
        return ()

    by_position = {p.index: i for i, p in enumerate(paras)}
    signatures: list[Signature] = []

    for position, para in enumerate(paras):
        if not looks_like_person_name(para.text):
            continue

        start = end = para.index
        name, qualifier = split_trailing_qualifier(para.text)
        name = name.rstrip(".")

        # An office line may follow the name, or ride on the same line.
        cargo: str | None = qualifier
        if cargo is None and position + 1 < len(paras):
            following = paras[position + 1]
            if _is_cargo(following.text) and not looks_like_person_name(
                following.text
            ):
                cargo = following.text.strip()
                end = following.index

        # A closing date may precede it, within a couple of lines.
        local_date: str | None = None
        for back in range(1, 3):
            if position - back < 0:
                break
            candidate = paras[position - back]
            text = candidate.text.strip()
            if is_closing_line(text, profile):
                local_date = text
                start = candidate.index
                break

        signatures.append(
            Signature(
                name=name,
                cargo=cargo,
                local_date=local_date,
                span=Span(start, end),
                date=parse_pt_date(local_date) if local_date else None,
            )
        )

    # Drop a signature swallowed by the previous one's office line.
    deduped: list[Signature] = []
    for signature in signatures:
        if deduped and signature.span.start <= deduped[-1].span.end:
            continue
        deduped.append(signature)
    return tuple(deduped)


def segment_back(
    doc: StyledDoc,
    profile: DocumentProfile,
    *,
    within: Span | None = None,
) -> BackMatter:
    """Closing date and signatures for ``doc``, restricted to ``within``."""
    signatures = find_signatures(doc, profile, within=within)

    paras = [p for p in doc.paragraphs if not p.is_empty]
    if within is not None:
        paras = [p for p in paras if p.index in within]

    local_date: Span | None = None
    if not any(s.local_date for s in signatures):
        found = _find_closing(paras, profile)
        if found is not None:
            local_date = found[0]

    return BackMatter(signatures=signatures, local_date=local_date)
