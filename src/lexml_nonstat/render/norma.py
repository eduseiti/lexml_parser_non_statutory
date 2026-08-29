"""The statutory ``norma`` emitter — plan §4.3, §5.3, and §4.2's safety rule.

One sample in fifteen routes here: ``port_mf_277``, whose two genuine articles
survive the quotation guard while its 130-entry ``ANEXO ÚNICO`` splits off as a
sibling document. Fourteen do not, and §4.4 is explicit that "statutory
detection's main job is refusing false positives" — so this module's most
important function is not :func:`render_norma` but :func:`render_statutory`,
which renders, *checks*, and falls back.

Four schema facts, each measured against both shipped schemas before a line of
this module was written, and each of which the plan's §4.3 snippet does not
state:

**Dispositivo ids are pattern-constrained.** ``lexml09-flexivel.xsd`` restricts
``idArtigo`` with an ``xsd:pattern`` — ``art1``, ``art1_cpt``, ``art1_par1``,
``art1_cpt_inc1`` are legal, and **``pp1_art1`` is rejected by both schemas**.
Cycle 5's path-composed :class:`~.ids.IdAllocator` therefore cannot issue them:
the two id grammars are incompatible, so :class:`DispositivoIds` is a second,
separate allocator (amendment **A-6.1**). The two spaces never meet — a
``Norma`` primary has no ``Agrupamento`` and an annex has no dispositivo — so
one document can carry both without collision.

**``ParteInicial`` and ``ParteFinal`` are closed sequences.** Neither
``<Agrupamento>`` nor a bare ``<p>`` is accepted inside them, so amendment
A-5.1's "regions, not parts" rendering — the one that exists because 40
non-empty blocks in 6 samples sit inside a hull and inside no named part — has
**no statutory equivalent**. ``Preambulo`` is ``textoSimplesType`` and takes
several ``<p>``, so *front* residue folds in; ``ParteFinal`` offers nothing at
all, so *back* residue makes the document unrenderable as a ``Norma`` and it
falls back (amendment **A-6.2**). Text is never dropped to keep a route.

**``Rotulo`` is required on ``Artigo`` and must precede ``Caput``.** Both
orderings were probed: an ``Artigo`` without a ``Rotulo`` and a ``Caput``
before its ``Rotulo`` are each rejected on both schemas. That is what makes
"a deliberately mis-ordered tree fails validation" assertable against the
schema itself rather than against a check of our own.

**``Anexos`` follows ``ParteFinal``.** ``HierarchicalStructure`` is an
``xsd:sequence`` of ``ParteInicial? Articulacao ParteFinal? Anexos?``; emitting
the annex pointers before the signatures fails on both schemas.

Building an articulation the source lacks is exactly the sin that got Cycle 6b
withdrawn (A-R.6). This builder therefore reads
:func:`~..hierarchy.labels.parse_label` and nothing else, refuses whatever it
cannot label, and hands the verdict to a gate that would rather fall back than
invent structure.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from lxml import etree

from ..model.document import DocumentModel
from ..model.nodes import ListNode, Para, Table
from ..hierarchy.labels import fold, parse_label
from ..segment.render import render_parte_final, render_parte_inicial
from .anexo import anexos_element, lexml_root, render_anexo
from .common import el, words
from .generico import RenderedDocument, render_generico

__all__ = [
    "ARTIGO_ID_RE",
    "BLOCKER_BACK_RESIDUE",
    "BLOCKER_LOSSY",
    "BLOCKER_INVALID",
    "EMITTER",
    "Artigo",
    "Caput",
    "DispositivoIds",
    "Inciso",
    "Paragrafo",
    "build_articulacao",
    "render_articulacao",
    "render_norma",
    "render_norma_checked",
    "render_norma_from_docx",
    "render_statutory",
]

logger = logging.getLogger("lexml_nonstat.render.norma")

#: This emitter's name, as it appears in :attr:`RenderedDocument.emitter` and
#: on the CLI's ``--emitter`` flag (Cycle 8).
EMITTER = "norma"

#: ``lexml09-flexivel.xsd``'s own ``idArtigo`` pattern, transcribed for the
#: levels this cycle builds. Not a re-derivation: a test validates every
#: emitted id against the schema *as well*, so this is the fast check and the
#: schema is the authority.
ARTIGO_ID_RE = re.compile(
    r"^art(\d+|1u)((_cpt|_par(\d+|1u))(_inc\d+)?)?$"
)

# Re-exported, not redeclared: `routing.viability` owns `BLOCKER_CODES`, and a
# code this module invented independently would be one no verdict could name —
# the exact failure that module's "a blocker nobody can name is a blocker
# nobody will fix" comment guards against.
from ..routing.viability import (  # noqa: E402  (after the module docstring)
    BLOCKER_BACK_RESIDUE,
    BLOCKER_STATUTORY_INVALID as BLOCKER_INVALID,
    BLOCKER_STATUTORY_LOSSY as BLOCKER_LOSSY,
)


# --------------------------------------------------------------------------
# Ids — A-6.1
# --------------------------------------------------------------------------


class DispositivoIds:
    """Issues ``art1`` / ``art1_cpt`` / ``art1_par1`` / ``art1_cpt_inc1``.

    Separate from :class:`~.ids.IdAllocator` because the two id grammars are
    incompatible: that one composes a path from a parent it has issued, this
    one must satisfy a schema pattern that forbids any prefix but ``art``.
    Mixing them would make one module answer to two constraints (A-6.1).

    Uniqueness is enforced the same way, because ``xsd:ID`` still requires it —
    the schema catches a collision only after the document is written.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._incisos: dict[str, int] = {}

    def _take(self, ident: str) -> str:
        if not ARTIGO_ID_RE.match(ident):
            raise ValueError(f"not a schema-legal dispositivo id: {ident!r}")
        if ident in self._seen:
            raise ValueError(f"duplicate id: {ident!r}")
        self._seen.add(ident)
        return ident

    def artigo(self, number: int | None, *, unico: bool = False) -> str:
        """``art1``, or ``art1u`` for an ``Artigo único`` (probe N13)."""
        return self._take("art1u" if unico else f"art{number}")

    def caput(self, artigo_id: str) -> str:
        return self._take(f"{artigo_id}_cpt")

    def paragrafo(self, artigo_id: str, number: int, *, unico: bool = False) -> str:
        """``art1_par1``, or ``art1_par1u`` for a ``Parágrafo único``."""
        suffix = "1u" if unico else str(number)
        return self._take(f"{artigo_id}_par{suffix}")

    def inciso(self, parent_id: str) -> str:
        """The next ``…_incN`` under ``parent_id`` — a ``Caput`` or ``Paragrafo``."""
        self._incisos[parent_id] = self._incisos.get(parent_id, 0) + 1
        return self._take(f"{parent_id}_inc{self._incisos[parent_id]}")

    @property
    def issued(self) -> tuple[str, ...]:
        return tuple(sorted(self._seen))


# --------------------------------------------------------------------------
# The articulation — A-6.3's four levels
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Inciso:
    """``I -``, ``II -`` — a ``Caput``'s or ``Paragrafo``'s enumerated item."""

    rotulo: str
    ident: str
    paragraphs: tuple[str, ...] = ()
    source_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class Caput:
    """An article's opening text. Carries its own ``Rotulo`` (D-3)."""

    rotulo: str
    ident: str
    paragraphs: tuple[str, ...] = ()
    incisos: tuple[Inciso, ...] = ()
    source_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class Paragrafo:
    """``§ 1º``, ``Parágrafo único``."""

    rotulo: str
    ident: str
    paragraphs: tuple[str, ...] = ()
    incisos: tuple[Inciso, ...] = ()
    source_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class Artigo:
    """One ``Artigo``: a ``Rotulo``, a ``Caput``, then its parágrafos."""

    rotulo: str
    ident: str
    caput: Caput
    paragrafos: tuple[Paragrafo, ...] = ()
    source_indices: tuple[int, ...] = ()

    @property
    def all_source_indices(self) -> tuple[int, ...]:
        out = list(self.source_indices) + list(self.caput.source_indices)
        for inciso in self.caput.incisos:
            out.extend(inciso.source_indices)
        for paragrafo in self.paragrafos:
            out.extend(paragrafo.source_indices)
            for inciso in paragrafo.incisos:
                out.extend(inciso.source_indices)
        return tuple(out)


class _Unarticulable(Exception):
    """Raised when a body node cannot be expressed as a dispositivo.

    Caught by :func:`build_articulacao`, which returns ``()`` — the gate then
    falls back. Never propagates to a caller: a document we cannot articulate
    is a routing outcome, not an error.
    """


def _body_paras(model: DocumentModel):
    """Every body node, in document order, refusing anything unarticulable.

    Tables and lists are **rejected inside ``Caput``** by both schemas (probes
    B10, B11), so a body carrying one cannot be articulated at all — and
    dropping it would lose text. Refusing here is what routes such a document
    to ``generico``, where the same content is expressible (D-6).
    """
    tree = model.body
    nodes = list(tree.preamble)
    for section in tree.sections:
        for node in section.body:
            nodes.append(node)
        if section.children:
            raise _Unarticulable("body has nested sections")

    out = []
    for node in nodes:
        if isinstance(node, (ListNode, Table)):
            raise _Unarticulable(f"{type(node).__name__} cannot sit inside a Caput")
        if isinstance(node, Para) and not node.is_empty:
            out.append(node)
    return out


def build_articulacao(model: DocumentModel) -> tuple[Artigo, ...]:
    """Read the body as ``Artigo``s, or return ``()`` if it does not read as one.

    Labels come from :func:`~..hierarchy.labels.parse_label` alone — Cycle 4
    owns the grammar, and a second one here would be the competing source of
    truth A-3.4 refused. Anything before the first article, and anything the
    grammar cannot name, makes the whole body unarticulable rather than being
    silently absorbed: that is the difference between reading an articulation
    and inventing one (A-R.6).
    """
    try:
        paras = _body_paras(model)
    except _Unarticulable as reason:
        logger.debug("articulacao refused: %s", reason)
        return ()

    if not paras:
        return ()

    ids = DispositivoIds()
    artigos: list[Artigo] = []

    # Mutable frames, collapsed into the frozen records as each one closes.
    current: dict | None = None
    target: dict | None = None  # the caput or parágrafo receiving prose

    def close_artigo() -> None:
        if current is None:
            return
        caput = Caput(
            rotulo=current["rotulo"],
            ident=current["caput_id"],
            paragraphs=tuple(current["caput_paras"]),
            incisos=tuple(current["caput_incisos"]),
            source_indices=tuple(current["caput_src"]),
        )
        artigos.append(
            Artigo(
                rotulo=current["rotulo"],
                ident=current["ident"],
                caput=caput,
                paragrafos=tuple(
                    Paragrafo(
                        rotulo=p["rotulo"],
                        ident=p["ident"],
                        paragraphs=tuple(p["paras"]),
                        incisos=tuple(p["incisos"]),
                        source_indices=tuple(p["src"]),
                    )
                    for p in current["paragrafos"]
                ),
                source_indices=tuple(current["src"]),
            )
        )

    try:
        for para in paras:
            text = para.text.strip()
            label = parse_label(text)
            kind = label.kind if label else None

            if kind == "artigo":
                close_artigo()
                # `Art. único` is **not** an artigo to Cycle 4: `ARTICLE_RE`
                # requires a digit, so it parses as `None` and reaches the
                # unlabelled branch below, where it becomes caput prose of the
                # article above it. Measured, not assumed — and left alone,
                # because inventing a number the grammar refused to read is the
                # kind of fabrication A-R.6 withdrew a whole cycle over. The
                # `unico=` path of `DispositivoIds.artigo` is therefore reached
                # only by a caller building an articulation directly, which is
                # why it is tested there rather than here.
                ident = ids.artigo(label.value[0])
                current = {
                    "rotulo": label.raw,
                    "ident": ident,
                    "src": list(para.source_indices),
                    "caput_id": ids.caput(ident),
                    "caput_paras": [label.text] if label.text else [],
                    "caput_incisos": [],
                    "caput_src": list(para.source_indices),
                    "paragrafos": [],
                }
                target = None
                continue

            if current is None:
                # Prose before the first article. §4.2's coverage gate would
                # catch it, but refusing here says *why* rather than scoring it.
                raise _Unarticulable("body text precedes the first article")

            if kind == "paragrafo":
                # `parse_label` returns value `(1,)` for `§ 1º` *and* for
                # `Parágrafo único`, so the ordinal cannot distinguish them —
                # the word can. `1u` is the `idArtigo` pattern's own escape
                # hatch, admitted exactly where a number is, so an unnumbered
                # parágrafo keeps a schema-legal id instead of being renumbered
                # `1` and cited as something the document never said.
                #
                # Folded through Cycle 4's own `fold`, not `casefold`: every
                # real Brazilian legal text writes `único` with the accent, and
                # a plain lowercase comparison silently misses all of them. A
                # test-authoring subagent caught exactly that.
                unico = "unic" in fold(label.raw)
                number = label.value[0] if label.value else 1
                frame = {
                    "rotulo": label.raw,
                    "ident": ids.paragrafo(current["ident"], number, unico=unico),
                    "paras": [label.text] if label.text else [],
                    "incisos": [],
                    "src": list(para.source_indices),
                }
                current["paragrafos"].append(frame)
                target = frame
                continue

            if kind == "roman":
                parent_id = (
                    target["ident"] if target is not None else current["caput_id"]
                )
                inciso = Inciso(
                    rotulo=label.raw,
                    ident=ids.inciso(parent_id),
                    paragraphs=(label.text,) if label.text else (),
                    source_indices=tuple(para.source_indices),
                )
                bucket = (
                    target["incisos"] if target is not None else current["caput_incisos"]
                )
                bucket.append(inciso)
                continue

            # Unlabelled continuation prose, which belongs to whatever is open.
            if target is not None:
                target["paras"].append(text)
                target["src"].extend(para.source_indices)
            else:
                current["caput_paras"].append(text)
                current["caput_src"].extend(para.source_indices)
    except (_Unarticulable, ValueError) as reason:
        logger.debug("articulacao refused: %s", reason)
        return ()

    close_artigo()
    return tuple(artigos)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _paragraphs(parent: etree._Element, texts: tuple[str, ...]) -> None:
    for text in texts:
        if not text.strip():
            continue
        paragraph = el("p")
        paragraph.text = text
        parent.append(paragraph)


def _dispositivo(
    tag: str, rotulo: str, ident: str, texts: tuple[str, ...], incisos=()
) -> etree._Element:
    """A ``DispositivoType`` element: ``Rotulo``, then ``p``s, then children.

    The order is the schema's ``xsd:sequence``, not ours, and reversing any of
    it fails validation — which is the point of the mis-ordering test.
    """
    element = el(tag, id=ident)
    label = el("Rotulo")
    label.text = rotulo
    element.append(label)
    _paragraphs(element, texts)
    for inciso in incisos:
        element.append(
            _dispositivo("Inciso", inciso.rotulo, inciso.ident, inciso.paragraphs)
        )
    return element


def render_articulacao(articulacao: tuple[Artigo, ...]) -> etree._Element | None:
    """``<Articulacao>``, or ``None`` when there is nothing to articulate.

    ``None`` rather than an empty element: ``Articulacao`` requires at least one
    ``hierElements`` child and an empty one is rejected on both schemas.
    """
    if not articulacao:
        return None
    element = el("Articulacao")
    for artigo in articulacao:
        node = el("Artigo", id=artigo.ident)
        rotulo = el("Rotulo")
        rotulo.text = artigo.rotulo
        node.append(rotulo)
        node.append(
            _dispositivo(
                "Caput",
                artigo.caput.rotulo,
                artigo.caput.ident,
                artigo.caput.paragraphs,
                artigo.caput.incisos,
            )
        )
        for paragrafo in artigo.paragrafos:
            node.append(
                _dispositivo(
                    "Paragrafo",
                    paragrafo.rotulo,
                    paragrafo.ident,
                    paragrafo.paragraphs,
                    paragrafo.incisos,
                )
            )
        element.append(node)
    return element


def _front_residue(model: DocumentModel) -> tuple[str, ...]:
    """Hull blocks inside no named front part, in document order (A-6.2).

    Measured over the corpus: 6 samples carry some, up to 7 blocks in
    ``parecer_93``. ``port_mf_277`` carries none, so folding them into
    ``Preambulo`` changes nothing here and prevents silent loss elsewhere.
    """
    front = model.segmentation.front
    hull = front.hull(model.segmentation.first_index)
    if hull is None:
        return ()
    claimed: set[int] = set()
    for span in (front.epigraph, front.ementa, front.preamble, front.enacting_formula):
        if span is not None:
            claimed.update(span.indices)
    out = []
    for index in hull.indices:
        if index in claimed:
            continue
        text = model.block_text(index).strip()
        if text:
            out.append(text)
    return tuple(out)


def back_residue(model: DocumentModel) -> tuple[str, ...]:
    """Back-matter hull blocks inside no signature or closing date (A-6.2).

    Public because it is a *gate input*, not an implementation detail: a
    document carrying any is refused the statutory route, and a caller
    inspecting the blocker deserves to see what could not be placed.
    """
    back = model.segmentation.back
    if back.span is None:
        return ()
    claimed: set[int] = set()
    for signature in back.signatures:
        claimed.update(signature.span.indices)
    if back.local_date is not None:
        claimed.update(back.local_date.indices)
    out = []
    for index in back.span.indices:
        if index in claimed:
            continue
        text = model.block_text(index).strip()
        if text:
            out.append(text)
    return tuple(out)


def _parte_inicial(model: DocumentModel) -> etree._Element | None:
    """Cycle 3's ``ParteInicial``, with front residue folded into ``Preambulo``.

    The residue goes *before* the preamble's own lines because that is where it
    stands in the document — ``parecer_93``'s portal stamp and institutional
    banner sit above everything. Folding preserves both the text and its order,
    which a closed content model otherwise makes impossible (A-6.2).
    """
    element = render_parte_inicial(model.segmentation.front, model.styled)
    residue = _front_residue(model)
    if not residue:
        return element

    if element is None:
        element = el("ParteInicial")

    preambulo = None
    for child in element:
        if etree.QName(child).localname == "Preambulo":
            preambulo = child
            break

    if preambulo is None:
        preambulo = el("Preambulo", id="pre1")
        element.append(preambulo)

    for offset, text in enumerate(residue):
        paragraph = el("p")
        paragraph.text = text
        preambulo.insert(offset, paragraph)

    return element if len(element) else None


def render_norma(model: DocumentModel) -> RenderedDocument:
    """Render ``model`` as a ``Norma`` bundle — **ungated**.

    Raises nothing and checks nothing: it is :func:`render_statutory` that
    decides whether the result may be published. Kept separate so a test can
    inspect an unarticulable render rather than only its fallback.
    """
    root = lexml_root()
    root.append(model.metadata.to_xml())

    norma = el("Norma")

    parte_inicial = _parte_inicial(model)
    if parte_inicial is not None:
        norma.append(parte_inicial)

    articulacao = render_articulacao(build_articulacao(model))
    if articulacao is not None:
        norma.append(articulacao)

    parte_final = render_parte_final(model.segmentation.back, model.styled)
    if parte_final is not None:
        norma.append(parte_final)

    # After ParteFinal — the sequence is the schema's, not document order (D-2).
    annexes = tuple(render_anexo(model, annex) for annex in model.annexes)
    anexos = anexos_element(model)
    if anexos is not None:
        norma.append(anexos)

    root.append(norma)

    return RenderedDocument(
        primary=root,
        annexes=annexes,
        urn=model.metadata.urn,
        emitter=EMITTER,
        source=model.source,
    )


# --------------------------------------------------------------------------
# §4.2 — validate, then fall back
# --------------------------------------------------------------------------


def _validation_blocker(rendered: RenderedDocument):
    """Every document in the bundle against both shipped schemas, or ``None``.

    The shipped generation, always: a ``Norma`` uses no proposed-schema
    construct, and gating publication on a directory that may not exist would
    make the route depend on the checkout (Q-6's determinism rule).
    """
    from ..routing.viability import Blocker
    from ..validate.schema import SHIPPED, load_schemas

    schemas = load_schemas(generation=SHIPPED)
    for document in rendered.documents:
        for name, schema in schemas.items():
            if schema.validate(document):
                continue
            message = str(schema.error_log[0].message) if len(schema.error_log) else ""
            return Blocker(
                BLOCKER_INVALID,
                f"{name} rejected the statutory render: {message}",
            )
    return None


def _conservation_blocker(rendered: RenderedDocument, reference: RenderedDocument):
    """Word-multiset equality between the statutory bundle and the generic one.

    The generic render is the reference because it is the one invariant #2 is
    already asserted against, sample by sample, for all 15 — so a difference
    here is a statement about *this* emitter, not a fresh measurement of the
    source. A schema cannot detect lost text, which is why validity alone is
    not the gate (A-6.3).
    """
    from collections import Counter

    from ..routing.viability import Blocker

    got = Counter(words(rendered.texts))
    want = Counter(words(reference.texts))
    if got == want:
        return None

    missing = sum((want - got).values())
    extra = sum((got - want).values())
    sample = ", ".join(sorted((want - got))[:5]) or ", ".join(sorted((got - want))[:5])
    return Blocker(
        BLOCKER_LOSSY,
        f"statutory render differs from the generic one by "
        f"{missing} missing and {extra} duplicated word(s): {sample}",
    )


def render_norma_checked(
    model: DocumentModel, *, generico: RenderedDocument | None = None
):
    """Render statutorily and report every reason it may not be published.

    Returns ``(rendered, blockers)``. The blockers are §4.2's four gates, in the
    order it is cheapest to fail them, and each is a
    :class:`~..routing.viability.Blocker` so the reason survives into telemetry
    rather than into a log line nobody reads.
    """
    from ..routing.coverage import COVERAGE_MIN
    from ..routing.viability import BLOCKER_LOW_COVERAGE, Blocker

    blockers: list = []

    residue = back_residue(model)
    if residue:
        blockers.append(
            Blocker(
                BLOCKER_BACK_RESIDUE,
                f"{len(residue)} back-matter block(s) fit no ParteFinal element, "
                f"which admits only LocalDataFecho and Assinatura: "
                f"{residue[0][:60]!r}",
            )
        )

    articulacao = build_articulacao(model)
    if not articulacao:
        blockers.append(
            Blocker(
                BLOCKER_INVALID,
                "the body does not read as an articulation",
            )
        )

    coverage = getattr(model.viability, "coverage", 0.0)
    if coverage < COVERAGE_MIN:
        blockers.append(
            Blocker(
                BLOCKER_LOW_COVERAGE,
                f"articulation covers {coverage:.2f} of the body, below "
                f"{COVERAGE_MIN}",
            )
        )

    rendered = render_norma(model)

    if not blockers:
        invalid = _validation_blocker(rendered)
        if invalid is not None:
            blockers.append(invalid)
        else:
            reference = generico if generico is not None else render_generico(model)
            lossy = _conservation_blocker(rendered, reference)
            if lossy is not None:
                blockers.append(lossy)

    return rendered, tuple(blockers)


def render_statutory(model: DocumentModel) -> RenderedDocument:
    """§4.2's validate-then-fallback: the statutory bundle, or the generic one.

    This is what makes "prefer statutory when possible" safe **by construction**
    rather than by trusting the classifier. A document that is not routed to
    ``norma`` never even attempts it; one that is, attempts it and keeps the
    result only if it validates, conserves every word and covers the body.

    The returned :attr:`RenderedDocument.emitter` says which emitter actually
    produced the artifact, so a fallback is visible in the output and not only
    in the log.
    """
    generico = render_generico(model)

    if model.route != EMITTER:
        return generico

    rendered, blockers = render_norma_checked(model, generico=generico)
    if not blockers:
        return rendered

    for blocker in blockers:
        logger.warning(
            "%s: statutory render refused, falling back to generico — %s",
            model.source or "<document>",
            blocker,
        )
    return generico


def render_norma_from_docx(path, *, filename: str | None = None) -> RenderedDocument:
    """Read a DOCX and render it statutorily, with §4.2's fallback applied."""
    from pathlib import Path

    from ..ingest import read_docx
    from ..model import build_model

    path = Path(path)
    model = build_model(read_docx(path), filename=filename or path.name)
    return render_statutory(model)
