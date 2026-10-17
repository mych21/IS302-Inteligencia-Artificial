"""Servidor MCP restringido de MALI Asistente (transporte stdio).

Administra los archivos con datos personales: cuentas del personal, padrón de alumnos, registro de matrícula,
pagos y auditoría. Solo lo usa el orquestador (cliente_mcp.py), y sus respuestas se muestran al usuario sin pasar
por el modelo de lenguaje. Las operaciones del personal reciben el usuario que las pide y verifican su permiso.

Inspeccionarlo:  npx @modelcontextprotocol/inspector python servidor_restringido.py
"""
import json

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:                                   # versión 2 de la librería mcp
    from mcp.server.mcpserver import MCPServer as FastMCP

import datos_restringidos as dr

mcp = FastMCP("mali-restringido", instructions="Datos restringidos de MALI Educación (solo para el orquestador).")


# ------------------------------------------------------------------ cuentas, permisos y auditoría
@mcp.tool()
def buscar_cuenta(usuario: str) -> str:
    """Indica si existe una cuenta del personal (sin devolver su contraseña)."""
    c = dr.cuenta(usuario)
    return json.dumps({"usuario": c["usuario"], "perfil": c["perfil"]} if c else {}, ensure_ascii=False)


@mcp.tool()
def verificar_credenciales(usuario: str, clave: str) -> str:
    """Compara la contraseña con su versión cifrada (PBKDF2). Devuelve el usuario y su perfil, o {} si no coincide."""
    return json.dumps(dr.verificar_credenciales(usuario, clave) or {}, ensure_ascii=False)


@mcp.tool()
def permisos(usuario: str) -> str:
    """Perfil del usuario y si está habilitado para la gestión de alumnos."""
    return json.dumps({"perfil": dr.perfil(usuario), "gestion": dr.puede_gestionar(usuario)}, ensure_ascii=False)


@mcp.tool()
def cambiar_habilitacion(solicitante: str, usuario: str, habilitar: bool) -> str:
    """La Coordinación Académica habilita o retira el acceso de una cuenta Personal a la gestión de alumnos."""
    return dr.cambiar_habilitacion(solicitante, usuario, habilitar)


@mcp.tool()
def registrar_consulta(usuario: str, tipo: str, fuente: str, resultado: str) -> str:
    """Agrega una fila al registro de auditoría (sin el texto de la conversación)."""
    dr.registrar(usuario, tipo, fuente, resultado)
    return "OK"


@mcp.tool()
def ver_registro(solicitante: str) -> str:
    """Últimas consultas del registro de auditoría (Coordinación Académica y Soporte TI)."""
    return dr.ver_registro(solicitante)


@mcp.tool()
def ver_permisos(solicitante: str) -> str:
    """Quién tiene acceso a la gestión de alumnos (Coordinación Académica)."""
    return dr.ver_permisos(solicitante)


@mcp.tool()
def actualizar_vacantes(solicitante: str, codigo_horario: str, cantidad: int) -> str:
    """Corrige las vacantes disponibles de un horario (Coordinación Académica)."""
    return dr.actualizar_vacantes(solicitante, codigo_horario, cantidad)


# ------------------------------------------------------------------ matrícula y pagos (estudiante)
@mcp.tool()
def registrar_matricula(codigo_horario: str, nombre: str, correo: str, numero_documento: str = "",
                        telefono: str = "") -> str:
    """Descuenta una vacante y registra la pre-inscripción. Devuelve «OK MAT-…: resumen» o «ERROR: …»."""
    return dr.registrar_matricula(codigo_horario, nombre, correo, numero_documento, telefono)


@mcp.tool()
def codigo_de_alumno(codigo_matricula: str) -> str:
    """Código de alumno (ALU-…) asociado a una matrícula."""
    return dr.id_alumno_de_matricula(codigo_matricula)


@mcp.tool()
def registrar_pago(codigo_matricula: str, codigo_pago: str) -> str:
    """Registra el código de pago: «OK» (conciliado), «POR_CONFIRMAR» (lo revisa el personal) o «ERROR: …»."""
    return dr.registrar_pago(codigo_matricula, codigo_pago)


@mcp.tool()
def ficha_inscripcion(codigo_matricula: str, mostrar_nombre: bool = True, por_confirmar: bool = False) -> str:
    """Resumen final de la inscripción con el horario y recordatorios de la base general."""
    return dr.ficha_inscripcion(codigo_matricula, mostrar_nombre, por_confirmar)


@mcp.tool()
def verificar_alumno(codigo: str, documento: str) -> str:
    """Código de alumno si el documento coincide con su registro; si no, cadena vacía."""
    return dr.verificar_alumno(codigo, documento)


@mcp.tool()
def estado_matricula(id_alumno: str) -> str:
    """Estado de las matrículas de un alumno ya verificado, sin documento, teléfono ni correo."""
    return dr.estado_por_alumno(id_alumno)


# ------------------------------------------------------------------ gestión (personal autorizado)
@mcp.tool()
def consultar_gestion(solicitante: str, consulta: str) -> str:
    """Ficha de un alumno, resumen de matrícula, asistencia baja o pagos pendientes, según la consulta."""
    return dr.consultar_gestion(solicitante, consulta)


@mcp.tool()
def pagos_por_confirmar(solicitante: str) -> str:
    """Pre-inscripciones con un código de pago no conciliado que espera la revisión del personal."""
    return dr.pagos_por_confirmar(solicitante)


@mcp.tool()
def resolver_pago(solicitante: str, codigo_matricula: str, aprobar: bool) -> str:
    """Aprueba (Matriculado) o rechaza (vuelve a pendiente de pago) un pago por confirmar."""
    return dr.resolver_pago(solicitante, codigo_matricula, aprobar)


if __name__ == "__main__":
    mcp.run()
