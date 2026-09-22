import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from controle_gols_antecipados import (
    VERSAO,
    ativar_metodo,
    ler_estado,
    metodo_liberado,
    suspender_metodo,
)
from gols_antecipados import VERSAO_GOL_HT_ANTECIPADO
from telegram_alertas import motivo_suspensao_simulacao


class ControleGolsAntecipadosTest(unittest.TestCase):
    def setUp(self):
        self.caminho = (
            Path.cwd() / f".teste_controle_gols_{uuid4().hex}.json"
        )
        self.agora = datetime(2026, 9, 8, 20, 0, 0)

    def tearDown(self):
        self.caminho.unlink(missing_ok=True)
        for temporario in self.caminho.parent.glob(
            f".{self.caminho.name}.*.tmp"
        ):
            temporario.unlink(missing_ok=True)

    def test_ausencia_preserva_metodo_liberado(self):
        self.assertTrue(metodo_liberado("metodo-v1", self.caminho))
        self.assertTrue(ler_estado(self.caminho)["saudavel"])

    def test_estado_corrompido_falha_fechado(self):
        self.caminho.write_text("{", encoding="utf-8")

        self.assertFalse(metodo_liberado("metodo-v1", self.caminho))
        self.assertFalse(ler_estado(self.caminho)["saudavel"])

    def test_suspensao_e_isolada_idempotente_e_reversivel(self):
        primeiro = suspender_metodo(
            "metodo-v1",
            "validacao|ancora",
            "ic95_roi_integralmente_negativo",
            metricas={"validos": 100, "roi": -0.2},
            caminho=self.caminho,
            agora=self.agora,
        )
        repetido = suspender_metodo(
            "metodo-v1",
            "validacao|ancora",
            "ic95_roi_integralmente_negativo",
            caminho=self.caminho,
            agora=self.agora,
        )

        self.assertTrue(primeiro["alterado"])
        self.assertTrue(repetido["idempotente"])
        self.assertFalse(metodo_liberado("metodo-v1", self.caminho))
        self.assertTrue(metodo_liberado("metodo-v2", self.caminho))

        reativado = ativar_metodo(
            "metodo-v1", caminho=self.caminho, agora=self.agora
        )
        self.assertTrue(reativado["alterado"])
        self.assertTrue(metodo_liberado("metodo-v1", self.caminho))

    def test_estrutura_incompativel_nao_e_sobrescrita(self):
        self.caminho.write_text(json.dumps({
            "versao": VERSAO, "metodos": {"x": {"ativo": "sim"}}
        }), encoding="utf-8")

        resultado = suspender_metodo(
            "x", "a", "motivo", caminho=self.caminho
        )

        self.assertFalse(resultado["saudavel"])
        self.assertFalse(resultado["alterado"])

    def test_gateway_informa_circuit_breaker_do_braco(self):
        candidato = {
            "status": "simulacao",
            "mercado": "gol_ht",
            "features": {
                "exploracao_sombra": {
                    "versao": VERSAO_GOL_HT_ANTECIPADO,
                    "telegram_oficial": False,
                    "aplicacao_automatica": False,
                },
                "gol_antecipado": {"linhagem_sha256": "sha"},
            },
        }

        with patch(
            "telegram_alertas.metodo_antecipado_liberado",
            return_value=False,
        ):
            motivo = motivo_suspensao_simulacao(candidato)

        self.assertEqual("circuit_breaker_gol_antecipado", motivo)
