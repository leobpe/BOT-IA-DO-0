import unittest

from politica_gols_tempo import aplicar_politica_gols_tempo


class PoliticaGolsTempoTest(unittest.TestCase):
    def candidato(self, mercado, minuto):
        return {"mercado": mercado, "status": "aprovado", "bloqueios": [], "features": {"minuto": minuto}}

    def test_ft_sem_minimo_e_com_teto_82(self):
        self.assertEqual("aprovado", aplicar_politica_gols_tempo(self.candidato("gol_ft", 3))["status"])
        self.assertEqual("rejeitado", aplicar_politica_gols_tempo(self.candidato("gol_ft", 83))["status"])

    def test_ht_sem_minimo_e_com_teto_28(self):
        self.assertEqual("aprovado", aplicar_politica_gols_tempo(self.candidato("gol_ht", 2))["status"])
        self.assertEqual("rejeitado", aplicar_politica_gols_tempo(self.candidato("gol_ht", 29))["status"])

    def test_outro_mercado_nao_muda(self):
        candidato = self.candidato("proximo_gol", 90)
        self.assertIs(candidato, aplicar_politica_gols_tempo(candidato))
        self.assertEqual("aprovado", candidato["status"])


if __name__ == "__main__":
    unittest.main()
