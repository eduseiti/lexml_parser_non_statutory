"""Text conservation across the `generico` emitter — plan §9.2, invariant #2.

**All source text present exactly once, including across `Norma` + `Anexo`.**
Of the twelve cross-cutting invariants this is the one a reader can check by
eye and the one whose failure is least forgivable: a parser that silently drops
a paragraph publishes a document that says something different from the one it
was given. Validity can be re-checked by a schema, determinism by a rerun —
conservation can only be checked here.

It is also the invariant Cycle 5's reconciliation caught failing. Cycle 3's
`FrontMatter.span` / `BackMatter.span` are contiguous **hulls** (amendment
A-3.5) so that the parts partition the document, but its
`render_front_generico` / `render_back_generico` render the *named parts only*.
Measured over the corpus, **40 non-empty blocks in 6 samples** sit inside a hull
and inside no named part: `parecer_93`'s portal stamp, institutional banner and
`NUP:`/`INTERESSADOS:` lines (21), `pn_cst_38`'s `De acordo` and `Publique-se`
*between* its two signatures (7), `REsp_1306393`'s front matter (7),
`par_cosit_26`'s `Nota Normas:` disclaimer (3), and one block each in
`adn_cst_10` and `port_mf_454`. Spec decision D-6 (amendment A-5.1) is the fix —
render *regions*, not parts — and this module is what stops the hole reopening.
The tests are arithmetic over the whole hull rather than a checklist of part
names, so a run of unclaimed blocks in an unseen document is covered by
construction.

**The currency is a multiset of words, not of paragraphs.** A source paragraph
may legitimately become two elements — a `Bloco nome="rotulo"` carrying the
rótulo and a `<p>` carrying the prose that followed it on the same line — so
comparing whole paragraphs would report a false loss on every labelled section
in the corpus. Words survive that split; `collections.Counter` keeps
"exactly once" meaningful where a `set` would not.

Two things are deliberately outside the comparison, and both are stated as
assertions rather than left as assumptions:

* the emitter's own `Metadado` — `Metadata` *extracts* fields (a
  `MetadadoProprietario/campo` repeats the source's `JURISPRUDÊNCIA` list
  verbatim), so counting it would double every extracted field. Conservation is
  a property of the *body*, and `leaf_texts` never descends into `Metadado`;
* `Bloco nome="nivel"` — a depth marker whose value never appeared in the
  source. `test_structural_markers_add_no_source_text` proves it is the *only*
  such text, which is what makes "everything else came from the document" a
  measured claim rather than a comment.
"""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import pytest

from lexml_nonstat.ingest import StyledDoc, StyledPara, StyledTable, read_docx
from lexml_nonstat.model import build_model
from lexml_nonstat.render import (
    RenderedDocument,
    leaf_texts,
    local_name,
    render_generico,
    words,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"
SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))

LEX = "{http://www.lexml.gov.br/1.0}"

#: The one sample with an annex — the only corpus exercise of the §2.9 split.
ANNEX_SAMPLE = "port_mf_277_20180607"

assert len(SAMPLES) == 15, SAMPLES
assert ANNEX_SAMPLE in SAMPLES

_CACHE: dict[str, tuple[StyledDoc, RenderedDocument]] = {}


def rendered(name: str) -> tuple[StyledDoc, RenderedDocument]:
    """The source document and its rendering, built once per session."""
    if name not in _CACHE:
        path = SAMPLES_DIR / f"{name}.docx"
        doc = read_docx(path)
        _CACHE[name] = (doc, render_generico(build_model(doc, filename=path.name)))
    return _CACHE[name]


def source_texts(doc: StyledDoc) -> list[str]:
    """Every piece of text Cycle 1's reader saw.

    Paragraphs and table cells both, because a table is source text like any
    other: `REsp_1306393`'s front-matter table alone is 31 words that an
    extraction over paragraphs would call conserved while losing them.
    Cycle 1's model is `StyledTable.rows -> StyledRow.cells -> StyledCell.paras`,
    so a cell can hold several paragraphs even though LexML's `<td>` cannot.
    """
    out: list[str] = []
    for block in doc.blocks:
        if isinstance(block, StyledPara):
            if block.text.strip():
                out.append(block.text)
        elif isinstance(block, StyledTable):
            for row in block.rows:
                for cell in row.cells:
                    for para in cell.paras:
                        if para.text.strip():
                            out.append(para.text)
    return out


def source_words(doc: StyledDoc) -> Counter:
    return Counter(words(source_texts(doc)))


def emitted_words(bundle: RenderedDocument) -> Counter:
    """Rule B leaf text across the whole bundle, primary and annexes."""
    return Counter(words(bundle.texts))


def diff_message(name: str, source: Counter, emitted: Counter) -> str:
    """Both directions of the symmetric difference, capped so it stays readable.

    A bare count is not a finding. Naming the words — and which way they went —
    is usually enough to point at the block that was lost or repeated.
    """
    lost = source - emitted
    extra = emitted - source
    return (
        f"{name}: {sum(lost.values())} word(s) lost, "
        f"{sum(extra.values())} emitted without a source.\n"
        f"  lost (first 10):  {list(lost.items())[:10]}\n"
        f"  extra (first 10): {list(extra.items())[:10]}"
    )


# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_every_source_block_appears_exactly_once(name):
    """The emitted word multiset equals the source's, exactly.

    Invariant #2 in its strongest form: equality of multisets is simultaneously
    "nothing lost" and "nothing duplicated", and it is the assertion the 40-block
    hole failed. It is checked over the whole bundle, because on `port_mf_277`
    part of the answer is in a sibling document.
    """
    doc, bundle = rendered(name)
    source = source_words(doc)
    emitted = emitted_words(bundle)
    assert emitted == source, diff_message(name, source, emitted)


@pytest.mark.parametrize("name", SAMPLES)
def test_no_source_text_is_lost(name):
    """No *distinct* word appears on one side and not the other.

    Weaker than the multiset equality above and kept anyway, because the two
    fail differently and the difference is diagnostic: a set-level failure means
    a whole block went missing (a vocabulary the document alone had), while a
    multiset-only failure means a block was rendered the wrong number of times.
    Reading which of the two tests went red is the first step of the diagnosis.
    """
    doc, bundle = rendered(name)
    source = source_words(doc)
    emitted = emitted_words(bundle)

    missing = sorted(set(source) - set(emitted))
    unexpected = sorted(set(emitted) - set(source))
    assert not missing, f"{name}: source words never emitted: {missing[:10]}"
    assert not unexpected, f"{name}: emitted words with no source: {unexpected[:10]}"


def test_conservation_across_the_annex_split():
    """`port_mf_277`: primary ∪ annex == source, and the union is disjoint.

    Plan §9.2 says "including across `Norma` + `Anexo`", and reconciliation
    answer Q3 makes an annex a **sibling document** rather than a subtree
    (plan §2.9, matching the reference parser's `lei_5070_19660707.anexo1.xml`).
    That is the arrangement conservation is easiest to break in: neither file is
    wrong on its own, and a block that fell between them — or was defensively
    written into both — is invisible to any check that looks at one file.

    Addition is what makes this a disjointness test as well as a completeness
    one. If a word the source has once were emitted in both documents, the sum
    would exceed the source and the equality would fail; the anchors below then
    say *which* document each end of the split belongs to.
    """
    doc, bundle = rendered(ANNEX_SAMPLE)
    assert len(bundle.annexes) == 1

    primary = Counter(words(leaf_texts(bundle.primary)))
    annex = Counter(words(leaf_texts(bundle.annexes[0])))
    source = source_words(doc)

    assert primary + annex == source, diff_message(
        ANNEX_SAMPLE, source, primary + annex
    )
    assert primary and annex, "both documents must carry text"

    # Anchors: the epigraph belongs to the primary, the annex title to the annex.
    primary_texts = leaf_texts(bundle.primary)
    annex_texts = leaf_texts(bundle.annexes[0])
    assert any(t.startswith("Portaria MF") for t in primary_texts)
    assert "ANEXO ÚNICO" in annex_texts
    assert "ANEXO ÚNICO" not in primary_texts


@pytest.mark.parametrize("name", SAMPLES)
def test_structural_markers_add_no_source_text(name):
    """`Bloco nome="nivel"` is the only text the emitter invents.

    Spec decision D-7 writes the unified depth into the document as
    `<Bloco nome="nivel">2</Bloco>`: one of plan §5.1's three redundant depth
    channels, and also what keeps an `Agrupamento` from being empty, which
    `blocksreq` rejects. It is text that was never in the source, so it has to
    be excluded from extraction — and "excluded" is only trustworthy if it is
    also **exhaustive**. A future marker added the same way and forgotten here
    would inflate every conservation comparison in this module and make it
    permanently green.

    Two assertions, in the order that makes a failure readable:

    1. *completeness* — re-labelling the `nivel` blocks so `leaf_texts` picks
       them up makes the extraction account for **every** character under the
       `PartePrincipal`. Compared with whitespace squeezed out, because the
       comparison is about which text is reachable, not how it is spaced, and
       because an inline `<b>` legitimately splits a word's neighbourhood
       across text nodes;
    2. *exactness* — the words that re-labelling added are precisely the `nivel`
       values, so `leaf_texts` excludes those and nothing else.
    """
    _, bundle = rendered(name)

    for position, document in enumerate(bundle.documents):
        where = "primary" if position == 0 else f"annex {position}"
        for parte in document.iter(f"{LEX}PartePrincipal"):
            relabelled = copy.deepcopy(parte)
            markers: list[str] = []
            for node in relabelled.iter():
                if local_name(node.tag) == "Bloco" and node.get("nome") == "nivel":
                    markers.append(node.text or "")
                    node.set("nome", "rotulo")

            full = leaf_texts(relabelled)
            lean = leaf_texts(parte)

            assert squash("".join(relabelled.itertext())) == squash("".join(full)), (
                f"{name} ({where}): leaf extraction does not reach all text under "
                f"{parte.get('id')!r} — something is emitted that no test counts"
            )

            added = Counter(words(full)) - Counter(words(lean))
            assert added == Counter(words(markers)), (
                f"{name} ({where}): excluding Bloco nome='nivel' removes "
                f"{list(added.items())[:10]}, expected exactly the nivel values "
                f"{markers[:10]}"
            )

            for marker in markers:
                assert marker.strip().isdigit(), (
                    f"{name} ({where}): nivel value {marker!r} is not a depth"
                )


def squash(text: str) -> str:
    """All whitespace removed — the form in which two extractions are compared."""
    return "".join(text.split())
