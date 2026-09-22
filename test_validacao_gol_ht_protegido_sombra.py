import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from validacao_gol_ht_protegido_sombra import (
    registrar_ou_validar_gol_ht_protegido,
    resumir_validacao_gol_ht_protegido,
)
from versoes_gol_ht_protegido import VERSAO_GOL_HT_PROTEGIDO


class ValidacaoGolHTProtegidoSombraTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id TEXT, criado_em TEXT,
              mercado TEXT, status TEXT, regra_versao TEXT,
              regra_fingerprint TEXT, odd REAL, features_json TEXT
            );
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER PRIMARY KEY, resultado TEXT,
              retorno_unidades REAL
            );
            """
        )
        self.inicio = datetime(2026, 9, 8, 18, 0, 0)
        registrar_ou_validar_gol_ht_protegido(self.conexao, self.inicio)

    def tearDown(self):
        self.conexao.close()

    def _inserir(self, indice, partida, resultado="green", retorno=0.5,
                  fingerprint="a" * 64, modo="validacao_sombra"):
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?,?,?,?,?,?,?,?,?)",
            (
                indice, partida,
                (self.inicio + timedelta(minutes=indice)).isoformat(),
                "gol_ht", "simulacao", VERSAO_GOL_HT_PROTEGIDO,
                fingerprint, 1.75,
                json.dumps({"gol_ht_protegido": {"modo": modo}}),
            ),
        )
        if resultado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?,?,?)",
                (indice, resultado, retorno),
            )

    def test_deduplica_partida_e_permanece_silenciosa(self):
        self._inserir(1, "a")
        self._inserir(2, "a")
        self._inserir(3, "b")
        resumo = resumir_validacao_gol_ht_protegido(self.conexao)
        self.assertEqual(2, resumo["candidatos"])
        self.assertEqual(98, resumo["faltam"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["promocao_automatica"])

    def test_coorte_favoravel_exige_prova_acima_do_break_even(self):
        for indice in range(1, 101):
            self._inserir(indice, f"jogo-{indice}")
        resumo = resumir_validacao_gol_ht_protegido(self.conexao)
        self.assertEqual("encerrada", resumo["estado"])
        self.assertEqual(
            "favoravel_para_revisao_manual", resumo["decisao"]
        )
        self.assertEqual(70, resumo["desenvolvimento"]["validos"])
        self.assertEqual(30, resumo["holdout"]["validos"])

    def test_linhagem_mista_bloqueia_conclusao(self):
        for indice in range(1, 101):
            self._inserir(
                indice, f"jogo-{indice}",
                fingerprint=("b" * 64 if indice == 100 else "a" * 64),
            )
        resumo = resumir_validacao_gol_ht_protegido(self.conexao)
        self.assertEqual("linhagem_inconsistente", resumo["decisao"])

    def test_pendente_impede_conclusao(self):
        for indice in range(1, 100):
            self._inserir(indice, f"jogo-{indice}")
        self._inserir(100, "jogo-100", resultado=None)
        resumo = resumir_validacao_gol_ht_protegido(self.conexao)
        self.assertEqual("aguardando_resultados", resumo["decisao"])


if __name__ == "__main__":
    unittest.main()
