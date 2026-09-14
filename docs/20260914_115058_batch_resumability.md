# Re-running `parse -o` over a populated directory — what actually happens

- **Date:** 2026-09-14
- **Cycle:** 5 of [`20260913_212337_corpus_233_hardening_plan.md`](../dev/20260913_212337_corpus_233_hardening_plan.md)
- **Tests:** `tests/regression/test_batch_robustness.py`, §G-4

Cycle 5's deliverable list asks for "a documented resumability story: re-running
over a directory that already holds output should be safe and cheap."

Measured against the code as delivered, **one half of that is true and the other
is not**, and this note states both rather than the flattering one. The
distinction matters to anyone running the 233-document corpus: it decides
whether an interrupted run can be restarted for free (it cannot) and whether
restarting it is *dangerous* (it is not).

## The measurement

Three consecutive `parse -o` runs of one sample into one directory:

| Run | Files | sha256 | Exit |
|---|---|---|---|
| 1 | 1 | `X` | 0 |
| 2 | 1 | `X` | 0 |
| 3 | 1 | `X` | 0 |

Three consecutive runs of **two sources that resolve to the same URN**:

```
run1: exit=0 count=2  [urn_…_1306393.xml, urn_…_1306393_b.xml]
run2: exit=0 count=2  [urn_…_1306393.xml, urn_…_1306393_b.xml]
run3: exit=0 count=2  [urn_…_1306393.xml, urn_…_1306393_b.xml]
```

And at full scale, two runs over all 15 samples: 16 files both times.

## Safe — yes

Three properties, each pinned by a test:

1. **Byte-identical output.** A re-run rewrites every file with exactly the
   bytes already there. This is invariant #4 (same input ⇒ byte-identical
   output) surviving the case where the destination is already populated.
   — `test_rerunning_a_batch_is_byte_identical`
2. **A stable file count.** The directory does not grow.
   — `test_rerunning_a_batch_does_not_change_the_file_count`
3. **No accumulating disambiguation suffixes.** This is the sharp case. Two
   sources sharing one URN write `<slug>.xml` and `<slug>_<stem>.xml`; if a
   re-run read that second file as itself a collision, names would grow
   `_b`, `_b_b`, `_b_b_b` on every run and the directory would fill with
   near-duplicates. It does not, because `_write_bundle`'s `taken` set is
   seeded **empty per invocation** and is a record of what *this run* has
   written — never a listing of what is on disk.
   — `test_rerunning_colliding_urns_does_not_grow_suffixes`

So an interrupted corpus run can be restarted over the same output directory
without corrupting anything it already produced.

## Cheap — no

Nothing is skipped. A second run reads, models, renders and validates every
document again, and writes every file again. There is no `--resume` flag, no
mtime comparison and no content check.

`test_a_rerun_re_renders_rather_than_skipping` pins this by counting calls to
`_render`: 20 documents produce 20 renders on the first run and 40 after the
second. **The test asserts the absence of an optimisation**, deliberately — if a
later cycle implements skip-on-existing, that test is the one that must change,
and having to change it is the signal that this documented contract moved.

The cost of a re-run is therefore the cost of the run. For the 233-document
corpus that is the full pipeline cost, not a delta.

## Why it was left this way

Implementing skip-on-existing was offered and declined for this cycle (Q-2). The
reasoning is that a cheap re-run needs a correct answer to "is the existing file
still what we would produce?", and the two easy answers are both wrong:

- **Skip if the file exists** is wrong whenever the parser has changed — which,
  across six cycles that each moved rendering or metadata, is most of the time.
  It would silently serve stale XML from a previous parser version, and the
  staleness would be invisible in the artifact.
- **Skip if the source is older than the output** keys on mtime, which says
  nothing about the parser's version and is destroyed by any checkout or copy.

A correct check keys on the parser's own output, which means rendering the
document — at which point the only saving is the file write, and the file write
is not what costs anything.

That is a real cycle's worth of design, with its own exit criteria, and Cycle 5's
deliverable is the *story*, not the flag. The honest statement is more useful
than a flag that looks like a guarantee and is not — the same reasoning
`_write_bundle` already applies to cross-process collision safety, which Cycle 2
documented as single-invocation rather than locking.

## If you need a cheap re-run today

Run one `parse` per output directory and merge afterwards, or filter the input
list before invoking — the shell already knows which outputs exist:

```bash
for f in corpus/*.docx; do
  out="out/$(basename "${f%.docx}").xml"
  [ -e "$out" ] || printf '%s\0' "$f"
done | xargs -0 -r python3 -m lexml_nonstat parse -o out/
```

This is not equivalent to a real resume — the output filename is the URN slug,
not the source stem, so the existence test above is approximate — which is
itself part of why the flag is not a one-line change.
