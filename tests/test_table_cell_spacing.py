"""Regresión: el texto de celdas de tabla no debe perder separadores de palabra.

Al ensamblar el texto de una celda a partir de runs adyacentes, el separador
se descartaba, produciendo palabras pegadas ("la lista de casos" -> "la lista
decasos"). El separador sí está presente en la salida del parser.

Nota sobre el fixture (`tests/data/pdf/table_cell_spacing.pdf`): lo genera
`tests/data/pdf/make_table_cell_spacing.py`, con palabras inventadas y la
geometría medida en el documento real donde apareció el bug: el primer run
termina en un glifo de espacio real y el siguiente empieza 0.85pt después de
la última letra (Helvetica 8.4pt, unos 0.10 em), solapando ese espacio. Con
docling-parse 7.7.0 la celda sale pegada ("decasos"), igual que el documento
real; desde 7.18.0 sale separada en los dos. Si alguien cambia esa geometría,
el test dejaría de representar el caso real.
"""

from pathlib import Path

import pytest

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

FIXTURE = Path(__file__).parent / "data" / "pdf" / "table_cell_spacing.pdf"


@pytest.fixture(scope="module")
def markdown() -> str:
    opts = PdfPipelineOptions()
    opts.do_ocr = False
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    return converter.convert(FIXTURE).document.export_to_markdown()


def test_table_cell_preserves_word_separation(markdown: str) -> None:
    """Runs adyacentes dentro de una celda deben quedar separados por un espacio."""
    assert "decasos" not in markdown, (
        "las palabras quedaron pegadas al unir runs de la celda:\n" + markdown
    )
    assert "de casos revisados" in markdown


def test_table_cell_does_not_split_words(markdown: str) -> None:
    """El arreglo no debe partir palabras que ya estaban correctas."""
    for glued in ("document o", "list a", "revisado s"):
        assert glued not in markdown, (
            f"se partió una palabra correcta ({glued!r}):\n" + markdown
        )
