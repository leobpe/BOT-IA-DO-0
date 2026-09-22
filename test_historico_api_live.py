import sqlite3
import unittest
from datetime import datetime, timedelta

from historico_api_live import (
    calcular_evolucao_api_live,
    comparar_evolucoes_packball_api,
    janelas_disponiveis_api_live,
    normalizar_snapshot_api_live,
    resumir_historico_api_live,
)
from banco import BancoMonitor, auditar_compatibilidade


def fixture_api(orientacao=False):
    blocos = [
        {
            "team": {"id": 10},
            "statistics": [
                {"type": "Total Shots", "value": 8},
                {"type": "Shots on Goal", "value": 4},
                {"type": "Corner Kicks", "value": 3},
                {"type": "expected_goals", "value": "1.25"},
            ],
        },
        {
            "team": {"id": 20},
            "statistics": [
                {"type": "Total Shots", "value": 5},
                {"type": "Shots on Goal", "value": 2},
                {"type": "Corner Kicks", "value": 1},
                {"type": "expected_goals", "value": None},
            ],
        },
    ]
    if orientacao:
        blocos.reverse()
    return {
        "fixture": {"id": 123, "status": {"elapsed": 32, "short": "1H"}},
        "teams": {"home": {"id": 10}, "away": {"id": 20}},
        "statistics": blocos,
    }


class HistoricoApiLiveTest(unittest.TestCase):
    def test_normaliza_por_id_do_time_e_preserva_valor_ausente(self):
        registro = normalizar_snapshot_api_live(
            fixture_api(orientacao=True),
            "https://packball/jogo",
            coletado_em=datetime(2026, 8, 9, 10, 0),
        )

        self.assertEqual(registro["chutes_mandante"], 8.0)
        self.assertEqual(registro["escanteios_visitante"], 1.0)
        self.assertEqual(registro["xg_mandante"], 1.25)
        self.assertIsNone(registro["xg_visitante"])
        self.assertTrue(registro["completo"])
        self.assertEqual(registro["periodo"], "primeiro_tempo")

    def test_orientacao_invertida_alinha_com_o_packball(self):
        registro = normalizar_snapshot_api_live(
            fixture_api(), "https://packball/jogo", orientacao="invertida"
        )

        self.assertEqual(registro["chutes_mandante"], 5.0)
        self.assertEqual(registro["chutes_visitante"], 8.0)
        self.assertEqual(registro["orientacao"], "invertida")

    def test_ignora_fixture_sem_estatistica_real(self):
        fixture = fixture_api()
        fixture["statistics"] = []

        self.assertIsNone(
            normalizar_snapshot_api_live(fixture, "https://packball/jogo")
        )

    def test_detecta_janelas_5_10_15_da_leitura_mais_recente(self):
        agora = datetime(2026, 8, 9, 10, 20)
        registros = []
        for minutos, chutes in ((15, 2), (10, 4), (5, 6), (0, 8)):
            registros.append({
                "coletado_em": (agora - timedelta(minutes=minutos)).isoformat(),
                "periodo": "primeiro_tempo",
                "chutes_mandante": chutes,
                "chutes_visitante": 1,
            })

        self.assertEqual(
            janelas_disponiveis_api_live(registros), {5, 10, 15}
        )

        evolucao = calcular_evolucao_api_live(registros)
        self.assertEqual(evolucao["5"]["chutes"], [2, 0])
        self.assertEqual(evolucao["10"]["chutes"], [4, 0])
        self.assertEqual(evolucao["15"]["chutes"], [6, 0])
        self.assertFalse(evolucao["aplicacao_sinais"])

    def test_nao_cruza_periodos_da_partida(self):
        agora = datetime(2026, 8, 9, 11, 0)
        registros = [
            {
                "coletado_em": (agora - timedelta(minutes=5)).isoformat(),
                "periodo": "primeiro_tempo",
                "chutes_mandante": 4,
            },
            {
                "coletado_em": agora.isoformat(),
                "periodo": "segundo_tempo",
                "chutes_mandante": 5,
            },
        ]

        self.assertEqual(janelas_disponiveis_api_live(registros), set())

    def test_reset_de_contador_nao_vira_delta_negativo(self):
        agora = datetime(2026, 8, 9, 11, 0)
        registros = [
            {
                "coletado_em": (agora - timedelta(minutes=5)).isoformat(),
                "periodo": "segundo_tempo",
                "chutes_mandante": 8,
                "chutes_visitante": 4,
            },
            {
                "coletado_em": agora.isoformat(),
                "periodo": "segundo_tempo",
                "chutes_mandante": 2,
                "chutes_visitante": 1,
            },
        ]

        evolucao = calcular_evolucao_api_live(registros)

        self.assertIsNone(evolucao["5"])

    def test_compara_somente_janelas_e_metricas_equivalentes(self):
        comparacao = comparar_evolucoes_packball_api(
            {
                "5": {"chutes": [3, 1], "escanteios": [1, 0]},
                "10": None,
            },
            {
                "5": {"chutes": [4, 1], "escanteios": [3, 0]},
                "10": {"chutes": [8, 2]},
            },
        )

        self.assertEqual(comparacao["total"], 2)
        self.assertEqual(comparacao["concordantes"], 1)
        self.assertEqual(comparacao["taxa_concordancia"], 0.5)
        self.assertFalse(comparacao["aplicacao_sinais"])

    def test_resumo_indisponivel_nao_finge_cobertura(self):
        conexao = sqlite3.connect(":memory:")
        try:
            resumo = resumir_historico_api_live(conexao)
        finally:
            conexao.close()

        self.assertFalse(resumo["saudavel"])
        self.assertEqual(resumo["estado"], "indisponivel")
        self.assertFalse(resumo["aplicacao_sinais"])

    def test_persiste_idempotente_remove_expirado_e_resume_janela(self):
        banco = BancoMonitor(":memory:")
        agora = datetime(2026, 8, 9, 12, 0)
        try:
            registros = []
            for minutos, chutes in ((6, 4), (0, 7)):
                fixture = fixture_api()
                fixture["statistics"][0]["statistics"][0]["value"] = chutes
                registros.append(normalizar_snapshot_api_live(
                    fixture,
                    "https://packball/jogo",
                    coletado_em=agora - timedelta(minutes=minutos),
                ))
            expirado = dict(registros[0])
            expirado.update({
                "fixture_id": 999,
                "packball_url": "https://packball/antigo",
                "coletado_em": (agora - timedelta(days=31)).isoformat(),
            })

            primeiro = banco.salvar_historico_api_live(
                [expirado, *registros], agora=agora
            )
            repetido = banco.salvar_historico_api_live(
                registros, agora=agora
            )
            banco.salvar_registro({
                "coletado_em": agora,
                "url": "https://packball/jogo",
                "mandante": "Casa",
                "visitante": "Fora",
                "contexto_api": {
                    "comparacao_temporal_packball_api": {
                        "total": 2,
                        "concordantes": 1,
                        "taxa_concordancia": 0.5,
                        "aplicacao_sinais": False,
                    }
                },
            })
            resumo = resumir_historico_api_live(
                banco.conexao, agora=agora
            )

            self.assertEqual(primeiro["inseridos"], 3)
            self.assertEqual(primeiro["removidos_retencao"], 1)
            self.assertEqual(repetido["inseridos"], 0)
            self.assertEqual(repetido["duplicados"], 2)
            self.assertEqual(resumo["snapshots"], 2)
            self.assertEqual(resumo["fixtures"], 1)
            self.assertEqual(resumo["janelas_disponiveis"]["5"], 1)
            self.assertEqual(resumo["comparacoes_packball_api"], 2)
            self.assertEqual(resumo["comparacoes_concordantes"], 1)
            self.assertEqual(
                resumo["snapshots_concordantes_packball"], 0
            )
            self.assertEqual(
                resumo["fixtures_comparaveis_packball"], 1
            )
            self.assertEqual(
                resumo["taxa_concordancia_packball_api"], 0.5
            )
            self.assertEqual(
                resumo["prontidao_revisao"]["estado"],
                "aguardando_amostra",
            )
            self.assertEqual(
                resumo["prontidao_revisao"]["faltam_snapshots"], 29
            )
            self.assertFalse(
                resumo["prontidao_revisao"]["aplicacao_automatica"]
            )
            self.assertTrue(
                auditar_compatibilidade(banco.conexao)["compativel"]
            )
        finally:
            banco.fechar()

    def test_prontidao_exige_amostra_diversa_e_wilson_conservador(self):
        agora = datetime(2026, 8, 9, 12, 0)

        def avaliar(snapshots_concordantes):
            banco = BancoMonitor(":memory:")
            try:
                for indice in range(30):
                    banco.salvar_registro({
                        "coletado_em": agora - timedelta(
                            minutes=(indice // 10) * 5
                        ),
                        "url": (
                            "https://packball/jogo/"
                            f"{indice % 10}"
                        ),
                        "mandante": f"Casa {indice % 10}",
                        "visitante": f"Fora {indice % 10}",
                        "contexto_api": {
                            "comparacao_temporal_packball_api": {
                                "total": 2,
                                "concordantes": (
                                    2 if indice < snapshots_concordantes
                                    else 1
                                ),
                                "aplicacao_sinais": False,
                            }
                        },
                    })
                return resumir_historico_api_live(
                    banco.conexao, agora=agora
                )["prontidao_revisao"]
            finally:
                banco.fechar()

        apto = avaliar(30)
        conservador = avaliar(24)

        self.assertEqual(apto["estado"], "apto_revisao")
        self.assertTrue(apto["apto_revisao"])
        self.assertEqual(conservador["estado"], "divergencia_fontes")
        self.assertFalse(conservador["apto_revisao"])
        self.assertFalse(apto["aplicacao_automatica"])
        self.assertEqual(apto["intervalo_independencia_minutos"], 5)


if __name__ == "__main__":
    unittest.main()
