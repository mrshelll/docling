import pytest

from informe import cuerpo, estado_tests, revisar_a_mano, titulo
from registro import Arreglo

LIMPIA = {"del_original": ["t::a"], "nuestras": [], "corridas_rotas": [], "mensajes": {}, "bloquea": False}
CON_NUESTRAS = {"del_original": [], "nuestras": ["t::b"], "corridas_rotas": [],
                "mensajes": {"t::b": "assert 1 == 2"}, "bloquea": True}
ROTA = {"del_original": [], "nuestras": [], "corridas_rotas": ["e2e"], "mensajes": {}, "bloquea": True}
ARREGLOS = [Arreglo("bug2", "Bug 2", True, (), "t.py"), Arreglo("bug1", "Bug 1", False, (), "t.py", rama="fix/b1")]
SOBRA = {"bug2": {"veredicto": "hace_falta", "detalle": ""}, "bug1": {"veredicto": "sobra", "detalle": ""}}
LOTE = {"por_arreglo": {"bug2": [{"sha": "aaa", "titulo": "feat: x (#4276)", "pr": 4276}], "bug1": []},
        "areas": [{"sha": "ddd1234567", "titulo": "fix(pdf): y", "pr": None}],
        "workflows_nuevos": [".github/workflows/nuevo.yml"]}


def test_titulo():
    assert titulo("v2.136.0", False) == "Pasar a v2.136.0"
    assert titulo("v2.136.0", True) == "[conflicto para revisar a mano] Pasar a v2.136.0"


@pytest.mark.parametrize("comparacion, conflicto, resumen, estado", [
    (LIMPIA, False, None, "success"),
    (CON_NUESTRAS, False, None, "failure"),
    (ROTA, False, None, "failure"),
    (LIMPIA, True, {"resuelto": False, "archivos": []}, "failure"),
    (LIMPIA, True, None, "failure"),  # Claude no devolvió resumen
    (LIMPIA, True, {"resuelto": True, "archivos": []}, "success"),
])
def test_estado_tests(comparacion, conflicto, resumen, estado):
    e, descripcion = estado_tests(comparacion, conflicto, resumen)
    assert e == estado
    assert 0 < len(descripcion) <= 140


def test_revisar_a_mano_solo_con_conflicto():
    assert not revisar_a_mano(CON_NUESTRAS, False, None)
    assert revisar_a_mano(CON_NUESTRAS, True, {"resuelto": True, "archivos": []})
    assert revisar_a_mano(LIMPIA, True, {"resuelto": False, "archivos": []})
    assert not revisar_a_mano(LIMPIA, True, {"resuelto": True, "archivos": []})


def _cuerpo(**kw):
    base = dict(tag="v2.136.0", tag_anterior="v2.135.0", arreglos=ARREGLOS, sobra=SOBRA,
                comparacion=CON_NUESTRAS, lote=LOTE, conflicto=False, resumen_conflicto=None,
                explicacion="", enlace="https://run")
    base.update(kw)
    return cuerpo(**base)


def test_cuerpo_contiene_lo_que_necesitan_los_revisores():
    texto = _cuerpo()
    assert "v2.135.0" in texto and "v2.136.0" in texto
    assert "Sobra: el original ya lo resuelve" in texto            # bug1
    assert "Sigue haciendo falta" in texto                          # bug2
    assert "`t::b`" in texto and "assert 1 == 2" in texto           # fallo nuestro
    assert "https://github.com/docling-project/docling/pull/4276" in texto
    assert "ddd12345" in texto                                       # cambio sin PR
    assert ".github/workflows/nuevo.yml" in texto
    assert "docling-validar" in texto
    assert "Create a merge commit" in texto


def test_cuerpo_con_conflicto_y_explicacion():
    resumen = {"resuelto": True, "archivos": [
        {"archivo": "a.py", "original": "movió | el bloque", "decision": "reaplicar", "tests": "3 PASS"}]}
    texto = _cuerpo(conflicto=True, resumen_conflicto=resumen, explicacion="Causa: X")
    assert "movió \\| el bloque" in texto   # una barra no rompe la tabla
    assert "Causa: X" in texto


def test_cuerpo_con_corrida_rota():
    assert "Corridas rotas" in _cuerpo(comparacion=ROTA)
