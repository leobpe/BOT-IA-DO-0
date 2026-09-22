import json
import sqlite3
import unittest
from datetime import datetime

from validacao_gol_ht_00_min20 import (
    CHAVE, registrar_ou_validar_gol_ht_00_min20,
)


class ValidacaoGolHT00Min20Test(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE metadados(chave TEXT PRIMARY KEY,valor TEXT)")

    def tearDown(self):
        self.db.close()

    def test_ancora_idempotente_e_imutavel(self):
        a = registrar_ou_validar_gol_ht_00_min20(
            self.db, datetime(2026, 8, 26, 12, 0)
        )
        b = registrar_ou_validar_gol_ht_00_min20(
            self.db, datetime(2099, 1, 1)
        )
        self.assertEqual(a["registrado_em"], b["registrado_em"])
        documento = json.loads(self.db.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE,)
        ).fetchone()["valor"])
        documento["linhagem_sha256"] = "x" * 64
        self.db.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(documento), CHAVE),
        )
        with self.assertRaisesRegex(RuntimeError, "âncora imutável"):
            registrar_ou_validar_gol_ht_00_min20(self.db)

    def test_v5_nao_sobrescreve_ancoras_anteriores(self):
        antigas = (
            "exploracao_sombra_definicao:validacao-gol-ht-00-min20-odd144-red-ok-v3",
            "exploracao_sombra_definicao:validacao-gol-ht-00-min20-odd144-red-ok-v4",
        )
        for antiga in antigas:
            self.db.execute("INSERT INTO metadados VALUES (?,?)", (antiga, '{"original":true}'))
            self.assertNotEqual(antiga, CHAVE)
        registrar_ou_validar_gol_ht_00_min20(self.db)
        for antiga in antigas:
            self.assertEqual('{"original":true}', self.db.execute("SELECT valor FROM metadados WHERE chave=?", (antiga,)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
