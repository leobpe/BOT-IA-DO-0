import json
import sqlite3
import unittest

from valor_mercado import (
    anexar_par_odds_sincronizado,
    anexar_valor_mercado,
    auditar_valor_mercado_sinais,
    avaliar_valor_mercado,
    odd_oposta_sincronizada,
    referencia_tres_vias_sincronizada,
    validar_rastro_valor_mercado,
)


class ValorMercadoTest(unittest.TestCase):
    @staticmethod
    def origem(identificador="grupo-a", linha=0.5):
        return {
            "schema": "origem-mercado-odd-v1", "fonte": "betsapi",
            "identificador": identificador, "nome": "Match Goals",
            "linha": linha, "lados": ["over", "under"],
            "bookmaker": "bet365",
        }

    def test_calcula_preco_justo_e_ev_conservador(self):
        resultado = avaliar_valor_mercado(0.80, 1.85, 2.05)

        self.assertTrue(resultado["aprovado"])
        self.assertAlmostEqual(1.25, resultado["odd_justa_conservadora"])
        self.assertAlmostEqual(0.48, resultado["valor_esperado_conservador"])
        self.assertAlmostEqual(
            0.80 - 1 / 1.85,
            resultado["vantagem_probabilidade"],
            places=6,
        )

    def test_nao_chama_ev_de_vantagem_sem_referencia_sem_vig(self):
        resultado = avaliar_valor_mercado(0.80, 1.85)

        self.assertFalse(resultado["aprovado"])
        self.assertEqual("referencia_sem_vig_ausente", resultado["motivo"])
        self.assertGreater(resultado["valor_esperado_conservador"], 0)

    def test_reprova_odd_sem_margem_conservadora(self):
        resultado = avaliar_valor_mercado(0.50, 1.85)

        self.assertFalse(resultado["aprovado"])
        self.assertEqual("sem_margem", resultado["estado"])
        self.assertAlmostEqual(-0.075, resultado["valor_esperado_conservador"])

    def test_remove_vig_quando_lado_oposto_esta_disponivel(self):
        resultado = avaliar_valor_mercado(0.60, 1.90, 1.90)

        self.assertTrue(resultado["referencia_sem_vig_disponivel"])
        self.assertAlmostEqual(0.50, resultado["probabilidade_mercado_sem_vig"])
        self.assertAlmostEqual(
            2 / 1.9 - 1, resultado["margem_bookmaker"], places=6
        )
        self.assertAlmostEqual(
            0.10, resultado["vantagem_probabilidade_sem_vig"]
        )
        self.assertTrue(resultado["margem_bookmaker_plausivel"])

    def test_preserva_pequeno_underround_como_desajuste_possivel(self):
        resultado = avaliar_valor_mercado(0.60, 2.03, 2.03)

        self.assertTrue(resultado["aprovado"])
        self.assertTrue(resultado["margem_bookmaker_plausivel"])
        self.assertLess(resultado["margem_bookmaker"], 0)

    def test_rejeita_underround_extremo_como_referencia_incoerente(self):
        resultado = avaliar_valor_mercado(0.60, 2.20, 2.20)

        self.assertFalse(resultado["aprovado"])
        self.assertFalse(resultado["margem_bookmaker_plausivel"])
        self.assertEqual("margem_bookmaker_incoerente", resultado["motivo"])

    def test_rejeita_overround_binario_extremo(self):
        resultado = avaliar_valor_mercado(0.50, 1.20, 1.20)

        self.assertFalse(resultado["aprovado"])
        self.assertFalse(resultado["margem_bookmaker_plausivel"])
        self.assertEqual("margem_bookmaker_incoerente", resultado["motivo"])

    def test_rejeita_overround_extremo_em_tres_vias(self):
        resultado = avaliar_valor_mercado(
            0.70,
            2.0,
            odds_mercado={"casa": 2.0, "visitante": 2.0, "sem_gol": 2.0},
            selecao_mercado="casa",
        )

        self.assertFalse(resultado["aprovado"])
        self.assertFalse(resultado["margem_bookmaker_plausivel"])
        self.assertEqual("margem_bookmaker_incoerente", resultado["motivo"])

    def test_ignora_odd_oposta_persistida_sem_prova_de_sincronia(self):
        self.assertIsNone(odd_oposta_sincronizada({
            "odd_oposta": 1.90,
        }))
        self.assertIsNone(odd_oposta_sincronizada({
            "features": {"odd_oposta": 1.90},
        }))
        self.assertEqual(1.90, odd_oposta_sincronizada({
            "features": {
                "odd_oposta": 1.90,
                "odd_par_sincronizado": True,
            },
        }))

    def test_anexa_par_exato_do_mesmo_snapshot_sem_alterar_decisao(self):
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.85,
            "pontuacao_tecnica": 84.0,
            "status": "aprovado",
            "features": {"minuto": 60},
        }
        odds = {"ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "ofertas": [
                {"linha": 1.5, "over": 1.85, "under": 1.95},
                {"linha": 0.5, "over": 1.85, "under": 2.05},
            ],
        }]}

        self.assertTrue(anexar_par_odds_sincronizado(candidato, odds))
        self.assertEqual(2.05, candidato["odd_oposta"])
        self.assertEqual(2.05, candidato["features"]["odd_oposta"])
        self.assertTrue(candidato["features"]["odd_par_sincronizado"])
        self.assertEqual(84.0, candidato["pontuacao_tecnica"])
        self.assertEqual("aprovado", candidato["status"])

    def test_par_sem_vig_usa_primeiro_a_cotacao_congelada(self):
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.85,
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v1",
                    "mercado": "gol_ft",
                    "tipo": "binaria",
                    "linha": 0.5,
                    "over": 1.85,
                    "under": 2.05,
                    "odd_selecionada": 1.85,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "coletado_em": "2026-09-09T10:00:00-04:00",
                    "idade_segundos": 2,
                    "cache": False,
                },
            },
        }
        odds_contraditorias = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "ofertas": [{"linha": 0.5, "over": 1.85, "under": 9.0}],
        }]}

        self.assertTrue(
            anexar_par_odds_sincronizado(candidato, odds_contraditorias)
        )
        self.assertEqual(2.05, candidato["odd_oposta"])
        self.assertEqual(
            "betsapi", candidato["features"]["fonte_referencia_sem_vig"]
        )

    def test_cotacao_congelada_invalida_nao_cai_em_fallback(self):
        candidato = {
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.85,
            "fonte_odds": "betsapi", "bookmaker_odds": "bet365",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v1",
                    "mercado": "gol_ft", "tipo": "binaria",
                    "linha": 0.5, "over": 1.85, "under": 2.05,
                    "odd_selecionada": 1.85,
                    "fonte": "outra_fonte", "bookmaker": "bet365",
                    "idade_segundos": 2, "cache": False,
                },
            },
        }
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "ofertas": [{"linha": 0.5, "over": 1.85, "under": 2.05}],
        }]}

        self.assertFalse(anexar_par_odds_sincronizado(candidato, odds))
        self.assertNotIn("odd_oposta", candidato)

    def test_cotacao_v2_exige_mesma_origem_do_grupo_validado(self):
        origem = self.origem()
        candidato = {
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.85,
            "fonte_odds": "betsapi", "bookmaker_odds": "bet365",
            "features": {
                "fonte_odds": "betsapi", "bookmaker_odds": "bet365",
                "cotacao_entrada_clv_estado": "congelada_v1",
                "acompanhamento_odd_rapido": {
                    "origem_mercado_odd": origem,
                },
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v2",
                    "mercado": "gol_ft", "tipo": "binaria",
                    "linha": 0.5, "over": 1.85, "under": 2.05,
                    "odd_selecionada": 1.85,
                    "fonte": "betsapi", "bookmaker": "bet365",
                    "idade_segundos": 2, "cache": False,
                    "origem_mercado": dict(origem),
                },
            },
        }

        self.assertTrue(anexar_par_odds_sincronizado(candidato, {}))
        candidato["features"]["cotacao_entrada_clv"]["origem_mercado"][
            "identificador"
        ] = "grupo-adulterado"
        self.assertFalse(anexar_par_odds_sincronizado(candidato, {}))

    def test_cotacao_futura_nao_congelada_nao_usa_fallback_legado(self):
        candidato = {
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.85,
            "features": {
                "cotacao_entrada_clv_estado": "oferta_ambigua",
            },
        }
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "ofertas": [{"linha": 0.5, "over": 1.85, "under": 2.05}],
        }]}

        self.assertFalse(anexar_par_odds_sincronizado(candidato, odds))
        self.assertNotIn("odd_oposta", candidato)

    def test_anexa_trio_exato_do_proximo_gol_e_remove_vig(self):
        candidato = {
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 1.70,
            "pontuacao_tecnica": 82.0,
            "status": "aprovado",
            "features": {"minuto": 54},
        }
        odds = {"ao_vivo": [{
            "mercado": "Próximo Gol",
            "selecoes": {
                "casa": 1.70,
                "visitante": 3.20,
                "sem_gol": 5.00,
            },
            "fonte": "betsapi",
            "bookmaker": "bet365",
        }]}

        self.assertTrue(anexar_par_odds_sincronizado(candidato, odds))
        referencia = referencia_tres_vias_sincronizada(candidato)
        self.assertEqual("casa", referencia["selecao"])
        self.assertEqual(3.20, referencia["odds"]["visitante"])
        self.assertEqual(82.0, candidato["pontuacao_tecnica"])
        self.assertEqual("aprovado", candidato["status"])

        resultado = avaliar_valor_mercado(
            0.65,
            1.70,
            odds_mercado=referencia["odds"],
            selecao_mercado=referencia["selecao"],
        )
        soma = 1 / 1.70 + 1 / 3.20 + 1 / 5.00
        self.assertEqual("tres_vias", resultado["tipo_referencia_sem_vig"])
        self.assertAlmostEqual(
            (1 / 1.70) / soma,
            resultado["probabilidade_mercado_sem_vig"],
            places=6,
        )

    def test_rejeita_trio_ambiguo_e_prefere_fonte_declarada(self):
        odds = {"ao_vivo": [
            {
                "selecoes": {
                    "casa": 1.70, "visitante": 3.20, "sem_gol": 5.00,
                },
                "fonte": "betsapi",
                "bookmaker": "bet365",
            },
            {
                "selecoes": {
                    "casa": 1.70, "visitante": 3.40, "sem_gol": 4.50,
                },
                "fonte": "api_football",
                "bookmaker": "bet365",
            },
        ]}
        ambiguo = {
            "mercado": "proximo_gol", "linha": "casa", "odd": 1.70,
            "features": {},
        }
        self.assertFalse(anexar_par_odds_sincronizado(ambiguo, odds))
        self.assertIsNone(referencia_tres_vias_sincronizada(ambiguo))

        com_fonte = {
            **ambiguo,
            "fonte_odds": "betsapi",
            "features": {},
        }
        self.assertTrue(anexar_par_odds_sincronizado(com_fonte, odds))
        self.assertEqual(
            3.20,
            referencia_tres_vias_sincronizada(com_fonte)["odds"][
                "visitante"
            ],
        )

    def test_rastro_tres_vias_detecta_alteracao_do_preco_adversario(self):
        candidato = {
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 1.70,
            "probabilidade_calibrada": 0.65,
            "features": {
                "selecao_mercado": "casa",
                "odds_mercado_sincronizadas": {
                    "casa": 1.70,
                    "visitante": 3.20,
                    "sem_gol": 5.00,
                },
                "mercado_odds_sincronizado": True,
            },
        }
        anexar_valor_mercado(candidato)
        self.assertTrue(validar_rastro_valor_mercado(
            0.65, 1.70, candidato["features"]
        )["valido"])

        candidato["features"]["odds_mercado_sincronizadas"][
            "visitante"
        ] = 4.00
        divergente = validar_rastro_valor_mercado(
            0.65, 1.70, candidato["features"]
        )
        self.assertFalse(divergente["valido"])
        self.assertEqual(
            "rastro_valor_mercado_divergente", divergente["motivo"]
        )

    def test_rastro_rejeita_adulteracao_coordenada_do_par_congelado(self):
        candidato = {
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.85,
            "probabilidade_calibrada": 0.80,
            "fonte_odds": "betsapi", "bookmaker_odds": "bet365",
            "odd_oposta": 2.05, "odd_par_sincronizado": True,
            "features": {
                "fonte_odds": "betsapi", "bookmaker_odds": "bet365",
                "odd_oposta": 2.05, "odd_par_sincronizado": True,
                "cotacao_entrada_clv_estado": "congelada_v1",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v1",
                    "mercado": "gol_ft", "tipo": "binaria",
                    "linha": 0.5, "over": 1.85, "under": 2.05,
                    "odd_selecionada": 1.85,
                    "fonte": "betsapi", "bookmaker": "bet365",
                    "coletado_em": "2026-09-09T10:00:00-04:00",
                    "idade_segundos": 2, "cache": False,
                },
            },
        }
        anexar_valor_mercado(candidato)
        candidato["odd_oposta"] = 9.0
        candidato["features"]["odd_oposta"] = 9.0
        anexar_valor_mercado(candidato)

        resultado = validar_rastro_valor_mercado(
            0.80, 1.85, candidato["features"]
        )

        self.assertFalse(resultado["valido"])
        self.assertEqual(
            "referencia_sem_vig_diverge_cotacao_entrada",
            resultado["motivo"],
        )

    def test_rastro_exige_uso_da_cotacao_congelada_disponivel(self):
        features = {
            "fonte_odds": "betsapi", "bookmaker_odds": "bet365",
            "cotacao_entrada_clv_estado": "congelada_v1",
            "cotacao_entrada_clv": {
                "schema": "cotacao-entrada-clv-v1",
                "mercado": "gol_ft", "tipo": "binaria",
                "linha": 0.5, "over": 1.85, "under": 2.05,
                "odd_selecionada": 1.85,
                "fonte": "betsapi", "bookmaker": "bet365",
                "coletado_em": "2026-09-09T10:00:00-04:00",
                "idade_segundos": 2, "cache": False,
            },
        }
        features["valor_mercado_conservador"] = avaliar_valor_mercado(
            0.80, 1.85
        )

        resultado = validar_rastro_valor_mercado(0.80, 1.85, features)

        self.assertFalse(resultado["valido"])
        self.assertEqual(
            "referencia_sem_vig_diverge_cotacao_entrada",
            resultado["motivo"],
        )

    def test_anexa_rastro_sem_apagar_features(self):
        candidato = {
            "odd": 1.50,
            "probabilidade_calibrada": 0.75,
            "odd_oposta": 3.0,
            "odd_par_sincronizado": True,
            "features": {"minuto": 60},
        }

        avaliacao = anexar_valor_mercado(candidato)

        self.assertTrue(avaliacao["aprovado"])
        self.assertEqual(60, candidato["features"]["minuto"])
        self.assertEqual(
            avaliacao,
            candidato["features"]["valor_mercado_conservador"],
        )
        self.assertAlmostEqual(0.125, candidato["valor_esperado_conservador"])

    def test_valida_rastro_persistido_e_detecta_adulteracao(self):
        candidato = {
            "odd": 1.85,
            "odd_oposta": 2.05,
            "odd_par_sincronizado": True,
            "probabilidade_calibrada": 0.80,
            "features": {},
        }
        anexar_valor_mercado(candidato)

        valido = validar_rastro_valor_mercado(
            0.80, 1.85, candidato["features"]
        )
        self.assertTrue(valido["valido"])
        candidato["features"]["valor_mercado_conservador"][
            "valor_esperado_conservador"
        ] = 9.0
        divergente = validar_rastro_valor_mercado(
            0.80, 1.85, candidato["features"]
        )
        self.assertFalse(divergente["valido"])
        self.assertEqual(
            "rastro_valor_mercado_divergente", divergente["motivo"]
        )

    def test_dados_invalidos_falham_fechado(self):
        for probabilidade, odd in ((None, 1.8), (0, 1.8), (0.8, 1.0)):
            with self.subTest(probabilidade=probabilidade, odd=odd):
                self.assertFalse(
                    avaliar_valor_mercado(probabilidade, odd)["aprovado"]
                )

    def test_auditoria_detecta_entrega_oficial_sem_valor(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, mercado TEXT, regra_versao TEXT,
                status TEXT, odd REAL, probabilidade_calibrada REAL,
                features_json TEXT
            );
            CREATE TABLE entregas_alertas (
                sinal_id INTEGER, canal TEXT, status TEXT
            );
            INSERT INTO sinais VALUES
                (1, 'gol_ft', 'r1', 'aprovado', 1.85, 0.80,
                 '{"odd_oposta": 2.05}'),
                (2, 'gol_ht', 'r2', 'aprovado', 1.85, 0.50, '{}'),
                (3, 'proximo_gol', 'r3', 'simulacao', 1.85, 0.50, '{}');
            INSERT INTO entregas_alertas VALUES
                (1, '-100-oficial', 'entregue'),
                (2, '-100-oficial', 'entregue'),
                (3, '-100:teste', 'entregue');
            """
        )
        rastro_valido = avaliar_valor_mercado(0.80, 1.85, 2.05)
        conexao.execute(
            "UPDATE sinais SET features_json=? WHERE id=1",
            (json.dumps({
                "odd_oposta": 2.05,
                "odd_par_sincronizado": True,
                "valor_mercado_conservador": rastro_valido,
            }),),
        )

        resultado = auditar_valor_mercado_sinais(conexao)

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(3, resultado["sinais_calibrados"])
        self.assertEqual(2, resultado["sem_valor_conservador"])
        self.assertEqual(1, resultado["entregues_oficiais_sem_valor"])
        self.assertEqual(1, resultado["com_referencia_sem_vig"])
        self.assertEqual(2, resultado["sem_referencia_sem_vig"])
        self.assertEqual(1, resultado["rastros_validos"])
        self.assertEqual(2, resultado["rastros_ausentes"])
        self.assertEqual(0, resultado["rastros_divergentes"])
        self.assertEqual(0, resultado["referencias_margem_incoerente"])
        self.assertEqual(
            1, resultado["entregues_oficiais_rastro_invalido"]
        )
        conexao.close()

    def test_auditoria_expoe_margem_incoerente_corretamente_bloqueada(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, mercado TEXT, regra_versao TEXT,
                status TEXT, odd REAL, probabilidade_calibrada REAL,
                features_json TEXT
            );
            CREATE TABLE entregas_alertas (
                sinal_id INTEGER, canal TEXT, status TEXT
            );
            """
        )
        rastro = avaliar_valor_mercado(0.95, 1.20, 1.20)
        conexao.execute(
            "INSERT INTO sinais VALUES (?,?,?,?,?,?,?)",
            (
                1, "gol_ft", "r1", "rejeitado", 1.20, 0.95,
                json.dumps({
                    "odd_oposta": 1.20,
                    "odd_par_sincronizado": True,
                    "valor_mercado_conservador": rastro,
                }),
            ),
        )

        resultado = auditar_valor_mercado_sinais(conexao)

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(1, resultado["referencias_margem_incoerente"])
        self.assertEqual(
            "margem_bookmaker_incoerente",
            resultado["detalhes_sem_valor"][0]["motivo"],
        )
        self.assertEqual(
            1,
            resultado["por_mercado"]["gol_ft"][
                "referencias_margem_incoerente"
            ],
        )
        conexao.close()


if __name__ == "__main__":
    unittest.main()
