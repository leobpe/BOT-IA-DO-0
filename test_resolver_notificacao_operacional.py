import hashlib
import unittest
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from resolver_notificacao_operacional import (
    listar_notificacoes_incertas,
    resolver_notificacao_operacional,
)
from watchdog import auditar_notificacoes_operacionais


class ResolverNotificacaoOperacionalTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_resolver_notificacao.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def criar_incerta(self, status="enviando"):
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO notificacoes_operacionais (
                    chave, destino, criado_em, tentado_em,
                    status, tentativas, resumo
                ) VALUES (?, 'admin', '2026-07-20T12:00:00',
                          '2026-07-20T12:00:00', ?, 1,
                          'ALERTA DE TESTE')
                """,
                (hashlib.sha256(b"alerta").hexdigest(), status),
            )
        return cursor.lastrowid

    def test_lista_sem_texto_token_ou_conteudo_da_mensagem(self):
        notificacao_id = self.criar_incerta()

        itens = listar_notificacoes_incertas(
            self.banco.conexao, datetime(2026, 7, 20, 12, 3)
        )

        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["notificacao_id"], notificacao_id)
        self.assertEqual(itens[0]["destino"], "admin")
        self.assertEqual(itens[0]["resumo"], "ALERTA DE TESTE")
        self.assertNotIn("texto", itens[0])
        self.assertNotIn("token", str(itens).lower())

    def test_confirmacao_manual_exige_e_persiste_message_id(self):
        notificacao_id = self.criar_incerta()
        with self.assertRaisesRegex(ValueError, "telegram_message_id"):
            resolver_notificacao_operacional(
                self.banco.conexao, notificacao_id, "entregue"
            )

        resultado = resolver_notificacao_operacional(
            self.banco.conexao,
            notificacao_id,
            "entregue",
            datetime(2026, 7, 20, 12, 3),
            telegram_message_id=456,
        )
        auditoria = auditar_notificacoes_operacionais(
            self.banco.conexao, datetime(2026, 7, 20, 12, 4)
        )

        self.assertTrue(resultado["resolvido"])
        self.assertEqual(resultado["telegram_message_id"], 456)
        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["entregues_com_prova"], 1)

    def test_nao_enviado_vira_erro_retentavel_sem_apagar_intencao(self):
        notificacao_id = self.criar_incerta("tentando")

        resultado = resolver_notificacao_operacional(
            self.banco.conexao,
            notificacao_id,
            "nao_enviado",
            datetime(2026, 7, 20, 12, 3),
        )

        linha = self.banco.conexao.execute(
            """
            SELECT status, erro, tentativas
            FROM notificacoes_operacionais WHERE id=?
            """,
            (notificacao_id,),
        ).fetchone()
        self.assertTrue(resultado["resolvido"])
        self.assertEqual(linha["status"], "erro")
        self.assertIn("reconciliacao_manual", linha["erro"])
        self.assertEqual(linha["tentativas"], 1)

    def test_nao_altera_notificacao_ja_finalizada(self):
        notificacao_id = self.criar_incerta()
        resolver_notificacao_operacional(
            self.banco.conexao,
            notificacao_id,
            "entregue",
            telegram_message_id=789,
        )

        repetida = resolver_notificacao_operacional(
            self.banco.conexao,
            notificacao_id,
            "nao_enviado",
        )

        self.assertFalse(repetida["resolvido"])
        self.assertEqual(repetida["motivo"], "notificacao_nao_esta_incerta")


if __name__ == "__main__":
    unittest.main()
