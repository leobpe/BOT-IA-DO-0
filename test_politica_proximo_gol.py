import unittest

from politica_proximo_gol_faixa_global import (
    MOTIVO_MINUTO,
    MOTIVO_ODD,
    aplicar_politica_proximo_gol,
)
from versoes_challengers_global import (
    VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
    versao_regra_operacional,
    versoes_regras_operacionais,
)


class PoliticaProximoGolTests(unittest.TestCase):
    def _candidato(self, odd=1.40, minuto=75):
        return {
            "mercado": "proximo_gol",
            "regra_versao": "sinais-v6",
            "odd": odd,
            "features": {"minuto": minuto},
            "motivos": [],
            "bloqueios": [],
            "status": "aprovado",
        }

    def test_limites_exatos_permanecem_elegiveis(self):
        candidato = aplicar_politica_proximo_gol(self._candidato())

        self.assertEqual(candidato["status"], "aprovado")
        self.assertEqual(
            candidato["regra_versao"],
            VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
        )
        self.assertFalse(candidato["bloqueios"])

    def test_odd_abaixo_da_faixa_global_rejeita(self):
        candidato = aplicar_politica_proximo_gol(
            self._candidato(odd=1.39)
        )

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn(MOTIVO_ODD, candidato["bloqueios"])

    def test_minuto_acima_do_corte_rejeita(self):
        candidato = aplicar_politica_proximo_gol(
            self._candidato(minuto=76)
        )

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn(MOTIVO_MINUTO, candidato["bloqueios"])

    def test_outro_mercado_nao_e_alterado(self):
        candidato = self._candidato()
        candidato["mercado"] = "gol_ft"
        original = dict(candidato)

        self.assertEqual(aplicar_politica_proximo_gol(candidato), original)

    def test_versao_operacional_e_listada(self):
        self.assertEqual(
            versao_regra_operacional("proximo_gol"),
            VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
        )
        self.assertIn(
            VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
            versoes_regras_operacionais(),
        )


if __name__ == "__main__":
    unittest.main()
