import unittest

from qualidade_dados import avaliar_qualidade, extrair_minuto, extrair_placar


ESTATISTICAS_COMPLETAS = {
    "Chutes": "10-8",
    "Chutes no gol": "4-3",
    "Índice de pressão": "60-40",
    "Escanteios": "5-2",
    "Ataques perigosos": "42-30",
}


class QualidadeDadosTest(unittest.TestCase):
    def test_packball_completo_sem_api_continua_apto(self):
        qualidade = avaliar_qualidade(
            {"placar": "1-0"}, ESTATISTICAS_COMPLETAS
        )
        self.assertEqual(qualidade["pontuacao"], 90.0)
        self.assertTrue(qualidade["apto_para_sinal"])
        self.assertIn("sem_confirmacao_api", qualidade["alertas"])

    def test_api_compativel_aumenta_qualidade(self):
        qualidade = avaliar_qualidade(
            {"placar": "1-0"},
            ESTATISTICAS_COMPLETAS,
            {"similaridade": 0.9, "placar": [1, 0]},
        )
        self.assertEqual(qualidade["pontuacao"], 98.0)
        self.assertFalse(qualidade["divergencia_critica"])

    def test_placar_divergente_bloqueia_sinal(self):
        qualidade = avaliar_qualidade(
            {"placar": "1-0"},
            ESTATISTICAS_COMPLETAS,
            {"similaridade": 0.9, "placar": [0, 1]},
        )
        self.assertEqual(qualidade["pontuacao"], 35.0)
        self.assertFalse(qualidade["apto_para_sinal"])

    def test_campos_ausentes_reduzem_completude(self):
        qualidade = avaliar_qualidade(
            {"placar": "0-0"}, {"Chutes": "2-1"}
        )
        self.assertEqual(qualidade["completude"], 0.2)
        self.assertFalse(qualidade["apto_para_sinal"])

    def test_extrai_placar(self):
        self.assertEqual(extrair_placar("2 - 3"), [2, 3])
        self.assertIsNone(extrair_placar("vs"))

    def test_minuto_divergente_reduz_qualidade(self):
        qualidade = avaliar_qualidade(
            {"placar": "1-0", "status": "72 '"},
            ESTATISTICAS_COMPLETAS,
            {
                "similaridade": 0.9,
                "placar": [1, 0],
                "status": {"elapsed": 60},
            },
        )
        self.assertIn("minuto_divergente_api", qualidade["alertas"])
        self.assertEqual(qualidade["pontuacao"], 83.0)

    def test_extrai_minuto_e_intervalo(self):
        self.assertEqual(extrair_minuto("67 '"), 67)
        self.assertEqual(extrair_minuto("Intervalo"), 45)

    def test_registra_latencia_e_atraso_entre_fontes(self):
        qualidade = avaliar_qualidade(
            {"placar": "0-0", "status": "40 '"},
            ESTATISTICAS_COMPLETAS,
            {
                "similaridade": 1,
                "placar": [0, 0],
                "status": {"elapsed": 38},
            },
            latencia_coleta_segundos=7.1234,
        )
        self.assertEqual(qualidade["latencia_coleta_segundos"], 7.123)
        self.assertEqual(qualidade["atraso_api_minutos"], 2)


if __name__ == "__main__":
    unittest.main()
