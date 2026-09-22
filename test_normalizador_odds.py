import unittest
import json
from pathlib import Path

from normalizador_odds import (
    escolher_proximo_gol,
    escolher_over_ht,
    escolher_over_ao_vivo,
    escolher_over_periodo,
    estruturar_mercado,
    estruturar_odds,
)


class NormalizadorOddsTest(unittest.TestCase):
    def test_fixture_salva_do_packball(self):
        caminho = Path(__file__).parent / "fixtures" / "odds_packball.json"
        odds = estruturar_odds(json.loads(caminho.read_text(encoding="utf-8")))
        self.assertEqual(len(odds["ao_vivo"]), 3)
        self.assertEqual(odds["ao_vivo"][2]["categoria"], "escanteios")
        self.assertEqual(escolher_over_ht(odds)["linha"], 0.5)

    def test_extrai_linha_over_e_under(self):
        mercado = estruturar_mercado(
            {
                "mercado": "Total Gols",
                "dados": "Total Gols Over Under 3.5 1.72 2.00",
            }
        )
        self.assertEqual(mercado["categoria"], "gols")
        self.assertEqual(
            mercado["ofertas"][0],
            {"linha": 3.5, "over": 1.72, "under": 2.0},
        )

    def test_classifica_escanteios_com_acento(self):
        odds = estruturar_odds(
            {
                "ao_vivo": [
                    {
                        "mercado": "Escanteios - 2 Opções",
                        "dados": "Over Under 11.5 1.66 2.10",
                    }
                ]
            }
        )
        oferta = escolher_over_ao_vivo(odds, "escanteios")
        self.assertEqual(oferta["linha"], 11.5)
        self.assertEqual(oferta["over"], 1.66)

    def test_mercado_sem_padrao_fica_sem_ofertas(self):
        mercado = estruturar_mercado(
            {"mercado": "Próximo Gol", "dados": "1: 1.50 2: 3.00"}
        )
        self.assertEqual(mercado["ofertas"], [])

    def test_extrai_odds_do_proximo_gol(self):
        odds = estruturar_odds(
            {
                "ao_vivo": [
                    {
                        "mercado": "Marcar O Próximo Gol",
                        "dados": "Marcar O Próximo Gol 1: 1.36 2: 6.00 No : 4.50",
                    }
                ]
            }
        )
        self.assertEqual(
            escolher_proximo_gol(odds, "visitante"),
            {"linha": "visitante", "over": 6.0},
        )

    def test_extrai_linha_de_gol_ht_separadamente(self):
        odds = estruturar_odds(
            {
                "ao_vivo": [
                    {
                        "mercado": "Total Gols",
                        "dados": (
                            "Total Gols Over Under 2.5 1.83 1.83 "
                            "1º Tempo Gols (HT) Over Under 0.5 1.36 3.00"
                        ),
                    }
                ]
            }
        )
        self.assertEqual(
            escolher_over_ht(odds),
            {"linha": 0.5, "over": 1.36, "under": 3.0},
        )

    def test_separa_exactly_total_e_escanteios_por_tempo(self):
        odds = estruturar_odds(
            {
                "ao_vivo": [{
                    "mercado": "Escanteios Exactly",
                    "dados": (
                        "Escanteios Exactly Over Under "
                        "8 7.00 1.44 3.75 9 6.50 1.80 2.62 "
                        "1º Tempo Escanteios (HT) Exactly Over Under "
                        "4 4.33 1.95 3.00 "
                        "2º Tempo Escanteios Exactly Over Under "
                        "5 5.00 2.10 2.20"
                    ),
                }]
            }
        )
        mercado = odds["ao_vivo"][0]

        self.assertEqual(mercado["formato"], "tres_opcoes_exactly")
        self.assertEqual(mercado["ofertas"], [])
        self.assertEqual(
            mercado["ofertas_exatamente"][0],
            {"linha": 8.0, "exatamente": 7.0, "over": 1.44, "under": 3.75},
        )
        self.assertEqual(
            mercado["ofertas_periodos"]["1T"]["ofertas"][0],
            {"linha": 4.0, "exatamente": 4.33, "over": 1.95, "under": 3.0},
        )
        self.assertEqual(
            mercado["ofertas_periodos"]["2T"]["ofertas"][0],
            {"linha": 5.0, "exatamente": 5.0, "over": 2.1, "under": 2.2},
        )
        self.assertIsNone(escolher_over_periodo(odds, "escanteios", "1T"))

    def test_seleciona_periodo_apenas_quando_tem_duas_opcoes(self):
        odds = estruturar_odds(
            {
                "ao_vivo": [{
                    "mercado": "Escanteios - 2 Opções",
                    "dados": (
                        "Escanteios - 2 Opções Over Under 9.5 1.80 1.90 "
                        "1º Tempo Escanteios (HT) Over Under 4.5 1.75 2.00"
                    ),
                }]
            }
        )

        self.assertEqual(
            escolher_over_periodo(odds, "escanteios", "1T"),
            {
                "linha": 4.5,
                "over": 1.75,
                "under": 2.0,
                "tipo_mercado": "total",
            },
        )

    def test_diferencia_total_normal_asiatico_e_exactly(self):
        mercados = [
            estruturar_mercado({
                "mercado": "Escanteios - 2 Opções",
                "dados": "Over Under 8.5 1.80 2.00",
            }),
            estruturar_mercado({
                "mercado": "Escanteios Asiáticos",
                "dados": "Over Under 8 1.90 1.90",
            }),
            estruturar_mercado({
                "mercado": "Escanteios Exactly",
                "dados": "Exactly Over Under 8 4.00 1.80 2.00",
            }),
        ]

        self.assertEqual(
            [item["tipo_mercado"] for item in mercados],
            ["total", "asiatico", "exactly"],
        )

    def test_extrai_todas_as_linhas_de_duas_opcoes(self):
        mercado = estruturar_mercado(
            {
                "mercado": "Total Gols",
                "dados": "Total Gols Over Under 1.5 1.30 3.20 2.5 1.80 1.90",
            }
        )

        self.assertEqual([item["linha"] for item in mercado["ofertas"]], [1.5, 2.5])

    def test_escolhe_somente_linha_vencida_com_um_evento(self):
        odds = {
            "ao_vivo": [{
                "categoria": "gols",
                "escopo": "total",
                "formato": "duas_opcoes",
                "ofertas": [
                    {"linha": 0.5, "over": 1.1, "under": 6.0},
                    {"linha": 1.5, "over": 1.8, "under": 2.0},
                    {"linha": 2.5, "over": 3.2, "under": 1.3},
                ],
            }]
        }

        oferta = escolher_over_ao_vivo(odds, "gols", total_atual=1)

        self.assertEqual(oferta["linha"], 1.5)

    def test_rejeita_linha_que_exige_dois_eventos(self):
        odds = {
            "ao_vivo": [{
                "categoria": "gols",
                "ofertas": [{"linha": 2.5, "over": 1.8, "under": 2.0}],
            }]
        }

        self.assertIsNone(
            escolher_over_ao_vivo(odds, "gols", total_atual=0)
        )

if __name__ == "__main__":
    unittest.main()
