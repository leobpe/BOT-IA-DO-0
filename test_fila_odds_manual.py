import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from banco import BancoMonitor
from fila_odds_manual import listar_solicitacoes_odds_manuais


class FilaOddsManualTest(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(
            dir=Path.cwd(), suffix=".db", delete=False
        ) as arquivo:
            self.caminho = Path(arquivo.name)
        self.caminho.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.agora = datetime(2026, 7, 26, 12, 0)
        self.snapshot_id = self.banco.salvar_registro({
            "coletado_em": self.agora - timedelta(minutes=2),
            "url": "https://packball.com/partida/1",
            "mandante": "Time A",
            "visitante": "Time B",
            "placar": "0-0",
            "status": "61 '",
        })

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def _salvar(self, mercado, bloqueios, nota=80, criado_em=None):
        candidato = {
            "mercado": mercado,
            "linha": None,
            "odd": None,
            "pontuacao_tecnica": nota,
            "probabilidade_calibrada": None,
            "regra_versao": "sinais-v4",
            "motivos": ["pressao_confirmada"],
            "bloqueios": bloqueios,
            "status": "rejeitado",
        }
        return self.banco.salvar_candidatos(
            self.snapshot_id,
            [candidato],
            criado_em or self.agora - timedelta(minutes=2),
        )[0]

    def test_lista_apenas_candidato_bloqueado_exclusivamente_por_odd(self):
        sinal_id = self._salvar(
            "escanteios_2t", ["odd_ao_vivo_indisponivel"]
        )

        resultado = listar_solicitacoes_odds_manuais(
            self.banco.conexao, agora=self.agora
        )

        self.assertEqual(resultado["total"], 1)
        item = resultado["solicitacoes"][0]
        self.assertEqual(item["sinal_id"], sinal_id)
        self.assertEqual(item["periodo"], "2T")
        self.assertEqual(item["estado"], "aguardando_captura_manual")
        self.assertFalse(resultado["envio_automatico"])

    def test_bloqueio_tecnico_adicional_impede_pedido_manual(self):
        self._salvar(
            "escanteios_2t",
            [
                "baseline_intervalo_indisponivel",
                "odd_ao_vivo_indisponivel",
            ],
        )

        resultado = listar_solicitacoes_odds_manuais(
            self.banco.conexao, agora=self.agora
        )

        self.assertEqual(resultado["total"], 0)

    def test_oferta_manual_posterior_resolve_o_pedido(self):
        self._salvar(
            "escanteios_1t", ["odd_ao_vivo_indisponivel"]
        )
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?",
            (self.snapshot_id,),
        ).fetchone()[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado,
                    periodo, mercado, metodo_coleta
                ) VALUES (?, 'bet365_site', ?, 'oferta_valida',
                          '1T', 'escanteios', 'automatizada')
                """,
                (partida_id, self.agora.isoformat()),
            )

        resultado = listar_solicitacoes_odds_manuais(
            self.banco.conexao, agora=self.agora
        )

        self.assertEqual(resultado["total"], 0)

    def test_usa_somente_estado_mais_recente_da_partida(self):
        self._salvar(
            "escanteios_2t",
            ["odd_ao_vivo_indisponivel"],
            criado_em=self.agora - timedelta(minutes=3),
        )
        self._salvar(
            "escanteios_2t",
            [
                "fora_da_janela_escanteios_2t",
                "odd_ao_vivo_indisponivel",
            ],
            criado_em=self.agora - timedelta(minutes=1),
        )

        resultado = listar_solicitacoes_odds_manuais(
            self.banco.conexao, agora=self.agora
        )

        self.assertEqual(resultado["total"], 0)

    def test_expira_sem_reaproveitar_odd_antiga(self):
        self._salvar(
            "escanteios_2t",
            ["odd_ao_vivo_indisponivel"],
            criado_em=self.agora - timedelta(minutes=7),
        )

        resultado = listar_solicitacoes_odds_manuais(
            self.banco.conexao, agora=self.agora
        )

        self.assertEqual(resultado["total"], 0)


if __name__ == "__main__":
    unittest.main()
