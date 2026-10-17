"""Servidor MCP general de MALI Asistente (transporte stdio).

Expone la información pública: la base de conocimiento general (RAG) y el archivo de vacantes de demostración.
No tiene acceso a datos de alumnos.

Inspeccionarlo:  npx @modelcontextprotocol/inspector python servidor_general.py
"""
import json

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:                                   # versión 2 de la librería mcp
    from mcp.server.mcpserver import MCPServer as FastMCP

import conocimiento
import vacantes

mcp = FastMCP("mali-general", instructions="Base de conocimiento general de MALI Educación y vacantes de demostración.")


@mcp.tool()
def buscar_informacion(consulta: str) -> str:
    """Busca en la base de conocimiento general (cursos, talleres, sedes, modalidad virtual, inasistencias, pagos y
    devoluciones, edad mínima, ingreso a clases, datos personales, canales, reclamos). Devuelve en JSON los
    fragmentos relevantes con su fuente, o una lista vacía si no hay información suficiente."""
    resultados = conocimiento.buscar(consulta) or []
    return json.dumps([{"id": d.id, "titulo": d.titulo, "fuente": d.fuente, "texto": d.texto, "puntaje": round(p, 3)}
                       for d, p in resultados], ensure_ascii=False)


@mcp.tool()
def documento_de_curso(curso: str) -> str:
    """Documento de la base general que menciona un curso (para indicar a qué oferta pertenece), en JSON."""
    d = conocimiento.documento_que_menciona(curso)
    return json.dumps({"id": d.id, "titulo": d.titulo, "fuente": d.fuente} if d else {}, ensure_ascii=False)


@mcp.tool()
def listar_horarios() -> str:
    """Todos los horarios del archivo de vacantes (código, curso, categoría, sede, modalidad, público, horario,
    fechas de inicio y fin, periodo y vacantes disponibles), en JSON."""
    return json.dumps(vacantes.horarios(), ensure_ascii=False)


@mcp.tool()
def consultar_vacantes(consulta: str) -> str:
    """Vacantes disponibles según una pregunta libre («vacantes de guitarra en verano»), agrupadas por curso."""
    return vacantes.vacantes_para_usuario(consulta)


if __name__ == "__main__":
    mcp.run()
