# SPDX-FileCopyrightText: DoTech Labs S.A.S
# SPDX-License-Identifier: MIT
import json

import pytest

from error_claude import LARGO_MAXIMO, SIN_ARCHIVO, SIN_RESULTADO, SIN_RESUMEN, main, motivo

INIT = {"type": "system", "subtype": "init", "model": "claude-haiku-5-5"}


def _resultado(**kw):
    return dict({"type": "result", "subtype": "success", "is_error": True, "total_cost_usd": 0}, **kw)


def test_rechazo_de_la_api_devuelve_su_mensaje():
    texto = json.dumps([INIT, _resultado(result="Invalid API key · Fix external API key")])
    assert motivo(texto) == "Invalid API key · Fix external API key"


def test_acepta_un_objeto_suelto_y_json_por_linea():
    r = _resultado(result="Credit balance is too low")
    assert motivo(json.dumps(r)) == "Credit balance is too low"
    assert motivo(json.dumps(INIT) + "\n" + json.dumps(r) + "\n") == "Credit balance is too low"


def test_usa_el_ultimo_resultado():
    texto = json.dumps([_resultado(result="viejo"), _resultado(result="nuevo")])
    assert motivo(texto) == "nuevo"


def test_sin_texto_cae_en_errors_o_subtype():
    assert motivo(json.dumps([_resultado(errors=["a", "b"])])) == '["a", "b"]'
    assert motivo(json.dumps([_resultado(subtype="error_max_turns")])) == "error_max_turns"


def test_queda_en_una_linea_y_acotado():
    m = motivo(json.dumps([_resultado(result="API Error: 400\n" + "x" * 2000)]))
    assert "\n" not in m and len(m) == LARGO_MAXIMO and m.endswith("…")


@pytest.mark.parametrize("texto, esperado", [
    (None, SIN_ARCHIVO),
    ("", SIN_ARCHIVO),
    ("no es json", SIN_RESULTADO),
    (json.dumps([INIT]), SIN_RESULTADO),
    (json.dumps(42), SIN_RESULTADO),
    (json.dumps([_resultado(is_error=False, result="ok")]), SIN_RESUMEN),
])
def test_casos_sin_mensaje_de_error(texto, esperado):
    assert motivo(texto) == esperado


def test_main_con_archivo_ausente_o_vacio(tmp_path, capsys):
    main([str(tmp_path / "no-existe.json")])
    main([""])
    main([])
    assert capsys.readouterr().out.splitlines() == [SIN_ARCHIVO] * 3


def test_main_lee_el_archivo(tmp_path, capsys):
    f = tmp_path / "salida.json"
    f.write_text(json.dumps([INIT, _resultado(result="API Error: 401")]), encoding="utf-8")
    main([str(f)])
    assert capsys.readouterr().out.strip() == "API Error: 401"
