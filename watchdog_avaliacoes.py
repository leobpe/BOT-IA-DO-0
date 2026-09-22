"""Verificacoes observacionais das coortes de avaliacao do watchdog.

Cada funcao le o arquivo de estado de uma avaliacao e devolve um resumo
sem gerar alerta, alterar sinais ou promover politica. O contrato e
fail-closed: qualquer leitura invalida vira um resultado explicito de
indisponibilidade, nunca uma aprovacao silenciosa.

Extraido de watchdog.py, que reexporta estes nomes.
"""

import json
import math
from avaliacao_acompanhamento_odd import VERSAO as VERSAO_AVALIACAO_ACOMPANHAMENTO_ODD
from avaliacao_desajuste_odds import (
    BOOKMAKER_EXECUTAVEL as BOOKMAKER_DESAJUSTE_ODDS,
    DESENVOLVIMENTO_REFERENCIA_POS_ENVIO,
    HOLDOUT_REFERENCIA_POS_ENVIO,
    MERCADOS_LIQUIDAVEIS_EDGE_SEM_VIG,
    MERCADOS_REFERENCIA_POS_ENVIO,
    MOTIVO_FALHA_EXECUCAO as MOTIVO_FALHA_EXECUCAO_DESAJUSTE,
    ORIGENS_FONTES_OBSERVACIONAIS,
    RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS,
    RESULTADOS_EDGE_SEM_VIG_DEV_MINIMOS,
    RESULTADOS_EDGE_SEM_VIG_HOLDOUT_MINIMOS,
    RESULTADOS_EDGE_SEM_VIG_MINIMOS,
    RESULTADOS_REFERENCIA_POS_ENVIO_DEV_MINIMOS,
    RESULTADOS_REFERENCIA_POS_ENVIO_HOLDOUT_MINIMOS,
    RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS,
    TAMANHO_COORTE_EDGE_SEM_VIG,
    TAMANHO_COORTE_REFERENCIA_POS_ENVIO,
    VERSAO as VERSAO_AVALIACAO_DESAJUSTE_ODDS,
    VERSAO_CONVERGENCIA_PRECO,
    VERSAO_EDGE_SEM_VIG,
    VERSAO_FONTES_OBSERVACIONAIS,
    VERSAO_LIQUIDACAO_EDGE_SEM_VIG,
    VERSAO_REFERENCIA_POS_ENVIO,
)
from avaliacao_prioridade_ligas_gols import VERSAO as VERSAO_AVALIACAO_PRIORIDADE_LIGAS_GOLS
from avaliacao_probabilidade_individual import (
    ERRO_CALIBRACAO_MAXIMO as ERRO_CALIBRACAO_PROBABILIDADE_INDIVIDUAL,
    RESULTADOS_DESENVOLVIMENTO_MINIMOS as RESULTADOS_DEV_PROBABILIDADE_INDIVIDUAL,
    RESULTADOS_HOLDOUT_MINIMOS as RESULTADOS_HOLDOUT_PROBABILIDADE_INDIVIDUAL,
    RESULTADOS_MINIMOS as RESULTADOS_PROBABILIDADE_INDIVIDUAL,
    TAMANHO_COORTE as TAMANHO_COORTE_PROBABILIDADE_INDIVIDUAL,
    VERSAO as VERSAO_AVALIACAO_PROBABILIDADE_INDIVIDUAL,
    VERSAO_MODELO as VERSAO_MODELO_PROBABILIDADE_INDIVIDUAL,
)
from avaliacao_quarentena_fallback_ht import (
    REGRA_VERSAO_ALVO as REGRA_VERSAO_QUARENTENA_FALLBACK_HT,
    STATUS_COORTE as STATUS_COORTE_QUARENTENA_FALLBACK_HT,
    VERSAO as VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT,
)
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
from datetime import datetime
from desajuste_odds import VERSAO as VERSAO_COMPARACAO_ODDS
from functools import wraps
from observabilidade import resumir_erro_seguro
from pathlib import Path


def _resposta_avaliacao_observacional(funcao):
    """Garante contrato fail-closed em toda saida, inclusive erro precoce."""
    @wraps(funcao)
    def protegida(*args, **kwargs):
        return aplicar_efeitos_desativados(funcao(*args, **kwargs))
    return protegida


def _bloqueio_custodia_avaliacao(
    dados, *, versao_compativel, idade_segundos,
    prefixo_motivo, motivo_falha, agora,
):
    """Bloqueia conclusoes quando a rodada nao terminou sob custodia."""
    if not versao_compativel:
        return None
    custodia_compativel = (
        dados.get("custodia_execucao_versao")
        == VERSAO_CUSTODIA_AVALIACAO
    )
    cronologia = auditar_cronologia_execucao(dados, agora=agora)
    efeitos = auditar_efeitos_desativados(dados)
    classificacao = classificar_execucao(
        dados.get("estado_execucao"),
        cronologia.get("idade_segundos")
        if cronologia.get("idade_segundos") is not None
        else idade_segundos,
    )
    if (
        custodia_compativel
        and cronologia["valida"]
        and efeitos["valida"]
        and classificacao == "concluida"
    ):
        return None
    if not custodia_compativel:
        estado = "estado_invalido"
        motivo = f"{prefixo_motivo}_custodia_execucao_invalida"
    elif not cronologia["valida"]:
        estado = "estado_invalido"
        motivo = f"{prefixo_motivo}_cronologia_execucao_invalida"
    elif not efeitos["valida"]:
        estado = "estado_invalido"
        motivo = f"{prefixo_motivo}_efeitos_operacionais_invalidos"
    elif classificacao == "falha":
        estado = "falha_avaliacao"
        motivo = motivo_falha
    elif classificacao == "interrompida":
        estado = "execucao_interrompida"
        motivo = f"{prefixo_motivo}_execucao_expirada"
    elif classificacao == "em_execucao":
        estado = "avaliando"
        motivo = f"{prefixo_motivo}_em_execucao"
    else:
        estado = "estado_invalido"
        motivo = f"{prefixo_motivo}_estado_execucao_invalido"
    return {
        "saudavel": False,
        "estado": estado,
        "motivo": motivo,
        "custodia_execucao_versao": dados.get(
            "custodia_execucao_versao"
        ),
        "custodia_execucao_versao_esperada": (
            VERSAO_CUSTODIA_AVALIACAO
        ),
        "custodia_execucao_compativel": custodia_compativel,
        "cronologia_execucao": cronologia,
        "efeitos_operacionais": efeitos,
        "exposicao_coleta_prospectiva": (
            dados.get("exposicao_coleta_prospectiva") or {}
        ),
        "estado_execucao": dados.get("estado_execucao"),
        "atualizado_em": dados.get("atualizado_em"),
        "iniciado_em": dados.get("iniciado_em"),
        "finalizado_em": dados.get("finalizado_em"),
        "duracao_segundos": dados.get("duracao_segundos"),
        "idade_segundos": cronologia.get("idade_segundos"),
        "limite_execucao_segundos": LIMITE_EXECUCAO_AVALIACAO_SEGUNDOS,
        "tipo_erro": dados.get("tipo_erro"),
        "erro": dados.get("erro"),
        **EFEITOS_DESATIVADOS_AVALIACAO,
    }


@_resposta_avaliacao_observacional
def verificar_avaliacao_acompanhamento_odd(caminho, *, agora=None):
    """Expõe a coorte prospectiva sem gerar alerta ou alterar sinais."""
    agora = agora or datetime.now()
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "saudavel": True,
            "estado": "aguardando_primeira_avaliacao",
            "motivo": None,
            "aplicacao_sinais": False,
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as erro:
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_acompanhamento_odd_invalida",
            "erro": resumir_erro_seguro(erro),
            "aplicacao_sinais": False,
        }
    try:
        atualizado = datetime.fromisoformat(str(dados["atualizado_em"]))
    except (KeyError, TypeError, ValueError):
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_acompanhamento_odd_sem_data",
            "aplicacao_sinais": False,
        }
    if atualizado.tzinfo is not None:
        atualizado = atualizado.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = max((agora - atualizado).total_seconds(), 0.0)
    versao = dados.get("versao")
    versao_compativel = versao == VERSAO_AVALIACAO_ACOMPANHAMENTO_ODD
    bloqueio_execucao = _bloqueio_custodia_avaliacao(
        dados,
        versao_compativel=versao_compativel,
        idade_segundos=idade,
        prefixo_motivo="avaliacao_acompanhamento_odd",
        motivo_falha="avaliacao_acompanhamento_odd_falhou",
        agora=agora,
    )
    if bloqueio_execucao is not None:
        return {
            **bloqueio_execucao,
            "versao": versao,
            "versao_esperada": VERSAO_AVALIACAO_ACOMPANHAMENTO_ODD,
            "versao_compativel": True,
            "conclusivos_prospectivos": 0,
            "jogos_distintos_prospectivos": 0,
            "atingiram_faixa": 0,
            "entradas_oficiais_convertidas": 0,
            "vantagem_espera_comprovada": False,
            "desvantagem_espera_comprovada": False,
        }
    saudavel = idade <= 3600.0 and versao_compativel
    prospectiva = dados.get("coorte_prospectiva_rapida") or {}
    return {
        "saudavel": saudavel,
        "estado": (
            "em_formacao" if saudavel
            else "metodologia_desatualizada" if not versao_compativel
            else "desatualizada"
        ),
        "motivo": (
            None if saudavel else
            "avaliacao_acompanhamento_odd_metodologia_desatualizada"
            if not versao_compativel else
            "avaliacao_acompanhamento_odd_desatualizada"
        ),
        "versao": versao,
        "versao_esperada": VERSAO_AVALIACAO_ACOMPANHAMENTO_ODD,
        "versao_compativel": versao_compativel,
        "custodia_execucao_versao": dados.get(
            "custodia_execucao_versao"
        ),
        "custodia_execucao_compativel": bool(
            versao_compativel
            and dados.get("custodia_execucao_versao")
            == VERSAO_CUSTODIA_AVALIACAO
        ),
        "cronologia_execucao": auditar_cronologia_execucao(
            dados, agora=agora
        ),
        "efeitos_operacionais": auditar_efeitos_desativados(dados),
        "exposicao_coleta_prospectiva": (
            dados.get("exposicao_coleta_prospectiva") or {}
        ),
        "estado_execucao": dados.get("estado_execucao"),
        "atualizado_em": dados.get("atualizado_em"),
        "iniciado_em": dados.get("iniciado_em"),
        "finalizado_em": dados.get("finalizado_em"),
        "duracao_segundos": dados.get("duracao_segundos"),
        "idade_segundos": round(idade, 3),
        "ancora_prospectiva_em": dados.get("ancora_prospectiva_em"),
        "estado_avaliacao": dados.get("estado"),
        "conclusivos_prospectivos": int(
            prospectiva.get("conclusivos") or 0
        ),
        "jogos_distintos_prospectivos": int(
            prospectiva.get("jogos_distintos") or 0
        ),
        "atingiram_faixa": int(
            prospectiva.get("atingiram_faixa") or 0
        ),
        "taxa_conversao_faixa": prospectiva.get(
            "taxa_conversao_faixa"
        ),
        "entradas_oficiais_convertidas": int(
            prospectiva.get("entradas_oficiais_convertidas") or 0
        ),
        "delta_roi_espera_vs_entrada_imediata": prospectiva.get(
            "delta_roi_espera_vs_entrada_imediata"
        ),
        "ic95_delta_roi": prospectiva.get(
            "ic95_bootstrap_delta_roi_estrategia"
        ),
        "roi_espera_por_aviso": prospectiva.get(
            "roi_espera_estrategia_por_aviso"
        ),
        "ic95_roi_espera_por_aviso": prospectiva.get(
            "ic95_bootstrap_roi_espera_por_aviso"
        ),
        "criterio_execucao_faixa": dados.get(
            "criterio_execucao_faixa"
        ),
        "criterio_vinculo_entrada_oficial": dados.get(
            "criterio_vinculo_entrada_oficial"
        ),
        "unidade_independente": dados.get("unidade_independente"),
        "vantagem_espera_comprovada": bool(
            versao_compativel
            and dados.get("vantagem_espera_comprovada")
        ),
        "desvantagem_espera_comprovada": bool(
            versao_compativel
            and dados.get("desvantagem_espera_comprovada")
        ),
        "promocao_automatica": False,
        "aplicacao_sinais": False,
    }


@_resposta_avaliacao_observacional
def verificar_avaliacao_prioridade_ligas_gols(caminho, *, agora=None):
    """Resume a coorte de ligas sem transformá-la em gate operacional."""
    agora = agora or datetime.now()
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "saudavel": True,
            "estado": "aguardando_primeira_avaliacao",
            "motivo": None,
            "aplicacao_sinais": False,
            "altera_prioridade": False,
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as erro:
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_prioridade_ligas_gols_invalida",
            "erro": resumir_erro_seguro(erro),
            "aplicacao_sinais": False,
            "altera_prioridade": False,
        }
    try:
        atualizado = datetime.fromisoformat(str(dados["atualizado_em"]))
    except (KeyError, TypeError, ValueError):
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_prioridade_ligas_gols_sem_data",
            "aplicacao_sinais": False,
            "altera_prioridade": False,
        }
    if atualizado.tzinfo is not None:
        atualizado = atualizado.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = max((agora - atualizado).total_seconds(), 0.0)
    versao = dados.get("versao")
    versao_compativel = (
        versao == VERSAO_AVALIACAO_PRIORIDADE_LIGAS_GOLS
    )
    bloqueio_execucao = _bloqueio_custodia_avaliacao(
        dados,
        versao_compativel=versao_compativel,
        idade_segundos=idade,
        prefixo_motivo="avaliacao_prioridade_ligas_gols",
        motivo_falha="avaliacao_prioridade_ligas_gols_falhou",
        agora=agora,
    )
    if bloqueio_execucao is not None:
        return {
            **bloqueio_execucao,
            "versao": versao,
            "versao_esperada": VERSAO_AVALIACAO_PRIORIDADE_LIGAS_GOLS,
            "versao_compativel": True,
            "ancora_metodologia_v2_pre_registrada": False,
            "decisoes": 0,
            "decisoes_brutas": 0,
            "unidades_independentes": 0,
            "vantagem_captura_comprovada": False,
            "regressao_captura_comprovada": False,
        }
    ancora_pre_registrada = (
        dados.get("ancora_metodologia_v2_pre_registrada") is True
    )
    saudavel = (
        idade <= 3600.0
        and versao_compativel
        and ancora_pre_registrada
    )
    grupos = dados.get("por_grupo") or {}
    alta = grupos.get("prioridade_maxima") or {}
    controle = grupos.get("controle_pontuado") or {}
    return {
        "saudavel": saudavel,
        "estado": (
            "em_formacao" if saudavel
            else "metodologia_desatualizada" if not versao_compativel
            else "coorte_nao_pre_registrada" if not ancora_pre_registrada
            else "desatualizada"
        ),
        "motivo": (
            None if saudavel else
            "avaliacao_prioridade_ligas_gols_metodologia_desatualizada"
            if not versao_compativel else
            "avaliacao_prioridade_ligas_gols_coorte_nao_pre_registrada"
            if not ancora_pre_registrada else
            "avaliacao_prioridade_ligas_gols_desatualizada"
        ),
        "versao": versao,
        "versao_esperada": VERSAO_AVALIACAO_PRIORIDADE_LIGAS_GOLS,
        "versao_compativel": versao_compativel,
        "custodia_execucao_versao": dados.get(
            "custodia_execucao_versao"
        ),
        "custodia_execucao_compativel": bool(
            versao_compativel
            and dados.get("custodia_execucao_versao")
            == VERSAO_CUSTODIA_AVALIACAO
        ),
        "cronologia_execucao": auditar_cronologia_execucao(
            dados, agora=agora
        ),
        "efeitos_operacionais": auditar_efeitos_desativados(dados),
        "exposicao_coleta_prospectiva": (
            dados.get("exposicao_coleta_prospectiva") or {}
        ),
        "estado_execucao": dados.get("estado_execucao"),
        "ancora_metodologia_v2_pre_registrada": ancora_pre_registrada,
        "atualizado_em": dados.get("atualizado_em"),
        "iniciado_em": dados.get("iniciado_em"),
        "finalizado_em": dados.get("finalizado_em"),
        "duracao_segundos": dados.get("duracao_segundos"),
        "idade_segundos": round(idade, 3),
        "ancora_prospectiva_em": dados.get("ancora_prospectiva_em"),
        "decisoes": int(dados.get("decisoes") or 0),
        "decisoes_brutas": int(dados.get("decisoes_brutas") or 0),
        "unidades_independentes": int(
            dados.get("unidades_independentes") or 0
        ),
        "ciclos": int(dados.get("ciclos") or 0),
        "processadas_prioridade": int(alta.get("processadas") or 0),
        "processadas_controle": int(controle.get("processadas") or 0),
        "jogos_prioridade": int(alta.get("jogos_distintos") or 0),
        "jogos_controle": int(controle.get("jogos_distintos") or 0),
        "oportunidades_prioridade": int(
            alta.get("jogos_com_oportunidade_gol") or 0
        ),
        "oportunidades_controle": int(
            controle.get("jogos_com_oportunidade_gol") or 0
        ),
        "taxa_captura_prioridade": alta.get(
            "taxa_captura_oportunidade_por_jogo_exposto"
        ),
        "taxa_captura_controle": controle.get(
            "taxa_captura_oportunidade_por_jogo_exposto"
        ),
        "resultados_acionaveis_prioridade": int(
            alta.get("resultados_gol") or 0
        ),
        "resultados_acionaveis_controle": int(
            controle.get("resultados_gol") or 0
        ),
        "delta_rendimento_oportunidade_por_detalhe": dados.get(
            "delta_taxa_captura_por_jogo_exposto"
            if "delta_taxa_captura_por_jogo_exposto" in dados
            else "delta_rendimento_oportunidade_por_detalhe"
        ),
        "ic95_delta_rendimento_oportunidade": dados.get(
            "ic95_delta_taxa_captura_por_jogo_exposto"
            if "ic95_delta_taxa_captura_por_jogo_exposto" in dados
            else "ic95_delta_rendimento_oportunidade"
        ),
        "vantagem_captura_comprovada": bool(
            versao_compativel
            and ancora_pre_registrada
            and dados.get("vantagem_captura_comprovada")
        ),
        "regressao_captura_comprovada": bool(
            versao_compativel
            and ancora_pre_registrada
            and dados.get("regressao_captura_comprovada")
        ),
        "promocao_automatica": False,
        "aplicacao_sinais": False,
        "altera_prioridade": False,
    }


@_resposta_avaliacao_observacional
def verificar_avaliacao_probabilidade_individual(caminho, *, agora=None):
    """Valida custódia e contagens sem promover a previsão individual."""
    agora = agora or datetime.now()
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "saudavel": True,
            "estado": "aguardando_primeira_avaliacao",
            "motivo": None,
            "bloqueia_inferencia": False,
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as erro:
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_probabilidade_individual_invalida",
            "erro": resumir_erro_seguro(erro),
            "bloqueia_inferencia": True,
        }
    try:
        atualizado = datetime.fromisoformat(str(dados["atualizado_em"]))
    except (KeyError, TypeError, ValueError):
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_probabilidade_individual_sem_data",
            "bloqueia_inferencia": True,
        }
    if atualizado.tzinfo is not None:
        atualizado = atualizado.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = max((agora - atualizado).total_seconds(), 0.0)
    versao = dados.get("versao")
    versao_compativel = (
        versao == VERSAO_AVALIACAO_PROBABILIDADE_INDIVIDUAL
    )
    bloqueio = _bloqueio_custodia_avaliacao(
        dados,
        versao_compativel=versao_compativel,
        idade_segundos=idade,
        prefixo_motivo="avaliacao_probabilidade_individual",
        motivo_falha="avaliacao_probabilidade_individual_falhou",
        agora=agora,
    )
    if bloqueio is not None:
        return {
            **bloqueio,
            "versao": versao,
            "versao_esperada": VERSAO_AVALIACAO_PROBABILIDADE_INDIVIDUAL,
            "mercados": {},
            "bloqueia_inferencia": True,
        }

    problemas = []

    def inteiro_nao_negativo(valor):
        if isinstance(valor, bool):
            return None
        try:
            inteiro = int(valor)
        except (TypeError, ValueError, OverflowError):
            return None
        return inteiro if inteiro >= 0 and valor == inteiro else None

    mercados_entrada = dados.get("mercados")
    if not isinstance(mercados_entrada, dict) or set(mercados_entrada) != {
        "gol_ht", "gol_ft",
    }:
        mercados_entrada = {}
        problemas.append("mercados_invalidos")
    mercados = {}
    for mercado in ("gol_ht", "gol_ft"):
        item = mercados_entrada.get(mercado)
        if not isinstance(item, dict):
            problemas.append(f"{mercado}_invalido")
            continue
        retro = item.get("validacao_retro")
        coorte = item.get("coorte_prospectiva")
        if (
            not isinstance(retro, dict)
            or retro.get("versao")
            != VERSAO_MODELO_PROBABILIDADE_INDIVIDUAL
        ):
            problemas.append(f"{mercado}_validacao_retro_invalida")
            retro = {}
        if not isinstance(coorte, dict):
            problemas.append(f"{mercado}_coorte_invalida")
            coorte = {}

        amostra_bruta = inteiro_nao_negativo(
            item.get("amostra_retro_bruta")
        )
        amostra_referenciada = inteiro_nao_negativo(
            item.get("amostra_retro")
        )
        auditoria_referencia = item.get(
            "auditoria_referencia_sem_vig"
        )
        if not isinstance(auditoria_referencia, dict):
            problemas.append(f"{mercado}_referencia_sem_vig_invalida")
            auditoria_referencia = {}
        total_referencia = inteiro_nao_negativo(
            auditoria_referencia.get("total")
        )
        com_referencia = inteiro_nao_negativo(
            auditoria_referencia.get("com_referencia_sem_vig")
        )
        sem_referencia = inteiro_nao_negativo(
            auditoria_referencia.get("sem_referencia_sem_vig")
        )
        taxa_referencia = auditoria_referencia.get("taxa_cobertura")
        try:
            taxa_referencia = (
                None if taxa_referencia is None
                else float(taxa_referencia)
            )
        except (TypeError, ValueError, OverflowError):
            taxa_referencia = None
        contagens_referencia_validas = bool(
            amostra_bruta is not None
            and amostra_referenciada is not None
            and total_referencia == amostra_bruta
            and com_referencia == amostra_referenciada
            and sem_referencia == amostra_bruta - amostra_referenciada
            and (
                (amostra_bruta == 0 and taxa_referencia is None)
                or (
                    amostra_bruta > 0
                    and taxa_referencia is not None
                    and math.isfinite(taxa_referencia)
                    and math.isclose(
                        taxa_referencia,
                        amostra_referenciada / amostra_bruta,
                        abs_tol=1e-9,
                    )
                )
            )
            and auditoria_referencia.get("referencia")
            == "over_under_mesmo_snapshot_sem_vig"
            and auditoria_referencia.get("consulta_resultado") is False
            and auditoria_referencia.get("aplicacao_sinais") is False
            and auditoria_referencia.get("telegram") is False
        )
        if not contagens_referencia_validas:
            problemas.append(
                f"{mercado}_referencia_sem_vig_incoerente"
            )
        cobertura_suficiente = (
            auditoria_referencia.get("cobertura_suficiente") is True
        )
        if (
            retro.get("aprovado_para_coorte_prospectiva") is True
            and not cobertura_suficiente
        ):
            problemas.append(
                f"{mercado}_modelo_aprovado_sem_cobertura_sem_vig"
            )

        numeros = {}
        for chave in (
            "candidatos", "resultados", "pendentes",
            "faltam_candidatos", "faltam_resultados",
        ):
            inteiro = inteiro_nao_negativo(coorte.get(chave))
            if inteiro is None:
                problemas.append(f"{mercado}_{chave}_invalido")
                continue
            numeros[chave] = inteiro
        candidatos = numeros.get("candidatos", 0)
        resultados = numeros.get("resultados", 0)
        pendentes = numeros.get("pendentes", 0)
        if (
            candidatos > TAMANHO_COORTE_PROBABILIDADE_INDIVIDUAL
            or resultados > candidatos
            or pendentes != candidatos - resultados
            or numeros.get("faltam_candidatos")
            != max(TAMANHO_COORTE_PROBABILIDADE_INDIVIDUAL - candidatos, 0)
            or numeros.get("faltam_resultados")
            != max(RESULTADOS_PROBABILIDADE_INDIVIDUAL - resultados, 0)
        ):
            problemas.append(f"{mercado}_contagens_incoerentes")

        definicao_presente = item.get("definicao_presente") is True
        definicao_valida = item.get("definicao_valida") is True
        if definicao_presente and not definicao_valida:
            problemas.append(f"{mercado}_definicao_integra_invalida")
        if not definicao_presente and candidatos:
            problemas.append(f"{mercado}_predicao_sem_definicao")
        predicoes_invalidas = inteiro_nao_negativo(
            item.get("predicoes_invalidas")
        )
        if predicoes_invalidas is None:
            problemas.append(f"{mercado}_predicoes_invalidas_invalido")
        elif predicoes_invalidas != 0:
            problemas.append(f"{mercado}_predicoes_invalidas")

        vantagem = coorte.get("vantagem_preditiva_prospectiva") is True
        pronta = coorte.get("pronta_para_revisao") is True
        total = coorte.get("total") or {}
        dev = coorte.get("desenvolvimento") or {}
        holdout = coorte.get("holdout") or {}
        if pronta:
            n_total = inteiro_nao_negativo(total.get("n"))
            n_dev = inteiro_nao_negativo(dev.get("n"))
            n_holdout = inteiro_nao_negativo(holdout.get("n"))
            if not (
                n_total is not None
                and n_total >= RESULTADOS_PROBABILIDADE_INDIVIDUAL
                and n_dev is not None
                and n_dev >= RESULTADOS_DEV_PROBABILIDADE_INDIVIDUAL
                and n_holdout is not None
                and n_holdout >= RESULTADOS_HOLDOUT_PROBABILIDADE_INDIVIDUAL
            ):
                problemas.append(f"{mercado}_revisao_prematura")
        if vantagem:
            valores = (
                total.get("delta_brier_vs_mercado_sem_vig"),
                dev.get("delta_brier_vs_mercado_sem_vig"),
                holdout.get("delta_brier_vs_mercado_sem_vig"),
                total.get("erro_calibracao"),
            )
            try:
                delta_total, delta_dev, delta_holdout, ece = map(
                    float, valores
                )
            except (TypeError, ValueError):
                problemas.append(f"{mercado}_vantagem_sem_metricas")
            else:
                if (
                    not pronta
                    or not all(math.isfinite(valor) for valor in (
                        delta_total, delta_dev, delta_holdout, ece
                    ))
                    or delta_total > -0.002
                    or delta_dev > 0
                    or delta_holdout > 0
                    or ece > ERRO_CALIBRACAO_PROBABILIDADE_INDIVIDUAL
                ):
                    problemas.append(f"{mercado}_vantagem_nao_comprovada")
        mercados[mercado] = {
            "estado": item.get("estado"),
            "amostra_retro_bruta": amostra_bruta or 0,
            "amostra_retro": amostra_referenciada or 0,
            "referencia_sem_vig": {
                "com_referencia": com_referencia or 0,
                "sem_referencia": sem_referencia or 0,
                "taxa_cobertura": taxa_referencia,
                "cobertura_suficiente": cobertura_suficiente,
                "margem_bookmaker_media": (
                    auditoria_referencia.get("margem_bookmaker_media")
                ),
            },
            "validacao_retro_estado": retro.get("estado"),
            "validacao_retro_aprovada": bool(
                retro.get("aprovado_para_coorte_prospectiva")
            ),
            "definicao_presente": definicao_presente,
            "definicao_valida": definicao_valida,
            "candidatos": candidatos,
            "resultados": resultados,
            "pendentes": pendentes,
            "pronta_para_revisao": pronta,
            "vantagem_preditiva_prospectiva": vantagem,
            "brier": total.get("brier"),
            "brier_mercado_sem_vig": total.get(
                "brier_mercado_sem_vig"
            ),
            "delta_brier_vs_mercado_sem_vig": total.get(
                "delta_brier_vs_mercado_sem_vig"
            ),
            "erro_calibracao": total.get("erro_calibracao"),
        }
    if dados.get("integridade") is not True:
        problemas.append("integridade_declarada_invalida")
    if idade > 3600:
        problemas.append("avaliacao_desatualizada")
    if not versao_compativel:
        problemas.append("metodologia_desatualizada")
    problemas = sorted(set(problemas))
    return {
        "saudavel": not problemas,
        "estado": "em_formacao" if not problemas else "estado_invalido",
        "motivo": (
            None if not problemas
            else "avaliacao_probabilidade_individual_invalida"
        ),
        "problemas": problemas,
        "versao": versao,
        "versao_esperada": VERSAO_AVALIACAO_PROBABILIDADE_INDIVIDUAL,
        "versao_compativel": versao_compativel,
        "atualizado_em": dados.get("atualizado_em"),
        "idade_segundos": round(idade, 3),
        "mercados": mercados,
        "bloqueia_inferencia": bool(problemas),
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "promocao_automatica": False,
        "telegram": False,
    }


@_resposta_avaliacao_observacional
def verificar_avaliacao_desajuste_odds(caminho, *, agora=None):
    """Expõe a coorte de preço sem transformá-la em gate operacional."""
    agora = agora or datetime.now()
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "saudavel": True,
            "estado": "aguardando_primeira_avaliacao",
            "motivo": None,
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as erro:
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_desajuste_odds_invalida",
            "erro": resumir_erro_seguro(erro),
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }
    try:
        atualizado = datetime.fromisoformat(str(dados["atualizado_em"]))
    except (KeyError, TypeError, ValueError):
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_desajuste_odds_sem_data",
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }
    if atualizado.tzinfo is not None:
        atualizado = atualizado.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = max((agora - atualizado).total_seconds(), 0.0)
    versao = dados.get("versao")
    versao_compativel = versao == VERSAO_AVALIACAO_DESAJUSTE_ODDS
    estado_execucao = dados.get("estado_execucao")
    bloqueio_execucao = _bloqueio_custodia_avaliacao(
        dados,
        versao_compativel=versao_compativel,
        idade_segundos=idade,
        prefixo_motivo="avaliacao_desajuste_odds",
        motivo_falha=MOTIVO_FALHA_EXECUCAO_DESAJUSTE,
        agora=agora,
    )
    if bloqueio_execucao is not None:
        return {
            **bloqueio_execucao,
            "versao": versao,
            "versao_esperada": VERSAO_AVALIACAO_DESAJUSTE_ODDS,
            "versao_compativel": True,
            "pronto_para_revisao": False,
            "persistencia_comprovada": False,
            "integridade_comparacoes_odds": {
                "saudavel": False,
                "estado": "nao_auditada",
                "bloqueia_inferencia": True,
            },
            "corroboracao_entrada_rapida": {
                "pronta_para_analise": False,
                "aplicacao_sinais": False,
                "promocao_automatica": False,
                "telegram": False,
            },
            "recorte_executavel": {},
            "recorte_observacional_executavel": {},
            "recorte_convergencia_preco_prospectivo": {},
            "recorte_convergencia_escanteios_prospectivo": {},
            "recorte_edge_sem_vig_multifonte": {},
            "recorte_referencia_pos_envio": {},
            "aplicacao_sinais": False,
            "promocao_automatica": False,
            "altera_prioridade": False,
            "telegram": False,
        }
    corroboracao = dados.get("corroboracao_entrada_rapida")
    try:
        contagens_corroboracao = [
            int(corroboracao.get(chave))
            for chave in (
                "comparacoes",
                "fotografias_independentes",
                "jogos_distintos",
                "faltam_fotografias",
                "faltam_jogos",
            )
        ]
        corroboracao_valida = bool(
            isinstance(corroboracao, dict)
            and corroboracao.get("marcador")
            == "corroboracao_odd_entrada_rapida"
            and all(valor >= 0 for valor in contagens_corroboracao)
            and corroboracao.get("aplicacao_sinais") is False
            and corroboracao.get("promocao_automatica") is False
        )
    except (AttributeError, TypeError, ValueError):
        corroboracao_valida = False
        corroboracao = {}
    integridade = dados.get("integridade_comparacoes_odds")
    try:
        persistidas_integridade = int(
            integridade.get("comparacoes_persistidas")
        )
        auditadas_integridade = int(
            integridade.get("comparacoes_auditadas")
        )
        validas_integridade = int(
            integridade.get("comparacoes_validas")
        )
        invalidas_integridade = int(
            integridade.get("comparacoes_invalidas")
        )
        fingerprint_integridade = str(
            integridade.get("fingerprint_evidencias") or ""
        ).casefold()
        integridade_contrato_valida = bool(
            isinstance(integridade, dict)
            and integridade.get("versao")
            == "integridade-comparacoes-odds-multifonte-v1"
            and integridade.get("versao_comparacao")
            == VERSAO_COMPARACAO_ODDS
            and min(
                persistidas_integridade,
                auditadas_integridade,
                validas_integridade,
                invalidas_integridade,
            ) >= 0
            and auditadas_integridade
            == validas_integridade + invalidas_integridade
            and len(fingerprint_integridade) == 64
            and all(
                caractere in "0123456789abcdef"
                for caractere in fingerprint_integridade
            )
            and integridade.get("bloqueia_inferencia")
            is (not bool(integridade.get("saudavel")))
        )
    except (AttributeError, TypeError, ValueError):
        integridade_contrato_valida = False
        persistidas_integridade = 0
        auditadas_integridade = 0
        validas_integridade = 0
        invalidas_integridade = 0
        fingerprint_integridade = ""
        integridade = {}
    integridade_saudavel = bool(
        integridade_contrato_valida
        and integridade.get("saudavel") is True
        and integridade.get("auditoria_truncada") is False
        and invalidas_integridade == 0
        and persistidas_integridade == auditadas_integridade
    )
    executavel = dados.get("recorte_executavel_prospectivo") or {}
    observacional = dados.get("recorte_observacional_executavel") or {}
    convergencia = dados.get(
        "recorte_convergencia_preco_prospectivo"
    ) or {}
    convergencia_escanteios = dados.get(
        "recorte_convergencia_escanteios_prospectivo"
    ) or {}
    edge_sem_vig = dados.get("recorte_edge_sem_vig_multifonte") or {}
    referencia_pos_envio = (
        dados.get("recorte_referencia_pos_envio") or {}
    )

    def auditar_liquidacao_edge_sem_vig(liquidacao):
        problemas = []
        if not isinstance(liquidacao, dict):
            liquidacao = {}
            problemas.append("bloco_ausente")

        def inteiro_nao_negativo(objeto, campo, prefixo):
            valor = objeto.get(campo)
            if (
                not isinstance(valor, int)
                or isinstance(valor, bool)
                or valor < 0
            ):
                problemas.append(f"{prefixo}_{campo}_invalido")
                return 0
            return valor

        fingerprint = str(
            liquidacao.get("definicao_sha256") or ""
        ).casefold()
        if (
            len(fingerprint) != 64
            or not all(
                caractere in "0123456789abcdef"
                for caractere in fingerprint
            )
        ):
            problemas.append("definicao_sha256_invalida")
            fingerprint = ""
        if liquidacao.get("versao") != VERSAO_LIQUIDACAO_EDGE_SEM_VIG:
            problemas.append("versao_divergente")
        try:
            datetime.fromisoformat(str(liquidacao["registrado_em"]))
        except (KeyError, TypeError, ValueError):
            problemas.append("registrado_em_invalido")
        if liquidacao.get("linhas") != "somente_meias_linhas_sem_push":
            problemas.append("politica_linhas_divergente")
        for campo in (
            "aplicacao_sinais", "telegram", "promocao_automatica",
        ):
            if liquidacao.get(campo) is not False:
                problemas.append(f"{campo}_indevidamente_ativo")
        if liquidacao.get("vantagem_executavel_comprovada") is not False:
            problemas.append("vantagem_executavel_prematura")

        por_mercado = liquidacao.get("por_mercado")
        if not isinstance(por_mercado, dict):
            problemas.append("por_mercado_ausente")
            por_mercado = {}
        mercados_esperados = {
            f"{categoria}:{periodo}": (categoria, periodo)
            for categoria, periodo in MERCADOS_LIQUIDAVEIS_EDGE_SEM_VIG
        }
        if set(por_mercado) != set(mercados_esperados):
            problemas.append("mercados_divergentes")

        mercados_limpos = {}
        for chave, (categoria, periodo) in sorted(
            mercados_esperados.items()
        ):
            item = por_mercado.get(chave)
            if not isinstance(item, dict):
                problemas.append(f"{chave}_ausente")
                item = {}
            if item.get("categoria") != categoria:
                problemas.append(f"{chave}_categoria_divergente")
            if item.get("periodo") != periodo:
                problemas.append(f"{chave}_periodo_divergente")
            contagens = {
                campo: inteiro_nao_negativo(item, campo, chave)
                for campo in (
                    "candidatos_brutos", "candidatos_independentes",
                    "coorte", "jogos", "faltam_coorte",
                )
            }
            if not (
                contagens["coorte"]
                <= contagens["candidatos_independentes"]
                <= contagens["candidatos_brutos"]
            ):
                problemas.append(f"{chave}_contagens_inconsistentes")
            if contagens["coorte"] > TAMANHO_COORTE_EDGE_SEM_VIG:
                problemas.append(f"{chave}_coorte_excede_limite")
            if contagens["faltam_coorte"] != max(
                TAMANHO_COORTE_EDGE_SEM_VIG - contagens["coorte"], 0
            ):
                problemas.append(f"{chave}_faltam_coorte_divergente")

            recortes_limpos = {}
            for nome_recorte in ("total", "desenvolvimento", "holdout"):
                recorte = item.get(nome_recorte)
                if not isinstance(recorte, dict):
                    problemas.append(f"{chave}_{nome_recorte}_ausente")
                    recorte = {}
                numeros = {
                    campo: inteiro_nao_negativo(
                        recorte, campo, f"{chave}_{nome_recorte}"
                    )
                    for campo in (
                        "resultados", "pendentes", "cronologia_invalida",
                        "greens", "reds",
                    )
                }
                if numeros["greens"] + numeros["reds"] != (
                    numeros["resultados"]
                ):
                    problemas.append(
                        f"{chave}_{nome_recorte}_desfechos_inconsistentes"
                    )
                posterior = recorte.get("resultado_posterior_selecao") is True
                if posterior != (numeros["cronologia_invalida"] == 0):
                    problemas.append(
                        f"{chave}_{nome_recorte}_cronologia_inconsistente"
                    )
                recortes_limpos[nome_recorte] = {
                    **numeros,
                    "taxa_green": recorte.get("taxa_green"),
                    "ic95_taxa_green": recorte.get("ic95_taxa_green"),
                    "odd_media": recorte.get("odd_media"),
                    "probabilidade_controle_sem_vig_media": recorte.get(
                        "probabilidade_controle_sem_vig_media"
                    ),
                    "ev_previsto_medio": recorte.get("ev_previsto_medio"),
                    "retorno_unidades": recorte.get("retorno_unidades"),
                    "roi_real": recorte.get("roi_real"),
                    "ic95_roi_real": recorte.get("ic95_roi_real"),
                    "vies_calibracao": recorte.get("vies_calibracao"),
                    "brier_score": recorte.get("brier_score"),
                    "resultado_posterior_selecao": posterior,
                }
            total = recortes_limpos["total"]
            desenvolvimento = recortes_limpos["desenvolvimento"]
            holdout = recortes_limpos["holdout"]
            if total["resultados"] + total["pendentes"] != contagens["coorte"]:
                problemas.append(f"{chave}_liquidacao_total_inconsistente")
            if (
                desenvolvimento["resultados"] + desenvolvimento["pendentes"]
                + holdout["resultados"] + holdout["pendentes"]
                != contagens["coorte"]
            ):
                problemas.append(f"{chave}_particao_liquidacao_inconsistente")
            evidencia = item.get("evidencia_completa") is True
            requisitos_evidencia = bool(
                contagens["coorte"] >= TAMANHO_COORTE_EDGE_SEM_VIG
                and total["resultados"] >= RESULTADOS_EDGE_SEM_VIG_MINIMOS
                and desenvolvimento["resultados"]
                >= RESULTADOS_EDGE_SEM_VIG_DEV_MINIMOS
                and holdout["resultados"]
                >= RESULTADOS_EDGE_SEM_VIG_HOLDOUT_MINIMOS
                and total["resultado_posterior_selecao"]
                and desenvolvimento["resultado_posterior_selecao"]
                and holdout["resultado_posterior_selecao"]
            )
            if evidencia and not requisitos_evidencia:
                problemas.append(f"{chave}_evidencia_prematura")
            vantagem = item.get("vantagem_resultados_comprovada") is True
            if vantagem and not evidencia:
                problemas.append(f"{chave}_vantagem_prematura")
            mercados_limpos[chave] = {
                "categoria": categoria,
                "periodo": periodo,
                **contagens,
                **recortes_limpos,
                "evidencia_completa": evidencia,
                "vantagem_resultados_comprovada": vantagem,
                "decisao": item.get("decisao"),
            }

        contagens_topo = {
            campo: inteiro_nao_negativo(liquidacao, campo, "total")
            for campo in (
                "candidatos_liquidaveis", "resultados", "pendentes",
            )
        }
        if contagens_topo["candidatos_liquidaveis"] != sum(
            item["coorte"] for item in mercados_limpos.values()
        ):
            problemas.append("candidatos_liquidaveis_divergentes")
        if contagens_topo["resultados"] != sum(
            item["total"]["resultados"] for item in mercados_limpos.values()
        ):
            problemas.append("resultados_divergentes")
        if contagens_topo["pendentes"] != sum(
            item["total"]["pendentes"] for item in mercados_limpos.values()
        ):
            problemas.append("pendentes_divergentes")
        mercados_vantagem = sorted(
            chave for chave, item in mercados_limpos.items()
            if item["vantagem_resultados_comprovada"]
        )
        if liquidacao.get("mercados_com_vantagem_comprovada") != mercados_vantagem:
            problemas.append("mercados_com_vantagem_divergentes")
        saudavel_liquidacao = not problemas
        if not saudavel_liquidacao:
            for item in mercados_limpos.values():
                item["evidencia_completa"] = False
                item["vantagem_resultados_comprovada"] = False
        return {
            "saudavel": saudavel_liquidacao,
            "problemas": sorted(set(problemas)),
            "versao": liquidacao.get("versao"),
            "definicao_sha256": fingerprint,
            "registrado_em": liquidacao.get("registrado_em"),
            "linhas": liquidacao.get("linhas"),
            **contagens_topo,
            "por_mercado": mercados_limpos,
            "exclusoes": liquidacao.get("exclusoes") or {},
            "mercados_com_vantagem_comprovada": (
                mercados_vantagem if saudavel_liquidacao else []
            ),
            "vantagem_executavel_comprovada": False,
            "bloqueia_inferencia": not saudavel_liquidacao,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }

    def auditar_edge_sem_vig_multifonte(recorte):
        problemas = []
        if not isinstance(recorte, dict):
            recorte = {}
            problemas.append("recorte_ausente")
        contagens = {}
        for campo in (
            "linhas_elegiveis",
            "fotografias_completas",
            "candidatos_brutos",
            "candidatos_independentes",
            "coorte",
            "jogos",
            "desenvolvimento",
            "holdout",
            "faltam_coorte",
            "faltam_revisao",
            "faltam_jogos_revisao",
        ):
            valor = recorte.get(campo)
            if (
                not isinstance(valor, int)
                or isinstance(valor, bool)
                or valor < 0
            ):
                problemas.append(f"{campo}_invalido")
                valor = 0
            contagens[campo] = valor
        fingerprint = str(
            recorte.get("definicao_sha256") or ""
        ).casefold()
        if (
            len(fingerprint) != 64
            or not all(
                caractere in "0123456789abcdef"
                for caractere in fingerprint
            )
        ):
            problemas.append("definicao_sha256_invalida")
            fingerprint = ""
        if recorte.get("versao") != VERSAO_EDGE_SEM_VIG:
            problemas.append("versao_divergente")
        if str(
            recorte.get("bookmaker_executavel") or ""
        ).strip().casefold() != BOOKMAKER_DESAJUSTE_ODDS:
            problemas.append("bookmaker_executavel_divergente")
        if recorte.get("selecao_antes_resultado") is not True:
            problemas.append("selecao_prospectiva_nao_comprovada")
        for campo in (
            "aplicacao_sinais", "telegram", "promocao_automatica",
        ):
            if recorte.get(campo) is not False:
                problemas.append(f"{campo}_indevidamente_ativo")
        if recorte.get("vantagem_executavel_comprovada") is not False:
            problemas.append("vantagem_prematura")
        if not (
            contagens["coorte"]
            <= contagens["candidatos_independentes"]
            <= contagens["candidatos_brutos"]
            <= contagens["fotografias_completas"]
            <= contagens["linhas_elegiveis"]
        ):
            problemas.append("contagens_inconsistentes")
        if contagens["desenvolvimento"] + contagens["holdout"] != (
            contagens["coorte"]
        ):
            problemas.append("particao_coorte_inconsistente")
        liquidacao = auditar_liquidacao_edge_sem_vig(
            recorte.get("liquidacao_resultados")
        )
        problemas.extend(
            f"liquidacao_{problema}"
            for problema in liquidacao["problemas"]
        )
        return {
            "saudavel": not problemas,
            "problemas": sorted(set(problemas)),
            "definicao_sha256": fingerprint,
            "liquidacao_resultados": liquidacao,
            **contagens,
        }

    auditoria_edge_sem_vig = auditar_edge_sem_vig_multifonte(
        edge_sem_vig
    )

    def auditar_referencia_pos_envio(recorte):
        problemas = []
        if not isinstance(recorte, dict):
            recorte = {}
            problemas.append("recorte_ausente")

        def inteiro(objeto, campo, prefixo):
            valor = objeto.get(campo)
            if (
                not isinstance(valor, int)
                or isinstance(valor, bool)
                or valor < 0
            ):
                problemas.append(f"{prefixo}_{campo}_invalido")
                return 0
            return valor

        if recorte.get("versao") != VERSAO_REFERENCIA_POS_ENVIO:
            problemas.append("versao_divergente")
        fingerprint = str(
            recorte.get("definicao_sha256") or ""
        ).casefold()
        if (
            len(fingerprint) != 64
            or not all(item in "0123456789abcdef" for item in fingerprint)
        ):
            problemas.append("definicao_sha256_invalida")
            fingerprint = ""
        try:
            datetime.fromisoformat(str(recorte["ancora_pre_registrada_em"]))
        except (KeyError, TypeError, ValueError):
            problemas.append("ancora_invalida")
        for campo in (
            "aplicacao_sinais", "altera_calibracao", "altera_prioridade",
            "telegram", "promocao_automatica",
        ):
            if recorte.get(campo) is not False:
                problemas.append(f"{campo}_indevidamente_ativo")
        if recorte.get("selecao_antes_resultado") is not True:
            problemas.append("selecao_prospectiva_nao_comprovada")
        topo = {
            campo: inteiro(recorte, campo, "topo")
            for campo in (
                "auditorias_pos_envio", "fotografias_elegiveis",
                "fotografias_independentes",
            )
        }
        if not (
            topo["fotografias_independentes"]
            <= topo["fotografias_elegiveis"]
            <= topo["auditorias_pos_envio"]
        ):
            problemas.append("contagens_topo_inconsistentes")
        por_mercado = recorte.get("por_mercado")
        if not isinstance(por_mercado, dict):
            por_mercado = {}
            problemas.append("por_mercado_ausente")
        if set(por_mercado) != set(MERCADOS_REFERENCIA_POS_ENVIO):
            problemas.append("mercados_divergentes")
        mercados_limpos = {}
        vantagens = []
        for mercado in MERCADOS_REFERENCIA_POS_ENVIO:
            item = por_mercado.get(mercado)
            if not isinstance(item, dict):
                item = {}
                problemas.append(f"{mercado}_ausente")
            contagens = {
                campo: inteiro(item, campo, mercado)
                for campo in (
                    "fotografias_independentes", "candidatos_edge",
                    "sem_edge", "coorte_edge", "coorte_controle",
                    "desenvolvimento", "holdout", "faltam_coorte_edge",
                    "faltam_resultados_edge",
                    "faltam_resultados_controle",
                )
            }
            if contagens["candidatos_edge"] + contagens["sem_edge"] != (
                contagens["fotografias_independentes"]
            ):
                problemas.append(f"{mercado}_particao_edge_inconsistente")
            if not (
                contagens["coorte_edge"]
                <= contagens["candidatos_edge"]
                <= contagens["fotografias_independentes"]
            ):
                problemas.append(f"{mercado}_coorte_edge_inconsistente")
            if not (
                contagens["coorte_controle"]
                <= contagens["sem_edge"]
                <= contagens["fotografias_independentes"]
            ):
                problemas.append(f"{mercado}_controle_inconsistente")
            if contagens["coorte_edge"] > TAMANHO_COORTE_REFERENCIA_POS_ENVIO:
                problemas.append(f"{mercado}_coorte_edge_excede_limite")
            if contagens["coorte_controle"] > (
                TAMANHO_COORTE_REFERENCIA_POS_ENVIO
            ):
                problemas.append(f"{mercado}_controle_excede_limite")
            if contagens["desenvolvimento"] + contagens["holdout"] != (
                contagens["coorte_edge"]
            ):
                problemas.append(f"{mercado}_particao_coorte_inconsistente")
            if contagens["desenvolvimento"] > (
                DESENVOLVIMENTO_REFERENCIA_POS_ENVIO
            ):
                problemas.append(f"{mercado}_desenvolvimento_excede_limite")
            if contagens["holdout"] > HOLDOUT_REFERENCIA_POS_ENVIO:
                problemas.append(f"{mercado}_holdout_excede_limite")
            if contagens["faltam_coorte_edge"] != max(
                TAMANHO_COORTE_REFERENCIA_POS_ENVIO
                - contagens["coorte_edge"], 0
            ):
                problemas.append(f"{mercado}_faltam_coorte_divergente")

            resumos = {}
            tamanhos = {
                "total": contagens["coorte_edge"],
                "desenvolvimento_resultados": contagens["desenvolvimento"],
                "holdout_resultados": contagens["holdout"],
                "controle_sem_edge": contagens["coorte_controle"],
            }
            for nome, tamanho in tamanhos.items():
                resumo = item.get(nome)
                if not isinstance(resumo, dict):
                    resumo = {}
                    problemas.append(f"{mercado}_{nome}_ausente")
                numeros = {
                    campo: inteiro(resumo, campo, f"{mercado}_{nome}")
                    for campo in (
                        "resultados", "pendentes", "cronologia_invalida",
                        "desfechos_nao_binarios", "greens", "reds",
                        "neutros",
                    )
                }
                if numeros["resultados"] + numeros["pendentes"] != tamanho:
                    problemas.append(
                        f"{mercado}_{nome}_liquidacao_inconsistente"
                    )
                if (
                    numeros["greens"] + numeros["reds"]
                    + numeros["neutros"] != numeros["resultados"]
                ):
                    problemas.append(
                        f"{mercado}_{nome}_desfechos_inconsistentes"
                    )
                posterior = resumo.get("resultado_posterior_selecao") is True
                if posterior != (numeros["cronologia_invalida"] == 0):
                    problemas.append(
                        f"{mercado}_{nome}_cronologia_inconsistente"
                    )
                resumos[nome] = {
                    **numeros,
                    "roi_real": resumo.get("roi_real"),
                    "ic95_roi_real": resumo.get("ic95_roi_real"),
                    "resultado_posterior_selecao": posterior,
                }
            total = resumos["total"]
            dev = resumos["desenvolvimento_resultados"]
            holdout = resumos["holdout_resultados"]
            controle = resumos["controle_sem_edge"]
            if contagens["faltam_resultados_edge"] != max(
                RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS
                - total["resultados"], 0
            ):
                problemas.append(f"{mercado}_faltam_resultados_divergente")
            if contagens["faltam_resultados_controle"] != max(
                RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS
                - controle["resultados"], 0
            ):
                problemas.append(
                    f"{mercado}_faltam_resultados_controle_divergente"
                )
            comparacao = item.get("comparacao_roi")
            if not isinstance(comparacao, dict):
                comparacao = {}
                problemas.append(f"{mercado}_comparacao_roi_ausente")
            if int(comparacao.get("resultados_edge") or 0) != total["resultados"]:
                problemas.append(f"{mercado}_comparacao_edge_divergente")
            if int(comparacao.get("resultados_sem_edge") or 0) != (
                controle["resultados"]
            ):
                problemas.append(f"{mercado}_comparacao_controle_divergente")
            evidencia_esperada = bool(
                contagens["coorte_edge"]
                >= TAMANHO_COORTE_REFERENCIA_POS_ENVIO
                and total["resultados"]
                >= RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS
                and dev["resultados"]
                >= RESULTADOS_REFERENCIA_POS_ENVIO_DEV_MINIMOS
                and holdout["resultados"]
                >= RESULTADOS_REFERENCIA_POS_ENVIO_HOLDOUT_MINIMOS
                and controle["resultados"]
                >= RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS
                and all(
                    resumo["resultado_posterior_selecao"]
                    for resumo in resumos.values()
                )
            )
            evidencia = item.get("evidencia_completa") is True
            if evidencia != evidencia_esperada:
                problemas.append(f"{mercado}_evidencia_divergente")
            intervalo_total = total.get("ic95_roi_real")
            intervalo_delta = comparacao.get("ic95_delta_roi")
            try:
                vantagem_esperada = bool(
                    evidencia
                    and float(intervalo_total[0]) > 0.0
                    and float(dev["roi_real"]) > 0.0
                    and float(holdout["roi_real"]) > 0.0
                    and float(intervalo_delta[0]) > 0.0
                )
            except (IndexError, TypeError, ValueError):
                vantagem_esperada = False
            vantagem = item.get(
                "vantagem_estatistica_para_revisao"
            ) is True
            if vantagem != vantagem_esperada:
                problemas.append(f"{mercado}_vantagem_divergente")
            if vantagem:
                vantagens.append(mercado)
            mercados_limpos[mercado] = {
                **contagens,
                **resumos,
                "comparacao_roi": comparacao,
                "evidencia_completa": evidencia,
                "vantagem_estatistica_para_revisao": vantagem,
                "decisao": item.get("decisao"),
            }
        if sum(
            item["fotografias_independentes"]
            for item in mercados_limpos.values()
        ) != topo["fotografias_independentes"]:
            problemas.append("fotografias_por_mercado_divergentes")
        vantagens = sorted(vantagens)
        if recorte.get("mercados_para_revisao") != vantagens:
            problemas.append("mercados_para_revisao_divergentes")
        if bool(recorte.get("vantagem_estatistica_para_revisao")) != bool(
            vantagens
        ):
            problemas.append("vantagem_topo_divergente")
        saudavel_recorte = not problemas
        if not saudavel_recorte:
            vantagens = []
            for item in mercados_limpos.values():
                item["evidencia_completa"] = False
                item["vantagem_estatistica_para_revisao"] = False
        return {
            "saudavel": saudavel_recorte,
            "problemas": sorted(set(problemas)),
            "definicao_sha256": fingerprint,
            **topo,
            "exclusoes": recorte.get("exclusoes") or {},
            "por_mercado": mercados_limpos,
            "mercados_para_revisao": vantagens,
            "vantagem_estatistica_para_revisao": bool(vantagens),
            "bloqueia_inferencia": not saudavel_recorte,
        }

    auditoria_referencia_pos_envio = auditar_referencia_pos_envio(
        referencia_pos_envio
    )

    def auditar_recorte_fontes(recorte, *, versao_recorte=None):
        problemas = []
        if not isinstance(recorte, dict):
            recorte = {}
            problemas.append("recorte_ausente")
        observacoes = recorte.get("observacoes_validas")
        if (
            not isinstance(observacoes, int)
            or isinstance(observacoes, bool)
            or observacoes < 0
        ):
            problemas.append("observacoes_validas_invalidas")
            observacoes = 0
        totais = {}
        for campo in ("fontes_observadas", "origens_observacoes"):
            contagens = recorte.get(campo)
            if not isinstance(contagens, dict):
                problemas.append(f"{campo}_ausente")
                contagens = {}
            total = 0
            for nome, quantidade in contagens.items():
                if not isinstance(nome, str) or not nome.strip():
                    problemas.append(f"{campo}_chave_invalida")
                    continue
                if (
                    not isinstance(quantidade, int)
                    or isinstance(quantidade, bool)
                    or quantidade < 0
                ):
                    problemas.append(f"{campo}_contagem_invalida")
                    continue
                total += quantidade
            totais[campo] = total
            if total != observacoes:
                problemas.append(f"{campo}_total_divergente")
        origens = recorte.get("origens_observacoes") or {}
        if isinstance(origens, dict) and not set(origens).issubset(
            ORIGENS_FONTES_OBSERVACIONAIS
        ):
            problemas.append("origem_observacao_desconhecida")
        if (
            recorte.get("fontes_observacionais_versao")
            != VERSAO_FONTES_OBSERVACIONAIS
        ):
            problemas.append("versao_fontes_divergente")
        if recorte.get("contraparte_exige_fonte_independente") is not True:
            problemas.append("fonte_independente_nao_exigida")
        if str(recorte.get("bookmaker") or "").strip().casefold() != (
            BOOKMAKER_DESAJUSTE_ODDS
        ):
            problemas.append("bookmaker_executavel_divergente")
        if versao_recorte is not None and recorte.get("versao") != versao_recorte:
            problemas.append("versao_recorte_divergente")
        return {
            "saudavel": not problemas,
            "problemas": sorted(set(problemas)),
            "observacoes_validas": observacoes,
            "fontes_observadas_total": totais.get("fontes_observadas", 0),
            "origens_observacoes_total": totais.get(
                "origens_observacoes", 0
            ),
            "fontes_observacionais_versao": recorte.get(
                "fontes_observacionais_versao"
            ),
            "contraparte_exige_fonte_independente": (
                recorte.get("contraparte_exige_fonte_independente") is True
            ),
        }

    auditoria_fontes_observacional = auditar_recorte_fontes(observacional)
    auditoria_fontes_convergencia = auditar_recorte_fontes(
        convergencia,
        versao_recorte=VERSAO_CONVERGENCIA_PRECO,
    )
    contrato_fontes_saudavel = bool(
        auditoria_fontes_observacional["saudavel"]
        and auditoria_fontes_convergencia["saudavel"]
    )
    saudavel = bool(
        idade <= 3600.0
        and versao_compativel
        and estado_execucao == ESTADO_AVALIACAO_CONCLUIDO
        and corroboracao_valida
        and integridade_saudavel
        and contrato_fontes_saudavel
        and auditoria_referencia_pos_envio["saudavel"]
    )
    return {
        "saudavel": saudavel,
        "estado": (
            "em_formacao" if saudavel
            else "metodologia_desatualizada" if not versao_compativel
            else "estado_invalido" if not corroboracao_valida
            else "estado_invalido" if not integridade_contrato_valida
            else "integridade_inconsistente"
            if not integridade_saudavel
            else "contrato_fontes_invalido"
            if not contrato_fontes_saudavel
            else "referencia_pos_envio_invalida"
            if not auditoria_referencia_pos_envio["saudavel"]
            else "desatualizada"
        ),
        "motivo": (
            None if saudavel else
            "avaliacao_desajuste_odds_metodologia_desatualizada"
            if not versao_compativel else
            "corroboracao_entrada_rapida_invalida"
            if not corroboracao_valida else
            "integridade_comparacoes_odds_invalida"
            if not integridade_contrato_valida else
            "integridade_comparacoes_odds_inconsistente"
            if not integridade_saudavel else
            "contrato_fontes_observacionais_invalido"
            if not contrato_fontes_saudavel else
            "referencia_pos_envio_invalida"
            if not auditoria_referencia_pos_envio["saudavel"] else
            "avaliacao_desajuste_odds_desatualizada"
        ),
        "versao": versao,
        "versao_esperada": VERSAO_AVALIACAO_DESAJUSTE_ODDS,
        "versao_compativel": versao_compativel,
        "custodia_execucao_versao": dados.get(
            "custodia_execucao_versao"
        ),
        "custodia_execucao_compativel": bool(
            versao_compativel
            and dados.get("custodia_execucao_versao")
            == VERSAO_CUSTODIA_AVALIACAO
        ),
        "cronologia_execucao": auditar_cronologia_execucao(
            dados, agora=agora
        ),
        "efeitos_operacionais": auditar_efeitos_desativados(dados),
        "exposicao_coleta_prospectiva": (
            dados.get("exposicao_coleta_prospectiva") or {}
        ),
        "estado_execucao": estado_execucao,
        "atualizado_em": dados.get("atualizado_em"),
        "iniciado_em": dados.get("iniciado_em"),
        "finalizado_em": dados.get("finalizado_em"),
        "duracao_segundos": dados.get("duracao_segundos"),
        "idade_segundos": round(idade, 3),
        "ancora_prospectiva_em": dados.get("ancora_prospectiva_em"),
        "comparacoes": int(dados.get("comparacoes") or 0),
        "candidatos_independentes": int(
            dados.get("candidatos_independentes") or 0
        ),
        "jogos_distintos": int(dados.get("jogos_distintos") or 0),
        "com_seguimento_5m": int(dados.get("com_seguimento_5m") or 0),
        "persistentes_5m": int(dados.get("persistentes_5m") or 0),
        "taxa_persistencia_5m": dados.get("taxa_persistencia_5m"),
        "ic95_persistencia_5m": dados.get("ic95_persistencia_5m"),
        "pronto_para_revisao": bool(
            saudavel and dados.get("pronto_para_revisao")
        ),
        "persistencia_comprovada": bool(
            saudavel and dados.get("persistencia_comprovada")
        ),
        "integridade_comparacoes_odds": {
            "versao": integridade.get("versao"),
            "versao_comparacao": integridade.get("versao_comparacao"),
            "comparacoes_persistidas": persistidas_integridade,
            "comparacoes_auditadas": auditadas_integridade,
            "comparacoes_validas": validas_integridade,
            "comparacoes_invalidas": invalidas_integridade,
            "auditoria_truncada": bool(
                integridade.get("auditoria_truncada")
            ),
            "problemas": integridade.get("problemas") or {},
            "invalidas_amostra": integridade.get(
                "invalidas_amostra"
            ) or [],
            "fingerprint_evidencias": fingerprint_integridade,
            "saudavel": integridade_saudavel,
            "estado": (
                "integra"
                if integridade_saudavel else "inconsistente"
            ),
            "bloqueia_inferencia": not integridade_saudavel,
        },
        "contrato_fontes_observacionais": {
            "versao_esperada": VERSAO_FONTES_OBSERVACIONAIS,
            "origens_permitidas": sorted(ORIGENS_FONTES_OBSERVACIONAIS),
            "saudavel": contrato_fontes_saudavel,
            "estado": (
                "integro" if contrato_fontes_saudavel else "inconsistente"
            ),
            "recorte_observacional": auditoria_fontes_observacional,
            "recorte_convergencia": auditoria_fontes_convergencia,
            "bloqueia_inferencia": not contrato_fontes_saudavel,
        },
        "corroboracao_entrada_rapida": {
            "marcador": corroboracao.get("marcador"),
            "comparacoes": int(
                corroboracao.get("comparacoes") or 0
            ),
            "fotografias_independentes": int(
                corroboracao.get("fotografias_independentes") or 0
            ),
            "jogos_distintos": int(
                corroboracao.get("jogos_distintos") or 0
            ),
            "por_par_fontes": corroboracao.get("por_par_fontes") or {},
            "por_estado": corroboracao.get("por_estado") or {},
            "por_selecao": corroboracao.get("por_selecao") or {},
            "amostra_minima_fotografias": int(
                corroboracao.get("amostra_minima_fotografias") or 0
            ),
            "jogos_minimos": int(
                corroboracao.get("jogos_minimos") or 0
            ),
            "faltam_fotografias": int(
                corroboracao.get("faltam_fotografias") or 0
            ),
            "faltam_jogos": int(
                corroboracao.get("faltam_jogos") or 0
            ),
            "pronta_para_analise": bool(
                saudavel
                and corroboracao_valida
                and corroboracao.get("pronta_para_analise")
            ),
            "recomendacao": corroboracao.get("recomendacao"),
            "aplicacao_sinais": False,
            "promocao_automatica": False,
            "telegram": False,
        },
        "recorte_executavel": {
            "bookmaker": executavel.get("bookmaker"),
            "ancora_pre_registrada_em": executavel.get(
                "ancora_pre_registrada_em"
            ),
            "candidatos_independentes": int(
                executavel.get("candidatos_independentes") or 0
            ),
            "jogos_distintos": int(
                executavel.get("jogos_distintos") or 0
            ),
            "com_seguimento_mesma_bookmaker_5m": int(
                executavel.get(
                    "com_seguimento_mesma_bookmaker_5m"
                ) or 0
            ),
            "persistentes_mesma_bookmaker_5m": int(
                executavel.get(
                    "persistentes_mesma_bookmaker_5m"
                ) or 0
            ),
            "taxa_persistencia_mesma_bookmaker_5m": executavel.get(
                "taxa_persistencia_mesma_bookmaker_5m"
            ),
            "ic95_persistencia_mesma_bookmaker_5m": executavel.get(
                "ic95_persistencia_mesma_bookmaker_5m"
            ),
            "pronto_para_revisao": bool(
                saudavel and executavel.get("pronto_para_revisao")
            ),
            "persistencia_comprovada": bool(
                saudavel
                and executavel.get("persistencia_comprovada")
            ),
            "vantagem_executavel_comprovada": bool(
                saudavel
                and executavel.get("vantagem_executavel_comprovada")
            ),
            "resultados_gols_ft": executavel.get(
                "resultados_gols_ft"
            ) or {},
            "cobertura_comparacao": executavel.get(
                "cobertura_comparacao"
            ) or {},
            "aplicacao_sinais": False,
            "promocao_automatica": False,
            "telegram": False,
        },
        "recorte_observacional_executavel": {
            "bookmaker": observacional.get("bookmaker"),
            "ancora_pre_registrada_em": observacional.get(
                "ancora_pre_registrada_em"
            ),
            "relogio_seguimento_inicia_quando_ambas_fontes_conhecidas": bool(
                observacional.get(
                    "relogio_seguimento_inicia_quando_ambas_fontes_conhecidas"
                )
            ),
            "unidade_independente": observacional.get(
                "unidade_independente"
            ),
            "observacoes_validas": int(
                observacional.get("observacoes_validas") or 0
            ),
            "fontes_observadas": observacional.get(
                "fontes_observadas"
            ) or {},
            "origens_observacoes": observacional.get(
                "origens_observacoes"
            ) or {},
            "fontes_observacionais_versao": observacional.get(
                "fontes_observacionais_versao"
            ),
            "contraparte_exige_fonte_independente": (
                observacional.get(
                    "contraparte_exige_fonte_independente"
                ) is True
            ),
            "pares_temporais": int(
                observacional.get("pares_temporais") or 0
            ),
            "candidatos_independentes": int(
                observacional.get("candidatos_independentes") or 0
            ),
            "jogos_distintos": int(
                observacional.get("jogos_distintos") or 0
            ),
            "com_seguimento_mesma_bookmaker_5m": int(
                observacional.get(
                    "com_seguimento_mesma_bookmaker_5m"
                ) or 0
            ),
            "persistentes_mesma_bookmaker_5m": int(
                observacional.get(
                    "persistentes_mesma_bookmaker_5m"
                ) or 0
            ),
            "taxa_persistencia_mesma_bookmaker_5m": observacional.get(
                "taxa_persistencia_mesma_bookmaker_5m"
            ),
            "ic95_persistencia_mesma_bookmaker_5m": observacional.get(
                "ic95_persistencia_mesma_bookmaker_5m"
            ),
            "pronto_para_revisao": bool(
                saudavel
                and observacional.get("pronto_para_revisao")
            ),
            "persistencia_comprovada": bool(
                saudavel
                and observacional.get("persistencia_comprovada")
            ),
            "vantagem_executavel_comprovada": bool(
                saudavel
                and observacional.get("vantagem_executavel_comprovada")
            ),
            "resultados_gols_ft": observacional.get(
                "resultados_gols_ft"
            ) or {},
            "exclusoes_pareamento": observacional.get(
                "exclusoes_pareamento"
            ) or {},
            "aplicacao_sinais": False,
            "promocao_automatica": False,
            "telegram": False,
        },
        "recorte_convergencia_preco_prospectivo": {
            "versao": convergencia.get("versao"),
            "definicao_sha256": convergencia.get("definicao_sha256"),
            "ancora_pre_registrada_em": convergencia.get(
                "ancora_pre_registrada_em"
            ),
            "bookmaker": convergencia.get("bookmaker"),
            "estado": convergencia.get("estado"),
            "decisao": convergencia.get("decisao"),
            "coorte_fechada": bool(convergencia.get("coorte_fechada")),
            "evidencia_completa": bool(
                saudavel and convergencia.get("evidencia_completa")
            ),
            "vantagem_executavel_comprovada": bool(
                saudavel
                and convergencia.get("vantagem_executavel_comprovada")
            ),
            "tamanho_coorte": int(
                convergencia.get("tamanho_coorte") or 0
            ),
            "candidatos_independentes": int(
                convergencia.get("candidatos_independentes") or 0
            ),
            "observacoes_validas": int(
                convergencia.get("observacoes_validas") or 0
            ),
            "fontes_observadas": convergencia.get(
                "fontes_observadas"
            ) or {},
            "origens_observacoes": convergencia.get(
                "origens_observacoes"
            ) or {},
            "fontes_observacionais_versao": convergencia.get(
                "fontes_observacionais_versao"
            ),
            "contraparte_exige_fonte_independente": (
                convergencia.get(
                    "contraparte_exige_fonte_independente"
                ) is True
            ),
            "pares_temporais": int(
                convergencia.get("pares_temporais") or 0
            ),
            "total": convergencia.get("total") or {},
            "desenvolvimento": convergencia.get(
                "desenvolvimento"
            ) or {},
            "holdout": convergencia.get("holdout") or {},
            "criterios": convergencia.get("criterios") or {},
            "faltam_candidatos": int(
                convergencia.get("faltam_candidatos") or 0
            ),
            "faltam_seguimentos": int(
                convergencia.get("faltam_seguimentos") or 0
            ),
            "faltam_resultados": int(
                convergencia.get("faltam_resultados") or 0
            ),
            "aplicacao_sinais": False,
            "promocao_automatica": False,
            "telegram": False,
        },
        "recorte_convergencia_escanteios_prospectivo": {
            "versao": convergencia_escanteios.get("versao"),
            "definicao_sha256": convergencia_escanteios.get(
                "definicao_sha256"
            ),
            "ancora_pre_registrada_em": convergencia_escanteios.get(
                "ancora_pre_registrada_em"
            ),
            "bookmaker": convergencia_escanteios.get("bookmaker"),
            "mercado": convergencia_escanteios.get("mercado"),
            "estado": convergencia_escanteios.get("estado"),
            "decisao": convergencia_escanteios.get("decisao"),
            "coorte_fechada": bool(
                convergencia_escanteios.get("coorte_fechada")
            ),
            "evidencia_completa": bool(
                saudavel
                and convergencia_escanteios.get("evidencia_completa")
            ),
            "vantagem_executavel_comprovada": bool(
                saudavel and convergencia_escanteios.get(
                    "vantagem_executavel_comprovada"
                )
            ),
            "tamanho_coorte": int(
                convergencia_escanteios.get("tamanho_coorte") or 0
            ),
            "comparacoes_temporais_validas": int(
                convergencia_escanteios.get(
                    "comparacoes_temporais_validas"
                ) or 0
            ),
            "registros_odds_temporais": int(
                convergencia_escanteios.get(
                    "registros_odds_temporais"
                ) or 0
            ),
            "observacoes_validas": int(
                convergencia_escanteios.get("observacoes_validas") or 0
            ),
            "pares_temporais": int(
                convergencia_escanteios.get("pares_temporais") or 0
            ),
            "candidatos_independentes": int(
                convergencia_escanteios.get(
                    "candidatos_independentes"
                ) or 0
            ),
            "total": convergencia_escanteios.get("total") or {},
            "desenvolvimento": convergencia_escanteios.get(
                "desenvolvimento"
            ) or {},
            "holdout": convergencia_escanteios.get("holdout") or {},
            "criterios": convergencia_escanteios.get("criterios") or {},
            "faltam_candidatos": int(
                convergencia_escanteios.get("faltam_candidatos") or 0
            ),
            "faltam_seguimentos": int(
                convergencia_escanteios.get("faltam_seguimentos") or 0
            ),
            "faltam_resultados": int(
                convergencia_escanteios.get("faltam_resultados") or 0
            ),
            "aplicacao_sinais": False,
            "promocao_automatica": False,
            "telegram": False,
        },
        "recorte_edge_sem_vig_multifonte": {
            "versao": edge_sem_vig.get("versao"),
            "definicao_sha256": auditoria_edge_sem_vig[
                "definicao_sha256"
            ],
            "ancora_pre_registrada_em": edge_sem_vig.get(
                "ancora_pre_registrada_em"
            ),
            "bookmaker_executavel": edge_sem_vig.get(
                "bookmaker_executavel"
            ),
            "estado": edge_sem_vig.get("estado"),
            "decisao": edge_sem_vig.get("decisao"),
            "linhas_elegiveis": auditoria_edge_sem_vig[
                "linhas_elegiveis"
            ],
            "fotografias_completas": auditoria_edge_sem_vig[
                "fotografias_completas"
            ],
            "candidatos_brutos": auditoria_edge_sem_vig[
                "candidatos_brutos"
            ],
            "candidatos_independentes": auditoria_edge_sem_vig[
                "candidatos_independentes"
            ],
            "coorte": auditoria_edge_sem_vig["coorte"],
            "jogos": auditoria_edge_sem_vig["jogos"],
            "desenvolvimento": auditoria_edge_sem_vig[
                "desenvolvimento"
            ],
            "holdout": auditoria_edge_sem_vig["holdout"],
            "ev_medio_candidatos": edge_sem_vig.get(
                "ev_medio_candidatos"
            ),
            "ev_maximo_candidatos": edge_sem_vig.get(
                "ev_maximo_candidatos"
            ),
            "por_categoria": edge_sem_vig.get("por_categoria") or {},
            "por_fonte_controle": edge_sem_vig.get(
                "por_fonte_controle"
            ) or {},
            "exclusoes": edge_sem_vig.get("exclusoes") or {},
            "criterios": edge_sem_vig.get("criterios") or {},
            "liquidacao_resultados": auditoria_edge_sem_vig[
                "liquidacao_resultados"
            ],
            "pronto_para_revisao_metodologica": bool(
                auditoria_edge_sem_vig["saudavel"]
                and edge_sem_vig.get(
                    "pronto_para_revisao_metodologica"
                )
            ),
            "vantagem_executavel_comprovada": False,
            "faltam_coorte": auditoria_edge_sem_vig["faltam_coorte"],
            "faltam_revisao": auditoria_edge_sem_vig[
                "faltam_revisao"
            ],
            "faltam_jogos_revisao": auditoria_edge_sem_vig[
                "faltam_jogos_revisao"
            ],
            "selecao_antes_resultado": bool(
                auditoria_edge_sem_vig["saudavel"]
                and edge_sem_vig.get("selecao_antes_resultado") is True
            ),
            "saudavel": auditoria_edge_sem_vig["saudavel"],
            "problemas": auditoria_edge_sem_vig["problemas"],
            "bloqueia_inferencia": not auditoria_edge_sem_vig["saudavel"],
            "aplicacao_sinais": False,
            "promocao_automatica": False,
            "telegram": False,
        },
        "recorte_referencia_pos_envio": {
            "versao": referencia_pos_envio.get("versao"),
            "definicao_sha256": auditoria_referencia_pos_envio[
                "definicao_sha256"
            ],
            "ancora_pre_registrada_em": referencia_pos_envio.get(
                "ancora_pre_registrada_em"
            ),
            "auditorias_pos_envio": auditoria_referencia_pos_envio[
                "auditorias_pos_envio"
            ],
            "fotografias_elegiveis": auditoria_referencia_pos_envio[
                "fotografias_elegiveis"
            ],
            "fotografias_independentes": auditoria_referencia_pos_envio[
                "fotografias_independentes"
            ],
            "exclusoes": auditoria_referencia_pos_envio["exclusoes"],
            "por_mercado": auditoria_referencia_pos_envio["por_mercado"],
            "mercados_para_revisao": auditoria_referencia_pos_envio[
                "mercados_para_revisao"
            ],
            "vantagem_estatistica_para_revisao": bool(
                saudavel
                and auditoria_referencia_pos_envio[
                    "vantagem_estatistica_para_revisao"
                ]
            ),
            "selecao_antes_resultado": bool(
                auditoria_referencia_pos_envio["saudavel"]
                and referencia_pos_envio.get("selecao_antes_resultado")
                is True
            ),
            "saudavel": auditoria_referencia_pos_envio["saudavel"],
            "problemas": auditoria_referencia_pos_envio["problemas"],
            "bloqueia_inferencia": auditoria_referencia_pos_envio[
                "bloqueia_inferencia"
            ],
            "aplicacao_sinais": False,
            "altera_calibracao": False,
            "altera_prioridade": False,
            "promocao_automatica": False,
            "telegram": False,
        },
        "aplicacao_sinais": False,
        "promocao_automatica": False,
        "telegram": False,
    }

@_resposta_avaliacao_observacional
def verificar_avaliacao_quarentena_fallback_ht(caminho, *, agora=None):
    """Expõe a coorte HT sem reabilitar automaticamente a política."""
    agora = agora or datetime.now()
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "saudavel": True,
            "estado": "aguardando_primeira_avaliacao",
            "motivo": None,
            "aplicacao_sinais": False,
            "reativacao_automatica": False,
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as erro:
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_quarentena_fallback_ht_invalida",
            "erro": resumir_erro_seguro(erro),
            "aplicacao_sinais": False,
            "reativacao_automatica": False,
        }
    try:
        atualizado = datetime.fromisoformat(str(dados["atualizado_em"]))
    except (KeyError, TypeError, ValueError):
        return {
            "saudavel": False,
            "estado": "estado_invalido",
            "motivo": "avaliacao_quarentena_fallback_ht_sem_data",
            "aplicacao_sinais": False,
            "reativacao_automatica": False,
        }
    if atualizado.tzinfo is not None:
        atualizado = atualizado.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = max((agora - atualizado).total_seconds(), 0.0)
    fresco = idade <= 3600.0
    versao_compativel = (
        dados.get("versao") == VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT
    )
    bloqueio_execucao = _bloqueio_custodia_avaliacao(
        dados,
        versao_compativel=versao_compativel,
        idade_segundos=idade,
        prefixo_motivo="avaliacao_quarentena_fallback_ht",
        motivo_falha="avaliacao_quarentena_fallback_ht_falhou",
        agora=agora,
    )
    if bloqueio_execucao is not None:
        return {
            **bloqueio_execucao,
            "versao": dados.get("versao"),
            "versao_esperada": VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT,
            "versao_compativel": True,
            "metodologia_compativel": False,
            "ancora_metodologia_v2_pre_registrada": False,
            "politica_operacional_ativa": False,
            "pronto_para_revisao": False,
            "vantagem_linhas_altas_comprovada": False,
            "prejuizo_linhas_altas_comprovado": False,
        }
    regra_compativel = (
        dados.get("regra_versao_alvo")
        == REGRA_VERSAO_QUARENTENA_FALLBACK_HT
    )
    status_compativel = (
        dados.get("status_coorte")
        == STATUS_COORTE_QUARENTENA_FALLBACK_HT
    )
    ancora_pre_registrada = (
        dados.get("ancora_metodologia_v2_pre_registrada") is True
    )
    metodologia_compativel = bool(
        versao_compativel and regra_compativel and status_compativel
    )
    saudavel = bool(
        fresco and metodologia_compativel and ancora_pre_registrada
    )
    if not metodologia_compativel:
        estado = "metodologia_desatualizada"
        motivo = "avaliacao_quarentena_fallback_ht_metodologia_desatualizada"
    elif not ancora_pre_registrada:
        estado = "ancora_nao_pre_registrada"
        motivo = "avaliacao_quarentena_fallback_ht_ancora_nao_pre_registrada"
    elif not fresco:
        estado = "desatualizada"
        motivo = "avaliacao_quarentena_fallback_ht_desatualizada"
    else:
        estado = (
            "pronta_para_revisao"
            if dados.get("pronto_para_revisao") else "em_formacao"
        )
        motivo = None
    grupos = dados.get("por_grupo") or {}
    quarentena = grupos.get("quarentena_linhas_altas") or {}
    controle = grupos.get("controle_ht_0_5") or {}
    cronologia = dados.get("cronologia_por_grupo") or {}
    holdout_quarentena = (
        cronologia.get("quarentena_linhas_altas") or {}
    ).get("holdout_30") or {}
    holdout_controle = (
        cronologia.get("controle_ht_0_5") or {}
    ).get("holdout_30") or {}
    auditoria = dados.get("auditoria_independencia") or {}
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": motivo,
        "versao": dados.get("versao"),
        "versao_esperada": VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT,
        "versao_compativel": versao_compativel,
        "custodia_execucao_versao": dados.get(
            "custodia_execucao_versao"
        ),
        "custodia_execucao_compativel": bool(
            versao_compativel
            and dados.get("custodia_execucao_versao")
            == VERSAO_CUSTODIA_AVALIACAO
        ),
        "cronologia_execucao": auditar_cronologia_execucao(
            dados, agora=agora
        ),
        "efeitos_operacionais": auditar_efeitos_desativados(dados),
        "exposicao_coleta_prospectiva": (
            dados.get("exposicao_coleta_prospectiva") or {}
        ),
        "estado_execucao": dados.get("estado_execucao"),
        "metodologia_compativel": metodologia_compativel,
        "regra_versao_alvo": dados.get("regra_versao_alvo"),
        "regra_versao_esperada": REGRA_VERSAO_QUARENTENA_FALLBACK_HT,
        "status_coorte": dados.get("status_coorte"),
        "status_coorte_esperado": STATUS_COORTE_QUARENTENA_FALLBACK_HT,
        "politica_versao": dados.get("politica_versao"),
        "atualizado_em": dados.get("atualizado_em"),
        "iniciado_em": dados.get("iniciado_em"),
        "finalizado_em": dados.get("finalizado_em"),
        "duracao_segundos": dados.get("duracao_segundos"),
        "idade_segundos": round(idade, 3),
        "ancora_prospectiva_em": dados.get("ancora_prospectiva_em"),
        "ancora_metodologia_v2_pre_registrada": ancora_pre_registrada,
        "unidades_independentes": int(
            auditoria.get("unidades_independentes") or 0
        ),
        "decisoes_brutas_elegiveis": int(
            auditoria.get("candidatos_elegiveis") or 0
        ),
        "politica_operacional_ativa": bool(
            dados.get("politica_operacional_ativa")
        ),
        "resultados_quarentena": int(
            quarentena.get("resultados") or 0
        ),
        "roi_quarentena": quarentena.get("roi"),
        "resultados_controle": int(controle.get("resultados") or 0),
        "roi_controle": controle.get("roi"),
        "resultados_holdout_quarentena": int(
            holdout_quarentena.get("resultados") or 0
        ),
        "resultados_holdout_controle": int(
            holdout_controle.get("resultados") or 0
        ),
        "pronto_para_revisao": bool(
            metodologia_compativel and ancora_pre_registrada
            and dados.get("pronto_para_revisao")
        ),
        "vantagem_linhas_altas_comprovada": bool(
            metodologia_compativel and ancora_pre_registrada
            and dados.get("vantagem_linhas_altas_comprovada")
        ),
        "prejuizo_linhas_altas_comprovado": bool(
            metodologia_compativel and ancora_pre_registrada
            and dados.get("prejuizo_linhas_altas_comprovado")
        ),
        "aplicacao_sinais": False,
        "reativacao_automatica": False,
        "telegram": False,
    }
