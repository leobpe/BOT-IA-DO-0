import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import ANY, patch

from avaliacao_portfolio_edge import (
    _carregar_metodo_entregue,
    _carregar_sinais_binarios_entregues,
    _decidir,
    _avaliar_mercado_binario,
    _avaliar_braco_metodo,
    _resumir_asiatico,
    _resumir_portfolio_gols,
    avaliar,
    avaliar_candidato_oficial,
)
from gols_antecipados import (
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
    VERSAO_GOL_HT_ANTECIPADO,
)
from filtro_gol_ft_antecipado_preciso import (
    VERSAO as VERSAO_FILTRO_GOL_FT_PRECISO,
)


class AvaliacaoPortfolioEdgeTest(unittest.TestCase):
    @patch("avaliacao_portfolio_edge._avaliar_mercado_binario")
    def test_gate_candidato_oficial_usa_versao_exata_e_exige_edge(
        self, avaliar_binario
    ):
        avaliar_binario.return_value = {
            "coorte_operacional_avaliada": "entregue_confirmado",
            "decisao": {
                "estado": "vantagem_nao_replicada_holdout",
                "criterios": {"holdout_minimo": True},
                "todos_satisfeitos": False,
            },
        }

        resultado = avaliar_candidato_oficial(object(), {
            "mercado": "proximo_gol",
            "regra_versao": "regra-exata-v7",
        })

        avaliar_binario.assert_called_once_with(
            ANY, "proximo_gol", "regra-exata-v7"
        )
        self.assertFalse(resultado["apto"])
        self.assertEqual("edge_nao_comprovado", resultado["estado"])
        self.assertEqual(
            "vantagem_nao_replicada_holdout", resultado["motivo"]
        )
        self.assertFalse(resultado["promocao_automatica"])

    @patch("avaliacao_portfolio_edge._resumir_asiatico")
    def test_gate_candidato_oficial_aceita_asiatico_so_com_todos_criterios(
        self, avaliar_asiatico_gate
    ):
        avaliar_asiatico_gate.return_value = {
            "coorte_operacional_avaliada": "oficial_entregue",
            "decisao": {
                "estado": "favoravel_para_revisao_manual",
                "criterios": {"holdout_minimo": True},
                "todos_satisfeitos": True,
            },
        }

        resultado = avaliar_candidato_oficial(object(), {
            "mercado": "escanteios_ft_asiatico",
            "regra_versao": "asiatico-v9",
        })

        avaliar_asiatico_gate.assert_called_once_with(
            ANY, "asiatico-v9"
        )
        self.assertTrue(resultado["apto"])
        self.assertEqual("edge_comprovado", resultado["estado"])

    def test_gate_candidato_oficial_falha_fechado_sem_avaliador(self):
        resultado = avaliar_candidato_oficial(object(), {
            "mercado": "escanteios_2t",
            "regra_versao": "periodo-sem-fonte-v1",
        })

        self.assertFalse(resultado["apto"])
        self.assertEqual("mercado_sem_gate_edge", resultado["estado"])

    @patch("avaliacao_portfolio_edge.avaliar_coorte")
    @patch("avaliacao_portfolio_edge._carregar_metodo_entregue")
    def test_braco_metodo_exige_edge_sem_vig_no_holdout(
        self, carregar, avaliar_preco
    ):
        carregar.return_value = (
            [{"id": indice} for indice in range(100)],
            {
                "estado": "carregada",
                "linhas_divergentes": 0,
                "linhas_invalidas": 0,
                "resultados_independentes_completos": True,
            },
        )

        def resumo(_conexao, itens):
            tamanho = len(list(itens))
            holdout = tamanho == 30
            return {
                "tamanho_coorte": tamanho,
                "cobertura_referencia_sem_vig": tamanho,
                "taxa_cobertura": 1.0,
                "exclusoes": {},
                "metricas": {
                    "amostra": tamanho,
                    "ic95_roi": (
                        [-0.12, 0.08] if holdout else [0.02, 0.20]
                    ),
                    "ic95_desvio_observado_menos_mercado": (
                        [-0.08, 0.10] if holdout else [0.01, 0.15]
                    ),
                },
                "por_faixa_probabilidade_mercado": {},
                "itens": [],
            }

        avaliar_preco.side_effect = resumo
        resultado = _avaliar_braco_metodo(
            object(),
            identificador="metodo",
            mercado="gol_ht",
            versao="metodo-v1",
            resumo={
                "decisao_estatistica": "favoravel_para_revisao",
                "linhagem_homogenea": True,
            },
            registrado_em="2026-01-01T00:00:00",
            linhagem_sha256="sha",
            linhagem_caminho="metodo.sha",
        )

        self.assertEqual(
            "vantagem_nao_comprovada", resultado["decisao"]["estado"]
        )
        self.assertFalse(resultado["decisao"]["todos_satisfeitos"])
        self.assertFalse(
            resultado["decisao"]["criterios"][
                "roi_preco_holdout_ic95_inferior_positivo"
            ]
        )

    @patch("avaliacao_portfolio_edge.avaliar_coorte")
    def test_mercado_binario_decide_so_por_entrada_entregue(
        self, avaliar_preco
    ):
        conexao = sqlite3.connect(":memory:")
        self.addCleanup(conexao.close)
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id INTEGER,
              snapshot_id INTEGER, criado_em TEXT, mercado TEXT,
              linha REAL, odd REAL, probabilidade_calibrada REAL,
              status TEXT, regra_versao TEXT, features_json TEXT
            );
            CREATE TABLE snapshots (id INTEGER PRIMARY KEY, placar TEXT);
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER, resultado TEXT, retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas (
              sinal_id INTEGER, status TEXT, canal TEXT
            );
            INSERT INTO snapshots VALUES (1, '0-0'), (2, '0-0');
            INSERT INTO sinais VALUES
              (1,10,1,'2026-01-01T10:00:00','proximo_gol',NULL,1.8,
               NULL,'aprovado','regra-v1','{}'),
              (2,20,2,'2026-01-01T10:01:00','proximo_gol',NULL,1.8,
               NULL,'simulacao','regra-v1','{}');
            INSERT INTO resultados_sinais VALUES
              (1,'green',0.8),(2,'red',-1.0);
            INSERT INTO entregas_alertas VALUES
              (2,'entregue','telegram:gols:teste');
            """
        )

        def resumo(_conexao, itens):
            tamanho = len(list(itens))
            return {
                "tamanho_coorte": tamanho,
                "cobertura_referencia_sem_vig": tamanho,
                "taxa_cobertura": 1.0 if tamanho else None,
                "exclusoes": {},
                "metricas": {
                    "amostra": tamanho,
                    "ic95_roi": None,
                    "ic95_desvio_observado_menos_mercado": None,
                },
                "por_faixa_probabilidade_mercado": {},
                "itens": [],
            }

        avaliar_preco.side_effect = resumo
        resultado = _avaliar_mercado_binario(
            conexao, "proximo_gol", "regra-v1"
        )

        self.assertEqual(
            "entregue_confirmado",
            resultado["coorte_operacional_avaliada"],
        )
        self.assertEqual(1, resultado["coorte_entregue"]["tamanho_coorte"])
        self.assertEqual(1, resultado["resolvidas_entregues_consultadas"])
        self.assertEqual(
            1, resultado["decisao"]["criterios"]["coorte_presente"]
        )

    def test_metodo_entregue_deduplica_depois_do_filtro_de_entrega(self):
        conexao = sqlite3.connect(":memory:")
        self.addCleanup(conexao.close)
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id INTEGER,
              snapshot_id INTEGER, criado_em TEXT, mercado TEXT,
              linha REAL, odd REAL, status TEXT, features_json TEXT
            );
            CREATE TABLE snapshots (id INTEGER PRIMARY KEY, placar TEXT);
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER, resultado TEXT, retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas (
              sinal_id INTEGER, status TEXT, canal TEXT
            );
            INSERT INTO snapshots VALUES (1, '0-0'), (2, '0-0');
            """
        )
        features = json.dumps({
            "exploracao_sombra": {"versao": "metodo-v1"},
            "gol_antecipado": {"linhagem_sha256": "sha-ok"},
        })
        conexao.executemany(
            "INSERT INTO sinais VALUES (?, 10, ?, ?, 'gol_ft', 0.5, "
            "1.8, 'simulacao', ?)",
            [
                (1, 1, "2026-01-01T10:00:00", features),
                (2, 2, "2026-01-01T10:01:00", features),
            ],
        )
        conexao.executemany(
            "INSERT INTO resultados_sinais VALUES (?, 'green', 0.8)",
            [(1,), (2,)],
        )
        conexao.execute(
            "INSERT INTO entregas_alertas VALUES "
            "(2, 'entregue', 'telegram:gols:teste')"
        )

        sinais, auditoria = _carregar_metodo_entregue(
            conexao,
            mercado="gol_ft",
            versao="metodo-v1",
            registrado_em="2026-01-01T00:00:00",
            linhagem_caminho="gol_antecipado.linhagem_sha256",
            linhagem_sha256="sha-ok",
        )

        self.assertEqual([2], [item["id"] for item in sinais])
        self.assertEqual(1, auditoria["candidatos_independentes"])

    def test_metodo_nao_substitui_primeira_entrega_pendente(self):
        conexao = sqlite3.connect(":memory:")
        self.addCleanup(conexao.close)
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id INTEGER,
              snapshot_id INTEGER, criado_em TEXT, mercado TEXT,
              linha REAL, odd REAL, status TEXT, features_json TEXT
            );
            CREATE TABLE snapshots (id INTEGER PRIMARY KEY, placar TEXT);
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER, resultado TEXT, retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas (
              sinal_id INTEGER, status TEXT, canal TEXT
            );
            INSERT INTO snapshots VALUES (1, '0-0'), (2, '0-0');
            """
        )
        features = json.dumps({
            "exploracao_sombra": {"versao": "metodo-v1"},
            "gol_antecipado": {"linhagem_sha256": "sha-ok"},
        })
        conexao.executemany(
            "INSERT INTO sinais VALUES (?, 10, ?, ?, 'gol_ft', 0.5, "
            "1.8, 'simulacao', ?)",
            [
                (1, 1, "2026-01-01T10:00:00", features),
                (2, 2, "2026-01-01T10:01:00", features),
            ],
        )
        conexao.execute(
            "INSERT INTO resultados_sinais VALUES (2, 'green', 0.8)"
        )
        conexao.executemany(
            "INSERT INTO entregas_alertas VALUES "
            "(?, 'entregue', 'telegram:gols:teste')",
            [(1,), (2,)],
        )

        sinais, auditoria = _carregar_metodo_entregue(
            conexao,
            mercado="gol_ft",
            versao="metodo-v1",
            registrado_em="2026-01-01T00:00:00",
            linhagem_caminho="gol_antecipado.linhagem_sha256",
            linhagem_sha256="sha-ok",
        )

        self.assertEqual([], sinais)
        self.assertEqual(1, auditoria["candidatos_independentes"])
        self.assertEqual(1, auditoria["linhas_sem_resultado_valido"])
        self.assertFalse(
            auditoria["resultados_independentes_completos"]
        )

    def test_coorte_base_fixa_primeira_entrega_antes_do_resultado(self):
        conexao = sqlite3.connect(":memory:")
        self.addCleanup(conexao.close)
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id INTEGER,
              snapshot_id INTEGER, criado_em TEXT, mercado TEXT,
              linha REAL, odd REAL, probabilidade_calibrada REAL,
              status TEXT, regra_versao TEXT, features_json TEXT
            );
            CREATE TABLE snapshots (id INTEGER PRIMARY KEY, placar TEXT);
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER, resultado TEXT, retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas (
              sinal_id INTEGER, status TEXT, canal TEXT
            );
            INSERT INTO snapshots VALUES (1, '0-0'), (2, '0-0');
            INSERT INTO sinais VALUES
              (1,10,1,'2026-01-01T10:00:00','proximo_gol','casa',1.8,
               NULL,'simulacao','regra-v1','{}'),
              (2,10,2,'2026-01-01T10:01:00','proximo_gol','casa',1.8,
               NULL,'simulacao','regra-v1','{}');
            INSERT INTO resultados_sinais VALUES (2,'green',0.8);
            INSERT INTO entregas_alertas VALUES
              (1,'entregue','telegram:gols:teste'),
              (2,'entregue','telegram:gols:teste');
            """
        )

        sinais, auditoria = _carregar_sinais_binarios_entregues(
            conexao, "proximo_gol", "regra-v1"
        )

        self.assertEqual([], sinais)
        coorte = auditoria["por_coorte"]["simulacao"]
        self.assertEqual(1, coorte["candidatos_coorte_fixa"])
        self.assertEqual(1, coorte["linhas_sem_resultado_valido"])
        self.assertFalse(coorte["resultados_independentes_completos"])

    def test_coorte_base_congela_primeiras_cem_partidas(self):
        conexao = sqlite3.connect(":memory:")
        self.addCleanup(conexao.close)
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id INTEGER,
              snapshot_id INTEGER, criado_em TEXT, mercado TEXT,
              linha REAL, odd REAL, probabilidade_calibrada REAL,
              status TEXT, regra_versao TEXT, features_json TEXT
            );
            CREATE TABLE snapshots (id INTEGER PRIMARY KEY, placar TEXT);
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER, resultado TEXT, retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas (
              sinal_id INTEGER, status TEXT, canal TEXT
            );
            """
        )
        inicio = datetime(2026, 1, 1, 10, 0, 0)
        ids = list(range(1, 102))
        conexao.executemany(
            "INSERT INTO snapshots VALUES (?, '0-0')",
            [(identificador,) for identificador in ids],
        )
        conexao.executemany(
            "INSERT INTO sinais VALUES (?,?,?,?, 'proximo_gol','casa',"
            "1.8,NULL,'simulacao','regra-v1','{}')",
            [
                (
                    identificador, 1000 + identificador, identificador,
                    (inicio + timedelta(minutes=identificador)).isoformat(),
                )
                for identificador in ids
            ],
        )
        conexao.executemany(
            "INSERT INTO resultados_sinais VALUES (?, 'green', 0.8)",
            [(identificador,) for identificador in ids],
        )
        conexao.executemany(
            "INSERT INTO entregas_alertas VALUES "
            "(?, 'entregue', 'telegram:gols:teste')",
            [(identificador,) for identificador in ids],
        )

        sinais, auditoria = _carregar_sinais_binarios_entregues(
            conexao, "proximo_gol", "regra-v1"
        )

        coorte = auditoria["por_coorte"]["simulacao"]
        self.assertEqual(101, coorte["candidatos_independentes_total"])
        self.assertEqual(100, coorte["candidatos_coorte_fixa"])
        self.assertEqual(1, coorte["ignorados_apos_coorte_fixa"])
        self.assertEqual(70, coorte["unidades_desenvolvimento"])
        self.assertEqual(30, coorte["unidades_holdout"])
        self.assertEqual(100, len(sinais))
        self.assertNotIn(101, {item["id"] for item in sinais})

    @patch("avaliacao_portfolio_edge.avaliar_coorte")
    @patch("avaliacao_portfolio_edge._carregar_sinais_binarios_entregues")
    @patch("avaliacao_portfolio_edge._carregar_sinais")
    def test_mercado_binario_nao_mistura_oficial_e_sombra(
        self, carregar_historico, carregar_entregues, avaliar_preco
    ):
        carregar_historico.return_value = ([], {
            "linhas_resultado_valido_brutas": 0,
            "linhas_invalidas": 0,
        })
        carregar_entregues.return_value = (
            [
                {
                    "id": 1, "_coorte_portfolio": "aprovado",
                    "_particao_portfolio": "desenvolvimento",
                },
                {
                    "id": 2, "_coorte_portfolio": "sombra:teste-v1",
                    "_particao_portfolio": "desenvolvimento",
                },
            ],
            {
                "por_coorte": {
                    nome: {
                        "candidatos_coorte_fixa": 1,
                        "linhas_resultado_valido": 1,
                        "linhas_sem_resultado_valido": 0,
                        "linhas_invalidas": 0,
                        "resultados_independentes_completos": True,
                        "dados_resultados_validos": True,
                    }
                    for nome in ("aprovado", "sombra:teste-v1")
                },
            },
        )

        def resumo(_conexao, itens):
            tamanho = len(list(itens))
            return {
                "tamanho_coorte": tamanho,
                "taxa_cobertura": 1.0 if tamanho else None,
                "metricas": {"amostra": tamanho},
                "itens": [],
            }

        avaliar_preco.side_effect = resumo

        resultado = _avaliar_mercado_binario(
            object(), "proximo_gol", "regra-v1"
        )

        self.assertEqual("aprovado", resultado["coorte_selecao_avaliada"])
        self.assertEqual(1, resultado["coorte_entregue"]["tamanho_coorte"])
        self.assertEqual(
            {"aprovado", "sombra:teste-v1"},
            set(resultado["coortes_entregues"]),
        )

    def test_decisao_exige_amostra_preco_roi_e_residuo(self):
        metricas = {
            "amostra": 100,
            "ic95_roi": [0.01, 0.20],
            "ic95_desvio_observado_menos_mercado": [0.005, 0.10],
        }

        decisao = _decidir(
            metricas,
            0.95,
            metricas_holdout={
                "amostra": 30,
                "ic95_roi": [0.01, 0.20],
                "ic95_desvio_observado_menos_mercado": [0.005, 0.10],
            },
            taxa_cobertura_holdout=0.95,
        )

        self.assertTrue(decisao["todos_satisfeitos"])
        self.assertEqual(
            "favoravel_para_revisao_manual", decisao["estado"]
        )
        self.assertFalse(decisao["promocao_automatica"])

    def test_decisao_bloqueia_primeira_unidade_pendente(self):
        metricas = {
            "amostra": 100,
            "ic95_roi": [0.01, 0.20],
            "ic95_desvio_observado_menos_mercado": [0.005, 0.10],
        }

        decisao = _decidir(
            metricas,
            1.0,
            metricas_holdout={
                "amostra": 30,
                "ic95_roi": [0.01, 0.20],
                "ic95_desvio_observado_menos_mercado": [0.005, 0.10],
            },
            taxa_cobertura_holdout=1.0,
            resultados_independentes_completos=False,
        )

        self.assertEqual(
            "aguardando_resultados_independentes", decisao["estado"]
        )
        self.assertFalse(decisao["todos_satisfeitos"])

    def test_decisao_nao_aceita_roi_pontual_sem_ic_positivo(self):
        metricas = {
            "amostra": 150,
            "roi": 0.20,
            "ic95_roi": [-0.01, 0.41],
            "ic95_desvio_observado_menos_mercado": [0.01, 0.20],
        }

        decisao = _decidir(
            metricas,
            1.0,
            metricas_holdout={
                "amostra": 45,
                "ic95_roi": [0.02, 0.30],
                "ic95_desvio_observado_menos_mercado": [0.01, 0.20],
            },
            taxa_cobertura_holdout=1.0,
        )

        self.assertFalse(decisao["todos_satisfeitos"])
        self.assertEqual("vantagem_nao_comprovada", decisao["estado"])

    def test_decisao_exige_replicacao_do_edge_no_holdout(self):
        decisao = _decidir(
            {
                "amostra": 120,
                "ic95_roi": [0.03, 0.20],
                "ic95_desvio_observado_menos_mercado": [0.01, 0.15],
            },
            1.0,
            metricas_holdout={
                "amostra": 36,
                "ic95_roi": [-0.20, 0.15],
                "ic95_desvio_observado_menos_mercado": [-0.10, 0.12],
            },
            taxa_cobertura_holdout=1.0,
        )

        self.assertFalse(decisao["todos_satisfeitos"])
        self.assertEqual(
            "vantagem_nao_replicada_holdout", decisao["estado"]
        )
        self.assertFalse(
            decisao["criterios"]["roi_holdout_ic95_inferior_positivo"]
        )

    @patch("avaliacao_portfolio_edge.avaliar_asiatico")
    def test_asiatico_usa_entradas_entregues_como_populacao(self, avaliador):
        avaliador.return_value = {
            "resolvidas_consultadas": 20,
            "por_coorte": {"oficial": {"amostra": 20}},
            "oficial_elegivel": {"amostra": 20},
            "oficial_entregue": {"amostra": 7},
            "divisao_cronologica_oficial_entregue": {
                "holdout_30": {"amostra": 2},
            },
            "oficial_entregue_por_tipo_linha": {},
            "revisao_operacional": {
                "decisao": "nao_pronto_para_alteracao_operacional",
                "criterios": {"amostra_oficial_entregue_minima": False},
                "todos_satisfeitos": False,
            },
        }

        resumo = _resumir_asiatico(object(), "regra")

        self.assertEqual("oficial_entregue", resumo["coorte_operacional_avaliada"])
        self.assertEqual(7, resumo["metricas_oficiais"]["amostra"])
        self.assertEqual(20, resumo["metricas_oficiais_elegiveis"]["amostra"])

    @patch(
        "avaliacao_portfolio_edge.resumir_validacao_escanteios_ft_asiatico"
    )
    @patch("avaliacao_portfolio_edge.avaliar_asiatico")
    def test_asiatico_ancorado_decide_so_pela_coorte_prospectiva(
        self, historico, prospectiva
    ):
        historico.return_value = {
            "oficial_entregue": {"amostra": 999, "roi": 9.0},
            "revisao_operacional": {
                "decisao": "favoravel_para_revisao_manual",
                "todos_satisfeitos": True,
            },
        }
        prospectiva.return_value = {
            "saudavel": True,
            "estado": "coletando",
            "decisao": "aguardando_amostra_futura",
            "regra_versao": "regra-fixa",
            "apto_revisao": False,
            "coorte_fechada": False,
            "resultados_completos": False,
            "validos": 0,
            "taxa_resultado_positivo": None,
            "intervalo_roi_95": None,
            "desenvolvimento": {},
            "holdout": {},
            "gate_preco_sem_vig": {"satisfeito": False},
        }

        resumo = _resumir_asiatico(
            object(), "regra-fixa", {"saudavel": True, "ativo": True}
        )

        self.assertEqual(
            "prospectiva_executavel_betsapi_bet365_pos_ancora",
            resumo["coorte_operacional_avaliada"],
        )
        self.assertFalse(resumo["decisao"]["todos_satisfeitos"])
        self.assertFalse(resumo["historico_pre_ancora_entra_na_decisao"])
        self.assertEqual(
            999,
            resumo["coortes"]["historico_pre_ancora_diagnostico"]
            ["metricas_oficiais"]["amostra"],
        )

    @patch("avaliacao_portfolio_edge._avaliar_mercado_binario")
    @patch("avaliacao_portfolio_edge._resumir_asiatico")
    def test_portfolio_nunca_promove_automaticamente(
        self, asiatico, binario
    ):
        binario.return_value = {
            "regra_versao": "v1",
            "decisao": {
                "todos_satisfeitos": True,
                "promocao_automatica": False,
            },
        }
        asiatico.return_value = {
            "regra_versao": "v2",
            "decisao": {
                "todos_satisfeitos": False,
                "promocao_automatica": False,
            },
        }

        resumo = avaliar(
            object(),
            mercados=("gol_ft", "escanteios_ft_asiatico"),
            regras_por_mercado={
                "gol_ft": "v1", "escanteios_ft_asiatico": "v2"
            },
        )

        self.assertEqual(
            ["gol_ft"], resumo["mercados_favoraveis_para_revisao_manual"]
        )
        self.assertFalse(resumo["todos_mercados_com_edge_comprovado"])
        self.assertFalse(resumo["alteracao_filtros"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["promocao_automatica"])
        self.assertEqual(
            "avaliacao-edge-escanteios-asiaticos-v3",
            resumo[
                "versao_avaliacao_historica_escanteios_asiaticos"
            ],
        )

    @patch("avaliacao_portfolio_edge._resumir_portfolio_gols")
    @patch("avaliacao_portfolio_edge._resumos_validadores_gols")
    def test_portfolio_gols_usa_metodos_ativos_quando_recebe_recursos(
        self, validadores, resumir_gols
    ):
        validadores.return_value = {"qualquer": "resumo"}
        resumir_gols.return_value = {
            "regra_versao": "portfolio-gol-ft-metodos-ativos-v1",
            "decisao": {
                "todos_satisfeitos": False,
                "promocao_automatica": False,
            },
        }

        resumo = avaliar(
            object(),
            mercados=("gol_ft",),
            recursos={"gols_antecipados_grupo": True},
            controle_v2b_ft={"saudavel": True, "ativo": True},
        )

        resumir_gols.assert_called_once()
        self.assertEqual(
            "portfolio-gol-ft-metodos-ativos-v1",
            resumo["regras_por_mercado"]["gol_ft"],
        )

    def test_v2b_ft_inativo_no_breaker_nao_entra_no_portfolio(self):
        resumo = _resumir_portfolio_gols(
            object(),
            "gol_ft",
            {
                "gols_antecipados_grupo": False,
                "gol_ft_capacidade_contextual_v2_grupo": True,
                "top_criterios_gols_grupo": False,
            },
            {"saudavel": True, "ativo": False},
            {
                "antecipados": {},
                "capacidade_v2_ft_grupo": {},
                "top": {},
            },
        )

        self.assertIsNone(resumo)

    @patch("avaliacao_portfolio_edge._avaliar_mercado_binario")
    @patch("avaliacao_portfolio_edge._avaliar_braco_metodo")
    def test_portfolio_expoe_metodo_antecipado_suspenso_sem_avalia_lo(
        self, avaliar_braco, avaliar_base
    ):
        avaliar_base.return_value = {"decisao": {}}

        resumo = _resumir_portfolio_gols(
            object(),
            "gol_ht",
            {
                "gols_antecipados_grupo": True,
                "gol_ht_00_min20_grupo": False,
                "gol_ht_capacidade_contextual_v2_grupo": False,
                "top_criterios_gols_grupo": False,
            },
            {},
            {
                "antecipados": {
                    "registrado_em": "2026-01-01T00:00:00",
                    "linhagem_sha256": "sha",
                    "por_braco": {VERSAO_GOL_HT_ANTECIPADO: {}},
                },
                "capacidade_v2": {},
                "ht_00_min20": {},
                "top": {},
            },
            controle_gols_antecipados={
                "saudavel": True,
                "estado": "ok",
                "metodos": {
                    VERSAO_GOL_HT_ANTECIPADO: {
                        "ativo": False,
                        "estado": "suspenso",
                        "motivo": "evidencia_desfavoravel",
                    }
                },
            },
        )

        avaliar_braco.assert_not_called()
        self.assertEqual([], resumo["metodos_ativos"])
        self.assertEqual(1, len(resumo["metodos_bloqueados"]))
        self.assertEqual(
            "sem_metodos_ativos", resumo["decisao"]["estado"]
        )
        self.assertFalse(resumo["decisao"]["promocao_automatica"])

    @patch("avaliacao_portfolio_edge._avaliar_mercado_binario")
    @patch("avaliacao_portfolio_edge._avaliar_braco_metodo")
    def test_ht_preciso_substitui_coorte_legada_no_portfolio(
        self, avaliar_braco, avaliar_base
    ):
        avaliar_base.return_value = {"decisao": {}}
        resumo = _resumir_portfolio_gols(
            object(),
            "gol_ht",
            {
                "gols_antecipados_grupo": True,
                "filtro_gol_ht_antecipado_preciso": True,
                "gol_ht_00_min20_grupo": False,
                "gol_ht_capacidade_contextual_v2_grupo": False,
                "top_criterios_gols_grupo": False,
            },
            {},
            {
                "antecipados": {
                    "registrado_em": "2026-01-01T00:00:00",
                    "linhagem_sha256": "sha",
                    "por_braco": {VERSAO_GOL_HT_ANTECIPADO: {}},
                },
                "ht_antecipado_preciso": {
                    "versao_filtro": "filtro-ht-preciso-v1",
                    "saudavel": True,
                    "candidatos": 12,
                    "validos": 11,
                    "resultados_completos": False,
                    "decisao": "aguardando_amostra_futura",
                    "apto_revisao": False,
                    "gate_preco_conservador": {"satisfeito": False},
                },
                "capacidade_v2": {},
                "ht_00_min20": {},
                "top": {},
            },
            controle_gols_antecipados={
                "saudavel": True,
                "metodos": {
                    VERSAO_GOL_HT_ANTECIPADO: {"ativo": True}
                },
            },
            controle_filtro_gol_ht_preciso={
                "saudavel": True, "ativo": True,
            },
        )

        avaliar_braco.assert_not_called()
        self.assertEqual(
            ["ht_antecipado_preciso"],
            [
                item["identificador"]
                for item in resumo["metodos_ativos"]
            ],
        )
        self.assertEqual(
            "aguardando_amostra", resumo["decisao"]["estado"]
        )

    @patch("avaliacao_portfolio_edge._avaliar_mercado_binario")
    @patch("avaliacao_portfolio_edge._avaliar_braco_metodo")
    def test_ft_antecipado_avalia_os_dois_bracos_reais(
        self, avaliar_braco, avaliar_base
    ):
        avaliar_braco.return_value = {
            "decisao": {
                "estado": "aguardando_amostra",
                "todos_satisfeitos": False,
            },
        }
        avaliar_base.return_value = {"decisao": {}}
        resumo_antecipados = {
            "registrado_em": "2026-01-01T00:00:00",
            "linhagem_sha256": "sha",
            "por_braco": {
                VERSAO_GOL_FT_ANTECIPADO: {},
                VERSAO_GOL_FT_ANTECIPADO_2T: {},
            },
        }

        resumo = _resumir_portfolio_gols(
            object(),
            "gol_ft",
            {
                "gols_antecipados_grupo": True,
                "gol_ft_capacidade_contextual_v2_grupo": False,
                "top_criterios_gols_grupo": False,
            },
            {},
            {
                "antecipados": resumo_antecipados,
                "capacidade_v2_ft_grupo": {},
                "top": {},
            },
        )

        versoes = {
            chamada.kwargs["versao"]
            for chamada in avaliar_braco.call_args_list
        }
        self.assertEqual(
            {VERSAO_GOL_FT_ANTECIPADO, VERSAO_GOL_FT_ANTECIPADO_2T},
            versoes,
        )
        self.assertEqual(2, len(resumo["metodos_ativos"]))
        self.assertFalse(resumo["decisao"]["promocao_automatica"])

    @patch("avaliacao_portfolio_edge._avaliar_mercado_binario")
    @patch("avaliacao_portfolio_edge._avaliar_braco_metodo")
    def test_ft_preciso_substitui_somente_braco_2t_legado(
        self, avaliar_braco, avaliar_base
    ):
        avaliar_braco.return_value = {
            "identificador": "ft_antecipado_1t",
            "decisao": {
                "estado": "aguardando_amostra",
                "todos_satisfeitos": False,
            },
        }
        avaliar_base.return_value = {"decisao": {}}
        resumo = _resumir_portfolio_gols(
            object(),
            "gol_ft",
            {
                "gols_antecipados_grupo": True,
                "filtro_gol_ft_antecipado_preciso": True,
                "gol_ft_capacidade_contextual_v2_grupo": False,
                "top_criterios_gols_grupo": False,
            },
            {},
            {
                "antecipados": {
                    "registrado_em": "2026-01-01T00:00:00",
                    "linhagem_sha256": "sha",
                    "por_braco": {
                        VERSAO_GOL_FT_ANTECIPADO: {},
                        VERSAO_GOL_FT_ANTECIPADO_2T: {},
                    },
                },
                "ft_antecipado_preciso": {
                    "versao_filtro": VERSAO_FILTRO_GOL_FT_PRECISO,
                    "saudavel": True,
                    "candidatos": 7,
                    "validos": 6,
                    "resultados_completos": False,
                    "decisao": "aguardando_amostra_futura",
                    "apto_revisao": False,
                    "gate_preco_conservador": {"satisfeito": False},
                },
                "capacidade_v2_ft_grupo": {},
                "top": {},
            },
            controle_gols_antecipados={
                "saudavel": True,
                "metodos": {
                    VERSAO_GOL_FT_ANTECIPADO: {"ativo": True},
                    VERSAO_GOL_FT_ANTECIPADO_2T: {"ativo": True},
                },
            },
            controle_filtro_gol_ft_preciso={
                "saudavel": True, "ativo": True,
            },
        )

        self.assertEqual(
            ["ft_antecipado_1t"],
            [
                chamada.kwargs["identificador"]
                for chamada in avaliar_braco.call_args_list
            ],
        )
        self.assertEqual(
            ["ft_antecipado_1t", "ft_antecipado_2t_preciso"],
            [item["identificador"] for item in resumo["metodos_ativos"]],
        )
        preciso = resumo["metodos_ativos"][1]
        self.assertEqual(
            VERSAO_FILTRO_GOL_FT_PRECISO, preciso["versao_metodo"]
        )
        self.assertEqual("aguardando_amostra", preciso["decisao"]["estado"])


if __name__ == "__main__":
    unittest.main()
