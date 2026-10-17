"""Genera 200 registros SINTÉTICOS de alumnos para la base restringida (no son datos reales del MALI).

Incluye datos personales FICTICIOS (nombre y correo @example.com, un dominio reservado que no pertenece a nadie)
para simular el registro real; solo los ve el personal autorizado del MALI. No incluye DNI ni datos de pago.
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
NOMBRES = ["Lucía", "Mateo", "Valeria", "Santiago", "Camila", "Diego", "Sofía", "Sebastián", "Daniela", "Andrés",
           "Fernanda", "Gabriel", "Mariana", "Nicolás", "Isabella", "Joaquín", "Renata", "Adrián", "Ximena", "Thiago",
           "Alessia", "Bruno", "Antonella", "Emilio", "Luciana", "Rodrigo", "Micaela", "Gonzalo", "Paula", "Iván"]
APELLIDOS = ["Quispe", "Flores", "Rojas", "Huamán", "Mendoza", "Torres", "Ramírez", "Castillo", "Vargas", "Chávez",
             "Salazar", "Paredes", "Gutiérrez", "Romero", "Medina", "Cárdenas", "Ríos", "Vega", "Silva", "Aguilar"]
CAMPOS = ["id_alumno", "nombre", "correo", "programa", "curso", "sede", "periodo", "estado_matricula",
          "porcentaje_asistencia", "inasistencias", "cursos_inscritos", "situacion_administrativa", "actualizado_al"]


def _sin_tildes(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def datos_personales(n: int, semilla: int = 7) -> list[tuple[str, str]]:
    """Nombres y correos ficticios (en un generador aparte para no alterar el resto de los datos)."""
    rnd, usados, salida = random.Random(semilla), set(), []
    for i in range(1, n + 1):
        nombre = f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}"
        base = _sin_tildes(nombre.lower()).split()
        correo = f"{base[0]}.{base[1]}{i:03d}@example.com"
        salida.append((nombre, correo))
    return salida


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
    for fila, (nombre, correo) in zip(filas, datos_personales(n)):
        fila.update(nombre=nombre, correo=correo)
    return filas


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent / "alumnos_sinteticos.csv"
    filas = generar()
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(filas)
    print(f"{len(filas)} registros sintéticos en {destino}")
