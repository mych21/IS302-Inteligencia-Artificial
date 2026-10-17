"""
Conversación de inscripción de MALI Asistente (curso → horario → datos → confirmación → pago).

Este módulo solo conduce el diálogo: los horarios se leen a través del servidor MCP general y la pre-inscripción,
el pago y la ficha final se registran a través del servidor MCP restringido. El estado de la conversación se guarda
en memoria (un usuario a la vez, suficiente para la demostración).
"""
from __future__ import annotations

import re

import cliente_mcp
import texto as tx
from datos_restringidos import EMAIL, MATRICULA

PAGO = re.compile(r"\bPAG[-\s]?(\d{6})\b", re.I)
DATOS_REQUERIDOS = [("nombre", "tu nombre completo"), ("numero_documento", "tu número de documento (DNI o CE)"),
                    ("telefono", "un teléfono de contacto"),
                    ("correo", "un correo electrónico válido (por ejemplo, nombre@gmail.com)")]
PALABRAS_SALUDO = {"hola", "buenas", "buenos", "hey", "saludos", "holi", "eres", "ayudar", "ayudarme", "ayudame",
                   "ayuda", "presentate", "haces"}
PALABRAS_SI = {"si", "confirmo", "confirmar", "ok", "dale", "acepto", "correcto", "listo", "claro", "perfecto",
               "yes", "va", "procede"}
PALABRAS_NO = {"no", "cancelar", "cancela", "cancelo", "salir", "olvidalo", "detener"}
ORDINALES = {"primer": 1, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercer": 3, "tercero": 3,
             "tercera": 3, "cuarto": 4, "cuarta": 4, "quinto": 5, "quinta": 5, "uno": 1, "dos": 2, "tres": 3,
             "cuatro": 4, "cinco": 5}

DESPEDIDA = (
    "Entendido, no registré ninguna pre-inscripción. ¡Gracias por conversar conmigo! 😊\n"
    "Espero que puedas matricularte próximamente: revisa los cursos y las vacantes disponibles cuando quieras, "
    "aquí estaré para ayudarte.")

estado: dict = {}


def reiniciar() -> None:
    estado.clear()


# ------------------------------------------------------------------ horarios (servidor MCP general)
def horarios() -> list[dict]:
    return cliente_mcp.llamar_json("general", "listar_horarios")


def _restringido(herramienta: str, **argumentos) -> str:
    return cliente_mcp.llamar("restringido", herramienta, **argumentos)


def _cursos_disponibles() -> list[str]:
    return sorted({f["curso"] for f in horarios() if f["vacantes_disponibles"] > 0})


def detectar_cursos(texto: str) -> list[str]:
    return tx.detectar_cursos(texto, horarios())


def pide_vacantes(texto: str) -> bool:
    return tx.pide_vacantes(texto, {f["periodo"] for f in horarios()})


def _opciones(curso: str, sede_texto: str = "") -> list[dict]:
    ops = [f for f in horarios() if f["curso"] == curso and f["vacantes_disponibles"] > 0]
    if sede_texto:
        por_sede = [f for f in ops if (tx.conjunto(sede_texto) - tx.GENERICAS_SEDE)
                    & (tx.conjunto(f["sede"]) - tx.GENERICAS_SEDE)]
        if por_sede:
            return por_sede
    return ops


def _linea(n: int, f: dict) -> str:
    return (f"{n}. {f['sede']} – {f['horario']} – del {f['fecha_inicio']} al {f.get('fecha_fin', '-')} "
            f"({f['periodo']}) – {f['publico']} – {f['vacantes_disponibles']} vacante(s) [código {f['codigo']}]")


_DIAS = {"lunes": "lun", "lun": "lun", "martes": "mar", "miercoles": "mie", "mie": "mie", "jueves": "jue",
         "jue": "jue", "viernes": "vie", "vie": "vie", "sabado": "sab", "sabados": "sab", "sab": "sab"}


def _puntaje_opcion(texto: str, f: dict) -> int:
    """Qué tanto coincide lo que escribió el usuario (sede, días, hora) con un horario."""
    import difflib
    norm = tx.normalizar(texto)
    palabras = norm.split()
    puntos = 0
    claves_sede = tx.conjunto(f["sede"]) - tx.GENERICAS_SEDE
    for p in palabras:
        if len(p) > 3 and (p in claves_sede or difflib.get_close_matches(p, claves_sede, 1, 0.75)):
            puntos += 2
    dias_horario = {_DIAS[d] for d in tx.normalizar(f["horario"]).split() if d in _DIAS}
    dias_texto = {_DIAS[p] for p in palabras if p in _DIAS}
    if dias_texto:
        puntos += 2 if dias_texto == dias_horario else (1 if dias_texto & dias_horario else -1)
    inicio = re.search(r"(\d{1,2}):\d{2}", f["horario"])
    horas = [int(h) for h in re.findall(r"\b(\d{1,2})(?::\d{2})?\b", norm) if int(h) <= 23]
    if inicio and horas:
        puntos += 2 if int(inicio.group(1)) in horas or int(inicio.group(1)) - 12 in horas else -1
    return puntos


def _elegir_opcion(texto: str, ops: list[dict]) -> dict | None:
    norm = tx.normalizar(texto)
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
    return next((f for f in horarios() if f["codigo"].upper() == f"H{int(cod.group(1)):02d}"), None)


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
    comunes = tx.STOPWORDS | tx.RELLENO | PALABRAS_SI | PALABRAS_NO | {
        "el", "la", "los", "las", "proyecto", "curso", "cursos", "vacante", "vacantes", "horario", "explica",
        "explicame", "que", "como", "cuando", "donde", "gracias", "hola", "quiero", "ver", "otro", "otra"}
    con_prefijo = bool(re.search(r"(?i)\b(me llamo|mi nombre es|soy)\b", texto)) or bool(correo)
    capitalizado = bool(palabras) and all(p[0].isupper() for p in palabras
                                          if p.lower() not in {"de", "del", "la", "los", "las", "y"})
    normalizadas = set(tx.normalizar(" ".join(palabras)).split())
    if not (con_prefijo or capitalizado) and normalizadas & comunes:
        return
    if len(palabras) >= 2 and not normalizadas & (PALABRAS_SI | PALABRAS_NO):
        estado["nombre"] = " ".join(p.capitalize() for p in palabras[:5])


def ocultar(valor: str, visibles: int = 3) -> str:
    """Muestra solo los últimos dígitos (p. ej. «*****678»)."""
    d = re.sub(r"\D", "", valor or "")
    return ("*" * max(0, len(d) - visibles) + d[-visibles:]) if d else "-"


# ------------------------------------------------------------------ pago (servidor MCP restringido)
def _pedir_pago(codigo_matricula: str, detalle: str) -> str:
    estado.clear()
    estado.update(paso="pago", codigo_matricula=codigo_matricula)
    id_alumno = _restringido("codigo_de_alumno", codigo_matricula=codigo_matricula)
    return (f"¡Listo! Tu pre-inscripción quedó registrada con el código **{codigo_matricula}**.\n"
            f"- Tu **código de alumno** es **{id_alumno}** (guárdalo para tus trámites).\n- {detalle}\n\n"
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
    r = _restringido("registrar_pago", codigo_matricula=codigo_matricula, codigo_pago=f"PAG-{m.group(1)}")
    if r.startswith("ERROR"):
        if "en revisión" in r:
            reiniciar()
            return r.replace("ERROR: ", "")
        return r.replace("ERROR: ", "No pude registrar el pago: ") + " Revisa el código e inténtalo de nuevo."
    reiniciar()
    return _restringido("ficha_inscripcion", codigo_matricula=codigo_matricula, mostrar_nombre=en_flujo,
                        por_confirmar=r == "POR_CONFIRMAR")


# ------------------------------------------------------------------ conversación
def es_saludo(texto: str) -> bool:
    palabras = set(tx.normalizar(texto).split())
    return bool(palabras & PALABRAS_SALUDO) and not pide_vacantes(texto) and not detectar_cursos(texto) \
        and not quiere_inscribirse(texto)


CODIGO_HORARIO = re.compile(r"\bh\s?-?(\d{1,2})\b", re.I)
_INTENCION = re.compile(
    r"\b(inscrib(irme|eme|irte|ir a mi|irlo|irla|o)\b|(quisiera|quiero|deseo|me gustaria|puedo) inscribir\b|"
    r"inscripcion en|matricul(arme|ame|o|ar a mi)\b|(quisiera|quiero|deseo) matricular\b|me apunto|"
    r"pre ?inscrib\w*|pre ?inscripcion|agend\w*|reserv(ar|ame|a|o)\s+(una\s+|mi\s+)?(vacante|cupo|horario)|"
    r"separ(ar|ame|o)\s+(una\s+|mi\s+)?(vacante|cupo)|apuntame|quiero\s+(inscribir|matricular|llevar)\w*)")


def quiere_inscribirse(texto: str) -> bool:
    """Intención explícita de inscribirse («quiero inscribirme», «inscríbeme», «agéndame una vacante»…)."""
    return bool(_INTENCION.search(tx.normalizar(texto))) or bool(MATRICULA.search(texto) and PAGO.search(texto)) \
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
    eligio = bool(detectar_cursos(texto)) or bool(re.search(r"\b\d{1,2}\b|\bh\d", tx.normalizar(texto))) \
        or bool(set(tx.normalizar(texto).split()) & set(ORDINALES))
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
    f = next(x for x in horarios() if x["codigo"] == estado["codigo"])
    estado["paso"] = "confirmar"
    return (f"Revisa tu pre-inscripción:\n- Curso: {f['curso']}\n- Sede: {f['sede']} ({f['modalidad']})\n"
            f"- Horario: {f['horario']}\n- Duración: del {f['fecha_inicio']} al {f.get('fecha_fin', '-')} ({f['periodo']})\n"
            f"- Alumno(a): {estado['nombre']} – documento {ocultar(estado['numero_documento'])} – "
            f"teléfono {ocultar(estado['telefono'])} – {estado['correo']}\n\n"
            "¿Confirmas la pre-inscripción? Responde **sí** para registrarla o **no** para cancelar.")


def procesar_mensaje(texto: str) -> str:
    """Devuelve el mensaje que el agente debe dar al usuario para el paso actual de la matrícula."""
    palabras = set(tx.normalizar(texto).split())
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

    paso = estado.get("paso")
    if CODIGO_HORARIO.search(texto) and paso in (None, "curso", "horario", "datos"):   # «inscribirme en H18»
        fila = _horario_por_codigo(texto)
        if fila is None:
            return f"No existe el horario {CODIGO_HORARIO.search(texto).group(0).upper()}. " + _pedir_curso()
        if fila["vacantes_disponibles"] <= 0:
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
        num = re.search(r"\b(\d{1,2})\b", tx.normalizar(texto))
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
            r = _restringido("registrar_matricula", codigo_horario=estado["codigo"], nombre=estado["nombre"],
                             correo=estado["correo"], numero_documento=estado.get("numero_documento", ""),
                             telefono=estado.get("telefono", ""))
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
