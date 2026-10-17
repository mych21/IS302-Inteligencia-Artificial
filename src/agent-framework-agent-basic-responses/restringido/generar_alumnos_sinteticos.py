"""Genera 200 registros SINTÉTICOS de alumnos para la base restringida (no son datos reales del MALI).

Minimización: solo identificador interno y campos necesarios para gestión; sin nombres, DNI, teléfonos ni correos.
Uso: python restringido/generar_alumnos_sinteticos.py
"""
import csv
import random
from pathlib import Path

CURSOS = [("Dibujo y Pintura", "Curso"), ("Pintura al Óleo", "Curso"), ("Ballet", "Taller"), ("Kpop", "Taller"),
          ("Marinera Norteña", "Taller"), ("Teatro y Actuación", "Curso"), ("Fotografía digital", "Curso"),
          ("Guitarra", "Curso"), ("Violín", "Curso"), ("Taekwondo", "Taller"), ("Oratoria y Liderazgo", "Curso"),
          ("Gestión Cultural", "Diplomado"), ("Museografía y Diseño de Exhibiciones", "Diplomado")]
SEDES = ["Lima – Principal", "Chorrillos – Faisanes", "La Molina – Camacho", "Los Olivos – Villa Sol",
         "San Miguel 1", "SJL – Arabiscos", "Virtual"]
PERIODOS = ["Setiembre 2026", "Octubre 2026"]


def generar(n: int = 200, semilla: int = 42) -> list[dict]:
    rnd = random.Random(semilla)
    filas = []
    for i in range(1, n + 1):
        curso, programa = rnd.choice(CURSOS)
        asistencia = round(min(100, max(20, rnd.gauss(80, 14))), 1)
        sesiones = 8
        inasistencias = round(sesiones * (100 - asistencia) / 100)
        estado = rnd.choices(["Activa", "Pendiente de pago", "Retirada"], [0.82, 0.12, 0.06])[0]
        situacion = {"Activa": rnd.choices(["Al día", "Incidencia de pago"], [0.9, 0.1])[0],
                     "Pendiente de pago": "Pago pendiente", "Retirada": "Sin deuda"}[estado]
        filas.append({
            "id_alumno": f"ALU-{i:04d}", "programa": programa, "curso": curso,
            "sede": "Virtual" if programa == "Diplomado" and rnd.random() < 0.6 else rnd.choice(SEDES),
            "periodo": rnd.choice(PERIODOS), "estado_matricula": estado,
            "porcentaje_asistencia": asistencia, "inasistencias": inasistencias,
            "cursos_inscritos": rnd.choices([1, 2, 3], [0.7, 0.24, 0.06])[0],
            "situacion_administrativa": situacion, "actualizado_al": "15/10/2026",
        })
    return filas


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent / "alumnos_sinteticos.csv"
    filas = generar()
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"{len(filas)} registros sintéticos en {destino}")
