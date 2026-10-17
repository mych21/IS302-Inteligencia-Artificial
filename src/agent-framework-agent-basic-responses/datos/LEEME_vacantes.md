# Archivo de vacantes (datos/vacantes.csv)

Lo consulta la herramienta MCP `consultar_vacantes`. **Los datos actuales son de EJEMPLO** (el MALI no publica
sus vacantes); sirven para la demostración de la PC2. Para usar datos reales, reemplaza el archivo manteniendo
las mismas columnas, o apunta a otro archivo con la variable `VACANTES_ARCHIVO` en `.env`.

| Columna | Ejemplo |
|---|---|
| codigo | H04 (identifica el horario) |
| periodo | Verano 2027 |
| curso | Guitarra |
| categoria | Música |
| sede | Lima – Principal |
| modalidad | Presencial / Virtual (Zoom) |
| publico | Jóvenes y adultos |
| horario | Sáb 15:00–17:00 |
| fecha_inicio | 09/01/2027 |
| vacantes_totales | 12 |
| vacantes_disponibles | 1 |
| actualizado_al | 10/10/2026 |

Al confirmar una inscripción, el agente descuenta 1 en `vacantes_disponibles` y registra la matrícula en
`datos/matriculas.csv` (se crea solo, con código MAT-0001, MAT-0002…; estado "Pre-inscrito (pendiente de pago)").
Luego pide el código de pago: `datos/pagos_demo.csv` tiene 20 códigos de demostración (PAG-100001 a PAG-100020).
Al validar uno, se marca como `usado`, la matrícula pasa a "Inscrito DEMO (pago validado)" y el asistente muestra el
horario y la información del curso. Para reiniciar la demo, restaura las vacantes, pon los pagos en `disponible`
y borra `matriculas.csv`.

El agente lee el archivo en cada consulta: si lo editas, no hace falta reiniciar nada.
Si guardas desde Excel, usa "CSV UTF-8 (delimitado por comas)".
