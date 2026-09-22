import sqlite3
import unittest
from datetime import datetime, timedelta
import json

from resgate_qualidade_api import (
    avaliar_resgate_qualidade_api,
    resumir_resgate_qualidade_api,
)


class ResgateQualidadeApiTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.execute(
            """
            CREATE TABLE historico_api_live (
                id INTEGER PRIMARY KEY,
                fixture_id INTEGER,
                packball_url TEXT,
                coletado_em TEXT,
                minuto REAL,
                chutes_mandante REAL,
                chutes_visitante REAL,
                chutes_gol_mandante REAL,
                chutes_gol_visitante REAL,
                escanteios_mandante REAL,
                escanteios_visitante REAL
            )
            """
        )
        self.conexao.execute(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY,
                partida_id INTEGER,
                coletado_em TEXT,
                qualidade_json TEXT
            )
            """
        )
        self.agora = datetime(2026, 8, 24, 20, 0, 0)
        self.jogo = {
            "url": "https://packball.test/jogo/1",
            "status": "12'",
            "placar": "0-0",
        }
        self.confirmacao = {
            "fixture_id": 123,
            "similaridade": 0.95,
            "placar": [0, 0],
            "status": {"elapsed": 12},
        }
        self.estatisticas = {
            "Chutes": "4-2",
            "Escanteios": "2-1",
            "Ataques perigosos": "20-14",
        }
        self.qualidade = {
            "pontuacao": 67.0,
            "campos_ausentes": ["Chutes no gol", "Índice de pressão"],
            "divergencia_critica": False,
        }

    def tearDown(self):
        self.conexao.close()

    def _inserir(self, coletado_em=None, minuto=12):
        self.conexao.execute(
            """
            INSERT INTO historico_api_live VALUES (
                1, 123, ?, ?, ?, 4, 2, 2, 1, 2, 1
            )
            """,
            (
                self.jogo["url"],
                (coletado_em or self.agora).isoformat(),
                minuto,
            ),
        )

    def test_resgata_com_snapshot_persistido_sem_chamada_extra(self):
        self._inserir()

        resultado = avaliar_resgate_qualidade_api(
            self.conexao, self.jogo, self.confirmacao,
            self.estatisticas, self.qualidade, agora=self.agora,
        )

        self.assertEqual("resgatado", resultado["estado"])
        self.assertEqual(["Chutes no gol"], resultado["campos_complementados"])
        self.assertGreaterEqual(resultado["qualidade_sombra"], 80)
        self.assertEqual(0, resultado["chamadas_api_adicionais"])
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_rejeita_snapshot_velho_e_minuto_incompativel(self):
        self._inserir(self.agora - timedelta(minutes=6))
        resultado = avaliar_resgate_qualidade_api(
            self.conexao, self.jogo, self.confirmacao,
            self.estatisticas, self.qualidade, agora=self.agora,
        )
        self.assertEqual("snapshot_api_desatualizado", resultado["motivo"])

        self.conexao.execute("DELETE FROM historico_api_live")
        self._inserir(minuto=2)
        resultado = avaliar_resgate_qualidade_api(
            self.conexao, self.jogo, self.confirmacao,
            self.estatisticas, self.qualidade, agora=self.agora,
        )
        self.assertEqual("minuto_api_incompativel", resultado["motivo"])

    def test_nao_aplica_fora_da_janela(self):
        self.jogo["status"] = "35'"
        resultado = avaliar_resgate_qualidade_api(
            self.conexao, self.jogo, self.confirmacao,
            self.estatisticas, self.qualidade, agora=self.agora,
        )
        self.assertEqual("nao_elegivel", resultado["estado"])
        self.assertEqual(
            "fora_janela_gols_antecipados", resultado["motivo"]
        )

    def test_resume_evidencias_persistidas_por_janela(self):
        diagnosticos = [
            {
                "estado": "resgatado",
                "motivo": "qualidade_resgatada_sombra",
                "qualidade_original": 67.0,
                "qualidade_sombra": 83.0,
                "campos_complementados": ["Chutes no gol"],
            },
            {
                "estado": "avaliado",
                "motivo": "sem_snapshot_api",
                "qualidade_original": 65.0,
                "campos_complementados": [],
            },
            {
                "estado": "dispensado",
                "motivo": "qualidade_ja_suficiente",
                "qualidade_original": 90.0,
                "campos_complementados": [],
            },
        ]
        for indice, diagnostico in enumerate(diagnosticos, 1):
            self.conexao.execute(
                "INSERT INTO snapshots VALUES (?, ?, ?, ?)",
                (
                    indice,
                    10 + min(indice, 2),
                    (self.agora - timedelta(hours=indice)).isoformat(),
                    json.dumps({
                        "resgate_qualidade_api_sombra": diagnostico
                    }),
                ),
            )

        resumo = resumir_resgate_qualidade_api(
            self.conexao, horas=24, agora=self.agora
        )

        self.assertEqual(3, resumo["registros"])
        self.assertEqual(2, resumo["elegiveis"])
        self.assertEqual(2, resumo["jogos_distintos"])
        self.assertEqual(1, resumo["resgatadas"])
        self.assertEqual(0.5, resumo["taxa_resgate"])
        self.assertEqual(16.0, resumo["ganho_medio_qualidade"])
        self.assertEqual(
            {"Chutes no gol": 1}, resumo["campos_complementados"]
        )
        self.assertFalse(resumo["pronto_para_revisao"])


if __name__ == "__main__":
    unittest.main()
