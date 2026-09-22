import unittest

from relatorio_backtest import (
    formatar_metricas,
    separar_metricas_populacoes,
    validar_contadores_progresso,
)


class RelatorioBacktestTest(unittest.TestCase):
    def test_faltam_usa_amostra_real_da_calibracao(self):
        contadores = validar_contadores_progresso(
            resultados_brutos=120,
            amostra_vinculada=76,
            andamento={"amostra": 76, "faltam": 24},
        )

        self.assertEqual(contadores["resultados_brutos"], 120)
        self.assertEqual(contadores["amostra_calibracao"], 76)
        self.assertEqual(contadores["faltam_calibracao"], 24)

    def test_divergencia_entre_relatorio_e_calibrador_falha_fechada(self):
        with self.assertRaisesRegex(
            RuntimeError, "diverge da amostra usada na calibracao"
        ):
            validar_contadores_progresso(
                resultados_brutos=120,
                amostra_vinculada=75,
                andamento={"amostra": 76, "faltam": 24},
            )

    def test_metricas_da_amostra_oficial_nao_misturam_legado(self):
        brutas = {
            "amostra": 3,
            "greens": 2,
            "half_greens": 0,
            "reds": 1,
            "half_reds": 0,
            "taxa_acerto": 0.6667,
            "intervalo_acerto_95": [0.2, 0.9],
            "estado_amostra": "inconclusiva",
            "lucro_unidades": 0.2,
            "roi": 0.0667,
            "yield": 0.0667,
            "drawdown_maximo": 1.0,
            "maior_sequencia_reds": 1,
            "discriminacao_pontuacao": {"auc": 0.5},
        }
        vinculadas = [
            {
                "resultado": "red",
                "retorno_unidades": -1.0,
                "pontuacao_tecnica": 80,
            }
        ]

        metricas = separar_metricas_populacoes(brutas, vinculadas)

        self.assertEqual(metricas["resultados_brutos"]["amostra"], 3)
        self.assertEqual(metricas["amostra_calibracao"]["amostra"], 1)
        self.assertEqual(
            metricas["amostra_calibracao"]["taxa_acerto"], 0.0
        )
        self.assertEqual(metricas["amostra_calibracao"]["roi"], -1.0)
        self.assertIn(
            "n=1 | acerto=0.0% | ROI=-100.0%",
            formatar_metricas(metricas["amostra_calibracao"]),
        )


if __name__ == "__main__":
    unittest.main()
