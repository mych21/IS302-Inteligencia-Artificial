"""Copia de los datos para las pruebas y la evaluación: los servidores MCP trabajan sobre ella (variable MALI_DATOS),
así los archivos reales del proyecto no cambian."""
import csv
import os
import shutil
import sys
import tempfile
from pathlib import Path

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO))
import cliente_mcp  # noqa: E402
import datos_restringidos as dr  # noqa: E402

_copia: Path | None = None


def _filtrar(ruta: Path, campos: list[str], conservar) -> None:
    with open(ruta, encoding="utf-8") as f:
        filas = [x for x in csv.DictReader(f) if conservar(x)]
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(filas)


def preparar() -> Path:
    """Deja la copia en su estado inicial: datos sintéticos sin las inscripciones hechas al usar el asistente y
    códigos de pago de demostración disponibles. La primera vez crea la copia y reinicia los servidores MCP."""
    global _copia
    if _copia is None:
        _copia = Path(tempfile.mkdtemp(prefix="mali_"))
        os.environ["MALI_DATOS"] = str(_copia)
        cliente_mcp.cerrar()
    for carpeta in ("conocimiento", "datos", "restringido"):
        shutil.rmtree(_copia / carpeta, ignore_errors=True)
        shutil.copytree(PROYECTO / carpeta, _copia / carpeta, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    shutil.rmtree(_copia / "registros", ignore_errors=True)
    r = _copia / "restringido"
    _filtrar(r / "matricula.csv", dr.CAMPOS_MATRICULA, lambda x: x.get("origen") != "asistente")
    _filtrar(r / "alumnos_sinteticos.csv", dr.CAMPOS_ALUMNOS, lambda x: int(x["id_alumno"][4:]) <= 200)
    with open(_copia / "datos" / "pagos_demo.csv", encoding="utf-8") as f:
        pagos = [{"codigo_pago": p["codigo_pago"], "estado": "disponible"} for p in csv.DictReader(f)]
    with open(_copia / "datos" / "pagos_demo.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=dr.CAMPOS_PAGOS, restval="")
        w.writeheader()
        w.writerows(pagos)
    return _copia
