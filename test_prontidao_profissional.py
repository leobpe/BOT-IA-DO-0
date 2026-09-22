import copy
import json
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from avaliacao_clv_live import VERSAO as VERSAO_AVALIACAO_CLV_LIVE
from mercados import MERCADOS_CALIBRADOS
from prontidao_profissional import (
    avaliar_prontidao,
    classificar_pendencia_prontidao,
    coletar_estado_pre_live_autoritativo,
    diagnosticar_acesso_packball,
    diagnosticar_cota_api_football,
    diagnosticar_exposicao_coleta_prospectiva,
    diagnosticar_fluxo_amostras_ativas,
    diagnosticar_fonte_odds_betsapi,
    diagnosticar_fonte_odds_thestatsapi,
    diagnosticar_frescor_espelho_watchdog,
    diagnosticar_integridade_banco_ativo,
    diagnosticar_prazo_prontidao,
    diagnosticar_sincronizacao_historico_drift,
    resumir_fluxo_amostras_ativas,
    resumir_resultado_prontidao,
)
from versoes_gol_ft_reforcado import VERSAO_GOL_FT_REFORCADO
from versoes_gol_ht_protegido import VERSAO_GOL_HT_PROTEGIDO


def evidencias_prontas():
    return {
        "agora": "2026-07-25T21:35:00",
        "worker_treino_isolado": {
            "saudavel": True,
            "estado": "pronto",
            "motivo": None,
            "protocolo": "treino-modelo-isolado-v1",
            "tentativas": 1,
            "recuperou_falha_transitoria": False,
            "falhas_transitorias": [],
            "duracao_ms": 50.0,
        },
        "avaliacoes_periodicas": {
            nome: {
                "custodia_execucao_compativel": True,
                "cronologia_execucao": {"valida": True},
                "efeitos_operacionais": {"valida": True},
                "exposicao_coleta_prospectiva": {
                    "versao": "exposicao-coleta-prospectiva-v2",
                    "estado": "exposicao_observada",
                    "saudavel": True,
                    "requer_atencao": False,
                    "coortes": 1,
                    "coortes_com_exposicao": 1,
                    "coortes_sem_exposicao_por_manutencao": 0,
                    "aplicacao_sinais": False,
                    "altera_calibracao": False,
                    "altera_prioridade": False,
                    "promocao_automatica": False,
                    "reativacao_automatica": False,
                    "telegram": False,
                },
            }
            for nome in (
                "acompanhamento_odd",
                "prioridade_ligas_gols",
                "desajuste_odds",
                "quarentena_fallback_ht",
            )
        },
        "configuracao": {
            "valida": True,
            "recursos": {
                "telegram_gols": True,
                "telegram_escanteios": True,
                "sinais_teste": True,
            },
        },
        "coleta": {
            "saudavel": True,
            "partidas_ultimo_ciclo": 12,
        },
        "fluxo_amostras_ativas": {
            "saudavel": True,
            "partidas_ultimo_ciclo": 12,
            "mercados": {
                mercado: {
                    "versao": f"versao-{mercado}",
                    "registros_24h": 5,
                    "ultimo_candidato_em": "2026-07-25T21:34:00",
                }
                for mercado in MERCADOS_CALIBRADOS
                if mercado not in {"escanteios_1t", "escanteios_2t"}
            },
            "bracos": {},
        },
        "backup": {"saudavel": True},
        "pre_live": {
            "saudavel": True,
            "estado": "ativo",
            "pid": 123,
            "banco": {"valido": True, "integridade": ["ok"]},
            "backup": {
                "saudavel": True, "fresco": True,
                "arquivo": "pre_live_20260725_210000.db",
                "idade_horas": 0.5,
            },
            "resultados": 30,
            "roi": 0.08,
            "apto_revisao": True,
        },
        "historico_drift": {
            "saudavel": True,
            "estado": "integro",
            "total": 5,
            "mercados": 5,
            "chaves_atuais": 5,
            "chaves_atuais_ausentes": [],
            "chaves_atuais_divergentes": [],
            "json_invalidos": 0,
            "chaves_duplicadas": 0,
        },
        "persistencia_estado_watchdog": {
            "saudavel": True,
            "estado": "persistido",
            "motivo": None,
            "persistido_em": "2026-07-25T21:30:00",
        },
        "historico_drift_watchdog": {
            "saudavel": True,
            "estado": "integro",
            "chaves_atuais": 5,
        },
        "supervisao_watchdog": {
            "estado": "fresco",
            "fresco": True,
        },
        "integridade_banco_ativo": {
            "saudavel": True,
            "estado": "integro",
            "verificado_em": "2026-07-25T21:30:00",
            "proxima_verificacao_em": "2026-07-25T21:40:00",
            "recuperacao_necessaria": False,
        },
        "pendencias_resultados": {"por_mercado": {}},
        "processos": {
            "monitor_ativo": True,
            "watchdog_ativo": True,
            "monitor_codigo": "atualizado",
            "watchdog_codigo": "atualizado",
        },
        "validacao": {
            "saudavel": True,
            "prioridade_scanner_packball": {
                "saudavel": True,
                "estado": "saudavel",
                "ciclos_observados": 33,
                "episodios_sem_prioridade_observados": 2,
                "duracao_sem_prioridade_segundos": 0.0,
                "duracao_total_sem_prioridade_segundos": 311.0,
            },
            "politica_telegram": {
                "versao": "telegram-compacto-criticos-v1",
                "alertas_tecnicos_ativos": False,
                "alertas_sombra_ativos": False,
                "resumo_diario_compacto": True,
                "alertas_operacionais_criticos": True,
            },
            "hipoteses_sombra": {
                "integridade": {
                    "saudavel": True,
                    "estado": "valido",
                    "total": 1,
                    "protegido": True,
                    "invalidas": [],
                    "gatilhos_ausentes": [],
                },
            },
            "pontuacao_sombra": {
                "integro": True,
                "mercados_com_modelo": ["gol_ft"],
                "por_mercado": {
                    "gol_ft": {"integro": True},
                },
            },
            "pontuacao_contexto_sombra": {
                "integro": True,
                "mercados_com_modelo": [],
                "por_mercado": {
                    mercado: {"integro": True}
                    for mercado in MERCADOS_CALIBRADOS
                },
            },
            "pontuacao_longa_sombra": {
                "integro": True,
                "mercados_com_modelo": [],
                "por_mercado": {
                    mercado: {"integro": True}
                    for mercado in MERCADOS_CALIBRADOS
                },
            },
            "auditoria_ligas_sombra": {
                "versao": "auditoria-ligas-sombra-bonferroni-v1",
                "integro": True,
                "aplicacao_automatica": False,
                "mercados_com_evidencia_historica": [],
                "por_mercado": {
                    mercado: {"estado": "aguardando_amostra"}
                    for mercado in MERCADOS_CALIBRADOS
                    if mercado not in {"escanteios_1t", "escanteios_2t"}
                },
            },
            "historico_avaliacao_contexto": {
                "saudavel": True,
                "estado": "integro",
                "total": 10,
                "mercados": 5,
                "json_invalidos": [],
                "divergentes": [],
                "duplicadas": [],
                "ultimo": "2026-07-25T21:30:00",
            },
            "ritmo_acesso_packball": {
                "saudavel": True,
                "estado": "seguro",
            },
            "experimento_ritmo_packball": {
                "saudavel": True,
                "estado": "aprovado",
                "minimo_ciclos": 12,
                "minimo_minutos": 45,
                "minutos_observados": 60,
                "pausas_packball": 0,
                "retencao_fluxo": 1.0,
                "retencao_temporal": 1.1,
                "base": {
                    "processadas_por_10_minutos": 12,
                    "cobertura_temporal": 0.2,
                },
                "experimento": {
                    "ciclos": 15,
                    "processadas_por_10_minutos": 12,
                    "cobertura_temporal": 0.22,
                },
            },
            "contador_api": {
                "saudavel": True,
                "limite_confirmado_provedor": 7500,
                "consumo_dia": 100,
            },
            "cache_api_football": {"saudavel": True},
            "valor_mercado_sinais": {
                "versao": "valor-mercado-calibrado-conservador-v6",
                "saudavel": True,
                "sinais_calibrados": 5,
                "com_valor_conservador": 5,
                "sem_valor_conservador": 0,
                "entregues_oficiais_sem_valor": 0,
                "rastros_validos": 5,
                "rastros_ausentes": 0,
                "rastros_divergentes": 0,
                "entregues_oficiais_rastro_invalido": 0,
                "com_referencia_sem_vig": 5,
                "sem_referencia_sem_vig": 0,
                "referencias_margem_incoerente": 0,
                "por_mercado": {},
            },
            "integridade_telegram": {"saudavel": True},
            "experimento_filtro": {
                "saudavel": True,
                "estado": "valido",
                "iniciado_em": "2026-07-22T18:10:08",
                "protegido": True,
            },
            "conclusao_filtro_simulacoes": {
                "versao": "conclusao-filtro-simulacoes-v1",
                "concluido_em": "2026-07-24T10:00:00",
                "regra_fingerprint": "fp-atual",
                "decisao": "evidencia_favoravel",
                "evidencia": {
                    "estado": "avaliavel",
                    "decisao": "evidencia_favoravel",
                    "decisoes_enviadas": 35,
                    "decisoes_filtradas": 36,
                    "resultados_resolvidos_enviadas": 32,
                    "resultados_resolvidos_filtradas": 33,
                    "pendentes_enviadas": 3,
                    "pendentes_filtradas": 3,
                    "voids_enviadas": 2,
                    "voids_filtradas": 3,
                    "amostra_enviadas": 30,
                    "amostra_filtradas": 30,
                    "amostra_minima_por_coorte": 30,
                    "intervalo_delta_taxa_acerto_95": [0.01, 0.20],
                    "intervalo_delta_roi_95": [0.02, 0.25],
                },
            },
            "estado_calibracoes": {
                mercado: {
                    "ativa": True,
                    "amostra": 100,
                    "motivo": None,
                }
                for mercado in MERCADOS_CALIBRADOS
            },
            "progresso_calibracao": {
                mercado: {"amostra": 100, "faltam": 0}
                for mercado in MERCADOS_CALIBRADOS
            },
            "diversidade_calibracao": {
                mercado: {
                    "pronto": True,
                    "estado": "aprovada",
                    "amostra": 100,
                    "dias_distintos": 7,
                    "ligas_distintas": 5,
                    "minimo_dias": 7,
                    "minimo_ligas": 5,
                }
                for mercado in MERCADOS_CALIBRADOS
            },
        },
        "dataset_temporal": {
            "validos": 100,
            "elegiveis": 100,
            "cobertura": 1.0,
            "schema_features": "features-temporais-v2",
        },
        "cortes_sombra": {
            "versao": "cortes-sombra-v1",
            "aplicacao_automatica": False,
            "mercados_aptos_para_revisao": [],
            "avaliacoes": {},
        },
        "diagnostico_pre_calibracao": {
            mercado: {
                "amostra": 100,
                "taxa_acerto": 0.70,
                "intervalo_acerto_95": [0.60, 0.78],
                "roi": 0.10,
                "lucro_unidades": 10.0,
                "discriminacao_pontuacao": {"auc": 0.65},
            }
            for mercado in MERCADOS_CALIBRADOS
        },
        "sobreajuste_gol_ft": {
            "estado": "nenhum_corte_exploratorio_comprovado",
            "amostra": 300,
            "desenvolvimento": 270,
            "validacao_reservada": 30,
            "testes_explorados": 826,
            "aprovados_bonferroni": 0,
            "aprovados_bh": 0,
            "promocao_retroativa_permitida": False,
            "exige_validacao_prospectiva": True,
        },
        "pareamento_api": {"saudavel": True, "estado": "saudavel"},
        "cache_api_operacional": {"saudavel": True, "estado": "saudavel"},
        "telegram": {"provas_teste": 5, "provas_oficiais": 1},
        "comparacao_filtro": {
            "comparacao": {
                "geral": {
                    "estado": "avaliavel",
                    "decisao": "evidencia_favoravel",
                    "decisoes_enviadas": 35,
                    "decisoes_filtradas": 36,
                    "resultados_resolvidos_enviadas": 32,
                    "resultados_resolvidos_filtradas": 33,
                    "pendentes_enviadas": 3,
                    "pendentes_filtradas": 3,
                    "voids_enviadas": 2,
                    "voids_filtradas": 3,
                    "amostra_enviadas": 30,
                    "amostra_filtradas": 30,
                    "amostra_minima_por_coorte": 30,
                    "intervalo_delta_taxa_acerto_95": [0.01, 0.20],
                    "intervalo_delta_roi_95": [0.02, 0.25],
                }
            }
        },
        "odds_periodos": {
            "FT": {
                "mapeada": True,
                "diagnostico_fonte": "fonte_real_comprovada",
            },
            "1T": {
                "mapeada": True,
                "diagnostico_fonte": "fonte_real_comprovada",
            },
            "2T": {
                "mapeada": True,
                "diagnostico_fonte": "fonte_real_comprovada",
            },
        },
        "autostart": {
            "instalada": True, "consultavel": True,
            "saudavel": True, "divergencias": [],
            "origem_evidencia": "consulta_direta",
            "heartbeat": {
                "versao": "autostart-heartbeat-v2",
                "definicao_tarefa": {
                    "saudavel": True,
                    "consulta_direta": True,
                    "permite_inicio_em_bateria": True,
                    "continua_em_bateria": True,
                },
            },
        },
    }


class ClassificacaoPendenciaProntidaoTest(unittest.TestCase):
    def test_distingue_espera_estatistica_de_falha_tecnica(self):
        self.assertEqual(
            classificar_pendencia_prontidao("pendente_amostra"),
            "aguardando_dados_reais",
        )
        self.assertEqual(
            classificar_pendencia_prontidao("reprovado_validacao"),
            "modelo_reprovado",
        )
        self.assertEqual(
            classificar_pendencia_prontidao("degradado"),
            "pendencia_tecnica",
        )

    def test_pausa_por_login_e_dependencia_externa(self):
        self.assertEqual(
            classificar_pendencia_prontidao("aguardando_login_packball"),
            "dependencia_externa",
        )


class ExposicaoColetaProntidaoTest(unittest.TestCase):
    def test_quatro_relogios_integros_formam_diagnostico_pronto(self):
        diagnostico = diagnosticar_exposicao_coleta_prospectiva(
            evidencias_prontas()["avaliacoes_periodicas"]
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual("pronto", diagnostico["estado"])
        self.assertEqual(4, diagnostico["avaliacoes_auditadas"])
        self.assertEqual(4, diagnostico["coortes"])
        self.assertEqual(4, diagnostico["coortes_com_exposicao"])
        self.assertFalse(diagnostico["tempo_de_parede_conta_como_amostra"])

    def test_efeito_ativo_no_relogio_degrada_e_identifica_avaliacao(self):
        avaliacoes = evidencias_prontas()["avaliacoes_periodicas"]
        avaliacoes["desajuste_odds"][
            "exposicao_coleta_prospectiva"
        ]["telegram"] = True

        diagnostico = diagnosticar_exposicao_coleta_prospectiva(avaliacoes)

        self.assertFalse(diagnostico["pronto"])
        self.assertIn(
            "desajuste_odds:efeitos_relogio_invalidos",
            diagnostico["problemas"],
        )

    def test_pausa_planejada_nao_esconde_relogio_degradado(self):
        evidencias = evidencias_prontas()
        evidencias["modo_manutencao"] = {
            "ativo": True,
            "motivo": "manutencao_manual",
            "solicitado_em": "2026-07-25T20:00:00",
        }
        exposicao = evidencias["avaliacoes_periodicas"][
            "prioridade_ligas_gols"
        ]["exposicao_coleta_prospectiva"]
        exposicao.update({
            "estado": "telemetria_indisponivel",
            "saudavel": False,
            "requer_atencao": True,
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual("pausa_planejada", resultado["estado_geral"])
        self.assertTrue(resultado["falha_tecnica_ativa"])
        self.assertEqual(
            "degradado",
            resultado["componentes"][
                "exposicao_coleta_prospectiva"
            ]["estado"],
        )


class AcessoPackBallProntidaoTest(unittest.TestCase):
    def test_pausa_futura_por_login_e_identificada(self):
        diagnostico = diagnosticar_acesso_packball(
            {
                "motivo": "falha_login_packball",
                "pausado_ate": "2026-07-25T22:35:00",
            },
            agora=datetime.fromisoformat("2026-07-25T21:35:00"),
        )

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(
            diagnostico["estado"], "aguardando_login_packball"
        )
        self.assertEqual(diagnostico["restante_segundos"], 3600.0)

    def test_pausa_expirada_nao_bloqueia(self):
        diagnostico = diagnosticar_acesso_packball(
            {
                "motivo": "falha_login_packball",
                "pausado_ate": "2026-07-25T20:35:00",
            },
            agora=datetime.fromisoformat("2026-07-25T21:35:00"),
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "pronto")


class FonteOddsTheStatsProntidaoTest(unittest.TestCase):
    def _configuracao_oficial(self):
        return {
            "chave_configurada": True,
            "sombra_ativa": True,
            "aplicacao_sinais": True,
        }

    def _ciclo_oficial(self):
        return {
            "thestatsapi_sombra": {
                "estado": "coleta_oficial",
                "ativa": True,
                "disponivel": True,
                "aplicacao_sinais": True,
                "telegram": True,
                "calibracao": False,
                "substitui_packball": False,
                "sem_autorizacao_sinal": False,
                "modo": "oficial_fail_closed",
                "erros": 0,
                "chamadas_rede": 27,
                "pareadas": 13,
                "tentativas_pareamento": 33,
                "partidas_com_odds": 13,
                "ofertas_odds_persistidas": 301,
                "desligar_com": "THESTATSAPI_APLICACAO_SINAIS_ATIVA=0",
            },
        }

    def test_complemento_oficial_coerente_esta_pronto(self):
        diagnostico = diagnosticar_fonte_odds_thestatsapi(
            self._configuracao_oficial(), self._ciclo_oficial()
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "pronto")
        self.assertTrue(diagnostico["oficial"])
        self.assertEqual(diagnostico["partidas_com_odds"], 13)
        self.assertEqual(diagnostico["ofertas_persistidas"], 301)
        self.assertEqual(diagnostico["divergencias"], [])

    def test_configuracao_oficial_nao_aceita_runtime_sombra(self):
        ciclo = self._ciclo_oficial()
        ciclo["thestatsapi_sombra"].update({
            "aplicacao_sinais": False,
            "telegram": False,
            "sem_autorizacao_sinal": True,
            "modo": "sombra",
        })

        diagnostico = diagnosticar_fonte_odds_thestatsapi(
            self._configuracao_oficial(), ciclo
        )

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "degradado")
        self.assertIn(
            "aplicacao_sinais_divergente", diagnostico["divergencias"]
        )
        self.assertIn("modo_oficial_divergente", diagnostico["divergencias"])

    def test_fonte_opcional_desativada_nao_degrada_prontidao(self):
        diagnostico = diagnosticar_fonte_odds_thestatsapi({}, {})

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(
            diagnostico["modo"], "desativada_intencionalmente"
        )

    def test_runtime_oficial_divergente_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["configuracao"]["thestatsapi"] = (
            self._configuracao_oficial()
        )
        evidencias["coleta"].update(self._ciclo_oficial())
        evidencias["coleta"]["thestatsapi_sombra"][
            "substitui_packball"
        ] = True

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["fonte_odds_thestatsapi"]
        self.assertFalse(componente["pronto"])
        self.assertIn(
            "packball_indevidamente_substituido",
            componente["evidencias"]["divergencias"],
        )
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        self.assertTrue(resultado["falha_tecnica_ativa"])


class FonteOddsBetsAPIProntidaoTest(unittest.TestCase):
    def _configuracao_oficial(self):
        return {
            "chave_configurada": True,
            "ativa": True,
            "aplicacao_sinais": True,
            "limite_hora": 3000,
            "limite_diario": 50000,
            "modo": "complemento_oficial_fail_closed",
        }

    def _ciclo_oficial(self):
        return {
            "betsapi": {
                "ativa": True,
                "aplicacao_sinais": True,
                "uso_hora": 120,
                "limite_hora": 3000,
                "uso_dia": 900,
                "limite_diario": 50000,
                "circuito_aberto": False,
                "partidas_pareadas": 8,
                "partidas_consultadas": 8,
                "mercados_anexados": 5,
            }
        }

    def test_betsapi_oficial_coerente_esta_pronta(self):
        diagnostico = diagnosticar_fonte_odds_betsapi(
            self._configuracao_oficial(), self._ciclo_oficial()
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "pronto")
        self.assertTrue(diagnostico["oficial"])
        self.assertEqual(diagnostico["mercados_anexados"], 5)

    def test_circuito_aberto_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["configuracao"]["betsapi"] = (
            self._configuracao_oficial()
        )
        evidencias["coleta"].update(self._ciclo_oficial())
        evidencias["coleta"]["betsapi"]["circuito_aberto"] = True

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["fonte_odds_betsapi"]
        self.assertFalse(componente["pronto"])
        self.assertIn(
            "circuito_aberto", componente["evidencias"]["divergencias"]
        )
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )


class FluxoAmostrasAtivasProntidaoTest(unittest.TestCase):
    def _processos(self):
        return {"monitor_ativo": True}

    def _fluxo(self, instante="2026-08-29T19:55:00"):
        return {
            "saudavel": True,
            "mercados": {
                "gol_ft": {"ultimo_candidato_em": instante},
                "gol_ht": {"ultimo_candidato_em": instante},
            },
            "bracos": {
                "challenger-raro": {
                    "ativo": True,
                    "ultimo_candidato_em": None,
                    "registros_24h": 0,
                },
            },
        }

    def test_fluxo_recente_esta_pronto_e_braco_raro_nao_degrada(self):
        diagnostico = diagnosticar_fluxo_amostras_ativas(
            self._fluxo(),
            {"partidas_ultimo_ciclo": 15},
            self._processos(),
            ("gol_ft", "gol_ht"),
            agora=datetime(2026, 8, 29, 20, 0),
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["mercados_sem_fluxo"], [])
        self.assertFalse(diagnostico["bracos_afetam_saude"])

    def test_mercado_base_sem_amostra_recente_degrada(self):
        fluxo = self._fluxo()
        fluxo["mercados"]["gol_ht"][
            "ultimo_candidato_em"
        ] = "2026-08-29T19:20:00"

        diagnostico = diagnosticar_fluxo_amostras_ativas(
            fluxo,
            {"partidas_ultimo_ciclo": 15},
            self._processos(),
            ("gol_ft", "gol_ht"),
            agora=datetime(2026, 8, 29, 20, 0),
        )

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "degradado")
        self.assertEqual(diagnostico["mercados_sem_fluxo"], ["gol_ht"])

    def test_politica_composta_recente_nao_inventa_falha_sem_aprovacao(self):
        fluxo = self._fluxo()
        fluxo["mercados"]["gol_ft"] = {
            "versao": VERSAO_GOL_FT_REFORCADO,
            "ultimo_candidato_em": None,
            "heartbeat_politica": {
                "observado_em": "2026-08-29T19:58:00",
                "ativa": True,
                "versao": VERSAO_GOL_FT_REFORCADO,
                "avaliados": 0,
                "oficiais": 0,
            },
        }

        diagnostico = diagnosticar_fluxo_amostras_ativas(
            fluxo,
            {"partidas_ultimo_ciclo": 15},
            self._processos(),
            ("gol_ft", "gol_ht"),
            agora=datetime(2026, 8, 29, 20, 0),
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["mercados_sem_fluxo"], [])
        self.assertEqual(
            diagnostico["mercados"]["gol_ft"][
                "idade_heartbeat_politica_minutos"
            ],
            2.0,
        )

    def test_extrai_heartbeat_persistido_da_politica_gol_ft(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                mercado TEXT, regra_versao TEXT, criado_em TEXT,
                features_json TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, encerrado_em TEXT
            );
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY, coletado_em TEXT,
                qualidade_json TEXT
            );
            """
        )
        qualidade = {"gol_ft_reforcado": {
            "ativa": True,
            "avaliados": 0,
            "oficiais": 0,
            "versao": VERSAO_GOL_FT_REFORCADO,
        }}
        conexao.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?)",
            (1, "2026-08-29T19:58:00", json.dumps(qualidade)),
        )

        with patch.dict(
            "os.environ", {"GOL_FT_REFORCADO_ATIVO": "1"}
        ):
            fluxo = resumir_fluxo_amostras_ativas(
                conexao,
                ("gol_ft",),
                agora=datetime(2026, 8, 29, 20, 0),
            )
        conexao.close()

        heartbeat = fluxo["mercados"]["gol_ft"]["heartbeat_politica"]
        self.assertTrue(heartbeat["ativa"])
        self.assertEqual(heartbeat["versao"], VERSAO_GOL_FT_REFORCADO)
        self.assertEqual(heartbeat["observado_em"], "2026-08-29T19:58:00")

    def test_extrai_heartbeat_da_quarentena_principal_gol_ht(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                mercado TEXT, regra_versao TEXT, criado_em TEXT,
                features_json TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, encerrado_em TEXT
            );
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY, coletado_em TEXT,
                qualidade_json TEXT
            );
            """
        )
        qualidade = {"gol_ht_protegido": {
            "ativa": True,
            "oficial_ativo": False,
            "avaliados": 0,
            "oficiais": 0,
            "v8c_sombra": 0,
            "versao": VERSAO_GOL_HT_PROTEGIDO,
        }}
        conexao.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?)",
            (1, "2026-09-08T19:58:00", json.dumps(qualidade)),
        )

        fluxo = resumir_fluxo_amostras_ativas(
            conexao,
            ("gol_ht",),
            agora=datetime(2026, 9, 8, 20, 0),
        )
        conexao.close()

        heartbeat = fluxo["mercados"]["gol_ht"]["heartbeat_politica"]
        self.assertTrue(heartbeat["ativa"])
        self.assertFalse(heartbeat["oficial_ativo"])
        self.assertEqual(heartbeat["versao"], VERSAO_GOL_HT_PROTEGIDO)
        self.assertEqual(heartbeat["observado_em"], "2026-09-08T19:58:00")

    def test_sem_jogos_ao_vivo_nao_inventa_falha_de_amostra(self):
        diagnostico = diagnosticar_fluxo_amostras_ativas(
            {"saudavel": True, "mercados": {}, "bracos": {}},
            {"partidas_ultimo_ciclo": 0},
            self._processos(),
            ("gol_ft", "gol_ht"),
            agora=datetime(2026, 8, 29, 20, 0),
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(
            diagnostico["motivo"],
            "sem_jogos_ao_vivo_no_ultimo_ciclo",
        )

    def test_contagem_de_partidas_ausente_sincroniza_sem_falsa_falha(self):
        diagnostico = diagnosticar_fluxo_amostras_ativas(
            self._fluxo(), {}, self._processos(), ("gol_ft", "gol_ht"),
            agora=datetime(2026, 8, 29, 20, 0),
        )

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "sincronizando")


class CotaAPIFootballProntidaoTest(unittest.TestCase):
    def test_cota_disponivel_esta_pronta(self):
        diagnostico = diagnosticar_cota_api_football({
            "saudavel": True,
            "limite_diario_seguro": 7000,
            "consumo_dia": 6900,
            "restante_seguro_dia": 100,
        })

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "pronto")
        self.assertEqual(diagnostico["restante"], 100)

    def test_cota_esgotada_informa_proximo_reset_utc(self):
        diagnostico = diagnosticar_cota_api_football(
            {
                "saudavel": True,
                "limite_diario_seguro": 7000,
                "consumo_dia": 7000,
                "restante_seguro_dia": 0,
            },
            agora=datetime(2026, 8, 29, 23, 58, tzinfo=timezone.utc),
        )

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "aguardando_reset_cota")
        self.assertEqual(
            diagnostico["proximo_reset_utc"],
            "2026-08-30T00:00:00+00:00",
        )
        self.assertEqual(diagnostico["segundos_ate_reset"], 120)

    def test_contador_inseguro_continua_falha_tecnica(self):
        diagnostico = diagnosticar_cota_api_football({
            "saudavel": False,
            "limite_diario_seguro": 7000,
            "consumo_dia": 100,
            "restante_seguro_dia": 6900,
        })

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(diagnostico["estado"], "degradado")

    def test_cota_esgotada_nao_e_classificada_como_falha_tecnica(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["contador_api"].update({
            "limite_diario_seguro": 7000,
            "consumo_dia": 7000,
            "restante_seguro_dia": 0,
        })

        resultado = avaliar_prontidao(evidencias)

        api = resultado["componentes"]["api_football"]
        self.assertFalse(api["pronto"])
        self.assertEqual(api["estado"], "aguardando_reset_cota")
        self.assertTrue(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        self.assertFalse(resultado["falha_tecnica_ativa"])
        self.assertIn({
            "requisito": "api_football",
            "estado": "aguardando_reset_cota",
            "categoria": "dependencia_externa",
        }, resultado["pendencias"])


class EstadoPreLiveAutoritativoTest(unittest.TestCase):
    def test_snapshot_ativo_nao_oculta_processo_ja_parado(self):
        anterior = {
            "pre_live": {
                "saudavel": True,
                "estado": "ativo",
                "pid": 25708,
            }
        }

        atual = coletar_estado_pre_live_autoritativo(
            ".",
            anterior,
            auditar_fn=lambda _pasta: {
                "saudavel": False,
                "estado": "parado",
                "pid": 25708,
                "status_processo": "encerrado",
                "pid_responde": False,
                "trava_ativa": False,
            },
        )

        self.assertEqual("parado", atual["estado"])
        self.assertFalse(atual["saudavel"])
        self.assertEqual("ativo", atual["estado_watchdog_anterior"])
        self.assertTrue(atual["snapshot_watchdog_divergente"])

    def test_falha_da_revalidacao_nao_reaproveita_saude_antiga(self):
        def falhar(_pasta):
            raise PermissionError("sem acesso")

        atual = coletar_estado_pre_live_autoritativo(
            ".",
            {"pre_live": {"saudavel": True, "estado": "ativo"}},
            auditar_fn=falhar,
        )

        self.assertEqual("auditoria_falhou", atual["estado"])
        self.assertFalse(atual["saudavel"])
        self.assertEqual("ativo", atual["estado_watchdog_anterior"])
        self.assertEqual("PermissionError", atual["erro_auditoria"])


class ProntidaoProfissionalTest(unittest.TestCase):
    def test_prazo_fica_suspenso_e_sem_data_durante_manutencao(self):
        resultado = {
            "pronto_profissional_completo": False,
            "componentes": {
                "modo_manutencao": {
                    "evidencias": {"ativo": True},
                },
                "seletor_pre_live_validacao": {
                    "evidencias": {
                        "resultados": 0,
                        "amostra_minima": 60,
                    },
                },
                "mercados": {
                    "proximo_gol": {
                        "evidencias": {
                            "faltam": 92,
                            "challenger_balanceado": {"faltam": 40},
                        },
                    },
                },
            },
            "diagnosticos_informativos": {
                "clv_live": {
                    "coorte_clv_prospectiva_fixa": {
                        "unidades_faltantes": 120,
                    },
                },
            },
        }

        prazo = diagnosticar_prazo_prontidao(resultado)

        self.assertEqual(prazo["estado"], "suspenso_manutencao")
        self.assertTrue(prazo["exige_retomada_manual"])
        self.assertFalse(prazo["calendario_em_contagem"])
        self.assertIsNone(prazo["dias_estimados"])
        self.assertIsNone(prazo["data_estimada"])
        self.assertEqual(prazo["maior_faltante_quantificado"], 120)
        self.assertEqual(len(prazo["requisitos_quantificados"]), 4)

    def test_prazo_ativo_nao_inventa_data_sem_ritmo_da_coorte_exata(self):
        resultado = {
            "pronto_profissional_completo": False,
            "componentes": {
                "modo_manutencao": {"evidencias": {"ativo": False}},
                "mercados": {
                    "gol_ht": {
                        "evidencias": {
                            "metodos_ativos": [{
                                "identificador": "ht_preciso",
                                "faltam": 60,
                            }],
                        },
                    },
                },
            },
        }

        prazo = diagnosticar_prazo_prontidao(resultado)

        self.assertEqual(
            prazo["estado"], "aguardando_ritmo_prospectivo_exato"
        )
        self.assertTrue(prazo["calendario_em_contagem"])
        self.assertFalse(prazo["prazo_calendario_disponivel"])
        self.assertIsNone(prazo["data_estimada"])

    def test_prazo_calcula_dias_operacionais_da_coorte_exata(self):
        resultado = {
            "pronto_profissional_completo": False,
            "componentes": {
                "modo_manutencao": {"evidencias": {"ativo": False}},
                "mercados": {
                    "gol_ht": {
                        "evidencias": {
                            "metodos_ativos": [{
                                "identificador": "ht_preciso",
                                "candidatos": 5,
                                "tamanho_coorte": 10,
                                "faltam": 5,
                                "exposicao_coorte_prontidao": {
                                    "estado": "exposicao_observada",
                                    "saudavel": True,
                                    "requer_atencao": False,
                                    "exposicao_operacional_confirmada_horas": 48,
                                    "cobertura_telemetria_desde_ancora": True,
                                },
                            }],
                        },
                    },
                },
            },
        }

        prazo = diagnosticar_prazo_prontidao(resultado)
        requisito = prazo["requisitos_quantificados"][0]

        self.assertEqual(
            prazo["estado"], "coletando_com_ritmo_operacional_observado"
        )
        self.assertEqual(requisito["ritmo_por_24h_operacionais"], 2.5)
        self.assertEqual(requisito["dias_operacionais_estimados"], 2)
        self.assertEqual(requisito["confiabilidade_ritmo"], "preliminar")
        self.assertFalse(prazo["prazo_calendario_disponivel"])
        self.assertIsNone(prazo["data_estimada"])

    def test_prazo_nao_extrapola_com_poucas_unidades_ou_poucas_horas(self):
        resultado = {
            "pronto_profissional_completo": False,
            "componentes": {
                "modo_manutencao": {"evidencias": {"ativo": False}},
                "mercados": {
                    "gol_ht": {
                        "evidencias": {
                            "metodos_ativos": [
                                {
                                    "identificador": "poucas_unidades",
                                    "candidatos": 4,
                                    "tamanho_coorte": 10,
                                    "faltam": 6,
                                    "exposicao_coorte_prontidao": {
                                        "saudavel": True,
                                        "requer_atencao": False,
                                        "exposicao_operacional_confirmada_horas": 48,
                                        "cobertura_telemetria_desde_ancora": True,
                                    },
                                },
                                {
                                    "identificador": "poucas_horas",
                                    "candidatos": 5,
                                    "tamanho_coorte": 10,
                                    "faltam": 5,
                                    "exposicao_coorte_prontidao": {
                                        "saudavel": True,
                                        "requer_atencao": False,
                                        "exposicao_operacional_confirmada_horas": 23.9,
                                        "cobertura_telemetria_desde_ancora": True,
                                    },
                                },
                            ],
                        },
                    },
                },
            },
        }

        prazo = diagnosticar_prazo_prontidao(resultado)

        self.assertEqual(prazo["requisitos_com_ritmo_estimado"], 0)
        for requisito in prazo["requisitos_quantificados"]:
            self.assertEqual(requisito["confiabilidade_ritmo"], "sem_ritmo")
            self.assertIsNone(requisito["ritmo_por_24h_operacionais"])
            self.assertIsNone(requisito["dias_operacionais_estimados"])

    def test_worker_treino_saudavel_integra_operacao_continua(self):
        resultado = avaliar_prontidao(evidencias_prontas())
        componente = resultado["componentes"]["worker_treino_isolado"]

        self.assertTrue(componente["pronto"])
        self.assertEqual(componente["estado"], "pronto")
        self.assertTrue(
            resultado["componentes"]["operacao_continua"]["evidencias"][
                "worker_treino_isolado"
            ]
        )

    def test_worker_treino_invalido_vira_falha_tecnica(self):
        evidencias = evidencias_prontas()
        evidencias["worker_treino_isolado"].update({
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "worker_treino_isolado_indisponivel",
            "erro": "RuntimeError",
        })

        resultado = avaliar_prontidao(evidencias)
        componente = resultado["componentes"]["worker_treino_isolado"]

        self.assertFalse(componente["pronto"])
        self.assertEqual(componente["estado"], "degradado")
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        self.assertTrue(resultado["falha_tecnica_ativa"])
        pendencia = next(
            item for item in resultado["pendencias"]
            if item["requisito"] == "worker_treino_isolado"
        )
        self.assertEqual(pendencia["categoria"], "pendencia_tecnica")

    def test_custodia_clv_invalida_vira_falha_tecnica(self):
        evidencias = evidencias_prontas()
        evidencias["clv_live"] = {
            "versao": VERSAO_AVALIACAO_CLV_LIVE,
            "cadeia_custodia_clv": {
                "versao": "cadeia-v1",
                "saudavel": False,
                "estado": "protecao_ausente_ou_invalida",
                "gatilhos_ausentes": [
                    "trg_odds_clv_delete_imutavel"
                ],
                "definicoes_invalidas": [],
                "bloqueia_inferencia": True,
            },
        }

        resultado = avaliar_prontidao(evidencias)
        componente = resultado["componentes"]["cadeia_custodia_clv"]

        self.assertFalse(componente["pronto"])
        self.assertEqual("inconsistente", componente["estado"])
        self.assertTrue(resultado["falha_tecnica_ativa"])
        pendencia = next(
            item for item in resultado["pendencias"]
            if item["requisito"] == "cadeia_custodia_clv"
        )
        self.assertEqual("pendencia_tecnica", pendencia["categoria"])

    def test_resumo_expoe_clv_sem_transformar_em_gate(self):
        evidencias = evidencias_prontas()
        evidencias["clv_live"] = {
            "versao": "clv-v4",
            "criterio_independencia": (
                "primeira_entrega_por_partida_e_mercado"
            ),
            "entregas_brutas_consultadas": 40,
            "sinais_independentes_consultados": 35,
            "comparaveis": 30,
            "taxa_cobertura": 30 / 35,
            "coorte_clv_prospectiva_fixa": {
                "versao": "coorte-fixa-v1",
                "criterio_coorte": "primeiras_120",
                "selecao_antes_do_resultado": True,
                "divisao_fixa": True,
                "tamanho_planejado": 120,
                "tamanho_desenvolvimento": 84,
                "tamanho_holdout": 36,
                "unidades_coorte": 12,
                "unidades_faltantes": 108,
                "coorte_completa": False,
                "estado": "formando_coorte_fixa",
                "vantagem_replicada": False,
                "pode_informar_edge": False,
                "pode_decidir_edge": False,
            },
            "total": {
                "amostra": 30,
                "media_pontos_probabilidade": 0.04,
                "mediana_pontos_probabilidade": 0.01,
                "intervalo_media_95": [0.01, 0.07],
                "estado_evidencia": (
                    "mark_to_market_favoravel_com_ic95_positivo"
                ),
                "pode_informar_edge": True,
                "pode_decidir_edge": False,
            },
            "movimento_preco_contratos_sobreviventes": {
                "amostra": 20,
                "media_pontos_probabilidade": -0.05,
                "intervalo_media_95": [-0.07, -0.03],
                "estado_evidencia": (
                    "diagnostico_condicionado_a_sobrevivencia"
                ),
                "vies_selecao_sobrevivencia": True,
                "pode_decidir_edge": False,
            },
            "por_mercado": {
                "gol_ht": {
                    "comparaveis": 30,
                    "taxa_cobertura": 0.8,
                    "media_pontos_probabilidade": 0.04,
                    "intervalo_media_95": [0.01, 0.07],
                    "estado_evidencia": (
                        "mark_to_market_favoravel_com_ic95_positivo"
                    ),
                },
            },
            "gate_operacional": False,
        }

        resultado = avaliar_prontidao(evidencias)
        resumo = resumir_resultado_prontidao(resultado)
        clv = resumo["diagnostico_valor_mercado"]

        self.assertEqual(35, clv["sinais_independentes"])
        self.assertFalse(clv["gate_operacional"])
        self.assertFalse(clv["mark_to_market"]["pode_decidir_edge"])
        self.assertEqual(
            12, clv["coorte_prospectiva_fixa"]["unidades_coorte"]
        )
        self.assertTrue(clv["coorte_prospectiva_fixa"]["divisao_fixa"])
        self.assertFalse(
            clv["coorte_prospectiva_fixa"]["pode_informar_edge"]
        )
        self.assertTrue(
            clv["movimento_preco_sobreviventes"]
            ["vies_selecao_sobrevivencia"]
        )

    def test_escanteio_ft_ancorado_expoe_coorte_futura_em_vez_do_historico(self):
        evidencias = evidencias_prontas()
        evidencias["portfolio_edge"] = {
            "versao": "avaliacao-portfolio-edge-read-only-v9",
            "todos_mercados_com_edge_comprovado": False,
            "mercados_favoraveis_para_revisao_manual": [],
            "avaliacoes": {
                "escanteios_ft_asiatico": {
                    "coorte_operacional_avaliada": (
                        "prospectiva_fixa_pos_ancora"
                    ),
                    "metricas_oficiais": {
                        "versao": "validacao-escanteios-ft-v1",
                        "regra_versao": "regra-fixa",
                        "estado": "coletando",
                        "decisao": "aguardando_amostra_futura",
                        "candidatos": 0,
                        "tamanho_coorte": 100,
                        "validos": 0,
                        "greens": 0,
                        "half_greens": 0,
                        "voids": 0,
                        "half_reds": 0,
                        "reds": 0,
                        "pendentes": 0,
                        "faltam": 100,
                        "roi": None,
                    },
                    "controle_operacional": {
                        "saudavel": True, "ativo": True,
                    },
                    "decisao": {"todos_satisfeitos": False},
                },
            },
            "promocao_automatica": False,
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"][
            "escanteios_ft_asiatico"
        ]

        self.assertEqual("pendente_amostra", mercado["estado"])
        self.assertEqual(0, mercado["evidencias"]["amostra"])
        self.assertEqual(100, mercado["evidencias"]["faltam"])
        self.assertEqual(
            "regra-fixa", mercado["evidencias"]["metodo_efetivo"]
        )
        self.assertFalse(
            mercado["evidencias"]["validacao_prospectiva"]
            ["historico_anterior_entra_na_decisao"]
        )

    def test_portfolio_sem_edge_comprovado_impede_prontidao_completa(self):
        evidencias = evidencias_prontas()
        evidencias["portfolio_edge"] = {
            "versao": "avaliacao-portfolio-edge-read-only-v1",
            "versao_avaliacao_historica_escanteios_asiaticos": (
                "avaliacao-edge-escanteios-asiaticos-v3"
            ),
            "todos_mercados_com_edge_comprovado": False,
            "mercados_favoraveis_para_revisao_manual": [],
            "regras_por_mercado": {"gol_ft": "regra-ft"},
            "avaliacoes": {
                "gol_ft": {
                    "decisao": {
                        "estado": "aguardando_primeiros_resultados"
                    }
                }
            },
        }

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["portfolio_edge"]
        self.assertEqual("pendente_amostra", componente["estado"])
        self.assertFalse(resultado["pronto_profissional_completo"])
        self.assertFalse(
            componente["evidencias"]["promocao_automatica"]
        )
        self.assertEqual(
            "avaliacao-edge-escanteios-asiaticos-v3",
            componente["evidencias"]
            ["versao_avaliacao_historica_escanteios_asiaticos"],
        )

    def test_entrega_oficial_sem_valor_degrada_prontidao(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["valor_mercado_sinais"].update({
            "saudavel": False,
            "sem_valor_conservador": 1,
            "entregues_oficiais_sem_valor": 1,
        })

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["valor_mercado_oficial"]
        self.assertEqual("degradado", componente["estado"])
        self.assertFalse(resultado["pronto_profissional_completo"])
        self.assertTrue(resultado["falha_tecnica_ativa"])

    def test_entrega_oficial_com_rastro_de_valor_invalido_degrada(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["valor_mercado_sinais"].update({
            "saudavel": False,
            "rastros_validos": 4,
            "rastros_divergentes": 1,
            "entregues_oficiais_rastro_invalido": 1,
        })

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["valor_mercado_oficial"]
        self.assertEqual("degradado", componente["estado"])
        self.assertEqual(1, componente["evidencias"]["rastros_divergentes"])
        self.assertFalse(resultado["pronto_profissional_completo"])
        self.assertTrue(resultado["falha_tecnica_ativa"])

    def test_pre_live_sem_backup_degrada_operacao_profissional(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["pre_live"]["backup"]["saudavel"] = False

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertFalse(
            resultado["componentes"]["pre_live_operacional"]["pronto"]
        )
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )

    def test_pre_live_formando_amostra_nao_degrada_coleta(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["pre_live"].update({
            "resultados": 12, "roi": 0.05, "apto_revisao": False,
        })

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"][
            "seletor_pre_live_validacao"
        ]
        self.assertEqual(componente["estado"], "pendente_amostra")
        self.assertTrue(resultado["componentes"]["operacao_continua"]["pronto"])
        self.assertFalse(resultado["pronto_profissional_completo"])
        self.assertIn({
            "requisito": "seletor_pre_live_validacao",
            "estado": "pendente_amostra",
            "categoria": "aguardando_dados_reais",
        }, resultado["pendencias"])

    def test_pre_live_usa_coorte_nova_em_vez_do_historico_antigo(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["pre_live"].update({
            "resultados": 300,
            "roi": 0.20,
            "apto_revisao": True,
            "filtro_preciso": {
                "estado": "coletando",
                "validos": 0,
                "candidatos": 0,
                "tamanho_coorte": 60,
                "faltam": 60,
                "roi": None,
                "decisao": "aguardando_amostra_futura",
                "apto_revisao": False,
                "desenvolvimento": {"validos": 0},
                "holdout": {"validos": 0},
                "gate_preco_justo": {"satisfeito": False},
            },
            "controle_filtro_preciso": {
                "saudavel": True,
                "ativo": True,
                "estado": "ativo_padrao",
            },
        })

        resultado = avaliar_prontidao(evidencias)
        componente = resultado["componentes"][
            "seletor_pre_live_validacao"
        ]

        self.assertEqual("pendente_amostra", componente["estado"])
        self.assertEqual(0, componente["evidencias"]["resultados"])
        self.assertEqual(60, componente["evidencias"]["amostra_minima"])
        self.assertTrue(
            componente["evidencias"]["validacao_prospectiva"]
        )
        self.assertFalse(resultado["pronto_profissional_completo"])

    def test_auditoria_de_ligas_automatica_degrada_operacao(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["auditoria_ligas_sombra"][
            "aplicacao_automatica"
        ] = True

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["auditoria_ligas_sombra"]
        self.assertFalse(componente["pronto"])
        self.assertFalse(resultado["componentes"]["operacao_continua"]["pronto"])

    def test_politica_telegram_tecnica_ativa_degrada_prontidao(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["politica_telegram"][
            "alertas_tecnicos_ativos"
        ] = True

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["politica_telegram"]
        self.assertFalse(componente["pronto"])
        self.assertEqual(componente["estado"], "degradado")

    def test_resultado_de_analise_incerto_antigo_nao_degrada_rota_atual(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["integridade_telegram"] = {
            "saudavel": False,
            "saudavel_operacional": True,
            "envios_analise_incertos": 1,
            "resultados_analise_sem_aviso": 1,
        }

        resultado = avaliar_prontidao(evidencias)
        telegram = resultado["componentes"]["telegram_teste"]

        self.assertTrue(telegram["pronto"])
        self.assertTrue(
            telegram["evidencias"]["integridade_operacional_saudavel"]
        )
        self.assertEqual(
            telegram["evidencias"]["envios_analise_incertos"], 1
        )

    def test_integridade_operacional_telegram_falha_degrada_rota(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["integridade_telegram"] = {
            "saudavel": False,
            "saudavel_operacional": False,
            "envios_oficiais_incertos": 1,
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertFalse(resultado["componentes"]["telegram_teste"]["pronto"])

    def test_integridade_banco_ativo_exige_evidencia_recente(self):
        fresco = diagnosticar_integridade_banco_ativo(
            evidencias_prontas()["integridade_banco_ativo"],
            agora=datetime(2026, 7, 25, 21, 35, 0),
        )
        antigo = diagnosticar_integridade_banco_ativo(
            evidencias_prontas()["integridade_banco_ativo"],
            agora=datetime(2026, 7, 25, 22, 0, 0),
        )

        self.assertTrue(fresco["pronto"])
        self.assertEqual(fresco["estado"], "pronto")
        self.assertFalse(antigo["pronto"])
        self.assertEqual(antigo["estado"], "verificacao_desatualizada")

    def test_corrupcao_banco_ativo_degrada_prontidao_profissional(self):
        evidencias = evidencias_prontas()
        evidencias["integridade_banco_ativo"].update({
            "saudavel": False,
            "estado": "corrompido",
            "motivo": "banco_ativo_corrompido",
            "recuperacao_necessaria": True,
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertFalse(
            resultado["componentes"]["integridade_banco_ativo"]["pronto"]
        )
        self.assertTrue(resultado["falha_tecnica_ativa"])

    def test_pausa_planejada_nao_e_rotulada_como_falha_tecnica(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["modo_manutencao"] = {
            "ativo": True,
            "motivo": "manutencao_manual",
            "solicitado_em": "2026-07-25T21:34:00",
        }
        evidencias["processos"].update({
            "monitor_ativo": False,
            "watchdog_ativo": False,
        })
        evidencias["coleta"]["saudavel"] = False
        for item in evidencias["fluxo_amostras_ativas"][
            "mercados"
        ].values():
            item["ultimo_candidato_em"] = "2026-07-25T20:00:00"
        evidencias["integridade_banco_ativo"][
            "verificado_em"
        ] = "2026-07-25T20:00:00"
        evidencias["persistencia_estado_watchdog"] = {}
        evidencias["pre_live"].update({
            "saudavel": False,
            "estado": "parado",
            "pid": None,
            "ultima_execucao_erro": None,
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "pausa_planejada")
        self.assertFalse(resultado["falha_tecnica_ativa"])
        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])
        requisitos = {
            item["requisito"]: item for item in resultado["pendencias"]
        }
        self.assertEqual(
            requisitos["modo_manutencao"]["categoria"],
            "pausa_planejada",
        )
        for derivada in (
            "operacao_continua",
            "fluxo_amostras_ativas",
            "integridade_banco_ativo",
            "estado_watchdog_persistente",
            "pre_live_operacional",
        ):
            self.assertNotIn(derivada, requisitos)

    def test_pausa_planejada_nao_esconde_corrupcao_real(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["modo_manutencao"] = {
            "ativo": True,
            "motivo": "manutencao_manual",
        }
        evidencias["integridade_banco_ativo"].update({
            "saudavel": False,
            "estado": "corrompido",
            "motivo": "banco_ativo_corrompido",
            "recuperacao_necessaria": True,
        })

        resultado = avaliar_prontidao(evidencias)

        requisitos = {
            item["requisito"]: item for item in resultado["pendencias"]
        }
        self.assertTrue(resultado["falha_tecnica_ativa"])
        self.assertEqual(
            requisitos["integridade_banco_ativo"]["categoria"],
            "pendencia_tecnica",
        )

    def test_arquivo_de_manutencao_invalido_continua_falha_tecnica(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["modo_manutencao"] = {
            "ativo": True,
            "motivo": "arquivo_manutencao_invalido",
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertTrue(resultado["falha_tecnica_ativa"])
        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])

    def test_espelho_anterior_ao_processo_e_identificado(self):
        diagnostico = diagnosticar_frescor_espelho_watchdog(
            {
                "persistencia_estado_watchdog": {
                    "persistido_em": "2026-07-29T10:00:00"
                }
            },
            {"atualizado_em": "2026-07-29T10:01:00"},
        )

        self.assertFalse(diagnostico["fresco"])
        self.assertEqual(diagnostico["estado"], "anterior_ao_processo")

    def test_espelho_posterior_ao_processo_e_fresco(self):
        diagnostico = diagnosticar_frescor_espelho_watchdog(
            {
                "persistencia_estado_watchdog": {
                    "persistido_em": "2026-07-29T10:02:00"
                }
            },
            {"atualizado_em": "2026-07-29T10:01:00"},
        )

        self.assertTrue(diagnostico["fresco"])
        self.assertEqual(diagnostico["estado"], "fresco")

    def test_reinicio_aguardando_espelho_nao_e_rotulado_como_falha(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["saudavel"] = False
        evidencias["supervisao_watchdog"] = {
            "inicializando": True,
            "estado": "anterior_ao_processo",
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(
            resultado["estado_geral"], "supervisao_inicializando"
        )
        self.assertEqual(
            resultado["componentes"]["operacao_continua"]["estado"],
            "inicializando",
        )
        self.assertEqual(
            resultado["mercados_liberados_para_oficial"], []
        )

    def test_todos_requisitos_comprovados_resultam_em_pronto(self):
        resultado = avaliar_prontidao(evidencias_prontas())

        self.assertTrue(resultado["pronto_profissional_completo"])
        self.assertEqual(resultado["estado_geral"], "profissional_completo")
        self.assertEqual(
            set(resultado["mercados_liberados_para_oficial"]),
            set(MERCADOS_CALIBRADOS),
        )
        self.assertEqual(resultado["pendencias"], [])
        recuperacao = resultado["componentes"]["recuperacao_windows"]
        self.assertTrue(
            recuperacao["evidencias"]["permite_inicio_em_bateria"]
        )
        self.assertTrue(
            recuperacao["evidencias"]["continua_em_bateria"]
        )

    def test_pausa_packball_deduplica_falhas_derivadas(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["acesso_packball"] = {
            "motivo": "falha_login_packball",
            "pausado_ate": "2026-07-25T22:35:00",
        }
        evidencias["validacao"]["ritmo_acesso_packball"] = {
            "saudavel": True,
            "estado": "aguardando_telemetria",
        }
        for item in evidencias["fluxo_amostras_ativas"][
            "mercados"
        ].values():
            item["ultimo_candidato_em"] = "2026-07-25T20:00:00"

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(
            resultado["componentes"]["acesso_packball"]["estado"],
            "aguardando_login_packball",
        )
        self.assertEqual(
            resultado["componentes"]["operacao_continua"]["estado"],
            "aguardando_login_packball",
        )
        self.assertEqual(
            resultado["componentes"]["fluxo_amostras_ativas"]["estado"],
            "aguardando_login_packball",
        )
        self.assertEqual(
            resultado["componentes"]["ritmo_packball"]["estado"],
            "aguardando_login_packball",
        )
        requisitos = {
            item["requisito"]: item for item in resultado["pendencias"]
        }
        self.assertIn("acesso_packball", requisitos)
        self.assertNotIn("operacao_continua", requisitos)
        self.assertNotIn("fluxo_amostras_ativas", requisitos)
        self.assertNotIn("ritmo_packball", requisitos)
        self.assertEqual(
            requisitos["acesso_packball"]["categoria"],
            "dependencia_externa",
        )
        self.assertFalse(resultado["falha_tecnica_ativa"])

    def test_calibracao_ativa_sem_diversidade_nao_libera_oficial(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["diversidade_calibracao"]["gol_ft"].update({
            "pronto": False,
            "estado": "diversidade_temporal_insuficiente",
            "dias_distintos": 4,
        })

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]

        self.assertEqual(mercado["estado"], "bloqueado_diversidade")
        self.assertFalse(mercado["pronto"])
        self.assertNotIn(
            "gol_ft", resultado["mercados_liberados_para_oficial"]
        )
        self.assertEqual(mercado["evidencias"]["dias_distintos"], 4)
        self.assertEqual(mercado["evidencias"]["minimo_dias"], 7)

    def test_modelo_reprovado_expoe_recuperacao_prospectiva_sem_promover(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ft"].update({
            "ativa": False,
            "amostra": 100,
            "motivo": "pontuacao_sem_discriminacao",
            "amostra_validacao": 30,
            "roi_validacao_agregado": -0.18,
        })
        evidencias["validacao"]["hipoteses_sombra"]["avaliacoes"] = [{
            "identificador": "gol_ft_ritmo_escanteios_teste",
            "mercado": "gol_ft",
            "estado": "aguardando_amostra",
            "descricao_corte": "ritmo maior_igual 0.1786",
            "iniciado_em": "2026-08-09T13:20:46",
            "minimo_resultados": 30,
            "selecionada": {"amostra": 2, "roi": 0.2},
            "controle_excluido": {"amostra": 4, "roi": -0.1},
            "pendentes_resultado": 1,
            "pendentes_selecionados": 1,
            "pendentes_controle": 0,
            "faltam": 28,
            "faltam_controle": 6,
            "delta_roi_selecionada_controle": 0.3,
            "intervalo_delta_roi_95": [-0.2, 0.8],
        }]

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]
        recuperacao = mercado["evidencias"]["hipoteses_recuperacao"]

        self.assertEqual(mercado["estado"], "reprovado_validacao")
        self.assertNotIn(
            "gol_ft", resultado["mercados_liberados_para_oficial"]
        )
        self.assertTrue(
            mercado["evidencias"]["hipotese_recuperacao_em_andamento"]
        )
        self.assertEqual(len(recuperacao), 1)
        self.assertEqual(recuperacao[0]["resultados_selecionados"], 2)
        self.assertEqual(recuperacao[0]["pendentes_selecionados"], 1)
        self.assertFalse(recuperacao[0]["aplicacao_automatica"])

    def test_amostra_fonte_e_autostart_pendentes_nao_fingem_prontidao(self):
        evidencias = evidencias_prontas()
        evidencias["autostart"]["instalada"] = False
        evidencias["telegram"]["provas_oficiais"] = 0
        evidencias["odds_periodos"]["1T"]["mapeada"] = False
        evidencias["odds_periodos"]["2T"]["mapeada"] = False
        evidencias["odds_periodos"]["1T"][
            "diagnostico_fonte"
        ] = "catalogada_sem_oferta_real"
        evidencias["odds_periodos"]["2T"][
            "diagnostico_fonte"
        ] = "somente_exactly_tres_opcoes"
        for mercado in MERCADOS_CALIBRADOS:
            evidencias["validacao"]["estado_calibracoes"][mercado] = {
                "ativa": False,
                "amostra": 2,
                "motivo": "amostra_insuficiente",
            }
            evidencias["validacao"]["progresso_calibracao"][mercado] = {
                "amostra": 2,
                "faltam": 98,
            }

        resultado = avaliar_prontidao(evidencias)

        self.assertFalse(resultado["pronto_profissional_completo"])
        self.assertEqual(
            resultado["estado_geral"], "coleta_profissional_em_validacao"
        )
        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])
        self.assertEqual(
            resultado["componentes"]["mercados"]["escanteios_2t"]["estado"],
            "bloqueado_fonte",
        )
        self.assertEqual(
            resultado["componentes"]["mercados"]["escanteios_2t"][
                "evidencias"
            ]["diagnostico_fonte"],
            "somente_exactly_tres_opcoes",
        )
        self.assertEqual(
            resultado["componentes"]["recuperacao_windows"]["estado"],
            "aguardando_autorizacao",
        )

    def test_aprovado_em_canal_teste_nao_vira_prova_oficial(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["telegram"].update({
            "provas_oficiais": 0,
            "provas_aprovadas_em_teste": 14,
            "provas_simuladas_em_teste": 113,
        })

        resultado = avaliar_prontidao(evidencias)

        oficial = resultado["componentes"]["telegram_oficial"]
        self.assertFalse(oficial["pronto"])
        self.assertEqual(oficial["estado"], "pendente_evidencia_real")
        self.assertEqual(
            oficial["evidencias"]["provas_aprovadas_em_teste"], 14
        )
        self.assertEqual(
            oficial["evidencias"]["provas_simuladas_em_teste"], 113
        )
        self.assertFalse(oficial["evidencias"]["promocao_retroativa"])
        self.assertIn("canal experimental", oficial["resumo"])

    def test_primeiro_mercado_calibrado_pode_ser_liberado_isoladamente(self):
        evidencias = evidencias_prontas()
        evidencias["telegram"]["provas_oficiais"] = 0
        for mercado in MERCADOS_CALIBRADOS:
            evidencias["validacao"]["estado_calibracoes"][mercado][
                "ativa"
            ] = mercado == "gol_ft"

        resultado = avaliar_prontidao(evidencias)

        self.assertFalse(resultado["pronto_profissional_completo"])
        self.assertEqual(resultado["estado_geral"], "sinais_oficiais_parciais")
        self.assertEqual(
            resultado["mercados_liberados_para_oficial"], ["gol_ft"]
        )

    def test_mercados_suspensos_nao_bloqueiam_escopo_real(self):
        evidencias = evidencias_prontas()
        evidencias["mercados_exigidos"] = [
            mercado for mercado in MERCADOS_CALIBRADOS
            if mercado not in ("escanteios_1t", "escanteios_2t")
        ]
        evidencias["odds_periodos"]["1T"]["mapeada"] = False
        evidencias["odds_periodos"]["2T"]["mapeada"] = False

        resultado = avaliar_prontidao(evidencias)

        self.assertTrue(resultado["pronto_profissional_completo"])
        self.assertEqual(
            resultado["mercados_suspensos"],
            ["escanteios_1t", "escanteios_2t"],
        )
        self.assertNotIn(
            "escanteios_1t", resultado["componentes"]["mercados"]
        )

    def test_challenger_favoravel_nao_substitui_calibracao_reprovada(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["telegram"]["provas_oficiais"] = 0
        for mercado in MERCADOS_CALIBRADOS:
            evidencias["validacao"]["estado_calibracoes"][mercado].update({
                "ativa": False,
                "amostra": 100,
                "motivo": "pontuacao_sem_discriminacao",
                "amostra_validacao": 30,
                "roi_validacao_agregado": -0.12,
                "discriminacao_pontuacao": {
                    "auc": 0.40,
                    "limite_inferior_auc_95": 0.20,
                },
            })
        evidencias["validacao"]["pontuacao_sombra"].update({
            "mercados_prontos_para_revisao": ["gol_ft"],
            "por_mercado": {
                "gol_ft": {
                    "integro": True,
                    "estado": "favoravel_para_revisao",
                    "pronto_para_revisao": True,
                    "validacao": 30,
                    "aplicacao_automatica": False,
                },
            },
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])
        self.assertEqual(
            resultado["componentes"]["mercados"]["gol_ft"]["estado"],
            "reprovado_validacao",
        )
        self.assertFalse(resultado["pronto_profissional_completo"])

    def test_v2b_ft_ativo_aparece_separado_da_calibracao_antiga(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["metodos_grupo"] = {"v2b_ft_ativo": True}
        evidencias["validacao"][
            "validacao_grupo_gol_ft_capacidade_v2"
        ] = {"saudavel": True, "estado": "valida"}
        evidencias["validacao"][
            "progresso_grupo_gol_ft_capacidade_v2"
        ] = {
            "versao_avaliada": "gol-ft-capacidade-contextual-v2b",
            "registrado_em": "2026-08-26T21:01:14",
            "validos": 7,
            "greens": 5,
            "reds": 2,
            "roi": 0.12,
            "intervalo_roi_95": [-0.2, 0.44],
            "proximo_checkpoint": 20,
            "decisao_estatistica": "aguardando_amostra_futura",
            "rollback_recomendado": False,
        }
        evidencias["validacao"]["estado_calibracoes"]["gol_ft"].update({
            "ativa": False,
            "amostra": 100,
            "motivo": "pontuacao_sem_discriminacao",
            "amostra_validacao": 30,
        })

        resultado = avaliar_prontidao(evidencias)

        v2b = resultado["componentes"]["gol_ft_v2b_grupo"]
        self.assertEqual(v2b["estado"], "pronto")
        self.assertEqual(v2b["evidencias"]["validos"], 7)
        self.assertEqual(
            resultado["componentes"]["mercados"]["gol_ft"]["estado"],
            "pendente_amostra",
        )
        self.assertEqual(
            resultado["componentes"]["mercados"]["gol_ft"]
            ["evidencias"]["metodo_efetivo"],
            "gol-ft-capacidade-contextual-v2b",
        )
        self.assertEqual(
            resultado["componentes"]["mercados"]["gol_ft"]
            ["evidencias"]["metodo_legado"]["estado"],
            "reprovado_validacao",
        )

    def test_portfolio_ht_ativo_separa_legado_reprovado(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ht"].update({
            "ativa": False,
            "amostra": 100,
            "motivo": "faixas_sem_validacao",
            "amostra_validacao": 30,
            "roi_validacao_agregado": -0.19,
        })
        evidencias["portfolio_ht"] = {
            "capacidade_v1_legada_no_grupo": False,
            "promocao_automatica": False,
            "metodos": [{
                "identificador": "ht_00_min20",
                "versao": "gol-ht-00-min20-v3",
                "ativo": True,
                "candidatos": 54,
                "validos": 53,
                "greens": 32,
                "reds": 21,
                "pendentes": 1,
                "roi": 0.0889,
                "intervalo_roi_95": [-0.1549, 0.3326],
                "faltam": 46,
                "decisao_estatistica": "aguardando_amostra_futura",
                "linhagem_homogenea": True,
                "funil_candidatos": {
                    "estado": "sem_elegiveis",
                    "decisoes_gerador": 1,
                    "partidas_com_decisao": 1,
                    "partidas_com_alguma_decisao_elegivel": 0,
                    "gargalo_atual": "chutes_no_gol_insuficientes",
                },
            }],
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ht"]

        self.assertEqual(mercado["estado"], "pendente_amostra")
        self.assertEqual(
            mercado["evidencias"]["metodo_efetivo"],
            "portfolio-ht-prospectivo-v1",
        )
        self.assertEqual(
            mercado["evidencias"]["metodo_legado"]["estado"],
            "reprovado_validacao",
        )
        self.assertFalse(
            mercado["evidencias"]["capacidade_v1_legada_no_grupo"]
        )
        self.assertNotIn(
            "gol_ht", resultado["mercados_liberados_para_oficial"]
        )
        self.assertIn(
            {
                "requisito": "mercado:gol_ht",
                "estado": "pendente_amostra",
                "categoria": "aguardando_dados_reais",
            },
            resultado["pendencias"],
        )
        resumo = resumir_resultado_prontidao(resultado)
        funil = resumo["progresso_mercados"]["gol_ht"][
            "metodos_ativos"
        ][0]["funil_candidatos"]
        self.assertEqual(1, funil["decisoes_gerador"])
        self.assertEqual(
            "chutes_no_gol_insuficientes", funil["gargalo_atual"]
        )

    def test_portfolio_ft_preciso_substitui_prontidao_legada_sem_promover(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["portfolio_ft"] = {
            "mercado": "gol_ft",
            "metodos_ativos": [{
                "identificador": "ft_antecipado_2t_preciso",
                "versao_metodo": "filtro-gol-ft-antecipado-preciso-v2",
                "validador_prospectivo": {
                    "candidatos": 7,
                    "validos": 6,
                    "greens": 5,
                    "reds": 1,
                    "faltam": 53,
                    "decisao": "aguardando_amostra_futura",
                },
                "decisao": {
                    "estado": "aguardando_amostra",
                    "todos_satisfeitos": False,
                },
            }],
            "metodos_bloqueados": [],
            "metodo_base_legado": {"decisao": {"estado": "reprovado"}},
            "decisao": {
                "estado": "aguardando_amostra",
                "todos_satisfeitos": False,
                "promocao_automatica": False,
            },
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]

        self.assertEqual("pendente_amostra", mercado["estado"])
        self.assertEqual(
            "portfolio-ft-prospectivo-v1",
            mercado["evidencias"]["metodo_efetivo"],
        )
        self.assertEqual(
            "ft_antecipado_2t_preciso",
            mercado["evidencias"]["metodos_ativos"][0]["identificador"],
        )
        self.assertNotIn(
            "gol_ft", resultado["mercados_liberados_para_oficial"]
        )
        self.assertFalse(
            mercado["evidencias"]["promocao_automatica"]
        )
        resumo = resumir_resultado_prontidao(resultado)
        metodo = resumo["progresso_mercados"]["gol_ft"][
            "metodos_ativos"
        ][0]
        self.assertEqual(
            metodo["versao"], "filtro-gol-ft-antecipado-preciso-v2"
        )
        self.assertEqual(metodo["candidatos"], 7)
        self.assertEqual(metodo["validos"], 6)
        self.assertEqual(metodo["faltam"], 53)
        requisitos = {
            item["identificador"]: item
            for item in resumo["previsao_prontidao_operacional"][
                "requisitos_quantificados"
            ]
        }
        self.assertEqual(
            requisitos[
                "mercado:gol_ft:metodo:ft_antecipado_2t_preciso"
            ]["faltam_unidades_independentes"],
            53,
        )

    def test_portfolio_ht_concluido_sem_vantagem_continua_reprovado(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ht"].update({
            "ativa": False,
            "amostra": 100,
            "motivo": "faixas_sem_validacao",
            "amostra_validacao": 30,
        })
        evidencias["portfolio_ht"] = {
            "metodos": [{
                "identificador": "ht_00_min20",
                "versao": "gol-ht-00-min20-v3",
                "ativo": True,
                "candidatos": 100,
                "validos": 97,
                "faltam": 0,
                "roi": -0.04,
                "decisao_estatistica": "inconclusiva",
            }],
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(
            resultado["componentes"]["mercados"]["gol_ht"]["estado"],
            "reprovado_validacao",
        )

    def test_v2b_ft_so_fica_pronto_apos_validacao_prospectiva_favoravel(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["metodos_grupo"] = {"v2b_ft_ativo": True}
        evidencias["validacao"][
            "validacao_grupo_gol_ft_capacidade_v2"
        ] = {"saudavel": True, "estado": "valida"}
        evidencias["validacao"][
            "progresso_grupo_gol_ft_capacidade_v2"
        ] = {
            "versao_avaliada": "gol-ft-capacidade-contextual-v2b",
            "validos": 97,
            "candidatos_coorte": 100,
            "greens": 70,
            "reds": 27,
            "roi": 0.14,
            "intervalo_roi_95": [0.03, 0.25],
            "linhagem_homogenea": True,
            "decisao_estatistica": "favoravel_para_revisao_independente",
            "rollback_recomendado": False,
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]

        self.assertEqual("pronto", mercado["estado"])
        self.assertTrue(mercado["pronto"])
        self.assertIn(
            "gol_ft", resultado["mercados_liberados_para_oficial"]
        )

    def test_v2b_ft_negativo_pede_revisao_sem_fingir_falha_tecnica(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["metodos_grupo"] = {"v2b_ft_ativo": True}
        evidencias["validacao"][
            "validacao_grupo_gol_ft_capacidade_v2"
        ] = {"saudavel": True, "estado": "valida"}
        evidencias["validacao"][
            "progresso_grupo_gol_ft_capacidade_v2"
        ] = {
            "validos": 20,
            "greens": 6,
            "reds": 14,
            "roi": -0.31,
            "intervalo_roi_95": [-0.52, -0.10],
            "decisao_estatistica": "evidencia_desfavoravel",
            "rollback_recomendado": True,
        }

        resultado = avaliar_prontidao(evidencias)

        componente = resultado["componentes"]["gol_ft_v2b_grupo"]
        self.assertEqual(componente["estado"], "revisao_necessaria")
        self.assertEqual(
            resultado["componentes"]["mercados"]["gol_ft"]["estado"],
            "reprovado_validacao",
        )
        self.assertFalse(resultado["falha_tecnica_ativa"])
        self.assertIn(
            {
                "requisito": "gol_ft_v2b_grupo",
                "estado": "revisao_necessaria",
                "categoria": "modelo_reprovado",
            },
            resultado["pendencias"],
        )

    def test_v2b_ft_pausado_pelo_breaker_continua_classificado_como_modelo(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["metodos_grupo"] = {
            "v2b_ft_ativo": False,
            "controle_v2b_ft": {
                "saudavel": True,
                "ativo": False,
                "estado": "sombra_automatico",
            },
        }
        evidencias["validacao"][
            "validacao_grupo_gol_ft_capacidade_v2"
        ] = {"saudavel": True, "estado": "valida"}
        evidencias["validacao"][
            "progresso_grupo_gol_ft_capacidade_v2"
        ] = {
            "validos": 20, "greens": 6, "reds": 14,
            "roi": -0.31,
            "intervalo_roi_95": [-0.52, -0.10],
            "decisao_estatistica": "evidencia_desfavoravel",
            "rollback_recomendado": True,
        }

        resultado = avaliar_prontidao(evidencias)
        componente = resultado["componentes"]["gol_ft_v2b_grupo"]

        self.assertEqual(componente["estado"], "revisao_necessaria")
        self.assertFalse(componente["evidencias"]["ativo"])
        self.assertFalse(resultado["falha_tecnica_ativa"])

    def test_v2b_ft_com_ancora_inconsistente_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["metodos_grupo"] = {"v2b_ft_ativo": True}
        evidencias["validacao"][
            "validacao_grupo_gol_ft_capacidade_v2"
        ] = {"saudavel": False, "estado": "inconsistente"}
        evidencias["validacao"][
            "progresso_grupo_gol_ft_capacidade_v2"
        ] = {"rollback_recomendado": False}

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertEqual(
            resultado["componentes"]["gol_ft_v2b_grupo"]["estado"],
            "degradado",
        )

    def test_operacao_degradada_bloqueia_mercado_ja_calibrado(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["coleta"]["saudavel"] = False

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])
        self.assertEqual(
            resultado["componentes"]["operacao_continua"]["estado"],
            "degradado",
        )

    def test_marco_do_filtro_inconsistente_degrada_telegram_teste(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["experimento_filtro"] = {
            "saudavel": False,
            "estado": "ausente",
            "iniciado_em": None,
            "protegido": False,
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(
            resultado["componentes"]["filtro_simulacoes"]["estado"],
            "degradado",
        )
        self.assertEqual(
            resultado["componentes"]["telegram_teste"]["estado"],
            "degradado",
        )
        self.assertFalse(resultado["pronto_profissional_completo"])

    def test_filtro_integro_sem_amostra_nao_finge_validacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["conclusao_filtro_simulacoes"] = None
        evidencias["comparacao_filtro"]["comparacao"]["geral"].update({
            "estado": "amostra_insuficiente",
            "decisao": "aguardando_amostra",
            "decisoes_enviadas": 42,
            "decisoes_filtradas": 29,
            "resultados_resolvidos_enviadas": 40,
            "resultados_resolvidos_filtradas": 26,
            "pendentes_enviadas": 2,
            "pendentes_filtradas": 3,
            "amostra_enviadas": 38,
            "amostra_filtradas": 23,
            "intervalo_delta_taxa_acerto_95": None,
            "intervalo_delta_roi_95": None,
        })

        resultado = avaliar_prontidao(evidencias)

        filtro = resultado["componentes"]["filtro_simulacoes"]
        self.assertEqual(filtro["estado"], "pendente_amostra")
        self.assertEqual(filtro["evidencias"]["amostra_enviadas"], 38)
        self.assertEqual(filtro["evidencias"]["amostra_filtradas"], 23)
        self.assertEqual(filtro["evidencias"]["decisoes_enviadas"], 42)
        self.assertEqual(filtro["evidencias"]["decisoes_filtradas"], 29)
        self.assertEqual(filtro["evidencias"]["pendentes_enviadas"], 2)
        self.assertEqual(filtro["evidencias"]["pendentes_filtradas"], 3)
        self.assertEqual(
            filtro["evidencias"]["resultados_resolvidos_enviadas"], 40
        )
        self.assertEqual(
            filtro["evidencias"]["resultados_resolvidos_filtradas"], 26
        )
        self.assertTrue(
            resultado["componentes"]["telegram_teste"]["pronto"]
        )
        self.assertFalse(resultado["pronto_profissional_completo"])

    def test_filtro_concluido_sem_vantagem_nao_e_promovido(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencia_conclusao = {
            "estado": "avaliavel",
            "decisao": "nao_comprovado",
            "amostra_enviadas": 40,
            "amostra_filtradas": 35,
            "intervalo_delta_taxa_acerto_95": [-0.10, 0.15],
            "intervalo_delta_roi_95": [-0.20, 0.18],
        }
        evidencias["validacao"]["conclusao_filtro_simulacoes"].update({
            "decisao": "nao_comprovado",
            "evidencia": evidencia_conclusao,
        })

        resultado = avaliar_prontidao(evidencias)

        filtro = resultado["componentes"]["filtro_simulacoes"]
        self.assertEqual(filtro["estado"], "pronto")
        self.assertTrue(filtro["pronto"])
        self.assertTrue(filtro["evidencias"]["conclusao_congelada"])
        self.assertEqual(
            filtro["evidencias"]["resultado_experimento"],
            "concluido_sem_vantagem",
        )
        self.assertTrue(resultado["pronto_profissional_completo"])

    def test_experimento_de_ritmo_em_observacao_impede_prontidao_total(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["experimento_ritmo_packball"].update({
            "estado": "em_observacao",
            "minutos_observados": 30,
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertFalse(resultado["pronto_profissional_completo"])
        self.assertEqual(
            resultado["componentes"]["ritmo_packball"]["estado"],
            "pendente_validacao",
        )
        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])

    def test_ritmo_inseguro_degrada_operacao_continua(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["ritmo_acesso_packball"] = {
            "saudavel": False,
            "estado": "inseguro",
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertEqual(
            resultado["componentes"]["ritmo_packball"]["estado"],
            "degradado",
        )
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )

    def test_historico_drift_inconsistente_bloqueia_prontidao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["historico_drift"].update({
            "saudavel": False,
            "estado": "inconsistente",
            "chaves_atuais_ausentes": ["gol_ft:101"],
        })
        evidencias["historico_drift_watchdog"]["saudavel"] = False

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertFalse(
            resultado["componentes"]["historico_drift"]["pronto"]
        )
        self.assertEqual(
            resultado["componentes"]["historico_drift"]["evidencias"][
                "ausentes"
            ],
            ["gol_ft:101"],
        )
        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])

    def test_historico_drift_novo_aguarda_ciclo_sem_degradar_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["historico_drift"].update({
            "saudavel": False,
            "estado": "inconsistente",
            "chaves_atuais_ausentes": ["gol_ft:101"],
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertNotEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertTrue(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        historico = resultado["componentes"]["historico_drift"]
        self.assertEqual(historico["estado"], "sincronizando")
        self.assertTrue(
            historico["evidencias"]["sincronizacao"]["sincronizando"]
        )
        self.assertFalse(resultado["falha_tecnica_ativa"])
        self.assertFalse(resultado["pronto_profissional_completo"])

    def test_historico_drift_divergente_nunca_e_sincronizacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["historico_drift"].update({
            "saudavel": False,
            "estado": "inconsistente",
            "chaves_atuais_ausentes": ["gol_ft:101"],
            "chaves_atuais_divergentes": ["gol_ft:100"],
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertEqual(
            resultado["componentes"]["historico_drift"]["estado"],
            "degradado",
        )

    def test_historico_drift_com_watchdog_velho_degrada(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["historico_drift"].update({
            "saudavel": False,
            "estado": "inconsistente",
            "chaves_atuais_ausentes": ["gol_ft:101"],
        })
        evidencias["persistencia_estado_watchdog"]["persistido_em"] = (
            "2026-07-25T20:00:00"
        )

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertEqual(
            resultado["componentes"]["historico_drift"]["estado"],
            "degradado",
        )

    def test_diagnostico_sincronizacao_exige_watchdog_ativo(self):
        diagnostico = diagnosticar_sincronizacao_historico_drift(
            {
                "saudavel": False,
                "estado": "inconsistente",
                "chaves_atuais_ausentes": ["gol_ft:101"],
                "chaves_atuais_divergentes": [],
                "json_invalidos": 0,
                "chaves_duplicadas": 0,
            },
            {"saudavel": True, "estado": "integro", "chaves_atuais": 5},
            {"fresco": True},
            {"watchdog_ativo": False},
            {
                "saudavel": True,
                "estado": "persistido",
                "persistido_em": "2026-07-25T21:30:00",
            },
            agora=datetime.fromisoformat("2026-07-25T21:35:00"),
        )

        self.assertFalse(diagnostico["sincronizando"])

    def test_hipotese_sombra_mutavel_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["hipoteses_sombra"]["integridade"].update({
            "saudavel": False,
            "estado": "inconsistente",
            "protegido": False,
            "gatilhos_ausentes": [
                "trg_hipotese_sombra_update_imutavel"
            ],
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        self.assertEqual(
            resultado["componentes"]["hipoteses_sombra"]["estado"],
            "degradado",
        )

    def test_modelo_contextual_corrompido_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["pontuacao_contexto_sombra"].update({
            "integro": False,
            "mercados_com_modelo": ["gol_ft"],
        })
        evidencias["validacao"]["pontuacao_contexto_sombra"][
            "por_mercado"
        ]["gol_ft"] = {
            "integro": False,
            "estado": "modelo_invalido",
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        modelos = resultado["componentes"]["modelos_sombra"]
        self.assertEqual(modelos["estado"], "degradado")
        self.assertEqual(
            modelos["evidencias"][
                "mercados_contextuais_inconsistentes"
            ],
            ["gol_ft"],
        )

    def test_modelo_longo_corrompido_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["pontuacao_longa_sombra"].update({
            "integro": False,
            "mercados_com_modelo": ["gol_ft"],
        })
        evidencias["validacao"]["pontuacao_longa_sombra"][
            "por_mercado"
        ]["gol_ft"] = {
            "integro": False,
            "estado": "modelo_invalido",
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertFalse(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        modelos = resultado["componentes"]["modelos_sombra"]
        self.assertEqual(modelos["estado"], "degradado")
        self.assertFalse(
            modelos["evidencias"]["pontuacao_longa_integra"]
        )
        self.assertEqual(
            modelos["evidencias"]["mercados_longos_inconsistentes"],
            ["gol_ft"],
        )

    def test_historico_contextual_inconsistente_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["historico_avaliacao_contexto"].update({
            "saudavel": False,
            "estado": "inconsistente",
            "json_invalidos": [17],
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        contexto = resultado["componentes"]["historico_contexto"]
        self.assertEqual(contexto["estado"], "degradado")
        self.assertEqual(
            contexto["evidencias"]["json_invalidos"], [17]
        )

    def test_historico_drift_sem_resultados_e_pendencia_nao_falha_operacional(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["historico_drift"].update({
            "saudavel": True,
            "estado": "aguardando_resultados",
            "total": 0,
            "mercados": 0,
            "chaves_atuais": 0,
            "chaves_atuais_ausentes": [],
            "chaves_atuais_divergentes": [],
            "json_invalidos": 0,
            "chaves_duplicadas": 0,
        })

        resultado = avaliar_prontidao(evidencias)

        self.assertNotEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertTrue(
            resultado["componentes"]["operacao_continua"]["pronto"]
        )
        self.assertEqual(
            resultado["componentes"]["historico_drift"]["estado"],
            "pendente_amostra",
        )
        self.assertFalse(resultado["pronto_profissional_completo"])

    def test_estado_watchdog_sem_copia_sqlite_degrada_operacao(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["persistencia_estado_watchdog"] = {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "persistencia_estado_watchdog_falhou",
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertFalse(
            resultado["componentes"]["estado_watchdog_persistente"]["pronto"]
        )
        self.assertEqual(resultado["mercados_liberados_para_oficial"], [])

    def test_progresso_separa_resultados_modelo_e_sinais_pendentes(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ft"].update({
            "ativa": False,
            "amostra": 75,
            "motivo": "amostra_insuficiente",
        })
        evidencias["validacao"]["progresso_calibracao"]["gol_ft"] = {
            "amostra": 76,
            "faltam": 24,
        }
        evidencias["pendencias_resultados"]["por_mercado"]["gol_ft"] = 2

        resultado = avaliar_prontidao(evidencias)
        dados = resultado["componentes"]["mercados"]["gol_ft"]["evidencias"]

        self.assertEqual(dados["amostra"], 76)
        self.assertEqual(dados["resultados_resolvidos"], 76)
        self.assertEqual(dados["amostra_modelo"], 75)
        self.assertEqual(dados["sinais_pendentes"], 2)
        self.assertEqual(dados["faltam_resultados_reais"], 24)

    def test_corte_sombra_rejeitado_fica_visivel_sem_liberar_mercado(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ft"].update({
            "ativa": False,
            "amostra": 80,
            "motivo": "amostra_insuficiente",
        })
        evidencias["validacao"]["progresso_calibracao"]["gol_ft"] = {
            "amostra": 80,
            "faltam": 20,
        }
        evidencias["cortes_sombra"]["avaliacoes"]["gol_ft"] = {
            "estado": "avaliavel",
            "motivo": None,
            "apto_para_alterar_regra": False,
            "corte_escolhido_no_desenvolvimento": {
                "feature": "linha",
                "operador": "menor_igual",
                "limiar": 2.5,
            },
            "baseline_validacao": {
                "amostra": 24,
                "roi": -0.0113,
            },
            "metricas_validacao_corte": {
                "amostra": 14,
                "roi": -0.0364,
            },
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]

        self.assertEqual(mercado["estado"], "pendente_amostra")
        self.assertIn("sem vantagem futura", mercado["resumo"])
        self.assertFalse(
            mercado["evidencias"]["corte_sombra_apto"]
        )
        self.assertEqual(
            mercado["evidencias"]["corte_sombra_metricas_validacao"]["roi"],
            -0.0364,
        )
        self.assertNotIn(
            "gol_ft", resultado["mercados_liberados_para_oficial"]
        )

    def test_desempenho_negativo_pre_calibracao_fica_explicito(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ft"].update({
            "ativa": False,
            "amostra": 81,
            "motivo": "amostra_insuficiente",
        })
        evidencias["validacao"]["progresso_calibracao"]["gol_ft"] = {
            "amostra": 81,
            "faltam": 19,
        }
        evidencias["diagnostico_pre_calibracao"]["gol_ft"].update({
            "amostra": 81,
            "taxa_acerto": 0.543,
            "intervalo_acerto_95": [0.435, 0.647],
            "roi": -0.101,
            "lucro_unidades": -8.18,
            "discriminacao_pontuacao": {"auc": 0.519},
        })

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]

        self.assertEqual(mercado["estado"], "pendente_amostra")
        self.assertIn("desempenho atual negativo", mercado["resumo"])
        self.assertEqual(
            mercado["evidencias"][
                "diagnostico_pre_calibracao_estado"
            ],
            "desempenho_desfavoravel_pre_validacao",
        )
        self.assertEqual(
            mercado["evidencias"]["diagnostico_pre_calibracao_roi"],
            -0.101,
        )
        self.assertNotIn(
            "gol_ft", resultado["mercados_liberados_para_oficial"]
        )

    def test_amostra_completa_reprovada_nao_aparece_como_so_pendente(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ft"].update({
            "ativa": False,
            "amostra": 100,
            "motivo": "faixas_sem_validacao",
            "amostra_validacao": 30,
            "roi_validacao_agregado": -0.16,
            "auc_validacao": 0.68,
            "limite_inferior_auc_95": 0.55,
            "celulas_aprovadas": 0,
            "celulas_avaliadas": 1,
        })
        evidencias["validacao"]["progresso_calibracao"]["gol_ft"] = {
            "amostra": 100,
            "faltam": 0,
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]

        self.assertEqual(mercado["estado"], "reprovado_validacao")
        self.assertTrue(
            mercado["evidencias"]["validacao_final_realizada"]
        )
        self.assertEqual(
            mercado["evidencias"]["roi_validacao_agregado"], -0.16
        )
        self.assertEqual(
            mercado["evidencias"]["auc_validacao"], 0.68
        )
        self.assertEqual(
            mercado["evidencias"]["celulas_aprovadas"], 0
        )
        self.assertNotIn(
            "gol_ft", resultado["mercados_liberados_para_oficial"]
        )

    def test_reprovacao_por_classes_desbalanceadas_conta_como_validacao_final(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"]["gol_ft"].update({
            "ativa": False,
            "amostra": 100,
            "motivo": "resultados_desbalanceados",
            "amostra_validacao": 0,
            "roi_validacao_agregado": None,
            "auc_validacao": None,
        })
        evidencias["validacao"]["progresso_calibracao"]["gol_ft"] = {
            "amostra": 100,
            "faltam": 0,
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["gol_ft"]

        self.assertEqual(mercado["estado"], "reprovado_validacao")
        self.assertTrue(
            mercado["evidencias"]["validacao_final_realizada"]
        )
        self.assertEqual(
            mercado["evidencias"]["motivo"],
            "resultados_desbalanceados",
        )

    def test_rollback_seguro_pode_ser_considerado_regime_pronto(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["experimento_ritmo_packball"][
            "estado"
        ] = "rollback_acionado"

        resultado = avaliar_prontidao(evidencias)

        self.assertTrue(resultado["pronto_profissional_completo"])
        self.assertEqual(
            resultado["componentes"]["ritmo_packball"]["estado"], "pronto"
        )

    def test_gol_ft_expoe_protecao_contra_sobreajuste(self):
        resultado = avaliar_prontidao(evidencias_prontas())
        evidencias = resultado["componentes"]["mercados"]["gol_ft"][
            "evidencias"
        ]
        self.assertEqual(
            evidencias["controle_sobreajuste_estado"],
            "nenhum_corte_exploratorio_comprovado",
        )
        self.assertEqual(evidencias["controle_sobreajuste_testes"], 826)
        self.assertEqual(evidencias["controle_sobreajuste_bonferroni"], 0)
        self.assertFalse(evidencias["promocao_retroativa_permitida"])
        self.assertTrue(evidencias["exige_validacao_prospectiva"])

    def test_proximo_gol_expoe_challenger_balanceado_separadamente(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"]["estado_calibracoes"][
            "proximo_gol"
        ].update({
            "ativa": False,
            "amostra": 8,
            "motivo": "amostra_insuficiente",
        })
        evidencias["validacao"]["progresso_calibracao"][
            "proximo_gol"
        ] = {"amostra": 8, "faltam": 92}
        evidencias["validacao"][
            "progresso_proximo_gol_balanceado_sombra"
        ] = {
            "versao": "validacao-proximo-gol-balanceado-sombra-v3",
            "regra_versao": "sinais-v10i-balanceado",
            "estado": "coletando",
            "decisao": "aguardando_amostra_futura",
            "candidatos": 3,
            "tamanho_coorte": 40,
            "validos": 2,
            "greens": 1,
            "reds": 1,
            "pendentes": 1,
            "faltam": 37,
            "roi": -0.1,
            "intervalo_roi_95": [-1.0, 0.8],
            "alerta_desfavoravel": False,
            "resultados_completos": False,
            "checkpoint_seguranca": {"validos": 2},
            "funil_origem_v10f": {"candidatos_por_24h": 1.5},
        }
        evidencias["metodos_grupo"] = {
            "proximo_gol_balanceado_ativo": True,
            "proximo_gol_balanceado_sombra_ativo": True,
            "controle_proximo_gol_balanceado": {
                "saudavel": True,
                "ativo": True,
                "estado": "ativo_padrao",
            },
        }

        resultado = avaliar_prontidao(evidencias)
        mercado = resultado["componentes"]["mercados"]["proximo_gol"]

        self.assertEqual("pendente_amostra", mercado["estado"])
        self.assertEqual(
            "portfolio-proximo-gol-prospectivo-v1",
            mercado["evidencias"]["metodo_efetivo"],
        )
        challenger = mercado["evidencias"]["challenger_balanceado"]
        self.assertEqual(3, challenger["candidatos"])
        self.assertEqual(40, challenger["tamanho_coorte"])
        self.assertTrue(challenger["grupo_teste_ativo"])
        self.assertFalse(challenger["telegram_oficial"])

        resumo = resumir_resultado_prontidao(resultado)
        resumo_challenger = resumo["progresso_mercados"][
            "proximo_gol"
        ]["challenger_balanceado"]
        self.assertEqual(3, resumo_challenger["candidatos"])
        self.assertEqual("ativo_padrao", resumo_challenger[
            "controle_operacional"
        ]["estado"])

    def test_challenger_sombra_nao_rebaixa_regra_oficial_pronta(self):
        evidencias = copy.deepcopy(evidencias_prontas())
        evidencias["validacao"][
            "progresso_proximo_gol_balanceado_sombra"
        ] = {
            "versao": "validacao-proximo-gol-balanceado-sombra-v3",
            "estado": "coletando",
            "decisao": "aguardando_amostra_futura",
            "candidatos": 0,
            "tamanho_coorte": 40,
        }
        evidencias["metodos_grupo"] = {
            "proximo_gol_balanceado_ativo": True,
            "proximo_gol_balanceado_sombra_ativo": True,
            "controle_proximo_gol_balanceado": {
                "saudavel": True,
                "ativo": True,
                "estado": "ativo_padrao",
            },
        }

        resultado = avaliar_prontidao(evidencias)

        self.assertTrue(
            resultado["componentes"]["mercados"]["proximo_gol"]["pronto"]
        )
        self.assertIn("proximo_gol", resultado[
            "mercados_liberados_para_oficial"
        ])


class ResumoProntidaoProfissionalTest(unittest.TestCase):
    def test_resume_pendencias_e_progresso_sem_perder_contexto(self):
        resultado = avaliar_prontidao(evidencias_prontas())

        resumo = resumir_resultado_prontidao(resultado)

        self.assertEqual(resumo["estado_geral"], "profissional_completo")
        self.assertFalse(resumo["falha_tecnica_ativa"])
        self.assertEqual(resumo["pendencias_total"], 0)
        self.assertEqual(
            set(resumo["progresso_mercados"]),
            set(resultado["mercados_exigidos"]),
        )
        self.assertEqual(resumo["scanner_packball"]["estado"], "pronto")
        self.assertEqual(
            resumo["worker_treino_isolado"]["estado"], "pronto"
        )
        self.assertEqual(
            resumo["worker_treino_isolado"]["tentativas"], 1
        )
        self.assertEqual(
            "pronto", resumo["exposicao_coleta_prospectiva"]["estado"]
        )
        self.assertEqual(
            4, resumo["exposicao_coleta_prospectiva"]["coortes"]
        )
        self.assertEqual(
            resumo["scanner_packball"][
                "duracao_total_sem_prioridade_segundos"
            ],
            311.0,
        )

    def test_scanner_persistente_degradado_reprova_operacao(self):
        evidencias = evidencias_prontas()
        evidencias["validacao"]["prioridade_scanner_packball"].update({
            "saudavel": False,
            "estado": "degradado",
            "ciclos_sem_prioridade_consecutivos": 3,
            "duracao_sem_prioridade_segundos": 120.0,
        })

        resultado = avaliar_prontidao(evidencias)
        resumo = resumir_resultado_prontidao(resultado)

        self.assertEqual(resultado["estado_geral"], "operacao_degradada")
        self.assertEqual(
            resultado["componentes"]["prioridade_scanner_packball"][
                "estado"
            ],
            "degradado",
        )
        self.assertFalse(resumo["scanner_packball"]["pronto"])
        self.assertEqual(
            resumo["scanner_packball"][
                "duracao_sem_prioridade_segundos"
            ],
            120.0,
        )

    def test_inclui_resumo_humano_da_pendencia(self):
        resultado = avaliar_prontidao(evidencias_prontas())
        resultado["componentes"]["backup_fora_dispositivo"].update({
            "estado": "aguardando_autorizacao",
            "pronto": False,
            "resumo": "aguardando escolha do disco externo pelo usuario",
        })
        resultado["pendencias"] = [{
            "requisito": "backup_fora_dispositivo",
            "estado": "aguardando_autorizacao",
            "categoria": "dependencia_externa",
        }]
        resultado["pendencias_por_categoria"] = {"dependencia_externa": 1}

        resumo = resumir_resultado_prontidao(resultado)

        self.assertEqual(resumo["pendencias_total"], 1)
        self.assertEqual(
            resumo["pendencias"][0]["resumo"],
            "aguardando escolha do disco externo pelo usuario",
        )


if __name__ == "__main__":
    unittest.main()
