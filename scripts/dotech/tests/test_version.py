import pytest

from version import decidir, tag_de_titulo

RAMA = "dotech/sync-upstream"


def _d(**kw):
    base = dict(rama=RAMA, contiene_main=False, solicitud_abierta=False,
                contiene_rama=False, tag_rechazado=None)
    base.update(kw)
    return decidir("v2.136.0", **base)


def test_main_ya_la_contiene():
    d = _d(contiene_main=True)
    assert d.accion == "nada"


def test_version_nueva_sin_solicitud_parte_de_main():
    d = _d()
    assert (d.accion, d.base) == ("sincronizar", "main")


def test_solicitud_abierta_sin_la_version_parte_de_la_rama():
    d = _d(solicitud_abierta=True, contiene_rama=False)
    assert (d.accion, d.base) == ("sincronizar", RAMA)


def test_solicitud_abierta_que_ya_la_contiene():
    assert _d(solicitud_abierta=True, contiene_rama=True).accion == "nada"


def test_version_rechazada_no_se_reabre():
    """Cerrar la solicitud sin integrar es un 'no' a esa versión: no se insiste cada 6 h."""
    assert _d(tag_rechazado="v2.136.0").accion == "nada"


def test_una_version_posterior_a_la_rechazada_si_se_propone():
    d = _d(tag_rechazado="v2.135.0")
    assert (d.accion, d.base) == ("sincronizar", "main")


@pytest.mark.parametrize("titulo, tag", [
    ("Pasar a v2.136.0", "v2.136.0"),
    ("[conflicto para revisar a mano] Pasar a v2.137.1", "v2.137.1"),
    ("fix: otra cosa", None),
])
def test_tag_de_titulo(titulo, tag):
    assert tag_de_titulo(titulo) == tag


def test_tag_anterior_se_mide_desde_main_aunque_la_base_sea_la_rama(monkeypatch, capsys):
    import json
    import subprocess

    import version

    pedidos = []

    def salida(*args):
        pedidos.append(args)
        if args[:3] == ("gh", "pr", "list") and "open" in args:
            return json.dumps([_pr(1)])
        if args[:3] == ("gh", "pr", "list"):
            return "[]"
        return "v2.135.0"

    monkeypatch.setattr(version, "_salida", salida)
    monkeypatch.setattr(
        version, "_ejecutar",
        lambda *a: subprocess.CompletedProcess(a, 0 if a[:2] == ("git", "ls-remote") else 1, "", ""),
    )
    version.main(["--repo", f"{DUENO}/docling", "--upstream", "u", "--rama", RAMA,
                  "--ref", "v2.136.0"])

    salida_cli = capsys.readouterr().out
    assert "base=" + RAMA in salida_cli
    describe = [p for p in pedidos if p[:2] == ("git", "describe")]
    assert describe and describe[0][-1] == "origin/main"


DUENO = "mrshelll"


def _pr(numero, *, ajena=False, titulo="", integrada=False):
    return {
        "number": numero,
        "title": titulo,
        "mergedAt": "2026-10-01T00:00:00Z" if integrada else None,
        "isCrossRepository": ajena,
        "headRepositoryOwner": {"login": "tercero" if ajena else DUENO},
    }


def test_solicitud_abierta_desde_un_fork_no_cuenta():
    from version import solicitudes_propias

    assert solicitudes_propias([_pr(7, ajena=True)], DUENO) == []
    assert solicitudes_propias([_pr(7, ajena=True), _pr(3)], DUENO) == [_pr(3)]


def test_cerrada_ajena_mas_reciente_no_tapa_el_rechazo_propio():
    from version import tag_rechazado

    cerradas = [_pr(9, ajena=True, titulo="fix: otra cosa"), _pr(5, titulo="Pasar a v2.136.0")]
    assert tag_rechazado(cerradas, DUENO) == "v2.136.0"


def test_cerrada_ajena_sin_integrar_no_es_rechazo():
    from version import tag_rechazado

    assert tag_rechazado([_pr(9, ajena=True, titulo="Pasar a v2.136.0")], DUENO) is None


def test_cerrada_propia_integrada_no_es_rechazo_aunque_haya_otra_anterior():
    from version import tag_rechazado

    cerradas = [_pr(6, titulo="Pasar a v2.137.0", integrada=True), _pr(5, titulo="Pasar a v2.136.0")]
    assert tag_rechazado(cerradas, DUENO) is None


def test_sin_cerradas_no_hay_rechazo():
    from version import tag_rechazado

    assert tag_rechazado([], DUENO) is None


def test_mismo_dueno_sin_marca_de_repo_no_cuenta():
    """Si GitHub no dice que es del propio repo, se descarta: mejor perder una que confiar en una ajena."""
    from version import solicitudes_propias

    assert solicitudes_propias([{"number": 1, "headRepositoryOwner": {"login": DUENO}}], DUENO) == []


def test_main_ignora_la_solicitud_abierta_de_un_fork(monkeypatch, capsys):
    import json
    import subprocess

    import version

    pedidos = []

    def salida(*args):
        pedidos.append(args)
        if args[:3] == ("gh", "pr", "list") and "open" in args:
            return json.dumps([_pr(7, ajena=True)])
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([_pr(8, ajena=True, titulo="Pasar a v2.136.0")])
        return "v2.135.0"

    monkeypatch.setattr(version, "_salida", salida)
    monkeypatch.setattr(
        version, "_ejecutar",
        lambda *a: subprocess.CompletedProcess(a, 1, "", ""),
    )
    version.main(["--repo", f"{DUENO}/docling", "--upstream", "u", "--rama", RAMA,
                  "--ref", "v2.136.0"])

    salida_cli = capsys.readouterr().out
    assert "accion=sincronizar" in salida_cli
    assert "base=main" in salida_cli
    cerradas = [p for p in pedidos if p[:3] == ("gh", "pr", "list") and "closed" in p]
    limite = int(cerradas[0][cerradas[0].index("--limit") + 1])
    assert limite > 1
