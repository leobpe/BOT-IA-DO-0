import unittest

from contexto_periodos_10 import coletar_contexto_periodos_10


def _partidas(time_id, em_casa, quantidade=12):
    itens = []
    for indice in range(quantidade):
        casa_id, fora_id = (
            (time_id, 9000 + indice)
            if em_casa else (9000 + indice, time_id)
        )
        itens.append({
            "fixture": {"timestamp": 100000 - indice},
            "teams": {"home": {"id": casa_id}, "away": {"id": fora_id}},
            "goals": {"home": 2, "away": 1},
            "score": {"halftime": {"home": 1, "away": 0}},
        })
    return itens


class _API:
    def __init__(self):
        self.chamadas = []

    def _lista_contexto(self, chave, caminho, parametros, ttl, prazo):
        self.chamadas.append(parametros)
        time_id = parametros["team"]
        return _partidas(time_id, time_id == 1)


class ContextoPeriodos10Test(unittest.TestCase):
    def test_separa_dez_jogos_no_mando_e_periodos(self):
        api = _API()
        contexto = coletar_contexto_periodos_10(api, {
            "times": {"home": {"id": 1}, "away": {"id": 2}},
        }, {"preservado": True})
        self.assertTrue(contexto["preservado"])
        casa = contexto["historico_periodos_10"]["mandante"]
        fora = contexto["historico_periodos_10"]["visitante"]
        self.assertEqual(10, casa["jogos"])
        self.assertEqual(10, fora["jogos"])
        self.assertEqual(1.0, casa["over_0_5_ht_taxa"])
        self.assertEqual(1.0, fora["over_1_5_ft_taxa"])
        self.assertTrue(all(x["last"] == 30 for x in api.chamadas))


if __name__ == "__main__":
    unittest.main()
