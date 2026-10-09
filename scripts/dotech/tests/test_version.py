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
    import subprocess

    import version

    pedidos = []

    def salida(*args):
        pedidos.append(args)
        if args[:3] == ("gh", "pr", "list") and "open" in args:
            return '[{"number": 1}]'
        if args[:3] == ("gh", "pr", "list"):
            return "[]"
        return "v2.135.0"

    monkeypatch.setattr(version, "_salida", salida)
    monkeypatch.setattr(
        version, "_ejecutar",
        lambda *a: subprocess.CompletedProcess(a, 0 if a[:2] == ("git", "ls-remote") else 1, "", ""),
    )
    version.main(["--repo", "r", "--upstream", "u", "--rama", RAMA, "--ref", "v2.136.0"])

    salida_cli = capsys.readouterr().out
    assert "base=" + RAMA in salida_cli
    describe = [p for p in pedidos if p[:2] == ("git", "describe")]
    assert describe and describe[0][-1] == "origin/main"
