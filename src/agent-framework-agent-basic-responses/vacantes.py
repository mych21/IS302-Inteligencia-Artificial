"""
Vacantes de MALI Educación: lee el archivo local datos/vacantes.csv (data dummy) y responde por curso, sede,
periodo o modalidad. Solo usa la librería estándar.
"""
from __future__ import annotations

import csv
import difflib
import os
import re
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARCHIVO_VACANTES_DEFECTO = AQUI / "datos" / "vacantes.csv"

STOPWORDS = set("""a al algo algun alguna como con cual cuales de del el ella en entre es esta este esto hay la las le les
lo los me mi mis muy no o para pero por que se si sin su sus te tengo tienen tu un una uno y ya yo quiero quisiera
puedo podria saber hola buenas buenos dias tardes noches gracias favor ustedes usted mali museo hay tienen ofrecen""".split())

SINONIMOS = {
    "baile": "bailes danza", "bailar": "bailes danza", "danza": "bailes danza", "danzas": "bailes danza",
    "pintar": "pintura dibujo plasticas", "dibujar": "dibujo pintura", "cantar": "canto vocal",
    "canto": "canto vocal", "hablar": "oratoria habla", "musica": "musicales instrumentos",
    "instrumento": "instrumentos musicales", "tocar": "instrumentos musicales", "teatro": "teatro escenicas actuacion",
    "actuar": "actuacion teatro", "recuperar": "recuperables inasistencias", "falto": "inasistencias recuperables",
    "faltar": "inasistencias recuperables", "falte": "inasistencias recuperables",
    "devuelven": "devolucion pagos", "devolver": "devolucion pagos", "reembolso": "devolucion pagos",
    "retiro": "devolucion pagos retiro", "retirarme": "devolucion pagos retiro", "dinero": "pagos devolucion",
    "online": "virtual zoom", "zoom": "virtual zoom", "remoto": "virtual", "donde": "sede direccion ubicada",
    "queda": "ubicada direccion", "direccion": "direccion ubicada sede principal", "hijo": "ninos edad",
    "hija": "ninos edad", "nino": "ninos edad", "ninos": "ninos edad", "anos": "edad",
    "borren": "datos personales revocar", "borrar": "datos personales revocar", "privacidad": "datos personales",
    "reclamo": "reclamos libro reclamaciones", "queja": "reclamos libro reclamaciones",
    "empresa": "arte empresa colaboradores", "colegio": "colegios experiencias educativas",
    "profesional": "extension profesional", "diplomado": "extension profesional programas",
    "cupo": "cupos vacante", "vacante": "cupos vacante", "llena": "minimo alumnos cancelar horario",
    "salon": "alumnos horario cancelar", "cancelan": "cancelar horario minimo",
    "entrar": "ingreso aulas boleta", "aula": "ingreso aulas boleta", "ingresar": "ingreso aulas boleta",
    "contacto": "correo atencion", "correo": "correo atencion", "ia": "inteligencia artificial",
    "fotos": "fotografia", "comic": "historieta manga comics",
    "paga": "pagos", "pagar": "pagos", "pago": "pagos", "pague": "pagos", "dan": "ofrece ramas artisticas",
    "empezar": "iniciar basico progresiva", "iniciar": "basico progresiva", "nunca": "basico iniciar",
    "estudiado": "basico", "principiante": "basico iniciar", "dictan": "sedes buscador", "dicta": "sedes",
    "recoger": "recoger dejar puntualmente minutos", "anticipacion": "minutos antes", "llegar": "minutos antes",
    "escribo": "correo contacto atencion", "escribir": "correo contacto", "presento": "reclamaciones libro",
    "grabadas": "grabarse sesiones virtual", "grabada": "grabarse sesiones", "grabacion": "grabarse sesiones",
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9@\s]", " ", texto)


def _tokens(texto: str, expandir: bool = False) -> list[str]:
    toks = [t for t in _normalizar(texto).split() if t not in STOPWORDS and len(t) > 1]
    if expandir:
        toks += [s for t in toks if t in SINONIMOS for s in SINONIMOS[t].split()]
    return [t[:-1] if len(t) > 4 and t.endswith("s") else t for t in toks]   # singular simple


# ------------------------------------------------------------------ vacantes (archivo CSV)
PALABRAS_VACANTES = {"vacante", "vacantes", "cupo", "cupos", "disponibilidad", "disponible", "disponibles",
                     "lleno", "llenos", "quedan"}
_GENERICAS_SEDE = {"sede", "principal", "virtual", "zoom", "1", "san", "la", "lo"}
_GENERICAS_CONSULTA = {"curso", "cursos", "taller", "tallere", "clase", "horario", "programa", "periodo", "temporada",
                       "inscripcion", "inscribir", "matricula", "hay", "cuanta", "cuanto", "ver", "todo", "toda",
                       "informacion", "dato", "lista", "mostrar", "muestrame", "dime", "necesito", "busco"}
_RELLENO = {"dame", "da", "danos", "muestra", "muestrame", "lista", "listar", "listame", "ensename", "pasame",
            "necesito", "digas", "diga", "dime", "decir", "quiero", "quisiera", "saber", "conocer", "ver", "mostrar",
            "muestrame", "puedes", "podrias", "cuales", "cual", "son", "estan", "esta", "hay", "tienen", "tiene",
            "abiertas", "abiertos", "proximos", "proximas", "siguiente", "actuales", "todas", "todos", "ahora",
            "ayuda", "ayudame", "info", "porfa", "por", "favor", "consultar", "consulta", "existen", "cuantas"}
_MODO_VIRTUAL = {"virtual", "virtuale", "zoom", "online", "remoto", "linea"}
MAX_FILAS = 15


def _archivo_vacantes() -> Path:
    ruta = os.getenv("VACANTES_ARCHIVO", "").strip()
    if not ruta:
        return ARCHIVO_VACANTES_DEFECTO
    ruta = Path(ruta).expanduser()
    return ruta if ruta.is_absolute() else AQUI / ruta


def _leer_vacantes() -> list[dict]:
    """Lee el CSV en cada consulta (si lo editas, el agente ve el cambio sin reiniciar). Acepta ',' o ';'."""
    texto = _archivo_vacantes().read_text(encoding="utf-8-sig")
    delim = ";" if texto.splitlines()[0].count(";") > texto.splitlines()[0].count(",") else ","
    filas = []
    for f in csv.DictReader(texto.splitlines(), delimiter=delim):
        f = {(k or "").strip().lower(): (v or "").strip() for k, v in f.items()}
        try:
            f["vacantes_disponibles"] = int(float(f.get("vacantes_disponibles") or 0))
        except ValueError:
            f["vacantes_disponibles"] = 0
        filas.append(f)
    return filas


def _set(texto: str) -> set[str]:
    return set(_tokens(texto, expandir=True))


def _pide_solo_generico(resto: set[str]) -> bool:
    return resto <= {"cual", "son", "esta", "estan", "tiene", "abierta", "abierto", "nuevo", "proximo", "siguiente"}


def _pide_vacantes(texto: str) -> bool:
    palabras = set(_normalizar(texto).split())
    if palabras & PALABRAS_VACANTES:
        return True
    try:                                   # «¿qué cursos hay en verano?»: menciona un periodo del archivo
        periodos = {t for f in _leer_vacantes() for t in _normalizar(f["periodo"]).split() if not t.isdigit()}
    except FileNotFoundError:
        return False
    return bool(palabras & periodos) and bool(palabras & {"curso", "cursos", "taller", "talleres", "horario",
                                                          "horarios", "clases", "hay", "dan", "ofrecen"})


def _coincide(filtro: str, campo: str) -> bool:
    """Coincidencia flexible: sin tildes, mayúsculas ni plurales, y con sinónimos (baile → danzas, etc.)."""
    if not filtro.strip():
        return True
    if _normalizar(filtro).strip() in _normalizar(campo):
        return True
    genericas = {"arte", "y", "de", "curso", "taller", "nino", "edad", "adulto", "joven", "todas", "toda"}
    clave = _set(filtro) - genericas
    return bool((clave or _set(filtro)) & _set(campo))


def _coincide_todo(filtro: str, campo: str) -> bool:
    """Para sedes: todas las palabras distintivas del filtro deben estar (evita que 'San Miguel' traiga SJL)."""
    if not filtro.strip() or _normalizar(filtro).strip() in _normalizar(campo):
        return True
    clave = _set(filtro) - _GENERICAS_SEDE
    return bool(clave) and clave <= _set(campo)


def _filtros_desde_texto(texto: str, filas: list[dict]) -> dict:
    """Deduce curso, sede y periodo a partir de una pregunta libre ("vacantes de guitarra en verano")."""
    t = _set(texto) - {_tokens(p)[0] for p in PALABRAS_VACANTES if _tokens(p)}
    filtros = {"curso": "", "sede": "", "periodo": "", "modalidad": "", "no_reconocido": ""}
    periodos = {f["periodo"] for f in filas}
    filtros["periodo"] = next((p for p in periodos if t & (_set(p) - {"2026", "2027"})), "")
    cursos = {f["curso"] for f in filas}
    exactos = [c for c in cursos if _normalizar(c).strip() in _normalizar(texto)]
    if exactos:
        filtros["curso"] = exactos[0]
    else:
        categorias = {f.get("categoria", "") for f in filas}
        filtros["curso"] = next((c for c in sorted(cursos | categorias) if t & (_set(c) - {"arte", "artes"})), "")
    sedes = {f["sede"] for f in filas if f["sede"].lower() != "virtual"}
    filtros["sede"] = max(sedes, key=lambda s: len(t & (_set(s) - _GENERICAS_SEDE)), default="")
    if not t & (_set(filtros["sede"]) - _GENERICAS_SEDE):
        filtros["sede"] = ""
    if t & _MODO_VIRTUAL:
        filtros["modalidad"] = "virtual"
    if not filtros["curso"]:
        # Palabras sobrantes: se corrigen errores de tipeo ("dispoibles", "guitara"); si una parece un curso se usa
        # como filtro, y si no se reconoce se informa (sin bloquear la respuesta).
        usadas = set().union(*(_set(v) for k, v in filtros.items() if v and k != "no_reconocido"))
        ignorar = {t for p in PALABRAS_VACANTES | _GENERICAS_CONSULTA | _RELLENO for t in _tokens(p) + [_normalizar(p)]}
        vocab_cursos = {}
        for f in filas:
            for tok in _set(f"{f['curso']} {f.get('categoria', '')} {f.get('publico', '')}") - {"arte", "artes", "ano", "edad", "edade", "toda", "y"}:
                vocab_cursos.setdefault(tok, tok)
        desconocidas = []
        for tok in sorted(t - usadas - _MODO_VIRTUAL - _GENERICAS_SEDE - {"2026", "2027"}):
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


def _seleccionar(curso: str, sede: str, periodo: str, modalidad: str, consulta: str) -> dict:
    """Filtra el archivo de vacantes. Devuelve las filas elegidas y los filtros aplicados."""
    archivo = _archivo_vacantes()
    try:
        filas = _leer_vacantes()
    except FileNotFoundError:
        return {"error": f"SIN_RESULTADOS: no se encontró el archivo de vacantes ({archivo.name}). "
                         "Deriva a cursosdearte@mali.pe."}
    no_reconocido = ""
    if consulta and not (curso or sede or periodo or modalidad):
        f = _filtros_desde_texto(consulta, filas)
        curso, sede, periodo, modalidad = f["curso"], f["sede"], f["periodo"], f["modalidad"]
        no_reconocido = f["no_reconocido"]

    def _filtrar(curso):
        return [f for f in filas
                if (_coincide(curso, f"{f['curso']} {f.get('categoria', '')} {f.get('publico', '')}") if curso else True)
                and _coincide_todo(sede, f["sede"]) and _coincide(periodo, f["periodo"])
                and _coincide(modalidad, f.get("modalidad", ""))]

    elegidas = _filtrar(curso)
    if not elegidas and consulta and curso:          # pregunta libre: si el curso deducido no existe, se relaja
        no_reconocido, curso = curso, ""
        elegidas = _filtrar(curso)
    filtro_txt = ", ".join(f"{k}: {v}" for k, v in
                           [("curso", curso), ("sede", sede), ("periodo", periodo), ("modalidad", modalidad)] if v)
    if not elegidas:
        periodos = sorted({f["periodo"] for f in filas})
        return {"error": f"SIN_RESULTADOS: el archivo de vacantes no tiene horarios para "
                         f"({filtro_txt or 'sin filtro'}). Periodos con información: {', '.join(periodos)}. "
                         "Deriva a cursosdearte@mali.pe."}
    fechas = sorted({f.get("actualizado_al", "") for f in elegidas if f.get("actualizado_al")})
    ejemplo = os.getenv("VACANTES_ES_EJEMPLO", "1").strip() not in {"0", "no", "false"}
    fuente = (f"Fuente: archivo de vacantes {archivo.name}" + (f" (actualizado al {fechas[-1]})" if fechas else "")
              + (" – datos de ejemplo para la demostración" if ejemplo else "")
              + ". La vacante se asegura solo al completar la inscripción en cursosdearte@mali.pe.")
    return {"con": [f for f in elegidas if f["vacantes_disponibles"] > 0],
            "llenos": [f for f in elegidas if f["vacantes_disponibles"] <= 0],
            "curso": curso, "filtro_txt": filtro_txt, "no_reconocido": no_reconocido, "fuente": fuente}


def consultar_vacantes(curso: str = "", sede: str = "", periodo: str = "", modalidad: str = "",
                       solo_con_vacantes: bool = False, consulta: str = "") -> str:
    """Consulta el archivo de vacantes y devuelve, por curso, sede y horario, cuántas vacantes quedan."""
    r = _seleccionar(curso, sede, periodo, modalidad, consulta)
    if "error" in r:
        return r["error"]
    con, llenos = r["con"], r["llenos"]
    con.sort(key=lambda f: (-f["vacantes_disponibles"] if not r["curso"] else 0, f["curso"], f["sede"]))
    lineas = []
    if r["no_reconocido"]:
        lineas.append(f"Nota: no hay un curso llamado «{r['no_reconocido']}» en el archivo de vacantes; "
                      "se muestran las vacantes de los cursos que sí tienen horarios.")
    lineas += [f"Vacantes ({r['filtro_txt'] or 'todos los periodos'}): {len(con)} horario(s) con vacantes, "
               f"{len(llenos)} lleno(s)."]
    for f in con[:MAX_FILAS]:
        lineas.append(f"- {f['curso']} | {f['sede']} | {f['horario']} | del {f.get('fecha_inicio', '-')} al {f.get('fecha_fin', '-')} | "
                      f"{f.get('publico', '')} | {f['vacantes_disponibles']} vacante(s) [{f['periodo']}]")
    if len(con) > MAX_FILAS:
        lineas.append(f"- … y {len(con) - MAX_FILAS} horario(s) más: pide filtrar por curso o sede.")
    if llenos and not solo_con_vacantes:
        lineas.append("Sin vacantes: " + "; ".join(f"{f['curso']} ({f['sede']}, {f['periodo']})" for f in llenos[:8]))
    lineas.append(r["fuente"])
    return "\n".join(lineas)


def vacantes_para_usuario(consulta: str) -> str:
    """Respuesta lista para el usuario, agrupada por curso, construida solo con las filas del archivo."""
    r = _seleccionar("", "", "", "", consulta)
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
                lineas.append(f"- **{f.get('codigo', '')}** · {f['sede']} · {f['horario']} · del {f.get('fecha_inicio', '-')} al {f.get('fecha_fin', '-')} "
                              f"({f['periodo']}) · {f.get('publico', '')} · {f['vacantes_disponibles']} vacante(s)")
            lineas.append("")
    if r["llenos"]:
        lineas.append("Sin vacantes (llenos): " + "; ".join(
            f"{f['curso']} – {f['sede']} ({f['periodo']})" for f in r["llenos"]))
    if r["con"]:
        lineas.append("\n¿Te gustaría inscribirte? Escribe el **código del horario**, por ejemplo: «inscribirme en "
                      f"{r['con'][0].get('codigo', '')}».")
    lineas.append("\n" + r["fuente"])
    return "\n".join(lineas).replace("\n\n\n", "\n\n")
