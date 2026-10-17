# MALI Asistente – chatbot con IA para orientar a la comunidad educativa y proteger sus datos (IS302, UPC 2026-2)
# Basado en la plantilla "agent-framework-agent-basic-responses" de Microsoft Foundry Toolkit.
#
# Prototipo local: Microsoft Agent Framework + Foundry Local (Phi-4-mini) + dos servidores MCP propios.
#  - asistente.py decide cómo se atiende cada mensaje (seguridad, perfiles, gestión de alumnos, vacantes, RAG).
#  - Los datos se leen y registran a través de los servidores MCP (servidor_general.py y servidor_restringido.py).
#  - Solo las preguntas sobre la base general las redacta el modelo, con los fragmentos recuperados (RAG).
#  - Los datos de alumnos (servidor restringido) nunca se envían al modelo.
#
# Ejecutar con Agent Inspector: F5 en VS Code (o `python main.py`), y probar en el inspector (puerto 8088).

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from agent_framework import (Agent, ChatResponse, ChatResponseUpdate, Content, Message, ResponseStream,
                             chat_middleware)
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
from openai import AsyncOpenAI

AQUI = Path(__file__).resolve().parent
load_dotenv(AQUI / ".env")
sys.path.insert(0, str(AQUI))
import asistente  # noqa: E402

NOMBRE_AGENTE = "MALI Asistente"
INSTRUCCIONES_MALI = (AQUI / "instrucciones_agente.md").read_text(encoding="utf-8")


MODELO_LOCAL: dict = {}        # cliente OpenAI del endpoint local de Foundry y nombre del modelo


def create_local_client(model: str) -> OpenAIChatCompletionClient:
    """Inicia Foundry Local, carga el modelo y devuelve un cliente OpenAI apuntando al endpoint local."""
    executable = shutil.which("foundry")
    if not executable:
        raise RuntimeError("Foundry Local CLI is not installed or not on PATH.")

    subprocess.run([executable, "server", "start"], check=True)
    subprocess.run([executable, "model", "load", model], check=True)
    status = json.loads(
        subprocess.check_output([executable, "server", "status", "--output", "json"], encoding="utf-8")
    )
    urls = status.get("webUrls")
    if not status.get("running") or not isinstance(urls, list) or not urls:
        raise RuntimeError("Foundry Local did not report a running HTTP server.")
    endpoint = urls[0]
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("Foundry Local endpoint must be a loopback HTTP address.")

    async_client = AsyncOpenAI(base_url=f"{endpoint.rstrip('/')}/v1", api_key="foundry-local")
    MODELO_LOCAL.update(cliente=async_client, modelo=model)
    return OpenAIChatCompletionClient(model=model, async_client=async_client)


MARCA_CONTEXTO = "[INDICACIÓN INTERNA DEL SISTEMA]"


def _fijar_respuesta(context, texto: str) -> None:
    """Entrega `texto` como respuesta del asistente sin llamar al modelo (funciona con y sin streaming)."""
    ids = {"response_id": f"resp_{uuid.uuid4().hex}", "message_id": f"msg_{uuid.uuid4().hex}"}
    if context.stream:
        async def _actualizaciones():
            yield ChatResponseUpdate(contents=[Content.from_text(text=texto)], role="assistant",
                                     finish_reason="stop", **ids)
        context.result = ResponseStream(_actualizaciones(), finalizer=ChatResponse.from_updates)
    else:
        context.result = ChatResponse(messages=[Message(role="assistant", contents=[texto],
                                                        message_id=ids["message_id"])],
                                      response_id=ids["response_id"], finish_reason="stop")


@chat_middleware
async def orquestar(context, call_next):
    """Pasa cada mensaje por asistente.responder():
    - si el sistema ya tiene la respuesta (seguridad, perfiles, gestión, vacantes, pre-inscripción, sin información),
      se entrega directamente;
    - si es una consulta a la base general, se adjuntan los fragmentos recuperados y Phi-4-mini redacta (RAG)."""
    msgs = context.messages
    idx = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i].role == "user"), None)
    pregunta = (msgs[idx].text or "").strip() if idx is not None else ""
    if not pregunta or MARCA_CONTEXTO in pregunta:
        await call_next()
        return
    r = asistente.responder(pregunta)
    for i, m in enumerate(msgs):         # el modelo nunca ve mensajes con contraseñas del historial
        if m.role == "user" and i != idx and asistente.ocultar_si_sensible(m.text or "") != (m.text or ""):
            msgs[i] = Message(role="user", contents=[asistente.ocultar_si_sensible(m.text or "")])
    if r.texto is not None:
        _fijar_respuesta(context, r.texto)
        return
    _fijar_respuesta(context, await redactar_con_modelo(pregunta, r) + r.pie)


async def redactar_con_modelo(pregunta: str, r) -> str:
    """RAG: Phi-4-mini redacta la respuesta con los fragmentos recuperados. La llamada es directa (sin streaming)
    para poder revisar el texto antes de mostrarlo: se cortan repeticiones, se asegura la línea «Fuente:» y, si el
    modelo falla o no responde, se entrega el fragmento recuperado tal cual."""
    cliente = MODELO_LOCAL.get("cliente")
    texto = ""
    if cliente is not None:
        try:
            resp = await cliente.chat.completions.create(
                model=MODELO_LOCAL["modelo"], temperature=0.3, max_tokens=250,
                messages=[{"role": "system", "content": INSTRUCCIONES_MALI},
                          {"role": "user", "content": f"{pregunta}\n\n{MARCA_CONTEXTO}\n{r.contexto}"}])
            texto = (resp.choices[0].message.content or "").strip()
            if resp.choices[0].finish_reason == "length":       # se quedó sin espacio: hasta la última oración
                corte = max(texto.rfind(". "), texto.rfind(".\n"), texto.rfind("."))
                texto = texto[:corte + 1] if corte > 0 else texto
        except Exception:                                       # modelo no disponible: respuesta extractiva
            texto = ""
    texto = recortar_repeticiones(texto)
    fuente = r.respaldo.rsplit("Fuente:", 1)[-1].strip() if "Fuente:" in r.respaldo else ""
    if len(texto) < 20:
        return r.respaldo
    if "Fuente:" not in texto and fuente:
        texto += f"\n\nFuente: {fuente}"
    return texto


_FRASE = re.compile(r"(?<=[.!?:])\s+|\n+")


def _clave(frase: str) -> str:
    return re.sub(r"\W+", " ", frase.lower()).strip()


def texto_permitido(texto: str) -> tuple[str, bool]:
    """Parte del texto que se puede mostrar. Corta donde el modelo empieza a repetir una frase ya escrita
    (bucle de repetición) y retiene la frase en curso si empieza igual que una anterior. Devuelve (texto, cortado)."""
    vistas, inicio = set(), 0
    cortes = [m.end() for m in _FRASE.finditer(texto)]
    for fin in cortes:
        clave = _clave(texto[inicio:fin])
        if len(clave) >= 25 and clave in vistas:
            return texto[:inicio].rstrip(), True
        if clave:
            vistas.add(clave)
        inicio = fin
    resto = _clave(texto[inicio:])
    if resto and any(v.startswith(resto) or resto.startswith(v) for v in vistas if len(v) >= 25):
        if any(resto.startswith(v) for v in vistas if len(v) >= 25) or len(resto) >= 40:
            return texto[:inicio].rstrip(), True
        return texto[:inicio], False                 # se retiene hasta saber si es una repetición
    return texto, False


def recortar_repeticiones(texto: str) -> str:
    permitido, cortado = texto_permitido(texto)
    return permitido if cortado else texto


def create_agent(client: OpenAIChatCompletionClient, store: bool | None = False) -> Agent:
    # Temperatura moderada y respuestas cortas: reduce que el modelo pequeño entre en
    # bucles repitiendo párrafos (además, orquestar() corta cualquier repetición que llegue a producirse).
    opciones = {"temperature": 0.3, "max_tokens": 300}
    if store is not None:
        opciones["store"] = store
    return Agent(client=client, name=NOMBRE_AGENTE, instructions=INSTRUCCIONES_MALI, middleware=[orquestar],
                 default_options=opciones)


def get_model_name() -> str:
    model_name = os.getenv("FOUNDRY_LOCAL_MODEL", "").strip()
    if not model_name:
        raise RuntimeError("Local model is not configured. Set FOUNDRY_LOCAL_MODEL.")
    return model_name


def main():
    client = create_local_client(model=get_model_name())
    asyncio.run(serve_agent(client))


async def serve_agent(client: OpenAIChatCompletionClient) -> None:
    from agent_framework_foundry_hosting import ResponsesHostServer

    async with create_agent(client) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    main()
