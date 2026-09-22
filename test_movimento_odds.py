import unittest

from movimento_odds import calcular_movimento_odds, movimento_para
from normalizador_odds import estruturar_odds


class MovimentoOddsTest(unittest.TestCase):
    @staticmethod
    def odds(valor):
        return {
            "ao_vivo": [
                {
                    "categoria": "gols",
                    "ofertas": [
                        {"linha": 2.5, "over": valor, "under": 2.0}
                    ],
                }
            ]
        }

    def test_detecta_queda_da_odd_na_mesma_linha(self):
        movimentos = calcular_movimento_odds(
            self.odds(2.1), self.odds(1.8)
        )
        self.assertEqual(movimentos[0]["delta"], -0.3)
        self.assertEqual(movimentos[0]["direcao"], "queda")

    def test_nao_compara_linhas_diferentes(self):
        atuais = self.odds(1.8)
        atuais["ao_vivo"][0]["ofertas"][0]["linha"] = 3.5
        self.assertEqual(calcular_movimento_odds(self.odds(2.1), atuais), [])

    def test_localiza_movimento_por_mercado(self):
        odds = self.odds(1.8)
        odds["movimentacao"] = calcular_movimento_odds(
            self.odds(2.0), odds
        )
        self.assertEqual(
            movimento_para(odds, "gols", 2.5)["direcao"], "queda"
        )

    def test_exactly_nao_contamina_movimento_asiatico(self):
        def odds(odd_over):
            return estruturar_odds({
                "ao_vivo": [{
                    "mercado": "Escanteios Exactly",
                    "dados": (
                        "Escanteios Exactly Over Under "
                        f"8 7.00 {odd_over:.2f} 3.75"
                    ),
                }]
            })

        self.assertEqual(calcular_movimento_odds(odds(1.44), odds(1.60)), [])

    def test_total_nao_colide_com_gols_de_cada_time(self):
        def odds(total, casa, visitante):
            return {
                "ao_vivo": [
                    {
                        "categoria": "gols", "escopo": "total",
                        "ofertas": [{"linha": 2.5, "over": total, "under": 2.0}],
                    },
                    {
                        "categoria": "gols", "escopo": "time_casa",
                        "ofertas": [{"linha": 2.5, "over": casa, "under": 2.0}],
                    },
                    {
                        "categoria": "gols", "escopo": "time_visitante",
                        "ofertas": [{"linha": 2.5, "over": visitante, "under": 2.0}],
                    },
                ]
            }

        atual = odds(1.80, 4.0, 5.0)
        atual["movimentacao"] = calcular_movimento_odds(
            odds(2.00, 3.0, 6.0), atual
        )

        self.assertEqual(
            movimento_para(atual, "gols", 2.5)["delta"], -0.2
        )
        self.assertEqual(len(atual["movimentacao"]), 3)

    def test_total_normal_nao_colide_com_asiatico(self):
        anteriores = {
            "ao_vivo": [
                {
                    "categoria": "escanteios",
                    "escopo": "total",
                    "tipo_mercado": "total",
                    "ofertas": [
                        {"linha": 8.0, "over": 2.0, "under": 1.8}
                    ],
                },
                {
                    "categoria": "escanteios",
                    "escopo": "total",
                    "tipo_mercado": "asiatico",
                    "ofertas": [
                        {"linha": 8.0, "over": 1.9, "under": 1.9}
                    ],
                },
            ]
        }
        atuais = {
            "ao_vivo": [
                {
                    "categoria": "escanteios",
                    "escopo": "total",
                    "tipo_mercado": "total",
                    "ofertas": [
                        {"linha": 8.0, "over": 1.8, "under": 2.0}
                    ],
                },
                {
                    "categoria": "escanteios",
                    "escopo": "total",
                    "tipo_mercado": "asiatico",
                    "ofertas": [
                        {"linha": 8.0, "over": 2.1, "under": 1.7}
                    ],
                },
            ]
        }
        movimentos = calcular_movimento_odds(anteriores, atuais)

        self.assertEqual(len(movimentos), 2)
        self.assertEqual(
            movimento_para(
                {"movimentacao": movimentos},
                "escanteios",
                8.0,
                tipo_mercado="total",
            )["delta"],
            -0.2,
        )
        self.assertEqual(
            movimento_para(
                {"movimentacao": movimentos},
                "escanteios",
                8.0,
                tipo_mercado="asiatico",
            )["delta"],
            0.2,
        )

    def test_movimento_proximo_gol_preserva_tipo_e_lado(self):
        def odds(casa, visitante):
            return {
                "ao_vivo": [{
                    "categoria": "gols",
                    "escopo": "proximo",
                    "tipo_mercado": "proximo",
                    "selecoes": {
                        "casa": casa,
                        "visitante": visitante,
                    },
                }]
            }

        movimentos = calcular_movimento_odds(
            odds(2.0, 3.0),
            odds(1.8, 3.2),
        )

        self.assertEqual(len(movimentos), 2)
        por_lado = {item["linha"]: item for item in movimentos}
        self.assertEqual(por_lado["casa"]["delta"], -0.2)
        self.assertEqual(por_lado["visitante"]["delta"], 0.2)
        self.assertTrue(
            all(
                item["tipo_mercado"] == "proximo"
                for item in movimentos
            )
        )


if __name__ == "__main__":
    unittest.main()
