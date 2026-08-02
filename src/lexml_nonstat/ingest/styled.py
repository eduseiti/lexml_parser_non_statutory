"""The ingestion model: a document reduced to styled blocks.

``StyledDoc`` is deliberately format-agnostic. The DOCX reader builds one, and
Cycle 8's HTML and plain-text readers will build the same shape, so everything
downstream — segmentation, hierarchy inference, routing — is written once
against this model rather than three times against three parsers.

Nothing here imports ``python-docx``: these are plain dataclasses, so a reader
for another format costs a module, not a dependency.

The model keeps *evidence*, not conclusions. A paragraph records the style it
carries, the numbering it belongs to and how far it is indented; it does not
decide whether it is a heading or a quotation. Those judgements belong to later
cycles, which need the raw signals intact to make them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Union


@dataclass(frozen=True)
class Inline:
    """A run of text with uniform formatting.

    Mirrors plan §3.1's ``Inline``. There is no ``strike`` flag: struck runs are
    dropped at ingestion (following the reference parser), so a surviving inline
    is by definition live text.
    """

    text: str
    bold: bool = False
    italic: bool = False
    sup: bool = False
    sub: bool = False
    href: str | None = None

    @property
    def is_plain(self) -> bool:
        """True when the run carries no formatting worth preserving."""
        return not (self.bold or self.italic or self.sup or self.sub or self.href)

    def to_dict(self) -> dict[str, Any]:
        """Compact form: default-valued fields are omitted.

        Goldens are read by humans reviewing a behaviour change. Emitting
        ``"bold": false`` on every run of a 450-paragraph document buries the
        signal in noise.
        """
        data: dict[str, Any] = {"text": self.text}
        if self.bold:
            data["bold"] = True
        if self.italic:
            data["italic"] = True
        if self.sup:
            data["sup"] = True
        if self.sub:
            data["sub"] = True
        if self.href is not None:
            data["href"] = self.href
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Inline":
        return cls(
            text=data["text"],
            bold=data.get("bold", False),
            italic=data.get("italic", False),
            sup=data.get("sup", False),
            sub=data.get("sub", False),
            href=data.get("href"),
        )


@dataclass(frozen=True)
class StyledPara:
    """One paragraph, with every signal later cycles need to classify it.

    Two indentation fields, not one — this is load-bearing and was settled by
    measurement, not preference. In ``parecer_93`` the ``Normal`` style declares
    ``w:ind/@w:left="2909"`` while the 21 quoted articles carry a *direct*
    ``w:ind`` of 2880–2930 and ordinary body text carries a direct 7–60. Resolve
    inheritance and the quotation signal vanishes (modal 2909 against a quote
    band of 2908); read only direct values and 226 paragraphs report nothing.
    Cycle 4's quotation guard needs whichever discriminates, so both are kept.
    """

    inlines: tuple[Inline, ...] = ()
    style: str | None = None
    style_id: str | None = None
    outline_level: int | None = None
    num_id: str | None = None
    ilvl: int | None = None
    indent_direct: int | None = None
    indent_effective: int = 0
    first_line: int | None = None
    hanging: int | None = None
    alignment: str | None = None
    index: int = 0

    @property
    def text(self) -> str:
        """The paragraph's text, formatting discarded."""
        return "".join(i.text for i in self.inlines)

    @property
    def is_empty(self) -> bool:
        """True for blank paragraphs.

        Kept rather than dropped: Cycle 3 may read blank lines as front/back
        matter separators, and discarding them at ingestion is irreversible.
        """
        return not self.text.strip()

    @property
    def is_listed(self) -> bool:
        """True when Word considers this paragraph part of a numbered list."""
        return self.num_id is not None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": "para",
            "index": self.index,
            "inlines": [i.to_dict() for i in self.inlines],
        }
        for name in (
            "style",
            "style_id",
            "outline_level",
            "num_id",
            "ilvl",
            "indent_direct",
            "first_line",
            "hanging",
            "alignment",
        ):
            value = getattr(self, name)
            if value is not None:
                data[name] = value
        # Always emitted: 0 is a meaningful measurement here, not an absence.
        data["indent_effective"] = self.indent_effective
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyledPara":
        return cls(
            inlines=tuple(Inline.from_dict(i) for i in data.get("inlines", ())),
            style=data.get("style"),
            style_id=data.get("style_id"),
            outline_level=data.get("outline_level"),
            num_id=data.get("num_id"),
            ilvl=data.get("ilvl"),
            indent_direct=data.get("indent_direct"),
            indent_effective=data.get("indent_effective", 0),
            first_line=data.get("first_line"),
            hanging=data.get("hanging"),
            alignment=data.get("alignment"),
            index=data.get("index", 0),
        )


@dataclass(frozen=True)
class StyledCell:
    """One table cell. Holds paragraphs; LexML restricts cells to inline
    content (plan §2.2), but that is the emitter's problem, not ingestion's."""

    paras: tuple[StyledPara, ...] = ()

    @property
    def text(self) -> str:
        return " ".join(p.text for p in self.paras if not p.is_empty)

    def to_dict(self) -> dict[str, Any]:
        return {"paras": [p.to_dict() for p in self.paras]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyledCell":
        return cls(paras=tuple(StyledPara.from_dict(p) for p in data.get("paras", ())))


@dataclass(frozen=True)
class StyledRow:
    cells: tuple[StyledCell, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"cells": [c.to_dict() for c in self.cells]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyledRow":
        return cls(cells=tuple(StyledCell.from_dict(c) for c in data.get("cells", ())))


@dataclass(frozen=True)
class StyledTable:
    rows: tuple[StyledRow, ...] = ()
    index: int = 0

    @property
    def shape(self) -> tuple[int, int]:
        """(rows, columns) — columns taken from the widest row."""
        return (len(self.rows), max((len(r.cells) for r in self.rows), default=0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "table",
            "index": self.index,
            "rows": [r.to_dict() for r in self.rows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyledTable":
        return cls(
            rows=tuple(StyledRow.from_dict(r) for r in data.get("rows", ())),
            index=data.get("index", 0),
        )


Block = Union[StyledPara, StyledTable]


@dataclass(frozen=True)
class StyledDoc:
    """A whole document as an ordered sequence of blocks.

    Order matters and is preserved from the source. ``python-docx`` exposes
    ``.paragraphs`` and ``.tables`` as separate flat lists, which loses the
    interleaving — and every sample with a table has it *mid-document*
    (block 4 of 21 in ``REsp_1306393``, 10 of 397 in ``sumula_stj_125``), never
    appended at the end. Segmentation would misplace it.
    """

    blocks: tuple[Block, ...] = ()
    source: str | None = None

    def __iter__(self) -> Iterator[Block]:
        return iter(self.blocks)

    def __len__(self) -> int:
        return len(self.blocks)

    @property
    def paragraphs(self) -> tuple[StyledPara, ...]:
        return tuple(b for b in self.blocks if isinstance(b, StyledPara))

    @property
    def tables(self) -> tuple[StyledTable, ...]:
        return tuple(b for b in self.blocks if isinstance(b, StyledTable))

    @property
    def text(self) -> str:
        """All paragraph text, one block per line. Table text is excluded —
        use ``StyledCell.text`` for that."""
        return "\n".join(p.text for p in self.paragraphs)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.source is not None:
            data["source"] = self.source
        data["blocks"] = [b.to_dict() for b in self.blocks]
        return data

    def to_json(self, *, indent: int = 2) -> str:
        """Golden-file form: stable, readable, and machine-independent.

        ``ensure_ascii=False`` keeps Portuguese legible in a diff; ``source``
        is a bare filename so goldens never encode a checkout path.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyledDoc":
        blocks: list[Block] = []
        for raw in data.get("blocks", ()):
            kind = raw.get("kind")
            if kind == "table":
                blocks.append(StyledTable.from_dict(raw))
            elif kind == "para":
                blocks.append(StyledPara.from_dict(raw))
            else:
                raise ValueError(f"unknown block kind {kind!r}")
        return cls(blocks=tuple(blocks), source=data.get("source"))

    @classmethod
    def from_json(cls, text: str) -> "StyledDoc":
        import json

        return cls.from_dict(json.loads(text))
