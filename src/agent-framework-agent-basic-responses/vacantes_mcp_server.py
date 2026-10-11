"""Servidor MCP local (stdio): vacantes (datos/vacantes.csv) y matrículas registradas (datos/matriculas.csv)."""
from mcp.server.fastmcp import FastMCP

import matricula
import vacantes

mcp = FastMCP("mali-vacantes", instructions="Vacantes y matrículas de los cursos de MALI Educación (data dummy local).")


@mcp.tool()
def consultar_vacantes(curso: str = "", sede: str = "", periodo: str = "", modalidad: str = "",
                       consulta: str = "") -> str:
    """Vacantes disponibles de los cursos: curso, sede, horario, fecha de inicio y vacantes que quedan.
    Filtros opcionales (curso: "Guitarra"; sede: "San Miguel"; periodo: "verano" o "noviembre";
    modalidad: "virtual") o la pregunta completa del usuario en consulta. Sin parámetros = todas."""
    return vacantes.consultar_vacantes(curso=curso, sede=sede, periodo=periodo, modalidad=modalidad,
                                       consulta=consulta)


@mcp.tool()
def consultar_matriculas() -> str:
    """Lista las matrículas ya registradas (código, alumno, curso, sede, horario y estado)."""
    return matricula.consultar_matriculas()


if __name__ == "__main__":
    mcp.run()
