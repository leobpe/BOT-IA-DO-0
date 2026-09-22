import argparse
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from backup_banco import verificar_backup_espelho

from autostart_windows import consultar as consultar_autostart
from analisar_erros_gol_ft import auditar_sobreajuste
from avaliacao_clv_live import (
    VERSAO as VERSAO_AVALIACAO_CLV_LIVE,
    avaliar as avaliar_clv_live,
)
from avaliacao_portfolio_edge import avaliar as avaliar_portfolio_edge
from auditoria_ligas_sombra import MERCADOS_AUDITADOS
from backtest import calcular_metricas
from banco import auditar_historico_drift_simulacoes
from configuracao import obter_limites_risco, validar_configuracao
from controle_sistema import ler_modo_manutencao
from custodia_avaliacao import EFEITOS_DESATIVADOS
from controle_v2b_ft import ler_estado_v2b_ft
from controle_gols_antecipados import (
    ler_estado as ler_estado_gols_antecipados,
)
from controle_filtro_gol_ft_preciso import (
    ler_estado as ler_estado_filtro_gol_ft_preciso,
)
from controle_filtro_gol_ht_preciso import (
    ler_estado as ler_estado_filtro_gol_ht_preciso,
)
from controle_escanteios_ft_asiatico import (
    ler_estado as ler_estado_escanteios_ft_asiatico,
)
from controle_proximo_gol_balanceado import (
    ler_estado as ler_estado_proximo_gol_balanceado,
)
from controle_pre_live_preciso import (
    ler_estado as ler_estado_pre_live_preciso,
)
from gol_ht_00_min20 import VERSAO as VERSAO_GOL_HT_00_MIN20
from gols_antecipados import (
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
    VERSAO_GOL_HT_ANTECIPADO,
)
from filtro_gol_ht_antecipado_preciso import (
    VERSAO as VERSAO_FILTRO_GOL_HT_PRECISO,
)
from filtro_gol_ft_antecipado_preciso import (
    VERSAO as VERSAO_FILTRO_GOL_FT_PRECISO,
)
from gols_capacidade_contextual_v2 import (
    VERSAO_GOL_FT as VERSAO_GOL_FT_CAPACIDADE_CONTEXTUAL_V2,
    VERSAO_GOL_HT as VERSAO_GOL_HT_CAPACIDADE_CONTEXTUAL_V2,
)
from dataset_temporal import (
    resumir_cobertura_dataset_temporal,
    resumir_cortes_sombra,
)
from fallback_indicadores_lista import resumir_auditoria_temporal_sqlite
from linhagem_regras import fingerprint_vinculado_no_banco
from integridade_calibracao import carregar_amostra_independente
from mercados import (
    MERCADOS_CALIBRADOS,
    mercados_calibrados_operacionais,
)
from motor_sinais import VERSAO_REGRAS
from processo_monitor import (
    ARQUIVOS_RUNTIME_WATCHDOG,
    estado_codigo_runtime,
    ler_estado,
    pid_ativo,
    trava_em_uso,
)
from treino_processo_isolado import (
    PROTOCOLO_TREINO_ISOLADO,
    verificar_worker_treino_isolado,
)
from versoes_gol_ft_reforcado import (
    VERSAO_GOL_FT_REFORCADO,
    versao_regra_operacional as versao_regra_para_mercado,
)
from versoes_gol_ht_protegido import VERSAO_GOL_HT_PROTEGIDO
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)
from relatorio_odds_periodos import (
    diagnosticar_fontes_odds_periodos,
    resumir_odds_escanteios_periodos,
)
from relatorio_pendencias import resumir_pendencias_resultados
from relatorio_simulacoes import comparar_filtro_simulacoes
from repositorio_pre_live import verificar_backup_pre_live
from top_criterios_gols import (
    VERSAO_FT as VERSAO_TOP_CRITERIO_FT,
    VERSAO_HT as VERSAO_TOP_CRITERIO_HT,
)
from validacao_gol_ht_00_min20 import (
    resumir_validacao_gol_ht_00_min20,
)
from validacao_gols_antecipados import (
    resumir_validacao_gols_antecipados,
)
from validacao_gol_ht_antecipado_preciso import (
    resumir_validacao as resumir_validacao_filtro_gol_ht_preciso,
)
from validacao_gol_ft_antecipado_preciso import (
    resumir_validacao as resumir_validacao_filtro_gol_ft_preciso,
)
from validacao_quase_candidatos_gol_ft import (
    resumir_validacao as resumir_validacao_quase_gol_ft,
)
from validacao_gols_capacidade_contextual_v2 import (
    MINIMO_VALIDOS_TOTAL as MINIMO_VALIDOS_V2B_FT,
    TAMANHO_COORTE as TAMANHO_COORTE_V2B_FT,
)
from validacao_top_criterios_gols import resumir_top_criterios_gols
from validacao_pre_live_preciso import (
    resumir_validacao_pre_live_preciso_arquivo,
)
from valor_mercado import VERSAO as VERSAO_VALOR_MERCADO
from exposicao_coleta_prospectiva import (
    VERSAO as VERSAO_EXPOSICAO_COLETA_PROSPECTIVA,
    carregar_eventos_observabilidade,
    resumir_exposicao,
)
from watchdog import (
    auditar_operacao_pre_live,
    verificar_avaliacao_acompanhamento_odd,
    verificar_avaliacao_desajuste_odds,
    verificar_avaliacao_prioridade_ligas_gols,
    verificar_avaliacao_quarentena_fallback_ht,
    verificar_cache_api_operacional,
    verificar_coleta,
    verificar_pareamento_api,
    verificar_ponto_recuperacao,
    verificar_validacao,
)


def _componente(estado, resumo, **evidencias):
    return {
        "estado": estado,
        "pronto": estado == "pronto",
        "resumo": resumo,
        "evidencias": evidencias,
    }


def _valor_progresso_metodo(metodo, chave):
    """Normaliza progresso sem descartar a auditoria completa do método."""
    metodo = dict(metodo or {})
    validador = dict(metodo.get("validador_prospectivo") or {})
    if chave == "versao":
        return metodo.get("versao") or metodo.get("versao_metodo")
    if chave == "decisao_estatistica":
        return (
            metodo.get("decisao_estatistica")
            or metodo.get("decisao_validador")
            or validador.get("decisao_estatistica")
            or validador.get("decisao")
        )
    if metodo.get(chave) is not None:
        return metodo[chave]
    return validador.get(chave)


def _com_exposicao_coorte(
    resumo, *, telemetria, modo_manutencao, agora,
):
    """Anexa um relógio operacional à versão exata, sem alterar a coorte."""
    resultado = dict(resumo or {})
    ancora = (
        resultado.get("registrado_em")
        or resultado.get("ancora_prospectiva_em")
        or resultado.get("iniciado_em")
    )
    if not ancora:
        return resultado
    telemetria = dict(telemetria or {})
    resultado["exposicao_coorte_prontidao"] = resumir_exposicao(
        telemetria.get("eventos") or (),
        ancora=ancora,
        modo_manutencao=modo_manutencao,
        agora=agora,
        telemetria_saudavel=telemetria.get("saudavel") is True,
    )
    return resultado


def coletar_estado_pre_live_autoritativo(
    pasta, estado_watchdog=None, auditar_fn=None,
):
    """Revalida o processo pré-live em vez de confiar no snapshot do watchdog.

    O watchdog pode estar deliberadamente parado durante a manutenção. Nesse
    caso, seu último JSON ainda pode dizer ``ativo`` mesmo depois que o PID e a
    trava já desapareceram. A prontidão precisa observar o estado presente e
    falhar fechada se essa auditoria não puder ser concluída.
    """
    pasta = Path(pasta)
    anterior = dict((estado_watchdog or {}).get("pre_live") or {})
    auditar_fn = auditar_fn or auditar_operacao_pre_live
    try:
        atual = dict(auditar_fn(pasta) or {})
    except Exception as erro:
        return {
            **anterior,
            "saudavel": False,
            "estado": "auditoria_falhou",
            "motivo": "auditoria_pre_live_atual_falhou",
            "erro_auditoria": type(erro).__name__,
            "estado_watchdog_anterior": anterior.get("estado"),
        }
    atual["estado_watchdog_anterior"] = anterior.get("estado")
    atual["snapshot_watchdog_divergente"] = bool(
        anterior
        and (
            anterior.get("estado") != atual.get("estado")
            or bool(anterior.get("saudavel"))
            != bool(atual.get("saudavel"))
            or anterior.get("pid") != atual.get("pid")
        )
    )
    return atual


def _idade_minutos(instante, agora):
    try:
        observado = datetime.fromisoformat(str(instante))
    except (TypeError, ValueError):
        return None
    referencia = agora
    if observado.tzinfo is None and referencia.tzinfo is not None:
        referencia = referencia.replace(tzinfo=None)
    elif observado.tzinfo is not None and referencia.tzinfo is None:
        observado = observado.replace(tzinfo=None)
    return round(max((referencia - observado).total_seconds(), 0) / 60, 3)


def diagnosticar_acesso_packball(estado, agora=None):
    """Expõe uma pausa operacional como dependência, não como falha interna.

    O arquivo de controle pode conservar datas de pausas já encerradas. Por
    isso, a autoridade é a data limite comparada ao relógio atual, e não a
    mera presença dos campos ``pausado_ate`` ou ``bloqueado_ate``.
    """
    estado = dict(estado or {})
    agora = agora or datetime.now()
    limites = []
    for campo in ("bloqueado_ate", "pausado_ate"):
        try:
            limite = datetime.fromisoformat(str(estado.get(campo)))
        except (TypeError, ValueError):
            continue
        referencia = agora
        if limite.tzinfo is None and referencia.tzinfo is not None:
            referencia = referencia.replace(tzinfo=None)
        elif limite.tzinfo is not None and referencia.tzinfo is None:
            limite = limite.replace(tzinfo=None)
        limites.append((limite, referencia, campo))
    ativos = [item for item in limites if item[0] > item[1]]
    if not ativos:
        return {
            "pronto": True,
            "estado": "pronto",
            "ativo": False,
            "motivo": None,
            "limite_em": None,
            "restante_segundos": 0.0,
        }
    limite, referencia, campo = max(ativos, key=lambda item: item[0])
    motivo = str(estado.get("motivo") or "pausa_seguranca_packball")
    return {
        "pronto": False,
        "estado": (
            "aguardando_login_packball"
            if motivo == "falha_login_packball"
            else "pausa_seguranca_packball"
        ),
        "ativo": True,
        "motivo": motivo,
        "campo_limite": campo,
        "limite_em": limite.isoformat(),
        "restante_segundos": round(
            max((limite - referencia).total_seconds(), 0.0), 1
        ),
    }


def diagnosticar_fluxo_amostras_ativas(
    fluxo, coleta, processos, mercados_exigidos, agora=None,
    limite_minutos=20,
):
    """Distingue funil ativo de ausencia legitima de jogos ou oportunidade."""
    fluxo = dict(fluxo or {})
    coleta = dict(coleta or {})
    processos = dict(processos or {})
    agora = agora or datetime.now()
    mercados_exigidos = tuple(mercados_exigidos or ())
    try:
        limite_minutos = max(float(limite_minutos), 1.0)
    except (TypeError, ValueError):
        limite_minutos = 20.0
    mercados = dict(fluxo.get("mercados") or {})
    bracos = dict(fluxo.get("bracos") or {})
    partidas = coleta.get(
        "partidas_ultimo_ciclo",
        fluxo.get("partidas_ultimo_ciclo"),
    )
    try:
        partidas = int(partidas) if partidas is not None else None
    except (TypeError, ValueError):
        partidas = None

    base = {
        mercado: {
            **dict(mercados.get(mercado) or {}),
            "idade_ultimo_candidato_minutos": _idade_minutos(
                (mercados.get(mercado) or {}).get("ultimo_candidato_em"),
                agora,
            ),
            "idade_heartbeat_politica_minutos": _idade_minutos(
                ((mercados.get(mercado) or {}).get(
                    "heartbeat_politica"
                ) or {}).get("observado_em"),
                agora,
            ),
        }
        for mercado in mercados_exigidos
    }
    bracos_detalhados = {
        versao: {
            **dict(item or {}),
            "idade_ultimo_candidato_minutos": _idade_minutos(
                (item or {}).get("ultimo_candidato_em"), agora
            ),
        }
        for versao, item in bracos.items()
    }
    comuns = {
        "limite_minutos": limite_minutos,
        "partidas_ultimo_ciclo": partidas,
        "mercados": base,
        "bracos": bracos_detalhados,
        "bracos_afetam_saude": False,
    }
    if fluxo.get("saudavel") is False:
        return {
            "pronto": False,
            "estado": "degradado",
            "motivo": fluxo.get("motivo") or "consulta_fluxo_falhou",
            "mercados_sem_fluxo": list(mercados_exigidos),
            **comuns,
        }
    if not processos.get("monitor_ativo"):
        return {
            "pronto": False,
            "estado": "degradado",
            "motivo": "monitor_inativo",
            "mercados_sem_fluxo": list(mercados_exigidos),
            **comuns,
        }
    if partidas is None:
        return {
            "pronto": False,
            "estado": "sincronizando",
            "motivo": "aguardando_contagem_ultimo_ciclo",
            "mercados_sem_fluxo": [],
            **comuns,
        }
    if partidas <= 0:
        return {
            "pronto": True,
            "estado": "pronto",
            "motivo": "sem_jogos_ao_vivo_no_ultimo_ciclo",
            "mercados_sem_fluxo": [],
            **comuns,
        }

    def possui_fluxo_recente(item):
        idade_candidato = item.get("idade_ultimo_candidato_minutos")
        if idade_candidato is not None and idade_candidato <= limite_minutos:
            return True
        heartbeat = item.get("heartbeat_politica") or {}
        idade_heartbeat = item.get("idade_heartbeat_politica_minutos")
        return bool(
            heartbeat.get("ativa") is True
            and heartbeat.get("versao") == item.get("versao")
            and idade_heartbeat is not None
            and idade_heartbeat <= limite_minutos
        )

    sem_fluxo = sorted(
        mercado for mercado, item in base.items()
        if not possui_fluxo_recente(item)
    )
    return {
        "pronto": not sem_fluxo,
        "estado": "pronto" if not sem_fluxo else "degradado",
        "motivo": None if not sem_fluxo else "mercado_sem_amostra_recente",
        "mercados_sem_fluxo": sem_fluxo,
        **comuns,
    }


def classificar_pendencia_prontidao(estado):
    """Separa espera estatistica de defeitos que exigem intervencao tecnica."""
    if estado in {
        "pendente_amostra",
        "pendente_evidencia",
        "pendente_evidencia_real",
        "pendente_validacao",
        "aguardando_resultados",
        "historico_drift_aguardando_amostra",
    }:
        return "aguardando_dados_reais"
    if estado == "sincronizando":
        return "sincronizacao_em_curso"
    if estado == "sombra":
        return "controle_experimental"
    if estado == "revisao_necessaria":
        return "modelo_reprovado"
    if estado == "reprovado_validacao":
        return "modelo_reprovado"
    if estado in {
        "aguardando_autorizacao",
        "aguardando_login_packball",
        "aguardando_reset_cota",
        "fonte_indisponivel",
        "pausa_seguranca_packball",
    }:
        return "dependencia_externa"
    if estado == "pausa_planejada":
        return "pausa_planejada"
    return "pendencia_tecnica"


def diagnosticar_frescor_espelho_watchdog(
    estado_watchdog, processo_watchdog
):
    persistido_em = (
        (estado_watchdog.get("persistencia_estado_watchdog") or {}).get(
            "persistido_em"
        )
    )
    processo_iniciado_em = processo_watchdog.get("atualizado_em")
    try:
        persistido = datetime.fromisoformat(persistido_em)
        processo_iniciado = datetime.fromisoformat(processo_iniciado_em)
    except (TypeError, ValueError):
        return {
            "estado": "desconhecido",
            "fresco": False,
            "persistido_em": persistido_em,
            "processo_iniciado_em": processo_iniciado_em,
        }
    fresco = persistido >= processo_iniciado
    return {
        "estado": "fresco" if fresco else "anterior_ao_processo",
        "fresco": fresco,
        "persistido_em": persistido_em,
        "processo_iniciado_em": processo_iniciado_em,
    }


def diagnosticar_sincronizacao_historico_drift(
    auditoria_atual,
    auditoria_watchdog,
    supervisao_watchdog,
    processos,
    persistencia_watchdog,
    agora=None,
    tolerancia_minutos=10,
):
    """Reconhece apenas a janela curta entre a decisao e o proximo ciclo."""
    auditoria_atual = dict(auditoria_atual or {})
    auditoria_watchdog = dict(auditoria_watchdog or {})
    supervisao_watchdog = dict(supervisao_watchdog or {})
    processos = dict(processos or {})
    persistencia_watchdog = dict(persistencia_watchdog or {})
    ausentes = list(
        auditoria_atual.get("chaves_atuais_ausentes") or []
    )
    agora = agora or datetime.now()
    try:
        persistido = datetime.fromisoformat(
            persistencia_watchdog.get("persistido_em")
        )
        idade_minutos = (agora - persistido).total_seconds() / 60
    except (TypeError, ValueError):
        idade_minutos = None
    persistencia_fresca = bool(
        idade_minutos is not None
        and -2 <= idade_minutos <= float(tolerancia_minutos)
    )
    sincronizando = bool(
        auditoria_atual.get("estado") == "inconsistente"
        and not auditoria_atual.get("saudavel")
        and ausentes
        and len(ausentes) <= max(
            1, int(auditoria_watchdog.get("chaves_atuais", 0) or 0)
        )
        and not (auditoria_atual.get("chaves_atuais_divergentes") or [])
        and int(auditoria_atual.get("json_invalidos", 0) or 0) == 0
        and int(auditoria_atual.get("chaves_duplicadas", 0) or 0) == 0
        and auditoria_watchdog.get("saudavel")
        and auditoria_watchdog.get("estado") == "integro"
        and supervisao_watchdog.get("fresco")
        and processos.get("watchdog_ativo")
        and persistencia_watchdog.get("saudavel")
        and persistencia_watchdog.get("estado") == "persistido"
        and persistencia_fresca
    )
    if sincronizando:
        motivo = "aguardando_proximo_ciclo_watchdog"
    elif not ausentes:
        motivo = "sem_chaves_pendentes"
    elif auditoria_atual.get("chaves_atuais_divergentes"):
        motivo = "valores_divergentes"
    elif not persistencia_fresca:
        motivo = "persistencia_watchdog_desatualizada"
    else:
        motivo = "nao_e_sincronizacao_transitoria"
    return {
        "sincronizando": sincronizando,
        "motivo": motivo,
        "ausentes": ausentes,
        "idade_persistencia_minutos": idade_minutos,
        "tolerancia_minutos": float(tolerancia_minutos),
    }


def diagnosticar_integridade_banco_ativo(
    auditoria, agora=None, tolerancia_minutos=20
):
    auditoria = dict(auditoria or {})
    agora = agora or datetime.now()
    try:
        verificado = datetime.fromisoformat(auditoria.get("verificado_em"))
        idade_minutos = (agora - verificado).total_seconds() / 60
    except (TypeError, ValueError):
        idade_minutos = None
    fresco = bool(
        idade_minutos is not None
        and -2 <= idade_minutos <= float(tolerancia_minutos)
    )
    pronto = bool(
        auditoria.get("saudavel")
        and auditoria.get("estado") == "integro"
        and not auditoria.get("recuperacao_necessaria")
        and fresco
    )
    if pronto:
        estado = "pronto"
    elif auditoria.get("recuperacao_necessaria"):
        estado = "recuperacao_necessaria"
    elif auditoria.get("estado") == "integro" and not fresco:
        estado = "verificacao_desatualizada"
    elif not auditoria:
        estado = "aguardando_primeira_verificacao"
    else:
        estado = auditoria.get("estado") or "indisponivel"
    return {
        "pronto": pronto,
        "estado": estado,
        "fresco": fresco,
        "idade_minutos": (
            round(idade_minutos, 2) if idade_minutos is not None else None
        ),
        "tolerancia_minutos": float(tolerancia_minutos),
        "verificado_em": auditoria.get("verificado_em"),
        "proxima_verificacao_em": auditoria.get(
            "proxima_verificacao_em"
        ),
        "motivo": auditoria.get("motivo"),
        "recuperacao_necessaria": bool(
            auditoria.get("recuperacao_necessaria")
        ),
    }


def diagnosticar_fonte_odds_thestatsapi(configuracao, coleta):
    """Confirma que o modo configurado da TheStats coincide com o runtime."""
    configuracao = dict(configuracao or {})
    coleta = dict(coleta or {})
    fonte = dict(coleta.get("thestatsapi_sombra") or {})
    chave_configurada = bool(configuracao.get("chave_configurada"))
    ativa_configurada = bool(configuracao.get("sombra_ativa"))
    oficial_configurada = bool(configuracao.get("aplicacao_sinais"))

    if not chave_configurada or not ativa_configurada:
        return {
            "pronto": True,
            "estado": "pronto",
            "modo": "desativada_intencionalmente",
            "oficial": False,
            "divergencias": [],
            "estado_ciclo": fonte.get("estado"),
            "erros": int(fonte.get("erros", 0) or 0),
            "erros_por_codigo": dict(
                fonte.get("erros_por_codigo") or {}
            ),
        }

    if not fonte:
        return {
            "pronto": False,
            "estado": "sincronizando",
            "modo": (
                "oficial_fail_closed" if oficial_configurada else "sombra"
            ),
            "oficial": oficial_configurada,
            "divergencias": ["ciclo_sem_diagnostico_thestatsapi"],
            "estado_ciclo": None,
            "erros": 0,
            "erros_por_codigo": {},
        }

    divergencias = []
    if fonte.get("ativa") is not True:
        divergencias.append("runtime_inativo")
    if fonte.get("disponivel") is not True:
        divergencias.append("fonte_indisponivel")
    if bool(fonte.get("aplicacao_sinais")) != oficial_configurada:
        divergencias.append("aplicacao_sinais_divergente")
    if bool(fonte.get("telegram")) != oficial_configurada:
        divergencias.append("telegram_divergente")
    if fonte.get("calibracao") is not False:
        divergencias.append("calibracao_indevidamente_ativa")
    if fonte.get("substitui_packball") is not False:
        divergencias.append("packball_indevidamente_substituido")
    if oficial_configurada:
        if fonte.get("modo") != "oficial_fail_closed":
            divergencias.append("modo_oficial_divergente")
        if fonte.get("sem_autorizacao_sinal") is not False:
            divergencias.append("gate_oficial_sem_autorizacao")
    else:
        if fonte.get("modo") != "sombra":
            divergencias.append("modo_sombra_divergente")
        if fonte.get("sem_autorizacao_sinal") is not True:
            divergencias.append("sombra_com_autorizacao_sinal")

    estado_ciclo = str(fonte.get("estado") or "").strip()
    falha_total = bool(
        not estado_ciclo
        or estado_ciclo in {
            "falha_isolada",
            "falha_isolada_lista",
            "sem_chave",
            "desativada",
        }
    )
    if falha_total:
        divergencias.append("coleta_indisponivel_no_ultimo_ciclo")
    pronto = not divergencias
    return {
        "pronto": pronto,
        "estado": "pronto" if pronto else "degradado",
        "modo": fonte.get("modo"),
        "oficial": oficial_configurada,
        "divergencias": sorted(set(divergencias)),
        "estado_ciclo": estado_ciclo or None,
        "parcial": estado_ciclo.endswith("_parcial"),
        "erros": int(fonte.get("erros", 0) or 0),
        "erros_por_codigo": dict(fonte.get("erros_por_codigo") or {}),
        "chamadas_rede": int(fonte.get("chamadas_rede", 0) or 0),
        "pareadas": int(fonte.get("pareadas", 0) or 0),
        "tentativas_pareamento": int(
            fonte.get("tentativas_pareamento", 0) or 0
        ),
        "partidas_com_odds": int(
            fonte.get("partidas_com_odds", 0) or 0
        ),
        "ofertas_persistidas": int(
            fonte.get("ofertas_odds_persistidas", 0) or 0
        ),
        "rollback": fonte.get("desligar_com"),
    }


def diagnosticar_fonte_odds_betsapi(configuracao, coleta):
    """Confirma que a BetsAPI oficial coincide com o runtime supervisionado."""
    configuracao = dict(configuracao or {})
    coleta = dict(coleta or {})
    fonte = dict(coleta.get("betsapi") or {})
    chave_configurada = bool(configuracao.get("chave_configurada"))
    ativa_configurada = bool(configuracao.get("ativa"))
    oficial_configurada = bool(configuracao.get("aplicacao_sinais"))

    if not chave_configurada or not ativa_configurada:
        return {
            "pronto": True,
            "estado": "pronto",
            "modo": "desativada_intencionalmente",
            "oficial": False,
            "divergencias": [],
            "circuito_aberto": bool(fonte.get("circuito_aberto")),
        }

    if not fonte:
        return {
            "pronto": False,
            "estado": "sincronizando",
            "modo": configuracao.get("modo"),
            "oficial": oficial_configurada,
            "divergencias": ["ciclo_sem_diagnostico_betsapi"],
            "circuito_aberto": False,
        }

    divergencias = []
    if fonte.get("ativa") is not True:
        divergencias.append("runtime_inativo")
    if bool(fonte.get("aplicacao_sinais")) != oficial_configurada:
        divergencias.append("aplicacao_sinais_divergente")
    if fonte.get("circuito_aberto") is True:
        divergencias.append("circuito_aberto")

    for nome_runtime, nome_configuracao in (
        ("hora", "hora"),
        ("dia", "diario"),
    ):
        uso = int(fonte.get(f"uso_{nome_runtime}", 0) or 0)
        limite_runtime = int(
            fonte.get(f"limite_{nome_configuracao}", 0) or 0
        )
        limite_configurado = int(
            configuracao.get(f"limite_{nome_configuracao}", 0) or 0
        )
        if limite_runtime <= 0:
            divergencias.append(
                f"limite_{nome_configuracao}_runtime_ausente"
            )
        elif limite_configurado and limite_runtime != limite_configurado:
            divergencias.append(f"limite_{nome_configuracao}_divergente")
        if limite_runtime > 0 and uso > limite_runtime:
            divergencias.append(f"cota_{nome_runtime}_excedida")

    pronto = not divergencias
    return {
        "pronto": pronto,
        "estado": "pronto" if pronto else "degradado",
        "modo": configuracao.get("modo"),
        "oficial": oficial_configurada,
        "divergencias": sorted(set(divergencias)),
        "circuito_aberto": bool(fonte.get("circuito_aberto")),
        "uso_hora": int(fonte.get("uso_hora", 0) or 0),
        "limite_hora": int(fonte.get("limite_hora", 0) or 0),
        "uso_dia": int(fonte.get("uso_dia", 0) or 0),
        "limite_diario": int(fonte.get("limite_diario", 0) or 0),
        "partidas_pareadas": int(
            fonte.get("partidas_pareadas", 0) or 0
        ),
        "partidas_consultadas": int(
            fonte.get("partidas_consultadas", 0) or 0
        ),
        "mercados_anexados": int(
            fonte.get("mercados_anexados", 0) or 0
        ),
    }


def diagnosticar_cota_api_football(contador, agora=None):
    """Separa integridade do contador da indisponibilidade diária esperada."""
    contador = dict(contador or {})
    limite = contador.get("limite_diario_seguro")
    if limite is None:
        limite = contador.get("limite_confirmado_provedor")
    consumo = contador.get("consumo_dia")
    restante = contador.get("restante_seguro_dia")
    try:
        limite = int(limite)
        consumo = int(consumo)
        restante = (
            max(limite - consumo, 0)
            if restante is None else max(int(restante), 0)
        )
    except (TypeError, ValueError):
        return {
            "pronto": False,
            "estado": "degradado",
            "motivo": "contador_sem_limite_ou_consumo",
            "limite_seguro": limite,
            "consumo": consumo,
            "restante": restante,
            "proximo_reset_utc": None,
            "segundos_ate_reset": None,
        }
    if not contador.get("saudavel") or limite <= 0:
        return {
            "pronto": False,
            "estado": "degradado",
            "motivo": "contador_api_inseguro",
            "limite_seguro": limite,
            "consumo": consumo,
            "restante": restante,
            "proximo_reset_utc": None,
            "segundos_ate_reset": None,
        }
    if restante > 0:
        return {
            "pronto": True,
            "estado": "pronto",
            "motivo": None,
            "limite_seguro": limite,
            "consumo": consumo,
            "restante": restante,
            "proximo_reset_utc": None,
            "segundos_ate_reset": None,
        }

    agora = agora or datetime.now().astimezone()
    if agora.tzinfo is None:
        agora = agora.astimezone()
    agora_utc = agora.astimezone(timezone.utc)
    proximo_dia = agora_utc.date() + timedelta(days=1)
    reset_utc = datetime.combine(
        proximo_dia, datetime.min.time(), tzinfo=timezone.utc
    )
    return {
        "pronto": False,
        "estado": "aguardando_reset_cota",
        "motivo": "cota_segura_diaria_esgotada",
        "limite_seguro": limite,
        "consumo": consumo,
        "restante": 0,
        "proximo_reset_utc": reset_utc.isoformat(),
        "segundos_ate_reset": max(
            int((reset_utc - agora_utc).total_seconds()), 0
        ),
    }


def _classificar_diagnostico_pre_calibracao(metricas):
    metricas = metricas or {}
    amostra = int(metricas.get("amostra", 0) or 0)
    roi = metricas.get("roi")
    if amostra < 30 or roi is None:
        return "amostra_inicial"
    if float(roi) <= 0:
        return "desempenho_desfavoravel_pre_validacao"
    return "desempenho_positivo_ainda_nao_comprovado"


AVALIACOES_EXPOSICAO_PROSPECTIVA = (
    "acompanhamento_odd",
    "prioridade_ligas_gols",
    "desajuste_odds",
    "quarentena_fallback_ht",
)


def diagnosticar_exposicao_coleta_prospectiva(avaliacoes):
    """Audita os relógios V30 sem inferir amostra a partir do tempo."""
    avaliacoes = avaliacoes if isinstance(avaliacoes, dict) else {}
    problemas = []
    por_avaliacao = {}
    total_coortes = 0
    total_observadas = 0
    total_pausadas = 0
    for nome in AVALIACOES_EXPOSICAO_PROSPECTIVA:
        avaliacao = avaliacoes.get(nome) or {}
        exposicao = avaliacao.get("exposicao_coleta_prospectiva") or {}
        problemas_item = []
        if not avaliacao:
            problemas_item.append("avaliacao_ausente")
        if avaliacao.get("custodia_execucao_compativel") is not True:
            problemas_item.append("custodia_invalida")
        if (avaliacao.get("cronologia_execucao") or {}).get("valida") is not True:
            problemas_item.append("cronologia_invalida")
        if (avaliacao.get("efeitos_operacionais") or {}).get("valida") is not True:
            problemas_item.append("efeitos_avaliacao_invalidos")
        if not exposicao:
            problemas_item.append("relogio_ausente")
        elif exposicao.get("versao") != VERSAO_EXPOSICAO_COLETA_PROSPECTIVA:
            problemas_item.append("versao_relogio_invalida")
        if exposicao.get("estado") == "sem_ancora_prospectiva":
            problemas_item.append("ancora_ausente")
        if exposicao.get("saudavel") is not True:
            problemas_item.append("relogio_nao_saudavel")
        if exposicao.get("requer_atencao") is not False:
            problemas_item.append("relogio_requer_atencao")
        efeitos_invalidos = [
            chave for chave in EFEITOS_DESATIVADOS
            if exposicao.get(chave) is not False
        ]
        if efeitos_invalidos:
            problemas_item.append("efeitos_relogio_invalidos")
        total_coortes += int(exposicao.get("coortes") or 0)
        total_observadas += int(
            exposicao.get("coortes_com_exposicao") or 0
        )
        total_pausadas += int(
            exposicao.get("coortes_sem_exposicao_por_manutencao") or 0
        )
        por_avaliacao[nome] = {
            "estado": exposicao.get("estado"),
            "versao": exposicao.get("versao"),
            "saudavel": exposicao.get("saudavel") is True,
            "requer_atencao": exposicao.get("requer_atencao"),
            "coortes": int(exposicao.get("coortes") or 0),
            "coortes_com_exposicao": int(
                exposicao.get("coortes_com_exposicao") or 0
            ),
            "coortes_sem_exposicao_por_manutencao": int(
                exposicao.get(
                    "coortes_sem_exposicao_por_manutencao"
                ) or 0
            ),
            "problemas": problemas_item,
        }
        problemas.extend(
            f"{nome}:{problema}" for problema in problemas_item
        )
    pronto = not problemas
    return {
        "versao": "diagnostico-exposicao-coleta-prospectiva-v1",
        "estado": "pronto" if pronto else "degradado",
        "pronto": pronto,
        "avaliacoes_esperadas": len(AVALIACOES_EXPOSICAO_PROSPECTIVA),
        "avaliacoes_auditadas": sum(
            int(bool(avaliacoes.get(nome)))
            for nome in AVALIACOES_EXPOSICAO_PROSPECTIVA
        ),
        "coortes": total_coortes,
        "coortes_com_exposicao": total_observadas,
        "coortes_sem_exposicao_por_manutencao": total_pausadas,
        "problemas": problemas,
        "por_avaliacao": por_avaliacao,
        "tempo_de_parede_conta_como_amostra": False,
        **{chave: False for chave in EFEITOS_DESATIVADOS},
    }


def avaliar_prontidao(evidencias):
    mercados_exigidos = tuple(
        evidencias.get("mercados_exigidos", MERCADOS_CALIBRADOS)
    )
    mercados_suspensos = tuple(
        mercado for mercado in MERCADOS_CALIBRADOS
        if mercado not in mercados_exigidos
    )
    componentes = {}
    clv_live = evidencias.get("clv_live") or {}
    cadeia_custodia_clv = clv_live.get("cadeia_custodia_clv") or {}
    cadeia_custodia_clv_auditada = bool(
        clv_live.get("versao") == VERSAO_AVALIACAO_CLV_LIVE
    )
    cadeia_custodia_clv_ok = bool(
        not cadeia_custodia_clv_auditada
        or cadeia_custodia_clv.get("saudavel") is True
    )
    if cadeia_custodia_clv_auditada:
        componentes["cadeia_custodia_clv"] = _componente(
            "pronto" if cadeia_custodia_clv_ok else "inconsistente",
            (
                "entregas, sinais, snapshots e odds CLV imutaveis"
                if cadeia_custodia_clv_ok
                else "a avaliacao de vantagem esta bloqueada porque a "
                     "cadeia de custodia CLV esta ausente ou invalida"
            ),
            versao=cadeia_custodia_clv.get("versao"),
            estado_custodia=cadeia_custodia_clv.get("estado"),
            gatilhos_ausentes=cadeia_custodia_clv.get(
                "gatilhos_ausentes"
            ) or [],
            definicoes_invalidas=cadeia_custodia_clv.get(
                "definicoes_invalidas"
            ) or [],
            fingerprint_definicoes=cadeia_custodia_clv.get(
                "fingerprint_definicoes"
            ),
            integridade_evidencias=cadeia_custodia_clv.get(
                "integridade_evidencias"
            ) or {},
            bloqueia_inferencia=bool(
                cadeia_custodia_clv.get("bloqueia_inferencia")
            ),
        )
    portfolio_edge_auditado = "portfolio_edge" in evidencias
    portfolio_edge = evidencias.get("portfolio_edge") or {}
    portfolio_edge_ok = bool(
        not portfolio_edge_auditado
        or portfolio_edge.get("todos_mercados_com_edge_comprovado") is True
    )
    if portfolio_edge_auditado:
        componentes["portfolio_edge"] = _componente(
            "pronto" if portfolio_edge_ok else "pendente_amostra",
            (
                "todos os mercados ativos comprovaram edge fora da amostra"
                if portfolio_edge_ok
                else "nenhuma mudança ampla: mercados ainda sem edge "
                     "independente comprovado"
            ),
            versao=portfolio_edge.get("versao"),
            versao_referencia_preco_sem_vig=portfolio_edge.get(
                "versao_referencia_preco_sem_vig"
            ),
            versao_avaliacao_historica_escanteios_asiaticos=(
                portfolio_edge.get(
                    "versao_avaliacao_historica_escanteios_asiaticos"
                )
            ),
            mercados_favoraveis=portfolio_edge.get(
                "mercados_favoraveis_para_revisao_manual"
            ) or [],
            regras_por_mercado=portfolio_edge.get(
                "regras_por_mercado"
            ) or {},
            decisoes={
                mercado: (item.get("decisao") or {}).get("estado")
                for mercado, item in (
                    portfolio_edge.get("avaliacoes") or {}
                ).items()
            },
            coortes_selecao={
                mercado: (
                    item.get("coorte_selecao_avaliada")
                    or item.get("coorte_operacional_avaliada")
                )
                for mercado, item in (
                    portfolio_edge.get("avaliacoes") or {}
                ).items()
            },
            amostras_entregues={
                mercado: {
                    "candidatos": (
                        item.get("auditoria_coorte_entregue") or {}
                    ).get("candidatos_coorte_fixa"),
                    "validos": (
                        item.get("auditoria_coorte_entregue") or {}
                    ).get("linhas_resultado_valido"),
                    "pendentes": (
                        item.get("auditoria_coorte_entregue") or {}
                    ).get("linhas_sem_resultado_valido"),
                }
                for mercado, item in (
                    portfolio_edge.get("avaliacoes") or {}
                ).items()
            },
            promocao_automatica=False,
        )
    modo_manutencao = evidencias.get("modo_manutencao") or {}
    modo_manutencao_invalido = bool(
        modo_manutencao.get("ativo")
        and modo_manutencao.get("motivo")
        == "arquivo_manutencao_invalido"
    )
    pausa_planejada = bool(
        modo_manutencao.get("ativo") and not modo_manutencao_invalido
    )
    exposicao_auditada = "avaliacoes_periodicas" in evidencias
    exposicao_coleta = diagnosticar_exposicao_coleta_prospectiva(
        evidencias.get("avaliacoes_periodicas") or {}
    )
    exposicao_coleta_ok = bool(
        not exposicao_auditada or exposicao_coleta.get("pronto")
    )
    worker_treino_auditado = "worker_treino_isolado" in evidencias
    worker_treino = evidencias.get("worker_treino_isolado") or {}
    worker_treino_ok = bool(
        not worker_treino_auditado
        or (
            worker_treino.get("saudavel") is True
            and worker_treino.get("estado") in {"pronto", "recuperado"}
            and worker_treino.get("protocolo")
            == PROTOCOLO_TREINO_ISOLADO
        )
    )
    processos = evidencias.get("processos") or {}
    validacao = evidencias.get("validacao") or {}
    prioridade_scanner = (
        validacao.get("prioridade_scanner_packball") or {}
    )
    prioridade_scanner_auditada = bool(prioridade_scanner)
    prioridade_scanner_ok = bool(
        not prioridade_scanner_auditada
        or prioridade_scanner.get("saudavel")
    )
    coleta = evidencias.get("coleta") or {}
    diagnostico_v2_ultimo_ciclo = (
        coleta.get("gols_capacidade_contextual_v2") or {}
    )
    backup = evidencias.get("backup") or {}
    backup_espelho_auditado = "backup_espelho" in evidencias
    backup_espelho = evidencias.get("backup_espelho") or {}
    historico_drift = evidencias.get("historico_drift") or {}
    hipoteses_sombra = (
        (validacao.get("hipoteses_sombra") or {}).get("integridade")
        or {}
    )
    validacao_gols_antecipados = (
        validacao.get("validacao_gols_antecipados") or {}
    )
    validacao_v2b_ft_grupo = (
        validacao.get("validacao_grupo_gol_ft_capacidade_v2") or {}
    )
    progresso_v2b_ft_grupo = (
        validacao.get("progresso_grupo_gol_ft_capacidade_v2") or {}
    )
    v2b_ft_grupo_ativo = bool(
        (evidencias.get("metodos_grupo") or {}).get("v2b_ft_ativo")
    )
    controle_v2b_ft = (
        (evidencias.get("metodos_grupo") or {}).get("controle_v2b_ft")
        or {}
    )
    controle_v2b_ft_ok = bool(
        not controle_v2b_ft or controle_v2b_ft.get("saudavel")
    )
    v2b_ft_auditado = bool(
        validacao_v2b_ft_grupo or progresso_v2b_ft_grupo
    )
    v2b_ft_integridade_ok = bool(
        not v2b_ft_auditado
        or (
            controle_v2b_ft_ok
            and validacao_v2b_ft_grupo.get("saudavel")
            and validacao_v2b_ft_grupo.get("estado") == "valida"
        )
    )
    v2b_ft_rollback_recomendado = bool(
        progresso_v2b_ft_grupo.get("rollback_recomendado")
    )
    progresso_proximo_gol_balanceado = (
        validacao.get("progresso_proximo_gol_balanceado_sombra") or {}
    )
    metodos_grupo = evidencias.get("metodos_grupo") or {}
    controle_proximo_gol_balanceado = (
        metodos_grupo.get("controle_proximo_gol_balanceado")
        or validacao.get("controle_operacional_proximo_gol_balanceado")
        or {}
    )
    proximo_gol_balanceado_auditado = bool(
        progresso_proximo_gol_balanceado
        and progresso_proximo_gol_balanceado.get("estado")
        not in {None, "nao_registrada"}
    )
    pontuacao_sombra = validacao.get("pontuacao_sombra") or {}
    pontuacao_contexto_sombra = (
        validacao.get("pontuacao_contexto_sombra") or {}
    )
    pontuacao_longa_sombra = (
        validacao.get("pontuacao_longa_sombra") or {}
    )
    auditoria_ligas_sombra = (
        validacao.get("auditoria_ligas_sombra") or {}
    )
    historico_contexto = (
        validacao.get("historico_avaliacao_contexto") or {}
    )
    persistencia_watchdog = (
        evidencias.get("persistencia_estado_watchdog") or {}
    )
    pre_live = evidencias.get("pre_live") or {}
    pre_live_banco = pre_live.get("banco") or {}
    pre_live_backup = pre_live.get("backup") or {}
    pre_live_filtro_preciso = pre_live.get("filtro_preciso") or {}
    pre_live_controle_preciso = (
        pre_live.get("controle_filtro_preciso")
        or pre_live_filtro_preciso.get("controle_operacional")
        or {}
    )
    pre_live_controle_preciso_ok = bool(
        not pre_live_controle_preciso
        or (
            pre_live_controle_preciso.get("saudavel")
            and pre_live_controle_preciso.get("ativo")
        )
    )
    pre_live_operacional_ok = bool(
        pre_live.get("saudavel")
        and pre_live.get("estado") == "ativo"
        and pre_live_banco.get("valido")
        and pre_live_backup.get("saudavel")
        and pre_live_backup.get("fresco")
        and pre_live_controle_preciso_ok
    )
    pre_live_validacao_prospectiva = bool(
        pre_live_filtro_preciso
        and pre_live_filtro_preciso.get("estado")
        not in {None, "nao_registrada"}
    )
    if pre_live_validacao_prospectiva:
        pre_live_resultados = int(
            pre_live_filtro_preciso.get("validos") or 0
        )
        pre_live_amostra_minima = int(
            pre_live_filtro_preciso.get("tamanho_coorte") or 60
        )
        pre_live_validacao_ok = bool(
            pre_live_filtro_preciso.get("apto_revisao")
        )
        pre_live_roi = pre_live_filtro_preciso.get("roi")
    else:
        pre_live_resultados = int(pre_live.get("resultados") or 0)
        pre_live_amostra_minima = 30
        pre_live_validacao_ok = bool(pre_live.get("apto_revisao"))
        pre_live_roi = pre_live.get("roi")
    try:
        agora_evidencias = datetime.fromisoformat(evidencias.get("agora"))
    except (TypeError, ValueError):
        agora_evidencias = datetime.now()
    acesso_packball = diagnosticar_acesso_packball(
        evidencias.get("acesso_packball") or {},
        agora=agora_evidencias,
    )
    acesso_packball_ok = acesso_packball["pronto"]
    integridade_banco_ativo = diagnosticar_integridade_banco_ativo(
        evidencias.get("integridade_banco_ativo") or {},
        agora=agora_evidencias,
    )
    integridade_banco_ativo_ok = integridade_banco_ativo["pronto"]
    integridade_desatualizada_por_pausa = bool(
        pausa_planejada
        and not integridade_banco_ativo.get("recuperacao_necessaria")
        and integridade_banco_ativo.get("estado") in {
            "verificacao_desatualizada",
            "aguardando_primeira_verificacao",
        }
    )
    configuracao = evidencias.get("configuracao") or {}
    fonte_odds_thestatsapi = diagnosticar_fonte_odds_thestatsapi(
        configuracao.get("thestatsapi") or {},
        coleta,
    )
    fonte_odds_thestatsapi_ok = fonte_odds_thestatsapi["pronto"]
    fonte_odds_betsapi = diagnosticar_fonte_odds_betsapi(
        configuracao.get("betsapi") or {},
        coleta,
    )
    fonte_odds_betsapi_ok = fonte_odds_betsapi["pronto"]
    mercados_fluxo_operacionais = set(
        mercados_calibrados_operacionais()
    )
    mercados_fluxo_exigidos = tuple(
        mercado for mercado in mercados_exigidos
        if mercado in mercados_fluxo_operacionais
    )
    fluxo_amostras_ativas = diagnosticar_fluxo_amostras_ativas(
        evidencias.get("fluxo_amostras_ativas") or {},
        coleta,
        processos,
        mercados_fluxo_exigidos,
        agora=agora_evidencias,
    )
    fluxo_amostras_ativas["mercados_auditados"] = list(
        mercados_fluxo_exigidos
    )
    if pausa_planejada:
        fluxo_amostras_ativas.update({
            "estado_sem_dependencia": fluxo_amostras_ativas.get("estado"),
            "motivo_sem_dependencia": fluxo_amostras_ativas.get("motivo"),
            "pronto": False,
            "estado": "pausa_planejada",
            "motivo": "coleta_pausada_por_manutencao_manual",
            "dependencia_raiz": "modo_manutencao",
        })
    elif not acesso_packball_ok:
        fluxo_amostras_ativas.update({
            "estado_sem_dependencia": fluxo_amostras_ativas.get("estado"),
            "motivo_sem_dependencia": fluxo_amostras_ativas.get("motivo"),
            "pronto": False,
            "estado": acesso_packball["estado"],
            "motivo": "coleta_packball_pausada",
            "dependencia_raiz": "acesso_packball",
        })
    fluxo_amostras_ativas_ok = fluxo_amostras_ativas["pronto"]
    ritmo_acesso = validacao.get("ritmo_acesso_packball") or {}
    experimento_ritmo = validacao.get("experimento_ritmo_packball") or {}
    ritmo_auditado = bool(
        ritmo_acesso.get("saudavel")
        and ritmo_acesso.get("estado") == "seguro"
    )
    historico_drift_ok = bool(
        historico_drift.get("saudavel")
        and historico_drift.get("estado") == "integro"
        and int(historico_drift.get("chaves_atuais", 0) or 0) > 0
    )
    historico_drift_aguardando_amostra = bool(
        historico_drift.get("saudavel")
        and historico_drift.get("estado") == "aguardando_resultados"
        and int(historico_drift.get("total", 0) or 0) == 0
        and not (historico_drift.get("chaves_atuais_ausentes") or [])
        and not (historico_drift.get("chaves_atuais_divergentes") or [])
        and int(historico_drift.get("json_invalidos", 0) or 0) == 0
        and int(historico_drift.get("chaves_duplicadas", 0) or 0) == 0
    )
    sincronizacao_historico_drift = (
        diagnosticar_sincronizacao_historico_drift(
            historico_drift,
            evidencias.get("historico_drift_watchdog") or {},
            evidencias.get("supervisao_watchdog") or {},
            processos,
            persistencia_watchdog,
            agora=agora_evidencias,
        )
    )
    historico_drift_sincronizando = bool(
        sincronizacao_historico_drift.get("sincronizando")
    )
    historico_drift_operacional_ok = bool(
        historico_drift_ok
        or historico_drift_aguardando_amostra
        or historico_drift_sincronizando
    )
    persistencia_watchdog_ok = bool(
        persistencia_watchdog.get("saudavel")
        and persistencia_watchdog.get("estado") == "persistido"
    )
    hipoteses_sombra_ok = bool(hipoteses_sombra.get("saudavel"))
    validacao_gols_antecipados_ok = bool(
        not validacao_gols_antecipados
        or validacao_gols_antecipados.get("saudavel")
    )
    modelos_sombra_ok = bool(
        pontuacao_sombra.get("integro")
        and pontuacao_contexto_sombra.get("integro")
        and pontuacao_longa_sombra.get("integro")
    )
    auditoria_ligas_sombra_ok = bool(
        auditoria_ligas_sombra.get("integro")
        and auditoria_ligas_sombra.get("aplicacao_automatica") is False
        and all(
            mercado in (auditoria_ligas_sombra.get("por_mercado") or {})
            for mercado in mercados_exigidos
            if mercado in MERCADOS_AUDITADOS
        )
    )
    historico_contexto_ok = bool(
        historico_contexto.get("saudavel")
    )
    supervisao_inicializando = bool(
        (evidencias.get("supervisao_watchdog") or {}).get(
            "inicializando"
        )
    )
    operacao_ok = bool(
        not modo_manutencao.get("ativo")
        and configuracao.get("valida")
        and coleta.get("saudavel")
        and validacao.get("saudavel")
        and ritmo_auditado
        and backup.get("saudavel")
        and historico_drift_operacional_ok
        and hipoteses_sombra_ok
        and validacao_gols_antecipados_ok
        and v2b_ft_integridade_ok
        and modelos_sombra_ok
        and auditoria_ligas_sombra_ok
        and historico_contexto_ok
        and persistencia_watchdog_ok
        and integridade_banco_ativo_ok
        and pre_live_operacional_ok
        and fonte_odds_thestatsapi_ok
        and fonte_odds_betsapi_ok
        and fluxo_amostras_ativas_ok
        and prioridade_scanner_ok
        and exposicao_coleta_ok
        and worker_treino_ok
        and processos.get("monitor_ativo")
        and processos.get("watchdog_ativo")
        and processos.get("monitor_codigo") == "atualizado"
        and processos.get("watchdog_codigo") == "atualizado"
    )
    estado_operacao = (
        "pronto"
        if operacao_ok
        else "pausa_planejada"
        if pausa_planejada
        else acesso_packball["estado"]
        if not acesso_packball_ok
        else "inicializando"
        if supervisao_inicializando
        else "degradado"
    )
    componentes["modo_manutencao"] = _componente(
        (
            "degradado" if modo_manutencao_invalido
            else "pausa_planejada" if pausa_planejada
            else "pronto"
        ),
        (
            "operação pausada intencionalmente; autorreinício bloqueado"
            if pausa_planejada
            else "arquivo de manutenção inválido; fail-safe ativo"
            if modo_manutencao_invalido
            else "operação não está em manutenção"
        ),
        ativo=bool(modo_manutencao.get("ativo")),
        motivo=modo_manutencao.get("motivo"),
        solicitado_em=modo_manutencao.get("solicitado_em"),
    )
    if exposicao_auditada:
        componentes["exposicao_coleta_prospectiva"] = _componente(
            "pronto" if exposicao_coleta_ok else "degradado",
            (
                "relógios prospectivos íntegros; pausa e exposição real "
                "permanecem separadas"
                if exposicao_coleta_ok
                else "um ou mais relógios prospectivos perderam custódia, "
                     "telemetria ou continuidade de coleta"
            ),
            **{
                chave: valor for chave, valor in exposicao_coleta.items()
                if chave not in {"estado", "pronto"}
            },
        )
    if worker_treino_auditado:
        componentes["worker_treino_isolado"] = _componente(
            "pronto" if worker_treino_ok else "degradado",
            (
                "worker de treinamento isolado respondeu ao desafio local"
                if worker_treino_ok
                else "retomada bloqueada: worker de treinamento isolado "
                     "não respondeu de forma íntegra"
            ),
            **{
                chave: valor for chave, valor in worker_treino.items()
                if chave not in {"saudavel", "estado"}
            },
        )
    componentes["acesso_packball"] = _componente(
        acesso_packball["estado"],
        (
            "sessão PackBall disponível para coleta oficial"
            if acesso_packball_ok
            else "coleta oficial aguarda uma sessão válida do PackBall"
            if acesso_packball["estado"] == "aguardando_login_packball"
            else "circuit breaker do PackBall está em pausa de segurança"
        ),
        **{
            chave: valor
            for chave, valor in acesso_packball.items()
            if chave not in {"estado", "pronto"}
        },
    )
    componentes["operacao_continua"] = _componente(
        estado_operacao,
        (
            "monitoramento, banco, backup e supervisão saudáveis"
            if operacao_ok
            else "operação pausada intencionalmente pelo usuário"
            if pausa_planejada
            else "operação oficial pausada até recuperar o acesso ao PackBall"
            if not acesso_packball_ok
            else "aguardando o primeiro espelho do watchdog atual"
            if supervisao_inicializando
            else "uma ou mais proteções operacionais falharam"
        ),
        configuracao_valida=bool(configuracao.get("valida")),
        coleta_saudavel=bool(coleta.get("saudavel")),
        validacao_saudavel=bool(validacao.get("saudavel")),
        ritmo_packball_seguro=ritmo_auditado,
        backup_saudavel=bool(backup.get("saudavel")),
        historico_drift_saudavel=historico_drift_operacional_ok,
        hipoteses_sombra_integras=hipoteses_sombra_ok,
        validacao_gols_antecipados_integra=(
            validacao_gols_antecipados_ok
        ),
        modelos_sombra_integros=modelos_sombra_ok,
        auditoria_ligas_sombra_integra=auditoria_ligas_sombra_ok,
        historico_contexto_integro=historico_contexto_ok,
        estado_watchdog_persistente=persistencia_watchdog_ok,
        integridade_banco_ativo=integridade_banco_ativo_ok,
        fonte_odds_thestatsapi=fonte_odds_thestatsapi_ok,
        fonte_odds_betsapi=fonte_odds_betsapi_ok,
        fluxo_amostras_ativas=fluxo_amostras_ativas_ok,
        exposicao_coleta_prospectiva=exposicao_coleta_ok,
        worker_treino_isolado=worker_treino_ok,
        dependencia_raiz=(
            "modo_manutencao" if pausa_planejada
            else "acesso_packball" if not acesso_packball_ok else None
        ),
        **processos,
    )
    if prioridade_scanner_auditada:
        componentes["prioridade_scanner_packball"] = _componente(
            "pronto" if prioridade_scanner_ok else "degradado",
            (
                "Scanner prioriza candidatos e mantém a lista Ao Vivo como "
                "cobertura"
                if prioridade_scanner_ok
                else "prioridade do Scanner indisponível de forma persistente"
            ),
            **{
                chave: valor
                for chave, valor in prioridade_scanner.items()
                if chave not in {"saudavel", "estado"}
            },
        )
    componentes["fonte_odds_thestatsapi"] = _componente(
        fonte_odds_thestatsapi["estado"],
        (
            "Bet365/TheStats em complemento oficial fail-closed e coerente"
            if fonte_odds_thestatsapi.get("oficial")
            and fonte_odds_thestatsapi_ok
            else "TheStats em coleta sombra coerente e sem autoridade oficial"
            if fonte_odds_thestatsapi.get("modo") == "sombra"
            and fonte_odds_thestatsapi_ok
            else "TheStats desativada intencionalmente; PackBall segue primario"
            if fonte_odds_thestatsapi_ok
            else "configuracao e runtime Bet365/TheStats nao coincidem"
        ),
        **{
            chave: valor
            for chave, valor in fonte_odds_thestatsapi.items()
            if chave not in {"estado", "pronto"}
        },
    )
    componentes["fonte_odds_betsapi"] = _componente(
        fonte_odds_betsapi["estado"],
        (
            "BetsAPI oficial ativa, dentro das cotas e sem circuito aberto"
            if fonte_odds_betsapi_ok and fonte_odds_betsapi.get("oficial")
            else "BetsAPI desativada intencionalmente"
            if fonte_odds_betsapi_ok
            else "configuracao ou runtime da BetsAPI estao divergentes"
        ),
        **{
            chave: valor
            for chave, valor in fonte_odds_betsapi.items()
            if chave not in {"estado", "pronto"}
        },
    )
    componentes["fluxo_amostras_ativas"] = _componente(
        fluxo_amostras_ativas["estado"],
        (
            "todos os mercados ativos persistem candidatos recentes"
            if fluxo_amostras_ativas_ok
            and fluxo_amostras_ativas.get("partidas_ultimo_ciclo", 0) > 0
            else "ultimo ciclo nao tinha jogos ao vivo; ausencia de amostra e legitima"
            if fluxo_amostras_ativas_ok
            else "um ou mais mercados deixaram de persistir amostras recentes"
        ),
        **{
            chave: valor
            for chave, valor in fluxo_amostras_ativas.items()
            if chave not in {"estado", "pronto"}
        },
    )
    componentes["integridade_banco_ativo"] = _componente(
        (
            "pausa_planejada"
            if integridade_desatualizada_por_pausa
            else integridade_banco_ativo["estado"]
        ),
        (
            "SQLite ativo auditado periodicamente e sem corrupcao"
            if integridade_banco_ativo_ok
            else "auditoria periodica do SQLite ativo requer atencao"
        ),
        fresco=integridade_banco_ativo["fresco"],
        idade_minutos=integridade_banco_ativo["idade_minutos"],
        tolerancia_minutos=integridade_banco_ativo["tolerancia_minutos"],
        verificado_em=integridade_banco_ativo["verificado_em"],
        proxima_verificacao_em=integridade_banco_ativo[
            "proxima_verificacao_em"
        ],
        motivo=integridade_banco_ativo["motivo"],
        recuperacao_necessaria=integridade_banco_ativo[
            "recuperacao_necessaria"
        ],
        estado_sem_dependencia=(
            integridade_banco_ativo["estado"]
            if integridade_desatualizada_por_pausa else None
        ),
        dependencia_raiz=(
            "modo_manutencao"
            if integridade_desatualizada_por_pausa else None
        ),
    )
    pre_live_pausado_com_dados_integros = bool(
        pausa_planejada
        and pre_live.get("estado") == "parado"
        and pre_live_banco.get("valido")
        and pre_live_backup.get("saudavel")
        and not pre_live.get("ultima_execucao_erro")
    )
    componentes["pre_live_operacional"] = _componente(
        (
            "pronto" if pre_live_operacional_ok
            else "pausa_planejada"
            if pre_live_pausado_com_dados_integros
            else "degradado"
        ),
        (
            "agendador, SQLite e backup pré-live estão saudáveis"
            if pre_live_operacional_ok
            else (
                "pré-live parado conforme manutenção; SQLite e backup "
                "permanecem íntegros"
                if pre_live_pausado_com_dados_integros
                else "processo, banco ou backup pré-live requer atenção"
            )
        ),
        processo_saudavel=bool(pre_live.get("saudavel")),
        estado_processo=pre_live.get("estado"),
        pid=pre_live.get("pid"),
        status_processo=pre_live.get("status_processo"),
        pid_responde=pre_live.get("pid_responde"),
        trava_ativa=pre_live.get("trava_ativa"),
        estado_watchdog_anterior=pre_live.get(
            "estado_watchdog_anterior"
        ),
        snapshot_watchdog_divergente=bool(
            pre_live.get("snapshot_watchdog_divergente")
        ),
        banco_valido=bool(pre_live_banco.get("valido")),
        backup_saudavel=bool(pre_live_backup.get("saudavel")),
        backup_fresco=bool(pre_live_backup.get("fresco")),
        backup_arquivo=pre_live_backup.get("arquivo"),
        backup_idade_horas=pre_live_backup.get("idade_horas"),
        candidatos_elegiveis=int(
            pre_live.get("candidatos_elegiveis") or 0
        ),
        jogos_analisados=int(pre_live.get("jogos_analisados") or 0),
        jogos_nao_analisados_limite=int(
            pre_live.get("jogos_nao_analisados_limite") or 0
        ),
        cobertura_analise=pre_live.get("cobertura_analise"),
        limite_analise=pre_live.get("limite_analise") or {},
        controle_filtro_preciso=pre_live_controle_preciso,
        filtro_preciso_liberado=pre_live_controle_preciso_ok,
        dependencia_raiz=(
            "modo_manutencao"
            if pre_live_pausado_com_dados_integros else None
        ),
    )
    componentes["seletor_pre_live_validacao"] = _componente(
        (
            "pronto" if pre_live_validacao_ok
            else "pendente_amostra"
            if pre_live_resultados < pre_live_amostra_minima
            else "reprovado_validacao"
        ),
        (
            "seleção pré-live superou amostra, ROI e limite inferior exigidos"
            if pre_live_validacao_ok
            else (
                "nova coorte pré-live continua prospectiva; vantagem ainda "
                "não foi comprovada"
            )
        ),
        resultados=pre_live_resultados,
        amostra_minima=pre_live_amostra_minima,
        roi=pre_live_roi,
        apto_revisao=pre_live_validacao_ok,
        validacao_prospectiva=pre_live_validacao_prospectiva,
        decisao=pre_live_filtro_preciso.get("decisao"),
        faltam=pre_live_filtro_preciso.get("faltam"),
        desenvolvimento=pre_live_filtro_preciso.get("desenvolvimento"),
        holdout=pre_live_filtro_preciso.get("holdout"),
        gate_preco_justo=pre_live_filtro_preciso.get("gate_preco_justo"),
        checkpoint_seguranca=pre_live_filtro_preciso.get(
            "checkpoint_seguranca"
        ),
        tamanho_coorte=pre_live_filtro_preciso.get("tamanho_coorte"),
        registrado_em=pre_live_filtro_preciso.get("registrado_em"),
        exposicao_coorte_prontidao=pre_live_filtro_preciso.get(
            "exposicao_coorte_prontidao"
        ),
        promocao_automatica=False,
    )
    if v2b_ft_auditado:
        estado_v2b_ft = (
            "degradado"
            if not v2b_ft_integridade_ok
            else "revisao_necessaria"
            if v2b_ft_rollback_recomendado
            else "pronto"
            if v2b_ft_grupo_ativo
            else "sombra"
        )
        resumo_v2b_ft = (
            "coorte ativa e íntegra; prontidão estatística é avaliada separadamente"
            if estado_v2b_ft == "pronto"
            else "evidencia negativa forte; retorno ao sombra recomendado"
            if estado_v2b_ft == "revisao_necessaria"
            else "coorte preservada, mas o envio ao grupo esta desativado"
            if estado_v2b_ft == "sombra"
            else "ancora ou linhagem da coorte V2b FT inconsistente"
        )
        componentes["gol_ft_v2b_grupo"] = _componente(
            estado_v2b_ft,
            resumo_v2b_ft,
            ativo=v2b_ft_grupo_ativo,
            versao=progresso_v2b_ft_grupo.get("versao_avaliada"),
            registrado_em=progresso_v2b_ft_grupo.get("registrado_em"),
            validos=int(progresso_v2b_ft_grupo.get("validos", 0) or 0),
            greens=int(progresso_v2b_ft_grupo.get("greens", 0) or 0),
            reds=int(progresso_v2b_ft_grupo.get("reds", 0) or 0),
            roi=progresso_v2b_ft_grupo.get("roi"),
            intervalo_roi_95=progresso_v2b_ft_grupo.get(
                "intervalo_roi_95"
            ),
            proximo_checkpoint=progresso_v2b_ft_grupo.get(
                "proximo_checkpoint"
            ),
            decisao=progresso_v2b_ft_grupo.get("decisao_estatistica"),
            rollback_recomendado=v2b_ft_rollback_recomendado,
            rollback=progresso_v2b_ft_grupo.get("rollback"),
            integridade=validacao_v2b_ft_grupo,
            controle_operacional=controle_v2b_ft,
            finalidade="integridade_operacional_do_metodo",
            ultimo_ciclo=diagnostico_v2_ultimo_ciclo,
        )
    backup_espelho_pronto = bool(
        not backup_espelho_auditado
        or (
            backup_espelho.get("configurado")
            and backup_espelho.get("saudavel")
            and backup_espelho.get("fora_dispositivo")
        )
    )
    componentes["backup_fora_dispositivo"] = _componente(
        (
            "pronto" if backup_espelho_pronto
            else "aguardando_autorizacao"
            if not backup_espelho.get("configurado")
            else "degradado"
        ),
        (
            "replica externa recente e verificada"
            if backup_espelho_pronto
            else "aguardando escolha do disco externo pelo usuario"
            if not backup_espelho.get("configurado")
            else "replica externa configurada requer atencao"
        ),
        configurado=bool(backup_espelho.get("configurado")),
        saudavel=bool(backup_espelho.get("saudavel")),
        fora_dispositivo=bool(backup_espelho.get("fora_dispositivo")),
        estado_espelho=backup_espelho.get("estado"),
        motivo=backup_espelho.get("motivo"),
        replicado_em=backup_espelho.get("replicado_em"),
    )

    if historico_drift_ok:
        estado_historico_drift = "pronto"
        resumo_historico_drift = (
            "cada avaliacao atual de desempenho possui evidencia imutavel"
        )
    elif historico_drift_aguardando_amostra:
        estado_historico_drift = "pendente_amostra"
        resumo_historico_drift = (
            "integridade preservada; aguardando resultados para formar "
            "o primeiro historico estatistico"
        )
    elif historico_drift_sincronizando:
        estado_historico_drift = "sincronizando"
        resumo_historico_drift = (
            "novo resultado aguardando a persistencia do proximo ciclo"
        )
    else:
        estado_historico_drift = "degradado"
        resumo_historico_drift = (
            "historico estatistico ausente, atrasado ou divergente"
        )
    componentes["historico_drift"] = _componente(
        estado_historico_drift,
        resumo_historico_drift,
        estado_auditoria=historico_drift.get("estado"),
        registros=int(historico_drift.get("total", 0) or 0),
        mercados=int(historico_drift.get("mercados", 0) or 0),
        chaves_atuais=int(historico_drift.get("chaves_atuais", 0) or 0),
        ausentes=historico_drift.get("chaves_atuais_ausentes") or [],
        divergentes=historico_drift.get("chaves_atuais_divergentes") or [],
        json_invalidos=int(historico_drift.get("json_invalidos", 0) or 0),
        duplicadas=int(historico_drift.get("chaves_duplicadas", 0) or 0),
        sincronizacao=sincronizacao_historico_drift,
    )

    componentes["hipoteses_sombra"] = _componente(
        "pronto" if hipoteses_sombra_ok else "degradado",
        (
            "hipoteses registradas e protegidas contra alteracao"
            if hipoteses_sombra_ok
            else "definicoes das hipoteses ausentes, mutaveis ou invalidas"
        ),
        estado_integridade=hipoteses_sombra.get("estado"),
        total=int(hipoteses_sombra.get("total", 0) or 0),
        protegido=bool(hipoteses_sombra.get("protegido")),
        invalidas=hipoteses_sombra.get("invalidas") or [],
        gatilhos_ausentes=hipoteses_sombra.get(
            "gatilhos_ausentes"
        ) or [],
    )

    componentes["validacao_gols_antecipados"] = _componente(
        "pronto" if validacao_gols_antecipados_ok else "degradado",
        (
            "definição, política e linhagem dos gols antecipados íntegras"
            if validacao_gols_antecipados_ok
            else "coorte antecipada ausente, divergente ou com linhagem mista"
        ),
        registrada=bool(validacao_gols_antecipados.get("registrada")),
        versao=validacao_gols_antecipados.get("versao"),
        estado_auditoria=validacao_gols_antecipados.get("estado"),
        divergencias=validacao_gols_antecipados.get("divergencias") or [],
        bracos_inconsistentes=validacao_gols_antecipados.get(
            "bracos_linhagem_inconsistente"
        ) or [],
        protegida=bool(validacao_gols_antecipados.get("protegida")),
        promocao_automatica=bool(
            validacao_gols_antecipados.get("promocao_automatica")
        ),
    )

    componentes["modelos_sombra"] = _componente(
        "pronto" if modelos_sombra_ok else "degradado",
        (
            "modelos experimentais ausentes ou congelados estão íntegros"
            if modelos_sombra_ok
            else "modelo temporal, contextual ou 5/10/15 incompatível ou corrompido"
        ),
        pontuacao_temporal_integra=bool(
            pontuacao_sombra.get("integro")
        ),
        pontuacao_contexto_integra=bool(
            pontuacao_contexto_sombra.get("integro")
        ),
        pontuacao_longa_integra=bool(
            pontuacao_longa_sombra.get("integro")
        ),
        modelos_temporais=pontuacao_sombra.get(
            "mercados_com_modelo"
        ) or [],
        modelos_contextuais=pontuacao_contexto_sombra.get(
            "mercados_com_modelo"
        ) or [],
        modelos_longos=pontuacao_longa_sombra.get(
            "mercados_com_modelo"
        ) or [],
        mercados_temporais_inconsistentes=[
            mercado
            for mercado, item in (
                pontuacao_sombra.get("por_mercado") or {}
            ).items()
            if not item.get("integro")
        ],
        mercados_contextuais_inconsistentes=[
            mercado
            for mercado, item in (
                pontuacao_contexto_sombra.get("por_mercado") or {}
            ).items()
            if not item.get("integro")
        ],
        mercados_longos_inconsistentes=[
            mercado
            for mercado, item in (
                pontuacao_longa_sombra.get("por_mercado") or {}
            ).items()
            if not item.get("integro")
        ],
    )

    componentes["auditoria_ligas_sombra"] = _componente(
        "pronto" if auditoria_ligas_sombra_ok else "degradado",
        (
            "ligas avaliadas por mercado sem bloqueio automático"
            if auditoria_ligas_sombra_ok
            else "auditoria de ligas ausente, incompleta ou aplicando filtros"
        ),
        versao=auditoria_ligas_sombra.get("versao"),
        integra=bool(auditoria_ligas_sombra.get("integro")),
        aplicacao_automatica=bool(
            auditoria_ligas_sombra.get("aplicacao_automatica")
        ),
        estados={
            mercado: item.get("estado")
            for mercado, item in (
                auditoria_ligas_sombra.get("por_mercado") or {}
            ).items()
        },
        metodos_grupo={
            nome: {
                "estado": item.get("estado"),
                "amostra": int(item.get("amostra", 0) or 0),
                "evidencia_historica_favoravel": bool(
                    item.get("evidencia_historica_favoravel")
                ),
                "validacao_prospectiva": (
                    item.get("validacao_prospectiva") or {}
                ).get("estado"),
            }
            for nome, item in (
                auditoria_ligas_sombra.get("por_metodo_grupo") or {}
            ).items()
        },
        mercados_com_evidencia_historica=(
            auditoria_ligas_sombra.get(
                "mercados_com_evidencia_historica"
            ) or []
        ),
    )

    componentes["historico_contexto"] = _componente(
        "pronto" if historico_contexto_ok else "degradado",
        (
            "avaliações contextuais possuem trilha imutável coerente"
            if historico_contexto_ok
            else "histórico contextual contém JSON inválido ou divergência"
        ),
        estado_auditoria=historico_contexto.get("estado"),
        registros=int(historico_contexto.get("total", 0) or 0),
        mercados=int(historico_contexto.get("mercados", 0) or 0),
        json_invalidos=historico_contexto.get("json_invalidos") or [],
        divergentes=historico_contexto.get("divergentes") or [],
        duplicadas=historico_contexto.get("duplicadas") or [],
        legado_sem_versao=historico_contexto.get(
            "legado_sem_versao"
        ) or [],
        ultimo=historico_contexto.get("ultimo"),
    )

    componentes["estado_watchdog_persistente"] = _componente(
        (
            "pronto" if persistencia_watchdog_ok
            else "pausa_planejada" if pausa_planejada
            else "degradado"
        ),
        (
            "estado de alertas espelhado no SQLite para recuperacao"
            if persistencia_watchdog_ok
            else "estado de alertas sem copia recuperavel no SQLite"
        ),
        estado_persistencia=persistencia_watchdog.get("estado"),
        persistido_em=persistencia_watchdog.get("persistido_em"),
        motivo=persistencia_watchdog.get("motivo"),
        dependencia_raiz=(
            "modo_manutencao"
            if pausa_planejada and not persistencia_watchdog_ok else None
        ),
    )

    estado_experimento_ritmo = experimento_ritmo.get("estado")
    experimento_ritmo_aprovado = estado_experimento_ritmo in (
        "aprovado",
        "rollback_acionado",
    )
    if not acesso_packball_ok:
        estado_ritmo = acesso_packball["estado"]
        resumo_ritmo = (
            "telemetria de ritmo suspensa enquanto o PackBall exige acesso"
        )
    elif not ritmo_auditado or experimento_ritmo.get("saudavel") is False:
        estado_ritmo = "degradado"
        resumo_ritmo = "ritmo de acesso inseguro ou com regressao detectada"
    elif experimento_ritmo_aprovado:
        estado_ritmo = "pronto"
        resumo_ritmo = "ritmo seguro validado contra a base persistente"
    elif estado_experimento_ritmo == "em_observacao":
        estado_ritmo = "pendente_validacao"
        resumo_ritmo = "ritmo seguro ainda cumprindo a janela de observacao"
    else:
        estado_ritmo = "pendente_evidencia"
        resumo_ritmo = "falta evidencia persistente do experimento de ritmo"
    base_ritmo = experimento_ritmo.get("base") or {}
    teste_ritmo = experimento_ritmo.get("experimento") or {}
    componentes["ritmo_packball"] = _componente(
        estado_ritmo,
        resumo_ritmo,
        auditoria_estado=ritmo_acesso.get("estado"),
        experimento_estado=estado_experimento_ritmo,
        ciclos=int(teste_ritmo.get("ciclos", 0) or 0),
        minimo_ciclos=experimento_ritmo.get("minimo_ciclos"),
        minutos_observados=experimento_ritmo.get("minutos_observados"),
        minimo_minutos=experimento_ritmo.get("minimo_minutos"),
        fluxo_base=base_ritmo.get("processadas_por_10_minutos"),
        fluxo_atual=teste_ritmo.get("processadas_por_10_minutos"),
        retencao_fluxo=experimento_ritmo.get("retencao_fluxo"),
        cobertura_temporal_base=base_ritmo.get("cobertura_temporal"),
        cobertura_temporal_atual=teste_ritmo.get("cobertura_temporal"),
        retencao_temporal=experimento_ritmo.get("retencao_temporal"),
        pausas_na_revalidacao=int(
            experimento_ritmo.get(
                "pausas_na_revalidacao",
                experimento_ritmo.get("pausas_packball", 0),
            ) or 0
        ),
        pausas_historicas=int(
            experimento_ritmo.get(
                "pausas_packball_historicas",
                experimento_ritmo.get("pausas_packball", 0),
            ) or 0
        ),
        revalidacao_prospectiva=bool(
            experimento_ritmo.get("revalidacao_prospectiva")
        ),
        revalidacao_iniciada_em=experimento_ritmo.get("iniciado_em"),
        ultimo_incidente_em=experimento_ritmo.get("ultimo_incidente_em"),
        versao_anterior_congelada=(
            (experimento_ritmo.get("evidencia_legada_congelada") or {})
            .get("versao")
        ),
        dependencia_raiz=(
            "acesso_packball" if not acesso_packball_ok else None
        ),
        motivos=experimento_ritmo.get("motivos") or [],
    )

    temporal = evidencias.get("dataset_temporal") or {}
    auditoria_lista_temporal = (
        evidencias.get("auditoria_indicadores_lista_temporais") or {}
    )
    cobertura = temporal.get("cobertura")
    temporal_ok = bool(
        temporal.get("validos", 0) > 0
        and cobertura is not None
        and float(cobertura) >= 0.8
    )
    componentes["historico_temporal"] = _componente(
        "pronto" if temporal_ok else "pendente_validacao",
        (
            "features temporais versionadas possuem cobertura suficiente"
            if temporal_ok else "histórico temporal ainda insuficiente"
        ),
        validos=int(temporal.get("validos", 0) or 0),
        elegiveis=int(temporal.get("elegiveis", 0) or 0),
        historicos=int(temporal.get("historicos", 0) or 0),
        legado_excluido=int(temporal.get("legado_excluido", 0) or 0),
        cobertura=cobertura,
        schema=temporal.get("schema_features"),
        indicadores_lista_temporais_estado=(
            "pronto_para_revisao"
            if auditoria_lista_temporal.get("pronto_para_revisao")
            else "coletando_sombra"
        ),
        indicadores_lista_comparacoes=int(
            auditoria_lista_temporal.get("comparacoes_independentes", 0)
            or 0
        ),
        indicadores_lista_partidas=int(
            auditoria_lista_temporal.get("partidas_distintas", 0) or 0
        ),
        indicadores_lista_concordancia=(
            auditoria_lista_temporal.get("taxa_concordancia")
        ),
        indicadores_lista_wilson_95=(
            auditoria_lista_temporal.get("limite_inferior_wilson_95")
        ),
        indicadores_lista_aplicacao_sinais=bool(
            auditoria_lista_temporal.get("aplicacao_sinais")
        ),
    )

    contador = validacao.get("contador_api") or {}
    cache_api = validacao.get("cache_api_football") or {}
    pareamento = evidencias.get("pareamento_api") or {}
    cache_operacional = evidencias.get("cache_api_operacional") or {}
    cota_api = diagnosticar_cota_api_football(
        contador, agora=agora_evidencias
    )
    api_infraestrutura_ok = bool(
        contador.get("saudavel")
        and contador.get("limite_confirmado_provedor")
        and cache_api.get("saudavel")
        and pareamento.get("saudavel")
        and cache_operacional.get("saudavel")
    )
    api_ok = bool(api_infraestrutura_ok and cota_api["pronto"])
    estado_api = (
        "pronto"
        if api_ok
        else "aguardando_reset_cota"
        if (
            api_infraestrutura_ok
            and cota_api["estado"] == "aguardando_reset_cota"
        )
        else "degradado"
    )
    componentes["api_football"] = _componente(
        estado_api,
        (
            "cota, cache e pareamento supervisionados"
            if api_ok
            else "cota segura esgotada; aguardando renovacao UTC"
            if estado_api == "aguardando_reset_cota"
            else "API sem confirmação completa ou degradada"
        ),
        contador_saudavel=bool(contador.get("saudavel")),
        limite_confirmado=contador.get("limite_confirmado_provedor"),
        limite_seguro=cota_api.get("limite_seguro"),
        consumo_dia=cota_api.get("consumo"),
        restante_seguro=cota_api.get("restante"),
        motivo_cota=cota_api.get("motivo"),
        proximo_reset_utc=cota_api.get("proximo_reset_utc"),
        segundos_ate_reset=cota_api.get("segundos_ate_reset"),
        cache_saudavel=bool(cache_api.get("saudavel")),
        pareamento_estado=pareamento.get("estado"),
        cache_operacional_estado=cache_operacional.get("estado"),
    )

    telegram = evidencias.get("telegram") or {}
    integridade = validacao.get("integridade_telegram") or {}
    valor_mercado = validacao.get("valor_mercado_sinais") or {}
    valor_mercado_ok = bool(
        valor_mercado.get("versao") == VERSAO_VALOR_MERCADO
        and valor_mercado.get("saudavel") is True
        and int(
            valor_mercado.get("entregues_oficiais_sem_valor", 0) or 0
        ) == 0
        and int(
            valor_mercado.get(
                "entregues_oficiais_rastro_invalido", 0
            ) or 0
        ) == 0
    )
    componentes["valor_mercado_oficial"] = _componente(
        "pronto" if valor_mercado_ok else "degradado",
        (
            "todas as entregas oficiais respeitam o valor conservador"
            if valor_mercado_ok
            else "gate de valor ausente, divergente ou sem margem"
        ),
        versao=valor_mercado.get("versao"),
        sinais_calibrados=int(
            valor_mercado.get("sinais_calibrados", 0) or 0
        ),
        com_valor_conservador=int(
            valor_mercado.get("com_valor_conservador", 0) or 0
        ),
        sem_valor_conservador=int(
            valor_mercado.get("sem_valor_conservador", 0) or 0
        ),
        entregues_oficiais_sem_valor=int(
            valor_mercado.get("entregues_oficiais_sem_valor", 0) or 0
        ),
        com_referencia_sem_vig=int(
            valor_mercado.get("com_referencia_sem_vig", 0) or 0
        ),
        sem_referencia_sem_vig=int(
            valor_mercado.get("sem_referencia_sem_vig", 0) or 0
        ),
        referencias_margem_incoerente=int(
            valor_mercado.get("referencias_margem_incoerente", 0) or 0
        ),
        rastros_validos=int(valor_mercado.get("rastros_validos", 0) or 0),
        rastros_ausentes=int(
            valor_mercado.get("rastros_ausentes", 0) or 0
        ),
        rastros_divergentes=int(
            valor_mercado.get("rastros_divergentes", 0) or 0
        ),
        entregues_oficiais_rastro_invalido=int(
            valor_mercado.get(
                "entregues_oficiais_rastro_invalido", 0
            ) or 0
        ),
        por_mercado=valor_mercado.get("por_mercado") or {},
    )
    politica_telegram = validacao.get("politica_telegram") or {}
    recursos = configuracao.get("recursos") or {}
    experimento_filtro = validacao.get("experimento_filtro") or {}
    conclusao_filtro = (
        validacao.get("conclusao_filtro_simulacoes") or {}
    )
    comparacao_filtro = evidencias.get("comparacao_filtro") or {}
    comparacao_atual_geral = (
        (comparacao_filtro.get("comparacao") or {}).get("geral") or {}
    )
    comparacao_geral = (
        conclusao_filtro.get("evidencia") or comparacao_atual_geral
    )
    sinais_teste_ativos = bool(recursos.get("sinais_teste"))
    integridade_experimento_ok = bool(
        not sinais_teste_ativos or experimento_filtro.get("saudavel")
    )
    if not sinais_teste_ativos:
        estado_filtro = "pronto"
        resumo_filtro = "modo de simulacao desativado"
        evidencia_filtro_ok = True
    elif not integridade_experimento_ok:
        estado_filtro = "degradado"
        resumo_filtro = (
            "marco do experimento de selecao ausente ou inconsistente"
        )
        evidencia_filtro_ok = False
    elif not conclusao_filtro:
        estado_filtro = "pendente_amostra"
        resumo_filtro = (
            "experimento integro, aguardando amostra minima nas duas coortes"
        )
        evidencia_filtro_ok = False
    elif conclusao_filtro.get("decisao") != "evidencia_favoravel":
        estado_filtro = "pronto"
        resumo_filtro = (
            "experimento concluido; filtro nao promovido por falta de vantagem"
        )
        evidencia_filtro_ok = True
    else:
        estado_filtro = "pronto"
        resumo_filtro = (
            "experimento concluido com vantagem e intervalo de 95%"
        )
        evidencia_filtro_ok = True
    componentes["filtro_simulacoes"] = _componente(
        estado_filtro,
        resumo_filtro,
        ativo=sinais_teste_ativos,
        saudavel=bool(experimento_filtro.get("saudavel")),
        estado_experimento=experimento_filtro.get("estado"),
        iniciado_em=experimento_filtro.get("iniciado_em"),
        protegido=experimento_filtro.get("protegido"),
        estado_comparacao=comparacao_geral.get("estado"),
        decisao=conclusao_filtro.get("decisao"),
        conclusao_versao=conclusao_filtro.get("versao"),
        concluido_em=conclusao_filtro.get("concluido_em"),
        conclusao_congelada=bool(conclusao_filtro),
        resultado_experimento=(
            "vantagem_comprovada"
            if conclusao_filtro.get("decisao") == "evidencia_favoravel"
            else "concluido_sem_vantagem"
            if conclusao_filtro
            else None
        ),
        decisoes_enviadas=int(
            comparacao_geral.get("decisoes_enviadas", 0) or 0
        ),
        decisoes_filtradas=int(
            comparacao_geral.get("decisoes_filtradas", 0) or 0
        ),
        resultados_resolvidos_enviadas=int(
            comparacao_geral.get(
                "resultados_resolvidos_enviadas", 0
            ) or 0
        ),
        resultados_resolvidos_filtradas=int(
            comparacao_geral.get(
                "resultados_resolvidos_filtradas", 0
            ) or 0
        ),
        pendentes_enviadas=int(
            comparacao_geral.get("pendentes_enviadas", 0) or 0
        ),
        pendentes_filtradas=int(
            comparacao_geral.get("pendentes_filtradas", 0) or 0
        ),
        voids_enviadas=int(
            comparacao_geral.get("voids_enviadas", 0) or 0
        ),
        voids_filtradas=int(
            comparacao_geral.get("voids_filtradas", 0) or 0
        ),
        amostra_enviadas=int(
            comparacao_geral.get("amostra_enviadas", 0) or 0
        ),
        amostra_filtradas=int(
            comparacao_geral.get("amostra_filtradas", 0) or 0
        ),
        amostra_minima_por_coorte=int(
            comparacao_geral.get("amostra_minima_por_coorte", 30) or 30
        ),
        intervalo_delta_taxa_acerto_95=(
            comparacao_geral.get("intervalo_delta_taxa_acerto_95")
        ),
        intervalo_delta_roi_95=(
            comparacao_geral.get("intervalo_delta_roi_95")
        ),
    )
    canais_configurados = bool(
        recursos.get("telegram_gols") and recursos.get("telegram_escanteios")
    )
    telegram_teste_ok = bool(
        canais_configurados
        and integridade.get(
            "saudavel_operacional", integridade.get("saudavel")
        )
        and integridade_experimento_ok
        and int(telegram.get("provas_teste", 0) or 0) > 0
    )
    componentes["telegram_teste"] = _componente(
        "pronto" if telegram_teste_ok else "degradado",
        (
            "entrega de teste comprovada por message_id"
            if telegram_teste_ok else "falta prova válida de entrega de teste"
        ),
        canais_configurados=canais_configurados,
        integridade_saudavel=bool(integridade.get("saudavel")),
        integridade_operacional_saudavel=bool(
            integridade.get(
                "saudavel_operacional", integridade.get("saudavel")
            )
        ),
        envios_analise_incertos=int(
            integridade.get("envios_analise_incertos", 0) or 0
        ),
        resultados_analise_sem_aviso=int(
            integridade.get("resultados_analise_sem_aviso", 0) or 0
        ),
        provas_teste=int(telegram.get("provas_teste", 0) or 0),
    )
    politica_telegram_ok = bool(
        politica_telegram.get("versao")
        == "telegram-compacto-criticos-v1"
        and not politica_telegram.get("alertas_tecnicos_ativos")
        and not politica_telegram.get("alertas_sombra_ativos")
        and politica_telegram.get("resumo_diario_compacto")
        and politica_telegram.get("alertas_operacionais_criticos")
    )
    componentes["politica_telegram"] = _componente(
        "pronto" if politica_telegram_ok else "degradado",
        (
            "resumo compacto e somente alertas operacionais críticos"
            if politica_telegram_ok
            else "política anti-poluição do Telegram ausente ou divergente"
        ),
        versao=politica_telegram.get("versao"),
        alertas_tecnicos_ativos=bool(
            politica_telegram.get("alertas_tecnicos_ativos")
        ),
        alertas_sombra_ativos=bool(
            politica_telegram.get("alertas_sombra_ativos")
        ),
        resumo_diario_compacto=bool(
            politica_telegram.get("resumo_diario_compacto")
        ),
        alertas_operacionais_criticos=bool(
            politica_telegram.get("alertas_operacionais_criticos")
        ),
    )
    provas_oficiais = int(telegram.get("provas_oficiais", 0) or 0)
    aprovadas_em_teste = int(
        telegram.get("provas_aprovadas_em_teste", 0) or 0
    )
    simuladas_em_teste = int(
        telegram.get("provas_simuladas_em_teste", 0) or 0
    )
    componentes["telegram_oficial"] = _componente(
        "pronto" if provas_oficiais > 0 else "pendente_evidencia_real",
        (
            "rota oficial possui entrega real comprovada"
            if provas_oficiais > 0
            else (
                "existem sinais aprovados entregues em canal experimental; "
                "a rota oficial ainda aguarda metodo calibrado elegivel"
            )
            if aprovadas_em_teste > 0
            else "rota testada em código, aguardando o primeiro sinal elegível"
        ),
        provas_oficiais=provas_oficiais,
        provas_aprovadas_em_teste=aprovadas_em_teste,
        provas_simuladas_em_teste=simuladas_em_teste,
        promocao_retroativa=False,
    )

    odds_periodos = evidencias.get("odds_periodos") or {}
    cortes_sombra = evidencias.get("cortes_sombra") or {}
    avaliacoes_cortes = cortes_sombra.get("avaliacoes") or {}
    diagnosticos_pre = (
        evidencias.get("diagnostico_pre_calibracao") or {}
    )
    sobreajuste_gol_ft = evidencias.get("sobreajuste_gol_ft") or {}
    calibracoes = validacao.get("estado_calibracoes") or {}
    progresso = validacao.get("progresso_calibracao") or {}
    diversidade_calibracao = (
        validacao.get("diversidade_calibracao") or {}
    )
    pendencias_resultados = evidencias.get("pendencias_resultados") or {}
    pendentes_por_mercado = pendencias_resultados.get("por_mercado") or {}
    avaliacoes_hipoteses = list(
        ((validacao.get("hipoteses_sombra") or {}).get("avaliacoes")) or []
    )
    mercados = {}
    liberados = []
    for mercado in mercados_exigidos:
        avaliacao_edge_mercado = (
            (portfolio_edge.get("avaliacoes") or {}).get(mercado) or {}
        )
        prospectiva_asiatica = {}
        if (
            mercado == "escanteios_ft_asiatico"
            and avaliacao_edge_mercado.get("coorte_operacional_avaliada")
            == "prospectiva_fixa_pos_ancora"
        ):
            prospectiva_asiatica = dict(
                avaliacao_edge_mercado.get("metricas_oficiais") or {}
            )
        fonte_ok = True
        if mercado == "escanteios_ft_asiatico":
            fonte_ok = bool((odds_periodos.get("FT") or {}).get("mapeada"))
        elif mercado == "escanteios_1t":
            fonte_ok = bool((odds_periodos.get("1T") or {}).get("mapeada"))
        elif mercado == "escanteios_2t":
            fonte_ok = bool((odds_periodos.get("2T") or {}).get("mapeada"))
        calibracao = calibracoes.get(mercado) or {}
        validacao_prospectiva = (
            calibracao.get("validacao_prospectiva") or {}
        )
        if prospectiva_asiatica:
            validacao_prospectiva = {
                "versao": prospectiva_asiatica.get("versao"),
                "regra_versao": prospectiva_asiatica.get("regra_versao"),
                "estado": prospectiva_asiatica.get("estado"),
                "decisao": prospectiva_asiatica.get("decisao"),
                "candidatos": int(
                    prospectiva_asiatica.get("candidatos", 0) or 0
                ),
                "tamanho_coorte": int(
                    prospectiva_asiatica.get("tamanho_coorte", 100) or 100
                ),
                "validos": int(
                    prospectiva_asiatica.get("validos", 0) or 0
                ),
                "greens": int(
                    prospectiva_asiatica.get("greens", 0) or 0
                ),
                "half_greens": int(
                    prospectiva_asiatica.get("half_greens", 0) or 0
                ),
                "voids": int(
                    prospectiva_asiatica.get("voids", 0) or 0
                ),
                "half_reds": int(
                    prospectiva_asiatica.get("half_reds", 0) or 0
                ),
                "reds": int(
                    prospectiva_asiatica.get("reds", 0) or 0
                ),
                "pendentes": int(
                    prospectiva_asiatica.get("pendentes", 0) or 0
                ),
                "faltam": int(
                    prospectiva_asiatica.get("faltam", 100) or 0
                ),
                "registrado_em": prospectiva_asiatica.get(
                    "registrado_em"
                ),
                "exposicao_coorte_prontidao": (
                    prospectiva_asiatica.get(
                        "exposicao_coorte_prontidao"
                    )
                ),
                "taxa_resultado_positivo": prospectiva_asiatica.get(
                    "taxa_resultado_positivo"
                ),
                "roi": prospectiva_asiatica.get("roi"),
                "intervalo_roi_95": prospectiva_asiatica.get(
                    "intervalo_roi_95"
                ),
                "checkpoint_seguranca": prospectiva_asiatica.get(
                    "checkpoint_seguranca"
                ) or {},
                "gate_preco_sem_vig": prospectiva_asiatica.get(
                    "gate_preco_sem_vig"
                ) or {},
                "controle_operacional": avaliacao_edge_mercado.get(
                    "controle_operacional"
                ) or {},
                "historico_anterior_entra_na_decisao": False,
                "telegram_oficial": False,
                "promocao_automatica": False,
            }
        diversidade = diversidade_calibracao.get(mercado) or {}
        corte_sombra = avaliacoes_cortes.get(mercado) or {}
        diagnostico_pre = diagnosticos_pre.get(mercado) or {}
        estado_diagnostico_pre = _classificar_diagnostico_pre_calibracao(
            diagnostico_pre
        )
        ativa = bool(calibracao.get("ativa"))
        motivo_calibracao = calibracao.get("motivo")
        amostra_modelo = int(calibracao.get("amostra", 0) or 0)
        validacao_final_realizada = bool(
            int(calibracao.get("amostra_validacao", 0) or 0)
            or calibracao.get("roi_validacao_agregado") is not None
            or calibracao.get("auc_validacao") is not None
            or (
                amostra_modelo >= 100
                and motivo_calibracao != "amostra_insuficiente"
            )
        )
        if not fonte_ok:
            estado = "bloqueado_fonte"
            resumo = "fonte asiática real de duas opções não comprovada"
        elif prospectiva_asiatica:
            if (
                (avaliacao_edge_mercado.get("decisao") or {}).get(
                    "todos_satisfeitos"
                ) is True
            ):
                estado = "pronto"
                resumo = (
                    "coorte prospectiva fixa comprovou edge e aguarda "
                    "revisão humana"
                )
            else:
                estado = "pendente_amostra"
                resumo = (
                    "coorte prospectiva fixa de escanteios FT asiáticos "
                    "ainda está formando evidência futura"
                )
        elif ativa and not diversidade.get("pronto"):
            estado = "bloqueado_diversidade"
            resumo = (
                "calibração aprovada, mas a amostra ainda não possui "
                "diversidade mínima de dias e ligas"
            )
        elif ativa:
            estado = "pronto"
            resumo = "calibração real ativa e compatível"
        elif validacao_final_realizada:
            estado = "reprovado_validacao"
            resumo = (
                "amostra submetida à validação cronológica, "
                f"mas reprovada: {motivo_calibracao or 'critérios finais'}"
            )
        elif (
            corte_sombra.get("estado") == "avaliavel"
            and corte_sombra.get("apto_para_alterar_regra") is False
        ):
            estado = "pendente_amostra"
            if (
                estado_diagnostico_pre
                == "desempenho_desfavoravel_pre_validacao"
            ):
                resumo = (
                    "aguardando calibração; desempenho atual negativo "
                    "e corte sombra sem vantagem futura"
                )
            else:
                resumo = (
                    "aguardando calibração; corte sombra avaliado "
                    "sem vantagem futura"
                )
        elif (
            estado_diagnostico_pre
            == "desempenho_desfavoravel_pre_validacao"
        ):
            estado = "pendente_amostra"
            resumo = (
                "aguardando calibração; desempenho atual negativo "
                "na pré-validação"
            )
        elif (
            estado_diagnostico_pre
            == "desempenho_positivo_ainda_nao_comprovado"
        ):
            estado = "pendente_amostra"
            resumo = (
                "aguardando calibração; resultado preliminar positivo "
                "ainda não comprovado"
            )
        else:
            estado = "pendente_amostra"
            resumo = "aguardando amostra independente e calibração"
        if (
            estado == "pronto"
            and operacao_ok
            and telegram_teste_ok
            and experimento_ritmo_aprovado
        ):
            liberados.append(mercado)
        andamento = progresso.get(mercado) or {}
        resultados_resolvidos = int(
            andamento.get(
                "amostra", calibracao.get("amostra", 0)
            ) or 0
        )
        faltam_resultados = int(
            andamento.get(
                "faltam", max(100 - resultados_resolvidos, 0)
            ) or 0
        )
        if prospectiva_asiatica:
            resultados_resolvidos = int(
                prospectiva_asiatica.get("validos", 0) or 0
            )
            faltam_resultados = int(
                prospectiva_asiatica.get("faltam", 100) or 0
            )
        hipoteses_recuperacao = []
        for hipotese in avaliacoes_hipoteses:
            if hipotese.get("mercado") != mercado:
                continue
            selecionada = hipotese.get("selecionada") or {}
            controle = hipotese.get("controle_excluido") or {}
            hipoteses_recuperacao.append({
                "identificador": hipotese.get("identificador"),
                "estado": hipotese.get("estado"),
                "descricao_corte": hipotese.get("descricao_corte"),
                "iniciado_em": hipotese.get("iniciado_em"),
                "minimo_resultados": int(
                    hipotese.get("minimo_resultados", 0) or 0
                ),
                "resultados_selecionados": int(
                    selecionada.get("amostra", 0) or 0
                ),
                "resultados_controle": int(
                    controle.get("amostra", 0) or 0
                ),
                "pendentes_resultado": int(
                    hipotese.get("pendentes_resultado", 0) or 0
                ),
                "pendentes_selecionados": int(
                    hipotese.get("pendentes_selecionados", 0) or 0
                ),
                "pendentes_controle": int(
                    hipotese.get("pendentes_controle", 0) or 0
                ),
                "faltam_selecionados": int(
                    hipotese.get("faltam", 0) or 0
                ),
                "faltam_controle": int(
                    hipotese.get("faltam_controle", 0) or 0
                ),
                "roi_selecionados": selecionada.get("roi"),
                "roi_controle": controle.get("roi"),
                "delta_roi": hipotese.get(
                    "delta_roi_selecionada_controle"
                ),
                "intervalo_delta_roi_95": hipotese.get(
                    "intervalo_delta_roi_95"
                ),
                "aplicacao_automatica": False,
            })
        mercados[mercado] = _componente(
            estado,
            resumo,
            amostra=resultados_resolvidos,
            resultados_resolvidos=resultados_resolvidos,
            amostra_modelo=amostra_modelo,
            sinais_pendentes=int(
                pendentes_por_mercado.get(mercado, 0) or 0
            ),
            faltam=faltam_resultados,
            faltam_resultados_reais=faltam_resultados,
            hipoteses_recuperacao=hipoteses_recuperacao,
            hipotese_recuperacao_em_andamento=any(
                item.get("estado") in {
                    "aguardando_amostra", "aguardando_controle"
                }
                for item in hipoteses_recuperacao
            ),
            motivo=motivo_calibracao,
            validacao_final_realizada=validacao_final_realizada,
            amostra_validacao=int(
                calibracao.get("amostra_validacao", 0) or 0
            ),
            roi_validacao_agregado=calibracao.get(
                "roi_validacao_agregado"
            ),
            auc_validacao=calibracao.get("auc_validacao"),
            limite_inferior_auc_95=calibracao.get(
                "limite_inferior_auc_95"
            ),
            erro_calibracao=calibracao.get("erro_calibracao"),
            celulas_aprovadas=int(
                calibracao.get("celulas_aprovadas", 0) or 0
            ),
            celulas_avaliadas=int(
                calibracao.get("celulas_avaliadas", 0) or 0
            ),
            validacao_prospectiva=validacao_prospectiva,
            metodo_efetivo=(
                prospectiva_asiatica.get("regra_versao")
                if prospectiva_asiatica else None
            ),
            validos=(
                int(prospectiva_asiatica.get("validos", 0) or 0)
                if prospectiva_asiatica else None
            ),
            greens=(
                int(prospectiva_asiatica.get("greens", 0) or 0)
                if prospectiva_asiatica else None
            ),
            half_greens=(
                int(prospectiva_asiatica.get("half_greens", 0) or 0)
                if prospectiva_asiatica else None
            ),
            voids=(
                int(prospectiva_asiatica.get("voids", 0) or 0)
                if prospectiva_asiatica else None
            ),
            half_reds=(
                int(prospectiva_asiatica.get("half_reds", 0) or 0)
                if prospectiva_asiatica else None
            ),
            reds=(
                int(prospectiva_asiatica.get("reds", 0) or 0)
                if prospectiva_asiatica else None
            ),
            roi=(
                prospectiva_asiatica.get("roi")
                if prospectiva_asiatica else None
            ),
            intervalo_roi_95=(
                prospectiva_asiatica.get("intervalo_roi_95")
                if prospectiva_asiatica else None
            ),
            decisao_estatistica=(
                prospectiva_asiatica.get("decisao")
                if prospectiva_asiatica else None
            ),
            fonte_comprovada=fonte_ok,
            diversidade_estado=diversidade.get("estado"),
            diversidade_pronta=bool(diversidade.get("pronto")),
            diversidade_amostra=int(
                diversidade.get("amostra", 0) or 0
            ),
            dias_distintos=int(
                diversidade.get("dias_distintos", 0) or 0
            ),
            ligas_distintas=int(
                diversidade.get("ligas_distintas", 0) or 0
            ),
            minimo_dias=int(diversidade.get("minimo_dias", 0) or 0),
            minimo_ligas=int(
                diversidade.get("minimo_ligas", 0) or 0
            ),
            corte_sombra_estado=corte_sombra.get("estado"),
            corte_sombra_motivo=corte_sombra.get("motivo"),
            corte_sombra_apto=corte_sombra.get(
                "apto_para_alterar_regra"
            ),
            corte_sombra_escolhido=corte_sombra.get(
                "corte_escolhido_no_desenvolvimento"
            ),
            corte_sombra_baseline_validacao=corte_sombra.get(
                "baseline_validacao"
            ),
            corte_sombra_metricas_validacao=corte_sombra.get(
                "metricas_validacao_corte"
            ),
            diagnostico_pre_calibracao_estado=estado_diagnostico_pre,
            diagnostico_pre_calibracao_amostra=int(
                diagnostico_pre.get("amostra", 0) or 0
            ),
            diagnostico_pre_calibracao_taxa_acerto=diagnostico_pre.get(
                "taxa_acerto"
            ),
            diagnostico_pre_calibracao_intervalo_acerto_95=(
                diagnostico_pre.get("intervalo_acerto_95")
            ),
            diagnostico_pre_calibracao_roi=diagnostico_pre.get("roi"),
            diagnostico_pre_calibracao_lucro_unidades=(
                diagnostico_pre.get("lucro_unidades")
            ),
            diagnostico_pre_calibracao_auc=(
                (diagnostico_pre.get("discriminacao_pontuacao") or {}).get(
                    "auc"
                )
            ),
            controle_sobreajuste_estado=(
                sobreajuste_gol_ft.get("estado")
                if mercado == "gol_ft" else None
            ),
            controle_sobreajuste_testes=(
                int(sobreajuste_gol_ft.get("testes_explorados", 0) or 0)
                if mercado == "gol_ft" else 0
            ),
            controle_sobreajuste_bonferroni=(
                int(sobreajuste_gol_ft.get("aprovados_bonferroni", 0) or 0)
                if mercado == "gol_ft" else 0
            ),
            controle_sobreajuste_bh=(
                int(sobreajuste_gol_ft.get("aprovados_bh", 0) or 0)
                if mercado == "gol_ft" else 0
            ),
            promocao_retroativa_permitida=(
                bool(sobreajuste_gol_ft.get(
                    "promocao_retroativa_permitida", False
                ))
                if mercado == "gol_ft" else False
            ),
            exige_validacao_prospectiva=(
                bool(sobreajuste_gol_ft.get(
                    "exige_validacao_prospectiva", True
                ))
                if mercado == "gol_ft" else False
            ),
            diagnostico_fonte=(
                (odds_periodos.get("FT") or {}).get("diagnostico_fonte")
                if mercado == "escanteios_ft_asiatico"
                else (
                    (odds_periodos.get("1T") or {}).get(
                        "diagnostico_fonte"
                    )
                    if mercado == "escanteios_1t"
                    else (
                        (odds_periodos.get("2T") or {}).get(
                            "diagnostico_fonte"
                        )
                        if mercado == "escanteios_2t"
                        else None
                    )
                )
            ),
        )
    if proximo_gol_balanceado_auditado and "proximo_gol" in mercados:
        legado_proximo_gol = mercados["proximo_gol"]
        proximo_gol_ja_liberado = "proximo_gol" in liberados
        evidencias_legadas = dict(
            legado_proximo_gol.get("evidencias") or {}
        )
        controle_integro = bool(
            not controle_proximo_gol_balanceado
            or controle_proximo_gol_balanceado.get("saudavel")
        )
        grupo_ativo = bool(
            metodos_grupo.get("proximo_gol_balanceado_ativo")
        )
        challenger = {
            "versao_validacao": progresso_proximo_gol_balanceado.get(
                "versao"
            ),
            "regra_versao": progresso_proximo_gol_balanceado.get(
                "regra_versao"
            ),
            "estado": progresso_proximo_gol_balanceado.get("estado"),
            "decisao": progresso_proximo_gol_balanceado.get("decisao"),
            "candidatos": int(
                progresso_proximo_gol_balanceado.get("candidatos", 0) or 0
            ),
            "tamanho_coorte": int(
                progresso_proximo_gol_balanceado.get(
                    "tamanho_coorte", 40
                ) or 40
            ),
            "validos": int(
                progresso_proximo_gol_balanceado.get("validos", 0) or 0
            ),
            "greens": int(
                progresso_proximo_gol_balanceado.get("greens", 0) or 0
            ),
            "reds": int(
                progresso_proximo_gol_balanceado.get("reds", 0) or 0
            ),
            "pendentes": int(
                progresso_proximo_gol_balanceado.get("pendentes", 0) or 0
            ),
            "faltam": int(
                progresso_proximo_gol_balanceado.get("faltam", 0) or 0
            ),
            "registrado_em": progresso_proximo_gol_balanceado.get(
                "registrado_em"
            ),
            "exposicao_coorte_prontidao": (
                progresso_proximo_gol_balanceado.get(
                    "exposicao_coorte_prontidao"
                )
            ),
            "roi": progresso_proximo_gol_balanceado.get("roi"),
            "intervalo_roi_95": progresso_proximo_gol_balanceado.get(
                "intervalo_roi_95"
            ),
            "alerta_desfavoravel": bool(
                progresso_proximo_gol_balanceado.get(
                    "alerta_desfavoravel"
                )
            ),
            "resultados_completos": bool(
                progresso_proximo_gol_balanceado.get(
                    "resultados_completos"
                )
            ),
            "grupo_teste_ativo": grupo_ativo,
            "gerador_sombra_ativo": bool(
                metodos_grupo.get(
                    "proximo_gol_balanceado_sombra_ativo"
                )
            ),
            "controle_operacional": dict(
                controle_proximo_gol_balanceado
            ),
            "checkpoint_seguranca": dict(
                progresso_proximo_gol_balanceado.get(
                    "checkpoint_seguranca"
                ) or {}
            ),
            "funil_origem": dict(
                progresso_proximo_gol_balanceado.get(
                    "funil_origem_v10f"
                ) or {}
            ),
            "telegram_oficial": False,
            "promocao_automatica": False,
        }
        evidencias_legadas["challenger_balanceado"] = challenger
        if legado_proximo_gol.get("pronto"):
            mercados["proximo_gol"] = _componente(
                legado_proximo_gol["estado"],
                legado_proximo_gol["resumo"],
                **evidencias_legadas,
            )
        else:
            if not controle_integro:
                estado_proximo_gol = "degradado"
                resumo_proximo_gol = (
                    "o controle persistente do Próximo Gol balanceado está "
                    "inconsistente e bloqueou o grupo de teste"
                )
            elif challenger["alerta_desfavoravel"]:
                estado_proximo_gol = "pendente_amostra"
                resumo_proximo_gol = (
                    "o balanceado foi suspenso por evidência negativa no "
                    "checkpoint; a regra precisa continua em validação"
                )
            elif challenger["resultados_completos"]:
                estado_proximo_gol = "pendente_validacao"
                resumo_proximo_gol = (
                    "a coorte balanceada terminou e aguarda revisão humana; "
                    "nenhuma promoção é automática"
                )
            else:
                estado_proximo_gol = "pendente_amostra"
                resumo_proximo_gol = (
                    "a regra precisa e o challenger balanceado continuam "
                    "formando amostras prospectivas separadas"
                )
            evidencias_legadas["metodo_efetivo"] = (
                "portfolio-proximo-gol-prospectivo-v1"
            )
            mercados["proximo_gol"] = _componente(
                estado_proximo_gol,
                resumo_proximo_gol,
                **evidencias_legadas,
            )
        liberados = [
            item for item in liberados if item != "proximo_gol"
        ]
        if proximo_gol_ja_liberado:
            liberados.append("proximo_gol")
    if v2b_ft_auditado and "gol_ft" in mercados:
        legado_gol_ft = mercados["gol_ft"]
        decisao_v2b = progresso_v2b_ft_grupo.get("decisao_estatistica")
        validos_v2b = int(
            progresso_v2b_ft_grupo.get("validos", 0) or 0
        )
        if not v2b_ft_integridade_ok:
            estado_v2b_mercado = "degradado"
            resumo_v2b_mercado = (
                "V2b é o método selecionado, mas sua âncora ou linhagem "
                "está inconsistente"
            )
        elif v2b_ft_rollback_recomendado or decisao_v2b == "evidencia_desfavoravel":
            estado_v2b_mercado = "reprovado_validacao"
            resumo_v2b_mercado = (
                "V2b apresentou evidência negativa forte e requer retorno "
                "ao modo sombra"
            )
        elif not v2b_ft_grupo_ativo:
            estado_v2b_mercado = "sombra"
            resumo_v2b_mercado = (
                "V2b está preservado em sombra; o método legado continua "
                "registrado apenas como histórico"
            )
        elif decisao_v2b == "favoravel_para_revisao_independente":
            estado_v2b_mercado = "pronto"
            resumo_v2b_mercado = (
                "V2b superou a coorte prospectiva, o holdout e o intervalo "
                "de confiança exigidos"
            )
        elif decisao_v2b in {"inconclusiva", "amostra_valida_insuficiente"}:
            estado_v2b_mercado = "reprovado_validacao"
            resumo_v2b_mercado = (
                "V2b encerrou a coorte sem comprovar vantagem estatística"
            )
        else:
            estado_v2b_mercado = "pendente_amostra"
            resumo_v2b_mercado = (
                "V2b é o método selecionado e continua formando sua coorte "
                "prospectiva independente"
            )
        mercados["gol_ft"] = _componente(
            estado_v2b_mercado,
            resumo_v2b_mercado,
            metodo_efetivo="gol-ft-capacidade-contextual-v2b",
            ativo=v2b_ft_grupo_ativo,
            validos=validos_v2b,
            greens=int(progresso_v2b_ft_grupo.get("greens", 0) or 0),
            reds=int(progresso_v2b_ft_grupo.get("reds", 0) or 0),
            roi=progresso_v2b_ft_grupo.get("roi"),
            intervalo_roi_95=progresso_v2b_ft_grupo.get("intervalo_roi_95"),
            decisao_estatistica=decisao_v2b,
            amostra_minima_valida=MINIMO_VALIDOS_V2B_FT,
            tamanho_coorte=TAMANHO_COORTE_V2B_FT,
            faltam=max(TAMANHO_COORTE_V2B_FT - int(
                progresso_v2b_ft_grupo.get("candidatos_coorte", validos_v2b)
                or 0
            ), 0),
            linhagem_homogenea=progresso_v2b_ft_grupo.get(
                "linhagem_homogenea"
            ),
            metodo_legado={
                "estado": legado_gol_ft.get("estado"),
                "resumo": legado_gol_ft.get("resumo"),
                "motivo": (
                    legado_gol_ft.get("evidencias") or {}
                ).get("motivo"),
                "amostra_validacao": int((
                    legado_gol_ft.get("evidencias") or {}
                ).get("amostra_validacao", 0) or 0),
                "roi_validacao": (
                    legado_gol_ft.get("evidencias") or {}
                ).get("roi_validacao_agregado"),
                "auc_validacao": (
                    legado_gol_ft.get("evidencias") or {}
                ).get("auc_validacao"),
                "validacao_prospectiva": (
                    legado_gol_ft.get("evidencias") or {}
                ).get("validacao_prospectiva") or {},
            },
            promocao_automatica=False,
            ultimo_ciclo=diagnostico_v2_ultimo_ciclo,
        )
        liberados = [item for item in liberados if item != "gol_ft"]
        if (
            estado_v2b_mercado == "pronto"
            and operacao_ok
            and telegram_teste_ok
            and experimento_ritmo_aprovado
        ):
            liberados.append("gol_ft")
    portfolio_ft = evidencias.get("portfolio_ft") or {}
    if portfolio_ft and "gol_ft" in mercados:
        legado_gol_ft = mercados["gol_ft"]
        decisao_portfolio_ft = (
            portfolio_ft.get("decisao") or {}
        ).get("estado")
        if decisao_portfolio_ft == "favoravel_para_revisao_manual":
            estado_portfolio_ft = "pendente_validacao"
            resumo_portfolio_ft = (
                "ao menos um método FT comprovou vantagem prospectiva; "
                "a promoção continua dependendo de revisão manual"
            )
        elif decisao_portfolio_ft == "vantagem_nao_comprovada":
            estado_portfolio_ft = "reprovado_validacao"
            resumo_portfolio_ft = (
                "um ou mais métodos FT concluíram a avaliação sem "
                "comprovar vantagem replicada"
            )
        elif decisao_portfolio_ft == "sem_metodos_ativos":
            estado_portfolio_ft = "sombra"
            resumo_portfolio_ft = (
                "nenhum método FT do portfólio está liberado para entrega"
            )
        else:
            estado_portfolio_ft = "pendente_amostra"
            resumo_portfolio_ft = (
                "os métodos FT ativos continuam formando coortes futuras "
                "separadas, sem promoção automática"
            )
        mercados["gol_ft"] = _componente(
            estado_portfolio_ft,
            resumo_portfolio_ft,
            metodo_efetivo="portfolio-ft-prospectivo-v1",
            versao_filtro_2t=VERSAO_FILTRO_GOL_FT_PRECISO,
            metodos_ativos=[
                dict(item)
                for item in (portfolio_ft.get("metodos_ativos") or [])
            ],
            metodos_bloqueados=[
                dict(item)
                for item in (portfolio_ft.get("metodos_bloqueados") or [])
            ],
            metodo_base_legado=portfolio_ft.get("metodo_base_legado") or {},
            estado_portfolio=decisao_portfolio_ft,
            mercado_anterior={
                "estado": legado_gol_ft.get("estado"),
                "resumo": legado_gol_ft.get("resumo"),
                "metodo_efetivo": (
                    legado_gol_ft.get("evidencias") or {}
                ).get("metodo_efetivo"),
            },
            promocao_automatica=False,
        )
        liberados = [item for item in liberados if item != "gol_ft"]
    portfolio_ht = evidencias.get("portfolio_ht") or {}
    metodos_ht_ativos = [
        dict(item)
        for item in (portfolio_ht.get("metodos") or [])
        if item.get("ativo") is True
    ]
    if metodos_ht_ativos and "gol_ht" in mercados:
        legado_gol_ht = mercados["gol_ht"]
        decisoes_favoraveis = {
            "favoravel_para_revisao",
            "favoravel_para_revisao_independente",
        }
        decisoes_terminais_negativas = {
            "evidencia_desfavoravel",
            "inconclusiva",
            "amostra_valida_insuficiente",
        }
        alguma_favoravel = any(
            item.get("decisao_estatistica") in decisoes_favoraveis
            for item in metodos_ht_ativos
        )
        todos_concluidos_sem_vantagem = all(
            int(item.get("faltam", 0) or 0) == 0
            and item.get("decisao_estatistica")
            in decisoes_terminais_negativas
            for item in metodos_ht_ativos
        )
        if todos_concluidos_sem_vantagem:
            estado_portfolio_ht = "reprovado_validacao"
            resumo_portfolio_ht = (
                "todos os braços HT ativos concluíram suas coortes sem "
                "comprovar vantagem estatística"
            )
        elif alguma_favoravel:
            estado_portfolio_ht = "pendente_validacao"
            resumo_portfolio_ht = (
                "ao menos um braço HT atingiu o critério prospectivo e "
                "aguarda revisão independente; não há promoção automática"
            )
        else:
            estado_portfolio_ht = "pendente_amostra"
            resumo_portfolio_ht = (
                "o método legado foi reprovado; os braços HT novos e "
                "separados continuam formando coortes prospectivas"
            )
        mercados["gol_ht"] = _componente(
            estado_portfolio_ht,
            resumo_portfolio_ht,
            metodo_efetivo="portfolio-ht-prospectivo-v1",
            ativo=True,
            metodos_ativos=metodos_ht_ativos,
            metodos_inativos=[
                dict(item)
                for item in (portfolio_ht.get("metodos") or [])
                if item.get("ativo") is not True
            ],
            metodo_legado={
                "estado": legado_gol_ht.get("estado"),
                "resumo": legado_gol_ht.get("resumo"),
                "motivo": (
                    legado_gol_ht.get("evidencias") or {}
                ).get("motivo"),
                "amostra_validacao": int((
                    legado_gol_ht.get("evidencias") or {}
                ).get("amostra_validacao", 0) or 0),
                "roi_validacao": (
                    legado_gol_ht.get("evidencias") or {}
                ).get("roi_validacao_agregado"),
                "auc_validacao": (
                    legado_gol_ht.get("evidencias") or {}
                ).get("auc_validacao"),
                "validacao_prospectiva": (
                    legado_gol_ht.get("evidencias") or {}
                ).get("validacao_prospectiva") or {},
            },
            capacidade_v1_legada_no_grupo=bool(
                portfolio_ht.get("capacidade_v1_legada_no_grupo")
            ),
            promocao_automatica=False,
        )
        liberados = [item for item in liberados if item != "gol_ht"]
    if modo_manutencao.get("ativo"):
        liberados = []
    componentes["mercados"] = mercados

    autostart = evidencias.get("autostart") or {}
    autostart_ok = bool(
        autostart.get("instalada") and autostart.get("saudavel")
    )
    heartbeat_autostart = autostart.get("heartbeat") or {}
    definicao_autostart = (
        heartbeat_autostart.get("definicao_tarefa") or {}
    )
    componentes["recuperacao_windows"] = _componente(
        "pronto" if autostart_ok else "aguardando_autorizacao",
        (
            "tarefa automática instalada"
            if autostart_ok else "instalação depende de autorização do usuário"
        ),
        instalada=autostart_ok,
        consultavel=autostart.get("consultavel", True),
        divergencias=autostart.get("divergencias") or [],
        origem_evidencia=autostart.get("origem_evidencia"),
        heartbeat_versao=heartbeat_autostart.get("versao"),
        definicao_consulta_direta=definicao_autostart.get(
            "consulta_direta"
        ),
        permite_inicio_em_bateria=definicao_autostart.get(
            "permite_inicio_em_bateria"
        ),
        continua_em_bateria=definicao_autostart.get(
            "continua_em_bateria"
        ),
    )

    mercados_prontos = [
        mercado for mercado, item in mercados.items() if item["pronto"]
    ]
    completo = bool(
        operacao_ok
        and temporal_ok
        and api_ok
        and valor_mercado_ok
        and portfolio_edge_ok
        and cadeia_custodia_clv_ok
        and telegram_teste_ok
        and politica_telegram_ok
        and evidencia_filtro_ok
        and experimento_ritmo_aprovado
        and historico_drift_ok
        and hipoteses_sombra_ok
        and validacao_gols_antecipados_ok
        and persistencia_watchdog_ok
        and pre_live_operacional_ok
        and pre_live_validacao_ok
        and provas_oficiais > 0
        and autostart_ok
        and backup_espelho_pronto
        and len(mercados_prontos) == len(mercados_exigidos)
    )
    if completo:
        estado_geral = "profissional_completo"
    elif pausa_planejada:
        estado_geral = "pausa_planejada"
    elif liberados:
        estado_geral = "sinais_oficiais_parciais"
    elif supervisao_inicializando:
        estado_geral = "supervisao_inicializando"
    elif not operacao_ok:
        estado_geral = "operacao_degradada"
    else:
        estado_geral = "coleta_profissional_em_validacao"
    pendencias = []
    for nome, item in componentes.items():
        if nome != "mercados" and not item["pronto"]:
            dependencia_raiz = (item.get("evidencias") or {}).get(
                "dependencia_raiz"
            )
            if (
                dependencia_raiz
                and not (componentes.get(dependencia_raiz) or {}).get(
                    "pronto", True
                )
            ):
                continue
            pendencias.append({
                "requisito": nome,
                "estado": item["estado"],
                "categoria": classificar_pendencia_prontidao(item["estado"]),
            })
    pendencias.extend(
        {
            "requisito": f"mercado:{mercado}",
            "estado": item["estado"],
            "categoria": classificar_pendencia_prontidao(item["estado"]),
        }
        for mercado, item in mercados.items() if not item["pronto"]
    )
    pendencias_por_categoria = {}
    for item in pendencias:
        categoria = item["categoria"]
        pendencias_por_categoria[categoria] = (
            pendencias_por_categoria.get(categoria, 0) + 1
        )
    return {
        "pronto_profissional_completo": completo,
        "estado_geral": estado_geral,
        "mercados_liberados_para_oficial": liberados,
        "mercados_exigidos": list(mercados_exigidos),
        "mercados_suspensos": list(mercados_suspensos),
        "componentes": componentes,
        "diagnosticos_informativos": {
            "clv_live": clv_live,
            "exposicao_coleta_prospectiva": (
                exposicao_coleta if exposicao_auditada else {}
            ),
        },
        "pendencias": pendencias,
        "pendencias_por_categoria": pendencias_por_categoria,
        "falha_tecnica_ativa": bool(
            pendencias_por_categoria.get("pendencia_tecnica")
        ),
    }


def resumir_resultado_prontidao(resultado):
    """Reduz a auditoria completa a um painel operacional estável.

    O relatório integral é mantido para auditoria, enquanto este resumo evita
    que operadores e supervisores precisem interpretar milhares de linhas para
    descobrir se há falha técnica ou apenas formação normal de amostra.
    """
    componentes = resultado.get("componentes") or {}
    mercados = componentes.get("mercados") or {}
    scanner = componentes.get("prioridade_scanner_packball") or {}
    worker_treino = componentes.get("worker_treino_isolado") or {}
    clv_live = (
        (resultado.get("diagnosticos_informativos") or {}).get("clv_live")
        or {}
    )
    exposicao_coleta = (
        (resultado.get("diagnosticos_informativos") or {}).get(
            "exposicao_coleta_prospectiva"
        ) or {}
    )
    mark_to_market = clv_live.get("total") or {}
    sobreviventes = clv_live.get(
        "movimento_preco_contratos_sobreviventes"
    ) or {}
    cotacao_prospectiva = clv_live.get(
        "cobertura_cotacao_entrada_prospectiva"
    ) or {}
    coorte_clv_fixa = clv_live.get("coorte_clv_prospectiva_fixa") or {}
    cadeia_custodia = clv_live.get("cadeia_custodia_clv") or {}
    por_mercado_clv = clv_live.get("por_mercado") or {}
    diagnostico_valor_mercado = {
        "versao": clv_live.get("versao"),
        "criterio_independencia": clv_live.get("criterio_independencia"),
        "entregas_brutas": clv_live.get("entregas_brutas_consultadas"),
        "sinais_independentes": clv_live.get(
            "sinais_independentes_consultados"
        ),
        "sinais_partida_mercado": clv_live.get(
            "sinais_partida_mercado_consultados"
        ),
        "selecao_unidade_antes_da_comparabilidade": clv_live.get(
            "selecao_unidade_antes_da_comparabilidade"
        ),
        "comparaveis": clv_live.get("comparaveis"),
        "taxa_cobertura": clv_live.get("taxa_cobertura"),
        "cadeia_custodia": {
            chave: cadeia_custodia.get(chave)
            for chave in (
                "versao", "saudavel", "estado", "gatilhos_exigidos",
                "gatilhos_presentes", "gatilhos_ausentes",
                "definicoes_invalidas", "fingerprint_definicoes",
                "integridade_evidencias",
                "bloqueia_inferencia",
            )
        },
        "cotacao_entrada_prospectiva": {
            chave: cotacao_prospectiva.get(chave)
            for chave in (
                "versao", "criterio_coorte",
                "selecao_antes_da_comparabilidade",
                "entregas_legadas_fora_do_denominador",
                "entregas_instrumentadas",
                "cotacoes_congeladas_validas",
                "cotacoes_congeladas_invalidas",
                "comparaveis_apos_horizonte",
                "taxa_cobertura_cotacao_entrada",
                "cobertura_minima", "amostra_minima",
                "amostra_suficiente", "cobertura_suficiente",
                "estado", "estados_persistidos", "falhas",
                "pode_informar_edge", "pode_decidir_edge",
            )
        },
        "coorte_prospectiva_fixa": {
            chave: coorte_clv_fixa.get(chave)
            for chave in (
                "versao", "criterio_coorte", "selecao_antes_do_resultado",
                "divisao_fixa", "tamanho_planejado",
                "tamanho_desenvolvimento", "tamanho_holdout",
                "unidades_coorte", "unidades_faltantes",
                "unidades_excedentes_fora_coorte", "primeiro_sinal_id",
                "ultimo_sinal_id", "fingerprint_ids", "coorte_completa",
                "cobertura_cotacao_entrada_suficiente",
                "cobertura_horizonte_suficiente", "pronta_para_conclusao",
                "pronta_estatisticamente", "cadeia_custodia_saudavel",
                "vantagem_replicada", "desvantagem_replicada", "estado",
                "pode_informar_edge", "pode_decidir_edge",
            )
        },
        "mark_to_market": {
            chave: mark_to_market.get(chave)
            for chave in (
                "amostra", "media_pontos_probabilidade",
                "mediana_pontos_probabilidade", "intervalo_media_95",
                "estado_evidencia", "pode_informar_edge",
                "pode_decidir_edge", "taxa_cobertura",
                "cobertura_minima_informar_edge",
                "cobertura_suficiente_para_informar_edge",
                "vies_correlacao_intrajogo",
            )
        },
        "movimento_preco_sobreviventes": {
            chave: sobreviventes.get(chave)
            for chave in (
                "amostra", "media_pontos_probabilidade",
                "intervalo_media_95", "estado_evidencia",
                "vies_selecao_sobrevivencia", "pode_decidir_edge",
            )
        },
        "por_mercado": {
            mercado: {
                "comparaveis": item.get("comparaveis"),
                "taxa_cobertura": item.get("taxa_cobertura"),
                "media_mark_to_market": item.get(
                    "media_pontos_probabilidade"
                ),
                "intervalo_mark_to_market_95": item.get(
                    "intervalo_media_95"
                ),
                "estado_evidencia": item.get("estado_evidencia"),
            }
            for mercado, item in por_mercado_clv.items()
        },
        "gate_operacional": False,
        "promocao_automatica": False,
    }

    pendencias = []
    for pendencia in resultado.get("pendencias") or ():
        requisito = str(pendencia.get("requisito") or "")
        if requisito.startswith("mercado:"):
            componente = mercados.get(requisito.split(":", 1)[1]) or {}
        else:
            componente = componentes.get(requisito) or {}
        pendencias.append({
            "requisito": requisito,
            "estado": pendencia.get("estado"),
            "categoria": pendencia.get("categoria"),
            "resumo": componente.get("resumo"),
        })

    progresso_mercados = {}
    for mercado in resultado.get("mercados_exigidos") or ():
        item = mercados.get(mercado) or {}
        evidencias = item.get("evidencias") or {}
        resumo = {
            "estado": item.get("estado"),
            "pronto": bool(item.get("pronto")),
            "resumo": item.get("resumo"),
            "metodo_efetivo": evidencias.get("metodo_efetivo"),
        }
        for chave in (
            "amostra", "validos", "greens", "half_greens", "voids",
            "half_reds", "reds", "faltam", "roi",
            "intervalo_roi_95", "decisao_estatistica",
            "diversidade_estado", "dias_distintos", "ligas_distintas",
        ):
            if evidencias.get(chave) is not None:
                resumo[chave] = evidencias[chave]
        metodos_ativos = evidencias.get("metodos_ativos")
        if metodos_ativos:
            resumo["metodos_ativos"] = [
                {
                    chave: _valor_progresso_metodo(metodo, chave)
                    for chave in (
                        "identificador", "versao", "candidatos",
                        "tamanho_coorte", "validos", "greens",
                        "reds", "pendentes", "roi", "intervalo_roi_95",
                        "faltam", "decisao_estatistica", "registrado_em",
                        "exposicao_coorte_prontidao", "funil_candidatos",
                        "funil_gerador",
                    )
                    if _valor_progresso_metodo(metodo, chave) is not None
                }
                for metodo in metodos_ativos
            ]
        validacao_prospectiva = evidencias.get(
            "validacao_prospectiva"
        )
        if validacao_prospectiva:
            resumo["validacao_prospectiva"] = dict(
                validacao_prospectiva
            )
        metodo_legado = evidencias.get("metodo_legado")
        if metodo_legado:
            resumo["metodo_legado"] = {
                chave: metodo_legado.get(chave)
                for chave in (
                    "estado", "resumo", "motivo", "amostra_validacao",
                    "roi_validacao", "auc_validacao",
                    "validacao_prospectiva",
                )
                if metodo_legado.get(chave) is not None
            }
        challenger_balanceado = evidencias.get("challenger_balanceado")
        if challenger_balanceado:
            resumo["challenger_balanceado"] = {
                chave: challenger_balanceado.get(chave)
                for chave in (
                    "versao_validacao", "regra_versao", "estado",
                    "decisao", "candidatos", "tamanho_coorte", "validos",
                    "greens", "reds", "pendentes", "faltam", "roi",
                    "intervalo_roi_95", "alerta_desfavoravel",
                    "resultados_completos", "grupo_teste_ativo",
                    "gerador_sombra_ativo", "telegram_oficial",
                    "promocao_automatica", "checkpoint_seguranca",
                    "controle_operacional", "funil_origem",
                    "registrado_em", "exposicao_coorte_prontidao",
                )
                if challenger_balanceado.get(chave) is not None
            }
        progresso_mercados[mercado] = resumo

    return {
        "pronto_profissional_completo": bool(
            resultado.get("pronto_profissional_completo")
        ),
        "estado_geral": resultado.get("estado_geral"),
        "falha_tecnica_ativa": bool(resultado.get("falha_tecnica_ativa")),
        "mercados_liberados_para_oficial": list(
            resultado.get("mercados_liberados_para_oficial") or ()
        ),
        "pendencias_total": len(pendencias),
        "pendencias_por_categoria": (
            resultado.get("pendencias_por_categoria") or {}
        ),
        "pendencias": pendencias,
        "progresso_mercados": progresso_mercados,
        "diagnostico_valor_mercado": diagnostico_valor_mercado,
        "exposicao_coleta_prospectiva": exposicao_coleta or None,
        "previsao_prontidao_operacional": (
            diagnosticar_prazo_prontidao(resultado)
        ),
        "worker_treino_isolado": (
            {
                "estado": worker_treino.get("estado"),
                "pronto": bool(worker_treino.get("pronto")),
                "resumo": worker_treino.get("resumo"),
                **(worker_treino.get("evidencias") or {}),
            }
            if worker_treino else None
        ),
        "scanner_packball": (
            {
                "estado": scanner.get("estado"),
                "pronto": bool(scanner.get("pronto")),
                "resumo": scanner.get("resumo"),
                **(scanner.get("evidencias") or {}),
            }
            if scanner else None
        ),
    }


VERSAO_PREVISAO_PRONTIDAO = "previsao-prontidao-operacional-v2"
MINIMO_UNIDADES_RITMO_PRONTIDAO = 5
MINIMO_HORAS_RITMO_PRONTIDAO = 24.0
LIMITE_UNIDADES_RITMO_OBSERVADO = 15
LIMITE_HORAS_RITMO_OBSERVADO = 72.0
MINIMO_HORAS_ALERTA_FUNIL = 24.0
MINIMO_CICLOS_COM_PARTIDAS_ALERTA_FUNIL = 20
MINIMO_HORAS_OBSERVACAO_FUNIL = 6.0
MINIMO_CICLOS_COM_PARTIDAS_OBSERVACAO_FUNIL = 5


def _faltante_quantificado(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if numero >= 0 else None


def _numero_finito_nao_negativo(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numero) or numero < 0:
        return None
    return numero


def _primeiro_progresso(item, *chaves):
    item = dict(item or {})
    for chave in chaves:
        valor = _faltante_quantificado(item.get(chave))
        if valor is not None:
            return valor
    return None


def diagnosticar_prazo_prontidao(resultado):
    """Expõe o trabalho restante sem inventar uma data de liberação.

    As coortes podem se sobrepor e cada método possui sua própria unidade
    causal. Por isso os valores abaixo não são somados. Durante manutenção, o
    tempo de parede também não é tratado como tempo de coleta.
    """
    componentes = resultado.get("componentes") or {}
    requisitos = {}

    def adicionar(
        identificador, *, tipo, faltam, mercado=None,
        observadas=None, tamanho_coorte=None, exposicao=None,
    ):
        restante = _faltante_quantificado(faltam)
        if restante is None:
            return
        observadas = _faltante_quantificado(observadas)
        tamanho_coorte = _faltante_quantificado(tamanho_coorte)
        if observadas is None and tamanho_coorte is not None:
            observadas = max(tamanho_coorte - restante, 0)
        if tamanho_coorte is None and observadas is not None:
            tamanho_coorte = observadas + restante

        exposicao = dict(exposicao or {})
        horas = _numero_finito_nao_negativo(
            exposicao.get("exposicao_operacional_confirmada_horas")
        )
        telemetria_exposicao_saudavel = bool(
            exposicao
            and exposicao.get("saudavel") is True
            and exposicao.get("requer_atencao") is not True
        )
        cobertura_desde_ancora = bool(
            exposicao.get("cobertura_telemetria_desde_ancora") is True
        )
        exposicao_apta_para_ritmo = bool(
            telemetria_exposicao_saudavel and cobertura_desde_ancora
        )
        ciclos_com_partidas = _faltante_quantificado(
            exposicao.get("ciclos_com_partidas")
        )
        ciclos_com_partidas = ciclos_com_partidas or 0
        if restante == 0:
            saude_formacao = "coorte_concluida"
            requer_diagnostico_funil = False
        elif (
            exposicao.get("manutencao_ativa") is True
            and (horas is None or horas == 0)
        ):
            saude_formacao = "aguardando_retomada"
            requer_diagnostico_funil = False
        elif not exposicao:
            saude_formacao = (
                "progresso_sem_relogio_exato"
                if (observadas or 0) > 0
                else "sem_telemetria_da_coorte"
            )
            requer_diagnostico_funil = False
        elif not telemetria_exposicao_saudavel:
            saude_formacao = "telemetria_invalida"
            requer_diagnostico_funil = True
        elif not cobertura_desde_ancora:
            saude_formacao = "cobertura_telemetria_incompleta"
            requer_diagnostico_funil = False
        elif (
            (observadas or 0) == 0
            and horas is not None
            and horas >= MINIMO_HORAS_ALERTA_FUNIL
            and ciclos_com_partidas
            >= MINIMO_CICLOS_COM_PARTIDAS_ALERTA_FUNIL
        ):
            saude_formacao = "sem_rendimento_requer_diagnostico"
            requer_diagnostico_funil = True
        elif (
            (observadas or 0) == 0
            and horas is not None
            and horas >= MINIMO_HORAS_OBSERVACAO_FUNIL
            and ciclos_com_partidas
            >= MINIMO_CICLOS_COM_PARTIDAS_OBSERVACAO_FUNIL
        ):
            saude_formacao = "sem_rendimento_em_observacao"
            requer_diagnostico_funil = False
        elif (observadas or 0) > 0:
            saude_formacao = "formando_amostra"
            requer_diagnostico_funil = False
        else:
            saude_formacao = "aguardando_exposicao_minima"
            requer_diagnostico_funil = False
        ritmo = None
        dias_operacionais = None
        confiabilidade = "sem_ritmo"
        if (
            observadas is not None
            and observadas >= MINIMO_UNIDADES_RITMO_PRONTIDAO
            and horas is not None
            and horas >= MINIMO_HORAS_RITMO_PRONTIDAO
            and exposicao_apta_para_ritmo
        ):
            ritmo_calculado = observadas / (horas / 24.0)
            if math.isfinite(ritmo_calculado) and ritmo_calculado > 0:
                ritmo = round(ritmo_calculado, 3)
                dias_operacionais = int(math.ceil(restante / ritmo_calculado))
                confiabilidade = (
                    "preliminar"
                    if (
                        observadas < LIMITE_UNIDADES_RITMO_OBSERVADO
                        or horas < LIMITE_HORAS_RITMO_OBSERVADO
                    )
                    else "observada"
                )

        requisitos[identificador] = {
            "tipo": tipo,
            "mercado": mercado,
            "faltam_unidades_independentes": restante,
            "unidades_observadas": observadas,
            "tamanho_coorte": tamanho_coorte,
            "exposicao_operacional_horas": (
                round(horas, 3) if horas is not None else None
            ),
            "exposicao_estado": exposicao.get("estado"),
            "telemetria_exposicao_saudavel": (
                telemetria_exposicao_saudavel
            ),
            "cobertura_telemetria_desde_ancora": cobertura_desde_ancora,
            "exposicao_apta_para_ritmo": exposicao_apta_para_ritmo,
            "ciclos_com_partidas": ciclos_com_partidas,
            "saude_formacao_coorte": saude_formacao,
            "requer_diagnostico_funil": requer_diagnostico_funil,
            "ritmo_por_24h_operacionais": ritmo,
            "dias_operacionais_estimados": dias_operacionais,
            "confiabilidade_ritmo": confiabilidade,
        }

    pre_live = componentes.get("seletor_pre_live_validacao") or {}
    evidencia_pre_live = pre_live.get("evidencias") or {}
    minimo_pre_live = _faltante_quantificado(
        evidencia_pre_live.get("amostra_minima")
    )
    resultados_pre_live = _faltante_quantificado(
        evidencia_pre_live.get("resultados")
    )
    if minimo_pre_live is not None and resultados_pre_live is not None:
        adicionar(
            "pre_live:seletor_preciso",
            tipo="coorte_pre_live",
            faltam=max(minimo_pre_live - resultados_pre_live, 0),
            mercado="pre_live",
            observadas=resultados_pre_live,
            tamanho_coorte=minimo_pre_live,
            exposicao=evidencia_pre_live.get(
                "exposicao_coorte_prontidao"
            ),
        )

    mercados = componentes.get("mercados") or {}
    for mercado, componente in mercados.items():
        evidencias = componente.get("evidencias") or {}
        prospectiva = evidencias.get("validacao_prospectiva") or {}
        fonte_principal = (
            prospectiva
            if prospectiva.get("faltam") is not None
            else evidencias
        )
        faltam_principal = fonte_principal.get("faltam")
        observadas_principal = _primeiro_progresso(
            fonte_principal,
            "candidatos", "candidatos_coorte", "unidades_coorte",
            "resultados_resolvidos", "validos", "amostra",
        )
        adicionar(
            f"mercado:{mercado}:principal",
            tipo="coorte_mercado",
            faltam=faltam_principal,
            mercado=mercado,
            observadas=observadas_principal,
            tamanho_coorte=fonte_principal.get("tamanho_coorte"),
            exposicao=fonte_principal.get(
                "exposicao_coorte_prontidao"
            ),
        )
        for indice, metodo in enumerate(evidencias.get("metodos_ativos") or ()):
            identificador = str(
                metodo.get("identificador")
                or metodo.get("versao")
                or indice
            )
            adicionar(
                f"mercado:{mercado}:metodo:{identificador}",
                tipo="coorte_metodo",
                faltam=_valor_progresso_metodo(metodo, "faltam"),
                mercado=mercado,
                observadas=(
                    _valor_progresso_metodo(metodo, "candidatos")
                    if _valor_progresso_metodo(
                        metodo, "candidatos"
                    ) is not None
                    else _valor_progresso_metodo(metodo, "validos")
                ),
                tamanho_coorte=_valor_progresso_metodo(
                    metodo, "tamanho_coorte"
                ),
                exposicao=_valor_progresso_metodo(
                    metodo, "exposicao_coorte_prontidao"
                ),
            )
        challenger = evidencias.get("challenger_balanceado") or {}
        if challenger:
            adicionar(
                f"mercado:{mercado}:challenger_balanceado",
                tipo="coorte_challenger",
                faltam=challenger.get("faltam"),
                mercado=mercado,
                observadas=_primeiro_progresso(
                    challenger, "candidatos", "validos"
                ),
                tamanho_coorte=challenger.get("tamanho_coorte"),
                exposicao=challenger.get(
                    "exposicao_coorte_prontidao"
                ),
            )
        if (
            prospectiva
            and f"mercado:{mercado}:principal" not in requisitos
        ):
            adicionar(
                f"mercado:{mercado}:validacao_prospectiva",
                tipo="coorte_mercado",
                faltam=prospectiva.get("faltam"),
                mercado=mercado,
                observadas=_primeiro_progresso(
                    prospectiva, "candidatos", "validos", "amostra"
                ),
                tamanho_coorte=prospectiva.get("tamanho_coorte"),
                exposicao=prospectiva.get(
                    "exposicao_coorte_prontidao"
                ),
            )

    clv_live = (
        (resultado.get("diagnosticos_informativos") or {}).get("clv_live")
        or {}
    )
    coorte_clv = clv_live.get("coorte_clv_prospectiva_fixa") or {}
    adicionar(
        "valor_mercado:clv_prospectivo",
        tipo="coorte_valor_mercado",
        faltam=coorte_clv.get("unidades_faltantes"),
        mercado=None,
        observadas=coorte_clv.get("unidades_coorte"),
        tamanho_coorte=coorte_clv.get("tamanho_planejado"),
        exposicao=coorte_clv.get("exposicao_coorte_prontidao"),
    )

    ordenados = [
        {"identificador": identificador, **item}
        for identificador, item in sorted(requisitos.items())
    ]
    maior_faltante = max(
        (
            item["faltam_unidades_independentes"]
            for item in ordenados
        ),
        default=0,
    )
    requisitos_com_ritmo = [
        item for item in ordenados
        if item.get("dias_operacionais_estimados") is not None
    ]
    requisitos_requerem_diagnostico = [
        item["identificador"] for item in ordenados
        if item.get("requer_diagnostico_funil") is True
    ]
    requisitos_sem_relogio_exato = [
        item["identificador"] for item in ordenados
        if item.get("saude_formacao_coorte")
        == "progresso_sem_relogio_exato"
    ]
    maior_dias_operacionais = max(
        (
            item["dias_operacionais_estimados"]
            for item in requisitos_com_ritmo
        ),
        default=None,
    )
    manutencao = componentes.get("modo_manutencao") or {}
    manutencao_ativa = bool(
        (manutencao.get("evidencias") or {}).get("ativo")
    )
    completo = bool(resultado.get("pronto_profissional_completo"))
    if completo:
        estado = "pronto"
        motivo = None
    elif manutencao_ativa:
        estado = "suspenso_manutencao"
        motivo = "modo_manutencao_ativo"
    elif requisitos_com_ritmo:
        estado = "coletando_com_ritmo_operacional_observado"
        motivo = "ritmos_por_coorte_nao_formam_prazo_global"
    elif ordenados:
        estado = "aguardando_ritmo_prospectivo_exato"
        motivo = "ritmo_das_coortes_atuais_ainda_nao_observado"
    else:
        estado = "aguardando_validacao_nao_quantificavel"
        motivo = "existem_gates_sem_meta_numerica"

    return {
        "versao": VERSAO_PREVISAO_PRONTIDAO,
        "estado": estado,
        "motivo": motivo,
        "coleta_ativa": bool(not manutencao_ativa and not completo),
        "calendario_em_contagem": bool(not manutencao_ativa and not completo),
        "prazo_calendario_disponivel": False,
        "dias_estimados": None,
        "data_estimada": None,
        "exige_retomada_manual": manutencao_ativa,
        "maior_faltante_quantificado": maior_faltante,
        "requisitos_com_ritmo_estimado": len(requisitos_com_ritmo),
        "maior_dias_operacionais_por_coorte": maior_dias_operacionais,
        "requisitos_requerem_diagnostico_funil": (
            requisitos_requerem_diagnostico
        ),
        "requisitos_sem_relogio_exato": requisitos_sem_relogio_exato,
        "requisitos_quantificados": ordenados,
        "agregacao": "coortes_independentes_nao_somaveis",
        "tempo_de_parede_conta_como_amostra": False,
        "promocao_automatica": False,
    }


def resumir_fluxo_amostras_ativas(
    conexao, mercados_exigidos, bracos=None, agora=None,
):
    """Extrai o heartbeat dos funis sem interpretar falta de oportunidade."""
    agora = agora or datetime.now()
    referencia_local = agora.replace(tzinfo=None)
    inicio_24h = (referencia_local - timedelta(hours=24)).isoformat()
    alvos = [
        (mercado, versao_regra_para_mercado(mercado))
        for mercado in mercados_exigidos or ()
    ]
    por_mercado = {}
    if alvos:
        filtros = " OR ".join(
            "(s.mercado=? AND s.regra_versao=?)" for _ in alvos
        )
        parametros = [inicio_24h]
        for mercado, versao in alvos:
            parametros.extend((mercado, versao))
        linhas = conexao.execute(
            f"""
            SELECT s.mercado, s.regra_versao,
                   COUNT(*) AS registros,
                   COUNT(DISTINCT s.partida_id) AS jogos,
                   SUM(CASE WHEN datetime(s.criado_em) >= datetime(?)
                            THEN 1 ELSE 0 END) AS registros_24h,
                   SUM(CASE WHEN r.sinal_id IS NOT NULL
                            THEN 1 ELSE 0 END) AS resolvidos,
                   MAX(s.criado_em) AS ultimo_candidato_em,
                   MAX(r.encerrado_em) AS ultimo_resultado_em
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE {filtros}
            GROUP BY s.mercado, s.regra_versao
            """,
            parametros,
        ).fetchall()
        encontrados = {
            (linha["mercado"], linha["regra_versao"]): dict(linha)
            for linha in linhas
        }
        for mercado, versao in alvos:
            item = encontrados.get((mercado, versao), {})
            por_mercado[mercado] = {
                "versao": versao,
                "registros": int(item.get("registros", 0) or 0),
                "jogos": int(item.get("jogos", 0) or 0),
                "registros_24h": int(item.get("registros_24h", 0) or 0),
                "resolvidos": int(item.get("resolvidos", 0) or 0),
                "ultimo_candidato_em": item.get("ultimo_candidato_em"),
                "ultimo_resultado_em": item.get("ultimo_resultado_em"),
            }

    # O Gol FT reforçado é uma política composta: ela avalia o candidato
    # v6 em todos os snapshots, mas cria uma linha v11 somente quando aprova a
    # entrada. O heartbeat persistido no snapshot prova que a política rodou,
    # sem transformar ausência legítima de oportunidade em falha do funil.
    item_gol_ft = por_mercado.get("gol_ft")
    if (
        item_gol_ft
        and item_gol_ft.get("versao") == VERSAO_GOL_FT_REFORCADO
    ):
        heartbeat = conexao.execute(
            """
            SELECT coletado_em,
                   json_extract(
                       qualidade_json, '$.gol_ft_reforcado.ativa'
                   ) AS ativa,
                   json_extract(
                       qualidade_json, '$.gol_ft_reforcado.versao'
                   ) AS versao,
                   json_extract(
                       qualidade_json, '$.gol_ft_reforcado.avaliados'
                   ) AS avaliados,
                   json_extract(
                       qualidade_json, '$.gol_ft_reforcado.oficiais'
                   ) AS oficiais,
                   json_extract(
                       qualidade_json, '$.gol_ft_reforcado.oficial_ativo'
                   ) AS oficial_ativo,
                   json_extract(
                       qualidade_json,
                       '$.gol_ft_reforcado.reforcados_sombra'
                   ) AS reforcados_sombra
            FROM snapshots
            WHERE json_extract(
                      qualidade_json, '$.gol_ft_reforcado.versao'
                  )=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (VERSAO_GOL_FT_REFORCADO,),
        ).fetchone()
        if heartbeat is not None:
            item_gol_ft["heartbeat_politica"] = {
                "observado_em": heartbeat["coletado_em"],
                "ativa": bool(heartbeat["ativa"]),
                "versao": heartbeat["versao"],
                "avaliados": int(heartbeat["avaliados"] or 0),
                "oficiais": int(heartbeat["oficiais"] or 0),
                "oficial_ativo": bool(heartbeat["oficial_ativo"]),
                "reforcados_sombra": int(
                    heartbeat["reforcados_sombra"] or 0
                ),
            }

    # A V8c também pode passar vários ciclos sem oportunidade. O heartbeat
    # comprova que a quarentena foi executada, sem inventar um candidato.
    item_gol_ht = por_mercado.get("gol_ht")
    if (
        item_gol_ht
        and item_gol_ht.get("versao") == VERSAO_GOL_HT_PROTEGIDO
    ):
        heartbeat = conexao.execute(
            """
            SELECT coletado_em,
                   json_extract(
                       qualidade_json, '$.gol_ht_protegido.ativa'
                   ) AS ativa,
                   json_extract(
                       qualidade_json, '$.gol_ht_protegido.versao'
                   ) AS versao,
                   json_extract(
                       qualidade_json, '$.gol_ht_protegido.avaliados'
                   ) AS avaliados,
                   json_extract(
                       qualidade_json, '$.gol_ht_protegido.oficiais'
                   ) AS oficiais,
                   json_extract(
                       qualidade_json, '$.gol_ht_protegido.oficial_ativo'
                   ) AS oficial_ativo,
                   json_extract(
                       qualidade_json, '$.gol_ht_protegido.v8c_sombra'
                   ) AS v8c_sombra
            FROM snapshots
            WHERE json_extract(
                      qualidade_json, '$.gol_ht_protegido.versao'
                  )=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (VERSAO_GOL_HT_PROTEGIDO,),
        ).fetchone()
        if heartbeat is not None:
            item_gol_ht["heartbeat_politica"] = {
                "observado_em": heartbeat["coletado_em"],
                "ativa": bool(heartbeat["ativa"]),
                "versao": heartbeat["versao"],
                "avaliados": int(heartbeat["avaliados"] or 0),
                "oficiais": int(heartbeat["oficiais"] or 0),
                "oficial_ativo": bool(heartbeat["oficial_ativo"]),
                "sombra": int(heartbeat["v8c_sombra"] or 0),
            }

    bracos = dict(bracos or {})
    por_braco = {}
    if bracos:
        versoes = tuple(bracos)
        marcadores = ",".join("?" for _ in versoes)
        linhas = conexao.execute(
            f"""
            SELECT json_extract(
                       s.features_json, '$.exploracao_sombra.versao'
                   ) AS versao,
                   COUNT(*) AS registros,
                   COUNT(DISTINCT s.partida_id) AS jogos,
                   SUM(CASE WHEN datetime(s.criado_em) >= datetime(?)
                            THEN 1 ELSE 0 END) AS registros_24h,
                   SUM(CASE WHEN r.sinal_id IS NOT NULL
                            THEN 1 ELSE 0 END) AS resolvidos,
                   MAX(s.criado_em) AS ultimo_candidato_em,
                   MAX(r.encerrado_em) AS ultimo_resultado_em
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE json_extract(
                      s.features_json, '$.exploracao_sombra.versao'
                  ) IN ({marcadores})
            GROUP BY versao
            """,
            (inicio_24h, *versoes),
        ).fetchall()
        encontrados = {linha["versao"]: dict(linha) for linha in linhas}
        for versao, ativo in bracos.items():
            item = encontrados.get(versao, {})
            por_braco[versao] = {
                "ativo": bool(ativo),
                "registros": int(item.get("registros", 0) or 0),
                "jogos": int(item.get("jogos", 0) or 0),
                "registros_24h": int(item.get("registros_24h", 0) or 0),
                "resolvidos": int(item.get("resolvidos", 0) or 0),
                "ultimo_candidato_em": item.get("ultimo_candidato_em"),
                "ultimo_resultado_em": item.get("ultimo_resultado_em"),
            }
    return {
        "saudavel": True,
        "coletado_em": referencia_local.replace(microsecond=0).isoformat(),
        "mercados": por_mercado,
        "bracos": por_braco,
    }


def coletar_evidencias(pasta):
    pasta = Path(pasta).resolve()
    agora_evidencias = datetime.now().replace(microsecond=0)
    modo_manutencao = ler_modo_manutencao(pasta)
    load_dotenv(pasta / ".env")
    configuracao = validar_configuracao()
    worker_treino_isolado = verificar_worker_treino_isolado()
    recursos_configurados = configuracao.get("recursos") or {}
    controle_v2b_ft = ler_estado_v2b_ft(
        pasta / "v2b_ft_estado.json"
    )
    controle_gols_antecipados = ler_estado_gols_antecipados(
        pasta / "gols_antecipados_estado.json"
    )
    controle_filtro_gol_ht_preciso = ler_estado_filtro_gol_ht_preciso(
        pasta / "filtro_gol_ht_antecipado_preciso_estado.json"
    )
    controle_filtro_gol_ft_preciso = ler_estado_filtro_gol_ft_preciso(
        pasta / "filtro_gol_ft_antecipado_preciso_estado.json"
    )
    controle_escanteios_ft_asiatico = ler_estado_escanteios_ft_asiatico(
        pasta / "escanteios_ft_asiatico_estado.json"
    )
    controle_proximo_gol_balanceado = (
        ler_estado_proximo_gol_balanceado(
            pasta / "proximo_gol_balanceado_estado.json"
        )
    )
    v2b_ft_configurado = bool(recursos_configurados.get(
        "gol_ft_capacidade_contextual_v2_grupo"
    ))
    bracos_fluxo = {
        VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA: bool(
            recursos_configurados.get("proximo_gol_balanceado_sombra")
        ),
        VERSAO_GOL_FT_CAPACIDADE_CONTEXTUAL_V2: v2b_ft_configurado,
        VERSAO_GOL_HT_CAPACIDADE_CONTEXTUAL_V2: bool(
            recursos_configurados.get(
                "gol_ht_capacidade_contextual_v2_grupo"
            )
        ),
        VERSAO_GOL_HT_00_MIN20: bool(
            recursos_configurados.get("gol_ht_00_min20_grupo")
        ),
        VERSAO_GOL_HT_ANTECIPADO: bool(
            recursos_configurados.get("gols_antecipados_grupo")
        ),
        VERSAO_GOL_FT_ANTECIPADO: bool(
            recursos_configurados.get("gols_antecipados_grupo")
        ),
        VERSAO_GOL_FT_ANTECIPADO_2T: bool(
            recursos_configurados.get("gols_antecipados_grupo")
        ),
        VERSAO_TOP_CRITERIO_HT: bool(
            recursos_configurados.get("top_criterios_gols_grupo")
        ),
        VERSAO_TOP_CRITERIO_FT: bool(
            recursos_configurados.get("top_criterios_gols_grupo")
        ),
    }
    caminho_banco = pasta / "monitor_packball.db"
    caminho_log = pasta / "monitor_eventos.jsonl"
    telemetria_exposicao = carregar_eventos_observabilidade(caminho_log)
    validacao = verificar_validacao(caminho_banco)
    chave_proximo_gol_balanceado = (
        "progresso_proximo_gol_balanceado_sombra"
    )
    if isinstance(validacao.get(chave_proximo_gol_balanceado), dict):
        validacao[chave_proximo_gol_balanceado] = _com_exposicao_coorte(
            validacao[chave_proximo_gol_balanceado],
            telemetria=telemetria_exposicao,
            modo_manutencao=modo_manutencao,
            agora=agora_evidencias,
        )
    estado_watchdog = ler_estado(pasta / "watchdog_estado.json")
    monitor = ler_estado(pasta / "monitor_processo.json")
    watchdog = ler_estado(pasta / "watchdog_processo.json")
    avaliacoes_periodicas = {
        "acompanhamento_odd": verificar_avaliacao_acompanhamento_odd(
            pasta / "avaliacao_acompanhamento_odd_estado.json"
        ),
        "prioridade_ligas_gols": verificar_avaliacao_prioridade_ligas_gols(
            pasta / "avaliacao_prioridade_ligas_gols_estado.json"
        ),
        "desajuste_odds": verificar_avaliacao_desajuste_odds(
            pasta / "avaliacao_desajuste_odds_estado.json"
        ),
        "quarentena_fallback_ht": (
            verificar_avaliacao_quarentena_fallback_ht(
                pasta / "avaliacao_quarentena_fallback_ht_estado.json"
            )
        ),
    }
    espelho_watchdog = diagnosticar_frescor_espelho_watchdog(
        estado_watchdog, watchdog
    )
    validacao_runtime = estado_watchdog.get("validacao") or {}
    for chave in (
        "ritmo_acesso_packball",
        "experimento_ritmo_packball",
        "politica_telegram",
        "prioridade_scanner_packball",
    ):
        if isinstance(validacao_runtime.get(chave), dict):
            validacao[chave] = validacao_runtime[chave]
    if validacao_runtime:
        validacao["saudavel"] = bool(
            validacao.get("saudavel")
            and validacao_runtime.get("saudavel")
        )
        validacao["motivos"] = sorted(set(
            (validacao.get("motivos") or [])
            + (validacao_runtime.get("motivos") or [])
        ))
    coleta = verificar_coleta(caminho_log)
    backup = verificar_ponto_recuperacao(pasta / "backups")
    backup_espelho = verificar_backup_espelho(
        pasta / "backups",
        os.getenv("BACKUP_ESPELHO_DIRETORIO") or None,
        verificar_integridade=False,
    )
    pre_live = coletar_estado_pre_live_autoritativo(
        pasta, estado_watchdog
    )
    pre_live["filtro_preciso"] = _com_exposicao_coorte(
        resumir_validacao_pre_live_preciso_arquivo(pasta / "pre_live.db"),
        telemetria=telemetria_exposicao,
        modo_manutencao=modo_manutencao,
        agora=agora_evidencias,
    )
    pre_live["controle_filtro_preciso"] = ler_estado_pre_live_preciso(
        pasta / "pre_live_preciso_estado.json"
    )
    backups_pre_live = sorted(
        (pasta / "backups" / "pre_live").glob(
            "pre_live_[0-9]*.db"
        ),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if backups_pre_live:
        backup_pre_live = verificar_backup_pre_live(backups_pre_live[0])
        idade_horas = max(
            (datetime.now().timestamp() - backups_pre_live[0].stat().st_mtime)
            / 3600,
            0.0,
        )
        backup_pre_live.update({
            "idade_horas": round(idade_horas, 3),
            "fresco": idade_horas <= 24,
        })
    else:
        backup_pre_live = {
            "saudavel": False, "fresco": False,
            "arquivo": None, "idade_horas": None,
            "motivo": "backup_pre_live_ausente",
        }
    pre_live["backup"] = backup_pre_live
    processos = {
        "monitor_ativo": bool(
            pid_ativo(monitor.get("pid"))
            and trava_em_uso(pasta / "monitor_instancia.lock")
        ),
        "watchdog_ativo": bool(
            pid_ativo(watchdog.get("pid"))
            and trava_em_uso(pasta / "watchdog_instancia.lock")
        ),
        "monitor_codigo": estado_codigo_runtime(pasta, monitor),
        "watchdog_codigo": estado_codigo_runtime(
            pasta, watchdog, ARQUIVOS_RUNTIME_WATCHDOG
        ),
    }
    uri = caminho_banco.as_uri() + "?mode=ro"
    conexao = sqlite3.connect(uri, uri=True, timeout=10)
    conexao.row_factory = sqlite3.Row
    try:
        limites_risco = obter_limites_risco()
        dataset_temporal = resumir_cobertura_dataset_temporal(
            conexao,
            MERCADOS_CALIBRADOS,
            VERSAO_REGRAS,
            regras_por_mercado={
                mercado: versao_regra_para_mercado(mercado)
                for mercado in MERCADOS_CALIBRADOS
            },
        )
        auditoria_indicadores_lista_temporais = (
            resumir_auditoria_temporal_sqlite(conexao)
        )
        avaliacoes_cortes = {}
        regras_cortes = {}
        aptos_cortes = []
        for mercado in MERCADOS_CALIBRADOS:
            regra_corte = versao_regra_para_mercado(mercado)
            parcial = resumir_cortes_sombra(
                conexao,
                [mercado],
                regra_corte,
            )
            regras_cortes[mercado] = regra_corte
            avaliacoes_parciais = parcial.get("avaliacoes") or {}
            avaliacoes_cortes.update(avaliacoes_parciais)
            if (avaliacoes_parciais.get(mercado) or {}).get(
                "apto_para_alterar_regra"
            ) is True:
                aptos_cortes.append(mercado)
        cortes_sombra = {
            "versao": "cortes-sombra-v1",
            "regras_por_mercado": regras_cortes,
            "aplicacao_automatica": False,
            "mercados_aptos_para_revisao": aptos_cortes,
            "avaliacoes": avaliacoes_cortes,
        }
        diagnostico_pre_calibracao = {
            mercado: calcular_metricas(
                carregar_amostra_independente(
                    conexao,
                    mercado,
                    versao_regra_para_mercado(mercado),
                    limites_risco,
                )
            )
            for mercado in MERCADOS_CALIBRADOS
        }
        odds_periodos = diagnosticar_fontes_odds_periodos(
            resumir_odds_escanteios_periodos(conexao),
            validacao_runtime.get("catalogo_odds_live") or {},
            validacao_runtime.get("estado_odds_api") or {},
        )
        pendencias_resultados = resumir_pendencias_resultados(conexao)
        historico_drift = auditar_historico_drift_simulacoes(
            conexao,
            validacao.get("drift_simulacoes") or {},
            VERSAO_REGRAS,
        )
        experimento_filtro = validacao.get("experimento_filtro") or {}
        comparacao_filtro = comparar_filtro_simulacoes(
            conexao,
            VERSAO_REGRAS,
            iniciado_em=experimento_filtro.get("iniciado_em"),
            regra_fingerprint=fingerprint_vinculado_no_banco(
                conexao, VERSAO_REGRAS
            ),
        )
        validacao_ht_00_min20 = _com_exposicao_coorte(
            resumir_validacao_gol_ht_00_min20(conexao),
            telemetria=telemetria_exposicao,
            modo_manutencao=modo_manutencao,
            agora=agora_evidencias,
        )
        validacao_gols_antecipados_resumo = (
            resumir_validacao_gols_antecipados(conexao)
        )
        registrado_antecipados = (
            validacao_gols_antecipados_resumo.get("registrado_em")
        )
        por_braco_antecipados = (
            validacao_gols_antecipados_resumo.get("por_braco") or {}
        )
        for versao, resumo_braco in tuple(por_braco_antecipados.items()):
            por_braco_antecipados[versao] = _com_exposicao_coorte(
                {**dict(resumo_braco or {}),
                 "registrado_em": registrado_antecipados},
                telemetria=telemetria_exposicao,
                modo_manutencao=modo_manutencao,
                agora=agora_evidencias,
            )
        validacao_filtro_gol_ht_preciso = _com_exposicao_coorte(
            resumir_validacao_filtro_gol_ht_preciso(conexao),
            telemetria=telemetria_exposicao,
            modo_manutencao=modo_manutencao,
            agora=agora_evidencias,
        )
        validacao_filtro_gol_ft_preciso = _com_exposicao_coorte(
            resumir_validacao_filtro_gol_ft_preciso(conexao),
            telemetria=telemetria_exposicao,
            modo_manutencao=modo_manutencao,
            agora=agora_evidencias,
        )
        validacao_quase_gol_ft = resumir_validacao_quase_gol_ft(conexao)
        registrado_quase_gol_ft = validacao_quase_gol_ft.get(
            "registrado_em"
        )
        for braco, resumo_braco in tuple(
            (validacao_quase_gol_ft.get("bracos") or {}).items()
        ):
            validacao_quase_gol_ft["bracos"][braco] = (
                _com_exposicao_coorte(
                    {
                        **dict(resumo_braco or {}),
                        "registrado_em": registrado_quase_gol_ft,
                    },
                    telemetria=telemetria_exposicao,
                    modo_manutencao=modo_manutencao,
                    agora=agora_evidencias,
                )
            )
        validacao_top_criterios = resumir_top_criterios_gols(conexao)
        for periodo in ("ht", "ft"):
            if isinstance(validacao_top_criterios.get(periodo), dict):
                validacao_top_criterios[periodo] = _com_exposicao_coorte(
                    validacao_top_criterios[periodo],
                    telemetria=telemetria_exposicao,
                    modo_manutencao=modo_manutencao,
                    agora=agora_evidencias,
                )
        try:
            portfolio_edge = avaliar_portfolio_edge(
                conexao,
                recursos=recursos_configurados,
                controle_v2b_ft=controle_v2b_ft,
                controle_gols_antecipados=controle_gols_antecipados,
                controle_filtro_gol_ht_preciso=(
                    controle_filtro_gol_ht_preciso
                ),
                controle_filtro_gol_ft_preciso=(
                    controle_filtro_gol_ft_preciso
                ),
                controle_escanteios_ft_asiatico=(
                    controle_escanteios_ft_asiatico
                ),
            )
        except (sqlite3.Error, TypeError, ValueError) as erro:
            portfolio_edge = {
                "versao": "avaliacao-portfolio-edge-read-only-v9",
                "todos_mercados_com_edge_comprovado": False,
                "mercados_favoraveis_para_revisao_manual": [],
                "avaliacoes": {},
                "erro": type(erro).__name__,
                "promocao_automatica": False,
            }
        fontes_exposicao_metodos = {
            VERSAO_GOL_HT_ANTECIPADO: (
                por_braco_antecipados.get(VERSAO_GOL_HT_ANTECIPADO) or {}
            ),
            VERSAO_GOL_FT_ANTECIPADO: (
                por_braco_antecipados.get(VERSAO_GOL_FT_ANTECIPADO) or {}
            ),
            VERSAO_GOL_FT_ANTECIPADO_2T: (
                por_braco_antecipados.get(VERSAO_GOL_FT_ANTECIPADO_2T) or {}
            ),
            VERSAO_GOL_HT_00_MIN20: validacao_ht_00_min20,
            VERSAO_TOP_CRITERIO_HT: validacao_top_criterios.get("ht") or {},
            VERSAO_TOP_CRITERIO_FT: validacao_top_criterios.get("ft") or {},
        }
        fontes_exposicao_identificador = {
            "ht_antecipado_preciso": validacao_filtro_gol_ht_preciso,
            "ft_antecipado_2t_preciso": validacao_filtro_gol_ft_preciso,
        }
        for avaliacao_gol in (
            (portfolio_edge.get("avaliacoes") or {}).get("gol_ht") or {},
            (portfolio_edge.get("avaliacoes") or {}).get("gol_ft") or {},
        ):
            for metodo in avaliacao_gol.get("metodos_ativos") or ():
                fonte = fontes_exposicao_identificador.get(
                    metodo.get("identificador")
                ) or fontes_exposicao_metodos.get(
                    metodo.get("versao_metodo")
                )
                if not fonte:
                    continue
                validador = dict(
                    metodo.get("validador_prospectivo") or {}
                )
                for chave in (
                    "registrado_em",
                    "tamanho_coorte",
                    "exposicao_coorte_prontidao",
                ):
                    if fonte.get(chave) is not None:
                        validador[chave] = fonte[chave]
                metodo["validador_prospectivo"] = validador
        avaliacao_asiatica = (
            (portfolio_edge.get("avaliacoes") or {}).get(
                "escanteios_ft_asiatico"
            ) or {}
        )
        metricas_asiaticas = avaliacao_asiatica.get("metricas_oficiais")
        if isinstance(metricas_asiaticas, dict):
            avaliacao_asiatica["metricas_oficiais"] = (
                _com_exposicao_coorte(
                    metricas_asiaticas,
                    telemetria=telemetria_exposicao,
                    modo_manutencao=modo_manutencao,
                    agora=agora_evidencias,
                )
            )
        try:
            clv_live = avaliar_clv_live(conexao)
            clv_live.pop("itens", None)
        except (sqlite3.Error, TypeError, ValueError) as erro:
            clv_live = {
                "versao": VERSAO_AVALIACAO_CLV_LIVE,
                "comparaveis": 0,
                "erro": type(erro).__name__,
                "altera_sinais": False,
                "gate_operacional": False,
                "promocao_automatica": False,
            }
        provas = conexao.execute(
            """
            SELECT
              SUM(CASE WHEN e.canal LIKE '%:teste'
                        AND e.canal NOT LIKE '%:teste:resultado'
                       THEN 1 ELSE 0 END) AS teste,
              SUM(CASE WHEN e.canal NOT LIKE '%:%'
                       THEN 1 ELSE 0 END) AS oficial,
              SUM(CASE WHEN e.canal LIKE '%:teste'
                        AND e.canal NOT LIKE '%:teste:resultado'
                        AND s.status='aprovado'
                       THEN 1 ELSE 0 END) AS aprovadas_em_teste,
              SUM(CASE WHEN e.canal LIKE '%:teste'
                        AND e.canal NOT LIKE '%:teste:resultado'
                        AND s.status='simulacao'
                       THEN 1 ELSE 0 END) AS simuladas_em_teste
            FROM entregas_alertas e
            JOIN sinais s ON s.id=e.sinal_id
            WHERE e.status='entregue' AND e.provedor='telegram'
              AND e.provedor_mensagem_id IS NOT NULL
            """
        ).fetchone()
        try:
            fluxo_amostras = resumir_fluxo_amostras_ativas(
                conexao,
                mercados_calibrados_operacionais(),
                bracos=bracos_fluxo,
            )
            fluxo_amostras["partidas_ultimo_ciclo"] = coleta.get(
                "partidas_ultimo_ciclo"
            )
        except (sqlite3.Error, TypeError, ValueError) as erro:
            fluxo_amostras = {
                "saudavel": False,
                "motivo": "consulta_fluxo_falhou",
                "erro": type(erro).__name__,
                "mercados": {},
                "bracos": {},
            }
    finally:
        conexao.close()
    sobreajuste_gol_ft = auditar_sobreajuste(caminho_banco)
    recursos = configuracao.get("recursos") or {}
    v2b_ft_habilitado_ambiente = bool(
        recursos.get("gol_ft_capacidade_contextual_v2_grupo")
    )
    progresso_v2 = validacao.get("progresso_gols_capacidade_v2") or {}
    contextual_ht = (
        (progresso_v2.get("por_braco_segmento") or {}).get(
            f"{VERSAO_GOL_HT_CAPACIDADE_CONTEXTUAL_V2}|profissional"
        )
        or {}
    )

    def normalizar_metodo_ht(
        identificador, versao, ativo, item, controle_operacional=None
    ):
        item = dict(item or {})
        controle_operacional = dict(controle_operacional or {})
        candidatos = int(
            item.get(
                "candidatos_coorte",
                item.get("candidatos", item.get("total", 0)),
            )
            or 0
        )
        faltam = item.get("faltam")
        if faltam is None:
            faltam = max(100 - candidatos, 0)
        return {
            "identificador": identificador,
            "versao": versao,
            "ativo": bool(ativo),
            "candidatos": candidatos,
            "tamanho_coorte": int(
                item.get("tamanho_coorte", candidatos + int(faltam or 0))
                or 0
            ),
            "validos": int(item.get("validos", 0) or 0),
            "greens": int(item.get("greens", 0) or 0),
            "reds": int(item.get("reds", 0) or 0),
            "pendentes": int(item.get("pendentes", 0) or 0),
            "roi": item.get("roi"),
            "intervalo_roi_95": item.get("intervalo_roi_95"),
            "faltam": int(faltam or 0),
            "decisao_estatistica": item.get(
                "decisao_estatistica", item.get("decisao")
            ),
            "linhagem_homogenea": item.get("linhagem_homogenea"),
            "registrado_em": item.get("registrado_em"),
            "exposicao_coorte_prontidao": item.get(
                "exposicao_coorte_prontidao"
            ),
            "funil_candidatos": item.get("funil_candidatos"),
            "funil_gerador": item.get("funil_gerador"),
            "controle_operacional": controle_operacional,
        }

    portfolio_ht = {
        "versao": "portfolio-ht-prospectivo-v1",
        "metodos": [
            normalizar_metodo_ht(
                "ht_00_min20",
                VERSAO_GOL_HT_00_MIN20,
                recursos.get("gol_ht_00_min20_grupo"),
                validacao_ht_00_min20,
            ),
            normalizar_metodo_ht(
                "ht_antecipado_preciso",
                VERSAO_FILTRO_GOL_HT_PRECISO,
                bool(
                    recursos.get("gols_antecipados_grupo")
                    and recursos.get(
                        "filtro_gol_ht_antecipado_preciso"
                    )
                    and controle_gols_antecipados.get("saudavel")
                    and controle_filtro_gol_ht_preciso.get("saudavel")
                    and controle_filtro_gol_ht_preciso.get("ativo")
                    and (
                        (controle_gols_antecipados.get("metodos") or {})
                        .get(VERSAO_GOL_HT_ANTECIPADO, {})
                        .get("ativo", True)
                    )
                ),
                validacao_filtro_gol_ht_preciso,
                controle_filtro_gol_ht_preciso,
            ),
            normalizar_metodo_ht(
                "ht_capacidade_contextual_v2b",
                VERSAO_GOL_HT_CAPACIDADE_CONTEXTUAL_V2,
                recursos.get("gol_ht_capacidade_contextual_v2_grupo"),
                contextual_ht,
            ),
            normalizar_metodo_ht(
                "ht_top_casa_fora_10",
                VERSAO_TOP_CRITERIO_HT,
                recursos.get("top_criterios_gols_grupo"),
                validacao_top_criterios.get("ht") or {},
            ),
        ],
        "capacidade_v1_legada_no_grupo": bool(
            recursos.get("gol_ht_capacidade_v1_grupo")
        ),
        "ht_antecipado_legado": {
            "versao": VERSAO_GOL_HT_ANTECIPADO,
            "uso": "diagnostico_historico_nao_prova_filtro_preciso",
            "validacao": (
                (validacao_gols_antecipados_resumo.get("por_braco") or {})
                .get(VERSAO_GOL_HT_ANTECIPADO)
                or {}
            ),
            "controle": (
                (controle_gols_antecipados.get("metodos") or {}).get(
                    VERSAO_GOL_HT_ANTECIPADO
                )
                or {}
            ),
        },
        "promocao_automatica": False,
    }
    portfolio_ft = dict(
        (portfolio_edge.get("avaliacoes") or {}).get("gol_ft") or {}
    )
    if portfolio_ft:
        portfolio_ft.setdefault(
            "versao_filtro_2t", VERSAO_FILTRO_GOL_FT_PRECISO
        )
        portfolio_ft.setdefault(
            "validacao_filtro_2t", validacao_filtro_gol_ft_preciso
        )
        portfolio_ft.setdefault(
            "controle_filtro_2t", controle_filtro_gol_ft_preciso
        )
        portfolio_ft.setdefault(
            "quase_candidatos_precisos", validacao_quase_gol_ft
        )
    return {
        "agora": agora_evidencias.isoformat(),
        "modo_manutencao": modo_manutencao,
        "avaliacoes_periodicas": avaliacoes_periodicas,
        "acesso_packball": ler_estado(
            pasta / "packball_acesso_estado.json"
        ),
        "mercados_exigidos": mercados_calibrados_operacionais(),
        "configuracao": configuracao,
        "worker_treino_isolado": worker_treino_isolado,
        "metodos_grupo": {
            "v2b_ft_ativo": bool(
                v2b_ft_habilitado_ambiente
                and controle_v2b_ft.get("saudavel")
                and controle_v2b_ft.get("ativo")
            ),
            "v2b_ft_habilitado_ambiente": v2b_ft_habilitado_ambiente,
            "controle_v2b_ft": controle_v2b_ft,
            "controle_gols_antecipados": controle_gols_antecipados,
            "controle_filtro_gol_ht_preciso": (
                controle_filtro_gol_ht_preciso
            ),
            "controle_filtro_gol_ft_preciso": (
                controle_filtro_gol_ft_preciso
            ),
            "controle_escanteios_ft_asiatico": (
                controle_escanteios_ft_asiatico
            ),
            "proximo_gol_balanceado_ativo": bool(
                recursos_configurados.get(
                    "proximo_gol_balanceado_grupo_teste"
                )
                and controle_proximo_gol_balanceado.get("saudavel")
                and controle_proximo_gol_balanceado.get("ativo")
            ),
            "proximo_gol_balanceado_sombra_ativo": bool(
                recursos_configurados.get("proximo_gol_balanceado_sombra")
            ),
            "controle_proximo_gol_balanceado": (
                controle_proximo_gol_balanceado
            ),
        },
        "portfolio_ft": portfolio_ft,
        "validacao_quase_candidatos_gol_ft": validacao_quase_gol_ft,
        "portfolio_ht": portfolio_ht,
        "portfolio_edge": portfolio_edge,
        "clv_live": clv_live,
        "fluxo_amostras_ativas": fluxo_amostras,
        "validacao": validacao,
        "coleta": coleta,
        "backup": backup,
        "backup_espelho": backup_espelho,
        "processos": processos,
        "supervisao_watchdog": {
            **espelho_watchdog,
            "inicializando": bool(
                espelho_watchdog["estado"] == "anterior_ao_processo"
                and processos["watchdog_ativo"]
            ),
        },
        "autostart": consultar_autostart(pasta=pasta),
        "dataset_temporal": dataset_temporal,
        "auditoria_indicadores_lista_temporais": (
            auditoria_indicadores_lista_temporais
        ),
        "cortes_sombra": cortes_sombra,
        "diagnostico_pre_calibracao": diagnostico_pre_calibracao,
        "sobreajuste_gol_ft": sobreajuste_gol_ft,
        "odds_periodos": odds_periodos,
        "historico_drift": historico_drift,
        "historico_drift_watchdog": (
            validacao_runtime.get("historico_drift_simulacoes") or {}
        ),
        "comparacao_filtro": comparacao_filtro,
        "persistencia_estado_watchdog": (
            estado_watchdog.get("persistencia_estado_watchdog") or {}
        ),
        "integridade_banco_ativo": (
            estado_watchdog.get("integridade_banco_ativo") or {}
        ),
        "pre_live": pre_live,
        "pendencias_resultados": pendencias_resultados,
        "telegram": {
            "provas_teste": int(provas["teste"] or 0),
            "provas_oficiais": int(provas["oficial"] or 0),
            "provas_aprovadas_em_teste": int(
                provas["aprovadas_em_teste"] or 0
            ),
            "provas_simuladas_em_teste": int(
                provas["simuladas_em_teste"] or 0
            ),
        },
        "pareamento_api": verificar_pareamento_api(caminho_log),
        "cache_api_operacional": verificar_cache_api_operacional(caminho_log),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audita a prontidão profissional real do Bot PackBall"
    )
    parser.add_argument(
        "--exigir-completo", action="store_true",
        help="Retorna código 1 enquanto algum requisito estiver pendente.",
    )
    parser.add_argument(
        "--resumo", action="store_true",
        help="Exibe somente estado, pendências e progresso dos mercados.",
    )
    argumentos = parser.parse_args()
    pasta = Path(__file__).parent
    resultado = avaliar_prontidao(coletar_evidencias(pasta))
    saida = resumir_resultado_prontidao(resultado) if argumentos.resumo else resultado
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    if argumentos.exigir_completo and not resultado["pronto_profissional_completo"]:
        raise SystemExit(1)
    if resultado["estado_geral"] == "operacao_degradada":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
