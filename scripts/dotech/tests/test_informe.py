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
    assert "`docling-project/docling#4276`" in texto                 # sin enlace al original
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


def _sin_codigo(texto):
    import re
    return re.sub(r"`[^`]*`", "", texto)


def test_no_enlaza_ni_menciona_al_original():
    texto = _cuerpo()
    assert "https://github.com/docling-project" not in texto
    assert "`docling-project/docling#4276`" in texto
    assert "(#4276)" not in texto   # el sufijo del título se quita si hay pr
    import re
    assert not re.search(r"#\d", _sin_codigo(texto))


def test_neutraliza_menciones_y_html():
    lote = {"por_arreglo": {"bug2": [{"sha": "aaa", "titulo": "fix: cc @alguien <b>", "pr": 1}]},
            "areas": [], "workflows_nuevos": []}
    comp = dict(CON_NUESTRAS, mensajes={"t::b": "</details> @otro <script>"})
    texto = _cuerpo(lote=lote, comparacion=comp, explicacion="Fixes #3\nhola @x <i>")
    assert "@alguien" not in texto and "@otro" not in texto and "@x" not in texto
    assert "@​alguien" in texto
    assert "</details> @" not in texto and "<script>" not in texto and "<b>" not in texto
    assert "&lt;/details&gt;" in texto
    assert "#3" not in texto and "#​3" in texto
    assert "> Fixes" in texto and "> hola" in texto


@pytest.mark.parametrize("crudo", ["no es json", "[1, 2]", '"x"', "3"])
def test_main_tolera_resumen_malformado(tmp_path, monkeypatch, capsys, crudo):
    import json
    from informe import main
    (tmp_path / "c.json").write_text(json.dumps(LIMPIA))
    (tmp_path / "l.json").write_text(json.dumps(LOTE))
    (tmp_path / "r.toml").write_text("")
    monkeypatch.setattr("informe.cargar", lambda _: ARREGLOS)
    monkeypatch.setenv("CONFLICTO", "true")
    monkeypatch.setenv("RESUMEN_CONFLICTO", crudo)
    rc = main(["--registro", str(tmp_path / "r.toml"), "--tag", "v2.136.0", "--tag-anterior", "v2.135.0",
               "--comparacion", str(tmp_path / "c.json"), "--sobra", str(tmp_path / "s.json"),
               "--lote", str(tmp_path / "l.json"), "--enlace", "https://run",
               "--salida-cuerpo", str(tmp_path / "out.md")])
    salida = capsys.readouterr().out
    assert rc == 0
    assert "estado=failure" in salida
    assert "titulo=[conflicto para revisar a mano] Pasar a v2.136.0" in salida


def test_entradas_de_archivos_incompletas():
    resumen = {"resuelto": True, "archivos": ["suelto", {"archivo": "a.py"}, {}]}
    texto = _cuerpo(conflicto=True, resumen_conflicto=resumen)
    assert "`a.py`" in texto
