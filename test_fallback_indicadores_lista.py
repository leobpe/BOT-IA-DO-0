import unittest
from datetime import datetime, timedelta

from fallback_indicadores_lista import (
    auditar_janelas_temporais_lista,
    complementar_estatisticas_com_lista,
    fundir_janelas_temporais_lista_como_fallback,
    marcar_dependencia_fallback_temporal_lista,
    resumir_auditoria_temporal_sqlite,
)
import json
import sqlite3


class FallbackIndicadoresListaTest(unittest.TestCase):
    def _jogo(self, observado_em, campos=None):
        return {
            "url": "https://packball.com/pt/matches/1/match/a-b/live",
            "lista_observada_em": observado_em.isoformat(),
            "indicadores_lista": {
                "versao": "packball-lista-indicadores-v1",
                "campos": campos or {
                    "total_chutes_partida_completa": {
                        "casa": 7, "visitante": 4,
                    },
                    "escanteios_partida_completa": {
                        "casa": 3, "visitante": 2,
                    },
                    "ataques_perigosos_partida_completa": {
                        "casa": 18, "visitante": 13,
                    },
                    "indice_de_pressao_ult_10_minutos": {
                        "casa": 90, "visitante": 10,
                    },
                    "chutes_no_gol_ult_10_minutos": {
                        "casa": 2, "visitante": 1,
                    },
                },
            },
        }

    def test_complementa_apenas_equivalencias_cumulativas(self):
        agora = datetime(2026, 8, 24, 21, 30, 0)
        estatisticas, diagnostico = complementar_estatisticas_com_lista(
            self._jogo(agora - timedelta(seconds=90)),
            {"Chutes no gol": None, "Índice de pressão": None},
            instante=agora,
        )

        self.assertEqual(estatisticas["Chutes"], "7 - 4")
        self.assertEqual(estatisticas["Escanteios"], "3 - 2")
        self.assertEqual(estatisticas["Ataques perigosos"], "18 - 13")
        self.assertIsNone(estatisticas["Chutes no gol"])
        self.assertIsNone(estatisticas["Índice de pressão"])
        self.assertTrue(diagnostico["aplicado"])
        self.assertTrue(diagnostico["autoriza_sinal"])

    def test_nunca_substitui_detalhe_existente(self):
        agora = datetime(2026, 8, 24, 21, 30, 0)
        estatisticas, diagnostico = complementar_estatisticas_com_lista(
            self._jogo(agora),
            {"Chutes": "9 - 8", "Escanteios": "4 - 4"},
            instante=agora,
        )

        self.assertEqual(estatisticas["Chutes"], "9 - 8")
        self.assertEqual(estatisticas["Escanteios"], "4 - 4")
        self.assertEqual(estatisticas["Ataques perigosos"], "18 - 13")
        self.assertEqual(
            diagnostico["campos_complementados"], ["Ataques perigosos"]
        )

    def test_rejeita_lista_envelhecida(self):
        agora = datetime(2026, 8, 24, 21, 30, 0)
        estatisticas, diagnostico = complementar_estatisticas_com_lista(
            self._jogo(agora - timedelta(seconds=241)),
            {},
            instante=agora,
        )

        self.assertNotIn("Chutes", estatisticas)
        self.assertFalse(diagnostico["aplicado"])
        self.assertEqual(
            diagnostico["motivo"], "indicadores_lista_desatualizados"
        )

    def test_rejeita_par_incompleto_ou_negativo(self):
        agora = datetime(2026, 8, 24, 21, 30, 0)
        campos = {
            "total_chutes_partida_completa": {
                "casa": 4, "visitante": None,
            },
            "escanteios_partida_completa": {
                "casa": -1, "visitante": 2,
            },
        }
        estatisticas, diagnostico = complementar_estatisticas_com_lista(
            self._jogo(agora, campos), {}, instante=agora
        )

        self.assertNotIn("Chutes", estatisticas)
        self.assertNotIn("Escanteios", estatisticas)
        self.assertFalse(diagnostico["aplicado"])
        self.assertEqual(len(diagnostico["campos_rejeitados"]), 2)

    def test_auditoria_temporal_compara_sem_aplicar_em_sinais(self):
        agora = datetime(2026, 8, 24, 21, 30, 0)
        jogo = self._jogo(agora - timedelta(seconds=30))
        campos = jogo["indicadores_lista"]["campos"]
        campos.update({
            "total_chutes_ult_5_minutos": {"casa": 2, "visitante": 1},
            "escanteios_ult_5_minutos": {"casa": 1, "visitante": 0},
            "indice_de_pressao_ult_5_minutos": {
                "casa": 70, "visitante": 20,
            },
        })
        auditoria = auditar_janelas_temporais_lista(
            jogo,
            {"5": {"chutes": [3, 1], "escanteios": [1, 0]}},
            instante=agora,
        )

        self.assertEqual(auditoria["estado"], "comparavel")
        self.assertEqual(len(auditoria["comparacoes"]), 2)
        self.assertFalse(auditoria["aplicacao_sinais"])
        self.assertTrue(all(
            item["concordante_tolerancia"]
            for item in auditoria["comparacoes"]
        ))

    def test_resumo_sqlite_exige_amostra_e_wilson(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.execute(
            "CREATE TABLE snapshots ("
            "id INTEGER, partida_id INTEGER, qualidade_json TEXT)"
        )
        for indice in range(40):
            auditoria = {
                "versao": "packball-lista-janelas-sombra-v1",
                "idade_segundos": 20,
                "comparacoes": [
                    {
                        "metrica": metrica,
                        "concordante_tolerancia": True,
                        "atividade_concordante": True,
                    }
                    for metrica in ("chutes", "escanteios")
                ],
            }
            conexao.execute(
                "INSERT INTO snapshots VALUES (?, ?, ?)",
                (
                    indice + 1,
                    (indice % 12) + 1,
                    json.dumps({
                        "auditoria_indicadores_temporais_lista": auditoria
                    }),
                ),
            )
        resumo = resumir_auditoria_temporal_sqlite(conexao)

        self.assertEqual(resumo["comparacoes_independentes"], 80)
        self.assertEqual(resumo["partidas_distintas"], 12)
        self.assertTrue(resumo["pronto_para_revisao"])
        self.assertEqual(
            set(resumo["metricas_aprovadas"]), {"chutes", "escanteios"}
        )
        self.assertFalse(resumo["aplicacao_sinais"])
        conexao.close()

    def test_fallback_temporal_so_ativa_apos_gate_e_nao_substitui_historico(self):
        agora = datetime(2026, 8, 24, 21, 30, 0)
        jogo = self._jogo(agora - timedelta(seconds=20))
        jogo["indicadores_lista"]["campos"].update({
            "total_chutes_ult_5_minutos": {"casa": 3, "visitante": 1},
            "escanteios_ult_5_minutos": {"casa": 1, "visitante": 0},
            "total_chutes_ult_10_minutos": {"casa": 5, "visitante": 2},
        })
        evolucao = {
            "5": {"chutes": [2, 1], "duracao_real_minutos": 5.2},
            "10": None,
            "15": None,
        }
        revisao = {
            "pronto_para_revisao": True,
            "metricas_aprovadas": ["chutes", "escanteios"],
        }

        fundida, diagnostico = fundir_janelas_temporais_lista_como_fallback(
            jogo, evolucao, revisao, autorizado=True, instante=agora
        )

        self.assertEqual(fundida["5"]["chutes"], [2, 1])
        self.assertEqual(fundida["5"]["escanteios"], [1.0, 0.0])
        self.assertEqual(fundida["10"]["chutes"], [5.0, 2.0])
        self.assertIsNone(fundida["10"]["pressao"])
        self.assertIsNone(fundida["10"]["pressao_resumo"])
        self.assertTrue(diagnostico["aplicado"])
        self.assertTrue(diagnostico["aplicacao_sinais"])

    def test_fallback_temporal_falha_fechado_sem_gate(self):
        agora = datetime(2026, 8, 24, 21, 30, 0)
        original = {"5": None, "10": None, "15": None}

        fundida, diagnostico = fundir_janelas_temporais_lista_como_fallback(
            self._jogo(agora), original,
            {"pronto_para_revisao": False},
            autorizado=True, instante=agora,
        )

        self.assertEqual(fundida, original)
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertEqual(diagnostico["motivo"], "gate_independente_pendente")

    def test_marca_candidato_que_so_passou_com_fallback_temporal(self):
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "regra_versao": "sinais-v6",
            "status": "aprovado",
            "features": {},
            "motivos": [],
        }
        base = {
            **candidato,
            "status": "rejeitado",
            "features": {},
            "motivos": ["historico_5min_insuficiente"],
        }
        diagnostico = {
            "fallback_condicional": {
                "aplicado": True,
                "versao": "packball-lista-janelas-fallback-v1",
                "campos_complementados": ["5.chutes"],
            },
            "gate_revisao": {
                "metricas_aprovadas": ["chutes"],
                "comparacoes": 80,
                "partidas": 12,
            },
        }

        marcar_dependencia_fallback_temporal_lista(
            [candidato], [base], diagnostico
        )

        evidencia = candidato["features"]["fallback_temporal_lista"]
        self.assertTrue(evidencia["dependente"])
        self.assertEqual(evidencia["status_sem_fallback"], "rejeitado")
        self.assertEqual(evidencia["campos_complementados"], ["5.chutes"])
        self.assertIn("dependente_fallback_temporal_lista", candidato["motivos"])

    def test_nao_marca_dependencia_se_o_metodo_base_tambem_passaria(self):
        candidato = {
            "mercado": "proximo_gol",
            "linha": "casa",
            "regra_versao": "sinais-v10e",
            "status": "simulacao",
            "features": {},
            "motivos": [],
        }
        base = {**candidato, "features": {}, "motivos": []}
        diagnostico = {
            "fallback_condicional": {
                "aplicado": True,
                "campos_complementados": ["10.chutes"],
            },
            "gate_revisao": {"metricas_aprovadas": ["chutes"]},
        }

        marcar_dependencia_fallback_temporal_lista(
            [candidato], [base], diagnostico
        )

        evidencia = candidato["features"]["fallback_temporal_lista"]
        self.assertFalse(evidencia["dependente"])
        self.assertNotIn(
            "dependente_fallback_temporal_lista", candidato["motivos"]
        )

    def test_nao_altera_candidato_quando_fallback_nao_foi_aplicado(self):
        candidato = {
            "mercado": "gol_ft",
            "features": {},
            "motivos": [],
        }

        marcar_dependencia_fallback_temporal_lista(
            [candidato], [], {"fallback_condicional": {"aplicado": False}}
        )

        self.assertNotIn("fallback_temporal_lista", candidato["features"])


if __name__ == "__main__":
    unittest.main()
