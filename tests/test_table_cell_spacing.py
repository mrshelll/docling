"""Regresión: el texto de celdas de tabla no debe perder separadores de palabra.

Al ensamblar el texto de una celda a partir de runs adyacentes, el separador
se descartaba, produciendo palabras pegadas ("la lista de casos" -> "la lista
decasos"). El separador sí está presente en la salida del parser.

Nota sobre el fixture (`tests/data/pdf/table_cell_spacing.pdf`): el hueco
entre los dos runs de texto está calibrado a 1.5pt a propósito, para que el
parser siga emitiendo el separador pero el ensamblado de la celda lo
descarte. Un hueco mayor produce una salida correcta de punta a punta (el
bug no se reproduce) y uno menor hace que el propio parser pegue las
palabras (un bug distinto, en otra capa). Si en el futuro alguien "arregla"
el fixture agrandando o achicando ese hueco, dejaría de probar este
mecanismo específico.
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
