import unittest
from pathlib import Path
from unittest.mock import patch

from reiniciar_watchdog import (
    _watchdog_novo_comprovado,
    reiniciar_watchdog_isolado,
)


class ReiniciarWatchdogTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_reiniciar_watchdog"
        self.pasta.mkdir(exist_ok=True)

    def tearDown(self):
        for caminho in self.pasta.iterdir():
            caminho.unlink()
        self.pasta.rmdir()

    def test_nao_reinicia_quando_codigo_ja_esta_atualizado(self):
        estado = {
            "pid": 123,
            "status": "ativo",
            "codigo_hash": "qualquer",
        }
        with patch(
            "reiniciar_watchdog.estado_codigo_runtime",
            return_value="atualizado",
        ):
            resultado = reiniciar_watchdog_isolado(
                self.pasta,
                iniciar_fn=lambda _: self.fail("não deveria iniciar"),
                ler_estado_fn=lambda _: estado,
                verificar_pid=lambda pid: pid == 123,
                verificar_trava=lambda _: True,
            )

        self.assertEqual(resultado["estado"], "ja_atualizado")
        self.assertEqual(resultado["pid"], 123)
        self.assertTrue(resultado["monitor_preservado"])

    def test_recusa_identidade_sem_pid_e_trava_concordantes(self):
        with self.assertRaisesRegex(RuntimeError, "PID e trava"):
            reiniciar_watchdog_isolado(
                self.pasta,
                ler_estado_fn=lambda _: {
                    "pid": 123, "status": "ativo"
                },
                verificar_pid=lambda _: True,
                verificar_trava=lambda _: False,
            )

    def test_adota_watchdog_que_supervisor_iniciou_primeiro(self):
        estado = {
            "pid": 456,
            "status": "ativo",
            "codigo_hash": "novo",
        }
        with patch(
            "reiniciar_watchdog.estado_codigo_runtime",
            return_value="atualizado",
        ):
            pid = _watchdog_novo_comprovado(
                self.pasta,
                estado,
                pid_anterior=123,
                verificar_pid=lambda valor: valor == 456,
                verificar_trava=lambda _: True,
            )

        self.assertEqual(pid, 456)

    def test_nao_adota_pid_antigo_com_estado_regravado(self):
        estado = {
            "pid": 123,
            "status": "ativo",
            "codigo_hash": "novo",
        }
        pid = _watchdog_novo_comprovado(
            self.pasta,
            estado,
            pid_anterior=123,
            verificar_pid=lambda _: True,
            verificar_trava=lambda _: True,
        )

        self.assertIsNone(pid)


if __name__ == "__main__":
    unittest.main()
