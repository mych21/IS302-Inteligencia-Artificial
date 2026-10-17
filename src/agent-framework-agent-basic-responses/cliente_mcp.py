"""Cliente MCP del orquestador.

Inicia los dos servidores MCP del proyecto (servidor_general.py y servidor_restringido.py) como procesos locales
(transporte stdio) y ofrece `llamar(servidor, herramienta, **argumentos)`, una función síncrona que usan
asistente.py, matricula.py y acceso.py. Las conexiones viven en un hilo propio con su bucle de eventos, de modo que
se pueden usar tanto desde el servidor del agente como desde las pruebas.
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

AQUI = Path(__file__).resolve().parent
SERVIDORES = {"general": "servidor_general.py", "restringido": "servidor_restringido.py"}
_TIEMPO_MAXIMO = 60


class _Conexion:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.hilo = threading.Thread(target=self.loop.run_forever, name="cliente-mcp", daemon=True)
        self.hilo.start()
        self.sesiones: dict[str, ClientSession] = {}
        self.error: BaseException | None = None
        self.fin: asyncio.Event | None = None
        self.tarea = None
        asyncio.run_coroutine_threadsafe(self._abrir(), self.loop).result(_TIEMPO_MAXIMO)
        if self.error:
            self.cerrar()
            raise RuntimeError(f"No se pudieron iniciar los servidores MCP: {self.error}")

    async def _abrir(self) -> None:
        listo = asyncio.Event()
        self.fin = asyncio.Event()
        self.tarea = asyncio.create_task(self._mantener(listo))
        await listo.wait()

    async def _mantener(self, listo: asyncio.Event) -> None:
        """Abre y mantiene las sesiones en una sola tarea (así se cierran en el mismo contexto en que se abrieron)."""
        try:
            async with AsyncExitStack() as pila:
                for nombre, archivo in SERVIDORES.items():
                    parametros = StdioServerParameters(command=sys.executable, args=[str(AQUI / archivo)],
                                                       env=dict(os.environ), cwd=str(AQUI))
                    lectura, escritura = await pila.enter_async_context(stdio_client(parametros))
                    sesion = await pila.enter_async_context(ClientSession(lectura, escritura))
                    await sesion.initialize()
                    self.sesiones[nombre] = sesion
                listo.set()
                await self.fin.wait()
        except BaseException as e:            # noqa: BLE001 - se informa al hilo que pidió la conexión
            self.error = e
            listo.set()

    async def _llamar(self, servidor: str, herramienta: str, argumentos: dict) -> str:
        resultado = await self.sesiones[servidor].call_tool(herramienta, argumentos)
        texto = "".join(getattr(c, "text", "") for c in resultado.content)
        if getattr(resultado, "isError", False) or getattr(resultado, "is_error", False):
            raise RuntimeError(f"{servidor}.{herramienta}: {texto}")
        return texto

    def llamar(self, servidor: str, herramienta: str, argumentos: dict) -> str:
        futuro = asyncio.run_coroutine_threadsafe(self._llamar(servidor, herramienta, argumentos), self.loop)
        return futuro.result(_TIEMPO_MAXIMO)

    def cerrar(self) -> None:
        if self.fin is not None:
            self.loop.call_soon_threadsafe(self.fin.set)
            if self.tarea is not None:
                asyncio.run_coroutine_threadsafe(asyncio.wait([self.tarea]), self.loop).result(_TIEMPO_MAXIMO)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.hilo.join(5)


_conexion: _Conexion | None = None
_candado = threading.Lock()


def llamar(servidor: str, herramienta: str, **argumentos) -> str:
    """Ejecuta una herramienta de un servidor MCP y devuelve su texto."""
    global _conexion
    with _candado:
        if _conexion is None:
            _conexion = _Conexion()
    return _conexion.llamar(servidor, herramienta, argumentos)


def llamar_json(servidor: str, herramienta: str, **argumentos):
    return json.loads(llamar(servidor, herramienta, **argumentos))


def cerrar() -> None:
    """Detiene los servidores. La siguiente llamada los vuelve a iniciar (las pruebas lo usan al cambiar de datos)."""
    global _conexion
    with _candado:
        if _conexion is not None:
            _conexion.cerrar()
            _conexion = None


atexit.register(cerrar)
