import hashlib
import json
import math
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from api_football import (
    auditar_cache_api_football,
    verificar_catalogo_odds_live,
    verificar_contador_uso,
    verificar_estado_odds_api,
)
from auditoria_regras_operacionais import auditar_regra_proximo_gol
from auditoria_ligas_sombra import auditar_ligas_por_mercado
from backup_banco import (
    BackupBanco,
    caminho_manifesto,
    verificar_arquivo_backup,
    verificar_backup_espelho,
)
from backup_compactado import executar_drill_restauracao_compactada
from avaliacao_contexto import (
    auditar_historico_avaliacao_contexto,
    avaliar_contexto_avancado,
    registrar_historico_avaliacao_contexto,
    registrar_ou_obter_ancoras_contexto,
)
from avaliacao_acompanhamento_odd import (
    VERSAO as VERSAO_AVALIACAO_ACOMPANHAMENTO_ODD,
)
from avaliacao_desajuste_odds import (
    BOOKMAKER_EXECUTAVEL as BOOKMAKER_DESAJUSTE_ODDS,
    MOTIVO_FALHA_EXECUCAO as MOTIVO_FALHA_EXECUCAO_DESAJUSTE,
    ORIGENS_FONTES_OBSERVACIONAIS,
    VERSAO as VERSAO_AVALIACAO_DESAJUSTE_ODDS,
    VERSAO_CONVERGENCIA_PRECO,
    VERSAO_EDGE_SEM_VIG,
    VERSAO_FONTES_OBSERVACIONAIS,
    VERSAO_LIQUIDACAO_EDGE_SEM_VIG,
    MERCADOS_LIQUIDAVEIS_EDGE_SEM_VIG,
    TAMANHO_COORTE_EDGE_SEM_VIG,
    RESULTADOS_EDGE_SEM_VIG_MINIMOS,
    RESULTADOS_EDGE_SEM_VIG_DEV_MINIMOS,
    RESULTADOS_EDGE_SEM_VIG_HOLDOUT_MINIMOS,
    DESENVOLVIMENTO_REFERENCIA_POS_ENVIO,
    HOLDOUT_REFERENCIA_POS_ENVIO,
    MERCADOS_REFERENCIA_POS_ENVIO,
    RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS,
    RESULTADOS_REFERENCIA_POS_ENVIO_DEV_MINIMOS,
    RESULTADOS_REFERENCIA_POS_ENVIO_HOLDOUT_MINIMOS,
    RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS,
    TAMANHO_COORTE_REFERENCIA_POS_ENVIO,
    VERSAO_REFERENCIA_POS_ENVIO,
)
from desajuste_odds import VERSAO as VERSAO_COMPARACAO_ODDS
from avaliacao_quarentena_fallback_ht import (
    REGRA_VERSAO_ALVO as REGRA_VERSAO_QUARENTENA_FALLBACK_HT,
    STATUS_COORTE as STATUS_COORTE_QUARENTENA_FALLBACK_HT,
    VERSAO as VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT,
)
from avaliacao_prioridade_ligas_gols import (
    VERSAO as VERSAO_AVALIACAO_PRIORIDADE_LIGAS_GOLS,
)
from avaliacao_probabilidade_individual import (
    ERRO_CALIBRACAO_MAXIMO as ERRO_CALIBRACAO_PROBABILIDADE_INDIVIDUAL,
    RESULTADOS_DESENVOLVIMENTO_MINIMOS as RESULTADOS_DEV_PROBABILIDADE_INDIVIDUAL,
    RESULTADOS_HOLDOUT_MINIMOS as RESULTADOS_HOLDOUT_PROBABILIDADE_INDIVIDUAL,
    RESULTADOS_MINIMOS as RESULTADOS_PROBABILIDADE_INDIVIDUAL,
    TAMANHO_COORTE as TAMANHO_COORTE_PROBABILIDADE_INDIVIDUAL,
    VERSAO as VERSAO_AVALIACAO_PROBABILIDADE_INDIVIDUAL,
    VERSAO_MODELO as VERSAO_MODELO_PROBABILIDADE_INDIVIDUAL,
)
from banco import (
    auditar_historico_drift_simulacoes,
    registrar_historico_drift_simulacoes,
    resumir_risco_alertas_oficiais_conexao,
)
from calibracao import (
    POLITICA_CALIBRACAO_VERSAO,
    modelo_compativel_com_politica,
)
from carteira_operacional import auditar_carteira_operacional
from clv_pos_alerta import (
    MERCADOS_CLV_API_RAPIDA,
    MERCADOS_CLV_SOMENTE_SNAPSHOT,
    VERSAO_COLETA_CLV_API_RAPIDA,
)
from configuracao import obter_limites_api, obter_limites_risco
from controle_acesso_packball import (
    auditar_ritmo_packball,
    avaliar_experimento_ritmo_packball,
    verificar_acesso_packball,
)
from controle_sistema import ler_modo_manutencao, solicitar_modo_manutencao
from custodia_avaliacao import (
    EFEITOS_DESATIVADOS as EFEITOS_DESATIVADOS_AVALIACAO,
    ESTADO_CONCLUIDO as ESTADO_AVALIACAO_CONCLUIDO,
    LIMITE_EXECUCAO_SEGUNDOS as LIMITE_EXECUCAO_AVALIACAO_SEGUNDOS,
    VERSAO_CUSTODIA as VERSAO_CUSTODIA_AVALIACAO,
    aplicar_efeitos_desativados,
    auditar_cronologia_execucao,
    auditar_efeitos_desativados,
    classificar_execucao,
)
from controle_gols_antecipados import (
    ler_estado as ler_estado_gols_antecipados,
    metodo_liberado as metodo_gol_antecipado_liberado,
    suspender_metodo as suspender_metodo_gol_antecipado,
)
from controle_filtro_gol_ht_preciso import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_FILTRO_GOL_HT_PRECISO,
    aplicar_validacao as aplicar_controle_filtro_gol_ht_preciso,
    ler_estado as ler_estado_filtro_gol_ht_preciso,
)
from controle_filtro_gol_ft_preciso import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_FILTRO_GOL_FT_PRECISO,
    aplicar_validacao as aplicar_controle_filtro_gol_ft_preciso,
    ler_estado as ler_estado_filtro_gol_ft_preciso,
)
from controle_escanteios_ft_asiatico import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_ESCANTEIOS_FT_ASIATICO,
    aplicar_validacao as aplicar_controle_escanteios_ft_asiatico,
    ler_estado as ler_estado_escanteios_ft_asiatico,
)
from controle_proximo_gol_balanceado import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_PROXIMO_GOL_BALANCEADO,
    ler_estado as ler_estado_proximo_gol_balanceado,
    suspender as suspender_proximo_gol_balanceado,
)
from controle_pre_live_preciso import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_PRE_LIVE_PRECISO,
    aplicar_validacao as aplicar_controle_pre_live_preciso,
    ler_estado as ler_estado_pre_live_preciso,
)
from controle_v2b_ft import ler_estado_v2b_ft, suspender_v2b_ft
from dataset_temporal import resumir_cortes_sombra
from diagnostico_sinais_recentes import (
    comparar_fluxos_consecutivos,
    comparar_fluxos_mesmo_horario,
    diagnosticar_funil,
    resumir_fluxo_sinais,
)
from hipoteses_sombra import (
    VERSAO_AVALIACAO_HIPOTESES_SOMBRA,
    avaliar_hipoteses_sombra_ativas,
)
from historico_api_live import resumir_historico_api_live
from supervisao_melhor_preco_sombra import (
    verificar_integridade_melhor_preco_sombra,
)
from supervisao_referencia_api_football import (
    verificar_referencia_api_football_sombra,
)
from exploracao_sombra import (
    auditar_definicao_exploracao_gols,
    resumir_exploracoes_sombra,
)
from gols_capacidade_contextual_v2 import (
    VERSAO_GOL_FT as VERSAO_GOL_FT_CAPACIDADE_V2,
)
from validacao_gols_antecipados import (
    auditar_validacao_gols_antecipados,
    resumir_validacao_gols_antecipados,
)
from validacao_gols_capacidade_times import (
    auditar_validacao_gols_capacidade_times,
    resumir_validacao_gols_capacidade_times,
)
from validacao_gols_capacidade_contextual_v2 import (
    auditar_grupo_ft_capacidade_contextual_v2,
    auditar_validacao_gols_capacidade_contextual_v2,
    resumir_grupo_ft_capacidade_contextual_v2,
    resumir_validacao_gols_capacidade_contextual_v2,
)
from validacao_gol_ht_00_min20 import (
    VERSAO_VALIDACAO as VERSAO_VALIDACAO_GOL_HT_00_MIN20,
    resumir_validacao_gol_ht_00_min20,
)
from validacao_gol_ht_antecipado_preciso import (
    VERSAO_VALIDACAO as VERSAO_VALIDACAO_FILTRO_GOL_HT_PRECISO,
    resumir_validacao as resumir_validacao_filtro_gol_ht_preciso,
)
from validacao_gol_ft_antecipado_preciso import (
    VERSAO_VALIDACAO as VERSAO_VALIDACAO_FILTRO_GOL_FT_PRECISO,
    resumir_validacao as resumir_validacao_filtro_gol_ft_preciso,
)
from validacao_quase_candidatos_gol_ft import (
    VERSAO_VALIDACAO as VERSAO_VALIDACAO_QUASE_GOL_FT,
    resumir_validacao as resumir_validacao_quase_gol_ft,
)
from validacao_escanteios_ft_asiatico_executavel import (
    VERSAO_VALIDACAO as VERSAO_VALIDACAO_ESCANTEIOS_FT_ASIATICO,
    resumir_validacao as resumir_validacao_escanteios_ft_asiatico,
)
from validacao_escanteios_ft_asiatico_prospectiva import (
    resumir_validacao as resumir_validacao_escanteios_ft_asiatico_legada,
)
from validacao_gol_ft_reforcado_sombra import (
    auditar_validacao_gol_ft_reforcado,
    resumir_validacao_gol_ft_reforcado,
)
from validacao_gol_ht_protegido_sombra import (
    auditar_validacao_gol_ht_protegido,
    resumir_validacao_gol_ht_protegido,
)
from validacao_proximo_gol_balanceado_sombra import (
    resumir_validacao_proximo_gol_balanceado,
)
from validacao_quase_candidatos_proximo_gol import (
    resumir_validacao as resumir_validacao_quase_proximo_gol,
)
from integridade_resultados import auditar_proveniencia_resultados
from valor_mercado import auditar_valor_mercado_sinais
from integridade_calibracao import (
    auditar_diversidade_amostra_calibracao,
    auditar_frescor_calibracoes,
    auditar_frescor_calibracoes_por_mercado,
    auditar_particoes_calibracao,
    auditar_particoes_calibracao_por_mercado,
)
from mercados import (
    MERCADOS_CALIBRADOS,
    ROTULOS_MERCADOS,
    mercados_calibrados_operacionais,
)
from linhagem_regras import (
    auditar_linhagem_regra,
    fingerprint_vinculado_no_banco,
    resumir_cobertura_linhagem_sinais,
)
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from versoes_gol_ft_reforcado import (
    versao_regra_operacional as versao_regra_para_mercado,
    versoes_regras_operacionais,
)
from observabilidade import percentil_valores, resumir_erro_seguro
from packball_login import diagnosticar_storage_state
from processo_monitor import (
    TravaInstancia,
    garantir_pre_live_ativo,
    gravar_json_atomico,
    hash_codigo_watchdog,
    iniciar_monitor,
    ler_estado,
    pid_ativo,
    registrar_estado,
    trava_em_uso,
)
from progresso_calibracao import resumir_progresso_calibracao
from probabilidade_por_acertos import auditar_estimativas_persistidas
from pontuacao_sombra import (
    avaliar_pontuacao_sombra,
    registrar_modelos_pontuacao_sombra,
)
from pontuacao_contexto_sombra import (
    avaliar_pontuacao_contexto_sombra,
    registrar_modelos_pontuacao_contexto_sombra,
)
from pontuacao_longa_sombra import (
    avaliar_pontuacao_longa_sombra,
    registrar_estudos_pontuacao_longa,
)
from relatorio_odds_periodos import resumir_odds_escanteios_periodos
from relatorio_simulacoes import (
    auditar_experimento_filtro,
    avaliar_drift_simulacoes,
    avaliar_drift_simulacoes_por_mercado,
    comparar_filtros_por_mercado,
    comparar_filtro_simulacoes,
    obter_conclusao_experimento_filtro,
    registrar_ou_obter_conclusao_experimento_filtro,
)
from repositorio_pre_live import verificar_banco_pre_live
from validacao_pre_live_preciso import (
    resumir_validacao_pre_live_preciso_arquivo,
)
from watchdog_avaliacoes import (
    _bloqueio_custodia_avaliacao,
    _resposta_avaliacao_observacional,
    verificar_avaliacao_acompanhamento_odd,
    verificar_avaliacao_desajuste_odds,
    verificar_avaliacao_prioridade_ligas_gols,
    verificar_avaliacao_probabilidade_individual,
    verificar_avaliacao_quarentena_fallback_ht,
)


PASTA = Path(__file__).parent
ARQUIVO_LOG = PASTA / "monitor_eventos.jsonl"
ARQUIVO_ESTADO = PASTA / "watchdog_estado.json"
ARQUIVO_PROCESSO = PASTA / "monitor_processo.json"
ARQUIVO_PROCESSO_WATCHDOG = PASTA / "watchdog_processo.json"
ARQUIVO_BANCO = PASTA / "monitor_packball.db"
ARQUIVO_ACESSO_PACKBALL = PASTA / "packball_acesso_estado.json"
ARQUIVO_SESSAO_PACKBALL = PASTA / "packball_session.json"
ARQUIVO_AVALIACAO_RITMO = PASTA / "packball_experimento_ritmo.json"
ARQUIVO_RECUPERACAO_BANCO = PASTA / "recuperacao_banco_estado.json"
ARQUIVO_ESTADO_V2B_FT = PASTA / "v2b_ft_estado.json"
ARQUIVO_ESTADO_GOLS_ANTECIPADOS = (
    PASTA / "gols_antecipados_estado.json"
)
ARQUIVO_BANCO_PRE_LIVE = PASTA / "pre_live.db"
ARQUIVO_PROCESSO_PRE_LIVE = PASTA / "pre_live_processo.json"
ARQUIVO_ESTADO_PRE_LIVE = PASTA / "pre_live_estado.json"
ARQUIVO_ESTADO_ACOMPANHAMENTO_ODD = (
    PASTA / "monitor_odds_rapidas_estado.json"
)
ARQUIVO_AVALIACAO_ACOMPANHAMENTO_ODD = (
    PASTA / "avaliacao_acompanhamento_odd_estado.json"
)
ARQUIVO_AVALIACAO_PRIORIDADE_LIGAS_GOLS = (
    PASTA / "avaliacao_prioridade_ligas_gols_estado.json"
)
ARQUIVO_AVALIACAO_DESAJUSTE_ODDS = (
    PASTA / "avaliacao_desajuste_odds_estado.json"
)
ARQUIVO_AVALIACAO_PROBABILIDADE_INDIVIDUAL = (
    PASTA / "avaliacao_probabilidade_individual_estado.json"
)
ARQUIVO_AVALIACAO_QUARENTENA_FALLBACK_HT = (
    PASTA / "avaliacao_quarentena_fallback_ht_estado.json"
)
PASTA_BACKUPS = PASTA / "backups"
ARQUIVO_TRAVA = PASTA / "watchdog_instancia.lock"
ARQUIVO_REINICIO_ISOLADO = PASTA / "watchdog_reinicio.json"
POLITICA_TELEGRAM_VERSAO = "telegram-compacto-criticos-v1"
LIMITE_SEM_COLETA_SEGUNDOS = 300
INTERVALO_REINICIO_SEGUNDOS = 300
LIMITE_DISCO_LIVRE_MB = 512
LIMITE_WAL_MB = 512
JANELA_FUNIL_MINUTOS = 30
AMOSTRA_MINIMA_FUNIL = 10
COBERTURA_MINIMA_CANDIDATOS = 0.90
COBERTURA_MINIMA_ODDS = 0.20
AMOSTRA_MINIMA_FEATURES = 10
MERCADOS_VALIDACAO = MERCADOS_CALIBRADOS
MARCOS_VALIDACAO = (30, 100)
LIMIARES_COTA_API = (80, 95, 100)
AVISO_SESSAO_PACKBALL_HORAS = 48
HORA_RESUMO_DIARIO = 18
LIMITE_PARTE_RESUMO_DIARIO = 3900
VERSAO_ENTREGA_RESUMO_DIARIO = "resumo-diario-compacto-v2"
VERSAO_DETECCAO_ODDS_PERIODOS = "odds-periodos-v1"
CHAVE_ESTADO_WATCHDOG_SQLITE = "watchdog_estado_persistente:v1"
VERSAO_ESTADO_WATCHDOG_SQLITE = 1
TOLERANCIA_RECONCILIACAO_CALIBRACAO_SEGUNDOS = 300
CICLOS_CONFIRMAR_ALERTA_VALIDACAO = 3
CICLOS_CONFIRMAR_RECUPERACAO_VALIDACAO = 3
MINUTOS_CONFIRMAR_RECUPERACAO_VALIDACAO = 15
COOLDOWN_ALERTA_VALIDACAO_HORAS = 6
LIMITE_ASSINATURAS_RITMO_NOTIFICADAS = 32
INTERVALO_INTEGRIDADE_BANCO_MINUTOS = 10
MINIMO_SEM_DADO_ALERTA_24H = 3
TAXA_SEM_DADO_ALERTA_24H = 0.10
LIMITE_ABSOLUTO_SEM_DADO_ALERTA_24H = 10
_CACHE_VERIFICACAO_BACKUP = {}
MOTIVOS_VALIDACAO_CRITICOS = frozenset({
    "auditoria_validacao_falhou",
    "backup_diario_ausente",
    "backup_diario_invalido",
    "cache_api_football_inconsistente",
    "calibracao_ativa_desatualizada",
    "calibracao_inativa_desatualizada",
    "calibracao_ativa_incompativel",
    "contador_api_inseguro",
    "controle_v2b_ft_inconsistente",
    "crescimento_armazenamento_critico",
    "espaco_disco_baixo",
    "experimento_filtro_inconsistente",
    "experimento_ritmo_packball_regressao",
    "features_temporais_invalidas",
    "fontes_sinais_indisponiveis",
    "integridade_telegram_inconsistente",
    "linhagem_regra_inconsistente",
    "notificacoes_operacionais_inconsistentes",
    "proveniencia_resultados_inconsistente",
    "prioridade_scanner_indisponivel",
    "ritmo_packball_inseguro",
    "sinais_sem_linhagem_valida",
    "wal_excessivo",
})
MOTIVOS_VALIDACAO_OSCILANTES = frozenset({
    "capacidade_coleta_saturada",
    "cobertura_api_caiu_versus_base",
    "cobertura_odds_estruturadas_baixa",
    "experimento_ritmo_packball_regressao",
})


def verificar_integridade_banco_ativo(
    caminho,
    anterior=None,
    agora=None,
    intervalo_minutos=INTERVALO_INTEGRIDADE_BANCO_MINUTOS,
):
    """Detecta dano físico sem confundir indisponibilidade transitória."""
    caminho = Path(caminho)
    anterior = dict(anterior or {})
    agora = (agora or datetime.now()).replace(microsecond=0)
    if anterior.get("estado") == "integro":
        try:
            proxima = datetime.fromisoformat(
                anterior.get("proxima_verificacao_em")
            )
        except (TypeError, ValueError):
            proxima = None
        limite_futuro = agora + timedelta(
            minutes=max(int(intervalo_minutos), 1)
        )
        if (
            proxima is not None
            and agora < proxima <= limite_futuro
        ):
            return {
                **anterior,
                "executada": False,
                "cache_reutilizado": True,
            }
    proxima = agora + timedelta(minutes=max(int(intervalo_minutos), 1))
    base = {
        "verificado_em": agora.isoformat(),
        "proxima_verificacao_em": proxima.isoformat(),
        "executada": True,
        "cache_reutilizado": False,
    }
    try:
        caminho.stat()
    except FileNotFoundError:
        return {
            **base,
            "saudavel": False,
            "estado": "banco_ausente",
            "motivo": "banco_ativo_ausente",
            "recuperacao_necessaria": True,
            "corrupcao_comprovada": False,
            "quick_check": [],
        }
    except OSError as erro:
        return {
            **base,
            "saudavel": False,
            "estado": "indisponivel_temporario",
            "motivo": "integridade_banco_indisponivel",
            "recuperacao_necessaria": False,
            "corrupcao_comprovada": False,
            "erro": type(erro).__name__,
            "quick_check": [],
        }
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        mensagens = [
            str(item[0])
            for item in conexao.execute("PRAGMA quick_check")
        ]
    except (OSError, sqlite3.Error) as erro:
        mensagem = str(erro).lower()
        comprovada = any(
            trecho in mensagem
            for trecho in (
                "file is not a database",
                "database disk image is malformed",
                "database corrupt",
                "malformed database schema",
            )
        )
        return {
            **base,
            "saudavel": False,
            "estado": (
                "corrompido" if comprovada else "indisponivel_temporario"
            ),
            "motivo": (
                "banco_ativo_corrompido"
                if comprovada else "integridade_banco_indisponivel"
            ),
            "recuperacao_necessaria": comprovada,
            "corrupcao_comprovada": comprovada,
            "erro": type(erro).__name__,
            "quick_check": [],
        }
    finally:
        if conexao is not None:
            conexao.close()
    integro = mensagens == ["ok"]
    return {
        **base,
        "saudavel": integro,
        "estado": "integro" if integro else "corrompido",
        "motivo": None if integro else "banco_ativo_corrompido",
        "recuperacao_necessaria": not integro,
        "corrupcao_comprovada": not integro,
        "quick_check": mensagens[:10],
    }


def acionar_recuperacao_banco_ativo(
    caminho_banco,
    pasta,
    anterior=None,
    agora=None,
    enviar=None,
    solicitar=None,
    intervalo_minutos=INTERVALO_INTEGRIDADE_BANCO_MINUTOS,
):
    agora = (agora or datetime.now()).replace(microsecond=0)
    anterior = dict(anterior or {})
    auditoria = verificar_integridade_banco_ativo(
        caminho_banco,
        anterior=anterior,
        agora=agora,
        intervalo_minutos=intervalo_minutos,
    )
    if not auditoria.get("recuperacao_necessaria"):
        auditoria["alertado"] = bool(anterior.get("alertado", False))
        auditoria["manutencao_solicitada"] = False
        return auditoria
    assinatura = hashlib.sha256(json.dumps({
        "estado": auditoria.get("estado"),
        "motivo": auditoria.get("motivo"),
        "quick_check": auditoria.get("quick_check") or [],
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    evento_ja_tratado = bool(
        anterior.get("assinatura") == assinatura
        and anterior.get("manutencao_solicitada")
    )
    enviado = bool(anterior.get("alertado", False))
    erro_alerta = None
    if not evento_ja_tratado:
        enviar = enviar or enviar_alerta
        try:
            enviado = bool(enviar(
                "🚨 RECUPERAÇÃO AUTOMÁTICA DO BANCO SOLICITADA\n\n"
                "A integridade do SQLite falhou durante a operação.\n"
                f"Motivo técnico: {auditoria.get('motivo')}\n"
                "O monitor será encerrado com segurança. No próximo início, "
                "o backup válido mais recente será restaurado e a base anterior "
                "ficará preservada em quarentena."
            ))
        except Exception as erro:
            enviado = False
            erro_alerta = type(erro).__name__
    solicitar = solicitar or (
        lambda: solicitar_modo_manutencao(
            pasta, "recuperacao_banco_automatica", agora=agora
        )
    )
    manutencao_solicitada = bool(evento_ja_tratado)
    erro_manutencao = None
    if not evento_ja_tratado:
        try:
            solicitar()
            manutencao_solicitada = True
        except OSError as erro:
            erro_manutencao = type(erro).__name__
    return {
        **auditoria,
        "assinatura": assinatura,
        "alertado": enviado,
        "erro_alerta": erro_alerta,
        "manutencao_solicitada": manutencao_solicitada,
        "erro_manutencao": erro_manutencao,
    }


def verificar_backup_diario(
    pasta_backups, agora=None, tolerancia_minutos=10, cache=None
):
    agora = agora or datetime.now()
    pasta_backups = Path(pasta_backups)
    caminho = BackupBanco._existente_para_destino(
        pasta_backups / f"monitor_{agora:%Y%m%d}.db"
    )
    segundos_do_dia = agora.hour * 3600 + agora.minute * 60 + agora.second
    em_tolerancia = segundos_do_dia < int(tolerancia_minutos) * 60
    if not caminho.exists():
        return {
            "saudavel": em_tolerancia,
            "motivo": None if em_tolerancia else "backup_diario_ausente",
            "estado": "aguardando" if em_tolerancia else "ausente",
            "caminho": str(caminho),
        }
    cache = _CACHE_VERIFICACAO_BACKUP if cache is None else cache
    manifesto = caminho_manifesto(caminho)
    estado_arquivo = caminho.stat()
    estado_manifesto = manifesto.stat() if manifesto.exists() else None
    assinatura = (
        estado_arquivo.st_size,
        estado_arquivo.st_mtime_ns,
        estado_manifesto.st_size if estado_manifesto else None,
        estado_manifesto.st_mtime_ns if estado_manifesto else None,
    )
    chave_cache = str(caminho.resolve())
    anterior = cache.get(chave_cache)
    if anterior and anterior.get("assinatura") == assinatura:
        return dict(anterior["resultado"])
    verificacao = verificar_arquivo_backup(caminho)
    resultado = {
        "saudavel": bool(verificacao["valido"]),
        "motivo": (
            None if verificacao["valido"] else "backup_diario_invalido"
        ),
        "estado": "valido" if verificacao["valido"] else "invalido",
        "caminho": str(caminho),
        "detalhe": verificacao.get("motivo"),
    }
    cache[chave_cache] = {
        "assinatura": assinatura,
        "resultado": dict(resultado),
    }
    return resultado


def verificar_ponto_recuperacao(
    pasta_backups, agora=None, limite_horas=6,
    tolerancia_minutos=15, cache=None,
):
    agora = agora or datetime.now()
    pasta_backups = Path(pasta_backups)
    caminhos = set(BackupBanco._glob_formatos(
        pasta_backups, "monitor_????????.db"
    ))
    caminhos.update(BackupBanco._glob_formatos(
        pasta_backups, "periodico_*.db"
    ))
    caminhos.update(BackupBanco._glob_formatos(
        pasta_backups, "pre_reinicio_*.db"
    ))
    candidatos = []
    for caminho in caminhos:
        criado_em = None
        manifesto = caminho_manifesto(caminho)
        if manifesto.exists():
            try:
                dados = json.loads(manifesto.read_text(encoding="utf-8"))
                criado_em = datetime.fromisoformat(dados.get("criado_em"))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                criado_em = None
        if criado_em is None:
            try:
                criado_em = datetime.fromtimestamp(caminho.stat().st_mtime)
            except OSError:
                continue
        candidatos.append((criado_em, caminho))
    if not candidatos:
        return {
            "saudavel": False,
            "motivo": "ponto_recuperacao_ausente",
            "caminho": None,
            "idade_minutos": None,
            "limite_minutos": int(limite_horas * 60 + tolerancia_minutos),
        }
    criado_em, caminho = max(candidatos, key=lambda item: item[0])
    cache = _CACHE_VERIFICACAO_BACKUP if cache is None else cache
    manifesto = caminho_manifesto(caminho)
    estado_arquivo = caminho.stat()
    estado_manifesto = manifesto.stat() if manifesto.exists() else None
    assinatura = (
        estado_arquivo.st_size,
        estado_arquivo.st_mtime_ns,
        estado_manifesto.st_size if estado_manifesto else None,
        estado_manifesto.st_mtime_ns if estado_manifesto else None,
    )
    chave_cache = f"rpo:{caminho.resolve()}"
    anterior = cache.get(chave_cache)
    if anterior and anterior.get("assinatura") == assinatura:
        verificacao = anterior["verificacao"]
    else:
        verificacao = verificar_arquivo_backup(caminho)
        cache[chave_cache] = {
            "assinatura": assinatura,
            "verificacao": dict(verificacao),
        }
    idade_minutos = max(
        (agora - criado_em).total_seconds() / 60,
        0.0,
    )
    limite_minutos = int(limite_horas * 60 + tolerancia_minutos)
    valido = bool(verificacao["valido"])
    dentro_rpo = idade_minutos <= limite_minutos
    if not valido:
        motivo = "ponto_recuperacao_invalido"
    elif not dentro_rpo:
        motivo = "ponto_recuperacao_desatualizado"
    else:
        motivo = None
    return {
        "saudavel": motivo is None,
        "motivo": motivo,
        "caminho": str(caminho),
        "criado_em": criado_em.replace(microsecond=0).isoformat(),
        "idade_minutos": round(idade_minutos, 1),
        "limite_minutos": limite_minutos,
        "detalhe": verificacao.get("motivo"),
    }


def verificar_armazenamento(
    pasta, caminho_banco, limite_livre_mb=LIMITE_DISCO_LIVRE_MB,
    limite_wal_mb=LIMITE_WAL_MB, pasta_backups=None,
):
    pasta = Path(pasta)
    pasta_backups = Path(pasta_backups or (pasta / "backups"))
    caminho_wal = Path(f"{Path(caminho_banco)}-wal")
    try:
        livre_mb = shutil.disk_usage(pasta).free / (1024 * 1024)
        banco_mb = (
            Path(caminho_banco).stat().st_size / (1024 * 1024)
            if Path(caminho_banco).exists() else 0.0
        )
        wal_mb = (
            caminho_wal.stat().st_size / (1024 * 1024)
            if caminho_wal.exists() else 0.0
        )
        arquivos_backup = (
            [
                item for item in BackupBanco._glob_formatos(
                    pasta_backups, "*.db"
                ) if item.is_file()
            ]
            if pasta_backups.exists() else []
        )
        backups_mb = sum(
            item.stat().st_size for item in arquivos_backup
        ) / (1024 * 1024)
        compactados = [
            item for item in arquivos_backup
            if item.name.endswith(".db.gz")
        ]
        tamanho_logico_bytes = 0
        for item in arquivos_backup:
            if not item.name.endswith(".db.gz"):
                tamanho_logico_bytes += item.stat().st_size
                continue
            try:
                manifesto_compactado = json.loads(
                    caminho_manifesto(item).read_text(encoding="utf-8")
                )
                tamanho_logico_bytes += int(
                    manifesto_compactado.get("tamanho_sqlite_bytes")
                    or item.stat().st_size
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                tamanho_logico_bytes += item.stat().st_size
        retencao_backups = BackupBanco(pasta_backups).auditar_retencao()
    except OSError as erro:
        return {
            "saudavel": False,
            "motivos": ["armazenamento_indisponivel"],
            "erro": type(erro).__name__,
        }
    motivos = []
    if livre_mb < float(limite_livre_mb):
        motivos.append("espaco_disco_baixo")
    if wal_mb > float(limite_wal_mb):
        motivos.append("wal_excessivo")
    compactacao_ativa = (
        os.getenv("BACKUP_COMPACTACAO_ATIVA", "1") == "1"
    )
    if not compactacao_ativa:
        estado_compactacao = "desligada"
    elif compactados:
        estado_compactacao = "operando_com_backup_verificado"
    else:
        estado_compactacao = "aguardando_primeiro_backup_novo"
    return {
        "saudavel": not motivos,
        "motivos": motivos,
        "livre_mb": round(livre_mb, 1),
        "banco_mb": round(banco_mb, 1),
        "wal_mb": round(wal_mb, 1),
        "backups_mb": round(backups_mb, 1),
        "backups_arquivos": len(arquivos_backup),
        "backups_compactados": len(compactados),
        "backups_legados": len(arquivos_backup) - len(compactados),
        "backups_logicos_mb": round(
            tamanho_logico_bytes / (1024 * 1024), 1
        ),
        "economia_compactacao_mb": round(
            max(tamanho_logico_bytes / (1024 * 1024) - backups_mb, 0.0),
            1,
        ),
        "compactacao_ativa": compactacao_ativa,
        "estado_compactacao": estado_compactacao,
        "primeiro_backup_compacto_pendente": bool(
            compactacao_ativa and not compactados
        ),
        "rollback_compactacao": "BACKUP_COMPACTACAO_ATIVA=0",
        "retencao_backups": retencao_backups,
        "total_mb": round(banco_mb + wal_mb + backups_mb, 1),
        "metrica_versao": "armazenamento-com-backups-v4-compactacao",
        "limite_livre_mb": float(limite_livre_mb),
        "limite_wal_mb": float(limite_wal_mb),
    }


def atualizar_tendencia_armazenamento(
    atual,
    anterior=None,
    agora=None,
    intervalo_minutos=60,
    janela_horas=72,
    minimo_horas=6,
    horizonte_alerta_dias=30,
    reducao_material_minima_mb=1024,
    reducao_material_fracao=0.10,
):
    """Estima esgotamento sem reagir a oscilações curtas do arquivo WAL."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    resultado = dict(atual or {})
    anterior = anterior or {}
    metrica_versao = resultado.get("metrica_versao")
    if (
        metrica_versao
        and anterior.get("metrica_versao") != metrica_versao
    ):
        anterior = {}
    historico = []
    limite_historico = agora - timedelta(hours=float(janela_horas))
    for amostra in anterior.get("historico") or []:
        try:
            instante = datetime.fromisoformat(amostra["em"])
            total = float(amostra["total_mb"])
        except (KeyError, TypeError, ValueError):
            continue
        if limite_historico <= instante <= agora:
            historico.append({
                "em": instante.replace(microsecond=0).isoformat(),
                "total_mb": round(total, 1),
            })
    historico.sort(key=lambda item: item["em"])

    try:
        total_atual = float(resultado["total_mb"])
        livre_atual = float(resultado["livre_mb"])
    except (KeyError, TypeError, ValueError):
        resultado.update({
            "historico": historico,
            "tendencia_avaliavel": False,
            "crescimento_mb_dia": None,
            "dias_ate_limite": None,
        })
        return resultado

    # Uma compactação ou retenção verificada muda o patamar físico do
    # armazenamento. Manter todos os pontos anteriores depois de uma queda
    # grande faria o estimador interpretar espaço já recuperado como se ainda
    # estivesse crescendo. Rebasa somente quedas materiais; oscilações normais
    # do WAL permanecem no mesmo histórico.
    if historico:
        total_anterior = float(historico[-1]["total_mb"])
        reducao_mb = total_anterior - total_atual
        limiar_reducao = max(
            float(reducao_material_minima_mb),
            total_anterior * float(reducao_material_fracao),
        )
        if reducao_mb >= limiar_reducao:
            resultado["rebase_tendencia"] = True
            resultado["motivo_rebase_tendencia"] = (
                "reducao_material_armazenamento"
            )
            resultado["reducao_material_mb"] = round(reducao_mb, 1)
            resultado["historico_antes_rebase"] = {
                "amostras": len(historico),
                "primeiro_em": historico[0]["em"],
                "ultimo_em": historico[-1]["em"],
                "ultimo_total_mb": round(total_anterior, 1),
            }
            historico = []

    ultimo_em = (
        datetime.fromisoformat(historico[-1]["em"])
        if historico else None
    )
    if (
        ultimo_em is None
        or (agora - ultimo_em).total_seconds()
        >= float(intervalo_minutos) * 60
    ):
        historico.append({
            "em": agora.isoformat(),
            "total_mb": round(total_atual, 1),
        })

    resultado["historico"] = historico
    resultado["tendencia_avaliavel"] = False
    resultado["crescimento_mb_dia"] = None
    resultado["dias_ate_limite"] = None
    if not historico:
        return resultado

    inicio = datetime.fromisoformat(historico[0]["em"])
    horas = (agora - inicio).total_seconds() / 3600
    if horas < float(minimo_horas):
        return resultado

    crescimento_endpoint = (
        (total_atual - float(historico[0]["total_mb"]))
        / horas * 24
    )
    # Backups diarios, periodicos e pre-migracao entram no disco em degraus.
    # Usar somente o primeiro e o ultimo ponto transforma um backup isolado
    # em uma taxa permanente e pode fechar toda a operacao por um falso
    # esgotamento. A mediana das inclinacoes entre todos os pares (estimador
    # de Theil-Sen) conserva crescimento sustentado, mas e resistente a um
    # salto ou a uma limpeza pontual. Com apenas dois pontos, preservamos o
    # calculo historico ate existir amostra suficiente para a estimativa
    # robusta.
    inclinacoes = []
    intervalo_minimo_horas = max(float(intervalo_minutos) / 60.0, 1 / 60)
    for indice, primeiro in enumerate(historico):
        instante_primeiro = datetime.fromisoformat(primeiro["em"])
        total_primeiro = float(primeiro["total_mb"])
        for segundo in historico[indice + 1:]:
            instante_segundo = datetime.fromisoformat(segundo["em"])
            intervalo_horas = (
                instante_segundo - instante_primeiro
            ).total_seconds() / 3600
            if intervalo_horas < intervalo_minimo_horas:
                continue
            inclinacoes.append(
                (float(segundo["total_mb"]) - total_primeiro)
                / intervalo_horas * 24
            )
    usar_estimador_robusto = bool(
        len(historico) >= 3 and inclinacoes
    )
    crescimento_estimado = (
        median(inclinacoes)
        if usar_estimador_robusto else crescimento_endpoint
    )
    crescimento = max(crescimento_estimado, 0.0)
    resultado["metodo_tendencia"] = (
        "theil_sen_mediana_pares_v1"
        if usar_estimador_robusto else "primeiro_ultimo_ponto"
    )
    resultado["amostras_tendencia"] = len(historico)
    resultado["pares_tendencia"] = len(inclinacoes)
    resultado["crescimento_endpoint_mb_dia"] = round(
        max(crescimento_endpoint, 0.0), 1
    )
    resultado["tendencia_avaliavel"] = True
    resultado["crescimento_mb_dia"] = round(crescimento, 1)
    if crescimento <= 0:
        return resultado

    reserva = float(resultado.get("limite_livre_mb", 0) or 0)
    dias = max(livre_atual - reserva, 0.0) / crescimento
    resultado["dias_ate_limite"] = round(dias, 1)
    if dias < float(horizonte_alerta_dias):
        motivos = list(resultado.get("motivos") or [])
        if "crescimento_armazenamento_critico" not in motivos:
            motivos.append("crescimento_armazenamento_critico")
        resultado["motivos"] = motivos
        resultado["saudavel"] = False
    return resultado


def auditar_funil_recente(
    conexao,
    agora=None,
    regra_versao=VERSAO_REGRAS,
    janela_minutos=JANELA_FUNIL_MINUTOS,
):
    regra_versoes = (
        (regra_versao,)
        if isinstance(regra_versao, str)
        else tuple(dict.fromkeys(regra_versao or ()))
    )
    if not regra_versoes:
        regra_versoes = (VERSAO_REGRAS,)
    marcadores_versoes = ",".join("?" for _ in regra_versoes)
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite = (agora - timedelta(minutes=janela_minutos)).isoformat()
    inicio_versao = conexao.execute(
        f"""
        SELECT MIN(sn.coletado_em)
        FROM sinais s
        JOIN snapshots sn ON sn.id=s.snapshot_id
        WHERE s.regra_versao IN ({marcadores_versoes})
        """,
        regra_versoes,
    ).fetchone()[0]
    origem_inicio_versao = "primeiro_candidato"
    if inicio_versao is None:
        inicio_versao = conexao.execute(
            f"""
            SELECT MIN(atualizado_em) FROM calibracoes
            WHERE regra_versao IN ({marcadores_versoes})
            """,
            regra_versoes,
        ).fetchone()[0]
        origem_inicio_versao = "calibracao_inicial"
    transicao_versao = bool(
        inicio_versao
        and datetime.fromisoformat(inicio_versao)
        > datetime.fromisoformat(limite)
    )
    if transicao_versao:
        limite = inicio_versao
    linha = conexao.execute(
        f"""
        WITH base AS (
            SELECT id, qualidade_json, contexto_api_json
            FROM snapshots
            WHERE datetime(coletado_em) >= datetime(?)
              AND COALESCE(LOWER(status), '') NOT LIKE '%finaliz%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%encerrad%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%finished%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%full time%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%cancelad%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%anulad%'
              AND COALESCE(LOWER(status), '') NOT IN ('ft', 'wo')
        ),
        recentes AS (
            SELECT id
            FROM base
            WHERE COALESCE(
                json_extract(qualidade_json, '$.versao'), ''
            ) <> 'recuperacao-packball-v1'
              AND COALESCE(
                json_extract(qualidade_json, '$.versao'), ''
              ) NOT LIKE 'resultado-%'
              AND COALESCE(
                  json_extract(
                      contexto_api_json, '$.sem_detalhe_packball'
                  ), 0
              ) <> 1
        )
        SELECT
            COUNT(*) AS snapshots,
            (
                SELECT COUNT(*) FROM base
                WHERE COALESCE(
                    json_extract(qualidade_json, '$.versao'), ''
                ) = 'recuperacao-packball-v1'
            ) AS snapshots_recuperacao_excluidos,
            (
                SELECT COUNT(*) FROM base
                WHERE COALESCE(
                    json_extract(qualidade_json, '$.versao'), ''
                ) LIKE 'resultado-%'
            ) AS snapshots_liquidacao_excluidos,
            (
                SELECT COUNT(*) FROM base
                WHERE COALESCE(
                    json_extract(
                        contexto_api_json, '$.sem_detalhe_packball'
                    ), 0
                ) = 1
            ) AS snapshots_sombra_multifonte_excluidos,
            SUM(EXISTS (
                SELECT 1 FROM sinais s
                WHERE s.snapshot_id=recentes.id
                  AND s.regra_versao IN ({marcadores_versoes})
            )) AS com_candidatos,
            SUM(EXISTS (
                SELECT 1 FROM odds o
                WHERE o.snapshot_id=recentes.id AND o.tipo='ao_vivo'
                  AND CASE
                    WHEN json_valid(o.estrutura_json) THEN (
                        COALESCE(json_array_length(json_extract(
                            o.estrutura_json, '$.ofertas'
                        )), 0) > 0
                        OR COALESCE(json_array_length(json_extract(
                            o.estrutura_json, '$.ofertas_ht'
                        )), 0) > 0
                        OR json_extract(
                            o.estrutura_json, '$.selecoes.casa'
                        ) IS NOT NULL
                        OR json_extract(
                            o.estrutura_json, '$.selecoes.visitante'
                        ) IS NOT NULL
                    ) ELSE 0
                  END
            )) AS com_odds_estruturadas
        FROM recentes
        """,
        (limite, *regra_versoes),
    ).fetchone()
    snapshots = int(linha["snapshots"] or 0)
    candidatos = int(linha["com_candidatos"] or 0)
    odds = int(linha["com_odds_estruturadas"] or 0)
    recuperacao_excluidos = int(
        linha["snapshots_recuperacao_excluidos"] or 0
    )
    liquidacao_excluidos = int(
        linha["snapshots_liquidacao_excluidos"] or 0
    )
    sombra_multifonte_excluidos = int(
        linha["snapshots_sombra_multifonte_excluidos"] or 0
    )
    cobertura_candidatos = candidatos / snapshots if snapshots else None
    cobertura_odds = odds / snapshots if snapshots else None
    if snapshots == 0:
        estado = "sem_jogos_recentes"
    elif snapshots < AMOSTRA_MINIMA_FUNIL:
        estado = "amostra_operacional_insuficiente"
    else:
        estado = "avaliavel"
    return {
        "estado": estado,
        "janela_minutos": int(janela_minutos),
        "inicio_janela": limite,
        "transicao_versao": transicao_versao,
        "origem_inicio_versao": origem_inicio_versao,
        "regra_versoes": list(regra_versoes),
        "amostra_minima": AMOSTRA_MINIMA_FUNIL,
        "snapshots_ao_vivo": snapshots,
        "snapshots_com_candidatos": candidatos,
        "snapshots_com_odds_estruturadas": odds,
        "snapshots_recuperacao_excluidos": recuperacao_excluidos,
        "snapshots_liquidacao_excluidos": liquidacao_excluidos,
        "snapshots_sombra_multifonte_excluidos": (
            sombra_multifonte_excluidos
        ),
        "cobertura_candidatos": (
            round(cobertura_candidatos, 4)
            if cobertura_candidatos is not None else None
        ),
        "cobertura_odds_estruturadas": (
            round(cobertura_odds, 4) if cobertura_odds is not None else None
        ),
    }


def auditar_features_temporais(
    conexao,
    agora=None,
    regra_versao=VERSAO_REGRAS,
    versao_features=VERSAO_FEATURES,
    janela_minutos=JANELA_FUNIL_MINUTOS,
    amostra_minima=AMOSTRA_MINIMA_FEATURES,
):
    """Confere se candidatos novos preservam o vetor temporal versionado."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite = (agora - timedelta(minutes=janela_minutos)).isoformat()
    inicio_features = conexao.execute(
        """
        SELECT MIN(criado_em) FROM sinais
        WHERE regra_versao=? AND json_valid(features_json)
          AND json_extract(features_json, '$.schema_versao')=?
        """,
        (regra_versao, versao_features),
    ).fetchone()[0]
    transicao = bool(
        inicio_features
        and datetime.fromisoformat(inicio_features)
        > datetime.fromisoformat(limite)
    )
    if transicao:
        limite = inicio_features
    linhas = conexao.execute(
        """
        SELECT snapshot_id, mercado, features_json
        FROM sinais
        WHERE regra_versao=? AND datetime(criado_em) >= datetime(?)
        ORDER BY snapshot_id, id
        """,
        (regra_versao, limite),
    ).fetchall()
    por_snapshot = {}
    candidatos_validos = 0
    janelas_disponiveis = {str(item): 0 for item in (5, 10, 15)}
    duracoes_medidas = {str(item): 0 for item in (5, 10, 15)}
    features_representativas = {}

    def janela_valida(janela):
        if not isinstance(janela, dict) or not isinstance(
            janela.get("disponivel"), bool
        ):
            return False
        if not janela["disponivel"]:
            return True
        try:
            duracao_bruta = janela.get("duracao_real_minutos")
            duracao = (
                float(duracao_bruta) if duracao_bruta is not None else None
            )
            if duracao is not None and duracao <= 0:
                return False
            for nome in ("chutes", "escanteios"):
                par = janela.get(nome)
                total = janela.get(f"{nome}_total")
                taxa = janela.get(f"{nome}_por_minuto")
                taxas_lados = janela.get(f"{nome}_por_minuto_lados")
                if par is None:
                    if total is not None or taxa is not None or taxas_lados is not None:
                        return False
                    continue
                if not isinstance(par, list) or len(par) != 2:
                    return False
                valores = [float(par[0]), float(par[1])]
                if total is None or abs(float(total) - sum(valores)) > 0.001:
                    return False
                if duracao is None:
                    if taxa is not None or taxas_lados is not None:
                        return False
                    continue
                if abs(float(taxa) - sum(valores) / duracao) > 0.001:
                    return False
                if not isinstance(taxas_lados, list) or len(taxas_lados) != 2:
                    return False
                if any(
                    abs(float(taxas_lados[indice]) - valores[indice] / duracao)
                    > 0.001
                    for indice in (0, 1)
                ):
                    return False
        except (TypeError, ValueError, ZeroDivisionError):
            return False
        return True

    for linha in linhas:
        valido = False
        features = None
        try:
            features = json.loads(linha["features_json"] or "{}")
            janelas = features.get("janelas")
            valido = bool(
                isinstance(features, dict)
                and features.get("schema_versao") == versao_features
                and features.get("mercado") == linha["mercado"]
                and isinstance(janelas, dict)
                and all(
                    janela_valida(janelas.get(str(item)))
                    for item in (5, 10, 15)
                )
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            valido = False
        por_snapshot.setdefault(linha["snapshot_id"], []).append(valido)
        if valido:
            candidatos_validos += 1
            features_representativas.setdefault(
                linha["snapshot_id"], features
            )
    for features in features_representativas.values():
        for item in (5, 10, 15):
            janela = features["janelas"][str(item)]
            if janela.get("disponivel"):
                janelas_disponiveis[str(item)] += 1
            if janela.get("duracao_real_minutos") is not None:
                duracoes_medidas[str(item)] += 1
    snapshots = len(por_snapshot)
    snapshots_integros = sum(all(itens) for itens in por_snapshot.values())
    total = len(linhas)
    cobertura = candidatos_validos / total if total else None
    cobertura_snapshots = snapshots_integros / snapshots if snapshots else None
    if total == 0:
        estado = "sem_candidatos_recentes"
    elif inicio_features is None:
        estado = "aguardando_primeiro_registro"
    elif snapshots < int(amostra_minima):
        estado = "amostra_operacional_insuficiente"
    else:
        estado = "avaliavel"
    saudavel = not (
        inicio_features is not None and candidatos_validos != total
    )
    return {
        "saudavel": saudavel,
        "estado": estado,
        "schema_versao": versao_features,
        "janela_minutos": int(janela_minutos),
        "inicio_janela": limite,
        "inicio_schema": inicio_features,
        "transicao_schema": transicao,
        "amostra_minima": int(amostra_minima),
        "candidatos": total,
        "candidatos_validos": candidatos_validos,
        "snapshots": snapshots,
        "snapshots_integros": snapshots_integros,
        "cobertura": round(cobertura, 4) if cobertura is not None else None,
        "cobertura_snapshots": (
            round(cobertura_snapshots, 4)
            if cobertura_snapshots is not None else None
        ),
        "janelas_disponiveis": janelas_disponiveis,
        "duracoes_medidas": duracoes_medidas,
    }


def auditar_integridade_telegram(
    conexao, agora=None, tolerancia_minutos=5, erro_minutos=10,
    incerto_minutos=2,
):
    """Confere a cadeia persistida entre sinal, resultado e Telegram."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite_aviso = (
        agora - timedelta(minutes=tolerancia_minutos)
    ).isoformat()
    limite_erro = (agora - timedelta(minutes=erro_minutos)).isoformat()
    limite_incerto = (
        agora - timedelta(minutes=incerto_minutos)
    ).isoformat()
    resultados_sem_aviso_linha = conexao.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE
                   WHEN faltante.canal NOT LIKE '%:%' THEN 1 ELSE 0
               END), 0) AS oficiais,
               COALESCE(SUM(CASE
                   WHEN faltante.canal LIKE '%:teste' THEN 1 ELSE 0
               END), 0) AS analises
        FROM (
            SELECT DISTINCT r.sinal_id, origem.canal
            FROM resultados_sinais r
            JOIN entregas_alertas origem ON origem.sinal_id=r.sinal_id
             AND origem.status='entregue'
             AND (
                 origem.canal NOT LIKE '%:%'
                 OR origem.canal LIKE '%:teste'
             )
            WHERE datetime(r.encerrado_em) <= datetime(?)
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas aviso
                  WHERE aviso.sinal_id=r.sinal_id
                    AND aviso.canal=origem.canal || ':resultado'
                    AND aviso.status='entregue'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM revisoes_resultados rev
                  WHERE rev.sinal_id=r.sinal_id
                    AND rev.notificacao_status='entregue'
              )
        ) AS faltante
        """,
        (limite_aviso,),
    ).fetchone()
    resultados_sem_aviso = int(resultados_sem_aviso_linha[0] or 0)
    resultados_oficiais_sem_aviso = int(
        resultados_sem_aviso_linha[1] or 0
    )
    resultados_analise_sem_aviso = int(
        resultados_sem_aviso_linha[2] or 0
    )
    avisos_sem_resultado = conexao.execute(
        """
        SELECT COUNT(*)
        FROM entregas_alertas aviso
        LEFT JOIN resultados_sinais r ON r.sinal_id=aviso.sinal_id
        WHERE aviso.status='entregue'
          AND aviso.canal LIKE '%:resultado'
          AND r.sinal_id IS NULL
        """
    ).fetchone()[0]
    erros_persistentes = conexao.execute(
        """
        SELECT COUNT(*) FROM entregas_alertas
        WHERE status='erro' AND datetime(tentado_em) <= datetime(?)
        """,
        (limite_erro,),
    ).fetchone()[0]
    correcoes_pendentes = conexao.execute(
        """
        SELECT COUNT(*)
        FROM revisoes_resultados rev
        JOIN entregas_alertas origem
          ON origem.sinal_id=rev.sinal_id
         AND origem.status='entregue'
         AND origem.canal LIKE '%:teste'
         AND origem.canal NOT LIKE '%:teste:resultado'
        WHERE rev.notificacao_status<>'entregue'
          AND datetime(rev.revisado_em) <= datetime(?)
        """,
        (limite_aviso,),
    ).fetchone()[0]
    resultados_duplicados = conexao.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT sinal_id
            FROM entregas_alertas
            WHERE status='entregue' AND canal LIKE '%:resultado'
            GROUP BY sinal_id HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    bloqueios_gateway = conexao.execute(
        """
        SELECT COUNT(*) FROM entregas_alertas
        WHERE status='bloqueado' AND canal='gateway:oficial'
          AND datetime(tentado_em) >= datetime(?, '-24 hours')
        """,
        (agora.isoformat(),),
    ).fetchone()[0]
    envios_incertos_linha = conexao.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE
                   WHEN pendente.canal NOT LIKE '%:%' THEN 1 ELSE 0
               END), 0) AS oficiais,
               COALESCE(SUM(CASE
                   WHEN pendente.canal LIKE '%:teste%' THEN 1 ELSE 0
               END), 0) AS analises
        FROM entregas_alertas pendente
        WHERE pendente.status IN ('enviando', 'tentando', 'incerto')
          AND (
              pendente.status='incerto'
              OR datetime(pendente.tentado_em) <= datetime(?)
          )
          AND NOT EXISTS (
              SELECT 1 FROM entregas_alertas final
              WHERE final.sinal_id=pendente.sinal_id
                AND final.canal=pendente.canal
                AND final.status IN (
                    'entregue', 'erro', 'recuperado', 'cancelado',
                    'expirado'
                )
                AND datetime(final.tentado_em)
                    >= datetime(pendente.tentado_em)
          )
          AND NOT EXISTS (
              SELECT 1 FROM entregas_alertas posterior
              WHERE posterior.sinal_id=pendente.sinal_id
                AND posterior.canal=pendente.canal
                AND posterior.status IN ('enviando', 'tentando', 'incerto')
                AND (
                    datetime(posterior.tentado_em)
                        > datetime(pendente.tentado_em)
                    OR (
                        datetime(posterior.tentado_em)
                            = datetime(pendente.tentado_em)
                        AND posterior.id > pendente.id
                    )
                )
          )
        """,
        (limite_incerto,),
    ).fetchone()
    envios_incertos = int(envios_incertos_linha[0] or 0)
    envios_oficiais_incertos = int(envios_incertos_linha[1] or 0)
    envios_analise_incertos = int(envios_incertos_linha[2] or 0)
    confirmacoes_telegram_invalidas = conexao.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT provedor_destino_id AS destino,
                   provedor_mensagem_id AS mensagem_id,
                   confirmacao_json AS confirmacao
            FROM entregas_alertas
            WHERE status='entregue' AND provedor='telegram'
            UNION ALL
            SELECT notificacao_destino_id,
                   notificacao_mensagem_id,
                   notificacao_confirmacao_json
            FROM revisoes_resultados
            WHERE notificacao_status='entregue'
              AND notificacao_provedor='telegram'
        ) AS provas
        WHERE destino IS NULL OR TRIM(destino)=''
           OR CASE
                WHEN json_valid(confirmacao) THEN
                    COALESCE(json_extract(confirmacao, '$.ok'), 0) <> 1
                    OR CASE
                         WHEN COALESCE(
                             json_extract(confirmacao, '$.edicao'), 0
                         ) = 1 THEN
                             mensagem_id IS NOT NULL
                             OR TRIM(CAST(COALESCE(
                                 json_extract(
                                     confirmacao, '$.message_id_origem'
                                 ), ''
                             ) AS TEXT)) = ''
                         ELSE
                             COALESCE(
                                 json_extract(confirmacao, '$.provedor'), ''
                             ) <> 'telegram'
                             OR
                             mensagem_id IS NULL
                             OR TRIM(mensagem_id)=''
                             OR CAST(COALESCE(
                                 json_extract(
                                     confirmacao, '$.message_id'
                                 ), ''
                             ) AS TEXT) <> CAST(mensagem_id AS TEXT)
                       END
                ELSE 1
              END
        """
    ).fetchone()[0]
    confirmacoes_telegram_duplicadas = conexao.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT destino, mensagem_id
            FROM (
                SELECT provedor_destino_id AS destino,
                       provedor_mensagem_id AS mensagem_id
                FROM entregas_alertas
                WHERE status='entregue' AND provedor='telegram'
                UNION ALL
                SELECT notificacao_destino_id,
                       notificacao_mensagem_id
                FROM revisoes_resultados
                WHERE notificacao_status='entregue'
                  AND notificacao_provedor='telegram'
            ) AS provas
            WHERE destino IS NOT NULL AND mensagem_id IS NOT NULL
            GROUP BY destino, mensagem_id
            HAVING COUNT(*) > 1
        ) AS duplicadas
        """
    ).fetchone()[0]
    confirmacoes_telegram_validas = conexao.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT provedor_mensagem_id AS mensagem_id
            FROM entregas_alertas
            WHERE status='entregue' AND provedor='telegram'
            UNION ALL
            SELECT notificacao_mensagem_id
            FROM revisoes_resultados
            WHERE notificacao_status='entregue'
              AND notificacao_provedor='telegram'
        ) AS provas
        WHERE mensagem_id IS NOT NULL
        """
    ).fetchone()[0]
    entregas_telegram_legadas_sem_prova = conexao.execute(
        """
        SELECT (
            SELECT COUNT(*) FROM entregas_alertas
            WHERE status='entregue' AND provedor IS NULL
        ) + (
            SELECT COUNT(*) FROM revisoes_resultados
            WHERE notificacao_status='entregue'
              AND notificacao_provedor IS NULL
        )
        """
    ).fetchone()[0]
    valores = {
        "resultados_sem_aviso": resultados_sem_aviso,
        "avisos_sem_resultado": int(avisos_sem_resultado or 0),
        "erros_persistentes": int(erros_persistentes or 0),
        "correcoes_pendentes": int(correcoes_pendentes or 0),
        "resultados_duplicados": int(resultados_duplicados or 0),
        "bloqueios_gateway_24h": int(bloqueios_gateway or 0),
        "envios_incertos": int(envios_incertos or 0),
        "confirmacoes_telegram_invalidas": int(
            confirmacoes_telegram_invalidas or 0
        ),
        "confirmacoes_telegram_duplicadas": int(
            confirmacoes_telegram_duplicadas or 0
        ),
    }
    valores_operacionais = {
        **valores,
        # Uma análise já liquidada com entrega ambígua exige conferência,
        # mas não invalida o dado esportivo nem deve bloquear novas análises.
        "resultados_sem_aviso": resultados_oficiais_sem_aviso,
        "envios_incertos": envios_oficiais_incertos,
    }
    return {
        "saudavel": not any(valores.values()),
        "saudavel_operacional": not any(valores_operacionais.values()),
        "tolerancia_minutos": int(tolerancia_minutos),
        "erro_minutos": int(erro_minutos),
        "incerto_minutos": int(incerto_minutos),
        "confirmacoes_telegram_validas": int(
            confirmacoes_telegram_validas or 0
        ),
        "entregas_telegram_legadas_sem_prova": int(
            entregas_telegram_legadas_sem_prova or 0
        ),
        "envios_oficiais_incertos": envios_oficiais_incertos,
        "envios_analise_incertos": envios_analise_incertos,
        "resultados_oficiais_sem_aviso": resultados_oficiais_sem_aviso,
        "resultados_analise_sem_aviso": resultados_analise_sem_aviso,
        **valores,
    }


def _destinos_operacionais_configurados():
    admin = os.getenv("TELEGRAM_ADMIN_ID")
    grupos_ativos = (
        os.getenv("TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS", "0") == "1"
    )
    grupos = tuple(filter(None, (
        os.getenv("TELEGRAM_CHAT_ID"),
        os.getenv("TELEGRAM_CHAT_ID_GOLS"),
        os.getenv("TELEGRAM_CHAT_ID_ESCANTEIOS"),
    )))
    destinos = []
    # TELEGRAM_ADMIN_ID só é uma rota administrativa segura quando não
    # aponta para um dos grupos de sinais. Sem esse cuidado, a configuração
    # aparentemente separada continuava publicando telemetria no grupo.
    admin_exclusivo = bool(admin and admin not in grupos)
    candidatos = [admin] if admin_exclusivo else []
    if grupos_ativos or not admin:
        candidatos.extend(grupos)
    for destino in candidatos:
        if destino and destino not in destinos:
            destinos.append(destino)
    return destinos


def _destinos_resumo_configurados():
    """Mantém o placar no grupo sem misturar telemetria administrativa."""
    destinos = []
    for destino in (
        os.getenv("TELEGRAM_CHAT_ID"),
        os.getenv("TELEGRAM_CHAT_ID_GOLS"),
    ):
        if destino and destino not in destinos:
            destinos.append(destino)
    if not destinos:
        fallback = (
            os.getenv("TELEGRAM_CHAT_ID_ESCANTEIOS")
            or os.getenv("TELEGRAM_ADMIN_ID")
        )
        if fallback:
            destinos.append(fallback)
    return destinos


def auditar_notificacoes_operacionais(
    conexao, agora=None, incerto_minutos=2, erro_minutos=10,
):
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite_incerto = (
        agora - timedelta(minutes=incerto_minutos)
    ).isoformat()
    limite_erro = (agora - timedelta(minutes=erro_minutos)).isoformat()
    incertas_em_transito = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais
        WHERE status IN ('enviando', 'tentando')
          AND datetime(tentado_em) <= datetime(?)
        """,
        (limite_incerto,),
    ).fetchone()[0]
    incertas_nao_superadas = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais incerta
        WHERE incerta.status='incerto'
          AND NOT EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.destino=incerta.destino
                AND sucesso.status='entregue'
                AND datetime(sucesso.entregue_em)
                    > datetime(incerta.tentado_em)
          )
        """
    ).fetchone()[0]
    incertas_superadas = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais incerta
        WHERE incerta.status='incerto'
          AND EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.destino=incerta.destino
                AND sucesso.status='entregue'
                AND datetime(sucesso.entregue_em)
                    > datetime(incerta.tentado_em)
          )
        """
    ).fetchone()[0]
    incertas = int(incertas_em_transito or 0) + int(
        incertas_nao_superadas or 0
    )
    destinos_ativos = _destinos_operacionais_configurados()
    filtro_destinos = ""
    parametros_erros = [limite_erro]
    if destinos_ativos:
        filtro_destinos = (
            " AND falha.destino IN ("
            + ",".join("?" for _ in destinos_ativos)
            + ")"
        )
        parametros_erros.extend(destinos_ativos)
    else:
        # Sem contexto de configuração não é correto reclassificar falhas
        # históricas de destinos já removidos como incidentes atuais.
        # A ausência de destino é tratada pela validação de configuração.
        filtro_destinos = " AND 0"
    erros_persistentes = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais falha
        WHERE falha.status='erro'
          AND falha.tentativas >= 3
          AND datetime(falha.tentado_em) <= datetime(?)
        """ + filtro_destinos + """
          AND NOT EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.status='entregue'
                AND (
                    sucesso.chave=falha.chave
                    OR (
                        sucesso.destino=falha.destino
                        AND datetime(sucesso.entregue_em)
                            > datetime(falha.tentado_em)
                    )
                )
          )
        """,
        parametros_erros,
    ).fetchone()[0]
    provas_invalidas = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais
        WHERE status='entregue'
          AND (
              provedor<>'telegram'
              OR provedor_mensagem_id IS NULL
              OR TRIM(provedor_mensagem_id)=''
              OR CASE
                   WHEN json_valid(confirmacao_json) THEN
                       COALESCE(
                           json_extract(confirmacao_json, '$.ok'), 0
                       ) <> 1
                       OR COALESCE(
                           json_extract(
                               confirmacao_json, '$.provedor'
                           ), ''
                       ) <> 'telegram'
                       OR CAST(COALESCE(
                           json_extract(
                               confirmacao_json, '$.message_id'
                           ), ''
                       ) AS TEXT) <> CAST(provedor_mensagem_id AS TEXT)
                   ELSE 1
                 END
          )
        """
    ).fetchone()[0]
    provas_duplicadas = conexao.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT destino, provedor_mensagem_id
            FROM notificacoes_operacionais
            WHERE status='entregue' AND provedor='telegram'
              AND provedor_mensagem_id IS NOT NULL
            GROUP BY destino, provedor_mensagem_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    entregues = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais
        WHERE status='entregue'
        """
    ).fetchone()[0]
    disjuntores = [
        _estado_disjuntor_notificacao_operacional(
            conexao, destino, agora
        )
        for destino in destinos_ativos
    ]
    pausados = [
        item for item in disjuntores if item.get("pausado")
    ]
    valores = {
        "incertas": int(incertas or 0),
        "incertas_em_transito": int(incertas_em_transito or 0),
        "incertas_nao_superadas": int(incertas_nao_superadas or 0),
        "incertas_superadas": int(incertas_superadas or 0),
        "erros_persistentes": int(erros_persistentes or 0),
        "provas_invalidas": int(provas_invalidas or 0),
        "provas_duplicadas": int(provas_duplicadas or 0),
        "disjuntor_pausado": bool(pausados),
    }
    criticos = {
        "erros_persistentes": valores["erros_persistentes"],
        "provas_invalidas": valores["provas_invalidas"],
        "provas_duplicadas": valores["provas_duplicadas"],
    }
    return {
        # Uma confirmação operacional ambígua não altera snapshots,
        # sinais ou resultados. Ela continua visível para reconciliação,
        # mas somente falha persistente ou prova inválida degrada os dados.
        "saudavel": not any(criticos.values()),
        "requer_atencao": bool(
            valores["incertas"] or valores["disjuntor_pausado"]
        ),
        "entregues_com_prova": int(entregues or 0),
        "destinos_configurados": len(destinos_ativos),
        "incerto_minutos": int(incerto_minutos),
        "erro_minutos": int(erro_minutos),
        "disjuntor_pausado": bool(pausados),
        "destinos_pausados": len(pausados),
        "proxima_tentativa_em": min(
            (
                item["proxima_tentativa_em"]
                for item in pausados
                if item.get("proxima_tentativa_em")
            ),
            default=None,
        ),
        **valores,
    }


def reconciliar_notificacoes_operacionais(
    conexao, agora=None, incerto_minutos=2,
):
    """Fecha intenções abandonadas sem assumir entrega nem reenviar."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite = (agora - timedelta(minutes=incerto_minutos)).isoformat()
    with conexao:
        cursor = conexao.execute(
            """
            UPDATE notificacoes_operacionais
            SET status='incerto',
                erro=COALESCE(
                    erro,
                    'confirmacao_telegram_ausente_apos_interrupcao'
                )
            WHERE status IN ('enviando', 'tentando')
              AND datetime(tentado_em) <= datetime(?)
            """,
            (limite,),
        )
    auditoria = auditar_notificacoes_operacionais(
        conexao,
        agora=agora,
        incerto_minutos=incerto_minutos,
    )
    return {
        "saudavel": True,
        "reconciliadas": int(cursor.rowcount or 0),
        "incertas_nao_superadas": auditoria["incertas_nao_superadas"],
        "incertas_superadas": auditoria["incertas_superadas"],
    }


def reconciliar_acompanhamentos_odd_expirados(conexao):
    """Fecha avisos ambíguos que perderam a validade esportiva.

    Um aviso ``aguardar_odd`` não é entrada oficial. Se a confirmação do
    Telegram ficou ambígua e o último snapshot comprova que a partida acabou,
    ele pode ser encerrado como expirado sem afirmar entrega ou não entrega.
    Envios oficiais e partidas ainda ao vivo nunca são tocados.
    """
    marcador = "entrega_ambigua_expirada_apos_partida_finalizada"
    with conexao:
        cursor = conexao.execute(
            """
            UPDATE entregas_alertas AS pendente
            SET status='expirado',
                erro=CASE
                    WHEN pendente.erro IS NULL
                      OR TRIM(pendente.erro)='' THEN ?
                    WHEN INSTR(pendente.erro, ?) > 0 THEN pendente.erro
                    ELSE pendente.erro || ';' || ?
                END
            WHERE pendente.status IN ('enviando', 'tentando', 'incerto')
              AND pendente.canal LIKE '%:aguardar_odd'
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas final
                  WHERE final.sinal_id=pendente.sinal_id
                    AND final.canal=pendente.canal
                    AND final.status IN (
                        'entregue', 'erro', 'recuperado', 'cancelado',
                        'expirado'
                    )
                    AND final.id<>pendente.id
                    AND datetime(final.tentado_em)
                        >= datetime(pendente.tentado_em)
              )
              AND EXISTS (
                  SELECT 1
                  FROM sinais s
                  JOIN snapshots ultimo ON ultimo.partida_id=s.partida_id
                  WHERE s.id=pendente.sinal_id
                    AND ultimo.id=(
                        SELECT MAX(sn.id)
                        FROM snapshots sn
                        WHERE sn.partida_id=s.partida_id
                    )
                    AND datetime(ultimo.coletado_em)
                        >= datetime(pendente.tentado_em)
                    AND (
                        COALESCE(LOWER(ultimo.status), '') LIKE '%finaliz%'
                        OR COALESCE(LOWER(ultimo.status), '') LIKE '%encerrad%'
                        OR COALESCE(LOWER(ultimo.status), '') LIKE '%finished%'
                        OR COALESCE(LOWER(ultimo.status), '') LIKE '%full time%'
                        OR COALESCE(LOWER(ultimo.status), '') LIKE '%cancelad%'
                        OR COALESCE(LOWER(ultimo.status), '') LIKE '%anulad%'
                        OR COALESCE(LOWER(ultimo.status), '') LIKE '%adiad%'
                        OR COALESCE(LOWER(ultimo.status), '') IN ('ft', 'wo')
                    )
              )
            """,
            (marcador, marcador, marcador),
        )
    return {
        "saudavel": True,
        "estado": "reconciliado",
        "expirados": int(cursor.rowcount or 0),
        "criterio": "aviso_aguardar_odd_com_partida_finalizada",
        "envios_oficiais_alterados": 0,
    }


def _resumir_estado_calibracao(item, modelo):
    discriminacao = modelo.get("discriminacao_pontuacao") or {}
    celulas = modelo.get("validacao_por_faixa") or {}
    prospectiva = modelo.get("validacao_prospectiva_expandida") or {}
    discriminacao_prospectiva = (
        prospectiva.get("discriminacao_pontuacao") or {}
    )
    return {
        "ativa": bool(item["ativa"]),
        "amostra": int(item["amostra"] or 0),
        "motivo": modelo.get("motivo"),
        "atualizado_em": item["atualizado_em"],
        "amostra_validacao": int(
            modelo.get("amostra_validacao", 0) or 0
        ),
        "roi_validacao_agregado": modelo.get(
            "roi_validacao_agregado"
        ),
        "auc_validacao": discriminacao.get("auc"),
        "limite_inferior_auc_95": discriminacao.get(
            "limite_inferior_auc_95"
        ),
        "erro_calibracao": modelo.get("erro_calibracao"),
        "celulas_aprovadas": sum(
            bool(valor.get("aprovada"))
            for valor in celulas.values()
            if isinstance(valor, dict)
        ),
        "celulas_avaliadas": len(celulas),
        "validacao_prospectiva": {
            "estado": prospectiva.get("estado"),
            "motivo": prospectiva.get("motivo"),
            "motivos": list(prospectiva.get("motivos") or ()),
            "amostra_avaliada": int(
                prospectiva.get("amostra_avaliada", 0) or 0
            ),
            "amostra_validacao": int(
                prospectiva.get("amostra_validacao", 0) or 0
            ),
            "resultados_apos_holdout_original": int(
                prospectiva.get(
                    "resultados_apos_holdout_original", 0
                ) or 0
            ),
            "roi_validacao_agregado": prospectiva.get(
                "roi_validacao_agregado"
            ),
            "auc_validacao": discriminacao_prospectiva.get("auc"),
            "limite_inferior_auc_95": (
                discriminacao_prospectiva.get(
                    "limite_inferior_auc_95"
                )
            ),
            "validacao_coberta": int(
                prospectiva.get("validacao_coberta", 0) or 0
            ),
            "validacao_aprovada": int(
                prospectiva.get("validacao_aprovada", 0) or 0
            ),
            "celulas_avaliadas": int(
                prospectiva.get("celulas_avaliadas", 0) or 0
            ),
            "celulas_aprovadas": int(
                prospectiva.get("celulas_aprovadas", 0) or 0
            ),
            "habilita_sinal_oficial": bool(
                prospectiva.get("habilita_sinal_oficial", False)
            ),
            "promocao_automatica": bool(
                prospectiva.get("promocao_automatica", False)
            ),
        },
    }


def _classificar_frescor_calibracoes(
    frescor, agora, estado_coleta=None,
    tolerancia_segundos=TOLERANCIA_RECONCILIACAO_CALIBRACAO_SEGUNDOS,
):
    """Separa atraso persistente da janela normal de reconciliação.

    Uma calibração inativa não participa de sinais oficiais. Quando ela fica
    um resultado atrás, concedemos a mesma janela curta de reconciliação mesmo
    entre ciclos; isso evita alertar o operador por um estado transitório que o
    monitor corrigirá na próxima passagem. Calibrações ativas continuam
    toleradas somente enquanto um ciclo está comprovadamente em andamento.
    """
    resultado = dict(frescor or {})
    ciclo_em_andamento = bool(
        (estado_coleta or {}).get("ciclo_em_andamento")
    )
    detalhes = list(resultado.get("detalhes") or [])
    reconciliando = []
    alertaveis = []
    for item in detalhes:
        if not item.get("desatualizada"):
            continue
        recente = False
        try:
            instante = datetime.fromisoformat(
                item.get("ultimo_resultado_em")
            )
            referencia = agora
            if instante.tzinfo is not None and referencia.tzinfo is None:
                instante = instante.replace(tzinfo=None)
            elif instante.tzinfo is None and referencia.tzinfo is not None:
                referencia = referencia.replace(tzinfo=None)
            idade = (referencia - instante).total_seconds()
            recente = 0 <= idade <= float(tolerancia_segundos)
        except (TypeError, ValueError):
            recente = False
        em_janela_reconciliacao = bool(
            recente
            and (
                ciclo_em_andamento
                or not bool(item.get("ativa"))
            )
        )
        (
            reconciliando
            if em_janela_reconciliacao
            else alertaveis
        ).append(item)

    # Auditorias simuladas/legadas sem detalhes continuam falhando fechado.
    total_desatualizadas = int(resultado.get("desatualizadas", 0) or 0)
    sem_detalhe = max(
        total_desatualizadas - len(reconciliando) - len(alertaveis),
        0,
    )
    alertaveis_ativas = sum(
        bool(item.get("ativa")) for item in alertaveis
    )
    alertaveis_inativas = len(alertaveis) - alertaveis_ativas
    if sem_detalhe:
        alertaveis_ativas += int(
            resultado.get("desatualizadas_ativas", sem_detalhe) or 0
        )
        alertaveis_inativas += int(
            resultado.get("desatualizadas_inativas", 0) or 0
        )
    resultado["reconciliacao_em_andamento"] = len(reconciliando)
    resultado["mercados_em_reconciliacao"] = [
        item.get("mercado") for item in reconciliando
    ]
    resultado["desatualizadas_alertaveis"] = (
        alertaveis_ativas + alertaveis_inativas
    )
    resultado["desatualizadas_ativas_alertaveis"] = alertaveis_ativas
    resultado["desatualizadas_inativas_alertaveis"] = alertaveis_inativas
    resultado["tolerancia_reconciliacao_segundos"] = int(
        tolerancia_segundos
    )
    return resultado


def verificar_validacao(caminho_banco, agora=None, estado_coleta=None):
    inicio_validacao = time.monotonic()
    inicio_fase_validacao = [inicio_validacao]
    duracoes_validacao = {}

    def marcar_validacao(nome):
        instante = time.monotonic()
        duracoes_validacao[nome] = round(
            instante - inicio_fase_validacao[0], 3
        )
        inicio_fase_validacao[0] = instante

    agora = (agora or datetime.now()).replace(microsecond=0)
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "requer_atencao": True,
            "motivos": ["banco_ausente"],
            "avisos": [],
        }
    try:
        conexao = sqlite3.connect(
            f"file:{caminho_banco.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=10,
        )
        conexao.row_factory = sqlite3.Row
        limite_pendencia = (agora - timedelta(minutes=180)).isoformat()
        limite_pendencia_absoluta = (
            agora - timedelta(minutes=360)
        ).isoformat()
        limite_observacao_recente = (
            agora - timedelta(minutes=30)
        ).isoformat()
        limite_24h = (agora - timedelta(hours=24)).isoformat()
        limite_estagnacao = (agora - timedelta(hours=6)).isoformat()
        pendencias_vencidas = conexao.execute(
            """
            SELECT COUNT(*)
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado' AND r.sinal_id IS NULL
              AND datetime(s.criado_em) <= datetime(?)
              AND (
                  datetime(s.criado_em) <= datetime(?)
                  OR COALESCE(
                      (
                          SELECT MAX(sn.coletado_em)
                          FROM snapshots sn
                          WHERE sn.partida_id=s.partida_id
                      ),
                      s.criado_em
                  ) <= ?
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM consultas_finalizacao cf
                  WHERE cf.partida_id=s.partida_id
                    AND cf.estado='finalizado_dados_incompletos'
                  GROUP BY cf.partida_id
                  HAVING datetime(MIN(cf.consultado_em)) > datetime(?)
              )
            """,
            (
                limite_pendencia,
                limite_pendencia_absoluta,
                limite_observacao_recente,
                limite_24h,
            ),
        ).fetchone()[0]
        linhas_pendencias_vencidas = conexao.execute(
            """
            SELECT s.id AS sinal_id, s.mercado, s.criado_em,
                   p.mandante, p.visitante
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado' AND r.sinal_id IS NULL
              AND datetime(s.criado_em) <= datetime(?)
              AND (
                  datetime(s.criado_em) <= datetime(?)
                  OR COALESCE(
                      (
                          SELECT MAX(sn.coletado_em)
                          FROM snapshots sn
                          WHERE sn.partida_id=s.partida_id
                      ),
                      s.criado_em
                  ) <= ?
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM consultas_finalizacao cf
                  WHERE cf.partida_id=s.partida_id
                    AND cf.estado='finalizado_dados_incompletos'
                  GROUP BY cf.partida_id
                  HAVING datetime(MIN(cf.consultado_em)) > datetime(?)
              )
            ORDER BY datetime(s.criado_em), s.id
            LIMIT 3
            """,
            (
                limite_pendencia,
                limite_pendencia_absoluta,
                limite_observacao_recente,
                limite_24h,
            ),
        ).fetchall()
        pendencias_finais_incompletas_aguardando = conexao.execute(
            """
            SELECT COUNT(*)
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado' AND r.sinal_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM consultas_finalizacao cf
                  WHERE cf.partida_id=s.partida_id
                    AND cf.estado='finalizado_dados_incompletos'
                  GROUP BY cf.partida_id
                  HAVING datetime(MIN(cf.consultado_em)) > datetime(?)
              )
            """,
            (limite_24h,),
        ).fetchone()[0]
        detalhes_pendencias_vencidas = []
        for item in linhas_pendencias_vencidas:
            try:
                idade_minutos = round(
                    max(
                        (
                            agora - datetime.fromisoformat(
                                item["criado_em"]
                            )
                        ).total_seconds(),
                        0,
                    ) / 60,
                    1,
                )
            except (TypeError, ValueError):
                idade_minutos = None
            detalhes_pendencias_vencidas.append({
                "sinal_id": int(item["sinal_id"]),
                "partida": f"{item['mandante']} x {item['visitante']}",
                "mercado": item["mercado"],
                "idade_minutos": idade_minutos,
            })
        pendencias_longas_ativas = conexao.execute(
            """
            SELECT COUNT(*)
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado' AND r.sinal_id IS NULL
              AND datetime(s.criado_em) <= datetime(?)
              AND datetime(s.criado_em) > datetime(?)
              AND (
                  SELECT MAX(sn.coletado_em)
                  FROM snapshots sn
                  WHERE sn.partida_id=s.partida_id
              ) > ?
            """,
            (
                limite_pendencia,
                limite_pendencia_absoluta,
                limite_observacao_recente,
            ),
        ).fetchone()[0]
        sem_dado_24h = conexao.execute(
            """
            SELECT COUNT(*) FROM resultados_sinais
            WHERE resultado='sem_dado'
              AND datetime(encerrado_em) >= datetime(?)
            """,
            (limite_24h,),
        ).fetchone()[0]
        resultados_encerrados_24h = conexao.execute(
            """
            SELECT COUNT(*) FROM resultados_sinais
            WHERE datetime(encerrado_em) >= datetime(?)
            """,
            (limite_24h,),
        ).fetchone()[0]
        taxa_sem_dado_24h = (
            float(sem_dado_24h) / float(resultados_encerrados_24h)
            if resultados_encerrados_24h else 0.0
        )
        sem_dado_24h_requer_atencao = bool(
            sem_dado_24h >= LIMITE_ABSOLUTO_SEM_DADO_ALERTA_24H
            or (
                sem_dado_24h >= MINIMO_SEM_DADO_ALERTA_24H
                and taxa_sem_dado_24h >= TAXA_SEM_DADO_ALERTA_24H
            )
        )
        limites = obter_limites_risco()
        fingerprint_regra = fingerprint_vinculado_no_banco(
            conexao, VERSAO_REGRAS
        )
        amostra_por_mercado = {}
        pendentes_quantidade = 0
        pendentes_instantes = []
        resultados_24h = 0
        for mercado in MERCADOS_VALIDACAO:
            regra_mercado = versao_regra_para_mercado(mercado)
            fingerprint_mercado = fingerprint_vinculado_no_banco(
                conexao, regra_mercado
            )
            amostra_por_mercado[mercado] = int(conexao.execute(
                """
                SELECT COUNT(DISTINCT s.partida_id)
                FROM sinais s
                JOIN resultados_sinais r ON r.sinal_id=s.id
                WHERE s.status='aprovado' AND s.odd BETWEEN ? AND ?
                  AND s.mercado=? AND s.regra_versao=?
                  AND s.regra_fingerprint=?
                  AND r.resultado IN (
                      'green', 'half_green', 'red', 'half_red'
                  )
                """,
                (
                    limites.odd_minima,
                    limites.odd_maxima,
                    mercado,
                    regra_mercado,
                    fingerprint_mercado or "",
                ),
            ).fetchone()[0] or 0)
            pendencia = conexao.execute(
                """
                SELECT COUNT(*) AS quantidade,
                       MIN(s.criado_em) AS mais_antigo
                FROM sinais s
                LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
                WHERE s.status='aprovado' AND r.sinal_id IS NULL
                  AND s.odd BETWEEN ? AND ?
                  AND s.mercado=? AND s.regra_versao=?
                  AND datetime(s.criado_em) >= datetime(?)
                """,
                (
                    limites.odd_minima,
                    limites.odd_maxima,
                    mercado,
                    regra_mercado,
                    limite_24h,
                ),
            ).fetchone()
            pendentes_quantidade += int(
                pendencia["quantidade"] or 0
            )
            if pendencia["mais_antigo"]:
                pendentes_instantes.append(pendencia["mais_antigo"])
            resultados_24h += int(conexao.execute(
                """
                SELECT COUNT(*)
                FROM resultados_sinais r
                JOIN sinais s ON s.id=r.sinal_id
                WHERE r.resultado IN (
                    'green','half_green','red','half_red'
                )
                  AND s.status='aprovado' AND s.odd BETWEEN ? AND ?
                  AND s.mercado=? AND s.regra_versao=?
                  AND datetime(r.encerrado_em) >= datetime(?)
                """,
                (
                    limites.odd_minima,
                    limites.odd_maxima,
                    mercado,
                    regra_mercado,
                    limite_24h,
                ),
            ).fetchone()[0] or 0)
        sinais_sem_progresso = {
            "quantidade": pendentes_quantidade,
            "mais_antigo": (
                min(pendentes_instantes)
                if pendentes_instantes else None
            ),
        }
        marcar_validacao("consultas_pendencias_e_amostras")
        funil_recente = auditar_funil_recente(
            conexao, agora, versoes_regras_operacionais()
        )
        marcar_validacao("funil_recente")
        inicio_diagnostico_fluxo = (
            agora - timedelta(minutes=60)
        ).isoformat()
        diagnostico_fluxo_sinais = resumir_fluxo_sinais(
            diagnosticar_funil(conexao, inicio_diagnostico_fluxo),
            funil_recente,
        )
        marcar_validacao("diagnostico_fluxo_sinais")
        comparacao_fluxo_sinais = comparar_fluxos_consecutivos(
            conexao, horas=24, agora=agora
        )
        marcar_validacao("comparacao_fluxos_consecutivos")
        comparacao_fluxo_mesmo_horario = comparar_fluxos_mesmo_horario(
            conexao, horas=6, agora=agora
        )
        marcar_validacao("comparacao_fluxos_mesmo_horario")
        features_temporais = auditar_features_temporais(
            conexao, agora, VERSAO_REGRAS
        )
        marcar_validacao("features_temporais")
        incompativeis = 0
        estado_calibracoes = {}
        for item in conexao.execute(
            """
            SELECT mercado, regra_versao, ativa, amostra,
                   atualizado_em, modelo_json
            FROM calibracoes
            WHERE ativa=1
            """
        ).fetchall():
            if item["regra_versao"] != versao_regra_para_mercado(
                item["mercado"]
            ):
                continue
            modelo = json.loads(item["modelo_json"] or "{}")
            compativel = modelo_compativel_com_politica(modelo, limites)
            incompativeis += not compativel
            estado_calibracoes[item["mercado"]] = (
                _resumir_estado_calibracao(item, modelo)
            )
        for item in conexao.execute(
            """
            SELECT mercado, regra_versao, ativa, amostra,
                   atualizado_em, modelo_json
            FROM calibracoes
            WHERE ativa=0
            """,
        ).fetchall():
            if item["regra_versao"] != versao_regra_para_mercado(
                item["mercado"]
            ):
                continue
            modelo = json.loads(item["modelo_json"] or "{}")
            estado_calibracoes[item["mercado"]] = (
                _resumir_estado_calibracao(item, modelo)
            )
        proveniencia_resultados = auditar_proveniencia_resultados(conexao)
        valor_mercado_sinais = auditar_valor_mercado_sinais(conexao)
        regras_ativas_por_mercado = {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in MERCADOS_CALIBRADOS
        }
        diversidade_calibracao = {
            mercado: auditar_diversidade_amostra_calibracao(
                conexao,
                mercado,
                regra_versao,
                limites,
                somente_executaveis=True,
            )
            for mercado, regra_versao in regras_ativas_por_mercado.items()
        }
        frescor_calibracoes = (
            auditar_frescor_calibracoes_por_mercado(
                conexao,
                regras_ativas_por_mercado,
                limites,
                somente_ativas=False,
                politica_versao=POLITICA_CALIBRACAO_VERSAO,
                somente_executaveis=True,
            )
        )
        frescor_calibracoes = _classificar_frescor_calibracoes(
            frescor_calibracoes,
            agora,
            estado_coleta=estado_coleta,
        )
        particoes_calibracao = auditar_particoes_calibracao_por_mercado(
            conexao,
            regras_ativas_por_mercado,
            limites,
            somente_executaveis=True,
        )
        marcar_validacao("calibracao_diversidade_frescor_particoes")
        avaliacao_contexto = avaliar_contexto_avancado(
            conexao,
            regras_ativas_por_mercado,
            limites,
        )
        historico_avaliacao_contexto = (
            auditar_historico_avaliacao_contexto(conexao)
        )
        pontuacao_sombra = avaliar_pontuacao_sombra(
            conexao,
            regras_ativas_por_mercado,
        )
        pontuacao_contexto_sombra = avaliar_pontuacao_contexto_sombra(
            conexao,
            regras_ativas_por_mercado,
        )
        pontuacao_longa_sombra = avaliar_pontuacao_longa_sombra(
            conexao,
            regras_ativas_por_mercado,
        )
        odds_escanteios_periodos = resumir_odds_escanteios_periodos(
            conexao
        )
        integridade_telegram = auditar_integridade_telegram(
            conexao, agora
        )
        integridade_estimativas_historicas = (
            auditar_estimativas_persistidas(conexao)
        )
        notificacoes_operacionais = auditar_notificacoes_operacionais(
            conexao, agora
        )
        marcar_validacao("modelos_sombra_contexto_e_telegram")
        pontuacao_minima_filtro = float(
            os.getenv("PONTUACAO_MINIMA_SINAL_TESTE", "70")
        )
        qualidade_minima_filtro = float(
            os.getenv("QUALIDADE_MINIMA_SINAL_TESTE", "0")
        )
        fingerprint_experimento_filtro = fingerprint_vinculado_no_banco(
            conexao, VERSAO_REGRAS
        )
        experimento_filtro = auditar_experimento_filtro(
            conexao,
            VERSAO_REGRAS,
            pontuacao_minima_filtro,
            qualidade_minima_filtro,
            ativo=os.getenv("SINAIS_TESTE_ATIVO", "0") == "1",
            regra_fingerprint=fingerprint_experimento_filtro,
            exigir_linhagem=True,
        )
        marcar_validacao("experimento_filtro")
        comparacao_filtro_simulacoes = (
            comparar_filtro_simulacoes(
                conexao,
                VERSAO_REGRAS,
                iniciado_em=experimento_filtro.get("iniciado_em"),
                regra_fingerprint=fingerprint_regra,
            )
            if (
                os.getenv("SINAIS_TESTE_ATIVO", "0") == "1"
                and experimento_filtro.get("saudavel")
                and experimento_filtro.get("iniciado_em")
                and fingerprint_regra
            )
            else {
                "iniciado_em": experimento_filtro.get("iniciado_em"),
                "regra_fingerprint": fingerprint_regra,
                "enviadas": {},
                "filtradas": {},
                "comparacao": {},
            }
        )
        regras_filtros_ativas = {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in mercados_calibrados_operacionais()
        }
        comparacao_filtros_regras_ativas = (
            comparar_filtros_por_mercado(
                conexao,
                regras_filtros_ativas,
                fingerprints_por_regra={
                    regra: fingerprint_vinculado_no_banco(conexao, regra)
                    for regra in set(regras_filtros_ativas.values())
                },
            )
            if os.getenv("SINAIS_TESTE_ATIVO", "0") == "1"
            else []
        )
        conclusao_filtro_simulacoes = None
        if (
            os.getenv("SINAIS_TESTE_ATIVO", "0") == "1"
            and experimento_filtro.get("saudavel")
            and fingerprint_experimento_filtro
        ):
            conclusao_filtro_simulacoes = obter_conclusao_experimento_filtro(
                conexao,
                VERSAO_REGRAS,
                pontuacao_minima_filtro,
                qualidade_minima_filtro,
                fingerprint_experimento_filtro,
            )
        experimento_filtro["conclusao"] = conclusao_filtro_simulacoes
        marcar_validacao("comparacoes_filtros")
        drift_simulacoes = avaliar_drift_simulacoes_por_mercado(
            conexao,
            {
                mercado: versao_regra_para_mercado(mercado)
                for mercado in MERCADOS_VALIDACAO
            },
        )
        marcar_validacao("drift_simulacoes")
        # A auditoria completa pode levar vários segundos enquanto o monitor
        # continua gravando o cache em outro processo. Usar o instante capturado
        # no início da supervisão fazia gravações legítimas parecerem vindas do
        # futuro e gerava alertas que se recuperavam no ciclo seguinte.
        cache_api_football = auditar_cache_api_football(
            conexao, datetime.now()
        )
        progresso_calibracao = resumir_progresso_calibracao(
            conexao,
            agora,
            VERSAO_REGRAS,
            usar_versoes_ativas=True,
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
                limites,
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
        hipoteses_sombra = avaliar_hipoteses_sombra_ativas(
            conexao, regras_ativas_por_mercado
        )
        marcar_validacao("cache_progresso_cortes_e_hipoteses")
        definicao_exploracao_gols = (
            auditar_definicao_exploracao_gols(conexao)
        )
        validacao_gols_antecipados = (
            auditar_validacao_gols_antecipados(conexao)
        )
        progresso_gols_antecipados = (
            resumir_validacao_gols_antecipados(conexao)
        )
        try:
            progresso_filtro_gol_ht_preciso = (
                resumir_validacao_filtro_gol_ht_preciso(conexao)
            )
        except (
            OSError, sqlite3.Error, json.JSONDecodeError, ValueError,
            RuntimeError,
        ) as erro:
            progresso_filtro_gol_ht_preciso = {
                "versao": VERSAO_VALIDACAO_FILTRO_GOL_HT_PRECISO,
                "saudavel": False,
                "estado": "auditoria_falhou",
                "decisao": "indisponivel",
                "erro": type(erro).__name__,
                "apto_revisao": False,
                "promocao_automatica": False,
            }
        controle_filtro_gol_ht_preciso = (
            ler_estado_filtro_gol_ht_preciso()
        )
        try:
            progresso_filtro_gol_ft_preciso = (
                resumir_validacao_filtro_gol_ft_preciso(conexao)
            )
        except (
            OSError, sqlite3.Error, json.JSONDecodeError, ValueError,
            RuntimeError,
        ) as erro:
            progresso_filtro_gol_ft_preciso = {
                "versao": VERSAO_VALIDACAO_FILTRO_GOL_FT_PRECISO,
                "saudavel": False,
                "estado": "auditoria_falhou",
                "decisao": "indisponivel",
                "erro": type(erro).__name__,
                "apto_revisao": False,
                "promocao_automatica": False,
            }
        controle_filtro_gol_ft_preciso = (
            ler_estado_filtro_gol_ft_preciso()
        )
        try:
            progresso_quase_gol_ft = resumir_validacao_quase_gol_ft(
                conexao
            )
        except (
            OSError, sqlite3.Error, json.JSONDecodeError, ValueError,
            RuntimeError,
        ) as erro:
            progresso_quase_gol_ft = {
                "versao": VERSAO_VALIDACAO_QUASE_GOL_FT,
                "saudavel": False,
                "estado": "auditoria_falhou",
                "decisao": "indisponivel",
                "erro": type(erro).__name__,
                "apto_revisao": False,
                "promocao_automatica": False,
            }
        try:
            progresso_escanteios_ft_asiatico = (
                resumir_validacao_escanteios_ft_asiatico(conexao)
            )
        except (
            OSError, sqlite3.Error, json.JSONDecodeError, ValueError,
            RuntimeError,
        ) as erro:
            progresso_escanteios_ft_asiatico = {
                "versao": VERSAO_VALIDACAO_ESCANTEIOS_FT_ASIATICO,
                "saudavel": False,
                "estado": "auditoria_falhou",
                "decisao": "indisponivel",
                "erro": type(erro).__name__,
                "apto_revisao": False,
                "promocao_automatica": False,
            }
        try:
            progresso_escanteios_ft_asiatico_legado = (
                resumir_validacao_escanteios_ft_asiatico_legada(conexao)
            )
        except (
            OSError, sqlite3.Error, json.JSONDecodeError, ValueError,
            RuntimeError,
        ) as erro:
            progresso_escanteios_ft_asiatico_legado = {
                "saudavel": False,
                "estado": "auditoria_falhou",
                "erro": type(erro).__name__,
                "entra_na_decisao": False,
            }
        controle_escanteios_ft_asiatico = (
            ler_estado_escanteios_ft_asiatico()
        )
        validacao_gols_capacidade = (
            auditar_validacao_gols_capacidade_times(conexao)
        )
        progresso_gols_capacidade = (
            resumir_validacao_gols_capacidade_times(conexao)
        )
        validacao_gols_capacidade_v2 = (
            auditar_validacao_gols_capacidade_contextual_v2(conexao)
        )
        progresso_gols_capacidade_v2 = (
            resumir_validacao_gols_capacidade_contextual_v2(conexao)
        )
        validacao_grupo_gol_ft_capacidade_v2 = (
            auditar_grupo_ft_capacidade_contextual_v2(conexao)
        )
        progresso_grupo_gol_ft_capacidade_v2 = (
            resumir_grupo_ft_capacidade_contextual_v2(conexao)
        )
        progresso_gol_ht_00_min20 = (
            resumir_validacao_gol_ht_00_min20(conexao)
        )
        validacao_gol_ft_reforcado = (
            auditar_validacao_gol_ft_reforcado(conexao)
        )
        progresso_gol_ft_reforcado = (
            resumir_validacao_gol_ft_reforcado(conexao)
        )
        validacao_gol_ht_protegido = (
            auditar_validacao_gol_ht_protegido(conexao)
        )
        progresso_gol_ht_protegido = (
            resumir_validacao_gol_ht_protegido(conexao)
        )
        progresso_proximo_gol_balanceado = (
            resumir_validacao_proximo_gol_balanceado(conexao)
        )
        progresso_quase_proximo_gol = (
            resumir_validacao_quase_proximo_gol(conexao)
        )
        controle_proximo_gol_balanceado = (
            ler_estado_proximo_gol_balanceado()
        )
        progresso_proximo_gol_balanceado["grupo_liberado"] = bool(
            controle_proximo_gol_balanceado.get("saudavel")
            and controle_proximo_gol_balanceado.get("ativo")
        )
        progresso_proximo_gol_balanceado["circuit_breaker"] = {
            "versao": controle_proximo_gol_balanceado.get("versao"),
            "estado": controle_proximo_gol_balanceado.get("estado"),
            "ativo": controle_proximo_gol_balanceado.get("ativo"),
            "motivo": controle_proximo_gol_balanceado.get("motivo"),
            "atualizado_em": controle_proximo_gol_balanceado.get(
                "atualizado_em"
            ),
            "reativacao": controle_proximo_gol_balanceado.get("reativacao"),
        }
        exploracao_sombra = resumir_exploracoes_sombra(conexao)
        marcar_validacao("validacoes_e_exploracoes_gols")
        linhagens_por_regra = {
            regra_ativa: auditar_linhagem_regra(
                conexao,
                PASTA,
                regra_ativa,
                VERSAO_FEATURES,
            )
            for regra_ativa in sorted(set(
                regras_ativas_por_mercado.values()
            ))
        }
        linhagem_regra = linhagens_por_regra[VERSAO_REGRAS]
        cobertura_linhagem_sinais = resumir_cobertura_linhagem_sinais(
            conexao, VERSAO_REGRAS
        )
        coberturas_por_regra = {
            VERSAO_REGRAS: cobertura_linhagem_sinais,
        }
        for regra_mercado in set(regras_ativas_por_mercado.values()):
            if regra_mercado not in coberturas_por_regra:
                coberturas_por_regra[regra_mercado] = (
                    resumir_cobertura_linhagem_sinais(
                        conexao, regra_mercado
                    )
                )
        conformidade_regras_operacionais = {
            "proximo_gol": auditar_regra_proximo_gol(conexao),
        }
        marcar_validacao("linhagem_regras")
        auditoria_ligas_sombra = auditar_ligas_por_mercado(
            conexao,
            regras_ativas_por_mercado,
            fingerprints_por_regra={
                regra: fingerprint_vinculado_no_banco(conexao, regra)
                for regra in set(regras_ativas_por_mercado.values())
            },
            metodos_grupo={
                "gol_ft_v2b": {
                    "mercado": "gol_ft",
                    "versao_exploracao": (
                        VERSAO_GOL_FT_CAPACIDADE_V2
                    ),
                    "inicio": (
                        progresso_grupo_gol_ft_capacidade_v2 or {}
                    ).get("registrado_em"),
                    "linhagem": (
                        progresso_grupo_gol_ft_capacidade_v2 or {}
                    ).get("linhagem_sha256"),
                },
            },
        )
        marcar_validacao("auditoria_ligas")
    except (
        OSError, sqlite3.Error, json.JSONDecodeError, ValueError, RuntimeError
    ) as erro:
        return {
            "saudavel": False,
            "requer_atencao": True,
            "motivos": ["auditoria_validacao_falhou"],
            "avisos": [],
            "erro": type(erro).__name__,
        }
    finally:
        if "conexao" in locals():
            conexao.close()

    quantidade_pendente = int(sinais_sem_progresso["quantidade"] or 0)
    mais_antigo = sinais_sem_progresso["mais_antigo"]
    estagnada = bool(
        quantidade_pendente >= 5
        and int(resultados_24h or 0) == 0
        and mais_antigo
        and mais_antigo <= limite_estagnacao
    )
    motivos = []
    avisos = []
    if pendencias_vencidas:
        motivos.append("pendencias_acima_180_minutos")
    if incompativeis:
        motivos.append("calibracao_ativa_incompativel")
    if not proveniencia_resultados["saudavel"]:
        motivos.append("proveniencia_resultados_inconsistente")
    if valor_mercado_sinais.get("entregues_oficiais_sem_valor"):
        motivos.append("entrega_oficial_sem_valor_conservador")
    if valor_mercado_sinais.get("entregues_oficiais_rastro_invalido"):
        motivos.append("entrega_oficial_rastro_valor_invalido")
    desatualizadas_ativas = frescor_calibracoes.get(
        "desatualizadas_ativas_alertaveis"
    )
    desatualizadas_inativas = frescor_calibracoes.get(
        "desatualizadas_inativas_alertaveis"
    )
    if (
        desatualizadas_ativas is None
        and desatualizadas_inativas is None
        and not frescor_calibracoes["saudavel"]
    ):
        desatualizadas_ativas = frescor_calibracoes.get(
            "desatualizadas", 0
        )
    if desatualizadas_ativas:
        motivos.append("calibracao_ativa_desatualizada")
    if desatualizadas_inativas:
        motivos.append("calibracao_inativa_desatualizada")
    if not particoes_calibracao["saudavel"]:
        motivos.append("particao_temporal_calibracao_inconsistente")
    if not pontuacao_sombra["integro"]:
        avisos.append("pontuacao_sombra_inconsistente")
    if not pontuacao_contexto_sombra["integro"]:
        avisos.append("pontuacao_contexto_sombra_inconsistente")
    if not pontuacao_longa_sombra["integro"]:
        avisos.append("pontuacao_longa_sombra_inconsistente")
    if not historico_avaliacao_contexto["saudavel"]:
        avisos.append("historico_avaliacao_contexto_inconsistente")
    if estagnada:
        motivos.append("amostra_estagnada")
    if not features_temporais["saudavel"]:
        motivos.append("features_temporais_invalidas")
    if not integridade_telegram.get(
        "saudavel_operacional", integridade_telegram["saudavel"]
    ):
        motivos.append("integridade_telegram_inconsistente")
    if not integridade_estimativas_historicas.get("saudavel"):
        motivos.append("estimativa_historica_executavel_inconsistente")
    if not notificacoes_operacionais["saudavel"]:
        motivos.append("notificacoes_operacionais_inconsistentes")
    if not experimento_filtro["saudavel"]:
        motivos.append("experimento_filtro_inconsistente")
    integridade_hipoteses = hipoteses_sombra.get("integridade") or {}
    if not integridade_hipoteses.get("saudavel"):
        motivos.append("hipoteses_sombra_inconsistentes")
    if not definicao_exploracao_gols.get("saudavel"):
        motivos.append("definicao_exploracao_gols_inconsistente")
    if not validacao_gols_antecipados.get("saudavel"):
        motivos.append("validacao_gols_antecipados_inconsistente")
    if not progresso_filtro_gol_ht_preciso.get("saudavel"):
        motivos.append("validacao_filtro_gol_ht_preciso_inconsistente")
    if not controle_filtro_gol_ht_preciso.get("saudavel"):
        motivos.append("controle_filtro_gol_ht_preciso_inconsistente")
    if not progresso_filtro_gol_ft_preciso.get("saudavel"):
        motivos.append("validacao_filtro_gol_ft_preciso_inconsistente")
    if not controle_filtro_gol_ft_preciso.get("saudavel"):
        motivos.append("controle_filtro_gol_ft_preciso_inconsistente")
    if not progresso_quase_gol_ft.get("saudavel"):
        motivos.append("validacao_quase_gol_ft_inconsistente")
    if not progresso_escanteios_ft_asiatico.get("saudavel"):
        motivos.append("validacao_escanteios_ft_asiatico_inconsistente")
    if not progresso_escanteios_ft_asiatico_legado.get("saudavel"):
        avisos.append("validacao_escanteios_ft_asiatico_legada_inconsistente")
    if not controle_escanteios_ft_asiatico.get("saudavel"):
        motivos.append("controle_escanteios_ft_asiatico_inconsistente")
    if not validacao_gols_capacidade.get("saudavel"):
        motivos.append("validacao_gols_capacidade_inconsistente")
    if not validacao_gols_capacidade_v2.get("saudavel"):
        motivos.append("validacao_gols_capacidade_v2_inconsistente")
    if not validacao_grupo_gol_ft_capacidade_v2.get("saudavel"):
        motivos.append("validacao_grupo_gol_ft_capacidade_v2_inconsistente")
    if not validacao_gol_ft_reforcado.get("saudavel"):
        motivos.append("validacao_gol_ft_reforcado_inconsistente")
    if not validacao_gol_ht_protegido.get("saudavel"):
        motivos.append("validacao_gol_ht_protegido_inconsistente")
    if not controle_proximo_gol_balanceado.get("saudavel"):
        motivos.append("controle_proximo_gol_balanceado_inconsistente")
    if progresso_grupo_gol_ft_capacidade_v2.get(
        "alerta_desfavoravel"
    ):
        avisos.append("gol_ft_capacidade_v2_grupo_evidencia_desfavoravel")
    if any(
        item.get("alerta_desfavoravel") is True
        for item in (
            progresso_gols_capacidade.get("por_braco") or {}
        ).values()
    ):
        avisos.append("gols_capacidade_evidencia_desfavoravel")
    if not cache_api_football["saudavel"]:
        motivos.append("cache_api_football_inconsistente")
    linhagens_invalidas = [
        regra for regra, item in linhagens_por_regra.items()
        if not item["saudavel"] and item["estado"] != "nao_registrada"
    ]
    if linhagens_invalidas:
        motivos.append("linhagem_regra_inconsistente")
    coberturas_invalidas = [
        regra for regra, cobertura in coberturas_por_regra.items()
        if linhagens_por_regra[regra]["estado"] != "nao_registrada"
        and not cobertura["saudavel"]
    ]
    if coberturas_invalidas:
        motivos.append("sinais_sem_linhagem_valida")
    regras_operacionais_invalidas = [
        mercado
        for mercado, auditoria in (
            conformidade_regras_operacionais.items()
        )
        if not auditoria.get("saudavel")
    ]
    if regras_operacionais_invalidas:
        motivos.append("regra_operacional_inconsistente")
    if sem_dado_24h_requer_atencao:
        avisos.append("resultados_sem_dado_24h")
    if (
        features_temporais["estado"] == "aguardando_primeiro_registro"
        and features_temporais["snapshots"] >= AMOSTRA_MINIMA_FEATURES
    ):
        avisos.append("features_temporais_ainda_nao_iniciadas")
    if funil_recente["estado"] == "avaliavel":
        cobertura_candidatos = funil_recente["cobertura_candidatos"]
        cobertura_odds = funil_recente["cobertura_odds_estruturadas"]
        if cobertura_candidatos < COBERTURA_MINIMA_CANDIDATOS:
            motivos.append("candidatos_ausentes_em_snapshots_recentes")
        elif cobertura_odds < COBERTURA_MINIMA_ODDS:
            avisos.append("cobertura_odds_estruturadas_baixa")
    contador_api = verificar_contador_uso(
        caminho_banco.parent / "api_football_uso.json", agora
    )
    limites_api = obter_limites_api()
    limite_api_seguro = max(
        limites_api.limite_diario - limites_api.reserva_diaria, 0
    )
    cota_provedor = contador_api.get("provedor") or {}
    if cota_provedor.get("dia") == contador_api.get("dia"):
        limite_api_seguro = min(
            limite_api_seguro,
            max(
                int(cota_provedor.get("limite_diario", 0))
                - limites_api.reserva_diaria,
                0,
            ),
        )
    consumo_api = contador_api.get("consumo_dia")
    contador_api["limite_diario_plano"] = limites_api.limite_diario
    contador_api["limite_diario_seguro"] = limite_api_seguro
    contador_api["reserva_diaria"] = limites_api.reserva_diaria
    contador_api["limite_confirmado_provedor"] = (
        cota_provedor.get("limite_diario")
    )
    contador_api["restante_informado_provedor"] = (
        cota_provedor.get("restante_diario")
    )
    contador_api["cota_provedor_dia"] = cota_provedor.get("dia")
    contador_api["cota_provedor_vigente"] = bool(
        cota_provedor.get("dia")
        and cota_provedor.get("dia") == contador_api.get("dia")
    )
    contador_api["cota_observada_em"] = cota_provedor.get("observado_em")
    contador_api["restante_seguro_dia"] = (
        max(limite_api_seguro - int(consumo_api), 0)
        if consumo_api is not None else None
    )
    contador_api["percentual_limite_seguro"] = (
        round(int(consumo_api) / limite_api_seguro * 100, 2)
        if consumo_api is not None and limite_api_seguro else None
    )
    if not contador_api["saudavel"]:
        motivos.append("contador_api_inseguro")
    elif contador_api["requer_atencao"]:
        avisos.append("contador_api_recuperavel_por_backup")
    estado_odds_api = verificar_estado_odds_api(
        caminho_banco.parent / "api_football_odds_estado.json"
    )
    if not estado_odds_api["saudavel"]:
        avisos.append("estado_odds_api_corrompido")
    catalogo_odds_live = verificar_catalogo_odds_live(
        caminho_banco.parent / "api_football_catalogo_odds_estado.json"
    )
    if catalogo_odds_live.get("estado") in {
        "corrompido", "desatualizado", "incoerente",
    }:
        avisos.append(
            catalogo_odds_live.get("motivo")
            or "catalogo_odds_live_inconsistente"
        )
    amostra_oficial_id = "|".join((
        VERSAO_REGRAS,
        POLITICA_CALIBRACAO_VERSAO,
        fingerprint_regra or "sem_fingerprint",
        cobertura_linhagem_sinais.get("iniciado_em") or "sem_marco",
    ))
    amostra_populacao_id_por_mercado = {}
    for mercado, regra_mercado in regras_ativas_por_mercado.items():
        cobertura_regra = coberturas_por_regra[regra_mercado]
        amostra_populacao_id_por_mercado[mercado] = "|".join((
            regra_mercado,
            cobertura_regra.get("fingerprint") or "sem_fingerprint",
            cobertura_regra.get("iniciado_em") or "sem_marco",
        ))
    amostra_populacao_id = "|".join((
        VERSAO_REGRAS,
        fingerprint_regra or "sem_fingerprint",
        cobertura_linhagem_sinais.get("iniciado_em") or "sem_marco",
    ))
    marcar_validacao("consolidacao_e_arquivos_api")
    return {
        "saudavel": not motivos,
        "requer_atencao": bool(motivos or avisos),
        "motivos": motivos,
        "avisos": avisos,
        "pendencias_vencidas": int(pendencias_vencidas or 0),
        "detalhes_pendencias_vencidas": detalhes_pendencias_vencidas,
        "pendencias_finais_incompletas_aguardando": int(
            pendencias_finais_incompletas_aguardando or 0
        ),
        "pendencias_longas_ativas": int(pendencias_longas_ativas or 0),
        "sem_dado_24h": int(sem_dado_24h or 0),
        "resultados_encerrados_24h": int(
            resultados_encerrados_24h or 0
        ),
        "taxa_sem_dado_24h": round(taxa_sem_dado_24h, 4),
        "sem_dado_24h_requer_atencao": sem_dado_24h_requer_atencao,
        "politica_sem_dado_24h": {
            "minimo": MINIMO_SEM_DADO_ALERTA_24H,
            "taxa_minima": TAXA_SEM_DADO_ALERTA_24H,
            "limite_absoluto": LIMITE_ABSOLUTO_SEM_DADO_ALERTA_24H,
        },
        "calibracoes_ativas_incompativeis": int(incompativeis),
        "estado_calibracoes": estado_calibracoes,
        "diversidade_calibracao": diversidade_calibracao,
        "proveniencia_resultados": proveniencia_resultados,
        "valor_mercado_sinais": valor_mercado_sinais,
        "frescor_calibracoes": frescor_calibracoes,
        "particoes_calibracao": particoes_calibracao,
        "avaliacao_contexto": avaliacao_contexto,
        "historico_avaliacao_contexto": historico_avaliacao_contexto,
        "pontuacao_sombra": pontuacao_sombra,
        "pontuacao_contexto_sombra": pontuacao_contexto_sombra,
        "pontuacao_longa_sombra": pontuacao_longa_sombra,
        "amostra_estagnada": estagnada,
        "amostra_por_mercado": amostra_por_mercado,
        "progresso_calibracao": progresso_calibracao,
        "conformidade_regras_operacionais": (
            conformidade_regras_operacionais
        ),
        "auditoria_ligas_sombra": auditoria_ligas_sombra,
        "cortes_sombra": cortes_sombra,
        "hipoteses_sombra": hipoteses_sombra,
        "definicao_exploracao_gols": definicao_exploracao_gols,
        "validacao_gols_antecipados": validacao_gols_antecipados,
        "progresso_gols_antecipados": progresso_gols_antecipados,
        "progresso_filtro_gol_ht_preciso": (
            progresso_filtro_gol_ht_preciso
        ),
        "controle_operacional_filtro_gol_ht_preciso": (
            controle_filtro_gol_ht_preciso
        ),
        "progresso_filtro_gol_ft_preciso": (
            progresso_filtro_gol_ft_preciso
        ),
        "controle_operacional_filtro_gol_ft_preciso": (
            controle_filtro_gol_ft_preciso
        ),
        "progresso_quase_candidatos_gol_ft": progresso_quase_gol_ft,
        "progresso_escanteios_ft_asiatico": (
            progresso_escanteios_ft_asiatico
        ),
        "progresso_escanteios_ft_asiatico_legado_v2": (
            progresso_escanteios_ft_asiatico_legado
        ),
        "controle_operacional_escanteios_ft_asiatico": (
            controle_escanteios_ft_asiatico
        ),
        "validacao_gols_capacidade": validacao_gols_capacidade,
        "progresso_gols_capacidade": progresso_gols_capacidade,
        "validacao_gols_capacidade_v2": validacao_gols_capacidade_v2,
        "progresso_gols_capacidade_v2": progresso_gols_capacidade_v2,
        "validacao_grupo_gol_ft_capacidade_v2": (
            validacao_grupo_gol_ft_capacidade_v2
        ),
        "progresso_grupo_gol_ft_capacidade_v2": (
            progresso_grupo_gol_ft_capacidade_v2
        ),
        "progresso_gol_ht_00_min20": progresso_gol_ht_00_min20,
        "validacao_gol_ft_reforcado": validacao_gol_ft_reforcado,
        "progresso_gol_ft_reforcado": progresso_gol_ft_reforcado,
        "validacao_gol_ht_protegido": validacao_gol_ht_protegido,
        "progresso_gol_ht_protegido": progresso_gol_ht_protegido,
        "progresso_proximo_gol_balanceado_sombra": (
            progresso_proximo_gol_balanceado
        ),
        "progresso_quase_candidatos_proximo_gol": (
            progresso_quase_proximo_gol
        ),
        "controle_operacional_proximo_gol_balanceado": (
            controle_proximo_gol_balanceado
        ),
        "exploracao_sombra": exploracao_sombra,
        "funil_recente": funil_recente,
        "diagnostico_fluxo_sinais": diagnostico_fluxo_sinais,
        "comparacao_fluxo_sinais": comparacao_fluxo_sinais,
        "comparacao_fluxo_mesmo_horario": (
            comparacao_fluxo_mesmo_horario
        ),
        "features_temporais": features_temporais,
        "odds_escanteios_periodos": odds_escanteios_periodos,
        "integridade_telegram": integridade_telegram,
        "integridade_estimativas_historicas": (
            integridade_estimativas_historicas
        ),
        "notificacoes_operacionais": notificacoes_operacionais,
        "experimento_filtro": experimento_filtro,
        "comparacao_filtro_simulacoes": comparacao_filtro_simulacoes,
        "comparacao_filtros_regras_ativas": (
            comparacao_filtros_regras_ativas
        ),
        "conclusao_filtro_simulacoes": conclusao_filtro_simulacoes,
        "drift_simulacoes": drift_simulacoes,
        "cache_api_football": cache_api_football,
        "contador_api": contador_api,
        "estado_odds_api": estado_odds_api,
        "catalogo_odds_live": catalogo_odds_live,
        "linhagem_regra": linhagem_regra,
        "linhagens_por_regra": linhagens_por_regra,
        "linhagens_invalidas": linhagens_invalidas,
        "coberturas_linhagem_invalidas": coberturas_invalidas,
        "cobertura_linhagem_sinais": cobertura_linhagem_sinais,
        "amostra_oficial_id": amostra_oficial_id,
        "amostra_populacao_id": amostra_populacao_id,
        "amostra_populacao_id_por_mercado": (
            amostra_populacao_id_por_mercado
        ),
        "politica_calibracao": POLITICA_CALIBRACAO_VERSAO,
        "regra_versao": VERSAO_REGRAS,
        "regra_versoes_por_mercado": {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in MERCADOS_VALIDACAO
        },
        "observabilidade_validacao": {
            "fases_segundos": dict(duracoes_validacao),
            "duracao_total_segundos": round(
                time.monotonic() - inicio_validacao, 3
            ),
        },
    }


def tentar_reiniciar_processo(
    estado_coleta,
    estado_processo,
    estado_watchdog,
    agora=None,
    iniciar=None,
    verificar_instancia=None,
):
    agora = agora or datetime.now()
    status = estado_processo.get("status")
    if status not in (
        None, "iniciando", "ativo", "falha", "reinicio_pendente"
    ):
        return None
    verificar_instancia = verificar_instancia or (
        lambda: trava_em_uso(PASTA / "monitor_instancia.lock")
    )
    if verificar_instancia():
        return None
    # A trava exclusiva e a evidencia autoritativa da instancia. Se o estado
    # ainda diz ativo/falha, mas a trava ja esta livre, o processo terminou e
    # nao e necessario esperar o ultimo ciclo ficar cinco minutos atrasado.
    if status in (None, "iniciando"):
        if estado_coleta.get("saudavel"):
            return None
        if status == "iniciando":
            try:
                inicio = datetime.fromisoformat(
                    estado_processo.get("atualizado_em")
                )
                if (agora - inicio).total_seconds() < 60:
                    return None
            except (TypeError, ValueError):
                pass
    ultimo = estado_watchdog.get("ultimo_reinicio_em")
    # Uma saida deliberada no limite do ciclo nao e uma falha oscilante. O
    # hash novo ja esta estavel no disco e a trava livre prova que a instancia
    # antiga terminou; aguardar o cooldown deixaria sinais fechados por cinco
    # minutos sem trazer seguranca adicional.
    if ultimo and status != "reinicio_pendente":
        try:
            if (
                agora - datetime.fromisoformat(ultimo)
            ).total_seconds() < INTERVALO_REINICIO_SEGUNDOS:
                return None
        except ValueError:
            pass
    iniciar = iniciar or (lambda: iniciar_monitor(PASTA))
    novo_pid = iniciar()
    resultado = {
        "novo_pid": novo_pid,
        "motivo_reinicio": (
            "processo_falhou"
            if status == "falha"
            else (
                "codigo_runtime_atualizado"
                if status == "reinicio_pendente"
                else (
                    "inicializacao_interrompida"
                    if status == "iniciando"
                    else (
                        "estado_processo_ausente"
                        if status is None
                        else "instancia_ausente"
                    )
                )
            )
        ),
        "ultimo_reinicio_em": agora.replace(microsecond=0).isoformat(),
    }
    if status == "falha" and (
        estado_processo.get("erro") or estado_processo.get("mensagem")
    ):
        resultado["causa_fatal"] = {
            "erro": resumir_erro_seguro(
                estado_processo.get("erro") or "erro_desconhecido",
                limite=100,
            ),
            "mensagem": resumir_erro_seguro(
                estado_processo.get("mensagem") or "sem detalhe",
                limite=500,
            ),
            "registrado_em": estado_processo.get("atualizado_em"),
        }
    return resultado


def formatar_alerta_reinicio_monitor(reinicio):
    texto = (
        "🔄 Monitor PackBall reiniciado automaticamente após "
        "detecção de processo encerrado."
    )
    causa = (reinicio or {}).get("causa_fatal") or {}
    if not causa:
        return texto
    linhas = [
        texto,
        "",
        f"Causa: {causa.get('erro') or 'erro desconhecido'}",
        f"Detalhe: {causa.get('mensagem') or 'sem detalhe'}",
    ]
    if causa.get("registrado_em"):
        linhas.append(f"Registrada em: {causa['registrado_em']}")
    return "\n".join(linhas)


def _assinatura_alerta_reinicio_monitor(reinicio):
    dados = {
        "ultimo_reinicio_em": (reinicio or {}).get("ultimo_reinicio_em"),
        "motivo_reinicio": (reinicio or {}).get("motivo_reinicio"),
        "causa_fatal": (reinicio or {}).get("causa_fatal") or {},
    }
    return hashlib.sha256(json.dumps(
        dados,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _reunir_alertas_reinicio_pendentes(estado, anterior, reinicio=None):
    pendentes = []
    assinaturas = set()

    def adicionar(item):
        if not isinstance(item, dict) or not item:
            return
        assinatura = _assinatura_alerta_reinicio_monitor(item)
        if assinatura in assinaturas:
            return
        assinaturas.add(assinatura)
        pendentes.append(dict(item))

    for origem in (anterior or {}, estado or {}):
        fila = origem.get("alertas_reinicio_pendentes") or []
        if isinstance(fila, list):
            for item in fila:
                adicionar(item)
        adicionar(origem.get("alerta_reinicio_pendente"))
    adicionar(reinicio)
    return pendentes


def atualizar_alerta_reinicio_monitor(
    estado, anterior=None, reinicio=None, enviar=None, agora=None,
    caminho_banco=None,
):
    """Mantem cada aviso de reinicio pendente ate a entrega confirmada."""
    anterior = anterior or {}
    pendentes = _reunir_alertas_reinicio_pendentes(
        estado, anterior, reinicio=reinicio
    )
    if not pendentes:
        estado.pop("alerta_reinicio_pendente", None)
        estado.pop("alertas_reinicio_pendentes", None)
        return estado
    restantes = []
    for pendente in pendentes:
        assinatura = _assinatura_alerta_reinicio_monitor(pendente)
        texto = formatar_alerta_reinicio_monitor(pendente)
        try:
            if enviar is None:
                entregue = enviar_alerta(
                    texto,
                    caminho_banco=caminho_banco,
                    agora=agora,
                    chave_evento=f"watchdog:reinicio:{assinatura}",
                    deduplicacao_minutos=None,
                    max_tentativas=None,
                )
            else:
                entregue = enviar(texto)
        except Exception:
            entregue = False
        if not entregue:
            restantes.append(pendente)
    if restantes:
        estado["alertas_reinicio_pendentes"] = restantes
        # Mantem a chave singular para leitores de estado legados.
        estado["alerta_reinicio_pendente"] = dict(restantes[0])
    else:
        estado.pop("alerta_reinicio_pendente", None)
        estado.pop("alertas_reinicio_pendentes", None)
    return estado


def _identificador_incidente_saude_monitor(estado, anterior, agora):
    existente = (
        estado.get("alerta_saude_incidente_id")
        or anterior.get("alerta_saude_incidente_id")
    )
    if existente:
        return str(existente)
    # Estados anteriores a esta fila nao possuem um identificador. Quando ja
    # havia alerta entregue, a assinatura precisa ser deterministica para que
    # uma falha posterior de persistencia nao duplique a recuperacao.
    legado = bool(anterior.get("alertado"))
    origem = anterior if legado else estado
    dados = {
        "motivo": origem.get("motivo") or anterior.get("motivo"),
        "ultimo_sucesso_em": (
            origem.get("ultimo_sucesso_em")
            or anterior.get("ultimo_sucesso_em")
        ),
        "inicio": None if legado else agora.isoformat(),
        "legado": legado,
    }
    return hashlib.sha256(json.dumps(
        dados,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def atualizar_alerta_saude_monitor(
    estado, anterior=None, tolerancia_inicial=False, enviar=None,
    agora=None, caminho_banco=None,
):
    """So encerra um incidente depois de confirmar sua recuperacao."""
    anterior = anterior or {}
    agora = (agora or datetime.now()).replace(microsecond=0)

    def enviar_evento(texto, tipo, incidente_id):
        try:
            if enviar is not None:
                return bool(enviar(texto))
            return bool(enviar_alerta(
                texto,
                caminho_banco=caminho_banco,
                agora=agora,
                chave_evento=(
                    f"watchdog:saude:{tipo}:{incidente_id}"
                ),
                deduplicacao_minutos=None,
                max_tentativas=None,
            ))
        except Exception:
            return False

    if (
        not estado.get("saudavel")
        and not tolerancia_inicial
        and not anterior.get("alertado")
    ):
        incidente_id = _identificador_incidente_saude_monitor(
            estado, anterior, agora
        )
        estado["alerta_saude_incidente_id"] = incidente_id
        entregue = enviar_evento(
            "🚨 ALERTA DO MONITOR PACKBALL\n\n"
            "A coleta está parada ou sem atualização há mais de 5 minutos.\n"
            f"Motivo técnico: {estado.get('motivo')}\n"
            "Verifique o computador, a internet e o navegador.",
            "indisponivel",
            incidente_id,
        )
        estado["alertado"] = bool(entregue)
    elif estado.get("saudavel") and anterior.get("alertado"):
        incidente_id = _identificador_incidente_saude_monitor(
            estado, anterior, agora
        )
        estado["alerta_saude_incidente_id"] = incidente_id
        entregue = enviar_evento(
            "✅ Monitor PackBall recuperado e coleta atualizada novamente.",
            "recuperado",
            incidente_id,
        )
        estado["alertado"] = not bool(entregue)
        if entregue:
            estado.pop("alerta_saude_incidente_id", None)
    else:
        estado["alertado"] = bool(anterior.get("alertado", False))
        incidente_id = anterior.get("alerta_saude_incidente_id")
        if estado.get("saudavel"):
            # Se a indisponibilidade nunca chegou a ser entregue, nao existe
            # recuperacao a anunciar. Encerra o incidente para que uma queda
            # futura receba uma chave nova em vez de herdar o retry antigo.
            estado.pop("alerta_saude_incidente_id", None)
        elif incidente_id:
            estado["alerta_saude_incidente_id"] = incidente_id
    return estado


def monitor_em_inicializacao(
    estado_coleta,
    estado_processo,
    agora=None,
    verificar_pid=None,
    verificar_instancia=None,
    tolerancia_segundos=300,
):
    if estado_coleta.get("saudavel"):
        return False
    status = estado_processo.get("status")
    if status not in ("iniciando", "ativo"):
        return False
    iniciado_em = estado_processo.get("atualizado_em")
    if not iniciado_em:
        return False
    agora = agora or datetime.now()
    try:
        inicio = datetime.fromisoformat(iniciado_em)
    except (TypeError, ValueError):
        return False
    idade = max((agora - inicio).total_seconds(), 0)
    if idade > tolerancia_segundos:
        return False
    if status == "iniciando":
        # Entre o Popen do iniciador e a aquisicao da trava pelo processo
        # filho existe uma janela curta em que o ciclo anterior ja parece
        # vencido. Ela faz parte da partida normal e nao e uma parada.
        return idade < 60
    verificar_pid = verificar_pid or pid_ativo
    verificar_instancia = verificar_instancia or (
        lambda: trava_em_uso(PASTA / "monitor_instancia.lock")
    )
    if not verificar_instancia():
        return False
    if not verificar_pid(estado_processo.get("pid")):
        return False
    ultimo_sucesso = estado_coleta.get("ultimo_sucesso_em")
    if ultimo_sucesso:
        try:
            if datetime.fromisoformat(ultimo_sucesso) >= inicio:
                return False
        except (TypeError, ValueError):
            pass
    return True


def verificar_trabalhador_acompanhamento_odd(
    caminho,
    *,
    agora=None,
    ativo=None,
    monitor_inicializando=False,
):
    """Audita a cadencia da thread sem transformar oscilacao em Telegram."""
    if ativo is None:
        ativo = str(os.getenv(
            "ACOMPANHAMENTO_ODD_WORKER_DEDICADO_ATIVO", "1"
        )).strip().casefold() in {"1", "true", "sim", "yes", "on"}
    if not ativo:
        return {
            "saudavel": True,
            "estado": "desativado",
            "motivo": None,
            "aplicacao_sinais": False,
        }
    agora = agora or datetime.now()
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        atualizado = datetime.fromisoformat(str(dados["atualizado_em"]))
        intervalo = max(float(
            dados.get("intervalo_alvo_segundos") or 15.0
        ), 1.0)
    except (
        OSError, KeyError, TypeError, ValueError, json.JSONDecodeError,
    ):
        return {
            "saudavel": bool(monitor_inicializando),
            "estado": (
                "inicializando" if monitor_inicializando
                else "estado_ausente_ou_invalido"
            ),
            "motivo": (
                None if monitor_inicializando
                else "trabalhador_acompanhamento_odd_sem_estado"
            ),
            "aplicacao_sinais": False,
        }
    if atualizado.tzinfo is not None:
        atualizado = atualizado.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = max((agora - atualizado).total_seconds(), 0.0)
    limite = max(intervalo * 4.0, 90.0)
    status = str(dados.get("status") or "indeterminado")
    try:
        falhas = max(int(dados.get("falhas_consecutivas") or 0), 0)
    except (TypeError, ValueError):
        falhas = 0
    def inteiro_nao_negativo(chave, padrao=0):
        try:
            return max(int(dados.get(chave, padrao)), 0)
        except (TypeError, ValueError):
            return max(int(padrao), 0)

    clv_informado = "clv_pos_alerta_versao" in dados
    clv_versao = dados.get("clv_pos_alerta_versao")
    clv_candidatos = inteiro_nao_negativo("clv_pos_alerta_candidatos")
    clv_consultados = inteiro_nao_negativo("clv_pos_alerta_consultados")
    clv_com_oferta = inteiro_nao_negativo(
        "clv_pos_alerta_com_oferta_exata"
    )
    clv_sem_oferta = inteiro_nao_negativo(
        "clv_pos_alerta_sem_oferta_exata"
    )
    clv_somente_estado = inteiro_nao_negativo(
        "clv_pos_alerta_somente_estado"
    )
    clv_persistidos = inteiro_nao_negativo(
        "clv_pos_alerta_estados_persistidos"
    )
    clv_falhas = inteiro_nao_negativo("clv_pos_alerta_falhas")
    clv_falhas_consecutivas = inteiro_nao_negativo(
        "clv_pos_alerta_falhas_consecutivas"
    )
    clv_aplicacao_sinais = bool(
        dados.get("clv_pos_alerta_aplicacao_sinais")
    )
    clv_telegram = bool(dados.get("clv_pos_alerta_telegram"))
    clv_mercados_api = dados.get(
        "clv_pos_alerta_mercados_api_rapida"
    )
    clv_mercados_snapshot = dados.get(
        "clv_pos_alerta_mercados_somente_snapshot"
    )
    cobertura_clv_v2 = bool(
        isinstance(clv_mercados_api, list)
        and isinstance(clv_mercados_snapshot, list)
        and set(clv_mercados_api) == set(MERCADOS_CLV_API_RAPIDA)
        and len(clv_mercados_api) == len(set(clv_mercados_api))
        and set(clv_mercados_snapshot)
        == set(MERCADOS_CLV_SOMENTE_SNAPSHOT)
        and len(clv_mercados_snapshot) == len(set(clv_mercados_snapshot))
        and not set(clv_mercados_api) & set(clv_mercados_snapshot)
    )
    integridade_clv = bool(
        not clv_informado
        or (
            clv_versao in {
                "coleta-clv-pos-alerta-api-rapida-v1",
                "coleta-clv-pos-alerta-api-rapida-v2",
                "coleta-clv-pos-alerta-api-rapida-v3",
                "coleta-clv-pos-alerta-api-rapida-v4",
                VERSAO_COLETA_CLV_API_RAPIDA,
            }
            and (
                clv_versao == "coleta-clv-pos-alerta-api-rapida-v1"
                or cobertura_clv_v2
            )
            and clv_consultados <= clv_candidatos
            and clv_com_oferta <= clv_consultados
            and clv_sem_oferta <= clv_consultados
            and clv_com_oferta + clv_sem_oferta == clv_consultados
            and clv_somente_estado <= clv_sem_oferta
            and clv_persistidos <= clv_consultados
            and not clv_aplicacao_sinais
            and not clv_telegram
        )
    )

    lote = max(inteiro_nao_negativo("lote_maximo", 10), 1)
    fila_total = inteiro_nao_negativo("fila_total")
    fila_recente = inteiro_nao_negativo("fila_tecnica_recente")
    fila_dormente = inteiro_nao_negativo("fila_tecnica_dormente")
    fila_nunca_consultada = inteiro_nao_negativo(
        "fila_recente_nunca_consultada"
    )
    fila_pendente = inteiro_nao_negativo("fila_pendente_apos_lote")
    referencias_tentadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_tentadas"
    )
    referencias_reservadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_reservadas"
    )
    referencias_consultadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_consultadas"
    )
    referencias_linha_exata = inteiro_nao_negativo(
        "referencias_sombra_rapidas_linha_exata"
    )
    referencias_auditadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_auditadas"
    )
    referencias_observadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_observadas"
    )
    comparacoes_referencia = inteiro_nao_negativo(
        "comparacoes_referencia_sombra_rapida"
    )
    aplicacao_referencia = bool(
        dados.get("aplicacao_sinais_referencia_sombra")
    )
    integridade_referencia_rodada = bool(
        referencias_reservadas <= referencias_tentadas
        and referencias_consultadas <= referencias_reservadas
        and referencias_linha_exata <= referencias_consultadas
        and referencias_auditadas <= referencias_tentadas
        and referencias_observadas <= referencias_linha_exata
        and comparacoes_referencia <= referencias_observadas * 2
        and not aplicacao_referencia
    )
    campos_funil_referencia = (
        "avaliadas", "aprovadas", "reprovadas", "com_oferta",
        "bloqueadas_custodia", "bloqueadas_materializacao",
        "alertas_enviados", "fontes_executaveis_pos_envio",
        "selecionadas_para_consulta", "suprimidas_limite_rodada",
    )

    def auditar_funil_referencia(bruto, *, informado, versao_esperada):
        presente = isinstance(bruto, dict)
        funil = bruto if presente else {}
        valor_anterior = funil.get("tentativas_anteriores_funil")
        if isinstance(valor_anterior, bool):
            tentativas_anteriores = 0
            tentativas_anteriores_validas = False
        else:
            try:
                tentativas_anteriores = int(valor_anterior or 0)
                tentativas_anteriores_validas = tentativas_anteriores >= 0
            except (TypeError, ValueError):
                tentativas_anteriores = 0
                tentativas_anteriores_validas = False
        contadores = {}
        contadores_validos = True
        for chave in campos_funil_referencia:
            valor = funil.get(chave)
            if isinstance(valor, bool):
                numero = None
            else:
                try:
                    numero = int(valor or 0)
                except (TypeError, ValueError):
                    numero = None
            if numero is None or numero < 0:
                contadores_validos = False
                numero = 0
            contadores[chave] = numero
        exclusoes = funil.get("exclusoes") or {}
        exclusoes_validas = isinstance(exclusoes, dict)
        if exclusoes_validas:
            for quantidade in exclusoes.values():
                if isinstance(quantidade, bool):
                    exclusoes_validas = False
                    break
                try:
                    if int(quantidade) < 0:
                        exclusoes_validas = False
                        break
                except (TypeError, ValueError):
                    exclusoes_validas = False
                    break
        if not informado:
            integridade = True
        else:
            integridade = bool(
                presente
                and funil.get("versao") == versao_esperada
                and contadores_validos
                and tentativas_anteriores_validas
                and exclusoes_validas
                and contadores["aprovadas"] + contadores["reprovadas"]
                == contadores["avaliadas"]
                and contadores["com_oferta"] <= contadores["avaliadas"]
                and contadores["bloqueadas_custodia"]
                <= contadores["avaliadas"]
                and contadores["bloqueadas_materializacao"]
                <= contadores["aprovadas"]
                and contadores["alertas_enviados"]
                <= contadores["aprovadas"]
                and contadores["fontes_executaveis_pos_envio"]
                <= contadores["alertas_enviados"]
                and contadores["selecionadas_para_consulta"]
                + contadores["suprimidas_limite_rodada"]
                == contadores["fontes_executaveis_pos_envio"]
                and not bool(funil.get("aplicacao_sinais"))
                and not bool(funil.get("telegram"))
                and funil.get("integridade", True) is True
            )
        return {
            "presente": presente,
            "legado_sem_funil": not informado,
            "versao": funil.get("versao"),
            "integridade": integridade,
            **contadores,
            "tentativas_anteriores_funil": tentativas_anteriores,
            "exclusoes": exclusoes if exclusoes_validas else {},
            "aplicacao_sinais": bool(funil.get("aplicacao_sinais")),
            "telegram": bool(funil.get("telegram")),
        }

    chave_funil_rodada = "referencias_sombra_rapidas_funil"
    funil_rodada = auditar_funil_referencia(
        dados.get(chave_funil_rodada),
        informado=chave_funil_rodada in dados,
        versao_esperada="funil-referencia-sombra-rapida-v1",
    )
    integridade_referencia_rodada = bool(
        integridade_referencia_rodada
        and funil_rodada["integridade"]
        and referencias_tentadas
        <= funil_rodada["selecionadas_para_consulta"]
        if not funil_rodada["legado_sem_funil"]
        else integridade_referencia_rodada
    )
    chave_acumulada = "referencia_sombra_rapida_acumulada"
    acumulada_informada = chave_acumulada in dados
    acumulada_bruta = dados.get(chave_acumulada)
    acumulada_presente = isinstance(acumulada_bruta, dict)
    acumulada = acumulada_bruta if acumulada_presente else {}

    def inteiro_acumulado(chave):
        valor = acumulada.get(chave)
        if isinstance(valor, bool):
            return None
        try:
            numero = int(valor or 0)
        except (TypeError, ValueError):
            return None
        return numero if numero >= 0 else None

    nomes_acumulados = (
        "rodadas", "tentadas", "reservadas", "consultadas",
        "linha_exata", "auditadas", "observadas", "comparacoes",
        "creditos_estimados_reservados",
    )
    contadores_acumulados = {
        chave: inteiro_acumulado(chave) for chave in nomes_acumulados
    }
    valores_acumulados_validos = all(
        valor is not None for valor in contadores_acumulados.values()
    )
    if not acumulada_informada:
        integridade_referencia_acumulada = True
    elif not acumulada_presente or not valores_acumulados_validos:
        integridade_referencia_acumulada = False
    else:
        evidencia_acumulada = any(
            contadores_acumulados[chave]
            for chave in nomes_acumulados
            if chave != "rodadas"
        )
        ultima_evidencia_valida = not evidencia_acumulada
        if evidencia_acumulada:
            try:
                datetime.fromisoformat(str(
                    acumulada["ultima_evidencia_em"]
                ))
                ultima_evidencia_valida = True
            except (KeyError, TypeError, ValueError):
                ultima_evidencia_valida = False
        integridade_referencia_acumulada = bool(
            acumulada.get("versao")
            == "referencia-sincronizada-monitor-odd-rapido-acumulada-v1"
            and acumulada.get("integridade") is True
            and not bool(acumulada.get("aplicacao_sinais"))
            and not bool(acumulada.get("telegram"))
            and contadores_acumulados["reservadas"]
            <= contadores_acumulados["tentadas"]
            and contadores_acumulados["consultadas"]
            <= contadores_acumulados["reservadas"]
            and contadores_acumulados["linha_exata"]
            <= contadores_acumulados["consultadas"]
            and contadores_acumulados["auditadas"]
            <= contadores_acumulados["tentadas"]
            and contadores_acumulados["observadas"]
            <= contadores_acumulados["linha_exata"]
            and contadores_acumulados["comparacoes"]
            <= contadores_acumulados["observadas"] * 2
            and contadores_acumulados["tentadas"]
            >= referencias_tentadas
            and contadores_acumulados["reservadas"]
            >= referencias_reservadas
            and contadores_acumulados["consultadas"]
            >= referencias_consultadas
            and contadores_acumulados["linha_exata"]
            >= referencias_linha_exata
            and contadores_acumulados["auditadas"]
            >= referencias_auditadas
            and contadores_acumulados["observadas"]
            >= referencias_observadas
            and contadores_acumulados["comparacoes"]
            >= comparacoes_referencia
            and ultima_evidencia_valida
        )
    chave_funil_acumulado = "funil_selecao"
    funil_acumulado = auditar_funil_referencia(
        acumulada.get(chave_funil_acumulado),
        informado=(
            acumulada_presente and chave_funil_acumulado in acumulada
        ),
        versao_esperada="funil-referencia-sombra-rapida-acumulado-v1",
    )
    if acumulada_presente and not funil_acumulado["legado_sem_funil"]:
        integridade_referencia_acumulada = bool(
            integridade_referencia_acumulada
            and funil_acumulado["integridade"]
            and contadores_acumulados.get("tentadas", 0)
            <= (
                funil_acumulado["tentativas_anteriores_funil"]
                + funil_acumulado["selecionadas_para_consulta"]
            )
            and all(
                funil_acumulado[chave] >= funil_rodada[chave]
                for chave in campos_funil_referencia
            )
        )
    integridade_referencia = bool(
        integridade_referencia_rodada
        and integridade_referencia_acumulada
    )
    rodadas_estimadas = (
        (fila_recente + lote - 1) // lote if fila_recente else 0
    )
    espera_fila_estimada = max(rodadas_estimadas - 1, 0) * intervalo
    try:
        sla_fila = min(max(float(os.getenv(
            "ACOMPANHAMENTO_ODD_API_FILA_SLA_SEGUNDOS", "60"
        )), 30.0), 300.0)
    except (TypeError, ValueError):
        sla_fila = 60.0
    fila_saturada = bool(
        fila_pendente > 0 and espera_fila_estimada > sla_fila
    )
    if fila_saturada:
        estado_fila = "saturada"
    elif fila_pendente:
        estado_fila = "em_rodizio"
    elif fila_recente:
        estado_fila = "coberta"
    elif fila_dormente:
        estado_fila = "dormente"
    else:
        estado_fila = "vazia"
    fresco = idade <= limite
    executando = status in {"ativo", "iniciando"}
    saudavel = bool(
        fresco and executando and falhas < 3 and not fila_saturada
        and integridade_referencia and integridade_clv
    )
    if not fresco:
        motivo = "trabalhador_acompanhamento_odd_atrasado"
        estado = "atrasado"
    elif status == "degradado" or falhas:
        motivo = "trabalhador_acompanhamento_odd_em_recuperacao"
        estado = "recuperando"
    elif not executando:
        motivo = "trabalhador_acompanhamento_odd_parado"
        estado = "parado"
    elif fila_saturada:
        motivo = "fila_acompanhamento_odd_saturada"
        estado = "fila_saturada"
    elif not integridade_referencia:
        motivo = "referencia_sombra_rapida_inconsistente"
        estado = "referencia_sombra_inconsistente"
    elif not integridade_clv:
        motivo = "clv_pos_alerta_inconsistente"
        estado = "clv_pos_alerta_inconsistente"
    else:
        motivo = None
        estado = "ativo"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": motivo,
        "status": status,
        "idade_segundos": round(idade, 3),
        "limite_atraso_segundos": round(limite, 3),
        "intervalo_alvo_segundos": intervalo,
        "intervalo_real_segundos": dados.get(
            "intervalo_real_segundos"
        ),
        "atraso_inicio_segundos": dados.get("atraso_inicio_segundos"),
        "duracao_rodada_segundos": dados.get(
            "duracao_rodada_segundos"
        ),
        "falhas_consecutivas": falhas,
        "consultados": int(dados.get("consultados") or 0),
        "lote_maximo": lote,
        "fila_total": fila_total,
        "fila_tecnica_recente": fila_recente,
        "fila_tecnica_dormente": fila_dormente,
        "fila_recente_nunca_consultada": fila_nunca_consultada,
        "fila_pendente_apos_lote": fila_pendente,
        "estado_fila": estado_fila,
        "rodadas_estimadas_para_cobrir_fila": rodadas_estimadas,
        "espera_fila_estimada_segundos": round(
            espera_fila_estimada, 3
        ),
        "sla_fila_segundos": round(sla_fila, 3),
        "sem_navegacao_packball": bool(
            dados.get("sem_navegacao_packball")
        ),
        "referencia_sombra_rapida": {
            "versao": "referencia-sincronizada-monitor-odd-rapido-v1",
            "integridade": integridade_referencia,
            "integridade_rodada": integridade_referencia_rodada,
            "tentadas": referencias_tentadas,
            "reservadas": referencias_reservadas,
            "consultadas": referencias_consultadas,
            "linha_exata": referencias_linha_exata,
            "auditadas": referencias_auditadas,
            "observadas": referencias_observadas,
            "comparacoes": comparacoes_referencia,
            "creditos_estimados_reservados": inteiro_nao_negativo(
                "creditos_estimados_referencia_sombra_rapida"
            ),
            "aplicacao_sinais": aplicacao_referencia,
            "telegram": False,
            "funil_rodada": funil_rodada,
            "acumulada": {
                "presente": acumulada_presente,
                "legado_sem_acumulado": not acumulada_informada,
                "versao": acumulada.get("versao"),
                "integridade": integridade_referencia_acumulada,
                "iniciado_em": acumulada.get("iniciado_em"),
                "atualizado_em": acumulada.get("atualizado_em"),
                "ultima_evidencia_em": acumulada.get(
                    "ultima_evidencia_em"
                ),
                **{
                    chave: (
                        contadores_acumulados[chave]
                        if contadores_acumulados[chave] is not None else 0
                    )
                    for chave in nomes_acumulados
                },
                "aplicacao_sinais": bool(
                    acumulada.get("aplicacao_sinais")
                ),
                "telegram": bool(acumulada.get("telegram")),
                "motivos": acumulada.get("motivos") or {},
                "funil_selecao": funil_acumulado,
            },
        },
        "clv_pos_alerta": {
            "presente": clv_informado,
            "legado_sem_telemetria": not clv_informado,
            "versao": clv_versao,
            "mercados_api_rapida": (
                list(clv_mercados_api)
                if isinstance(clv_mercados_api, list) else []
            ),
            "mercados_somente_snapshot": (
                list(clv_mercados_snapshot)
                if isinstance(clv_mercados_snapshot, list) else []
            ),
            "cobertura_mercados_integra": (
                cobertura_clv_v2
                if clv_versao != "coleta-clv-pos-alerta-api-rapida-v1"
                else True
            ),
            "estado": dados.get("clv_pos_alerta_estado"),
            "integridade": integridade_clv,
            "coleta_saudavel": clv_falhas_consecutivas < 3,
            "candidatos": clv_candidatos,
            "consultados": clv_consultados,
            "com_oferta_exata": clv_com_oferta,
            "sem_oferta_exata": clv_sem_oferta,
            "somente_estado": clv_somente_estado,
            "estados_persistidos": clv_persistidos,
            "falhas": clv_falhas,
            "falhas_consecutivas": clv_falhas_consecutivas,
            "motivos": dados.get("clv_pos_alerta_motivos") or {},
            "aplicacao_sinais": clv_aplicacao_sinais,
            "telegram": clv_telegram,
        },
        "aplicacao_sinais": False,
    }


def verificar_carteira_operacional(caminho_banco, pasta, env=None):
    """Expõe a política efetiva; divergência pendente é informativa."""
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "banco_ausente",
            "motivo": "carteira_operacional_indisponivel",
        }
    conexao = None
    try:
        uri = caminho_banco.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        return auditar_carteira_operacional(
            conexao,
            env if env is not None else os.environ,
            pasta,
        )
    except (OSError, sqlite3.Error) as erro:
        return {
            "saudavel": False,
            "estado": "auditoria_indisponivel",
            "motivo": "carteira_operacional_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def _ler_registros_coleta_recentes(caminho_log, limite=1000):
    """Preserva a continuidade do ciclo quando o JSONL acabou de girar."""
    caminho_log = Path(caminho_log)

    def ler(caminho):
        if not caminho.exists():
            return []
        try:
            linhas = caminho.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return []
        registros = []
        for linha in linhas:
            try:
                evento = json.loads(linha)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if evento.get("em"):
                registros.append(evento)
        return registros

    registros = ler(caminho_log)
    recentes = registros[-max(int(limite), 1):]
    if any(
        item.get("evento") == "ciclo_concluido" for item in recentes
    ):
        return recentes

    # A rotação pode acontecer durante um ciclo longo: nesse instante o log
    # atual contém progresso, mas o último sucesso está em `.1`. Retrocedemos
    # somente até encontrá-lo e mantemos tudo a partir dele, inclusive falhas
    # atravessando a fronteira entre os arquivos.
    posteriores = registros
    for indice in range(1, 6):
        anteriores = ler(Path(f"{caminho_log}.{indice}"))
        if not anteriores:
            continue
        combinados = anteriores + posteriores
        posicao_sucesso = next(
            (
                posicao for posicao in range(len(combinados) - 1, -1, -1)
                if combinados[posicao].get("evento") == "ciclo_concluido"
            ),
            None,
        )
        if posicao_sucesso is not None:
            return combinados[posicao_sucesso:]
        posteriores = combinados
    return posteriores[-max(int(limite), 1):]


def verificar_coleta(
    caminho_log, agora=None, limite=300, limite_progresso=120
):
    agora = agora or datetime.now()
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {"saudavel": False, "motivo": "log_ausente", "idade": None}
    registros = _ler_registros_coleta_recentes(caminho_log)
    if not registros:
        return {"saudavel": False, "motivo": "log_invalido", "idade": None}

    ultimo_sucesso = next(
        (
            item for item in reversed(registros)
            if item.get("evento") == "ciclo_concluido"
        ),
        None,
    )
    ultimo_progresso = next(
        (
            item for item in reversed(registros)
            if item.get("evento") == "ciclo_em_andamento"
        ),
        None,
    )
    falhas_consecutivas = 0
    falhas_desde_sucesso = []
    for item in reversed(registros):
        if item.get("evento") in (
            "ciclo_concluido",
            "ciclo_pausado_packball",
        ):
            break
        if item.get("evento") == "ciclo_falhou":
            falhas_consecutivas += 1
            falhas_desde_sucesso.append(item)

    pausa_local_legada = bool(falhas_desde_sucesso) and all(
        item.get("erro") == "PackBallBloqueadoError"
        for item in falhas_desde_sucesso
    ) and any(
        "teto local" in str(item.get("mensagem") or "").lower()
        for item in falhas_desde_sucesso
    )
    if pausa_local_legada:
        falhas_consecutivas = 0

    if ultimo_sucesso is None:
        return {
            "saudavel": False,
            "motivo": "sem_ciclo_concluido",
            "idade": None,
            "ultimo_evento": registros[-1].get("evento"),
            "falhas_consecutivas": falhas_consecutivas,
        }
    instante = datetime.fromisoformat(ultimo_sucesso["em"])
    idade = max((agora - instante).total_seconds(), 0)
    idade_progresso = None
    ciclo_em_andamento = False
    if ultimo_progresso is not None:
        try:
            instante_progresso = datetime.fromisoformat(
                ultimo_progresso["em"]
            )
            idade_progresso = max(
                (agora - instante_progresso).total_seconds(), 0
            )
            falha_posterior = any(
                item.get("evento") == "ciclo_falhou"
                and datetime.fromisoformat(item["em"]) > instante_progresso
                for item in registros
                if item.get("em")
            )
            ciclo_em_andamento = (
                instante_progresso > instante
                and idade_progresso <= limite_progresso
                and not falha_posterior
            )
        except (KeyError, TypeError, ValueError):
            idade_progresso = None
    ultimo = registros[-1]
    pausa_recente = (
        ultimo.get("evento") == "ciclo_pausado_packball"
        or pausa_local_legada
    )
    try:
        idade_pausa = max(
            (agora - datetime.fromisoformat(ultimo["em"])).total_seconds(), 0
        )
    except (KeyError, TypeError, ValueError):
        idade_pausa = float("inf")
    if pausa_recente and idade_pausa <= limite and idade <= 900:
        motivo = None
    elif falhas_consecutivas >= 3:
        motivo = "falhas_consecutivas"
    elif idade > limite and not ciclo_em_andamento:
        motivo = "coleta_parada"
    else:
        motivo = None
    diagnostico_v2 = ultimo_sucesso.get(
        "gols_capacidade_contextual_v2"
    )
    if not isinstance(diagnostico_v2, dict):
        diagnostico_v2 = {}
    diagnostico_thestatsapi = ultimo_sucesso.get("thestatsapi_sombra")
    if not isinstance(diagnostico_thestatsapi, dict):
        diagnostico_thestatsapi = {}
    diagnostico_betsapi = ultimo_sucesso.get("betsapi")
    if not isinstance(diagnostico_betsapi, dict):
        diagnostico_betsapi = {}
    return {
        "saudavel": motivo is None,
        "motivo": motivo,
        "idade": round(idade, 1),
        "ultimo_evento": registros[-1].get("evento"),
        "ultimo_sucesso_em": ultimo_sucesso["em"],
        "partidas_ultimo_ciclo": int(
            ultimo_sucesso.get("partidas", 0) or 0
        ),
        "tarefas_processadas_ultimo_ciclo": int(
            ultimo_sucesso.get("tarefas_processadas", 0) or 0
        ),
        "falhas_consecutivas": falhas_consecutivas,
        "pausa_preventiva": bool(pausa_recente and idade_pausa <= limite),
        "ciclo_em_andamento": ciclo_em_andamento,
        "etapa_atual": (
            ultimo_progresso.get("etapa")
            if ciclo_em_andamento else None
        ),
        "ultimo_progresso_em": (
            ultimo_progresso.get("em") if ultimo_progresso else None
        ),
        "idade_progresso": (
            round(idade_progresso, 1)
            if idade_progresso is not None else None
        ),
        "gols_capacidade_contextual_v2": diagnostico_v2,
        "thestatsapi_sombra": diagnostico_thestatsapi,
        "betsapi": diagnostico_betsapi,
    }


def verificar_historico_api_live(caminho_banco, agora=None):
    """Resume a série auxiliar em leitura, sem afetar a operação."""
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
            "aplicacao_sinais": False,
        }
    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho_banco.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=10,
        )
        conexao.row_factory = sqlite3.Row
        return resumir_historico_api_live(
            conexao, agora=agora
        )
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "historico_api_live_indisponivel",
            "erro": type(erro).__name__,
            "aplicacao_sinais": False,
        }
    finally:
        if conexao is not None:
            conexao.close()


def verificar_cache_api_operacional(caminho_log, limite_consecutivo=3):
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_com_falha_consecutivos": 0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-1000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            evento.get("evento") == "ciclo_concluido"
            and evento.get("cache_api_falhas_ciclo") is not None
        ):
            ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_com_falha_consecutivos": 0,
        }
    consecutivos = 0
    for ciclo in reversed(ciclos):
        if int(ciclo.get("cache_api_falhas_ciclo") or 0) <= 0:
            break
        consecutivos += 1
    ultima_falha = int(ciclos[-1].get("cache_api_falhas_ciclo") or 0)
    saudavel = consecutivos < int(limite_consecutivo)
    return {
        "saudavel": saudavel,
        "estado": "saudavel" if saudavel else "degradado",
        "motivo": None if saudavel else "cache_api_persistente_indisponivel",
        "ciclos_com_falha_consecutivos": consecutivos,
        "falhas_ultimo_ciclo": ultima_falha,
        "ciclos_observados": len(ciclos),
    }


def verificar_acompanhamento_preco_pos_alerta(
    caminho_log, limite_consecutivo=3
):
    """Audita a coleta auxiliar de preço sem interferir nos sinais.

    Ciclos sem alerta elegível não representam sucesso nem falha. A degradação
    só é confirmada quando as últimas execuções que realmente agendaram um
    acompanhamento falham de forma consecutiva. O estado é informativo: a
    seleção e o envio de sinais continuam sob as regras e gates próprios.
    """
    caminho_log = Path(caminho_log)
    limite = max(int(limite_consecutivo), 1)
    base = {
        "saudavel": True,
        "estado": "aguardando_telemetria",
        "motivo": None,
        "ciclos_degradados_consecutivos": 0,
        "limite_consecutivo": limite,
        "ciclos_aplicaveis_observados": 0,
        "altera_sinais": False,
    }
    if not caminho_log.exists():
        return base

    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-1000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        perfil = evento.get("perfil_agendamento")
        if not isinstance(perfil, dict):
            continue
        if "acompanhamentos_preco_agendados" not in perfil:
            continue
        agendados = int(
            perfil.get("acompanhamentos_preco_agendados") or 0
        )
        if agendados <= 0:
            continue
        ciclos.append({
            "em": evento.get("em"),
            "agendados": agendados,
            "processados": int(
                perfil.get("acompanhamentos_preco_processados") or 0
            ),
            "com_odds": int(
                perfil.get("acompanhamentos_preco_com_odds") or 0
            ),
            "sem_odds": int(
                perfil.get("acompanhamentos_preco_sem_odds") or 0
            ),
            "snapshots": int(
                perfil.get("acompanhamentos_preco_snapshots") or 0
            ),
        })

    if not ciclos:
        return {
            **base,
            "estado": "sem_acompanhamentos_recentes",
        }

    def degradado(ciclo):
        return bool(
            ciclo["processados"] < ciclo["agendados"]
            or ciclo["com_odds"] < ciclo["processados"]
            or ciclo["snapshots"] < ciclo["processados"]
        )

    consecutivos = 0
    for ciclo in reversed(ciclos):
        if not degradado(ciclo):
            break
        consecutivos += 1

    ultimo = dict(ciclos[-1])
    saudavel = consecutivos < limite
    estado = "saudavel"
    if not saudavel:
        estado = "degradado"
    elif consecutivos:
        estado = "oscilacao_tolerada"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": (
            None
            if saudavel
            else "acompanhamento_preco_pos_alerta_indisponivel"
        ),
        "ciclos_degradados_consecutivos": consecutivos,
        "limite_consecutivo": limite,
        "ciclos_aplicaveis_observados": len(ciclos),
        "ultimo_ciclo": ultimo,
        "altera_sinais": False,
    }


def verificar_amostragem_referencia_odds_sombra(
    caminho_log, limite_consecutivo=3
):
    """Detecta falha ou ausência persistente na referência independente.

    Somente ciclos que reservaram uma chamada contam como tentativa. Ciclos
    sem jogos elegíveis, em cooldown ou após o limite diário não são falhas.
    A auditoria é observacional e jamais altera sinais, HT/FT ou Telegram.
    """
    caminho_log = Path(caminho_log)
    limite = max(int(limite_consecutivo), 1)
    base = {
        "saudavel": True,
        "estado": "aguardando_telemetria",
        "motivo": None,
        "requer_atencao": False,
        "tentativas_sem_cobertura_consecutivas": 0,
        "falhas_tecnicas_consecutivas": 0,
        "limite_consecutivo": limite,
        "ciclos_observados": 0,
        "ciclos_com_tentativa": 0,
        "elegiveis_betsapi": 0,
        "reservadas": 0,
        "mercados_persistidos_sombra": 0,
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
        "ciclos_telemetria_multimercado": 0,
        "altera_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    if not caminho_log.exists():
        return base

    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        diagnostico_fonte = evento.get("the_odds_api") or {}
        resumo = (diagnostico_fonte.get(
            "amostragem_referencia"
        ))
        if not isinstance(resumo, dict) or "ativa" not in resumo:
            continue
        ciclos.append({
            **resumo,
            "em": evento.get("em"),
            "controle_estado": diagnostico_fonte.get("controle_estado"),
            "circuito": diagnostico_fonte.get("circuito"),
        })

    if not ciclos:
        return base
    ultimo = ciclos[-1]
    if ultimo.get("ativa") is not True:
        return {
            **base,
            "estado": "desativada",
            "ciclos_observados": len(ciclos),
        }
    controle_estado = ultimo.get("controle_estado")
    if (
        isinstance(controle_estado, dict)
        and controle_estado.get("saudavel") is False
    ):
        return {
            **base,
            "saudavel": False,
            "estado": "controle_estado_invalido",
            "motivo": "the_odds_api_estado_irrecuperavel",
            "requer_atencao": True,
            "ciclos_observados": len(ciclos),
            "elegiveis_betsapi": sum(
                int(ciclo.get("elegiveis_betsapi") or 0)
                for ciclo in ciclos
            ),
            "reservadas": sum(
                int(ciclo.get("reservadas") or 0) for ciclo in ciclos
            ),
            "mercados_persistidos_sombra": sum(
                int(ciclo.get("mercados_persistidos_sombra") or 0)
                for ciclo in ciclos
            ),
            "controle_estado": dict(controle_estado),
            "ultimo_ciclo": dict(ultimo),
        }

    tentativas = [
        ciclo for ciclo in ciclos
        if ciclo.get("ativa") is True
        and int(ciclo.get("elegiveis_betsapi") or 0) > 0
        and int(ciclo.get("reservadas") or 0) > 0
    ]
    elegiveis = sum(
        int(ciclo.get("elegiveis_betsapi") or 0) for ciclo in ciclos
    )
    reservadas = sum(int(ciclo.get("reservadas") or 0) for ciclo in ciclos)
    mercados = sum(
        int(ciclo.get("mercados_persistidos_sombra") or 0)
        for ciclo in ciclos
    )
    preselecoes = sum(
        int(ciclo.get("preselecoes_cobertura") or 0)
        for ciclo in ciclos
    )
    preselecoes_cobertas = sum(
        int(ciclo.get("preselecoes_cobertas") or 0)
        for ciclo in ciclos
    )
    preselecoes_descartadas = sum(
        int(ciclo.get("preselecoes_descartadas") or 0)
        for ciclo in ciclos
    )
    reservas_economizadas = sum(
        int(ciclo.get("reservas_economizadas") or 0)
        for ciclo in ciclos
    )
    preselecoes_evento = sum(
        int(ciclo.get("preselecoes_evento") or 0)
        for ciclo in ciclos
    )
    eventos_pareados = sum(
        int(ciclo.get("eventos_pareados_pre_reserva") or 0)
        for ciclo in ciclos
    )
    eventos_descartados = sum(
        int(ciclo.get("eventos_descartados_pre_reserva") or 0)
        for ciclo in ciclos
    )
    reservas_economizadas_evento = sum(
        int(ciclo.get("reservas_economizadas_evento") or 0)
        for ciclo in ciclos
    )
    creditos_estimados_reservados = sum(
        int(ciclo.get("creditos_estimados_reservados") or 0)
        for ciclo in ciclos
    )
    consultas_combinadas = sum(
        int(ciclo.get("consultas_combinadas") or 0)
        for ciclo in ciclos
    )
    maximo_mercados_por_consulta = max((
        int(ciclo.get("maximo_mercados_por_consulta") or 0)
        for ciclo in ciclos
    ), default=0)
    ciclos_telemetria_multimercado = sum(
        1 for ciclo in ciclos
        if "creditos_estimados_reservados" in ciclo
        and "por_mercado" in ciclo
    )
    por_mercado = {}
    auditorias_multimercado_invalidas = 0
    for ciclo in ciclos:
        if not (
            "creditos_estimados_reservados" in ciclo
            and "por_mercado" in ciclo
        ):
            continue
        reservas_ciclo = int(ciclo.get("reservadas") or 0)
        consultas_ciclo = int(ciclo.get("consultadas") or 0)
        persistidos_ciclo = int(
            ciclo.get("mercados_persistidos_sombra") or 0
        )
        creditos_ciclo = int(
            ciclo.get("creditos_estimados_reservados") or 0
        )
        combinadas_ciclo = int(
            ciclo.get("consultas_combinadas") or 0
        )
        maximo_ciclo = int(
            ciclo.get("maximo_mercados_por_consulta") or 0
        )
        mercados_ciclo = ciclo.get("por_mercado") or {}
        invalida = bool(
            not isinstance(mercados_ciclo, dict)
            or creditos_ciclo < reservas_ciclo
            or creditos_ciclo > 3 * reservas_ciclo
            or creditos_ciclo < maximo_ciclo
            or combinadas_ciclo < 0
            or combinadas_ciclo > reservas_ciclo
            or maximo_ciclo < 0
            or maximo_ciclo > 3
            or (combinadas_ciclo > 0 and maximo_ciclo < 2)
        )
        soma_consultados = 0
        soma_anexados = 0
        if isinstance(mercados_ciclo, dict):
            for mercado, contadores in mercados_ciclo.items():
                if not isinstance(contadores, dict):
                    invalida = True
                    continue
                try:
                    elegiveis_mercado = int(
                        contadores.get("elegiveis") or 0
                    )
                    consultados_mercado = int(
                        contadores.get("consultados") or 0
                    )
                    anexados_mercado = int(
                        contadores.get("anexados") or 0
                    )
                except (TypeError, ValueError):
                    invalida = True
                    continue
                if (
                    elegiveis_mercado < 0
                    or consultados_mercado < 0
                    or anexados_mercado < 0
                    or consultados_mercado > elegiveis_mercado
                    or anexados_mercado > consultados_mercado
                ):
                    invalida = True
                soma_consultados += consultados_mercado
                soma_anexados += anexados_mercado
                acumulado = por_mercado.setdefault(str(mercado), {
                    "elegiveis": 0,
                    "consultados": 0,
                    "anexados": 0,
                })
                acumulado["elegiveis"] += elegiveis_mercado
                acumulado["consultados"] += consultados_mercado
                acumulado["anexados"] += anexados_mercado
        if (
            soma_anexados != persistidos_ciclo
            or soma_consultados < consultas_ciclo
            or soma_consultados > 3 * consultas_ciclo
        ):
            invalida = True
        if invalida:
            auditorias_multimercado_invalidas += 1
    if auditorias_multimercado_invalidas:
        return {
            **base,
            "saudavel": False,
            "estado": "auditoria_multimercado_invalida",
            "motivo": "amostragem_referencia_multimercado_inconsistente",
            "requer_atencao": True,
            "ciclos_observados": len(ciclos),
            "ciclos_com_tentativa": len(tentativas),
            "elegiveis_betsapi": elegiveis,
            "reservadas": reservadas,
            "mercados_persistidos_sombra": mercados,
            "creditos_estimados_reservados": (
                creditos_estimados_reservados
            ),
            "consultas_combinadas": consultas_combinadas,
            "maximo_mercados_por_consulta": (
                maximo_mercados_por_consulta
            ),
            "por_mercado": por_mercado,
            "ciclos_telemetria_multimercado": (
                ciclos_telemetria_multimercado
            ),
            "auditorias_multimercado_invalidas": (
                auditorias_multimercado_invalidas
            ),
            "ultimo_ciclo": dict(ultimo),
        }
    auditorias_preselecao_invalidas = sum(
        1 for ciclo in ciclos
        if (
            int(ciclo.get("preselecoes_cobertas") or 0)
            + int(ciclo.get("preselecoes_descartadas") or 0)
            != int(ciclo.get("preselecoes_cobertura") or 0)
            or int(ciclo.get("eventos_pareados_pre_reserva") or 0)
            + int(ciclo.get("eventos_descartados_pre_reserva") or 0)
            != int(ciclo.get("preselecoes_evento") or 0)
            or int(ciclo.get("preselecoes_evento") or 0)
            > int(ciclo.get("preselecoes_cobertas") or 0)
            or int(ciclo.get("reservas_economizadas") or 0)
            > (
                int(ciclo.get("preselecoes_descartadas") or 0)
                + int(ciclo.get("eventos_descartados_pre_reserva") or 0)
            )
            or int(ciclo.get("reservas_economizadas_evento") or 0)
            > int(ciclo.get("eventos_descartados_pre_reserva") or 0)
        )
    )
    if auditorias_preselecao_invalidas:
        return {
            **base,
            "saudavel": False,
            "estado": "auditoria_preselecao_invalida",
            "motivo": "amostragem_referencia_preselecao_inconsistente",
            "requer_atencao": True,
            "ciclos_observados": len(ciclos),
            "ciclos_com_tentativa": len(tentativas),
            "elegiveis_betsapi": elegiveis,
            "reservadas": reservadas,
            "mercados_persistidos_sombra": mercados,
            "preselecoes_cobertura": preselecoes,
            "preselecoes_cobertas": preselecoes_cobertas,
            "preselecoes_descartadas": preselecoes_descartadas,
            "preselecoes_evento": preselecoes_evento,
            "eventos_pareados_pre_reserva": eventos_pareados,
            "eventos_descartados_pre_reserva": eventos_descartados,
            "reservas_economizadas": reservas_economizadas,
            "reservas_economizadas_evento": (
                reservas_economizadas_evento
            ),
            "auditorias_preselecao_invalidas": (
                auditorias_preselecao_invalidas
            ),
            "ultimo_ciclo": dict(ultimo),
        }
    if not tentativas:
        return {
            **base,
            "estado": (
                "aguardando_reserva" if elegiveis else "sem_oportunidade"
            ),
            "ciclos_observados": len(ciclos),
            "elegiveis_betsapi": elegiveis,
            "reservadas": reservadas,
            "mercados_persistidos_sombra": mercados,
            "preselecoes_cobertura": preselecoes,
            "preselecoes_cobertas": preselecoes_cobertas,
            "preselecoes_descartadas": preselecoes_descartadas,
            "preselecoes_evento": preselecoes_evento,
            "eventos_pareados_pre_reserva": eventos_pareados,
            "eventos_descartados_pre_reserva": eventos_descartados,
            "reservas_economizadas": reservas_economizadas,
            "reservas_economizadas_evento": (
                reservas_economizadas_evento
            ),
            "creditos_estimados_reservados": (
                creditos_estimados_reservados
            ),
            "consultas_combinadas": consultas_combinadas,
            "maximo_mercados_por_consulta": (
                maximo_mercados_por_consulta
            ),
            "por_mercado": por_mercado,
            "ciclos_telemetria_multimercado": (
                ciclos_telemetria_multimercado
            ),
            "ultimo_ciclo": dict(ultimo),
        }

    sem_cobertura = 0
    falhas_tecnicas = 0
    for ciclo in reversed(tentativas):
        persistidos = int(
            ciclo.get("mercados_persistidos_sombra") or 0
        )
        if persistidos > 0:
            break
        sem_cobertura += 1
    for ciclo in reversed(tentativas):
        motivos = ciclo.get("motivos") or {}
        if int(motivos.get("falha_isolada") or 0) <= 0:
            break
        falhas_tecnicas += 1

    saudavel = falhas_tecnicas < limite
    requer_atencao = bool(
        falhas_tecnicas >= limite or sem_cobertura >= limite
    )
    motivo = None
    estado = "saudavel"
    if falhas_tecnicas >= limite:
        estado = "falha_persistente"
        motivo = "amostragem_referencia_odds_falhou"
    elif sem_cobertura >= limite:
        estado = "sem_cobertura_persistente"
        motivo = "amostragem_referencia_odds_sem_cobertura"
    elif sem_cobertura:
        estado = "cobertura_em_formacao"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": motivo,
        "requer_atencao": requer_atencao,
        "tentativas_sem_cobertura_consecutivas": sem_cobertura,
        "falhas_tecnicas_consecutivas": falhas_tecnicas,
        "limite_consecutivo": limite,
        "ciclos_observados": len(ciclos),
        "ciclos_com_tentativa": len(tentativas),
        "elegiveis_betsapi": elegiveis,
        "reservadas": reservadas,
        "mercados_persistidos_sombra": mercados,
        "preselecoes_cobertura": preselecoes,
        "preselecoes_cobertas": preselecoes_cobertas,
        "preselecoes_descartadas": preselecoes_descartadas,
        "preselecoes_evento": preselecoes_evento,
        "eventos_pareados_pre_reserva": eventos_pareados,
        "eventos_descartados_pre_reserva": eventos_descartados,
        "reservas_economizadas": reservas_economizadas,
        "reservas_economizadas_evento": reservas_economizadas_evento,
        "creditos_estimados_reservados": (
            creditos_estimados_reservados
        ),
        "consultas_combinadas": consultas_combinadas,
        "maximo_mercados_por_consulta": maximo_mercados_por_consulta,
        "por_mercado": por_mercado,
        "ciclos_telemetria_multimercado": (
            ciclos_telemetria_multimercado
        ),
        "ultimo_ciclo": dict(ultimo),
        "altera_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def verificar_prioridade_scanner_packball(
    caminho_log, limite_consecutivo=3
):
    """Detecta perda persistente do Scanner sem reagir a uma oscilação.

    O Scanner organiza a prioridade, mas a lista Ao Vivo continua sendo o
    fallback de cobertura. Por isso uma falha isolada permanece saudável e só
    três ciclos concluídos consecutivos sem ``prioridade_carregada`` formam um
    incidente operacional.
    """
    def _instante_ciclo(ciclo):
        valor = ciclo.get("_em_ciclo")
        if not valor:
            return None
        try:
            return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    def _duracao_segundos(inicio, fim):
        if inicio is None or fim is None:
            return 0.0
        try:
            return round(max((fim - inicio).total_seconds(), 0.0), 3)
        except (TypeError, ValueError):
            return 0.0

    caminho_log = Path(caminho_log)
    limite = max(int(limite_consecutivo), 1)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_sem_prioridade_consecutivos": 0,
            "limite_consecutivo": limite,
            "ciclos_observados": 0,
            "episodios_sem_prioridade_observados": 0,
            "duracao_sem_prioridade_segundos": 0.0,
            "duracao_total_sem_prioridade_segundos": 0.0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        scanner = ((evento.get("lista_packball") or {}).get("scanner"))
        if not isinstance(scanner, dict) or "habilitado" not in scanner:
            continue
        ciclos.append({**scanner, "_em_ciclo": evento.get("em")})
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_sem_prioridade_consecutivos": 0,
            "limite_consecutivo": limite,
            "ciclos_observados": 0,
            "episodios_sem_prioridade_observados": 0,
            "duracao_sem_prioridade_segundos": 0.0,
            "duracao_total_sem_prioridade_segundos": 0.0,
        }

    episodios = []
    inicio_episodio = None
    ultimo_degradado = None
    for scanner in ciclos:
        instante = _instante_ciclo(scanner)
        degradado = bool(
            scanner.get("habilitado") is True
            and scanner.get("estado") != "prioridade_carregada"
        )
        if degradado:
            if inicio_episodio is None:
                inicio_episodio = instante
            if instante is not None:
                ultimo_degradado = instante
            continue
        if inicio_episodio is not None:
            fim_episodio = instante or ultimo_degradado
            episodios.append({
                "inicio": inicio_episodio,
                "fim": fim_episodio,
                "aberto": False,
                "duracao_segundos": _duracao_segundos(
                    inicio_episodio, fim_episodio
                ),
            })
            inicio_episodio = None
            ultimo_degradado = None
    if inicio_episodio is not None:
        episodios.append({
            "inicio": inicio_episodio,
            "fim": ultimo_degradado,
            "aberto": True,
            "duracao_segundos": _duracao_segundos(
                inicio_episodio, ultimo_degradado
            ),
        })

    episodio_atual = (
        episodios[-1]
        if episodios and episodios[-1]["aberto"]
        else None
    )
    duracao_total = round(sum(
        episodio["duracao_segundos"] for episodio in episodios
    ), 3)

    ultimo = ciclos[-1]
    if ultimo.get("habilitado") is not True:
        return {
            "saudavel": True,
            "estado": "desativado",
            "motivo": None,
            "ciclos_sem_prioridade_consecutivos": 0,
            "limite_consecutivo": limite,
            "ciclos_observados": len(ciclos),
            "estado_ultimo_ciclo": ultimo.get("estado") or "desativado",
            "fallback_ao_vivo_ativo": True,
            "episodios_sem_prioridade_observados": len(episodios),
            "duracao_sem_prioridade_segundos": 0.0,
            "duracao_total_sem_prioridade_segundos": duracao_total,
        }

    consecutivos = 0
    estados_recentes = []
    for scanner in reversed(ciclos):
        if scanner.get("habilitado") is not True:
            break
        estado = scanner.get("estado")
        if estado == "prioridade_carregada":
            break
        consecutivos += 1
        estados_recentes.append(estado or "estado_ausente")

    saudavel = consecutivos < limite
    return {
        "saudavel": saudavel,
        "estado": "saudavel" if saudavel else "degradado",
        "motivo": None if saudavel else "prioridade_scanner_indisponivel",
        "ciclos_sem_prioridade_consecutivos": consecutivos,
        "limite_consecutivo": limite,
        "ciclos_observados": len(ciclos),
        "estado_ultimo_ciclo": ultimo.get("estado"),
        "estados_degradados_recentes": estados_recentes,
        "contador_filtrado_ultimo_ciclo": ultimo.get("contador_filtrado"),
        "jogos_extraidos_ultimo_ciclo": ultimo.get("jogos_extraidos"),
        "fallback_ao_vivo_ativo": True,
        "episodios_sem_prioridade_observados": len(episodios),
        "sem_prioridade_desde": (
            episodio_atual["inicio"].isoformat()
            if episodio_atual and episodio_atual["inicio"] is not None
            else None
        ),
        "duracao_sem_prioridade_segundos": (
            episodio_atual["duracao_segundos"] if episodio_atual else 0.0
        ),
        "duracao_total_sem_prioridade_segundos": duracao_total,
    }


def verificar_fontes_sinais_operacionais(
    caminho_log, limite_consecutivo=2
):
    """Alerta apenas quando o gate fail-closed persiste entre ciclos."""
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_degradados_consecutivos": 0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        if (
            "saude_api" not in evento
            and "sinais_bloqueados_fontes" not in evento
        ):
            continue
        ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_degradados_consecutivos": 0,
        }

    consecutivos = 0
    for ciclo in reversed(ciclos):
        saude_api = ciclo.get("saude_api") or {}
        betsapi = ciclo.get("betsapi") or {}
        bloqueados = int(ciclo.get("sinais_bloqueados_fontes") or 0)
        sem_demanda_api = bool(
            int(ciclo.get("partidas") or 0) == 0
            and int(ciclo.get("tarefas_agendadas") or 0) == 0
        )
        api_ainda_nao_necessaria = bool(
            sem_demanda_api
            and saude_api.get("motivo") == "api_ainda_nao_confirmada"
        )
        betsapi_oficial_disponivel = bool(
            betsapi.get("ativa") is True
            and betsapi.get("aplicacao_sinais") is True
            and betsapi.get("circuito_aberto") is not True
            and (
                (betsapi.get("circuito") or {}).get(
                    "persistencia_saudavel"
                ) is not False
            )
        )
        degradado = (
            (
                saude_api.get("saudavel") is False
                and not api_ainda_nao_necessaria
                and not betsapi_oficial_disponivel
            )
            or bloqueados > 0
        )
        if not degradado:
            break
        consecutivos += 1
    ultimo = ciclos[-1]
    ultima_saude_api = dict(ultimo.get("saude_api") or {})
    ultimos_bloqueados = int(
        ultimo.get("sinais_bloqueados_fontes") or 0
    )
    motivos = dict(ultimo.get("motivos_bloqueio_fontes") or {})
    betsapi_ultimo = dict(ultimo.get("betsapi") or {})
    betsapi_oficial_ultimo_ciclo = bool(
        betsapi_ultimo.get("ativa") is True
        and betsapi_ultimo.get("aplicacao_sinais") is True
        and betsapi_ultimo.get("circuito_aberto") is not True
        and (
            (betsapi_ultimo.get("circuito") or {}).get(
                "persistencia_saudavel"
            ) is not False
        )
    )
    saudavel = consecutivos < max(int(limite_consecutivo), 1)
    return {
        "saudavel": saudavel,
        "estado": "saudavel" if saudavel else "degradado",
        "motivo": None if saudavel else "fontes_sinais_indisponiveis",
        "ciclos_degradados_consecutivos": consecutivos,
        "limite_consecutivo": max(int(limite_consecutivo), 1),
        "sinais_bloqueados_ultimo_ciclo": ultimos_bloqueados,
        "motivos_ultimo_ciclo": motivos,
        "saude_api_ultimo_ciclo": ultima_saude_api,
        "betsapi_oficial_ultimo_ciclo": betsapi_oficial_ultimo_ciclo,
        "ciclos_observados": len(ciclos),
    }


def verificar_capacidade_coleta(
    caminho_log,
    limite_consecutivo=3,
    janela_ciclos=20,
    limiar_pressao=0.85,
    margem_ultima_tarefa_segundos=5.0,
):
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_adiando": 0,
            "ciclos_pausa_preventiva": 0,
            "ciclos_reserva_adaptativa": 0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-1000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            evento.get("evento") == "ciclo_concluido"
            and evento.get("tarefas_adiadas") is not None
        ):
            ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_adiando": 0,
            "ciclos_pausa_preventiva": 0,
        }
    consecutivos = 0
    for ciclo in reversed(ciclos):
        # O limitador de acesso do PackBall adia tarefas de propósito para
        # evitar bloqueios. Esses ciclos são neutros: não criam nem apagam
        # uma sequência de falta real de capacidade de processamento.
        limitado_packball = (
            (ciclo.get("ritmo_packball") or {}).get(
                "distribuicao_janela_ativa"
            ) is True
        )
        if limitado_packball:
            # A distribuição uniforme é um novo regime de capacidade:
            # a fila restante decorre do teto externo, não de atraso do
            # processamento. Ela encerra a sequência do regime anterior.
            break
        if ciclo.get("pausa_preventiva"):
            continue
        if int(ciclo.get("tarefas_adiadas") or 0) <= 0:
            break
        consecutivos += 1
    pausas_preventivas = 0
    for ciclo in reversed(ciclos):
        if not ciclo.get("pausa_preventiva"):
            break
        pausas_preventivas += 1
    ciclos_limitados_packball = 0
    for ciclo in reversed(ciclos):
        if (
            (ciclo.get("ritmo_packball") or {}).get(
                "distribuicao_janela_ativa"
            ) is not True
        ):
            break
        ciclos_limitados_packball += 1
    ciclos_sem_resgate_antigo = 0
    for ciclo in reversed(ciclos):
        idade_fila = ciclo.get("idade_fila")
        if not isinstance(idade_fila, dict) or not idade_fila:
            break
        agendadas_idade = (
            idade_fila.get("agendadas_acionaveis")
            or idade_fila.get("agendadas")
            or {}
        )
        processadas_idade = (
            idade_fila.get("processadas_acionaveis")
            or idade_fila.get("processadas")
            or {}
        )
        atrasadas = int(agendadas_idade.get("acima_20_minutos") or 0)
        resgatadas = int(
            processadas_idade.get("acima_20_minutos") or 0
        )
        # Compatibilidade com ciclos produzidos antes da telemetria de idade
        # acionável. A priorização já registrava essa contagem e permite
        # distinguir uma partida expirada de uma oportunidade que ainda pode
        # gerar sinal. Na ausência das duas evidências, conserva a leitura
        # legada mais prudente.
        telemetria_acionavel = isinstance(
            idade_fila.get("agendadas_acionaveis"), dict
        )
        if not telemetria_acionavel:
            priorizacao = (
                (ciclo.get("enriquecimento_api_lote") or {})
                .get("priorizacao") or {}
            )
            if priorizacao.get("atrasadas_acionaveis") is not None:
                atrasadas = int(
                    priorizacao.get("atrasadas_acionaveis") or 0
                )
        if atrasadas <= 0 or resgatadas > 0:
            break
        if ciclo.get("pausa_preventiva"):
            break
        ciclos_sem_resgate_antigo += 1
    ciclos_sem_rechecagem_pos_evento = 0
    for ciclo in reversed(ciclos):
        perfil = ciclo.get("perfil_agendamento")
        if not isinstance(perfil, dict):
            break
        agendadas_pos_evento = int(
            perfil.get("rechecagens_pos_evento_agendadas") or 0
        )
        processadas_pos_evento = int(
            perfil.get("rechecagens_pos_evento_processadas") or 0
        )
        if agendadas_pos_evento <= 0 or processadas_pos_evento > 0:
            break
        if ciclo.get("pausa_preventiva"):
            break
        ciclos_sem_rechecagem_pos_evento += 1
    ciclos_observados = []
    ciclos_ativos = []
    for ciclo in ciclos:
        duracao = ciclo.get("duracao_detalhada_segundos")
        orcamento = ciclo.get("orcamento_detalhado_segundos")
        mensuravel = (
            not ciclo.get("pausa_preventiva")
            and int(ciclo.get("tarefas_agendadas") or 0) > 0
            and duracao is not None
            and orcamento is not None
            and float(orcamento) > 0
        )
        if mensuravel:
            ciclos_observados.append(ciclo)
        if (
            mensuravel
            and not (
                (ciclo.get("ritmo_packball") or {}).get(
                    "distribuicao_janela_ativa"
                ) is True
            )
        ):
            ciclos_ativos.append(ciclo)
    if ciclos_limitados_packball:
        ciclos_ativos = []
    ciclos_ativos = ciclos_ativos[-int(janela_ciclos):]
    ciclos_observados = ciclos_observados[-int(janela_ciclos):]
    utilizacoes = [
        float(ciclo["duracao_detalhada_segundos"])
        / float(ciclo["orcamento_detalhado_segundos"])
        for ciclo in ciclos_ativos
    ]
    utilizacoes_observadas = [
        float(ciclo["duracao_detalhada_segundos"])
        / float(ciclo["orcamento_detalhado_segundos"])
        for ciclo in ciclos_observados
    ]
    excessos_observados = [
        max(
            float(ciclo["duracao_detalhada_segundos"])
            - float(ciclo["orcamento_detalhado_segundos"]),
            0.0,
        )
        for ciclo in ciclos_observados
    ]
    excessos_inesperados_consecutivos = 0
    for ciclo in reversed(ciclos_observados):
        p95_tarefa = ciclo.get("duracao_tarefa_p95_segundos")
        if p95_tarefa is None:
            break
        excesso = max(
            float(ciclo["duracao_detalhada_segundos"])
            - float(ciclo["orcamento_detalhado_segundos"]),
            0.0,
        )
        tolerancia = (
            max(float(p95_tarefa), 0.0)
            + float(margem_ultima_tarefa_segundos)
        )
        if excesso <= tolerancia:
            break
        excessos_inesperados_consecutivos += 1
    pressao_consecutiva = 0
    if not ciclos_limitados_packball:
        for utilizacao in reversed(utilizacoes):
            if utilizacao < float(limiar_pressao):
                break
            pressao_consecutiva += 1
    ultimo = ciclos[-1]
    saturada = consecutivos >= int(limite_consecutivo)
    degradada = pressao_consecutiva >= int(limite_consecutivo)
    excesso_anormal = (
        excessos_inesperados_consecutivos >= int(limite_consecutivo)
    )
    starvation = ciclos_sem_resgate_antigo >= int(limite_consecutivo)
    starvation_pos_evento = (
        ciclos_sem_rechecagem_pos_evento >= int(limite_consecutivo)
    )
    saudavel = (
        not saturada
        and not degradada
        and not excesso_anormal
        and not starvation
        and not starvation_pos_evento
    )
    if saturada:
        estado = "saturada"
        motivo = "capacidade_coleta_saturada"
    elif degradada:
        estado = "degradada"
        motivo = "orcamento_coleta_proximo_limite"
    elif excesso_anormal:
        estado = "degradada"
        motivo = "ciclo_excede_orcamento_mais_ultima_tarefa"
    elif starvation:
        estado = "degradada"
        motivo = "fila_antiga_sem_resgate"
    elif starvation_pos_evento:
        estado = "degradada"
        motivo = "rechecagem_pos_evento_sem_processamento"
    elif pausas_preventivas:
        estado = "protegida_packball"
        motivo = None
    elif ciclos_limitados_packball:
        estado = "limitada_packball"
        motivo = None
    else:
        estado = "saudavel"
        motivo = None
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": motivo,
        "ciclos_adiando": consecutivos,
        "ciclos_pausa_preventiva": pausas_preventivas,
        "ciclos_limitados_packball": ciclos_limitados_packball,
        "ciclos_sob_pressao": pressao_consecutiva,
        "ciclos_sem_resgate_antigo": ciclos_sem_resgate_antigo,
        "starvation_avalia_somente_acionaveis": bool(
            isinstance(
                (ultimo.get("idade_fila") or {}).get(
                    "agendadas_acionaveis"
                ),
                dict,
            )
            or (
                (
                    (ultimo.get("enriquecimento_api_lote") or {})
                    .get("priorizacao") or {}
                ).get("atrasadas_acionaveis") is not None
            )
        ),
        "ciclos_sem_rechecagem_pos_evento": (
            ciclos_sem_rechecagem_pos_evento
        ),
        "limite_consecutivo": int(limite_consecutivo),
        "limiar_pressao_percentual": round(float(limiar_pressao) * 100, 1),
        "janela_ciclos_ativos": len(ciclos_ativos),
        "janela_ciclos_observados": len(ciclos_observados),
        "utilizacao_capacidade_motivo": (
            "limitada_packball"
            if ciclos_limitados_packball and not utilizacoes
            else None
        ),
        "utilizacao_media_percentual": (
            round(sum(utilizacoes) / len(utilizacoes) * 100, 1)
            if utilizacoes else None
        ),
        "utilizacao_p95_percentual": (
            round(percentil_valores(utilizacoes, 0.95) * 100, 1)
            if utilizacoes else None
        ),
        "utilizacao_maxima_percentual": (
            round(max(utilizacoes) * 100, 1) if utilizacoes else None
        ),
        "utilizacao_observada_media_percentual": (
            round(
                sum(utilizacoes_observadas)
                / len(utilizacoes_observadas) * 100,
                1,
            )
            if utilizacoes_observadas else None
        ),
        "utilizacao_observada_p95_percentual": (
            round(
                percentil_valores(utilizacoes_observadas, 0.95) * 100,
                1,
            )
            if utilizacoes_observadas else None
        ),
        "utilizacao_observada_maxima_percentual": (
            round(max(utilizacoes_observadas) * 100, 1)
            if utilizacoes_observadas else None
        ),
        "margem_ultima_tarefa_segundos": float(
            margem_ultima_tarefa_segundos
        ),
        "ciclos_com_excesso_orcamento": sum(
            excesso > 0 for excesso in excessos_observados
        ),
        "ciclos_reserva_adaptativa": sum(
            ciclo.get("interrompido_por_reserva") is True
            for ciclo in ciclos_observados
        ),
        "ultimo_interrompido_por_reserva": (
            ultimo.get("interrompido_por_reserva") is True
        ),
        "ultima_reserva_admissao_segundos": (
            float(ultimo["reserva_admissao_segundos"])
            if ultimo.get("reserva_admissao_segundos") is not None
            else None
        ),
        "ciclos_excesso_inesperado_consecutivos": (
            excessos_inesperados_consecutivos
        ),
        "excesso_orcamento_media_segundos": (
            round(
                sum(excessos_observados) / len(excessos_observados),
                1,
            )
            if excessos_observados else None
        ),
        "excesso_orcamento_p95_segundos": (
            round(percentil_valores(excessos_observados, 0.95), 1)
            if excessos_observados else None
        ),
        "excesso_orcamento_maximo_segundos": (
            round(max(excessos_observados), 1)
            if excessos_observados else None
        ),
        "agendadas": int(ultimo.get("tarefas_agendadas") or 0),
        "processadas": int(ultimo.get("tarefas_processadas") or 0),
        "adiadas": int(ultimo.get("tarefas_adiadas") or 0),
        "idade_fila": dict(ultimo.get("idade_fila") or {}),
        "priorizacao_fila": dict(
            (
                ultimo.get("enriquecimento_api_lote") or {}
            ).get("priorizacao") or {}
        ),
        "perfil_agendamento": dict(
            ultimo.get("perfil_agendamento") or {}
        ),
        "associacoes_api": dict(ultimo.get("associacoes_api") or {}),
        "enriquecimento_api_lote": dict(
            ultimo.get("enriquecimento_api_lote") or {}
        ),
        "gols_antecipados": dict(
            ultimo.get("gols_antecipados") or {}
        ),
        "resgate_qualidade_api": dict(
            ultimo.get("resgate_qualidade_api") or {}
        ),
    }


def verificar_pareamento_api(
    caminho_log,
    ciclos_recentes=3,
    ciclos_base=20,
    minimo_tarefas_recentes=10,
    minimo_tarefas_base=20,
):
    """Detecta colapso relativo sem exigir cobertura universal da API."""
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            evento.get("evento") == "ciclo_concluido"
            and isinstance(evento.get("associacoes_api"), dict)
            and evento.get("associacoes_api")
        ):
            saude_api = evento.get("saude_api") or {}
            if (
                saude_api.get("saudavel") is False
                and saude_api.get("motivo") in {
                    "cota_api_segura_esgotada",
                    "api_ainda_nao_confirmada",
                }
            ):
                continue
            ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
        }

    recentes = ciclos[-int(ciclos_recentes):]
    anteriores = ciclos[
        -int(ciclos_recentes + ciclos_base):-int(ciclos_recentes)
    ]

    def resumir(itens):
        totais = {}
        for ciclo in itens:
            for motivo, quantidade in (
                ciclo.get("associacoes_api") or {}
            ).items():
                try:
                    quantidade = max(int(quantidade), 0)
                except (TypeError, ValueError):
                    continue
                totais[motivo] = totais.get(motivo, 0) + quantidade
        tarefas = sum(totais.values())
        associados = totais.get("associado", 0)
        return {
            "ciclos": len(itens),
            "tarefas": tarefas,
            "associados": associados,
            "taxa_associacao": (
                round(associados / tarefas, 4) if tarefas else None
            ),
            "motivos": totais,
        }

    recente = resumir(recentes)
    base = resumir(anteriores)
    erros = recente["motivos"].get("erro_processamento", 0)
    ambiguas = recente["motivos"].get("associacao_ambigua", 0)
    comparaveis_ambiguidade = recente["associados"] + ambiguas
    taxa_ambiguidade = (
        ambiguas / comparaveis_ambiguidade
        if comparaveis_ambiguidade else 0.0
    )
    recente_suficiente = recente["tarefas"] >= int(
        minimo_tarefas_recentes
    )
    base_suficiente = base["tarefas"] >= int(minimo_tarefas_base)
    colapso = bool(
        recente_suficiente
        and base_suficiente
        and (base["taxa_associacao"] or 0) >= 0.30
        and (recente["taxa_associacao"] or 0)
        < (base["taxa_associacao"] or 0) * 0.25
    )
    ambiguidade_excessiva = bool(
        comparaveis_ambiguidade >= 10 and taxa_ambiguidade >= 0.5
    )
    if erros >= 3:
        motivo = "erros_pareamento_api_repetidos"
    elif ambiguidade_excessiva:
        motivo = "ambiguidade_api_excessiva"
    elif colapso:
        motivo = "cobertura_api_caiu_versus_base"
    else:
        motivo = None
    if motivo:
        estado = "degradado"
    elif recente_suficiente and base_suficiente:
        estado = "avaliavel"
    else:
        estado = "formando_linha_de_base"
    return {
        "saudavel": motivo is None,
        "estado": estado,
        "motivo": motivo,
        "recente": recente,
        "base": base,
        "taxa_ambiguidade": round(taxa_ambiguidade, 4),
        "minimo_tarefas_recentes": int(minimo_tarefas_recentes),
        "minimo_tarefas_base": int(minimo_tarefas_base),
    }


def _preparar_notificacao_operacional(
    conexao, chave, destino, agora, deduplicacao_minutos=10,
    espera_retry_minutos=2, max_tentativas=3, resumo=None,
):
    if deduplicacao_minutos is None:
        entregue = conexao.execute(
            """
            SELECT id FROM notificacoes_operacionais
            WHERE chave=? AND destino=? AND status='entregue'
            ORDER BY id DESC LIMIT 1
            """,
            (chave, destino),
        ).fetchone()
    else:
        limite_deduplicacao = (
            agora - timedelta(minutes=float(deduplicacao_minutos))
        ).isoformat()
        entregue = conexao.execute(
            """
            SELECT id FROM notificacoes_operacionais
            WHERE chave=? AND destino=? AND status='entregue'
              AND datetime(entregue_em) >= datetime(?)
            ORDER BY id DESC LIMIT 1
            """,
            (chave, destino, limite_deduplicacao),
        ).fetchone()
    if entregue is not None:
        return {"estado": "ja_entregue", "id": entregue[0]}
    incerta = conexao.execute(
        """
        SELECT id FROM notificacoes_operacionais
        WHERE chave=? AND destino=?
          AND status IN ('enviando', 'tentando', 'incerto')
        ORDER BY id DESC LIMIT 1
        """,
        (chave, destino),
    ).fetchone()
    if incerta is not None:
        return {"estado": "incerta", "id": incerta[0]}
    erro = conexao.execute(
        """
        SELECT id, tentado_em, tentativas
        FROM notificacoes_operacionais
        WHERE chave=? AND destino=? AND status='erro'
        ORDER BY id DESC LIMIT 1
        """,
        (chave, destino),
    ).fetchone()
    if erro is not None:
        tentativas = int(erro["tentativas"] or 1)
        try:
            tentado_em = datetime.fromisoformat(erro["tentado_em"])
        except (TypeError, ValueError):
            tentado_em = agora
        if (
            max_tentativas is not None
            and tentativas >= int(max_tentativas)
        ):
            return {"estado": "esgotada", "id": erro["id"]}
        if agora - tentado_em < timedelta(minutes=espera_retry_minutos):
            return {"estado": "aguardando_retry", "id": erro["id"]}
        with conexao:
            conexao.execute(
                """
                UPDATE notificacoes_operacionais
                SET status='tentando', tentado_em=?,
                    tentativas=tentativas+1, erro=NULL,
                    resumo=COALESCE(resumo, ?)
                WHERE id=? AND status='erro'
                """,
                (agora.isoformat(), resumo, erro["id"]),
            )
        return {"estado": "enviar", "id": erro["id"]}
    with conexao:
        cursor = conexao.execute(
            """
            INSERT INTO notificacoes_operacionais (
                chave, destino, criado_em, tentado_em,
                status, tentativas, resumo
            ) VALUES (?, ?, ?, ?, 'enviando', 1, ?)
            """,
            (
                chave, destino, agora.isoformat(), agora.isoformat(),
                resumo,
            ),
        )
    return {"estado": "enviar", "id": cursor.lastrowid}


def _concluir_notificacao_operacional(
    conexao, notificacao_id, status, agora, erro=None,
    mensagem_id=None, confirmacao=None,
):
    confirmacao_json = (
        json.dumps(
            confirmacao,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if confirmacao is not None else None
    )
    with conexao:
        conexao.execute(
            """
            UPDATE notificacoes_operacionais
            SET status=?, entregue_em=?, erro=?,
                provedor=CASE WHEN ? IS NOT NULL THEN 'telegram'
                              ELSE provedor END,
                provedor_mensagem_id=COALESCE(
                    provedor_mensagem_id, ?
                ),
                confirmacao_json=COALESCE(confirmacao_json, ?)
            WHERE id=?
            """,
            (
                status,
                agora.isoformat() if status == "entregue" else None,
                erro,
                mensagem_id,
                str(mensagem_id) if mensagem_id is not None else None,
                confirmacao_json,
                int(notificacao_id),
            ),
        )


def _estado_disjuntor_notificacao_operacional(
    conexao,
    destino,
    agora,
    limite_falhas=3,
    janela_minutos=10,
    pausa_minutos=5,
):
    """Evita tempestade de alertas durante indisponibilidade do Telegram."""
    inicio_janela = (
        agora - timedelta(minutes=janela_minutos)
    ).replace(microsecond=0).isoformat()
    linha = conexao.execute(
        """
        SELECT COUNT(*) AS falhas, MAX(falha.tentado_em) AS ultima_falha
        FROM notificacoes_operacionais falha
        WHERE falha.destino=? AND falha.status='erro'
          AND datetime(falha.tentado_em) >= datetime(?)
          AND NOT EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.destino=falha.destino
                AND sucesso.status='entregue'
                AND datetime(sucesso.entregue_em)
                    > datetime(falha.tentado_em)
          )
        """,
        (destino, inicio_janela),
    ).fetchone()
    try:
        falhas = int(linha["falhas"] or 0)
        ultima_falha = linha["ultima_falha"]
    except (TypeError, IndexError):
        falhas = int(linha[0] or 0)
        ultima_falha = linha[1]
    proxima_tentativa_em = None
    pausado = False
    if falhas >= int(limite_falhas) and ultima_falha:
        try:
            proxima = datetime.fromisoformat(ultima_falha) + timedelta(
                minutes=pausa_minutos
            )
            proxima_tentativa_em = proxima.replace(
                microsecond=0
            ).isoformat()
            pausado = agora < proxima
        except (TypeError, ValueError):
            pausado = False
    return {
        "pausado": pausado,
        "destino": destino,
        "falhas_recentes": falhas,
        "limite_falhas": int(limite_falhas),
        "janela_minutos": int(janela_minutos),
        "pausa_minutos": int(pausa_minutos),
        "ultima_falha_em": ultima_falha,
        "proxima_tentativa_em": proxima_tentativa_em,
    }


def formatar_alerta_recuperacao_banco(registro):
    return (
        "🛡️ RECUPERAÇÃO AUTOMÁTICA DO BANCO PACKBALL\n\n"
        "✅ O banco foi restaurado com um backup validado.\n"
        f"Backup utilizado: {registro.get('backup') or '-'}\n"
        f"Motivo: {registro.get('motivo') or '-'}\n"
        f"Restaurado em: {registro.get('restaurado_em') or '-'}\n"
        "Base anterior preservada: "
        f"{registro.get('quarentena') or 'não foi necessária'}\n\n"
        "Monitor e watchdog somente iniciam após a nova verificação de "
        "integridade."
    )


def atualizar_alerta_recuperacao_banco(
    caminho_estado,
    caminho_banco=None,
    enviar=None,
    agora=None,
    espera_retry_minutos=2,
):
    """Entrega uma única confirmação para cada restauração persistida."""
    caminho_estado = Path(caminho_estado)
    agora = (agora or datetime.now()).replace(microsecond=0)
    enviar = enviar or (
        lambda texto: enviar_alerta(
            texto, caminho_banco=caminho_banco, agora=agora
        )
    )
    try:
        registro = json.loads(caminho_estado.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"saudavel": True, "estado": "nunca_necessario"}
    except (OSError, json.JSONDecodeError, TypeError):
        return {
            "saudavel": False,
            "estado": "registro_recuperacao_invalido",
        }
    if (
        not isinstance(registro, dict)
        or registro.get("estado") != "banco_restaurado"
        or not registro.get("backup")
        or not registro.get("restaurado_em")
    ):
        return {
            "saudavel": False,
            "estado": "registro_recuperacao_invalido",
        }
    evento_id = hashlib.sha256(json.dumps(
        {
            "backup": registro.get("backup"),
            "checksum": registro.get("checksum_sha256"),
            "restaurado_em": registro.get("restaurado_em"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    alerta = registro.get("alerta_telegram") or {}
    if (
        alerta.get("evento_id") == evento_id
        and alerta.get("estado") == "entregue"
    ):
        return {
            "saudavel": True,
            "estado": "ja_entregue",
            "evento_id": evento_id,
            "tentativas": int(alerta.get("tentativas", 0) or 0),
        }
    texto_alerta = formatar_alerta_recuperacao_banco(registro)
    chave_alerta = hashlib.sha256(
        texto_alerta.encode("utf-8")
    ).hexdigest()
    if (
        alerta.get("evento_id") == evento_id
        and alerta.get("estado") == "enviando"
        and caminho_banco is not None
    ):
        conexao = None
        try:
            uri = Path(caminho_banco).resolve().as_uri() + "?mode=ro"
            conexao = sqlite3.connect(uri, uri=True, timeout=10)
            linha = conexao.execute(
                """
                SELECT status FROM notificacoes_operacionais
                WHERE chave=? ORDER BY id DESC LIMIT 1
                """,
                (chave_alerta,),
            ).fetchone()
        except (OSError, sqlite3.Error):
            linha = None
        finally:
            if conexao is not None:
                conexao.close()
        status_persistido = linha[0] if linha is not None else None
        if status_persistido == "entregue":
            registro["alerta_telegram"].update({
                "estado": "entregue",
                "entregue_em": agora.isoformat(),
                "proxima_tentativa_em": None,
            })
            try:
                gravar_json_atomico(caminho_estado, registro)
            except OSError as erro:
                return {
                    "saudavel": False,
                    "estado": "persistencia_confirmacao_falhou",
                    "erro": type(erro).__name__,
                    "evento_id": evento_id,
                    "enviado": True,
                }
            return {
                "saudavel": True,
                "estado": "entrega_reconciliada",
                "evento_id": evento_id,
                "tentativas": int(alerta.get("tentativas", 0) or 0),
            }
        if status_persistido in {"enviando", "tentando", "incerto"}:
            return {
                "saudavel": False,
                "estado": "entrega_incerta",
                "evento_id": evento_id,
                "tentativas": int(alerta.get("tentativas", 0) or 0),
            }
    if alerta.get("evento_id") == evento_id:
        proxima = alerta.get("proxima_tentativa_em")
        try:
            aguardando = bool(
                proxima and agora < datetime.fromisoformat(proxima)
            )
        except (TypeError, ValueError):
            aguardando = False
        if aguardando:
            return {
                "saudavel": True,
                "estado": "aguardando_retry",
                "evento_id": evento_id,
                "tentativas": int(alerta.get("tentativas", 0) or 0),
                "proxima_tentativa_em": proxima,
            }

    tentativas = (
        int(alerta.get("tentativas", 0) or 0) + 1
        if alerta.get("evento_id") == evento_id else 1
    )
    registro["alerta_telegram"] = {
        "evento_id": evento_id,
        "estado": "enviando",
        "tentativas": tentativas,
        "tentado_em": agora.isoformat(),
    }
    try:
        gravar_json_atomico(caminho_estado, registro)
    except OSError as erro:
        return {
            "saudavel": False,
            "estado": "persistencia_alerta_falhou",
            "erro": type(erro).__name__,
            "evento_id": evento_id,
        }

    erro_envio = None
    try:
        enviado = bool(enviar(texto_alerta))
    except Exception as erro:
        enviado = False
        erro_envio = type(erro).__name__
    if enviado:
        registro["alerta_telegram"].update({
            "estado": "entregue",
            "entregue_em": agora.isoformat(),
            "proxima_tentativa_em": None,
        })
        estado = "entregue"
    else:
        proxima = agora + timedelta(minutes=espera_retry_minutos)
        registro["alerta_telegram"].update({
            "estado": "erro",
            "erro": erro_envio,
            "proxima_tentativa_em": proxima.isoformat(),
        })
        estado = "erro_temporario"
    try:
        gravar_json_atomico(caminho_estado, registro)
    except OSError as erro:
        return {
            "saudavel": False,
            "estado": "persistencia_confirmacao_falhou",
            "erro": type(erro).__name__,
            "evento_id": evento_id,
            "enviado": enviado,
        }
    return {
        "saudavel": enviado,
        "estado": estado,
        "evento_id": evento_id,
        "tentativas": tentativas,
        "proxima_tentativa_em": (
            registro["alerta_telegram"].get("proxima_tentativa_em")
        ),
    }


def enviar_alerta(
    texto, caminho_banco=None, agora=None, destinos=None,
    chave_evento=None, deduplicacao_minutos=10, max_tentativas=3,
):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    agora = (agora or datetime.now()).replace(microsecond=0)
    caminho_banco = Path(caminho_banco or ARQUIVO_BANCO)
    chave = str(chave_evento or "").strip() or hashlib.sha256(
        str(texto).encode("utf-8")
    ).hexdigest()
    primeira_linha = next(
        (
            linha.strip() for linha in str(texto).splitlines()
            if linha.strip()
        ),
        "notificacao_operacional",
    )
    resumo = resumir_erro_seguro(primeira_linha, limite=160)
    if destinos is None:
        destinos = _destinos_operacionais_configurados()
    else:
        destinos = list(dict.fromkeys(
            str(destino).strip() for destino in destinos if destino
        ))
    if not token or not destinos:
        return False
    conexao = None
    try:
        uri = caminho_banco.resolve().as_uri() + "?mode=rw"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.execute(
            "SELECT 1 FROM notificacoes_operacionais LIMIT 1"
        ).fetchone()
    except (OSError, sqlite3.Error):
        if conexao is not None:
            conexao.close()
        conexao = None
    if conexao is not None:
        if deduplicacao_minutos is None:
            ja_entregue = conexao.execute(
                """
                SELECT 1 FROM notificacoes_operacionais
                WHERE chave=? AND status='entregue'
                LIMIT 1
                """,
                (chave,),
            ).fetchone()
        else:
            limite_deduplicacao = (
                agora - timedelta(minutes=float(deduplicacao_minutos))
            ).isoformat()
            ja_entregue = conexao.execute(
                """
                SELECT 1 FROM notificacoes_operacionais
                WHERE chave=? AND status='entregue'
                  AND datetime(entregue_em) >= datetime(?)
                LIMIT 1
                """,
                (chave, limite_deduplicacao),
            ).fetchone()
        if ja_entregue is not None:
            conexao.close()
            return True
        intencao_incerta = conexao.execute(
            """
            SELECT 1 FROM notificacoes_operacionais
            WHERE chave=? AND status IN ('enviando', 'tentando', 'incerto')
            LIMIT 1
            """,
            (chave,),
        ).fetchone()
        if intencao_incerta is not None:
            conexao.close()
            return False
    for destino in destinos:
        intencao = None
        if conexao is not None:
            try:
                disjuntor = _estado_disjuntor_notificacao_operacional(
                    conexao, destino, agora
                )
                if disjuntor["pausado"]:
                    continue
                intencao = _preparar_notificacao_operacional(
                    conexao,
                    chave,
                    destino,
                    agora,
                    deduplicacao_minutos=deduplicacao_minutos,
                    max_tentativas=max_tentativas,
                    resumo=resumo,
                )
            except sqlite3.Error:
                continue
            if intencao["estado"] == "ja_entregue":
                conexao.close()
                return True
            if intencao["estado"] == "incerta":
                conexao.close()
                return False
            if intencao["estado"] in ("aguardando_retry", "esgotada"):
                continue
        try:
            requisicao = Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=urlencode(
                    {"chat_id": destino, "text": texto}
                ).encode("utf-8"),
                method="POST",
            )
            with urlopen(requisicao, timeout=15) as resposta:
                retorno = json.loads(resposta.read().decode("utf-8"))
            resultado = retorno.get("result") if isinstance(retorno, dict) else None
            mensagem_id = (
                resultado.get("message_id")
                if isinstance(resultado, dict) else None
            )
            if isinstance(mensagem_id, bool):
                mensagem_id = None
            try:
                mensagem_id = int(mensagem_id)
            except (TypeError, ValueError):
                mensagem_id = 0
            if retorno.get("ok") is True and mensagem_id > 0:
                confirmacao = {
                    "message_id": mensagem_id,
                    "ok": True,
                    "provedor": "telegram",
                }
                data_mensagem = resultado.get("date")
                if isinstance(data_mensagem, int) and not isinstance(
                    data_mensagem, bool
                ):
                    confirmacao["date"] = data_mensagem
                if conexao is not None and intencao is not None:
                    try:
                        _concluir_notificacao_operacional(
                            conexao,
                            intencao["id"],
                            "entregue",
                            agora,
                            mensagem_id=mensagem_id,
                            confirmacao=confirmacao,
                        )
                    except sqlite3.Error:
                        conexao.close()
                        return False
                    conexao.close()
                return True
            raise RuntimeError("Telegram confirmou sem message_id valido")
        except Exception as erro:
            if conexao is not None and intencao is not None:
                try:
                    _concluir_notificacao_operacional(
                        conexao,
                        intencao["id"],
                        "erro",
                        agora,
                        erro=f"{type(erro).__name__}: {erro}",
                    )
                except sqlite3.Error:
                    pass
            continue
    if conexao is not None:
        conexao.close()
    return False


def _atualizar_alerta_validacao_imediato(
    validacao, anterior=None, enviar=None, agora=None
):
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    agora = agora or datetime.now()
    integridade_telegram = validacao.get("integridade_telegram") or {}
    envios_incertos = int(
        integridade_telegram.get("envios_incertos", 0) or 0
    )
    envios_oficiais_incertos = int(
        integridade_telegram.get(
            "envios_oficiais_incertos", envios_incertos
        ) or 0
    )
    envios_analise_incertos = int(
        integridade_telegram.get("envios_analise_incertos", 0) or 0
    )
    assinatura = json.dumps(
        {
            "motivos": validacao.get("motivos") or [],
            "avisos": validacao.get("avisos") or [],
            "pendencias_vencidas": validacao.get("pendencias_vencidas", 0),
            "sem_dado_24h": validacao.get("sem_dado_24h", 0),
            "envios_incertos": envios_incertos,
            "envios_oficiais_incertos": envios_oficiais_incertos,
            "envios_analise_incertos": envios_analise_incertos,
            "proveniencia_inconsistente": (
                (validacao.get("proveniencia_resultados") or {}).get(
                    "inconsistentes", 0
                )
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    alertado_anterior = bool(anterior.get("alertado"))
    assinatura_anterior = anterior.get("assinatura_alertada")
    causas_atuais = set(validacao.get("motivos") or []) | set(
        validacao.get("avisos") or []
    )
    causas_notificadas = set(
        anterior.get("causas_validacao_notificadas") or []
    )
    criticos_novos = (
        causas_atuais & MOTIVOS_VALIDACAO_CRITICOS
    ) - causas_notificadas
    envios_incertos_notificados = int(
        anterior.get("envios_incertos_notificados", 0) or 0
    )
    novos_envios_incertos = (
        envios_incertos > envios_incertos_notificados
    )
    if validacao.get("requer_atencao"):
        if (
            not alertado_anterior
            or criticos_novos
            or novos_envios_incertos
        ):
            detalhes = ", ".join(
                (validacao.get("motivos") or [])
                + (validacao.get("avisos") or [])
            ) or "qualidade da validação"
            texto_envios_incertos = ""
            if envios_oficiais_incertos:
                texto_envios_incertos += (
                    "\n🚫 ENVIO OFICIAL SEM CONFIRMAÇÃO\n"
                    f"Há {envios_oficiais_incertos} entrega(s) oficial(is) "
                    "incerta(s).\n"
                    "Novas entradas oficiais estão pausadas até a "
                    "reconciliação.\n"
                    "Confira a conversa no Telegram e, no computador, "
                    "execute: python resolver_envio_incerto.py\n"
                )
            if envios_analise_incertos:
                texto_envios_incertos += (
                    "\n⚠️ RESULTADO DE ANÁLISE SEM CONFIRMAÇÃO\n"
                    f"Há {envios_analise_incertos} notificação(ões) antiga(s) "
                    "aguardando conferência.\n"
                    "Isso não pausa novas análises nem significa falha na "
                    "liquidação esportiva.\n"
                    "Para conferir: python resolver_envio_incerto.py\n"
                )
            enviado = enviar(
                "⚠️ ATENÇÃO OPERACIONAL DO BOT\n\n"
                f"Motivo: {detalhes}\n"
                "Monitor e coleta continuam ativos."
                f"{texto_envios_incertos}"
            )
            validacao["alertado"] = bool(enviado) or alertado_anterior
            validacao["assinatura_alertada"] = (
                assinatura if enviado else assinatura_anterior
            )
            validacao["causas_validacao_notificadas"] = sorted(
                causas_notificadas | causas_atuais
                if enviado else causas_notificadas
            )
            validacao["envios_incertos_notificados"] = (
                envios_incertos
                if enviado
                else envios_incertos_notificados
            )
        else:
            validacao["alertado"] = True
            validacao["assinatura_alertada"] = assinatura_anterior
            validacao["causas_validacao_notificadas"] = sorted(
                causas_notificadas | causas_atuais
            )
            validacao["envios_incertos_notificados"] = min(
                envios_incertos, envios_incertos_notificados
            )
    else:
        if alertado_anterior:
            enviado = enviar(
                "✅ Bot PackBall recuperado: operação normalizada."
            )
            if not enviado:
                validacao["alertado"] = True
                validacao["assinatura_alertada"] = assinatura_anterior
                validacao["causas_validacao_notificadas"] = sorted(
                    causas_notificadas
                )
                validacao["envios_incertos_notificados"] = (
                    envios_incertos_notificados
                )
                return validacao
        validacao["alertado"] = False
        validacao["assinatura_alertada"] = None
        validacao["causas_validacao_notificadas"] = []
        validacao["envios_incertos_notificados"] = 0
    return validacao


def atualizar_alerta_validacao(
    validacao, anterior=None, enviar=None, agora=None
):
    """Estabiliza notificações sem atrasar as travas internas do watchdog."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    agora = agora or datetime.now()
    causas_atuais = set(validacao.get("motivos") or []) | set(
        validacao.get("avisos") or []
    )
    contagens_anteriores = dict(
        anterior.get("alerta_validacao_contagens_causas") or {}
    )
    contagens = {
        causa: int(contagens_anteriores.get(causa, 0) or 0) + 1
        for causa in causas_atuais
    }
    confirmadas = {
        causa for causa in causas_atuais
        if causa not in MOTIVOS_VALIDACAO_OSCILANTES
        or contagens[causa] >= CICLOS_CONFIRMAR_ALERTA_VALIDACAO
    }
    pendentes = causas_atuais - confirmadas
    ultimos_envios = dict(
        anterior.get("alerta_validacao_ultimos_envios") or {}
    )
    if not ultimos_envios and anterior.get("alertado"):
        instante_migracao = agora.replace(microsecond=0).isoformat()
        for causa in (
            anterior.get("causas_validacao_notificadas") or []
        ):
            if causa in MOTIVOS_VALIDACAO_OSCILANTES:
                ultimos_envios[causa] = instante_migracao

    def preservar_estado_alerta(destino):
        destino["alertado"] = bool(anterior.get("alertado"))
        destino["assinatura_alertada"] = anterior.get(
            "assinatura_alertada"
        )
        destino["causas_validacao_notificadas"] = list(
            anterior.get("causas_validacao_notificadas") or []
        )
        destino["envios_incertos_notificados"] = int(
            anterior.get("envios_incertos_notificados", 0) or 0
        )
        return destino

    def anexar_estado_antispam(
        destino, ciclos_recuperacao=0, recuperacao_iniciada_em=None
    ):
        destino["alerta_validacao_contagens_causas"] = contagens
        destino["alerta_validacao_causas_pendentes"] = sorted(pendentes)
        destino["alerta_validacao_ciclos_recuperacao"] = int(
            ciclos_recuperacao
        )
        destino["alerta_validacao_recuperacao_iniciada_em"] = (
            recuperacao_iniciada_em
        )
        destino["alerta_validacao_recuperacao_pendente"] = bool(
            destino.get("alertado")
            and not validacao.get("requer_atencao")
        )
        destino["alerta_validacao_ultimos_envios"] = ultimos_envios
        return destino

    if validacao.get("requer_atencao"):
        if not confirmadas:
            return anexar_estado_antispam(
                preservar_estado_alerta(validacao)
            )

        filtrada = dict(validacao)
        filtrada["motivos"] = [
            causa for causa in (validacao.get("motivos") or [])
            if causa in confirmadas
        ]
        filtrada["avisos"] = [
            causa for causa in (validacao.get("avisos") or [])
            if causa in confirmadas
        ]
        notificadas = set(
            anterior.get("causas_validacao_notificadas") or []
        )
        criticas_novas = (
            confirmadas & MOTIVOS_VALIDACAO_CRITICOS
        ) - notificadas
        integridade = validacao.get("integridade_telegram") or {}
        envios_incertos = int(integridade.get("envios_incertos", 0) or 0)
        envios_anteriores = int(
            anterior.get("envios_incertos_notificados", 0) or 0
        )
        novo_envio_incerto = envios_incertos > envios_anteriores
        disparadoras = (
            confirmadas if not anterior.get("alertado") else criticas_novas
        )
        cooldown_bloqueia = bool(disparadoras) and all(
            causa in MOTIVOS_VALIDACAO_OSCILANTES
            and _alerta_validacao_em_cooldown(
                ultimos_envios.get(causa), agora
            )
            for causa in disparadoras
        )
        if cooldown_bloqueia and not novo_envio_incerto:
            return anexar_estado_antispam(
                preservar_estado_alerta(validacao)
            )

        assinatura_anterior = anterior.get("assinatura_alertada")
        resultado = _atualizar_alerta_validacao_imediato(
            filtrada, anterior, enviar=enviar, agora=agora
        )
        enviado_agora = bool(resultado.get("alertado")) and (
            resultado.get("assinatura_alertada") != assinatura_anterior
            or not anterior.get("alertado")
        )
        if enviado_agora:
            instante = agora.replace(microsecond=0).isoformat()
            for causa in confirmadas:
                ultimos_envios[causa] = instante
        return anexar_estado_antispam(resultado)

    ciclos_recuperacao = 0
    recuperacao_iniciada_em = None
    if anterior.get("alertado"):
        ciclos_recuperacao = int(
            anterior.get("alerta_validacao_ciclos_recuperacao", 0) or 0
        ) + 1
        recuperacao_iniciada_em = anterior.get(
            "alerta_validacao_recuperacao_iniciada_em"
        )
        try:
            inicio_recuperacao = datetime.fromisoformat(
                recuperacao_iniciada_em
            )
            tempo_saudavel = agora - inicio_recuperacao
            if tempo_saudavel < timedelta(0):
                raise ValueError("instante de recuperacao no futuro")
        except (TypeError, ValueError):
            tempo_saudavel = timedelta(0)
            recuperacao_iniciada_em = agora.replace(
                microsecond=0
            ).isoformat()
        recuperacao_pronta = bool(
            ciclos_recuperacao
            >= CICLOS_CONFIRMAR_RECUPERACAO_VALIDACAO
            and tempo_saudavel
            >= timedelta(
                minutes=MINUTOS_CONFIRMAR_RECUPERACAO_VALIDACAO
            )
        )
        if not recuperacao_pronta:
            return anexar_estado_antispam(
                preservar_estado_alerta(validacao),
                ciclos_recuperacao,
                recuperacao_iniciada_em,
            )
    resultado = _atualizar_alerta_validacao_imediato(
        validacao, anterior, enviar=enviar, agora=agora
    )
    if not resultado.get("alertado"):
        ciclos_recuperacao = 0
        recuperacao_iniciada_em = None
    return anexar_estado_antispam(
        resultado, ciclos_recuperacao, recuperacao_iniciada_em
    )


def _alerta_validacao_em_cooldown(ultimo_envio, agora):
    try:
        instante = datetime.fromisoformat(ultimo_envio)
    except (TypeError, ValueError):
        return False
    return agora - instante < timedelta(
        hours=COOLDOWN_ALERTA_VALIDACAO_HORAS
    )


def atualizar_alerta_experimento_ritmo(
    validacao, anterior=None, enviar=None
):
    """Notifica uma única vez cada decisão do experimento operacional."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    experimento = validacao.get("experimento_ritmo_packball") or {}
    estado = experimento.get("estado")
    assinatura = "|".join(str(item or "") for item in (
        experimento.get("versao"),
        experimento.get("regime_atual"),
        experimento.get("iniciado_em"),
        estado,
    ))
    anterior_assinatura = anterior.get(
        "experimento_ritmo_assinatura_notificada"
    )
    historico_bruto = anterior.get(
        "experimento_ritmo_assinaturas_notificadas"
    )
    historico = []
    if isinstance(historico_bruto, (list, tuple)):
        for item in historico_bruto:
            item = str(item or "")
            if item and item not in historico:
                historico.append(item)
    if anterior_assinatura and anterior_assinatura not in historico:
        historico.append(anterior_assinatura)
    historico = historico[-LIMITE_ASSINATURAS_RITMO_NOTIFICADAS:]

    def persistir(assinatura_atual=None, registrar=False):
        if registrar and assinatura not in historico:
            historico.append(assinatura)
        validacao["experimento_ritmo_assinaturas_notificadas"] = (
            historico[-LIMITE_ASSINATURAS_RITMO_NOTIFICADAS:]
        )
        validacao["experimento_ritmo_assinatura_notificada"] = (
            assinatura_atual
            if assinatura_atual is not None
            else anterior_assinatura
        )
        return validacao

    if (
        estado == "regressao_recomendada"
        and "experimento_ritmo_packball_regressao"
        in (validacao.get("alerta_validacao_causas_pendentes") or [])
    ):
        return persistir()
    if (
        estado == "aprovado"
        and (
            validacao.get("alertado")
            or validacao.get("alerta_validacao_recuperacao_pendente")
        )
    ):
        return persistir()
    if not experimento.get("avaliavel") or not estado:
        return persistir()
    if assinatura in historico:
        return persistir(assinatura)
    if estado in ("em_observacao", "inativo", "aguardando_telemetria"):
        return persistir(assinatura)

    # A regressão já pertence ao alerta crítico da validação. Quando a
    # confirmação desse alerta foi persistida, não cria uma segunda mensagem.
    if (
        estado == "regressao_recomendada"
        and "experimento_ritmo_packball_regressao"
        in (validacao.get("causas_validacao_notificadas") or [])
    ):
        return persistir(assinatura, registrar=True)
    # Se a validação acabou de enviar sua recuperação, ela também comunica a
    # volta do ritmo seguro; evita uma segunda mensagem no mesmo ciclo.
    if (
        estado == "aprovado"
        and anterior.get("alertado")
        and not validacao.get("alertado")
    ):
        return persistir(assinatura, registrar=True)

    teste = experimento.get("experimento") or {}
    base = experimento.get("base") or {}
    if estado == "aprovado":
        titulo = "✅ RITMO PACKBALL VALIDADO"
        conclusao = (
            "O novo ritmo foi aprovado para continuar. Isso mede somente a "
            "coleta e não representa confiança dos sinais."
        )
    elif estado == "rollback_acionado":
        titulo = "🛡️ ROLLBACK DE SEGURANÇA DO PACKBALL ATIVO"
        conclusao = (
            "O monitor voltou aos limites conservadores. A coleta pode "
            "continuar, sem aumento automático de velocidade."
        )
    else:
        titulo = "🚨 REGRESSÃO NO RITMO DO PACKBALL"
        conclusao = (
            "O experimento não manteve os limites operacionais; revise o "
            "ritmo antes de qualquer novo aumento."
        )
    mensagem = (
        f"{titulo}\n\n"
        f"Estado: {estado}\n"
        f"Ciclos observados: {teste.get('ciclos', 0)}\n"
        f"Tempo observado: {experimento.get('minutos_observados')} min\n"
        "Fluxo base/atual: "
        f"{base.get('processadas_por_10_minutos')} / "
        f"{teste.get('processadas_por_10_minutos')} por 10 min\n"
        "Retenção de fluxo: "
        f"{experimento.get('retencao_fluxo')}\n"
        "Cobertura temporal base/atual: "
        f"{base.get('cobertura_temporal')} / "
        f"{teste.get('cobertura_temporal')}\n"
        "Retenção temporal: "
        f"{experimento.get('retencao_temporal')}\n"
        "Incidentes na janela atual: "
        f"{experimento.get('pausas_na_revalidacao', experimento.get('pausas_packball', 0))}\n"
        "Incidentes historicos preservados: "
        f"{experimento.get('pausas_packball_historicas', experimento.get('pausas_packball', 0))}\n\n"
        f"{conclusao}"
    )
    if enviar is enviar_alerta:
        chave_evento = (
            "watchdog:experimento_ritmo:"
            + hashlib.sha256(assinatura.encode("utf-8")).hexdigest()
        )
        enviado = enviar(
            mensagem,
            chave_evento=chave_evento,
            deduplicacao_minutos=None,
        )
    else:
        enviado = enviar(mensagem)
    if enviado:
        return persistir(assinatura, registrar=True)
    return persistir()


def atualizar_alerta_experimento_filtro(
    validacao, anterior=None, enviar=None
):
    """Notifica uma única vez a conclusão imutável de cada experimento."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    conclusao_congelada = (
        validacao.get("conclusao_filtro_simulacoes") or {}
    )
    geral = conclusao_congelada.get("evidencia") or {}
    assinatura_anterior = anterior.get(
        "experimento_filtro_assinatura_notificada"
    )
    if (
        geral.get("estado") != "avaliavel"
        or not conclusao_congelada.get("concluido_em")
    ):
        validacao["experimento_filtro_assinatura_notificada"] = (
            assinatura_anterior
        )
        return validacao

    decisao = conclusao_congelada.get("decisao") or "nao_comprovado"
    assinatura = "|".join(str(item or "") for item in (
        conclusao_congelada.get("versao"),
        conclusao_congelada.get("concluido_em"),
        conclusao_congelada.get("regra_fingerprint"),
    ))
    if assinatura == assinatura_anterior:
        validacao["experimento_filtro_assinatura_notificada"] = assinatura
        return validacao

    favoravel = decisao == "evidencia_favoravel"
    titulo = (
        "✅ EXPERIMENTO CONCLUÍDO — FILTRO COM VANTAGEM COMPROVADA"
        if favoravel
        else "⚠️ EXPERIMENTO CONCLUÍDO — FILTRO NÃO PROMOVIDO"
    )
    conclusao = (
        "A seleção apresentou vantagem estatística pelos critérios "
        "pré-definidos."
        if favoravel
        else "A amostra mínima foi atingida sem comprovar vantagem. "
        "O filtro permanece apenas como regra de simulação."
    )
    mensagem = (
        f"{titulo}\n\n"
        "Enviadas: "
        f"{geral.get('decisoes_enviadas', 0)} decisoes | "
        f"{geral.get('amostra_enviadas', 0)} resultados validos | "
        f"{geral.get('pendentes_enviadas', 0)} pendentes\n"
        "Filtradas: "
        f"{geral.get('decisoes_filtradas', 0)} decisoes | "
        f"{geral.get('amostra_filtradas', 0)} resultados validos | "
        f"{geral.get('pendentes_filtradas', 0)} pendentes\n"
        f"Mínimo por grupo: "
        f"{geral.get('amostra_minima_por_coorte', 30)}\n"
        f"Diferença de acerto: {geral.get('delta_taxa_acerto')}\n"
        "IC95 da diferença de acerto: "
        f"{geral.get('intervalo_delta_taxa_acerto_95')}\n"
        f"Diferença de ROI: {geral.get('delta_roi')}\n"
        "IC95 da diferença de ROI: "
        f"{geral.get('intervalo_delta_roi_95')}\n\n"
        f"{conclusao}\n"
        "Esta conclusão foi congelada e não muda com resultados futuros. "
        "Um novo teste exige nova versão previamente registrada."
    )
    enviado = enviar(mensagem)
    validacao["experimento_filtro_assinatura_notificada"] = (
        assinatura if enviado else assinatura_anterior
    )
    return validacao


def atualizar_alertas_filtros_regras_ativas(
    validacao, anterior=None, enviar=None
):
    """Notifica uma vez quando uma regra ativa completa os dois grupos."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave_estado = "filtros_regras_ativas_marcos_notificados"
    estado_existia = chave_estado in anterior
    notificados = dict(anterior.get(chave_estado) or {})
    comparacoes_anteriores = {
        (
            item.get("mercado"),
            item.get("regra_versao"),
            int(
                ((item.get("comparacao") or {}).get(
                    "amostra_minima_por_coorte", 30
                )) or 30
            ),
        ): item
        for item in (
            anterior.get("comparacao_filtros_regras_ativas") or []
        )
        if item.get("mercado") and item.get("regra_versao")
    }

    for item in validacao.get("comparacao_filtros_regras_ativas") or []:
        mercado = item.get("mercado")
        regra_versao = item.get("regra_versao")
        comparacao = item.get("comparacao") or {}
        minimo = int(
            comparacao.get("amostra_minima_por_coorte", 30) or 30
        )
        if (
            not mercado
            or not regra_versao
            or comparacao.get("estado") != "avaliavel"
        ):
            continue

        chave = f"{mercado}|{regra_versao}|{minimo}"
        decisao = comparacao.get("decisao") or "nao_comprovado"
        assinatura = f"{chave}|{decisao}"
        if chave in notificados:
            continue

        anterior_item = comparacoes_anteriores.get(
            (mercado, regra_versao, minimo)
        )
        anterior_avaliavel = (
            ((anterior_item or {}).get("comparacao") or {}).get("estado")
            == "avaliavel"
        )
        # Na implantação, resultados que já estavam completos viram apenas
        # a linha de base. Assim o Telegram não recebe um marco antigo.
        if not estado_existia and (
            anterior_item is None or anterior_avaliavel
        ):
            notificados[chave] = assinatura
            continue

        enviadas = item.get("enviadas") or {}
        filtradas = item.get("filtradas") or {}

        def roi_texto(metricas):
            roi = metricas.get("roi")
            return "-" if roi is None else f"{float(roi) * 100:+.1f}%"

        estado_decisao = {
            "evidencia_favoravel": "evidência favorável para revisão",
            "nao_comprovado": "vantagem não comprovada",
        }.get(decisao, decisao)
        mensagem = (
            "📊 AMOSTRA 30/30 COMPLETA — REVISÃO NECESSÁRIA\n\n"
            f"Mercado: {ROTULOS_MERCADOS.get(mercado, mercado)}\n"
            f"Regra ativa: {regra_versao}\n"
            f"Mínimo atingido: {minimo} resultados por grupo\n\n"
            "Enviados: "
            f"{int(enviadas.get('greens', 0) or 0)} G / "
            f"{int(enviadas.get('reds', 0) or 0)} R | "
            f"ROI {roi_texto(enviadas)}\n"
            "Filtrados: "
            f"{int(filtradas.get('greens', 0) or 0)} G / "
            f"{int(filtradas.get('reds', 0) or 0)} R | "
            f"ROI {roi_texto(filtradas)}\n"
            f"Leitura estatística: {estado_decisao}\n\n"
            "Este marco apenas abre uma revisão manual e não promove "
            "automaticamente nenhuma regra. Os sinais continuam sujeitos "
            "aos controles e à validação cronológica."
        )
        if enviar(mensagem):
            notificados[chave] = assinatura

    validacao[chave_estado] = notificados
    return validacao


def atualizar_alerta_hipoteses_sombra(
    validacao, anterior=None, enviar=None
):
    """Notifica conclusões novas sem promover o corte automaticamente."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    estados_anteriores = dict(
        anterior.get("hipoteses_sombra_estados_notificados") or {}
    )
    estados_atualizados = dict(estados_anteriores)
    avaliacoes = (
        (validacao.get("hipoteses_sombra") or {}).get("avaliacoes")
        or []
    )
    incompativeis = []
    for item in avaliacoes:
        estado = item.get("estado")
        identificador = item.get("identificador")
        versao_avaliacao = item.get("versao_avaliacao")
        if (
            estado in ("confirmada", "refutada")
            and versao_avaliacao
            != VERSAO_AVALIACAO_HIPOTESES_SOMBRA
        ):
            if identificador:
                incompativeis.append(identificador)
            continue
        if (
            not identificador
            or estado not in ("confirmada", "refutada")
            or estados_anteriores.get(identificador) == estado
        ):
            continue
        selecionada = item.get("selecionada") or {}
        baseline = item.get("baseline") or {}
        controle = item.get("controle_excluido") or {}
        intervalo_delta_roi = item.get("intervalo_delta_roi_95")
        confirmada = estado == "confirmada"
        titulo = (
            "✅ HIPÓTESE SOMBRA CONFIRMADA PARA REVISÃO"
            if confirmada
            else "⚠️ HIPÓTESE SOMBRA REFUTADA"
        )
        conclusao = (
            "O corte pode ser revisado manualmente para uma futura versão."
            if confirmada
            else "O corte não deve ser promovido para a regra."
        )
        mensagem = (
            f"{titulo}\n\n"
            f"Mercado: {ROTULOS_MERCADOS.get(item.get('mercado'), item.get('mercado'))}\n"
            f"Corte: {item.get('descricao_corte') or '-'}\n"
            f"Resultados independentes: {selecionada.get('amostra', 0)}\n"
            f"Acerto do corte: {selecionada.get('taxa_acerto')}\n"
            f"ROI do corte: {selecionada.get('roi')}\n"
            f"ROI baseline: {baseline.get('roi')}\n"
            "Controle excluído: "
            f"{controle.get('amostra', 0)} resultado(s)\n"
            f"ROI do controle: {controle.get('roi')}\n"
            "Diferença de ROI corte-controle: "
            f"{item.get('delta_roi_selecionada_controle')}\n"
            f"IC95 da diferença: {intervalo_delta_roi}\n"
            "Política de avaliação: "
            f"{versao_avaliacao}\n\n"
            f"{conclusao}\n"
            "Nenhuma regra foi alterada automaticamente."
        )
        if enviar(mensagem):
            estados_atualizados[identificador] = estado
    validacao["hipoteses_sombra_estados_notificados"] = (
        estados_atualizados
    )
    validacao["hipoteses_sombra_avaliacoes_incompativeis"] = sorted(
        set(incompativeis)
    )
    return validacao


MARCOS_VALIDACAO_EXPLORACAO_GOLS = (10, 20, 30)


def atualizar_marcos_exploracao_gols(
    validacao, anterior=None, enviar=None
):
    """Avisa progresso futuro sem transformar amostra em aprovação."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    notificados = dict(
        anterior.get("exploracao_gols_marcos_notificados") or {}
    )
    progresso = (
        (validacao.get("exploracao_sombra") or {}).get(
            "validacao_prospectiva_gols"
        ) or {}
    )
    for mercado, item in sorted(progresso.items()):
        versao = item.get("versao")
        avaliadas = int(item.get("avaliadas", 0) or 0)
        anterior_mercado = notificados.get(mercado) or {}
        marco_anterior = (
            int(anterior_mercado.get("marco", 0) or 0)
            if anterior_mercado.get("versao") == versao else 0
        )
        elegiveis = [
            marco for marco in MARCOS_VALIDACAO_EXPLORACAO_GOLS
            if marco_anterior < marco <= avaliadas
        ]
        if not elegiveis or not versao:
            continue
        marco = max(elegiveis)
        final = marco == max(MARCOS_VALIDACAO_EXPLORACAO_GOLS)
        julgamento = item.get("decisao_estatistica")
        titulos_finais = {
            "favoravel_para_revisao_independente": (
                "✅ AMOSTRA DE GOLS FAVORÁVEL PARA REVISÃO"
            ),
            "inconclusiva": (
                "⚠️ AMOSTRA DE GOLS CONCLUÍDA — EVIDÊNCIA INCONCLUSIVA"
            ),
            "evidencia_desfavoravel": (
                "❌ AMOSTRA DE GOLS CONCLUÍDA — EVIDÊNCIA DESFAVORÁVEL"
            ),
            "linhagem_inconsistente": (
                "🚫 AMOSTRA DE GOLS COM LINHAGEM INCONSISTENTE"
            ),
        }
        titulo = (
            titulos_finais.get(
                julgamento,
                "📊 AMOSTRA DE GOLS CONCLUÍDA PARA REVISÃO",
            )
            if final else "📊 PROGRESSO DA VALIDAÇÃO DE GOLS"
        )
        rotulo = ROTULOS_MERCADOS.get(mercado, mercado)
        mensagem = (
            f"{titulo}\n\n"
            f"Mercado: {rotulo}\n"
            f"Versão: {versao}\n"
            f"Resultados futuros: {avaliadas}/"
            f"{item.get('minimo_resultados', 30)}\n"
            f"Placar: {item.get('greens', 0)} GREEN / "
            f"{item.get('reds', 0)} RED\n"
            f"Taxa de acerto: {item.get('taxa_acerto')}\n"
            f"ROI: {item.get('roi')}\n"
            f"IC95 do ROI: {item.get('intervalo_roi_95')}\n"
            "Julgamento pré-registrado: "
            f"{julgamento}\n"
            "Política: "
            f"{item.get('politica_avaliacao_versao')}\n"
            f"Lucro hipotético: {item.get('lucro_unidades', 0.0)}u\n\n"
            + (
                (
                    "Os critérios pré-registrados foram favoráveis. Isso "
                    "libera somente uma revisão independente; o mercado "
                    "ainda não está aprovado automaticamente."
                    if julgamento == "favoravel_para_revisao_independente"
                    else
                    "A janela fixa foi concluída, mas não comprovou vantagem "
                    "estatística. O mercado permanece bloqueado e nenhuma "
                    "regra será alterada automaticamente."
                )
                if final else
                "A coleta permanece em modo sombra, sem envio de entrada e "
                "sem alterar a calibração oficial."
            )
        )
        if enviar(mensagem):
            notificados[mercado] = {
                "versao": versao,
                "marco": marco,
            }
    validacao["exploracao_gols_marcos_notificados"] = notificados
    return validacao


def aplicar_circuit_breaker_pre_live_preciso(
    pre_live, caminho_estado=None, agora=None
):
    """Pausa apenas a entrega pre-live; a coorte sombra continua."""
    pre_live = dict(pre_live or {})
    validacao = dict(pre_live.get("filtro_preciso") or {})
    caminho_estado = caminho_estado or ARQUIVO_ESTADO_PRE_LIVE_PRECISO
    estado = aplicar_controle_pre_live_preciso(
        validacao,
        caminho=caminho_estado,
        agora=agora,
    )
    validacao["controle_operacional"] = {
        "versao": estado.get("versao"),
        "saudavel": estado.get("saudavel"),
        "ativo": estado.get("ativo"),
        "estado": estado.get("estado"),
        "motivo": estado.get("motivo"),
        "assinatura": estado.get("assinatura"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    pre_live["filtro_preciso"] = validacao
    pre_live["controle_filtro_preciso"] = estado
    if (
        not estado.get("saudavel")
        or validacao.get("saudavel") is False
    ):
        pre_live["saudavel"] = False
        pre_live["motivo_filtro_preciso"] = (
            "controle_pre_live_preciso_inconsistente"
            if not estado.get("saudavel")
            else "validacao_pre_live_preciso_inconsistente"
        )
    return pre_live


def atualizar_alerta_circuit_breaker_pre_live_preciso(
    estado, anterior=None, enviar=None
):
    """Notifica uma vez cada suspensao automatica da entrega pre-live."""
    estado = dict(estado or {})
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave = "pre_live_preciso_breaker_notificado"
    notificado = anterior.get(chave)
    estado[chave] = notificado
    controle = (
        (estado.get("pre_live") or {}).get("controle_filtro_preciso") or {}
    )
    if not (
        controle.get("ativo") is False
        and controle.get("estado") == "suspenso_automatico"
    ):
        return estado
    assinatura = str(controle.get("assinatura") or "sem_assinatura")
    if notificado == assinatura:
        return estado
    metricas = controle.get("metricas") or {}
    intervalo = metricas.get("intervalo_roi_95")
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        intervalo_texto = (
            f"[{float(intervalo[0]) * 100:.1f}%, "
            f"{float(intervalo[1]) * 100:.1f}%]"
        )
    else:
        intervalo_texto = "indisponivel"
    roi = metricas.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:.1f}%"
    coorte_concluida = bool(metricas.get("coorte_concluida"))
    validacao_inconsistente = bool(
        controle.get("motivo") == "validacao_pre_live_preciso_inconsistente"
    )
    conclusao = (
        "A validacao prospectiva ficou inconsistente e falhou fechada."
        if validacao_inconsistente else
        "A coorte fixa chegou a 60 e foi fechada para revisao humana."
        if coorte_concluida else
        "O checkpoint fixo dos 25 primeiros casos comprovou ROI negativo."
    )
    mensagem = (
        "🛑 PRE-LIVE PRECISO — ENTREGA SUSPENSA\n\n"
        f"Amostra valida: {int(metricas.get('validos', 0) or 0)}\n"
        f"Placar: {int(metricas.get('greens', 0) or 0)} GREEN / "
        f"{int(metricas.get('reds', 0) or 0)} RED\n"
        f"ROI: {roi_texto}\n"
        f"IC95 do ROI: {intervalo_texto}\n\n"
        f"{conclusao} A geracao e a liquidacao sombra continuam, e nenhum "
        "mercado ao vivo foi alterado."
    )
    if enviar(mensagem):
        estado[chave] = assinatura
    return estado


def aplicar_circuit_breaker_proximo_gol_balanceado(
    validacao, caminho_estado=None, agora=None
):
    """Pausa só o grupo do balanceado; a coorte sombra segue intacta."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_PROXIMO_GOL_BALANCEADO
    )
    progresso = (
        validacao.get("progresso_proximo_gol_balanceado_sombra") or {}
    )
    estado = ler_estado_proximo_gol_balanceado(caminho_estado)
    evidencia_negativa = bool(progresso.get("rollback_recomendado"))
    coorte_concluida = bool(progresso.get("resultados_completos"))
    if (evidencia_negativa or coorte_concluida) and estado.get("ativo"):
        assinatura = "|".join((
            str(progresso.get("versao") or "sem_validacao"),
            str(progresso.get("registrado_em") or "sem_ancora"),
            str(progresso.get("definicao_sha256") or "sem_definicao"),
        ))
        motivo = (
            "ic95_roi_checkpoint_20_integralmente_negativo"
            if evidencia_negativa
            else "coorte_40_concluida_aguardando_revisao_manual"
        )
        estado = suspender_proximo_gol_balanceado(
            assinatura,
            motivo,
            metricas={
                "validos": int(progresso.get("validos", 0) or 0),
                "greens": int(progresso.get("greens", 0) or 0),
                "reds": int(progresso.get("reds", 0) or 0),
                "roi": progresso.get("roi"),
                "intervalo_roi_95": progresso.get("intervalo_roi_95"),
                "checkpoint_seguranca": progresso.get(
                    "checkpoint_seguranca"
                ),
                "coorte_concluida": coorte_concluida,
                "coleta_sombra_continua": True,
            },
            caminho=caminho_estado,
            agora=agora,
            automatico=True,
        )
    validacao["controle_operacional_proximo_gol_balanceado"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        validacao.setdefault("motivos", []).append(
            "controle_proximo_gol_balanceado_inconsistente"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao


def atualizar_alerta_circuit_breaker_proximo_gol_balanceado(
    validacao, anterior=None, enviar=None
):
    """Notifica uma única vez cada suspensão persistente do balanceado."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave = "proximo_gol_balanceado_breaker_notificado"
    notificado = anterior.get(chave)
    validacao[chave] = notificado
    controle = validacao.get(
        "controle_operacional_proximo_gol_balanceado"
    ) or {}
    if not (
        controle.get("ativo") is False
        and controle.get("estado") == "sombra_automatico"
    ):
        return validacao
    assinatura = str(controle.get("assinatura") or "sem_assinatura")
    if notificado == assinatura:
        return validacao
    metricas = controle.get("metricas") or {}
    intervalo = metricas.get("intervalo_roi_95")
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        intervalo_texto = (
            f"[{float(intervalo[0]) * 100:.1f}%, "
            f"{float(intervalo[1]) * 100:.1f}%]"
        )
    else:
        intervalo_texto = "indisponível"
    roi = metricas.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:.1f}%"
    coorte_concluida = bool(metricas.get("coorte_concluida"))
    titulo = (
        "🧪 PRÓXIMO GOL BALANCEADO — COORTE CONCLUÍDA\n\n"
        if coorte_concluida else
        "🛑 PRÓXIMO GOL BALANCEADO — GRUPO PAUSADO\n\n"
    )
    conclusao = (
        "A coorte fixa chegou a 40 e o grupo foi fechado. Nenhum novo teste "
        "será entregue até uma revisão humana da evidência completa."
        if coorte_concluida else
        "O envio ao grupo de teste foi suspenso porque o checkpoint fixo dos "
        "20 primeiros casos apresentou evidência integralmente negativa."
    )
    mensagem = (
        titulo
        +
        f"Amostra válida: {int(metricas.get('validos', 0) or 0)}\n"
        f"Placar: {int(metricas.get('greens', 0) or 0)} GREEN / "
        f"{int(metricas.get('reds', 0) or 0)} RED\n"
        f"ROI: {roi_texto}\n"
        f"IC95 do ROI: {intervalo_texto}\n\n"
        f"{conclusao} A coleta silenciosa permanece preservada e nenhum "
        "outro mercado foi alterado."
    )
    if enviar(mensagem):
        validacao[chave] = assinatura
    return validacao


def atualizar_alerta_grupo_gol_ft_capacidade_v2(
    validacao, anterior=None, enviar=None
):
    """Avisa uma vez se a coorte ativa comprovar ROI negativo."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave_estado = "grupo_gol_ft_capacidade_v2_alerta_notificado"
    notificado = anterior.get(chave_estado)
    validacao[chave_estado] = notificado
    progresso = (
        validacao.get("progresso_grupo_gol_ft_capacidade_v2") or {}
    )
    if not progresso.get("alerta_desfavoravel"):
        return validacao
    assinatura = "|".join((
        str(progresso.get("versao") or "sem_versao"),
        str(progresso.get("registrado_em") or "sem_ancora"),
    ))
    if not assinatura or notificado == assinatura:
        return validacao
    intervalo = progresso.get("intervalo_roi_95")
    roi = progresso.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:.1f}%"
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        intervalo_texto = (
            f"[{float(intervalo[0]) * 100:.1f}%, "
            f"{float(intervalo[1]) * 100:.1f}%]"
        )
    else:
        intervalo_texto = "indisponível"
    controle = validacao.get("controle_operacional_v2b_ft") or {}
    pausado_automaticamente = bool(
        controle.get("ativo") is False
        and controle.get("estado") == "sombra_automatico"
    )
    titulo = (
        "🛑 V2b FT — RETORNO AUTOMÁTICO AO SOMBRA\n\n"
        if pausado_automaticamente else
        "⚠️ V2b FT — RETORNO AO SOMBRA RECOMENDADO\n\n"
    )
    mensagem = (
        titulo
        +
        f"Amostra enviada: {int(progresso.get('validos', 0) or 0)}\n"
        f"Placar: {int(progresso.get('greens', 0) or 0)} GREEN / "
        f"{int(progresso.get('reds', 0) or 0)} RED\n"
        f"ROI: {roi_texto}\n"
        f"IC95 do ROI: {intervalo_texto}\n\n"
        "A evidência estatística ficou integralmente negativa. "
        + (
            "O envio deste método foi pausado; os demais mercados continuam "
            "ativos. O histórico permanece preservado para revisão."
            if pausado_automaticamente else
            "O histórico permanece preservado para revisão."
        )
    )
    if enviar(mensagem):
        validacao[chave_estado] = assinatura
    return validacao


def aplicar_circuit_breaker_grupo_gol_ft_capacidade_v2(
    validacao, caminho_estado=None, agora=None
):
    """Suspende apenas o V2b FT quando o IC95 do ROI é todo negativo."""
    caminho_estado = caminho_estado or ARQUIVO_ESTADO_V2B_FT
    progresso = (
        validacao.get("progresso_grupo_gol_ft_capacidade_v2") or {}
    )
    estado = ler_estado_v2b_ft(caminho_estado)
    if progresso.get("rollback_recomendado") and estado.get("ativo"):
        assinatura = "|".join((
            str(progresso.get("versao") or "sem_versao"),
            str(progresso.get("registrado_em") or "sem_ancora"),
        ))
        estado = suspender_v2b_ft(
            assinatura,
            "ic95_roi_integralmente_negativo",
            metricas={
                "validos": int(progresso.get("validos", 0) or 0),
                "greens": int(progresso.get("greens", 0) or 0),
                "reds": int(progresso.get("reds", 0) or 0),
                "roi": progresso.get("roi"),
                "intervalo_roi_95": progresso.get("intervalo_roi_95"),
            },
            caminho=caminho_estado,
            agora=agora,
            automatico=True,
        )
    validacao["controle_operacional_v2b_ft"] = estado
    progresso["grupo_ativo"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        validacao.setdefault("motivos", []).append(
            "controle_v2b_ft_inconsistente"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao


def aplicar_circuit_breaker_filtro_gol_ft_preciso(
    validacao, caminho_estado=None, agora=None
):
    """Pausa somente a entrega do FT antecipado que passou no filtro V2."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_FILTRO_GOL_FT_PRECISO
    )
    progresso = validacao.get("progresso_filtro_gol_ft_preciso") or {}
    estado = aplicar_controle_filtro_gol_ft_preciso(
        progresso,
        caminho=caminho_estado,
        agora=agora,
    )
    validacao["controle_operacional_filtro_gol_ft_preciso"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "assinatura": estado.get("assinatura"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        motivo = "controle_filtro_gol_ft_preciso_inconsistente"
        if motivo not in validacao.setdefault("motivos", []):
            validacao["motivos"].append(motivo)
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao


def atualizar_alerta_circuit_breaker_filtro_gol_ft_preciso(
    validacao, anterior=None, enviar=None
):
    """Notifica uma vez cada suspensão persistente do filtro FT preciso."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave = "filtro_gol_ft_preciso_breaker_notificado"
    notificado = anterior.get(chave)
    validacao[chave] = notificado
    controle = validacao.get(
        "controle_operacional_filtro_gol_ft_preciso"
    ) or {}
    if not (
        controle.get("ativo") is False
        and controle.get("estado") == "suspenso_automatico"
    ):
        return validacao
    assinatura = str(controle.get("assinatura") or "sem_assinatura")
    if notificado == assinatura:
        return validacao
    metricas = controle.get("metricas") or {}
    intervalo = metricas.get("intervalo_roi_95")
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        intervalo_texto = (
            f"[{float(intervalo[0]) * 100:.1f}%, "
            f"{float(intervalo[1]) * 100:.1f}%]"
        )
    else:
        intervalo_texto = "indisponível"
    roi = metricas.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:.1f}%"
    motivo = str(controle.get("motivo") or "")
    if "inconsistente" in motivo:
        conclusao = "A validação ficou inconsistente e falhou fechada."
    elif metricas.get("coorte_concluida"):
        conclusao = (
            "A coorte fixa chegou a 60 e foi fechada para revisão humana."
        )
    else:
        conclusao = (
            "O checkpoint fixo dos 25 primeiros casos comprovou ROI "
            "integralmente negativo."
        )
    mensagem = (
        "🛑 GOL FT ANTECIPADO PRECISO — ENTREGA SUSPENSA\n\n"
        f"Amostra válida: {int(metricas.get('validos', 0) or 0)}\n"
        f"Placar: {int(metricas.get('greens', 0) or 0)} GREEN / "
        f"{int(metricas.get('reds', 0) or 0)} RED\n"
        f"ROI: {roi_texto}\n"
        f"IC95 do ROI: {intervalo_texto}\n\n"
        f"{conclusao} A coleta sombra continua e nenhum outro mercado "
        "foi alterado."
    )
    if enviar(mensagem):
        validacao[chave] = assinatura
    return validacao


def aplicar_circuit_breaker_escanteios_ft_asiatico(
    validacao, caminho_estado=None, agora=None
):
    """Pausa somente a entrega do escanteio asiatico FT validado."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_ESCANTEIOS_FT_ASIATICO
    )
    progresso = validacao.get("progresso_escanteios_ft_asiatico") or {}
    estado = aplicar_controle_escanteios_ft_asiatico(
        progresso,
        caminho=caminho_estado,
        agora=agora,
    )
    validacao["controle_operacional_escanteios_ft_asiatico"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "assinatura": estado.get("assinatura"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        motivo = "controle_escanteios_ft_asiatico_inconsistente"
        if motivo not in validacao.setdefault("motivos", []):
            validacao["motivos"].append(motivo)
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao


def atualizar_alerta_circuit_breaker_escanteios_ft_asiatico(
    validacao, anterior=None, enviar=None
):
    """Notifica uma vez cada suspensao persistente do escanteio FT."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave = "escanteios_ft_asiatico_breaker_notificado"
    notificado = anterior.get(chave)
    validacao[chave] = notificado
    controle = validacao.get(
        "controle_operacional_escanteios_ft_asiatico"
    ) or {}
    if not (
        controle.get("ativo") is False
        and controle.get("estado") == "suspenso_automatico"
    ):
        return validacao
    assinatura = str(controle.get("assinatura") or "sem_assinatura")
    if notificado == assinatura:
        return validacao
    metricas = controle.get("metricas") or {}
    intervalo = metricas.get("intervalo_roi_95")
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        intervalo_texto = (
            f"[{float(intervalo[0]) * 100:.1f}%, "
            f"{float(intervalo[1]) * 100:.1f}%]"
        )
    else:
        intervalo_texto = "indisponivel"
    roi = metricas.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:.1f}%"
    motivo = str(controle.get("motivo") or "")
    if "inconsistente" in motivo:
        conclusao = "A validacao ficou inconsistente e falhou fechada."
    elif metricas.get("coorte_concluida"):
        conclusao = (
            "A coorte fixa chegou a 100 e foi fechada para revisao humana."
        )
    else:
        conclusao = (
            "O checkpoint fixo dos 25 primeiros casos comprovou ROI "
            "integralmente negativo."
        )
    mensagem = (
        "🛑 ESCANTEIOS FT ASIATICO — ENTREGA SUSPENSA\n\n"
        f"Amostra valida: {int(metricas.get('validos', 0) or 0)}\n"
        f"Placar: {int(metricas.get('greens', 0) or 0)} GREEN / "
        f"{int(metricas.get('half_greens', 0) or 0)} HALF GREEN / "
        f"{int(metricas.get('voids', 0) or 0)} VOID / "
        f"{int(metricas.get('half_reds', 0) or 0)} HALF RED / "
        f"{int(metricas.get('reds', 0) or 0)} RED\n"
        f"ROI: {roi_texto}\n"
        f"IC95 do ROI: {intervalo_texto}\n\n"
        f"{conclusao} A coleta sombra continua e nenhum outro mercado "
        "foi alterado."
    )
    if enviar(mensagem):
        validacao[chave] = assinatura
    return validacao


def aplicar_circuit_breaker_filtro_gol_ht_preciso(
    validacao, caminho_estado=None, agora=None
):
    """Pausa somente a entrega do HT antecipado que passou no filtro."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_FILTRO_GOL_HT_PRECISO
    )
    progresso = validacao.get("progresso_filtro_gol_ht_preciso") or {}
    estado = aplicar_controle_filtro_gol_ht_preciso(
        progresso,
        caminho=caminho_estado,
        agora=agora,
    )
    validacao["controle_operacional_filtro_gol_ht_preciso"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "assinatura": estado.get("assinatura"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        motivo = "controle_filtro_gol_ht_preciso_inconsistente"
        if motivo not in validacao.setdefault("motivos", []):
            validacao["motivos"].append(motivo)
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao


def atualizar_alerta_circuit_breaker_filtro_gol_ht_preciso(
    validacao, anterior=None, enviar=None
):
    """Notifica uma vez cada suspensão persistente do filtro HT preciso."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave = "filtro_gol_ht_preciso_breaker_notificado"
    notificado = anterior.get(chave)
    validacao[chave] = notificado
    controle = validacao.get(
        "controle_operacional_filtro_gol_ht_preciso"
    ) or {}
    if not (
        controle.get("ativo") is False
        and controle.get("estado") == "suspenso_automatico"
    ):
        return validacao
    assinatura = str(controle.get("assinatura") or "sem_assinatura")
    if notificado == assinatura:
        return validacao
    metricas = controle.get("metricas") or {}
    intervalo = metricas.get("intervalo_roi_95")
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        intervalo_texto = (
            f"[{float(intervalo[0]) * 100:.1f}%, "
            f"{float(intervalo[1]) * 100:.1f}%]"
        )
    else:
        intervalo_texto = "indisponível"
    roi = metricas.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:.1f}%"
    motivo = str(controle.get("motivo") or "")
    if "inconsistente" in motivo:
        conclusao = "A validação ficou inconsistente e falhou fechada."
    elif metricas.get("coorte_concluida"):
        conclusao = (
            "A coorte fixa chegou a 60 e foi fechada para revisão humana."
        )
    else:
        conclusao = (
            "O checkpoint fixo dos 25 primeiros casos comprovou ROI "
            "integralmente negativo."
        )
    mensagem = (
        "🛑 GOL HT ANTECIPADO PRECISO — ENTREGA SUSPENSA\n\n"
        f"Amostra válida: {int(metricas.get('validos', 0) or 0)}\n"
        f"Placar: {int(metricas.get('greens', 0) or 0)} GREEN / "
        f"{int(metricas.get('reds', 0) or 0)} RED\n"
        f"ROI: {roi_texto}\n"
        f"IC95 do ROI: {intervalo_texto}\n\n"
        f"{conclusao} A coleta sombra continua e nenhum outro mercado "
        "foi alterado."
    )
    if enviar(mensagem):
        validacao[chave] = assinatura
    return validacao


def aplicar_circuit_breaker_gols_antecipados(
    validacao, caminho_estado=None, agora=None
):
    """Suspende somente o braço com coorte prospectiva comprovadamente ruim."""
    caminho_estado = caminho_estado or ARQUIVO_ESTADO_GOLS_ANTECIPADOS
    progresso = validacao.get("progresso_gols_antecipados") or {}
    estado = ler_estado_gols_antecipados(caminho_estado)
    suspensos = []
    if estado.get("saudavel"):
        for versao, item in sorted(
            (progresso.get("por_braco") or {}).items()
        ):
            intervalo = item.get("intervalo_roi_95")
            evidencia_forte = bool(
                item.get("decisao_estatistica") == "evidencia_desfavoravel"
                and int(item.get("validos", 0) or 0) >= 95
                and isinstance(intervalo, (list, tuple))
                and len(intervalo) == 2
                and intervalo[1] is not None
                and float(intervalo[1]) < 0
                and item.get("linhagem_homogenea") is True
            )
            if not evidencia_forte or not metodo_gol_antecipado_liberado(
                versao, caminho_estado
            ):
                continue
            assinatura = "|".join((
                str(progresso.get("versao") or "sem_validacao"),
                str(progresso.get("registrado_em") or "sem_ancora"),
                str(progresso.get("linhagem_sha256") or "sem_linhagem"),
                str(versao),
            ))
            estado = suspender_metodo_gol_antecipado(
                versao,
                assinatura,
                "ic95_roi_integralmente_negativo",
                metricas={
                    "validos": int(item.get("validos", 0) or 0),
                    "greens": int(item.get("greens", 0) or 0),
                    "reds": int(item.get("reds", 0) or 0),
                    "roi": item.get("roi"),
                    "intervalo_roi_95": intervalo,
                    "decisao_estatistica": item.get(
                        "decisao_estatistica"
                    ),
                },
                caminho=caminho_estado,
                agora=agora,
                automatico=True,
            )
            if estado.get("alterado"):
                suspensos.append(versao)
    validacao["controle_operacional_gols_antecipados"] = {
        **estado,
        "suspensos_neste_ciclo": suspensos,
    }
    metodos_estado = estado.get("metodos") or {}
    for versao, item in (progresso.get("por_braco") or {}).items():
        controle = metodos_estado.get(versao) or {}
        item["grupo_liberado"] = bool(
            estado.get("saudavel") and controle.get("ativo", True)
        )
        item["circuit_breaker"] = {
            "ativo": controle.get("ativo", True),
            "estado": controle.get("estado", "ativo_padrao"),
            "motivo": controle.get("motivo"),
            "atualizado_em": controle.get("atualizado_em"),
        }
    if not estado.get("saudavel"):
        validacao.setdefault("motivos", []).append(
            "controle_gols_antecipados_inconsistente"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao


def atualizar_alerta_circuit_breaker_gols_antecipados(
    validacao, anterior=None, enviar=None
):
    """Notifica cada suspensão persistente uma única vez."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    chave = "circuit_breaker_gols_antecipados_notificados"
    notificados = dict(anterior.get(chave) or {})
    controle = validacao.get(
        "controle_operacional_gols_antecipados"
    ) or {}
    for versao, item in sorted((controle.get("metodos") or {}).items()):
        if not (
            item.get("ativo") is False
            and item.get("estado") == "sombra_automatico"
        ):
            continue
        assinatura = str(item.get("assinatura") or "sem_assinatura")
        if notificados.get(versao) == assinatura:
            continue
        metricas = item.get("metricas") or {}
        intervalo = metricas.get("intervalo_roi_95")
        if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
            intervalo_texto = (
                f"[{float(intervalo[0]) * 100:.1f}%, "
                f"{float(intervalo[1]) * 100:.1f}%]"
            )
        else:
            intervalo_texto = "indisponível"
        roi = metricas.get("roi")
        roi_texto = "-" if roi is None else f"{float(roi) * 100:.1f}%"
        mensagem = (
            "🛑 GOL ANTECIPADO — RETORNO AUTOMÁTICO AO SOMBRA\n\n"
            f"Método: {versao}\n"
            f"Amostra válida: {int(metricas.get('validos', 0) or 0)}\n"
            f"Placar: {int(metricas.get('greens', 0) or 0)} GREEN / "
            f"{int(metricas.get('reds', 0) or 0)} RED\n"
            f"ROI: {roi_texto}\n"
            f"IC95 do ROI: {intervalo_texto}\n\n"
            "A evidência prospectiva ficou integralmente negativa. Apenas "
            "este método foi pausado; os demais continuam independentes."
        )
        if enviar(mensagem):
            notificados[versao] = assinatura
    validacao[chave] = notificados
    return validacao


TITULOS_CONCLUSAO_GOL_FT_V3 = {
    "favoravel_para_revisao_independente": (
        "✅ JULGAMENTO FINAL GOL FT V3 — FAVORÁVEL PARA REVISÃO INDEPENDENTE"
    ),
    "inconclusiva": (
        "⚠️ JULGAMENTO FINAL GOL FT V3 — EVIDÊNCIA INCONCLUSIVA"
    ),
    "evidencia_desfavoravel": (
        "❌ JULGAMENTO FINAL GOL FT V3 — EVIDÊNCIA DESFAVORÁVEL"
    ),
    "linhagem_inconsistente": (
        "🚫 JULGAMENTO FINAL GOL FT V3 — LINHAGEM INCONSISTENTE"
    ),
    "amostra_valida_insuficiente": (
        "⚠️ JULGAMENTO FINAL GOL FT V3 — AMOSTRA VÁLIDA INSUFICIENTE"
    ),
}


def enviar_alerta_conclusao_gol_ft_v3(
    texto, assinatura, caminho_banco=None, agora=None,
):
    """Envia a conclusão V3 somente ao destino administrativo explícito."""
    destino_admin = os.getenv("TELEGRAM_ADMIN_ID")
    if not destino_admin:
        return False
    chave_evento = hashlib.sha256(
        f"conclusao-gol-ft-v3|{assinatura}".encode("utf-8")
    ).hexdigest()
    return enviar_alerta(
        texto,
        caminho_banco=caminho_banco,
        agora=agora,
        destinos=(destino_admin,),
        chave_evento=chave_evento,
        deduplicacao_minutos=None,
    )


def atualizar_conclusao_gol_ft_v3(
    validacao, anterior=None, enviar=None,
):
    """Notifica uma única conclusão por versão e fingerprint da coorte V3."""
    anterior = anterior or {}
    chave_estado = "exploracao_gol_ft_v3_conclusoes_notificadas"
    historico = anterior.get(chave_estado)
    notificados = dict(historico) if isinstance(historico, dict) else {}
    validacao[chave_estado] = notificados
    item = (
        (validacao.get("exploracao_sombra") or {}).get(
            "validacao_prospectiva_gol_ft_v3"
        ) or {}
    )
    if (
        item.get("coorte_fechada") is not True
        or item.get("resultados_completos") is not True
    ):
        return validacao

    julgamento = item.get("decisao_estatistica")
    titulo = TITULOS_CONCLUSAO_GOL_FT_V3.get(julgamento)
    versao = str(item.get("versao") or "").strip()
    fingerprint = str(item.get("validacao_fingerprint") or "").strip()
    if not titulo or not versao or not fingerprint:
        return validacao
    assinatura = f"{versao}|{fingerprint}"
    if assinatura in notificados:
        return validacao

    politica = item.get("politica_avaliacao_versao") or "-"
    mensagem = (
        f"{titulo}\n\n"
        "Experimento: confirmação prospectiva independente Gol FT V3\n"
        f"Versão: {versao}\n"
        f"Política pré-registrada: {politica}\n"
        f"Coorte fixa: {int(item.get('candidatos_coorte', 0) or 0)}/"
        f"{int(item.get('tamanho_coorte_fixa', 0) or 0)}\n"
        "Resultados válidos: "
        f"{int(item.get('avaliadas', 0) or 0)}/"
        f"{int(item.get('minimo_resultados_validos', 0) or 0)} | "
        f"pendentes={int(item.get('pendentes', 0) or 0)} | "
        f"inválidos={int(item.get('invalidos', 0) or 0)}\n"
        f"Placar: {int(item.get('greens', 0) or 0)} GREEN / "
        f"{int(item.get('reds', 0) or 0)} RED\n"
        f"ROI: {item.get('roi')} | IC95: {item.get('intervalo_roi_95')}\n"
        f"Julgamento pré-registrado: {julgamento}\n"
        f"Fingerprint da coorte: {fingerprint}\n\n"
        + (
            "O resultado permite somente revisão humana independente; "
            "não aprova nem ativa o mercado.\n"
            if julgamento == "favoravel_para_revisao_independente"
            else
            "O mercado permanece bloqueado para ativação oficial.\n"
        )
        + "Nenhum sinal oficial foi enviado e nenhuma regra foi promovida "
        "automaticamente."
    )
    enviado = (
        enviar(mensagem)
        if enviar is not None
        else enviar_alerta_conclusao_gol_ft_v3(mensagem, assinatura)
    )
    if enviado:
        notificados[assinatura] = {
            "versao": versao,
            "politica_avaliacao_versao": politica,
            "validacao_fingerprint": fingerprint,
            "decisao_estatistica": julgamento,
        }
    validacao[chave_estado] = notificados
    return validacao


def enviar_alerta_conclusao_gol_ht_00_min20(
    texto, assinatura, caminho_banco=None, agora=None,
):
    """Entrega o fechamento HT apenas ao destino administrativo."""
    destino_admin = os.getenv("TELEGRAM_ADMIN_ID")
    if not destino_admin:
        return False
    chave_evento = hashlib.sha256(
        f"conclusao-gol-ht-00-min20|{assinatura}".encode("utf-8")
    ).hexdigest()
    return enviar_alerta(
        texto,
        caminho_banco=caminho_banco,
        agora=agora,
        destinos=(destino_admin,),
        chave_evento=chave_evento,
        deduplicacao_minutos=None,
    )


def _formatar_percentual(valor):
    return "-" if valor is None else f"{float(valor) * 100:+.1f}%"


def _formatar_intervalo_percentual(intervalo):
    if not isinstance(intervalo, (list, tuple)) or len(intervalo) != 2:
        return "indisponível"
    return (
        f"[{float(intervalo[0]) * 100:+.1f}%, "
        f"{float(intervalo[1]) * 100:+.1f}%]"
    )


def atualizar_conclusao_gol_ht_00_min20(
    validacao, anterior=None, enviar=None,
):
    """Notifica uma vez o fechamento HT, sem promover a regra."""
    anterior = anterior or {}
    chave_estado = "gol_ht_00_min20_conclusoes_notificadas"
    historico = anterior.get(chave_estado)
    notificados = dict(historico) if isinstance(historico, dict) else {}
    validacao[chave_estado] = notificados
    item = validacao.get("progresso_gol_ht_00_min20") or {}
    decisao = item.get("decisao")
    if decisao not in {"favoravel_para_revisao", "inconclusiva"}:
        return validacao
    if int(item.get("faltam", 1) or 0) > 0 or int(
        item.get("pendentes", 0) or 0
    ) > 0:
        return validacao

    registrado_em = str(item.get("registrado_em") or "").strip()
    if not registrado_em:
        return validacao
    assinatura = "|".join((
        VERSAO_VALIDACAO_GOL_HT_00_MIN20,
        registrado_em,
        str(decisao),
    ))
    if assinatura in notificados:
        return validacao

    favoravel = decisao == "favoravel_para_revisao"
    titulo = (
        "✅ GOL HT 0-0 MIN20 — FAVORÁVEL PARA REVISÃO MANUAL"
        if favoravel else
        "⚠️ GOL HT 0-0 MIN20 — EVIDÊNCIA INCONCLUSIVA"
    )
    desenvolvimento = item.get("desenvolvimento") or {}
    holdout = item.get("holdout") or {}
    mensagem = (
        f"{titulo}\n\n"
        f"Coorte fixa: {int(item.get('candidatos', 0) or 0)}/100\n"
        f"Resultados válidos: {int(item.get('validos', 0) or 0)} | "
        f"{int(item.get('greens', 0) or 0)} GREEN / "
        f"{int(item.get('reds', 0) or 0)} RED\n"
        f"ROI total: {_formatar_percentual(item.get('roi'))} | IC95: "
        f"{_formatar_intervalo_percentual(item.get('intervalo_roi_95'))}\n"
        "Desenvolvimento: "
        f"{int(desenvolvimento.get('validos', 0) or 0)} resultado(s), "
        f"ROI {_formatar_percentual(desenvolvimento.get('roi'))}\n"
        "Holdout: "
        f"{int(holdout.get('validos', 0) or 0)} resultado(s), "
        f"ROI {_formatar_percentual(holdout.get('roi'))}\n"
        "Linhagem homogênea: "
        f"{'sim' if item.get('linhagem_homogenea') else 'não'}\n\n"
        + (
            "Os critérios pré-registrados permitem somente revisão humana. "
            if favoravel else
            "A coorte não comprovou vantagem suficiente para promoção. "
        )
        + "Nenhum método foi ativado, desativado ou promovido automaticamente."
    )
    enviado = (
        enviar(mensagem)
        if enviar is not None
        else enviar_alerta_conclusao_gol_ht_00_min20(
            mensagem, assinatura
        )
    )
    if enviado:
        notificados[assinatura] = {
            "versao": VERSAO_VALIDACAO_GOL_HT_00_MIN20,
            "registrado_em": registrado_em,
            "decisao": decisao,
        }
    validacao[chave_estado] = notificados
    return validacao


def atualizar_alerta_prontidao_historico_api_live(
    validacao, anterior=None, enviar=None
):
    """Avisa uma vez quando a comparacao temporal pode ser revisada."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    historico = validacao.get("historico_api_live") or {}
    prontidao = historico.get("prontidao_revisao") or {}
    estado = prontidao.get("estado")
    estados_conclusivos = {"apto_revisao", "divergencia_fontes"}
    if estado not in estados_conclusivos:
        return validacao

    assinatura = str(estado)
    if anterior.get("historico_api_live_prontidao_notificada") == assinatura:
        validacao["historico_api_live_prontidao_notificada"] = assinatura
        return validacao

    snapshots = int(prontidao.get("snapshots", 0) or 0)
    minimo_snapshots = int(prontidao.get("minimo_snapshots", 30) or 30)
    fixtures = int(prontidao.get("fixtures", 0) or 0)
    minimo_fixtures = int(prontidao.get("minimo_fixtures", 10) or 10)
    concordancia = historico.get("taxa_concordancia_snapshots")
    wilson = historico.get("limite_inferior_wilson_snapshots")
    concordancia_texto = (
        "-" if concordancia is None else f"{float(concordancia) * 100:.1f}%"
    )
    wilson_texto = "-" if wilson is None else f"{float(wilson) * 100:.1f}%"
    favoravel = estado == "apto_revisao"
    titulo = (
        "✅ FONTES TEMPORAIS PRONTAS PARA REVISÃO"
        if favoravel else
        "⚠️ DIVERGÊNCIA ENTRE PACKBALL E API-FOOTBALL"
    )
    conclusao = (
        "A concordância atingiu os critérios pré-registrados."
        if favoravel else
        "A amostra mínima foi atingida, mas a concordância não passou."
    )
    mensagem = (
        f"{titulo}\n\n"
        f"Leituras independentes: {snapshots}/{minimo_snapshots}\n"
        f"Jogos distintos: {fixtures}/{minimo_fixtures}\n"
        f"Concordância observada: {concordancia_texto}\n"
        f"Limite inferior de Wilson 95%: {wilson_texto}\n\n"
        f"{conclusao}\n"
        "Esta decisão libera somente revisão independente. Os dados "
        "temporais continuam em modo sombra e não alteram sinais "
        "automaticamente."
    )
    if enviar(mensagem):
        validacao["historico_api_live_prontidao_notificada"] = assinatura
    return validacao


def atualizar_alertas_pontuacao_contexto_sombra(
    validacao, anterior=None, enviar=None
):
    """Avisa somente congelamento e conclusão prospectiva do challenger."""
    if os.getenv("ALERTAS_ANALISES_SOMBRA_TELEGRAM", "1") != "1":
        # A análise e seus marcos continuam persistidos no estado/status. O
        # Telegram fica reservado à operação; isto evita que uma conclusão
        # puramente experimental pareça um sinal ou uma mudança de regra.
        return validacao
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    notificados_anteriores = dict(
        anterior.get("pontuacao_contexto_marcos_notificados") or {}
    )
    notificados = {
        mercado: dict(marcos)
        for mercado, marcos in notificados_anteriores.items()
        if isinstance(marcos, dict)
    }
    avaliacao = validacao.get("pontuacao_contexto_sombra") or {}
    for mercado, item in sorted(
        (avaliacao.get("por_mercado") or {}).items()
    ):
        if not item.get("integro", False):
            continue
        treino = item.get("treino")
        ancora = item.get("treino_ate_sinal_id")
        if treino is None or ancora is None:
            continue
        marcos = dict(notificados.get(mercado) or {})
        assinatura_modelo = "|".join((
            str(avaliacao.get("versao") or ""),
            str(item.get("avaliacao_versao") or ""),
            str(item.get("regra_versao") or ""),
            str(ancora),
        ))
        if marcos.get("congelado") != assinatura_modelo:
            mensagem = (
                "🧪 MODELO CONTEXTUAL CONGELADO — SOMENTE SOMBRA\n\n"
                f"Mercado: {ROTULOS_MERCADOS.get(mercado, mercado)}\n"
                f"Treino independente: {int(treino)} resultado(s)\n"
                f"Âncora imutável: sinal {int(ancora)}\n"
                "Validação futura exigida: "
                f"{int(item.get('amostra_minima_validacao', 30) or 30)}"
                " resultado(s)\n"
                f"Versão: {avaliacao.get('versao') or '-'}\n\n"
                "Somente sinais posteriores à âncora serão avaliados. "
                "Nenhuma regra ou sinal oficial foi alterado."
            )
            if enviar(mensagem):
                marcos["congelado"] = assinatura_modelo
            if marcos:
                notificados[mercado] = marcos
            continue
        quantidade_validacao = int(item.get("validacao", 0) or 0)
        minima_validacao = int(
            item.get("amostra_minima_validacao", 30) or 30
        )
        estado = item.get("estado")
        if (
            quantidade_validacao >= minima_validacao
            and estado in (
                "favoravel_para_revisao", "contraria", "inconclusiva"
            )
        ):
            assinatura_conclusao = "|".join((
                assinatura_modelo,
                str(estado),
                str(item.get("validacao_fingerprint") or ""),
            ))
            if marcos.get("conclusao") != assinatura_conclusao:
                favoravel = estado == "favoravel_para_revisao"
                titulo = (
                    "✅ CHALLENGER CONTEXTUAL FAVORÁVEL PARA REVISÃO"
                    if favoravel
                    else "⚠️ CHALLENGER CONTEXTUAL SEM VANTAGEM COMPROVADA"
                )
                auc_contexto = item.get("auc_contexto") or {}
                auc_atual = item.get("auc_nota_atual") or {}
                mensagem = (
                    f"{titulo}\n\n"
                    f"Mercado: {ROTULOS_MERCADOS.get(mercado, mercado)}\n"
                    f"Estado: {estado}\n"
                    f"Treino congelado: {int(treino)}\n"
                    f"Validação futura: {quantidade_validacao}\n"
                    f"AUC contextual: {auc_contexto.get('auc')}\n"
                    "Limite inferior AUC95: "
                    f"{auc_contexto.get('limite_inferior_auc_95')}\n"
                    f"AUC da nota atual: {auc_atual.get('auc')}\n"
                    f"Brier contextual/odd: "
                    f"{item.get('brier_contexto')}/"
                    f"{item.get('brier_odd')}\n\n"
                    + (
                        "O resultado pode ser revisado manualmente para uma "
                        "futura versão."
                        if favoravel
                        else "O modelo não deve ser promovido com esta "
                        "evidência."
                    )
                    + "\nNenhuma aplicação automática foi realizada."
                )
                if enviar(mensagem):
                    marcos["conclusao"] = assinatura_conclusao
        if marcos:
            notificados[mercado] = marcos
    validacao["pontuacao_contexto_marcos_notificados"] = notificados
    return validacao


def atualizar_alertas_pontuacao_longa_sombra(
    validacao, anterior=None, enviar=None
):
    """Avisa os dois marcos fixos do estudo 5/10/15 sem promover regra."""
    if os.getenv("ALERTAS_ANALISES_SOMBRA_TELEGRAM", "1") != "1":
        return validacao
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    notificados_anteriores = dict(
        anterior.get("pontuacao_longa_marcos_notificados") or {}
    )
    notificados = {
        mercado: dict(marcos)
        for mercado, marcos in notificados_anteriores.items()
        if isinstance(marcos, dict)
    }
    avaliacao = validacao.get("pontuacao_longa_sombra") or {}
    for mercado, item in sorted(
        (avaliacao.get("por_mercado") or {}).items()
    ):
        if not item.get("integro", False):
            continue
        treino = item.get("treino")
        ancora_treino = item.get("treino_ate_sinal_id")
        if treino is None or ancora_treino is None:
            continue
        marcos = dict(notificados.get(mercado) or {})
        assinatura_modelo = "|".join((
            str(avaliacao.get("versao") or ""),
            str(item.get("avaliacao_versao") or ""),
            str(item.get("regra_versao") or ""),
            str(item.get("iniciar_apos_sinal_id") or ""),
            str(ancora_treino),
        ))
        if marcos.get("congelado") != assinatura_modelo:
            mensagem = (
                "🧪 MODELO TEMPORAL 5/10/15 CONGELADO — SOMENTE SOMBRA\n\n"
                f"Mercado: {ROTULOS_MERCADOS.get(mercado, mercado)}\n"
                f"Treino prospectivo: {int(treino)} resultado(s)\n"
                f"Âncora final do treino: sinal {int(ancora_treino)}\n"
                "Janelas obrigatórias: 5, 10 e 15 minutos completas\n"
                "Validação futura exigida: "
                f"{int(item.get('amostra_minima_validacao', 30) or 30)}"
                " resultado(s)\n"
                f"Versão: {avaliacao.get('versao') or '-'}\n\n"
                "Somente os próximos resultados elegíveis serão avaliados. "
                "Nenhuma regra ou sinal oficial foi alterado."
            )
            if enviar(mensagem):
                marcos["congelado"] = assinatura_modelo
            if marcos:
                notificados[mercado] = marcos
            continue
        quantidade_validacao = int(item.get("validacao", 0) or 0)
        minima_validacao = int(
            item.get("amostra_minima_validacao", 30) or 30
        )
        estado = item.get("estado")
        if (
            quantidade_validacao >= minima_validacao
            and estado in (
                "favoravel_para_revisao", "contraria", "inconclusiva"
            )
        ):
            assinatura_conclusao = "|".join((
                assinatura_modelo,
                str(estado),
                str(item.get("validacao_fingerprint") or ""),
            ))
            if marcos.get("conclusao") != assinatura_conclusao:
                favoravel = estado == "favoravel_para_revisao"
                titulo = (
                    "✅ TEMPORAL 5/10/15 FAVORÁVEL PARA REVISÃO"
                    if favoravel
                    else "⚠️ TEMPORAL 5/10/15 SEM VANTAGEM COMPROVADA"
                )
                auc_longa = item.get("auc_longa") or {}
                auc_atual = item.get("auc_nota_atual") or {}
                mensagem = (
                    f"{titulo}\n\n"
                    f"Mercado: {ROTULOS_MERCADOS.get(mercado, mercado)}\n"
                    f"Estado: {estado}\n"
                    f"Treino congelado: {int(treino)}\n"
                    f"Validação futura: {quantidade_validacao}\n"
                    f"AUC temporal: {auc_longa.get('auc')}\n"
                    "Limite inferior AUC95: "
                    f"{auc_longa.get('limite_inferior_auc_95')}\n"
                    f"AUC da nota atual: {auc_atual.get('auc')}\n"
                    f"Brier temporal/odd: {item.get('brier_longa')}/"
                    f"{item.get('brier_odd')}\n\n"
                    + (
                        "O resultado pode ser revisado manualmente para uma "
                        "futura versão."
                        if favoravel
                        else "O modelo não deve ser promovido com esta "
                        "evidência."
                    )
                    + "\nNenhuma aplicação automática foi realizada."
                )
                if enviar(mensagem):
                    marcos["conclusao"] = assinatura_conclusao
        if marcos:
            notificados[mercado] = marcos
    validacao["pontuacao_longa_marcos_notificados"] = notificados
    return validacao


def atualizar_alerta_drift_simulacoes(
    validacao, anterior=None, enviar=None
):
    """Avisa deterioração estatística por mercado sem alterar regras."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    drift = validacao.get("drift_simulacoes") or {}
    degradados = sorted(set(drift.get("mercados_degradados") or []))
    notificados = sorted(set(
        anterior.get("drift_simulacoes_mercados_notificados") or []
    ))
    confirmacoes_anteriores = (
        anterior.get("drift_simulacoes_confirmacoes") or {}
    )
    confirmacoes = {}
    confirmados = []
    mercados = drift.get("mercados") or {}
    for mercado in degradados:
        dados = mercados.get(mercado) or {}
        decisao_id = dados.get("ultima_decisao_id")
        anterior_mercado = confirmacoes_anteriores.get(mercado) or {}
        if (
            decisao_id is not None
            and anterior_mercado.get("ultima_decisao_id") == decisao_id
        ):
            quantidade = int(anterior_mercado.get("quantidade") or 1)
        else:
            quantidade = int(anterior_mercado.get("quantidade") or 0) + 1
        confirmacoes[mercado] = {
            "quantidade": quantidade,
            "ultima_decisao_id": decisao_id,
            "ultimo_resultado_em": dados.get("ultimo_resultado_em"),
        }
        if quantidade >= 2:
            confirmados.append(mercado)
    confirmados = sorted(confirmados)
    novos = sorted(set(confirmados) - set(notificados))
    recuperados = sorted(set(notificados) - set(degradados))
    if not novos and not recuperados:
        validacao["drift_simulacoes_confirmacoes"] = confirmacoes
        validacao["drift_simulacoes_mercados_confirmados"] = confirmados
        validacao["drift_simulacoes_mercados_notificados"] = notificados
        return validacao

    blocos = []
    if novos:
        linhas = []
        for mercado in novos:
            dados = mercados.get(mercado) or {}
            linhas.append(
                f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
                f"base={dados.get('amostra_base', 0)} | "
                f"recente={dados.get('amostra_recente', 0)} | "
                f"ROI {dados.get('roi_base')} → {dados.get('roi_recente')} | "
                f"delta={dados.get('delta_roi')} | "
                f"IC95={dados.get('intervalo_delta_roi_95')}"
            )
        blocos.append(
            "⚠️ DETERIORAÇÃO NAS SIMULAÇÕES PACKBALL\n\n"
            + "\n".join(linhas)
            + "\n\nA queda permaneceu significativa em duas atualizações "
            "independentes."
        )
    if recuperados:
        blocos.append(
            "✅ DESEMPENHO DAS SIMULAÇÕES RECUPERADO\n\n"
            + "\n".join(
                f"• {ROTULOS_MERCADOS.get(mercado, mercado)}"
                for mercado in recuperados
            )
        )
    entregue = enviar(
        "\n\n".join(blocos)
        + "\n\nNenhuma regra foi alterada automaticamente; as simulações "
        "continuam servindo para medição e os mercados oficiais mantêm "
        "suas próprias travas de calibração."
    )
    alvo_notificados = sorted(
        (set(notificados) - set(recuperados)) | set(novos)
    )
    validacao["drift_simulacoes_confirmacoes"] = confirmacoes
    validacao["drift_simulacoes_mercados_confirmados"] = confirmados
    validacao["drift_simulacoes_mercados_notificados"] = (
        alvo_notificados if entregue else notificados
    )
    return validacao


def persistir_historico_drift_simulacoes(
    validacao, caminho_banco=ARQUIVO_BANCO, agora=None
):
    """Grava só avaliações associadas a um novo resultado independente."""
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        conexao = sqlite3.connect(caminho_banco, timeout=10)
        conexao.row_factory = sqlite3.Row
        with conexao:
            gravacao = registrar_historico_drift_simulacoes(
                conexao, validacao, registrado_em=agora
            )
        auditoria = auditar_historico_drift_simulacoes(
            conexao,
            validacao.get("drift_simulacoes") or {},
            regra_versao=(
                (validacao.get("drift_simulacoes") or {}).get("regra_versao")
                or validacao.get("regra_versao")
            ),
        )
        return {
            "saudavel": True,
            "estado": "ativo",
            "motivo": None,
            **gravacao,
            **auditoria,
        }
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "historico_drift_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def persistir_historico_avaliacao_contexto(
    validacao, caminho_banco=ARQUIVO_BANCO, agora=None
):
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        conexao = sqlite3.connect(caminho_banco, timeout=10)
        conexao.row_factory = sqlite3.Row
        instante = (agora or datetime.now()).replace(
            microsecond=0
        ).isoformat()
        avaliacao = (validacao or {}).get("avaliacao_contexto") or {}
        regras = {
            mercado: item.get("regra_versao")
            for mercado, item in (
                avaliacao.get("por_mercado") or {}
            ).items()
            if item.get("regra_versao")
        }
        with conexao:
            ancoras = registrar_ou_obter_ancoras_contexto(
                conexao, regras, registrado_em=instante
            )
            gravacao = registrar_historico_avaliacao_contexto(
                conexao,
                avaliacao,
                instante,
            )
        auditoria = auditar_historico_avaliacao_contexto(conexao)
        saudavel = bool(auditoria["saudavel"])
        return {
            "saudavel": saudavel,
            "estado": "ativo" if saudavel else "inconsistente",
            "motivo": auditoria.get("motivo"),
            **gravacao,
            **auditoria,
            "ancoras_pre_registradas": ancoras,
        }
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "historico_contexto_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def persistir_modelos_pontuacao_sombra(
    validacao, caminho_banco=ARQUIVO_BANCO, agora=None
):
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        conexao = sqlite3.connect(caminho_banco, timeout=10)
        conexao.row_factory = sqlite3.Row
        regras = (validacao or {}).get(
            "regra_versoes_por_mercado"
        ) or {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in MERCADOS_VALIDACAO
        }
        instante = (agora or datetime.now()).replace(
            microsecond=0
        ).isoformat()
        with conexao:
            gravacao = registrar_modelos_pontuacao_sombra(
                conexao,
                regras,
                registrado_em=instante,
            )
        avaliacao = avaliar_pontuacao_sombra(conexao, regras)
        saudavel = bool(gravacao["integro"] and avaliacao["integro"])
        return {
            "saudavel": saudavel,
            "estado": "ativo" if saudavel else "inconsistente",
            "motivo": None if saudavel else "pontuacao_sombra_inconsistente",
            "criados": gravacao["criados"],
            "avaliacao": avaliacao,
        }
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "pontuacao_sombra_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def persistir_modelos_pontuacao_contexto_sombra(
    validacao, caminho_banco=ARQUIVO_BANCO, agora=None
):
    """Registra o challenger contextual sem tocar no modelo sombra original."""
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        conexao = sqlite3.connect(caminho_banco, timeout=10)
        conexao.row_factory = sqlite3.Row
        regras = (validacao or {}).get(
            "regra_versoes_por_mercado"
        ) or {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in MERCADOS_VALIDACAO
        }
        instante = (agora or datetime.now()).replace(
            microsecond=0
        ).isoformat()
        with conexao:
            gravacao = registrar_modelos_pontuacao_contexto_sombra(
                conexao,
                regras,
                registrado_em=instante,
            )
        avaliacao = avaliar_pontuacao_contexto_sombra(conexao, regras)
        saudavel = bool(gravacao["integro"] and avaliacao["integro"])
        return {
            "saudavel": saudavel,
            "estado": "ativo" if saudavel else "inconsistente",
            "motivo": (
                None
                if saudavel
                else "pontuacao_contexto_sombra_inconsistente"
            ),
            "criados": gravacao["criados"],
            "avaliacao": avaliacao,
        }
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "pontuacao_contexto_sombra_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def persistir_estudos_pontuacao_longa_sombra(
    validacao, caminho_banco=ARQUIVO_BANCO, agora=None
):
    """Ancora o V2 e congela treino/validacao sem tocar na regra ativa."""
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        conexao = sqlite3.connect(caminho_banco, timeout=10)
        conexao.row_factory = sqlite3.Row
        regras = (validacao or {}).get(
            "regra_versoes_por_mercado"
        ) or {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in MERCADOS_VALIDACAO
        }
        instante = (agora or datetime.now()).replace(
            microsecond=0
        ).isoformat()
        with conexao:
            gravacao = registrar_estudos_pontuacao_longa(
                conexao,
                regras,
                registrado_em=instante,
            )
        avaliacao = avaliar_pontuacao_longa_sombra(conexao, regras)
        saudavel = bool(gravacao["integro"] and avaliacao["integro"])
        return {
            "saudavel": saudavel,
            "estado": "ativo" if saudavel else "inconsistente",
            "motivo": (
                None
                if saudavel
                else "pontuacao_longa_sombra_inconsistente"
            ),
            "ancoras_criadas": gravacao["ancoras_criadas"],
            "modelos_criados": gravacao["modelos_criados"],
            "avaliacao": avaliacao,
        }
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "pontuacao_longa_sombra_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def persistir_conclusao_experimento_filtro(
    caminho_banco=ARQUIVO_BANCO, agora=None
):
    """Congela a primeira conclusão em uma etapa explícita de escrita."""
    if os.getenv("SINAIS_TESTE_ATIVO", "0") != "1":
        return {
            "saudavel": True,
            "estado": "desativado",
            "motivo": None,
            "conclusao": None,
        }
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
            "conclusao": None,
        }
    conexao = None
    try:
        conexao = sqlite3.connect(caminho_banco, timeout=10)
        conexao.row_factory = sqlite3.Row
        pontuacao_minima = float(
            os.getenv("PONTUACAO_MINIMA_SINAL_TESTE", "70")
        )
        qualidade_minima = float(
            os.getenv("QUALIDADE_MINIMA_SINAL_TESTE", "0")
        )
        fingerprint = fingerprint_vinculado_no_banco(
            conexao, VERSAO_REGRAS
        )
        auditoria = auditar_experimento_filtro(
            conexao,
            VERSAO_REGRAS,
            pontuacao_minima,
            qualidade_minima,
            ativo=True,
            regra_fingerprint=fingerprint,
            exigir_linhagem=True,
        )
        if not auditoria.get("saudavel"):
            return {
                "saudavel": False,
                "estado": "inconsistente",
                "motivo": auditoria.get("motivo"),
                "conclusao": None,
            }
        comparacao = comparar_filtro_simulacoes(
            conexao,
            VERSAO_REGRAS,
            iniciado_em=auditoria.get("iniciado_em"),
            regra_fingerprint=fingerprint,
        )
        conclusao = registrar_ou_obter_conclusao_experimento_filtro(
            conexao,
            VERSAO_REGRAS,
            pontuacao_minima,
            qualidade_minima,
            fingerprint,
            comparacao,
            agora=agora,
        )
        return {
            "saudavel": True,
            "estado": "concluido" if conclusao else "aguardando_amostra",
            "motivo": None,
            "conclusao": conclusao,
        }
    except (
        OSError, sqlite3.Error, RuntimeError, TypeError, ValueError
    ) as erro:
        return {
            "saudavel": False,
            "estado": "falha",
            "motivo": resumir_erro_seguro(erro),
            "conclusao": None,
        }
    finally:
        if conexao is not None:
            conexao.close()


def _normalizar_id_populacao_calibracao(valor):
    """Remove somente a política estatística de IDs legados."""
    if not valor:
        return None
    partes = str(valor).split("|")
    if (
        len(partes) >= 4
        and partes[1].startswith("calibracao-")
    ):
        return "|".join((partes[0], *partes[2:]))
    return str(valor)


def _ids_populacao_por_mercado(validacao):
    explicitos = dict(
        validacao.get("amostra_populacao_id_por_mercado") or {}
    )
    regra_padrao = validacao.get("regra_versao") or VERSAO_REGRAS
    global_id = (
        validacao.get("amostra_populacao_id")
        or _normalizar_id_populacao_calibracao(
            validacao.get("amostra_oficial_id")
        )
        or regra_padrao
    )
    regras = validacao.get("regra_versoes_por_mercado") or {}
    return {
        mercado: (
            explicitos.get(mercado)
            or regras.get(mercado)
            or global_id
        )
        for mercado in MERCADOS_VALIDACAO
    }


def _continuidade_populacao_por_mercado(
    validacao, anterior, sufixo
):
    atuais = _ids_populacao_por_mercado(validacao)
    anteriores = dict(
        anterior.get(
            f"amostra_populacao_id_por_mercado_{sufixo}"
        ) or {}
    )
    if not anteriores:
        legado = (
            anterior.get(f"amostra_populacao_id_{sufixo}")
            or _normalizar_id_populacao_calibracao(
                anterior.get(f"amostra_oficial_id_{sufixo}")
            )
            or anterior.get(f"regra_versao_{sufixo}")
        )
        anteriores = {
            mercado: legado for mercado in MERCADOS_VALIDACAO
        }
    continuidade = {
        mercado: bool(
            anteriores.get(mercado)
            and _normalizar_id_populacao_calibracao(
                anteriores.get(mercado)
            )
            == _normalizar_id_populacao_calibracao(
                atuais.get(mercado)
            )
        )
        for mercado in MERCADOS_VALIDACAO
    }
    return atuais, continuidade


def atualizar_marcos_validacao(validacao, anterior=None, enviar=None):
    """Avisa marcos amostrais sem confundi-los com aprovação do modelo."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    regra_versao = validacao.get("regra_versao") or VERSAO_REGRAS
    amostra_oficial_id = validacao.get("amostra_oficial_id") or regra_versao
    ids_populacao, continuidade = _continuidade_populacao_por_mercado(
        validacao, anterior, "marcos"
    )
    anteriores_notificados = dict(
        anterior.get("marcos_notificados") or {}
    )
    notificados = {
        mercado: valor
        for mercado, valor in anteriores_notificados.items()
        if continuidade.get(mercado)
    }
    amostras = validacao.get("amostra_por_mercado") or {}
    cruzamentos = {}
    proximos = {}
    for mercado in MERCADOS_VALIDACAO:
        quantidade = max(int(amostras.get(mercado, 0) or 0), 0)
        ultimo = max(int(notificados.get(mercado, 0) or 0), 0)
        atingidos = [marco for marco in MARCOS_VALIDACAO if quantidade >= marco]
        maior_atingido = max(atingidos, default=0)
        if maior_atingido > ultimo:
            cruzamentos[mercado] = {
                "marco": maior_atingido,
                "amostra": quantidade,
            }
        proximos[mercado] = next(
            (marco for marco in MARCOS_VALIDACAO if quantidade < marco),
            None,
        )

    if cruzamentos:
        linhas = [
            f"• {mercado}: {dados['amostra']} resultados independentes "
            f"(marco {dados['marco']})"
            for mercado, dados in cruzamentos.items()
        ]
        atingiu_validavel = any(
            dados["marco"] >= 100 for dados in cruzamentos.values()
        )
        explicacao = (
            "O marco de 100 torna a amostra validável, mas não aprova o "
            "modelo. Wilson, ROI, validação cronológica e drift ainda precisam "
            "passar; os alertas continuam condicionados a esses critérios."
            if atingiu_validavel else
            "O marco de 30 inicia somente a pré-validação. Os alertas "
            "permanecem bloqueados até a amostra e todos os critérios finais."
        )
        enviado = enviar(
            "📊 MARCO DA VALIDAÇÃO PACKBALL\n\n"
            + "\n".join(linhas)
            + f"\n\nRegra: {regra_versao}\n{explicacao}"
        )
        if enviado:
            for mercado, dados in cruzamentos.items():
                notificados[mercado] = dados["marco"]

    validacao["regra_versao_marcos"] = regra_versao
    validacao["amostra_oficial_id_marcos"] = amostra_oficial_id
    validacao["amostra_populacao_id_marcos"] = (
        validacao.get("amostra_populacao_id")
        or _normalizar_id_populacao_calibracao(amostra_oficial_id)
    )
    validacao["amostra_populacao_id_por_mercado_marcos"] = ids_populacao
    validacao["marcos_notificados"] = notificados
    validacao["proximo_marco_por_mercado"] = proximos
    return validacao


def atualizar_alertas_estado_calibracoes(
    validacao, anterior=None, enviar=None
):
    """Notifica somente transições reais e repete se a entrega falhar."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    regra_versao = validacao.get("regra_versao") or VERSAO_REGRAS
    amostra_oficial_id = validacao.get("amostra_oficial_id") or regra_versao
    estados = validacao.get("estado_calibracoes") or {}
    ids_populacao, continuidade = _continuidade_populacao_por_mercado(
        validacao, anterior, "estado_calibracoes"
    )
    estados_anteriores = dict(
        anterior.get("calibracoes_estado_notificado") or {}
    )
    notificados = {
        mercado: valor
        for mercado, valor in estados_anteriores.items()
        if continuidade.get(mercado)
    }
    finais_anteriores = dict(
        anterior.get("calibracoes_validacao_final_notificada") or {}
    )
    validacoes_finais_notificadas = {
        mercado: valor
        for mercado, valor in finais_anteriores.items()
        if continuidade.get(mercado)
    }
    for mercado in MERCADOS_VALIDACAO:
        atual = estados.get(mercado) or {
            "ativa": False, "amostra": 0, "motivo": "modelo_ausente"
        }
        ativa = bool(atual.get("ativa"))
        amostra = int(atual.get("amostra", 0) or 0)
        estado_anterior = notificados.get(mercado)
        if ativa and estado_anterior is not True:
            rotulo = ROTULOS_MERCADOS.get(mercado, mercado)
            roi = atual.get("roi_validacao_agregado")
            auc = atual.get("auc_validacao")
            entregue = enviar(
                "✅ CALIBRAÇÃO PROFISSIONAL ATIVADA\n\n"
                f"Mercado: {rotulo}\n"
                f"Regra: {regra_versao}\n"
                f"Amostra independente: {atual.get('amostra', 0)}\n"
                "Validação cronológica: "
                f"{atual.get('amostra_validacao', 0)} resultado(s)\n"
                f"ROI da validação: {roi if roi is not None else '-'}\n"
                f"AUC da validação: {auc if auc is not None else '-'}\n\n"
                "O mercado passou pelos critérios cronológicos. Novos "
                "sinais oficiais ainda obedecem confiança mínima, odds, "
                "limites diários e circuit breaker."
            )
            if entregue:
                notificados[mercado] = True
        elif not ativa and estado_anterior is True:
            rotulo = ROTULOS_MERCADOS.get(mercado, mercado)
            entregue = enviar(
                "⛔ CALIBRAÇÃO PROFISSIONAL DESATIVADA\n\n"
                f"Mercado: {rotulo}\n"
                f"Regra: {regra_versao}\n"
                f"Motivo: {atual.get('motivo') or 'revalidação'}\n\n"
                "Novos sinais oficiais desse mercado estão bloqueados; "
                "a coleta e as simulações continuam."
            )
            if entregue:
                notificados[mercado] = False
        elif (
            not ativa
            and estado_anterior is not True
            and amostra >= MARCOS_VALIDACAO[-1]
            and mercado not in validacoes_finais_notificadas
        ):
            rotulo = ROTULOS_MERCADOS.get(mercado, mercado)
            motivo = atual.get("motivo") or "criterios_finais"
            roi = atual.get("roi_validacao_agregado")
            auc = atual.get("auc_validacao")
            entregue = enviar(
                "⚠️ VALIDAÇÃO PROFISSIONAL CONCLUÍDA — NÃO APROVADA\n\n"
                f"Mercado: {rotulo}\n"
                f"Regra: {regra_versao}\n"
                f"Amostra independente: {amostra}\n"
                "Validação cronológica: "
                f"{atual.get('amostra_validacao', 0)} resultado(s)\n"
                f"ROI da validação: {roi if roi is not None else '-'}\n"
                f"AUC da validação: {auc if auc is not None else '-'}\n"
                f"Motivo técnico: {motivo}\n\n"
                "Esse mercado continua somente em simulação. Resultados "
                "posteriores monitoram drift, mas não reabrem esta decisão. "
                "Uma nova tentativa exige nova política ou linhagem "
                "pré-registrada."
            )
            if entregue:
                validacoes_finais_notificadas[mercado] = {
                    "amostra": amostra,
                    "motivo": motivo,
                }
                notificados[mercado] = False
        elif estado_anterior is None and not ativa:
            # Estado inicial inativo não é um evento e não deve gerar ruído.
            notificados[mercado] = False
    validacao["regra_versao_estado_calibracoes"] = regra_versao
    validacao["amostra_oficial_id_estado_calibracoes"] = amostra_oficial_id
    validacao["amostra_populacao_id_estado_calibracoes"] = (
        validacao.get("amostra_populacao_id")
        or _normalizar_id_populacao_calibracao(amostra_oficial_id)
    )
    validacao[
        "amostra_populacao_id_por_mercado_estado_calibracoes"
    ] = ids_populacao
    validacao["calibracoes_estado_notificado"] = notificados
    validacao["calibracoes_validacao_final_notificada"] = (
        validacoes_finais_notificadas
    )
    return validacao


def atualizar_marcos_odds_periodos(validacao, anterior=None, enviar=None):
    """Avisa uma vez quando uma fonte comprovar O/U asiático de duas opções."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    mesma_versao = (
        anterior.get("versao_detector_odds_periodos")
        == VERSAO_DETECCAO_ODDS_PERIODOS
    )
    notificados = (
        dict(anterior.get("marcos_odds_periodos") or {})
        if mesma_versao else {}
    )
    resumo = validacao.get("odds_escanteios_periodos") or {}
    novos = {
        periodo: dados
        for periodo, dados in resumo.items()
        if dados.get("mapeada") and periodo not in notificados
    }
    if novos:
        linhas = []
        for periodo, dados in novos.items():
            ofertas = ", ".join(
                f"{float(linha):g}"
                for linha in dados.get("linhas_asiaticas") or []
            ) or "-"
            fontes = [
                {
                    "packball": "PackBall",
                    "api_football": "API-Football",
                    "bet365_site": "Bet365",
                }.get(str(fonte), str(fonte))
                for fonte in dados.get("fontes") or []
            ]
            fontes_texto = ", ".join(fontes) or "não identificada"
            linhas.append(
                f"• {periodo}: linhas {ofertas} | fonte {fontes_texto} | "
                "evidência "
                f"{dados.get('ultima_asiatica_em') or '-'}"
            )
        enviado = enviar(
            "📐 LINHA ASIÁTICA DETECTADA — FONTE CONFIRMADA\n\n"
            + "\n".join(linhas)
            + "\n\nO formato foi confirmado como over/under de duas opções; "
            "mercados Exactly não contam. Isso habilita somente a coleta e "
            "a amostra independente — sinais oficiais continuam bloqueados "
            "até a calibração profissional."
        )
        if enviado:
            detectado_em = datetime.now().replace(microsecond=0).isoformat()
            for periodo, dados in novos.items():
                notificados[periodo] = {
                    "detectado_em": detectado_em,
                    "evidencia_em": dados.get("ultima_asiatica_em"),
                    "linhas": list(dados.get("linhas_asiaticas") or []),
                    "fontes": list(dados.get("fontes") or []),
                }
    validacao["versao_detector_odds_periodos"] = (
        VERSAO_DETECCAO_ODDS_PERIODOS
    )
    validacao["marcos_odds_periodos"] = notificados
    return validacao


def atualizar_alerta_cota_api(validacao, anterior=None, enviar=None):
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    contador = validacao.get("contador_api") or {}
    dia = contador.get("dia")
    consumo = contador.get("consumo_dia")
    limite = contador.get("limite_diario_seguro")
    mesmo_dia = bool(dia and anterior.get("cota_api_dia") == dia)
    notificado = (
        int(anterior.get("limiar_cota_api_notificado") or 0)
        if mesmo_dia else 0
    )
    percentual = (
        float(consumo) / float(limite) * 100
        if contador.get("saudavel")
        and consumo is not None
        and limite
        else None
    )
    atingidos = (
        [limiar for limiar in LIMIARES_COTA_API if percentual >= limiar]
        if percentual is not None else []
    )
    maior_atingido = max(atingidos, default=0)
    if maior_atingido > notificado:
        restante = max(int(limite) - int(consumo), 0)
        complemento = (
            "O teto seguro foi atingido e novas chamadas da API estão "
            "bloqueadas até a virada do dia. O PackBall continua como fonte "
            "principal."
            if maior_atingido >= 100 else
            "O PackBall continua como fonte principal. O bot preservará a "
            "reserva e bloqueará a API automaticamente no teto seguro."
        )
        enviado = enviar(
            "📡 USO DIÁRIO DA API-FOOTBALL\n\n"
            f"Consumo: {int(consumo)}/{int(limite)}\n"
            f"Faixa atingida: {maior_atingido}%\n"
            f"Saldo seguro: {restante}\n\n{complemento}"
        )
        if enviado:
            notificado = maior_atingido

    validacao["cota_api_dia"] = dia
    validacao["limiar_cota_api_notificado"] = notificado
    validacao["proximo_limiar_cota_api"] = (
        next(
            (
                limiar for limiar in LIMIARES_COTA_API
                if percentual is not None and percentual < limiar
            ),
            None,
        )
        if percentual is not None else None
    )
    return validacao


def verificar_sessao_packball(
    caminho, agora=None, aviso_horas=AVISO_SESSAO_PACKBALL_HORAS,
    caminho_estado_acesso=None,
):
    """Cruza o token local com a aceitação real observada no PackBall."""
    agora = agora or datetime.now()

    def finalizar(resultado):
        if caminho_estado_acesso is None:
            return resultado
        acesso = verificar_acesso_packball(
            caminho_estado_acesso, agora=agora
        )
        if not (
            acesso.get("ativo")
            and acesso.get("motivo_persistido") == "falha_login_packball"
        ):
            return resultado
        return {
            **resultado,
            "saudavel": False,
            "estado": "login_manual_necessario",
            "motivo": "falha_login_packball",
            "requer_renovacao": True,
            "autoridade_estado": "resposta_real_packball",
            "pausado_ate": acesso.get("pausado_ate"),
        }

    try:
        storage_state = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return finalizar({
            "saudavel": False,
            "estado": "ausente",
            "motivo": "sessao_ausente",
            "requer_renovacao": True,
        })
    except (OSError, json.JSONDecodeError):
        return finalizar({
            "saudavel": False,
            "estado": "invalida",
            "motivo": "sessao_invalida",
            "requer_renovacao": True,
        })

    diagnostico = diagnosticar_storage_state(storage_state, agora=agora)
    if diagnostico.get("saudavel") is not True:
        return finalizar({
            "saudavel": False,
            "estado": "expirada" if diagnostico.get("motivo")
            == "sessao_expirada" else "invalida",
            "motivo": diagnostico.get("motivo") or "sessao_invalida",
            "expira_em": diagnostico.get("expira_em"),
            "requer_renovacao": True,
        })

    expira_em = diagnostico.get("expira_em")
    restante_horas = None
    if expira_em:
        try:
            expiracao = datetime.fromisoformat(expira_em)
            restante_horas = max(
                (expiracao - agora).total_seconds() / 3600.0, 0.0
            )
        except (TypeError, ValueError):
            restante_horas = None
    requer_renovacao = bool(
        restante_horas is not None
        and restante_horas <= max(float(aviso_horas), 0.0)
    )
    return finalizar({
        "saudavel": True,
        "estado": "expira_em_breve" if requer_renovacao else "valida",
        "motivo": None,
        "expira_em": expira_em,
        "restante_horas": (
            round(restante_horas, 1)
            if restante_horas is not None else None
        ),
        "requer_renovacao": requer_renovacao,
        "aviso_horas": aviso_horas,
    })


def atualizar_alerta_sessao_packball(
    validacao, anterior=None, enviar=None
):
    """Notifica uma vez por expiracao e confirma a renovacao posterior."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    sessao = validacao.get("sessao_packball") or {}
    expira_em = sessao.get("expira_em")
    estado_sessao = sessao.get("estado") or "desconhecida"
    # A data de expiração identifica a sessão, mas não a fase do alerta.
    # Uma sessão renovada pode ser registrada como ``valida`` e, dias depois,
    # entrar em ``expira_em_breve`` mantendo exatamente a mesma data. Portanto
    # a assinatura precisa incluir ambos para que cada transição seja avisada.
    assinatura = (
        f"{expira_em}|{estado_sessao}"
        if expira_em else estado_sessao
    )
    assinatura_alertada = anterior.get("sessao_packball_alerta_assinatura")
    alerta_ativo_anterior = bool(
        anterior.get("sessao_packball_alerta_ativo")
    )
    requer_renovacao = bool(
        sessao.get("requer_renovacao")
        or sessao.get("saudavel") is not True
    )

    alerta_ativo = alerta_ativo_anterior
    legado_preventivo_ja_entregue = bool(
        requer_renovacao
        and estado_sessao == "expira_em_breve"
        and alerta_ativo_anterior
        and expira_em
        and assinatura_alertada == expira_em
    )
    if legado_preventivo_ja_entregue:
        # Migra sem repetir o aviso que a versão anterior já confirmou.
        assinatura_alertada = assinatura
        alerta_ativo = True
    elif requer_renovacao and (
        assinatura != assinatura_alertada or not alerta_ativo_anterior
    ):
        if estado_sessao == "login_manual_necessario":
            entregue = enviar(
                "⚠️ PACKBALL PRECISA DE LOGIN\n\n"
                "O site recusou a sessão salva durante a coleta.\n"
                "Sinais oficiais estão pausados; as APIs continuam apenas "
                "coletando em sombra.\n\n"
                "Faça o login manual no computador para retomar."
            )
        else:
            restante = sessao.get("restante_horas")
            prazo = (
                f"Restam aproximadamente {restante:.1f} horas."
                if isinstance(restante, (int, float)) else
                "A sessao nao esta disponivel ou ja expirou."
            )
            entregue = enviar(
                "AVISO DE SESSAO DO PACKBALL\n\n"
                f"Estado: {estado_sessao}\n"
                f"Expira em: {expira_em or '-'}\n"
                f"{prazo}\n\n"
                "Renove o login antes do vencimento para evitar interrupcao. "
                "Nenhum token ou senha foi incluído neste aviso."
            )
        if entregue:
            assinatura_alertada = assinatura
            alerta_ativo = True
    elif (
        not requer_renovacao
        and alerta_ativo_anterior
        and assinatura != assinatura_alertada
    ):
        entregue = enviar(
            "Sessao do PackBall renovada e novamente fora da janela "
            "de vencimento preventivo."
        )
        if entregue:
            assinatura_alertada = assinatura
            alerta_ativo = False

    validacao["sessao_packball_alerta_assinatura"] = assinatura_alertada
    validacao["sessao_packball_alerta_ativo"] = alerta_ativo
    alerta_pendente = bool(requer_renovacao and not alerta_ativo)
    validacao["sessao_packball_alerta_pendente"] = alerta_pendente
    validacao["sessao_packball_alerta_pendente_motivo"] = (
        "entrega_nao_confirmada" if alerta_pendente else None
    )
    return validacao


def resumir_operacao_diaria(
    caminho_banco, agora=None, destinos_resultado=None,
):
    """Resume o dia ativo sem alterar o banco nem consumir a API externa."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    dia = agora.date().isoformat()
    caminho_banco = Path(caminho_banco)
    destinos_resultado = tuple(dict.fromkeys(
        str(destino).strip()
        for destino in (destinos_resultado or ())
        if str(destino).strip()
    ))
    filtro_destinos = ""
    parametros_destinos = ()
    if destinos_resultado:
        canais_visiveis = tuple(destinos_resultado) + tuple(
            f"{destino}:teste" for destino in destinos_resultado
        )
        marcadores = ", ".join("?" for _ in canais_visiveis)
        filtro_destinos = f" AND e.canal IN ({marcadores})"
        parametros_destinos = canais_visiveis
    resumo = {
        "saudavel": False,
        "dia": dia,
        "regra_versao": VERSAO_REGRAS,
        "regra_versoes_por_mercado": {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in MERCADOS_VALIDACAO
        },
        "aprovados_novos": 0,
        "pendentes": 0,
        "pendentes_por_mercado": {},
        "resultados": {
            "total": 0, "greens": 0, "reds": 0,
            "retorno_unidades": 0.0, "roi": None,
        },
        "resultados_por_mercado": {},
        "alertas_oficiais": 0,
        "simulacoes": 0,
        "risco_oficial": {},
    }
    if not caminho_banco.exists():
        resumo["motivo"] = "banco_ausente"
        return resumo
    try:
        conexao = sqlite3.connect(
            f"file:{caminho_banco.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=10,
        )
        conexao.row_factory = sqlite3.Row
        limites_risco = obter_limites_risco()
        regra_fingerprint = fingerprint_vinculado_no_banco(
            conexao, VERSAO_REGRAS
        )
        if regra_fingerprint is None:
            resumo["motivo"] = "linhagem_regra_indisponivel"
            return resumo
        resumo["regra_fingerprint"] = regra_fingerprint
        fingerprints = {}
        for versao in set(
            resumo["regra_versoes_por_mercado"].values()
        ):
            fingerprint = fingerprint_vinculado_no_banco(conexao, versao)
            if fingerprint:
                fingerprints[versao] = fingerprint
        resumo["regra_fingerprints"] = fingerprints
        pares_ativos = [
            (mercado, versao, fingerprints[versao])
            for mercado, versao in (
                resumo["regra_versoes_por_mercado"].items()
            )
            if versao in fingerprints
        ]
        filtro_regras_ativas = " OR ".join(
            "(s.mercado=? AND s.regra_versao=? "
            "AND s.regra_fingerprint=?)"
            for _ in pares_ativos
        )
        parametros_regras_ativas = [
            valor
            for par in pares_ativos
            for valor in par
        ]
        risco_oficial = resumir_risco_alertas_oficiais_conexao(
            conexao, agora
        )
        risco_oficial.update({
            "limite_reds_consecutivos": (
                limites_risco.limite_reds_consecutivos_oficiais
            ),
            "limite_perda_diaria": (
                limites_risco.limite_perda_diaria_oficial
            ),
        })
        motivos_bloqueio = []
        if (
            risco_oficial["reds_consecutivos_24h"]
            >= risco_oficial["limite_reds_consecutivos"]
        ):
            motivos_bloqueio.append("reds_consecutivos")
        if (
            risco_oficial["perda_realizada_hoje"]
            >= risco_oficial["limite_perda_diaria"]
        ):
            motivos_bloqueio.append("perda_diaria")
        risco_oficial["bloqueado"] = bool(motivos_bloqueio)
        risco_oficial["motivos_bloqueio"] = motivos_bloqueio
        resumo["risco_oficial"] = risco_oficial
        resumo["aprovados_novos"] = int(conexao.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT s.partida_id, s.mercado
                FROM sinais s
                WHERE s.status='aprovado'
                  AND ({filtro_regras_ativas})
                  AND json_extract(
                      s.features_json, '$.exploracao_sombra.versao'
                  ) IS NULL
                  AND date(s.criado_em)=date(?)
                GROUP BY s.partida_id, s.mercado
            )
            """.format(filtro_regras_ativas=filtro_regras_ativas),
            (*parametros_regras_ativas, dia),
        ).fetchone()[0] or 0)
        pendentes_por_mercado = {
            linha["mercado"]: int(linha["quantidade"] or 0)
            for linha in conexao.execute(
                """
                WITH independentes AS (
                    SELECT s.mercado, r.sinal_id AS resultado_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY s.partida_id, s.mercado,
                                            s.regra_versao
                               ORDER BY datetime(s.criado_em), s.id
                           ) AS ordem
                    FROM sinais s
                    LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
                    WHERE s.status IN ('aprovado', 'simulacao')
                      AND ({filtro_regras_ativas})
                      AND json_extract(
                          s.features_json, '$.exploracao_sombra.versao'
                      ) IS NULL
                )
                SELECT mercado, COUNT(*) AS quantidade
                FROM independentes
                WHERE ordem=1 AND resultado_id IS NULL
                GROUP BY mercado
                """.format(filtro_regras_ativas=filtro_regras_ativas),
                parametros_regras_ativas,
            ).fetchall()
        }
        resumo["pendentes_por_mercado"] = pendentes_por_mercado
        resumo["pendentes"] = sum(pendentes_por_mercado.values())
        linhas = conexao.execute(
            """
            SELECT mercado, resultado, retorno_unidades
            FROM sinais s
            JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status IN ('aprovado', 'simulacao')
              AND r.resultado IN (
                  'green','half_green','red','half_red'
              )
              AND date(r.encerrado_em)=date(?)
               AND EXISTS (
                   SELECT 1
                   FROM entregas_alertas e
                   WHERE e.sinal_id=s.id
                     AND e.status='entregue'
                     AND e.canal NOT LIKE '%:resultado'
                     {filtro_destinos}
               )
             ORDER BY mercado
            """.format(filtro_destinos=filtro_destinos),
            (dia, *parametros_destinos),
        ).fetchall()
        por_mercado = {}
        for linha in linhas:
            mercado = linha["mercado"]
            item = por_mercado.setdefault(
                mercado,
                {"total": 0, "greens": 0, "reds": 0,
                 "retorno_unidades": 0.0, "roi": None},
            )
            item["total"] += 1
            if linha["resultado"] in ("green", "half_green"):
                item["greens"] += 1
            else:
                item["reds"] += 1
            item["retorno_unidades"] += float(
                linha["retorno_unidades"] or 0
            )
        for item in por_mercado.values():
            item["retorno_unidades"] = round(
                item["retorno_unidades"], 4
            )
            item["roi"] = round(
                item["retorno_unidades"] / item["total"], 4
            ) if item["total"] else None
        resumo["resultados_por_mercado"] = por_mercado
        geral = resumo["resultados"]
        geral["total"] = sum(item["total"] for item in por_mercado.values())
        geral["greens"] = sum(
            item["greens"] for item in por_mercado.values()
        )
        geral["reds"] = sum(item["reds"] for item in por_mercado.values())
        geral["retorno_unidades"] = round(sum(
            item["retorno_unidades"] for item in por_mercado.values()
        ), 4)
        geral["roi"] = round(
            geral["retorno_unidades"] / geral["total"], 4
        ) if geral["total"] else None
        entregas = conexao.execute(
            """
            SELECT
                SUM(CASE WHEN e.canal NOT LIKE '%:teste%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.canal LIKE '%:teste' THEN 1 ELSE 0 END)
            FROM entregas_alertas e
             JOIN sinais s ON s.id=e.sinal_id
             WHERE e.status='entregue' AND date(e.entregue_em)=date(?)
               AND ({filtro_regras_ativas})
               {filtro_destinos}
               AND json_extract(
                   s.features_json, '$.exploracao_sombra.versao'
               ) IS NULL
            """.format(
                filtro_regras_ativas=filtro_regras_ativas,
                filtro_destinos=filtro_destinos,
            ),
            (dia, *parametros_regras_ativas, *parametros_destinos),
        ).fetchone()
        resumo["alertas_oficiais"] = int(entregas[0] or 0)
        resumo["simulacoes"] = int(entregas[1] or 0)
        resumo["saudavel"] = True
        return resumo
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        resumo["motivo"] = "resumo_diario_falhou"
        resumo["erro"] = type(erro).__name__
        return resumo
    finally:
        if "conexao" in locals():
            conexao.close()


def _estado_calibracao_resumo(estado):
    estado = estado or {}
    if estado.get("ativa"):
        return "liberado"
    motivo = estado.get("motivo") or "modelo_inativo"
    rotulos = {
        "amostra_insuficiente": "formando_amostra",
        "pontuacao_sem_discriminacao": "reprovado_sem_vantagem",
        "roi_validacao_insuficiente": "reprovado_roi",
        "auc_validacao_insuficiente": "reprovado_discriminacao",
    }
    return rotulos.get(motivo, str(motivo))


def descrever_filtro_ativo_resumo_diario(resumo):
    comparacao = resumo.get("comparacao") or {}
    enviadas = resumo.get("enviadas") or {}
    filtradas = resumo.get("filtradas") or {}

    def roi_texto(metricas):
        roi = metricas.get("roi")
        return "-" if roi is None else f"{float(roi) * 100:+.1f}%"

    estado = {
        "aguardando_amostra": "aguardando amostra",
        "nao_comprovado": "vantagem não comprovada",
        "evidencia_favoravel": "evidência favorável",
    }.get(
        comparacao.get("decisao"),
        comparacao.get("decisao") or "aguardando amostra",
    )
    mercado = resumo.get("mercado")
    return (
        f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
        f"enviados {int(enviadas.get('greens', 0) or 0)}G/"
        f"{int(enviadas.get('reds', 0) or 0)}R "
        f"(ROI {roi_texto(enviadas)}) | filtrados "
        f"{int(filtradas.get('greens', 0) or 0)}G/"
        f"{int(filtradas.get('reds', 0) or 0)}R "
        f"(ROI {roi_texto(filtradas)}) | {estado} | mínimo "
        f"{int(comparacao.get('amostra_minima_por_coorte', 30) or 30)}/grupo"
    )


def comprimento_texto_telegram(texto):
    """Conta unidades UTF-16, margem conservadora usada pelo Telegram."""
    return len(str(texto).encode("utf-16-le")) // 2


def _fatiar_texto_por_unidades_telegram(texto, limite):
    fatias = []
    atual = []
    unidades = 0
    for caractere in str(texto):
        peso = 2 if ord(caractere) > 0xFFFF else 1
        if atual and unidades + peso > limite:
            fatias.append("".join(atual))
            atual = []
            unidades = 0
        atual.append(caractere)
        unidades += peso
    if atual:
        fatias.append("".join(atual))
    return fatias


def dividir_resumo_diario_telegram(
    mensagem, limite=LIMITE_PARTE_RESUMO_DIARIO,
):
    """Divide sem perder texto e deixa margem abaixo dos 4096 caracteres."""
    mensagem = str(mensagem)
    limite = max(int(limite), 256)
    if comprimento_texto_telegram(mensagem) <= limite:
        return [mensagem]

    # O cabecalho depende do total de partes. A reserva torna o resultado
    # estavel sem precisar refazer cortes quando o total ganha outro digito.
    limite_conteudo = limite - 80
    partes_brutas = []
    atual = ""
    for linha in mensagem.splitlines(keepends=True):
        if comprimento_texto_telegram(linha) > limite_conteudo:
            if atual:
                partes_brutas.append(atual)
                atual = ""
            partes_brutas.extend(
                trecho
                for trecho in _fatiar_texto_por_unidades_telegram(
                    linha, limite_conteudo
                )
                if trecho
            )
            continue
        candidato = atual + linha
        if (
            atual
            and comprimento_texto_telegram(candidato) > limite_conteudo
        ):
            partes_brutas.append(atual)
            atual = linha
        else:
            atual = candidato
    if atual:
        partes_brutas.append(atual)

    total = len(partes_brutas)
    partes = [
        f"[Resumo diario - parte {indice}/{total}]\n\n{conteudo}"
        for indice, conteudo in enumerate(partes_brutas, start=1)
    ]
    if not partes or any(
        comprimento_texto_telegram(parte) > limite for parte in partes
    ):
        raise ValueError("divisao_resumo_diario_excedeu_limite")
    return partes


def _criar_manifesto_resumo_diario(dia, mensagem):
    partes = dividir_resumo_diario_telegram(mensagem)
    registros = []
    for numero, texto in enumerate(partes, start=1):
        registros.append({
            "numero": numero,
            "chave": (
                f"{VERSAO_ENTREGA_RESUMO_DIARIO}|{dia}|"
                f"parte-{numero:03d}"
            ),
            "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
            "texto": texto,
            "entregue": False,
        })
    return {
        "versao": VERSAO_ENTREGA_RESUMO_DIARIO,
        "dia": str(dia),
        "partes_total": len(registros),
        "partes": registros,
        "concluida": False,
    }


def _manifesto_resumo_diario_valido(manifesto, dia):
    try:
        if not isinstance(manifesto, dict):
            return False
        if (
            manifesto.get("versao") != VERSAO_ENTREGA_RESUMO_DIARIO
            or manifesto.get("dia") != str(dia)
        ):
            return False
        partes = manifesto.get("partes")
        if not isinstance(partes, list) or not partes:
            return False
        partes_total = manifesto.get("partes_total")
        if (
            isinstance(partes_total, bool)
            or not isinstance(partes_total, int)
            or partes_total != len(partes)
        ):
            return False
        for numero, parte in enumerate(partes, start=1):
            if not isinstance(parte, dict):
                return False
            texto = parte.get("texto")
            chave = (
                f"{VERSAO_ENTREGA_RESUMO_DIARIO}|{dia}|"
                f"parte-{numero:03d}"
            )
            if (
                parte.get("numero") != numero
                or parte.get("chave") != chave
                or not isinstance(texto, str)
                or comprimento_texto_telegram(texto)
                > LIMITE_PARTE_RESUMO_DIARIO
                or parte.get("sha256")
                != hashlib.sha256(texto.encode("utf-8")).hexdigest()
            ):
                return False
        return True
    except (TypeError, ValueError, UnicodeError):
        return False


def _copiar_manifesto_resumo_diario(manifesto):
    return {
        **manifesto,
        "partes": [dict(parte) for parte in manifesto.get("partes") or []],
    }


def _enviar_parte_resumo_diario(enviar, enviar_parte, texto, chave):
    if enviar_parte is not None:
        return bool(enviar_parte(texto, chave))
    if enviar is enviar_alerta:
        return bool(enviar_alerta(
            texto,
            chave_evento=chave,
            deduplicacao_minutos=None,
        ))
    return bool(enviar(texto))


def atualizar_alerta_risco_oficial(validacao, anterior=None, enviar=None):
    """Notifica uma vez ao bloquear e uma vez ao recuperar o risco oficial."""
    anterior = anterior or {}
    enviar = enviar or enviar_alerta
    resumo = validacao.get("resumo_operacao_diaria") or {}
    risco = resumo.get("risco_oficial") or {}
    alertado_anterior = bool(
        anterior.get("circuit_breaker_oficial_alertado")
    )
    if not resumo.get("saudavel") or not risco:
        validacao["circuit_breaker_oficial_alertado"] = alertado_anterior
        validacao["circuit_breaker_oficial_estado"] = anterior.get(
            "circuit_breaker_oficial_estado", "indisponivel"
        )
        return validacao

    bloqueado = bool(risco.get("bloqueado"))
    if bloqueado and not alertado_anterior:
        motivos = ", ".join(risco.get("motivos_bloqueio") or [])
        enviado = enviar(
            "🛑 CIRCUIT BREAKER OFICIAL ATIVADO\n\n"
            "Novos sinais oficiais foram pausados automaticamente.\n"
            f"Motivo: {motivos or 'limite de risco'}\n"
            f"Reds consecutivos em 24h: "
            f"{risco.get('reds_consecutivos_24h', 0)}/"
            f"{risco.get('limite_reds_consecutivos', '-')}\n"
            f"Perda realizada hoje: "
            f"{float(risco.get('perda_realizada_hoje', 0)):.2f}/"
            f"{risco.get('limite_perda_diaria', '-')}u\n"
            f"Placar oficial de hoje: "
            f"{risco.get('greens_hoje', 0)} greens / "
            f"{risco.get('reds_hoje', 0)} reds\n\n"
            "Simulações e coleta continuam; nenhuma aposta é executada."
        )
        alertado = bool(enviado)
    elif not bloqueado and alertado_anterior:
        enviado = enviar(
            "✅ CIRCUIT BREAKER OFICIAL NORMALIZADO\n\n"
            "Os limites automáticos de reds/perda não estão mais atingidos. "
            "Qualquer sinal oficial continua sujeito à calibração e aos "
            "demais controles de risco."
        )
        alertado = not bool(enviado)
    else:
        alertado = alertado_anterior

    validacao["circuit_breaker_oficial_alertado"] = alertado
    validacao["circuit_breaker_oficial_estado"] = (
        "bloqueado" if bloqueado else "ativo"
    )
    return validacao


def atualizar_resumo_diario(
    validacao, anterior=None, estado_coleta=None, agora=None,
    enviar=None, enviar_parte=None, hora_envio=HORA_RESUMO_DIARIO,
):
    anterior = anterior or {}
    estado_coleta = estado_coleta or {}
    agora = agora or datetime.now()
    enviar = enviar or enviar_alerta
    resumo = validacao.get("resumo_operacao_diaria") or {}
    dia = resumo.get("dia") or agora.date().isoformat()
    enviado_no_dia = anterior.get("resumo_diario_enviado_em") == dia
    entrega_anterior = anterior.get("resumo_diario_entrega")
    if _manifesto_resumo_diario_valido(entrega_anterior, dia):
        validacao["resumo_diario_entrega"] = (
            _copiar_manifesto_resumo_diario(entrega_anterior)
        )
    hora_envio = min(max(int(hora_envio), 0), 23)
    if (
        agora.hour < hora_envio
        or enviado_no_dia
        or not resumo.get("saudavel")
        or estado_coleta.get("monitor_inicializando")
    ):
        validacao["resumo_diario_enviado_em"] = (
            dia if enviado_no_dia else anterior.get("resumo_diario_enviado_em")
        )
        return validacao

    resultados = resumo.get("resultados") or {}
    roi = resultados.get("roi")
    roi_texto = f"{float(roi) * 100:.1f}%" if roi is not None else "-"
    consumo = validacao.get("contador_api") or {}
    amostras = validacao.get("amostra_por_mercado") or {}
    pendentes_amostra = resumo.get("pendentes_por_mercado") or {}
    versoes_por_mercado = resumo.get("regra_versoes_por_mercado") or {}
    estados_calibracao = validacao.get("estado_calibracoes") or {}
    mercados_resumo = mercados_calibrados_operacionais()
    linhas_amostra = []
    for mercado in mercados_resumo:
        amostra = int(amostras.get(mercado, 0) or 0)
        pendentes = int(pendentes_amostra.get(mercado, 0) or 0)
        versao = versoes_por_mercado.get(mercado)
        sufixo_versao = f" | regra={versao}" if versao else ""
        estado_calibracao = estados_calibracao.get(mercado) or {}
        amostra_modelo = int(
            estado_calibracao.get("amostra", min(amostra, 100)) or 0
        )
        estado_texto_calibracao = _estado_calibracao_resumo(
            estado_calibracao
        )
        linhas_amostra.append(
            f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
            f"modelo={min(amostra_modelo, 100)}/100 | "
            f"monitorados={amostra} | pendentes={pendentes} | "
            f"estado={estado_texto_calibracao}"
            f"{sufixo_versao}"
        )
    challenger = validacao.get("pontuacao_contexto_sombra") or {}
    linhas_challenger = []
    for mercado, item in sorted(
        (challenger.get("por_mercado") or {}).items()
    ):
        amostra_contexto = int(item.get("amostra_total", 0) or 0)
        treino = item.get("treino")
        validacao_futura = int(item.get("validacao", 0) or 0)
        if not amostra_contexto and treino is None:
            continue
        if treino is None:
            progresso = (
                f"treino={amostra_contexto}/"
                f"{int(item.get('amostra_minima_treino', 60) or 60)} | "
                f"G/R={int(item.get('greens', 0) or 0)}/"
                f"{int(item.get('reds', 0) or 0)}"
            )
        else:
            progresso = (
                f"treino congelado={int(treino)} | "
                f"validação futura={validacao_futura}/"
                f"{int(item.get('amostra_minima_validacao', 30) or 30)}"
            )
        linhas_challenger.append(
            f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
            f"{progresso} | estado={item.get('estado') or '-'}"
        )
    bloco_challenger = ""
    if linhas_challenger:
        bloco_challenger = (
            "\n\nChallenger contextual API V4 (somente sombra):\n"
            + "\n".join(linhas_challenger)
        )
    validacao_gols = (
        (validacao.get("exploracao_sombra") or {}).get(
            "validacao_prospectiva_gols"
        ) or {}
    )
    cobertura_validacao_gols = (
        (validacao.get("exploracao_sombra") or {}).get(
            "cobertura_temporal_validacao_gols"
        ) or {}
    )
    linhas_validacao_gols = []
    for mercado in ("gol_ft", "gol_ht"):
        item = validacao_gols.get(mercado) or {}
        if not item:
            continue
        roi_item = item.get("roi")
        roi_item_texto = (
            "-" if roi_item is None
            else f"{float(roi_item) * 100:+.1f}%"
        )
        cobertura_item = cobertura_validacao_gols.get(mercado) or {}
        linhas_validacao_gols.append(
            f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
            f"{int(item.get('avaliadas', 0) or 0)}/"
            f"{int(item.get('minimo_resultados', 30) or 30)} | "
            f"{int(item.get('greens', 0) or 0)}G/"
            f"{int(item.get('reds', 0) or 0)}R | "
            f"ROI {roi_item_texto} | "
            f"estado={item.get('estado') or 'aguardando_amostra_futura'} | "
            "API temporal="
            f"{int(cobertura_item.get('com_evolucao_api', 0) or 0)}/"
            f"{int(cobertura_item.get('total', 0) or 0)} | "
            "confirmação fontes="
            f"{int(cobertura_item.get('com_comparacao_fontes', 0) or 0)}/"
            f"{int(cobertura_item.get('total', 0) or 0)}"
        )
    bloco_validacao_gols = ""
    if linhas_validacao_gols:
        bloco_validacao_gols = (
            "\n\nNova validação prospectiva de gols "
            "(separada das regras antigas):\n"
            + "\n".join(linhas_validacao_gols)
        )
    validacao_gol_ft_v3 = (
        (validacao.get("exploracao_sombra") or {}).get(
            "validacao_prospectiva_gol_ft_v3"
        ) or {}
    )
    bloco_validacao_gol_ft_v3 = ""
    candidatos_v3 = int(
        validacao_gol_ft_v3.get("candidatos_coorte", 0) or 0
    )
    if candidatos_v3 > 0:
        roi_v3 = validacao_gol_ft_v3.get("roi")
        roi_v3_texto = (
            "-" if roi_v3 is None else f"{float(roi_v3) * 100:+.1f}%"
        )
        bloco_validacao_gol_ft_v3 = (
            "\n\nConfirmação Gol FT V3 (somente sombra):\n"
            f"coorte={candidatos_v3}/"
            f"{int(validacao_gol_ft_v3.get('tamanho_coorte_fixa', 75) or 75)} | "
            "válidos="
            f"{int(validacao_gol_ft_v3.get('avaliadas', 0) or 0)}/"
            f"{int(validacao_gol_ft_v3.get('minimo_resultados_validos', 70) or 70)} | "
            f"pendentes={int(validacao_gol_ft_v3.get('pendentes', 0) or 0)} | "
            f"inválidos={int(validacao_gol_ft_v3.get('invalidos', 0) or 0)} | "
            f"G/R={int(validacao_gol_ft_v3.get('greens', 0) or 0)}/"
            f"{int(validacao_gol_ft_v3.get('reds', 0) or 0)} | "
            f"ROI={roi_v3_texto} | "
            f"estado={validacao_gol_ft_v3.get('estado') or '-'} | "
            "Telegram oficial=não | promoção automática=não"
        )
    comparacao_ft_v2_v3 = (
        (validacao.get("exploracao_sombra") or {}).get(
            "comparacao_gol_ft_v2_controle_v3"
        ) or {}
    )
    bloco_comparacao_ft_v2_v3 = ""
    v2_controle = comparacao_ft_v2_v3.get("v2_controle") or {}
    v3_mesma_janela = comparacao_ft_v2_v3.get("v3") or {}
    avaliadas_v2_controle = int(
        v2_controle.get("avaliadas", 0) or 0
    )
    avaliadas_v3_mesma_janela = int(
        v3_mesma_janela.get("avaliadas", 0) or 0
    )
    if avaliadas_v2_controle > 0 and avaliadas_v3_mesma_janela > 0:
        roi_v2_controle = v2_controle.get("roi")
        roi_v3_mesma_janela = v3_mesma_janela.get("roi")
        roi_v2_texto = (
            "-" if roi_v2_controle is None
            else f"{float(roi_v2_controle) * 100:+.1f}%"
        )
        roi_v3_janela_texto = (
            "-" if roi_v3_mesma_janela is None
            else f"{float(roi_v3_mesma_janela) * 100:+.1f}%"
        )
        delta_texto = "-"
        if roi_v2_controle is not None and roi_v3_mesma_janela is not None:
            delta_texto = (
                f"{(float(roi_v3_mesma_janela) - float(roi_v2_controle)) * 100:+.1f} pp"
            )
        bloco_comparacao_ft_v2_v3 = (
            "\n\nReteste simultâneo Gol FT "
            "(somente sombra; comparação descritiva):\n"
            f"desde={comparacao_ft_v2_v3.get('iniciado_em') or '-'} | "
            "V2-controle="
            f"{avaliadas_v2_controle} resultado(s), "
            f"{int(v2_controle.get('greens', 0) or 0)}G/"
            f"{int(v2_controle.get('reds', 0) or 0)}R, "
            f"ROI {roi_v2_texto} | V3="
            f"{avaliadas_v3_mesma_janela} resultado(s), "
            f"{int(v3_mesma_janela.get('greens', 0) or 0)}G/"
            f"{int(v3_mesma_janela.get('reds', 0) or 0)}R, "
            f"ROI {roi_v3_janela_texto} | diferença V3-V2={delta_texto} | "
            "Telegram oficial=não | promoção automática=não"
        )
    challenger_longo = validacao.get("pontuacao_longa_sombra") or {}
    linhas_challenger_longo = []
    for mercado, item in sorted(
        (challenger_longo.get("por_mercado") or {}).items()
    ):
        treino = int(item.get("treino", 0) or 0)
        ancora_treino = item.get("treino_ate_sinal_id")
        validacao_futura = int(item.get("validacao", 0) or 0)
        if treino <= 0 and ancora_treino is None:
            continue
        if ancora_treino is None:
            progresso = (
                f"treino prospectivo={treino}/"
                f"{int(item.get('amostra_minima_treino', 60) or 60)}"
            )
        else:
            progresso = (
                f"treino congelado={treino} | "
                f"validação futura={validacao_futura}/"
                f"{int(item.get('amostra_minima_validacao', 30) or 30)}"
            )
        linhas_challenger_longo.append(
            f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
            f"{progresso} | estado={item.get('estado') or '-'}"
        )
    bloco_challenger_longo = ""
    if linhas_challenger_longo:
        bloco_challenger_longo = (
            "\n\nTemporal 5/10/15 V2 (somente sombra):\n"
            + "\n".join(linhas_challenger_longo)
        )
    historico_api_live = validacao.get("historico_api_live") or {}
    bloco_historico_api_live = ""
    if historico_api_live:
        if historico_api_live.get("saudavel"):
            janelas_api = (
                historico_api_live.get("janelas_disponiveis") or {}
            )
            concordancia = historico_api_live.get(
                "taxa_concordancia_packball_api"
            )
            concordancia_texto = (
                "-" if concordancia is None
                else f"{float(concordancia) * 100:.1f}%"
            )
            prontidao_temporal = (
                historico_api_live.get("prontidao_revisao") or {}
            )
            bloco_historico_api_live = (
                "\n\nAuditoria temporal API-Football (somente sombra):\n"
                f"snapshots={int(historico_api_live.get('snapshots', 0) or 0)} | "
                f"fixtures={int(historico_api_live.get('fixtures', 0) or 0)} | "
                "janelas 5/10/15="
                f"{int(janelas_api.get('5', 0) or 0)}/"
                f"{int(janelas_api.get('10', 0) or 0)}/"
                f"{int(janelas_api.get('15', 0) or 0)} | "
                "comparacoes PackBall/API="
                f"{int(historico_api_live.get('comparacoes_packball_api', 0) or 0)} | "
                f"concordancia={concordancia_texto} | prontidao="
                f"{prontidao_temporal.get('estado') or 'aguardando_amostra'} "
                f"({int(prontidao_temporal.get('snapshots', 0) or 0)}/"
                f"{int(prontidao_temporal.get('minimo_snapshots', 30) or 30)} "
                "snapshots, "
                f"{int(prontidao_temporal.get('fixtures', 0) or 0)}/"
                f"{int(prontidao_temporal.get('minimo_fixtures', 10) or 10)} "
                "jogos) | uso nos sinais=nao"
            )
        else:
            bloco_historico_api_live = (
                "\n\nAuditoria temporal API-Football (somente sombra): "
                "indisponivel | uso nos sinais=nao"
            )
    comparacoes_filtros_ativos = (
        validacao.get("comparacao_filtros_regras_ativas") or []
    )
    linhas_filtros_ativos = [
        descrever_filtro_ativo_resumo_diario(item)
        for item in comparacoes_filtros_ativos
    ]
    bloco_filtros_ativos = ""
    if linhas_filtros_ativos:
        bloco_filtros_ativos = (
            "\n\nFiltro prospectivo das regras ativas "
            "(não é aprovação):\n"
            + "\n".join(linhas_filtros_ativos)
        )
    resultados_por_mercado = resumo.get("resultados_por_mercado") or {}
    linhas_resultados = []
    for mercado in mercados_resumo:
        item = resultados_por_mercado.get(mercado) or {}
        linhas_resultados.append(
            f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
            f"{int(item.get('greens', 0) or 0)} G / "
            f"{int(item.get('reds', 0) or 0)} R"
        )
    risco = resumo.get("risco_oficial") or {}
    estado_risco = "BLOQUEADO" if risco.get("bloqueado") else "ativo"
    estado_texto = (
        "saudável"
        if estado_coleta.get("saudavel") and validacao.get("saudavel")
        else "requer atenção"
    )
    identificacao_regras = (
        "Regras ativas: versões específicas por mercado"
        if versoes_por_mercado
        else f"Regra ativa: {resumo.get('regra_versao')}"
    )
    greens = int(resultados.get("greens", 0) or 0)
    reds = int(resultados.get("reds", 0) or 0)
    decididos = greens + reds
    assertividade = (greens / decididos * 100.0) if decididos else 0.0
    assertividade_texto = f"{assertividade:.2f}".replace(".", ",")
    try:
        dia_texto = datetime.fromisoformat(str(dia)).strftime("%d/%m")
    except (TypeError, ValueError):
        dia_texto = str(dia)
    mensagem = (
        f"🤖 RELATÓRIO PARCIAL ROBÔ - {dia_texto}\n\n"
        f"☺️ {greens} GREENS\n"
        f"✖️ {reds} REDS\n\n"
        f"⬆️ Assertividade: {assertividade_texto}%\n\n"
        "🤖 I.A ligada 24h"
    )
    if _manifesto_resumo_diario_valido(entrega_anterior, dia):
        manifesto = _copiar_manifesto_resumo_diario(entrega_anterior)
    else:
        manifesto = _criar_manifesto_resumo_diario(dia, mensagem)
    for parte in manifesto["partes"]:
        if parte.get("entregue"):
            continue
        try:
            entregue = _enviar_parte_resumo_diario(
                enviar,
                enviar_parte,
                parte["texto"],
                parte["chave"],
            )
        except Exception:
            entregue = False
        if not entregue:
            break
        parte["entregue"] = True
        parte["entregue_em"] = agora.replace(
            microsecond=0
        ).isoformat()
    concluida = all(
        bool(parte.get("entregue")) for parte in manifesto["partes"]
    )
    manifesto["concluida"] = concluida
    manifesto["partes_entregues"] = sum(
        1 for parte in manifesto["partes"] if parte.get("entregue")
    )
    validacao["resumo_diario_entrega"] = manifesto
    validacao["resumo_diario_enviado_em"] = (
        dia if concluida else anterior.get("resumo_diario_enviado_em")
    )
    return validacao


def carregar_estado_watchdog_sqlite(caminho_banco):
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": {},
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho_banco.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=10,
        )
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (CHAVE_ESTADO_WATCHDOG_SQLITE,),
        ).fetchone()
        if linha is None:
            return {
                "saudavel": False,
                "estado": {},
                "motivo": "estado_persistente_ausente",
            }
        payload = json.loads(linha[0])
        estado = payload.get("estado") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get("versao") != VERSAO_ESTADO_WATCHDOG_SQLITE
            or not isinstance(estado, dict)
        ):
            return {
                "saudavel": False,
                "estado": {},
                "motivo": "estado_persistente_invalido",
            }
        return {
            "saudavel": True,
            "estado": estado,
            "motivo": None,
            "persistido_em": payload.get("persistido_em"),
        }
    except (OSError, sqlite3.Error, TypeError, json.JSONDecodeError):
        return {
            "saudavel": False,
            "estado": {},
            "motivo": "estado_persistente_indisponivel",
        }
    finally:
        if conexao is not None:
            conexao.close()


def persistir_estado_watchdog_sqlite(caminho_banco, estado, agora=None):
    caminho_banco = Path(caminho_banco)
    agora = (agora or datetime.now()).replace(microsecond=0)
    conexao = None
    try:
        estado_persistido = dict(estado or {})
        estado_persistido["persistencia_estado_watchdog"] = {
            "saudavel": True,
            "estado": "persistido",
            "motivo": None,
            "persistido_em": agora.isoformat(),
        }
        payload = json.dumps(
            {
                "versao": VERSAO_ESTADO_WATCHDOG_SQLITE,
                "persistido_em": agora.isoformat(),
                "estado": estado_persistido,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        conexao = sqlite3.connect(caminho_banco, timeout=10)
        with conexao:
            conexao.execute(
                """
                INSERT INTO metadados (chave, valor) VALUES (?, ?)
                ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor
                """,
                (CHAVE_ESTADO_WATCHDOG_SQLITE, payload),
            )
        return estado_persistido["persistencia_estado_watchdog"]
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "persistencia_estado_watchdog_falhou",
            "erro": type(erro).__name__,
            "persistido_em": None,
        }
    finally:
        if conexao is not None:
            conexao.close()


def carregar_estado_anterior_watchdog(caminho_json, caminho_banco):
    caminho_json = Path(caminho_json)
    if caminho_json.exists():
        try:
            estado = json.loads(caminho_json.read_text(encoding="utf-8"))
            if isinstance(estado, dict):
                return estado, {
                    "origem": "json",
                    "recuperado": False,
                    "motivo": None,
                }
        except (OSError, json.JSONDecodeError):
            pass
    recuperacao = carregar_estado_watchdog_sqlite(caminho_banco)
    if recuperacao["saudavel"]:
        return recuperacao["estado"], {
            "origem": "sqlite",
            "recuperado": True,
            "motivo": None,
            "persistido_em": recuperacao.get("persistido_em"),
        }
    return {}, {
        "origem": "vazio",
        "recuperado": False,
        "motivo": recuperacao.get("motivo"),
    }


_CHAVES_ESTADO_ALERTAS_MONITOR = (
    "alertado",
    "alerta_saude_incidente_id",
    "alerta_reinicio_pendente",
    "alertas_reinicio_pendentes",
    "ultimo_reinicio_em",
)


def _preservar_estado_alertas_monitor(estado, anterior):
    for chave in _CHAVES_ESTADO_ALERTAS_MONITOR:
        if chave not in estado and chave in (anterior or {}):
            estado[chave] = anterior[chave]
    return estado


def _recorte_estado_alertas_monitor(estado):
    return {
        chave: (estado or {}).get(chave)
        for chave in _CHAVES_ESTADO_ALERTAS_MONITOR
        if chave in (estado or {})
    }


def _persistir_alertas_monitor_antecipadamente(estado, anterior):
    """Salva a intencao critica antes das auditorias de ciclo."""
    consolidado = dict(anterior or {})
    consolidado.update(estado or {})
    # O JSON e a fonte preferencial no carregamento. Grava-lo primeiro evita
    # que uma falha posterior deixe uma copia antiga ocultando o SQLite novo.
    gravar_json_atomico(ARQUIVO_ESTADO, consolidado)
    persistencia = persistir_estado_watchdog_sqlite(
        ARQUIVO_BANCO, consolidado
    )
    estado["persistencia_estado_watchdog"] = persistencia
    return persistencia


def auditar_operacao_pre_live(
    pasta, verificar_pid_fn=None, verificar_trava_fn=None,
    verificar_banco_fn=None, resumir_filtro_preciso_fn=None,
    ler_controle_preciso_fn=None,
):
    """Expõe saúde do pré-live sem interferir nos sinais ao vivo."""
    pasta = Path(pasta)
    verificar_pid_fn = verificar_pid_fn or pid_ativo
    verificar_trava_fn = verificar_trava_fn or trava_em_uso
    verificar_banco_fn = verificar_banco_fn or verificar_banco_pre_live
    resumir_filtro_preciso_fn = (
        resumir_filtro_preciso_fn
        or resumir_validacao_pre_live_preciso_arquivo
    )
    ler_controle_preciso_fn = (
        ler_controle_preciso_fn or ler_estado_pre_live_preciso
    )
    processo = ler_estado(pasta / "pre_live_processo.json")
    pid = processo.get("pid")
    status_processo = processo.get("status")
    pid_responde = bool(verificar_pid_fn(pid))
    trava_ativa = bool(
        verificar_trava_fn(pasta / "pre_live_instancia.lock")
    )
    banco = verificar_banco_fn(pasta / "pre_live.db")
    ultima = ler_estado(pasta / "pre_live_estado.json")
    validacao = ultima.get("validacao_depois") or ultima.get(
        "validacao_antes"
    ) or {}
    filtro_preciso = resumir_filtro_preciso_fn(pasta / "pre_live.db")
    controle_filtro_preciso = ler_controle_preciso_fn(
        pasta / "pre_live_preciso_estado.json"
    )
    filtro_preciso["controle_operacional"] = {
        "versao": controle_filtro_preciso.get("versao"),
        "saudavel": controle_filtro_preciso.get("saudavel"),
        "ativo": controle_filtro_preciso.get("ativo"),
        "estado": controle_filtro_preciso.get("estado"),
        "motivo": controle_filtro_preciso.get("motivo"),
        "assinatura": controle_filtro_preciso.get("assinatura"),
        "atualizado_em": controle_filtro_preciso.get("atualizado_em"),
        "reativacao": controle_filtro_preciso.get("reativacao"),
    }
    ativo = bool(trava_ativa and pid_responde)
    inicializando = bool(
        not trava_ativa
        and pid_responde
        and status_processo == "iniciando"
    )
    return {
        "saudavel": bool(ativo and banco.get("valido")),
        "estado": (
            "ativo" if ativo else "inicializando" if inicializando
            else "parado"
        ),
        "pid": pid,
        "status_processo": status_processo,
        "pid_responde": pid_responde,
        "trava_ativa": trava_ativa,
        "banco": banco,
        "ultima_execucao_em": ultima.get("finalizado_em"),
        "ultima_execucao_erro": ultima.get("erro"),
        "jogos_analisados": int(ultima.get("jogos_analisados") or 0),
        "candidatos_elegiveis": int(
            ultima.get("candidatos_elegiveis") or 0
        ),
        "jogos_nao_analisados_limite": int(
            ultima.get("jogos_nao_analisados_limite") or 0
        ),
        "cobertura_analise": ultima.get("cobertura_analise"),
        "limite_analise": ultima.get("limite_analise") or {},
        "bilhetes": int(ultima.get("bilhetes") or 0),
        "resultados": int(validacao.get("resultados") or 0),
        "roi": validacao.get("roi"),
        "apto_revisao": bool(validacao.get("apto_revisao")),
        "filtro_preciso": filtro_preciso,
        "controle_filtro_preciso": controle_filtro_preciso,
    }


def executar_verificacao():
    inicio_verificacao = time.monotonic()
    inicio_fase = [inicio_verificacao]
    duracoes_fases = {}

    def marcar_fase(nome):
        agora_monotonic = time.monotonic()
        duracoes_fases[nome] = round(
            agora_monotonic - inicio_fase[0], 3
        )
        inicio_fase[0] = agora_monotonic

    estado = verificar_coleta(
        ARQUIVO_LOG, limite=LIMITE_SEM_COLETA_SEGUNDOS
    )
    anterior, recuperacao_estado = carregar_estado_anterior_watchdog(
        ARQUIVO_ESTADO, ARQUIVO_BANCO
    )
    estado["recuperacao_estado_watchdog"] = recuperacao_estado
    estado["pre_live"] = aplicar_circuit_breaker_pre_live_preciso(
        auditar_operacao_pre_live(PASTA)
    )
    estado = atualizar_alerta_circuit_breaker_pre_live_preciso(
        estado,
        anterior,
        enviar=enviar_alerta,
    )
    integridade_banco = acionar_recuperacao_banco_ativo(
        ARQUIVO_BANCO,
        PASTA,
        anterior=anterior.get("integridade_banco_ativo") or {},
        enviar=enviar_alerta,
    )
    estado["integridade_banco_ativo"] = integridade_banco
    estado["carteira_operacional"] = verificar_carteira_operacional(
        ARQUIVO_BANCO, PASTA
    )
    marcar_fase("saude_base_e_integridade_sqlite")
    if integridade_banco.get("recuperacao_necessaria"):
        _preservar_estado_alertas_monitor(estado, anterior)
        estado.update({
            "saudavel": False,
            "motivo": integridade_banco.get("motivo"),
            "alertado": bool(anterior.get("alertado", False)),
            "recuperacao_automatica_solicitada": bool(
                integridade_banco.get("manutencao_solicitada")
            ),
            "observabilidade_watchdog": {
                "fases_segundos": dict(duracoes_fases),
                "duracao_total_segundos": round(
                    time.monotonic() - inicio_verificacao, 3
                ),
                "estado": "interrompido_por_integridade_sqlite",
            },
        })
        gravar_json_atomico(ARQUIVO_ESTADO, estado)
        return estado

    estado_processo = ler_estado(ARQUIVO_PROCESSO)
    tolerancia_inicial = monitor_em_inicializacao(
        estado, estado_processo
    )
    estado["monitor_inicializando"] = tolerancia_inicial
    trabalhador_acompanhamento_odd = (
        verificar_trabalhador_acompanhamento_odd(
            ARQUIVO_ESTADO_ACOMPANHAMENTO_ODD,
            monitor_inicializando=tolerancia_inicial,
        )
    )
    estado["trabalhador_acompanhamento_odd"] = (
        trabalhador_acompanhamento_odd
    )
    estado["avaliacao_acompanhamento_odd"] = (
        verificar_avaliacao_acompanhamento_odd(
            ARQUIVO_AVALIACAO_ACOMPANHAMENTO_ODD
        )
    )
    estado["avaliacao_prioridade_ligas_gols"] = (
        verificar_avaliacao_prioridade_ligas_gols(
            ARQUIVO_AVALIACAO_PRIORIDADE_LIGAS_GOLS
        )
    )
    estado["avaliacao_desajuste_odds"] = (
        verificar_avaliacao_desajuste_odds(
            ARQUIVO_AVALIACAO_DESAJUSTE_ODDS
        )
    )
    estado["avaliacao_probabilidade_individual"] = (
        verificar_avaliacao_probabilidade_individual(
            ARQUIVO_AVALIACAO_PROBABILIDADE_INDIVIDUAL
        )
    )
    estado["avaliacao_quarentena_fallback_ht"] = (
        verificar_avaliacao_quarentena_fallback_ht(
            ARQUIVO_AVALIACAO_QUARENTENA_FALLBACK_HT
        )
    )
    reinicio = None
    alertas_monitor_antes = _recorte_estado_alertas_monitor(anterior)
    if os.getenv("WATCHDOG_REINICIO_AUTOMATICO", "1") == "1":
        reinicio = tentar_reiniciar_processo(
            estado, estado_processo, anterior
        )
        if reinicio:
            estado.update(reinicio)
    atualizar_alerta_reinicio_monitor(
        estado, anterior, reinicio=reinicio
    )
    atualizar_alerta_saude_monitor(
        estado,
        anterior,
        tolerancia_inicial=tolerancia_inicial,
    )
    if not reinicio and anterior.get("ultimo_reinicio_em"):
        estado["ultimo_reinicio_em"] = anterior["ultimo_reinicio_em"]
    if (
        _recorte_estado_alertas_monitor(estado)
        != alertas_monitor_antes
    ):
        _persistir_alertas_monitor_antecipadamente(estado, anterior)
    persistencia_conclusao_filtro = (
        persistir_conclusao_experimento_filtro(ARQUIVO_BANCO)
    )
    conexao_notificacoes = None
    try:
        conexao_notificacoes = sqlite3.connect(ARQUIVO_BANCO, timeout=10)
        conexao_notificacoes.row_factory = sqlite3.Row
        reconciliacao_acompanhamentos_odd = (
            reconciliar_acompanhamentos_odd_expirados(
                conexao_notificacoes
            )
        )
        reconciliacao_notificacoes = (
            reconciliar_notificacoes_operacionais(
                conexao_notificacoes
            )
        )
    except (OSError, sqlite3.Error) as erro:
        reconciliacao_acompanhamentos_odd = {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "reconciliacao_acompanhamentos_odd_indisponivel",
            "erro": resumir_erro_seguro(erro),
            "expirados": 0,
        }
        reconciliacao_notificacoes = {
            "saudavel": False,
            "motivo": "reconciliacao_notificacoes_indisponivel",
            "erro": resumir_erro_seguro(erro),
            "reconciliadas": 0,
        }
    finally:
        if conexao_notificacoes is not None:
            conexao_notificacoes.close()
    estado["alerta_recuperacao_banco"] = atualizar_alerta_recuperacao_banco(
        ARQUIVO_RECUPERACAO_BANCO,
        caminho_banco=ARQUIVO_BANCO,
        enviar=enviar_alerta,
    )
    marcar_fase("supervisao_e_reconciliacoes")
    validacao = verificar_validacao(
        ARQUIVO_BANCO,
        estado_coleta=estado,
    )
    validacao["avaliacao_probabilidade_individual"] = estado[
        "avaliacao_probabilidade_individual"
    ]
    if not estado["avaliacao_probabilidade_individual"]["saudavel"]:
        # É uma inferência em sombra: a falha fica visível e bloqueia apenas
        # qualquer conclusão dessa avaliação, nunca a coleta ou os sinais.
        validacao.setdefault("avisos", []).append(
            estado["avaliacao_probabilidade_individual"]["motivo"]
        )
        validacao["requer_atencao"] = True
    validacao["trabalhador_acompanhamento_odd"] = (
        trabalhador_acompanhamento_odd
    )
    if not trabalhador_acompanhamento_odd["saudavel"]:
        validacao.setdefault("avisos", []).append(
            trabalhador_acompanhamento_odd["motivo"]
        )
        validacao["requer_atencao"] = True
    marcar_fase("validacao_principal")
    validacao["reconciliacao_notificacoes_operacionais"] = (
        reconciliacao_notificacoes
    )
    validacao["reconciliacao_acompanhamentos_odd"] = (
        reconciliacao_acompanhamentos_odd
    )
    if not reconciliacao_acompanhamentos_odd["saudavel"]:
        validacao.setdefault("avisos", []).append(
            reconciliacao_acompanhamentos_odd["motivo"]
        )
        validacao["requer_atencao"] = True
    if not reconciliacao_notificacoes["saudavel"]:
        validacao.setdefault("avisos", []).append(
            reconciliacao_notificacoes["motivo"]
        )
        validacao["requer_atencao"] = True
    validacao["persistencia_conclusao_filtro"] = (
        persistencia_conclusao_filtro
    )
    if not persistencia_conclusao_filtro["saudavel"]:
        validacao.setdefault("motivos", []).append(
            "conclusao_experimento_filtro_inconsistente"
        )
        validacao["motivos"] = sorted(set(validacao["motivos"]))
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    backup = verificar_backup_diario(PASTA_BACKUPS)
    validacao["backup_diario"] = backup
    if not backup["saudavel"]:
        validacao.setdefault("motivos", []).append(backup["motivo"])
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    backup_espelho = verificar_backup_espelho(
        PASTA_BACKUPS,
        os.getenv("BACKUP_ESPELHO_DIRETORIO") or None,
        verificar_integridade=False,
    )
    validacao["backup_espelho"] = backup_espelho
    if backup_espelho["configurado"] and not backup_espelho["saudavel"]:
        validacao.setdefault("avisos", []).append(
            "backup_espelho_indisponivel"
        )
        validacao["requer_atencao"] = True
    ponto_recuperacao = verificar_ponto_recuperacao(PASTA_BACKUPS)
    validacao["ponto_recuperacao"] = ponto_recuperacao
    if not ponto_recuperacao["saudavel"]:
        validacao.setdefault("motivos", []).append(
            ponto_recuperacao["motivo"]
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    capacidade = verificar_capacidade_coleta(ARQUIVO_LOG)
    validacao["capacidade_coleta"] = capacidade
    if not capacidade["saudavel"]:
        validacao.setdefault("motivos", []).append(capacidade["motivo"])
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    ritmo_packball = auditar_ritmo_packball(
        ARQUIVO_ACESSO_PACKBALL,
        exigir_distribuicao=(
            os.getenv("PACKBALL_DISTRIBUIR_NAVEGACOES", "0") == "1"
        ),
    )
    validacao["ritmo_acesso_packball"] = ritmo_packball
    if not ritmo_packball["saudavel"]:
        validacao.setdefault("motivos", []).append(
            "ritmo_packball_inseguro"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    experimento_ritmo = avaliar_experimento_ritmo_packball(
        ARQUIVO_LOG,
        ARQUIVO_AVALIACAO_RITMO,
        auditoria_ritmo=ritmo_packball,
        caminho_estado_acesso=ARQUIVO_ACESSO_PACKBALL,
    )
    validacao["experimento_ritmo_packball"] = experimento_ritmo
    if not experimento_ritmo["saudavel"]:
        validacao.setdefault("motivos", []).append(
            "experimento_ritmo_packball_regressao"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    cache_api_operacional = verificar_cache_api_operacional(ARQUIVO_LOG)
    validacao["cache_api_operacional"] = cache_api_operacional
    if not cache_api_operacional["saudavel"]:
        validacao.setdefault("motivos", []).append(
            cache_api_operacional["motivo"]
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    acompanhamento_preco_pos_alerta = (
        verificar_acompanhamento_preco_pos_alerta(ARQUIVO_LOG)
    )
    validacao["acompanhamento_preco_pos_alerta"] = (
        acompanhamento_preco_pos_alerta
    )
    if not acompanhamento_preco_pos_alerta["saudavel"]:
        # Evidência de preço é observabilidade, não gate de entrada. A falha
        # exige atenção, mas não reclassifica a saúde da estratégia nem altera
        # qualquer decisão de sinal.
        validacao.setdefault("avisos", []).append(
            acompanhamento_preco_pos_alerta["motivo"]
        )
        validacao["requer_atencao"] = True
    amostragem_referencia_odds = (
        verificar_amostragem_referencia_odds_sombra(ARQUIVO_LOG)
    )
    validacao["amostragem_referencia_odds_sombra"] = (
        amostragem_referencia_odds
    )
    if amostragem_referencia_odds.get("requer_atencao"):
        # A referência independente é uma investigação em sombra. Sua
        # ausência precisa ficar visível, mas não pode bloquear a estratégia.
        validacao.setdefault("avisos", []).append(
            amostragem_referencia_odds["motivo"]
        )
        validacao["requer_atencao"] = True
    integridade_melhor_preco = (
        verificar_integridade_melhor_preco_sombra(ARQUIVO_BANCO)
    )
    validacao["integridade_melhor_preco_sombra"] = (
        integridade_melhor_preco
    )
    if integridade_melhor_preco.get("requer_atencao"):
        validacao.setdefault("avisos", []).append(
            integridade_melhor_preco["motivo"]
        )
        validacao["requer_atencao"] = True
        if integridade_melhor_preco.get("severidade") == "critica":
            validacao.setdefault("motivos", []).append(
                integridade_melhor_preco["motivo"]
            )
            validacao["saudavel"] = False
    referencia_api_football = verificar_referencia_api_football_sombra(
        ARQUIVO_BANCO
    )
    validacao["referencia_api_football_sombra"] = (
        referencia_api_football
    )
    if referencia_api_football.get("requer_atencao"):
        validacao.setdefault("avisos", []).append(
            referencia_api_football["motivo"]
        )
        validacao["requer_atencao"] = True
        if referencia_api_football.get("severidade") == "critica":
            validacao.setdefault("motivos", []).append(
                referencia_api_football["motivo"]
            )
            validacao["saudavel"] = False
    prioridade_scanner = verificar_prioridade_scanner_packball(ARQUIVO_LOG)
    validacao["prioridade_scanner_packball"] = prioridade_scanner
    if not prioridade_scanner["saudavel"]:
        validacao.setdefault("motivos", []).append(
            prioridade_scanner["motivo"]
        )
        validacao["motivos"] = sorted(set(validacao["motivos"]))
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    fontes_sinais = verificar_fontes_sinais_operacionais(ARQUIVO_LOG)
    validacao["fontes_sinais_operacionais"] = fontes_sinais
    if not fontes_sinais["saudavel"]:
        validacao.setdefault("motivos", []).append(
            fontes_sinais["motivo"]
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    pareamento_api = verificar_pareamento_api(ARQUIVO_LOG)
    validacao["pareamento_api"] = pareamento_api
    if not pareamento_api["saudavel"]:
        validacao.setdefault("avisos", []).append(
            pareamento_api["motivo"]
        )
        validacao["requer_atencao"] = True
    # Observa a nova série temporal sem transformá-la em gate enquanto
    # permanece experimental. Uma indisponibilidade fica registrada no
    # estado e no resumo diário, mas não interrompe a coleta nem os sinais.
    validacao["historico_api_live"] = verificar_historico_api_live(
        ARQUIVO_BANCO
    )
    armazenamento = verificar_armazenamento(PASTA, ARQUIVO_BANCO)
    armazenamento = atualizar_tendencia_armazenamento(
        armazenamento,
        (anterior.get("validacao") or {}).get("armazenamento") or {},
    )
    validacao["armazenamento"] = armazenamento
    if not armazenamento["saudavel"]:
        validacao.setdefault("motivos", []).extend(
            armazenamento.get("motivos") or []
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    drill_restauracao = executar_drill_restauracao_compactada(
        PASTA / "backups",
        (anterior.get("validacao") or {}).get(
            "drill_restauracao_compactada"
        ) or {},
    )
    validacao["drill_restauracao_compactada"] = drill_restauracao
    if not drill_restauracao.get("saudavel"):
        validacao.setdefault("avisos", []).append(
            "drill_restauracao_compactada_falhou"
        )
        validacao["requer_atencao"] = True
    validacao["resumo_operacao_diaria"] = resumir_operacao_diaria(
        ARQUIVO_BANCO,
        destinos_resultado=_destinos_resumo_configurados(),
    )
    validacao["sessao_packball"] = verificar_sessao_packball(
        ARQUIVO_SESSAO_PACKBALL,
        caminho_estado_acesso=ARQUIVO_ACESSO_PACKBALL,
    )
    if validacao["sessao_packball"].get("saudavel") is not True:
        validacao.setdefault("avisos", []).append(
            "sessao_packball_requer_login"
        )
        validacao["requer_atencao"] = True
    marcar_fase("auditorias_operacionais")
    # Durante a partida a frio ainda não existe um ciclo completo que
    # contextualize cobertura, drift, marcos ou capacidade. As auditorias
    # continuam sendo calculadas e persistidas, mas nenhuma delas pode gerar
    # alerta antes de a própria coleta sair do estado de inicialização.
    enviar_validacao = (
        (lambda _texto: False)
        if tolerancia_inicial else enviar_alerta
    )
    enviar_resumo_parte = (
        (lambda _texto, _chave: False)
        if tolerancia_inicial else
        lambda texto, chave: enviar_alerta(
            texto,
            destinos=_destinos_resumo_configurados(),
            chave_evento=chave,
            deduplicacao_minutos=None,
        )
    )
    alertas_tecnicos_ativos = (
        os.getenv("TELEGRAM_ALERTAS_TECNICOS", "0") == "1"
    )
    enviar_diagnostico = (
        enviar_validacao
        if alertas_tecnicos_ativos
        else (lambda _texto: False)
    )
    destinos_operacionais = _destinos_operacionais_configurados()
    validacao["politica_telegram"] = {
        "versao": POLITICA_TELEGRAM_VERSAO,
        "alertas_tecnicos_ativos": alertas_tecnicos_ativos,
        "alertas_sombra_ativos": (
            os.getenv("ALERTAS_ANALISES_SOMBRA_TELEGRAM", "0") == "1"
        ),
        "resumo_diario_compacto": True,
        "alertas_operacionais_criticos": True,
        "destinos_operacionais": len(destinos_operacionais),
    }
    validacao_atualizada = atualizar_alerta_drift_simulacoes(
        validacao,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    historico_drift = persistir_historico_drift_simulacoes(
        validacao_atualizada, ARQUIVO_BANCO
    )
    validacao_atualizada["historico_drift_simulacoes"] = historico_drift
    if not historico_drift["saudavel"]:
        validacao_atualizada.setdefault("avisos", []).append(
            historico_drift["motivo"]
        )
        validacao_atualizada["requer_atencao"] = True
    historico_contexto = persistir_historico_avaliacao_contexto(
        validacao_atualizada, ARQUIVO_BANCO
    )
    validacao_atualizada["historico_avaliacao_contexto"] = (
        historico_contexto
    )
    if not historico_contexto["saudavel"]:
        validacao_atualizada.setdefault("avisos", []).append(
            historico_contexto["motivo"]
        )
        validacao_atualizada["requer_atencao"] = True
    persistencia_pontuacao = persistir_modelos_pontuacao_sombra(
        validacao_atualizada, ARQUIVO_BANCO
    )
    validacao_atualizada["persistencia_pontuacao_sombra"] = (
        persistencia_pontuacao
    )
    if persistencia_pontuacao.get("avaliacao"):
        validacao_atualizada["pontuacao_sombra"] = (
            persistencia_pontuacao["avaliacao"]
        )
    if not persistencia_pontuacao["saudavel"]:
        validacao_atualizada.setdefault("avisos", []).append(
            persistencia_pontuacao["motivo"]
        )
        validacao_atualizada["requer_atencao"] = True
    persistencia_pontuacao_contexto = (
        persistir_modelos_pontuacao_contexto_sombra(
            validacao_atualizada,
            ARQUIVO_BANCO,
        )
    )
    validacao_atualizada["persistencia_pontuacao_contexto_sombra"] = (
        persistencia_pontuacao_contexto
    )
    if persistencia_pontuacao_contexto.get("avaliacao"):
        validacao_atualizada["pontuacao_contexto_sombra"] = (
            persistencia_pontuacao_contexto["avaliacao"]
        )
    if not persistencia_pontuacao_contexto["saudavel"]:
        validacao_atualizada.setdefault("avisos", []).append(
            persistencia_pontuacao_contexto["motivo"]
        )
        validacao_atualizada["requer_atencao"] = True
    persistencia_pontuacao_longa = (
        persistir_estudos_pontuacao_longa_sombra(
            validacao_atualizada,
            ARQUIVO_BANCO,
        )
    )
    validacao_atualizada["persistencia_pontuacao_longa_sombra"] = (
        persistencia_pontuacao_longa
    )
    if persistencia_pontuacao_longa.get("avaliacao"):
        validacao_atualizada["pontuacao_longa_sombra"] = (
            persistencia_pontuacao_longa["avaliacao"]
        )
    if not persistencia_pontuacao_longa["saudavel"]:
        validacao_atualizada.setdefault("avisos", []).append(
            persistencia_pontuacao_longa["motivo"]
        )
        validacao_atualizada["requer_atencao"] = True
    marcar_fase("persistencias_modelos_sombra")
    validacao_atualizada = atualizar_alertas_pontuacao_contexto_sombra(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_alertas_pontuacao_longa_sombra(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    causas_validacao = set(
        validacao_atualizada.get("motivos") or []
    ) | set(validacao_atualizada.get("avisos") or [])
    causas_operacionais = MOTIVOS_VALIDACAO_CRITICOS - {
        "experimento_ritmo_packball_regressao",
    }
    integridade_telegram = (
        validacao_atualizada.get("integridade_telegram") or {}
    )
    alerta_validacao_acionavel = bool(
        causas_validacao & causas_operacionais
        or int(integridade_telegram.get("envios_incertos", 0) or 0) > 0
    )
    enviar_alerta_validacao = (
        enviar_validacao
        if alerta_validacao_acionavel
        else (lambda _texto: True)
    )
    validacao_atualizada = atualizar_alerta_validacao(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_alerta_validacao,
    )
    validacao_atualizada = atualizar_alerta_experimento_ritmo(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_alerta_experimento_filtro(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_alertas_filtros_regras_ativas(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_alerta_hipoteses_sombra(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_marcos_exploracao_gols(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = aplicar_circuit_breaker_gols_antecipados(
        validacao_atualizada,
    )
    validacao_atualizada = atualizar_alerta_circuit_breaker_gols_antecipados(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_validacao,
    )
    validacao_atualizada = aplicar_circuit_breaker_filtro_gol_ft_preciso(
        validacao_atualizada,
    )
    validacao_atualizada = (
        atualizar_alerta_circuit_breaker_filtro_gol_ft_preciso(
            validacao_atualizada,
            anterior.get("validacao") or {},
            enviar=enviar_validacao,
        )
    )
    validacao_atualizada = aplicar_circuit_breaker_escanteios_ft_asiatico(
        validacao_atualizada,
    )
    validacao_atualizada = (
        atualizar_alerta_circuit_breaker_escanteios_ft_asiatico(
            validacao_atualizada,
            anterior.get("validacao") or {},
            enviar=enviar_validacao,
        )
    )
    validacao_atualizada = aplicar_circuit_breaker_filtro_gol_ht_preciso(
        validacao_atualizada,
    )
    validacao_atualizada = (
        atualizar_alerta_circuit_breaker_filtro_gol_ht_preciso(
            validacao_atualizada,
            anterior.get("validacao") or {},
            enviar=enviar_validacao,
        )
    )
    validacao_atualizada = aplicar_circuit_breaker_proximo_gol_balanceado(
        validacao_atualizada,
    )
    validacao_atualizada = (
        atualizar_alerta_circuit_breaker_proximo_gol_balanceado(
            validacao_atualizada,
            anterior.get("validacao") or {},
            enviar=enviar_validacao,
        )
    )
    validacao_atualizada = aplicar_circuit_breaker_grupo_gol_ft_capacidade_v2(
        validacao_atualizada,
    )
    validacao_atualizada = atualizar_alerta_grupo_gol_ft_capacidade_v2(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_validacao,
    )
    validacao_atualizada = atualizar_conclusao_gol_ft_v3(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_conclusao_gol_ht_00_min20(
        validacao_atualizada,
        anterior.get("validacao") or {},
    )
    validacao_atualizada = atualizar_alerta_prontidao_historico_api_live(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_marcos_validacao(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_alertas_estado_calibracoes(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_marcos_odds_periodos(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_diagnostico,
    )
    validacao_atualizada = atualizar_alerta_cota_api(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_validacao,
    )
    validacao_atualizada = atualizar_alerta_sessao_packball(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_validacao,
    )
    if (
        validacao_atualizada.get("sessao_packball_alerta_pendente")
        and not destinos_operacionais
    ):
        validacao_atualizada[
            "sessao_packball_alerta_pendente_motivo"
        ] = "destino_operacional_ausente"
    validacao_atualizada = atualizar_alerta_risco_oficial(
        validacao_atualizada,
        anterior.get("validacao") or {},
        enviar=enviar_validacao,
    )
    marcar_fase("politicas_e_alertas")
    try:
        hora_resumo = int(os.getenv(
            "HORA_RESUMO_DIARIO", str(HORA_RESUMO_DIARIO)
        ))
    except (TypeError, ValueError):
        hora_resumo = HORA_RESUMO_DIARIO
    estado["validacao"] = atualizar_resumo_diario(
        validacao_atualizada,
        anterior.get("validacao") or {},
        estado,
        hora_envio=hora_resumo,
        enviar_parte=enviar_resumo_parte,
    )
    marcar_fase("resumo_diario")
    estado["observabilidade_watchdog"] = {
        "fases_segundos": dict(duracoes_fases),
        "duracao_total_segundos": round(
            time.monotonic() - inicio_verificacao, 3
        ),
        "estado": "concluido",
    }
    persistencia_estado = persistir_estado_watchdog_sqlite(
        ARQUIVO_BANCO, estado
    )
    estado["persistencia_estado_watchdog"] = persistencia_estado
    marcar_fase("persistencia_estado_sqlite")
    estado["observabilidade_watchdog"] = {
        "fases_segundos": dict(duracoes_fases),
        "duracao_total_segundos": round(
            time.monotonic() - inicio_verificacao, 3
        ),
        "estado": "concluido",
    }
    gravar_json_atomico(ARQUIVO_ESTADO, estado)
    return estado


def _aguardar_intervalo_interrompivel_watchdog(
    segundos, dormir, modo_manutencao_fn, passo_segundos=1.0
):
    """Divide a espera para que manutencao nao aguarde o minuto inteiro."""
    restante = max(float(segundos), 0.0)
    passo = max(float(passo_segundos), 0.1)
    while restante > 0:
        if modo_manutencao_fn():
            return True
        atual = min(passo, restante)
        dormir(atual)
        restante -= atual
    return bool(modo_manutencao_fn())


def _imprimir_estado_watchdog_seguro(estado, stream=None):
    """Registra o estado sem transformar limitações do console em falha."""
    stream = stream if stream is not None else sys.stdout
    texto = f"Watchdog: {estado}"
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        texto = texto.encode(
            encoding, errors="backslashreplace"
        ).decode(encoding)
    except LookupError:
        texto = texto.encode(
            "ascii", errors="backslashreplace"
        ).decode("ascii")
    print(texto, file=stream)


def executar_loop(
    uma_vez=False,
    intervalo_segundos=60,
    dormir=None,
    limite_ciclos=None,
    enviar=None,
    modo_manutencao_fn=None,
    supervisionar_pre_live=None,
):
    dormir = dormir or time.sleep
    enviar = enviar or enviar_alerta
    modo_manutencao_fn = modo_manutencao_fn or (
        lambda: ler_modo_manutencao(PASTA).get("ativo", False)
    )
    ciclos = 0
    falhas_consecutivas = 0
    recuperacoes = 0
    while limite_ciclos is None or ciclos < limite_ciclos:
        if modo_manutencao_fn():
            return {
                "ciclos": ciclos,
                "falhas_consecutivas": falhas_consecutivas,
                "recuperacoes": recuperacoes,
                "encerrado_por_manutencao": True,
            }
        ciclos += 1
        try:
            if supervisionar_pre_live is not None:
                supervisionar_pre_live()
            estado = executar_verificacao()
            _imprimir_estado_watchdog_seguro(estado)
            if falhas_consecutivas:
                recuperacoes += 1
                enviar(
                    "✅ Watchdog do Bot PackBall recuperado após "
                    f"{falhas_consecutivas} falha(s) interna(s)."
                )
            falhas_consecutivas = 0
        except Exception as erro:
            falhas_consecutivas += 1
            print(
                "Falha interna temporária do watchdog: "
                f"{type(erro).__name__}: {erro}"
            )
            if uma_vez:
                raise
            if falhas_consecutivas == 1 or falhas_consecutivas % 5 == 0:
                enviar(
                    "🚨 WATCHDOG PACKBALL COM FALHA INTERNA\n\n"
                    f"Erro: {type(erro).__name__}\n"
                    f"Falhas consecutivas: {falhas_consecutivas}\n"
                    "O processo continuará tentando se recuperar."
                )
        if uma_vez:
            break
        if limite_ciclos is None or ciclos < limite_ciclos:
            if _aguardar_intervalo_interrompivel_watchdog(
                intervalo_segundos,
                dormir,
                modo_manutencao_fn,
            ):
                return {
                    "ciclos": ciclos,
                    "falhas_consecutivas": falhas_consecutivas,
                    "recuperacoes": recuperacoes,
                    "encerrado_por_manutencao": True,
                }
    return {
        "ciclos": ciclos,
        "falhas_consecutivas": falhas_consecutivas,
        "recuperacoes": recuperacoes,
        "encerrado_por_manutencao": False,
    }


def reinicio_isolado_watchdog_solicitado(
    caminho=ARQUIVO_REINICIO_ISOLADO, pid=None,
):
    """Aceita somente um pedido direcionado a esta instancia exata."""
    try:
        pedido = json.loads(Path(caminho).read_text(encoding="utf-8"))
        pid_alvo = int(pedido.get("pid_alvo"))
        pid_atual = int(pid or os.getpid())
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        pedido.get("estado") == "solicitado"
        and pid_alvo == pid_atual
    )


def main():
    load_dotenv(PASTA / ".env")
    os.environ.setdefault("BACKUP_COMPACTACAO_ATIVA", "1")
    uma_vez = "--uma-vez" in sys.argv
    trava = TravaInstancia(ARQUIVO_TRAVA)
    if not trava.adquirir():
        print("Watchdog não iniciado: outra instância já está ativa.")
        return
    encerramento_limpo = False
    erro_final = None
    codigo_hash = hash_codigo_watchdog(PASTA)
    registrar_estado(
        ARQUIVO_PROCESSO_WATCHDOG, "ativo", codigo_hash=codigo_hash
    )
    try:
        encerramento_solicitado = lambda: (
            ler_modo_manutencao(PASTA).get("ativo", False)
            or reinicio_isolado_watchdog_solicitado()
        )
        executar_loop(
            uma_vez=uma_vez,
            modo_manutencao_fn=encerramento_solicitado,
            supervisionar_pre_live=(
                None
                if uma_vez
                or os.getenv("PRELIVE_AGENDADOR_ATIVO", "1") != "1"
                else lambda: garantir_pre_live_ativo(PASTA)
            ),
        )
        encerramento_limpo = True
    except KeyboardInterrupt:
        encerramento_limpo = True
    except Exception as erro:
        erro_final = type(erro).__name__
        raise
    finally:
        try:
            registrar_estado(
                ARQUIVO_PROCESSO_WATCHDOG,
                "encerrado" if encerramento_limpo else "falha",
                erro=erro_final,
                codigo_hash=codigo_hash,
            )
        finally:
            trava.liberar()


if __name__ == "__main__":
    main()
