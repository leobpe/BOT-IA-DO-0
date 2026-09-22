import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from validacao_pre_live_preciso import (
    TAMANHO_COORTE,
    VERSAO_ALVO,
    registrar_ou_validar_definicao,
    resumir_validacao_pre_live_preciso,
    sincronizar_coorte_pre_live_preciso,
)


class ValidacaoPreLivePrecisoTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.executescript(
            """
            CREATE TABLE bilhetes_pre_live (
                id INTEGER PRIMARY KEY,
                criado_em TEXT NOT NULL,
                versao TEXT NOT NULL,
                resultado TEXT,
                retorno_unidades REAL,
                odd_total REAL NOT NULL,
                bilhete_json TEXT NOT NULL
            );
            CREATE TABLE entregas_pre_live (
                id INTEGER PRIMARY KEY,
                bilhete_id INTEGER,
                mensagem_id INTEGER,
                criado_em TEXT
            );
            CREATE TABLE listas_pre_live (
                id INTEGER PRIMARY KEY,
                mensagem_id INTEGER,
                criado_em TEXT
            );
            CREATE TABLE itens_listas_pre_live (
                lista_id INTEGER,
                bilhete_id INTEGER
            );
            """
        )
        self.inicio = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)
        self.ancora = registrar_ou_validar_definicao(
            self.conexao, self.inicio
        )

    def tearDown(self):
        self.conexao.close()

    def _bilhete(self, *, qualidade=90.0, edge=0.05,
                  probabilidade_sem_vig=0.50, mercado="chance_dupla"):
        perna = {
            "mercado": mercado,
            "selecao": "mandante_ou_empate",
            "qualidade_contexto": qualidade,
        }
        if probabilidade_sem_vig is not None:
            perna["probabilidade_mercado_sem_margem"] = (
                probabilidade_sem_vig
            )
        return {
            "tipo": "simples",
            "edge_conservador": edge,
            "pernas": [perna],
        }

    def _inserir(self, indice, *, minutos=None, resultado="green",
                  retorno=0.50, odd=1.50, bilhete=None,
                  versao=VERSAO_ALVO, publicado=False):
        minutos = indice if minutos is None else minutos
        criado_em = (self.inicio + timedelta(minutes=minutos)).isoformat()
        self.conexao.execute(
            """
            INSERT INTO bilhetes_pre_live(
                id,criado_em,versao,resultado,retorno_unidades,
                odd_total,bilhete_json
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                indice, criado_em, versao, resultado, retorno, odd,
                json.dumps(bilhete or self._bilhete()),
            ),
        )
        if publicado:
            self.conexao.execute(
                "INSERT INTO entregas_pre_live VALUES (?,?,?,?)",
                (indice, indice, 1000 + indice, criado_em),
            )

    def _resumir(self):
        sincronizar_coorte_pre_live_preciso(
            self.conexao, agora=self.inicio + timedelta(hours=2)
        )
        return resumir_validacao_pre_live_preciso(self.conexao)

    def test_ancora_exclui_legado_e_criterio_exato_exclui_fraco(self):
        self._inserir(1, minutos=-10, publicado=True)
        self._inserir(
            2,
            bilhete=self._bilhete(qualidade=84.9),
            publicado=True,
        )
        self._inserir(3, publicado=False)

        resumo = self._resumir()

        self.assertEqual(1, resumo["candidatos"])
        self.assertEqual(0, resumo["publicados"])
        self.assertEqual(TAMANHO_COORTE - 1, resumo["faltam"])
        self.assertEqual(
            1, resumo["historico_legado"]["publicados_resolvidos"]
        )
        self.assertFalse(
            resumo["historico_legado"]["entra_na_coorte_nova"]
        )

    def test_coorte_fixa_favoravel_exige_dev_holdout_e_preco_sem_vig(self):
        for indice in range(1, 61):
            self._inserir(indice, publicado=indice % 2 == 0)

        resumo = self._resumir()

        self.assertEqual(60, resumo["candidatos"])
        self.assertEqual(30, resumo["publicados"])
        self.assertTrue(resumo["coorte_fechada"])
        self.assertTrue(resumo["resultados_completos"])
        self.assertEqual(42, resumo["desenvolvimento"]["validos"])
        self.assertEqual(18, resumo["holdout"]["validos"])
        self.assertTrue(resumo["gate_preco_justo"]["satisfeito"])
        self.assertEqual(
            "favoravel_para_revisao_manual", resumo["decisao"]
        )
        self.assertTrue(resumo["apto_revisao"])

    def test_roi_bom_sem_referencia_sem_vig_nao_comprova_edge(self):
        for indice in range(1, 61):
            self._inserir(
                indice,
                bilhete=self._bilhete(probabilidade_sem_vig=None),
            )

        resumo = self._resumir()

        self.assertEqual(
            "inconclusiva_ou_desfavoravel", resumo["decisao"]
        )
        self.assertFalse(resumo["gate_preco_justo"]["satisfeito"])
        self.assertEqual(
            0, resumo["referencia_sem_vig"]["cobertura"]
        )

    def test_checkpoint_so_dispara_no_prefixo_fixo_de_25(self):
        for indice in range(1, 25):
            self._inserir(indice, resultado="red", retorno=-1.0)
        antes = self._resumir()
        self.assertFalse(antes["alerta_desfavoravel"])

        self._inserir(25, resultado="red", retorno=-1.0)
        depois = self._resumir()
        self.assertTrue(depois["alerta_desfavoravel"])
        self.assertEqual(
            25, depois["checkpoint_seguranca"]["validos"]
        )
        self.assertLess(
            depois["checkpoint_seguranca"]["intervalo_roi_95"][1], 0
        )

    def test_primeiros_60_nao_mudam_com_resultado_do_61(self):
        for indice in range(1, 61):
            self._inserir(indice, resultado="green", retorno=0.50)
        self._inserir(61, resultado="red", retorno=-1.0)

        resumo = self._resumir()

        self.assertEqual(60, resumo["candidatos"])
        self.assertEqual(60, resumo["greens"])
        self.assertEqual(0, resumo["reds"])

    def test_entrada_congelada_nao_muda_com_atualizacao_posterior(self):
        self._inserir(1)
        sincronizar_coorte_pre_live_preciso(
            self.conexao, agora=self.inicio + timedelta(hours=1)
        )
        self.conexao.execute(
            """
            UPDATE bilhetes_pre_live
            SET odd_total=?, bilhete_json=?
            WHERE id=?
            """,
            (9.0, json.dumps(self._bilhete(qualidade=10.0)), 1),
        )

        resumo = self._resumir()

        self.assertEqual(1, resumo["candidatos"])
        self.assertEqual(
            0.6667, resumo["equilibrio_odd"]["probabilidade_media"]
        )
        congelado = self.conexao.execute(
            """
            SELECT odd_total,bilhete_json FROM coorte_pre_live_preciso
            WHERE bilhete_id=1
            """
        ).fetchone()
        self.assertEqual(1.5, congelado[0])
        self.assertEqual(
            90.0,
            json.loads(congelado[1])["pernas"][0]["qualidade_contexto"],
        )

    def test_ancora_divergente_falha_fechado(self):
        documento = dict(self.ancora)
        documento["coorte_fixa"] = 999
        self.conexao.execute(
            "UPDATE metadados_pre_live SET valor=?",
            (json.dumps(documento),),
        )
        with self.assertRaises(RuntimeError):
            resumir_validacao_pre_live_preciso(self.conexao)

    def test_membro_congelado_adulterado_falha_fechado(self):
        self._inserir(1)
        sincronizar_coorte_pre_live_preciso(self.conexao)
        self.conexao.execute(
            """
            UPDATE coorte_pre_live_preciso SET bilhete_json=?
            WHERE bilhete_id=1
            """,
            (json.dumps(self._bilhete(qualidade=1.0)),),
        )

        with self.assertRaises(RuntimeError):
            resumir_validacao_pre_live_preciso(self.conexao)


if __name__ == "__main__":
    unittest.main()
