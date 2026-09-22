import copy
import json
import math
import os
import sys
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from api_football import APIFootball, diagnosticar_associacao
from acompanhamento_odd import (
    FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS,
    VERSAO_MATERIALIZACAO_RAPIDA,
    avaliar_rechecagem_odd_api,
    extrair_odd_exata_acompanhamento,
    finalizar_acompanhamento_odd,
    mercado_acompanhamento_odd_autorizado,
    preparar_acompanhamento_odd,
    validar_contrato_mercado_oferta,
    validar_identidade_evento_oferta,
)
from acompanhamento_metodos_gols import (
    IDADE_MAXIMA_REANALISE_SEGUNDOS,
    gerar_acompanhamentos_metodos_gols,
    revalidar_metodo_acompanhado,
)
from avaliacao_acompanhamento_odd import (
    VERSAO as VERSAO_AVALIACAO_ACOMPANHAMENTO_ODD,
    avaliar_estrategia_acompanhamento_odd,
)
from avaliacao_desajuste_odds import (
    VERSAO as VERSAO_AVALIACAO_DESAJUSTE_ODDS,
    avaliar_desajustes_odds,
)
from avaliacao_prioridade_ligas_gols import (
    VERSAO as VERSAO_AVALIACAO_PRIORIDADE_LIGAS,
    avaliar_prioridade_ligas_gols,
)
from avaliacao_probabilidade_individual import (
    VERSAO as VERSAO_AVALIACAO_PROBABILIDADE_INDIVIDUAL,
    avaliar_probabilidade_individual,
)
from avaliacao_portfolio_edge import avaliar_candidato_oficial
from avaliacao_quarentena_fallback_ht import (
    VERSAO as VERSAO_AVALIACAO_QUARENTENA_HT,
    avaliar_quarentena_fallback_ht,
)
from agendador_coleta import AgendadorColeta
from agendador_thestatsapi import planejar_coleta_thestatsapi
from backtest import AvaliadorBacktest, reabrir_resultados_provisorios
from backup_banco import BackupBanco
from betsapi import BetsAPI
from banco import BancoMonitor
from clv_pos_alerta import (
    MERCADOS_CLV_API_RAPIDA,
    MERCADOS_CLV_SOMENTE_SNAPSHOT,
    VERSAO_COLETA_CLV_API_RAPIDA,
    modo_coleta_estado_clv,
)
from carteira_operacional import registrar_carteira_operacional
from calibracao import CalibradorBacktest
from coletor_odds import coletar_odds
from coletor_packball import ColetorPackBall, PackBallListaNaoValidadaError
from configuracao import validar_configuracao
from conectividade import VerificadorConectividade
from controle_acesso_packball import (
    ControleAcessoPackBall,
    PackBallBloqueadoError,
    PackBallPausaPreventivaError,
)
from controle_sistema import ler_modo_manutencao
from custodia_avaliacao import (
    ESTADO_CONCLUIDO as ESTADO_AVALIACAO_CONCLUIDO,
    ESTADO_EM_ANDAMENTO as ESTADO_AVALIACAO_EM_ANDAMENTO,
    ESTADO_FALHA as ESTADO_AVALIACAO_FALHA,
    VERSAO_CUSTODIA as VERSAO_CUSTODIA_AVALIACAO,
    aplicar_efeitos_desativados,
    construir_estado_nao_concluido,
)
from exposicao_coleta_prospectiva import (
    enriquecer_avaliacao_com_exposicao,
)
from evolucao import (
    HistoricoTemporal,
    extrair_par,
    formatar_delta,
    periodo_partida,
)
from historico_api_live import (
    comparar_evolucoes_packball_api,
    normalizar_snapshot_api_live,
    obter_evolucao_api_live,
    resumir_historico_api_live,
)
from integracao_thestatsapi_sombra import (
    adaptar_lista_thestatsapi_para_associador,
    diagnosticar_associacao_thestatsapi,
    normalizar_live_stats_thestatsapi,
    normalizar_odds_live_thestatsapi,
    resumir_cobertura_thestatsapi,
)
from exploracao_sombra import (
    gerar_exploracoes_sombra,
    registrar_ou_validar_definicao_gol_ft_v2_controle,
    registrar_ou_validar_definicao_exploracao_gol_ft_v3,
    registrar_ou_validar_definicao_exploracao_gols,
    registrar_ou_validar_politica_gol_ft_v2_controle,
    registrar_ou_validar_politica_avaliacao_gol_ft_v3,
    registrar_ou_validar_politica_avaliacao_gols,
)
from challenger_v2_ft import (
    TAMANHO_COORTE_CHALLENGER_V2_FT,
    VERSAO_CHALLENGER_V2_FT,
    registrar_ou_validar_challenger_v2_ft,
)
from finalizador_resultados import (
    FinalizadorPendenciasSemDado,
    FinalizadorResultadosAPI,
    FinalizadorResultadosPackBall,
)
from fallback_indicadores_lista import (
    auditar_janelas_temporais_lista,
    complementar_estatisticas_com_lista,
    fundir_janelas_temporais_lista_como_fallback,
    marcar_dependencia_fallback_temporal_lista,
    resumir_auditoria_temporal_sqlite,
)
from mercados import (
    MERCADOS_CALIBRADOS,
    escanteios_asiaticos_periodos_ativos,
    filtrar_mercados_operacionais,
)
from melhor_preco_sombra import anexar_melhor_preco_sombra
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS, gerar_candidatos
from linhagem_regras import (
    registrar_inicio_linhagem_sinais,
    registrar_ou_validar_linhagem_regra,
)
from movimento_odds import calcular_movimento_odds
from observabilidade import Observabilidade, resumir_erro_seguro
from packball_login import (
    _storage_state_completo,
    autenticar_pagina,
    fazer_login,
    sincronizar_storage_state,
)
from qualidade_dados import avaliar_qualidade, extrair_minuto, extrair_placar
from valor_mercado import anexar_par_odds_sincronizado
from validacao_resultado_valor_justo import (
    STATUS_ELEGIVEIS as STATUS_VALOR_JUSTO_ELEGIVEIS,
    mercados_com_candidato_sincronizado,
)
from contexto_pre_jogo import (
    comparar_estatisticas_ao_vivo,
    resumir_estatisticas_api_ao_vivo,
    resumir_eventos_api_ao_vivo,
    resumir_jogadores_api_ao_vivo,
)
from processo_monitor import (
    TravaInstancia,
    garantir_watchdog_ativo,
    gravar_json_atomico,
    hash_codigo_runtime,
    registrar_estado,
)
from prioridade_pre_live_ao_vivo import aplicar_prioridade_pre_live
from prioridade_ligas_gols import (
    coletar_taxas_ligas_packball,
    priorizar_tarefas_por_ligas,
)
from politica_escanteios_ft import aplicar_politicas_por_mercado
from politica_gol_ht import aplicar_politica_gol_ht
from politica_gols_tempo import aplicar_politica_gols_tempo
from politica_proximo_gol_preciso import aplicar_politica_proximo_gol
from proximo_gol_balanceado_sombra import (
    gerar as gerar_proximo_gol_balanceado_sombra,
    registrar_ou_validar_definicao as registrar_ou_validar_proximo_gol_balanceado_sombra,
)
from proveniencia_odds import (
    BLOQUEIOS_PROVENIENCIA,
    CHAVE_ESTADO_COTACAO_ENTRADA,
    ESTADO_COTACAO_CONGELADA,
    IDADE_ODD_MAXIMA_SEGUNDOS,
    aplicar_proveniencia_odds,
    validar_cotacao_executavel_oficial,
)
from retencao import rotacionar_arquivo
from telegram_alertas import (
    AlertasTelegram,
    PROBABILIDADE_MINIMA,
    candidato_v2_controle_grupo_teste,
    candidato_experimento_grupo_teste,
    candidato_top_criterio_grupo_teste,
    motivo_suspensao_simulacao,
)
from trabalhador_acompanhamento_odd import (
    TrabalhadorAcompanhamentoOdd,
)

from fusao_packball_thestats import (
    fundir_estatisticas_packball_thestats,
    marcar_candidatos_dependentes_fusao,
)
from consenso_multifonte_sombra import (
    VERSAO_CONSENSO_MULTIFONTE_SOMBRA,
    estatisticas_do_consenso,
    isolar_candidatos_consenso,
    registrar_ou_validar_consenso_multifonte,
    validar_consenso_multifonte,
)
from gols_antecipados import (
    elegivel_para_enriquecimento_antecipado,
    gerar_gols_antecipados,
)
from gols_capacidade_times import (
    elegivel_para_enriquecimento_capacidade,
    gerar_gols_capacidade_times,
)
from gols_capacidade_contextual_v2 import (
    coletar_contexto_capacidade_v2,
    elegivel_para_enriquecimento_v2,
    gerar_gols_capacidade_contextual_v2,
)
from contexto_periodos_10 import coletar_contexto_periodos_10
from contexto_linhas_gols import coletar_contexto_linhas_gols
from protecao_conversao_gols import aplicar_protecao_conversao_gols
from tendencias_packball_ligas import (
    VERSAO as VERSAO_TENDENCIAS_PACKBALL,
    aplicar_protecao_tendencias_packball,
    periodo_atual as periodo_tendencia_packball,
)
from gol_ht_00_min20 import (
    elegivel_para_contexto as elegivel_gol_ht_00_min20,
    gerar_gol_ht_00_min20,
)
from gol_ft_tendencia_mais_um import (
    elegivel_para_contexto as elegivel_gol_ft_tendencia_mais_um,
    gerar_gol_ft_tendencia_mais_um,
)
from gol_2t_pos_ht_red import (
    VERSAO as VERSAO_GOL_2T_POS_HT_RED,
    gerar_gol_2t_pos_ht_red,
)
from diagnostico_gols_antecipados import diagnosticar_gols_antecipados
from diagnostico_gols_capacidade_contextual_v2 import (
    diagnosticar_gols_capacidade_contextual_v2,
)
from resgate_qualidade_api import (
    avaliar_resgate_qualidade_api,
    elegivel_coleta_resgate_qualidade,
)
from validacao_gols_antecipados import (
    registrar_ou_validar_gols_antecipados,
)
from validacao_gol_ht_antecipado_preciso import (
    registrar_ou_validar_definicao as registrar_ou_validar_filtro_ht_preciso,
    sincronizar_coorte as sincronizar_coorte_filtro_ht_preciso,
)
from validacao_gol_ft_antecipado_preciso import (
    registrar_ou_validar_definicao as registrar_ou_validar_filtro_ft_preciso,
    sincronizar_coorte as sincronizar_coorte_filtro_ft_preciso,
)
from validacao_quase_candidatos_gol_ft import (
    registrar_ou_validar_definicao as registrar_ou_validar_quase_gol_ft,
    sincronizar_coorte as sincronizar_coorte_quase_gol_ft,
)
from validacao_escanteios_ft_asiatico_prospectiva import (
    registrar_ou_validar_definicao as registrar_ou_validar_escanteios_ft_legado,
    sincronizar_coorte as sincronizar_coorte_escanteios_ft_legado,
)
from validacao_escanteios_ft_asiatico_executavel import (
    registrar_ou_validar_definicao as registrar_ou_validar_escanteios_ft,
    sincronizar_coorte as sincronizar_coorte_escanteios_ft,
)
from validacao_quase_candidatos_proximo_gol import (
    registrar_ou_validar_definicao as registrar_ou_validar_quase_proximo_gol,
    sincronizar_coorte as sincronizar_coorte_quase_proximo_gol,
)
from validacao_gols_capacidade_times import (
    registrar_ou_validar_gols_capacidade_times,
)
from validacao_gols_capacidade_contextual_v2 import (
    registrar_ou_validar_grupo_ft_capacidade_contextual_v2,
    registrar_ou_validar_gols_capacidade_contextual_v2,
)
from validacao_gol_ht_00_min20 import (
    registrar_ou_validar_gol_ht_00_min20,
)
from validacao_gol_ft_reforcado_sombra import (
    registrar_ou_validar_gol_ft_reforcado,
)
from validacao_gol_ht_protegido_sombra import (
    registrar_ou_validar_gol_ht_protegido,
)
from validacao_gol_ft_tendencia_mais_um import (
    registrar_ou_validar_gol_ft_tendencia_mais_um,
)
from top_criterios_gols import gerar_top_criterio_ft, gerar_top_criterio_ht
from validacao_top_criterios_gols import (
    registrar_ou_validar_top_criterios_gols,
)
from fusao_temporal_api_live import (
    fundir_evolucao_temporal_como_fallback,
    fusao_temporal_grupo_ativa,
    gerar_candidatos_fusao_temporal,
)
from roteador_odds_thestatsapi import (
    converter_odds_bet365_contrato_interno,
    validar_gate_operacional_thestatsapi,
)
from thestatsapi import TheStatsAPI
from the_odds_api import TheOddsAPI
from versoes_gol_ft_reforcado import (
    versao_regra_operacional,
    versoes_regras_operacionais,
)
from politica_gol_ft_reforcado import aplicar_politica_gol_ft_reforcado
from politica_gol_ht_protegido import aplicar_politica_gol_ht_protegido


INTERVALO_SEGUNDOS = 90
ORCAMENTO_COLETA_DETALHADA_SEGUNDOS = 180
ORCAMENTO_COLETA_DETALHADA_ADAPTATIVO_SEGUNDOS = 225
MAXIMO_DETALHES_PACKBALL_ADAPTATIVO = 5
ORCAMENTO_TRIAGEM_CAPACIDADE_SEGUNDOS = 270
MAXIMO_DETALHES_TRIAGEM_CAPACIDADE = 7
VERSAO_AUDITORIA_BLOQUEIOS = "auditoria-bloqueios-promissores-v1"
INTERVALO_BACKUP_PERIODICO_HORAS = 6
JANELA_DURACOES_TAREFAS = 30
PERCENTIL_RESERVA_TAREFA = 0.90
MARGEM_RESERVA_TAREFA_SEGUNDOS = 3.0
LIMIAR_ALTA_CARGA_AO_VIVO = 15
LIMITE_FINALIZACOES_PACKBALL_ALTA_CARGA = 1
MINIMO_RESERVA_TAREFA_SEGUNDOS = 10.0
MINUTO_MAXIMO_PRIORIDADE_SINAIS = 86
MINUTO_MAXIMO_PRIORIDADE_LIGAS_GOLS = 82
JANELA_PAREAMENTOS_API_PAUSA_HORAS = 2
JANELA_PRIORIDADE_THE_STATS_API_MINUTOS = 5
LIMITE_ATRASO_CRITICO_SEGUNDOS = 20 * 60


class ManutencaoSolicitadaError(RuntimeError):
    """Interrompe o ciclo somente em um ponto cooperativo e seguro."""


class ServicoMonitor:
    def _separar_filas_operacionais(self, tarefas):
        """Mantem urgentes na frente sem apagar a ordem tecnica interna."""
        tarefas = list(tarefas or [])
        ativa = os.getenv(
            "PACKBALL_FILAS_OPERACIONAIS_ATIVAS", "0"
        ) == "1"
        grupos = {
            "urgente": [],
            "acompanhamento": [],
            "exploracao": [],
        }
        for ordem, tarefa in enumerate(tarefas):
            jogo = tarefa.get("jogo") or {}
            minuto = extrair_minuto(jogo.get("status"))
            try:
                radar = float(
                    tarefa.get("pontuacao_indicadores_lista") or 0
                )
            except (TypeError, ValueError):
                radar = 0.0
            acionavel = tarefa.get("acionavel_fila_detalhada") is True
            rechecagem = bool(tarefa.get("rechecagem_pos_evento"))
            urgente = bool(
                rechecagem
                or tarefa.get("pre_live_confirmado")
                or (tarefa.get("em_foco") and acionavel)
                or (
                    acionavel
                    and minuto is not None
                    and 10 <= minuto <= 28
                    and radar >= 50.0
                )
            )
            acompanhamento = bool(
                not urgente
                and (
                    tarefa.get("prioridade") == "rapida"
                    or tarefa.get("pre_live_prioritario")
                    or tarefa.get("janelas_temporais_projetadas")
                    or tarefa.get("prioridade_exploracao_gols")
                    or tarefa.get("idade_segundos") is not None
                )
            )
            fila = (
                "urgente" if urgente
                else "acompanhamento" if acompanhamento
                else "exploracao"
            )
            tarefa["fila_operacional"] = fila
            tarefa["ordem_antes_filas"] = ordem
            grupos[fila].append(tarefa)

        if ativa:
            grupos["urgente"].sort(key=lambda item: (
                not bool(item.get("rechecagem_pos_evento")),
                not bool(item.get("pre_live_confirmado")),
                not bool(item.get("em_foco")),
                item.get("ordem_antes_filas", 10**9),
            ))
            ordenadas = (
                grupos["urgente"]
                + grupos["acompanhamento"]
                + grupos["exploracao"]
            )
        else:
            ordenadas = tarefas

        # Esta é a ordem final entregue ao navegador. A separação por filas
        # pode acontecer depois da priorização técnica e, em carga alta,
        # empurrar novamente a melhor liga sazonal para fora do lote real.
        # Reserva uma única vaga no top 4 sem tocar na primeira urgência.
        liga_gols_reservada_final = None
        if len(ordenadas) >= LIMIAR_ALTA_CARGA_AO_VIVO:
            def score_liga_gols(item):
                try:
                    valor = float(item.get("prioridade_liga_gols") or 0)
                except (TypeError, ValueError):
                    return 0.0
                return valor if math.isfinite(valor) and valor > 0 else 0.0

            candidatas_liga = [
                item for item in ordenadas
                if item.get("acionavel_fila_detalhada") is True
                and score_liga_gols(item) > 0
                and (
                    extrair_minuto(
                        (item.get("jogo") or {}).get("status")
                    ) is None
                    or extrair_minuto(
                        (item.get("jogo") or {}).get("status")
                    ) <= MINUTO_MAXIMO_PRIORIDADE_LIGAS_GOLS
                )
            ]
            if candidatas_liga:
                melhor_liga = max(
                    candidatas_liga,
                    key=lambda item: (
                        score_liga_gols(item),
                        float(item.get("pontuacao_indicadores_lista") or 0),
                        -item.get("ordem_antes_filas", 10**9),
                    ),
                )
                if melhor_liga not in ordenadas[:4]:
                    ordenadas.remove(melhor_liga)

                    def protecao(item):
                        return (
                            5 if item.get("rechecagem_pos_evento") else
                            5 if item.get("pre_live_confirmado") else
                            4 if item.get("fila_operacional") == "urgente" else
                            3 if item.get("em_foco") else
                            2 if item.get("pre_live_prioritario") else
                            2 if item.get("janelas_temporais_projetadas") else
                            1
                        )

                    faixa = list(range(1, min(4, len(ordenadas))))
                    posicao = min(
                        faixa,
                        key=lambda indice: (
                            protecao(ordenadas[indice]), -indice
                        ),
                    )
                    ordenadas.insert(posicao, melhor_liga)
                    melhor_liga["reserva_liga_gols_final"] = True
                    liga_gols_reservada_final = melhor_liga

        return ordenadas, {
            "ativa": ativa,
            "urgentes": len(grupos["urgente"]),
            "acompanhamento": len(grupos["acompanhamento"]),
            "exploracao": len(grupos["exploracao"]),
            "urgentes_nas_quatro_primeiras": sum(
                item.get("fila_operacional") == "urgente"
                for item in ordenadas[:4]
            ),
            "liga_gols_reservada_final": (
                liga_gols_reservada_final is not None
            ),
            "liga_gols_reservada_final_score": (
                score_liga_gols(liga_gols_reservada_final)
                if liga_gols_reservada_final is not None else None
            ),
            "liga_gols_reservada_final_nas_quatro_primeiras": bool(
                liga_gols_reservada_final is not None
                and liga_gols_reservada_final in ordenadas[:4]
            ),
            "liga_gols_minuto_maximo_reserva": (
                MINUTO_MAXIMO_PRIORIDADE_LIGAS_GOLS
            ),
            "rollback": "PACKBALL_FILAS_OPERACIONAIS_ATIVAS=0",
        }

    def _aplicar_triagem_capacidade(self, tarefas):
        """Reduz a fila ampla e troca a aba de odds por API quando seguro.

        A ordem calculada pelo agendador continua sendo a autoridade. O teste
        apenas limita o backlog detalhado e usa a cobertura global cacheada da
        BetsAPI para evitar uma segunda navegacao PackBall no mesmo jogo.
        """
        tarefas = list(tarefas or [])
        ativa = str(
            os.getenv("PACKBALL_TRIAGEM_CAPACIDADE_ATIVA", "0")
        ).strip().casefold() in {"1", "true", "sim", "yes", "on"}
        diagnostico = {
            "ativa": ativa,
            "tarefas_entrada": len(tarefas),
            "tarefas_selecionadas": len(tarefas),
            "tarefas_fora_lista_curta": 0,
            "cobertura_betsapi": 0,
            "odds_api_prioritarias": 0,
            "rollback": "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA=0",
        }
        if not ativa or not tarefas:
            diagnostico["motivo"] = (
                "flag_desativada" if not ativa else "fila_vazia"
            )
            return tarefas, diagnostico

        try:
            limite = int(os.getenv("PACKBALL_TRIAGEM_MAX_JOGOS", "28"))
        except (TypeError, ValueError):
            limite = 28
        limite = min(max(limite, MAXIMO_DETALHES_TRIAGEM_CAPACIDADE), 80)

        cliente = getattr(self, "betsapi", None)
        cobertura = {}
        diagnostico_betsapi = {
            "ativa": False,
            "motivo": "cliente_indisponivel",
        }
        consultar_cobertura = getattr(
            cliente, "cobertura_jogos_ao_vivo", None
        )
        if callable(consultar_cobertura):
            try:
                diagnostico_betsapi = consultar_cobertura(
                    [tarefa.get("jogo") or {} for tarefa in tarefas],
                ) or {}
                cobertura = dict(
                    diagnostico_betsapi.get("cobertura_por_url") or {}
                )
            except Exception as erro:
                diagnostico_betsapi = {
                    "ativa": bool(getattr(cliente, "ativa", False)),
                    "motivo": "falha_isolada",
                    "erro": type(erro).__name__,
                }

        for tarefa in tarefas:
            url = str((tarefa.get("jogo") or {}).get("url") or "")
            tarefa["betsapi_cobertura_ao_vivo"] = url in cobertura

        resgates = set(getattr(
            self, "_resgate_odds_packball_urls", set()
        ) or set())
        for tarefa in tarefas:
            url = str((tarefa.get("jogo") or {}).get("url") or "")
            tarefa["resgate_odds_packball"] = bool(url in resgates)

        # As quatro primeiras posicoes carregam reservas deliberadas de foco,
        # HT, historico temporal e pre-live. Depois delas, cobertura de odds
        # sobe sem apagar a ordem tecnica ja calculada.
        prefixo = tarefas[:4]
        restante = tarefas[4:]
        restante = sorted(
            enumerate(restante),
            key=lambda par: (
                not bool(par[1].get("resgate_odds_packball")),
                not bool(par[1].get("betsapi_cobertura_ao_vivo")),
                par[0],
            ),
        )
        ordenadas = prefixo + [item for _, item in restante]

        selecionadas = list(ordenadas[:limite])
        ids_selecionados = {id(item) for item in selecionadas}
        # Nunca corta um foco/recheck/pre-live que o motor ja declarou
        # prioritario. Esses casos sao poucos e podem exceder o teto nominal.
        for tarefa in ordenadas[limite:]:
            protegida = bool(
                tarefa.get("em_foco")
                or tarefa.get("rechecagem_pos_evento")
                or tarefa.get("pre_live_confirmado")
                or tarefa.get("pre_live_prioritario")
            )
            if protegida and id(tarefa) not in ids_selecionados:
                selecionadas.append(tarefa)
                ids_selecionados.add(id(tarefa))

        for tarefa in selecionadas:
            url = str((tarefa.get("jogo") or {}).get("url") or "")
            tarefa["odds_api_prioritaria"] = bool(
                tarefa.get("coletar_odds")
                and tarefa.get("betsapi_cobertura_ao_vivo")
                and url not in resgates
            )

        diagnostico.update({
            "motivo": "lista_curta_aplicada",
            "limite_nominal": limite,
            "tarefas_selecionadas": len(selecionadas),
            "tarefas_fora_lista_curta": max(
                len(tarefas) - len(selecionadas), 0
            ),
            "protegidas_fora_teto": max(len(selecionadas) - limite, 0),
            "cobertura_betsapi": sum(
                bool(item.get("betsapi_cobertura_ao_vivo"))
                for item in tarefas
            ),
            "cobertura_betsapi_na_lista_curta": sum(
                bool(item.get("betsapi_cobertura_ao_vivo"))
                for item in selecionadas
            ),
            "odds_api_prioritarias": sum(
                bool(item.get("odds_api_prioritaria"))
                for item in selecionadas
            ),
            "resgates_packball": sum(
                bool(item.get("resgate_odds_packball"))
                for item in selecionadas
            ),
            "betsapi": {
                chave: valor
                for chave, valor in diagnostico_betsapi.items()
                if chave != "cobertura_por_url"
            },
        })
        return selecionadas, diagnostico

    def _configurar_detalhamento_packball(self, tarefas):
        """Amplia um lote saudável sem elevar o teto de navegações.

        O rollback é uma flag operacional: desligá-la restaura exatamente o
        orçamento histórico de 180 segundos. O ControleAcessoPackBall segue
        sendo a autoridade para espaçamento, teto da janela e circuit breaker.
        """
        habilitado = str(
            os.getenv("PACKBALL_DETALHAMENTO_ADAPTATIVO", "0")
        ).strip().casefold() in {"1", "true", "sim", "yes", "on"}
        diagnostico = {
            "habilitado": habilitado,
            "ativado_no_ciclo": False,
            "orcamento_base_segundos": float(
                ORCAMENTO_COLETA_DETALHADA_SEGUNDOS
            ),
            "orcamento_efetivo_segundos": float(
                ORCAMENTO_COLETA_DETALHADA_SEGUNDOS
            ),
            "maximo_detalhes": None,
            "motivo": "flag_desativada",
        }
        if not habilitado:
            return diagnostico
        teste_capacidade = str(
            os.getenv("PACKBALL_TRIAGEM_CAPACIDADE_ATIVA", "0")
        ).strip().casefold() in {"1", "true", "sim", "yes", "on"}
        if teste_capacidade:
            try:
                maximo_detalhes = int(os.getenv(
                    "PACKBALL_TRIAGEM_MAX_DETALHES",
                    str(MAXIMO_DETALHES_TRIAGEM_CAPACIDADE),
                ))
            except (TypeError, ValueError):
                maximo_detalhes = MAXIMO_DETALHES_TRIAGEM_CAPACIDADE
            maximo_detalhes = min(max(maximo_detalhes, 1), 10)
            try:
                orcamento_adaptativo = float(os.getenv(
                    "PACKBALL_TRIAGEM_ORCAMENTO_SEGUNDOS",
                    str(ORCAMENTO_TRIAGEM_CAPACIDADE_SEGUNDOS),
                ))
            except (TypeError, ValueError):
                orcamento_adaptativo = float(
                    ORCAMENTO_TRIAGEM_CAPACIDADE_SEGUNDOS
                )
            orcamento_adaptativo = min(
                max(orcamento_adaptativo, 180.0), 360.0
            )
        else:
            maximo_detalhes = MAXIMO_DETALHES_PACKBALL_ADAPTATIVO
            orcamento_adaptativo = (
                ORCAMENTO_COLETA_DETALHADA_ADAPTATIVO_SEGUNDOS
            )
        maximo_configurado = maximo_detalhes
        dinamica_ativa = bool(
            teste_capacidade
            and os.getenv("PACKBALL_CAPACIDADE_DINAMICA_ATIVA", "0") == "1"
        )
        diagnostico["capacidade_dinamica_ativa"] = dinamica_ativa
        if dinamica_ativa:
            try:
                minimo_detalhes = int(os.getenv(
                    "PACKBALL_TRIAGEM_MIN_DETALHES", "5"
                ))
            except (TypeError, ValueError):
                minimo_detalhes = 5
            minimo_detalhes = min(
                max(minimo_detalhes, 1), maximo_configurado
            )
            try:
                alvo_ciclo = float(os.getenv(
                    "PACKBALL_CICLO_ALVO_SEGUNDOS", "300"
                ))
            except (TypeError, ValueError):
                alvo_ciclo = 300.0
            try:
                reserva_final = float(os.getenv(
                    "PACKBALL_CICLO_RESERVA_FINAL_SEGUNDOS", "10"
                ))
            except (TypeError, ValueError):
                reserva_final = 10.0
            try:
                custo_thestats = float(os.getenv(
                    "THESTATSAPI_CUSTO_ESTIMADO_JOGO_SEGUNDOS", "3.5"
                ))
            except (TypeError, ValueError):
                custo_thestats = 3.5
            try:
                auditoria_extra = int(os.getenv(
                    "THESTATSAPI_RESERVA_AUDITORIA_FORA_LOTE", "2"
                ))
            except (TypeError, ValueError):
                auditoria_extra = 2
            duracoes = [
                float(valor)
                for valor in getattr(
                    self, "_duracoes_tarefas_recentes", []
                )[-12:]
                if isinstance(valor, (int, float))
                and math.isfinite(float(valor))
                and float(valor) > 0
            ]
            duracoes.sort()
            if duracoes:
                meio = len(duracoes) // 2
                estimativa_tarefa = (
                    duracoes[meio]
                    if len(duracoes) % 2
                    else (duracoes[meio - 1] + duracoes[meio]) / 2
                )
            else:
                estimativa_tarefa = 30.0
            estimativa_tarefa = min(max(estimativa_tarefa, 15.0), 60.0)
            inicio_ciclo = getattr(
                self, "_inicio_ciclo_monotonic", None
            )
            decorrido_pre_detalhe = (
                max(time.monotonic() - inicio_ciclo, 0.0)
                if isinstance(inicio_ciclo, (int, float)) else 0.0
            )
            restante_alvo = max(
                alvo_ciclo - decorrido_pre_detalhe - reserva_final, 0.0
            )
            escolhido = minimo_detalhes
            for quantidade in range(
                maximo_configurado, minimo_detalhes - 1, -1
            ):
                custo_estimado = (
                    quantidade * estimativa_tarefa
                    + (quantidade + max(auditoria_extra, 0))
                    * max(custo_thestats, 0.0)
                )
                if custo_estimado <= restante_alvo:
                    escolhido = quantidade
                    break
            maximo_detalhes = escolhido
            custo_auxiliar = (
                (maximo_detalhes + max(auditoria_extra, 0))
                * max(custo_thestats, 0.0)
            )
            orcamento_adaptativo = min(
                orcamento_adaptativo,
                max(restante_alvo - custo_auxiliar, 180.0),
            )
            diagnostico.update({
                "maximo_configurado": maximo_configurado,
                "minimo_configurado": minimo_detalhes,
                "alvo_ciclo_segundos": round(alvo_ciclo, 3),
                "decorrido_pre_detalhe_segundos": round(
                    decorrido_pre_detalhe, 3
                ),
                "estimativa_tarefa_segundos": round(
                    estimativa_tarefa, 3
                ),
                "custo_auxiliar_estimado_segundos": round(
                    custo_auxiliar, 3
                ),
                "escolha_dinamica": maximo_detalhes,
            })
        acionaveis = sum(
            tarefa.get("acionavel_fila_detalhada") is True
            for tarefa in (tarefas or [])
        )
        if acionaveis < maximo_detalhes and not dinamica_ativa:
            diagnostico["motivo"] = "acionaveis_abaixo_do_lote"
            return diagnostico
        if dinamica_ativa and acionaveis > 0:
            maximo_detalhes = min(maximo_detalhes, acionaveis)
        controle = getattr(self, "controle_packball", None)
        estado_atual = getattr(controle, "estado_atual", None)
        if not callable(estado_atual):
            diagnostico["motivo"] = "controle_packball_indisponivel"
            return diagnostico
        try:
            estado = estado_atual() or {}
        except Exception:
            diagnostico["motivo"] = "estado_packball_indisponivel"
            return diagnostico
        if estado.get("ativo") is True:
            diagnostico["motivo"] = "pausa_packball_ativa"
            return diagnostico
        if estado.get("rollback_capacidade_ativo") is True:
            diagnostico["motivo"] = "rollback_capacidade_ativo"
            return diagnostico
        if estado.get("distribuicao_janela_ativa") is not True:
            diagnostico["motivo"] = "distribuicao_janela_inativa"
            return diagnostico
        diagnostico.update({
            "ativado_no_ciclo": True,
            "orcamento_efetivo_segundos": float(
                orcamento_adaptativo
            ),
            "maximo_detalhes": maximo_detalhes,
            "motivo": "capacidade_saudavel",
            "teste_capacidade": teste_capacidade,
            "rollback_teste": "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA=0",
            "rollback_lote": (
                "PACKBALL_TRIAGEM_MAX_DETALHES=7; "
                "PACKBALL_TRIAGEM_ORCAMENTO_SEGUNDOS=270"
            ),
            "tarefas_acionaveis": acionaveis,
            "maximo_navegacoes_janela": estado.get(
                "maximo_navegacoes_efetivo_janela"
            ),
            "janela_navegacoes_segundos": estado.get(
                "janela_navegacoes_segundos"
            ),
        })
        return diagnostico

    @staticmethod
    def _registrar_ancoras_exploracao(conexao):
        """Congela todas as definições antes da primeira coleta."""
        registrar_ou_validar_definicao_exploracao_gols(conexao)
        registrar_ou_validar_politica_avaliacao_gols(conexao)
        registrar_ou_validar_definicao_exploracao_gol_ft_v3(conexao)
        registrar_ou_validar_politica_avaliacao_gol_ft_v3(conexao)
        registrar_ou_validar_consenso_multifonte(conexao)
        registrar_ou_validar_definicao_gol_ft_v2_controle(conexao)
        registrar_ou_validar_politica_gol_ft_v2_controle(conexao)
        registrar_ou_validar_challenger_v2_ft(conexao)
        registrar_ou_validar_gols_antecipados(conexao)
        registrar_ou_validar_filtro_ht_preciso(conexao)
        registrar_ou_validar_filtro_ft_preciso(conexao)
        registrar_ou_validar_quase_gol_ft(conexao)
        registrar_ou_validar_escanteios_ft_legado(conexao)
        registrar_ou_validar_escanteios_ft(conexao)
        registrar_ou_validar_gols_capacidade_times(conexao)
        registrar_ou_validar_gols_capacidade_contextual_v2(conexao)
        registrar_ou_validar_grupo_ft_capacidade_contextual_v2(conexao)
        registrar_ou_validar_gol_ht_00_min20(conexao)
        registrar_ou_validar_gol_ft_reforcado(conexao)
        registrar_ou_validar_gol_ht_protegido(conexao)
        registrar_ou_validar_gol_ft_tendencia_mais_um(conexao)
        registrar_ou_validar_top_criterios_gols(conexao)
        registrar_ou_validar_proximo_gol_balanceado_sombra(conexao)
        registrar_ou_validar_quase_proximo_gol(conexao)

    def __init__(self, pasta_projeto=None):
        self.pasta = Path(pasta_projeto or Path(__file__).parent)
        load_dotenv(self.pasta / ".env")
        self.configuracao = validar_configuracao()
        if not self.configuracao["valida"]:
            raise ValueError(
                "Configuração inválida: "
                + "; ".join(self.configuracao["erros"])
            )
        self.arquivo_sessao = self.pasta / "packball_session.json"
        self.arquivo_registros = self.pasta / "monitor_registros.jsonl"
        self.banco = BancoMonitor(self.pasta / "monitor_packball.db")
        self.carteira_operacional = registrar_carteira_operacional(
            self.banco.conexao, os.environ, self.pasta
        )
        self._registrar_ancoras_exploracao(self.banco.conexao)
        self.api = APIFootball(self.pasta)
        try:
            timeout_thestatsapi = float(
                os.getenv("THESTATSAPI_TIMEOUT_SEGUNDOS", "6")
            )
        except (TypeError, ValueError):
            timeout_thestatsapi = 6.0
        self.thestatsapi = TheStatsAPI(
            self.pasta,
            timeout=timeout_thestatsapi,
        )
        configuracao_thestatsapi = (
            self.configuracao.get("thestatsapi") or {}
        )
        self.thestatsapi_sombra_ativa = bool(
            configuracao_thestatsapi.get("sombra_ativa")
        )
        self.thestatsapi_aplicacao_sinais_ativa = bool(
            configuracao_thestatsapi.get("aplicacao_sinais")
        )
        self.thestatsapi_max_jogos_ciclo = min(
            max(
                int(
                    configuracao_thestatsapi.get(
                        "maximo_jogos_ciclo", 17
                    ) or 0
                ),
                0,
            ),
            17,
        )
        self._thestatsapi_selecoes = {}
        self._thestatsapi_selecoes_stats = {}
        self._thestatsapi_selecoes_odds = {}
        self.betsapi = BetsAPI(self.pasta)
        self.the_odds_api = TheOddsAPI(self.pasta)
        self.historico = HistoricoTemporal()
        self.observabilidade = Observabilidade(
            self.pasta / "monitor_eventos.jsonl"
        )
        self.controle_packball = ControleAcessoPackBall(
            self.pasta / "packball_acesso_estado.json",
            intervalo_minimo_segundos=float(
                os.getenv("PACKBALL_INTERVALO_NAVEGACAO_SEGUNDOS", "12")
            ),
            cooldown_minutos=int(
                os.getenv("PACKBALL_COOLDOWN_MINUTOS", "15")
            ),
            maximo_por_janela=int(
                os.getenv("PACKBALL_MAXIMO_NAVEGACOES_JANELA", "24")
            ),
            janela_segundos=int(
                os.getenv("PACKBALL_JANELA_NAVEGACOES_SEGUNDOS", "600")
            ),
            experimento_capacidade=(
                os.getenv("PACKBALL_EXPERIMENTO_CAPACIDADE", "0") == "1"
            ),
            intervalo_rollback_segundos=float(
                os.getenv(
                    "PACKBALL_INTERVALO_ROLLBACK_SEGUNDOS", "12"
                )
            ),
            maximo_rollback_por_janela=int(
                os.getenv(
                    "PACKBALL_MAXIMO_ROLLBACK_JANELA", "24"
                )
            ),
            distribuir_janela=(
                os.getenv(
                    "PACKBALL_DISTRIBUIR_NAVEGACOES", "0"
                ) == "1"
            ),
            margem_distribuicao_segundos=float(
                os.getenv(
                    "PACKBALL_MARGEM_DISTRIBUICAO_SEGUNDOS", "0.5"
                )
            ),
        )
        self.packball = ColetorPackBall(
            renovar_sessao=lambda pagina: autenticar_pagina(
                pagina, self.arquivo_sessao,
                controle_acesso=self.controle_packball,
            ),
            controle_acesso=self.controle_packball,
            usar_scanner_prioridade=(
                os.getenv("PACKBALL_SCANNER_PRIORIDADE_ATIVO", "0") == "1"
            ),
            capturar_indicadores_lista=(
                os.getenv("PACKBALL_COLUNAS_PRIORIDADE_ATIVO", "0") == "1"
            ),
            aceitar_zero_sem_contador_confirmado=(
                os.getenv(
                    "PACKBALL_ZERO_SEM_CONTADOR_CONFIRMADO_ATIVO", "1"
                ) == "1"
            ),
        )
        self.backtest = AvaliadorBacktest(self.banco)
        self.calibrador = CalibradorBacktest(self.banco)
        self.alertas = AlertasTelegram(
            self.banco,
            validador_operacao_oficial=(
                self._validar_operacao_para_alerta_oficial
            ),
        )
        self.backup = BackupBanco(
            self.pasta / "backups",
            pasta_espelho=(
                os.getenv("BACKUP_ESPELHO_DIRETORIO") or None
            ),
            compactar=(
                os.getenv("BACKUP_COMPACTACAO_ATIVA", "1") == "1"
            ),
        )
        self._data_backup_verificada = None
        self._janela_backup_periodico_verificada = None
        self._data_manutencao_verificada = None
        self._duracoes_tarefas_recentes = (
            self.observabilidade.duracoes_tarefas_recentes(
                JANELA_DURACOES_TAREFAS
            )
        )
        self._resgate_odds_packball_urls = set()
        # Trava fail-closed do ciclo atual. Uma falha em qualquer fonte
        # obrigatoria impede todos os envios seguintes, mesmo que a fonte
        # volte a responder alguns segundos depois. A trava so e limpa no
        # inicio de um novo ciclo completo.
        self._operacao_bloqueada_ciclo = False
        self._adiar_alertas_ciclo = False
        self._alertas_pendentes_ciclo = []
        self._ultima_rechecagem_odd_api = 0.0
        self._ultima_avaliacao_acompanhamento_odd = 0.0
        self._ultima_avaliacao_desajuste_odds = 0.0
        self._ultima_avaliacao_prioridade_ligas_gols = 0.0
        self._ultima_avaliacao_probabilidade_individual = 0.0
        self._ultima_avaliacao_quarentena_fallback_ht = 0.0
        self._trabalhador_acompanhamento_odd = None
        self.reinicio_runtime_solicitado = False
        self.diagnostico_reinicio_runtime = None
        self.finalizador = FinalizadorResultadosAPI(
            self.banco, self.api, self.backtest
        )
        self.finalizador_packball = FinalizadorResultadosPackBall(
            self.banco, self.packball, self.backtest
        )
        self.finalizador_sem_dado = FinalizadorPendenciasSemDado(self.banco)
        self.agendador = AgendadorColeta(
            intervalo_rapido=int(
                os.getenv("COLETA_INTERVALO_RAPIDO_SEGUNDOS", "240")
            ),
            intervalo_lento=int(
                os.getenv("COLETA_INTERVALO_LENTO_SEGUNDOS", "360")
            ),
            odds_rapidas=int(
                os.getenv("COLETA_ODDS_RAPIDAS_SEGUNDOS", "600")
            ),
            odds_lentas=int(
                os.getenv("COLETA_ODDS_LENTAS_SEGUNDOS", "900")
            ),
            maximo_foco=int(
                os.getenv("COLETA_MAXIMO_JOGOS_FOCO", "3")
            ),
            intervalo_exploracao=int(
                os.getenv("COLETA_INTERVALO_EXPLORACAO", "3")
            ),
            intervalo_rechecagem_evento=int(
                os.getenv("COLETA_RECHECAGEM_URGENTE_SEGUNDOS", "75")
            ),
            usar_indicadores_lista=(
                os.getenv("PACKBALL_COLUNAS_PRIORIDADE_ATIVO", "0") == "1"
            ),
        )
        self.conectividade = VerificadorConectividade()
        self.regra_fingerprint = None

    def _intervalo_trabalhador_acompanhamento_odd(self):
        try:
            return min(max(float(os.getenv(
                "ACOMPANHAMENTO_ODD_API_INTERVALO_SEGUNDOS", "15"
            )), 8.0), 60.0)
        except (TypeError, ValueError):
            return 15.0

    def _criar_servico_trabalhador_acompanhamento_odd(self):
        """Cria dependencias dentro da thread, inclusive o SQLite proprio."""
        servico = type(self)(self.pasta)
        # BetsAPI e The Odds API protegem estado e cota com RLock.
        # Compartilhar as mesmas
        # instancia evita que dois contadores locais gravem o mesmo arquivo
        # simultaneamente. A API-Football tambem serializa cada requisicao
        # pela trava de cota; compartilhar a instancia reaproveita a saude
        # ja confirmada pelo monitor e evita um bloqueio circular no primeiro
        # ciclo do trabalhador. O SQLite continua exclusivo da thread.
        servico.betsapi = self.betsapi
        servico.api = self.api
        servico.the_odds_api = self.the_odds_api
        servico.observabilidade = Observabilidade(
            self.pasta / "monitor_odds_rapidas_eventos.jsonl"
        )
        return servico

    def _trabalhador_acompanhamento_odd_ativo(self):
        trabalhador = getattr(
            self, "_trabalhador_acompanhamento_odd", None
        )
        ativo = getattr(trabalhador, "ativo", None)
        return bool(callable(ativo) and ativo())

    def _iniciar_trabalhador_acompanhamento_odd(self):
        ativo = str(os.getenv(
            "ACOMPANHAMENTO_ODD_WORKER_DEDICADO_ATIVO", "1"
        )).strip().casefold() in {"1", "true", "sim", "yes", "on"}
        if not ativo:
            return {
                "iniciado": False,
                "estado": "desativado",
                "rollback": "ACOMPANHAMENTO_ODD_WORKER_DEDICADO_ATIVO=1",
            }
        existente = getattr(
            self, "_trabalhador_acompanhamento_odd", None
        )
        if existente is not None and self._trabalhador_acompanhamento_odd_ativo():
            return {"iniciado": False, "estado": "ja_ativo"}
        trabalhador = TrabalhadorAcompanhamentoOdd(
            self._criar_servico_trabalhador_acompanhamento_odd,
            intervalo_segundos=(
                self._intervalo_trabalhador_acompanhamento_odd()
            ),
            caminho_estado=(
                self.pasta / "monitor_odds_rapidas_estado.json"
            ),
        )
        self._trabalhador_acompanhamento_odd = trabalhador
        iniciado = trabalhador.iniciar()
        diagnostico = {
            "iniciado": bool(iniciado),
            "estado": "iniciado" if iniciado else "nao_iniciado",
            "intervalo_segundos": trabalhador.intervalo_segundos,
            "sem_navegacao_packball": True,
            "rollback": "ACOMPANHAMENTO_ODD_WORKER_DEDICADO_ATIVO=0",
        }
        try:
            self.observabilidade.ciclo_progresso(
                "trabalhador_acompanhamento_odd_iniciado", **diagnostico
            )
        except Exception:
            pass
        return diagnostico

    def _parar_trabalhador_acompanhamento_odd(self):
        trabalhador = getattr(
            self, "_trabalhador_acompanhamento_odd", None
        )
        if trabalhador is None:
            return True
        encerrado = trabalhador.parar(timeout_segundos=30.0)
        try:
            self.observabilidade.ciclo_progresso(
                "trabalhador_acompanhamento_odd_encerrado",
                encerrado=bool(encerrado),
                estado=trabalhador.estado(),
            )
        except Exception:
            pass
        return encerrado

    def _modo_manutencao_ativo(self):
        pasta = getattr(self, "pasta", None)
        return bool(
            pasta is not None
            and ler_modo_manutencao(pasta).get("ativo")
        )

    @staticmethod
    def _json_seguro(valor, padrao):
        try:
            carregado = json.loads(valor) if valor is not None else padrao
        except (TypeError, ValueError, json.JSONDecodeError):
            return copy.deepcopy(padrao)
        if not isinstance(carregado, type(padrao)):
            return copy.deepcopy(padrao)
        return carregado

    @staticmethod
    def _estado_fixture_acompanhamento_odd(item, fixture):
        status = (fixture.get("fixture") or {}).get("status") or {}
        try:
            minuto = float(status.get("elapsed"))
        except (TypeError, ValueError):
            return None
        try:
            extra = float(status.get("extra") or 0)
        except (TypeError, ValueError):
            extra = 0.0
        minuto = max(minuto + max(extra, 0.0), 0.0)
        gols = fixture.get("goals") or {}
        try:
            casa = int(gols.get("home"))
            fora = int(gols.get("away"))
        except (TypeError, ValueError):
            return None
        if str(item.get("api_orientacao") or "").lower() == "invertida":
            casa, fora = fora, casa
        estado = {
            "placar": f"{casa}-{fora}",
            "minuto": minuto,
            "status": f"{int(minuto)}'",
            "status_codigo": str(status.get("short") or ""),
            "status_api": status,
            "mandante": item.get("mandante"),
            "visitante": item.get("visitante"),
        }
        snapshot_api = normalizar_snapshot_api_live(
            fixture,
            item.get("packball_url") or f"api://fixture/{(fixture.get('fixture') or {}).get('id')}",
            orientacao=item.get("api_orientacao") or "direta",
        )
        if isinstance(snapshot_api, dict):
            cantos_casa = snapshot_api.get("escanteios_mandante")
            cantos_fora = snapshot_api.get("escanteios_visitante")
            try:
                cantos_casa = float(cantos_casa)
                cantos_fora = float(cantos_fora)
            except (TypeError, ValueError):
                cantos_casa = cantos_fora = None
            if (
                cantos_casa is not None and cantos_fora is not None
                and math.isfinite(cantos_casa) and math.isfinite(cantos_fora)
                and cantos_casa >= 0 and cantos_fora >= 0
                and cantos_casa.is_integer() and cantos_fora.is_integer()
            ):
                estado["escanteios"] = {
                    "mandante": int(cantos_casa),
                    "visitante": int(cantos_fora),
                }
        return estado

    def _registrar_desfecho_acompanhamento_odd_api(
        self, item, fixture, estado, motivo,
    ):
        """Registra um evento decisivo e atualiza o aviso sem PackBall."""
        status_codigo = str(estado.get("status_codigo") or "").upper()
        if self.banco.estado_acompanhamento_odd_api_ja_registrado(
            item["origem_sinal_id"], estado.get("placar"), status_codigo
        ):
            return {"estado": "estado_ja_registrado", "snapshot_id": None}
        if status_codigo in {"FT", "AET", "PEN"}:
            status_snapshot = "Finalizado"
        elif status_codigo in {"CANC", "ABD", "PST"}:
            status_snapshot = "Anulado"
        elif (
            item.get("mercado") == "gol_ht"
            and status_codigo in {"HT", "2H", "ET", "BT", "P"}
        ):
            status_snapshot = "Intervalo"
        else:
            status_snapshot = estado.get("status")
        try:
            placar_api = [
                int(valor) for valor in str(estado.get("placar")).split("-")
            ]
        except (TypeError, ValueError):
            placar_api = None
        agora = datetime.now().replace(microsecond=0)
        registro = {
            "coletado_em": agora.isoformat(),
            "url": item["packball_url"],
            "mandante": item["mandante"],
            "visitante": item["visitante"],
            "pais": item.get("pais"),
            "liga": item.get("liga"),
            "placar": estado.get("placar"),
            "status": status_snapshot,
            "estatisticas": {},
            "evolucao": {},
            "odds": {},
            "confirmacao_api": {
                "fixture_id": item.get("api_fixture_id"),
                "orientacao": item.get("api_orientacao"),
                "placar": placar_api,
                "status": estado.get("status_api") or {},
                "fonte": "api_football",
            },
            "contexto_api": {
                "acompanhamento_odd_api_rapido": {
                    "versao": "desfecho-acompanhamento-odd-api-v1",
                    "estado_decisivo": True,
                    "motivo": str(motivo),
                    "origem_sinal_id": int(item["origem_sinal_id"]),
                    "sem_navegacao_packball_extra": True,
                },
            },
            "qualidade": {
                "pontuacao": 100.0,
                "fontes": ["api_football"],
                "versao": "resultado-api-live-acompanhamento-v1",
                "apto_para_sinal": False,
                "apto_para_liquidacao": True,
            },
            "falhas_fontes": [],
            "_nao_atualizar_ultima_coleta": True,
        }
        snapshot_id = self.salvar_registro(registro)
        if not snapshot_id:
            return {"estado": "snapshot_duplicado", "snapshot_id": None}
        resolvidos = 0
        avaliador = getattr(self, "backtest", None)
        avaliar = getattr(avaliador, "avaliar_snapshot", None)
        if callable(avaliar):
            resolvidos = int(avaliar(snapshot_id) or 0)
            if resolvidos:
                recalibrar = getattr(self, "_recalibrar", None)
                if callable(recalibrar):
                    recalibrar()
        atualizacao = {
            "consultados": 0, "conclusivos": 0, "entregues": 0,
            "erros": 0, "bloqueados": 0,
        }
        alertas = getattr(self, "alertas", None)
        atualizar = getattr(alertas, "atualizar_acompanhamentos_odd", None)
        if callable(atualizar):
            atualizacao = atualizar(limite=50)
        return {
            "estado": "registrado",
            "snapshot_id": snapshot_id,
            "sinais_resolvidos": resolvidos,
            "avisos_atualizados": int(atualizacao.get("entregues") or 0),
            "atualizacao": atualizacao,
        }

    def _materializar_entrada_acompanhamento_odd_api(
        self, item, fixture, estado, odds, avaliacao,
    ):
        agora = datetime.now().replace(microsecond=0)
        oferta = avaliacao["oferta"]
        contrato_mercado = validar_contrato_mercado_oferta(
            oferta,
            item.get("mercado"),
            item.get("linha"),
            exigir_origem=True,
        )
        if contrato_mercado["valido"] is not True:
            return {
                "estado": "contrato_mercado_incompleto",
                "persistido": False,
            }
        identidade_evento = validar_identidade_evento_oferta(oferta, estado)
        if identidade_evento["valida"] is not True:
            return {
                "estado": identidade_evento["motivo"],
                "persistido": False,
            }
        features = self._json_seguro(item.get("features_json"), {})
        recalculado, bloqueio_metodo = revalidar_metodo_acompanhado(
            features,
            {
                "url": item["packball_url"], "mandante": item["mandante"],
                "visitante": item["visitante"], "liga": item.get("liga"),
                "placar": estado["placar"], "status": estado["status"],
                "minuto": estado["minuto"],
            },
            self._json_seguro(item.get("contexto_api_json"), {}),
            self._json_seguro(item.get("qualidade_json"), {}),
            oferta, getattr(self, "alertas", None),
            avaliacao.get("idade_tecnica_segundos"),
        )
        if bloqueio_metodo:
            return {"estado": bloqueio_metodo, "persistido": False}
        if recalculado is not None:
            # Atualiza a análise, conservando a observação e as provas das
            # proteções transversais aprovadas no ciclo técnico.
            features.update(recalculado["features"])
        acompanhamento = dict(features.get("acompanhamento_odd") or {})
        acompanhamento.update({
            "convertido_por_api": True,
            "convertido_em": agora.isoformat(),
            "odd_convertida": oferta["odd"],
            "fonte_convertida": oferta.get("fonte"),
        })
        referencia_mercado = {}
        if contrato_mercado["tipo"] == "tres_vias":
            referencia_mercado = {
                "selecao_mercado": contrato_mercado["selecao_mercado"],
                "odds_mercado_sincronizadas": contrato_mercado[
                    "odds_mercado_sincronizadas"
                ],
                "mercado_odds_sincronizado": True,
            }
        else:
            referencia_mercado = {
                "odd_oposta": contrato_mercado["odd_oposta"],
                "odd_par_sincronizado": True,
            }
        features.update({
            "acompanhamento_odd": acompanhamento,
            "acompanhamento_odd_rapido": {
                "versao": VERSAO_MATERIALIZACAO_RAPIDA,
                "origem_sinal_id": int(item["origem_sinal_id"]),
                "leitura_tecnica_sinal_id": int(item["sinal_id"]),
                "idade_tecnica_segundos": avaliacao.get(
                    "idade_tecnica_segundos"
                ),
                "placar_confirmado": estado["placar"],
                "minuto_confirmado": estado["minuto"],
                "linha_exata_confirmada": True,
                "proveniencia_temporal_odd": avaliacao.get(
                    "proveniencia_temporal"
                ),
                "identidade_evento_odd": identidade_evento[
                    "identidade_evento"
                ],
                "origem_mercado_odd": contrato_mercado[
                    "origem_mercado"
                ],
                "navegacao_packball_extra": False,
                "criterios_revalidados": [
                    "leitura_tecnica_ainda_valida",
                    "placar_inalterado",
                    "periodo_e_minuto_operacionais",
                    "linha_exata_disponivel",
                    "evento_externo_da_odd_confirmado",
                    "odd_atual_fresca",
                    "relogio_da_fonte_coerente",
                    "contrato_de_mercado_completo",
                    "lados_vindos_do_mesmo_grupo_da_casa",
                    "odd_dentro_da_faixa",
                ],
                "rollback": "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO=0",
            },
            "decisao_em": agora.isoformat(),
            "estado_observado_em": agora.isoformat(),
            "minuto": estado["minuto"],
            "fonte_odds": oferta.get("fonte") or "betsapi",
            "bookmaker_odds": oferta.get("bookmaker"),
            "tipo_mercado_odds": "total",
            "coletado_em_odds": oferta.get("coletado_em"),
            "idade_odds_segundos": oferta.get("idade_segundos"),
            "odds_cache": oferta.get("cache"),
            # A referência sem vig só pode combinar preços observados no
            # mesmo par e no mesmo instante. Nunca reutilize o Under que
            # originou a fila depois que o Over for atualizado pela API.
            **referencia_mercado,
            "qualidade_dados": item.get("qualidade_dados"),
        })
        motivos = [
            motivo
            for motivo in (
                recalculado.get("motivos", []) if recalculado is not None
                else self._json_seguro(item.get("motivos_json"), [])
            )
            if not str(motivo).startswith("bloqueio:")
            and motivo != "monitoramento_odd_abaixo_da_faixa"
        ]
        motivos.extend([
            "odd_alvo_atingida_por_api",
            "placar_e_minuto_revalidados_por_api",
            "linha_exata_revalidada",
        ])
        candidato = {
            "mercado": item["mercado"],
            "linha": item["linha"],
            "odd": oferta["odd"],
            "pontuacao_tecnica": (
                recalculado["pontuacao_tecnica"] if recalculado is not None
                else item["pontuacao_tecnica"]
            ),
            "probabilidade_calibrada": None,
            "regra_versao": item["regra_versao"],
            "regra_fingerprint": item["regra_fingerprint"],
            "motivos": list(dict.fromkeys(motivos)),
            "bloqueios": [],
            "features": features,
            "qualidade_dados": item.get("qualidade_dados") or 0,
            "status": (
                "simulacao" if features.get("exploracao_sombra")
                else "aprovado"
            ),
        }
        if contrato_mercado["tipo"] == "tres_vias":
            candidato.update({
                "selecao_mercado": contrato_mercado["selecao_mercado"],
                "odds_mercado_sincronizadas": contrato_mercado[
                    "odds_mercado_sincronizadas"
                ],
                "mercado_odds_sincronizado": True,
            })
        else:
            candidato.update({
                "odd_oposta": contrato_mercado["odd_oposta"],
                "odd_par_sincronizado": True,
            })
        if recalculado is not None:
            features["acompanhamento_odd_rapido"]["criterios_revalidados"].append(
                "mesmo_metodo_recalculado_na_odd_e_minuto_atuais"
            )
        self.calibrador.aplicar(candidato)
        probabilidade = candidato.get("probabilidade_calibrada")
        if probabilidade is None:
            alertas = getattr(self, "alertas", None)
            filtro = getattr(alertas, "motivo_filtro_teste", None)
            if not getattr(alertas, "modo_teste", False) or not callable(filtro):
                return {"estado": "sem_calibracao_ativa", "persistido": False}
            motivo = filtro(candidato)
            if motivo is not None:
                return {"estado": motivo, "persistido": False}
            # Mesma rota já autorizada no ciclo normal. Não promove modelos
            # nem fabrica probabilidade; o gateway revalida tudo ao enviar.
            criterio_rota = "politica_envio_grupo_ativa"
        else:
            try:
                probabilidade = float(probabilidade)
            except (TypeError, ValueError):
                return {"estado": "calibracao_invalida", "persistido": False}
            if not math.isfinite(probabilidade) or not 0 <= probabilidade <= 1:
                return {"estado": "calibracao_invalida", "persistido": False}
            if probabilidade < PROBABILIDADE_MINIMA:
                return {
                    "estado": "confianca_calibrada_insuficiente",
                    "probabilidade_calibrada": probabilidade,
                    "probabilidade_minima": PROBABILIDADE_MINIMA,
                    "persistido": False,
                }
            criterio_rota = "calibracao_ativa"
        features["acompanhamento_odd_rapido"]["criterios_revalidados"].append(
            criterio_rota
        )
        features["acompanhamento_odd_rapido"]["rota_envio"] = criterio_rota

        # A cotação de entrada precisa ser congelada a partir desta nova
        # coleta, não da odd baixa que originou a fila. Sem a fotografia
        # completa e unívoca do mercado, a conversão termina aqui.
        aplicar_proveniencia_odds(
            [candidato], odds, instante=agora,
            idade_maxima_segundos=FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS,
        )
        features = candidato.get("features") or {}
        bloqueios_proveniencia = [
            bloqueio for bloqueio in candidato.get("bloqueios") or []
            if bloqueio in BLOQUEIOS_PROVENIENCIA
        ]
        if bloqueios_proveniencia:
            return {
                "estado": bloqueios_proveniencia[0],
                "categoria": "proveniencia_odd_rapida_invalida",
                "bloqueios_proveniencia": bloqueios_proveniencia,
                "coerencia_curva_odds": features.get(
                    "coerencia_curva_odds"
                ),
                "persistido": False,
            }
        if features.get(CHAVE_ESTADO_COTACAO_ENTRADA) != (
            ESTADO_COTACAO_CONGELADA
        ) or not anexar_par_odds_sincronizado(candidato, odds):
            return {
                "estado": "contrato_mercado_nao_congelado",
                "persistido": False,
            }

        verificar_leitura = getattr(
            getattr(self, "banco", None), "acompanhamento_odd_leitura_vigente", None
        )
        if not callable(verificar_leitura) or not verificar_leitura(item["sinal_id"]):
            return {"estado": "analise_acompanhamento_substituida", "persistido": False}

        qualidade = self._json_seguro(item.get("qualidade_json"), {})
        fontes_qualidade = ["packball", "api_football"]
        fonte_odd = str(oferta.get("fonte") or "").strip()
        if fonte_odd and fonte_odd not in fontes_qualidade:
            fontes_qualidade.append(fonte_odd)
        qualidade.update({
            "pontuacao": item.get("qualidade_dados"),
            "apto_para_sinal": True,
            "apto_para_liquidacao": True,
            "fontes": fontes_qualidade,
            "acompanhamento_odd_rapido": {
                "aprovado": True,
                "sem_navegacao_packball_extra": True,
                "idade_tecnica_segundos": avaliacao.get(
                    "idade_tecnica_segundos"
                ),
                "proveniencia_temporal_odd": avaliacao.get(
                    "proveniencia_temporal"
                ),
                "identidade_evento_odd": identidade_evento[
                    "identidade_evento"
                ],
                "origem_mercado_odd": contrato_mercado[
                    "origem_mercado"
                ],
            },
        })
        confirmacao_api = {
            "fixture_id": item.get("api_fixture_id"),
            "orientacao": item.get("api_orientacao"),
            "placar": estado["placar"],
            "status": estado.get("status_api") or {},
            "fonte": "api_football",
        }
        registro = {
            "coletado_em": agora.isoformat(),
            "url": item["packball_url"],
            "mandante": item["mandante"],
            "visitante": item["visitante"],
            "pais": item.get("pais"),
            "liga": item.get("liga"),
            "placar": estado["placar"],
            "status": estado["status"],
            "texto_linha": item.get("texto_linha"),
            "estatisticas": self._json_seguro(
                item.get("estatisticas_json"), {}
            ),
            "evolucao": self._json_seguro(item.get("evolucao_json"), {}),
            "odds": odds,
            "confirmacao_api": confirmacao_api,
            "estatisticas_api": self._json_seguro(
                item.get("estatisticas_api_json"), {}
            ),
            "contexto_api": self._json_seguro(
                item.get("contexto_api_json"), {}
            ),
            "qualidade": qualidade,
            "falhas_fontes": [],
            "_nao_atualizar_ultima_coleta": True,
        }
        snapshot_id = self.salvar_registro(registro)
        if not snapshot_id:
            return {"estado": "snapshot_duplicado"}
        ids = self.banco.salvar_candidatos(
            snapshot_id, [candidato], agora.isoformat()
        )
        if not ids or candidato.get("_status_persistido") != candidato["status"]:
            return {"estado": "sinal_duplicado_ou_aberto"}
        if self._bloquear_exposicao_gol_partida(ids[0], candidato):
            return {"estado": "exposicao_gol_partida_existente", "persistido": True}
        envio = self._despachar_alertas([
            (
                ids[0],
                candidato,
                {
                    "url": item["packball_url"],
                    "mandante": item["mandante"],
                    "visitante": item["visitante"],
                    "liga": item.get("liga"),
                    "placar": estado["placar"],
                    "status": estado["status"],
                },
            )
        ])
        return {
            "estado": "enviado" if envio["entregues"] else "bloqueado",
            "sinal_id": ids[0],
            "entregues": envio["entregues"],
            "bloqueados": envio["bloqueados"],
        }

    def _observar_rechecagem_odd_api(self, resumo):
        """Registra apenas atividade relevante, sem poluir o Telegram."""
        resumo = dict(resumo or {})
        relevante = bool(
            resumo.get("consultados")
            or resumo.get("atingiram_alvo")
            or resumo.get("enviados")
            or resumo.get("bloqueados")
            or resumo.get("erro")
        )
        if not relevante:
            return
        observabilidade = getattr(self, "observabilidade", None)
        registrar = getattr(observabilidade, "ciclo_progresso", None)
        if not callable(registrar):
            return
        try:
            registrar("acompanhamento_odd_api_rapido", **resumo)
        except Exception:
            # Telemetria nunca pode interromper a vigilância nem o PackBall.
            pass

    def _complementar_odd_exata_acompanhamento_api(
        self, odds, item, estado, *, forcar_controle=False,
    ):
        """Cobre a fila rápida com a API-Football sem abrir o PackBall.

        A BetsAPI continua sendo a primeira fonte porque atualiza em cadência
        curta. Quando ela não pareia o evento ou não traz a mesma linha do
        aviso, a API-Football pode fornecer a cotação exata. Ao atingir o
        alvo, ``forcar_controle`` coleta uma segunda fotografia prospectiva
        sem substituir a oferta principal. O carimbo de idade real permanece
        obrigatório, portanto cache antigo nunca vira entrada oficial.
        """
        exata_existente = extrair_odd_exata_acompanhamento(
            odds, item.get("mercado"), item.get("linha")
        )
        if (
            not forcar_controle
            and exata_existente is not None
            and validar_identidade_evento_oferta(
            exata_existente, estado
            ).get("valida") is True
        ):
            return {"complementado": False, "motivo": "linha_ja_disponivel"}
        fixture_id = item.get("api_fixture_id")
        if fixture_id is None:
            return {"complementado": False, "motivo": "sem_fixture_api"}
        mercado = item.get("mercado")
        oferta_api = None
        if mercado == "gol_ft":
            oferta_api = self.api.odds_gols_total_ft(fixture_id)
        elif mercado == "gol_ht":
            oferta_api = self.api.odds_gols_total_ht(fixture_id)
        elif mercado == "proximo_gol":
            placar = extrair_placar(estado.get("placar"))
            if placar is not None:
                oferta_api = self.api.odds_proximo_gol(
                    fixture_id, placar[0] + placar[1]
                )
        if not isinstance(oferta_api, dict):
            return {
                "complementado": False,
                "motivo": "linha_api_football_indisponivel",
            }
        oferta_api["identidade_evento"] = {
            "schema": "identidade-evento-odd-v1",
            "confirmada": True,
            "fonte": "api_football",
            "evento_externo_id": str(fixture_id),
            "orientacao": str(
                item.get("api_orientacao") or "direta"
            ).casefold(),
            "similaridade": None,
            "mandante_normalizado": item.get("mandante"),
            "visitante_normalizado": item.get("visitante"),
            "placar_normalizado": estado.get("placar"),
            "metodo": "fixture_api_football_persistido_revalidado",
        }
        self._carimbar_mercado_api(oferta_api)
        exata_api = extrair_odd_exata_acompanhamento(
            {"ao_vivo": [oferta_api]},
            item.get("mercado"),
            item.get("linha"),
        )
        contrato_api = (
            validar_contrato_mercado_oferta(
                exata_api,
                item.get("mercado"),
                item.get("linha"),
                exigir_origem=True,
            )
            if exata_api is not None else {"valido": False}
        )
        identidade_api = (
            validar_identidade_evento_oferta(exata_api, estado)
            if exata_api is not None else {"valida": False}
        )
        exata_valida = bool(
            exata_api is not None
            and contrato_api.get("valido") is True
            and identidade_api.get("valida") is True
        )
        if exata_valida:
            if forcar_controle:
                odds.setdefault("ao_vivo", []).append(oferta_api)
            else:
                odds.setdefault("ao_vivo", []).insert(0, oferta_api)
        return {
            "complementado": exata_valida,
            "motivo": (
                "controle_api_football_anexado"
                if exata_valida and forcar_controle
                else "linha_api_football_anexada"
                if exata_valida
                else "controle_api_football_divergente"
                if forcar_controle
                else "linha_api_football_divergente"
            ),
            "oferta_controle": exata_api if exata_valida else None,
            "aplicacao_sinais": False if forcar_controle else None,
        }

    def _rechecar_acompanhamentos_odd_api(self, forcar=False):
        """Vigia avisos de odd pela API, sempre isolada do ciclo PackBall."""
        trabalhador = getattr(
            self, "_trabalhador_acompanhamento_odd", None
        )
        if (
            not forcar
            and trabalhador is not None
            and not self._trabalhador_acompanhamento_odd_ativo()
        ):
            # A thread trata falhas comuns internamente. Se ainda assim ela
            # terminar, o primeiro ponto seguro do ciclo principal cria uma
            # nova instancia; enquanto isso, a consulta principal continua
            # disponível como fallback.
            self._iniciar_trabalhador_acompanhamento_odd()
        if (
            not forcar
            and self._trabalhador_acompanhamento_odd_ativo()
        ):
            return {
                "consultados": 0,
                "atingiram_alvo": 0,
                "enviados": 0,
                "bloqueados": 0,
                "motivo": "trabalhador_dedicado_ativo",
            }
        try:
            resumo = self._executar_rechecagem_odd_api(forcar=forcar)
        except Exception as erro:
            resumo = {
                "consultados": 0,
                "atingiram_alvo": 0,
                "enviados": 0,
                "bloqueados": 0,
                "motivos": {"falha_isolada_api": 1},
                "motivo": "falha_isolada_api",
                "erro": resumir_erro_seguro(erro),
                "tipo_erro": type(erro).__name__,
            }
        self._observar_rechecagem_odd_api(resumo)
        return resumo

    def _capturar_cotacoes_clv_pos_alerta_api(self):
        """Fotografa a mesma Bet365 2–10 minutos após uma entrega.

        A rotina roda na thread de odds rápidas, não navega no PackBall e não
        chama nenhum caminho de geração, materialização ou envio de sinais.
        O estado API-Football é persistido mesmo se a linha já tiver sumido;
        assim, contratos liquidados não desaparecem da amostra de CLV.
        """
        resumo = {
            "versao": VERSAO_COLETA_CLV_API_RAPIDA,
            "mercados_api_rapida": sorted(MERCADOS_CLV_API_RAPIDA),
            "mercados_somente_snapshot": sorted(
                MERCADOS_CLV_SOMENTE_SNAPSHOT
            ),
            "candidatos": 0,
            "consultados": 0,
            "com_oferta_exata": 0,
            "sem_oferta_exata": 0,
            "somente_estado": 0,
            "estados_persistidos": 0,
            "falhas": 0,
            "motivos": {},
            "aplicacao_sinais": False,
            "telegram": False,
            "sem_navegacao_packball": True,
        }
        if str(os.getenv(
            "CLV_POS_ALERTA_API_RAPIDA_ATIVA", "1"
        )).strip().casefold() not in {"1", "true", "sim", "yes", "on"}:
            resumo["estado"] = "desativada"
            return resumo
        try:
            limite = min(max(int(os.getenv(
                "CLV_POS_ALERTA_API_RAPIDA_LOTE", "8"
            )), 1), 20)
        except (TypeError, ValueError):
            limite = 8
        agora = datetime.now().replace(microsecond=0)
        itens = [dict(item) for item in (
            self.banco.sinais_entregues_para_clv_pos_alerta(
                limite, agora=agora.isoformat()
            )
        )]
        resumo["candidatos"] = len(itens)
        if not itens:
            resumo["estado"] = "sem_candidatos_na_janela"
            return resumo
        cliente_api = getattr(self, "api", None)
        cliente_betsapi = getattr(self, "betsapi", None)
        if not callable(getattr(
            cliente_api, "fixtures_ao_vivo_detalhadas", None
        )):
            resumo["estado"] = "api_football_indisponivel"
            resumo["falhas"] = len(itens)
            return resumo
        precisa_betsapi = any(
            modo_coleta_estado_clv(
                item.get("fonte_odds"), item.get("bookmaker_odds")
            ) == "estado_e_preco"
            for item in itens
        )
        if precisa_betsapi and not callable(getattr(
            cliente_betsapi, "buscar_mercados", None
        )):
            resumo["estado"] = "betsapi_indisponivel"
            resumo["falhas"] = len(itens)
            return resumo

        fixture_ids = sorted({
            int(item["api_fixture_id"])
            for item in itens if item.get("api_fixture_id") is not None
        })
        fixtures = cliente_api.fixtures_ao_vivo_detalhadas(fixture_ids)
        por_id = {
            int((fixture.get("fixture") or {}).get("id")): fixture
            for fixture in fixtures or []
            if (fixture.get("fixture") or {}).get("id") is not None
        }

        def motivo(nome):
            resumo["motivos"][nome] = resumo["motivos"].get(nome, 0) + 1

        for item in itens:
            fixture_id = int(item["api_fixture_id"])
            fixture = por_id.get(fixture_id)
            estado = (
                self._estado_fixture_acompanhamento_odd(item, fixture)
                if fixture is not None else None
            )
            if estado is None:
                resumo["falhas"] += 1
                motivo("estado_api_football_indisponivel")
                continue
            estado["evento_externo_id"] = fixture_id
            odds = {"ao_vivo": []}
            oferta = None
            modo_coleta = modo_coleta_estado_clv(
                item.get("fonte_odds"), item.get("bookmaker_odds")
            )
            if modo_coleta is None:
                resumo["falhas"] += 1
                motivo("fonte_entrada_estado_clv_nao_suportada")
                continue
            if modo_coleta == "somente_estado":
                resumo["somente_estado"] += 1
            else:
                try:
                    odds_betsapi, diagnostico = cliente_betsapi.buscar_mercados(
                    {
                        "url": item["packball_url"],
                        "mandante": item["mandante"],
                        "visitante": item["visitante"],
                        "placar": estado["placar"],
                        "status": estado["status"],
                    },
                    {item["mercado"]},
                )
                    diagnostico = (
                        diagnostico if isinstance(diagnostico, dict) else {}
                    )
                    if isinstance(odds_betsapi, dict):
                        odds = odds_betsapi
                    oferta_candidata = extrair_odd_exata_acompanhamento(
                        odds, item["mercado"], item["linha"]
                    )
                    if (
                        isinstance(oferta_candidata, dict)
                        and str(oferta_candidata.get("fonte") or "")
                            .strip().casefold() == "betsapi"
                        and str(oferta_candidata.get("bookmaker") or "")
                            .strip().casefold() == "bet365"
                    ):
                        oferta = oferta_candidata
                    elif not diagnostico.get("pareado"):
                        motivo(str(
                            diagnostico.get("motivo") or "betsapi_nao_pareada"
                        ))
                except Exception as erro:
                    resumo["falhas"] += 1
                    motivo("falha_isolada_betsapi_clv")
                    resumo.setdefault("erros_itens", []).append({
                        "sinal_id": item.get("sinal_id"),
                        "tipo": type(erro).__name__,
                        "erro": resumir_erro_seguro(erro),
                    })
                    # Falha técnica não pode virar falsa ausência de odd.
                    continue
            resumo["consultados"] += 1

            observacao_oferta_id = None
            if oferta is not None:
                try:
                    observacao = (
                        self.banco.registrar_observacao_acompanhamento_odd(
                            item["sinal_id"],
                            oferta,
                            estado,
                            consultado_em=agora.isoformat(),
                            url_origem=item.get("packball_url"),
                            motivo="clv_pos_alerta",
                            odds=odds,
                        )
                    )
                    if (
                        observacao.get("persistido")
                        and observacao.get("autorizada", True) is not False
                    ):
                        observacao_oferta_id = observacao.get(
                            "observacao_id"
                        )
                        resumo["com_oferta_exata"] += 1
                    else:
                        resumo["falhas"] += 1
                        motivo(str(
                            observacao.get("motivo")
                            or observacao.get("estado")
                            or "oferta_clv_nao_persistida"
                        ))
                except Exception as erro:
                    resumo["falhas"] += 1
                    motivo("falha_persistencia_oferta_clv")
                    resumo.setdefault("erros_itens", []).append({
                        "sinal_id": item.get("sinal_id"),
                        "tipo": type(erro).__name__,
                        "erro": resumir_erro_seguro(erro),
                    })
                    # Sem vínculo persistido confiável, não sela a amostra.
                    continue
            if observacao_oferta_id is None:
                resumo["sem_oferta_exata"] += 1
            try:
                registro = self.banco.registrar_estado_clv_pos_alerta(
                    item["sinal_id"],
                    estado,
                    observacao_oferta_id=observacao_oferta_id,
                    consultado_em=agora.isoformat(),
                )
                if registro.get("persistido"):
                    resumo["estados_persistidos"] += 1
                elif registro.get("estado") != "ja_persistido":
                    resumo["falhas"] += 1
                    motivo(str(
                        registro.get("estado") or "estado_clv_nao_persistido"
                    ))
            except Exception as erro:
                resumo["falhas"] += 1
                motivo("falha_persistencia_estado_clv")
                resumo.setdefault("erros_itens", []).append({
                    "sinal_id": item.get("sinal_id"),
                    "tipo": type(erro).__name__,
                    "erro": resumir_erro_seguro(erro),
                })
        resumo["estado"] = (
            "degradada" if resumo["falhas"] else "concluida"
        )
        return resumo

    def _executar_rechecagem_odd_api(self, forcar=False):
        """Executa uma rodada da fila rápida; falhas são tratadas pelo invólucro."""
        resumo = {
            "consultados": 0, "atingiram_alvo": 0, "enviados": 0,
            "bloqueados": 0, "observacoes_odds": 0,
            "anomalias_curva_odds": 0,
            "mudancas_odds": 0, "estados_decisivos": 0,
            "comparacoes_odds_fontes": 0,
            "corroboracoes_api_football_solicitadas": 0,
            "corroboracoes_api_football_disponiveis": 0,
            "comparacoes_corroboracao_odds": 0,
            "referencias_sombra_rapidas_tentadas": 0,
            "referencias_sombra_rapidas_reservadas": 0,
            "referencias_sombra_rapidas_consultadas": 0,
            "referencias_sombra_rapidas_linha_exata": 0,
            "referencias_sombra_rapidas_auditadas": 0,
            "referencias_sombra_rapidas_observadas": 0,
            "comparacoes_referencia_sombra_rapida": 0,
            "creditos_estimados_referencia_sombra_rapida": 0,
            "aplicacao_sinais_referencia_sombra": False,
            "referencias_sombra_rapidas_motivos": {},
            "referencias_sombra_rapidas_funil": {
                "versao": "funil-referencia-sombra-rapida-v1",
                "avaliadas": 0,
                "aprovadas": 0,
                "reprovadas": 0,
                "com_oferta": 0,
                "bloqueadas_custodia": 0,
                "bloqueadas_materializacao": 0,
                "alertas_enviados": 0,
                "fontes_executaveis_pos_envio": 0,
                "selecionadas_para_consulta": 0,
                "suprimidas_limite_rodada": 0,
                "exclusoes": {},
                "aplicacao_sinais": False,
                "telegram": False,
            },
            "avisos_resultado_atualizados": 0,
            "marcacoes_rodizio": 0,
            "fila_total": 0,
            "fila_tecnica_recente": 0,
            "fila_tecnica_dormente": 0,
            "fila_recente_nunca_consultada": 0,
            "fila_pendente_apos_lote": 0,
            "motivos": {},
        }
        if os.getenv("ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO", "1") != "1":
            resumo["motivo"] = "desativado"
            return resumo
        intervalo = self._intervalo_trabalhador_acompanhamento_odd()
        agora_mono = time.monotonic()
        ultima_rechecagem = float(
            getattr(self, "_ultima_rechecagem_odd_api", 0.0) or 0.0
        )
        if (
            not forcar
            and agora_mono - ultima_rechecagem < intervalo
        ):
            resumo["motivo"] = "intervalo_curto"
            return resumo
        self._ultima_rechecagem_odd_api = agora_mono
        cliente_betsapi = getattr(self, "betsapi", None)
        betsapi_ativa = bool(
            getattr(cliente_betsapi, "aplicacao_sinais", False)
        )
        cliente_api_football = getattr(self, "api", None)
        api_football_ativa = bool(
            callable(getattr(
                cliente_api_football, "fixtures_ao_vivo_detalhadas", None
            ))
            and any(callable(getattr(
                cliente_api_football, metodo, None
            )) for metodo in (
                "odds_gols_total_ft",
                "odds_gols_total_ht",
                "odds_proximo_gol",
            ))
        )
        if not betsapi_ativa and not api_football_ativa:
            resumo["motivo"] = "fontes_odds_api_indisponiveis"
            return resumo
        gate = self._validar_operacao_para_alerta_oficial()
        if gate.get("apto") is not True:
            resumo["motivo"] = gate.get("motivo") or "operacao_bloqueada"
            return resumo
        try:
            ttl = min(max(float(os.getenv(
                "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS", "900"
            )), 60.0), 1200.0)
        except (TypeError, ValueError):
            ttl = 900.0
        try:
            lote = min(max(int(os.getenv(
                "ACOMPANHAMENTO_ODD_API_LOTE", "10"
            )), 1), 20)
        except (TypeError, ValueError):
            lote = 10
        resumo["lote_maximo"] = lote
        try:
            maximo_referencias_rapidas = min(max(int(os.getenv(
                "THE_ODDS_API_AMOSTRAGEM_RAPIDA_MAXIMO_RODADA", "1"
            )), 0), 2)
        except (TypeError, ValueError):
            maximo_referencias_rapidas = 1
        resumo["referencias_sombra_rapidas_maximo_rodada"] = (
            maximo_referencias_rapidas
        )
        referencias_rapidas_usadas = 0
        snapshot_desde = (
            datetime.now() - timedelta(seconds=ttl)
        ).replace(microsecond=0).isoformat()
        itens_brutos = [
            dict(item) for item in
            self.banco.acompanhamentos_odd_para_rechecagem_api(
                lote, snapshot_desde=snapshot_desde
            )
        ]
        if itens_brutos:
            cabecalho_fila = itens_brutos[0]
            def contagem_fila(chave, padrao):
                valor = cabecalho_fila.get(chave)
                try:
                    return int(padrao if valor is None else valor)
                except (TypeError, ValueError):
                    return int(padrao)

            resumo["fila_total"] = contagem_fila(
                "fila_total", len(itens_brutos)
            )
            resumo["fila_tecnica_recente"] = contagem_fila(
                "fila_tecnica_recente_total", len(itens_brutos)
            )
            resumo["fila_tecnica_dormente"] = contagem_fila(
                "fila_tecnica_dormente_total", 0
            )
            resumo["fila_recente_nunca_consultada"] = contagem_fila(
                "fila_recente_nunca_consultada", 0
            )
        itens = []
        for item in itens_brutos:
            if not mercado_acompanhamento_odd_autorizado(
                item.get("mercado")
            ):
                motivo = "mercado_fora_carteira_acompanhamento_odd"
                resumo["motivos"][motivo] = (
                    resumo["motivos"].get(motivo, 0) + 1
                )
                continue
            meta_metodo = self._json_seguro(item.get("features_json"), {}).get(
                "acompanhamento_metodo_gols"
            )
            ttl_item = min(ttl, IDADE_MAXIMA_REANALISE_SEGUNDOS) if meta_metodo else ttl
            try:
                instante = datetime.fromisoformat(
                    str(item.get("snapshot_em") or "").replace("Z", "+00:00")
                )
                agora_snapshot = (
                    datetime.now(instante.tzinfo)
                    if instante.tzinfo is not None else datetime.now()
                )
                idade_snapshot = (
                    agora_snapshot - instante
                ).total_seconds()
            except (TypeError, ValueError):
                idade_snapshot = None
            if (
                idade_snapshot is None
                or idade_snapshot < -1.0
                or idade_snapshot > ttl_item
            ):
                motivo = "leitura_tecnica_expirada"
                resumo["motivos"][motivo] = (
                    resumo["motivos"].get(motivo, 0) + 1
                )
                continue
            itens.append(item)
        resumo["fila_pendente_apos_lote"] = max(
            resumo["fila_tecnica_recente"] - len(itens), 0
        )
        if not itens:
            resumo["motivo"] = (
                "sem_acompanhamento_pendente"
                if not itens_brutos else "sem_acompanhamento_tecnico_recente"
            )
            return resumo
        ids = sorted({
            int(item["api_fixture_id"])
            for item in itens if item.get("api_fixture_id") is not None
        })
        if not ids:
            resumo["motivo"] = "sem_fixture_api_confirmado"
            return resumo
        fixtures = self.api.fixtures_ao_vivo_detalhadas(ids)
        por_id = {
            int((fixture.get("fixture") or {}).get("id")): fixture
            for fixture in fixtures or []
            if (fixture.get("fixture") or {}).get("id") is not None
        }

        def amostrar_referencia_rapida(
            item_atual,
            estado_atual,
            oferta_atual,
            odds_atuais,
            sinal_enviado_id,
        ):
            nonlocal referencias_rapidas_usadas
            funil_referencia = resumo[
                "referencias_sombra_rapidas_funil"
            ]

            def excluir(motivo):
                exclusoes = funil_referencia["exclusoes"]
                exclusoes[motivo] = exclusoes.get(motivo, 0) + 1

            fonte_atual = str(
                (oferta_atual or {}).get("fonte") or ""
            ).strip().casefold()
            bookmaker_atual = str(
                (oferta_atual or {}).get("bookmaker") or ""
            ).strip().casefold()
            mercado_atual = str(
                item_atual.get("mercado") or ""
            ).strip().casefold()
            if fonte_atual != "betsapi":
                excluir("fonte_pos_envio_nao_e_betsapi")
                return
            if bookmaker_atual != "bet365":
                excluir("bookmaker_pos_envio_nao_e_bet365")
                return
            if mercado_atual not in {"gol_ft", "gol_ht"}:
                excluir("mercado_pos_envio_nao_suportado")
                return
            funil_referencia["fontes_executaveis_pos_envio"] += 1
            if referencias_rapidas_usadas >= maximo_referencias_rapidas:
                funil_referencia["suprimidas_limite_rodada"] += 1
                excluir("limite_referencias_rapidas_rodada")
                return
            funil_referencia["selecionadas_para_consulta"] += 1
            referencias_rapidas_usadas += 1
            try:
                referencia = self._amostrar_referencia_odd_monitor_rapido(
                    item_atual,
                    estado_atual,
                    oferta_atual,
                    odds_atuais,
                    sinal_enviado_id=sinal_enviado_id,
                )
            except Exception as erro:
                referencia = {
                    "tentada": True,
                    "motivo": "falha_isolada_referencia_sombra_rapida",
                    "tipo_erro": type(erro).__name__,
                    "erro": resumir_erro_seguro(erro),
                    "aplicacao_sinais": False,
                }
            resumo["referencias_sombra_rapidas_tentadas"] += int(
                bool(referencia.get("tentada"))
            )
            resumo["referencias_sombra_rapidas_reservadas"] += int(
                bool(referencia.get("reserva_consumida"))
            )
            resumo["referencias_sombra_rapidas_consultadas"] += int(
                bool(referencia.get("consulta_executada"))
            )
            resumo["referencias_sombra_rapidas_linha_exata"] += int(
                bool(referencia.get("linha_exata"))
            )
            resumo["referencias_sombra_rapidas_auditadas"] += int(
                bool(referencia.get("auditoria_persistida"))
            )
            resumo["referencias_sombra_rapidas_observadas"] += int(
                bool(referencia.get("observacao_persistida"))
            )
            novas_comparacoes = int(
                referencia.get("comparacoes_persistidas") or 0
            )
            resumo["comparacoes_referencia_sombra_rapida"] += (
                novas_comparacoes
            )
            resumo["comparacoes_odds_fontes"] += novas_comparacoes
            resumo["creditos_estimados_referencia_sombra_rapida"] += int(
                referencia.get("creditos_estimados_reservados") or 0
            )
            motivo_referencia = str(
                referencia.get("motivo") or "indeterminado"
            )
            motivos_referencia = resumo[
                "referencias_sombra_rapidas_motivos"
            ]
            motivos_referencia[motivo_referencia] = (
                motivos_referencia.get(motivo_referencia, 0) + 1
            )
            if referencia.get("aplicacao_sinais") is True:
                # Invariante fail-closed: a coleta jamais pode promover seu
                # próprio resultado para a decisão que já foi calculada.
                resumo["aplicacao_sinais_referencia_sombra"] = True

        for item in itens:
            resumo["consultados"] += 1
            try:
                marcacao = (
                    self.banco.registrar_consulta_acompanhamento_odd_api(
                        item["origem_sinal_id"],
                        consultado_em=datetime.now().replace(
                            microsecond=0
                        ).isoformat(),
                    )
                )
                if marcacao.get("persistido"):
                    resumo["marcacoes_rodizio"] += 1
            except Exception as erro:
                motivo_rodizio = "falha_marcacao_rodizio_api"
                resumo["motivos"][motivo_rodizio] = (
                    resumo["motivos"].get(motivo_rodizio, 0) + 1
                )
                resumo.setdefault("erros_itens", []).append({
                    "origem_sinal_id": item.get("origem_sinal_id"),
                    "tipo": type(erro).__name__,
                    "erro": resumir_erro_seguro(erro),
                })
            try:
                fixture_id = int(item.get("api_fixture_id"))
            except (TypeError, ValueError):
                motivo = "fixture_api_indeterminado"
                resumo["motivos"][motivo] = resumo["motivos"].get(motivo, 0) + 1
                continue
            fixture = por_id.get(fixture_id)
            estado = (
                self._estado_fixture_acompanhamento_odd(item, fixture)
                if fixture else None
            )
            if estado is None:
                motivo = "estado_api_indisponivel"
                resumo["motivos"][motivo] = resumo["motivos"].get(motivo, 0) + 1
                continue
            jogo = {
                "url": item["packball_url"],
                "mandante": item["mandante"],
                "visitante": item["visitante"],
                "placar": estado["placar"],
                "status": estado["status"],
            }
            odds = {"ao_vivo": []}
            diagnostico = {"pareado": False, "motivo": "sem_oferta_betsapi"}
            if betsapi_ativa:
                try:
                    odds_betsapi, diagnostico = (
                        cliente_betsapi.buscar_mercados(
                            jogo, {item["mercado"]}
                        )
                    )
                    if isinstance(odds_betsapi, dict):
                        odds = odds_betsapi
                except Exception as erro:
                    motivo_fonte = "falha_isolada_betsapi_item"
                    resumo["motivos"][motivo_fonte] = (
                        resumo["motivos"].get(motivo_fonte, 0) + 1
                    )
                    resumo.setdefault("erros_itens", []).append({
                        "fixture_id": fixture_id,
                        "fonte": "betsapi",
                        "tipo": type(erro).__name__,
                        "erro": resumir_erro_seguro(erro),
                    })
            else:
                diagnostico = {
                    "pareado": False,
                    "motivo": "betsapi_indisponivel",
                }
            try:
                cobertura_api = (
                    self._complementar_odd_exata_acompanhamento_api(
                        odds, item, estado
                    )
                )
            except Exception as erro:
                cobertura_api = {
                    "complementado": False,
                    "motivo": "falha_isolada_api_football_odds_item",
                }
                motivo_fonte = cobertura_api["motivo"]
                resumo["motivos"][motivo_fonte] = (
                    resumo["motivos"].get(motivo_fonte, 0) + 1
                )
                resumo.setdefault("erros_itens", []).append({
                    "fixture_id": fixture_id,
                    "fonte": "api_football_odds",
                    "tipo": type(erro).__name__,
                    "erro": resumir_erro_seguro(erro),
                })
            try:
                acompanhamento = (
                    self._json_seguro(item.get("features_json"), {}).get(
                        "acompanhamento_odd"
                    ) or {}
                )
                avaliacao = avaliar_rechecagem_odd_api(
                    acompanhamento,
                    mercado=item["mercado"],
                    linha=item["linha"],
                    placar_origem=item["placar_origem"],
                    snapshot_em=item["snapshot_em"],
                    jogo_atual=estado,
                    odds=odds,
                    ttl_tecnico_segundos=ttl,
                )
            except Exception as erro:
                motivo = "falha_isolada_item_api"
                resumo["motivos"][motivo] = (
                    resumo["motivos"].get(motivo, 0) + 1
                )
                resumo.setdefault("erros_itens", []).append({
                    "fixture_id": fixture_id,
                    "tipo": type(erro).__name__,
                    "erro": resumir_erro_seguro(erro),
                })
                continue
            motivo = avaliacao["motivo"]
            if (
                not diagnostico.get("pareado")
                and not cobertura_api.get("complementado")
            ):
                motivo = diagnostico.get("motivo") or motivo
            terminal_api = str(
                estado.get("status_codigo") or ""
            ).upper() in {"FT", "AET", "PEN", "CANC", "ABD", "PST"}
            if motivo in {"placar_alterado", "primeiro_tempo_encerrado"} or (
                motivo == "partida_nao_operacional" and terminal_api
            ):
                try:
                    desfecho = self._registrar_desfecho_acompanhamento_odd_api(
                        item, fixture, estado, motivo
                    )
                    if desfecho.get("estado") == "registrado":
                        resumo["estados_decisivos"] += 1
                        resumo["avisos_resultado_atualizados"] += int(
                            desfecho.get("avisos_atualizados") or 0
                        )
                except Exception as erro:
                    motivo_desfecho = "falha_isolada_desfecho_api"
                    resumo["motivos"][motivo_desfecho] = (
                        resumo["motivos"].get(motivo_desfecho, 0) + 1
                    )
                    resumo.setdefault("erros_itens", []).append({
                        "fixture_id": fixture_id,
                        "tipo": type(erro).__name__,
                        "erro": resumir_erro_seguro(erro),
                    })
            oferta_monitorada = avaliacao.get("oferta")
            funil_referencia = resumo[
                "referencias_sombra_rapidas_funil"
            ]
            funil_referencia["avaliadas"] += 1
            if avaliacao.get("aprovada") is True:
                funil_referencia["aprovadas"] += 1
            else:
                funil_referencia["reprovadas"] += 1
                motivo_funil = f"decisao_reprovada:{motivo}"
                exclusoes_funil = funil_referencia["exclusoes"]
                exclusoes_funil[motivo_funil] = (
                    exclusoes_funil.get(motivo_funil, 0) + 1
                )
            if oferta_monitorada:
                funil_referencia["com_oferta"] += 1
            corroboracao_api = {
                "complementado": False,
                "motivo": "corroboracao_nao_solicitada",
            }
            fonte_monitorada = str(
                (oferta_monitorada or {}).get("fonte") or ""
            ).strip().casefold()
            if (
                avaliacao.get("aprovada") is True
                and oferta_monitorada
                and fonte_monitorada != "api_football"
                and api_football_ativa
            ):
                resumo["corroboracoes_api_football_solicitadas"] += 1
                try:
                    corroboracao_api = (
                        self._complementar_odd_exata_acompanhamento_api(
                            odds,
                            item,
                            estado,
                            forcar_controle=True,
                        )
                    )
                    if corroboracao_api.get("complementado"):
                        resumo[
                            "corroboracoes_api_football_disponiveis"
                        ] += 1
                except Exception as erro:
                    corroboracao_api = {
                        "complementado": False,
                        "motivo": "falha_corroboracao_api_football",
                    }
                    motivo_corroboracao = corroboracao_api["motivo"]
                    resumo["motivos"][motivo_corroboracao] = (
                        resumo["motivos"].get(motivo_corroboracao, 0) + 1
                    )
                    resumo.setdefault("erros_itens", []).append({
                        "fixture_id": fixture_id,
                        "fonte": "api_football_odds_controle",
                        "tipo": type(erro).__name__,
                        "erro": resumir_erro_seguro(erro),
                    })
            observacao_ordenada = True
            observacao_autorizada = True
            if oferta_monitorada:
                try:
                    observacao = (
                        self.banco.registrar_observacao_acompanhamento_odd(
                            item["origem_sinal_id"],
                            oferta_monitorada,
                            estado,
                            consultado_em=datetime.now().replace(
                                microsecond=0
                            ).isoformat(),
                            url_origem=item.get("packball_url"),
                            motivo=motivo,
                            odds=odds,
                        )
                    )
                    if observacao.get("persistido"):
                        resumo["observacoes_odds"] += 1
                        if observacao.get("estado") == "anomalia_curva_odd":
                            resumo["anomalias_curva_odds"] += 1
                    else:
                        observacao_autorizada = False
                        motivo = str(
                            observacao.get("motivo")
                            or observacao.get("estado")
                            or "observacao_odd_nao_persistida"
                        )
                    if observacao.get("autorizada") is False:
                        observacao_autorizada = False
                        motivo = str(
                            observacao.get("motivo")
                            or observacao.get("estado")
                            or "observacao_odd_nao_autorizada"
                        )
                    if observacao.get("ordem_temporal_valida") is False:
                        observacao_ordenada = False
                    if observacao.get(
                        "mudanca_material", observacao.get("nova_linha")
                    ):
                        resumo["mudancas_odds"] += 1
                except Exception as erro:
                    motivo_auditoria = "falha_auditoria_trajetoria_odd"
                    motivo = motivo_auditoria
                    observacao_autorizada = False
                    resumo.setdefault("erros_itens", []).append({
                        "fixture_id": fixture_id,
                        "tipo": type(erro).__name__,
                        "erro": resumir_erro_seguro(erro),
                    })
                registrar_comparacao = getattr(
                    self.banco,
                    "registrar_comparacao_acompanhamento_odd_api",
                    None,
                )
                if (
                    callable(registrar_comparacao)
                    and observacao_ordenada
                    and observacao_autorizada
                ):
                    try:
                        auditoria_desajuste = registrar_comparacao(
                            item["sinal_id"], oferta_monitorada, estado,
                            consultado_em=datetime.now().replace(
                                microsecond=0
                            ).isoformat(),
                        )
                        resumo["comparacoes_odds_fontes"] += int(
                            auditoria_desajuste.get("persistidos") or 0
                        )
                    except Exception as erro:
                        motivo_desajuste = (
                            "falha_auditoria_desajuste_odd_rapida"
                        )
                        resumo["motivos"][motivo_desajuste] = (
                            resumo["motivos"].get(motivo_desajuste, 0) + 1
                        )
                        resumo.setdefault("erros_itens", []).append({
                            "fixture_id": fixture_id,
                            "tipo": type(erro).__name__,
                            "erro": resumir_erro_seguro(erro),
                        })
            if not observacao_ordenada:
                motivo = "regressao_temporal_observacao_odd"
                observacao_autorizada = False
            registrar_corroboracao = getattr(
                self.banco,
                "registrar_corroboracao_acompanhamento_odd_api",
                None,
            )
            if (
                callable(registrar_corroboracao)
                and observacao_ordenada
                and observacao_autorizada
                and corroboracao_api.get("complementado") is True
            ):
                try:
                    evidencia_corroboracao = registrar_corroboracao(
                        item["origem_sinal_id"],
                        odds,
                        estado,
                        consultado_em=datetime.now().replace(
                            microsecond=0
                        ).isoformat(),
                    )
                    resumo["comparacoes_corroboracao_odds"] += int(
                        evidencia_corroboracao.get("persistidos") or 0
                    )
                except Exception as erro:
                    motivo_corroboracao = (
                        "falha_persistencia_corroboracao_odds"
                    )
                    resumo["motivos"][motivo_corroboracao] = (
                        resumo["motivos"].get(motivo_corroboracao, 0) + 1
                    )
                    resumo.setdefault("erros_itens", []).append({
                        "fixture_id": fixture_id,
                        "tipo": type(erro).__name__,
                        "erro": resumir_erro_seguro(erro),
                    })
            resumo["motivos"][motivo] = resumo["motivos"].get(motivo, 0) + 1
            if not observacao_autorizada:
                # A linha continua no histórico para auditoria, mas nunca
                # representa uma prova autorizada e não pode disparar entrada.
                resumo["bloqueados"] += 1
                funil_referencia["bloqueadas_custodia"] += 1
                exclusoes_funil = funil_referencia["exclusoes"]
                chave_exclusao = f"custodia_bloqueada:{motivo}"
                exclusoes_funil[chave_exclusao] = (
                    exclusoes_funil.get(chave_exclusao, 0) + 1
                )
                continue
            if avaliacao.get("aprovada") is not True:
                # A cota independente é reservada para entradas realmente
                # enviadas. Reprovações permanecem explicadas no funil, sem
                # competir com o sinal oficial pela única vaga da rodada.
                continue
            resumo["atingiram_alvo"] += 1
            try:
                resultado = self._materializar_entrada_acompanhamento_odd_api(
                    item, fixture, estado, odds, avaliacao
                )
            except Exception as erro:
                motivo = "falha_isolada_materializacao"
                resumo["motivos"][motivo] = (
                    resumo["motivos"].get(motivo, 0) + 1
                )
                resumo.setdefault("erros_itens", []).append({
                    "fixture_id": fixture_id,
                    "tipo": type(erro).__name__,
                    "erro": resumir_erro_seguro(erro),
                })
                resumo["bloqueados"] += 1
                funil_referencia["bloqueadas_materializacao"] += 1
                exclusoes_funil = funil_referencia["exclusoes"]
                exclusoes_funil["falha_materializacao"] = (
                    exclusoes_funil.get("falha_materializacao", 0) + 1
                )
                continue
            if resultado.get("estado") == "enviado":
                resumo["enviados"] += 1
                funil_referencia["alertas_enviados"] += 1
                print(
                    "  Telegram: odd monitorada atingiu a faixa; "
                    "entrada revalidada pelas APIs e enviada"
                )
                # O alerta já foi materializado. Só agora a referência sombra
                # pode usar a vaga da rodada, sem adicionar latência ou mudar
                # a decisão operacional.
                amostrar_referencia_rapida(
                    item,
                    estado,
                    oferta_monitorada,
                    odds,
                    resultado.get("sinal_id"),
                )
            else:
                resumo["bloqueados"] += 1
                funil_referencia["bloqueadas_materializacao"] += 1
                estado_resultado = resultado.get("estado") or "bloqueado"
                resumo["motivos"][estado_resultado] = (
                    resumo["motivos"].get(estado_resultado, 0) + 1
                )
                exclusoes_funil = funil_referencia["exclusoes"]
                chave_exclusao = f"materializacao_bloqueada:{estado_resultado}"
                exclusoes_funil[chave_exclusao] = (
                    exclusoes_funil.get(chave_exclusao, 0) + 1
                )
        return resumo

    def _executar_avaliacao_periodica_persistente(
        self, *, arquivo, evento, versao, modo,
        motivo_falha, executar, transformar=None,
    ):
        """Executa avaliador sob custodia fail-closed comum e atomica."""
        caminho_estado = self.pasta / arquivo
        inicio_monotonic = time.monotonic()
        iniciado_em = datetime.now().replace(microsecond=0).isoformat()
        registrar = getattr(
            getattr(self, "observabilidade", None),
            "ciclo_progresso", None,
        )

        def registrar_seguro(dados):
            if callable(registrar):
                try:
                    registrar(evento, **dados)
                except Exception:
                    pass

        em_andamento = construir_estado_nao_concluido(
            versao_avaliacao=versao,
            modo=modo,
            estado_execucao=ESTADO_AVALIACAO_EM_ANDAMENTO,
            atualizado_em=iniciado_em,
            iniciado_em=iniciado_em,
        )
        try:
            gravar_json_atomico(caminho_estado, em_andamento)
        except Exception as erro:
            falha = construir_estado_nao_concluido(
                versao_avaliacao=versao,
                modo=modo,
                estado_execucao=ESTADO_AVALIACAO_FALHA,
                atualizado_em=iniciado_em,
                iniciado_em=iniciado_em,
                finalizado_em=iniciado_em,
                duracao_segundos=0.0,
                motivo_falha=motivo_falha,
                tipo_erro=type(erro).__name__,
                erro=resumir_erro_seguro(erro),
            )
            falha["estado"] = "falha_persistencia_inicio"
            falha["persistencia_estado"] = "falhou"
            registrar_seguro(falha)
            return falha
        try:
            avaliacao = executar()
            if transformar is not None:
                avaliacao = transformar(avaliacao)
            avaliacao = enriquecer_avaliacao_com_exposicao(
                avaliacao,
                pasta=self.pasta,
                modo_manutencao=ler_modo_manutencao(self.pasta),
            )
            avaliacao = aplicar_efeitos_desativados(avaliacao)
            if avaliacao.get("versao") != versao:
                raise RuntimeError("versao de avaliacao inesperada")
            if (
                avaliacao.get("custodia_execucao_versao")
                != VERSAO_CUSTODIA_AVALIACAO
                or avaliacao.get("estado_execucao")
                != ESTADO_AVALIACAO_CONCLUIDO
            ):
                raise RuntimeError("custodia de avaliacao incompleta")
            finalizado_em = datetime.now().replace(
                microsecond=0
            ).isoformat()
            avaliacao.update({
                "iniciado_em": iniciado_em,
                "finalizado_em": finalizado_em,
                "atualizado_em": finalizado_em,
                "duracao_segundos": round(max(
                    time.monotonic() - inicio_monotonic, 0.0
                ), 3),
            })
            gravar_json_atomico(caminho_estado, avaliacao)
            registrar_seguro(avaliacao)
            return avaliacao
        except Exception as erro:
            finalizado_em = datetime.now().replace(
                microsecond=0
            ).isoformat()
            falha = construir_estado_nao_concluido(
                versao_avaliacao=versao,
                modo=modo,
                estado_execucao=ESTADO_AVALIACAO_FALHA,
                atualizado_em=finalizado_em,
                iniciado_em=iniciado_em,
                finalizado_em=finalizado_em,
                duracao_segundos=max(
                    time.monotonic() - inicio_monotonic, 0.0
                ),
                motivo_falha=motivo_falha,
                tipo_erro=type(erro).__name__,
                erro=resumir_erro_seguro(erro),
            )
            try:
                gravar_json_atomico(caminho_estado, falha)
                falha["persistencia_estado"] = "confirmada"
            except Exception as erro_persistencia:
                falha["persistencia_estado"] = "falhou"
                falha["erro_persistencia"] = resumir_erro_seguro(
                    erro_persistencia
                )
            registrar_seguro(falha)
            return falha

    def _avaliar_acompanhamento_odd_prospectivo(self, forcar=False):
        """Observa vantagem da espera sem promover ou alterar regras."""
        try:
            intervalo = min(max(float(os.getenv(
                "ACOMPANHAMENTO_ODD_AVALIACAO_INTERVALO_SEGUNDOS", "900"
            )), 60.0), 3600.0)
        except (TypeError, ValueError):
            intervalo = 900.0
        agora = time.monotonic()
        ultima = float(getattr(
            self, "_ultima_avaliacao_acompanhamento_odd", 0.0
        ) or 0.0)
        if not forcar and agora - ultima < intervalo:
            return {"estado": "intervalo_curto", "aplicacao_sinais": False}
        self._ultima_avaliacao_acompanhamento_odd = agora
        return self._executar_avaliacao_periodica_persistente(
            arquivo="avaliacao_acompanhamento_odd_estado.json",
            evento="avaliacao_estrategia_aguardar_odd",
            versao=VERSAO_AVALIACAO_ACOMPANHAMENTO_ODD,
            modo="avaliacao_prospectiva",
            motivo_falha="avaliacao_acompanhamento_odd_falhou",
            executar=lambda: avaliar_estrategia_acompanhamento_odd(
                self.banco, limite=500
            ),
            transformar=lambda avaliacao: {
                chave: valor for chave, valor in avaliacao.items()
                if chave != "detalhes"
            },
        )

    def _avaliar_prioridade_ligas_gols_prospectiva(self, forcar=False):
        """Mede a fila sazonal sem alterar prioridade, mercado ou sinal."""
        try:
            intervalo = min(max(float(os.getenv(
                "PRIORIZACAO_LIGAS_GOLS_AVALIACAO_INTERVALO_SEGUNDOS",
                "900",
            )), 60.0), 3600.0)
        except (TypeError, ValueError):
            intervalo = 900.0
        agora = time.monotonic()
        ultima = float(getattr(
            self, "_ultima_avaliacao_prioridade_ligas_gols", 0.0
        ) or 0.0)
        if not forcar and agora - ultima < intervalo:
            return {"estado": "intervalo_curto", "aplicacao_sinais": False}
        self._ultima_avaliacao_prioridade_ligas_gols = agora
        return self._executar_avaliacao_periodica_persistente(
            arquivo="avaliacao_prioridade_ligas_gols_estado.json",
            evento="avaliacao_prioridade_ligas_gols",
            versao=VERSAO_AVALIACAO_PRIORIDADE_LIGAS,
            modo="avaliacao_prospectiva",
            motivo_falha="avaliacao_prioridade_ligas_gols_falhou",
            executar=lambda: avaliar_prioridade_ligas_gols(
                self.banco, limite=10000
            ),
        )

    def _avaliar_desajuste_odds_prospectivo(self, forcar=False):
        """Mede vantagem de preco sem aprovar, bloquear ou enviar sinal."""
        try:
            intervalo = min(max(float(os.getenv(
                "DESAJUSTE_ODDS_AVALIACAO_INTERVALO_SEGUNDOS", "900",
            )), 60.0), 3600.0)
        except (TypeError, ValueError):
            intervalo = 900.0
        agora = time.monotonic()
        ultima = float(getattr(
            self, "_ultima_avaliacao_desajuste_odds", 0.0
        ) or 0.0)
        if not forcar and agora - ultima < intervalo:
            return {"estado": "intervalo_curto", "aplicacao_sinais": False}
        self._ultima_avaliacao_desajuste_odds = agora
        return self._executar_avaliacao_periodica_persistente(
            arquivo="avaliacao_desajuste_odds_estado.json",
            evento="avaliacao_desajuste_odds",
            versao=VERSAO_AVALIACAO_DESAJUSTE_ODDS,
            modo="sombra_prospectiva",
            motivo_falha="avaliacao_desajuste_odds_falhou",
            executar=lambda: avaliar_desajustes_odds(
                self.banco, limite=20000
            ),
        )

    def _avaliar_quarentena_fallback_ht_prospectiva(self, forcar=False):
        """Mede a quarentena HT sem reativar regra ou enviar mensagem."""
        try:
            intervalo = min(max(float(os.getenv(
                "FALLBACK_HT_AVALIACAO_INTERVALO_SEGUNDOS", "900",
            )), 60.0), 3600.0)
        except (TypeError, ValueError):
            intervalo = 900.0
        agora = time.monotonic()
        ultima = float(getattr(
            self, "_ultima_avaliacao_quarentena_fallback_ht", 0.0
        ) or 0.0)
        if not forcar and agora - ultima < intervalo:
            return {
                "estado": "intervalo_curto",
                "aplicacao_sinais": False,
                "reativacao_automatica": False,
            }
        self._ultima_avaliacao_quarentena_fallback_ht = agora
        return self._executar_avaliacao_periodica_persistente(
            arquivo="avaliacao_quarentena_fallback_ht_estado.json",
            evento="avaliacao_quarentena_fallback_ht",
            versao=VERSAO_AVALIACAO_QUARENTENA_HT,
            modo="avaliacao_prospectiva_silenciosa",
            motivo_falha="avaliacao_quarentena_fallback_ht_falhou",
            executar=lambda: avaliar_quarentena_fallback_ht(
                self.banco, limite=20000
            ),
        )

    def _avaliar_probabilidade_individual_prospectiva(self, forcar=False):
        """Compara previsão contextual e odd sem alterar as entradas."""
        try:
            intervalo = min(max(float(os.getenv(
                "PROBABILIDADE_INDIVIDUAL_AVALIACAO_INTERVALO_SEGUNDOS",
                "300",
            )), 60.0), 3600.0)
        except (TypeError, ValueError):
            intervalo = 300.0
        agora = time.monotonic()
        ultima = float(getattr(
            self, "_ultima_avaliacao_probabilidade_individual", 0.0
        ) or 0.0)
        if not forcar and agora - ultima < intervalo:
            return {
                "estado": "intervalo_curto",
                "aplicacao_sinais": False,
                "telegram": False,
            }
        self._ultima_avaliacao_probabilidade_individual = agora
        return self._executar_avaliacao_periodica_persistente(
            arquivo="avaliacao_probabilidade_individual_estado.json",
            evento="avaliacao_probabilidade_individual",
            versao=VERSAO_AVALIACAO_PROBABILIDADE_INDIVIDUAL,
            modo="sombra_prospectiva",
            motivo_falha="avaliacao_probabilidade_individual_falhou",
            executar=lambda: avaliar_probabilidade_individual(self.banco),
        )

    def _interromper_se_manutencao(self, etapa):
        if self._modo_manutencao_ativo():
            raise ManutencaoSolicitadaError(str(etapa))

    def _aguardar_intervalo_interrompivel(
        self,
        segundos,
        intervalo_segundos=1.0,
        relogio=None,
        dormir=None,
        interromper_fn=None,
        durante_espera_fn=None,
    ):
        """Espera sem atrasar manutenção ou mudança de estado observável."""
        relogio = relogio or time.monotonic
        dormir = dormir or time.sleep
        limite = relogio() + max(float(segundos), 0.0)
        while True:
            if self._modo_manutencao_ativo():
                return True
            if callable(durante_espera_fn):
                try:
                    durante_espera_fn()
                except Exception:
                    # A vigilancia auxiliar e fail-closed e nunca deve
                    # interromper o ciclo principal do PackBall.
                    pass
            if callable(interromper_fn):
                try:
                    if interromper_fn():
                        return True
                except Exception:
                    # O chamador mantém seu gate autoritativo; uma leitura
                    # auxiliar falha não deve encurtar a espera nem liberar
                    # a operação por suposição.
                    pass
            restante = limite - relogio()
            if restante <= 0:
                return False
            dormir(min(float(intervalo_segundos), restante))

    def _aguardar_supervisao_inicial(
        self,
        timeout_segundos=120.0,
        intervalo_segundos=1.0,
        relogio=None,
        dormir=None,
    ):
        """Aguarda o primeiro espelho do watchdog sem abrir o PackBall.

        O monitor e o watchdog nascem em processos diferentes. Logo apos um
        reinicio, o processo do watchdog pode estar ativo enquanto sua
        primeira verificacao ainda nao foi persistida. A espera ocorre uma
        unica vez, e nunca transforma um estado degradado em saudavel.
        """
        relogio = relogio or time.monotonic
        dormir = dormir or time.sleep
        inicio = relogio()
        limite = inicio + max(float(timeout_segundos), 0.0)
        tentativas = 0
        ultimo_gate = {"apto": False, "estado": "inicializando"}

        while True:
            if self._modo_manutencao_ativo():
                return {
                    "saudavel": False,
                    "estado": "manutencao",
                    "tentativas": tentativas,
                    "duracao_segundos": round(relogio() - inicio, 3),
                    "gate": ultimo_gate,
                }

            tentativas += 1
            ultimo_gate = self._validar_operacao_para_alerta_oficial(
                exigir_api_confirmada=False
            )
            agora = relogio()
            if ultimo_gate.get("apto") is True:
                return {
                    "saudavel": True,
                    "estado": "pronta",
                    "tentativas": tentativas,
                    "duracao_segundos": round(agora - inicio, 3),
                    "gate": ultimo_gate,
                }
            if agora >= limite:
                return {
                    "saudavel": False,
                    "estado": "timeout",
                    "tentativas": tentativas,
                    "duracao_segundos": round(agora - inicio, 3),
                    "gate": ultimo_gate,
                }
            dormir(min(float(intervalo_segundos), max(limite - agora, 0.0)))

    def _validar_operacao_para_alerta_oficial(
        self, exigir_api_confirmada=True, *, candidato=None
    ):
        """Gate rápido e fail-closed usado no instante de cada envio."""
        if getattr(self, "_operacao_bloqueada_ciclo", False):
            return {
                "apto": False,
                "estado": "degradado",
                "motivo": "bloqueio_preservado_no_ciclo",
                "fonte": "ciclo",
            }

        from processo_monitor import (
            ARQUIVOS_RUNTIME_WATCHDOG,
            estado_codigo_runtime,
            ler_estado,
            pid_ativo,
            trava_em_uso,
        )

        pasta = Path(self.pasta).resolve()
        estado_watchdog = ler_estado(pasta / "watchdog_estado.json")
        processo_monitor = ler_estado(pasta / "monitor_processo.json")
        processo_watchdog = ler_estado(pasta / "watchdog_processo.json")

        processos_ativos = bool(
            pid_ativo(processo_monitor.get("pid"))
            and pid_ativo(processo_watchdog.get("pid"))
            and trava_em_uso(pasta / "monitor_instancia.lock")
            and trava_em_uso(pasta / "watchdog_instancia.lock")
        )
        if not processos_ativos:
            return {
                "apto": False,
                "estado": "degradado",
                "motivo": "processos_ou_travas_inativos",
                "fonte": "runtime",
            }

        if (
            estado_codigo_runtime(pasta, processo_monitor) != "atualizado"
            or estado_codigo_runtime(
                pasta,
                processo_watchdog,
                ARQUIVOS_RUNTIME_WATCHDOG,
            ) != "atualizado"
        ):
            return {
                "apto": False,
                "estado": "degradado",
                "motivo": "codigo_runtime_desatualizado",
                "fonte": "runtime",
            }

        persistencia = (
            estado_watchdog.get("persistencia_estado_watchdog") or {}
        )
        try:
            persistido_em = datetime.fromisoformat(
                persistencia["persistido_em"]
            )
            monitor_iniciado_em = datetime.fromisoformat(
                processo_monitor["atualizado_em"]
            )
            watchdog_iniciado_em = datetime.fromisoformat(
                processo_watchdog["atualizado_em"]
            )
        except (KeyError, TypeError, ValueError):
            return {
                "apto": False,
                "estado": "inicializando",
                "motivo": "espelho_watchdog_ainda_indisponivel",
                "fonte": "watchdog",
            }

        agora = datetime.now()
        idade_espelho = (agora - persistido_em).total_seconds()
        limite_espelho = 120.0
        try:
            duracao_watchdog = float(
                (
                    estado_watchdog.get("observabilidade_watchdog") or {}
                ).get("duracao_total_segundos")
            )
        except (TypeError, ValueError):
            duracao_watchdog = None
        if (
            duracao_watchdog is not None
            and math.isfinite(duracao_watchdog)
            and duracao_watchdog > 0
        ):
            # O watchdog executa auditorias SQLite/Telegram pesadas. Usa a
            # duração realmente observada com margem de uma rodada, porém
            # mantém um teto rígido para não mascarar supervisor parado.
            limite_espelho = min(
                max(120.0, duracao_watchdog * 2.0 + 30.0),
                300.0,
            )
        if persistido_em < max(monitor_iniciado_em, watchdog_iniciado_em):
            return {
                "apto": False,
                "estado": "inicializando",
                "motivo": "espelho_watchdog_anterior_ao_reinicio",
                "fonte": "watchdog",
            }
        if idade_espelho < -5 or idade_espelho > limite_espelho:
            return {
                "apto": False,
                "estado": "degradado",
                "motivo": "espelho_watchdog_fora_do_prazo",
                "fonte": "watchdog",
            }

        # O estado geral e o indicador historico de fontes do watchdog
        # descrevem ciclos anteriores. Usa-los como gate instantaneo criaria
        # uma recuperacao circular: um ciclo novo teria de ser descartado
        # apenas para provar que a falha antiga acabou. O espelho novo e sua
        # persistencia continuam obrigatorios; API, PackBall e falhas do ciclo
        # sao validados abaixo no instante corrente e permanecem fail-closed.
        if not (
            persistencia.get("saudavel") is True
            and persistencia.get("estado") == "persistido"
        ):
            return {
                "apto": False,
                "estado": "degradado",
                "motivo": "persistencia_watchdog_invalida",
                "fonte": "watchdog",
            }

        if exigir_api_confirmada:
            saude_api_fn = getattr(self.api, "saude_operacional", None)
            try:
                saude_api = (
                    saude_api_fn() if callable(saude_api_fn) else None
                )
            except Exception:
                saude_api = None
            if not isinstance(saude_api, dict) or (
                saude_api.get("saudavel") is not True
            ):
                return {
                    "apto": False,
                    "estado": "degradado",
                    "motivo": "api_nao_confirmada",
                    "fonte": "api_football",
                    "detalhe": (
                        saude_api.get("motivo")
                        if isinstance(saude_api, dict) else None
                    ),
                }

        estado_packball_fn = getattr(
            self.controle_packball, "estado_atual", None
        )
        try:
            estado_packball = (
                estado_packball_fn()
                if callable(estado_packball_fn) else None
            )
        except Exception:
            estado_packball = None
        if not isinstance(estado_packball, dict) or (
            estado_packball.get("ativo") is not False
        ):
            return {
                "apto": False,
                "estado": "degradado",
                "motivo": "packball_em_pausa_preventiva",
                "fonte": "packball",
                "detalhe": (
                    estado_packball.get("motivo")
                    if isinstance(estado_packball, dict) else None
                ),
            }

        # A calibração e o valor esperado do sinal são necessários, mas não
        # bastam para provar vantagem replicável. Somente a rota oficial passa
        # por este gate; candidatos sem probabilidade calibrada continuam no
        # canal de simulação para formar a amostra prospectiva.
        if (
            isinstance(candidato, dict)
            and candidato.get("probabilidade_calibrada") is not None
        ):
            custodia_cotacao = validar_cotacao_executavel_oficial(
                candidato
            )
            if custodia_cotacao.get("apto") is not True:
                return {
                    "apto": False,
                    "estado": "bloqueado",
                    "motivo": "cotacao_oficial_nao_executavel",
                    "fonte": "custodia_cotacao",
                    "detalhe": custodia_cotacao,
                }
            try:
                edge = avaliar_candidato_oficial(
                    self.banco.conexao, candidato
                )
            except Exception as erro:
                return {
                    "apto": False,
                    "estado": "degradado",
                    "motivo": "gate_edge_portfolio_falhou",
                    "fonte": "portfolio_edge",
                    "detalhe": type(erro).__name__,
                }
            if edge.get("apto") is not True:
                return {
                    "apto": False,
                    "estado": "bloqueado",
                    "motivo": "edge_portfolio_nao_comprovado",
                    "fonte": "portfolio_edge",
                    "detalhe": {
                        "estado": edge.get("estado"),
                        "motivo": edge.get("motivo"),
                        "mercado": edge.get("mercado"),
                        "regra_versao": edge.get("regra_versao"),
                    },
                }

        return {"apto": True, "estado": "saudavel"}

    def _avaliar_reinicio_runtime_monitor(self):
        """Pede reinicio limpo quando somente o monitor ficou antigo.

        O watchdog compartilha varios modulos de regras com o monitor. Se os
        dois processos estiverem desatualizados, um reinicio isolado deixaria
        o novo monitor preso ao watchdog antigo; esse caso continua
        fail-closed e exige o fluxo completo de manutencao/preflight. Quando
        apenas o monitor diverge (por exemplo, apos uma correcao operacional
        em ``servico_monitor.py``), ele pode sair no fim do ciclo e ser
        recuperado com seguranca pelo watchdog ainda atual.
        """
        from processo_monitor import (
            ARQUIVOS_RUNTIME_WATCHDOG,
            estado_codigo_runtime,
            ler_estado,
        )

        pasta = Path(self.pasta).resolve()
        estado_monitor = estado_codigo_runtime(
            pasta,
            ler_estado(pasta / "monitor_processo.json"),
        )
        estado_watchdog = estado_codigo_runtime(
            pasta,
            ler_estado(pasta / "watchdog_processo.json"),
            ARQUIVOS_RUNTIME_WATCHDOG,
        )
        solicitado = bool(
            estado_monitor == "reinicio_pendente"
            and estado_watchdog == "atualizado"
        )
        return {
            "solicitado": solicitado,
            "estado_monitor": estado_monitor,
            "estado_watchdog": estado_watchdog,
            "motivo": (
                "codigo_runtime_monitor_desatualizado"
                if solicitado else None
            ),
        }

    @staticmethod
    def _atualizar_bloqueio_operacao_ciclo(
        bloqueado=False,
        gate=None,
        finalizacao_packball=None,
    ):
        """Mantem fail-closed ate o ciclo seguinte apos qualquer degradacao."""
        if bloqueado:
            return True
        if gate is not None and gate.get("apto") is not True:
            return True
        finalizacao_packball = finalizacao_packball or {}
        return bool(
            finalizacao_packball.get("pausa_preventiva")
            or int(finalizacao_packball.get("erros", 0) or 0) > 0
        )

    def _invalidar_alertas_pendentes_ciclo(self):
        pendentes = list(getattr(self, "_alertas_pendentes_ciclo", []))
        ids = [item[0] for item in pendentes]
        alterados = self.banco.invalidar_sinais_operacao_degradada(ids)
        self._alertas_pendentes_ciclo = []
        return alterados

    def _aplicar_integridade_lista_packball(self, diagnostico):
        """Mantem o ciclo fechado quando a propria lista nao se confirma."""
        inconsistente = bool(
            (diagnostico or {}).get("lista_consistente") is False
        )
        if inconsistente:
            self._operacao_bloqueada_ciclo = True
        return inconsistente

    def _pausar_lista_packball_nao_validada(self, minutos=15):
        limite = self.controle_packball.ativar_pausa(
            "lista_packball_nao_validada",
            minutos=minutos,
        )
        self.observabilidade.circuito_packball_ativado(
            "lista_packball_nao_validada",
            limite,
        )
        return limite

    def _registrar_interrupcao_ciclo(self, duracao_segundos, erro):
        """Separa falha real de um ciclo protegido por pausa persistida."""
        pausa_protegida = isinstance(
            erro, PackBallPausaPreventivaError
        )
        if pausa_protegida:
            self.observabilidade.ciclo_pausado_packball(
                duracao_segundos, erro
            )
        else:
            self.observabilidade.ciclo_erro(duracao_segundos, erro)
        return pausa_protegida

    def _sincronizar_sessao_contexto(self, contexto):
        try:
            resultado = sincronizar_storage_state(
                contexto,
                self.arquivo_sessao,
            )
        except Exception as erro:
            self.observabilidade.sessao_contexto(
                atualizada=False,
                motivo="sincronizacao_falhou",
                erro=type(erro).__name__,
            )
            return {
                "atualizada": False,
                "motivo": "sincronizacao_falhou",
                "erro": type(erro).__name__,
            }
        if resultado.get("atualizada"):
            self.observabilidade.sessao_contexto(
                atualizada=True,
                motivo=None,
                expira_em=resultado.get("expira_em"),
            )
            print(
                "Sessao PackBall renovada em memoria e persistida "
                "com seguranca."
            )
        return resultado

    def _despachar_alertas(self, pendentes):
        resumo = {"consultados": 0, "entregues": 0, "bloqueados": 0}
        for sinal_id, candidato, jogo in pendentes:
            resumo["consultados"] += 1
            entrega = self.alertas.avaliar_e_enviar(
                sinal_id, candidato, jogo
            )
            if entrega == "entregue":
                resumo["entregues"] += 1
                print("  Telegram: sinal calibrado enviado")
            elif entrega == "teste_entregue":
                resumo["entregues"] += 1
                print("  Telegram: simulacao enviada (nao apostar)")
            elif entrega == "aviso_insuficiente":
                resumo["entregues"] += 1
                print("  Telegram: aviso de confianca insuficiente enviado")
            elif entrega in (
                "operacao_oficial_degradada",
                "operacao_oficial_bloqueada",
                "operacao_oficial_inicializando",
                "gate_operacao_oficial_falhou",
                "gate_operacao_oficial_indisponivel",
            ):
                resumo["bloqueados"] += 1
        return resumo

    def preparar(self):
        for aviso in self.configuracao["avisos"]:
            print(f"Aviso de configuração: {aviso}")
        cota = self.api.sincronizar_cota_status()
        if cota["sincronizado"]:
            print(
                "Cota API-Football confirmada pelo provedor — "
                f"{cota['consumo_dia']}/{cota['limite_diario']} UTC."
            )
        else:
            print(
                "Cota API-Football não confirmada na inicialização; "
                "mantendo o contador local conservador."
            )
        catalogo_odds = self.api.validar_catalogo_odds_ao_vivo()
        print(
            "Catálogo de odds ao vivo da API-Football: "
            f"{catalogo_odds.get('estado', 'indisponível')} | "
            "Asian Corners 2T="
            f"{'disponível' if catalogo_odds.get('asiatico_2t_disponivel') else 'não oferecido'}"
        )
        self.regra_fingerprints = {}
        for regra_versao in versoes_regras_operacionais():
            linhagem = registrar_ou_validar_linhagem_regra(
                self.banco.conexao,
                self.pasta,
                regra_versao,
                VERSAO_FEATURES,
            )
            fingerprint = linhagem["fingerprint_atual"]
            self.regra_fingerprints[regra_versao] = fingerprint
            registrar_inicio_linhagem_sinais(
                self.banco.conexao,
                regra_versao,
                fingerprint,
            )
            print(
                "Linhagem da regra confirmada — "
                f"{regra_versao}: {fingerprint[:12]}"
            )
        self.regra_fingerprint = self.regra_fingerprints[VERSAO_REGRAS]
        if not self.arquivo_sessao.exists():
            print("Sessão ausente; realizando login automático...")
            fazer_login(headless=True, manter_aberto=False)
        importados = self.banco.migrar_jsonl(self.arquivo_registros)
        duplicados = self.banco.normalizar_sinais_duplicados()
        self.banco.normalizar_sinais_simulacao()
        revisoes = reabrir_resultados_provisorios(self.banco)
        agora_backup = datetime.now()
        arquivo_backup, backup_criado = self.backup.criar_diario(
            self.banco.conexao, agora_backup
        )
        self._registrar_compactacao_backup("diario")
        arquivo_periodico, periodico_criado = self.backup.criar_periodico(
            self.banco.conexao, agora_backup
        )
        self._registrar_compactacao_backup("periodico")
        self._data_backup_verificada = agora_backup.date()
        self._janela_backup_periodico_verificada = (
            self._janela_backup_periodico(agora_backup)
        )
        manutencao = self.banco.limpar_dados_antigos(dias=180)
        checkpoint = self.banco.checkpoint_wal()
        self._data_manutencao_verificada = datetime.now().date()
        restaurado = self.banco.carregar_historico_recente(minutos=20)
        restaurados = self.historico.restaurar(restaurado)
        self._recalibrar()
        contagens = self.banco.contagens()
        print(
            "Banco SQLite pronto — "
            f"partidas: {contagens['partidas']} | "
            f"snapshots: {contagens['snapshots']} | "
            f"odds: {contagens['odds']}"
        )
        if importados:
            print(f"Histórico JSONL importado: {importados} registros.")
        if restaurados:
            print(f"Histórico temporal restaurado: {restaurados} snapshots.")
        if duplicados:
            print(
                "Sinais repetidos retirados da amostra ativa: "
                f"{duplicados}."
            )
        if revisoes["quantidade"]:
            print(
                "Liquidações provisórias reabertas para conferência "
                f"final: {revisoes['quantidade']}."
            )
        if backup_criado:
            print(f"Backup diário criado: {arquivo_backup.name}")
        if periodico_criado:
            print(
                "Ponto periódico de recuperação criado: "
                f"{arquivo_periodico.name}"
            )
        if manutencao["snapshots"] or manutencao["sinais_descartados"]:
            print(
                "Retenção concluída — snapshots: "
                f"{manutencao['snapshots']} | candidatos descartados: "
                f"{manutencao['sinais_descartados']}"
            )

    def _supervisionar_watchdog(self, garantir_fn=None):
        garantir_fn = garantir_fn or garantir_watchdog_ativo
        try:
            resultado = garantir_fn(self.pasta)
        except Exception as erro:
            self.observabilidade.supervisao_watchdog(erro=erro)
            print(f"Falha ao supervisionar watchdog: {erro}")
            return {
                "estado": "erro",
                "erro": type(erro).__name__,
                "mensagem": str(erro),
            }
        if resultado.get("estado") == "reiniciado":
            self.observabilidade.supervisao_watchdog(
                reiniciado=True, pid=resultado.get("pid")
            )
            print(
                "Watchdog reiniciado automaticamente pelo monitor "
                f"(PID {resultado.get('pid')})."
            )
        return resultado

    def salvar_registro(self, registro):
        rotacionar_arquivo(
            self.arquivo_registros, 20 * 1024 * 1024, copias=5
        )
        with self.arquivo_registros.open("a", encoding="utf-8") as arquivo:
            arquivo.write(
                json.dumps(
                    registro,
                    ensure_ascii=False,
                    default=lambda valor: (
                        valor.isoformat()
                        if isinstance(valor, datetime)
                        else str(valor)
                    ),
                )
                + "\n"
            )
        return self.banco.salvar_registro(registro)

    def _registrar_compactacao_backup(self, tipo):
        resultado = self.backup.ultima_compactacao
        if not resultado:
            return None
        self.observabilidade.compactacao_backup_operacional(
            tipo, resultado
        )
        if resultado.get("fallback_original"):
            print(
                "Compactação do backup adiada; cópia SQLite íntegra "
                f"preservada ({tipo})."
            )
        return resultado

    def _manter_backup_diario(self, agora=None):
        agora = agora or datetime.now()
        if self._data_backup_verificada == agora.date():
            return {"verificado": False, "motivo": "dia_ja_verificado"}
        try:
            caminho, criado = self.backup.criar_diario(
                self.banco.conexao, agora
            )
            self._registrar_compactacao_backup("diario")
        except Exception as erro:
            print(f"Falha no backup diário: {erro}")
            try:
                self.observabilidade.backup_diario(erro=erro)
            except Exception:
                pass
            return {
                "verificado": False,
                "motivo": "backup_falhou",
                "erro": type(erro).__name__,
            }
        self._data_backup_verificada = agora.date()
        self.observabilidade.backup_diario(caminho, criado)
        if criado:
            print(f"Backup diário criado durante a operação: {caminho.name}")
        return {
            "verificado": True,
            "criado": criado,
            "caminho": str(caminho),
        }

    @staticmethod
    def _janela_backup_periodico(agora):
        return (
            agora.date(),
            agora.hour // INTERVALO_BACKUP_PERIODICO_HORAS,
        )

    def _manter_backup_periodico(self, agora=None):
        agora = agora or datetime.now()
        janela = self._janela_backup_periodico(agora)
        if self._janela_backup_periodico_verificada == janela:
            return {"verificado": False, "motivo": "janela_ja_verificada"}
        try:
            caminho, criado = self.backup.criar_periodico(
                self.banco.conexao, agora
            )
            self._registrar_compactacao_backup("periodico")
        except Exception as erro:
            print(f"Falha no backup periódico: {erro}")
            try:
                self.observabilidade.backup_periodico(erro=erro)
            except Exception:
                pass
            return {
                "verificado": False,
                "motivo": "backup_periodico_falhou",
                "erro": type(erro).__name__,
            }
        self._janela_backup_periodico_verificada = janela
        self.observabilidade.backup_periodico(caminho, criado)
        try:
            migracao_legado = self.backup.compactar_legado_mais_antigo(
                agora
            )
            self.observabilidade.compactacao_backup_legado(
                migracao_legado
            )
        except Exception as erro:
            migracao_legado = {
                "saudavel": False,
                "estado": "compactacao_legado_falhou",
                "executado": False,
                "erro": type(erro).__name__,
            }
            try:
                self.observabilidade.compactacao_backup_legado(erro=erro)
            except Exception:
                pass
        if criado:
            print(f"Backup periódico criado: {caminho.name}")
        if migracao_legado.get("executado"):
            if migracao_legado.get("saudavel"):
                print(
                    "Backup antigo compactado e verificado: "
                    f"{migracao_legado.get('origem')} | espaço liberado: "
                    f"{migracao_legado.get('espaco_liberado_mb')} MB"
                )
            else:
                print(
                    "Backup antigo preservado após falha de compactação: "
                    f"{migracao_legado.get('origem')}"
                )
        return {
            "verificado": True,
            "criado": criado,
            "caminho": str(caminho),
            "migracao_backup_legado": migracao_legado,
        }

    def _manter_manutencao_diaria(self, agora=None):
        agora = agora or datetime.now()
        if self._data_manutencao_verificada == agora.date():
            return {"verificado": False, "motivo": "dia_ja_verificado"}
        if self._data_backup_verificada != agora.date():
            return {"verificado": False, "motivo": "aguardando_backup"}
        try:
            resultado = self.banco.limpar_dados_antigos(dias=180)
            checkpoint = self.banco.checkpoint_wal()
        except Exception as erro:
            print(f"Falha na manutenção diária: {erro}")
            try:
                self.observabilidade.manutencao_diaria(erro=erro)
            except Exception:
                pass
            return {
                "verificado": False,
                "motivo": "manutencao_falhou",
                "erro": type(erro).__name__,
            }
        self._data_manutencao_verificada = agora.date()
        self.observabilidade.manutencao_diaria(resultado, checkpoint)
        if resultado["snapshots"] or resultado["sinais_descartados"]:
            print(
                "Manutenção diária concluída — snapshots: "
                f"{resultado['snapshots']} | candidatos descartados: "
                f"{resultado['sinais_descartados']}"
            )
        return {
            "verificado": True,
            "resultado": resultado,
            "checkpoint": checkpoint,
        }

    @staticmethod
    def eh_candidato_api(estatisticas):
        chutes_gol = extrair_par(estatisticas.get("Chutes no gol"))
        ataques = extrair_par(estatisticas.get("Ataques perigosos"))
        return bool(
            chutes_gol is not None
            and ataques is not None
            and sum(chutes_gol) >= 2
            and sum(ataques) >= 20
        )

    @staticmethod
    def _mercados_com_potencial_para_odds_api(candidatos):
        """Seleciona somente mercados que uma odd nova ainda pode aprovar."""
        suportados = {
            "gol_ft",
            "gol_ht",
            "proximo_gol",
            "escanteios_ft_asiatico",
        }
        bloqueios_resolvidos_por_odd = {
            "odd_ao_vivo_indisponivel",
            "odd_fora_da_faixa_operacional",
            "odds_desatualizadas",
            "linha_exige_multiplos_gols",
            "linha_exige_multiplos_escanteios",
        } | set(BLOQUEIOS_PROVENIENCIA)
        mercados = set()
        for candidato in candidatos or []:
            mercado = candidato.get("mercado")
            if mercado not in suportados:
                continue
            bloqueios = set(candidato.get("bloqueios") or [])
            try:
                pontuacao = float(
                    candidato.get("pontuacao_tecnica") or 0
                )
            except (TypeError, ValueError):
                pontuacao = 0.0
            # A presenca da odd pode acrescentar ate cinco pontos no motor.
            # Qualquer outro bloqueio continuaria impedindo o sinal mesmo
            # depois da consulta e, portanto, nao justifica gastar a API.
            if (
                candidato.get("status") == "aprovado"
                or (
                    pontuacao >= 65.0
                    and bloqueios
                    and bloqueios <= bloqueios_resolvidos_por_odd
                )
            ):
                mercados.add(mercado)
        return mercados

    @staticmethod
    def _precisa_contexto_linhas_gols(
        candidatos,
        mercados_para_odds_api,
        *,
        candidato_antecipado=False,
        candidato_capacidade=False,
        candidato_capacidade_v2=False,
        candidato_ht_00_min20=False,
        candidato_ft_tendencia=False,
    ):
        """Decide se os metodos de gol precisam do historico de linhas.

        Os metodos especiais podem gerar um candidato usando uma odd que ja
        veio do PackBall. Nesse caso ``mercados_para_odds_api`` fica vazio,
        embora a protecao de conversao ainda precise das ultimas partidas.
        """
        mercados_gols = {"gol_ft", "gol_ht", "proximo_gol"}
        if mercados_gols & set(mercados_para_odds_api or ()):
            return True
        if any((
            candidato_antecipado,
            candidato_capacidade,
            candidato_capacidade_v2,
            candidato_ht_00_min20,
            candidato_ft_tendencia,
        )):
            return True
        return any(
            item.get("mercado") in mercados_gols
            and item.get("status") in {"aprovado", "simulacao"}
            for item in (candidatos or [])
        )

    @staticmethod
    def _tem_candidato_aprovado(candidatos):
        return any(
            item.get("status") == "aprovado"
            for item in (candidatos or [])
        )

    def precisa_eventos_proximo_gol(self, jogo):
        sinal = self.banco.conexao.execute(
            """
            SELECT inicial.placar
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots inicial ON inicial.id=s.snapshot_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE p.packball_url=? AND s.status='aprovado'
              AND s.mercado='proximo_gol' AND r.sinal_id IS NULL
            ORDER BY s.id LIMIT 1
            """,
            (jogo.get("url"),),
        ).fetchone()
        if sinal is None:
            return False
        inicial = extrair_placar(sinal["placar"])
        atual = extrair_placar(jogo.get("placar"))
        if inicial is None or atual is None:
            return False
        deltas = [atual[indice] - inicial[indice] for indice in range(2)]
        return all(delta > 0 for delta in deltas)

    def _registrar_falha_fonte(self, fonte, jogo, erro, fallback):
        partida = (
            f"{jogo.get('mandante', '?')} x "
            f"{jogo.get('visitante', '?')}"
        )
        print(
            f"  Falha parcial em {fonte}: {erro} | "
            f"fallback: {fallback}"
        )
        try:
            self.observabilidade.fonte_falhou(
                fonte, partida, erro, fallback
            )
        except Exception:
            # A telemetria nunca pode derrubar a coleta principal.
            pass
        return {
            "fonte": fonte,
            "erro": type(erro).__name__,
            "mensagem": str(erro),
            "fallback": fallback,
        }

    def _estado_fontes_para_sinal(self, falhas_fontes):
        falhas_fontes = list(falhas_fontes or [])
        saude_api_fn = getattr(self.api, "saude_operacional", None)
        try:
            saude_api = (
                saude_api_fn() if callable(saude_api_fn) else None
            )
        except Exception as erro:
            saude_api = {
                "saudavel": False,
                "motivo": f"auditoria_api_falhou:{type(erro).__name__}",
            }
        if not isinstance(saude_api, dict):
            saude_api = {
                "saudavel": False,
                "motivo": "auditoria_api_indisponivel",
            }
        motivos = [
            str(item.get("fonte") or "fonte_desconhecida")
            for item in falhas_fontes
            if isinstance(item, dict)
        ]
        if saude_api.get("saudavel") is not True:
            motivos.append(str(
                saude_api.get("motivo") or "api_football_indisponivel"
            ))
        return {
            "saudavel": not motivos,
            "motivos": sorted(set(motivos)),
            "api": saude_api,
        }

    @staticmethod
    def _bloquear_candidatos_por_fontes(candidatos, estado_fontes):
        if estado_fontes.get("saudavel") is True:
            return 0
        bloqueados = 0
        for candidato in candidatos:
            if candidato.get("status") != "aprovado":
                continue
            candidato["status"] = "rejeitado"
            motivos = list(candidato.get("motivos") or [])
            if "fontes_operacionais_incompletas" not in motivos:
                motivos.append("fontes_operacionais_incompletas")
            candidato["motivos"] = motivos
            candidato["bloqueio_fontes"] = list(
                estado_fontes.get("motivos") or []
            )
            bloqueados += 1
        return bloqueados

    @staticmethod
    def _erro_navegador_fatal(erro):
        """Identifica navegador/contexto fechado, inclusive como causa."""
        atual = erro
        visitados = set()
        while atual is not None and id(atual) not in visitados:
            visitados.add(id(atual))
            nome = type(atual).__name__.lower()
            mensagem = str(atual).lower()
            if (
                "targetclosed" in nome
                or "target page, context or browser has been closed" in mensagem
                or "browser has been closed" in mensagem
                or "connection closed while reading from the driver" in mensagem
            ):
                return True
            atual = getattr(atual, "__cause__", None) or getattr(
                atual, "__context__", None
            )
        return False

    def _coletar_estatisticas_seguras(self, pagina, jogo):
        self.packball.ultimo_diagnostico_estatisticas = {
            "versao": "diagnostico-coleta-estatisticas-v3",
            "tentativas_adicionais": 0,
            "campos_essenciais_ausentes": [],
            "campos_lidos": [],
            "quantidade_campos_lidos": 0,
            "nova_navegacao": False,
            "estado": "iniciando",
            "altera_sinal": False,
        }
        try:
            estatisticas = self.packball.coletar_estatisticas(
                pagina, jogo
            ) or {}
            metadados = estatisticas.pop("_metadados", {}) or {}
            estado_detalhado = bool(
                metadados.get("placar") or metadados.get("status")
            )
            observado_em = (
                datetime.now().replace(microsecond=0).isoformat()
                if estado_detalhado else (
                    jogo.get("estado_observado_em")
                    or jogo.get("lista_observada_em")
                )
            )
            jogo_atualizado = {
                **jogo,
                "pais": metadados.get("pais"),
                "liga": metadados.get("liga"),
                "placar": metadados.get("placar") or jogo.get("placar"),
                "status": metadados.get("status") or jogo.get("status"),
                "estado_observado_em": observado_em,
            }
            return estatisticas, jogo_atualizado, None
        except Exception as erro:
            if isinstance(erro, PackBallBloqueadoError):
                raise
            if self._erro_navegador_fatal(erro):
                raise
            falha = self._registrar_falha_fonte(
                "estatisticas_packball", jogo, erro, "estatisticas_vazias"
            )
            return {}, dict(jogo), falha

    def _coletar_odds_seguras(
        self, pagina, jogo, odds_anteriores, coletar_odds_agora
    ):
        if not coletar_odds_agora:
            odds = odds_anteriores or {"pre_jogo": [], "ao_vivo": []}
            odds["movimentacao"] = []
            return odds, None
        try:
            odds = coletar_odds(
                pagina, jogo, getattr(self, "controle_packball", None)
            ) or {
                "pre_jogo": [], "ao_vivo": []
            }
            coletado_em = datetime.now().replace(microsecond=0).isoformat()
            for tipo in ("pre_jogo", "ao_vivo"):
                for mercado in odds.get(tipo) or []:
                    # Este caminho acabou de ler diretamente a pagina do
                    # PackBall; aqui a origem e conhecida, nao inferida.
                    mercado["fonte"] = "packball"
                    mercado["coletado_em"] = coletado_em
                    mercado["cache"] = False
                    mercado["idade_segundos"] = 0.0
            odds["_metadados"] = {
                "cache": False,
                "coletado_em": coletado_em,
                "idade_segundos": 0.0,
            }
            odds["movimentacao"] = calcular_movimento_odds(
                odds_anteriores, odds
            )
            return odds, None
        except Exception as erro:
            if isinstance(erro, PackBallBloqueadoError):
                raise
            if self._erro_navegador_fatal(erro):
                raise
            odds = odds_anteriores or {"pre_jogo": [], "ao_vivo": []}
            odds["movimentacao"] = []
            falha = self._registrar_falha_fonte(
                "odds_packball", jogo, erro, "ultimas_odds_persistidas"
            )
            return odds, falha

    @staticmethod
    def _mercado_odds_utilizavel(mercado, agora=None):
        if not isinstance(mercado, dict):
            return False
        if not str(mercado.get("fonte") or "").strip():
            return False
        if not isinstance(mercado.get("cache"), bool):
            return False
        idades = []
        try:
            idade_declarada = float(mercado.get("idade_segundos"))
            if not math.isfinite(idade_declarada) or idade_declarada < 0:
                return False
            idades.append(idade_declarada)
        except (TypeError, ValueError):
            pass
        coletado_em = mercado.get("coletado_em")
        if coletado_em:
            try:
                origem = datetime.fromisoformat(str(coletado_em))
                referencia = (agora or datetime.now())
                if origem.tzinfo is not None:
                    origem = origem.astimezone().replace(tzinfo=None)
                referencia = referencia.replace(tzinfo=None)
                idade_instante = (referencia - origem).total_seconds()
                if idade_instante < -1:
                    return False
                idades.append(max(idade_instante, 0.0))
            except (TypeError, ValueError):
                return False
        if not idades:
            return False
        return max(idades) <= IDADE_ODD_MAXIMA_SEGUNDOS

    @staticmethod
    def _tem_odds_asiaticas_periodo(odds, periodo):
        for mercado in (odds or {}).get("ao_vivo") or []:
            if not ServicoMonitor._mercado_odds_utilizavel(mercado):
                continue
            if mercado.get("categoria") != "escanteios":
                continue
            if mercado.get("tipo_mercado") != "asiatico":
                continue
            dados = (mercado.get("ofertas_periodos") or {}).get(periodo)
            if (
                dados
                and dados.get("formato") == "duas_opcoes"
                and dados.get("ofertas")
            ):
                return True
        return False

    @staticmethod
    def _tem_odds_asiaticas_total(odds):
        for mercado in (odds or {}).get("ao_vivo") or []:
            if not ServicoMonitor._mercado_odds_utilizavel(mercado):
                continue
            if mercado.get("categoria") != "escanteios":
                continue
            if mercado.get("tipo_mercado") != "asiatico":
                continue
            if (mercado.get("escopo") or "total") != "total":
                continue
            if (
                mercado.get("formato") == "duas_opcoes"
                and mercado.get("ofertas")
            ):
                return True
        return False

    @staticmethod
    def _tem_odds_gols_total(odds):
        for mercado in (odds or {}).get("ao_vivo") or []:
            if not ServicoMonitor._mercado_odds_utilizavel(mercado):
                continue
            if mercado.get("categoria") != "gols":
                continue
            if (mercado.get("escopo") or "total") != "total":
                continue
            if (
                mercado.get("formato") == "duas_opcoes"
                and mercado.get("ofertas")
            ):
                return True
        return False

    @staticmethod
    def _tem_odds_proximo_gol(odds):
        for mercado in (odds or {}).get("ao_vivo") or []:
            if not ServicoMonitor._mercado_odds_utilizavel(mercado):
                continue
            if mercado.get("categoria") != "gols":
                continue
            if mercado.get("escopo") != "proximo":
                continue
            selecoes = mercado.get("selecoes") or {}
            if {"casa", "visitante"} <= set(selecoes):
                return True
        return False

    @staticmethod
    def _tem_odds_operacionais_utilizaveis(odds):
        """Só confirma a coleta quando existe uma oferta de gols/cantos."""
        for mercado in (odds or {}).get("ao_vivo") or []:
            if mercado.get("categoria") not in ("gols", "escanteios"):
                continue
            if mercado.get("ofertas") or mercado.get("selecoes"):
                return True
            for periodo in (mercado.get("ofertas_periodos") or {}).values():
                if isinstance(periodo, dict) and periodo.get("ofertas"):
                    return True
        return False

    @classmethod
    def _odds_coletadas_com_sucesso(
        cls,
        coletar_odds_agora,
        falha_odds,
        odds,
        aceitar_fonte_auxiliar=False,
    ):
        packball_ok = bool(
            coletar_odds_agora
            and falha_odds is None
            and cls._tem_odds_operacionais_utilizaveis(odds)
        )
        if packball_ok:
            return True
        if not aceitar_fonte_auxiliar:
            return False
        fontes = cls._fontes_odds_operacionais(odds)
        return bool(
            cls._tem_odds_operacionais_utilizaveis(odds)
            and any(fonte != "packball" for fonte in fontes)
        )

    @classmethod
    def _diagnosticar_cobertura_odds(cls, odds_packball, odds_finais):
        """Distingue cobertura PackBall de um fallback realmente necessário.

        Esta telemetria não participa da decisão dos sinais. Ela evita que a
        operação confunda "aba de odds visitada" com "odd utilizável" e mede
        se as fontes auxiliares cobriram uma ausência real do PackBall.
        """
        packball_utilizavel = cls._tem_odds_operacionais_utilizaveis(
            odds_packball
        )
        final_utilizavel = cls._tem_odds_operacionais_utilizaveis(
            odds_finais
        )
        fontes_packball = cls._fontes_odds_operacionais(odds_packball)
        fontes_finais = cls._fontes_odds_operacionais(odds_finais)
        fallback_necessario = not packball_utilizavel
        return {
            "packball_utilizavel": bool(packball_utilizavel),
            "final_utilizavel": bool(final_utilizavel),
            "fallback_necessario": bool(fallback_necessario),
            "fallback_atendeu": bool(
                fallback_necessario and final_utilizavel
            ),
            "fallback_sem_cobertura": bool(
                fallback_necessario and not final_utilizavel
            ),
            "fontes_packball": sorted(fontes_packball),
            "fontes_finais": sorted(fontes_finais),
            "fontes_fallback_atenderam": sorted(
                fontes_finais if fallback_necessario and final_utilizavel
                else set()
            ),
            "aplicacao_sinais": False,
        }

    @staticmethod
    def _fontes_odds_operacionais(odds):
        aliases = {
            "api-football": "api_football",
            "api_football": "api_football",
            "the odds api": "the_odds_api",
            "the_odds_api": "the_odds_api",
            "bets api": "betsapi",
            "betsapi": "betsapi",
            "b365api": "betsapi",
            "thestats": "thestatsapi",
            "thestatsapi": "thestatsapi",
            "packball": "packball",
        }

        def normalizar(valor):
            texto = str(valor or "").strip().casefold()
            return aliases.get(texto, texto or None)

        fontes = set()
        for mercado in (odds or {}).get("ao_vivo") or []:
            if not isinstance(mercado, dict):
                continue
            if mercado.get("categoria") not in ("gols", "escanteios"):
                continue
            ofertas = list(mercado.get("ofertas") or [])
            ofertas.extend(mercado.get("ofertas_ht") or [])
            for periodo in (
                mercado.get("ofertas_periodos") or {}
            ).values():
                if isinstance(periodo, dict):
                    ofertas.extend(periodo.get("ofertas") or [])
            utilizavel = bool(ofertas or mercado.get("selecoes"))
            if not utilizavel:
                continue
            fonte_mercado = normalizar(mercado.get("fonte"))
            if fonte_mercado:
                fontes.add(fonte_mercado)
            for oferta in ofertas:
                if not isinstance(oferta, dict):
                    continue
                fonte_oferta = normalizar(oferta.get("fonte"))
                if fonte_oferta:
                    fontes.add(fonte_oferta)
        return fontes

    def _gerar_exploracoes_sombra_novas(
        self, snapshot_id, candidatos, odds
    ):
        """Permite experiências paralelas e deduplica cada versão."""
        novas = []
        chaves_no_lote = set()
        total_challenger_v2 = self.banco.contar_exploracao_sombra_versao(
            VERSAO_CHALLENGER_V2_FT
        )
        for item in gerar_exploracoes_sombra(
            candidatos,
            odds,
            regra_fingerprints=self.regra_fingerprints,
        ):
            versao_experimento = (
                ((item.get("features") or {}).get(
                    "exploracao_sombra"
                ) or {}).get("versao")
            )
            chave_lote = (
                item.get("mercado"), item.get("regra_versao"),
                versao_experimento,
            )
            if chave_lote in chaves_no_lote:
                continue
            if versao_experimento == VERSAO_CHALLENGER_V2_FT:
                if total_challenger_v2 >= TAMANHO_COORTE_CHALLENGER_V2_FT:
                    continue
                total_challenger_v2 += 1
            if not self.banco.exploracao_sombra_ja_registrada(
                snapshot_id,
                item["mercado"],
                item["regra_versao"],
                versao_experimento,
            ):
                novas.append(item)
                chaves_no_lote.add(chave_lote)
        return novas

    def _filtrar_exploracoes_repetidas(self, snapshot_id, candidatos):
        """Evita que challengers paralelos repetidos abortem o ciclo inteiro."""
        filtrados = []
        chaves_no_lote = set()
        for item in candidatos or []:
            versao = (
                ((item.get("features") or {}).get("exploracao_sombra") or {})
                .get("versao")
            )
            if versao is None:
                filtrados.append(item)
                continue
            chave = (item.get("mercado"), str(versao))
            if chave in chaves_no_lote:
                continue
            if self.banco.exploracao_sombra_ja_registrada(
                snapshot_id,
                item.get("mercado"),
                item.get("regra_versao"),
                versao,
            ):
                continue
            filtrados.append(item)
            chaves_no_lote.add(chave)
        return filtrados

    @staticmethod
    def _classificar_auditoria_bloqueio(original):
        """Prevê, sem persistir, se o descarte formará auditoria silenciosa."""
        ativa = os.getenv(
            "AUDITORIA_BLOQUEIOS_PROMISSORES_ATIVA", "0"
        ) == "1"
        if not ativa:
            return None
        try:
            pontuacao_minima = float(os.getenv(
                "AUDITORIA_BLOQUEIOS_PONTUACAO_MINIMA", "60"
            ))
        except (TypeError, ValueError):
            pontuacao_minima = 60.0
        try:
            odd_minima = float(os.getenv(
                "AUDITORIA_BLOQUEIOS_ODD_MINIMA", "1.35"
            ))
            odd_maxima = float(os.getenv(
                "AUDITORIA_BLOQUEIOS_ODD_MAXIMA", "2.50"
            ))
        except (TypeError, ValueError):
            odd_minima, odd_maxima = 1.35, 2.50
        bloqueios_estruturais = (
            "minuto_maximo", "fora_da_janela", "fora_janela",
            "periodo_incompativel", "linha_invalida", "placar_invalido",
            "partida_encerrada",
        )
        if (original.get("features") or {}).get("acompanhamento_metodo_gols"):
            return None
        if original.get("mercado") not in {
            "gol_ft", "gol_ht", "proximo_gol"
        }:
            return None
        if original.get("status") != "rejeitado":
            return None
        try:
            pontuacao = float(original.get("pontuacao_tecnica") or 0)
            odd = float(original.get("odd"))
        except (TypeError, ValueError):
            return None
        if (
            not math.isfinite(pontuacao)
            or pontuacao < pontuacao_minima
            or not math.isfinite(odd)
            or not (odd_minima <= odd <= odd_maxima)
            or original.get("linha") in (None, "")
        ):
            return None
        bloqueios = sorted({
            str(item).strip()
            for item in original.get("bloqueios") or []
            if str(item).strip()
        })
        if not bloqueios:
            bloqueios = sorted({
                str(item).strip()
                for item in original.get("bloqueio_fontes") or []
                if str(item).strip()
            })
        if not bloqueios:
            return None
        if any(
            trecho in bloqueio.casefold()
            for bloqueio in bloqueios
            for trecho in bloqueios_estruturais
        ):
            return None
        return {
            "bloqueios": bloqueios,
            "bloqueios_chave": "|".join(bloqueios),
        }

    def _gerar_auditorias_bloqueadas(self, snapshot_id, candidatos):
        """Congela descartes promissores sem Telegram nem efeito nas regras."""
        novos = []
        chaves_lote = set()
        for original in candidatos or []:
            classificacao = self._classificar_auditoria_bloqueio(original)
            if classificacao is None:
                continue
            bloqueios = classificacao["bloqueios"]
            bloqueios_chave = classificacao["bloqueios_chave"]
            chave = (
                original.get("mercado"), original.get("regra_versao"),
                bloqueios_chave,
            )
            if chave in chaves_lote:
                continue
            if self.banco.auditoria_bloqueio_ja_registrada(
                snapshot_id,
                original.get("mercado"),
                original.get("regra_versao"),
                VERSAO_AUDITORIA_BLOQUEIOS,
                bloqueios_chave,
            ):
                continue
            item = copy.deepcopy(original)
            features = dict(item.get("features") or {})
            features["auditoria_bloqueio"] = {
                "versao": VERSAO_AUDITORIA_BLOQUEIOS,
                "bloqueios_chave": bloqueios_chave,
                "bloqueios_originais": bloqueios,
                "motivos_originais": list(original.get("motivos") or []),
                "origem_status": "rejeitado",
                "aplicacao_sinais": False,
                "telegram": False,
                "calibracao": False,
                "rollback": "AUDITORIA_BLOQUEIOS_PROMISSORES_ATIVA=0",
            }
            item.update({
                "features": features,
                "status": "auditoria",
                "bloqueios": [],
                "probabilidade_calibrada": None,
                "probabilidade_observada": None,
            })
            motivos = list(item.get("motivos") or [])
            motivos.append("auditoria_silenciosa_de_bloqueio_promissor")
            item["motivos"] = motivos
            novos.append(item)
            chaves_lote.add(chave)
        return novos

    @staticmethod
    def _ordenar_odds_por_frescor(odds, agora=None):
        """Prioriza a coleta atual e remove versões já substituídas.

        A mescla de fontes pode manter leituras anteriores para auditoria. Os
        seletores não podem voltar a uma linha antiga quando a mesma casa já
        publicou outra. O histórico permanece no SQLite de snapshots
        anteriores; somente o contrato usado na decisão é saneado aqui.
        """
        if not isinstance(odds, dict):
            return odds
        referencia_epoch = (
            agora.timestamp() if isinstance(agora, datetime) else None
        )

        def interpretar(valor):
            if isinstance(valor, datetime):
                return valor
            if not isinstance(valor, str) or not valor.strip():
                return None
            texto = valor.strip()
            if texto.endswith("Z"):
                texto = f"{texto[:-1]}+00:00"
            try:
                return datetime.fromisoformat(texto)
            except ValueError:
                return None

        def instante(item, pai=None):
            if not isinstance(item, dict):
                return float("-inf")
            pai = pai if isinstance(pai, dict) else {}
            for valor in (
                item.get("coletado_em"),
                pai.get("coletado_em"),
                item.get("recebido_em"),
                pai.get("recebido_em"),
            ):
                data = interpretar(valor)
                if data is not None:
                    return data.timestamp()
            return float("-inf")

        def valor(item, pai, chave):
            if isinstance(item, dict) and item.get(chave) is not None:
                return item.get(chave)
            if isinstance(pai, dict):
                return pai.get(chave)
            return None

        def versao(item, pai=None):
            cache = bool(valor(item, pai, "cache"))
            idade = valor(item, pai, "idade_segundos")
            try:
                idade = float(idade) if idade is not None else float("inf")
            except (TypeError, ValueError):
                idade = float("inf")
            return instante(item, pai), not cache, -idade

        def identidade_oferta(oferta, mercado, sufixo=""):
            fonte = str(valor(oferta, mercado, "fonte") or "").casefold()
            casa = str(valor(oferta, mercado, "bookmaker") or "").casefold()
            evento = str(
                valor(oferta, mercado, "evento_externo_id") or ""
            ).casefold()
            if not fonte and not casa:
                return None
            return fonte, casa, evento, str(sufixo).casefold()

        descartadas = 0

        def sanear_ofertas(mercado, ofertas, sufixo=""):
            nonlocal descartadas
            if not isinstance(ofertas, list):
                return ofertas
            melhores = {}
            for oferta in ofertas:
                chave = identidade_oferta(oferta, mercado, sufixo)
                if chave is None:
                    continue
                atual = versao(oferta, mercado)
                if chave not in melhores or atual > melhores[chave]:
                    melhores[chave] = atual
            filtradas = []
            for oferta in ofertas:
                instante_oferta = instante(oferta, mercado)
                if (
                    referencia_epoch is not None
                    and instante_oferta != float("-inf")
                    and max(referencia_epoch - instante_oferta, 0.0)
                    > IDADE_ODD_MAXIMA_SEGUNDOS
                ):
                    descartadas += 1
                    continue
                chave = identidade_oferta(oferta, mercado, sufixo)
                if chave is not None and versao(oferta, mercado) != melhores[chave]:
                    descartadas += 1
                    continue
                filtradas.append(oferta)
            ofertas[:] = filtradas
            ofertas.sort(
                key=lambda oferta: instante(oferta, mercado),
                reverse=True,
            )
            return ofertas

        mercados = odds.get("ao_vivo")
        if not isinstance(mercados, list):
            return odds
        for mercado in mercados:
            if not isinstance(mercado, dict):
                continue
            ofertas_identidade = (
                list(mercado.get("ofertas") or [])
                + list(mercado.get("ofertas_ht") or [])
            )
            for dados in (mercado.get("ofertas_periodos") or {}).values():
                ofertas_identidade.extend((dados or {}).get("ofertas") or [])
            if ofertas_identidade:
                origem = ofertas_identidade[0]
                for campo in ("fonte", "bookmaker", "evento_externo_id"):
                    if mercado.get(campo) is None and origem.get(campo) is not None:
                        mercado[campo] = origem.get(campo)
            for chave in ("ofertas", "ofertas_ht"):
                sanear_ofertas(mercado, mercado.get(chave), chave)
            for periodo, dados in (
                mercado.get("ofertas_periodos") or {}
            ).items():
                if isinstance(dados, dict):
                    sanear_ofertas(
                        mercado, dados.get("ofertas"), f"periodo:{periodo}"
                    )

        def instante_mercado(mercado):
            if not isinstance(mercado, dict):
                return float("-inf")
            instantes = [instante(mercado)]
            for chave in ("ofertas", "ofertas_ht"):
                instantes.extend(
                    instante(oferta, mercado)
                    for oferta in mercado.get(chave) or []
                )
            for dados in (mercado.get("ofertas_periodos") or {}).values():
                instantes.extend(
                    instante(oferta, mercado)
                    for oferta in (dados or {}).get("ofertas") or []
                )
            return max(instantes)

        mercados.sort(key=instante_mercado, reverse=True)

        def identidade_mercado(mercado):
            fonte = str(mercado.get("fonte") or "").casefold()
            casa = str(mercado.get("bookmaker") or "").casefold()
            evento = str(
                mercado.get("evento_externo_id") or ""
            ).casefold()
            ofertas = (
                list(mercado.get("ofertas") or [])
                + list(mercado.get("ofertas_ht") or [])
            )
            if ofertas:
                fonte = fonte or str(ofertas[0].get("fonte") or "").casefold()
                casa = casa or str(
                    ofertas[0].get("bookmaker") or ""
                ).casefold()
                evento = evento or str(
                    ofertas[0].get("evento_externo_id") or ""
                ).casefold()
            if not fonte and not casa:
                return None
            return (
                fonte,
                casa,
                evento,
                str(mercado.get("categoria") or "").casefold(),
                str(mercado.get("escopo") or "total").casefold(),
                str(mercado.get("tipo_mercado") or "").casefold(),
                str(mercado.get("formato") or "").casefold(),
            )

        melhores_mercados = {}
        for mercado in mercados:
            chave = identidade_mercado(mercado)
            if chave is None:
                continue
            atual = versao(mercado)
            atual = max(atual, (instante_mercado(mercado), atual[1], atual[2]))
            if chave not in melhores_mercados or atual > melhores_mercados[chave]:
                melhores_mercados[chave] = atual
        filtrados = []
        for mercado in mercados:
            chave = identidade_mercado(mercado)
            atual = versao(mercado)
            atual = max(atual, (instante_mercado(mercado), atual[1], atual[2]))
            if chave is not None and atual != melhores_mercados[chave]:
                descartadas += 1
                continue
            filtrados.append(mercado)
        mercados[:] = filtrados
        if descartadas:
            odds.setdefault("_metadados", {})[
                "ofertas_substituidas_descartadas"
            ] = descartadas
        return odds

    @staticmethod
    def _gerar_candidatos_rastreaveis(
        jogo, estatisticas, evolucao, odds, qualidade,
        odds_referencia_sombra=None,
    ):
        decisao_em = datetime.now().astimezone().replace(microsecond=0)
        ServicoMonitor._ordenar_odds_por_frescor(odds, agora=decisao_em)
        candidatos = gerar_candidatos(
            jogo, estatisticas, evolucao, odds, qualidade
        )
        aplicar_proveniencia_odds(candidatos, odds, instante=decisao_em)
        anexar_melhor_preco_sombra(
            candidatos,
            odds,
            instante=decisao_em,
            odds_referencia_sombra=odds_referencia_sombra,
        )
        estado_observado_em = (
            jogo.get("estado_observado_em")
            or jogo.get("lista_observada_em")
        )
        for candidato in candidatos:
            features = candidato.get("features")
            if not isinstance(features, dict):
                features = {}
            candidato["features"] = {
                **features,
                "decisao_em": decisao_em.isoformat(),
                "estado_observado_em": estado_observado_em,
            }
        return candidatos

    def _priorizar_referencia_valor_justo(
        self, jogo, candidatos, mercados_anexados_betsapi
    ):
        """Reserva a fonte independente somente para coorte liquidavel.

        A decisao operacional ja esta pronta quando esta funcao roda. Ela
        apenas identifica candidatos com cotacao Bet365 congelada e elimina
        mercados que ja formaram sua unidade prospectiva no mesmo jogo. Um
        descarte que vai formar auditoria silenciosa também pode ser medido,
        porque essa cópia só é materializada depois da persistência do
        snapshot e não existia ainda nesta etapa do ciclo.
        """
        anexados = {
            str(mercado or "").strip()
            for mercado in (mercados_anexados_betsapi or ())
        } & {"gol_ft", "gol_ht", "escanteios_ft_asiatico"}
        elegiveis = set()
        motivos = {}
        origens_elegibilidade = {
            "candidato_final": 0,
            "auditoria_bloqueio_prevista": 0,
        }

        def excluir(motivo):
            motivos[motivo] = int(motivos.get(motivo, 0) or 0) + 1

        for candidato in candidatos or []:
            mercado = str(candidato.get("mercado") or "").strip()
            if mercado not in anexados:
                continue
            status = str(
                candidato.get("status") or ""
            ).strip().casefold()
            origem_elegibilidade = "candidato_final"
            if status not in STATUS_VALOR_JUSTO_ELEGIVEIS:
                if (
                    status == "rejeitado"
                    and self._classificar_auditoria_bloqueio(candidato)
                    is not None
                ):
                    origem_elegibilidade = "auditoria_bloqueio_prevista"
                else:
                    excluir("status_nao_liquidavel")
                    continue
            features = candidato.get("features") or {}
            if not isinstance(features, dict):
                excluir("features_invalidas")
                continue
            if features.get(CHAVE_ESTADO_COTACAO_ENTRADA) != (
                ESTADO_COTACAO_CONGELADA
            ):
                excluir("cotacao_nao_congelada")
                continue
            fonte = str(
                candidato.get("fonte_odds")
                or features.get("fonte_odds")
                or ""
            ).strip().casefold()
            bookmaker = str(
                candidato.get("bookmaker_odds")
                or features.get("bookmaker_odds")
                or ""
            ).strip().casefold()
            if fonte != "betsapi" or bookmaker != "bet365":
                excluir("cotacao_executavel_nao_e_betsapi_bet365")
                continue
            elegiveis.add(mercado)
            origens_elegibilidade[origem_elegibilidade] += 1

        ja_formados = mercados_com_candidato_sincronizado(
            self.banco.conexao,
            (jogo or {}).get("url"),
            elegiveis,
        )
        priorizados = elegiveis - ja_formados
        return priorizados, {
            "versao": "priorizacao-referencia-valor-justo-v2",
            "mercados_betsapi_anexados": sorted(anexados),
            "mercados_cotacao_liquidavel": sorted(elegiveis),
            "mercados_coorte_ja_formada": sorted(ja_formados),
            "mercados_priorizados": sorted(priorizados),
            "origens_elegibilidade": origens_elegibilidade,
            "exclusoes": motivos,
            "recuperacao_unica_limite_antigo": bool(priorizados),
            "aplicacao_sinais": False,
            "altera_calibracao": False,
            "telegram": False,
            "promocao_automatica": False,
        }

    @staticmethod
    def _carimbar_mercado_api(mercado, agora=None):
        """Preserva a idade real da resposta API sem fingir coleta fresca."""
        if not isinstance(mercado, dict):
            return mercado
        agora = (agora or datetime.now()).replace(microsecond=0)
        recebido_em = agora.isoformat()

        def carimbar(item, idade_herdada=None):
            if not isinstance(item, dict):
                return
            idade = item.get("idade_segundos", idade_herdada)
            try:
                idade = float(idade)
                if not math.isfinite(idade) or idade < 0:
                    idade = None
            except (TypeError, ValueError):
                idade = None
            item["recebido_em"] = recebido_em
            if idade is not None:
                item["idade_segundos"] = round(idade, 3)
                item["coletado_em"] = (
                    agora - timedelta(seconds=idade)
                ).isoformat()

        idades = []
        for chave in ("ofertas", "ofertas_ht"):
            for oferta in mercado.get(chave) or []:
                carimbar(oferta, mercado.get("idade_segundos"))
                try:
                    idades.append(float(oferta.get("idade_segundos")))
                except (AttributeError, TypeError, ValueError):
                    pass
        for dados in (mercado.get("ofertas_periodos") or {}).values():
            for oferta in (dados or {}).get("ofertas") or []:
                carimbar(oferta, mercado.get("idade_segundos"))
                try:
                    idades.append(float(oferta.get("idade_segundos")))
                except (AttributeError, TypeError, ValueError):
                    pass
        idade_mercado = mercado.get("idade_segundos")
        if idade_mercado is None and idades:
            idade_mercado = max(idades)
        carimbar(mercado, idade_mercado)
        return mercado

    def _complementar_odds_escanteios_ft_api(
        self, odds, jogo, confirmacao_api, coletar_odds_agora
    ):
        """Usa a API quando o PackBall nao oferece a linha asiática FT.

        ``coletar_odds_agora`` controla apenas a navegação no PackBall. A
        resposta global da API possui cache próprio e não deve ser descartada
        quando essa navegação não foi agendada.
        """
        fixture_id = (confirmacao_api or {}).get("fixture_id")
        minuto = extrair_minuto(jogo.get("status"))
        if (
            fixture_id is None
            or minuto is None
            or not 15 <= minuto <= 87
            or self._tem_odds_asiaticas_total(odds)
        ):
            return False
        mercado = self.api.odds_escanteios_asiaticos_ft(fixture_id)
        if not mercado:
            return False
        self._carimbar_mercado_api(mercado)
        odds.setdefault("ao_vivo", []).insert(0, mercado)
        return True

    def _complementar_odds_escanteios_1t_api(
        self, odds, jogo, confirmacao_api, coletar_odds_agora
    ):
        """Usa a API somente quando o PackBall nao oferece a linha 1T."""
        if not escanteios_asiaticos_periodos_ativos():
            return False
        fixture_id = (confirmacao_api or {}).get("fixture_id")
        minuto = extrair_minuto(jogo.get("status"))
        if (
            not coletar_odds_agora
            or fixture_id is None
            or minuto is None
            or not 15 <= minuto <= 40
            or self._tem_odds_asiaticas_periodo(odds, "1T")
        ):
            return False
        mercado = self.api.odds_escanteios_asiaticos_1t(fixture_id)
        if not mercado:
            return False
        self._carimbar_mercado_api(mercado)
        odds.setdefault("ao_vivo", []).insert(0, mercado)
        return True

    def _complementar_odds_gols_ft_api(
        self, odds, jogo, confirmacao_api
    ):
        """Usa a API quando o PackBall nao oferece uma linha de gols FT."""
        fixture_id = (confirmacao_api or {}).get("fixture_id")
        minuto = extrair_minuto(jogo.get("status"))
        if (
            fixture_id is None
            or minuto is None
            or not 15 <= minuto <= 87
            or self._tem_odds_gols_total(odds)
        ):
            return False
        mercado = self.api.odds_gols_total_ft(fixture_id)
        if not isinstance(mercado, dict):
            return False
        self._carimbar_mercado_api(mercado)
        odds.setdefault("ao_vivo", []).insert(0, mercado)
        return True

    def _complementar_odds_proximo_gol_api(
        self, odds, jogo, confirmacao_api
    ):
        """Usa a API quando o PackBall nao oferece a odd de proximo gol."""
        fixture_id = (confirmacao_api or {}).get("fixture_id")
        minuto = extrair_minuto(jogo.get("status"))
        placar = extrair_placar(jogo.get("placar"))
        if (
            fixture_id is None
            or minuto is None
            or not 10 <= minuto <= 87
            or placar is None
            or self._tem_odds_proximo_gol(odds)
        ):
            return False
        mercado = self.api.odds_proximo_gol(
            fixture_id, placar[0] + placar[1]
        )
        if not isinstance(mercado, dict):
            return False
        self._carimbar_mercado_api(mercado)
        odds.setdefault("ao_vivo", []).insert(0, mercado)
        return True

    def _complementar_odds_the_odds_api(
        self, odds, jogo, mercados_para_odds
    ):
        """Complementa apenas linhas comprovadas pela nova fonte paga.

        O cliente exige pareamento forte, mercado explícito, Over/Under
        completo e frescor. Ausência ou erro preserva integralmente o fluxo
        PackBall/API-Football.
        """
        cliente = getattr(self, "the_odds_api", None)
        if cliente is None:
            return {
                "ativa": False,
                "pareado": False,
                "anexados": [],
                "motivo": "cliente_ausente",
            }
        internos = {
            item for item in (mercados_para_odds or set())
            if item in {
                "gol_ft", "gol_ht", "escanteios_ft_asiatico"
            }
        }
        if not internos:
            return {
                **cliente.diagnostico(),
                "pareado": False,
                "anexados": [],
                "motivo": "sem_mercado_compativel",
            }
        encontrados, diagnostico = cliente.buscar_mercados(jogo, internos)
        mercados = (encontrados or {}).get("ao_vivo") or []
        if mercados:
            self._mesclar_mercados_odds_complementares(odds, mercados)
        diagnostico.update(cliente.diagnostico())
        return diagnostico

    def _amostrar_referencia_api_football_sombra(
        self, jogo, confirmacao_api, mercados
    ):
        """Usa outra bookmaker da API-Football apenas como contrafactual."""
        ativa = os.getenv(
            "API_FOOTBALL_REFERENCIA_SOMBRA_ATIVA", "1"
        ) == "1"
        suportados = {
            str(item or "").strip()
            for item in (mercados or ())
        } & {"gol_ft", "gol_ht", "escanteios_ft_asiatico"}
        base = {
            "versao": "api-football-referencia-sombra-v1",
            "ativa": ativa,
            "mercados_solicitados": sorted(suportados),
            "mercados_retornados": [],
            "bookmakers_independentes": [],
            "consultas_rede_estimadas": 0,
            "consultas_rede_evitadas": 0,
            "mercados_sem_identidade_bookmaker": [],
            "pareado": False,
            "aplicacao_sinais": False,
            "altera_calibracao": False,
            "telegram": False,
            "promocao_automatica": False,
            "rollback": "API_FOOTBALL_REFERENCIA_SOMBRA_ATIVA=0",
        }
        if not ativa:
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base, "motivo": "fonte_desativada",
            }
        buscar = getattr(
            getattr(self, "api", None),
            "odds_referencia_independente",
            None,
        )
        if not callable(buscar):
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base, "motivo": "cliente_sem_referencia_independente",
            }
        fixture_id = (confirmacao_api or {}).get("fixture_id")
        placar_jogo = extrair_placar((jogo or {}).get("placar"))
        try:
            placar_api = tuple(int(item) for item in (
                (confirmacao_api or {}).get("placar") or ()
            ))
            similaridade = float(
                (confirmacao_api or {}).get("similaridade")
            )
        except (TypeError, ValueError):
            placar_api = ()
            similaridade = 0.0
        if (
            fixture_id is None
            or placar_jogo is None
            or placar_api != tuple(placar_jogo)
            or similaridade < 0.84
        ):
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base,
                "fixture_id": fixture_id,
                "similaridade_associacao": round(similaridade, 4),
                "motivo": "associacao_api_ou_placar_incompativel",
            }

        identidade = {
            "schema": "identidade-evento-odd-v1",
            "confirmada": True,
            "fonte": "api_football",
            "evento_externo_id": str(fixture_id),
            "orientacao": (confirmacao_api or {}).get("orientacao"),
            "similaridade": round(similaridade, 4),
            "mandante_normalizado": (
                (jogo or {}).get("mandante") or (jogo or {}).get("casa")
            ),
            "visitante_normalizado": (
                (jogo or {}).get("visitante") or (jogo or {}).get("fora")
            ),
            "placar_normalizado": f"{placar_jogo[0]}-{placar_jogo[1]}",
            "metodo": "fixture_api_football_confirmada_nome_placar",
        }
        saida = []
        por_mercado = {}
        for mercado_interno in sorted(suportados):
            try:
                mercados_api, diagnostico = buscar(
                    fixture_id,
                    mercado_interno,
                    bookmaker_excluido="bet365",
                )
            except Exception as erro:
                mercados_api, diagnostico = [], {
                    "motivo": "falha_isolada",
                    "erro": type(erro).__name__,
                    "aplicacao_sinais": False,
                    "telegram": False,
                }
            diagnostico = dict(diagnostico or {})
            por_mercado[mercado_interno] = diagnostico
            consulta_explicita = diagnostico.get(
                "consulta_rede_realizada"
            )
            if consulta_explicita is True or (
                consulta_explicita is None
                and diagnostico.get("cache") is False
            ):
                base["consultas_rede_estimadas"] += 1
            if diagnostico.get("consulta_rede_evitada") is True:
                base["consultas_rede_evitadas"] += 1
            if diagnostico.get("motivo") == (
                "fonte_live_sem_identidade_bookmaker"
            ):
                base["mercados_sem_identidade_bookmaker"].append(
                    mercado_interno
                )
            for mercado_api in mercados_api or []:
                if not isinstance(mercado_api, dict):
                    continue
                self._carimbar_mercado_api(mercado_api)
                mercado_api["identidade_evento"] = dict(identidade)
                ofertas = list(mercado_api.get("ofertas") or [])
                ofertas.extend(mercado_api.get("ofertas_ht") or [])
                for dados_periodo in (
                    mercado_api.get("ofertas_periodos") or {}
                ).values():
                    ofertas.extend((dados_periodo or {}).get("ofertas") or [])
                for oferta in ofertas:
                    if isinstance(oferta, dict):
                        oferta["identidade_evento"] = dict(identidade)
                bookmaker = str(
                    mercado_api.get("bookmaker") or ""
                ).strip()
                if not bookmaker or bookmaker.casefold() == "bet365":
                    continue
                saida.append(mercado_api)
                base["mercados_retornados"].append(mercado_interno)
                base["bookmakers_independentes"].append(bookmaker)
        base["por_mercado"] = por_mercado
        base["mercados_retornados"] = sorted(set(
            base["mercados_retornados"]
        ))
        base["bookmakers_independentes"] = sorted(set(
            base["bookmakers_independentes"]
        ))
        base["mercados_sem_identidade_bookmaker"] = sorted(set(
            base["mercados_sem_identidade_bookmaker"]
        ))
        base["pareado"] = bool(saida)
        base["motivo"] = (
            "referencia_independente_disponivel"
            if saida
            else "fonte_live_sem_identidade_bookmaker"
            if base["mercados_sem_identidade_bookmaker"]
            else "sem_referencia_independente_api_football"
        )
        return {"pre_jogo": [], "ao_vivo": saida}, base

    def _amostrar_referencia_odds_sombra(
        self,
        jogo,
        mercados_anexados_betsapi,
        *,
        controlar_ciclo=True,
        permitir_recuperacao_coorte=False,
        origem_coleta="ciclo_packball",
        contexto_auditoria=None,
    ):
        """Coleta uma contraparte independente sem entrar no motor de sinais.

        A amostra fica em uma estrutura separada das odds operacionais. Ela é
        limitada por ciclo no serviço e por dia/jogo no próprio cliente. A
        fila rápida pode desativar apenas o limite em memória do ciclo; os
        limites persistentes de dia, jogo e cooldown continuam obrigatórios.
        A referência é usada apenas na avaliação prospectiva de preço.
        """
        cliente = getattr(self, "the_odds_api", None)
        if contexto_auditoria is None:
            contexto_auditoria = getattr(
                self, "_contexto_amostragem_referencia_ciclo", {}
            )
        if not isinstance(contexto_auditoria, dict):
            contexto_auditoria = {}
        base = {
            "ativa": bool(getattr(
                cliente, "amostragem_referencia_ativa", False
            )),
            "elegivel_betsapi": False,
            "consultados": [],
            "anexados": [],
            "pareado": False,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
            "prioriza_novas_partidas": True,
            "prioriza_competicoes_cobertas": True,
            "exige_evento_pareado_antes_reserva": True,
            "recuperacao_coorte_solicitada": bool(
                permitir_recuperacao_coorte
            ),
            "reserva_consumida": False,
            "controle_ciclo": bool(controlar_ciclo),
            "origem_coleta": str(origem_coleta),
            "auditoria_amostragem": {
                "versao": "amostragem-referencia-sombra-auditoria-v5",
                "origem_coleta": str(origem_coleta),
                "ciclo_em": contexto_auditoria.get("ciclo_em"),
                "posicao_fila": contexto_auditoria.get("posicao_fila"),
                "tarefas_ciclo": contexto_auditoria.get("tarefas_ciclo"),
                "fila_operacional": contexto_auditoria.get(
                    "fila_operacional"
                ),
                "liga": contexto_auditoria.get("liga"),
                "minuto": contexto_auditoria.get("minuto"),
                "selecao_antes_resultado": True,
                "recuperacao_coorte_solicitada": bool(
                    permitir_recuperacao_coorte
                ),
                "aplicacao_sinais": False,
            },
        }
        if cliente is None:
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base, "motivo": "cliente_ausente",
            }
        mercados_elegiveis = {
            item for item in set(mercados_anexados_betsapi or ())
            if item in {
                "gol_ft", "gol_ht", "escanteios_ft_asiatico",
            }
        }
        base["mercados_elegiveis_betsapi"] = sorted(
            mercados_elegiveis
        )
        base["custo_estimado_creditos"] = len(mercados_elegiveis)
        if not mercados_elegiveis:
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base, "motivo": "sem_mercado_betsapi_suportado",
            }
        base["elegivel_betsapi"] = True
        diagnosticar_cobertura = getattr(
            cliente, "diagnosticar_cobertura_competicao", None
        )
        if callable(diagnosticar_cobertura):
            try:
                cobertura = diagnosticar_cobertura(jogo)
            except Exception as erro:
                cobertura = {
                    "versao": "preselecao-cobertura-the-odds-api-v1",
                    "executada": True,
                    "coberta": None,
                    "motivo": "falha_preselecao_cobertura",
                    "erro": type(erro).__name__,
                    "reserva_consumida": False,
                    "aplicacao_sinais": False,
                    "telegram": False,
                }
            if isinstance(cobertura, dict):
                base["preselecao_cobertura"] = dict(cobertura)
                if cobertura.get("coberta") is not True:
                    motivo_cobertura = str(
                        cobertura.get("motivo") or ""
                    )
                    return {"pre_jogo": [], "ao_vivo": []}, {
                        **base,
                        "motivo": (
                            "competicao_nao_coberta_pre_reserva"
                            if cobertura.get("coberta") is False
                            else "cobertura_indisponivel_pre_reserva"
                        ),
                        "motivo_cobertura": motivo_cobertura,
                        "mercados_persistidos_sombra": 0,
                    }
        diagnosticar_evento = getattr(
            cliente, "diagnosticar_cobertura_evento", None
        )
        if callable(diagnosticar_evento):
            try:
                evento = diagnosticar_evento(
                    jogo,
                    esportes_candidatos=(
                        (base.get("preselecao_cobertura") or {}).get(
                            "esportes_candidatos"
                        )
                    ),
                )
            except Exception as erro:
                evento = {
                    "versao": "preselecao-evento-the-odds-api-v1",
                    "executada": True,
                    "pareado": None,
                    "motivo": "falha_preselecao_evento",
                    "erro": type(erro).__name__,
                    "reserva_consumida": False,
                    "aplicacao_sinais": False,
                    "telegram": False,
                }
            if isinstance(evento, dict):
                base["preselecao_evento"] = dict(evento)
                if evento.get("pareado") is not True:
                    return {"pre_jogo": [], "ao_vivo": []}, {
                        **base,
                        "motivo": (
                            "evento_nao_encontrado_pre_reserva"
                            if evento.get("pareado") is False
                            else "evento_indisponivel_pre_reserva"
                        ),
                        "motivo_evento": str(
                            evento.get("motivo") or ""
                        ),
                        "mercados_persistidos_sombra": 0,
                    }
        configuracao = (
            ((getattr(self, "configuracao", {}) or {}).get(
                "the_odds_api"
            ) or {}).get("amostragem_referencia") or {}
        )
        maximo_ciclo = min(max(int(
            configuracao.get("maximo_ciclo", 2) or 0
        ), 0), 10)
        usadas_ciclo = int(getattr(
            self, "_amostras_referencia_odds_ciclo", 0
        ) or 0)
        confirmacoes_usadas_ciclo = int(getattr(
            self, "_amostras_referencia_confirmacoes_ciclo", 0
        ) or 0)
        maximo_confirmacoes_ciclo = max(maximo_ciclo - 1, 0)
        if controlar_ciclo and usadas_ciclo >= maximo_ciclo:
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base,
                "motivo": "limite_amostragem_ciclo",
                "uso_ciclo": usadas_ciclo,
                "limite_ciclo": maximo_ciclo,
            }
        chave = f"{str(jogo.get('url') or '').strip()}|gol_ft"
        reserva = cliente.reservar_amostragem_referencia(
            chave,
            custo_estimado=len(mercados_elegiveis),
            permitir_confirmacao=(
                True if not controlar_ciclo else
                confirmacoes_usadas_ciclo < maximo_confirmacoes_ciclo
            ),
            permitir_recuperacao_coorte=bool(
                permitir_recuperacao_coorte
            ),
        )
        if reserva.get("autorizada") is not True:
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base,
                "motivo": reserva.get("motivo") or "amostragem_nao_autorizada",
                "reserva": reserva,
                "uso_ciclo": usadas_ciclo if controlar_ciclo else None,
                "limite_ciclo": maximo_ciclo if controlar_ciclo else None,
                "confirmacoes_ciclo": confirmacoes_usadas_ciclo,
                "confirmacoes_maximo_ciclo": (
                    maximo_confirmacoes_ciclo if controlar_ciclo else None
                ),
            }
        if controlar_ciclo:
            self._amostras_referencia_odds_ciclo = usadas_ciclo + 1
        base["reserva_consumida"] = True
        if (
            controlar_ciclo
            and reserva.get("tipo_amostra") == "confirmacao_temporal"
        ):
            self._amostras_referencia_confirmacoes_ciclo = (
                confirmacoes_usadas_ciclo + 1
            )
        try:
            encontrados, diagnostico = cliente.buscar_mercados(
                jogo, mercados_elegiveis
            )
        except Exception as erro:
            # Preserva a reserva no diagnóstico. Sem isso, uma chamada que
            # falhasse depois de consumir o orçamento pareceria nunca ter
            # sido tentada e a supervisão não conseguiria detectar a falha.
            return {"pre_jogo": [], "ao_vivo": []}, {
                **base,
                "motivo": "falha_isolada",
                "erro": type(erro).__name__,
                "reserva": reserva,
                "uso_ciclo": (
                    usadas_ciclo + 1 if controlar_ciclo else None
                ),
                "limite_ciclo": maximo_ciclo if controlar_ciclo else None,
                "confirmacoes_ciclo": (
                    int(getattr(
                        self, "_amostras_referencia_confirmacoes_ciclo", 0
                    ) or 0) if controlar_ciclo else None
                ),
                "confirmacoes_maximo_ciclo": (
                    maximo_confirmacoes_ciclo if controlar_ciclo else None
                ),
                "mercados_persistidos_sombra": 0,
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            }
        mercados = list((encontrados or {}).get("ao_vivo") or [])
        diagnostico = {
            **base,
            **(diagnostico or {}),
            "reserva": reserva,
            "uso_ciclo": usadas_ciclo + 1 if controlar_ciclo else None,
            "limite_ciclo": maximo_ciclo if controlar_ciclo else None,
            "confirmacoes_ciclo": (
                int(getattr(
                    self, "_amostras_referencia_confirmacoes_ciclo", 0
                ) or 0) if controlar_ciclo else None
            ),
            "confirmacoes_maximo_ciclo": (
                maximo_confirmacoes_ciclo if controlar_ciclo else None
            ),
            "mercados_persistidos_sombra": len(mercados),
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        return {"pre_jogo": [], "ao_vivo": mercados}, diagnostico

    def _amostrar_referencia_odd_monitor_rapido(
        self,
        item,
        estado,
        oferta_monitorada,
        odds_operacionais,
        *,
        sinal_enviado_id=None,
    ):
        """Fotografa uma casa independente no instante da fila rapida.

        A consulta e a persistencia sao estritamente sombra: a estrutura de
        odds usada por ``avaliar_rechecagem_odd_api`` nao e alterada e o
        resultado nunca autoriza, bloqueia ou atrasa uma decisao pendente.
        """
        base = {
            "versao": "referencia-sincronizada-monitor-odd-rapido-v1",
            "tentada": False,
            "reserva_consumida": False,
            "consulta_executada": False,
            "linha_exata": False,
            "auditoria_persistida": False,
            "observacao_persistida": False,
            "comparacoes_persistidas": 0,
            "creditos_estimados_reservados": 0,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        if not isinstance(oferta_monitorada, dict):
            return {**base, "motivo": "oferta_monitorada_ausente"}
        fonte = str(oferta_monitorada.get("fonte") or "").strip().casefold()
        bookmaker = str(
            oferta_monitorada.get("bookmaker") or ""
        ).strip().casefold()
        mercado = str(item.get("mercado") or "").strip().casefold()
        if fonte != "betsapi" or bookmaker != "bet365":
            return {**base, "motivo": "fonte_executavel_nao_e_betsapi_bet365"}
        if mercado not in {"gol_ft", "gol_ht"}:
            return {**base, "motivo": "mercado_nao_suportado"}
        cliente = getattr(self, "the_odds_api", None)
        if not bool(getattr(cliente, "amostragem_referencia_ativa", False)):
            return {**base, "motivo": "amostragem_referencia_desativada"}

        consultado_em = datetime.now().astimezone().replace(
            microsecond=0
        ).isoformat()
        jogo = {
            "url": item.get("packball_url"),
            "mandante": item.get("mandante"),
            "visitante": item.get("visitante"),
            "liga": item.get("liga"),
            "pais": item.get("pais"),
            "placar": estado.get("placar"),
            "status": estado.get("status"),
            "minuto": estado.get("minuto"),
        }
        try:
            referencia, diagnostico = self._amostrar_referencia_odds_sombra(
                jogo,
                {mercado},
                controlar_ciclo=False,
                origem_coleta="monitor_odd_rapido",
                contexto_auditoria={
                    "ciclo_em": consultado_em,
                    "posicao_fila": item.get("posicao_fila"),
                    "tarefas_ciclo": item.get("fila_total"),
                    "fila_operacional": "monitor_odd_rapido",
                    "liga": item.get("liga"),
                    "minuto": estado.get("minuto"),
                },
            )
        except Exception as erro:
            return {
                **base,
                "tentada": True,
                "motivo": "falha_isolada_referencia_sombra_rapida",
                "tipo_erro": type(erro).__name__,
                "erro": resumir_erro_seguro(erro),
            }
        diagnostico = dict(diagnostico or {})
        resultado = {
            **base,
            "tentada": True,
            "motivo": diagnostico.get("motivo"),
            "reserva_consumida": bool(
                diagnostico.get("reserva_consumida")
            ),
            "consulta_executada": bool(
                diagnostico.get("reserva_consumida")
                and diagnostico.get("consultados")
            ),
            "creditos_estimados_reservados": (
                int(diagnostico.get("custo_estimado_creditos") or 0)
                if diagnostico.get("reserva_consumida") else 0
            ),
            "diagnostico": diagnostico,
        }

        registrar_auditoria = getattr(
            self.banco,
            "registrar_referencia_sombra_acompanhamento_odd",
            None,
        )
        if callable(registrar_auditoria):
            try:
                auditoria = registrar_auditoria(
                    item["sinal_id"],
                    referencia,
                    diagnostico,
                    estado,
                    consultado_em=consultado_em,
                    origem_sinal_id=item.get("origem_sinal_id"),
                    sinal_enviado_id=sinal_enviado_id,
                )
                resultado["auditoria_persistida"] = bool(
                    auditoria.get("persistido")
                )
                resultado["auditoria"] = auditoria
            except Exception as erro:
                resultado["erro_auditoria"] = resumir_erro_seguro(erro)
                resultado["tipo_erro_auditoria"] = type(erro).__name__

        oferta_referencia = extrair_odd_exata_acompanhamento(
            referencia, mercado, item.get("linha")
        )
        if oferta_referencia is None:
            if resultado["consulta_executada"]:
                resultado["motivo"] = "referencia_sem_mesma_linha"
            return resultado
        resultado["linha_exata"] = True
        registrar_observacao = getattr(
            self.banco, "registrar_observacao_acompanhamento_odd", None
        )
        if not callable(registrar_observacao):
            resultado["motivo"] = "persistencia_observacao_indisponivel"
            return resultado
        try:
            observacao = registrar_observacao(
                item["origem_sinal_id"],
                oferta_referencia,
                estado,
                consultado_em=consultado_em,
                url_origem=item.get("packball_url"),
                motivo="referencia_sombra_sincronizada_monitor_rapido",
                odds=referencia,
            )
        except Exception as erro:
            resultado.update({
                "motivo": "falha_persistencia_referencia_sombra_rapida",
                "tipo_erro_persistencia": type(erro).__name__,
                "erro_persistencia": resumir_erro_seguro(erro),
            })
            return resultado
        resultado["observacao"] = observacao
        resultado["observacao_persistida"] = bool(
            observacao.get("persistido")
            and observacao.get("autorizada", True) is not False
            and observacao.get("ordem_temporal_valida", True) is not False
        )
        if not resultado["observacao_persistida"]:
            resultado["motivo"] = str(
                observacao.get("motivo")
                or observacao.get("estado")
                or "referencia_sombra_nao_autorizada"
            )
            return resultado

        registrar_comparacao = getattr(
            self.banco,
            "registrar_corroboracao_acompanhamento_odd_api",
            None,
        )
        if callable(registrar_comparacao):
            odds_multifonte = {
                "pre_jogo": [],
                "ao_vivo": list(
                    copy.deepcopy((odds_operacionais or {}).get("ao_vivo"))
                    or []
                ) + list(copy.deepcopy(referencia.get("ao_vivo")) or []),
            }
            try:
                comparacao = registrar_comparacao(
                    item["origem_sinal_id"],
                    odds_multifonte,
                    estado,
                    consultado_em=consultado_em,
                )
                resultado["comparacoes_persistidas"] = int(
                    comparacao.get("persistidos") or 0
                )
                resultado["comparacao"] = comparacao
            except Exception as erro:
                resultado["erro_comparacao"] = resumir_erro_seguro(erro)
                resultado["tipo_erro_comparacao"] = type(erro).__name__
        resultado["motivo"] = "referencia_mesma_linha_persistida"
        return resultado

    def _complementar_odds_betsapi(
        self, odds, jogo, mercados_para_odds
    ):
        """Usa a Bet365 da BetsAPI como complemento oficial reversivel.

        O cliente faz o pareamento forte, exige placar compativel e elimina
        mercados suspensos. O PackBall permanece primeiro na mescla; a nova
        fonte cobre apenas uma linha que o snapshot principal nao forneceu.
        """
        cliente = getattr(self, "betsapi", None)
        if cliente is None:
            return {
                "ativa": False,
                "pareado": False,
                "anexados": [],
                "motivo": "cliente_ausente",
            }
        internos = {
            item for item in (mercados_para_odds or set())
            if item in {
                "gol_ft", "gol_ht", "proximo_gol",
                "escanteios_ft_asiatico",
            }
        }
        if not internos:
            return {
                **cliente.diagnostico(),
                "pareado": False,
                "anexados": [],
                "motivo": "sem_mercado_compativel",
            }
        encontrados, diagnostico = cliente.buscar_mercados(jogo, internos)
        mercados = (encontrados or {}).get("ao_vivo") or []
        if mercados:
            diagnostico["mescla"] = (
                self._mesclar_mercados_odds_complementares(odds, mercados)
            )
        diagnostico.update(cliente.diagnostico())
        return diagnostico

    @staticmethod
    def _mesclar_mercados_odds_complementares(odds, complementares):
        """Une ofertas auxiliares ao mercado PackBall sem apagar a origem.

        As ofertas PackBall permanecem primeiro. Linhas auxiliares ficam no
        mesmo mercado e são alcançadas pelo seletor quando a linha PackBall
        não atende ao estado atual. Sem mercado PackBall compatível, o bloco
        auxiliar é anexado integralmente como fallback.
        """
        if not isinstance(odds, dict):
            return {"mercados": 0, "ofertas": 0, "anexados": 0}
        mercados = odds.setdefault("ao_vivo", [])
        resumo = {"mercados": 0, "ofertas": 0, "anexados": 0}

        def assinatura(oferta):
            if not isinstance(oferta, dict):
                return None
            return tuple(str(oferta.get(chave)) for chave in (
                "fonte", "bookmaker", "linha", "over", "under",
                "periodo", "tipo_mercado",
            ))

        def anexar_ofertas(destino, novas):
            existentes = {
                assinatura(item) for item in destino
                if isinstance(item, dict)
            }
            adicionadas = 0
            for oferta in novas or []:
                chave = assinatura(oferta)
                if chave is None or chave in existentes:
                    continue
                destino.append(copy.deepcopy(oferta))
                existentes.add(chave)
                adicionadas += 1
            return adicionadas

        def compativel(base, auxiliar):
            if str(base.get("fonte") or "").lower() != "packball":
                return False
            if base.get("categoria") != auxiliar.get("categoria"):
                return False
            if (base.get("escopo") or "total") != (
                auxiliar.get("escopo") or "total"
            ):
                return False
            if (base.get("formato") or "duas_opcoes") != (
                auxiliar.get("formato") or "duas_opcoes"
            ):
                return False
            if base.get("categoria") == "escanteios":
                return base.get("tipo_mercado") == auxiliar.get(
                    "tipo_mercado"
                )
            return True

        for auxiliar in complementares or []:
            if not isinstance(auxiliar, dict):
                continue
            resumo["mercados"] += 1
            base = next(
                (item for item in mercados
                 if isinstance(item, dict) and compativel(item, auxiliar)),
                None,
            )
            if base is None:
                mercados.append(copy.deepcopy(auxiliar))
                resumo["anexados"] += 1
                resumo["ofertas"] += len(auxiliar.get("ofertas") or [])
                resumo["ofertas"] += len(auxiliar.get("ofertas_ht") or [])
                resumo["ofertas"] += sum(
                    len((dados or {}).get("ofertas") or [])
                    for dados in (
                        auxiliar.get("ofertas_periodos") or {}
                    ).values()
                )
                continue

            resumo["ofertas"] += anexar_ofertas(
                base.setdefault("ofertas", []), auxiliar.get("ofertas")
            )
            resumo["ofertas"] += anexar_ofertas(
                base.setdefault("ofertas_ht", []),
                auxiliar.get("ofertas_ht"),
            )
            periodos_base = base.setdefault("ofertas_periodos", {})
            for periodo, dados in (
                auxiliar.get("ofertas_periodos") or {}
            ).items():
                destino = periodos_base.setdefault(
                    periodo,
                    {"formato": (dados or {}).get("formato"), "ofertas": []},
                )
                resumo["ofertas"] += anexar_ofertas(
                    destino.setdefault("ofertas", []),
                    (dados or {}).get("ofertas"),
                )
            fontes = base.setdefault("fontes_complementares", [])
            fonte = str(auxiliar.get("fonte") or "").strip()
            if fonte and fonte not in fontes:
                fontes.append(fonte)
        return resumo

    @staticmethod
    def _autorizar_contrato_odds_thestatsapi(odds):
        """Promove somente o contrato que já passou pelo gate operacional."""
        if not isinstance(odds, dict):
            return odds

        def autorizar(valor):
            if isinstance(valor, dict):
                for chave, item in valor.items():
                    if chave == "aplicacao_sinais":
                        valor[chave] = True
                    elif chave == "autoriza_sinal":
                        valor[chave] = True
                    elif chave == "telegram":
                        valor[chave] = True
                    else:
                        autorizar(item)
            elif isinstance(valor, list):
                for item in valor:
                    autorizar(item)

        autorizar(odds)
        metadados = odds.setdefault("_metadados", {})
        metadados["aplicacao_sinais"] = True
        metadados["autoriza_sinal"] = True
        metadados["telegram"] = True
        metadados["estado"] = "convertido_oficial_fail_closed"
        metadados["rollback"] = "THESTATSAPI_APLICACAO_SINAIS_ATIVA=0"
        return odds

    def processar_jogo(
        self,
        pagina,
        jogo,
        fixtures_api,
        coletar_odds_agora=True,
        instante=None,
        odd_asiatica_api_disponivel=False,
        odds_api_prioritaria=False,
        mercados_acompanhamento_preco=None,
        somente_acompanhamento_preco=False,
    ):
        instante = instante or datetime.now()
        inicio_coleta = time.monotonic()
        inicio_etapa = inicio_coleta
        duracoes_etapas = {}
        mercados_acompanhamento_preco = {
            str(mercado)
            for mercado in (mercados_acompanhamento_preco or ())
            if str(mercado) in {
                "gol_ft", "gol_ht", "proximo_gol",
                "proximo_escanteio", "escanteios_ft_asiatico",
            }
        }

        def marcar_etapa(nome):
            nonlocal inicio_etapa
            agora = time.monotonic()
            duracoes_etapas[str(nome)] = round(
                max(agora - inicio_etapa, 0.0), 3
            )
            inicio_etapa = agora

        def resumir_duracoes_etapas():
            total = max(time.monotonic() - inicio_coleta, 0.0)
            medido = sum(
                float(valor) for valor in duracoes_etapas.values()
                if isinstance(valor, (int, float))
            )
            return {
                "versao": "duracoes-etapas-detalhe-v1",
                "etapas": dict(duracoes_etapas),
                "total_segundos": round(total, 3),
                "nao_classificado_segundos": round(
                    max(total - medido, 0.0), 3
                ),
                "altera_sinal": False,
            }

        odds_anteriores = self.banco.carregar_ultimas_odds(jogo["url"])
        falhas_fontes = []
        estatisticas, jogo, falha_estatisticas = (
            self._coletar_estatisticas_seguras(pagina, jogo)
        )
        diagnostico_coleta_estatisticas = dict(
            getattr(
                getattr(self, "packball", None),
                "ultimo_diagnostico_estatisticas",
                {},
            ) or {}
        )
        estatisticas, diagnostico_fallback_lista = (
            complementar_estatisticas_com_lista(
                jogo,
                estatisticas,
                instante=instante,
            )
        )
        estatisticas_packball = dict(estatisticas or {})
        evidencia_thestats = getattr(
            self, "_thestatsapi_fusao_ciclo", {}
        ).get(jogo.get("url")) or {}
        resposta_stats_thestats = evidencia_thestats.get("resposta_stats")
        resposta_odds_thestats = evidencia_thestats.get("resposta_odds")
        gate_thestatsapi = {}
        if resposta_stats_thestats and resposta_odds_thestats:
            gate_thestatsapi = validar_gate_operacional_thestatsapi(
                jogo,
                evidencia_thestats.get("diagnostico"),
                resposta_stats_thestats,
                resposta_odds_thestats,
                agora=datetime.now().astimezone(),
            )
        aplicacao_thestatsapi = bool(
            getattr(self, "thestatsapi_aplicacao_sinais_ativa", False)
            and gate_thestatsapi.get("apto_sombra") is True
        )
        estatisticas, diagnostico_fusao = fundir_estatisticas_packball_thestats(
            jogo,
            estatisticas_packball,
            evidencia_thestats,
            agora=datetime.now().astimezone(),
        )
        diagnostico_fusao["gate_operacional"] = gate_thestatsapi
        diagnostico_fusao["aplicacao_sinais"] = aplicacao_thestatsapi
        diagnostico_fusao["rollback"] = (
            "THESTATSAPI_APLICACAO_SINAIS_ATIVA=0"
        )
        if falha_estatisticas:
            falhas_fontes.append(falha_estatisticas)
        marcar_etapa("estatisticas_packball_e_fusao")
        odds, falha_odds = self._coletar_odds_seguras(
            pagina,
            jogo,
            odds_anteriores,
            coletar_odds_agora,
        )
        odds_packball = copy.deepcopy(odds)
        mescla_odds_thestatsapi = {
            "mercados": 0,
            "ofertas": 0,
            "anexados": 0,
        }
        if resposta_stats_thestats and resposta_odds_thestats:
            gate_odds_thestats = gate_thestatsapi
            if gate_odds_thestats.get("apto_sombra") is True:
                odds_thestats = converter_odds_bet365_contrato_interno(
                    resposta_odds_thestats,
                    agora=datetime.now().astimezone(),
                )
                if aplicacao_thestatsapi:
                    odds_thestats = (
                        self._autorizar_contrato_odds_thestatsapi(
                            odds_thestats
                        )
                    )
                mercados_thestats = odds_thestats.get("ao_vivo") or []
                if mercados_thestats:
                    # PackBall permanece primeiro. TheStats completa linhas
                    # no mesmo mercado e preserva a origem de cada oferta.
                    mescla_odds_thestatsapi = (
                        self._mesclar_mercados_odds_complementares(
                        odds, mercados_thestats
                        )
                    )
                    diagnostico_fusao["complementou"].append("Odds Bet365")
                    diagnostico_fusao["valida"] = True
                    diagnostico_fusao["odds_bet365_thestats"] = True
                    diagnostico_fusao["odds_oficiais"] = (
                        aplicacao_thestatsapi
                    )
        diagnostico_odds_thestatsapi = {
            "evidencia_disponivel": bool(
                resposta_stats_thestats and resposta_odds_thestats
            ),
            "gate_motivo": gate_thestatsapi.get("motivo"),
            "gate_apto": gate_thestatsapi.get("apto_sombra") is True,
            "aplicacao_sinais": aplicacao_thestatsapi,
            "mercados_convertidos": int(
                mescla_odds_thestatsapi.get("mercados", 0) or 0
            ),
            "ofertas_anexadas": int(
                mescla_odds_thestatsapi.get("ofertas", 0) or 0
            ),
            "mercados_anexados": int(
                mescla_odds_thestatsapi.get("anexados", 0) or 0
            ),
            "rollback": "THESTATSAPI_APLICACAO_SINAIS_ATIVA=0",
        }
        if falha_odds:
            falhas_fontes.append(falha_odds)
        marcar_etapa("odds_packball_e_fusao")
        diagnostico_api = {"motivo": "erro_processamento"}
        odd_asiatica_api_anexada = False
        cliente_the_odds_api = getattr(self, "the_odds_api", None)
        diagnostico_the_odds_api = (
            cliente_the_odds_api.diagnostico()
            if cliente_the_odds_api is not None
            else {"ativa": False, "motivo": "cliente_ausente"}
        )
        cliente_betsapi = getattr(self, "betsapi", None)
        diagnostico_betsapi = (
            cliente_betsapi.diagnostico()
            if cliente_betsapi is not None
            else {"ativa": False, "motivo": "cliente_ausente"}
        )
        odds_referencia_sombra = {"pre_jogo": [], "ao_vivo": []}
        anexados_betsapi = set()
        diagnostico_amostragem_referencia = {
            "ativa": bool(getattr(
                cliente_the_odds_api,
                "amostragem_referencia_ativa",
                False,
            )),
            "motivo": "sem_mercado_elegivel",
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        candidatos_fusao_temporal = []
        candidatos_base_lista_temporal = []
        evolucao_sem_fallback_lista = {"5": None, "10": None, "15": None}
        diagnostico_temporal = {}
        diagnostico_indicadores_temporais_lista = {
            "versao": "packball-lista-janelas-sombra-v1",
            "estado": "nao_avaliado",
            "aplicacao_sinais": False,
        }
        try:
            diagnostico_api = diagnosticar_associacao(jogo, fixtures_api)
            confirmacao_api = diagnostico_api["associacao"]
            estatisticas_embutidas = None
            jogadores_embutidos = None
            escalacoes_embutidas = None
            if confirmacao_api:
                estatisticas_embutidas = confirmacao_api.pop(
                    "_estatisticas_embutidas", None
                )
                jogadores_embutidos = confirmacao_api.pop(
                    "_jogadores_embutidos", None
                )
                escalacoes_embutidas = confirmacao_api.pop(
                    "_escalacoes_embutidas", None
                )
            evolucao = self.historico.calcular(
                jogo["url"],
                estatisticas,
                instante,
                jogo.get("status"),
                jogo.get("placar"),
                (confirmacao_api or {}).get("eventos"),
            )
            evolucao["escanteios_intervalo"] = (
                self.banco.total_escanteios_intervalo(
                    packball_url=jogo["url"]
                )
            )
            evolucao_sem_fallback_lista = copy.deepcopy(evolucao)
            evolucao, diagnostico_indicadores_temporais_lista = (
                self._auditar_e_aplicar_indicadores_lista_temporais(
                    jogo, evolucao, instante
                )
            )
            qualidade_previa = avaliar_qualidade(
                jogo,
                estatisticas,
                confirmacao_api,
                time.monotonic() - inicio_coleta,
            )
            qualidade_previa["fallback_indicadores_lista"] = (
                diagnostico_fallback_lista
            )
            qualidade_previa[
                "auditoria_indicadores_temporais_lista"
            ] = diagnostico_indicadores_temporais_lista
            candidatos_previos = self._gerar_candidatos_rastreaveis(
                jogo, estatisticas, evolucao, odds, qualidade_previa
            )
            mercados_para_odds_api = (
                self._mercados_com_potencial_para_odds_api(
                    candidatos_previos
                )
            )
            mercados_para_odds_api.update(
                mercados_acompanhamento_preco
            )
            if odds_api_prioritaria:
                # O teste de capacidade pula a segunda navegacao PackBall.
                # As mesmas politicas continuam decidindo o sinal; esta lista
                # apenas garante que as odds auxiliares sejam consultadas.
                mercados_para_odds_api.update({
                    "gol_ft",
                    "proximo_gol",
                    "escanteios_ft_asiatico",
                })
                minuto_odds = extrair_minuto(jogo.get("status"))
                if minuto_odds is None or minuto_odds <= 45:
                    mercados_para_odds_api.add("gol_ht")
            # A varredura global cacheada já comprovou que esta fixture tem
            # Asian Corners. Não espere a própria odd existir no snapshot
            # para então decidir consultá-la: isso criaria um ciclo lógico.
            # A anexação ainda usa a fixture novamente associada e todos os
            # filtros de minuto, frescor, linha e segurança do motor.
            if odd_asiatica_api_disponivel:
                mercados_para_odds_api.add("escanteios_ft_asiatico")
            precisa_eventos = bool(
                self.precisa_eventos_proximo_gol(jogo)
                or "proximo_gol" in mercados_para_odds_api
                or elegivel_para_enriquecimento_v2(
                    jogo, qualidade_previa, candidatos_previos
                )
                or elegivel_gol_ht_00_min20(
                    jogo, qualidade_previa, candidatos_previos
                )
                or elegivel_gol_ft_tendencia_mais_um(
                    jogo, qualidade_previa, candidatos_previos
                )
                or any(
                    item.get("mercado") == "proximo_gol"
                    and item.get("status") == "aprovado"
                    for item in candidatos_previos
                )
            )
            if (
                confirmacao_api
                and confirmacao_api.get("fixture_id")
                and not (confirmacao_api.get("eventos") or [])
                and precisa_eventos
            ):
                eventos = self.api.eventos(confirmacao_api["fixture_id"])
                if isinstance(eventos, list):
                    confirmacao_api["eventos"] = eventos
                    evolucao = self.historico.calcular(
                        jogo["url"],
                        estatisticas,
                        instante,
                        jogo.get("status"),
                        jogo.get("placar"),
                        eventos,
                    )
                    evolucao["escanteios_intervalo"] = (
                        self.banco.total_escanteios_intervalo(
                            packball_url=jogo["url"]
                        )
                    )
                    evolucao_sem_fallback_lista = copy.deepcopy(evolucao)
                    (
                        evolucao,
                        diagnostico_indicadores_temporais_lista,
                    ) = self._auditar_e_aplicar_indicadores_lista_temporais(
                        jogo, evolucao, instante
                    )
                    candidatos_previos = self._gerar_candidatos_rastreaveis(
                        jogo,
                        estatisticas,
                        evolucao,
                        odds,
                        qualidade_previa,
                    )
                    mercados_para_odds_api = (
                        self._mercados_com_potencial_para_odds_api(
                            candidatos_previos
                        )
                    )
                    mercados_para_odds_api.update(
                        mercados_acompanhamento_preco
                    )
                    if odds_api_prioritaria:
                        mercados_para_odds_api.update({
                            "gol_ft",
                            "proximo_gol",
                            "escanteios_ft_asiatico",
                        })
                        minuto_odds = extrair_minuto(jogo.get("status"))
                        if minuto_odds is None or minuto_odds <= 45:
                            mercados_para_odds_api.add("gol_ht")
                    if odd_asiatica_api_disponivel:
                        mercados_para_odds_api.add(
                            "escanteios_ft_asiatico"
                        )
            if mercados_para_odds_api:
                mercados_restantes = set(mercados_para_odds_api)
                try:
                    diagnostico_betsapi = (
                        self._complementar_odds_betsapi(
                            odds, jogo, mercados_para_odds_api
                        )
                    )
                    anexados_betsapi = set(
                        diagnostico_betsapi.get("anexados") or []
                    )
                    mercados_restantes -= anexados_betsapi
                    if "escanteios_ft_asiatico" in anexados_betsapi:
                        odd_asiatica_api_anexada = True
                except Exception as erro:
                    # BetsAPI e complementar: uma falha jamais impede que
                    # PackBall, The Odds API e API-Football prossigam.
                    self._registrar_falha_fonte(
                        "betsapi",
                        jogo,
                        erro,
                        "demais_fontes_de_odds_preservadas",
                    )
                    diagnostico_betsapi = {
                        **(
                            cliente_betsapi.diagnostico()
                            if cliente_betsapi is not None else {}
                        ),
                        "pareado": False,
                        "anexados": [],
                        "motivo": "falha_isolada",
                    }
                try:
                    diagnostico_the_odds_api = (
                        self._complementar_odds_the_odds_api(
                            odds, jogo, mercados_restantes
                        )
                    )
                    if "escanteios_ft_asiatico" in mercados_para_odds_api:
                        odd_asiatica_api_anexada = bool(
                            self._complementar_odds_escanteios_ft_api(
                                odds,
                                jogo,
                                confirmacao_api,
                                coletar_odds_agora,
                            )
                        )
                    if "gol_ft" in mercados_para_odds_api:
                        self._complementar_odds_gols_ft_api(
                            odds, jogo, confirmacao_api
                        )
                    if "proximo_gol" in mercados_para_odds_api:
                        self._complementar_odds_proximo_gol_api(
                            odds, jogo, confirmacao_api
                        )
                except Exception as erro:
                    falhas_fontes.append(
                        self._registrar_falha_fonte(
                            "odds_api_football",
                            jogo,
                            erro,
                            "sinal_bloqueado",
                        )
                    )
                diagnostico_amostragem_referencia = {
                    **diagnostico_amostragem_referencia,
                    "motivo": "aguardando_decisao_operacional_final",
                    "mercados_betsapi_anexados": sorted(
                        anexados_betsapi
                    ),
                }
                diagnostico_the_odds_api[
                    "amostragem_referencia_sombra"
                ] = diagnostico_amostragem_referencia
            candidatos_apos_odds = self._gerar_candidatos_rastreaveis(
                jogo,
                estatisticas,
                evolucao,
                odds,
                qualidade_previa,
                odds_referencia_sombra=odds_referencia_sombra,
            )
            candidato_api = self._tem_candidato_aprovado(
                candidatos_apos_odds
            )
            candidato_antecipado = elegivel_para_enriquecimento_antecipado(
                jogo, qualidade_previa, candidatos_apos_odds
            )
            candidato_capacidade = elegivel_para_enriquecimento_capacidade(
                jogo, qualidade_previa, candidatos_apos_odds
            )
            candidato_capacidade_v2 = elegivel_para_enriquecimento_v2(
                jogo, qualidade_previa, candidatos_apos_odds
            )
            candidato_ht_00_min20 = elegivel_gol_ht_00_min20(
                jogo, qualidade_previa, candidatos_apos_odds
            )
            candidato_ft_tendencia = elegivel_gol_ft_tendencia_mais_um(
                jogo, qualidade_previa, candidatos_apos_odds
            )
            estatisticas_api = (
                estatisticas_embutidas
                if isinstance(estatisticas_embutidas, list)
                and estatisticas_embutidas
                else None
            )
            jogadores_api = (
                jogadores_embutidos
                if isinstance(jogadores_embutidos, list)
                and jogadores_embutidos
                else None
            )
            contexto_api = None
            if (
                confirmacao_api
                and confirmacao_api.get("fixture_id")
                and (
                    candidato_api or candidato_antecipado
                    or candidato_capacidade or candidato_capacidade_v2
                    or candidato_ht_00_min20 or candidato_ft_tendencia
                )
            ):
                if estatisticas_api is None:
                    estatisticas_api = self.api.estatisticas(
                        confirmacao_api["fixture_id"]
                    )
                if jogadores_api is None:
                    coletar_jogadores = getattr(
                        self.api, "estatisticas_jogadores", None
                    )
                    if callable(coletar_jogadores):
                        resposta_jogadores = coletar_jogadores(
                            confirmacao_api["fixture_id"]
                        )
                        if isinstance(resposta_jogadores, list):
                            jogadores_api = resposta_jogadores
            contexto_avancado_ativo = (
                os.getenv("API_CONTEXTO_AVANCADO_ATIVO", "1") == "1"
            )
            if (
                contexto_avancado_ativo
                and confirmacao_api
                and confirmacao_api.get("fixture_id")
                and (
                    candidato_api or candidato_antecipado
                    or candidato_capacidade or candidato_capacidade_v2
                    or candidato_ht_00_min20 or candidato_ft_tendencia
                )
            ):
                try:
                    coletar_contexto = getattr(
                        type(self.api), "contexto_pre_jogo", None
                    )
                    if callable(coletar_contexto):
                        confirmacao_contexto = dict(confirmacao_api)
                        if isinstance(escalacoes_embutidas, list):
                            confirmacao_contexto[
                                "_escalacoes_embutidas"
                            ] = escalacoes_embutidas
                        contexto_api = coletar_contexto(
                            self.api, confirmacao_contexto
                        )
                    if contexto_api is not None:
                        contexto_api["comparacao_fontes_ao_vivo"] = (
                            comparar_estatisticas_ao_vivo(
                                estatisticas,
                                estatisticas_api,
                                confirmacao_api,
                            )
                        )
                        contexto_api["estatisticas_ao_vivo"] = (
                            resumir_estatisticas_api_ao_vivo(
                                estatisticas_api,
                                confirmacao_api,
                            )
                        )
                        contexto_api["jogadores_ao_vivo"] = (
                            resumir_jogadores_api_ao_vivo(
                                jogadores_api,
                                confirmacao_api,
                            )
                        )
                        contexto_api["eventos_ao_vivo"] = (
                            resumir_eventos_api_ao_vivo(
                                (confirmacao_api or {}).get("eventos"),
                                confirmacao_api,
                            )
                        )
                        cobertura = contexto_api.setdefault("cobertura", {})
                        cobertura["estatisticas_ao_vivo"] = bool(
                            estatisticas_api
                        )
                        cobertura["jogadores_ao_vivo"] = bool(
                            jogadores_api
                        )
                        cobertura["eventos_ao_vivo"] = bool(
                            (confirmacao_api or {}).get("eventos")
                        )
                except Exception as erro:
                    falhas_fontes.append(
                        self._registrar_falha_fonte(
                            "contexto_api_football",
                            jogo,
                            erro,
                            "analise_live_preservada",
                        )
                    )
            # A auditoria temporal não depende de haver um candidato
            # aprovado nem realiza consultas externas. Assim, mede a
            # concordância PackBall/API também nos jogos descartados sem
            # contaminar a decisão dos sinais.
            if (
                confirmacao_api
                and confirmacao_api.get("fixture_id")
            ):
                contexto_api = self._anexar_historico_api_live_contexto(
                    contexto_api if isinstance(contexto_api, dict) else {},
                    confirmacao_api,
                    jogo,
                    evolucao,
                    instante,
                )
            precisa_contexto_gols = self._precisa_contexto_linhas_gols(
                candidatos_apos_odds,
                mercados_para_odds_api,
                candidato_antecipado=candidato_antecipado,
                candidato_capacidade=candidato_capacidade,
                candidato_capacidade_v2=candidato_capacidade_v2,
                candidato_ht_00_min20=candidato_ht_00_min20,
                candidato_ft_tendencia=candidato_ft_tendencia,
            )
            if (
                (candidato_capacidade_v2 or candidato_ft_tendencia
                 or precisa_contexto_gols)
                and confirmacao_api
            ):
                try:
                    contexto_api = coletar_contexto_capacidade_v2(
                        self.api,
                        confirmacao_api,
                        contexto_api if isinstance(contexto_api, dict) else {},
                    )
                except Exception as erro:
                    self._registrar_falha_fonte(
                        "contexto_capacidade_v2",
                        jogo,
                        erro,
                        "challenger_v2_ignorado_sem_afetar_metodos_ativos",
                    )
            if (
                (candidato_ht_00_min20 or candidato_ft_tendencia)
                and confirmacao_api
            ):
                try:
                    contexto_api = coletar_contexto_periodos_10(
                        self.api,
                        confirmacao_api,
                        contexto_api if isinstance(contexto_api, dict) else {},
                    )
                except Exception as erro:
                    self._registrar_falha_fonte(
                        "contexto_periodos_10",
                        jogo,
                        erro,
                        "top_criterios_ignorados_sem_afetar_metodos_ativos",
                    )
            if precisa_contexto_gols and confirmacao_api:
                try:
                    contexto_api = coletar_contexto_linhas_gols(
                        self.api,
                        confirmacao_api,
                        contexto_api if isinstance(contexto_api, dict) else {},
                    )
                except Exception as erro:
                    self._registrar_falha_fonte(
                        "contexto_linhas_gols",
                        jogo,
                        erro,
                        "hipotese_ft_v3_ignorada_sem_afetar_metodos_ativos",
                    )
            qualidade = avaliar_qualidade(
                jogo,
                estatisticas,
                confirmacao_api,
                time.monotonic() - inicio_coleta,
            )
            qualidade["fallback_indicadores_lista"] = (
                diagnostico_fallback_lista
            )
            qualidade["coleta_estatisticas_packball"] = (
                diagnostico_coleta_estatisticas
            )
            qualidade[
                "auditoria_indicadores_temporais_lista"
            ] = diagnostico_indicadores_temporais_lista
            qualidade["associacao_api"] = {
                chave: valor for chave, valor in diagnostico_api.items()
                if chave != "associacao"
            }
            qualidade["enriquecimento_api_elegivel"] = candidato_api
            qualidade["mercados_consultados_odds_api"] = sorted(
                mercados_para_odds_api
            )
            qualidade["the_odds_api"] = diagnostico_the_odds_api
            qualidade["betsapi"] = diagnostico_betsapi
            qualidade["odds_thestatsapi"] = diagnostico_odds_thestatsapi
            diagnostico_resgate_qualidade_api = (
                avaliar_resgate_qualidade_api(
                    self.banco.conexao,
                    jogo,
                    confirmacao_api,
                    estatisticas,
                    qualidade,
                    agora=instante,
                )
            )
            qualidade["resgate_qualidade_api_sombra"] = (
                diagnostico_resgate_qualidade_api
            )
            candidatos = self._gerar_candidatos_rastreaveis(
                jogo,
                estatisticas,
                evolucao,
                odds,
                qualidade,
                odds_referencia_sombra=odds_referencia_sombra,
            )
            if (
                diagnostico_indicadores_temporais_lista.get(
                    "fallback_condicional", {}
                ).get("aplicado")
            ):
                candidatos_base_lista_temporal = (
                    self._gerar_candidatos_rastreaveis(
                        jogo,
                        estatisticas,
                        evolucao_sem_fallback_lista,
                        odds,
                        qualidade,
                    )
                )
            if self._fontes_temporais_aptas(instante):
                evolucao_fundida, diagnostico_temporal = (
                    fundir_evolucao_temporal_como_fallback(
                        evolucao, contexto_api
                    )
                )
                if evolucao_fundida is not None:
                    candidatos_fusao_temporal = (
                        self._gerar_candidatos_rastreaveis(
                            jogo, estatisticas, evolucao_fundida,
                            odds, qualidade,
                        )
                    )
            if (
                diagnostico_fusao.get("valida")
                and diagnostico_fusao.get("complementou")
            ):
                evolucao_base = self.historico.calcular(
                    jogo["url"], estatisticas_packball, instante,
                    jogo.get("status"), jogo.get("placar"),
                    (confirmacao_api or {}).get("eventos"),
                )
                candidatos_base = self._gerar_candidatos_rastreaveis(
                jogo, estatisticas_packball, evolucao_base, odds_packball,
                    qualidade,
                )
                marcar_candidatos_dependentes_fusao(
                    candidatos,
                    candidatos_base,
                    diagnostico_fusao,
                    aplicacao_sinais=aplicacao_thestatsapi,
                )
        except Exception as erro:
            evolucao = {"5": None, "10": None, "15": None}
            confirmacao_api = None
            estatisticas_api = None
            jogadores_api = None
            contexto_api = None
            qualidade = avaliar_qualidade(jogo, {})
            qualidade["fallback_indicadores_lista"] = (
                diagnostico_fallback_lista
            )
            qualidade["coleta_estatisticas_packball"] = (
                diagnostico_coleta_estatisticas
            )
            qualidade[
                "auditoria_indicadores_temporais_lista"
            ] = diagnostico_indicadores_temporais_lista
            qualidade["associacao_api"] = {
                "motivo": diagnostico_api.get("motivo", "erro_processamento")
            }
            qualidade["odds_thestatsapi"] = diagnostico_odds_thestatsapi
            diagnostico_resgate_qualidade_api = {
                "versao": "resgate-qualidade-api-live-sombra-v1",
                "estado": "falha_isolada_processamento",
                "aplicacao_sinais": False,
                "telegram": False,
            }
            candidatos = self._gerar_candidatos_rastreaveis(
                jogo,
                estatisticas,
                evolucao,
                odds,
                qualidade,
                odds_referencia_sombra=odds_referencia_sombra,
            )
            falhas_fontes.append(
                self._registrar_falha_fonte(
                    "processamento_jogo",
                    jogo,
                    erro,
                    "dados_parciais_persistidos",
                )
            )

        marcar_etapa("api_contexto_e_motor_base")

        candidatos = filtrar_mercados_operacionais(candidatos)
        candidatos_base_lista_temporal = filtrar_mercados_operacionais(
            candidatos_base_lista_temporal
        )
        candidatos_fusao_temporal = filtrar_mercados_operacionais(
            candidatos_fusao_temporal
        )
        aplicar_politicas_por_mercado(candidatos)
        for candidato in candidatos:
            aplicar_politica_gol_ht(candidato)
            aplicar_politica_proximo_gol(candidato)
            aplicar_politica_gols_tempo(candidato)
        aplicar_politicas_por_mercado(candidatos_base_lista_temporal)
        for candidato in candidatos_base_lista_temporal:
            aplicar_politica_gol_ht(candidato)
            aplicar_politica_proximo_gol(candidato)
            aplicar_politica_gols_tempo(candidato)
        marcar_dependencia_fallback_temporal_lista(
            candidatos,
            candidatos_base_lista_temporal,
            diagnostico_indicadores_temporais_lista,
        )
        for candidato in candidatos_fusao_temporal:
            aplicar_politica_gol_ht(candidato)
            aplicar_politica_proximo_gol(candidato)
            aplicar_politica_gols_tempo(candidato)
        candidatos.extend(gerar_candidatos_fusao_temporal(
            candidatos, candidatos_fusao_temporal,
            diagnostico_temporal,
        ))
        candidatos_antecipados = gerar_gols_antecipados(
            jogo, candidatos, contexto_api, qualidade
        )
        diagnostico_gols_antecipados = diagnosticar_gols_antecipados(
            jogo, candidatos, contexto_api, qualidade,
            candidatos_antecipados,
        )
        # Preserva a decisão causal do gerador junto ao snapshot. Essa
        # telemetria é somente diagnóstica: não altera candidatos, alertas ou
        # resultados e permite explicar futuramente onde o funil foi barrado.
        qualidade["diagnostico_gols_antecipados"] = (
            diagnostico_gols_antecipados
        )
        candidatos_capacidade = gerar_gols_capacidade_times(
            jogo, candidatos, contexto_api, qualidade
        )
        candidatos_capacidade_v2 = gerar_gols_capacidade_contextual_v2(
            jogo, candidatos, contexto_api, qualidade
        )
        diagnostico_capacidade_contextual_v2 = (
            diagnosticar_gols_capacidade_contextual_v2(
                jogo,
                candidatos,
                contexto_api,
                qualidade,
                candidatos_capacidade_v2,
            )
        )
        candidatos_ht_00_min20 = gerar_gol_ht_00_min20(
            jogo, candidatos, contexto_api, qualidade
        )
        candidatos_ft_tendencia = gerar_gol_ft_tendencia_mais_um(
            jogo, candidatos, contexto_api, qualidade
        )
        candidatos_top_ht = gerar_top_criterio_ht(
            candidatos_ht_00_min20, contexto_api
        )
        candidatos_top_ft = gerar_top_criterio_ft(
            candidatos_ft_tendencia, contexto_api
        )
        tendencia_ht_red = self.banco.obter_tendencia_ht_red_para_2t(
            jogo.get("url"), VERSAO_GOL_2T_POS_HT_RED
        )
        candidatos_2t_pos_ht_red = gerar_gol_2t_pos_ht_red(
            jogo, candidatos, qualidade, tendencia_ht_red
        )
        acompanhamentos_metodos = gerar_acompanhamentos_metodos_gols(
            jogo, candidatos, contexto_api, qualidade,
            getattr(self, "alertas", None), tendencia_ht_red,
        )
        candidatos.extend(candidatos_antecipados)
        candidatos.extend(candidatos_capacidade)
        candidatos.extend(candidatos_capacidade_v2)
        candidatos.extend(candidatos_ht_00_min20)
        candidatos.extend(candidatos_ft_tendencia)
        candidatos.extend(candidatos_top_ht)
        candidatos.extend(candidatos_top_ft)
        candidatos.extend(candidatos_2t_pos_ht_red)
        candidatos.extend(acompanhamentos_metodos)
        candidatos_proximo_gol_balanceado = (
            gerar_proximo_gol_balanceado_sombra(candidatos)
        )
        candidatos.extend(candidatos_proximo_gol_balanceado)
        preparar_acompanhamento_odd(candidatos)
        qualidade["gol_2t_pos_ht_red_sombra"] = {
            "tendencia_ht_identificada": bool(
                tendencia_ht_red.get("identificada")
            ),
            "ja_registrado": bool(tendencia_ht_red.get("ja_registrado")),
            "candidatos": len(candidatos_2t_pos_ht_red),
            "aplicacao_automatica": False,
            "telegram_oficial": False,
            "rollback": "GOL_2T_POS_HT_RED_SOMBRA_ATIVO=0",
        }
        qualidade["proximo_gol_balanceado_sombra"] = {
            "candidatos": len(candidatos_proximo_gol_balanceado),
            "aplicacao_sinais": False,
            "telegram": "somente_grupo_teste",
            "telegram_oficial": False,
            "promocao_automatica": False,
            "rollback": "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO=0",
        }
        diagnostico_protecao_conversao = aplicar_protecao_conversao_gols(
            candidatos, contexto_api
        )
        qualidade["protecao_conversao_gols"] = diagnostico_protecao_conversao
        diagnostico_tendencias_packball = {
            "avaliados": 0,
            "aprovados": 0,
            "bloqueados": 0,
            "motivos": {},
            "estado": "sem_candidato_elegivel",
        }
        candidatos_tendencia_packball = [
            item for item in candidatos
            if item.get("mercado") in {"gol_ft", "gol_ht", "proximo_gol"}
            and item.get("status") in {"aprovado", "simulacao"}
            and (
                (
                    (item.get("features") or {}).get(
                        "protecao_conversao_gols"
                    )
                    or {}
                ).get("aprovada")
                is not False
            )
        ]
        coletor_tendencias = getattr(
            type(getattr(self, "packball", None)),
            "coletar_tendencias_gols_liga",
            None,
        )
        if candidatos_tendencia_packball and callable(coletor_tendencias):
            try:
                contexto_tendencias_packball = coletor_tendencias(
                    self.packball,
                    pagina,
                    jogo,
                    periodo_tendencia_packball(jogo),
                )
                diagnostico_tendencias_packball = (
                    aplicar_protecao_tendencias_packball(
                        candidatos_tendencia_packball,
                        contexto_tendencias_packball,
                        jogo,
                        confirmacao_api,
                    )
                )
                diagnostico_tendencias_packball["estado"] = "avaliada"
                diagnostico_tendencias_packball["periodo"] = (
                    contexto_tendencias_packball.get("periodo")
                )
                diagnostico_tendencias_packball["cache"] = bool(
                    contexto_tendencias_packball.get("cache")
                )
                diagnostico_tendencias_packball["fonte"] = (
                    contexto_tendencias_packball.get("fonte")
                )
                if contexto_tendencias_packball.get("fallback_dom"):
                    diagnostico_tendencias_packball["fallback_dom"] = (
                        contexto_tendencias_packball["fallback_dom"]
                    )
            except PackBallBloqueadoError:
                raise
            except Exception as erro:
                contexto_tendencias_packball = {
                    "versao": VERSAO_TENDENCIAS_PACKBALL,
                    "estado": "indisponivel",
                    "erro": type(erro).__name__,
                }
                diagnostico_tendencias_packball = (
                    aplicar_protecao_tendencias_packball(
                        candidatos_tendencia_packball,
                        contexto_tendencias_packball,
                        jogo,
                        confirmacao_api,
                    )
                )
                diagnostico_tendencias_packball.update({
                    "estado": (
                        "indisponivel_fallback_historico"
                        if diagnostico_tendencias_packball.get(
                            "bloqueados", 0
                        ) == 0
                        and diagnostico_tendencias_packball.get(
                            "fallbacks_historicos", 0
                        ) > 0
                        else "indisponivel_fail_closed"
                    ),
                    "erro": type(erro).__name__,
                    "detalhe": str(erro)[:300],
                })
        elif candidatos_tendencia_packball:
            diagnostico_tendencias_packball["estado"] = (
                "coletor_nao_disponivel_no_ambiente"
            )
        qualidade["protecao_tendencias_packball"] = (
            diagnostico_tendencias_packball
        )
        marcar_etapa("politicas_e_tendencias_liga")
        diagnostico_gol_ht_protegido = aplicar_politica_gol_ht_protegido(
            candidatos
        )
        qualidade["gol_ht_protegido"] = diagnostico_gol_ht_protegido
        diagnostico_gol_ft_reforcado = aplicar_politica_gol_ft_reforcado(
            candidatos, contexto_api
        )
        qualidade["gol_ft_reforcado"] = diagnostico_gol_ft_reforcado
        estado_fontes = self._estado_fontes_para_sinal(falhas_fontes)
        qualidade["acompanhamento_odd"] = finalizar_acompanhamento_odd(
            candidatos,
            fontes_saudaveis=estado_fontes.get("saudavel") is True,
        )
        if estado_fontes.get("saudavel") is not True:
            self._operacao_bloqueada_ciclo = True
            self._invalidar_alertas_pendentes_ciclo()
        elif getattr(self, "_operacao_bloqueada_ciclo", False):
            estado_fontes = {
                **estado_fontes,
                "saudavel": False,
                "motivos": list(estado_fontes.get("motivos") or [])
                + ["operacao_degradada_no_ciclo"],
            }
        qualidade["apto_para_liquidacao"] = bool(
            estado_fontes.get("saudavel") is True
        )
        qualidade["integridade_fontes"] = estado_fontes
        bloqueados_fontes = self._bloquear_candidatos_por_fontes(
            candidatos, estado_fontes
        )
        if bloqueados_fontes:
            qualidade["apto_para_sinal"] = False
            alertas_qualidade = qualidade.setdefault("alertas", [])
            if "fontes_operacionais_incompletas" not in alertas_qualidade:
                alertas_qualidade.append("fontes_operacionais_incompletas")
            print(
                "  Sinais bloqueados por fonte incompleta: "
                f"{bloqueados_fontes} | "
                + ", ".join(estado_fontes["motivos"])
            )
        mercados_referencia, diagnostico_priorizacao_referencia = (
            self._priorizar_referencia_valor_justo(
                jogo, candidatos, anexados_betsapi
            )
        )
        if mercados_referencia:
            try:
                (
                    odds_referencia_sombra,
                    diagnostico_amostragem_referencia,
                ) = self._amostrar_referencia_odds_sombra(
                    jogo,
                    mercados_referencia,
                    permitir_recuperacao_coorte=True,
                )
            except Exception as erro:
                # A coleta e observacional. Sua falha nao degrada as fontes
                # operacionais nem bloqueia HT, FT ou Telegram.
                diagnostico_amostragem_referencia = {
                    "ativa": bool(getattr(
                        cliente_the_odds_api,
                        "amostragem_referencia_ativa",
                        False,
                    )),
                    "motivo": "falha_isolada",
                    "erro": type(erro).__name__,
                    "aplicacao_sinais": False,
                    "telegram": False,
                    "promocao_automatica": False,
                }
        else:
            diagnostico_amostragem_referencia = {
                **diagnostico_amostragem_referencia,
                "motivo": "sem_candidato_liquidavel_betsapi",
                "reserva_consumida": False,
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            }
        diagnostico_amostragem_referencia["priorizacao_valor_justo"] = (
            diagnostico_priorizacao_referencia
        )
        diagnostico_the_odds_api[
            "amostragem_referencia_sombra"
        ] = diagnostico_amostragem_referencia
        qualidade["the_odds_api"] = diagnostico_the_odds_api
        diagnostico_referencia_api_football = {
            "versao": "api-football-referencia-sombra-v1",
            "ativa": os.getenv(
                "API_FOOTBALL_REFERENCIA_SOMBRA_ATIVA", "1"
            ) == "1",
            "motivo": (
                "referencia_the_odds_api_disponivel"
                if odds_referencia_sombra.get("ao_vivo")
                else "sem_candidato_liquidavel_betsapi"
                if not mercados_referencia
                else "aguardando_fallback"
            ),
            "pareado": False,
            "aplicacao_sinais": False,
            "altera_calibracao": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        if mercados_referencia and not odds_referencia_sombra.get("ao_vivo"):
            try:
                (
                    referencia_api_football,
                    diagnostico_referencia_api_football,
                ) = self._amostrar_referencia_api_football_sombra(
                    jogo, confirmacao_api, mercados_referencia
                )
                if referencia_api_football.get("ao_vivo"):
                    odds_referencia_sombra = referencia_api_football
            except Exception as erro:
                diagnostico_referencia_api_football = {
                    **diagnostico_referencia_api_football,
                    "motivo": "falha_isolada",
                    "erro": type(erro).__name__,
                }
        qualidade["api_football_referencia_sombra"] = (
            diagnostico_referencia_api_football
        )
        if odds_referencia_sombra.get("ao_vivo"):
            anexar_melhor_preco_sombra(
                candidatos,
                odds,
                instante=datetime.now().astimezone().replace(
                    microsecond=0
                ),
                odds_referencia_sombra=odds_referencia_sombra,
            )
        self._imprimir_jogo(
            jogo, estatisticas, odds, evolucao, confirmacao_api, qualidade
        )
        registro = {
            "coletado_em": instante,
            **jogo,
            "_analise_tecnica_acompanhamento_odd": True,
            "estatisticas": estatisticas,
            "odds": odds,
            "odds_referencia_sombra": odds_referencia_sombra,
            "evolucao": evolucao,
            "confirmacao_api": confirmacao_api,
            "estatisticas_api": estatisticas_api,
            "contexto_api": contexto_api,
            "qualidade": qualidade,
            "falhas_fontes": falhas_fontes,
        }
        qualidade["duracoes_etapas_ate_decisao"] = (
            resumir_duracoes_etapas()
        )
        snapshot_id = self.salvar_registro(registro)
        marcar_etapa("persistencia_snapshot")
        janelas_temporais = [
            janela
            for janela in ("5", "10", "15")
            if isinstance(evolucao.get(janela), dict)
        ]
        if not snapshot_id:
            diagnostico_cobertura_odds = (
                self._diagnosticar_cobertura_odds(odds_packball, odds)
            )
            return {
                "fixture_id": (confirmacao_api or {}).get("fixture_id"),
                "odds_coletadas": self._odds_coletadas_com_sucesso(
                    coletar_odds_agora,
                    falha_odds,
                    odds,
                    aceitar_fonte_auxiliar=odds_api_prioritaria,
                ),
                "api_associacao_motivo": diagnostico_api.get("motivo"),
                "duracao_segundos": round(
                    time.monotonic() - inicio_coleta, 3
                ),
                "janelas_temporais": janelas_temporais,
                "sinais_bloqueados_fontes": bloqueados_fontes,
                "motivos_bloqueio_fontes": list(
                    estado_fontes.get("motivos") or []
                ),
                "odd_asiatica_api_priorizada": bool(
                    odd_asiatica_api_disponivel
                ),
                "odd_asiatica_api_anexada": odd_asiatica_api_anexada,
                "the_odds_api": diagnostico_the_odds_api,
                "betsapi": diagnostico_betsapi,
                "thestatsapi_odds": diagnostico_odds_thestatsapi,
                "cobertura_odds": diagnostico_cobertura_odds,
                "gols_antecipados": diagnostico_gols_antecipados,
                "gols_capacidade_contextual_v2": (
                    diagnostico_capacidade_contextual_v2
                ),
                "resgate_qualidade_api": diagnostico_resgate_qualidade_api,
                "snapshot_id": None,
                "somente_acompanhamento_preco": bool(
                    somente_acompanhamento_preco
                ),
                "duracoes_etapas": resumir_duracoes_etapas(),
            }

        resolvidos = self.backtest.avaliar_snapshot(snapshot_id)
        if resolvidos:
            self._recalibrar()
            print(f"  Backtest: {resolvidos} sinal(is) resolvido(s)")
        cancelados = self.alertas.cancelar_por_evento(
            jogo, evolucao.get("eventos_recentes") or {}
        )
        if cancelados:
            print(f"  Telegram: {cancelados} sinal(is) invalidado(s)")
        if (
            not somente_acompanhamento_preco
            and estado_fontes.get("saudavel") is True
        ):
            exploracoes = self._gerar_exploracoes_sombra_novas(
                snapshot_id,
                [c for c in candidatos if not (c.get("features") or {}).get(
                    "acompanhamento_metodo_gols"
                )],
                odds,
            )
            candidatos.extend(exploracoes)
        if somente_acompanhamento_preco:
            auditorias_bloqueios = []
            pares = []
        else:
            auditorias_bloqueios = self._gerar_auditorias_bloqueadas(
                snapshot_id, candidatos
            )
            candidatos.extend(auditorias_bloqueios)
            candidatos = self._filtrar_exploracoes_repetidas(
                snapshot_id, candidatos
            )
            for candidato in candidatos:
                candidato["regra_fingerprint"] = self.regra_fingerprints[
                    candidato["regra_versao"]
                ]
                anexar_par_odds_sincronizado(candidato, odds)
                self.calibrador.aplicar(candidato)
            ids = self.banco.salvar_candidatos(
                snapshot_id, candidatos, instante
            )
            pares = list(zip(ids, candidatos))
        sincronizacao_ht_preciso = sincronizar_coorte_filtro_ht_preciso(
            self.banco.conexao
        )
        diagnostico_gols_antecipados[
            "filtro_ht_antecipado_preciso"
        ] = sincronizacao_ht_preciso
        sincronizacao_ft_preciso = sincronizar_coorte_filtro_ft_preciso(
            self.banco.conexao
        )
        diagnostico_gols_antecipados[
            "filtro_ft_antecipado_preciso"
        ] = sincronizacao_ft_preciso
        sincronizacao_quase_gol_ft = sincronizar_coorte_quase_gol_ft(
            self.banco.conexao
        )
        diagnostico_gols_antecipados[
            "quase_candidatos_gol_ft_preciso"
        ] = sincronizacao_quase_gol_ft
        sincronizacao_escanteios_ft = sincronizar_coorte_escanteios_ft(
            self.banco.conexao
        )
        diagnostico_gols_antecipados[
            "escanteios_ft_asiatico_executavel"
        ] = sincronizacao_escanteios_ft
        sincronizacao_escanteios_ft_legado = (
            sincronizar_coorte_escanteios_ft_legado(self.banco.conexao)
        )
        diagnostico_gols_antecipados[
            "escanteios_ft_asiatico_legado_fontes_mistas"
        ] = sincronizacao_escanteios_ft_legado
        sincronizacao_quase_proximo_gol = (
            sincronizar_coorte_quase_proximo_gol(self.banco.conexao)
        )
        diagnostico_gols_antecipados[
            "quase_candidatos_proximo_gol"
        ] = sincronizacao_quase_proximo_gol
        for sinal_id, candidato in pares:
            acompanhamento = (
                (candidato.get("features") or {}).get(
                    "acompanhamento_odd"
                )
                or {}
            )
            if acompanhamento.get("elegivel_aviso") is True:
                resultado_aviso = self.alertas.enviar_acompanhamento_odd(
                    sinal_id, candidato, jogo
                )
                if resultado_aviso == "acompanhamento_odd_entregue":
                    print("  Telegram: oportunidade aguardando odd enviada")
        envios = []
        for sinal_id, candidato in pares:
            if candidato.get("_status_persistido") != "aprovado":
                continue
            if (
                self.alertas.modo_teste
                and candidato.get("probabilidade_calibrada") is None
            ):
                continue
            if self._bloquear_exposicao_gol_partida(sinal_id, candidato):
                continue
            envios.append((sinal_id, candidato, dict(jogo)))
        if self.alertas.modo_teste:
            separar_canais = os.getenv(
                "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA", "1"
            ) == "1"
            selecionadas = (
                self._selecionar_simulacoes_teste(pares)
                if separar_canais else [
                    selecionada for selecionada in (
                        self._selecionar_simulacao_teste(pares),
                    ) if selecionada is not None
                ]
            )
            for sinal_id, candidato in selecionadas:
                envios.append((sinal_id, candidato, dict(jogo)))
        if envios:
            if getattr(self, "_adiar_alertas_ciclo", False):
                self._alertas_pendentes_ciclo.extend(envios)
            else:
                self._despachar_alertas(envios)
        marcar_etapa("backtest_calibracao_telegram")
        diagnostico_cobertura_odds = self._diagnosticar_cobertura_odds(
            odds_packball, odds
        )
        return {
            "fixture_id": (confirmacao_api or {}).get("fixture_id"),
            "odds_coletadas": self._odds_coletadas_com_sucesso(
                coletar_odds_agora,
                falha_odds,
                odds,
                aceitar_fonte_auxiliar=odds_api_prioritaria,
            ),
            "api_associacao_motivo": diagnostico_api.get("motivo"),
            "duracao_segundos": round(
                time.monotonic() - inicio_coleta, 3
            ),
            "janelas_temporais": janelas_temporais,
            "sinais_bloqueados_fontes": bloqueados_fontes,
            "motivos_bloqueio_fontes": list(
                estado_fontes.get("motivos") or []
            ),
            "odd_asiatica_api_priorizada": bool(
                odd_asiatica_api_disponivel
            ),
            "odd_asiatica_api_anexada": odd_asiatica_api_anexada,
            "the_odds_api": diagnostico_the_odds_api,
            "betsapi": diagnostico_betsapi,
            "thestatsapi_odds": diagnostico_odds_thestatsapi,
            "cobertura_odds": diagnostico_cobertura_odds,
            "gols_antecipados": diagnostico_gols_antecipados,
            "gols_capacidade_contextual_v2": (
                diagnostico_capacidade_contextual_v2
            ),
            "resgate_qualidade_api": diagnostico_resgate_qualidade_api,
            "snapshot_id": int(snapshot_id),
            "auditoria_bloqueios_promissores": len(auditorias_bloqueios),
            "somente_acompanhamento_preco": bool(
                somente_acompanhamento_preco
            ),
            "duracoes_etapas": resumir_duracoes_etapas(),
        }

    def _selecionar_simulacao_teste(self, pares):
        """Escolhe um envio e preserva os descartes comparáveis da mesma leitura."""
        # Alguns motores persistem ``grupo_teste=true`` na própria evidência,
        # mas a rota pode estar desligada por um rollback/configuração mais
        # recente. Esses casos não podem disputar a vaga do Telegram; ainda
        # assim, precisam deixar o motivo auditável. Sem este registro o sinal
        # aparece como ``simulacao`` no SQLite, sem entrega e sem explicação,
        # parecendo uma falha de envio.
        for sinal_id, candidato in pares:
            features = candidato.get("features") or {}
            exploracao = features.get("exploracao_sombra") or {}
            rota_declarada = exploracao.get("grupo_teste") is True
            if not (
                rota_declarada
                and candidato.get("_status_persistido") == "simulacao"
                and candidato.get("status") == "simulacao"
                and candidato.get("probabilidade_calibrada") is None
                and not candidato_experimento_grupo_teste(candidato)
                and motivo_suspensao_simulacao(candidato) is not None
            ):
                continue
            self.alertas.registrar_filtro_teste(sinal_id, candidato)
        candidatas = [
            (sinal_id, candidato)
            for sinal_id, candidato in pares
            if candidato.get("probabilidade_calibrada") is None
            and (
                (
                    candidato.get("_status_persistido") == "aprovado"
                    and candidato.get("status") == "aprovado"
                )
                or (
                    candidato.get("_status_persistido") == "simulacao"
                    and candidato.get("status") == "simulacao"
                    and candidato_experimento_grupo_teste(candidato)
                )
            )
        ]
        simulaveis = []
        for sinal_id, candidato in candidatas:
            if self._bloquear_exposicao_gol_partida(sinal_id, candidato):
                continue
            if motivo_suspensao_simulacao(candidato) is not None:
                self.alertas.registrar_filtro_teste(
                    sinal_id, candidato
                )
                continue
            simulaveis.append((sinal_id, candidato))
        if not simulaveis:
            return None
        selecionada = max(
            simulaveis,
            key=lambda item: (
                float(item[1].get("pontuacao_tecnica") or 0),
                int(candidato_top_criterio_grupo_teste(item[1])),
            ),
        )
        for sinal_id, candidato in simulaveis:
            if sinal_id == selecionada[0]:
                continue
            motivo_filtro = self.alertas.registrar_filtro_teste(
                sinal_id, candidato
            )
            if motivo_filtro is None:
                self.alertas.registrar_priorizacao_teste(sinal_id)
        return selecionada

    def _selecionar_simulacoes_teste(self, pares):
        """Escolhe uma oportunidade por canal, sem canto disputar com gol.

        Gols e escanteios são publicados em canais diferentes. Fazer os dois
        mercados disputarem uma única vaga descartava um canto válido apenas
        porque havia um gol com nota maior no mesmo snapshot. A seleção dentro
        de cada família continua escolhendo somente a melhor oportunidade.
        """
        familias = {"gols": [], "escanteios": []}
        for par in pares or []:
            candidato = par[1] or {}
            mercado = str(candidato.get("mercado") or "")
            familia = (
                "escanteios"
                if mercado in {
                    "proximo_escanteio",
                    "escanteios_ft_asiatico",
                    "escanteios_1t",
                    "escanteios_2t",
                }
                else "gols"
            )
            familias[familia].append(par)
        selecionadas = []
        for familia in ("gols", "escanteios"):
            if not familias[familia]:
                continue
            selecionada = self._selecionar_simulacao_teste(
                familias[familia]
            )
            if selecionada is not None:
                selecionadas.append(selecionada)
        return selecionadas

    def _bloquear_exposicao_gol_partida(self, sinal_id, candidato):
        if candidato.get("mercado") not in {
            "gol_ht", "gol_ft", "proximo_gol",
        }:
            return False
        verificar = getattr(
            self.banco, "existe_exposicao_gol_aberta_na_partida", None
        )
        if not callable(verificar) or not verificar(sinal_id):
            return False
        self.banco.registrar_entrega_alerta(
            sinal_id,
            "gateway:exposicao_gol",
            "filtrado",
            "exposicao_gol_partida_existente",
        )
        return True

    def _fontes_temporais_aptas(self, agora=None):
        """Revalida a promoção periodicamente e falha fechado em regressão."""
        if not fusao_temporal_grupo_ativa():
            return False
        agora = agora or datetime.now()
        cache = getattr(self, "_cache_prontidao_temporal", None) or {}
        instante_cache = cache.get("em")
        if (
            isinstance(instante_cache, datetime)
            and (agora - instante_cache).total_seconds() < 300
        ):
            return bool(cache.get("apta"))
        resumo = resumir_historico_api_live(
            self.banco.conexao, agora=agora
        )
        pronta = bool(
            ((resumo.get("prontidao_revisao") or {}).get("estado"))
            == "apto_revisao"
        )
        self._cache_prontidao_temporal = {"em": agora, "apta": pronta}
        return pronta

    def _resumo_gate_indicadores_lista_temporais(self, agora=None):
        agora = agora or datetime.now()
        cache = getattr(
            self, "_cache_gate_indicadores_lista_temporais", None
        ) or {}
        instante_cache = cache.get("em")
        if (
            isinstance(instante_cache, datetime)
            and (agora - instante_cache).total_seconds() < 300
        ):
            return cache.get("resumo") or {}
        resumo = resumir_auditoria_temporal_sqlite(self.banco.conexao)
        self._cache_gate_indicadores_lista_temporais = {
            "em": agora,
            "resumo": resumo,
        }
        return resumo

    def _auditar_e_aplicar_indicadores_lista_temporais(
        self, jogo, evolucao, instante
    ):
        auditoria = auditar_janelas_temporais_lista(
            jogo, evolucao, instante=instante
        )
        autorizado = str(os.getenv(
            "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS", "1"
        )).strip().casefold() in {"1", "true", "sim", "yes", "on"}
        revisao = self._resumo_gate_indicadores_lista_temporais(instante)
        fundida, fallback = fundir_janelas_temporais_lista_como_fallback(
            jogo,
            evolucao,
            revisao,
            autorizado=autorizado,
            instante=instante,
        )
        auditoria["fallback_condicional"] = fallback
        auditoria["gate_revisao"] = {
            "versao": revisao.get("versao"),
            "pronto": bool(revisao.get("pronto_para_revisao")),
            "comparacoes": revisao.get("comparacoes_independentes"),
            "partidas": revisao.get("partidas_distintas"),
            "metricas_aprovadas": list(
                revisao.get("metricas_aprovadas") or []
            ),
        }
        auditoria["aplicacao_sinais"] = bool(
            fallback.get("aplicacao_sinais")
        )
        auditoria["promocao_automatica"] = False
        auditoria["ativacao_condicional_pre_autorizada"] = autorizado
        return fundida, auditoria

    @staticmethod
    def _resumo_thestatsapi_sombra_base(
        ativa=False, disponivel=False, aplicacao_sinais=False
    ):
        return {
            "estado": (
                "aguardando_coleta" if ativa and disponivel
                else "sem_chave" if ativa else "desativada"
            ),
            "ativa": bool(ativa),
            "disponivel": bool(disponivel),
            "lista_api": {
                "estado": "nao_consultada",
                "partidas": 0,
                "cache": False,
            },
            "pareamentos": {
                "tentativas": 0,
                "associados": 0,
                "persistidos": 0,
                "cobertura": None,
            },
            "stats": {
                "consultados": 0,
                "persistidos": 0,
                "indisponiveis_cache": 0,
            },
            "odds": {
                "consultados": 0,
                "jogos_com_ofertas": 0,
                "ofertas_persistidas": 0,
            },
            "jogos_consultados": 0,
            "chamadas_rede": 0,
            "chamadas_cache": 0,
            "erros": 0,
            "erros_por_codigo": {},
            "aplicacao_sinais": bool(aplicacao_sinais),
            "telegram": bool(aplicacao_sinais),
            "calibracao": False,
            "substitui_packball": False,
            "sem_autorizacao_sinal": not bool(aplicacao_sinais),
            "modo": (
                "oficial_fail_closed"
                if aplicacao_sinais else "sombra"
            ),
            "desligar_com": (
                "THESTATSAPI_APLICACAO_SINAIS_ATIVA=0"
                if aplicacao_sinais else "THESTATSAPI_SOMBRA_ATIVA=0"
            ),
        }

    @staticmethod
    def _registrar_erro_thestatsapi_sombra(resumo, codigo):
        codigo = str(codigo or "erro_desconhecido")[:80]
        resumo["erros"] = int(resumo.get("erros", 0) or 0) + 1
        erros = resumo.setdefault("erros_por_codigo", {})
        erros[codigo] = int(erros.get(codigo, 0) or 0) + 1

    def _consumo_thestatsapi_dia(self):
        cliente = getattr(self, "thestatsapi", None)
        if cliente is None:
            return 0
        try:
            return int(
                (cliente.consumo_atual() or {}).get(
                    "usado_local_dia", 0
                ) or 0
            )
        except Exception:
            return 0

    def _preparar_thestatsapi_sombra(self, jogos):
        """Consulta a fonte auxiliar; qualquer uso oficial ainda exige o gate."""
        cliente = getattr(self, "thestatsapi", None)
        ativa = bool(getattr(self, "thestatsapi_sombra_ativa", False))
        disponivel = bool(cliente is not None and cliente.disponivel)
        resumo = self._resumo_thestatsapi_sombra_base(
            ativa,
            disponivel,
            bool(getattr(
                self, "thestatsapi_aplicacao_sinais_ativa", False
            )),
        )
        contexto = {
            "resumo": resumo,
            "resposta_lista": None,
            "diagnosticos": [],
            "pares": [],
        }
        if not ativa or not disponivel:
            return contexto

        uso_antes = self._consumo_thestatsapi_dia()
        try:
            resposta = cliente.jogos_ao_vivo(pagina=1, por_pagina=100)
        except Exception as erro:
            resumo["estado"] = "falha_isolada_lista"
            resumo["lista_api"]["estado"] = "erro_cliente"
            self._registrar_erro_thestatsapi_sombra(
                resumo, type(erro).__name__
            )
            resumo["chamadas_rede"] = max(
                self._consumo_thestatsapi_dia() - uso_antes, 0
            )
            return contexto

        contexto["resposta_lista"] = resposta
        if resposta.get("cache"):
            resumo["chamadas_cache"] += 1
        resumo["chamadas_rede"] = max(
            self._consumo_thestatsapi_dia() - uso_antes, 0
        )
        if not resposta.get("ok"):
            erro = resposta.get("erro") or {}
            resumo["estado"] = "falha_isolada_lista"
            resumo["lista_api"]["estado"] = (
                erro.get("codigo") or "resposta_indisponivel"
            )
            self._registrar_erro_thestatsapi_sombra(
                resumo, erro.get("codigo")
            )
            return contexto

        partidas_api = adaptar_lista_thestatsapi_para_associador(resposta)
        resumo["lista_api"] = {
            "estado": "cache" if resposta.get("cache") else "rede",
            "partidas": len(partidas_api),
            "cache": bool(resposta.get("cache")),
        }
        candidatos = []
        for jogo in jogos or []:
            try:
                diagnostico = diagnosticar_associacao_thestatsapi(
                    jogo, resposta
                )
            except Exception as erro:
                diagnostico = {
                    "associacao": None,
                    "motivo": "erro_associacao_isolado",
                    "erro": type(erro).__name__,
                    "fonte": "thestatsapi",
                    "aplicacao_sinais": False,
                }
                self._registrar_erro_thestatsapi_sombra(
                    resumo, "erro_associacao"
                )
            contexto["diagnosticos"].append(diagnostico)
            associacao = diagnostico.get("associacao")
            if isinstance(associacao, dict):
                candidatos.append((jogo, associacao, diagnostico))

        # Pareamento um-para-um. Se dois registros PackBall apontarem para o
        # mesmo match_id, somente o candidato de maior similaridade sobrevive.
        candidatos.sort(
            key=lambda item: (
                float(item[1].get("similaridade") or 0),
                float(item[1].get("margem_associacao") or 0),
            ),
            reverse=True,
        )
        ids_usados = set()
        for jogo, associacao, diagnostico in candidatos:
            match_id = str(associacao.get("match_id") or "").strip()
            if not match_id or match_id in ids_usados:
                continue
            ids_usados.add(match_id)
            times = associacao.get("times") or {}
            diagnostico_compacto = {
                chave: diagnostico.get(chave)
                for chave in (
                    "motivo",
                    "fixtures_validas",
                    "nomes_compativeis",
                    "candidatos_compativeis",
                    "rejeicoes_categoria",
                    "rejeicoes_placar",
                    "rejeicoes_minuto",
                    "margem_associacao",
                    "fonte",
                    "aplicacao_sinais",
                    "calibracao",
                )
            }
            pareamento = {
                "packball_url": jogo.get("url"),
                "match_id": match_id,
                "orientacao": associacao.get("orientacao"),
                "similaridade": associacao.get("similaridade"),
                "margem": associacao.get("margem_associacao"),
                "mandante_api": (
                    (times.get("home") or {}).get("name")
                ),
                "visitante_api": (
                    (times.get("away") or {}).get("name")
                ),
                "atualizado_em": datetime.now()
                .replace(microsecond=0)
                .isoformat(),
                "diagnostico": diagnostico_compacto,
            }
            try:
                self.banco.salvar_pareamento_thestatsapi(pareamento)
            except Exception as erro:
                self._registrar_erro_thestatsapi_sombra(
                    resumo, f"persistencia_pareamento_{type(erro).__name__}"
                )
                continue
            contexto["pares"].append({
                "jogo": jogo,
                "associacao": associacao,
                "diagnostico": diagnostico,
            })

        tentativas = len(jogos or [])
        pareadas = len(contexto["pares"])
        resumo["pareamentos"] = {
            "tentativas": tentativas,
            "associados": pareadas,
            "persistidos": pareadas,
            "cobertura": (
                round(pareadas / tentativas, 4) if tentativas else None
            ),
        }
        resumo["tentativas_pareamento"] = tentativas
        resumo["pareadas"] = pareadas
        resumo["pareamentos_persistidos"] = pareadas
        if pareadas:
            estado = "lista_coletada_sombra"
        elif tentativas == 0 and not partidas_api:
            estado = "sem_jogos_ao_vivo"
        elif tentativas == 0:
            estado = "packball_sem_jogos_ao_vivo"
        elif not partidas_api:
            estado = "thestatsapi_sem_jogos_ao_vivo"
        else:
            estado = "sem_pareamentos"
        resumo["estado"] = estado
        return contexto

    @staticmethod
    def _idade_evidencia_thestatsapi(
        registros, agora, janela_minutos
    ):
        referencia = agora or datetime.now()
        idades = []
        for registro in registros or []:
            bruto = (registro or {}).get("coletado_em")
            try:
                instante = datetime.fromisoformat(str(bruto))
            except (TypeError, ValueError):
                continue
            if instante.tzinfo is not None:
                comparador = (
                    referencia
                    if referencia.tzinfo is not None
                    else referencia.astimezone()
                )
            else:
                comparador = (
                    referencia.replace(tzinfo=None)
                    if referencia.tzinfo is not None else referencia
                )
            idade = (comparador - instante).total_seconds()
            if 0 <= idade <= float(janela_minutos) * 60:
                idades.append(idade)
        return min(idades) if idades else None

    @staticmethod
    def _tarefa_atrasada_para_scout_thestatsapi(tarefa):
        """Replica a reserva critica do agendador sem relaxar atrasos legados."""
        for campo in ("idade_segundos", "atraso_segundos"):
            try:
                valor = float(tarefa.get(campo) or 0)
            except (TypeError, ValueError):
                continue
            if math.isfinite(valor) and valor > LIMITE_ATRASO_CRITICO_SEGUNDOS:
                return True
        return False

    def _priorizar_packball_por_thestatsapi(
        self,
        tarefas,
        *,
        agora=None,
        janela_minutos=JANELA_PRIORIDADE_THE_STATS_API_MINUTOS,
    ):
        """Reserva no maximo uma vaga scout sem ultrapassar tarefas criticas."""
        ordenadas = list(tarefas or [])
        diagnostico = {
            "estado": "desativada",
            "janela_minutos": float(janela_minutos),
            "jogos_avaliados": len(ordenadas),
            "jogos_com_evidencia_recente": 0,
            "fontes_evidencia": {"stats": 0, "odds": 0},
            "scout_disponiveis": 0,
            "scout_reservado": False,
            "scout_nas_quatro_primeiras": False,
            "idade_evidencia_segundos": None,
            "aplicacao_sinais": False,
            "exige_confirmacao_packball": True,
            "sem_autorizacao_sinal": True,
            "desligar_com": "THESTATSAPI_SOMBRA_ATIVA=0",
        }
        cliente = getattr(self, "thestatsapi", None)
        if (
            not bool(getattr(self, "thestatsapi_sombra_ativa", False))
            or cliente is None
            or not bool(getattr(cliente, "disponivel", False))
        ):
            return ordenadas, diagnostico
        diagnosticar_cliente = getattr(cliente, "diagnostico", None)
        if callable(diagnosticar_cliente):
            try:
                saude_cliente = diagnosticar_cliente() or {}
            except Exception:
                diagnostico["estado"] = "cliente_indisponivel"
                return ordenadas, diagnostico
            consumo_cliente = saude_cliente.get("consumo") or {}
            if (
                saude_cliente.get("circuito_aberto")
                or consumo_cliente.get("contador_saudavel") is False
                or int(
                    consumo_cliente.get("restante_local_seguro", 1) or 0
                ) <= 0
            ):
                diagnostico["estado"] = "cliente_sem_capacidade"
                return ordenadas, diagnostico
        diagnostico["estado"] = "sem_evidencia_recente"
        referencia = agora or datetime.now()
        candidatos = []
        for indice, tarefa in enumerate(ordenadas):
            jogo = tarefa.get("jogo") or {}
            url = jogo.get("url")
            if not url or tarefa.get("acionavel_fila_detalhada") is not True:
                continue
            status = str(jogo.get("status") or "").strip().casefold()
            minuto = extrair_minuto(jogo.get("status"))
            if (
                minuto is None
                or minuto > MINUTO_MAXIMO_PRIORIDADE_SINAIS
                or status in {"ht", "intervalo"}
                or "intervalo" in status
                or any(
                    termo in status
                    for termo in (
                        "final", "encerr", "adiad", "cancel", "aband",
                    )
                )
            ):
                continue
            try:
                pareamento = self.banco.obter_pareamento_thestatsapi(
                    packball_url=url
                )
                if not pareamento:
                    continue
                stats = self.banco.carregar_serie_thestatsapi_recente(
                    packball_url=url,
                    minutos=janela_minutos,
                    limite=10,
                    agora=referencia,
                )
                odds = self.banco.carregar_odds_thestatsapi_recentes(
                    packball_url=url,
                    minutos=janela_minutos,
                    limite=10,
                    agora=referencia,
                )
            except Exception:
                # Uma falha local da fonte auxiliar preserva exatamente a
                # ordem anterior e nunca fecha o gate operacional.
                continue
            idade_stats = self._idade_evidencia_thestatsapi(
                stats, referencia, janela_minutos
            )
            idade_odds = self._idade_evidencia_thestatsapi(
                odds, referencia, janela_minutos
            )
            if idade_stats is None and idade_odds is None:
                continue
            diagnostico["jogos_com_evidencia_recente"] += 1
            diagnostico["fontes_evidencia"]["stats"] += int(
                idade_stats is not None
            )
            diagnostico["fontes_evidencia"]["odds"] += int(
                idade_odds is not None
            )
            atrasada = self._tarefa_atrasada_para_scout_thestatsapi(tarefa)
            protegida = bool(
                tarefa.get("em_foco")
                or tarefa.get("rechecagem_pos_evento")
                or tarefa.get("prioridade") == "rapida"
                or atrasada
                or tarefa.get("janelas_temporais_projetadas")
            )
            if protegida:
                continue
            idade = min(
                valor for valor in (idade_stats, idade_odds)
                if valor is not None
            )
            candidatos.append((indice, idade, url, tarefa))

        diagnostico["scout_disponiveis"] = len(candidatos)
        if not candidatos:
            if diagnostico["jogos_com_evidencia_recente"]:
                diagnostico["estado"] = "evidencia_sem_vaga_scout"
            return ordenadas, diagnostico

        contagens = getattr(self, "_thestatsapi_scout_selecoes", {})
        candidatos.sort(
            key=lambda item: (
                int(contagens.get(item[2], 0) or 0),
                item[1],
                item[0],
            )
        )
        indice_original, idade, url, escolhida = candidatos[0]
        indices_protegidos = []
        for indice, tarefa in enumerate(ordenadas):
            atrasada = self._tarefa_atrasada_para_scout_thestatsapi(tarefa)
            if (
                tarefa.get("em_foco")
                or tarefa.get("rechecagem_pos_evento")
                or tarefa.get("prioridade") == "rapida"
                or atrasada
                or tarefa.get("janelas_temporais_projetadas")
            ):
                indices_protegidos.append(indice)
        posicao = max(indices_protegidos) + 1 if indices_protegidos else 0
        ordenadas.remove(escolhida)
        posicao = min(posicao, len(ordenadas))
        ordenadas.insert(posicao, escolhida)
        escolhida["_thestatsapi_scout"] = True
        contagens[url] = int(contagens.get(url, 0) or 0) + 1
        self._thestatsapi_scout_selecoes = contagens
        diagnostico.update({
            "estado": "prioridade_packball_auxiliar",
            "scout_reservado": True,
            "scout_nas_quatro_primeiras": posicao < 4,
            "idade_evidencia_segundos": round(float(idade), 1),
            "posicao_original": indice_original + 1,
            "posicao_final": posicao + 1,
            "ordem_alterada": indice_original != posicao,
        })
        return ordenadas, diagnostico

    def _selecionar_thestatsapi_sombra(self, pares, tarefas, pontuacoes):
        limite = min(
            max(
                int(
                    getattr(self, "thestatsapi_max_jogos_ciclo", 2) or 0
                ),
                0,
            ),
            2,
        )
        if limite == 0:
            return []
        tarefas_por_url = {
            (item.get("jogo") or {}).get("url"): item
            for item in tarefas or []
        }
        pontuacoes = dict(pontuacoes or {})
        ativos = {
            (item.get("jogo") or {}).get("url") for item in pares or []
        }
        contagens = getattr(self, "_thestatsapi_selecoes", {})
        contagens = {
            url: int(quantidade or 0)
            for url, quantidade in contagens.items()
            if url in ativos
        }

        def chave(item):
            jogo = item.get("jogo") or {}
            url = jogo.get("url")
            tarefa = tarefas_por_url.get(url) or {}
            return (
                contagens.get(url, 0),
                not bool(tarefa.get("rechecagem_pos_evento")),
                not bool(tarefa.get("em_foco")),
                -float(pontuacoes.get(url) or 0),
                str(url or ""),
            )

        selecionados = sorted(pares or [], key=chave)[:limite]
        for item in selecionados:
            url = (item.get("jogo") or {}).get("url")
            contagens[url] = contagens.get(url, 0) + 1
        self._thestatsapi_selecoes = contagens
        return selecionados

    @staticmethod
    def _finalizar_diagnostico_scout_thestatsapi(
        diagnostico, coleta
    ):
        diagnostico = dict(diagnostico or {})
        processado = bool(
            (coleta or {}).get("thestatsapi_scout_processado")
        )
        diagnostico["scout_processado"] = processado
        diagnostico["amostra_coleta_influenciada"] = bool(
            processado and diagnostico.get("ordem_alterada")
        )
        diagnostico["sem_autorizacao_sinal"] = True
        return diagnostico

    def _coletar_detalhes_thestatsapi_sombra(
        self, contexto, tarefas, pontuacoes
    ):
        resumo = contexto["resumo"]
        if not resumo.get("ativa") or not resumo.get("disponivel"):
            return resumo
        if contexto.get("resposta_lista") is None:
            return resumo
        consumo = self.thestatsapi.consumo_atual()
        pares_contexto = list(contexto.get("pares") or [])
        urls_lote = {
            (item.get("jogo") or {}).get("url")
            for item in tarefas or []
            if (item.get("jogo") or {}).get("url")
        }
        # Quando o chamador fornece um lote, detalhes auxiliares ficam
        # estritamente dentro dele. A lista completa ainda é pareada para
        # diagnóstico de cobertura, sem consumir chamadas por cada partida.
        pares_planejaveis = (
            [
                par for par in pares_contexto
                if (par.get("jogo") or {}).get("url") in urls_lote
            ]
            if urls_lote else pares_contexto
        )
        planos, planejamento = planejar_coleta_thestatsapi(
            pares_planejaveis,
            tarefas,
            pontuacoes,
            consumo,
            contagens_stats=getattr(
                self, "_thestatsapi_selecoes_stats", {}
            ),
            contagens_odds=getattr(
                self, "_thestatsapi_selecoes_odds", {}
            ),
            maximo_jogos=getattr(
                self, "thestatsapi_max_jogos_ciclo", 6
            ),
        )
        resumo["planejamento"] = planejamento
        resumo["pares_elegiveis_no_lote"] = len(pares_planejaveis)
        resumo["jogos_consultados"] = len(planos)
        resumo["detalhes_selecionados"] = len(planos)
        if not planos:
            return resumo

        ativos = {
            (par.get("jogo") or {}).get("url")
            for par in pares_planejaveis
        }
        cont_stats = {
            url: int(valor or 0) for url, valor in getattr(
                self, "_thestatsapi_selecoes_stats", {}
            ).items() if url in ativos
        }
        cont_odds = {
            url: int(valor or 0) for url, valor in getattr(
                self, "_thestatsapi_selecoes_odds", {}
            ).items() if url in ativos
        }

        uso_antes = self._consumo_thestatsapi_dia()
        respostas = []
        # Sequencial por seguranca: evita que uma resposta 200 concorrente
        # apague um bloqueio 429 recem-observado pelo mesmo cliente. Como esta
        # etapa antecede o PackBall, o lote curto limita a latencia total.
        for plano in planos:
            par = plano.par
            url = (par.get("jogo") or {}).get("url")
            match_id = (par.get("associacao") or {}).get("match_id")
            consultas = [("stats", self.thestatsapi.estatisticas_ao_vivo)]
            if plano.consultar_odds:
                consultas.append(("odds", self.thestatsapi.odds_ao_vivo))
            for tipo, metodo in consultas:
                try:
                    resposta = metodo(match_id)
                except Exception as erro:
                    resposta = {
                        "ok": False,
                        "erro": {"codigo": type(erro).__name__},
                        "cache": False,
                    }
                respostas.append((tipo, par, resposta))
                if tipo == "stats":
                    cont_stats[url] = cont_stats.get(url, 0) + 1
                else:
                    cont_odds[url] = cont_odds.get(url, 0) + 1

        self._thestatsapi_selecoes_stats = cont_stats
        self._thestatsapi_selecoes_odds = cont_odds

        resumo["chamadas_rede"] += max(
            self._consumo_thestatsapi_dia() - uso_antes, 0
        )
        snapshots = []
        envelopes_odds = []
        for tipo, par, resposta in respostas:
            if resposta.get("cache"):
                resumo["chamadas_cache"] += 1
            jogo = par.get("jogo") or {}
            associacao = par.get("associacao") or {}
            evidencia = self._thestatsapi_fusao_ciclo.setdefault(
                jogo.get("url"), {
                    "diagnostico": par.get("diagnostico") or {},
                }
            )
            if tipo == "stats":
                resumo["stats"]["consultados"] += 1
                evidencia["resposta_stats"] = resposta
            else:
                resumo["odds"]["consultados"] += 1
                evidencia["resposta_odds"] = resposta
            if not resposta.get("ok"):
                erro = resposta.get("erro") or {}
                if (
                    tipo == "stats"
                    and resposta.get("cache") is True
                    and erro.get("codigo") == "http_404"
                ):
                    resumo["stats"]["indisponiveis_cache"] += 1
                    continue
                self._registrar_erro_thestatsapi_sombra(
                    resumo,
                    f"{tipo}_{erro.get('codigo') or 'indisponivel'}",
                )
                continue

            if tipo == "stats":
                snapshot = normalizar_live_stats_thestatsapi(
                    resposta,
                    packball_url=jogo.get("url"),
                    orientacao=associacao.get("orientacao") or "direta",
                )
                if snapshot is None:
                    self._registrar_erro_thestatsapi_sombra(
                        resumo, "stats_nao_normalizaveis"
                    )
                    continue
                try:
                    persistencia = (
                        self.banco.salvar_historico_thestatsapi_live(
                            [snapshot]
                        )
                    )
                except Exception as erro:
                    self._registrar_erro_thestatsapi_sombra(
                        resumo,
                        f"persistencia_stats_{type(erro).__name__}",
                    )
                    continue
                snapshots.append(snapshot)
                evidencia.update(snapshot)
                resumo["stats"]["persistidos"] += int(
                    persistencia.get("recebidos", 0) or 0
                )
                continue

            envelope = normalizar_odds_live_thestatsapi(resposta)
            envelope["packball_url"] = jogo.get("url")
            ofertas = envelope.get("ofertas") or []
            if not ofertas:
                continue
            try:
                persistencia = self.banco.salvar_odds_thestatsapi_live(
                    [envelope]
                )
            except Exception as erro:
                self._registrar_erro_thestatsapi_sombra(
                    resumo,
                    f"persistencia_odds_{type(erro).__name__}",
                )
                continue
            envelopes_odds.append(envelope)
            resumo["odds"]["jogos_com_ofertas"] += 1
            resumo["odds"]["ofertas_persistidas"] += int(
                persistencia.get("recebidos", 0) or 0
            )

        resumo["stats_consultados"] = resumo["stats"]["consultados"]
        resumo["stats_persistidos"] = resumo["stats"]["persistidos"]
        resumo["odds_consultadas"] = resumo["odds"]["consultados"]
        resumo["partidas_com_odds"] = resumo["odds"][
            "jogos_com_ofertas"
        ]
        resumo["ofertas_odds_persistidas"] = resumo["odds"][
            "ofertas_persistidas"
        ]
        resumo["cobertura"] = resumir_cobertura_thestatsapi(
            partidas=contexto.get("resposta_lista"),
            diagnosticos=contexto.get("diagnosticos"),
            snapshots=snapshots,
            odds=envelopes_odds,
        )
        oficial = bool(resumo.get("aplicacao_sinais"))
        resumo["estado"] = (
            "coleta_oficial_parcial"
            if oficial and resumo.get("erros")
            else "coleta_oficial"
            if oficial
            else "coleta_sombra_parcial"
            if resumo.get("erros")
            else "coleta_sombra"
        )
        return resumo

    def _executar_thestatsapi_sombra(self, jogos, tarefas, pontuacoes):
        """Executa a fonte isolada; falhas locais nunca liberam uso oficial."""
        inicio = time.monotonic()
        self._thestatsapi_fusao_ciclo = {}
        contexto = None
        try:
            contexto = self._preparar_thestatsapi_sombra(jogos)
            resumo = self._coletar_detalhes_thestatsapi_sombra(
                contexto, tarefas, pontuacoes
            )
            resumo["duracao_segundos"] = round(
                max(time.monotonic() - inicio, 0), 3
            )
            return resumo
        except Exception as erro:
            if contexto is not None:
                resumo = contexto.get("resumo") or {}
            else:
                cliente = getattr(self, "thestatsapi", None)
                resumo = self._resumo_thestatsapi_sombra_base(
                    bool(getattr(self, "thestatsapi_sombra_ativa", False)),
                    bool(cliente is not None and cliente.disponivel),
                    bool(getattr(
                        self, "thestatsapi_aplicacao_sinais_ativa", False
                    )),
                )
            resumo["estado"] = "falha_isolada"
            self._registrar_erro_thestatsapi_sombra(
                resumo, type(erro).__name__
            )
            resumo["aplicacao_sinais"] = False
            resumo["telegram"] = False
            resumo["calibracao"] = False
            resumo["substitui_packball"] = False
            resumo["duracao_segundos"] = round(
                max(time.monotonic() - inicio, 0), 3
            )
            return resumo

    def _analisar_consenso_multifonte_sombra(
        self, tarefas, fixtures_api, *, agora=None
    ):
        """Analisa jogos sem detalhe PB usando duas APIs, sem enviar sinais."""
        resumo = {
            "versao": VERSAO_CONSENSO_MULTIFONTE_SOMBRA,
            "ativa": os.getenv(
                "CONSENSO_MULTIFONTE_SOMBRA_ATIVO", "0"
            ) == "1",
            "avaliadas": 0,
            "consensos": 0,
            "snapshots": 0,
            "simulacoes": 0,
            "rejeicoes": {},
            "aplicacao_sinais": False,
            "telegram": False,
            "calibracao": False,
            "promocao_automatica": False,
            "rollback": "CONSENSO_MULTIFONTE_SOMBRA_ATIVO=0",
        }
        if not resumo["ativa"]:
            resumo["estado"] = "desativada"
            return resumo
        agora = agora or datetime.now().astimezone()
        por_fixture = {
            (item.get("fixture") or {}).get("id"): item
            for item in fixtures_api or []
            if isinstance(item, dict)
        }
        evidencias_ts = getattr(self, "_thestatsapi_fusao_ciclo", {})

        def rejeitar(motivo):
            chave = str(motivo or "indeterminado")
            resumo["rejeicoes"][chave] = (
                int(resumo["rejeicoes"].get(chave, 0)) + 1
            )

        for tarefa in tarefas or []:
            jogo = (tarefa or {}).get("jogo") or {}
            fixture_id = tarefa.get("api_fixture_id_prioridade")
            fixture = por_fixture.get(fixture_id)
            evidencia_ts = evidencias_ts.get(jogo.get("url")) or {}
            if fixture is None or not evidencia_ts:
                continue
            resumo["avaliadas"] += 1
            resposta_stats = evidencia_ts.get("resposta_stats")
            resposta_odds = evidencia_ts.get("resposta_odds")
            if not resposta_stats or not resposta_odds:
                rejeitar("thestats_detalhes_incompletos")
                continue
            gate_odds = validar_gate_operacional_thestatsapi(
                jogo,
                evidencia_ts.get("diagnostico"),
                resposta_stats,
                resposta_odds,
                agora=agora,
            )
            if gate_odds.get("apto_sombra") is not True:
                rejeitar(gate_odds.get("motivo"))
                continue
            snapshot_api = normalizar_snapshot_api_live(
                fixture,
                jogo.get("url"),
                orientacao=tarefa.get(
                    "api_orientacao_prioridade", "direta"
                ),
                coletado_em=agora,
            )
            diagnostico = validar_consenso_multifonte(
                jogo, fixture, snapshot_api, evidencia_ts, agora=agora
            )
            if not diagnostico.get("valido"):
                rejeitar(diagnostico.get("motivo"))
                continue
            evolucao = obter_evolucao_api_live(
                self.banco.conexao,
                fixture_id,
                jogo.get("url"),
                agora=agora.replace(tzinfo=None),
            )
            if not isinstance(evolucao.get("5"), dict):
                rejeitar("historico_api_5min_insuficiente")
                continue
            odds = converter_odds_bet365_contrato_interno(
                resposta_odds, agora=agora
            )
            if not (odds.get("ao_vivo") or []):
                rejeitar("odds_bet365_gols_ausentes")
                continue
            estatisticas = estatisticas_do_consenso(
                snapshot_api, evidencia_ts
            )
            qualidade = {
                "pontuacao": 90.0,
                "completude": 1.0,
                "campos_ausentes": [
                    "Índice de pressão", "Ataques perigosos"
                ],
                "fontes": ["api_football", "thestatsapi"],
                "alertas": ["sem_detalhe_packball_modo_sombra"],
                "divergencia_critica": False,
                "apto_para_sinal": True,
                "apto_para_liquidacao": True,
                "versao": "qualidade-consenso-multifonte-sombra-v1",
            }
            candidatos = self._gerar_candidatos_rastreaveis(
                jogo, estatisticas, evolucao, odds, qualidade
            )
            candidatos = filtrar_mercados_operacionais(candidatos)
            aplicar_politicas_por_mercado(candidatos)
            for candidato in candidatos:
                aplicar_politica_gol_ht(candidato)
                aplicar_politica_gols_tempo(candidato)
            candidatos = isolar_candidatos_consenso(
                candidatos, diagnostico
            )
            if not candidatos:
                rejeitar("nenhum_gol_aprovado_pela_regra_atual")
                continue
            registro = {
                "coletado_em": agora.replace(tzinfo=None),
                **jogo,
                "estatisticas": estatisticas,
                "odds": odds,
                "evolucao": evolucao,
                "confirmacao_api": {
                    "fixture_id": fixture_id,
                    "orientacao": tarefa.get(
                        "api_orientacao_prioridade", "direta"
                    ),
                },
                "estatisticas_api": fixture.get("statistics") or [],
                "contexto_api": {
                    "consenso_multifonte_sombra": diagnostico,
                    "sem_detalhe_packball": True,
                },
                "qualidade": qualidade,
                "falhas_fontes": [],
            }
            snapshot_id = self.salvar_registro(registro)
            if not snapshot_id:
                rejeitar("snapshot_nao_persistido")
                continue
            self.backtest.avaliar_snapshot(snapshot_id)
            novos = []
            for candidato in candidatos:
                if self.banco.exploracao_sombra_ja_registrada(
                    snapshot_id,
                    candidato["mercado"],
                    candidato["regra_versao"],
                    VERSAO_CONSENSO_MULTIFONTE_SOMBRA,
                ):
                    continue
                candidato["regra_fingerprint"] = self.regra_fingerprints[
                    candidato["regra_versao"]
                ]
                novos.append(candidato)
            if not novos:
                rejeitar("exploracao_ja_registrada")
                continue
            self.banco.salvar_candidatos(snapshot_id, novos, agora)
            resumo["consensos"] += 1
            resumo["snapshots"] += 1
            resumo["simulacoes"] += len(novos)
        resumo["estado"] = "analisando_sombra"
        return resumo

    def _atualizar_taxas_ligas_gols(self, pagina_detalhe, jogos):
        ativa = str(os.getenv(
            "PRIORIZACAO_LIGAS_GOLS_ATIVA", "1"
        )).strip().casefold() in {"1", "true", "sim", "yes", "on"}
        try:
            limiar = max(int(os.getenv(
                "PRIORIZACAO_LIGAS_GOLS_LIMIAR_CARGA", "15"
            )), 1)
        except (TypeError, ValueError):
            limiar = 15
        try:
            atualizacao_horas = max(float(os.getenv(
                "PRIORIZACAO_LIGAS_GOLS_ATUALIZACAO_HORAS", "6"
            )), 1.0)
        except (TypeError, ValueError):
            atualizacao_horas = 6.0
        diagnostico = {
            "ativa": ativa,
            "estado": "desativada" if not ativa else "aguardando",
            "jogos_ao_vivo": len(jogos or []),
            "limiar_carga": limiar,
            "atualizacao_horas": atualizacao_horas,
            "coleta_executada": False,
            "rollback": "PRIORIZACAO_LIGAS_GOLS_ATIVA=0",
            "altera_aprovacao_sinal": False,
        }
        if not ativa:
            self._taxas_ligas_gols_cache = []
            return diagnostico

        estado = self.banco.ultima_coleta_taxas_ligas_gols()
        coletado_em = estado.get("coletado_em")
        idade_horas = None
        if coletado_em:
            try:
                idade_horas = max(
                    (datetime.now() - datetime.fromisoformat(
                        coletado_em
                    )).total_seconds() / 3600.0,
                    0.0,
                )
            except (TypeError, ValueError):
                idade_horas = None
        diagnostico["ultima_coleta"] = coletado_em
        diagnostico["idade_horas"] = (
            round(idade_horas, 3) if idade_horas is not None else None
        )
        fresca = bool(
            estado.get("registros")
            and idade_horas is not None
            and idade_horas < atualizacao_horas
        )
        carga_alta = len(jogos or []) >= limiar
        if carga_alta and not fresca:
            try:
                coleta = coletar_taxas_ligas_packball(
                    pagina_detalhe,
                    controle_acesso=self.controle_packball,
                )
                persistencia = self.banco.salvar_taxas_ligas_gols(
                    coleta.get("registros")
                )
                diagnostico.update({
                    "estado": "atualizada",
                    "coleta_executada": True,
                    "por_periodo": coleta.get("por_periodo"),
                    "persistencia": persistencia,
                    "ultima_coleta": coleta.get("coletado_em"),
                    "idade_horas": 0.0,
                })
                print(
                    "Taxas sazonais PackBall atualizadas: "
                    f"1T={coleta['por_periodo'].get('1t', 0)} | "
                    f"2T={coleta['por_periodo'].get('2t', 0)}."
                )
            except Exception as erro:
                diagnostico.update({
                    "estado": "falha_isolada",
                    "erro": type(erro).__name__,
                    "detalhe": str(erro)[:180],
                })
                print(
                    "Aviso: taxas sazonais de ligas indisponiveis nesta "
                    f"atualizacao ({type(erro).__name__})."
                )
        elif fresca:
            diagnostico["estado"] = "cache_fresco"
        else:
            diagnostico["estado"] = "abaixo_limiar_sem_navegacao"

        self._taxas_ligas_gols_cache = (
            self.banco.carregar_taxas_ligas_gols()
        )
        diagnostico["registros_disponiveis"] = len(
            self._taxas_ligas_gols_cache
        )
        return diagnostico

    def _aplicar_prioridade_ligas_gols(self, tarefas):
        try:
            limiar = max(int(os.getenv(
                "PRIORIZACAO_LIGAS_GOLS_LIMIAR_CARGA", "15"
            )), 1)
        except (TypeError, ValueError):
            limiar = 15
        try:
            amostra = max(int(os.getenv(
                "PRIORIZACAO_LIGAS_GOLS_AMOSTRA_MINIMA", "20"
            )), 1)
        except (TypeError, ValueError):
            amostra = 20
        ativa = str(os.getenv(
            "PRIORIZACAO_LIGAS_GOLS_ATIVA", "1"
        )).strip().casefold() in {"1", "true", "sim", "yes", "on"}
        registros = (
            getattr(self, "_taxas_ligas_gols_cache", []) if ativa else []
        )
        limite_efetivo = limiar if ativa else len(tarefas or []) + 1
        return priorizar_tarefas_por_ligas(
            tarefas,
            registros,
            limiar_carga=limite_efetivo,
            amostra_minima=amostra,
        )

    def executar_ciclo(self, pagina_lista, pagina_detalhe):
        self._inicio_ciclo_monotonic = time.monotonic()
        # Somente o inicio de um ciclo novo pode liberar a trava. Se uma
        # fonte cair durante este ciclo, a liberacao fica para a proxima
        # varredura completa e passa novamente por todos os gates.
        self._operacao_bloqueada_ciclo = False
        # Cada oportunidade confirmada sai no próprio processamento do jogo.
        # O gateway ainda revalida snapshot, placar, minuto e idade da odd
        # imediatamente antes do transporte. Não esperamos o restante do lote.
        self._adiar_alertas_ciclo = False
        self._alertas_pendentes_ciclo = []
        horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        iniciar_saude_api = getattr(self.api, "iniciar_ciclo_saude", None)
        if callable(iniciar_saude_api):
            iniciar_saude_api()
        self._rechecar_acompanhamentos_odd_api()
        self._avaliar_acompanhamento_odd_prospectivo()
        self.observabilidade.ciclo_progresso("buscando_lista_ao_vivo")
        jogos = self.packball.buscar_jogos_ao_vivo(pagina_lista)
        lista_observada_em = datetime.now().replace(microsecond=0).isoformat()
        for jogo in jogos:
            jogo["lista_observada_em"] = lista_observada_em
            jogo.setdefault("estado_observado_em", lista_observada_em)
        self.observabilidade.ciclo_progresso(
            "lista_ao_vivo_carregada", partidas=len(jogos)
        )
        self._interromper_se_manutencao("apos_lista_ao_vivo")
        fixtures_api = self._fixtures_api_para(jogos)
        print(f"[{horario}] Jogos ao vivo encontrados: {len(jogos)}")
        diagnostico_lista = getattr(
            self.packball, "ultimo_diagnostico_lista", {}
        ) or {}
        diagnostico_scanner = diagnostico_lista.get("scanner") or {}
        if diagnostico_scanner.get("habilitado") is True:
            self.observabilidade.ciclo_progresso(
                "scanner_packball_verificado",
                estado=diagnostico_scanner.get("estado"),
                contador_filtrado=diagnostico_scanner.get(
                    "contador_filtrado"
                ),
                jogos_extraidos=diagnostico_scanner.get(
                    "jogos_extraidos"
                ),
                painel_visivel=diagnostico_scanner.get("painel_visivel"),
                tentativas_abertura=diagnostico_scanner.get(
                    "tentativas_abertura"
                ),
                tentativas_extracao=diagnostico_scanner.get(
                    "tentativas_extracao"
                ),
            )
            print(
                "Scanner PackBall: estado="
                f"{diagnostico_scanner.get('estado')} | filtradas="
                f"{diagnostico_scanner.get('contador_filtrado')} | lidas="
                f"{diagnostico_scanner.get('jogos_extraidos')}"
            )
        contador_ao_vivo = diagnostico_lista.get("contador_ao_vivo")
        lista_packball_inconsistente = (
            self._aplicar_integridade_lista_packball(diagnostico_lista)
        )
        if contador_ao_vivo is not None:
            print(
                "Conferencia da lista: contador PackBall="
                f"{contador_ao_vivo} | extraidos={len(jogos)}"
            )
            if diagnostico_lista.get("entraram") is not None:
                print(
                    "Mudanca desde o ciclo anterior: entraram="
                    f"{diagnostico_lista['entraram']} | sairam="
                    f"{diagnostico_lista['sairam']}"
                )
            if contador_ao_vivo != len(jogos):
                if diagnostico_lista.get("transicao_dinamica"):
                    print(
                        "Transicao dinamica confirmada: diferenca de uma "
                        "partida, com estados ao vivo explicitos apos a "
                        "segunda leitura."
                    )
                else:
                    print(
                        "Aviso: a quantidade extraida difere do contador "
                        "visivel; sinais e resultados ficam bloqueados neste "
                        "ciclo."
                    )
        if not jogos:
            print("Nenhum jogo ao vivo no momento.")

        # A liquidação usa a mesma cota segura de navegação das coletas.
        # Executá-la primeiro impede que partidas antigas fiquem sem uma
        # tentativa no PackBall quando há muitos jogos simultâneos.
        self.observabilidade.ciclo_progresso(
            "conferindo_resultados_packball"
        )
        gate_finalizacao_packball = (
            self._validar_operacao_para_alerta_oficial()
        )
        operacao_bloqueada_ciclo = self._atualizar_bloqueio_operacao_ciclo(
            gate=gate_finalizacao_packball
        )
        self._operacao_bloqueada_ciclo = operacao_bloqueada_ciclo
        resolvidos_historico = 0
        if gate_finalizacao_packball.get("apto") is True:
            resolvidos_historico = (
                self.backtest.reavaliar_snapshots_conclusivos_pendentes()
            )
        if gate_finalizacao_packball.get("apto") is not True:
            finalizacao_packball = {
                "consultadas": 0, "encerradas": 0, "resolvidos": 0,
                "erros": 0, "snapshots_recuperados": 0,
                "regulamentares_recuperadas": 0,
                "bloqueado_operacao": gate_finalizacao_packball.get(
                    "estado", "degradado"
                ),
                "motivo_bloqueio": gate_finalizacao_packball.get("motivo"),
                "fonte_bloqueio": gate_finalizacao_packball.get("fonte"),
            }
        else:
            try:
                finalizacao_packball = self.finalizador_packball.executar(
                    pagina_detalhe,
                    {jogo["url"] for jogo in jogos},
                    interromper_fn=self._modo_manutencao_ativo,
                    limite_navegacoes=(
                        LIMITE_FINALIZACOES_PACKBALL_ALTA_CARGA
                        if len(jogos) >= LIMIAR_ALTA_CARGA_AO_VIVO
                        else None
                    ),
                )
            except PackBallPausaPreventivaError as erro:
                operacao_bloqueada_ciclo = True
                finalizacao_packball = {
                    "consultadas": 0, "encerradas": 0, "resolvidos": 0,
                    "erros": 0, "snapshots_recuperados": 0,
                    "regulamentares_recuperadas": 0,
                    "pausa_preventiva": str(erro),
                }
        finalizacao_packball["resolvidos_historico"] = (
            resolvidos_historico
        )
        finalizacao_packball["resolvidos"] = int(
            finalizacao_packball.get("resolvidos", 0) or 0
        ) + resolvidos_historico
        operacao_bloqueada_ciclo = self._atualizar_bloqueio_operacao_ciclo(
            operacao_bloqueada_ciclo,
            finalizacao_packball=finalizacao_packball,
        )
        self._operacao_bloqueada_ciclo = operacao_bloqueada_ciclo
        if finalizacao_packball.get("interrompido_manutencao"):
            raise ManutencaoSolicitadaError("resultados_packball")
        self._interromper_se_manutencao("apos_resultados_packball")

        taxas_ligas_gols = self._atualizar_taxas_ligas_gols(
            pagina_detalhe, jogos
        )

        prioridade_pre_live = aplicar_prioridade_pre_live(
            jogos,
            fixtures_api,
            self.pasta / "pre_live.db",
            ativa=(
                os.getenv("PRELIVE_PRIORIDADE_AO_VIVO_ATIVA", "1") == "1"
            ),
        )
        if prioridade_pre_live.get("jogos_associados"):
            print(
                "Prioridade pré-live no ao vivo: "
                f"{prioridade_pre_live['jogos_associados']} jogo(s), "
                f"{prioridade_pre_live['confirmados_associados']} "
                "confirmado(s)."
            )
        if prioridade_pre_live.get("jogos_contexto_associados"):
            print(
                "Ponte pré-live/API disponível: "
                f"{prioridade_pre_live['jogos_contexto_associados']} "
                "jogo(s) com identidade causal para revalidação."
            )

        restauracao_agendamento = self._restaurar_agendamento_persistido(
            jogos
        )
        if restauracao_agendamento["coletas_restauradas"]:
            print(
                "Agendamento restaurado do SQLite: coletas="
                f"{restauracao_agendamento['coletas_restauradas']} | odds="
                f"{restauracao_agendamento['odds_restauradas']}"
        )
        prioridades_recentes = self._estado_prioridades_recentes(jogos)
        pontuacoes = prioridades_recentes["pontuacoes"]
        jogos_por_url = {jogo["url"]: jogo for jogo in jogos}
        rechecagens_pos_evento = {
            url
            for url in prioridades_recentes["rechecagens_pos_evento"]
            if url in jogos_por_url
            and str(jogos_por_url[url].get("status") or "").strip().lower()
            not in {"ht", "intervalo"}
            and (extrair_minuto(jogos_por_url[url].get("status")) or 0) <= 75
        }
        rechecagens_odd_gol = {
            url
            for url in prioridades_recentes.get("rechecagens_odd_gol", set())
            if url in jogos_por_url
            and str(jogos_por_url[url].get("status") or "").strip().lower()
            not in {"ht", "intervalo"}
            and (extrair_minuto(jogos_por_url[url].get("status")) or 0) <= 82
        }
        rechecagens_rapidas = rechecagens_pos_evento | rechecagens_odd_gol
        acompanhamentos_preco = (
            {
                url: dados
                for url, dados in prioridades_recentes.get(
                    "acompanhamentos_preco", {}
                ).items()
                if url in jogos_por_url
                and str(
                    jogos_por_url[url].get("status") or ""
                ).strip().lower() not in {"ht", "intervalo"}
                and (
                    extrair_minuto(jogos_por_url[url].get("status")) or 0
                ) <= 90
            }
            if os.getenv(
                "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO", "1"
            ) == "1"
            else {}
        )
        tarefas = self.agendador.planejar(
            jogos,
            pontuacoes,
            rechecagens_pos_evento=rechecagens_rapidas,
            acompanhamentos_preco=acompanhamentos_preco,
        )
        alvos_exploracao_gols = prioridades_recentes.get(
            "candidatos_exploracao_gols", set()
        )
        for tarefa in tarefas:
            tarefa["prioridade_exploracao_gols"] = bool(
                tarefa["jogo"]["url"] in alvos_exploracao_gols
            )
        tarefas, priorizacao_ligas_gols = (
            self._aplicar_prioridade_ligas_gols(tarefas)
        )
        taxas_ligas_gols["priorizacao"] = priorizacao_ligas_gols
        print(f"Coletas detalhadas agendadas: {len(tarefas)}/{len(jogos)}")
        fixtures_api, enriquecimento_api_lote = (
            self._enriquecer_fixtures_api_lote(tarefas, fixtures_api)
        )
        enriquecimento_api_lote["historico_temporal_sombra"] = (
            self._persistir_historico_api_live_lote(
                tarefas, fixtures_api
            )
        )
        self._interromper_se_manutencao("apos_enriquecimento_api")
        tarefas, priorizacao_api = self._priorizar_tarefas_por_api(
            tarefas, fixtures_api
        )
        priorizacao_api["ligas_gols"] = taxas_ligas_gols
        enriquecimento_api_lote["priorizacao"] = priorizacao_api
        tarefas, triagem_capacidade = self._aplicar_triagem_capacidade(
            tarefas
        )
        enriquecimento_api_lote["triagem_capacidade"] = triagem_capacidade
        tarefas, prioridade_thestatsapi = (
            self._priorizar_packball_por_thestatsapi(tarefas)
        )
        tarefas, filas_operacionais = self._separar_filas_operacionais(
            tarefas
        )
        enriquecimento_api_lote["priorizacao"][
            "filas_operacionais"
        ] = filas_operacionais
        detalhamento_adaptativo = (
            self._configurar_detalhamento_packball(tarefas)
        )
        limite_pb = int(
            detalhamento_adaptativo.get("maximo_detalhes", 0) or 0
        )
        try:
            reserva_auditoria_thestats = max(int(os.getenv(
                "THESTATSAPI_RESERVA_AUDITORIA_FORA_LOTE", "2"
            )), 0)
        except (TypeError, ValueError):
            reserva_auditoria_thestats = 2
        limite_thestats = min(
            len(tarefas), limite_pb + reserva_auditoria_thestats
        )
        # O complemento fresco continua chegando antes da leitura PackBall,
        # mas agora acompanha o lote realmente navegável e uma pequena amostra
        # de auditoria. Evitamos atrasar todas as urgências com dezenas de
        # consultas que não poderiam ser abertas neste ciclo.
        coleta_thestatsapi = self._executar_thestatsapi_sombra(
            jogos, tarefas[:limite_thestats], pontuacoes
        )
        coleta_thestatsapi["limite_alinhado_ao_lote"] = limite_thestats
        coleta_thestatsapi["tarefas_totais_antes_limite"] = len(tarefas)
        coleta_thestatsapi["reserva_auditoria_fora_lote"] = (
            reserva_auditoria_thestats
        )
        fixtures_restantes = list(fixtures_api)
        # Mede, em uma coorte totalmente separada, oportunidades que ficariam
        # fora do orçamento de detalhes PackBall. Mesmo um consenso válido
        # entre as duas APIs gera apenas `simulacao` e nunca Telegram.
        try:
            consenso_multifonte = self._analisar_consenso_multifonte_sombra(
                tarefas[limite_pb:], fixtures_api
            )
        except Exception as erro:
            consenso_multifonte = {
                "versao": VERSAO_CONSENSO_MULTIFONTE_SOMBRA,
                "estado": "falha_isolada",
                "erro": type(erro).__name__,
                "aplicacao_sinais": False,
                "telegram": False,
                "calibracao": False,
                "promocao_automatica": False,
            }
        coleta = self._processar_tarefas_detalhadas(
            pagina_detalhe,
            tarefas,
            fixtures_restantes,
            orcamento_segundos=detalhamento_adaptativo[
                "orcamento_efetivo_segundos"
            ],
            maximo_tarefas=detalhamento_adaptativo["maximo_detalhes"],
        )
        coleta["avaliacao_prioridade_ligas_gols"] = (
            self._avaliar_prioridade_ligas_gols_prospectiva()
        )
        coleta["avaliacao_desajuste_odds"] = (
            self._avaliar_desajuste_odds_prospectivo()
        )
        coleta["avaliacao_probabilidade_individual"] = (
            self._avaliar_probabilidade_individual_prospectiva()
        )
        coleta["avaliacao_quarentena_fallback_ht"] = (
            self._avaliar_quarentena_fallback_ht_prospectiva()
        )
        coleta["detalhamento_adaptativo"] = detalhamento_adaptativo
        coleta["consenso_multifonte_sombra"] = consenso_multifonte
        self._interromper_se_manutencao("apos_coleta_detalhada")
        # A fonte auxiliar permanece isolada: falha externa não invalida a
        # leitura PackBall e o diagnóstico registra exatamente o lote coberto.
        coleta["thestatsapi_sombra"] = coleta_thestatsapi
        prioridade_thestatsapi = (
            self._finalizar_diagnostico_scout_thestatsapi(
                prioridade_thestatsapi, coleta
            )
        )
        coleta["thestatsapi_sombra"][
            "prioridade_packball_auxiliar"
        ] = prioridade_thestatsapi
        coleta["enriquecimento_api_lote"] = enriquecimento_api_lote
        coleta["prioridade_pre_live_ao_vivo"] = prioridade_pre_live
        if lista_packball_inconsistente:
            motivos_lista = coleta.setdefault(
                "motivos_bloqueio_fontes", {}
            )
            motivos_lista["lista_packball_inconsistente"] = max(
                1,
                int(motivos_lista.get(
                    "lista_packball_inconsistente", 0
                ) or 0),
            )
        if (
            coleta.get("pausa_preventiva")
            or coleta.get("motivos_bloqueio_fontes")
        ):
            operacao_bloqueada_ciclo = True
            self._operacao_bloqueada_ciclo = True
        self.observabilidade.ciclo_progresso(
            "coleta_detalhada_concluida",
            processadas=coleta["processadas"],
            agendadas=coleta["agendadas"],
        )
        coleta["lista_packball"] = diagnostico_lista
        if coleta["adiadas"]:
            print(
                "Orçamento do ciclo atingido: "
                f"{coleta['adiadas']} coleta(s) adiada(s) para a próxima fila."
            )

        greens_antecipados = (
            {
                "consultados": 0,
                "confirmados": 0,
                "entregues": 0,
                "erros": 0,
                "bloqueados": 1,
                "motivo_bloqueio": "operacao_degradada_no_ciclo",
            }
            if operacao_bloqueada_ciclo
            else self.alertas.enviar_greens_antecipados()
        )
        coleta["greens_antecipados_telegram"] = greens_antecipados
        if greens_antecipados["entregues"]:
            print(
                "Telegram: "
                f"{greens_antecipados['entregues']} entrada(s) editada(s) "
                "como GREEN antes do encerramento."
            )

        self.observabilidade.ciclo_progresso("conferindo_resultados_api")
        gate_finalizacao = self._validar_operacao_para_alerta_oficial()
        operacao_bloqueada_ciclo = self._atualizar_bloqueio_operacao_ciclo(
            operacao_bloqueada_ciclo,
            gate=gate_finalizacao,
        )
        self._operacao_bloqueada_ciclo = operacao_bloqueada_ciclo
        if operacao_bloqueada_ciclo:
            estado_bloqueio = (
                gate_finalizacao.get("estado", "degradado")
                if gate_finalizacao.get("apto") is not True
                else "degradado_no_ciclo"
            )
            finalizacao = {
                "consultadas": 0,
                "encerradas": 0,
                "resolvidos": 0,
                "respostas_ausentes": 0,
                "respostas_invalidas": 0,
                "bloqueado_operacao": estado_bloqueio,
                "motivo_bloqueio": (
                    gate_finalizacao.get("motivo")
                    if gate_finalizacao.get("apto") is not True
                    else "degradacao_anterior_no_ciclo"
                ),
                "fonte_bloqueio": (
                    gate_finalizacao.get("fonte")
                    if gate_finalizacao.get("apto") is not True
                    else "ciclo"
                ),
            }
            finalizacao_sem_dado = {
                "candidatos": 0,
                "encerrados_sem_dado": 0,
                "recuperados_sem_dado": 0,
                "resultados_recuperados": [],
                "idade_horas": self.finalizador_sem_dado.idade_horas,
                "tentativas_minimas": (
                    self.finalizador_sem_dado.tentativas_minimas
                ),
                "encerrados_fallback": 0,
                "idade_fallback_horas": (
                    self.finalizador_sem_dado.idade_fallback_horas
                ),
                "tentativas_fallback": (
                    self.finalizador_sem_dado.tentativas_fallback
                ),
                "bloqueado_operacao": estado_bloqueio,
                "motivo_bloqueio": finalizacao["motivo_bloqueio"],
                "fonte_bloqueio": finalizacao["fonte_bloqueio"],
            }
        else:
            finalizacao = self.finalizador.executar()
            finalizacao_sem_dado = self.finalizador_sem_dado.executar()
        if finalizacao["resolvidos"]:
            self._recalibrar()
            print(
                "Resultados encerrados pela API: "
                f"{finalizacao['resolvidos']} sinal(is)"
            )
        if finalizacao.get("respostas_ausentes"):
            print(
                "API-Football sem resposta válida para "
                f"{finalizacao['respostas_ausentes']} partida(s); "
                "nova tentativa após o cooldown."
            )
        if finalizacao_packball.get("pausa_preventiva"):
            coleta["pausa_preventiva"] = (
                finalizacao_packball["pausa_preventiva"]
            )
        self.observabilidade.finalizacao_resultados(
            finalizacao, finalizacao_packball, finalizacao_sem_dado
        )
        if finalizacao_packball["resolvidos"]:
            self._recalibrar()
            print(
                "Resultados encerrados pelo PackBall: "
                f"{finalizacao_packball['resolvidos']} sinal(is)"
            )
        reconciliadas = self._recalibrar_desatualizadas()
        if reconciliadas:
            print(
                "Calibrações reconciliadas automaticamente: "
                + ", ".join(reconciliadas)
            )
        if finalizacao_packball["erros"]:
            print(
                "Falhas temporárias ao conferir encerramentos no PackBall: "
                f"{finalizacao_packball['erros']}"
            )
        if finalizacao_sem_dado["encerrados_sem_dado"]:
            print(
                "Resultados encerrados sem dado suficiente: "
                f"{finalizacao_sem_dado['encerrados_sem_dado']} sinal(is); "
                "não entram no backtest."
            )
        if finalizacao_sem_dado.get("recuperados_sem_dado"):
            self._recalibrar()
            print(
                "Resultados antes sem dado recuperados por evidência "
                "persistida: "
                f"{finalizacao_sem_dado['recuperados_sem_dado']} sinal(is)."
            )
        gate_pos_finalizacao = self._validar_operacao_para_alerta_oficial()
        operacao_bloqueada_ciclo = self._atualizar_bloqueio_operacao_ciclo(
            operacao_bloqueada_ciclo,
            gate=gate_pos_finalizacao,
        )
        if (
            finalizacao.get("respostas_ausentes")
            or finalizacao.get("respostas_invalidas")
            or finalizacao_packball.get("erros")
        ):
            operacao_bloqueada_ciclo = True
        self._operacao_bloqueada_ciclo = operacao_bloqueada_ciclo
        self._adiar_alertas_ciclo = False
        if operacao_bloqueada_ciclo:
            invalidados = self._invalidar_alertas_pendentes_ciclo()
            if invalidados:
                print(
                    "Sinais do ciclo invalidados por fonte incompleta: "
                    f"{invalidados}"
                )
        else:
            pendentes_ciclo = list(self._alertas_pendentes_ciclo)
            self._alertas_pendentes_ciclo = []
            self._despachar_alertas(pendentes_ciclo)

        resultados_acompanhamento_odd = (
            {
                "consultados": 0, "conclusivos": 0, "entregues": 0,
                "erros": 0, "bloqueados": 1,
                "motivo_bloqueio": "operacao_degradada_no_ciclo",
            }
            if operacao_bloqueada_ciclo
            else self.alertas.atualizar_acompanhamentos_odd()
        )
        coleta["resultados_acompanhamento_odd"] = (
            resultados_acompanhamento_odd
        )
        if resultados_acompanhamento_odd["entregues"]:
            print(
                "Telegram: "
                f"{resultados_acompanhamento_odd['entregues']} "
                "monitoramento(s) de odd encerrado(s) com resultado."
            )

        if operacao_bloqueada_ciclo:
            correcoes_simuladas = {
                "consultados": 0, "entregues": 0, "erros": 0,
                "bloqueados": 1,
                "motivo_bloqueio": "operacao_degradada_no_ciclo",
            }
        else:
            correcoes_simuladas = (
                self.alertas.enviar_correcoes_resultados_simulacoes()
            )
        if correcoes_simuladas["entregues"]:
            print(
                "Telegram: "
                f"{correcoes_simuladas['entregues']} correção(ões) de "
                "resultado provisório enviada(s)."
            )
        resultados_oficiais = (
            {
                "consultados": 0, "entregues": 0, "erros": 0,
                "bloqueados": 1,
                "motivo_bloqueio": "operacao_degradada_no_ciclo",
            }
            if operacao_bloqueada_ciclo
            else self.alertas.enviar_resultados_oficiais()
        )
        if resultados_oficiais["entregues"]:
            print(
                "Telegram: "
                f"{resultados_oficiais['entregues']} resultado(s) "
                "oficial(is) enviado(s)."
            )
        if resultados_oficiais.get("recuperados"):
            print(
                "Telegram recuperado: "
                f"{resultados_oficiais['recuperados']} edição(ões) de "
                "resultado oficial confirmada(s)."
            )
        resultados_simulados = (
            {
                "consultados": 0, "entregues": 0, "erros": 0,
                "bloqueados": 1,
                "motivo_bloqueio": "operacao_degradada_no_ciclo",
            }
            if operacao_bloqueada_ciclo
            else self.alertas.enviar_resultados_simulacoes()
        )
        if resultados_simulados["entregues"]:
            print(
                "Telegram: "
                f"{resultados_simulados['entregues']} resultado(s) de "
                "simulação enviado(s)."
            )
        if resultados_simulados.get("recuperados"):
            print(
                "Telegram recuperado: "
                f"{resultados_simulados['recuperados']} edição(ões) de "
                "resultado de análise confirmada(s)."
            )
        reenvios = (
            {
                "consultados": 0, "entregues": 0, "erros": 0,
                "incertos": 0, "cancelados": 0, "expirados": 0,
                "bloqueados": 1,
                "motivo_bloqueio": "operacao_degradada_no_ciclo",
            }
            if operacao_bloqueada_ciclo
            else self.alertas.reenviar_pendentes()
        )
        if reenvios["entregues"]:
            print(
                "Telegram recuperado: "
                f"{reenvios['entregues']} alerta(s) reenviado(s)."
            )
        if reenvios.get("incertos"):
            print(
                "Telegram: "
                f"{reenvios['incertos']} reenvio(s) ficaram incertos; "
                "reconciliação manual necessária."
            )
        self.observabilidade.ciclo_progresso(
            "notificacoes_conferidas",
            resultados_oficiais=resultados_oficiais["entregues"],
            resultados_simulados=resultados_simulados["entregues"],
            resultados_oficiais_recuperados=int(
                resultados_oficiais.get("recuperados", 0) or 0
            ),
            resultados_simulados_recuperados=int(
                resultados_simulados.get("recuperados", 0) or 0
            ),
        )
        agora_manutencao = datetime.now()
        self._manter_backup_diario(agora_manutencao)
        self._manter_backup_periodico(agora_manutencao)
        self._manter_manutencao_diaria(agora_manutencao)
        print("-" * 60)
        consumo = self.api.consumo_atual()
        print(
            "Uso API-Football — hoje: "
            f"{consumo['total_dia']}/{consumo['limite_diario_seguro']} | "
            f"reserva: {consumo['reserva_diaria']} | "
            f"restante seguro: {consumo['restante_seguro_dia']}"
        )
        return len(jogos), consumo, coleta

    def _processar_tarefas_detalhadas(
        self,
        pagina_detalhe,
        tarefas,
        fixtures_restantes,
        orcamento_segundos=ORCAMENTO_COLETA_DETALHADA_SEGUNDOS,
        maximo_tarefas=None,
        relogio=None,
    ):
        relogio = relogio or time.monotonic
        inicio = relogio()
        self._amostras_referencia_odds_ciclo = 0
        self._amostras_referencia_confirmacoes_ciclo = 0
        auditoria_ciclo_em = datetime.now().replace(microsecond=0)
        processadas = 0
        associacoes_api = {}
        duracoes_tarefas = []
        duracoes_etapas_tarefas = {}
        tarefas_com_odds = 0
        tarefas_odds_solicitadas = 0
        odds_packball_poupadas = 0
        odds_api_prioritarias_processadas = 0
        resgates_odds_packball_agendados = 0
        coletas_odds_sucesso = 0
        fallback_odds_necessario = 0
        fallback_odds_atendeu = 0
        fallback_odds_sem_cobertura = 0
        fontes_odds_utilizaveis = {}
        fontes_fallback_odds = {}
        comparacoes_fontes_odds = []
        prioridades_asiaticas_processadas = 0
        odds_asiaticas_api_anexadas = 0
        alvos_um_escanteio_processados = 0
        alvos_um_escanteio_anexados = 0
        sinais_bloqueados_fontes = 0
        motivos_bloqueio_fontes = {}
        auditorias_bloqueios_promissores = 0
        filas_operacionais = {
            nome: {
                "agendadas": sum(
                    1 for tarefa in tarefas
                    if tarefa.get("fila_operacional", "exploracao") == nome
                ),
                "processadas": 0,
            }
            for nome in ("urgente", "acompanhamento", "exploracao")
        }
        gols_antecipados = {
            "avaliacoes": 0,
            "gerados": 0,
            "por_braco": {},
        }
        gols_capacidade_contextual_v2 = {
            "avaliacoes": 0,
            "gerados": 0,
            "por_mercado": {},
        }
        resgate_qualidade_api = {
            "avaliacoes": 0,
            "resgatadas": 0,
            "estados": {},
            "campos_complementados": {},
        }
        cliente_the_odds_api_ciclo = getattr(
            self, "the_odds_api", None
        )
        diagnostico_the_odds_api_base = {}
        diagnosticar_the_odds_api = getattr(
            cliente_the_odds_api_ciclo, "diagnostico", None
        )
        if callable(diagnosticar_the_odds_api):
            try:
                diagnostico_the_odds_api_base = (
                    diagnosticar_the_odds_api() or {}
                )
            except Exception:
                diagnostico_the_odds_api_base = {}
        if not isinstance(diagnostico_the_odds_api_base, dict):
            diagnostico_the_odds_api_base = {}
        diagnostico_amostragem_referencia_base = (
            diagnostico_the_odds_api_base.get("amostragem_referencia")
            or {}
        )
        configuracao_amostragem_referencia = (
            ((getattr(self, "configuracao", {}) or {}).get(
                "the_odds_api"
            ) or {}).get("amostragem_referencia") or {}
        )
        maximo_amostragem_referencia_ciclo = min(max(int(
            configuracao_amostragem_referencia.get(
                "maximo_ciclo", 2
            ) or 0
        ), 0), 10)
        the_odds_api = {
            **diagnostico_the_odds_api_base,
            "ativa": bool(getattr(
                cliente_the_odds_api_ciclo, "ativa", False
            )),
            "partidas_pareadas": 0,
            "partidas_consultadas": 0,
            "mercados_anexados": 0,
            "por_mercado": {},
            "amostragem_referencia": {
                **diagnostico_amostragem_referencia_base,
                "ativa": bool(getattr(
                    cliente_the_odds_api_ciclo,
                    "amostragem_referencia_ativa",
                    False,
                )),
                "elegiveis_betsapi": 0,
                "reservadas": 0,
                "consultadas": 0,
                "pareadas": 0,
                "mercados_persistidos_sombra": 0,
                "novas_partidas_ciclo": 0,
                "confirmacoes_temporais_ciclo": 0,
                "confirmacoes_maximo_ciclo": max(
                    maximo_amostragem_referencia_ciclo - 1, 0
                ),
                "prioriza_novas_partidas": True,
                "prioriza_competicoes_cobertas": True,
                "exige_evento_pareado_antes_reserva": True,
                "preselecoes_cobertura": 0,
                "preselecoes_cobertas": 0,
                "preselecoes_descartadas": 0,
                "preselecoes_evento": 0,
                "eventos_pareados_pre_reserva": 0,
                "eventos_descartados_pre_reserva": 0,
                "reservas_economizadas": 0,
                "reservas_economizadas_evento": 0,
                "creditos_estimados_reservados": 0,
                "consultas_combinadas": 0,
                "maximo_mercados_por_consulta": 0,
                "por_mercado": {},
                "motivos": {},
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            },
        }
        cliente_betsapi = getattr(self, "betsapi", None)
        diagnostico_betsapi_base = {}
        diagnosticar_betsapi = getattr(
            cliente_betsapi, "diagnostico", None
        )
        if callable(diagnosticar_betsapi):
            try:
                diagnostico_betsapi_base = diagnosticar_betsapi()
            except Exception:
                diagnostico_betsapi_base = {}
        if not isinstance(diagnostico_betsapi_base, dict):
            diagnostico_betsapi_base = {}
        betsapi = {
            **diagnostico_betsapi_base,
            "ativa": bool(getattr(cliente_betsapi, "ativa", False)),
            "aplicacao_sinais": bool(getattr(
                cliente_betsapi, "aplicacao_sinais", False
            )),
            "partidas_pareadas": 0,
            "partidas_consultadas": 0,
            "mercados_anexados": 0,
            "por_mercado": {},
        }
        thestatsapi_odds = {
            "evidencias_disponiveis": 0,
            "gates_aptos": 0,
            "aplicacoes_sinais": 0,
            "mercados_convertidos": 0,
            "ofertas_anexadas": 0,
            "mercados_anexados": 0,
            "motivos_gate": {},
        }
        janelas_temporais = {"5": 0, "10": 0, "15": 0}
        partidas_com_historico_temporal = 0
        historico_temporal_por_perfil = {
            "foco": {"processadas": 0, "com_historico": 0},
            "exploracao": {"processadas": 0, "com_historico": 0},
        }
        perfil_agendamento = {
            "foco_agendadas": sum(
                1 for tarefa in tarefas if tarefa.get("em_foco")
            ),
            "exploracao_agendadas": sum(
                1 for tarefa in tarefas if not tarefa.get("em_foco")
            ),
            "foco_processadas": 0,
            "exploracao_processadas": 0,
            "revisitas_processadas": 0,
            "novas_processadas": 0,
            "rechecagens_pos_evento_agendadas": sum(
                1 for tarefa in tarefas
                if tarefa.get("rechecagem_pos_evento")
            ),
            "rechecagens_pos_evento_processadas": 0,
            "acompanhamentos_preco_agendados": sum(
                1 for tarefa in tarefas
                if tarefa.get("acompanhamento_preco")
            ),
            "acompanhamentos_preco_processados": 0,
            "acompanhamentos_preco_com_odds": 0,
            "acompanhamentos_preco_sem_odds": 0,
            "acompanhamentos_preco_snapshots": 0,
            "acompanhamentos_preco_por_mercado": {},
        }
        for tarefa in tarefas:
            if not tarefa.get("acompanhamento_preco"):
                continue
            dados_preco = tarefa.get("acompanhamento_preco_dados") or {}
            for mercado in dados_preco.get("mercados") or []:
                resumo_mercado = perfil_agendamento[
                    "acompanhamentos_preco_por_mercado"
                ].setdefault(str(mercado), {
                    "agendados": 0,
                    "processados": 0,
                    "com_odds": 0,
                    "sem_odds": 0,
                    "snapshots": 0,
                })
                resumo_mercado["agendados"] += 1
        fixtures_restantes = list(fixtures_restantes)
        pausa_preventiva = None
        interrompido_por_reserva = False
        reserva_admissao_segundos = None
        for posicao_tarefa, tarefa in enumerate(tarefas, start=1):
            if (
                maximo_tarefas is not None
                and processadas >= max(int(maximo_tarefas), 1)
            ):
                break
            self._interromper_se_manutencao("entre_partidas")
            self._rechecar_acompanhamentos_odd_api()
            if processadas > 0:
                decorrido = relogio() - inicio
                if decorrido >= float(orcamento_segundos):
                    break
                historico_duracoes = list(getattr(
                    self, "_duracoes_tarefas_recentes", []
                ))
                if historico_duracoes:
                    ordenadas = sorted(historico_duracoes)
                    indice_reserva = max(
                        0,
                        math.ceil(
                            len(ordenadas) * PERCENTIL_RESERVA_TAREFA
                        ) - 1,
                    )
                    reserva_admissao_segundos = max(
                        float(ordenadas[indice_reserva]),
                        MINIMO_RESERVA_TAREFA_SEGUNDOS,
                    ) + MARGEM_RESERVA_TAREFA_SEGUNDOS
                    if (
                        decorrido + reserva_admissao_segundos
                        > float(orcamento_segundos)
                    ):
                        interrompido_por_reserva = True
                        break
            jogo_tarefa = tarefa.get("jogo") or {}
            taxa_liga_tarefa = tarefa.get("taxa_liga_gols") or {}
            self._contexto_amostragem_referencia_ciclo = {
                "ciclo_em": auditoria_ciclo_em.isoformat(),
                "posicao_fila": posicao_tarefa,
                "tarefas_ciclo": len(tarefas),
                "fila_operacional": tarefa.get(
                    "fila_operacional", "exploracao"
                ),
                "liga": (
                    jogo_tarefa.get("liga")
                    or jogo_tarefa.get("liga_nome")
                    or taxa_liga_tarefa.get("liga")
                ),
                "minuto": extrair_minuto(jogo_tarefa.get("status")),
            }
            try:
                odds_api_prioritaria = bool(
                    tarefa.get("odds_api_prioritaria")
                )
                coletar_odds_packball = bool(
                    tarefa["coletar_odds"] and not odds_api_prioritaria
                )
                processamento = self.processar_jogo(
                    pagina_detalhe,
                    tarefa["jogo"],
                    fixtures_restantes,
                coletar_odds_packball,
                    odd_asiatica_api_disponivel=bool(
                        tarefa.get("odd_asiatica_api_disponivel")
                    ),
                    odds_api_prioritaria=odds_api_prioritaria,
                    mercados_acompanhamento_preco=(
                        (tarefa.get("acompanhamento_preco_dados") or {}).get(
                            "mercados_api"
                        ) or []
                    ),
                    somente_acompanhamento_preco=bool(
                        tarefa.get("somente_acompanhamento_preco")
                    ),
                )
            except PackBallPausaPreventivaError as erro:
                pausa_preventiva = str(erro)
                break
            finally:
                self._contexto_amostragem_referencia_ciclo = {}
            duracao_tarefa = processamento.get("duracao_segundos")
            if duracao_tarefa is not None:
                duracao_tarefa = float(duracao_tarefa)
                if math.isfinite(duracao_tarefa) and duracao_tarefa >= 0:
                    duracoes_tarefas.append(duracao_tarefa)
                    historico_duracoes = list(getattr(
                        self, "_duracoes_tarefas_recentes", []
                    ))
                    historico_duracoes.append(duracao_tarefa)
                    self._duracoes_tarefas_recentes = (
                        historico_duracoes[-JANELA_DURACOES_TAREFAS:]
                    )
            diagnostico_etapas = processamento.get("duracoes_etapas") or {}
            etapas_tarefa = diagnostico_etapas.get("etapas") or {}
            if isinstance(etapas_tarefa, dict):
                for nome_etapa, valor_etapa in etapas_tarefa.items():
                    try:
                        valor_etapa = float(valor_etapa)
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(valor_etapa) or valor_etapa < 0:
                        continue
                    duracoes_etapas_tarefas.setdefault(
                        str(nome_etapa), []
                    ).append(valor_etapa)
            if tarefa["coletar_odds"]:
                tarefas_odds_solicitadas += 1
            if odds_api_prioritaria:
                odds_api_prioritarias_processadas += 1
                odds_packball_poupadas += 1
            if processamento.get("odds_coletadas"):
                coletas_odds_sucesso += 1
            auditorias_bloqueios_promissores += int(
                processamento.get("auditoria_bloqueios_promissores", 0) or 0
            )
            fila_processada = tarefa.get(
                "fila_operacional", "exploracao"
            )
            if fila_processada in filas_operacionais:
                filas_operacionais[fila_processada]["processadas"] += 1
            cobertura_odds = processamento.get("cobertura_odds") or {}
            odds_utilizaveis = bool(
                cobertura_odds.get(
                    "final_utilizavel",
                    processamento.get("odds_coletadas", False),
                )
            )
            if odds_utilizaveis:
                tarefas_com_odds += 1
            if cobertura_odds.get("fallback_necessario"):
                fallback_odds_necessario += 1
            if cobertura_odds.get("fallback_atendeu"):
                fallback_odds_atendeu += 1
            if cobertura_odds.get("fallback_sem_cobertura"):
                fallback_odds_sem_cobertura += 1
            url_tarefa = str(tarefa["jogo"].get("url") or "")
            resgates_odds = getattr(
                self, "_resgate_odds_packball_urls", None
            )
            if not isinstance(resgates_odds, set):
                resgates_odds = set()
                self._resgate_odds_packball_urls = resgates_odds
            if odds_api_prioritaria:
                if processamento.get("odds_coletadas"):
                    resgates_odds.discard(url_tarefa)
                elif url_tarefa:
                    resgates_odds.add(url_tarefa)
                    resgates_odds_packball_agendados += 1
            elif coletar_odds_packball and processamento.get(
                "odds_coletadas"
            ):
                resgates_odds.discard(url_tarefa)
            for fonte in cobertura_odds.get("fontes_finais") or []:
                fonte = str(fonte or "nao_identificada")
                fontes_odds_utilizaveis[fonte] = (
                    fontes_odds_utilizaveis.get(fonte, 0) + 1
                )
            for fonte in (
                cobertura_odds.get("fontes_fallback_atenderam") or []
            ):
                fonte = str(fonte or "nao_identificada")
                fontes_fallback_odds[fonte] = (
                    fontes_fallback_odds.get(fonte, 0) + 1
                )
            if processamento.get("odd_asiatica_api_priorizada"):
                prioridades_asiaticas_processadas += 1
            if processamento.get("odd_asiatica_api_anexada"):
                odds_asiaticas_api_anexadas += 1
            diagnostico_odds_novo = processamento.get("the_odds_api") or {}
            if diagnostico_odds_novo.get("pareado"):
                the_odds_api["partidas_pareadas"] += 1
            if diagnostico_odds_novo.get("consultados"):
                the_odds_api["partidas_consultadas"] += 1
            for mercado in diagnostico_odds_novo.get("anexados") or []:
                the_odds_api["mercados_anexados"] += 1
                the_odds_api["por_mercado"][mercado] = (
                    the_odds_api["por_mercado"].get(mercado, 0) + 1
                )
            for chave in (
                "consumo_dia", "limite_diario", "creditos_usados",
                "creditos_restantes", "reserva_mensal", "circuito_aberto",
                "circuito", "controle_estado",
            ):
                if chave in diagnostico_odds_novo:
                    the_odds_api[chave] = diagnostico_odds_novo[chave]
            amostragem_referencia = (
                diagnostico_odds_novo.get(
                    "amostragem_referencia_sombra"
                ) or {}
            )
            resumo_amostragem = the_odds_api["amostragem_referencia"]
            if amostragem_referencia.get("elegivel_betsapi"):
                resumo_amostragem["elegiveis_betsapi"] += 1
            mercados_elegiveis_amostragem = sorted({
                str(item) for item in amostragem_referencia.get(
                    "mercados_elegiveis_betsapi"
                ) or [] if str(item)
            })
            mercados_solicitados_amostragem = sorted({
                str(item) for item in amostragem_referencia.get(
                    "solicitados"
                ) or [] if str(item)
            })
            mercados_anexados_amostragem = sorted({
                str(item) for item in amostragem_referencia.get(
                    "anexados"
                ) or [] if str(item)
            })
            for mercado in mercados_elegiveis_amostragem:
                resumo_mercado = resumo_amostragem[
                    "por_mercado"
                ].setdefault(mercado, {
                    "elegiveis": 0,
                    "consultados": 0,
                    "anexados": 0,
                })
                resumo_mercado["elegiveis"] += 1
            for mercado in mercados_solicitados_amostragem:
                resumo_mercado = resumo_amostragem[
                    "por_mercado"
                ].setdefault(mercado, {
                    "elegiveis": 0,
                    "consultados": 0,
                    "anexados": 0,
                })
                resumo_mercado["consultados"] += 1
            for mercado in mercados_anexados_amostragem:
                resumo_mercado = resumo_amostragem[
                    "por_mercado"
                ].setdefault(mercado, {
                    "elegiveis": 0,
                    "consultados": 0,
                    "anexados": 0,
                })
                resumo_mercado["anexados"] += 1
            preselecao_cobertura = amostragem_referencia.get(
                "preselecao_cobertura"
            ) or {}
            if preselecao_cobertura.get("executada") is True:
                resumo_amostragem["preselecoes_cobertura"] += 1
                if preselecao_cobertura.get("coberta") is True:
                    resumo_amostragem["preselecoes_cobertas"] += 1
                else:
                    resumo_amostragem["preselecoes_descartadas"] += 1
                    if not amostragem_referencia.get(
                        "reserva_consumida", False
                    ):
                        resumo_amostragem["reservas_economizadas"] += 1
            preselecao_evento = amostragem_referencia.get(
                "preselecao_evento"
            ) or {}
            if preselecao_evento.get("executada") is True:
                resumo_amostragem["preselecoes_evento"] += 1
                if preselecao_evento.get("pareado") is True:
                    resumo_amostragem[
                        "eventos_pareados_pre_reserva"
                    ] += 1
                else:
                    resumo_amostragem[
                        "eventos_descartados_pre_reserva"
                    ] += 1
                    if not amostragem_referencia.get(
                        "reserva_consumida", False
                    ):
                        resumo_amostragem[
                            "reservas_economizadas"
                        ] += 1
                        resumo_amostragem[
                            "reservas_economizadas_evento"
                        ] += 1
            if (amostragem_referencia.get("reserva") or {}).get(
                "autorizada"
            ):
                resumo_amostragem["reservadas"] += 1
                custo_estimado = max(int(
                    amostragem_referencia.get(
                        "custo_estimado_creditos", 0
                    ) or 0
                ), 0)
                resumo_amostragem[
                    "creditos_estimados_reservados"
                ] += custo_estimado
                quantidade_mercados = len(
                    mercados_solicitados_amostragem
                    or mercados_elegiveis_amostragem
                )
                resumo_amostragem[
                    "maximo_mercados_por_consulta"
                ] = max(
                    int(resumo_amostragem.get(
                        "maximo_mercados_por_consulta", 0
                    ) or 0),
                    quantidade_mercados,
                )
                if amostragem_referencia.get("consulta_combinada"):
                    resumo_amostragem["consultas_combinadas"] += 1
                tipo_amostra = (
                    amostragem_referencia.get("reserva") or {}
                ).get("tipo_amostra")
                if tipo_amostra == "nova_partida":
                    resumo_amostragem["novas_partidas_ciclo"] += 1
                elif tipo_amostra == "confirmacao_temporal":
                    resumo_amostragem[
                        "confirmacoes_temporais_ciclo"
                    ] += 1
            if amostragem_referencia.get("consultados"):
                resumo_amostragem["consultadas"] += 1
            if amostragem_referencia.get("pareado"):
                resumo_amostragem["pareadas"] += 1
            resumo_amostragem["mercados_persistidos_sombra"] += int(
                amostragem_referencia.get(
                    "mercados_persistidos_sombra", 0
                ) or 0
            )
            motivo_amostragem = amostragem_referencia.get("motivo")
            if motivo_amostragem:
                motivo_amostragem = str(motivo_amostragem)
                motivos_amostragem = resumo_amostragem["motivos"]
                motivos_amostragem[motivo_amostragem] = int(
                    motivos_amostragem.get(motivo_amostragem, 0) or 0
                ) + 1
            diagnostico_betsapi = processamento.get("betsapi") or {}
            if diagnostico_betsapi.get("pareado"):
                betsapi["partidas_pareadas"] += 1
            if diagnostico_betsapi.get("consultados"):
                betsapi["partidas_consultadas"] += 1
            for mercado in diagnostico_betsapi.get("anexados") or []:
                betsapi["mercados_anexados"] += 1
                betsapi["por_mercado"][mercado] = (
                    betsapi["por_mercado"].get(mercado, 0) + 1
                )
            for chave in (
                "uso_hora", "limite_hora", "uso_dia", "limite_diario",
                "circuito_aberto", "circuito", "aplicacao_sinais",
                "rollback",
            ):
                if chave in diagnostico_betsapi:
                    betsapi[chave] = diagnostico_betsapi[chave]
            diagnostico_thestats = (
                processamento.get("thestatsapi_odds") or {}
            )
            if diagnostico_thestats.get("evidencia_disponivel"):
                thestatsapi_odds["evidencias_disponiveis"] += 1
            if diagnostico_thestats.get("gate_apto"):
                thestatsapi_odds["gates_aptos"] += 1
            if diagnostico_thestats.get("aplicacao_sinais"):
                thestatsapi_odds["aplicacoes_sinais"] += 1
            for chave in (
                "mercados_convertidos",
                "ofertas_anexadas",
                "mercados_anexados",
            ):
                thestatsapi_odds[chave] += int(
                    diagnostico_thestats.get(chave, 0) or 0
                )
            motivo_gate = diagnostico_thestats.get("gate_motivo")
            if motivo_gate:
                motivo_gate = str(motivo_gate)
                motivos_gate = thestatsapi_odds["motivos_gate"]
                motivos_gate[motivo_gate] = (
                    int(motivos_gate.get(motivo_gate, 0) or 0) + 1
                )
            comparacoes_fontes_odds.append({
                "partida": tarefa["jogo"].get("url"),
                "fontes_utilizaveis": sorted({
                    str(fonte)
                    for fonte in cobertura_odds.get("fontes_finais") or []
                    if fonte
                }),
                "fontes_fallback": sorted({
                    str(fonte)
                    for fonte in (
                        cobertura_odds.get(
                            "fontes_fallback_atenderam"
                        ) or []
                    )
                    if fonte
                }),
                "betsapi": {
                    "ativa": bool(betsapi.get("ativa")),
                    "pareada": bool(diagnostico_betsapi.get("pareado")),
                    "consultada": bool(
                        diagnostico_betsapi.get("consultados")
                    ),
                    "mercados_anexados": len(
                        diagnostico_betsapi.get("anexados") or []
                    ),
                },
                "thestatsapi": {
                    "ativa": bool(getattr(
                        self, "thestatsapi_sombra_ativa", False
                    )),
                    "evidencia_disponivel": bool(
                        diagnostico_thestats.get("evidencia_disponivel")
                    ),
                    "gate_apto": bool(
                        diagnostico_thestats.get("gate_apto")
                    ),
                    "mercados_anexados": int(
                        diagnostico_thestats.get(
                            "mercados_anexados", 0
                        ) or 0
                    ),
                },
                "the_odds_api": {
                    "ativa": bool(the_odds_api.get("ativa")),
                    "pareada": bool(
                        diagnostico_odds_novo.get("pareado")
                    ),
                    "consultada": bool(
                        diagnostico_odds_novo.get("consultados")
                    ),
                    "mercados_anexados": len(
                        diagnostico_odds_novo.get("anexados") or []
                    ),
                },
            })
            if tarefa.get("odd_asiatica_api_alvo_um_escanteio"):
                alvos_um_escanteio_processados += 1
                if processamento.get("odd_asiatica_api_anexada"):
                    alvos_um_escanteio_anexados += 1
            sinais_bloqueados_fontes += int(
                processamento.get("sinais_bloqueados_fontes") or 0
            )
            for motivo in processamento.get(
                "motivos_bloqueio_fontes", []
            ):
                motivo = str(motivo or "fonte_desconhecida")
                motivos_bloqueio_fontes[motivo] = (
                    motivos_bloqueio_fontes.get(motivo, 0) + 1
                )
            diagnostico_gols = processamento.get("gols_antecipados") or {}
            for braco, avaliacao in (
                diagnostico_gols.get("por_braco") or {}
            ).items():
                if not isinstance(avaliacao, dict):
                    continue
                estado = str(avaliacao.get("estado") or "desconhecido")
                motivo = str(avaliacao.get("motivo") or estado)
                resumo_braco = gols_antecipados["por_braco"].setdefault(
                    str(braco), {"avaliacoes": 0, "gerados": 0, "motivos": {}}
                )
                resumo_braco["avaliacoes"] += 1
                gols_antecipados["avaliacoes"] += 1
                if estado == "gerado":
                    resumo_braco["gerados"] += 1
                    gols_antecipados["gerados"] += 1
                else:
                    resumo_braco["motivos"][motivo] = (
                        resumo_braco["motivos"].get(motivo, 0) + 1
                    )
                for campo_detalhe in ("alertas", "campos_ausentes"):
                    valores = avaliacao.get(campo_detalhe) or []
                    if not isinstance(valores, (list, tuple, set)):
                        valores = [valores]
                    if not valores:
                        continue
                    contadores = resumo_braco.setdefault(
                        "detalhes", {}
                    ).setdefault(campo_detalhe, {})
                    for valor in valores:
                        chave_detalhe = str(valor or "desconhecido")
                        contadores[chave_detalhe] = (
                            contadores.get(chave_detalhe, 0) + 1
                        )
            diagnostico_v2 = (
                processamento.get("gols_capacidade_contextual_v2") or {}
            )
            for mercado, avaliacao in (
                diagnostico_v2.get("por_mercado") or {}
            ).items():
                if not isinstance(avaliacao, dict):
                    continue
                estado = str(avaliacao.get("estado") or "desconhecido")
                motivo = str(avaliacao.get("motivo") or estado)
                resumo_mercado = gols_capacidade_contextual_v2[
                    "por_mercado"
                ].setdefault(
                    str(mercado),
                    {"avaliacoes": 0, "gerados": 0, "motivos": {}},
                )
                resumo_mercado["avaliacoes"] += 1
                gols_capacidade_contextual_v2["avaliacoes"] += 1
                if estado == "gerado":
                    resumo_mercado["gerados"] += 1
                    gols_capacidade_contextual_v2["gerados"] += 1
                else:
                    resumo_mercado["motivos"][motivo] = (
                        resumo_mercado["motivos"].get(motivo, 0) + 1
                    )
            diagnostico_resgate = (
                processamento.get("resgate_qualidade_api") or {}
            )
            if diagnostico_resgate:
                estado_resgate = str(
                    diagnostico_resgate.get("estado") or "desconhecido"
                )
                resgate_qualidade_api["avaliacoes"] += 1
                resgate_qualidade_api["estados"][estado_resgate] = (
                    resgate_qualidade_api["estados"].get(
                        estado_resgate, 0
                    ) + 1
                )
                if estado_resgate == "resgatado":
                    resgate_qualidade_api["resgatadas"] += 1
                for campo in diagnostico_resgate.get(
                    "campos_complementados", []
                ):
                    campo = str(campo)
                    resgate_qualidade_api["campos_complementados"][campo] = (
                        resgate_qualidade_api["campos_complementados"].get(
                            campo, 0
                        ) + 1
                    )
            if tarefa.get("em_foco"):
                perfil_agendamento["foco_processadas"] += 1
                perfil_temporal = "foco"
            else:
                perfil_agendamento["exploracao_processadas"] += 1
                perfil_temporal = "exploracao"
            historico_temporal_por_perfil[perfil_temporal][
                "processadas"
            ] += 1
            if tarefa.get("idade_segundos") is None:
                perfil_agendamento["novas_processadas"] += 1
            else:
                perfil_agendamento["revisitas_processadas"] += 1
            if tarefa.get("rechecagem_pos_evento"):
                perfil_agendamento[
                    "rechecagens_pos_evento_processadas"
                ] += 1
            if tarefa.get("acompanhamento_preco"):
                perfil_agendamento[
                    "acompanhamentos_preco_processados"
                ] += 1
                com_odds_preco = bool(processamento.get("odds_coletadas"))
                snapshot_preco = processamento.get("snapshot_id") is not None
                perfil_agendamento[
                    "acompanhamentos_preco_com_odds"
                    if com_odds_preco
                    else "acompanhamentos_preco_sem_odds"
                ] += 1
                if snapshot_preco:
                    perfil_agendamento[
                        "acompanhamentos_preco_snapshots"
                    ] += 1
                dados_preco = (
                    tarefa.get("acompanhamento_preco_dados") or {}
                )
                for mercado in dados_preco.get("mercados") or []:
                    resumo_mercado = perfil_agendamento[
                        "acompanhamentos_preco_por_mercado"
                    ].setdefault(str(mercado), {
                        "agendados": 0,
                        "processados": 0,
                        "com_odds": 0,
                        "sem_odds": 0,
                        "snapshots": 0,
                    })
                    resumo_mercado["processados"] += 1
                    resumo_mercado[
                        "com_odds" if com_odds_preco else "sem_odds"
                    ] += 1
                    if snapshot_preco:
                        resumo_mercado["snapshots"] += 1
            janelas_disponiveis = {
                str(janela)
                for janela in processamento.get(
                    "janelas_temporais", []
                )
            }
            if janelas_disponiveis:
                partidas_com_historico_temporal += 1
                historico_temporal_por_perfil[perfil_temporal][
                    "com_historico"
                ] += 1
            for janela in janelas_temporais:
                if janela in janelas_disponiveis:
                    janelas_temporais[janela] += 1
            fixture_usado = processamento["fixture_id"]
            motivo_api = processamento.get(
                "api_associacao_motivo", "nao_registrado"
            )
            associacoes_api[motivo_api] = (
                associacoes_api.get(motivo_api, 0) + 1
            )
            if fixture_usado is not None:
                fixtures_restantes = [
                    item for item in fixtures_restantes
                    if (item.get("fixture") or {}).get("id") != fixture_usado
                ]
            self.agendador.concluir(
                tarefa,
                odds_coletadas=processamento["odds_coletadas"],
            )
            processadas += 1
            self.observabilidade.ciclo_progresso(
                "coleta_detalhada",
                processadas=processadas,
                agendadas=len(tarefas),
                partida=tarefa["jogo"].get("url"),
            )
        duracoes_ordenadas = sorted(duracoes_tarefas)
        indice_p95 = max(
            0, math.ceil(len(duracoes_ordenadas) * 0.95) - 1
        ) if duracoes_ordenadas else None
        resumo_duracoes_etapas = {}
        for nome_etapa, valores_etapa in sorted(
            duracoes_etapas_tarefas.items()
        ):
            ordenados_etapa = sorted(valores_etapa)
            indice_p95_etapa = max(
                0, math.ceil(len(ordenados_etapa) * 0.95) - 1
            )
            resumo_duracoes_etapas[nome_etapa] = {
                "amostras": len(ordenados_etapa),
                "total_segundos": round(sum(ordenados_etapa), 3),
                "media_segundos": round(
                    sum(ordenados_etapa) / len(ordenados_etapa), 3
                ),
                "p95_segundos": round(
                    ordenados_etapa[indice_p95_etapa], 3
                ),
            }
        controle_packball = getattr(self, "controle_packball", None)
        ritmo_packball = {
            "distribuicao_janela_ativa": (
                getattr(
                    controle_packball, "distribuir_janela", False
                ) is True
            ),
            "intervalo_efetivo_segundos": getattr(
                controle_packball,
                "intervalo_minimo_segundos",
                None,
            ),
            "maximo_por_janela": getattr(
                controle_packball, "maximo_por_janela", None
            ),
            "janela_segundos": getattr(
                controle_packball, "janela_segundos", None
            ),
        }

        def resumir_idades(tarefas_grupo):
            idades = []
            sem_historico = 0
            for tarefa in tarefas_grupo:
                valor = tarefa.get("idade_segundos")
                if valor is None:
                    sem_historico += 1
                    continue
                try:
                    valor = float(valor)
                except (TypeError, ValueError):
                    sem_historico += 1
                    continue
                if not math.isfinite(valor) or valor < 0:
                    sem_historico += 1
                    continue
                idades.append(valor)
            return {
                "tarefas": len(tarefas_grupo),
                "com_historico": len(idades),
                "sem_historico": sem_historico,
                "maxima_segundos": (
                    round(max(idades), 3) if idades else None
                ),
                "acima_20_minutos": sum(
                    valor > 20 * 60 for valor in idades
                ),
            }

        tarefas_processadas = tarefas[:processadas]
        tarefas_adiadas = tarefas[processadas:]

        def somente_acionaveis(tarefas_grupo):
            return [
                tarefa for tarefa in tarefas_grupo
                if tarefa.get("acionavel_fila_detalhada") is True
            ]

        # A idade bruta continua disponível para auditoria histórica, mas o
        # watchdog também recebe a idade operacional. Uma partida já fora de
        # todas as janelas pode permanecer no ciclo para coleta/fechamento sem
        # ser confundida com uma oportunidade acionável sofrendo starvation.
        idade_fila = {
            "agendadas": resumir_idades(tarefas),
            "processadas": resumir_idades(tarefas_processadas),
            "adiadas": resumir_idades(tarefas_adiadas),
        }
        if any(
            "acionavel_fila_detalhada" in tarefa for tarefa in tarefas
        ):
            idade_fila.update({
                "agendadas_acionaveis": resumir_idades(
                    somente_acionaveis(tarefas)
                ),
                "processadas_acionaveis": resumir_idades(
                    somente_acionaveis(tarefas_processadas)
                ),
                "adiadas_acionaveis": resumir_idades(
                    somente_acionaveis(tarefas_adiadas)
                ),
            })
        if pausa_preventiva:
            motivo_adiamento = "pausa_preventiva"
        elif interrompido_por_reserva:
            motivo_adiamento = "reserva_orcamento"
        elif (
            maximo_tarefas is not None
            and processadas >= max(int(maximo_tarefas), 1)
        ):
            motivo_adiamento = "limite_detalhes"
        else:
            motivo_adiamento = "orcamento_ciclo"
        registros_auditoria_fila = []
        for indice, tarefa in enumerate(tarefas, start=1):
            jogo = tarefa.get("jogo") or {}
            taxa_liga_gols = tarefa.get("taxa_liga_gols") or {}
            registros_auditoria_fila.append({
                "ciclo_em": auditoria_ciclo_em.isoformat(),
                "packball_url": jogo.get("url"),
                "mandante": jogo.get("mandante"),
                "visitante": jogo.get("visitante"),
                "liga": (
                    jogo.get("liga")
                    or jogo.get("liga_nome")
                    or taxa_liga_gols.get("liga")
                ),
                "minuto": extrair_minuto(jogo.get("status")),
                "posicao": indice,
                "processada": indice <= processadas,
                "acionavel": tarefa.get(
                    "acionavel_fila_detalhada"
                ) is True,
                "fila_operacional": tarefa.get(
                    "fila_operacional", "exploracao"
                ),
                "idade_segundos": tarefa.get("idade_segundos"),
                "atraso_segundos": tarefa.get("atraso_segundos"),
                "em_foco": tarefa.get("em_foco") is True,
                "scanner_prioritario": tarefa.get(
                    "scanner_prioritario"
                ) is True,
                "pre_live_prioritario": tarefa.get(
                    "pre_live_prioritario"
                ) is True,
                "prioridade_liga_gols": tarefa.get(
                    "prioridade_liga_gols"
                ),
                "prioridade_indicadores_lista": tarefa.get(
                    "pontuacao_indicadores_lista"
                ),
                "prioridade_api_lote": tarefa.get(
                    "prioridade_api_lote"
                ),
                "janelas_temporais": tarefa.get(
                    "janelas_temporais_projetadas", []
                ),
                "motivo": (
                    "processada" if indice <= processadas
                    else motivo_adiamento
                ),
            })
        salvar_auditoria_fila = getattr(
            self.banco, "salvar_auditoria_fila_packball", None
        )
        try:
            auditoria_fila = (
                salvar_auditoria_fila(
                    registros_auditoria_fila,
                    agora=datetime.now(),
                    retencao_dias=float(os.getenv(
                        "AUDITORIA_FILA_RETENCAO_DIAS", "7"
                    )),
                )
                if callable(salvar_auditoria_fila)
                else {
                    "saudavel": False,
                    "estado": "repositorio_indisponivel",
                    "aplicacao_sinais": False,
                }
            )
        except Exception as erro:
            auditoria_fila = {
                "saudavel": False,
                "estado": "falha_isolada",
                "erro": type(erro).__name__,
                "aplicacao_sinais": False,
            }
        thestatsapi_scout_reservado = any(
            bool(tarefa.get("_thestatsapi_scout")) for tarefa in tarefas
        )
        thestatsapi_scout_processado = any(
            bool(tarefa.get("_thestatsapi_scout"))
            for tarefa in tarefas[:processadas]
        )
        return {
            "agendadas": len(tarefas),
            "processadas": processadas,
            "adiadas": len(tarefas) - processadas,
            "pausa_preventiva": pausa_preventiva,
            "duracao_detalhada_segundos": round(relogio() - inicio, 3),
            "orcamento_segundos": float(orcamento_segundos),
            "interrompido_por_reserva": interrompido_por_reserva,
            "reserva_admissao_segundos": (
                round(reserva_admissao_segundos, 3)
                if reserva_admissao_segundos is not None else None
            ),
            "duracoes_historicas_admissao": len(getattr(
                self, "_duracoes_tarefas_recentes", []
            )),
            "associacoes_api": associacoes_api,
            "tarefas_com_odds": tarefas_com_odds,
            "tarefas_sem_odds": processadas - tarefas_com_odds,
            "tarefas_odds_solicitadas": tarefas_odds_solicitadas,
            "odds_api_prioritarias_processadas": (
                odds_api_prioritarias_processadas
            ),
            "odds_packball_poupadas": odds_packball_poupadas,
            "resgates_odds_packball_agendados": (
                resgates_odds_packball_agendados
            ),
            "coletas_odds_sucesso": coletas_odds_sucesso,
            "fallback_odds_necessario": fallback_odds_necessario,
            "fallback_odds_atendeu": fallback_odds_atendeu,
            "fallback_odds_sem_cobertura": (
                fallback_odds_sem_cobertura
            ),
            "fontes_odds_utilizaveis": fontes_odds_utilizaveis,
            "fontes_fallback_odds": fontes_fallback_odds,
            "comparacoes_fontes_odds": comparacoes_fontes_odds,
            "prioridades_asiaticas_processadas": (
                prioridades_asiaticas_processadas
            ),
            "odds_asiaticas_api_anexadas": odds_asiaticas_api_anexadas,
            "prioridades_asiaticas_sem_anexo": max(
                prioridades_asiaticas_processadas
                - odds_asiaticas_api_anexadas,
                0,
            ),
            "alvos_um_escanteio_processados": (
                alvos_um_escanteio_processados
            ),
            "alvos_um_escanteio_anexados": alvos_um_escanteio_anexados,
            "sinais_bloqueados_fontes": sinais_bloqueados_fontes,
            "motivos_bloqueio_fontes": motivos_bloqueio_fontes,
            "auditoria_bloqueios_promissores": (
                auditorias_bloqueios_promissores
            ),
            "filas_operacionais": filas_operacionais,
            "gols_antecipados": gols_antecipados,
            "gols_capacidade_contextual_v2": (
                gols_capacidade_contextual_v2
            ),
            "resgate_qualidade_api": resgate_qualidade_api,
            "the_odds_api": the_odds_api,
            "betsapi": betsapi,
            "thestatsapi_odds": thestatsapi_odds,
            "perfil_agendamento": perfil_agendamento,
            "ritmo_packball": ritmo_packball,
            "idade_fila": idade_fila,
            "auditoria_fila_packball": auditoria_fila,
            "thestatsapi_scout_reservado": thestatsapi_scout_reservado,
            "thestatsapi_scout_processado": thestatsapi_scout_processado,
            "cobertura_temporal": {
                "partidas_com_historico": (
                    partidas_com_historico_temporal
                ),
                "taxa_com_historico": (
                    round(
                        partidas_com_historico_temporal / processadas,
                        4,
                    )
                    if processadas else None
                ),
                "janelas_disponiveis": janelas_temporais,
                "taxas_por_janela": {
                    janela: (
                        round(quantidade / processadas, 4)
                        if processadas else None
                    )
                    for janela, quantidade in janelas_temporais.items()
                },
                "por_perfil": {
                    perfil: {
                        **valores,
                        "taxa_com_historico": (
                            round(
                                valores["com_historico"]
                                / valores["processadas"],
                                4,
                            )
                            if valores["processadas"] else None
                        ),
                    }
                    for perfil, valores in (
                        historico_temporal_por_perfil.items()
                    )
                },
            },
            "duracao_tarefa_media_segundos": (
                round(sum(duracoes_tarefas) / len(duracoes_tarefas), 3)
                if duracoes_tarefas else None
            ),
            "duracao_tarefa_p95_segundos": (
                round(duracoes_ordenadas[indice_p95], 3)
                if indice_p95 is not None else None
            ),
            "duracoes_tarefas_segundos": [
                round(valor, 3) for valor in duracoes_tarefas
            ],
            "duracoes_etapas_detalhadas": {
                "versao": "duracoes-etapas-detalhe-v1",
                "altera_sinal": False,
                "etapas": resumo_duracoes_etapas,
            },
        }

    def _estado_prioridades_recentes(self, jogos, agora=None):
        urls = [jogo["url"] for jogo in jogos]
        if not urls:
            return {
                "pontuacoes": {},
                "rechecagens_pos_evento": set(),
                "rechecagens_odd_gol": set(),
                "candidatos_exploracao_gols": set(),
                "acompanhamentos_preco": {},
            }
        agora = agora or datetime.now()
        agora_sql = agora.replace(microsecond=0).isoformat()
        marcadores = ",".join("?" for _ in urls)
        versao_proximo_gol = versao_regra_operacional("proximo_gol")
        linhas = self.banco.conexao.execute(
            f"""
            WITH partidas_alvo AS (
                SELECT id, packball_url
                FROM partidas
                WHERE packball_url IN ({marcadores})
            ),
            alertas_preco AS (
                SELECT s.partida_id,
                       MAX(COALESCE(e.entregue_em,e.tentado_em)) AS entregue_em,
                       GROUP_CONCAT(DISTINCT s.mercado) AS mercados,
                       GROUP_CONCAT(DISTINCT COALESCE(
                           json_extract(s.features_json,'$.fonte_odds'),''
                       )) AS fontes
                FROM sinais s
                JOIN partidas_alvo alvo ON alvo.id=s.partida_id
                JOIN entregas_alertas e ON e.sinal_id=s.id
                WHERE s.mercado IN (
                    'gol_ft','gol_ht','proximo_gol',
                    'proximo_escanteio','escanteios_ft_asiatico'
                )
                  AND e.status='entregue'
                  AND e.canal NOT LIKE 'gateway:%'
                  AND e.canal NOT LIKE '%:resultado%'
                  AND e.canal NOT LIKE '%:green_antecipado%'
                  AND e.canal NOT LIKE '%:aguardar_odd%'
                  AND e.canal NOT LIKE '%:cancelamento%'
                  AND e.canal NOT LIKE '%:insuficiente%'
                  AND e.canal NOT LIKE '%:monitoramento_final%'
                  AND datetime(COALESCE(e.entregue_em,e.tentado_em))
                      >= datetime(?, '-10 minutes')
                  AND datetime(COALESCE(e.entregue_em,e.tentado_em))
                      <= datetime(?, '-2 minutes')
                GROUP BY s.partida_id
            ),
            ultimas_decisoes AS (
                SELECT s.partida_id, MAX(s.id) AS ultimo_sinal_id
                FROM sinais s
                JOIN partidas_alvo p ON p.id=s.partida_id
                GROUP BY s.partida_id
            ),
            snapshots_recentes AS (
                SELECT s.partida_id, s.snapshot_id
                FROM sinais s
                JOIN ultimas_decisoes u ON u.ultimo_sinal_id=s.id
            )
            SELECT p.packball_url,
                   alerta_preco.entregue_em AS alerta_preco_entregue_em,
                   alerta_preco.mercados AS alerta_preco_mercados,
                   alerta_preco.fontes AS alerta_preco_fontes,
                   MAX(s.pontuacao_tecnica) AS pontuacao,
                   MAX(
                       CASE
                           WHEN s.mercado='proximo_gol'
                            AND s.regra_versao=?
                            AND s.motivos_json LIKE
                                '%"bloqueio:gol_recente_aguardar_odds"%'
                           THEN 1 ELSE 0
                       END
                   ) AS rechecagem_pos_evento
                   ,MAX(
                       CASE
                           WHEN s.mercado='proximo_gol'
                            AND s.regra_versao=?
                            AND s.status='aprovado'
                           THEN 1 ELSE 0
                       END
                   ) AS proximo_gol_aprovado
                   ,MAX(
                       CASE
                           WHEN s.mercado='gol_ft'
                            AND s.status='rejeitado'
                            AND (
                                s.motivos_json LIKE
                                    '%"bloqueio:odd_ao_vivo_indisponivel"%'
                                OR s.motivos_json LIKE
                                    '%"bloqueio:odd_fora_da_faixa_operacional"%'
                            )
                           THEN 1 ELSE 0
                       END
                   ) AS gol_ft_aguardando_odd
                   ,MAX(
                       CASE
                           WHEN s.mercado IN (
                                'gol_ft', 'gol_ht', 'proximo_gol'
                           )
                            AND s.status='rejeitado'
                            AND json_extract(
                                s.features_json,
                                '$.acompanhamento_odd.elegivel_aviso'
                            )=1
                            AND EXISTS (
                                SELECT 1
                                FROM sinais origem_sinal
                                JOIN entregas_alertas origem_alerta
                                  ON origem_alerta.sinal_id=origem_sinal.id
                                 AND origem_alerta.status='entregue'
                                 AND origem_alerta.canal LIKE
                                     '%:aguardar_odd'
                                WHERE origem_sinal.partida_id=s.partida_id
                            )
                           THEN 1 ELSE 0
                       END
                   ) AS acompanhamento_odd_ativo
                   ,MAX(
                       CASE
                           WHEN s.mercado IN ('gol_ft', 'gol_ht')
                            AND s.status='rejeitado'
                            AND s.pontuacao_tecnica >= 60
                            AND s.motivos_json LIKE
                                '%"bloqueio:atividade_recente_insuficiente_gols"%'
                            AND s.motivos_json LIKE
                                '%"bloqueio:historico_5min_insuficiente"%'
                            AND s.motivos_json NOT LIKE
                                '%"bloqueio:qualidade_insuficiente"%'
                            AND s.motivos_json NOT LIKE
                                '%"bloqueio:cartao_vermelho_reavaliar"%'
                            AND s.motivos_json NOT LIKE
                                '%"bloqueio:contador_reiniciado"%'
                           THEN 1 ELSE 0
                       END
                   ) AS candidato_exploracao_gols
            FROM partidas_alvo p
            LEFT JOIN alertas_preco alerta_preco
                   ON alerta_preco.partida_id=p.id
            LEFT JOIN snapshots_recentes recente
                   ON recente.partida_id=p.id
            LEFT JOIN sinais s
                   ON s.partida_id=p.id
                  AND s.snapshot_id=recente.snapshot_id
            GROUP BY p.id, p.packball_url, alerta_preco.entregue_em,
                     alerta_preco.mercados, alerta_preco.fontes
            """,
            [
                *urls, agora_sql, agora_sql,
                versao_proximo_gol, versao_proximo_gol,
            ],
        ).fetchall()
        acompanhamentos_preco = {}
        for linha in linhas:
            instante = linha["alerta_preco_entregue_em"]
            if not instante:
                continue
            try:
                entregue_em = datetime.fromisoformat(
                    str(instante).replace("Z", "+00:00")
                )
                referencia = agora
                if entregue_em.tzinfo is not None and referencia.tzinfo is None:
                    entregue_em = entregue_em.astimezone().replace(
                        tzinfo=None
                    )
                elif entregue_em.tzinfo is None and referencia.tzinfo is not None:
                    referencia = referencia.replace(tzinfo=None)
                idade = (referencia - entregue_em).total_seconds()
            except (TypeError, ValueError):
                continue
            if 120 <= idade <= 600:
                mercados = {
                    item.strip()
                    for item in str(
                        linha["alerta_preco_mercados"] or ""
                    ).split(",")
                    if item.strip()
                }
                fontes = {
                    item.strip().casefold()
                    for item in str(
                        linha["alerta_preco_fontes"] or ""
                    ).split(",")
                    if item.strip()
                }
                acompanhamentos_preco[linha["packball_url"]] = {
                    "idade_segundos": idade,
                    "mercados": sorted(mercados),
                    # PackBall sera coletado diretamente. Uma fonte auxiliar
                    # precisa ter o mesmo mercado solicitado outra vez.
                    "mercados_api": (
                        sorted(mercados)
                        if fontes - {"packball"} else []
                    ),
                    "fontes": sorted(fontes),
                }
        return {
            "pontuacoes": {
                linha["packball_url"]: linha["pontuacao"] or 0
                for linha in linhas
            },
            "rechecagens_pos_evento": {
                linha["packball_url"]
                for linha in linhas
                if linha["rechecagem_pos_evento"]
            },
            "rechecagens_odd_gol": {
                linha["packball_url"]
                for linha in linhas
                if (
                    linha["acompanhamento_odd_ativo"]
                    or (
                        linha["proximo_gol_aprovado"]
                        and linha["gol_ft_aguardando_odd"]
                    )
                )
            },
            "candidatos_exploracao_gols": {
                linha["packball_url"]
                for linha in linhas
                if linha["candidato_exploracao_gols"]
            },
            "acompanhamentos_preco": acompanhamentos_preco,
        }

    def _pontuacoes_recentes(self, jogos):
        return self._estado_prioridades_recentes(jogos)["pontuacoes"]

    def _restaurar_agendamento_persistido(self, jogos, agora=None):
        agora = agora or datetime.now()
        instantes = self.banco.carregar_instantes_agendamento(
            [jogo["url"] for jogo in jogos]
        )
        idades = {}
        for url, estado in instantes.items():
            dados = {}
            for origem, destino in (
                ("ultima_coleta", "idade_coleta"),
                ("ultima_odds", "idade_odds"),
            ):
                valor = estado.get(origem)
                if not valor:
                    continue
                try:
                    dados[destino] = max(
                        (agora - datetime.fromisoformat(valor)).total_seconds(),
                        0.0,
                    )
                except (TypeError, ValueError):
                    continue
            if dados:
                idades[url] = dados
        return self.agendador.restaurar(idades)

    def _fixtures_api_para(self, jogos):
        if not jogos:
            return []
        return self.api.jogos_ao_vivo()

    def _coletar_historico_api_live_durante_pausa_packball(
        self, motivo, agora=None
    ):
        """Mantem somente a serie API de pareamentos ja comprovados.

        Este caminho e deliberadamente fail-closed: nao cria snapshots do
        motor, sinais, resultados, calibracoes ou entregas Telegram.
        """
        self._operacao_bloqueada_ciclo = True
        self._invalidar_alertas_pendentes_ciclo()
        agora = (agora or datetime.now()).replace(microsecond=0)
        diagnostico = {
            "estado": "indisponivel",
            "motivo_packball": str(motivo or "packball_indisponivel"),
            "alvos_pareados": 0,
            "alvos_ao_vivo": 0,
            "detalhes_retornados": 0,
            "normalizados": 0,
            "inseridos": 0,
            "aplicacao_sinais": False,
            "operacao_bloqueada": True,
        }

        def concluir(estado, **dados):
            diagnostico.update({"estado": estado, **dados})
            observabilidade = getattr(self, "observabilidade", None)
            registrar = getattr(
                observabilidade, "historico_api_pausa_packball", None
            )
            if callable(registrar):
                registrar(diagnostico)
            return diagnostico

        desde = (
            agora - timedelta(hours=JANELA_PAREAMENTOS_API_PAUSA_HORAS)
        ).isoformat()
        try:
            linhas = self.banco.conexao.execute(
                """
                SELECT packball_url, api_fixture_id, api_orientacao,
                       ultima_coleta
                FROM partidas
                WHERE api_fixture_id IS NOT NULL
                  AND api_orientacao IN ('direta', 'invertida')
                  AND datetime(ultima_coleta) >= datetime(?)
                ORDER BY datetime(ultima_coleta) DESC, id DESC
                """,
                (desde,),
            ).fetchall()
        except Exception as erro:
            return concluir(
                "falha_pareamentos", erro=type(erro).__name__
            )

        pareamentos = {}
        for linha in linhas:
            item = dict(linha)
            fixture_id = int(item["api_fixture_id"])
            pareamentos.setdefault(fixture_id, item)
        diagnostico["alvos_pareados"] = len(pareamentos)
        if not pareamentos:
            return concluir("sem_pareamentos_recentes")

        limite, capacidade = self._limite_enriquecimento_api_lote()
        diagnostico["capacidade_api"] = capacidade
        cota_confirmada = (
            capacidade.get("restante_seguro_antes") is not None
            and capacidade.get("detalhes_restantes_antes") is not None
        )
        if not cota_confirmada:
            return concluir("adiado_cota_api_nao_confirmada")
        if limite <= 0:
            return concluir("adiado_capacidade_api")

        try:
            fixtures_live = self.api.jogos_ao_vivo()
        except Exception as erro:
            return concluir("falha_lista_api", erro=type(erro).__name__)
        ids_live = {
            int(fixture_id)
            for item in fixtures_live or []
            if isinstance(item, dict)
            for fixture_id in [(item.get("fixture") or {}).get("id")]
            if fixture_id is not None
        }
        ids = [
            fixture_id for fixture_id in pareamentos
            if fixture_id in ids_live
        ][:limite]
        diagnostico["alvos_ao_vivo"] = len(ids)
        if not ids:
            return concluir("sem_pareamentos_ao_vivo")

        try:
            detalhes = self.api.fixtures_ao_vivo_detalhadas(ids)
        except Exception as erro:
            return concluir("falha_detalhes_api", erro=type(erro).__name__)
        detalhes = [item for item in detalhes or [] if isinstance(item, dict)]
        diagnostico["detalhes_retornados"] = len(detalhes)
        registros = []
        for fixture in detalhes:
            fixture_id = (fixture.get("fixture") or {}).get("id")
            try:
                alvo = pareamentos.get(int(fixture_id))
            except (TypeError, ValueError):
                alvo = None
            if alvo is None:
                continue
            registro = normalizar_snapshot_api_live(
                fixture,
                alvo["packball_url"],
                orientacao=alvo["api_orientacao"],
                coletado_em=agora,
            )
            if registro is not None:
                registros.append(registro)
        diagnostico["normalizados"] = len(registros)
        if not registros:
            return concluir("sem_estatisticas_normalizaveis")
        try:
            persistencia = self.banco.salvar_historico_api_live(
                registros, agora=agora
            )
        except Exception as erro:
            return concluir("falha_persistencia", erro=type(erro).__name__)
        return concluir(
            "persistido",
            inseridos=int((persistencia or {}).get("inseridos", 0) or 0),
            duplicados=int(
                (persistencia or {}).get("duplicados", 0) or 0
            ),
        )

    def _aguardar_pausa_packball_antes_navegador(self, uma_vez=False):
        """Mantem o monitor vivo sem iniciar o Playwright durante a pausa.

        Uma pausa persistida (inclusive por login expirado) ja determina que
        nenhuma navegacao PackBall pode ocorrer. Abrir o driver antes de ler
        esse estado e desnecessario e, no Windows, pode criar um ciclo de
        ``PermissionError`` seguido de reinicios do watchdog. Enquanto a
        pausa estiver ativa, somente o historico auxiliar fail-closed e
        atualizado; sinais e Telegram permanecem bloqueados.

        Retorna ``True`` quando o chamador deve encerrar sem abrir navegador
        (execucao unica, manutencao ou atualizacao de runtime). Retorna
        ``False`` quando a pausa terminou e a inicializacao normal pode
        continuar.
        """
        estado_fn = getattr(
            getattr(self, "controle_packball", None),
            "estado_atual",
            None,
        )
        if not callable(estado_fn):
            return False

        assinatura_impressa = None
        while True:
            if self._modo_manutencao_ativo():
                return True
            try:
                estado = estado_fn() or {}
            except Exception:
                # O gate de navegacao continua sendo a autoridade final. Se
                # o espelho nao puder ser lido aqui, nao invente uma pausa.
                return False
            if estado.get("ativo") is not True:
                return False

            inicio = time.monotonic()
            motivo = str(estado.get("motivo") or "pausa_seguranca")
            restante = max(
                float(estado.get("restante_segundos") or 0.0), 0.0
            )
            erro = PackBallPausaPreventivaError(
                "Pausa de seguranca do PackBall ativa antes do navegador "
                f"(motivo: {motivo}); aguarde {restante:.0f}s."
            )
            self._operacao_bloqueada_ciclo = True
            self._invalidar_alertas_pendentes_ciclo()
            observabilidade = getattr(self, "observabilidade", None)
            if observabilidade is not None:
                observabilidade.ciclo_progresso(
                    "pausa_packball_antes_navegador",
                    motivo=motivo,
                    restante_segundos=round(restante, 1),
                )
            try:
                self._coletar_historico_api_live_durante_pausa_packball(
                    "PackBallPausaPreventivaError"
                )
            except Exception as erro_sombra:
                self._operacao_bloqueada_ciclo = True
                self._alertas_pendentes_ciclo = []
                if observabilidade is not None:
                    observabilidade.historico_api_pausa_packball({
                        "estado": "falha_isolada",
                        "erro": type(erro_sombra).__name__,
                        "aplicacao_sinais": False,
                        "operacao_bloqueada": True,
                    })
            self._registrar_interrupcao_ciclo(
                time.monotonic() - inicio, erro
            )

            assinatura = (motivo, int(restante // 60))
            if assinatura != assinatura_impressa:
                print(
                    "PackBall aguardando liberacao sem abrir navegador "
                    f"(motivo: {motivo}; restante: {restante:.0f}s)."
                )
                assinatura_impressa = assinatura
            if uma_vez:
                return True

            self._supervisionar_watchdog()
            diagnostico_runtime = self._avaliar_reinicio_runtime_monitor()
            if diagnostico_runtime.get("solicitado"):
                self.reinicio_runtime_solicitado = True
                self.diagnostico_reinicio_runtime = diagnostico_runtime
                if observabilidade is not None:
                    observabilidade.ciclo_progresso(
                        "reinicio_runtime_monitor_solicitado",
                        estado_monitor=diagnostico_runtime.get(
                            "estado_monitor"
                        ),
                        estado_watchdog=diagnostico_runtime.get(
                            "estado_watchdog"
                        ),
                    )
                return True

            duracao = time.monotonic() - inicio
            espera = max(0.0, INTERVALO_SEGUNDOS - duracao)
            if restante > 0:
                espera = min(espera, restante)
            interrompido = self._aguardar_intervalo_interrompivel(
                espera,
                interromper_fn=lambda: (
                    (estado_fn() or {}).get("ativo") is not True
                ),
            )
            if interrompido:
                if self._modo_manutencao_ativo():
                    return True
                # A pausa foi alterada no disco (por exemplo, depois de um
                # login manual confirmado). Releia imediatamente sem fazer
                # outra coleta auxiliar ou aguardar o intervalo completo.
                continue

    def _limite_enriquecimento_api_lote(self):
        """Reserva a cota cara para os jogos que chegarem ao motor."""
        try:
            configurado = int(os.getenv(
                "API_FIXTURES_DETALHADAS_MAX_CICLO", "40"
            ))
        except (TypeError, ValueError):
            configurado = 40
        configurado = max(0, min(configurado, 100))
        diagnostico = {
            "limite_configurado": configurado,
            "restante_seguro_antes": None,
            "detalhes_restantes_antes": None,
        }
        consumo_fn = getattr(self.api, "consumo_atual", None)
        try:
            consumo = consumo_fn() if callable(consumo_fn) else None
        except Exception:
            consumo = None
        if not isinstance(consumo, dict):
            diagnostico["limite_efetivo"] = configurado
            return configurado, diagnostico

        try:
            restante_seguro = max(
                int(consumo.get("restante_seguro_dia")), 0
            )
        except (TypeError, ValueError):
            restante_seguro = None
        dia = consumo.get("dia") or {}
        try:
            detalhes_usados = max(int(dia.get("detalhe", 0)), 0)
            limite_detalhes = max(
                int(getattr(self.api, "limite_diario_detalhes")), 0
            )
            detalhes_restantes = max(
                limite_detalhes - detalhes_usados, 0
            )
        except (TypeError, ValueError):
            detalhes_restantes = None

        limite = configurado
        # O lote e apenas uma otimizacao de prioridade. Perto do fim da
        # cota ele e reduzido antes de afetar estatisticas, odds e resultados
        # dos jogos efetivamente processados.
        if restante_seguro is not None:
            if restante_seguro < 100:
                limite = 0
            elif restante_seguro < 500:
                limite = min(limite, 20)
        if detalhes_restantes is not None:
            limite = min(limite, detalhes_restantes * 20)

        diagnostico.update({
            "restante_seguro_antes": restante_seguro,
            "detalhes_restantes_antes": detalhes_restantes,
            "limite_efetivo": limite,
        })
        return limite, diagnostico

    @staticmethod
    def _prioridade_enriquecimento_api(tarefa):
        idade = tarefa.get("idade_segundos")
        try:
            idade_numerica = float(idade) if idade is not None else None
        except (TypeError, ValueError):
            idade_numerica = None
        if tarefa.get("em_foco") or tarefa.get("pre_live_confirmado"):
            grupo = 0
        elif tarefa.get("pre_live_contexto_disponivel"):
            grupo = 1
        elif idade is None:
            grupo = 2
        elif idade_numerica is not None and 300 <= idade_numerica <= 480:
            grupo = 3
        else:
            grupo = 4
        return grupo

    def _enriquecer_fixtures_api_lote(self, tarefas, fixtures_api):
        fixtures_api = list(fixtures_api or [])
        limite, capacidade = self._limite_enriquecimento_api_lote()
        associacoes = []
        associacoes_tarefas = []
        ids_originais = {
            (item.get("fixture") or {}).get("id")
            for item in fixtures_api
            if isinstance(item, dict)
            and (item.get("fixture") or {}).get("id") is not None
        }
        restantes = list(fixtures_api)
        tarefas_ordenadas = sorted(
            enumerate(tarefas or []),
            key=lambda item: (
                self._prioridade_enriquecimento_api(item[1]), item[0]
            ),
        )
        ordens_tarefas = {
            id(tarefa): ordem for ordem, tarefa in tarefas_ordenadas
        }
        for _, tarefa in tarefas_ordenadas:
            diagnostico = diagnosticar_associacao(
                tarefa.get("jogo") or {},
                restantes,
            )
            associacao = diagnostico.get("associacao") or {}
            fixture_id = associacao.get("fixture_id")
            if fixture_id is None:
                continue
            tarefa["api_fixture_id_prioridade"] = fixture_id
            tarefa["api_orientacao_prioridade"] = (
                associacao.get("orientacao") or "direta"
            )
            associacoes.append(fixture_id)
            associacoes_tarefas.append((tarefa, fixture_id))
            restantes = [
                item for item in restantes
                if (item.get("fixture") or {}).get("id") != fixture_id
            ]
        # A lista global da API pode atrasar alguns minutos ou omitir uma
        # competicao. Quando a pre-live ja produziu causalmente um fixture_id
        # para o mesmo confronto, o lote detalhado tenta esse ID exato. A
        # resposta ainda sera revalidada por nome, placar, minuto e estado
        # ao vivo antes de entrar no conjunto usado pelo motor.
        dicas_pre_live = []
        ids_associados = set(associacoes)
        for tarefa in tarefas or []:
            jogo = tarefa.get("jogo") or {}
            if not jogo.get("pre_live_contexto_disponivel"):
                continue
            try:
                fixture_id = int(jogo.get("pre_live_fixture_id"))
            except (TypeError, ValueError):
                continue
            if fixture_id <= 0 or fixture_id in ids_associados:
                continue
            dicas_pre_live.append((tarefa, fixture_id))
            ids_associados.add(fixture_id)
        ofertas_asiaticas = {}
        listar_ofertas = getattr(
            type(self.api),
            "ofertas_escanteios_asiaticos_ft_por_fixture",
            None,
        )
        if callable(listar_ofertas) and associacoes_tarefas:
            try:
                ofertas_asiaticas = {
                    int(fixture_id): oferta
                    for fixture_id, oferta in (
                        listar_ofertas(self.api) or {}
                    ).items()
                    if isinstance(oferta, dict)
                }
            except Exception:
                # O lote detalhado é auxiliar; a prioridade principal fará
                # sua própria tentativa segura e nenhum sinal é liberado.
                ofertas_asiaticas = {}
        solicitacoes_tarefas = [
            (tarefa, fixture_id, "lista_ao_vivo")
            for tarefa, fixture_id in associacoes_tarefas
        ] + [
            (tarefa, fixture_id, "pre_live_causal")
            for tarefa, fixture_id in dicas_pre_live
        ]
        solicitacoes_tarefas.sort(key=lambda item: (
            self._prioridade_enriquecimento_api(item[0]),
            item[1] not in ofertas_asiaticas,
            ordens_tarefas.get(id(item[0]), 0),
        ))
        ids = list(dict.fromkeys(
            fixture_id
            for _tarefa, fixture_id, _origem in solicitacoes_tarefas
        ))[:limite]
        coletar = getattr(
            self.api, "fixtures_ao_vivo_detalhadas", None
        )
        diagnostico = {
            "associadas": len(associacoes),
            "solicitadas": len(ids),
            "adiadas_capacidade_api": max(
                len(set(associacoes)) - len(ids), 0
            ),
            "chamadas_maximas_estimadas": math.ceil(len(ids) / 20),
            "ofertas_asiaticas_disponiveis": len(ofertas_asiaticas),
            "solicitadas_com_oferta_asiatica": sum(
                fixture_id in ofertas_asiaticas for fixture_id in ids
            ),
            "dicas_pre_live_causais": len(dicas_pre_live),
            "dicas_pre_live_solicitadas": sum(
                fixture_id in ids for _tarefa, fixture_id in dicas_pre_live
            ),
            "dicas_pre_live_recuperadas": 0,
            "dicas_pre_live_rejeitadas": 0,
            "dicas_pre_live_adiadas_capacidade": sum(
                fixture_id not in ids
                for _tarefa, fixture_id in dicas_pre_live
            ),
            "dicas_pre_live_aplicacao_sinais_direta": False,
            "retornadas": 0,
            "incorporadas": 0,
            "stats_resgate_limite_ciclo": 0,
            "stats_resgate_selecionadas": 0,
            "stats_resgate_consultadas": 0,
            "stats_resgate_com_dados": 0,
            "stats_resgate_sem_dados": 0,
            "stats_resgate_erros": 0,
            "stats_resgate_aplicacao_sinais": False,
            "stats_resgate_rollback": "API_STATS_RESGATE_MAX_CICLO=0",
            "estado": (
                "sem_associacoes"
                if not associacoes else
                "adiado_capacidade_api"
                if not ids else
                "indisponivel"
            ),
            **capacidade,
        }
        if not ids or not callable(coletar):
            return fixtures_api, diagnostico
        try:
            detalhadas = coletar(ids)
        except Exception as erro:
            diagnostico["estado"] = "falha_isolada"
            diagnostico["erro"] = type(erro).__name__
            return fixtures_api, diagnostico
        if not isinstance(detalhadas, list):
            return fixtures_api, diagnostico
        por_id = {
            ((item.get("fixture") or {}).get("id")): item
            for item in detalhadas
            if isinstance(item, dict)
            and ((item.get("fixture") or {}).get("id")) is not None
        }
        dicas_validas = []
        codigos_ao_vivo = {
            "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE",
        }
        codigos_finais = {
            "NS", "TBD", "PST", "CANC", "ABD", "AWD", "WO",
            "FT", "AET", "PEN",
        }
        for tarefa, fixture_id in dicas_pre_live:
            if fixture_id not in ids:
                continue
            fixture = por_id.get(fixture_id)
            status = ((fixture or {}).get("fixture") or {}).get("status") or {}
            codigo = str(status.get("short") or "").strip().upper()
            try:
                minuto_api = float(status.get("elapsed"))
            except (TypeError, ValueError):
                minuto_api = None
            estado_ao_vivo = bool(
                codigo in codigos_ao_vivo
                or (
                    codigo not in codigos_finais
                    and minuto_api is not None and minuto_api > 0
                )
            )
            if fixture is None or not estado_ao_vivo:
                diagnostico["dicas_pre_live_rejeitadas"] += 1
                continue
            validacao = diagnosticar_associacao(
                tarefa.get("jogo") or {}, [fixture]
            )
            associacao = validacao.get("associacao") or {}
            if associacao.get("fixture_id") != fixture_id:
                diagnostico["dicas_pre_live_rejeitadas"] += 1
                continue
            tarefa["api_fixture_id_prioridade"] = fixture_id
            tarefa["api_orientacao_prioridade"] = (
                associacao.get("orientacao") or "direta"
            )
            dicas_validas.append((tarefa, fixture_id))
        diagnostico["dicas_pre_live_recuperadas"] = len(dicas_validas)
        associacoes_tarefas.extend(dicas_validas)
        try:
            limite_stats_resgate = int(os.getenv(
                "API_STATS_RESGATE_MAX_CICLO", "2"
            ))
        except (TypeError, ValueError):
            limite_stats_resgate = 2
        limite_stats_resgate = max(0, min(limite_stats_resgate, 5))
        restante_seguro = capacidade.get("restante_seguro_antes")
        detalhes_restantes = capacidade.get("detalhes_restantes_antes")
        if restante_seguro is None or restante_seguro < 500:
            limite_stats_resgate = 0
        if detalhes_restantes is not None:
            limite_stats_resgate = min(
                limite_stats_resgate, max(int(detalhes_restantes), 0)
            )
        coletar_stats = getattr(self.api, "estatisticas", None)
        alvos_stats = []
        for tarefa, fixture_id in associacoes_tarefas:
            if len(alvos_stats) >= limite_stats_resgate:
                break
            if fixture_id not in por_id or fixture_id not in ids:
                continue
            if fixture_id in alvos_stats:
                continue
            if not elegivel_coleta_resgate_qualidade(
                tarefa.get("jogo") or {}
            ):
                continue
            if (por_id[fixture_id].get("statistics") or []):
                continue
            alvos_stats.append(fixture_id)
        diagnostico.update({
            "stats_resgate_limite_ciclo": limite_stats_resgate,
            "stats_resgate_selecionadas": len(alvos_stats),
            "stats_resgate_consultadas": 0,
            "stats_resgate_com_dados": 0,
            "stats_resgate_sem_dados": 0,
            "stats_resgate_erros": 0,
            "stats_resgate_aplicacao_sinais": False,
            "stats_resgate_rollback": "API_STATS_RESGATE_MAX_CICLO=0",
        })
        if callable(coletar_stats):
            for fixture_id in alvos_stats:
                diagnostico["stats_resgate_consultadas"] += 1
                try:
                    estatisticas_live = coletar_stats(fixture_id)
                except Exception:
                    diagnostico["stats_resgate_erros"] += 1
                    continue
                if not isinstance(estatisticas_live, list) or not (
                    estatisticas_live
                ):
                    diagnostico["stats_resgate_sem_dados"] += 1
                    continue
                fixture_enriquecida = copy.deepcopy(por_id[fixture_id])
                fixture_enriquecida["statistics"] = estatisticas_live
                por_id[fixture_id] = fixture_enriquecida
                diagnostico["stats_resgate_com_dados"] += 1
        enriquecidas = []
        for item in fixtures_api:
            fixture_id = (item.get("fixture") or {}).get("id")
            enriquecidas.append(por_id.get(fixture_id, item))
        for _tarefa, fixture_id in dicas_validas:
            if fixture_id not in ids_originais and fixture_id in por_id:
                enriquecidas.append(por_id[fixture_id])
                ids_originais.add(fixture_id)
        ids_enriquecidos = {
            (item.get("fixture") or {}).get("id")
            for item in enriquecidas if isinstance(item, dict)
        }
        diagnostico["retornadas"] = len(por_id)
        diagnostico["incorporadas"] = sum(
            fixture_id in ids_enriquecidos for fixture_id in set(ids)
        )
        diagnostico["estado"] = (
            "completo"
            if diagnostico["incorporadas"] == diagnostico["solicitadas"]
            else "parcial"
        )
        return enriquecidas, diagnostico

    def _persistir_historico_api_live_lote(self, tarefas, fixtures_api):
        """Guarda o lote já obtido como série auxiliar, sem novas consultas."""
        salvar = getattr(self.banco, "salvar_historico_api_live", None)
        if not callable(salvar):
            return {
                "saudavel": False,
                "estado": "persistencia_indisponivel",
                "aplicacao_sinais": False,
                "chamadas_api_adicionais": 0,
                "navegacoes_packball_adicionais": 0,
            }
        tarefas_por_fixture = {}
        for tarefa in tarefas or []:
            fixture_id = tarefa.get("api_fixture_id_prioridade")
            if fixture_id is not None:
                tarefas_por_fixture[fixture_id] = tarefa
        coletado_em = datetime.now().replace(microsecond=0)
        registros = []
        for fixture in fixtures_api or []:
            fixture_id = (fixture.get("fixture") or {}).get("id")
            tarefa = tarefas_por_fixture.get(fixture_id)
            if tarefa is None:
                continue
            registro = normalizar_snapshot_api_live(
                fixture,
                (tarefa.get("jogo") or {}).get("url"),
                orientacao=tarefa.get(
                    "api_orientacao_prioridade", "direta"
                ),
                coletado_em=coletado_em,
            )
            if registro is not None:
                registros.append(registro)
        try:
            diagnostico = salvar(registros, agora=coletado_em)
        except Exception as erro:
            return {
                "saudavel": False,
                "estado": "falha_isolada",
                "erro": type(erro).__name__,
                "recebidos": len(registros),
                "aplicacao_sinais": False,
                "chamadas_api_adicionais": 0,
                "navegacoes_packball_adicionais": 0,
            }
        return {
            **dict(diagnostico or {}),
            "normalizados": len(registros),
            "aplicacao_sinais": False,
            "chamadas_api_adicionais": 0,
            "navegacoes_packball_adicionais": 0,
        }

    def _anexar_historico_api_live_contexto(
        self, contexto, confirmacao_api, jogo, evolucao_packball,
        instante=None,
    ):
        """Anexa comparação temporal somente ao contexto de pesquisa."""
        if not isinstance(contexto, dict):
            return contexto
        fixture_id = (confirmacao_api or {}).get("fixture_id")
        packball_url = (jogo or {}).get("url")
        if fixture_id is None or not packball_url:
            return contexto
        try:
            evolucao_api = obter_evolucao_api_live(
                self.banco.conexao,
                fixture_id,
                packball_url,
                agora=instante,
            )
            comparacao = comparar_evolucoes_packball_api(
                evolucao_packball, evolucao_api
            )
            contexto["evolucao_temporal_api_live"] = evolucao_api
            contexto["comparacao_temporal_packball_api"] = comparacao
            cobertura = contexto.setdefault("cobertura", {})
            cobertura["evolucao_temporal_api_live"] = any(
                isinstance(evolucao_api.get(str(janela)), dict)
                for janela in (5, 10, 15)
            )
            cobertura["comparacao_temporal_packball_api"] = (
                comparacao.get("total", 0) > 0
            )
        except Exception as erro:
            contexto["historico_api_live_diagnostico"] = {
                "estado": "falha_isolada",
                "erro": type(erro).__name__,
                "aplicacao_sinais": False,
            }
        return contexto

    @staticmethod
    def _numero_estatistica_api(valor):
        if isinstance(valor, bool) or valor is None:
            return 0.0
        try:
            return max(float(str(valor).replace("%", "").strip()), 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _total_escanteios_fixture_api(cls, fixture):
        """Soma cantos apenas quando os dois lados estão informados."""
        if not isinstance(fixture, dict):
            return None
        valores = []
        for bloco_time in fixture.get("statistics") or []:
            if not isinstance(bloco_time, dict):
                continue
            encontrado = False
            for item in bloco_time.get("statistics") or []:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "Corner Kicks"
                    and item.get("value") is not None
                ):
                    valores.append(
                        cls._numero_estatistica_api(item.get("value"))
                    )
                    encontrado = True
                    break
            if not encontrado:
                return None
        if len(valores) != 2:
            return None
        return round(sum(valores), 3)

    @classmethod
    def _pontuar_prioridade_fixture_api(cls, fixture):
        if not isinstance(fixture, dict):
            return None, False
        bloco_fixture = fixture.get("fixture") or {}
        status = bloco_fixture.get("status") or {}
        minuto = cls._numero_estatistica_api(status.get("elapsed"))
        estatisticas = fixture.get("statistics") or []
        tem_estatisticas = bool(
            isinstance(estatisticas, list) and estatisticas
        )
        if minuto <= 0 and not tem_estatisticas:
            return None, False

        totais = {
            "Shots on Goal": 0.0,
            "Total Shots": 0.0,
            "Corner Kicks": 0.0,
            "expected_goals": 0.0,
        }
        for bloco_time in estatisticas if tem_estatisticas else []:
            if not isinstance(bloco_time, dict):
                continue
            for item in bloco_time.get("statistics") or []:
                if not isinstance(item, dict):
                    continue
                tipo = item.get("type")
                if tipo in totais:
                    totais[tipo] += cls._numero_estatistica_api(
                        item.get("value")
                    )

        if 12 <= minuto <= 42 or 50 <= minuto <= 82:
            janela = 20.0
        elif 10 <= minuto <= 87:
            janela = 8.0
        else:
            janela = -20.0
        pontuacao = (
            janela
            + (20.0 if tem_estatisticas else 0.0)
            + min(totais["Shots on Goal"], 10.0) * 4.0
            + min(totais["Total Shots"], 24.0)
            + min(totais["Corner Kicks"], 14.0) * 2.0
            + min(totais["expected_goals"], 5.0) * 5.0
        )
        return round(pontuacao, 3), tem_estatisticas

    def _janelas_temporais_projetadas(self, tarefa, agora=None):
        """Prevê quais janelas a próxima leitura conseguirá fechar."""
        agora = agora or datetime.now()
        jogo = tarefa.get("jogo") or {}
        url = jogo.get("url")
        historico_obj = getattr(self, "historico", None)
        historico = getattr(historico_obj, "partidas", None)
        if not isinstance(historico, dict):
            # Compatibilidade conservadora para chamadas isoladas e para a
            # partida ainda não restaurada em memória.
            try:
                idade = float(tarefa.get("idade_segundos"))
            except (TypeError, ValueError):
                return set()
            return {5} if 300 <= idade <= 480 else set()

        itens = historico.get(url) or []
        periodo_atual = periodo_partida(jogo.get("status"))
        idades_minutos = []
        for item in itens:
            instante = item.get("instante") if isinstance(item, dict) else None
            if not isinstance(instante, datetime):
                continue
            periodo_item = item.get("periodo")
            if (
                periodo_atual
                and periodo_item
                and periodo_item != periodo_atual
            ):
                continue
            idade = (agora - instante).total_seconds() / 60
            if 0 < idade <= 20:
                idades_minutos.append(idade)
        return {
            alvo
            for alvo in (5, 10, 15)
            if any(alvo <= idade <= alvo + 3 for idade in idades_minutos)
        }

    def _priorizar_tarefas_por_api(self, tarefas, fixtures_api):
        """Ordena exploração com dados já coletados, sem criar sinal."""
        tarefas = list(tarefas or [])
        tarefas_agendador = list(tarefas)
        consulta_odds_api_executada = False
        consulta_odds_api_falhou = False
        fixtures_odds_asiaticas = set()
        ofertas_odds_asiaticas = {}
        api_obj = getattr(self, "api", None)
        listar_ofertas = getattr(
            type(api_obj),
            "ofertas_escanteios_asiaticos_ft_por_fixture",
            None,
        )
        listar_odds = getattr(
            type(api_obj),
            "fixtures_com_odds_escanteios_asiaticos_ft",
            None,
        )
        if callable(listar_ofertas) and tarefas:
            consulta_odds_api_executada = True
            try:
                ofertas_odds_asiaticas = {
                    int(fixture_id): dict(oferta)
                    for fixture_id, oferta in (
                        listar_ofertas(api_obj) or {}
                    ).items()
                    if isinstance(oferta, dict)
                }
                fixtures_odds_asiaticas = set(ofertas_odds_asiaticas)
            except Exception:
                # Priorização auxiliar nunca derruba nem libera um sinal.
                consulta_odds_api_falhou = True
                fixtures_odds_asiaticas = set()
                ofertas_odds_asiaticas = {}
        elif callable(listar_odds) and tarefas:
            consulta_odds_api_executada = True
            try:
                fixtures_odds_asiaticas = {
                    int(item)
                    for item in (listar_odds(api_obj) or set())
                }
            except Exception:
                consulta_odds_api_falhou = True
                fixtures_odds_asiaticas = set()
        por_id = {
            (item.get("fixture") or {}).get("id"): item
            for item in fixtures_api or []
            if isinstance(item, dict)
            and (item.get("fixture") or {}).get("id") is not None
        }
        com_estatisticas = 0
        pontuadas = 0
        for ordem, tarefa in enumerate(tarefas):
            tarefa["ordem_agendador"] = ordem
            fixture = por_id.get(tarefa.get("api_fixture_id_prioridade"))
            status_fixture = (fixture or {}).get("fixture") or {}
            status_fixture = status_fixture.get("status") or {}
            tarefa["minuto_prioridade_api"] = status_fixture.get("elapsed")
            pontuacao, tem_estatisticas = (
                self._pontuar_prioridade_fixture_api(fixture)
            )
            tarefa["prioridade_api_lote"] = pontuacao
            try:
                fixture_prioridade = int(
                    tarefa.get("api_fixture_id_prioridade")
                )
            except (TypeError, ValueError):
                fixture_prioridade = None
            tarefa["odd_asiatica_api_disponivel"] = bool(
                fixture_prioridade in fixtures_odds_asiaticas
            )
            oferta_asiatica = ofertas_odds_asiaticas.get(
                fixture_prioridade
            )
            total_escanteios_api = self._total_escanteios_fixture_api(
                fixture
            )
            try:
                linha_asiatica = float(
                    (oferta_asiatica or {}).get("linha")
                )
            except (TypeError, ValueError):
                linha_asiatica = None
            tarefa["linha_asiatica_api"] = linha_asiatica
            tarefa["escanteios_atuais_api"] = total_escanteios_api
            tarefa["odd_asiatica_api_alvo_um_escanteio"] = bool(
                linha_asiatica is not None
                and total_escanteios_api is not None
                and total_escanteios_api
                <= linha_asiatica
                <= total_escanteios_api + 0.5
            )
            pontuadas += pontuacao is not None
            com_estatisticas += tem_estatisticas

        def dentro_janela_prioridade(item):
            status = str(
                (item.get("jogo") or {}).get("status") or ""
            ).strip().lower()
            if status == "ht" or "intervalo" in status:
                return False
            minuto = extrair_minuto(status)
            return (
                minuto is None
                or minuto <= MINUTO_MAXIMO_PRIORIDADE_SINAIS
            )

        def minuto_prioridade(item):
            minuto = extrair_minuto(
                (item.get("jogo") or {}).get("status")
            )
            if minuto is None:
                try:
                    minuto = int(item.get("minuto_prioridade_api"))
                except (TypeError, ValueError):
                    return None
            return minuto

        def base_gol_ht_ativa(item):
            minuto = minuto_prioridade(item)
            return minuto is not None and 10 <= minuto <= 22

        def janela_gol_ht_ativa(item):
            minuto = minuto_prioridade(item)
            return minuto is not None and 10 <= minuto <= 28

        def acionavel_mercado_ativo(item):
            """Confirma que ainda existe ao menos uma janela operacional."""
            status = str(
                (item.get("jogo") or {}).get("status") or ""
            ).strip().lower()
            if status == "ht" or "intervalo" in status:
                return False
            minuto = minuto_prioridade(item)
            return (
                minuto is not None
                and minuto <= MINUTO_MAXIMO_PRIORIDADE_SINAIS
            )

        # Esta e a prioridade primaria. Foco, revisitas temporais, API e
        # atraso continuam ordenando estavelmente dentro de cada grupo, mas
        # nao devem consumir o orcamento antes de uma partida ainda acionavel.
        for item in tarefas:
            item["acionavel_fila_detalhada"] = (
                acionavel_mercado_ativo(item)
            )
        tarefas_acionaveis = [
            item for item in tarefas
            if item["acionavel_fila_detalhada"]
        ]
        tarefas_fora_janelas_ativas = [
            item for item in tarefas
            if not item["acionavel_fila_detalhada"]
        ]
        tarefas = tarefas_acionaveis + tarefas_fora_janelas_ativas

        tarefas_no_intervalo = sum(
            1 for item in tarefas
            if (
                str((item.get("jogo") or {}).get("status") or "")
                .strip().lower() == "ht"
                or "intervalo" in str(
                    (item.get("jogo") or {}).get("status") or ""
                ).strip().lower()
            )
        )

        focos_fora_janela = [
            item for item in tarefas
            if item.get("em_foco") and not dentro_janela_prioridade(item)
        ]
        for item in focos_fora_janela:
            # A partida continua na fila normal e pode ser visitada pelo
            # resgate de atraso. Apenas deixa de consumir a vaga reservada a
            # jogos que ainda podem produzir algum mercado operacional.
            item["em_foco"] = False
        focos = [item for item in tarefas if item.get("em_foco")]
        exploracao = [item for item in tarefas if not item.get("em_foco")]

        def idade_valida(item):
            try:
                idade = float(item.get("idade_segundos"))
            except (TypeError, ValueError):
                return None
            return idade if math.isfinite(idade) and idade >= 0 else None

        def radar_lista(item):
            try:
                valor = float(item.get("pontuacao_indicadores_lista") or 0)
            except (TypeError, ValueError):
                return 0.0
            return valor if math.isfinite(valor) and valor > 0 else 0.0

        def score_liga_gols(item):
            try:
                valor = float(item.get("prioridade_liga_gols") or 0)
            except (TypeError, ValueError):
                return 0.0
            return valor if math.isfinite(valor) and valor > 0 else 0.0

        # Sob congestionamento, as prioridades de exploracao, janelas e API
        # podem ocupar todas as vagas do ciclo. Reserva uma unica vaga para
        # a partida mais atrasada, sem ampliar o numero de navegacoes.
        atrasadas = [
            item for item in tarefas
            if (idade_valida(item) or 0) > 20 * 60
        ]
        atrasadas_acionaveis = [
            item for item in atrasadas
            if item.get("acionavel_fila_detalhada")
        ]
        candidatas_atraso = atrasadas_acionaveis or atrasadas
        reservada_atrasada = (
            max(
                candidatas_atraso,
                key=lambda item: (
                    idade_valida(item) or 0.0,
                    -item["ordem_agendador"],
                ),
            )
            if candidatas_atraso else None
        )
        if reservada_atrasada in focos:
            focos.remove(reservada_atrasada)
        elif reservada_atrasada in exploracao:
            exploracao.remove(reservada_atrasada)
        reservada_periodica = None
        if focos and tarefas and tarefas[0] in exploracao:
            # Preserva a vaga periódica de exploração criada pelo
            # agendador para que a otimização não cause starvation.
            reservada_periodica = tarefas[0]
        novas = [
            item for item in exploracao
            if "idade_segundos" in item
            and item.get("idade_segundos") is None
            and dentro_janela_prioridade(item)
        ]
        reservada_nova = (
            max(
                novas,
                key=lambda item: (
                    base_gol_ht_ativa(item),
                    score_liga_gols(item),
                    radar_lista(item),
                    item.get(
                        "odd_asiatica_api_alvo_um_escanteio", False
                    ),
                    item.get("prioridade_api_lote") is not None,
                    item.get("prioridade_api_lote") or 0.0,
                    # Oferta generica serve apenas para pesquisa/desempate;
                    # o boost operacional exige alvo de mais um escanteio.
                    item.get("odd_asiatica_api_disponivel", False),
                    -item["ordem_agendador"],
                ),
            )
            if novas else None
        )
        # Uma leitura inedita cria a base das janelas temporais e aumenta a
        # amostra independente sem elevar o numero de navegacoes do ciclo.
        reservada = reservada_nova or reservada_periodica
        if reservada is not None:
            exploracao.remove(reservada)
        agora_temporal = datetime.now()
        for item in tarefas:
            item["janelas_temporais_projetadas"] = sorted(
                self._janelas_temporais_projetadas(
                    item, agora=agora_temporal
                )
            )

        def janelas_projetadas(item):
            return set(item.get("janelas_temporais_projetadas") or [])

        # A janela de 5 minutos e o requisito minimo comum do motor de
        # sinais. Entre jogos ja classificados como foco, processa primeiro
        # aquele que consegue fecha-la agora; a ordem original continua como
        # desempate e preserva a pontuacao anterior.
        focos.sort(
            key=lambda item: (
                not item.get("rechecagem_pos_evento", False),
                5 not in janelas_projetadas(item),
                -score_liga_gols(item),
                -radar_lista(item),
                not item.get("prioridade_exploracao_gols", False),
                not item.get(
                    "odd_asiatica_api_alvo_um_escanteio", False
                ),
                not item.get("odd_asiatica_api_disponivel", False),
            )
        )
        foco_ja_temporal = any(
            janelas_projetadas(item) for item in focos
        )
        foco_ja_temporal_5 = any(
            5 in janelas_projetadas(item) for item in focos
        )
        foco_ja_temporal_longo = any(
            janelas_projetadas(item) & {10, 15} for item in focos
        )
        candidatas_temporais = [
            item for item in exploracao
            if janelas_projetadas(item) and dentro_janela_prioridade(item)
        ]
        candidatas_temporais_longas = [
            item for item in candidatas_temporais
            if janelas_projetadas(item) & {10, 15}
        ]
        # Com quatro a cinco detalhes por ciclo, quinze tarefas ja deixam a
        # cobertura perto de 25%-33% e justificam reforcar as revisitas.
        carga_alta = len(tarefas) >= 15
        reservadas_temporais = []
        if carga_alta:
            atrasada_ja_temporal_5 = bool(
                reservada_atrasada is not None
                and 5 in janelas_projetadas(reservada_atrasada)
            )
            cobertura_existente = sum((
                bool(foco_ja_temporal),
                bool(
                    reservada_atrasada is not None
                    and janelas_projetadas(reservada_atrasada)
                ),
            ))
            quantidade = max(2 - cobertura_existente, 0)
            disponiveis = list(candidatas_temporais)
            # Duas janelas longas nao substituem a janela minima de 5 min.
            # Se nenhuma vaga ja reservada fecha 5 min, garante uma candidata
            # de 5 min sem aumentar o numero total de navegacoes.
            if (
                not foco_ja_temporal_5
                and not atrasada_ja_temporal_5
                and any(5 in janelas_projetadas(item) for item in disponiveis)
            ):
                quantidade = max(quantidade, 1)
            for _ in range(quantidade):
                if not disponiveis:
                    break
                cinco_ja_coberto = bool(
                    foco_ja_temporal_5
                    or atrasada_ja_temporal_5
                    or any(
                        5 in janelas_projetadas(item)
                        for item in reservadas_temporais
                    )
                )
                cinco = [
                    item for item in disponiveis
                    if 5 in janelas_projetadas(item)
                ]
                longas = [
                    item for item in disponiveis
                    if janelas_projetadas(item) & {10, 15}
                ]
                grupo = cinco if cinco and not cinco_ja_coberto else (
                    longas or cinco or disponiveis
                )
                escolhida = max(
                    grupo,
                    key=lambda item: (
                        janela_gol_ht_ativa(item),
                        score_liga_gols(item),
                        radar_lista(item),
                        item.get("prioridade_exploracao_gols", False),
                        item.get(
                            "odd_asiatica_api_alvo_um_escanteio", False
                        ),
                        15 in janelas_projetadas(item),
                        10 in janelas_projetadas(item),
                        5 in janelas_projetadas(item),
                        bool(item.get("coletar_odds")),
                        item.get("prioridade_api_lote") or 0.0,
                        item.get("odd_asiatica_api_disponivel", False),
                        -item["ordem_agendador"],
                    ),
                )
                reservadas_temporais.append(escolhida)
                disponiveis.remove(escolhida)
                exploracao.remove(escolhida)
        else:
            if candidatas_temporais_longas and not foco_ja_temporal_longo:
                candidatas_para_reserva = candidatas_temporais_longas
            elif not foco_ja_temporal:
                candidatas_para_reserva = candidatas_temporais
            else:
                candidatas_para_reserva = []
            if candidatas_para_reserva:
                reservada_temporal = max(
                    candidatas_para_reserva,
                    key=lambda item: (
                        janela_gol_ht_ativa(item),
                        score_liga_gols(item),
                        radar_lista(item),
                        item.get("prioridade_exploracao_gols", False),
                        item.get(
                            "odd_asiatica_api_alvo_um_escanteio", False
                        ),
                        15 in janelas_projetadas(item),
                        10 in janelas_projetadas(item),
                        5 in janelas_projetadas(item),
                        bool(item.get("coletar_odds")),
                        item.get("prioridade_api_lote") or 0.0,
                        item.get("odd_asiatica_api_disponivel", False),
                        -item["ordem_agendador"],
                    ),
                )
                reservadas_temporais.append(reservada_temporal)
                exploracao.remove(reservada_temporal)

        reservada_oportunidade = None
        if carga_alta:
            candidatas_oportunidade = [
                item for item in exploracao
                if item.get("prioridade_api_lote") is not None
                and dentro_janela_prioridade(item)
            ]
            if candidatas_oportunidade:
                reservada_oportunidade = max(
                    candidatas_oportunidade,
                    key=lambda item: (
                        janela_gol_ht_ativa(item),
                        score_liga_gols(item),
                        radar_lista(item),
                        item.get(
                            "odd_asiatica_api_alvo_um_escanteio", False
                        ),
                        item.get("prioridade_api_lote") or 0.0,
                        bool(item.get("coletar_odds")),
                        item.get("odd_asiatica_api_disponivel", False),
                        -item["ordem_agendador"],
                    ),
                )
                exploracao.remove(reservada_oportunidade)
        exploracao.sort(key=lambda item: (
            not item.get(
                "odd_asiatica_api_alvo_um_escanteio", False
            ),
            -score_liga_gols(item),
            -radar_lista(item),
            item.get("prioridade_api_lote") is None,
            not bool(item.get("coletar_odds")),
            -(item.get("prioridade_api_lote") or 0.0),
            not item.get("odd_asiatica_api_disponivel", False),
            item["ordem_agendador"],
        ))
        prefixo_atrasada = (
            [reservada_atrasada]
            if reservada_atrasada is not None else []
        )
        prefixo_nova = [reservada] if reservada is not None else []
        prefixo_oportunidade = (
            [reservada_oportunidade]
            if reservada_oportunidade is not None else []
        )
        if carga_alta:
            # Em producao o orcamento costuma comportar apenas tres ou quatro
            # detalhes. As reservas de exploracao nao podem consumir todas as
            # vagas antes de um jogo que o motor ja classificou como foco.
            foco_prioritario = focos.pop(0) if focos else None
            prefixo_foco = (
                [foco_prioritario]
                if foco_prioritario is not None else []
            )
            primeira_temporal = reservadas_temporais[:1]
            demais_temporais = reservadas_temporais[1:]
            if foco_prioritario is not None:
                if prefixo_atrasada:
                    ordenadas = (
                        prefixo_foco + primeira_temporal
                        + prefixo_atrasada + demais_temporais
                        + prefixo_oportunidade + prefixo_nova
                        + focos + exploracao
                    )
                else:
                    ordenadas = (
                        prefixo_foco + reservadas_temporais
                        + prefixo_oportunidade + prefixo_nova + focos
                        + exploracao
                    )
            else:
                if prefixo_atrasada:
                    ordenadas = (
                        prefixo_oportunidade + primeira_temporal
                        + prefixo_atrasada + prefixo_nova
                        + demais_temporais + exploracao
                    )
                else:
                    ordenadas = (
                        prefixo_oportunidade + prefixo_nova
                        + reservadas_temporais + exploracao
                    )
        else:
            foco_prioritario = None
            ordenadas = (
                prefixo_atrasada + prefixo_nova
                + reservadas_temporais + focos + exploracao
            )
        reservas_gol_ht = []
        reservas_gol_ht.extend(
            item for item in reservadas_temporais
            if janela_gol_ht_ativa(item)
        )
        if (
            reservada_nova is not None
            and base_gol_ht_ativa(reservada_nova)
        ):
            reservas_gol_ht.append(reservada_nova)
        if (
            reservada_oportunidade is not None
            and janela_gol_ht_ativa(reservada_oportunidade)
        ):
            reservas_gol_ht.append(reservada_oportunidade)
        prioridade_gol_ht = next(
            (
                item for item in reservas_gol_ht
                if item in ordenadas
            ),
            None,
        )
        if prioridade_gol_ht is not None:
            # O mercado HT vence primeiro. Promover uma única reserva garante
            # execução no orçamento real de quatro detalhes sem aumentar a
            # cardinalidade nem retirar foco e resgate da fila antiga.
            ordenadas.remove(prioridade_gol_ht)
            posicao = (
                1
                if (
                    foco_prioritario is not None
                    or reservada_atrasada is not None
                )
                else 0
            )
            ordenadas.insert(posicao, prioridade_gol_ht)
            if (
                foco_prioritario is not None
                and reservada_atrasada is not None
                and ordenadas.index(reservada_atrasada) > 2
            ):
                ordenadas.remove(reservada_atrasada)
                ordenadas.insert(2, reservada_atrasada)

        # As reservas acima preservam a politica historica entre jogos
        # acionaveis. Esta particao final impede que uma prioridade auxiliar
        # de intervalo/87+ volte a ultrapassa-los.
        ordenadas_auxiliares = list(ordenadas)
        ordenadas = [
            item for item in ordenadas_auxiliares
            if item.get("acionavel_fila_detalhada")
        ] + [
            item for item in ordenadas_auxiliares
            if not item.get("acionavel_fila_detalhada")
        ]
        # A otimização por API acontece depois do Agendador e pode reordenar
        # toda a fila. Reaplica aqui a garantia pré-live sem aumentar o lote:
        # confirmado fica logo após um foco já estabelecido; publicado ainda
        # sem confirmação recebe uma única vaga entre as quatro primeiras.
        pre_live_acionaveis = [
            item for item in ordenadas
            if item.get("pre_live_prioritario")
            and item.get("acionavel_fila_detalhada")
        ]
        pre_live_confirmados = [
            item for item in pre_live_acionaveis
            if item.get("pre_live_confirmado")
        ]
        prioridade_pre_live = None
        tipo_prioridade_pre_live = None
        if pre_live_confirmados:
            prioridade_pre_live = min(
                pre_live_confirmados,
                key=lambda item: item.get("ordem_agendador", 10**9),
            )
            ordenadas.remove(prioridade_pre_live)
            posicao = 1 if ordenadas and ordenadas[0].get("em_foco") else 0
            ordenadas.insert(posicao, prioridade_pre_live)
            tipo_prioridade_pre_live = "confirmado"
        elif (
            pre_live_acionaveis
            and not any(
                item.get("pre_live_prioritario")
                for item in ordenadas[:4]
            )
        ):
            prioridade_pre_live = min(
                pre_live_acionaveis,
                key=lambda item: item.get("ordem_agendador", 10**9),
            )
            ordenadas.remove(prioridade_pre_live)
            ordenadas.insert(min(3, len(ordenadas)), prioridade_pre_live)
            tipo_prioridade_pre_live = "publicado"

        # Em carga alta, as reservas historicas de foco, janelas temporais e
        # API podem preencher todo o pequeno lote real. Garante uma unica
        # vaga entre as quatro primeiras para a melhor taxa sazonal ainda
        # acionavel. Isso apenas decide qual detalhe abrir primeiro: a taxa da
        # liga nunca aprova, rejeita nem altera um sinal.
        prioridade_liga_gols_reservada = None
        if carga_alta:
            candidatas_liga_gols = [
                item for item in ordenadas
                if item.get("acionavel_fila_detalhada")
                and score_liga_gols(item) > 0
                and (
                    minuto_prioridade(item) is None
                    or minuto_prioridade(item)
                    <= MINUTO_MAXIMO_PRIORIDADE_LIGAS_GOLS
                )
            ]
            if candidatas_liga_gols:
                melhor_liga_gols = max(
                    candidatas_liga_gols,
                    key=lambda item: (
                        score_liga_gols(item),
                        radar_lista(item),
                        bool(item.get("prioridade_api_lote") is not None),
                        item.get("prioridade_api_lote") or 0.0,
                        -item.get("ordem_agendador", 10**9),
                    ),
                )
                if melhor_liga_gols not in ordenadas[:4]:
                    ordenadas.remove(melhor_liga_gols)

                    def protecao_reserva(item):
                        return (
                            4 if item.get("rechecagem_pos_evento") else
                            4 if item.get("pre_live_confirmado") else
                            3 if item.get("em_foco") else
                            2 if item.get("pre_live_prioritario") else
                            2 if item.get("janelas_temporais_projetadas") else
                            1
                        )

                    faixa = list(range(1, min(4, len(ordenadas))))
                    posicao = (
                        min(
                            faixa,
                            key=lambda indice: (
                                protecao_reserva(ordenadas[indice]),
                                -indice,
                            ),
                        )
                        if faixa else min(3, len(ordenadas))
                    )
                    ordenadas.insert(posicao, melhor_liga_gols)
                    melhor_liga_gols["reserva_liga_gols"] = True
                    prioridade_liga_gols_reservada = melhor_liga_gols

        # A leitura de preco posterior a um alerta tem prazo curto (2–10
        # minutos) e serve para medir valor executavel, mesmo quando a partida
        # ja saiu da janela de novos sinais. A particao por acionabilidade
        # acima podia empurra-la para o fim da fila e o pequeno lote real nao
        # chegava a processa-la. Reserva uma unica vaga entre as tres primeiras
        # sem aumentar a quantidade de navegacoes; entre varios acompanhamentos
        # vence o mais perto de expirar.
        acompanhamentos_preco_disponiveis = [
            item for item in ordenadas
            if item.get("acompanhamento_preco") is True
        ]

        def idade_acompanhamento_preco(item):
            dados = item.get("acompanhamento_preco_dados") or {}
            try:
                idade = float(dados.get("idade_segundos"))
            except (TypeError, ValueError):
                return -1.0
            return idade if math.isfinite(idade) and idade >= 0 else -1.0

        acompanhamento_preco_reservado = (
            max(
                acompanhamentos_preco_disponiveis,
                key=lambda item: (
                    idade_acompanhamento_preco(item),
                    -item.get("ordem_agendador", 10**9),
                ),
            )
            if acompanhamentos_preco_disponiveis else None
        )
        if (
            acompanhamento_preco_reservado is not None
            and acompanhamento_preco_reservado not in ordenadas[:3]
        ):
            indice_reservado = ordenadas.index(
                acompanhamento_preco_reservado
            )

            def protecao_posicao_preco(item):
                return (
                    6 if item.get("rechecagem_pos_evento") else
                    5 if item is prioridade_gol_ht else
                    5 if item.get("pre_live_confirmado") else
                    4 if item.get("em_foco") else
                    3 if item.get("pre_live_prioritario") else
                    2 if item.get("reserva_liga_gols") else
                    1 if item.get("janelas_temporais_projetadas") else
                    0
                )

            faixa_troca = range(1, min(3, len(ordenadas)))
            posicao = (
                min(
                    faixa_troca,
                    key=lambda indice: (
                        protecao_posicao_preco(ordenadas[indice]),
                        -indice,
                    ),
                )
                if len(ordenadas) > 1 else 0
            )
            ordenadas[indice_reservado], ordenadas[posicao] = (
                ordenadas[posicao], ordenadas[indice_reservado]
            )
            acompanhamento_preco_reservado[
                "reserva_acompanhamento_preco"
            ] = True
        prioridade_acionaveis_aplicada = any(
            item is not ordenadas_auxiliares[indice]
            for indice, item in enumerate(ordenadas)
        )
        reordenadas = sum(
            tarefa is not tarefas_agendador[indice]
            for indice, tarefa in enumerate(ordenadas)
        )
        pontos = [
            item["prioridade_api_lote"] for item in tarefas
            if item.get("prioridade_api_lote") is not None
        ]
        pontos_radar = [radar_lista(item) for item in tarefas]
        pontos_ligas = [score_liga_gols(item) for item in tarefas]
        campos_radar = sorted({
            str(chave)
            for item in tarefas
            for chave in (
                (((item.get("jogo") or {}).get("indicadores_lista") or {})
                 .get("campos") or {})
            )
        })
        return ordenadas, {
            "tarefas": len(tarefas),
            "associadas_pontuadas": pontuadas,
            "com_estatisticas": com_estatisticas,
            "reordenadas": reordenadas,
            "maior_pontuacao": max(pontos) if pontos else None,
            "indicadores_lista_disponiveis": sum(
                valor > 0 for valor in pontos_radar
            ),
            "maior_pontuacao_indicadores_lista": (
                max(pontos_radar) if pontos_radar else None
            ),
            "indicadores_lista_nas_quatro_primeiras": sum(
                radar_lista(item) > 0 for item in ordenadas[:4]
            ),
            "ligas_gols_pontuadas": sum(
                valor > 0 for valor in pontos_ligas
            ),
            "maior_pontuacao_liga_gols": (
                max(pontos_ligas) if pontos_ligas else None
            ),
            "ligas_gols_nas_quatro_primeiras": sum(
                score_liga_gols(item) > 0 for item in ordenadas[:4]
            ),
            "liga_gols_reservada": (
                prioridade_liga_gols_reservada is not None
            ),
            "liga_gols_reservada_score": (
                score_liga_gols(prioridade_liga_gols_reservada)
                if prioridade_liga_gols_reservada is not None else None
            ),
            "liga_gols_reservada_nas_quatro_primeiras": bool(
                prioridade_liga_gols_reservada is not None
                and prioridade_liga_gols_reservada in ordenadas[:4]
            ),
            "pre_live_disponiveis": len(pre_live_acionaveis),
            "pre_live_confirmados_disponiveis": len(
                pre_live_confirmados
            ),
            "pre_live_reservado": prioridade_pre_live is not None,
            "tipo_prioridade_pre_live": tipo_prioridade_pre_live,
            "pre_live_nas_quatro_primeiras": any(
                item.get("pre_live_prioritario")
                for item in ordenadas[:4]
            ),
            "acompanhamentos_preco_disponiveis": len(
                acompanhamentos_preco_disponiveis
            ),
            "acompanhamento_preco_reservado": (
                acompanhamento_preco_reservado is not None
            ),
            "acompanhamento_preco_nas_tres_primeiras": bool(
                acompanhamento_preco_reservado is not None
                and acompanhamento_preco_reservado in ordenadas[:3]
            ),
            "acompanhamento_preco_reservado_idade_segundos": (
                round(
                    idade_acompanhamento_preco(
                        acompanhamento_preco_reservado
                    ),
                    3,
                )
                if acompanhamento_preco_reservado is not None else None
            ),
            "acompanhamento_preco_reservado_fora_janela_sinais": bool(
                acompanhamento_preco_reservado is not None
                and not acompanhamento_preco_reservado.get(
                    "acionavel_fila_detalhada"
                )
            ),
            "campos_indicadores_lista": campos_radar[:40],
            "novas_disponiveis": len(novas),
            "nova_reservada": reservada_nova is not None,
            "nova_gol_ht_reservada": bool(
                reservada_nova is not None
                and base_gol_ht_ativa(reservada_nova)
            ),
            "atrasadas_acima_20_minutos": len(atrasadas),
            "atrasadas_acionaveis": len(atrasadas_acionaveis),
            "atrasada_reservada": reservada_atrasada is not None,
            "atrasada_reservada_acionavel": bool(
                reservada_atrasada is not None
                and reservada_atrasada.get("acionavel_fila_detalhada")
            ),
            "atrasada_nas_tres_primeiras": bool(
                reservada_atrasada is not None
                and reservada_atrasada in ordenadas[:3]
            ),
            "maior_atraso_reservado_segundos": (
                round(idade_valida(reservada_atrasada), 3)
                if reservada_atrasada is not None else None
            ),
            "seguimentos_temporais_disponiveis": len(
                candidatas_temporais
            ),
            "seguimentos_temporais_longos_disponiveis": len(
                candidatas_temporais_longas
            ),
            "foco_ja_cobre_janela_temporal": foco_ja_temporal,
            "foco_ja_cobre_janela_5": foco_ja_temporal_5,
            "foco_ja_cobre_janela_temporal_longa": (
                foco_ja_temporal_longo
            ),
            "seguimento_temporal_reservado": (
                bool(reservadas_temporais)
            ),
            "seguimento_gol_ht_reservado": any(
                janela_gol_ht_ativa(item)
                for item in reservadas_temporais
            ),
            "seguimentos_temporais_reservados": len(
                reservadas_temporais
            ),
            "carga_alta_temporal": carga_alta,
            "foco_prioritario_reservado": (
                foco_prioritario is not None
            ),
            "focos_fora_janela_operacional": len(focos_fora_janela),
            "minuto_maximo_prioridade_sinais": (
                MINUTO_MAXIMO_PRIORIDADE_SINAIS
            ),
            "tarefas_intervalo_fora_prioridade": tarefas_no_intervalo,
            "tarefas_acionaveis": len(tarefas_acionaveis),
            "tarefas_fora_janelas_ativas": len(
                tarefas_fora_janelas_ativas
            ),
            "prioridade_acionaveis_aplicada": (
                prioridade_acionaveis_aplicada
            ),
            "acionaveis_nas_quatro_primeiras": sum(
                bool(item.get("acionavel_fila_detalhada"))
                for item in ordenadas[:4]
            ),
            "oportunidade_api_reservada": (
                reservada_oportunidade is not None
            ),
            "oportunidade_gol_ht_reservada": bool(
                reservada_oportunidade is not None
                and janela_gol_ht_ativa(reservada_oportunidade)
            ),
            "prioridade_gol_ht_garantida": prioridade_gol_ht is not None,
            "tipo_prioridade_gol_ht": (
                "seguimento"
                if prioridade_gol_ht in reservadas_temporais
                else "base"
                if prioridade_gol_ht is reservada_nova
                else "oportunidade"
                if prioridade_gol_ht is reservada_oportunidade
                else None
            ),
            "prioridade_gol_ht_nas_quatro_primeiras": bool(
                prioridade_gol_ht is not None
                and prioridade_gol_ht in ordenadas[:4]
            ),
            "janelas_temporais_reservadas": sorted({
                janela
                for item in reservadas_temporais
                for janela in item.get("janelas_temporais_projetadas", [])
            }),
            "janela_5_priorizada": bool(
                foco_ja_temporal_5
                or (
                    reservada_atrasada is not None
                    and 5 in janelas_projetadas(reservada_atrasada)
                )
                or any(
                    5 in janelas_projetadas(item)
                    for item in reservadas_temporais
                )
            ),
            "fixtures_odds_asiaticas_api": len(
                fixtures_odds_asiaticas
            ),
            "tarefas_com_odds_asiaticas_api": sum(
                bool(item.get("odd_asiatica_api_disponivel"))
                for item in tarefas
            ),
            "tarefas_asiaticas_alvo_um_escanteio": sum(
                bool(item.get(
                    "odd_asiatica_api_alvo_um_escanteio"
                ))
                for item in tarefas
            ),
            "tarefas_candidatas_exploracao_gols": sum(
                bool(item.get("prioridade_exploracao_gols"))
                for item in tarefas
            ),
            "candidatas_exploracao_gols_com_janela_5": sum(
                bool(item.get("prioridade_exploracao_gols"))
                and 5 in janelas_projetadas(item)
                for item in tarefas
            ),
            "exploracao_gols_nas_quatro_primeiras": any(
                item.get("prioridade_exploracao_gols")
                for item in ordenadas[:4]
            ),
            "exploracao_gols_janela_5_nas_quatro_primeiras": any(
                item.get("prioridade_exploracao_gols")
                and 5 in janelas_projetadas(item)
                for item in ordenadas[:4]
            ),
            "odd_asiatica_api_nas_quatro_primeiras": any(
                item.get("odd_asiatica_api_disponivel")
                for item in ordenadas[:4]
            ),
            "alvo_um_escanteio_nas_quatro_primeiras": any(
                item.get("odd_asiatica_api_alvo_um_escanteio")
                for item in ordenadas[:4]
            ),
            "consulta_odds_api_cacheada_executada": (
                consulta_odds_api_executada
            ),
            "consulta_odds_api_cacheada_falhou": consulta_odds_api_falhou,
            "sem_navegacoes_packball_extras": True,
            "sem_solicitacoes_extras": not consulta_odds_api_executada,
        }

    def _recalibrar(self):
        for mercado in MERCADOS_CALIBRADOS:
            self.calibrador.recalibrar(
                mercado, versao_regra_operacional(mercado)
            )

    def _recalibrar_desatualizadas(self):
        reconciliadas = []
        for mercado in MERCADOS_CALIBRADOS:
            resultado = self.calibrador.reconciliar_se_desatualizado(
                mercado, versao_regra_operacional(mercado)
            )
            if resultado is not None:
                reconciliadas.append(mercado)
        return reconciliadas

    @staticmethod
    def _imprimir_jogo(
        jogo, estatisticas, odds, evolucao, confirmacao_api, qualidade
    ):
        print(
            f"• {jogo['mandante']} {jogo['placar']} "
            f"{jogo['visitante']} — {jogo['status']}"
        )
        print(
            "  Pressão: "
            f"{estatisticas.get('Índice de pressão', '-')} | "
            f"Chutes: {estatisticas.get('Chutes', '-')} | "
            f"No gol: {estatisticas.get('Chutes no gol', '-')} | "
            "Ataques perigosos: "
            f"{estatisticas.get('Ataques perigosos', '-')}"
        )
        print(
            f"  Posse: {estatisticas.get('Posse de bola', '-')} | "
            f"Escanteios: {estatisticas.get('Escanteios', '-')} | "
            f"Ataques: {estatisticas.get('Ataques', '-')}"
        )
        mercados = odds.get("ao_vivo") or odds.get("pre_jogo") or []
        if mercados:
            print("  Odds de gols/escanteios:")
            for mercado in mercados:
                descricao = (
                    mercado.get("dados")
                    or mercado.get("mercado")
                    or mercado.get("categoria")
                    or "mercado estruturado sem descrição textual"
                )
                print(f"    {descricao}")
        else:
            print("  Odds de gols/escanteios: indisponíveis")
        if confirmacao_api:
            status_api = confirmacao_api.get("status") or {}
            print(
                "  API-Football: confirmado | "
                f"minuto {status_api.get('elapsed', '-')} | "
                f"placar {confirmacao_api.get('placar')} | "
                f"similaridade {confirmacao_api.get('similaridade')}"
            )
        else:
            print("  API-Football: partida não associada")
        situacao = "apta" if qualidade["apto_para_sinal"] else "bloqueada"
        print(
            f"  Qualidade dos dados: {qualidade['pontuacao']:.1f}/100 | "
            f"{situacao} para sinais"
        )
        print("  Evolução recente:")
        for minutos in (5, 10, 15):
            janela = evolucao.get(str(minutos))
            if not janela:
                print(f"    {minutos} min: aguardando histórico")
                continue
            print(
                f"    {minutos} min — Pressão: "
                f"{formatar_delta(janela.get('pressao'))} | "
                f"Chutes: {formatar_delta(janela.get('chutes'))} | "
                f"Escanteios: {formatar_delta(janela.get('escanteios'))}"
            )

    def _executar_configuracao_packball(self, headless=False, aguardar=None):
        """Abre o mesmo navegador operacional sem iniciar ciclos de coleta."""
        if headless:
            raise ValueError("configuracao_packball_exige_janela_visivel")
        aguardar = aguardar or input
        with self._iniciar_playwright_seguro() as playwright:
            navegador, contexto, pagina, _detalhe = self._abrir_navegador(
                playwright, headless=False
            )
            try:
                self.packball._navegar(
                    pagina, self.packball.url_partidas
                )
                pagina.wait_for_timeout(5000)
                print(
                    "Janela operacional do PackBall aberta em modo de "
                    "configuracao. O monitor nao analisara partidas enquanto "
                    "voce ajusta o Scanner e as colunas."
                )
                aguardar(
                    "Depois de clicar em Salvar Filtros, pressione Enter "
                    "nesta janela para gravar e fechar..."
                )
                _storage_state_completo(
                    contexto, path=self.arquivo_sessao
                )
                print(
                    "Scanner e configuracao da janela operacional salvos."
                )
                return True
            finally:
                try:
                    if navegador.is_connected():
                        navegador.close()
                except Exception:
                    pass

    def executar(
        self, uma_vez=False, headless=False,
        configurar_packball=False,
    ):
        if configurar_packball:
            return self._executar_configuracao_packball(
                headless=headless
            )
        if ler_modo_manutencao(self.pasta).get("ativo"):
            print("Monitor pausado: modo de manutenção ativo.")
            return
        self.preparar()
        if self._aguardar_pausa_packball_antes_navegador(
            uma_vez=uma_vez
        ):
            return
        if not uma_vez:
            self._supervisionar_watchdog()
            self.observabilidade.ciclo_progresso(
                "aguardando_supervisao_inicial"
            )
            supervisao_inicial = self._aguardar_supervisao_inicial()
            if supervisao_inicial["estado"] == "manutencao":
                print(
                    "Modo de manutencao detectado durante a inicializacao; "
                    "o PackBall nao sera aberto."
                )
                return
            if supervisao_inicial["saudavel"]:
                print(
                    "Supervisao inicial confirmada em "
                    f"{supervisao_inicial['duracao_segundos']:.1f}s."
                )
            else:
                print(
                    "Supervisao inicial ainda indisponivel apos "
                    f"{supervisao_inicial['duracao_segundos']:.1f}s; "
                    "a coleta pode continuar, mas os sinais permanecem "
                    "fechados pelos gates de seguranca."
                )
        with ExitStack() as recursos:
            # O acompanhamento de odds usa apenas APIs e SQLite. Ele precisa
            # continuar ativo mesmo quando o Playwright/Chrome demora para
            # liberar o pipe no Windows; por isso nasce antes do navegador.
            if not uma_vez:
                self._iniciar_trabalhador_acompanhamento_odd()
                recursos.callback(
                    self._parar_trabalhador_acompanhamento_odd
                )
            playwright = recursos.enter_context(
                self._iniciar_playwright_seguro()
            )
            navegador, contexto, pagina, detalhe = self._abrir_navegador(
                playwright, headless
            )
            print("Monitor do Packball iniciado!")
            print(f"Atualização a cada {INTERVALO_SEGUNDOS} segundos.")
            print("Para encerrar, pressione Ctrl + C.\n")
            try:
                while True:
                    if ler_modo_manutencao(self.pasta).get("ativo"):
                        print(
                            "Modo de manutenção detectado; encerrando o "
                            "monitor após o ciclo anterior."
                        )
                        break
                    if not uma_vez:
                        self._supervisionar_watchdog()
                    inicio = time.monotonic()
                    try:
                        partidas, consumo, coleta = self.executar_ciclo(
                            pagina, detalhe
                        )
                        self.observabilidade.ciclo_sucesso(
                            time.monotonic() - inicio,
                            partidas,
                            consumo,
                            coleta,
                        )
                        self._sincronizar_sessao_contexto(contexto)
                    except ManutencaoSolicitadaError as interrupcao:
                        self._invalidar_alertas_pendentes_ciclo()
                        print(
                            "Modo de manutenção detectado em ponto seguro "
                            f"({interrupcao}); encerrando o monitor."
                        )
                        break
                    except Exception as erro:
                        pausa_preventiva = (
                            self._registrar_interrupcao_ciclo(
                                time.monotonic() - inicio, erro
                            )
                        )
                        print(f"Erro temporário: {erro}")
                        if not self.conectividade.disponivel():
                            print(
                                "Internet indisponível; mantendo o estado e "
                                "aguardando o próximo ciclo."
                            )
                            if uma_vez:
                                break
                            duracao = time.monotonic() - inicio
                            if self._aguardar_intervalo_interrompivel(
                                max(0, INTERVALO_SEGUNDOS - duracao)
                            ):
                                break
                            continue
                        erro_fatal_navegador = self._erro_navegador_fatal(
                            erro
                        )
                        bloqueio_packball = isinstance(
                            erro, PackBallBloqueadoError
                        )
                        lista_nao_validada = isinstance(
                            erro, PackBallListaNaoValidadaError
                        )
                        if bloqueio_packball or lista_nao_validada:
                            try:
                                self._coletar_historico_api_live_durante_pausa_packball(
                                    type(erro).__name__
                                )
                            except Exception as erro_sombra:
                                # A continuidade auxiliar nunca pode romper
                                # o tratamento da falha principal nem reabrir
                                # o gate operacional.
                                self._operacao_bloqueada_ciclo = True
                                self._alertas_pendentes_ciclo = []
                                self.observabilidade.historico_api_pausa_packball({
                                    "estado": "falha_isolada",
                                    "erro": type(erro_sombra).__name__,
                                    "aplicacao_sinais": False,
                                    "operacao_bloqueada": True,
                                })
                        recuperar_por_falhas = (
                            self.observabilidade.deve_recuperar_navegador()
                        )
                        if bloqueio_packball:
                            estado_acesso = (
                                self.controle_packball.estado_atual()
                            )
                            print(
                                "PackBall em pausa de seguranca; nenhuma "
                                "nova navegacao sera feita por "
                                f"{estado_acesso['restante_segundos']:.0f}s."
                            )
                        if (
                            lista_nao_validada
                            and not bloqueio_packball
                            and recuperar_por_falhas
                        ):
                            limite = (
                                self._pausar_lista_packball_nao_validada()
                            )
                            print(
                                "Lista Ao Vivo nao validada em tres ciclos; "
                                "PackBall pausado sem novas navegacoes ate "
                                f"{limite.isoformat()}."
                            )
                            # O contador pode desaparecer por estado velho
                            # da SPA. Renove somente o navegador/contexto;
                            # _abrir_navegador não acessa o PackBall. A
                            # primeira navegação continua bloqueada pelo
                            # circuito até o prazo acima expirar.
                            try:
                                if navegador.is_connected():
                                    navegador.close()
                            except Exception:
                                pass
                            navegador, contexto, pagina, detalhe = (
                                self._abrir_navegador(playwright, headless)
                            )
                            self.observabilidade.recuperacao(
                                "lista ao vivo não validada; contexto "
                                "renovado sem navegação durante a pausa"
                            )
                            print(
                                "Contexto do navegador renovado; a pausa "
                                "de acesso permanece ativa."
                            )
                        elif (
                            not bloqueio_packball
                            and (
                                erro_fatal_navegador
                                or recuperar_por_falhas
                            )
                        ):
                            try:
                                if navegador.is_connected():
                                    navegador.close()
                            except Exception:
                                pass
                            navegador, contexto, pagina, detalhe = (
                                self._abrir_navegador(playwright, headless)
                            )
                            self.observabilidade.recuperacao(
                                "navegador/contexto fechado; reinício imediato"
                                if erro_fatal_navegador else
                                "três ciclos com erro; navegador reiniciado"
                            )
                            print("Navegador reiniciado automaticamente.")
                    if not uma_vez:
                        diagnostico_runtime = (
                            self._avaliar_reinicio_runtime_monitor()
                        )
                        if diagnostico_runtime["solicitado"]:
                            self.reinicio_runtime_solicitado = True
                            self.diagnostico_reinicio_runtime = (
                                diagnostico_runtime
                            )
                            self.observabilidade.ciclo_progresso(
                                "reinicio_runtime_monitor_solicitado",
                                estado_monitor=diagnostico_runtime[
                                    "estado_monitor"
                                ],
                                estado_watchdog=diagnostico_runtime[
                                    "estado_watchdog"
                                ],
                            )
                            print(
                                "Código operacional atualizado; fechando "
                                "o monitor após o ciclo para reinício "
                                "automático seguro."
                            )
                            break
                    if uma_vez:
                        break
                    duracao = time.monotonic() - inicio
                    if self._aguardar_intervalo_interrompivel(
                        max(0, INTERVALO_SEGUNDOS - duracao),
                        durante_espera_fn=(
                            self._rechecar_acompanhamentos_odd_api
                        ),
                    ):
                        print(
                            "Modo de manutenção detectado durante a espera; "
                            "encerrando o monitor."
                        )
                        break
            except KeyboardInterrupt:
                print("\nMonitor encerrado.")
            finally:
                try:
                    if navegador.is_connected():
                        navegador.close()
                except Exception:
                    pass

    def fechar(self):
        self._parar_trabalhador_acompanhamento_odd()
        self.banco.fechar()

    @contextmanager
    def _iniciar_playwright_seguro(
        self, tentativas=8, espera_inicial=2, espera_maxima=15
    ):
        """Tolera a liberação tardia do pipe do Playwright no Windows."""
        total_tentativas = max(int(tentativas), 1)
        playwright = None
        for tentativa in range(total_tentativas):
            gerenciador = None
            try:
                gerenciador = sync_playwright()
                playwright = gerenciador.start()
                if tentativa:
                    observabilidade = getattr(
                        self, "observabilidade", None
                    )
                    if observabilidade is not None:
                        observabilidade.recuperacao(
                            "driver Playwright liberado após "
                            f"{tentativa + 1} tentativas"
                        )
                break
            except PermissionError as erro:
                # Um start parcial pode deixar o transporte/pipe do driver
                # aberto no próprio processo. Fechá-lo antes do retry evita
                # perpetuar o WinError 5 nas tentativas seguintes.
                if gerenciador is not None:
                    try:
                        gerenciador.__exit__(None, None, None)
                    except Exception:
                        pass
                if tentativa + 1 >= total_tentativas:
                    raise PermissionError(
                        "playwright_start_bloqueado_apos_"
                        f"{total_tentativas}_tentativas: {erro}"
                    ) from erro
                espera = min(
                    max(float(espera_inicial), 0) * (2 ** tentativa),
                    max(float(espera_maxima), 0),
                )
                observabilidade = getattr(self, "observabilidade", None)
                if observabilidade is not None:
                    observabilidade.ciclo_progresso(
                        "playwright_permission_retry",
                        etapa_bloqueada="iniciar_driver",
                        tentativa=tentativa + 1,
                        proxima_espera_segundos=espera,
                    )
                time.sleep(espera)
        try:
            yield playwright
        finally:
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    pass

    def _abrir_navegador(
        self, playwright, headless, tentativas=8, espera_inicial=2,
        espera_maxima=15,
    ):
        """Tolera a liberação tardia do Chrome após um reinício controlado."""
        total_tentativas = max(int(tentativas), 1)
        for tentativa in range(total_tentativas):
            navegador = None
            try:
                navegador = playwright.chromium.launch(
                    channel="chrome", headless=headless
                )
                contexto = navegador.new_context(
                    storage_state=self.arquivo_sessao
                )
                pagina = contexto.new_page()
                # O PackBall orienta manter o site em uma unica aba. Lista,
                # estatisticas e odds sao visitadas sequencialmente nesta
                # pagina.
                return navegador, contexto, pagina, pagina
            except PermissionError as erro:
                if navegador is not None:
                    try:
                        navegador.close()
                    except Exception:
                        pass
                if tentativa + 1 >= total_tentativas:
                    raise PermissionError(
                        "chrome_abertura_bloqueada_apos_"
                        f"{total_tentativas}_tentativas: {erro}"
                    ) from erro
                espera = min(
                    max(float(espera_inicial), 0) * (2 ** tentativa),
                    max(float(espera_maxima), 0),
                )
                observabilidade = getattr(self, "observabilidade", None)
                if observabilidade is not None:
                    observabilidade.ciclo_progresso(
                        "playwright_permission_retry",
                        etapa_bloqueada="abrir_chrome",
                        tentativa=tentativa + 1,
                        proxima_espera_segundos=espera,
                    )
                time.sleep(espera)


def main():
    pasta = Path(__file__).parent
    configurar_packball = "--configurar-packball" in sys.argv
    trava = TravaInstancia(pasta / "monitor_instancia.lock")
    if not trava.adquirir():
        print("Monitor não iniciado: outra instância já está ativa.")
        return
    servico = None
    caminho_processo = pasta / "monitor_processo.json"
    codigo_hash = None
    encerramento_limpo = False
    erro_fatal = None
    try:
        codigo_hash = hash_codigo_runtime(pasta)
        registrar_estado(
            caminho_processo, "iniciando", codigo_hash=codigo_hash,
            modo_inicio=os.getenv("MONITOR_MODO_INICIO", "direto"),
        )
        servico = ServicoMonitor(pasta)
        registrar_estado(
            caminho_processo,
            "configurando" if configurar_packball else "ativo",
            codigo_hash=codigo_hash,
            modo_inicio=os.getenv("MONITOR_MODO_INICIO", "direto"),
            rollback_terminal_visivel="MONITOR_TERMINAL_VISIVEL=0",
        )
        servico.executar(
            uma_vez="--uma-vez" in sys.argv,
            headless="--headless" in sys.argv,
            configurar_packball=configurar_packball,
        )
        encerramento_limpo = True
    except Exception as erro:
        erro_fatal = erro
        try:
            if servico is not None:
                servico.observabilidade.processo_falhou("monitor", erro)
        except Exception:
            pass
        raise
    finally:
        try:
            if servico is not None:
                servico.fechar()
            detalhes_falha = {}
            if erro_fatal is not None:
                detalhes_falha = {
                    "erro": type(erro_fatal).__name__,
                    "mensagem": resumir_erro_seguro(erro_fatal),
                }
            status_final = (
                "reinicio_pendente"
                if (
                    erro_fatal is None
                    and servico is not None
                    and servico.reinicio_runtime_solicitado
                )
                else "encerrado" if encerramento_limpo else "falha"
            )
            detalhes_reinicio = {}
            if status_final == "reinicio_pendente":
                detalhes_reinicio = {
                    "motivo": "codigo_runtime_monitor_desatualizado",
                    "diagnostico_runtime": (
                        servico.diagnostico_reinicio_runtime
                    ),
                }
            registrar_estado(
                caminho_processo,
                status_final,
                codigo_hash=codigo_hash,
                **detalhes_falha,
                **detalhes_reinicio,
            )
        finally:
            trava.liberar()
