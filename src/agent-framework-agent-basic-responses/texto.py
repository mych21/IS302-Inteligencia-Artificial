"""Normalización de texto en español: minúsculas sin tildes, palabras vacías, sinónimos y detección de cursos."""
from __future__ import annotations

import difflib
import re
import unicodedata

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

PALABRAS_VACANTES = {"vacante", "vacantes", "cupo", "cupos", "disponibilidad", "disponible", "disponibles",
                     "lleno", "llenos", "quedan"}
GENERICAS_SEDE = {"sede", "principal", "virtual", "zoom", "1", "san", "la", "lo"}
RELLENO = {"dame", "da", "danos", "muestra", "muestrame", "lista", "listar", "listame", "ensename", "pasame",
           "necesito", "digas", "diga", "dime", "decir", "quiero", "quisiera", "saber", "conocer", "ver", "mostrar",
           "puedes", "podrias", "cuales", "cual", "son", "estan", "esta", "hay", "tienen", "tiene",
           "abiertas", "abiertos", "proximos", "proximas", "siguiente", "actuales", "todas", "todos", "ahora",
           "ayuda", "ayudame", "info", "porfa", "por", "favor", "consultar", "consulta", "existen", "cuantas"}
_NO_CURSO = {"arte", "artes", "y", "de", "al", "dance", "for", "pequeno", "pequena", "kids"}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9@\s]", " ", texto)


def tokens(texto: str, expandir: bool = False) -> list[str]:
    toks = [t for t in normalizar(texto).split() if t not in STOPWORDS and len(t) > 1]
    if expandir:
        toks += [s for t in toks if t in SINONIMOS for s in SINONIMOS[t].split()]
    return [t[:-1] if len(t) > 4 and t.endswith("s") else t for t in toks]   # singular simple


def conjunto(texto: str) -> set[str]:
    return set(tokens(texto, expandir=True))


def pide_vacantes(texto: str, periodos: set[str]) -> bool:
    """Pregunta por vacantes o por los cursos de un periodo del archivo («¿qué cursos hay en verano?»)."""
    palabras = set(normalizar(texto).split())
    if palabras & PALABRAS_VACANTES:
        return True
    claves = {t for p in periodos for t in normalizar(p).split() if not t.isdigit()}
    return bool(palabras & claves) and bool(palabras & {"curso", "cursos", "taller", "talleres", "horario",
                                                        "horarios", "clases", "hay", "dan", "ofrecen"})


def detectar_cursos(texto: str, horarios: list[dict]) -> list[str]:
    """Cursos del archivo de vacantes que menciona el texto (nombre exacto, palabra clave, categoría o error de
    tipeo)."""
    cursos = sorted({f["curso"] for f in horarios})
    norm = normalizar(texto)
    exactos = [c for c in cursos if normalizar(c).strip() in norm]
    if exactos:
        return exactos
    palabras = conjunto(texto)
    encontrados = set()
    for f in horarios:
        claves = conjunto(f["curso"]) - _NO_CURSO
        categoria = conjunto(f.get("categoria", "")) - _NO_CURSO
        for tok in palabras:
            if tok in claves or tok in categoria or difflib.get_close_matches(tok, claves, 1, 0.82):
                encontrados.add(f["curso"])
    return sorted(encontrados)
