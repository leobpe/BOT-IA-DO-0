import shutil
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import mapear_bet365_manual


class TestMapearBet365Manual(unittest.TestCase):
    def test_cria_caminhos_unicos_e_auditaveis(self):
        pasta = Path.cwd() / ".teste_capturas_bet365"
        try:
            with patch.object(
                mapear_bet365_manual,
                "PASTA_SAIDA",
                pasta,
            ):
                caminhos = mapear_bet365_manual.criar_caminhos_captura(
                    datetime(2026, 7, 26, 12, 34, 56)
                )
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

        self.assertEqual(
            caminhos["json"].name,
            "bet365_20260726_123456.json",
        )
        self.assertEqual(
            caminhos["txt"].name,
            "bet365_20260726_123456.txt",
        )
        self.assertEqual(
            caminhos["imagem"].name,
            "bet365_20260726_123456.png",
        )

    def test_aguarda_e_consumo_sinal_local(self):
        pasta = Path.cwd() / ".teste_sinal_bet365"
        caminho = pasta / ".capturar"
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            def criar_sinal():
                caminho.touch()

            thread = threading.Timer(0.05, criar_sinal)
            thread.start()
            mapear_bet365_manual.aguardar_sinal(
                caminho,
                timeout_segundos=1,
            )
            thread.join()
            self.assertFalse(caminho.exists())
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

    def test_aguarda_sinal_respeita_timeout(self):
        caminho = Path.cwd() / ".sinal_bet365_inexistente"
        caminho.unlink(missing_ok=True)
        with self.assertRaises(TimeoutError):
            mapear_bet365_manual.aguardar_sinal(
                caminho,
                timeout_segundos=0.01,
            )


if __name__ == "__main__":
    unittest.main()
