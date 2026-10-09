"""¿El original ya resuelve alguno de nuestros arreglos?

Copia el test de comportamiento de cada arreglo (y sus datos) sobre el árbol del
original sin nuestro código y lo corre. Si pasa, el original ya lo resolvió.

Solo un fallo de aserción dice algo del comportamiento. Un `AttributeError` o
`TypeError` en los helpers del test significa que el original cambió una API
interna, y eso no prueba que el bug siga ahí: es «no concluyente».
"""

from __future__ import annotations

import argparse
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from registro import Arreglo, cargar

TIMEOUT_PYTEST_S = 20 * 60


def _es_asercion(mensaje: str) -> bool:
    return mensaje.startswith("assert ") or mensaje.startswith("AssertionError")


def veredicto(codigo_salida: int, junit: Path | None) -> str:
    if codigo_salida not in (0, 1) or junit is None or not junit.exists():
        return "no_concluyente"
    try:
        casos = list(ET.parse(junit).getroot().iter("testcase"))
    except ET.ParseError:
        return "no_concluyente"
    if codigo_salida == 0:
        # pytest también sale 0 si todo se salta: hace falta al menos un test que corra.
        corrio = any(caso.find("skipped") is None for caso in casos)
        return "sobra" if corrio else "no_concluyente"
    fallos = [h for caso in casos for h in caso if h.tag in ("failure", "error")]
    if fallos and all(h.tag == "failure" and _es_asercion(h.get("message") or "") for h in fallos):
        return "hace_falta"
    return "no_concluyente"


def _leer(arreglo: Arreglo, fuente: Path, ruta: str) -> bytes:
    if arreglo.en_main:
        return (fuente / ruta).read_bytes()
    return subprocess.run(
        ["git", "-C", str(fuente), "show", f"origin/{arreglo.rama}:{ruta}"],
        check=True, capture_output=True,
    ).stdout


def copiar_test(arreglo: Arreglo, fuente: Path, destino: Path) -> None:
    for ruta in (arreglo.test_comportamiento, *arreglo.fixtures):
        objetivo = destino / ruta
        objetivo.parent.mkdir(parents=True, exist_ok=True)
        objetivo.write_bytes(_leer(arreglo, fuente, ruta))


def evaluar(arreglo: Arreglo, fuente: Path, original: Path) -> dict[str, str]:
    try:
        if not arreglo.en_main:
            subprocess.run(
                ["git", "-C", str(fuente), "fetch", "--quiet", "origin",
                 f"{arreglo.rama}:refs/remotes/origin/{arreglo.rama}"],
                check=True, capture_output=True,
            )
        copiar_test(arreglo, fuente, original)
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"veredicto": "no_concluyente", "detalle": f"no se pudo copiar el test: {exc}"}
    junit = original / f"junit-sobra-{arreglo.clave}.xml"
    try:
        r = subprocess.run(
            ["uv", "run", "--no-sync", "pytest", "-q", "-p", "no:cacheprovider",
             f"--junitxml={junit}", arreglo.test_comportamiento],
            cwd=original, capture_output=True, text=True, timeout=TIMEOUT_PYTEST_S,
        )
    except subprocess.TimeoutExpired:
        return {"veredicto": "no_concluyente", "detalle": f"timeout tras {TIMEOUT_PYTEST_S // 60} min"}
    return {"veredicto": veredicto(r.returncode, junit), "detalle": r.stdout.strip()[-300:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registro", type=Path, required=True)
    ap.add_argument("--fuente", type=Path, required=True)
    ap.add_argument("--original", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args(argv)
    resultado = {}
    for x in cargar(a.registro):
        try:
            resultado[x.clave] = evaluar(x, a.fuente, a.original)
        except Exception as exc:  # un arreglo roto no debe dejar sin informe a los demás
            resultado[x.clave] = {"veredicto": "no_concluyente",
                                  "detalle": f"{type(exc).__name__}: {exc}"}
    a.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
