import unittest
from datetime import datetime
from unittest.mock import patch

from progresso_calibracao import (
    calcular_progresso_amostra,
    resumir_progresso_calibracao,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO as VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
)


class ProgressoCalibracaoTest(unittest.TestCase):
    def test_sem_resultados_nao_inventa_prazo(self):
        progresso = calcular_progresso_amostra(
            [], datetime(2026, 7, 21, 12, 0)
        )
        self.assertEqual(progresso["amostra"], 0)
        self.assertIsNone(progresso["dias_estimados"])
        self.assertEqual(
            progresso["confiabilidade_estimativa"], "sem_ritmo"
        )

    def test_calcula_ritmo_somente_com_resultados_validos(self):
        resultados = [
            {"encerrado_em": f"2026-07-{dia:02d}T12:00:00"}
            for dia in range(15, 22)
            for _ in range(2)
        ] + [
            {"encerrado_em": "inválido"},
            {"encerrado_em": "2026-07-22T12:00:00"},
        ]
        progresso = calcular_progresso_amostra(
            resultados, datetime(2026, 7, 21, 18, 0)
        )
        self.assertEqual(progresso["amostra"], 14)
        self.assertEqual(progresso["resultados_janela"], 14)
        self.assertEqual(progresso["ritmo_dia"], 2.0)
        self.assertEqual(progresso["dias_estimados"], 43)
        self.assertEqual(
            progresso["confiabilidade_estimativa"], "preliminar"
        )

    def test_meta_atingida_tem_prazo_zero(self):
        resultados = [
            {"encerrado_em": "2026-07-21T12:00:00"}
            for _ in range(100)
        ]
        progresso = calcular_progresso_amostra(
            resultados, datetime(2026, 7, 21, 18, 0)
        )
        self.assertEqual(progresso["faltam"], 0)
        self.assertEqual(progresso["dias_estimados"], 0)
        self.assertEqual(progresso["data_estimada"], "2026-07-21")

    @patch("progresso_calibracao.obter_limites_risco")
    @patch("progresso_calibracao.carregar_amostra_independente")
    def test_usa_versao_challenger_ativa(self, carregar, _limites):
        carregar.return_value = []

        resumo = resumir_progresso_calibracao(
            object(),
            agora=datetime(2026, 8, 8, 8, 0),
            mercados=("proximo_gol",),
            usar_versoes_ativas=True,
        )

        self.assertEqual(resumo["proximo_gol"]["amostra"], 0)
        self.assertEqual(resumo["proximo_gol"]["faltam"], 100)
        self.assertEqual(
            carregar.call_args.args[2],
            VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
        )


if __name__ == "__main__":
    unittest.main()
