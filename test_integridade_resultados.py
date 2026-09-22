import unittest
from pathlib import Path

from backtest import AvaliadorBacktest
from banco import BancoMonitor
from integridade_resultados import (
    auditar_liquidacao_escanteios_ft,
    auditar_proveniencia_resultados,
)


class IntegridadeResultadosEscanteiosTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_integridade_resultados.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def _liquidar(self, features=None, avaliar=True, status_final="Finalizado"):
        inicial = self.banco.salvar_registro({
            "coletado_em": "2026-09-08T12:00:00",
            "url": "https://packball.com/match/corner-audit/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "80 '",
            "estatisticas": {"Escanteios": "4-3"},
        })
        sinal = self.banco.salvar_candidatos(inicial, [{
            "mercado": "escanteios_ft_asiatico",
            "linha": 7.5, "odd": 1.9,
            "regra_versao": "sinais-v9d-teste",
            "status": "aprovado", "features": features or {},
        }], "2026-09-08T12:00:01")[0]
        final = self.banco.salvar_registro({
            "coletado_em": "2026-09-08T12:10:00",
            "url": "https://packball.com/match/corner-audit/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": status_final,
            "estatisticas": {"Escanteios": "5-3"},
            "qualidade": {
                "fontes": ["packball"],
                "apto_para_liquidacao": True,
            },
        })
        if avaliar:
            AvaliadorBacktest(self.banco).avaliar_snapshot(final)
        return sinal, final

    def test_recompoe_liquidacao_e_rastro_temporal(self):
        self._liquidar({
            "estado_observado_em": "2026-09-08T12:00:00",
            "coletado_em_odds": "2026-09-08T11:59:55",
            "decisao_em": "2026-09-08T12:00:01",
        })

        resultado = auditar_liquidacao_escanteios_ft(
            self.banco.conexao
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["liquidacoes_recompostas"], 1)
        self.assertEqual(resultado["rastro_temporal_auditavel"], 1)

    def test_resultado_adulterado_degrada_proveniencia_geral(self):
        sinal, final = self._liquidar(avaliar=False)
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-09-08T12:10:00', 'red', -1,
                          'registro deliberadamente divergente', ?,
                          'packball')
                """,
                (sinal, final),
            )

        resultado = auditar_proveniencia_resultados(
            self.banco.conexao
        )
        liquidacao = resultado["liquidacao_escanteios_ft"]

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(liquidacao["resultado_divergente"], 1)
        self.assertEqual(liquidacao["retorno_divergente"], 1)
        self.assertEqual(liquidacao["inconsistentes"], 1)

    def test_odd_posterior_a_decisao_e_detectada(self):
        self._liquidar({
            "estado_observado_em": "2026-09-08T12:00:00",
            "coletado_em_odds": "2026-09-08T12:00:03",
            "decisao_em": "2026-09-08T12:00:01",
        })

        resultado = auditar_liquidacao_escanteios_ft(
            self.banco.conexao
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["rastro_temporal_invalido"], 1)

    def test_legado_sem_timestamps_continua_identificado_e_saudavel(self):
        self._liquidar()

        resultado = auditar_liquidacao_escanteios_ft(
            self.banco.conexao
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["legado_sem_rastro_temporal"], 1)

    def test_penaltis_comprovam_fim_do_periodo_regulamentar(self):
        self._liquidar(status_final="PEN")

        resultado = auditar_liquidacao_escanteios_ft(
            self.banco.conexao
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["periodo_nao_encerrado"], 0)


if __name__ == "__main__":
    unittest.main()
