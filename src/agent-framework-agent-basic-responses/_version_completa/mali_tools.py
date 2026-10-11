"""
Herramientas del MALI Asistente Estudiantil (sin dependencias externas: solo librería estándar).

Las expone el servidor MCP local (mali_mcp_server.py) para que el agente las use:
  - buscar_informacion_mali: búsqueda BM25 en la base de conocimiento oficial (carpeta conocimiento/).
  - listar_oferta: cursos y programas publicados por categoría.
  - canales_de_atencion: correos y enlaces oficiales.
  - consultar_vacantes: vacantes disponibles por curso, sede y periodo (archivo datos/vacantes.csv).
  - senal_de_apoyo: señal de acompañamiento (uso interno) con el modelo predictivo del proyecto.
"""
from __future__ import annotations

import csv
import difflib
import json
import math
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CARPETA_KB = AQUI / "conocimiento"
MODELO_JSON = AQUI / "modelo" / "modelo_senal_apoyo.json"
ARCHIVO_VACANTES_DEFECTO = AQUI / "datos" / "vacantes.csv"
UMBRAL_RELEVANCIA = 2.0

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
}

CATEGORIAS = {
    "artes plasticas": "Cursos de artes plásticas", "artes vocales": "Cursos de artes vocales",
    "bailes": "Cursos de bailes y danzas", "artes escenicas": "Cursos de artes escénicas",
    "artes graficas": "Cursos de artes gráficas", "artes marciales": "Cursos de artes marciales",
    "musica": "Cursos de artes musicales", "extension profesional": "Programas",
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


def _cargar_secciones():
    secciones = []
    for archivo in sorted(CARPETA_KB.glob("*.md")):
        contenido = archivo.read_text(encoding="utf-8")
        documento = re.search(r"^# (.+)$", contenido, re.M).group(1).strip()
        fuente = re.search(r"^Fuentes?: (.+)$", contenido, re.M).group(1).strip()
        for bloque in re.split(r"^## ", contenido, flags=re.M)[1:]:
            titulo, _, cuerpo = bloque.partition("\n")
            secciones.append({"documento": documento, "titulo": titulo.strip(),
                              "texto": cuerpo.strip(), "fuente": fuente})
    return secciones


SECCIONES = _cargar_secciones()
_DOCS = [_tokens(f"{s['titulo']} {s['titulo']} {s['texto']}") for s in SECCIONES]
_DF = Counter(t for d in _DOCS for t in set(d))
_AVGDL = sum(map(len, _DOCS)) / len(_DOCS)


def _bm25(consulta: list[str], k1: float = 1.4, b: float = 0.75) -> list[float]:
    n = len(_DOCS)
    puntajes = []
    for doc in _DOCS:
        tf = Counter(doc)
        s = 0.0
        for t in set(consulta):
            if t in tf:
                idf = math.log(1 + (n - _DF[t] + 0.5) / (_DF[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(doc) / _AVGDL))
        puntajes.append(s)
    return puntajes


def buscar_informacion_mali(consulta: str, max_resultados: int = 2) -> str:
    """Busca en la información oficial de MALI Educación y devuelve los fragmentos más relevantes con su fuente."""
    if _pide_vacantes(consulta):        # las vacantes viven en un archivo aparte: se responde desde ahí
        return consultar_vacantes(consulta=consulta)
    puntajes = _bm25(_tokens(consulta, expandir=True))
    orden = sorted(range(len(SECCIONES)), key=lambda i: -puntajes[i])
    elegidos = [i for i in orden[:max_resultados] if puntajes[i] >= UMBRAL_RELEVANCIA]
    if not elegidos:
        return ("SIN_RESULTADOS: no hay información sobre esa consulta en las fuentes oficiales de MALI Educación. "
                "Indica al usuario que no tienes ese dato y deriva a cursosdearte@mali.pe o a la sección "
                "«Cursos y horarios» de https://educacion.mali.pe/.")
    partes = []
    for i in elegidos:
        s = SECCIONES[i]
        partes.append(f"### {s['titulo']}\n{s['texto']}\nFuente: {s['fuente']}")
    return "\n\n".join(partes)


def listar_oferta(categoria: str = "") -> str:
    """Lista los cursos y programas publicados. Categorías: artes plásticas, artes vocales, bailes, artes escénicas,
    artes gráficas, artes marciales, música, extensión profesional. Vacío = resumen de todas."""
    cat = _normalizar(categoria).strip()
    filas = []
    for s in SECCIONES:
        if not s["documento"].startswith(("Oferta", "Extensión")) or ":" not in s["texto"] or ";" not in s["texto"]:
            continue
        clave = next((k for k, pref in CATEGORIAS.items() if s["titulo"].startswith(pref)), None)
        if cat and not (clave and (cat in clave or clave in cat or
                                   (clave == "extension profesional" and "extension" in cat))):
            continue
        intro, _, lista = s["texto"].partition(":")
        items = [x.strip(" .") for x in lista.split(";") if x.strip(" .")]
        filas.append(f"{intro.strip()}: " + "; ".join(items))
    if not filas:
        return "SIN_RESULTADOS: categoría no encontrada. Categorías válidas: " + ", ".join(CATEGORIAS)
    return "\n".join(filas) + "\nFuente: https://educacion.mali.pe/ (consultado el 10/10/2026)"


def canales_de_atencion() -> str:
    """Devuelve los canales oficiales de atención de MALI Educación."""
    return "\n".join(f"- {s['titulo']}: {s['texto']}" for s in SECCIONES if s["documento"].startswith("Canales")) + \
        "\nFuente: https://educacion.mali.pe/ y https://www.mali.pe/ (consultado el 10/10/2026)"


# ------------------------------------------------------------------ vacantes (archivo CSV)
PALABRAS_VACANTES = {"vacante", "vacantes", "cupo", "cupos", "disponibilidad", "disponible", "disponibles",
                     "lleno", "llenos", "quedan", "queda"}
_GENERICAS_SEDE = {"sede", "principal", "virtual", "zoom", "1", "san", "la", "lo"}
_GENERICAS_CONSULTA = {"curso", "cursos", "taller", "tallere", "clase", "horario", "programa", "periodo", "temporada",
                       "inscripcion", "inscribir", "matricula", "hay", "cuanta", "cuanto", "ver", "todo", "toda",
                       "informacion", "dato", "lista", "mostrar", "muestrame", "dime", "necesito", "busco"}
_RELLENO = {"necesito", "digas", "diga", "dime", "decir", "quiero", "quisiera", "saber", "conocer", "ver", "mostrar",
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
    return bool(set(_normalizar(texto).split()) & PALABRAS_VACANTES)


def _coincide(filtro: str, campo: str) -> bool:
    """Coincidencia flexible: sin tildes, mayúsculas ni plurales, y con sinónimos (baile → danzas, etc.)."""
    if not filtro.strip():
        return True
    if _normalizar(filtro).strip() in _normalizar(campo):
        return True
    return bool(_set(filtro) & _set(campo))


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
            for tok in _set(f"{f['curso']} {f.get('categoria', '')} {f.get('publico', '')}") - {"arte", "artes", "ano", "edad"}:
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


def consultar_vacantes(curso: str = "", sede: str = "", periodo: str = "", modalidad: str = "",
                       solo_con_vacantes: bool = False, consulta: str = "") -> str:
    """Consulta el archivo de vacantes y devuelve, por curso, sede y horario, cuántas vacantes quedan."""
    archivo = _archivo_vacantes()
    try:
        filas = _leer_vacantes()
    except FileNotFoundError:
        return (f"SIN_RESULTADOS: no se encontró el archivo de vacantes ({archivo.name}). "
                "Deriva a cursosdearte@mali.pe.")
    no_reconocido = ""
    if consulta and not (curso or sede or periodo or modalidad):
        f = _filtros_desde_texto(consulta, filas)
        curso, sede, periodo, modalidad = f["curso"], f["sede"], f["periodo"], f["modalidad"]
        no_reconocido = f["no_reconocido"]

    elegidas = [f for f in filas
                if (_coincide(curso, f"{f['curso']} {f.get('categoria', '')} {f.get('publico', '')}") if curso else True)
                and _coincide_todo(sede, f["sede"]) and _coincide(periodo, f["periodo"])
                and _coincide(modalidad, f.get("modalidad", ""))]
    filtro_txt = ", ".join(f"{k}: {v}" for k, v in
                           [("curso", curso), ("sede", sede), ("periodo", periodo), ("modalidad", modalidad)] if v)
    if not elegidas:
        periodos = sorted({f["periodo"] for f in filas})
        return (f"SIN_RESULTADOS: el archivo de vacantes no tiene horarios para ({filtro_txt or 'sin filtro'}). "
                f"Periodos con información: {', '.join(periodos)}. Deriva a cursosdearte@mali.pe.")

    con = [f for f in elegidas if f["vacantes_disponibles"] > 0]
    llenos = [f for f in elegidas if f["vacantes_disponibles"] <= 0]
    con.sort(key=lambda f: (-f["vacantes_disponibles"] if not curso else 0, f["curso"], f["sede"]))
    lineas = []
    if no_reconocido:
        lineas.append(f"Nota: no hay un curso llamado «{no_reconocido}» en el archivo de vacantes; "
                      "se muestran las vacantes de los cursos que sí tienen horarios.")
    lineas += [f"Vacantes ({filtro_txt or 'todos los periodos'}): {len(con)} horario(s) con vacantes, "
              f"{len(llenos)} lleno(s)."]
    for f in con[:MAX_FILAS]:
        lineas.append(f"- {f['curso']} | {f['sede']} | {f['horario']} | inicio {f.get('fecha_inicio', '-')} | "
                      f"{f.get('publico', '')} | {f['vacantes_disponibles']} vacante(s) [{f['periodo']}]")
    if len(con) > MAX_FILAS:
        lineas.append(f"- … y {len(con) - MAX_FILAS} horario(s) más: pide filtrar por curso o sede.")
    if llenos and not solo_con_vacantes:
        lineas.append("Sin vacantes: " + "; ".join(f"{f['curso']} ({f['sede']}, {f['periodo']})" for f in llenos[:8]))
    fechas = sorted({f.get("actualizado_al", "") for f in elegidas if f.get("actualizado_al")})
    ejemplo = os.getenv("VACANTES_ES_EJEMPLO", "1").strip() not in {"0", "no", "false"}
    lineas.append(f"Fuente: archivo de vacantes {archivo.name}"
                  + (f" (actualizado al {fechas[-1]})" if fechas else "")
                  + (" – datos de ejemplo para la demostración" if ejemplo else "")
                  + ". La vacante se asegura solo al completar la inscripción en cursosdearte@mali.pe.")
    return "\n".join(lineas)


# ------------------------------------------------------------------ señal de apoyo (modelo predictivo)
_PARAMS = json.loads(MODELO_JSON.read_text(encoding="utf-8"))
_FACTORES = [
    ("Porcentaje_Asistencia", lambda v: v < 70, "asistencia menor al 70 %"),
    ("Promedio_Evaluaciones", lambda v: v < 12, "promedio menor a 12"),
    ("Pagos_Atrasados", lambda v: v >= 2, "dos o más incidencias de pago"),
    ("Continuidad_Previa", lambda v: v == 0, "sin continuidad previa"),
    ("Porcentaje_Cursos_Completados", lambda v: v < 50, "menos de la mitad de cursos previos completados"),
]


def probabilidad_no_continuar(alumno: dict) -> float:
    p = _PARAMS
    x = []
    for col in p["numericas"]:
        v = alumno.get(col)
        v = p["medianas"][col] if v is None else float(v)
        x.append((v - p["medias"][col]) / p["escalas"][col])
    tipo = alumno.get("Tipo_Programa") or p["moda_tipo_programa"]
    x += [1.0 if tipo == c else 0.0 for c in p["categorias_tipo_programa"]]
    z = p["intercepto"] + sum(c * v for c, v in zip(p["coeficientes"], x))
    return 1 - 1 / (1 + math.exp(-z))          # probabilidad de clase 0 (no continúa)


def senal_de_apoyo(porcentaje_asistencia: float, promedio_evaluaciones: float, pagos_atrasados: int = 0,
                   continuidad_previa: int = 0, porcentaje_cursos_completados: float = 60.0,
                   numero_cursos_previos: int = 1, numero_inasistencias: int | None = None,
                   edad: int | None = None, tipo_programa: str = "Curso") -> str:
    """USO INTERNO para coordinación académica. Estima una señal de acompañamiento (Bajo/Medio/Alto) con el modelo
    predictivo del proyecto. No es una decisión: requiere revisión humana y no debe comunicarse al estudiante."""
    alumno = {
        "Edad": edad, "Numero_Cursos_Previos": numero_cursos_previos,
        "Porcentaje_Asistencia": porcentaje_asistencia, "Promedio_Evaluaciones": promedio_evaluaciones,
        "Pagos_Atrasados": pagos_atrasados, "Porcentaje_Cursos_Completados": porcentaje_cursos_completados,
        "Numero_Inasistencias": numero_inasistencias, "Continuidad_Previa": continuidad_previa,
        "Tipo_Programa": tipo_programa.capitalize() if tipo_programa else None,
    }
    p = probabilidad_no_continuar(alumno)
    u = _PARAMS["umbrales"]
    nivel = "Alto" if p >= u["Alto"] else ("Medio" if p >= u["Medio"] else "Bajo")
    factores = [d for col, regla, d in _FACTORES if alumno.get(col) is not None and regla(float(alumno[col]))]
    return (f"[USO INTERNO – requiere revisión humana] Señal de acompañamiento: {nivel} "
            f"(probabilidad estimada de no continuar: {p:.0%}). "
            f"Factores observables: {', '.join(factores) if factores else 'ninguno destacado'}. "
            + ("Sugerencia: que coordinación contacte al alumno y ofrezca apoyo. " if nivel != "Bajo"
               else "Sugerencia: seguimiento regular, sin acción adicional. ")
            + "No comunicar esta etiqueta al estudiante. Modelo entrenado con datos sintéticos del proyecto "
            "(no son datos reales del MALI).")
