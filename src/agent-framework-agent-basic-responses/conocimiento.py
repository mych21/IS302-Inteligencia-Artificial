"""
Base de conocimiento GENERAL de MALI Asistente (RAG: recuperación con BM25, solo librería estándar).

- Cada documento es un archivo .md en conocimiento/general/ con título, fuente, nivel de acceso, responsable y
  vigencia. Al editar, agregar o quitar un archivo, la siguiente consulta usa la versión vigente (se reindexa al
  detectar cambios): no hay que reentrenar nada.
- `buscar(consulta)` devuelve los fragmentos más relevantes con su fuente, o `None` si no hay información suficiente.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import vacantes as v

CARPETA = Path(__file__).resolve().parent / "conocimiento" / "general"
UMBRAL_RELEVANCIA = 3.0
COBERTURA_MINIMA = 0.4        # fracción de palabras de la pregunta que deben aparecer en los fragmentos


@dataclass
class Documento:
    id: str
    titulo: str
    coleccion: str
    fuente: str
    texto: str


_indice: dict = {"firma": None}


def _firma() -> tuple:
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in CARPETA.glob("*.md")))


def _campo(contenido: str, nombre: str) -> str:
    m = re.search(rf"^{nombre}: (.+)$", contenido, re.M)
    return m.group(1).strip() if m else ""


def _cargar() -> None:
    docs = []
    for p in sorted(CARPETA.glob("*.md")):
        c = p.read_text(encoding="utf-8")
        if _campo(c, "Nivel de acceso").lower() not in ("", "general"):
            continue                      # solo documentos de nivel general
        titulo = re.search(r"^# (.+)$", c, re.M).group(1).strip()
        cuerpo = c.split("\n\n", 1)[1].strip() if "\n\n" in c else ""
        docs.append(Documento(p.stem.split("_")[0], titulo, _campo(c, "Colección"), _campo(c, "Fuente"), cuerpo))
    tokens = [v._tokens(f"{d.titulo} {d.titulo} {d.coleccion} {d.texto}") for d in docs]
    _indice.update(firma=_firma(), docs=docs, tokens=tokens,
                   df=Counter(t for d in tokens for t in set(d)),
                   avgdl=sum(map(len, tokens)) / max(1, len(tokens)))


def documentos() -> list[Documento]:
    if _indice["firma"] != _firma():
        _cargar()
    return _indice["docs"]


def _bm25(consulta: list[str], k1: float = 1.4, b: float = 0.75) -> list[float]:
    n, puntajes = len(_indice["docs"]), []
    for doc in _indice["tokens"]:
        tf, s = Counter(doc), 0.0
        for t in set(consulta):
            if t in tf:
                idf = math.log(1 + (n - _indice["df"][t] + 0.5) / (_indice["df"][t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(doc) / _indice["avgdl"]))
        puntajes.append(s)
    return puntajes


def buscar(consulta: str, max_resultados: int = 2) -> list[tuple[Documento, float]] | None:
    """Fragmentos relevantes de la base general, o None si no hay información suficiente."""
    docs = documentos()
    puntajes = _bm25(v._tokens(consulta, expandir=True))
    orden = sorted(range(len(docs)), key=lambda i: -puntajes[i])
    elegidos = [(docs[i], puntajes[i]) for i in orden[:max_resultados] if puntajes[i] >= UMBRAL_RELEVANCIA]
    if len(elegidos) == 2 and elegidos[1][1] < 0.6 * elegidos[0][1]:
        elegidos = elegidos[:1]          # el segundo fragmento solo si también es relevante
    if elegidos and _cobertura(consulta, [docs.index(d) for d, _ in elegidos]) < COBERTURA_MINIMA:
        return None                      # el fragmento no cubre lo que se pregunta: no hay información suficiente
    return elegidos or None


def _cobertura(consulta: str, indices: list[int]) -> float:
    """Qué parte de la pregunta (palabras propias, o sus sinónimos) aparece en los fragmentos recuperados."""
    palabras = set(v._tokens(consulta))
    if not palabras:
        return 1.0
    presentes = set().union(*(set(_indice["tokens"][i]) for i in indices))
    cubiertas = 0
    for p in palabras:
        variantes = {p} | set(v._tokens(v.SINONIMOS.get(p, ""))) | set(v._tokens(v.SINONIMOS.get(p + "s", "")))
        cubiertas += bool(variantes & presentes)
    return cubiertas / len(palabras)


def documento_que_menciona(nombre: str) -> Documento | None:
    """Primer documento de la base general cuyo texto menciona el nombre (p. ej. un curso)."""
    clave = v._normalizar(nombre).strip()
    return next((d for d in documentos() if clave in v._normalizar(d.texto)), None)


def como_texto(resultados: list[tuple[Documento, float]]) -> str:
    return "\n\n".join(f"[{d.id}] {d.titulo}\n{d.texto}\nFuente: {d.fuente}" for d, _ in resultados)


def buscar_informacion(consulta: str) -> str:
    """Versión en texto (para la herramienta MCP)."""
    r = buscar(consulta)
    if not r:
        return ("SIN_RESULTADOS: no hay información suficiente en las fuentes autorizadas. Indica la limitación y "
                "orienta a cursosdearte@mali.pe o a https://educacion.mali.pe/.")
    return como_texto(r)
