import json
import sqlite3
import unittest

from relatorio_odds_periodos import (
    diagnosticar_fontes_odds_periodos,
    resumir_odds_escanteios_periodos,
)


class RelatorioOddsPeriodosTest(unittest.TestCase):
    def test_exactly_nunca_e_contado_como_linha_asiatica(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY, coletado_em TEXT
            );
            CREATE TABLE odds (
                id INTEGER PRIMARY KEY, snapshot_id INTEGER,
                tipo TEXT, mercado TEXT, dados TEXT, estrutura_json TEXT
            );
            INSERT INTO snapshots VALUES (1, '2026-07-21T12:00:00');
            """
        )
        estruturas = [
            {
                "categoria": "escanteios",
                "tipo_mercado": "asiatico",
                "ofertas_periodos": {
                    "1T": {
                        "formato": "tres_opcoes_exactly",
                        "ofertas": [{"linha": 4.5, "exatamente": 3.0,
                                     "over": 1.8, "under": 1.9}],
                    },
                    "2T": {
                        "formato": "duas_opcoes",
                        "ofertas": [{"linha": 5.5, "over": 1.85,
                                     "under": 1.95}],
                    },
                },
            },
            {
                "categoria": "gols",
                "ofertas_periodos": {
                    "1T": {"formato": "duas_opcoes", "ofertas": [
                        {"linha": 1.5, "over": 1.8, "under": 2.0}
                    ]}
                },
            },
        ]
        conexao.executemany(
            "INSERT INTO odds VALUES (?, 1, 'ao_vivo', ?, '', ?)",
            [
                (1, "Escanteios", json.dumps(estruturas[0])),
                (2, "Gols", json.dumps(estruturas[1])),
            ],
        )

        resumo = resumir_odds_escanteios_periodos(conexao)

        self.assertFalse(resumo["1T"]["mapeada"])
        self.assertEqual(resumo["1T"]["exactly"], 1)
        self.assertTrue(resumo["2T"]["mapeada"])
        self.assertEqual(resumo["2T"]["asiaticas"], 1)
        self.assertEqual(resumo["2T"]["linhas_asiaticas"], [5.5])
        self.assertEqual(resumo["2T"]["fontes"], ["packball"])
        conexao.close()

    def test_catalogo_sem_oferta_real_nao_comprova_fonte(self):
        resumo = {
            "1T": {"mapeada": False, "exactly": 10},
            "2T": {"mapeada": False, "exactly": 12},
        }
        catalogo = {
            "mapeamentos": {"51": {"coerente": True}},
            "candidatos_asiatico_2t": [],
        }
        estado_api = {
            "por_bet": {
                "51": {
                    "consultas": 208,
                    "ofertas_anexadas": 0,
                }
            }
        }

        diagnostico = diagnosticar_fontes_odds_periodos(
            resumo, catalogo, estado_api
        )

        self.assertEqual(
            diagnostico["1T"]["diagnostico_fonte"],
            "catalogada_sem_oferta_real",
        )
        self.assertEqual(diagnostico["1T"]["consultas_api"], 208)
        self.assertEqual(
            diagnostico["2T"]["diagnostico_fonte"],
            "somente_exactly_tres_opcoes",
        )
        self.assertFalse(diagnostico["2T"]["catalogada_api"])

    def test_oferta_persistida_e_a_unica_prova_suficiente(self):
        resumo = {
            "1T": {
                "mapeada": True,
                "exactly": 4,
                "asiaticas": 1,
                "fontes": ["api_football"],
            },
            "2T": {"mapeada": False, "exactly": 0},
        }

        diagnostico = diagnosticar_fontes_odds_periodos(resumo)

        self.assertEqual(
            diagnostico["1T"]["diagnostico_fonte"],
            "fonte_real_comprovada",
        )

    def test_tipo_asiatico_do_periodo_prevalece_sobre_mercado_pai(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY, coletado_em TEXT
            );
            CREATE TABLE odds (
                id INTEGER PRIMARY KEY, snapshot_id INTEGER,
                tipo TEXT, mercado TEXT, dados TEXT, estrutura_json TEXT
            );
            INSERT INTO snapshots VALUES (1, '2026-07-28T12:00:00');
            """
        )
        estrutura = {
            "categoria": "escanteios",
            "tipo_mercado": "total",
            "fonte": "packball",
            "ofertas_periodos": {
                "1T": {
                    "formato": "duas_opcoes",
                    "tipo_mercado": "asiatico",
                    "ofertas": [
                        {"linha": 4.5, "over": 1.85, "under": 1.95}
                    ],
                }
            },
        }
        conexao.execute(
            "INSERT INTO odds VALUES (1, 1, 'ao_vivo', ?, '', ?)",
            ("Corrida De Escanteios", json.dumps(estrutura)),
        )

        resumo = resumir_odds_escanteios_periodos(conexao)

        self.assertTrue(resumo["1T"]["mapeada"])
        self.assertEqual(resumo["1T"]["asiaticas"], 1)
        self.assertEqual(resumo["1T"]["linhas_asiaticas"], [4.5])
        self.assertEqual(resumo["1T"]["fontes"], ["packball"])
        conexao.close()


if __name__ == "__main__":
    unittest.main()
