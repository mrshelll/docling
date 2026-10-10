from pathlib import Path

import pytest

from registro import REGISTRO, RAIZ_REPO, RegistroInvalido, cargar


def _escribir(tmp_path: Path, texto: str) -> Path:
    ruta = tmp_path / "arreglos.toml"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def test_carga_un_arreglo_completo(tmp_path):
    ruta = _escribir(tmp_path, """
[[arreglo]]
clave = "bug2"
nombre = "Bug 2"
en_main = true
archivos = ["docling/utils/layout_postprocessor.py"]
test_comportamiento = "tests/test_kv.py"
""")
    [a] = cargar(ruta)
    assert a.clave == "bug2" and a.en_main and a.rama is None
    assert a.archivos == ("docling/utils/layout_postprocessor.py",)
    assert a.fixtures == ()


def test_fuera_de_main_exige_rama(tmp_path):
    ruta = _escribir(tmp_path, """
[[arreglo]]
clave = "bug1"
nombre = "Bug 1"
en_main = false
archivos = ["x.py"]
test_comportamiento = "tests/t.py"
""")
    with pytest.raises(RegistroInvalido, match="rama"):
        cargar(ruta)


def test_faltan_campos(tmp_path):
    ruta = _escribir(tmp_path, '[[arreglo]]\nclave = "a"\n')
    with pytest.raises(RegistroInvalido, match="faltan"):
        cargar(ruta)


def test_claves_repetidas(tmp_path):
    bloque = """
[[arreglo]]
clave = "a"
nombre = "A"
en_main = true
archivos = []
test_comportamiento = "t.py"
"""
    with pytest.raises(RegistroInvalido, match="repetidas"):
        cargar(_escribir(tmp_path, bloque * 2))


def test_registro_vacio(tmp_path):
    with pytest.raises(RegistroInvalido, match="no tiene"):
        cargar(_escribir(tmp_path, ""))


def test_el_registro_real_es_coherente_con_el_repo():
    """Cada arreglo integrado tiene su test y sus archivos en este árbol."""
    for a in cargar(REGISTRO):
        if a.en_main:
            assert (RAIZ_REPO / a.test_comportamiento).exists(), a.clave
            for archivo in a.archivos + a.fixtures:
                assert (RAIZ_REPO / archivo).exists(), f"{a.clave}: {archivo}"
