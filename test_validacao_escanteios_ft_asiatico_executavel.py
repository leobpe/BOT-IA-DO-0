import json
import sqlite3
import unittest
from datetime import datetime

import validacao_escanteios_ft_asiatico_executavel as validacao


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


def _origem():
    return {
        "schema": "origem-mercado-odd-v1",
        "fonte": "betsapi",
        "identificador": "1778",
        "nome": "Asian Corners",
        "linha": 7.5,
        "lados": ["over", "under"],
        "bookmaker": "bet365",
    }


def _features_executaveis():
    origem = _origem()
    return {
        "tipo_mercado_odds": "asiatico",
        "escanteios_atuais": 7,
        "fonte_odds": "betsapi",
        "bookmaker_odds": "bet365",
        "cotacao_entrada_clv_estado": "congelada_v1",
        "cotacao_entrada_clv": {
            "schema": "cotacao-entrada-clv-v2",
            "mercado": validacao.MERCADO,
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "coletado_em": "2026-09-12T20:00:00+00:00",
            "idade_segundos": 4.0,
            "cache": False,
            "tipo": "binaria",
            "linha": 7.5,
            "over": 1.80,
            "under": 2.05,
            "odd_selecionada": 1.80,
            "origem_mercado": origem,
        },
    }


def _inserir(
    conexao, sinal_id, partida_id, criado_em, *, executavel=True
):
    if executavel:
        features = _features_executaveis()
    else:
        features = {
            "tipo_mercado_odds": "asiatico",
            "escanteios_atuais": 7,
            "fonte_odds": "api_football",
            "bookmaker_odds": None,
        }
    conexao.execute("""
        INSERT INTO sinais(
            id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
            pontuacao_tecnica,probabilidade_calibrada,status,regra_versao,
            regra_fingerprint,motivos_json,features_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        sinal_id, partida_id, sinal_id, criado_em,
        validacao.MERCADO, 7.5, 1.80, 90.0, None, "aprovado",
        validacao.REGRA_VERSAO, "a" * 64, "[]", json.dumps(features),
    ))


class ValidacaoEscanteiosFtAsiaticoExecutavelTest(unittest.TestCase):
    def test_coorte_recusa_agregado_e_aceita_betsapi_bet365(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        validacao.registrar_ou_validar_definicao(
            conexao, datetime(2026, 9, 12, 16, 0)
        )
        _inserir(
            conexao, 1, 10, "2026-09-12T16:00:01", executavel=False
        )
        _inserir(conexao, 2, 20, "2026-09-12T16:00:02")

        sincronizacao = validacao.sincronizar_coorte(conexao)

        self.assertEqual(1, sincronizacao["inseridos"])
        self.assertEqual(1, sincronizacao["candidatos"])
        self.assertEqual(1, sincronizacao["excluidos_custodia"])
        self.assertEqual(
            [(2, 20)],
            [tuple(item) for item in conexao.execute(
                f"SELECT sinal_id,partida_id FROM {validacao.TABELA_COORTE}"
            ).fetchall()],
        )
        resumo = validacao.resumir_validacao(conexao)
        self.assertEqual("betsapi", resumo["custodia_cotacao"]["fonte_exigida"])
        self.assertEqual("bet365", resumo["custodia_cotacao"]["bookmaker_exigida"])
        self.assertEqual(0, resumo["custodia_cotacao"]["violacoes_na_coorte"])
        self.assertEqual(
            1, resumo["custodia_cotacao"]["exclusoes"]["total"]
        )
        self.assertEqual("aguardando_amostra_executavel_futura", resumo["decisao"])

    def test_primeiro_executavel_por_partida_ocupa_uma_vaga(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        validacao.registrar_ou_validar_definicao(
            conexao, datetime(2026, 9, 12, 16, 0)
        )
        _inserir(conexao, 1, 10, "2026-09-12T16:00:01")
        _inserir(conexao, 2, 10, "2026-09-12T16:00:02")

        resumo = validacao.sincronizar_coorte(conexao)

        self.assertEqual(1, resumo["candidatos"])
        self.assertEqual(1, resumo["inseridos"])

    def test_prova_congelada_adulterada_falha_fechado(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        validacao.registrar_ou_validar_definicao(
            conexao, datetime(2026, 9, 12, 16, 0)
        )
        _inserir(conexao, 1, 10, "2026-09-12T16:00:01")
        validacao.sincronizar_coorte(conexao)
        membro = json.loads(conexao.execute(
            f"SELECT candidato_json FROM {validacao.TABELA_COORTE}"
        ).fetchone()[0])
        membro["features"]["cotacao_entrada_clv"]["odd_selecionada"] = 1.90
        conexao.execute(
            f"UPDATE {validacao.TABELA_COORTE} SET candidato_json=?",
            (json.dumps(membro),),
        )

        with self.assertRaises(RuntimeError):
            validacao.resumir_validacao(conexao)

    def test_exclusao_adulterada_falha_fechado(self):
        conexao = _banco()
        self.addCleanup(conexao.close)
        validacao.registrar_ou_validar_definicao(
            conexao, datetime(2026, 9, 12, 16, 0)
        )
        _inserir(
            conexao, 1, 10, "2026-09-12T16:00:01", executavel=False
        )
        validacao.sincronizar_coorte(conexao)
        conexao.execute(
            f"UPDATE {validacao.TABELA_EXCLUSOES} SET motivo='alterado'"
        )

        with self.assertRaises(RuntimeError):
            validacao.resumir_validacao(conexao)


if __name__ == "__main__":
    unittest.main()
