import io
import sqlite3
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from banco import BancoMonitor, registrar_historico_drift_simulacoes
from calibracao import hash_modelo_calibracao
from status_bot import (
    carregar_historico_drift_status,
    configurar_saida_terminal,
    descrever_autostart,
    descrever_amostragem_referencia_odds,
    descrever_escanteios_ft_asiatico,
    descrever_integridade_banco_ativo,
    descrever_janelas_temporais_ritmo,
    descrever_cobertura_temporal_priorizada,
    descrever_comparacao_gol_ft_v2_v3,
    descrever_cota_provedor,
    descrever_clv_live,
    descrever_challenger_v2_ft,
    descrever_desajuste_odds,
    descrever_funil_marginal_proximo_gol,
    descrever_quase_candidatos_gol_ft,
    descrever_quase_candidatos_proximo_gol,
    descrever_proximo_gol_balanceado,
    descrever_historico_api_live,
    descrever_pendencias_prontidao,
    descrever_portfolio_edge,
    descrever_prioridade_ligas_gols,
    descrever_quarentena_fallback_ht,
    descrever_recuperacao_banco,
    descrever_filtro_regra_ativa,
    descrever_simulacoes_ativas_hoje,
    descrever_uso_fontes_odds,
    enriquecer_validacao_com_watchdog,
    imprimir_calibracoes_arquivadas,
    imprimir_conclusao_experimento_filtro,
    imprimir_cortes_sombra,
    imprimir_diversidade_calibracao,
    imprimir_hipoteses_sombra,
    ler_recuperacao_banco,
    resumir_calibracoes_arquivadas,
    resumir_amostragem_referencia_odds,
    resumir_filtros_regras_ativas,
    resumir_simulacoes_ativas_hoje,
    resumir_uso_fontes_odds,
)


class StatusBotTest(unittest.TestCase):
    def test_status_separa_referencia_sombra_do_uso_operacional(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        self.addCleanup(conexao.close)
        conexao.executescript(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY, partida_id INTEGER, coletado_em TEXT
            );
            CREATE TABLE odds (
                id INTEGER PRIMARY KEY, snapshot_id INTEGER, tipo TEXT
            );
            CREATE TABLE comparacoes_odds_fontes (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                observado_em TEXT, fonte_a TEXT, fonte_b TEXT
            );
            CREATE TABLE observacoes_fontes_odds (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                fonte TEXT, consultado_em TEXT, estado TEXT,
                metodo_coleta TEXT, metadados_json TEXT
            );
            INSERT INTO snapshots VALUES (
                1, 7, datetime('now', 'localtime')
            );
            INSERT INTO odds VALUES (1, 1, 'referencia_sombra');
            INSERT INTO comparacoes_odds_fontes VALUES (
                1, 7, datetime('now', 'localtime'),
                'betsapi', 'the_odds_api'
            );
            INSERT INTO observacoes_fontes_odds VALUES (
                1, 7, 'the_odds_api', datetime('now', 'localtime'),
                'oferta_disponivel', 'amostragem_referencia_sombra',
                '{"tipo_amostra":"nova_partida","posicao_fila":1,"tarefas_ciclo":4}'
            );
            INSERT INTO observacoes_fontes_odds VALUES (
                2, 8, 'the_odds_api', datetime('now', 'localtime'),
                'evento_nao_encontrado', 'amostragem_referencia_sombra',
                '{"tipo_amostra":"confirmacao_temporal","posicao_fila":3,"tarefas_ciclo":4}'
            );
            INSERT INTO observacoes_fontes_odds VALUES (
                3, 9, 'the_odds_api', datetime('now', 'localtime'),
                'competicao_nao_coberta_pre_reserva',
                'amostragem_referencia_preselecao',
                '{"preselecao_executada":true,"competicao_coberta":false,"reserva_consumida":false}'
            );
            INSERT INTO observacoes_fontes_odds VALUES (
                4, 10, 'the_odds_api', datetime('now', 'localtime'),
                'evento_nao_encontrado_pre_reserva',
                'amostragem_referencia_preselecao',
                '{"preselecao_executada":true,"competicao_coberta":true,"preselecao_evento_executada":true,"evento_pareado_pre_reserva":false,"reserva_consumida":false}'
            );
            INSERT INTO observacoes_fontes_odds VALUES (
                5, 11, 'the_odds_api', datetime('now', 'localtime'),
                'limite_amostragem_diario',
                'amostragem_referencia_preselecao',
                '{"preselecao_executada":true,"competicao_coberta":true,"preselecao_evento_executada":true,"evento_pareado_pre_reserva":true,"reserva_consumida":false}'
            );
            """
        )
        resumo = resumir_amostragem_referencia_odds(
            conexao,
            {
                "amostragem_referencia": {
                    "dia": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "reservas": 2,
                    "contagens": {
                        "jogo-1|gol_ft": 2,
                        "jogo-2|gol_ft": 1,
                    },
                },
                "provedor": {"restante": 19750},
                "circuito": {
                    "falhas_consecutivas": 3,
                    "bloqueado_ate": 9999999999,
                    "motivo": "URLError",
                },
                "controle_estado": {
                    "saudavel": True,
                    "origem": "backup",
                    "recuperado": True,
                    "backup": True,
                },
            },
            limite_diario=30,
        )
        texto = descrever_amostragem_referencia_odds(resumo)

        self.assertEqual(1, resumo["mercados_sombra"])
        self.assertEqual(1, resumo["jogos_pareados"])
        self.assertEqual(2, resumo["tentativas_auditadas"])
        self.assertEqual(2, resumo["jogos_tentados"])
        self.assertEqual(1, resumo["novas_partidas_auditadas"])
        self.assertEqual(1, resumo["confirmacoes_auditadas"])
        self.assertEqual(3, resumo["preselecoes"])
        self.assertEqual(2, resumo["preselecoes_cobertas"])
        self.assertEqual(1, resumo["preselecoes_descartadas"])
        self.assertEqual(2, resumo["preselecoes_evento"])
        self.assertEqual(1, resumo["eventos_pareados_pre_reserva"])
        self.assertEqual(1, resumo["eventos_descartados_pre_reserva"])
        self.assertEqual(2, resumo["reservas_economizadas"])
        self.assertEqual(1, resumo["reservas_economizadas_evento"])
        self.assertEqual(0.5, resumo["posicao_relativa_media"])
        self.assertEqual("aguardando_30_amostras", resumo["estado_vies_ordem"])
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertIn("reservas hoje=2/30", texto)
        self.assertIn(
            "jogos distintos/maior repetição hoje=2/2 (máx=2)",
            texto,
        )
        self.assertIn("confirmações máximas/ciclo=1", texto)
        self.assertIn("tentativas auditadas/jogos=2/2", texto)
        self.assertIn("posição relativa média=50.0%", texto)
        self.assertIn(
            "pré-seleções cobertas/descartadas/reservas economizadas=2/1/2",
            texto,
        )
        self.assertIn(
            "eventos pareados/descartados/economia específica=1/1/1",
            texto,
        )
        self.assertTrue(resumo["circuito_aberto"])
        self.assertIn("circuito=aberto (falhas=3)", texto)
        self.assertIn("estado persistente=backup/saudavel", texto)
        self.assertIn("altera HT/FT=não", texto)

    def test_descreve_quase_candidatos_ft_sem_sugerir_promocao(self):
        texto = descrever_quase_candidatos_gol_ft({
            "saudavel": True,
            "estado": "coletando",
            "bracos": {
                "minuto_61_75": {
                    "candidatos": 2, "tamanho_coorte": 60,
                    "greens": 1, "reds": 0, "pendentes": 1,
                    "roi": 0.5, "decisao": "aguardando_amostra_futura",
                },
                "historico_8_11": {
                    "candidatos": 1, "tamanho_coorte": 60,
                    "greens": 0, "reds": 1, "pendentes": 0,
                    "roi": -1, "decisao": "aguardando_amostra_futura",
                },
            },
        })

        self.assertIn("minuto 61–75=2/60", texto)
        self.assertIn("histórico 8–11=1/60", texto)
        self.assertIn("um filtro alterado por braço=sim", texto)
        self.assertIn("Telegram=não", texto)
        self.assertIn("promoção automática=não", texto)

    def test_descreve_quase_candidatos_sem_inventar_vantagem(self):
        texto = descrever_quase_candidatos_proximo_gol({
            "saudavel": True,
            "estado": "coletando",
            "bracos": {
                "odd_165_199": {
                    "candidatos": 4,
                    "tamanho_coorte": 60,
                    "greens": 1,
                    "reds": 1,
                    "pendentes": 2,
                    "roi": 0.05,
                    "decisao": "aguardando_amostra_futura",
                },
                "atividade_com_chute": {
                    "candidatos": 3,
                    "tamanho_coorte": 60,
                    "greens": 0,
                    "reds": 1,
                    "pendentes": 2,
                    "roi": -1.0,
                    "decisao": "aguardando_amostra_futura",
                },
            },
        })

        self.assertIn("odd 1,65–1,99=4/60", texto)
        self.assertIn("atividade+chute=3/60", texto)
        self.assertIn("seleção antes do resultado=sim", texto)
        self.assertIn("Telegram=não", texto)
        self.assertIn("promoção automática=não", texto)

    def test_desajuste_expoe_execucao_integridade_e_corroboracao(self):
        texto = descrever_desajuste_odds({
            "estado": "em_formacao",
            "estado_execucao": "concluida",
            "cronologia_execucao": {"valida": True, "problemas": []},
            "efeitos_operacionais": {"valida": True},
            "exposicao_coleta_prospectiva": {
                "estado": "exposicao_parcial_com_coortes_em_pausa",
                "coortes": 4,
                "coortes_com_exposicao": 1,
                "coortes_sem_exposicao_por_manutencao": 3,
                "por_coorte": {
                    "principal": {
                        "ciclos_concluidos": 5,
                        "partidas_somadas": 12,
                        "tarefas_processadas": 7,
                    },
                    "desajuste_executavel": {},
                    "convergencia_gols": {},
                    "convergencia_escanteios": {},
                },
            },
            "saudavel": True,
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "integridade_comparacoes_odds": {
                "comparacoes_validas": 4045,
                "comparacoes_auditadas": 4045,
                "comparacoes_invalidas": 0,
                "auditoria_truncada": False,
                "fingerprint_evidencias": "a" * 64,
            },
            "corroboracao_entrada_rapida": {
                "fotografias_independentes": 3,
                "jogos_distintos": 2,
                "faltam_fotografias": 27,
                "faltam_jogos": 13,
            },
            "recorte_observacional_executavel": {
                "candidatos_independentes": 8,
                "com_seguimento_mesma_bookmaker_5m": 6,
                "persistentes_mesma_bookmaker_5m": 5,
                "vantagem_executavel_comprovada": False,
                "fontes_observadas": {
                    "api_football": 4,
                    "betsapi": 5,
                },
                "origens_observacoes": {
                    "observacoes_fontes_odds": 5,
                    "snapshots_odds": 4,
                },
                "contraparte_exige_fonte_independente": True,
            },
            "recorte_edge_sem_vig_multifonte": {
                "fotografias_completas": 7,
                "coorte": 3,
                "faltam_coorte": 57,
                "decisao": "formando_coorte_prospectiva",
                "liquidacao_resultados": {
                    "candidatos_liquidaveis": 3,
                    "resultados": 2,
                    "pendentes": 1,
                    "por_mercado": {
                        "escanteios:FT": {
                            "coorte": 0,
                            "total": {"resultados": 0},
                            "decisao": "formando_coorte",
                        },
                        "gols:FT": {
                            "coorte": 3,
                            "total": {"resultados": 2},
                            "decisao": "formando_coorte",
                        },
                    },
                },
                "vantagem_executavel_comprovada": False,
            },
            "recorte_referencia_pos_envio": {
                "auditorias_pos_envio": 2,
                "fotografias_independentes": 1,
                "por_mercado": {
                    "gol_ft": {
                        "coorte_edge": 1,
                        "coorte_controle": 0,
                        "total": {"resultados": 0},
                        "decisao": "formando_coorte_edge_e_controle",
                    },
                    "gol_ht": {
                        "coorte_edge": 0,
                        "coorte_controle": 0,
                        "total": {"resultados": 0},
                        "decisao": (
                            "aguardando_primeira_referencia_pos_envio"
                        ),
                    },
                },
                "vantagem_estatistica_para_revisao": False,
                "saudavel": True,
            },
            "contrato_fontes_observacionais": {"saudavel": True},
        })

        self.assertIn("execução=concluida", texto)
        self.assertIn("cronologia=ok", texto)
        self.assertIn("efeitos=bloqueados", texto)
        self.assertIn(
            "exposição=exposicao_parcial_com_coortes_em_pausa; "
            "principal=5 ciclos/12 partidas/7 tarefas; "
            "coortes=4/observadas=1/pausadas=3",
            texto,
        )
        self.assertIn("saudável=sim", texto)
        self.assertIn("4045/4045/0", texto)
        self.assertIn("fingerprint=aaaaaaaaaaaa", texto)
        self.assertIn("corroboração fotos/jogos/faltam=3/2/27+13", texto)
        self.assertIn(
            "fontes/origens=api_football:4,betsapi:5/"
            "observacoes_fontes_odds:5,snapshots_odds:4",
            texto,
        )
        self.assertIn("fonte independente=sim", texto)
        self.assertIn("contrato fontes=ok", texto)
        self.assertIn("edge sem vig fotos/coorte/faltam=7/3/57", texto)
        self.assertIn(
            "decisão sem vig=formando_coorte_prospectiva", texto
        )
        self.assertIn(
            "liquidação sem vig candidatos/resultados/pendentes=3/2/1",
            texto,
        )
        self.assertIn("gols:FT:coorte=3/resultados=2", texto)
        self.assertIn("escanteios:FT:coorte=0/resultados=0", texto)
        self.assertIn("vantagem sem vig comprovada=não", texto)
        self.assertIn("referência pós-envio auditorias/fotos=2/1", texto)
        self.assertIn("gol_ft:edge=1/controle=0/resultados=0", texto)
        self.assertIn("integridade pós-envio=ok", texto)
        self.assertIn("bloqueia inferência=não", texto)
        self.assertIn("aplicação automática=não", texto)

    def test_desajuste_em_falha_nao_parece_vantagem(self):
        texto = descrever_desajuste_odds({
            "estado": "falha_avaliacao",
            "estado_execucao": "falha",
            "cronologia_execucao": {
                "valida": False,
                "problemas": ["atualizado_em_futuro"],
            },
            "efeitos_operacionais": {
                "valida": False,
                "campos_invalidos": ["telegram"],
            },
            "saudavel": False,
            "motivo": "avaliacao_desajuste_odds_falhou",
            "recorte_observacional_executavel": {},
        })

        self.assertIn("execução=falha", texto)
        self.assertIn(
            "cronologia=inválida:atualizado_em_futuro", texto
        )
        self.assertIn("efeitos=inválidos:telegram", texto)
        self.assertIn("saudável=não", texto)
        self.assertIn("vantagem executável=não", texto)
        self.assertIn("bloqueia inferência=sim", texto)

    def test_quarentena_ht_expoe_coorte_causal_sem_reativar(self):
        texto = descrever_quarentena_fallback_ht({
            "estado": "em_formacao",
            "estado_execucao": "concluida",
            "cronologia_execucao": {"valida": True, "problemas": []},
            "efeitos_operacionais": {"valida": True},
            "saudavel": True,
            "versao": "quarentena-v2",
            "metodologia_compativel": True,
            "unidades_independentes": 34,
            "decisoes_brutas_elegiveis": 80,
            "resultados_quarentena": 12,
            "resultados_holdout_quarentena": 0,
            "resultados_controle": 22,
            "resultados_holdout_controle": 0,
            "vantagem_linhas_altas_comprovada": False,
            "prejuizo_linhas_altas_comprovado": False,
            "politica_operacional_ativa": True,
        })

        self.assertIn("metodologia compatível=sim", texto)
        self.assertIn("execução=concluida", texto)
        self.assertIn("cronologia=ok", texto)
        self.assertIn("efeitos=bloqueados", texto)
        self.assertIn("saudável=sim", texto)
        self.assertIn("partidas independentes/decisões brutas=34/80", texto)
        self.assertIn("quarentena válidos/holdout=12/0", texto)
        self.assertIn("controle válidos/holdout=22/0", texto)
        self.assertIn("quarentena ativa=sim", texto)
        self.assertIn("reativação automática=não", texto)

    def test_prioridade_ligas_expoe_unidade_independente_sem_promover(self):
        texto = descrever_prioridade_ligas_gols({
            "estado": "em_formacao",
            "estado_execucao": "concluida",
            "cronologia_execucao": {"valida": True, "problemas": []},
            "efeitos_operacionais": {"valida": True},
            "saudavel": True,
            "versao": "prioridade-v2",
            "unidades_independentes": 20,
            "decisoes_brutas": 200,
            "oportunidades_prioridade": 2,
            "jogos_prioridade": 8,
            "oportunidades_controle": 3,
            "jogos_controle": 12,
            "delta_rendimento_oportunidade_por_detalhe": 0.0,
            "ic95_delta_rendimento_oportunidade": [-0.2, 0.2],
            "vantagem_captura_comprovada": False,
        })

        self.assertIn("partidas independentes/decisões brutas=20/200", texto)
        self.assertIn("execução=concluida", texto)
        self.assertIn("cronologia=ok", texto)
        self.assertIn("efeitos=bloqueados", texto)
        self.assertIn("saudável=sim", texto)
        self.assertIn("prioridade oportunidades/jogos=2/8", texto)
        self.assertIn("controle oportunidades/jogos=3/12", texto)
        self.assertIn("vantagem comprovada=não", texto)
        self.assertIn("altera fila=não", texto)

    def test_clv_expoe_cobertura_baixa_sem_anunciar_edge(self):
        texto = descrever_clv_live({
            "diagnosticos_informativos": {
                "clv_live": {
                    "versao": "clv-v7",
                    "criterio_independencia": (
                        "primeira_entrega_por_partida"
                    ),
                    "sinais_independentes_consultados": 880,
                    "comparaveis": 203,
                    "taxa_cobertura": 203 / 880,
                    "cadeia_custodia_clv": {
                        "estado": "integra",
                        "saudavel": True,
                        "integridade_evidencias": {
                            "observacoes_auditadas": 10665,
                            "total_problemas": 0,
                        },
                        "bloqueia_inferencia": False,
                    },
                    "cobertura_cotacao_entrada_prospectiva": {
                        "entregas_instrumentadas": 30,
                        "cotacoes_congeladas_validas": 27,
                        "taxa_cobertura_cotacao_entrada": 0.9,
                        "estado": (
                            "cobertura_cotacao_entrada_suficiente"
                        ),
                    },
                    "coorte_clv_prospectiva_fixa": {
                        "unidades_coorte": 12,
                        "tamanho_planejado": 120,
                        "tamanho_desenvolvimento": 84,
                        "tamanho_holdout": 36,
                        "divisao_fixa": True,
                        "estado": "formando_coorte_fixa",
                        "vantagem_replicada": False,
                    },
                    "total": {
                        "cobertura_minima_informar_edge": 0.9,
                        "estado_evidencia": (
                            "cobertura_insuficiente_para_informar_edge"
                        ),
                        "pode_informar_edge": False,
                    },
                },
            },
        })

        self.assertIn("partidas/comparáveis=880/203", texto)
        self.assertIn("cobertura=23.1%", texto)
        self.assertIn("mínimo=90.0%", texto)
        self.assertIn("pode informar edge=não", texto)
        self.assertIn("gate operacional=não", texto)
        self.assertIn("cadeia de custódia CLV=integra", texto)
        self.assertIn("observações de odds auditadas=10665", texto)
        self.assertIn("inconsistências=0", texto)
        self.assertIn("bloqueia inferência=não", texto)
        self.assertIn("cotação de entrada prospectiva=27/30 (90.0%)", texto)
        self.assertIn(
            "estado da instrumentação=cobertura_cotacao_entrada_suficiente",
            texto,
        )
        self.assertIn("coorte CLV fixa=12/120 (dev=84, holdout=36)", texto)
        self.assertIn("divisão fixa=sim", texto)
        self.assertIn("estado da coorte=formando_coorte_fixa", texto)
        self.assertIn("vantagem replicada=não", texto)

    def test_portfolio_expoe_decisao_e_coorte_sem_promover(self):
        texto = descrever_portfolio_edge({
            "componentes": {
                "portfolio_edge": {
                    "evidencias": {
                        "versao": "portfolio-v10",
                        "versao_referencia_preco_sem_vig": "preco-v2",
                        "versao_avaliacao_historica_escanteios_asiaticos": (
                            "asiatico-v3"
                        ),
                        "mercados_favoraveis": [],
                        "decisoes": {
                            "proximo_gol": "aguardando_amostra",
                        },
                        "coortes_selecao": {
                            "proximo_gol": "aprovado",
                        },
                    },
                },
            },
        })

        self.assertIn("versão=portfolio-v10", texto)
        self.assertIn("referência sem vig=preco-v2", texto)
        self.assertIn("histórico asiático=asiatico-v3", texto)
        self.assertIn("favoráveis=nenhum", texto)
        self.assertIn(
            "proximo_gol=aguardando_amostra[aprovado]", texto
        )
        self.assertIn("promoção automática=não", texto)

    def test_cota_do_dia_anterior_nao_parece_saldo_atual(self):
        texto = descrever_cota_provedor({
            "dia": "2026-09-09",
            "limite_confirmado_provedor": 7500,
            "restante_informado_provedor": 2532,
            "cota_provedor_dia": "2026-09-08",
            "cota_provedor_vigente": False,
            "cota_observada_em": 1788904626.0,
        })

        self.assertIn("dia anterior", texto)
        self.assertIn("dia=2026-09-08", texto)
        self.assertIn("dia atual=2026-09-09", texto)
        self.assertIn("aplicada ao dia atual=não", texto)

    def test_saida_cp1252_e_reconfigurada_sem_quebrar_simbolos(self):
        bruto = io.BytesIO()
        stream = io.TextIOWrapper(bruto, encoding="cp1252", errors="strict")

        self.assertTrue(configurar_saida_terminal(stream))
        stream.write("corte ≤ 1 e ≥ 0")
        stream.flush()

        self.assertEqual("corte ≤ 1 e ≥ 0", bruto.getvalue().decode("utf-8"))

    def test_descreve_proximo_gol_balanceado_sem_confundir_com_oficial(self):
        descricao = descrever_proximo_gol_balanceado({
            "estado": "coletando",
            "candidatos": 7,
            "tamanho_coorte": 40,
            "greens": 4,
            "reds": 2,
            "pendentes": 1,
            "roi": 0.12,
            "decisao": "aguardando_amostra_futura",
            "funil_origem_v10f": {
                "candidatos_por_24h": 1.5,
                "gargalo_principal_interno": "odd_140_159",
            },
        })

        self.assertIn("coorte=7/40", descricao)
        self.assertIn("G/R/P=4/2/1", descricao)
        self.assertIn("candidatos/24h=1.50", descricao)
        self.assertIn("gargalo=odd_140_159", descricao)
        self.assertIn("Telegram oficial=não", descricao)
        self.assertIn("promoção automática=não", descricao)

    def test_descreve_funil_marginal_sem_promover_relaxamento(self):
        descricao = descrever_funil_marginal_proximo_gol({
            "estados_independentes": 52,
            "distancia_minima_observada": 2,
            "passagens_marginais": {
                "odd_curta": 6,
                "pressao_balanceada": 9,
            },
            "gargalo_tecnico_marginal": "odd_curta",
            "bloqueios_adicionais_estados_tecnicamente_prontos": {
                "cartao_vermelho_reavaliar": 1,
            },
            "auditoria_contrafactual": {
                "greens": 1,
                "reds": 2,
                "pendentes": 3,
            },
        })

        self.assertIn("estados=52", descricao)
        self.assertIn("menor distância=2", descricao)
        self.assertIn("odd curta=6/52", descricao)
        self.assertIn("pressão balanceada=9/52", descricao)
        self.assertIn("cartao_vermelho_reavaliar=1", descricao)
        self.assertIn("auditoria exploratória G/R/P=1/2/3", descricao)
        self.assertIn("resultados não usados no funil", descricao)
        self.assertIn("efeito operacional=nenhum", descricao)

    def test_enriquece_drill_e_armazenamento_com_estado_persistido(self):
        atual = {
            "saudavel": True,
            "drill_restauracao_compactada": {},
        }
        estado = {
            "validacao": {
                "armazenamento": {"banco_mb": 100},
                "drill_restauracao_compactada": {
                    "saudavel": True,
                    "estado": "restauracao_confirmada",
                    "backup": "monitor.db.gz",
                },
            }
        }

        enriquecida = enriquecer_validacao_com_watchdog(atual, estado)

        self.assertEqual(
            enriquecida["drill_restauracao_compactada"]["estado"],
            "restauracao_confirmada",
        )
        self.assertEqual(enriquecida["armazenamento"]["banco_mb"], 100)
        self.assertEqual(atual["drill_restauracao_compactada"], {})

    def test_resume_uso_efetivo_das_fontes_sem_duplicar_entrega(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        try:
            conexao.executescript(
                """
                CREATE TABLE sinais (
                    id INTEGER PRIMARY KEY,
                    criado_em TEXT,
                    status TEXT,
                    features_json TEXT
                );
                CREATE TABLE entregas_alertas (
                    sinal_id INTEGER,
                    status TEXT
                );
                INSERT INTO sinais VALUES
                    (1, datetime('now', 'localtime'), 'aprovado',
                     '{"fonte_odds":"packball"}'),
                    (2, datetime('now', 'localtime'), 'rejeitado',
                     '{"fonte_odds":"thestatsapi"}'),
                    (3, datetime('now', 'localtime'), 'aprovado',
                     '{"fonte_odds":"thestatsapi"}'),
                    (4, datetime('now', 'localtime'), 'rejeitado', '{}');
                INSERT INTO entregas_alertas VALUES
                    (1, 'entregue'), (1, 'entregue'), (3, 'filtrado');
                """
            )

            resumo = resumir_uso_fontes_odds(conexao, horas=24)
            texto = descrever_uso_fontes_odds(resumo)

            self.assertEqual(
                resumo["por_fonte"]["packball"]["enviados"], 1
            )
            self.assertEqual(
                resumo["por_fonte"]["thestatsapi"]["avaliados"], 2
            )
            self.assertEqual(
                resumo["por_fonte"]["thestatsapi"]["aprovados"], 1
            )
            self.assertEqual(
                resumo["por_fonte"]["thestatsapi"]["enviados"], 0
            )
            self.assertIn(
                "TheStats: avaliados=2, aprovados=1, enviados=0", texto
            )
        finally:
            conexao.close()

    def test_descreve_challenger_v2_sem_promover(self):
        descricao = descrever_challenger_v2_ft({
            "candidatos_coorte": 12,
            "tamanho_coorte_fixa": 75,
            "avaliadas": 10,
            "minimo_resultados_validos": 70,
            "greens": 7, "reds": 3, "pendentes": 2,
            "lucro_unidades": 1.5, "roi": 0.15,
            "intervalo_roi_95": [-0.2, 0.5],
            "decisao_estatistica": "aguardando_amostra_futura",
        })
        self.assertIn("coorte=12/75", descricao)
        self.assertIn("válidos=10/70", descricao)
        self.assertIn("G/R/P=7/3/2", descricao)
        self.assertIn("ROI=+15.0%", descricao)
        self.assertIn("Telegram=não", descricao)

    def test_descreve_comparacao_ft_sem_misturar_v2_historica(self):
        descricao = descrever_comparacao_gol_ft_v2_v3(
            {
                "avaliadas": 30, "greens": 21, "reds": 9,
                "roi": 0.1917,
            },
            {
                "tamanho_coorte_fixa": 75,
                "iniciado_em": "2026-08-11T12:30:00",
            },
            {
                "iniciado_em": "2026-08-11T12:30:00",
                "v2_controle": {
                    "candidatos_coorte": 3, "avaliadas": 2,
                    "pendentes": 1, "greens": 2, "reds": 0,
                    "roi": 0.6,
                },
                "v3": {
                    "candidatos_coorte": 2, "avaliadas": 2,
                    "pendentes": 0, "greens": 1, "reds": 1,
                    "roi": -0.1,
                },
            },
        )

        self.assertIn("V2 histórica gol_ft — congelada", descricao)
        self.assertIn("resultados=30 | G/R=21/9 | ROI=+19.2%", descricao)
        self.assertIn("V2-controle: coorte=3/75", descricao)
        self.assertIn("V3: coorte=2/75", descricao)
        self.assertIn("diferença descritiva V3-V2=-70.0 pp", descricao)
        self.assertIn("Telegram oficial=não", descricao)

    def test_comparacao_ft_aguarda_resultados_nos_dois_bracos(self):
        descricao = descrever_comparacao_gol_ft_v2_v3(
            {},
            {"tamanho_coorte_fixa": 75},
            {
                "v2_controle": {"avaliadas": 0},
                "v3": {"avaliadas": 1, "roi": 0.5},
            },
        )

        self.assertIn(
            "diferença descritiva: aguardando os dois braços",
            descricao,
        )

    def test_descreve_filtro_da_regra_ativa_sem_promover_amostra_pequena(self):
        descricao = descrever_filtro_regra_ativa({
            "mercado": "proximo_gol",
            "regra_versao": "regra-ativa",
            "comparacao": {
                "estado": "amostra_insuficiente",
                "decisao": "aguardando_amostra",
                "amostra_enviadas": 8,
                "amostra_filtradas": 7,
                "amostra_minima_por_coorte": 30,
            },
            "enviadas": {"greens": 6, "reds": 2, "roi": 0.2839},
            "filtradas": {"greens": 2, "reds": 5, "roi": -0.4},
        })

        self.assertIn("proximo_gol [regra-ativa]", descricao)
        self.assertIn("G=6, R=2, ROI=+28.4%", descricao)
        self.assertIn("G=2, R=5, ROI=-40.0%", descricao)
        self.assertIn("mínimo=30/grupo", descricao)
        self.assertIn("decisão=aguardando_amostra", descricao)

    def test_resume_filtro_separadamente_para_cada_regra_ativa(self):
        diagnostico = [{
            "mercado": "proximo_gol",
            "regra_versao": "sinais-v10e-proximo-gol-faixa-global-max75",
            "comparacao": {
                "estado": "amostra_insuficiente",
                "amostra_enviadas": 8,
                "amostra_filtradas": 7,
            },
            "enviadas": {"roi": 0.2839},
            "filtradas": {"roi": -0.4},
        }]
        with patch(
            "status_bot.fingerprint_vinculado_no_banco",
            return_value="fingerprint",
        ), patch(
            "status_bot.comparar_filtros_por_mercado",
            return_value=diagnostico,
        ) as comparar:
            resumo = resumir_filtros_regras_ativas(
                object(), ["proximo_gol"]
            )

        self.assertEqual(len(resumo), 1)
        self.assertEqual(resumo[0]["mercado"], "proximo_gol")
        self.assertEqual(resumo[0]["enviadas"]["roi"], 0.2839)
        comparar.assert_called_once()

    def test_resume_simulacoes_das_versoes_ativas_por_mercado(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        try:
            conexao.executescript(
                """
                CREATE TABLE sinais (
                    id INTEGER PRIMARY KEY,
                    mercado TEXT,
                    regra_versao TEXT
                );
                CREATE TABLE entregas_alertas (
                    sinal_id INTEGER,
                    canal TEXT,
                    status TEXT,
                    entregue_em TEXT
                );
                INSERT INTO sinais VALUES
                    (1, 'gol_ft', 'antiga'),
                    (2, 'gol_ht', 'ht-ativa'),
                    (3, 'proximo_gol', 'pg-ativa');
                INSERT INTO entregas_alertas VALUES
                    (1, 'grupo:teste', 'entregue', datetime('now', 'localtime')),
                    (2, 'grupo:teste', 'entregue', datetime('now', 'localtime')),
                    (3, 'grupo:teste', 'entregue', datetime('now', 'localtime'));
                """
            )

            resumo = resumir_simulacoes_ativas_hoje(
                conexao,
                {
                    "gol_ft": "ft-ativa",
                    "gol_ht": "ht-ativa",
                    "proximo_gol": "pg-ativa",
                },
            )

            self.assertEqual(
                resumo,
                {"gol_ft": 0, "gol_ht": 1, "proximo_gol": 1},
            )
            self.assertEqual(
                descrever_simulacoes_ativas_hoje(resumo),
                "gol_ft=0 | gol_ht=1 | proximo_gol=1",
            )
        finally:
            conexao.close()

    def test_descreve_amostra_de_cada_janela_temporal(self):
        descricao = descrever_janelas_temporais_ritmo({
            "janelas_temporais": {"5": 41, "10": 18, "15": 7},
        })

        self.assertEqual(
            descricao, "5min=41 | 10min=18 | 15min=7"
        )

    def test_descreve_janelas_ausentes_como_zero(self):
        self.assertEqual(
            descrever_janelas_temporais_ritmo({}),
            "5min=0 | 10min=0 | 15min=0",
        )

    def test_descreve_cobertura_temporal_dos_jogos_priorizados(self):
        descricao = descrever_cobertura_temporal_priorizada({
            "metrica_retencao_temporal": "cobertura_temporal_foco",
            "base": {
                "cobertura_temporal_foco": 0.42,
                "rendimento_temporal_por_foco": 0.75,
            },
            "experimento": {
                "cobertura_temporal_foco": 0.68,
                "rendimento_temporal_por_foco": 1.1,
            },
        })

        self.assertIn("foco base/atual=0.42/0.68", descricao)
        self.assertIn("rendimento por foco base/atual=0.75/1.1", descricao)
        self.assertIn("métrica decisória=cobertura dos jogos em foco", descricao)

    def test_cobertura_temporal_priorizada_preserva_legado_sem_dado(self):
        descricao = descrever_cobertura_temporal_priorizada({})

        self.assertIn("foco base/atual=-/-", descricao)
        self.assertIn("métrica decisória=cobertura de todas as leituras", descricao)

    def test_descreve_historico_api_live_como_sombra_sem_custo_extra(self):
        descricao = descrever_historico_api_live({
            "saudavel": True,
            "estado": "coletando",
            "snapshots": 120,
            "fixtures": 20,
            "cobertura_completa": 0.875,
            "janelas_disponiveis": {"5": 16, "10": 11, "15": 8},
            "comparacoes_packball_api": 12,
            "taxa_concordancia_packball_api": 0.75,
            "prontidao_revisao": {
                "estado": "aguardando_amostra",
                "snapshots": 8,
                "minimo_snapshots": 30,
                "fixtures": 4,
                "minimo_fixtures": 10,
            },
        })

        self.assertIn("somente sombra", descricao)
        self.assertIn("snapshots=120", descricao)
        self.assertIn("completos=87.5%", descricao)
        self.assertIn("5/10/15=16/11/8", descricao)
        self.assertIn("comparações PackBall/API=12", descricao)
        self.assertIn("concordância=75.0%", descricao)
        self.assertIn(
            "prontidão para revisão=aguardando_amostra "
            "(8/30 snapshots, 4/10 jogos)",
            descricao,
        )
        self.assertIn("chamadas adicionais=0", descricao)
        self.assertIn("uso nos sinais=não", descricao)

    def test_historico_api_live_indisponivel_nao_e_usado_em_sinais(self):
        descricao = descrever_historico_api_live({
            "saudavel": False,
            "motivo": "historico_api_live_indisponivel",
        })

        self.assertIn("indisponível", descricao)
        self.assertIn("uso nos sinais=não", descricao)

    def test_descreve_integridade_periodica_do_banco_ativo(self):
        descricao = descrever_integridade_banco_ativo({
            "estado": "integro",
            "verificado_em": "2026-08-09T16:00:00",
            "proxima_verificacao_em": "2026-08-09T16:10:00",
            "recuperacao_necessaria": False,
        })

        self.assertIn("integro", descricao)
        self.assertIn("recuperacao necessaria=nao", descricao)

    def test_descreve_recuperacao_automatica_do_banco(self):
        inexistente = Path.cwd() / ".recuperacao_inexistente_teste.json"
        self.assertEqual(
            ler_recuperacao_banco(inexistente)["estado"],
            "nunca_acionada",
        )
        descricao = descrever_recuperacao_banco({
            "estado": "banco_restaurado",
            "backup": "periodico_20260809_12.db",
            "restaurado_em": "2026-08-09T15:30:00",
            "quarentena": "quarentena_corrompido.db",
        })
        self.assertIn("concluida", descricao)
        self.assertIn("periodico_20260809_12.db", descricao)
        self.assertIn("telegram=pendente", descricao)

    def test_exibe_diversidade_necessaria_para_sinal_oficial(self):
        saida = io.StringIO()
        with redirect_stdout(saida):
            imprimir_diversidade_calibracao({
                "diversidade_calibracao": {
                    "gol_ft": {
                        "pronto": False,
                        "estado": "diversidade_temporal_insuficiente",
                        "amostra": 100,
                        "dias_distintos": 5,
                        "ligas_distintas": 22,
                        "minimo_dias": 7,
                        "minimo_ligas": 5,
                    },
                },
            })

        texto = saida.getvalue()
        self.assertIn("gol_ft", texto)
        self.assertIn("dias=5/7", texto)
        self.assertIn("ligas=22/5", texto)
        self.assertIn("oficial=bloqueado", texto)

    def test_descreve_cada_pendencia_profissional(self):
        linhas = descrever_pendencias_prontidao({
            "pendencias": [
                {"requisito": "mercado:gol_ht", "estado": "amostra_9_de_100"},
                {"requisito": "telegram_oficial", "estado": "sem_prova_real"},
            ]
        })

        self.assertEqual(linhas, [
            "  pendência profissional — mercado:gol_ht: amostra_9_de_100",
            "  pendência profissional — telegram_oficial: sem_prova_real",
        ])

    def test_prontidao_completa_explicita_ausencia_de_pendencias(self):
        self.assertEqual(
            descrever_pendencias_prontidao({"pendencias": []}),
            ["  pendências profissionais: nenhuma"],
        )

    def test_distingue_fonte_ft_comprovada_de_calibracao_pendente(self):
        prontidao = {
            "componentes": {
                "mercados": {
                    "escanteios_ft_asiatico": {
                        "pronto": False,
                        "evidencias": {
                            "fonte_comprovada": True,
                            "resultados_resolvidos": 3,
                            "faltam_resultados_reais": 97,
                        },
                    },
                },
            },
        }
        estado_odds = {
            "por_bet": {
                "32": {
                    "ofertas_anexadas": 365,
                    "ultima_oferta_anexada_em": "2026-07-28T18:50:39",
                },
            },
        }

        descricao = descrever_escanteios_ft_asiatico(
            prontidao, estado_odds
        )

        self.assertIn("bet 32=comprovada", descricao)
        self.assertIn("ofertas anexadas=365", descricao)
        self.assertIn("amostra independente=3/100", descricao)
        self.assertIn(
            "sinal oficial=bloqueado (aguardando calibração)",
            descricao,
        )

    def test_exibe_conclusao_congelada_sem_confundir_com_nova_amostra(self):
        saida = io.StringIO()
        with redirect_stdout(saida):
            imprimir_conclusao_experimento_filtro({
                "conclusao_filtro_simulacoes": {
                    "versao": "conclusao-filtro-simulacoes-v1",
                    "concluido_em": "2026-07-28T22:35:58",
                    "decisao": "nao_comprovado",
                    "evidencia": {
                        "amostra_enviadas": 57,
                        "amostra_filtradas": 31,
                        "delta_roi": -0.2253,
                        "intervalo_delta_roi_95": [-0.6372, 0.1866],
                    },
                },
            })

        texto = saida.getvalue()
        self.assertIn("vantagem não comprovada", texto)
        self.assertIn("congelada=sim", texto)
        self.assertIn("filtro promovido=não", texto)
        self.assertIn("57/31", texto)
        self.assertIn("não reabrem este experimento", texto)

    def test_calibracoes_antigas_ficam_visiveis_sem_misturar_regra_ativa(self):
        caminho = Path.cwd() / ".teste_status_calibracoes_arquivadas.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            with banco.conexao:
                banco.conexao.executemany(
                    """
                    INSERT INTO calibracoes (
                        mercado, regra_versao, atualizado_em,
                        amostra, ativa, modelo_json
                    ) VALUES (?, ?, ?, ?, ?, '{}')
                    """,
                    (
                        ("gol_ft", "sinais-v4", "2026-07-25T12:00:00", 83, 0),
                        ("gol_ht", "sinais-v4", "2026-07-25T12:00:00", 17, 0),
                        ("gol_ht", "sinais-v6", "2026-07-26T01:00:00", 2, 0),
                    ),
                )
                banco.conexao.executemany(
                    """
                    INSERT INTO historico_calibracoes (
                        mercado, regra_versao, registrado_em,
                        amostra, ativa, amostra_fingerprint,
                        motivo, modelo_hash, modelo_json
                    ) VALUES (?, ?, ?, ?, ?, '', NULL, ?, '{}')
                    """,
                    (
                        (
                            "gol_ft", "sinais-v4",
                            "2026-07-25T12:00:00", 83, 0,
                            hash_modelo_calibracao({}),
                        ),
                        (
                            "gol_ht", "sinais-v4",
                            "2026-07-25T12:00:00", 17, 0,
                            hash_modelo_calibracao({}),
                        ),
                    ),
                )

            resumo = resumir_calibracoes_arquivadas(
                banco.conexao, "sinais-v6"
            )
            self.assertEqual(len(resumo), 1)
            self.assertEqual(resumo[0]["regra_versao"], "sinais-v4")
            self.assertEqual(resumo[0]["mercados"]["gol_ft"], 83)
            self.assertTrue(resumo[0]["historico_vinculado"])
            self.assertNotIn("sinais-v6", str(resumo))

            saida = io.StringIO()
            with redirect_stdout(saida):
                imprimir_calibracoes_arquivadas(
                    banco.conexao, "sinais-v6"
                )
            texto = saida.getvalue()
            self.assertIn("sinais-v4", texto)
            self.assertIn("gol_ft=83", texto)
            self.assertIn("histórico imutável=vinculado", texto)
            self.assertIn("uso na regra ativa=não", texto)
            self.assertNotIn("sinais-v6", texto)

            resumo_ativo = resumir_calibracoes_arquivadas(
                banco.conexao,
                "sinais-v6",
                regras_ativas_por_mercado={"gol_ft": "sinais-v4"},
            )
            self.assertEqual(
                resumo_ativo[0]["mercados_em_uso"], ["gol_ft"]
            )
            saida_ativa = io.StringIO()
            with redirect_stdout(saida_ativa):
                imprimir_calibracoes_arquivadas(
                    banco.conexao,
                    "sinais-v6",
                    regras_ativas_por_mercado={"gol_ft": "sinais-v4"},
                )
            self.assertIn(
                "uso na regra ativa=sim (gol_ft)",
                saida_ativa.getvalue(),
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_imprime_supervisao_sombra_sem_aplicar_regra(self):
        validacao = {
            "cortes_sombra": {
                "versao": "cortes-sombra-v1",
                "aplicacao_automatica": False,
                "mercados_aptos_para_revisao": ["gol_ft"],
                "avaliacoes": {
                    "gol_ft": {
                        "estado": "avaliavel",
                        "apto_para_alterar_regra": True,
                        "corte_escolhido_no_desenvolvimento": {
                            "feature": "pressao_media_10min_max",
                            "operador": ">=",
                            "limiar": 42.0,
                        },
                        "metricas_validacao_corte": {
                            "amostra": 25,
                            "roi": 0.08,
                        },
                    },
                    "gol_ht": {"estado": "amostra_insuficiente"},
                },
            }
        }
        saida = io.StringIO()

        with redirect_stdout(saida):
            imprimir_cortes_sombra(validacao)

        texto = saida.getvalue()
        self.assertIn("aplicacao automatica=nao", texto)
        self.assertIn("aptos para revisao=gol_ft", texto)
        self.assertIn("validacao n=25", texto)
        self.assertIn("ROI=0.08", texto)
        self.assertIn("valor confirmatório=não", texto)

    def test_imprime_estado_vazio_sem_falhar(self):
        saida = io.StringIO()

        with redirect_stdout(saida):
            imprimir_cortes_sombra({})

        self.assertIn("aptos para revisao=-", saida.getvalue())

    def test_imprime_controle_e_ic_da_hipotese_sombra(self):
        caminho = Path.cwd() / ".teste_status_hipotese.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        banco.fechar()
        avaliacao = {
            "identificador": "proximo_gol_minuto_56_v1_20260825",
            "iniciado_em": "2026-08-25T01:42:15",
            "mercado": "proximo_gol",
            "feature": "minuto",
            "operador": "maior_igual",
            "limiar": 56.0,
            "estado": "aguardando_amostra",
            "selecionada": {"amostra": 18, "roi": 0.3444},
            "minimo_resultados": 30,
            "faltam": 12,
            "controle_excluido": {"amostra": 6, "roi": -0.0333},
            "minimo_controle": 10,
            "faltam_controle": 4,
            "delta_roi_selecionada_controle": 0.3778,
            "intervalo_delta_roi_95": [-0.6467, 1.4023],
            "versao_avaliacao": (
                "avaliacao-hipoteses-sombra-controle-ic95-v2"
            ),
        }
        saida = io.StringIO()
        try:
            with patch(
                "status_bot.avaliar_hipoteses_sombra_ativas",
                return_value={"avaliacoes": [avaliacao]},
            ), redirect_stdout(saida):
                imprimir_hipoteses_sombra(caminho)
        finally:
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

        texto = saida.getvalue()
        self.assertIn(
            "id=proximo_gol_minuto_56_v1_20260825",
            texto,
        )
        self.assertIn("desde=2026-08-25T01:42:15", texto)
        self.assertIn("controle=6/10", texto)
        self.assertIn("faltam controle=4", texto)
        self.assertIn("delta ROI corte-controle=0.3778", texto)
        self.assertIn("IC95=[-0.6467, 1.4023]", texto)
        self.assertIn("controle-ic95-v2", texto)

    def test_descreve_autostart_com_heartbeat_como_confirmado(self):
        descricao = descrever_autostart({
            "instalada": True,
            "saudavel": True,
            "consultavel": False,
            "origem_evidencia": "execucao_agendada_recente",
            "heartbeat": {
                "idade_minutos": 1.25,
                "definicao_tarefa": {
                    "saudavel": True,
                    "consulta_direta": True,
                    "permite_inicio_em_bateria": True,
                    "continua_em_bateria": True,
                },
            },
        })

        self.assertIn("execução agendada confirmada", descricao)
        self.assertIn("definição e bateria comprovadas", descricao)
        self.assertNotIn("indisponível", descricao)

    def test_nao_finge_confirmacao_sem_heartbeat_valido(self):
        descricao = descrever_autostart({
            "instalada": False,
            "saudavel": False,
            "consultavel": False,
            "origem_evidencia": None,
        })

        self.assertEqual(
            descricao,
            "consulta direta indisponível; sem prova recente",
        )


    def test_status_historico_drift_le_diretamente_do_sqlite(self):
        caminho = Path.cwd() / ".teste_status_historico_drift.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            with banco.conexao:
                registrar_historico_drift_simulacoes(
                    banco.conexao,
                    {
                        "regra_versao": "sinais-v4",
                        "drift_simulacoes": {
                            "mercados": {
                                "gol_ft": {
                                    "estado": "estavel",
                                    "avaliavel": True,
                                    "amostra_recente": 30,
                                    "amostra_base": 60,
                                    "ultima_decisao_id": 10,
                                }
                            }
                        },
                    },
                )
            resumo = carregar_historico_drift_status(
                caminho, "sinais-v4"
            )
            self.assertTrue(resumo["saudavel"])
            self.assertEqual(resumo["estado"], "ativo")
            self.assertEqual(resumo["total"], 1)
            self.assertEqual(resumo["mercados"], 1)
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
