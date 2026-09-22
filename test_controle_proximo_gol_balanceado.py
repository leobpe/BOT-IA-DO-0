import json
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from controle_proximo_gol_balanceado import (
    VERSAO_CONTROLE,
    ativar,
    grupo_liberado,
    ler_estado,
    suspender,
)


class ControleProximoGolBalanceadoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / (
            f".teste_controle_proximo_gol_{uuid4().hex}.json"
        )
        self.agora = datetime(2026, 9, 9, 14, 0, 0)

    def tearDown(self):
        self.caminho.unlink(missing_ok=True)
        for temporario in self.caminho.parent.glob(
            f".{self.caminho.name}.*.tmp"
        ):
            temporario.unlink(missing_ok=True)

    def test_ausencia_libera_e_estado_corrompido_falha_fechado(self):
        self.assertTrue(grupo_liberado(self.caminho))
        self.caminho.write_text("{", encoding="utf-8")
        self.assertFalse(grupo_liberado(self.caminho))
        self.assertFalse(ler_estado(self.caminho)["saudavel"])

    def test_suspensao_e_persistente_idempotente_e_reversivel(self):
        primeiro = suspender(
            "validacao|ancora|sha",
            "ic95_roi_integralmente_negativo",
            metricas={"validos": 20, "roi": -0.4},
            caminho=self.caminho,
            agora=self.agora,
        )
        repetido = suspender(
            "validacao|ancora|sha",
            "ic95_roi_integralmente_negativo",
            caminho=self.caminho,
            agora=self.agora,
        )

        self.assertTrue(primeiro["alterado"])
        self.assertTrue(repetido["idempotente"])
        self.assertFalse(grupo_liberado(self.caminho))
        reativado = ativar(
            caminho=self.caminho,
            agora=self.agora,
        )
        self.assertTrue(reativado["alterado"])
        self.assertTrue(grupo_liberado(self.caminho))

    def test_estrutura_incompativel_nao_e_sobrescrita(self):
        self.caminho.write_text(json.dumps({
            "versao": VERSAO_CONTROLE,
            "ativo": "sim",
        }), encoding="utf-8")

        resultado = suspender(
            "assinatura",
            "motivo",
            caminho=self.caminho,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertFalse(resultado["alterado"])


if __name__ == "__main__":
    unittest.main()
