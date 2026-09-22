import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from banco import BancoMonitor
from exploracao_sombra import (
    FASE_EXPLORACAO_GOLS,
    MINIMO_VALIDACAO_EXPLORACAO_GOLS,
    MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3,
    MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE,
    REGRA_FINGERPRINT_GOL_FT_V3,
    TAMANHO_COORTE_VALIDACAO_GOL_FT_V3,
    TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
    VERSAO_EXPLORACAO_ASIATICA,
    VERSAO_EXPLORACAO_GOL_FT_V3,
    VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
    VERSAO_EXPLORACAO_SOMBRA,
    criar_exploracao_asiatica_multiplos,
    criar_exploracao_sombra,
    criar_exploracao_gol_ft_v2_controle,
    gerar_exploracoes_sombra,
    auditar_definicao_gol_ft_v2_controle,
    auditar_definicao_exploracao_gols,
    registrar_ou_validar_definicao_exploracao_gol_ft_v3,
    registrar_ou_validar_definicao_exploracao_gols,
    registrar_ou_validar_politica_avaliacao_gol_ft_v3,
    registrar_ou_validar_definicao_gol_ft_v2_controle,
    registrar_ou_validar_politica_gol_ft_v2_controle,
    registrar_ou_validar_politica_avaliacao_gols,
    _avaliar_retornos_validacao_gols,
    _resumir_funil_exploracao_gols_linhas,
    resumir_exploracoes_sombra,
)


class ExploracaoSombraTest(unittest.TestCase):
    @staticmethod
    def candidato(**alteracoes):
        base = {
            "mercado": "gol_ft",
            "status": "rejeitado",
            "bloqueios": ["atividade_recente_insuficiente_gols"],
            "pontuacao_tecnica": 72,
            "qualidade_dados": 90,
            "odd": 1.8,
            "idade_odds_segundos": 30,
            "motivos": ["alvo=mais_1_gol"],
            "features": {
                "minuto": 70,
                "janelas": {"5": {"chutes_total": 1}},
            },
            "regra_versao": "sinais-v6",
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
        }
        base.update(alteracoes)
        return base

    def test_relaxa_somente_atividade_e_mantem_original_inalterado(self):
        original = self.candidato()

        sombra = criar_exploracao_sombra(original)

        self.assertEqual(sombra["status"], "simulacao")
        self.assertEqual(sombra["bloqueios"], [])
        self.assertEqual(original["status"], "rejeitado")
        self.assertIn(
            f"exploracao_sombra={VERSAO_EXPLORACAO_GOL_FT_V3}",
            sombra["motivos"],
        )
        self.assertFalse(
            sombra["features"]["exploracao_sombra"]["aplicacao_automatica"]
        )
        self.assertEqual(
            sombra["features"]["exploracao_sombra"]["fase"],
            FASE_EXPLORACAO_GOLS,
        )
        self.assertEqual(
            sombra["features"]["exploracao_sombra"][
                "minimo_resultados_validacao"
            ],
            MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3,
        )

    def test_nao_relaxa_odd_ausente_historico_ou_qualidade(self):
        casos = (
            self.candidato(odd=None),
            self.candidato(qualidade_dados=79),
            self.candidato(bloqueios=[
                "atividade_recente_insuficiente_gols",
                "historico_5min_insuficiente",
            ]),
            self.candidato(status="aprovado"),
        )

        self.assertTrue(all(
            criar_exploracao_sombra(item) is None for item in casos
        ))

    def test_aceita_gol_ht_sem_remover_bloqueio_de_janela(self):
        self.assertIsNotNone(criar_exploracao_sombra(
            self.candidato(mercado="gol_ht")
        ))
        self.assertIsNone(criar_exploracao_sombra(self.candidato(
            mercado="gol_ht",
            bloqueios=["fora_da_janela_gol_ht_max_28"],
        )))

    def test_gol_ft_v3_exige_chute_recente_e_linhagem_exata(self):
        self.assertIsNone(criar_exploracao_sombra(self.candidato(
            features={"minuto": 70, "janelas": {"5": {
                "chutes_total": 0,
            }}},
        )))
        self.assertIsNone(criar_exploracao_sombra(self.candidato(
            regra_fingerprint="fingerprint-divergente",
        )))

        sombra = criar_exploracao_sombra(self.candidato())

        self.assertEqual(
            sombra["features"]["exploracao_sombra"]["versao"],
            VERSAO_EXPLORACAO_GOL_FT_V3,
        )
        self.assertEqual(
            sombra["features"]["exploracao_sombra"]
            ["tamanho_coorte_fixa"],
            TAMANHO_COORTE_VALIDACAO_GOL_FT_V3,
        )
        self.assertFalse(
            sombra["features"]["exploracao_sombra"]
            ["telegram_oficial"]
        )

    def test_v2_controle_reproduz_gate_original_sem_exigir_chute(self):
        sem_chute = self.candidato(features={
            "minuto": 70,
            "janelas": {"5": {"chutes_total": 0}},
        })

        controle = criar_exploracao_gol_ft_v2_controle(sem_chute)

        self.assertIsNotNone(controle)
        self.assertEqual(controle["status"], "simulacao")
        self.assertEqual(
            controle["features"]["exploracao_sombra"]["versao"],
            VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        )
        self.assertFalse(
            controle["features"]["exploracao_sombra"]
            ["criterio_selecao"]["filtro_atividade_adicional"]
        )
        self.assertFalse(
            controle["features"]["exploracao_sombra"]
            ["historico_v2_reaberto"]
        )
        self.assertIsNone(criar_exploracao_gol_ft_v2_controle(
            self.candidato(bloqueios=[
                "atividade_recente_insuficiente_gols",
                "historico_5min_insuficiente",
            ])
        ))
        self.assertIsNone(criar_exploracao_gol_ft_v2_controle(
            self.candidato(pontuacao_tecnica=64.9)
        ))

    def test_gerador_roda_v2_controle_e_v3_em_paralelo_por_versao(self):
        ambas = gerar_exploracoes_sombra([self.candidato()])
        versoes_ambas = {
            item["features"]["exploracao_sombra"]["versao"]
            for item in ambas
        }
        somente_controle = gerar_exploracoes_sombra([
            self.candidato(features={
                "minuto": 70,
                "janelas": {"5": {"chutes_total": 0}},
            })
        ])

        self.assertEqual(versoes_ambas, {
            VERSAO_EXPLORACAO_GOL_FT_V3,
            VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        })
        self.assertEqual(len(ambas), 2)
        self.assertEqual(len(somente_controle), 1)
        self.assertEqual(
            somente_controle[0]["features"]["exploracao_sombra"]
            ["versao"],
            VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        )

    def test_definicao_da_validacao_futura_fica_ancorada_e_imutavel(self):
        banco = BancoMonitor(":memory:")
        try:
            primeira = registrar_ou_validar_definicao_exploracao_gols(
                banco.conexao
            )
            politica = registrar_ou_validar_politica_avaliacao_gols(
                banco.conexao
            )
            registrar_ou_validar_definicao_exploracao_gol_ft_v3(
                banco.conexao
            )
            registrar_ou_validar_politica_avaliacao_gol_ft_v3(
                banco.conexao
            )
            controle = (
                registrar_ou_validar_definicao_gol_ft_v2_controle(
                    banco.conexao
                )
            )
            politica_controle = (
                registrar_ou_validar_politica_gol_ft_v2_controle(
                    banco.conexao
                )
            )
            segunda = registrar_ou_validar_definicao_exploracao_gols(
                banco.conexao
            )
            auditoria = auditar_definicao_exploracao_gols(
                banco.conexao
            )
            self.assertEqual(
                primeira["definicao_sha256"],
                segunda["definicao_sha256"],
            )
            self.assertTrue(auditoria["saudavel"])
            self.assertTrue(auditoria["protegida"])
            self.assertTrue(
                auditoria["politica_avaliacao"]["registrada"]
            )
            self.assertEqual(
                politica["politica_sha256"],
                auditoria["politica_avaliacao"]["politica_sha256"],
            )
            auditoria_controle = auditar_definicao_gol_ft_v2_controle(
                banco.conexao
            )
            self.assertTrue(auditoria_controle["saudavel"])
            self.assertEqual(
                controle["definicao_sha256"],
                auditoria_controle["definicao_sha256"],
            )
            self.assertEqual(
                politica_controle["politica_sha256"],
                auditoria_controle["politica_sha256"],
            )
            with self.assertRaises(sqlite3.IntegrityError):
                banco.conexao.execute(
                    """
                    UPDATE metadados SET valor='{}'
                    WHERE chave LIKE 'exploracao_sombra_definicao:%'
                    """
                )
            with self.assertRaises(sqlite3.IntegrityError):
                banco.conexao.execute(
                    """
                    DELETE FROM metadados
                    WHERE chave LIKE 'exploracao_sombra_definicao:%'
                    """
                )
            with self.assertRaises(sqlite3.IntegrityError):
                banco.conexao.execute(
                    """
                    UPDATE metadados SET valor='{}'
                    WHERE chave LIKE 'exploracao_sombra_politica:%'
                    """
                )
            with self.assertRaises(sqlite3.IntegrityError):
                banco.conexao.execute(
                    """
                    DELETE FROM metadados
                    WHERE chave LIKE 'exploracao_sombra_politica:%'
                    """
                )
        finally:
            banco.fechar()

    def test_preflight_aceita_v3_ainda_nao_registrada(self):
        banco = BancoMonitor(":memory:")
        try:
            registrar_ou_validar_definicao_exploracao_gols(
                banco.conexao
            )
            registrar_ou_validar_politica_avaliacao_gols(
                banco.conexao
            )

            auditoria = auditar_definicao_exploracao_gols(
                banco.conexao
            )

            self.assertTrue(auditoria["saudavel"])
            self.assertEqual(
                auditoria["exploracao_gol_ft_v3"]["estado"],
                "nao_registrada",
            )
            self.assertIsNone(
                auditoria["exploracao_gol_ft_v3"]["motivo"]
            )
        finally:
            banco.fechar()

    def test_politica_estatistica_nao_promove_resultado_inconclusivo(self):
        aguardando = _avaliar_retornos_validacao_gols([0.8] * 10)
        favoravel = _avaliar_retornos_validacao_gols([0.5] * 30)
        inconclusiva = _avaliar_retornos_validacao_gols(
            [0.8] * 18 + [-1.0] * 12
        )
        desfavoravel = _avaliar_retornos_validacao_gols([-0.5] * 30)

        self.assertEqual(
            aguardando["decisao_estatistica"],
            "aguardando_amostra_futura",
        )
        self.assertEqual(
            favoravel["decisao_estatistica"],
            "favoravel_para_revisao_independente",
        )
        self.assertEqual(
            inconclusiva["decisao_estatistica"], "inconclusiva"
        )
        self.assertEqual(
            desfavoravel["decisao_estatistica"],
            "evidencia_desfavoravel",
        )

    def test_resumo_deduplica_defensivamente_a_mesma_partida(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
            CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais(
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                snapshot_id INTEGER,
                mercado TEXT, criado_em TEXT, status TEXT,
                pontuacao_tecnica REAL, odd REAL,
                regra_versao TEXT, regra_fingerprint TEXT,
                motivos_json TEXT, features_json TEXT
            );
            CREATE TABLE snapshots(
                id INTEGER PRIMARY KEY, contexto_api_json TEXT
            );
            CREATE TABLE resultados_sinais(
                sinal_id INTEGER PRIMARY KEY, resultado TEXT,
                retorno_unidades REAL
            );
        """)
        features = json.dumps({"exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_SOMBRA,
        }})
        for sinal_id, retorno in ((1, 0.8), (2, -1.0)):
            contexto = {
                "evolucao_temporal_api_live": {
                    "5": {"chutes": [2, 1]},
                },
                "comparacao_temporal_packball_api": {
                    "total": 2,
                    "concordantes": 2,
                    "aplicacao_sinais": False,
                },
            } if sinal_id == 1 else {}
            conexao.execute(
                "INSERT INTO snapshots VALUES(?, ?)",
                (sinal_id, json.dumps(contexto)),
            )
            conexao.execute(
                """INSERT INTO sinais VALUES(
                    ?, 10, ?, 'gol_ft', ?, 'simulacao', 70, 1.8,
                    'sinais-v6', 'fp-v6', '[]', ?
                )""",
                (
                    sinal_id, sinal_id,
                    f"2026-08-08T10:0{sinal_id}:00", features,
                ),
            )
            conexao.execute(
                "INSERT INTO resultados_sinais VALUES(?, ?, ?)",
                (sinal_id, "green" if retorno > 0 else "red", retorno),
            )

        resumo = resumir_exploracoes_sombra(conexao)

        item = resumo["validacao_prospectiva_gols"]["gol_ft"]
        self.assertEqual(item["avaliadas"], 1)
        self.assertEqual(item["greens"], 1)
        self.assertEqual(item["reds"], 0)
        cobertura = resumo["cobertura_temporal_validacao_gols"][
            "gol_ft"
        ]
        self.assertEqual(cobertura["total"], 1)
        self.assertEqual(cobertura["com_evolucao_api"], 1)
        self.assertEqual(cobertura["com_comparacao_fontes"], 1)
        self.assertEqual(cobertura["com_confirmacao"]["greens"], 1)
        self.assertEqual(cobertura["com_confirmacao"]["roi"], 0.8)
        self.assertFalse(cobertura["uso_na_decisao_validacao"])
        conexao.close()

    def test_validacao_gols_congela_nos_primeiros_trinta_candidatos(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
            CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais(
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                snapshot_id INTEGER, mercado TEXT, criado_em TEXT,
                status TEXT, pontuacao_tecnica REAL, odd REAL,
                regra_versao TEXT, regra_fingerprint TEXT,
                motivos_json TEXT, features_json TEXT
            );
            CREATE TABLE snapshots(
                id INTEGER PRIMARY KEY, contexto_api_json TEXT
            );
            CREATE TABLE resultados_sinais(
                sinal_id INTEGER PRIMARY KEY, resultado TEXT,
                retorno_unidades REAL
            );
        """)
        features = json.dumps({"exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_SOMBRA,
        }})
        for sinal_id in range(1, 36):
            conexao.execute(
                "INSERT INTO snapshots VALUES(?, '{}')", (sinal_id,)
            )
            conexao.execute(
                """INSERT INTO sinais VALUES(
                    ?, ?, ?, 'gol_ft', ?, 'simulacao', 75, 1.8,
                    'sinais-v6', 'fp-v6', '[]', ?
                )""",
                (
                    sinal_id, sinal_id, sinal_id,
                    f"2026-08-08T10:{sinal_id:02d}:00", features,
                ),
            )
            # Os cinco exemplos extras seriam todos GREEN e mudariam a
            # conclusão caso a janela prospectiva continuasse crescendo.
            green = sinal_id > 30 or sinal_id % 2 == 0
            conexao.execute(
                "INSERT INTO resultados_sinais VALUES(?, ?, ?)",
                (sinal_id, "green" if green else "red", 0.8 if green else -1),
            )

        item = resumir_exploracoes_sombra(conexao)[
            "validacao_prospectiva_gols"
        ]["gol_ft"]

        self.assertEqual(item["avaliadas"], 30)
        self.assertEqual(item["greens"], 15)
        self.assertEqual(item["reds"], 15)
        self.assertEqual(item["total_disponivel"], 35)
        self.assertEqual(item["resultados_totais_disponiveis"], 35)
        self.assertTrue(item["validacao_congelada"])
        self.assertEqual(item["roi"], -0.1)
        conexao.close()

    def test_validacao_gols_bloqueia_coorte_com_linhagens_misturadas(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
            CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais(
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                snapshot_id INTEGER, mercado TEXT, criado_em TEXT,
                status TEXT, pontuacao_tecnica REAL, odd REAL,
                regra_versao TEXT, regra_fingerprint TEXT,
                motivos_json TEXT, features_json TEXT
            );
            CREATE TABLE snapshots(
                id INTEGER PRIMARY KEY, contexto_api_json TEXT
            );
            CREATE TABLE resultados_sinais(
                sinal_id INTEGER PRIMARY KEY, resultado TEXT,
                retorno_unidades REAL
            );
        """)
        features = json.dumps({"exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_SOMBRA,
        }})
        for sinal_id in range(1, 31):
            regra = "sinais-v6" if sinal_id < 30 else "sinais-v7"
            conexao.execute(
                "INSERT INTO snapshots VALUES(?, '{}')", (sinal_id,)
            )
            conexao.execute(
                """INSERT INTO sinais VALUES(
                    ?, ?, ?, 'gol_ft', ?, 'simulacao', 80, 2.0,
                    ?, ?, '[]', ?
                )""",
                (
                    sinal_id, sinal_id, sinal_id,
                    f"2026-08-08T11:{sinal_id:02d}:00",
                    regra, f"fp-{regra}", features,
                ),
            )
            conexao.execute(
                "INSERT INTO resultados_sinais VALUES(?, 'green', 1.0)",
                (sinal_id,),
            )

        item = resumir_exploracoes_sombra(conexao)[
            "validacao_prospectiva_gols"
        ]["gol_ft"]

        self.assertFalse(item["linhagem_homogenea"])
        self.assertEqual(item["estado"], "inconsistente")
        self.assertEqual(
            item["decisao_estatistica"], "linhagem_inconsistente"
        )
        self.assertEqual(len(item["linhagens_coorte"]), 2)
        conexao.close()

    def test_gol_ft_v3_congela_75_futuros_e_fingerprint_da_coorte(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
            CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais(
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                snapshot_id INTEGER, mercado TEXT, criado_em TEXT,
                status TEXT, pontuacao_tecnica REAL, odd REAL,
                regra_versao TEXT, regra_fingerprint TEXT,
                motivos_json TEXT, features_json TEXT
            );
            CREATE TABLE snapshots(
                id INTEGER PRIMARY KEY, contexto_api_json TEXT
            );
            CREATE TABLE resultados_sinais(
                sinal_id INTEGER PRIMARY KEY, resultado TEXT,
                retorno_unidades REAL
            );
        """)
        conexao.execute(
            "INSERT INTO metadados VALUES(?, ?)",
            (
                "exploracao_sombra_definicao:"
                + VERSAO_EXPLORACAO_GOL_FT_V3,
                json.dumps({"registrado_em": "2026-08-10T00:00:00"}),
            ),
        )
        features = json.dumps({"exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
        }})
        for sinal_id in range(1, 81):
            hora, minuto = divmod(sinal_id, 60)
            criado_em = f"2026-08-10T{hora:02d}:{minuto:02d}:00"
            conexao.execute(
                "INSERT INTO snapshots VALUES(?, '{}')", (sinal_id,)
            )
            conexao.execute(
                """INSERT INTO sinais VALUES(
                    ?, ?, ?, 'gol_ft', ?, 'simulacao', 80, 1.8,
                    'sinais-v6', ?, '[]', ?
                )""",
                (
                    sinal_id, sinal_id, sinal_id, criado_em,
                    REGRA_FINGERPRINT_GOL_FT_V3, features,
                ),
            )
            green = sinal_id % 3 != 0
            conexao.execute(
                "INSERT INTO resultados_sinais VALUES(?, ?, ?)",
                (sinal_id, "green" if green else "red", 0.8 if green else -1),
            )

        primeiro = resumir_exploracoes_sombra(conexao)[
            "validacao_prospectiva_gol_ft_v3"
        ]
        conexao.execute(
            "UPDATE resultados_sinais SET resultado='red', "
            "retorno_unidades=-1 WHERE sinal_id=1"
        )
        segundo = resumir_exploracoes_sombra(conexao)[
            "validacao_prospectiva_gol_ft_v3"
        ]
        conexao.execute(
            "UPDATE sinais SET regra_fingerprint='divergente' WHERE id=75"
        )
        inconsistente = resumir_exploracoes_sombra(conexao)[
            "validacao_prospectiva_gol_ft_v3"
        ]

        self.assertEqual(primeiro["candidatos_coorte"], 75)
        self.assertEqual(primeiro["total_disponivel"], 80)
        self.assertTrue(primeiro["coorte_fechada"])
        self.assertTrue(primeiro["linhagem_compativel"])
        self.assertEqual(
            primeiro["validacao_fingerprint"],
            segundo["validacao_fingerprint"],
        )
        self.assertNotEqual(primeiro["roi"], segundo["roi"])
        self.assertFalse(primeiro["promocao_automatica"])
        self.assertFalse(primeiro["telegram_oficial"])
        self.assertEqual(inconsistente["estado"], "inconsistente")
        self.assertEqual(
            inconsistente["decisao_estatistica"],
            "linhagem_inconsistente",
        )
        conexao.close()

    def test_v2_controle_compara_v3_no_mesmo_periodo_e_sobreposicao(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
            CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais(
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                snapshot_id INTEGER, mercado TEXT, criado_em TEXT,
                status TEXT, pontuacao_tecnica REAL, odd REAL,
                regra_versao TEXT, regra_fingerprint TEXT,
                motivos_json TEXT, features_json TEXT
            );
            CREATE TABLE snapshots(
                id INTEGER PRIMARY KEY, contexto_api_json TEXT
            );
            CREATE TABLE resultados_sinais(
                sinal_id INTEGER PRIMARY KEY, resultado TEXT,
                retorno_unidades REAL
            );
        """)
        inicio = datetime(2026, 8, 11, 10, 0, 0)
        conexao.execute(
            "INSERT INTO metadados VALUES(?, ?)",
            (
                "exploracao_sombra_definicao:"
                + VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
                json.dumps({"registrado_em": inicio.isoformat()}),
            ),
        )
        features_controle = json.dumps({"exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        }})
        features_v3 = json.dumps({"exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
        }})
        for partida_id in range(1, 81):
            sinal_id = partida_id
            criado_em = (inicio + timedelta(minutes=partida_id)).isoformat()
            conexao.execute(
                "INSERT INTO snapshots VALUES(?, '{}')", (sinal_id,)
            )
            conexao.execute(
                """INSERT INTO sinais VALUES(
                    ?, ?, ?, 'gol_ft', ?, 'simulacao', 75, 1.8,
                    'sinais-v6', ?, '[]', ?
                )""",
                (
                    sinal_id, partida_id, sinal_id, criado_em,
                    REGRA_FINGERPRINT_GOL_FT_V3, features_controle,
                ),
            )
            green = partida_id % 2 == 0
            conexao.execute(
                "INSERT INTO resultados_sinais VALUES(?, ?, ?)",
                (sinal_id, "green" if green else "red", 0.8 if green else -1),
            )
            if partida_id <= 50:
                sinal_v3 = 100 + partida_id
                conexao.execute(
                    "INSERT INTO snapshots VALUES(?, '{}')", (sinal_v3,)
                )
                conexao.execute(
                    """INSERT INTO sinais VALUES(
                        ?, ?, ?, 'gol_ft', ?, 'simulacao', 75, 1.8,
                        'sinais-v6', ?, '[]', ?
                    )""",
                    (
                        sinal_v3, partida_id, sinal_v3, criado_em,
                        REGRA_FINGERPRINT_GOL_FT_V3, features_v3,
                    ),
                )
                conexao.execute(
                    "INSERT INTO resultados_sinais VALUES(?, ?, ?)",
                    (
                        sinal_v3, "green" if green else "red",
                        0.8 if green else -1,
                    ),
                )

        resumo = resumir_exploracoes_sombra(conexao)
        controle = resumo["validacao_gol_ft_v2_controle"]
        comparacao = resumo["comparacao_gol_ft_v2_controle_v3"]

        self.assertEqual(
            controle["candidatos_coorte"],
            TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
        )
        self.assertEqual(controle["total_disponivel"], 80)
        self.assertTrue(controle["coorte_fechada"])
        self.assertFalse(controle["historico_v2_reaberto"])
        self.assertEqual(
            controle["minimo_resultados_validos"],
            MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE,
        )
        self.assertEqual(
            comparacao["v3"]["candidatos_coorte"], 50
        )
        self.assertEqual(
            comparacao["sobreposicao"]["candidatos"], 50
        )
        self.assertEqual(
            comparacao["sobreposicao"]["apenas_v2_controle"], 25
        )
        self.assertEqual(
            comparacao["sobreposicao"]["apenas_v3"], 0
        )
        self.assertEqual(
            comparacao["sobreposicao"]["resultados_divergentes"], 0
        )
        self.assertEqual(
            comparacao["subgrupos_exclusivos"]["v2_controle"][
                "candidatos"
            ],
            25,
        )
        self.assertEqual(
            comparacao["subgrupos_exclusivos"]["v3"]["candidatos"], 0
        )
        self.assertFalse(
            comparacao["subgrupos_exclusivos"]["uso_para_sinais"]
        )
        self.assertFalse(comparacao["conclusao"]["alterar_regra_ativa"])
        self.assertTrue(comparacao["conclusao"]["manter_v2_em_sombra"])
        self.assertTrue(comparacao["conclusao"]["manter_v3_em_sombra"])
        self.assertEqual(
            comparacao["monitoramento_pos_coorte"]["v2_controle"][
                "candidatos"
            ],
            5,
        )
        self.assertEqual(
            comparacao["monitoramento_pos_coorte"]["v3"]["candidatos"], 0
        )
        self.assertFalse(
            comparacao["monitoramento_pos_coorte"][
                "altera_validacao_congelada"
            ]
        )
        conexao.close()

    def test_funil_explica_bloqueios_sem_afrouxar_a_regra(self):
        linhas = [
            {
                "partida_id": 1,
                "mercado": "gol_ft",
                "pontuacao_tecnica": 75,
                "odd": None,
                "motivos_json": json.dumps([
                    "bloqueio:atividade_recente_insuficiente_gols",
                    "bloqueio:historico_5min_insuficiente",
                    "bloqueio:odd_ao_vivo_indisponivel",
                ]),
                "features_json": json.dumps({"qualidade_dados": 90}),
            },
            {
                "partida_id": 2,
                "mercado": "gol_ft",
                "pontuacao_tecnica": 72,
                "odd": 1.8,
                "motivos_json": json.dumps([
                    "bloqueio:atividade_recente_insuficiente_gols",
                ]),
                "features_json": json.dumps({
                    "qualidade_dados": 90,
                    "idade_odds_segundos": 20,
                }),
            },
            {
                "partida_id": 2,
                "mercado": "gol_ft",
                "pontuacao_tecnica": 60,
                "odd": 1.9,
                "motivos_json": json.dumps([
                    "bloqueio:atividade_recente_insuficiente_gols",
                ]),
                "features_json": json.dumps({"qualidade_dados": 90}),
            },
        ]

        item = _resumir_funil_exploracao_gols_linhas(linhas)["gol_ft"]

        self.assertEqual(item["tentativas_rejeitadas"], 3)
        self.assertEqual(item["partidas_unicas"], 2)
        self.assertEqual(item["somente_atividade"], 2)
        self.assertEqual(item["pontuacao_elegivel"], 1)
        self.assertEqual(item["aptas_reconstruidas"], 1)
        self.assertEqual(
            item["bloqueios"]["historico_5min_insuficiente"], 1
        )

    def test_cria_experimento_asiatico_distinto_sem_envio(self):
        candidato = self.candidato(
            mercado="escanteios_ft_asiatico",
            bloqueios=[
                "linha_exige_multiplos_escanteios",
                "odd_ao_vivo_indisponivel",
            ],
            pontuacao_tecnica=80,
            qualidade_dados=95,
            linha=None,
            odd=None,
            features={
                "minuto": 60,
                "escanteios_atuais": 8,
                "janelas": {"5": {
                    "disponivel": True,
                    "escanteios_total": 1,
                    "chutes_total": 2,
                }},
            },
        )
        odds = {"ao_vivo": [{
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "fonte": "api_football",
            "ofertas": [{
                "linha": 10.5,
                "over": 1.85,
                "under": 1.95,
                "idade_segundos": 20,
            }],
        }]}

        sombra = criar_exploracao_asiatica_multiplos(candidato, odds)

        self.assertEqual(sombra["status"], "simulacao")
        self.assertEqual(sombra["linha"], 10.5)
        self.assertEqual(sombra["odd"], 1.85)
        self.assertIn(
            f"exploracao_sombra={VERSAO_EXPLORACAO_ASIATICA}",
            sombra["motivos"],
        )
        self.assertFalse(
            sombra["features"]["exploracao_sombra"][
                "aplicacao_automatica"
            ]
        )

    def test_asiatico_ignora_linha_substituida_da_mesma_casa(self):
        candidato = self.candidato(
            mercado="escanteios_ft_asiatico",
            bloqueios=[
                "linha_exige_multiplos_escanteios",
                "odd_ao_vivo_indisponivel",
            ],
            pontuacao_tecnica=80,
            qualidade_dados=95,
            linha=None,
            odd=None,
            features={
                "minuto": 63,
                "decisao_em": "2026-08-30T21:26:34-04:00",
                "escanteios_atuais": 8,
                "janelas": {"5": {
                    "disponivel": True,
                    "escanteios_total": 2,
                    "chutes_total": 2,
                }},
            },
        )
        comum = {
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "fonte": "betsapi",
            "bookmaker": "bet365",
        }
        odds = {"ao_vivo": [{
            **comum,
            "coletado_em": "2026-08-31T01:26:32+00:00",
            "cache": False,
            "ofertas": [{
                "linha": 11.0,
                "over": 1.95,
                "idade_segundos": 0.987,
                "coletado_em": "2026-08-31T01:26:32+00:00",
                "evento_externo_id": "199420703",
            }],
        }, {
            **comum,
            "coletado_em": "2026-08-31T01:19:49+00:00",
            "cache": True,
            "ofertas": [{
                "linha": 9.5,
                "over": 1.825,
                # A idade declarada pertencia ao instante da consulta antiga.
                "idade_segundos": 1.08,
                "coletado_em": "2026-08-31T01:19:49+00:00",
                "evento_externo_id": "199420703",
            }],
        }]}

        sombra = criar_exploracao_asiatica_multiplos(candidato, odds)

        self.assertEqual(sombra["linha"], 11.0)
        self.assertEqual(sombra["odd"], 1.95)
        self.assertEqual(
            sombra["features"]["coletado_em_odds"],
            "2026-08-31T01:26:32+00:00",
        )
        self.assertAlmostEqual(
            sombra["features"]["idade_odds_segundos"], 2.0, places=3
        )

    def test_asiatico_prefere_fonte_fresca_a_linha_menor_vencida(self):
        candidato = self.candidato(
            mercado="escanteios_ft_asiatico",
            bloqueios=[
                "linha_exige_multiplos_escanteios",
                "odd_ao_vivo_indisponivel",
            ],
            pontuacao_tecnica=82,
            qualidade_dados=95,
            linha=None,
            odd=None,
            features={
                "minuto": 60,
                "escanteios_atuais": 8,
                "janelas": {"5": {
                    "disponivel": True,
                    "escanteios_total": 1,
                    "chutes_total": 3,
                }},
            },
        )
        comum = {
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
        }
        odds = {"ao_vivo": [{
            **comum,
            "fonte": "api_football",
            "ofertas": [{
                "linha": 9.5, "over": 1.80,
                "idade_segundos": 120,
            }],
        }, {
            **comum,
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "ofertas": [{
                "linha": 10.5, "over": 1.90,
                "idade_segundos": 5,
            }],
        }]}

        sombra = criar_exploracao_asiatica_multiplos(candidato, odds)

        self.assertEqual(sombra["linha"], 10.5)
        self.assertEqual(sombra["odd"], 1.90)
        self.assertEqual(sombra["features"]["fonte_odds"], "betsapi")
        self.assertEqual(sombra["features"]["idade_odds_segundos"], 5)

    def test_experimento_asiatico_rejeita_gap_ou_dado_inseguro(self):
        base = self.candidato(
            mercado="escanteios_ft_asiatico",
            bloqueios=[
                "linha_exige_multiplos_escanteios",
                "odd_ao_vivo_indisponivel",
            ],
            pontuacao_tecnica=80,
            qualidade_dados=95,
            linha=None,
            odd=None,
            features={
                "minuto": 60,
                "escanteios_atuais": 8,
                "janelas": {"5": {
                    "disponivel": True,
                    "escanteios_total": 1,
                    "chutes_total": 2,
                }},
            },
        )
        odds_gap_longo = {"ao_vivo": [{
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "ofertas": [{"linha": 13, "over": 1.85}],
        }]}
        odds_gap_valido = {"ao_vivo": [{
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "ofertas": [{"linha": 10.5, "over": 1.85}],
        }]}
        sem_janela = {
            **base,
            "features": {**base["features"], "janelas": {}},
        }
        bloqueio_extra = {
            **base,
            "bloqueios": [
                "linha_exige_multiplos_escanteios",
                "odd_ao_vivo_indisponivel",
                "odds_desatualizadas",
            ],
        }

        self.assertIsNone(criar_exploracao_asiatica_multiplos(
            base, odds_gap_longo
        ))
        self.assertIsNone(
            criar_exploracao_asiatica_multiplos(
                sem_janela, odds_gap_valido
            )
        )
        self.assertIsNone(
            criar_exploracao_asiatica_multiplos(
                bloqueio_extra, odds_gap_valido
            )
        )


if __name__ == "__main__":
    unittest.main()
