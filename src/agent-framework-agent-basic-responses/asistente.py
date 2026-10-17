"""
Orquestador de MALI Asistente: decide cómo se atiende cada mensaje.

Orden de decisión (las respuestas marcadas con * las arma el sistema, sin el modelo de lenguaje):
  1. Intentos de manipulación (prompt injection, pedir instrucciones o fuentes restringidas) ........ *
  2. Datos sensibles en el mensaje (DNI, tarjeta, contraseña): aviso y se descartan ................ *
  3. Sesión y perfiles: iniciar/cerrar sesión, ver perfil, habilitar personal (Coordinación) ........ *
  4. Pre-inscripción de demostración (curso → horario → datos → sí/no) ............................. *
  5. Saludo con aviso de privacidad ................................................................ *
  6. Gestión de alumnos (base restringida; solo perfiles autorizados) .............................. *
  7. Vacantes (archivo vacantes.csv) ............................................................... *
  8. Datos que no existen en las fuentes (precios, descuentos, becas, certificados) .................. *
  9. Base general (RAG): se recuperan fragmentos y el modelo redacta citando la fuente.
 10. Sin información suficiente en las fuentes: se reconoce y se deriva al canal oficial .............. *

Todas las consultas quedan en registros/consultas.csv (sin guardar el texto de la conversación).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import acceso
import conocimiento
import matricula
import vacantes as v

CANAL = "cursosdearte@mali.pe"


@dataclass
class Respuesta:
    tipo: str                     # inyeccion, sesion, matricula, saludo, gestion, vacantes, sin_dato, rag, sin_info…
    texto: str | None = None      # respuesta directa del sistema (None = la redacta el modelo)
    contexto: str = ""            # indicación + fragmentos para el modelo (solo tipo "rag")
    respaldo: str = ""            # respuesta extractiva si no se usa el modelo (evaluación sin modelo)
    fuentes: list[str] = field(default_factory=list)
    ms: float = 0.0


# ------------------------------------------------------------------ detectores
_INYECCION = re.compile(
    r"ignora\w*\s+(todas?\s+)?(tus|las|sus|mis)?\s*(instrucciones|reglas|indicaciones)|"
    r"olvida\w*\s+(todas?\s+)?(tus|las)?\s*(instrucciones|reglas)|"
    r"(muestra|muestrame|dime|revela|ensena|ensename|imprime|copia|pega|repite)\w*\s+.{0,25}"
    r"(prompt|instrucciones|reglas internas|configuracion|indicacion interna|system)|"
    r"(cuales|que)\s+(son|eran)\s+tus\s+(instrucciones|reglas)|system\s*prompt|prompt\s+del\s+sistema|"
    r"modo\s+(desarrollador|developer|dios|administrador|sin\s+restricciones)|jailbreak|"
    r"sin\s+restricciones|actua\s+como\s+(si\s+fueras\s+)?(administrador|coordinacion|coordinador|root)|"
    r"(contenido|muestra|lee|abre|descarga)\w*\s+.{0,20}(permisos\s*csv|usuarios\s*csv|alumnos\s*sinteticos|archivo\s+restringido|"
    r"base\s+restringida)|eres\s+ahora|a\s+partir\s+de\s+ahora\s+eres|desactiva\w*\s+.{0,15}(filtros|seguridad)")
_DNI = re.compile(r"\b\d{8}\b")
_TARJETA = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_CLAVE = re.compile(r"(?i)\b(contrase[nñ]a|password|clave)\b\s*(es|:)?\s*\S+")
_GESTION = re.compile(
    r"gesti[oó]n de alumnos|datos? (de|del) (los )?alumnos?|lista(do)? de (los )?alumnos|alumnos (con|que tienen)|"
    r"registros? de (los )?alumnos|base de (datos de )?alumnos|situaci[oó]n (administrativa )?del alumno|"
    r"asistencia del alumno|expediente|ficha del alumno|informaci[oó]n de (los )?alumnos|"
    r"alumnos? (matriculados|inscritos|retirados)", re.I)
_SIN_DATO = {"precio", "precios", "cuesta", "cuestan", "costo", "costos", "pension", "mensualidad", "tarifa",
             "descuento", "descuentos", "beca", "becas", "certificado", "certificados", "diploma", "promocion"}
_POLITICA = re.compile(r"\b(si me|cuando me|asegurad\w*|asegura|garantiz\w*|que pasa si|para que usan|"
                       r"como funciona|como se hace|que es la|que es el)\b")
_GRACIAS = {"gracias", "chau", "adios", "hasta luego", "nos vemos", "ok gracias", "muchas gracias"}

AVISO_PRIVACIDAD = (
    "🔒 *Aviso de privacidad:* soy un prototipo académico. No compartas DNI, tarjetas ni contraseñas personales "
    "(solo el personal ingresa su clave del asistente al iniciar sesión). "
    "Las consultas se registran solo con fecha, perfil, tipo y fuente (sin guardar tu conversación). "
    "Para tus derechos sobre datos personales (Ley N.º 29733) escribe a datos@mali.pe.")


def presentacion() -> str:
    if not acceso.autenticado():
        return (
            "¡Hola! Soy **MALI Asistente** 🎨, un prototipo académico de chatbot con IA para orientar a la comunidad "
            "educativa del Museo de Arte de Lima. Puedo ayudarte a:\n"
            "- Resolver dudas sobre cursos, talleres, sedes, procedimientos y canales de atención (con la fuente).\n"
            "- Ver los horarios y vacantes de los cursos.\n"
            "- Inscribirte en un curso (pre-inscripción y código de pago de demostración).\n\n"
            f"{AVISO_PRIVACIDAD}\n\n"
            "Para atenderte mejor, **¿eres estudiante o personal del MALI?** Responde «estudiante» o «personal». "
            "(Si eres estudiante también puedes preguntarme directamente.)")
    return (
        f"¡Hola, {acceso.sesion['usuario']}! Soy **MALI Asistente** 🎨. {acceso.describir_sesion()}\n\n"
        "Respondo con la fuente de cada dato y, si no tengo la información, te derivo al canal oficial.\n\n"
        f"{AVISO_PRIVACIDAD}\n\n¿En qué te puedo ayudar?")


_ES_ESTUDIANTE = {"estudiante", "soy estudiante", "alumno", "alumna", "soy alumno", "soy alumna", "soy estudiante del mali"}
_ES_PERSONAL = {"personal", "soy personal", "personal del mali", "soy personal del mali", "soy del personal",
                "docente", "soy docente", "profesor", "soy profesor", "coordinacion", "soy de coordinacion",
                "coordinacion academica", "soporte", "soporte ti", "soy de soporte", "trabajador", "soy trabajador"}
_MENSAJES_SENSIBLES: set[str] = set()     # huellas de mensajes con contraseña (para ocultarlos al modelo)


def registrar_mensaje_sensible(texto: str) -> None:
    import hashlib
    _MENSAJES_SENSIBLES.add(hashlib.sha256(texto.strip().encode("utf-8")).hexdigest())


def ocultar_si_sensible(texto: str) -> str:
    """Si el mensaje tenía una contraseña, devuelve una versión sin ella (para el historial que ve el modelo)."""
    import hashlib
    if hashlib.sha256(texto.strip().encode("utf-8")).hexdigest() in _MENSAJES_SENSIBLES:
        return "[mensaje de inicio de sesión oculto]"
    return texto


def _denegado(tipo: str, que: str) -> "Respuesta":
    acceso.registrar(tipo, "-", "denegado")
    return Respuesta("permiso_denegado", f"Con tu perfil ({acceso.sesion['perfil']}) no puedes {que}. "
                                         f"Puedes consultar: {acceso.DESCRIPCION_PERMISOS.get(acceso.sesion['perfil'], '')}.")


def es_inyeccion(texto: str) -> bool:
    return bool(_INYECCION.search(v._normalizar(texto)))


def _datos_sensibles(texto: str) -> tuple[str, list[str]]:
    hallados = []
    for nombre, patron in (("tarjeta", _TARJETA), ("DNI", _DNI), ("contraseña", _CLAVE)):
        if patron.search(texto):
            hallados.append(nombre)
            texto = patron.sub(" ", texto)
    return texto.strip(), hallados


_LOGIN = re.compile(r"(?:iniciar|inicia|inicio|abrir)\s+sesi[oó]n(?:\s+como)?\s+([\w.-]+)"
                    r"(?:\s+(?:con\s+)?(?:clave|contrase[nñ]a|password)?\s*:?\s*(\S+))?|\blogin\s+([\w.-]+)(?:\s+(\S+))?",
                    re.I)


def es_login(texto: str) -> bool:
    return bool(_LOGIN.search(texto))


def _comando_sesion(texto: str) -> str | None:
    n = v._normalizar(texto)
    m = _LOGIN.search(texto)
    if m:
        return acceso.iniciar_sesion(m.group(1) or m.group(3), m.group(2) or m.group(4))
    if re.search(r"(cerrar|cierra|salir de( la)?)\s+sesion|\blogout\b", n):
        return acceso.cerrar_sesion()
    if re.search(r"(que|cual)\s+(es\s+)?mi\s+perfil|\bmi perfil\b|que perfil tengo|con que (cuenta|perfil) estoy|"
                 r"\bquien soy\b", n):
        return acceso.describir_sesion()
    m = re.search(r"\b(habilita|habilitar|dale acceso a|dar acceso a|deshabilita|deshabilitar|quita\w* (el )?acceso a|"
                  r"retira\w* (el )?acceso a)\s+(a\s+)?([a-z0-9_.-]+)", n)
    if m:
        habilitar = m.group(1).startswith(("habilita", "dale", "dar"))
        return acceso.cambiar_habilitacion(m.group(5), habilitar)
    return None


def _pide_dato_inexistente(texto: str) -> bool:
    return bool(set(v._normalizar(texto).split()) & _SIN_DATO)


def _sin_informacion() -> str:
    return ("No tengo información suficiente sobre eso en mis fuentes autorizadas, así que prefiero no inventarla. "
            f"Te sugiero consultar a {CANAL} o la sección «Cursos y horarios» de https://educacion.mali.pe/. "
            "Puedo ayudarte con cursos, sedes, procedimientos, vacantes y pre-inscripción.")


def _indicacion_rag(pregunta: str, resultados) -> str:
    return ("Responde la pregunta usando SOLO estos fragmentos de la base de conocimiento del MALI. No agregues "
            "datos que no estén en ellos (cursos, horarios, precios, fechas, requisitos) ni explicaciones generales que "
            "no figuren en el texto, y no repitas párrafos. Si los fragmentos no "
            f"responden exactamente lo que se pregunta, dilo y sugiere {CANAL}. Responde en máximo 6 líneas y "
            "termina con la línea «Fuente:» copiando la fuente del fragmento usado.\n\n"
            + conocimiento.como_texto(resultados))


def _ficha_curso(curso: str) -> Respuesta:
    """Información de un curso armada solo con las fuentes: su categoría (base general) y sus horarios
    (vacantes.csv). Evita que el modelo complete con conocimiento general."""
    doc = conocimiento.documento_que_menciona(curso)
    partes = []
    if doc:
        partes.append(f"**{curso}** forma parte de: {doc.titulo.lower()} de MALI Educación.")
    partes.append(v.vacantes_para_usuario(curso))
    if doc:
        partes.append(f"Fuente de la oferta: {doc.fuente}")
    acceso.registrar("curso", "vacantes.csv", "atendida")
    return Respuesta("curso", "\n\n".join(partes), fuentes=([doc.id] if doc else []) + ["vacantes.csv"])


# ------------------------------------------------------------------ orquestación
def _decidir(pregunta: str) -> Respuesta:
    texto = pregunta.strip()
    if acceso.pendiente.get("usuario"):  # el mensaje es la contraseña del usuario que inició sesión
        usuario = acceso.pendiente["usuario"]
        if v._normalizar(texto).strip() in ("cancelar", "salir"):
            acceso.pendiente.clear()
            return Respuesta("sesion", "Inicio de sesión cancelado.")
        registrar_mensaje_sensible(texto)
        return Respuesta("sesion", acceso.iniciar_sesion(usuario, texto), fuentes=["usuarios.csv"])
    n0 = v._normalizar(texto).strip(" !.")
    if acceso.pendiente.get("esperando_usuario"):        # personal: el mensaje es su usuario
        acceso.pendiente.clear()
        if n0 in ("cancelar", "salir", "estudiante", "soy estudiante"):
            return Respuesta("perfil", "De acuerdo, te atiendo como **estudiante**. ¿En qué te puedo ayudar?")
        return Respuesta("sesion", acceso.iniciar_sesion(texto.split()[0]), fuentes=["usuarios.csv"])
    if n0 in _ES_ESTUDIANTE:
        if acceso.autenticado():
            acceso.cerrar_sesion()
        return Respuesta("perfil", "Perfecto, te atiendo como **estudiante** (no necesitas iniciar sesión). Puedo "
                                   "ayudarte con cursos, procedimientos, horarios y vacantes, e inscribirte en un curso. "
                                   "¿Qué te gustaría saber?")
    if n0 in _ES_PERSONAL:
        if acceso.autenticado():
            return Respuesta("perfil", acceso.describir_sesion())
        acceso.pendiente.update(esperando_usuario=True)
        return Respuesta("perfil", "Para el personal del MALI necesito verificar tu perfil. 🔐 Escribe tu **usuario** "
                                   "(por ejemplo, coord01).")
    if es_login(texto):                  # antes de los filtros: la contraseña no es un dato a descartar
        registrar_mensaje_sensible(texto)
        return Respuesta("sesion", _comando_sesion(texto), fuentes=["usuarios.csv"])
    if es_inyeccion(texto):
        acceso.registrar("intento_inyeccion", "-", "bloqueado")
        return Respuesta("inyeccion", "No puedo compartir mis instrucciones internas, cambiar mis reglas ni mostrar "
                                      "fuentes restringidas. Con gusto te ayudo con cursos, procedimientos, vacantes "
                                      "o pre-inscripción.")

    limpio, sensibles = _datos_sensibles(texto)
    if sensibles:
        acceso.registrar("dato_sensible", "-", "descartado")
        aviso = (f"⚠️ Por tu seguridad no compartas tu {', '.join(sensibles)}: no lo necesito y no lo guardé.")
        if len(limpio.split()) < 2 and not matricula.flujo_activo():
            return Respuesta("dato_sensible", aviso + " ¿En qué te puedo ayudar?")
        r = _decidir(limpio)
        r.texto = aviso + "\n\n" + (r.texto or "")
        if r.tipo == "rag":
            r.texto, r.tipo = aviso + "\n\n" + r.respaldo, "rag_con_aviso"
        return r

    cmd = _comando_sesion(texto)
    if cmd:
        return Respuesta("sesion", cmd, fuentes=["usuarios.csv"])

    norm0 = v._normalizar(texto)
    if re.search(r"registro de consultas|\bauditoria\b|ver (el )?registro", norm0):
        return Respuesta("administracion", acceso.ver_registro(), fuentes=["consultas.csv"])
    if re.search(r"(ver|revisar|lista\w*) (los )?permisos|quien(es)? tiene(n)? acceso", norm0):
        return Respuesta("administracion", acceso.ver_permisos(), fuentes=["usuarios.csv"])
    m = re.search(r"(actualiza\w*|cambia\w*|modifica\w*)\s+(las\s+)?vacantes\s+(de(l)?\s+)?(h\s?\d{1,2})\s+(a\s+)?(\d{1,3})", norm0)
    if m:
        codigo = "H{:02d}".format(int(re.sub(r"\D", "", m.group(5))))
        return Respuesta("administracion", acceso.actualizar_vacantes(codigo, int(m.group(7))),
                         fuentes=["vacantes.csv"])

    if matricula.flujo_activo() and (matricula.fuera_del_flujo(texto)
                                     or v._normalizar(texto).strip(" !.") in _GRACIAS):
        matricula.reiniciar()            # cambió de tema: se deja la pre-inscripción y se atiende la pregunta
    consulta_de_politica = bool(_POLITICA.search(v._normalizar(texto)))
    if matricula.flujo_activo() or (matricula.quiere_inscribirse(texto) and not consulta_de_politica):
        if not acceso.autorizar("inscripcion"):
            matricula.reiniciar()
            return _denegado("pre_inscripcion", "hacer pre-inscripciones (están disponibles para estudiantes)")
        acceso.registrar("pre_inscripcion", "vacantes.csv", "atendida")
        return Respuesta("matricula", matricula.procesar_mensaje(texto), fuentes=["vacantes.csv"])

    if matricula.es_saludo(texto):
        return Respuesta("saludo", presentacion())

    if acceso.ID_ALUMNO.search(texto) or _GESTION.search(texto):
        r = acceso.consultar_gestion(texto)
        return Respuesta("gestion" if r != acceso.DENEGADO else "gestion_denegada", r,
                         fuentes=["alumnos_sinteticos.csv"])

    cursos = matricula.detectar_cursos(texto)
    norm = v._normalizar(texto)
    if len(cursos) == 1:
        matricula.estado["ultimo_curso"] = cursos[0]
    pide_horario = bool(re.search(r"horario|cuando|inicia|empieza|turno|dias|hora\b|sede", norm))
    seguimiento = (not cursos and matricula.estado.get("ultimo_curso") and len(norm.split()) <= 6
                   and (pide_horario or v._pide_vacantes(texto)))
    if seguimiento:                      # «¿y los horarios?» después de preguntar por un curso
        cursos = [matricula.estado["ultimo_curso"]]
    if len(cursos) == 1 and not _pide_dato_inexistente(texto) and not consulta_de_politica \
            and (seguimiento or pide_horario or v._pide_vacantes(texto)
                 or re.search(r"informacion|info|detalle|sobre|ensenan|tienen|hay|ofrecen|dictan|curso de|taller de",
                              norm) or len(norm.split()) <= 3):
        if not acceso.autorizar("vacantes"):
            return _denegado("vacantes", "consultar vacantes")
        return _ficha_curso(cursos[0])
    if v._pide_vacantes(texto) and not consulta_de_politica:
        if not acceso.autorizar("vacantes"):
            return _denegado("vacantes", "consultar vacantes")
        acceso.registrar("vacantes", "vacantes.csv", "atendida")
        return Respuesta("vacantes", v.vacantes_para_usuario(texto), fuentes=["vacantes.csv"])

    if _pide_dato_inexistente(texto):
        acceso.registrar("sin_informacion", "-", "derivada")
        return Respuesta("sin_dato", "No tengo ese dato en mis fuentes autorizadas (no cuento con precios, "
                                     "descuentos, becas ni certificados) y prefiero no inventarlo. "
                                     f"Consulta a {CANAL} o la sección «Cursos y horarios» de "
                                     "https://educacion.mali.pe/.")

    if v._normalizar(texto).strip(" !.") in _GRACIAS:
        return Respuesta("cortesia", "¡Con gusto! Si necesitas algo más sobre los cursos del MALI, aquí estaré. 😊")

    if not acceso.autorizar("general"):
        return _denegado("base_general", "consultar la base general")
    resultados = conocimiento.buscar(texto)
    if resultados:
        d = resultados[0][0]
        acceso.registrar("base_general", d.id, "atendida")
        return Respuesta("rag", None, contexto=_indicacion_rag(texto, resultados),
                         respaldo=f"{d.texto}\nFuente: {d.fuente} [{d.id} – {d.titulo}]",
                         fuentes=[x.id for x, _ in resultados])

    acceso.registrar("sin_informacion", "-", "derivada")
    return Respuesta("sin_info", _sin_informacion())


def responder(pregunta: str) -> Respuesta:
    inicio = time.perf_counter()
    r = _decidir(pregunta)
    r.ms = (time.perf_counter() - inicio) * 1000
    return r
