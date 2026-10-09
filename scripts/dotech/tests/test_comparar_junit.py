from pathlib import Path

from comparar_junit import comparar, comparar_directorios, resultados

TABLA_5 = """converting a.pdf
+-------+-------+--------+-------+
| document | check | status | error |
+-------+-------+--------+-------+
| a.pdf | md | FAIL | diff |
| b.pdf | all | PASS |  |
+-------+-------+--------+-------+
"""
TABLA_6 = TABLA_5.replace("| b.pdf | all | PASS |  |", "| b.pdf | json | FAIL | diff |")


def _junit(casos: str) -> str:
    return f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{casos}</testsuite></testsuites>'


def _caso(nombre, *, falla=None, error=None, salida=None, clase="tests.test_x"):
    hijos = ""
    if falla:
        hijos += f'<failure message="{falla}">tb</failure>'
    if error:
        hijos += f'<error message="{error}">tb</error>'
    if salida:
        hijos += f"<system-out>{salida}</system-out>"
    return f'<testcase classname="{clase}" name="{nombre}">{hijos}</testcase>'


def _escribir(directorio: Path, corrida: str, contenido: str) -> None:
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / f"junit-{corrida}.xml").write_text(contenido, encoding="utf-8")


def test_fallo_en_los_dos_lados_es_del_original(tmp_path):
    xml = _junit(_caso("test_a", falla="assert 1 == 2"))
    _escribir(tmp_path / "o", "core", xml)
    _escribir(tmp_path / "n", "core", xml)
    c = comparar(resultados(tmp_path / "o/junit-core.xml"), resultados(tmp_path / "n/junit-core.xml"))
    assert c.del_original == ["tests.test_x::test_a"] and c.nuestras == []
    assert not c.bloquea


def test_fallo_solo_en_nuestra_rama_es_nuestro():
    original = {"tests.test_x::test_a": ("ok", "")}
    nuestra = {"tests.test_x::test_a": ("fallo", "assert 1 == 2")}
    c = comparar(original, nuestra)
    assert c.nuestras == ["tests.test_x::test_a"]
    assert c.mensajes["tests.test_x::test_a"] == "assert 1 == 2"
    assert c.bloquea


def test_error_de_coleccion_cuenta_como_fallo(tmp_path):
    _escribir(tmp_path, "core", _junit(_caso("tests.test_y", error="collection failure", clase="")))
    assert resultados(tmp_path / "junit-core.xml") == {"::tests.test_y": ("fallo", "collection failure")}


def test_omitido_no_es_fallo(tmp_path):
    _escribir(tmp_path, "core", _junit('<testcase classname="t" name="s"><skipped message="x"/></testcase>'))
    assert resultados(tmp_path / "junit-core.xml") == {"t::s": ("omitido", "")}


def test_la_tabla_del_e2e_se_desglosa_por_documento_y_comprobacion(tmp_path):
    """El e2e es un solo test que ya falla en el original: sin desglose, una
    comprobación nueva rota por nosotros quedaría escondida como 'del original'."""
    _escribir(tmp_path / "o", "e2e", _junit(_caso("test_e2e", falla="assert 1 == 0", salida=TABLA_5)))
    _escribir(tmp_path / "n", "e2e", _junit(_caso("test_e2e", falla="assert 2 == 0", salida=TABLA_6)))
    c = comparar(resultados(tmp_path / "o/junit-e2e.xml"), resultados(tmp_path / "n/junit-e2e.xml"))
    assert c.del_original == ["tests.test_x::test_e2e[a.pdf::md]"]
    assert c.nuestras == ["tests.test_x::test_e2e[b.pdf::json]"]


def test_falta_el_junit_es_corrida_rota(tmp_path):
    xml = _junit(_caso("test_a"))
    for lado in ("o", "n"):
        _escribir(tmp_path / lado, "core", xml)
    _escribir(tmp_path / "n", "dotech", xml)
    # falta junit-e2e.xml en los dos lados
    c = comparar_directorios(tmp_path / "o", tmp_path / "n")
    assert c.corridas_rotas == ["e2e"]
    assert c.bloquea


def test_junit_sin_ningun_test_es_corrida_rota(tmp_path):
    for lado in ("o", "n"):
        for corrida in ("core", "e2e"):
            _escribir(tmp_path / lado, corrida, _junit(_caso("test_a")))
    _escribir(tmp_path / "n", "dotech", _junit(""))
    assert comparar_directorios(tmp_path / "o", tmp_path / "n").corridas_rotas == ["dotech"]


def test_junit_ilegible_es_corrida_rota(tmp_path):
    for lado in ("o", "n"):
        for corrida in ("core", "e2e"):
            _escribir(tmp_path / lado, corrida, _junit(_caso("test_a")))
    _escribir(tmp_path / "n", "dotech", "<testsuites><testsu")
    assert comparar_directorios(tmp_path / "o", tmp_path / "n").corridas_rotas == ["dotech"]


def test_los_tests_dotech_solo_existen_en_nuestra_rama(tmp_path):
    for lado in ("o", "n"):
        for corrida in ("core", "e2e"):
            _escribir(tmp_path / lado, corrida, _junit(_caso("test_a")))
    _escribir(tmp_path / "n", "dotech", _junit(_caso("test_d", falla="assert 0")))
    c = comparar_directorios(tmp_path / "o", tmp_path / "n")
    assert c.corridas_rotas == [] and c.nuestras == ["tests.test_x::test_d"]
