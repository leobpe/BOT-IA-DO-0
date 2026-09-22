import json
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from controle_pre_live_preciso import (
    VERSAO_CONTROLE,
    aplicar_validacao,
    ativar,
    entrega_liberada,
    ler_estado,
    suspender,
)


class ControlePreLivePrecisoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / (
            f".teste_controle_pre_live_preciso_{uuid4().hex}.json"
        )
        self.agora = datetime(2026, 9, 9, 18, 0, 0)

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
            "validacao|ancora|sha",
            "evidencia_negativa",
            caminho=self.caminho,
            agora=self.agora,
        )
        repetido = suspender(
            "validacao|ancora|sha",
            "evidencia_negativa",
            caminho=self.caminho,
            agora=self.agora,
        )
        self.assertTrue(primeiro["alterado"])
        self.assertTrue(repetido["idempotente"])
        self.assertFalse(entrega_liberada(self.caminho))
        reativado = ativar(caminho=self.caminho, agora=self.agora)
        self.assertTrue(reativado["alterado"])
        self.assertTrue(entrega_liberada(self.caminho))

    def test_aplica_somente_checkpoint_negativo_ou_coorte_concluida(self):
        base = {
            "versao": "validacao",
            "registrado_em": "2026-09-09T18:00:00",
            "definicao_sha256": "sha",
            "alerta_desfavoravel": False,
            "resultados_completos": False,
        }
        ativo = aplicar_validacao(
            base, caminho=self.caminho, agora=self.agora
        )
        self.assertTrue(ativo["ativo"])

        negativo = aplicar_validacao(
            {
                **base,
                "alerta_desfavoravel": True,
                "validos": 25,
                "greens": 0,
                "reds": 25,
                "roi": -1.0,
            },
            caminho=self.caminho,
            agora=self.agora,
        )
        self.assertFalse(negativo["ativo"])
        self.assertEqual(
            "ic95_roi_checkpoint_25_integralmente_negativo",
            negativo["motivo"],
        )

    def test_estado_incompativel_nao_e_sobrescrito(self):
        self.caminho.write_text(json.dumps({
            "versao": VERSAO_CONTROLE,
            "ativo": "sim",
        }), encoding="utf-8")
        resultado = suspender(
            "assinatura", "motivo", caminho=self.caminho
        )
        self.assertFalse(resultado["saudavel"])
        self.assertFalse(resultado["alterado"])

    def test_validacao_inconsistente_falha_fechado(self):
        resultado = aplicar_validacao(
            {
                "versao": "validacao-pre-live-v1",
                "saudavel": False,
                "registrado_em": "2026-09-09T18:00:00",
                "definicao_sha256": "sha",
            },
            caminho=self.caminho,
            agora=self.agora,
        )

        self.assertFalse(resultado["ativo"])
        self.assertEqual(
            "validacao_pre_live_preciso_inconsistente",
            resultado["motivo"],
        )


if __name__ == "__main__":
    unittest.main()
