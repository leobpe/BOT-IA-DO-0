import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from observabilidade import Observabilidade


class ObservabilidadeTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_monitor_eventos.jsonl"
        if self.caminho.exists():
            self.caminho.unlink()
        self.obs = Observabilidade(self.caminho)

    def tearDown(self):
        for caminho in [self.caminho] + [
            Path(f"{self.caminho}.{indice}") for indice in range(1, 6)
        ]:
            if caminho.exists():
                caminho.unlink()

    def _gravar_eventos(self, eventos, caminho=None):
        caminho = caminho or self.caminho
        caminho.write_text(
            "\n".join(
                json.dumps(evento, ensure_ascii=False)
                for evento in eventos
            ) + "\n",
            encoding="utf-8",
        )

    def test_registra_ciclo_com_metricas(self):
        diagnostico_v2 = {
            "avaliacoes": 2,
            "gerados": 1,
            "por_mercado": {"gol_ft": {"gerados": 1}},
        }
        self.obs.ciclo_sucesso(
            12.3456,
            15,
            {"mes": 20, "dia": {"geral": 2, "detalhe": 3}},
            {
                "gols_capacidade_contextual_v2": diagnostico_v2,
                "betsapi": {"ativa": True, "partidas_pareadas": 2},
                "thestatsapi_odds": {"gates_aptos": 1},
                "the_odds_api": {"ativa": True},
                "comparacoes_fontes_odds": [{
                    "partida": "https://packball/match/1",
                    "fontes_utilizaveis": ["betsapi"],
                }],
            },
        )
        registro = json.loads(
            self.caminho.read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(registro["evento"], "ciclo_concluido")
        self.assertEqual(registro["partidas"], 15)
        self.assertEqual(registro["consumo_api_dia"], 5)
        self.assertEqual(
            registro["gols_capacidade_contextual_v2"],
            diagnostico_v2,
        )
        self.assertEqual(registro["betsapi"]["partidas_pareadas"], 2)
        self.assertEqual(registro["thestatsapi_odds"]["gates_aptos"], 1)
        self.assertTrue(registro["the_odds_api"]["ativa"])
        self.assertEqual(
            registro["comparacoes_fontes_odds"][0]["partida"],
            "https://packball/match/1",
        )

    def test_resumo_funil_24h_identifica_gargalo_sem_mudar_sinais(self):
        agora = datetime(2026, 8, 24, 20, 0, 0)
        self._gravar_eventos([
            {
                "em": (agora - timedelta(hours=2)).isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 5,
                "tarefas_agendadas": 4,
                "tarefas_processadas": 4,
                "tarefas_adiadas": 0,
                "tarefas_com_odds": 3,
                "tarefas_sem_odds": 1,
                "tarefas_odds_solicitadas": 4,
                "coletas_odds_sucesso": 3,
                "fallback_odds_necessario": 2,
                "fallback_odds_atendeu": 1,
                "fallback_odds_sem_cobertura": 1,
                "fontes_odds_utilizaveis": {
                    "packball": 2,
                    "betsapi": 2,
                    "thestatsapi": 1,
                },
                "fontes_fallback_odds": {
                    "betsapi": 1,
                    "thestatsapi": 1,
                },
                "betsapi": {
                    "ativa": True,
                    "partidas_pareadas": 2,
                    "partidas_consultadas": 2,
                    "mercados_anexados": 2,
                },
                "thestatsapi_sombra": {
                    "ativa": True,
                    "tentativas_pareamento": 4,
                    "pareadas": 2,
                    "odds_consultadas": 2,
                    "partidas_com_odds": 1,
                    "ofertas_odds_persistidas": 30,
                    "erros": 0,
                },
                "thestatsapi_odds": {
                    "gates_aptos": 1,
                    "mercados_anexados": 1,
                },
                "comparacoes_fontes_odds": [
                    {
                        "partida": "https://packball/match/1",
                        "fontes_utilizaveis": ["packball", "betsapi"],
                        "fontes_fallback": ["betsapi"],
                        "betsapi": {
                            "ativa": True,
                            "pareada": True,
                            "consultada": True,
                            "mercados_anexados": 1,
                        },
                        "thestatsapi": {
                            "ativa": True,
                            "evidencia_disponivel": False,
                            "gate_apto": False,
                            "mercados_anexados": 0,
                        },
                    },
                    {
                        "partida": "https://packball/match/2",
                        "fontes_utilizaveis": [
                            "packball", "betsapi", "thestatsapi",
                        ],
                        "fontes_fallback": ["thestatsapi"],
                        "betsapi": {
                            "ativa": True,
                            "pareada": True,
                            "consultada": True,
                            "mercados_anexados": 1,
                        },
                        "thestatsapi": {
                            "ativa": True,
                            "evidencia_disponivel": True,
                            "gate_apto": True,
                            "mercados_anexados": 1,
                        },
                    },
                ],
                "gols_antecipados": {
                    "avaliacoes": 4,
                    "gerados": 0,
                    "por_braco": {
                        "global": {
                            "motivos": {"qualidade_insuficiente": 3},
                            "detalhes": {
                                "campos_ausentes": {
                                    "Índice de pressão": 2,
                                },
                            },
                        },
                        "gol_ft_antecipado_2t": {
                            "motivos": {
                                "fora_janelas_operacionais": 1,
                            },
                        },
                    },
                },
                "sinais_bloqueados_fontes": 0,
            },
        ])

        resumo = self.obs.resumo_funil_periodo(24, agora=agora)

        self.assertEqual(resumo["estado"], "qualidade_insuficiente")
        self.assertEqual(
            resumo["gargalo_principal"], "qualidade_insuficiente"
        )
        self.assertEqual(resumo["tarefas_processadas"], 4)
        self.assertEqual(resumo["cobertura_odds"], 0.75)
        self.assertEqual(resumo["tarefas_odds_solicitadas"], 4)
        self.assertEqual(resumo["coletas_odds_sucesso"], 3)
        self.assertEqual(resumo["fallback_odds_necessario"], 2)
        self.assertEqual(resumo["fallback_odds_atendeu"], 1)
        self.assertEqual(resumo["fallback_odds_sem_cobertura"], 1)
        self.assertEqual(
            resumo["fontes_odds_utilizaveis"],
            {"packball": 2, "betsapi": 2, "thestatsapi": 1},
        )
        self.assertEqual(
            resumo["fontes_fallback_odds"],
            {"betsapi": 1, "thestatsapi": 1},
        )
        self.assertEqual(
            resumo["campos_ausentes"], {"Índice de pressão": 2}
        )
        self.assertFalse(resumo["aplicacao_sinais"])
        comparacao = resumo["comparacao_fontes_odds"]
        self.assertEqual(comparacao["partidas_unicas_comparadas"], 2)
        self.assertEqual(
            comparacao["fontes"]["betsapi"][
                "partidas_unicas_utilizaveis"
            ],
            2,
        )
        self.assertEqual(
            comparacao["fontes"]["thestatsapi"][
                "partidas_unicas_utilizaveis"
            ],
            1,
        )
        self.assertEqual(
            comparacao["lider_cobertura_provisorio"], "betsapi"
        )
        self.assertFalse(comparacao["amostra_operacional_minima"])

    def test_comparacao_fontes_exige_tempo_e_partidas_unicas(self):
        agora = datetime(2026, 8, 29, 22, 0, 0)

        def comparacoes(prefixo):
            return [
                {
                    "partida": f"https://packball/{prefixo}/{indice}",
                    "fontes_utilizaveis": [
                        "betsapi",
                        *( ["thestatsapi"] if indice % 2 == 0 else [] ),
                    ],
                    "fontes_fallback": [],
                    "betsapi": {"ativa": True, "pareada": True},
                    "thestatsapi": {
                        "ativa": True,
                        "evidencia_disponivel": indice % 2 == 0,
                    },
                }
                for indice in range(15)
            ]

        self._gravar_eventos([
            {
                "em": (agora - timedelta(hours=21)).isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 15,
                "tarefas_processadas": 15,
                "fontes_odds_utilizaveis": {
                    "betsapi": 15, "thestatsapi": 8,
                },
                "comparacoes_fontes_odds": comparacoes("inicio"),
            },
            {
                "em": agora.isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 15,
                "tarefas_processadas": 15,
                "fontes_odds_utilizaveis": {
                    "betsapi": 15, "thestatsapi": 8,
                },
                "comparacoes_fontes_odds": comparacoes("fim"),
            },
        ])

        resumo = self.obs.resumo_funil_periodo(24, agora=agora)
        comparacao = resumo["comparacao_fontes_odds"]

        self.assertEqual(comparacao["partidas_unicas_comparadas"], 30)
        self.assertEqual(
            comparacao["partidas_unicas_com_betsapi_e_thestats_ativas"],
            30,
        )
        self.assertEqual(comparacao["horas_telemetria_direta"], 21.0)
        self.assertTrue(comparacao["amostra_operacional_minima"])
        self.assertFalse(
            comparacao["avaliacao_substituicao_conclusiva"]
        )

    def test_resumo_funil_usa_rotacao_e_detecta_baixa_oferta(self):
        agora = datetime(2026, 8, 24, 20, 0, 0)
        self._gravar_eventos([
            {
                "em": (agora - timedelta(hours=3)).isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 1,
                "tarefas_processadas": 1,
                "tarefas_com_odds": 1,
                "gols_antecipados": {
                    "avaliacoes": 1,
                    "gerados": 0,
                    "por_braco": {},
                },
            },
        ], Path(f"{self.caminho}.1"))
        self._gravar_eventos([
            {
                "em": (agora - timedelta(hours=1)).isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 0,
                "tarefas_processadas": 0,
                "gols_antecipados": {
                    "avaliacoes": 0,
                    "gerados": 0,
                    "por_braco": {},
                },
            },
        ])

        resumo = self.obs.resumo_funil_periodo(24, agora=agora)

        self.assertEqual(resumo["ciclos_concluidos"], 2)
        self.assertEqual(
            resumo["gargalo_principal"],
            "baixa_oferta_jogos_ao_vivo",
        )
        self.assertEqual(resumo["partidas_maximo_por_ciclo"], 1)

    def test_resumo_nao_confunde_distribuicao_segura_com_falha_capacidade(self):
        agora = datetime(2026, 8, 24, 20, 0, 0)
        self._gravar_eventos([
            {
                "em": (agora - timedelta(minutes=10)).isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 6,
                "tarefas_agendadas": 10,
                "tarefas_processadas": 2,
                "tarefas_adiadas": 8,
                "tarefas_com_odds": 2,
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                },
                "gols_antecipados": {
                    "avaliacoes": 2,
                    "gerados": 0,
                    "por_braco": {
                        "global": {
                            "motivos": {"qualidade_insuficiente": 2},
                        },
                    },
                },
            },
        ])

        resumo = self.obs.resumo_funil_periodo(3, agora=agora)

        self.assertEqual(resumo["tarefas_adiadas_distribuidas"], 8)
        self.assertEqual(resumo["tarefas_adiadas_capacidade"], 0)
        self.assertEqual(
            resumo["gargalo_principal"], "qualidade_insuficiente"
        )

    def test_zero_confirmado_e_recuperacao_nao_viram_falha_atual(self):
        agora = datetime(2026, 8, 25, 1, 5, 0)
        eventos = [{
            "em": (agora - timedelta(minutes=5)).isoformat(),
            "evento": "ciclo_falhou",
            "erro": "PackBallListaNaoValidadaError",
        }]
        for minutos in (3, 1):
            eventos.append({
                "em": (agora - timedelta(minutes=minutos)).isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 0,
                "tarefas_agendadas": 0,
                "tarefas_processadas": 0,
                "lista_packball": {
                    "modo_confirmacao": (
                        "status_linhas_zero_confirmado"
                    ),
                },
                "gols_antecipados": {
                    "avaliacoes": 0,
                    "gerados": 0,
                    "por_braco": {},
                },
            })
        self._gravar_eventos(eventos)

        resumo = self.obs.resumo_funil_periodo(3, agora=agora)

        self.assertEqual(
            resumo["estado"], "sem_jogos_ao_vivo_confirmado"
        )
        self.assertIsNone(resumo["gargalo_principal"])
        self.assertEqual(resumo["ciclos_zero_ao_vivo_confirmado"], 2)
        self.assertEqual(resumo["sucessos_consecutivos_finais"], 2)
        self.assertEqual(resumo["falhas_consecutivas_finais"], 0)
        self.assertTrue(resumo["operacao_recuperada"])
        self.assertFalse(resumo["aplicacao_sinais"])

    def test_registra_batimento_de_progresso_do_ciclo(self):
        registro = self.obs.ciclo_progresso(
            "coleta_detalhada", processadas=2, agendadas=5
        )

        self.assertEqual(registro["evento"], "ciclo_em_andamento")
        self.assertEqual(registro["etapa"], "coleta_detalhada")
        self.assertEqual(registro["processadas"], 2)
        self.assertEqual(registro["agendadas"], 5)

    def test_resumo_agrega_cobertura_da_cotacao_pos_alerta(self):
        agora = datetime(2026, 9, 9, 12, 0, 0)
        self._gravar_eventos([{
            "em": (agora - timedelta(minutes=1)).isoformat(),
            "evento": "ciclo_concluido",
            "partidas": 2,
            "tarefas_agendadas": 2,
            "tarefas_processadas": 2,
            "perfil_agendamento": {
                "acompanhamentos_preco_agendados": 2,
                "acompanhamentos_preco_processados": 2,
                "acompanhamentos_preco_com_odds": 1,
                "acompanhamentos_preco_sem_odds": 1,
                "acompanhamentos_preco_snapshots": 2,
            },
        }])

        resumo = self.obs.resumo_funil_periodo(3, agora=agora)
        acompanhamento = resumo["acompanhamento_preco_pos_alerta"]

        self.assertEqual(2, acompanhamento["agendados"])
        self.assertEqual(2, acompanhamento["processados"])
        self.assertEqual(1, acompanhamento["com_odds"])
        self.assertEqual(1, acompanhamento["sem_odds"])
        self.assertEqual(2, acompanhamento["snapshots_persistidos"])
        self.assertEqual(1.0, acompanhamento["taxa_processamento"])
        self.assertEqual(0.5, acompanhamento["taxa_coleta_odds"])
        self.assertFalse(acompanhamento["altera_sinais"])

    def test_historico_api_na_pausa_nao_mascara_falha_como_progresso(self):
        registro = self.obs.historico_api_pausa_packball({
            "estado": "persistido",
            "inseridos": 3,
            "aplicacao_sinais": False,
            "operacao_bloqueada": True,
        })

        self.assertEqual(
            registro["evento"], "historico_api_sombra_pausa_packball"
        )
        self.assertNotEqual(registro["evento"], "ciclo_em_andamento")
        self.assertEqual(registro["inseridos"], 3)
        self.assertFalse(registro["aplicacao_sinais"])
        self.assertTrue(registro["operacao_bloqueada"])

    def test_registra_orcamento_diario_da_api(self):
        self.obs.ciclo_sucesso(
            1,
            2,
            {
                "dia": {"geral": 3, "detalhe": 4},
                "total_dia": 7,
                "limite_diario_seguro": 7000,
                "restante_seguro_dia": 6993,
            },
        )
        registro = json.loads(
            self.caminho.read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(registro["consumo_api_dia"], 7)
        self.assertEqual(registro["limite_api_dia"], 7000)
        self.assertEqual(registro["restante_api_dia"], 6993)

    def test_registra_saude_e_bloqueios_das_fontes(self):
        registro = self.obs.ciclo_sucesso(
            1,
            2,
            {
                "dia": {"geral": 1},
                "saude_api": {
                    "saudavel": False,
                    "motivo": "falha_api_no_ciclo",
                },
            },
            {
                "sinais_bloqueados_fontes": 2,
                "motivos_bloqueio_fontes": {
                    "falha_api_no_ciclo": 2
                },
            },
        )

        self.assertFalse(registro["saude_api"]["saudavel"])
        self.assertEqual(registro["sinais_bloqueados_fontes"], 2)
        self.assertEqual(
            registro["motivos_bloqueio_fontes"],
            {"falha_api_no_ciclo": 2},
        )

    def test_registra_eficiencia_do_cache_api_por_ciclo(self):
        consumo = {
            "mes": 2,
            "dia": {"geral": 1},
            "cache_persistente_hits": 3,
            "cache_persistente_gravacoes": 2,
            "cache_persistente_descartes": 1,
            "cache_persistente_falhas": 1,
        }
        primeiro = self.obs.ciclo_sucesso(1, 2, consumo)
        consumo.update({
            "cache_persistente_hits": 5,
            "cache_persistente_gravacoes": 3,
            "cache_persistente_descartes": 1,
            "cache_persistente_falhas": 2,
        })
        segundo = self.obs.ciclo_sucesso(1, 2, consumo)

        self.assertEqual(primeiro["cache_api_hits_ciclo"], 3)
        self.assertEqual(primeiro["cache_api_gravacoes_ciclo"], 2)
        self.assertEqual(primeiro["cache_api_descartes_ciclo"], 1)
        self.assertEqual(primeiro["cache_api_falhas_ciclo"], 1)
        self.assertEqual(segundo["cache_api_hits_ciclo"], 2)
        self.assertEqual(segundo["cache_api_gravacoes_ciclo"], 1)
        self.assertEqual(segundo["cache_api_descartes_ciclo"], 0)
        self.assertEqual(segundo["cache_api_falhas_ciclo"], 1)

    def test_resumo_inclui_media_p95_e_maximo(self):
        for duracao in (10, 20, 30, 40):
            self.obs.ciclo_sucesso(
                duracao, 1, {"mes": 0, "dia": {}}
            )

        resumo = self.obs.resumo()

        self.assertEqual(resumo["latencia_media_segundos"], 25.0)
        self.assertEqual(resumo["latencia_p95_segundos"], 40.0)
        self.assertEqual(resumo["latencia_maxima_segundos"], 40.0)

    def test_registra_fila_processada_e_adiada_no_ciclo(self):
        self.obs.ciclo_sucesso(
            190,
            30,
            {"mes": 0, "dia": {}},
            {
                "agendadas": 25,
                "processadas": 18,
                "adiadas": 7,
                "duracao_detalhada_segundos": 181.2,
                "orcamento_segundos": 180,
                "interrompido_por_reserva": True,
                "reserva_admissao_segundos": 46.2,
                "duracoes_historicas_admissao": 30,
                "duracoes_tarefas_segundos": [12.5, 14.25],
                "duracoes_etapas_detalhadas": {
                    "versao": "duracoes-etapas-detalhe-v1",
                    "altera_sinal": False,
                    "etapas": {
                        "estatisticas_packball_e_fusao": {
                            "tarefas": 2,
                            "total_segundos": 18.5,
                            "media_segundos": 9.25,
                            "p95_segundos": 10.0,
                        },
                    },
                },
                "prioridades_asiaticas_processadas": 3,
                "odds_asiaticas_api_anexadas": 2,
                "prioridades_asiaticas_sem_anexo": 1,
                "alvos_um_escanteio_processados": 2,
                "alvos_um_escanteio_anexados": 2,
                "associacoes_api": {
                    "associado": 10,
                    "nomes_incompativeis": 8,
                },
                "perfil_agendamento": {
                    "foco_agendadas": 6,
                    "exploracao_agendadas": 19,
                    "foco_processadas": 6,
                    "exploracao_processadas": 12,
                    "revisitas_processadas": 14,
                    "novas_processadas": 4,
                },
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                    "intervalo_efetivo_segundos": 21.929,
                    "maximo_por_janela": 28,
                    "janela_segundos": 600,
                },
                "idade_fila": {
                    "agendadas": {
                        "tarefas": 25,
                        "com_historico": 20,
                        "sem_historico": 5,
                        "maxima_segundos": 1500.0,
                        "acima_20_minutos": 2,
                    },
                    "processadas": {
                        "tarefas": 18,
                        "com_historico": 14,
                        "sem_historico": 4,
                        "maxima_segundos": 900.0,
                        "acima_20_minutos": 0,
                    },
                    "adiadas": {
                        "tarefas": 7,
                        "com_historico": 6,
                        "sem_historico": 1,
                        "maxima_segundos": 1500.0,
                        "acima_20_minutos": 2,
                    },
                },
                "cobertura_temporal": {
                    "partidas_com_historico": 12,
                    "taxa_com_historico": 0.6667,
                    "janelas_disponiveis": {
                        "5": 12, "10": 9, "15": 7,
                    },
                    "taxas_por_janela": {
                        "5": 0.6667, "10": 0.5, "15": 0.3889,
                    },
                },
                "gols_antecipados": {
                    "avaliacoes": 2,
                    "gerados": 1,
                    "por_braco": {
                        "gol_ft_antecipado_pre_live": {
                            "avaliacoes": 2,
                            "gerados": 1,
                            "motivos": {"candidato_base_ausente": 1},
                        },
                    },
                },
            },
        )
        registro = json.loads(
            self.caminho.read_text(encoding="utf-8").splitlines()[0]
        )

        self.assertEqual(registro["tarefas_agendadas"], 25)
        self.assertEqual(registro["tarefas_processadas"], 18)
        self.assertEqual(registro["tarefas_adiadas"], 7)
        self.assertEqual(
            registro["associacoes_api"]["nomes_incompativeis"], 8
        )
        self.assertEqual(
            registro["cobertura_temporal"]["janelas_disponiveis"],
            {"5": 12, "10": 9, "15": 7},
        )
        self.assertEqual(
            registro["gols_antecipados"]["gerados"], 1
        )
        self.assertEqual(
            registro["perfil_agendamento"]["foco_processadas"], 6
        )
        self.assertEqual(
            registro["perfil_agendamento"]["revisitas_processadas"], 14
        )
        self.assertTrue(
            registro["ritmo_packball"][
                "distribuicao_janela_ativa"
            ]
        )
        self.assertEqual(
            registro["idade_fila"]["adiadas"]["maxima_segundos"],
            1500.0,
        )
        self.assertEqual(
            registro["idade_fila"]["adiadas"]["acima_20_minutos"],
            2,
        )
        self.assertEqual(registro["duracao_detalhada_segundos"], 181.2)
        self.assertTrue(registro["interrompido_por_reserva"])
        self.assertEqual(registro["reserva_admissao_segundos"], 46.2)
        self.assertEqual(registro["duracoes_historicas_admissao"], 30)
        self.assertEqual(
            registro["duracoes_tarefas_segundos"], [12.5, 14.25]
        )
        self.assertEqual(
            registro["duracoes_etapas_detalhadas"]["etapas"]
            ["estatisticas_packball_e_fusao"]["media_segundos"],
            9.25,
        )
        self.assertFalse(
            registro["duracoes_etapas_detalhadas"]["altera_sinal"]
        )
        self.assertEqual(registro["prioridades_asiaticas_processadas"], 3)
        self.assertEqual(registro["odds_asiaticas_api_anexadas"], 2)
        self.assertEqual(registro["prioridades_asiaticas_sem_anexo"], 1)
        self.assertEqual(registro["alvos_um_escanteio_processados"], 2)
        self.assertEqual(registro["alvos_um_escanteio_anexados"], 2)

    def test_restaura_duracoes_brutas_ignorando_valores_invalidos(self):
        self.obs.ciclo_sucesso(
            20,
            2,
            {"mes": 0, "dia": {}},
            {
                "duracoes_tarefas_segundos": [
                    11.0, "12.5", None, -1, float("inf")
                ],
                "duracao_tarefa_p95_segundos": 99,
            },
        )
        self.obs.ciclo_sucesso(
            30,
            2,
            {"mes": 0, "dia": {}},
            {"duracoes_tarefas_segundos": [13.0, 14.0]},
        )

        self.assertEqual(
            self.obs.duracoes_tarefas_recentes(3),
            [12.5, 13.0, 14.0],
        )

    def test_restaura_p95_legado_quando_nao_ha_duracoes_brutas(self):
        self.obs.ciclo_sucesso(
            20,
            2,
            {"mes": 0, "dia": {}},
            {"duracao_tarefa_p95_segundos": 41.0},
        )
        self.obs.ciclo_sucesso(
            30,
            2,
            {"mes": 0, "dia": {}},
            {"duracao_tarefa_p95_segundos": 43.0},
        )

        self.assertEqual(
            self.obs.duracoes_tarefas_recentes(30),
            [41.0, 43.0],
        )

    def test_tres_falhas_solicitam_recuperacao(self):
        for _ in range(3):
            self.obs.ciclo_erro(1.0, TimeoutError("tempo excedido"))
        self.assertTrue(self.obs.deve_recuperar_navegador())
        self.obs.recuperacao("três falhas consecutivas")
        self.assertFalse(self.obs.deve_recuperar_navegador())

    def test_circuit_breaker_packball_zera_falhas_e_fica_auditavel(self):
        for _ in range(3):
            self.obs.ciclo_erro(1.0, RuntimeError("lista vazia"))

        registro = self.obs.circuito_packball_ativado(
            "lista_packball_nao_validada",
            "2026-08-01T14:00:00",
        )

        self.assertEqual(registro["evento"], "circuit_breaker_packball")
        self.assertEqual(registro["falhas_consecutivas"], 3)
        self.assertEqual(self.obs.falhas_consecutivas, 0)

    def test_sessao_renovada_registra_apenas_validade(self):
        registro = self.obs.sessao_contexto(
            atualizada=True,
            expira_em="2026-08-11T14:00:00",
        )

        self.assertEqual(registro["evento"], "sessao_packball_persistida")
        self.assertTrue(registro["atualizada"])
        self.assertEqual(registro["expira_em"], "2026-08-11T14:00:00")
        self.assertNotIn("token", str(registro).lower())

    def test_falha_fatal_do_processo_remove_segredos(self):
        registro = self.obs.processo_falhou(
            "monitor",
            PermissionError(
                "Playwright negado token=segredo api_key=abc123 "
                "https://api.telegram.org/bot123456:ABC-def/sendMessage"
            ),
        )

        self.assertEqual(registro["evento"], "processo_falhou")
        self.assertEqual(registro["nivel"], "erro")
        self.assertEqual(registro["componente"], "monitor")
        self.assertEqual(registro["erro"], "PermissionError")
        self.assertNotIn("segredo", registro["mensagem"])
        self.assertNotIn("abc123", registro["mensagem"])
        self.assertNotIn("123456:ABC-def", registro["mensagem"])
        self.assertIn("<redigido>", registro["mensagem"])
        resumo = self.obs.resumo()
        self.assertEqual(resumo["processos_falhas_fatais"], 1)
        self.assertEqual(
            resumo["processo_ultima_falha_fatal"]["erro"],
            "PermissionError",
        )

    def test_pausa_preventiva_nao_conta_como_falha(self):
        self.obs.ciclo_erro(1.0, TimeoutError("falha anterior"))
        registro = self.obs.ciclo_pausado_packball(
            0.1, RuntimeError("teto local")
        )
        self.assertEqual(registro["evento"], "ciclo_pausado_packball")
        self.assertEqual(registro["nivel"], "info")
        self.assertEqual(self.obs.falhas_consecutivas, 0)
        self.assertFalse(self.obs.deve_recuperar_navegador())

    def test_recuperacao_do_watchdog_fica_auditavel(self):
        registro = self.obs.supervisao_watchdog(
            reiniciado=True, pid=321
        )

        self.assertEqual(registro["nivel"], "aviso")
        self.assertEqual(registro["evento"], "watchdog_reiniciado_pelo_monitor")
        self.assertEqual(registro["pid"], 321)

    def test_falha_ao_recuperar_watchdog_fica_auditavel(self):
        registro = self.obs.supervisao_watchdog(
            erro=RuntimeError("sem recurso")
        )

        self.assertEqual(registro["nivel"], "erro")
        self.assertEqual(registro["evento"], "watchdog_supervisao_falhou")
        self.assertEqual(registro["erro"], "RuntimeError")

        resumo = self.obs.resumo()
        self.assertEqual(resumo["watchdog_reinicios"], 0)
        self.assertEqual(resumo["watchdog_falhas_supervisao"], 1)
        self.assertEqual(
            resumo["watchdog_ultima_supervisao"]["evento"],
            "watchdog_supervisao_falhou",
        )

    def test_modo_manutencao_fica_auditavel(self):
        registro = self.obs.modo_manutencao(
            "solicitado", {"motivo": "teste"}
        )

        self.assertEqual(registro["evento"], "modo_manutencao_solicitado")
        self.assertEqual(registro["detalhes"]["motivo"], "teste")

    def test_sucesso_zera_falhas_consecutivas(self):
        self.obs.ciclo_erro(1.0, RuntimeError("falha"))
        self.obs.ciclo_sucesso(2.0, 1, {"mes": 0, "dia": {}})
        self.assertEqual(self.obs.falhas_consecutivas, 0)

    def test_registra_resumo_de_finalizacao(self):
        registro = self.obs.finalizacao_resultados(
            {"consultadas": 2, "resolvidos": 1},
            {"consultadas": 1, "resolvidos": 0, "erros": 1},
        )
        self.assertEqual(registro["evento"], "finalizacao_resultados")

    def test_resposta_ausente_da_api_fica_como_aviso(self):
        registro = self.obs.finalizacao_resultados(
            {"respostas_ausentes": 1, "respostas_invalidas": 2},
            {"erros": 0},
        )

        self.assertEqual(registro["nivel"], "aviso")
        self.assertEqual(registro["api"]["respostas_ausentes"], 1)
        self.assertEqual(registro["nivel"], "aviso")

    def test_finalizacao_sem_dado_fica_auditavel(self):
        registro = self.obs.finalizacao_resultados(
            {"consultadas": 0},
            {"consultadas": 0, "erros": 0},
            {"candidatos": 1, "encerrados_sem_dado": 1},
        )
        self.assertEqual(registro["nivel"], "aviso")
        self.assertEqual(registro["sem_dado"]["encerrados_sem_dado"], 1)

    def test_registra_falha_parcial_e_fallback(self):
        registro = self.obs.fonte_falhou(
            "odds_packball",
            "A x B",
            TimeoutError("tempo excedido"),
            "ultimas_odds_persistidas",
        )

        self.assertEqual(registro["evento"], "fonte_falhou")
        self.assertEqual(registro["nivel"], "aviso")
        self.assertEqual(registro["fonte"], "odds_packball")
        self.assertEqual(registro["erro"], "TimeoutError")
        self.assertEqual(registro["fallback"], "ultimas_odds_persistidas")

    def test_registra_falha_de_backup_sem_ocultar_erro(self):
        registro = self.obs.backup_diario(erro=OSError("sem espaço"))

        self.assertEqual(registro["evento"], "backup_diario_falhou")
        self.assertEqual(registro["nivel"], "erro")
        self.assertEqual(registro["erro"], "OSError")

    def test_registra_compactacao_adiada_com_backup_utilizavel(self):
        registro = self.obs.compactacao_backup_operacional(
            "periodico",
            {
                "saudavel": False,
                "fallback_original": True,
                "original_valido": True,
                "motivo": "PermissionError",
            },
        )

        self.assertEqual(
            registro["evento"],
            "compactacao_backup_adiada_original_preservado",
        )
        self.assertEqual(registro["nivel"], "aviso")
        self.assertTrue(registro["backup_utilizavel"])

    def test_registra_manutencao_e_checkpoint(self):
        registro = self.obs.manutencao_diaria(
            {"snapshots": 2, "sinais_descartados": 1},
            {"ocupado": 0, "paginas": 10, "checkpoint": 10},
        )

        self.assertEqual(registro["evento"], "manutencao_diaria_concluida")
        self.assertEqual(registro["resultado"]["snapshots"], 2)
        self.assertEqual(registro["checkpoint"]["ocupado"], 0)


if __name__ == "__main__":
    unittest.main()
