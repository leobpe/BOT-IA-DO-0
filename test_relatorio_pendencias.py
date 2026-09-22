import sqlite3
import unittest
from datetime import datetime

from relatorio_pendencias import resumir_pendencias_resultados


class RelatorioPendenciasTest(unittest.TestCase):
    def test_resume_cobertura_idade_e_tentativas(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE partidas (
                id INTEGER PRIMARY KEY, api_fixture_id INTEGER
            );
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                mercado TEXT, criado_em TEXT, status TEXT
            );
            CREATE TABLE resultados_sinais (sinal_id INTEGER);
            CREATE TABLE consultas_finalizacao (
                id INTEGER PRIMARY KEY, partida_id INTEGER, fonte TEXT
            );
            INSERT INTO partidas VALUES (1, 100), (2, NULL), (3, 300);
            INSERT INTO sinais VALUES
              (1, 1, 'gol_ft', '2026-07-21T08:00:00', 'aprovado'),
              (2, 1, 'gol_ft', '2026-07-21T09:00:00', 'simulacao'),
              (3, 2, 'proximo_gol', '2026-07-21T11:00:00', 'aprovado'),
              (4, 3, 'gol_ht', '2026-07-21T08:00:00', 'rejeitado');
            INSERT INTO resultados_sinais VALUES (2);
            INSERT INTO consultas_finalizacao VALUES
              (1, 1, 'api_football'), (2, 1, 'packball');
            """
        )

        resumo = resumir_pendencias_resultados(
            conexao, datetime(2026, 7, 21, 12, 0)
        )

        self.assertEqual(resumo["sinais"], 2)
        self.assertEqual(resumo["partidas"], 2)
        self.assertEqual(resumo["partidas_com_api"], 1)
        self.assertEqual(resumo["partidas_somente_packball"], 1)
        self.assertEqual(resumo["partidas_com_tentativa"], 1)
        self.assertEqual(resumo["partidas_sem_tentativa"], 1)
        self.assertEqual(resumo["sinais_acima_180_minutos"], 1)
        self.assertEqual(resumo["idade_mais_antiga_minutos"], 240.0)
        self.assertEqual(
            resumo["por_mercado"], {"gol_ft": 1, "proximo_gol": 1}
        )
        conexao.close()


if __name__ == "__main__":
    unittest.main()
