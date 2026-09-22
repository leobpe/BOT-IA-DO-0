import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from validacao_gol_ft_reforcado_sombra import (
    registrar_ou_validar_gol_ft_reforcado,
    resumir_validacao_gol_ft_reforcado,
)
from versoes_gol_ft_reforcado import VERSAO_GOL_FT_REFORCADO


class ValidacaoGolFTReforcadoSombraTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id TEXT, criado_em TEXT,
              mercado TEXT, status TEXT, regra_versao TEXT,
              regra_fingerprint TEXT, features_json TEXT
            );
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER PRIMARY KEY, resultado TEXT,
              retorno_unidades REAL
            );
            """
        )
        self.inicio = datetime(2026, 9, 8, 18, 0, 0)
        registrar_ou_validar_gol_ft_reforcado(self.conexao, self.inicio)

    def tearDown(self):
        self.conexao.close()

    def _inserir(self, indice, partida, resultado="green", retorno=0.25,
                  fingerprint="a" * 64, modo="validacao_sombra"):
        features = {"gol_ft_reforcado": {"modo": modo}}
        self.conexao.execute(
            """
            INSERT INTO sinais VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                indice,
                partida,
                (self.inicio + timedelta(minutes=indice)).isoformat(),
                "gol_ft",
                "simulacao",
                VERSAO_GOL_FT_REFORCADO,
                fingerprint,
                json.dumps(features),
            ),
        )
        if resultado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?,?,?)",
                (indice, resultado, retorno),
            )

    def test_coorte_deduplica_partida(self):
        self._inserir(1, "jogo-a")
        self._inserir(2, "jogo-a")
        self._inserir(3, "jogo-b")
        resumo = resumir_validacao_gol_ft_reforcado(self.conexao)
        self.assertEqual(2, resumo["candidatos"])
        self.assertEqual(73, resumo["faltam"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["promocao_automatica"])

    def test_coorte_favoravel_exige_holdout_e_intervalo_positivo(self):
        for indice in range(1, 76):
            self._inserir(indice, f"jogo-{indice}")
        resumo = resumir_validacao_gol_ft_reforcado(self.conexao)
        self.assertEqual("encerrada", resumo["estado"])
        self.assertEqual(
            "favoravel_para_revisao_manual", resumo["decisao"]
        )
        self.assertEqual(50, resumo["desenvolvimento"]["validos"])
        self.assertEqual(25, resumo["holdout"]["validos"])

    def test_fingerprint_misto_bloqueia_conclusao(self):
        for indice in range(1, 76):
            fingerprint = "b" * 64 if indice == 75 else "a" * 64
            self._inserir(
                indice, f"jogo-{indice}", fingerprint=fingerprint
            )
        resumo = resumir_validacao_gol_ft_reforcado(self.conexao)
        self.assertFalse(resumo["linhagem_homogenea"])
        self.assertEqual("linhagem_inconsistente", resumo["decisao"])

    def test_pendente_impede_conclusao(self):
        for indice in range(1, 75):
            self._inserir(indice, f"jogo-{indice}")
        self._inserir(75, "jogo-75", resultado=None)
        resumo = resumir_validacao_gol_ft_reforcado(self.conexao)
        self.assertEqual("aguardando_resultados", resumo["decisao"])


if __name__ == "__main__":
    unittest.main()
