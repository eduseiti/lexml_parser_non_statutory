"""``python3 -m lexml_nonstat`` — the unified CLI (plan §8, Cycle 8).

    PYTHONPATH=src python3 -m lexml_nonstat parse samples/pn_cst_38_19801031.docx

This form and the ``lexml-nonstat`` console script installed by
``[project.scripts]`` reach the same :func:`~.cli.main`. The module form is the
one the test suite and the documentation use, because the package is
deliberately *not* installed (``tests/conftest.py`` puts ``src/`` on
``sys.path``) and the suite must run straight from a clean checkout.

Each package keeps its own ``__main__`` debug view — ``lexml_nonstat.ingest``,
``.model``, ``.hierarchy``, ``.routing``, ``.segment``, ``.segments`` and
``.validate``. They are not superseded: they show one stage in the detail that
stage's author wanted, and this CLI delegates to the same library functions
rather than replacing them.
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
