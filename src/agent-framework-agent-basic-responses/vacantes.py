"""Archivo de vacantes (datos/vacantes.csv, datos de demostración): lectura, escritura y respuesta por curso, sede,
periodo o modalidad. Lo usa el servidor MCP general (y el restringido para descontar o actualizar vacantes)."""
from __future__ import annotations

import csv
import difflib
from datetime import datetime

import rutas
import texto as tx

_GENERICAS_CONSULTA = {"curso", "cursos", "taller", "tallere", "clase", "horario", "programa", "periodo", "temporada",
                       "inscripcion", "inscribir", "matricula", "hay", "cuanta", "cuanto", "ver", "todo", "toda",
                       "informacion", "dato", "lista", "mostrar", "muestrame", "dime", "necesito", "busco"}
_MODO_VIRTUAL = {"virtual", "virtuale", "zoom", "online", "remoto", "linea"}


# ------------------------------------------------------------------ lectura y escritura
def leer_tabla() -> tuple[list[dict], list[str], str]:
    """Filas tal como están en el archivo (texto), sus columnas y el separador (',' o ';')."""
    contenido = rutas.vacantes().read_text(encoding="utf-8-sig")
    primera = contenido.splitlines()[0]
    delim = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.DictReader(contenido.splitlines(), delimiter=delim)
    filas = [{(k or "").strip().lower(): (v or "").strip() for k, v in f.items()} for f in lector]
    return filas, [(c or "").strip().lower() for c in lector.fieldnames or []], delim


def guardar_tabla(filas: list[dict], campos: list[str], delim: str) -> None:
    with open(rutas.vacantes(), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=delim)
        w.writeheader()
        w.writerows(filas)


def disponibles(fila: dict) -> int:
    try:
        return int(float(fila.get("vacantes_disponibles") or 0))
    except ValueError:
        return 0


def horarios() -> list[dict]:
    """Todas las filas con vacantes_disponibles como número. Se lee en cada consulta: si la Coordinación edita el
    archivo, la siguiente consulta ya usa el dato nuevo."""
    filas, _, _ = leer_tabla()
    for f in filas:
        f["vacantes_disponibles"] = disponibles(f)
    return filas


def descontar_vacante(codigo: str) -> dict | str:
    """Resta una vacante al horario. Devuelve la fila actualizada o un mensaje de error."""
    filas, campos, delim = leer_tabla()
    fila = next((f for f in filas if f.get("codigo", "").upper() == codigo.upper()), None)
    if fila is None:
        return f"no existe el horario {codigo}."
    if disponibles(fila) <= 0:
        return f"el horario {codigo} ya no tiene vacantes."
    fila["vacantes_disponibles"] = str(disponibles(fila) - 1)
    if "actualizado_al" in fila:
        fila["actualizado_al"] = datetime.now().strftime("%d/%m/%Y")
    guardar_tabla(filas, campos, delim)
    return fila


def fijar_vacantes(codigo: str, cantidad: int) -> tuple[dict, str] | None:
    """La Coordinación corrige las vacantes de un horario. Devuelve (fila, valor anterior) o None si no existe."""
    filas, campos, delim = leer_tabla()
    fila = next((f for f in filas if f["codigo"].upper() == codigo.upper()), None)
    if not fila:
        return None
    antes = fila["vacantes_disponibles"]
    fila["vacantes_disponibles"] = str(max(0, cantidad))
    fila["actualizado_al"] = datetime.now().strftime("%d/%m/%Y")
    guardar_tabla(filas, campos, delim)
    return fila, antes


# ------------------------------------------------------------------ búsqueda por pregunta libre
def _coincide(filtro: str, campo: str) -> bool:
    """Coincidencia flexible: sin tildes, mayúsculas ni plurales, y con sinónimos (baile → danzas, etc.)."""
    if not filtro.strip():
        return True
    if tx.normalizar(filtro).strip() in tx.normalizar(campo):
        return True
    genericas = {"arte", "y", "de", "curso", "taller", "nino", "edad", "adulto", "joven", "todas", "toda"}
    clave = tx.conjunto(filtro) - genericas
    return bool((clave or tx.conjunto(filtro)) & tx.conjunto(campo))


def _coincide_todo(filtro: str, campo: str) -> bool:
    """Para sedes: todas las palabras distintivas del filtro deben estar (evita que 'San Miguel' traiga SJL)."""
    if not filtro.strip() or tx.normalizar(filtro).strip() in tx.normalizar(campo):
        return True
    clave = tx.conjunto(filtro) - tx.GENERICAS_SEDE
    return bool(clave) and clave <= tx.conjunto(campo)


def _filtros_desde_texto(consulta: str, filas: list[dict]) -> dict:
    """Deduce curso, sede y periodo a partir de una pregunta libre ("vacantes de guitarra en verano")."""
    t = tx.conjunto(consulta) - {tx.tokens(p)[0] for p in tx.PALABRAS_VACANTES if tx.tokens(p)}
    filtros = {"curso": "", "sede": "", "periodo": "", "modalidad": "", "no_reconocido": ""}
    periodos = {f["periodo"] for f in filas}
    filtros["periodo"] = next((p for p in periodos if t & (tx.conjunto(p) - {"2026", "2027"})), "")
    cursos = {f["curso"] for f in filas}
    exactos = [c for c in cursos if tx.normalizar(c).strip() in tx.normalizar(consulta)]
    if exactos:
        filtros["curso"] = exactos[0]
    else:
        categorias = {f.get("categoria", "") for f in filas}
        filtros["curso"] = next((c for c in sorted(cursos | categorias) if t & (tx.conjunto(c) - {"arte", "artes"})), "")
    sedes = {f["sede"] for f in filas if f["sede"].lower() != "virtual"}
    filtros["sede"] = max(sedes, key=lambda s: len(t & (tx.conjunto(s) - tx.GENERICAS_SEDE)), default="")
    if not t & (tx.conjunto(filtros["sede"]) - tx.GENERICAS_SEDE):
        filtros["sede"] = ""
    if t & _MODO_VIRTUAL:
        filtros["modalidad"] = "virtual"
    if not filtros["curso"]:
        # Palabras sobrantes: se corrigen errores de tipeo ("dispoibles", "guitara"); si una parece un curso se usa
        # como filtro, y si no se reconoce se informa (sin bloquear la respuesta).
        usadas = set().union(*(tx.conjunto(v) for k, v in filtros.items() if v and k != "no_reconocido"))
        ignorar = {t for p in tx.PALABRAS_VACANTES | _GENERICAS_CONSULTA | tx.RELLENO
                   for t in tx.tokens(p) + [tx.normalizar(p)]}
        vocab_cursos = {}
        for f in filas:
            for tok in tx.conjunto(f"{f['curso']} {f.get('categoria', '')} {f.get('publico', '')}") \
                    - {"arte", "artes", "ano", "edad", "edade", "toda", "y"}:
                vocab_cursos.setdefault(tok, tok)
        desconocidas = []
        for tok in sorted(t - usadas - _MODO_VIRTUAL - tx.GENERICAS_SEDE - {"2026", "2027"}):
            if tok.isdigit() or tok in ignorar or difflib.get_close_matches(tok, ignorar, 1, 0.8):
                continue
            parecido = difflib.get_close_matches(tok, vocab_cursos, 1, 0.8)
            if parecido:
                filtros["curso"] = vocab_cursos[parecido[0]]
                break
            desconocidas.append(tok)
        if not filtros["curso"] and desconocidas:
            filtros["no_reconocido"] = " ".join(desconocidas)
    return filtros


def _seleccionar(consulta: str) -> dict:
    """Filtra el archivo de vacantes según la pregunta. Devuelve las filas elegidas y los filtros aplicados."""
    archivo = rutas.vacantes()
    try:
        filas = horarios()
    except FileNotFoundError:
        return {"error": f"no se encontró el archivo de vacantes ({archivo.name})."}
    f = _filtros_desde_texto(consulta, filas)
    curso, sede, periodo, modalidad, no_reconocido = (f["curso"], f["sede"], f["periodo"], f["modalidad"],
                                                      f["no_reconocido"])

    def _filtrar(curso):
        return [f for f in filas
                if (_coincide(curso, f"{f['curso']} {f.get('categoria', '')} {f.get('publico', '')}") if curso else True)
                and _coincide_todo(sede, f["sede"]) and _coincide(periodo, f["periodo"])
                and _coincide(modalidad, f.get("modalidad", ""))]

    elegidas = _filtrar(curso)
    if not elegidas and curso:                        # si el curso deducido no existe, se relaja el filtro
        no_reconocido, curso = curso, ""
        elegidas = _filtrar(curso)
    filtro_txt = ", ".join(f"{k}: {v}" for k, v in
                           [("curso", curso), ("sede", sede), ("periodo", periodo), ("modalidad", modalidad)] if v)
    if not elegidas:
        return {"error": f"el archivo de vacantes no tiene horarios para ({filtro_txt or 'sin filtro'})."}
    fechas = sorted({f.get("actualizado_al", "") for f in elegidas if f.get("actualizado_al")})
    fuente = (f"Fuente: archivo de vacantes {archivo.name}" + (f" (actualizado al {fechas[-1]})" if fechas else "")
              + " – datos de ejemplo para la demostración. La vacante se asegura solo al completar la inscripción "
              "en cursosdearte@mali.pe.")
    return {"con": [f for f in elegidas if f["vacantes_disponibles"] > 0],
            "llenos": [f for f in elegidas if f["vacantes_disponibles"] <= 0],
            "curso": curso, "filtro_txt": filtro_txt, "no_reconocido": no_reconocido, "fuente": fuente}


def vacantes_para_usuario(consulta: str) -> str:
    """Respuesta lista para el usuario, agrupada por curso, construida solo con las filas del archivo."""
    r = _seleccionar(consulta)
    if "error" in r:
        return ("No encontré vacantes para esa búsqueda en el archivo de vacantes. Puedes preguntarme por otro "
                "curso, sede o periodo, o escribir a cursosdearte@mali.pe.")
    lineas = []
    if r["no_reconocido"]:
        lineas.append(f"No tengo un curso llamado «{r['no_reconocido']}» en el archivo de vacantes; "
                      "estas son las vacantes que sí están registradas:\n")
    if not r["con"]:
        lineas.append("Por ahora no quedan vacantes para esa búsqueda (" + (r["filtro_txt"] or "todos") + ").")
    else:
        lineas.append("Estas son las vacantes disponibles por curso" +
                      (f" ({r['filtro_txt']})" if r["filtro_txt"] else "") + ":\n")
        por_curso: dict[str, list[dict]] = {}
        for f in sorted(r["con"], key=lambda f: (f["curso"], f["periodo"], f["sede"])):
            por_curso.setdefault(f["curso"], []).append(f)
        for curso, filas in por_curso.items():
            total = sum(f["vacantes_disponibles"] for f in filas)
            lineas.append(f"**{curso}** — {total} vacante(s)")
            for f in filas:
                lineas.append(f"- **{f.get('codigo', '')}** · {f['sede']} · {f['horario']} · del "
                              f"{f.get('fecha_inicio', '-')} al {f.get('fecha_fin', '-')} ({f['periodo']}) · "
                              f"{f.get('publico', '')} · {f['vacantes_disponibles']} vacante(s)")
            lineas.append("")
    if r["llenos"]:
        lineas.append("Sin vacantes (llenos): " + "; ".join(
            f"{f['curso']} – {f['sede']} ({f['periodo']})" for f in r["llenos"]))
    if r["con"]:
        lineas.append("\n¿Te gustaría inscribirte? Escribe el **código del horario**, por ejemplo: «inscribirme en "
                      f"{r['con'][0].get('codigo', '')}».")
    lineas.append("\n" + r["fuente"])
    return "\n".join(lineas).replace("\n\n\n", "\n\n")
