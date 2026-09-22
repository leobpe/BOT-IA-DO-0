import json
import os
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agendador_pre_live import (
    _horarios_configurados,
    encontrar_slot_devido,
    executar_slot,
    executar_loop,
)


class AgendadorPreLiveTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_agendador_pre_live"
        self.pasta.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.pasta)

    def test_normaliza_horarios_e_encontra_slot_na_janela(self):
        self.assertEqual(
            ["06:00", "12:00"],
            _horarios_configurados("12:00,06:00,99:00,06:00"),
        )
        agora = datetime(2026, 8, 27, 12, 30, tzinfo=timezone.utc)
        chave, horario = encontrar_slot_devido(
            agora, {}, horarios=["06:00", "12:00"]
        )
        self.assertEqual("2026-08-27|12:00", chave)
        self.assertEqual("12:00", horario)

    def test_nao_executa_slot_antigo_ou_ja_concluido(self):
        agora = datetime(2026, 8, 27, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(
            (None, None),
            encontrar_slot_devido(agora, {}, horarios=["06:00"]),
        )
        agenda = {
            "execucoes": {
                "2026-08-27|22:00": {"estado": "concluida"}
            }
        }
        self.assertEqual(
            (None, None),
            encontrar_slot_devido(agora, agenda, horarios=["22:00"]),
        )

    def test_falha_temporaria_respeita_espera_e_depois_repete(self):
        agora = datetime(2026, 8, 27, 12, 10, tzinfo=timezone.utc)
        agenda = {"execucoes": {"2026-08-27|12:00": {
            "estado": "falha_temporaria",
            "proxima_tentativa_em": "2026-08-27T12:15:00+00:00",
        }}}

        self.assertEqual(
            (None, None),
            encontrar_slot_devido(agora, agenda, horarios=["12:00"]),
        )
        self.assertEqual(
            ("2026-08-27|12:00", "12:00"),
            encontrar_slot_devido(
                agora.replace(minute=16), agenda, horarios=["12:00"]
            ),
        )

    def test_falha_no_fim_da_janela_ainda_recebe_repeticao_curta(self):
        agenda = {"execucoes": {"2026-08-27|17:00": {
            "estado": "falha_temporaria",
            "proxima_tentativa_em": "2026-08-27T20:04:00+00:00",
        }}}

        self.assertEqual(
            ("2026-08-27|17:00", "17:00"),
            encontrar_slot_devido(
                datetime(2026, 8, 27, 20, 5, tzinfo=timezone.utc),
                agenda,
                horarios=["17:00"],
            ),
        )

    def test_repeticao_temporaria_nao_se_estende_pelo_resto_do_dia(self):
        agenda = {"execucoes": {"2026-08-27|17:00": {
            "estado": "falha_temporaria",
            "proxima_tentativa_em": "2026-08-27T20:04:00+00:00",
        }}}

        self.assertEqual(
            (None, None),
            encontrar_slot_devido(
                datetime(2026, 8, 27, 20, 31, tzinfo=timezone.utc),
                agenda,
                horarios=["17:00"],
            ),
        )

    def test_slot_persiste_conclusao_sem_telegram(self):
        agora = datetime(2026, 8, 27, 12, 5, tzinfo=timezone.utc)
        retorno = {
            "jogos_analisados": 10, "bilhetes": 2,
            "candidatos_elegiveis": 14,
            "jogos_nao_analisados_limite": 4,
            "cobertura_analise": 0.7143,
            "limite_analise": {"configurado": 60, "efetivo": 10},
            "telegram": False,
        }
        with patch(
            "agendador_pre_live.executar", return_value=retorno
        ), patch(
            "agendador_pre_live.ler_modo_manutencao",
            return_value={"ativo": False},
        ):
            executar_slot(
                self.pasta, object(), {},
                "2026-08-27|12:00", "12:00", agora=agora,
            )
        agenda = json.loads(
            (self.pasta / "pre_live_agenda.json").read_text(encoding="utf-8")
        )
        item = agenda["execucoes"]["2026-08-27|12:00"]
        self.assertEqual("concluida", item["estado"])
        self.assertEqual(10, item["jogos_analisados"])
        self.assertEqual(14, item["candidatos_elegiveis"])
        self.assertEqual(4, item["jogos_nao_analisados_limite"])
        self.assertEqual(0.7143, item["cobertura_analise"])
        self.assertEqual(10, item["limite_analise"]["efetivo"])
        self.assertEqual(2, item["bilhetes"])

    def test_slot_com_api_indisponivel_fica_pronto_para_repetir(self):
        agora = datetime(2026, 8, 27, 12, 5, tzinfo=timezone.utc)
        retorno = {
            "jogos_calendario": 0,
            "jogos_analisados": 0,
            "candidatos_elegiveis": 0,
            "jogos_nao_analisados_limite": 0,
            "cobertura_analise": 1.0,
            "limite_analise": {"configurado": 60, "efetivo": 60},
            "bilhetes": 0,
            "motivo_odds": "pagina_indisponivel",
        }
        with patch(
            "agendador_pre_live.executar", return_value=retorno
        ):
            executar_slot(
                self.pasta, object(), {},
                "2026-08-27|12:00", "12:00", agora=agora,
            )

        agenda = json.loads(
            (self.pasta / "pre_live_agenda.json").read_text(encoding="utf-8")
        )
        item = agenda["execucoes"]["2026-08-27|12:00"]
        self.assertEqual("falha_temporaria", item["estado"])
        self.assertEqual("pagina_indisponivel", item["motivo"])
        self.assertIn("proxima_tentativa_em", item)

    def test_slot_com_reserva_live_protegida_tambem_repete(self):
        agora = datetime(2026, 8, 27, 12, 5, tzinfo=timezone.utc)
        retorno = {
            "jogos_analisados": 0,
            "candidatos_elegiveis": 0,
            "jogos_nao_analisados_limite": 0,
            "cobertura_analise": 1.0,
            "limite_analise": {
                "configurado": 60,
                "efetivo": 0,
                "motivo": "reserva_ao_vivo_protegida",
            },
            "bilhetes": 0,
            "motivo_odds": "reserva_ao_vivo_protegida",
        }
        with patch(
            "agendador_pre_live.executar", return_value=retorno
        ):
            executar_slot(
                self.pasta, object(), {},
                "2026-08-27|12:00", "12:00", agora=agora,
            )

        agenda = json.loads(
            (self.pasta / "pre_live_agenda.json").read_text(encoding="utf-8")
        )
        item = agenda["execucoes"]["2026-08-27|12:00"]
        self.assertEqual("falha_temporaria", item["estado"])
        self.assertEqual("reserva_ao_vivo_protegida", item["motivo"])
        self.assertIn("proxima_tentativa_em", item)

    def test_reconciliacao_persiste_diagnostico_sem_telegram(self):
        retorno = {
            "liquidacao": {
                "pendentes": 8,
                "fixtures_consultadas": 10,
                "finalizados": 2,
                "greens": 1,
                "reds": 1,
                "anulados": 0,
            },
            "telegram": {"editados": 0, "falhas": 0},
            "telegram_listas": {"editados": 1, "falhas": 0},
        }
        agora = datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc)
        with patch.dict(os.environ, {
            "PRELIVE_HORARIOS": "23:59",
            "PRELIVE_AGENDADOR_ATIVO": "1",
        }), patch(
            "agendador_pre_live.APIFootball", return_value=object()
        ), patch(
            "agendador_pre_live.reconciliar_entregas_pre_live",
            return_value=retorno,
        ):
            resumo = executar_loop(
                self.pasta, uma_vez=True, agora_fn=lambda: agora
            )

        estado = json.loads(
            (self.pasta / "pre_live_reconciliacao_estado.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(resumo["falhas"], 0)
        self.assertEqual(estado["estado"], "saudavel")
        self.assertEqual(estado["pendentes"], 8)
        self.assertEqual(estado["finalizados"], 2)
        self.assertEqual(estado["greens"], 1)
        self.assertEqual(estado["reds"], 1)
        self.assertEqual(estado["listas_telegram_editadas"], 1)

    def test_falha_de_reconciliacao_fica_observavel(self):
        agora = datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc)
        with patch.dict(os.environ, {
            "PRELIVE_HORARIOS": "23:59",
            "PRELIVE_AGENDADOR_ATIVO": "1",
        }), patch(
            "agendador_pre_live.APIFootball", return_value=object()
        ), patch(
            "agendador_pre_live.reconciliar_entregas_pre_live",
            side_effect=RuntimeError("falha simulada"),
        ):
            resumo = executar_loop(
                self.pasta, uma_vez=True, agora_fn=lambda: agora
            )

        estado = json.loads(
            (self.pasta / "pre_live_reconciliacao_estado.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(resumo["falhas"], 1)
        self.assertEqual(estado["estado"], "falha")
        self.assertEqual(estado["erro"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
