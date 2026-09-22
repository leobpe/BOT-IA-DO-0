import unittest

from previsao_gols_provedor import (
    interpretar_previsao_gols, linha_over_prevista, total_gols_esperados,
)


class PrevisaoGolsProvedorTest(unittest.TestCase):
    def test_distingue_sinal_positivo_e_negativo(self):
        for valor in ("+2.5", " +2,5 ", "+ 2.5", "Over 2.5", "mais de 2,5 gols", "OVER 2.5 goals", "＋２.５"):
            with self.subTest(valor=valor):
                self.assertEqual({"direcao": "over", "linha": 2.5}, interpretar_previsao_gols(valor))
                self.assertEqual(2.5, linha_over_prevista(valor))
        for valor in ("-2.5", "−2,5", " - 2.5 ", "Under 2.5", "menos de 2,5 gols", "UNDER 2.5 goals"):
            with self.subTest(valor=valor):
                self.assertEqual({"direcao": "under", "linha": 2.5}, interpretar_previsao_gols(valor))
                self.assertIsNone(linha_over_prevista(valor))

    def test_nao_adivinha_direcao_em_numeros_ou_textos_ambiguos(self):
        for valor in (None, True, 2.5, -2.5, {}, [], "", "2.5", "2,5", "nan", "+inf", "under -2.5", "over -2.5", "over 2.5 @ 1.60", "-2.5/+3.5", "+2.5 ou -3.5", "Over 2.5 Under 3.5", "+0", "+-2.5"):
            with self.subTest(valor=valor):
                self.assertIsNone(interpretar_previsao_gols(valor))

    def test_soma_medias_pontuais_completas(self):
        self.assertEqual(2.5, total_gols_esperados({"home": 1.5, "away": 1.0}))
        self.assertEqual(2.5, total_gols_esperados({"home": "1,5", "away": "1.0"}))
        self.assertEqual(0.0, total_gols_esperados({"home": 0, "away": 0}))

    def test_faixas_nao_sao_gols_esperados_nem_zero(self):
        for valor in ("-2.5", "−2.5", "+2.5", "Over 2.5", "Under 2.5", None, True, -1, float("nan"), float("inf"), "", "25%"):
            with self.subTest(valor=valor):
                self.assertIsNone(total_gols_esperados({"home": 3.0, "away": valor}))
        for valor in ({}, None, [], {"home": 2.5}, {"away": 2.5}, {"home": 1.5, "away": 1.5, "total": 3}):
            self.assertIsNone(total_gols_esperados(valor))


if __name__ == "__main__":
    unittest.main()
