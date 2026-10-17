"""
Datos restringidos de MALI Asistente: cuentas del personal, padrón de alumnos, registro de matrícula, pagos y
auditoría. Solo los usa el servidor MCP restringido: el modelo de lenguaje nunca recibe estos datos.

Permisos: cada operación del personal recibe el usuario que la pide y se verifica aquí, contra usuarios.csv,
con PERMISOS_POR_PERFIL (la gestión de alumnos además exige estar habilitado por la Coordinación Académica).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import re
from datetime import datetime

import conocimiento
import rutas
import texto as tx
import vacantes

ITERACIONES = 100_000
PUBLICO = {"usuario": "publico", "perfil": "Estudiante"}
PERMISOS_POR_PERFIL = {
    "Estudiante": {"general", "vacantes", "inscripcion"},
    "Personal": {"general", "vacantes", "gestion"},
    "Coordinación Académica": {"general", "vacantes", "gestion", "administracion", "registro"},
    "Soporte TI": {"general", "registro"},
}
DENEGADO = ("Lo siento, la gestión de alumnos solo está disponible para la Coordinación Académica y el personal que "
            "esta habilite. Con tu perfil no puedo mostrar datos de alumnos. Si necesitas acceso, solicítalo a la "
            "Coordinación Académica.")
ID_ALUMNO = re.compile(r"\bALU[-\s]?(\d{1,4})\b", re.I)
MATRICULA = re.compile(r"\bMAT[-\s]?(\d{1,4})\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
POR_CONFIRMAR = "Pago por confirmar (MALI)"
PENDIENTE = "Pre-inscrito (pendiente de pago)"

CAMPOS_USUARIOS = ["usuario", "perfil", "sal", "clave_hash", "gestion_alumnos", "habilitado_por", "descripcion"]
CAMPOS_ALUMNOS = ["id_alumno", "nombre", "numero_documento", "telefono", "correo", "programa", "curso", "sede",
                  "periodo", "estado_matricula", "porcentaje_asistencia", "inasistencias", "cursos_inscritos",
                  "situacion_administrativa", "actualizado_al"]
CAMPOS_MATRICULA = ["codigo_matricula", "id_alumno", "nombre", "numero_documento", "telefono", "correo", "curso",
                    "codigo_horario", "sede", "modalidad", "horario", "periodo", "fecha_inicio", "fecha_fin",
                    "estado", "codigo_pago", "fecha_registro", "origen", "validado_por", "fecha_validacion"]
CAMPOS_PAGOS = ["codigo_pago", "estado", "codigo_matricula", "fecha_uso"]
CAMPOS_REGISTRO = ["fecha", "usuario", "perfil", "tipo_consulta", "fuente", "resultado"]


def _leer(ruta) -> list[dict]:
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _guardar(ruta, campos: list[str], filas: list[dict]) -> None:
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(filas)


def _ahora() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


# ------------------------------------------------------------------ cuentas del personal y permisos
def cifrar(clave: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), ITERACIONES).hex()


def cuenta(usuario: str) -> dict | None:
    return next((p for p in _leer(rutas.usuarios()) if p["usuario"].lower() == (usuario or "").lower()), None)


def verificar_credenciales(usuario: str, clave: str) -> dict | None:
    c = cuenta(usuario)
    if c and hmac.compare_digest(cifrar(clave, c["sal"]), c["clave_hash"]):
        return {"usuario": c["usuario"], "perfil": c["perfil"]}
    return None


def perfil(usuario: str) -> str:
    if usuario == PUBLICO["usuario"]:
        return PUBLICO["perfil"]
    c = cuenta(usuario)
    return c["perfil"] if c else ""


def puede_gestionar(usuario: str) -> bool:
    c = cuenta(usuario) if usuario != PUBLICO["usuario"] else None
    return bool(c) and c["gestion_alumnos"].strip().lower() == "si" \
        and c["perfil"] in ("Coordinación Académica", "Personal")


def autorizado(usuario: str, tipo: str) -> bool:
    permitido = tipo in PERMISOS_POR_PERFIL.get(perfil(usuario), set())
    return permitido and (tipo != "gestion" or puede_gestionar(usuario))


def cambiar_habilitacion(solicitante: str, usuario: str, habilitar: bool) -> str:
    """Solo la Coordinación Académica habilita o retira el acceso del personal a la gestión de alumnos."""
    if perfil(solicitante) != "Coordinación Académica":
        registrar(solicitante, "habilitacion", "usuarios.csv", "denegado")
        return "Solo la Coordinación Académica puede habilitar o retirar el acceso a la gestión de alumnos."
    filas = _leer(rutas.usuarios())
    c = next((p for p in filas if p["usuario"].lower() == usuario.lower()), None)
    if not c or c["perfil"] != "Personal":
        return "Solo se puede habilitar a cuentas del perfil Personal (administrativo o docente)."
    c["gestion_alumnos"] = "si" if habilitar else "no"
    c["habilitado_por"] = solicitante if habilitar else ""
    _guardar(rutas.usuarios(), CAMPOS_USUARIOS, filas)
    registrar(solicitante, "habilitacion", "usuarios.csv", "permitido")
    return f"Listo: {c['usuario']} {'ahora tiene' if habilitar else 'ya no tiene'} acceso a la gestión de alumnos."


def ver_permisos(solicitante: str) -> str:
    if not autorizado(solicitante, "administracion"):
        registrar(solicitante, "permisos", "usuarios.csv", "denegado")
        return "Solo la Coordinación Académica puede revisar los permisos."
    registrar(solicitante, "permisos", "usuarios.csv", "permitido")
    return "Permisos de gestión de alumnos:\n" + "\n".join(
        f"- {p['usuario']} ({p['perfil']}): {'sí' if p['gestion_alumnos'] == 'si' else 'no'}"
        + (f", habilitado por {p['habilitado_por']}" if p['habilitado_por'] else "") for p in _leer(rutas.usuarios()))


# ------------------------------------------------------------------ auditoría
def registrar(usuario: str, tipo: str, fuente: str, resultado: str) -> None:
    """Fecha, usuario, perfil, tipo, fuente y resultado; nunca el texto de la conversación."""
    ruta = rutas.registro()
    ruta.parent.mkdir(exist_ok=True)
    nuevo = not ruta.exists()
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_REGISTRO)
        if nuevo:
            w.writeheader()
        w.writerow({"fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "usuario": usuario,
                    "perfil": perfil(usuario) or "desconocido", "tipo_consulta": tipo, "fuente": fuente,
                    "resultado": resultado})


def ver_registro(solicitante: str, n: int = 10) -> str:
    if not autorizado(solicitante, "registro"):
        registrar(solicitante, "registro_consultas", "consultas.csv", "denegado")
        return "Solo la Coordinación Académica y Soporte de TI pueden revisar el registro de consultas."
    registrar(solicitante, "registro_consultas", "consultas.csv", "permitido")
    filas = _leer(rutas.registro())
    resumen = {}
    for f in filas:
        resumen[f["resultado"]] = resumen.get(f["resultado"], 0) + 1
    return (f"Registro de consultas: {len(filas)} en total ("
            + ", ".join(f"{k}: {v}" for k, v in sorted(resumen.items())) + ").\nÚltimas consultas:\n"
            + "\n".join(f"- {f['fecha']} · {f['usuario']} ({f['perfil']}) · {f['tipo_consulta']} · {f['resultado']}"
                        for f in filas[-n:])
            + "\n(El registro no guarda el texto de las conversaciones.)")


def actualizar_vacantes(solicitante: str, codigo_horario: str, cantidad: int) -> str:
    """La Coordinación edita el archivo de vacantes; la siguiente consulta ya usa el dato nuevo."""
    if not autorizado(solicitante, "administracion"):
        registrar(solicitante, "actualizar_vacantes", "vacantes.csv", "denegado")
        return "Solo la Coordinación Académica puede actualizar el archivo de vacantes."
    r = vacantes.fijar_vacantes(codigo_horario, cantidad)
    if r is None:
        return f"No existe el horario {codigo_horario} en el archivo de vacantes."
    fila, antes = r
    registrar(solicitante, "actualizar_vacantes", "vacantes.csv", "permitido")
    return (f"Listo: {fila['codigo']} ({fila['curso']} – {fila['sede']} – {fila['horario']}) pasó de {antes} a "
            f"{fila['vacantes_disponibles']} vacante(s). Las siguientes consultas ya usan el dato actualizado.")


# ------------------------------------------------------------------ padrón de alumnos
def alumnos() -> list[dict]:
    return _leer(rutas.alumnos())


def _alumno_para_inscripcion(nombre: str, correo: str, fila_horario: dict, numero_documento: str,
                             telefono: str) -> str:
    """Código del alumno (se crea en el padrón si es nuevo, buscando por documento o correo). Así matricula.csv y
    alumnos_sinteticos.csv usan siempre los mismos códigos ALU-…"""
    padron = alumnos()
    hoy = datetime.now().strftime("%d/%m/%Y")
    programa = "Taller" if "taller" in fila_horario.get("categoria", "").lower() else "Curso"
    a = next((x for x in padron if numero_documento and x.get("numero_documento") == numero_documento), None) or \
        next((x for x in padron if x.get("correo", "").lower() == correo.strip().lower()), None)
    cambios = {"curso": fila_horario["curso"], "sede": fila_horario["sede"], "periodo": fila_horario["periodo"],
               "estado_matricula": "Pendiente de pago", "situacion_administrativa": "Pago pendiente",
               "actualizado_al": hoy}
    if a:
        a.update(telefono=telefono or a.get("telefono", ""), correo=correo.strip() or a.get("correo", ""),
                 numero_documento=a.get("numero_documento") or numero_documento,
                 cursos_inscritos=str(int(a.get("cursos_inscritos") or 0) + 1), **cambios)
    else:
        ultimo = max([int(x["id_alumno"][4:]) for x in padron if x["id_alumno"].startswith("ALU-")] + [0])
        a = {"id_alumno": f"ALU-{ultimo + 1:04d}", "nombre": nombre.strip(), "numero_documento": numero_documento,
             "telefono": telefono, "correo": correo.strip(), "programa": programa, "porcentaje_asistencia": "",
             "inasistencias": "0", "cursos_inscritos": "1", **cambios}
        padron.append(a)
    _guardar(rutas.alumnos(), CAMPOS_ALUMNOS, padron)
    return a["id_alumno"]


def _marcar_alumno_activo(id_alumno: str) -> None:
    """Tras validar el pago: matrícula activa y situación administrativa al día."""
    padron = alumnos()
    a = next((x for x in padron if x["id_alumno"] == id_alumno), None)
    if a:
        a.update(estado_matricula="Activa", situacion_administrativa="Al día",
                 actualizado_al=datetime.now().strftime("%d/%m/%Y"))
        _guardar(rutas.alumnos(), CAMPOS_ALUMNOS, padron)


# ------------------------------------------------------------------ registro de matrícula
def matriculas() -> list[dict]:
    return _leer(rutas.matriculas())


def _guardar_matriculas(filas: list[dict]) -> None:
    _guardar(rutas.matriculas(), CAMPOS_MATRICULA, filas)


def registrar_matricula(codigo_horario: str, nombre: str, correo: str, numero_documento: str = "",
                        telefono: str = "") -> str:
    """Descuenta una vacante del horario y registra la pre-inscripción. Devuelve «OK MAT-…: resumen» o «ERROR: …»."""
    if not nombre.strip() or not EMAIL.fullmatch(correo.strip()):
        return "ERROR: faltan el nombre completo o un correo válido."
    fila = vacantes.descontar_vacante(codigo_horario)
    if isinstance(fila, str):
        return "ERROR: " + fila
    filas = matriculas()
    codigo = f"MAT-{sum(m.get('origen') == 'asistente' for m in filas) + 1:04d}"
    id_alumno = _alumno_para_inscripcion(nombre, correo, fila, numero_documento, telefono)
    filas.append({"codigo_matricula": codigo, "id_alumno": id_alumno, "origen": "asistente", "fecha_registro": _ahora(),
                  "codigo_horario": fila["codigo"], "curso": fila["curso"], "sede": fila["sede"],
                  "modalidad": fila.get("modalidad", ""), "horario": fila["horario"], "periodo": fila["periodo"],
                  "fecha_inicio": fila["fecha_inicio"], "fecha_fin": fila.get("fecha_fin", ""),
                  "nombre": nombre.strip(), "numero_documento": numero_documento, "telefono": telefono,
                  "correo": correo.strip(), "estado": PENDIENTE, "codigo_pago": ""})
    _guardar_matriculas(filas)
    return (f"OK {codigo}: {nombre.strip()} quedó pre-inscrito(a) en {fila['curso']} – {fila['sede']} – "
            f"{fila['horario']}, del {fila['fecha_inicio']} al {fila.get('fecha_fin', '-')}. Vacantes restantes en "
            f"ese horario: {fila['vacantes_disponibles']}.")


def id_alumno_de_matricula(codigo_matricula: str) -> str:
    return next((m.get("id_alumno", "") for m in matriculas() if m["codigo_matricula"] == codigo_matricula), "")


def registrar_pago(codigo_matricula: str, codigo_pago: str) -> str:
    """Registra el código de pago de una pre-inscripción.

    - Si figura como disponible en datos/pagos_demo.csv (pago conciliado), la matrícula se completa.
    - Si no figura, la vacante queda separada con estado «Pago por confirmar (MALI)» hasta que el personal del MALI
      lo apruebe o lo rechace.
    Devuelve "OK", "POR_CONFIRMAR" o un mensaje que empieza con "ERROR".
    """
    filas = matriculas()
    mat = next((m for m in filas if m["codigo_matricula"].upper() == codigo_matricula.upper()), None)
    if mat is None:
        return f"ERROR: no encontré la pre-inscripción {codigo_matricula}."
    if mat["estado"] == POR_CONFIRMAR:
        return (f"ERROR: la inscripción {codigo_matricula} ya tiene el pago {mat['codigo_pago']} en revisión por el "
                "personal del MALI.")
    if mat.get("codigo_pago") or mat["estado"] != PENDIENTE:
        return f"ERROR: la inscripción {codigo_matricula} ya tiene un pago validado ({mat['codigo_pago'] or mat['estado']})."
    codigo_pago = codigo_pago.upper()
    if any(m.get("codigo_pago", "").upper() == codigo_pago for m in filas):
        return f"ERROR: el código de pago {codigo_pago} ya fue registrado en otra inscripción."
    pagos = _leer(rutas.pagos())
    pago = next((p for p in pagos if p["codigo_pago"].upper() == codigo_pago), None)
    if pago is not None and pago["estado"] != "disponible":
        return f"ERROR: el código de pago {codigo_pago} ya fue usado."
    if pago is None:                                   # no conciliado: lo revisa el personal del MALI
        mat.update(estado=POR_CONFIRMAR, codigo_pago=codigo_pago)
        _guardar_matriculas(filas)
        return "POR_CONFIRMAR"
    pago.update(estado="usado", codigo_matricula=mat["codigo_matricula"], fecha_uso=_ahora())
    _guardar(rutas.pagos(), CAMPOS_PAGOS, pagos)
    mat.update(estado="Matriculado", codigo_pago=pago["codigo_pago"], validado_por="automático (pago conciliado)",
               fecha_validacion=_ahora())
    _guardar_matriculas(filas)
    _marcar_alumno_activo(mat.get("id_alumno", ""))
    return "OK"


def pagos_por_confirmar(solicitante: str) -> str:
    if not autorizado(solicitante, "gestion"):
        registrar(solicitante, "revision_pagos", "matricula.csv", "denegado")
        return DENEGADO
    registrar(solicitante, "revision_pagos", "matricula.csv", "permitido")
    filas = [m for m in matriculas() if m["estado"] == POR_CONFIRMAR]
    if not filas:
        return "No hay pagos por confirmar. Fuente: base restringida matricula.csv."
    lineas = [f"**Pagos por confirmar: {len(filas)}**"]
    lineas += [f"- {m['codigo_matricula']} · pago **{m['codigo_pago']}** · {m['id_alumno']} ({m['nombre']}) · "
               f"{m['curso']} · {m['codigo_horario']} {m['sede']} · {m['horario']} · registrado {m['fecha_registro']}"
               for m in filas]
    ej = filas[0]["codigo_matricula"]
    lineas += ["", f"Para resolver: «aprobar pago {ej}» o «rechazar pago {ej}».",
               "Fuente: base restringida matricula.csv."]
    return "\n".join(lineas)


def resolver_pago(solicitante: str, codigo_matricula: str, aprobar: bool) -> str:
    """El personal del MALI aprueba (Matriculado) o rechaza (vuelve a pendiente de pago) un pago en revisión."""
    if not autorizado(solicitante, "gestion"):
        registrar(solicitante, "revision_pagos", "matricula.csv", "denegado")
        return DENEGADO
    registrar(solicitante, "revision_pagos", "matricula.csv", "permitido")
    filas = matriculas()
    mat = next((m for m in filas if m["codigo_matricula"].upper() == codigo_matricula.upper()), None)
    if mat is None:
        return f"No encontré la inscripción {codigo_matricula}."
    if mat["estado"] != POR_CONFIRMAR:
        return f"La inscripción {codigo_matricula} no tiene un pago por confirmar (estado actual: {mat['estado']})."
    codigo_pago = mat["codigo_pago"]
    if aprobar:
        mat.update(estado="Matriculado", validado_por=solicitante, fecha_validacion=_ahora())
        _guardar_matriculas(filas)
        _marcar_alumno_activo(mat.get("id_alumno", ""))
        return (f"Listo: pago **{codigo_pago}** aprobado. {mat['codigo_matricula']} ({mat['id_alumno']}) queda "
                f"**Matriculado** en {mat['curso']} – {mat['sede']} – {mat['horario']}.\n"
                "Fuente: base restringida matricula.csv.")
    mat.update(estado=PENDIENTE, codigo_pago="", validado_por=f"rechazado por {solicitante} ({codigo_pago})",
               fecha_validacion=_ahora())
    _guardar_matriculas(filas)
    return (f"Listo: pago **{codigo_pago}** rechazado. {mat['codigo_matricula']} vuelve a «{PENDIENTE}»; la vacante "
            "sigue separada y el alumno puede enviar otro código de pago.\nFuente: base restringida matricula.csv.")


# ------------------------------------------------------------------ estado de matrícula (el propio alumno)
def _id_de(codigo: str) -> str:
    """Normaliza un código de alumno (ALU-0205) o de matrícula (MAT-0005) al código de alumno."""
    m = MATRICULA.search(codigo)
    if m:
        return id_alumno_de_matricula(f"MAT-{int(m.group(1)):04d}")
    m = ID_ALUMNO.search(codigo)
    return f"ALU-{int(m.group(1)):04d}" if m else ""


def verificar_alumno(codigo: str, documento: str) -> str:
    """Código de alumno si el documento coincide con el padrón o con su matrícula; si no, ""."""
    ident, doc = _id_de(codigo), re.sub(r"\D", "", documento)
    if not ident or not doc:
        return ""
    docs = {re.sub(r"\D", "", a.get("numero_documento", "")) for a in alumnos() if a["id_alumno"] == ident}
    docs |= {re.sub(r"\D", "", m.get("numero_documento", "")) for m in matriculas() if m["id_alumno"] == ident}
    return ident if doc in docs else ""


def estado_por_alumno(id_alumno: str) -> str:
    """Estado de las matrículas de un alumno ya verificado (sin documento, teléfono ni correo)."""
    filas = [m for m in matriculas() if m["id_alumno"] == id_alumno]
    if not filas:
        return (f"El código de alumno **{id_alumno}** no tiene matrículas registradas. Si te inscribiste por otro "
                "canal, escribe a cursosdearte@mali.pe.")
    nombre = (filas[0].get("nombre") or "").split(" ")[0]
    lineas = [f"**Estado de tu matrícula**{', ' + nombre if nombre else ''} (código de alumno **{id_alumno}**):"]
    extra = {POR_CONFIRMAR: "el pago {pago} está en revisión por el personal del MALI; tu vacante sigue separada.",
             PENDIENTE: "falta el pago; envíame «pago {mat} PAG-000000» cuando lo tengas.",
             "Matriculado": "inscripción completada{con_pago}."}
    for m in filas:
        partes = [m["curso"], m["sede"]] + ([m["horario"]] if m.get("horario") else [])
        duracion = (f" · del {m['fecha_inicio']} al {m.get('fecha_fin') or '-'} ({m['periodo']})"
                    if m.get("fecha_inicio") else "")
        nota = extra.get(m["estado"], "").format(pago=m.get("codigo_pago", ""), mat=m["codigo_matricula"],
                                                 con_pago=f" (pago {m['codigo_pago']})" if m.get("codigo_pago") else "")
        lineas.append(f"- {m['codigo_matricula']} · {' – '.join(partes)}{duracion}: **{m['estado']}**"
                      + (f" — {nota}" if nota else ""))
    lineas.append("")                    # línea en blanco: la fuente no queda dentro de la lista
    lineas.append("Fuente: registro de matrícula del MALI (matricula.csv). Por tu privacidad no muestro tu "
                  "documento, teléfono ni correo.")
    return "\n".join(lineas)


def ficha_inscripcion(codigo_matricula: str, mostrar_nombre: bool = True, por_confirmar: bool = False) -> str:
    """Resumen final con el horario, la información del curso y recordatorios tomados de la base general."""
    mat = next(m for m in matriculas() if m["codigo_matricula"] == codigo_matricula)
    hor = next((f for f in vacantes.horarios() if f["codigo"] == mat["codigo_horario"]), {})
    doc = conocimiento.documento_que_menciona(mat["curso"])
    titulo = (f"📝 Recibí tu código de pago **{mat['codigo_pago']}**. Tu inscripción **{mat['codigo_matricula']}** queda "
              "**por confirmar**: tu vacante está separada y el personal del MALI validará el pago. Puedes consultar "
              "el estado cuando quieras: escribe «estado de mi matrícula» y tu código de alumno." if por_confirmar else
              f"🎉 ¡Matrícula completada! Código de matrícula **{mat['codigo_matricula']}** · pago **{mat['codigo_pago']}** validado.")
    lineas = [titulo,
              f"Tu **código de alumno** es **{mat.get('id_alumno', '')}**.",
              "", f"**{mat['curso']}**" + (f" — {doc.titulo.lower()} de MALI Educación" if doc else ""),
              *([f"- Alumno(a): {mat['nombre']}"] if mostrar_nombre else []),
              f"- Sede: {mat['sede']}" + ("" if mat["sede"].lower() == "virtual" else f" ({mat['modalidad']})")
              + (" – clases en vivo por Zoom" if "zoom" in mat["modalidad"].lower() else ""),
              f"- Horario: {mat['horario']}",
              f"- Duración: del {hor.get('fecha_inicio') or mat['fecha_inicio']} al "
              f"{hor.get('fecha_fin') or mat.get('fecha_fin') or '-'} ({mat['periodo']})"]
    if hor.get("publico"):
        lineas.append(f"- Público: {hor['publico']}")
    resumen = {"Modalidad virtual": "Las clases son en vivo por Zoom y tienes acceso al Campus Virtual durante el mes.",
               "Ingreso a clases": "Para ingresar al aula debes presentar tu boleta (física o virtual) o la constancia de matrícula.",
               "Inasistencias": "Las sesiones no son recuperables ni acumulables si faltas.",
               "Cancelación de horarios": "El horario puede cancelarse si no llega a un mínimo de 5 alumnos inscritos."}
    temas = (["Modalidad virtual"] if "virtual" in mat["modalidad"].lower() else []) + \
        ["Ingreso a clases", "Inasistencias", "Cancelación de horarios"]
    recordatorios = [(t, d) for t in temas for d in conocimiento.documentos() if d.titulo.startswith(t)]
    if recordatorios:
        lineas += ["", "Ten en cuenta:"] + [f"- {resumen[t]}" for t, _ in recordatorios]
        lineas.append(f"Fuente: {recordatorios[-1][1].fuente}")
    lineas += ["", "Inscripción de demostración: el código de pago y los datos son simulados. "
               "Para una matrícula real escribe a cursosdearte@mali.pe."]
    return "\n".join(lineas)


# ------------------------------------------------------------------ gestión de alumnos (personal autorizado)
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


def _resumen_matricula(filas: list[dict], norm: str) -> str:
    """Respuestas sobre el registro de matrícula: totales, por curso o por estado."""
    cursos = tx.detectar_cursos(norm, vacantes.horarios())
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


def consultar_gestion(solicitante: str, consulta: str) -> str:
    """Consulta la base restringida si el usuario está autorizado; si no, la deniega y lo registra."""
    if not autorizado(solicitante, "gestion"):
        registrar(solicitante, "gestion_alumnos", "alumnos_sinteticos.csv", "denegado")
        return DENEGADO
    padron, filas = alumnos(), matriculas()
    m = ID_ALUMNO.search(consulta)
    if m:
        ident = f"ALU-{int(m.group(1)):04d}"
        a = next((x for x in padron if x["id_alumno"] == ident), None)
        suyas = [x for x in filas if x.get("id_alumno") == ident]
        registrar(solicitante, "gestion_alumnos", "alumnos_sinteticos.csv",
                  "permitido" if (a or suyas) else "sin_resultado")
        if not a and not suyas:
            return f"No existe el alumno {ident} en la base de gestión."
        partes = [_ficha(a)] if a else [f"**{ident}**" + (f" – {suyas[0]['nombre']}" if suyas[0].get("nombre") else "")]
        if suyas:
            partes.append("Matrículas:\n" + "\n".join(_linea_matricula(x) for x in suyas))
        return "\n".join(partes) + "\nFuente: base restringida (alumnos_sinteticos.csv y matricula.csv)."
    norm = tx.normalizar(consulta)
    if re.search(r"matricul|inscrit|retirad", norm):
        registrar(solicitante, "gestion_alumnos", "matricula.csv", "permitido")
        return _resumen_matricula(filas, norm)
    registrar(solicitante, "gestion_alumnos", "alumnos_sinteticos.csv", "permitido")
    if "asistencia" in norm or "inasist" in norm:
        bajos = sorted((a for a in padron if a["porcentaje_asistencia"] and float(a["porcentaje_asistencia"]) < 70
                        and a["estado_matricula"] != "Retirada"),
                       key=lambda a: float(a["porcentaje_asistencia"]))
        return (f"Alumnos activos con asistencia menor a 70 %: {len(bajos)} de {len(padron)}.\n"
                + "\n".join(f"- {a['id_alumno']}: {a['porcentaje_asistencia']} % – {a['curso']} ({a['sede']})"
                            for a in bajos[:10])
                + ("\n- …" if len(bajos) > 10 else "")
                + "\nSugerencia: que la Coordinación revise cada caso; el asistente no toma decisiones."
                + "\nFuente: base restringida alumnos_sinteticos.csv (datos sintéticos).")
    if "pago" in norm or "deuda" in norm or "administrativ" in norm:
        pend = [a for a in padron if a["situacion_administrativa"] in ("Pago pendiente", "Incidencia de pago")]
        return (f"Alumnos con pago pendiente o incidencia de pago: {len(pend)} de {len(padron)}.\n"
                + "\n".join(f"- {a['id_alumno']}: {a['situacion_administrativa']} – {a['curso']}" for a in pend[:10])
                + ("\n- …" if len(pend) > 10 else "")
                + "\nFuente: base restringida alumnos_sinteticos.csv (datos sintéticos).")
    estados = {}
    for a in padron:
        estados[a["estado_matricula"]] = estados.get(a["estado_matricula"], 0) + 1
    return (f"Resumen de la gestión de alumnos ({len(padron)} registros sintéticos): "
            + ", ".join(f"{k}: {n}" for k, n in sorted(estados.items())) + ".\n"
            "Puedes consultar un alumno por su código (por ejemplo «alumno ALU-0007»), los alumnos con "
            "asistencia baja o los que tienen pagos pendientes.\n"
            "Fuente: base restringida alumnos_sinteticos.csv (datos sintéticos).")
