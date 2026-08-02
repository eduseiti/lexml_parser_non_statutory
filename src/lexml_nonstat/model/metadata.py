"""Document metadata: what a document *is*, extracted from how it presents itself.

The output is a :class:`Metadata`, which knows its own URN and — importantly —
knows when it is incomplete. Four of the fifteen samples (``sumula_carf_42``,
``sumula_stj_125``, ``REsp_1306393``, ``CARNE_LEAO``) carry no
authority+type+number+date quadruple at all, so extraction is best-effort by
design: it always yields a syntactically valid URN and never raises, and
:attr:`Metadata.complete` reports honestly what was actually found.

Every extracted value records *where it came from* (``date_source``,
``authority_source``). That is not decoration. The date chain in particular is
tuned against 15 documents and will meet 300+; when it mis-fires, the only way
to see which branch is responsible is to have recorded it at the time.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, Iterable

from lxml import etree

from ..ingest import StyledDoc, StyledPara
from ..profile import DocumentProfile, get_profile, select_profile
from .urn import UrnDate, build_urn, slugify_authority

__all__ = [
    "METADATA_SOURCE_URI",
    "Metadata",
    "ProprietaryField",
    "extract_metadata",
    "parse_pt_date",
]

LEXML_NS = "http://www.lexml.gov.br/1.0"

#: The ``fonte`` attribute ``MetadadoProprietario`` requires (schema
#: ``attributeGroup name="source"``). It identifies this parser as the origin
#: of the fields, which is what the attribute is for.
METADATA_SOURCE_URI = "http://www.lexml.gov.br/nonstat"

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def _fold(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    )


def parse_pt_date(text: str) -> UrnDate | None:
    """Parse the date forms this corpus actually uses.

    Handles ``7 de junho de 2018``, ``1º de dezembro de 2008``, ``28/12/2018``,
    ``2018-06-07`` and a bare ``2018``. Returns ``None`` when the text carries
    no date, so callers can chain fallbacks without exception handling.
    """
    folded = _fold(text)

    m = re.search(
        r"(\d{1,2})\s*[ºo°]?\s*de\s+([a-z]+)\s+de\s+(\d{4})",
        folded,
    )
    if m and m.group(2) in _MONTHS:
        return UrnDate(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))

    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", folded)
    if m:
        return UrnDate(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # Two-digit years appear in citations ("27/08/10"), never as a document's
    # own date, so they are deliberately not accepted here.
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", folded)
    if m:
        return UrnDate(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # A year alone, but only behind the "de" that introduces one. A bare run of
    # four digits is far more often a document number, a process number or a
    # monetary value than a date — "PORTARIA MF nº 277" must not yield the year
    # 277, and dropping the cue makes exactly that happen.
    m = re.search(r"\bde\s+(\d{4})\b", folded)
    if m:
        return UrnDate(int(m.group(1)))

    return None


@dataclass(frozen=True)
class ProprietaryField:
    """A labelled front-matter field LexML has no element for.

    ``NUP``, ``INTERESSADOS``, ``ASSUNTO``, ``Cod. Ement.`` and friends. They
    are real metadata and must not be dropped (plan §8, "unmapped fields land
    in ``MetadadoProprietario``; none dropped"), but LexML's ``Metadado`` has
    nowhere typed to put them.
    """

    label: str
    value: str
    source_index: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "source_index": self.source_index}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProprietaryField":
        return cls(
            label=data["label"],
            value=data["value"],
            source_index=data.get("source_index", -1),
        )


@dataclass(frozen=True)
class Metadata:
    """Everything the ``<Metadado>`` element needs, plus its provenance."""

    profile: str
    locality: str = "br"
    authority: str | None = None
    doc_type: str | None = None
    number: str | None = None
    date: UrnDate | None = None
    date_source: str | None = None
    authority_source: str | None = None
    epigraph: str | None = None
    epigraph_index: int | None = None
    proprietary: tuple[ProprietaryField, ...] = ()
    source: str | None = None

    @property
    def urn(self) -> str:
        """A syntactically valid URN, whatever was found.

        Falls back to the profile's defaults for authority and type, and to
        sentinel values inside :func:`build_urn` for a missing date or number.
        """
        authority = self.authority or "federal"
        doc_type = self.doc_type or "documento"
        return build_urn(
            locality=self.locality,
            authority=authority,
            doc_type=doc_type,
            date=self.date,
            number=self.number,
        )

    def urn_with_fragment(self, fragment: str) -> str:
        """``…;277!anexo1`` — the annex convention of plan §2.9, for Cycle 6."""
        return f"{self.urn}!{fragment}"

    @property
    def missing(self) -> tuple[str, ...]:
        """Which of the four URN components were not found in the document."""
        gaps = []
        if not self.authority:
            gaps.append("authority")
        if not self.doc_type:
            gaps.append("doc_type")
        if not self.number:
            gaps.append("number")
        if self.date is None:
            gaps.append("date")
        return tuple(gaps)

    @property
    def complete(self) -> bool:
        """True when the URN rests on evidence rather than on defaults."""
        return not self.missing

    def field(self, label: str) -> str | None:
        """The value of a proprietary field by label, accent/case-insensitive."""
        want = _fold(label).strip().rstrip(".")
        for f in self.proprietary:
            if _fold(f.label).strip().rstrip(".") == want:
                return f.value
        return None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"profile": self.profile, "locality": self.locality}
        for name in (
            "authority",
            "doc_type",
            "number",
            "date_source",
            "authority_source",
            "epigraph",
            "epigraph_index",
            "source",
        ):
            value = getattr(self, name)
            if value is not None:
                data[name] = value
        if self.date is not None:
            data["date"] = self.date.to_dict()
        data["urn"] = self.urn
        data["complete"] = self.complete
        if self.missing:
            data["missing"] = list(self.missing)
        if self.proprietary:
            data["proprietary"] = [f.to_dict() for f in self.proprietary]
        return data

    def to_json(self, *, indent: int = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Metadata":
        date = data.get("date")
        return cls(
            profile=data["profile"],
            locality=data.get("locality", "br"),
            authority=data.get("authority"),
            doc_type=data.get("doc_type"),
            number=data.get("number"),
            date=UrnDate.from_dict(date) if date else None,
            date_source=data.get("date_source"),
            authority_source=data.get("authority_source"),
            epigraph=data.get("epigraph"),
            epigraph_index=data.get("epigraph_index"),
            proprietary=tuple(
                ProprietaryField.from_dict(f) for f in data.get("proprietary", ())
            ),
            source=data.get("source"),
        )

    @classmethod
    def from_json(cls, text: str) -> "Metadata":
        import json

        return cls.from_dict(json.loads(text))

    def to_xml(self) -> etree._Element:
        """The ``<Metadado>`` element.

        ``MetadadoProprietario`` extends ``xsd:anyType``, so its children are
        unconstrained; it requires a ``fonte`` URI. One element holding all
        fields as ``<campo nome="…">`` children keeps the node count down
        without losing anything. Omitted entirely when there are no fields,
        since the schema makes it optional.
        """
        nsmap = {None: LEXML_NS}
        meta = etree.Element(f"{{{LEXML_NS}}}Metadado", nsmap=nsmap)
        etree.SubElement(meta, f"{{{LEXML_NS}}}Identificacao").set("URN", self.urn)
        if self.proprietary:
            prop = etree.SubElement(meta, f"{{{LEXML_NS}}}MetadadoProprietario")
            prop.set("fonte", METADATA_SOURCE_URI)
            for f in self.proprietary:
                campo = etree.SubElement(prop, f"{{{LEXML_NS}}}campo")
                campo.set("nome", f.label)
                campo.text = f.value
        return meta

    def to_xml_string(self) -> str:
        return etree.tostring(self.to_xml(), pretty_print=True, encoding="unicode")


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

# "Portaria MF nº 277, de 7 de junho de 2018" — the dominant form, 11 of 15.
#
# The trailing group is deliberately permissive about what follows the number:
# besides ", de <data>", the corpus has "RECURSO ESPECIAL Nº 1.306.393 - DF
# (2012/0013476-0)", where a court/case suffix follows. Anything that is not a
# date simply yields no date, which the chain below then fills in.
_EPIGRAPH_RE = re.compile(
    r"^\s*(?P<tipo>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-]{2,60}?)"
    r"\s+n[.ºo°]*\s*(?P<num>\d[\d.,]*)"
    r"(?:\s*[,\-–]?\s*(?P<date>.*))?$",
    re.IGNORECASE,
)

# "PARECER n. 00093/2018/DECOR/CGU/AGU" — number and year fused into a path.
_EPIGRAPH_PATH_RE = re.compile(
    r"^\s*(?P<tipo>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-]{2,60}?)"
    r"\s+n[.ºo°]*\s*(?P<num>\d+)\s*/\s*(?P<year>\d{4})(?P<rest>/\S*)?\s*$",
    re.IGNORECASE,
)

# A bare header stamp, e.g. `parecer_93` block 0.
_BARE_DATE_RE = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{4}\s*$")

# "Brasília, 19 de dezembro de 2018" — the closing local/date line.
_LOCAL_DATE_RE = re.compile(
    r"^\s*(bras[ií]lia|rio de janeiro|s[ãa]o paulo)\s*[,.]",
    re.IGNORECASE,
)

# `Cod. Ement.34` — a label fused to its value with no colon (parecer_93).
_COD_EMENT_RE = re.compile(r"^\s*(cod\.?\s*ement\.?)\s*:?\s*(\S.*)$", re.IGNORECASE)

_LABEL_RE = re.compile(r"^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .\-/]{1,40}?)\s*:\s*(.*)$")

#: How many leading blocks count as "front matter" for field capture. The
#: allowlist does the real work (spec §2.1 decision #4); this bounds the damage
#: if an unseen document repeats a label deep in its body.
_FRONT_MATTER_BLOCKS = 40


def _normalise_number(raw: str) -> str | None:
    """``00093/2018`` → ``93``; ``1.306.393`` → ``1306393``; ``nº 3`` → ``3``."""
    if raw is None:
        return None
    # A number written as a path takes only its first component: the rest is
    # the year and the issuing chain ("00093/2018/DECOR/CGU/AGU").
    head = raw.split("/")[0]
    digits = re.sub(r"[.,\s]", "", head)
    m = re.match(r"^(\d+)", digits)
    if not m:
        return None
    value = m.group(1).lstrip("0")
    return value or "0"


def _authority_from_epigraph(text: str, profile: DocumentProfile) -> str | None:
    """Match the profile's sigla map against the epigraph (``MF``, ``PGFN``…)."""
    upper = text.upper()
    for sigla, slug in profile.authority_map:
        if re.search(rf"(?<![A-Z0-9]){re.escape(sigla.upper())}(?![A-Z0-9])", upper):
            return slug
    return None


def _authority_from_preamble(paras: Iterable[StyledPara]) -> str | None:
    """Read the issuing officer from the preamble opener.

    The preamble names a *person's office* ("O MINISTRO DE ESTADO DA
    FAZENDA"), which maps to the institution that issues the act.
    """
    table = (
        (r"ministro\s+de\s+estado\s+d[ae]\s+fazenda", "ministerio.fazenda"),
        (
            r"procurador(a)?-geral\s+d[ae]\s+fazenda\s+nacional",
            "procuradoria.geral.fazenda.nacional",
        ),
        (
            r"secretari[oa]\s+d[ae]\s+receita\s+federal",
            "ministerio.fazenda;secretaria.receita.federal",
        ),
        (
            r"coordenador(-geral)?\s+d[oe]\s+sistema\s+de\s+tributacao",
            "ministerio.fazenda;secretaria.receita.federal",
        ),
        (r"advocacia-geral\s+da\s+uniao", "advocacia.geral.uniao"),
        (r"advogad[oa]-geral\s+da\s+uniao", "advocacia.geral.uniao"),
        (r"consultoria-geral\s+da\s+uniao", "advocacia.geral.uniao"),
        (r"superior\s+tribunal\s+de\s+justica", "superior.tribunal.justica"),
        (
            r"conselho\s+administrativo\s+de\s+recursos\s+fiscais",
            "ministerio.fazenda;conselho.administrativo.recursos.fiscais",
        ),
    )
    for para in paras:
        folded = _fold(para.text)
        for pattern, slug in table:
            if re.search(pattern, folded):
                return slug
    return None


def _date_from_filename(filename: str | None) -> UrnDate | None:
    """``ad_srf_3_19990107`` → 1999-01-07.

    Last resort only (spec §2.1 decision #3): the 300+ corpus may not follow
    this naming convention, so a filename-derived date must never pre-empt one
    the document states itself.
    """
    if not filename:
        return None
    m = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", filename)
    if not m:
        return None
    year, month, day = (int(g) for g in m.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return UrnDate(year, month, day)


def _find_epigraph(
    paras: list[StyledPara],
) -> tuple[StyledPara | None, str | None, str | None, UrnDate | None]:
    """Locate the epigraph and read type, number and date off it.

    Scans the first several non-empty paragraphs rather than only the first,
    because ``parecer_93`` puts a date stamp and a three-line institutional
    header above its ``PARECER n. …`` line.
    """
    for para in paras[:8]:
        text = para.text.strip()
        if not text:
            continue

        m = _EPIGRAPH_PATH_RE.match(text)
        if m:
            date = UrnDate(int(m.group("year")))
            return para, m.group("tipo").strip(), _normalise_number(m.group("num")), date

        m = _EPIGRAPH_RE.match(text)
        if m:
            date_text = m.group("date")
            date = parse_pt_date(date_text) if date_text else None
            return (
                para,
                m.group("tipo").strip(),
                _normalise_number(m.group("num")),
                date,
            )
    return None, None, None, None


def _extract_fields(
    paras: list[StyledPara], profile: DocumentProfile
) -> tuple[ProprietaryField, ...]:
    """Capture labelled front-matter fields, allowlist-gated.

    Two gates, both required (spec §2.1 decision #4). The label must be one the
    profile declares, *or* be short and fully capitalised; and the paragraph
    must sit in the front-matter region. Without the allowlist,
    ``sumula_stj_125`` yields ``Some-se:``, ``O Sr. Ministro Garcia Vieira:``
    and seven ``Advogados:`` lines — ministers' prose captured as document
    metadata.
    """
    fields: list[ProprietaryField] = []
    seen: set[tuple[str, str]] = set()

    for para in paras[:_FRONT_MATTER_BLOCKS]:
        text = para.text.strip()
        if not text:
            continue

        label: str | None = None
        value: str | None = None

        m = _COD_EMENT_RE.match(text)
        if m and profile.matches_label("Cod. Ement."):
            label, value = "Cod. Ement.", m.group(2).strip()
        else:
            m = _LABEL_RE.match(text)
            if m:
                candidate, rest = m.group(1).strip(), m.group(2).strip()
                allowed = profile.matches_label(candidate)
                # An unlisted label is still captured when it looks like a
                # field rather than a sentence: short, and shouted. This is the
                # bounded-recall path for the 300+ unseen documents.
                shouty = (
                    candidate.isupper()
                    and len(candidate.split()) <= 4
                    and candidate == candidate.strip()
                )
                if allowed or shouty:
                    label, value = candidate, rest

        if label is None or not value:
            continue
        key = (_fold(label), _fold(value))
        if key in seen:
            continue
        seen.add(key)
        fields.append(ProprietaryField(label=label, value=value, source_index=para.index))

    return tuple(fields)


def extract_metadata(
    doc: StyledDoc,
    *,
    profile: DocumentProfile | str | None = None,
    filename: str | None = None,
) -> Metadata:
    """Read a document's identity off its front matter.

    Never raises on a document it cannot identify: the four jurisprudence and
    service samples legitimately carry no number or date, and the pipeline must
    still produce output for them (plan §8, Cycle 8's "handles any document").
    """
    if profile is None:
        prof = select_profile(doc)
    elif isinstance(profile, str):
        prof = get_profile(profile)
    else:
        prof = profile

    paras = [p for p in doc.paragraphs if not p.is_empty]
    source = filename or doc.source

    epi_para, epi_type, number, epi_date = _find_epigraph(paras)

    # --- doc_type: the profile's URN vocabulary wins over the epigraph's
    # wording, so "Ato Declaratório Normativo Cosit" and "Ato Declaratório SRF"
    # both yield `ato.declaratorio` rather than two spellings of one type.
    doc_type = prof.urn_type if epi_type or prof.name != "generic" else None
    if epi_type and prof.name == "generic":
        doc_type = slugify_authority(epi_type) or prof.urn_type

    # --- authority chain: epigraph sigla → preamble opener → profile default.
    authority: str | None = None
    authority_source: str | None = None
    if epi_para is not None:
        authority = _authority_from_epigraph(epi_para.text, prof)
        if authority:
            authority_source = "epigraph"
    if authority is None:
        authority = _authority_from_preamble(paras[:_FRONT_MATTER_BLOCKS])
        if authority:
            authority_source = "preamble"
    if authority is None and prof.urn_authority:
        authority = prof.urn_authority
        authority_source = "profile"

    # --- date chain: epigraph → bare header stamp → signature → filename.
    #
    # A year-only epigraph date does not end the chain. `parecer_93`'s
    # "PARECER n. 00093/2018/…" yields 2018 and nothing finer, while the
    # document's header stamp gives the full 28/12/2018. A later source is
    # therefore allowed to *refine* a year-only date — but only when it agrees
    # on the year, so a stray date elsewhere on the page cannot overwrite the
    # epigraph's.
    date, date_source = epi_date, ("epigraph" if epi_date else None)

    def _consider(candidate: UrnDate | None, label: str) -> bool:
        """Accept ``candidate`` if it fills a gap or sharpens a year-only date."""
        nonlocal date, date_source
        if candidate is None:
            return False
        if date is None:
            date, date_source = candidate, label
            return True
        if not date.is_full and candidate.is_full and candidate.year == date.year:
            date, date_source = candidate, label
            return True
        return False

    if date is None or not date.is_full:
        for para in paras[:8]:
            if _BARE_DATE_RE.match(para.text.strip()):
                if _consider(parse_pt_date(para.text), "header"):
                    break

    if date is None or not date.is_full:
        for para in reversed(paras[-40:]):
            if _LOCAL_DATE_RE.match(para.text.strip()):
                if _consider(parse_pt_date(para.text), "signature"):
                    break

    if date is None:
        _consider(_date_from_filename(source), "filename")

    fields = _extract_fields(paras, prof)

    return Metadata(
        profile=prof.name,
        locality=prof.urn_locality,
        authority=authority,
        doc_type=doc_type,
        number=number,
        date=date,
        date_source=date_source,
        authority_source=authority_source,
        epigraph=epi_para.text.strip() if epi_para is not None else None,
        epigraph_index=epi_para.index if epi_para is not None else None,
        proprietary=fields,
        source=source,
    )
