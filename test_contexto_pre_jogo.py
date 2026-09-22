import unittest
from pathlib import Path

from banco import BancoMonitor
from contexto_pre_jogo import (
    comparar_estatisticas_ao_vivo,
    resumir_contexto_pre_jogo,
    resumir_cobertura_contexto,
    resumir_odds_pre_jogo,
    resumir_estatisticas_api_ao_vivo,
    resumir_eventos_api_ao_vivo,
    resumir_jogadores_api_ao_vivo,
)


class ContextoPreJogoTest(unittest.TestCase):
    def test_resume_forma_h2h_escalacao_e_desfalques_sem_influenciar_regra(self):
        confirmacao = {
            "fixture_id": 99,
            "times": {
                "home": {"id": 1, "name": "Casa"},
                "away": {"id": 2, "name": "Fora"},
            },
        }
        jogos = [
            {
                "teams": {"home": {"id": 1}, "away": {"id": 2}},
                "goals": {"home": 2, "away": 1},
            },
            {
                "teams": {"home": {"id": 2}, "away": {"id": 1}},
                "goals": {"home": 0, "away": 0},
            },
        ]
        escalacoes = [{
            "team": {"id": 1},
            "formation": "4-3-3",
            "startXI": [
                {"player": {"id": indice, "name": f"J{indice}", "pos": "M"}}
                for indice in range(11)
            ],
        }]
        desfalques = [{
            "team": {"id": 2},
            "player": {
                "id": 7, "name": "Atleta", "type": "Missing Fixture",
                "reason": "Injury",
            },
        }]

        contexto = resumir_contexto_pre_jogo(
            confirmacao,
            h2h=jogos,
            forma_mandante=jogos,
            forma_visitante=jogos,
            escalacoes=escalacoes,
            desfalques=desfalques,
        )

        self.assertEqual(contexto["modo"], "sombra")
        self.assertEqual(contexto["versao"], "contexto-pre-jogo-v4")
        self.assertEqual(
            contexto["forma_recente"]["mandante"]["pontos_por_jogo"], 2.0
        )
        self.assertEqual(
            contexto["confrontos_diretos"]["taxa_over_1_5"], 0.5
        )
        self.assertTrue(contexto["escalacoes"]["1"]["confirmada"])
        self.assertEqual(contexto["desfalques"]["2"]["total"], 1)

    def test_odds_pre_jogo_exigem_par_e_formam_consenso_entre_casas(self):
        odds = resumir_odds_pre_jogo([{
            "update": "2026-07-29T18:00:00+00:00",
            "bookmakers": [
                {
                    "id": 1,
                    "name": "Casa A",
                    "bets": [
                        {
                            "id": 5,
                            "name": "Goals Over/Under",
                            "values": [
                                {
                                    "value": "Over 2.5",
                                    "odd": "1.91",
                                    "main": True,
                                },
                                {
                                    "value": "Under 2.5",
                                    "odd": "1.89",
                                    "main": True,
                                },
                                {
                                    "value": "Exactly 2",
                                    "odd": "4.0",
                                },
                            ],
                        },
                        {
                            "id": 20,
                            "name": "Asian Corners",
                            "values": [
                                {
                                    "value": "Over",
                                    "handicap": "9.5",
                                    "odd": "1.95",
                                },
                                {
                                    "value": "Under",
                                    "handicap": "9.5",
                                    "odd": "1.85",
                                },
                            ],
                        },
                    ],
                },
                {
                    "id": 2,
                    "name": "Casa B",
                    "bets": [
                        {
                            "id": 5,
                            "name": "Total Goals",
                            "values": [
                                {"value": "Over 2.5", "odd": "2.0"},
                                {"value": "Under 2.5", "odd": "1.8"},
                            ],
                        },
                        {
                            "id": 20,
                            "name": "Total Corners",
                            "values": [
                                {"value": "Over 9", "odd": "1.9"},
                                {"value": "Under 9", "odd": "1.9"},
                            ],
                        },
                    ],
                },
            ],
        }])

        gols = odds["mercados"]["gols_ft"]
        cantos = odds["mercados"]["escanteios_ft"]
        self.assertTrue(gols["consenso_suficiente"])
        self.assertEqual(gols["casas"], 2)
        self.assertEqual(gols["linha_consenso"], 2.5)
        self.assertEqual(gols["odd_over_mediana"], 1.955)
        self.assertTrue(cantos["consenso_suficiente"])
        self.assertEqual(cantos["linha_consenso"], 9.25)
        self.assertEqual(len(cantos["evidencias"]), 2)

    def test_odds_pre_jogo_rejeitam_time_metade_e_par_incompleto(self):
        odds = resumir_odds_pre_jogo([{
            "bookmakers": [{
                "id": 1,
                "name": "Casa A",
                "bets": [
                    {
                        "id": 1,
                        "name": "Home Team Total Goals",
                        "values": [
                            {"value": "Over 1.5", "odd": "1.8"},
                            {"value": "Under 1.5", "odd": "2.0"},
                        ],
                    },
                    {
                        "id": 2,
                        "name": "Corners Over/Under First Half",
                        "values": [
                            {"value": "Over 4.5", "odd": "1.9"},
                            {"value": "Under 4.5", "odd": "1.9"},
                        ],
                    },
                    {
                        "id": 3,
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.5", "odd": "1.9"},
                        ],
                    },
                    {
                        "id": 87,
                        "name": "Total ShotOnGoal",
                        "values": [
                            {"value": "Over 8.5", "odd": "1.9"},
                            {"value": "Under 8.5", "odd": "1.9"},
                        ],
                    },
                ],
            }],
        }])

        self.assertFalse(odds["cobertura"]["gols_ft"])
        self.assertFalse(odds["cobertura"]["escanteios_ft"])

    def test_compacta_payloads_estaveis_sem_guardar_resposta_bruta(self):
        contexto = resumir_contexto_pre_jogo(
            {
                "fixture_id": 99,
                "times": {
                    "home": {"id": 1},
                    "away": {"id": 2},
                },
            },
            estatisticas_times={
                "mandante": {
                    "team": {"id": 1, "name": "Casa", "logo": "grande"},
                    "league": {"id": 10, "name": "Liga"},
                    "season": 2026,
                    "fixtures": {
                        "played": {"total": 10},
                        "wins": {"total": 6},
                        "draws": {"total": 2},
                        "loses": {"total": 2},
                    },
                    "goals": {
                        "for": {
                            "average": {"total": "1.8"},
                            "minute": {
                                "46-60": {"total": 5, "percentage": "27.78%"}
                            },
                        },
                        "against": {
                            "average": {"total": "0.9"},
                            "minute": {
                                "61-75": {"total": 3, "percentage": "33.33%"}
                            },
                        },
                    },
                    "lineups": [{"formation": "4-3-3"}] * 100,
                }
            },
            previsao={
                "predictions": {
                    "winner": {"id": 1, "name": "Casa", "comment": "Win"},
                    "win_or_draw": True,
                    "under_over": "+1.5",
                    "goals": {"home": "-2.5", "away": "-1.5"},
                    "advice": "Casa vence",
                },
                "comparison": {
                    "form": {"home": "60%", "away": "40%"},
                    "total": {"home": "70%", "away": "30%"},
                },
                "h2h": [{"payload": "muito grande"}] * 100,
            },
        )
        temporada = contexto["estatisticas_temporada"]["mandante"]
        self.assertEqual(temporada["jogos"], 10)
        self.assertEqual(
            temporada["gols_pro_por_minuto"]["46-60"],
            {"total": 5, "percentual": 27.78},
        )
        self.assertEqual(
            temporada["gols_contra_por_minuto"]["61-75"]["total"], 3
        )
        self.assertNotIn("lineups", temporada)
        self.assertNotIn("h2h", contexto["previsao_provedor"])

    def test_contexto_fica_congelado_no_snapshot_do_sinal(self):
        caminho = Path.cwd() / ".teste_contexto_pre_jogo.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-29T13:00:00",
                "url": "https://packball.com/match/contexto/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "20 '",
                "contexto_api": {
                    "versao": "contexto-pre-jogo-v1",
                    "modo": "sombra",
                },
            })
            linha = banco.conexao.execute(
                "SELECT contexto_api_json FROM snapshots WHERE id=?",
                (snapshot,),
            ).fetchone()
            self.assertIn("contexto-pre-jogo-v1", linha[0])
            self.assertIn('"modo": "sombra"', linha[0])
            cobertura = resumir_cobertura_contexto(banco.conexao)
            self.assertEqual(cobertura["snapshots"], 1)
            self.assertIsNone(cobertura["taxa_concordancia_fontes"])
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                arquivo = Path(str(caminho) + sufixo)
                if arquivo.exists():
                    arquivo.unlink()

    def test_compara_metricas_equivalentes_das_duas_fontes(self):
        comparacao = comparar_estatisticas_ao_vivo(
            {
                "Chutes": "8 - 5",
                "Chutes no gol": "3 - 2",
                "Escanteios": "4 - 1",
            },
            [
                {
                    "team": {"id": 1},
                    "statistics": [
                        {"type": "Total Shots", "value": 8},
                        {"type": "Shots on Goal", "value": 3},
                        {"type": "Corner Kicks", "value": 4},
                    ],
                },
                {
                    "team": {"id": 2},
                    "statistics": [
                        {"type": "Total Shots", "value": 6},
                        {"type": "Shots on Goal", "value": 2},
                        {"type": "Corner Kicks", "value": 1},
                    ],
                },
            ],
            {
                "times": {
                    "home": {"id": 1},
                    "away": {"id": 2},
                }
            },
        )

        self.assertEqual(comparacao["comparadas"], 3)
        self.assertEqual(comparacao["concordantes"], 3)
        self.assertEqual(comparacao["taxa_concordancia"], 1.0)

    def test_resume_classificacao_e_historico_com_corners_chutes_e_xg(self):
        contexto = resumir_contexto_pre_jogo(
            {
                "fixture_id": 99,
                "times": {
                    "home": {"id": 1},
                    "away": {"id": 2},
                },
            },
            classificacao=[{
                "league": {
                    "standings": [[
                        {
                            "rank": 2,
                            "team": {"id": 1},
                            "points": 31,
                            "goalsDiff": 12,
                            "form": "WWDLW",
                            "all": {
                                "played": 15,
                                "win": 9,
                                "draw": 4,
                                "lose": 2,
                                "goals": {"for": 28, "against": 16},
                            },
                        },
                        {
                            "rank": 8,
                            "team": {"id": 2},
                            "points": 20,
                            "goalsDiff": -2,
                            "form": "LDWLW",
                            "all": {
                                "played": 15,
                                "win": 5,
                                "draw": 5,
                                "lose": 5,
                                "goals": {"for": 19, "against": 21},
                            },
                        },
                    ]]
                }
            }],
            historico_detalhado=[{
                "teams": {
                    "home": {"id": 1},
                    "away": {"id": 2},
                },
                "goals": {"home": 2, "away": 1},
                "statistics": [
                    {
                        "team": {"id": 1},
                        "statistics": [
                            {"type": "Corner Kicks", "value": 6},
                            {"type": "Total Shots", "value": 14},
                            {"type": "Shots on Goal", "value": 5},
                            {"type": "expected_goals", "value": "1.82"},
                        ],
                    },
                    {
                        "team": {"id": 2},
                        "statistics": [
                            {"type": "Corner Kicks", "value": 4},
                            {"type": "Total Shots", "value": 9},
                            {"type": "Shots on Goal", "value": 3},
                            {"type": "expected_goals", "value": "0.91"},
                        ],
                    },
                ],
            }],
        )

        self.assertEqual(contexto["classificacao"]["mandante"]["posicao"], 2)
        historico = contexto["historico_detalhado"]
        self.assertEqual(historico["mandante"]["escanteios_media"], 6.0)
        self.assertEqual(
            historico["mandante"]["escanteios_contra_media"], 4.0
        )
        self.assertEqual(historico["visitante"]["xg_media"], 0.91)

    def test_resume_live_api_sem_guardar_payload_integral(self):
        confirmacao = {
            "times": {
                "home": {"id": 1},
                "away": {"id": 2},
            }
        }
        estatisticas = resumir_estatisticas_api_ao_vivo(
            [
                {
                    "team": {"id": 1},
                    "statistics": [
                        {"type": "Total Shots", "value": 12},
                        {"type": "Shots on Goal", "value": 5},
                        {"type": "Ball Possession", "value": "61%"},
                        {"type": "expected_goals", "value": "1.45"},
                    ],
                },
                {
                    "team": {"id": 2},
                    "statistics": [
                        {"type": "Total Shots", "value": 7},
                        {"type": "Shots on Goal", "value": 2},
                    ],
                },
            ],
            confirmacao,
        )
        jogadores = resumir_jogadores_api_ao_vivo(
            [{
                "team": {"id": 1},
                "players": [{
                    "player": {"id": 10, "name": "Atacante"},
                    "statistics": [{
                        "games": {
                            "minutes": 70,
                            "position": "F",
                            "rating": "7.8",
                        },
                        "shots": {"total": 4, "on": 3},
                        "passes": {"key": 2},
                        "goals": {"total": 1, "assists": 0},
                    }],
                }],
            }],
            confirmacao,
        )
        eventos = resumir_eventos_api_ao_vivo(
            [{
                "time": {"elapsed": 65},
                "team": {"id": 2},
                "type": "Card",
                "detail": "Red Card",
                "player": {"name": "Zagueiro"},
            }],
            confirmacao,
        )

        self.assertEqual(
            estatisticas["times"]["mandante"]["posse"], 61.0
        )
        self.assertEqual(
            jogadores["times"]["mandante"]["totais"]["chutes_no_gol"],
            3.0,
        )
        self.assertEqual(
            eventos["times"]["visitante"]["cartoes_vermelhos"], 1
        )


if __name__ == "__main__":
    unittest.main()
