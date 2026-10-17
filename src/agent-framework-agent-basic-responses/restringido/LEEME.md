# Base restringida (gestión de alumnos)

- `alumnos_sinteticos.csv`: padrón de alumnos. 200 registros **sintéticos** (no son alumnos reales del MALI),
  generados con `generar_alumnos_sinteticos.py`, más los alumnos que se inscriben por el asistente (ALU-0201…).
  Campos: código de alumno, nombre, número de documento, teléfono, correo, programa, curso, sede, periodo, estado de
  matrícula, asistencia, inasistencias, cursos inscritos y situación administrativa. Los datos personales de los
  sintéticos son ficticios (documentos que empiezan con 99, teléfonos 900 000 xxx y correos @example.com).
  El código de alumno es el mismo en el padrón y en `matricula.csv`.
- `matricula.csv`: registro de **todos los alumnos matriculados**: código de matrícula, código de alumno (ALU-…),
  nombre, número de documento, teléfono, correo, curso, sede, horario, periodo, fechas, estado (Matriculado, Pendiente de pago, Pre-inscrito, Retirado) y código de
  pago. Contiene 200 matrículas sintéticas (MAT-S0001…, generadas con `generar_matricula.py`) y las inscripciones
  hechas en el asistente (MAT-0001…, con los datos que el alumno ingresa al inscribirse). Solo lo consultan la Coordinación y el personal
  habilitado («¿cuántos alumnos están matriculados?», «alumnos matriculados en guitarra», «ALU-0201»).
- `usuarios.csv`: cuentas del **personal** (Personal, Coordinación Académica, Soporte TI) con la contraseña cifrada
  (PBKDF2-SHA256 con sal; nunca en texto plano). Contraseña de prueba: `12345`. Los estudiantes no tienen cuenta:
  usan el asistente sin iniciar sesión. La Coordinación Académica decide quién tiene `gestion_alumnos=si`.
  En producción esto lo resolvería la cuenta institucional (p. ej. Microsoft Entra ID) y los permisos de SharePoint.

Estos datos **nunca se envían al modelo de lenguaje**: el sistema arma la respuesta directamente y la registra en
`registros/consultas.csv`.
