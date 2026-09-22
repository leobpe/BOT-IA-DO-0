import unittest
from datetime import datetime
from pathlib import Path

from controle_sistema import (
    liberar_modo_manutencao,
    ler_modo_manutencao,
    solicitar_modo_manutencao,
)


class ControleSistemaTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_controle_sistema"
        self.pasta.mkdir(exist_ok=True)

    def tearDown(self):
        for arquivo in self.pasta.iterdir():
            arquivo.unlink()
        self.pasta.rmdir()

    def test_solicita_e_libera_manutencao_de_forma_persistente(self):
        estado = solicitar_modo_manutencao(
            self.pasta,
            motivo="teste",
            agora=datetime(2026, 7, 21, 10, 0),
        )

        self.assertTrue(estado["ativo"])
        self.assertEqual(ler_modo_manutencao(self.pasta)["motivo"], "teste")
        self.assertTrue(liberar_modo_manutencao(self.pasta))
        self.assertFalse(ler_modo_manutencao(self.pasta)["ativo"])

    def test_arquivo_invalido_e_fail_safe(self):
        (self.pasta / "modo_manutencao.json").write_text(
            "invalido", encoding="utf-8"
        )

        estado = ler_modo_manutencao(self.pasta)

        self.assertTrue(estado["ativo"])
        self.assertEqual(estado["motivo"], "arquivo_manutencao_invalido")


if __name__ == "__main__":
    unittest.main()
