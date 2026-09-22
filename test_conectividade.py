import unittest

from conectividade import VerificadorConectividade


class ConexaoFalsa:
    def __init__(self):
        self.fechada = False

    def close(self):
        self.fechada = True


class ConectividadeTest(unittest.TestCase):
    def test_detecta_conexao_disponivel(self):
        conexao = ConexaoFalsa()
        verificador = VerificadorConectividade(
            conector=lambda *args, **kwargs: conexao
        )
        self.assertTrue(verificador.disponivel())
        self.assertTrue(conexao.fechada)

    def test_detecta_ausencia_de_internet(self):
        def falhar(*args, **kwargs):
            raise OSError("sem rede")

        self.assertFalse(
            VerificadorConectividade(conector=falhar).disponivel()
        )


if __name__ == "__main__":
    unittest.main()
