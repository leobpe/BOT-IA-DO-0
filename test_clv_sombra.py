import sqlite3
import unittest
from pathlib import Path
from uuid import uuid4

from clv_sombra import (
    PRIMEIRO_SINAL_INSTRUMENTADO,
    VERSAO,
    _metricas,
    _por_partida,
    carregar_sinais_coorte,
    executar,
)


class CarregarCoorteTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE snapshots (
              id INTEGER PRIMARY KEY, partida_id INTEGER, coletado_em TEXT,
              placar TEXT, estatisticas_json TEXT
            );
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id INTEGER, snapshot_id INTEGER,
              criado_em TEXT, mercado TEXT, linha TEXT, odd REAL,
              status TEXT, regra_versao TEXT, features_json TEXT
            );
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER PRIMARY KEY, encerrado_em TEXT, resultado TEXT
            );
            """
        )
        self.conexao.execute(
            "INSERT INTO snapshots VALUES (1,10,'2026-09-20T10:00:00','0-0','{}')"
        )

    def tearDown(self):
        self.conexao.close()

    def _sinal(self, sinal_id, *, status="simulacao", mercado="gol_ft",
               encerrado="2026-09-20T10:30:00"):
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?,10,1,'2026-09-20T10:00:00',?,'2.5',"
            "1.8,?,'v1','{}')",
            (sinal_id, mercado, status),
        )
        if encerrado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?,?,'green')",
                (sinal_id, encerrado),
            )

    def test_carrega_apenas_o_status_pedido(self):
        self._sinal(PRIMEIRO_SINAL_INSTRUMENTADO)
        self._sinal(PRIMEIRO_SINAL_INSTRUMENTADO + 1, status="aprovado")
        sinais = carregar_sinais_coorte(self.conexao, ("simulacao",))
        self.assertEqual(
            [PRIMEIRO_SINAL_INSTRUMENTADO], [s["id"] for s in sinais]
        )

    def test_ignora_sinal_anterior_a_instrumentacao(self):
        # Sem cotacao de entrada congelada nao ha comparacao possivel, e o
        # historico anterior e irrecuperavel.
        self._sinal(PRIMEIRO_SINAL_INSTRUMENTADO - 1)
        self.assertEqual([], carregar_sinais_coorte(self.conexao, ("simulacao",)))

    def test_ignora_sinal_sem_liquidacao(self):
        self._sinal(PRIMEIRO_SINAL_INSTRUMENTADO, encerrado=None)
        self.assertEqual([], carregar_sinais_coorte(self.conexao, ("simulacao",)))

    def test_ignora_mercado_nao_suportado(self):
        self._sinal(PRIMEIRO_SINAL_INSTRUMENTADO, mercado="mercado_inventado")
        self.assertEqual([], carregar_sinais_coorte(self.conexao, ("simulacao",)))

    def test_canal_marca_a_coorte_como_sombra(self):
        # avaliar_sinal usa o sufixo para nunca confundir com entrega real.
        self._sinal(PRIMEIRO_SINAL_INSTRUMENTADO)
        sinal = carregar_sinais_coorte(self.conexao, ("simulacao",))[0]
        self.assertTrue(sinal["canal"].endswith(":sombra"))

    def test_entregue_em_usa_a_decisao(self):
        self._sinal(PRIMEIRO_SINAL_INSTRUMENTADO)
        sinal = carregar_sinais_coorte(self.conexao, ("simulacao",))[0]
        self.assertEqual(sinal["criado_em"], sinal["entregue_em"])


class PorPartidaTest(unittest.TestCase):
    def test_mantem_uma_unidade_por_partida(self):
        itens = [
            {"sinal_id": 3, "partida_id": 1, "clv_probabilidade_pontos": 0.9},
            {"sinal_id": 1, "partida_id": 1, "clv_probabilidade_pontos": 0.1},
            {"sinal_id": 2, "partida_id": 2, "clv_probabilidade_pontos": 0.5},
        ]
        unidades = _por_partida(itens)
        self.assertEqual(2, len(unidades))

    def test_fica_o_primeiro_sinal_e_nao_o_melhor(self):
        # Escolher o melhor da partida seria selecao pelo resultado.
        itens = [
            {"sinal_id": 9, "partida_id": 1, "clv_probabilidade_pontos": 0.9},
            {"sinal_id": 4, "partida_id": 1, "clv_probabilidade_pontos": -0.2},
        ]
        self.assertEqual(4, _por_partida(itens)[0]["sinal_id"])


class MetricasTest(unittest.TestCase):
    def test_amostra_vazia_nao_inventa_numero(self):
        self.assertEqual(
            {"unidades": 0, "estado_evidencia": "amostra_insuficiente"},
            _metricas([]),
        )

    def test_marca_amostra_insuficiente_abaixo_de_trinta(self):
        self.assertEqual(
            "amostra_insuficiente", _metricas([0.1] * 29)["estado_evidencia"]
        )
        self.assertEqual(
            "amostra_suficiente", _metricas([0.1] * 30)["estado_evidencia"]
        )

    def test_intervalo_ausente_com_uma_unidade(self):
        self.assertIsNone(_metricas([0.1])["intervalo_media_95"])

    def test_proporcao_favoravel_conta_apenas_positivos(self):
        resultado = _metricas([0.1, -0.1, 0.0, 0.2])
        self.assertEqual(0.5, resultado["proporcao_movimento_favoravel"])

    def test_intervalo_cerca_a_media(self):
        resultado = _metricas([0.0, 0.1, 0.2, 0.3, 0.4])
        inferior, superior = resultado["intervalo_media_95"]
        self.assertLess(inferior, resultado["media_pontos_probabilidade"])
        self.assertGreater(superior, resultado["media_pontos_probabilidade"])


class ExecutarTest(unittest.TestCase):
    def test_banco_ausente_falha_fechado(self):
        caminho = Path.cwd() / f".teste_clv_sombra_{uuid4().hex}.db"
        resultado = executar(caminho)
        self.assertEqual("banco_ausente", resultado["erro"])
        self.assertEqual(VERSAO, resultado["versao"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["telegram"])
        self.assertFalse(resultado["calibracao"])
        self.assertFalse(resultado["promocao_automatica"])


if __name__ == "__main__":
    unittest.main()
