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
_GESTION_LIBRE = re.compile(r"\b(cuantos|cuantas|total|numero|cantidad|lista\w*|listado|quienes|reporte)\b.*\balumn|"
                            r"\balumn\w*\b.*\b(matricul|inscrit|retirad)|\bmatriculados\b|\bregistro de matricula")
_SIN_DATO = {"precio", "precios", "cuesta", "cuestan", "costo", "costos", "pension", "mensualidad", "tarifa",
             "descuento", "descuentos", "beca", "becas", "certificado", "certificados", "diploma", "promocion"}
_POLITICA = re.compile(r"\b(si me|cuando me|asegurad\w*|asegura|garantiz\w*|que pasa si|para que usan|"
                       r"como funciona|como se hace|que es la|que es el)\b")
_GRACIAS = {"gracias", "chau", "adios", "hasta luego", "nos vemos", "ok gracias", "muchas gracias"}

AVISO_PRIVACIDAD = (
    "🔒 *Aviso de privacidad:* soy un prototipo académico. No compartas tarjetas ni contraseñas personales. "
    "Tu documento y teléfono solo te los pediré al inscribirte y solo los verá el personal del MALI. "
    "Las consultas se registran solo con fecha, perfil, tipo y fuente (sin guardar tu conversación). "
    "Para tus derechos sobre datos personales (Ley N.º 29733) escribe a datos@mali.pe.")


def presentacion() -> str:
    if not acceso.autenticado():
        return (
            "¡Hola! Soy **MALI Asistente** 🎨, un prototipo académico de chatbot con IA para orientar a la comunidad "
            "educativa del Museo de Arte de Lima.\n\n"
            f"{AVISO_PRIVACIDAD}\n\n" + abrir_menu("rol"))
    return (f"¡Hola, {acceso.sesion['usuario']}! Soy **MALI Asistente** 🎨. {acceso.describir_sesion()}\n\n"
            + abrir_menu("personal"))


_ES_ESTUDIANTE = {"estudiante", "soy estudiante", "alumno", "alumna", "soy alumno", "soy alumna", "soy estudiante del mali"}
_ES_PERSONAL = {"personal", "soy personal", "personal del mali", "soy personal del mali", "soy del personal",
                "docente", "soy docente", "profesor", "soy profesor", "coordinacion", "soy de coordinacion",
                "coordinacion academica", "soporte", "soporte ti", "soy de soporte", "trabajador", "soy trabajador"}
_PALABRAS_ESTUDIANTE = {"estudiante", "alumno", "alumna"}
_PALABRAS_PERSONAL = {"personal", "docente", "profesor", "profesora", "coordinacion", "coordinador", "coordinadora",
                      "soporte", "trabajador", "trabajadora", "administrativo", "administrativa", "staff", "colaborador"}


def _comando_sesion_simple(texto: str) -> bool:
    return bool(re.search(r"sesion|perfil|habilita|acceso|registro|vacantes", v._normalizar(texto)))


def _responde_rol(texto: str, palabras: set[str]) -> bool:
    """Respuesta corta a «¿eres estudiante o personal?» (p. ej. «personal mali», «soy docente»)."""
    t = v._normalizar(texto).split()
    if _GESTION.search(texto) or acceso.ID_ALUMNO.search(texto) or _comando_sesion_simple(texto):
        return False
    return 0 < len(t) <= 5 and "?" not in texto and bool(set(t) & palabras) and not \
        (set(t) & (_PALABRAS_ESTUDIANTE if palabras is _PALABRAS_PERSONAL else _PALABRAS_PERSONAL))


_MENSAJES_SENSIBLES: set[str] = set()     # huellas de mensajes con contraseña (para ocultarlos al modelo)


def registrar_mensaje_sensible(texto: str) -> None:
    import hashlib
    _MENSAJES_SENSIBLES.add(hashlib.sha256(texto.strip().encode("utf-8")).hexdigest())


def ocultar_si_sensible(texto: str) -> str:
    """Si el mensaje tenía una contraseña, devuelve una versión sin ella (para el historial que ve el modelo)."""
    import hashlib
    if hashlib.sha256(texto.strip().encode("utf-8")).hexdigest() in _MENSAJES_SENSIBLES:
        return "[mensaje oculto: contenía una contraseña o un documento de verificación]"
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
            f"responden exactamente lo que se pregunta, dilo y sugiere {CANAL}. Responde en máximo 3 oraciones, sin repetir "
            "ideas, y "
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


# ------------------------------------------------------------------ estado de matrícula (estudiantes)
consulta_estado: dict = {}          # {"paso": "codigo" | "documento", "codigo": "ALU-0205"}
_PIDE_ESTADO = re.compile(r"\bestado\b.*\b(matricula|inscripcion|preinscripcion|pago)|"
                          r"\b(mi|mis) (matricula|inscripcion|preinscripcion)\b.*\b(como|va|esta|consult|ver)|"
                          r"\b(como|consult\w*|ver|revisar)\b.*\b(mi|mis) (matricula|inscripcion)")
_DATOS_DE_ALUMNO = re.compile(r"\b(datos|ficha|asistencia|situacion|expediente|deuda|telefono|correo|dni|"
                              r"documento|historial|notas|informacion)\b")
_CODIGO_ESTADO = re.compile(r"\b(ALU|MAT)[-\s]?(\d{1,4})\b", re.I)
_DOCUMENTO = re.compile(r"(?<![\w-])(\d[\d .]{6,14}\d)(?![\w-])")


def _verificar_estado(codigo: str, texto_doc: str) -> Respuesta:
    consulta_estado.clear()
    registrar_mensaje_sensible(texto_doc)          # el documento no llega al modelo ni al registro
    m = _DOCUMENTO.search(texto_doc)
    ident = matricula.verificar_alumno(codigo, m.group(1) if m else "")
    if not ident:
        acceso.registrar("estado_matricula", "matricula.csv", "denegado")
        return Respuesta("verificacion", "Los datos no coinciden con nuestros registros, así que por seguridad no "
                                         "puedo mostrar el estado. Revisa tu código de alumno y tu documento, o "
                                         f"escribe a {CANAL}.")
    acceso.registrar("estado_matricula", "matricula.csv", "permitido")
    return Respuesta("estado_matricula", matricula.estado_por_alumno(ident), fuentes=["matricula.csv"])


def _pedir_documento(codigo: str) -> Respuesta:
    consulta_estado.update(paso="documento", codigo=codigo)
    return Respuesta("verificacion", f"Para proteger tus datos necesito verificar que eres el titular de **{codigo}**. "
                                     "🔐 Escribe tu **número de documento** (el que diste al inscribirte). Solo lo "
                                     "uso para comparar y no lo guardo. (Escribe «cancelar» para salir.)")


def _flujo_estado(texto: str) -> Respuesta | None:
    """Consulta del estado de matrícula: código de alumno (o de matrícula) + documento para verificar."""
    n = v._normalizar(texto)
    cod = _CODIGO_ESTADO.search(texto)
    codigo = f"{cod.group(1).upper()}-{int(cod.group(2)):04d}" if cod else ""
    if consulta_estado:
        if n.strip(" .!") in ("cancelar", "salir", "no", "ya no"):
            consulta_estado.clear()
            return Respuesta("verificacion", "De acuerdo, cancelé la consulta. ¿En qué más te puedo ayudar?")
        if consulta_estado["paso"] == "codigo":
            if codigo:
                resto = _CODIGO_ESTADO.sub(" ", texto)
                return _verificar_estado(codigo, resto) if _DOCUMENTO.search(resto) else _pedir_documento(codigo)
        elif _DOCUMENTO.search(texto):
            return _verificar_estado(consulta_estado["codigo"], texto)
        if len(n.split()) > 3 or "?" in texto:          # cambió de tema
            consulta_estado.clear()
            return None
        return Respuesta("verificacion", "No reconocí el dato. " + (
            "Escribe tu **código de alumno** (formato ALU-0000)." if consulta_estado["paso"] == "codigo"
            else "Escribe tu **número de documento** (solo números)."))
    if acceso.puede_gestionar() or matricula.PAGO.search(texto):
        return None                                       # el personal habilitado usa la gestión de alumnos
    pide_estado = bool(_PIDE_ESTADO.search(n))
    if codigo and (pide_estado or (len(n.split()) <= 3 and codigo.startswith("ALU"))) \
            and not _DATOS_DE_ALUMNO.search(n) and not _GESTION.search(texto):
        resto = _CODIGO_ESTADO.sub(" ", texto)
        return _verificar_estado(codigo, resto) if _DOCUMENTO.search(resto) else _pedir_documento(codigo)
    if pide_estado and not codigo:
        consulta_estado.update(paso="codigo")
        return Respuesta("verificacion", "Claro. Escríbeme tu **código de alumno** (formato ALU-0000; te lo di al "
                                         "inscribirte). También sirve tu código de matrícula (MAT-0000).")
    return None


# ------------------------------------------------------------------ menús numerados
# Al comienzo (y cuando se escribe «menú») el asistente muestra opciones numeradas y SOLO acepta esos números:
# así cada camino empieza sin ambigüedades. Después de elegir, la conversación sigue normalmente.
menu: dict = {}                     # {"tipo": "rol" | "estudiante" | "personal", "opciones": [(texto, accion)]}
perfil_elegido: dict = {}           # {"rol": "estudiante"} cuando el usuario ya eligió


def _opciones(tipo: str) -> list[tuple[str, str]]:
    if tipo == "rol":
        return [("Soy **estudiante** (o quiero estudiar en el MALI)", "estudiante"),
                ("Soy **personal del MALI** (inicio de sesión)", "personal")]
    if tipo == "estudiante":
        return [("**Matricularme** en un curso", "matricular"),
                ("**Ver vacantes** y horarios", "vacantes"),
                ("**Estado de mi matrícula** (con tu código de alumno)", "estado"),
                ("**Otra consulta** sobre cursos, sedes o procedimientos", "consulta")]
    ops = []
    if acceso.autorizar("gestion"):
        ops += [("**Pagos por confirmar**", "pagos"), ("**Consultar un alumno** por su código", "alumno"),
                ("**Resumen de matrícula**", "resumen"), ("**Alumnos con asistencia baja**", "asistencia")]
    if acceso.autorizar("vacantes"):
        ops.append(("**Ver vacantes** y horarios", "vacantes"))
    if acceso.autorizar("registro"):
        ops.append(("**Registro de consultas** (auditoría)", "registro"))
    if acceso.autorizar("administracion"):
        ops.append(("**Permisos de los usuarios**", "permisos"))
    ops += [("**Otra consulta** sobre cursos, sedes o procedimientos", "consulta"), ("**Cerrar sesión**", "cerrar")]
    return ops


def abrir_menu(tipo: str) -> str:
    ops = _opciones(tipo)
    menu.clear()
    menu.update(tipo=tipo, opciones=ops)
    titulo = {"rol": "Para atenderte mejor, **¿quién eres?**",
              "estudiante": "¿Qué necesitas?",
              "personal": "¿Qué deseas hacer?"}[tipo]
    lineas = [titulo] + [f"{i}. {texto}" for i, (texto, _) in enumerate(ops, 1)]
    lineas.append(f"\nResponde **solo con el número** (1–{len(ops)}).")
    if tipo == "personal" and acceso.autorizar("administracion"):
        lineas.append("También puedes escribir «aprobar pago MAT-0005», «rechazar pago MAT-0005» o "
                      "«actualiza vacantes H16 a 5».")
    elif tipo == "personal" and acceso.autorizar("gestion"):
        lineas.append("Para resolver un pago escribe «aprobar pago MAT-0005» o «rechazar pago MAT-0005».")
    return "\n".join(lineas)


def _pide_menu(n: str) -> bool:
    return n in ("menu", "menu principal", "volver al menu", "ver menu", "opciones", "ver opciones", "inicio", "0")


def _menu_actual() -> str:
    if acceso.autenticado():
        return abrir_menu("personal")
    return abrir_menu("estudiante" if perfil_elegido.get("rol") == "estudiante" else "rol")


def _elegir_opcion(texto: str) -> Respuesta:
    """Con un menú abierto solo se aceptan sus números."""
    n = v._normalizar(texto).strip(" .!)-")
    ops = menu["opciones"]
    m = re.fullmatch(r"(opcion\s*)?(\d{1,2})", n)
    if not m or not 1 <= int(m.group(2)) <= len(ops):
        tipo = menu["tipo"]
        return Respuesta("menu", f"No es una opción válida. 🙂 {abrir_menu(tipo)}")
    accion = ops[int(m.group(2)) - 1][1]
    menu.clear()
    return _ejecutar(accion)


def _ejecutar(accion: str) -> Respuesta:
    if accion == "estudiante":
        if acceso.autenticado():
            acceso.cerrar_sesion()
        perfil_elegido.update(rol="estudiante")
        return Respuesta("perfil", "Perfecto, te atiendo como **estudiante** (no necesitas iniciar sesión).\n\n"
                         + abrir_menu("estudiante"))
    if accion == "personal":
        perfil_elegido.update(rol="personal")
        acceso.pendiente.clear()
        acceso.pendiente.update(esperando_usuario=True)
        return Respuesta("perfil", "Para el personal del MALI necesito verificar tu perfil. 🔐 Escribe tu **usuario** "
                                   "(por ejemplo, coord01).")
    pie = "\n\n_Escribe «menú» para volver a las opciones._"
    if accion == "matricular":
        r = _decidir("quiero inscribirme en un curso")
    elif accion == "vacantes":
        r = _decidir("¿qué vacantes hay disponibles?")
    elif accion == "estado":
        r = _decidir("quiero ver el estado de mi matrícula")
    elif accion == "consulta":
        return Respuesta("menu", "Claro, escríbeme tu pregunta sobre cursos, talleres, sedes, procedimientos o "
                                 "canales de atención. Te responderé con la fuente." + pie)
    elif accion == "pagos":
        acceso.registrar("revision_pagos", "matricula.csv", "permitido")
        r = Respuesta("administracion", matricula.pagos_por_confirmar(), fuentes=["matricula.csv"])
    elif accion == "alumno":
        return Respuesta("menu", "Escribe el **código del alumno** (por ejemplo «alumno ALU-0007»)." + pie)
    elif accion == "resumen":
        r = _decidir("¿cuántos alumnos matriculados hay?")
    elif accion == "asistencia":
        r = _decidir("alumnos con asistencia baja")
    elif accion == "registro":
        r = _decidir("ver registro de consultas")
    elif accion == "permisos":
        r = _decidir("ver permisos")
    elif accion == "cerrar":
        perfil_elegido.clear()
        return Respuesta("sesion", acceso.cerrar_sesion() + "\n\n" + abrir_menu("rol"))
    else:
        return Respuesta("menu", _menu_actual())
    r.texto = (r.texto or "") + pie if r.texto else r.texto
    return r


def _respuesta_login(texto: str) -> Respuesta:
    if acceso.autenticado() and texto.startswith("✅"):
        texto = texto.replace("\n¿En qué te puedo ayudar?", "") + "\n\n" + abrir_menu("personal")
    return Respuesta("sesion", texto, fuentes=["usuarios.csv"])


# ------------------------------------------------------------------ orquestación
def _decidir(pregunta: str) -> Respuesta:
    texto = pregunta.strip()
    if acceso.pendiente.get("usuario"):  # el mensaje es la contraseña del usuario que inició sesión
        usuario = acceso.pendiente["usuario"]
        if v._normalizar(texto).strip() in ("cancelar", "salir"):
            acceso.pendiente.clear()
            return Respuesta("sesion", "Inicio de sesión cancelado.")
        registrar_mensaje_sensible(texto)
        return _respuesta_login(acceso.iniciar_sesion(usuario, texto))
    n0 = v._normalizar(texto).strip(" !.")
    if acceso.pendiente.get("esperando_usuario"):        # personal: el mensaje es su usuario
        acceso.pendiente.clear()
        if n0 in ("cancelar", "salir", "estudiante", "soy estudiante"):
            return Respuesta("perfil", "De acuerdo, te atiendo como **estudiante**. ¿En qué te puedo ayudar?")
        return Respuesta("sesion", acceso.iniciar_sesion(texto.split()[0]), fuentes=["usuarios.csv"])
    if menu:                              # menú abierto: solo números
        return _elegir_opcion(texto)
    if _pide_menu(n0):                   # «menú» deja cualquier paso (una pre-inscripción ya registrada se conserva)
        consulta_estado.clear()
        matricula.reiniciar()
        return Respuesta("menu", _menu_actual())
    if _responde_rol(texto, _PALABRAS_ESTUDIANTE):
        consulta_estado.clear()
        return _ejecutar("estudiante")
    if _responde_rol(texto, _PALABRAS_PERSONAL):
        if acceso.autenticado():
            return Respuesta("perfil", acceso.describir_sesion())
        acceso.pendiente.update(esperando_usuario=True)
        return Respuesta("perfil", "Para el personal del MALI necesito verificar tu perfil. 🔐 Escribe tu **usuario** "
                                   "(por ejemplo, coord01).")
    if es_login(texto):                  # antes de los filtros: la contraseña no es un dato a descartar
        registrar_mensaje_sensible(texto)
        return _respuesta_login(_comando_sesion(texto))
    if es_inyeccion(texto):
        acceso.registrar("intento_inyeccion", "-", "bloqueado")
        return Respuesta("inyeccion", "No puedo compartir mis instrucciones internas, cambiar mis reglas ni mostrar "
                                      "fuentes restringidas. Con gusto te ayudo con cursos, procedimientos, vacantes "
                                      "o pre-inscripción.")

    r = _flujo_estado(texto)         # antes del filtro: aquí el documento sí se pide (solo para verificar)
    if r:
        return r

    limpio, sensibles = _datos_sensibles(texto)
    if matricula.estado.get("paso") == "datos":   # al inscribirse sí se pide el documento (solo lo ve el personal)
        sensibles = [x for x in sensibles if x != "DNI"]
        limpio = texto if not sensibles else limpio
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

    m = re.search(r"\b(aprob|rechaz)\w*\s+(el\s+)?pago\s+(de\s+)?(la\s+)?(inscripcion\s+|matricula\s+)?mat[-\s]?(\d{1,4})\b", norm0)
    revisar = re.search(r"pagos?\s+(por|pendientes?\s+de)\s+(confirmar|validar|aprobar|revision)|"
                        r"(confirmar|validar|aprobar|revisar)\s+(los\s+)?pagos", norm0)
    if m or revisar:
        if not acceso.autorizar("gestion"):
            return _denegado("revision_pagos", "revisar o aprobar pagos (solo personal del MALI habilitado y la "
                                               "Coordinación Académica)")
        acceso.registrar("revision_pagos", "matricula.csv", "permitido")
        if m:
            codigo = "MAT-{:04d}".format(int(m.group(6)))
            r = matricula.resolver_pago(codigo, m.group(1) == "aprob", acceso.sesion["usuario"])
        else:
            r = matricula.pagos_por_confirmar()
        return Respuesta("administracion", r, fuentes=["matricula.csv"])

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

    if acceso.ID_ALUMNO.search(texto) or _GESTION.search(texto) or _GESTION_LIBRE.search(v._normalizar(texto)):
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
