import json
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path

from supervisao_referencia_api_football import (
    VERSAO_FONTE,
    verificar_referencia_api_football_sombra,
)


class SupervisaoReferenciaAPIFootballTest(unittest.TestCase):
    def setUp(self):
        self.banco = Path.cwd() / ".teste_supervisao_referencia_api.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.banco) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        conexao = sqlite3.connect(self.banco)
        conexao.executescript(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY,
                partida_id INTEGER NOT NULL,
                coletado_em TEXT NOT NULL,
                qualidade_json TEXT NOT NULL
            );
            CREATE TABLE odds (
                id INTEGER PRIMARY KEY,
                snapshot_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                mercado TEXT NOT NULL,
                dados TEXT NOT NULL,
                estrutura_json TEXT NOT NULL
            );
            """
        )
        conexao.close()
        self.agora = datetime(2026, 9, 12, 18, 0, 0)

    def tearDown(self):
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.banco) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    @staticmethod
    def _diagnostico(*, pareado=False, efeito=False):
        retornados = ["gol_ft"] if pareado else []
        bookmakers = ["Pinnacle"] if pareado else []
        return {
            "versao": VERSAO_FONTE,
            "ativa": True,
            "mercados_solicitados": ["gol_ft"],
            "mercados_retornados": retornados,
            "bookmakers_independentes": bookmakers,
            "consultas_rede_estimadas": 1,
            "pareado": pareado,
            "motivo": (
                "referencia_independente_disponivel"
                if pareado else "sem_referencia_independente_api_football"
            ),
            "por_mercado": {
                "gol_ft": {
                    "versao": VERSAO_FONTE,
                    "mercado": "gol_ft",
                    "bookmaker_excluido": "bet365",
                    "aplicacao_sinais": False,
                    "telegram": False,
                    "promocao_automatica": False,
                }
            },
            "aplicacao_sinais": efeito,
            "altera_calibracao": False,
            "telegram": False,
            "promocao_automatica": False,
        }

    def _snapshot(self, diagnostico, snapshot_id=1):
        conexao = sqlite3.connect(self.banco)
        conexao.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?, ?)",
            (
                snapshot_id,
                100 + snapshot_id,
                "2026-09-12T17:50:00",
                json.dumps({
                    "api_football_referencia_sombra": diagnostico,
                }),
            ),
        )
        conexao.commit()
        conexao.close()

    def _referencia_persistida(self, snapshot_id=1, bookmaker="Pinnacle"):
        identidade = {
            "schema": "identidade-evento-odd-v1",
            "confirmada": True,
            "fonte": "api_football",
            "evento_externo_id": "987",
            "mandante_normalizado": "Casa",
            "visitante_normalizado": "Fora",
            "placar_normalizado": "1-0",
        }
        estrutura = {
            "categoria": "gols",
            "ofertas": [{
                "linha": 2.5,
                "over": 1.9,
                "under": 1.9,
                "fonte": "api_football",
                "bookmaker": bookmaker,
                "identidade_evento": identidade,
            }],
        }
        conexao = sqlite3.connect(self.banco)
        conexao.execute(
            "INSERT INTO odds VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                snapshot_id,
                "referencia_sombra",
                "",
                "",
                json.dumps(estrutura),
            ),
        )
        conexao.commit()
        conexao.close()

    def test_ausencia_de_bookmaker_e_resultado_saudavel(self):
        self._snapshot(self._diagnostico())
        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )
        self.assertTrue(resumo["saudavel"])
        self.assertEqual("coletando_sem_bookmaker_alternativa", resumo["estado"])
        self.assertEqual(1, resumo["tentativas"])
        self.assertEqual(1, resumo["tentativas_sem_referencia"])
        self.assertEqual(0, resumo["referencias_disponiveis"])

    def test_rejeicao_antes_da_consulta_e_resultado_saudavel(self):
        diagnostico = self._diagnostico()
        diagnostico.update({
            "consultas_rede_estimadas": 0,
            "motivo": "associacao_api_ou_placar_incompativel",
            "fixture_id": None,
            "similaridade_associacao": 0.0,
        })
        diagnostico.pop("por_mercado")
        self._snapshot(diagnostico)

        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )

        self.assertTrue(resumo["saudavel"])
        self.assertEqual("coletando_sem_bookmaker_alternativa", resumo["estado"])
        self.assertEqual(0, resumo["violacoes_estrutura"])
        self.assertEqual(0, resumo["consultas_rede_estimadas"])

    def test_detalhe_ausente_apos_consulta_continua_inconsistente(self):
        diagnostico = self._diagnostico()
        diagnostico.pop("por_mercado")
        self._snapshot(diagnostico)

        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )

        self.assertFalse(resumo["saudavel"])
        self.assertEqual(1, resumo["violacoes_estrutura"])

    def test_capacidade_sem_bookmaker_e_consulta_evitada_sao_saudaveis(self):
        diagnostico = self._diagnostico()
        diagnostico.update({
            "consultas_rede_estimadas": 0,
            "consultas_rede_evitadas": 1,
            "mercados_sem_identidade_bookmaker": ["gol_ft"],
            "motivo": "fonte_live_sem_identidade_bookmaker",
        })
        detalhe = diagnostico["por_mercado"]["gol_ft"]
        detalhe.update({
            "motivo": "fonte_live_sem_identidade_bookmaker",
            "consulta_rede_realizada": False,
            "consulta_rede_evitada": True,
            "capacidade_referencia": {
                "versao": "api-football-referencia-capacidade-v1",
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            },
        })
        self._snapshot(diagnostico)

        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )

        self.assertTrue(resumo["saudavel"])
        self.assertEqual(
            "capacidade_bookmaker_indisponivel_observada",
            resumo["estado"],
        )
        self.assertEqual(1, resumo["consultas_rede_evitadas"])
        self.assertEqual(
            ["gol_ft"], resumo["mercados_sem_identidade_bookmaker"]
        )
        self.assertEqual(
            1,
            resumo["por_motivo_mercado"][
                "fonte_live_sem_identidade_bookmaker"
            ],
        )

    def test_contador_de_consulta_evitada_divergente_falha_fechado(self):
        diagnostico = self._diagnostico()
        diagnostico["consultas_rede_evitadas"] = 1
        self._snapshot(diagnostico)

        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )

        self.assertFalse(resumo["saudavel"])
        self.assertEqual(1, resumo["violacoes_estrutura"])

    def test_referencia_exata_persistida_e_contabilizada(self):
        self._snapshot(self._diagnostico(pareado=True))
        self._referencia_persistida()
        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )
        self.assertTrue(resumo["saudavel"])
        self.assertEqual("referencia_independente_persistida", resumo["estado"])
        self.assertEqual(1, resumo["referencias_disponiveis"])
        self.assertEqual(1, resumo["referencias_api_persistidas"])
        self.assertEqual(["Pinnacle"], resumo["bookmakers_independentes"])

    def test_pareamento_sem_odds_persistidas_falha_fechado(self):
        self._snapshot(self._diagnostico(pareado=True))
        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )
        self.assertFalse(resumo["saudavel"])
        self.assertEqual("telemetria_inconsistente", resumo["estado"])
        self.assertEqual(1, resumo["violacoes_persistencia"])

    def test_bet365_na_referencia_e_inconsistente(self):
        diagnostico = self._diagnostico(pareado=True)
        diagnostico["bookmakers_independentes"] = ["Bet365"]
        self._snapshot(diagnostico)
        self._referencia_persistida(bookmaker="Bet365")
        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )
        self.assertFalse(resumo["saudavel"])
        self.assertGreaterEqual(resumo["violacoes_estrutura"], 1)

    def test_efeito_operacional_declarado_e_critico(self):
        self._snapshot(self._diagnostico(efeito=True))
        resumo = verificar_referencia_api_football_sombra(
            self.banco, agora=self.agora
        )
        self.assertFalse(resumo["saudavel"])
        self.assertEqual("vazamento_operacional_declarado", resumo["estado"])
        self.assertEqual("critica", resumo["severidade"])
        self.assertEqual(1, resumo["violacoes_efeito"])


if __name__ == "__main__":
    unittest.main()
