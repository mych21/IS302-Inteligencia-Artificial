"""
Flujo de matrícula del MALI Asistente Estudiantil (solo librería estándar).

Pasos: 1) curso → 2) horario → 3) nombre y correo → 4) confirmación → registro.
Al confirmar: descuenta 1 vacante en datos/vacantes.csv y registra la matrícula en datos/matriculas.csv.

`procesar_mensaje(texto)` devuelve la indicación que el agente debe responder en cada paso. El estado de la
conversación se guarda en memoria (un usuario a la vez, suficiente para la demostración).
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import vacantes as v

ARCHIVO_MATRICULAS = v.AQUI / "datos" / "matriculas.csv"
CAMPOS_MATRICULA = ["codigo_matricula", "fecha_registro", "codigo_horario", "curso", "sede", "modalidad", "horario",
                    "periodo", "fecha_inicio", "nombre", "correo", "estado"]

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
    return (f"{n}. {f['sede']} – {f['horario']} – inicia {f['fecha_inicio']} ({f['periodo']}) – "
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

    nuevo = not ARCHIVO_MATRICULAS.exists()
    previas = 0 if nuevo else max(0, len(ARCHIVO_MATRICULAS.read_text(encoding="utf-8").splitlines()) - 1)
    codigo = f"MAT-{previas + 1:04d}"
    with open(ARCHIVO_MATRICULAS, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_MATRICULA)
        if nuevo:
            w.writeheader()
        w.writerow({"codigo_matricula": codigo, "fecha_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "codigo_horario": fila["codigo"], "curso": fila["curso"], "sede": fila["sede"],
                    "modalidad": fila.get("modalidad", ""), "horario": fila["horario"], "periodo": fila["periodo"],
                    "fecha_inicio": fila["fecha_inicio"], "nombre": nombre.strip(), "correo": correo.strip(),
                    "estado": "Pre-inscrito DEMO (pendiente de confirmación y pago)"})
    return (f"OK {codigo}: {nombre.strip()} quedó pre-inscrito(a) en {fila['curso']} – {fila['sede']} – "
            f"{fila['horario']}, inicia {fila['fecha_inicio']}. Vacantes restantes en ese horario: "
            f"{fila['vacantes_disponibles']}.")


# ------------------------------------------------------------------ conversación
def consultar_matriculas() -> str:
    """Lista las matrículas registradas en datos/matriculas.csv."""
    if not ARCHIVO_MATRICULAS.exists():
        return "Aún no hay matrículas registradas."
    filas = list(csv.DictReader(ARCHIVO_MATRICULAS.read_text(encoding="utf-8").splitlines()))
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
    return bool(_INTENCION.search(v._normalizar(texto)))


def fuera_del_flujo(texto: str) -> bool:
    """El usuario cambió de tema a mitad de la pre-inscripción (pregunta sin elegir curso u horario)."""
    paso = estado.get("paso")
    if paso not in ("curso", "horario"):
        return False
    pregunta = "?" in texto or "¿" in texto
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
            f"- Horario: {f['horario']}, inicia {f['fecha_inicio']} ({f['periodo']})\n"
            f"- Alumno(a): {estado['nombre']} – {estado['correo']}\n\n"
            "¿Confirmas la pre-inscripción? Responde **sí** para registrarla o **no** para cancelar.")


def procesar_mensaje(texto: str) -> str:
    """Devuelve el mensaje que el agente debe dar al usuario para el paso actual de la matrícula."""
    palabras = set(v._normalizar(texto).split())
    cancelar = palabras & PALABRAS_NO and not palabras & PALABRAS_SI
    if flujo_activo() and cancelar and (estado.get("paso") != "datos" or palabras & {"cancelar", "cancela", "salir"}):
        reiniciar()
        return DESPEDIDA

    cursos = detectar_cursos(texto)
    paso = estado.get("paso")

    # Cambio de curso en cualquier momento antes de confirmar
    if cursos and paso in (None, "curso", "horario") and (len(cursos) == 1 and cursos[0] != estado.get("curso")):
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
            return (f"¡Listo! Tu pre-inscripción quedó registrada con el código {codigo}.\n- {detalle}\n"
                    "Es una pre-inscripción de demostración (no es una matrícula oficial). Para matricularte de "
                    "verdad, escribe a cursosdearte@mali.pe.")
        if palabras & PALABRAS_NO:
            reiniciar()
            return DESPEDIDA
        return "Solo necesito tu respuesta: escribe **sí** para registrar la pre-inscripción o **no** para cancelar."
    reiniciar()
    return _pedir_curso()
