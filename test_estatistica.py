import unittest

from estatistica import (
    discriminacao_pontuacao,
    estado_amostra,
    intervalo_wilson,
)


class EstatisticaTest(unittest.TestCase):
    def test_auc_mede_ordenacao_da_pontuacao(self):
        perfeita = discriminacao_pontuacao([
            {"pontuacao_tecnica": 90, "resultado": "green"},
            {"pontuacao_tecnica": 80, "resultado": "green"},
            {"pontuacao_tecnica": 70, "resultado": "red"},
            {"pontuacao_tecnica": 60, "resultado": "red"},
        ])
        acaso_por_empate = discriminacao_pontuacao([
            {"pontuacao_tecnica": 80, "resultado": "green"},
            {"pontuacao_tecnica": 80, "resultado": "red"},
        ])

        self.assertEqual(perfeita["auc"], 1.0)
        self.assertEqual(perfeita["intervalo_auc_95"], [1.0, 1.0])
        self.assertEqual(acaso_por_empate["auc"], 0.5)
        self.assertLessEqual(
            acaso_por_empate["limite_inferior_auc_95"], 0.5
        )

    def test_intervalo_de_amostra_pequena_e_amplo(self):
        inferior, superior = intervalo_wilson(1, 2)
        self.assertLess(inferior, 0.2)
        self.assertGreater(superior, 0.8)

    def test_estado_da_amostra(self):
        self.assertEqual(estado_amostra(2), "inconclusiva")
        self.assertEqual(estado_amostra(50), "pre_validacao")
        self.assertEqual(estado_amostra(100), "validavel")
