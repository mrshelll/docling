"""Desactiva los workflows heredados del original en cada ejecución.

Se desactivan en la configuración de GitHub, no borrando los archivos: borrarlos
haría chocar cada sincronización en la que el original los modifique. Los
dinámicos de GitHub (`dynamic/...`) no se tocan.
"""

from __future__ import annotations

import argparse
import json
import subprocess

_PROPIOS = ".github/workflows/dotech-"
_ARCHIVOS = ".github/workflows/"


def a_desactivar(workflows: list[dict]) -> list[dict]:
    return [
        w for w in workflows
        if w.get("state") == "active"
        and w.get("path", "").startswith(_ARCHIVOS)
        and not w["path"].startswith(_PROPIOS)
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args(argv)
    salida = subprocess.run(
        ["gh", "api", f"repos/{a.repo}/actions/workflows", "--paginate", "--jq", ".workflows[]"],
        check=True, capture_output=True, text=True,
    ).stdout
    workflows = [json.loads(linea) for linea in salida.splitlines() if linea.strip()]
    for w in a_desactivar(workflows):
        subprocess.run(
            ["gh", "api", "-X", "PUT", f"repos/{a.repo}/actions/workflows/{w['id']}/disable"],
            check=True, capture_output=True,
        )
        print(f"desactivado: {w['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
