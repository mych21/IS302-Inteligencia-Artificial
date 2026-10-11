import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mali_tools  # noqa: E402


class HerramientasMaliTests(unittest.TestCase):
    def test_busqueda_respaldada_con_fuente(self):
        r = mali_tools.buscar_informacion_mali("¿Qué cursos de baile tienen?")
        self.assertIn("Marinera Norteña", r)
        self.assertIn("Fuente:", r)

    def test_politica_de_inasistencias(self):
        r = mali_tools.buscar_informacion_mali("Si falto a una clase, ¿la puedo recuperar?")
        self.assertIn("no son recuperables", r)

    def test_fuera_de_alcance(self):
        self.assertTrue(mali_tools.buscar_informacion_mali("¿Quién ganó el mundial?").startswith("SIN_RESULTADOS"))

    def test_listar_oferta_por_categoria(self):
        self.assertIn("Violín", mali_tools.listar_oferta("música"))
        self.assertTrue(mali_tools.listar_oferta("astronomía").startswith("SIN_RESULTADOS"))

    def test_senal_de_apoyo_interna(self):
        alto = mali_tools.senal_de_apoyo(55, 10, 2, 0, 40, 0)
        bajo = mali_tools.senal_de_apoyo(92, 16, 0, 1, 85, 3)
        self.assertIn("Alto", alto)
        self.assertIn("Bajo", bajo)
        self.assertIn("revisión humana", alto)


class VacantesTests(unittest.TestCase):
    def test_vacantes_de_verano(self):
        r = mali_tools.buscar_informacion_mali("¿Cuáles son las vacantes disponibles del curso de verano?")
        self.assertIn("Verano 2027", r)
        self.assertIn("vacante(s)", r)
        self.assertIn("Fuente: archivo de vacantes", r)

    def test_filtro_por_curso_y_sede(self):
        r = mali_tools.consultar_vacantes(curso="baile", sede="San Miguel")
        self.assertIn("Kpop | San Miguel 1", r)
        self.assertNotIn("Arabiscos", r)

    def test_curso_que_no_esta_en_el_archivo(self):
        r = mali_tools.consultar_vacantes(consulta="vacantes de astronomía")
        self.assertIn("no hay un curso llamado", r)
        self.assertIn("vacante(s)", r)

    def test_pregunta_con_errores_de_tipeo(self):
        r = mali_tools.buscar_informacion_mali("necesito que me digas las vacantes dispoibles de los cursos")
        self.assertNotIn("SIN_RESULTADOS", r)
        self.assertNotIn("no hay un curso llamado", r)
        self.assertIn("vacante(s)", r)
        self.assertIn("Guitarra", mali_tools.consultar_vacantes(consulta="hay cupos de guitara?"))

    def test_archivo_configurable(self):
        with patch.dict(os.environ, {"VACANTES_ARCHIVO": "no_existe.csv"}):
            self.assertTrue(mali_tools.consultar_vacantes().startswith("SIN_RESULTADOS"))


class ConfiguracionAgenteTests(unittest.TestCase):
    def test_falta_modelo_local(self):
        try:
            import main
        except ImportError:
            self.skipTest("agent_framework no instalado en este entorno")
        with patch.dict(os.environ, {"FOUNDRY_LOCAL_MODEL": "  "}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "FOUNDRY_LOCAL_MODEL"):
                main.get_model_name()

    def test_servidor_mcp_usa_el_mismo_python(self):
        try:
            import main
        except ImportError:
            self.skipTest("agent_framework no instalado en este entorno")
        with patch.object(main, "MCPStdioTool") as tool:
            main.create_mali_mcp()
            kwargs = tool.call_args.kwargs
            self.assertEqual(kwargs["command"], sys.executable)
            self.assertTrue(kwargs["args"][0].endswith("mali_mcp_server.py"))


if __name__ == "__main__":
    unittest.main()
