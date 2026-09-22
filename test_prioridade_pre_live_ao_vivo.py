import json
import sqlite3
import unittest
from pathlib import Path

from prioridade_pre_live_ao_vivo import (
    aplicar_prioridade_pre_live,
    carregar_contextos_pre_live,
)


class PrioridadePreLiveAoVivoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_prioridade_pre_live.db"
        self.caminho.unlink(missing_ok=True)
        conexao = sqlite3.connect(self.caminho)
        conexao.executescript("""
            CREATE TABLE bilhetes_pre_live (
                id INTEGER PRIMARY KEY,
                data_alvo TEXT NOT NULL,
                estado TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                bilhete_json TEXT NOT NULL,
                resultado TEXT
            );
            CREATE TABLE entregas_pre_live (bilhete_id INTEGER);
            CREATE TABLE itens_listas_pre_live (bilhete_id INTEGER);
        """)
        bilhete = {
            "pernas": [{
                "fixture_id": 123,
                "jogo": {
                    "mandante": "Eintracht Braunschweig",
                    "visitante": "Hertha BSC",
                },
            }],
        }
        conexao.execute(
            """
            INSERT INTO bilhetes_pre_live (
                id, data_alvo, estado, criado_em, bilhete_json, resultado
            ) VALUES (1, ?, ?, ?, ?, NULL)
            """,
            (
                "2026-08-28",
                "apto_envio_automatico",
                "2026-08-28T10:00:00+00:00",
                json.dumps(bilhete),
            ),
        )
        conexao.execute("INSERT INTO itens_listas_pre_live VALUES (1)")
        conexao.commit()
        conexao.close()

    def tearDown(self):
        self.caminho.unlink(missing_ok=True)

    def test_associa_por_nomes_mesmo_sem_fixture_na_lista_api(self):
        jogos = [{
            "url": "hertha",
            "mandante": "Braunschweig",
            "visitante": "Hertha BSC",
            "placar": "0-0",
            "status": "10 '",
        }]

        diagnostico = aplicar_prioridade_pre_live(
            jogos,
            [],
            self.caminho,
            data_alvo="2026-08-28",
        )

        self.assertEqual(diagnostico["jogos_associados"], 1)
        self.assertEqual(diagnostico["confirmados_associados"], 1)
        self.assertTrue(jogos[0]["pre_live_prioritario"])
        self.assertTrue(jogos[0]["pre_live_confirmado"])
        self.assertEqual(jogos[0]["pre_live_fixture_id"], 123)

    def test_desativada_nao_marca_jogo(self):
        jogos = [{"url": "jogo"}]

        diagnostico = aplicar_prioridade_pre_live(
            jogos, [], self.caminho, ativa=False
        )

        self.assertEqual(diagnostico["estado"], "desativada")
        self.assertNotIn("pre_live_prioritario", jogos[0])

    def test_contexto_preliminar_causal_fornece_fixture_sem_promover(self):
        bilhete = {
            "pernas": [{
                "fixture_id": 456,
                "qualidade_contexto": 85,
                "probabilidade_modelo": 0.73,
                "mercado": "total_gols",
                "selecao": "over_2.5",
                "modelo": {"lambda_total": 2.8},
                "jogo": {
                    "mandante": "San Antonio Bulo Bulo",
                    "visitante": "Aurora",
                    "inicio": "2026-08-28T18:00:00-04:00",
                },
            }],
        }
        conexao = sqlite3.connect(self.caminho)
        conexao.execute(
            """
            INSERT INTO bilhetes_pre_live (
                id, data_alvo, estado, criado_em, bilhete_json, resultado
            ) VALUES (2, ?, ?, ?, ?, NULL)
            """,
            (
                "2026-08-28",
                "preliminar_aguardando_escalacao",
                "2026-08-28T20:00:00+00:00",
                json.dumps(bilhete),
            ),
        )
        conexao.commit()
        conexao.close()
        jogos = [{
            "url": "san-antonio",
            "mandante": "San Antonio Bulo Bulo",
            "visitante": "Aurora",
            "placar": "0-0",
            "status": "8 '",
        }]

        diagnostico = aplicar_prioridade_pre_live(
            jogos, [], self.caminho, data_alvo="2026-08-28"
        )

        self.assertEqual(diagnostico["jogos_contexto_associados"], 1)
        self.assertEqual(jogos[0]["pre_live_fixture_id"], 456)
        self.assertTrue(jogos[0]["pre_live_contexto_disponivel"])
        self.assertTrue(jogos[0]["pre_live_contexto"]["causal"])
        self.assertNotIn("pre_live_prioritario", jogos[0])

    def test_contexto_criado_depois_do_inicio_e_rejeitado(self):
        bilhete = {
            "pernas": [{
                "fixture_id": 789,
                "qualidade_contexto": 90,
                "modelo": {"lambda_total": 3.0},
                "jogo": {
                    "mandante": "Time C",
                    "visitante": "Time D",
                    "inicio": "2026-08-28T18:00:00+00:00",
                },
            }],
        }
        conexao = sqlite3.connect(self.caminho)
        conexao.execute(
            """
            INSERT INTO bilhetes_pre_live (
                id, data_alvo, estado, criado_em, bilhete_json, resultado
            ) VALUES (3, ?, ?, ?, ?, NULL)
            """,
            (
                "2026-08-28", "preliminar_aguardando_escalacao",
                "2026-08-28T18:01:00+00:00", json.dumps(bilhete),
            ),
        )
        conexao.commit()
        conexao.close()

        diagnostico = carregar_contextos_pre_live(
            self.caminho, data_alvo="2026-08-28"
        )

        self.assertNotIn(789, diagnostico["contextos"])
        self.assertEqual(diagnostico["rejeitados_nao_causais"], 2)


if __name__ == "__main__":
    unittest.main()
