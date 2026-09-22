import json
import sqlite3
import unittest
from datetime import datetime

from gols_capacidade_contextual_v2 import LINHAGEM, VERSAO_GOL_FT
from validacao_gols_capacidade_contextual_v2 import (
    CHAVE_DEFINICAO,
    registrar_ou_validar_grupo_ft_capacidade_contextual_v2,
    registrar_ou_validar_gols_capacidade_contextual_v2,
    resumir_grupo_ft_capacidade_contextual_v2,
    resumir_validacao_gols_capacidade_contextual_v2,
)


class TestValidacaoGolsCapacidadeContextualV2(unittest.TestCase):
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
            sinal_id INTEGER PRIMARY KEY, resultado TEXT, retorno_unidades REAL
          );
          CREATE TABLE entregas_alertas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sinal_id INTEGER, canal TEXT, status TEXT
          );
        """)

    def tearDown(self):
        self.db.close()

    def _sinal(
        self, sid, partida, segmento, resultado="green", retorno=0.8,
        entregue=False,
    ):
        features = {
            "exploracao_sombra": {"versao": VERSAO_GOL_FT},
            "gol_capacidade_contextual_v2": {
                "linhagem_sha256": LINHAGEM,
                "segmento_competicao": segmento,
            },
        }
        self.db.execute(
            "INSERT INTO sinais VALUES (?, ?, ?, 'gol_ft', 'simulacao', ?)",
            (sid, partida, f"2026-08-25T08:{sid:02d}:00", json.dumps(features)),
        )
        self.db.execute(
            "INSERT INTO resultados_sinais VALUES (?, ?, ?)",
            (sid, resultado, retorno),
        )
        if entregue:
            self.db.execute(
                """
                INSERT INTO entregas_alertas(sinal_id, canal, status)
                VALUES (?, 'telegram-gols:teste', 'entregue')
                """,
                (sid,),
            )

    def test_ancora_e_imutavel(self):
        marco = datetime(2026, 8, 25, 8, 0)
        primeiro = registrar_ou_validar_gols_capacidade_contextual_v2(self.db, marco)
        segundo = registrar_ou_validar_gols_capacidade_contextual_v2(
            self.db, datetime(2099, 1, 1)
        )
        self.assertEqual(
            primeiro["definicao"]["registrado_em"],
            segundo["definicao"]["registrado_em"],
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
            registrar_ou_validar_gols_capacidade_contextual_v2(self.db)

    def test_deduplica_e_separa_profissional_de_sub21(self):
        registrar_ou_validar_gols_capacidade_contextual_v2(
            self.db, datetime(2026, 8, 25, 8, 0)
        )
        self._sinal(1, 10, "profissional")
        self._sinal(2, 10, "profissional", "red", -1.0)
        self._sinal(3, 20, "sub21")
        self.db.commit()
        resumo = resumir_validacao_gols_capacidade_contextual_v2(self.db)
        profissional = resumo["por_braco_segmento"][f"{VERSAO_GOL_FT}|profissional"]
        sub21 = resumo["por_braco_segmento"][f"{VERSAO_GOL_FT}|sub21"]
        self.assertEqual(1, profissional["candidatos"])
        self.assertEqual(1, profissional["greens"])
        self.assertEqual(1, sub21["candidatos"])
        self.assertEqual("aguardando_amostra_futura", profissional["decisao_estatistica"])

    def test_coorte_grupo_conta_so_entregues_e_deduplica_partida(self):
        registrar_ou_validar_grupo_ft_capacidade_contextual_v2(
            self.db, datetime(2026, 8, 25, 8, 0)
        )
        self._sinal(1, 10, "profissional", entregue=True)
        self._sinal(2, 10, "profissional", "red", -1.0, entregue=True)
        self._sinal(3, 20, "sub21", entregue=False)
        self._sinal(4, 30, "sub21", entregue=True)
        self.db.commit()

        resumo = resumir_grupo_ft_capacidade_contextual_v2(self.db)

        self.assertEqual(2, resumo["candidatos_coorte"])
        self.assertEqual(LINHAGEM, resumo["linhagem_sha256"])
        self.assertEqual(2, resumo["validos"])
        self.assertEqual(1, resumo["por_segmento"]["profissional"]["validos"])
        self.assertEqual(1, resumo["por_segmento"]["sub21"]["validos"])
        self.assertEqual("aguardando_amostra_futura", resumo["decisao_estatistica"])
        self.assertFalse(resumo["rollback_recomendado"])

    def test_coorte_grupo_recomenda_rollback_so_com_evidencia_forte(self):
        registrar_ou_validar_grupo_ft_capacidade_contextual_v2(
            self.db, datetime(2026, 8, 25, 8, 0)
        )
        for sid in range(1, 21):
            self._sinal(
                sid, sid, "profissional", "red", -1.0, entregue=True
            )
        self.db.commit()

        resumo = resumir_grupo_ft_capacidade_contextual_v2(self.db)

        self.assertEqual(20, resumo["validos"])
        self.assertEqual("evidencia_desfavoravel", resumo["decisao_estatistica"])
        self.assertTrue(resumo["alerta_desfavoravel"])
        self.assertTrue(resumo["rollback_recomendado"])


if __name__ == "__main__":
    unittest.main()
