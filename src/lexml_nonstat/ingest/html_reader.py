"""HTML → :class:`StyledDoc`.

The second reader into the same model. Its job is not to be a good HTML parser
— ``lxml.html`` is that, and it is already a dependency of the validation stack
— but to translate HTML's vocabulary into the *evidence* Cycle 1 defined, so
that a document delivered as HTML reaches the same hierarchy, the same
segmentation and the same rendering as the DOCX of the same text. Everything
downstream reads ``StyledPara.style``, ``outline_level``, ``num_id``/``ilvl``
and ``indent_direct``; those four fields are what this module has to produce
faithfully, and the rest of HTML is noise to be discarded without trace.

Three deliberate correspondences with :mod:`.docx_reader`, each of which would
be a silent divergence if it were dropped:

1. **All text goes through** :func:`~.docx_reader.normalize_text`. NFC plus
   whitespace collapse. HTML's source formatting is arbitrary — an author may
   wrap a sentence across five indented lines — so without the collapse the
   HTML and DOCX renderings of one paragraph would differ by whitespace alone,
   and the conservation invariant compares text.
2. **Adjacent identically-formatted inlines are merged** by reusing
   :func:`~.docx_reader._merge_inlines` rather than reimplementing it. HTML
   splits runs on nesting (``<b>a<i>b</i>c</b>``) exactly as Word splits them
   on spell-check state, and a reimplementation would drift the moment either
   changed.
3. **``<br>`` splits the paragraph**, as Cycle 1's soft break does (amendment
   A-1.2). Leaving the halves joined would merge a heading with the text under
   it — the same failure the DOCX reader avoids.

**Robustness is a requirement, not a courtesy** (plan §9.1). HTML in a legacy
corpus is malformed by default: unclosed tags, stray ``<``, mojibake, fragments
with no ``<html>`` at all. ``lxml``'s HTML parser recovers from all of it, and
this module never turns a recovery into an exception. :class:`HtmlReadError` is
raised for exactly one class of problem — the file could not be *read* — and
never for anything the markup itself contains. A document that parses to
nothing yields a ``StyledDoc`` with zero blocks, which the pipeline already
handles.

**What is deliberately not inferred.** No attempt is made to read a ``<p>``
with a bold first line as a heading, or a ``<div class="titulo">`` as a
section. That is Cycle 4's job, working from the evidence this module records;
guessing here would put the same judgement in two places and make the HTML and
DOCX paths disagree about which one won. Invariant #8 — no fabricated
structure — applies to readers first.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from lxml import etree, html as lxml_html

from .docx_reader import _merge_inlines, normalize_text
from .styled import (
    Inline,
    StyledCell,
    StyledDoc,
    StyledPara,
    StyledRow,
    StyledTable,
)

__all__ = [
    "HtmlReadError",
    "read_html",
]

#: Tags whose subtree carries no document text at all. Dropped whole, including
#: their tails' *content* but not the tail text itself, which belongs to the
#: parent's flow (``<p>a<script>x</script>b</p>`` is the paragraph "a b").
_INVISIBLE = frozenset({"script", "style", "head", "meta", "link", "title", "noscript"})

#: Struck-through text. Dropped when ``drop_strikethrough`` is set, for parity
#: with the DOCX reader's ``<w:strike>`` handling.
_STRUCK = frozenset({"s", "strike", "del"})

#: Inline formatting → the ``Inline`` flag it sets. ``<u>`` is absent on
#: purpose: ``Inline`` has no underline field, because Cycle 1 found underline
#: carried no discriminating signal in the corpus, and adding a field here
#: would change a frozen shape five packages read.
_BOLD = frozenset({"b", "strong", "th"})
_ITALIC = frozenset({"i", "em", "cite", "dfn", "var"})

#: Block-level elements that become a paragraph of their own when they carry
#: their own text. ``<li>`` is handled separately (it carries list numbering);
#: ``<td>`` is handled separately (it lives inside a table).
_BLOCK = frozenset(
    {
        "p",
        "div",
        "blockquote",
        "pre",
        "dd",
        "dt",
        "figcaption",
        "address",
        "section",
        "article",
        "aside",
        "header",
        "footer",
        "main",
        "nav",
        "center",
    }
)

_HEADINGS = {f"h{n}": n for n in range(1, 7)}

#: Word's default tab stop, and the unit CSS lengths are converted into.
#: 1pt = 20 twips by definition (a twip is a twentieth of a point).
_TWIPS_PER_POINT = 20.0

#: CSS absolute-length units, expressed in points. ``em``/``ex``/``%`` are
#: deliberately absent: they are relative to a font size this module does not
#: know, and guessing one would fabricate a measurement.
_UNITS_IN_POINTS = {
    "pt": 1.0,
    "pc": 12.0,          # 1 pica = 12 points
    "in": 72.0,
    "cm": 72.0 / 2.54,
    "mm": 7.2 / 2.54,
    "px": 0.75,          # the CSS reference pixel: 96px = 1in
    "q": 72.0 / 101.6,   # quarter-millimetre
}


class HtmlReadError(Exception):
    """Raised when an HTML *source* cannot be read.

    A sibling of :class:`~.docx_reader.DocxReadError`, not a subclass. The two
    describe unrelated failures of unrelated libraries, and a caller that means
    "any ingestion failure" should say so by catching both — an inheritance
    relationship here would let ``except DocxReadError`` silently swallow an
    HTML problem, which is precisely the confusion the CLI's exit codes exist
    to avoid.

    Note what this is *not* raised for: malformed markup. ``lxml`` recovers
    from unclosed tags, stray ``<`` and truncated documents, and this module
    keeps that guarantee — bad HTML produces a possibly-empty ``StyledDoc``,
    never an exception.
    """


def _looks_like_markup(text: str) -> bool:
    """True when a ``str`` should be treated as HTML rather than as a path.

    Only consulted after the filesystem has been asked, so this decides the
    genuinely ambiguous case: a string that names no existing file. Containing
    ``<`` is the test — a path may not contain one on any platform we target,
    and markup essentially always does. A string with neither is treated as a
    path so that a typo'd filename gets "no such file" rather than silently
    parsing as a one-word document.

    The empty string is markup, not a path: an empty document is one of §9.1's
    degenerate cases and must yield an empty ``StyledDoc``, whereas ``Path("")``
    resolves to the current directory and would report "not a file: .".
    """
    return "<" in text or not text.strip()


def _read_source(source: Any) -> tuple[bytes | str, str | None]:
    """Resolve the ``source`` argument into (markup, default source name).

    ``Path`` always means the filesystem. A ``str`` means the filesystem when
    it names an existing file, and markup otherwise (see
    :func:`_looks_like_markup`). ``bytes`` is always markup — a caller holding
    bytes has already done the reading.
    """
    if isinstance(source, Path):
        return _read_file(source), source.name
    if isinstance(source, bytes):
        return source, None
    if isinstance(source, str):
        # Ask the filesystem first: a real file wins over any heuristic. The
        # probe itself can raise on absurd input (an embedded NUL, a path past
        # the OS limit), which means "not a path", not "crash".
        try:
            candidate = Path(source)
            is_file = candidate.is_file()
        except (OSError, ValueError):
            is_file = False
            candidate = None
        if is_file and candidate is not None:
            return _read_file(candidate), candidate.name
        if _looks_like_markup(source):
            return source, None
        return _read_file(Path(source)), Path(source).name
    raise HtmlReadError(f"cannot read {type(source).__name__} as HTML")


def _read_file(path: Path) -> bytes:
    """Read a file as bytes, leaving the encoding to :func:`_parse`.

    Bytes rather than text on purpose: HTML declares its own encoding in a
    ``<meta charset>`` or an XML declaration, and decoding here with a guess
    would override what the document says about itself. What to do when it
    says *nothing* is :func:`_parse`'s decision, and it is documented there.
    """
    if not path.exists():
        raise HtmlReadError(f"no such file: {path}")
    if path.is_dir():
        raise HtmlReadError(f"not a file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise HtmlReadError(f"cannot read {path.name}: {exc}") from exc


#: A ``<meta charset=X>``, a legacy ``<meta http-equiv ... charset=X>`` or an
#: XML declaration. Matched on the raw bytes, before any decoding, because
#: deciding *how* to decode is exactly what this answers. ASCII-only by
#: construction: every spelling of the declaration is ASCII whatever the
#: document's real encoding turns out to be.
_ENCODING_DECLARATION = re.compile(
    rb"(?:<\?xml[^>]*encoding|<meta[^>]*charset)\s*=\s*[\"']?\s*([A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)

#: Tried in order when the document declares nothing, or declares something
#: Python does not know. UTF-8 first because every document in this corpus is
#: UTF-8 and lxml's own fallback (latin-1, the HTML4 default) turns ``SEÇÃO``
#: into ``SEÃÃO``; latin-1 last because it cannot fail, so a legacy file is
#: read with mojibake rather than refused outright.
_ENCODING_FALLBACKS: tuple[str, ...] = ("utf-8", "latin-1")


def _declared_encoding(markup: bytes) -> str | None:
    """What the document says it is encoded in, if it says anything.

    Only the head is inspected: a declaration must appear early to be valid,
    and a ``charset=`` inside body text is not one.
    """
    match = _ENCODING_DECLARATION.search(markup[:4096])
    if match is None:
        return None
    return match.group(1).decode("ascii", "replace")


#: An XML declaration at the very start of a document. Stripped before the HTML
#: parser sees it — see :func:`_parse`.
_XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)


def _decode(markup: bytes) -> str:
    """Bytes to text, honouring the declaration and never raising.

    Decoding here rather than handing bytes to ``lxml`` is deliberate, and was
    measured. Given bytes, lxml decodes *lazily*: a byte the chosen encoding
    cannot represent surfaces as a ``UnicodeDecodeError`` from ``element.text``
    deep inside the walk, long after the reader could say which file was at
    fault — and that breaks this module's contract that malformed input yields
    a document rather than an exception.

    Deciding up front makes the choice explicit, testable, and unable to fail:
    the last candidate is latin-1, which maps every possible byte.
    """
    candidates: list[str] = []
    declared = _declared_encoding(markup)
    if declared:
        candidates.append(declared)
    candidates.extend(e for e in _ENCODING_FALLBACKS if e != declared)

    for encoding in candidates:
        try:
            return markup.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return markup.decode("latin-1", "replace")  # pragma: no cover - latin-1 total


def _parse(markup: bytes | str):
    """Parse markup into an element tree, recovering from anything.

    Returns ``None`` when the input holds no element at all — an empty string,
    pure whitespace, a bare comment. ``lxml`` signals that by raising, and an
    empty document is a legitimate input (§9.1's degenerate cases), so the
    exception is converted into "no tree" rather than propagated.
    """
    if isinstance(markup, str):
        stripped = markup.strip()
        if not stripped:
            return None
        payload: bytes | str = stripped
    else:
        if not markup.strip():
            return None
        payload = markup

    # Bytes become text here, once, by `_decode` — never lazily inside lxml.
    # A declaration wins; UTF-8 is assumed only when there is none, because
    # lxml's own fallback is latin-1 and every document in this corpus is
    # UTF-8. `txt_reader` resolves the same ambiguity the same way.
    if isinstance(payload, bytes):
        payload = _decode(payload)

    # An XML declaration on an HTML document (the XHTML era left plenty about)
    # makes lxml's HTML parser return an *empty* tree — not an error, just no
    # content, even for a fully wrapped page. Its encoding was already read off
    # the bytes above, so by here it carries no information and dropping it
    # costs nothing. Measured: without this, `<?xml ...?><p>x</p>` ingests as
    # zero blocks, which is text loss that nothing downstream could detect.
    payload = _XML_DECLARATION.sub("", payload, count=1).lstrip()
    if not payload:
        return None

    parser = lxml_html.HTMLParser(recover=True, remove_comments=True)
    try:
        # ``document_fromstring`` wraps a bare fragment in <html><body>, so a
        # snippet and a full page take the same code path below.
        return lxml_html.document_fromstring(payload, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return None


def _css_declarations(style: str | None) -> dict[str, str]:
    """The ``style`` attribute as a lowercased property → value mapping.

    Hand-rolled rather than pulled from ``cssselect``/``tinycss``: this needs
    two properties out of a syntax that a malformed document will violate, and
    a split on ``;`` and ``:`` degrades to "found nothing" on junk, which is
    the desired behaviour.
    """
    if not style:
        return {}
    out: dict[str, str] = {}
    for declaration in style.split(";"):
        name, separator, value = declaration.partition(":")
        if not separator:
            continue
        out[name.strip().lower()] = value.strip().lower()
    return out


def _length_in_twips(value: str | None) -> int | None:
    """A CSS absolute length as twips, or ``None`` if it is not one.

    Relative units are rejected rather than approximated (see
    :data:`_UNITS_IN_POINTS`). A bare ``0`` is accepted, since CSS lets a zero
    length omit its unit.
    """
    if not value:
        return None
    text = value.strip().lower()
    for unit, points in _UNITS_IN_POINTS.items():
        if text.endswith(unit):
            number = text[: -len(unit)].strip()
            try:
                return int(round(float(number) * points * _TWIPS_PER_POINT))
            except ValueError:
                return None
    try:
        # Unitless: only 0 is valid CSS, but tolerate any number as points
        # rather than dropping a measurement a hand-written document meant.
        return int(round(float(text) * _TWIPS_PER_POINT))
    except ValueError:
        return None


def _indent_of(element) -> int | None:
    """``indent_direct`` for one element, from its inline style.

    ``margin-left`` and ``padding-left`` both push text right and are used
    interchangeably by HTML authors, so they are summed; ``text-indent``
    contributes too, because Cycle 4's quotation guard reads the *displacement*
    of a block and a quotation styled with either one looks identical on the
    page. Returns ``None`` when nothing declares a displacement, matching the
    DOCX reader's "no direct ``w:ind``" — ``0`` and ``None`` are different
    claims and downstream distinguishes them.
    """
    declarations = _css_declarations(element.get("style"))
    total = 0
    found = False
    for prop in ("margin-left", "padding-left", "text-indent"):
        twips = _length_in_twips(declarations.get(prop))
        if twips is not None:
            total += twips
            found = True
    return total if found else None


class _Formatting:
    """The inline formatting in force at a point in the tree.

    A tiny immutable-by-convention record threaded down the walk. Kept as a
    class rather than a tuple so the ``with_`` calls read as what they are; the
    walk creates one per nested element, and there are never many.
    """

    __slots__ = ("bold", "italic", "sup", "sub", "href")

    def __init__(
        self,
        bold: bool = False,
        italic: bool = False,
        sup: bool = False,
        sub: bool = False,
        href: str | None = None,
    ) -> None:
        self.bold = bold
        self.italic = italic
        self.sup = sup
        self.sub = sub
        self.href = href

    def descend(self, tag: str, element) -> "_Formatting":
        """The formatting in force inside ``element``.

        Flags accumulate — nested ``<b><i>`` is both — and ``href`` is taken
        from the innermost anchor, which is the one a reader would follow.
        """
        bold = self.bold or tag in _BOLD
        italic = self.italic or tag in _ITALIC
        sup = self.sup or tag == "sup"
        sub = self.sub or tag == "sub"
        href = self.href
        if tag == "a":
            target = element.get("href")
            if target:
                href = target
        return _Formatting(bold, italic, sup, sub, href)

    def inline(self, text: str) -> Inline:
        return Inline(
            text=text,
            bold=self.bold,
            italic=self.italic,
            sup=self.sup,
            sub=self.sub,
            href=self.href,
        )


class _Builder:
    """Walks the tree once, emitting blocks in document order.

    A class rather than a recursive function returning lists because the walk
    has genuine state: the currently-open paragraph (which ``<br>`` closes and
    reopens), the list-nesting depth, and the running block index. Threading
    four accumulators through a recursion would say the same thing less
    clearly.

    The central invariant is that *text always lands in the open paragraph*.
    Encountering a block-level child flushes what is open before descending, so
    ``<div>loose text<p>a</p>more</div>`` yields three paragraphs in the order
    they appear rather than one concatenation — HTML permits that shape and
    legacy exports produce it constantly.
    """

    def __init__(self, *, drop_strikethrough: bool) -> None:
        self.drop_strikethrough = drop_strikethrough
        self.blocks: list[StyledPara | StyledTable] = []
        self._open: list[Inline] = []
        self._props: dict[str, Any] = {}
        #: One entry per enclosing <ol>/<ul>, holding its ``num_id``.
        self._lists: list[str] = []
        self._ol_count = 0
        self._ul_count = 0

    # -- paragraph accumulation ------------------------------------------

    def _flush(self, *, keep_empty: bool = False) -> None:
        """Close the open paragraph, if it has anything worth keeping.

        ``keep_empty`` is passed for elements that *are* a paragraph in the
        source — an explicit ``<p></p>``, an empty ``<li>``. Cycle 1 keeps
        empty DOCX paragraphs deliberately (``StyledPara.is_empty``'s
        docstring: segmentation may read a blank line as a separator, and
        dropping it at ingestion is irreversible), so HTML keeps them too.
        Structural wrappers with no text of their own — a ``<div>`` that only
        holds other blocks — are *not* paragraphs and flush to nothing.
        """
        inlines = _merge_inlines(self._open)
        self._open = []
        props = self._props
        self._props = {}
        if not inlines and not keep_empty:
            return
        self.blocks.append(
            StyledPara(inlines=inlines, index=len(self.blocks), **props)
        )

    def _set_props(self, props: dict[str, Any]) -> None:
        """Attach paragraph properties to whatever paragraph is currently open.

        Only the first setter wins: when ``<h1>`` contains a ``<div>``, the
        heading's properties describe the text, and the inner wrapper must not
        overwrite them with ``Normal``.
        """
        if not self._props:
            self._props = props

    def _text(self, text: str | None, formatting: _Formatting) -> None:
        if not text:
            return
        normalised = normalize_text(text)
        if not normalised:
            return
        self._open.append(formatting.inline(normalised))

    # -- the walk ---------------------------------------------------------

    def walk(self, element, formatting: _Formatting) -> None:
        """Emit every block under ``element``, in document order."""
        for child in element:
            tag = _tag_of(child)
            if tag is None:
                # A comment or processing instruction. ``remove_comments``
                # already dropped most; a PI's tail is still document text.
                self._text(child.tail, formatting)
                continue
            self._handle(child, tag, formatting)
            # Tail text belongs to the *parent's* flow, not the child's, so it
            # is emitted with the parent's formatting after the child closes.
            self._text(child.tail, formatting)

    def _handle(self, element, tag: str, formatting: _Formatting) -> None:
        if tag in _INVISIBLE:
            return
        if tag in _STRUCK and self.drop_strikethrough:
            return
        if tag == "br":
            # A soft break: close the line and start another, exactly as
            # ``<w:br/>`` does in Cycle 1 (A-1.2).
            self._flush()
            return
        if tag in _HEADINGS:
            self._block(element, self._heading_props(element, tag), formatting)
            return
        if tag == "table":
            self._table(element, formatting)
            return
        if tag in ("ol", "ul"):
            self._list(element, tag, formatting)
            return
        if tag == "li":
            self._list_item(element, formatting)
            return
        if tag in ("tr", "td", "th", "thead", "tbody", "tfoot", "caption"):
            # Reached only outside a <table> — malformed markup. Treat the cell
            # as a paragraph rather than losing its text.
            self._block(element, self._normal_props(element), formatting)
            return
        if tag in _BLOCK:
            self._block(element, self._normal_props(element), formatting)
            return
        # Anything else — <span>, <b>, <a>, <font>, an unknown custom tag — is
        # inline: it contributes formatting and text to the open paragraph.
        inner = formatting.descend(tag, element)
        self._text(element.text, inner)
        self.walk(element, inner)

    def _block(self, element, props: dict[str, Any], formatting: _Formatting) -> None:
        """A block-level element: flush what is open, then collect its text."""
        self._flush()
        self._set_props(props)
        before = len(self.blocks)
        self._text(element.text, formatting)
        self.walk(element, formatting)
        # An explicit empty ``<p></p>`` is a real blank paragraph — Cycle 1
        # keeps empty DOCX paragraphs for the same reason, and segmentation may
        # read one as a separator. A ``<div>`` that merely wrapped other blocks
        # is not a paragraph, and neither is a ``<p>`` whose content was itself
        # block-level and has already flushed: emitting a blank paragraph for
        # either would invent a separator the source does not contain.
        self._flush(
            keep_empty=_tag_of(element) == "p" and len(self.blocks) == before
        )

    def _heading_props(self, element, tag: str) -> dict[str, Any]:
        """``<hN>`` → the style name and outline level Cycle 4 reads.

        ``outline_level = N - 1`` is Word's own convention (``Heading 1`` has
        ``w:outlineLvl w:val="0"``), which is what makes an HTML heading and a
        DOCX heading indistinguishable to :mod:`..hierarchy`.
        """
        level = _HEADINGS[tag]
        return {
            "style": f"Heading {level}",
            "style_id": f"Heading{level}",
            "outline_level": level - 1,
            **self._indent_props(element),
        }

    def _normal_props(self, element) -> dict[str, Any]:
        """Body text. ``"Normal"`` is the name Word's default style resolves to
        in :meth:`StyleResolver.name`, so both readers report the same string
        for "no particular style"."""
        return {"style": "Normal", **self._indent_props(element)}

    @staticmethod
    def _indent_props(element) -> dict[str, Any]:
        indent = _indent_of(element)
        if indent is None:
            return {}
        # ``indent_effective`` mirrors the DOCX reader: a direct value is the
        # effective one; there is no style sheet here to inherit from.
        return {"indent_direct": indent, "indent_effective": indent}

    # -- lists ------------------------------------------------------------

    def _list(self, element, tag: str, formatting: _Formatting) -> None:
        """``<ol>``/``<ul>`` → a Word-style numbering id for its items.

        The ids are ``ol1``, ``ul1``, ``ol2``… — one per list *encountered*, so
        two sibling lists get different ``num_id``s. ``hierarchy/tree.py``
        groups contiguous runs of one ``num_id`` into a list and reads ``ilvl``
        for nesting, so this is exactly the shape it already understands; a
        shared id would fuse two adjacent lists into one.
        """
        self._flush()
        if tag == "ol":
            self._ol_count += 1
            num_id = f"ol{self._ol_count}"
        else:
            self._ul_count += 1
            num_id = f"ul{self._ul_count}"
        self._lists.append(num_id)
        try:
            self._text(element.text, formatting)
            self.walk(element, formatting)
        finally:
            self._lists.pop()
        self._flush()

    def _list_item(self, element, formatting: _Formatting) -> None:
        """``<li>`` → a paragraph carrying ``num_id`` and its nesting depth.

        A nested list inside the item flushes the item's own text first, so
        ``<li>a<ol><li>b</li></ol></li>`` yields "a" at ``ilvl=0`` and "b" at
        ``ilvl=1`` rather than "a b" at one level.
        """
        self._flush()
        props: dict[str, Any] = {"style": "Normal"}
        if self._lists:
            props["num_id"] = self._lists[-1]
            props["ilvl"] = len(self._lists) - 1
        else:
            # An <li> outside any list — malformed, but its text is real.
            props["ilvl"] = 0
        props.update(self._indent_props(element))
        self._set_props(props)
        before = len(self.blocks)
        self._text(element.text, formatting)
        self.walk(element, formatting)
        # ``keep_empty`` only when the item emitted nothing at all: a genuinely
        # empty ``<li></li>`` is a real (if blank) item, but an item whose text
        # was already flushed by a nested list must not leave a second, empty
        # paragraph behind it.
        self._flush(keep_empty=len(self.blocks) == before)

    # -- tables -----------------------------------------------------------

    def _table(self, element, formatting: _Formatting) -> None:
        """``<table>`` → :class:`StyledTable`.

        Rows are collected by descendant search rather than by direct children:
        ``<thead>``/``<tbody>``/``<tfoot>`` are optional in the source and
        supplied by the parser when absent, so ``element.iter`` is the only way
        to get the same answer for both spellings. Nested tables are read as
        part of the outer cell's text — LexML has no nested-table shape, and
        flattening loses less than dropping.
        """
        self._flush()
        rows: list[StyledRow] = []
        for tr in element.iter("tr"):
            cells: list[StyledCell] = []
            for cell in tr:
                if _tag_of(cell) not in ("td", "th"):
                    continue
                cells.append(StyledCell(paras=self._cell(cell, formatting)))
            rows.append(StyledRow(cells=tuple(cells)))
        self.blocks.append(StyledTable(rows=tuple(rows), index=len(self.blocks)))

    def _cell(self, cell, formatting: _Formatting) -> tuple[StyledPara, ...]:
        """One ``<td>``'s paragraphs, built by a nested builder.

        A separate builder keeps the cell's blocks out of the document's own
        block list and gives its paragraphs cell-local indices — which is what
        the DOCX reader does, where ``_read_paragraph`` is called with
        ``len(paras)`` inside the cell.
        """
        inner = _Builder(drop_strikethrough=self.drop_strikethrough)
        tag = _tag_of(cell) or "td"
        inner._set_props({"style": "Normal", **self._indent_props(cell)})
        inner._text(cell.text, formatting.descend(tag, cell))
        inner.walk(cell, formatting.descend(tag, cell))
        inner._flush()
        # A table cell holds paragraphs, never a nested StyledTable: a nested
        # <table> flattened into the cell's own paragraphs above.
        return tuple(b for b in inner.blocks if isinstance(b, StyledPara))


def _tag_of(element) -> str | None:
    """The element's lowercased tag, or ``None`` for comments and PIs."""
    tag = element.tag
    if not isinstance(tag, str):
        return None
    # Namespaced tags appear in XHTML served as XML: '{ns}p' → 'p'.
    if "}" in tag:
        tag = tag.rsplit("}", 1)[1]
    return tag.lower()


def _reindex(blocks: Iterable[StyledPara | StyledTable]) -> tuple[Any, ...]:
    """Assign dense ``index`` values ``0..n-1`` in document order.

    The same final pass the DOCX reader runs, and for the same reason: indices
    are assigned after every split and drop, so they address the blocks that
    actually exist rather than the source elements they came from. Downstream
    code indexes spans by these numbers.
    """
    out: list[StyledPara | StyledTable] = []
    for position, block in enumerate(blocks):
        if isinstance(block, StyledTable):
            out.append(StyledTable(rows=block.rows, index=position))
        else:
            out.append(
                StyledPara(
                    inlines=block.inlines,
                    style=block.style,
                    style_id=block.style_id,
                    outline_level=block.outline_level,
                    num_id=block.num_id,
                    ilvl=block.ilvl,
                    indent_direct=block.indent_direct,
                    indent_effective=block.indent_effective,
                    first_line=block.first_line,
                    hanging=block.hanging,
                    alignment=block.alignment,
                    index=position,
                )
            )
    return tuple(out)


def read_html(
    source: Any,
    *,
    source_name: str | None = None,
    drop_strikethrough: bool = True,
) -> StyledDoc:
    """Read HTML into a :class:`StyledDoc`.

    Args:
        source: a :class:`~pathlib.Path`, a ``str`` naming an existing file, or
            raw markup as ``str`` or ``bytes``. A ``str`` that names no file
            and contains ``<`` is treated as markup; one that contains neither
            is treated as a path, so a mistyped filename reports itself rather
            than parsing as a one-word document.
        source_name: the name recorded in ``StyledDoc.source``. Defaults to the
            file's basename when reading a file, and to ``None`` for markup
            passed in directly — goldens must never encode a checkout path.
        drop_strikethrough: discard ``<s>``/``<strike>``/``<del>`` content, as
            :func:`~.docx_reader.read_docx` discards struck runs. Set ``False``
            to retain it.

    Returns:
        A ``StyledDoc`` whose blocks carry dense indices ``0..n-1``. Malformed
        markup, and markup holding no elements, yield a document with as many
        blocks as could be recovered — possibly zero.

    Raises:
        HtmlReadError: the source is a file that is missing, is a directory, or
            cannot be read; or it is of a type this reader does not accept.
            Never raised for the *content* of the markup.
    """
    markup, default_name = _read_source(source)
    tree = _parse(markup)
    if tree is None:
        return StyledDoc(blocks=(), source=source_name or default_name)

    builder = _Builder(drop_strikethrough=drop_strikethrough)
    body = tree.find("body")
    root = body if body is not None else tree
    builder._text(root.text, _Formatting())
    builder.walk(root, _Formatting())
    builder._flush()

    return StyledDoc(
        blocks=_reindex(builder.blocks),
        source=source_name or default_name,
    )
