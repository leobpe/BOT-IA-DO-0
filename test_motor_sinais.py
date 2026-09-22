import unittest

from motor_sinais import gerar_candidatos


class MotorSinaisTest(unittest.TestCase):
    def dados(self):
        return {
            "jogo": {"status": "65 '", "placar": "0-0"},
            "estatisticas": {
                "Chutes no gol": "5-3",
                "Escanteios": "4-4",
            },
            "evolucao": {
                "5": {
                    "chutes": [4, 2],
                    "escanteios": [1, 1],
                    "duracao_real_minutos": 5,
                    "resets_detectados": [],
                    "pressao_resumo": {
                        "media": [65, 35],
                        "pico": [80, 45],
                    },
                },
                "10": {
                    "chutes": [6, 3],
                    "escanteios": [2, 1],
                    "duracao_real_minutos": 10,
                    "resets_detectados": [],
                },
            },
            "odds": {
                "ao_vivo": [
                    {
                        "mercado": "Total Gols",
                        "dados": "Over 1.5",
                        "categoria": "gols",
                        "ofertas": [
                            {"linha": 0.5, "over": 1.8, "under": 2.0}
                        ],
                    },
                    {
                        "mercado": "Escanteios",
                        "dados": "Over 8.5",
                        "categoria": "escanteios",
                        "tipo_mercado": "total",
                        "ofertas": [
                            {"linha": 8.5, "over": 1.9, "under": 1.9}
                        ],
                    },
                ]
            },
            "qualidade": {"pontuacao": 95, "apto_para_sinal": True},
        }

    def test_gera_candidatos_rastreaveis_sem_fingir_probabilidade(self):
        dados = self.dados()
        candidatos = gerar_candidatos(**dados)
        self.assertEqual(len(candidatos), 7)
        self.assertTrue(all(item["regra_versao"] for item in candidatos))
        self.assertTrue(
            all(item["probabilidade_calibrada"] is None for item in candidatos)
        )
        self.assertEqual(candidatos[0]["status"], "aprovado")

    def test_anexa_linha_e_odd_estruturadas(self):
        dados = self.dados()
        dados["odds"]["ao_vivo"][0].update(
            {
                "categoria": "gols",
                "ofertas": [{"linha": 0.5, "over": 1.85, "under": 1.95}],
            }
        )
        candidato = gerar_candidatos(**dados)[0]
        self.assertEqual(candidato["linha"], 0.5)
        self.assertEqual(candidato["odd"], 1.85)

    def test_registra_features_temporais_com_duracao_medida(self):
        candidato = gerar_candidatos(**self.dados())[0]
        features = candidato["features"]

        self.assertEqual(features["schema_versao"], "features-temporais-v2")
        self.assertEqual(features["chutes_no_gol"], [5.0, 3.0])
        self.assertEqual(features["chutes_no_gol_total"], 8.0)
        self.assertEqual(features["janelas"]["5"]["chutes_por_minuto"], 1.2)
        self.assertEqual(
            features["janelas"]["5"]["chutes_por_minuto_lados"],
            [0.8, 0.4],
        )
        self.assertEqual(
            features["janelas"]["5"]["escanteios_por_minuto_lados"],
            [0.2, 0.2],
        )
        self.assertEqual(features["janelas"]["10"]["chutes_por_minuto"], 0.9)
        self.assertFalse(features["janelas"]["15"]["disponivel"])

    def test_nao_inventa_taxa_sem_duracao_nem_zero_para_dado_ausente(self):
        dados = self.dados()
        dados["evolucao"]["10"].pop("duracao_real_minutos")
        dados["estatisticas"].pop("Chutes no gol")

        features = gerar_candidatos(**dados)[0]["features"]

        self.assertIsNone(features["janelas"]["10"]["chutes_por_minuto"])
        self.assertIsNone(
            features["janelas"]["10"]["chutes_por_minuto_lados"]
        )
        self.assertIsNone(features["chutes_no_gol"])
        self.assertIsNone(features["chutes_no_gol_total"])

    def test_linha_que_exige_multiplos_gols_e_bloqueada(self):
        dados = self.dados()
        dados["odds"]["ao_vivo"][0]["ofertas"] = [
            {"linha": 2.5, "over": 1.85, "under": 1.95}
        ]

        candidato = gerar_candidatos(**dados)[0]

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn("linha_exige_multiplos_gols", candidato["bloqueios"])

    def test_qualidade_ruim_bloqueia_mesmo_com_atividade_alta(self):
        dados = self.dados()
        dados["qualidade"] = {"pontuacao": 30, "apto_para_sinal": False}
        candidatos = gerar_candidatos(**dados)
        self.assertTrue(all(item["status"] == "rejeitado" for item in candidatos))
        self.assertTrue(
            all("qualidade_insuficiente" in item["bloqueios"] for item in candidatos)
        )

    def test_reset_de_contador_bloqueia(self):
        dados = self.dados()
        dados["evolucao"]["5"]["resets_detectados"] = ["chutes"]
        candidatos = gerar_candidatos(**dados)
        self.assertTrue(all(item["status"] == "rejeitado" for item in candidatos))

    def test_sem_historico_rejeita_candidatos(self):
        dados = self.dados()
        dados["evolucao"] = {"5": None, "10": None, "15": None}
        candidatos = gerar_candidatos(**dados)
        self.assertTrue(all(item["status"] == "rejeitado" for item in candidatos))

    def test_odds_conhecidamente_antigas_bloqueiam_sinal(self):
        dados = self.dados()
        dados["odds"]["_metadados"] = {"idade_segundos": 361}

        candidatos = gerar_candidatos(**dados)

        self.assertTrue(all(item["status"] == "rejeitado" for item in candidatos))
        self.assertTrue(
            all("odds_desatualizadas" in item["bloqueios"] for item in candidatos)
        )

    def test_mercado_sem_odd_estruturada_nao_e_aprovado(self):
        dados = self.dados()
        dados["odds"] = {
            "ao_vivo": [{"mercado": "Total Gols", "dados": "Over 1.5"}]
        }

        candidato = gerar_candidatos(**dados)[0]

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn("odd_ao_vivo_indisponivel", candidato["bloqueios"])

    def test_odd_fora_da_faixa_operacional_nao_e_aprovada(self):
        dados = self.dados()
        dados["odds"]["ao_vivo"][0]["ofertas"][0]["over"] = 1.2

        candidato = gerar_candidatos(**dados)[0]

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn(
            "odd_fora_da_faixa_operacional", candidato["bloqueios"]
        )

    def test_pressao_alta_sem_atividade_recente_nao_aprova_gols(self):
        dados = self.dados()
        dados["evolucao"]["5"].update(
            {
                "chutes": [1, 0],
                "pressao_resumo": {
                    "media": [88, 12],
                    "pico": [95, 20],
                },
            }
        )
        dados["estatisticas"]["Chutes no gol"] = "8-3"

        candidatos = {
            item["mercado"]: item for item in gerar_candidatos(**dados)
        }

        for mercado in ("gol_ft", "gol_ht", "proximo_gol"):
            self.assertEqual(candidatos[mercado]["status"], "rejeitado")
            self.assertIn(
                "atividade_recente_insuficiente_gols",
                candidatos[mercado]["bloqueios"],
            )

    def test_proximo_gol_exige_chute_do_lado_dominante(self):
        dados = self.dados()
        dados["evolucao"]["5"]["chutes"] = [0, 3]
        dados["evolucao"]["5"]["pressao_resumo"] = {
            "media": [80, 20],
            "pico": [90, 40],
        }

        candidato = gerar_candidatos(**dados)[3]

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn(
            "lado_dominante_sem_chute_recente", candidato["bloqueios"]
        )

    def test_escanteios_por_tempo_usam_odds_independentes(self):
        dados = self.dados()
        dados["odds"]["ao_vivo"][1]["tipo_mercado"] = "asiatico"
        dados["odds"]["ao_vivo"][1]["ofertas_periodos"] = {
            "1T": {
                "formato": "duas_opcoes",
                "ofertas": [{
                    "linha": 4.5, "over": 1.82, "under": 1.95,
                    "fonte": "api_football", "idade_segundos": 10,
                }],
            },
            "2T": {
                "formato": "duas_opcoes",
                "ofertas": [{"linha": 5.5, "over": 1.88, "under": 1.90}],
            },
        }

        dados["jogo"]["status"] = "35 '"
        dados["estatisticas"]["Escanteios"] = "2-2"
        primeiro_tempo = {
            item["mercado"]: item for item in gerar_candidatos(**dados)
        }
        dados["jogo"]["status"] = "65 '"
        dados["estatisticas"]["Escanteios"] = "4-4"
        dados["evolucao"]["escanteios_intervalo"] = 3
        segundo_tempo = {
            item["mercado"]: item for item in gerar_candidatos(**dados)
        }

        self.assertEqual(primeiro_tempo["escanteios_1t"]["linha"], 4.5)
        self.assertEqual(primeiro_tempo["escanteios_1t"]["odd"], 1.82)
        self.assertEqual(primeiro_tempo["escanteios_1t"]["status"], "aprovado")
        self.assertEqual(
            primeiro_tempo["escanteios_1t"]["features"]["fonte_odds"],
            "api_football",
        )
        self.assertEqual(
            primeiro_tempo["escanteios_1t"]["features"][
                "idade_odds_segundos"
            ],
            10.0,
        )
        self.assertIn(
            "fora_da_janela_escanteios_2t",
            primeiro_tempo["escanteios_2t"]["bloqueios"],
        )
        self.assertEqual(segundo_tempo["escanteios_2t"]["linha"], 5.5)
        self.assertEqual(segundo_tempo["escanteios_2t"]["odd"], 1.88)
        self.assertEqual(segundo_tempo["escanteios_2t"]["status"], "aprovado")
        self.assertIn(
            "fora_da_janela_escanteios_1t",
            segundo_tempo["escanteios_1t"]["bloqueios"],
        )

    def test_escanteios_por_tempo_rejeitam_mercado_nao_asiatico(self):
        dados = self.dados()
        dados["jogo"]["status"] = "35 '"
        dados["estatisticas"]["Escanteios"] = "2-2"
        dados["odds"]["ao_vivo"][1].update({
            "tipo_mercado": "total",
            "ofertas_periodos": {
                "1T": {
                    "formato": "duas_opcoes",
                    "ofertas": [{
                        "linha": 4.5,
                        "over": 1.82,
                        "under": 1.95,
                    }],
                }
            },
        })

        candidato = {
            item["mercado"]: item for item in gerar_candidatos(**dados)
        }["escanteios_1t"]

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIsNone(candidato["odd"])
        self.assertIsNone(candidato["tipo_mercado_odds"])
        self.assertIn("odd_ao_vivo_indisponivel", candidato["bloqueios"])

    def test_separa_escanteio_normal_do_asiatico_ft(self):
        dados = self.dados()
        dados["odds"]["ao_vivo"].append({
            "mercado": "Escanteios Asiáticos",
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "ofertas": [{
                "linha": 8.0,
                "over": 1.85,
                "under": 1.95,
                "fonte": "bet365_site",
            }],
        })

        candidatos = {
            item["mercado"]: item for item in gerar_candidatos(**dados)
        }

        self.assertEqual(candidatos["proximo_escanteio"]["linha"], 8.5)
        self.assertEqual(
            candidatos["proximo_escanteio"]["tipo_mercado_odds"],
            "total",
        )
        self.assertEqual(
            candidatos["escanteios_ft_asiatico"]["linha"],
            8.0,
        )
        self.assertEqual(
            candidatos["escanteios_ft_asiatico"]["tipo_mercado_odds"],
            "asiatico",
        )
        self.assertEqual(
            candidatos["escanteios_ft_asiatico"]["fonte_odds"],
            "bet365_site",
        )

    def test_odd_api_em_cache_vencido_nao_aprova_sinal(self):
        dados = self.dados()
        dados["jogo"]["status"] = "35 '"
        dados["estatisticas"]["Escanteios"] = "2-2"
        dados["odds"]["ao_vivo"][1]["tipo_mercado"] = "asiatico"
        dados["odds"]["ao_vivo"][1]["ofertas_periodos"] = {
            "1T": {
                "formato": "duas_opcoes",
                "ofertas": [{
                    "linha": 4.5, "over": 1.82, "under": 1.95,
                    "fonte": "api_football", "idade_segundos": 400,
                }],
            }
        }

        candidato = {
            item["mercado"]: item for item in gerar_candidatos(**dados)
        }["escanteios_1t"]

        self.assertEqual(candidato["status"], "rejeitado")
        self.assertIn("odds_desatualizadas", candidato["bloqueios"])


if __name__ == "__main__":
    unittest.main()
