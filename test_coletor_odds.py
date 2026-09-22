import unittest

from coletor_odds import (
    coletar_odds,
    filtrar_mercados_packball_ao_vivo,
)


class BotaoFalso:
    def __init__(self, existe=True):
        self.existe = existe
        self.clicado = False

    def count(self):
        return 1 if self.existe else 0

    def click(self, timeout=None):
        self.clicado = True


class PaginaFalsa:
    def __init__(self, existe_ao_vivo=True):
        self.botao = BotaoFalso(existe_ao_vivo)
        self.url = None
        self.avaliacoes = 0
        self.esperas_dinamicas = []

    def goto(self, url, **kwargs):
        self.url = url

    def wait_for_timeout(self, milissegundos):
        return None

    def wait_for_function(self, script, timeout=None):
        self.esperas_dinamicas.append((script, timeout))
        return True

    def locator(self, seletor):
        self.seletor = seletor
        return self.botao

    def evaluate(self, script):
        self.avaliacoes += 1
        if self.avaliacoes == 1:
            return [{"mercado": "Total Gols", "dados": "Over 2.5"}]
        return [{
            "mercado": "Marcar O Próximo Gol",
            "dados": "Casa 1.80",
        }]


class ColetorOddsTest(unittest.TestCase):
    def test_filtro_fechado_rejeita_mercados_ambiguos_com_goal(self):
        itens = [
            {
                "mercado": "Total Gols",
                "dados": "Total Gols Over Under 2.5 1.8 2.0",
            },
            {
                "mercado": "Total ShotOnGoal",
                "dados": "Total ShotOnGoal Over Under 8.5 1.9 1.9",
            },
            {
                "mercado": "Goal Kicks",
                "dados": "Goal Kicks Over Under 10.5 1.9 1.9",
            },
            {
                "mercado": "Handicap Asiático Gols",
                "dados": "Handicap Asiático Gols Over Under 0.5 1.9 1.9",
            },
            {
                "mercado": "Escanteios - 2 Opções",
                "dados": "Over Under 9.5 1.9 1.9",
            },
        ]

        filtrados = filtrar_mercados_packball_ao_vivo(itens)

        self.assertEqual(
            [item["mercado"] for item in filtrados],
            ["Total Gols", "Escanteios - 2 Opções"],
        )

    def test_abre_url_de_odds_e_subaba_ao_vivo(self):
        pagina = PaginaFalsa()
        resultado = coletar_odds(
            pagina,
            {"url": "https://packball.com/pt/match/123/live"},
        )
        self.assertEqual(
            pagina.url,
            "https://packball.com/pt/match/123/odds",
        )
        self.assertTrue(pagina.botao.clicado)
        self.assertEqual(len(resultado["ao_vivo"]), 1)
        mercado = resultado["ao_vivo"][0]
        self.assertEqual(mercado["fonte"], "packball")
        self.assertIs(mercado["cache"], False)
        self.assertEqual(mercado["idade_segundos"], 0.0)
        self.assertTrue(mercado["coletado_em"])
        self.assertEqual(
            [item[1] for item in pagina.esperas_dinamicas], [4000, 2500]
        )

    def test_continua_quando_subaba_ao_vivo_nao_existe(self):
        pagina = PaginaFalsa(existe_ao_vivo=False)
        resultado = coletar_odds(
            pagina,
            {"url": "https://packball.com/pt/match/123/live"},
        )
        self.assertFalse(pagina.botao.clicado)
        self.assertEqual(resultado["ao_vivo"], [])

    def test_odds_passam_pelo_controle_global_de_acesso(self):
        class ControleFalso:
            antes = 0
            validacoes = 0

            def antes_navegacao(self):
                self.antes += 1

            def validar_pagina(self, _pagina):
                self.validacoes += 1

        controle = ControleFalso()
        coletar_odds(
            PaginaFalsa(),
            {"url": "https://packball.com/pt/match/123/live"},
            controle,
        )
        self.assertEqual((controle.antes, controle.validacoes), (1, 1))


if __name__ == "__main__":
    unittest.main()
