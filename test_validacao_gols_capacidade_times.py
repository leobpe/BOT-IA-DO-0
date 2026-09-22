import json
import sqlite3
import unittest
from datetime import datetime

from gols_capacidade_times import (
    LINHAGEM_GOLS_CAPACIDADE,
    VERSAO_GOL_FT_CAPACIDADE,
)
from validacao_gols_capacidade_times import (
    CHAVE_DEFINICAO,
    registrar_ou_validar_gols_capacidade_times,
    resumir_validacao_gols_capacidade_times,
)


class TestValidacaoGolsCapacidadeTimes(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
          CREATE TABLE sinais(
            id INTEGER PRIMARY KEY, partida_id INTEGER, criado_em TEXT,
            mercado TEXT, status TEXT, features_json TEXT
          );
          CREATE TABLE resultados_sinais(
            sinal_id INTEGER PRIMARY KEY, resultado TEXT,
            retorno_unidades REAL
          );
          CREATE TABLE entregas_alertas(
            id INTEGER PRIMARY KEY, sinal_id INTEGER, canal TEXT,
            tentado_em TEXT, status TEXT
          );
        """)

    def tearDown(self):
        self.db.close()

    def _sinal(self, sid, partida, criado_em, resultado, retorno):
        features = {
            "exploracao_sombra": {"versao": VERSAO_GOL_FT_CAPACIDADE},
            "gol_capacidade_times": {
                "linhagem_sha256": LINHAGEM_GOLS_CAPACIDADE,
            },
        }
        self.db.execute(
            "INSERT INTO sinais VALUES (?, ?, ?, 'gol_ft', 'simulacao', ?)",
            (sid, partida, criado_em, json.dumps(features)),
        )
        self.db.execute(
            "INSERT INTO entregas_alertas VALUES (?, ?, '-1:teste', ?, 'entregue')",
            (sid, sid, criado_em),
        )
        self.db.execute(
            "INSERT INTO resultados_sinais VALUES (?, ?, ?)",
            (sid, resultado, retorno),
        )

    def test_registro_idempotente_e_ancora_fechada(self):
        marco = datetime(2026, 8, 25, 8, 0)
        a = registrar_ou_validar_gols_capacidade_times(self.db, marco)
        b = registrar_ou_validar_gols_capacidade_times(
            self.db, datetime(2099, 1, 1)
        )
        self.assertEqual(
            a["definicao"]["registrado_em"],
            b["definicao"]["registrado_em"],
        )
        documento = json.loads(self.db.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
        ).fetchone()["valor"])
        documento["linhagem_sha256"] = "x" * 64
        self.db.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(documento), CHAVE_DEFINICAO),
        )
        with self.assertRaisesRegex(RuntimeError, "âncora imutável"):
            registrar_ou_validar_gols_capacidade_times(self.db)

    def test_coorte_deduplica_partida_e_mede_roi(self):
        registrar_ou_validar_gols_capacidade_times(
            self.db, datetime(2026, 8, 25, 8, 0)
        )
        self._sinal(1, 10, "2026-08-25T08:01:00", "green", 0.8)
        self._sinal(2, 10, "2026-08-25T08:02:00", "red", -1.0)
        self._sinal(3, 20, "2026-08-25T08:03:00", "green", 0.7)
        self.db.commit()
        resumo = resumir_validacao_gols_capacidade_times(self.db)
        braco = resumo["por_braco"][VERSAO_GOL_FT_CAPACIDADE]
        self.assertEqual(2, braco["candidatos_coorte"])
        self.assertEqual(2, braco["validos"])
        self.assertEqual(2, braco["greens"])
        self.assertEqual(0.75, braco["roi"])
        self.assertEqual("aguardando_amostra_futura", braco["decisao_estatistica"])


if __name__ == "__main__":
    unittest.main()
