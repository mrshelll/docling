"""Compara dos corridas de pytest (JUnit XML) para atribuir cada fallo.

Falla en las dos → es del original, no bloquea. Falla solo en nuestra rama → es
nuestro, bloquea. Una corrida sin resultado legible bloquea: «no hay fallos»
nunca puede salir de «no hay datos».

`test_e2e_conversion.py` es un solo test con una comprobación por documento que
imprime una tabla. Esa tabla se desglosa en un identificador por documento y
comprobación, porque el test entero ya falla en el original y, sin desglose, una
comprobación nueva rota por nosotros quedaría como «del original».
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

CORRIDAS_COMUNES = ("core", "e2e")
CORRIDA_PROPIA = "dotech"  # solo existe en nuestra rama

_FILA_FAIL = re.compile(r"^\|\s*(?P<doc>[^|]+?)\s*\|\s*(?P<check>[^|]+?)\s*\|\s*FAIL\s*\|", re.M)


@dataclass
class Comparacion:
    del_original: list[str] = field(default_factory=list)
    nuestras: list[str] = field(default_factory=list)
    corridas_rotas: list[str] = field(default_factory=list)
    mensajes: dict[str, str] = field(default_factory=dict)

    @property
    def bloquea(self) -> bool:
        return bool(self.nuestras or self.corridas_rotas)

    def sumar(self, otra: Comparacion) -> None:
        self.del_original += otra.del_original
        self.nuestras += otra.nuestras
        self.corridas_rotas += otra.corridas_rotas
        self.mensajes.update(otra.mensajes)


def resultados(junit: Path) -> dict[str, tuple[str, str]]:
    """Identificador de test → (estado, mensaje); estado ∈ {ok, fallo, omitido}."""
    salida: dict[str, tuple[str, str]] = {}
    for caso in ET.parse(junit).getroot().iter("testcase"):
        tid = f"{caso.get('classname', '')}::{caso.get('name', '')}"
        estado, mensaje = "ok", ""
        for hijo in caso:
            if hijo.tag in ("failure", "error"):
                estado, mensaje = "fallo", (hijo.get("message") or "")[:500]
                break
            if hijo.tag == "skipped":
                estado = "omitido"
        filas = _FILA_FAIL.findall(caso.findtext("system-out") or "") if estado == "fallo" else []
        if filas:
            for doc, check in filas:
                salida[f"{tid}[{doc}::{check}]"] = ("fallo", mensaje)
        else:
            salida[tid] = (estado, mensaje)
    return salida


def comparar(
    original: dict[str, tuple[str, str]], nuestra: dict[str, tuple[str, str]]
) -> Comparacion:
    c = Comparacion()
    for tid, (estado, mensaje) in sorted(nuestra.items()):
        if estado != "fallo":
            continue
        if original.get(tid, ("ausente", ""))[0] == "fallo":
            c.del_original.append(tid)
        else:
            c.nuestras.append(tid)
            c.mensajes[tid] = mensaje
    return c


def _legible(junit: Path) -> bool:
    try:
        return any(True for _ in ET.parse(junit).getroot().iter("testcase"))
    except (OSError, ET.ParseError):
        return False


def comparar_directorios(dir_original: Path, dir_nuestra: Path) -> Comparacion:
    total = Comparacion()
    for corrida in CORRIDAS_COMUNES + (CORRIDA_PROPIA,):
        f_nuestra = dir_nuestra / f"junit-{corrida}.xml"
        f_original = dir_original / f"junit-{corrida}.xml"
        comun = corrida != CORRIDA_PROPIA
        if not _legible(f_nuestra) or (comun and not _legible(f_original)):
            total.corridas_rotas.append(corrida)
            continue
        original = resultados(f_original) if comun else {}
        total.sumar(comparar(original, resultados(f_nuestra)))
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", type=Path, required=True)
    ap.add_argument("--nuestra", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args(argv)
    c = comparar_directorios(a.original, a.nuestra)
    a.salida.write_text(
        json.dumps({**asdict(c), "bloquea": c.bloquea}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"hay_nuestras={'true' if c.nuestras else 'false'}")
    print(f"bloquea={'true' if c.bloquea else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
