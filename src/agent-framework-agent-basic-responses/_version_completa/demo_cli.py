"""
Demostración por consola del MALI Asistente Estudiantil (ideal para grabar el video de la PC2).

Uso:
    python demo_cli.py            # ejecuta las preguntas de demostración
    python demo_cli.py --chat     # conversación libre (escribe 'salir' para terminar)
"""
import asyncio
import sys
import time

from main import create_agent, create_local_client, create_mali_mcp, get_model_name

PREGUNTAS_DEMO = [
    # Funcionalidades básicas
    "¿Qué cursos de baile tienen?",
    "Si falto a una clase, ¿la puedo recuperar?",
    "¿Cuáles son las vacantes disponibles del curso de verano?",  # consulta el archivo local de vacantes
    "¿Cuánto cuesta el curso de guitarra?",                      # no inventa precios
    "Mi DNI es 45678912, ¿me puedes matricular en pintura?",     # privacidad + no toma decisiones
    # Funcionalidad avanzada (coordinación, vía MCP + modelo predictivo)
    "Soy de coordinación académica. Evalúa la señal de apoyo de un alumno con 58% de asistencia, "
    "promedio 10.5, 2 pagos atrasados, sin continuidad previa y 40% de cursos completados.",
]


async def preguntar(agent, pregunta: str) -> None:
    print(f"\n👤 {pregunta}")
    inicio = time.perf_counter()
    respuesta = await agent.run(pregunta)
    print(f"🤖 {respuesta.text}")
    print(f"   ({time.perf_counter() - inicio:.1f} s)")


async def main() -> None:
    client = create_local_client(model=get_model_name())
    async with create_agent(client, create_mali_mcp(), store=None) as agent:
        if "--chat" in sys.argv:
            while True:
                q = input("\n👤 Tú: ").strip()
                if q.lower() in {"salir", "exit", "quit"}:
                    break
                if q:
                    await preguntar(agent, q)
        else:
            for q in PREGUNTAS_DEMO:
                await preguntar(agent, q)


if __name__ == "__main__":
    asyncio.run(main())
