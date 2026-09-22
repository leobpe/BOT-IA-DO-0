import json
import unittest
from datetime import datetime
from pathlib import Path

from controle_v2b_ft import (
    ativar_v2b_ft,
    ler_estado_v2b_ft,
    suspender_v2b_ft,
    v2b_ft_grupo_liberado,
)


class ControleV2bFtTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_v2b_ft_estado.json"
        self.caminho.unlink(missing_ok=True)

    def tearDown(self):
        self.caminho.unlink(missing_ok=True)

    def test_ausencia_preserva_ativacao_atual(self):
        estado = ler_estado_v2b_ft(self.caminho)
        self.assertTrue(estado["saudavel"])
        self.assertTrue(estado["ativo"])
        self.assertTrue(v2b_ft_grupo_liberado(self.caminho))

    def test_suspensao_automatica_e_persistente_e_idempotente(self):
        primeiro = suspender_v2b_ft(
            "versao|ancora",
            "ic95_roi_integralmente_negativo",
            {"validos": 20, "roi": -0.31},
            self.caminho,
            datetime(2026, 8, 26, 22, 0),
        )
        segundo = suspender_v2b_ft(
            "versao|ancora",
            "ic95_roi_integralmente_negativo",
            {"validos": 20, "roi": -0.31},
            self.caminho,
            datetime(2026, 8, 26, 22, 1),
        )

        self.assertFalse(primeiro["ativo"])
        self.assertEqual(primeiro["estado"], "sombra_automatico")
        self.assertTrue(primeiro["alterado"])
        self.assertFalse(segundo["alterado"])
        self.assertTrue(segundo["idempotente"])
        self.assertFalse(v2b_ft_grupo_liberado(self.caminho))

    def test_reativacao_manual_e_reversivel(self):
        suspender_v2b_ft(
            "manual", "suspensao_manual", caminho=self.caminho,
            automatico=False,
        )
        estado = ativar_v2b_ft(
            self.caminho,
            datetime(2026, 8, 26, 22, 5),
        )

        self.assertTrue(estado["ativo"])
        self.assertEqual(estado["estado"], "ativo_manual")
        self.assertTrue(v2b_ft_grupo_liberado(self.caminho))

    def test_estado_corrompido_falha_fechado_so_para_v2b(self):
        self.caminho.write_text("{quebrado", encoding="utf-8")
        estado = ler_estado_v2b_ft(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertFalse(estado["ativo"])
        self.assertFalse(v2b_ft_grupo_liberado(self.caminho))

    def test_estado_com_versao_incompativel_falha_fechado(self):
        self.caminho.write_text(
            json.dumps({"versao": "antiga", "ativo": True}),
            encoding="utf-8",
        )
        estado = ler_estado_v2b_ft(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertFalse(estado["ativo"])


if __name__ == "__main__":
    unittest.main()
