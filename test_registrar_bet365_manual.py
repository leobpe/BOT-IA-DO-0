import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from banco import BancoMonitor, normalizar_texto
from bet365_odds import auditar_observacoes_bet365
from registrar_bet365_manual import (
    preservar_evidencia,
    registrar_captura_manual,
    validar_url_evento_bet365,
)


class RegistrarBet365ManualTest(unittest.TestCase):
    def test_url_exige_evento_do_site_brasileiro(self):
        self.assertEqual(
            validar_url_evento_bet365(
                "https://www.bet365.bet.br/#/IP/EV123456C1"
            ),
            "EV123456",
        )
        with self.assertRaises(ValueError):
            validar_url_evento_bet365(
                "https://exemplo.com/#/IP/EV123456C1"
            )
        with self.assertRaises(ValueError):
            validar_url_evento_bet365(
                "https://www.bet365.bet.br/#/IP/B1"
            )

    def test_registra_oferta_manual_com_imagem_hash_e_partida(self):
        with tempfile.NamedTemporaryFile(
            dir=Path.cwd(), suffix=".png", delete=False
        ) as arquivo_evidencia:
            arquivo_evidencia.write(
                b"\x89PNG\r\n\x1a\n" + b"evidencia-de-teste"
            )
            evidencia = Path(arquivo_evidencia.name)
        with tempfile.NamedTemporaryFile(
            dir=Path.cwd(), suffix=".db", delete=False
        ) as arquivo_banco:
            caminho_banco = Path(arquivo_banco.name)
        caminho_banco.unlink()
        try:
            banco = BancoMonitor(caminho_banco)
            try:
                banco.conexao.execute(
                    """
                    INSERT INTO partidas (
                        packball_url, mandante, visitante,
                        mandante_normalizado, visitante_normalizado,
                        primeira_coleta, ultima_coleta
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "https://packball.com/partida/1",
                        "Time A",
                        "Time B",
                        normalizar_texto("Time A"),
                        normalizar_texto("Time B"),
                        "2026-07-25T20:00:00",
                        "2026-07-25T20:00:00",
                    ),
                )
                banco.conexao.commit()
            finally:
                banco.fechar()

            with patch(
                "registrar_bet365_manual.preservar_evidencia",
                return_value={
                    "sha256": "a" * 64,
                    "referencia": (
                        "evidencias_bet365/20260725/"
                        + "a" * 64
                        + ".png"
                    ),
                    "tamanho_bytes": evidencia.stat().st_size,
                },
            ):
                resultado = registrar_captura_manual(
                    mandante_packball="Time A",
                    visitante_packball="Time B",
                    mandante_bet365="Team A",
                    visitante_bet365="Team B",
                    url_evento=(
                        "https://www.bet365.bet.br/#/IP/EV123456C1"
                    ),
                    periodo="2T",
                    titulo_mercado="Escanteios Asiáticos - 2º Tempo",
                    linha="5.5",
                    odd_over="1.80",
                    odd_under="1.90",
                    evidencia=evidencia,
                    caminho_banco=caminho_banco,
                )

            banco = BancoMonitor(caminho_banco)
            try:
                linha = banco.conexao.execute(
                    """
                    SELECT * FROM observacoes_fontes_odds
                    WHERE id=?
                    """,
                    (resultado["observacao_id"],),
                ).fetchone()
                auditoria = auditar_observacoes_bet365(banco.conexao)
            finally:
                banco.fechar()

            self.assertEqual(linha["estado"], "oferta_valida")
            self.assertEqual(linha["metodo_coleta"], "manual_usuario")
            self.assertEqual(len(linha["evidencia_sha256"]), 64)
            self.assertTrue(linha["evidencia_referencia"])
            self.assertEqual(
                json.loads(linha["oferta_json"])["metodo_coleta"],
                "manual_usuario",
            )
            self.assertTrue(auditoria["saudavel"])
            self.assertTrue(auditoria["comprovada"])
            self.assertFalse(resultado["ativa_no_monitor"])
        finally:
            evidencia.unlink(missing_ok=True)
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho_banco) + sufixo).unlink(missing_ok=True)

    def test_coleta_manual_sem_imagem_real_falha_fechada(self):
        with tempfile.NamedTemporaryFile(
            dir=Path.cwd(), suffix=".png", delete=False
        ) as arquivo:
            arquivo.write("isto não é uma imagem".encode("utf-8"))
            evidencia = Path(arquivo.name)
        try:
            with self.assertRaisesRegex(ValueError, "PNG, JPG ou WEBP"):
                preservar_evidencia(evidencia)
        finally:
            evidencia.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
