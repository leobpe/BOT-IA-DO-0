import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from executar_pre_live import (
    calcular_limite_analise,
    executar,
    filtrar_avaliacoes_ineditas,
    linhagem_operacional_pre_live,
)
from repositorio_pre_live import verificar_banco_pre_live


class ExecutarPreLiveTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / f".teste_executar_pre_live_{uuid4().hex}"
        self.pasta.mkdir()

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_cancelamento_seguro_cria_banco_estado_e_backup(self):
        resultado = executar(
            pasta=self.pasta,
            data_alvo="2026-08-27",
            api=object(),
            cancelar_fn=lambda: True,
        )
        self.assertTrue(resultado["cancelado"])
        self.assertEqual(resultado["preparacao_banco"]["estado"], "novo")
        backup = (
            self.pasta / "backups" / "pre_live"
            / resultado["backup"]["arquivo"]
        )
        self.assertTrue(backup.exists())
        self.assertTrue(verificar_banco_pre_live(backup)["valido"])
        self.assertTrue((self.pasta / "pre_live_estado.json").exists())
        self.assertEqual(
            "validacao-pre-live-preciso-v2",
            resultado["filtro_preciso_ancora"]["versao"],
        )
        self.assertEqual(
            60, resultado["filtro_preciso_ancora"]["tamanho_coorte"]
        )
        self.assertEqual(
            0,
            resultado["filtro_preciso_prospectivo_antes"]["candidatos"],
        )

    def test_limite_dinamico_amplia_cobertura_sem_consumir_reserva_live(self):
        class API:
            @staticmethod
            def consumo_atual():
                return {"restante_seguro_dia": 3220}

        limite = calcular_limite_analise(
            API(), solicitado=60, reserva_ao_vivo=2500
        )
        self.assertEqual(60, limite["efetivo"])
        self.assertEqual("limite_configurado", limite["motivo"])

        limitado = calcular_limite_analise(
            API(), solicitado=80, reserva_ao_vivo=3000
        )
        self.assertEqual(18, limitado["efetivo"])
        self.assertEqual(
            "reserva_ao_vivo_protegida", limitado["motivo"]
        )

    def test_limite_recarrega_contador_compartilhado_antes_do_calculo(self):
        class API:
            restante = 0

            def recarregar_uso_compartilhado(self):
                self.restante = 7000
                return True

            def consumo_atual(self):
                return {"restante_seguro_dia": self.restante}

        limite = calcular_limite_analise(
            API(), solicitado=60, reserva_ao_vivo=2500
        )

        self.assertEqual(60, limite["efetivo"])
        self.assertTrue(limite["contador_compartilhado_recarregado"])

    def test_limite_dinamico_bloqueia_pre_live_quando_so_resta_reserva(self):
        class API:
            @staticmethod
            def consumo_atual():
                return {"restante_seguro_dia": 2000}

        limite = calcular_limite_analise(
            API(), solicitado=60, reserva_ao_vivo=2500
        )
        self.assertEqual(0, limite["efetivo"])
        self.assertEqual(
            "reserva_ao_vivo_protegida", limite["motivo"]
        )

    def test_execucao_expoe_reserva_protegida_como_causa_real(self):
        class API:
            @staticmethod
            def consumo_atual():
                return {"restante_seguro_dia": 2000}

            @staticmethod
            def jogos_por_data(_data, _fuso):
                return []

            @staticmethod
            def odds_pre_jogo_por_data(_data):
                return {
                    "completo": False,
                    "paginas": 0,
                    "motivo": "pagina_indisponivel",
                    "itens": [],
                }

        with patch.dict(os.environ, {
            "BETSAPI_PRELIVE_ATIVA": "0",
            "PRELIVE_APLICACAO_AUTOMATICA": "0",
            "TELEGRAM_BOT_TOKEN": "",
        }, clear=False):
            resultado = executar(
                pasta=self.pasta,
                data_alvo="2026-08-27",
                api=API(),
            )

        self.assertEqual(0, resultado["limite_analise"]["efetivo"])
        self.assertEqual(
            "reserva_ao_vivo_protegida", resultado["motivo_odds"]
        )

    def test_execucao_reclassifica_cota_reconciliada_apos_primeira_resposta(self):
        class API:
            consultas_consumo = 0

            @classmethod
            def consumo_atual(cls):
                cls.consultas_consumo += 1
                restante = 7000 if cls.consultas_consumo == 1 else 491
                return {
                    "dia": "2026-08-31",
                    "consumo_dia": 7500 - restante,
                    "restante_seguro_dia": restante,
                }

            @staticmethod
            def jogos_por_data(_data, _fuso):
                return []

            @staticmethod
            def odds_pre_jogo_por_data(_data):
                return {
                    "completo": False,
                    "paginas": 0,
                    "motivo": "pagina_indisponivel",
                    "itens": [],
                }

        with patch.dict(os.environ, {
            "BETSAPI_PRELIVE_ATIVA": "0",
            "PRELIVE_APLICACAO_AUTOMATICA": "0",
            "TELEGRAM_BOT_TOKEN": "",
        }, clear=False):
            resultado = executar(
                pasta=self.pasta,
                data_alvo="2026-08-27",
                api=API(),
            )

        self.assertEqual(60, resultado["limite_analise"]["efetivo"])
        self.assertEqual(
            491,
            resultado["limite_analise"]["restante_seguro_apos_catalogo"],
        )
        self.assertEqual(
            "reserva_ao_vivo_protegida", resultado["motivo_odds"]
        )

    def test_linhagem_separa_mudanca_de_limite_ou_reserva(self):
        base = {
            "configurado": 60,
            "reserva_ao_vivo": 2500,
        }
        primeira = linhagem_operacional_pre_live(base)
        self.assertEqual(primeira, linhagem_operacional_pre_live(dict(base)))
        self.assertNotEqual(
            primeira,
            linhagem_operacional_pre_live({
                "configurado": 80, "reserva_ao_vivo": 2500,
            }),
        )
        self.assertNotEqual(
            primeira,
            linhagem_operacional_pre_live({
                "configurado": 60, "reserva_ao_vivo": 3000,
            }),
        )

    def test_remove_publicados_antes_de_montar_novo_ranking(self):
        avaliacoes = [
            {"jogo": {"fixture_id": 10}, "avaliacao": {}},
            {"jogo": {"fixture_id": 20}, "avaliacao": {}},
            {"jogo": {"fixture_id": 30}, "avaliacao": {}},
        ]

        ineditas, excluidas = filtrar_avaliacoes_ineditas(
            avaliacoes, {10, 30}
        )

        self.assertEqual(2, excluidas)
        self.assertEqual(
            [20],
            [item["jogo"]["fixture_id"] for item in ineditas],
        )


if __name__ == "__main__":
    unittest.main()
