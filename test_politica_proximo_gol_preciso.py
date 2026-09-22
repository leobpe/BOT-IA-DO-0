import unittest
from unittest.mock import patch

from politica_proximo_gol_preciso import (
    MOTIVO_ODD,
    MOTIVO_PRESSAO,
    MOTIVO_QUALIDADE,
    aplicar_politica_proximo_gol,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
    versao_regra_operacional,
)


class PoliticaProximoGolPrecisoTest(unittest.TestCase):
    def _candidato(self, odd=1.99, qualidade=100, pico=70):
        return {
            "mercado": "proximo_gol",
            "regra_versao": "sinais-v6",
            "odd": odd,
            "status": "aprovado",
            "bloqueios": [],
            "motivos": [],
            "features": {
                "minuto": 60,
                "qualidade_dados": qualidade,
                "lado_dominante": "casa",
                "janelas": {"5": {"pressao_pico": [pico, 20]}},
            },
        }

    def test_limites_aprovados_e_nova_versao(self):
        candidato = aplicar_politica_proximo_gol(self._candidato())
        self.assertEqual("aprovado", candidato["status"])
        self.assertEqual(
            VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            candidato["regra_versao"],
        )
        self.assertEqual(
            VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            versao_regra_operacional("proximo_gol"),
        )

    def test_odd_2_qualidade_99_e_pressao_69_rejeitam(self):
        casos = (
            (self._candidato(odd=2.0), MOTIVO_ODD),
            (self._candidato(qualidade=99), MOTIVO_QUALIDADE),
            (self._candidato(pico=69), MOTIVO_PRESSAO),
        )
        for candidato, motivo in casos:
            with self.subTest(motivo=motivo):
                aplicar_politica_proximo_gol(candidato)
                self.assertEqual("rejeitado", candidato["status"])
                self.assertIn(motivo, candidato["bloqueios"])

    def test_rollback_reaplica_v10e(self):
        candidato = self._candidato(odd=2.0, qualidade=50, pico=10)
        with patch(
            "politica_proximo_gol_preciso.PROXIMO_GOL_FILTRO_PRECISO_ATIVO",
            False,
        ):
            aplicar_politica_proximo_gol(candidato)
        self.assertEqual("aprovado", candidato["status"])
        self.assertNotEqual(
            VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            candidato["regra_versao"],
        )


if __name__ == "__main__":
    unittest.main()
