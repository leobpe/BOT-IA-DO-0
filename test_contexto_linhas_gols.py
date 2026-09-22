import unittest

from contexto_linhas_gols import coletar_contexto_linhas_gols


class _API:
    def _lista_contexto(self, chave, caminho, parametros, ttl, prazo):
        time_id = parametros["team"]
        itens = []
        for indice, total in enumerate((1, 2, 3, 4, 5, 0)):
            em_casa = indice < 4
            casa_id, fora_id = (
                (time_id, 9000 + indice) if em_casa
                else (9000 + indice, time_id)
            )
            itens.append({
                "fixture": {"timestamp": 1000 - indice},
                "teams": {"home": {"id": casa_id}, "away": {"id": fora_id}},
                "goals": {"home": total, "away": 0},
                "score": {"halftime": {"home": min(total, 2), "away": 0}},
            })
        return itens


class ContextoLinhasGolsTest(unittest.TestCase):
    def test_calcula_taxa_por_linha_e_mando(self):
        contexto = coletar_contexto_linhas_gols(
            _API(),
            {"times": {"home": {"id": 1}, "away": {"id": 2}}},
            {"preservado": True},
        )
        self.assertTrue(contexto["preservado"])
        casa = contexto["tendencia_linhas_gols_v1"]["recentes"]["mandante"]
        self.assertEqual(6, casa["geral"]["jogos"])
        self.assertEqual(4, casa["mando"]["jogos"])
        self.assertEqual(0.8333, casa["geral"]["over_0_5_taxa"])
        self.assertEqual(0.5, casa["geral"]["over_2_5_taxa"])
        self.assertEqual(0.1667, casa["geral"]["over_4_5_taxa"])
        self.assertEqual(1.0, casa["mando"]["ht_over_0_5_taxa"])
        self.assertEqual(0.75, casa["mando"]["ht_over_1_5_taxa"])


if __name__ == "__main__":
    unittest.main()
