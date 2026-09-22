import json
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from avaliacao_quarentena_fallback_ht import (
    CHAVE_ANCORA,
    CHAVE_ANCORA_LEGADA,
    MOTIVO_CONTROLE,
    MOTIVO_QUARENTENA,
    REGRA_VERSAO_ALVO,
    TAMANHO_COORTE,
    TAMANHO_DESENVOLVIMENTO,
    TAMANHO_HOLDOUT,
    VERSAO,
    avaliar_quarentena_fallback_ht,
)
from tendencias_packball_ligas import VERSAO_QUARENTENA_FALLBACK_HT


class AvaliacaoQuarentenaFallbackHTTest(unittest.TestCase):
    def setUp(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
            CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                criado_em TEXT, linha TEXT, odd REAL, status TEXT,
                regra_versao TEXT, mercado TEXT, features_json TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY, resultado TEXT,
                retorno_unidades REAL
            );
        """)
        self.banco = SimpleNamespace(conexao=conexao)

    def tearDown(self):
        self.banco.conexao.close()

    def _inserir(
        self, identificador, partida, criado_em, linha, motivo,
        resultado=None, retorno=None, politica=False, status="simulacao",
        odd=1.8,
    ):
        protecao = {"motivo": motivo}
        if politica:
            protecao["politica_fallback_ht"] = {
                "versao": VERSAO_QUARENTENA_FALLBACK_HT,
            }
        features = {"protecao_tendencias_packball": protecao}
        self.banco.conexao.execute(
            """
            INSERT INTO sinais (
                id, partida_id, criado_em, linha, odd, status,
                regra_versao, mercado, features_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'gol_ht', ?)
            """,
            (
                identificador, partida, criado_em, str(linha), odd,
                status, REGRA_VERSAO_ALVO,
                json.dumps(features),
            ),
        )
        if resultado is not None:
            self.banco.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?)",
                (identificador, resultado, retorno),
            )
        self.banco.conexao.commit()

    def test_coorte_deduplica_jogo_e_permanece_sem_autorizacao(self):
        ancora = "2026-09-01T20:00:00"
        self._inserir(
            1, 10, "2026-09-01T19:00:00", 1.5,
            MOTIVO_CONTROLE,
        )
        self._inserir(
            2, 10, "2026-09-01T19:01:00", 1.5,
            MOTIVO_CONTROLE, "red", -1.0,
        )
        self._inserir(
            3, 20, "2026-09-01T20:01:00", 1.5,
            MOTIVO_QUARENTENA, "red", -1.0, politica=True,
        )
        self._inserir(
            4, 20, "2026-09-01T20:02:00", 1.5,
            MOTIVO_QUARENTENA, "red", -1.0, politica=True,
        )
        self._inserir(
            5, 21, "2026-09-01T20:03:00", 2.5,
            MOTIVO_QUARENTENA, "green", 0.8, politica=True,
        )
        self._inserir(
            6, 30, "2026-09-01T20:04:00", 0.5,
            MOTIVO_CONTROLE, "green", 0.8,
        )

        resultado = avaliar_quarentena_fallback_ht(
            self.banco, ancora_prospectiva=ancora
        )

        self.assertEqual("concluida", resultado["estado_execucao"])
        self.assertEqual(
            "custodia-execucao-avaliacao-v3",
            resultado["custodia_execucao_versao"],
        )
        self.assertEqual(0, resultado["baseline_retrospectiva"]["resultados"])
        self.assertEqual(1, resultado["baseline_retrospectiva"]["pendentes"])
        self.assertEqual(
            1, resultado["auditoria_baseline"]["duplicados_posteriores"]
        )
        quarentena = resultado["por_grupo"]["quarentena_linhas_altas"]
        self.assertEqual(2, quarentena["candidatos_independentes"])
        self.assertEqual(1, quarentena["greens"])
        self.assertEqual(1, quarentena["reds"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["reativacao_automatica"])
        self.assertFalse(resultado["telegram"])

    def test_partida_nao_pode_entrar_nos_dois_bracos(self):
        ancora = "2026-09-01T20:00:00"
        self._inserir(
            1, 10, "2026-09-01T20:01:00", 1.5,
            MOTIVO_QUARENTENA, politica=True,
        )
        self._inserir(
            2, 10, "2026-09-01T20:02:00", 0.5,
            MOTIVO_CONTROLE, "green", 0.8,
        )

        resultado = avaliar_quarentena_fallback_ht(
            self.banco, ancora_prospectiva=ancora
        )

        quarentena = resultado["por_grupo"]["quarentena_linhas_altas"]
        controle = resultado["por_grupo"]["controle_ht_0_5"]
        self.assertEqual(1, quarentena["candidatos_independentes"])
        self.assertEqual(1, quarentena["pendentes"])
        self.assertEqual(0, controle["candidatos_independentes"])
        self.assertEqual(
            1,
            resultado["auditoria_independencia"][
                "trocas_grupo_posteriores"
            ],
        )

    def test_coorte_fixa_holdout_nao_substitui_pendente_por_item_101(self):
        ancora = "2026-09-01T20:00:00"
        for indice in range(1, TAMANHO_COORTE + 2):
            resultado = "green" if indice <= TAMANHO_DESENVOLVIMENTO else "red"
            retorno = 0.8 if resultado == "green" else -1.0
            if indice == TAMANHO_DESENVOLVIMENTO + 1:
                resultado = None
                retorno = None
            if indice == TAMANHO_COORTE + 1:
                resultado = "green"
                retorno = 0.8
            self._inserir(
                indice,
                1000 + indice,
                f"2026-09-02T{indice // 60:02d}:{indice % 60:02d}:00",
                1.5,
                MOTIVO_QUARENTENA,
                resultado,
                retorno,
                politica=True,
            )

        avaliado = avaliar_quarentena_fallback_ht(
            self.banco, ancora_prospectiva=ancora
        )

        grupo = avaliado["por_grupo"]["quarentena_linhas_altas"]
        holdout = avaliado["cronologia_por_grupo"][
            "quarentena_linhas_altas"
        ]["holdout_30"]
        diagnostico = avaliado[
            "por_grupo_todas_independentes_diagnostico"
        ]["quarentena_linhas_altas"]
        auditoria = avaliado["auditoria_por_grupo"][
            "quarentena_linhas_altas"
        ]
        self.assertEqual(TAMANHO_COORTE, grupo["candidatos_independentes"])
        self.assertEqual(TAMANHO_COORTE - 1, grupo["resultados"])
        self.assertEqual(TAMANHO_HOLDOUT, holdout["candidatos_independentes"])
        self.assertEqual(TAMANHO_HOLDOUT - 1, holdout["resultados"])
        self.assertEqual(TAMANHO_COORTE, diagnostico["resultados"])
        self.assertEqual(1, auditoria[
            "unidades_pos_coorte_fixa_somente_diagnostico"
        ])
        self.assertFalse(avaliado["pronto_para_revisao"])

    def test_retorno_incompativel_falha_fechado(self):
        ancora = "2026-09-01T20:00:00"
        self._inserir(
            1, 10, "2026-09-01T20:01:00", 1.5,
            MOTIVO_QUARENTENA, "green", 0.7, politica=True, odd=1.8,
        )

        resultado = avaliar_quarentena_fallback_ht(
            self.banco, ancora_prospectiva=ancora
        )

        grupo = resultado["por_grupo"]["quarentena_linhas_altas"]
        self.assertEqual(0, grupo["resultados"])
        self.assertEqual(1, grupo["pendentes"])
        self.assertEqual(
            1,
            grupo["auditoria_resultados"]["motivos"][
                "retorno_incompativel_com_resultado_e_odd"
            ],
        )

    def test_ancora_v2_ignora_chave_v1_e_e_idempotente(self):
        self.banco.conexao.execute(
            "INSERT INTO metadados VALUES (?, ?)",
            (CHAVE_ANCORA_LEGADA, "2026-01-01T00:00:00"),
        )
        self.banco.conexao.commit()

        primeiro = avaliar_quarentena_fallback_ht(self.banco)
        segundo = avaliar_quarentena_fallback_ht(self.banco)

        self.assertEqual(VERSAO, primeiro["versao"])
        self.assertEqual(
            primeiro["ancora_prospectiva_em"],
            segundo["ancora_prospectiva_em"],
        )
        self.assertNotEqual(
            "2026-01-01T00:00:00", primeiro["ancora_prospectiva_em"]
        )
        self.assertTrue(primeiro["ancora_metodologia_v2_pre_registrada"])

    def test_ancora_e_persistida_e_rollback_e_observavel(self):
        with patch(
            "avaliacao_quarentena_fallback_ht."
            "fallback_api_ht_linhas_altas_ativo",
            return_value=True,
        ):
            resultado = avaliar_quarentena_fallback_ht(self.banco)

        ancora = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE_ANCORA,)
        ).fetchone()
        self.assertIsNotNone(ancora)
        self.assertFalse(resultado["politica_operacional_ativa"])
        self.assertIn("HT_LINHAS_ALTAS_ATIVO=1", resultado["rollback"])


if __name__ == "__main__":
    unittest.main()
