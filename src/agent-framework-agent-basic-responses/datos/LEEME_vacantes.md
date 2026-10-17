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
| fecha_inicio | 09/01/2027 (primer día de clase) |
| fecha_fin | 27/02/2027 (último día de clase) |
| vacantes_totales | 12 |
| vacantes_disponibles | 1 |
| actualizado_al | 10/10/2026 |

Al confirmar una inscripción, el agente descuenta 1 en `vacantes_disponibles`, crea el **código de alumno**
(ALU-0201, ALU-0202…) y registra la matrícula en `restringido/matricula.csv` (código MAT-0001…, estado
"Pre-inscrito (pendiente de pago)").
Luego pide el código de pago: `datos/pagos_demo.csv` tiene 20 códigos de demostración (PAG-100001 a PAG-100020).
Al validar uno, se marca como `usado`, la matrícula pasa a "Matriculado" y el asistente muestra el
horario y la información del curso. Si el código **no** figura en `pagos_demo.csv` (por ejemplo PAG-000134), la
matrícula queda "Pago por confirmar (MALI)": la vacante sigue separada y el personal habilitado o la Coordinación
escribe «pagos por confirmar» para verlos y «aprobar pago MAT-0005» o «rechazar pago MAT-0005» para resolverlos
(todo se lee y se actualiza en `restringido/matricula.csv`: al aprobar pasa a "Matriculado" con el usuario y la
fecha en `validado_por` y `fecha_validacion`; al rechazar vuelve a pendiente de pago). El estudiante consulta el
estado con «estado de mi matrícula» + su código de alumno + su número de documento (verificación). Para reiniciar la demo, restaura las vacantes, pon los pagos en `disponible`
y ejecuta `python restringido/generar_matricula.py` (deja solo las 200 matrículas sintéticas… y las del
asistente; para quitarlas también, borra sus filas con origen «asistente»).

El agente lee el archivo en cada consulta: si lo editas, no hace falta reiniciar nada.
Si guardas desde Excel, usa "CSV UTF-8 (delimitado por comas)".
