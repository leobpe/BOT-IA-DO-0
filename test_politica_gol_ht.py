import unittest

from politica_gol_ht import aplicar_politica_gol_ht
from versoes_operacionais import (
    VERSAO_GOL_HT_MAX_28,
    versao_regra_operacional,
    versoes_regras_operacionais,
)
from versoes_regras import VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86


class PoliticaGolHTTest(unittest.TestCase):
    def candidato(self, minuto):
        return {
            "mercado": "gol_ht",
            "status": "aprovado",
            "bloqueios": [],
            "features": {"minuto": minuto},
            "regra_versao": "sinais-v6",
        }

    def test_minuto_28_permanece_elegivel(self):
        candidato = aplicar_politica_gol_ht(self.candidato(28))

        self.assertEqual(candidato["status"], "aprovado")
        self.assertEqual(candidato["regra_versao"], VERSAO_GOL_HT_MAX_28)
        self.assertNotIn(
            "fora_da_janela_gol_ht_max_28", candidato["bloqueios"]
        )

    def test_minuto_29_e_bloqueado(self):
        candidato = aplicar_politica_gol_ht(self.candidato(29))

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertEqual(candidato["regra_versao"], VERSAO_GOL_HT_MAX_28)
        self.assertIn(
            "fora_da_janela_gol_ht_max_28", candidato["bloqueios"]
        )

    def test_outro_mercado_nao_e_alterado(self):
        candidato = self.candidato(40)
        candidato["mercado"] = "gol_ft"
        original = candidato.copy()

        aplicar_politica_gol_ht(candidato)

        self.assertEqual(candidato, original)

    def test_mapeamento_preserva_asiatico_e_isola_gol_ht(self):
        self.assertEqual(
            versao_regra_operacional("gol_ht"), VERSAO_GOL_HT_MAX_28
        )
        self.assertEqual(
            versao_regra_operacional("escanteios_ft_asiatico"),
            VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
        )
        self.assertIn(
            VERSAO_GOL_HT_MAX_28, versoes_regras_operacionais()
        )
