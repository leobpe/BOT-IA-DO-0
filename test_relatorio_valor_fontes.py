import json
import sqlite3
import unittest
from datetime import datetime

from melhor_preco_sombra import VERSAO as VERSAO_MELHOR_PRECO_SOMBRA
from melhor_preco_sombra import VERSAO_VALOR_JUSTO
from relatorio_valor_fontes import resumir_valor_fontes
from validacao_resultado_valor_justo import (
    mercados_com_candidato_sincronizado,
    politica_avaliacao_resultado,
    politica_transferencia_resultado,
)


class RelatorioValorFontesTest(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        self.c.row_factory = sqlite3.Row
        self.c.executescript("""
            CREATE TABLE partidas (
                id INTEGER, packball_url TEXT
            );
            CREATE TABLE sinais (
                id INTEGER, partida_id INTEGER, criado_em TEXT,
                status TEXT, odd REAL, features_json TEXT,
                mercado TEXT DEFAULT 'gol_ft',
                linha TEXT,
                regra_versao TEXT DEFAULT 'regra-v1',
                snapshot_id INTEGER
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, resultado TEXT, retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas (
                sinal_id INTEGER, canal TEXT, status TEXT
            );
            CREATE TABLE odds_thestatsapi_live (
                packball_url TEXT, coletado_em TEXT
            );
            CREATE TABLE observacoes_fontes_odds (
                partida_id INTEGER, fonte TEXT, consultado_em TEXT,
                estado TEXT
            );
            CREATE TABLE comparacoes_odds_fontes (
                id INTEGER, snapshot_id INTEGER, observado_em TEXT,
                categoria TEXT, periodo TEXT, linha REAL, selecao TEXT,
                fonte_a TEXT, bookmaker_a TEXT, odd_a REAL,
                fonte_b TEXT, bookmaker_b TEXT, odd_b REAL,
                intervalo_fontes_segundos REAL,
                compatibilidade_bookmaker TEXT, estado TEXT
            );
        """)

    def tearDown(self):
        self.c.close()

    def _sinal(self, identificador, fonte, status="aprovado"):
        self.c.execute(
            "INSERT INTO sinais "
            "(id, partida_id, criado_em, status, odd, features_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                identificador,
                identificador,
                "2026-08-24T12:00:00",
                status,
                1.80,
                json.dumps({"fonte_odds": fonte}),
            ),
        )

    def test_detecta_coorte_valor_justo_ja_formada_no_mesmo_jogo(self):
        self.c.execute(
            "INSERT INTO partidas VALUES (?, ?)",
            (91, "https://packball.com/match/91/live"),
        )
        features = {
            "melhor_preco_sombra": {
                "versao": VERSAO_MELHOR_PRECO_SOMBRA,
                "valor_justo_sombra": {
                    "versao": VERSAO_VALOR_JUSTO,
                    "estado": "sem_desajuste_favoravel",
                },
            },
        }
        self.c.execute(
            """
            INSERT INTO sinais (
                id, partida_id, criado_em, status, odd, features_json,
                mercado
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                91, 91, "2026-09-12T12:00:00", "simulacao", 1.80,
                json.dumps(features), "gol_ft",
            ),
        )

        encontrados = mercados_com_candidato_sincronizado(
            self.c,
            "https://packball.com/match/91/live",
            {"gol_ft", "gol_ht"},
        )

        self.assertEqual({"gol_ft"}, encontrados)

    def test_entrega_e_resultado_nao_duplicam_por_varios_registros(self):
        self._sinal(1, "packball")
        self.c.execute(
            "INSERT INTO resultados_sinais VALUES (1, 'green', 0.8)"
        )
        self.c.executemany(
            "INSERT INTO entregas_alertas VALUES (1, ?, 'entregue')",
            [("grupo:teste",), ("grupo:teste:resultado",)],
        )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        packball = resumo["fontes"]["packball"]

        self.assertEqual(packball["candidatos"], 1)
        self.assertEqual(packball["entregues"], 1)
        self.assertEqual(packball["resolvidos"], 1)
        self.assertEqual(packball["greens"], 1)
        self.assertEqual(packball["roi"], 0.8)
        self.assertEqual(packball["entregues_resolvidos"], 1)
        self.assertEqual(packball["entregues_roi"], 0.8)
        self.assertEqual(
            resumo["entregas_por_fonte_mercado"]["packball"]
            ["gol_ft"]["roi"],
            0.8,
        )

    def test_fonte_paga_coletada_sem_sinal_fica_explicita(self):
        self.c.execute(
            "INSERT INTO odds_thestatsapi_live VALUES (?, ?)",
            ("https://packball/match/1", "2026-08-24T12:00:00"),
        )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )

        self.assertEqual(
            resumo["diagnosticos_fontes_pagas"]["thestatsapi"]["estado"],
            "coleta_sem_candidato_atribuido",
        )
        self.assertFalse(
            resumo["diagnosticos_fontes_pagas"]["thestatsapi"]
            ["avaliacao_custo_beneficio_conclusiva"]
        )

    def test_the_odds_api_distingue_cobertura_de_partida_pareada(self):
        self.c.executemany(
            "INSERT INTO observacoes_fontes_odds VALUES (?, ?, ?, ?)",
            [
                (1, "the_odds_api", "2026-08-24T12:00:00",
                 "competicao_nao_coberta"),
                (2, "the_odds_api", "2026-08-24T12:01:00",
                 "consultado_sem_oferta"),
            ],
        )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        coleta = resumo["coleta_auxiliar"]["the_odds_api"]

        self.assertEqual(coleta["observacoes_persistidas"], 2)
        self.assertEqual(coleta["consultas_persistidas"], 1)
        self.assertEqual(coleta["partidas_pareadas"], 1)
        self.assertEqual(
            coleta["por_estado"]["competicao_nao_coberta"]["partidas"], 1
        )
        self.assertEqual(
            resumo["diagnosticos_fontes_pagas"]["the_odds_api"]["estado"],
            "coleta_sem_candidato_atribuido",
        )

    def test_alias_de_fonte_e_normalizado(self):
        self._sinal(2, "api-football", status="simulacao")
        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )

        self.assertEqual(resumo["fontes"]["api_football"]["candidatos"], 1)
        self.assertEqual(resumo["fontes"]["api_football"]["simulacoes"], 1)

    def test_betsapi_e_fonte_conhecida_e_audita_candidatos(self):
        self._sinal(7, "Bets API")

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )

        self.assertEqual(resumo["fontes"]["betsapi"]["candidatos"], 1)
        self.assertEqual(
            resumo["diagnosticos_fontes_pagas"]["betsapi"]["estado"],
            "fonte_utilizada_em_candidatos",
        )

    def test_dependencia_estatistica_thestats_nao_exige_odd_thestats(self):
        self.c.execute(
            "INSERT INTO sinais "
            "(id, partida_id, criado_em, status, odd, features_json, mercado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                3, 3, "2026-08-24T12:00:00", "aprovado", 1.80,
                json.dumps({
                    "fonte_odds": "packball",
                    "fusao_fontes": {
                        "valida": True,
                        "modo": "oficial_fail_closed",
                        "complementou": ["Chutes no gol"],
                        "xg": [1.1, 0.7],
                    },
                }),
                "gol_ft",
            ),
        )
        self.c.execute(
            "INSERT INTO entregas_alertas VALUES (3, 'grupo:teste', 'entregue')"
        )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        dados = resumo["beneficio_dados"]["thestatsapi"]

        self.assertEqual(dados["candidatos_dependentes_fusao"], 1)
        self.assertEqual(dados["dependentes_entregues"], 1)
        self.assertEqual(dados["xg_disponivel"], 1)
        self.assertEqual(
            resumo["diagnosticos_fontes_pagas"]["thestatsapi"]["estado"],
            "beneficio_via_estatisticas",
        )

    def test_mede_roi_apenas_dos_sinais_dependentes_da_lista_temporal(self):
        for identificador, dependente, resultado, retorno in (
            (4, True, "green", 0.8),
            (5, True, "red", -1.0),
            (6, False, "green", 0.7),
        ):
            self.c.execute(
                "INSERT INTO sinais "
                "(id, partida_id, criado_em, status, odd, features_json, "
                "mercado) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    identificador,
                    identificador,
                    "2026-08-24T12:00:00",
                    "aprovado" if identificador != 5 else "simulacao",
                    1.80,
                    json.dumps({
                        "fonte_odds": "packball",
                        "fallback_temporal_lista": {
                            "aplicado": True,
                            "dependente": dependente,
                            "campos_complementados": ["5.chutes"],
                        },
                    }),
                    "gol_ft",
                ),
            )
            self.c.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?)",
                (identificador, resultado, retorno),
            )
            self.c.execute(
                "INSERT INTO entregas_alertas VALUES "
                "(?, 'grupo:teste', 'entregue')",
                (identificador,),
            )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        dados = resumo["beneficio_dados"]["packball_lista_temporal"]

        self.assertEqual(dados["candidatos_expostos"], 3)
        self.assertEqual(dados["candidatos_dependentes"], 2)
        self.assertEqual(dados["dependentes_resolvidos"], 2)
        self.assertEqual(dados["dependentes_greens"], 1)
        self.assertEqual(dados["dependentes_reds"], 1)
        self.assertEqual(dados["dependentes_roi"], -0.1)
        self.assertEqual(dados["dependentes_taxa_acerto"], 0.5)
        self.assertEqual(dados["por_mercado"]["gol_ft"]["roi"], -0.1)

    def test_resultado_de_rejeitados_nao_conclui_valor_da_fonte(self):
        for identificador in range(100, 140):
            self._sinal(identificador, "betsapi", status="rejeitado")
            self.c.execute(
                "INSERT INTO resultados_sinais VALUES (?, 'red', -1)",
                (identificador,),
            )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        diagnostico = resumo["diagnosticos_fontes_pagas"]["betsapi"]

        self.assertTrue(
            diagnostico["resultados_candidatos_sao_contrafactuais"]
        )
        self.assertFalse(
            diagnostico["amostra_descritiva_exposta_suficiente"]
        )
        self.assertFalse(
            diagnostico["avaliacao_custo_beneficio_conclusiva"]
        )

    def test_entregas_teste_e_oficiais_ficam_separadas(self):
        for identificador, canal in ((201, "grupo:teste"), (202, "grupo")):
            self._sinal(identificador, "betsapi")
            self.c.execute(
                "INSERT INTO resultados_sinais VALUES (?, 'green', 0.8)",
                (identificador,),
            )
            self.c.execute(
                "INSERT INTO entregas_alertas VALUES (?, ?, 'entregue')",
                (identificador, canal),
            )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        item = resumo["entregas_por_fonte_mercado"]["betsapi"]["gol_ft"]

        self.assertEqual(item["entregues"], 2)
        self.assertEqual(item["por_modo"]["teste"]["entregues"], 1)
        self.assertEqual(item["por_modo"]["oficial"]["entregues"], 1)
        self.assertEqual(
            resumo["diagnosticos_fontes_pagas"]["betsapi"]
            ["entregas_oficiais_com_odd_da_fonte"],
            1,
        )

    def test_canal_derivado_nao_conta_como_entrega_de_sinal(self):
        self._sinal(250, "betsapi")
        self.c.execute(
            "INSERT INTO resultados_sinais VALUES (?, 'green', 0.8)",
            (250,),
        )
        self.c.execute(
            "INSERT INTO entregas_alertas VALUES "
            "(?, 'grupo:aguardar_odd', 'entregue')",
            (250,),
        )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )

        self.assertEqual(resumo["fontes"]["betsapi"]["entregues"], 0)
        self.assertNotIn(
            "betsapi", resumo["entregas_por_fonte_mercado"]
        )

    def test_mistura_de_estrategias_nao_forma_amostra_homogenea(self):
        for identificador in range(300, 340):
            ramo = "ramo-a" if identificador < 320 else "ramo-b"
            self.c.execute(
                "INSERT INTO sinais "
                "(id, partida_id, criado_em, status, odd, features_json, "
                "mercado, regra_versao) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identificador, identificador,
                    "2026-08-24T12:00:00", "simulacao", 1.8,
                    json.dumps({
                        "fonte_odds": "betsapi",
                        "exploracao_sombra": {"versao": ramo},
                    }),
                    "gol_ht", "regra-v1",
                ),
            )
            self.c.execute(
                "INSERT INTO resultados_sinais VALUES (?, 'green', 0.8)",
                (identificador,),
            )
            self.c.execute(
                "INSERT INTO entregas_alertas VALUES "
                "(?, 'grupo:teste', 'entregue')",
                (identificador,),
            )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        item = resumo["entregas_por_fonte_mercado"]["betsapi"]["gol_ht"]
        diagnostico = resumo["diagnosticos_fontes_pagas"]["betsapi"]

        self.assertEqual(item["resolvidos"], 40)
        self.assertEqual(len(item["por_estrategia"]), 2)
        self.assertFalse(
            diagnostico["amostra_descritiva_exposta_suficiente"]
        )
        self.assertEqual(
            diagnostico["motivo_avaliacao"],
            "amostra_exposta_homogenea_insuficiente",
        )

    def test_estrato_suficiente_continua_descritivo_sem_causalidade(self):
        for identificador in range(400, 430):
            self._sinal(identificador, "betsapi", status="simulacao")
            self.c.execute(
                "UPDATE sinais SET mercado='gol_ht', regra_versao='regra-v2' "
                "WHERE id=?",
                (identificador,),
            )
            self.c.execute(
                "INSERT INTO resultados_sinais VALUES (?, 'green', 0.8)",
                (identificador,),
            )
            self.c.execute(
                "INSERT INTO entregas_alertas VALUES "
                "(?, 'grupo:teste', 'entregue')",
                (identificador,),
            )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        diagnostico = resumo["diagnosticos_fontes_pagas"]["betsapi"]

        self.assertTrue(
            diagnostico["amostra_descritiva_exposta_suficiente"]
        )
        self.assertEqual(len(diagnostico["estratos_expostos_suficientes"]), 1)
        self.assertFalse(
            diagnostico["comparacao_causal_pareada_disponivel"]
        )
        self.assertFalse(
            diagnostico["avaliacao_custo_beneficio_conclusiva"]
        )
        self.assertEqual(
            diagnostico["motivo_avaliacao"],
            "amostra_exposta_sem_contrafactual_pareado_da_fonte",
        )

    def _sinal_com_preco_pareado(
        self, identificador, snapshot_id, bookmaker="bet365"
    ):
        self.c.execute(
            "INSERT INTO sinais "
            "(id, partida_id, criado_em, status, odd, features_json, "
            "mercado, linha, regra_versao, snapshot_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identificador, identificador,
                "2026-08-24T12:00:00", "simulacao", 1.80,
                json.dumps({
                    "fonte_odds": "betsapi",
                    "bookmaker_odds": bookmaker,
                    "exploracao_sombra": {"versao": "ramo-preco"},
                }),
                "gol_ft", "2.5", "regra-preco-v1", snapshot_id,
            ),
        )
        self.c.execute(
            "INSERT INTO entregas_alertas VALUES "
            "(?, 'grupo:teste', 'entregue')",
            (identificador,),
        )
        self.c.execute(
            "INSERT INTO resultados_sinais VALUES (?, 'green', 0.8)",
            (identificador,),
        )

    def _comparacao_preco(
        self, identificador, snapshot_id, bookmaker_b="pinnacle",
        odd_b=1.70, intervalo=4.0,
        compatibilidade="bookmakers_distintas", linha=2.5,
    ):
        self.c.execute(
            "INSERT INTO comparacoes_odds_fontes VALUES "
            "(?, ?, ?, 'gols', 'FT', ?, 'over', "
            "'betsapi', 'bet365', 1.80, "
            "'the_odds_api', ?, ?, ?, ?, 'desajuste_candidato')",
            (
                identificador, snapshot_id,
                "2026-08-24T12:00:01", linha, bookmaker_b, odd_b,
                intervalo, compatibilidade,
            ),
        )

    def test_preco_pareado_exige_bookmaker_independente(self):
        self._sinal_com_preco_pareado(501, 900)
        self._comparacao_preco(1, 900)

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        preco = resumo["contribuicao_preco_pareada"]

        self.assertEqual(preco["sinais_com_par_exato"], 1)
        self.assertEqual(preco["pares_referencia_independente"], 1)
        self.assertEqual(preco["preco_escolhido_melhor"], 1)
        self.assertEqual(preco["ganho_preco_realizado_unidades"], 0.1)
        self.assertEqual(
            preco["lucro_referencia_mesmo_resultado_unidades"], 0.7
        )
        self.assertEqual(preco["estado"], "coletando_amostra_independente")
        self.assertFalse(preco["amostra_independente_suficiente"])
        self.assertTrue(
            resumo["diagnosticos_fontes_pagas"]["betsapi"]
            ["comparacao_preco_independente_disponivel"]
        )

    def test_mesma_bookmaker_nao_prova_contribuicao_de_preco(self):
        self._sinal_com_preco_pareado(502, 901)
        self._comparacao_preco(
            2, 901, bookmaker_b="bet365",
            compatibilidade="mesma_bookmaker",
        )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        preco = resumo["contribuicao_preco_pareada"]

        self.assertEqual(preco["sinais_com_par_exato"], 1)
        self.assertEqual(preco["pares_mesma_bookmaker"], 1)
        self.assertEqual(preco["pares_referencia_independente"], 0)
        self.assertEqual(preco["estado"], "sem_referencia_independente")

    def test_linha_diferente_nao_e_associada_ao_sinal(self):
        self._sinal_com_preco_pareado(503, 902)
        self._comparacao_preco(3, 902, linha=3.5)

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )

        self.assertEqual(
            resumo["contribuicao_preco_pareada"]
            ["sinais_com_par_exato"],
            0,
        )

    def test_um_sinal_conta_um_unico_par_e_prefere_o_mais_proximo(self):
        self._sinal_com_preco_pareado(504, 903)
        self._comparacao_preco(4, 903, odd_b=1.60, intervalo=20.0)
        self._comparacao_preco(5, 903, odd_b=1.79, intervalo=2.0)

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        preco = resumo["contribuicao_preco_pareada"]

        self.assertEqual(preco["sinais_com_par_exato"], 1)
        self.assertEqual(preco["pares_referencia_independente"], 1)
        self.assertEqual(preco["delta_odd_medio"], 0.01)

    def test_trinta_pares_homogeneos_podem_confirmar_vantagem_de_preco(self):
        for indice in range(30):
            sinal_id = 600 + indice
            snapshot_id = 1000 + indice
            self._sinal_com_preco_pareado(sinal_id, snapshot_id)
            self._comparacao_preco(
                100 + indice, snapshot_id, odd_b=1.70,
            )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        preco = resumo["contribuicao_preco_pareada"]

        self.assertEqual(preco["pares_referencia_independente"], 30)
        self.assertEqual(preco["partidas_independentes"], 30)
        self.assertTrue(preco["amostra_independente_suficiente"])
        self.assertTrue(preco["vantagem_preco_confirmada"])
        self.assertEqual(preco["intervalo_ganho_preco_95"], [0.1, 0.1])
        self.assertEqual(preco["estado"], "apto_revisao_preco")
        self.assertEqual(len(preco["estratos_independentes_suficientes"]), 1)
        self.assertFalse(preco["aplicacao_sinais"])
        self.assertFalse(preco["promocao_automatica"])

    def _sinal_melhor_preco_sombra(
        self, identificador, partida_id, diferenca=0.10,
        valor_esperado=None, status="aprovado",
        criado_em="2026-08-24T12:00:00", mercado="gol_ft",
    ):
        sombra = {
            "versao": VERSAO_MELHOR_PRECO_SOMBRA,
            "estado": "comparacao_independente_exata",
            "cotacao_escolhida": {
                "fonte": "betsapi", "bookmaker": "bet365", "odd": 1.80,
            },
            "melhor_alternativa_independente": {
                "fonte": "the_odds_api", "bookmaker": "pinnacle",
                "odd": 1.80 + diferenca,
            },
            "diferenca_odd": diferenca,
            "relacao": (
                "alternativa_melhor" if diferenca > 0.005
                else "escolhida_melhor" if diferenca < -0.005
                else "equivalentes"
            ),
            "ganho_retorno_bruto_potencial_percentual": round(
                diferenca / 1.80 * 100, 3
            ),
            "aplicacao_sinais": False,
            "telegram": False,
        }
        if valor_esperado is not None:
            sombra["valor_justo_sombra"] = {
                "versao": VERSAO_VALOR_JUSTO,
                "estado": (
                    "desajuste_favoravel_candidato"
                    if valor_esperado >= 0.02
                    else "sem_desajuste_favoravel"
                ),
                "valor_esperado_referencia": valor_esperado,
                "desajuste_favoravel": valor_esperado >= 0.02,
                "probabilidade_referencia_sem_vig": 0.70,
                "avaliacao_resultado_sombra": (
                    politica_avaliacao_resultado()
                ),
            }
        self.c.execute(
            "INSERT INTO sinais "
            "(id, partida_id, criado_em, status, odd, features_json, "
            "mercado, linha, regra_versao, snapshot_id) "
            "VALUES (?, ?, ?, ?, 1.80, ?, ?, '2.5', 'regra-v1', ?)",
            (
                identificador, partida_id, criado_em, status,
                json.dumps({"melhor_preco_sombra": sombra}),
                mercado,
                3000 + identificador,
            ),
        )

    def test_preco_prospectivo_nao_infla_partida_reavaliada(self):
        self._sinal_melhor_preco_sombra(800, 700)
        self._sinal_melhor_preco_sombra(801, 700, diferenca=0.30)

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )["melhor_preco_prospectivo"]

        self.assertEqual(1, resumo["comparacoes_independentes"])
        self.assertEqual(1, resumo["partidas_distintas"])
        self.assertEqual(0.10, resumo["delta_odd_medio"])
        self.assertEqual("coletando_amostra_independente", resumo["estado"])
        self.assertFalse(resumo["aplicacao_sinais"])

    def test_trinta_precos_prospectivos_homogeneos_liberam_so_revisao(self):
        for indice in range(30):
            self._sinal_melhor_preco_sombra(
                900 + indice, 800 + indice
            )

        relatorio = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )
        resumo = relatorio["melhor_preco_prospectivo"]

        self.assertEqual(
            "valor-fontes-odds-v9-resultado-valor-justo",
            relatorio["versao"],
        )
        self.assertEqual(30, resumo["comparacoes_independentes"])
        self.assertEqual(30, resumo["partidas_distintas"])
        self.assertEqual([0.1, 0.1], resumo["intervalo_delta_odd_95"])
        self.assertEqual("apto_revisao_seletor_preco", resumo["estado"])
        self.assertEqual(1, len(
            resumo["estratos_independentes_suficientes"]
        ))
        self.assertTrue(
            resumo["estratos_independentes_suficientes"][0]
            ["alternativa_melhor_confirmada"]
        )
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["altera_calibracao"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["promocao_automatica"])

    def test_trinta_precos_justos_positivos_liberam_apenas_revisao(self):
        for indice in range(30):
            self._sinal_melhor_preco_sombra(
                1000 + indice,
                900 + indice,
                valor_esperado=0.05,
            )

        resumo = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )["melhor_preco_prospectivo"]

        self.assertEqual(30, resumo["avaliacoes_valor_justo"])
        self.assertEqual(30, resumo["partidas_valor_justo_distintas"])
        self.assertEqual([0.05, 0.05], resumo["intervalo_valor_esperado_95"])
        self.assertTrue(resumo["vantagem_valor_justo_confirmada"])
        self.assertEqual("apto_revisao_valor_justo", resumo[
            "estado_valor_justo"
        ])
        self.assertEqual(1, len(
            resumo["estratos_valor_justo_aptos_revisao"]
        ))
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["promocao_automatica"])

    def _habilitar_cronologia_resultados(self):
        self.c.execute(
            "ALTER TABLE resultados_sinais ADD COLUMN encerrado_em TEXT"
        )

    def test_resultado_valor_justo_exclui_rejeitado_e_separa_controle(self):
        self._habilitar_cronologia_resultados()
        self._sinal_melhor_preco_sombra(
            1100, 1000, valor_esperado=0.05, status="rejeitado"
        )
        self._sinal_melhor_preco_sombra(
            1101, 1001, valor_esperado=0.05, status="auditoria"
        )
        self._sinal_melhor_preco_sombra(
            1102, 1002, valor_esperado=-0.01, status="simulacao"
        )
        self.c.executemany(
            "INSERT INTO resultados_sinais "
            "(sinal_id, resultado, retorno_unidades, encerrado_em) "
            "VALUES (?, ?, ?, ?)",
            [
                (1100, "red", -1.0, "2026-08-24T14:00:00"),
                (1101, "green", 0.8, "2026-08-24T14:00:00"),
                (1102, "red", -1.0, "2026-08-24T14:00:00"),
            ],
        )

        validacao = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )["validacao_resultado_valor_justo"]
        mercado = validacao["por_mercado"]["gol_ft"]["total"]

        self.assertEqual(2, validacao["candidatos_elegiveis"])
        self.assertEqual(1, validacao["exclusoes"]["status_nao_liquidavel"])
        self.assertEqual(1, mercado["edge"]["resultados_validos"])
        self.assertEqual(0.8, mercado["edge"]["roi_real"])
        self.assertEqual(1, mercado["controle_sem_edge"]["resultados_validos"])
        self.assertEqual(-1.0, mercado["controle_sem_edge"]["roi_real"])
        self.assertFalse(validacao["aplicacao_sinais"])
        self.assertEqual(
            0,
            validacao["validacao_transferencia"]["candidatos_pos_ancora"],
        )

    def test_transferencia_separa_acionaveis_de_auditorias_futuras(self):
        self._habilitar_cronologia_resultados()
        self._sinal_melhor_preco_sombra(
            1150, 1050, valor_esperado=0.05, status="aprovado",
            criado_em="2026-09-13T12:00:00",
        )
        self._sinal_melhor_preco_sombra(
            1151, 1051, valor_esperado=-0.01, status="auditoria",
            criado_em="2026-09-13T12:01:00",
        )
        self.c.executemany(
            "INSERT INTO resultados_sinais "
            "(sinal_id, resultado, retorno_unidades, encerrado_em) "
            "VALUES (?, ?, ?, ?)",
            [
                (1150, "green", 0.8, "2026-09-13T14:00:00"),
                (1151, "red", -1.0, "2026-09-13T14:00:00"),
            ],
        )

        transferencia = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 9, 13, 18)
        )["validacao_resultado_valor_justo"]["validacao_transferencia"]
        mercado = transferencia["por_mercado"]["gol_ft"]

        self.assertEqual(2, transferencia["candidatos_pos_ancora"])
        self.assertEqual(
            {"aprovado": 1, "auditoria": 1},
            transferencia["composicao_status"],
        )
        self.assertEqual(
            1,
            mercado["estratos"]["candidatos_acionaveis"]["coorte"],
        )
        self.assertEqual(
            1,
            mercado["estratos"]["auditorias_silenciosas"]["coorte"],
        )
        self.assertFalse(mercado["vantagem_transferivel_comprovada"])
        self.assertEqual(
            "formando_coortes_por_origem", transferencia["estado"]
        )
        self.assertFalse(transferencia["aplicacao_sinais"])
        self.assertFalse(transferencia["telegram"])

    def test_politica_transferencia_e_congelada_e_sem_efeito(self):
        politica = politica_transferencia_resultado()
        self.assertEqual(
            "2026-09-12T18:20:00-04:00",
            politica["ancora_prospectiva"],
        )
        self.assertTrue(politica["exige_vantagem_nos_dois_estratos"])
        self.assertEqual(64, len(politica["definicao_sha256"]))
        self.assertFalse(politica["aplicacao_sinais"])
        self.assertFalse(politica["altera_calibracao"])
        self.assertFalse(politica["telegram"])
        self.assertFalse(politica["promocao_automatica"])

    def test_resultado_valor_justo_nao_substitui_primeiro_pendente(self):
        self._habilitar_cronologia_resultados()
        self._sinal_melhor_preco_sombra(
            1200, 1100, valor_esperado=0.05,
            criado_em="2026-08-24T12:00:00",
        )
        self._sinal_melhor_preco_sombra(
            1201, 1100, valor_esperado=0.05,
            criado_em="2026-08-24T12:05:00",
        )
        self.c.execute(
            "INSERT INTO resultados_sinais "
            "(sinal_id, resultado, retorno_unidades, encerrado_em) "
            "VALUES (1201, 'green', 0.8, '2026-08-24T14:00:00')"
        )

        total = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )["validacao_resultado_valor_justo"]["por_mercado"][
            "gol_ft"
        ]["total"]["edge"]

        self.assertEqual(1, total["candidatos"])
        self.assertEqual(1, total["pendentes"])
        self.assertEqual(0, total["resultados_validos"])

    def test_resultado_anterior_ao_sinal_bloqueia_inferencia(self):
        self._habilitar_cronologia_resultados()
        self._sinal_melhor_preco_sombra(
            1300, 1200, valor_esperado=0.05
        )
        self.c.execute(
            "INSERT INTO resultados_sinais "
            "(sinal_id, resultado, retorno_unidades, encerrado_em) "
            "VALUES (1300, 'green', 0.8, '2026-08-24T11:59:00')"
        )

        validacao = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )["validacao_resultado_valor_justo"]

        self.assertFalse(validacao["saudavel"])
        self.assertEqual("resultado_inconsistente", validacao["estado"])
        self.assertEqual(1, validacao["violacoes_integridade"])

    def test_coorte_completa_favoravel_libera_somente_revisao(self):
        self._habilitar_cronologia_resultados()
        resultados = []
        for indice in range(100):
            edge = indice % 2 == 0
            sinal_id = 1400 + indice
            self._sinal_melhor_preco_sombra(
                sinal_id,
                1300 + indice,
                valor_esperado=0.05 if edge else -0.01,
            )
            if indice < 95:
                resultados.append((
                    sinal_id,
                    "green" if edge else "red",
                    0.8 if edge else -1.0,
                    "2026-08-24T14:00:00",
                ))
        self.c.executemany(
            "INSERT INTO resultados_sinais "
            "(sinal_id, resultado, retorno_unidades, encerrado_em) "
            "VALUES (?, ?, ?, ?)",
            resultados,
        )

        validacao = resumir_valor_fontes(
            self.c, dias=30, agora=datetime(2026, 8, 24, 18)
        )["validacao_resultado_valor_justo"]
        mercado = validacao["por_mercado"]["gol_ft"]

        self.assertTrue(mercado["evidencia_completa"])
        self.assertTrue(mercado["vantagem_resultados_comprovada"])
        self.assertEqual(
            "vantagem_real_confirmada_somente_para_revisao",
            mercado["decisao"],
        )
        self.assertEqual("apto_revisao_humana", validacao["estado"])
        self.assertFalse(validacao["aplicacao_sinais"])
        self.assertFalse(validacao["altera_calibracao"])
        self.assertFalse(validacao["telegram"])
        self.assertFalse(validacao["promocao_automatica"])


if __name__ == "__main__":
    unittest.main()
