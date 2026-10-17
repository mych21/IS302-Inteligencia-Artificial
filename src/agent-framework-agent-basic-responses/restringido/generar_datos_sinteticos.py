"""Genera los datos SINTÉTICOS de la base restringida (no son datos reales del MALI).

- restringido/alumnos_sinteticos.csv: 200 alumnos con datos personales FICTICIOS: nombre, número de documento (empieza
  con 99, un rango que no corresponde a DNI emitidos), teléfono (900 000 xxx) y correo @example.com (dominio
  reservado). La semilla es fija, así que el resultado siempre es el mismo.
- restringido/matricula.csv: una matrícula por alumno sintético (MAT-S0001…).
Los alumnos y matrículas creados por el asistente (ALU-0201…, MAT-0001…) se conservan.
Uso: python restringido/generar_datos_sinteticos.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import datos_restringidos as dr  # noqa: E402
import rutas  # noqa: E402

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


def _sin_tildes(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def datos_personales(n: int, semilla: int = 7) -> list[tuple[str, str, str, str]]:
    """Nombres y correos ficticios (en un generador aparte para no alterar el resto de los datos)."""
    rnd, usados, salida = random.Random(semilla), set(), []
    for i in range(1, n + 1):
        nombre = f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}"
        base = _sin_tildes(nombre.lower()).split()
        correo = f"{base[0]}.{base[1]}{i:03d}@example.com"
        documento = f"99{rnd.randint(0, 999999):06d}"
        telefono = f"900 000 {i:03d}"
        salida.append((nombre, correo, documento, telefono))
    return salida


def generar_alumnos(n: int = 200, semilla: int = 42) -> list[dict]:
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
    for fila, (nombre, correo, documento, telefono) in zip(filas, datos_personales(n)):
        fila.update(nombre=nombre, correo=correo, numero_documento=documento, telefono=telefono)
    return filas


FECHAS_PERIODO = {"Setiembre 2026": ("01/09/2026", "30/09/2026"), "Octubre 2026": ("01/10/2026", "31/10/2026")}
ESTADOS = {"Activa": "Matriculado", "Pendiente de pago": "Pendiente de pago", "Retirada": "Retirado"}


def generar_matriculas(alumnos: list[dict]) -> list[dict]:
    filas = []
    for n, a in enumerate(alumnos, 1):
        ini, fin = FECHAS_PERIODO.get(a["periodo"], ("", ""))
        filas.append({"codigo_matricula": f"MAT-S{n:04d}", "id_alumno": a["id_alumno"], "nombre": a["nombre"],
                      "numero_documento": a["numero_documento"], "telefono": a["telefono"], "correo": a["correo"],
                      "curso": a["curso"], "codigo_horario": "", "sede": a["sede"],
                      "modalidad": "Virtual (Zoom)" if a["sede"] == "Virtual" else "Presencial", "horario": "",
                      "periodo": a["periodo"], "fecha_inicio": ini, "fecha_fin": fin,
                      "estado": ESTADOS.get(a["estado_matricula"], a["estado_matricula"]), "codigo_pago": "",
                      "fecha_registro": a["actualizado_al"], "origen": "sistema (sintético)"})
    return filas


if __name__ == "__main__":
    alumnos = generar_alumnos()
    sinteticos = {f["id_alumno"] for f in alumnos}
    otros = [f for f in dr.alumnos() if f["id_alumno"] not in sinteticos]
    dr._guardar(rutas.alumnos(), dr.CAMPOS_ALUMNOS, alumnos + otros)
    del_asistente = [m for m in dr.matriculas() if m.get("origen") == "asistente"]
    matriculas = generar_matriculas(alumnos)
    dr._guardar(rutas.matriculas(), dr.CAMPOS_MATRICULA, matriculas + del_asistente)
    print(f"{len(alumnos)} alumnos y {len(matriculas)} matrículas sintéticas "
          f"(se conservaron {len(otros)} alumnos y {len(del_asistente)} matrículas del asistente).")
