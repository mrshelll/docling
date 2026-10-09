import json
import subprocess
from pathlib import Path

import pytest

import sobra
from registro import Arreglo
from sobra import copiar_test, veredicto


def _junit(tmp_path: Path, *mensajes: tuple[str, str]) -> Path:
    casos = "".join(
        f'<testcase classname="t" name="n{i}"/>' if tag is None
        else f'<testcase classname="t" name="n{i}"><{tag} message="{m}">tb</{tag}></testcase>'
        for i, (tag, m) in enumerate(mensajes)
    )
    ruta = tmp_path / "j.xml"
    ruta.write_text(f"<testsuites><testsuite>{casos}</testsuite></testsuites>", encoding="utf-8")
    return ruta


def test_todo_pasa_sobra(tmp_path):
    assert veredicto(0, _junit(tmp_path, (None, ""))) == "sobra"


def test_pasa_con_algun_saltado_sobra(tmp_path):
    assert veredicto(0, _junit(tmp_path, (None, ""), ("skipped", "sin red"))) == "sobra"


@pytest.mark.parametrize("mensajes", [(), (("skipped", "sin red"), ("skipped", "sin GPU"))])
def test_salida_0_sin_tests_que_corran_no_es_concluyente(tmp_path, mensajes):
    """pytest sale 0 si todo se salta: eso no prueba que el original lo resuelva."""
    assert veredicto(0, _junit(tmp_path, *mensajes)) == "no_concluyente"


def test_salida_0_sin_junit_no_es_concluyente(tmp_path):
    assert veredicto(0, tmp_path / "no-existe.xml") == "no_concluyente"
    assert veredicto(0, None) == "no_concluyente"


def test_salida_0_con_junit_ilegible_no_es_concluyente(tmp_path):
    ruta = tmp_path / "j.xml"
    ruta.write_text("<testsuites><testsuite>", encoding="utf-8")
    assert veredicto(0, ruta) == "no_concluyente"


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


def test_test_colgado_no_es_concluyente(tmp_path, monkeypatch):
    fuente, original = tmp_path / "f", tmp_path / "o"
    (fuente / "tests/data").mkdir(parents=True)
    (fuente / "tests/test_b.py").write_text("def test(): pass\n")
    (fuente / "tests/data/b.pdf").write_bytes(b"%PDF")
    vistos = []

    def colgado(cmd, **kw):
        vistos.append(kw.get("timeout"))
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(sobra.subprocess, "run", colgado)
    r = sobra.evaluar(_arreglo(), fuente, original)
    assert r == {"veredicto": "no_concluyente", "detalle": "timeout tras 20 min"}
    assert vistos == [sobra.TIMEOUT_PYTEST_S] and sobra.TIMEOUT_PYTEST_S == 20 * 60


def test_un_arreglo_que_revienta_no_borra_el_informe_de_los_demas(tmp_path, monkeypatch):
    registro = tmp_path / "arreglos.toml"
    registro.write_text(
        '[[arreglo]]\nclave = "a"\nnombre = "A"\nen_main = true\narchivos = []\n'
        'test_comportamiento = "tests/test_a.py"\n\n'
        '[[arreglo]]\nclave = "b"\nnombre = "B"\nen_main = true\narchivos = []\n'
        'test_comportamiento = "tests/test_b.py"\n',
        encoding="utf-8",
    )

    def evaluar(arreglo, fuente, original):
        if arreglo.clave == "a":
            raise FileNotFoundError("uv no está instalado")
        return {"veredicto": "hace_falta", "detalle": "1 failed"}

    monkeypatch.setattr(sobra, "evaluar", evaluar)
    salida = tmp_path / "con espacios" / "sobra.json"
    salida.parent.mkdir()
    assert sobra.main(["--registro", str(registro), "--fuente", str(tmp_path),
                       "--original", str(tmp_path), "--salida", str(salida)]) == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["b"] == {"veredicto": "hace_falta", "detalle": "1 failed"}
    assert datos["a"]["veredicto"] == "no_concluyente"
    assert "uv no está instalado" in datos["a"]["detalle"]
