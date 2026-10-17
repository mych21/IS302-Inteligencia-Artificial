import unittest

import entorno
import datos_restringidos as dr
import matricula
import vacantes


class VacantesTests(unittest.TestCase):
    def setUp(self):
        entorno.preparar()

    def test_vacantes_de_verano(self):
        r = vacantes.vacantes_para_usuario("¿Cuáles son las vacantes disponibles del curso de verano?")
        self.assertIn("Verano 2027", r)
        self.assertIn("Fuente: archivo de vacantes", r)

    def test_errores_de_tipeo(self):
        r = vacantes.vacantes_para_usuario("necesito que me digas las vacantes dispoibles de los cursos")
        self.assertIn("Estas son las vacantes", r)
        self.assertIn("Guitarra", vacantes.vacantes_para_usuario("hay cupos de guitara?"))

    def test_filtro_por_curso_y_sede(self):
        r = vacantes.vacantes_para_usuario("vacantes de baile en San Miguel")
        self.assertIn("San Miguel 1", r)
        self.assertNotIn("Arabiscos", r)

    def test_curso_que_no_existe(self):
        self.assertIn("No tengo un curso llamado", vacantes.vacantes_para_usuario("vacantes de astronomía"))

    def test_solo_cursos_del_archivo(self):
        filas = vacantes.horarios()
        r = vacantes.vacantes_para_usuario("necesito ver las vacantes disponibles por curso")
        mostrados = {linea[2:linea.index("**", 2)] for linea in r.splitlines() if linea.startswith("**")}
        self.assertEqual(mostrados, {f["curso"] for f in filas if f["vacantes_disponibles"] > 0})

    def test_teatro_no_trae_otros_cursos(self):
        r = vacantes.vacantes_para_usuario("vacantes de teatro")
        self.assertIn("Teatro y Actuación", r)
        self.assertNotIn("Dibujo y Pintura", r)


class MatriculaTests(unittest.TestCase):
    """La conversación usa los servidores MCP sobre la copia de los datos."""

    def setUp(self):
        self.copia = entorno.preparar()
        matricula.reiniciar()

    def tearDown(self):
        matricula.reiniciar()

    def _archivo(self, nombre: str) -> str:
        carpeta = "datos" if nombre == "pagos_demo.csv" else "restringido"
        return (self.copia / carpeta / nombre).read_text(encoding="utf-8")

    def test_saludo(self):
        self.assertTrue(matricula.es_saludo("¡Hola! ¿Quién eres y cómo puedes ayudarme?"))
        self.assertFalse(matricula.es_saludo("¿quién ganó el mundial?"))

    def test_pide_curso_antes_del_horario(self):
        r = matricula.procesar_mensaje("agéndame una vacante en un horario")
        self.assertIn("¿A qué curso", r)
        self.assertNotIn("vacante(s)", r)

    def test_flujo_completo_actualiza_archivos(self):
        antes = next(f for f in vacantes.horarios() if f["codigo"] == "H20")["vacantes_disponibles"]
        matricula.procesar_mensaje("quiero inscribirme en dibujo y pintura")
        self.assertIn("necesito", matricula.procesar_mensaje("el segundo"))
        self.assertIn("Confirmas", matricula.procesar_mensaje("Ana Torres, DNI 45678912, teléfono 987654321, ana@correo.com"))
        self.assertIn("MAT-0001", matricula.procesar_mensaje("sí"))
        despues = next(f for f in vacantes.horarios() if f["codigo"] == "H20")["vacantes_disponibles"]
        self.assertEqual(despues, antes - 1)
        self.assertIn("Ana Torres", self._archivo("matricula.csv"))

    def test_cambiar_de_curso_a_mitad_del_flujo(self):
        self.assertIn("Taekwondo", matricula.procesar_mensaje("quisiera inscribirme en taekwondo"))
        r = matricula.procesar_mensaje("marinera norteña?")
        self.assertIn("horarios de Marinera Norteña", r)
        self.assertNotIn("nombre completo", r)

    def test_pago_completa_la_inscripcion(self):
        for paso in ("quiero inscribirme en dibujo y pintura", "2",
                     "Ana Torres, DNI 45678912, teléfono 987654321, ana@correo.com"):
            matricula.procesar_mensaje(paso)
        self.assertIn("código de pago", matricula.procesar_mensaje("sí"))
        self.assertIn("No reconocí", matricula.procesar_mensaje("12345"))
        r = matricula.procesar_mensaje("PAG-100002")
        self.assertIn("Matrícula completada", r)
        self.assertIn("Lun y Mié 18:00–20:00", r)
        self.assertIn("código de alumno** es **ALU-0201", r)
        self.assertIn("PAG-100002,usado,MAT-0001", self._archivo("pagos_demo.csv"))
        self.assertIn("ALU-0201,Ana Torres,45678912,987654321,ana@correo.com", self._archivo("alumnos_sinteticos.csv"))

    def test_pago_posterior_y_codigo_usado(self):
        for paso in ("quiero inscribirme en dibujo y pintura", "1",
                     "Ana Torres, DNI 45678912, teléfono 987654321, ana@correo.com", "sí", "después"):
            r = matricula.procesar_mensaje(paso)
        self.assertIn("pendiente de pago", r)
        r = matricula.procesar_mensaje("pago MAT-0001 PAG-100001")
        self.assertIn("Matrícula completada", r)
        self.assertNotIn("Ana Torres", r)                 # pago posterior: no se muestra el nombre
        self.assertIn("ya tiene un pago", matricula.procesar_mensaje("pago MAT-0001 PAG-100003"))

    def test_pago_no_conciliado_queda_por_confirmar(self):
        for paso in ("inscribirme en H18", "Julio Quispe, DNI 45678912, teléfono 987654321, julio@correo.com", "sí"):
            matricula.procesar_mensaje(paso)
        self.assertIn("por confirmar", matricula.procesar_mensaje("PAG-000134"))
        self.assertIn("Pago por confirmar (MALI),PAG-000134", self._archivo("matricula.csv"))
        self.assertIn("en revisión", matricula.procesar_mensaje("pago MAT-0001 PAG-100001"))
        ident = dr.verificar_alumno("MAT-0001", "45678912")
        self.assertTrue(ident)
        self.assertEqual(dr.verificar_alumno(ident, "11111111"), "")
        self.assertIn("rechazado", dr.resolver_pago("coord01", "MAT-0001", False))
        self.assertIn("pendiente de pago", dr.estado_por_alumno(ident))
        matricula.procesar_mensaje("pago MAT-0001 PAG-000135")
        self.assertIn("**Matriculado**", dr.resolver_pago("coord01", "MAT-0001", True))
        self.assertIn("Matriculado,PAG-000135", self._archivo("matricula.csv"))
        self.assertNotIn("PAG-000135", self._archivo("pagos_demo.csv"))
        self.assertIn("No hay pagos por confirmar", dr.pagos_por_confirmar("coord01"))

    def test_inscripcion_por_codigo_de_horario(self):
        self.assertIn("Elegiste **H16**", matricula.procesar_mensaje("inscribirme en H16"))
        self.assertEqual(matricula.estado["codigo"], "H16")

    def test_elige_horario_por_sede_dias_y_hora(self):
        matricula.procesar_mensaje("quiero inscribirme en dibujo y pintura")
        matricula.procesar_mensaje("el de las 6 de la tarde, lunes y miércoles")
        self.assertEqual(matricula.estado["codigo"], "H20")
        matricula.reiniciar()
        matricula.estado["ultimo_curso"] = "Violín"
        matricula.procesar_mensaje("quisiera inscribir en la molian camacho lunes y miercoles de 10 a 11")
        self.assertEqual(matricula.estado.get("codigo"), "H18")

    def test_cancelar_no_registra(self):
        matricula.procesar_mensaje("inscríbeme en guitarra")
        matricula.procesar_mensaje("cancelar")
        self.assertNotIn("asistente", self._archivo("matricula.csv"))

    def test_horario_lleno_no_se_registra(self):
        self.assertTrue(dr.registrar_matricula("H02", "Ana Torres", "ana@correo.com").startswith("ERROR"))


if __name__ == "__main__":
    unittest.main()
