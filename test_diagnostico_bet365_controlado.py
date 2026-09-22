import unittest

from diagnostico_bet365_controlado import (
    _evento_id_da_url,
    classificar_painel_bet365,
)


class DiagnosticoBet365ControladoTest(unittest.TestCase):
    def test_classifica_bloqueio_antes_dos_demais_estados(self):
        self.assertEqual(
            classificar_painel_bet365({
                "bloqueado": True,
                "carregadores": 1,
                "mercados_escanteios": [{"texto": "Escanteios"}],
            }),
            ("bloqueado", "bloqueio_ou_verificacao_humana"),
        )

    def test_mercado_visivel_ainda_nao_vira_oferta_valida(self):
        self.assertEqual(
            classificar_painel_bet365({
                "bloqueado": False,
                "carregadores": 0,
                "mercados_escanteios": [{"texto": "Escanteios Asiáticos"}],
            }),
            ("mercado_rejeitado", "estrutura_dom_aguardando_mapeamento"),
        )

    def test_distingue_carregamento_de_mercado_ausente(self):
        self.assertEqual(
            classificar_painel_bet365({
                "carregadores": 1,
                "mercados_escanteios": [],
            })[0],
            "painel_nao_carregou",
        )
        self.assertEqual(
            classificar_painel_bet365({
                "carregadores": 0,
                "mercados_escanteios": [],
            })[0],
            "mercado_ausente",
        )

    def test_painel_de_outro_evento_nao_finge_mercado_ausente(self):
        estado, motivo = classificar_painel_bet365(
            {
                "bloqueado": False,
                "carregadores": 0,
                "texto_corpo": "Auckland FC 0 1 Tottenham",
                "mercados_escanteios": [],
            },
            "LAFC",
            "Kansas City",
        )

        self.assertEqual(estado, "painel_nao_carregou")
        self.assertEqual(
            motivo,
            "evento_selecionado_nao_substituiu_painel",
        )

    def test_evento_confirmado_sem_escanteios_e_mercado_ausente(self):
        estado, motivo = classificar_painel_bet365(
            {
                "bloqueado": False,
                "carregadores": 0,
                "texto_corpo": "LAFC 3 0 Kansas City Resultado Final",
                "mercados_escanteios": [],
            },
            "LAFC",
            "Kansas City",
        )

        self.assertEqual(estado, "mercado_ausente")
        self.assertEqual(motivo, "escanteios_nao_exibidos")

    def test_extrai_evento_somente_da_url_de_partida(self):
        self.assertEqual(
            _evento_id_da_url(
                "https://www.bet365.bet.br/#/IP/EV151365391432C1"
            ),
            "EV151365391432",
        )
        self.assertIsNone(
            _evento_id_da_url("https://www.bet365.bet.br/#/IP/B1")
        )


if __name__ == "__main__":
    unittest.main()
