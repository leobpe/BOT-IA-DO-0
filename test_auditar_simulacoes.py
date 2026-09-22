import unittest
from pathlib import Path

from auditar_simulacoes import carregar_auditoria, formatar_item
from banco import BancoMonitor
from motor_sinais import VERSAO_REGRAS


class AuditarSimulacoesTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_auditar_simulacoes.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def test_destaca_primeira_decisao_e_exclui_leitura_posterior(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-21T12:00:00",
            "url": "https://packball.com/match/1/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "20 '",
        })
        primeiro = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ht", "linha": 0.5, "odd": 1.8,
            "pontuacao_tecnica": 80, "regra_versao": VERSAO_REGRAS,
            "status": "aprovado",
        }], "2026-07-21T12:00:00")[0]
        segundo = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ht", "linha": 0.5, "odd": 1.9,
            "pontuacao_tecnica": 90, "regra_versao": VERSAO_REGRAS,
            "status": "aprovado",
        }], "2026-07-21T12:01:00")[0]
        self.banco.registrar_entrega_alerta(
            primeiro, "teste:teste", "entregue"
        )
        self.banco.registrar_entrega_alerta(
            segundo, "teste:teste", "entregue"
        )

        itens = carregar_auditoria(
            self.banco.conexao, regra_versao=VERSAO_REGRAS
        )
        por_id = {item["sinal_id"]: item for item in itens}

        self.assertTrue(por_id[primeiro]["primeira_decisao_independente"])
        self.assertTrue(por_id[primeiro]["elegivel_amostra_independente"])
        self.assertFalse(por_id[segundo]["primeira_decisao_independente"])
        self.assertFalse(por_id[segundo]["elegivel_amostra_independente"])
        texto = formatar_item(por_id[segundo])
        self.assertIn("primeira decisão=não", texto)
        self.assertIn("amostra=excluída", texto)
        self.assertIn("Telegram_sinal=entregue", texto)
        self.assertIn(
            "Telegram_resultado=aguardando_liquidacao", texto
        )


if __name__ == "__main__":
    unittest.main()
