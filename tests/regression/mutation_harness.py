"""In-process mutation machinery — plan §8 Cycle 9, spec decisions N-1 and N-2.

A **mutation** is a named, reversible patch to one delivered behaviour, paired
with a **guard**: the project's own existing assertion that ought to go red
under it. The claim a mutation makes is not "this breaks something" — it is
"*this specific invariant* is actually defended", which is a much narrower and
much more useful statement.

Why this is a module and not a sweep
------------------------------------

Every cycle from 1 to 8e ran a hand-authored mutation sweep and threw it away.
That proves the suite bit *on the day someone looked*, which is the weakest
form the claim has: the guard a cycle-4 sweep exercised can be deleted in
cycle 7 and nothing notices. Committing the harness converts a one-off
inspection into a standing assertion, which is decision **N-1**.

Why nothing here writes to disk
-------------------------------

Decision **N-2**, and it is the single most dangerous thing this cycle builds.
A harness that rewrote `src/` and then crashed — an assertion inside the patch,
a `KeyboardInterrupt`, a guard that raised something unexpected — would leave
the working tree corrupt, with the corruption looking exactly like authored
code. Cycle 2 has a recorded incident of a source edit made against
instruction, and that is the precedent for treating this as non-negotiable
rather than merely tidy.

So every mutation is applied by rebinding an attribute on an already-imported
module object and restoring it in a `finally`. Three properties follow, and
each is asserted by the test module rather than assumed here:

* the repository is never written to, so a crash costs a process and nothing
  more;
* the restoration is unconditional, so an exception inside a guard cannot leak
  a patched function into a later test;
* `test_no_mutation_leaks` re-renders a canary against its committed golden
  after the whole module has run, which is what turns "we restore it" from a
  claim about this code into a measurement of the outcome.

The vacuity problem
-------------------

A harness that reported "caught" unconditionally would pass
`test_every_mutation_is_caught` forever while proving nothing at all — the
exact failure mode a mutation test exists to rule out elsewhere. Two things
guard against it. :func:`guard_fails` distinguishes an `AssertionError` (the
guard did its job) from an arbitrary exception (the mutation broke something
before reaching the assertion, which is a *different* and weaker finding), and
it reports which it saw. And :data:`NO_OP` is a mutation that changes nothing,
which the suite requires to **survive** — if the harness claims to catch that,
its verdicts are worthless.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

__all__ = [
    "Mutation",
    "MutationResult",
    "NO_OP",
    "guard_fails",
    "patched",
]


@contextlib.contextmanager
def patched(target: Any, name: str, value: Any) -> Iterator[None]:
    """Rebind ``target.name`` to ``value``, restoring it unconditionally.

    Deliberately not `monkeypatch`: a pytest fixture unwinds at *test* teardown,
    and several guards here need the mutation to be live for one render and gone
    for the next comparison **inside** a single test. A context manager makes the
    window explicit and closes it in a `finally`, which is what N-2 requires.

    `getattr` is read before the patch rather than assumed — a mutation naming an
    attribute that does not exist is a stale mutation, and it must fail loudly
    here rather than silently patch nothing and be reported as "survived".
    """
    if not hasattr(target, name):
        raise AttributeError(
            f"{getattr(target, '__name__', target)!r} has no attribute {name!r}: "
            "the mutation targets code that has moved, so it patches nothing and "
            "would be reported as a surviving mutation"
        )
    original = getattr(target, name)
    setattr(target, name, value)
    try:
        yield
    finally:
        setattr(target, name, original)


@dataclass(frozen=True)
class MutationResult:
    """What happened when one mutation met its guard.

    ``caught`` is the verdict; ``how`` says *why*, because the two ways a guard
    can go red are not equally good news. An `AssertionError` means the project's
    own assertion fired, which is the claim being made. Any other exception means
    the mutated code broke before the assertion was reached — the suite would
    still go red, so the invariant is not undefended, but the evidence is weaker
    and the report should say so rather than quietly bank it.
    """

    name: str
    caught: bool
    how: str = ""
    detail: str = ""

    def __str__(self) -> str:
        verdict = "caught" if self.caught else "SURVIVED"
        return f"{self.name}: {verdict} ({self.how})" if self.how else (
            f"{self.name}: {verdict}"
        )


@dataclass(frozen=True)
class Mutation:
    """One named, reversible patch and the guard that must reject it.

    Attributes:
        name: the stable id (``M-1`` … ``M-10``) the report and the spec use.
        attacks: the invariant or constraint in the plan's own numbering. This
            is the field that makes a surviving mutation *actionable* — it names
            what is unguarded, not merely that something is.
        guard: the module or assertion expected to fail, named for the report.
        apply: a zero-argument callable returning a context manager that holds
            the mutation open. A callable rather than a live context manager so
            one `Mutation` can be exercised repeatedly and independently.
        check: runs the guard under the mutation. Must raise `AssertionError`
            when the invariant is defended.
        constraint: for M-1…M-3 only, which of §5.4's three constraints this
            attacks — asserted by `test_constraint_mutations_are_declared` so
            amendment A-R.9's specific demand cannot be quietly dropped.
        requires_nested: whether the guard judges validity against
            `lexml-proposed/`, and so cannot run on a bare checkout (A-R.9).
    """

    name: str
    attacks: str
    guard: str
    apply: Callable[[], Any]
    check: Callable[[], None]
    constraint: int | None = None
    requires_nested: bool = False
    notes: str = field(default="")

    def run(self) -> MutationResult:
        """Apply the mutation, run the guard, and report whether it bit."""
        with self.apply():
            return guard_fails(self.name, self.check)


def guard_fails(name: str, check: Callable[[], None]) -> MutationResult:
    """Run ``check`` and report whether it rejected the mutated behaviour.

    The three outcomes are kept distinct on purpose:

    * `AssertionError` — the project's own assertion fired. The mutation is
      caught, and by the mechanism claimed.
    * any other exception — the mutated code broke before the assertion. Still
      caught (the suite goes red), but recorded as `raised` so a reader can see
      the evidence is indirect.
    * no exception — the mutation **survived**, which is a gap in the suite and
      is reported with the invariant's name by the caller.
    """
    try:
        check()
    except AssertionError as exc:
        return MutationResult(name, True, "assertion", str(exc).split("\n")[0][:200])
    except Exception as exc:  # noqa: BLE001 - the distinction is the point
        return MutationResult(
            name, True, f"raised {type(exc).__name__}", str(exc)[:200]
        )
    return MutationResult(name, False, "")


@contextlib.contextmanager
def _nothing() -> Iterator[None]:
    yield


#: A mutation that mutates nothing, required to **survive**.
#:
#: The harness's own control. `test_the_harness_itself_is_not_vacuous` asserts
#: this one is *not* caught, which is the only thing separating a harness that
#: discriminates from one that reports success unconditionally. Its `check` is a
#: real guard — the same conservation assertion M-4 attacks — so "survived" here
#: means the guard genuinely passed on unmutated code, not that nothing ran.
NO_OP = "M-0"
