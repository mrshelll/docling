# SPDX-FileCopyrightText: DoTech Labs S.A.S
# SPDX-License-Identifier: MIT

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


# La misma rejilla en un documento de derecha a izquierda: el generador escribe
# la columna de más a la derecha primero, así que el índice de celda crece hacia
# la izquierda. Ordenar cada fila por 'x' ascendente invertiría la lectura.
_GRID_RTL = [
    # (índice, texto,     left,  top)
    (0, "valorA", 420.0, 100.0),  # fila 1, columna de la derecha (se escribe 1ª)
    (1, "etiqA", 300.0, 100.0),  # fila 1, columna de la izquierda
    (2, "valorB", 420.0, 120.0),  # fila 2, columna de la derecha
    (3, "etiqB", 300.0, 120.0),  # fila 2, columna de la izquierda
]

EXPECTED_RTL_READING_ORDER = ["valorA", "etiqA", "valorB", "etiqB"]


def _processor_with_grid(
    grid: list[tuple[int, str, float, float]],
    label: DocItemLabel = DocItemLabel.KEY_VALUE_REGION,
) -> tuple[LayoutPostprocessor, Cluster]:
    children = [
        _child(cid=100 + index, cell=_text_cell(index, text, left, top))
        for index, text, left, top in grid
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
    processor, region = _processor_with_grid(_GRID)

    processor._process_special_clusters()

    assert _child_texts(region) == EXPECTED_READING_ORDER, (
        "los hijos siguen en el orden columna-mayor del content stream, "
        "así que el par etiqueta↔valor solo se recupera contando posiciones"
    )


def test_key_value_region_pairs_each_label_with_its_own_value() -> None:
    """El par concreto que motivó el arreglo: 'Tasa' junto a '14.45%'."""
    processor, region = _processor_with_grid(_GRID)

    processor._process_special_clusters()

    texts = _child_texts(region)
    assert texts.index("14.45%") == texts.index("Tasa") + 1
    assert texts.index("090") == texts.index("Plazo") + 1


def test_key_value_region_respects_right_to_left_documents() -> None:
    """Agrupar por filas no debe imponer el sentido izquierda→derecha.

    En un documento RTL el generador escribe la columna de la derecha primero.
    El orden dentro de la fila lo marca el índice de celda nativo, no la 'x'.
    """
    processor, region = _processor_with_grid(_GRID_RTL)

    processor._process_special_clusters()

    assert _child_texts(region) == EXPECTED_RTL_READING_ORDER, (
        "se invirtió el orden de lectura de un documento de derecha a izquierda"
    )


def test_picture_children_keep_native_cell_order() -> None:
    """El reordenado es solo para regiones clave-valor: PICTURE no se toca."""
    processor, region = _processor_with_grid(_GRID, label=DocItemLabel.PICTURE)

    processor._process_special_clusters()

    assert _child_texts(region) == [text for _, text, _, _ in _GRID]


# --- Orden del documento final -------------------------------------------------
#
# Desde la reestructuración de los contenedores en el original, los hijos de un
# KEY_VALUE_REGION solo deciden a qué contenedor pertenece cada elemento; el
# orden dentro del contenedor lo vuelve a calcular el predictor de orden de
# lectura basado en reglas, que en una rejilla etiqueta|valor lee por columnas.
# Estos tests ejercitan ReadingOrderModel, la etapa que produce el documento.
# FORM queda fuera a propósito: a veces envuelve una página entera de tablas y
# listas, y ahí el orden por filas desordena el contenido.
#
# Las etiquetas terminan en ":" a propósito: así ninguna se fusiona con su valor
# por la heurística de continuación de párrafo y el test mide solo el orden.

from pathlib import PurePath  # noqa: E402

from docling_core.types.doc import GroupLabel  # noqa: E402

from docling.datamodel.base_models import (  # noqa: E402
    AssembledUnit,
    ContainerElement,
    InputFormat,
    Page,
    TextElement,
)
from docling.datamodel.document import ConversionResult, InputDocument  # noqa: E402
from docling.models.stages.reading_order.readingorder_model import (  # noqa: E402
    ReadingOrderModel,
    ReadingOrderOptions,
)

_KV_GRID = [
    # (índice, texto,        left,  top)   columna por columna, como el generador
    (0, "Rate:", 40.0, 100.4),
    (1, "Term:", 40.0, 120.0),
    (2, "14.45%", 150.0, 100.0),
    (3, "090", 150.0, 120.0),
    (4, "Currency:", 300.0, 100.0),
    (5, "Installments:", 300.0, 120.0),
    (6, "COP", 420.0, 100.0),
    (7, "049", 420.0, 120.0),
]

EXPECTED_KV_ORDER = [
    "Rate:",
    "14.45%",
    "Currency:",
    "COP",
    "Term:",
    "090",
    "Installments:",
    "049",
]


def _key_value_area_from_grid(grid: list[tuple[int, str, float, float]]) -> list[str]:
    """Convierte la rejilla con ReadingOrderModel y devuelve los textos del área."""
    children = [
        _child(cid=100 + index, cell=_text_cell(index, text, left, top))
        for index, text, left, top in grid
    ]
    region_cluster = Cluster(
        id=1,
        label=DocItemLabel.KEY_VALUE_REGION,
        bbox=BoundingBox(l=30.0, t=95.0, r=470.0, b=135.0),
        confidence=0.7,
        # Fila-mayor, que es como los deja el postprocesador de layout.
        children=sorted(children, key=lambda c: (round(c.bbox.t / 10), c.id)),
    )
    region = ContainerElement(
        label=DocItemLabel.KEY_VALUE_REGION, id=1, page_no=1, cluster=region_cluster
    )
    # El orden de ensamblado sigue el índice de celda nativo: columna-mayor.
    texts = [
        TextElement(
            label=DocItemLabel.TEXT,
            id=child.id,
            text=child.cells[0].text,
            page_no=1,
            cluster=child,
        )
        for child in children
    ]
    elements = [region, *texts]
    conv_res = ConversionResult(
        input=InputDocument.model_construct(
            file=PurePath("input.pdf"),
            document_hash="0" * 64,
            valid=True,
            format=InputFormat.PDF,
        ),
        pages=[Page(page_no=1, size=Size(width=612.0, height=792.0))],
        assembled=AssembledUnit(elements=elements, body=elements),
    )

    doc = ReadingOrderModel(ReadingOrderOptions())(conv_res)

    area = next(
        group for group in doc.groups if group.label == GroupLabel.KEY_VALUE_AREA
    )
    return [child.resolve(doc).text for child in area.children]


def test_key_value_area_in_document_is_in_row_major_reading_order() -> None:
    """El documento final debe alternar etiqueta y valor, fila a fila."""
    assert _key_value_area_from_grid(_KV_GRID) == EXPECTED_KV_ORDER, (
        "el área clave-valor del documento sale en orden columna-mayor, "
        "así que cada etiqueta queda separada de su valor"
    )


def test_key_value_area_in_document_respects_right_to_left_documents() -> None:
    assert _key_value_area_from_grid(_GRID_RTL) == EXPECTED_RTL_READING_ORDER
