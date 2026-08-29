"""CSV and JSONL segment output — plan §6.2, Cycle 7.

Two writers, two entirely different jobs, and the tests split the same way.

**CSV is an interoperability contract.** §6.2's reference stylesheets exist so a
consumer can get segment rows out of a LexML file with `xsltproc` and no Python
at all. That only works if both paths emit the *same* columns in the same order
— which is what makes "the XSLT rows equal the Python rows" a test
(`test_segments_xslt.py`) rather than a hope. This module owns the half of that
contract that does not need Saxon: `CSV_COLUMNS` is read out of the stylesheets
themselves. Hardcoding the six names a second time here would make the test
pass by construction on the day someone changed a column in one place — a
second copy of a constant is not a check on the first.

**JSONL is a lossless serialisation.** Its job is that `from_dict(json.loads(
line))` gives back the record, for every field of every segment, so the goldens
can be diffed and a downstream consumer can rebuild `Segment` objects without
re-parsing XML. `Segment.to_dict` omits empty optional fields (house style), so
"lossless" here means *round-trip equality*, not *every key present* — and
equality on a frozen dataclass compares all thirteen fields including the ones
that were omitted, which is exactly the property worth asserting.

Two cross-cutting invariants (§9.2) run through both:

* **Determinism.** No dict ordering, no locale, no timestamps, `\\n` written
  explicitly rather than left to the platform. The goldens are byte-compared, so
  a writer that varied between runs would make them unmaintainable.
* **Escaping honesty.** The corpus is Portuguese and the documents are legal
  prose, so accented characters, commas and quotation marks are not edge cases —
  they are the normal content of a `Texto` column. A writer that mangled them
  would still produce a well-formed file, which is why both are asserted on real
  corpus text and not only on a synthetic fixture.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pytest

from lexml_nonstat.ingest import read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.segments import (
    BREADCRUMB_SEPARATOR,
    CSV_COLUMNS,
    Segment,
    csv_row,
    segments,
    to_csv,
    to_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

#: Where the reference stylesheets live — package data, spec decision D-2.
STYLESHEET_DIR = REPO_ROOT / "src" / "lexml_nonstat" / "segments" / "stylesheets"
STYLESHEETS = sorted(STYLESHEET_DIR.glob("*.xsl"))

#: A sample with real structure, real accents and a real annex, so the
#: "on corpus text" assertions have something to bite on.
RICH_SAMPLE = "pn_cst_38_19801031"
ANNEX_SAMPLE = "port_mf_277_20180607"

assert len(SAMPLES) == 15, SAMPLES

_SEGMENTS: dict[str, tuple[Segment, ...]] = {}


def segments_for(name: str) -> tuple[Segment, ...]:
    """One sample's segments, built once per session — the caching idiom."""
    if name not in _SEGMENTS:
        path = SAMPLES_DIR / f"{name}.docx"
        model = build_model(read_docx(path), filename=path.name)
        _SEGMENTS[name] = segments(model)
    return _SEGMENTS[name]


# --------------------------------------------------------------------------
# T-25 — the column contract, read from the stylesheets rather than restated
# --------------------------------------------------------------------------

#: The header an XSL emits: a literal `<xsl:text>` whose content is the comma
#: separated names followed by a newline character reference. Matching on the
#: *shape* rather than on the names is the point — this must not contain a
#: second copy of the answer.
_HEADER_TEXT = re.compile(
    r"<xsl:text>([^<>&]*?(?:,[^<>&]*?)+)&#10;</xsl:text>",
)


def stylesheet_header(path: Path) -> tuple[str, ...]:
    """The CSV header one stylesheet writes, parsed out of its source.

    Deliberately parsed rather than transcribed. If this function returned a
    constant, T-25 would compare `CSV_COLUMNS` against a copy of itself and
    would keep passing after someone edited a stylesheet — which is the exact
    drift the test exists to catch.
    """
    text = path.read_text(encoding="utf-8")
    matches = _HEADER_TEXT.findall(text)
    assert matches, f"{path.name}: no CSV header line found in the stylesheet"
    # The header is the first such literal — everything after it is a data row.
    return tuple(matches[0].split(","))


def test_the_stylesheet_header_parser_finds_exactly_one_header() -> None:
    """The parser above is doing real work, on all three stylesheets.

    Without this, a regex that silently matched nothing would make T-25's
    assertion vacuous by never running — the classic way a "read it from the
    source" test degrades into a no-op.
    """
    assert len(STYLESHEETS) == 3, [p.name for p in STYLESHEETS]
    for path in STYLESHEETS:
        header = stylesheet_header(path)
        assert len(header) == 6, f"{path.name}: parsed {header!r}"
        assert all(field and not field.isspace() for field in header)


@pytest.mark.parametrize(
    "stylesheet", STYLESHEETS, ids=lambda p: p.stem
)
def test_csv_header_matches_the_stylesheet_columns(stylesheet: Path) -> None:
    """T-25. `CSV_COLUMNS` is exactly what each `.xsl` writes — §6.2.

    Order included, not just membership: a CSV consumer reads by position, so
    two files with the same six names in different orders are not
    interchangeable. All three stylesheets are checked, because the `norma` one
    adapts the community stylesheet and is the likeliest to drift.
    """
    assert stylesheet_header(stylesheet) == CSV_COLUMNS, (
        f"{stylesheet.name} and CSV_COLUMNS disagree; the XSLT and Python "
        "paths would no longer be comparable row for row"
    )


def test_all_three_stylesheets_agree_with_each_other() -> None:
    """And with one another — stated separately so a failure localises.

    If all three drifted together, the test above fails three times and this
    one passes, which says "someone changed `CSV_COLUMNS`". If one drifted,
    both fail, which says "someone changed a stylesheet". Two different repairs.
    """
    headers = {p.name: stylesheet_header(p) for p in STYLESHEETS}
    assert len(set(headers.values())) == 1, headers


def test_the_written_header_is_the_declared_one() -> None:
    """`to_csv` writes `CSV_COLUMNS`, and `header=False` writes no header.

    The constant being right is worth nothing if the writer does not use it,
    and the `header=False` half matters because that is how a caller appends
    one sample's rows to another's.
    """
    rows = segments_for(RICH_SAMPLE)
    with_header = to_csv(rows)
    assert next(csv.reader(io.StringIO(with_header))) == list(CSV_COLUMNS)

    without = to_csv(rows, header=False)
    assert with_header == ",".join(CSV_COLUMNS) + "\n" + without


# --------------------------------------------------------------------------
# T-26 — the CSV survives the characters legal prose is actually made of
# --------------------------------------------------------------------------


def test_csv_quotes_commas_and_quotes() -> None:
    """T-26. A segment whose text carries `,` and `"` round-trips.

    Both characters at once, in the same field, plus a comma in the *rótulo*
    field as well — because a numbered rótulo such as `1,2` is ordinary in this
    corpus and a writer that only escaped the long text column would still
    corrupt the row. Verified by reading the output back with `csv.reader`
    rather than by eyeballing the escaped string, so the assertion is "a
    standard CSV parser recovers the values", which is the actual contract.
    """
    segment = Segment(
        urn="urn:lex:br:federal:parecer:1980-10-31;38!pp1_agr4",
        id="pp1_agr4",
        kind="secao",
        level=1,
        label="1,2 -",
        heading='Da "isenção", em geral',
        breadcrumb=("A, com vírgula", 'B com "aspas"'),
        text='O contribuinte disse: "não há, no caso, isenção".',
        path=(1,),
    )

    text = to_csv([segment])
    rows = list(csv.reader(io.StringIO(text)))

    assert rows[0] == list(CSV_COLUMNS)
    assert len(rows) == 2, "one segment must produce exactly one data row"

    tipo, nivel, rotulo, breadcrumb, texto, urn = rows[1]
    assert tipo == "secao"
    assert nivel == "1"
    assert rotulo == "1,2 -"
    assert breadcrumb == 'A, com vírgula | B com "aspas"'
    assert texto == segment.full_text
    assert '"não há, no caso, isenção"' in texto
    assert urn == segment.urn

    # And the parsed row is the writer's own row, so the escaping is reversible
    # rather than merely well-formed.
    assert tuple(rows[1]) == csv_row(segment)


def test_csv_of_the_corpus_reparses_row_for_row() -> None:
    """The same claim, on every segment of a real sample rather than a fixture.

    A hand-built segment proves the escaping works when it is exercised; the
    corpus proves it is exercised. `pn_cst_38`'s prose carries commas, quotation
    marks and accented characters throughout.
    """
    rows = segments_for(RICH_SAMPLE)
    parsed = list(csv.reader(io.StringIO(to_csv(rows))))
    assert parsed[0] == list(CSV_COLUMNS)
    assert len(parsed) == len(rows) + 1
    for segment, row in zip(rows, parsed[1:]):
        assert tuple(row) == csv_row(segment)


def test_csv_rows_never_contain_a_bare_newline() -> None:
    """One line per segment, so `wc -l` and a line-oriented reader agree.

    A section's own text is a single joined string, so an embedded newline would
    be a bug rather than data — but it would be an *invisible* bug, producing a
    file that `csv.reader` handles and every line-oriented tool misreads.
    Asserted across the whole corpus, annex included.
    """
    for name in SAMPLES:
        text = to_csv(segments_for(name))
        assert text.endswith("\n"), name
        assert "\r" not in text, f"{name}: a platform line ending leaked in"
        assert len(text.splitlines()) == len(segments_for(name)) + 1, name


def test_breadcrumb_uses_the_declared_separator_and_drops_empty_entries() -> None:
    """`' | '` joins the breadcrumb, and a titleless ancestor is not a `||`.

    Spec decision D-4 keeps a titleless ancestor in `Segment.breadcrumb` as
    `""`, so depth is recorded honestly. The CSV is a *display* column, and
    `csv_row` drops the empties rather than emitting `A |  | C`. Both halves are
    deliberate and they pull in opposite directions, so both are pinned here.
    """
    segment = Segment(
        breadcrumb=("A", "", "C"), text="t", path=(1, 1, 1), kind="secao", level=3
    )
    assert BREADCRUMB_SEPARATOR == " | "
    assert csv_row(segment)[3] == "A | C"
    # The record itself still remembers the gap — D-4's point.
    assert segment.breadcrumb == ("A", "", "C")
    assert segment.depth == 3


def test_csv_texto_column_is_the_cumulative_reading() -> None:
    """`Texto` carries `full_text`, not own-text — R-5 and §6.2's `descendant::p`.

    The own/cumulative split is the load-bearing decision of the whole package,
    and the two writers land on opposite sides of it *on purpose*: CSV matches
    the reference format, JSONL keeps the record. Asserting the CSV side here
    means a change to `csv_row` cannot quietly turn the reference format into
    something the stylesheets do not produce.
    """
    rows = segments_for(RICH_SAMPLE)
    parents = [s for s in rows if s.descendant_texts]
    assert parents, "premise failed: no segment in this sample has descendants"
    for segment in parents:
        assert csv_row(segment)[4] == segment.full_text
        assert csv_row(segment)[4] != segment.text, (
            "a parent's cumulative text must differ from its own text, or the "
            "distinction R-5 exists for is not being written"
        )


# --------------------------------------------------------------------------
# T-27 — JSONL is lossless
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_jsonl_one_object_per_line_and_reparses(name: str) -> None:
    """T-27. Every segment of every sample survives `to_jsonl` → `from_dict`.

    Equality on a frozen dataclass compares **all** fields, including the
    optional ones `to_dict` omits when empty — so this catches both a field
    dropped on the way out and a field defaulted wrongly on the way back in. A
    key-by-key comparison of the dicts would catch neither, because both sides
    would be missing the same key.

    Run over all 15 samples rather than one, because the fields most likely to
    be lost are the ones a single document may not exercise: `echoed_label`
    appears only on the statutory route, `path` only on body sections,
    `document` only once annexes are in play.
    """
    original = segments_for(name)
    lines = to_jsonl(original).splitlines()

    assert len(lines) == len(original), f"{name}: one object per line"

    for line, segment in zip(lines, original):
        data = json.loads(line)
        assert isinstance(data, dict), f"{name}: a line is not a JSON object"
        assert Segment.from_dict(data) == segment, (
            f"{name}: segment {segment.id!r} did not survive the JSONL round-trip"
        )


def test_jsonl_exercises_every_optional_field_somewhere_in_the_corpus() -> None:
    """T-27's premise: the omitted-when-empty fields are not all always empty.

    `to_dict` drops `label`, `echoed_label`, `heading`, `breadcrumb`, `path`,
    `document` and `descendant_texts` when they are empty. If none of the 15
    samples ever populated one of them, T-27 would be silently untested on that
    field. This checks each is populated by *something* in the corpus, so the
    round-trip claim covers the whole record.
    """
    seen: set[str] = set()
    for name in SAMPLES:
        for segment in segments_for(name):
            seen.update(segment.to_dict())
    missing = {
        "urn",
        "id",
        "kind",
        "level",
        "label",
        "heading",
        "breadcrumb",
        "text",
        "route",
        "path",
        "order",
        "document",
        "descendant_texts",
    } - seen
    assert not missing, f"never exercised anywhere in the corpus: {sorted(missing)}"

    # `echoed_label` is A-6.4's statutory-only flag, so it is exercised on the
    # norma route rather than on the default `generico` one — checked directly
    # rather than left out of the sweep above.
    from lexml_nonstat.render import render_norma

    path = SAMPLES_DIR / f"{ANNEX_SAMPLE}.docx"
    model = build_model(read_docx(path), filename=path.name)
    norma = segments(render_norma(model))
    assert any(s.echoed_label for s in norma), "A-6.4's flag is never set"
    for segment in norma:
        assert Segment.from_dict(json.loads(segment.to_json())) == segment


def test_jsonl_ends_every_line_including_the_last() -> None:
    """A trailing newline, and no blank line — the JSONL convention.

    `to_jsonl` appends `\\n` per record rather than joining with it, so the file
    concatenates: appending an annex's segments to a primary's produces a valid
    file rather than one glued-together line. Asserted because "join with
    newline" is the natural thing to write and would silently break that.
    """
    text = to_jsonl(segments_for(RICH_SAMPLE))
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert "\r" not in text
    lines = text.split("\n")
    assert lines[-1] == "", "exactly one trailing newline"
    assert all(line.strip() for line in lines[:-1]), "no blank lines"

    # Concatenation really is safe: two files appended parse as one.
    other = to_jsonl(segments_for(ANNEX_SAMPLE))
    combined = (text + other).splitlines()
    assert len(combined) == len(segments_for(RICH_SAMPLE)) + len(
        segments_for(ANNEX_SAMPLE)
    )
    for line in combined:
        json.loads(line)


def test_jsonl_of_an_empty_sequence_is_empty() -> None:
    """No segments, no bytes — not a lone newline, not a header.

    JSONL has no header, so an empty document must produce a zero-byte file;
    anything else would parse as one malformed record.
    """
    assert to_jsonl([]) == ""
    # CSV, by contrast, still writes its header — the formats differ here and
    # both behaviours are deliberate.
    assert to_csv([]) == ",".join(CSV_COLUMNS) + "\n"
    assert to_csv([], header=False) == ""


# --------------------------------------------------------------------------
# T-28 — determinism, §9.2
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_writers_are_deterministic(name: str) -> None:
    """T-28. Two runs of each writer are byte-identical — §9.2.

    Not a formality: `to_jsonl` serialises a dict per record, and `json.dumps`
    with `sort_keys=False` preserves insertion order — which is deterministic
    only because `to_dict` builds the dict in a fixed sequence. A refactor that
    built it from a set, or from `dataclasses.asdict` under a different Python,
    would break here and nowhere else. The `segments` goldens are byte-compared,
    so this failing means they cannot be maintained at all.
    """
    original = segments_for(name)
    assert to_csv(original) == to_csv(original), f"{name}: CSV varies between runs"
    assert to_jsonl(original) == to_jsonl(original), f"{name}: JSONL varies"


def test_writers_are_deterministic_across_independently_built_models() -> None:
    """And across two *separate* `build_model` runs, not just two writer calls.

    The test above holds the segments fixed and varies only the writer, which
    would pass even if the model pipeline were nondeterministic. This rebuilds
    the document from the DOCX a second time, so the whole chain is covered —
    the form determinism has to take to be worth anything to a golden.
    """
    path = SAMPLES_DIR / f"{RICH_SAMPLE}.docx"
    first = segments(build_model(read_docx(path), filename=path.name))
    second = segments(build_model(read_docx(path), filename=path.name))
    assert to_jsonl(first) == to_jsonl(second)
    assert to_csv(first) == to_csv(second)


def test_writers_write_to_a_stream_exactly_what_they_return() -> None:
    """The `stream=` argument is a convenience, not a second code path.

    Both writers return the text *and* optionally write it. Two ways of
    producing the same bytes is two places to diverge, so the identity is
    asserted rather than assumed — and the return value is checked to be the
    full text even when a stream was given, which is what lets a caller do both.
    """
    rows = segments_for(RICH_SAMPLE)
    for writer in (to_csv, to_jsonl):
        buffer = io.StringIO()
        returned = writer(rows, buffer)
        assert buffer.getvalue() == returned
        assert returned == writer(rows)


# --------------------------------------------------------------------------
# T-29 — UTF-8, unescaped
# --------------------------------------------------------------------------


def test_jsonl_is_utf8_and_not_escaped() -> None:
    """T-29. Portuguese text appears literally, never as `\\uXXXX`.

    `json.dumps` defaults to `ensure_ascii=True`, which is a real trap for this
    corpus: the output would still be valid JSON, would still reparse to equal
    segments, and would still be deterministic — T-27 and T-28 would both pass —
    while every golden became an unreadable wall of escapes and every `grep` for
    a Portuguese word failed. Nothing else in the suite would notice.

    So this asserts both directions: the accented characters are present as
    themselves, and no `\\u` escape appears anywhere in the file.
    """
    text = to_jsonl(segments_for(RICH_SAMPLE))

    assert "\\u" not in text, "ensure_ascii=True has crept back in"
    assert any(ord(ch) > 127 for ch in text), (
        "premise failed: this sample carries no non-ASCII text to escape"
    )
    # The specific characters, named, so the failure says what was lost.
    for character in "ções":
        assert character in text or character.isascii()
    assert "ç" in text and "õ" in text or "ã" in text

    # It really is UTF-8 on the way to bytes, and survives the trip back.
    encoded = text.encode("utf-8")
    assert encoded.decode("utf-8") == text
    for line in encoded.decode("utf-8").splitlines():
        json.loads(line)


def test_csv_is_utf8_and_not_escaped() -> None:
    """The same claim for CSV, which has no escaping mechanism to hide behind.

    `csv` has no `ensure_ascii`, so the risk here is different: a caller opening
    the output file in the platform's default encoding. Asserting the returned
    text is already `str` with the accents intact is what documents that the
    writer hands back text, and the encoding choice belongs to whoever writes it
    to disk.
    """
    text = to_csv(segments_for(RICH_SAMPLE))
    assert "\\u" not in text
    assert any(ord(ch) > 127 for ch in text)
    assert text.encode("utf-8").decode("utf-8") == text


@pytest.mark.parametrize("name", SAMPLES)
def test_accented_source_words_reach_both_writers_intact(name: str) -> None:
    """Every accented word of every segment appears in both outputs, verbatim.

    Stated over the whole corpus and over both formats, because the two writers
    fail differently — JSONL by escaping, CSV by encoding — and a corpus-wide
    check is what turns "we looked at one sample" into a property.
    """
    rows = segments_for(name)
    accented = {
        word
        for segment in rows
        for word in segment.text.split()
        if any(ord(ch) > 127 for ch in word)
    }
    if not accented:
        pytest.skip(f"{name}: no accented words in this sample's segment text")

    jsonl = to_jsonl(rows)
    csv_text = to_csv(rows)
    for word in sorted(accented)[:40]:
        # `"` is the one character CSV doubles and JSON escapes; skip it rather
        # than assert a false claim about verbatim survival.
        if '"' in word or "\\" in word:
            continue
        assert word in csv_text, f"{name}: {word!r} missing from the CSV"
        assert word in jsonl, f"{name}: {word!r} missing from the JSONL"
