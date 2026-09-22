import unittest
from datetime import datetime, timezone

from betsapi_pre_live import (
    carregar_catalogo_bet365_pre_live,
    extrair_ofertas_bet365_pre_live,
    listar_eventos_bet365_pre_live,
    parear_evento_bet365_pre_live,
    resumir_catalogo_bet365_pre_live,
)


class APIFalsa:
    ativa = True

    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def _requisitar(self, caminho, parametros):
        self.chamadas.append((caminho, parametros))
        return self.respostas.get(
            (caminho, parametros.get("page")),
            self.respostas.get(caminho),
        )

    @staticmethod
    def _cacheado(_chave, _ttl, carregar):
        return carregar()


class BetsAPIPreLiveTest(unittest.TestCase):
    def setUp(self):
        self.evento = {
            "id": "900",
            "home": {"name": "Palmeiras"},
            "away": {"name": "Santos"},
            "time": "1788026400",
        }
        self.prematch = {
            "success": 1,
            "results": [{
                "FI": "900",
                "main": {"sp": {
                    "full_time_result": {
                        "id": "1", "name": "Full Time Result", "odds": [
                            {"id": "1a", "odds": "1.500", "name": "1"},
                            {"id": "1b", "odds": "4.000", "name": "Draw"},
                            {"id": "1c", "odds": "6.000", "name": "2"},
                        ],
                    },
                    "alternative_total_goals": {
                        "id": "2", "name": "Alternative Total Goals",
                        "odds": [
                            {"id": "2a", "odds": "1.444", "name": "1.5", "header": "Over"},
                            {"id": "2b", "odds": "2.625", "name": "1.5", "header": "Under"},
                            {"id": "2c", "odds": "1.900", "name": "2.0", "header": "Over"},
                        ],
                    },
                    "both_teams_to_score": {
                        "id": "3", "name": "Both Teams to Score", "odds": [
                            {"id": "3a", "odds": "1.800", "name": "Yes"},
                            {"id": "3b", "odds": "1.900", "name": "No"},
                        ],
                    },
                    "total_goals_both_teams_to_score": {
                        "id": "4", "name": "Total Goals/Both Teams to Score",
                        "odds": [
                            {"id": "4a", "odds": "1.600", "name": "Over 2.5 & Yes"},
                        ],
                    },
                    "match_goals_range": {
                        "id": "5", "name": "Match Goals Range", "odds": [
                            {"id": "5a", "odds": "1.550", "name": "Match Goals", "header": "Yes", "ED": "1-4"},
                        ],
                    },
                    "team_total_goals": {
                        "id": "7", "name": "Team Total Goals", "odds": [
                            {"id": "7a", "odds": "1.533", "header": "2", "handicap": "Over 0.5"},
                            {"id": "7b", "odds": "2.375", "header": "2", "handicap": "Under 0.5"},
                        ],
                    },
                }},
                "corners": {"sp": {
                    "corners_2_way": {
                        "id": "6", "name": "Corners 2-Way", "odds": [
                            {"id": "6a", "odds": "1.900", "name": "9.5", "header": "Over"},
                        ],
                    },
                }},
            }],
        }

    def test_lista_pareia_por_times_e_horario(self):
        api = APIFalsa({
            "v1/bet365/upcoming": {
                "success": 1, "results": [self.evento]
            }
        })
        eventos, diagnostico = listar_eventos_bet365_pre_live(
            api, "2026-08-29",
            agora=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(1, diagnostico["eventos"])
        pareamento = parear_evento_bet365_pre_live(eventos, {
            "mandante": "Palmeiras FC",
            "visitante": "Santos FC",
            "inicio": "2026-08-29T18:00:00+00:00",
        })
        self.assertEqual("900", pareamento["evento_id"])

    def test_hoje_ignora_encerrados_e_avanca_ate_pagina_futura(self):
        encerrados = [{
            "id": str(indice),
            "home": {"name": f"Casa {indice}"},
            "away": {"name": f"Fora {indice}"},
            "time": "1788048000",
            "time_status": "3",
        } for indice in range(50)]
        futuro = {
            **self.evento,
            "time_status": "0",
        }
        api = APIFalsa({
            ("v1/bet365/upcoming", 1): {
                "success": 1,
                "pager": {"page": 1, "per_page": 50, "total": 51},
                "results": encerrados,
            },
            ("v1/bet365/upcoming", 2): {
                "success": 1,
                "pager": {"page": 2, "per_page": 50, "total": 51},
                "results": [futuro],
            },
        })
        eventos, diagnostico = listar_eventos_bet365_pre_live(
            api,
            "2026-08-29",
            maximo_paginas=2,
            agora=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(["900"], [item["id"] for item in eventos])
        self.assertEqual(2, diagnostico["paginas"])
        self.assertEqual(50, diagnostico["descartes"]["status_nao_futuro"])
        primeira_chamada = api.chamadas[0][1]
        self.assertNotIn("day", primeira_chamada)
        self.assertEqual(1, primeira_chamada["skip_esports"])

    def test_catalogo_preserva_tudo_e_normaliza_so_placar(self):
        api = APIFalsa({"v4/bet365/prematch": self.prematch})
        catalogo, diagnostico = carregar_catalogo_bet365_pre_live(
            api, {"evento_id": "900"}
        )
        self.assertEqual("catalogo_coletado", diagnostico["estado"])
        self.assertIn(
            "Corners 2-Way",
            {item["nome"] for item in catalogo["mercados"]},
        )
        ofertas = extrair_ofertas_bet365_pre_live(
            catalogo, 10,
            {"mandante": "Palmeiras", "visitante": "Santos"},
        )
        identidades = {
            (item["mercado"], item["selecao"]) for item in ofertas
        }
        self.assertIn(("resultado", "mandante"), identidades)
        self.assertIn(
            ("time_marca_gol", "visitante|sim"), identidades
        )
        self.assertIn(
            ("time_marca_gol", "visitante|nao"), identidades
        )
        self.assertIn(("total_gols", "over_1.5"), identidades)
        self.assertNotIn(("total_gols", "over_2"), identidades)
        self.assertIn(("ambas_marcam", "sim"), identidades)
        self.assertIn(
            ("total_gols_mais_ambas", "over_2.5|sim"), identidades
        )
        self.assertIn(("multigols", "de_1_a_4"), identidades)
        self.assertEqual({"bet365"}, {
            item["bookmaker_id"] for item in ofertas
        })
        self.assertEqual({"900"}, {
            item["evento_externo_id"] for item in ofertas
        })
        self.assertNotIn("escanteios", {item["mercado"] for item in ofertas})
        resumo = resumir_catalogo_bet365_pre_live([catalogo], ofertas)
        self.assertGreaterEqual(resumo["familias_distintas"], 6)
        self.assertEqual(len(ofertas), resumo["ofertas_precificaveis"])


if __name__ == "__main__":
    unittest.main()
