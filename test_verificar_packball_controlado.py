import unittest
from pathlib import Path

from verificar_packball_controlado import (
    avaliar_pagina,
    executar_teste_controlado,
)


class LocalizadorFalso:
    def __init__(self, texto="", quantidade=0, visivel=False):
        self.texto = texto
        self.quantidade = quantidade
        self.visivel = visivel

    def count(self):
        return self.quantidade

    def is_visible(self):
        return self.visivel

    def inner_text(self):
        return self.texto


class PaginaFalsa:
    def __init__(self, login=False, contador=""):
        self.login = login
        self.contador = contador

    def locator(self, seletor):
        if seletor == 'input[name="email"]':
            return LocalizadorFalso(
                quantidade=1 if self.login else 0,
                visivel=self.login,
            )
        return LocalizadorFalso(
            texto=self.contador,
            quantidade=1 if self.contador else 0,
            visivel=True,
        )


class VerificarPackBallControladoTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_verificar_packball"
        self.pasta.mkdir(exist_ok=True)

    def tearDown(self):
        for arquivo in self.pasta.iterdir():
            arquivo.unlink()
        self.pasta.rmdir()

    def test_tela_login_para_sem_tentar_autenticar(self):
        resultado = avaliar_pagina(PaginaFalsa(login=True))
        self.assertEqual(resultado["status"], "sessao_expirada")
        self.assertFalse(resultado["autenticado"])

    def test_acesso_confirmado_le_contador_sem_clicar(self):
        resultado = avaliar_pagina(PaginaFalsa(contador="51"))
        self.assertEqual(resultado["status"], "acesso_confirmado")
        self.assertEqual(resultado["contador_ao_vivo"], 51)

    def test_recusa_teste_se_monitor_nao_esta_em_manutencao(self):
        resultado = executar_teste_controlado(self.pasta)
        self.assertEqual(resultado["status"], "recusado")
        self.assertEqual(resultado["motivo"], "modo_manutencao_inativo")
        self.assertEqual(resultado["navegacoes"], 0)


if __name__ == "__main__":
    unittest.main()
