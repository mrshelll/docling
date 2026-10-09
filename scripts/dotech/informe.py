"""Título, cuerpo y estado de la solicitud de sincronización."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from registro import Arreglo, cargar

# Nada se enlaza ni menciona al original: GitHub crearía referencias cruzadas y avisos allí.
REF_PR = "`docling-project/docling#{}`"
VEREDICTOS = {
    "sobra": "Sobra: el original ya lo resuelve. Proponer retirarlo.",
    "hace_falta": "Sigue haciendo falta.",
    "no_concluyente": "No concluyente: su test no pudo correr sobre el original. Revisar a mano.",
}


def titulo(tag: str, revisar_a_mano: bool) -> str:
    base = f"Pasar a {tag}"
    return f"[conflicto para revisar a mano] {base}" if revisar_a_mano else base


def _conflicto_resuelto(resumen: dict | None) -> bool:
    return bool(resumen and resumen.get("resuelto"))


def revisar_a_mano(comparacion: dict, conflicto: bool, resumen_conflicto: dict | None) -> bool:
    return conflicto and (not _conflicto_resuelto(resumen_conflicto) or comparacion["bloquea"])


def estado_tests(comparacion: dict, conflicto: bool, resumen_conflicto: dict | None) -> tuple[str, str]:
    if conflicto and not _conflicto_resuelto(resumen_conflicto):
        return "failure", "Claude no dio por resuelto el conflicto"
    if comparacion["corridas_rotas"]:
        return "failure", f"Corridas sin resultado: {', '.join(comparacion['corridas_rotas'])}"[:140]
    if comparacion["nuestras"]:
        return "failure", f"{len(comparacion['nuestras'])} fallos nuestros"
    return "success", f"Sin fallos nuestros ({len(comparacion['del_original'])} del original)"


def _seguro(texto: str) -> str:
    """Neutraliza menciones, referencias `#N` y HTML en texto que no controlamos."""
    texto = str(texto).replace("@", "@\u200b").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"#(?=\d)", "#\u200b", texto)


def _celda(texto: str) -> str:
    return _seguro(" ".join(str(texto).split())).replace("|", "\\|")


def _cambio(c: dict) -> str:
    titulo_ = c["titulo"]
    if c.get("pr"):
        titulo_ = re.sub(r"\s*\(#\d+\)\s*$", "", titulo_)
        ref = REF_PR.format(c["pr"])
    else:
        ref = f"`{c['sha'][:8]}`"
    return f"- {_celda(titulo_)} ({ref})"


def cuerpo(
    *, tag: str, tag_anterior: str, arreglos: list[Arreglo], sobra: dict, comparacion: dict,
    lote: dict, conflicto: bool, resumen_conflicto: dict | None, explicacion: str, enlace: str,
) -> str:
    l = [f"Pasar de **{tag_anterior}** a **{tag}** del proyecto original.", "",
         f"[Ejecución que generó este informe]({enlace})", "",
         "## Nuestros arreglos", "", "| arreglo | en main | veredicto |", "|---|---|---|"]
    for a in arreglos:
        v = sobra.get(a.clave, {}).get("veredicto", "no_concluyente")
        l.append(f"| {_celda(a.nombre)} | {'sí' if a.en_main else 'no'} | {VEREDICTOS[v]} |")

    l += ["", "## Tests", ""]
    if comparacion["corridas_rotas"]:
        l.append(f"**Corridas rotas** (no se pudo leer su resultado): "
                 f"{', '.join(comparacion['corridas_rotas'])}. Esto bloquea.")
        l.append("")
    l.append(f"**Fallos nuestros (bloquean): {len(comparacion['nuestras'])}**")
    for tid in comparacion["nuestras"]:
        l.append(f"- `{tid}` — {_celda(comparacion['mensajes'].get(tid, ''))[:300]}")
    l += ["", f"<details><summary>Fallos que ya trae el original (no bloquean): "
              f"{len(comparacion['del_original'])}</summary>", ""]
    l += [f"- `{tid}`" for tid in comparacion["del_original"]]
    l += ["", "</details>"]
    if explicacion:
        l += ["", "### Causa probable (Claude Haiku)", ""]
        l += [f"> {_seguro(linea)}".rstrip() for linea in explicacion.strip().splitlines()]

    l += ["", "## Cambios del lote que nos tocan", ""]
    por_nombre = {a.clave: a.nombre for a in arreglos}
    for clave, cambios in lote["por_arreglo"].items():
        if cambios:
            l.append(f"**{por_nombre.get(clave, clave)}**")
            l += [_cambio(c) for c in cambios]
            l.append("")
    if lote["areas"]:
        l.append("**Otras áreas (layout, tablas, VLM, PDF)**")
        l += [_cambio(c) for c in lote["areas"]]
        l.append("")
    if lote["workflows_nuevos"]:
        l += ["## ⚠️ Automatismos nuevos del original", ""]
        l += [f"- `{w}`" for w in lote["workflows_nuevos"]]
        l += ["", "La sincronización los desactiva en su siguiente ejecución. Antes de aprobar, "
              "revisa que ninguno arranque al integrar en `main` (`on: push`).", ""]

    if conflicto:
        l += ["## Conflicto resuelto por Claude (Sonnet)", ""]
        if not _conflicto_resuelto(resumen_conflicto):
            l += ["**Claude no lo dio por resuelto.** Revisar a mano.", ""]
        archivos = (resumen_conflicto or {}).get("archivos", [])
        archivos = [x for x in archivos if isinstance(x, dict)] if isinstance(archivos, list) else []
        if archivos:
            l += ["| archivo | qué cambió el original | qué decidió | tests |", "|---|---|---|---|"]
            l += [f"| `{_celda(x.get('archivo', ''))}` | {_celda(x.get('original', ''))} | "
                  f"{_celda(x.get('decision', ''))} | {_celda(x.get('tests', ''))} |" for x in archivos]
            l.append("")

    l += ["## Antes de aprobar", "",
          "- [ ] Validación local: `docling-validar <número de esta solicitud>` en el Mac de Miguel",
          "- [ ] Aprobación de Miguel", "- [ ] Aprobación de Fabio", "",
          "Integrar solo con **Create a merge commit**."]
    return "\n".join(l) + "\n"


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    for opcion in ("--registro", "--comparacion", "--sobra", "--lote", "--salida-cuerpo"):
        ap.add_argument(opcion, type=Path, required=True)
    for opcion in ("--tag", "--tag-anterior", "--enlace"):
        ap.add_argument(opcion, required=True)
    a = ap.parse_args(argv)

    conflicto = os.environ.get("CONFLICTO", "false") == "true"
    crudo = os.environ.get("RESUMEN_CONFLICTO", "").strip()
    try:
        resumen = json.loads(crudo) if crudo else None
    except ValueError:
        resumen = None
    if not isinstance(resumen, dict):
        resumen = None
    comparacion = _json(a.comparacion)
    sobra = _json(a.sobra) if a.sobra.exists() else {}

    a.salida_cuerpo.write_text(cuerpo(
        tag=a.tag, tag_anterior=a.tag_anterior, arreglos=cargar(a.registro), sobra=sobra,
        comparacion=comparacion, lote=_json(a.lote), conflicto=conflicto,
        resumen_conflicto=resumen, explicacion=os.environ.get("EXPLICACION", ""), enlace=a.enlace,
    ), encoding="utf-8")
    estado, descripcion = estado_tests(comparacion, conflicto, resumen)
    print(f"titulo={titulo(a.tag, revisar_a_mano(comparacion, conflicto, resumen))}")
    print(f"estado={estado}")
    print(f"descripcion={descripcion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
