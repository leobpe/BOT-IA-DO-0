import sqlite3
import unittest

from validacao_gol_ft_tendencia_mais_um import (
    CHAVE, auditar_validacao_gol_ft_tendencia_mais_um,
    registrar_ou_validar_gol_ft_tendencia_mais_um,
)


class ValidacaoGolFTTendenciaMaisUmTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT NOT NULL)"
        )

    def tearDown(self):
        self.db.close()

    def test_registra_e_audita_ancora(self):
        documento = registrar_ou_validar_gol_ft_tendencia_mais_um(
            self.db, registrado_em=__import__("datetime").datetime(
                2026, 8, 26, 13, 0, 0
            ),
        )
        self.assertEqual(100, documento["tamanho_coorte"])
        self.assertEqual(70, documento["desenvolvimento"])
        self.assertEqual(30, documento["holdout"])
        self.assertEqual(1, self.db.execute(
            "SELECT COUNT(*) FROM metadados WHERE chave=?", (CHAVE,)
        ).fetchone()[0])
        self.assertTrue(
            auditar_validacao_gol_ft_tendencia_mais_um(
                self.db, exigir_registro=True,
            )["saudavel"]
        )

    def test_nova_versao_nao_sobrescreve_ancoras_v3_e_v4(self):
        antigas = [
            "exploracao_sombra_definicao:validacao-gol-ft-tendencia-mais-um-" + versao
            for versao in ("v3", "v4")
        ]
        for antiga in antigas:
            self.db.execute("INSERT INTO metadados VALUES (?,?)", (antiga, '{"original":true}'))
            self.assertNotEqual(antiga, CHAVE)
        registrar_ou_validar_gol_ft_tendencia_mais_um(self.db)
        for antiga in antigas:
            self.assertEqual('{"original":true}', self.db.execute("SELECT valor FROM metadados WHERE chave=?", (antiga,)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
