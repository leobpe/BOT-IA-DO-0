import copy
import unittest
from datetime import datetime, timezone

from melhor_preco_sombra import (
    VERSAO,
    anexar_melhor_preco_sombra,
    avaliar_melhor_preco_sombra,
)
from validacao_resultado_valor_justo import (
    validar_politica_avaliacao_resultado,
)
from validacao_veto_preco_justo import validar_avaliacao_veto


AGORA = datetime(2026, 9, 1, 12, 0, 30, tzinfo=timezone.utc)


class MelhorPrecoSombraTest(unittest.TestCase):
    @staticmethod
    def candidato(
        mercado="gol_ft", linha=2.5, odd=1.80,
        fonte="betsapi", bookmaker="bet365",
    ):
        return {
            "mercado": mercado,
            "linha": linha,
            "odd": odd,
            "status": "aprovado",
            "bloqueios": ["bloqueio_preexistente"],
            "features": {
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v2",
                    "mercado": mercado,
                    "fonte": fonte,
                    "bookmaker": bookmaker,
                    "coletado_em": "2026-09-01T12:00:20+00:00",
                    "idade_segundos": 10,
                    "cache": False,
                    "tipo": "binaria",
                    "linha": linha,
                    "over": odd,
                    "under": 2.0,
                    "odd_selecionada": odd,
                }
            },
        }

    @staticmethod
    def mercado(
        linha=2.5, over=1.90, fonte="the_odds_api",
        bookmaker="pinnacle", coletado_em="2026-09-01T12:00:25+00:00",
        idade=5, categoria="gols", tipo="total", ofertas=None,
        placar="0-0", mandante="time casa", visitante="time fora",
    ):
        if ofertas is None:
            ofertas = [{
                "linha": linha,
                "over": over,
                "under": 1.95,
                "fonte": fonte,
                "bookmaker": bookmaker,
                "coletado_em": coletado_em,
                "idade_segundos": idade,
                "cache": False,
                "identidade_evento": {
                    "schema": "identidade-evento-odd-v1",
                    "confirmada": True,
                    "fonte": fonte,
                    "evento_externo_id": f"evento-{fonte}",
                    "mandante_normalizado": mandante,
                    "visitante_normalizado": visitante,
                    "placar_normalizado": placar,
                },
            }]
        return {
            "categoria": categoria,
            "escopo": "total",
            "tipo_mercado": tipo,
            "formato": "duas_opcoes",
            "fonte": fonte,
            "bookmaker": bookmaker,
            "coletado_em": coletado_em,
            "idade_segundos": idade,
            "cache": False,
            "ofertas": ofertas,
        }

    def test_detecta_preco_independente_melhor_sem_mudar_candidato(self):
        candidato = self.candidato()
        antes = copy.deepcopy(candidato)
        odds = {"ao_vivo": [self.mercado()]}

        anexar_melhor_preco_sombra([candidato], odds, instante=AGORA)

        sombra = candidato["features"]["melhor_preco_sombra"]
        self.assertEqual(VERSAO, sombra["versao"])
        self.assertEqual("comparacao_independente_exata", sombra["estado"])
        self.assertEqual("alternativa_melhor", sombra["relacao"])
        self.assertAlmostEqual(0.10, sombra["diferenca_odd"])
        self.assertEqual("pinnacle", sombra[
            "melhor_alternativa_independente"
        ]["bookmaker"])
        self.assertFalse(sombra["aplicacao_sinais"])
        self.assertFalse(sombra["telegram"])
        self.assertEqual(antes["odd"], candidato["odd"])
        self.assertEqual(antes["status"], candidato["status"])
        self.assertEqual(antes["bloqueios"], candidato["bloqueios"])

    def test_usa_referencia_separada_sem_mesclar_na_odd_operacional(self):
        candidato = self.candidato()
        antes = copy.deepcopy(candidato)
        odds_operacionais = {"ao_vivo": [self.mercado(
            over=1.80, fonte="betsapi", bookmaker="bet365"
        )]}
        odds_referencia = {"ao_vivo": [self.mercado(over=1.94)]}
        operacionais_antes = copy.deepcopy(odds_operacionais)
        referencia_antes = copy.deepcopy(odds_referencia)

        anexar_melhor_preco_sombra(
            [candidato],
            odds_operacionais,
            instante=AGORA,
            odds_referencia_sombra=odds_referencia,
        )

        sombra = candidato["features"]["melhor_preco_sombra"]
        self.assertEqual("comparacao_independente_exata", sombra["estado"])
        self.assertTrue(sombra["referencia_sombra_recebida"])
        self.assertTrue(sombra["referencia_sombra_consultada"])
        self.assertEqual(1, sombra["ofertas_exatas_validas_operacionais"])
        self.assertEqual(
            1, sombra["ofertas_exatas_validas_referencia_sombra"]
        )
        self.assertEqual(
            "referencia_sombra",
            sombra["melhor_alternativa_independente"]["camada"],
        )
        self.assertEqual(1.94, sombra[
            "melhor_alternativa_independente"
        ]["odd"])
        self.assertFalse(sombra["aplicacao_sinais"])
        self.assertFalse(sombra["telegram"])
        self.assertEqual(antes["odd"], candidato["odd"])
        self.assertEqual(antes["status"], candidato["status"])
        self.assertEqual(operacionais_antes, odds_operacionais)
        self.assertEqual(referencia_antes, odds_referencia)

    def test_linha_diferente_nao_e_comparada(self):
        resultado = avaliar_melhor_preco_sombra(
            self.candidato(),
            {"ao_vivo": [self.mercado(linha=3.5)]},
            instante=AGORA,
        )

        self.assertEqual(
            "sem_referencia_independente_exata", resultado["estado"]
        )
        self.assertEqual(0, resultado["ofertas_exatas_validas"])

    def test_mesma_bookmaker_nao_e_independente_mesmo_com_grafia(self):
        resultado = avaliar_melhor_preco_sombra(
            self.candidato(bookmaker="Bet 365"),
            {"ao_vivo": [self.mercado(bookmaker="bet365")]},
            instante=AGORA,
        )

        self.assertEqual(
            "sem_referencia_independente_exata", resultado["estado"]
        )
        self.assertEqual(1, resultado["ofertas_exatas_validas"])
        self.assertEqual(0, resultado["alternativas_independentes_validas"])

    def test_mesma_fonte_nao_e_independente(self):
        resultado = avaliar_melhor_preco_sombra(
            self.candidato(),
            {"ao_vivo": [self.mercado(
                fonte="Bets API", bookmaker="pinnacle"
            )]},
            instante=AGORA,
        )

        self.assertEqual(
            "sem_referencia_independente_exata", resultado["estado"]
        )

    def test_oferta_antiga_e_descartada(self):
        resultado = avaliar_melhor_preco_sombra(
            self.candidato(),
            {"ao_vivo": [self.mercado(
                coletado_em="2026-09-01T11:50:00+00:00", idade=600
            )]},
            instante=AGORA,
        )

        self.assertEqual(
            "sem_referencia_independente_exata", resultado["estado"]
        )
        self.assertEqual(0, resultado["ofertas_exatas_validas"])

    def test_bookmaker_ausente_e_descartada(self):
        resultado = avaliar_melhor_preco_sombra(
            self.candidato(),
            {"ao_vivo": [self.mercado(bookmaker=None)]},
            instante=AGORA,
        )

        self.assertEqual(
            "sem_referencia_independente_exata", resultado["estado"]
        )
        self.assertEqual(0, resultado["ofertas_exatas_validas"])

    def test_ht_usa_exclusivamente_ofertas_ht(self):
        candidato = self.candidato("gol_ht", 0.5, 1.75)
        mercado = self.mercado(linha=0.5, over=2.50)
        mercado["ofertas_ht"] = [{
            "linha": 0.5,
            "over": 1.86,
            "under": 1.94,
            "fonte": "the_odds_api",
            "bookmaker": "pinnacle",
            "coletado_em": "2026-09-01T12:00:25+00:00",
            "idade_segundos": 5,
            "cache": False,
        }]

        resultado = avaliar_melhor_preco_sombra(
            candidato, {"ao_vivo": [mercado]}, instante=AGORA
        )

        self.assertEqual("comparacao_independente_exata", resultado["estado"])
        self.assertEqual(1.86, resultado[
            "melhor_alternativa_independente"
        ]["odd"])

    def test_proximo_gol_exige_as_tres_vias_completas(self):
        candidato = self.candidato("proximo_gol", "casa", 1.80)
        candidato["features"]["cotacao_entrada_clv"].update({
            "tipo": "tres_vias",
            "selecao": "casa",
            "odds": {"casa": 1.8, "visitante": 2.5, "sem_gol": 4.0},
        })
        incompleto = {
            "categoria": "gols", "escopo": "proximo",
            "tipo_mercado": "proximo",
            "selecoes": {"casa": 1.95, "visitante": 2.4},
            "fonte": "the_odds_api", "bookmaker": "pinnacle",
            "coletado_em": "2026-09-01T12:00:25+00:00",
            "idade_segundos": 5, "cache": False,
        }
        completo = copy.deepcopy(incompleto)
        completo["selecoes"]["sem_gol"] = 4.1

        sem_par = avaliar_melhor_preco_sombra(
            candidato, {"ao_vivo": [incompleto]}, instante=AGORA
        )
        com_par = avaliar_melhor_preco_sombra(
            candidato, {"ao_vivo": [completo]}, instante=AGORA
        )

        self.assertEqual(0, sem_par["ofertas_exatas_validas"])
        self.assertEqual("comparacao_independente_exata", com_par["estado"])
        self.assertEqual(1.95, com_par[
            "melhor_alternativa_independente"
        ]["odd"])

    def test_retem_versao_mais_fresca_da_mesma_origem(self):
        antiga = self.mercado(
            over=2.05,
            coletado_em="2026-09-01T11:59:50+00:00",
            idade=40,
        )
        nova = self.mercado(
            over=1.88,
            coletado_em="2026-09-01T12:00:25+00:00",
            idade=5,
        )

        resultado = avaliar_melhor_preco_sombra(
            self.candidato(), {"ao_vivo": [antiga, nova]}, instante=AGORA
        )

        self.assertEqual(1, resultado["alternativas_independentes_validas"])
        self.assertEqual(1.88, resultado[
            "melhor_alternativa_independente"
        ]["odd"])

    def test_calcula_edge_sem_vig_sem_alterar_o_candidato(self):
        candidato = self.candidato(odd=2.10)
        antes = copy.deepcopy(candidato)
        operacional = self.mercado(
            over=2.10, fonte="betsapi", bookmaker="bet365",
            coletado_em="2026-09-01T12:00:20+00:00", idade=10,
        )
        operacional["ofertas"][0]["under"] = 2.0
        referencia = self.mercado(over=2.0)
        referencia["ofertas"][0]["under"] = 2.0

        resultado = avaliar_melhor_preco_sombra(
            candidato,
            {"ao_vivo": [operacional, referencia]},
            instante=AGORA,
        )

        valor = resultado["valor_justo_sombra"]
        self.assertEqual("desajuste_favoravel_candidato", valor["estado"])
        self.assertAlmostEqual(0.5, valor["probabilidade_referencia_sem_vig"])
        self.assertAlmostEqual(0.05, valor["valor_esperado_referencia"])
        self.assertTrue(valor["desajuste_favoravel"])
        self.assertTrue(validar_politica_avaliacao_resultado(
            valor["avaliacao_resultado_sombra"]
        ))
        self.assertTrue(validar_avaliacao_veto(
            valor["avaliacao_veto_preco_sombra"],
            valor["valor_esperado_referencia"],
        ))
        self.assertEqual(
            "controle_nao_veto",
            valor["avaliacao_veto_preco_sombra"]["classificacao"],
        )
        self.assertFalse(valor["aplicacao_sinais"])
        self.assertEqual(antes, candidato)

    def test_odd_maior_na_referencia_nao_significa_edge_executavel(self):
        candidato = self.candidato(linha=5.5, odd=2.20)
        operacional = self.mercado(
            linha=5.5, over=2.20, fonte="betsapi", bookmaker="bet365",
            coletado_em="2026-09-01T12:00:20+00:00", idade=10,
        )
        operacional["ofertas"][0]["under"] = 1.6154
        referencia = self.mercado(linha=5.5, over=4.57)
        referencia["ofertas"][0]["under"] = 1.19

        resultado = avaliar_melhor_preco_sombra(
            candidato,
            {"ao_vivo": [operacional, referencia]},
            instante=AGORA,
        )

        self.assertEqual("alternativa_melhor", resultado["relacao"])
        valor = resultado["valor_justo_sombra"]
        self.assertEqual("sem_desajuste_favoravel", valor["estado"])
        self.assertLess(valor["valor_esperado_referencia"], -0.50)
        self.assertFalse(valor["desajuste_favoravel"])
        self.assertEqual(
            "veto_preco_negativo",
            valor["avaliacao_veto_preco_sombra"]["classificacao"],
        )

    def test_par_com_margem_implausivel_nao_vira_preco_justo(self):
        operacional = self.mercado(
            over=1.80, fonte="betsapi", bookmaker="bet365",
            coletado_em="2026-09-01T12:00:20+00:00", idade=10,
        )
        referencia = self.mercado(over=10.0)
        referencia["ofertas"][0]["under"] = 10.0

        resultado = avaliar_melhor_preco_sombra(
            self.candidato(),
            {"ao_vivo": [operacional, referencia]},
            instante=AGORA,
        )

        self.assertEqual(
            "comparacao_independente_exata", resultado["estado"]
        )
        self.assertEqual(
            "sem_referencia_sem_vig_sincronizada",
            resultado["valor_justo_sombra"]["estado"],
        )

    def test_referencia_de_valor_e_escolhida_por_frescor_nao_pela_odd(self):
        operacional = self.mercado(
            over=1.80, fonte="betsapi", bookmaker="bet365",
            coletado_em="2026-09-01T12:00:20+00:00", idade=10,
        )
        antiga = self.mercado(
            over=2.40,
            fonte="the_odds_api",
            bookmaker="pinnacle",
            coletado_em="2026-09-01T12:00:10+00:00",
            idade=20,
        )
        antiga["ofertas"][0]["under"] = 1.70
        nova = self.mercado(
            over=1.90,
            fonte="the_odds_api",
            bookmaker="coolbet",
            coletado_em="2026-09-01T12:00:25+00:00",
            idade=5,
        )
        nova["ofertas"][0]["under"] = 2.0

        resultado = avaliar_melhor_preco_sombra(
            self.candidato(),
            {"ao_vivo": [operacional, antiga, nova]},
            instante=AGORA,
        )

        self.assertEqual(
            "pinnacle", resultado["melhor_alternativa_independente"][
                "bookmaker"
            ]
        )
        self.assertEqual(
            "coolbet", resultado["valor_justo_sombra"]["referencia"][
                "bookmaker"
            ]
        )

    def test_placar_divergente_impede_preco_justo_mas_preserva_preco(self):
        operacional = self.mercado(
            over=1.80, fonte="betsapi", bookmaker="bet365",
            coletado_em="2026-09-01T12:00:20+00:00", idade=10,
            placar="0-0",
        )
        referencia = self.mercado(over=1.90, placar="1-0")

        resultado = avaliar_melhor_preco_sombra(
            self.candidato(),
            {"ao_vivo": [operacional, referencia]},
            instante=AGORA,
        )

        self.assertEqual("comparacao_independente_exata", resultado["estado"])
        self.assertEqual(
            "sem_referencia_sem_vig_sincronizada",
            resultado["valor_justo_sombra"]["estado"],
        )

    def test_intervalo_acima_de_60_segundos_impede_preco_justo(self):
        candidato = self.candidato()
        candidato["features"]["cotacao_entrada_clv"].update({
            "coletado_em": "2026-09-01T11:59:00+00:00",
            "idade_segundos": 90,
        })
        operacional = self.mercado(
            over=1.80, fonte="betsapi", bookmaker="bet365",
            coletado_em="2026-09-01T11:59:00+00:00", idade=90,
        )
        referencia = self.mercado(over=1.90)

        resultado = avaliar_melhor_preco_sombra(
            candidato,
            {"ao_vivo": [operacional, referencia]},
            instante=AGORA,
            idade_maxima_segundos=120,
        )

        self.assertEqual("comparacao_independente_exata", resultado["estado"])
        self.assertEqual(
            "sem_referencia_sem_vig_sincronizada",
            resultado["valor_justo_sombra"]["estado"],
        )

    def test_preco_operacional_divergente_da_cotacao_congelada_impede_valor(self):
        operacional = self.mercado(
            over=1.85, fonte="betsapi", bookmaker="bet365",
            coletado_em="2026-09-01T12:00:20+00:00", idade=10,
        )
        referencia = self.mercado(over=1.90)

        resultado = avaliar_melhor_preco_sombra(
            self.candidato(odd=1.80),
            {"ao_vivo": [operacional, referencia]},
            instante=AGORA,
        )

        self.assertEqual("comparacao_independente_exata", resultado["estado"])
        self.assertEqual(
            "sem_referencia_sem_vig_sincronizada",
            resultado["valor_justo_sombra"]["estado"],
        )

    def test_proveniencia_escolhida_incompleta_falha_fechada(self):
        candidato = self.candidato(bookmaker=None)
        antes = copy.deepcopy(candidato)

        anexar_melhor_preco_sombra(
            [candidato], {"ao_vivo": [self.mercado()]}, instante=AGORA
        )

        sombra = candidato["features"]["melhor_preco_sombra"]
        self.assertEqual("proveniencia_escolhida_incompleta", sombra["estado"])
        self.assertEqual(antes["odd"], candidato["odd"])
        self.assertEqual(antes["status"], candidato["status"])
        self.assertEqual(antes["bloqueios"], candidato["bloqueios"])


if __name__ == "__main__":
    unittest.main()
