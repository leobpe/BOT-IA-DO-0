import unittest
from pathlib import Path

from dependencias import ler_lock_dependencias, verificar_dependencias


class DependenciasTest(unittest.TestCase):
    def setUp(self):
        self.lock = Path.cwd() / ".teste_requirements.lock.txt"
        self.lock.unlink(missing_ok=True)

    def tearDown(self):
        self.lock.unlink(missing_ok=True)

    def test_confirma_ambiente_igual_ao_lock(self):
        self.lock.write_text(
            "Pacote_A==1.2.3\npacote-b==4.5\n", encoding="utf-8"
        )

        resultado = verificar_dependencias(
            self.lock,
            versoes_instaladas={"pacote-a": "1.2.3", "pacote-b": "4.5"},
            versao_python=(3, 14, 6),
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "reproduzivel")
        self.assertEqual(resultado["total_lock"], 2)
        self.assertTrue(resultado["lock_sha256"])

    def test_detecta_dependencia_ausente_e_versao_diferente(self):
        self.lock.write_text(
            "pacote-a==1.0\npacote-b==2.0\n", encoding="utf-8"
        )

        resultado = verificar_dependencias(
            self.lock,
            versoes_instaladas={"pacote-a": "9.0"},
            versao_python=(3, 14, 6),
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["motivo"], "dependencias_ausentes")
        self.assertEqual(resultado["ausentes"], ["pacote-b"])
        self.assertEqual(resultado["divergentes"][0]["instalada"], "9.0")

    def test_recusa_lock_flexivel_ou_duplicado(self):
        self.lock.write_text("pacote>=1\n", encoding="utf-8")
        invalido = ler_lock_dependencias(self.lock)
        self.assertFalse(invalido["valido"])
        self.assertEqual(invalido["motivo"], "lock_dependencias_invalido")

        self.lock.write_text(
            "pacote-a==1\nPacote_A==1\n", encoding="utf-8"
        )
        duplicado = ler_lock_dependencias(self.lock)
        self.assertFalse(duplicado["valido"])
        self.assertEqual(duplicado["motivo"], "lock_dependencias_duplicado")

    def test_recusa_python_abaixo_do_minimo(self):
        self.lock.write_text("pacote==1\n", encoding="utf-8")
        resultado = verificar_dependencias(
            self.lock,
            versoes_instaladas={"pacote": "1"},
            versao_python=(3, 10, 14),
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["motivo"], "python_incompativel")


if __name__ == "__main__":
    unittest.main()
