"""
Servidor MCP local del MALI (transporte stdio).

Expone las herramientas de mali_tools.py mediante el Model Context Protocol para que cualquier agente
compatible (Microsoft Agent Framework, Claude, VS Code, etc.) pueda usarlas.

Probarlo solo:   python mali_mcp_server.py        (queda esperando mensajes MCP por stdin)
Inspeccionarlo:  npx @modelcontextprotocol/inspector python mali_mcp_server.py
"""
from mcp.server.fastmcp import FastMCP

import mali_tools

mcp = FastMCP(
    "mali-educacion",
    instructions="Herramientas con información oficial de MALI Educación y señal de acompañamiento interna.",
)


@mcp.tool()
def buscar_informacion_mali(consulta: str) -> str:
    """Busca en la información oficial de MALI Educación (cursos, sedes, clases virtuales, inasistencias,
    pagos y devoluciones, edad mínima, ingreso a clases, datos personales, reclamos, vacantes) y devuelve los fragmentos
    más relevantes con su fuente. Úsala para cualquier pregunta sobre MALI Educación."""
    return mali_tools.buscar_informacion_mali(consulta)


@mcp.tool()
def listar_oferta(categoria: str = "") -> str:
    """Lista los cursos y programas publicados. categoria puede ser: artes plásticas, artes vocales, bailes,
    artes escénicas, artes gráficas, artes marciales, música o extensión profesional. Vacío = todas."""
    return mali_tools.listar_oferta(categoria)


@mcp.tool()
def canales_de_atencion() -> str:
    """Devuelve los correos y enlaces oficiales de atención de MALI Educación."""
    return mali_tools.canales_de_atencion()


@mcp.tool()
def consultar_vacantes(curso: str = "", sede: str = "", periodo: str = "", modalidad: str = "",
                       consulta: str = "") -> str:
    """Vacantes disponibles de los cursos (archivo local datos/vacantes.csv): curso, sede, horario, fecha de inicio
    y cuántas vacantes quedan. Úsala SIEMPRE que pregunten por vacantes, cupos o disponibilidad. Puedes pasar
    filtros (curso: "Guitarra"; sede: "San Miguel"; periodo: "verano" o "noviembre"; modalidad: "virtual")
    o, más fácil, la pregunta completa del usuario en consulta. Sin parámetros = todas las vacantes."""
    return mali_tools.consultar_vacantes(curso=curso, sede=sede, periodo=periodo, modalidad=modalidad,
                                         consulta=consulta)


@mcp.tool()
def senal_de_apoyo(porcentaje_asistencia: float, promedio_evaluaciones: float, pagos_atrasados: int = 0,
                   continuidad_previa: int = 0, porcentaje_cursos_completados: float = 60.0,
                   numero_cursos_previos: int = 1, tipo_programa: str = "Curso") -> str:
    """SOLO para personal de coordinación académica. Estima una señal de acompañamiento (Bajo/Medio/Alto)
    de un alumno con el modelo predictivo del proyecto. promedio_evaluaciones va de 0 a 20; continuidad_previa
    es 1 o 0; tipo_programa: Curso, Taller o Diplomado. El resultado requiere revisión humana y no se comunica
    al estudiante."""
    return mali_tools.senal_de_apoyo(
        porcentaje_asistencia=porcentaje_asistencia, promedio_evaluaciones=promedio_evaluaciones,
        pagos_atrasados=pagos_atrasados, continuidad_previa=continuidad_previa,
        porcentaje_cursos_completados=porcentaje_cursos_completados,
        numero_cursos_previos=numero_cursos_previos, tipo_programa=tipo_programa)


if __name__ == "__main__":
    mcp.run()   # stdio
