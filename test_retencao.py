import unittest
from pathlib import Path

from retencao import rotacionar_arquivo


class RetencaoArquivoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_rotacao.jsonl"
        for indice in range(0, 4):
            arquivo = self.caminho if indice == 0 else Path(f"{self.caminho}.{indice}")
            if arquivo.exists():
                arquivo.unlink()

    def tearDown(self):
        self.setUp()

    def test_rotaciona_e_preserva_copia(self):
        self.caminho.write_text("123456", encoding="utf-8")
        self.assertTrue(rotacionar_arquivo(self.caminho, 5, copias=2))
        self.assertFalse(self.caminho.exists())
        self.assertEqual(
            Path(f"{self.caminho}.1").read_text(encoding="utf-8"), "123456"
        )

    def test_nao_rotaciona_abaixo_do_limite(self):
        self.caminho.write_text("123", encoding="utf-8")
        self.assertFalse(rotacionar_arquivo(self.caminho, 5))
