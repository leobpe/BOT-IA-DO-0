import json
import sqlite3
import unittest
from datetime import datetime

import validacao_escanteios_ft_asiatico_prospectiva as validacao


def _banco():
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript("""
        CREATE TABLE sinais (
            id INTEGER PRIMARY KEY,
            partida_id INTEGER NOT NULL,
            snapshot_id INTEGER NOT NULL,
            criado_em TEXT NOT NULL,
            mercado TEXT NOT NULL,
            linha REAL,
            odd REAL,
            pontuacao_tecnica REAL,
            probabilidade_calibrada REAL,
            status TEXT NOT NULL,
            regra_versao TEXT NOT NULL,
            regra_fingerprint TEXT,
            motivos_json TEXT,
            features_json TEXT
        );
        CREATE TABLE resultados_sinais (
            sinal_id INTEGER PRIMARY KEY,
            resultado TEXT,
            retorno_unidades REAL
        );
        CREATE TABLE entregas_alertas (
            sinal_id INTEGER,
            canal TEXT,
            status TEXT
        );
    """)
    return conexao


def _inserir(conexao, sinal_id, partida_id, criado_em, *, status="aprovado"):
    features = {
        "tipo_mercado_odds": "asiatico",
        "escanteios_atuais": 7,
        "fonte_odds": "api_football",
        "bookmaker_odds": "bookmaker_teste",
    }
    conexao.execute("""
        INSERT INTO sinais(
            id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
            pontuacao_tecnica,probabilidade_calibrada,status,regra_versao,
            regra_fingerprint,motivos_json,features_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        sinal_id, partida_id, sinal_id, criado_em,
        validacao.MERCADO, 7.5, 1.80, 90.0, None, status,
        validacao.REGRA_VERSAO, "a" * 64, "[]",
        json.dumps(features),
    ))


class ValidacaoEscanteiosFtAsiaticoTest(unittest.TestCase):
    def test_congela_somente_futuro_e_uma_entrada_por_partida(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        _inserir(conexao, 1, 10, "2026-09-09T11:59:59")
        documento = validacao.registrar_ou_validar_definicao(
            conexao, datetime(2026, 9, 9, 12, 0),
        )
        self.assertEqual(
            "2026-09-09T12:00:00",
            documento["registrado_em_relogio_sinais"],
        )
        self.assertRegex(documento["registrado_em"], r"[+-]\d\d:\d\d$")
        _inserir(conexao, 2, 20, "2026-09-09T12:00:01")
        _inserir(conexao, 3, 20, "2026-09-09T12:01:01")
        _inserir(conexao, 4, 30, "2026-09-09T12:02:01")
        sincronizacao = validacao.sincronizar_coorte(conexao)
        self.assertEqual(sincronizacao["inseridos"], 2)
        self.assertEqual(sincronizacao["candidatos"], 2)
        linhas = conexao.execute(
            f"SELECT sinal_id,partida_id,ordem FROM {validacao.TABELA_COORTE} "
            "ORDER BY ordem"
        ).fetchall()
        self.assertEqual([tuple(item) for item in linhas], [
            (2, 20, 1), (4, 30, 2),
        ])

    def test_conteudo_congelado_adulterado_falha_fechado(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        validacao.registrar_ou_validar_definicao(
            conexao, datetime(2026, 9, 9, 12, 0),
        )
        _inserir(conexao, 2, 20, "2026-09-09T12:00:01")
        validacao.sincronizar_coorte(conexao)
        conexao.execute(
            f"UPDATE {validacao.TABELA_COORTE} SET candidato_json='{{}}'"
        )
        with self.assertRaises(RuntimeError):
            validacao.resumir_validacao(conexao)

    def test_metricas_preservam_liquidacao_asiatica(self):
        referencia = {"probabilidade_over": 0.50}
        itens = [
            {"linha": 7.5, "resultado": "green", "retorno_unidades": 0.8,
             "referencia": referencia, "publicado": True},
            {"linha": 7.5, "resultado": "red", "retorno_unidades": -1.0,
             "referencia": referencia, "publicado": True},
            {"linha": 7.25, "resultado": "half_green", "retorno_unidades": 0.4,
             "referencia": referencia, "publicado": False},
            {"linha": 7.0, "resultado": "void", "retorno_unidades": 0.0,
             "referencia": referencia, "publicado": False},
            {"linha": 7.75, "resultado": "half_red", "retorno_unidades": -0.5,
             "referencia": referencia, "publicado": False},
        ]
        resumo = validacao._metricas(itens)
        self.assertEqual(resumo["validos"], 5)
        self.assertEqual(resumo["resultados_direcionais"], 4)
        self.assertEqual(resumo["resultados_positivos"], 2)
        self.assertEqual(resumo["taxa_resultado_positivo"], 0.5)
        self.assertEqual(resumo["voids"], 1)
        self.assertEqual(resumo["referencia_sem_vig"]["binarios_meia"], 2)
        self.assertAlmostEqual(resumo["roi"], -0.06)

    def test_definicao_divergente_e_rejeitada(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        documento = validacao.registrar_ou_validar_definicao(conexao)
        documento["coorte_fixa"] = 99
        conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(documento), validacao.CHAVE_DEFINICAO),
        )
        with self.assertRaises(RuntimeError):
            validacao.registrar_ou_validar_definicao(conexao)

    def test_ancora_sem_relogio_de_selecao_falha_fechado(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        documento = validacao.registrar_ou_validar_definicao(
            conexao, datetime(2026, 9, 9, 12, 0),
        )
        documento.pop("registrado_em_relogio_sinais")
        conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(documento), validacao.CHAVE_DEFINICAO),
        )
        with self.assertRaises(RuntimeError):
            validacao.resumir_validacao(conexao)


if __name__ == "__main__":
    unittest.main()
