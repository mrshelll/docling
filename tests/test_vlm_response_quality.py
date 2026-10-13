# SPDX-FileCopyrightText: DoTech Labs S.A.S
# SPDX-License-Identifier: MIT

"""A VLM can answer with nothing at all, or with the same line 238 times. Both were
reported as ConversionStatus.SUCCESS with zero errors, so a batch conversion would hand
over blank or garbage documents without raising anything.

Measured on granite-docling over a 280-word page: 13564 characters, 2380 words, 7 of
them distinct, no word in common with the page.
"""

import pytest

from docling.utils.vlm_response_quality import looks_degenerate


class TestEmptyOutput:
    def test_empty_string_is_degenerate(self):
        assert looks_degenerate("")

    def test_whitespace_only_is_degenerate(self):
        assert looks_degenerate("   \n\t  ")


class TestRepetitionLoop:
    def test_the_same_line_repeated_is_degenerate(self):
        assert looks_degenerate("la industria de la industria de " * 200)

    def test_a_short_repetitive_answer_is_not_flagged(self):
        """A table cell or a heading is legitimately short and repetitive."""
        assert not looks_degenerate("Total Total Total")


class TestHealthyOutput:
    def test_ordinary_prose_is_not_degenerate(self):
        texto = " ".join(f"palabra{i} de contenido variado" for i in range(80))
        assert not looks_degenerate(texto)

    def test_a_normal_page_of_markdown_is_not_degenerate(self):
        texto = "# Cultivo hidroponico\n\nEl sustrato debe mantenerse humedo y aireado, "
        texto += "con un riego que aporte los nutrientes disueltos en agua limpia. "
        texto += "Las raices necesitan oxigeno, asi que conviene evitar el encharcamiento."
        assert not looks_degenerate(texto)
