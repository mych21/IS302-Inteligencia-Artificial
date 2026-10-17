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
CAMPOS_MATRICULA = ["codigo_matricula", "id_alumno", "nombre", "correo", "curso", "codigo_horario", "sede",
                    "modalidad", "horario", "periodo", "fecha_inicio", "fecha_fin", "estado", "codigo_pago",
                    "fecha_registro", "origen"]

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


def _elegir_opcion(texto: str, ops: list[dict]) -> dict | None:
    norm = v._normalizar(texto)
    cod = re.search(r"\bh\s?(\d{1,3})\b", norm)
    if cod:
        codigo = f"H{int(cod.group(1)):02d}"
        return next((f for f in ops if f["codigo"].upper() == codigo), None)
    num = re.search(r"\b(\d{1,2})\b", norm)
    n = int(num.group(1)) if num else next((ORDINALES[w] for w in norm.split() if w in ORDINALES), None)
    if n and 1 <= n <= len(ops):
        return ops[n - 1]
    t = v._set(texto) - v._GENERICAS_SEDE
    por_sede = [f for f in ops if t & (v._set(f["sede"]) - v._GENERICAS_SEDE)]
    if len(por_sede) == 1:
        return por_sede[0]
    if len(ops) == 1 and set(norm.split()) & PALABRAS_SI:
        return ops[0]
    return None


def _extraer_datos(texto: str, con_nombre: bool = True) -> None:
    correo = EMAIL.search(texto)
    if correo:
        estado["correo"] = correo.group(0)
        texto = texto.replace(correo.group(0), " ")
    texto = re.sub(r"\S*[@.]\S*", " ", texto)          # restos de un correo incompleto
    limpio = re.sub(r"(?i)\b(me llamo|mi nombre es|mi nombre|nombre|soy|mi correo es|mi correo|correo|email|"
                    r"electr[oó]nico|es|y|mi)\b", " ", texto)
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


def registrar_matricula(codigo_horario: str, nombre: str, correo: str) -> str:
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
    ids = [int(m["id_alumno"][4:]) for m in matriculas if m.get("id_alumno", "").startswith("ALU-")]
    previo = next((m["id_alumno"] for m in matriculas if m.get("correo", "").lower() == correo.strip().lower()
                   and m.get("id_alumno")), None)
    id_alumno = previo or f"ALU-{max(ids + [200]) + 1:04d}"
    matriculas.append({"codigo_matricula": codigo, "id_alumno": id_alumno, "origen": "asistente",
                       "fecha_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                       "codigo_horario": fila["codigo"], "curso": fila["curso"], "sede": fila["sede"],
                       "modalidad": fila.get("modalidad", ""), "horario": fila["horario"], "periodo": fila["periodo"],
                       "fecha_inicio": fila["fecha_inicio"], "fecha_fin": fila.get("fecha_fin", ""),
                       "nombre": nombre.strip(), "correo": correo.strip(),
                       "estado": "Pre-inscrito (pendiente de pago)", "codigo_pago": ""})
    _guardar_matriculas(matriculas)
    return (f"OK {codigo}: {nombre.strip()} quedó pre-inscrito(a) en {fila['curso']} – {fila['sede']} – "
            f"{fila['horario']}, del {fila['fecha_inicio']} al {fila.get('fecha_fin', '-')}. Vacantes restantes en ese horario: "
            f"{fila['vacantes_disponibles']}.")


# ------------------------------------------------------------------ pago y confirmación final
def _leer_pagos() -> list[dict]:
    with open(ARCHIVO_PAGOS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validar_pago(codigo_matricula: str, codigo_pago: str) -> str:
    """Valida un código de pago de demostración (datos/pagos_demo.csv) y completa la inscripción."""
    matriculas = _leer_matriculas()
    mat = next((m for m in matriculas if m["codigo_matricula"].upper() == codigo_matricula.upper()), None)
    if mat is None:
        return f"ERROR: no encontré la pre-inscripción {codigo_matricula}."
    if mat.get("codigo_pago"):
        return f"ERROR: la inscripción {codigo_matricula} ya tiene un pago validado ({mat['codigo_pago']})."
    pagos = _leer_pagos()
    pago = next((p for p in pagos if p["codigo_pago"].upper() == codigo_pago.upper()), None)
    if pago is None:
        return f"ERROR: el código de pago {codigo_pago} no existe."
    if pago["estado"] != "disponible":
        return f"ERROR: el código de pago {codigo_pago} ya fue usado."
    pago.update(estado="usado", codigo_matricula=mat["codigo_matricula"],
                fecha_uso=datetime.now().strftime("%d/%m/%Y %H:%M"))
    with open(ARCHIVO_PAGOS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pagos[0]))
        w.writeheader()
        w.writerows(pagos)
    mat.update(estado="Matriculado", codigo_pago=pago["codigo_pago"])
    _guardar_matriculas(matriculas)
    return "OK"


def ficha_inscripcion(codigo_matricula: str, mostrar_nombre: bool = True) -> str:
    """Resumen final con el horario, la información del curso y recordatorios tomados de las fuentes."""
    import conocimiento
    mat = next(m for m in _leer_matriculas() if m["codigo_matricula"] == codigo_matricula)
    filas, _, _ = _leer_tabla()
    hor = next((f for f in filas if f["codigo"] == mat["codigo_horario"]), {})
    doc = conocimiento.documento_que_menciona(mat["curso"])
    lineas = [f"🎉 ¡Matrícula completada! Código de matrícula **{mat['codigo_matricula']}** · pago **{mat['codigo_pago']}** validado.",
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
        return r.replace("ERROR: ", "No pude validar el pago: ") + " Revisa el código e inténtalo de nuevo."
    reiniciar()
    return ficha_inscripcion(codigo_matricula, mostrar_nombre=en_flujo)


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


_INTENCION = re.compile(
    r"\b(inscrib(irme|eme|irte|ir a mi|irlo|irla|o)|inscripcion en|matricul(arme|ame|o|ar a mi)|"
    r"pre ?inscrib\w*|pre ?inscripcion|agend\w*|reserv(ar|ame|a|o)\s+(una\s+|mi\s+)?(vacante|cupo|horario)|"
    r"separ(ar|ame|o)\s+(una\s+|mi\s+)?(vacante|cupo)|apuntame|quiero\s+(inscribir|matricular|llevar)\w*)")


def quiere_inscribirse(texto: str) -> bool:
    """Intención explícita de inscribirse («quiero inscribirme», «inscríbeme», «agéndame una vacante»…)."""
    return bool(_INTENCION.search(v._normalizar(texto))) or bool(MATRICULA.search(texto) and PAGO.search(texto))


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
    if len(ops) == 1:
        estado.update(paso="datos", codigo=ops[0]["codigo"])
        if estado.get("nombre") and estado.get("correo"):
            return f"{curso} tiene un solo horario con vacantes.\n\n" + _resumen()
        return (f"{curso} tiene este horario con vacantes:\n" + _linea(1, ops[0])[3:] +
                "\nSi te acomoda, envíame tu nombre completo y tu correo electrónico para registrar tu pre-inscripción "
                "(o escribe «cancelar»).")
    return (f"Estos son los horarios de {curso} con vacantes:\n" + "\n".join(_linea(i, f) for i, f in enumerate(ops, 1))
            + "\n¿Cuál horario eliges? Responde con el número de la opción.")


def _pedir_datos() -> str:
    estado["paso"] = "datos"
    falta = [x for x, k in (("tu nombre completo", "nombre"),
                            ("un correo electrónico válido (por ejemplo, nombre@gmail.com)", "correo"))
             if not estado.get(k)]
    return ("Para registrar tu pre-inscripción necesito " + " y ".join(falta) +
            ". Por ejemplo: «Mario Pérez, mario@gmail.com». (Escribe «cancelar» si prefieres salir.)")


def _resumen() -> str:
    filas, _, _ = _leer_tabla()
    f = next(x for x in filas if x["codigo"] == estado["codigo"])
    estado["paso"] = "confirmar"
    return (f"Revisa tu pre-inscripción:\n- Curso: {f['curso']}\n- Sede: {f['sede']} ({f['modalidad']})\n"
            f"- Horario: {f['horario']}\n- Duración: del {f['fecha_inicio']} al {f.get('fecha_fin', '-')} ({f['periodo']})\n"
            f"- Alumno(a): {estado['nombre']} – {estado['correo']}\n\n"
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
    if MATRICULA.search(texto) and PAGO.search(texto):      # pago posterior: «pago MAT-0004 PAG-100003»
        mat = f"MAT-{int(MATRICULA.search(texto).group(1)):04d}"
        return procesar_pago(texto, mat)
    cancelar = palabras & PALABRAS_NO and not palabras & PALABRAS_SI
    if flujo_activo() and cancelar and (estado.get("paso") != "datos" or palabras & {"cancelar", "cancela", "salir"}):
        reiniciar()
        return DESPEDIDA

    cursos = detectar_cursos(texto)
    paso = estado.get("paso")

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
        return _resumen() if estado.get("nombre") and estado.get("correo") else _pedir_datos()

    if paso == "datos":
        _extraer_datos(texto)
        return _resumen() if estado.get("nombre") and estado.get("correo") else _pedir_datos()

    if paso == "confirmar":
        if palabras & PALABRAS_SI:
            r = registrar_matricula(estado["codigo"], estado["nombre"], estado["correo"])
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
