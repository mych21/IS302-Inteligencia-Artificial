# MALI Asistente Estudiantil (vacantes) – PC2 IS302 (UPC)
# Basado en la plantilla "agent-framework-agent-basic-responses" de Microsoft Foundry Toolkit.
#
# Agente local: Microsoft Agent Framework + Foundry Local (modelo Phi-4-mini) + servidor MCP propio
# (vacantes_mcp_server.py) que consulta el archivo local datos/vacantes.csv (data dummy).
#
# Ejecutar con Agent Inspector: F5 en VS Code (o `python main.py`), y probar en el inspector (puerto 8088).

import asyncio
import uuid
import json
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
import matricula  # noqa: E402
import vacantes  # noqa: E402

NOMBRE_AGENTE = "MALI Asistente Estudiantil"
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


def create_vacantes_mcp() -> MCPStdioTool:
    """Servidor MCP local del MALI, lanzado con el mismo intérprete de Python del agente."""
    return MCPStdioTool(
        name="mali-vacantes",
        command=sys.executable,
        args=[str(AQUI / "vacantes_mcp_server.py")],
        description="Vacantes disponibles de los cursos de MALI Educación (archivo local)",
        load_prompts=False,
        request_timeout=60,
        approval_mode="never_require",
    )


MARCA_CONTEXTO = "[INDICACIÓN INTERNA DEL SISTEMA]"


def respuesta_directa(pregunta: str) -> str | None:
    """Saludo, vacantes y pasos de la pre-inscripción: los responde el sistema directamente con los datos del
    archivo (sin el modelo), para que nunca se inventen ni se alteren cursos, horarios o vacantes."""
    if matricula.flujo_activo() or matricula.quiere_inscribirse(pregunta):
        return matricula.procesar_mensaje(pregunta)
    if matricula.es_saludo(pregunta):
        return matricula.PRESENTACION
    cursos = matricula.detectar_cursos(pregunta)
    if vacantes._pide_vacantes(pregunta) or cursos:
        if len(cursos) == 1:
            matricula.estado["ultimo_curso"] = cursos[0]
        return vacantes.vacantes_para_usuario(pregunta)
    return None


def contexto_para(pregunta: str) -> str:
    """Indicación para el modelo en los demás temas (proyecto, orientación o temas ajenos)."""
    return ("El mensaje no trata de vacantes ni de pre-inscripción. Si es sobre el proyecto o sobre orientación "
            "para estudiar, responde brevemente según tus instrucciones. No menciones cursos, horarios ni "
            "vacantes: si el usuario los necesita, invítalo a escribir «ver vacantes» o «quiero inscribirme». "
            "Si es ajeno a MALI Educación o al proyecto, di con amabilidad que solo ayudas con vacantes, "
            "pre-inscripción y el proyecto. No escribas una línea \"Fuente:\".")


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
async def inyectar_contexto(context, call_next):
    """1) Saludo, vacantes y pre-inscripción: respuesta directa del sistema con los datos del archivo.
    2) Otros temas (proyecto, orientación): Phi-4-mini redacta la respuesta siguiendo sus instrucciones."""
    msgs = context.messages
    idx = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i].role == "user"), None)
    pregunta = (msgs[idx].text or "").strip() if idx is not None else ""
    if not pregunta or MARCA_CONTEXTO in pregunta:
        await call_next()
        return
    directa = respuesta_directa(pregunta)
    if directa is not None:
        _fijar_respuesta(context, directa)
        return
    msgs[idx] = Message(role="user", contents=[f"{pregunta}\n\n{MARCA_CONTEXTO}\n{contexto_para(pregunta)}"])
    await call_next()


def create_agent(client: OpenAIChatCompletionClient, vacantes_mcp: MCPStdioTool, store: bool | None = False) -> Agent:
    kwargs = {"default_options": {"store": store}} if store is not None else {}
    return Agent(client=client, name=NOMBRE_AGENTE, instructions=INSTRUCCIONES_MALI, tools=[vacantes_mcp],
                 middleware=[inyectar_contexto], **kwargs)


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

    async with create_agent(client, create_vacantes_mcp()) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    main()
