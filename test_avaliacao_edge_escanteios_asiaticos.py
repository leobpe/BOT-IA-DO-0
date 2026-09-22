import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from avaliacao_edge_escanteios_asiaticos import avaliar


class AvaliacaoEdgeEscanteiosAsiaticosTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE partidas (
                id INTEGER PRIMARY KEY, pais TEXT, liga TEXT
            );
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY, partida_id INTEGER, placar TEXT
            );
            CREATE TABLE odds (
                id INTEGER PRIMARY KEY, snapshot_id INTEGER, tipo TEXT,
                mercado TEXT, dados TEXT, estrutura_json TEXT
            );
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                snapshot_id INTEGER, criado_em TEXT, mercado TEXT,
                linha TEXT, odd REAL, pontuacao_tecnica REAL,
                probabilidade_calibrada REAL, regra_versao TEXT,
                status TEXT, features_json TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY, encerrado_em TEXT,
                resultado TEXT, retorno_unidades REAL,
                fonte_resultado TEXT
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY, sinal_id INTEGER, canal TEXT,
                status TEXT
            );
            """
        )

    def tearDown(self):
        self.conexao.close()

    def _inserir(
        self, identificador, *, partida_id=None, status="aprovado",
        linha=8.5, odd=1.90, under=1.90, resultado="green",
        retorno=0.90, minuto=70, atuais=8, sombra=None,
        entregue=False, inserir_resultado=True,
    ):
        partida_id = partida_id or identificador
        features = {
            "minuto": minuto,
            "escanteios_atuais": atuais,
            "fonte_odds": "fonte_teste",
            "bookmaker_odds": "casa_teste",
        }
        if sombra:
            features["exploracao_sombra"] = {"versao": sombra}
        criado_em = (
            datetime(2026, 9, 1, 12, 0)
            + timedelta(minutes=identificador)
        )
        self.conexao.execute(
            "INSERT OR IGNORE INTO partidas VALUES (?, 'BR', 'Liga Teste')",
            (partida_id,),
        )
        self.conexao.execute(
            "INSERT INTO snapshots VALUES (?, ?, '0-0')",
            (identificador, partida_id),
        )
        estrutura = {
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "fonte": "fonte_teste",
            "bookmaker": "casa_teste",
            "ofertas": [{
                "linha": linha,
                "over": odd,
                "under": under,
                "fonte": "fonte_teste",
                "bookmaker": "casa_teste",
            }],
        }
        self.conexao.execute(
            "INSERT INTO odds VALUES (?, ?, 'ao_vivo', ?, '', ?)",
            (
                identificador,
                identificador,
                "Asian Corners",
                json.dumps(estrutura),
            ),
        )
        self.conexao.execute(
            """
            INSERT INTO sinais VALUES (?, ?, ?, ?,
                'escanteios_ft_asiatico', ?, ?, 80, NULL,
                'regra-teste', ?, ?)
            """,
            (
                identificador,
                partida_id,
                identificador,
                criado_em.isoformat(),
                str(linha),
                odd,
                status,
                json.dumps(features),
            ),
        )
        if inserir_resultado:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?, ?, 'teste')",
                (
                    identificador,
                    (criado_em + timedelta(hours=2)).isoformat(),
                    resultado,
                    retorno,
                ),
            )
        if entregue:
            self.conexao.execute(
                "INSERT INTO entregas_alertas VALUES (?, ?, 'chat:teste', 'entregue')",
                (identificador, identificador),
            )

    def test_separa_oficial_das_versoes_sombra(self):
        self._inserir(1, status="aprovado", entregue=True)
        self._inserir(2, status="simulacao", sombra="exp-v1")
        self._inserir(3, status="simulacao", sombra="exp-v2")

        resumo = avaliar(self.conexao, "regra-teste")

        self.assertEqual(1, resumo["por_coorte"]["oficial"]["amostra"])
        self.assertEqual(
            1, resumo["por_coorte"]["sombra:exp-v1"]["amostra"]
        )
        self.assertEqual(
            1, resumo["por_coorte"]["sombra:exp-v2"]["amostra"]
        )
        self.assertEqual(
            1, resumo["por_coorte"]["oficial"]["entradas_entregues"]
        )
        self.assertEqual(1, resumo["oficial_elegivel"]["amostra"])
        self.assertEqual(1, resumo["oficial_entregue"]["amostra"])
        self.assertEqual(
            "primeiras_100_entradas_oficiais_entregues_independentes_por_"
            "partida_selecionadas_antes_do_resultado",
            resumo["revisao_operacional"]["populacao_decisao"],
        )
        self.assertFalse(resumo["revisao_operacional"]["todos_satisfeitos"])

    def test_entregue_e_deduplicado_depois_do_filtro_de_entrega(self):
        self._inserir(
            1, partida_id=99, resultado="red", retorno=-1.0,
            entregue=False,
        )
        self._inserir(
            2, partida_id=99, resultado="green", retorno=0.90,
            entregue=True,
        )

        resumo = avaliar(self.conexao, "regra-teste")

        self.assertEqual(1, resumo["oficial_elegivel"]["amostra"])
        self.assertEqual(-1.0, resumo["oficial_elegivel"]["roi"])
        self.assertEqual(1, resumo["oficial_entregue"]["amostra"])
        self.assertEqual(0.9, resumo["oficial_entregue"]["roi"])
        self.assertEqual(
            1,
            resumo["divisao_cronologica_oficial_entregue"]
            ["desenvolvimento_70"]["amostra"],
        )

    def test_preserva_void_e_half_green_no_roi(self):
        self._inserir(
            1, linha=8.0, atuais=8, resultado="void", retorno=0.0
        )
        self._inserir(
            2, linha=8.25, atuais=8,
            resultado="half_green", retorno=0.45,
        )

        resumo = avaliar(self.conexao, "regra-teste")
        oficial = resumo["por_coorte"]["oficial"]

        self.assertEqual(2, oficial["amostra"])
        self.assertEqual(1, oficial["voids"])
        self.assertEqual(1, oficial["half_greens"])
        self.assertAlmostEqual(0.225, oficial["roi"])
        self.assertEqual(0, oficial["avaliacoes_binarias_sem_push"])
        self.assertIn("inteira", resumo["oficial_por_tipo_linha"])
        self.assertIn("quarto_25", resumo["oficial_por_tipo_linha"])

    def test_holdout_so_comeca_depois_das_70_unidades_de_desenvolvimento(self):
        for identificador in range(1, 11):
            green = identificador <= 7
            self._inserir(
                identificador,
                resultado="green" if green else "red",
                retorno=0.90 if green else -1.0,
            )

        resumo = avaliar(self.conexao, "regra-teste")
        divisao = resumo["divisao_cronologica_oficial"]

        self.assertEqual(10, divisao["desenvolvimento_70"]["amostra"])
        self.assertEqual(0, divisao["holdout_30"]["amostra"])
        self.assertEqual(7, divisao["desenvolvimento_70"]["greens_cheios"])
        self.assertEqual(3, divisao["desenvolvimento_70"]["reds_cheios"])
        self.assertIsNone(divisao["holdout_30"]["roi"])
        self.assertTrue(divisao["particao_definida_antes_do_resultado"])

    def test_primeira_pendente_nao_e_substituida_por_duplicata_resolvida(self):
        self._inserir(
            1, partida_id=99, entregue=True, inserir_resultado=False,
        )
        self._inserir(
            2, partida_id=99, entregue=True,
            resultado="green", retorno=0.90,
        )

        resumo = avaliar(self.conexao, "regra-teste")
        auditoria = resumo["auditoria_oficial_entregue"]

        self.assertEqual(2, resumo["candidatas_consultadas"])
        self.assertEqual(1, resumo["resolvidas_consultadas"])
        self.assertEqual(1, auditoria["unidades_independentes"])
        self.assertEqual(1, auditoria["duplicadas_excluidas"])
        self.assertEqual(0, resumo["oficial_entregue"]["amostra"])
        self.assertEqual(
            1,
            auditoria["resultado_coorte_fixa"]["motivos"]
            ["resultado_ausente"],
        )
        self.assertFalse(
            resumo["revisao_operacional"]["criterios"]
            ["resultados_e_contratos_completos"]
        )

    def test_particao_fixa_antes_do_resultado_nao_puxa_unidade_101(self):
        for identificador in range(1, 102):
            if identificador <= 70 or identificador == 101:
                resultado, retorno = "green", 0.90
            else:
                resultado, retorno = "red", -1.0
            self._inserir(
                identificador,
                resultado=resultado,
                retorno=retorno,
                inserir_resultado=identificador != 71,
            )

        resumo = avaliar(self.conexao, "regra-teste")
        fixo = resumo["por_coorte"]["oficial"]
        todas = resumo[
            "por_coorte_todas_independentes_diagnostico"
        ]["oficial"]
        divisao = resumo["divisao_cronologica_oficial"]
        auditoria = resumo["auditoria_por_coorte"]["oficial"]

        self.assertEqual(100, auditoria["unidades_coorte_fixa"])
        self.assertEqual(1, auditoria["unidades_pos_coorte_fixa_somente_diagnostico"])
        self.assertEqual(99, fixo["amostra"])
        self.assertEqual(100, todas["amostra"])
        self.assertEqual(70, fixo["greens_cheios"])
        self.assertEqual(71, todas["greens_cheios"])
        self.assertEqual(70, divisao["desenvolvimento_70"]["amostra"])
        self.assertEqual(29, divisao["holdout_30"]["amostra"])
        self.assertEqual(30, divisao["unidades_holdout_30"])
        self.assertEqual(
            1,
            divisao["auditoria_holdout_30"]["motivos"]
            ["resultado_ausente"],
        )

    def test_retorno_incompativel_falha_fechado(self):
        self._inserir(1, resultado="green", retorno=-1.0, entregue=True)

        resumo = avaliar(self.conexao, "regra-teste")

        self.assertEqual(0, resumo["oficial_entregue"]["amostra"])
        self.assertEqual(
            1,
            resumo["auditoria_oficial_entregue"]
            ["resultado_coorte_fixa"]["motivos"]
            ["retorno_incompativel_com_resultado_e_odd"],
        )

    def test_linha_meia_tem_avaliacao_binaria_sem_vig(self):
        self._inserir(
            1, linha=8.5, odd=2.0, under=2.0, retorno=1.0
        )

        resumo = avaliar(self.conexao, "regra-teste")
        oficial = resumo["por_coorte"]["oficial"]

        self.assertEqual(1, oficial["cobertura_par_sem_vig"])
        self.assertEqual(1, oficial["avaliacoes_binarias_sem_push"])
        self.assertAlmostEqual(
            0.5, oficial["probabilidade_over_sem_vig_media"]
        )
        self.assertAlmostEqual(
            0.5, oficial["desvio_binario_observado_menos_mercado"]
        )
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["promocao_automatica"])


if __name__ == "__main__":
    unittest.main()
