import sqlite3
import unittest
from datetime import datetime

from validacao_top_criterios_gols import (
    VERSAO_VALIDACAO_FT, VERSAO_VALIDACAO_HT,
    registrar_ou_validar_top_criterios_gols,
)


class ValidacaoTopCriteriosGolsTest(unittest.TestCase):
    def test_registra_ancoras_ht_e_ft_separadas(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT NOT NULL)"
        )
        documentos = registrar_ou_validar_top_criterios_gols(
            db, datetime(2026, 8, 26, 15, 0, 0)
        )
        self.assertEqual(VERSAO_VALIDACAO_HT, documentos["ht"]["versao"])
        self.assertEqual(VERSAO_VALIDACAO_FT, documentos["ft"]["versao"])
        self.assertEqual(2, db.execute(
            "SELECT COUNT(*) FROM metadados"
        ).fetchone()[0])
        db.close()


if __name__ == "__main__":
    unittest.main()
