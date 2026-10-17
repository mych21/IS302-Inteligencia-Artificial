import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matricula  # noqa: E402
import vacantes  # noqa: E402


class VacantesTests(unittest.TestCase):
    def test_vacantes_de_verano(self):
        r = vacantes.consultar_vacantes(consulta="¿Cuáles son las vacantes disponibles del curso de verano?")
        self.assertIn("Verano 2027", r)
        self.assertIn("Fuente: archivo de vacantes", r)

    def test_errores_de_tipeo(self):
        r = vacantes.consultar_vacantes(consulta="necesito que me digas las vacantes dispoibles de los cursos")
        self.assertNotIn("SIN_RESULTADOS", r)
        self.assertIn("Guitarra", vacantes.consultar_vacantes(consulta="hay cupos de guitara?"))

    def test_filtro_por_curso_y_sede(self):
        r = vacantes.consultar_vacantes(curso="baile", sede="San Miguel")
        self.assertIn("Kpop | San Miguel 1", r)
        self.assertNotIn("Arabiscos", r)

    def test_curso_que_no_existe(self):
        self.assertIn("no hay un curso llamado", vacantes.consultar_vacantes(consulta="vacantes de astronomía"))

    def test_archivo_no_encontrado(self):
        with patch.dict(os.environ, {"VACANTES_ARCHIVO": "no_existe.csv"}):
            self.assertTrue(vacantes.consultar_vacantes().startswith("SIN_RESULTADOS"))


class RespuestaUsuarioTests(unittest.TestCase):
    def test_solo_cursos_del_archivo(self):
        filas = vacantes._leer_vacantes()
        cursos_archivo = {f["curso"] for f in filas}
        r = vacantes.vacantes_para_usuario("necesito ver las vacantes disponibles por curso")
        mostrados = {l[2:l.index("**", 2)] for l in r.splitlines() if l.startswith("**")}
        self.assertTrue(mostrados)
        self.assertLessEqual(mostrados, cursos_archivo)
        self.assertEqual(mostrados, {f["curso"] for f in filas if f["vacantes_disponibles"] > 0})

    def test_teatro_no_trae_otros_cursos(self):
        r = vacantes.vacantes_para_usuario("vacantes de teatro")
        self.assertIn("Teatro y Actuación", r)
        self.assertNotIn("Dibujo y Pintura", r)


class MatriculaTests(unittest.TestCase):
    """Usa copias temporales: no modifica los archivos reales."""

    def setUp(self):
        import shutil
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(vacantes.ARCHIVO_VACANTES_DEFECTO, self.tmp / "vacantes.csv")
        self.env = patch.dict(os.environ, {"VACANTES_ARCHIVO": str(self.tmp / "vacantes.csv")})
        self.mat = patch.object(matricula, "ARCHIVO_MATRICULAS", self.tmp / "matriculas.csv")
        shutil.copy(matricula.ARCHIVO_PAGOS, self.tmp / "pagos.csv")
        self.pag = patch.object(matricula, "ARCHIVO_PAGOS", self.tmp / "pagos.csv")
        self.pag.start()
        import acceso
        shutil.copy(acceso.ALUMNOS, self.tmp / "alumnos.csv")
        self.alu = patch.object(acceso, "ALUMNOS", self.tmp / "alumnos.csv")
        self.alu.start()
        self.env.start()
        self.mat.start()
        matricula.reiniciar()

    def tearDown(self):
        self.env.stop()
        self.mat.stop()
        self.pag.stop()
        self.alu.stop()
        matricula.reiniciar()

    def test_saludo(self):
        self.assertTrue(matricula.es_saludo("¡Hola! ¿Quién eres y cómo puedes ayudarme?"))
        self.assertFalse(matricula.es_saludo("¿quién ganó el mundial?"))

    def test_pide_curso_antes_del_horario(self):
        r = matricula.procesar_mensaje("agéndame una vacante en un horario")
        self.assertIn("¿A qué curso", r)
        self.assertNotIn("vacante(s)", r)

    def test_flujo_completo_actualiza_archivos(self):
        matricula.procesar_mensaje("quiero inscribirme en dibujo y pintura")
        self.assertIn("necesito", matricula.procesar_mensaje("el segundo"))
        self.assertIn("Confirmas", matricula.procesar_mensaje("Ana Torres ana@correo.com"))
        r = matricula.procesar_mensaje("sí")
        self.assertIn("MAT-0001", r)
        filas, _, _ = matricula._leer_tabla()
        self.assertEqual(next(f for f in filas if f["codigo"] == "H20")["vacantes_disponibles"], "5")
        registro = (self.tmp / "matriculas.csv").read_text(encoding="utf-8")
        self.assertIn("Ana Torres", registro)
        self.assertIn("H20", registro)

    def test_cambiar_de_curso_a_mitad_del_flujo(self):
        self.assertIn("Taekwondo", matricula.procesar_mensaje("quisiera inscribirme en taekwondo"))
        r = matricula.procesar_mensaje("marinera norteña?")
        self.assertIn("horarios de Marinera Norteña", r)
        self.assertNotIn("nombre completo", r)

    def test_pago_completa_la_inscripcion(self):
        import acceso
        esperado = "ALU-{:04d}".format(max(int(a["id_alumno"][4:]) for a in acceso._alumnos()) + 1)
        for paso in ("quiero inscribirme en dibujo y pintura", "2", "Ana Torres ana@correo.com"):
            matricula.procesar_mensaje(paso)
        self.assertIn("código de pago", matricula.procesar_mensaje("sí"))
        self.assertIn("No reconocí", matricula.procesar_mensaje("12345"))
        r = matricula.procesar_mensaje("PAG-100002")
        self.assertIn("Matrícula completada", r)
        self.assertIn("Lun y Mié 18:00–20:00", r)
        self.assertIn("Matriculado", (self.tmp / "matriculas.csv").read_text(encoding="utf-8"))
        self.assertIn("PAG-100002,usado,MAT-0001", (self.tmp / "pagos.csv").read_text(encoding="utf-8"))
        self.assertIn(f"código de alumno** es **{esperado}", r)
        padron = (self.tmp / "alumnos.csv").read_text(encoding="utf-8")
        self.assertIn(f"{esperado},Ana Torres,ana@correo.com", padron)       # mismo código en el padrón de alumnos

    def test_pago_posterior_y_codigo_usado(self):
        for paso in ("quiero inscribirme en dibujo y pintura", "1", "Ana Torres ana@correo.com", "sí", "después"):
            r = matricula.procesar_mensaje(paso)
        self.assertIn("pendiente de pago", r)
        r = matricula.procesar_mensaje("pago MAT-0001 PAG-100001")
        self.assertIn("Matrícula completada", r)
        self.assertNotIn("Ana Torres", r)                 # pago posterior: no se muestra el nombre
        self.assertIn("ya tiene un pago", matricula.procesar_mensaje("pago MAT-0001 PAG-100003"))

    def test_cancelar_no_registra(self):
        matricula.procesar_mensaje("inscríbeme en guitarra")
        matricula.procesar_mensaje("cancelar")
        self.assertFalse((self.tmp / "matriculas.csv").exists())

    def test_horario_lleno_no_se_registra(self):
        self.assertTrue(matricula.registrar_matricula("H02", "Ana Torres", "ana@correo.com").startswith("ERROR"))


if __name__ == "__main__":
    unittest.main()
