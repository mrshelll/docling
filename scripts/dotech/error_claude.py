# SPDX-FileCopyrightText: DoTech Labs S.A.S
# SPDX-License-Identifier: MIT
"""Por qué falló una llamada a Claude, en una línea, para el informe.

claude-code-action oculta la salida de Claude en el registro, también en modo
depuración. Si la API rechaza la llamada (clave inválida, sin saldo, sin permiso
para el modelo), el registro solo dice «did not return structured_output» y el
informe lo confundía con «Claude no lo dio por resuelto». El mensaje real está en
el archivo de ejecución (`execution_file`): este script lo saca.

Uso: error_claude.py <execution_file>  →  imprime el motivo (una línea) o nada.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LARGO_MAXIMO = 500
SIN_ARCHIVO = ("la acción de Claude no dejó archivo de ejecución: se agotó el tiempo o falló "
               "antes de arrancar (ver el registro de la ejecución)")
SIN_RESULTADO = "el archivo de ejecución de Claude no trae resultado final (ver el registro)"
SIN_RESUMEN = "Claude terminó sin error pero no devolvió el resumen estructurado"


def _mensajes(texto: str) -> list[dict]:
    """El archivo es una lista JSON de mensajes; se aceptan también un objeto o JSON por línea."""
    try:
        datos = json.loads(texto)
    except ValueError:
        datos = []
        for linea in texto.splitlines():
            try:
                datos.append(json.loads(linea))
            except ValueError:
                continue
    if isinstance(datos, dict):
        datos = [datos]
    return [m for m in datos if isinstance(m, dict)] if isinstance(datos, list) else []


def motivo(texto: str | None) -> str:
    if not texto or not texto.strip():
        return SIN_ARCHIVO
    resultados = [m for m in _mensajes(texto) if m.get("type") == "result"]
    if not resultados:
        return SIN_RESULTADO
    ultimo = resultados[-1]
    if not ultimo.get("is_error"):
        return SIN_RESUMEN
    detalle = ultimo.get("result") or ultimo.get("errors") or ultimo.get("subtype") or "sin mensaje"
    if not isinstance(detalle, str):
        detalle = json.dumps(detalle, ensure_ascii=False)
    linea = " ".join(detalle.split())
    return linea if len(linea) <= LARGO_MAXIMO else linea[: LARGO_MAXIMO - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ruta = Path(argv[0]) if argv and argv[0] else None
    texto = None
    if ruta is not None and ruta.is_file():
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    print(motivo(texto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
