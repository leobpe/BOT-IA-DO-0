import unittest
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from replay_historico import executar_replay


class ReplayHistoricoTest(unittest.TestCase):
    def setUp(self):
        self.origem = Path.cwd() / ".teste_replay_origem.db"
        self.destino = Path.cwd() / ".teste_replay_destino.db"
        for base in (self.origem, self.destino):
            for sufixo in ("", "-wal", "-shm"):
                Path(str(base) + sufixo).unlink(missing_ok=True)

    def tearDown(self):
        for base in (self.origem, self.destino):
            for sufixo in ("", "-wal", "-shm"):
                Path(str(base) + sufixo).unlink(missing_ok=True)

    def test_replay_nao_contamina_origem_e_usa_apenas_futuro(self):
        banco = BancoMonitor(self.origem)
        try:
            banco.salvar_registro(
                {
                    "coletado_em": datetime(2026, 7, 20, 12, 0),
                    "url": "https://packball.com/match/1/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "0-0",
                    "status": "60 '",
                    "estatisticas": {
                        "Chutes": "9-4",
                        "Chutes no gol": "5-2",
                        "Índice de pressão": "70-30",
                        "Escanteios": "2-1",
                        "Ataques perigosos": "42-21",
                    },
                    "evolucao": {
                        "5": {
                            "chutes": [4, 2],
                            "escanteios": [1, 1],
                            "resets_detectados": [],
                            "pressao_resumo": {
                                "media": [68, 32],
                                "pico": [82, 41],
                            },
                        },
                        "eventos_recentes": {},
                    },
                    "odds": {
                        "pre_jogo": [],
                        "ao_vivo": [
                            {
                                "mercado": "Total Gols",
                                "dados": "Over Under 0.5 1.80 2.00",
                                "categoria": "gols",
                                "fonte": "packball",
                                "coletado_em": "2026-07-20T12:00:00",
                                "cache": False,
                                "ofertas": [{
                                    "linha": 0.5,
                                    "over": 1.8,
                                    "under": 2.0,
                                }],
                            },
                            {
                                "mercado": "Escanteios - 2 Opções",
                                "dados": "Over Under 3.5 1.90 1.90",
                                "categoria": "escanteios",
                                "tipo_mercado": "total",
                                "fonte": "packball",
                                "coletado_em": "2026-07-20T12:00:00",
                                "cache": False,
                                "ofertas": [{
                                    "linha": 3.5,
                                    "over": 1.9,
                                    "under": 1.9,
                                }],
                            },
                            {
                                "mercado": "Marcar O Próximo Gol",
                                "dados": "1: 1.75 2: 2.20 No: 8.00",
                                "categoria": "gols",
                                "escopo": "proximo",
                                "fonte": "packball",
                                "coletado_em": "2026-07-20T12:00:00",
                                "cache": False,
                                "selecoes": {
                                    "casa": 1.75,
                                    "visitante": 2.2,
                                    "sem_gol": 8.0,
                                },
                            },
                        ],
                    },
                    "qualidade": {
                        "pontuacao": 100,
                        "apto_para_sinal": True,
                        "fontes": ["packball"],
                    },
                }
            )
            banco.salvar_registro(
                {
                    "coletado_em": datetime(2026, 7, 20, 12, 30),
                    "url": "https://packball.com/match/1/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "2-0",
                    "status": "Finalizado",
                    "estatisticas": {"Escanteios": "6-3"},
                    "qualidade": {
                        "pontuacao": 90,
                        "apto_para_sinal": True,
                        "fontes": ["packball"],
                    },
                }
            )
            self.assertEqual(banco.contagens()["sinais"], 0)
        finally:
            banco.fechar()

        resultado = executar_replay(self.origem, self.destino)

        self.assertEqual(resultado["snapshots_processados"], 2)
        self.assertEqual(resultado["decisoes_geradas_brutas"], 5)
        self.assertEqual(resultado["decisoes_aprovadas_brutas"], 3)
        self.assertEqual(resultado["liquidacoes_brutas"], 3)
        self.assertEqual(resultado["pendencias_brutas"], 0)
        self.assertEqual(resultado["partidas_com_liquidacao_bruta"], 1)
        self.assertEqual(resultado["partidas_elegiveis_independentes"], 1)
        self.assertEqual(
            resultado["unidades_independentes_por_mercado"]["gol_ft"], 1
        )
        self.assertEqual(resultado["metricas"]["gol_ft"]["amostra"], 1)
        self.assertEqual(
            resultado["funil_por_mercado"]["gol_ft"]["aprovados"], 1
        )
        self.assertEqual(
            resultado["funil_por_mercado"]["gol_ft"]["odd_elegivel"], 1
        )
        temporal = resultado["analise_temporal"]
        self.assertEqual(
            temporal["uso"],
            "pesquisa_offline_nao_incorpora_calibracao_oficial",
        )
        self.assertEqual(temporal["separacao"], "cronologica_70_30")
        temporal_ft = temporal["mercados"]["gol_ft"]
        self.assertEqual(temporal_ft["elegiveis_independentes"], 1)
        self.assertEqual(temporal_ft["registros_validos"], 1)
        self.assertEqual(temporal_ft["desenvolvimento"], 1)
        self.assertEqual(temporal_ft["validacao_cronologica"], 0)
        self.assertEqual(
            temporal_ft["discriminacao_temporal"]["motivo"],
            "amostra_insuficiente",
        )
        self.assertEqual(
            temporal_ft["corte_sombra"]["motivo"],
            "desenvolvimento_insuficiente",
        )
        origem = BancoMonitor(self.origem)
        try:
            self.assertEqual(origem.contagens()["sinais"], 0)
        finally:
            origem.fechar()

    def test_replay_preserva_idade_original_e_bloqueia_odd_velha(self):
        banco = BancoMonitor(self.origem)
        try:
            banco.salvar_registro(
                {
                    "coletado_em": datetime(2026, 7, 20, 12, 0),
                    "url": "https://packball.com/match/2/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "0-0",
                    "status": "60 '",
                    "estatisticas": {
                        "Chutes no gol": "5-2",
                        "Escanteios": "2-1",
                    },
                    "evolucao": {
                        "5": {
                            "chutes": [4, 2],
                            "escanteios": [1, 1],
                            "resets_detectados": [],
                            "pressao_resumo": {
                                "media": [68, 32],
                                "pico": [82, 41],
                            },
                        },
                        "eventos_recentes": {},
                    },
                    "odds": {
                        "pre_jogo": [],
                        "ao_vivo": [
                            {
                                "mercado": "Total Gols",
                                "dados": "Over Under 0.5 1.80 2.00",
                                "categoria": "gols",
                                "coletado_em": "2026-07-20T11:50:00",
                                "cache": True,
                                "ofertas": [
                                    {
                                        "linha": 0.5,
                                        "over": 1.8,
                                        "under": 2.0,
                                    }
                                ],
                            }
                        ],
                    },
                    "qualidade": {
                        "pontuacao": 100,
                        "apto_para_sinal": True,
                        "fontes": ["packball"],
                    },
                }
            )
        finally:
            banco.fechar()

        resultado = executar_replay(self.origem, self.destino)
        gol_ft = resultado["funil_por_mercado"]["gol_ft"]
        self.assertEqual(resultado["decisoes_aprovadas_brutas"], 0)
        self.assertEqual(gol_ft["gerados"], 1)
        self.assertEqual(gol_ft["rejeitados"], 1)
        self.assertEqual(gol_ft["odd_elegivel"], 1)
        self.assertEqual(gol_ft["bloqueios"]["odds_desatualizadas"], 1)


if __name__ == "__main__":
    unittest.main()
