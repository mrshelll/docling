"""Los hijos de una región clave-valor deben quedar en orden de lectura fila-mayor.

Muchos formularios se generan escribiendo el content stream **columna por
columna**: primero todas las etiquetas de una columna y después todos sus
valores. `LayoutPostprocessor` ordenaba los hijos de un `KEY_VALUE_REGION` con
`_sort_clusters(mode="id")`, es decir por índice de celda, así que preservaba ese
orden columna-mayor. El resultado es que la relación etiqueta↔valor solo se puede
recuperar contando posiciones:

    esperado:  "Tasa" / "14.45%" / "Plazo" / "090"
    obtenido:  "Tasa" / "Plazo" / "14.45%" / "090"

Para un consumidor de RAG eso significa emparejar una etiqueta con el valor
equivocado, que en un documento financiero es peor que no extraer nada.

Nota sobre las coordenadas del fixture: la primera fila tiene `t=100.4` y
`t=100.0` a propósito (desalineación de 0.4pt, habitual entre fuentes de distinto
tamaño en una misma fila). Un orden estricto por `(t, l)` colocaría la celda de
`t=100.4` antes de toda la fila anterior, así que el agrupado por filas necesita
tolerancia. Si alguien "arregla" el fixture alineando esos valores, dejaría de
cubrir ese caso.
"""

from docling_core.types.doc import CoordOrigin, DocItemLabel, Size
from docling_core.types.doc.page import BoundingRectangle, TextCell

from docling.datamodel.base_models import BoundingBox, Cluster
from docling.utils.layout_postprocessor import (
    LayoutPostprocessor,
    SpatialClusterIndex,
)


def _text_cell(index: int, text: str, left: float, top: float) -> TextCell:
    right, bottom = left + 40.0, top + 8.0
    return TextCell(
        index=index,
        rect=BoundingRectangle(
            r_x0=left,
            r_y0=top,
            r_x1=right,
            r_y1=top,
            r_x2=right,
            r_y2=bottom,
            r_x3=left,
            r_y3=bottom,
            coord_origin=CoordOrigin.TOPLEFT,
        ),
        text=text,
        orig=text,
        from_ocr=False,
    )


def _child(cid: int, cell: TextCell) -> Cluster:
    bbox = cell.rect.to_bounding_box()
    return Cluster(
        id=cid,
        label=DocItemLabel.TEXT,
        bbox=BoundingBox(l=bbox.l, t=bbox.t, r=bbox.r, b=bbox.b),
        confidence=0.8,
        cells=[cell],
    )


# Rejilla etiqueta|valor|etiqueta|valor de 2x2 pares, tal y como la escribe el
# generador del PDF: columna 1 completa, luego columna 2, luego 3, luego 4.
# El índice de celda es el orden del content stream; (left, top) la geometría.
_GRID = [
    # (índice, texto,      left,  top)
    (0, "Tasa", 40.0, 100.4),  # col 1, fila 1  (0.4pt más abajo, a propósito)
    (1, "Plazo", 40.0, 120.0),  # col 1, fila 2
    (2, "14.45%", 150.0, 100.0),  # col 2, fila 1
    (3, "090", 150.0, 120.0),  # col 2, fila 2
    (4, "Moneda", 300.0, 100.0),  # col 3, fila 1
    (5, "Cuotas", 300.0, 120.0),  # col 3, fila 2
    (6, "COP", 420.0, 100.0),  # col 4, fila 1
    (7, "049", 420.0, 120.0),  # col 4, fila 2
]

EXPECTED_READING_ORDER = [
    "Tasa",
    "14.45%",
    "Moneda",
    "COP",
    "Plazo",
    "090",
    "Cuotas",
    "049",
]


def _processor_with_key_value_grid(
    label: DocItemLabel = DocItemLabel.KEY_VALUE_REGION,
) -> tuple[LayoutPostprocessor, Cluster]:
    children = [
        _child(cid=100 + index, cell=_text_cell(index, text, left, top))
        for index, text, left, top in _GRID
    ]
    region = Cluster(
        id=1,
        label=label,
        bbox=BoundingBox(l=30.0, t=95.0, r=470.0, b=135.0),
        confidence=0.7,
    )

    processor = object.__new__(LayoutPostprocessor)
    processor.regular_clusters = children
    processor.special_clusters = [region]
    processor.page_size = Size(width=612.0, height=792.0)
    processor.options = type("_Opts", (), {"skip_cell_assignment": False})()
    processor.regular_index = SpatialClusterIndex(children)
    is_picture = label == DocItemLabel.PICTURE
    processor.picture_index = SpatialClusterIndex([region] if is_picture else [])
    processor.wrapper_index = SpatialClusterIndex([] if is_picture else [region])

    return processor, region


def _child_texts(region: Cluster) -> list[str]:
    return [cell.text for child in region.children for cell in child.cells]


def test_key_value_region_children_are_in_row_major_reading_order() -> None:
    """Cada etiqueta debe quedar seguida de su propio valor."""
    processor, region = _processor_with_key_value_grid()

    processor._process_special_clusters()

    assert _child_texts(region) == EXPECTED_READING_ORDER, (
        "los hijos siguen en el orden columna-mayor del content stream, "
        "así que el par etiqueta↔valor solo se recupera contando posiciones"
    )


def test_key_value_region_pairs_each_label_with_its_own_value() -> None:
    """El par concreto que motivó el arreglo: 'Tasa' junto a '14.45%'."""
    processor, region = _processor_with_key_value_grid()

    processor._process_special_clusters()

    texts = _child_texts(region)
    assert texts.index("14.45%") == texts.index("Tasa") + 1
    assert texts.index("090") == texts.index("Plazo") + 1


def test_picture_children_keep_native_cell_order() -> None:
    """El reordenado es solo para regiones clave-valor: PICTURE no se toca."""
    processor, region = _processor_with_key_value_grid(label=DocItemLabel.PICTURE)

    processor._process_special_clusters()

    assert _child_texts(region) == [text for _, text, _, _ in _GRID]
