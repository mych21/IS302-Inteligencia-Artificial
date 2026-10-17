"""
Perfiles, control de acceso, base restringida de gestión de alumnos y registro de consultas.

- Los estudiantes usan el asistente sin iniciar sesión (perfil público «Estudiante»): base general, vacantes y
  pre-inscripción.
- El personal (Personal, Coordinación Académica y Soporte TI) inicia sesión con usuario y contraseña. Las cuentas
  están en restringido/usuarios.csv con la contraseña cifrada (PBKDF2 con sal); la de prueba es 12345.
  En producción: cuenta institucional (p. ej. Microsoft Entra ID).
- Antes de cada consulta se verifica el rol y sus permisos (PERMISOS_POR_PERFIL).
- Solo la Coordinación Académica y el personal que esta habilite consultan la gestión de alumnos.
- Los datos de alumnos (sintéticos) se devuelven al usuario sin pasar por el modelo de lenguaje.
- Cada consulta queda en registros/consultas.csv con fecha, usuario, perfil, tipo, fuente y resultado, sin
  guardar el texto de la conversación (tampoco contraseñas).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import re
import secrets
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
USUARIOS = AQUI / "restringido" / "usuarios.csv"
ALUMNOS = AQUI / "restringido" / "alumnos_sinteticos.csv"
# El registro de matrícula (restringido/matricula.csv) lo administra matricula.py
REGISTRO = AQUI / "registros" / "consultas.csv"
CAMPOS_REGISTRO = ["fecha", "usuario", "perfil", "tipo_consulta", "fuente", "resultado"]
CAMPOS_USUARIOS = ["usuario", "perfil", "sal", "clave_hash", "gestion_alumnos", "habilitado_por", "descripcion"]
ITERACIONES = 100_000

ID_ALUMNO = re.compile(r"\bALU[-\s]?(\d{1,4})\b", re.I)
PUBLICO = {"usuario": "publico", "perfil": "Estudiante"}
sesion: dict = dict(PUBLICO)
pendiente: dict = {}            # usuario que está ingresando su contraseña

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


# ------------------------------------------------------------------ usuarios y contraseñas
def cifrar(clave: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), ITERACIONES).hex()


def nueva_clave(clave: str) -> tuple[str, str]:
    sal = secrets.token_hex(16)
    return sal, cifrar(clave, sal)


def _leer_usuarios() -> list[dict]:
    with open(USUARIOS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _guardar_usuarios(filas: list[dict]) -> None:
    with open(USUARIOS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_USUARIOS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def _cuenta(usuario: str) -> dict | None:
    return next((p for p in _leer_usuarios() if p["usuario"].lower() == usuario.lower()), None)


# ------------------------------------------------------------------ sesión
def iniciar_sesion(usuario: str, clave: str | None = None) -> str:
    """Inicio de sesión del personal. Sin contraseña, la pide en el siguiente mensaje."""
    cuenta = _cuenta(usuario)
    if not cuenta:
        pendiente.clear()
        registrar("inicio_sesion", "usuarios.csv", "denegado")
        return ("No existe esa cuenta de personal. Si eres estudiante no necesitas iniciar sesión: pregúntame "
                "directamente por cursos, vacantes o tu pre-inscripción.")
    if clave is None:
        pendiente.update(usuario=cuenta["usuario"])
        return f"🔐 Ingresa la contraseña de **{cuenta['usuario']}** (escribe «cancelar» para salir)."
    pendiente.clear()
    if not hmac.compare_digest(cifrar(clave, cuenta["sal"]), cuenta["clave_hash"]):
        registrar("inicio_sesion", "usuarios.csv", "denegado")
        return "Usuario o contraseña incorrectos."
    sesion.update(usuario=cuenta["usuario"], perfil=cuenta["perfil"])
    registrar("inicio_sesion", "usuarios.csv", "permitido")
    return (f"✅ Sesión iniciada como **{cuenta['usuario']}** (perfil: {cuenta['perfil']}).\n"
            f"Con este perfil puedes consultar: {DESCRIPCION_PERMISOS.get(cuenta['perfil'], 'información general')}.\n"
            "¿En qué te puedo ayudar?")


def cerrar_sesion() -> str:
    pendiente.clear()
    if not autenticado():
        return "No hay una sesión de personal abierta. Puedes seguir consultando como estudiante."
    registrar("cierre_sesion", "-", "permitido")
    sesion.update(PUBLICO)
    return "Sesión cerrada. Sigues usando el asistente como estudiante (sin sesión)."


def autenticado() -> bool:
    """True si hay un miembro del personal con sesión iniciada."""
    return sesion["usuario"] != PUBLICO["usuario"]


def autorizar(tipo: str) -> bool:
    """Verifica, antes de cada consulta, si el perfil de la sesión puede hacer ese tipo de consulta."""
    permitido = tipo in PERMISOS_POR_PERFIL.get(sesion["perfil"], set())
    return permitido and (tipo != "gestion" or puede_gestionar())


def puede_gestionar() -> bool:
    if not autenticado():
        return False
    cuenta = _cuenta(sesion["usuario"])
    return bool(cuenta) and cuenta["gestion_alumnos"].strip().lower() == "si" \
        and cuenta["perfil"] in ("Coordinación Académica", "Personal")


def describir_sesion() -> str:
    if not autenticado():
        return "Estás usando el asistente como estudiante (no necesitas iniciar sesión)."
    return (f"Estás como **{sesion['usuario']}** (perfil: {sesion['perfil']}). Puedes consultar: "
            f"{DESCRIPCION_PERMISOS.get(sesion['perfil'], 'información general')}. Gestión de alumnos: "
            + ("habilitada (también puedes revisar los «pagos por confirmar» y aprobarlos o rechazarlos)."
               if puede_gestionar() else "no habilitada."))


def cambiar_habilitacion(usuario: str, habilitar: bool) -> str:
    """Solo la Coordinación Académica habilita o retira el acceso del personal a la gestión de alumnos."""
    if sesion["perfil"] != "Coordinación Académica":
        registrar("habilitacion", "usuarios.csv", "denegado")
        return "Solo la Coordinación Académica puede habilitar o retirar el acceso a la gestión de alumnos."
    filas = _leer_usuarios()
    cuenta = next((p for p in filas if p["usuario"].lower() == usuario.lower()), None)
    if not cuenta or cuenta["perfil"] != "Personal":
        return "Solo se puede habilitar a cuentas del perfil Personal (administrativo o docente)."
    cuenta["gestion_alumnos"] = "si" if habilitar else "no"
    cuenta["habilitado_por"] = sesion["usuario"] if habilitar else ""
    _guardar_usuarios(filas)
    registrar("habilitacion", "usuarios.csv", "permitido")
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


CAMPOS_ALUMNOS = ["id_alumno", "nombre", "numero_documento", "telefono", "correo", "programa", "curso", "sede", "periodo", "estado_matricula",
                  "porcentaje_asistencia", "inasistencias", "cursos_inscritos", "situacion_administrativa",
                  "actualizado_al"]


def _guardar_alumnos(filas: list[dict]) -> None:
    with open(ALUMNOS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_ALUMNOS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def alumno_para_inscripcion(nombre: str, correo: str, curso: str, sede: str, periodo: str, programa: str,
                            numero_documento: str = "", telefono: str = "") -> str:
    """Devuelve el código del alumno (lo crea en el padrón de alumnos si es nuevo, buscando por correo).
    Así matricula.csv y alumnos_sinteticos.csv usan siempre los mismos códigos ALU-…"""
    alumnos = _alumnos()
    hoy = datetime.now().strftime("%d/%m/%Y")
    a = next((x for x in alumnos if numero_documento and x.get("numero_documento") == numero_documento), None) or \
        next((x for x in alumnos if x.get("correo", "").lower() == correo.strip().lower()), None)
    if a:
        a.update(telefono=telefono or a.get("telefono", ""), correo=correo.strip() or a.get("correo", ""),
                 numero_documento=a.get("numero_documento") or numero_documento)
        a.update(curso=curso, sede=sede, periodo=periodo, estado_matricula="Pendiente de pago",
                 situacion_administrativa="Pago pendiente", actualizado_al=hoy,
                 cursos_inscritos=str(int(a.get("cursos_inscritos") or 0) + 1))
    else:
        ultimo = max([int(x["id_alumno"][4:]) for x in alumnos if x["id_alumno"].startswith("ALU-")] + [0])
        a = {"id_alumno": f"ALU-{ultimo + 1:04d}", "nombre": nombre.strip(), "numero_documento": numero_documento,
             "telefono": telefono, "correo": correo.strip(),
             "programa": programa, "curso": curso, "sede": sede, "periodo": periodo,
             "estado_matricula": "Pendiente de pago", "porcentaje_asistencia": "", "inasistencias": "0",
             "cursos_inscritos": "1", "situacion_administrativa": "Pago pendiente", "actualizado_al": hoy}
        alumnos.append(a)
    _guardar_alumnos(alumnos)
    return a["id_alumno"]


def marcar_alumno_activo(id_alumno: str) -> None:
    """Tras validar el pago: matrícula activa y situación administrativa al día."""
    alumnos = _alumnos()
    a = next((x for x in alumnos if x["id_alumno"] == id_alumno), None)
    if a:
        a.update(estado_matricula="Activa", situacion_administrativa="Al día",
                 actualizado_al=datetime.now().strftime("%d/%m/%Y"))
        _guardar_alumnos(alumnos)


def _ficha(a: dict) -> str:
    contacto = (f"\n- Nombre: {a['nombre']}\n- Documento: {a.get('numero_documento') or '-'}\n"
                f"- Teléfono: {a.get('telefono') or '-'}\n- Correo: {a['correo']}") if a.get("nombre") else ""
    asistencia = (f"{a['porcentaje_asistencia']} % ({a['inasistencias']} inasistencia(s))"
                  if a.get("porcentaje_asistencia") else "sin clases registradas aún")
    origen = "dato sintético" if int(a["id_alumno"][4:]) <= 200 else "inscrito por el asistente"
    return (f"**{a['id_alumno']}** ({origen}){contacto}\n- Programa: {a['programa']} – {a['curso']} – {a['sede']} "
            f"({a['periodo']})\n- Matrícula: {a['estado_matricula']}\n- Asistencia: {asistencia}\n"
            f"- Cursos inscritos: {a['cursos_inscritos']}\n"
            f"- Situación administrativa: {a['situacion_administrativa']}\n(actualizado al {a['actualizado_al']})")


def _linea_matricula(x: dict) -> str:
    quien = f"{x['id_alumno']}" + (f" ({x['nombre']}, doc. {x.get('numero_documento') or '-'}, "
                                    f"tel. {x.get('telefono') or '-'})" if x.get("nombre") else "")
    horario = f" · {x['horario']}" if x.get("horario") else ""
    return f"- {x['codigo_matricula']} · {quien} · {x['curso']} · {x['sede']}{horario} · {x['periodo']} · {x['estado']}"


def _resumen_matricula(matriculas: list[dict], norm: str) -> str:
    """Respuestas sobre el registro de matrícula: totales, por curso o por estado."""
    import matricula as reg
    filas = matriculas
    cursos = reg.detectar_cursos(norm)
    if cursos:
        filas = [x for x in filas if x["curso"] in cursos]
    if "retirad" in norm:
        filas = [x for x in filas if x["estado"] == "Retirado"]
    elif "pendiente" in norm or "pre inscrit" in norm or "preinscrit" in norm:
        filas = [x for x in filas if x["estado"].startswith(("Pendiente", "Pre-inscrito", "Pago por confirmar"))]
    matriculados = [x for x in filas if x["estado"] == "Matriculado"]
    estados, periodos = {}, {}
    for x in filas:
        estados[x["estado"]] = estados.get(x["estado"], 0) + 1
    for x in matriculados:
        periodos[x["periodo"]] = periodos.get(x["periodo"], 0) + 1
    titulo = f" en {', '.join(cursos)}" if cursos else ""
    if "retirad" in norm:
        cabecera = f"**Alumnos retirados{titulo}: {len(filas)}**"
    elif "pendiente" in norm or "inscrit" in norm and "pre" in norm:
        cabecera = f"**Matrículas pendientes de pago{titulo}: {len(filas)}**"
    else:
        cabecera = f"**Alumnos matriculados{titulo}: {len(matriculados)}** (de {len(filas)} registros de matrícula)"
    lineas = [cabecera + ".",
              "Por estado: " + ", ".join(f"{k}: {v}" for k, v in sorted(estados.items())) + ".",
              "Matriculados por periodo: " + (", ".join(f"{k}: {v}" for k, v in sorted(periodos.items())) or "—") + "."]
    muestra = [x for x in filas if x.get("origen") == "asistente"] + [x for x in filas if x.get("origen") != "asistente"]
    if muestra:
        lineas.append("Registros (primeros 10):")
        lineas += [_linea_matricula(x) for x in muestra[:10]]
        if len(muestra) > 10:
            lineas.append(f"- … y {len(muestra) - 10} más.")
    lineas.append("Fuente: base restringida matricula.csv (datos sintéticos y matrículas del asistente).")
    return "\n".join(lineas)


DENEGADO = ("Lo siento, la gestión de alumnos solo está disponible para la Coordinación Académica y el personal que "
            "esta habilite. Con tu perfil no puedo mostrar datos de alumnos. Si necesitas acceso, solicítalo a la "
            "Coordinación Académica.")


def consultar_gestion(texto: str) -> str:
    """Consulta la base restringida si el perfil está autorizado; si no, la deniega y lo registra."""
    if not autorizar("gestion"):
        registrar("gestion_alumnos", "alumnos_sinteticos.csv", "denegado")
        return DENEGADO
    import matricula as reg
    alumnos = _alumnos()
    matriculas = reg._leer_matriculas()
    m = ID_ALUMNO.search(texto)
    if m:
        ident = f"ALU-{int(m.group(1)):04d}"
        a = next((x for x in alumnos if x["id_alumno"] == ident), None)
        suyas = [x for x in matriculas if x.get("id_alumno") == ident]
        registrar("gestion_alumnos", "alumnos_sinteticos.csv", "permitido" if (a or suyas) else "sin_resultado")
        if not a and not suyas:
            return f"No existe el alumno {ident} en la base de gestión."
        partes = [_ficha(a)] if a else [f"**{ident}**" + (f" – {suyas[0]['nombre']}" if suyas[0].get("nombre") else "")]
        if suyas:
            partes.append("Matrículas:\n" + "\n".join(_linea_matricula(x) for x in suyas))
        return "\n".join(partes) + "\nFuente: base restringida (alumnos_sinteticos.csv y matricula.csv)."
    norm = re.sub(r"[áéíóú]", lambda c: "aeiou"["áéíóú".index(c.group())], texto.lower())
    if re.search(r"matricul|inscrit|retirad", norm):
        return _resumen_matricula(matriculas, norm)
    registrar("gestion_alumnos", "alumnos_sinteticos.csv", "permitido")
    if "asistencia" in norm or "inasist" in norm:
        bajos = sorted((a for a in alumnos if a["porcentaje_asistencia"] and float(a["porcentaje_asistencia"]) < 70
                        and a["estado_matricula"] != "Retirada"),
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
    filas = list(csv.DictReader(REGISTRO.read_text(encoding="utf-8").splitlines())) if REGISTRO.exists() else []
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
        registrar("permisos", "usuarios.csv", "denegado")
        return "Solo la Coordinación Académica puede revisar los permisos."
    registrar("permisos", "usuarios.csv", "permitido")
    return "Permisos de gestión de alumnos:\n" + "\n".join(
        f"- {p['usuario']} ({p['perfil']}): {'sí' if p['gestion_alumnos'] == 'si' else 'no'}"
        + (f", habilitado por {p['habilitado_por']}" if p['habilitado_por'] else "") for p in _leer_usuarios())


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
