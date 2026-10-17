"""
Administra las cuentas del personal en restringido/usuarios.csv (las contraseñas se guardan cifradas).

Uso:
    python restringido/gestionar_usuarios.py crear-iniciales          # crea las cuentas de prueba con clave 12345
    python restringido/gestionar_usuarios.py clave <usuario> <nueva>   # cambia la contraseña de una cuenta
    python restringido/gestionar_usuarios.py agregar <usuario> <perfil> <clave> [descripcion]
        perfiles: "Personal", "Coordinación Académica", "Soporte TI"
    python restringido/gestionar_usuarios.py listar

Los estudiantes no tienen cuenta: usan el asistente sin iniciar sesión.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acceso  # noqa: E402

INICIALES = [
    ("docente01", "Personal", "no", "", "Docente sin acceso a gestión de alumnos"),
    ("docente02", "Personal", "si", "coord01", "Docente habilitado por la Coordinación Académica"),
    ("coord01", "Coordinación Académica", "si", "", "Coordinación Académica (administra la gestión de alumnos)"),
    ("soporte01", "Soporte TI", "no", "", "Soporte técnico: configura el asistente pero no consulta datos de alumnos"),
]
CLAVE_INICIAL = "12345"


def _fila(usuario, perfil, gestion, habilitado_por, descripcion, clave):
    sal, h = acceso.nueva_clave(clave)
    return {"usuario": usuario, "perfil": perfil, "sal": sal, "clave_hash": h, "gestion_alumnos": gestion,
            "habilitado_por": habilitado_por, "descripcion": descripcion}


def main(args):
    if not args or args[0] == "listar":
        for u in acceso._leer_usuarios():
            print(f"{u['usuario']:12} {u['perfil']:24} gestión de alumnos: {u['gestion_alumnos']}")
    elif args[0] == "crear-iniciales":
        acceso._guardar_usuarios([_fila(*u, CLAVE_INICIAL) for u in INICIALES])
        print(f"{len(INICIALES)} cuentas creadas en {acceso.USUARIOS} (contraseña: {CLAVE_INICIAL})")
    elif args[0] == "clave" and len(args) == 3:
        filas = acceso._leer_usuarios()
        u = next(f for f in filas if f["usuario"] == args[1])
        u["sal"], u["clave_hash"] = acceso.nueva_clave(args[2])
        acceso._guardar_usuarios(filas)
        print(f"Contraseña de {args[1]} actualizada.")
    elif args[0] == "agregar" and len(args) >= 4:
        if args[2] not in ("Personal", "Coordinación Académica", "Soporte TI"):
            sys.exit("Perfil no válido (los estudiantes no tienen cuenta).")
        filas = acceso._leer_usuarios()
        filas.append(_fila(args[1], args[2], "no", "", args[4] if len(args) > 4 else "", args[3]))
        acceso._guardar_usuarios(filas)
        print(f"Cuenta {args[1]} creada.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
