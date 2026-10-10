"""Lee el registro de arreglos propios del fork (`arreglos.toml`).

Cada arreglo declara qué archivos toca y qué test comprueba su comportamiento
usando solo la API del original, para poder correrlo sobre el original sin
nuestro código y saber si el arreglo sigue haciendo falta.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DIR_SCRIPTS = Path(__file__).resolve().parent
RAIZ_REPO = DIR_SCRIPTS.parent.parent
REGISTRO = DIR_SCRIPTS / "arreglos.toml"

_OBLIGATORIOS = {"clave", "nombre", "en_main", "archivos", "test_comportamiento"}


class RegistroInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Arreglo:
    clave: str
    nombre: str
    en_main: bool
    archivos: tuple[str, ...]
    test_comportamiento: str
    fixtures: tuple[str, ...] = ()
    rama: str | None = None


def cargar(ruta: Path) -> list[Arreglo]:
    datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    arreglos = []
    for i, d in enumerate(datos.get("arreglo", []), start=1):
        faltan = _OBLIGATORIOS - d.keys()
        if faltan:
            raise RegistroInvalido(f"arreglo #{i}: faltan {sorted(faltan)}")
        if not d["en_main"] and not d.get("rama"):
            raise RegistroInvalido(f"{d['clave']}: en_main = false exige 'rama'")
        arreglos.append(
            Arreglo(
                clave=d["clave"],
                nombre=d["nombre"],
                en_main=bool(d["en_main"]),
                archivos=tuple(d["archivos"]),
                test_comportamiento=d["test_comportamiento"],
                fixtures=tuple(d.get("fixtures", ())),
                rama=d.get("rama"),
            )
        )
    if not arreglos:
        raise RegistroInvalido("el registro no tiene arreglos")
    claves = [a.clave for a in arreglos]
    if len(set(claves)) != len(claves):
        raise RegistroInvalido(f"claves repetidas: {claves}")
    return arreglos
