"""
Perfiles, control de acceso, base restringida de gestión de alumnos y registro de consultas.

- Nadie consulta sin autenticarse: primero «iniciar sesión <usuario>» con una cuenta de prueba de
  restringido/permisos.csv (simula la cuenta institucional; en producción, p. ej. Microsoft Entra ID).
- Antes de cada consulta se verifica el rol y sus permisos (PERMISOS_POR_PERFIL).
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
SIN_SESION = {"usuario": "sin_sesion", "perfil": "Sin autenticar"}
sesion: dict = dict(SIN_SESION)

# Qué tipo de consulta puede hacer cada perfil (la gestión de alumnos además exige estar habilitado).
PERMISOS_POR_PERFIL = {
    "Estudiante": {"general", "vacantes", "inscripcion"},
    "Personal": {"general", "vacantes", "gestion"},
    "Coordinación Académica": {"general", "vacantes", "gestion", "administracion", "registro"},
    "Soporte TI": {"general", "registro"},
}
DESCRIPCION_PERMISOS = {
    "Estudiante": "cursos, procedimientos, vacantes y tu pre-inscripción",
    "Personal": "información general y vacantes (gestión de alumnos solo si la Coordinación te habilita)",
    "Coordinación Académica": "información general, gestión de alumnos, permisos, vacantes y registro de consultas",
    "Soporte TI": "información general y registro de consultas (sin datos de alumnos)",
}


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
    return (f"✅ Sesión iniciada como **{cuenta['usuario']}** (perfil: {cuenta['perfil']}).\n"
            f"Con este perfil puedes consultar: {DESCRIPCION_PERMISOS.get(cuenta['perfil'], 'información general')}.\n"
            "¿En qué te puedo ayudar?")


def cerrar_sesion() -> str:
    registrar("cierre_sesion", "-", "permitido")
    sesion.update(SIN_SESION)
    return "Sesión cerrada. Para volver a consultar, inicia sesión con tu cuenta institucional."


def autenticado() -> bool:
    return sesion["usuario"] != SIN_SESION["usuario"]


def autorizar(tipo: str) -> bool:
    """Verifica, antes de cada consulta, si el perfil de la sesión puede hacer ese tipo de consulta."""
    if not autenticado():
        return False
    permitido = tipo in PERMISOS_POR_PERFIL.get(sesion["perfil"], set())
    return permitido and (tipo != "gestion" or puede_gestionar())


def cuentas_de_prueba() -> str:
    return "\n".join(f"- `{p['usuario']}` – {p['perfil']}" for p in _leer_permisos())


def puede_gestionar() -> bool:
    cuenta = _cuenta(sesion["usuario"])
    return bool(cuenta) and cuenta["gestion_alumnos"].strip().lower() == "si" \
        and cuenta["perfil"] in ("Coordinación Académica", "Personal")


def describir_sesion() -> str:
    if not autenticado():
        return "Aún no has iniciado sesión."
    return (f"Estás como **{sesion['usuario']}** (perfil: {sesion['perfil']}). Puedes consultar: "
            f"{DESCRIPCION_PERMISOS.get(sesion['perfil'], 'información general')}. Gestión de alumnos: "
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
    if not autorizar("gestion"):
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


# ------------------------------------------------------------------ administración (Coordinación Académica)
def ver_registro(n: int = 10) -> str:
    if not autorizar("registro"):
        registrar("registro_consultas", "consultas.csv", "denegado")
        return "Solo la Coordinación Académica y Soporte de TI pueden revisar el registro de consultas."
    registrar("registro_consultas", "consultas.csv", "permitido")
    filas = list(csv.DictReader(REGISTRO.open(encoding="utf-8"))) if REGISTRO.exists() else []
    resumen = {}
    for f in filas:
        resumen[f["resultado"]] = resumen.get(f["resultado"], 0) + 1
    return (f"Registro de consultas: {len(filas)} en total ("
            + ", ".join(f"{k}: {v}" for k, v in sorted(resumen.items())) + ").\nÚltimas consultas:\n"
            + "\n".join(f"- {f['fecha']} · {f['usuario']} ({f['perfil']}) · {f['tipo_consulta']} · {f['resultado']}"
                        for f in filas[-n:])
            + "\n(El registro no guarda el texto de las conversaciones.)")


def ver_permisos() -> str:
    if not autorizar("administracion"):
        registrar("permisos", "permisos.csv", "denegado")
        return "Solo la Coordinación Académica puede revisar los permisos."
    registrar("permisos", "permisos.csv", "permitido")
    return "Permisos de gestión de alumnos:\n" + "\n".join(
        f"- {p['usuario']} ({p['perfil']}): {'sí' if p['gestion_alumnos'] == 'si' else 'no'}"
        + (f", habilitado por {p['habilitado_por']}" if p['habilitado_por'] else "") for p in _leer_permisos())


def actualizar_vacantes(codigo_horario: str, cantidad: int) -> str:
    """La Coordinación edita el archivo de vacantes; la siguiente consulta ya usa el dato nuevo."""
    if not autorizar("administracion"):
        registrar("actualizar_vacantes", "vacantes.csv", "denegado")
        return "Solo la Coordinación Académica puede actualizar el archivo de vacantes."
    import matricula
    filas, campos, delim = matricula._leer_tabla()
    fila = next((f for f in filas if f["codigo"].upper() == codigo_horario.upper()), None)
    if not fila:
        return f"No existe el horario {codigo_horario} en el archivo de vacantes."
    antes = fila["vacantes_disponibles"]
    fila["vacantes_disponibles"] = str(max(0, cantidad))
    fila["actualizado_al"] = datetime.now().strftime("%d/%m/%Y")
    matricula._guardar_tabla(filas, campos, delim)
    registrar("actualizar_vacantes", "vacantes.csv", "permitido")
    return (f"Listo: {fila['codigo']} ({fila['curso']} – {fila['sede']} – {fila['horario']}) pasó de {antes} a "
            f"{fila['vacantes_disponibles']} vacante(s). Las siguientes consultas ya usan el dato actualizado.")
