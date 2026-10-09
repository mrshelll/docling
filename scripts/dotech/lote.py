"""Cambios del lote del original que tocan nuestros arreglos o nuestras áreas."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from registro import Arreglo, cargar

FORMATO_LOG = "%x1e%H%x1f%s"
PALABRAS_AREA = ("layout", "reading-order", "reading order", "table", "vlm", "pdf")
_TIPO_RELEVANTE = re.compile(r"^(feat|fix|perf)(\(|!|:)")
_PR = re.compile(r"\(#(\d+)\)\s*$")
_PREFIJO_PROPIO = ".github/workflows/dotech-"


@dataclass(frozen=True)
class Cambio:
    sha: str
    titulo: str
    archivos: tuple[str, ...]

    @property
    def pr(self) -> int | None:
        m = _PR.search(self.titulo)
        return int(m.group(1)) if m else None


def parsear_log(texto: str) -> list[Cambio]:
    cambios = []
    for bloque in texto.split("\x1e"):
        if not bloque.strip():
            continue
        cabecera, _, resto = bloque.partition("\n")
        sha, _, titulo = cabecera.partition("\x1f")
        archivos = tuple(linea.strip() for linea in resto.splitlines() if linea.strip())
        cambios.append(Cambio(sha.strip(), titulo.strip(), archivos))
    return cambios


def _menciona_area(titulo: str) -> bool:
    t = titulo.lower()
    return bool(_TIPO_RELEVANTE.match(t)) and any(p in t for p in PALABRAS_AREA)


def relevantes(cambios: list[Cambio], arreglos: list[Arreglo]) -> dict[str, list[Cambio]]:
    salida = {
        a.clave: [c for c in cambios if set(c.archivos) & set(a.archivos)] for a in arreglos
    }
    tocados = {c.sha for lista in salida.values() for c in lista}
    salida["_areas"] = [c for c in cambios if c.sha not in tocados and _menciona_area(c.titulo)]
    return salida


def workflows_nuevos(nombres: str) -> list[str]:
    return [
        n.strip() for n in nombres.splitlines()
        if n.strip() and not n.strip().startswith(_PREFIJO_PROPIO)
    ]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _a_dict(c: Cambio) -> dict:
    return {"sha": c.sha, "titulo": c.titulo, "pr": c.pr}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registro", type=Path, required=True)
    ap.add_argument("--desde", required=True)
    ap.add_argument("--hasta", required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args(argv)
    rango = f"{a.desde}..{a.hasta}"
    cambios = parsear_log(_git("log", "--no-merges", f"--format={FORMATO_LOG}", "--name-only", rango))
    grupos = relevantes(cambios, cargar(a.registro))
    nuevos = workflows_nuevos(
        _git("diff", "--name-only", "--diff-filter=A", a.desde, a.hasta, "--", ".github/workflows/")
    )
    datos = {
        "por_arreglo": {k: [_a_dict(c) for c in v] for k, v in grupos.items() if k != "_areas"},
        "areas": [_a_dict(c) for c in grupos["_areas"]],
        "workflows_nuevos": nuevos,
    }
    a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
