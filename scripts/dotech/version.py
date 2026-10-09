"""Decide si hay una versión nueva del original que llevar a una solicitud.

No guarda estado: git ya sabe si una versión está dentro de `main` o de la rama
de trabajo, y GitHub sabe si la última solicitud se rechazó.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass

_TITULO = re.compile(r"Pasar a (v\d+\.\d+\.\d+\S*)")


@dataclass(frozen=True)
class Decision:
    accion: str  # "nada" | "sincronizar"
    tag: str
    base: str  # rama desde la que se mezcla la versión
    motivo: str


def tag_de_titulo(titulo: str) -> str | None:
    m = _TITULO.search(titulo)
    return m.group(1) if m else None


def decidir(
    tag: str,
    *,
    rama: str,
    contiene_main: bool,
    solicitud_abierta: bool,
    contiene_rama: bool,
    tag_rechazado: str | None,
) -> Decision:
    if contiene_main:
        return Decision("nada", tag, "main", f"main ya contiene {tag}")
    if solicitud_abierta:
        if contiene_rama:
            return Decision("nada", tag, rama, f"la solicitud abierta ya contiene {tag}")
        return Decision("sincronizar", tag, rama, f"se añade {tag} a la solicitud abierta")
    if tag == tag_rechazado:
        return Decision("nada", tag, "main", f"{tag} se rechazó; se espera a la siguiente")
    return Decision("sincronizar", tag, "main", f"nueva solicitud para {tag}")


def _ejecutar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def _salida(*args: str) -> str:
    r = _ejecutar(*args)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def _es_ancestro(ref: str, de: str) -> bool:
    r = _ejecutar("git", "merge-base", "--is-ancestor", f"{ref}^{{commit}}", de)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"git merge-base {ref} {de}: {r.stderr.strip()}")
    return r.returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--rama", required=True)
    ap.add_argument("--ref", default="")
    a = ap.parse_args(argv)

    tag = a.ref or _salida(
        "gh", "api", f"repos/{a.upstream}/releases/latest", "--jq", ".tag_name"
    )
    abiertas = json.loads(_salida(
        "gh", "pr", "list", "-R", a.repo, "--head", a.rama,
        "--state", "open", "--json", "number",
    ))
    cerradas = json.loads(_salida(
        "gh", "pr", "list", "-R", a.repo, "--head", a.rama,
        "--state", "closed", "--limit", "1", "--json", "title,mergedAt",
    ))
    rechazado = (
        tag_de_titulo(cerradas[0]["title"])
        if cerradas and not cerradas[0]["mergedAt"]
        else None
    )
    existe_rama = _ejecutar(
        "git", "ls-remote", "--exit-code", "--heads", "origin", a.rama
    ).returncode == 0

    d = decidir(
        tag,
        rama=a.rama,
        contiene_main=_es_ancestro(tag, "origin/main"),
        solicitud_abierta=bool(abiertas),
        contiene_rama=bool(abiertas) and _es_ancestro(tag, f"origin/{a.rama}"),
        tag_rechazado=rechazado,
    )
    tag_anterior = _salida(
        "git", "describe", "--tags", "--abbrev=0", "--match", "v*", f"origin/{d.base}"
    )
    print(f"accion={d.accion}")
    print(f"tag={d.tag}")
    print(f"base={d.base}")
    print(f"tag_anterior={tag_anterior}")
    print(f"rama_huerfana={'true' if existe_rama and not abiertas else 'false'}")
    print(f"::notice::{d.motivo}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
