import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from probabilidade_individual_sem_vig import (
    VERSAO,
    ajustar,
    anexar_referencia_sem_vig,
    prever,
    validar_walk_forward,
)


def sinteticos(total=200):
    itens = []
    for indice in range(total):
        item = {
            "sinal_id": indice + 1,
            "partida_id": indice + 1,
            "snapshot_id": indice + 1,
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.7,
            "probabilidade_mercado_sem_vig": 0.58,
            "margem_bookmaker": 0.08,
            "metodo": "metodo-v1",
            "segmento": "principal",
            "criado_em": (
                datetime(2026, 1, 1) + timedelta(days=indice)
            ).isoformat(),
            "encerrado_em": (
                datetime(2026, 1, 1, 2) + timedelta(days=indice)
            ).isoformat(),
            "alvo": int(indice % 30 < 17),
            "valores": {
                "tempo_restante": 40 - indice % 30,
                "gols_atuais": indice % 3,
                "diferenca_placar": indice % 2,
                "gols_necessarios": 1,
                "ataque_casa_defesa_fora": 0.7 + (indice % 13) / 5,
                "ataque_fora_defesa_casa": 0.9 + (indice % 7) / 5,
                "chutes_5min": indice % 6,
                "pressao_5min": None,
                "xg_5min": None,
                "vermelhos": 0,
            },
        }
        itens.append(item)
    return itens


class ReferenciaSemVigTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript("""
            CREATE TABLE odds(
                id INTEGER PRIMARY KEY,snapshot_id INTEGER,tipo TEXT,
                mercado TEXT,dados TEXT,estrutura_json TEXT
            );
        """)

    def tearDown(self):
        self.conexao.close()

    def test_reconstroi_over_under_do_mesmo_snapshot(self):
        self.conexao.execute(
            "INSERT INTO odds VALUES(1,1,'ao_vivo','Total Gols',?, '{}')",
            ("Total Gols Over Under 0.5 1.70 2.20",),
        )
        itens, auditoria = anexar_referencia_sem_vig(
            self.conexao,
            [{
                "sinal_id": 1,
                "snapshot_id": 1,
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.70,
            }],
        )
        esperado = (1 / 1.70) / (1 / 1.70 + 1 / 2.20)
        self.assertEqual(1, len(itens))
        self.assertAlmostEqual(
            esperado, itens[0]["probabilidade_mercado_sem_vig"]
        )
        self.assertTrue(auditoria["cobertura_suficiente"])
        self.assertFalse(auditoria["consulta_resultado"])
        self.assertFalse(auditoria["aplicacao_sinais"])

    def test_odd_divergente_ou_par_ausente_falha_fechado(self):
        self.conexao.execute(
            "INSERT INTO odds VALUES(1,1,'ao_vivo','Total Gols',?, '{}')",
            ("Total Gols Over Under 0.5 1.70 2.20",),
        )
        itens, auditoria = anexar_referencia_sem_vig(
            self.conexao,
            [{
                "sinal_id": 1,
                "snapshot_id": 1,
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.71,
            }],
        )
        self.assertEqual([], itens)
        self.assertEqual(
            1,
            auditoria["exclusoes"][
                "mercado_exato_incompleto_ou_ambiguo"
            ],
        )


class ModeloSemVigTest(unittest.TestCase):
    def test_offset_e_mercado_sem_vig_e_contexto_altera_previsao(self):
        registros = sinteticos()
        modelo = ajustar(registros[:120])
        self.assertEqual(VERSAO, modelo["versao"])
        self.assertEqual(
            "logit_probabilidade_mercado_sem_vig_mesmo_snapshot",
            modelo["offset"],
        )
        cedo = copy.deepcopy(registros[150])
        tarde = copy.deepcopy(cedo)
        cedo["valores"]["tempo_restante"] = 38
        tarde["valores"]["tempo_restante"] = 5
        self.assertGreater(prever(modelo, cedo), prever(modelo, tarde))
        cedo["probabilidade_mercado_sem_vig"] = 0.65
        alta = prever(modelo, cedo)
        cedo["probabilidade_mercado_sem_vig"] = 0.45
        self.assertGreater(alta, prever(modelo, cedo))

    def test_walk_forward_nao_vaza_validacao_no_treino(self):
        registros = sinteticos()
        original = ajustar
        chamadas = []

        def registrar(itens):
            chamadas.append([item["sinal_id"] for item in itens])
            return original(itens)

        with patch(
            "probabilidade_individual_sem_vig.ajustar",
            side_effect=registrar,
        ):
            resultado = validar_walk_forward(
                registros, "gol_ft", "2026-09-11T12:00:00"
            )
        self.assertEqual(3, len(resultado["folds"]))
        for indice, fold in enumerate(resultado["folds"]):
            self.assertFalse(
                set(chamadas[indice]) & set(fold["sinais"])
            )
            self.assertLess(max(chamadas[indice]), min(fold["sinais"]))

    def test_nao_aprova_se_nao_superar_mercado_sem_vig(self):
        registros = sinteticos()
        for indice, item in enumerate(registros):
            item["alvo"] = int(indice % 5 < 3)
            item["probabilidade_mercado_sem_vig"] = 0.60
            item["valores"]["tempo_restante"] = 20 + indice % 2
        resultado = validar_walk_forward(
            registros, "gol_ft", "2026-09-11T12:00:00"
        )
        self.assertEqual("validacao_reprovada", resultado["estado"])
        self.assertFalse(resultado["aprovado_para_coorte_prospectiva"])
        self.assertIsNone(resultado["modelo"])
        self.assertIn(
            "delta_brier_vs_mercado_sem_vig",
            resultado["validacao"],
        )

    def test_exige_tres_blocos_temporais(self):
        resultado = validar_walk_forward(
            sinteticos(169), "gol_ft", "2026-09-11T12:00:00"
        )
        self.assertEqual("amostra_insuficiente", resultado["estado"])
        self.assertEqual(170, resultado["minimo"])


if __name__ == "__main__":
    unittest.main()
