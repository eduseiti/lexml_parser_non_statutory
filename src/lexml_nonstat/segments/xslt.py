"""The XSLT reference path — plan §6.2.

The Python API is the primary path; these stylesheets are the *reference*
implementation, and their value is precisely that they are a second one. A
stylesheet that shipped without ever being compared with the API would be
documentation, not evidence; here the two are run over the same documents and
their rows are required to match.

Saxon is optional (``pip install 'lexml-nonstat[xslt]'``). Absent it, callers
get :class:`SaxonUnavailable` with something actionable in the message and the
tests skip with that reason — never a traceback, and never a silent pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "COMMUNITY_STYLESHEET",
    "HAVE_SAXON",
    "STYLESHEETS",
    "SaxonUnavailable",
    "rows",
    "saxon_reason",
    "stylesheet_for",
    "transform",
]


class SaxonUnavailable(RuntimeError):
    """Raised when an XSLT path is asked for and Saxon is not installed."""


def _probe() -> str | None:
    try:
        import saxonche  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on the environment
        return f"saxonche is not importable ({exc}); install lexml-nonstat[xslt]"
    return None


#: Why Saxon is unusable, or ``None`` when it is fine. A *reason*, not a bool,
#: because a skip that cannot say why is a skip nobody investigates.
saxon_reason = _probe()

#: Whether the XSLT path can run at all.
HAVE_SAXON = saxon_reason is None

_HERE = Path(__file__).resolve().parent

#: emitter → its reference stylesheet.
STYLESHEETS: dict[str, Path] = {
    "generico": _HERE / "stylesheets" / "segment_generico.xsl",
    "generico-aninhado": _HERE / "stylesheets" / "segment_generico_aninhado.xsl",
    "norma": _HERE / "stylesheets" / "segment_norma.xsl",
}

#: The community stylesheet §6.2 asks Cycle 7 to probe. Not one of ours — it
#: lives in ``scripts/`` and is vendored from the LexML community.
# `_HERE` is `src/lexml_nonstat/segments`, so the repo root is three up. This
#: resolves only in a source checkout, which is where the probe is run; an
#: installed package has no `scripts/`, and the probe test skips accordingly.
COMMUNITY_STYLESHEET = (
    _HERE.parents[2] / "scripts" / "GeraCSVporArtigoPorAgrupador.xsl"
)


def stylesheet_for(emitter: str) -> Path:
    """The reference stylesheet for ``emitter``."""
    try:
        return STYLESHEETS[emitter]
    except KeyError:
        raise ValueError(
            f"no stylesheet for emitter {emitter!r}; "
            f"expected one of {', '.join(sorted(STYLESHEETS))}"
        ) from None


def transform(document: Any, stylesheet: Any) -> str:
    """Run ``stylesheet`` over ``document``, returning its text output.

    ``document`` may be an element, an XML string, or a path.
    """
    if not HAVE_SAXON:
        raise SaxonUnavailable(saxon_reason or "saxonche is unavailable")

    from lxml import etree
    from saxonche import PySaxonProcessor

    if hasattr(document, "tag"):
        text = etree.tostring(document, encoding="unicode")
    elif isinstance(document, bytes):
        text = document.decode("utf-8")
    elif isinstance(document, str) and document.lstrip().startswith("<"):
        text = document
    else:
        text = Path(document).read_text(encoding="utf-8")

    with PySaxonProcessor(license=False) as proc:
        executable = proc.new_xslt30_processor().compile_stylesheet(
            stylesheet_file=str(stylesheet)
        )
        node = proc.parse_xml(xml_text=text)
        return executable.transform_to_string(xdm_node=node) or ""


def rows(document: Any, stylesheet: Any) -> tuple[tuple[str, ...], ...]:
    """``transform`` parsed as CSV — header first, then one tuple per row."""
    import csv
    import io

    output = transform(document, stylesheet)
    return tuple(tuple(row) for row in csv.reader(io.StringIO(output)) if row)
