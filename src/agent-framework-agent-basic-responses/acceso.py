"""
Sesión y permisos del usuario que conversa con MALI Asistente.

- Los estudiantes usan el asistente sin iniciar sesión (perfil público «Estudiante»): base general, vacantes,
  inscripción y estado de su matrícula.
- El personal (Personal, Coordinación Académica y Soporte TI) inicia sesión con usuario y contraseña. Las cuentas
  están en restringido/usuarios.csv con la contraseña cifrada (PBKDF2 con sal) y se consultan a través del servidor
  MCP restringido. En producción: cuenta institucional (p. ej. Microsoft Entra ID).
- Antes de cada consulta se verifica el perfil y sus permisos; el servidor restringido vuelve a verificarlos.
- Cada consulta queda en registros/consultas.csv con fecha, usuario, perfil, tipo, fuente y resultado, sin guardar
  el texto de la conversación (tampoco contraseñas).
"""
from __future__ import annotations

import cliente_mcp
from datos_restringidos import DENEGADO, ID_ALUMNO, PERMISOS_POR_PERFIL, PUBLICO  # noqa: F401 (usados por asistente)

sesion: dict = dict(PUBLICO)
pendiente: dict = {}            # usuario que está ingresando su contraseña
DESCRIPCION_PERMISOS = {
    "Estudiante": "cursos, procedimientos, vacantes y tu pre-inscripción",
    "Personal": "información general y vacantes (gestión de alumnos solo si la Coordinación te habilita)",
    "Coordinación Académica": "información general, gestión de alumnos, permisos, vacantes y registro de consultas",
    "Soporte TI": "información general y registro de consultas (sin datos de alumnos)",
}


def _restringido(herramienta: str, **argumentos) -> str:
    return cliente_mcp.llamar("restringido", herramienta, **argumentos)


def registrar(tipo: str, fuente: str, resultado: str) -> None:
    _restringido("registrar_consulta", usuario=sesion["usuario"], tipo=tipo, fuente=fuente, resultado=resultado)


# ------------------------------------------------------------------ sesión
def iniciar_sesion(usuario: str, clave: str | None = None) -> str:
    """Inicio de sesión del personal. Sin contraseña, la pide en el siguiente mensaje."""
    cuenta = cliente_mcp.llamar_json("restringido", "buscar_cuenta", usuario=usuario)
    if not cuenta:
        pendiente.clear()
        registrar("inicio_sesion", "usuarios.csv", "denegado")
        return ("No existe esa cuenta de personal. Si eres estudiante no necesitas iniciar sesión: pregúntame "
                "directamente por cursos, vacantes o tu pre-inscripción.")
    if clave is None:
        pendiente.update(usuario=cuenta["usuario"])
        return f"🔐 Ingresa la contraseña de **{cuenta['usuario']}** (escribe «cancelar» para salir)."
    pendiente.clear()
    verificada = cliente_mcp.llamar_json("restringido", "verificar_credenciales", usuario=cuenta["usuario"], clave=clave)
    if not verificada:
        registrar("inicio_sesion", "usuarios.csv", "denegado")
        return "Usuario o contraseña incorrectos."
    sesion.update(usuario=verificada["usuario"], perfil=verificada["perfil"])
    registrar("inicio_sesion", "usuarios.csv", "permitido")
    return (f"✅ Sesión iniciada como **{sesion['usuario']}** (perfil: {sesion['perfil']}).\n"
            f"Con este perfil puedes consultar: {DESCRIPCION_PERMISOS.get(sesion['perfil'], 'información general')}.")


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


def puede_gestionar() -> bool:
    return autenticado() and cliente_mcp.llamar_json("restringido", "permisos", usuario=sesion["usuario"])["gestion"]


def autorizar(tipo: str) -> bool:
    """Verifica, antes de cada consulta, si el perfil de la sesión puede hacer ese tipo de consulta."""
    permitido = tipo in PERMISOS_POR_PERFIL.get(sesion["perfil"], set())
    return permitido and (tipo != "gestion" or puede_gestionar())


def describir_sesion() -> str:
    if not autenticado():
        return "Estás usando el asistente como estudiante (no necesitas iniciar sesión)."
    return (f"Estás como **{sesion['usuario']}** (perfil: {sesion['perfil']}). Puedes consultar: "
            f"{DESCRIPCION_PERMISOS.get(sesion['perfil'], 'información general')}. Gestión de alumnos: "
            + ("habilitada (también puedes revisar los «pagos por confirmar» y aprobarlos o rechazarlos)."
               if puede_gestionar() else "no habilitada."))


# ------------------------------------------------------------------ operaciones del personal (servidor restringido)
def cambiar_habilitacion(usuario: str, habilitar: bool) -> str:
    return _restringido("cambiar_habilitacion", solicitante=sesion["usuario"], usuario=usuario, habilitar=habilitar)


def consultar_gestion(consulta: str) -> str:
    return _restringido("consultar_gestion", solicitante=sesion["usuario"], consulta=consulta)


def ver_registro() -> str:
    return _restringido("ver_registro", solicitante=sesion["usuario"])


def ver_permisos() -> str:
    return _restringido("ver_permisos", solicitante=sesion["usuario"])


def actualizar_vacantes(codigo_horario: str, cantidad: int) -> str:
    return _restringido("actualizar_vacantes", solicitante=sesion["usuario"], codigo_horario=codigo_horario,
                        cantidad=cantidad)


def pagos_por_confirmar() -> str:
    return _restringido("pagos_por_confirmar", solicitante=sesion["usuario"])


def resolver_pago(codigo_matricula: str, aprobar: bool) -> str:
    return _restringido("resolver_pago", solicitante=sesion["usuario"], codigo_matricula=codigo_matricula,
                        aprobar=aprobar)
