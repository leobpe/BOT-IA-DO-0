import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from controle_filtro_gol_ht_preciso import (
    VERSAO_CONTROLE,
    aplicar_validacao,
    ativar,
    entrega_liberada,
    ler_estado,
    suspender,
)
from filtro_gol_ht_antecipado_preciso import METODO, ROLLBACK
from telegram_alertas import motivo_suspensao_simulacao


class ControleFiltroGolHtPrecisoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / (
            f".teste_controle_filtro_ht_{uuid4().hex}.json"
        )
        self.agora = datetime(2026, 9, 9, 19, 0, 0)

    def tearDown(self):
        self.caminho.unlink(missing_ok=True)
        for temporario in self.caminho.parent.glob(
            f".{self.caminho.name}.*.tmp"
        ):
            temporario.unlink(missing_ok=True)

    def test_ausencia_libera_e_corrupcao_falha_fechado(self):
        self.assertTrue(entrega_liberada(self.caminho))
        self.caminho.write_text("{", encoding="utf-8")
        self.assertFalse(entrega_liberada(self.caminho))
        self.assertFalse(ler_estado(self.caminho)["saudavel"])

    def test_suspensao_idempotente_e_reativacao_manual(self):
        primeiro = suspender(
            "validacao|ancora|sha", "negativo",
            caminho=self.caminho, agora=self.agora,
        )
        repetido = suspender(
            "validacao|ancora|sha", "negativo",
            caminho=self.caminho, agora=self.agora,
        )
        self.assertTrue(primeiro["alterado"])
        self.assertTrue(repetido["idempotente"])
        self.assertFalse(entrega_liberada(self.caminho))
        self.assertTrue(
            ativar(caminho=self.caminho, agora=self.agora)["ativo"]
        )

    def test_checkpoint_negativo_suspende_so_entrega(self):
        estado = aplicar_validacao({
            "versao": "validacao-v1",
            "registrado_em": "2026-09-09T19:00:00",
            "definicao_sha256": "sha",
            "alerta_desfavoravel": True,
            "resultados_completos": False,
            "validos": 25,
            "greens": 0,
            "reds": 25,
            "roi": -1.0,
        }, caminho=self.caminho, agora=self.agora)
        self.assertFalse(estado["ativo"])
        self.assertEqual(
            "ic95_roi_checkpoint_25_integralmente_negativo",
            estado["motivo"],
        )
        self.assertTrue(estado["metricas"]["coleta_sombra_continua"])

    def test_validacao_inconsistente_falha_fechado(self):
        estado = aplicar_validacao({
            "versao": "validacao-v1",
            "saudavel": False,
            "registrado_em": "ancora",
            "definicao_sha256": "sha",
        }, caminho=self.caminho, agora=self.agora)
        self.assertFalse(estado["ativo"])
        self.assertEqual(
            "validacao_filtro_gol_ht_preciso_inconsistente",
            estado["motivo"],
        )

    def test_estado_incompativel_nao_e_sobrescrito(self):
        self.caminho.write_text(json.dumps({
            "versao": VERSAO_CONTROLE, "ativo": "sim"
        }), encoding="utf-8")
        estado = suspender("a", "b", caminho=self.caminho)
        self.assertFalse(estado["saudavel"])
        self.assertFalse(estado["alterado"])

    @staticmethod
    def _candidato(chutes_no_gol=2):
        return {
            "mercado": "gol_ht",
            "status": "simulacao",
            "odd": 1.80,
            "features": {
                "exploracao_sombra": {
                    "versao": METODO,
                    "telegram_oficial": False,
                    "aplicacao_automatica": False,
                },
                "gol_antecipado": {
                    "minuto": 20,
                    "linhagem_sha256": "sha",
                },
                "gol_antecipado_ht": {
                    "confirmado": True,
                    "total_gols_amostra_faixa": 12,
                },
                "qualidade_dados": 100,
                "odds_cache": False,
                "idade_odds_segundos": 5,
                "chutes_no_gol": [chutes_no_gol, 0],
                "chutes_no_gol_total": chutes_no_gol,
                "janelas": {"5": {
                    "disponivel": True,
                    "duracao_real_minutos": 5,
                    "resets_detectados": [],
                    "chutes": [2, 0],
                    "chutes_total": 2,
                }},
            },
        }

    def test_gateway_aplica_filtro_e_circuit_breaker_exatos(self):
        with patch.dict("os.environ", {ROLLBACK: "1"}, clear=False):
            self.assertIn(
                "chutes_no_gol_insuficientes",
                motivo_suspensao_simulacao(self._candidato(1)),
            )
            with patch(
                "telegram_alertas.filtro_gol_ht_preciso_liberado",
                return_value=False,
            ):
                self.assertEqual(
                    "circuit_breaker_filtro_gol_ht_antecipado_preciso",
                    motivo_suspensao_simulacao(self._candidato()),
                )


if __name__ == "__main__":
    unittest.main()
