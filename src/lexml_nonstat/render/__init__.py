"""Rendering: a :class:`~..model.document.DocumentModel` becomes LexML XML.

    from lexml_nonstat.render import render_generico_from_docx
    bundle = render_generico_from_docx("samples/pn_cst_38_19801031.docx")
    print(bundle.to_xml_string())

Plan §5 defines three renderings of two routes. ``generico`` (flat) is here and
is the default; ``generico-aninhado`` (nested, Cycle 5b) is
here too and is opt-in behind the §2.11 capability probe; ``norma`` + ``anexo``
(Cycle 6) follow. They differ only in how they *write* the model —
amendment A-R.7's point that a route is not an emitter — which is why
:mod:`.common` and :mod:`.ids` are shared rather than duplicated.
"""

from .common import (
    LEXML_NS,
    NSMAP,
    XLINK_NS,
    agrupamento,
    all_ids,
    back_region,
    el,
    front_region,
    leaf_text,
    leaf_texts,
    local_name,
    render_inlines,
    render_list,
    render_node,
    render_para,
    render_table,
    to_xml_string,
    words,
)
from .generico import (
    AUXILIARY_NOMES,
    RenderedDocument,
    Scope,
    render_generico,
    render_generico_from_docx,
)
from .generico_aninhado import (
    EMITTER,
    EMPTY_BLOCO,
    ORDER_BLOCO,
    render_generico_aninhado,
    render_generico_aninhado_from_docx,
)
from .ids import (
    ID_RE,
    IdAllocator,
    compose,
    is_valid_id,
    missing_prefixes,
    path_prefixes,
)

__all__ = [
    "AUXILIARY_NOMES",
    "EMITTER",
    "EMPTY_BLOCO",
    "ID_RE",
    "LEXML_NS",
    "NSMAP",
    "XLINK_NS",
    "IdAllocator",
    "ORDER_BLOCO",
    "RenderedDocument",
    "Scope",
    "agrupamento",
    "all_ids",
    "back_region",
    "compose",
    "el",
    "front_region",
    "is_valid_id",
    "leaf_text",
    "leaf_texts",
    "local_name",
    "missing_prefixes",
    "path_prefixes",
    "render_generico",
    "render_generico_aninhado",
    "render_generico_aninhado_from_docx",
    "render_generico_from_docx",
    "render_inlines",
    "render_list",
    "render_node",
    "render_para",
    "render_table",
    "to_xml_string",
    "words",
]
