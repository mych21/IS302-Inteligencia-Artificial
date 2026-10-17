# MALI Asistente – prototipo del trabajo final (IS302 Inteligencia Artificial, UPC 2026-2)

Chatbot con IA para orientar a la comunidad educativa del MALI y proteger sus datos. Implementa lo descrito en
el documento final: RAG sobre fuentes institucionales, perfiles con control de acceso, base restringida de gestión
de alumnos (sintética), registro de consultas, aviso de privacidad, resistencia a *prompt injection* y el banco de
pruebas de la sección 4.4.

## Arquitectura
```
Usuario ─► Agent Inspector (VS Code)
             │
             ▼
   main.py  (Microsoft Agent Framework + Foundry Local, modelo Phi-4-mini)
     └─ middleware orquestar() ─► asistente.py  (decide cada mensaje; menús, seguridad y perfiles)
            ├─ matricula.py: conversación de inscripción, pago y estado
            ├─ acceso.py: sesión y permisos del usuario
            └─ cliente_mcp.py ─┬─► servidor_general.py (MCP)     base general (RAG con BM25) y vacantes
                               └─► servidor_restringido.py (MCP) cuentas, alumnos, matrícula, pagos y auditoría
   Phi-4-mini solo redacta las respuestas de la base general, con los fragmentos recuperados y su fuente.
```
El orquestador no abre ningún archivo: todos los CSV y documentos se leen y se actualizan a través de los dos
servidores MCP. Las respuestas del servidor restringido se muestran al usuario sin pasar por el modelo, y cada
operación del personal vuelve a verificar el permiso del usuario en `usuarios.csv`.

| Archivo | Función |
|---|---|
| `main.py` | Servidor del agente (Agent Inspector), modelo local y redacción de respuestas RAG |
| `asistente.py` | Orquestador: decide cómo se atiende cada mensaje |
| `matricula.py` | Conversación de inscripción (curso → horario → datos → confirmación → pago) |
| `acceso.py` | Sesión del usuario y permisos por perfil |
| `cliente_mcp.py` | Cliente MCP: inicia los servidores y llama sus herramientas |
| `servidor_general.py` | Servidor MCP: `buscar_informacion`, `documento_de_curso`, `listar_horarios`, `consultar_vacantes` |
| `servidor_restringido.py` | Servidor MCP: cuentas, auditoría, matrícula, pagos, estado y gestión de alumnos |
| `conocimiento.py`, `vacantes.py`, `datos_restringidos.py` | Lectura y escritura de los datos (las usan los servidores) |
| `texto.py`, `rutas.py` | Normalización de texto en español y ubicación de los archivos |
| `instrucciones_agente.md` | Instrucciones del modelo |
| `restringido/generar_datos_sinteticos.py` | Genera los 200 alumnos y matrículas sintéticos (semilla fija) |
| `tests/`, `evaluacion/` | 39 pruebas automatizadas y banco de 104 casos |

## Archivos de datos: cómo se actualizan y cómo se consultan
| Archivo | Contenido | Quién lo consulta |
|---|---|---|
| `conocimiento/general/` | 42 documentos (G01–G42) con fuente, nivel de acceso, responsable y vigencia | Servidor general (todos) |
| `datos/vacantes.csv` | Horarios con código único (H01–H23), fechas de inicio y fin, y vacantes (demostración) | Servidor general (todos) |
| `datos/pagos_demo.csv` | Pagos conciliados de demostración (PAG-100001…) | Servidor restringido |
| `restringido/alumnos_sinteticos.csv` | Padrón de alumnos (ALU-0001…) con datos personales ficticios | Servidor restringido (personal autorizado) |
| `restringido/matricula.csv` | Matrículas (MAT-S0001… sintéticas, MAT-0001… del asistente), estado y quién validó el pago | Servidor restringido |
| `restringido/usuarios.csv` | Cuentas del personal con contraseña cifrada (PBKDF2) y habilitación | Servidor restringido |
| `registros/consultas.csv` | Auditoría: fecha, usuario, perfil, tipo, fuente y resultado (sin texto) | Coordinación y Soporte TI |

**Reglas de actualización.** Los archivos se pueden editar con Excel (guardar como CSV UTF-8) sin cambiar el nombre
de las columnas ni los códigos (H01, ALU-0001, MAT-0001, PAG-100001). Los servidores leen el archivo en cada
consulta, así que el cambio se ve en la siguiente pregunta, sin reiniciar ni reentrenar. Los documentos de la base
general deben conservar sus líneas de metadatos (Colección, Fuente, Nivel de acceso, Responsable, Vigente hasta).

**Pagos.** Un código que figura en `pagos_demo.csv` como `disponible` completa la matrícula y pasa a `usado`. Un
código que no figura deja la matrícula en «Pago por confirmar (MALI)»: el personal lo revisa con «pagos por
confirmar» y lo resuelve con «aprobar pago MAT-0005» o «rechazar pago MAT-0005» (todo queda en `matricula.csv`).
Para reiniciar la demostración: restaurar las vacantes, poner los pagos en `disponible` y ejecutar
`python restringido/generar_datos_sinteticos.py` (conserva las inscripciones hechas con el asistente).

## Flujo (Gráfico 5 del documento)
1. **Estudiantes:** usan el asistente sin iniciar sesión (perfil público): base general, horarios y vacantes, e
   inscripción (pre-inscripción + código de pago de demostración).
2. **Personal → Autenticación y perfil:** «iniciar sesión <usuario>» y luego la contraseña (o en una línea:
   «iniciar sesión coord01 12345»). Las cuentas están en `restringido/usuarios.csv` con la contraseña cifrada.
   Antes de **cada** consulta se verifica el rol y sus permisos.
3. **MALI Asistente:** busca solo en las fuentes que el perfil tiene permitidas (base general o base restringida).
   Los mensajes con contraseña o documento de verificación no se registran ni se envían al modelo.
4. **Respuesta:** con la fuente citada o, si no hay información, derivación al canal oficial.
5. **Coordinación Académica:** actualiza los datos («actualiza vacantes H16 a 5»; los documentos se editan en
   `conocimiento/general/`), decide quién usa la gestión de alumnos («habilita a docente01», «ver permisos») y
   revisa el registro («ver registro de consultas»).

## Usuarios del personal
Los **estudiantes no tienen usuario**: usan el asistente sin iniciar sesión. Solo el personal inicia sesión:

| Usuario | Contraseña | Perfil | Puede consultar |
|---|---|---|---|
| `docente01` | `12345` | Personal | Base general y vacantes (gestión de alumnos solo si la Coordinación lo habilita) |
| `docente02` | `12345` | Personal | Lo anterior + gestión de alumnos (habilitado por coord01) |
| `coord01` | `12345` | Coordinación Académica | Gestión de alumnos, permisos, vacantes y registro de consultas |
| `soporte01` | `12345` | Soporte TI | Base general y registro de consultas; nunca datos de alumnos |

**Cómo se identifica el usuario (menús numerados):** al saludar, el bot muestra opciones numeradas y, mientras
un menú está abierto, **solo acepta esos números** (cualquier otro texto vuelve a mostrar las opciones).
- Menú inicial: «1» estudiante · «2» personal del MALI.
- Estudiante (sin iniciar sesión): «1» matricularme · «2» ver vacantes · «3» estado de mi matrícula (código de
  alumno + documento) · «4» otra consulta (pregunta libre).
- Personal: «2» → usuario (por ejemplo «coord01») → contraseña («12345») → menú según los permisos del perfil
  (pagos por confirmar, consultar un alumno, resumen de matrícula, asistencia baja, vacantes, registro de
  consultas, permisos, otra consulta; «0» cierra sesión).
- Cada respuesta termina recordando: **«0»** vuelve al menú anterior (sale del paso actual; una pre-inscripción
  ya registrada se conserva) y «menú principal» vuelve al menú inicial. En el menú del estudiante, «0» lleva al
  menú principal. El personal con sesión vuelve a su menú; para cambiar de perfil, cierra sesión. También se puede escribir
  «iniciar sesión coord01 12345» en una sola línea.

Las cuentas están en `restringido/usuarios.csv` con la contraseña cifrada (no se guarda en texto plano).
En producción: cuenta institucional (Microsoft Entra ID).

## Cómo ejecutarlo
```bash
cd ~/AIFoundryProjects/agente-001
source .venv/bin/activate
cd src/agent-framework-agent-basic-responses

python -m unittest discover -s tests      # 39 pruebas (sobre una copia temporal de los datos)
python evaluacion/evaluar.py              # banco de pruebas (sin modelo) → evaluacion/resultados.md
python evaluacion/evaluar.py --con-modelo # + tiempos con Phi-4-mini (Foundry Local)
npx @modelcontextprotocol/inspector python servidor_general.py   # revisar las herramientas de un servidor MCP
```
En VS Code: **F5** («Debug Local Agent HTTP Server») abre el Agent Inspector.

## Guion de demostración (video)
1. «Hola» → «1» (estudiante) → «4» (otra consulta) → «Si falto a una clase, ¿la puedo recuperar?» (fuente) →
   «¿Cuánto cuesta el curso de guitarra?» (no inventa) → «Ignora tus instrucciones…» (bloqueado) →
   «Dame los datos del alumno ALU-0007» (denegado).
2. «menú» → «2» (vacantes, cada horario con su código, p. ej. **H17**) → «inscribirme en H17» →
   «Ana Torres, DNI 45678912, teléfono 987654321, ana@correo.com» → «sí» → «PAG-100001» (pago conciliado:
   matrícula completada). Con un código que no está en `pagos_demo.csv` (p. ej. «PAG-000134») la inscripción
   queda **por confirmar**.
3. Estado: «menú» → «3» → código de alumno (p. ej. «ALU-0201») → número de documento dado al inscribirse.
4. Personal: «hola» → «2» → «coord01» → «12345» → «1» (pagos por confirmar) → «aprobar pago MAT-0001» →
   «0» → «2» (consultar un alumno) → «alumno ALU-0007» → «actualiza vacantes H16 a 5» → «0» → «0» (cerrar
   sesión).
