import unittest
from datetime import datetime, timedelta

from evolucao import HistoricoTemporal, extrair_par, formatar_delta


class EvolucaoTemporalTest(unittest.TestCase):
    def setUp(self):
        self.historico = HistoricoTemporal()
        self.url = "https://packball.com/match/1"
        self.inicio = datetime(2026, 7, 20, 12, 0, 0)

    @staticmethod
    def estatisticas(pressao, chutes, escanteios):
        return {
            "Índice de pressão": pressao,
            "Chutes": chutes,
            "Escanteios": escanteios,
        }

    def test_extrai_par_com_decimal_e_percentual(self):
        self.assertEqual(extrair_par("60,5% - 39.5%"), (60.5, 39.5))
        self.assertIsNone(extrair_par("-"))

    def test_calcula_janelas_de_5_10_e_15_minutos(self):
        base = self.estatisticas("60-40", "4-2", "1-0")
        self.historico.calcular(self.url, base, self.inicio)
        self.historico.calcular(
            self.url,
            self.estatisticas("58-42", "5-2", "1-0"),
            self.inicio + timedelta(minutes=5),
        )
        self.historico.calcular(
            self.url,
            self.estatisticas("55-45", "7-3", "2-1"),
            self.inicio + timedelta(minutes=10),
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("70-30", "10-5", "4-1"),
            self.inicio + timedelta(minutes=15),
        )

        self.assertEqual(evolucao["5"]["chutes"], [3.0, 2.0])
        self.assertEqual(evolucao["10"]["escanteios"], [3.0, 1.0])
        self.assertEqual(evolucao["15"]["pressao"], [10.0, -10.0])
        self.assertEqual(evolucao["5"]["duracao_real_minutos"], 5.0)
        self.assertEqual(evolucao["10"]["desvio_alvo_minutos"], 0.0)

    def test_nao_chama_intervalo_muito_antigo_de_janela_recente(self):
        self.historico.calcular(
            self.url,
            self.estatisticas("50-50", "1-1", "0-0"),
            self.inicio,
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("80-20", "8-2", "3-0"),
            self.inicio + timedelta(minutes=15),
        )

        self.assertIsNone(evolucao["5"])
        self.assertIsNone(evolucao["10"])
        self.assertEqual(evolucao["15"]["chutes"], [7.0, 1.0])

    def test_restaura_snapshots_e_continua_calculo(self):
        quantidade = self.historico.restaurar(
            {
                self.url: [
                    {
                        "instante": self.inicio,
                        "estatisticas": self.estatisticas(
                            "50-50", "2-2", "0-1"
                        ),
                    }
                ]
            }
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("65-35", "6-3", "2-1"),
            self.inicio + timedelta(minutes=5),
        )
        self.assertEqual(quantidade, 1)
        self.assertEqual(evolucao["5"]["chutes"], [4.0, 1.0])

    def test_formatacao_de_delta_negativo(self):
        self.assertEqual(formatar_delta([-30, 30]), "-30/+30")

    def test_resume_pressao_por_media_pico_tendencia_e_dominio(self):
        self.historico.calcular(
            self.url,
            self.estatisticas("40-60", "1-1", "0-0"),
            self.inicio,
        )
        self.historico.calcular(
            self.url,
            self.estatisticas("70-30", "3-1", "1-0"),
            self.inicio + timedelta(minutes=3),
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("60-40", "4-2", "2-0"),
            self.inicio + timedelta(minutes=5),
        )
        resumo = evolucao["5"]["pressao_resumo"]
        self.assertEqual(resumo["media"], [56.67, 43.33])
        self.assertEqual(resumo["pico"], [70.0, 60.0])
        self.assertEqual(resumo["tendencia"], [20.0, -20.0])
        self.assertEqual(resumo["dominio_amostras"], [2, 1])
        self.assertEqual(resumo["dominio_minutos"], [2.0, 3.0])

    def test_detecta_reset_de_contador_sem_criar_delta_negativo(self):
        self.historico.calcular(
            self.url,
            self.estatisticas("50-50", "12-8", "5-4"),
            self.inicio,
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("55-45", "2-1", "0-0"),
            self.inicio + timedelta(minutes=5),
        )
        self.assertIsNone(evolucao["5"]["chutes"])
        self.assertIsNone(evolucao["5"]["escanteios"])
        self.assertEqual(
            evolucao["5"]["resets_detectados"],
            ["chutes", "escanteios"],
        )

    def test_calcula_aceleracao_entre_blocos_de_cinco_minutos(self):
        self.historico.calcular(
            self.url,
            self.estatisticas("50-50", "1-1", "0-0"),
            self.inicio,
            "20 '",
        )
        self.historico.calcular(
            self.url,
            self.estatisticas("55-45", "3-1", "1-0"),
            self.inicio + timedelta(minutes=5),
            "25 '",
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("70-30", "8-2", "3-0"),
            self.inicio + timedelta(minutes=10),
            "30 '",
        )
        self.assertEqual(
            evolucao["aceleracao_5_vs_5"]["chutes"], [3.0, 1.0]
        )

    def test_nao_mistura_primeiro_e_segundo_tempo(self):
        self.historico.calcular(
            self.url,
            self.estatisticas("70-30", "10-4", "5-2"),
            self.inicio,
            "45 '",
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("60-40", "11-4", "5-2"),
            self.inicio + timedelta(minutes=6),
            "51 '",
        )
        self.assertIsNone(evolucao["5"])
        self.assertEqual(evolucao["periodo"], "segundo_tempo")

    def test_detecta_gol_e_cartao_vermelho_recentes(self):
        self.historico.calcular(
            self.url,
            self.estatisticas("55-45", "4-2", "1-1"),
            self.inicio,
            "30 '",
            "0-0",
            [],
        )
        evolucao = self.historico.calcular(
            self.url,
            self.estatisticas("60-40", "5-2", "1-1"),
            self.inicio + timedelta(minutes=1),
            "31 '",
            "1-0",
            [{"type": "Card", "detail": "Red Card"}],
        )
        self.assertTrue(evolucao["eventos_recentes"]["gol"])
        self.assertTrue(evolucao["eventos_recentes"]["cartao_vermelho"])


if __name__ == "__main__":
    unittest.main()
