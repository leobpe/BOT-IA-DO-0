import unittest
from unittest.mock import AsyncMock, Mock, patch

import bot


class BotComandosTest(unittest.IsolatedAsyncioTestCase):
    def test_formatacao_sem_pedido_nao_parece_sinal(self):
        texto = bot.formatar_fila_odds_manual({
            "solicitacoes": [],
            "janela_minutos": 6,
        })

        self.assertIn("Nenhuma partida", texto)
        self.assertIn("não representa indicação de aposta", texto)

    def test_formatacao_limita_cinco_e_exibe_contexto(self):
        solicitacoes = [
            {
                "partida": f"Time {indice} x Rival {indice}",
                "periodo": "2T",
                "status_partida": "61 '",
                "placar": "0-0",
                "pontuacao_tecnica": 80.0,
                "packball_url": f"https://packball.com/partida/{indice}",
            }
            for indice in range(6)
        ]

        texto = bot.formatar_fila_odds_manual({
            "solicitacoes": solicitacoes,
            "janela_minutos": 6,
        })

        self.assertIn("Somente captura de odds", texto)
        self.assertIn("Time 0 x Rival 0", texto)
        self.assertNotIn("Time 5 x Rival 5", texto)
        self.assertIn("Outras partidas na fila: 1", texto)

    async def test_oddsmanual_recusa_usuario_nao_administrador(self):
        mensagem = Mock()
        mensagem.reply_text = AsyncMock()
        update = Mock(
            effective_message=mensagem,
            effective_user=Mock(id=999),
        )
        with patch.object(bot, "ADMIN_ID", "123"):
            await bot.oddsmanual(update, Mock())

        mensagem.reply_text.assert_awaited_once_with(
            "⛔ Comando restrito ao administrador."
        )

    async def test_oddsmanual_admin_consulta_banco_sem_rede(self):
        mensagem = Mock()
        mensagem.reply_text = AsyncMock()
        update = Mock(
            effective_message=mensagem,
            effective_user=Mock(id=123),
        )
        banco = Mock()
        banco.conexao = Mock()
        with (
            patch.object(bot, "ADMIN_ID", "123"),
            patch.object(bot, "BancoMonitor", return_value=banco),
            patch.object(
                bot,
                "listar_solicitacoes_odds_manuais",
                return_value={
                    "solicitacoes": [],
                    "janela_minutos": 6,
                },
            ) as listar,
        ):
            await bot.oddsmanual(update, Mock())

        listar.assert_called_once_with(banco.conexao)
        banco.fechar.assert_called_once_with()
        mensagem.reply_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
