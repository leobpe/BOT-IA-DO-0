import json
import sqlite3
import unittest

from avaliacao_probabilidade_sem_vig import avaliar


class AvaliacaoProbabilidadeSemVigTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE snapshots (id INTEGER PRIMARY KEY, placar TEXT);
            CREATE TABLE odds (
                id INTEGER PRIMARY KEY, snapshot_id INTEGER, tipo TEXT,
                mercado TEXT, dados TEXT, estrutura_json TEXT
            );
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                snapshot_id INTEGER, criado_em TEXT, mercado TEXT,
                linha TEXT, odd REAL, probabilidade_calibrada REAL,
                regra_versao TEXT, status TEXT, features_json TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY, resultado TEXT,
                retorno_unidades REAL
            );
            """
        )

    def tearDown(self):
        self.conexao.close()

    def _inserir(
        self, identificador, *, partida_id=10, gols=0, placar="0-0",
        odd=1.70, resultado="green", retorno=0.70,
        selecoes="1: 1.70 2: 3.20 No: 5.00",
    ):
        instante = f"2026-09-01T12:{identificador:02d}:00"
        self.conexao.execute(
            "INSERT INTO snapshots VALUES (?, ?)",
            (identificador, placar),
        )
        self.conexao.execute(
            "INSERT INTO odds VALUES (?, ?, 'ao_vivo', ?, ?, '{}')",
            (identificador, identificador, "Próximo Gol", selecoes),
        )
        self.conexao.execute(
            """
            INSERT INTO sinais VALUES (?, ?, ?, ?, 'proximo_gol',
                'casa', ?, NULL, 'regra-teste', 'auditoria', ?)
            """,
            (
                identificador,
                partida_id,
                identificador,
                instante,
                odd,
                json.dumps({"gols_atuais": gols}),
            ),
        )
        self.conexao.execute(
            "INSERT INTO resultados_sinais VALUES (?, ?, ?)",
            (identificador, resultado, retorno),
        )

    def test_reconstroi_trio_bruto_do_mesmo_snapshot(self):
        self._inserir(1)

        resumo = avaliar(self.conexao, "proximo_gol", "regra-teste")

        esperado = (1 / 1.70) / (1 / 1.70 + 1 / 3.20 + 1 / 5.00)
        self.assertEqual(1, resumo["cobertura_referencia_sem_vig"])
        self.assertEqual(1.0, resumo["taxa_cobertura"])
        self.assertAlmostEqual(
            esperado,
            resumo["metricas"]["probabilidade_sem_vig_media"],
            places=6,
        )
        self.assertEqual(1, resumo["metricas"]["greens"])
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["promocao_automatica"])

    def test_nao_pareia_odd_selecionada_diferente(self):
        self._inserir(1, odd=1.71)

        resumo = avaliar(self.conexao, "proximo_gol", "regra-teste")

        self.assertEqual(0, resumo["cobertura_referencia_sem_vig"])
        self.assertEqual(
            1,
            resumo["exclusoes"][
                "mercado_exato_incompleto_ou_ambiguo"
            ],
        )

    def test_independencia_nao_repete_estados_do_mesmo_jogo(self):
        self._inserir(1, gols=0, placar="0-0")
        self._inserir(2, gols=0, placar="0-0")
        self._inserir(
            3,
            gols=1,
            placar="1-0",
            resultado="red",
            retorno=-1.0,
        )

        resumo = avaliar(self.conexao, "proximo_gol", "regra-teste")

        self.assertEqual(3, resumo["resolvidas_consultadas"])
        self.assertEqual(1, resumo["estados_independentes"])
        self.assertEqual(1, resumo["unidades_independentes"])
        self.assertEqual(1, resumo["cobertura_referencia_sem_vig"])
        self.assertEqual(1, resumo["metricas"]["greens"])
        self.assertEqual(0, resumo["metricas"]["reds"])
        self.assertEqual(
            "coorte_selecao+partida", resumo["criterio_independencia"]
        )
        self.assertFalse(resumo["vantagem_estatistica_descritiva"])

    def test_primeira_unidade_pendente_nao_e_trocada_pela_resolvida(self):
        self._inserir(1, resultado="green", retorno=0.70)
        self._inserir(
            2, resultado="green", retorno=0.70, partida_id=10
        )
        self.conexao.execute(
            "DELETE FROM resultados_sinais WHERE sinal_id=1"
        )

        resumo = avaliar(self.conexao, "proximo_gol", "regra-teste")

        self.assertEqual(2, resumo["candidatos_consultados"])
        self.assertEqual(1, resumo["resolvidas_consultadas"])
        self.assertEqual(1, resumo["unidades_independentes"])
        self.assertEqual(0, resumo["estados_independentes"])
        self.assertEqual(1, resumo["resultados_pendentes_ou_invalidos"])
        self.assertTrue(resumo["selecao_antes_do_resultado"])
        self.assertFalse(resumo["vantagem_estatistica_descritiva"])

    def test_nao_declara_edge_misturando_oficial_e_exploracao(self):
        self._inserir(1, partida_id=10)
        self._inserir(2, partida_id=11)
        self.conexao.execute(
            "UPDATE sinais SET status='aprovado' WHERE id=1"
        )
        self.conexao.execute(
            "UPDATE sinais SET status='simulacao', features_json=? WHERE id=2",
            (json.dumps({
                "gols_atuais": 0,
                "exploracao_sombra": {"versao": "experimento-v1"},
            }),),
        )

        resumo = avaliar(self.conexao, "proximo_gol", "regra-teste")

        self.assertEqual(
            {"aprovado": 1, "sombra:experimento-v1": 1},
            resumo["coortes_selecao"],
        )
        self.assertFalse(resumo["coorte_homogenea"])
        self.assertFalse(resumo["vantagem_estatistica_descritiva"])


if __name__ == "__main__":
    unittest.main()
