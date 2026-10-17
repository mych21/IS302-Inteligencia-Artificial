# MALI Asistente – prototipo del trabajo final (IS302 Inteligencia Artificial, UPC 2026-2)

Chatbot con IA para orientar a la comunidad educativa del MALI y proteger sus datos. Implementa lo descrito en
el documento final: RAG sobre fuentes institucionales, perfiles con control de acceso, base restringida de gestión
de alumnos (sintética), registro de consultas, aviso de privacidad, resistencia a *prompt injection* y el banco de
pruebas de la sección 4.4.

## Arquitectura
```
Usuario ─► Agent Inspector (VS Code) / demo_cli.py
             │
             ▼
   main.py  (Microsoft Agent Framework + Foundry Local, modelo Phi-4-mini)
     └─ middleware orquestar() ─► asistente.py  (decide cada mensaje)
            ├─ seguridad: prompt injection y datos sensibles ............ respuesta del sistema
            ├─ acceso.py: perfiles, gestión de alumnos, registro ........ respuesta del sistema
            ├─ vacantes.py / matricula.py: vacantes y pre-inscripción .... respuesta del sistema
            └─ conocimiento.py: RAG (BM25) sobre conocimiento/general ..... redacta Phi-4-mini con la fuente
   mali_mcp_server.py (MCP): buscar_informacion_mali y consultar_vacantes (solo nivel general)
```

| Carpeta / archivo | Contenido | Nivel |
|---|---|---|
| `conocimiento/general/` | 42 documentos (G01–G42) con fuente, responsable y vigencia | General |
| `datos/vacantes.csv` | Horarios y vacantes de demostración | General (DEMO) |
| `datos/pagos_demo.csv` | Pagos conciliados de demostración (PAG-100001…); los aprobados por el personal se agregan como `usado` | DEMO |
| `restringido/alumnos_sinteticos.csv` | Padrón de alumnos (ALU-0001…): nombre, documento, teléfono, correo y situación | Restringido |
| `restringido/matricula.csv` | Todos los alumnos matriculados, con sus datos personales y el mismo código de alumno | Restringido |
| `restringido/usuarios.csv` | Cuentas del personal con contraseña cifrada; la Coordinación habilita al personal | Restringido |
| `registros/consultas.csv` | Auditoría: fecha, usuario, perfil, tipo, fuente, resultado (sin texto) | Coordinación y TI |
| `evaluacion/` | Banco de 104 pruebas, `evaluar.py` y resultados | – |

## Flujo (Gráfico 5 del documento)
1. **Estudiantes:** usan el asistente sin iniciar sesión (perfil público): base general, horarios y vacantes, e
   inscripción (pre-inscripción + código de pago de demostración).
2. **Personal → Autenticación y perfil:** «iniciar sesión <usuario>» y luego la contraseña (o en una línea:
   «iniciar sesión coord01 12345»). Las cuentas están en `restringido/usuarios.csv` con la contraseña cifrada.
   Antes de **cada** consulta se verifica el rol y sus permisos.
3. **MALI Asistente:** busca solo en las fuentes que el perfil tiene permitidas (base general o base restringida).
   Los mensajes con contraseña no se registran ni se envían al modelo.
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

**Cómo se identifica el usuario:** al saludar, el bot pregunta «¿eres estudiante o personal del MALI?».
- «estudiante» → se atiende sin iniciar sesión (también si pregunta directamente sin responder).
- «personal» → el bot pide el usuario (por ejemplo «coord01») y luego la contraseña («12345»).
  También se puede escribir «iniciar sesión coord01 12345» en una sola línea. Para salir: «cerrar sesión».

Las cuentas están en `restringido/usuarios.csv` con la contraseña cifrada (no se guarda en texto plano).
En producción: cuenta institucional (Microsoft Entra ID).

## Cómo ejecutarlo
```bash
cd ~/AIFoundryProjects/agente-001
source .venv/bin/activate
cd src/agent-framework-agent-basic-responses

python -m unittest discover -s tests      # 22 pruebas
python evaluacion/evaluar.py              # banco de pruebas (sin modelo) → evaluacion/resultados.md
python evaluacion/evaluar.py --con-modelo # + tiempos con Phi-4-mini (Foundry Local)
python demo_cli.py                        # guion de demostración (con el modelo)
python demo_cli.py --sin-modelo           # guion sin el modelo
```
En VS Code: **F5** («Debug Local Agent HTTP Server») abre el Agent Inspector.

## Guion de demostración (video)
1. «Hola» → «estudiante» → «Si falto a una clase, ¿la puedo recuperar?» (fuente) →
   «¿Cuánto cuesta el curso de guitarra?» (no inventa) → «Ignora tus instrucciones…» (bloqueado) →
   «Dame los datos del alumno ALU-0007» (denegado).
2. «información de guitarra» (muestra cada horario con su código, p. ej. **H17**) → «inscribirme en H17» →
   «Ana Torres, DNI 45678912, teléfono 987654321, ana@correo.com» → «sí» → «PAG-100001» (pago conciliado:
   matrícula completada). Con un código que no está en `pagos_demo.csv` (p. ej. «PAG-000134») la inscripción
   queda **por confirmar**. Para ver el estado: «hola» → «estudiante» → «3» (estado de mi matrícula) →
   código de alumno (p. ej. «ALU-0201») → número de documento dado al inscribirse (verificación).
3. Personal: «personal» → «coord01» → «12345» → «pagos por confirmar» → «aprobar pago MAT-0001» (o «rechazar
   pago MAT-0001») → «Dame los datos del alumno ALU-0007» →
   «actualiza vacantes H16 a 5» → «ver registro de consultas» → «cerrar sesión».
