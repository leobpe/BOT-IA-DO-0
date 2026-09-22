import os
import unittest
from unittest.mock import patch

from fusao_temporal_api_live import (
    VERSAO_EXPERIMENTO_FUSAO_TEMPORAL,
    fundir_evolucao_temporal_como_fallback,
    gerar_candidatos_fusao_temporal,
)
from telegram_alertas import (
    candidato_fusao_temporal_grupo_teste,
    motivo_suspensao_simulacao,
)


class TestFusaoTemporalAPILive(unittest.TestCase):
    def test_preenche_apenas_lacuna_sem_sobrescrever_packball(self):
        packball = {
            "5": {"chutes": [2, 1], "escanteios": None},
            "10": None,
        }
        contexto = {
            "evolucao_temporal_api_live": {
                "5": {"chutes": [9, 9], "escanteios": [1, 0]},
                "10": {"chutes": [4, 2], "escanteios": [2, 1]},
            },
            "comparacao_temporal_packball_api": {
                "comparacoes": [{"concordante": True}],
            },
        }
        fundida, diagnostico = fundir_evolucao_temporal_como_fallback(
            packball, contexto
        )
        self.assertEqual([2, 1], fundida["5"]["chutes"])
        self.assertEqual([1, 0], fundida["5"]["escanteios"])
        self.assertEqual([4, 2], fundida["10"]["chutes"])
        self.assertTrue(diagnostico["valida"])
        self.assertFalse(
            fundida["fusao_temporal_api_live"]["sobrescreveu_packball"]
        )

    def test_divergencia_atual_bloqueia_toda_fusao(self):
        fundida, diagnostico = fundir_evolucao_temporal_como_fallback(
            {"5": {"chutes": None}},
            {
                "evolucao_temporal_api_live": {"5": {"chutes": [2, 1]}},
                "comparacao_temporal_packball_api": {
                    "comparacoes": [{"concordante": False}],
                },
            },
        )
        self.assertIsNone(fundida)
        self.assertEqual("divergencia_atual", diagnostico["motivo"])

    def test_so_cria_oportunidade_nova_e_mantem_simulacao(self):
        base = [{"mercado": "gol_ft", "status": "rejeitado"}]
        fusao = [{
            "mercado": "gol_ft", "status": "aprovado",
            "features": {}, "motivos": [], "regra_versao": "sinais-v6",
        }]
        itens = gerar_candidatos_fusao_temporal(
            base, fusao,
            {"valida": True, "preenchimentos": ["5.chutes"]},
        )
        self.assertEqual(1, len(itens))
        self.assertEqual("simulacao", itens[0]["status"])
        self.assertEqual(
            VERSAO_EXPERIMENTO_FUSAO_TEMPORAL,
            itens[0]["features"]["exploracao_sombra"]["versao"],
        )
        self.assertEqual([], gerar_candidatos_fusao_temporal(
            [{"mercado": "gol_ft", "status": "aprovado"}], fusao,
            {"valida": True, "preenchimentos": ["5.chutes"]},
        ))

    def test_roteamento_grupo_e_rollback(self):
        item = gerar_candidatos_fusao_temporal(
            [{"mercado": "gol_ft", "status": "rejeitado"}],
            [{
                "mercado": "gol_ft", "status": "aprovado",
                "features": {}, "motivos": [], "regra_versao": "sinais-v6",
            }],
            {"valida": True, "preenchimentos": ["5.chutes"]},
        )[0]
        with patch.dict(os.environ, {"API_LIVE_TEMPORAL_GRUPO_ATIVO": "1"}):
            self.assertTrue(candidato_fusao_temporal_grupo_teste(item))
            self.assertIsNone(motivo_suspensao_simulacao(item))
        with patch.dict(os.environ, {"API_LIVE_TEMPORAL_GRUPO_ATIVO": "0"}):
            self.assertFalse(candidato_fusao_temporal_grupo_teste(item))
            self.assertEqual(
                "exploracao_sombra_fora_allowlist_simulacao_grupo",
                motivo_suspensao_simulacao(item),
            )


if __name__ == "__main__":
    unittest.main()
