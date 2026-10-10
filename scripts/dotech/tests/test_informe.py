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


@pytest.mark.parametrize("url", [
    "https://github.com/docling-project/docling/issues/12",
    "HTTPS://GitHub.com/otro/repo/pull/3",
    "github.com/docling-project/docling/pull/9",
])
def test_defusa_urls_de_github_en_texto_variable(url):
    import re
    lote = {"por_arreglo": {}, "areas": [{"sha": "ddd1234567", "titulo": f"fix: see {url} (#10)", "pr": 10}],
            "workflows_nuevos": []}
    comp = dict(CON_NUESTRAS, mensajes={"t::b": f"mira {url}"})
    resumen = {"resuelto": True, "archivos": [
        {"archivo": "a.py", "original": f"ver {url}", "decision": f"{url}", "tests": url}]}
    texto = _cuerpo(lote=lote, comparacion=comp, explicacion=f"ver {url}", conflicto=True,
                    resumen_conflicto=resumen, enlace="https://github.com/mi/fork/actions/runs/1")
    assert len(re.findall(r"github\.com", texto, re.I)) == 1   # solo el enlace a la ejecución
    assert "https://github.com/mi/fork/actions/runs/1" in texto


def test_aviso_de_workflows_nuevos_menciona_pull_request():
    texto = _cuerpo()
    assert "`on: push`" in texto and "`pull_request`" in texto


MARCADO = "[conflicto para revisar a mano] Pasar a v2.138.0"
_VARIABLES = ("CONFLICTO", "RESUMEN_CONFLICTO", "EXPLICACION", "TITULO_ACTUAL", "MARCAS",
              "ARCHIVOS_DE_MAS", "ARCHIVOS_PROPIOS")


def _main(tmp_path, monkeypatch, capsys, comparacion=LIMPIA, **entorno):
    """Corre informe.main como el vigía y devuelve (salidas, cuerpo, comentario)."""
    import json
    from informe import main
    (tmp_path / "c.json").write_text(json.dumps(comparacion))
    (tmp_path / "l.json").write_text(json.dumps(dict(LOTE, workflows_nuevos=[])))
    (tmp_path / "r.toml").write_text("")
    monkeypatch.setattr("informe.cargar", lambda _: ARREGLOS)
    for nombre in _VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    for nombre, valor in entorno.items():
        monkeypatch.setenv(nombre, valor)
    rc = main(["--registro", str(tmp_path / "r.toml"), "--tag", "v2.139.0", "--tag-anterior", "v2.137.0",
               "--comparacion", str(tmp_path / "c.json"), "--sobra", str(tmp_path / "s.json"),
               "--lote", str(tmp_path / "l.json"), "--enlace", "https://run",
               "--salida-cuerpo", str(tmp_path / "cuerpo.md"),
               "--salida-comentario", str(tmp_path / "comentario.md")])
    assert rc == 0
    salidas = dict(linea.split("=", 1) for linea in capsys.readouterr().out.splitlines())
    return salidas, (tmp_path / "cuerpo.md").read_text(), (tmp_path / "comentario.md").read_text()


def test_la_marca_persiste_al_acumular_una_version_limpia(tmp_path, monkeypatch, capsys):
    # v2.138 dejó un conflicto sin revisar; v2.139 mezcla limpio sobre la misma rama.
    salidas, cuerpo_, _ = _main(tmp_path, monkeypatch, capsys, CONFLICTO="false", TITULO_ACTUAL=MARCADO)
    assert salidas["titulo"] == "[conflicto para revisar a mano] Pasar a v2.139.0"
    assert salidas["estado"] == "failure"
    assert "marca" in salidas["descripcion"] and len(salidas["descripcion"]) <= 140
    assert "## ⚠️ Revisar a mano" in cuerpo_ and "dotech-abrir-solicitud" in cuerpo_


def test_sin_marca_previa_la_version_limpia_sale_en_verde(tmp_path, monkeypatch, capsys):
    salidas, cuerpo_, comentario = _main(tmp_path, monkeypatch, capsys, CONFLICTO="false",
                                         TITULO_ACTUAL="Pasar a v2.138.0")
    assert salidas["titulo"] == "Pasar a v2.139.0"
    assert salidas["estado"] == "success"
    assert "## ⚠️ Revisar a mano" not in cuerpo_
    assert comentario == ""


def test_marca_pendiente():
    from informe import marca_pendiente
    assert marca_pendiente(MARCADO)
    assert not marca_pendiente("Pasar a v2.138.0")
    assert not marca_pendiente("")


def test_el_resumen_del_conflicto_va_tambien_en_un_comentario(tmp_path, monkeypatch, capsys):
    import json
    import re
    resumen = {"resuelto": True, "archivos": [
        {"archivo": "a.py", "original": "cc @alguien <b>", "decision": "ver github.com/x/y/pull/9",
         "tests": "Fixes #3"}]}
    _, _, comentario = _main(tmp_path, monkeypatch, capsys, CONFLICTO="true",
                             RESUMEN_CONFLICTO=json.dumps(resumen))
    primera, _, resto = comentario.partition("\n")
    assert primera == "<!-- dotech:conflicto v2.139.0 -->"
    assert "`a.py`" in resto
    assert "@alguien" not in resto and "<b>" not in resto and "#3" not in resto
    assert not re.search(r"github\.com", resto, re.I)


@pytest.mark.parametrize("entorno, motivo", [
    ({"MARCAS": "true"}, "marcas de conflicto"),
    ({"ARCHIVOS_PROPIOS": ".github/workflows/dotech-vigia.yml\nscripts/dotech/lote.py\n"}, "dotech-vigia.yml"),
])
def test_alertas_de_la_rama_fuerzan_revision(tmp_path, monkeypatch, capsys, entorno, motivo):
    salidas, cuerpo_, _ = _main(tmp_path, monkeypatch, capsys, CONFLICTO="false", **entorno)
    assert salidas["titulo"].startswith("[conflicto para revisar a mano]")
    assert salidas["estado"] == "failure" and len(salidas["descripcion"]) <= 140
    assert motivo in cuerpo_


def test_claude_toco_archivos_fuera_del_conflicto(tmp_path, monkeypatch, capsys):
    import json
    resumen = {"resuelto": True, "archivos": [{"archivo": "a.py", "original": "o", "decision": "d",
                                               "tests": "t"}]}
    salidas, cuerpo_, comentario = _main(tmp_path, monkeypatch, capsys, CONFLICTO="true",
                                         RESUMEN_CONFLICTO=json.dumps(resumen),
                                         ARCHIVOS_DE_MAS="docs/x.md\n\ndocling/y.py\n")
    assert salidas["titulo"].startswith("[conflicto para revisar a mano]")
    assert salidas["estado"] == "failure"
    for texto in (cuerpo_, comentario):
        assert "`docs/x.md`" in texto and "`docling/y.py`" in texto


@pytest.mark.parametrize("alertas", [
    {"marca_previa": True}, {"marcas": True}, {"fuera_del_conflicto": ("a",) * 50},
    {"propios": ("b",) * 50},
])
def test_estado_con_alertas(alertas):
    from informe import Alertas
    e, descripcion = estado_tests(LIMPIA, False, None, Alertas(**alertas))
    assert e == "failure"
    assert 0 < len(descripcion) <= 140
    assert revisar_a_mano(LIMPIA, False, None, Alertas(**alertas))
