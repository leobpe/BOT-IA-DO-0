import json
import sqlite3
import unittest
from unittest.mock import patch

from avaliacao_probabilidade_individual import (
    PREFIXO_DEFINICAO,
    PREFIXO_PREVISAO,
    VERSAO,
    avaliar_probabilidade_individual,
)
from probabilidade_individual_sem_vig import VERSAO as VERSAO_MODELO


class BancoMemoria:
    def __init__(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript("""
            CREATE TABLE metadados(chave TEXT PRIMARY KEY,valor TEXT NOT NULL);
            CREATE TABLE sinais(
                id INTEGER PRIMARY KEY,partida_id INTEGER,snapshot_id INTEGER,
                mercado TEXT,linha REAL,odd REAL,regra_versao TEXT,
                regra_fingerprint TEXT,features_json TEXT,criado_em TEXT
            );
            CREATE TABLE snapshots(
                id INTEGER PRIMARY KEY,partida_id INTEGER,placar TEXT,
                contexto_api_json TEXT,coletado_em TEXT
            );
            CREATE TABLE partidas(
                id INTEGER PRIMARY KEY,mandante TEXT,visitante TEXT,liga TEXT
            );
            CREATE TABLE entregas_alertas(
                sinal_id INTEGER,canal TEXT,status TEXT,
                provedor_mensagem_id INTEGER,entregue_em TEXT
            );
            CREATE TABLE resultados_sinais(
                sinal_id INTEGER,resultado TEXT,retorno_unidades REAL,
                encerrado_em TEXT
            );
        """)

    def close(self):
        self.conexao.close()


def retro(aprovado=False):
    return {
        "versao": VERSAO_MODELO,
        "mercado": "gol_ft",
        "estado": (
            "aprovado_para_coorte_prospectiva"
            if aprovado else "validacao_reprovada"
        ),
        "amostra": 200,
        "folds": [],
        "validacao": {"n": 90},
        "aprovado_para_coorte_prospectiva": aprovado,
        "modelo": {"versao": VERSAO_MODELO} if aprovado else None,
        "aplicacao_sinais": False,
        "telegram": False,
    }


class AvaliacaoProbabilidadeIndividualTest(unittest.TestCase):
    def setUp(self):
        self.banco = BancoMemoria()
        self.addCleanup(self.banco.close)

    def _avaliar(self, agora, aprovado=False):
        def validar(_base, mercado, _corte):
            item = retro(aprovado)
            item["mercado"] = mercado
            return item

        with (
            patch(
                "avaliacao_probabilidade_individual.carregar_base",
                return_value=[],
            ),
            patch(
                "avaliacao_probabilidade_individual.anexar_referencia_sem_vig",
                side_effect=lambda _conexao, itens: (
                    [
                        {
                            **item,
                            "probabilidade_mercado_sem_vig": 0.58,
                            "margem_bookmaker": 0.08,
                            "tipo_referencia_mercado": (
                                "binaria_mesmo_snapshot"
                            ),
                        }
                        for item in itens
                    ],
                    {
                        "total": len(itens),
                        "com_referencia_sem_vig": len(itens),
                        "sem_referencia_sem_vig": 0,
                        "taxa_cobertura": 1.0 if itens else None,
                        "cobertura_minima": 0.95,
                        "cobertura_suficiente": True,
                        "margem_bookmaker_media": 0.08,
                        "exclusoes": {},
                        "referencia": (
                            "over_under_mesmo_snapshot_sem_vig"
                        ),
                        "consulta_resultado": False,
                        "aplicacao_sinais": False,
                        "telegram": False,
                    },
                ),
            ),
            patch(
                "avaliacao_probabilidade_individual.validar_modelo",
                side_effect=validar,
            ),
            patch(
                "avaliacao_probabilidade_individual.prever_modelo",
                return_value=0.7,
            ),
        ):
            return avaliar_probabilidade_individual(
                self.banco, agora=agora
            )

    def test_reprovacao_retro_nao_cria_modelo_nem_efeito(self):
        estado = self._avaliar("2026-09-11T12:00:00", aprovado=False)
        self.assertEqual(estado["versao"], VERSAO)
        self.assertTrue(estado["integridade"])
        self.assertFalse(estado["aplicacao_sinais"])
        self.assertFalse(estado["altera_calibracao"])
        self.assertFalse(estado["telegram"])
        self.assertEqual(
            "individual-logistica-offset-mercado-sem-vig-walkforward-v3",
            estado["modelo_versao"],
        )
        self.assertTrue(all(
            item["estado"] == "aguardando_modelo_retro_validado"
            for item in estado["mercados"].values()
        ))
        total = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM metadados"
        ).fetchone()[0]
        self.assertEqual(total, 0)

    def test_definicao_e_previsao_sao_anteriores_ao_resultado(self):
        primeiro = self._avaliar("2026-09-11T12:00:00", aprovado=True)
        self.assertTrue(all(
            item["definicao_presente"]
            for item in primeiro["mercados"].values()
        ))
        contexto = {
            "historico_detalhado": {
                "mandante": {
                    "jogos": 10,
                    "gols_pro_media": 1.8,
                    "gols_contra_media": 0.7,
                },
                "visitante": {
                    "jogos": 10,
                    "gols_pro_media": 1.2,
                    "gols_contra_media": 1.5,
                },
            }
        }
        features = {
            "minuto": 55,
            "janelas": {
                "5": {
                    "disponivel": True,
                    "duracao_real_minutos": 5,
                    "chutes_total": 3,
                    "pressao_pico": [60, 30],
                }
            },
        }
        self.banco.conexao.execute(
            "INSERT INTO partidas VALUES(1,'A','B','Liga')"
        )
        self.banco.conexao.execute(
            "INSERT INTO snapshots VALUES(1,1,'0-0',?,?)",
            (json.dumps(contexto), "2026-09-11T12:00:30"),
        )
        self.banco.conexao.execute(
            "INSERT INTO sinais VALUES(1,1,1,'gol_ft',0.5,1.70,?,?,?,?)",
            (
                "metodo-v1",
                "fp-v1",
                json.dumps(features),
                "2026-09-11T12:01:00",
            ),
        )
        self.banco.conexao.execute(
            "INSERT INTO entregas_alertas VALUES(1,'-100:teste','entregue',9,?)",
            ("2026-09-11T12:01:02",),
        )
        segundo = self._avaliar("2026-09-11T12:02:00", aprovado=True)
        coorte = segundo["mercados"]["gol_ft"]["coorte_prospectiva"]
        self.assertEqual(coorte["candidatos"], 1)
        self.assertEqual(coorte["resultados"], 0)
        previsao = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (PREFIXO_PREVISAO + "gol_ft:1",),
        ).fetchone()
        self.assertIsNotNone(previsao)
        self.banco.conexao.execute(
            "INSERT INTO resultados_sinais VALUES(1,'green',0.7,?)",
            ("2026-09-11T12:03:00",),
        )
        terceiro = self._avaliar("2026-09-11T12:04:00", aprovado=True)
        coorte = terceiro["mercados"]["gol_ft"]["coorte_prospectiva"]
        self.assertEqual(coorte["resultados"], 1)
        self.assertEqual(coorte["total"]["greens"], 1)
        self.assertIn(
            "delta_brier_vs_mercado_sem_vig", coorte["total"]
        )

    def test_definicao_adulterada_bloqueia_so_inferencia(self):
        self._avaliar("2026-09-11T12:00:00", aprovado=True)
        self.banco.conexao.execute(
            "UPDATE metadados SET valor='{}' WHERE chave=?",
            (PREFIXO_DEFINICAO + "gol_ft",),
        )
        estado = self._avaliar("2026-09-11T12:01:00", aprovado=True)
        self.assertFalse(estado["integridade"])
        self.assertEqual(
            estado["mercados"]["gol_ft"]["estado"],
            "definicao_integra_invalida",
        )
        self.assertFalse(estado["aplicacao_sinais"])
        self.assertFalse(estado["telegram"])


if __name__ == "__main__":
    unittest.main()
