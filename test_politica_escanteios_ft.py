import unittest

from politica_escanteios_ft import aplicar_politica_escanteios_ft
from versoes_regras import (
    VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
    VERSAO_PROXIMO_ESCANTEIO_MAX_86,
)


class PoliticaEscanteiosFTTest(unittest.TestCase):
    def candidato(self, idade=120, bloqueios=None, minuto=86):
        return {
            "mercado": "escanteios_ft_asiatico",
            "odd": 1.85,
            "pontuacao_tecnica": 82,
            "idade_odds_segundos": idade,
            "bloqueios": list(
                bloqueios
                if bloqueios is not None
                else ["odds_desatualizadas"]
            ),
            "status": "rejeitado",
            "regra_versao": "sinais-v6",
            "features": {"minuto": minuto},
        }

    def test_oferta_fresca_nao_herda_idade_de_outro_mercado(self):
        candidato = aplicar_politica_escanteios_ft(self.candidato())

        self.assertEqual(
            candidato["regra_versao"],
            VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
        )
        self.assertNotIn(
            "odds_desatualizadas", candidato["bloqueios"]
        )
        self.assertEqual(candidato["status"], "aprovado")

    def test_oferta_realmente_vencida_permanece_bloqueada(self):
        candidato = aplicar_politica_escanteios_ft(
            self.candidato(idade=361)
        )

        self.assertIn("odds_desatualizadas", candidato["bloqueios"])
        self.assertEqual(candidato["status"], "rejeitado")

    def test_outro_bloqueio_nao_e_afrouxado(self):
        candidato = aplicar_politica_escanteios_ft(
            self.candidato(
                bloqueios=[
                    "odds_desatualizadas",
                    "historico_5min_insuficiente",
                ]
            )
        )

        self.assertNotIn(
            "odds_desatualizadas", candidato["bloqueios"]
        )
        self.assertIn(
            "historico_5min_insuficiente", candidato["bloqueios"]
        )
        self.assertEqual(candidato["status"], "rejeitado")

    def test_outro_mercado_nao_e_alterado(self):
        candidato = self.candidato()
        candidato["mercado"] = "gol_ft"
        original = candidato.copy()

        aplicar_politica_escanteios_ft(candidato)

        self.assertEqual(candidato, original)

    def test_minuto_86_permanece_elegivel_no_asiatico(self):
        candidato = aplicar_politica_escanteios_ft(
            self.candidato(bloqueios=[], minuto=86)
        )

        self.assertEqual(candidato["status"], "aprovado")

    def test_minuto_87_e_bloqueado_no_asiatico(self):
        candidato = aplicar_politica_escanteios_ft(
            self.candidato(bloqueios=[], minuto=87)
        )

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn(
            "fora_da_janela_escanteios_max_86",
            candidato["bloqueios"],
        )

    def test_proximo_escanteio_usa_nova_linhagem_e_bloqueia_87(self):
        candidato = self.candidato(bloqueios=[], minuto=87)
        candidato["mercado"] = "proximo_escanteio"
        candidato["status"] = "aprovado"

        aplicar_politica_escanteios_ft(candidato)

        self.assertEqual(
            candidato["regra_versao"],
            VERSAO_PROXIMO_ESCANTEIO_MAX_86,
        )
        self.assertEqual(candidato["status"], "rejeitado")

    def test_proximo_escanteio_no_minuto_86_permanece_aprovado(self):
        candidato = self.candidato(bloqueios=[], minuto=86)
        candidato["mercado"] = "proximo_escanteio"
        candidato["status"] = "aprovado"

        aplicar_politica_escanteios_ft(candidato)

        self.assertEqual(candidato["status"], "aprovado")


if __name__ == "__main__":
    unittest.main()
