"""Ubicación de los archivos de datos. Por defecto, la carpeta del proyecto; la variable MALI_DATOS permite usar
otra carpeta con la misma estructura (las pruebas la usan para trabajar sobre una copia)."""
from __future__ import annotations

import os
from pathlib import Path

PROYECTO = Path(__file__).resolve().parent


def base() -> Path:
    return Path(os.environ.get("MALI_DATOS") or PROYECTO)


def conocimiento() -> Path:
    return base() / "conocimiento" / "general"


def vacantes() -> Path:
    return base() / "datos" / "vacantes.csv"


def pagos() -> Path:
    return base() / "datos" / "pagos_demo.csv"


def usuarios() -> Path:
    return base() / "restringido" / "usuarios.csv"


def alumnos() -> Path:
    return base() / "restringido" / "alumnos_sinteticos.csv"


def matriculas() -> Path:
    return base() / "restringido" / "matricula.csv"


def registro() -> Path:
    return base() / "registros" / "consultas.csv"
