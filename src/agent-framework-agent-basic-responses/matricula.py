"""
Flujo de matrícula del MALI Asistente Estudiantil (solo librería estándar).

Pasos: 1) curso → 2) horario → 3) nombre y correo → 4) confirmación → registro.
Al confirmar: descuenta 1 vacante en datos/vacantes.csv crea el código de alumno y registra la matrícula en restringido/matricula.csv.

`procesar_mensaje(texto)` devuelve la indicación que el agente debe responder en cada paso. El estado de la
conversación se guarda en memoria (un usuario a la vez, suficiente para la demostración).
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import vacantes as v

ARCHIVO_MATRICULAS = v.AQUI / "restringido" / "matricula.csv"      # todos los alumnos matriculados
ARCHIVO_PAGOS = v.AQUI / "datos" / "pagos_demo.csv"
PAGO = re.compile(r"\bPAG[-\s]?(\d{6})\b", re.I)
MATRICULA = re.compile(r"\bMAT[-\s]?(\d{1,4})\b", re.I)
CAMPOS_MATRICULA = ["codigo_matricula", "id_alumno", "nombre", "numero_documento", "telefono", "correo", "curso",
                    "codigo_horario", "sede", "modalidad", "horario", "periodo", "fecha_inicio", "fecha_fin",
                    "estado", "codigo_pago", "fecha_registro", "origen", "validado_por", "fecha_validacion"]
POR_CONFIRMAR = "Pago por confirmar (MALI)"
PENDIENTE = "Pre-inscrito (pendiente de pago)"
DATOS_REQUERIDOS = [("nombre", "tu nombre completo"), ("numero_documento", "tu número de documento (DNI o CE)"),
                    ("telefono", "un teléfono de contacto"),
                    ("correo", "un correo electrónico válido (por ejemplo, nombre@gmail.com)")]

PALABRAS_INSCRIBIR = ("inscrib", "inscripc", "matricul", "agend", "reserv", "separ", "apunt", "registr")
PALABRAS_SALUDO = {"hola", "buenas", "buenos", "hey", "saludos", "holi", "eres", "ayudar", "ayudarme", "ayudame",
                   "ayuda", "presentate", "haces"}
PALABRAS_SI = {"si", "confirmo", "confirmar", "ok", "dale", "acepto", "correcto", "listo", "claro", "perfecto",
               "yes", "va", "procede"}
PALABRAS_NO = {"no", "cancelar", "cancela", "cancelo", "salir", "olvidalo", "detener"}
ORDINALES = {"primer": 1, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercer": 3, "tercero": 3,
             "tercera": 3, "cuarto": 4, "cuarta": 4, "quinto": 5, "quinta": 5, "uno": 1, "dos": 2, "tres": 3,
             "cuatro": 4, "cinco": 5}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_NO_CURSO = {"arte", "artes", "y", "de", "al", "dance", "for", "pequeno", "pequena", "kids"}

PRESENTACION = (
    "¡Hola! Soy MALI Asistente Estudiantil 🎨, un prototipo académico de IA del proyecto de retención y apoyo al "
    "estudiante del Museo de Arte de Lima. Estoy aquí para ayudarte con tu matrícula en los cursos del MALI:\n"
    "- Ver las vacantes disponibles por curso, sede o periodo.\n"
    "- Elegir el curso y el horario que mejor te acomode.\n"
    "- Dejar registrada tu pre-inscripción.\n"
    "(Las vacantes y horarios son datos de demostración.) ¿Qué curso te gustaría llevar?")

DESPEDIDA = (
    "Entendido, no registré ninguna pre-inscripción. ¡Gracias por conversar conmigo! 😊\n"
    "Espero que puedas matricularte próximamente: revisa los cursos y las vacantes disponibles cuando quieras, "
    "aquí estaré para ayudarte.")

estado: dict = {}


def reiniciar() -> None:
    estado.clear()


# ------------------------------------------------------------------ archivo de vacantes (lectura y escritura)
def _leer_tabla() -> tuple[list[dict], list[str], str]:
    texto = v._archivo_vacantes().read_text(encoding="utf-8-sig")
    primera = texto.splitlines()[0]
    delim = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.DictReader(texto.splitlines(), delimiter=delim)
    filas = [{k: (val or "").strip() for k, val in f.items()} for f in lector]
    return filas, list(lector.fieldnames or []), delim


def _guardar_tabla(filas: list[dict], campos: list[str], delim: str) -> None:
    with open(v._archivo_vacantes(), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=delim)
        w.writeheader()
        w.writerows(filas)


def _vac(f: dict) -> int:
    try:
        return int(float(f.get("vacantes_disponibles") or 0))
    except ValueError:
        return 0


def _cursos_disponibles() -> list[str]:
    filas, _, _ = _leer_tabla()
    return sorted({f["curso"] for f in filas if _vac(f) > 0})


def detectar_cursos(texto: str) -> list[str]:
    """Cursos del archivo que menciona el texto (nombre exacto, palabra clave, categoría o error de tipeo)."""
    filas, _, _ = _leer_tabla()
    cursos = sorted({f["curso"] for f in filas})
    norm = v._normalizar(texto)
    exactos = [c for c in cursos if v._normalizar(c).strip() in norm]
    if exactos:
        return exactos
    t = v._set(texto)
    import difflib
    encontrados = set()
    for f in filas:
        claves = v._set(f["curso"]) - _NO_CURSO
        categoria = v._set(f.get("categoria", "")) - _NO_CURSO
        for tok in t:
            if tok in claves or tok in categoria or difflib.get_close_matches(tok, claves, 1, 0.82):
                encontrados.add(f["curso"])
    return sorted(encontrados)


def _opciones(curso: str, sede_texto: str = "") -> list[dict]:
    filas, _, _ = _leer_tabla()
    ops = [f for f in filas if f["curso"] == curso and _vac(f) > 0]
    if sede_texto:
        por_sede = [f for f in ops if (v._set(sede_texto) - v._GENERICAS_SEDE) & (v._set(f["sede"]) - v._GENERICAS_SEDE)]
        if por_sede:
            return por_sede
    return ops


def _linea(n: int, f: dict) -> str:
    return (f"{n}. {f['sede']} – {f['horario']} – del {f['fecha_inicio']} al {f.get('fecha_fin', '-')} "
            f"({f['periodo']}) – "
            f"{f['publico']} – {_vac(f)} vacante(s) [código {f['codigo']}]")


_DIAS = {"lunes": "lun", "lun": "lun", "martes": "mar", "miercoles": "mie", "mie": "mie", "jueves": "jue",
         "jue": "jue", "viernes": "vie", "vie": "vie", "sabado": "sab", "sabados": "sab", "sab": "sab"}


def _puntaje_opcion(texto: str, f: dict) -> int:
    """Qué tanto coincide lo que escribió el usuario (sede, días, hora) con un horario."""
    import difflib
    norm = v._normalizar(texto)
    palabras = norm.split()
    puntos = 0
    claves_sede = v._set(f["sede"]) - v._GENERICAS_SEDE
    for p in palabras:
        if len(p) > 3 and (p in claves_sede or difflib.get_close_matches(p, claves_sede, 1, 0.75)):
            puntos += 2
    dias_horario = {_DIAS[d] for d in v._normalizar(f["horario"]).split() if d in _DIAS}
    dias_texto = {_DIAS[p] for p in palabras if p in _DIAS}
    if dias_texto:
        puntos += 2 if dias_texto == dias_horario else (1 if dias_texto & dias_horario else -1)
    inicio = re.search(r"(\d{1,2}):\d{2}", f["horario"])
    horas = [int(h) for h in re.findall(r"\b(\d{1,2})(?::\d{2})?\b", norm) if int(h) <= 23]
    if inicio and horas:
        puntos += 2 if int(inicio.group(1)) in horas or int(inicio.group(1)) - 12 in horas else -1
    return puntos


def _elegir_opcion(texto: str, ops: list[dict]) -> dict | None:
    norm = v._normalizar(texto)
    cod = CODIGO_HORARIO.search(texto)
    if cod:
        codigo = f"H{int(cod.group(1)):02d}"
        return next((f for f in ops if f["codigo"].upper() == codigo), None)
    num = re.fullmatch(r"\s*(?:el|la|opcion|numero)?\s*(\d{1,2})\s*", norm)
    n = int(num.group(1)) if num else next((ORDINALES[w] for w in norm.split() if w in ORDINALES), None)
    if n and 1 <= n <= len(ops):
        return ops[n - 1]
    puntajes = sorted(((_puntaje_opcion(texto, f), i) for i, f in enumerate(ops)), reverse=True)
    if puntajes and puntajes[0][0] > 0 and (len(puntajes) == 1 or puntajes[0][0] > puntajes[1][0]):
        return ops[puntajes[0][1]]
    if len(ops) == 1 and set(norm.split()) & PALABRAS_SI:
        return ops[0]
    return None


def _horario_por_codigo(texto: str) -> dict | None:
    cod = CODIGO_HORARIO.search(texto)
    if not cod:
        return None
    filas, _, _ = _leer_tabla()
    return next((f for f in filas if f["codigo"].upper() == f"H{int(cod.group(1)):02d}"), None)


_ETIQUETA_TEL = r"(?:tel[eé]fono|telf?\.?|cel(?:ular)?\.?|whatsapp|m[oó]vil)"
_ETIQUETA_DOC = r"(?:dni|documento|doc\.?|c\.?e\.?|carn[eé] de extranjer[ií]a|pasaporte)"


def _extraer_numeros(texto: str) -> str:
    """Toma el número de documento y el teléfono del mensaje. Devuelve el texto sin esos números."""
    for etiqueta, clave in ((_ETIQUETA_TEL, "telefono"), (_ETIQUETA_DOC, "numero_documento")):
        m = re.search(rf"(?i)\b{etiqueta}\s*(?:n[°ºo.]*|n[uú]mero)?\s*(?:es|:)?\s*(\+?[\d][\d\s-]{{6,14}}\d)", texto)
        if m:
            estado[clave] = re.sub(r"\D", "", m.group(1)) if clave == "numero_documento" else m.group(1).strip()
            texto = texto.replace(m.group(0), " ")
    for m in re.finditer(r"\+?\d[\d\s-]{6,14}\d", texto):
        digitos = re.sub(r"\D", "", m.group(0))
        if len(digitos) == 9 and digitos.startswith("9") and not estado.get("telefono"):
            estado["telefono"] = m.group(0).strip()
        elif 8 <= len(digitos) <= 12 and not estado.get("numero_documento") and not m.group(0).startswith("+"):
            estado["numero_documento"] = digitos
        elif 7 <= len(digitos) <= 12 and not estado.get("telefono"):
            estado["telefono"] = m.group(0).strip()
        else:
            continue
        texto = texto.replace(m.group(0), " ")
    return texto


def _datos_completos() -> bool:
    return all(estado.get(k) for k, _ in DATOS_REQUERIDOS)


def _extraer_datos(texto: str, con_nombre: bool = True) -> None:
    correo = EMAIL.search(texto)
    if correo:
        estado["correo"] = correo.group(0)
        texto = texto.replace(correo.group(0), " ")
    texto = _extraer_numeros(texto)
    texto = re.sub(r"\S*[@.]\S*", " ", texto)          # restos de un correo incompleto
    limpio = re.sub(rf"(?i)\b(me llamo|mi nombre es|mi nombre|nombre|soy|mi correo es|mi correo|correo|email|"
                    rf"electr[oó]nico|es|y|mi|n[uú]mero|{_ETIQUETA_TEL}|{_ETIQUETA_DOC})\b", " ", texto)
    palabras = [p for p in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'-]+", limpio) if len(p) > 1]
    if not con_nombre or "?" in texto or "¿" in texto or re.search(r"\d", limpio) or len(palabras) > 6:
        return
    comunes = v.STOPWORDS | v._RELLENO | PALABRAS_SI | PALABRAS_NO | {
        "el", "la", "los", "las", "proyecto", "curso", "cursos", "vacante", "vacantes", "horario", "explica",
        "explicame", "que", "como", "cuando", "donde", "gracias", "hola", "quiero", "ver", "otro", "otra"}
    con_prefijo = bool(re.search(r"(?i)\b(me llamo|mi nombre es|soy)\b", texto)) or bool(correo)
    capitalizado = bool(palabras) and all(p[0].isupper() for p in palabras
                                          if p.lower() not in {"de", "del", "la", "los", "las", "y"})
    normalizadas = set(v._normalizar(" ".join(palabras)).split())
    if not (con_prefijo or capitalizado) and normalizadas & comunes:
        return
    if len(palabras) >= 2 and not normalizadas & (PALABRAS_SI | PALABRAS_NO):
        estado["nombre"] = " ".join(p.capitalize() for p in palabras[:5])


def ocultar(valor: str, visibles: int = 3) -> str:
    """Muestra solo los últimos dígitos (p. ej. «*****678»)."""
    d = re.sub(r"\D", "", valor or "")
    return ("*" * max(0, len(d) - visibles) + d[-visibles:]) if d else "-"


# ------------------------------------------------------------------ registro de la matrícula
def _leer_matriculas() -> list[dict]:
    if not ARCHIVO_MATRICULAS.exists():
        return []
    return list(csv.DictReader(ARCHIVO_MATRICULAS.read_text(encoding="utf-8").splitlines()))


def _guardar_matriculas(filas: list[dict]) -> None:
    with open(ARCHIVO_MATRICULAS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_MATRICULA, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c, "") or "" for c in CAMPOS_MATRICULA})


def registrar_matricula(codigo_horario: str, nombre: str, correo: str, numero_documento: str = "",
                        telefono: str = "") -> str:
    """Descuenta una vacante del horario y registra la matrícula. Devuelve un resumen o un mensaje de error."""
    filas, campos, delim = _leer_tabla()
    fila = next((f for f in filas if f.get("codigo", "").upper() == codigo_horario.upper()), None)
    if fila is None:
        return f"ERROR: no existe el horario {codigo_horario}."
    if _vac(fila) <= 0:
        return f"ERROR: el horario {codigo_horario} ya no tiene vacantes."
    if not nombre.strip() or not EMAIL.fullmatch(correo.strip()):
        return "ERROR: faltan el nombre completo o un correo válido."
    fila["vacantes_disponibles"] = str(_vac(fila) - 1)
    if "actualizado_al" in fila:
        fila["actualizado_al"] = datetime.now().strftime("%d/%m/%Y")
    _guardar_tabla(filas, campos, delim)

    matriculas = _leer_matriculas()
    codigo = f"MAT-{sum(m.get('origen') == 'asistente' for m in matriculas) + 1:04d}"
    import acceso
    programa = "Taller" if "taller" in fila.get("categoria", "").lower() else "Curso"
    id_alumno = acceso.alumno_para_inscripcion(nombre, correo, fila["curso"], fila["sede"], fila["periodo"], programa,
                                               numero_documento, telefono)
    matriculas.append({"codigo_matricula": codigo, "id_alumno": id_alumno, "origen": "asistente",
                       "fecha_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                       "codigo_horario": fila["codigo"], "curso": fila["curso"], "sede": fila["sede"],
                       "modalidad": fila.get("modalidad", ""), "horario": fila["horario"], "periodo": fila["periodo"],
                       "fecha_inicio": fila["fecha_inicio"], "fecha_fin": fila.get("fecha_fin", ""),
                       "nombre": nombre.strip(), "numero_documento": numero_documento, "telefono": telefono,
                       "correo": correo.strip(),
                       "estado": PENDIENTE, "codigo_pago": ""})
    _guardar_matriculas(matriculas)
    return (f"OK {codigo}: {nombre.strip()} quedó pre-inscrito(a) en {fila['curso']} – {fila['sede']} – "
            f"{fila['horario']}, del {fila['fecha_inicio']} al {fila.get('fecha_fin', '-')}. Vacantes restantes en ese horario: "
            f"{fila['vacantes_disponibles']}.")


# ------------------------------------------------------------------ pago y confirmación final
def _leer_pagos() -> list[dict]:
    with open(ARCHIVO_PAGOS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _guardar_pagos(pagos: list[dict]) -> None:
    with open(ARCHIVO_PAGOS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["codigo_pago", "estado", "codigo_matricula", "fecha_uso"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(pagos)


def _ahora() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def validar_pago(codigo_matricula: str, codigo_pago: str) -> str:
    """Registra el código de pago de una pre-inscripción.

    - Si el código figura como disponible en datos/pagos_demo.csv (pagos ya conciliados), la matrícula se completa.
    - Si no figura, la vacante queda separada con estado «Pago por confirmar (MALI)» hasta que el personal del MALI
      lo apruebe o lo rechace («aprobar pago MAT-0005» / «rechazar pago MAT-0005»).
    Devuelve "OK", "POR_CONFIRMAR" o un mensaje que empieza con "ERROR".
    """
    matriculas = _leer_matriculas()
    mat = next((m for m in matriculas if m["codigo_matricula"].upper() == codigo_matricula.upper()), None)
    if mat is None:
        return f"ERROR: no encontré la pre-inscripción {codigo_matricula}."
    if mat["estado"] == POR_CONFIRMAR:
        return (f"ERROR: la inscripción {codigo_matricula} ya tiene el pago {mat['codigo_pago']} en revisión por el "
                "personal del MALI.")
    if mat.get("codigo_pago") or mat["estado"] != PENDIENTE:
        return f"ERROR: la inscripción {codigo_matricula} ya tiene un pago validado ({mat['codigo_pago'] or mat['estado']})."
    codigo_pago = codigo_pago.upper()
    if any(m.get("codigo_pago", "").upper() == codigo_pago for m in matriculas):
        return f"ERROR: el código de pago {codigo_pago} ya fue registrado en otra inscripción."
    pagos = _leer_pagos()
    pago = next((p for p in pagos if p["codigo_pago"].upper() == codigo_pago), None)
    if pago is not None and pago["estado"] != "disponible":
        return f"ERROR: el código de pago {codigo_pago} ya fue usado."
    if pago is None:                                   # no conciliado: lo revisa el personal del MALI
        mat.update(estado=POR_CONFIRMAR, codigo_pago=codigo_pago)
        _guardar_matriculas(matriculas)
        return "POR_CONFIRMAR"
    pago.update(estado="usado", codigo_matricula=mat["codigo_matricula"], fecha_uso=_ahora())
    _guardar_pagos(pagos)
    mat.update(estado="Matriculado", codigo_pago=pago["codigo_pago"], validado_por="automático (pago conciliado)",
               fecha_validacion=_ahora())
    _guardar_matriculas(matriculas)
    import acceso
    acceso.marcar_alumno_activo(mat.get("id_alumno", ""))
    return "OK"


# ------------------------------------------------------------------ revisión de pagos (personal del MALI)
def pagos_por_confirmar() -> str:
    filas = [m for m in _leer_matriculas() if m["estado"] == POR_CONFIRMAR]
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


def resolver_pago(codigo_matricula: str, aprobar: bool, usuario: str) -> str:
    """El personal del MALI aprueba (matrícula completa) o rechaza (vuelve a pendiente de pago) un pago en revisión."""
    matriculas = _leer_matriculas()
    mat = next((m for m in matriculas if m["codigo_matricula"].upper() == codigo_matricula.upper()), None)
    if mat is None:
        return f"No encontré la inscripción {codigo_matricula}."
    if mat["estado"] != POR_CONFIRMAR:
        return f"La inscripción {codigo_matricula} no tiene un pago por confirmar (estado actual: {mat['estado']})."
    codigo_pago = mat["codigo_pago"]
    if aprobar:
        pagos = _leer_pagos()
        pagos.append({"codigo_pago": codigo_pago, "estado": "usado", "codigo_matricula": mat["codigo_matricula"],
                      "fecha_uso": _ahora()})
        _guardar_pagos(pagos)
        mat.update(estado="Matriculado", validado_por=usuario, fecha_validacion=_ahora())
        _guardar_matriculas(matriculas)
        import acceso
        acceso.marcar_alumno_activo(mat.get("id_alumno", ""))
        return (f"Listo: pago **{codigo_pago}** aprobado. {mat['codigo_matricula']} ({mat['id_alumno']}) queda "
                f"**Matriculado** en {mat['curso']} – {mat['sede']} – {mat['horario']}.\n"
                "Fuente: base restringida matricula.csv.")
    mat.update(estado=PENDIENTE, codigo_pago="", validado_por=f"rechazado por {usuario} ({codigo_pago})",
               fecha_validacion=_ahora())
    _guardar_matriculas(matriculas)
    return (f"Listo: pago **{codigo_pago}** rechazado. {mat['codigo_matricula']} vuelve a «{PENDIENTE}»; la vacante "
            "sigue separada y el alumno puede enviar otro código de pago.\nFuente: base restringida matricula.csv.")


def estado_inscripcion(codigo_matricula: str) -> str:
    """Estado de una inscripción para el estudiante (sin datos personales)."""
    mat = next((m for m in _leer_matriculas() if m["codigo_matricula"].upper() == codigo_matricula.upper()), None)
    if mat is None or mat.get("origen") != "asistente":
        return f"No encontré la inscripción {codigo_matricula}. Revisa el código."
    extra = {POR_CONFIRMAR: f" El pago {mat['codigo_pago']} está en revisión por el personal del MALI.",
             PENDIENTE: f" Cuando tengas el código de pago escríbeme: «pago {mat['codigo_matricula']} PAG-000000»."}
    return (f"Inscripción **{mat['codigo_matricula']}** · {mat['curso']} – {mat['sede']} – {mat['horario']}: "
            f"**{mat['estado']}**." + extra.get(mat["estado"], ""))


def ficha_inscripcion(codigo_matricula: str, mostrar_nombre: bool = True, por_confirmar: bool = False) -> str:
    """Resumen final con el horario, la información del curso y recordatorios tomados de las fuentes."""
    import conocimiento
    mat = next(m for m in _leer_matriculas() if m["codigo_matricula"] == codigo_matricula)
    filas, _, _ = _leer_tabla()
    hor = next((f for f in filas if f["codigo"] == mat["codigo_horario"]), {})
    doc = conocimiento.documento_que_menciona(mat["curso"])
    titulo = (f"📝 Recibí tu código de pago **{mat['codigo_pago']}**. Tu inscripción **{mat['codigo_matricula']}** queda "
              "**por confirmar**: tu vacante está separada y el personal del MALI validará el pago. Puedes consultar "
              f"el estado escribiendo «estado {mat['codigo_matricula']}»." if por_confirmar else
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
    recordatorios = []
    for titulo_doc in ("Ingreso a clases", "Inasistencias", "Cancelación de horarios"):
        d = next((x for x in conocimiento.documentos() if x.titulo.startswith(titulo_doc)), None)
        if d:
            recordatorios.append(d)
    if "virtual" in mat["modalidad"].lower():
        d = next((x for x in conocimiento.documentos() if x.titulo.startswith("Modalidad virtual")), None)
        if d:
            recordatorios.insert(0, d)
    if recordatorios:
        lineas += ["", "Ten en cuenta:"]
        resumen = {"Ingreso a clases": "Para ingresar al aula debes presentar tu boleta (física o virtual) o la constancia de matrícula.",
                   "Inasistencias": "Las sesiones no son recuperables ni acumulables si faltas.",
                   "Cancelación de horarios": "El horario puede cancelarse si no llega a un mínimo de 5 alumnos inscritos.",
                   "Modalidad virtual": "Las clases son en vivo por Zoom y tienes acceso al Campus Virtual durante el mes."}
        for d in recordatorios:
            clave = next(k for k in resumen if d.titulo.startswith(k))
            lineas.append(f"- {resumen[clave]}")
        lineas.append(f"Fuente: {recordatorios[-1].fuente}")
    lineas += ["", "Inscripción de demostración: el código de pago y los datos son simulados. "
               "Para una matrícula real escribe a cursosdearte@mali.pe."]
    return "\n".join(lineas)


def _id_alumno(codigo_matricula: str) -> str:
    return next((m.get("id_alumno", "") for m in _leer_matriculas()
                 if m["codigo_matricula"] == codigo_matricula), "")


def _pedir_pago(codigo_matricula: str, detalle: str) -> str:
    estado.clear()
    estado.update(paso="pago", codigo_matricula=codigo_matricula)
    return (f"¡Listo! Tu pre-inscripción quedó registrada con el código **{codigo_matricula}**.\n"
            f"- Tu **código de alumno** es **{_id_alumno(codigo_matricula)}** (guárdalo para tus trámites).\n- {detalle}\n\n"
            "Para **finalizar tu inscripción**, envíame el **código de pago** de tu operación (formato PAG-000000, "
            "por ejemplo PAG-100001). Si aún no pagas, escribe «después»: tu vacante queda separada como "
            "pre-inscripción y podrás enviarme el código más tarde junto con tu código de pre-inscripción.")


def procesar_pago(texto: str, codigo_matricula: str | None = None) -> str:
    en_flujo = codigo_matricula is None        # pago posterior: no se muestra el nombre (podría ser de otra persona)
    codigo_matricula = codigo_matricula or estado.get("codigo_matricula")
    m = PAGO.search(texto)
    if not m:
        return ("No reconocí un código de pago. Envíalo con el formato PAG-000000 (por ejemplo PAG-100001) o "
                "escribe «después» para completarlo más tarde. No compartas números de tarjeta.")
    r = validar_pago(codigo_matricula, f"PAG-{m.group(1)}")
    if r.startswith("ERROR"):
        if "en revisión" in r:
            reiniciar()
            return r.replace("ERROR: ", "")
        return r.replace("ERROR: ", "No pude registrar el pago: ") + " Revisa el código e inténtalo de nuevo."
    reiniciar()
    return ficha_inscripcion(codigo_matricula, mostrar_nombre=en_flujo, por_confirmar=r == "POR_CONFIRMAR")


# ------------------------------------------------------------------ conversación
def consultar_matriculas() -> str:
    """Lista las matrículas registradas en restringido/matricula.csv."""
    if not ARCHIVO_MATRICULAS.exists():
        return "Aún no hay matrículas registradas."
    filas = _leer_matriculas()
    return "\n".join(f"- {f['codigo_matricula']} | {f['nombre']} | {f['curso']} | {f['sede']} | {f['horario']} | "
                     f"{f['estado']}" for f in filas) or "Aún no hay matrículas registradas."


def es_saludo(texto: str) -> bool:
    palabras = set(v._normalizar(texto).split())
    return bool(palabras & PALABRAS_SALUDO) and not v._pide_vacantes(texto) and not detectar_cursos(texto) \
        and not quiere_inscribirse(texto)


CODIGO_HORARIO = re.compile(r"\bh\s?-?(\d{1,2})\b", re.I)
_INTENCION = re.compile(
    r"\b(inscrib(irme|eme|irte|ir a mi|irlo|irla|o)\b|(quisiera|quiero|deseo|me gustaria|puedo) inscribir\b|"
    r"inscripcion en|matricul(arme|ame|o|ar a mi)\b|(quisiera|quiero|deseo) matricular\b|me apunto|"
    r"pre ?inscrib\w*|pre ?inscripcion|agend\w*|reserv(ar|ame|a|o)\s+(una\s+|mi\s+)?(vacante|cupo|horario)|"
    r"separ(ar|ame|o)\s+(una\s+|mi\s+)?(vacante|cupo)|apuntame|quiero\s+(inscribir|matricular|llevar)\w*)")


def quiere_inscribirse(texto: str) -> bool:
    """Intención explícita de inscribirse («quiero inscribirme», «inscríbeme», «agéndame una vacante»…)."""
    return bool(_INTENCION.search(v._normalizar(texto))) or bool(MATRICULA.search(texto) and PAGO.search(texto)) \
        or bool(MATRICULA.search(texto) and re.search(r"\bestado\b", v._normalizar(texto))) \
        or bool(CODIGO_HORARIO.search(texto) and (_horario_por_codigo(texto) or len(texto.split()) <= 4))


def fuera_del_flujo(texto: str) -> bool:
    """El usuario cambió de tema a mitad de la pre-inscripción (pregunta sin elegir curso u horario)."""
    paso = estado.get("paso")
    if paso == "pago":
        return ("?" in texto or "¿" in texto) and not PAGO.search(texto)
    if paso not in ("curso", "horario", "datos"):
        return False
    pregunta = "?" in texto or "¿" in texto
    if paso == "datos" and EMAIL.search(texto):
        return False
    eligio = bool(detectar_cursos(texto)) or bool(re.search(r"\b\d{1,2}\b|\bh\d", v._normalizar(texto))) \
        or bool(set(v._normalizar(texto).split()) & set(ORDINALES))
    return pregunta and not eligio


def flujo_activo() -> bool:
    return bool(estado.get("paso"))


def _pedir_curso(cursos: list[str] | None = None) -> str:
    estado["paso"] = "curso"
    estado["candidatos"] = cursos or []
    lista = cursos or _cursos_disponibles()
    if cursos:
        return "¿En cuál de estos cursos te quieres inscribir?\n" + "\n".join(
            f"{i}. {c}" for i, c in enumerate(lista, 1))
    return ("¡Con gusto te ayudo a inscribirte! ¿A qué curso te gustaría inscribirte? Cursos con vacantes:\n"
            + "\n".join(f"- {c}" for c in lista))


def _pedir_horario(curso: str, sede_texto: str = "") -> str:
    ops = _opciones(curso, sede_texto)
    if not ops:
        estado.pop("curso", None)
        return f"Lo siento, {curso} no tiene vacantes en este momento. " + _pedir_curso()
    estado.update(paso="horario", curso=curso, opciones=[f["codigo"] for f in ops])
    elegido = _elegir_opcion(sede_texto, ops) if len(ops) > 1 and sede_texto else None
    if elegido:                                   # ya indicó sede, días u hora: se elige ese horario
        estado.update(paso="datos", codigo=elegido["codigo"])
        return (f"Elegiste **{elegido['codigo']}**: {curso} – " + _linea(1, elegido)[3:] + "\n\n"
                + (_resumen() if _datos_completos() else _pedir_datos()))
    if len(ops) == 1:
        estado.update(paso="datos", codigo=ops[0]["codigo"])
        if _datos_completos():
            return f"{curso} tiene un solo horario con vacantes.\n\n" + _resumen()
        return (f"{curso} tiene este horario con vacantes:\n" + _linea(1, ops[0])[3:] +
                "\nSi te acomoda, envíame tu nombre completo, número de documento, teléfono y correo para registrar "
                "tu pre-inscripción (o escribe «cancelar»).")
    return (f"Estos son los horarios de {curso} con vacantes:\n" + "\n".join(_linea(i, f) for i, f in enumerate(ops, 1))
            + "\n¿Cuál horario eliges? Responde con el número de la opción o con su código (por ejemplo, "
            f"«{ops[0]['codigo']}»).")


def _pedir_datos() -> str:
    estado["paso"] = "datos"
    falta = [texto for clave, texto in DATOS_REQUERIDOS if not estado.get(clave)]
    lista = falta[0] if len(falta) == 1 else ", ".join(falta[:-1]) + " y " + falta[-1]
    return ("Para registrar tu pre-inscripción necesito " + lista + ". Por ejemplo: «Mario Pérez, DNI 12345678, "
            "teléfono 987654321, mario@gmail.com». Estos datos solo los verá el personal del MALI. "
            "(Escribe «cancelar» si prefieres salir.)")


def _resumen() -> str:
    filas, _, _ = _leer_tabla()
    f = next(x for x in filas if x["codigo"] == estado["codigo"])
    estado["paso"] = "confirmar"
    return (f"Revisa tu pre-inscripción:\n- Curso: {f['curso']}\n- Sede: {f['sede']} ({f['modalidad']})\n"
            f"- Horario: {f['horario']}\n- Duración: del {f['fecha_inicio']} al {f.get('fecha_fin', '-')} ({f['periodo']})\n"
            f"- Alumno(a): {estado['nombre']} – documento {ocultar(estado['numero_documento'])} – "
            f"teléfono {ocultar(estado['telefono'])} – {estado['correo']}\n\n"
            "¿Confirmas la pre-inscripción? Responde **sí** para registrarla o **no** para cancelar.")


def procesar_mensaje(texto: str) -> str:
    """Devuelve el mensaje que el agente debe dar al usuario para el paso actual de la matrícula."""
    palabras = set(v._normalizar(texto).split())
    if estado.get("paso") == "pago":
        if palabras & {"despues", "luego", "mas", "tarde", "ahora", "no", "cancelar", "salir"} and not PAGO.search(texto):
            codigo = estado.get("codigo_matricula")
            reiniciar()
            return (f"De acuerdo. Tu pre-inscripción **{codigo}** queda pendiente de pago. Cuando tengas el código, "
                    f"escríbeme por ejemplo: «pago {codigo} PAG-100001».")
        return procesar_pago(texto)
    if MATRICULA.search(texto) and re.search(r"\bestado\b", v._normalizar(texto)) and not PAGO.search(texto):
        reiniciar()
        return estado_inscripcion(f"MAT-{int(MATRICULA.search(texto).group(1)):04d}")
    if MATRICULA.search(texto) and PAGO.search(texto):      # pago posterior: «pago MAT-0004 PAG-100003»
        mat = f"MAT-{int(MATRICULA.search(texto).group(1)):04d}"
        return procesar_pago(texto, mat)
    cancelar = palabras & PALABRAS_NO and not palabras & PALABRAS_SI
    if flujo_activo() and cancelar and (estado.get("paso") != "datos" or palabras & {"cancelar", "cancela", "salir"}):
        reiniciar()
        return DESPEDIDA

    paso = estado.get("paso")
    if CODIGO_HORARIO.search(texto) and paso in (None, "curso", "horario", "datos"):   # «inscribirme en H18»
        fila = _horario_por_codigo(texto)
        if fila is None:
            return f"No existe el horario {CODIGO_HORARIO.search(texto).group(0).upper()}. " + _pedir_curso()
        if _vac(fila) <= 0:
            return f"El horario {fila['codigo']} de {fila['curso']} ya no tiene vacantes. " + _pedir_horario(fila["curso"])
        estado.update(curso=fila["curso"], codigo=fila["codigo"], opciones=[fila["codigo"]])
        _extraer_datos(CODIGO_HORARIO.sub(" ", texto))
        if _datos_completos():
            return _resumen()
        return (f"Elegiste **{fila['codigo']}**: {fila['curso']} – " + _linea(1, fila)[3:] + "\n\n" + _pedir_datos())

    cursos = detectar_cursos(texto)
    if not cursos and estado.get("ultimo_curso") and paso in (None, "curso") and quiere_inscribirse(texto):
        cursos = [estado["ultimo_curso"]]                  # «quisiera inscribirme…» justo después de ver un curso

    # Cambio de curso en cualquier paso: si nombra otro curso (y no está enviando su correo), se cambia
    if cursos and len(cursos) == 1 and cursos[0] != estado.get("curso") and not EMAIL.search(texto) \
            and (paso in (None, "curso", "horario") or paso in ("datos", "confirmar")):
        estado.pop("codigo", None)
        return _pedir_horario(cursos[0], texto)
    if paso == "curso" and estado.get("candidatos"):
        cand = estado["candidatos"]
        elegidos = [c for c in cursos if c in cand]
        if len(elegidos) == 1:
            return _pedir_horario(elegidos[0], texto)
        num = re.search(r"\b(\d{1,2})\b", v._normalizar(texto))
        n = int(num.group(1)) if num else next((ORDINALES[w] for w in palabras if w in ORDINALES), None)
        if n and 1 <= n <= len(cand):
            return _pedir_horario(cand[n - 1], texto)
    if paso in (None, "curso"):
        if len(cursos) > 1:
            return _pedir_curso(cursos)
        if paso is None and "ese" in palabras and estado.get("ultimo_curso"):
            return _pedir_horario(estado["ultimo_curso"], texto)
        return _pedir_curso()

    if paso == "horario":
        ops = [f for f in _opciones(estado["curso"]) if f["codigo"] in estado.get("opciones", [])]
        elegido = _elegir_opcion(texto, ops)
        if not elegido:
            return _pedir_horario(estado["curso"])
        estado["codigo"] = elegido["codigo"]
        _extraer_datos(texto, con_nombre=False)
        return _resumen() if _datos_completos() else _pedir_datos()

    if paso == "datos":
        _extraer_datos(texto)
        return _resumen() if _datos_completos() else _pedir_datos()

    if paso == "confirmar":
        if palabras & PALABRAS_SI:
            r = registrar_matricula(estado["codigo"], estado["nombre"], estado["correo"],
                                    estado.get("numero_documento", ""), estado.get("telefono", ""))
            reiniciar()
            if r.startswith("ERROR"):
                return r.replace("ERROR: ", "No pude registrar la pre-inscripción: ") + " " + _pedir_curso()
            codigo, _, detalle = r[3:].partition(": ")
            return _pedir_pago(codigo, detalle)
        if palabras & PALABRAS_NO:
            reiniciar()
            return DESPEDIDA
        return "Solo necesito tu respuesta: escribe **sí** para registrar la pre-inscripción o **no** para cancelar."
    reiniciar()
    return _pedir_curso()
