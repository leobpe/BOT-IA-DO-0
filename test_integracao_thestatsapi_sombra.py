import unittest
from datetime import datetime, timezone

from integracao_thestatsapi_sombra import (
    adaptar_lista_thestatsapi_para_associador,
    associar_jogo_thestatsapi,
    diagnosticar_associacao_thestatsapi,
    normalizar_live_stats_thestatsapi,
    normalizar_odds_live_thestatsapi,
    resumir_associacoes_thestatsapi,
    resumir_cobertura_thestatsapi,
)


def partida(
    match_id="mt_745359007",
    casa="Club Nacional W U20 FC",
    fora="Santos W U20 CF",
    gols_casa=1,
    gols_fora=0,
    minuto=31,
):
    return {
        "id": match_id,
        "competition_id": "cp_10",
        "season_id": "se_20",
        "status": "live",
        "elapsed_minutes": minuto,
        "utc_date": "2026-08-13T20:00:00Z",
        "home_team": {"id": "tm_1", "name": casa},
        "away_team": {"id": "tm_2", "name": fora},
        "score": {"home": gols_casa, "away": gols_fora},
        "live_odds_available": True,
        "xg_available": True,
    }


class TestAssociacaoTheStatsAPISombra(unittest.TestCase):
    def test_adapta_shape_real_e_mantem_id_string(self):
        adaptadas = adaptar_lista_thestatsapi_para_associador({
            "data": [partida(), {"id": 123}],
        })

        self.assertEqual(len(adaptadas), 1)
        item = adaptadas[0]
        self.assertEqual(item["fixture"]["id"], "mt_745359007")
        self.assertEqual(item["fixture"]["status"]["elapsed"], 31)
        self.assertEqual(item["teams"]["home"]["name"], "Nacional W U20")
        self.assertEqual(
            item["teams"]["home"]["name_original"],
            "Club Nacional W U20 FC",
        )
        self.assertEqual(item["goals"], {"home": 1, "away": 0})

    def test_pareia_com_afixos_categoria_placar_minuto_e_margem(self):
        jogo = {
            "mandante": "Nacional W U20",
            "visitante": "Santos W U20",
            "placar": "1-0",
            "status": "32 '",
        }

        diagnostico = diagnosticar_associacao_thestatsapi(
            jogo, {"ok": True, "dados": [partida()]}
        )

        self.assertEqual(diagnostico["motivo"], "associado")
        self.assertFalse(diagnostico["aplicacao_sinais"])
        associacao = diagnostico["associacao"]
        self.assertEqual(associacao["match_id"], "mt_745359007")
        self.assertEqual(associacao["fixture_id"], "mt_745359007")
        self.assertEqual(associacao["orientacao"], "direta")
        self.assertEqual(associacao["placar"], [1, 0])
        self.assertEqual(
            associacao["times"]["home"]["name"],
            "Club Nacional W U20 FC",
        )
        self.assertEqual(associacao["fonte"], "thestatsapi")

    def test_detecta_orientacao_invertida_e_reorienta_placar(self):
        jogo = {
            "mandante": "Alpha",
            "visitante": "Beta",
            "placar": "1-0",
            "status": "20 '",
        }
        item = partida(
            casa="Beta SC",
            fora="Alpha FC",
            gols_casa=0,
            gols_fora=1,
            minuto=20,
        )

        associacao = associar_jogo_thestatsapi(jogo, [item])

        self.assertIsNotNone(associacao)
        self.assertEqual(associacao["orientacao"], "invertida")
        self.assertEqual(associacao["placar"], [1, 0])
        self.assertEqual(associacao["times"]["home"]["name"], "Alpha FC")
        self.assertEqual(associacao["times"]["away"]["name"], "Beta SC")

    def test_rejeita_categoria_feminina_e_subidade_incompativeis(self):
        jogo = {
            "mandante": "Nacional U20",
            "visitante": "Santos U20",
            "placar": "1-0",
            "status": "31 '",
        }
        candidato = partida(
            casa="Nacional W U19 FC",
            fora="Santos W U19 CF",
        )

        diagnostico = diagnosticar_associacao_thestatsapi(jogo, [candidato])

        self.assertIsNone(diagnostico["associacao"])
        self.assertEqual(
            diagnostico["motivo"], "categoria_equipes_incompativel"
        )

    def test_rejeita_placar_distante(self):
        jogo = {
            "mandante": "Nacional W U20",
            "visitante": "Santos W U20",
            "placar": "5-0",
            "status": "31 '",
        }
        diagnostico = diagnosticar_associacao_thestatsapi(
            jogo, [partida(gols_casa=0, gols_fora=0)]
        )
        self.assertIsNone(diagnostico["associacao"])
        self.assertEqual(diagnostico["motivo"], "placar_incompativel")

    def test_rejeita_empate_de_candidatos_por_margem(self):
        jogo = {
            "mandante": "Nacional W U20",
            "visitante": "Santos W U20",
            "placar": "1-0",
            "status": "31 '",
        }
        outro = partida(match_id="mt_745359008")

        diagnostico = diagnosticar_associacao_thestatsapi(
            jogo, [partida(), outro]
        )

        self.assertIsNone(diagnostico["associacao"])
        self.assertEqual(diagnostico["motivo"], "associacao_ambigua")
        self.assertEqual(diagnostico["margem_associacao"], 0.0)


class TestLiveStatsTheStatsAPISombra(unittest.TestCase):
    def setUp(self):
        self.coletado_em = datetime(
            2026, 8, 13, 20, 31, tzinfo=timezone.utc
        )
        self.payload = {
            "data": {
                "match_id": "mt_745359007",
                "meta": {
                    "match_status": "first_half",
                    "elapsed_minutes": 31,
                    "home_goals": 1,
                    "away_goals": 0,
                    "ht_score": None,
                    "period": "first_half",
                },
                "stats": {
                    "total_shots": {"all": {"home": 8, "away": 5}},
                    "shots_on_target": {"all": {"home": 4, "away": 0}},
                    "corner_kicks": {"all": {"home": 3, "away": 2}},
                    "expected_goals": {"all": {"home": "1.21"}},
                    "ball_possession": {"all": {"home": 55, "away": 45}},
                },
            }
        }

    def test_normaliza_shape_real_sem_inventar_zero(self):
        snapshot = normalizar_live_stats_thestatsapi(
            self.payload,
            packball_url="https://packball.com/match/abc",
            coletado_em=self.coletado_em,
        )

        self.assertEqual(snapshot["match_id"], "mt_745359007")
        self.assertEqual(snapshot["periodo"], "primeiro_tempo")
        self.assertEqual(snapshot["minuto"], 31)
        self.assertEqual(snapshot["placar"], [1, 0])
        self.assertEqual(snapshot["chutes_mandante"], 8)
        self.assertEqual(snapshot["chutes_visitante"], 5)
        self.assertEqual(snapshot["chutes_gol_visitante"], 0)
        self.assertEqual(snapshot["xg_mandante"], 1.21)
        self.assertIsNone(snapshot["xg_visitante"])
        self.assertTrue(snapshot["completo"])
        self.assertFalse(snapshot["aplicacao_sinais"])
        self.assertFalse(snapshot["calibracao"])

    def test_inverte_todos_os_lados_inclusive_placar(self):
        snapshot = normalizar_live_stats_thestatsapi(
            self.payload,
            orientacao="invertida",
            coletado_em="2026-08-13T20:31:00+00:00",
        )

        self.assertEqual(snapshot["placar"], [0, 1])
        self.assertEqual(snapshot["chutes_mandante"], 5)
        self.assertEqual(snapshot["chutes_visitante"], 8)
        self.assertIsNone(snapshot["xg_mandante"])
        self.assertEqual(snapshot["xg_visitante"], 1.21)
        self.assertEqual(snapshot["orientacao"], "invertida")

    def test_ausencias_permanecem_none_e_snapshot_incompleto(self):
        del self.payload["data"]["stats"]["shots_on_target"]
        snapshot = normalizar_live_stats_thestatsapi(
            self.payload, coletado_em=self.coletado_em
        )
        self.assertIsNone(snapshot["chutes_gol_mandante"])
        self.assertIsNone(snapshot["chutes_gol_visitante"])
        self.assertFalse(snapshot["completo"])

    def test_sem_metricas_ou_orientacao_invalida_falha_fechado(self):
        self.payload["data"]["stats"] = {}
        self.assertIsNone(normalizar_live_stats_thestatsapi(self.payload))
        self.assertIsNone(normalizar_live_stats_thestatsapi(
            {"data": {"match_id": "mt_1", "meta": {}, "stats": {
                "total_shots": {"all": {"home": 1, "away": 1}}
            }}},
            orientacao="duvidosa",
        ))


class TestOddsTheStatsAPISombra(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "data": {
                "match_id": "mt_745359007",
                "bookmakers": [
                    {
                        "bookmaker": "Bet365",
                        "markets": {
                            "total_goals": {
                                "2.5": {
                                    "over": {"live": "1.833"},
                                    "under": {"live": "1.833"},
                                }
                            },
                            "first_half_total_goals": {
                                "1.5": {
                                    "over": {"live": "2.10"},
                                    "under": {"live": "1.70"},
                                }
                            },
                            "match_corners": {
                                "8": {
                                    "over": {"live": "2.000"},
                                    "under": {"live": "1.800"},
                                },
                                "8.25": {
                                    "over": {"live": "2.050"},
                                    "under": {"live": "1.750"},
                                },
                                "8.5": {
                                    "over": {"live": "2.100"},
                                    "under": {"live": "1.700"},
                                },
                                "8.75": {
                                    "over": {"live": "2.200"},
                                    "under": {"live": "1.650"},
                                },
                            },
                            "first_half_corners": {
                                "4.5": {
                                    "over": {"live": "1.90"},
                                    "under": {},
                                }
                            },
                            "asian_handicap": {
                                "0.5": {
                                    "over": {"live": "1.9"},
                                    "under": {"live": "1.9"},
                                }
                            },
                            "next_goal": {
                                "home": {"live": "2.0"},
                            },
                        },
                    },
                    {
                        "bookmaker": "Paddy Power",
                        "markets": {},
                    },
                ],
            }
        }

    def test_preserva_bookmaker_mercado_linha_lados_e_instante(self):
        resultado = normalizar_odds_live_thestatsapi(
            self.payload,
            coletado_em="2026-08-13T20:31:00+00:00",
        )

        self.assertEqual(resultado["match_id"], "mt_745359007")
        self.assertEqual(resultado["bookmakers"], ["Bet365"])
        oferta = next(
            item for item in resultado["ofertas"]
            if item["mercado_original"] == "total_goals"
        )
        self.assertEqual(oferta["categoria"], "gols")
        self.assertEqual(oferta["periodo"], "jogo")
        self.assertEqual(oferta["linha"], 2.5)
        self.assertEqual(oferta["over"], 1.833)
        self.assertEqual(oferta["under"], 1.833)
        self.assertEqual(oferta["bookmaker"], "Bet365")
        self.assertEqual(oferta["fonte"], "thestatsapi")
        self.assertEqual(
            oferta["coletado_em"], "2026-08-13T20:31:00+00:00"
        )
        self.assertFalse(oferta["aplicacao_sinais"])

    def test_classifica_inteira_e_quarto_como_asiatica_e_meia_normal(self):
        resultado = normalizar_odds_live_thestatsapi(self.payload)
        cantos = {
            item["linha"]: item["tipo_mercado"]
            for item in resultado["ofertas"]
            if item["mercado_original"] == "match_corners"
        }
        self.assertEqual(cantos[8.0], "asiatico")
        self.assertEqual(cantos[8.25], "asiatico")
        self.assertEqual(cantos[8.5], "total_normal")
        self.assertEqual(cantos[8.75], "asiatico")

    def test_nao_cria_proximo_gol_nem_handicap_e_preserva_lado_ausente(self):
        resultado = normalizar_odds_live_thestatsapi(self.payload)
        mercados = {item["mercado_original"] for item in resultado["ofertas"]}
        self.assertNotIn("next_goal", mercados)
        self.assertNotIn("asian_handicap", mercados)
        self.assertIn("next_goal", resultado["mercados_ignorados"])
        parcial = next(
            item for item in resultado["ofertas"]
            if item["mercado_original"] == "first_half_corners"
        )
        self.assertEqual(parcial["over"], 1.9)
        self.assertIsNone(parcial["under"])
        self.assertFalse(parcial["completa"])


class TestResumoTheStatsAPISombra(unittest.TestCase):
    def test_resumos_sao_observacionais_e_nunca_liberam_sinais(self):
        jogo = {
            "mandante": "Nacional W U20",
            "visitante": "Santos W U20",
            "placar": "1-0",
            "status": "31 '",
        }
        diagnostico = diagnosticar_associacao_thestatsapi(jogo, [partida()])
        snapshot = normalizar_live_stats_thestatsapi({
            "data": {
                "match_id": "mt_745359007",
                "meta": {"elapsed_minutes": 31},
                "stats": {
                    "total_shots": {"all": {"home": 8, "away": 5}},
                    "corner_kicks": {"all": {"home": 3, "away": 2}},
                },
            }
        }, coletado_em="2026-08-13T20:31:00+00:00")
        odds = normalizar_odds_live_thestatsapi({
            "data": {
                "match_id": "mt_745359007",
                "bookmakers": [{
                    "bookmaker": "Bet365",
                    "markets": {"match_corners": {"8.5": {
                        "over": {"live": "2.0"},
                        "under": {"live": "1.8"},
                    }}},
                }],
            }
        }, coletado_em="2026-08-13T20:31:00+00:00")

        associacoes = resumir_associacoes_thestatsapi([diagnostico])
        resumo = resumir_cobertura_thestatsapi(
            partidas=[partida()],
            diagnosticos=[diagnostico],
            snapshots=[snapshot],
            odds=[odds],
        )

        self.assertEqual(associacoes["associadas"], 1)
        self.assertFalse(associacoes["aplicacao_sinais"])
        self.assertEqual(resumo["estado"], "coletando_sombra")
        self.assertEqual(resumo["partidas_ao_vivo"], 1)
        self.assertEqual(resumo["partidas_com_stats"], 1)
        self.assertEqual(resumo["partidas_com_odds"], 1)
        self.assertEqual(resumo["linhas_escanteio_por_tipo"], {
            "total_normal": 1,
        })
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["calibracao"])
        self.assertFalse(resumo["promocao_automatica"])


if __name__ == "__main__":
    unittest.main()
