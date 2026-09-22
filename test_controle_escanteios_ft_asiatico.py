import json
import unittest
from pathlib import Path
from uuid import uuid4

from controle_escanteios_ft_asiatico import (
    aplicar_validacao,
    entrega_liberada,
    ler_estado,
)
from telegram_alertas import motivo_circuit_breaker_escanteios_ft_asiatico
from unittest.mock import patch
from versoes_regras import VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86


class ControleEscanteiosFtAsiaticoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / (
            f".teste_controle_escanteios_ft_{uuid4().hex}.json"
        )

    def tearDown(self):
        self.caminho.unlink(missing_ok=True)
        for temporario in self.caminho.parent.glob(
            f".{self.caminho.name}.*.tmp"
        ):
            temporario.unlink(missing_ok=True)

    def test_ausencia_e_estado_ativo_saudavel(self):
        self.assertTrue(entrega_liberada(self.caminho))
        self.assertEqual(
            ler_estado(self.caminho)["estado"], "ativo_padrao"
        )

    def test_checkpoint_negativo_suspende_apenas_o_braco(self):
        validacao = {
            "versao": "v1", "saudavel": True,
            "registrado_em": "2026-09-09T12:00:00+00:00",
            "definicao_sha256": "a" * 64,
            "alerta_desfavoravel": True,
            "resultados_completos": False,
            "validos": 25, "greens": 5, "reds": 20,
            "roi": -0.6, "intervalo_roi_95": [-0.8, -0.2],
        }
        estado = aplicar_validacao(validacao, caminho=self.caminho)
        self.assertFalse(estado["ativo"])
        self.assertEqual(estado["estado"], "suspenso_automatico")
        self.assertFalse(entrega_liberada(self.caminho))

    def test_estado_corrompido_falha_fechado(self):
        self.caminho.write_text("{", encoding="utf-8")
        estado = ler_estado(self.caminho)
        self.assertFalse(estado["saudavel"])
        self.assertFalse(estado["ativo"])

    def test_conclusao_suspende_sem_promocao(self):
        estado = aplicar_validacao({
            "versao": "v1", "saudavel": True,
            "registrado_em": "2026-09-09T12:00:00+00:00",
            "definicao_sha256": "b" * 64,
            "alerta_desfavoravel": False,
            "resultados_completos": True,
            "validos": 100,
        }, caminho=self.caminho)
        self.assertFalse(estado["ativo"])
        documento = json.loads(self.caminho.read_text(encoding="utf-8"))
        self.assertIn("revisao_manual", documento["motivo"])

    def test_gateway_isola_mercado_e_versao_exatos(self):
        candidato = {
            "mercado": "escanteios_ft_asiatico",
            "regra_versao": VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
        }
        with patch(
            "telegram_alertas.escanteios_ft_asiatico_liberado",
            return_value=False,
        ):
            self.assertEqual(
                motivo_circuit_breaker_escanteios_ft_asiatico(candidato),
                "circuit_breaker_escanteios_ft_asiatico",
            )
            self.assertIsNone(
                motivo_circuit_breaker_escanteios_ft_asiatico({
                    **candidato, "mercado": "proximo_escanteio",
                })
            )
            self.assertIsNone(
                motivo_circuit_breaker_escanteios_ft_asiatico({
                    **candidato, "regra_versao": "legada",
                })
            )


if __name__ == "__main__":
    unittest.main()
