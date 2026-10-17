"""Servidor MCP local de MALI Asistente (transporte stdio).

Expone SOLO información de nivel general: la base de conocimiento (RAG) y las vacantes de demostración.
La base restringida de alumnos y las pre-inscripciones (con nombre y correo) no se exponen al modelo.

Inspeccionarlo:  npx @modelcontextprotocol/inspector python mali_mcp_server.py
"""
from mcp.server.fastmcp import FastMCP

import conocimiento
import vacantes

mcp = FastMCP("mali-asistente",
              instructions="Base de conocimiento general de MALI Educación y vacantes de demostración.")


@mcp.tool()
def buscar_informacion_mali(consulta: str) -> str:
    """Busca en la base de conocimiento general de MALI Educación (cursos, talleres, sedes, modalidad virtual,
    inasistencias, pagos y devoluciones, edad mínima, ingreso a clases, datos personales, canales, reclamos) y
    devuelve los fragmentos relevantes con su fuente, o SIN_RESULTADOS si no hay información suficiente."""
    return conocimiento.buscar_informacion(consulta)


@mcp.tool()
def consultar_vacantes(curso: str = "", sede: str = "", periodo: str = "", modalidad: str = "",
                       consulta: str = "") -> str:
    """Vacantes de demostración (archivo vacantes.csv): curso, sede, horario, fechas de inicio y fin, y vacantes.
    Filtros opcionales o la pregunta completa en consulta."""
    return vacantes.consultar_vacantes(curso=curso, sede=sede, periodo=periodo, modalidad=modalidad,
                                       consulta=consulta)


if __name__ == "__main__":
    mcp.run()
