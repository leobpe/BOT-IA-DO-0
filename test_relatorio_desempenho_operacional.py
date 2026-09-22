import json
import sqlite3
import unittest

from relatorio_desempenho_operacional import (
    resumir_desempenho_operacional,
)


class RelatorioDesempenhoOperacionalTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                partida_id INTEGER,
                criado_em TEXT,
                mercado TEXT,
                regra_versao TEXT,
                regra_fingerprint TEXT,
                status TEXT,
                odd REAL,
                motivos_json TEXT,
                features_json TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                resultado TEXT,
                retorno_unidades REAL,
                encerrado_em TEXT
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY,
                sinal_id INTEGER,
                canal TEXT,
                status TEXT,
                provedor TEXT,
                provedor_mensagem_id TEXT
            );
            CREATE TABLE metadados (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );
            """
        )

    def tearDown(self):
        self.conexao.close()

    def _sinal(
        self, identificador, partida, mercado, status, resultado,
        metodo=None, contrafactual=False,
    ):
        features = {}
        if metodo:
            features["exploracao_sombra"] = {"versao": metodo}
        if contrafactual:
            features["avaliacao_contrafactual"] = {
                "versao": "contrafactual-protecoes-gols-v1",
                "protecao": "protecao_tendencias_packball",
            }
        self.conexao.execute(
            """
            INSERT INTO sinais VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identificador,
                partida,
                f"2026-08-28T10:{identificador:02d}:00",
                mercado,
                "regra-v1",
                "fingerprint-v1",
                status,
                1.80,
                "[]",
                json.dumps(features),
            ),
        )
        if resultado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?, ?)",
                (
                    identificador,
                    resultado,
                    0.8 if resultado == "green" else -1.0,
                    "2026-08-28T12:00:00",
                ),
            )

    def _entrega(self, sinal_id, canal, status, provedor=None):
        self.conexao.execute(
            """
            INSERT INTO entregas_alertas
              (sinal_id, canal, status, provedor, provedor_mensagem_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sinal_id,
                canal,
                status,
                provedor,
                "123" if provedor == "telegram" else None,
            ),
        )

    def test_separa_oficial_validacao_bloqueio_e_sombra(self):
        self._sinal(1, 10, "gol_ft", "aprovado", "green")
        self._entrega(1, "-1001", "entregue", "telegram")
        self._sinal(2, 20, "gol_ht", "simulacao", "red")
        self._entrega(2, "-1001:teste", "entregue", "telegram")
        self._sinal(3, 30, "gol_ft", "simulacao", "green")
        self._entrega(3, "gateway:validacao", "filtrado")
        self._sinal(4, 40, "gol_ht", "simulacao", None)

        resumo = resumir_desempenho_operacional(
            self.conexao,
            "2026-08-28T00:00:00",
            "2026-08-29T00:00:00",
        )

        categorias = resumo["categorias"]
        self.assertEqual(categorias["oficial"]["greens"], 1)
        self.assertEqual(categorias["validacao_enviada"]["reds"], 1)
        self.assertEqual(
            categorias["validacao_bloqueada"]["greens"], 1
        )
        self.assertEqual(categorias["sombra_nao_enviada"]["pendentes"], 1)

    def test_separa_contrafactual_de_outras_sombras(self):
        self._sinal(
            1, 10, "gol_ht", "simulacao", "green",
            metodo="contrafactual-protecoes-gols-v1",
            contrafactual=True,
        )
        self._sinal(
            2, 20, "gol_ht", "simulacao", "red", metodo="outro"
        )

        resumo = resumir_desempenho_operacional(
            self.conexao,
            "2026-08-28T00:00:00",
            "2026-08-29T00:00:00",
        )

        self.assertEqual(
            resumo["categorias"]["contrafactual_protecao"]["greens"], 1
        )
        self.assertEqual(
            resumo["categorias"]["sombra_nao_enviada"]["reds"], 1
        )

    def test_exposicao_real_conta_envios_e_amostra_independente_deduplica(self):
        self._sinal(1, 10, "gol_ft", "simulacao", "red")
        self._entrega(1, "-1001:teste", "entregue", "telegram")
        self._sinal(2, 10, "gol_ft", "simulacao", "green")
        self._entrega(2, "-1001:teste", "entregue", "telegram")

        resumo = resumir_desempenho_operacional(
            self.conexao,
            "2026-08-28T00:00:00",
            "2026-08-29T00:00:00",
        )

        grupo = resumo["categorias"]["validacao_enviada"]
        self.assertEqual(grupo["decisoes"], 2)
        self.assertEqual(grupo["greens"], 1)
        self.assertEqual(grupo["reds"], 1)
        self.assertEqual(
            grupo["amostra_independente"]["decisoes"], 1
        )
        self.assertEqual(grupo["amostra_independente"]["reds"], 1)

    def test_separa_challengers_com_mesma_regra_base(self):
        self._sinal(
            1, 10, "gol_ft", "simulacao", "green",
            "gol-ft-capacidade-contextual-v2b",
        )
        self._entrega(1, "-1001:teste", "entregue", "telegram")
        self._sinal(
            2, 10, "gol_ft", "simulacao", "red",
            "gol-ft-tendencia-15-25-mais-um-odd144-v1",
        )
        self._entrega(2, "-1001:teste", "entregue", "telegram")

        resumo = resumir_desempenho_operacional(
            self.conexao,
            "2026-08-28T00:00:00",
            "2026-08-29T00:00:00",
        )

        grupo = resumo["categorias"]["validacao_enviada"]
        self.assertEqual(grupo["amostra_independente"]["decisoes"], 2)
        self.assertEqual(
            grupo["por_metodo"][
                "gol-ft-capacidade-contextual-v2b"
            ]["greens"],
            1,
        )
        self.assertEqual(
            grupo["por_metodo"][
                "gol-ft-tendencia-15-25-mais-um-odd144-v1"
            ]["reds"],
            1,
        )

    def test_carteira_atual_nao_mistura_decisoes_anteriores(self):
        self._sinal(1, 10, "gol_ft", "simulacao", "red")
        self._entrega(1, "-1001:teste", "entregue", "telegram")
        self._sinal(2, 20, "gol_ft", "simulacao", "green")
        self._entrega(2, "-1001:teste", "entregue", "telegram")
        carteira = {
            "versao": "carteira-operacional-epocas-v1",
            "fingerprint": "fp-atual",
            "ativada_em": "2026-08-28T10:02:00",
            "mercados_operacionais": ["gol_ft"],
            "versoes_por_mercado": {"gol_ft": "regra-v1"},
        }
        self.conexao.execute(
            "INSERT INTO metadados(chave, valor) VALUES (?, ?)",
            ("estado_carteira_operacional:atual", json.dumps(carteira)),
        )

        resumo = resumir_desempenho_operacional(
            self.conexao,
            "2026-08-28T00:00:00",
            "2026-08-29T00:00:00",
        )

        amplo = resumo["categorias"]["validacao_enviada"]
        atual = resumo["carteira_operacional_atual"]["desempenho"]
        atual = atual["categorias"]["validacao_enviada"]
        self.assertEqual(2, amplo["decisoes"])
        self.assertEqual(1, atual["decisoes"])
        self.assertEqual(1, atual["greens"])
        self.assertEqual("2026-08-28T10:02:00", (
            resumo["carteira_operacional_atual"]["desde_efetivo"]
        ))


if __name__ == "__main__":
    unittest.main()
