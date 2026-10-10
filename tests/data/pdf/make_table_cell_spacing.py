"""Generate ``table_cell_spacing.pdf``, the fixture of ``test_table_cell_spacing.py``.

Run from anywhere: ``python tests/data/pdf/make_table_cell_spacing.py``. It only
uses the standard library and writes the PDF next to this script, byte for byte
the same on every run.

The words are made up. What is copied from the real document where the bug was
seen is only the geometry of the cell text, measured with docling-parse:

* the text is drawn in runs, one text-showing operator each, the way browsers
  print to PDF;
* the run before the break **ends with a real space glyph**;
* the next run starts 0.85 pt after the right edge of the previous letter, so
  it overlaps the space glyph instead of starting where the space ends;
* the font is 8.4 pt, which makes that gap about 0.10 em.

With docling-parse 7.7.0 those two runs come out as one glued word cell
("decasos"); from 7.18.0 on the space glyph splits them, as it does in the real
document.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).with_name("table_cell_spacing.pdf")

FONT_SIZE = 8.4
# Gap between the right edge of the last letter of run A and the start of run B.
GAP = 0.85

# Helvetica advance widths (AFM, 1/1000 em) of the characters in run A.
HELVETICA_WIDTHS = {
    " ": 278,
    "a": 556,
    "c": 500,
    "d": 556,
    "e": 556,
    "i": 222,
    "l": 222,
    "m": 833,
    "n": 556,
    "o": 556,
    "s": 500,
    "t": 278,
    "u": 556,
}


def text_width(text: str, size: float = FONT_SIZE) -> float:
    return sum(HELVETICA_WIDTHS[ch] for ch in text) * size / 1000


def run(x: float, y: float, text: str) -> str:
    return f"BT /F1 {FONT_SIZE} Tf 1 0 0 1 {x:.3f} {y:.3f} Tm ({text}) Tj ET\n"


def content() -> str:
    cell_x, row_y = 168.0, 677.0
    # Run A ends with a space glyph, as in the real document.
    run_a = "documento con la lista de "
    run_b = "casos revisados"
    run_b_x = cell_x + text_width(run_a.rstrip(" ")) + GAP
    assert run_b_x < cell_x + text_width(run_a), "run B must overlap the space glyph"
    return (
        # 2-column ruled table: header row and one body row.
        "0.8 w 0 0 0 RG 50 642 495 100 re S\n"
        "50 702 m 545 702 l S\n"
        "160 742 m 160 642 l S\n"
        + run(58, 717, "Etapa")
        + run(168, 717, "Descripcion")
        + run(58, row_y, "E1")
        + run(cell_x, row_y, run_a)
        + run(run_b_x, row_y, run_b)
    )


def build_pdf() -> bytes:
    stream = content().encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]"
        b" /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
        b" /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.7\n%\xb5\xb6\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


if __name__ == "__main__":
    OUT.write_bytes(build_pdf())
    print(f"wrote {OUT}")
