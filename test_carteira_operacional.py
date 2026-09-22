import json
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from carteira_operacional import (
    CHAVE_ATUAL,
    PREFIXO_EPOCA,
    auditar_carteira_operacional,
    registrar_carteira_operacional,
)


class CarteiraOperacionalTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_carteira_operacional.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)
        self.hashes = {"motor_sinais.py": "abc"}

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def test_reinicio_idempotente_e_mudanca_abre_nova_epoca(self):
        primeira = registrar_carteira_operacional(
            self.banco.conexao,
            {"GOLS_ANTECIPADOS_GRUPO_ATIVO": "1"},
            agora=datetime(2026, 9, 8, 10, 0),
            hashes_componentes=self.hashes,
        )
        repetida = registrar_carteira_operacional(
            self.banco.conexao,
            {"GOLS_ANTECIPADOS_GRUPO_ATIVO": "1"},
            agora=datetime(2026, 9, 8, 11, 0),
            hashes_componentes=self.hashes,
        )
        segunda = registrar_carteira_operacional(
            self.banco.conexao,
            {"GOLS_ANTECIPADOS_GRUPO_ATIVO": "0"},
            agora=datetime(2026, 9, 8, 12, 0),
            hashes_componentes=self.hashes,
        )

        self.assertTrue(primeira["nova_epoca"])
        self.assertFalse(repetida["nova_epoca"])
        self.assertEqual(primeira["ativada_em"], repetida["ativada_em"])
        self.assertTrue(segunda["nova_epoca"])
        self.assertEqual(
            primeira["fingerprint"], segunda["fingerprint_anterior"]
        )
        quantidade = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM metadados WHERE chave LIKE ?",
            (f"{PREFIXO_EPOCA}%",),
        ).fetchone()[0]
        self.assertEqual(2, quantidade)

    def test_epoca_e_imutavel_e_credenciais_nao_sao_persistidas(self):
        estado = registrar_carteira_operacional(
            self.banco.conexao,
            {
                "SINAIS_TESTE_ATIVO": "1",
                "TELEGRAM_BOT_TOKEN": "segredo-telegram",
                "API_FOOTBALL_KEY": "segredo-api",
            },
            hashes_componentes=self.hashes,
        )
        serializado = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE_ATUAL,)
        ).fetchone()[0]
        self.assertNotIn("segredo-telegram", serializado)
        self.assertNotIn("segredo-api", serializado)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor='{}' WHERE chave=?",
                    (estado["chave_epoca"],),
                )

    def test_auditoria_detecta_epoca_referenciada_ausente(self):
        estado = registrar_carteira_operacional(
            self.banco.conexao, {}, hashes_componentes=self.hashes
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                "DROP TRIGGER trg_carteira_operacional_epoca_delete_imutavel"
            )
            self.banco.conexao.execute(
                "DELETE FROM metadados WHERE chave=?",
                (estado["chave_epoca"],),
            )
        auditoria = auditar_carteira_operacional(
            self.banco.conexao, {}, hashes_componentes=self.hashes
        )
        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            "epoca_referenciada_ausente", auditoria["estado"]
        )


if __name__ == "__main__":
    unittest.main()
