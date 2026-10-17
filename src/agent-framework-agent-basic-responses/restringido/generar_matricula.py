"""Genera restringido/matricula.csv: el registro de TODOS los alumnos matriculados (datos sintéticos).

Parte de los 200 alumnos de alumnos_sinteticos.csv (una matrícula por alumno, código MAT-S0001…). Las inscripciones
que se completan en el asistente se agregan al mismo archivo (código MAT-0001…, origen «asistente»).
Uso: python restringido/generar_matricula.py   (sobrescribe el archivo; conserva las filas de origen «asistente»)
"""
import csv
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import matricula  # noqa: E402

PERIODOS = {"Setiembre 2026": ("01/09/2026", "30/09/2026"), "Octubre 2026": ("01/10/2026", "31/10/2026")}
ESTADOS = {"Activa": "Matriculado", "Pendiente de pago": "Pendiente de pago", "Retirada": "Retirado"}


def generar() -> list[dict]:
    alumnos = [a for a in csv.DictReader((AQUI / "alumnos_sinteticos.csv").open(encoding="utf-8"))
               if int(a["id_alumno"][4:]) <= 200]           # solo los sintéticos
    filas = []
    for n, a in enumerate(alumnos, 1):
        ini, fin = PERIODOS.get(a["periodo"], ("", ""))
        filas.append({"codigo_matricula": f"MAT-S{n:04d}", "id_alumno": a["id_alumno"], "nombre": a["nombre"],
                      "numero_documento": a["numero_documento"], "telefono": a["telefono"], "correo": a["correo"],
                      "curso": a["curso"], "codigo_horario": "", "sede": a["sede"],
                      "modalidad": "Virtual (Zoom)" if a["sede"] == "Virtual" else "Presencial", "horario": "",
                      "periodo": a["periodo"], "fecha_inicio": ini, "fecha_fin": fin,
                      "estado": ESTADOS.get(a["estado_matricula"], a["estado_matricula"]), "codigo_pago": "",
                      "fecha_registro": a["actualizado_al"], "origen": "sistema (sintético)"})
    return filas


if __name__ == "__main__":
    previas = [m for m in matricula._leer_matriculas() if m.get("origen") == "asistente"]
    # Solo se regeneran las filas sintéticas; las inscripciones del asistente se conservan.
    matricula._guardar_matriculas(generar() + previas)
    print(f"{len(generar())} matrículas sintéticas + {len(previas)} del asistente en {matricula.ARCHIVO_MATRICULAS}")
