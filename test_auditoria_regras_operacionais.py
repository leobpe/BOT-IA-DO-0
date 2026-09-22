import json
import sqlite3
import unittest

from auditoria_regras_operacionais import auditar_regra_proximo_gol
from politica_proximo_gol_preciso import MOTIVO_MINUTO, MOTIVO_ODD
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO as VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
)


class AuditoriaRegrasOperacionaisTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.execute(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                mercado TEXT,
                odd REAL,
                features_json TEXT,
                status TEXT,
                regra_versao TEXT,
                motivos_json TEXT
            )
            """
        )

    def tearDown(self):
        self.conexao.close()

    def _inserir(
        self, odd, minuto, status="aprovado", mercado="proximo_gol",
        motivos=None, idade_odds=0,
    ):
        self.conexao.execute(
            """
            INSERT INTO sinais (
                mercado, odd, features_json, status, regra_versao,
                motivos_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mercado,
                odd,
                json.dumps({
                    "minuto": minuto,
                    "idade_odds_segundos": idade_odds,
                    "qualidade_dados": 100,
                    "lado_dominante": "casa",
                    "janelas": {"5": {"pressao_pico": [70, 20]}},
                }),
                status,
                VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
                json.dumps(motivos or []),
            ),
        )

    def test_aprovacao_nos_limites_e_saudavel(self):
        self._inserir(1.40, 75)

        auditoria = auditar_regra_proximo_gol(self.conexao)

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["aprovadas"], 1)
        self.assertEqual(auditoria["violacoes"], 0)

    def test_rejeitados_fora_da_coorte_nao_sao_violacao(self):
        self._inserir(1.50, 80, status="rejeitado")

        self.assertTrue(auditar_regra_proximo_gol(self.conexao)["saudavel"])

    def test_aprovacao_abaixo_da_odd_e_detectada(self):
        self._inserir(1.39, 70)

        auditoria = auditar_regra_proximo_gol(self.conexao)

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            auditoria["detalhes_violacoes"][0]["motivo"],
            MOTIVO_ODD,
        )

    def test_aprovacao_depois_do_minuto_e_detectada(self):
        self._inserir(1.80, 76)

        auditoria = auditar_regra_proximo_gol(self.conexao)

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            auditoria["detalhes_violacoes"][0]["motivo"],
            MOTIVO_MINUTO,
        )

    def test_versao_usada_em_outro_mercado_e_detectada(self):
        self._inserir(1.80, 70, mercado="gol_ft")

        auditoria = auditar_regra_proximo_gol(self.conexao)

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            auditoria["detalhes_violacoes"][0]["motivo"],
            "mercado_incorreto",
        )

    def test_funil_expoe_exatamente_onde_decisoes_sao_bloqueadas(self):
        self._inserir(
            1.80, 70, status="rejeitado",
            motivos=["bloqueio:historico_5min_insuficiente"],
        )
        self._inserir(
            1.80, 70, status="rejeitado",
            motivos=["bloqueio:atividade_recente_insuficiente_gols"],
        )
        self._inserir(1.65, 70, status="rejeitado")
        self._inserir(1.80, 70, status="aprovado")
        self._inserir(1.80, 80, status="rejeitado")

        auditoria = auditar_regra_proximo_gol(self.conexao)

        self.assertEqual(auditoria["funil"], {
            "mercado_correto": 5,
            "dentro_janela": 4,
            "historico_5min": 3,
            "atividade_recente": 2,
            "odd_minima": 2,
            "qualidade_100": 2,
            "pressao_pico_70": 2,
            "sem_outros_bloqueios": 2,
            "aprovadas": 1,
        })
        self.assertEqual(auditoria["bloqueios_principais"], [
            {
                "motivo": "atividade_recente_insuficiente_gols",
                "quantidade": 1,
            },
            {"motivo": "historico_5min_insuficiente", "quantidade": 1},
        ])

    def test_cobertura_independente_distingue_odd_ausente_e_vencida(self):
        self._inserir(1.80, 70, status="rejeitado", idade_odds=120)
        self._inserir(1.90, 70, status="rejeitado", idade_odds=500)
        self._inserir(None, 70, status="rejeitado", idade_odds=0)

        cobertura = auditar_regra_proximo_gol(
            self.conexao
        )["cobertura_independente"]

        self.assertEqual(cobertura["odd_disponivel"], 2)
        self.assertEqual(cobertura["odd_fresca"], 1)
        self.assertEqual(cobertura["odd_minima"], 2)


if __name__ == "__main__":
    unittest.main()
