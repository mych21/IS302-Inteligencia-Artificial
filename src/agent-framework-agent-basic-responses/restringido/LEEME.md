# Base restringida (gestión de alumnos)

- `alumnos_sinteticos.csv`: 200 registros **sintéticos** (no son alumnos reales del MALI), generados con
  `generar_alumnos_sinteticos.py` (semilla 42). Solo contienen un identificador interno (ALU-0001…) y los campos
  necesarios para gestión: programa, curso, sede, periodo, estado de matrícula, asistencia, inasistencias, cursos
  inscritos y situación administrativa. No hay nombres, DNI, teléfonos ni correos (minimización).
- `usuarios.csv`: cuentas del **personal** (Personal, Coordinación Académica, Soporte TI) con la contraseña cifrada
  (PBKDF2-SHA256 con sal; nunca en texto plano). Contraseña de prueba: `12345`. Los estudiantes no tienen cuenta:
  usan el asistente sin iniciar sesión. La Coordinación Académica decide quién tiene `gestion_alumnos=si`.
  En producción esto lo resolvería la cuenta institucional (p. ej. Microsoft Entra ID) y los permisos de SharePoint.

Estos datos **nunca se envían al modelo de lenguaje**: el sistema arma la respuesta directamente y la registra en
`registros/consultas.csv`.
