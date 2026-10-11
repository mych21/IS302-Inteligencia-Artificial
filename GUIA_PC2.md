# PC2 – MALI Asistente Estudiantil (agente de IA local con MCP)
IS302 Inteligencia Artificial · UPC · 2026-2

Agente que evidencia el avance del proyecto final *"Predicción de retención y apoyo al estudiante del MALI
mediante IA"*: orienta a estudiantes con la información oficial de MALI Educación y, para coordinación académica,
consulta el modelo predictivo de retención. Todo corre **en local** y las herramientas se conectan por **MCP**.

## 1. Arquitectura
```
Usuario ──► Agent Inspector (VS Code) o demo_cli.py
              │
              ▼
   MALI Asistente Estudiantil  (Microsoft Agent Framework)
      │  instrucciones_agente.md
      │
      ├──► Modelo local: Phi-4-mini  (Foundry Local, GPU Apple Silicon, endpoint 127.0.0.1)
      │
      └──► Servidor MCP propio "mali-educacion"  (mali_mcp_server.py, stdio)
              ├─ buscar_informacion_mali  → base de conocimiento oficial (conocimiento/*.md, búsqueda BM25)
              ├─ listar_oferta            → cursos y programas por categoría
              ├─ canales_de_atencion      → correos y enlaces oficiales
              ├─ consultar_vacantes       → archivo local datos/vacantes.csv (data dummy)
              └─ senal_de_apoyo           → modelo predictivo del proyecto (uso interno, revisión humana)
```

## 2. Modelo seleccionado y justificación
**Modelo local:** `Phi-4-mini-instruct` (Microsoft, 3,8 mil millones de parámetros), ID en Foundry Local
`Phi-4-mini-instruct-generic-gpu:5`.

| Criterio | Por qué Phi-4-mini |
|---|---|
| Privacidad | Corre en la laptop: las consultas de estudiantes y los datos que usa la señal de apoyo no salen del equipo. |
| Llamada a herramientas | Soporta *function calling*, necesario para usar las herramientas del servidor MCP. |
| Recursos | Con 3,8 B de parámetros funciona en la GPU de una Mac con chip Apple; modelos de 14 B a 20 B son más lentos o no caben en memoria. |
| Contexto | Ventana de contexto amplia (128 K tokens), suficiente para instrucciones + fragmentos recuperados. |
| Idioma | Responde en español; las respuestas se apoyan en el texto que devuelven las herramientas. |
| Costo y licencia | Gratis y con licencia MIT; no requiere suscripción de nube. |

**Alternativas evaluadas (catálogo de Foundry Local):**
- `qwen2.5-7b-instruct-generic-gpu:4`: mejor español y llamada a herramientas, pero el doble de tamaño. Es el
  **plan B** si Phi-4-mini no usa bien las herramientas: basta cambiar `FOUNDRY_LOCAL_MODEL` en `.env`.
- `gpt-oss-20b` y `Phi-4` (14 B): más capaces, pero demasiado pesados para una laptop en tiempo real.
- **Opcional nube:** la plantilla ya incluye un despliegue de `gpt-5.4-mini` en Azure AI Foundry (`azure.yaml`).
  Mayor calidad, pero con costo por uso y enviando datos fuera del equipo, por eso no es la opción principal.

## 3. Instrucciones del agente
Están en `instrucciones_agente.md`. Resumen:
1. Usar primero las herramientas MCP para toda pregunta sobre MALI Educación y citar la fuente.
2. Si la herramienta no trae el dato (precios, horarios, certificados), decir "No tengo ese dato en mis fuentes"
   y derivar a cursosdearte@mali.pe o a "Cursos y horarios".
3. Nunca inventar información, pedir datos sensibles ni tomar decisiones (matrículas, aprobaciones, devoluciones).
4. La señal de apoyo es solo para coordinación y requiere revisión humana; nunca se le dice a un estudiante que
   "está en riesgo".

## 4. Funcionalidades
| Tipo | Funcionalidad | Pregunta de prueba |
|---|---|---|
| Básica | Responder con información oficial y citar fuente | ¿Qué cursos de baile tienen? |
| Básica | Explicar políticas (inasistencias, devoluciones, edad mínima) | Si falto a una clase, ¿la puedo recuperar? |
| Básica | Consultar vacantes en archivo local (data dummy) | ¿Cuáles son las vacantes disponibles del curso de verano? |
| Básica | No inventar datos que no tiene | ¿Cuánto cuesta el curso de guitarra? |
| Básica | Privacidad y no tomar decisiones | Mi DNI es 45678912, ¿me puedes matricular? |
| Avanzada | Señal de apoyo con el modelo predictivo del proyecto | Soy de coordinación… evalúa a un alumno con 58 % de asistencia… |
| **Extra MCP** | Todas las herramientas se consumen desde un servidor MCP propio (`mali_mcp_server.py`) | (se ve en el Agent Inspector como llamadas a herramientas) |

La base de conocimiento usa solo información pública de educacion.mali.pe y los Términos y condiciones de MALI
Educación 2026 (consultados el 10/10/2026). El modelo predictivo se entrenó con datos **sintéticos**; la herramienta
usa la Regresión Logística exportada a JSON (F1 de desertores 0,627; ROC-AUC 0,799), que en el proyecto tuvo un
desempeño equivalente al Random Forest y corre sin librerías adicionales.

**Vacantes:** `datos/vacantes.csv` contiene data dummy (23 horarios de "Verano 2027" y "Noviembre 2026"),
porque el MALI no publica sus vacantes. El agente la lee en cada consulta; se puede editar en Excel (guardar como
CSV UTF-8) o apuntar a otro archivo con `VACANTES_ARCHIVO=` en `.env`. Ver `datos/LEEME_vacantes.md`.

## 5. Cómo ejecutarlo
```bash
cd ~/AIFoundryProjects/agente-001
source .venv/bin/activate
cd src/agent-framework-agent-basic-responses

python -m unittest tests/test_main.py   # 1. pruebas de las herramientas
python demo_cli.py                      # 2. demo por consola (preguntas del video)
python demo_cli.py --chat               # 3. conversación libre
```
Con interfaz: en VS Code presiona **F5** ("Debug Local Agent HTTP Server") y conversa en el **Agent Inspector**;
ahí se ven las llamadas a las herramientas MCP.

La primera ejecución descarga el modelo (2–3 GB) y puede tardar varios minutos.

## 6. Guion del video (1 minuto)
| Tiempo | En pantalla | Qué decir |
|---|---|---|
| 0:00–0:10 | VS Code con `main.py` y `.env` | "Este es MALI Asistente Estudiantil, el agente de nuestro proyecto final. Corre en local con Phi-4-mini en Foundry Local." |
| 0:10–0:18 | `instrucciones_agente.md` | "Sus instrucciones: responder solo con fuentes oficiales del MALI, no inventar, proteger datos y no tomar decisiones." |
| 0:18–0:35 | Agent Inspector o `demo_cli.py`: cursos de baile e inasistencias | "Pregunto por los cursos de baile y por las faltas: responde con la información oficial y cita la fuente." |
| 0:35–0:45 | Pregunta de precio y la del DNI | "Si no tiene el dato, lo dice y deriva al correo oficial; si escribo mi DNI, me pide no compartirlo." |
| 0:45–0:57 | Pregunta de coordinación + llamada a la herramienta | "Función avanzada: por MCP consulta nuestro modelo predictivo y da una señal de apoyo para revisión humana." |
| 0:57–1:00 | `mali_mcp_server.py` | "Todas las herramientas vienen de nuestro propio servidor MCP." |

## 7. Problemas conocidos
- **El servidor de Foundry no arranca (`libonnxruntime.1.dylib` no encontrado):** crear el enlace
  `ln -s libonnxruntime.dylib libonnxruntime.1.dylib` en `/opt/homebrew/Cellar/foundrylocal/0.11.0/libexec`.
- **"Model not found: phi-4-mini":** usar el ID completo `Phi-4-mini-instruct-generic-gpu:5` en `.env`.
- **El agente no llama a las herramientas o responde sin fuente:** cambiar a `qwen2.5-7b-instruct-generic-gpu:4`
  en `.env`.
- **VS Code parece "pegado" la primera vez:** se está descargando el modelo; revisar con `foundry server logs`.
