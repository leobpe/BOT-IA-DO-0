import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from exposicao_coleta_prospectiva import (
    enriquecer_avaliacao_com_exposicao,
    resumir_exposicao,
)


class ExposicaoColetaProspectivaTest(unittest.TestCase):
    def test_ancora_utc_e_convertida_para_hora_local_dos_eventos(self):
        ancora_local = datetime(2026, 9, 10, 10, 0, 0)
        ancora_utc = (
            ancora_local.astimezone().astimezone(timezone.utc).isoformat()
        )
        resultado = resumir_exposicao(
            [{
                "em": "2026-09-10T10:05:00",
                "evento": "ciclo_concluido",
                "partidas": 1,
            }],
            ancora=ancora_utc,
            agora=datetime(2026, 9, 10, 10, 10, 0),
        )

        self.assertEqual(resultado["ancora"], "2026-09-10T10:00:00")
        self.assertEqual(resultado["ciclos_concluidos"], 1)
        self.assertEqual(resultado["idade_operacional_horas"], 0.167)

    def test_ancora_durante_manutencao_nao_parece_pipeline_quebrado(self):
        resultado = resumir_exposicao(
            [],
            ancora="2026-09-10T10:00:00",
            agora=datetime(2026, 9, 10, 14, 0, 0),
            modo_manutencao={
                "ativo": True,
                "motivo": "manutencao_manual",
                "solicitado_em": "2026-09-10T09:00:00",
            },
        )

        self.assertEqual(
            "sem_exposicao_manutencao_planejada", resultado["estado"]
        )
        self.assertTrue(resultado["esperado_sem_dados"])
        self.assertFalse(resultado["requer_atencao"])
        self.assertFalse(resultado["relogio_amostra_iniciou"])
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_ciclos_reais_iniciam_relogio_e_somam_cobertura(self):
        eventos = [{
            "em": "2026-09-10T10:05:00",
            "evento": "ciclo_concluido",
            "duracao_segundos": 40.5,
            "partidas": 4,
            "tarefas_processadas": 2,
            "comparacoes_fontes_odds": [{}, {}],
            "betsapi": {
                "partidas_pareadas": 1,
                "partidas_consultadas": 1,
                "mercados_anexados": 3,
            },
        }, {
            "em": "2026-09-10T10:10:00",
            "evento": "ciclo_concluido",
            "duracao_segundos": 20.0,
            "partidas": 3,
            "tarefas_processadas": 1,
            "comparacoes_fontes_odds": [{}],
            "betsapi": {"partidas_pareadas": 0},
        }]

        resultado = resumir_exposicao(
            eventos,
            ancora="2026-09-10T10:00:00",
            agora=datetime(2026, 9, 10, 10, 15, 0),
        )

        self.assertEqual("exposicao_observada", resultado["estado"])
        self.assertTrue(resultado["relogio_amostra_iniciou"])
        self.assertEqual(2, resultado["ciclos_concluidos"])
        self.assertEqual(7, resultado["partidas_somadas"])
        self.assertEqual(3, resultado["tarefas_processadas"])
        self.assertEqual(3, resultado["comparacoes_fontes_odds"])
        self.assertEqual(1, resultado["betsapi_partidas_pareadas"])
        self.assertEqual(
            60.5, resultado["duracao_processamento_confirmada_segundos"]
        )
        self.assertEqual(
            0.095, resultado["exposicao_operacional_confirmada_horas"]
        )
        self.assertTrue(resultado["cobertura_telemetria_desde_ancora"])

    def test_lacuna_offline_nao_vira_exposicao_operacional_confirmada(self):
        eventos = [{
            "em": "2026-09-10T10:05:00",
            "evento": "ciclo_concluido",
            "duracao_segundos": 60,
        }, {
            "em": "2026-09-10T20:00:00",
            "evento": "ciclo_concluido",
            "duracao_segundos": 60,
        }]

        resultado = resumir_exposicao(
            eventos,
            ancora="2026-09-10T10:00:00",
            agora=datetime(2026, 9, 10, 20, 5, 0),
        )

        self.assertEqual(resultado["idade_operacional_horas"], 10.083)
        self.assertEqual(
            resultado["exposicao_operacional_confirmada_horas"], 0.033
        )
        self.assertTrue(resultado["cobertura_telemetria_desde_ancora"])

    def test_log_iniciado_tarde_nao_cobre_ancora_da_coorte(self):
        resultado = resumir_exposicao(
            [{
                "em": "2026-09-10T10:05:00",
                "evento": "ciclo_concluido",
                "duracao_segundos": 60,
            }],
            ancora="2026-09-10T09:00:00",
            agora=datetime(2026, 9, 10, 10, 10, 0),
        )

        self.assertFalse(resultado["cobertura_telemetria_desde_ancora"])
        self.assertEqual(
            resultado["lacuna_operacional_antes_da_telemetria_horas"],
            1.067,
        )

    def test_sem_ciclo_fora_de_manutencao_exige_atencao_apos_uma_hora(self):
        resultado = resumir_exposicao(
            [],
            ancora="2026-09-10T10:00:00",
            agora=datetime(2026, 9, 10, 11, 0, 1),
            modo_manutencao={"ativo": False},
        )

        self.assertEqual(
            "sem_ciclo_apos_ancora_requer_atencao", resultado["estado"]
        )
        self.assertTrue(resultado["requer_atencao"])
        self.assertFalse(resultado["saudavel"])

    def test_pausa_historica_nao_conta_como_tempo_operacional(self):
        eventos = [{
            "em": "2026-09-10T10:00:00",
            "evento": "modo_manutencao_solicitado",
        }, {
            "em": "2026-09-10T14:00:00",
            "evento": "modo_manutencao_liberado",
        }]

        resultado = resumir_exposicao(
            eventos,
            ancora="2026-09-10T11:00:00",
            agora=datetime(2026, 9, 10, 14, 15, 0),
            modo_manutencao={"ativo": False},
        )

        self.assertEqual("aguardando_primeiro_ciclo", resultado["estado"])
        self.assertEqual(0.25, resultado["idade_operacional_horas"])
        self.assertEqual(3.0, resultado["manutencao_excluida_horas"])
        self.assertFalse(resultado["requer_atencao"])

    def test_rollback_de_inicio_abre_pausa_historica_auditavel(self):
        eventos = [{
            "em": "2026-09-10T10:00:00",
            "evento": "modo_manutencao_restaurado_apos_falha_inicio",
        }, {
            "em": "2026-09-10T12:00:00",
            "evento": "modo_manutencao_liberado",
        }]

        resultado = resumir_exposicao(
            eventos,
            ancora="2026-09-10T10:30:00",
            agora=datetime(2026, 9, 10, 12, 15, 0),
            modo_manutencao={"ativo": False},
        )

        self.assertEqual("aguardando_primeiro_ciclo", resultado["estado"])
        self.assertEqual(0.25, resultado["idade_operacional_horas"])
        self.assertEqual(1.5, resultado["manutencao_excluida_horas"])
        self.assertFalse(resultado["requer_atencao"])

    def test_pausa_atual_nao_mascara_pipeline_ja_parado(self):
        eventos = [{
            "em": "2026-09-10T12:30:00",
            "evento": "modo_manutencao_solicitado",
        }]

        resultado = resumir_exposicao(
            eventos,
            ancora="2026-09-10T10:00:00",
            agora=datetime(2026, 9, 10, 14, 0, 0),
            modo_manutencao={
                "ativo": True,
                "motivo": "manutencao_manual",
                "solicitado_em": "2026-09-10T12:30:00",
            },
        )

        self.assertEqual(
            "sem_ciclo_antes_da_pausa_requer_atencao",
            resultado["estado"],
        )
        self.assertEqual(2.5, resultado["idade_operacional_horas"])
        self.assertTrue(resultado["requer_atencao"])

    def test_estado_e_evento_sobrepostos_nao_duplicam_tempo_de_pausa(self):
        eventos = [{
            "em": "2026-09-10T10:00:00",
            "evento": "modo_manutencao_solicitado",
        }, {
            "em": "2026-09-10T11:00:00",
            "evento": "modo_manutencao_liberado",
        }]

        resultado = resumir_exposicao(
            eventos,
            ancora="2026-09-10T09:00:00",
            agora=datetime(2026, 9, 10, 12, 0, 0),
            modo_manutencao={
                "ativo": True,
                "motivo": "manutencao_manual",
                "solicitado_em": "2026-09-10T10:30:00",
            },
        )

        self.assertEqual(2.0, resultado["manutencao_excluida_horas"])
        self.assertEqual(1.0, resultado["idade_operacional_horas"])
        self.assertEqual(1, resultado["pausas_manutencao_apos_ancora"])

    def test_estado_de_manutencao_invalido_falha_fechado(self):
        resultado = resumir_exposicao(
            [],
            ancora="2026-09-10T11:30:00",
            agora=datetime(2026, 9, 10, 12, 0, 0),
            modo_manutencao={
                "ativo": True,
                "motivo": "arquivo_manutencao_invalido",
                "solicitado_em": "2026-09-10T11:00:00",
            },
        )

        self.assertEqual("estado_manutencao_invalido", resultado["estado"])
        self.assertTrue(resultado["requer_atencao"])
        self.assertFalse(resultado["saudavel"])

    def test_ancora_futura_falha_fechada(self):
        resultado = resumir_exposicao(
            [],
            ancora="2099-09-10T10:00:00",
            agora=datetime(2026, 9, 10, 10, 0, 0),
        )

        self.assertEqual("ancora_futura", resultado["estado"])
        self.assertTrue(resultado["requer_atencao"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["telegram"])

    def test_enriquecimento_separa_ancoras_do_desajuste(self):
        pasta = Path.cwd()
        avaliacao = {
            "ancora_prospectiva_em": "2026-09-10T08:00:00",
            "recorte_observacional_executavel": {
                "ancora_pre_registrada_em": "2026-09-10T10:00:00",
            },
        }
        eventos = [{
                "em": "2026-09-10T09:00:00",
                "evento": "ciclo_concluido",
                "partidas": 2,
                "tarefas_processadas": 1,
                "duracao_segundos": 10,
            }]
        # Isola a leitura sem tocar o arquivo real de observabilidade.
        with patch(
            "exposicao_coleta_prospectiva.carregar_eventos_observabilidade",
            return_value={
                "saudavel": True,
                "eventos": eventos,
                "linhas": 1,
                "linhas_invalidas": 0,
                "erro": None,
            },
        ):
            resultado = enriquecer_avaliacao_com_exposicao(
                avaliacao,
                pasta=pasta,
                agora=datetime(2026, 9, 10, 12, 0, 0),
                modo_manutencao={
                    "ativo": True,
                    "motivo": "manutencao_manual",
                    "solicitado_em": "2026-09-10T09:30:00",
                },
            )
        exposicao = resultado["exposicao_coleta_prospectiva"]
        self.assertEqual(
            "exposicao_parcial_com_coortes_em_pausa", exposicao["estado"]
        )
        self.assertEqual(
            "exposicao_observada_antes_da_pausa",
            exposicao["por_coorte"]["principal"]["estado"],
        )
        self.assertEqual(
            "sem_exposicao_manutencao_planejada",
            exposicao["por_coorte"]["desajuste_executavel"]["estado"],
        )
        self.assertFalse(exposicao["aplicacao_sinais"])


if __name__ == "__main__":
    unittest.main()
