"""
Perfiles, control de acceso, base restringida de gestión de alumnos y registro de consultas.

- La sesión empieza como Estudiante. En el prototipo se cambia con «iniciar sesión <usuario>» usando las cuentas de
  prueba de restringido/permisos.csv (en producción: cuenta institucional, p. ej. Microsoft Entra ID).
- Solo la Coordinación Académica y el personal que esta habilite consultan la gestión de alumnos.
- Los datos de alumnos (sintéticos) se leen aquí y se devuelven al usuario sin pasar por el modelo de lenguaje.
- Cada consulta queda en registros/consultas.csv con fecha, usuario de prueba, perfil, tipo, fuente y resultado,
  sin guardar el texto de la conversación.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PERMISOS = AQUI / "restringido" / "permisos.csv"
ALUMNOS = AQUI / "restringido" / "alumnos_sinteticos.csv"
REGISTRO = AQUI / "registros" / "consultas.csv"
CAMPOS_REGISTRO = ["fecha", "usuario", "perfil", "tipo_consulta", "fuente", "resultado"]

ID_ALUMNO = re.compile(r"\bALU[-\s]?(\d{1,4})\b", re.I)
sesion: dict = {"usuario": "invitado", "perfil": "Estudiante"}


# ------------------------------------------------------------------ permisos y sesión
def _leer_permisos() -> list[dict]:
    with open(PERMISOS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _guardar_permisos(filas: list[dict]) -> None:
    with open(PERMISOS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def _cuenta(usuario: str) -> dict | None:
    return next((p for p in _leer_permisos() if p["usuario"].lower() == usuario.lower()), None)


def iniciar_sesion(usuario: str) -> str:
    cuenta = _cuenta(usuario)
    if not cuenta:
        registrar("inicio_sesion", "permisos.csv", "denegado")
        return (f"No encontré la cuenta «{usuario}». Cuentas de prueba: "
                + ", ".join(p["usuario"] for p in _leer_permisos()) + ".")
    sesion.update(usuario=cuenta["usuario"], perfil=cuenta["perfil"])
    registrar("inicio_sesion", "permisos.csv", "permitido")
    extra = (" Tienes habilitada la gestión de alumnos." if puede_gestionar()
             else " No tienes habilitada la gestión de alumnos.")
    return f"Sesión iniciada como **{cuenta['usuario']}** (perfil: {cuenta['perfil']}).{extra}"


def cerrar_sesion() -> str:
    registrar("cierre_sesion", "-", "permitido")
    sesion.update(usuario="invitado", perfil="Estudiante")
    return "Sesión cerrada. Ahora estás como invitado (perfil: Estudiante)."


def puede_gestionar() -> bool:
    cuenta = _cuenta(sesion["usuario"])
    return bool(cuenta) and cuenta["gestion_alumnos"].strip().lower() == "si" \
        and cuenta["perfil"] in ("Coordinación Académica", "Personal")


def describir_sesion() -> str:
    return (f"Estás como **{sesion['usuario']}** (perfil: {sesion['perfil']}). Gestión de alumnos: "
            + ("habilitada." if puede_gestionar() else "no habilitada."))


def cambiar_habilitacion(usuario: str, habilitar: bool) -> str:
    """Solo la Coordinación Académica habilita o retira el acceso del personal a la gestión de alumnos."""
    if sesion["perfil"] != "Coordinación Académica":
        registrar("habilitacion", "permisos.csv", "denegado")
        return "Solo la Coordinación Académica puede habilitar o retirar el acceso a la gestión de alumnos."
    filas = _leer_permisos()
    cuenta = next((p for p in filas if p["usuario"].lower() == usuario.lower()), None)
    if not cuenta or cuenta["perfil"] != "Personal":
        return "Solo se puede habilitar a cuentas del perfil Personal (administrativo o docente)."
    cuenta["gestion_alumnos"] = "si" if habilitar else "no"
    cuenta["habilitado_por"] = sesion["usuario"] if habilitar else ""
    _guardar_permisos(filas)
    registrar("habilitacion", "permisos.csv", "permitido")
    return f"Listo: {cuenta['usuario']} {'ahora tiene' if habilitar else 'ya no tiene'} acceso a la gestión de alumnos."


# ------------------------------------------------------------------ registro de consultas (auditoría)
def registrar(tipo: str, fuente: str, resultado: str) -> None:
    REGISTRO.parent.mkdir(exist_ok=True)
    nuevo = not REGISTRO.exists()
    with open(REGISTRO, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_REGISTRO)
        if nuevo:
            w.writeheader()
        w.writerow({"fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "usuario": sesion["usuario"],
                    "perfil": sesion["perfil"], "tipo_consulta": tipo, "fuente": fuente, "resultado": resultado})


# ------------------------------------------------------------------ base restringida: gestión de alumnos
def _alumnos() -> list[dict]:
    with open(ALUMNOS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _ficha(a: dict) -> str:
    return (f"**{a['id_alumno']}** (dato sintético)\n- Programa: {a['programa']} – {a['curso']} – {a['sede']} "
            f"({a['periodo']})\n- Matrícula: {a['estado_matricula']}\n- Asistencia: {a['porcentaje_asistencia']} % "
            f"({a['inasistencias']} inasistencia(s))\n- Cursos inscritos: {a['cursos_inscritos']}\n"
            f"- Situación administrativa: {a['situacion_administrativa']}\n(actualizado al {a['actualizado_al']})")


DENEGADO = ("Lo siento, la gestión de alumnos solo está disponible para la Coordinación Académica y el personal que "
            "esta habilite. Con tu perfil no puedo mostrar datos de alumnos. Si necesitas acceso, solicítalo a la "
            "Coordinación Académica.")


def consultar_gestion(texto: str) -> str:
    """Consulta la base restringida si el perfil está autorizado; si no, la deniega y lo registra."""
    if not puede_gestionar():
        registrar("gestion_alumnos", "alumnos_sinteticos.csv", "denegado")
        return DENEGADO
    alumnos = _alumnos()
    m = ID_ALUMNO.search(texto)
    if m:
        ident = f"ALU-{int(m.group(1)):04d}"
        a = next((x for x in alumnos if x["id_alumno"] == ident), None)
        registrar("gestion_alumnos", "alumnos_sinteticos.csv", "permitido" if a else "sin_resultado")
        if not a:
            return f"No existe el alumno {ident} en la base de gestión (sintética)."
        return _ficha(a) + "\nFuente: base restringida alumnos_sinteticos.csv (datos sintéticos)."
    norm = texto.lower()
    registrar("gestion_alumnos", "alumnos_sinteticos.csv", "permitido")
    if "asistencia" in norm or "inasist" in norm:
        bajos = sorted((a for a in alumnos if float(a["porcentaje_asistencia"]) < 70 and a["estado_matricula"] != "Retirada"),
                       key=lambda a: float(a["porcentaje_asistencia"]))
        return (f"Alumnos activos con asistencia menor a 70 %: {len(bajos)} de {len(alumnos)}.\n"
                + "\n".join(f"- {a['id_alumno']}: {a['porcentaje_asistencia']} % – {a['curso']} ({a['sede']})"
                            for a in bajos[:10])
                + ("\n- …" if len(bajos) > 10 else "")
                + "\nSugerencia: que la Coordinación revise cada caso; el asistente no toma decisiones."
                + "\nFuente: base restringida alumnos_sinteticos.csv (datos sintéticos).")
    if "pago" in norm or "deuda" in norm or "administrativ" in norm:
        pend = [a for a in alumnos if a["situacion_administrativa"] in ("Pago pendiente", "Incidencia de pago")]
        return (f"Alumnos con pago pendiente o incidencia de pago: {len(pend)} de {len(alumnos)}.\n"
                + "\n".join(f"- {a['id_alumno']}: {a['situacion_administrativa']} – {a['curso']}" for a in pend[:10])
                + ("\n- …" if len(pend) > 10 else "")
                + "\nFuente: base restringida alumnos_sinteticos.csv (datos sintéticos).")
    estados = {}
    for a in alumnos:
        estados[a["estado_matricula"]] = estados.get(a["estado_matricula"], 0) + 1
    return (f"Resumen de la gestión de alumnos ({len(alumnos)} registros sintéticos): "
            + ", ".join(f"{k}: {n}" for k, n in sorted(estados.items())) + ".\n"
            "Puedes consultar un alumno por su código (por ejemplo «alumno ALU-0007»), los alumnos con "
            "asistencia baja o los que tienen pagos pendientes.\n"
            "Fuente: base restringida alumnos_sinteticos.csv (datos sintéticos).")
