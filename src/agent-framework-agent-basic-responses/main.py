# MALI Asistente – chatbot con IA para orientar a la comunidad educativa y proteger sus datos (IS302, UPC 2026-2)
# Basado en la plantilla "agent-framework-agent-basic-responses" de Microsoft Foundry Toolkit.
#
# Prototipo local: Microsoft Agent Framework + Foundry Local (Phi-4-mini) + servidor MCP propio (mali_mcp_server.py).
#  - asistente.py decide cómo se atiende cada mensaje (seguridad, perfiles, gestión de alumnos, vacantes, RAG).
#  - Solo las preguntas sobre la base general las redacta el modelo, con los fragmentos recuperados (RAG).
#  - Los datos de alumnos (base restringida) nunca se envían al modelo.
#
# Ejecutar con Agent Inspector: F5 en VS Code (o `python main.py`), y probar en el inspector (puerto 8088).

import asyncio
import uuid
import json
import re
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from agent_framework import (Agent, ChatResponse, ChatResponseUpdate, Content, MCPStdioTool, Message,
                             ResponseStream, chat_middleware)
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
from openai import AsyncOpenAI

AQUI = Path(__file__).resolve().parent
load_dotenv(AQUI / ".env")
sys.path.insert(0, str(AQUI))
import asistente  # noqa: E402

NOMBRE_AGENTE = "MALI Asistente"
INSTRUCCIONES_MALI = (AQUI / "instrucciones_agente.md").read_text(encoding="utf-8")


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

    return OpenAIChatCompletionClient(
        model=model,
        async_client=AsyncOpenAI(base_url=f"{endpoint.rstrip('/')}/v1", api_key="foundry-local"),
    )


def create_mali_mcp() -> MCPStdioTool:
    """Servidor MCP local: solo expone la base GENERAL y las vacantes (nunca datos de alumnos)."""
    return MCPStdioTool(
        name="mali-asistente",
        command=sys.executable,
        args=[str(AQUI / "mali_mcp_server.py")],
        description="Base de conocimiento general de MALI Educación y vacantes de demostración",
        load_prompts=False,
        request_timeout=60,
        approval_mode="never_require",
    )


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
    msgs[idx] = Message(role="user", contents=[f"{pregunta}\n\n{MARCA_CONTEXTO}\n{r.contexto}"])
    if context.stream:
        context.stream_transform_hooks.append(_hook_anti_repeticion())
    await call_next()
    if not context.stream and context.result is not None:
        for m in context.result.messages:
            for c in m.contents:
                if c.type == "text" and c.text:
                    c.text = recortar_repeticiones(c.text)


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


def _hook_anti_repeticion():
    """Transformación del streaming: muestra el texto a medida que llega, pero deja de mostrarlo en cuanto el
    modelo empieza a repetir una frase."""
    estado = {"recibido": "", "emitido": "", "cortado": False}

    def hook(update):
        if estado["cortado"] and getattr(update, "finish_reason", None) is not None:
            update.finish_reason = "stop"          # se cortó a propósito: la respuesta no queda «incompleta»
        textos = [c for c in update.contents if c.type == "text"]
        if not textos:
            return update
        otros = [c for c in update.contents if c.type != "text"]
        if estado["cortado"]:
            update.contents[:] = otros
            return update
        estado["recibido"] += "".join(c.text or "" for c in textos)
        permitido, cortado = texto_permitido(estado["recibido"])
        estado["cortado"] = cortado
        nuevo = permitido[len(estado["emitido"]):] if permitido.startswith(estado["emitido"]) else ""
        estado["emitido"] += nuevo
        textos[0].text = nuevo
        update.contents[:] = otros + [textos[0]]
        return update

    return hook


def create_agent(client: OpenAIChatCompletionClient, mali_mcp: MCPStdioTool, store: bool | None = False) -> Agent:
    # Temperatura moderada y respuestas cortas: reduce que el modelo pequeño entre en
    # bucles repitiendo párrafos (además, orquestar() corta cualquier repetición que llegue a producirse).
    opciones = {"temperature": 0.3, "max_tokens": 300}
    if store is not None:
        opciones["store"] = store
    return Agent(client=client, name=NOMBRE_AGENTE, instructions=INSTRUCCIONES_MALI, tools=[mali_mcp],
                 middleware=[orquestar], default_options=opciones)


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

    async with create_agent(client, create_mali_mcp()) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    main()
