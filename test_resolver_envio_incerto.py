import json
import unittest
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from resolver_envio_incerto import (
    listar_envios_incertos,
    resolver_envio_incerto,
)
from watchdog import auditar_integridade_telegram


class ResolverEnvioIncertoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_resolver_envio_incerto.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:00:00",
            "url": "https://packball.com/match/reconciliar/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "60 '",
        })
        self.sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft", "linha": 1.5, "odd": 1.8,
            "pontuacao_tecnica": 85, "regra_versao": "sinais-v4",
            "status": "aprovado",
        }])[0]

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def criar_incerto(self, status="enviando"):
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "chat-oficial",
            status,
            instante="2026-07-20T12:00:00",
        )
        return self.banco.conexao.execute(
            "SELECT id FROM entregas_alertas WHERE status=?", (status,)
        ).fetchone()[0]

    def test_lista_sem_expor_credenciais(self):
        entrega_id = self.criar_incerto()

        itens = listar_envios_incertos(
            self.banco.conexao, datetime(2026, 7, 20, 12, 3)
        )

        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["entrega_id"], entrega_id)
        self.assertEqual(itens[0]["mercado"], "gol_ft")
        self.assertNotIn("token", str(itens).lower())

    def test_timeout_explicito_fica_incerto_sem_aguardar_tolerancia(self):
        entrega_id = self.criar_incerto("incerto")

        itens = listar_envios_incertos(
            self.banco.conexao, datetime(2026, 7, 20, 12, 0)
        )
        auditoria = auditar_integridade_telegram(
            self.banco.conexao, datetime(2026, 7, 20, 12, 0)
        )

        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["entrega_id"], entrega_id)
        self.assertEqual(itens[0]["status"], "incerto")
        self.assertEqual(auditoria["envios_incertos"], 1)

    def test_duplicidade_historica_conta_apenas_tentativa_mais_recente(self):
        antigo_id = self.criar_incerto("enviando")
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "chat-oficial",
            "incerto",
            instante="2026-07-20T12:01:00",
        )
        recente_id = self.banco.conexao.execute(
            "SELECT id FROM entregas_alertas WHERE status='incerto'"
        ).fetchone()[0]

        itens = listar_envios_incertos(
            self.banco.conexao, datetime(2026, 7, 20, 12, 3)
        )
        auditoria = auditar_integridade_telegram(
            self.banco.conexao, datetime(2026, 7, 20, 12, 3)
        )

        self.assertEqual([item["entrega_id"] for item in itens], [recente_id])
        self.assertNotEqual(antigo_id, recente_id)
        self.assertEqual(auditoria["envios_incertos"], 1)
        self.assertEqual(auditoria["envios_oficiais_incertos"], 1)

        obsoleto = resolver_envio_incerto(
            self.banco.conexao,
            antigo_id,
            "nao_enviado",
            datetime(2026, 7, 20, 12, 3),
        )
        self.assertFalse(obsoleto["resolvido"])
        self.assertEqual(obsoleto["motivo"], "entrega_nao_esta_incerta")

    def test_confirmacao_manual_conta_entrega_e_preserva_auditoria(self):
        entrega_id = self.criar_incerto()

        resultado = resolver_envio_incerto(
            self.banco.conexao,
            entrega_id,
            "entregue",
            datetime(2026, 7, 20, 12, 3),
            telegram_message_id=321,
        )
        auditoria = auditar_integridade_telegram(
            self.banco.conexao, datetime(2026, 7, 20, 12, 4)
        )

        self.assertTrue(resultado["resolvido"])
        self.assertTrue(
            self.banco.alerta_ja_entregue(self.sinal_id, "chat-oficial")
        )
        estados = self.banco.conexao.execute(
            "SELECT status FROM entregas_alertas ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [item[0] for item in estados],
            ["confirmado_manual", "entregue"],
        )
        self.assertEqual(auditoria["envios_incertos"], 0)
        self.assertEqual(auditoria["confirmacoes_telegram_validas"], 1)
        prova = self.banco.conexao.execute(
            """
            SELECT provedor, provedor_destino_id, provedor_mensagem_id
            FROM entregas_alertas WHERE status='entregue'
            """
        ).fetchone()
        self.assertEqual(tuple(prova), ("telegram", "chat-oficial", "321"))

    def test_confirmacao_manual_exige_message_id_do_telegram(self):
        entrega_id = self.criar_incerto()

        with self.assertRaisesRegex(ValueError, "telegram_message_id"):
            resolver_envio_incerto(
                self.banco.conexao,
                entrega_id,
                "entregue",
                datetime(2026, 7, 20, 12, 3),
            )

        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT status FROM entregas_alertas WHERE id=?",
                (entrega_id,),
            ).fetchone()[0],
            "enviando",
        )

    def test_reconcilia_edicao_usando_message_id_original_comprovado(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "123:teste",
            "entregue",
            instante="2026-07-20T12:00:00",
            provedor="telegram",
            provedor_destino_id="123",
            provedor_mensagem_id=555,
            confirmacao={
                "ok": True, "provedor": "telegram", "message_id": 555,
            },
        )
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "123:teste:resultado",
            "incerto",
            instante="2026-07-20T12:02:00",
        )
        entrega_id = self.banco.conexao.execute(
            "SELECT id FROM entregas_alertas WHERE status='incerto'"
        ).fetchone()[0]

        listagem = listar_envios_incertos(
            self.banco.conexao, datetime(2026, 7, 20, 12, 3)
        )
        resultado = resolver_envio_incerto(
            self.banco.conexao,
            entrega_id,
            "entregue",
            datetime(2026, 7, 20, 12, 3),
        )

        self.assertTrue(listagem[0]["reconciliacao_edicao_possivel"])
        self.assertEqual(listagem[0]["mensagem_id_origem"], 555)
        self.assertEqual(listagem[0]["tipo_operacao"], "resultado")
        self.assertTrue(resultado["edicao"])
        prova = self.banco.conexao.execute(
            """
            SELECT provedor_mensagem_id, confirmacao_json
            FROM entregas_alertas
            WHERE canal='123:teste:resultado' AND status='entregue'
            """
        ).fetchone()
        self.assertIsNone(prova["provedor_mensagem_id"])
        self.assertEqual(
            json.loads(prova["confirmacao_json"])["message_id_origem"],
            555,
        )

    def test_nao_enviado_volta_para_fila_de_erro_sem_apagar_evidencia(self):
        entrega_id = self.criar_incerto("tentando")

        resultado = resolver_envio_incerto(
            self.banco.conexao,
            entrega_id,
            "nao_enviado",
            datetime(2026, 7, 20, 12, 3),
        )

        self.assertTrue(resultado["resolvido"])
        linhas = self.banco.conexao.execute(
            "SELECT status, erro FROM entregas_alertas ORDER BY id"
        ).fetchall()
        self.assertEqual(linhas[0]["status"], "nao_enviado_manual")
        self.assertEqual(linhas[1]["status"], "erro")
        self.assertIn("reconciliacao_manual", linhas[1]["erro"])

    def test_nao_altera_entrega_que_ja_possui_estado_final(self):
        entrega_id = self.criar_incerto()
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "chat-oficial",
            "entregue",
            instante="2026-07-20T12:01:00",
        )

        resultado = resolver_envio_incerto(
            self.banco.conexao, entrega_id, "nao_enviado"
        )

        self.assertFalse(resultado["resolvido"])
        self.assertEqual(resultado["motivo"], "entrega_nao_esta_incerta")

    def test_reconcilia_correcao_sem_duplicar_prova_telegram(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "123:teste", "entregue"
        )
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior, motivo
                ) VALUES (?, '2026-07-20T12:01:00',
                          '2026-07-20T12:00:00', 'green', 0.8,
                          'resultado provisorio')
                """,
                (self.sinal_id,),
            )
        revisao_id = cursor.lastrowid
        token = self.banco.reservar_notificacao_correcao(
            revisao_id, self.sinal_id, "123:teste",
            instante="2026-07-20T12:02:00",
        )
        self.assertTrue(token)
        self.assertTrue(self.banco.finalizar_notificacao_correcao(
            revisao_id,
            self.sinal_id,
            "123:teste",
            token,
            "incerto",
            "timeout",
            instante="2026-07-20T12:02:00",
        ))
        entrega_id = self.banco.conexao.execute(
            """
            SELECT id FROM entregas_alertas
            WHERE sinal_id=? AND canal=? AND status='incerto'
            """,
            (
                self.sinal_id,
                f"123:teste:correcao:{revisao_id}",
            ),
        ).fetchone()[0]

        resultado = resolver_envio_incerto(
            self.banco.conexao,
            entrega_id,
            "entregue",
            datetime(2026, 7, 20, 12, 3),
            telegram_message_id=654,
        )
        auditoria = auditar_integridade_telegram(
            self.banco.conexao, datetime(2026, 7, 20, 12, 4)
        )

        self.assertTrue(resultado["resolvido"])
        revisao = self.banco.conexao.execute(
            """
            SELECT notificacao_status, notificacao_provedor,
                   notificacao_destino_id, notificacao_mensagem_id
            FROM revisoes_resultados WHERE id=?
            """,
            (revisao_id,),
        ).fetchone()
        self.assertEqual(
            tuple(revisao), ("entregue", "telegram", "123", "654")
        )
        estados = self.banco.conexao.execute(
            """
            SELECT status FROM entregas_alertas
            WHERE sinal_id=? AND canal=? ORDER BY id
            """,
            (
                self.sinal_id,
                f"123:teste:correcao:{revisao_id}",
            ),
        ).fetchall()
        self.assertEqual([linha["status"] for linha in estados], [
            "confirmado_manual"
        ])
        self.assertEqual(auditoria["correcoes_pendentes"], 0)
        self.assertEqual(auditoria["envios_incertos"], 0)
        self.assertEqual(auditoria["confirmacoes_telegram_validas"], 1)
        self.assertEqual(auditoria["confirmacoes_telegram_duplicadas"], 0)


if __name__ == "__main__":
    unittest.main()
