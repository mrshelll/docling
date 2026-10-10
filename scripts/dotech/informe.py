"""Título, cuerpo y estado de la solicitud de sincronización."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from registro import Arreglo, cargar

# Nada se enlaza ni menciona al original: GitHub crearía referencias cruzadas y avisos allí.
REF_PR = "`docling-project/docling#{}`"
MARCA = "[conflicto para revisar a mano]"
VEREDICTOS = {
    "sobra": "Sobra: el original ya lo resuelve. Proponer retirarlo.",
    "hace_falta": "Sigue haciendo falta.",
    "no_concluyente": "No concluyente: su test no pudo correr sobre el original. Revisar a mano.",
}


@dataclass(frozen=True)
class Alertas:
    """Motivos de revisión a mano que no salen de los tests."""

    marca_previa: bool = False                   # la solicitud abierta ya llevaba la MARCA
    marcas: bool = False                         # la rama tiene <<<<<<< / >>>>>>>
    fuera_del_conflicto: tuple[str, ...] = ()    # Claude tocó archivos que no estaban en conflicto
    propios: tuple[str, ...] = ()                # la rama cambia workflows dotech-* o scripts/dotech/

    def motivo(self) -> str | None:
        if self.marcas:
            return "La rama tiene marcas de conflicto (<<<<<<< / >>>>>>>) sin resolver"
        if self.propios:
            return f"La sincronización cambia {len(self.propios)} archivos de la automatización dotech"
        if self.fuera_del_conflicto:
            return f"Claude cambió {len(self.fuera_del_conflicto)} archivos que no estaban en conflicto"
        if self.marca_previa:
            return "Marcada para revisar a mano: quita la marca del título y relanza dotech-abrir-solicitud"
        return None


def marca_pendiente(titulo_actual: str) -> bool:
    return MARCA in (titulo_actual or "")


def titulo(tag: str, revisar_a_mano: bool) -> str:
    base = f"Pasar a {tag}"
    return f"{MARCA} {base}" if revisar_a_mano else base


def _conflicto_resuelto(resumen: dict | None) -> bool:
    return bool(resumen and resumen.get("resuelto"))


def revisar_a_mano(
    comparacion: dict, conflicto: bool, resumen_conflicto: dict | None, alertas: Alertas = Alertas(),
) -> bool:
    if alertas.motivo():
        return True
    return conflicto and (not _conflicto_resuelto(resumen_conflicto) or comparacion["bloquea"])


def estado_tests(
    comparacion: dict, conflicto: bool, resumen_conflicto: dict | None, alertas: Alertas = Alertas(),
) -> tuple[str, str]:
    if conflicto and not _conflicto_resuelto(resumen_conflicto):
        return "failure", "Claude no dio por resuelto el conflicto"
    if motivo := alertas.motivo():
        return "failure", motivo[:140]
    if comparacion["corridas_rotas"]:
        return "failure", f"Corridas sin resultado: {', '.join(comparacion['corridas_rotas'])}"[:140]
    if comparacion["nuestras"]:
        return "failure", f"{len(comparacion['nuestras'])} fallos nuestros"
    return "success", f"Sin fallos nuestros ({len(comparacion['del_original'])} del original)"


def _seguro(texto: str) -> str:
    """Neutraliza menciones, referencias `#N` y HTML en texto que no controlamos."""
    texto = str(texto).replace("@", "@\u200b").replace("<", "&lt;").replace(">", "&gt;")
    texto = re.sub(r"(?i)github\.com", lambda m: m.group()[:6] + "\u200b" + m.group()[6:], texto)
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


def _lista_de_archivos(archivos: tuple[str, ...]) -> list[str]:
    return [f"- `{_celda(a)}`" for a in archivos]


def _revisar_a_mano(alertas: Alertas) -> list[str]:
    if not alertas.motivo():
        return []
    l = ["## ⚠️ Revisar a mano", ""]
    if alertas.marcas:
        l += ["- La rama tiene marcas de conflicto (`<<<<<<<` / `>>>>>>>`) sin resolver.", ""]
    if alertas.propios:
        l += ["- La sincronización cambia archivos de la propia automatización (workflows `dotech-*` "
              "o `scripts/dotech/`). Una versión del original nunca debería tocarlos:"]
        l += [f"  {x}" for x in _lista_de_archivos(alertas.propios)] + [""]
    if alertas.fuera_del_conflicto:
        l += ["- Claude cambió archivos que no estaban en conflicto (no se revirtieron):"]
        l += [f"  {x}" for x in _lista_de_archivos(alertas.fuera_del_conflicto)] + [""]
    if alertas.marca_previa:
        l += [f"- Una ejecución anterior marcó esta solicitud para revisar a mano (ver sus comentarios). "
              f"Cuando esté revisada, quita «{MARCA}» del título y vuelve a lanzar "
              "`dotech-abrir-solicitud` con la rama de esta solicitud: hasta entonces `dotech/tests` "
              "sale en rojo.", ""]
    return l


def _seccion_conflicto(conflicto: bool, resumen_conflicto: dict | None) -> list[str]:
    if not conflicto:
        return []
    l = ["## Conflicto resuelto por Claude (Sonnet)", ""]
    if not _conflicto_resuelto(resumen_conflicto):
        l += ["**Claude no lo dio por resuelto.** Revisar a mano.", ""]
    archivos = (resumen_conflicto or {}).get("archivos", [])
    archivos = [x for x in archivos if isinstance(x, dict)] if isinstance(archivos, list) else []
    if archivos:
        l += ["| archivo | qué cambió el original | qué decidió | tests |", "|---|---|---|---|"]
        l += [f"| `{_celda(x.get('archivo', ''))}` | {_celda(x.get('original', ''))} | "
              f"{_celda(x.get('decision', ''))} | {_celda(x.get('tests', ''))} |" for x in archivos]
        l.append("")
    return l


def comentario_conflicto(
    *, tag: str, conflicto: bool, resumen_conflicto: dict | None, alertas: Alertas = Alertas(),
) -> str:
    """Copia del resumen del conflicto que sobrevive a que otra versión reescriba el cuerpo.

    La primera línea identifica la versión: el flujo no repite el comentario si ya existe.
    """
    if not conflicto:
        return ""
    l = [f"<!-- dotech:conflicto {re.sub(r'[^0-9A-Za-z._-]', '_', tag)} -->",
         f"Conflicto al pasar a **{_celda(tag)}**.", ""]
    l += _seccion_conflicto(conflicto, resumen_conflicto)
    if alertas.fuera_del_conflicto:
        l += ["**Claude cambió también archivos que no estaban en conflicto** (no se revirtieron):"]
        l += _lista_de_archivos(alertas.fuera_del_conflicto) + [""]
    return "\n".join(l) + "\n"


def cuerpo(
    *, tag: str, tag_anterior: str, arreglos: list[Arreglo], sobra: dict, comparacion: dict,
    lote: dict, conflicto: bool, resumen_conflicto: dict | None, explicacion: str, enlace: str,
    alertas: Alertas = Alertas(),
) -> str:
    l = [f"Pasar de **{tag_anterior}** a **{tag}** del proyecto original.", "",
         f"[Ejecución que generó este informe]({enlace})", ""]
    l += _revisar_a_mano(alertas)
    l += ["## Nuestros arreglos", "", "| arreglo | en main | veredicto |", "|---|---|---|"]
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
              "revisa que ninguno arranque al integrar en `main` (`on: push`). Los que se disparan "
              "con `pull_request` o `pull_request_target` ya corren al abrir o actualizar esta "
              "solicitud.", ""]

    l += _seccion_conflicto(conflicto, resumen_conflicto)

    l += ["## Antes de aprobar", "",
          "- [ ] Validación local: `docling-validar <número de esta solicitud>` en el Mac de Miguel",
          "- [ ] Aprobación de Miguel", "- [ ] Aprobación de Fabio", "",
          "Integrar solo con **Create a merge commit**."]
    return "\n".join(l) + "\n"


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _rutas(variable: str) -> tuple[str, ...]:
    rutas = (r.strip() for r in os.environ.get(variable, "").splitlines())
    return tuple(r for r in rutas if r)


def resumen_del_entorno() -> dict | None:
    """RESUMEN_CONFLICTO: JSON con el resumen de Claude. Ausente, roto o no-objeto → None."""
    crudo = os.environ.get("RESUMEN_CONFLICTO", "").strip()
    try:
        resumen = json.loads(crudo) if crudo else None
    except ValueError:
        return None
    return resumen if isinstance(resumen, dict) else None


def alertas_del_entorno() -> Alertas:
    """TITULO_ACTUAL: título de la solicitud abierta (vacío si no hay). MARCAS: "true" si la
    rama tiene marcas de conflicto. ARCHIVOS_DE_MAS / ARCHIVOS_PROPIOS: una ruta por línea."""
    return Alertas(
        marca_previa=marca_pendiente(os.environ.get("TITULO_ACTUAL", "")),
        marcas=os.environ.get("MARCAS", "false") == "true",
        fuera_del_conflicto=_rutas("ARCHIVOS_DE_MAS"),
        propios=_rutas("ARCHIVOS_PROPIOS"),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    for opcion in ("--registro", "--comparacion", "--sobra", "--lote", "--salida-cuerpo"):
        ap.add_argument(opcion, type=Path, required=True)
    for opcion in ("--tag", "--tag-anterior", "--enlace"):
        ap.add_argument(opcion, required=True)
    ap.add_argument("--salida-comentario", type=Path)
    a = ap.parse_args(argv)

    conflicto = os.environ.get("CONFLICTO", "false") == "true"
    resumen = resumen_del_entorno()
    alertas = alertas_del_entorno()
    comparacion = _json(a.comparacion)
    sobra = _json(a.sobra) if a.sobra.exists() else {}

    a.salida_cuerpo.write_text(cuerpo(
        tag=a.tag, tag_anterior=a.tag_anterior, arreglos=cargar(a.registro), sobra=sobra,
        comparacion=comparacion, lote=_json(a.lote), conflicto=conflicto,
        resumen_conflicto=resumen, explicacion=os.environ.get("EXPLICACION", ""), enlace=a.enlace,
        alertas=alertas,
    ), encoding="utf-8")
    if a.salida_comentario:
        a.salida_comentario.write_text(comentario_conflicto(
            tag=a.tag, conflicto=conflicto, resumen_conflicto=resumen, alertas=alertas,
        ), encoding="utf-8")
    estado, descripcion = estado_tests(comparacion, conflicto, resumen, alertas)
    print(f"titulo={titulo(a.tag, revisar_a_mano(comparacion, conflicto, resumen, alertas))}")
    print(f"estado={estado}")
    print(f"descripcion={descripcion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
