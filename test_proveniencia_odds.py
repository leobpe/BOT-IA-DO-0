import unittest
import sqlite3
from datetime import datetime

from proveniencia_odds import (
    aplicar_proveniencia_odds,
    resumir_custodia_cotacao_oficial,
    validar_cotacao_executavel_oficial,
)


class ProvenienciaOddsTest(unittest.TestCase):
    def candidato(self, mercado="proximo_gol", linha="casa", odd=1.9):
        return {
            "mercado": mercado,
            "linha": linha,
            "odd": odd,
            "pontuacao_tecnica": 80,
            "status": "aprovado",
            "bloqueios": [],
            "features": {"mercado": mercado},
        }

    @staticmethod
    def origem(identificador, linha=2.5):
        return {
            "schema": "origem-mercado-odd-v1",
            "fonte": "betsapi",
            "identificador": identificador,
            "nome": "Match Goals",
            "linha": linha,
            "lados": ["over", "under"],
            "bookmaker": "bet365",
        }

    def test_proximo_gol_packball_preserva_evidencia_do_mercado(self):
        candidato = self.candidato()
        odds = {"ao_vivo": [{
            "mercado": "Marcar O Próximo Gol",
            "categoria": "gols",
            "escopo": "proximo",
            "tipo_mercado": "proximo",
            "selecoes": {
                "casa": 1.9,
                "visitante": 2.4,
                "sem_gol": 4.2,
            },
            "coletado_em": "2026-08-13T12:00:00",
            "cache": False,
        }]}

        retorno = aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 0, 30)
        )

        self.assertIs(retorno[0], candidato)
        self.assertEqual(candidato["fonte_odds"], "packball")
        self.assertEqual(candidato["coletado_em_odds"], "2026-08-13T12:00:00")
        self.assertEqual(candidato["idade_odds_segundos"], 30.0)
        self.assertIs(candidato["odds_cache"], False)
        self.assertEqual(candidato["tipo_mercado_odds"], "proximo")
        self.assertEqual(candidato["features"]["fonte_odds"], "packball")
        self.assertEqual(
            candidato["features"]["cotacao_entrada_clv_estado"],
            "congelada_v1",
        )
        self.assertEqual(
            candidato["features"]["cotacao_entrada_clv"],
            {
                "schema": "cotacao-entrada-clv-v1",
                "mercado": "proximo_gol",
                "fonte": "packball",
                "bookmaker": None,
                "coletado_em": "2026-08-13T12:00:00",
                "idade_segundos": 30.0,
                "cache": False,
                "tipo": "tres_vias",
                "selecao": "casa",
                "odds": {
                    "casa": 1.9, "visitante": 2.4, "sem_gol": 4.2,
                },
                "odd_selecionada": 1.9,
            },
        )
        self.assertEqual(candidato["status"], "aprovado")
        self.assertEqual(candidato["bloqueios"], [])

    def test_proximo_gol_api_nao_herda_metadado_global_packball(self):
        candidato = self.candidato()
        candidato["fonte_odds"] = "packball"
        odds = {
            "ao_vivo": [{
                "mercado": "Marcar O Próximo Gol",
                "categoria": "gols",
                "escopo": "proximo",
                "tipo_mercado": "proximo",
                "selecoes": {
                    "casa": 1.9,
                    "visitante": 2.4,
                    "sem_gol": 4.2,
                },
                "fonte": "api_football",
                "bookmaker": "Bet 365",
                "cache": True,
                "idade_segundos": 125,
                "coletado_em": "2026-08-13T12:00:00",
            }],
            "_metadados": {
                "cache": False,
                "idade_segundos": 0,
                "coletado_em": "2026-08-13T12:02:00",
            },
        }

        aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 2, 0)
        )

        self.assertEqual(candidato["fonte_odds"], "api_football")
        self.assertEqual(candidato["bookmaker_odds"], "Bet 365")
        self.assertEqual(candidato["idade_odds_segundos"], 125.0)
        self.assertIs(candidato["odds_cache"], True)
        self.assertEqual(candidato["bloqueios"], [])

    def test_idade_efetiva_usa_maior_entre_declarada_e_instante(self):
        candidato = self.candidato()
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "proximo",
            "selecoes": {"casa": 1.9},
            "fonte": "api_football",
            "cache": True,
            "idade_segundos": 10,
            "coletado_em": "2026-08-13T12:00:00",
        }]}

        aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 7, 0)
        )

        self.assertEqual(candidato["idade_odds_segundos"], 420.0)
        self.assertIn("odds_desatualizadas", candidato["bloqueios"])
        self.assertEqual(candidato["status"], "rejeitado")

    def test_oferta_sem_proveniencia_falha_fechada(self):
        candidato = self.candidato()
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "proximo",
            "selecoes": {"casa": 1.9},
        }]}

        aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 0, 0)
        )

        self.assertIn("fonte_odds_desconhecida", candidato["bloqueios"])
        self.assertIn("cache_odds_indeterminado", candidato["bloqueios"])
        self.assertIn("frescor_odds_indeterminado", candidato["bloqueios"])
        self.assertEqual(candidato["status"], "rejeitado")

    def test_cache_com_idade_declarada_pode_comprovar_frescor(self):
        candidato = self.candidato()
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "proximo",
            "selecoes": {"casa": 1.9},
            "fonte": "api_football",
            "cache": True,
            "idade_segundos": 45,
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertEqual(candidato["idade_odds_segundos"], 45.0)
        self.assertNotIn("frescor_odds_indeterminado", candidato["bloqueios"])
        self.assertEqual(candidato["status"], "aprovado")

    def test_odd_sem_oferta_exata_falha_fechada(self):
        candidato = self.candidato(odd=2.0)
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "proximo",
            "selecoes": {"casa": 1.9},
            "fonte": "api_football",
            "cache": False,
            "idade_segundos": 0,
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertIn("oferta_odds_nao_rastreavel", candidato["bloqueios"])
        self.assertIsNone(candidato["fonte_odds"])
        self.assertEqual(candidato["status"], "rejeitado")

    def test_oferta_ft_usa_metadados_da_oferta_antes_do_mercado(self):
        candidato = self.candidato("gol_ft", 2.5, 1.82)
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "packball",
            "cache": False,
            "coletado_em": "2026-08-13T11:59:00",
            "ofertas": [{
                "linha": 2.5,
                "over": 1.82,
                "under": 1.98,
                "fonte": "api_football",
                "bookmaker": "Book A",
                "cache": True,
                "idade_segundos": 30,
                "coletado_em": "2026-08-13T12:00:00",
            }],
        }]}

        aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 0, 20)
        )

        self.assertEqual(candidato["fonte_odds"], "api_football")
        self.assertEqual(candidato["bookmaker_odds"], "Book A")
        self.assertEqual(candidato["idade_odds_segundos"], 30.0)
        self.assertIs(candidato["odds_cache"], True)
        self.assertEqual(
            candidato["features"]["cotacao_entrada_clv"]["over"], 1.82
        )
        self.assertEqual(
            candidato["features"]["cotacao_entrada_clv"]["under"], 1.98
        )
        self.assertEqual(
            candidato["features"]["cotacao_entrada_clv"]["bookmaker"],
            "Book A",
        )

    def test_nao_congela_par_binario_incompleto(self):
        candidato = self.candidato("gol_ft", 2.5, 1.82)
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "packball",
            "cache": False,
            "idade_segundos": 2,
            "ofertas": [{"linha": 2.5, "over": 1.82}],
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertNotIn("cotacao_entrada_clv", candidato["features"])
        self.assertEqual(
            candidato["features"]["cotacao_entrada_clv_estado"],
            "mercado_incompleto_ou_invalido",
        )

    def test_nao_congela_cotacao_empatada_e_ambigua(self):
        candidato = self.candidato("gol_ft", 2.5, 1.82)
        base = {
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "packball",
            "cache": False,
            "idade_segundos": 2,
            "coletado_em": "2026-08-13T12:00:00",
        }
        odds = {"ao_vivo": [
            {**base, "ofertas": [{
                "linha": 2.5, "over": 1.82, "under": 1.98,
            }]},
            {**base, "ofertas": [{
                "linha": 2.5, "over": 1.82, "under": 2.08,
            }]},
        ]}

        aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 0, 2)
        )

        self.assertNotIn("cotacao_entrada_clv", candidato["features"])
        self.assertEqual(
            candidato["features"]["cotacao_entrada_clv_estado"],
            "oferta_ambigua",
        )

    def test_grupos_distintos_com_mesmo_preco_continuam_ambiguos(self):
        candidato = self.candidato("gol_ft", 2.5, 1.82)
        base = {
            "categoria": "gols", "escopo": "total",
            "tipo_mercado": "total", "formato": "duas_opcoes",
            "fonte": "betsapi", "bookmaker": "bet365",
            "cache": False, "idade_segundos": 2,
            "coletado_em": "2026-08-13T12:00:00",
        }
        odds = {"ao_vivo": [
            {**base, "ofertas": [{
                "linha": 2.5, "over": 1.82, "under": 1.98,
                "origem_mercado": self.origem("grupo-a"),
            }]},
            {**base, "ofertas": [{
                "linha": 2.5, "over": 1.82, "under": 1.98,
                "origem_mercado": self.origem("grupo-b"),
            }]},
        ]}

        aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 0, 2)
        )

        self.assertNotIn("cotacao_entrada_clv", candidato["features"])
        self.assertEqual(
            "oferta_ambigua",
            candidato["features"]["cotacao_entrada_clv_estado"],
        )

    def test_origem_esperada_seleciona_grupo_exato_e_congela_v2(self):
        candidato = self.candidato("gol_ft", 2.5, 1.82)
        candidato["features"]["acompanhamento_odd_rapido"] = {
            "origem_mercado_odd": self.origem("grupo-b")
        }
        base = {
            "categoria": "gols", "escopo": "total",
            "tipo_mercado": "total", "formato": "duas_opcoes",
            "fonte": "betsapi", "bookmaker": "bet365",
            "cache": False, "idade_segundos": 2,
            "coletado_em": "2026-08-13T12:00:00",
        }
        odds = {"ao_vivo": [
            {**base, "ofertas": [{
                "linha": 2.5, "over": 1.82, "under": 1.98,
                "origem_mercado": self.origem("grupo-a"),
            }]},
            {**base, "ofertas": [{
                "linha": 2.5, "over": 1.82, "under": 1.98,
                "origem_mercado": self.origem("grupo-b"),
            }]},
        ]}

        aplicar_proveniencia_odds(
            [candidato], odds, datetime(2026, 8, 13, 12, 0, 2)
        )

        cotacao = candidato["features"]["cotacao_entrada_clv"]
        self.assertEqual("cotacao-entrada-clv-v2", cotacao["schema"])
        self.assertEqual("grupo-b", cotacao["origem_mercado"]["identificador"])

    def test_origem_esperada_divergente_bloqueia_candidato(self):
        candidato = self.candidato("gol_ft", 2.5, 1.82)
        candidato["features"]["acompanhamento_odd_rapido"] = {
            "origem_mercado_odd": self.origem("grupo-esperado")
        }
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "tipo_mercado": "total", "formato": "duas_opcoes",
            "fonte": "betsapi", "bookmaker": "bet365",
            "cache": False, "idade_segundos": 2,
            "ofertas": [{
                "linha": 2.5, "over": 1.82, "under": 1.98,
                "origem_mercado": self.origem("grupo-observado"),
            }],
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertIn(
            "origem_mercado_entrada_divergente", candidato["bloqueios"]
        )
        self.assertEqual(
            "origem_mercado_entrada_divergente",
            candidato["features"]["cotacao_entrada_clv_estado"],
        )
        self.assertEqual("rejeitado", candidato["status"])

    def test_curva_dominada_do_mesmo_grupo_bloqueia_cotacao(self):
        candidato = self.candidato("gol_ft", 1.5, 1.80)
        candidato["features"]["acompanhamento_odd_rapido"] = {
            "origem_mercado_odd": self.origem("grupo-a", 1.5)
        }
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "tipo_mercado": "total", "formato": "duas_opcoes",
            "fonte": "betsapi", "bookmaker": "bet365",
            "cache": False, "idade_segundos": 2,
            "ofertas": [
                {
                    "linha": 0.5, "over": 2.00, "under": 1.70,
                    "origem_mercado": self.origem("grupo-a", 0.5),
                },
                {
                    "linha": 1.5, "over": 1.80, "under": 2.00,
                    "origem_mercado": self.origem("grupo-a", 1.5),
                },
            ],
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertIn("curva_linhas_odd_incoerente", candidato["bloqueios"])
        self.assertNotIn("cotacao_entrada_clv", candidato["features"])
        self.assertEqual(
            "curva_linhas_odd_incoerente",
            candidato["features"]["cotacao_entrada_clv_estado"],
        )
        self.assertEqual("rejeitado", candidato["status"])

    def test_localiza_ht_e_asiatico_por_periodo_sem_confundir_mercados(self):
        ht = self.candidato("gol_ht", 0.5, 1.75)
        canto = self.candidato("escanteios_2t", 5.5, 1.88)
        odds = {"ao_vivo": [
            {
                "categoria": "gols",
                "tipo_mercado": "total",
                "ofertas_ht": [{"linha": 0.5, "over": 1.75}],
                "fonte": "packball",
                "cache": False,
                "idade_segundos": 5,
            },
            {
                "categoria": "escanteios",
                "tipo_mercado": "total",
                "ofertas_periodos": {
                    "2T": {"ofertas": [{"linha": 5.5, "over": 1.88}]}
                },
                "fonte": "fonte_errada",
                "cache": False,
                "idade_segundos": 1,
            },
            {
                "categoria": "escanteios",
                "tipo_mercado": "asiatico",
                "ofertas_periodos": {
                    "2T": {"ofertas": [{"linha": 5.5, "over": 1.88}]}
                },
                "fonte": "api_football",
                "cache": True,
                "idade_segundos": 20,
            },
        ]}

        aplicar_proveniencia_odds([ht, canto], odds)

        self.assertEqual(ht["fonte_odds"], "packball")
        self.assertEqual(canto["fonte_odds"], "api_football")
        self.assertEqual(canto["tipo_mercado_odds"], "asiatico")

    def test_ht_nao_herda_oferta_de_categoria_errada(self):
        candidato = self.candidato("gol_ht", 0.5, 1.75)
        odds = {"ao_vivo": [{
            "categoria": "escanteios",
            "ofertas_ht": [{"linha": 0.5, "over": 1.75}],
            "fonte": "packball",
            "cache": False,
            "idade_segundos": 0,
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertIn(
            "oferta_odds_nao_rastreavel", candidato["bloqueios"]
        )
        self.assertEqual(candidato["status"], "rejeitado")

    def test_reexecucao_remove_bloqueio_global_errado_e_reaprova(self):
        candidato = self.candidato()
        candidato.update({
            "status": "rejeitado",
            "bloqueios": ["odds_desatualizadas"],
            "idade_odds_segundos": 999,
        })
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "proximo",
            "selecoes": {"casa": 1.9},
            "fonte": "api_football",
            "cache": False,
            "idade_segundos": 2,
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertEqual(candidato["bloqueios"], [])
        self.assertEqual(candidato["idade_odds_segundos"], 2.0)
        self.assertEqual(candidato["status"], "aprovado")

    def test_preserva_bloqueio_que_nao_e_de_proveniencia(self):
        candidato = self.candidato()
        candidato["bloqueios"] = ["lado_dominante_sem_chute_recente"]
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "proximo",
            "selecoes": {"casa": 1.9},
            "fonte": "api_football",
            "cache": False,
            "idade_segundos": 2,
        }]}

        aplicar_proveniencia_odds([candidato], odds)

        self.assertEqual(
            candidato["bloqueios"],
            ["lado_dominante_sem_chute_recente"],
        )
        self.assertEqual(candidato["status"], "rejeitado")

    def test_fuso_local_nao_transforma_odd_antiga_em_idade_zero(self):
        candidato = self.candidato("gol_ft", 2.5, 2.5)
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "thestatsapi",
            "bookmaker": "Bet365",
            "cache": False,
            "ofertas": [{
                "linha": 2.5,
                "over": 2.5,
                "under": 1.5,
                "fonte": "thestatsapi",
                "bookmaker": "Bet365",
                "cache": False,
                "idade_segundos": 0,
                "coletado_em": "2026-08-30T20:40:30+00:00",
            }],
        }]}

        aplicar_proveniencia_odds(
            [candidato],
            odds,
            datetime.fromisoformat("2026-08-30T16:59:13-04:00"),
        )

        self.assertEqual(candidato["idade_odds_segundos"], 1123.0)
        self.assertIn("odds_desatualizadas", candidato["bloqueios"])
        self.assertEqual(candidato["status"], "rejeitado")

    def test_localiza_a_oferta_exata_mais_recente(self):
        candidato = self.candidato("gol_ft", 2.5, 1.143)
        odds = {"ao_vivo": [
            {
                "categoria": "gols",
                "escopo": "total",
                "tipo_mercado": "total",
                "formato": "duas_opcoes",
                "fonte": "thestatsapi",
                "cache": False,
                "ofertas": [{
                    "linha": 2.5,
                    "over": 1.143,
                    "fonte": "thestatsapi",
                    "bookmaker": "Bet365",
                    "cache": False,
                    "coletado_em": "2026-08-30T20:40:30+00:00",
                }],
            },
            {
                "categoria": "gols",
                "escopo": "total",
                "tipo_mercado": "total",
                "formato": "duas_opcoes",
                "fonte": "thestatsapi",
                "cache": False,
                "ofertas": [{
                    "linha": 2.5,
                    "over": 1.143,
                    "fonte": "thestatsapi",
                    "bookmaker": "Bet365",
                    "cache": False,
                    "coletado_em": "2026-08-30T20:58:47+00:00",
                }],
            },
        ]}

        aplicar_proveniencia_odds(
            [candidato],
            odds,
            datetime.fromisoformat("2026-08-30T16:59:13-04:00"),
        )

        self.assertEqual(
            candidato["coletado_em_odds"],
            "2026-08-30T20:58:47+00:00",
        )
        self.assertEqual(candidato["idade_odds_segundos"], 26.0)
        self.assertNotIn("odds_desatualizadas", candidato["bloqueios"])

    def test_custodia_oficial_aceita_somente_betsapi_bet365_congelada(self):
        candidato = self.candidato("gol_ft", 2.5, 1.80)
        origem = self.origem("1778", linha=2.5)
        candidato["origem_mercado"] = origem
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "cache": False,
            "origem_mercado": origem,
            "ofertas": [{
                "linha": 2.5,
                "over": 1.80,
                "under": 2.05,
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "cache": False,
                "coletado_em": "2026-09-12T20:00:00+00:00",
                "origem_mercado": origem,
            }],
        }]}

        aplicar_proveniencia_odds(
            [candidato],
            odds,
            datetime.fromisoformat("2026-09-12T16:00:05-04:00"),
        )
        resultado = validar_cotacao_executavel_oficial(candidato)

        self.assertTrue(resultado["apto"])
        self.assertEqual(resultado["fonte_observada"], "betsapi")
        self.assertEqual(resultado["bookmaker_observada"], "bet365")
        self.assertFalse(resultado["simulacoes_afetadas"])

    def test_custodia_oficial_recusa_preco_agregado_sem_bookmaker(self):
        candidato = self.candidato("gol_ft", 2.5, 1.80)
        candidato.update({
            "fonte_odds": "api_football",
            "bookmaker_odds": None,
        })
        candidato["features"].update({
            "fonte_odds": "api_football",
            "bookmaker_odds": None,
            "cotacao_entrada_clv_estado": "congelada_v1",
            "cotacao_entrada_clv": {
                "schema": "cotacao-entrada-clv-v1",
                "mercado": "gol_ft",
                "fonte": "api_football",
                "bookmaker": None,
                "coletado_em": "2026-09-12T20:00:00+00:00",
                "idade_segundos": 5.0,
                "cache": False,
                "tipo": "binaria",
                "linha": 2.5,
                "over": 1.80,
                "under": 2.05,
                "odd_selecionada": 1.80,
            },
        })

        resultado = validar_cotacao_executavel_oficial(candidato)

        self.assertFalse(resultado["apto"])
        self.assertEqual(
            resultado["motivo"], "schema_cotacao_sem_origem_exata"
        )

    def test_custodia_oficial_detecta_adulteracao_entre_prova_e_candidato(self):
        candidato = self.candidato("gol_ft", 2.5, 1.80)
        origem = self.origem("1778", linha=2.5)
        candidato.update({
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
        })
        candidato["features"].update({
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
            "cotacao_entrada_clv_estado": "congelada_v1",
            "cotacao_entrada_clv": {
                "schema": "cotacao-entrada-clv-v2",
                "mercado": "gol_ft",
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": "2026-09-12T20:00:00+00:00",
                "idade_segundos": 5.0,
                "cache": False,
                "tipo": "binaria",
                "linha": 2.5,
                "over": 1.80,
                "under": 2.05,
                "odd_selecionada": 1.80,
                "origem_mercado": origem,
            },
        })
        candidato["odd"] = 1.90

        resultado = validar_cotacao_executavel_oficial(candidato)

        self.assertFalse(resultado["apto"])
        self.assertEqual(resultado["motivo"], "odd_cotacao_divergente")

    def test_resumo_custodia_separa_apto_de_bloqueado_sem_mudar_sinais(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                mercado TEXT,
                linha TEXT,
                odd REAL,
                probabilidade_calibrada REAL,
                status TEXT,
                features_json TEXT
            );
            CREATE TABLE entregas_alertas (
                canal TEXT,
                status TEXT,
                erro TEXT
            );
        """)
        origem = self.origem("1778", linha=2.5)
        features = {
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
            "cotacao_entrada_clv_estado": "congelada_v1",
            "cotacao_entrada_clv": {
                "schema": "cotacao-entrada-clv-v2",
                "mercado": "gol_ft",
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": "2026-09-12T20:00:00+00:00",
                "idade_segundos": 5.0,
                "cache": False,
                "tipo": "binaria",
                "linha": 2.5,
                "over": 1.80,
                "under": 2.05,
                "odd_selecionada": 1.80,
                "origem_mercado": origem,
            },
        }
        conexao.execute(
            "INSERT INTO sinais VALUES (1,?,?,?,?,?,?)",
            (
                "gol_ft", "2.5", 1.80, 0.80, "aprovado",
                __import__("json").dumps(features),
            ),
        )
        features_ruins = dict(features)
        features_ruins["fonte_odds"] = "packball"
        features_ruins["cotacao_entrada_clv"] = dict(
            features["cotacao_entrada_clv"],
            schema="cotacao-entrada-clv-v1",
            fonte="packball",
            bookmaker=None,
        )
        conexao.execute(
            "INSERT INTO sinais VALUES (2,?,?,?,?,?,?)",
            (
                "gol_ft", "2.5", 1.80, 0.80, "aprovado",
                __import__("json").dumps(features_ruins),
            ),
        )
        conexao.execute(
            "INSERT INTO entregas_alertas VALUES (?,?,?)",
            (
                "gateway:oficial", "bloqueado",
                "cotacao_oficial_nao_executavel",
            ),
        )

        resumo = resumir_custodia_cotacao_oficial(conexao)

        self.assertEqual(resumo["sinais_analisados"], 2)
        self.assertEqual(resumo["aptos"], 1)
        self.assertEqual(resumo["bloqueados"], 1)
        self.assertEqual(resumo["bloqueios_gateway"], 1)
        self.assertFalse(resumo["simulacoes_afetadas"])
        self.assertEqual(
            conexao.execute("SELECT COUNT(*) FROM sinais").fetchone()[0], 2
        )
        conexao.close()


if __name__ == "__main__":
    unittest.main()
