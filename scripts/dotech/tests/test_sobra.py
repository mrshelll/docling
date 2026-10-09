import subprocess
from pathlib import Path

import pytest

from registro import Arreglo
from sobra import copiar_test, veredicto


def _junit(tmp_path: Path, *mensajes: tuple[str, str]) -> Path:
    casos = "".join(
        f'<testcase classname="t" name="n{i}"><{tag} message="{m}">tb</{tag}></testcase>'
        for i, (tag, m) in enumerate(mensajes)
    )
    ruta = tmp_path / "j.xml"
    ruta.write_text(f"<testsuites><testsuite>{casos}</testsuite></testsuites>", encoding="utf-8")
    return ruta


def test_todo_pasa_sobra(tmp_path):
    assert veredicto(0, _junit(tmp_path)) == "sobra"


@pytest.mark.parametrize("mensaje", ["assert 1 == 2", "AssertionError: pegadas&#10;assert False"])
def test_fallos_de_asercion_hace_falta(tmp_path, mensaje):
    assert veredicto(1, _junit(tmp_path, ("failure", mensaje))) == "hace_falta"


@pytest.mark.parametrize("mensaje", [
    "AttributeError: type object 'LayoutPostprocessor' has no attribute 'x'",
    "TypeError: __init__() missing 1 required positional argument",
])
def test_fallo_por_api_cambiada_no_es_concluyente(tmp_path, mensaje):
    """El original cambió una API interna: el test no dice nada del comportamiento."""
    assert veredicto(1, _junit(tmp_path, ("failure", "assert 0"), ("failure", mensaje))) == "no_concluyente"


def test_error_de_preparacion_no_es_concluyente(tmp_path):
    assert veredicto(1, _junit(tmp_path, ("error", "failed on setup"))) == "no_concluyente"


@pytest.mark.parametrize("codigo", [2, 3, 4, 5])
def test_coleccion_rota_o_sin_tests_no_es_concluyente(tmp_path, codigo):
    assert veredicto(codigo, _junit(tmp_path)) == "no_concluyente"


def test_sin_junit_no_es_concluyente(tmp_path):
    assert veredicto(1, tmp_path / "no-existe.xml") == "no_concluyente"


def _arreglo(**kw):
    base = dict(clave="b", nombre="B", en_main=True, archivos=(),
                test_comportamiento="tests/test_b.py", fixtures=("tests/data/b.pdf",))
    base.update(kw)
    return Arreglo(**base)


def test_copia_test_y_fixtures_del_arbol_de_trabajo(tmp_path):
    fuente, destino = tmp_path / "f", tmp_path / "d"
    (fuente / "tests/data").mkdir(parents=True)
    (fuente / "tests/test_b.py").write_text("def test(): pass\n")
    (fuente / "tests/data/b.pdf").write_bytes(b"%PDF")
    copiar_test(_arreglo(), fuente, destino)
    assert (destino / "tests/test_b.py").read_text() == "def test(): pass\n"
    assert (destino / "tests/data/b.pdf").read_bytes() == b"%PDF"


def test_fuera_de_main_copia_desde_su_rama(tmp_path):
    fuente, destino = tmp_path / "f", tmp_path / "d"
    fuente.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(fuente), *a], check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    (fuente / "tests").mkdir()
    (fuente / "tests/test_b.py").write_text("rama\n")
    (fuente / "tests/data").mkdir()
    (fuente / "tests/data/b.pdf").write_bytes(b"%PDF")
    git("add", "."); git("commit", "-qm", "x")
    git("update-ref", "refs/remotes/origin/fix/b", "HEAD")
    (fuente / "tests/test_b.py").unlink()  # no está en el árbol de trabajo
    copiar_test(_arreglo(en_main=False, rama="fix/b"), fuente, destino)
    assert (destino / "tests/test_b.py").read_text() == "rama\n"
