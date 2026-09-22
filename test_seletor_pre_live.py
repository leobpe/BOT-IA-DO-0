import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


with patch.dict(
    os.environ,
    {
        "PRELIVE_PERFIL_SELECAO": "v11",
        "PRELIVE_MERCADOS_TIME_ATIVOS": "1",
        "PRELIVE_MULTIPLAS_TRES_PERNAS_ATIVAS": "1",
    },
    clear=True,
):
    _spec = importlib.util.spec_from_file_location(
        "seletor_pre_live_teste_v11",
        Path(__file__).with_name("seletor_pre_live.py"),
    )
    _seletor = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_seletor)

LINHAGEM = _seletor.LINHAGEM
anexar_consenso_casas = _seletor.anexar_consenso_casas
avaliar_ofertas_pre_live = _seletor.avaliar_ofertas_pre_live
construir_modelo_pre_live = _seletor.construir_modelo_pre_live
extrair_ofertas_api_football = _seletor.extrair_ofertas_api_football
liquidar_bilhete_pre_live = _seletor.liquidar_bilhete_pre_live
liquidar_perna_pre_live = _seletor.liquidar_perna_pre_live
montar_bilhetes_pre_live = _seletor.montar_bilhetes_pre_live
revalidar_bilhetes_publicados_pre_live = (
    _seletor.revalidar_bilhetes_publicados_pre_live
)


def contexto_completo(escalacao=True):
    return {
        "capacidade_times_v2": {
            "recentes": {
                "mandante": {
                    "geral": {
                        "jogos": 15, "gols_pro_media": 2.0,
                        "gols_contra_media": 0.8,
                    },
                    "mando": {
                        "jogos": 8, "gols_pro_media": 2.3,
                        "gols_contra_media": 0.7,
                    },
                },
                "visitante": {
                    "geral": {
                        "jogos": 15, "gols_pro_media": 0.8,
                        "gols_contra_media": 1.9,
                    },
                    "mando": {
                        "jogos": 8, "gols_pro_media": 0.7,
                        "gols_contra_media": 2.1,
                    },
                },
            },
            "temporada_mando": {
                "mandante": {
                    "gols_pro_media": 2.0, "gols_contra_media": 0.8,
                },
                "visitante": {
                    "gols_pro_media": 0.8, "gols_contra_media": 1.9,
                },
            },
            "cobertura": {
                "mandante": {"historico_total": 15, "historico_mando": 8},
                "visitante": {"historico_total": 15, "historico_mando": 8},
            },
        },
        "confrontos_diretos": {"jogos": 5, "media_gols": 2.8},
        "jogadores_chave": {
            lado: {
                "escalacao_confirmada": escalacao,
                "jogadores": [],
            }
            for lado in ("mandante", "visitante")
        },
    }


class SeletorPreLiveTest(unittest.TestCase):
    def test_consenso_casas_identifica_melhor_preco(self):
        ofertas = [{
            "fixture_id": 10,
            "bookmaker_id": indice,
            "bookmaker": casa,
            "mercado": "total_gols",
            "selecao": "over_1.5",
            "odd": odd,
            "probabilidade_mercado_sem_margem": probabilidade,
        } for indice, casa, odd, probabilidade in (
            (1, "Casa A", 1.50, 0.75),
            (2, "Casa B", 1.55, 0.74),
            (3, "Casa C", 1.48, 0.76),
        )]

        anexar_consenso_casas(ofertas)

        melhor = next(item for item in ofertas if item["bookmaker"] == "Casa B")
        self.assertTrue(melhor["melhor_preco_disponivel"])
        self.assertEqual(3, melhor["casas_comparadas"])
        self.assertAlmostEqual(0.75, melhor["probabilidade_consenso_casas"])
        self.assertAlmostEqual(1.50, melhor["odd_mediana_casas"])

    def test_avaliacao_retém_somente_melhor_preco_confirmado(self):
        ofertas = [{
            "fixture_id": 10,
            "bookmaker_id": indice,
            "bookmaker": casa,
            "mercado": "chance_dupla",
            "selecao": "mandante_ou_empate",
            "grupo_precificacao": "chance_dupla",
            "odd": odd,
            "probabilidade_mercado_sem_margem": 0.80,
            "fonte": "teste",
        } for indice, casa, odd in (
            (1, "Casa A", 1.20),
            (2, "Casa B", 1.30),
            (3, "Casa C", 1.25),
        )]

        resultado = avaliar_ofertas_pre_live(
            ofertas, contexto_completo(), qualidade=90.0
        )

        self.assertEqual(1, len(resultado["elegiveis"]))
        escolhida = resultado["elegiveis"][0]
        self.assertEqual("Casa B", escolhida["bookmaker"])
        self.assertTrue(escolhida["consenso_disponivel"])
        self.assertGreater(escolhida["edge_conservador"], 0)
        self.assertGreater(escolhida["score_valor"], 0)

    def test_extrai_mercados_reais_e_descarta_linhas_com_push(self):
        raw = [{
            "fixture": {"id": 10},
            "bookmakers": [{
                "id": 7, "name": "Casa A",
                "bets": [
                    {
                        "id": 12, "name": "Double Chance",
                        "values": [
                            {"value": "Home/Draw", "odd": "1.30"},
                            {"value": "Draw/Away", "odd": "2.90"},
                        ],
                    },
                    {
                        "id": 25, "name": "Result/Total Goals",
                        "values": [{"value": "Home/Over 1.5", "odd": "1.55"}],
                    },
                    {
                        "id": 26,
                        "name": "Double Chance And Total Goals",
                        "values": [{
                            "value": "Home/Draw & Over 1.5", "odd": "1.48"
                        }],
                    },
                    {
                        "id": 5, "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.0", "odd": "1.70"},
                            {"value": "Over 2.5", "odd": "1.90"},
                        ],
                    },
                ],
            }],
        }]
        ofertas = extrair_ofertas_api_football(raw)
        chaves = {(item["mercado"], item["selecao"]) for item in ofertas}
        self.assertIn(("chance_dupla", "mandante_ou_empate"), chaves)
        self.assertIn(("resultado_mais_gols", "mandante|over_1.5"), chaves)
        self.assertIn((
            "chance_dupla_mais_gols",
            "mandante_ou_empate|over_1.5",
        ), chaves)
        self.assertIn(("total_gols", "over_2.5"), chaves)
        self.assertNotIn(("total_gols", "over_2"), chaves)

    def test_extrai_mercados_reais_de_gol_e_multigols_do_time(self):
        raw = [{
            "fixture": {"id": 10},
            "bookmakers": [{
                "id": 7, "name": "Casa A",
                "bets": [
                    {
                        "name": "Home Team Score a Goal",
                        "values": [
                            {"value": "Yes", "odd": "1.17"},
                            {"value": "No", "odd": "4.50"},
                        ],
                    },
                    {
                        "name": "Away Team Multi Goals",
                        "values": [{"value": "1-4", "odd": "1.16"}],
                    },
                ],
            }],
        }]
        chaves = {
            (item["mercado"], item["selecao"])
            for item in extrair_ofertas_api_football(raw)
        }
        self.assertIn(("time_marca_gol", "mandante|sim"), chaves)
        self.assertIn(("multigols_time", "visitante|de_1_a_4"), chaves)

    def test_avaliacao_usa_historico_mando_h2h_e_escalacao(self):
        ofertas = [{
            "fixture_id": 10, "bookmaker_id": 7, "bookmaker": "Casa A",
            "mercado": "chance_dupla", "selecao": "mandante_ou_empate",
            "grupo_precificacao": "chance_dupla", "odd": 1.30,
            "fonte": "api_football",
        }]
        resultado = avaliar_ofertas_pre_live(ofertas, contexto_completo())
        self.assertIsNotNone(resultado["modelo"])
        self.assertEqual(15, resultado["modelo"]["amostras"]["mandante_geral"])
        self.assertEqual(5, resultado["modelo"]["h2h"]["jogos"])
        self.assertEqual(1, len(resultado["elegiveis"]))

    def test_modelo_usa_as_15_partidas_gerais_e_nao_so_mando(self):
        base = contexto_completo()
        forte = contexto_completo()
        forte["capacidade_times_v2"]["recentes"]["mandante"]["geral"].update({
            "gols_pro_media": 3.2, "gols_contra_media": 0.5,
        })
        modelo_base = construir_modelo_pre_live(base)
        modelo_forte = construir_modelo_pre_live(forte)
        self.assertGreater(
            modelo_forte["lambda_mandante"], modelo_base["lambda_mandante"]
        )
        self.assertEqual(15, modelo_forte["amostras"]["mandante_geral"])

    def test_previsao_classificacao_e_desfalque_entram_no_modelo(self):
        base = contexto_completo(escalacao=False)
        base["times"] = {"mandante_id": 1, "visitante_id": 2}
        base["previsao_provedor"] = {
            "vencedor_id": 1,
            "comparacao_percentual": {
                "total": {"home": "70%", "away": "30%"}
            },
        }
        base["classificacao"] = {
            "mandante": {"jogos": 10, "pontos": 24, "saldo_gols": 12},
            "visitante": {"jogos": 10, "pontos": 8, "saldo_gols": -8},
        }
        sem_desfalque = construir_modelo_pre_live(base)
        base["jogadores_chave"]["mandante"]["jogadores"] = [{
            "id": 9, "impacto": 1.0, "titular": None, "desfalque": True,
        }]
        com_desfalque = construir_modelo_pre_live(base)
        self.assertTrue(sem_desfalque["previsao"]["disponivel"])
        self.assertTrue(sem_desfalque["classificacao"]["disponivel"])
        self.assertGreater(
            sem_desfalque["lambda_mandante"],
            com_desfalque["lambda_mandante"],
        )
        self.assertEqual(
            1, com_desfalque["jogadores"]["mandante"][
                "desfalques_relevantes"
            ]
        )

    def test_multipla_exige_casa_igual_e_jogos_diferentes(self):
        def avaliacao(fixture_id, casa_id=7):
            perna = {
                "fixture_id": fixture_id,
                "bookmaker_id": casa_id,
                "bookmaker": f"Casa {casa_id}",
                "mercado": "chance_dupla",
                "selecao": "mandante_ou_empate",
                "odd": 1.23,
                "probabilidade_modelo": 0.90,
                "edge_modelo": 0.0803,
                "qualidade_contexto": 90.0,
                "modelo": {
                    "jogadores": {
                        lado: {"escalacao_confirmada": True}
                        for lado in ("mandante", "visitante")
                    }
                },
            }
            return {"jogo": {"fixture_id": fixture_id}, "avaliacao": {"elegiveis": [perna]}}

        bilhetes = montar_bilhetes_pre_live([avaliacao(1), avaliacao(2)])
        self.assertEqual(1, len(bilhetes))
        self.assertEqual("multipla_dois_jogos", bilhetes[0]["tipo"])
        self.assertEqual("apto_sombra_confirmado", bilhetes[0]["estado"])
        self.assertEqual(LINHAGEM, bilhetes[0]["linhagem_sha256"])

        self.assertEqual([], montar_bilhetes_pre_live([avaliacao(1), avaliacao(1)]))
        self.assertEqual([], montar_bilhetes_pre_live([avaliacao(1, 7), avaliacao(2, 8)]))

    def test_multipla_de_tres_jogos_reproduz_estrutura_do_exemplo(self):
        odds = {1: 1.17, 2: 1.10, 3: 1.17}
        mercados = {
            1: ("multigols_time", "mandante|de_1_a_4"),
            2: ("chance_dupla", "mandante_ou_empate"),
            3: ("multigols_time", "visitante|de_1_a_4"),
        }

        def avaliacao(fixture_id):
            perna = {
                "fixture_id": fixture_id,
                "bookmaker_id": 7,
                "bookmaker": "Casa A",
                "mercado": mercados[fixture_id][0],
                "selecao": mercados[fixture_id][1],
                "odd": odds[fixture_id],
                "probabilidade_modelo": 0.90,
                "edge_modelo": round(0.90 - 1.0 / odds[fixture_id], 4),
                "qualidade_contexto": 90.0,
                "modelo": {"jogadores": {
                    lado: {"escalacao_confirmada": True}
                    for lado in ("mandante", "visitante")
                }},
            }
            return {
                "jogo": {"fixture_id": fixture_id},
                "avaliacao": {"elegiveis": [perna]},
            }

        bilhetes = montar_bilhetes_pre_live([
            avaliacao(1), avaliacao(2), avaliacao(3)
        ])
        self.assertEqual(1, len(bilhetes))
        self.assertEqual("multipla_tres_jogos", bilhetes[0]["tipo"])
        self.assertEqual(3, len(bilhetes[0]["pernas"]))
        self.assertAlmostEqual(1.506, bilhetes[0]["odd_total"], places=3)

    def test_portfolio_nao_preenche_limite_com_opcoes_inferiores(self):
        tipos = [
            ("total_gols", "under_4.5"),
            ("total_gols", "under_3.5"),
            ("total_gols", "under_2.5"),
            ("total_gols", "under_5.5"),
            ("total_gols", "over_1.5"),
            ("ambas_marcam", "sim"),
            ("multigols", "de_1_a_4"),
            ("chance_dupla", "mandante_ou_empate"),
        ]
        avaliacoes = []
        for fixture_id, (mercado, selecao) in enumerate(tipos, 1):
            probabilidade = 0.90 if mercado == "total_gols" and "under" in selecao else 0.80
            perna = {
                "fixture_id": fixture_id,
                "bookmaker_id": 7,
                "bookmaker": "Casa A",
                "mercado": mercado,
                "selecao": selecao,
                "odd": 1.50,
                "probabilidade_modelo": probabilidade,
                "edge_modelo": round(probabilidade - 1.0 / 1.50, 4),
                "qualidade_contexto": 90.0,
                "modelo": {"jogadores": {
                    lado: {"escalacao_confirmada": True}
                    for lado in ("mandante", "visitante")
                }},
            }
            avaliacoes.append({
                "jogo": {"fixture_id": fixture_id},
                "avaliacao": {"elegiveis": [perna]},
            })

        bilhetes = montar_bilhetes_pre_live(avaliacoes, maximo=8)
        temas = [item["tema"] for item in bilhetes]
        self.assertEqual("under", temas[0])
        self.assertEqual({"under"}, set(temas))
        self.assertEqual(4, len(bilhetes))

    def test_odd_final_pre_live_inicia_em_um_e_cinquenta(self):
        def avaliacao(fixture_id, odd):
            return {
                "jogo": {"fixture_id": fixture_id},
                "avaliacao": {"elegiveis": [{
                    "fixture_id": fixture_id,
                    "bookmaker_id": 7,
                    "bookmaker": "Casa A",
                    "mercado": "total_gols",
                    "selecao": "over_1.5",
                    "odd": odd,
                    "probabilidade_modelo": 0.85,
                    "edge_modelo": 0.15,
                    "qualidade_contexto": 90.0,
                    "modelo": {"jogadores": {
                        lado: {"escalacao_confirmada": True}
                        for lado in ("mandante", "visitante")
                    }},
                }]},
            }

        abaixo = montar_bilhetes_pre_live([avaliacao(1, 1.49)])
        no_limite = montar_bilhetes_pre_live([avaliacao(2, 1.50)])
        self.assertEqual([], abaixo)
        self.assertEqual(1, len(no_limite))

    def test_aplicacao_automatica_marca_confirmado_para_envio(self):
        perna = {
            "fixture_id": 101,
            "bookmaker_id": 7,
            "bookmaker": "Casa 7",
            "mercado": "chance_dupla",
            "selecao": "mandante_ou_empate",
            "odd": 1.50,
            "probabilidade_modelo": 0.80,
            "edge_modelo": 0.1333,
            "qualidade_contexto": 90.0,
            "modelo": {"jogadores": {
                lado: {"escalacao_confirmada": True}
                for lado in ("mandante", "visitante")
            }},
        }
        bilhetes = montar_bilhetes_pre_live(
            [{
                "jogo": {"fixture_id": 101},
                "avaliacao": {"elegiveis": [perna]},
            }],
            aplicacao_automatica=True,
        )

        self.assertEqual("apto_envio_automatico", bilhetes[0]["estado"])
        self.assertTrue(bilhetes[0]["aplicacao_automatica"])
        self.assertTrue(bilhetes[0]["telegram"])

    def test_revalida_publicado_sem_repetir_e_promove_simples(self):
        original = {
            "tipo": "simples",
            "bookmaker": "Casa 7",
            "odd_total": 1.50,
            "probabilidade_modelo": 0.75,
            "edge_modelo": 0.08,
            "estado": "preliminar_aguardando_escalacao",
            "versao": "v10",
            "linhagem_sha256": "linhagem-original",
            "pernas": [{
                "fixture_id": 101,
                "bookmaker_id": 7,
                "bookmaker": "Casa 7",
                "mercado": "chance_dupla",
                "selecao": "mandante_ou_empate",
                "odd": 1.50,
            }],
        }
        atual = {
            "fixture_id": 101,
            "bookmaker_id": 7,
            "bookmaker": "Casa 7",
            "mercado": "chance_dupla",
            "selecao": "mandante_ou_empate",
            "odd": 1.55,
            "probabilidade_modelo": 0.80,
            "probabilidade_conservadora": 0.75,
            "edge_modelo": 0.1548,
            "edge_conservador": 0.1048,
            "score_valor": 10.0,
            "qualidade_contexto": 90.0,
            "modelo": {"jogadores": {
                lado: {"escalacao_confirmada": True}
                for lado in ("mandante", "visitante")
            }},
        }

        revalidados = revalidar_bilhetes_publicados_pre_live(
            [{"id": 1, "bilhete": original}],
            [{
                "jogo": {"fixture_id": 101, "mandante": "A", "visitante": "B"},
                "avaliacao": {"elegiveis": [atual]},
            }],
            aplicacao_automatica=True,
        )

        self.assertEqual(1, len(revalidados))
        self.assertEqual("apto_envio_automatico", revalidados[0]["estado"])
        self.assertEqual(1.55, revalidados[0]["odd_total"])
        self.assertEqual("linhagem-original", revalidados[0]["linhagem_sha256"])
        self.assertTrue(revalidados[0]["revalidado_sem_republicar"])

    def test_v11_multipla_confirmada_permanece_em_observacao(self):
        def avaliacao(fixture_id):
            return {
                "jogo": {"fixture_id": fixture_id},
                "avaliacao": {"elegiveis": [{
                    "fixture_id": fixture_id,
                    "bookmaker_id": 7,
                    "bookmaker": "Casa A",
                    "mercado": "chance_dupla",
                    "selecao": "mandante_ou_empate",
                    "odd": 1.23,
                    "probabilidade_modelo": 0.90,
                    "probabilidade_conservadora": 0.87,
                    "edge_modelo": 0.086,
                    "edge_conservador": 0.057,
                    "qualidade_contexto": 90.0,
                    "modelo": {"jogadores": {
                        lado: {"escalacao_confirmada": True}
                        for lado in ("mandante", "visitante")
                    }},
                }]},
            }

        bilhetes = montar_bilhetes_pre_live(
            [avaliacao(1), avaliacao(2)], aplicacao_automatica=True
        )

        self.assertEqual(1, len(bilhetes))
        self.assertEqual("multipla_dois_jogos", bilhetes[0]["tipo"])
        self.assertEqual("apto_sombra_confirmado", bilhetes[0]["estado"])
        self.assertFalse(bilhetes[0]["telegram"])

    def test_nao_fabrica_chance_dupla_mais_gols(self):
        raw = [{
            "fixture": {"id": 10},
            "bookmakers": [{
                "id": 7, "name": "Casa A",
                "bets": [
                    {"name": "Double Chance", "values": [
                        {"value": "Home/Draw", "odd": "1.20"}
                    ]},
                    {"name": "Goals Over/Under", "values": [
                        {"value": "Over 1.5", "odd": "1.30"}
                    ]},
                ],
            }],
        }]
        mercados = {
            item["mercado"] for item in extrair_ofertas_api_football(raw)
        }
        self.assertEqual({"chance_dupla", "total_gols"}, mercados)
        self.assertNotIn("chance_dupla_mais_gols", mercados)

    def test_liquida_mercados_pela_pontuacao_regulamentar(self):
        fixture = {
            "fixture": {"id": 10, "status": {"short": "FT"}},
            "score": {"fulltime": {"home": 2, "away": 1}},
            "goals": {"home": 2, "away": 1},
        }
        casos = [
            ({"mercado": "resultado", "selecao": "mandante"}, "green"),
            ({"mercado": "chance_dupla", "selecao": "visitante_ou_empate"}, "red"),
            ({
                "mercado": "chance_dupla_mais_gols",
                "selecao": "mandante_ou_empate|over_1.5",
            }, "green"),
            ({"mercado": "total_gols", "selecao": "over_2.5"}, "green"),
            ({"mercado": "ambas_marcam", "selecao": "sim"}, "green"),
            ({"mercado": "resultado_mais_gols", "selecao": "mandante|over_1.5"}, "green"),
            ({
                "mercado": "total_gols_mais_ambas",
                "selecao": "over_2.5|sim",
            }, "green"),
            ({"mercado": "multigols", "selecao": "de_2_a_3"}, "green"),
            ({"mercado": "time_marca_gol", "selecao": "mandante|sim"}, "green"),
            ({
                "mercado": "multigols_time",
                "selecao": "mandante|de_1_a_4",
            }, "green"),
        ]
        for perna, esperado in casos:
            with self.subTest(perna=perna):
                self.assertEqual(
                    esperado, liquidar_perna_pre_live(perna, fixture)
                )

    def test_confirma_green_irreversivel_antes_do_fim(self):
        fixture = {
            "fixture": {"id": 10, "status": {"short": "2H"}},
            "goals": {"home": 1, "away": 1},
        }
        self.assertEqual(
            "green",
            liquidar_perna_pre_live(
                {"mercado": "total_gols", "selecao": "over_1.5"},
                fixture,
            ),
        )
        self.assertEqual(
            "green",
            liquidar_perna_pre_live(
                {"mercado": "ambas_marcam", "selecao": "sim"},
                fixture,
            ),
        )
        self.assertEqual(
            "green",
            liquidar_perna_pre_live(
                {
                    "mercado": "total_gols_mais_ambas",
                    "selecao": "over_1.5|sim",
                },
                fixture,
            ),
        )
        self.assertEqual(
            "pendente",
            liquidar_perna_pre_live(
                {"mercado": "chance_dupla", "selecao": "mandante_ou_empate"},
                fixture,
            ),
        )

    def test_multipla_vira_red_quando_uma_perna_ja_e_irreversivel(self):
        bilhete = {"pernas": [
            {
                "fixture_id": 10, "mercado": "total_gols",
                "selecao": "under_1.5", "odd": 1.25,
            },
            {
                "fixture_id": 11, "mercado": "resultado",
                "selecao": "mandante", "odd": 1.25,
            },
        ]}
        fixtures = {
            10: {
                "fixture": {"status": {"short": "2H"}},
                "goals": {"home": 1, "away": 1},
            },
            11: {
                "fixture": {"status": {"short": "1H"}},
                "goals": {"home": 0, "away": 0},
            },
        }
        self.assertEqual(
            "red", liquidar_bilhete_pre_live(bilhete, fixtures)["resultado"]
        )

    def test_portfolio_nao_repete_o_mesmo_fixture(self):
        pernas = []
        for mercado, edge in (("chance_dupla", 0.10), ("total_gols", 0.08)):
            pernas.append({
                "fixture_id": 10, "bookmaker_id": 7, "bookmaker": "Casa A",
                "mercado": mercado,
                "selecao": (
                    "mandante_ou_empate" if mercado == "chance_dupla"
                    else "over_1.5"
                ),
                "odd": 1.50, "probabilidade_modelo": 0.80,
                "edge_modelo": edge, "qualidade_contexto": 90.0,
                "modelo": {"jogadores": {
                    lado: {"escalacao_confirmada": True}
                    for lado in ("mandante", "visitante")
                }},
            })
        bilhetes = montar_bilhetes_pre_live([{
            "jogo": {"fixture_id": 10},
            "avaliacao": {"elegiveis": pernas},
        }])
        self.assertEqual(1, len(bilhetes))
        self.assertEqual("chance_dupla", bilhetes[0]["pernas"][0]["mercado"])

    def test_time_marca_substitui_multigols_mais_restritivo_na_mesma_odd(self):
        base = {
            "fixture_id": 10,
            "bookmaker_id": 7,
            "bookmaker": "Casa A",
            "odd": 1.53,
            "probabilidade_modelo": 0.75,
            "edge_modelo": 0.10,
            "edge_conservador": 0.08,
            "score_valor": 7.0,
            "qualidade_contexto": 90.0,
            "modelo": {"jogadores": {
                lado: {"escalacao_confirmada": True}
                for lado in ("mandante", "visitante")
            }},
        }
        pernas = [
            {
                **base,
                "mercado": "multigols_time",
                "selecao": "visitante|de_1_a_6",
            },
            {
                **base,
                "mercado": "time_marca_gol",
                "selecao": "visitante|sim",
            },
        ]

        bilhetes = montar_bilhetes_pre_live([{
            "jogo": {"fixture_id": 10},
            "avaliacao": {"elegiveis": pernas},
        }])

        self.assertEqual(1, len(bilhetes))
        self.assertEqual(
            "time_marca_gol", bilhetes[0]["pernas"][0]["mercado"]
        )

    def test_faixa_estendida_exige_qualidade_e_vantagem_maiores(self):
        def perna(fixture_id, qualidade, edge):
            return {
                "fixture_id": fixture_id,
                "bookmaker_id": 7,
                "bookmaker": "Casa A",
                "mercado": "total_gols",
                "selecao": "over_1.5",
                "odd": 1.68,
                "probabilidade_modelo": 0.74,
                "edge_modelo": edge,
                "qualidade_contexto": qualidade,
                "modelo": {"jogadores": {
                    lado: {"escalacao_confirmada": True}
                    for lado in ("mandante", "visitante")
                }},
            }

        avaliacoes = [{
            "jogo": {"fixture_id": fixture_id},
            "avaliacao": {"elegiveis": [item]},
        } for fixture_id, item in (
            (10, perna(10, 84.0, 0.08)),
            (11, perna(11, 90.0, 0.05)),
            (12, perna(12, 90.0, 0.08)),
        )]

        bilhetes = montar_bilhetes_pre_live(avaliacoes)

        self.assertEqual([12], [
            item["pernas"][0]["fixture_id"] for item in bilhetes
        ])
        self.assertEqual("estendida", bilhetes[0]["faixa_odd"])

    def test_liquida_multipla_e_remove_perna_anulada_da_odd(self):
        bilhete = {
            "pernas": [
                {
                    "fixture_id": 10, "mercado": "resultado",
                    "selecao": "mandante", "odd": 1.25,
                },
                {
                    "fixture_id": 11, "mercado": "total_gols",
                    "selecao": "over_1.5", "odd": 1.24,
                },
            ]
        }
        fixtures = {
            10: {
                "fixture": {"status": {"short": "FT"}},
                "score": {"fulltime": {"home": 1, "away": 0}},
            },
            11: {"fixture": {"status": {"short": "CANC"}}},
        }
        resultado = liquidar_bilhete_pre_live(bilhete, fixtures)
        self.assertEqual("green", resultado["resultado"])
        self.assertEqual(0.25, resultado["retorno"])


if __name__ == "__main__":
    unittest.main()
