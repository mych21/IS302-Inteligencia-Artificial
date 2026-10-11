# MALI Asistente Estudiantil – PC2 IS302 (UPC)
# Basado en la plantilla "agent-framework-agent-basic-responses" de Microsoft Foundry Toolkit.
#
# Agente local: Microsoft Agent Framework + Foundry Local (modelo Phi-4-mini) + servidor MCP propio
# (mali_mcp_server.py) con la información oficial de MALI Educación y la señal de apoyo del modelo predictivo.
#
# Ejecutar con Agent Inspector: F5 en VS Code (o `python main.py`), y probar en el inspector (puerto 8088).
# Probar por consola, sin servidor:  python demo_cli.py

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from agent_framework import Agent, MCPStdioTool, Message, chat_middleware
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
from openai import AsyncOpenAI

AQUI = Path(__file__).resolve().parent
load_dotenv(AQUI / ".env")
sys.path.insert(0, str(AQUI))
import mali_tools  # noqa: E402

NOMBRE_AGENTE = "MALI Asistente Estudiantil"
INSTRUCCIONES = (AQUI / "instrucciones_agente.md").read_text(encoding="utf-8")


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
    """Servidor MCP local del MALI, lanzado con el mismo intérprete de Python del agente."""
    return MCPStdioTool(
        name="mali-educacion",
        command=sys.executable,
        args=[str(AQUI / "mali_mcp_server.py")],
        description="Información oficial de MALI Educación y señal de apoyo para coordinación",
        load_prompts=False,
        request_timeout=60,
        approval_mode="never_require",
    )


MARCA_CONTEXTO = "[CONTEXTO RECUPERADO DE LAS FUENTES DEL MALI]"


def contexto_para(pregunta: str) -> str:
    """Recupera el contexto de la pregunta: vacantes (archivo local) o información oficial (BM25)."""
    if mali_tools._pide_vacantes(pregunta):
        return mali_tools.consultar_vacantes(consulta=pregunta)
    return mali_tools.buscar_informacion_mali(pregunta, max_resultados=3)


@chat_middleware
async def inyectar_contexto(context, call_next):
    """RAG garantizado: antes de llamar al modelo local, adjunta a la última pregunta del usuario el resultado
    de las herramientas. Así el agente responde con los datos aunque el modelo pequeño no llame a la
    herramienta por su cuenta (las herramientas MCP siguen disponibles para preguntas más específicas)."""
    msgs = context.messages
    if not any(MARCA_CONTEXTO in (m.text or "") for m in msgs):
        idx = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i].role == "user"), None)
        pregunta = (msgs[idx].text or "").strip() if idx is not None else ""
        if pregunta:
            msgs[idx] = Message(role="user", contents=[
                f"{pregunta}\n\n{MARCA_CONTEXTO}\n{contexto_para(pregunta)}\n\n"
                "Responde la pregunta usando SOLO este contexto. Si empieza con SIN_RESULTADOS, di que no tienes "
                "ese dato y deriva a cursosdearte@mali.pe. Termina con la línea \"Fuente:\" del contexto."])
    await call_next()


def create_agent(client: OpenAIChatCompletionClient, mali_mcp: MCPStdioTool, store: bool | None = False) -> Agent:
    kwargs = {"default_options": {"store": store}} if store is not None else {}
    return Agent(client=client, name=NOMBRE_AGENTE, instructions=INSTRUCCIONES, tools=[mali_mcp],
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

    async with create_agent(client, create_mali_mcp()) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    main()
