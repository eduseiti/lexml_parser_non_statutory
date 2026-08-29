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

from .anexo import (
    ANEXO_FORMS,
    anexo_urn,
    anexos_element,
    lexml_root,
    render_anexo,
)
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
from .norma import (
    ARTIGO_ID_RE,
    Artigo,
    Caput,
    DispositivoIds,
    Inciso,
    Paragrafo,
    back_residue,
    build_articulacao,
    render_articulacao,
    render_norma,
    render_norma_checked,
    render_norma_from_docx,
    render_statutory,
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
    "ANEXO_FORMS",
    "ARTIGO_ID_RE",
    "AUXILIARY_NOMES",
    "EMITTER",
    "EMPTY_BLOCO",
    "ID_RE",
    "LEXML_NS",
    "NSMAP",
    "XLINK_NS",
    "Artigo",
    "Caput",
    "DispositivoIds",
    "IdAllocator",
    "Inciso",
    "ORDER_BLOCO",
    "Paragrafo",
    "RenderedDocument",
    "Scope",
    "agrupamento",
    "all_ids",
    "anexo_urn",
    "anexos_element",
    "back_region",
    "back_residue",
    "build_articulacao",
    "compose",
    "el",
    "front_region",
    "is_valid_id",
    "leaf_text",
    "leaf_texts",
    "lexml_root",
    "local_name",
    "missing_prefixes",
    "path_prefixes",
    "render_anexo",
    "render_articulacao",
    "render_generico",
    "render_generico_aninhado",
    "render_generico_aninhado_from_docx",
    "render_generico_from_docx",
    "render_norma",
    "render_norma_checked",
    "render_norma_from_docx",
    "render_inlines",
    "render_list",
    "render_node",
    "render_para",
    "render_statutory",
    "render_table",
    "to_xml_string",
    "words",
]
